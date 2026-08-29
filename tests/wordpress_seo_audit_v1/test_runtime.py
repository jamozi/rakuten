from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
from typing import Any

import pytest

from scripts import raos_wordpress_seo_audit as audit


OBSERVED = "2026-08-30T00:00:00Z"


def response(url: str, status: int, body: str, **headers: str) -> audit.HttpResponse:
    base_headers = {"Content-Type": "text/html; charset=UTF-8"}
    base_headers.update(headers)
    return audit.HttpResponse(
        url=url,
        status=status,
        headers=tuple(base_headers.items()),
        body=body.encode("utf-8"),
        observed_at=OBSERVED,
    )


def html(item: audit.InventoryItem, required: frozenset[str]) -> str:
    graph = [{"@type": schema_type} for schema_type in sorted(required)]
    return f"""<!doctype html><html><head>
<title>Valid title</title>
<meta name="description" content="Valid description">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{item.url}">
<meta property="og:title" content="Valid title">
<meta property="og:description" content="Valid description">
<meta property="og:url" content="{item.url}">
<meta property="og:image" content="https://kurashinoshirube.com/media/og.webp">
<script type="application/ld+json">{json.dumps({"@graph": graph})}</script>
</head><body>Public content</body></html>"""


class FakeTransport:
    def __init__(self, responses: dict[str, audit.HttpResponse]) -> None:
        self.responses = responses
        self.requested: list[str] = []

    def get(self, url: str) -> audit.HttpResponse:
        self.requested.append(url)
        return self.responses[url]


@pytest.fixture
def contract() -> audit.AuditContract:
    return audit.load_contract()


@pytest.fixture
def valid_responses(contract: audit.AuditContract) -> dict[str, audit.HttpResponse]:
    responses = {
        item.url: response(
            item.url, 200, html(item, contract.required_types[item.role])
        )
        for item in contract.items
    }
    post_url = contract.origin + "/post-sitemap.xml"
    page_url = contract.origin + "/page-sitemap.xml"
    article_urls = [item.url for item in contract.items if item.role == "article"]
    page_urls = [item.url for item in contract.items if item.role == "fixed_page"]
    responses[contract.robots_url] = response(
        contract.robots_url,
        200,
        "User-agent: *\nDisallow: /wp-admin/\nAllow: /wp-admin/admin-ajax.php\n",
        **{"Content-Type": "text/plain"},
    )
    responses[contract.sitemap_seed_url] = response(
        contract.sitemap_seed_url,
        200,
        sitemap_index([post_url, page_url]),
        **{"Content-Type": "application/xml"},
    )
    responses[post_url] = response(
        post_url, 200, urlset(article_urls), **{"Content-Type": "application/xml"}
    )
    responses[page_url] = response(
        page_url, 200, urlset(page_urls), **{"Content-Type": "application/xml"}
    )
    responses[contract.llms_url] = response(
        contract.llms_url, 404, "not found", **{"Content-Type": "text/plain"}
    )
    return responses


def sitemap_index(urls: list[str]) -> str:
    return (
        "<sitemapindex xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
        + "".join(f"<sitemap><loc>{url}</loc></sitemap>" for url in urls)
        + "</sitemapindex>"
    )


def urlset(urls: list[str]) -> str:
    return (
        "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
        + "".join(f"<url><loc>{url}</loc></url>" for url in urls)
        + "</urlset>"
    )


def run(
    contract: audit.AuditContract,
    valid_responses: dict[str, audit.HttpResponse],
) -> dict[str, Any]:
    return audit.run_audit(FakeTransport(valid_responses), contract)


def failed_checks(report: dict[str, Any], identifier: str) -> set[str]:
    page = next(item for item in report["pages"] if item["identifier"] == identifier)
    return {name for name, check in page["checks"].items() if check["status"] == "FAIL"}


def test_closed_inventory_and_passing_report(
    contract: audit.AuditContract,
    valid_responses: dict[str, audit.HttpResponse],
) -> None:
    report = run(contract, valid_responses)
    assert report["status"] == "PASS"
    assert len(contract.items) == report["inventory_count"] == 14
    assert len(contract.content_urls) == report["content_sitemap_count"] == 13
    assert [item.identifier for item in contract.items if item.role == "article"] == [
        f"a{number:02d}" for number in range(1, 11)
    ]
    assert report["index_state_basis"] == "UNAVAILABLE"
    assert all(
        page["index_state"]["state"] == "UNAVAILABLE" for page in report["pages"]
    )
    assert all(
        page["index_state"]["evidence_sha256"] is None for page in report["pages"]
    )


@pytest.mark.parametrize("status", [404, 301, 302])
def test_non_200_and_redirects_fail_without_following(
    contract: audit.AuditContract,
    valid_responses: dict[str, audit.HttpResponse],
    status: int,
) -> None:
    item = contract.items[1]
    valid_responses[item.url] = replace(valid_responses[item.url], status=status)
    transport = FakeTransport(valid_responses)
    report = audit.run_audit(transport, contract)
    assert failed_checks(report, item.identifier) == {"http_200_no_redirect"}
    assert transport.requested.count(item.url) == 1
    assert contract.items[2].url in transport.requested


def test_wrong_or_duplicate_canonical_fails(
    contract: audit.AuditContract,
    valid_responses: dict[str, audit.HttpResponse],
) -> None:
    item = contract.items[1]
    body = (
        valid_responses[item.url]
        .body.decode()
        .replace(
            f'<link rel="canonical" href="{item.url}">',
            '<link rel="canonical" href="https://kurashinoshirube.com/wrong/">',
        )
    )
    valid_responses[item.url] = response(item.url, 200, body)
    report = run(contract, valid_responses)
    assert "self_canonical" in failed_checks(report, item.identifier)


@pytest.mark.parametrize(
    "robots_value,header_value",
    [
        ("noindex, follow", None),
        ("index, nofollow", None),
        ("index, follow", "noindex"),
    ],
)
def test_meta_and_x_robots_rejections(
    contract: audit.AuditContract,
    valid_responses: dict[str, audit.HttpResponse],
    robots_value: str,
    header_value: str | None,
) -> None:
    item = contract.items[1]
    body = (
        valid_responses[item.url].body.decode().replace("index, follow", robots_value)
    )
    headers = {} if header_value is None else {"X-Robots-Tag": header_value}
    valid_responses[item.url] = response(item.url, 200, body, **headers)
    report = run(contract, valid_responses)
    assert "robots_index_follow" in failed_checks(report, item.identifier)


@pytest.mark.parametrize(
    "needle,expected",
    [
        ("<title>Valid title</title>", "title"),
        ('<meta name="description" content="Valid description">', "meta_description"),
    ],
)
def test_title_and_meta_description_are_required(
    contract: audit.AuditContract,
    valid_responses: dict[str, audit.HttpResponse],
    needle: str,
    expected: str,
) -> None:
    item = contract.items[1]
    body = valid_responses[item.url].body.decode().replace(needle, "")
    valid_responses[item.url] = response(item.url, 200, body)
    report = run(contract, valid_responses)
    assert expected in failed_checks(report, item.identifier)


@pytest.mark.parametrize(
    "property_name,expected",
    [
        ("og:title", "og_title"),
        ("og:description", "og_description"),
        ("og:url", "og_url"),
        ("og:image", "og_image"),
    ],
)
def test_all_open_graph_fields_are_required(
    contract: audit.AuditContract,
    valid_responses: dict[str, audit.HttpResponse],
    property_name: str,
    expected: str,
) -> None:
    item = contract.items[1]
    lines = [
        line
        for line in valid_responses[item.url].body.decode().splitlines()
        if f'property="{property_name}"' not in line
    ]
    valid_responses[item.url] = response(item.url, 200, "\n".join(lines))
    report = run(contract, valid_responses)
    assert expected in failed_checks(report, item.identifier)


def test_missing_required_schema_fails(
    contract: audit.AuditContract,
    valid_responses: dict[str, audit.HttpResponse],
) -> None:
    item = contract.items[1]
    body = valid_responses[item.url].body.decode().replace('"Article"', '"Thing"')
    valid_responses[item.url] = response(item.url, 200, body)
    report = run(contract, valid_responses)
    assert "required_schema" in failed_checks(report, item.identifier)


@pytest.mark.parametrize("forbidden", ["Product", "Offer", "Review", "FAQPage"])
def test_forbidden_schema_types_fail(
    contract: audit.AuditContract,
    valid_responses: dict[str, audit.HttpResponse],
    forbidden: str,
) -> None:
    item = contract.items[1]
    body = (
        valid_responses[item.url]
        .body.decode()
        .replace('"@graph": [', f'"@graph": [{{"@type": "{forbidden}"}}, ')
    )
    valid_responses[item.url] = response(item.url, 200, body)
    report = run(contract, valid_responses)
    assert "forbidden_schema_absent" in failed_checks(report, item.identifier)


def test_robots_txt_disallow_fails_surface(
    contract: audit.AuditContract,
    valid_responses: dict[str, audit.HttpResponse],
) -> None:
    valid_responses[contract.robots_url] = response(
        contract.robots_url, 200, "User-agent: *\nDisallow: /\n"
    )
    report = run(contract, valid_responses)
    assert report["surfaces"]["robots"]["status"] == "FAIL"


@pytest.mark.parametrize("change", ["missing", "extra"])
def test_sitemap_must_equal_exact_thirteen_content_urls(
    contract: audit.AuditContract,
    valid_responses: dict[str, audit.HttpResponse],
    change: str,
) -> None:
    post_url = contract.origin + "/post-sitemap.xml"
    urls = [item.url for item in contract.items if item.role == "article"]
    if change == "missing":
        urls.pop()
    else:
        urls.append(contract.origin + "/unexpected/")
    valid_responses[post_url] = response(post_url, 200, urlset(urls))
    report = run(contract, valid_responses)
    assert report["surfaces"]["sitemap"]["status"] == "FAIL"


def test_llms_txt_presence_fails(
    contract: audit.AuditContract,
    valid_responses: dict[str, audit.HttpResponse],
) -> None:
    valid_responses[contract.llms_url] = response(contract.llms_url, 200, "# Site")
    report = run(contract, valid_responses)
    assert report["surfaces"]["llms_txt_absent"]["status"] == "FAIL"


def test_evidence_hashes_and_freshness_are_always_present(
    contract: audit.AuditContract,
    valid_responses: dict[str, audit.HttpResponse],
) -> None:
    report = run(contract, valid_responses)
    checks = [
        check for page in report["pages"] for check in page["checks"].values()
    ] + list(report["surfaces"].values())
    assert all(check["observed_at"] == OBSERVED for check in checks)
    assert all(len(check["evidence_sha256"]) == 64 for check in checks)
    serialized = json.dumps(report, ensure_ascii=False)
    assert "<html" not in serialized.lower()
    assert "credential" not in serialized.lower()


def test_exact_owner_private_index_input_is_bound_without_http_inference(
    contract: audit.AuditContract,
    valid_responses: dict[str, audit.HttpResponse],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
        private_root = Path(temporary) / ".secrets" / "wordpress-seo-audit-v1"
        private_root.mkdir(parents=True, mode=0o700)
        os.chmod(private_root, 0o700)
        input_path = private_root / "url-inspection.json"
        payload = {
            "schema": "RAOS_OWNER_PRIVATE_URL_INSPECTION_V1",
            "observed_at": OBSERVED,
            "results": [
                {"url": item.url, "state": "INDEXED", "last_crawl_at": OBSERVED}
                for item in contract.items
            ],
        }
        input_path.write_text(json.dumps(payload), encoding="utf-8")
        os.chmod(input_path, 0o600)
        monkeypatch.setattr(audit, "PRIVATE_ROOT", private_root)

        states = audit._load_index_states(input_path, contract)
        report = audit.run_audit(
            FakeTransport(valid_responses), contract, index_states=states
        )

        assert report["index_state_basis"] == (
            "OWNER_PRIVATE_RECORDED_URL_INSPECTION_V1"
        )
        assert all(
            page["index_state"]["state"] == "INDEXED" for page in report["pages"]
        )
        assert all(
            len(page["index_state"]["evidence_sha256"]) == 64
            for page in report["pages"]
        )

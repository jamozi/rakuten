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
    del required
    origin = "https://kurashinoshirube.com"
    title = "Valid title"
    description = "Valid description"
    image = origin + "/wp-content/themes/kurashinoshirube-child/assets/images/home-hero.webp"
    organization_id = origin + "/#organization"
    website_id = origin + "/#website"
    organization = {
        "@id": organization_id,
        "@type": "Organization",
        "name": "暮らしのしるべ編集者",
        "url": origin + "/",
    }
    website = {
        "@id": website_id,
        "@type": "WebSite",
        "inLanguage": "ja-JP",
        "name": "暮らしのしるべ",
        "publisher": {"@id": organization_id},
        "url": origin + "/",
    }
    graph: list[dict[str, Any]] = []
    if item.role == "article":
        graph.append(
            {
                "@id": item.url + "#article",
                "@type": "Article",
                "articleSection": "移動",
                "author": {"@id": organization_id},
                "breadcrumb": {"@id": item.url + "#breadcrumb"},
                "dateModified": "2026-08-30T00:00:00Z",
                "datePublished": "2026-08-29T00:00:00Z",
                "description": description,
                "headline": title,
                "image": [image],
                "inLanguage": "ja-JP",
                "mainEntityOfPage": item.url,
                "publisher": {"@id": organization_id},
                "url": item.url,
            }
        )
    elif item.role == "fixed_page":
        page_type = "AboutPage" if item.identifier == "about-ad-policy" else "WebPage"
        graph.append(
            {
                "@id": item.url + "#webpage",
                "@type": page_type,
                "breadcrumb": {"@id": item.url + "#breadcrumb"},
                "description": description,
                "inLanguage": "ja-JP",
                "isPartOf": {"@id": website_id},
                "name": title,
                "url": item.url,
            }
        )
    if item.role != "home":
        graph.append(
            {
                "@id": item.url + "#breadcrumb",
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "item": origin + "/",
                        "name": "ホーム",
                        "position": 1,
                    },
                    {
                        "@type": "ListItem",
                        "item": item.url,
                        "name": title,
                        "position": 2,
                    },
                ],
            }
        )
    graph.extend([organization, website])
    return f"""<!doctype html><html><head>
<title>{title}</title>
<meta name="description" content="{description}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{item.url}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{item.url}">
<meta property="og:image" content="{image}">
<meta property="og:image:width" content="1600">
<meta property="og:image:height" content="900">
<meta property="og:image:type" content="image/webp">
<meta property="og:type" content="{'article' if item.role == 'article' else 'website'}">
<meta property="og:locale" content="ja_JP">
<meta property="og:site_name" content="暮らしのしるべ">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{description}">
<meta name="twitter:image" content="{image}">
<script type="application/ld+json">{json.dumps({"@context": "https://schema.org", "@graph": graph})}</script>
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


@pytest.mark.parametrize(
    "forbidden", ["Product", "Offer", "Review", "AggregateRating", "FAQPage"]
)
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


@pytest.mark.parametrize(
    "old,new,expected",
    [
        (
            '<meta property="og:title" content="Valid title">',
            '<meta property="og:title" content="Different title">',
            "og_title",
        ),
        (
            '<meta name="twitter:image" content="https://kurashinoshirube.com/',
            '<meta name="twitter:image" content="https://kurashinoshirube.com/wrong-',
            "twitter_image",
        ),
        (
            "<title>Valid title</title>",
            "<title>Valid title</title><title>Duplicate</title>",
            "title",
        ),
    ],
)
def test_head_relationship_tampering_fails(
    contract: audit.AuditContract,
    valid_responses: dict[str, audit.HttpResponse],
    old: str,
    new: str,
    expected: str,
) -> None:
    item = contract.items[1]
    body = valid_responses[item.url].body.decode().replace(old, new, 1)
    valid_responses[item.url] = response(item.url, 200, body)

    report = run(contract, valid_responses)

    assert expected in failed_checks(report, item.identifier)


@pytest.mark.parametrize(
    "old,new",
    [
        ("#article", "#tampered-article"),
        (
            '"publisher": {"@id": "https://kurashinoshirube.com/#organization"}',
            '"publisher": {"@id": "https://kurashinoshirube.com/#website"}',
        ),
        ("2026-08-30T00:00:00Z", "2026-08-28T00:00:00Z"),
        (
            '"mainEntityOfPage": "https://kurashinoshirube.com/',
            '"mainEntityOfPage": "https://kurashinoshirube.com/wrong-',
        ),
        (
            '"url": "https://kurashinoshirube.com/',
            '"url": "https://kurashinoshirube.com/wrong-',
        ),
        (
            '"breadcrumb": {"@id": "https://kurashinoshirube.com/',
            '"breadcrumb": {"@id": "https://kurashinoshirube.com/wrong-',
        ),
    ],
)
def test_json_ld_relationship_tampering_fails(
    contract: audit.AuditContract,
    valid_responses: dict[str, audit.HttpResponse],
    old: str,
    new: str,
) -> None:
    item = contract.items[1]
    body = valid_responses[item.url].body.decode().replace(old, new, 1)
    valid_responses[item.url] = response(item.url, 200, body)

    report = run(contract, valid_responses)

    assert "structured_data_semantics" in failed_checks(report, item.identifier)


@pytest.mark.parametrize("field", ["url", "breadcrumb"])
def test_article_json_ld_url_and_breadcrumb_are_required(
    contract: audit.AuditContract,
    valid_responses: dict[str, audit.HttpResponse],
    field: str,
) -> None:
    item = contract.items[1]
    serialized = (
        f', "url": "{item.url}"'
        if field == "url"
        else f', "breadcrumb": {json.dumps({"@id": item.url + "#breadcrumb"})}'
    )
    body = valid_responses[item.url].body.decode().replace(serialized, "", 1)
    assert body != valid_responses[item.url].body.decode()
    valid_responses[item.url] = response(item.url, 200, body)

    report = run(contract, valid_responses)

    assert "structured_data_semantics" in failed_checks(report, item.identifier)


def test_json_ld_non_scalar_top_level_type_fails_closed_without_crashing(
    contract: audit.AuditContract,
    valid_responses: dict[str, audit.HttpResponse],
) -> None:
    item = contract.items[1]
    body = valid_responses[item.url].body.decode().replace(
        '"@type": "Article"',
        '"@type": ["Article"]',
        1,
    )
    valid_responses[item.url] = response(item.url, 200, body)

    report = run(contract, valid_responses)

    assert "structured_data_semantics" in failed_checks(report, item.identifier)


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


def test_yoast_image_locations_are_not_content_urls(
    contract: audit.AuditContract,
    valid_responses: dict[str, audit.HttpResponse],
) -> None:
    post_url = contract.origin + "/post-sitemap.xml"
    article_urls = [item.url for item in contract.items if item.role == "article"]
    entries = []
    for index, url in enumerate(article_urls):
        image = (
            "<image:image><image:loc>"
            f"{contract.origin}/wp-content/uploads/article-{index}.webp"
            "</image:loc></image:image>"
        )
        entries.append(f"<url><loc>{url}</loc>{image}</url>")
    sitemap = (
        "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9' "
        "xmlns:image='http://www.google.com/schemas/sitemap-image/1.1'>"
        + "".join(entries)
        + "</urlset>"
    )
    valid_responses[post_url] = response(post_url, 200, sitemap)

    report = run(contract, valid_responses)

    assert report["surfaces"]["sitemap"]["status"] == "PASS"
    assert report["status"] == "PASS"


def test_home_is_validated_separately_from_exact_content_inventory(
    contract: audit.AuditContract,
    valid_responses: dict[str, audit.HttpResponse],
) -> None:
    page_url = contract.origin + "/page-sitemap.xml"
    page_urls = [item.url for item in contract.items if item.role == "fixed_page"]
    home_url = next(item.url for item in contract.items if item.role == "home")
    valid_responses[page_url] = response(
        page_url,
        200,
        urlset([home_url, *page_urls]),
        **{"Content-Type": "application/xml"},
    )

    report = run(contract, valid_responses)

    assert report["surfaces"]["sitemap"]["status"] == "PASS"
    assert report["surfaces"]["sitemap_home"] == {
        "status": "PASS",
        "detail": "PRESENT_SEPARATE",
        "evidence_sha256": report["surfaces"]["sitemap"]["evidence_sha256"],
        "observed_at": OBSERVED,
    }
    assert report["status"] == "PASS"


def test_home_may_be_absent_from_sitemap(
    contract: audit.AuditContract,
    valid_responses: dict[str, audit.HttpResponse],
) -> None:
    report = run(contract, valid_responses)
    assert report["surfaces"]["sitemap_home"]["status"] == "PASS"
    assert report["surfaces"]["sitemap_home"]["detail"] == "ABSENT_ALLOWED"


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

        first_url = contract.items[0].url
        states[first_url]["state"] = "NOT_INDEXED"
        failed_report = audit.run_audit(
            FakeTransport(valid_responses), contract, index_states=states
        )
        assert failed_report["status"] == "FAIL"
        assert failed_report["pages"][0]["checks"]["gsc_indexed"]["detail"] == (
            "NOT_INDEXED"
        )


def test_live_url_inspection_input_binds_exact_requests_and_provider_states(
    contract: audit.AuditContract,
    valid_responses: dict[str, audit.HttpResponse],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
        private_root = Path(temporary) / ".secrets" / "wordpress-seo-audit-v1"
        private_root.mkdir(parents=True, mode=0o700)
        os.chmod(private_root, 0o700)
        input_path = private_root / "url-inspection.json"
        urls = tuple(item.url for item in contract.items)
        site_url = "sc-domain:kurashinoshirube.com"
        query = audit.SearchConsoleUrlInspectionQuery(
            site_id=audit.UUID("11111111-1111-4111-8111-111111111111"),
            site_url=site_url,
            inspection_urls=urls,
        )
        payload = {
            "schema": "RAOS_OWNER_PRIVATE_URL_INSPECTION_V1",
            "version": 1,
            "source": "GSC_URL_INSPECTION_API_V1",
            "site_id": str(query.site_id),
            "site_url": site_url,
            "observed_at": OBSERVED,
            "request_sha256": query.request_sha256,
            "result_count": 14,
            "results": [
                {
                    "url": url,
                    "state": "INDEXED",
                    "verdict": "PASS",
                    "indexing_state": "INDEXING_ALLOWED",
                    "last_crawl_at": OBSERVED,
                    "request_sha256": (
                        audit.gsc_url_inspection_request_sha256(
                            site_url=site_url,
                            inspection_url=url,
                        )
                    ),
                    "response_sha256": f"{position:x}" * 64,
                }
                for position, url in enumerate(urls)
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
            "OWNER_PRIVATE_LIVE_GSC_URL_INSPECTION_V1"
        )
        first = report["pages"][0]["index_state"]
        assert first["verdict"] == "PASS"
        assert first["indexing_state"] == "INDEXING_ALLOWED"
        assert len(first["request_sha256"]) == 64
        assert first["evidence_sha256"] == first["response_sha256"]


def test_live_url_inspection_input_rejects_request_hash_drift(
    contract: audit.AuditContract,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
        private_root = Path(temporary) / ".secrets" / "wordpress-seo-audit-v1"
        private_root.mkdir(parents=True, mode=0o700)
        os.chmod(private_root, 0o700)
        input_path = private_root / "url-inspection.json"
        urls = tuple(item.url for item in contract.items)
        site_url = "sc-domain:kurashinoshirube.com"
        input_path.write_text(
            json.dumps(
                {
                    "schema": "RAOS_OWNER_PRIVATE_URL_INSPECTION_V1",
                    "version": 1,
                    "source": "GSC_URL_INSPECTION_API_V1",
                    "site_id": "11111111-1111-4111-8111-111111111111",
                    "site_url": site_url,
                    "observed_at": OBSERVED,
                    "request_sha256": "0" * 64,
                    "result_count": 14,
                    "results": [
                        {
                            "url": url,
                            "state": "INDEXED",
                            "verdict": "PASS",
                            "indexing_state": "INDEXING_ALLOWED",
                            "last_crawl_at": OBSERVED,
                            "request_sha256": (
                                audit.gsc_url_inspection_request_sha256(
                                    site_url=site_url,
                                    inspection_url=url,
                                )
                            ),
                            "response_sha256": f"{position:x}" * 64,
                        }
                        for position, url in enumerate(urls)
                    ],
                }
            ),
            encoding="utf-8",
        )
        os.chmod(input_path, 0o600)
        monkeypatch.setattr(audit, "PRIVATE_ROOT", private_root)

        with pytest.raises(audit.AuditError) as failure:
            audit._load_index_states(input_path, contract)

        assert failure.value.code == "INDEX_INPUT_REQUEST_HASH_INVALID"

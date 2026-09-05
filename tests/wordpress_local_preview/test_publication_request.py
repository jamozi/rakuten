from __future__ import annotations

import importlib.util
import hashlib
import html
import json
import os
from dataclasses import replace
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/raos_wordpress_publication_request.py"
SPEC = importlib.util.spec_from_file_location("wordpress_publication_request", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
publication = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = publication
SPEC.loader.exec_module(publication)
ORIGINAL_VERIFY_PUBLIC_PAGES = publication.verify_public_pages
ORIGINAL_TRACKED_THEME_TREE_SHA256 = publication.tracked_theme_tree_sha256
ORIGINAL_STRICT_LOCAL_QUALITY_AUDIT = publication.strict_local_quality_audit
TEST_THEME_TREE_SHA256 = "1" * 64
THEME_REVISION = publication.EXPECTED_THEME_RUNTIME_REVISION


def _test_product_safety_binding() -> dict[str, object]:
    material: dict[str, object] = {
        "schema": "RAOS_PRODUCT_SAFETY_PUBLICATION_BINDING_V1",
        "required_product_count": 33,
        "required_authority_kinds": [
            "MANUFACTURER_OFFICIAL",
            "JAPAN_ADMINISTRATIVE_OFFICIAL",
        ],
        "required_administrative_capture_count": 99,
        "administrative_bundle_sha256": "9" * 64,
        "administrative_capture_count": 99,
        "administrative_verified_product_count": 33,
        "manufacturer_verified_product_count": 33,
        "complete_product_count": 33,
        "complete": True,
    }
    encoded = json.dumps(
        material,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return {
        **material,
        "binding_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _test_quality_audit_binding() -> dict[str, object]:
    return {
        "schema": "RAOS_WORDPRESS_QUALITY_AUDIT_BINDING_V3",
        "audit_phase": publication.wordpress_quality_audit.PRE_PUBLICATION_PHASE_ID,
        "status": "COMPLETE",
        "completion_state": (
            publication.wordpress_quality_audit.PRE_PUBLICATION_COMPLETION_STATE
        ),
        "production_parity_state": (
            publication.wordpress_quality_audit.POST_APPLY_PENDING_STATE
        ),
        "evaluated_at": "2026-08-31T00:00:00Z",
        "contract_file_sha256": "7" * 64,
        "ledger_file_sha256": "8" * 64,
        "ledger_sha256": "9" * 64,
        "fingerprint_bundle_sha256": "a" * 64,
        "latest_round_sha256": "b" * 64,
        "round_count": 2,
        "consecutive_clean_rounds": 2,
        "attestation_payload_sha256": "c" * 64,
        "attestation_signature_sha256": "d" * 64,
        "reviewer_key_id": "trusted-independent-reviewer-key-001",
        "reviewer_id": "independent-reviewer-bravo",
        "expires_at": "2099-08-31T00:15:00Z",
        "reviewer_attestation_verified": True,
    }


def _quality_input_paths(tmp_path: Path) -> tuple[Path, Path]:
    return (
        (tmp_path / "quality-attestation.json").resolve(),
        (tmp_path / "quality-attestation.ed25519.b64").resolve(),
    )


def _test_codex_quality_binding() -> dict[str, object]:
    audit = publication.wordpress_quality_audit
    return {
        **audit.CODEX_OWNER_BINDING_FIXED,
        **{key: "a" * 64 for key in audit.CODEX_OWNER_HASH_FIELDS},
        "evaluated_at": "2026-09-05T00:00:00Z",
        "expires_at": "2026-09-05T00:10:00Z",
        "round_count": 2,
        "consecutive_clean_rounds": 2,
    }


def test_audit_mode_is_explicit_and_does_not_default_to_codex() -> None:
    assert (
        publication.parser().parse_args([]).quality_audit_mode == "signed-independent"
    )
    arguments = publication.parser().parse_args(
        [
            "--quality-audit-mode",
            "codex-owner",
            "--codex-audit-report",
            "/tmp/report.json",
        ]
    )
    assert arguments.quality_audit_mode == "codex-owner"
    assert arguments.codex_audit_report == Path("/tmp/report.json")


@pytest.mark.parametrize(
    "earliest", ["audit", "local", "production", "product", "sales"]
)
def test_codex_wait_deadline_uses_earliest_bound_evidence(
    monkeypatch: pytest.MonkeyPatch,
    earliest: str,
) -> None:
    real_datetime = publication.datetime

    class FixedDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 5, tzinfo=publication.UTC)

    monkeypatch.setattr(publication, "datetime", FixedDateTime)
    products = [
        {
            "product_id": f"PRD-SYNTHETIC-{index}",
            "state": "verified",
            "retrieved_at": "2026-09-04T00:20:00Z",
        }
        for index in range(33)
    ]
    if earliest == "product":
        products[-1]["retrieved_at"] = "2026-09-04T00:05:00Z"
    inputs = {
        publication.LOCAL_MATERIALIZATION_RECEIPT: {
            "generated_at": "2026-09-04T23:50:00Z"
            if earliest == "local"
            else "2026-09-05T00:00:00Z",
        },
        publication.PRODUCTION_MATERIALIZATION_RECEIPT: {
            "generated_at": "2026-09-04T23:50:00Z"
            if earliest == "production"
            else "2026-09-05T00:00:00Z",
        },
        publication.ROOT / publication.V2_STATUS_RELATIVE_PATH: {"products": products},
    }
    snapshots = {path: (row, json.dumps(row).encode()) for path, row in inputs.items()}
    materialization = {
        "products": {row["product_id"]: {} for row in products},
        "manufacturer_sales_state_checked_at_utc": "2026-09-04T00:05:00Z"
        if earliest == "sales"
        else "2026-09-04T00:20:00Z",
    }
    for path, key in (
        (publication.LOCAL_MATERIALIZATION_RECEIPT, "local_receipt_sha256"),
        (publication.PRODUCTION_MATERIALIZATION_RECEIPT, "production_receipt_sha256"),
        (
            publication.ROOT / publication.V2_STATUS_RELATIVE_PATH,
            "evidence_status_sha256",
        ),
    ):
        materialization[key] = hashlib.sha256(snapshots[path][1]).hexdigest()
    quality = _test_codex_quality_binding()
    if earliest == "audit":
        quality["expires_at"] = "2026-09-05T00:05:00Z"
    receipt = {
        "quality_audit_binding": quality,
        "materialization_binding": materialization,
    }
    monkeypatch.setattr(
        publication,
        "_load_owner_private_json_snapshot",
        lambda path, *_a: snapshots[path],
    )
    assert (
        publication._codex_publication_evidence_expiry(receipt)
        == "2026-09-05T00:05:00Z"
    )
    materialization["local_receipt_sha256"] = "0" * 64
    with pytest.raises(
        publication.PublicationFailure, match="CODEX_EVIDENCE_DEADLINE_INVALID"
    ):
        publication._codex_publication_evidence_expiry(receipt)


def test_codex_deadline_is_forwarded_to_bounded_apply(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = {
        "batch_registration": {
            "batch_token": "a" * 64,
            "batch_manifest_sha256": "b" * 64,
        },
        "proposals": [],
        "quality_audit_binding": _test_codex_quality_binding(),
    }
    monkeypatch.setattr(publication, "_registered_proposal_ids", lambda _r: ["c" * 64])
    monkeypatch.setattr(publication, "_operation_ids", lambda _r: {})
    monkeypatch.setattr(publication, "_touch_receipt", lambda *_a: None)
    monkeypatch.setattr(
        publication,
        "_codex_publication_evidence_expiry",
        lambda _r: "2026-09-05T00:05:00Z",
    )

    def inspect_call(command, payload, **_kwargs):
        assert command == "release-wait-and-apply"
        assert payload["evidence_expires_at_gmt"] == "2026-09-05T00:05:00Z"
        raise publication.PublicationFailure("TEST_STOP_NO_LIVE_CALL")

    monkeypatch.setattr(publication, "_deployment_mcp_call", inspect_call)
    with pytest.raises(publication.PublicationFailure, match="TEST_STOP_NO_LIVE_CALL"):
        publication.wait_and_apply(receipt, tmp_path / "receipt.json")
    output = capsys.readouterr().out
    assert "人間による第三者署名ではありません" in output
    assert "承認後も延長されません" in output


@pytest.mark.parametrize(
    ("mode", "attestation", "signature", "report"),
    [
        ("signed-independent", None, None, "/tmp/codex.json"),
        ("codex-owner", "/tmp/attestation.json", None, "/tmp/codex.json"),
        ("codex-owner", None, "/tmp/signature.txt", "/tmp/codex.json"),
        ("codex-owner", None, None, None),
        ("codex-owner", None, None, "relative.json"),
        ("automatic", None, None, "/tmp/codex.json"),
    ],
)
def test_audit_modes_reject_mixed_or_missing_inputs(
    mode: str,
    attestation: str | None,
    signature: str | None,
    report: str | None,
) -> None:
    with pytest.raises(publication.PublicationFailure):
        publication._require_quality_audit_inputs(
            Path(attestation) if attestation else None,
            Path(signature) if signature else None,
            audit_mode=mode,
            codex_report_path=Path(report) if report else None,
        )


def test_codex_mode_requires_report_before_lock_or_wordpress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        publication, "validate_publication_link_evidence", lambda *_a, **_k: object()
    )
    monkeypatch.setattr(
        publication, "request_lock", lambda: pytest.fail("must not acquire lock")
    )
    with pytest.raises(
        publication.PublicationFailure, match="CODEX_AUDIT_REPORT_REQUIRED"
    ):
        publication.execute(
            "all",
            link_mode="standard-api",
            standard_api_receipt=Path("/tmp/api.json"),
            quality_audit_mode="codex-owner",
            client_factory=lambda: pytest.fail("no live call"),
        )


def test_codex_dispatch_never_calls_signed_verifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = Path("/tmp/codex-owner.json")
    calls: list[Path] = []
    monkeypatch.setattr(
        publication, "strict_local_quality_audit", lambda *_a: pytest.fail("not signed")
    )
    monkeypatch.setattr(
        publication.wordpress_quality_audit,
        "validate_codex_owner_report",
        lambda value: calls.append(value) or _test_codex_quality_binding(),
    )
    binding = publication.publication_quality_audit(
        None,
        None,
        audit_mode="codex-owner",
        codex_report_path=path,
    )
    assert calls == [path]
    assert binding["publication_authority"] is False
    publication._validate_quality_audit_binding(binding)
    binding["reviewer_attestation_verified"] = True
    with pytest.raises(publication.PublicationFailure, match="RECEIPT_INVALID"):
        publication._validate_quality_audit_binding(binding)


@pytest.mark.parametrize("drift", [False, True])
def test_apply_revalidation_preserves_codex_mode_and_exact_review_hash(
    monkeypatch: pytest.MonkeyPatch,
    drift: bool,
) -> None:
    activation = SimpleNamespace(production_fixture_root=Path("/tmp/fixture"))
    current = _test_codex_quality_binding()
    stored = dict(current)
    if drift:
        stored["codex_report_sha256"] = "b" * 64
    receipt = {
        "desired_sha256": {},
        "desired_theme_tree_sha256": TEST_THEME_TREE_SHA256,
        "desired_theme_runtime_revision": THEME_REVISION,
        "materialization_binding": {},
        "quality_audit_binding": stored,
    }
    monkeypatch.setattr(
        publication, "validate_publication_link_evidence", lambda *_a, **_k: activation
    )
    monkeypatch.setattr(publication, "load_publication_items", lambda *_a, **_k: [])
    monkeypatch.setattr(
        publication, "activation_materialization_binding", lambda *_a, **_k: {}
    )
    monkeypatch.setattr(
        publication,
        "strict_local_quality_audit",
        lambda *_a: pytest.fail("no mode switch"),
    )
    monkeypatch.setattr(
        publication.wordpress_quality_audit,
        "validate_codex_owner_report",
        lambda _p: current,
    )
    kwargs = {
        "rakuten_activation_dry_run": Path("/tmp/api.json"),
        "expected_activation": activation,
        "quality_audit_attestation": None,
        "quality_audit_signature": None,
        "quality_audit_mode": "codex-owner",
        "codex_audit_report": Path("/tmp/codex.json"),
    }
    if drift:
        with pytest.raises(
            publication.PublicationFailure, match="PENDING_REQUEST_CONFLICT"
        ):
            publication._revalidate_apply_inputs(receipt, **kwargs)
    else:
        assert publication._revalidate_apply_inputs(receipt, **kwargs)[3] == current


def _resume_gate_kwargs(tmp_path: Path) -> dict[str, Path]:
    attestation_path, signature_path = _quality_input_paths(tmp_path)
    return {
        "rakuten_activation_dry_run": (
            tmp_path / "activation-dry-run-v2.json"
        ).resolve(),
        "quality_audit_attestation": attestation_path,
        "quality_audit_signature": signature_path,
    }


@pytest.fixture(autouse=True)
def no_live_public_readback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        publication,
        "verify_public_pages",
        lambda articles, **_kwargs: {
            article.production_slug: {
                "url": f"{publication.ORIGIN}/{article.production_slug}/",
                "status": 200,
            }
            for article in articles
        },
    )
    # The shared integration worktree intentionally contains the candidate
    # 1.5.1 theme. Workflow unit tests use a stable reviewed tree while the
    # production function continues to refuse dirty theme sources.
    monkeypatch.setattr(
        publication,
        "tracked_theme_tree_sha256",
        lambda: TEST_THEME_TREE_SHA256,
    )
    monkeypatch.setattr(
        publication,
        "strict_public_seo_audit",
        lambda: {
            "schema": "RAOS_WORDPRESS_SEO_AUDIT_BINDING_V1",
            "origin": publication.ORIGIN,
            "status": "PASS",
            "generated_at": "2026-08-31T00:00:00Z",
            "inventory_count": 14,
            "content_sitemap_count": 13,
            "contract_sha256": "2" * 64,
            "portfolio_sha256": "3" * 64,
            "report_sha256": "4" * 64,
            "page_evidence_sha256": {
                identifier: "5" * 64
                for identifier in publication.SEO_INVENTORY_IDENTIFIERS
            },
            "surface_evidence_sha256": {
                name: "6" * 64 for name in publication.SEO_SURFACE_CHECKS
            },
            "index_state_basis": "UNAVAILABLE",
        },
    )
    monkeypatch.setattr(
        publication,
        "strict_local_quality_audit",
        lambda *_args, **_kwargs: _test_quality_audit_binding(),
    )


class _PublicResponse:
    def __init__(
        self,
        url: str,
        payload: str | bytes,
        *,
        headers: dict[str, str] | None = None,
        status: int = 200,
        final_url: str | None = None,
    ) -> None:
        self._url = url
        self._final_url = final_url or url
        self._payload = payload.encode("utf-8") if isinstance(payload, str) else payload
        self._status = status
        self.headers = {
            "Content-Type": "text/html; charset=UTF-8",
            **(headers or {}),
        }

    def __enter__(self) -> _PublicResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def getcode(self) -> int:
        return self._status

    def geturl(self) -> str:
        return self._final_url

    def read(self, maximum: int) -> bytes:
        return self._payload[:maximum]


class _PublicOpener:
    def __init__(
        self,
        response: _PublicResponse,
        *,
        stylesheet_responses: dict[str, _PublicResponse] | None = None,
    ) -> None:
        self.response = response
        self.stylesheet_responses = stylesheet_responses or {}
        self.requests: list[object] = []

    def open(self, request: object, timeout: int) -> _PublicResponse:
        assert timeout == 30
        self.requests.append(request)
        url = request.full_url
        if url == self.response._url:
            return self.response
        explicit = self.stylesheet_responses.get(url)
        if explicit is not None:
            return explicit
        parsed = publication.urlsplit(url)
        if parsed.path.endswith("/assets/theme.css"):
            asset = "assets/theme.css"
        elif parsed.path.endswith("/assets/editorial-v2.css"):
            asset = "assets/editorial-v2.css"
        elif parsed.path.startswith(publication.AUTOPTIMIZE_SINGLE_STYLESHEET_PREFIX):
            asset = (
                "assets/theme.css"
                if f"_{'a' * 32}.php" in parsed.path
                else "assets/editorial-v2.css"
            )
        else:
            raise AssertionError(f"unexpected public request: {url}")
        property_name = publication.THEME_RUNTIME_SENTINEL_PROPERTIES[asset]
        return _PublicResponse(
            url,
            ":root{"
            + property_name
            + ":"
            + publication.EXPECTED_THEME_RUNTIME_REVISION
            + ";}",
            headers={"Content-Type": "text/css; charset=UTF-8"},
        )


def _materialized_block_markup(article: Any, block_markup: str | None = None) -> str:
    body_markup = article.block_markup if block_markup is None else block_markup
    if article.post_type != "post":
        return body_markup

    def verified_product_image(match: re.Match[str]) -> str:
        opening = match.group(1)
        product_match = re.search(
            r'data-raos-product-image-id=["\']([^"\']+)["\']',
            opening,
        )
        assert product_match is not None
        product_id = product_match.group(1)
        return (
            '<img src="https://thumbnail.image.rakuten.co.jp/@0_mall/'
            f'test/cabinet/{product_id.casefold()}.jpg?_ex=128x128" '
            f'alt="{product_id}の商品画像" width="128" height="128" '
            'loading="lazy" '
            f'data-raos-product-image-id="{product_id}" '
            'data-raos-product-image-placement="product_card" '
            'data-raos-product-image-state="verified">'
        )

    return re.sub(
        r'(<(?P<tag>p|span)\b(?=[^>]*data-raos-product-image-id=["\']'
        r'[^"\']+["\'])(?=[^>]*data-raos-product-image-placement=["\']'
        r'product_card["\'])[^>]*>).*?</(?P=tag)>',
        verified_product_image,
        body_markup,
        flags=re.IGNORECASE | re.DOTALL,
    )


def _materialized_article(article: Any) -> Any:
    return replace(article, block_markup=_materialized_block_markup(article))


def _public_markup(
    article: Any,
    *,
    head_extra: str = "",
    block_markup: str | None = None,
    schema_types: list[str] | None = None,
    stylesheets: str | None = None,
    footer_markup: str = "<footer><h2>暮らしのしるべ</h2></footer>",
) -> str:
    url = f"{publication.ORIGIN}/{article.production_slug}/"
    social_image = publication.expected_social_image_url(article)
    required_schema_types = schema_types or (
        ["Article", "BreadcrumbList", "Organization", "WebSite"]
        if article.post_type == "post"
        else ["BreadcrumbList", "Organization", "WebSite"]
    )
    structured_data = json.dumps(
        {
            "@context": "https://schema.org",
            "@graph": [{"@type": value} for value in required_schema_types],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    excerpt = html.escape(article.excerpt, quote=True)
    title = html.escape(article.title, quote=True)
    seo_head = (
        f'<meta name="description" content="{excerpt}">'
        f'<meta property="og:title" content="{title}">'
        f'<meta property="og:description" content="{excerpt}">'
        f'<meta property="og:url" content="{url}">'
        f'<meta property="og:image" content="{social_image}">'
        '<script id="raos-structured-data" type="application/ld+json">'
        + structured_data
        + "</script>"
    )
    stylesheet_markup = stylesheets
    if stylesheet_markup is None:
        stylesheet_markup = (
            '<link rel="stylesheet" href="/wp-content/themes/'
            "kurashinoshirube-child/assets/theme.css?ver="
            f'{publication.EXPECTED_THEME_RUNTIME_REVISION}">'
        )
        if article.post_type == "post":
            stylesheet_markup += (
                '<link rel="stylesheet" href="/wp-content/themes/'
                "kurashinoshirube-child/assets/editorial-v2.css?ver="
                f'{publication.EXPECTED_THEME_RUNTIME_REVISION}">'
            )
    body_markup = _materialized_block_markup(article, block_markup)
    return (
        "<!doctype html><html><head><title>"
        + article.title
        + " | 暮らしのしるべ</title>"
        + stylesheet_markup
        + '<link rel="canonical" href="'
        + url
        + '">'
        + seo_head
        + head_extra
        + "</head><body><main><h1>"
        + article.title
        + "</h1>"
        + body_markup
        + "</main>"
        + footer_markup
        + "</body></html>"
    )


def _stylesheet_links(*hrefs: str) -> str:
    return "".join(
        f'<link rel="stylesheet" href="{href.replace("&", "&amp;")}">' for href in hrefs
    )


def test_anonymous_public_readback_requires_exact_canonical_title_and_headings() -> (
    None
):
    article = _materialized_article(
        publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    )
    url = f"{publication.ORIGIN}/{article.production_slug}/"
    markup = _public_markup(article)
    opener = _PublicOpener(_PublicResponse(url, markup))

    evidence = ORIGINAL_VERIFY_PUBLIC_PAGES(
        [article],
        attempts=1,
        sleeper=lambda seconds: None,
        opener=opener,
    )

    assert evidence[article.production_slug]["canonical_url"] == url
    assert evidence[article.production_slug]["heading_count"] >= 1
    assert evidence[article.production_slug]["meta_description"] == article.excerpt
    assert evidence[article.production_slug]["open_graph"] == {
        "og:description": article.excerpt,
        "og:image": publication.expected_social_image_url(article),
        "og:title": article.title,
        "og:url": url,
    }
    assert set(evidence[article.production_slug]["json_ld_types"]) >= {
        "Article",
        "BreadcrumbList",
        "Organization",
        "WebSite",
    }
    request = opener.requests[0]
    assert request.full_url == url
    assert request.get_header("Authorization") is None


def test_article_public_readback_accepts_one_exact_trailing_related_heading() -> None:
    article = _materialized_article(
        publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    )
    url = f"{publication.ORIGIN}/{article.production_slug}/"
    footer_markup = (
        '<aside class="related-posts"><h2>関連記事</h2></aside>'
        "<footer><h2>暮らしのしるべ</h2></footer>"
    )

    evidence = ORIGINAL_VERIFY_PUBLIC_PAGES(
        [article],
        attempts=1,
        sleeper=lambda seconds: None,
        opener=_PublicOpener(
            _PublicResponse(
                url,
                _public_markup(article, footer_markup=footer_markup),
            )
        ),
    )

    assert evidence[article.production_slug]["url"] == url


def test_policy_public_readback_rejects_related_heading_injection() -> None:
    page = publication.load_policy_pages()[0]
    url = f"{publication.ORIGIN}/{page.production_slug}/"
    footer_markup = (
        '<aside class="related-posts"><h2>関連記事</h2></aside>'
        "<footer><h2>暮らしのしるべ</h2></footer>"
    )

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLIC_READBACK_FAILED",
    ):
        ORIGINAL_VERIFY_PUBLIC_PAGES(
            [page],
            attempts=1,
            sleeper=lambda seconds: None,
            opener=_PublicOpener(
                _PublicResponse(
                    url,
                    _public_markup(page, footer_markup=footer_markup),
                )
            ),
        )


@pytest.mark.parametrize(
    ("article", "footer_markup"),
    [
        (
            publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0],
            "<aside><h2>関連記事<h2>関連記事</h2></h2></aside>"
            "<footer><h2>暮らしのしるべ</h2></footer>",
        ),
        (
            publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0],
            "<aside><h2>関連記事<h3>追加見出し</h3></h2></aside>"
            "<footer><h2>暮らしのしるべ</h2></footer>",
        ),
        (
            publication.load_policy_pages()[0],
            "<aside><h2>関連記事<h2>暮らしのしるべ</h2></h2></aside>",
        ),
        (
            publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0],
            "<footer><h2>暮らしのしるべ</h2></footer><aside><h2>関連記事",
        ),
        (
            publication.load_policy_pages()[0],
            "<footer><h2>暮らしのしるべ</h2></footer><aside><h2>関連記事",
        ),
        (
            publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0],
            '<aside><h2>関連記事</h2><h3 aria-label="追加見出し"></h3></aside>'
            "<footer><h2>暮らしのしるべ</h2></footer>",
        ),
        (
            publication.load_policy_pages()[0],
            '<aside><h2 aria-label="関連記事"></h2></aside>'
            "<footer><h2>暮らしのしるべ</h2></footer>",
        ),
    ],
    ids=(
        "article-nested-duplicate-related",
        "article-nested-arbitrary-heading",
        "policy-nested-related-around-footer",
        "article-unclosed-related-after-footer",
        "policy-unclosed-related-after-footer",
        "article-accessible-empty-heading-between-related-and-footer",
        "policy-accessible-empty-related-heading",
    ),
)
def test_public_readback_rejects_nested_heading_bypasses(
    article: Any,
    footer_markup: str,
) -> None:
    url = f"{publication.ORIGIN}/{article.production_slug}/"

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLIC_HTML_INVALID",
    ):
        ORIGINAL_VERIFY_PUBLIC_PAGES(
            [article],
            attempts=1,
            sleeper=lambda seconds: None,
            opener=_PublicOpener(
                _PublicResponse(
                    url,
                    _public_markup(article, footer_markup=footer_markup),
                )
            ),
        )


def test_public_head_uses_verified_brand_art_not_invented_product_photos() -> None:
    articles = publication.load_articles("all")
    assert len(publication.EXPECTED_ARTICLE_SOCIAL_IMAGE_BY_SLUG) == 10
    assert set(publication.EXPECTED_ARTICLE_SOCIAL_IMAGE_BY_SLUG.values()) == {
        "home-hero.webp"
    }
    assert {article.production_slug for article in articles} == set(
        publication.EXPECTED_ARTICLE_SOCIAL_IMAGE_BY_SLUG
    )
    urls = {publication.expected_social_image_url(article) for article in articles}
    assert urls == {publication.EXPECTED_SOCIAL_IMAGE_URL}
    assert urls == {
        f"{publication.ORIGIN}/wp-content/themes/kurashinoshirube-child/"
        f"assets/images/{name}"
        for name in publication.EXPECTED_ARTICLE_SOCIAL_IMAGE_BY_SLUG.values()
    }
    for page in publication.load_policy_pages():
        assert publication.expected_social_image_url(page) == (
            publication.EXPECTED_SOCIAL_IMAGE_URL
        )


@pytest.mark.parametrize(
    "stylesheets",
    [
        _stylesheet_links(
            "https://example.invalid/unrelated.css?build=42",
            f"{publication.ORIGIN}/wp-content/themes/kurashinoshirube-child/"
            f"assets/theme.css?ver={THEME_REVISION}",
            f"{publication.ORIGIN}/wp-content/themes/kurashinoshirube-child/"
            f"assets/editorial-v2.css?ver={THEME_REVISION}",
        ),
        _stylesheet_links(
            "https://example.invalid/unrelated.css?build=42",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'a' * 32}.php?ver={THEME_REVISION}",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'b' * 32}.php?ver={THEME_REVISION}",
        ),
        _stylesheet_links(
            "https://example.invalid/unrelated.css?build=42",
            "/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'a' * 32}.php?ver={THEME_REVISION}",
            "/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'b' * 32}.php?ver={THEME_REVISION}",
        ),
    ],
    ids=(
        "absolute-direct-theme-assets",
        "autoptimize-single-assets",
        "root-relative-autoptimize-single-assets",
    ),
)
def test_public_readback_accepts_exact_theme_stylesheet_materializations(
    stylesheets: str,
) -> None:
    article = _materialized_article(
        publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    )
    url = f"{publication.ORIGIN}/{article.production_slug}/"

    evidence = ORIGINAL_VERIFY_PUBLIC_PAGES(
        [article],
        attempts=1,
        sleeper=lambda seconds: None,
        opener=_PublicOpener(
            _PublicResponse(url, _public_markup(article, stylesheets=stylesheets))
        ),
    )

    page = evidence[article.production_slug]
    assert page["theme_version"] == "1.5.1"
    assert page["theme_runtime_revision"] == (
        publication.EXPECTED_THEME_RUNTIME_REVISION
    )
    stylesheet_evidence = page["theme_stylesheets"]
    assert [row["asset"] for row in stylesheet_evidence] == [
        "assets/editorial-v2.css",
        "assets/theme.css",
    ]
    assert all(
        publication.SHA256_RE.fullmatch(row["content_sha256"])
        and row["bytes"] > 0
        and row["runtime_revision"] == publication.EXPECTED_THEME_RUNTIME_REVISION
        for row in stylesheet_evidence
    )


def _runtime_css(asset: str, *, revision: str | None = None) -> str:
    return (
        ":root{"
        + publication.THEME_RUNTIME_SENTINEL_PROPERTIES[asset]
        + ":"
        + (revision or publication.EXPECTED_THEME_RUNTIME_REVISION)
        + ";}"
    )


@pytest.mark.parametrize(
    ("payload", "headers", "status", "final_url"),
    [
        (_runtime_css("assets/theme.css"), {"Content-Type": "text/css"}, 503, None),
        (
            _runtime_css("assets/theme.css"),
            {"Content-Type": "application/javascript"},
            200,
            None,
        ),
        (
            _runtime_css("assets/theme.css"),
            {"Content-Type": "text/css"},
            200,
            "redirect",
        ),
        (b"", {"Content-Type": "text/css"}, 200, None),
        (b"\xff", {"Content-Type": "text/css"}, 200, None),
        (
            b"a" * (publication.MAX_PUBLIC_STYLESHEET_BYTES + 1),
            {"Content-Type": "text/css"},
            200,
            None,
        ),
        (
            _runtime_css("assets/theme.css", revision="0" * 64),
            {"Content-Type": "text/css"},
            200,
            None,
        ),
        (
            _runtime_css("assets/theme.css") * 2,
            {"Content-Type": "text/css"},
            200,
            None,
        ),
        (
            _runtime_css("assets/theme.css") + _runtime_css("assets/editorial-v2.css"),
            {"Content-Type": "text/css"},
            200,
            None,
        ),
        (
            _runtime_css("assets/editorial-v2.css"),
            {"Content-Type": "text/css"},
            200,
            None,
        ),
    ],
    ids=(
        "wrong-status",
        "wrong-content-type",
        "redirected",
        "empty",
        "invalid-utf8",
        "oversize",
        "stale-revision",
        "duplicate-sentinel",
        "combined-sentinels",
        "wrong-direct-asset",
    ),
)
def test_public_readback_rejects_invalid_fetched_stylesheet_evidence(
    payload: str | bytes,
    headers: dict[str, str],
    status: int,
    final_url: str | None,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    page_url = f"{publication.ORIGIN}/{article.production_slug}/"
    stylesheet_url = (
        f"{publication.ORIGIN}/wp-content/themes/kurashinoshirube-child/"
        f"assets/theme.css?ver={THEME_REVISION}"
    )
    response_final_url = (
        f"{publication.ORIGIN}/redirected.css"
        if final_url == "redirect"
        else stylesheet_url
    )
    opener = _PublicOpener(
        _PublicResponse(page_url, _public_markup(article)),
        stylesheet_responses={
            stylesheet_url: _PublicResponse(
                stylesheet_url,
                payload,
                headers=headers,
                status=status,
                final_url=response_final_url,
            )
        },
    )

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLIC_STYLESHEET_INVALID",
    ):
        ORIGINAL_VERIFY_PUBLIC_PAGES(
            [article],
            attempts=1,
            sleeper=lambda seconds: None,
            opener=opener,
        )


def test_public_stylesheet_fetch_is_cached_once_per_url_per_readback() -> None:
    article = _materialized_article(
        publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    )
    page_url = f"{publication.ORIGIN}/{article.production_slug}/"
    opener = _PublicOpener(_PublicResponse(page_url, _public_markup(article)))

    ORIGINAL_VERIFY_PUBLIC_PAGES(
        [article, article],
        attempts=1,
        sleeper=lambda seconds: None,
        opener=opener,
    )

    requested_urls = [request.full_url for request in opener.requests]
    assert requested_urls.count(page_url) == 2
    assert len(requested_urls) == 4
    assert len(set(requested_urls) - {page_url}) == 2


@pytest.mark.parametrize(
    "footer_markup",
    [
        "",
        "<footer><h3>暮らしのしるべ</h3></footer>",
        "<footer><h2>別のサイト名</h2></footer>",
        "<footer><h2>暮らしのしるべ</h2><h2>暮らしのしるべ</h2></footer>",
        "<footer><h2>暮らしのしるべ</h2><h3>追加見出し</h3></footer>",
        "<footer><h3>追加見出し</h3><h2>暮らしのしるべ</h2></footer>",
        "<aside><h3>関連記事</h3></aside><footer><h2>暮らしのしるべ</h2></footer>",
        "<aside><h2>関連する記事</h2></aside><footer><h2>暮らしのしるべ</h2></footer>",
        "<aside><h2>関連記事</h2><h2>関連記事</h2></aside>"
        "<footer><h2>暮らしのしるべ</h2></footer>",
        "<footer><h2>暮らしのしるべ</h2></footer><aside><h2>関連記事</h2></aside>",
        "<aside><h2>追加見出し</h2><h2>関連記事</h2></aside>"
        "<footer><h2>暮らしのしるべ</h2></footer>",
    ],
    ids=(
        "missing",
        "wrong-level",
        "wrong-copy",
        "duplicate",
        "not-trailing",
        "extra-before-footer",
        "related-wrong-level",
        "related-wrong-copy",
        "related-duplicate",
        "related-after-footer",
        "arbitrary-before-related",
    ),
)
def test_public_readback_requires_one_exact_trailing_site_footer_heading(
    footer_markup: str,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    url = f"{publication.ORIGIN}/{article.production_slug}/"

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLIC_READBACK_FAILED",
    ):
        ORIGINAL_VERIFY_PUBLIC_PAGES(
            [article],
            attempts=1,
            sleeper=lambda seconds: None,
            opener=_PublicOpener(
                _PublicResponse(
                    url,
                    _public_markup(article, footer_markup=footer_markup),
                )
            ),
        )


@pytest.mark.parametrize(
    "stylesheets",
    [
        _stylesheet_links(
            f"/wp-content/themes/kurashinoshirube-child/assets/theme.css?ver={THEME_REVISION}",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'a' * 32}.php?ver={THEME_REVISION}",
        ),
        _stylesheet_links(
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'a' * 32}.php?ver={THEME_REVISION}",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'a' * 32}.php?ver={THEME_REVISION}",
        ),
        _stylesheet_links(
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'A' * 32}.php?ver={THEME_REVISION}",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'b' * 32}.php?ver={THEME_REVISION}",
        ),
        _stylesheet_links(
            "http://kurashinoshirube.com/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'a' * 32}.php?ver={THEME_REVISION}",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'b' * 32}.php?ver={THEME_REVISION}",
        ),
        _stylesheet_links(
            "https://user@kurashinoshirube.com/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'a' * 32}.php?ver={THEME_REVISION}",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'b' * 32}.php?ver={THEME_REVISION}",
        ),
        _stylesheet_links(
            "https://kurashinoshirube.com:443/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'a' * 32}.php?ver={THEME_REVISION}",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'b' * 32}.php?ver={THEME_REVISION}",
        ),
        _stylesheet_links(
            "https://example.invalid/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'a' * 32}.php?ver={THEME_REVISION}",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'b' * 32}.php?ver={THEME_REVISION}",
        ),
        _stylesheet_links(
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'a' * 32}.php?ver={THEME_REVISION}#fragment",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'b' * 32}.php?ver={THEME_REVISION}",
        ),
        _stylesheet_links(
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'a' * 32}.php?ver={THEME_REVISION}&extra=1",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'b' * 32}.php?ver={THEME_REVISION}",
        ),
        _stylesheet_links(
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'a' * 32}.php?ver={THEME_REVISION}",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'b' * 32}.php?ver={THEME_REVISION}",
            f"{publication.ORIGIN}/wp-content/cache/autoptimize/"
            f"autoptimize_single_{'c' * 32}.php?ver={THEME_REVISION}",
        ),
        _stylesheet_links(
            f"/wp-content/themes/kurashinoshirube-child/assets/theme.css?ver={THEME_REVISION}&extra=1",
            f"/wp-content/themes/kurashinoshirube-child/assets/editorial-v2.css?ver={THEME_REVISION}",
        ),
    ],
    ids=(
        "mixed-direct-and-autoptimize",
        "duplicate-autoptimize-hash",
        "uppercase-autoptimize-hash",
        "http-autoptimize-url",
        "userinfo-autoptimize-url",
        "port-autoptimize-url",
        "cross-origin-autoptimize-url",
        "fragment-autoptimize-url",
        "extra-query-autoptimize-url",
        "third-autoptimize-url",
        "extra-query-direct-url",
    ),
)
def test_public_readback_rejects_invalid_theme_stylesheet_materialization(
    stylesheets: str,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    url = f"{publication.ORIGIN}/{article.production_slug}/"

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLIC_READBACK_FAILED",
    ):
        ORIGINAL_VERIFY_PUBLIC_PAGES(
            [article],
            attempts=1,
            sleeper=lambda seconds: None,
            opener=_PublicOpener(
                _PublicResponse(url, _public_markup(article, stylesheets=stylesheets))
            ),
        )


def test_anonymous_public_readback_rejects_noindex() -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    url = f"{publication.ORIGIN}/{article.production_slug}/"
    markup = _public_markup(
        article,
        head_extra='<meta name="robots" content="noindex, follow">',
    )
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLIC_READBACK_FAILED",
    ):
        ORIGINAL_VERIFY_PUBLIC_PAGES(
            [article],
            attempts=1,
            sleeper=lambda seconds: None,
            opener=_PublicOpener(_PublicResponse(url, markup)),
        )


@pytest.mark.parametrize(
    "tamper",
    [
        lambda markup, article, url: markup.replace(
            f'<meta name="description" content="{html.escape(article.excerpt, quote=True)}">',
            "",
        ),
        lambda markup, article, url: markup.replace(
            html.escape(article.excerpt, quote=True),
            "wrong-description",
            1,
        ),
        lambda markup, article, url: markup.replace(
            f'<meta property="og:title" content="{html.escape(article.title, quote=True)}">',
            '<meta property="og:title" content="wrong-title">',
        ),
        lambda markup, article, url: markup.replace(
            f'<meta property="og:description" content="{html.escape(article.excerpt, quote=True)}">',
            '<meta property="og:description" content="wrong-description">',
        ),
        lambda markup, article, url: markup.replace(
            f'<meta property="og:url" content="{url}">',
            '<meta property="og:url" content="https://example.invalid/wrong/">',
        ),
        lambda markup, article, url: markup.replace(
            publication.expected_social_image_url(article),
            "http://kurashinoshirube.com/wp-content/themes/"
            "kurashinoshirube-child/assets/images/home-hero.webp",
        ),
        lambda markup, article, url: markup.replace(
            publication.expected_social_image_url(article),
            "https://example.invalid/home-hero.webp",
        ),
        lambda markup, article, url: markup.replace(
            publication.expected_social_image_url(article),
            f"{publication.ORIGIN}/wp-content/themes/"
            "kurashinoshirube-child/assets/images/other.webp",
        ),
        lambda markup, article, url: markup.replace(
            "</head>",
            f'<meta name="description" content="{html.escape(article.excerpt, quote=True)}">'
            "</head>",
        ),
    ],
    ids=(
        "missing-meta-description",
        "description-not-tracked-excerpt",
        "og-title-drift",
        "og-description-drift",
        "og-url-drift",
        "og-image-not-https",
        "og-image-cross-origin",
        "og-image-not-default-theme-image",
        "duplicate-meta-description",
    ),
)
def test_public_readback_rejects_meta_and_open_graph_drift(tamper: Any) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    url = f"{publication.ORIGIN}/{article.production_slug}/"
    markup = tamper(_public_markup(article), article, url)
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLIC_HEAD_INVALID",
    ):
        ORIGINAL_VERIFY_PUBLIC_PAGES(
            [article],
            attempts=1,
            sleeper=lambda seconds: None,
            opener=_PublicOpener(_PublicResponse(url, markup)),
        )


@pytest.mark.parametrize(
    "missing_type",
    ["Article", "BreadcrumbList", "Organization", "WebSite"],
)
def test_article_public_readback_requires_each_json_ld_type(
    missing_type: str,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    url = f"{publication.ORIGIN}/{article.production_slug}/"
    types = [
        value
        for value in ["Article", "BreadcrumbList", "Organization", "WebSite"]
        if value != missing_type
    ]
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLIC_JSON_LD_INVALID",
    ):
        ORIGINAL_VERIFY_PUBLIC_PAGES(
            [article],
            attempts=1,
            sleeper=lambda seconds: None,
            opener=_PublicOpener(
                _PublicResponse(url, _public_markup(article, schema_types=types))
            ),
        )


@pytest.mark.parametrize("forbidden_type", ["Product", "Offer", "Review", "FAQPage"])
def test_public_readback_rejects_forbidden_commercial_json_ld(
    forbidden_type: str,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    url = f"{publication.ORIGIN}/{article.production_slug}/"
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLIC_JSON_LD_INVALID",
    ):
        ORIGINAL_VERIFY_PUBLIC_PAGES(
            [article],
            attempts=1,
            sleeper=lambda seconds: None,
            opener=_PublicOpener(
                _PublicResponse(
                    url,
                    _public_markup(
                        article,
                        schema_types=[
                            "Article",
                            "BreadcrumbList",
                            "Organization",
                            "WebSite",
                            f"https://schema.org/{forbidden_type}",
                        ],
                    ),
                )
            ),
        )


def test_policy_page_json_ld_requires_page_graph_and_refuses_article_type() -> None:
    page = publication.load_policy_pages()[0]
    url = f"{publication.ORIGIN}/{page.production_slug}/"
    markup = _public_markup(page)
    assert "editorial-v2.css" not in markup
    evidence = ORIGINAL_VERIFY_PUBLIC_PAGES(
        [page],
        attempts=1,
        sleeper=lambda seconds: None,
        opener=_PublicOpener(_PublicResponse(url, markup)),
    )
    assert set(evidence[page.production_slug]["json_ld_types"]) == {
        "BreadcrumbList",
        "Organization",
        "WebSite",
    }
    for invalid_types in (
        ["BreadcrumbList", "Organization"],
        ["Article", "BreadcrumbList", "Organization", "WebSite"],
    ):
        with pytest.raises(
            publication.PublicationFailure,
            match="RAOS_WORDPRESS_REQUEST_PUBLIC_JSON_LD_INVALID",
        ):
            ORIGINAL_VERIFY_PUBLIC_PAGES(
                [page],
                attempts=1,
                sleeper=lambda seconds: None,
                opener=_PublicOpener(
                    _PublicResponse(
                        url,
                        _public_markup(page, schema_types=invalid_types),
                    )
                ),
            )


@pytest.mark.parametrize(
    ("meta_content", "response_headers"),
    [
        ("follow noindex noarchive", {}),
        ("follow; NONE", {}),
        (None, {"x-robots-tag": "googlebot: noindex, follow"}),
        (None, {"X-Robots-Tag": "none"}),
    ],
)
def test_anonymous_public_readback_rejects_all_noindex_marker_forms(
    meta_content: str | None,
    response_headers: dict[str, str],
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    url = f"{publication.ORIGIN}/{article.production_slug}/"
    meta = f'<meta name="robots" content="{meta_content}">' if meta_content else ""
    markup = _public_markup(article, head_extra=meta)
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLIC_READBACK_FAILED",
    ):
        ORIGINAL_VERIFY_PUBLIC_PAGES(
            [article],
            attempts=1,
            sleeper=lambda seconds: None,
            opener=_PublicOpener(
                _PublicResponse(url, markup, headers=response_headers)
            ),
        )


def test_anonymous_public_readback_rejects_googlebot_noindex_meta() -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    url = f"{publication.ORIGIN}/{article.production_slug}/"
    markup = _public_markup(
        article,
        head_extra='<meta name="googlebot" content="follow noindex">',
    )
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLIC_READBACK_FAILED",
    ):
        ORIGINAL_VERIFY_PUBLIC_PAGES(
            [article],
            attempts=1,
            sleeper=lambda seconds: None,
            opener=_PublicOpener(_PublicResponse(url, markup)),
        )


def test_anonymous_public_readback_rejects_cta_identity_or_theme_drift() -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    url = f"{publication.ORIGIN}/{article.production_slug}/"
    tampered_cta, replacements = re.subn(
        r'(<a\b[^>]*href=")[^"]+("[^>]*data-raos-placement=)',
        r"\1https://example.invalid/wrong-product\2",
        article.block_markup,
        count=1,
    )
    assert replacements == 1
    with pytest.raises(
        publication.PublicationFailure,
        match=(
            "RAOS_WORDPRESS_REQUEST_PUBLIC_"
            "(CTA_INVALID|PRODUCT_IMAGE_INVALID|READBACK_FAILED)"
        ),
    ):
        ORIGINAL_VERIFY_PUBLIC_PAGES(
            [article],
            attempts=1,
            sleeper=lambda seconds: None,
            opener=_PublicOpener(
                _PublicResponse(url, _public_markup(article, block_markup=tampered_cta))
            ),
        )

    wrong_theme = _public_markup(article).replace(
        f"?ver={publication.EXPECTED_THEME_RUNTIME_REVISION}",
        "?ver=1.3.8",
    )
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLIC_READBACK_FAILED",
    ):
        ORIGINAL_VERIFY_PUBLIC_PAGES(
            [article],
            attempts=1,
            sleeper=lambda seconds: None,
            opener=_PublicOpener(_PublicResponse(url, wrong_theme)),
        )


def test_authenticated_public_readback_sends_only_the_supplied_basic_header() -> None:
    article = _materialized_article(
        publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    )
    url = f"{publication.ORIGIN}/{article.production_slug}/"
    opener = _PublicOpener(_PublicResponse(url, _public_markup(article)))

    ORIGINAL_VERIFY_PUBLIC_PAGES(
        [article],
        attempts=1,
        sleeper=lambda seconds: None,
        opener=opener,
        authorization="Basic dXNlcjpwYXNz",
    )

    request = opener.requests[0]
    assert request.get_header("Authorization") == "Basic dXNlcjpwYXNz"


def test_policy_page_public_readback_checks_policy_content_and_private_absence() -> (
    None
):
    page = publication.load_policy_pages()[2]
    url = f"{publication.ORIGIN}/{page.production_slug}/"
    evidence = ORIGINAL_VERIFY_PUBLIC_PAGES(
        [page],
        attempts=1,
        sleeper=lambda seconds: None,
        opener=_PublicOpener(_PublicResponse(url, _public_markup(page))),
    )

    assert evidence[page.production_slug]["post_type"] == "page"
    assert evidence[page.production_slug]["h1"] == page.title
    assert evidence[page.production_slug]["private_financial_data_absent"] is True

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLIC_READBACK_FAILED",
    ):
        ORIGINAL_VERIFY_PUBLIC_PAGES(
            [page],
            attempts=1,
            sleeper=lambda seconds: None,
            opener=_PublicOpener(
                _PublicResponse(
                    url,
                    _public_markup(
                        page,
                        block_markup=page.block_markup
                        + "<p>owner_hourly_rate=1234</p>",
                    ),
                )
            ),
        )


@pytest.mark.parametrize(
    "tamper",
    [
        lambda article: article.block_markup.replace("<h2", "<h3", 1).replace(
            "</h2>", "</h3>", 1
        ),
        lambda article: f"<h1>{article.title}</h1>{article.block_markup}",
        lambda article: (
            article.block_markup
            + '<a href="https://hb.afl.rakuten.co.jp/ichiba/00000000.00000000.00000000/">hidden affiliate</a>'
        ),
        lambda article: article.block_markup.replace(
            "広告を含みます", "広告リンクがあります", 1
        ),
        lambda article: article.block_markup.replace(
            "商品画像未確認・購入導線停止",
            '<img src="https://example.invalid/product-image-drift.webp" '
            'alt="未検証の商品画像" width="128" height="128">',
            1,
        ),
    ],
    ids=(
        "heading-level-demotion",
        "duplicate-h1",
        "unattributed-affiliate-link",
        "disclosure-copy-drift",
        "product-image-drift",
    ),
)
def test_public_readback_rejects_semantic_or_commercial_drift(
    tamper: Any,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    url = f"{publication.ORIGIN}/{article.production_slug}/"
    with pytest.raises(
        publication.PublicationFailure,
        match=(
            "RAOS_WORDPRESS_REQUEST_PUBLIC_"
            "(CTA_INVALID|PRODUCT_IMAGE_INVALID|READBACK_FAILED)"
        ),
    ):
        ORIGINAL_VERIFY_PUBLIC_PAGES(
            [article],
            attempts=1,
            sleeper=lambda seconds: None,
            opener=_PublicOpener(
                _PublicResponse(
                    url,
                    _public_markup(article, block_markup=tamper(article)),
                )
            ),
        )


def test_mapping_is_closed_numeric_and_exact_slug_conversion() -> None:
    mapping = json.loads(
        (
            ROOT / "changes/wordpress-local-preview-v1/production-mapping.v1.json"
        ).read_text(encoding="utf-8")
    )
    articles = publication.load_articles("all")

    assert mapping["origin"] == publication.ORIGIN
    assert mapping["editor_endpoint"] == publication.EDITOR_ENDPOINT
    assert mapping["review_url"] == publication.REVIEW_URL
    assert len(articles) == 10
    pages = publication.load_policy_pages()
    assert [(page.production_slug, page.document()["post_type"]) for page in pages] == [
        ("about-ad-policy", "page"),
        ("comparison-policy", "page"),
        ("privacy-policy", "page"),
    ]
    assert all(
        isinstance(page.document()["excerpt"], str)
        and page.document()["excerpt"]
        and page.document()["taxonomies"] == {}
        and page.document()["media_ids"] == []
        for page in pages
    )
    assert [page.excerpt for page in pages] == [
        "暮らしのしるべの情報源、型番照合、広告との分離、更新・訂正と現在の問い合わせ窓口の扱いを説明します。",
        "暮らしのしるべの比較対象・除外、根拠の扱い、掲載順、販売条件、利益相反、更新・訂正の方針を説明します。",
        "ローカルプレビューにおける計測送信、Cookie、第三者送信、権利請求、安全管理、変更履歴の扱いを説明します。",
    ]
    for row in mapping["articles"]:
        assert row["production_slug"] == row["local_slug"].removeprefix(
            "local-preview-"
        )
        assert row["taxonomies"] == {
            "category": [5],
            "post_format": [],
            "post_tag": [],
        }
        assert all(type(term_id) is int for term_id in row["taxonomies"]["category"])


def test_publication_uses_production_policy_profile_not_local_preview_copy() -> None:
    local_pages = publication.load_policy_pages(profile="local")
    production_pages = publication.load_policy_pages(profile="production")
    assert [page.production_slug for page in production_pages] == [
        "about-ad-policy",
        "comparison-policy",
        "privacy-policy",
    ]
    assert all(
        production.block_markup != local.block_markup
        for production, local in zip(production_pages, local_pages, strict=True)
    )
    assert all(
        "ローカルWordPressプレビュー" not in page.block_markup
        and "このローカルプレビュー" not in page.block_markup
        and "contact@kurashinoshirube.com" in page.block_markup
        for page in production_pages
    )
    all_items = publication.load_publication_items("all")
    assert all_items[-3:] == production_pages
    local_privacy = next(
        page for page in local_pages if page.production_slug == "privacy-policy"
    )
    assert "閲覧行動データを保存していません" in local_privacy.block_markup
    assert "個別の生イベントは7日" not in local_privacy.block_markup
    assert "13か月" not in local_privacy.block_markup


def test_production_policy_profile_rejects_local_only_copy_injection(
    tmp_path: Path,
) -> None:
    fixture_root = tmp_path / "fixtures"
    shutil.copytree(publication.SOURCE_FIXTURE_ROOT, fixture_root)
    privacy = fixture_root / "production-pages/privacy-policy.html"
    privacy.write_text(
        privacy.read_text(encoding="utf-8")
        + "<p>このローカルプレビューだけに適用します。</p>",
        encoding="utf-8",
    )

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PAGE_KSES_INVALID",
    ):
        publication.load_policy_pages(
            fixture_root=fixture_root.resolve(),
            profile="production",
        )


def test_tracked_theme_hash_matches_the_bounded_operator_manifest() -> None:
    relative_theme = publication.THEME_ROOT.relative_to(ROOT).as_posix()
    if subprocess.run(
        ("git", "status", "--porcelain=v1", "--", relative_theme),
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout:
        pytest.skip(
            "candidate theme is intentionally dirty in the integration worktree"
        )
    operator_path = ROOT / "scripts/raos_wordpress_deployment_operator.py"
    specification = importlib.util.spec_from_file_location(
        "wordpress_deployment_operator_for_publication_test", operator_path
    )
    assert specification is not None and specification.loader is not None
    operator = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = operator
    specification.loader.exec_module(operator)
    _, descriptor = operator.theme_package()
    assert ORIGINAL_TRACKED_THEME_TREE_SHA256() == descriptor["file_manifest_sha256"]


def test_article_selection_is_exact_production_slug_csv() -> None:
    selected = publication.load_articles(
        "roomba-mini-vs-switchbot-k11-pro,solota-vs-rakua-mini-plus"
    )
    assert [article.production_slug for article in selected] == [
        "roomba-mini-vs-switchbot-k11-pro",
        "solota-vs-rakua-mini-plus",
    ]
    for invalid in (
        "",
        "local-preview-roomba-mini-vs-switchbot-k11-pro",
        "unknown-slug",
        "roomba-mini-vs-switchbot-k11-pro,roomba-mini-vs-switchbot-k11-pro",
        "roomba-mini-vs-switchbot-k11-pro, solota-vs-rakua-mini-plus",
    ):
        with pytest.raises(
            publication.PublicationFailure,
            match="RAOS_WORDPRESS_REQUEST_ARTICLE_SELECTION_INVALID",
        ):
            publication.load_articles(invalid)


def _write_quality_audit_inputs(
    tmp_path: Path,
    *,
    expires_at: str = "2026-08-31T00:15:00Z",
) -> tuple[Path, Path, dict[str, object], bytes, bytes]:
    attestation_path, signature_path = _quality_input_paths(tmp_path)
    payload: dict[str, object] = {
        "reviewer_key_id": "trusted-independent-reviewer-key-001",
        "reviewer_id": "independent-reviewer-bravo",
        "expires_at": expires_at,
    }
    payload_raw = publication.wordpress_quality_audit.canonical_json(payload) + b"\n"
    signature_raw = b"YQ==\n"
    attestation_path.write_bytes(payload_raw)
    signature_path.write_bytes(signature_raw)
    attestation_path.chmod(0o600)
    signature_path.chmod(0o600)
    return attestation_path, signature_path, payload, payload_raw, signature_raw


def test_complete_local_quality_audit_is_hash_bound_before_publication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    attestation_path, signature_path, payload, payload_raw, signature_raw = (
        _write_quality_audit_inputs(tmp_path)
    )
    ledger = {
        "evaluated_at": "2026-08-31T00:00:00Z",
        "completion": {
            "audit_phase": publication.wordpress_quality_audit.PRE_PUBLICATION_PHASE_ID,
            "status": "COMPLETE",
            "completion_state": (
                publication.wordpress_quality_audit.PRE_PUBLICATION_COMPLETION_STATE
            ),
            "production_parity_state": (
                publication.wordpress_quality_audit.POST_APPLY_PENDING_STATE
            ),
            "consecutive_clean_rounds": 2,
        },
        "rounds": [{"round_sha256": "4" * 64}, {"round_sha256": "5" * 64}],
        "repository_fingerprints": {"source": "6" * 64},
    }
    result = SimpleNamespace(
        audit_phase=publication.wordpress_quality_audit.PRE_PUBLICATION_PHASE_ID,
        status="COMPLETE",
        completion_state=(
            publication.wordpress_quality_audit.PRE_PUBLICATION_COMPLETION_STATE
        ),
        production_parity_state=(
            publication.wordpress_quality_audit.POST_APPLY_PENDING_STATE
        ),
        round_count=2,
        consecutive_clean_rounds=2,
        reviewer_attestation_verified=True,
        ledger_sha256="3" * 64,
    )
    monkeypatch.setattr(
        publication.wordpress_quality_audit,
        "load_contract",
        lambda: ({"contract": "validated"}, "1" * 64),
    )
    monkeypatch.setattr(
        publication.wordpress_quality_audit,
        "read_json",
        lambda _path: (ledger, b"sealed-ledger\n"),
    )
    validation_keywords: dict[str, object] = {}

    def validate_document(*_args: object, **kwargs: object) -> object:
        validation_keywords.update(kwargs)
        return result

    monkeypatch.setattr(
        publication.wordpress_quality_audit,
        "validate_document",
        validate_document,
    )
    monkeypatch.setattr(
        publication.wordpress_quality_audit,
        "fingerprint_bundle_sha256",
        lambda _fingerprints: "2" * 64,
    )

    binding = ORIGINAL_STRICT_LOCAL_QUALITY_AUDIT(
        attestation_path,
        signature_path,
    )

    assert binding == {
        "schema": "RAOS_WORDPRESS_QUALITY_AUDIT_BINDING_V3",
        "audit_phase": publication.wordpress_quality_audit.PRE_PUBLICATION_PHASE_ID,
        "status": "COMPLETE",
        "completion_state": (
            publication.wordpress_quality_audit.PRE_PUBLICATION_COMPLETION_STATE
        ),
        "production_parity_state": (
            publication.wordpress_quality_audit.POST_APPLY_PENDING_STATE
        ),
        "evaluated_at": "2026-08-31T00:00:00Z",
        "contract_file_sha256": "1" * 64,
        "ledger_file_sha256": hashlib.sha256(b"sealed-ledger\n").hexdigest(),
        "ledger_sha256": "3" * 64,
        "fingerprint_bundle_sha256": "2" * 64,
        "latest_round_sha256": "5" * 64,
        "round_count": 2,
        "consecutive_clean_rounds": 2,
        "attestation_payload_sha256": hashlib.sha256(payload_raw).hexdigest(),
        "attestation_signature_sha256": hashlib.sha256(signature_raw).hexdigest(),
        "reviewer_key_id": payload["reviewer_key_id"],
        "reviewer_id": payload["reviewer_id"],
        "expires_at": payload["expires_at"],
        "reviewer_attestation_verified": True,
    }
    assert validation_keywords == {
        "attestation_path": attestation_path,
        "attestation_signature_path": signature_path,
    }
    publication._validate_quality_audit_binding(binding)


def test_pre_publication_quality_binding_cannot_claim_post_apply_completion() -> None:
    binding = _test_quality_audit_binding()
    binding["production_parity_state"] = (
        publication.wordpress_quality_audit.POST_APPLY_COMPLETION_STATE
    )
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID",
    ):
        publication._validate_quality_audit_binding(binding)


def test_incomplete_local_quality_audit_fails_closed_before_publication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    attestation_path, signature_path, *_rest = _write_quality_audit_inputs(tmp_path)
    monkeypatch.setattr(
        publication.wordpress_quality_audit,
        "load_contract",
        lambda: ({"contract": "validated"}, "1" * 64),
    )
    monkeypatch.setattr(
        publication.wordpress_quality_audit,
        "read_json",
        lambda _path: (
            {
                "evaluated_at": "2026-08-31T00:00:00Z",
                "completion": {
                    "status": "BLOCKED",
                    "consecutive_clean_rounds": 0,
                },
                "rounds": [{"round_sha256": "4" * 64}],
                "repository_fingerprints": {"source": "6" * 64},
            },
            b"blocked-ledger\n",
        ),
    )
    monkeypatch.setattr(
        publication.wordpress_quality_audit,
        "validate_document",
        lambda *_args, **_kwargs: SimpleNamespace(
            status="BLOCKED",
            round_count=1,
            consecutive_clean_rounds=0,
            reviewer_attestation_verified=True,
            ledger_sha256="3" * 64,
        ),
    )

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_QUALITY_AUDIT_INCOMPLETE",
    ):
        ORIGINAL_STRICT_LOCAL_QUALITY_AUDIT(attestation_path, signature_path)


def test_local_quality_audit_requires_complete_absolute_attestation_pair(
    tmp_path: Path,
) -> None:
    attestation_path, signature_path = _quality_input_paths(tmp_path)
    for attestation, signature, code in (
        (
            None,
            signature_path,
            "RAOS_WORDPRESS_REQUEST_QUALITY_AUDIT_ATTESTATION_REQUIRED",
        ),
        (
            attestation_path,
            None,
            "RAOS_WORDPRESS_REQUEST_QUALITY_AUDIT_ATTESTATION_REQUIRED",
        ),
        (
            Path("attestation.json"),
            signature_path,
            "RAOS_WORDPRESS_REQUEST_QUALITY_AUDIT_ATTESTATION_INVALID",
        ),
    ):
        with pytest.raises(publication.PublicationFailure, match=code):
            ORIGINAL_STRICT_LOCAL_QUALITY_AUDIT(attestation, signature)


def test_local_quality_audit_rejects_attestation_tamper_during_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    attestation_path, signature_path, _payload, _payload_raw, _signature_raw = (
        _write_quality_audit_inputs(tmp_path)
    )
    ledger = {
        "evaluated_at": "2026-08-31T00:00:00Z",
        "completion": {
            "audit_phase": publication.wordpress_quality_audit.PRE_PUBLICATION_PHASE_ID,
            "status": "COMPLETE",
            "completion_state": (
                publication.wordpress_quality_audit.PRE_PUBLICATION_COMPLETION_STATE
            ),
            "production_parity_state": (
                publication.wordpress_quality_audit.POST_APPLY_PENDING_STATE
            ),
            "consecutive_clean_rounds": 2,
        },
        "rounds": [{"round_sha256": "4" * 64}, {"round_sha256": "5" * 64}],
        "repository_fingerprints": {"source": "6" * 64},
    }
    monkeypatch.setattr(
        publication.wordpress_quality_audit,
        "load_contract",
        lambda: ({"contract": "validated"}, "1" * 64),
    )
    monkeypatch.setattr(
        publication.wordpress_quality_audit,
        "read_json",
        lambda _path: (ledger, b"sealed-ledger\n"),
    )
    monkeypatch.setattr(
        publication.wordpress_quality_audit,
        "fingerprint_bundle_sha256",
        lambda _fingerprints: "2" * 64,
    )

    def tamper(*_args: object, **_kwargs: object) -> object:
        changed = {
            "reviewer_key_id": "trusted-independent-reviewer-key-001",
            "reviewer_id": "independent-reviewer-charlie",
            "expires_at": "2026-08-31T00:15:00Z",
        }
        attestation_path.write_bytes(
            publication.wordpress_quality_audit.canonical_json(changed) + b"\n"
        )
        return SimpleNamespace(
            audit_phase=publication.wordpress_quality_audit.PRE_PUBLICATION_PHASE_ID,
            status="COMPLETE",
            completion_state=(
                publication.wordpress_quality_audit.PRE_PUBLICATION_COMPLETION_STATE
            ),
            production_parity_state=(
                publication.wordpress_quality_audit.POST_APPLY_PENDING_STATE
            ),
            round_count=2,
            consecutive_clean_rounds=2,
            reviewer_attestation_verified=True,
            ledger_sha256="3" * 64,
        )

    monkeypatch.setattr(
        publication.wordpress_quality_audit,
        "validate_document",
        tamper,
    )
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_QUALITY_AUDIT_INCOMPLETE",
    ):
        ORIGINAL_STRICT_LOCAL_QUALITY_AUDIT(attestation_path, signature_path)


def test_local_quality_audit_rejects_expired_signed_attestation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    attestation_path, signature_path, *_rest = _write_quality_audit_inputs(tmp_path)
    monkeypatch.setattr(
        publication.wordpress_quality_audit,
        "load_contract",
        lambda: ({"contract": "validated"}, "1" * 64),
    )
    monkeypatch.setattr(
        publication.wordpress_quality_audit,
        "read_json",
        lambda _path: ({}, b"ledger\n"),
    )

    def expired(*_args: object, **_kwargs: object) -> object:
        raise publication.wordpress_quality_audit.QualityAuditFailure(
            "QUALITY_AUDIT_ATTESTATION_EXPIRED"
        )

    monkeypatch.setattr(
        publication.wordpress_quality_audit,
        "validate_document",
        expired,
    )
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_QUALITY_AUDIT_INVALID",
    ):
        ORIGINAL_STRICT_LOCAL_QUALITY_AUDIT(attestation_path, signature_path)


def _valid_public_seo_report() -> tuple[Any, dict[str, Any], Any]:
    contract = publication.wordpress_seo_audit.load_contract()
    now = publication.datetime.now(publication.UTC)
    observed = now.isoformat().replace("+00:00", "Z")

    def check() -> dict[str, str]:
        return {
            "status": "PASS",
            "detail": "VERIFIED",
            "evidence_sha256": "7" * 64,
            "observed_at": observed,
        }

    report = {
        "schema": "RAOS_WORDPRESS_SEO_AUDIT_REPORT_V1",
        "generated_at": observed,
        "origin": contract.origin,
        "status": "PASS",
        "inventory_count": 14,
        "content_sitemap_count": 13,
        "contract_sha256": contract.contract_sha256,
        "portfolio_sha256": contract.portfolio_sha256,
        "pages": [
            {
                "identifier": item.identifier,
                "role": item.role,
                "url": item.url,
                "status": "PASS",
                "checks": {name: check() for name in publication.SEO_CORE_PAGE_CHECKS},
                "schema_types": sorted(contract.required_types[item.role]),
                "index_state": {
                    "state": "UNAVAILABLE",
                    "basis": "UNAVAILABLE",
                },
            }
            for item in contract.items
        ],
        "surfaces": {name: check() for name in publication.SEO_SURFACE_CHECKS},
        "index_state_basis": "UNAVAILABLE",
    }
    return contract, report, now


def test_complete_public_seo_audit_is_hash_bound_to_all_14_urls() -> None:
    contract, report, now = _valid_public_seo_report()

    binding = publication._validated_public_seo_audit_report(
        report,
        contract,
        now=now,
    )

    assert binding["status"] == "PASS"
    assert binding["contract_sha256"] == contract.contract_sha256
    assert binding["portfolio_sha256"] == contract.portfolio_sha256
    assert set(binding["page_evidence_sha256"]) == (
        publication.SEO_INVENTORY_IDENTIFIERS
    )
    assert set(binding["surface_evidence_sha256"]) == (publication.SEO_SURFACE_CHECKS)
    publication._validate_seo_audit_binding(binding)


@pytest.mark.parametrize(
    "tamper",
    [
        "missing_twitter",
        "forbidden_schema",
        "failed_page",
        "failed_surface",
        "stale_report",
        "contract_drift",
        "duplicate_page",
        "index_basis_without_gsc",
    ],
)
def test_complete_public_seo_audit_fails_closed_on_tamper(tamper: str) -> None:
    contract, original, now = _valid_public_seo_report()
    report = json.loads(json.dumps(original))
    if tamper == "missing_twitter":
        del report["pages"][0]["checks"]["twitter_image"]
    elif tamper == "forbidden_schema":
        report["pages"][0]["schema_types"].append("Product")
    elif tamper == "failed_page":
        report["pages"][0]["status"] = "FAIL"
    elif tamper == "failed_surface":
        report["surfaces"]["robots"]["status"] = "FAIL"
    elif tamper == "stale_report":
        report["generated_at"] = "2020-01-01T00:00:00Z"
    elif tamper == "contract_drift":
        report["contract_sha256"] = "0" * 64
    elif tamper == "duplicate_page":
        report["pages"][1]["identifier"] = report["pages"][0]["identifier"]
    elif tamper == "index_basis_without_gsc":
        report["index_state_basis"] = "OWNER_PRIVATE_LIVE_GSC_URL_INSPECTION_V1"
        for page in report["pages"]:
            page["index_state"] = {
                "state": "INDEXED",
                "basis": "OWNER_PRIVATE_LIVE_GSC_URL_INSPECTION_V1",
            }
    else:  # pragma: no cover - closed parameter inventory
        raise AssertionError(tamper)

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_SEO_AUDIT_INVALID",
    ):
        publication._validated_public_seo_audit_report(
            report,
            contract,
            now=now,
        )


def _document(
    article: Any, post_id: int = 82, *, status: str = "draft"
) -> dict[str, Any]:
    value = article.document() | {
        "schema": "ContentDocumentV1",
        "id": post_id,
        "status": status,
        "revision_id": post_id,
        "modified_gmt": "2026-08-29T00:00:00Z",
        "content_sha256": f"{post_id:064x}",
    }
    return value


class ReconcileClient:
    def __init__(self, readback: dict[str, Any]) -> None:
        self.readback = readback
        self.calls: list[tuple[str, dict[str, object]]] = []

    def call(self, name: str, arguments: dict[str, object]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        if name == "raos-codex-content-get":
            return self.readback
        if name == "raos-codex-content-update-draft":
            return self.readback
        raise AssertionError(name)


class MultiReconcileClient:
    def __init__(self, readbacks: list[dict[str, Any]]) -> None:
        self.readbacks = {document["id"]: document for document in readbacks}
        self.calls: list[tuple[str, dict[str, object]]] = []

    def call(self, name: str, arguments: dict[str, object]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        assert name == "raos-codex-content-get"
        post_id = arguments["id"]
        assert isinstance(post_id, int)
        return self.readbacks[post_id]


def _private_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    os.chmod(tmp_path, 0o700)
    directory = tmp_path / "publication-requests"
    monkeypatch.setattr(publication, "PRIVATE_REQUEST_DIRECTORY", directory)
    publication._ensure_private_directory()
    return directory / "request.json"


def test_exact_draft_is_reused_and_read_back_without_update(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    document = _document(article)
    client = ReconcileClient(document)
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt([article], path)

    result = publication.reconcile_drafts(client, [article], [document], receipt, path)

    assert result[article.production_slug] == document
    assert [name for name, _ in client.calls] == ["raos-codex-content-get"]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_known_draft_is_cas_replaced_but_unknown_drift_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    drifted = _document(article)
    drifted["title"] = "prior workflow title"
    updated = _document(article)
    client = ReconcileClient(updated)
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt([article], path)

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_UNKNOWN_DRAFT_DRIFT",
    ):
        publication.reconcile_drafts(client, [article], [drifted], receipt, path)

    receipt["drafts"] = {
        article.production_slug: {
            "id": drifted["id"],
            "content_sha256": drifted["content_sha256"],
        }
    }
    client.calls.clear()
    publication.reconcile_drafts(client, [article], [drifted], receipt, path)
    update = next(arguments for name, arguments in client.calls if "update" in name)
    assert update["mode"] == "replace"
    assert update["precondition"]["content_sha256"] == drifted["content_sha256"]


def test_existing_published_target_is_bound_to_private_baseline_before_reuse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    published = _document(article, status="publish")
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt([article], path)
    client = ReconcileClient(published)

    authoritative = publication.capture_existing_baselines(
        client,
        [article],
        [published],
        receipt,
        path,
    )
    result = publication.reconcile_drafts(
        client,
        [article],
        authoritative,
        receipt,
        path,
    )

    assert result[article.production_slug] == published
    assert receipt["baselines"][article.production_slug] == {
        "id": published["id"],
        "slug": article.production_slug,
        "status": "publish",
        "revision_id": published["revision_id"],
        "modified_gmt": published["modified_gmt"],
        "content_sha256": published["content_sha256"],
    }
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["baselines"] == receipt["baselines"]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_policy_page_baseline_is_page_typed_and_unknown_drift_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    page = publication.load_policy_pages()[0]
    published = _document(page, status="publish")
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt([page], path)
    publication.capture_existing_baselines(
        ReconcileClient(published),
        [page],
        [published],
        receipt,
        path,
        require_existing_published=True,
    )
    assert receipt["selected_documents"] == {page.production_slug: "page"}
    assert receipt["baselines"][page.production_slug]["post_type"] == "page"

    drifted = dict(published)
    drifted["revision_id"] += 1
    drifted["modified_gmt"] = "2026-08-29T00:01:00Z"
    drifted["content_sha256"] = "f" * 64
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_UNKNOWN_BASELINE_DRIFT",
    ):
        publication.capture_existing_baselines(
            ReconcileClient(drifted),
            [page],
            [drifted],
            receipt,
            path,
            require_existing_published=True,
        )


def test_known_draft_does_not_authorize_a_published_target_in_normal_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    published = _document(article, status="publish")
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt([article], path)
    receipt["drafts"] = {
        article.production_slug: {
            "id": published["id"],
            "content_sha256": published["content_sha256"],
        }
    }

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLISHED_CONFLICT",
    ):
        publication.reconcile_drafts(
            ReconcileClient(published),
            [article],
            [published],
            receipt,
            path,
        )


def test_unknown_post_drift_after_baseline_is_refused_before_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    original = _document(article, status="publish")
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt([article], path)
    publication.capture_existing_baselines(
        ReconcileClient(original), [article], [original], receipt, path
    )
    drifted = dict(original)
    drifted["content_sha256"] = "f" * 64
    drifted["revision_id"] += 1
    drifted["modified_gmt"] = "2026-08-29T00:01:00Z"

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_UNKNOWN_BASELINE_DRIFT",
    ):
        publication.capture_existing_baselines(
            ReconcileClient(drifted), [article], [drifted], receipt, path
        )


@pytest.mark.parametrize("listed_state", [None, "draft"])
def test_all_mode_refuses_a_missing_or_unpublished_existing_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    listed_state: str | None,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt([article], path)
    documents = (
        [] if listed_state is None else [_document(article, status=listed_state)]
    )

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_UNKNOWN_BASELINE_DRIFT",
    ):
        publication.capture_existing_baselines(
            ReconcileClient(documents[0] if documents else _document(article)),
            [article],
            documents,
            receipt,
            path,
            require_existing_published=True,
        )


def test_all_mode_allows_only_the_explicit_missing_comparison_policy_page(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    page = next(
        item
        for item in publication.load_policy_pages()
        if item.production_slug == "comparison-policy"
    )
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt([page], path)

    assert (
        publication.capture_existing_baselines(
            ReconcileClient(_document(page)),
            [page],
            [],
            receipt,
            path,
            require_existing_published=True,
        )
        == []
    )

    unknown_draft = _document(page, status="draft")
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_UNKNOWN_BASELINE_DRIFT",
    ):
        publication.capture_existing_baselines(
            ReconcileClient(unknown_draft),
            [page],
            [unknown_draft],
            receipt,
            path,
            require_existing_published=True,
        )

    receipt["drafts"] = {
        page.production_slug: {
            "id": unknown_draft["id"],
            "content_sha256": unknown_draft["content_sha256"],
        }
    }
    authoritative = publication.capture_existing_baselines(
        ReconcileClient(unknown_draft),
        [page],
        [unknown_draft],
        receipt,
        path,
        require_existing_published=True,
    )
    assert authoritative == [unknown_draft]


def test_published_target_revision_only_race_is_refused_on_second_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    original = _document(article, status="publish")
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt([article], path)
    receipt["baselines"][article.production_slug] = publication._baseline_record(
        original
    )
    revised = dict(original)
    revised["revision_id"] += 1
    revised["modified_gmt"] = "2026-08-29T00:01:00Z"

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_DRAFT_READBACK_FAILED",
    ):
        publication.reconcile_drafts(
            ReconcileClient(revised),
            [article],
            [original],
            receipt,
            path,
        )


@pytest.mark.parametrize(
    "replacement_state",
    ["APPLIED_ATTEMPT_REPLACED", "EXPIRED_ATTEMPT_REPLACED"],
)
def test_replaced_attempt_reconciles_multiple_known_published_targets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, replacement_state: str
) -> None:
    articles = publication.load_articles(
        "roomba-mini-vs-switchbot-k11-pro,solota-vs-rakua-mini-plus"
    )
    published = [
        _document(article, post_id=85 + index, status="publish")
        for index, article in enumerate(articles)
    ]
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt(articles, path)
    receipt["state"] = replacement_state
    receipt["drafts"] = {
        article.production_slug: {
            "id": document["id"],
            "content_sha256": document["content_sha256"],
        }
        for article, document in zip(articles, published, strict=True)
    }
    client = MultiReconcileClient(published)

    result = publication.reconcile_drafts(client, articles, published, receipt, path)

    assert result == {
        article.production_slug: document
        for article, document in zip(articles, published, strict=True)
    }
    assert [name for name, _ in client.calls] == [
        "raos-codex-content-get",
        "raos-codex-content-get",
    ]
    assert receipt["state"] == "DRAFTS_READY"


class PaginatedClient:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = documents
        self.pages: list[int] = []

    def call(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        assert name == "raos-codex-content-list"
        page = arguments["page"]
        assert isinstance(page, int)
        self.pages.append(page)
        start = (page - 1) * publication.LIST_PER_PAGE
        return {
            "schema": "ContentDocumentListV1",
            "page": page,
            "per_page": publication.LIST_PER_PAGE,
            "total": len(self.documents),
            "documents": self.documents[start : start + publication.LIST_PER_PAGE],
        }


def test_content_list_fetches_every_page() -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    documents = [_document(article, post_id=index) for index in range(1, 24)]
    client = PaginatedClient(documents)
    assert publication.list_all_documents(client) == documents
    assert client.pages == [1, 2, 3]


def _tools() -> dict[str, dict[str, object]]:
    result = {name: {} for name in publication.EXPECTED_TOOLS}
    result["raos-codex-content-propose-release"] = {
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["id", "precondition", "document"],
            "properties": {
                "idempotency_key": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                }
            },
        }
    }
    result["raos-codex-publication-batch-register"] = {
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["proposal_ids", "expected_theme_tree_sha256"],
            "properties": {
                "proposal_ids": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 20,
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "pattern": "^[0-9a-f]{64}$",
                    },
                },
                "expected_theme_tree_sha256": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
            },
        }
    }
    return result


def _deployment_tools() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for name in sorted(publication.EXPECTED_DEPLOYMENT_TOOLS):
        schema: dict[str, object] = {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
        if name == "theme-propose-release":
            schema["properties"] = {
                "idempotency_key": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                }
            }
        if name in {"publication-batch-status", "release-wait-and-apply"}:
            schema["required"] = [
                "batch_token",
                "batch_manifest_sha256",
                "proposal_ids",
            ]
            schema["properties"] = {
                "batch_token": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
                "batch_manifest_sha256": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
                "proposal_ids": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 20,
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "pattern": "^[0-9a-f]{64}$",
                    },
                },
            }
        result.append(
            {
                "name": name,
                "inputSchema": schema,
                "annotations": {
                    "readOnlyHint": name
                    in {"deployment-status", "publication-batch-status"},
                    "destructiveHint": name
                    in {
                        "release-wait-and-apply",
                        "plugin-apply-change",
                        "operation-recover",
                    },
                    "idempotentHint": name
                    not in {"theme-propose-release", "plugin-propose-change"},
                    "openWorldHint": name == "plugin-propose-change",
                },
            }
        )
    return result


class WorkflowClient:
    def __init__(self, article: Any, events: list[str]) -> None:
        self.article = article
        self.events = events
        self.document = _document(article)
        self.published = False
        self.batch_registration_state = "REGISTERED"
        self.runtime_version = publication.theme_version()
        self.runtime_revision = publication.EXPECTED_THEME_RUNTIME_REVISION

    def initialize(self) -> None:
        self.events.append("remote-initialize")

    def public_authorization(self) -> str:
        return "Basic dGVzdDp0ZXN0"

    def tools(self) -> dict[str, dict[str, object]]:
        return _tools()

    def current_document(self) -> dict[str, object]:
        document = self.document | {"status": "publish" if self.published else "draft"}
        if self.published:
            document["content_sha256"] = publication._content_after_sha256(
                self.article.document(), self.document["id"]
            )
        return document

    def status(self) -> dict[str, object]:
        return {
            "schema": "RAOSWordPressSiteStatusV1",
            "origin": publication.ORIGIN,
            "wordpress_version_compatible": True,
            "mcp_adapter_version": "0.6.1",
            "mcp_adapter_version_compatible": True,
            "plugin_version": publication.EXPECTED_PLUGIN_VERSION,
            "plugin_runtime_revision": publication.EXPECTED_PLUGIN_RUNTIME_REVISION,
            "writes_enabled": {
                "global": True,
                "draft": True,
                "content_apply": True,
                "theme_apply": True,
                "plugin_apply": True,
            },
            "measurement": {
                "plugin_active": True,
                "plugin_version": "1.0.0",
                "collection_enabled": False,
                "aggregate_ability_registered": True,
                "raw_event_tool_exposed": False,
            },
            "theme": {
                "slug": "kurashinoshirube-child",
                "exists": True,
                "active": True,
                "version": publication.theme_version(),
                "runtime_version": self.runtime_version,
                "runtime_revision": self.runtime_revision,
            },
            "yoast": {
                "plugin_slug": "wordpress-seo",
                "installed": True,
                "active": True,
                "version": publication.EXPECTED_YOAST_VERSION,
                "version_exact": True,
                "options": json.loads(json.dumps(publication.EXPECTED_YOAST_OPTIONS)),
                "settings_fingerprint": (
                    publication.EXPECTED_YOAST_SETTINGS_FINGERPRINT
                ),
                "settings_exact": True,
            },
            "apply_authorization": {
                "mode": "approval_scoped_lease",
                "default": False,
                "single_use": True,
                "lease_ttl_seconds": publication.EXPECTED_APPLY_LEASE_TTL_SECONDS,
            },
            "server": {
                "endpoint": publication.EDITOR_ENDPOINT,
                "publish_tool_exposed": False,
                "delete_tool_exposed": False,
                "media_write_tool_exposed": False,
                "proposal_review_ttl_seconds": publication.EXPECTED_PROPOSAL_REVIEW_TTL_SECONDS,
            },
        }

    def call(self, name: str, arguments: dict[str, object]) -> dict[str, Any]:
        self.events.append(name)
        if name == "raos-codex-site-status":
            return self.status()
        if name == "raos-codex-content-list":
            return {
                "schema": "ContentDocumentListV1",
                "page": 1,
                "per_page": publication.LIST_PER_PAGE,
                "total": 1,
                "documents": [self.current_document()],
            }
        if name == "raos-codex-content-get":
            return self.current_document()
        if name == "raos-codex-operation-get":
            assert arguments == {"operation_id": "a" * 64}
            return {
                "schema": "OperationReceiptV1",
                "proposal_id": "a" * 64,
                "operation_id": "a" * 64,
                "state": "APPLIED" if self.published else "MANUAL_REQUIRED",
                "result_code": (
                    "CONTENT_RELEASE_APPLIED"
                    if self.published
                    else "HUMAN_APPROVAL_REQUIRED"
                ),
                "before_sha256": self.document["content_sha256"],
                "after_sha256": publication._content_after_sha256(
                    self.article.document(), self.document["id"]
                ),
                "audit_id": "3" * 64,
            }
        if name == "raos-codex-content-propose-release":
            assert publication.SHA256_RE.fullmatch(str(arguments["idempotency_key"]))
            return {
                "schema": "ContentReleaseProposalV1",
                "proposal_id": "a" * 64,
                "after_sha256": publication._content_after_sha256(
                    self.article.document(), self.document["id"]
                ),
                "expires_at_gmt": "2099-08-29T00:15:00Z",
            }
        if name == "raos-codex-publication-batch-register":
            proposal_ids = arguments["proposal_ids"]
            assert isinstance(proposal_ids, list)
            assert proposal_ids == sorted(proposal_ids)
            expected_theme = arguments["expected_theme_tree_sha256"]
            assert publication.SHA256_RE.fullmatch(str(expected_theme))
            return {
                "schema": "RAOSWordPressPublicationBatchV1",
                "batch_token": "c" * 64,
                "batch_manifest_sha256": "d" * 64,
                "expected_theme_tree_sha256": expected_theme,
                "proposal_count": len(proposal_ids),
                "proposal_ids": proposal_ids,
                "state": self.batch_registration_state,
                "expires_at_gmt": "2099-08-29T00:15:00Z",
                "review_url": publication.REVIEW_URL,
            }
        raise AssertionError(name)


class DeploymentRunner:
    def __init__(
        self,
        client: WorkflowClient,
        events: list[str],
        *,
        fail_first_wait: bool = False,
        batch_status_state: str = "APPROVED",
    ) -> None:
        self.client = client
        self.events = events
        self.fail_first_wait = fail_first_wait
        self.batch_status_state = batch_status_state
        self.watcher_calls = 0
        self.theme_proposed = False
        self.local_tree = publication.tracked_theme_tree_sha256()
        self.live_tree = "9" * 64
        self.runtime_version = publication.theme_version()
        self.runtime_revision = publication.EXPECTED_THEME_RUNTIME_REVISION

    def status(self) -> dict[str, object]:
        return {
            "schema": "RAOSWordPressDeploymentStatusV1",
            "origin": publication.ORIGIN,
            "plugin_runtime_revision": publication.EXPECTED_PLUGIN_RUNTIME_REVISION,
            "php_version": "8.3.0",
            "wordpress_version": "7.1.0",
            "theme": {
                "slug": "kurashinoshirube-child",
                "version": publication.theme_version(),
                "runtime_version": self.runtime_version,
                "runtime_revision": self.runtime_revision,
                "active": True,
                "tree_sha256": self.live_tree,
            },
            "gates": {
                "global": True,
                "content_apply": True,
                "theme_apply": True,
                "plugin_apply": True,
            },
            "apply_authorization": {
                "mode": "approval_scoped_lease",
                "default": False,
                "single_use": True,
                "lease_ttl_seconds": publication.EXPECTED_APPLY_LEASE_TTL_SECONDS,
            },
            "private_directory_ready": True,
        }

    def __call__(
        self, arguments: tuple[str, ...], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        assert arguments == (
            publication.NODE_BIN.as_posix(),
            "--experimental-strip-types",
            publication.DEPLOYMENT_BRIDGE.as_posix(),
        )
        messages = [
            json.loads(line)
            for line in bytes(kwargs["input"]).decode("utf-8").splitlines()
        ]
        assert [message["method"] for message in messages] == [
            "initialize",
            "notifications/initialized",
            "tools/list",
            "tools/call",
        ]
        call = messages[3]["params"]
        name = call["name"]
        tool_arguments = call["arguments"]
        self.events.append(f"deployment:{name}")
        if name == "deployment-status":
            value = self.status()
        elif name == "publication-batch-status":
            expected_ids = ["a" * 64]
            if self.theme_proposed:
                expected_ids.append("b" * 64)
            assert tool_arguments == {
                "batch_token": "c" * 64,
                "batch_manifest_sha256": "d" * 64,
                "proposal_ids": sorted(expected_ids),
            }
            value = {
                "schema": "RAOSWordPressPublicationBatchStatusV1",
                "batch_token": "c" * 64,
                "batch_manifest_sha256": "d" * 64,
                "proposal_count": len(expected_ids),
                "proposal_ids": sorted(expected_ids),
                "state": self.batch_status_state,
                "expires_at_gmt": "2099-08-29T00:15:00Z",
                "preconditions_ready": self.batch_status_state
                in {"APPROVED", "APPLIED"},
            }
        elif name == "theme-propose-release":
            self.theme_proposed = True
            assert publication.SHA256_RE.fullmatch(tool_arguments["idempotency_key"])
            value = {
                "proposal": {
                    "proposal_id": "b" * 64,
                    "after_tree_sha256": self.local_tree,
                    "expires_at_gmt": "2099-08-29T00:15:00Z",
                }
            }
        elif name == "release-wait-and-apply":
            self.watcher_calls += 1
            expected_ids = ["a" * 64]
            if self.theme_proposed:
                expected_ids.append("b" * 64)
            assert tool_arguments == {
                "batch_token": "c" * 64,
                "batch_manifest_sha256": "d" * 64,
                "proposal_ids": sorted(expected_ids),
            }
            if self.fail_first_wait and self.watcher_calls == 1:
                value = {"code": "WORDPRESS_MCP_RELEASE_WAIT_TIMEOUT"}
                return self._response(arguments, value, is_error=True)
            self.client.published = True
            if self.theme_proposed:
                self.live_tree = self.local_tree
                self.runtime_version = publication.theme_version()
                self.client.runtime_version = publication.theme_version()
                self.runtime_revision = publication.EXPECTED_THEME_RUNTIME_REVISION
                self.client.runtime_revision = (
                    publication.EXPECTED_THEME_RUNTIME_REVISION
                )
            receipts: list[dict[str, object]] = []
            if self.theme_proposed:
                receipts.append(
                    {
                        "schema": "OperationReceiptV1",
                        "proposal_id": "b" * 64,
                        "operation_id": "b" * 64,
                        "state": "APPLIED",
                        "result_code": "THEME_RELEASE_APPLIED",
                        "before_sha256": "9" * 64,
                        "after_sha256": self.local_tree,
                        "audit_id": "2" * 64,
                    }
                )
            receipts.append(
                {
                    "schema": "OperationReceiptV1",
                    "proposal_id": "a" * 64,
                    "operation_id": "a" * 64,
                    "state": "APPLIED",
                    "result_code": "CONTENT_RELEASE_APPLIED",
                    "before_sha256": "0" * 64,
                    "after_sha256": publication._content_after_sha256(
                        self.client.article.document(), self.client.document["id"]
                    ),
                    "audit_id": "3" * 64,
                }
            )
            value = {
                "schema": "ReleaseWaitApplyReceiptV1",
                "batch_token": "c" * 64,
                "batch_manifest_sha256": "d" * 64,
                "proposal_count": len(expected_ids),
                "proposal_ids": sorted(expected_ids),
                "state": "APPLIED",
                "receipts": receipts,
            }
        else:
            raise AssertionError(name)
        return self._response(arguments, value)

    @staticmethod
    def _response(
        arguments: tuple[str, ...], value: dict[str, object], *, is_error: bool = False
    ) -> subprocess.CompletedProcess[bytes]:
        responses = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "protocolVersion": publication.PROTOCOL_VERSION,
                    "serverInfo": {
                        "name": "raos-wordpress-bridge",
                        "version": "1.1.0",
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {"tools": _deployment_tools()},
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(value)}],
                    "structuredContent": value,
                    **({"isError": True} if is_error else {}),
                },
            },
        ]
        output = b"".join(
            json.dumps(response).encode("utf-8") + b"\n" for response in responses
        )
        return subprocess.CompletedProcess(arguments, 0, output, b"")


def test_partial_proposal_checkpoint_is_never_ready_for_batch_registration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles = publication.load_articles("all")
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt(articles, path)
    receipt["state"] = "PROPOSALS_IN_PROGRESS"
    receipt["proposals"] = [
        {
            "kind": "CONTENT_RELEASE",
            "slug": articles[0].production_slug,
            "proposal_id": "a" * 64,
            "after_sha256": "b" * 64,
            "expires_at_gmt": "2099-08-29T00:15:00Z",
            "idempotency_key": "c" * 64,
        }
    ]

    assert publication._unregistered_proposal_set_ready(receipt, len(articles)) is False
    receipt["state"] = "PROPOSALS_READY"
    assert publication._unregistered_proposal_set_ready(receipt, len(articles)) is False
    receipt["proposals"] = [
        {
            "kind": "CONTENT_RELEASE",
            "slug": article.production_slug,
            "proposal_id": f"{index + 1:064x}",
            "after_sha256": f"{index + 20:064x}",
            "expires_at_gmt": "2099-08-29T00:15:00Z",
            "idempotency_key": f"{index + 40:064x}",
        }
        for index, article in enumerate(articles)
    ]
    assert publication._unregistered_proposal_set_ready(receipt, len(articles)) is True
    receipt["proposals"].insert(
        0,
        {
            "kind": "THEME_RELEASE",
            "slug": None,
            "proposal_id": "e" * 64,
            "after_sha256": receipt["desired_theme_tree_sha256"],
            "expires_at_gmt": "2099-08-29T00:15:00Z",
            "idempotency_key": "f" * 64,
        },
    )
    assert publication._unregistered_proposal_set_ready(receipt, len(articles)) is True


def test_all_selection_builds_one_theme_ten_posts_and_three_page_proposals(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles = publication.load_publication_items("all")
    assert len(articles) == 13
    assert [article.post_type for article in articles].count("post") == 10
    assert [article.post_type for article in articles].count("page") == 3
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt(articles, path, TEST_THEME_TREE_SHA256)
    drafts = {
        article.production_slug: _document(article, post_id=200 + index)
        for index, article in enumerate(articles)
    }
    proposal_ids = {
        article.production_slug: f"{index + 10:064x}"
        for index, article in enumerate(articles)
    }

    class ProposalClient:
        def call(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
            if name == "raos-codex-content-propose-release":
                document = arguments["document"]
                assert isinstance(document, dict)
                slug = document["slug"]
                assert isinstance(slug, str)
                return {
                    "schema": "ContentReleaseProposalV1",
                    "proposal_id": proposal_ids[slug],
                    "after_sha256": publication._content_after_sha256(
                        document, int(arguments["id"])
                    ),
                    "expires_at_gmt": "2099-08-29T00:15:00Z",
                }
            if name == "raos-codex-publication-batch-register":
                ids = arguments["proposal_ids"]
                assert isinstance(ids, list)
                return {
                    "schema": "RAOSWordPressPublicationBatchV1",
                    "batch_token": "c" * 64,
                    "batch_manifest_sha256": "d" * 64,
                    "expected_theme_tree_sha256": TEST_THEME_TREE_SHA256,
                    "proposal_count": 14,
                    "proposal_ids": ids,
                    "state": "REGISTERED",
                    "expires_at_gmt": "2099-08-29T00:15:00Z",
                    "review_url": publication.REVIEW_URL,
                }
            raise AssertionError(name)

    def deployment_call(
        command: str,
        value: dict[str, object],
        **kwargs: object,
    ) -> dict[str, object]:
        assert command == "theme-propose-release"
        return {
            "proposal": {
                "proposal_id": "f" * 64,
                "after_tree_sha256": TEST_THEME_TREE_SHA256,
                "expires_at_gmt": "2099-08-29T00:15:00Z",
            }
        }

    monkeypatch.setattr(publication, "_deployment_mcp_call", deployment_call)
    client = ProposalClient()
    proposals = publication.create_proposals(
        client,
        articles,
        drafts,
        True,
        receipt,
        path,
    )
    registration = publication.register_publication_batch(client, receipt, path)

    assert [proposal["kind"] for proposal in proposals] == ["THEME_RELEASE"] + [
        "CONTENT_RELEASE"
    ] * 13
    assert [proposal["slug"] for proposal in proposals[1:]] == [
        article.production_slug for article in articles
    ]
    assert [proposal.get("post_type") for proposal in proposals[1:]] == [
        "post"
    ] * 10 + ["page"] * 3
    assert registration["proposal_count"] == 14
    assert set(receipt["operation_ids"]) == {
        proposal["proposal_id"] for proposal in proposals
    }


def test_missing_idempotency_schema_stops_before_mutation() -> None:
    tools = _tools()
    del tools["raos-codex-content-propose-release"]["inputSchema"]["properties"]
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_IDEMPOTENCY_BOOTSTRAP_REQUIRED",
    ):
        publication.validate_tool_contract(tools)


def test_site_status_requires_plugin_1_3_1_and_distinct_review_and_lease_ttls() -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    client = WorkflowClient(article, [])
    status = client.status()
    status["plugin_version"] = "1.1.0"
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_SITE_NOT_READY",
    ):
        publication.validate_site_status(status)
    status = client.status()
    status["apply_authorization"]["lease_ttl_seconds"] = 3600
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_SITE_NOT_READY",
    ):
        publication.validate_site_status(status)
    status = client.status()
    status["server"]["proposal_review_ttl_seconds"] = 900
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_SITE_NOT_READY",
    ):
        publication.validate_site_status(status)
    assert publication.EXPECTED_PROPOSAL_REVIEW_TTL_SECONDS == 3600
    assert publication.EXPECTED_APPLY_LEASE_TTL_SECONDS == 900
    assert publication.RELEASE_FOREGROUND_TIMEOUT_SECONDS == 4680
    for invalid_runtime in (None, "0" * 64, "not-a-sha256"):
        status = client.status()
        status["plugin_runtime_revision"] = invalid_runtime
        with pytest.raises(
            publication.PublicationFailure,
            match="RAOS_WORDPRESS_REQUEST_SITE_NOT_READY",
        ):
            publication.validate_site_status(status)
    status = client.status()
    del status["plugin_runtime_revision"]
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_SITE_NOT_READY",
    ):
        publication.validate_site_status(status)
    status = client.status()
    status["theme"]["runtime_version"] = None
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_SITE_NOT_READY",
    ):
        publication.validate_site_status(status)
    status = client.status()
    status["theme"]["runtime_revision"] = "not-a-sha256"
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_SITE_NOT_READY",
    ):
        publication.validate_site_status(status)
    status = client.status()
    del status["theme"]["runtime_revision"]
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_SITE_NOT_READY",
    ):
        publication.validate_site_status(status)
    status = client.status()
    status["theme"]["runtime_revision"] = None
    publication.validate_site_status(status)
    status = client.status()
    status["apply_authorization"] = {
        "mode": "approval_scoped_lease",
        "default": True,
        "single_use": True,
        "lease_ttl_seconds": publication.EXPECTED_APPLY_LEASE_TTL_SECONDS,
    }
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_SITE_NOT_READY",
    ):
        publication.validate_site_status(status)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("installed", False),
        ("active", False),
        ("version", "28.2"),
        ("version_exact", False),
        ("settings_fingerprint", "0" * 64),
        ("settings_exact", False),
    ],
)
def test_site_status_requires_exact_yoast_28_3_readback(
    field: str,
    value: object,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    status = WorkflowClient(article, []).status()
    yoast = status["yoast"]
    assert type(yoast) is dict
    yoast[field] = value

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_SITE_NOT_READY",
    ):
        publication.validate_site_status(status)


def test_site_status_requires_exact_yoast_options_and_bound_fingerprint() -> None:
    assert publication.EXPECTED_YOAST_SETTINGS_FINGERPRINT == publication.sha256_json(
        {
            "schema": "RAOSYoastSettingsV1",
            **publication.EXPECTED_YOAST_OPTIONS,
        }
    )
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    status = WorkflowClient(article, []).status()
    status["yoast"]["options"]["wpseo"]["tracking"] = True

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_SITE_NOT_READY",
    ):
        publication.validate_site_status(status)

    status = WorkflowClient(article, []).status()
    del status["yoast"]
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_SITE_NOT_READY",
    ):
        publication.validate_site_status(status)


def test_attempt_prepared_without_proposals_uses_review_window_plus_grace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_datetime = publication.datetime
    created_at = real_datetime(2026, 8, 30, 0, 0, 0, tzinfo=publication.UTC)

    class FixedDateTime(real_datetime):
        current = created_at

        @classmethod
        def now(cls, tz=None):
            return cls.current if tz is not None else cls.current.replace(tzinfo=None)

    monkeypatch.setattr(publication, "datetime", FixedDateTime)
    receipt = {
        "state": "ATTEMPT_PREPARED",
        "attempt_created_at_gmt": "2026-08-30T00:00:00Z",
        "proposals": [],
    }

    assert publication.ATTEMPT_PREPARED_EXPIRY_SECONDS == 3630
    FixedDateTime.current = created_at + publication.timedelta(seconds=930)
    assert publication._attempt_expired(receipt) is False
    FixedDateTime.current = created_at + publication.timedelta(seconds=3629)
    assert publication._attempt_expired(receipt) is False
    FixedDateTime.current = created_at + publication.timedelta(seconds=3630)
    assert publication._attempt_expired(receipt) is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("plugin_active", False),
        ("plugin_version", "0.9.0"),
        ("collection_enabled", True),
        ("aggregate_ability_registered", False),
        ("raw_event_tool_exposed", True),
    ],
)
def test_all_mode_site_status_requires_measurement_active_and_default_off(
    field: str, value: object
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    status = WorkflowClient(article, []).status()
    measurement = status["measurement"]
    assert type(measurement) is dict
    measurement[field] = value

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_SITE_NOT_READY",
    ):
        publication.validate_site_status(status, require_measurement_ready=True)

    # A legacy/single-article diagnostic read does not authorize collection,
    # but remains usable before the measurement plugin release is proposed.
    publication.validate_site_status(status, require_measurement_ready=False)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("plugin_active", True),
        ("plugin_active", None),
        ("collection_enabled", True),
        ("collection_enabled", None),
        ("raw_event_tool_exposed", True),
    ],
)
def test_standard_api_requires_explicitly_inactive_measurement(
    field: str, value: object
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    status = WorkflowClient(article, []).status()
    measurement = status["measurement"]
    assert type(measurement) is dict
    measurement["plugin_active"] = False
    measurement["plugin_version"] = None
    measurement["aggregate_ability_registered"] = False
    publication.validate_site_status(status, require_measurement_off=True)
    measurement[field] = value
    with pytest.raises(publication.PublicationFailure, match="SITE_NOT_READY"):
        publication.validate_site_status(status, require_measurement_off=True)
    status.pop("measurement")
    with pytest.raises(publication.PublicationFailure, match="SITE_NOT_READY"):
        publication.validate_site_status(status, require_measurement_off=True)


def test_standard_api_published_readback_rejects_active_measurement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    client = WorkflowClient(article, [])
    monkeypatch.setattr(publication, "_published_document_evidence", lambda *_args: {})

    def no_deployment_after_invalid_status(*_args: object, **_kwargs: object):
        raise AssertionError("deployment called after invalid measurement state")

    with pytest.raises(publication.PublicationFailure, match="SITE_NOT_READY"):
        publication.verify_published(
            client,
            [article],
            {
                "drafts": {},
                "desired_theme_runtime_revision": publication.EXPECTED_THEME_RUNTIME_REVISION,
            },
            tmp_path / "receipt.json",
            expected_theme_version=publication.EXPECTED_THEME_VERSION,
            expected_theme_tree_sha256="a" * 64,
            theme_was_proposed=False,
            require_measurement_ready=False,
            deployment_runner=no_deployment_after_invalid_status,
        )


def test_deployment_status_requires_runtime_revision_key_but_accepts_null(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    events: list[str] = []
    client = WorkflowClient(article, events)
    deployment = DeploymentRunner(client, events)
    status = deployment.status()
    del status["theme"]["runtime_revision"]
    monkeypatch.setattr(
        publication,
        "_deployment_mcp_call",
        lambda *_args, **_kwargs: status,
    )
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_DEPLOYMENT_STATUS_INVALID",
    ):
        publication.deployment_status()

    status = deployment.status()
    status["theme"]["runtime_revision"] = None
    assert publication.deployment_status()["theme"]["runtime_revision"] is None


@pytest.mark.parametrize(
    "invalid_runtime",
    [None, "0" * 64, "not-a-sha256"],
)
def test_deployment_status_requires_exact_plugin_runtime_revision(
    monkeypatch: pytest.MonkeyPatch,
    invalid_runtime: object,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    events: list[str] = []
    client = WorkflowClient(article, events)
    deployment = DeploymentRunner(client, events)
    status = deployment.status()
    status["plugin_runtime_revision"] = invalid_runtime
    monkeypatch.setattr(
        publication,
        "_deployment_mcp_call",
        lambda *_args, **_kwargs: status,
    )
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_DEPLOYMENT_STATUS_INVALID",
    ):
        publication.deployment_status()


def test_deployment_status_rejects_missing_plugin_runtime_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    events: list[str] = []
    client = WorkflowClient(article, events)
    deployment = DeploymentRunner(client, events)
    status = deployment.status()
    del status["plugin_runtime_revision"]
    monkeypatch.setattr(
        publication,
        "_deployment_mcp_call",
        lambda *_args, **_kwargs: status,
    )
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_DEPLOYMENT_STATUS_INVALID",
    ):
        publication.deployment_status()


def test_portfolio_refresh_runs_capture_then_both_materializations_in_foreground() -> (
    None
):
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def runner(
        command: tuple[str, ...], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, b"", b"")

    publication.run_editorial_portfolio_refresh(runner)

    assert [command[2:] for command, _ in calls] == [
        ("capture",),
        (
            "materialize-local",
            "--output-root",
            publication.PREVIEW_PRIVATE_ROOT.as_posix(),
        ),
        (
            "materialize-production",
            "--output-root",
            publication.PORTFOLIO_PRIVATE_ROOT.as_posix(),
        ),
    ]
    assert all(
        command[1] == publication.PORTFOLIO_SCRIPT.as_posix() for command, _ in calls
    )
    assert all(
        kwargs["stdout"] is None and kwargs["stderr"] is None for _, kwargs in calls
    )
    assert all(
        kwargs["env"] == publication.PORTFOLIO_SUBPROCESS_ENVIRONMENT
        for _, kwargs in calls
    )
    assert publication.PORTFOLIO_SUBPROCESS_ENVIRONMENT == {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "TMPDIR": "/tmp",
        "TEMP": "/tmp",
        "TMP": "/tmp",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _write_materialization_pair(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[list[Any], Path, Path]:
    articles = publication.load_articles("all")
    local_root = tmp_path / "local" / "materialized-fixtures-v2"
    production_root = tmp_path / "production" / "production-materialized-fixtures-v2"
    local_articles = local_root / "articles"
    local_articles.mkdir(parents=True)
    production_root.mkdir(parents=True)
    monkeypatch.setattr(publication, "LOCAL_MATERIALIZED_FIXTURE_ROOT", local_root)
    monkeypatch.setattr(
        publication,
        "LOCAL_MATERIALIZATION_RECEIPT",
        local_root / "materialization-receipt.v2.json",
    )
    monkeypatch.setattr(
        publication,
        "PRODUCTION_MATERIALIZATION_RECEIPT",
        production_root / "materialization-receipt.v2.json",
    )
    product_ids: set[str] = set()
    article_rows: list[dict[str, str]] = []
    for article in articles:
        parser = publication._PublicPageEvidenceParser()
        parser.feed(article.block_markup)
        parser.close()
        product_ids.update(
            str(cta["product_id"])
            for cta in publication._validated_ctas(
                parser,
                allow_empty=(
                    article.production_slug in publication.ZERO_PRODUCT_ROUTE_SLUGS
                ),
            )
        )
        payload = article.block_markup.encode("utf-8")
        (local_articles / f"{article.production_slug}.html").write_bytes(payload)
        article_rows.append(
            {
                "article_id": article.production_slug,
                "production_slug": article.production_slug,
                "content_sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    products = [
        {
            "product_id": product_id,
            "state": "verified",
            "provider_binding_sha256": hashlib.sha256(
                product_id.encode("ascii")
            ).hexdigest(),
        }
        for product_id in sorted(product_ids)
    ]
    media = [
        {
            "product_id": product_id,
            "image_sha256": hashlib.sha256(
                ("image:" + product_id).encode("ascii")
            ).hexdigest(),
            "image_extension": "jpg",
        }
        for product_id in sorted(product_ids)
    ]
    monkeypatch.setattr(
        publication,
        "_owner_materialized_product_ids",
        lambda **_kwargs: set(product_ids),
    )
    generated_at = publication.datetime.now(publication.UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    monkeypatch.setattr(
        publication,
        "_current_v2_source_binding",
        lambda **_kwargs: ("a" * 64, "e" * 64, "d" * 64, generated_at),
    )
    monkeypatch.setattr(
        publication,
        "_current_activation_v2_evidence_binding",
        lambda **_kwargs: {"product_safety": _test_product_safety_binding()},
    )
    common = {
        "schema": "RAOS_EDITORIAL_PORTFOLIO_MATERIALIZATION_RECEIPT_V2",
        "generated_at": generated_at,
        "portfolio_sha256": "a" * 64,
        "evidence_status_sha256": "e" * 64,
        "manufacturer_sales_state_sha256": "d" * 64,
        "manufacturer_sales_state_checked_at_utc": generated_at,
        "product_safety": _test_product_safety_binding(),
        "articles": article_rows,
        "products": products,
        "media": media,
        "completion": publication._expected_materialization_completion(len(products)),
    }
    local_receipt = publication.LOCAL_MATERIALIZATION_RECEIPT
    production_receipt = publication.PRODUCTION_MATERIALIZATION_RECEIPT
    local_receipt.write_text(json.dumps({**common, "mode": "local"}), encoding="utf-8")
    production_receipt.write_text(
        json.dumps({**common, "mode": "production"}), encoding="utf-8"
    )
    local_receipt.chmod(0o600)
    production_receipt.chmod(0o600)
    return articles, local_articles, local_receipt


def test_production_materialization_is_bound_to_the_exact_local_preview_variant(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles, local_articles, _ = _write_materialization_pair(monkeypatch, tmp_path)

    binding = publication.production_materialization_binding(articles)

    assert binding["portfolio_sha256"] == "a" * 64
    assert binding["evidence_status_sha256"] == "e" * 64
    assert (
        binding["local_receipt_sha256"]
        == hashlib.sha256(
            publication.LOCAL_MATERIALIZATION_RECEIPT.read_bytes()
        ).hexdigest()
    )
    assert (
        binding["production_receipt_sha256"]
        == hashlib.sha256(
            publication.PRODUCTION_MATERIALIZATION_RECEIPT.read_bytes()
        ).hexdigest()
    )
    assert binding["manufacturer_sales_state_sha256"] == "d" * 64
    assert binding["product_safety"] == _test_product_safety_binding()
    assert len(binding["articles"]) == 10
    target = local_articles / f"{articles[0].production_slug}.html"
    target.write_text(target.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID",
    ):
        publication.production_materialization_binding(articles)


def test_materialization_pair_refuses_evidence_set_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles, _, local_receipt = _write_materialization_pair(monkeypatch, tmp_path)
    local = json.loads(local_receipt.read_text(encoding="utf-8"))
    local["evidence_status_sha256"] = "f" * 64
    local_receipt.write_text(json.dumps(local), encoding="utf-8")
    local_receipt.chmod(0o600)

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID",
    ):
        publication.production_materialization_binding(articles)


def test_materialization_pair_refuses_manufacturer_sales_state_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles, _, local_receipt = _write_materialization_pair(monkeypatch, tmp_path)
    local = json.loads(local_receipt.read_text(encoding="utf-8"))
    local["manufacturer_sales_state_sha256"] = "f" * 64
    local_receipt.write_text(json.dumps(local), encoding="utf-8")
    local_receipt.chmod(0o600)

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID",
    ):
        publication.production_materialization_binding(articles)


@pytest.mark.parametrize(
    ("field", "mutate"),
    [
        (
            "completion",
            lambda receipt: receipt["completion"].update(
                {
                    "state": "INCOMPLETE",
                    "verified_product_count": 33,
                }
            ),
        ),
        (
            "media",
            lambda receipt: receipt["media"].pop(),
        ),
        (
            "products",
            lambda receipt: receipt["products"][0].update({"state": "not_found"}),
        ),
    ],
)
def test_production_materialization_rejects_incomplete_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    field: str,
    mutate: Any,
) -> None:
    articles, _, _ = _write_materialization_pair(monkeypatch, tmp_path)
    receipt_path = publication.PRODUCTION_MATERIALIZATION_RECEIPT
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert field in receipt
    mutate(receipt)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    receipt_path.chmod(0o600)

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID",
    ):
        publication.production_materialization_binding(articles)


def test_materialization_pair_rejects_media_or_completion_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles, _, local_receipt = _write_materialization_pair(monkeypatch, tmp_path)
    local = json.loads(local_receipt.read_text(encoding="utf-8"))
    local["media"][0]["image_sha256"] = "f" * 64
    local_receipt.write_text(json.dumps(local), encoding="utf-8")
    local_receipt.chmod(0o600)

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID",
    ):
        publication.production_materialization_binding(articles)


def test_production_materialization_replays_product_safety_instead_of_trusting_resealed_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles, _, _ = _write_materialization_pair(monkeypatch, tmp_path)
    for path in (
        publication.LOCAL_MATERIALIZATION_RECEIPT,
        publication.PRODUCTION_MATERIALIZATION_RECEIPT,
    ):
        document = json.loads(path.read_text(encoding="utf-8"))
        safety = document["product_safety"]
        safety["administrative_bundle_sha256"] = "f" * 64
        material = {
            key: value for key, value in safety.items() if key != "binding_sha256"
        }
        safety["binding_sha256"] = hashlib.sha256(
            json.dumps(
                material,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        path.write_text(json.dumps(document), encoding="utf-8")
        path.chmod(0o600)

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PRODUCT_SAFETY_INVALID",
    ):
        publication.production_materialization_binding(articles)


def test_publication_binding_rejects_missing_manufacturer_safety_even_with_valid_hash(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles, _, _ = _write_materialization_pair(monkeypatch, tmp_path)
    publication_binding = publication.production_materialization_binding(articles)
    binding = publication_binding["product_safety"]
    assert type(binding) is dict
    binding["manufacturer_verified_product_count"] = 0
    binding["complete_product_count"] = 0
    binding["complete"] = False
    material = {key: value for key, value in binding.items() if key != "binding_sha256"}
    binding["binding_sha256"] = hashlib.sha256(
        json.dumps(
            material,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID",
    ):
        publication._validate_materialization_binding(publication_binding)


def test_production_materialization_rejects_receipt_change_before_return(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles, _, _ = _write_materialization_pair(monkeypatch, tmp_path)
    generated_at = json.loads(
        publication.PRODUCTION_MATERIALIZATION_RECEIPT.read_text(encoding="utf-8")
    )["manufacturer_sales_state_checked_at_utc"]
    calls = 0

    def current(**_kwargs: object) -> tuple[str, str, str, str]:
        nonlocal calls
        calls += 1
        if calls == 2:
            path = publication.PRODUCTION_MATERIALIZATION_RECEIPT
            path.write_bytes(path.read_bytes() + b"\n")
            path.chmod(0o600)
        return "a" * 64, "e" * 64, "d" * 64, generated_at

    monkeypatch.setattr(publication, "_current_v2_source_binding", current)
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID",
    ):
        publication.production_materialization_binding(articles)


@pytest.mark.parametrize(
    "field",
    [
        "evidence_status_sha256",
        "local_receipt_sha256",
        "production_receipt_sha256",
    ],
)
def test_activation_binding_rejects_current_v2_digest_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    articles = publication.load_articles("all")
    activation = SimpleNamespace(
        v2_portfolio_sha256="a" * 64,
        v2_evidence_status_sha256="e" * 64,
        v2_local_receipt_sha256="5" * 64,
        v2_production_receipt_sha256="6" * 64,
    )
    current = {
        "portfolio_sha256": "a" * 64,
        "evidence_status_sha256": "e" * 64,
        "local_receipt_sha256": "5" * 64,
        "production_receipt_sha256": "6" * 64,
    }
    current[field] = "f" * 64
    monkeypatch.setattr(publication, "load_articles", lambda *_a, **_k: articles)
    monkeypatch.setattr(
        publication,
        "production_materialization_binding",
        lambda *_a, **_k: current,
    )
    monkeypatch.setattr(
        publication,
        "_current_activation_v2_evidence_binding",
        lambda **_kwargs: {
            "portfolio_sha256": "a" * 64,
            "evidence_status_sha256": "e" * 64,
        },
    )

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_RAKUTEN_ACTIVATION_INVALID",
    ):
        publication.activation_materialization_binding(
            activation,
            articles,
            require_recent=True,
        )


def test_activation_binding_persists_only_exact_hashes_and_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    articles = publication.load_articles("all")
    article_hashes = {
        article.production_slug: hashlib.sha256(
            article.block_markup.encode("utf-8")
        ).hexdigest()
        for article in articles
    }
    product_ids: set[str] = set()
    for article in articles:
        parser = publication._PublicPageEvidenceParser()
        parser.feed(article.block_markup)
        parser.close()
        product_ids.update(
            str(cta["product_id"])
            for cta in publication._validated_ctas(
                parser,
                allow_empty=(
                    article.production_slug in publication.ZERO_PRODUCT_ROUTE_SLUGS
                ),
            )
        )
    products = {
        product_id: {
            "state": "verified",
            "provider_binding_sha256": hashlib.sha256(
                product_id.encode("ascii")
            ).hexdigest(),
        }
        for product_id in sorted(product_ids)
    }
    media = [
        {
            "product_id": product_id,
            "image_sha256": hashlib.sha256(
                ("image:" + product_id).encode("ascii")
            ).hexdigest(),
            "image_extension": "jpg",
        }
        for product_id in sorted(product_ids)
    ]
    monkeypatch.setattr(
        publication,
        "_owner_materialized_product_ids",
        lambda **_kwargs: set(product_ids),
    )
    activation = SimpleNamespace(
        v2_portfolio_sha256="a" * 64,
        v2_evidence_status_sha256="e" * 64,
        v2_local_receipt_sha256="5" * 64,
        v2_production_receipt_sha256="6" * 64,
        v2_manufacturer_sales_state_sha256="7" * 64,
        v2_manufacturer_sales_state_checked_at_utc="2026-08-31T00:00:00Z",
        v2_product_safety=_test_product_safety_binding(),
        portfolio_sha256="b" * 64,
        production_article_sha256=article_hashes,
        article_count=10,
        provider_slot_count=20,
        provider_measurement_id_count=20,
        internal_cta_identity_count=74,
        cta_count=74,
        live_link_count=74,
        dry_run_sha256="c" * 64,
        admin_receipt_sha256="d" * 64,
        money_link_mapping_sha256="e" * 64,
        provider_slot_set_sha256="6" * 64,
        provider_measurement_binding_sha256="7" * 64,
        materialized_set_sha256="f" * 64,
        local_article_set_sha256="1" * 64,
        production_article_set_sha256="2" * 64,
        local_overlay_receipt_sha256="3" * 64,
        production_overlay_receipt_sha256="4" * 64,
        mapping_generated_at_utc="2026-08-31T00:01:00Z",
        admin_verified_at_utc="2026-08-31T00:02:00Z",
        activated_at_utc="2026-08-31T00:03:00Z",
    )
    monkeypatch.setattr(
        publication,
        "production_materialization_binding",
        lambda *_args, **_kwargs: {
            "schema": "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V1",
            "portfolio_sha256": "a" * 64,
            "evidence_status_sha256": "e" * 64,
            "local_receipt_sha256": "5" * 64,
            "production_receipt_sha256": "6" * 64,
            "manufacturer_sales_state_sha256": "7" * 64,
            "manufacturer_sales_state_checked_at_utc": "2026-08-31T00:00:00Z",
            "product_safety": _test_product_safety_binding(),
            "articles": article_hashes,
            "products": products,
            "media": media,
            "completion": publication._expected_materialization_completion(
                len(products)
            ),
        },
    )
    monkeypatch.setattr(
        publication,
        "_current_activation_v2_evidence_binding",
        lambda **_kwargs: {
            "portfolio_sha256": "a" * 64,
            "evidence_status_sha256": "e" * 64,
            "manufacturer_sales_state_sha256": "7" * 64,
            "manufacturer_sales_state_checked_at_utc": "2026-08-31T00:00:00Z",
            "product_safety": _test_product_safety_binding(),
            "products": products,
            "media": media,
        },
    )
    monkeypatch.setattr(
        publication, "load_articles", lambda *_args, **_kwargs: articles
    )

    binding = publication.activation_materialization_binding(
        activation,
        articles,
        require_recent=True,
    )

    publication._validate_materialization_binding(binding)
    assert binding["schema"] == "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V3"
    assert "://" not in json.dumps(binding, sort_keys=True)
    assert binding["activation"]["article_count"] == 10
    assert binding["activation"]["provider_slot_count"] == 20
    assert binding["activation"]["provider_measurement_id_count"] == 20
    assert binding["activation"]["internal_cta_identity_count"] == 74
    assert binding["activation"]["cta_count"] == 74
    assert binding["activation"]["live_link_count"] == 74
    assert binding["activation"]["v2_evidence_status_sha256"] == "e" * 64
    assert binding["activation"]["v2_local_receipt_sha256"] == "5" * 64
    assert binding["activation"]["v2_production_receipt_sha256"] == "6" * 64
    assert binding["activation"]["mapping_generated_at_utc"] == ("2026-08-31T00:01:00Z")
    assert binding["activation"]["admin_verified_at_utc"] == "2026-08-31T00:02:00Z"
    assert binding["activation"]["activated_at_utc"] == "2026-08-31T00:03:00Z"

    historical_v2 = json.loads(json.dumps(binding))
    historical_v2["schema"] = "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V2"
    for field in (
        "provider_slot_set_sha256",
        "provider_measurement_binding_sha256",
        "provider_slot_count",
        "provider_measurement_id_count",
        "internal_cta_identity_count",
        "live_link_count",
    ):
        historical_v2["activation"].pop(field)
    publication._validate_materialization_binding(historical_v2)
    captured = publication._fresh_receipt(
        articles,
        Path("/tmp/provider-binding.json"),
        TEST_THEME_TREE_SHA256,
        historical_v2,
    )
    assert not publication._receipt_matches_captured_inputs(
        captured,
        articles,
        TEST_THEME_TREE_SHA256,
        binding,
        None,
    )

    v2_with_provider_claim = json.loads(json.dumps(historical_v2))
    v2_with_provider_claim["activation"]["provider_slot_count"] = 20
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID",
    ):
        publication._validate_materialization_binding(v2_with_provider_claim)

    v3_without_internal_count = json.loads(json.dumps(binding))
    v3_without_internal_count["activation"].pop("internal_cta_identity_count")
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID",
    ):
        publication._validate_materialization_binding(v3_without_internal_count)

    for field, wrong_value in (
        ("provider_slot_count", 19),
        ("provider_measurement_id_count", 19),
        ("internal_cta_identity_count", 73),
        ("cta_count", 73),
        ("live_link_count", 73),
    ):
        invalid_count = json.loads(json.dumps(binding))
        invalid_count["activation"][field] = wrong_value
        with pytest.raises(
            publication.PublicationFailure,
            match="RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID",
        ):
            publication._validate_materialization_binding(invalid_count)

    invalid_time_order = json.loads(json.dumps(binding))
    invalid_time_order["activation"]["admin_verified_at_utc"] = "2026-08-31T00:04:00Z"
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID",
    ):
        publication._validate_materialization_binding(invalid_time_order)

    drifted_products = {key: dict(value) for key, value in products.items()}
    drifted_products[next(iter(drifted_products))]["provider_binding_sha256"] = "f" * 64
    monkeypatch.setattr(
        publication,
        "_current_activation_v2_evidence_binding",
        lambda **_kwargs: {
            "portfolio_sha256": "a" * 64,
            "evidence_status_sha256": "e" * 64,
            "manufacturer_sales_state_sha256": "7" * 64,
            "manufacturer_sales_state_checked_at_utc": "2026-08-31T00:00:00Z",
            "product_safety": _test_product_safety_binding(),
            "products": drifted_products,
            "media": media,
        },
    )
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_RAKUTEN_ACTIVATION_INVALID",
    ):
        publication.activation_materialization_binding(
            activation,
            articles,
            require_recent=True,
        )


def test_all_mode_recovers_registered_batch_before_provider_refresh(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles = publication.load_publication_items("all")
    path = tmp_path / "existing.json"
    loaded = {"state": "WAITING_FOR_APPROVAL"}
    calls: list[str] = []

    class NoopLock:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(publication, "request_lock", lambda: NoopLock())
    monkeypatch.setattr(
        publication, "load_publication_items", lambda *_args, **_kwargs: articles
    )
    monkeypatch.setattr(publication, "_receipt_path", lambda _articles: path)
    monkeypatch.setattr(publication, "_read_receipt", lambda _path: loaded)

    def resume(
        source_articles: list[Any],
        receipt: dict[str, object],
        receipt_path: Path,
        **_kwargs: object,
    ) -> bool:
        assert source_articles == articles
        assert receipt is loaded
        assert receipt_path == path
        calls.append("resume")
        return True

    monkeypatch.setattr(publication, "_resume_existing_all_attempt", resume)

    def activation_receipt(_path: Path | None, **_kwargs: object) -> object:
        calls.append("activation-receipt")
        return SimpleNamespace(production_fixture_root=publication.SOURCE_FIXTURE_ROOT)

    monkeypatch.setattr(
        publication,
        "validate_rakuten_activation_dry_run",
        activation_receipt,
    )
    monkeypatch.setattr(
        publication,
        "validate_measurement_plugin_apply_receipt",
        lambda _path: calls.append("plugin-receipt"),
    )

    result = publication.execute(
        "all",
        quality_audit_attestation=_quality_input_paths(tmp_path)[0],
        quality_audit_signature=_quality_input_paths(tmp_path)[1],
        portfolio_refresh=lambda: calls.append("refresh"),
    )

    assert result == path
    assert calls == ["activation-receipt", "plugin-receipt", "resume"]


def test_all_mode_requires_activation_before_any_lock_plugin_or_provider_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    monkeypatch.setattr(
        publication,
        "validate_measurement_plugin_apply_receipt",
        lambda _path: events.append("plugin"),
    )
    monkeypatch.setattr(
        publication,
        "request_lock",
        lambda: (_ for _ in ()).throw(AssertionError("lock must not be created")),
    )

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_RAKUTEN_ACTIVATION_REQUIRED",
    ):
        publication.execute(
            "all",
            portfolio_refresh=lambda: events.append("provider"),
            preview=lambda: events.append("preview"),
        )

    assert events == []


def test_all_mode_requires_signed_quality_audit_pair_before_lock_or_provider_action(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events: list[str] = []
    activation_path = (tmp_path / "activation.json").resolve()
    plugin_path = (tmp_path / "plugin-receipt.json").resolve()
    attestation_path, _signature_path = _quality_input_paths(tmp_path)
    monkeypatch.setattr(
        publication,
        "validate_rakuten_activation_dry_run",
        lambda *_args, **_kwargs: events.append("activation") or SimpleNamespace(),
    )
    monkeypatch.setattr(
        publication,
        "validate_measurement_plugin_apply_receipt",
        lambda *_args, **_kwargs: events.append("plugin"),
    )
    monkeypatch.setattr(
        publication,
        "request_lock",
        lambda: (_ for _ in ()).throw(AssertionError("lock must not be created")),
    )

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_QUALITY_AUDIT_ATTESTATION_REQUIRED",
    ):
        publication.execute(
            "all",
            measurement_plugin_apply_receipt=plugin_path,
            rakuten_activation_dry_run=activation_path,
            quality_audit_attestation=attestation_path,
            portfolio_refresh=lambda: events.append("provider"),
            preview=lambda: events.append("preview"),
        )

    assert events == ["activation", "plugin"]


def test_all_mode_preview_revalidates_activation_as_recent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events: list[str] = []
    activation_path = (tmp_path / "activation.json").resolve()
    plugin_path = (tmp_path / "plugin.json").resolve()
    quality_attestation, quality_signature = _quality_input_paths(tmp_path)
    activation = SimpleNamespace(
        local_fixture_root=publication.SOURCE_FIXTURE_ROOT,
        production_fixture_root=publication.SOURCE_FIXTURE_ROOT,
    )

    def activation_receipt(*_args: object, **kwargs: object) -> object:
        events.append(f"activation:{kwargs.get('require_recent')}")
        return activation

    class NoopLock:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(
        publication,
        "validate_rakuten_activation_dry_run",
        activation_receipt,
    )
    monkeypatch.setattr(
        publication,
        "validate_measurement_plugin_apply_receipt",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(publication, "request_lock", lambda: NoopLock())
    monkeypatch.setattr(
        publication,
        "_receipt_path",
        lambda _articles: (tmp_path / "request.json").resolve(),
    )
    monkeypatch.setattr(publication, "_read_receipt", lambda _path: None)
    monkeypatch.setattr(
        publication,
        "activation_materialization_binding",
        lambda *_args, **kwargs: (
            events.append(f"binding:{kwargs.get('require_recent')}") or None
        ),
    )
    monkeypatch.setattr(
        publication,
        "strict_local_quality_audit",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            publication.PublicationFailure("QUALITY_GATE_TEST_STOP")
        ),
    )

    with pytest.raises(publication.PublicationFailure, match="QUALITY_GATE_TEST_STOP"):
        publication.execute(
            "all",
            measurement_plugin_apply_receipt=plugin_path,
            rakuten_activation_dry_run=activation_path,
            quality_audit_attestation=quality_attestation,
            quality_audit_signature=quality_signature,
            preview=lambda: events.append("preview"),
            client_factory=lambda: (_ for _ in ()).throw(
                AssertionError("quality gate must precede WordPress client")
            ),
        )

    assert events == [
        "activation:False",
        "binding:True",
        "preview",
        "activation:True",
        "binding:True",
    ]


def test_parser_accepts_exact_owner_private_quality_attestation_paths(
    tmp_path: Path,
) -> None:
    attestation_path, signature_path = _quality_input_paths(tmp_path)
    arguments = publication.parser().parse_args(
        [
            "--quality-audit-attestation",
            os.fspath(attestation_path),
            "--quality-audit-signature",
            os.fspath(signature_path),
        ]
    )
    assert arguments.quality_audit_attestation == attestation_path
    assert arguments.quality_audit_signature == signature_path


def test_partial_selection_fails_before_activation_lock_or_other_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    parser = publication._PublicPageEvidenceParser()
    parser.feed(article.block_markup)
    parser.close()
    ctas = publication._validated_ctas(parser)
    assert ctas
    assert all(
        publication.urlsplit(str(cta["href"])).hostname != "hb.afl.rakuten.co.jp"
        and cta["cta_id"] is None
        and cta["snapshot_id"] is None
        and cta["offer_id"] is None
        and cta["rakuten_measurement_id"] is None
        for cta in ctas
    )
    events: list[str] = []
    monkeypatch.setattr(
        publication,
        "validate_rakuten_activation_dry_run",
        lambda *_args, **_kwargs: events.append("activation"),
    )
    monkeypatch.setattr(
        publication,
        "request_lock",
        lambda: events.append("lock"),
    )
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_COMPLETE_PORTFOLIO_REQUIRED",
    ):
        publication.execute(
            article.production_slug,
            portfolio_refresh=lambda: events.append("provider"),
            preview=lambda: events.append("preview"),
        )

    assert events == []
    # Read-only local selection remains useful for inspection; only production
    # execution is all-or-nothing.
    assert publication.load_publication_items(article.production_slug) == [article]


def test_all_mode_requires_exact_separate_admin_measurement_plugin_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _private_path(monkeypatch, tmp_path)
    manifest = json.loads(
        publication.MEASUREMENT_PLUGIN_MANIFEST_PATH.read_text(encoding="utf-8")
    )
    package_sha256 = manifest["package_sha256"]
    file_manifest_sha256 = hashlib.sha256(
        publication.canonical_json_bytes(manifest["plugin_files"])
    ).hexdigest()
    proposal_path = (
        publication.PRIVATE_REQUEST_DIRECTORY / "measurement-plugin-proposal-v3.json"
    )
    apply_path = publication.PRIVATE_REQUEST_DIRECTORY / "plugin-applied.json"
    proposal = {
        "schema": "RAOS_MEASUREMENT_PLUGIN_PROPOSAL_RECEIPT_V3",
        "state": "WAITING_FOR_SEPARATE_ADMIN_PLUGIN_APPROVAL",
        "artifact_id": "raos-editorial-measurement-v1",
        "plugin_slug": "raos-editorial-measurement",
        "plugin_version": "1.0.0",
        "package_sha256": package_sha256,
        "file_manifest_sha256": file_manifest_sha256,
        "measurement_gate_default_off": True,
        "proposal": {
            "proposal_id": "a" * 64,
            "operation_id": "b" * 64,
            "after_sha256": file_manifest_sha256,
        },
    }
    applied = {
        "schema": "OperationReceiptV1",
        "proposal_id": "a" * 64,
        "operation_id": "b" * 64,
        "state": "APPLIED",
        "result_code": "PLUGIN_CHANGE_APPLIED",
        "after_sha256": file_manifest_sha256,
    }
    publication._atomic_receipt(proposal_path, proposal)
    publication._atomic_receipt(apply_path, applied)

    publication.validate_measurement_plugin_apply_receipt(apply_path.resolve())

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_MEASUREMENT_PLUGIN_RECEIPT_REQUIRED",
    ):
        publication.validate_measurement_plugin_apply_receipt(None)
    applied["state"] = "APPROVED"
    publication._atomic_receipt(apply_path, applied)
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_MEASUREMENT_PLUGIN_RECEIPT_INVALID",
    ):
        publication.validate_measurement_plugin_apply_receipt(apply_path.resolve())

    applied["state"] = "APPLIED"
    publication._atomic_receipt(apply_path, applied)
    proposal["package_sha256"] = "0" * 64
    publication._atomic_receipt(proposal_path, proposal)
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_MEASUREMENT_PLUGIN_RECEIPT_INVALID",
    ):
        publication.validate_measurement_plugin_apply_receipt(apply_path.resolve())


def test_all_mode_applied_receipt_cannot_short_circuit_fresh_capture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles = publication.load_articles("all")
    path = tmp_path / "applied.json"
    receipt = publication._fresh_receipt(
        articles,
        path,
        TEST_THEME_TREE_SHA256,
        quality_audit_binding=_test_quality_audit_binding(),
    )
    receipt["state"] = "APPLIED"
    remote_status_called = False

    def remote_status(*_args: object, **_kwargs: object) -> dict[str, object]:
        nonlocal remote_status_called
        remote_status_called = True
        raise AssertionError("terminal receipt must not be resumed before refresh")

    monkeypatch.setattr(publication, "publication_batch_status", remote_status)

    assert (
        publication._resume_existing_all_attempt(
            articles,
            receipt,
            path,
            client_factory=lambda: (_ for _ in ()).throw(AssertionError()),
            deployment_runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError()
            ),
        )
        is False
    )
    assert remote_status_called is False


def test_all_mode_exact_nonterminal_receipt_remains_recoverable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles = publication.load_publication_items("all")
    current_binding = {"schema": "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V3"}
    path = tmp_path / "waiting.json"
    receipt = publication._fresh_receipt(
        articles,
        path,
        TEST_THEME_TREE_SHA256,
        current_binding,
        quality_audit_binding=_test_quality_audit_binding(),
    )
    receipt["state"] = "WAITING_FOR_APPROVAL"
    receipt["proposals"] = [
        {"proposal_id": f"{index + 1:064x}"} for index in range(len(articles))
    ]
    receipt["batch_registration"] = {}
    calls: list[str] = []

    class ResumeClient:
        def initialize(self) -> None:
            calls.append("initialize")

        def tools(self) -> list[dict[str, object]]:
            return []

        def call(self, name: str, _arguments: dict[str, object]) -> dict[str, object]:
            assert name == "raos-codex-site-status"
            calls.append("site-status")
            return {}

    monkeypatch.setattr(
        publication,
        "publication_batch_status",
        lambda *_args, **_kwargs: {"state": "APPROVED"},
    )
    monkeypatch.setattr(
        publication,
        "load_publication_items",
        lambda *_args, **_kwargs: articles,
    )
    monkeypatch.setattr(
        publication,
        "activation_materialization_binding",
        lambda *_args, **_kwargs: current_binding,
    )
    monkeypatch.setattr(
        publication,
        "_validate_receipt",
        lambda value, _articles: value,
    )
    activation = SimpleNamespace(
        production_fixture_root=publication.SOURCE_FIXTURE_ROOT,
    )
    monkeypatch.setattr(
        publication,
        "validate_rakuten_activation_dry_run",
        lambda *_args, **kwargs: (
            calls.append(f"activation-recent:{kwargs.get('require_recent')}")
            or activation
        ),
    )
    monkeypatch.setattr(
        publication,
        "strict_local_quality_audit",
        lambda *_args, **_kwargs: (
            calls.append("signed-quality") or _test_quality_audit_binding()
        ),
    )
    monkeypatch.setattr(publication, "validate_tool_contract", lambda _value: None)
    monkeypatch.setattr(
        publication, "validate_site_status", lambda _value, **_kwargs: None
    )
    monkeypatch.setattr(
        publication,
        "read_content_operations",
        lambda *_args: calls.append("operations") or {"a" * 64: {"state": "APPLIED"}},
    )
    monkeypatch.setattr(
        publication,
        "wait_and_apply",
        lambda *_args, **kwargs: calls.append(
            f"apply:{kwargs.get('finalize_applied')}"
        ),
    )
    monkeypatch.setattr(publication, "_published_document_evidence", lambda *_args: {})
    monkeypatch.setattr(
        publication, "_touch_receipt", lambda *_args: calls.append("touch")
    )

    assert (
        publication._resume_existing_all_attempt(
            articles,
            receipt,
            path,
            activation=activation,
            **_resume_gate_kwargs(tmp_path),
            client_factory=ResumeClient,
            deployment_runner=lambda *_args, **_kwargs: subprocess.CompletedProcess(
                [], 0, b"", b""
            ),
        )
        is False
    )
    assert calls == [
        "activation-recent:True",
        "signed-quality",
        "initialize",
        "site-status",
        "operations",
        "apply:False",
        "operations",
        "touch",
    ]


@pytest.mark.parametrize(
    "remote_state",
    ["REGISTERED", "WAITING_FOR_APPROVAL", "APPROVED", "APPLYING"],
)
def test_provider_slot_resume_rejects_historical_activation_binding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    remote_state: str,
) -> None:
    articles = publication.load_publication_items("all")
    receipt = publication._fresh_receipt(
        articles,
        tmp_path / "historical-v2.json",
        TEST_THEME_TREE_SHA256,
        {"schema": "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V2"},
        _test_quality_audit_binding(),
    )
    receipt["state"] = "WAITING_FOR_APPROVAL"
    receipt["proposals"] = [
        {"proposal_id": f"{index + 1:064x}"} for index in range(len(articles))
    ]
    receipt["batch_registration"] = {}
    monkeypatch.setattr(
        publication, "_validate_receipt", lambda value, _articles: value
    )
    monkeypatch.setattr(
        publication,
        "publication_batch_status",
        lambda *_args, **_kwargs: {"state": remote_state},
    )

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PENDING_REQUEST_CONFLICT",
    ):
        publication._resume_existing_all_attempt(
            articles,
            receipt,
            tmp_path / "historical-v2.json",
            activation=SimpleNamespace(),
            **_resume_gate_kwargs(tmp_path),
            client_factory=lambda: (_ for _ in ()).throw(
                AssertionError("historical proposal must not reach WordPress")
            ),
            deployment_runner=lambda *_args, **_kwargs: subprocess.CompletedProcess(
                [], 0, b"", b""
            ),
        )


@pytest.mark.parametrize(
    "historical_schema",
    [
        "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V1",
        "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V2",
    ],
)
def test_provider_slot_resume_allows_only_expired_historical_replacement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    historical_schema: str,
) -> None:
    articles = publication.load_publication_items("all")
    path = tmp_path / f"expired-{historical_schema[-2:].lower()}.json"
    receipt = publication._fresh_receipt(
        articles,
        path,
        TEST_THEME_TREE_SHA256,
        {"schema": historical_schema},
        _test_quality_audit_binding(),
    )
    receipt["state"] = "WAITING_FOR_APPROVAL"
    receipt["proposals"] = [
        {"proposal_id": f"{index + 1:064x}"} for index in range(len(articles))
    ]
    receipt["batch_registration"] = {}
    monkeypatch.setattr(
        publication, "_validate_receipt", lambda value, _articles: value
    )
    monkeypatch.setattr(
        publication,
        "publication_batch_status",
        lambda *_args, **_kwargs: {"state": "EXPIRED"},
    )

    assert (
        publication._resume_existing_all_attempt(
            articles,
            receipt,
            path,
            activation=SimpleNamespace(),
            **_resume_gate_kwargs(tmp_path),
            client_factory=lambda: (_ for _ in ()).throw(
                AssertionError("expired historical attempt must not call WordPress")
            ),
            deployment_runner=lambda *_args, **_kwargs: subprocess.CompletedProcess(
                [], 0, b"", b""
            ),
        )
        is False
    )


def test_unregistered_current_provider_binding_cannot_register_after_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles = publication.load_publication_items("all")
    captured = {"schema": "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V3", "x": "a"}
    current = {"schema": "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V3", "x": "b"}
    receipt = publication._fresh_receipt(
        articles,
        tmp_path / "unregistered-v3.json",
        TEST_THEME_TREE_SHA256,
        captured,
        _test_quality_audit_binding(),
    )
    monkeypatch.setattr(
        publication,
        "_unregistered_proposal_set_ready",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        publication,
        "register_publication_batch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("drifted provider binding must not register")
        ),
    )

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_UNREGISTERED_BATCH_HANDOFF_REQUIRED",
    ):
        publication._register_unregistered_proposal_set(
            object(),
            receipt,
            tmp_path / "unregistered-v3.json",
            articles=articles,
            desired_theme_tree_sha256=TEST_THEME_TREE_SHA256,
            activation=SimpleNamespace(),
            materialization_binding=current,
            quality_audit_binding=_test_quality_audit_binding(),
        )


def test_unregistered_historical_provider_binding_fails_closed_while_nonterminal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles = publication.load_publication_items("all")
    proposal_ids = [f"{index + 1:064x}" for index in range(len(articles))]
    receipt = publication._fresh_receipt(
        articles,
        tmp_path / "unregistered-v2.json",
        TEST_THEME_TREE_SHA256,
        {"schema": "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V2"},
        _test_quality_audit_binding(),
    )
    receipt["proposals"] = [
        {"kind": "CONTENT_RELEASE", "proposal_id": proposal_id}
        for proposal_id in proposal_ids
    ]
    receipt["baselines"] = {}
    receipt["drafts"] = {}
    monkeypatch.setattr(
        publication,
        "_unregistered_proposal_set_ready",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(publication, "_proposal_ids", lambda _receipt: proposal_ids)
    monkeypatch.setattr(
        publication,
        "read_content_operations",
        lambda *_args, **_kwargs: {
            proposal_id: {"state": "APPROVED"} for proposal_id in proposal_ids
        },
    )
    monkeypatch.setattr(
        publication,
        "register_publication_batch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("historical proposal must not register")
        ),
    )

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PENDING_REQUEST_CONFLICT",
    ):
        publication._register_unregistered_proposal_set(
            object(),
            receipt,
            tmp_path / "unregistered-v2.json",
            articles=articles,
            desired_theme_tree_sha256=TEST_THEME_TREE_SHA256,
            activation=SimpleNamespace(),
            materialization_binding={
                "schema": "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V3"
            },
            quality_audit_binding=_test_quality_audit_binding(),
        )


def test_all_mode_resume_refuses_stale_activation_before_client_or_apply(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles = publication.load_publication_items("all")
    path = tmp_path / "waiting-stale.json"
    receipt = publication._fresh_receipt(
        articles,
        path,
        TEST_THEME_TREE_SHA256,
        quality_audit_binding=_test_quality_audit_binding(),
    )
    receipt["state"] = "WAITING_FOR_APPROVAL"
    receipt["proposals"] = [
        {"proposal_id": f"{index + 1:064x}"} for index in range(len(articles))
    ]
    receipt["batch_registration"] = {}
    monkeypatch.setattr(
        publication,
        "publication_batch_status",
        lambda *_args, **_kwargs: {"state": "APPROVED"},
    )

    def stale(*_args: object, **kwargs: object) -> object:
        assert kwargs == {"require_recent": True}
        raise publication.PublicationFailure(
            "RAOS_WORDPRESS_REQUEST_RAKUTEN_ACTIVATION_INVALID"
        )

    monkeypatch.setattr(publication, "validate_rakuten_activation_dry_run", stale)
    monkeypatch.setattr(
        publication,
        "wait_and_apply",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("stale activation must prevent apply")
        ),
    )

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_RAKUTEN_ACTIVATION_INVALID",
    ):
        publication._resume_existing_all_attempt(
            articles,
            receipt,
            path,
            **_resume_gate_kwargs(tmp_path),
            client_factory=lambda: (_ for _ in ()).throw(
                AssertionError("client must not initialize")
            ),
            deployment_runner=lambda *_args, **_kwargs: subprocess.CompletedProcess(
                [], 0, b"", b""
            ),
        )


def test_all_mode_resume_refuses_signed_quality_fingerprint_drift_before_apply(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles = publication.load_publication_items("all")
    path = tmp_path / "waiting-quality-drift.json"
    receipt = publication._fresh_receipt(
        articles,
        path,
        TEST_THEME_TREE_SHA256,
        quality_audit_binding=_test_quality_audit_binding(),
    )
    receipt["state"] = "WAITING_FOR_APPROVAL"
    receipt["proposals"] = [
        {"proposal_id": f"{index + 1:064x}"} for index in range(len(articles))
    ]
    receipt["batch_registration"] = {}
    activation = SimpleNamespace(
        production_fixture_root=publication.SOURCE_FIXTURE_ROOT,
    )
    monkeypatch.setattr(
        publication,
        "publication_batch_status",
        lambda *_args, **_kwargs: {"state": "APPROVED"},
    )
    monkeypatch.setattr(
        publication,
        "validate_rakuten_activation_dry_run",
        lambda *_args, **_kwargs: activation,
    )
    monkeypatch.setattr(
        publication,
        "activation_materialization_binding",
        lambda *_args, **_kwargs: None,
    )
    drifted_quality = _test_quality_audit_binding()
    drifted_quality["fingerprint_bundle_sha256"] = "f" * 64
    monkeypatch.setattr(
        publication,
        "strict_local_quality_audit",
        lambda *_args, **_kwargs: drifted_quality,
    )
    monkeypatch.setattr(
        publication,
        "wait_and_apply",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("quality drift must prevent apply")
        ),
    )

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PENDING_REQUEST_CONFLICT",
    ):
        publication._resume_existing_all_attempt(
            articles,
            receipt,
            path,
            activation=activation,
            **_resume_gate_kwargs(tmp_path),
            client_factory=lambda: (_ for _ in ()).throw(
                AssertionError("client must not initialize")
            ),
            deployment_runner=lambda *_args, **_kwargs: subprocess.CompletedProcess(
                [], 0, b"", b""
            ),
        )


def _write_remote_applied_legacy_all_attempt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    interrupted_state: str = "APPLY_RETURNED",
) -> tuple[
    list[Any],
    Path,
    str,
    dict[str, dict[str, object]],
    dict[str, dict[str, object]],
    dict[str, dict[str, object]],
]:
    articles = publication.load_publication_items("all")
    path = _private_path(monkeypatch, tmp_path)
    old_tree = TEST_THEME_TREE_SHA256
    receipt = publication._fresh_receipt(
        articles,
        path,
        old_tree,
        quality_audit_binding=_test_quality_audit_binding(),
    )
    assert interrupted_state in {"APPLY_RETURNED", "FINALIZING_APPLIED"}
    receipt["state"] = interrupted_state
    content_proposals: list[dict[str, object]] = []
    operations: dict[str, dict[str, object]] = {}
    documents: dict[str, dict[str, object]] = {}
    drafts: dict[str, dict[str, object]] = {}
    for index, article in enumerate(articles, start=1):
        proposal_id = f"{index:064x}"
        post_id = 1000 + index
        after_sha256 = publication._content_after_sha256(article.document(), post_id)
        content_proposals.append(
            {
                "kind": "CONTENT_RELEASE",
                "slug": article.production_slug,
                "post_type": article.post_type,
                "proposal_id": proposal_id,
                "after_sha256": after_sha256,
                "expires_at_gmt": "2099-08-29T00:15:00Z",
                "idempotency_key": f"{index + 20:064x}",
            }
        )
        drafts[article.production_slug] = {
            "id": post_id,
            "content_sha256": after_sha256,
        }
        documents[article.production_slug] = {
            "id": post_id,
            "slug": article.production_slug,
            "status": "publish",
            "content_sha256": after_sha256,
            "revision_id": post_id,
            "modified_gmt": "2026-08-29T00:00:00Z",
        }
        if article.post_type == "page":
            documents[article.production_slug]["post_type"] = "page"
        operations[proposal_id] = {
            "schema": "OperationReceiptV1",
            "proposal_id": proposal_id,
            "operation_id": proposal_id,
            "state": "APPLIED",
            "result_code": "CONTENT_RELEASE_APPLIED",
            "before_sha256": after_sha256,
            "after_sha256": after_sha256,
            "audit_id": f"{index + 40:064x}",
        }
    theme_proposal_id = "f" * 64
    receipt["proposals"] = [
        *content_proposals,
        {
            "kind": "THEME_RELEASE",
            "slug": None,
            "proposal_id": theme_proposal_id,
            "after_sha256": old_tree,
            "expires_at_gmt": "2099-08-29T00:15:00Z",
            "idempotency_key": "e" * 64,
        },
    ]
    receipt["operation_ids"] = {
        str(proposal["proposal_id"]): str(proposal["proposal_id"])
        for proposal in receipt["proposals"]
    }
    receipt["batch_registration"] = {}
    receipt["drafts"] = drafts
    publication._atomic_receipt(path, receipt)
    activation = SimpleNamespace(
        local_fixture_root=publication.SOURCE_FIXTURE_ROOT,
        production_fixture_root=publication.SOURCE_FIXTURE_ROOT,
    )
    monkeypatch.setattr(
        publication,
        "validate_rakuten_activation_dry_run",
        lambda *_args, **_kwargs: activation,
    )
    monkeypatch.setattr(
        publication,
        "activation_materialization_binding",
        lambda *_args, **_kwargs: None,
    )
    return articles, path, old_tree, operations, documents, drafts


def _stub_required_all_mode_activation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path]:
    activation_path = (tmp_path / "activation-dry-run-v2.json").resolve()
    plugin_receipt_path = (tmp_path / "measurement-plugin-applied.json").resolve()
    activation = SimpleNamespace(
        local_fixture_root=publication.SOURCE_FIXTURE_ROOT,
        production_fixture_root=publication.SOURCE_FIXTURE_ROOT,
    )
    monkeypatch.setattr(
        publication,
        "validate_rakuten_activation_dry_run",
        lambda *_args, **_kwargs: activation,
    )
    monkeypatch.setattr(
        publication,
        "validate_measurement_plugin_apply_receipt",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        publication,
        "activation_materialization_binding",
        lambda *_args, **_kwargs: None,
    )
    quality_attestation_path, quality_signature_path = _quality_input_paths(tmp_path)
    return (
        activation_path,
        plugin_receipt_path,
        quality_attestation_path,
        quality_signature_path,
    )


@pytest.mark.parametrize(
    "interrupted_state",
    ["APPLY_RETURNED", "FINALIZING_APPLIED"],
)
def test_all_mode_remote_applied_reconciliation_revalidates_fresh_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    interrupted_state: str,
) -> None:
    articles, path, _old_tree, operations, documents, _drafts = (
        _write_remote_applied_legacy_all_attempt(
            monkeypatch,
            tmp_path,
            interrupted_state=interrupted_state,
        )
    )
    live_documents = {
        article.production_slug: article.document()
        | {"schema": "ContentDocumentV1"}
        | documents[article.production_slug]
        for article in articles
    }
    lifecycle: list[str] = []

    class Client:
        def initialize(self) -> None:
            lifecycle.append("initialize")

        def tools(self) -> dict[str, object]:
            return {}

        def call(
            self,
            name: str,
            arguments: dict[str, object],
        ) -> dict[str, object]:
            if name == "raos-codex-site-status":
                lifecycle.append("site-status")
                return {}
            assert name == "raos-codex-content-get"
            post_id = arguments.get("id")
            return next(
                document
                for document in live_documents.values()
                if document["id"] == post_id
            )

    monkeypatch.setattr(
        publication,
        "publication_batch_status",
        lambda *_args, **_kwargs: {
            "state": "APPLIED",
            "preconditions_ready": True,
        },
    )
    monkeypatch.setattr(publication, "validate_tool_contract", lambda _tools: None)
    monkeypatch.setattr(
        publication,
        "validate_site_status",
        lambda _status, **_kwargs: None,
    )

    def operation_readback(*_args: object) -> dict[str, dict[str, object]]:
        lifecycle.append("operations")
        return operations

    monkeypatch.setattr(publication, "read_content_operations", operation_readback)

    def finalize(*_args: object, **kwargs: object) -> None:
        assert kwargs == {"finalize_applied": True}
        lifecycle.append("finalize")

    monkeypatch.setattr(publication, "wait_and_apply", finalize)
    receipt = json.loads(path.read_text(encoding="utf-8"))

    assert (
        publication._resume_existing_all_attempt(
            articles,
            receipt,
            path,
            **_resume_gate_kwargs(tmp_path),
            client_factory=Client,
            deployment_runner=lambda *_args, **_kwargs: subprocess.CompletedProcess(
                [], 0, b"", b""
            ),
        )
        is False
    )

    assert lifecycle == [
        "initialize",
        "site-status",
        "operations",
        "finalize",
        "operations",
    ]
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["state"] == "APPLIED"
    assert stored["prior_applied_reconciliation"] == {
        "schema": "RAOS_WORDPRESS_PRIOR_APPLIED_RECONCILIATION_V1",
        "captured_at_gmt": stored["prior_applied_reconciliation"]["captured_at_gmt"],
        "documents": documents,
        "operations": operations,
    }


def test_all_mode_remote_applied_reconciliation_requires_ready_preconditions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles, path, _old_tree, _operations, _documents, _drafts = (
        _write_remote_applied_legacy_all_attempt(monkeypatch, tmp_path)
    )

    class Client:
        def __init__(self) -> None:
            raise AssertionError(
                "MCP client must not initialize after precondition drift"
            )

    monkeypatch.setattr(
        publication,
        "publication_batch_status",
        lambda *_args, **_kwargs: {
            "state": "APPLIED",
            "preconditions_ready": False,
        },
    )
    receipt = json.loads(path.read_text(encoding="utf-8"))

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_BATCH_STATUS_INVALID",
    ):
        publication._resume_existing_all_attempt(
            articles,
            receipt,
            path,
            **_resume_gate_kwargs(tmp_path),
            client_factory=Client,
            deployment_runner=lambda *_args, **_kwargs: subprocess.CompletedProcess(
                [], 0, b"", b""
            ),
        )

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["state"] == "APPLY_RETURNED"
    assert stored["prior_applied_reconciliation"] is None


def test_all_mode_remote_applied_reconciliation_rechecks_preconditions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles, path, _old_tree, operations, documents, _drafts = (
        _write_remote_applied_legacy_all_attempt(monkeypatch, tmp_path)
    )
    statuses = iter(
        (
            {"state": "APPLIED", "preconditions_ready": True},
            {"state": "APPLIED", "preconditions_ready": False},
        )
    )

    class Client:
        def initialize(self) -> None:
            return None

        def tools(self) -> dict[str, object]:
            return {}

        def call(self, name: str, _arguments: dict[str, object]) -> dict[str, object]:
            assert name == "raos-codex-site-status"
            return {}

    monkeypatch.setattr(
        publication,
        "publication_batch_status",
        lambda *_args, **_kwargs: next(statuses),
    )
    monkeypatch.setattr(publication, "validate_tool_contract", lambda _tools: None)
    monkeypatch.setattr(
        publication,
        "validate_site_status",
        lambda _status, **_kwargs: None,
    )
    monkeypatch.setattr(
        publication,
        "read_content_operations",
        lambda *_args: operations,
    )
    monkeypatch.setattr(publication, "wait_and_apply", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        publication,
        "_published_receipt_document_evidence",
        lambda *_args: documents,
    )
    receipt = json.loads(path.read_text(encoding="utf-8"))

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_BATCH_STATUS_INVALID",
    ):
        publication._resume_existing_all_attempt(
            articles,
            receipt,
            path,
            **_resume_gate_kwargs(tmp_path),
            client_factory=Client,
            deployment_runner=lambda *_args, **_kwargs: subprocess.CompletedProcess(
                [], 0, b"", b""
            ),
        )

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["state"] == "APPLY_RETURNED"
    assert stored["prior_applied_reconciliation"] is None


def test_all_mode_remote_applied_reconciliation_refuses_live_hash_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles, path, _old_tree, operations, documents, _drafts = (
        _write_remote_applied_legacy_all_attempt(monkeypatch, tmp_path)
    )
    live_documents = {
        article.production_slug: article.document()
        | {"schema": "ContentDocumentV1"}
        | documents[article.production_slug]
        for article in articles
    }
    changed_slug = articles[0].production_slug
    live_documents[changed_slug]["block_markup"] += "<!-- production drift -->"
    finalized = False

    class Client:
        def initialize(self) -> None:
            return None

        def tools(self) -> dict[str, object]:
            return {}

        def call(
            self,
            name: str,
            arguments: dict[str, object],
        ) -> dict[str, object]:
            if name == "raos-codex-site-status":
                return {}
            assert name == "raos-codex-content-get"
            post_id = arguments.get("id")
            return next(
                document
                for document in live_documents.values()
                if document["id"] == post_id
            )

    monkeypatch.setattr(
        publication,
        "publication_batch_status",
        lambda *_args, **_kwargs: {
            "state": "APPLIED",
            "preconditions_ready": True,
        },
    )
    monkeypatch.setattr(publication, "validate_tool_contract", lambda _tools: None)
    monkeypatch.setattr(
        publication,
        "validate_site_status",
        lambda _status, **_kwargs: None,
    )
    monkeypatch.setattr(
        publication,
        "read_content_operations",
        lambda *_args: operations,
    )

    def finalize(*_args: object, **kwargs: object) -> None:
        nonlocal finalized
        assert kwargs == {"finalize_applied": True}
        finalized = True

    monkeypatch.setattr(publication, "wait_and_apply", finalize)
    receipt = json.loads(path.read_text(encoding="utf-8"))

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLISH_READBACK_FAILED",
    ):
        publication._resume_existing_all_attempt(
            articles,
            receipt,
            path,
            **_resume_gate_kwargs(tmp_path),
            client_factory=Client,
            deployment_runner=lambda *_args, **_kwargs: subprocess.CompletedProcess(
                [], 0, b"", b""
            ),
        )

    assert finalized is True
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["state"] == "APPLY_RETURNED"
    assert stored["prior_applied_reconciliation"] is None


@pytest.mark.parametrize("replacement_preconditions_ready", [True, False])
def test_all_mode_remote_applied_legacy_attempt_checks_replacement_preconditions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    replacement_preconditions_ready: bool,
) -> None:
    articles, path, old_tree, operations, documents, drafts = (
        _write_remote_applied_legacy_all_attempt(monkeypatch, tmp_path)
    )
    (
        activation_path,
        plugin_receipt_path,
        quality_attestation_path,
        quality_signature_path,
    ) = _stub_required_all_mode_activation(monkeypatch, tmp_path)

    class Client:
        def initialize(self) -> None:
            return None

        def tools(self) -> dict[str, object]:
            return {}

        def call(self, name: str, _arguments: dict[str, object]) -> dict[str, object]:
            assert name == "raos-codex-site-status"
            return {"theme": {}}

    calls: list[str] = []
    status_calls = 0
    replacement_count = 0
    replacement_includes_theme = False

    def tracked_tree() -> str:
        # The old tree is bound by the immutable applied receipt and deployment
        # readback; fresh-cycle source checks must observe one stable new tree.
        return "2" * 64

    monkeypatch.setattr(publication, "tracked_theme_tree_sha256", tracked_tree)

    class NoopLock:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(publication, "request_lock", lambda: NoopLock())
    monkeypatch.setattr(publication, "_receipt_path", lambda _articles: path)
    monkeypatch.setattr(
        publication,
        "load_publication_items",
        lambda *_args, **_kwargs: articles,
    )
    monkeypatch.setattr(publication, "validate_tool_contract", lambda _tools: None)
    monkeypatch.setattr(
        publication,
        "validate_site_status",
        lambda _status, **_kwargs: None,
    )

    def batch_status(*_args: object, **_kwargs: object) -> dict[str, object]:
        nonlocal status_calls
        status_calls += 1
        return {
            "state": "APPLIED",
            "preconditions_ready": (
                replacement_preconditions_ready if status_calls == 3 else True
            ),
        }

    monkeypatch.setattr(publication, "publication_batch_status", batch_status)
    monkeypatch.setattr(
        publication,
        "read_content_operations",
        lambda *_args: operations,
    )
    monkeypatch.setattr(
        publication,
        "_published_receipt_document_evidence",
        lambda *_args: documents,
    )
    monkeypatch.setattr(
        publication,
        "list_all_documents",
        lambda _client, **_kwargs: [],
    )
    monkeypatch.setattr(
        publication,
        "capture_existing_baselines",
        lambda _client, _articles, listed, *_args, **_kwargs: listed,
    )
    monkeypatch.setattr(
        publication,
        "deployment_status",
        lambda *_args, **_kwargs: {
            "theme": {
                "tree_sha256": old_tree,
                "version": "1.3.9",
                "runtime_version": "1.3.9",
                "runtime_revision": None,
            }
        },
    )
    monkeypatch.setattr(
        publication,
        "reconcile_drafts",
        lambda *_args, **_kwargs: drafts,
    )

    def create_proposals(
        _client: object,
        selected: list[Any],
        _drafts: dict[str, object],
        include_theme: bool,
        stored: dict[str, object],
        *_args: object,
    ) -> list[dict[str, object]]:
        nonlocal replacement_count, replacement_includes_theme
        replacement_count = len(selected) + (1 if include_theme else 0)
        replacement_includes_theme = include_theme
        assert stored["state"] == "APPLIED_ATTEMPT_REPLACED"
        assert stored["prior_applied_reconciliation"] is not None
        return [{} for _ in range(replacement_count)]

    monkeypatch.setattr(publication, "create_proposals", create_proposals)
    monkeypatch.setattr(
        publication,
        "register_publication_batch",
        lambda *_args: calls.append("registered"),
    )

    def wait_for_batch(*_args: object, **kwargs: object) -> None:
        if kwargs.get("finalize_applied") is True:
            calls.append("finalized-old")
            return
        raise publication.PublicationFailure("WORDPRESS_MCP_RELEASE_WAIT_TIMEOUT")

    monkeypatch.setattr(publication, "wait_and_apply", wait_for_batch)

    with pytest.raises(
        publication.PublicationFailure,
        match=(
            "WORDPRESS_MCP_RELEASE_WAIT_TIMEOUT"
            if replacement_preconditions_ready
            else "RAOS_WORDPRESS_REQUEST_BATCH_STATUS_INVALID"
        ),
    ):
        publication.execute(
            "all",
            measurement_plugin_apply_receipt=plugin_receipt_path,
            rakuten_activation_dry_run=activation_path,
            quality_audit_attestation=quality_attestation_path,
            quality_audit_signature=quality_signature_path,
            portfolio_refresh=lambda: (_ for _ in ()).throw(
                AssertionError("validated activation must not be rematerialized")
            ),
            preview=lambda: calls.append("preview"),
            client_factory=Client,
        )

    assert status_calls == 3
    if replacement_preconditions_ready:
        assert calls == ["finalized-old", "preview", "registered"]
        assert replacement_includes_theme is True
        assert replacement_count == 14
    else:
        assert calls == ["finalized-old", "preview"]
        assert replacement_includes_theme is False
        assert replacement_count == 0


def test_all_mode_applied_recovery_failure_stops_before_fresh_cycle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles, path, _old_tree, operations, _documents, _drafts = (
        _write_remote_applied_legacy_all_attempt(monkeypatch, tmp_path)
    )
    (
        activation_path,
        plugin_receipt_path,
        quality_attestation_path,
        quality_signature_path,
    ) = _stub_required_all_mode_activation(monkeypatch, tmp_path)
    lifecycle: list[str] = []

    class Client:
        def initialize(self) -> None:
            return None

        def tools(self) -> dict[str, object]:
            return {}

        def call(self, name: str, _arguments: dict[str, object]) -> dict[str, object]:
            assert name == "raos-codex-site-status"
            return {"theme": {}}

    monkeypatch.setattr(publication, "_receipt_path", lambda _articles: path)
    monkeypatch.setattr(
        publication,
        "load_publication_items",
        lambda *_args, **_kwargs: articles,
    )
    monkeypatch.setattr(publication, "validate_tool_contract", lambda _tools: None)
    monkeypatch.setattr(
        publication,
        "validate_site_status",
        lambda _status, **_kwargs: None,
    )
    monkeypatch.setattr(
        publication,
        "publication_batch_status",
        lambda *_args, **_kwargs: {
            "state": "APPLIED",
            "preconditions_ready": True,
        },
    )
    monkeypatch.setattr(
        publication,
        "read_content_operations",
        lambda *_args: operations,
    )

    def recovery_failure(
        stored: dict[str, object],
        receipt_path: Path,
        *_args: object,
        **kwargs: object,
    ) -> None:
        assert kwargs == {"finalize_applied": True}
        publication._touch_receipt(receipt_path, stored, "FINALIZING_APPLIED")
        lifecycle.append("recover")
        raise publication.PublicationFailure(
            "RAOS_CODEX_RECOVERY_CLEANUP_INDETERMINATE"
        )

    monkeypatch.setattr(publication, "wait_and_apply", recovery_failure)
    monkeypatch.setattr(
        publication,
        "_published_receipt_document_evidence",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("readback must follow successful recovery")
        ),
    )

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_CODEX_RECOVERY_CLEANUP_INDETERMINATE",
    ):
        publication.execute(
            "all",
            measurement_plugin_apply_receipt=plugin_receipt_path,
            rakuten_activation_dry_run=activation_path,
            quality_audit_attestation=quality_attestation_path,
            quality_audit_signature=quality_signature_path,
            portfolio_refresh=lambda: (_ for _ in ()).throw(
                AssertionError("validated activation must not be rematerialized")
            ),
            preview=lambda: lifecycle.append("preview"),
            client_factory=Client,
        )

    assert lifecycle == ["recover"]
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["state"] == "FINALIZING_APPLIED"
    assert publication._resume_ready(stored, len(articles)) is True


def test_all_mode_refuses_revision_only_drift_after_applied_reconciliation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    articles, path, _old_tree, operations, documents, _drafts = (
        _write_remote_applied_legacy_all_attempt(monkeypatch, tmp_path)
    )
    (
        activation_path,
        plugin_receipt_path,
        quality_attestation_path,
        quality_signature_path,
    ) = _stub_required_all_mode_activation(monkeypatch, tmp_path)
    current_documents = {
        article.production_slug: article.document()
        | {"schema": "ContentDocumentV1"}
        | documents[article.production_slug]
        for article in articles
    }
    lifecycle: list[str] = []
    remote_calls: list[str] = []

    class Client:
        def initialize(self) -> None:
            remote_calls.append("initialize")

        def tools(self) -> dict[str, object]:
            return {}

        def call(
            self,
            name: str,
            arguments: dict[str, object],
        ) -> dict[str, object]:
            remote_calls.append(name)
            if name == "raos-codex-site-status":
                return {"theme": {}}
            if name == "raos-codex-content-list":
                post_type = arguments.get("post_type")
                assert post_type in {"post", "page"}
                assert arguments == {
                    "post_type": post_type,
                    "status": "any",
                    "page": 1,
                    "per_page": publication.LIST_PER_PAGE,
                }
                matching_documents = [
                    document
                    for document in current_documents.values()
                    if document["post_type"] == post_type
                ]
                return {
                    "schema": "ContentDocumentListV1",
                    "page": 1,
                    "per_page": publication.LIST_PER_PAGE,
                    "total": len(matching_documents),
                    "documents": matching_documents,
                }
            if name == "raos-codex-content-get":
                post_id = arguments.get("id")
                return next(
                    document
                    for document in current_documents.values()
                    if document["id"] == post_id
                )
            raise AssertionError(f"unexpected mutation/proposal call: {name}")

    client = Client()
    monkeypatch.setattr(publication, "_receipt_path", lambda _articles: path)
    monkeypatch.setattr(
        publication,
        "load_publication_items",
        lambda *_args, **_kwargs: articles,
    )
    monkeypatch.setattr(publication, "validate_tool_contract", lambda _tools: None)
    monkeypatch.setattr(
        publication,
        "validate_site_status",
        lambda _status, **_kwargs: None,
    )
    monkeypatch.setattr(
        publication,
        "publication_batch_status",
        lambda *_args, **_kwargs: {
            "state": "APPLIED",
            "preconditions_ready": True,
        },
    )
    monkeypatch.setattr(
        publication,
        "read_content_operations",
        lambda *_args: operations,
    )
    monkeypatch.setattr(
        publication,
        "wait_and_apply",
        lambda *_args, **kwargs: lifecycle.append(
            f"finalize:{kwargs.get('finalize_applied')}"
        ),
    )

    def reconciled_documents(*_args: object) -> dict[str, dict[str, object]]:
        lifecycle.append("resume-readback")
        return documents

    monkeypatch.setattr(
        publication,
        "_published_receipt_document_evidence",
        reconciled_documents,
    )
    monkeypatch.setattr(
        publication,
        "deployment_status",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("deployment status must follow exact baseline verification")
        ),
    )
    monkeypatch.setattr(
        publication,
        "reconcile_drafts",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("draft reconciliation must not run after unknown drift")
        ),
    )
    monkeypatch.setattr(
        publication,
        "create_proposals",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("proposal creation must not run after unknown drift")
        ),
    )

    def preview() -> None:
        assert lifecycle == ["finalize:True", "resume-readback"]
        lifecycle.append("preview")
        slug = articles[0].production_slug
        revised = dict(current_documents[slug])
        revised["revision_id"] = int(revised["revision_id"]) + 1
        revised["modified_gmt"] = "2026-08-29T00:01:00Z"
        assert revised["content_sha256"] == documents[slug]["content_sha256"]
        current_documents[slug] = revised

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_UNKNOWN_BASELINE_DRIFT",
    ):
        publication.execute(
            "all",
            measurement_plugin_apply_receipt=plugin_receipt_path,
            rakuten_activation_dry_run=activation_path,
            quality_audit_attestation=quality_attestation_path,
            quality_audit_signature=quality_signature_path,
            portfolio_refresh=lambda: (_ for _ in ()).throw(
                AssertionError("validated activation must not be rematerialized")
            ),
            preview=preview,
            client_factory=lambda: client,
        )

    assert lifecycle == [
        "finalize:True",
        "resume-readback",
        "preview",
    ]
    assert "raos-codex-content-update-draft" not in remote_calls
    assert "raos-codex-content-propose-release" not in remote_calls
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["state"] == "APPLIED"
    assert stored["prior_applied_reconciliation"]["documents"] == documents


def test_stale_docker_group_uses_only_fixed_sg_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(publication, "_docker_group_membership_is_stale", lambda: True)
    commands: list[tuple[str, ...]] = []
    fixture_roots: list[str] = []

    def runner(
        command: tuple[str, ...], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        commands.append(command)
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        fixture_roots.append(environment["RAOS_WORDPRESS_PREVIEW_FIXTURE_ROOT"])
        return subprocess.CompletedProcess(command, 0, b"", b"")

    publication.run_preview_checks(runner)
    assert commands == [
        (
            "/usr/bin/sg",
            "docker",
            "-c",
            f"/usr/bin/make {target}",
        )
        for target in (
            "wordpress-preview-up",
            "wordpress-preview-sync",
            "wordpress-preview-check",
        )
    ]
    assert all("ARTICLES" not in part for command in commands for part in command)
    assert fixture_roots == [publication.LOCAL_MATERIALIZED_FIXTURE_ROOT.as_posix()] * 3


def test_preview_commands_receive_exact_activation_overlay_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(publication, "_docker_group_membership_is_stale", lambda: False)
    activation_overlay_root = (
        tmp_path / "local-materialized-fixtures-v3-deadbeef"
    ).resolve()
    fixture_roots: list[str] = []

    def runner(
        command: tuple[str, ...], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        fixture_roots.append(environment["RAOS_WORDPRESS_PREVIEW_FIXTURE_ROOT"])
        return subprocess.CompletedProcess(command, 0, b"", b"")

    publication.run_preview_checks(runner, fixture_root=activation_overlay_root)

    assert fixture_roots == [activation_overlay_root.as_posix()] * 3


def test_make_target_passes_articles_via_environment_without_shell_expansion() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "wordpress-production-request:" in makefile
    recipe = makefile[makefile.index("wordpress-production-request:") :]
    assert "$(ARTICLES)" not in recipe
    assert 'os.environ.get("ARTICLES", "all")' in SCRIPT.read_text(encoding="utf-8")


def test_seed_uses_the_production_markup_sanitizers() -> None:
    seed = (ROOT / "changes/wordpress-local-preview-v1/seed.php").read_text(
        encoding="utf-8"
    )
    assert "wp_strip_all_tags($post['title']) !== $post['title']" in seed
    assert "wp_kses_post($post['excerpt']) !== $post['excerpt']" in seed
    assert "wp_kses_post($content) !== $content" in seed

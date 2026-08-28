from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[2]
WORDPRESS_SOURCE = ROOT / "packages/web-ui/src/decision-support-v2/wordpress"
PROJECTION_PATH = WORDPRESS_SOURCE / "projection.py"
PACKAGE_PATH = ROOT / "packages/web-ui/src/decision-support-v2/preview/pages.v2.json"
PLUGIN_ROOT = WORDPRESS_SOURCE / "plugin/raos-v2-decision-support"
PHP_PATH = PLUGIN_ROOT / "raos-v2-decision-support.php"
CSS_PATH = PLUGIN_ROOT / "assets/decision-support.css"
MANIFEST_PATH = PLUGIN_ROOT / "plugin-manifest.v1.json"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "raos_v2_wordpress_projection", PROJECTION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _package() -> dict[str, object]:
    value = json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _projection() -> dict[str, object]:
    value = _module().project_a05_wordpress_post_content_v1(_package())
    assert isinstance(value, dict)
    return value


def test_phase3_a05_projection_is_deterministic_and_route_exact() -> None:
    first = _projection()
    second = _projection()
    assert first == second
    assert first["schema"] == "RAOS_V2_WORDPRESS_POST_CONTENT_PROJECTION_V1"
    assert first["article_id"] == "A05"
    assert first["route"] == "/carry-on-suitcase-comparison/"
    assert first["post_status"] == "publish"
    assert first["comment_status"] == "closed"
    assert first["ping_status"] == "closed"
    assert first["package_marker"] == "RAOS_V2_A05_POST_CONTENT_V1"


def test_phase3_projection_is_owned_by_the_standard_mypy_gate() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert (
        "python/raos packages/web-ui/src/decision-support-v2/wordpress/projection.py"
        in makefile
    )


def test_phase3_post_content_is_fragment_with_wordpress_owned_single_h1() -> None:
    projection = _projection()
    markup = projection["post_content"]
    assert isinstance(markup, str)
    assert projection["heading_contract"] == {
        "document_heading_owner": "WORDPRESS_POST_TITLE",
        "expected_document_h1_count": 1,
        "post_content_h1_count": 0,
    }
    assert re.search(r"<h1(?:\s|>)", markup, flags=re.IGNORECASE) is None
    assert (
        re.search(
            r"<(?:!doctype|html|head|body|title|meta)(?:\s|>)",
            markup,
            flags=re.IGNORECASE,
        )
        is None
    )
    assert 'data-raos-v2-package-marker="RAOS_V2_A05_POST_CONTENT_V1"' in markup


def test_phase3_post_content_has_required_reader_value_and_fail_closed_ctas() -> None:
    projection = _projection()
    markup = projection["post_content"]
    assert isinstance(markup, str)
    assert "広告リンクに関する表示" in markup
    assert "根拠パケット基準日" in markup
    assert "仕様を同じ軸で比較" in markup
    assert "根拠と編集判断の分け方" in markup
    assert "未確認（UNKNOWN）の事項" in markup
    assert markup.count('class="raos-v2-decision-support__comparison-card"') == 4
    assert 'class="raos-v2-decision-support__comparison-cards" role="region"' in markup
    assert markup.count('id="raos-v2-mobile-axis-') == 4
    assert markup.count('data-raos-v2-evidence="A_OFFICIAL_FACT"') == 9
    assert markup.count('data-raos-v2-evidence="D_EDITORIAL_JUDGEMENT"') == 2
    assert markup.count("<dt>ACE クレスタ 06316</dt>") == 4
    assert markup.count("<dt>ace. ディフェレンス 05721</dt>") == 4
    assert markup.count("<dt>PROTECA マックスパス4 01471</dt>") == 4
    assert markup.count('data-raos-v2-cta-state="BLOCKED"') == 3
    assert markup.count("現在は商品リンクを利用できません") == 3
    assert projection["blocked_cta_count"] == 3
    assert projection["affiliate_url_count"] == 0
    assert markup.count("https://store.ace.jp/shop/g/") == 3
    assert markup.count("公式仕様</a>") == 3
    assert "affiliate.rakuten" not in markup.lower()
    assert "hb.afl.rakuten" not in markup.lower()
    assert "rakuten.co.jp" not in markup.lower()


def test_phase3_projection_has_no_images_or_unverified_routes() -> None:
    projection = _projection()
    markup = projection["post_content"]
    assert isinstance(markup, str)
    assert projection["image_count"] == 0
    assert "<img" not in markup.lower()
    assert "src=" not in markup.lower()
    hrefs = re.findall(r'href="([^"]+)"', markup)
    assert hrefs
    assert set(hrefs) <= {
        "/",
        "/carry-on-suitcase-comparison/",
        "/about-ad-policy/",
        "/privacy-policy/",
        "https://store.ace.jp/shop/g/g06316-01/",
        "https://store.ace.jp/shop/g/g05721-04",
        "https://store.ace.jp/shop/g/g01471-02",
        "https://store.ace.jp/shop/g/g06316-01/",
        "https://store.ace.jp/shop/g/g05721-04",
        "https://store.ace.jp/shop/g/g01471-02",
    }
    for forbidden in (
        "/carry-on/",
        "/tools/carry-on-size-checker/",
        "/policy/how-we-compare-carry-on-products/",
        "ローカルプレビュー",
    ):
        assert forbidden not in markup


def test_phase3_projection_neutralizes_wordpress_shortcode_delimiters() -> None:
    package = deepcopy(_package())
    products = package["products"]
    assert isinstance(products, dict)
    product = products["PRD-ACE-CRESTA-06316"]
    assert isinstance(product, dict)
    product["name"] = '[gallery ids="1,2"]'
    markup = _module().project_a05_wordpress_post_content_v1(package)["post_content"]
    assert isinstance(markup, str)
    assert '[gallery ids="1,2"]' not in markup
    assert "&#91;gallery ids=&quot;1,2&quot;&#93;" in markup


@pytest.mark.parametrize(
    ("field", "payload"),
    [
        ("title", "安全な比較<strong>ではない</strong>"),
        ("title", '[gallery ids="1,2"]'),
        ("description", "&lt;script&gt;alert(1)&lt;/script&gt;"),
        ("description", "購入判断を反転\u202eする説明"),
    ],
)
def test_phase3_projection_rejects_markup_in_wordpress_plain_text_fields(
    field: str, payload: str
) -> None:
    package = deepcopy(_package())
    pages = package["pages"]
    assert isinstance(pages, list)
    page = next(item for item in pages if item["article_id"] == "A05")
    page[field] = payload
    with pytest.raises(ValueError, match=rf"page\.{field} must be strict plain text"):
        _module().project_a05_wordpress_post_content_v1(package)


@pytest.mark.parametrize(
    "mutation",
    [
        "route",
        "scope",
        "cta",
        "commerce_field",
        "checked_at",
        "axis_evidence",
        "nested_product_id",
        "axis_value_scope",
        "source_href",
        "source_label",
        "source_status",
    ],
)
def test_phase3_projection_rejects_unsafe_or_incomplete_source(
    mutation: str,
) -> None:
    package = deepcopy(_package())
    pages = package["pages"]
    products = package["products"]
    assert isinstance(pages, list) and isinstance(products, dict)
    page = next(item for item in pages if item["article_id"] == "A05")
    product = products["PRD-ACE-CRESTA-06316"]
    if mutation == "route":
        page["route"] = "/other/"
    elif mutation == "scope":
        page["products"] = list(reversed(page["products"]))
    elif mutation == "cta":
        product["cta_state"] = "AVAILABLE"
    elif mutation == "commerce_field":
        product["affiliate_url"] = "https://example.invalid/"
    elif mutation == "checked_at":
        package["checked_at"] = "UNAVAILABLE"
    elif mutation == "axis_evidence":
        page["comparison_axes"][0]["label"] = "未分類軸"
    elif mutation == "nested_product_id":
        product["product_id"] = 'PRD-ACE-CRESTA-06316" onmouseover="alert(1)'
    elif mutation == "axis_value_scope":
        page["comparison_axes"][0]["values"]["UNBOUND"] = "ignored"
    elif mutation == "source_href":
        product["source"]["href"] = "https://example.invalid/product"
    elif mutation == "source_label":
        product["source"]["label"] = "別商品の公式仕様"
    elif mutation == "source_status":
        product["source"]["status"] = "STALE"
    with pytest.raises(ValueError):
        _module().project_a05_wordpress_post_content_v1(package)


def test_phase3_presentation_plugin_is_exactly_route_and_marker_scoped() -> None:
    php = PHP_PATH.read_text(encoding="utf-8")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert "carry-on-suitcase-comparison" in php
    assert "RAOS_V2_A05_POST_CONTENT_V1" in php
    assert "is_singular('post')" in php
    assert "$post->post_name !== RAOS_V2_DECISION_SUPPORT_SLUG" in php
    assert "wp_parse_url($permalink, PHP_URL_PATH)" in php
    assert "!== RAOS_V2_DECISION_SUPPORT_ROUTE" in php
    assert "substr_count($reviewed, $exact_marker) === 1" in php
    assert php.count("wp_enqueue_style(") == 1
    assert manifest["target"] == {
        "article_id": "A05",
        "exact_route": "/carry-on-suitcase-comparison/",
        "exact_post_slug": "carry-on-suitcase-comparison",
        "required_package_marker": "RAOS_V2_A05_POST_CONTENT_V1",
        "required_post_content_sha256": sha256(
            str(_projection()["post_content"]).encode("utf-8")
        ).hexdigest(),
        "rendered_content_envelope": "RAOS_V2_A05_ENVELOPE_V1",
    }
    assert manifest["runtime"] == {
        "allowed_effect": (
            "ENQUEUE_BUNDLED_STYLESHEET_AND_WRAP_UNCHANGED_REVIEWED_FRAGMENT_"
            "ON_EXACT_MATCH"
        ),
        "admin_ui": False,
        "content_filter": "FAIL_CLOSED_EXACT_BYTES_IDEMPOTENT",
        "cron": False,
        "database_write": False,
        "network_request": False,
        "option_write": False,
        "publication_capability": False,
        "rest_route": False,
        "telemetry": False,
    }


def test_phase3_plugin_wraps_one_exact_content_envelope_fail_closed() -> None:
    php = PHP_PATH.read_text(encoding="utf-8")
    post_content_sha256 = sha256(
        str(_projection()["post_content"]).encode("utf-8")
    ).hexdigest()
    for contract in (
        "RAOS_V2_A05_ENVELOPE_V1",
        "data-raos-v2-post-content-envelope=",
        "esc_attr(RAOS_V2_DECISION_SUPPORT_ENVELOPE)",
        "$reviewed = trim($post->post_content);",
        "$candidate = trim($content);",
        "$candidate !== $reviewed",
        "$candidate === $already_wrapped",
        "strpos($reviewed, $expected_root) !== 0",
        "strpos($reviewed, $envelope_attribute) !== false",
        'data-raos-v2-post-content-envelope-status="BLOCKED"',
        "公開内容の整合性を確認できないため、この記事は表示を停止しています。",
        "'the_content'",
        "PHP_INT_MAX",
        f"const RAOS_V2_DECISION_SUPPORT_POST_CONTENT_SHA256 = '{post_content_sha256}';",
        "hash_equals(",
        "hash('sha256', $reviewed)",
    ):
        assert contract in php
    assert php.count("add_filter(") == 1
    assert php.count("RAOS_V2_DECISION_SUPPORT_ENVELOPE") == 2


def test_phase3_plugin_leaves_non_target_and_preview_pipeline_unmodified() -> None:
    php = PHP_PATH.read_text(encoding="utf-8")
    assert "if (! ($post instanceof WP_Post)) {\n        return $content;\n    }" in php
    assert "is_preview(" not in php
    assert "is_admin(" not in php
    assert "get_the_ID(" not in php


def test_phase3_plugin_does_not_reinterpret_shortcode_or_kses_output() -> None:
    php = PHP_PATH.read_text(encoding="utf-8").lower()
    for prohibited in (
        "do_shortcode(",
        "wp_kses(",
        "apply_filters(",
        "shortcode_unautop(",
        "wpautop(",
        "html_entity_decode(",
    ):
        assert prohibited not in php
    assert "php_int_max" in php


def test_phase3_presentation_plugin_has_no_write_network_or_telemetry_port() -> None:
    php = PHP_PATH.read_text(encoding="utf-8").lower()
    for token in (
        "wp_remote_",
        "wp_insert_post",
        "wp_update_post",
        "update_option",
        "add_option",
        "delete_option",
        "update_post_meta",
        "register_rest_route",
        "wp_schedule_event",
        "set_transient",
        "curl_",
        "file_get_contents(",
        "fetch(",
        "sendbeacon",
        "analytics",
    ):
        assert token not in php


def test_phase3_css_selectors_are_fully_scoped_and_accessible() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")
    assert "url(" not in css.lower()
    assert "@import" not in css.lower()
    assert ":focus-visible" in css
    assert "forced-colors: active" in css
    assert "overflow-x: auto" in css
    assert ".raos-v2-decision-support__comparison-cards" in css
    assert "@media (max-width: 40rem)" in css
    mobile = css.split("@media (max-width: 40rem)", 1)[1]
    assert ".raos-v2-decision-support__table-scroll" in mobile
    assert "display: none" in mobile
    assert ".raos-v2-decision-support__comparison-cards" in mobile
    assert "display: grid" in mobile
    assert "min-width: 2.75rem" not in css
    blocks = re.findall(r"(?P<selectors>[^{}]+)\{[^{}]*\}", css)
    selectors = []
    for block in blocks:
        cleaned = block.strip()
        if cleaned.startswith("@") or ":" not in cleaned and cleaned == "":
            continue
        selectors.extend(part.strip() for part in cleaned.split(","))
    for selector in selectors:
        if selector.startswith("@"):
            continue
        assert selector.startswith(".raos-v2-decision-support"), selector

from __future__ import annotations

import ast
import gzip
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
UI_SOURCE = ROOT / "packages/web-ui/src/decision-support-v2/preview"
PAGES_PATH = UI_SOURCE / "pages.v2.json"
CSS_PATH = UI_SOURCE / "styles.css"
JAVASCRIPT_PATH = UI_SOURCE / "checker.js"
RENDERER_PATH = UI_SOURCE / "render_preview.py"
TS_ROOT = ROOT / "packages/web-ui/src/decision-support-v2"
SOURCE_REGISTRY_PATH = (
    ROOT / "changes/raos-v2/phase-2/sources/source-registry.v2.yaml"
)
AIRLINE_FIXTURE_PATH = (
    ROOT / "changes/raos-v2/phase-2/fixtures/recorded-airline-rules.v2.json"
)

EXPECTED_ROUTES = {
    "/": ("HOME", "HOME", True),
    "/carry-on/": ("HUB", "A01", True),
    "/tools/carry-on-size-checker/": ("TOOL", "A02", True),
    "/guides/carry-on-baggage-rules/": ("GUIDE", "A03", True),
    "/guides/low-cost-carrier-7kg-packing/": ("GUIDE", "A04", False),
    "/carry-on-suitcase-comparison/": ("COMPARISON", "A05", True),
    "/guides/carry-on-bag-measurement/": ("GUIDE", "A06", False),
    "/policy/how-we-compare-carry-on-products/": ("POLICY", "A25", True),
    "/differences/ace-cresta-vs-difference-vs-maxpass4/": (
        "DIFFERENCE",
        "A19",
        False,
    ),
}


def _pages() -> dict[str, object]:
    value = json.loads(PAGES_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _load_renderer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "raos_v2_preview_renderer", RENDERER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _render() -> dict[str, bytes]:
    renderer = _load_renderer()
    return renderer.render_pages(
        pages=_pages(),
        css=CSS_PATH.read_text(encoding="utf-8"),
        javascript=JAVASCRIPT_PATH.read_text(encoding="utf-8"),
    )


def test_t_v2_024_to_027_route_and_editorial_contracts_are_exact() -> None:
    package = _pages()
    raw_pages = package["pages"]
    assert isinstance(raw_pages, list)
    pages = {page["route"]: page for page in raw_pages}
    assert set(pages) == set(EXPECTED_ROUTES)
    assert {page["template"] for page in raw_pages} == {
        "HOME",
        "HUB",
        "GUIDE",
        "COMPARISON",
        "DIFFERENCE",
        "TOOL",
        "POLICY",
    }
    for route, (template, article_id, index_candidate) in EXPECTED_ROUTES.items():
        page = pages[route]
        assert page["template"] == template
        assert page["article_id"] == article_id
        assert page["intended_index_candidate"] is index_candidate

    for route in (
        "/guides/low-cost-carrier-7kg-packing/",
        "/guides/carry-on-bag-measurement/",
    ):
        assert pages[route]["publication_state"] == "PLANNED_LOCKED"
        assert pages[route]["public_candidate"] is False
    difference = pages["/differences/ace-cresta-vs-difference-vs-maxpass4/"]
    assert difference["publication_state"] == "FIXTURE_ONLY"
    assert difference["public_candidate"] is False
    assert "検索意図が比較記事と重なる" in json.dumps(difference, ensure_ascii=False)


def test_t_v2_035_sitemap_candidate_contract_matches_rendered_metadata() -> None:
    document = yaml.safe_load(
        (
            ROOT
            / "changes/raos-v2/phase-2/generated/sitemap-candidates.v2.yaml"
        ).read_text(encoding="utf-8")
    )
    pages = {row["route"]: row for row in _pages()["pages"]}
    entries = {row["route"]: row for row in document["entries"]}
    assert set(entries) == set(EXPECTED_ROUTES) == set(pages)
    assert document["mode"] == "LOCAL_CONTRACT_ONLY"
    assert document["production_sitemap_write"] == "NOT_EXECUTED"
    assert document["candidate_count"] == sum(
        page["intended_index_candidate"] is True for page in pages.values()
    )
    for route, page in pages.items():
        path = (
            ROOT / "changes/raos-v2/phase-2/preview/index.html"
            if route == "/"
            else ROOT
            / "changes/raos-v2/phase-2/preview"
            / route.strip("/")
            / "index.html"
        )
        payload = path.read_bytes()
        html = payload.decode("utf-8")
        entry = entries[route]
        assert entry["article_id"] == page["article_id"]
        assert entry["title"] == page["title"]
        assert entry["description"] == page["description"]
        assert entry["phase2_sitemap_included"] is False
        assert entry["phase3_intended_candidate"] is page["intended_index_candidate"]
        assert entry["lastmod"] == "UNAVAILABLE"
        assert entry["render_sha256"] == hashlib.sha256(payload).hexdigest()
        assert '<meta name="robots" content="noindex,nofollow">' in html
        assert (
            f'<link rel="canonical" href="https://kurashinoshirube.com{route}">'
            in html
        )


def test_t_v2_026_comparison_has_exact_scope_and_quality_slots() -> None:
    package = _pages()
    page = next(
        item
        for item in package["pages"]
        if item["route"] == "/carry-on-suitcase-comparison/"
    )
    product_ids = page["products"]
    assert product_ids == [
        "PRD-ACE-CRESTA-06316",
        "PRD-ACE-DIFFERENCE-05721",
        "PRD-ACE-MAXPASS4-01471",
    ]
    assert "NO UNIVERSAL WINNER" == page["eyebrow"]
    serialized_page = json.dumps(page, ensure_ascii=False)
    assert page["title"] == "ACEのスーツケース3モデルを機内持ち込み条件で比較"
    assert "機内持ち込み対応3モデル" not in serialized_page
    assert "ディフェレンス" in serialized_page
    assert "ディファレンス" not in serialized_page
    assert "実機試験は行っていません" in serialized_page
    assert "最もおすすめ" not in serialized_page
    assert "人気" not in serialized_page

    products = package["products"]
    assert set(products) == set(product_ids)
    for product_id in product_ids:
        product = products[product_id]
        assert all(
            product[field] for field in ("fit", "non_fit", "tradeoff", "unknown")
        )
        assert product["cta_state"] == "IDENTITY_BLOCKED"
        assert "price" not in product
        assert "rate" not in product
        assert "epc" not in product


def test_t_v2_023_checker_source_is_local_only_and_complete() -> None:
    javascript = JAVASCRIPT_PATH.read_text(encoding="utf-8")
    lowered = javascript.lower()
    for token in (
        "fetch(",
        "xmlhttprequest",
        "sendbeacon",
        "localstorage",
        "sessionstorage",
        "indexeddb",
        "serviceworker",
        "document.cookie",
    ):
        assert token not in lowered
    assert "BigInt" in javascript
    assert "departureAtJst" in javascript
    assert "effectiveFrom" in javascript
    assert "nextReviewAt" in javascript
    assert "fareOrOption" in javascript
    assert "journeyScope" in javascript
    assert "carryOnCount" in javascript
    assert "personalItemCount" in javascript
    assert "maxCarryOnCount" in javascript
    assert "maxPersonalItemCount" in javascript
    assert "requiresPersonalItemUnderseat" in javascript
    assert "personalItemUnderseatConfirmed" in javascript
    assert "appendagesIncluded" in javascript
    assert "coefficient <= 0n" in javascript
    assert "permutations" in javascript
    assert "maxSum" in javascript
    assert "effectiveFrom: '2026-07-01'" not in javascript
    jetstar_rule = re.search(
        r"carrier: 'JETSTAR_JAPAN',(?P<body>.*?)status: 'FRESH'",
        javascript,
        flags=re.DOTALL,
    )
    assert jetstar_rule is not None
    assert "effectiveUntil: null" in jetstar_rule.group("body")
    assert "nextReviewAt: '2026-09-27T06:41:52+09:00'" in jetstar_rule.group(
        "body"
    )
    assert "orientation: 'ORDERED'" in jetstar_rule.group("body")
    assert "NO_MATCH: 1" in javascript
    assert "UNKNOWN: 2" in javascript
    assert "departureInstant < effectiveUntil" in javascript
    assert "departureInstant >= nextReviewAt" in javascript
    state_match = re.search(
        r"const RESULT_STATES = Object\.freeze\(\[(.*?)\]\);",
        javascript,
        flags=re.DOTALL,
    )
    assert state_match is not None
    assert set(re.findall(r"'([A-Z_]+)'", state_match.group(1))) == {
        "PASS",
        "FAIL",
        "UNKNOWN",
        "STALE",
        "BLOCKED",
        "NO_MATCH",
    }


def test_t_v2_023_checker_source_ids_are_registry_bound() -> None:
    javascript = JAVASCRIPT_PATH.read_text(encoding="utf-8")
    checker_source_ids = set(re.findall(r"sourceId: '([^']+)'", javascript))
    registry = yaml.safe_load(SOURCE_REGISTRY_PATH.read_text(encoding="utf-8"))
    registry_source_ids = {source["source_id"] for source in registry["sources"]}
    assert checker_source_ids == {
        "SRC-V2-ANA-CARRY-ON",
        "SRC-V2-JAL-CARRY-ON",
        "SRC-V2-PEACH-CARRY-ON",
        "SRC-V2-JETSTAR-CARRY-ON",
    }
    assert checker_source_ids <= registry_source_ids


def _ui_rule_records(javascript: str) -> list[dict[str, object]]:
    rules_source = javascript.split("const RULES = Object.freeze([", 1)[1].split(
        "  ]);", 1
    )[0]
    blocks = re.findall(
        r"Object\.freeze\(\{\n(?P<body>.*?)\n    \}\)",
        rules_source,
        flags=re.DOTALL,
    )

    def value(body: str, key: str) -> object:
        match = re.search(rf"^      {re.escape(key)}: (?P<value>.*),$", body, re.MULTILINE)
        assert match is not None, key
        raw = match.group("value")
        if raw == "null":
            return None
        if raw in {"true", "false"}:
            return raw == "true"
        if raw.startswith("Object.freeze(") and raw.endswith(")"):
            raw = raw[len("Object.freeze(") : -1]
        return ast.literal_eval(raw)

    keys = (
        "carrier",
        "journeyScope",
        "aircraft",
        "fareOrOption",
        "effectiveFrom",
        "effectiveUntil",
        "nextReviewAt",
        "maxDimensions",
        "maxSum",
        "maxWeight",
        "maxItems",
        "maxCarryOnCount",
        "maxPersonalItemCount",
        "orientation",
        "sourceId",
    )
    return [{key: value(block, key) for key in keys} for block in blocks]


def test_t_v2_023_checker_rules_match_recorded_normalized_fixture() -> None:
    fixture = json.loads(AIRLINE_FIXTURE_PATH.read_text(encoding="utf-8"))
    rule_sets = {rule_set["rule_set_id"]: rule_set for rule_set in fixture["rule_sets"]}
    expected_variants = (
        ("AIR-ANA-DOMESTIC-2026", "ANA-100-SEATS-OR-MORE", "LARGE", None, "ANA"),
        ("AIR-ANA-DOMESTIC-2026", "ANA-UNDER-100-SEATS", "SMALL", None, "ANA"),
        ("AIR-JAL-DOMESTIC-2026", "JAL-100-SEATS-OR-MORE", "LARGE", None, "JAL"),
        ("AIR-JAL-DOMESTIC-2026", "JAL-UNDER-100-SEATS", "SMALL", None, "JAL"),
        ("AIR-PEACH-2026", "PEACH-STANDARD", None, None, "PEACH"),
        (
            "AIR-JETSTAR-JAPAN-2026",
            "JETSTAR-JAPAN-STANDARD-7KG",
            None,
            "STANDARD_7KG",
            "JETSTAR_JAPAN",
        ),
    )
    expected = []
    for rule_set_id, variant_id, aircraft, fare, ui_carrier in expected_variants:
        rule_set = rule_sets[rule_set_id]
        variant = next(
            value for value in rule_set["variants"] if value["variant_id"] == variant_id
        )
        expected.append(
            {
                "carrier": ui_carrier,
                "journeyScope": rule_set["journey_scope"],
                "aircraft": aircraft,
                "fareOrOption": fare,
                "effectiveFrom": rule_set["effective_from"]
                or rule_set["observed_applicable_from"],
                "effectiveUntil": rule_set["effective_to"],
                "nextReviewAt": rule_set["source_next_review_at"],
                "maxDimensions": variant["dimension_edges_cm"],
                "maxSum": variant["sum_edges_cm"],
                "maxWeight": variant["total_weight_kg"],
                "maxItems": variant["bag_count"] + variant["personal_item_count"],
                "maxCarryOnCount": variant["bag_count"],
                "maxPersonalItemCount": variant["personal_item_count"],
                "orientation": variant["orientation"],
                "sourceId": rule_set["source_id"],
            }
        )
    assert _ui_rule_records(JAVASCRIPT_PATH.read_text(encoding="utf-8")) == expected


def test_t_v2_033_tokens_responsive_and_performance_budgets() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")
    expected_colors = {
        "--color-ink": "#17213a",
        "--color-paper": "#fbf8f1",
        "--color-surface": "#fff",
        "--color-muted": "#f1f5f4",
        "--color-indigo": "#243b6b",
        "--color-indigo-dark": "#172a52",
        "--color-accent": "#a4492c",
        "--color-success": "#216e5a",
        "--color-warning": "#8a5a00",
        "--color-danger": "#a23434",
        "--color-focus": "#005fcc",
        "--color-border": "#d9d5cb",
    }
    for token, value in expected_colors.items():
        assert f"{token}: {value};" in css
    assert "min-height: 44px" in css
    assert "@media (forced-colors: active)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "@media (max-width: 767px)" in css
    assert len(gzip.compress(css.encode("utf-8"), mtime=0)) <= 40 * 1024
    javascript = JAVASCRIPT_PATH.read_bytes()
    assert len(gzip.compress(javascript, mtime=0)) <= 60 * 1024


def test_t_v2_035_036_renderer_is_deterministic_and_seo_consistent() -> None:
    first = _render()
    second = _render()
    assert first == second
    assert set(first) == set(EXPECTED_ROUTES)
    for route, document_bytes in first.items():
        document = document_bytes.decode("utf-8")
        assert document.count("<h1>") == 1
        assert '<html lang="ja">' in document
        assert 'href="#main"' in document
        assert 'aria-label="広告表示"' in document
        assert "広告リンクに関する表示" in document
        assert "広告リンクを設置する場合があります" in document
        assert "現在、確認済みでない商品リンクは表示しません" in document
        assert "このページには広告リンクがあります" not in document
        assert (
            f'<link rel="canonical" href="https://kurashinoshirube.com{route}">'
            in document
        )
        assert "<script src=" not in document
        assert '<link rel="stylesheet"' not in document
        assert "@font-face" not in document
        assert '<meta name="robots" content="noindex,nofollow">' in document
        assert 'type="application/ld+json"' not in document

    checker_document = first["/tools/carry-on-size-checker/"].decode("utf-8")
    assert 'name="journey-scope"' in checker_document
    assert 'name="journey-scope-2"' in checker_document
    assert "国内線" in checker_document
    assert "国際線" in checker_document
    assert "わからない・確認中" in checker_document


def test_t_v2_036_synthetic_indexable_model_matches_visible_content() -> None:
    renderer = _load_renderer()
    package = _pages()
    pages = {item["route"]: item for item in package["pages"]}

    home_payload = renderer._render_json_ld(
        pages["/"], "https://kurashinoshirube.com", "index,follow"
    )
    assert '"@type":"WebSite"' in home_payload
    assert '"@type":"Organization"' in home_payload
    assert '"@type":"BreadcrumbList"' not in home_payload
    assert '"@type":"Article"' not in home_payload

    for route in ("/carry-on/", "/tools/carry-on-size-checker/"):
        payload = renderer._render_json_ld(
            pages[route], "https://kurashinoshirube.com", "index,follow"
        )
        assert '"@type":"BreadcrumbList"' in payload
        assert '"@type":"WebSite"' not in payload
        assert '"@type":"Article"' not in payload
        for breadcrumb in pages[route]["breadcrumbs"]:
            assert breadcrumb["label"] in payload

    guide = json.loads(
        json.dumps(pages["/guides/carry-on-baggage-rules/"], ensure_ascii=False)
    )
    without_visible_metadata = renderer._render_json_ld(
        guide, "https://kurashinoshirube.com", "index,follow"
    )
    assert '"@type":"Article"' not in without_visible_metadata

    guide.update(
        {
            "author_name": "暮らしのしるべ編集部",
            "date_published": "2026-08-28",
            "date_modified": "2026-08-29",
        }
    )
    document = renderer._render_page(
        page=guide,
        products=package["products"],
        origin="https://kurashinoshirube.com",
        disclosure=package["disclosure"],
        preview_robots="index,follow",
        css=CSS_PATH.read_text(encoding="utf-8"),
        javascript=JAVASCRIPT_PATH.read_text(encoding="utf-8"),
    ).decode("utf-8")
    assert '"@type":"Article"' in document
    assert f'"headline":"{guide["title"]}"' in document
    assert '"name":"暮らしのしるべ編集部"' in document
    assert '"datePublished":"2026-08-28"' in document
    assert '"dateModified":"2026-08-29"' in document
    assert "執筆者：暮らしのしるべ編集部" in document
    assert '<time datetime="2026-08-28">2026-08-28</time>' in document
    assert '<time datetime="2026-08-29">2026-08-29</time>' in document

    partial = dict(guide)
    partial.pop("date_modified")
    with pytest.raises(renderer.PreviewInputError, match="ARTICLE_METADATA_INCOMPLETE"):
        renderer._render_json_ld(
            partial, "https://kurashinoshirube.com", "index,follow"
        )

    ineligible = dict(pages["/carry-on/"])
    ineligible.update(
        {
            "author_name": "暮らしのしるべ編集部",
            "date_published": "2026-08-28",
            "date_modified": "2026-08-28",
        }
    )
    with pytest.raises(renderer.PreviewInputError, match="ARTICLE_METADATA_INVALID"):
        renderer._render_json_ld(
            ineligible, "https://kurashinoshirube.com", "index,follow"
        )


def test_t_v2_033_rendered_comparison_has_semantic_parity_and_blocked_cta() -> None:
    document = _render()["/carry-on-suitcase-comparison/"].decode("utf-8")
    assert document.count('class="product-card"') == 3
    assert document.count('<th scope="col">') == 4
    assert document.count('<th scope="row">') == 4
    assert document.count('class="matrix-mobile-card"') == 4
    assert document.count("向く条件") >= 3
    assert document.count("向かない条件") >= 3
    assert document.count("トレードオフ") >= 3
    assert document.count("未確認") >= 3
    assert document.count('<button type="button" disabled>') == 3
    assert "楽天市場へ" not in document
    assert "affiliate.rakuten" not in document


def test_t_v2_044_renderer_fails_closed_for_unsafe_links_and_inline_breakout() -> None:
    renderer = _load_renderer()
    package = _pages()
    malicious = json.loads(json.dumps(package))
    malicious["pages"][0]["sections"][0]["links"][0]["href"] = "javascript:alert(1)"
    with pytest.raises(renderer.PreviewInputError, match="INTERNAL_LINK_INVALID"):
        renderer.render_pages(pages=malicious, css="body{}", javascript="")
    with pytest.raises(renderer.PreviewInputError, match="INLINE_BOUNDARY_INVALID"):
        renderer.render_pages(pages=package, css="</style>", javascript="")
    with pytest.raises(
        renderer.PreviewInputError, match="RUNTIME_EXTERNAL_EFFECT_PROHIBITED"
    ):
        renderer.render_pages(pages=package, css="body{}", javascript="fetch('/x')")


def test_ui_typescript_sources_keep_browser_and_business_boundaries_separate() -> None:
    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(TS_ROOT.glob("*.ts"))
    )
    assert "BROWSER_LOCAL_ONLY" in sources
    assert "analyticsSender: 'OFF'" in sources
    assert "wordpressWrite: 'DISABLED_DRY_RUN'" in sources
    for prohibited in ("businessScore", "confirmedEpc", "commissionRate"):
        assert prohibited not in sources

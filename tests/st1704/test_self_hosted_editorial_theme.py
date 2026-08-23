"""Static, deterministic checks for the isolated ST-1704 WordPress theme."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SLICE_ROOT = REPOSITORY_ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme"
THEME_ROOT = SLICE_ROOT / "kurashinoshirube-child"
CONTRACT_PATH = THEME_ROOT / "theme-contract.v1.json"
ASSET_MANIFEST_PATH = THEME_ROOT / "raos-assets.v1.json"
YOAST_LOCK_PATH = SLICE_ROOT / "yoast-seo-28.3.lock.json"
ARTICLES_PATH = (
    REPOSITORY_ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json"
)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
    )
    assert isinstance(value, dict)
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _contract_snapshot_validator(raw: str) -> bool:
    """Executable mirror of the language-neutral v1 snapshot contract."""

    contract = _load_json(CONTRACT_PATH)
    snapshot = contract["snapshot"]
    assert isinstance(snapshot, dict)
    if len(raw.encode("utf-8")) > snapshot["max_bytes"]:
        return False
    try:
        wrapper = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except UnicodeError, ValueError:
        return False
    if not isinstance(wrapper, dict) or sorted(wrapper) != snapshot["wrapper_keys"]:
        return False
    if raw != _canonical_json(wrapper):
        return False
    if wrapper.get("schema") != snapshot["schema_value"]:
        return False
    payload = wrapper.get("payload")
    if not isinstance(payload, dict) or sorted(payload) != snapshot["payload_keys"]:
        return False
    digest = hashlib.sha256(_canonical_json(payload).encode()).hexdigest()
    if wrapper.get("payload_sha256") != digest:
        return False
    bindings = snapshot["article_bindings"]
    assert isinstance(bindings, list)
    expected = {
        item["article_id"]: (item["slug"], item["section"])
        for item in bindings
        if isinstance(item, dict)
    }
    article_id = payload.get("article_id")
    if expected.get(article_id) != (payload.get("slug"), payload.get("section")):
        return False
    return (
        payload.get("author_name") == snapshot["author_name"]
        and payload.get("canonical_url")
        == f"{snapshot['canonical_origin']}/{payload.get('slug')}/"
        and payload.get("og_title") == payload.get("title")
        and payload.get("og_description") == payload.get("description")
        and isinstance(payload.get("visible_content_sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", payload["visible_content_sha256"]) is not None
    )


def _valid_snapshot() -> tuple[str, dict[str, object]]:
    payload: dict[str, object] = {
        "article_id": "st1704-portable-power-station-guide",
        "author_name": "暮らしのしるべ編集部",
        "canonical_url": ("https://kurashinoshirube.com/portable-power-station-guide/"),
        "description": (
            "停電時に必要な容量、定格出力、持ち運びやすさを一次情報から"
            "整理し、使う条件に合うポータブル電源の選び方を解説します。"
        ),
        "modified_at": None,
        "og_description": (
            "停電時に必要な容量、定格出力、持ち運びやすさを一次情報から"
            "整理し、使う条件に合うポータブル電源の選び方を解説します。"
        ),
        "og_title": (
            "停電対策用ポータブル電源の選び方｜容量・定格出力・持ち運びで決める"
        ),
        "packet_sha256": "b" * 64,
        "published_at": None,
        "section": "備え",
        "seo_title": "停電対策用ポータブル電源4モデル比較",
        "slug": "portable-power-station-guide",
        "title": ("停電対策用ポータブル電源の選び方｜容量・定格出力・持ち運びで決める"),
        "visible_content_sha256": "a" * 64,
    }
    wrapper: dict[str, object] = {
        "payload": payload,
        "payload_sha256": hashlib.sha256(_canonical_json(payload).encode()).hexdigest(),
        "schema": "RAOS_PUBLICATION_SNAPSHOT_V1",
    }
    return _canonical_json(wrapper), wrapper


def _relative_luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def _assert_balanced_wordpress_blocks(source: str) -> None:
    stack: list[str] = []
    for match in re.finditer(r"<!--\s*(/?)wp:([a-z0-9-]+)(.*?)-->", source):
        closing, name, suffix = match.groups()
        if closing:
            assert stack and stack.pop() == name
        elif not suffix.rstrip().endswith("/"):
            stack.append(name)
    assert stack == []


def test_theme_is_an_isolated_1_1_0_successor() -> None:
    stylesheet = (THEME_ROOT / "style.css").read_text(encoding="utf-8")
    assert stylesheet.count("\nVersion: 1.1.0\n") == 1
    assert "Template: twentytwentyfive" in stylesheet
    assert "ST-1704" in stylesheet
    assert THEME_ROOT != (
        REPOSITORY_ROOT
        / "changes/st-1703/self-hosted-minimum-start-v1/theme"
        / "kurashinoshirube-child"
    )


def test_asset_manifest_is_complete_and_hash_bound() -> None:
    manifest = _load_json(ASSET_MANIFEST_PATH)
    assert manifest["schema"] == "SELF_HOSTED_EDITORIAL_THEME_ASSETS_V1"
    assert manifest["theme_version"] == "1.1.0"
    records = manifest["required_images"]
    assert isinstance(records, list) and len(records) == 3
    for record in records:
        assert isinstance(record, dict)
        path = THEME_ROOT / str(record["path"])
        assert path.is_file() and not path.is_symlink()
        assert _sha256(path) == record["sha256"]
        assert record["status"] == "FINAL"
    source_files = manifest["source_files"]
    assert isinstance(source_files, list)
    assert source_files == sorted(source_files)
    assert all((THEME_ROOT / str(path)).is_file() for path in source_files)


def test_brand_mark_is_bounded_accessible_svg() -> None:
    mark = THEME_ROOT / "assets/images/brand-mark.svg"
    root = ET.fromstring(mark.read_text(encoding="utf-8"))
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert root.attrib["viewBox"] == "0 0 64 64"
    assert root.attrib["role"] == "img"
    assert root.attrib["aria-labelledby"] == "title"
    titles = root.findall("{http://www.w3.org/2000/svg}title")
    assert len(titles) == 1 and titles[0].text == "暮らしのしるべ"
    assert "<script" not in mark.read_text(encoding="utf-8").lower()


def test_homepage_has_one_h1_three_clusters_and_the_brand_promise() -> None:
    header = (THEME_ROOT / "parts/header.html").read_text(encoding="utf-8")
    front = (THEME_ROOT / "templates/front-page.html").read_text(encoding="utf-8")
    functions = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    assert header.count('"level":0') == 1
    assert front.count('<h1 class="') == 1
    assert front.count('"level":1') == 1
    assert "暮らしの道具に、根拠のある余白を。" in front
    assert front.count("[kurashinoshirube_published_clusters]") == 1
    for label, anchor in (
        ("移動", "cluster-mobility"),
        ("家事", "cluster-home"),
        ("備え", "cluster-ready"),
    ):
        assert label in functions
        assert functions.count(anchor) >= 1
    assert "広告報酬をおすすめ順位の判断材料にしません" in front
    assert '"inherit":false' in front
    assert "get_page_by_path($slug, OBJECT, 'post')" in functions
    assert "get_post_status($post) !== 'publish'" in functions
    for unpublished_path in (
        "/portable-power-station-guide/",
        "/countertop-dishwasher-for-small-households/",
        "/anker-solix-c300-c800-c1000-differences/",
        "/compact-robot-vacuum-shortlist/",
    ):
        assert unpublished_path not in front


def test_wordpress_block_templates_are_balanced() -> None:
    for path in (
        THEME_ROOT / "parts/header.html",
        THEME_ROOT / "parts/footer.html",
        THEME_ROOT / "templates/front-page.html",
        THEME_ROOT / "templates/single.html",
    ):
        _assert_balanced_wordpress_blocks(path.read_text(encoding="utf-8"))


def test_single_template_has_one_dynamic_h1_and_one_theme_owned_related_ui() -> None:
    single = (THEME_ROOT / "templates/single.html").read_text(encoding="utf-8")
    functions = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    assert single.count('wp:post-title {"level":1}') == 1
    assert "<h1" not in single
    assert single.count("[kurashinoshirube_breadcrumb]") == 1
    assert 'aria-label="パンくずリスト"' in functions
    assert 'aria-current="page"' in functions
    assert single.count("[kurashinoshirube_related_guides]") == 1
    assert single.index("wp:post-content") < single.index(
        "[kurashinoshirube_related_guides]"
    )
    assert functions.count("function kurashinoshirube_render_related_guides") == 1
    assert functions.count("'kurashinoshirube_related_guides'") == 2
    assert "get_post_status($target) !== 'publish'" in functions
    assert "get_permalink($target) !== $expected_url" in functions
    assert "kurashinoshirube_bound_post_snapshot(" in functions
    assert "$target_snapshot['article_id'] !== $target_id" in functions


def test_related_navigation_is_fixed_reciprocal_and_contract_hashed() -> None:
    contract = _load_json(CONTRACT_PATH)
    related = contract["related_navigation"]
    assert isinstance(related, dict)
    relation_map = related["map"]
    assert isinstance(relation_map, dict)
    assert (
        related["map_sha256"]
        == hashlib.sha256(_canonical_json(relation_map).encode()).hexdigest()
    )
    source = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    map_match = re.search(
        r"const KURASHINOSHIRUBE_RELATED_ARTICLE_MAP_JSON = '([^']+)';",
        source,
    )
    hash_match = re.search(
        r"const KURASHINOSHIRUBE_RELATED_ARTICLE_MAP_SHA256 = '([0-9a-f]{64})';",
        source,
    )
    assert map_match is not None
    assert hash_match is not None
    php_map_json = map_match.group(1)
    assert json.loads(php_map_json) == relation_map
    assert php_map_json == _canonical_json(relation_map)
    assert hash_match.group(1) == related["map_sha256"]
    assert related["owner"] == "THEME_FIXED_ALLOWLIST"
    assert related["content_hash_scope"] == (
        "THEME_CHROME_OUTSIDE_WORDPRESS_POST_CONTENT"
    )
    assert relation_map["st1704-portable-power-station-guide"]["targets"] == {
        "st1704-anker-solix-c300-c800-c1000-differences": (
            "Anker Solix C300・C800 Plus・C1000・C1000 Gen 2の違い"
        )
    }
    assert relation_map["st1704-anker-solix-c300-c800-c1000-differences"][
        "targets"
    ] == {"st1704-portable-power-station-guide": ("停電対策用ポータブル電源の選び方")}
    assert all(len(value["targets"]) <= 1 for value in relation_map.values())

    articles = _load_json(ARTICLES_PATH)
    routes = {route["route_ref"]: route for route in articles["routes"]}
    article_records = {
        article["article_id"]: article for article in articles["articles"]
    }
    assert set(article_records) == set(relation_map)
    for article_id, relation in relation_map.items():
        blocks = article_records[article_id]["content_ast"]["blocks"]
        internal = [block for block in blocks if block["type"] == "internal_links"]
        assert len(internal) == 1
        observed: dict[str | None, str] = {}
        for link in internal[0]["links"]:
            route = routes[link["route_ref"]]
            observed[route["article_id"]] = link["anchor_text"]
        assert observed.pop(None) == relation["home_label"]
        assert observed == relation["targets"]


def test_homepage_cluster_contract_is_hash_bound_and_covers_all_articles() -> None:
    contract = _load_json(CONTRACT_PATH)
    homepage = contract["homepage_clusters"]
    configuration = homepage["config"]
    canonical = _canonical_json(configuration)
    assert (
        homepage["config_sha256"]
        == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    )
    assert configuration["display_order"] == [
        "cluster-mobility",
        "cluster-home",
        "cluster-ready",
    ]
    clusters = configuration["clusters"]
    assert set(clusters) == set(configuration["display_order"])
    assert clusters["cluster-mobility"]["post_order"] == [
        "st1703-first-suitcase-comparison"
    ]
    assert clusters["cluster-home"]["post_order"] == [
        "st1704-countertop-dishwasher-for-small-households",
        "st1704-compact-robot-vacuum-shortlist",
    ]
    assert clusters["cluster-ready"]["post_order"] == [
        "st1704-portable-power-station-guide",
        "st1704-anker-solix-c300-c800-c1000-differences",
    ]
    assert all(
        set(cluster["post_order"]) == set(cluster["posts"])
        and len(cluster["post_order"]) == len(cluster["posts"])
        for cluster in clusters.values()
    )
    observed_articles = {
        article_id for cluster in clusters.values() for article_id in cluster["posts"]
    }
    assert observed_articles == set(contract["related_navigation"]["map"])
    for article_id, relation in contract["related_navigation"]["map"].items():
        assert article_id in clusters[relation["home_anchor"]]["posts"]

    source = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    config_match = re.search(
        r"const KURASHINOSHIRUBE_HOMEPAGE_CLUSTERS_JSON = '([^']+)';",
        source,
    )
    hash_match = re.search(
        r"const KURASHINOSHIRUBE_HOMEPAGE_CLUSTERS_SHA256 = '([0-9a-f]{64})';",
        source,
    )
    assert config_match is not None
    assert hash_match is not None
    assert config_match.group(1) == canonical
    assert json.loads(config_match.group(1)) == configuration
    assert hash_match.group(1) == homepage["config_sha256"]


def test_footer_removes_the_broken_subscription_link() -> None:
    footer = (THEME_ROOT / "parts/footer.html").read_text(encoding="utf-8")
    assert "/subscribe/" not in footer
    assert "新着案内を受け取る" not in footer
    assert "/about/" in footer
    assert "/about-ad-policy/" in footer


def test_content_is_visible_without_javascript() -> None:
    css = (THEME_ROOT / "assets/theme.css").read_text(encoding="utf-8")
    functions = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    assert not (THEME_ROOT / "assets/theme.js").exists()
    assert "wp_enqueue_script(" not in functions
    assert "raos-reveal" not in css
    assert "opacity: 0" not in css
    assert "visibility: hidden" not in css
    assert css.count("display: none") == 2
    assert ".raos-comparison__cards {\n  display: none;" in css
    assert ".raos-comparison__table-view {\n    display: none;" in css
    assert "prefers-reduced-motion: reduce" in css


def test_product_images_are_not_cropped_or_upscaled() -> None:
    css = (THEME_ROOT / "assets/theme.css").read_text(encoding="utf-8")
    match = re.search(r"\.raos-product-card__media img\s*\{([^}]*)\}", css)
    assert match is not None
    rule = match.group(1)
    for declaration in (
        "height: auto",
        "max-height: 128px",
        "max-width: 128px",
        "width: auto",
    ):
        assert declaration in rule
    for forbidden in ("object-fit", "transform", "width: 100%", "height: 100%"):
        assert forbidden not in rule
    contract = _load_json(CONTRACT_PATH)
    markup = contract["content_markup"]
    assert isinstance(markup, dict)
    image = markup["product_card"]["image"]
    assert image == {
        "css_max_height_px": 128,
        "css_max_width_px": 128,
        "declared_height_px": 128,
        "declared_width_px": 128,
        "media_class": "raos-product-card__media",
        "transformation": "NONE",
        "upscale": False,
    }


def test_comparison_and_cta_contracts_are_accessible_and_closed() -> None:
    contract = _load_json(CONTRACT_PATH)
    markup = contract["content_markup"]
    assert isinstance(markup, dict)
    comparison = markup["comparison"]
    assert comparison["semantic_element"] == "table"
    assert comparison["required_attributes"] == [
        "aria-labelledby",
        "role=region",
        "tabindex=0",
    ]
    assert comparison["desktop_view_class"] == "raos-comparison__table-view"
    assert comparison["mobile_view_class"] == "raos-comparison__cards"
    assert comparison["mobile_card_class"] == "raos-comparison-card"
    assert comparison["mobile_semantics"] == "article>dl>div>dt+dd"
    assert comparison["mobile_breakpoint_max_px"] == 640
    cta = markup["affiliate_cta"]
    assert cta["exact_label"] == "楽天市場で写真・価格・在庫を見る"
    assert sorted(cta["rel_tokens"]) == ["nofollow", "sponsored"]
    assert cta["required_host_provenance"].startswith("VALIDATED_RAKUTEN_")
    css = (THEME_ROOT / "assets/theme.css").read_text(encoding="utf-8")
    assert ".raos-comparison:focus-visible" in css
    assert ".raos-comparison__table-view" in css
    assert ".raos-comparison__cards" in css
    assert ".raos-comparison-card dl > div" in css
    assert "@media (max-width: 40rem)" in css
    assert '[tabindex="0"]):focus-visible' in css


def test_focus_and_text_color_pairs_meet_wcag_aa() -> None:
    assert _contrast("#17243f", "#f7f2e9") >= 4.5
    assert _contrast("#ffffff", "#24365f") >= 4.5
    assert _contrast("#702b18", "#f1ddd3") >= 4.5
    assert _contrast("#83361f", "#f7f2e9") >= 4.5
    assert _contrast("#ffffff", "#24365f") >= 3
    assert _contrast("#ffffff", "#17243f") >= 3
    assert _contrast("#4f5b57", "#fffdf8") >= 4.5
    css = (THEME_ROOT / "assets/theme.css").read_text(encoding="utf-8")
    references = set(re.findall(r"var\((--raos-[a-z-]+)\)", css))
    definitions = set(re.findall(r"(?m)^\s*(--raos-[a-z-]+):", css))
    assert references <= definitions
    assert "outline: 3px solid var(--raos-focus)" in css
    assert ".raos-hero :where(a, button):focus-visible" in css
    assert ".raos-masthead nav a" in css
    assert ".raos-wordmark:focus-visible" in css
    assert "outline-color: #fff" in css
    assert "@media (forced-colors: active)" in css


def test_snapshot_contract_accepts_only_canonical_hash_bound_shape() -> None:
    contract = _load_json(CONTRACT_PATH)
    assert contract["schema"] == "SELF_HOSTED_EDITORIAL_THEME_CONTRACT_V1"
    assert contract["publication_authority"] == "NONE"
    raw, wrapper = _valid_snapshot()
    assert _contract_snapshot_validator(raw)
    assert len(raw.encode()) < 16384
    assert sorted(wrapper) == ["payload", "payload_sha256", "schema"]
    snapshot = contract["snapshot"]
    assert isinstance(snapshot, dict)
    assert snapshot["review_draft_slug"] == (
        "raos-review-{public_slug}-{payload_sha256_lower_hex}"
    )
    assert snapshot["slug_binding"] == (
        "PUBLIC_SLUG_ONLY_WHEN_PUBLISHED_OR_EXACT_DERIVED_REVIEW_SLUG_WHEN_DRAFT"
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda wrapper: wrapper.update(schema="RAOS_PUBLICATION_SNAPSHOT_V2"),
        lambda wrapper: wrapper.update(payload_sha256="0" * 64),
        lambda wrapper: wrapper["payload"].update(section="家事"),
        lambda wrapper: wrapper["payload"].update(slug="other"),
        lambda wrapper: wrapper["payload"].update(og_title="別のタイトル"),
        lambda wrapper: wrapper["payload"].update(packet_sha256="0" * 63),
        lambda wrapper: wrapper.update(unexpected=True),
    ],
    ids=(
        "schema",
        "hash",
        "section",
        "slug",
        "og-title",
        "packet-hash",
        "unknown-key",
    ),
)
def test_snapshot_contract_rejects_mismatches(
    mutate: Callable[[dict[str, object]], None],
) -> None:
    _raw, wrapper = _valid_snapshot()
    mutate(wrapper)
    assert not _contract_snapshot_validator(_canonical_json(wrapper))


def test_snapshot_bridge_is_private_and_existing_update_is_human_bounded() -> None:
    source = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    for required in (
        "register_post_meta(",
        "kurashinoshirube_authorize_snapshot_meta",
        "current_user_can('edit_post', $post_id)",
        "kurashinoshirube_hide_public_snapshot_meta",
        "hash_equals($decoded['payload_sha256']",
        "hash('sha256', $content)",
        "kurashinoshirube_canonical_json($decoded) !== $raw",
        "function kurashinoshirube_review_slug",
        "'raos-review-' . $payload['slug']",
        "'-[0-9a-f]{64}\\z/D'",
        "return $status === 'publish'",
        "($status === 'publish' && $payload['slug'] === $slug)",
        "$status === 'draft'",
        "$review_slug === $slug",
        "revisions_enabled",
    ):
        assert required in source
    for forbidden in (
        "wp_publish_post",
        "delete_post_meta",
        "media_handle_",
        "wp_insert_attachment",
        "activate_plugin",
    ):
        assert forbidden not in source
    assert source.count("wp_update_post(") == 2
    assert source.count("update_post_meta(") == 2
    assert "admin_post_nopriv_" not in source
    assert "wp_ajax_" not in source
    assert "check_admin_referer(" in source
    assert "current_user_can('manage_options')" in source
    assert "current_user_can('publish_posts')" in source
    assert "add_option(" in source
    assert "KURASHINOSHIRUBE_EXISTING_UPDATE_ARTICLE_ID" in source
    assert "kurashinoshirube_existing_update_invariants(" in source


def test_yoast_is_the_only_generic_head_metadata_owner() -> None:
    source = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    expected_filters = (
        "wpseo_title",
        "wpseo_metadesc",
        "wpseo_canonical",
        "wpseo_opengraph_title",
        "wpseo_opengraph_desc",
        "wpseo_opengraph_url",
        "wpseo_opengraph_image",
        "wpseo_opengraph_image_width",
        "wpseo_opengraph_image_height",
        "wpseo_opengraph_image_type",
        "wpseo_twitter_title",
        "wpseo_twitter_description",
        "wpseo_twitter_image",
        "wpseo_twitter_card_type",
        "wpseo_robots",
    )
    for name in expected_filters:
        pattern = rf"add_filter\(\s*'{re.escape(name)}'"
        assert len(re.findall(pattern, source)) == 1
    assert "wpseo_add_opengraph_images" not in source
    assert "kurashinoshirube_filter_snapshot_value($value, 'seo_title')" in source
    assert "$payload['title'] !== $title" in source
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            THEME_ROOT / "functions.php",
            THEME_ROOT / "parts/header.html",
            THEME_ROOT / "parts/footer.html",
            THEME_ROOT / "templates/front-page.html",
            THEME_ROOT / "templates/single.html",
        )
    )
    for duplicate in (
        "<title",
        'name="description"',
        'rel="canonical"',
        'property="og:',
        'name="twitter:',
    ):
        assert duplicate not in combined


def test_existing_article_update_is_one_human_only_preserving_action() -> None:
    source = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    contract = _load_json(CONTRACT_PATH)
    update = contract["human_existing_update"]
    assert isinstance(update, dict)
    assert update["allowed_article_id"] == "st1703-first-suitcase-comparison"
    assert update["autonomous_authority"] == "NONE"
    assert update["transport"] == (
        "POST_ONLY_WORDPRESS_ADMIN_ACTION_NO_REST_AJAX_OR_NOPRIV"
    )
    assert update["mutation_order"] == (
        "SNAPSHOT_META_THEN_POST_FIELDS_THEN_EXACT_READBACK"
    )
    assert update["allowed_copy_fields"] == [
        "post_content",
        "post_excerpt",
        "post_title",
        "_raos_publication_snapshot_v1",
    ]
    assert update["journal_assertions"] == [
        "review_draft_id",
        "target_public_post_id",
        "packet_sha256",
        "request_sha256",
        "payload_sha256",
    ]
    assert update["approval_receipt_fields"] == [
        "approved_at",
        "approved_by_user_id",
        "approval_reason",
        "decision",
        "operation_sha256",
        "packet_sha256",
        "payload_sha256",
        "pre_state",
        "pre_state_sha256",
        "request_sha256",
        "rollback_artifact",
        "schema",
        "source_post_id",
        "target_post_id",
    ]
    assert "filter_input(INPUT_SERVER, 'REQUEST_METHOD'" in source
    assert "check_admin_referer(" in source
    assert "wp_check_post_lock(" in source
    assert "wp_get_current_user()" in source
    assert "APPROVE_AT003_EXISTING_UPDATE" in source
    assert "kurashinoshirube_existing_update_source_matches" in source
    assert "KURASHINOSHIRUBE_REVIEW_REQUEST_PATH" in source
    assert "hash_equals($request_sha256, hash('sha256', $request_material))" in source
    assert "wp_authenticate(" in source
    assert "$reauthentication_password = '';" in source
    assert 'name="approval_reason"' in source
    assert "'rollback_artifact'" in source
    handler = source.split("function kurashinoshirube_handle_existing_update", 1)[1]
    assert handler.index("update_post_meta(") < handler.index(
        "$updated = wp_update_post("
    )
    assert "kurashinoshirube_rollback_existing_update" in source
    assert "delete_option(" not in source


def test_structured_data_is_one_closed_raos_graph() -> None:
    source = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    contract = _load_json(CONTRACT_PATH)
    head = contract["head"]
    assert isinstance(head, dict)
    assert source.count("add_filter('wpseo_json_ld_output'") == 1
    assert "'__return_false', PHP_INT_MAX" in source
    assert source.count('id="raos-structured-data"') == 1
    assert source.count("add_action('wp_head', 'kurashinoshirube_emit_json_ld'") == 1
    assert head["allowed_json_ld_types"] == [
        "Article",
        "BreadcrumbList",
        "ListItem",
        "Organization",
        "WebSite",
    ]
    for schema_type in head["forbidden_json_ld_types"]:
        assert f"'@type' => '{schema_type}'" not in source


def test_theme_has_no_remote_or_headless_rest_call() -> None:
    source = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    for forbidden in (
        "wp_remote_",
        "curl_exec",
        "file_get_contents('http",
        'file_get_contents("http',
    ):
        assert forbidden not in source
    assert "kurashinoshirube_remove_yoast_head_route" in source
    assert "'/yoast/v1/get_head'" in source
    assert "unset($data['yoast_head'], $data['yoast_head_json'])" in source
    assert "add_filter('rest_prepare_post'" in source
    assert "add_filter('rest_prepare_page'" in source
    contract = _load_json(CONTRACT_PATH)
    head = contract["head"]
    assert isinstance(head, dict)
    assert head["yoast_headless_rest"] == ("PERSISTED_OPTION_PLUS_REST_OUTPUT_FILTER")
    assert head["yoast_option_write"] == "ABSENT"


def test_yoast_lock_is_exact_and_human_gated() -> None:
    lock = _load_json(YOAST_LOCK_PATH)
    assert lock["schema"] == "RAOS_WORDPRESS_PLUGIN_LOCK_V1"
    assert lock["plugin_slug"] == "wordpress-seo"
    assert lock["version"] == "28.3"
    assert lock["activation_authority"] == "HUMAN_ONLY"
    assert lock["release_status"] == "BLOCKED"
    assert lock["activation_blockers"] == [
        "OFFICIAL_CHECKSUM_UNAVAILABLE",
        "PERSISTED_CONFIGURATION_READBACK_NOT_EXECUTED",
        "WORDPRESS_YOAST_INTEGRATION_NOT_EXECUTED",
    ]
    assert lock["downloaded_archive_committed"] is False
    archive = lock["archive"]
    assert archive == {
        "byte_length": 5151735,
        "download_url": (
            "https://downloads.wordpress.org/plugin/wordpress-seo.28.3.zip"
        ),
        "sha256": ("381edc1603147bd76af81341f21c9155ff3e9f6ce29ed20886d889fb9d6744fb"),
        "verification": (
            "LOCAL_SHA256_OF_OFFICIAL_HTTPS_ARCHIVE_NOT_AN_OFFICIAL_CHECKSUM"
        ),
    }
    checksum = lock["official_checksum_api"]
    assert checksum["status"] == "NOT_AVAILABLE_HTTP_404_AT_OBSERVATION_TIME"
    readback = lock["configuration_readback"]
    assert readback == {
        "authority": "HUMAN_PERSISTED_OPTIONS_WITH_THEME_READBACK_GATE",
        "site_health_test": "kurashinoshirube_yoast_configuration",
        "status": "NOT_EXECUTED",
    }
    configuration = lock["required_configuration"]
    assert all(
        configuration[key] is False
        for key in (
            "ai_features",
            "automatic_updates",
            "headless_rest_api",
            "semrush_integration",
            "usage_tracking",
            "wincher_integration",
            "yoast_frontend_schema",
        )
    )
    options = configuration["wpseo_option_values"]
    assert options == {
        "enable_ai_generator": False,
        "enable_headless_rest_endpoints": False,
        "enable_index_now": False,
        "enable_schema": False,
        "enable_schema_aggregation_endpoint": False,
        "enable_xml_sitemap": True,
        "google_site_kit_feature_enabled": False,
        "googleverify": "",
        "semrush_integration_active": False,
        "tracking": False,
        "wincher_integration_active": False,
    }
    assert configuration["wpseo_social_option_values"] == {
        "og_default_image": "VERIFIED_THEME_SOCIAL_IMAGE_URI",
        "og_default_image_id": "",
        "opengraph": True,
        "twitter": True,
        "twitter_card_type": "summary_large_image",
    }


def test_yoast_policy_uses_persisted_readback_and_late_output_filters() -> None:
    source = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    for fragment in (
        "function kurashinoshirube_yoast_configuration_is_exact",
        "WPSEO_VERSION !== '28.3'",
        "get_option('wpseo', null)",
        "get_option('wpseo_social', null)",
        "'opengraph' => true",
        "'twitter' => true",
        "'twitter_card_type' => 'summary_large_image'",
        "'enable_headless_rest_endpoints'",
        "'enable_xml_sitemap'",
        "kurashinoshirube_register_site_health_tests",
        "add_filter(\n    'site_status_tests'",
        "add_filter('wpseo_robots'",
        "'noindex, nofollow'",
        "'noindex, follow'",
        "'index, follow, max-image-preview:large, max-snippet:-1, '",
        "kurashinoshirube_review_slug($snapshot) === $slug",
        "strpos($slug, 'raos-review-' . $public_slug . '-') === 0",
        "'wpseo_sitemap_exclude_post_type'",
        "'wpseo_sitemap_exclude_taxonomy'",
        "'wpseo_sitemap_exclude_author'",
    ):
        assert fragment in source
    assert "add_filter('option_wpseo'" not in source
    assert "update_option(" not in source
    assert source.count("function kurashinoshirube_sitemap_exclude_authors") == 1
    assert "return array();" in source
    contract = _load_json(CONTRACT_PATH)
    head = contract["head"]
    assert isinstance(head, dict)
    assert head["yoast_configuration_authority"] == (
        "HUMAN_PERSISTED_OPTIONS_WITH_THEME_READBACK_GATE"
    )
    assert head["yoast_social_option_values"] == {
        "og_default_image": "VERIFIED_THEME_SOCIAL_IMAGE_URI",
        "og_default_image_id": "",
        "opengraph": True,
        "twitter": True,
        "twitter_card_type": "summary_large_image",
    }
    assert head["sitemap"] == {
        "authors": False,
        "post_types": ["page", "post"],
        "taxonomies": [],
    }
    assert head["rest_output"] == {
        "preserved_route": "/wp/v2/posts",
        "removed_fields": ["yoast_head", "yoast_head_json"],
        "removed_route": "/yoast/v1/get_head",
    }

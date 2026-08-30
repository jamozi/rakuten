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
EDITORIAL_NAVIGATION_PATH = THEME_ROOT / "assets/editorial-navigation.v3.json"
EDITORIAL_V2_PUBLICATION_BINDINGS = (
    ("carry-on-suitcase-comparison", "st1703-first-suitcase-comparison"),
    ("portable-power-station-guide", "st1704-portable-power-station-guide"),
    (
        "countertop-dishwasher-for-small-households",
        "st1704-countertop-dishwasher-for-small-households",
    ),
    (
        "anker-solix-c300-c800-c1000-differences",
        "st1704-anker-solix-c300-c800-c1000-differences",
    ),
    ("compact-robot-vacuum-shortlist", "st1704-compact-robot-vacuum-shortlist"),
    ("carry-on-suitcase-under-100-seats", "carry-on-suitcase-under-100-seats"),
    (
        "front-open-carry-on-suitcase-with-stopper",
        "front-open-carry-on-suitcase-with-stopper",
    ),
    (
        "lightweight-carry-on-suitcase-under-3kg",
        "lightweight-carry-on-suitcase-under-3kg",
    ),
    ("roomba-mini-vs-switchbot-k11-pro", "roomba-mini-vs-switchbot-k11-pro"),
    ("solota-vs-rakua-mini-plus", "solota-vs-rakua-mini-plus"),
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


def test_theme_is_an_isolated_1_4_0_successor() -> None:
    stylesheet = (THEME_ROOT / "style.css").read_text(encoding="utf-8")
    functions = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    assert stylesheet.count("\nVersion: 1.4.0\n") == 1
    assert "Template: twentytwentyfive" in stylesheet
    assert "ST-1704" in stylesheet
    assert _load_json(CONTRACT_PATH)["theme_version"] == "1.4.0"
    assert functions.count("KURASHINOSHIRUBE_THEME_VERSION = '1.4.0'") == 1
    runtime_revision = (
        "44b8eb82ac770a93b7b25aef1353007b6da650fb49ef5a6d2567915940595684"
    )
    assert functions.count(
        "KURASHINOSHIRUBE_THEME_RUNTIME_REVISION = "
        f"'{runtime_revision}'"
    ) == 1
    contract = _load_json(CONTRACT_PATH)
    assert contract["runtime_evidence"] == {
        "revision": runtime_revision,
        "stylesheets": {
            "assets/editorial-v2.css": (
                "--raos-theme-runtime-revision-editorial-v2"
            ),
            "assets/theme.css": "--raos-theme-runtime-revision-base",
        },
    }
    assert _load_json(ASSET_MANIFEST_PATH)["theme_runtime_revision"] == (
        runtime_revision
    )
    assert (
        "--raos-theme-runtime-revision-base: " + runtime_revision + ";"
        in (THEME_ROOT / "assets/theme.css").read_text(encoding="utf-8")
    )
    assert (
        "--raos-theme-runtime-revision-editorial-v2: "
        + runtime_revision
        + ";"
        in (THEME_ROOT / "assets/editorial-v2.css").read_text(encoding="utf-8")
    )
    at003_gate = functions.split(
        "function kurashinoshirube_existing_update_context", 1
    )[1]
    assert "$theme->get('Version') !== KURASHINOSHIRUBE_THEME_VERSION" in at003_gate
    assert THEME_ROOT != (
        REPOSITORY_ROOT
        / "changes/st-1703/self-hosted-minimum-start-v1/theme"
        / "kurashinoshirube-child"
    )


def test_only_exact_public_article_identities_disable_wordpress_wpautop() -> None:
    source = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    function = source.split(
        "function kurashinoshirube_disable_wpautop_for_bound_public_article",
        1,
    )[1].split("add_action(", 1)[0]
    assert "is_singular('post')" in function
    assert "get_queried_object_id()" in function
    assert "get_post_status($post_id) !== 'publish'" in function
    assert "kurashinoshirube_public_article_identity($post_id) === null" in function
    assert "remove_filter('the_content', 'wpautop', 10);" in function
    assert source.count("remove_filter('the_content', 'wpautop', 10);") == 1
    registration = source.split(
        "function kurashinoshirube_disable_wpautop_for_bound_public_article",
        1,
    )[1]
    assert (
        "add_action(\n"
        "    'wp',\n"
        "    'kurashinoshirube_disable_wpautop_for_bound_public_article',\n"
        "    0\n"
        ");"
    ) in registration


def test_japanese_type_stacks_prefer_real_mincho_and_gothic_families() -> None:
    css = (THEME_ROOT / "assets/theme.css").read_text(encoding="utf-8")
    theme_json = _load_json(THEME_ROOT / "theme.json")
    typography = theme_json["settings"]["typography"]
    families = {
        record["slug"]: record["fontFamily"]
        for record in typography["fontFamilies"]
    }
    serif = (
        "'Hiragino Mincho ProN', 'Yu Mincho', YuMincho, "
        "'Noto Serif CJK JP', 'Noto Serif JP', serif"
    )
    sans = (
        "-apple-system, BlinkMacSystemFont, 'Hiragino Kaku Gothic ProN', "
        "'Yu Gothic', YuGothic, 'Noto Sans CJK JP', 'Noto Sans JP', sans-serif"
    )
    assert families == {"editorial-serif": serif, "editorial-sans": sans}
    assert "--raos-font-serif: " + serif.replace("'", '"') + ";" in css
    assert css.count("font-family: var(--raos-font-serif);") == 11
    assert "ui-serif" not in css
    assert "ui-serif" not in families["editorial-serif"]


def test_asset_manifest_is_complete_and_hash_bound() -> None:
    manifest = _load_json(ASSET_MANIFEST_PATH)
    assert manifest["schema"] == "SELF_HOSTED_EDITORIAL_THEME_ASSETS_V1"
    assert manifest["theme_version"] == "1.4.0"
    records = manifest["required_images"]
    assert isinstance(records, list) and len(records) == 4
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


def test_editorial_v2_styles_are_exactly_scoped_and_conditionally_loaded() -> None:
    functions = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    css = (THEME_ROOT / "assets/editorial-v2.css").read_text(encoding="utf-8")
    contract = _load_json(CONTRACT_PATH)["editorial_v2"]
    assert contract == {
        "asset": "assets/editorial-v2.css",
        "base_style_dependency": "kurashinoshirube-editorial",
        "body_class": "raos-editorial-v2-page",
        "category_fallback_allowlist": ["移動", "家事", "備え"],
        "content_root": '<div class="raos-editorial-v2">',
        "detection": "EXACT_RAW_CONTENT_PREFIX_ON_SINGULAR_POST",
        "publication_identity_predicate": (
            "PUBLISH_POST_EXACT_SINGLE_EDITORIAL_V2_ROOT_AND_CLOSED_SLUG_ARTICLE_ID_MATCH"
        ),
        "publication_snapshot_required": False,
        "scope": "ORDINARY_WORDPRESS_POST_ONLY",
        "section_binding_count": 10,
        "section_binding_source": "assets/editorial-navigation.v3.json#articles",
    }
    assert "function kurashinoshirube_is_editorial_v2_post(): bool" in functions
    assert (
        "KURASHINOSHIRUBE_EDITORIAL_V2_ROOT = '<div "
        'class="raos-editorial-v2">\''
    ) in functions
    assert "kurashinoshirube_post_has_editorial_v2_root($post_id)" in functions
    assert "'raos-editorial-v2-page'" in functions
    assert "'kurashinoshirube-editorial-v2'" in functions
    assert "'/assets/editorial-v2.css'" in functions
    assert "array('kurashinoshirube-editorial')" in functions
    assert "function kurashinoshirube_editorial_v2_body_class" in functions
    assert "function kurashinoshirube_enqueue_editorial_v2_stylesheet" in functions
    assert ".raos-editorial-v2-page" in css
    assert ".raos-editorial-v2 .comparison-table" in css
    assert ".raos-local-editorial-v2-page" not in css


def test_policy_v3_body_class_is_closed_to_exact_reviewed_pages() -> None:
    functions = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    contract = _load_json(CONTRACT_PATH)["policy_v3"]
    assert contract == {
        "body_class": "raos-policy-v3-page",
        "detection": (
            "EXACT_PUBLISHED_PAGE_SLUG_TITLE_AND_EXCERPT_MATCH_CLOSED_HEAD_MAP"
        ),
        "footer_presentation": (
            "SAME_RICH_RESPONSIVE_FOOTER_AS_HOME_AND_EDITORIAL_V2"
        ),
        "scope": "EXACT_THREE_REVIEWED_WORDPRESS_POLICY_PAGES_ONLY",
        "slugs": ["about-ad-policy", "comparison-policy", "privacy-policy"],
    }
    detector = functions.split(
        "function kurashinoshirube_is_policy_v3_page(): bool", 1
    )[1].split("/** Keep all ten production", 1)[0]
    for marker in (
        "is_singular('page')",
        "get_queried_object_id()",
        "get_post_type($post_id) !== 'page'",
        "get_post_status($post_id) !== 'publish'",
        "kurashinoshirube_policy_page_head_map()[$slug] ?? null",
        "get_post_field('post_title', $post_id, 'raw') === $head['title']",
        "get_post_field('post_excerpt', $post_id, 'raw') === $head['description']",
    ):
        assert marker in detector
    body_class = functions.split(
        "function kurashinoshirube_editorial_v2_body_class", 1
    )[1].split("add_filter('body_class'", 1)[0]
    assert "kurashinoshirube_is_policy_v3_page()" in body_class
    assert "$classes[] = 'raos-policy-v3-page';" in body_class
    assert "$classes[] = 'raos-editorial-v2-page';" in body_class


def test_editorial_v2_category_fallback_is_allowlisted() -> None:
    functions = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    category = functions.split(
        "function kurashinoshirube_render_article_category", 1
    )[1].split("add_shortcode(", 1)[0]
    assert "kurashinoshirube_current_snapshot()" in category
    assert "kurashinoshirube_is_editorial_v2_post()" in category
    assert "kurashinoshirube_editorial_v2_section_map()[$slug] ?? null" in category
    assert "wp_get_post_terms(" in category
    assert "array('移動', '家事', '備え')" in category
    assert "in_array($allowed_section, $terms, true)" in category
    publication_bindings = functions.split(
        "function kurashinoshirube_editorial_v2_publication_bindings", 1
    )[1].split("function kurashinoshirube_related_article_map", 1)[0]
    assert "return kurashinoshirube_article_bindings();" in publication_bindings
    navigation = _load_json(EDITORIAL_NAVIGATION_PATH)
    assert len(navigation["articles"]) == 10
    assert {article["category_label"] for article in navigation["articles"]} == {
        "移動",
        "家事",
        "備え",
    }
    section_map = functions.split(
        "function kurashinoshirube_editorial_v2_section_map", 1
    )[1].split("function kurashinoshirube_editorial_v2_body_class", 1)[0]
    assert "kurashinoshirube_editorial_v2_publication_bindings()" in section_map
    assert "return count($sections) === 20 ? $sections : array();" in section_map


def test_editorial_v2_publication_fallback_is_closed_and_fail_closed() -> None:
    source = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    navigation = _load_json(EDITORIAL_NAVIGATION_PATH)
    expected = {
        article["article_id"]: article["production_slug"]
        for article in navigation["articles"]
    }
    assert len(expected) == 10 and len(set(expected.values())) == 10
    loader = source.split("function kurashinoshirube_article_bindings", 1)[1].split(
        "function kurashinoshirube_editorial_v2_publication_bindings", 1
    )[0]
    for required in (
        "kurashinoshirube_editorial_navigation()",
        "count($bindings) !== 10",
        "'article_id'",
        "'production_slug'",
        "'local_slug'",
        "'snapshot_id'",
        "'article_code'",
    ):
        assert required in loader

    fallback = source.split(
        "function kurashinoshirube_published_editorial_v2_identity", 1
    )[1].split("function kurashinoshirube_public_article_identity", 1)[0]
    for required in (
        "get_post_type($post_id) !== 'post'",
        "get_post_status($post_id) !== 'publish'",
        "kurashinoshirube_editorial_v2_publication_bindings()",
        "! kurashinoshirube_post_has_editorial_v2_root($post_id)",
        "substr_count($content, KURASHINOSHIRUBE_EDITORIAL_V2_ROOT) !== 1",
        "! str_ends_with($content, \"</div>\\n\")",
        "data-raos-article-id",
        "array_values(array_unique($matches[1])) !== array($article_id)",
    ):
        assert required in fallback
    assert fallback.count("return null;") >= 4

    shared = source.split(
        "function kurashinoshirube_public_article_identity", 1
    )[1].split("function kurashinoshirube_current_snapshot", 1)[0]
    assert "kurashinoshirube_bound_post_snapshot($post_id, false)" in shared
    assert "kurashinoshirube_published_editorial_v2_identity($post_id)" in shared


def _editorial_v2_public_identity(
    *, status: str, slug: str, content: str
) -> tuple[str, str] | None:
    """Executable mirror of the closed published Editorial V2 identity."""

    if status != "publish":
        return None
    article_id = dict(EDITORIAL_V2_PUBLICATION_BINDINGS).get(slug)
    root = '<div class="raos-editorial-v2">'
    if (
        article_id is None
        or not content.startswith(root)
        or content.count(root) != 1
        or not content.endswith("</div>\n")
    ):
        return None
    article_ids = list(
        dict.fromkeys(
            re.findall(
                r'\bdata-raos-article-id="([a-z0-9]+(?:-[a-z0-9]+)*)"',
                content,
            )
        )
    )
    return (article_id, slug) if article_ids == [article_id] else None


def _editorial_v2_canonical(
    *,
    upstream: str,
    snapshot_canonical: str | None,
    singular: bool,
    status: str,
    slug: str,
    content: str,
) -> str:
    if snapshot_canonical is not None:
        return snapshot_canonical
    identity = (
        _editorial_v2_public_identity(status=status, slug=slug, content=content)
        if singular
        else None
    )
    return (
        f"https://kurashinoshirube.com/{identity[1]}/"
        if identity is not None
        else upstream
    )


def _editorial_v2_robots(*, status: str, slug: str, content: str) -> str:
    identity = _editorial_v2_public_identity(
        status=status, slug=slug, content=content
    )
    if identity is not None and identity[1] == slug:
        return (
            "index, follow, max-image-preview:large, max-snippet:-1, "
            "max-video-preview:-1"
        )
    known_slugs = {item[0] for item in EDITORIAL_V2_PUBLICATION_BINDINGS}
    if (
        slug.startswith("raos-review-")
        or content.startswith('<div class="raos-editorial-v2">')
        or slug in known_slugs
    ):
        return "noindex, nofollow"
    return "upstream"


@pytest.mark.parametrize(("slug", "article_id"), EDITORIAL_V2_PUBLICATION_BINDINGS)
def test_canonical_fallback_accepts_each_closed_published_editorial_v2_identity(
    slug: str,
    article_id: str,
) -> None:
    content = (
        '<div class="raos-editorial-v2">'
        f'<a data-raos-article-id="{article_id}">x</a></div>\n'
    )
    identity = _editorial_v2_public_identity(
        status="publish", slug=slug, content=content
    )
    assert identity == (article_id, slug)
    assert _editorial_v2_canonical(
        upstream="https://upstream.invalid/",
        snapshot_canonical=None,
        singular=True,
        status="publish",
        slug=slug,
        content=content,
    ) == f"https://kurashinoshirube.com/{slug}/"
    assert _editorial_v2_robots(
        status="publish", slug=slug, content=content
    ) == (
        "index, follow, max-image-preview:large, max-snippet:-1, "
        "max-video-preview:-1"
    )


@pytest.mark.parametrize(
    ("case", "status", "slug", "content"),
    (
        (
            "draft",
            "draft",
            "carry-on-suitcase-comparison",
            '<div class="raos-editorial-v2">'
            '<i data-raos-article-id="st1703-first-suitcase-comparison"></i>'
            "</div>\n",
        ),
        (
            "unknown",
            "publish",
            "unknown-editorial-guide",
            '<div class="raos-editorial-v2">'
            '<i data-raos-article-id="unknown-editorial-guide"></i></div>\n',
        ),
        (
            "wrong-id",
            "publish",
            "carry-on-suitcase-comparison",
            '<div class="raos-editorial-v2">'
            '<i data-raos-article-id="wrong-article-id"></i></div>\n',
        ),
        (
            "duplicate-root",
            "publish",
            "carry-on-suitcase-comparison",
            '<div class="raos-editorial-v2">'
            '<div class="raos-editorial-v2">'
            '<i data-raos-article-id="st1703-first-suitcase-comparison"></i>'
            "</div></div>\n",
        ),
        (
            "trailing-content",
            "publish",
            "carry-on-suitcase-comparison",
            '<div class="raos-editorial-v2">'
            '<i data-raos-article-id="st1703-first-suitcase-comparison"></i>'
            "</div>\n<p>trailing</p>",
        ),
    ),
)
def test_canonical_fallback_preserves_upstream_for_invalid_identity(
    case: str,
    status: str,
    slug: str,
    content: str,
) -> None:
    del case
    assert _editorial_v2_public_identity(
        status=status, slug=slug, content=content
    ) is None
    assert _editorial_v2_canonical(
        upstream="https://upstream.invalid/",
        snapshot_canonical=None,
        singular=True,
        status=status,
        slug=slug,
        content=content,
    ) == "https://upstream.invalid/"
    assert _editorial_v2_robots(
        status=status, slug=slug, content=content
    ) == "noindex, nofollow"


def test_canonical_fallback_contract_prefers_snapshot_and_shares_robots_identity() -> None:
    source = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    canonical = source.split("function kurashinoshirube_filter_canonical", 1)[1].split(
        "function kurashinoshirube_filter_og_title", 1
    )[0]
    assert canonical.index("kurashinoshirube_current_snapshot()") < canonical.index(
        "kurashinoshirube_public_head_context()"
    )
    for required in (
        "$snapshot['canonical_url']",
        "kurashinoshirube_public_head_context()",
        "$context === null ? $value : $context['canonical_url']",
    ):
        assert required in canonical

    robot_filter = source.split("function kurashinoshirube_filter_robots", 1)[1].split(
        "add_filter('wpseo_robots'", 1
    )[0]
    assert "kurashinoshirube_public_article_identity($post_id)" in robot_filter
    assert "$status === 'publish'" in robot_filter
    assert "$identity['slug'] === $slug" in robot_filter

    contract = _load_json(CONTRACT_PATH)
    assert contract["head"]["metadata_owner"] == (
        "PRODUCTION_YOAST_SEO_FILTERED_BY_VALID_RAOS_SNAPSHOT_OR_CLOSED_"
        "PUBLIC_HEAD_CONTEXT_AND_CONFIG_READBACK"
    )
    assert contract["head"]["raos_metadata_delivery"] == (
        "PRODUCTION_YOAST_METADATA_FILTERS_WITH_LOCAL_PREVIEW_NO_YOAST_"
        "FALLBACK"
    )
    assert contract["head"]["local_preview_metadata_fallback"] == {
        "active_when": (
            "EXACT_RAOS_LOCAL_PREVIEW_AND_WPSEO_VERSION_UNDEFINED_AND_"
            "CLOSED_HEAD_CONTEXT_AND_VERIFIED_SOCIAL_IMAGE"
        ),
        "canonical_owner": "RAOS_THEME_AFTER_REMOVING_CORE_REL_CANONICAL",
        "document_title_owner": "WORDPRESS_PRE_GET_DOCUMENT_TITLE_FILTER",
        "fields": [
            "canonical",
            "meta_description",
            "og_description",
            "og_image",
            "og_title",
            "og_url",
        ],
        "production_effect": "NONE",
    }
    assert contract["head"]["canonical"] == {
        "editorial_v2_fallback": (
            "FIXED_SITE_ORIGIN_PLUS_SLUG_FOR_SINGULAR_PUBLISHED_"
            "CLOSED_PUBLIC_ARTICLE_IDENTITY"
        ),
        "invalid_or_unpublished_policy": "PRESERVE_UPSTREAM_VALUE",
        "snapshot_precedence": "VALID_BOUND_RAOS_SNAPSHOT",
    }

    content = (
        '<div class="raos-editorial-v2">'
        '<i data-raos-article-id="st1703-first-suitcase-comparison"></i>'
        "</div>\n"
    )
    assert _editorial_v2_canonical(
        upstream="https://upstream.invalid/",
        snapshot_canonical="https://snapshot.example/exact/",
        singular=True,
        status="publish",
        slug="carry-on-suitcase-comparison",
        content=content,
    ) == "https://snapshot.example/exact/"
    assert _editorial_v2_canonical(
        upstream="https://upstream.invalid/",
        snapshot_canonical=None,
        singular=False,
        status="publish",
        slug="carry-on-suitcase-comparison",
        content=content,
    ) == "https://upstream.invalid/"


def test_editorial_v2_unknown_identity_is_noindex_and_listing_ineligible() -> None:
    root = '<div class="raos-editorial-v2">'
    bindings = {
        "carry-on-suitcase-comparison": "st1703-first-suitcase-comparison",
        "portable-power-station-guide": "st1704-portable-power-station-guide",
        "countertop-dishwasher-for-small-households": (
            "st1704-countertop-dishwasher-for-small-households"
        ),
        "anker-solix-c300-c800-c1000-differences": (
            "st1704-anker-solix-c300-c800-c1000-differences"
        ),
        "compact-robot-vacuum-shortlist": "st1704-compact-robot-vacuum-shortlist",
        "carry-on-suitcase-under-100-seats": "carry-on-suitcase-under-100-seats",
        "front-open-carry-on-suitcase-with-stopper": (
            "front-open-carry-on-suitcase-with-stopper"
        ),
        "lightweight-carry-on-suitcase-under-3kg": (
            "lightweight-carry-on-suitcase-under-3kg"
        ),
        "roomba-mini-vs-switchbot-k11-pro": "roomba-mini-vs-switchbot-k11-pro",
        "solota-vs-rakua-mini-plus": "solota-vs-rakua-mini-plus",
    }

    def exact_identity(slug: str, content: str) -> bool:
        expected = bindings.get(slug)
        article_ids = set(
            re.findall(
                r'\bdata-raos-article-id="([a-z0-9]+(?:-[a-z0-9]+)*)"',
                content,
            )
        )
        return bool(
            expected
            and content.startswith(root)
            and content.endswith("</div>\n")
            and content.count(root) == 1
            and article_ids == {expected}
        )

    def listing_eligible(slug: str, content: str) -> bool:
        if slug.startswith("raos-review-"):
            return False
        if slug in bindings:
            return exact_identity(slug, content)
        return not content.startswith(root)

    def robots(slug: str, content: str) -> str:
        if exact_identity(slug, content):
            return "index, follow"
        if (
            slug.startswith("raos-review-")
            or content.startswith(root)
            or slug in bindings
        ):
            return "noindex, nofollow"
        return "original"

    cases = (
        (
            "unknown-editorial-guide",
            root
            + '<a data-raos-article-id="unknown-editorial-guide">x</a></div>\n',
            False,
            "noindex, nofollow",
        ),
        (
            "carry-on-suitcase-comparison",
            root
            + '<a data-raos-article-id="wrong-article-id">x</a></div>\n',
            False,
            "noindex, nofollow",
        ),
        ("ordinary-unrelated-post", "<p>ordinary article</p>\n", True, "original"),
    )
    for slug, content, expected_listing, expected_robots in cases:
        assert listing_eligible(slug, content) is expected_listing
        assert robots(slug, content) == expected_robots

    source = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    robot_filter = source.split("function kurashinoshirube_filter_robots", 1)[1].split(
        "add_filter('wpseo_robots'", 1
    )[0]
    listing_filter = source.split(
        "function kurashinoshirube_public_listing_post_is_eligible", 1
    )[1].split("function kurashinoshirube_public_listing_excluded_post_ids", 1)[0]
    assert "kurashinoshirube_post_has_editorial_v2_root($post_id)" in robot_filter
    assert (
        "return ! kurashinoshirube_post_has_editorial_v2_root($post_id);"
        in listing_filter
    )


def test_consent_defaults_are_opt_in_and_global() -> None:
    functions = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    assert functions.count(
        "add_filter('wp_get_consent_type', 'kurashinoshirube_wp_consent_type');"
    ) == 1
    assert "return 'optin';" in functions
    assert functions.count(
        "'wp_cookie_expiration',\n"
        "    'kurashinoshirube_wp_consent_cookie_expiration'"
    ) == 1
    assert "function kurashinoshirube_wp_consent_cookie_expiration(): int" in functions
    assert "return 365;" in functions
    assert functions.count(
        "'googlesitekit_consent_defaults',\n"
        "    'kurashinoshirube_site_kit_global_consent_defaults'"
    ) == 1
    consent_filter = functions.split(
        "function kurashinoshirube_site_kit_global_consent_defaults", 1
    )[1]
    assert "if (!is_array($defaults))" in consent_filter
    assert "unset($defaults['region']);" in consent_filter
    assert "$defaults['wait_for_update'] = 2000;" in consent_filter
    assert "return $defaults;" in consent_filter
    assert functions.count(
        "'script_loader_tag',\n"
        "    'kurashinoshirube_gate_site_kit_analytics_loader'"
    ) == 1
    analytics_filter = functions.split(
        "function kurashinoshirube_gate_site_kit_analytics_loader", 1
    )[1]
    assert "$handle !== 'google_gtagjs'" in analytics_filter
    assert "www.googletagmanager.com" in analytics_filter
    assert "'/gtag/js'" in analytics_filter
    assert 'data-raos-consent-gate="statistics"' in analytics_filter
    assert 'data-raos-consent-config="statistics"' in analytics_filter
    assert 'type="text/plain"' in analytics_filter
    assert "eligibleAtParse" not in analytics_filter
    assert "initialCookieYes" not in analytics_filter
    assert 'window.getCkyConsent' in analytics_filter
    assert 'window.wp_has_consent("statistics")' in analytics_filter
    assert 'window._googlesitekitConsents.analytics_storage==="granted"' in analytics_filter
    for event_name in (
        "wp_consent_type_defined",
        "wp_listen_for_consent_change",
        "cookieyes_consent_update",
    ):
        assert event_name in analytics_filter
    assert analytics_filter.count('data-cookieyes","cookieyes-analytics') == 2
    assert analytics_filter.index("config.replaceWith(configScript)") < (
        analytics_filter.index("analytics.src=source")
    )
    assert analytics_filter.index("analytics.src=source") < analytics_filter.index(
        "loader.replaceWith(analytics)"
    )
    assert "$loader_replacement_count !== 1" in analytics_filter
    assert "$config_replacement_count === 1" in analytics_filter
    assert "? $gated_tag" in analytics_filter
    assert "googlesitekit_analytics-4_tag_blocked" not in functions
    assert "googlesitekit_analytics-4_tag_block_on_consent" not in functions
    assert "gtag('consent'" not in functions
    assert "X-RAOS-Consent" not in functions


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


def test_variant_a_homepage_has_one_h1_explicit_navigation_and_nine_sections() -> None:
    header = (THEME_ROOT / "parts/header.html").read_text(encoding="utf-8")
    front = (THEME_ROOT / "templates/front-page.html").read_text(encoding="utf-8")

    assert header.count('"level":0') == 1
    assert "raos-skip-link" not in header
    assert header.count("<!-- wp:navigation-link ") == 4
    for label, url in (
        ("目的から探す", "/#categories"),
        ("選び方・比較記事", "/#featured"),
        ("新しい記事", "/#latest"),
        ("このサイトについて", "/#about"),
    ):
        assert (
            f'<!-- wp:navigation-link {{"label":"{label}","url":"{url}",'
            in header
        )
    assert header.count("<!-- wp:search ") == 1
    for search_setting in (
        '"label":"記事を検索"',
        '"showLabel":false',
        '"buttonPosition":"button-only"',
        '"buttonUseIcon":true',
        '"isSearchFieldHidden":true',
    ):
        assert search_setting in header

    css = (THEME_ROOT / "assets/theme.css").read_text(encoding="utf-8")
    expanded_search = (
        ".raos-site-header .raos-header-search:not("
        ".wp-block-search__searchfield-hidden)"
    )
    assert css.count(expanded_search) == 4
    assert f"{expanded_search} {{" in css
    assert "position: absolute;" in css.split(f"{expanded_search} {{", 1)[1].split(
        "}", 1
    )[0]
    assert "width: 100%;" in css.split(f"{expanded_search} {{", 1)[1].split(
        "}", 1
    )[0]
    assert "padding: 0.5rem clamp(1rem, 4vw, 2rem);" in css
    assert "):last-child:nth-child(odd) {" in css

    assert front.count('<main id="main-content"') == 1
    assert front.count("<h1") == 1
    assert front.count("</h1>") == 1
    assert '"level":1' not in front
    assert (
        '<h1 id="home-hero-title">暮らしの選択に、<br>'
        "たしかな道しるべを。</h1>"
    ) in front

    section_markers = [
        '<section class="raos-home-hero"',
        '<section class="raos-home-promise"',
        '<section class="raos-home-purpose',
        "[kurashinoshirube_featured_guide]",
        '<section class="raos-home-problems',
        '<section id="latest"',
        "[kurashinoshirube_published_clusters]",
        '<section class="raos-home-method',
        '<section class="raos-home-about',
    ]
    assert all(front.count(marker) == 1 for marker in section_markers)
    assert [front.index(marker) for marker in section_markers] == sorted(
        front.index(marker) for marker in section_markers
    )

    promise = front.split('<section class="raos-home-promise"', 1)[1].split(
        "</section>", 1
    )[0]
    assert "EDITORIAL PROMISE" in promise
    assert promise.count("<li><span>") == 3
    for heading in ("条件から比較する", "確認できる情報を使う", "向かない人も伝える"):
        assert f"<h3>{heading}</h3>" in promise

    purpose = front.split('<section class="raos-home-purpose', 1)[1].split(
        "</section>", 1
    )[0]
    for heading, anchor in (
        ("移動を軽やかに", "cluster-mobility"),
        ("家事の手間を減らす", "cluster-home"),
        ("もしもの時に備える", "cluster-ready"),
    ):
        assert purpose.count(f'href="#{anchor}"') == 1
        assert f"<h3>{heading}</h3>" in purpose

    assert front.count("[kurashinoshirube_featured_guide]") == 1
    assert front.count("[kurashinoshirube_published_clusters]") == 1
    assert front.count(
        '<!-- wp:query {"query":{"inherit":false,"perPage":4,'
        '"postType":"post","order":"desc","orderBy":"modified"}} -->'
    ) == 1
    assert "商品選定・評価は報酬条件とは切り離して行います。" in front
    assert "よく読まれている" not in front
    for unpublished_path in (
        "/portable-power-station-guide/",
        "/countertop-dishwasher-for-small-households/",
        "/anker-solix-c300-c800-c1000-differences/",
        "/compact-robot-vacuum-shortlist/",
    ):
        assert unpublished_path not in front


def test_fixed_featured_guide_requires_one_exact_public_article_identity() -> None:
    contract = _load_json(CONTRACT_PATH)
    assert contract["homepage_featured"] == {
        "article_id": "st1704-portable-power-station-guide",
        "exclude_from_latest": True,
        "local_preview_substitute": "LATEST_SYNTHETIC_POST_LAYOUT_ONLY",
        "selection": "FIXED_ARTICLE_ID_WITH_EXACT_PUBLIC_ARTICLE_IDENTITY",
    }

    source = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    assert source.count(
        "KURASHINOSHIRUBE_HOMEPAGE_FEATURED_ARTICLE_ID = "
        "'st1704-portable-power-station-guide'"
    ) == 1
    selector = source.split(
        "function kurashinoshirube_homepage_featured_post(): ?WP_Post", 1
    )[1].split("/** Resolve a bounded reader-facing section label", 1)[0]
    for eligibility_check in (
        "$article_id = KURASHINOSHIRUBE_HOMEPAGE_FEATURED_ARTICLE_ID;",
        "$binding = kurashinoshirube_article_bindings()[$article_id] ?? null;",
        "get_page_by_path($slug, OBJECT, 'post')",
        "kurashinoshirube_public_article_identity((int) $post->ID)",
        "get_post_status($post) === 'publish'",
        "$identity['article_id'] === $article_id",
        "get_permalink($post) === $expected_permalink",
    ):
        assert eligibility_check in selector
    assert selector.index("get_post_status($post) === 'publish'") < selector.index(
        "$cached = $post;"
    )
    assert selector.index("$identity['article_id'] === $article_id") < selector.index(
        "$cached = $post;"
    )

    renderer = source.split(
        "function kurashinoshirube_render_featured_guide", 1
    )[1].split("add_shortcode(", 1)[0]
    assert "|| ! is_front_page()" in renderer
    assert "if (! ($post instanceof WP_Post))" in renderer
    assert 'id="featured"' in renderer
    assert "人気順ではなく、いまの比較テーマを編集部が案内します。" in renderer
    assert "よく読まれている" not in renderer


def test_local_preview_substitution_is_locked_to_the_isolated_fixture_origin() -> None:
    source = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    guard = source.split(
        "function kurashinoshirube_local_preview_origin(): ?string", 1
    )[1].split("/**\n * Resolve the fixed featured article", 1)[0]
    assert source.count("RAOS_LOCAL_PREVIEW") == 2
    for boundary in (
        "defined('RAOS_LOCAL_PREVIEW')",
        "RAOS_LOCAL_PREVIEW !== true",
        "function_exists('wp_get_environment_type')",
        "wp_get_environment_type() !== 'local'",
        "defined('RAOS_WORDPRESS_PREVIEW_ORIGIN')",
        "#\\Ahttp://127\\.0\\.0\\.1:([0-9]{4,5})\\z#D",
        "home_url('/') !== RAOS_WORDPRESS_PREVIEW_ORIGIN . '/'",
        "site_url('/') !== RAOS_WORDPRESS_PREVIEW_ORIGIN . '/'",
    ):
        assert boundary in guard

    selector = source.split(
        "function kurashinoshirube_homepage_featured_post(): ?WP_Post", 1
    )[1].split("/** Resolve a bounded reader-facing section label", 1)[0]
    assert selector.count("get_posts(") == 1
    assert "if (! kurashinoshirube_is_local_preview())" in selector
    assert selector.index("if (! kurashinoshirube_is_local_preview())") < (
        selector.index("get_posts(")
    )
    for preview_constraint in (
        "'fields' => 'ids'",
        "'numberposts' => 1",
        "'orderby' => 'modified'",
        "'post_status' => 'publish'",
        "'post_type' => 'post'",
        "preg_match('/\\Alocal-preview-[a-z0-9-]+\\z/D', $slug) !== 1",
    ):
        assert preview_constraint in selector


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
    related = functions.split(
        "function kurashinoshirube_render_related_guides", 1
    )[1].split("add_shortcode(", 1)[0]
    assert "$identity = kurashinoshirube_public_article_identity($post_id);" in related
    assert "$identity['article_id']" in related
    assert "kurashinoshirube_related_article_map()" in related
    assert "kurashinoshirube_resolve_related_target($target_id)" in related
    assert "data-raos-to-article-id" in related
    assert 'data-raos-link-placement="related_navigation"' in related
    resolver = functions.split(
        "function kurashinoshirube_resolve_related_target", 1
    )[1].split("function kurashinoshirube_inject_contextual_guide", 1)[0]
    assert "$target_identity = kurashinoshirube_public_article_identity(" in resolver
    assert "$target_identity['article_id'] !== $target_id" in resolver
    assert "kurashinoshirube_current_snapshot()" not in related
    assert "kurashinoshirube_bound_post_snapshot(" not in related
    contract = _load_json(CONTRACT_PATH)
    assert contract["related_navigation"]["target_requirement"] == (
        "PUBLISHED_EXACT_SAME_ORIGIN_PERMALINK_WITH_CLOSED_PUBLIC_ARTICLE_IDENTITY"
    )

    contextual = functions.split(
        "function kurashinoshirube_inject_contextual_guide", 1
    )[1].split("add_filter('the_content'", 1)[0]
    assert "data-raos-to-article-id" in contextual
    assert 'data-raos-link-placement="article_body"' in contextual


def test_single_article_titles_are_wide_balanced_and_responsive() -> None:
    single = (THEME_ROOT / "templates/single.html").read_text(encoding="utf-8")
    css = (THEME_ROOT / "assets/theme.css").read_text(encoding="utf-8")
    editorial_css = (THEME_ROOT / "assets/editorial-v2.css").read_text(
        encoding="utf-8"
    )

    assert single.count(
        '<!-- wp:group {"align":"wide","className":"raos-article-title-grid"'
    ) == 1
    assert single.count(
        '<div class="wp-block-group alignwide raos-article-title-grid">'
    ) == 1
    assert "45rem" not in css.split(".raos-article-title-grid {", 1)[1].split(
        "}", 1
    )[0]

    for stylesheet, selector in (
        (css, ".raos-article-title-grid h1"),
        (editorial_css, ".raos-editorial-v2-page .raos-article-title-grid h1"),
    ):
        desktop = stylesheet.split(f"{selector} {{", 1)[1].split("}", 1)[0]
        assert "font-size: clamp(2.7rem, 3.5vw, 3.75rem);" in desktop
        assert "line-height: 1.22;" in desktop
        assert "text-wrap: balance;" in desktop
        assert "word-break: auto-phrase;" in desktop
        mobile = stylesheet.rsplit(f"{selector} {{", 1)[1].split("}", 1)[0]
        assert "font-size: clamp(1.9rem, 8.5vw, 2.15rem);" in mobile
        assert "line-height: 1.33;" in mobile

    for selector in (
        ".raos-article .wp-block-post-content h2",
        ".raos-editorial-v2 .section-heading h2",
        ".raos-editorial-v2 .editorial-body-section > h2",
    ):
        stylesheet = editorial_css if "editorial-v2" in selector else css
        rule = stylesheet.split(f"{selector}", 1)[1].split("}", 1)[0]
        assert "text-wrap: balance;" in rule
        assert "word-break: auto-phrase;" in rule


def test_related_navigation_is_generated_closed_and_contract_hashed() -> None:
    contract = _load_json(CONTRACT_PATH)
    related = contract["related_navigation"]
    assert isinstance(related, dict)
    navigation = _load_json(EDITORIAL_NAVIGATION_PATH)
    navigation_contract = contract["editorial_navigation"]
    assert navigation_contract["sha256"] == _sha256(EDITORIAL_NAVIGATION_PATH)
    assert navigation_contract["source_navigation_sha256"] == navigation[
        "source_navigation_sha256"
    ]
    assert navigation_contract["source_portfolio_sha256"] == navigation[
        "source_portfolio_sha256"
    ]
    source = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    hash_match = re.search(
        r"const KURASHINOSHIRUBE_EDITORIAL_NAVIGATION_SHA256 = '([0-9a-f]{64})';",
        source,
    )
    assert hash_match is not None
    assert hash_match.group(1) == navigation_contract["sha256"]
    assert related["owner"] == "EDITORIAL_V3_GENERATED_NAVIGATION"
    assert related["content_hash_scope"] == (
        "THEME_CHROME_OUTSIDE_WORDPRESS_POST_CONTENT"
    )
    articles = navigation["articles"]
    assert len(articles) == 10
    article_ids = {article["article_id"] for article in articles}
    for article in articles:
        targets = article["related_articles"]
        assert len(targets) >= related["minimum_targets_per_article"]
        assert len({target["article_id"] for target in targets}) == len(targets)
        assert {target["article_id"] for target in targets} <= article_ids - {
            article["article_id"]
        }
        relationships = [target["relationship"] for target in targets]
        if article["cluster_id"] == "preparedness":
            assert relationships.count("same_cluster") == 1
            assert "adjacent_context" in relationships
        else:
            assert relationships.count("same_cluster") >= 2
            assert set(relationships) == {"same_cluster"}


def test_homepage_cluster_contract_is_hash_bound_and_covers_all_articles() -> None:
    contract = _load_json(CONTRACT_PATH)
    homepage = contract["homepage_clusters"]
    navigation = _load_json(EDITORIAL_NAVIGATION_PATH)
    clusters = navigation["clusters"]
    assert homepage["source"] == "assets/editorial-navigation.v3.json#clusters"
    assert homepage["article_count"] == 10
    assert homepage["cluster_count"] == 3
    assert [cluster["cluster_id"] for cluster in clusters] == [
        "mobility",
        "household",
        "preparedness",
    ]
    observed_articles = [
        article_id for cluster in clusters for article_id in cluster["article_ids"]
    ]
    assert len(observed_articles) == 10
    assert len(set(observed_articles)) == 10
    assert set(observed_articles) == {
        article["article_id"] for article in navigation["articles"]
    }
    assert homepage["link_requirement"] == (
        contract["related_navigation"]["target_requirement"]
    )

    source = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    assert "function kurashinoshirube_homepage_clusters(): array" in source
    assert "kurashinoshirube_editorial_navigation()" in source
    assert "return count($seen) === 10 ? $configuration : array();" in source

    renderer = source.split(
        "function kurashinoshirube_render_published_clusters", 1
    )[1].split("add_shortcode(", 1)[0]
    assert "$cluster_body = $items === ''" in renderer
    assert "このテーマの記事は、根拠と公開条件の確認後に掲載します。" in renderer
    assert ". esc_html($cluster['heading']) . '</h3>' . $cluster_body" in renderer
    assert "if ($items === '') {\n            continue;" not in renderer


@pytest.mark.parametrize(
    ("slug_class", "snapshot_state", "expected"),
    (
        ("RAOS_REVIEW", "ANY", False),
        (
            "PORTFOLIO_FINAL",
            "PUBLIC_ARTICLE_IDENTITY_MISSING_OR_MISMATCH",
            False,
        ),
        (
            "PORTFOLIO_FINAL",
            "EXACT_STORED_SNAPSHOT_OR_EDITORIAL_V2_PUBLISHED_IDENTITY",
            True,
        ),
        ("UNRELATED_POST", "NOT_EVALUATED", True),
    ),
)
def test_public_listing_contract_matrix_is_fail_closed_for_pilot_routes(
    slug_class: str,
    snapshot_state: str,
    expected: bool,
) -> None:
    contract = _load_json(CONTRACT_PATH)
    policy = contract["public_listing_eligibility"]
    assert isinstance(policy, dict)
    matches = [
        row
        for row in policy["matrix"]
        if row["slug_class"] == slug_class and row["snapshot_state"] == snapshot_state
    ]
    assert matches == [
        {
            "eligible": expected,
            "slug_class": slug_class,
            "snapshot_state": snapshot_state,
        }
    ]
    assert policy["candidate_query"] == {
        "max_candidates_per_slot": 2,
        "max_rows": 20,
        "post_type": "post",
        "query_limit": 21,
        "slug_classes": [
            "raos-review-*",
            "editorial_v2_publication_bindings[].slug",
            'raw_content_prefix:<div class="raos-editorial-v2">',
        ],
        "slot_count": 10,
    }
    assert policy["candidate_overflow_policy"] == (
        "LOOKUP_FAILURE_WHEN_RESULT_COUNT_EXCEEDS_MAX_ROWS"
    )
    assert policy["query_cache"] == "REQUEST_LOCAL_ONLY"
    assert policy["lookup_failure_policy"] == (
        "SUPPRESS_POST_SITEMAP_AND_FRONT_PAGE_POST_RESULTS"
    )
    assert policy["lookup_success_requirement"] == (
        "GET_RESULTS_ARRAY_AND_WPDB_LAST_ERROR_EMPTY_STRING"
    )
    assert policy["snapshot_validator"] == (
        "kurashinoshirube_public_article_identity(post_id)"
    )


def test_sitemap_and_front_page_share_one_public_listing_exclusion_policy() -> None:
    source = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    contract = _load_json(CONTRACT_PATH)
    policy = contract["public_listing_eligibility"]
    assert isinstance(policy, dict)
    assert contract["publication_authority"] == "NONE"
    assert policy["consumers"] == {
        "front_page_latest_posts": {
            "additional_exclusion": "FIXED_FEATURED_POST_WHEN_ELIGIBLE",
            "filter": "query_loop_block_query_vars",
            "merge_target": "post__not_in",
        },
        "yoast_sitemap": {
            "filter": "wpseo_exclude_from_sitemap_by_post_ids",
        },
    }
    assert policy["existing_exclusion_policy"] == (
        "PRESERVE_POSITIVE_POST_IDS_AND_DEDUPLICATE"
    )

    eligibility = source.split(
        "function kurashinoshirube_public_listing_post_is_eligible", 1
    )[1].split("function kurashinoshirube_public_listing_excluded_post_ids", 1)[0]
    assert "strpos($slug, 'raos-review-') === 0" in eligibility
    assert "kurashinoshirube_editorial_v2_publication_bindings()" in eligibility
    assert "kurashinoshirube_public_article_identity($post_id)" in eligibility
    assert "($identity['article_id'] ?? null) === $article_id" in eligibility
    assert "! kurashinoshirube_post_has_editorial_v2_root($post_id)" in eligibility
    assert eligibility.count("return false;") == 1
    assert eligibility.count("return true;") == 0

    resolver = source.split(
        "function kurashinoshirube_public_listing_excluded_post_ids", 1
    )[1].split("function kurashinoshirube_merge_public_listing_exclusions", 1)[0]
    assert "): ?array" in resolver
    assert "static $resolved = false;" in resolver
    assert "static $cached = null;" in resolver
    assert "if ($resolved)" in resolver
    assert "$resolved = true;" in resolver
    assert '"SELECT ID, post_name FROM {$wpdb->posts} "' in resolver
    assert '"WHERE post_type = %s AND (post_name LIKE %s "' in resolver
    assert (
        '"OR post_name IN ({$placeholders}) OR post_content LIKE %s) "' in resolver
    )
    assert '"ORDER BY ID ASC LIMIT %d"' in resolver
    assert "$wpdb->esc_like('raos-review-') . '%'" in resolver
    assert "$wpdb->esc_like(\n        KURASHINOSHIRUBE_EDITORIAL_V2_ROOT" in resolver
    assert "$max_candidates_per_slot = 2;" in resolver
    assert (
        "$max_candidate_rows = count($final_slugs) * $max_candidates_per_slot;"
        in resolver
    )
    assert "$query_row_limit = $max_candidate_rows + 1;" in resolver
    assert "array($editorial_root_like, $query_row_limit)" in resolver
    assert resolver.count("$wpdb->get_results($query)") == 1
    assert "! isset($wpdb->last_error)" in resolver
    assert "! is_string($wpdb->last_error)" in resolver
    assert "$wpdb->last_error !== ''" in resolver
    assert "count($rows) > $max_candidate_rows" in resolver
    assert "kurashinoshirube_public_listing_post_is_eligible(" in resolver
    assert "return $cached;" in resolver
    assert resolver.count("return null;") >= 4

    assert source.count("'wpseo_exclude_from_sitemap_by_post_ids'") == 1
    assert source.count("'query_loop_block_query_vars'") == 1
    sitemap = source.split("function kurashinoshirube_sitemap_exclude_post_ids", 1)[
        1
    ].split("/** Exclude the same post IDs", 1)[0]
    latest = source.split(
        "function kurashinoshirube_filter_front_page_latest_query", 1
    )[1].split("/** Keep the sitemap", 1)[0]
    assert "kurashinoshirube_merge_public_listing_exclusions($post_ids)" in sitemap
    assert "if (! is_front_page())" in latest
    assert "$query['post__not_in'] ?? array()" in latest
    assert "$featured = kurashinoshirube_homepage_featured_post();" in latest
    assert "if ($featured instanceof WP_Post)" in latest
    assert "$requested_exclusions[] = (int) $featured->ID;" in latest
    assert "kurashinoshirube_merge_public_listing_exclusions(" in latest
    assert "$query['post__in'] = array(0);" in latest
    assert latest.index("$requested_exclusions[] = (int) $featured->ID;") < (
        latest.index("kurashinoshirube_merge_public_listing_exclusions(")
    )
    assert latest.index("$query['post__in'] = array(0);") < latest.index(
        "$query['post__not_in'] = $excluded;"
    )
    post_type = source.split("function kurashinoshirube_sitemap_exclude_post_type", 1)[
        1
    ].split("function kurashinoshirube_sitemap_exclude_taxonomy", 1)[0]
    assert "$post_type === 'post'" in post_type
    assert "kurashinoshirube_public_listing_excluded_post_ids() === null" in post_type
    assert "pre_get_posts" not in source
    assert "wp_cache_" not in resolver


def test_wpdb_errors_and_candidate_overflow_fail_closed_for_consumers() -> None:
    """Model SQL-error and sentinel-overflow shapes for both consumers."""

    contract = _load_json(CONTRACT_PATH)
    policy = contract["public_listing_eligibility"]
    assert isinstance(policy, dict)
    candidate_query = policy["candidate_query"]
    assert isinstance(candidate_query, dict)
    slot_count = candidate_query["slot_count"]
    max_candidates_per_slot = candidate_query["max_candidates_per_slot"]
    max_rows = candidate_query["max_rows"]
    query_limit = candidate_query["query_limit"]
    assert isinstance(slot_count, int) and slot_count == 10
    assert isinstance(max_candidates_per_slot, int) and max_candidates_per_slot == 2
    assert isinstance(max_rows, int) and max_rows == 20
    assert max_rows == slot_count * max_candidates_per_slot
    assert isinstance(query_limit, int) and query_limit == max_rows + 1

    def modeled_lookup(rows: object, last_error: object) -> list[int] | None:
        if not isinstance(last_error, str) or last_error != "":
            return None
        if not isinstance(rows, list) or len(rows) > max_rows:
            return None
        return []

    lookup = modeled_lookup([], "simulated SQL error")
    assert lookup is None
    sitemap_post_type_excluded = lookup is None
    front_page_post_in = [0] if lookup is None else None
    assert sitemap_post_type_excluded
    assert front_page_post_in == [0]

    assert modeled_lookup([], "") == []
    assert modeled_lookup([{} for _ in range(max_rows)], "") == []

    overflow_lookup = modeled_lookup([{} for _ in range(query_limit)], "")
    assert overflow_lookup is None
    overflow_sitemap_post_type_excluded = overflow_lookup is None
    overflow_front_page_post_in = [0] if overflow_lookup is None else None
    assert overflow_sitemap_post_type_excluded
    assert overflow_front_page_post_in == [0]
    assert policy["candidate_overflow_policy"] == (
        "LOOKUP_FAILURE_WHEN_RESULT_COUNT_EXCEEDS_MAX_ROWS"
    )


def test_bound_snapshot_rejects_excerpt_mismatch() -> None:
    source = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    bound = source.split("function kurashinoshirube_bound_post_snapshot", 1)[1].split(
        "/** Bind the singular presentation", 1
    )[0]
    assert "$excerpt = get_post_field('post_excerpt', $post_id, 'raw');" in bound
    assert "! is_string($excerpt)" in bound
    assert "$payload['description'] !== $excerpt" in bound

    _, wrapper = _valid_snapshot()
    payload = wrapper["payload"]
    assert isinstance(payload, dict)
    exact_excerpt = payload["description"]
    assert isinstance(exact_excerpt, str)
    assert payload["description"] == exact_excerpt
    assert payload["description"] != exact_excerpt + "改変"

    contract = _load_json(CONTRACT_PATH)
    snapshot = contract["snapshot"]
    assert isinstance(snapshot, dict)
    assert snapshot["excerpt_binding"] == (
        "EXACT_WORDPRESS_POST_EXCERPT_EQUALS_DESCRIPTION_RAW_UTF8"
    )


def test_footer_removes_the_broken_subscription_link() -> None:
    footer = (THEME_ROOT / "parts/footer.html").read_text(encoding="utf-8")
    assert "/subscribe/" not in footer
    assert "新着案内を受け取る" not in footer
    assert footer.count('"url":"/#about"') == 1
    assert "/about-ad-policy/" in footer


def test_editorial_footer_keeps_shared_layout_and_safe_token_fallbacks() -> None:
    css = (THEME_ROOT / "assets/theme.css").read_text(encoding="utf-8")
    home_suffixes = sorted(
        suffix.strip()
        for suffix in re.findall(r"\.raos-home-v2-page \.raos-footer([^,{]*)", css)
    )
    editorial_suffixes = sorted(
        suffix.strip()
        for suffix in re.findall(
            r"\.raos-editorial-v2-page \.raos-footer([^,{]*)", css
        )
    )
    policy_suffixes = sorted(
        suffix.strip()
        for suffix in re.findall(
            r"\.raos-policy-v3-page \.raos-footer([^,{]*)", css
        )
    )
    assert len(home_suffixes) >= 31
    assert editorial_suffixes == home_suffixes
    assert policy_suffixes == home_suffixes
    assert ".raos-policy-v3-page .wp-site-blocks > footer" in css
    for fallback in (
        "var(--raos-home-ink, var(--raos-ink))",
        "var(--raos-home-inverse, #f7f2e9)",
        "var(--raos-home-content, 76rem)",
        "var(--raos-home-clay, var(--raos-warm))",
    ):
        assert fallback in css


def test_content_is_visible_without_javascript() -> None:
    css = (THEME_ROOT / "assets/theme.css").read_text(encoding="utf-8")
    functions = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    assert not (THEME_ROOT / "assets/theme.js").exists()
    assert functions.count("wp_enqueue_script(") == 1
    assert "kurashinoshirube-measurement-v1" in functions
    assert "raos_editorial_measurement_enabled()" in functions
    verifier = functions.split(
        "function kurashinoshirube_verified_asset_uri", 1
    )[1].split("function kurashinoshirube_bound_post_snapshot", 1)[0]
    assert "assets/measurement\\.js" in verifier
    measurement = (THEME_ROOT / "assets/measurement.js").read_text(encoding="utf-8")
    assert "preventDefault" not in measurement
    assert "document.documentElement" not in measurement
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
        "object-fit: contain",
        "width: auto",
    ):
        assert declaration in rule
    for forbidden in ("transform", "width: 100%", "height: 100%"):
        assert forbidden not in rule
    editorial_css = (THEME_ROOT / "assets/editorial-v2.css").read_text(
        encoding="utf-8"
    )
    editorial_image = editorial_css.split(
        ".raos-editorial-v2 .product-profile figure img {", 1
    )[1].split("}", 1)[0]
    assert "object-fit: contain;" in editorial_image
    assert "object-fit: cover;" not in editorial_image
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
    assert comparison["mobile_breakpoint_max_px"] == 768
    assert comparison["event_attributes"] == [
        "data-raos-article-id",
        "data-raos-placement=comparison_table",
    ]
    measurement = contract["measurement"]
    assert measurement["analytics_transmission_added"] is True
    assert measurement["default_enabled"] is False
    assert measurement["consent_gate"] == [
        "COOKIEYES_EXPLICIT_ANALYTICS_GRANTED",
        "WP_CONSENT_API_STATISTICS_GRANTED",
        "SITE_KIT_ANALYTICS_STORAGE_GRANTED",
    ]
    assert measurement["navigation_behavior"] == (
        "NO_PREVENT_DEFAULT_NO_AWAIT_SEND_BEACON_OR_KEEPALIVE"
    )
    assert contract["homepage_section_order"] == [
        "ヒーロー",
        "編集方針の約束",
        "暮らしの目的",
        "今、読んでほしい選び方",
        "困りごとから探す",
        "新しい記事",
        "目的別の記事",
        "商品選びの方法",
        "このサイトについて",
    ]
    cta = markup["affiliate_cta"]
    assert cta["exact_label"] == "楽天市場で現在の価格・在庫・カラーを見る"
    assert cta["data_attributes"] == [
        "data-raos-article-id",
        "data-raos-cta-id",
        "data-raos-offer-id",
        "data-raos-placement",
        "data-raos-product-id",
        "data-raos-rakuten-provider-slot-id",
        "data-raos-snapshot-id",
    ]
    assert sorted(cta["rel_tokens"]) == ["nofollow", "sponsored"]
    assert cta["required_host_provenance"].startswith("VALIDATED_RAKUTEN_")
    css = (THEME_ROOT / "assets/theme.css").read_text(encoding="utf-8")
    assert ".raos-comparison:focus-visible" in css
    assert ".raos-comparison__table-view" in css
    assert ".raos-comparison__cards" in css
    assert ".raos-comparison-card dl > div" in css
    assert "@media (max-width: 48rem)" in css
    assert '[tabindex="0"]):focus-visible' in css


def test_article_type_density_ctas_and_cmp_are_responsive_without_home_scope() -> None:
    css = (THEME_ROOT / "assets/theme.css").read_text(encoding="utf-8")
    editorial_css = (THEME_ROOT / "assets/editorial-v2.css").read_text(
        encoding="utf-8"
    )

    for selector in (
        ".raos-breadcrumb",
        ".raos-article-hero-image figcaption",
        ".raos-evidence-badge",
    ):
        rule = css.split(f"{selector} {{", 1)[1].split("}", 1)[0]
        assert "font-size: 0.8rem;" in rule
    for selector in (
        ".raos-article .raos-condition-label",
        ".raos-article-facts dt",
        ".raos-comparison thead th",
    ):
        rule = css.split(f"{selector} {{", 1)[1].split("}", 1)[0]
        assert "font-size: 0.875rem;" in rule
    assert "font-size: 0.875rem;" in css.split(
        ".raos-product-card__facts {", 1
    )[1].split("}", 1)[0]

    editorial_minimum_selectors = (
        ".raos-editorial-v2-page .raos-breadcrumbs",
        ".raos-editorial-v2-page .raos-article-category",
        ".raos-editorial-v2 .hero-photo figcaption",
        ".raos-editorial-v2 .section-number",
        ".raos-editorial-v2 .comparison-table td small",
        ".raos-editorial-v2 .source-list small",
    )
    for selector in editorial_minimum_selectors:
        rule = editorial_css.split(f"{selector} {{", 1)[1].split("}", 1)[0]
        assert "font-size: 0.8rem;" in rule
    for selector in (
        ".raos-editorial-v2 .article-meta dt",
        ".raos-editorial-v2 .comparison-table thead th",
        ".raos-editorial-v2 .comparison-table tbody th",
    ):
        rule = editorial_css.split(selector, 1)[1].split("}", 1)[0]
        assert "font-size: 0.875rem;" in rule
    editorial_root_match = re.search(
        r"^\.raos-editorial-v2 \{(?P<body>.*?)^\}",
        editorial_css,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert editorial_root_match is not None
    editorial_root = editorial_root_match.group("body")
    assert "font-size: 1rem;" in editorial_root
    verified_image = editorial_css.split(
        'img[data-raos-product-image-state="verified"] {', 1
    )[1].split("}", 1)[0]
    assert "width: 128px;" in verified_image
    assert "height: 128px;" in verified_image

    assert css.count("@media (max-width: 48rem)") >= 2
    comparison_mobile = css.rsplit("@media (max-width: 48rem)", 1)[1]
    assert ".raos-comparison__table-view {\n    display: none;" in comparison_mobile
    assert ".raos-comparison__cards {\n    display: grid;" in comparison_mobile
    editorial_mobile = editorial_css.split("@media (max-width: 48rem)", 1)[1]
    assert (
        ".raos-editorial-v2 .comparison-table-wrap:not(.raos-comparison),\n"
        "  .raos-editorial-v2 .comparison-table-wrap > table,\n"
        "  .raos-editorial-v2 .comparison-table-wrap > "
        ".raos-comparison__table-view {\n    display: none;"
        in editorial_mobile
    )
    assert ".raos-editorial-v2 .comparison-cards {\n    display: block;" in (
        editorial_mobile
    )

    cta = css.split(".raos-cta {", 1)[1].split("}", 1)[0]
    for declaration in (
        "line-height: 1.45;",
        "max-width: 100%;",
        "overflow-wrap: anywhere;",
        "white-space: normal;",
    ):
        assert declaration in cta
    final_summary = css.split(
        '.raos-decision-summary > ul > li > .raos-cta[data-raos-placement="final_summary"] {',
        1,
    )[1].split("}", 1)[0]
    assert "grid-column: 1 / -1;" in final_summary
    assert "width: min(100%, 26rem);" in final_summary
    editorial_cta = editorial_css.split(
        ".raos-editorial-v2 .rakuten-cta {", 1
    )[1].split("}", 1)[0]
    assert "white-space: normal;" in editorial_cta
    assert "overflow-wrap: anywhere;" in editorial_cta

    cmp = css.split("/* CookieYes 3.5.5:", 1)[1].split(
        "@media (forced-colors: active)", 1
    )[0]
    assert "@media (min-width: 22.5rem) and (max-width: 27.5rem)" in cmp
    assert "body.single-post .cky-consent-container.cky-box-bottom-left" in cmp
    assert "flex-direction: row !important;" in cmp
    assert "min-height: 44px !important;" in cmp
    assert "max-width: calc(100vw - 32px) !important;" in cmp
    assert "width: 320px !important;" in cmp
    assert "order:" not in cmp
    assert "content:" not in cmp
    assert ".cky-" not in editorial_css


def test_home_tablet_masthead_keeps_the_wordmark_on_its_own_row() -> None:
    css = (THEME_ROOT / "assets/theme.css").read_text(encoding="utf-8")
    tablet = css.split(
        "@media (min-width: 37.501rem) and (max-width: 51.25rem)", 1
    )[1].split("@media (max-width: 37.5rem)", 1)[0]

    masthead = tablet.split(".raos-home-v2-page .raos-masthead {", 1)[1].split(
        "}", 1
    )[0]
    assert "grid-template-columns: minmax(0, 1fr);" in masthead
    wordmark_link = tablet.split(
        ".raos-home-v2-page .raos-wordmark a {", 1
    )[1].split("}", 1)[0]
    assert "white-space: nowrap;" in wordmark_link
    actions = tablet.split(
        ".raos-home-v2-page .raos-masthead__actions {", 1
    )[1].split("}", 1)[0]
    assert "justify-self: stretch;" in actions
    assert "width: 100%;" in actions


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
    assert ".raos-home-v2 :where(a, button, input, summary):focus-visible" in css
    assert ".raos-masthead nav a" in css
    assert ".raos-wordmark:focus-visible" in css
    assert "outline-color: var(--raos-focus)" in css
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in css
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


def test_visual_fixtures_are_explicitly_non_production_and_closed() -> None:
    fixture_root = THEME_ROOT.parents[1] / "visual-fixtures"
    home = (fixture_root / "home.html").read_text(encoding="utf-8")
    article = (fixture_root / "article.html").read_text(encoding="utf-8")
    for payload in (home, article):
        assert "LOCAL STATIC THEME FIXTURE" in payload
        assert "本番表示ではありません" in payload
        assert "<script" not in payload.casefold()
        assert "javascript:" not in payload.casefold()
    assert "<span>暮らしの道具を、</span><span>根拠から選ぶ。</span>" in home
    assert "よく読まれている" not in home
    assert "中立画像" in home
    assert "検証済み画像なし" in article
    assert "UNKNOWN：未確認" in article
    assert "在庫なしfixture・CTAなし" in article
    assert "長い商品名" in article
    assert 'data-raos-placement="comparison_table"' in article


def test_raos_visual_evidence_is_hash_bound_and_never_calls_local_after_production() -> None:
    evidence_root = THEME_ROOT.parents[1] / "visual-evidence"
    manifest = json.loads((evidence_root / "manifest.v1.json").read_text("utf-8"))
    assert manifest["schema"] == "ST1704_RAOS_VISUAL_EVIDENCE_V1"
    assert manifest["competitor_screenshots_committed"] is False
    assert manifest["production_claim_for_after"] is False
    assert len(manifest["captures"]) == 7
    for capture in manifest["captures"]:
        payload = (evidence_root / capture["path"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == capture["sha256"]
        assert capture["viewport"]["width"] in {390, 1440}
        if capture["state"].startswith("LOCAL_STATIC_AFTER"):
            assert capture["source"].startswith("../visual-fixtures/")
            assert capture["http_status"] is None


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


def test_yoast_is_the_production_owner_with_one_bounded_local_fallback() -> None:
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
    static_templates = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
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
        assert duplicate not in static_templates

    fallback = source.split(
        "function kurashinoshirube_emit_local_fallback_head(): void", 1
    )[1].split(
        "add_action('wp_head', 'kurashinoshirube_emit_local_fallback_head'", 1
    )[0]
    assert "defined('WPSEO_VERSION')" in fallback
    assert "! kurashinoshirube_is_local_preview()" in fallback
    assert "kurashinoshirube_public_head_context()" in fallback
    assert "kurashinoshirube_verified_asset_uri(" in fallback
    assert fallback.index("$context === null || $image === null") < fallback.index(
        "remove_action('wp_head', 'rel_canonical');"
    )
    assert source.count('<meta name="description"') == 1
    assert source.count('<link rel="canonical"') == 1
    for property_name in ("og:title", "og:description", "og:url", "og:image"):
        assert source.count(f'<meta property="{property_name}"') == 1
    for forbidden in ('name="twitter:', "og:type"):
        assert forbidden not in fallback


def test_local_head_fallback_preserves_core_title_and_unrelated_routes() -> None:
    source = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    title_filter = source.split(
        "function kurashinoshirube_filter_local_document_title", 1
    )[1].split("add_filter('wpseo_title'", 1)[0]
    assert "defined('WPSEO_VERSION')" in title_filter
    assert "! kurashinoshirube_is_local_preview()" in title_filter
    assert "kurashinoshirube_public_head_context()" in title_filter
    assert "$context === null ? $title : $context['title']" in title_filter
    assert source.count("add_filter(\n    'pre_get_document_title'") == 1
    assert source.count("<title") == 0


def test_verified_asset_uri_accepts_only_the_exact_local_theme_base() -> None:
    source = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    verifier = source.split(
        "function kurashinoshirube_verified_asset_uri", 1
    )[1].split("function kurashinoshirube_bound_post_snapshot", 1)[0]
    local = (
        "$local_origin = kurashinoshirube_local_preview_origin();"
    )
    assert verifier.count(local) == 1
    assert (
        "$base === $local_origin\n"
        "            . '/wp-content/themes/kurashinoshirube-child'"
    ) in verifier
    assert verifier.index(local) < verifier.index("$parts = wp_parse_url($base);")
    for production_boundary in (
        "($parts['scheme'] ?? null) !== 'https'",
        "($parts['host'] ?? null) !== 'kurashinoshirube.com'",
        "array_flip(array('port', 'user', 'pass', 'query', 'fragment'))",
    ):
        assert production_boundary in verifier


def test_closed_head_contexts_cover_home_articles_and_exact_policy_excerpts() -> None:
    source = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    contract = _load_json(CONTRACT_PATH)
    pages = _load_json(
        REPOSITORY_ROOT
        / "changes/wordpress-local-preview-v1/fixtures/pages.json"
    )["pages"]
    assert contract["head"]["closed_head_contexts"] == {
        "article": "EXACT_EDITORIAL_V3_PUBLIC_IDENTITY_PLUS_CLEAN_TITLE_AND_EXCERPT",
        "fixed_page": "EXACT_THREE_POLICY_SLUG_TITLE_EXCERPT_RECORDS",
        "home": "FIXED_SITE_TITLE_AND_DESCRIPTION",
    }
    assert len(pages) == 3
    for page in pages:
        assert page["slug"] in source
        assert page["title"] in source
        assert page["excerpt"] in source
    resolver = source.split(
        "function kurashinoshirube_public_head_context(): ?array", 1
    )[1].split("function kurashinoshirube_filter_snapshot_value", 1)[0]
    for required in (
        "is_front_page()",
        "is_singular('post')",
        "is_singular('page')",
        "kurashinoshirube_public_article_identity($post_id)",
        "get_post_field('post_excerpt', $post_id, 'raw')",
        "get_post_status($post_id) !== 'publish'",
    ):
        assert required in resolver
    assert "kurashinoshirube_public_head_context()" in source.split(
        "function kurashinoshirube_filter_description", 1
    )[1].split("add_filter('wpseo_title'", 1)[0]


def test_document_title_has_one_conditional_owner_and_core_fallback() -> None:
    source = (THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    contract = _load_json(CONTRACT_PATH)
    deduplication = contract["head"]["document_title_deduplication"]
    assert deduplication == {
        "active_when": "WPSEO_VERSION_DEFINED",
        "hook": "wp_head",
        "hook_priority": 0,
        "removed_priority_1_callbacks": [
            "_wp_render_title_tag",
            "_block_template_render_title_tag",
            "gutenberg_render_title_tag",
        ],
    }
    assert contract["head"]["document_title_owner"] == (
        "YOAST_WHEN_ACTIVE_OTHERWISE_WORDPRESS_OR_GUTENBERG_FALLBACK"
    )
    assert source.count("add_theme_support('title-tag');") == 1
    assert source.count(
        "function kurashinoshirube_select_document_title_owner(): void"
    ) == 1
    owner = source.split(
        "function kurashinoshirube_select_document_title_owner(): void", 1
    )[1].split("add_action(", 1)[0]
    assert "if (! defined('WPSEO_VERSION'))" in owner
    for callback in deduplication["removed_priority_1_callbacks"]:
        assert owner.count(f"'{callback}'") == 1
    assert "remove_action('wp_head', $callback, 1);" in owner
    assert "else" not in owner
    assert source.count(
        "'wp_head',\n"
        "    'kurashinoshirube_select_document_title_owner',\n"
        "    0"
    ) == 1
    assert source.count(
        "'after_setup_theme',\n"
        "    'kurashinoshirube_select_document_title_owner'"
    ) == 0


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
    values = source.split(
        "function kurashinoshirube_structured_data_article_values", 1
    )[1].split("function kurashinoshirube_emit_json_ld", 1)[0]
    assert "! is_singular('post')" in values
    assert "$snapshot = kurashinoshirube_current_snapshot();" in values
    assert "if ($snapshot !== null)" in values
    assert "kurashinoshirube_published_editorial_v2_identity($post_id)" in values
    assert "get_post_field('post_title', $post_id, 'raw')" in values
    assert "get_post_field('post_excerpt', $post_id, 'raw')" in values
    assert "get_post_field('post_name', $post_id, 'raw')" in values
    assert "kurashinoshirube_is_clean_text($title, 8, 100)" in values
    assert "kurashinoshirube_is_clean_text($description, 30, 180)" in values
    assert (
        "KURASHINOSHIRUBE_SITE_ORIGIN . '/' . $slug . '/'" in values
    )
    emitter = source.split("function kurashinoshirube_emit_json_ld", 1)[1].split(
        "add_action('wp_head', 'kurashinoshirube_emit_json_ld'", 1
    )[0]
    assert "kurashinoshirube_public_head_context()" in emitter
    assert "$context['kind'] === 'article'" in emitter
    assert "array('article', 'fixed_page')" in emitter
    assert "kurashinoshirube_is_nullable_timestamp($published)" in emitter
    assert "kurashinoshirube_is_nullable_timestamp($modified)" in emitter
    assert "strcmp($modified, $published) < 0" in emitter
    for flag in (
        "JSON_HEX_TAG",
        "JSON_HEX_AMP",
        "JSON_HEX_APOS",
        "JSON_HEX_QUOT",
        "JSON_UNESCAPED_SLASHES",
        "JSON_UNESCAPED_UNICODE",
    ):
        assert flag in emitter
    assert head["allowed_json_ld_types"] == [
        "Article",
        "BreadcrumbList",
        "ListItem",
        "Organization",
        "WebSite",
    ]
    for schema_type in head["forbidden_json_ld_types"]:
        assert f"'@type' => '{schema_type}'" not in source
    assert head["structured_data_article_values"] == {
        "editorial_v2": (
            "CLOSED_PUBLISHED_IDENTITY_PLUS_CLEAN_RAW_TITLE_8_TO_100_AND_"
            "EXCERPT_30_TO_180_WITH_FIXED_ORIGIN_CANONICAL"
        ),
        "legacy": "VALID_BOUND_RAOS_SNAPSHOT",
        "unknown_or_invalid": "NO_OUTPUT",
    }
    assert head["structured_data_contexts"] == {
        "article": ["Article", "BreadcrumbList", "Organization", "WebSite"],
        "fixed_page": ["BreadcrumbList", "Organization", "WebSite"],
        "home": ["Organization", "WebSite"],
        "unknown_or_invalid": [],
    }


def test_editorial_v2_structured_data_dynamic_values_are_bounded() -> None:
    fixture = _load_json(
        REPOSITORY_ROOT / "changes/wordpress-local-preview-v1/fixtures/posts.json"
    )
    navigation = _load_json(EDITORIAL_NAVIGATION_PATH)
    sections = {
        article["production_slug"]: article["category_label"]
        for article in navigation["articles"]
    }
    assert len(sections) == 10

    def clean(value: str, minimum: int, maximum: int) -> bool:
        return bool(
            value == value.strip()
            and minimum <= len(value) <= maximum
            and re.search(r"[\x00-\x1f\x7f]", value) is None
            and re.search(r"<[^>]*>", value) is None
        )

    posts = fixture["posts"]
    assert isinstance(posts, list) and len(posts) == 10
    for post in posts:
        assert isinstance(post, dict)
        slug = str(post["slug"]).removeprefix("local-preview-")
        assert slug in sections
        assert clean(str(post["title"]), 8, 100)
        assert clean(str(post["excerpt"]), 30, 180)
        assert f"https://kurashinoshirube.com/{slug}/".startswith(
            "https://kurashinoshirube.com/"
        )

    for unsafe, minimum, maximum in (
        (" <script>alert(1)</script>", 8, 100),
        ("safe-title\ncontrol", 8, 100),
        ("x" * 101, 8, 100),
        ("x" * 29, 30, 180),
        ("x" * 181, 30, 180),
    ):
        assert clean(unsafe, minimum, maximum) is False


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
        "INSTALLED_FILES_NOT_VERIFIED_AGAINST_OFFICIAL_CHECKSUMS",
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
    assert checksum == {
        "manifest_byte_length": 343370,
        "manifest_sha256": (
            "1773aaadf88827311b488877c069aefcb6422e8dc6d5a7f50c1bd492d34bf85f"
        ),
        "observed_at": "2026-08-25T16:36:44Z",
        "sha256_file_count": 1952,
        "status": "AVAILABLE_HTTP_200",
        "url": (
            "https://downloads.wordpress.org/plugin-checksums/wordpress-seo/28.3.json"
        ),
    }
    assert lock["installed_file_verification"] == {
        "authority": "HUMAN_WORDPRESS_OPERATOR",
        "required_command": (
            "wp plugin verify-checksums wordpress-seo --version=28.3 --strict"
        ),
        "status": "NOT_EXECUTED",
    }
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
        "str_starts_with($slug, 'raos-review-')",
        "kurashinoshirube_public_article_identity($post_id)",
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

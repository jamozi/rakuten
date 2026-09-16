"""Batch F theme behaviour (plan 3.1 / ruling 4 and 17) through the real theme PHP.

Fail-before-fix tests are marked in their docstrings; the rest are regression guards
that already held before batch F.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import shutil

import pytest

from scripts import build_st1704_theme_assets as theme_assets
from tests.st1704.theme_php_harness import ORIGIN, THEME, run_theme_php


ROOT = Path(__file__).resolve().parents[2]
FUNCTIONS = (THEME / "functions.php").read_text(encoding="utf-8")
NAVIGATION = json.loads(
    (THEME / "assets/editorial-navigation.v3.json").read_text(encoding="utf-8")
)
HUBS = NAVIGATION["reader_navigation"]["hubs"]
HUB_LABELS = {hub["slug"]: hub["label"] for hub in HUBS}
LEDGER = {
    row["slug"]: row
    for row in json.loads(
        (ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json").read_text(
            encoding="utf-8"
        )
    )["articles"]
}
METADATA = json.loads(
    (THEME / "assets/site-editorial-metadata.v1.json").read_text(encoding="utf-8")
)
DISHWASHER_PATH = "assets/images/article-countertop-dishwasher-guide.webp"
TRAVEL_SMALL_PATH = "assets/images/travel-small-20260913.webp"
HOME_HERO_PATH = "assets/images/home-hero.webp"
OWNER_DIRECT = {
    549: ("compact-dishwasher-comparison", "kitchen"),
    550: ("standard-dishwasher-comparison", "kitchen"),
    551: ("large-dishwasher-comparison", "kitchen"),
    552: ("dishwasher-branch-faucet-guide", "kitchen"),
    553: ("small-carry-on-suitcase-comparison", "travel"),
}
MISMATCH_ID = 560
UPDATED_ID = 570

PROGRAM = r"""
$GLOBALS['theme'] = $argv[2];
$posts = json_decode($argv[3], true, 16, JSON_THROW_ON_ERROR);
$hubs = json_decode($argv[4], true, 16, JSON_THROW_ON_ERROR);
class RAOS_Codex_MCP_Owner_Direct {
    public static function public_article_snapshot($post_id) { return $GLOBALS['raos_direct'][$post_id] ?? null; }
}
$GLOBALS['raos_direct'] = array();
foreach ($posts as $fields) {
    $GLOBALS['raos_direct'][$fields['ID']] = array('id' => $fields['ID'], 'post_type' => 'post',
        'slug' => $fields['post_name'], 'title' => $fields['post_title'], 'excerpt' => $fields['post_excerpt'],
        'block_markup' => $fields['post_content']);
}
$GLOBALS['pages'] = array();
foreach ($hubs as $index => $hub) {
    $page = new WP_Post();
    foreach (array('ID' => 600 + $index, 'post_type' => 'page', 'post_status' => 'publish', 'post_password' => '',
        'post_name' => $hub['slug'], 'post_title' => $hub['label'], 'post_excerpt' => '', 'post_content' => '') as $key => $value) {
        $page->$key = $value;
    }
    $GLOBALS['pages'][$hub['slug']] = $page;
}
$GLOBALS['raos_state']['singular'] = 'post';
$out = array();
foreach ($posts as $fields) {
    kurashinoshirube_flush_reader_hub_page_cache();
    $GLOBALS['page'] = new WP_Post();
    foreach ($fields as $key => $value) { $GLOBALS['page']->$key = $value; }
    $id = $fields['ID'];
    ob_start(); kurashinoshirube_emit_json_ld(); $graph = ob_get_clean();
    $dates = array();
    foreach (array('published' => array(), 'modified' => array('displayType' => 'modified'),
        'listing' => array('displayType' => 'modified', 'className' => 'raos-listing-date')) as $name => $attrs) {
        $block = array('attrs' => $attrs + array('postId' => $id));
        $html = '<div class="wp-block-post-date"><time datetime="2026-09-15T16:56:21+09:00">2026年9月15日</time></div>';
        $html = kurashinoshirube_label_post_date_block($html, $block);
        $dates[$name] = kurashinoshirube_site_editorial_date_block($html, $block);
    }
    $out[(string) $id] = array(
        'identity' => kurashinoshirube_public_article_identity($id),
        'category' => kurashinoshirube_reader_article_category($id),
        'breadcrumb' => kurashinoshirube_render_breadcrumb(array(), '', 'kurashinoshirube_breadcrumb'),
        'graph' => $graph,
        'social' => kurashinoshirube_current_social_visual_asset(),
        'dates' => $dates,
    );
}
echo json_encode($out, JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
"""


def _post(post_id: int, slug: str, title: str, excerpt: str) -> dict[str, object]:
    return {
        "ID": post_id,
        "post_type": "post",
        "post_status": "publish",
        "post_password": "",
        "post_name": slug,
        "post_title": title,
        "post_excerpt": excerpt,
        "post_content": "<p>本文</p>",
    }


def _record(
    slug: str, post_id: int, category: str, updated_on: str | None
) -> dict[str, object]:
    template = copy.deepcopy(next(iter(METADATA["articles"].values())))
    template.update(
        category=category,
        post_id=post_id,
        slug=slug,
        published_on="2026-09-13",
        updated_on=updated_on,
    )
    return template


@pytest.fixture(scope="module")
def theme_php(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, object]]:
    theme_copy = tmp_path_factory.mktemp("batch-f-theme") / "kurashinoshirube-child"
    shutil.copytree(THEME, theme_copy)
    metadata = copy.deepcopy(METADATA)
    posts = []
    for post_id, (slug, category) in OWNER_DIRECT.items():
        row = LEDGER[slug]
        posts.append(_post(post_id, slug, row["title"], row["excerpt"]))
        metadata["articles"][slug] = _record(slug, post_id, category, None)
    excerpt = "テスト用の記事の抜粋です。公開日と内容更新日の表示だけを確かめるための固定文です。"
    posts.append(
        _post(
            MISMATCH_ID,
            "fixture-record-id-mismatch",
            "テスト用の記事（ID不一致）",
            excerpt,
        )
    )
    metadata["articles"]["fixture-record-id-mismatch"] = _record(
        "fixture-record-id-mismatch", MISMATCH_ID + 1, "kitchen", None
    )
    posts.append(
        _post(
            UPDATED_ID,
            "fixture-updated-article",
            "テスト用の記事（内容更新あり）",
            excerpt,
        )
    )
    metadata["articles"]["fixture-updated-article"] = _record(
        "fixture-updated-article", UPDATED_ID, "kitchen", "2026-09-15"
    )
    hub_member = LEDGER["countertop-dishwasher-for-small-households"]
    posts.append(
        _post(41, hub_member["slug"], hub_member["title"], hub_member["excerpt"])
    )
    (theme_copy / "assets/site-editorial-metadata.v1.json").write_text(
        json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
    )
    return run_theme_php(
        PROGRAM,
        str(theme_copy),
        json.dumps(posts, ensure_ascii=False),
        json.dumps(
            [{"slug": hub["slug"], "label": hub["label"]} for hub in HUBS],
            ensure_ascii=False,
        ),
        # The program points get_stylesheet_directory() at this copy, so the sandboxed PHP
        # has to be able to read it (theme_php_harness.run_theme_php).
        mounts=(theme_copy,),
    )


def _graph(case: dict[str, object]) -> dict[str, dict[str, object]]:
    match = re.fullmatch(
        r'<script id="raos-structured-data" type="application/ld\+json">(.*)</script>\n',
        str(case["graph"]),
        re.S,
    )
    assert match is not None, case["graph"]
    return {node["@type"]: node for node in json.loads(match[1])["@graph"]}


def _crumbs(case: dict[str, object]) -> list[tuple[int, str, str]]:
    return [
        (item["position"], item["item"], item["name"])
        for item in _graph(case)["BreadcrumbList"]["itemListElement"]
    ]


def _visible_crumbs(case: dict[str, object]) -> list[str]:
    return re.findall(
        r"<li(?: aria-current=\"page\")?>(.*?)</li>", str(case["breadcrumb"])
    )


@pytest.mark.parametrize("post_id", sorted(OWNER_DIRECT))
def test_articles_without_hub_membership_take_the_parent_from_the_editorial_record(
    theme_php, post_id: int
) -> None:
    """Fail before fix: 549-553 rendered a 2-level breadcrumb (plan 3.1 theme :3842)."""
    slug, category = OWNER_DIRECT[post_id]
    case = theme_php[str(post_id)]
    assert case["identity"]["article_id"] == f"owner-direct-{post_id}"
    assert case["category"] == {
        "label": HUB_LABELS[category],
        "slug": category,
        "url": f"{ORIGIN}/{category}/",
    }
    title = LEDGER[slug]["title"]
    assert _visible_crumbs(case) == [
        f'<a href="{ORIGIN}/">ホーム</a>',
        f'<a href="{ORIGIN}/{category}/">{HUB_LABELS[category]}</a>',
        title,
    ]
    assert _crumbs(case) == [
        (1, f"{ORIGIN}/", "ホーム"),
        (2, f"{ORIGIN}/{category}/", HUB_LABELS[category]),
        (3, f"{ORIGIN}/{slug}/", title),
    ]


def test_record_fallback_requires_the_record_post_id_to_match(theme_php) -> None:
    """Regression guard: a slug-only match never supplies a parent category."""
    case = theme_php[str(MISMATCH_ID)]
    assert case["category"] is None
    assert len(_visible_crumbs(case)) == 2
    assert [position for position, _, _ in _crumbs(case)] == [1, 2]


def test_hub_membership_still_decides_the_parent_of_bound_articles(theme_php) -> None:
    """Regression: hub-bound article 41 keeps its /kitchen/ parent."""
    case = theme_php["41"]
    assert case["category"]["slug"] == "kitchen"
    assert _crumbs(case)[1] == (2, f"{ORIGIN}/kitchen/", HUB_LABELS["kitchen"])


@pytest.mark.parametrize("post_id", sorted(OWNER_DIRECT))
def test_header_shows_only_the_publication_date_without_a_content_update(
    theme_php, post_id: int
) -> None:
    """Fail before fix: the modified block printed 「内容更新日 未確認」 (plan 3.1 theme :6524)."""
    dates = theme_php[str(post_id)]["dates"]
    assert dates["modified"] == ""
    assert dates["published"] == (
        '<div class="wp-block-post-date"><span class="raos-date-label">公開日</span> '
        '<time datetime="2026-09-13">2026-09-13</time></div>'
    )


def test_header_keeps_the_content_update_date_when_recorded(theme_php) -> None:
    """Regression: a recorded updated_on still renders 「内容更新日」."""
    dates = theme_php[str(UPDATED_ID)]["dates"]
    assert dates["modified"] == (
        '<div class="wp-block-post-date"><span class="raos-date-label">内容更新日</span> '
        '<time datetime="2026-09-15">2026-09-15</time></div>'
    )
    assert "未確認" not in dates["published"]


@pytest.mark.parametrize("post_id", sorted(OWNER_DIRECT))
def test_listing_card_shows_the_publication_date_without_a_content_update(
    theme_php, post_id: int
) -> None:
    """Fail before fix: archive/search/home list cards only carry the modified date block
    (className raos-listing-date), and it rendered nothing when updated_on is null."""
    dates = theme_php[str(post_id)]["dates"]
    assert dates["listing"] == dates["published"]
    assert dates["listing"] == (
        '<div class="wp-block-post-date"><span class="raos-date-label">公開日</span> '
        '<time datetime="2026-09-13">2026-09-13</time></div>'
    )


def test_listing_card_keeps_the_content_update_date_when_recorded(theme_php) -> None:
    """Regression: a list card of an updated record still shows 「内容更新日」."""
    dates = theme_php[str(UPDATED_ID)]["dates"]
    assert dates["listing"] == dates["modified"]
    assert "内容更新日" in dates["listing"]


@pytest.mark.parametrize("post_id", sorted(OWNER_DIRECT))
def test_date_modified_falls_back_to_date_published(theme_php, post_id: int) -> None:
    """Fail before fix: dateModified was unset when updated_on is null (ruling 17)."""
    article = _graph(theme_php[str(post_id)])["Article"]
    assert article["datePublished"] == "2026-09-13"
    assert article["dateModified"] == "2026-09-13"


def test_date_modified_uses_the_recorded_content_update(theme_php) -> None:
    """Regression: a recorded updated_on is still dateModified, never WP modified."""
    article = _graph(theme_php[str(UPDATED_ID)])["Article"]
    assert (article["datePublished"], article["dateModified"]) == (
        "2026-09-13",
        "2026-09-15",
    )


@pytest.mark.parametrize("post_id", (549, 550, 551, 552))
def test_dishwasher_owner_direct_articles_reuse_the_dishwasher_social_binding(
    theme_php, post_id: int
) -> None:
    """Fail before fix: 549-552 fell back to home-hero (ruling 4)."""
    social = theme_php[str(post_id)]["social"]
    assert social["path"] == DISHWASHER_PATH
    assert (social["width"], social["height"]) == (1536, 1024)
    assert (
        social["alt"]
        == "卓上食洗機の設置条件を整理した編集部のイメージ（商品写真ではありません）"
    )
    assert (
        social["uri"]
        == f"{ORIGIN}/wp-content/themes/kurashinoshirube-child/{DISHWASHER_PATH}"
    )
    assert _graph(theme_php[str(post_id)])["Article"]["image"] == [social["uri"]]


def test_small_suitcase_comparison_uses_the_recorded_travel_small_image(
    theme_php,
) -> None:
    """Fail before fix: 553 fell back to home-hero (ruling 4)."""
    social = theme_php["553"]["social"]
    assert social["path"] == TRAVEL_SMALL_PATH
    assert (social["width"], social["height"]) == (900, 675)
    # The alt repeats the recorded depiction of the image (build_st1704_self_hosted_theme.CATEGORY_IMAGE_ALTS).
    assert (
        social["alt"]
        == "小さなスーツケースと少量の着替えを揃えた旅支度のイメージ（商品写真ではありません）"
    )
    assert (
        social["uri"]
        == f"{ORIGIN}/wp-content/themes/kurashinoshirube-child/{TRAVEL_SMALL_PATH}"
    )
    assert HOME_HERO_PATH not in json.dumps(_graph(theme_php["553"])["Article"])


def _asset(name: str) -> theme_assets.AssetSpec:
    return next(asset for asset in theme_assets.ASSETS if asset.output.name == name)


def test_reassigned_images_record_their_new_uses() -> None:
    """Fail before fix: og and home new-arrival uses were not in allowed_uses (ruling 4)."""
    travel_small = _asset("travel-small-20260913.webp")
    assert travel_small.allowed_uses == (
        "CATEGORY_EDITORIAL_ILLUSTRATION",
        "HOMEPAGE_RECENT_ARTICLE_THUMBNAIL",
        "SOCIAL_PREVIEW",
    )
    for size in ("compact", "standard", "large"):
        assert _asset(f"kitchen-capacity-{size}-20260913.webp").allowed_uses == (
            "CATEGORY_CAPACITY_EDITORIAL_ILLUSTRATION",
            "ARTICLE_EDITORIAL_ILLUSTRATION",
            "HOMEPAGE_RECENT_ARTICLE_THUMBNAIL",
        )
    # Regression: the reused dishwasher binding keeps its own record untouched.
    assert _asset("article-countertop-dishwasher-guide.webp").allowed_uses == (
        "DISHWASHER_ARTICLE_ILLUSTRATION",
    )


def test_travel_small_social_constants_match_the_generated_webp() -> None:
    """Fail before fix: the theme had no constant for the travel-small social image."""
    asset = _asset("travel-small-20260913.webp")
    assert (
        f"const KURASHINOSHIRUBE_TRAVEL_SMALL_IMAGE_PATH = '{TRAVEL_SMALL_PATH}';"
        in FUNCTIONS
    )
    assert (
        f"const KURASHINOSHIRUBE_TRAVEL_SMALL_IMAGE_SHA256 = '{asset.output_sha256}';"
        in FUNCTIONS
    )
    bindings = FUNCTIONS.split("function kurashinoshirube_social_image_bindings", 1)[
        1
    ].split("function kurashinoshirube_social_image_asset", 1)[0]
    for post_id in (549, 550, 551, 552):
        assert f"'owner-direct-{post_id}' => $dishwasher," in bindings
    assert "'owner-direct-553' => array(" in bindings

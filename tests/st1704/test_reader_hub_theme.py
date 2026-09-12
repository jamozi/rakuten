"""Run the real theme's fail-open hub head, breadcrumb and body-class behavior without WordPress."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from tests.st1704.theme_php_harness import ORIGIN, run_theme_php


ROOT = Path(__file__).resolve().parents[2]
THEME = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
)
HUBS = json.loads((THEME / "assets/editorial-navigation.v3.json").read_text())[
    "reader_navigation"
]["hubs"]
HUB_BY_SLUG = {hub["slug"]: hub for hub in HUBS}
LOCAL_GUIDES = json.loads(
    (
        ROOT / "changes/wordpress-local-preview-v1/fixtures/reader-guides.v1.json"
    ).read_text()
)["articles"]
LEDGER_TITLES = {
    row["slug"]: row["title"]
    for row in json.loads(
        (ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json").read_text()
    )["articles"]
    if row.get("post_type") == "page"
}
LONG_EXCERPT = "食洗機を選ぶ前に、置き場所、扉の開閉、給排水、電源、普段の食器量を順に確認する案内です。"


def _page(hub: dict[str, object], post_id: int = 501) -> dict[str, object]:
    slug = hub["slug"]
    return {
        "ID": post_id,
        "post_type": "page",
        "post_status": "publish",
        "post_password": "",
        "post_name": slug,
        "post_title": hub["label"],
        "post_excerpt": hub["description"],
        "post_content": '<!-- wp:shortcode -->[kurashinoshirube_reader_hub slug="'
        + str(slug)
        + '"]<!-- /wp:shortcode -->',
    }


PROGRAM = r"""
$cases = json_decode($argv[2], true, 32, JSON_THROW_ON_ERROR);
$others = json_decode($argv[3], true, 32, JSON_THROW_ON_ERROR);
$policies = kurashinoshirube_policy_page_head_map();
foreach ($policies as $slug => $head) {
    $cases['policy-' . $slug] = array(
        'ID' => 501, 'post_type' => 'page', 'post_status' => 'publish',
        'post_password' => '', 'post_name' => $slug, 'post_title' => $head['title'],
        'post_excerpt' => $head['description'], 'post_content' => '<p>Policy fixture</p>',
    );
}
$results = array();
foreach ($cases as $name => $fields) {
    kurashinoshirube_flush_reader_hub_page_cache();
    $GLOBALS['raos_state']['singular'] = 'page';
    $GLOBALS['pages'] = array();
    foreach ($others as $slug => $other) {
        if ($slug === $fields['post_name']) { continue; }
        $page = new WP_Post();
        foreach ($other as $key => $value) { $page->$key = $value; }
        $GLOBALS['pages'][$slug] = $page;
    }
    $GLOBALS['page'] = new WP_Post();
    foreach ($fields as $key => $value) { $GLOBALS['page']->$key = $value; }
    ob_start(); kurashinoshirube_emit_json_ld(); $graph = ob_get_clean();
    ob_start(); kurashinoshirube_emit_fallback_icon(); $icons = ob_get_clean();
    $results[$name] = array(
        'head' => kurashinoshirube_public_head_context(),
        'title' => kurashinoshirube_filter_title('upstream-title'),
        'canonical' => kurashinoshirube_filter_canonical('upstream-canonical'),
        'description' => kurashinoshirube_filter_description('upstream-description'),
        'og_type' => kurashinoshirube_filter_og_type('upstream-type'),
        'social_image' => kurashinoshirube_filter_social_image('upstream-image'),
        'social_width' => kurashinoshirube_filter_social_image_width(''),
        'social_height' => kurashinoshirube_filter_social_image_height(''),
        'twitter_card' => kurashinoshirube_filter_twitter_card('upstream-card'),
        'classes' => kurashinoshirube_editorial_v2_body_class(array('existing-class')),
        'hub_url' => kurashinoshirube_reader_hub_url($fields['post_name']),
        'hub_title' => kurashinoshirube_reader_hub_title($fields['post_name']),
        'graph' => $graph,
        'icons' => $icons,
    );
}
echo json_encode(array('cases' => $results, 'policies' => $policies,
    'hub_count' => count(kurashinoshirube_editorial_navigation()['reader_navigation']['hubs'])),
    JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE);
"""


@pytest.fixture(scope="module")
def hub_php() -> dict[str, object]:
    cases = {"valid-" + hub["slug"]: _page(hub) for hub in HUBS}
    for name, patch in {
        "draft": {"post_status": "draft"},
        "password": {"post_password": "test-only-password"},
        "unknown": {"post_name": "unregistered-hub"},
        "wrong-type": {"post_type": "attachment"},
        "missing": {"ID": 0},
    }.items():
        cases["invalid-" + name] = {**_page(HUBS[0]), **patch}
    for name, patch in {
        "body": {"post_content": _page(HUBS[1])["post_content"]},
        "extra-body": {"post_content": str(_page(HUBS[0])["post_content"]) + "\n"},
        "title": {"post_title": "Unreviewed title"},
        "short-excerpt": {"post_excerpt": "Unreviewed description"},
        "long-excerpt": {"post_excerpt": LONG_EXCERPT},
    }.items():
        cases["tolerated-" + name] = {**_page(HUBS[0]), **patch}
    cases["ledger-kitchen"] = {
        **_page(HUB_BY_SLUG["kitchen"]),
        "post_title": LEDGER_TITLES["kitchen"],
        "post_excerpt": "",
    }
    for guide in LOCAL_GUIDES:
        cases["local-" + guide["article_id"]] = {
            **_page(HUBS[0]),
            "post_name": guide["local_slug"],
        }
    others = {
        hub["slug"]: {
            **_page(hub, post_id=600 + index),
            "post_title": LEDGER_TITLES.get(hub["slug"], hub["label"]),
        }
        for index, hub in enumerate(HUBS)
    }
    return run_theme_php(
        PROGRAM,
        json.dumps(cases, ensure_ascii=False),
        json.dumps(others, ensure_ascii=False),
    )


def _graph(actual: dict[str, object]) -> list[dict[str, object]]:
    match = re.fullmatch(
        r'<script id="raos-structured-data" type="application/ld\+json">(.*)</script>\n',
        str(actual["graph"]),
        re.S,
    )
    assert match is not None
    return json.loads(match[1])["@graph"]


@pytest.mark.parametrize("hub", HUBS, ids=lambda hub: hub["slug"])
def test_registered_hub_has_exact_head_graph_and_distinct_shell(hub_php, hub) -> None:
    actual = hub_php["cases"]["valid-" + hub["slug"]]
    url = f"{ORIGIN}/{hub['slug']}/"
    assert actual["head"] == {
        "canonical_url": url,
        "description": hub["description"],
        "kind": "fixed_page",
        "title": hub["label"],
    }
    assert actual["title"] == hub["label"] + "｜暮らしのしるべ"
    assert actual["canonical"] == actual["hub_url"] == url
    assert actual["description"] == hub["description"]
    assert actual["og_type"] == "website"
    assert actual["social_image"] == (
        f"{ORIGIN}/wp-content/themes/kurashinoshirube-child/assets/images/home-hero.webp"
    )
    assert (actual["social_width"], actual["social_height"]) == (1600, 900)
    assert actual["twitter_card"] == "summary_large_image"
    assert actual["classes"] == ["existing-class", "raos-reader-hub-page"]
    graph = _graph(actual)
    assert {node["@type"] for node in graph} == {
        "CollectionPage",
        "BreadcrumbList",
        "Organization",
        "WebSite",
    }
    page = next(node for node in graph if node["@type"] == "CollectionPage")
    assert (page["name"], page["description"], page["url"]) == (
        hub["label"],
        hub["description"],
        url,
    )
    crumbs = next(node for node in graph if node["@type"] == "BreadcrumbList")[
        "itemListElement"
    ]
    parent = {"category": "categories", "purpose": "purposes"}.get(hub["kind"])
    expected = [("ホーム", ORIGIN + "/")]
    if parent is not None:
        expected.append((LEDGER_TITLES[parent], f"{ORIGIN}/{parent}/"))
    expected.append((hub["label"], url))
    assert [(item["name"], item["item"]) for item in crumbs] == expected
    assert [item["position"] for item in crumbs] == list(range(1, len(expected) + 1))


def test_hub_page_keeps_its_own_ledger_title_in_head_and_breadcrumb(hub_php) -> None:
    actual = hub_php["cases"]["ledger-kitchen"]
    ledger_title = LEDGER_TITLES["kitchen"]
    assert actual["head"]["title"] == ledger_title
    assert actual["hub_title"] == ledger_title
    assert actual["title"] == ledger_title + "｜暮らしのしるべ"
    # An empty stored excerpt falls back to the registered description.
    assert actual["head"]["description"] == HUB_BY_SLUG["kitchen"]["description"]
    crumbs = next(node for node in _graph(actual) if node["@type"] == "BreadcrumbList")
    assert [item["name"] for item in crumbs["itemListElement"]] == [
        "ホーム",
        LEDGER_TITLES["categories"],
        ledger_title,
    ]


def test_hub_gate_tolerates_body_title_and_excerpt_drift(hub_php) -> None:
    baseline = hub_php["cases"]["valid-" + HUBS[0]["slug"]]
    for name in ("tolerated-body", "tolerated-extra-body"):
        actual = hub_php["cases"][name]
        assert actual["head"] == baseline["head"], name
        assert actual["hub_url"] == baseline["hub_url"], name
        assert actual["classes"] == ["existing-class", "raos-reader-hub-page"], name
    titled = hub_php["cases"]["tolerated-title"]
    assert titled["head"]["title"] == "Unreviewed title"
    assert titled["title"] == "Unreviewed title｜暮らしのしるべ"
    assert titled["hub_url"] == baseline["hub_url"]
    short = hub_php["cases"]["tolerated-short-excerpt"]
    assert short["head"]["description"] == HUBS[0]["description"]
    long = hub_php["cases"]["tolerated-long-excerpt"]
    assert long["head"]["description"] == LONG_EXCERPT
    assert long["description"] == LONG_EXCERPT


def test_unpublished_unknown_and_local_guide_pages_keep_upstream_head(hub_php) -> None:
    for name, actual in hub_php["cases"].items():
        if not name.startswith(("invalid-", "local-")):
            continue
        assert actual["head"] is None, name
        assert actual["title"] == "upstream-title", name
        assert actual["canonical"] == "upstream-canonical", name
        assert actual["description"] == "upstream-description", name
        assert actual["og_type"] == "upstream-type", name
        assert actual["classes"] == ["existing-class"], name
        assert actual["hub_url"] is None, name
        assert actual["graph"] == "", name


def test_three_policy_pages_remain_separate_from_registered_hubs(hub_php) -> None:
    assert set(hub_php["policies"]) == {
        "about-ad-policy",
        "comparison-policy",
        "privacy-policy",
    }
    assert hub_php["hub_count"] == 15
    for slug, head in hub_php["policies"].items():
        actual = hub_php["cases"]["policy-" + slug]
        assert actual["head"]["title"] == head["title"]
        assert actual["head"]["description"] == head["description"]
        assert actual["title"] == head["title"] + "｜暮らしのしるべ"
        assert actual["og_type"] == "website"
        assert actual["classes"] == ["existing-class", "raos-policy-v3-page"]
        assert actual["hub_url"] is None
        graph = _graph(actual)
        page = next(node for node in graph if node["@type"] in ("AboutPage", "WebPage"))
        assert page["@type"] == ("AboutPage" if slug == "about-ad-policy" else "WebPage")
    privacy = hub_php["policies"]["privacy-policy"]["description"]
    assert "GA4" in privacy and "CookieYes" in privacy
    assert "行わない" not in privacy


def test_organization_website_and_icons_are_emitted_for_every_public_page(hub_php) -> None:
    actual = hub_php["cases"]["valid-categories"]
    graph = _graph(actual)
    organization = next(node for node in graph if node["@type"] == "Organization")
    assert organization["name"] == "暮らしのしるべ"
    assert organization["url"] == ORIGIN + "/"
    assert organization["contactPoint"] == {
        "@type": "ContactPoint",
        "contactType": "customer support",
        "email": "contact@kurashinoshirube.com",
    }
    assert organization["logo"]["@type"] == "ImageObject"
    assert organization["logo"]["url"].endswith("/assets/images/brand-mark-512.png")
    assert (organization["logo"]["width"], organization["logo"]["height"]) == (512, 512)
    assert "sameAs" not in organization
    website = next(node for node in graph if node["@type"] == "WebSite")
    assert website["potentialAction"] == {
        "@type": "SearchAction",
        "query-input": "required name=search_term_string",
        "target": {
            "@type": "EntryPoint",
            "urlTemplate": ORIGIN + "/?s={search_term_string}",
        },
    }
    icons = str(actual["icons"])
    assert '<meta name="theme-color" content="#17243f">' in icons
    assert 'rel="icon" href="' + ORIGIN + "/wp-content/themes/kurashinoshirube-child/assets/images/favicon.ico" in icons
    assert 'type="image/svg+xml"' in icons
    assert 'type="image/png" sizes="32x32"' in icons
    assert '<link rel="apple-touch-icon" sizes="180x180" href="' + ORIGIN + "/wp-content/themes/kurashinoshirube-child/assets/images/apple-touch-icon.png" in icons


def test_related_target_uses_clean_stored_title_after_identity_validation() -> None:
    php = shutil.which("php")
    if php is None:
        pytest.skip("PHP is required for the theme behavior harness")
    source = (THEME / "functions.php").read_text()
    functions = "\n".join(
        re.search(r"function " + name + r"\(.*?\n}\n", source, re.S)[0]
        for name in (
            "kurashinoshirube_is_clean_text",
            "kurashinoshirube_resolve_related_target",
        )
    )
    program = (
        r"""
define('OBJECT', 'OBJECT');
define('KURASHINOSHIRUBE_SITE_ORIGIN', 'https://kurashinoshirube.com');
class WP_Post extends stdClass {}
function kurashinoshirube_article_bindings() {
    return array('fixture-article' => array('slug' => 'fixture-guide',
        'local_slug' => 'local-preview-fixture-guide', 'title' => 'スーツケース5モデルを比較'));
}
function kurashinoshirube_local_preview_origin() { return null; }
function get_page_by_path($slug, $output, $type) { return $GLOBALS['post']; }
function get_post_status($post) { return $post->post_status; }
function get_post_field($field, $id, $context) { return $GLOBALS['post']->$field; }
function get_permalink($post) { return 'https://kurashinoshirube.com/fixture-guide/'; }
function kurashinoshirube_public_article_identity($id) {
    return array('article_id' => $GLOBALS['identity']);
}
function wp_strip_all_tags($text) { return strip_tags($text); }
"""
        + functions
        + r"""
$cases = array(
    'stored' => array('スーツケース4モデルを比較', 'fixture-article', 'publish'),
    'empty' => array('', 'fixture-article', 'publish'),
    'markup' => array('<b>スーツケース4モデルを比較</b>', 'fixture-article', 'publish'),
    'identity' => array('スーツケース4モデルを比較', 'other-article', 'publish'),
    'draft' => array('スーツケース4モデルを比較', 'fixture-article', 'draft'),
);
$results = array();
foreach ($cases as $name => [$title, $identity, $status]) {
    $GLOBALS['post'] = new WP_Post();
    $GLOBALS['post']->ID = 83;
    $GLOBALS['post']->post_name = 'fixture-guide';
    $GLOBALS['post']->post_title = $title;
    $GLOBALS['post']->post_status = $status;
    $GLOBALS['identity'] = $identity;
    $results[$name] = kurashinoshirube_resolve_related_target('fixture-article');
}
echo json_encode($results, JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE);
"""
    )
    result = subprocess.run(
        [php, "-r", program],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stderr == ""
    actual = json.loads(result.stdout)
    assert actual["stored"] == {
        "title": "スーツケース4モデルを比較",
        "url": "https://kurashinoshirube.com/fixture-guide/",
    }
    assert all(
        actual[name] is None for name in ("empty", "markup", "identity", "draft")
    )

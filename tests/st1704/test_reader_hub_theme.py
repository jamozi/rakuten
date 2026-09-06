"""Run the real theme's closed hub head and body-class behavior without WordPress."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
THEME = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
)
HUBS = json.loads((THEME / "assets/editorial-navigation.v3.json").read_text())[
    "reader_navigation"
]["hubs"]
LOCAL_GUIDES = json.loads(
    (
        ROOT / "changes/wordpress-local-preview-v1/fixtures/reader-guides.v1.json"
    ).read_text()
)["articles"]


def _page(hub: dict[str, object]) -> dict[str, object]:
    slug = hub["slug"]
    return {
        "ID": 501,
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


@pytest.fixture(scope="module")
def hub_php() -> dict[str, object]:
    php = shutil.which("php")
    if php is None:
        pytest.skip("PHP is required for the theme behavior harness")
    cases = {"valid-" + hub["slug"]: _page(hub) for hub in HUBS}
    for name, patch in {
        "draft": {"post_status": "draft"},
        "password": {"post_password": "test-only-password"},
        "body": {"post_content": _page(HUBS[1])["post_content"]},
        "extra-body": {"post_content": str(_page(HUBS[0])["post_content"]) + "\n"},
        "title": {"post_title": "Unreviewed title"},
        "excerpt": {"post_excerpt": "Unreviewed description"},
        "unknown": {"post_name": "unregistered-hub"},
        "wrong-type": {"post_type": "attachment"},
        "missing": {"ID": 0},
    }.items():
        cases["invalid-" + name] = {**_page(HUBS[0]), **patch}
    for guide in LOCAL_GUIDES:
        cases["local-" + guide["article_id"]] = {
            **_page(HUBS[0]),
            "post_name": guide["local_slug"],
        }
    program = r"""
define('OBJECT', 'OBJECT');
class WP_Post extends stdClass {}
function add_action(...$args) {}
function add_filter(...$args) {}
function add_shortcode(...$args) {}
function is_front_page() { return false; }
function is_singular($type) { return $type === 'page'; }
function is_search() { return false; }
function is_archive() { return false; }
function is_404() { return false; }
function get_stylesheet_directory() { return $GLOBALS['theme']; }
function get_option($name, $default = false) { return $default; }
function get_queried_object_id() { return $GLOBALS['page']->ID; }
function get_post($id) {
    return $id instanceof WP_Post ? $id : ($id === $GLOBALS['page']->ID ? $GLOBALS['page'] : null);
}
function get_post_field($field, $id, $context = 'raw') {
    $post = get_post($id); return $post === null ? null : ($post->$field ?? null);
}
function get_post_type($id) { return get_post_field('post_type', $id); }
function get_post_status($id) { return get_post_field('post_status', $id); }
function get_page_by_path($slug, $output, $type) {
    $post = $GLOBALS['page'];
    return $post->post_name === $slug && $post->post_type === $type ? $post : null;
}
function get_permalink($post) {
    return 'https://kurashinoshirube.com/' . get_post($post)->post_name . '/';
}
function wp_strip_all_tags($text) { return strip_tags($text); }
function wp_json_encode($value, $flags = 0) { return json_encode($value, $flags); }
$GLOBALS['theme'] = $argv[1];
require $argv[1] . '/functions.php';
$cases = json_decode($argv[2], true, 32, JSON_THROW_ON_ERROR);
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
    $GLOBALS['page'] = new WP_Post();
    foreach ($fields as $key => $value) { $GLOBALS['page']->$key = $value; }
    ob_start(); kurashinoshirube_emit_json_ld(); $graph = ob_get_clean();
    $results[$name] = array(
        'head' => kurashinoshirube_public_head_context(),
        'canonical' => kurashinoshirube_filter_canonical('upstream-canonical'),
        'description' => kurashinoshirube_filter_description('upstream-description'),
        'classes' => kurashinoshirube_editorial_v2_body_class(array('existing-class')),
        'hub_url' => kurashinoshirube_reader_hub_url($fields['post_name']),
        'graph' => $graph,
    );
}
echo json_encode(array('cases' => $results, 'policies' => $policies,
    'hub_count' => count(kurashinoshirube_editorial_navigation()['reader_navigation']['hubs'])),
    JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE);
"""
    result = subprocess.run(
        [php, "-r", program, str(THEME), json.dumps(cases, ensure_ascii=False)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stderr == ""
    return json.loads(result.stdout)


@pytest.mark.parametrize("hub", HUBS, ids=lambda hub: hub["slug"])
def test_registered_hub_has_exact_head_graph_and_distinct_shell(hub_php, hub) -> None:
    actual = hub_php["cases"]["valid-" + hub["slug"]]
    url = "https://kurashinoshirube.com/" + hub["slug"] + "/"
    assert actual["head"] == {
        "canonical_url": url,
        "description": hub["description"],
        "kind": "fixed_page",
        "title": hub["label"],
    }
    assert actual["canonical"] == actual["hub_url"] == url
    assert actual["description"] == hub["description"]
    assert actual["classes"] == ["existing-class", "raos-reader-hub-page"]
    graph = json.loads(
        re.fullmatch(
            r'<script id="raos-structured-data" type="application/ld\+json">(.*)</script>\n',
            actual["graph"],
        )[1]
    )["@graph"]
    assert {node["@type"] for node in graph} == {
        "WebPage",
        "BreadcrumbList",
        "Organization",
        "WebSite",
    }
    page = next(node for node in graph if node["@type"] == "WebPage")
    assert (page["name"], page["description"], page["url"]) == (
        hub["label"],
        hub["description"],
        url,
    )


def test_invalid_hubs_and_five_local_guides_keep_upstream_head(hub_php) -> None:
    for name, actual in hub_php["cases"].items():
        if not name.startswith(("invalid-", "local-")):
            continue
        assert actual["head"] is None, name
        assert actual["canonical"] == "upstream-canonical", name
        assert actual["description"] == "upstream-description", name
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
        assert actual["classes"] == ["existing-class", "raos-policy-v3-page"]
        assert actual["hub_url"] is None


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

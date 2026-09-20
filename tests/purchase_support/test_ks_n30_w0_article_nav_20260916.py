"""next30 Wave 0 (2026-09-16): in-article navigation reads as separate links.

/dishwasher-branch-faucet-guide/ (552) prints three links in one nav with no
separator character, exactly like every other article, and leaves the spacing to
CSS. For the other articles that sheet is ``purchase-support.css``
(``.ps-article .ps-toc{display:flex;gap:.5em 1.2em}``). 552 is not in the
purchase-support runtime, so ``inc/purchase-support.php`` returns before
enqueueing it and the reader gets ``theme.css`` alone -- where the only
``.ps-toc`` rules are scoped to ``.sm-page``. The three links then rendered edge
to edge: 「台所の道具の選び方・比較蛇口を確認費用を確認」, one underlined string in
which 「比較蛇口」 is a word that does not exist.

The wave rewrote the first of those three links, so the check belongs here. It
measures rather than assumes, twice over: the stylesheets are the ones the real
theme PHP enqueues for that exact post, and the geometry is read out of headless
Chromium at 320 / 390 / 1440px. Adjacent links must be told apart -- by a gap, by
a line break, or by visible text printed between them.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from raos.adapters.price_overlay_live_guard import refuse_while_price_overlay_live
from tests.st1704.theme_php_harness import run_theme_php

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json"
HARNESS = ROOT / "tests/purchase_support/article_nav_frames.mjs"

WIDTHS = (320, 390, 1440)
#: The smallest rendered gap that still reads as two links. The healthy
#: navigations measure 14.39px and up on the same widths; 552 measured 0.
MINIMUM_GAP = 4.0
#: The articles whose navigation this wave rewrote (the hub links it renamed).
REWRITTEN_BY_THIS_WAVE = (
    "compact-robot-vacuum-shortlist",
    "countertop-dishwasher-for-small-households",
    "dishwasher-branch-faucet-guide",
    "dishwasher-cleaning-guide",
    "dishwasher-detergent-guide",
    "dishwasher-installation-measurement",
    "dishwasher-running-cost",
    "dishwasher-water-supply-methods",
    "roomba-mini-vs-switchbot-k11-pro",
    "solota-vs-rakua-mini-plus",
)

#: next30 Wave 1: published 2026-09-20 as 750 / 751 / 752, so the theme can be
#: asked which sheets they get. They keep their own measurement because the
#: control below reads the same bodies under theme.css alone.
AWAITING_PUBLICATION = (
    "dish-rack-installation-measurement",
    "slim-dish-rack-under-20cm",
    "dish-rack-no-space",
)
#: A published purchase-support article whose enqueued sheets these will share.
SHEET_REFERENCE = "dishwasher-installation-measurement"
#: Suffix marking the same body measured under theme.css alone (552's condition).
UNSTYLED = "@theme-css-only"

# The theme decides which stylesheets a post gets, so the theme is asked. A post
# whose body is not in the purchase-support runtime verifies no context and gets
# the base sheet alone.
PROGRAM = r"""
class RAOS_Codex_MCP_Owner_Direct {
    public static function public_article_snapshot($post_id) {
        return $GLOBALS['raos_snapshots'][$post_id] ?? null;
    }
}
function wp_enqueue_style($handle, $src = '', $deps = array(), $ver = '', $media = 'all') {
    $GLOBALS['raos_styles'][] = basename((string) $src);
}
function wp_enqueue_script(...$args) {}
$posts = json_decode(file_get_contents($argv[2]), true, 512, JSON_THROW_ON_ERROR);
$out = array();
foreach ($posts as $slug => $article) {
    $GLOBALS['raos_state']['singular'] = 'post';
    $GLOBALS['raos_state']['front'] = false;
    $GLOBALS['page'] = new WP_Post();
    foreach (array('ID' => $article['id'], 'post_type' => 'post', 'post_status' => 'publish',
        'post_password' => '', 'post_name' => $slug, 'post_title' => $article['title'],
        'post_excerpt' => $article['excerpt'], 'post_content' => $article['content']) as $key => $value) {
        $GLOBALS['page']->$key = $value;
    }
    $GLOBALS['raos_snapshots'][$article['id']] = array(
        'id' => $article['id'], 'post_type' => 'post', 'slug' => $slug,
        'title' => $article['title'], 'excerpt' => $article['excerpt'],
        'block_markup' => $article['content'],
    );
    $GLOBALS['raos_styles'] = array();
    foreach ($GLOBALS['raos_hooks'] as $hook) {
        if ($hook[0] === 'action' && $hook[1] === 'wp_enqueue_scripts') {
            ($hook[2])();
        }
    }
    $out[$slug] = array_values(array_unique($GLOBALS['raos_styles']));
}
echo json_encode($out, JSON_UNESCAPED_UNICODE);
"""


def ledger_rows() -> list[dict]:
    return json.loads(LEDGER.read_text(encoding="utf-8"))["articles"]


def published_posts() -> dict[str, dict]:
    """The posts WordPress serves: an existing row whose listing says published.

    The theme resolves purchase-support.css through the applied snapshot, and
    that comparison is `($snapshot['id'] ?? null) !== $post_id`
    (inc/purchase-support.php:22). A row whose post id is not minted yet has no
    id to compare, so measuring it here would only ever report the unstyled
    fallback and call a healthy body broken. Those rows are measured against the
    sheets they will get, in the test below.
    """
    return {
        row["slug"]: row
        for row in ledger_rows()
        if row["post_type"] == "post"
        and row["mode"] == "existing"
        and (row.get("listing") or {}).get("state") == "published"
        and (row.get("body_source") or row.get("patch_source"))
    }


def measure(plan: dict, tmp_path_factory, name: str) -> dict[str, dict]:
    """Drive the browser harness over ``plan`` and return its report."""
    # Contract §8: this starts the browser that article_nav_frames.mjs drives at the
    # site's own origin, so it refuses -- it does not skip -- while a price-overlay run
    # is live. The harness refuses again on its own side.
    refuse_while_price_overlay_live()
    node = shutil.which("node")
    if node is None or not (ROOT / "node_modules/playwright/package.json").is_file():
        pytest.skip("Node and the locked Playwright runtime are required")
    browser = subprocess.run(
        [node, "-e", "process.stdout.write(require('playwright').chromium.executablePath())"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if browser.returncode != 0 or not Path(browser.stdout.strip()).is_file():
        pytest.skip("The locked Chromium build is not installed")
    path = tmp_path_factory.mktemp(name) / "plan.json"
    path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    result = subprocess.run(
        [node, str(HARNESS), str(path), ",".join(str(width) for width in WIDTHS)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def stylesheets(tmp_path_factory) -> dict[str, list[str]]:
    posts = published_posts()
    payload = {
        slug: {
            "id": row["post_id"],
            "title": row["title"],
            "excerpt": row.get("excerpt") or "",
            "content": (
                ROOT / (row.get("body_source") or row.get("patch_source"))
            ).read_text(encoding="utf-8"),
        }
        for slug, row in posts.items()
    }
    path = tmp_path_factory.mktemp("stylesheets") / "posts.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return run_theme_php(PROGRAM, str(path))


@pytest.fixture(scope="module")
def rendered(stylesheets, tmp_path_factory) -> dict[str, dict]:
    posts = published_posts()
    plan = {
        slug: {
            "sheets": sheets,
            "body": posts[slug].get("body_source") or posts[slug].get("patch_source"),
        }
        for slug, sheets in stylesheets.items()
    }
    return measure(plan, tmp_path_factory, "navigation")


@pytest.fixture(scope="module")
def rendered_before_publication(stylesheets, tmp_path_factory) -> dict[str, dict]:
    """The wave-1 bodies under the sheets they get, and under theme.css alone."""
    rows = {row["article_key"]: row for row in ledger_rows()}
    plan = {}
    for key in AWAITING_PUBLICATION:
        body = rows[key]["body_source"]
        plan[key] = {"sheets": stylesheets[key], "body": body}
        plan[key + UNSTYLED] = {"sheets": ["theme.css"], "body": body}
    return measure(plan, tmp_path_factory, "navigation-wave-one")


def navigations(rendered: dict[str, dict]) -> list[tuple[str, int, dict]]:
    return [
        (slug, int(width), nav)
        for slug, report in rendered.items()
        for width, navs in report["widths"].items()
        for nav in navs
    ]


def test_the_measurement_covers_every_navigation_this_wave_rewrote(rendered) -> None:
    """A green run is only worth something if it read the articles in question."""
    measured = {slug for slug, _, nav in navigations(rendered) if nav["pairs"]}
    for slug in REWRITTEN_BY_THIS_WAVE:
        assert slug in measured, (slug, sorted(measured))
    widths = {width for _, width, _ in navigations(rendered)}
    assert widths == set(WIDTHS), widths


def test_adjacent_links_never_render_as_one_run_of_text(rendered) -> None:
    """552's three links ran together into 「台所の道具の選び方・比較蛇口を確認費用を確認」."""
    joined = []
    for slug, width, nav in navigations(rendered):
        for pair in nav["pairs"]:
            separated = (
                bool(pair["printed_between"])
                or not pair["same_line"]
                or pair["gap"] >= MINIMUM_GAP
            )
            if not separated:
                joined.append(
                    f"{slug} @{width}px .{nav['selector']}: "
                    f"{''.join(pair['texts'])} (gap {pair['gap']}px)"
                )
    assert joined == [], joined


def test_the_navigation_of_a_post_outside_the_runtime_is_styled_by_the_theme(
    stylesheets, rendered
) -> None:
    """552 gets theme.css alone, so theme.css has to carry its spacing."""
    assert stylesheets["dishwasher-branch-faucet-guide"] == ["theme.css"], stylesheets
    pairs = [
        pair
        for slug, _, nav in navigations(rendered)
        if slug == "dishwasher-branch-faucet-guide"
        for pair in nav["pairs"]
    ]
    assert pairs, "the guide's navigation was not measured"
    assert all(
        not pair["same_line"] or pair["gap"] >= MINIMUM_GAP for pair in pairs
    ), pairs


def test_the_rows_awaiting_publication_read_as_separate_links(
    stylesheets, rendered_before_publication
) -> None:
    """Wave 1's three bodies, measured under the sheets the theme enqueues for them.

    They are published now (750 / 751 / 752), so the theme is asked for their own
    sheets instead of borrowing the reference article's, and each one is pinned to
    the same three sheets. The second half is the control: the same body under
    theme.css alone -- 552's condition -- has to run together, or a green first
    half would only mean the measurement stopped looking.
    """
    assert stylesheets[SHEET_REFERENCE] == [
        "theme.css",
        "editorial-v2.css",
        "purchase-support.css",
    ], stylesheets[SHEET_REFERENCE]
    for key in AWAITING_PUBLICATION:
        assert stylesheets[key] == [
            "theme.css",
            "editorial-v2.css",
            "purchase-support.css",
        ], (key, stylesheets[key])
    joined, measured, unstyled = [], set(), set()
    for slug, width, nav in navigations(rendered_before_publication):
        for pair in nav["pairs"]:
            separated = (
                bool(pair["printed_between"])
                or not pair["same_line"]
                or pair["gap"] >= MINIMUM_GAP
            )
            if slug.endswith(UNSTYLED):
                if not separated:
                    unstyled.add(slug.removesuffix(UNSTYLED))
                continue
            measured.add(slug)
            if not separated:
                joined.append(
                    f"{slug} @{width}px .{nav['selector']}: "
                    f"{''.join(pair['texts'])} (gap {pair['gap']}px)"
                )
    assert joined == [], joined
    assert measured == set(AWAITING_PUBLICATION), sorted(measured)
    assert unstyled == set(AWAITING_PUBLICATION), sorted(unstyled)

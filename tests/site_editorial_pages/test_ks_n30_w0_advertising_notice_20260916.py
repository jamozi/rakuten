"""next30 Wave 0 (2026-09-16): every published article states its advertising, once.

The policy page makes two promises: 「広告を含む記事は、商品比較・購入リンクより前に、
広告・アフィリエイトリンクが含まれることを表示します。」 and 「広告を含まない記事は、
その旨を記事側で明示する運用にしています。」

Read on the published bodies alone the second promise looks broken: five
articles (262, 264, 265, 266, 552) carry no sentence about advertising inside
their body. The page a reader opens is the body *and* the theme, and the theme
is where that half is kept: templates/single.html prints
[kurashinoshirube_article_disclosure] under the title of every post, and
functions.php prints 「この記事にアフィリエイトリンクはありません。」 for a post with no
affiliate link. It steps aside only for a post whose body is verified against
the applied snapshot and already carries its own link-matched 断り. The policy
sentence and that notice were added in the same commit (47ed499a), so the
sentence describes the theme's notice; it was never a claim about body text.

What was missing is the pin. These checks read the body every ledger row
publishes and run the real theme PHP over it, and require exactly one
advertising statement per published article: the body's own 断り, placed before
the first advertising link, when the article carries advertising; the theme's
notice when it carries none. 「exactly one」 also forbids the opposite failure —
an article that states the same fact twice because a body notice was added where
the theme cannot stand aside. 552 is not in the purchase-support runtime, so its
context never verifies and its notice is always the theme's; a body notice there
could only ever be a second one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from raos.application.editorial.reader_html import Element, fragment
from tests.st1704.theme_php_harness import run_theme_php

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json"

POLICY_KEY = "about-ad-policy"
CARRIES_ADVERTISING = (
    "広告を含む記事は、商品比較・購入リンクより前に、"
    "広告・アフィリエイトリンクが含まれることを表示します。"
)
CARRIES_NO_ADVERTISING = "広告を含まない記事は、その旨を記事側で明示する運用にしています。"
# What the theme prints under the title of a post with no affiliate link.
THEME_NOTICE = "この記事にアフィリエイトリンクはありません。"
THEME_NOTICE_OPENING = '<p class="raos-ad-disclosure" data-raos-ad-disclosure="none">'
DISCLOSURE_CLASS = "ps-disclosure"
# The renderer marks an advertising link with rel="nofollow sponsored …".
ADVERTISING_REL = "sponsored"
ADVERTISING_WORDS = ("広告", "アフィリエイト")
# The five articles whose advertising statement is the theme's, measured today.
CARRIED_BY_THE_THEME = (
    "dishwasher-branch-faucet-guide",
    "dishwasher-cleaning-guide",
    "dishwasher-detergent-guide",
    "dishwasher-installation-measurement",
    "dishwasher-running-cost",
)

# The theme, run for real: one WordPress post per published article, its stored
# body, and the applied snapshot the owner-direct publisher records for it, so
# the verified path (and the stand-aside it allows) is the one under test.
PROGRAM = r"""
class RAOS_Codex_MCP_Owner_Direct {
    public static function public_article_snapshot($post_id) {
        return $GLOBALS['raos_snapshots'][$post_id] ?? null;
    }
}
$inputs = json_decode(file_get_contents($argv[2]), true, 512, JSON_THROW_ON_ERROR);
$out = array();
foreach ($inputs as $slug => $article) {
    $GLOBALS['raos_state']['singular'] = $article['post_type'];
    $GLOBALS['page'] = new WP_Post();
    foreach (array('ID' => $article['id'], 'post_type' => $article['post_type'],
        'post_status' => 'publish', 'post_password' => '', 'post_name' => $slug,
        'post_title' => $article['title'], 'post_excerpt' => $article['excerpt'],
        'post_content' => $article['content']) as $key => $value) {
        $GLOBALS['page']->$key = $value;
    }
    $GLOBALS['raos_snapshots'][$article['id']] = array(
        'id' => $article['id'], 'post_type' => $article['post_type'], 'slug' => $slug,
        'title' => $article['title'], 'excerpt' => $article['excerpt'],
        'block_markup' => $article['content'],
    );
    $out[$slug] = array(
        'notice' => kurashinoshirube_render_article_disclosure(
            array(), null, 'kurashinoshirube_article_disclosure'
        ),
        'affiliate' => kurashinoshirube_article_has_affiliate_links($article['id']),
        'verified' => is_array(kurashinoshirube_purchase_support_context()),
    );
}
echo json_encode($out, JSON_UNESCAPED_UNICODE);
"""


@pytest.fixture(scope="module")
def ledger() -> dict[str, dict]:
    rows = json.loads(LEDGER.read_text(encoding="utf-8"))["articles"]
    return {row["article_key"]: row for row in rows}


@pytest.fixture(scope="module")
def posts(ledger) -> dict[str, dict]:
    return {key: row for key, row in ledger.items() if row["post_type"] == "post"}


@pytest.fixture(scope="module")
def theme(posts, tmp_path_factory) -> dict[str, dict]:
    """The theme's own verdict per post, from the real functions.php."""
    payload = {
        row["slug"]: {
            "id": row["post_id"],
            "post_type": row["post_type"],
            "title": row["title"],
            "excerpt": row.get("excerpt") or "",
            "content": stored_body(row),
        }
        for row in posts.values()
    }
    path = tmp_path_factory.mktemp("advertising") / "posts.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return run_theme_php(PROGRAM, str(path))


def stored_body(row: dict) -> str:
    """What WordPress stores for this row: the tracked body, byte for byte."""
    source = row.get("body_source") or row["patch_source"]
    return (ROOT / source).read_text(encoding="utf-8")


def names_advertising(node: Element) -> bool:
    text = node.text()
    return any(word in text for word in ADVERTISING_WORDS)


def body_statements(body: str) -> list[Element]:
    """The body's own advertising 断り, whichever way it is worded."""
    return [
        node
        for node in fragment(body).find(cls=DISCLOSURE_CLASS)
        if names_advertising(node)
    ]


def advertising_links(body: str) -> list[Element]:
    return [
        anchor
        for anchor in fragment(body).find(tag="a")
        if ADVERTISING_REL in (anchor.attrs.get("rel") or "").split()
    ]


def first_positions(body: str) -> tuple[int | None, int | None]:
    """Document order of the first 断り and of the first advertising link."""
    nodes = list(fragment(body).walk())
    statement = next(
        (
            index
            for index, node in enumerate(nodes)
            if node.has(DISCLOSURE_CLASS) and names_advertising(node)
        ),
        None,
    )
    link = next(
        (
            index
            for index, node in enumerate(nodes)
            if node.tag == "a"
            and ADVERTISING_REL in (node.attrs.get("rel") or "").split()
        ),
        None,
    )
    return statement, link


def test_the_policy_page_publishes_both_halves_of_its_advertising_promise(
    ledger,
) -> None:
    body = stored_body(ledger[POLICY_KEY])
    assert CARRIES_ADVERTISING in body, body[-900:]
    assert CARRIES_NO_ADVERTISING in body, body[-900:]


def test_every_published_article_states_its_advertising_exactly_once(
    posts, theme
) -> None:
    """One statement reaches the reader: the body's, or the theme's, never both."""
    counted = {}
    for key, row in posts.items():
        statements = len(body_statements(stored_body(row)))
        printed = 1 if theme[row["slug"]]["notice"] else 0
        counted[key] = statements + printed
    assert {key: count for key, count in counted.items() if count != 1} == {}, counted


def test_an_article_with_advertising_names_it_before_its_first_link(
    posts, theme
) -> None:
    for key, row in posts.items():
        body = stored_body(row)
        if not advertising_links(body):
            continue
        statement, link = first_positions(body)
        assert statement is not None, key
        assert link is not None, key
        assert statement < link, (key, statement, link)
        # The body carries it, so the theme prints nothing of its own.
        assert theme[row["slug"]]["notice"] == "", (key, theme[row["slug"]])


def test_an_article_without_advertising_says_so_where_the_reader_opens_it(
    posts, theme
) -> None:
    silent = []
    for key, row in posts.items():
        body = stored_body(row)
        if advertising_links(body):
            continue
        silent.append(row["slug"])
        notice = theme[row["slug"]]
        assert notice["affiliate"] is False, key
        assert notice["notice"].startswith(THEME_NOTICE_OPENING), (key, notice)
        assert THEME_NOTICE in notice["notice"], (key, notice)
        # A body 断り here would be a second statement, not a first one.
        assert body_statements(body) == [], key
    assert sorted(silent) == sorted(CARRIED_BY_THE_THEME), silent


def test_the_theme_and_the_body_agree_on_which_articles_carry_advertising(
    posts, theme
) -> None:
    for key, row in posts.items():
        carried = bool(advertising_links(stored_body(row)))
        assert theme[row["slug"]]["affiliate"] is carried, (key, carried)


def test_the_theme_steps_aside_only_for_a_verified_body_that_names_advertising(
    posts, theme
) -> None:
    """Its own notice is the fallback; the body may replace it only when checked."""
    for key, row in posts.items():
        if theme[row["slug"]]["notice"]:
            continue
        assert theme[row["slug"]]["verified"] is True, key
        assert body_statements(stored_body(row)), key


def test_no_published_page_carries_an_advertising_link(ledger) -> None:
    """The promise speaks of 記事; nothing else the site publishes carries an ad."""
    offenders = {
        key: len(advertising_links(stored_body(row)))
        for key, row in ledger.items()
        if row["post_type"] != "post" and advertising_links(stored_body(row))
    }
    assert offenders == {}, offenders

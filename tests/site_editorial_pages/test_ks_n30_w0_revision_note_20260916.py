"""next30 Wave 0 (2026-09-16): the revision note claims exactly the surfaces it aligned.

The policy page's 改定内容 tells the reader what changed. Wave 0 renamed the two
category pages and rewrote the names that lead to them, and the note said the
naming was aligned 「カードやパンくず、記事一覧」. Two of those three are true. The
third is not: /easy-maintenance/ (134) is a published article listing that still
calls the same articles 「食洗機」「掃除機」, and it is outside this candidate (19
documents + the theme is the limit), so this wave cannot align it. A reader who
opens that one page disproves the note.

These checks read the note and the published bodies and hold them to each other
in both directions:

* every surface the note names as aligned really carries the new name, and
* no surface that still uses the old wording is named.

The surfaces are measured, not assumed: the cards from the published bodies, the
breadcrumb from the real theme PHP (it prints the hub's stored title, so the
crumb is the page name a reader sees), the back-links from every article body,
and the article listings from every heading that is a bare category name.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from raos.application.editorial.reader_html import Element, fragment
from scripts import build_site_editorial_pages as projection
from tests.st1704.theme_php_harness import run_theme_php

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json"
NAVIGATION = ROOT / (
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/editorial-navigation.v3.json"
)

POLICY_KEY = "about-ad-policy"
HUB_KEYS = ("kitchen", "cleaning")
# What the two pages are called now, and the words they stopped standing for.
NEW_TITLES = {"kitchen": "台所の道具の選び方・比較", "cleaning": "掃除の道具の選び方・比較"}
OLD_TITLES = {"kitchen": "食洗機の選び方・比較", "cleaning": "ロボット掃除機の選び方・比較"}
LABELS = {"kitchen": "台所", "cleaning": "掃除"}
RETIRED_LABELS = {"kitchen": "食洗機", "cleaning": "掃除機"}
CARD_CLASS = "ks-editorial-card"
HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
SKIPPED_TAGS = frozenset({"script", "style", "template", "code", "pre"})

# One word per surface, as the note writes it. A surface is "named" when its word
# appears in a sentence of the note that claims something was aligned (「そろえ」).
SURFACE_WORDS = {
    "cards": "カード",
    "breadcrumb": "パンくず",
    "back_links": "戻るリンク",
    "listings": "一覧",
}
# Every surface the programme has aligned so far; none may go stale again, no
# matter which wave's revision the note currently records.
ALIGNED_SO_FAR = ("cards", "breadcrumb", "back_links", "listings")
# The surface this wave really did align — W1 reached /easy-maintenance/ (134),
# the one listing W0 had to leave behind (DF07). The note may not drop it.
ALIGNED_BY_THIS_WAVE = ("listings",)

# The theme, run for real: the two category pages as stored pages (the breadcrumb
# reads their titles), one post at a time with the snapshot the owner-direct
# publisher records for it, and the breadcrumb shortcode the template prints.
PROGRAM = r"""
class RAOS_Codex_MCP_Owner_Direct {
    public static function public_article_snapshot($post_id) {
        return $GLOBALS['raos_snapshots'][$post_id] ?? null;
    }
}
$payload = json_decode(file_get_contents($argv[2]), true, 512, JSON_THROW_ON_ERROR);
foreach ($payload['hubs'] as $slug => $hub) {
    $page = new WP_Post();
    foreach (array('ID' => $hub['id'], 'post_type' => 'page', 'post_status' => 'publish',
        'post_password' => '', 'post_name' => $slug, 'post_title' => $hub['title'],
        'post_excerpt' => $hub['excerpt'], 'post_content' => '') as $key => $value) {
        $page->$key = $value;
    }
    $GLOBALS['pages'][$slug] = $page;
}
$GLOBALS['raos_state']['singular'] = 'post';
$out = array();
foreach ($payload['posts'] as $slug => $article) {
    kurashinoshirube_flush_reader_hub_page_cache();
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
    $out[$slug] = array(
        'category' => kurashinoshirube_reader_article_category($article['id']),
        'breadcrumb' => kurashinoshirube_render_breadcrumb(
            array(), '', 'kurashinoshirube_breadcrumb'
        ),
    );
}
echo json_encode($out, JSON_UNESCAPED_UNICODE);
"""


@pytest.fixture(scope="module")
def ledger() -> dict[str, dict]:
    rows = json.loads(LEDGER.read_text(encoding="utf-8"))["articles"]
    return {row["article_key"]: row for row in rows}


@pytest.fixture(scope="module")
def documents() -> dict[str, str]:
    """The public body per ledger row, exactly as the publisher would send it."""
    return projection.reader_documents()


def visible_text(node: Element) -> str:
    parts: list[str] = []

    def collect(element: Element) -> None:
        if element.tag in SKIPPED_TAGS:
            return
        for child in element.children:
            if isinstance(child, Element):
                collect(child)
            elif not child.startswith("<!--"):
                parts.append(child)

    collect(node)
    return "".join(parts)


def sentences(text: str) -> list[str]:
    """Split on 。 outside 「」 so a quoted name stays inside its sentence."""
    out, depth, current = [], 0, ""
    for char in text:
        current += char
        if char == "「":
            depth += 1
        elif char == "」":
            depth = max(0, depth - 1)
        elif char == "。" and depth == 0:
            out.append(current.strip())
            current = ""
    if current.strip():
        out.append(current.strip())
    return out


@pytest.fixture(scope="module")
def revision_note(documents) -> str:
    paragraphs = [
        p
        for p in fragment(documents[POLICY_KEY]).find(tag="p")
        if "改定内容：" in visible_text(p)
    ]
    assert len(paragraphs) == 1, "the policy page holds one revision note"
    return visible_text(paragraphs[0])


@pytest.fixture(scope="module")
def alignment_claim(revision_note) -> str:
    """The part of the note that claims a name was brought into line."""
    claims = [s for s in sentences(revision_note) if "そろえ" in s]
    assert claims, revision_note
    return "".join(claims)


def named_surfaces(claim: str) -> set[str]:
    return {key for key, word in SURFACE_WORDS.items() if word in claim}


def hub_of(href: str | None) -> str | None:
    if not href:
        return None
    path = href.split("#", 1)[0].split("?", 1)[0]
    for key in HUB_KEYS:
        if path.endswith(f"/{key}/"):
            return key
    return None


def heading_text(node: Element) -> str | None:
    for tag in HEADING_TAGS:
        found = node.find(tag=tag)
        if found:
            return visible_text(found[0]).strip()
    return None


def cards_that_lead_to_a_hub(documents) -> list[tuple[str, str, str | None]]:
    """(document, hub, card heading) for every card that links to a hub."""
    found = []
    for key, body in documents.items():
        for card in fragment(body).find(tag="article"):
            classes = (card.attrs.get("class") or "").split()
            if CARD_CLASS not in classes:
                continue
            hubs = {
                hub
                for anchor in card.find(tag="a")
                if (hub := hub_of(anchor.attrs.get("href"))) is not None
            }
            for hub in sorted(hubs):
                found.append((key, hub, heading_text(card)))
    return found


def hub_links_in_articles(ledger, documents) -> list[tuple[str, str, str]]:
    """(document, hub, link text) for every hub link inside an article body."""
    found = []
    for key, row in ledger.items():
        if row["post_type"] != "post":
            continue
        for anchor in fragment(documents[key]).find(tag="a"):
            hub = hub_of(anchor.attrs.get("href"))
            if hub is not None:
                found.append((key, hub, visible_text(anchor).strip()))
    return found


def bare_category_headings(ledger, documents) -> list[tuple[str, str]]:
    """(document, heading) for every heading that is only a category name."""
    words = set(LABELS.values()) | set(RETIRED_LABELS.values())
    found = []
    for key, row in ledger.items():
        if row["post_type"] != "page":
            continue
        for tag in HEADING_TAGS:
            for heading in fragment(documents[key]).find(tag=tag):
                text = visible_text(heading).strip()
                if text in words:
                    found.append((key, text))
    return found


@pytest.fixture(scope="module")
def breadcrumbs(ledger, documents, tmp_path_factory) -> dict[str, dict]:
    """What the real theme prints above every published post."""
    hubs = json.loads(NAVIGATION.read_text(encoding="utf-8"))
    registered = {hub["slug"]: hub["label"] for hub in hubs["reader_navigation"]["hubs"]}
    pages = {}
    for index, (slug, label) in enumerate(sorted(registered.items())):
        row = next(
            (r for r in ledger.values() if r["slug"] == slug and r["post_type"] == "page"),
            None,
        )
        pages[slug] = {
            "id": row["post_id"] if row else 900 + index,
            "title": row["title"] if row else label,
            "excerpt": (row.get("excerpt") if row else "") or "",
        }
    posts = {
        row["slug"]: {
            "id": row["post_id"],
            "title": row["title"],
            "excerpt": row.get("excerpt") or "",
            "content": documents[key],
        }
        for key, row in ledger.items()
        if row["post_type"] == "post"
        and row["mode"] == "existing"
        and (row.get("listing") or {}).get("state") == "published"
    }
    payload = tmp_path_factory.mktemp("breadcrumbs") / "payload.json"
    payload.write_text(
        json.dumps({"hubs": pages, "posts": posts}, ensure_ascii=False), encoding="utf-8"
    )
    return run_theme_php(PROGRAM, str(payload))


def measured_alignment(ledger, documents, breadcrumbs) -> dict[str, list[str]]:
    """Per surface, the places that still use a retired name (empty = aligned)."""
    stale: dict[str, list[str]] = {key: [] for key in SURFACE_WORDS}
    for key, hub, heading in cards_that_lead_to_a_hub(documents):
        if heading is None or LABELS[hub] not in heading:
            stale["cards"].append(f"{key}: {heading!r} → /{hub}/")
        elif RETIRED_LABELS[hub] in heading:
            stale["cards"].append(f"{key}: {heading!r} → /{hub}/")
    for slug, rendered in breadcrumbs.items():
        category = rendered["category"]
        if category is None or category["slug"] not in HUB_KEYS:
            continue
        label = category["label"]
        crumb = str(rendered["breadcrumb"])
        if label != NEW_TITLES[category["slug"]] or label not in crumb:
            stale["breadcrumb"].append(f"{slug}: {label!r}")
        if OLD_TITLES[category["slug"]] in crumb:
            stale["breadcrumb"].append(f"{slug}: {crumb!r}")
    for key, hub, text in hub_links_in_articles(ledger, documents):
        if not text.startswith(NEW_TITLES[hub]):
            stale["back_links"].append(f"{key}: {text!r} → /{hub}/")
    for key, heading in bare_category_headings(ledger, documents):
        if heading in RETIRED_LABELS.values():
            stale["listings"].append(f"{key}: {heading!r}")
    return stale


def test_the_breadcrumb_check_covers_exactly_the_posts_wordpress_has(
    ledger, breadcrumbs
) -> None:
    """The breadcrumb the theme prints belongs to a post that exists.

    next30 Wave 1 added three ``mode:"new"`` rows whose post id is still null.
    The theme cannot render a breadcrumb for one, so the payload is built from
    the ledger's published posts; the assertion keeps that set honest instead of
    letting a future wave quietly shrink what this note is measured against.
    """
    published = {
        row["slug"]
        for row in ledger.values()
        if row["post_type"] == "post"
        and row["mode"] == "existing"
        and (row.get("listing") or {}).get("state") == "published"
    }
    assert set(breadcrumbs) == published
    assert breadcrumbs


def test_the_note_keeps_the_old_and_the_new_page_names(revision_note) -> None:
    """A reader who bookmarked the old name has to find both names in the note."""
    for hub in HUB_KEYS:
        assert f"「{RETIRED_LABELS[hub]}」" in revision_note, hub
        assert f"「{LABELS[hub]}」" in revision_note, hub


def test_every_surface_the_note_names_really_carries_the_new_name(
    ledger, documents, breadcrumbs, alignment_claim
) -> None:
    """Each named surface is measured; a stale one makes the note false."""
    stale = measured_alignment(ledger, documents, breadcrumbs)
    named = named_surfaces(alignment_claim)
    assert named, alignment_claim
    for surface in sorted(named):
        assert stale[surface] == [], (surface, stale[surface], alignment_claim)


def test_the_note_names_no_surface_that_still_uses_the_old_wording(
    ledger, documents, breadcrumbs, alignment_claim
) -> None:
    """/easy-maintenance/ is outside this candidate, so 「一覧」 may not be claimed."""
    stale = measured_alignment(ledger, documents, breadcrumbs)
    for surface, places in sorted(stale.items()):
        if places:
            assert SURFACE_WORDS[surface] not in alignment_claim, (
                surface,
                places,
                alignment_claim,
            )


def test_the_note_still_names_every_surface_this_wave_aligned(
    ledger, documents, breadcrumbs, alignment_claim
) -> None:
    """Narrowing the claim may not empty it: the surface this wave aligned stays
    named, and no surface an earlier wave aligned may go stale again."""
    stale = measured_alignment(ledger, documents, breadcrumbs)
    named = named_surfaces(alignment_claim)
    for surface in ALIGNED_SO_FAR:
        assert stale[surface] == [], (surface, stale[surface])
    for surface in ALIGNED_BY_THIS_WAVE:
        assert surface in named, (surface, alignment_claim)


def test_the_listings_that_stay_behind_are_recorded_not_claimed(
    ledger, documents, breadcrumbs
) -> None:
    """The wave records the page it could not reach; 134 is that page today."""
    stale = measured_alignment(ledger, documents, breadcrumbs)
    record = json.loads(
        (ROOT / "changes/next30-20260916/decisions.v1.json").read_text(encoding="utf-8")
    )
    written = json.dumps(record, ensure_ascii=False)
    for place in stale["listings"]:
        document = place.split(":", 1)[0]
        assert document in written, (document, place)

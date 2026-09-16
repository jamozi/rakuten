"""Wave 0 of next30: the advertising sentence on /kitchen/ has to hold for the
eleven articles the shelf actually carries.

Base 9fa8ee45 said 「比較記事には広告を含みます。」 — true, because every article with
an advertising link was a comparison. The wave replaced it with 「広告の有無は記事
ごとに、記事の中で示します。」, which claims both halves: that an article says when
it carries advertising *and* when it does not. The second half is not rendered
anywhere — five of the six kitchen guides print no sentence about advertising at
all — so the wave turned a true sentence into a false one.

What the renderer really emits, read back below from the published bodies: an
article carries a disclosure naming 広告 before its first advertising link
exactly when it has one, and says nothing when it has none. The sentence on the
hub is pinned to that, and the pin reads the rendered bodies so the claim cannot
drift when an article gains or loses its advertising links.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from raos.application.editorial.reader_html import Element, fragment
from scripts import build_site_editorial_pages as projection

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json"

CATEGORY = "kitchen"
# The sentence the hub prints, and the claim it is allowed to make.
NOTE = "広告リンクを含む記事は、記事の中でその旨を示します。"
FORBIDDEN_NOTES = (
    # Not true of the five guides that carry no advertising link at all.
    "広告の有無は記事ごとに",
    # Not true of the guide that does carry advertising links.
    "比較記事には広告を含みます",
)
DISCLOSURE_CLASS = "ps-disclosure"
# The renderer marks an advertising link with rel="sponsored nofollow …".
ADVERTISING_REL = "sponsored"


@pytest.fixture(scope="module")
def ledger() -> dict[str, dict]:
    rows = json.loads(LEDGER.read_text(encoding="utf-8"))["articles"]
    return {row["article_key"]: row for row in rows}


@pytest.fixture(scope="module")
def documents() -> dict[str, str]:
    return projection.reader_documents()


def kitchen_articles(ledger: dict[str, dict]) -> list[str]:
    return [
        key
        for key, row in ledger.items()
        if (row.get("listing") or {}).get("category") == CATEGORY
    ]


def advertising_links(body: str) -> list[Element]:
    return [
        anchor
        for anchor in fragment(body).find(tag="a")
        if ADVERTISING_REL in (anchor.attrs.get("rel") or "").split()
    ]


def carries_advertising(body: str) -> bool:
    return bool(advertising_links(body))


def disclosure_text(body: str) -> str | None:
    found = fragment(body).find(cls=DISCLOSURE_CLASS)
    return None if not found else "".join(node.text() for node in found)


def test_the_kitchen_shelf_holds_the_articles_this_sentence_covers(
    ledger,
) -> None:
    """The sentence is about a known shelf: eleven articles, five with no ads."""
    keys = kitchen_articles(ledger)
    assert len(keys) == 11, keys
    documents = projection.reader_documents()
    with_ads = [key for key in keys if carries_advertising(documents[key])]
    assert len(with_ads) == 6, with_ads
    assert len(keys) - len(with_ads) == 5


def test_every_kitchen_article_with_advertising_says_so_inside_the_article(
    documents, ledger
) -> None:
    for key in kitchen_articles(ledger):
        body = documents[key]
        if not carries_advertising(body):
            continue
        text = disclosure_text(body)
        assert text is not None, key
        assert "広告" in text, (key, text)
        # 「記事の中で示します」 is only true if the reader meets it before the link.
        assert body.index(DISCLOSURE_CLASS) < body.index('rel="sponsored'), key


def test_a_kitchen_article_without_advertising_carries_no_disclosure(
    documents, ledger
) -> None:
    """The hub may not claim the silent half: nothing renders it."""
    for key in kitchen_articles(ledger):
        body = documents[key]
        if carries_advertising(body):
            continue
        assert DISCLOSURE_CLASS not in body, key
        assert "この記事に広告リンクはありません" not in body, key


def test_the_hub_note_says_only_what_the_articles_render(documents) -> None:
    body = documents[CATEGORY]
    assert NOTE in body, body[-600:]
    for forbidden in FORBIDDEN_NOTES:
        assert forbidden not in body, forbidden

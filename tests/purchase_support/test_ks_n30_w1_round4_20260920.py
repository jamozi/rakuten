"""next30 Wave 1 round 4 (2026-09-20): the 確認・更新履歴 describes this article.

The 確認・更新履歴 of an article is reader-facing prose that tells a reader what
was checked and what moved. Round 3 left two entries that describe a different
article from the one that shipped, so both of them are rules here rather than
sentences:

* **An entry that names where the body put something names where it is.** A03's
  second 2026-09-19 entry said the whole 紹介本文 of 5070 was quoted 「1か所（表B）」
  and that the 据え置き frame points at 表B for it. The body quotes it once in
  出典と確認日 -- which is where round 3 decided to put it, because the same
  quotation inside the 表B cell took that row from 10,734px to 12,315px at 320px
  -- and the 据え置き frame points there. A reader who follows 表B finds a table
  of dimensions and no quotation at all, so the entry sends them to the wrong
  place twice.
* **An entry that credits a record field names what that field holds.** The same
  entry said the source element name was written into the catalog locator. The
  locator of 5070's 置き方 fact has read 「商品ページ冒頭の紹介見出し・紹介本文、および
  「Product Details 仕様・サイズ」表の「対応サイズ」行」 since cb6fae23 and no round
  of this wave has touched it. The half of that sentence that is true -- the fact
  text itself was replaced with the whole 紹介本文 -- is checked here too, so the
  rule has something to hold on to and not only something to forbid.
* **An entry that prints a rendered width prints the measured one.** A01's second
  2026-09-19 entry published 52.0＋221.33px for 表1. The shipped CSS declares
  ``min-width:44rem`` and a 3.25rem first column over three data columns, which
  is 52.0＋217.33px, and that is what Chromium renders. 221.33px is the figure a
  44.75rem min-width would have produced; no version of the theme on this branch
  ever declared it.

Measured 2026-09-20 with ``node tests/purchase_support/phone_table_frames.mjs
dish-rack-installation-measurement 320,360,375,390`` (playwright, Chromium
152.0.7977.8) against the committed theme and the published body:

    表1  320 286 52.0 217.33 | 360 326 52.0 217.33 | 375 341 52.0 217.33 | 390 356 52.0 217.33
    表2  320 286 88.0 194.66 | 360 326 88.0 194.66 | 375 341 88.0 194.66 | 390 356 88.0 194.66

The recorded numbers live in ``tests/purchase_support/phone_table_frames.py``
beside the frames, and the CSS that produces them is checked against them here,
so a theme change that moves a column makes this test say so instead of leaving
the article printing a stale pixel. No ``\\b`` is used next to Japanese text.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

from raos.application.editorial.reader_html import Element, fragment
from tests.purchase_support import phone_table_frames

ROOT = Path(__file__).resolve().parents[2]
PUBLISHED = ROOT / "changes/wordpress-direct-publish-v1/articles"
CATALOG = ROOT / "changes/reader-purchase-support-v1/purchase-support.v1.json"
THEME_CSS = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/theme.css"
)

MEASURE = "dish-rack-installation-measurement"
SLIM = "slim-dish-rack-under-20cm"
NO_SPACE = "dish-rack-no-space"
WAVE = (MEASURE, SLIM, NO_SPACE)

#: product_id -> the model number the bodies and the records print.
WAVE_PRODUCTS = {
    "PRD-YAMAZAKI-4314": "4314",
    "PRD-YAMAZAKI-5070": "5070",
    "PRD-SHIMOMURA-42666": "42666",
    "PRD-YAMAZAKI-7835": "7835",
    "PRD-YAMAZAKI-3492": "3492",
}

#: 「紹介本文は「…」」 -- the quotation a fact introduces as the whole text.
WHOLE_INTRO_QUOTE = re.compile(r"紹介本文[はが]「([^」]+)」")

#: 「…の全文を1か所（X）に引用し直した」 -- where the entry says the body quotes it.
QUOTED_IN = re.compile(r"全文を1か所（([^）]+)）に")
#: 「全文の置き場所（X）を案内する形にした」 -- where the entry says the body sends the reader.
POINTED_AT = re.compile(r"全文の置き場所（([^）]+)）を案内")
#: 「全文（X に引用）」 -- the body's own pointer at the quotation.
BODY_POINTER = re.compile(r"全文（([^）]*?)に引用）")

#: A sentence crediting the catalog's ``locator`` field with something.
LOCATOR_CREDIT = re.compile(r"[^。]*locator[^。]*?(?:書いた|記録した|入れた)[^。]*。")
#: A CSS-ish element name. Written without ``\b`` so a Japanese character before
#: it cannot hide it: in Python's Unicode ``re`` a kanji counts as a word
#: character, and ``\b`` would then refuse to match at the boundary.
ELEMENT_NAME = re.compile(r"[a-z][a-z0-9]*\.[a-z][a-z0-9_-]*")
#: 「カタログの「置き方」factも全文に差し替え」 -- the record change the entry credits.
FACT_REPLACED = re.compile(r"カタログの「([^」]+)」fact(?:も)?全文に差し替え")

#: 「320/360/375/390pxの実測で、枠の内寸286/…pxに対し1列目＋データ1列が表1は52.0＋217.33px、…」
MEASURED_COLUMNS = re.compile(
    r"(?P<views>[0-9/]+)pxの実測で、枠の内寸(?P<frames>[0-9/]+)px"
    r"に対し1列目＋データ1列が表1は(?P<head1>[0-9.]+)＋(?P<data1>[0-9.]+)px、"
    r"表2は(?P<head2>[0-9.]+)＋(?P<data2>[0-9.]+)px"
)
#: 表1 and 表2 of A01, in the order the sentence above prints them.
MEASURE_TABLES = ("ks-measure-sheet-table", "ks-measure-condition-table")


@pytest.fixture(scope="module")
def catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def roots() -> dict[str, Element]:
    return {
        slug: fragment((PUBLISHED / (slug + ".html")).read_text(encoding="utf-8"))
        for slug in WAVE
    }


def article_of(catalog: dict, slug: str) -> dict:
    for article in catalog["articles"]:
        if article["slug"] == slug:
            return article
    raise AssertionError(f"{slug} is not in the catalog")


def history_of(catalog: dict, slug: str) -> list[dict]:
    return article_of(catalog, slug).get("history", [])


def facts_of(catalog: dict, product_id: str) -> list[dict]:
    for product in catalog["products"]:
        if product["product_id"] == product_id:
            return product["facts"]
    return []


def fact_of(catalog: dict, product_id: str, label_part: str) -> dict | None:
    for fact in facts_of(catalog, product_id):
        if label_part in fact["label"]:
            return fact
    return None


def recorded_intro(catalog: dict, product_id: str) -> str | None:
    """The whole 紹介本文 of a product, as its 置き方 fact holds it."""
    fact = fact_of(catalog, product_id, "置き方")
    if fact is None:
        return None
    match = WHOLE_INTRO_QUOTE.search(fact["text"])
    return match.group(1) if match else None


def models_in(text: str) -> list[str]:
    return [
        product_id for product_id, model in WAVE_PRODUCTS.items() if model in text
    ]


def place_name(raw: str) -> str:
    """The bare name of a place an entry or a body points at.

    「「出典と確認日」の節」, 「この記事の出典と確認日の節」 and 「出典と確認日」 are the
    same place; 「表B」 is a different one.
    """
    name = raw.strip()
    name = re.sub(r"^この記事の", "", name)
    name = re.sub(r"の節$", "", name)
    return name.strip("「」")


def table_of(node: Element | None) -> Element | None:
    while node is not None:
        if node.tag == "table":
            return node
        node = node.parent
    return None


def place_of(root: Element, needle: str) -> str:
    """Where in a published body a string sits: a 表X cell, or a ``<h2>`` section."""
    nodes = [node for node in root.walk() if node.tag]
    holders = [node for node in nodes if needle in node.text()]
    assert holders, f"the body does not carry {needle[:40]!r}"
    deepest = holders[-1]
    table = table_of(deepest)
    if table is not None:
        captions = table.find(tag="caption")
        label = re.match(r"\s*(表[A-Za-z0-9]+)", captions[0].text()) if captions else None
        return label.group(1) if label else "表（見出しなし）"
    position = nodes.index(deepest)
    headings = [node for node in nodes[:position] if node.tag == "h2"]
    assert headings, f"{needle[:40]!r} sits under no <h2>"
    return headings[-1].text()


# --- finding 1: the entry describes the article that shipped -----------------


def test_a_history_entry_names_the_place_the_body_really_quotes_the_whole_text(
    catalog, roots
):
    """「全文を1か所（X）に引用し直した」 -- X is where the body carries it."""
    checked = 0
    for slug in WAVE:
        for entry in history_of(catalog, slug):
            claimed = QUOTED_IN.search(entry["text"])
            if not claimed:
                continue
            for product_id in models_in(entry["text"]):
                whole = recorded_intro(catalog, product_id)
                if not whole:
                    continue
                checked += 1
                assert place_name(claimed.group(1)) == place_of(roots[slug], whole), (
                    f"{slug} {entry['date']}: the entry sends the reader to "
                    f"{claimed.group(1)!r} for {WAVE_PRODUCTS[product_id]}'s whole "
                    f"紹介本文, which the body carries in "
                    f"{place_of(roots[slug], whole)!r}"
                )
    assert checked, "no history entry of the wave says where a whole text is quoted"


def test_a_history_entry_names_the_place_the_body_really_points_the_reader_at(
    catalog, roots
):
    """「全文の置き場所（X）を案内する形にした」 -- the body's pointer names X too."""
    checked = 0
    for slug in WAVE:
        body = roots[slug].text()
        for entry in history_of(catalog, slug):
            claimed = POINTED_AT.search(entry["text"])
            if not claimed:
                continue
            pointers = [
                place_name(found) for found in BODY_POINTER.findall(body)
            ]
            assert pointers, (
                f"{slug} {entry['date']}: the entry says the body points at "
                f"{claimed.group(1)!r}, but the body points at nothing"
            )
            checked += 1
            assert place_name(claimed.group(1)) in pointers, (
                f"{slug} {entry['date']}: the entry says the body points at "
                f"{claimed.group(1)!r}; the body points at {pointers}"
            )
    assert checked, "no history entry of the wave says where the body points"


def test_a_history_entry_credits_the_records_with_what_they_hold(catalog):
    """A field an entry names holds the string the entry attributes to it."""
    replacements = 0
    for slug in WAVE:
        for entry in history_of(catalog, slug):
            text = entry["text"]
            for sentence in LOCATOR_CREDIT.findall(text):
                named = set(ELEMENT_NAME.findall(text))
                assert named, (
                    f"{slug} {entry['date']}: {sentence!r} credits the locator "
                    "with an element name the entry never prints"
                )
                locators = {
                    fact["locator"]
                    for product_id in models_in(text)
                    for fact in facts_of(catalog, product_id)
                }
                for element in named:
                    assert any(element in locator for locator in locators), (
                        f"{slug} {entry['date']}: the entry says {element!r} was "
                        f"written into the catalog locator; no locator of "
                        f"{[WAVE_PRODUCTS[p] for p in models_in(text)]} holds it"
                    )
            replaced = FACT_REPLACED.search(text)
            if not replaced:
                continue
            for product_id in models_in(text):
                fact = fact_of(catalog, product_id, replaced.group(1))
                if fact is None:
                    continue
                whole = recorded_intro(catalog, product_id)
                replacements += 1
                assert whole and whole in fact["text"], (
                    f"{slug} {entry['date']}: the entry says the "
                    f"{replaced.group(1)!r} fact of {WAVE_PRODUCTS[product_id]} "
                    "was replaced with the whole text; it was not"
                )
    assert replacements, "no history entry of the wave credits a fact replacement"


# --- finding 2: the entry prints the width the page renders ------------------


def test_a_history_entry_prints_the_measured_column_widths(catalog):
    """The pixels A01 publishes are the pixels ``phone_table_frames`` measured."""
    entries = [
        entry
        for entry in history_of(catalog, MEASURE)
        if MEASURED_COLUMNS.search(entry["text"])
    ]
    assert len(entries) == 1, [entry["date"] for entry in entries]
    found = MEASURED_COLUMNS.search(entries[0]["text"])
    assert found is not None

    views = [int(value) for value in found.group("views").split("/")]
    frames = [float(value) for value in found.group("frames").split("/")]
    assert views == sorted(phone_table_frames.ARTICLE_SCROLL_FRAME), views
    assert frames == [phone_table_frames.ARTICLE_SCROLL_FRAME[view] for view in views]

    printed = {
        MEASURE_TABLES[0]: (float(found.group("head1")), float(found.group("data1"))),
        MEASURE_TABLES[1]: (float(found.group("head2")), float(found.group("data2"))),
    }
    for table_class, pair in printed.items():
        assert pair == phone_table_frames.MEASURE_TABLE_COLUMNS[table_class], (
            f"{MEASURE} publishes {pair} for {table_class}; the measured widths "
            f"are {phone_table_frames.MEASURE_TABLE_COLUMNS[table_class]}"
        )


def test_the_shipped_css_still_produces_the_measured_column_widths():
    """The recorded measurement and the theme cannot drift apart silently."""
    phone = phone_table_frames.phone_block(THEME_CSS.read_text(encoding="utf-8"))
    for table_class in MEASURE_TABLES:
        total = re.search(
            r"table\." + re.escape(table_class) + r"\{min-width:(\d+(?:\.\d+)?)rem!important",
            phone,
        )
        first = re.search(
            r"table\."
            + re.escape(table_class)
            + r":is\(theadth:first-child,tbodyth\)\{width:(\d+(?:\.\d+)?)rem!important",
            phone,
        )
        assert total and first, table_class
        head, width = float(first.group(1)) * 16, float(total.group(1)) * 16
        columns = phone_table_frames.data_columns(MEASURE, table_class)
        measured_head, measured_data = phone_table_frames.MEASURE_TABLE_COLUMNS[table_class]
        assert head == measured_head, (table_class, head, measured_head)
        # Chromium lays a column out in 1/64px units, so the rendered width is
        # the declared share rounded down, not the exact quotient.
        assert 0 <= (width - head) / columns - measured_data <= 0.01, (
            table_class,
            (width - head) / columns,
            measured_data,
        )

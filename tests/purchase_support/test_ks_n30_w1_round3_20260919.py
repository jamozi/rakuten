"""next30 Wave 1 round 3 (2026-09-19): the criterion, the quoted text, the frame.

Round 2 left three things that are each a rule rather than a sentence, so each
one is measured here against the tracked records and against the real rendered
frame:

* **The criterion in the ledger is the criterion in the body.** A02 states a
  threshold over a printed dimension (短辺20cm以下). The catalog says four of the
  wave's products clear it; the body compares three, because the maker's own
  page sends 3492 to the sink edge. A ``title`` or ``excerpt`` that names the
  threshold without the restriction the body applies promises a set the article
  does not deliver, so the threshold and the restriction travel together and any
  「N商品」 beside them is recomputed from the products the body shows.
* **Placement wording in the ledger belongs to the page that prints it.** Round
  2 fixed this inside the bodies; the same rule holds for the ``title``,
  ``excerpt`` and ``reader_role`` strings, which are the first thing a reader
  sees on a hub card. 4314's page prints 「狭いシンク横に置ける」; 5070's page
  prints no placement surface at all, so no ledger string may hand it one.
* **A maker's 紹介本文 is one text.** Round 2 left it quoted three ways: a
  one-sentence fragment and a two-sentence fragment, each introduced as
  「紹介本文は「…」」, while a third record cited a sentence both fragments cut.
  A record that cites 「紹介本文の末尾」 therefore has to agree with the recorded
  紹介本文, a quotation introduced as the 紹介本文 has to be that whole text, a
  quotation introduced as its 冒頭 has to be its opening, and a body that tells
  the reader what the 紹介本文 does not say has to carry the whole text once so
  the reader can check the claim. The same rules hold for the records: the live
  catalog and the verified copy it is taken from both held the truncation.
* **A table that does not fit scrolls.** 表1 and 表2 of A01 were contained
  instead: at a 320px viewport every column was 71.5px wide, so cells broke at
  3-5 characters and 表2's rows ran 1008-1212px tall (measured 2026-09-19 with
  ``tests/purchase_support/phone_table_frames.mjs``). They take the treatment the
  published bodies use -- ``data-ks-table-layout="scroll"`` plus a declared
  min-width and first-column width under ``table-layout:fixed`` -- and the budget
  below is the measured frame, not a derived one.

Measured 2026-09-19, Chromium via playwright, the committed theme, the same
document ``phone_table_frames.mjs`` assembles (viewport / frame inner / first
column / first data column, px):

    表1  320 286 52.0 217.33 | 360 326 52.0 217.33 | 375 341 52.0 217.33 | 390 356 52.0 217.33
    表2  320 286 88.0 194.66 | 360 326 88.0 194.66 | 375 341 88.0 194.66 | 390 356 88.0 194.66

The same run puts 表1's height at 610px (was 1504) and 表2's at 2265px (was
6031), with 表2's tallest row at 461px where it was 1212.

``document.documentElement.scrollWidth`` stays at the viewport width at all four
sizes, so the page itself never scrolls sideways. No ``\\b`` is used next to
Japanese text.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

from raos.application.editorial.reader_html import Element, fragment
from tests.purchase_support import phone_table_frames

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "changes/reader-purchase-support-v1/articles"
PUBLISHED = ROOT / "changes/wordpress-direct-publish-v1/articles"
CATALOG = ROOT / "changes/reader-purchase-support-v1/purchase-support.v1.json"
REGISTRY = ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json"
THEME_CSS = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/theme.css"
)

MEASURE = "dish-rack-installation-measurement"
SLIM = "slim-dish-rack-under-20cm"
NO_SPACE = "dish-rack-no-space"
WAVE = (MEASURE, SLIM, NO_SPACE)

#: product_id -> the model number the bodies and the ledger print.
WAVE_PRODUCTS = {
    "PRD-YAMAZAKI-4314": "4314",
    "PRD-YAMAZAKI-5070": "5070",
    "PRD-SHIMOMURA-42666": "42666",
    "PRD-YAMAZAKI-7835": "7835",
    "PRD-YAMAZAKI-3492": "3492",
}

#: The threshold A02 states over a printed dimension, in mm.
SHORT_SIDE_LIMIT_MM = 200
#: The restriction that separates the products A02 compares from the ones that
#: merely clear the threshold: the body sets these down, it does not hang them.
RESTRICTION = re.compile("据え置|すき間に置く")
#: 「N商品」 as a count. A model number (4314, 42666) is never one of these.
COUNTED_PRODUCTS = re.compile(r"(?<![0-9０-９])([0-9０-９]{1,2})\s*商品(?!ページ)")
ASCII_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")

#: Placement wording a maker page either prints for a product or does not.
PLACEMENT_WORDS = (
    "シンク横",
    "シンク脇",
    "シンクの上",
    "シンクのフチ",
    "シンク渡し",
    "作業台",
)

#: 「紹介本文は「…」」 / 「紹介本文が「…」」 -- the quotation introduced as the whole
#: text. 「紹介本文には「…」とあります」 and 「紹介本文の末尾」 name a part and are
#: checked as parts instead.
WHOLE_INTRO_QUOTE = re.compile(r"紹介本文[はが]「([^」]+)」")
#: 「紹介本文の冒頭は「…」」 -- the quotation introduced as the opening of that text.
HEAD_INTRO_QUOTE = re.compile(r"紹介本文の冒頭は「([^」]+)」")
#: The fact that records where a maker says the product is put, whole intro text included.
PLACEMENT_FACT = "置き方"
TAIL_LOCATOR = "紹介本文の末尾"
#: The body telling the reader a maker prints no such wording.
ABSENT_WORDING = re.compile(
    "書かれていません|名指ししていません|印字していません|印字されていません|記載はありません"
)


@pytest.fixture(scope="module")
def catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ledger() -> dict[str, dict]:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return {row["article_key"]: row for row in registry["articles"]}


@pytest.fixture(scope="module")
def bodies() -> dict[str, str]:
    return {slug: (TEMPLATES / (slug + ".html")).read_text(encoding="utf-8") for slug in WAVE}


@pytest.fixture(scope="module")
def roots(bodies: dict[str, str]) -> dict[str, Element]:
    return {slug: fragment(markup) for slug, markup in bodies.items()}


def plain(markup: str) -> str:
    return re.sub(r"<[^>]+>", "", markup)


def claims(text: str) -> list[str]:
    """One claim per sentence, with 「…」 kept whole: a quotation is not a boundary."""
    out: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char == "「":
            depth += 1
        elif char == "」":
            depth = max(0, depth - 1)
        if char == "\n" and depth == 0:
            if "".join(current).strip():
                out.append("".join(current))
            current = []
            continue
        current.append(char)
        if char == "。" and depth == 0:
            out.append("".join(current))
            current = []
    if "".join(current).strip():
        out.append("".join(current))
    return out


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


def printed_text(catalog: dict, product_id: str) -> str:
    return "".join(fact["text"] for fact in facts_of(catalog, product_id))


def short_side_mm(catalog: dict, product_id: str) -> int:
    fact = fact_of(catalog, product_id, "本体寸法")
    assert fact is not None, f"{product_id} has no 本体寸法 fact"
    match = re.search(r"奥行([0-9]+)", fact["text"])
    assert match, f"{product_id} prints no 奥行 in {fact['text']!r}"
    return int(match.group(1))


def recorded_intro(catalog: dict, product_id: str) -> str | None:
    """The whole 紹介本文 of a product, as the 置き方 fact holds it."""
    fact = fact_of(catalog, product_id, PLACEMENT_FACT)
    if fact is None:
        return None
    match = WHOLE_INTRO_QUOTE.search(fact["text"])
    return match.group(1) if match else None


def shown_products(root: Element) -> set[str]:
    found: set[str] = set()
    for node in root.walk():
        for key in ("data-product-id", "data-ps-media-product", "data-ps-purchase-product"):
            value = node.attrs.get(key)
            if isinstance(value, str) and value in WAVE_PRODUCTS:
                found.add(value)
    return found


def ledger_strings(row: dict) -> list[tuple[str, str]]:
    """Every reader-facing string the ledger row carries, by name."""
    role = row["reader_role"]
    out = [("title", row["title"]), ("excerpt", row["excerpt"])]
    for key in ("primary_intent", "reader", "decision_after_reading"):
        out.append((f"reader_role.{key}", role[key]))
    out.append(("reader_role.main_cta.label", role["main_cta"]["label"]))
    out.append(("reader_role.next_question.question", role["next_question"]["question"]))
    return out


# --- finding 1: the criterion in the ledger is the criterion in the body ------


def test_the_threshold_alone_selects_more_products_than_a02_compares(catalog, roots):
    """The premise of the next test: without the restriction the counts differ."""
    clears = {
        pid for pid in WAVE_PRODUCTS if short_side_mm(catalog, pid) <= SHORT_SIDE_LIMIT_MM
    }
    shown = shown_products(roots[SLIM])
    assert len(clears) == 4, sorted(WAVE_PRODUCTS[p] for p in clears)
    assert len(shown) == 3, sorted(WAVE_PRODUCTS[p] for p in shown)


def test_a_ledger_count_beside_the_threshold_is_recomputed_from_the_catalog(catalog, roots, ledger):
    """The threshold alone counts four; only the restriction brings it to three."""
    clears = {
        pid for pid in WAVE_PRODUCTS if short_side_mm(catalog, pid) <= SHORT_SIDE_LIMIT_MM
    }
    shown = shown_products(roots[SLIM])
    for slug in WAVE:
        for name, value in ledger_strings(ledger[slug]):
            for sentence in claims(value):
                if "20cm" not in sentence:
                    continue
                restricted = bool(RESTRICTION.search(sentence))
                for match in COUNTED_PRODUCTS.finditer(sentence):
                    claimed = int(match.group(1).translate(ASCII_DIGITS))
                    expected = len(shown) if restricted else len(clears)
                    which = (
                        "the products A02 sets down in the gap"
                        if restricted
                        else "the products that clear 短辺20cm以下"
                    )
                    assert claimed == expected, (
                        f"{slug} {name} says {claimed}商品 where {which} is "
                        f"{expected}: {sentence!r}"
                    )


def test_the_ledger_states_the_criterion_a02_actually_applies(ledger):
    """Somewhere in the title or the excerpt, the threshold travels with the restriction."""
    row = ledger[SLIM]
    stated = [
        sentence
        for sentence in claims(row["title"] + "。" + row["excerpt"])
        if "20cm" in sentence and RESTRICTION.search(sentence)
    ]
    assert stated, (
        f"{SLIM} names 短辺20cm以下 without ever saying the article compares only "
        f"the ones it sets down in the gap: {row['title']!r} / {row['excerpt']!r}"
    )


def test_no_ledger_string_gives_a_product_a_placement_its_page_never_prints(catalog, ledger):
    """One sentence, one set of products: the wording holds for every one it names."""
    for slug in WAVE:
        for name, value in ledger_strings(ledger[slug]):
            for sentence in claims(value):
                named = {
                    pid for pid, model in WAVE_PRODUCTS.items() if model in sentence
                }
                if not named:
                    continue
                for word in PLACEMENT_WORDS:
                    if word not in sentence:
                        continue
                    for pid in sorted(named):
                        assert word in printed_text(catalog, pid), (
                            f"{slug} {name} puts 「{word}」 beside "
                            f"{WAVE_PRODUCTS[pid]}, whose maker page prints no "
                            f"such wording: {sentence!r}"
                        )


# --- finding 2: a maker's 紹介本文 is one text --------------------------------


def test_every_yamajitsu_rack_records_its_whole_intro_text_once(catalog):
    """The 置き方 fact is where the whole text lives; without it nothing can be checked."""
    for pid in ("PRD-YAMAZAKI-4314", "PRD-YAMAZAKI-5070", "PRD-YAMAZAKI-7835", "PRD-YAMAZAKI-3492"):
        whole = recorded_intro(catalog, pid)
        assert whole, (
            f"{WAVE_PRODUCTS[pid]} records no 紹介本文 in its 「{PLACEMENT_FACT}」 "
            "fact, so no quotation of it can be checked"
        )


def test_a_record_citing_the_tail_of_an_intro_text_agrees_with_the_recorded_text(catalog):
    """A fact located at 「紹介本文の末尾」 is the end of the recorded 紹介本文."""
    checked = 0
    for pid in WAVE_PRODUCTS:
        whole = recorded_intro(catalog, pid)
        if not whole:
            continue
        for fact in facts_of(catalog, pid):
            if TAIL_LOCATOR not in (fact.get("locator") or ""):
                continue
            quoted = re.search(r"「([^」]+)」", fact["text"])
            assert quoted, fact["text"]
            checked += 1
            assert whole.endswith(quoted.group(1)), (
                f"{WAVE_PRODUCTS[pid]}: 「{fact['label']}」 is located at "
                f"{TAIL_LOCATOR} and quotes {quoted.group(1)!r}, which the "
                f"recorded 紹介本文 does not end with: {whole!r}"
            )
    assert checked, "no record of the wave cites the tail of an intro text"


def test_a_quotation_introduced_as_an_intro_text_is_that_whole_text(catalog, bodies):
    wholes = {
        recorded_intro(catalog, pid)
        for pid in WAVE_PRODUCTS
        if recorded_intro(catalog, pid)
    }
    sources: dict[str, str] = {slug: plain(bodies[slug]) for slug in WAVE}
    for pid in WAVE_PRODUCTS:
        for fact in facts_of(catalog, pid):
            sources[f"catalog:{WAVE_PRODUCTS[pid]}:{fact['label']}"] = fact["text"]
    for article in catalog["articles"]:
        if article.get("slug") not in WAVE:
            continue
        for entry in article.get("history", []):
            sources[f"history:{article['slug']}:{entry['date']}"] = entry["text"]
    for where, text in sources.items():
        for match in WHOLE_INTRO_QUOTE.finditer(text):
            assert match.group(1) in wholes, (
                f"{where} introduces {match.group(1)!r} as a 紹介本文, but no "
                "maker page prints that as its whole 紹介本文"
            )


def test_a_quotation_introduced_as_the_opening_of_an_intro_text_is_its_opening(catalog):
    """3492's 対応サイズ record quotes one sentence; it has to say it is the first."""
    heads = {
        recorded_intro(catalog, pid)
        for pid in WAVE_PRODUCTS
        if recorded_intro(catalog, pid)
    }
    checked = 0
    for pid in WAVE_PRODUCTS:
        for fact in facts_of(catalog, pid):
            for match in HEAD_INTRO_QUOTE.finditer(fact["text"]):
                checked += 1
                assert any(whole.startswith(match.group(1)) for whole in heads), (
                    f"{WAVE_PRODUCTS[pid]} 「{fact['label']}」 calls "
                    f"{match.group(1)!r} the opening of a 紹介本文 that starts "
                    "with something else"
                )
    assert checked, "no record of the wave quotes the opening of an intro text"


def test_a_body_that_says_what_an_intro_text_omits_carries_that_text_once(catalog, bodies):
    """A negative claim about a 紹介本文 travels with the whole text, once.

    The claim and the quotation do not have to share a cell -- A03 draws the
    conclusion in the placement group and prints the text in 出典と確認日, which
    keeps the 表B row at the height it had (10,734px at 320px against 10,742px
    before the wave) instead of the 12,315px the same quotation cost inside the
    cell -- but the body that draws it has to carry the whole text exactly once,
    so a reader can hold the conclusion against everything the maker actually
    wrote. The claim is read one sentence at a time: a paragraph that says 4314
    prints a surface and 5070 prints none makes one negative claim, not two.
    """
    checked = 0
    for slug in WAVE:
        text = plain(bodies[slug])
        for sentence in claims(text):
            if "紹介本文" not in sentence or not ABSENT_WORDING.search(sentence):
                continue
            for pid, model in WAVE_PRODUCTS.items():
                if model not in sentence:
                    continue
                whole = recorded_intro(catalog, pid)
                if not whole:
                    continue
                checked += 1
                assert text.count(whole) == 1, (
                    f"{slug} tells the reader what {model}'s 紹介本文 does not "
                    f"print, but prints the whole text {text.count(whole)} times "
                    f"instead of once: {sentence[:90]!r}"
                )
    assert checked, "no body of the wave makes a negative claim about an intro text"


def test_a_body_quotes_a_whole_intro_text_at_most_once(catalog, bodies):
    for slug in WAVE:
        text = plain(bodies[slug])
        for pid, model in WAVE_PRODUCTS.items():
            whole = recorded_intro(catalog, pid)
            if not whole:
                continue
            assert text.count(whole) <= 1, (
                f"{slug} prints {model}'s whole 紹介本文 {text.count(whole)} times"
            )


# --- finding 3: the two A01 tables scroll instead of squeezing ----------------

#: The two A01 tables that carry the scroll treatment, and their data columns.
MEASURE_TABLES = ("ks-measure-sheet-table", "ks-measure-condition-table")


def test_the_two_measure_tables_opt_out_of_the_contained_layout():
    """``readable_tables`` contains every table that does not opt out."""
    published = (PUBLISHED / f"{MEASURE}.html").read_text(encoding="utf-8")
    for table_class in MEASURE_TABLES:
        match = re.search(r"<table[^>]*" + re.escape(table_class) + r"[^>]*>", published)
        assert match, f"{table_class} is not in the published body"
        assert 'data-ks-table-layout="scroll"' in match.group(0), match.group(0)
        assert "ks-readable-table" not in match.group(0), match.group(0)


def test_the_two_measure_tables_frame_a_whole_data_cell_on_a_phone():
    """The sticky first column has to leave room for one whole data column.

    The frame is measured, not assumed: see
    ``tests/purchase_support/phone_table_frames.py``. ``table-layout:fixed`` is
    what makes the declared widths bind; without it the auto layout sizes the
    columns to their content and the rule below does nothing.
    """
    phone = phone_table_frames.phone_block(THEME_CSS.read_text(encoding="utf-8"))
    assert "table-layout:fixed!important" in phone
    for table_class in MEASURE_TABLES:
        width = re.search(
            r"table\." + re.escape(table_class) + r"\{min-width:(\d+(?:\.\d+)?)rem!important",
            phone,
        )
        first = re.search(
            r"table\."
            + re.escape(table_class)
            + r":is\(theadth:first-child,tbodyth\)\{width:(\d+(?:\.\d+)?)rem!important",
            phone,
        )
        assert width and first, (table_class, phone[-1200:])
        total, head = float(width.group(1)) * 16, float(first.group(1)) * 16
        columns = phone_table_frames.data_columns(MEASURE, table_class)
        assert columns == 3, (table_class, columns)
        for viewport, frame in sorted(phone_table_frames.ARTICLE_SCROLL_FRAME.items()):
            assert (total - head) / columns <= frame - head, (
                table_class,
                viewport,
                frame,
                total,
                head,
            )

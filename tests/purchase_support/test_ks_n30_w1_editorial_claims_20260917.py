"""next30 Wave 1 round 2 (2026-09-17): what the three dish-rack bodies may claim.

Round 1 found the wave claiming work the records do not hold, counts that do not
match the products the bodies show, official wording attributed to a product
whose page never prints it, and one figure drawn on two scales. Each of those is
a rule, and each rule is measured here against the tracked records rather than
against a copy of the sentence:

* no published body claims an editorial action -- an inquiry sent, a reply
  awaited -- unless ``purchase-support.v1.json`` records an inquiry that left the
  desk. Naming the maker's own contact window is not such a claim: it is where a
  reader goes, not something the editors did. It is still a claim about a
  maker's site, so a body may name only a window this wave's history records;
* the measuring worksheet is one number. The rows of the sheet decide it, and
  every 「Nか所」「N項目」 in the wave agrees with the row count;
* every 「N商品」 in the three bodies is recomputed from the catalog -- from the
  products the body actually shows, or from the printed 対応サイズ rows when the
  sentence is about the axis the makers print;
* a stated selection threshold accounts for every product of the wave that meets
  it: a product that clears the threshold and is not shown has to be named,
  together with the maker's own printed wording that sends it elsewhere;
* official placement wording is attributed only to the product whose page prints
  it, and a product whose page names no surface is said to name none;
* a 文字図 that draws values as bars uses one scale for the whole figure, a
  larger value never draws a shorter bar, and no line of any 文字図 is wider than
  the narrowest pre the theme renders.

The narrow width is measured, not assumed: Chromium 320px viewport, the
kurashinoshirube-child theme (theme.css + editorial-v2.css + purchase-support.css)
with the .raos-article-shell/.raos-article wrappers, gives the figure pre a
content box of 238px, a halfwidth monospace glyph of 8.664px and a fullwidth one
of 14.0px. Those three numbers are the budget below. No ``\\b`` is used next to
Japanese text.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import unicodedata

import pytest

from raos.application.editorial.reader_html import Element, fragment

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "changes/reader-purchase-support-v1/articles"
PUBLISHED = ROOT / "changes/wordpress-direct-publish-v1/articles"
CATALOG = ROOT / "changes/reader-purchase-support-v1/purchase-support.v1.json"

MEASURE = "dish-rack-installation-measurement"
SLIM = "slim-dish-rack-under-20cm"
NO_SPACE = "dish-rack-no-space"
WAVE = (MEASURE, SLIM, NO_SPACE)

#: product_id -> the model number the bodies print.
WAVE_PRODUCTS = {
    "PRD-YAMAZAKI-4314": "4314",
    "PRD-YAMAZAKI-5070": "5070",
    "PRD-SHIMOMURA-42666": "42666",
    "PRD-YAMAZAKI-7835": "7835",
    "PRD-YAMAZAKI-3492": "3492",
}

# --- rule 1: an editorial action has to be in the records --------------------

#: Sentences that tell the reader the editors already acted on a maker.
EDITORIAL_INQUIRY_CLAIM = re.compile(
    "確認を依頼|問い合わせています|問い合わせました|問い合わせ済み"
    "|照会しています|照会中|回答待ち|回答を待って|回答が届くまで|送付しました"
)
#: research_issues statuses that mean an inquiry actually left the desk.
SENT_STATES = frozenset({"SENT", "AWAITING_REPLY", "ANSWERED", "REPLIED"})

# --- rule 6: the measured narrow width ---------------------------------------

PRE_CONTENT_PX = 238.0
HALF_PX = 8.664
FULL_PX = 14.0
#: A drawn bar is a run of = fenced by |. The wave has printed the value it
#: draws on both sides of that run (「幅555mm  |=====|」 and 「W|=====| 555」), so
#: the value is read as the last number on the line outside the run itself --
#: which skips the model number a line may open with.
BAR_RUN = re.compile(r"\|(=+)\|")
BAR_VALUE = re.compile(r"[0-9]+")

#: A maker's own contact window, as both the bodies and the records print it.
CONTACT_WINDOW = re.compile(r"[a-z0-9-]+(?:\.[a-z0-9-]+)*\.co\.jp/[A-Za-z0-9/_-]+")
#: 「N商品」 as a count. A model number (4314, 42666) is never one of these.
COUNTED_PRODUCTS = re.compile(r"(?<![0-9０-９])([0-9０-９]{1,2})\s*商品(?!ページ)")
#: 「Nか所」 always counts the worksheet; 「N項目」 counts whichever table it names.
COUNTED_PLACES = re.compile(r"([0-9０-９]+)\s*(?:か所|項目)")
WORKSHEET_WORDS = ("採寸",)
UNKNOWN_WORDS = ("公式に数値がない", "公式が数値を印字していません", "未確認")
ASCII_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
#: The threshold A02 states over a printed dimension.
SHORT_SIDE_LIMIT_MM = 200


@pytest.fixture(scope="module")
def catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def bodies() -> dict[str, str]:
    return {slug: (TEMPLATES / (slug + ".html")).read_text(encoding="utf-8") for slug in WAVE}


@pytest.fixture(scope="module")
def roots(bodies: dict[str, str]) -> dict[str, Element]:
    return {slug: fragment(markup) for slug, markup in bodies.items()}


def sentences(text: str) -> list[str]:
    """One claim per sentence, and a line break ends a claim as surely as 「。」."""
    parts = re.split(r"(?<=[。？])|\n", text)
    return [part for part in parts if part and part.strip()]


def shown_products(root: Element) -> set[str]:
    """The products a body puts in front of the reader, by their bound slots."""
    found: set[str] = set()
    for node in root.walk():
        for key in ("data-product-id", "data-ps-media-product", "data-ps-purchase-product"):
            value = node.attrs.get(key)
            if isinstance(value, str) and value in WAVE_PRODUCTS:
                found.add(value)
    return found


def fact_of(catalog: dict, product_id: str, label_part: str) -> dict | None:
    for product in catalog["products"]:
        if product["product_id"] != product_id:
            continue
        for fact in product["facts"]:
            if label_part in fact["label"]:
                return fact
    return None


def short_side_mm(catalog: dict, product_id: str) -> int:
    """The 奥行 the maker prints, in mm, read off the 本体寸法 fact."""
    fact = fact_of(catalog, product_id, "本体寸法")
    assert fact is not None, f"{product_id} has no 本体寸法 fact"
    match = re.search(r"奥行([0-9]+)", fact["text"])
    assert match, f"{product_id} prints no 奥行 in {fact['text']!r}"
    return int(match.group(1))


#: The axis words a 対応サイズ row can print, longest first: 7835 prints 「奥行き」
#: where 4314 and 5070 print 「奥行」, and collapsing the two is the slip this wave
#: exists to point at, so the longer word is matched first.
AXIS_WORDS = ("奥行き", "奥行", "内寸")


def sink_axis(catalog: dict, product_id: str) -> str | None:
    """奥行き / 奥行 / 内寸 / None, read off the printed 対応サイズ row alone.

    The fact text quotes the row and then annotates it (「…「内寸」とは印字されて
    いません」), so the annotation is cut before the axis is read.
    """
    fact = fact_of(catalog, product_id, "対応するシンクの条件")
    if fact is None or fact.get("state") != "KNOWN":
        return None
    printed = re.split(r"（原文ママ|。", fact["text"])[0]
    for word in AXIS_WORDS:
        if word in printed:
            return word
    return None


def line_px(line: str) -> float:
    width = 0.0
    for char in line:
        wide = unicodedata.east_asian_width(char) in ("W", "F", "A")
        width += FULL_PX if wide else HALF_PX
    return width


def figures(root: Element) -> list[tuple[str, str]]:
    """(figcaption text, pre text) for every 文字図 of a body."""
    out = []
    for block in root.find(cls="ps-guide-diagrams"):
        for figure in block.find(tag="figure"):
            caption = figure.find(tag="figcaption")
            pre = figure.find(tag="pre")
            if pre:
                out.append((caption[0].text() if caption else "", pre[0].text()))
    return out


# --- rule 1 -------------------------------------------------------------------


def test_no_published_body_claims_an_editorial_action_the_records_do_not_hold(catalog):
    sent = [
        issue
        for issue in catalog["research_issues"]
        if issue.get("status") in SENT_STATES
    ]
    offenders: list[str] = []
    for path in sorted(PUBLISHED.glob("*.html")) + sorted(TEMPLATES.glob("*.html")):
        text = re.sub(r"<[^>]+>", "", path.read_text(encoding="utf-8"))
        for sentence in sentences(text):
            if EDITORIAL_INQUIRY_CLAIM.search(sentence):
                offenders.append(f"{path.name}: {sentence.strip()}")
    assert not offenders or sent, (
        "a body tells the reader the editors already acted on a maker, but no "
        "research issue has left the desk:\n" + "\n".join(offenders)
    )


def recorded_windows(catalog: dict) -> set[str]:
    """The maker contact windows the wave's own history entries hold."""
    found: set[str] = set()
    for article in catalog["articles"]:
        if article.get("slug") not in WAVE:
            continue
        for entry in article.get("history", []):
            found.update(CONTACT_WINDOW.findall(entry["text"]))
    return found


def test_the_wave_sends_the_reader_only_to_a_window_the_records_hold(bodies, catalog):
    """What is true instead: the maker does not print it, so the reader asks.

    Where the reader asks is itself a claim about a maker's site, so it is held
    to the same rule as every other: a body may print only a window one of this
    wave's own history entries records having been read off the maker's page.
    """
    recorded = recorded_windows(catalog)
    assert recorded, "no history entry of the wave records a maker contact window"
    for slug in WAVE:
        text = re.sub(r"<[^>]+>", "", bodies[slug])
        named = set(CONTACT_WINDOW.findall(text))
        assert named, (
            f"{slug} has to say where the reader asks the maker instead, naming "
            f"the window the maker publishes: {sorted(recorded)}"
        )
        assert named <= recorded, (
            f"{slug} sends the reader to {sorted(named - recorded)}, which no "
            "record of this wave holds"
        )


# --- rule 2 -------------------------------------------------------------------


def table_rows(root: Element, caption_part: str) -> int:
    for table in root.find(tag="table"):
        captions = table.find(tag="caption")
        if captions and caption_part in captions[0].text():
            return len([row for tbody in table.find(tag="tbody") for row in tbody.find(tag="tr")])
    raise AssertionError(f"no table captioned {caption_part}")


def test_the_worksheet_count_is_the_number_of_rows_the_sheet_has(bodies, roots):
    rows = table_rows(roots[MEASURE], "採寸シート")
    unknown = table_rows(roots[MEASURE], "公式に数値がない")
    steps = roots[MEASURE].find(tag="ol")
    listed = [len(node.find(tag="li")) for node in steps if node.attrs.get("id") == "guide-steps-list"]
    assert listed == [rows], f"the steps and the sheet are the same count: {listed} vs {rows}"
    for slug in WAVE:
        text = re.sub(r"<[^>]+>", "", bodies[slug])
        for sentence in sentences(text):
            for match in COUNTED_PLACES.finditer(sentence):
                claimed = int(match.group(1).translate(ASCII_DIGITS))
                if "か所" in match.group(0) or any(w in sentence for w in WORKSHEET_WORDS):
                    expected, which = {rows}, "the worksheet"
                elif any(w in sentence for w in UNKNOWN_WORDS):
                    expected, which = {unknown}, "the table of values nobody prints"
                else:
                    expected, which = {rows, unknown}, "one of the two tables"
                assert claimed in expected, (
                    f"{slug} says {claimed} where {which} has {sorted(expected)}: "
                    f"{sentence.strip()!r}"
                )


def test_every_product_count_is_recomputed_from_the_catalog(bodies, roots, catalog):
    # 短辺20cm以下 is A02's scope wherever the wave names it, including the link
    # labels the other two carry, so it is judged against A02's own row set.
    scoped = len(shown_products(roots[SLIM]))
    for slug in WAVE:
        shown = shown_products(roots[slug])
        clears = {
            pid
            for pid in WAVE_PRODUCTS
            if short_side_mm(catalog, pid) <= SHORT_SIDE_LIMIT_MM
        }
        text = re.sub(r"<[^>]+>", "", bodies[slug])
        for sentence in sentences(text):
            for match in COUNTED_PRODUCTS.finditer(sentence):
                claimed = int(match.group(1).translate(ASCII_DIGITS))
                if "奥行" in sentence and "内寸" in sentence:
                    # Such a sentence counts one axis word at a time, and the
                    # words are not interchangeable: 7835 prints 「奥行き」 where
                    # 4314 and 5070 print 「奥行」. Which word a given count goes
                    # with is pinned by the round-6 attribution rule; here the
                    # count only has to be one the printed rows support.
                    allowed = {
                        len({pid for pid in shown if sink_axis(catalog, pid) == word})
                        for word in AXIS_WORDS
                        if word in sentence
                    }
                    why = "the products printing an axis word the sentence names"
                elif "短辺" in sentence and "20cm" in sentence:
                    # A threshold sentence counts either the products that clear
                    # it or the ones compared here; which products are dropped is
                    # the accounting test below.
                    allowed = {scoped, len(clears)}
                    why = "the products that clear 短辺20cm以下, or the ones A02 compares"
                else:
                    allowed = {len(shown)}
                    why = "the products the body shows"
                assert claimed in allowed, (
                    f"{slug} says {claimed}商品 where {why} is "
                    f"{sorted(allowed)}: {sentence.strip()!r}"
                )


def test_the_short_side_threshold_accounts_for_every_product_of_the_wave(bodies, roots, catalog):
    """A02 states 短辺20cm以下. 3492 prints 195mm, so it clears the threshold."""
    clears = {
        pid for pid in WAVE_PRODUCTS if short_side_mm(catalog, pid) <= SHORT_SIDE_LIMIT_MM
    }
    shown = shown_products(roots[SLIM])
    text = re.sub(r"<[^>]+>", "", bodies[SLIM])
    assert "短辺20cm以下" in text or "短辺（奥行）20cm以下" in text
    for pid in sorted(clears - shown):
        model = WAVE_PRODUCTS[pid]
        assert model in text, (
            f"{model} prints 奥行{short_side_mm(catalog, pid)}mm and clears the stated "
            "threshold, so the body has to name it and say why it is elsewhere"
        )
        placement = fact_of(catalog, pid, "置き方")
        assert placement is not None
        quoted = [
            piece
            for piece in re.findall(r"「([^」]+)」", placement["text"])
            if piece in text
        ]
        assert quoted, (
            f"the reason {model} is not shown has to be the maker's own printed "
            f"wording, quoted from {placement['locator']!r}"
        )


# --- rule 5 -------------------------------------------------------------------


def printed_text(catalog: dict, product_id: str) -> str:
    for product in catalog["products"]:
        if product["product_id"] == product_id:
            return "".join(fact["text"] for fact in product["facts"])
    return ""


def condition_cards(root: Element) -> list[tuple[set[str], str]]:
    """(products the group is bound to, the prose the editors wrote for it)."""
    cards = []
    for grid in root.find(cls="ps-condition-grid"):
        for card in grid.children:
            if not isinstance(card, Element) or card.tag != "div":
                continue
            bound = {
                str(node.attrs.get("data-ps-media-product"))
                for node in card.walk()
                if node.attrs.get("data-ps-media-product")
            }
            prose = "".join(
                child.text()
                for child in card.children
                if isinstance(child, Element) and not child.has("ps-condition-item")
            )
            if bound:
                cards.append((bound, prose))
    return cards


#: The body saying a maker prints no such wording at all.
ABSENT_WORDING = re.compile(
    "書かれていません|名指ししていません|印字していません|印字されていません"
    "|記載はありません|語が無い|ありません"
)


def official_quotes(prose: str, catalog: dict) -> dict[str, set[str]]:
    """Quoted phrase -> the wave products whose own page prints it."""
    quotes = {}
    for piece in re.findall(r"「([^」]+)」", prose):
        if len(piece) < 6:
            continue
        quotes[piece] = {
            pid for pid in WAVE_PRODUCTS if piece in printed_text(catalog, pid)
        }
    return quotes


def test_a_placement_group_quotes_only_what_its_own_products_print(roots, catalog):
    """Official wording belongs to the page that prints it, not to a group.

    A group that quotes official wording and then counts products hands that
    wording to every product it counts, so the count is checked against the
    products of the group whose own page prints one of the quoted phrases -- not
    against the size of the group.
    """
    cards = condition_cards(roots[NO_SPACE])
    assert len(cards) == 3, f"A03 sorts the wave into three methods, got {len(cards)}"
    for bound, prose in cards:
        quotes = official_quotes(prose, catalog)
        for piece, holders in quotes.items():
            assert holders, f"「{piece}」 is quoted as official wording no maker page prints"
            assert holders & bound, (
                f"「{piece}」 is printed by {sorted(WAVE_PRODUCTS[h] for h in holders)}, "
                f"none of which is in this group ({sorted(WAVE_PRODUCTS[b] for b in bound)})"
            )
        printers = {pid for holders in quotes.values() for pid in holders}
        for match in COUNTED_PRODUCTS.finditer(prose):
            claimed = int(match.group(1).translate(ASCII_DIGITS))
            assert claimed == len(printers & bound), (
                f"this group quotes official wording and then counts {claimed}商品, "
                f"but only {sorted(WAVE_PRODUCTS[p] for p in printers & bound)} of "
                f"{sorted(WAVE_PRODUCTS[b] for b in bound)} print any of it: "
                f"{prose[:80]!r}"
            )
        for pid, model in WAVE_PRODUCTS.items():
            if model not in prose:
                continue
            assert pid in bound, (
                f"{model} is discussed in a group it is not placed in: {prose[:60]!r}"
            )
            if not quotes:
                continue
            assert pid in printers or ABSENT_WORDING.search(prose), (
                f"{model} is named beside official wording it does not print, and "
                f"the group never says its page prints none: {prose[:80]!r}"
            )


def test_the_wave_says_when_a_maker_names_no_placement_surface(bodies, catalog):
    printed = printed_text(catalog, "PRD-YAMAZAKI-5070")
    assert "シンク横" not in printed and "シンク脇" not in printed
    text = re.sub(r"<[^>]+>", "", bodies[NO_SPACE])
    assert re.search("5070[^。]*(?:書かれていません|名指ししていません|印字されていません)", text), (
        "5070's page names no surface, so the body has to say so"
    )
    # and 5070 prints a sink-spanning condition, so it sits in that group too.
    condition = fact_of(catalog, "PRD-YAMAZAKI-5070", "対応するシンクの条件")
    assert condition is not None and "シンク渡し使用時" in condition["text"]
    assert "シンク渡し使用時" in text


# --- rule 6 -------------------------------------------------------------------


def test_a_text_figure_fits_the_narrowest_pre_the_theme_renders(roots):
    for slug in WAVE:
        for caption, drawing in figures(roots[slug]):
            for line in drawing.split("\n"):
                assert line_px(line) <= PRE_CONTENT_PX, (
                    f"{slug} {caption[:12]!r}: {line!r} is {line_px(line):.1f}px wide, "
                    f"over the {PRE_CONTENT_PX}px the 320px viewport gives the pre"
                )


def test_a_ruled_line_carries_no_fullwidth_glyph(roots):
    """A monospace fullwidth glyph is 14.0px against 8.664px: 1.616, not 2."""
    for slug in WAVE:
        for caption, drawing in figures(roots[slug]):
            for line in drawing.split("\n"):
                if "+" not in line and "|" not in line:
                    continue
                wide = [c for c in line if unicodedata.east_asian_width(c) in ("W", "F", "A")]
                assert not wide, (
                    f"{slug} {caption[:12]!r}: a ruled line cannot align around "
                    f"{wide!r}: {line!r}"
                )


def drawn_bars(drawing: str) -> list[tuple[int, int]]:
    """(value in mm, glyphs drawn) for every bar of a 文字図."""
    out: list[tuple[int, int]] = []
    for line in drawing.split("\n"):
        run = BAR_RUN.search(line)
        if not run:
            continue
        rest = line[: run.start()] + line[run.end() :]
        numbers = BAR_VALUE.findall(rest)
        assert numbers, f"a bar draws a value its line never prints: {line!r}"
        out.append((int(numbers[-1]), len(run.group(1))))
    return out


def test_a_bar_figure_draws_every_value_on_one_scale(roots):
    for slug in WAVE:
        for caption, drawing in figures(roots[slug]):
            bars = drawn_bars(drawing)
            if not bars:
                continue
            assert len(bars) >= 2
            scales = {value / glyphs for value, glyphs in bars}
            assert max(scales) / min(scales) <= 1.35, (
                f"{slug} {caption[:12]!r} draws {len(bars)} bars on scales "
                f"{sorted(round(s, 1) for s in scales)}: one figure, one scale"
            )
            for (small, short), (large, long) in zip(sorted(bars), sorted(bars)[1:]):
                assert short <= long, (
                    f"{slug} {caption[:12]!r}: {large}mm draws shorter ({long}) "
                    f"than {small}mm ({short})"
                )

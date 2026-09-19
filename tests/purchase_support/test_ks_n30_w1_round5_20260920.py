"""next30 Wave 1 round 5 (2026-09-20): the record holds what the wave ships.

Round 4 left three things settled only in a report, and a report is not a record:

* **The title an article ships is the title the record holds.** A02 ships
  「短辺20cm以下のすき間に据え置く水切りラック3商品を比べる」 while
  ``changes/next30-20260916/decisions.v1.json`` still carried the 2026-09-16
  wording 「短辺20cm以下の水切りラック3商品を比べる」. The narrower title is the
  one the body supports -- its criterion is 短辺20cm以下 かつ すき間の面に据え置く,
  which is why 3492 is named and set aside on the maker's own
  「シンクのフチに引っ掛けるので、浮かせて設置できます」 -- so the record is the stale
  side and has to carry the shipped title, the criterion and the wording it
  replaces. The same rule is applied to every shipped article and to the excerpt,
  because a title nobody approved and an excerpt nobody approved are the same
  problem.
* **A quotation quotes the maker's own word.** 7835's 対応サイズ row prints
  「奥行き：54cm以下のシンク」 while 4314 and 5070 print 「奥行」. In an article whose
  thesis is that the makers' printed axis words differ, a sentence that names
  7835 and quotes 「奥行」 for it is the slip the article warns against.
* **Reader-facing prose is written for a reader.** A03's second 2026-09-19 entry
  printed a CSS selector and put 表C in the past tense for a quotation 表C still
  carries. The element name belongs in the record, and the past tense belongs to
  the excerpt that dropped the sentence, not to the table that still quotes it.

The publication prerequisites are recorded the same way: a measurement with the
date it was taken, not a sentence saying somebody once looked.

Re-fetched 2026-09-20 before quoting: https://www.yamajitsu.co.jp/products/241440
(「奥行50cm以内のシンク　厚み1.8cmのまな板」), /241827 (「厚み2cmまでのまな板・奥行50cm
以内のシンク（シンク渡し使用時）」 and the 7-sentence 紹介本文), /242645
(「奥行き：54cm以下のシンク」), /241233 (「シンク内寸37cm〜47cm」) and
https://www.simomura-kihan.co.jp/products/category/detail---id-289.html (no
対応サイズ row at all). No ``\\b`` is used next to Japanese text.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

from raos.application.editorial.reader_html import Element, fragment

ROOT = Path(__file__).resolve().parents[2]
DECISIONS = ROOT / "changes/next30-20260916/decisions.v1.json"
LEDGER = ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json"
CATALOG = ROOT / "changes/reader-purchase-support-v1/purchase-support.v1.json"
PUBLISHED = ROOT / "changes/wordpress-direct-publish-v1/articles"

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
#: The axis words a 対応サイズ row can print, longest first so 奥行き wins over 奥行.
AXIS_WORDS = ("奥行き", "奥行", "内寸")
#: A sentence that attributes a printed condition rather than naming a table row.
CONDITION_CLAIM = re.compile(r"条件|印字")
#: A word in either quotation style the bodies use.
QUOTED = re.compile(r"[「『]([^」』]+)[」』]")
#: An element name written as CSS. The element list keeps 「yamajitsu.co.jp」 and
#: the other hostnames out; no ``\b`` is used, because a kanji counts as a word
#: character in Python's Unicode ``re`` and would hide a match at the boundary.
CSS_SELECTOR = re.compile(
    r"(?:^|[^A-Za-z0-9_.-])"
    r"(?:div|span|section|article|table|thead|tbody|tr|td|th|ul|ol|li|dl|dt|dd"
    r"|p|a|h[1-6]|figure|figcaption|img|summary|details)"
    r"\.[A-Za-z_][A-Za-z0-9_-]*"
)
#: The 5070 sentence 表C quotes; the round-4 entry says the excerpts dropped it.
TAIL_SENTENCE = (
    "トレーの水はけは可動式なので排水方向を変えることができ、"
    "止水栓付きなので水が流せない場所にも設置できます。"
)
ELEMENT_IN_RECORD = "div.s-main-product__intro-text"


@pytest.fixture(scope="module")
def decisions() -> dict:
    return json.loads(DECISIONS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ledger() -> dict[str, dict]:
    rows = json.loads(LEDGER.read_text(encoding="utf-8"))["articles"]
    return {row["slug"]: row for row in rows}


@pytest.fixture(scope="module")
def catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def bodies() -> dict[str, str]:
    return {
        slug: (PUBLISHED / (slug + ".html")).read_text(encoding="utf-8")
        for slug in WAVE
    }


@pytest.fixture(scope="module")
def roots(bodies: dict[str, str]) -> dict[str, Element]:
    return {slug: fragment(text) for slug, text in bodies.items()}


def shipped(decisions: dict, ledger: dict[str, dict]) -> list[dict]:
    """The recorded articles that already have a row in the publication ledger."""

    rows = [row for row in decisions["articles"] if row["slug"] in ledger]
    assert [row["article_id"] for row in rows] == ["A01", "A02", "A03"], rows
    return rows


def article_of(catalog: dict, slug: str) -> dict:
    for article in catalog["articles"]:
        if article["slug"] == slug:
            return article
    raise AssertionError(f"{slug} is not in the catalog")


def facts_of(catalog: dict, product_id: str) -> list[dict]:
    for product in catalog["products"]:
        if product["product_id"] == product_id:
            return product["facts"]
    return []


def printed_axis(catalog: dict, product_id: str) -> str | None:
    """The axis word this maker prints in its 対応サイズ row, or None."""

    for fact in facts_of(catalog, product_id):
        if "対応" in fact["label"] or "対応サイズ" in fact["text"]:
            for word in AXIS_WORDS:
                if word in fact["text"]:
                    return word
    return None


def sentences(text: str) -> list[str]:
    return [piece for piece in re.split(r"(?<=。)", text) if piece.strip()]


def visible_text(markup: str) -> str:
    return re.sub(r"<[^>]+>", "", markup)


def test_every_shipped_article_ships_the_title_the_record_holds(
    decisions: dict, ledger: dict[str, dict], catalog: dict
) -> None:
    for row in shipped(decisions, ledger):
        slug = row["slug"]
        assert ledger[slug]["title"] == row["title"], (
            f"{row['article_id']} ships {ledger[slug]['title']!r}; the record "
            f"holds {row['title']!r}"
        )
        assert article_of(catalog, slug)["title"] == row["title"], (
            f"{row['article_id']}: the catalog title and the record disagree"
        )


def test_every_shipped_article_ships_the_excerpt_the_record_holds(
    decisions: dict, ledger: dict[str, dict]
) -> None:
    for row in shipped(decisions, ledger):
        recorded = row.get("excerpt")
        assert recorded, f"{row['article_id']}: the record holds no excerpt"
        assert ledger[row["slug"]]["excerpt"] == recorded, (
            f"{row['article_id']} ships an excerpt the record does not hold"
        )


def test_a_changed_title_keeps_the_wording_it_replaced_and_says_why(
    decisions: dict, ledger: dict[str, dict], bodies: dict[str, str]
) -> None:
    """A02 is the one shipped title that is not the 2026-09-16 wording."""

    changed = [row for row in shipped(decisions, ledger) if "title_history" in row]
    assert [row["article_id"] for row in changed] == ["A02"], changed
    history = changed[0]["title_history"]
    assert [entry["recorded_on"] for entry in history] == ["2026-09-16", "2026-09-20"]
    assert history[0]["title"] == "短辺20cm以下の水切りラック3商品を比べる"
    assert history[-1]["title"] == changed[0]["title"]
    reason = history[-1]["reason"]
    for criterion in ("短辺20cm以下", "すき間"):
        assert criterion in reason, (criterion, reason)
    # The reason names the body's criterion, so the body has to apply it.
    text = visible_text(bodies[SLIM])
    assert "短辺20cm以下" in text
    assert "シンクのフチに引っ掛けるので、浮かせて設置できます" in text


def test_the_condition_table_quotes_each_makers_own_axis_word(
    catalog: dict, bodies: dict[str, str]
) -> None:
    axes = {
        model: printed_axis(catalog, product_id)
        for product_id, model in WAVE_PRODUCTS.items()
    }
    assert axes == {
        "4314": "奥行",
        "5070": "奥行",
        "42666": None,
        "7835": "奥行き",
        "3492": "内寸",
    }, axes
    for sentence in sentences(visible_text(bodies[MEASURE])):
        quoted = set(QUOTED.findall(sentence))
        if not quoted & set(AXIS_WORDS) or not CONDITION_CLAIM.search(sentence):
            # 「「内寸」行」 in the source list names a row of the maker's spec
            # table, not the axis a product is judged on; only a sentence about
            # the printed 条件 attributes an axis word to a 型番.
            continue
        for model, word in axes.items():
            if word is None or model not in sentence:
                continue
            assert word in quoted, (
                f"{model} prints 「{word}」 in its 対応サイズ row; this sentence "
                f"quotes {sorted(quoted & set(AXIS_WORDS))} for it: "
                f"{sentence.strip()!r}"
            )
        if "表2" in sentence and "奥行" in quoted:
            assert "奥行き" in quoted, (
                "表2 carries 7835, whose row prints 「奥行き」, so a sentence that "
                "sends the reader to 表2 for 「奥行」 names both: "
                f"{sentence.strip()!r}"
            )


def test_no_reader_facing_text_of_the_wave_prints_a_css_selector(
    catalog: dict, bodies: dict[str, str], decisions: dict
) -> None:
    for slug in WAVE:
        found = CSS_SELECTOR.findall(visible_text(bodies[slug]))
        assert found == [], (slug, found)
        for entry in article_of(catalog, slug).get("history", []):
            assert CSS_SELECTOR.findall(entry["text"]) == [], (
                f"{slug} {entry['date']}: the entry prints a CSS selector "
                "where a reader needs 商品ページ冒頭の紹介本文"
            )
    # The element name is evidence, so it stays -- in the record only.
    recorded = json.dumps(decisions, ensure_ascii=False)
    assert ELEMENT_IN_RECORD in recorded, (
        "the record no longer says which element the 紹介本文 was read from"
    )


def test_the_history_does_not_put_a_live_quotation_in_the_past(
    catalog: dict, bodies: dict[str, str]
) -> None:
    body = visible_text(bodies[NO_SPACE])
    assert TAIL_SENTENCE.strip("「」") in body
    entries = [
        entry
        for entry in article_of(catalog, NO_SPACE).get("history", [])
        if "表C" in entry["text"]
    ]
    assert entries, "no history entry names 表C"
    for entry in entries:
        assert re.search(r"表C[^。]*引いていた", entry["text"]) is None, (
            f"{entry['date']}: the entry puts 表C in the past while 表C still "
            "carries the quotation"
        )
        assert re.search(
            r"表C[^。]*(?:引いており|変えていない|いまも)", entry["text"]
        ), (
            f"{entry['date']}: the entry names 表C without saying the quotation "
            "is still there"
        )


def test_the_record_carries_the_measured_publication_prerequisites(
    decisions: dict,
) -> None:
    prerequisites = decisions["publication_prerequisites"]
    items = {item["id"]: item for item in prerequisites["items"]}
    assert set(items) == {"allow_new_posts", "approved_layout_baselines"}, sorted(items)

    allow = items["allow_new_posts"]
    assert allow["state"] == "MEASURED", allow
    assert type(allow["value"]) is bool, allow
    assert allow["measured_on"] == "2026-09-20", allow
    assert "status" in allow["measurement"]["command"], allow
    assert allow["measurement"]["profile"] == "owner-direct-v1", allow

    baselines = items["approved_layout_baselines"]
    assert baselines["state"] == "OPEN", baselines
    assert any("Before/After" in entry for entry in decisions["unresolved"]), (
        "the owner's Before/After sign-off dropped out of 未解決"
    )

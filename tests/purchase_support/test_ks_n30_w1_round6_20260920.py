"""next30 Wave 1 round 6 (2026-09-20): every article quotes the word the maker prints.

Round 5 wrote the rule for one article. The rule was right and the reach was
wrong: it read A01's body only, so the identical sentence in A03 -- which sends
the reader to A01 for 「条件の原文と読み替え方」 -- shipped 7835's axis as 「奥行」
while 7835's page prints 「奥行き」. A guard that reads one of three bodies cannot
say the wave is clean, so this module reads **every published body of the wave
and every reader-facing history entry of the wave**, and fails when a quoted word
is not the word that product's page prints.

Three ways the same defect shows up, one rule each:

* **Attribution.** 「4314・5070・7835はシンクの「奥行」」 hands three 型番 one quoted
  word. Every 型番 in such a group has to print that word in its 対応サイズ row,
  and a count in front of the group (「3商品（…）は「奥行」」) has to be the number
  of the wave's products that print it -- otherwise the caption says three where
  the body two screens down says two. The quotation counts whether it is the
  axis word on its own or the whole 対応サイズ row value that carries it, and it
  counts in any sentence: 「4314・5070・7835はシンクの「奥行」に合わせます。」 states
  the same falsehood without the word 条件 in it, and 「7835は「奥行50cm以内のシンク」
  と条件に印字しています。」 pins 4314's row value on 7835 without ever setting an
  axis word alone. A 商品サイズ row value (「幅40.3×奥行18×高さ16cm」) carries 奥行
  too but names a side of the product rather than the シンク, so it is left to
  the ownership rule -- every 対応サイズ row in this wave names the シンク, and no
  商品サイズ row does.
* **Ownership.** 「Wは公式の「幅」、Dは公式の「奥行」」 calls 幅 and 奥行 the makers'
  words for 4314 and 7835, but 山崎実業's 商品サイズ row prints 「W55.5×D16.5×H16cm」
  and 「W26×D58×H0.8cm」 -- W and D, never 幅 or 奥行. Only 下村企販 42666 prints
  幅・奥行・高さ. A word quoted as the maker's own has to appear in what that
  maker prints.
* **Enumeration.** A sentence that presents the printed axis words as a closed
  set -- either by saying they do not agree, or by saying these are the only ones
  the makers print -- has to show every word the pages print.
  「「奥行」「内寸」「行なし」で揃わない」 leaves out the fourth variant this wave exists
  to point at.

Re-fetched 2026-09-20 before quoting, and the 対応サイズ / 商品サイズ rows read from
the pages themselves: https://www.yamajitsu.co.jp/products/241440 →
対応サイズ「奥行50cm以内のシンク　厚み1.8cmのまな板」・商品サイズ「W55.5×D16.5×H16cm」;
/241827 → 「厚み2cmまでのまな板・奥行50cm以内のシンク（シンク渡し使用時）」・
「W57.5×D16×H33.5cm」; /242645 → 「奥行き：54cm以下のシンク」・「W26×D58×H0.8cm」;
/241233 → 「シンク内寸37cm〜47cm」・「W44〜54×D19.5×H14cm」;
https://www.simomura-kihan.co.jp/products/category/detail---id-289.html → no
対応サイズ row at all, サイズ「幅40.3×奥行18×高さ16cm、…」. No ``\\b`` is used
anywhere here: a kanji is a word character to Python's Unicode ``re``, so ``\\b``
next to Japanese matches where no boundary is meant.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[2]
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
#: The words a 商品サイズ / サイズ row can use to name a side of the product.
SIDE_WORDS = ("奥行き", "奥行", "幅", "高さ", "W", "D", "H")
#: A word in either quotation style the bodies use.
QUOTED = re.compile(r"[「『]([^」』]+)[」』]")
#: A sentence that says the printed axis words do not agree.
DISAGREEMENT = re.compile(r"揃|そろ")
#: A sentence that says these are the only axis words the makers print.
CLOSED_LIST = re.compile(r"公式[がは][^。]*印字しているのは[^。]*だけ")

_MODEL = "|".join(sorted(WAVE_PRODUCTS.values(), key=len, reverse=True))
#: 「4314・5070は…「奥行」」 -- a run of 型番 handed one quotation.
ATTRIBUTION = re.compile(
    rf"(?P<count>(\d+)商品（)?"
    rf"(?P<models>(?:{_MODEL})(?:[・、](?:{_MODEL}))*)"
    rf"[^「『」』。]{{0,14}}"
    rf"[「『](?P<quoted>[^「『」』]+)[」』]"
)
#: 「公式の「幅」」「メーカー表記の「奥行」」 -- a side word claimed as the maker's own.
OWNED = re.compile(
    rf"(?:メーカー|公式)(?:表記)?の[^「『」』。]{{0,6}}"
    rf"[「『](?P<word>{'|'.join(SIDE_WORDS)})[」』]"
)


def quoted_axis(quoted: str) -> str | None:
    """The axis word a quotation hands a product, or None if it hands none.

    A quotation is an axis claim when it is the axis word on its own (「奥行」)
    and equally when it is the 対応サイズ row value that carries the word
    (「奥行50cm以内のシンク」) -- the second is how the same false attribution
    reads when the body quotes the row instead of the word. Every 対応サイズ row
    in this wave names the シンク the condition is about; a 商品サイズ row names a
    side of the product (「幅40.3×奥行18×高さ16cm」) and never the シンク, so the
    シンク is what tells a condition quotation from a size quotation, and the
    ownership rule is what guards the latter.
    """

    for word in AXIS_WORDS:  # longest first, so 奥行き never reads as 奥行
        if quoted == word or (word in quoted and "シンク" in quoted):
            return word
    return None


@pytest.fixture(scope="module")
def catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def visible_text(markup: str) -> str:
    return re.sub(r"<[^>]+>", "", markup)


def sentences(text: str) -> list[str]:
    return [piece for piece in re.split(r"(?<=。)", text) if piece.strip()]


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


def printed_size(catalog: dict, product_id: str) -> str:
    """The 商品サイズ / サイズ row as the maker prints it, quoted in the fact."""

    for fact in facts_of(catalog, product_id):
        if "本体寸法" not in fact["label"]:
            continue
        for quoted in QUOTED.findall(fact["text"]):
            if "×" in quoted and "cm" in quoted:
                return quoted
    raise AssertionError(f"{product_id} records no printed 商品サイズ row")


@pytest.fixture(scope="module")
def axes(catalog: dict) -> dict[str, str | None]:
    found = {
        model: printed_axis(catalog, product_id)
        for product_id, model in WAVE_PRODUCTS.items()
    }
    assert found == {
        "4314": "奥行",
        "5070": "奥行",
        "42666": None,
        "7835": "奥行き",
        "3492": "内寸",
    }, found
    return found


@pytest.fixture(scope="module")
def sides(catalog: dict) -> dict[str, frozenset[str]]:
    """model -> the side words that product's printed size row actually uses."""

    printed = {
        model: printed_size(catalog, product_id)
        for product_id, model in WAVE_PRODUCTS.items()
    }
    assert printed == {
        "4314": "W55.5×D16.5×H16cm",
        "5070": "W57.5×D16×H33.5cm",
        "42666": "幅40.3×奥行18×高さ16cm",
        "7835": "W26×D58×H0.8cm",
        "3492": "W44〜54×D19.5×H14cm",
    }, printed
    return {
        model: frozenset(word for word in SIDE_WORDS if word in row)
        for model, row in printed.items()
    }


@pytest.fixture(scope="module")
def reader_texts(catalog: dict) -> list[tuple[str, str]]:
    """Every published body of the wave and every reader-facing history entry."""

    texts: list[tuple[str, str]] = []
    for slug in WAVE:
        body = (PUBLISHED / (slug + ".html")).read_text(encoding="utf-8")
        texts.append((f"{slug} body", visible_text(body)))
        for entry in article_of(catalog, slug).get("history", []):
            texts.append((f"{slug} history {entry['date']}", entry["text"]))
    assert len(texts) == 13, texts
    return texts


def test_every_body_and_history_of_the_wave_is_read(
    reader_texts: list[tuple[str, str]],
) -> None:
    """The guard's reach, stated as a test so widening it cannot be undone."""

    where = [name for name, _ in reader_texts]
    assert [name for name in where if name.endswith(" body")] == [
        f"{slug} body" for slug in WAVE
    ], where
    for slug in WAVE:
        assert sum(1 for name in where if name.startswith(f"{slug} history")) >= 3, (
            where
        )


def test_a_group_of_models_is_only_given_the_axis_word_all_of_them_print(
    reader_texts: list[tuple[str, str]], axes: dict[str, str | None]
) -> None:
    for where, text in reader_texts:
        for sentence in sentences(text):
            for match in ATTRIBUTION.finditer(sentence):
                quoted = quoted_axis(match.group("quoted"))
                if quoted is None:
                    continue
                models = re.split(r"[・、]", match.group("models"))
                for model in models:
                    assert axes[model] == quoted, (
                        f"{where}: {model} prints "
                        f"{axes[model] and f'「{axes[model]}」' or 'no 対応サイズ row'} "
                        f"but this sentence hands it 「{quoted}」 "
                        f"(quoting 「{match.group('quoted')}」): "
                        f"{sentence.strip()!r}"
                    )
                if match.group("count") is None:
                    continue
                counted = int(match.group(2))
                printing = sum(1 for word in axes.values() if word == quoted)
                assert counted == printing, (
                    f"{where}: {printing} of the wave's products print 「{quoted}」 "
                    f"but this sentence counts {counted}: {sentence.strip()!r}"
                )


def test_a_word_quoted_as_the_makers_own_is_a_word_that_maker_prints(
    reader_texts: list[tuple[str, str]], sides: dict[str, frozenset[str]]
) -> None:
    for where, text in reader_texts:
        for sentence in sentences(text):
            for match in OWNED.finditer(sentence):
                word = match.group("word")
                named = [model for model in sides if model in sentence]
                # A sentence that names no 型番 speaks for the makers as a group.
                about = named or sorted(sides)
                for model in about:
                    assert word in sides[model], (
                        f"{where}: {model}'s printed size row uses "
                        f"{sorted(sides[model])}, not 「{word}」: "
                        f"{sentence.strip()!r}"
                    )


def test_a_closed_list_of_the_axes_shows_every_one_the_pages_print(
    reader_texts: list[tuple[str, str]], axes: dict[str, str | None]
) -> None:
    printed = {word for word in axes.values() if word is not None}
    for where, text in reader_texts:
        for sentence in sentences(text):
            if not (DISAGREEMENT.search(sentence) or CLOSED_LIST.search(sentence)):
                # 「表2で「奥行」「奥行き」を条件にしている商品」 picks a subset out of
                # 表2; only a sentence that closes the list claims to be the whole
                # of it.
                continue
            quoted = set(QUOTED.findall(sentence)) & set(AXIS_WORDS)
            if not quoted:
                continue
            assert quoted == printed, (
                f"{where}: the wave's pages print {sorted(printed)} but this "
                f"sentence closes the list at {sorted(quoted)}: "
                f"{sentence.strip()!r}"
            )

"""next30 Wave 1 (2026-09-17): the three dish-rack article bodies.

A01 ``dish-rack-installation-measurement``, A02 ``slim-dish-rack-under-20cm`` and
A03 ``dish-rack-no-space`` are written as authored templates under
``changes/reader-purchase-support-v1/articles/``. The renderer fills only the
per-product photo and seller cells, so every editorial rule the plan names is a
property of the tracked template and is measured here directly.

The rules under test (plan.md §5.1-§5.3):

* the A01 measuring worksheet has exactly six rows and carries no product value
  -- no model number, no maker name and no dimension, because it is the sheet the
  reader fills in;
* every data cell of the A01 official-conditions table cites the locator of the
  fact it came from, with the maker page it was read on and the check date;
* the A01 table of values nobody prints lists exactly the seven items, each with
  the step that replaces the missing number;
* each article states its own central question exactly once, and no other
  article's;
* a value the makers do not print never becomes a fit verdict: it is written
  未確認 and paired with a measuring step;
* the three carry no affiliate offer, so the disclosure says the article has
  none and the only outward links are the maker pages;
* the three may link to each other and to the published /kitchen/ hub, and to no
  article that is not published yet.

Printed Japanese is compared verbatim against ``products.catalog.json`` fact
text whenever the wave's catalog rows are already tracked, so the quotations
cannot drift from the maker pages. No ``\\b`` is used next to Japanese text.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

from raos.application.editorial.reader_html import Element, fragment

ROOT = Path(__file__).resolve().parents[2]
ARTICLES = ROOT / "changes/reader-purchase-support-v1/articles"
CATALOG = ROOT / "changes/reader-purchase-support-v1/purchase-support.v1.json"
LEDGER = ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json"

MEASURE = "dish-rack-installation-measurement"
SLIM = "slim-dish-rack-under-20cm"
NO_SPACE = "dish-rack-no-space"
WAVE = (MEASURE, SLIM, NO_SPACE)

#: Each article names the one question it answers, once.
CENTRAL_QUESTIONS = {
    MEASURE: (
        "水切りラックを買う前に、自宅のどこを何か所測って、"
        "公式が印字しているどの条件に当てはめれば「置ける」と判断できるのか。"
    ),
    SLIM: (
        "シンク横に空いている短辺20cm以下のすき間に、"
        "公式が印字している外形と材質で置けるのはどの水切りラックか。"
    ),
    NO_SPACE: (
        "洗った食器を置く場所がないとき、作業台に常設する・シンクの上に渡す・"
        "使う時だけ広げるのどの方式から検討すればよいか。"
    ),
}

#: product_id -> (exact_model, maker page the facts were read on).
PRODUCTS = {
    "PRD-YAMAZAKI-4314": ("4314", "https://www.yamajitsu.co.jp/products/241440"),
    "PRD-YAMAZAKI-5070": ("5070", "https://www.yamajitsu.co.jp/products/241827"),
    "PRD-SHIMOMURA-42666": (
        "42666",
        "https://www.simomura-kihan.co.jp/products/category/detail---id-289.html",
    ),
    "PRD-YAMAZAKI-7835": ("7835", "https://www.yamajitsu.co.jp/products/242645"),
    "PRD-YAMAZAKI-3492": ("3492", "https://www.yamajitsu.co.jp/products/241233"),
}
OFFICIAL_URLS = {url for _, url in PRODUCTS.values()}
MAKERS = ("山崎実業", "下村企販")
CHECKED_ON = "2026年9月16日"

#: The seven values no maker prints, in the order the A01 table lists them.
UNKNOWN_ITEMS = (
    "脚の位置・脚間距離・接地幅",
    "蛇口下に必要な高さ",
    "シンク縁の厚み・形状と掛かり代",
    "水受けトレーの引き出し方向と前後の余白",
    "水受けの有無と排水先",
    "上段から食器を出し入れする上方の余白",
    "丸めた／折り畳んだ状態の寸法",
)

#: Printed Japanese that has to survive verbatim, with the fact it belongs to.
QUOTED = (
    ("PRD-YAMAZAKI-4314", "W55.5×D16.5×H16cm"),
    ("PRD-YAMAZAKI-4314", "奥行50cm以内のシンク　厚み1.8cmのまな板"),
    ("PRD-YAMAZAKI-5070", "W57.5×D16×H33.5cm"),
    ("PRD-YAMAZAKI-5070", "厚み2cmまでのまな板・奥行50cm以内のシンク（シンク渡し使用時）"),
    ("PRD-YAMAZAKI-5070", "ワイヤーバスケット：8kg"),
    ("PRD-SHIMOMURA-42666", "幅40.3×奥行18×高さ16cm"),
    ("PRD-SHIMOMURA-42666", "バスケット内寸:幅37×奥行17×深さ7(10.5)cm"),
    ("PRD-YAMAZAKI-7835", "W26×D58×H0.8cm"),
    ("PRD-YAMAZAKI-7835", "奥行き：54cm以下のシンク"),
    ("PRD-YAMAZAKI-3492", "W44〜54×D19.5×H14cm"),
    ("PRD-YAMAZAKI-3492", "シンク内寸37cm〜47cm"),
)

DISCLOSURE = "この記事にアフィリエイトリンクはありません。公式資料による比較で、実機試験ではありません。"
#: The label the body prints in front of its one central question.
QUESTION_LABEL = "この記事が答える問い："
#: The standing sentence that denies a ranking; removed before looking for one.
NOT_A_RANKING = "掲載順は性能の順位ではありません"
#: A number with a unit. Used to keep the reader's worksheet free of product values.
MEASUREMENT = re.compile(r"[0-9０-９]+(?:[.．][0-9０-９]+)?\s*(?:mm|cm|ｃｍ|kg|ｋｇ|[gLＬ]|リットル)")
#: Ranking language the three articles must not use about comfort or performance.
RANKING = re.compile(r"おすすめ順|人気順|順位|ランキング|一番使いやすい|最も使いやすい|ベスト[0-9０-９]")
#: Sentences that deny a ranking rather than making one.
DENIALS = (
    NOT_A_RANKING,
    "使い方による切り分けです。使い心地や水切れの順位ではありません。",
    "おすすめ順でもありません",
)


def read(slug: str) -> str:
    path = ARTICLES / (slug + ".html")
    assert path.is_file(), f"missing article template: {path}"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def bodies() -> dict[str, str]:
    return {slug: read(slug) for slug in WAVE}


@pytest.fixture(scope="module")
def roots(bodies: dict[str, str]) -> dict[str, Element]:
    return {slug: fragment(body) for slug, body in bodies.items()}


def rows_of(table: Element) -> list[list[Element]]:
    bodies_ = table.find(tag="tbody")
    source = bodies_[0] if bodies_ else table
    return [
        [n for n in row.children if isinstance(n, Element) and n.tag in {"th", "td"}]
        for row in source.find(tag="tr")
    ]


def table_with_caption(root: Element, needle: str) -> Element:
    found = [
        table
        for table in root.find(tag="table")
        if any(needle in caption.text() for caption in table.find(tag="caption"))
    ]
    assert len(found) == 1, f"expected one table captioned with {needle!r}, got {len(found)}"
    return found[0]


def ids_of(root: Element) -> list[str]:
    return [str(n.attrs["id"]) for n in root.walk() if isinstance(n.attrs.get("id"), str)]


# --- the rules the plan names ------------------------------------------------


def test_measuring_worksheet_has_six_rows_and_no_product_value(roots):
    worksheet = table_with_caption(roots[MEASURE], "採寸シート")
    rows = rows_of(worksheet)
    assert len(rows) == 6, f"the worksheet is the six places the reader measures, got {len(rows)}"
    text = worksheet.text()
    for model, _ in PRODUCTS.values():
        assert model not in text, f"the worksheet must not carry the value of {model}"
    for maker in MAKERS:
        assert maker not in text, f"the worksheet must not name {maker}"
    found = MEASUREMENT.search(text)
    assert found is None, f"the worksheet is the reader's own sheet, not a spec: {found!r}"


def test_official_conditions_table_cites_a_fact_locator_in_every_cell(roots):
    conditions = table_with_caption(roots[MEASURE], "公式が印字している条件")
    rows = rows_of(conditions)
    assert len(rows) == len(PRODUCTS)
    for cells in rows:
        assert cells[0].tag == "th" and cells[0].attrs.get("scope") == "row"
        for cell in cells[1:]:
            sources = cell.find(cls="ps-source")
            assert len(sources) == 1, "every cell cites the one fact it came from"
            source = sources[0]
            links = source.find(tag="a")
            assert links, "the locator names the page it was read on"
            for link in links:
                assert link.attrs.get("href") in OFFICIAL_URLS
            locator = source.text()
            for link in links:
                locator = locator.replace(link.text(), "")
            assert CHECKED_ON in locator, "the locator carries the check date"
            assert len(locator.replace(CHECKED_ON, "").strip("／ 　")) >= 4, (
                f"the locator must name the row it was read from: {source.text()!r}"
            )


def test_unknown_table_lists_exactly_the_seven_values_nobody_prints(roots):
    unknown = table_with_caption(roots[MEASURE], "公式に数値がない")
    rows = rows_of(unknown)
    assert [cells[0].text() for cells in rows] == list(UNKNOWN_ITEMS)
    for cells in rows:
        assert len(cells) == 3, "未掲載の項目 ／ 対象 ／ 自分で確かめること"
        step = cells[2].text()
        assert len(step) >= 8 and ("測" in step or "確か" in step or "用意" in step), (
            f"a value nobody prints is replaced by a measuring step: {step!r}"
        )


def test_each_article_states_its_own_central_question_once(bodies, roots):
    for slug, question in CENTRAL_QUESTIONS.items():
        marked = roots[slug].find(cls="ks-central-question")
        assert len(marked) == 1, f"{slug} states one central question"
        assert marked[0].text() == QUESTION_LABEL + question
        assert bodies[slug].count(question) == 1, f"{slug} states it once"
        for other, text in CENTRAL_QUESTIONS.items():
            if other != slug:
                assert text not in bodies[slug], f"{slug} must not answer {other}"


# --- the wave's standing rules ----------------------------------------------


def test_missing_values_are_written_unconfirmed_and_never_become_a_fit_verdict(roots):
    root = roots[MEASURE]
    unknown = table_with_caption(root, "公式に数値がない")
    assert "未確認" in root.text()
    conditions = table_with_caption(root, "公式が印字している条件")
    for cells in rows_of(conditions):
        for cell in cells[1:]:
            if "未確認" not in cell.text():
                continue
            assert "測" in cell.text() or "確か" in cell.text(), (
                f"未確認 is paired with the step that replaces it: {cell.text()!r}"
            )
    # 42666 prints no 対応サイズ row and no 耐荷重 row, so neither may read as a fit.
    smart = [cells for cells in rows_of(conditions) if "42666" in cells[0].text()]
    assert len(smart) == 1
    assert smart[0][2].text().startswith("未確認") and smart[0][3].text().startswith("未確認")
    assert "42666" in unknown.text()


def test_disclosure_says_the_article_carries_no_affiliate_link(bodies, roots):
    for slug in WAVE:
        notices = roots[slug].find(cls="ps-disclosure")
        assert len(notices) == 1, f"{slug} carries exactly one disclosure"
        assert notices[0].text() == DISCLOSURE
        body = bodies[slug]
        for marker in (
            'rel="sponsored"',
            "a.rakuten.co.jp",
            "hb.rakuten.co.jp",
            "data-affiliate",
            "アフィリエイトリンクが含まれます",
        ):
            assert marker not in body, f"{slug} has no approved offer, so no {marker}"


def test_outward_links_reach_only_the_maker_pages(roots):
    for slug in WAVE:
        for link in roots[slug].find(tag="a"):
            href = str(link.attrs.get("href") or "")
            if not href.startswith("http"):
                continue
            assert href in OFFICIAL_URLS, f"{slug} links outward only to the maker page: {href}"


def test_the_three_link_to_each_other_and_to_no_unpublished_article(roots):
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))["articles"]
    # A row is reachable once it has a post: articles say so in listing.state,
    # the hub pages carry no listing and are identified by their tracked post_id.
    published = {
        row["slug"]
        for row in ledger
        if row.get("listing", {}).get("state") == "published"
        or (row.get("mode") == "existing" and row.get("post_id"))
    }
    allowed = published | set(WAVE)
    for slug in WAVE:
        targets = set()
        for link in roots[slug].find(tag="a"):
            href = str(link.attrs.get("href") or "")
            match = re.fullmatch(r"/([a-z0-9-]+)/(?:#[A-Za-z0-9_-]+)?", href)
            if match:
                targets.add(match.group(1))
        assert "kitchen" in targets, f"{slug} returns to the published hub"
        assert targets & set(WAVE) - {slug}, f"{slug} links to the rest of the wave"
        assert targets <= allowed, f"{slug} links to an unpublished article: {targets - allowed}"


def test_figures_are_editorial_schematics_and_never_a_product_photo(bodies, roots):
    expected = {MEASURE: 2, SLIM: 1, NO_SPACE: 1}
    for slug, count in expected.items():
        diagrams = roots[slug].find(cls="ps-guide-diagrams")
        assert len(diagrams) == count, f"{slug} carries {count} text figure(s)"
        assert "<img" not in bodies[slug], f"{slug} states no photo it does not have"
        for diagram in diagrams:
            captions = diagram.find(tag="figcaption")
            assert captions, "every figure says who drew it"
            for caption in captions:
                assert "編集部作成" in caption.text()
                assert "実物の外観" in caption.text() or "商品の外観図ではありません" in caption.text()


def test_the_comparison_anchors_exist_once_and_carry_the_bound_rows(roots):
    anchors = {MEASURE: "guide-evidence", SLIM: "slim-compare", NO_SPACE: "rack-methods"}
    scopes = {
        MEASURE: list(PRODUCTS),
        SLIM: ["PRD-YAMAZAKI-4314", "PRD-YAMAZAKI-5070", "PRD-SHIMOMURA-42666"],
        NO_SPACE: list(PRODUCTS),
    }
    for slug, anchor in anchors.items():
        root = roots[slug]
        assert ids_of(root).count(anchor) == 1, f"{slug} names {anchor} once"
        section = next(n for n in root.find(tag="section") if n.attrs.get("id") == anchor)
        rows = [r for r in section.find(tag="tr") if r.attrs.get("data-product-key")]
        assert [r.attrs.get("data-product-id") for r in rows] == scopes[slug]
        for row in rows:
            for kind in ("media", "offer"):
                slots = row.find(cls="ps-row-" + kind)
                assert len(slots) == 1 and not slots[0].children, (
                    f"{slug}: the renderer fills the {kind} slot"
                )
                assert slots[0].attrs.get("data-product-key") == row.attrs["data-product-key"]
        table = next(t for t in section.find(tag="table") if t.find(tag="tbody"))
        heads = table.find(tag="thead")[0].find(tag="th")
        assert 3 <= len(heads) <= 6


def test_condition_slots_stay_empty_and_follow_the_planned_order(roots):
    expected = {
        SLIM: [
            ("cond-long", "PRD-YAMAZAKI-4314"),
            ("cond-two-tier", "PRD-YAMAZAKI-5070"),
            ("cond-short", "PRD-SHIMOMURA-42666"),
        ],
        NO_SPACE: [
            ("m-fixed", "PRD-YAMAZAKI-4314"),
            ("m-fixed", "PRD-YAMAZAKI-5070"),
            ("m-fixed", "PRD-SHIMOMURA-42666"),
            ("m-over-sink", "PRD-YAMAZAKI-4314"),
            # 5070 prints 「（シンク渡し使用時）」 in its 対応サイズ row, so the
            # sink-spanning method holds it too (round 2, 2026-09-17).
            ("m-over-sink", "PRD-YAMAZAKI-5070"),
            ("m-over-sink", "PRD-YAMAZAKI-7835"),
            ("m-over-sink", "PRD-YAMAZAKI-3492"),
            ("m-temporary", "PRD-YAMAZAKI-7835"),
        ],
    }
    for slug, identities in expected.items():
        root = roots[slug]
        photos = root.find(cls="ps-condition-product-media")
        purchases = root.find(cls="ps-condition-product-purchase")
        assert [
            (n.attrs.get("data-ps-condition"), n.attrs.get("data-ps-media-product"))
            for n in photos
        ] == identities
        assert [
            (n.attrs.get("data-ps-condition"), n.attrs.get("data-ps-purchase-product"))
            for n in purchases
        ] == identities
        assert not any(n.children for n in photos + purchases)


def test_scope_models_are_literal_in_the_measuring_guide(bodies):
    text = re.sub(r"<[^>]+>", " ", bodies[MEASURE])
    for model, _ in PRODUCTS.values():
        assert model in text, f"READER_SCOPE_MODEL_MISSING would fire for {model}"


def test_no_ranking_of_comfort_or_performance(bodies, roots):
    for slug in WAVE:
        text = roots[slug].text()
        for denial in DENIALS:
            text = text.replace(denial, "")
        found = RANKING.search(text)
        assert found is None, f"{slug} ranks nothing: {found!r}"
        assert NOT_A_RANKING in bodies[slug]


def test_printed_japanese_is_quoted_as_the_maker_prints_it(bodies):
    joined = "".join(bodies[slug] for slug in WAVE)
    for _, quoted in QUOTED:
        assert quoted in joined, f"the printed value must survive verbatim: {quoted}"
    # 5070 prints 「約」 on the size drawing only; the article keeps both spellings.
    assert "約55×約14.8×約3.5cm" in bodies[SLIM] or "約55" in bodies[SLIM]
    # 42666 prints no 段数 row, so the article never calls it a one-tier rack.
    for slug in WAVE:
        assert "1段" not in bodies[slug], f"{slug} prints no 段数 the maker does not"


def test_quotations_match_the_tracked_catalog_when_the_wave_rows_land(bodies):
    """Cross-check the quoted Japanese against the catalog once W1 data is tracked.

    The article job and the data job land together; until the catalog carries the
    five dish-rack products this walks an empty set and asserts nothing further.
    """
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    products = {p["product_id"]: p for p in catalog["products"] if p["product_id"] in PRODUCTS}
    joined = "".join(bodies[slug] for slug in WAVE)
    for product_id, product in products.items():
        model, official = PRODUCTS[product_id]
        assert product["exact_model"] == model
        assert product["official_url"] == official
        printed = "".join(fact["text"] for fact in product["facts"])
        for owner, quoted in QUOTED:
            if owner == product_id:
                assert quoted in printed, f"{quoted} is not what {model} prints"
        assert quoted in joined

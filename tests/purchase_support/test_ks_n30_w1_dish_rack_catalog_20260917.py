"""next30 Wave 1 (2026-09-17): the five dish-rack products enter the live catalog.

Wave 1 writes A01 / A02 / A03 about dish racks. Before a template can quote a
number, `changes/reader-purchase-support-v1/purchase-support.v1.json` has to
carry the five verified products (山崎実業 4314・5070・7835・3492 と 下村企販 42666)
in the shape `validate_catalog` accepts, with every fact keeping the locator and
the check date it was verified with, and with nothing claimed as KNOWN that has
no official page behind it.

The five products have no approved affiliate offer, so each one needs a research
issue (`PURCHASE_DESTINATION_OR_ISSUE_REQUIRED`) and each one has to be reached
from a `curated_comparison` (`PURCHASE_UNUSED_PRODUCT`). Their photos stay out:
`image_review.state` is UNVERIFIED with a reason, which is the only non-verified
state `resolve_product_media` accepts — an absent `image_review` raises
`PURCHASE_MEDIA_REVIEW_REQUIRED` rather than withholding the picture.

The verbatim assertions below are the guard the wave actually needs: the cells of
表2 (A01)、表A (A02) and 表B (A03) are filled from these exact strings, and a
re-worded fact would put a sentence on the site that no official page prints.

All three articles are `curated_comparison`, A01 included. The plan asks for
`kind: "guide"`, but a catalog guide is not a general kind: `render_guide` reads
its stage from `STAGES` by slug (purchase_support.py:2366), so any slug outside
the five dishwasher guides raises StopIteration, and the body it builds is the
dishwasher model index and stage table. A01 keeps `listing.role: "guide"` and
`reader_role.page_kind: "task_guide"` in the ledger — the catalog kind does not
change a role (tests/site_editorial_pages/test_ledger_listings.py:478) — and its
measuring steps live in the template rather than in `reader_steps`, which only
`render_guide` reads.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from raos.application.editorial.purchase_support import validate_catalog

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "changes/reader-purchase-support-v1/purchase-support.v1.json"
# The verified copy Wave 0 recorded. Wave 1 imports five of its 17 products.
CANDIDATE_PATH = ROOT / "changes/next30-20260916/products.candidate.v1.json"
# Copied without a word changed; only the live-schema fields are added on top.
COPIED = ("exact_model", "name", "anchor", "official_url", "facts", "guide_facts", "installation")
ADDED = {"lead", "fit", "avoid", "caution", "use_cases", "image_review"}

DISH_RACKS = (
    "PRD-YAMAZAKI-4314",
    "PRD-YAMAZAKI-5070",
    "PRD-SHIMOMURA-42666",
    "PRD-YAMAZAKI-7835",
    "PRD-YAMAZAKI-3492",
)
# product_id -> (exact_model, official_url). The model is what a task_guide body
# must print literally (READER_SCOPE_MODEL_MISSING) and what every fact repeats.
IDENTITIES = {
    "PRD-YAMAZAKI-4314": ("4314", "https://www.yamajitsu.co.jp/products/241440"),
    "PRD-YAMAZAKI-5070": ("5070", "https://www.yamajitsu.co.jp/products/241827"),
    "PRD-SHIMOMURA-42666": (
        "42666",
        "https://www.simomura-kihan.co.jp/products/category/detail---id-289.html",
    ),
    "PRD-YAMAZAKI-7835": ("7835", "https://www.yamajitsu.co.jp/products/242645"),
    "PRD-YAMAZAKI-3492": ("3492", "https://www.yamajitsu.co.jp/products/241233"),
}
# The three cells the wave's tables are built from, quoted as the maker prints them.
VERBATIM = {
    "PRD-YAMAZAKI-4314": {
        "本体寸法（幅×奥行×高さ）": (
            "幅555×奥行165×高さ160mm（公式の印字はcmで「W55.5×D16.5×H16cm」。"
            "公式サイズ図も「55.5cm」「16.5cm」「16cm」で「約」は付いていません）"
        ),
        "対応するシンクの条件（公式表記は「対応サイズ」）": (
            "奥行50cm以内のシンク　厚み1.8cmのまな板（原文ママ。条件はシンクの「奥行」で、"
            "この行にシンクの「内寸」は印字されていません。"
            "仕様表には別に「内寸」行がありますが、"
            "値は「開口部：W54.5×D16cm　高さ：11.5cm」で本体側の寸法です）"
        ),
        "耐荷重": "8kg",
    },
    "PRD-YAMAZAKI-5070": {
        "本体寸法（幅×奥行×高さ）": (
            "幅575×奥行160×高さ335mm（公式の印字はcmで、仕様表は「W57.5×D16×H33.5cm」、"
            "公式サイズ図は「約57.5cm」「約16cm」「約33.5cm」と「約」付き。"
            "値は同じで表記だけが異なります）"
        ),
        "対応するシンクの条件（公式表記は「対応サイズ」）": (
            "厚み2cmまでのまな板・奥行50cm以内のシンク（シンク渡し使用時）"
            "（原文ママ。シンクの条件は「奥行」で、しかも「シンク渡し使用時」という使用条件が"
            "付いています。この行にシンクの「内寸」は印字されていません。"
            "仕様表には別に「内寸」行がありますが、値は"
            "「ワイヤーバスケット：W54.5×D15.4×H11.5cm　 ワイヤーバスケットのスリット幅：2cm　"
            "ハンドル部：W15.5×D2cm」で本体側の寸法です）"
        ),
        "耐荷重": "ワイヤーバスケット：8kg  水切りトレー：5kg  フック：1つにつき250g",
    },
    "PRD-SHIMOMURA-42666": {
        "本体寸法（幅×奥行×高さ）": (
            "幅403×奥行180×高さ160mm（公式の印字はcmで「幅40.3×奥行18×高さ16cm」。"
            "同じ「サイズ」行に「バスケット内寸:幅37×奥行17×深さ7(10.5)cm、"
            "トレー:幅38×奥行18×高さ1.3cm」も1行にまとめて印字されています）"
        ),
        "対応するシンクの条件（対応サイズ行の有無）": (
            "公式商品ページに対応シンク寸法・渡し幅の条件は印字されていません。"
            "「商品の仕様」表の項目は品番・材質・サイズ・重量・生産国・JANコードの6行のみで、"
            "「対応サイズ」に当たる行自体が存在しません。"
            "紹介文もシンク脇に置く前提しか書いていません。"
        ),
        "耐荷重": "公式商品ページに耐荷重の記載はありません（「商品の仕様」表に耐荷重の行がありません）。",
    },
    "PRD-YAMAZAKI-7835": {
        "本体寸法（幅×奥行×高さ）": (
            "幅260×奥行580×高さ8mm（広げた状態。公式の印字はcmで、仕様表は「W26×D58×H0.8cm」、"
            "公式サイズ図は「約58cm」「約26cm」「約0.8cm」と「約」付き。"
            "値は同じで表記だけが異なります。"
            "丸めた／折り畳んだ状態の寸法は公式に印字されていません）"
        ),
        "対応するシンクの条件（公式表記は「対応サイズ」）": (
            "奥行き：54cm以下のシンク（原文ママ。条件はシンクの「奥行き」だけで、"
            "渡し幅は印字されていません。仕様表に「内寸」行そのものがありません）"
        ),
        "耐荷重": "4kg",
    },
    "PRD-YAMAZAKI-3492": {
        "本体寸法（幅×奥行×高さ）": (
            "幅540×奥行195×高さ140mm（幅は最も伸ばした状態の値。"
            "公式の印字はcmで「W44〜54×D19.5×H14cm」、幅は44〜54cm＝440〜540mmの伸縮式です。"
            "公式サイズ図も「44〜54cm」「19.5cm」「14cm」で「約」は付いていません。"
            "同じ「商品サイズ」欄に「カトラリーポケットサイズ：W15×D5.5×H11cm」も併記）"
        ),
        "対応するシンクの条件（公式表記は「対応サイズ」）": (
            "仕様表の「対応サイズ」行は「シンク内寸37cm〜47cm」（「約」なし）。"
            "紹介本文の冒頭は「伸縮可能でシンクの内寸約37cm〜47cmまでに対応。」（「約」付き）。"
            "値は同じで表記だけが異なります。"
            "本クラスタで唯一「内寸」を条件にしている商品です。"
        ),
        "耐荷重": "5kg",
    },
}
# The maker prints no 耐荷重 row and no 対応サイズ row for 42666: those two cells
# stay UNKNOWN so that no article turns them into a fit verdict.
UNKNOWN_CELLS = {
    ("PRD-SHIMOMURA-42666", "耐荷重"),
    ("PRD-SHIMOMURA-42666", "対応するシンクの条件（対応サイズ行の有無）"),
}
# The three Wave 1 articles, as §5 of the plan specifies them.
ARTICLES = {
    "dish-rack-installation-measurement": ("guide-evidence", DISH_RACKS),
    "slim-dish-rack-under-20cm": (
        "slim-compare",
        ("PRD-YAMAZAKI-4314", "PRD-YAMAZAKI-5070", "PRD-SHIMOMURA-42666"),
    ),
    "dish-rack-no-space": ("rack-methods", DISH_RACKS),
}
CONDITION_SLOTS = {
    "slim-dish-rack-under-20cm": [
        ("cond-long", "PRD-YAMAZAKI-4314"),
        ("cond-two-tier", "PRD-YAMAZAKI-5070"),
        ("cond-short", "PRD-SHIMOMURA-42666"),
    ],
    "dish-rack-no-space": [
        ("m-fixed", "PRD-YAMAZAKI-4314"),
        ("m-fixed", "PRD-YAMAZAKI-5070"),
        ("m-fixed", "PRD-SHIMOMURA-42666"),
        ("m-over-sink", "PRD-YAMAZAKI-4314"),
        # 5070 prints 「（シンク渡し使用時）」 in its 対応サイズ row (round 2).
        ("m-over-sink", "PRD-YAMAZAKI-5070"),
        ("m-over-sink", "PRD-YAMAZAKI-7835"),
        ("m-over-sink", "PRD-YAMAZAKI-3492"),
        ("m-temporary", "PRD-YAMAZAKI-7835"),
    ],
}
# The ten authored comparisons keep their own post ids; a Wave 1 article must not
# join that hardcoded set (validate_catalog would reject the catalog outright).
AUTHORED_COMPARISON_POST_IDS = {41, 83, 30, 28, 19, 82, 84, 85, 86, 29}


@pytest.fixture(scope="module")
def catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text())


@pytest.fixture(scope="module")
def racks(catalog) -> dict:
    return {
        p["product_id"]: p
        for p in catalog["products"]
        if p["product_id"] in set(DISH_RACKS)
    }


def records(product: dict) -> list[dict]:
    """Every sourced record of a product: the fact table and the guide fields."""
    return [*product["facts"], *product.get("guide_facts", [])]


def test_validator_accepts_the_catalog_carrying_the_five_dish_racks(catalog, racks):
    validate_catalog(catalog)
    assert sorted(racks) == sorted(DISH_RACKS)
    for pid, (model, url) in IDENTITIES.items():
        assert racks[pid]["exact_model"] == model
        assert racks[pid]["official_url"] == url
        assert racks[pid]["name"].endswith(model)


def test_every_record_carries_a_locator_and_a_check_date(racks):
    assert sorted(racks) == sorted(DISH_RACKS)
    for pid, product in racks.items():
        for record in records(product):
            name = record.get("label") or record.get("field")
            assert record["locator"].strip(), (pid, name)
            assert record["checked_at"] == "2026-09-16", (pid, name)
            assert record["exact_model"] == IDENTITIES[pid][0], (pid, name)


def test_no_known_record_stands_without_an_official_source(racks):
    assert sorted(racks) == sorted(DISH_RACKS)
    for pid, product in racks.items():
        for record in records(product):
            name = record.get("label") or record.get("field")
            assert record["state"] in {"KNOWN", "UNKNOWN"}, (pid, name)
            if record["state"] == "KNOWN":
                assert record["source_url"].startswith("https://"), (pid, name)


def test_the_live_records_are_the_verified_copy_word_for_word(racks):
    candidate = {
        p["product_id"]: p
        for p in json.loads(CANDIDATE_PATH.read_text())
        if p["product_id"] in set(DISH_RACKS)
    }
    assert sorted(candidate) == sorted(DISH_RACKS)
    for pid, verified in candidate.items():
        live = racks[pid]
        for key in COPIED:
            assert live[key] == verified[key], (pid, key)
        # Only the live schema's own fields are added; nothing else appears.
        assert set(live) - set(verified) == ADDED, pid
        assert set(verified) - set(live) == {"category"}, pid


def test_the_cells_the_tables_quote_are_the_printed_text(racks):
    for pid, cells in VERBATIM.items():
        labelled = {f["label"]: f for f in racks[pid]["facts"]}
        for label, text in cells.items():
            assert label in labelled, (pid, label)
            assert labelled[label]["text"] == text, (pid, label)
            expected = "UNKNOWN" if (pid, label) in UNKNOWN_CELLS else "KNOWN"
            assert labelled[label]["state"] == expected, (pid, label)


def test_the_dish_racks_sell_nothing_and_withhold_their_photos(catalog, racks):
    assert sorted(racks) == sorted(DISH_RACKS)
    ids = set(DISH_RACKS)
    assert not [o for o in catalog["offers"] if o["product_id"] in ids]
    for pid, product in racks.items():
        assert "display_offer_id" not in product, pid
        assert product["image_review"]["state"] == "UNVERIFIED", pid
        assert product["image_review"]["reason"].strip(), pid


def test_every_dish_rack_has_an_open_research_issue(catalog):
    issues = {
        i["product_id"] for i in catalog["research_issues"] if i["status"] != "RESOLVED"
    }
    assert set(DISH_RACKS) <= issues


def test_every_dish_rack_is_reached_from_a_curated_comparison(catalog):
    used: set[str] = set()
    for article in catalog["articles"]:
        if article["kind"] == "curated_comparison":
            used.update(article["product_ids"])
    assert set(DISH_RACKS) <= used


def test_the_three_wave_one_articles_compile_from_the_catalog(catalog):
    articles = {a["article_id"]: a for a in catalog["articles"]}
    for slug, (anchor, products) in ARTICLES.items():
        article = articles[slug]
        assert article["slug"] == slug
        assert article["kind"] == "curated_comparison"
        assert article["commerce_anchor"] == anchor
        assert article["commerce_presentation"] == "comparison_rows"
        assert article["responsive_layout"] == "matrix"
        assert tuple(article["product_ids"]) == products
        # bind_comparison_rows compares row order with product_ids directly.
        assert [r["product_id"] for r in article["row_products"]] == list(products)
        assert len({r["key"] for r in article["row_products"]}) == len(products)
    for slug, slots in CONDITION_SLOTS.items():
        assert [
            (s["key"], s["product_id"]) for s in articles[slug]["condition_slots"]
        ] == slots
    assert "condition_slots" not in articles["dish-rack-installation-measurement"]


def test_wave_one_does_not_join_the_authored_comparison_set(catalog):
    posts = {a["post_id"] for a in catalog["articles"] if a["kind"] == "comparison"}
    assert posts == AUTHORED_COMPARISON_POST_IDS
    assert set(catalog["target_post_ids"]) == AUTHORED_COMPARISON_POST_IDS


@pytest.mark.parametrize("field", ["locator", "checked_at"])
def test_dropping_a_locator_or_a_check_date_is_rejected(catalog, field):
    broken = copy.deepcopy(catalog)
    product = next(
        p for p in broken["products"] if p["product_id"] == "PRD-YAMAZAKI-4314"
    )
    product["facts"][0][field] = ""
    with pytest.raises(ValueError, match="PURCHASE_FACT_SOURCE_REQUIRED"):
        validate_catalog(broken)


def test_a_known_fact_without_an_official_url_is_rejected(catalog):
    broken = copy.deepcopy(catalog)
    product = next(
        p for p in broken["products"] if p["product_id"] == "PRD-SHIMOMURA-42666"
    )
    known = next(f for f in product["facts"] if f["state"] == "KNOWN")
    known["source_url"] = "http://www.simomura-kihan.co.jp/"
    with pytest.raises(ValueError, match="PURCHASE_FACT_SOURCE_REQUIRED"):
        validate_catalog(broken)

"""Dishwasher guide renderer checks for the 2026-09-15 batch 2 (KS-125/127/129/028-d/009).

Renderer-only checks build from the tracked catalog or from an in-memory copy.
The KS-125 reader_unknowns_note and KS-127 amount split are catalog data; their
end-to-end checks here pass only once that data is in the tracked catalog.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest

from raos.application.editorial.purchase_support import (
    compile_articles,
    guide_decision_table,
    validate_catalog,
)
from raos.application.editorial.reader_html import fragment
from raos.application.editorial.site_guide_improvements import render_guide_intro
from scripts import build_reader_purchase_support_v1 as builder

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "changes/reader-purchase-support-v1"
GUIDES = ROOT / "changes/editorial-portfolio-v3/local-reader-guides.v1.json"
CAPTION_TAIL = (
    "を決めるための表。値は下の機種別欄の出典から転記した公表条件で、"
    "同じ条件での実測比較ではありません。"
)
# Decision 1 (amended): neither NP-TSP1 manual gives a door-open depth, so the
# reader is sent to the manufacturer, not to the manuals.
MAKER_CHECK = "どちらの値かはメーカー（相談窓口）へ確認してください。"
DOOR_NOTE = "公式資料で値が異なります（個別仕様 上386mm・下362mm、比較表 433mm）。" + MAKER_CHECK
SPEC_URL = "https://panasonic.jp/dish/products/NP-TSP1/spec.html"
COMPARISON_URL = "https://panasonic.jp/dish/comparison.html"
INSTALLATION_URL = "https://panasonic.jp/dish/installation.html"
REAR_TEXT = "設置案内の図では、本体と壁面の間に排水ホース外径分を含めて1.7cm（17mm）以上のあきが必要です。"
REAR_FIGURE_ALT = "「図：本体と壁面の間に1.7cm以上のあきが必要。排水ホース外径分を含む。」"


def compile(catalog):
    end = datetime.combine(
        date.fromisoformat(catalog["editorial_updated_on"]),
        time(23, 59, 59),
        tzinfo=timezone(timedelta(hours=9)),
    )
    return compile_articles(
        catalog,
        {p.stem: p.read_text() for p in (BASE / "articles").glob("*.html")},
        json.loads(GUIDES.read_text()),
        now=end,
    )


@pytest.fixture(scope="module")
def tracked_catalog():
    return json.loads(builder.CATALOG_INPUT_PATH.read_text())


@pytest.fixture(scope="module")
def tracked():
    return {
        path.stem: text
        for path, text in builder.build().items()
        if path.suffix == ".html"
    }


def by_id(root, identity):
    return next(n for n in root.walk() if n.attrs.get("id") == identity)


def guide_table(root):
    return next(t for t in root.find(tag="table") if t.has("ps-guide-table"))


def row_labels(table):
    return [tr.find(tag="th")[0].text() for tr in table.find(tag="tbody")[0].find(tag="tr")]


def product(catalog, product_id):
    return next(p for p in catalog["products"] if p["product_id"] == product_id)


# KS-125 -------------------------------------------------------------------


def test_installation_table_caption_names_published_and_calculated_values(tracked):
    captions = {
        slug: guide_table(fragment(tracked[slug])).find(tag="caption")[0].text()
        # The water guide keeps its authored table layout and has no ps-guide-table.
        for slug in (
            "dishwasher-installation-measurement",
            "dishwasher-cleaning-guide",
            "dishwasher-running-cost",
        )
    }
    installation = captions["dishwasher-installation-measurement"]
    assert installation.startswith("4機種の設置を決めるための表。")
    assert "公表条件・公表寸法" in installation
    assert "その条件から計算した照合用の値" in installation
    assert installation.endswith("同じ条件での実測比較ではありません。")
    # Other stages keep their caption byte for byte.
    water = fragment(guide_decision_table("water", [])).find(tag="caption")[0].text()
    assert water == "4機種の給水・排水" + CAPTION_TAIL
    assert captions["dishwasher-cleaning-guide"] == "4機種の手入れ" + CAPTION_TAIL
    assert captions["dishwasher-running-cost"] == "4機種の維持費" + CAPTION_TAIL


def test_installation_unknowns_do_not_contradict_cited_clearance(tracked, tracked_catalog):
    """Data-dependent: needs the KS-125 reader_unknowns_note in the tracked catalog."""
    solota = product(tracked_catalog, "PRD-PANASONIC-NP-TMLK1")["installation"]
    assert all(isinstance(solota[k], (int, float)) for k in ("above_mm", "left_mm", "right_mm"))
    root = fragment(tracked["dishwasher-installation-measurement"])
    unknowns = by_id(root, "reader-unknowns").text()  # .ps-history is outside this section
    assert "上・左右の必要余白" not in unknowns
    assert not re.search(r"SOLOTAの上[^。]*未確認", unknowns)
    assert "開扉時の高さは未確認" in unknowns


# KS-127 -------------------------------------------------------------------


def test_detergent_decision_table_is_the_published_test_amount_only():
    p = {
        "product_id": "P",
        "anchor": "model",
        "name": "Model",
        "guide_summary": {"detergent": {"公表試験条件の洗剤量": "5g", "1回分の目安": "x"}},
    }
    region = fragment(guide_decision_table("detergent", [p])).find(cls="ps-table-scroll")[0]
    table = region.find(tag="table")[0]
    assert row_labels(table) == ["公表試験条件の洗剤量"]
    assert table.find(tag="caption")[0].text() == (
        "4機種の公表試験条件の洗剤量。使用量の指示ではなく、公表値の試験で使った洗剤量です。"
        "値は下の機種別欄の出典から転記した公表条件です。"
    )
    assert region.attrs["aria-label"] == "4機種の公表試験条件の洗剤量"


def test_detergent_answer_table_separates_amounts_and_lists_prohibitions(tracked):
    """Data-dependent: needs the KS-127 通常量 / 汚れが多いときの量 split in the catalog."""
    root = fragment(tracked["dishwasher-detergent-guide"])
    answer = by_id(root, "guide-detergent-answer")
    heads = [th.text() for th in answer.find(tag="thead")[0].find(tag="th")]
    assert heads == ["型番", "使える洗剤", "1回の量", "入れる位置", "使えないもの（主なもの）"]
    assert "／タブレット：" not in answer.text()
    rows = {
        tr.find(tag="th")[0].text(): tr.find(tag="td")
        for tr in answer.find(tag="tbody")[0].find(tag="tr")
    }
    assert set(rows) == {"NP-TMLK1-K", "TDWS25SBL / TDWS25SRD", "SS-MA251", "NP-TSP1-W"}
    amounts = {model: [li.text() for li in cells[1].find(tag="li")] for model, cells in rows.items()}
    assert amounts["NP-TMLK1-K"][:2] == ["通常：約2g", "汚れが多いとき：油・色素汚れは約4g"]
    assert amounts["NP-TSP1-W"][:2] == ["通常：約5g", "汚れが多いとき：約10g"]
    assert all(len(lines) == 3 and lines[2].startswith("タブレット：") for lines in amounts.values())
    prohibited = {model: cells[3] for model, cells in rows.items()}
    assert "プラスチック：80℃未満" in prohibited["NP-TMLK1-K"].text()
    assert [a.attrs.get("href") for a in prohibited["NP-TMLK1-K"].find(tag="a")] == [
        "#product-dish-np-tmlk1"
    ]
    # Decision 7: both manuals ban plastic without a heat label; each keeps its
    # low-temperature course exception (NP-TSP1 p.2/p.7, SS-MA251 p.8/p.25).
    assert (
        "プラスチック：耐熱60℃未満・表示なしは不可（60℃以上90℃未満は低温ソフトで洗う）"
        in prohibited["NP-TSP1-W"].text()
    )
    assert (
        "プラスチック：耐熱65℃未満・表示なしは不可（65℃以上90℃未満はソフトコースで洗う）"
        in prohibited["SS-MA251"].text()
    )
    assert "のみ低温ソフト" not in answer.text()
    assert "表示なしは通常コース不可" not in answer.text()
    assert all("強化ガラス" in cell.text() for cell in prohibited.values())
    assert row_labels(guide_table(root)) == ["公表試験条件の洗剤量"]


# KS-129 -------------------------------------------------------------------


def test_running_cost_example_cross_references_solota_unit_prices():
    section = by_id(fragment(render_guide_intro("cost", [])), "guide-cost-example")
    text = section.text()
    assert "/compact-dishwasher-comparison/#compact-cost" in [
        a.attrs.get("href") for a in section.find(tag="a")
    ]

    def per_run(wh, litres, power_yen, water_yen, detergent_yen):
        return round(wh / 1000 * power_yen + litres / 1000 * water_yen + detergent_yen, 2)

    # The fictional example (12.65) and the SOLOTA example (9.48) use different unit prices.
    assert per_run(230, 2.5, 30, 300, 5) == 12.65 and "12.65円/回" in text
    assert per_run(230, 2.5, 31, 300, 0.8 * 2) == 9.48
    for phrase in ("約9.48円/回", "電気31円/kWh", "上下水道300円/m³", "洗剤0.8円/g・2g", "比べません"):
        assert phrase in text
    fictional = next(p.text() for p in section.find(tag="p") if "12.65円/回" in p.text())
    assert "SOLOTA" not in fictional
    compact = by_id(
        fragment((BASE / "articles/compact-dishwasher-comparison.html").read_text()),
        "compact-cost",
    ).text()
    for phrase in ("SOLOTA・標準コースの計算例", "9.48円", "電気31円/kWh", "上下水道300円/m³", "洗剤0.8円/g・2g"):
        assert phrase in compact


# KS-028-d -----------------------------------------------------------------


def test_running_cost_model_routes_do_not_skip_heading_levels(tracked):
    levels = [int(level) for level in re.findall(r"<h([1-6])[\s>]", tracked["dishwasher-running-cost"])]
    previous = 1  # the theme renders the article title as h1
    for level in levels:
        assert level <= previous + 1, levels
        previous = level
    route = '<div class="ps-model-routes-block"><h4>'
    assert route in tracked["dishwasher-installation-measurement"]
    assert route in tracked["countertop-dishwasher-for-small-households"]


# KS-009 -------------------------------------------------------------------


def door_conflict(catalog, *, labels=True):
    sources = [
        {
            "label": "個別仕様",
            "value": "上386mm・下362mm",
            "source_url": "https://panasonic.jp/dish/products/NP-TSP1/spec.html",
            "locator": "仕様・スペック表「本体外形寸法」行と表末の注記",
            "checked_at": "2026-09-15",
        },
        {
            "label": "比較表",
            "value": "433mm",
            "source_url": "https://panasonic.jp/dish/comparison.html",
            "locator": "比較表「本体外形寸法」行のNP-TSP1列",
            "checked_at": "2026-09-15",
        },
    ]
    if not labels:
        for source in sources:
            del source["label"]
    p = product(catalog, "PRD-PANASONIC-NP-TSP1")
    records = [f for f in p["facts"] if f["label"] == "開扉時の寸法"] + [
        f for f in p["guide_facts"] if f["field"] == "door"
    ]
    assert len(records) == 2
    for record in records:
        record.update(
            state="CONFLICT",
            conflict_sources=deepcopy(sources),
            conflict_installation_keys=["door_depth_mm"],
        )
    return p


def test_conflict_door_depth_names_both_official_values_without_choosing(tracked_catalog):
    catalog = deepcopy(tracked_catalog)
    p = door_conflict(catalog)
    html, _ = compile(catalog)
    assert p["installation"]["door_depth_mm"] is None

    guide = fragment(html["dishwasher-installation-measurement"])
    row = next(
        tr
        for tr in guide_table(guide).find(tag="tbody")[0].find(tag="tr")
        if tr.find(tag="th")[0].text() == "扉を開いたとき"
    )
    cell = next(td for td in row.find(tag="td") if td.attrs.get("data-ps-product") == p["product_id"])
    assert cell.text() == "奥行 公式資料で値が異なる（個別仕様 上386mm・下362mm、比較表 433mm）／高さ 712mm"
    model = by_id(guide, p["anchor"])
    assert DOOR_NOTE in model.text()
    reference = model.find(cls="ps-installation-reference")[0].text()
    assert "公式資料で値が異なる項目：開扉時の奥行（個別仕様 上386mm・下362mm、比較表 433mm）" in reference
    assert "確認できていない項目：開扉時の奥行" not in reference
    assert "どちらの値かはメーカー（相談窓口）へ確認してください" in reference
    assert "取扱説明書" not in reference
    # Decision 2: both conflict sources are links next to the note.
    labelled = {(a.text(), a.attrs.get("href")) for a in model.find(tag="a")}
    assert ("個別仕様", SPEC_URL) in labelled and ("比較表", COMPARISON_URL) in labelled

    main = fragment(html["countertop-dishwasher-for-small-households"])
    cells = [
        n
        for n in main.walk()
        if n.attrs.get("data-ps-product") == p["product_id"]
        and n.attrs.get("data-ps-fact-state") == "CONFLICT"
    ]
    assert cells and all(DOOR_NOTE in n.text() for n in cells)


def test_conflict_note_names_locators_when_sources_have_no_label(tracked_catalog):
    from raos.application.editorial.purchase_support import conflict_note

    catalog = deepcopy(tracked_catalog)
    p = door_conflict(catalog, labels=False)
    record = next(f for f in p["facts"] if f["label"] == "開扉時の寸法")
    assert conflict_note(record) == (
        "公式資料で値が異なります（仕様・スペック表「本体外形寸法」行と表末の注記：上386mm・下362mm、"
        "比較表「本体外形寸法」行のNP-TSP1列：433mm）。" + MAKER_CHECK
    )
    assert conflict_note({"state": "UNKNOWN", "text": "x"}) == ""
    validate_catalog(catalog)
    record["conflict_sources"][0]["label"] = " "
    with pytest.raises(ValueError, match="PURCHASE_FACT_CONFLICT_SOURCES_REQUIRED"):
        validate_catalog(catalog)


# Catalog data (KS-125/127/128/009/133/137/138) ------------------------------
# test_data_* read purchase-support.v1.json and its evidence records only; they do
# not build bodies. Keyword checks use substring search, never \b next to Japanese.

from raos.application.editorial.purchase_support import (  # noqa: E402
    installation_consistency_mismatches,
)

DATA_CATALOG_PATH = BASE / "purchase-support.v1.json"
DATA_EVIDENCE = ROOT / "changes/site-improvements-20260913"
DATA_AMOUNT = re.compile(r"(?<![A-Za-z0-9_.])[0-9]+(?:〜[0-9]+)?g")


def _data_catalog() -> dict:
    return json.loads(DATA_CATALOG_PATH.read_text(encoding="utf-8"))


def _data_product(catalog: dict, product_id: str) -> dict:
    return next(p for p in catalog["products"] if p["product_id"] == product_id)


def _data_article(catalog: dict, slug: str) -> dict:
    return next(a for a in catalog["articles"] if a["slug"] == slug)


def _data_records(p: dict, label: str, field: str) -> list[dict]:
    facts = [f for f in p["facts"] if f["label"] == label]
    guides = [f for f in p.get("guide_facts", []) if f.get("field") == field]
    assert len(facts) == 1 and len(guides) == 1, (p["product_id"], label)
    return facts + guides


def test_data_tmlk1_clearance_issue_is_resolved_by_manual_and_installation_page():
    # KS-125: installation.html (personal type) states 0.5cm between body and wall;
    # manual p.8 lists 上方5・側方0.5・後方0.5 (re-fetched 2026-09-15 19:30 JST).
    catalog = _data_catalog()
    validate_catalog(catalog)
    issue = next(
        i
        for i in catalog["research_issues"]
        if i["issue_id"] == "PRD-PANASONIC-NP-TMLK1-clearance"
    )
    assert issue["status"] == "RESOLVED"
    for text in (issue["impact"], issue["unknown_reason"]["impact"]):
        assert "未確認" not in text and "記載がありません" not in text
        assert "0.5cm" in text and "p.8" in text and "2026年9月15日" in text
    note = _data_article(catalog, "dishwasher-installation-measurement")[
        "reader_unknowns_note"
    ]
    assert note == (
        "SOLOTA・ラクアmini color・SS-MA251の開扉時の高さは未確認です。"
        "設置後の使い勝手は実機で確認していません。"
    )


def test_data_tmlk1_rear_clearance_cites_the_installation_figure():
    # Decision 6 (reverted 2026-09-15 night): the installation.html figure alt gives
    # the rear gap including the drain hose; the section footnote adds the hose to the
    # A4 footprint, so the two agree and rear_mm 17 stays in the fit check.
    catalog = _data_catalog()
    validate_catalog(catalog)
    p = _data_product(catalog, "PRD-PANASONIC-NP-TMLK1")
    for record in _data_records(p, "必要な余白", "clearance"):
        assert record["state"] == "KNOWN"
        assert "conflict_sources" not in record and "conflict_installation_keys" not in record
        assert record["source_url"] == INSTALLATION_URL
        assert REAR_FIGURE_ALT in record["locator"]
        assert "取扱説明書P9901-20V10 p.8" in record["locator"]
        text = record["text"]
        assert text.startswith(REAR_TEXT + "取扱説明書p.8では、可燃物から上方50mm、左右・後方各5mm以上です。")
        assert "別に" not in text and "値が異なる" not in text
    installation = p["installation"]
    assert installation["rear_mm"] == 17
    assert (installation["above_mm"], installation["left_mm"], installation["right_mm"]) == (55, 5, 5)
    assert installation_consistency_mismatches(p) == []


def test_data_detergent_summary_separates_normal_and_heavy_soil_amounts():
    # KS-127: amounts already recorded in each model's detergent fact; no record -> 未確認.
    catalog = _data_catalog()
    expected = {
        "PRD-PANASONIC-NP-TMLK1": ("約2g", "油・色素汚れは約4g"),
        "PRD-THANKO-RAKUA-MINI-COLOR": ("約3〜5g", "未確認"),
        "PRD-SIROCA-SS-MA251": ("約4g", "未確認"),
        "PRD-PANASONIC-NP-TSP1": ("約5g", "約10g"),
    }
    for product_id, amounts in expected.items():
        p = _data_product(catalog, product_id)
        summary = p["guide_summary"]["detergent"]
        assert "1回分の目安" not in summary, product_id
        assert (summary["通常量"], summary["汚れが多いときの量"]) == amounts
        fact = next(f for f in p["guide_facts"] if f["field"] == "detergent")
        for value in amounts:
            if value == "未確認":
                continue
            tokens = DATA_AMOUNT.findall(value)
            assert len(tokens) == 1 and "約" + tokens[0] in fact["text"], (product_id, value)
    tmlk1 = _data_product(catalog, "PRD-PANASONIC-NP-TMLK1")
    assert "色素汚れ" in tmlk1["guide_summary"]["detergent"]["汚れが多いときの量"]


def test_data_cleaning_steps_run_each_time_periodic_dirty_long_term():
    # KS-128: whole objects move; the wording of every step stays the same.
    ranks = (
        ("毎回", 0),
        ("その都度", 0),
        ("週1回", 1),
        ("月1回", 1),
        ("月2〜3回", 1),
        ("定期", 1),
        ("汚れが気になる", 2),
        ("例外手順", 2),
        ("長期間", 3),
        ("長く使わない", 3),
        ("1週間以上使わない", 3),
    )

    def rank(text: str, previous: int) -> int:
        hits = [(text.find(word), -len(word), r) for word, r in ranks if word in text]
        return min(hits)[2] if hits else previous

    catalog = _data_catalog()
    counts = {
        "PRD-PANASONIC-NP-TMLK1": 5,
        "PRD-THANKO-RAKUA-MINI-COLOR": 2,
        "PRD-SIROCA-SS-MA251": 4,
        "PRD-PANASONIC-NP-TSP1": 6,
    }
    for product_id, count in counts.items():
        steps = [
            f["text"]
            for f in _data_product(catalog, product_id)["guide_facts"]
            if f["field"] == "maintenance"
        ]
        assert len(steps) == count, product_id
        order: list[int] = []
        for text in steps:
            order.append(rank(text, order[-1] if order else 0))
        assert order == sorted(order), (product_id, order)


def test_data_tsp1_door_depth_is_a_conflict_between_two_official_pages():
    # KS-009: spec.html 奥行341＜上386,下362＞mm vs comparison.html 341<433>, both
    # captioned as the maximum while the door opens (2026-09-15 19:30 JST). The
    # reader note comes from conflict_sources, so the fact text does not repeat it.
    catalog = _data_catalog()
    validate_catalog(catalog)
    p = _data_product(catalog, "PRD-PANASONIC-NP-TSP1")
    for record in _data_records(p, "開扉時の寸法", "door"):
        assert record["state"] == "CONFLICT"
        assert record["conflict_installation_keys"] == ["door_depth_mm"]
        assert record["conflict_sources"] == [
            {
                "label": "個別仕様",
                "value": "上386mm・下362mm",
                "source_url": "https://panasonic.jp/dish/products/NP-TSP1/spec.html",
                "locator": "仕様・スペック表「本体外形寸法」行と表末の注記",
                "checked_at": "2026-09-15",
            },
            {
                "label": "比較表",
                "value": "433mm",
                "source_url": "https://panasonic.jp/dish/comparison.html",
                "locator": "比較表「本体外形寸法」行のNP-TSP1列",
                "checked_at": "2026-09-15",
            },
        ]
        text = record["text"]
        # Decision 11: the values come from the renderer note; the text does not repeat them.
        assert text == (
            "どちらもドア開閉時の最大寸法と表記しています。"
            "どちらが正しいかは判断せず、数値による設置判定はしません。開扉時の高さは712mm。"
        )
        assert "未解決" not in text and "未解決" not in record["locator"]
        # Decision 3 (amended): the locator names only the linked spec page wording.
        assert record["locator"] == "個別仕様の本体外形寸法と表末の注記「＜＞はドア開閉時の最大寸法」"
        assert not re.search(r"433|386|362", record["locator"])
    assert p["installation"]["door_depth_mm"] is None
    assert p["installation"]["door_height_mm"] == 712
    assert installation_consistency_mismatches(p) == []


def test_data_robot_wifi_bands_cite_the_pages_that_state_them():
    # KS-137: the K11+ Pro product page has no band row; manual p.27 and p.23 do.
    catalog = _data_catalog()
    validate_catalog(catalog)

    def wifi(product_id: str) -> dict:
        return next(
            f
            for f in _data_product(catalog, product_id)["facts"]
            if f["label"] == "アプリ / Wi-Fi"
        )

    k11 = wifi("PRD-SWITCHBOT-K11-PRO")
    assert k11["source_url"] == (
        "https://cdn.shopify.com/s/files/1/0522/2458/9999/files/"
        "K11_Pro-SMS-JP-2604-Q.pdf?v=1784279900"
    )
    assert "p.27" in k11["locator"] and "p.23" in k11["locator"]
    assert "再確認した値ではありません" not in k11["locator"]
    assert (k11["state"], k11["checked_at"]) == ("KNOWN", "2026-09-15")
    assert "2.4GHz" in k11["text"] and "5GHz" not in k11["text"]
    mini = wifi("PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY")
    assert mini["source_url"] == "https://store.irobot-jp.com/item/F155260.html"
    assert "無線通信" in mini["locator"]
    assert (mini["state"], mini["checked_at"]) == ("KNOWN", "2026-09-15")
    # Roomba Plus 515 (2.4GHz only) gets a band record only when an article shows its band.
    plus = _data_product(catalog, "PRD-IROBOT-ROOMBA-PLUS-515-COMBO")
    shows_band = any(
        "GHz" in step and ("515" in step or "N285060" in step)
        for a in catalog["articles"]
        for step in (a.get("decision_steps") or {}).get("steps", [])
    ) or any(
        "GHz" in c["label"] and plus["product_id"] in c.get("product_ids", [])
        for a in catalog["articles"]
        for c in a.get("conditions", [])
    )
    assert any("GHz" in f["text"] for f in plus["facts"]) == shows_band


def test_data_bermas_history_keeps_withheld_entry_and_appends_verification():
    # KS-133: the image was withheld, then verified and displayed on 2026-09-13.
    catalog = _data_catalog()
    history = _data_article(catalog, "carry-on-suitcase-under-100-seats")["history"]
    assert history[:2] == [
        {"date": "2026-09-12", "text": "現行公開本文の内容を維持して移行。原典の過去確認日は個別出典を参照。"},
        {"date": "2026-09-13", "text": "通常時と拡張時を区別し、60524新仕様を公式で再確認。未照合画像を非掲載。"},
    ]
    # Decision 9: the text correction is dated when it was made, not a second 09-13 entry.
    assert history[2:] == [
        {
            "date": "2026-09-15",
            "text": "掲載画像の説明を、60524の販売ページの画像で確認した範囲（USBポートがないこと・背面のトラベルセントリーID）に合わせて訂正",
        }
    ]
    registry = json.loads(
        (DATA_EVIDENCE / "catalog-registry-updates.json").read_text(encoding="utf-8")
    )
    row = next(r for r in registry if r["post_id"] == 82)
    assert "未照合画像を非掲載" in row["update_summary"]
    assert "bermas-new" in row["superseded_note"]
    lines = [
        line
        for line in (DATA_EVIDENCE / "research-catalog.md").read_text(encoding="utf-8").splitlines()
        if "PG082-01" in line
    ]
    assert len(lines) == 2 and all("bermas-new" in line for line in lines)


def test_data_portable_intro_describes_the_calculation_it_shows():
    # KS-138 option B: the approved order stays; the lead stops saying 先に整理.
    catalog = _data_catalog()
    article = _data_article(catalog, "portable-power-station-guide")
    assert "先に整理" not in article["intro"]
    assert "必要なWhを計算し、同時使用W・起動電力・端子は別に確認する例" in article["intro"]
    assert article["intro"].endswith("異なる容量帯を性能順位にしません。")
    assert article["decision_steps"]["placement"] == "after_specs"
    steps = "".join(article["decision_steps"]["steps"])
    assert "240Wh" in steps and "起動電力・端子" in steps


def test_data_histories_record_the_2026_09_15_catalog_corrections():
    catalog = _data_catalog()
    for slug in (
        "dishwasher-installation-measurement",
        "dishwasher-detergent-guide",
        "dishwasher-cleaning-guide",
        "countertop-dishwasher-for-small-households",
        "solota-vs-rakua-mini-plus",
        "roomba-mini-vs-switchbot-k11-pro",
        "carry-on-suitcase-under-100-seats",
    ):
        dates = [e["date"] for e in _data_article(catalog, slug)["history"]]
        assert dates[-1] == "2026-09-15", slug
    for article in catalog["articles"]:
        dates = [e["date"] for e in article.get("history", [])]
        assert dates == sorted(dates), article["slug"]
        # The KS-007 guard reads 250 characters around this phrase; new entries avoid it.
        for entry in article.get("history", []):
            if entry["date"] == "2026-09-15":
                assert "SOLOTAの上・左右" not in entry["text"], article["slug"]


# Amended decisions (2026-09-15 night) ---------------------------------------


def test_conflict_sources_are_links_on_the_installation_guide_and_main_comparison(tracked):
    # Decision 2: the 433mm comparison-table source is reachable wherever the note shows.
    for slug in ("dishwasher-installation-measurement", "countertop-dishwasher-for-small-households"):
        root = fragment(tracked[slug])
        labelled = {(a.text(), a.attrs.get("href")) for a in root.find(tag="a")}
        assert ("個別仕様", SPEC_URL) in labelled and ("比較表", COMPARISON_URL) in labelled, slug
        text = root.text()
        assert DOOR_NOTE in text, slug
        assert REAR_TEXT in text and "設置案内の注記" not in text, slug
        assert "比較表 433mm）。設置前に取扱説明書" not in text, slug


def test_installation_widget_names_conflicting_keys(tracked, tracked_catalog):
    # Decision 3: the fit check learns which unset references are source conflicts.
    root = fragment(tracked["dishwasher-installation-measurement"])
    expected = {"PRD-PANASONIC-NP-TSP1": ["door_depth_mm"]}
    seen = 0
    for p in tracked_catalog["products"]:
        sections = [n for n in root.walk() if n.attrs.get("id") == p["anchor"]]
        if not sections:
            continue
        containers = [n for n in sections[0].walk() if "data-ps-installation" in n.attrs]
        if not containers:
            continue
        seen += 1
        attr = containers[0].attrs.get("data-ps-installation-conflicts")
        if p["product_id"] in expected:
            assert json.loads(attr) == expected[p["product_id"]], p["product_id"]
            values = json.loads(containers[0].attrs["data-ps-installation"])
            assert all(values[key] is None for key in expected[p["product_id"]])
        else:
            assert attr is None, p["product_id"]
    assert seen == 4
    tmlk1 = by_id(root, product(tracked_catalog, "PRD-PANASONIC-NP-TMLK1")["anchor"]).text()
    assert REAR_TEXT in tmlk1 and "公式資料で値が異なります" not in tmlk1


def test_data_plastic_summaries_follow_the_recorded_manual_text():
    # Decision 7: each summary is checked against the model's recorded source text.
    from raos.application.editorial.site_guide_improvements import MATERIAL_LIMITS

    catalog = _data_catalog()
    tsp1 = " ".join(
        f["text"]
        for f in _data_product(catalog, "PRD-PANASONIC-NP-TSP1")["guide_facts"]
        if f["field"] == "prohibited"
    )
    assert "60℃以上90℃未満なら「低温ソフト」で洗います" in tsp1
    assert "耐熱60℃未満や表示のないものは入れないでください" in tsp1
    assert MATERIAL_LIMITS["NP-TSP1-W"][:2] == (
        "耐熱60℃未満・表示なしは不可",
        "60℃以上90℃未満は低温ソフトで洗う",
    )
    siroca = next(
        f["text"]
        for f in _data_product(catalog, "PRD-SIROCA-SS-MA251")["guide_facts"]
        if f["field"] == "detergent"
    )
    assert "ソフトコースで使えるのは耐熱65℃以上です" in siroca
    assert "耐熱表示のないプラスチック食器は洗えません" in siroca
    record = next(
        f
        for f in _data_product(catalog, "PRD-SIROCA-SS-MA251")["guide_facts"]
        if f["field"] == "detergent"
    )
    assert (
        "「耐熱90℃未満、および耐熱表示のないプラスチック食器"
        "（耐熱65℃以上のプラスチック食器は、ソフトコースで洗えます）」"
    ) in record["locator"]
    assert MATERIAL_LIMITS["SS-MA251"][:2] == (
        "耐熱65℃未満・表示なしは不可",
        "65℃以上90℃未満はソフトコースで洗う",
    )

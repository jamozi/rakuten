"""W4b suitcase edits: KS-131, KS-201b, KS-014 links, corrections 2-6 and 13-15.

Bodies compile in memory from ``changes/reader-purchase-support-v1`` so each check
follows the editorial source, not a previously generated copy. Every test here
failed before the W4b source edits.
"""

from __future__ import annotations

from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import re

import pytest

from raos.application.editorial import purchase_support
from raos.application.editorial.reader_html import Element, fragment, readable_tables
from scripts import build_reader_purchase_support_v1 as builder

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "changes/reader-purchase-support-v1/purchase-support.v1.json"
TEMPLATES = ROOT / "changes/reader-purchase-support-v1/articles"
LEDGER = ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json"
THEME_CSS = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/theme.css"
)
SMALL = "small-carry-on-suitcase-comparison"
LIGHT = "lightweight-carry-on-suitcase-under-3kg"
FIT_HEADING = "各社の上限を超える型番（通常時・拡張時）"
SMALL_HREF = "/small-carry-on-suitcase-comparison/"
SUITCASE_KEYS = (
    "carry-on-suitcase-comparison",
    "carry-on-suitcase-under-100-seats",
    "lightweight-carry-on-suitcase-under-3kg",
    "front-open-carry-on-suitcase-with-stopper",
)
SKIPPED_TAGS = frozenset({"script", "style", "template", "code", "pre"})

_emergency = importlib.util.spec_from_file_location(
    "ks_emergency_tokens", Path(__file__).with_name("test_ks_emergency_20260915.py")
)
assert _emergency and _emergency.loader
emergency = importlib.util.module_from_spec(_emergency)
_emergency.loader.exec_module(emergency)


@pytest.fixture(scope="module")
def outputs() -> dict[str, str]:
    return {
        path.stem: body
        for path, body in builder.build().items()
        if path.suffix == ".html"
    }


@pytest.fixture(scope="module")
def roots(outputs: dict[str, str]) -> dict[str, Element]:
    return {slug: fragment(body) for slug, body in outputs.items()}


@pytest.fixture(scope="module")
def catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


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
    return re.sub(r"\s+", " ", "".join(parts))


def by_id(root: Element, element_id: str) -> Element:
    found = [n for n in root.walk() if n.attrs.get("id") == element_id]
    assert len(found) == 1, element_id
    return found[0]


def ancestors(node: Element) -> list[Element]:
    chain = []
    current = node.parent
    while current is not None:
        chain.append(current)
        current = current.parent
    return chain


def article(catalog: dict, slug: str) -> dict:
    return next(a for a in catalog["articles"] if a["slug"] == slug)


def product(catalog: dict, pid: str) -> dict:
    return next(p for p in catalog["products"] if p["product_id"] == pid)


def fact(catalog: dict, pid: str, label: str) -> str:
    return next(
        f["text"] for f in product(catalog, pid)["facts"] if f["label"] == label
    )


# KS-131 --------------------------------------------------------------------------


def test_small_carry_on_summary_precedes_products_and_airline_details_follow(
    outputs, roots
) -> None:
    html, root = outputs[SMALL], roots[SMALL]
    assert (
        html.index('id="carry-on-summary"')
        < html.index('id="ps-choose"')
        < html.index('id="specs"')
        < html.index('id="carry-on-rules"')
        < html.index('id="purchase-check"')
    )
    summary = by_id(root, "carry-on-summary")
    shortcuts = [n for n in summary.find(tag="nav") if n.has("sc-shortcuts")]
    assert len(shortcuts) == 1
    targets = [a.attrs.get("href") for a in shortcuts[0].find(tag="a")]
    # Shortcuts follow the page order (review W4b: the table link skipped #ps-choose).
    assert targets == ["#ps-choose", "#specs", "#carry-on-rules", "#carry-on-fit"], targets
    rules = by_id(root, "carry-on-rules")
    assert not [n for n in ancestors(rules) if n.tag == "details"]
    heading = rules.find(tag="h2")[0]
    assert visible_text(heading).strip() == "航空会社別の詳細条件"
    table = [t for t in rules.find(tag="table") if t.has("sc-airline-table")]
    assert len(table) == 1
    assert len(table[0].find(tag="tbody")[0].find(tag="tr")) == 9


def test_small_carry_on_summary_states_each_scope_as_the_table_does(roots) -> None:
    text = visible_text(by_id(roots[SMALL], "carry-on-summary"))
    # Round 3: the heading names the carriers instead of claiming 国内線 for six,
    # three of which state no route on their own page.
    assert "JAL・ANA（100席以上の便）・スカイマーク・AIRDO・ソラシドエア・スターフライヤー" in text
    assert "国内線（JAL・ANAは100席以上）" not in text
    assert "100席以上（JAL・ANA・スカイマーク" not in text
    assert "3辺それぞれ55×40×25cm以内かつ3辺合計115cm以内" in text
    # AIRDO shows each side only (re-fetched 2026-09-16); Skymark states no route scope.
    item = by_id(roots[SMALL], "carry-on-summary").find(tag="li")[0]
    domestic = visible_text(item)
    # The heading lists the carriers; the 115cm sentence below it must not.
    sentences = domestic[len(visible_text(item.find(tag="strong")[0])) :]
    assert "スカイマーク・AIRDO" not in sentences.split("。")[0]
    assert "AIRDOは各辺55×40×25cm以内だけを示し、3辺合計の上限は示していません" in domestic
    assert "スカイマーク・AIRDO・ソラシドエアの公式ページには対象便の記載がありません" in domestic
    assert "高さ56×幅36×奥行23cmまで" in text
    assert "1個10kg以内" in text
    assert (
        "一部のエコノミークラス運賃・ビジネスクラス運賃・プラス7kgのオプション" in text
    )
    # Round-6 review: the pages omit the axis words, which is not the same as
    # leaving the correspondence unknowable -- AIRDO draws it in its size figure.
    assert "各辺の数値に高さ・幅・奥行の語を付けていません" in text
    assert "どの数値が高さ・幅・奥行かは書いていません" not in text
    assert "45×35×20cm以内・3辺合計100cm以内" in text


def test_small_carry_on_airline_table_matches_the_rule_records(roots, catalog) -> None:
    rules = article(catalog, SMALL)["carry_on_fit"]["rules"]
    table = [
        t
        for t in by_id(roots[SMALL], "carry-on-rules").find(tag="table")
        if t.has("sc-airline-table")
    ][0]
    rows = table.find(tag="tbody")[0].find(tag="tr")
    assert len(rows) == len(rules) == 9
    caption = visible_text(table.find(tag="caption")[0])
    # Every row was re-fetched on the same day, so the caption states one date.
    assert {rule["checked_on"] for rule in rules} == {"2026-09-16"}
    assert caption.startswith("2026年9月16日確認"), caption
    assert "再確認" not in caption
    for row, rule in zip(rows, rules, strict=True):
        head = row.find(tag="th")[0]
        cells = row.find(tag="td")
        assert [a.attrs["href"] for a in head.find(tag="a")] == [
            link["url"] for link in rule["carrier_links"]
        ]
        assert visible_text(head.find(tag="small")[0]) == rule["scope"]
        size = visible_text(cells[0])
        if rule["edges_cm"]:
            assert size.startswith("×".join(str(e) for e in rule["edges_cm"]) + "cm")
        if rule["sum_cm"] is not None:
            assert f"3辺合計：{rule['sum_cm']}cm" in size
        else:
            assert "各辺で規定" in size
        assert (
            visible_text(cells[1].find(tag="strong")[0])
            == f"{rule['total_weight_kg']}kg"
        )
        assert f"合計{rule['pieces']}個" in visible_text(cells[1])


def test_airdo_record_follows_the_refetched_page(roots, catalog) -> None:
    rules = {r["rule_id"]: r for r in article(catalog, SMALL)["carry_on_fit"]["rules"]}
    airdo = rules["airdo"]
    assert airdo["edges_cm"] == [55, 40, 25] and airdo["sum_cm"] is None
    assert airdo["checked_on"] == "2026-09-16"
    assert "carry-on-baggage02-2609.png" in airdo["locator"]
    assert "身の回りの品のサイズは2026年10月1日より運用開始" in airdo["locator"]
    assert "国内線" not in rules["skymark"]["scope"]
    section = by_id(roots[SMALL], "carry-on-rules")
    row = [
        tr
        for tr in section.find(tag="tr")
        if any(a.attrs.get("href") == airdo["carrier_links"][0]["url"] for a in tr.find(tag="a"))
    ]
    assert len(row) == 1
    assert "2026年10月1日から40×30×20cm以内" in visible_text(row[0])
    assert "AIRDOは2026年10月1日から" in visible_text(section)


def test_wheel_inclusion_is_attributed_only_to_carriers_that_state_it(
    roots, catalog
) -> None:
    rules = article(catalog, SMALL)["carry_on_fit"]["rules"]
    named: list[str] = []
    silent: list[str] = []
    for rule in rules:
        for link in rule["carrier_links"]:
            label = link["label"].replace("ジェットスター・ジャパン（GK）", "ジェットスター")
            target = named if rule["dims_include_wheels"] is True else silent
            if label not in named and label not in silent:
                target.append(label)
    text = visible_text(by_id(roots[SMALL], "carry-on-rules"))
    assert "寸法はキャスター（車輪）やハンドルを含めて測ります" not in text
    assert "・".join(named) + "は、キャスター（車輪）やハンドルも寸法に含むと明記しています" in text
    assert "・".join(silent) + "は、この記載を公式ページで確認できていません" in text


# KS-201b -------------------------------------------------------------------------


def test_limit_excess_is_measured_edge_by_edge_and_on_the_sum() -> None:
    excess = purchase_support.carry_on_excess
    d = Decimal
    assert excess((d(55), d(40), d(23)), (d(55), d(40), d(25)), d(115)) == [
        ("3辺合計", d(3))
    ]
    assert excess((d(55), d("35.5"), d(29)), (d(55), d(40), d(25)), d(115)) == [
        ("奥行", d(4)),
        ("3辺合計", d("4.5")),
    ]
    assert excess((d(54), d(37), d(24)), (d(56), d(36), d(23)), None) == [
        ("幅", d(1)),
        ("奥行", d(1)),
    ]
    assert excess((d(55), d(36), d(23)), (d(56), d(36), d(23)), None) == []
    assert excess((d(55), d(40), d(20)), None, d(115)) == []


def test_unknown_wheel_inclusion_switches_to_the_expansion_question(
    roots, catalog
) -> None:
    data = article(catalog, SMALL)["carry_on_fit"]
    luggage = data["luggage"]
    assert [entry["product_id"] for entry in luggage] == article(catalog, SMALL)[
        "product_ids"
    ]
    unknown = [e for e in luggage if e["dims_include_wheels"] is None]
    assert len(unknown) * 2 > len(luggage)
    assert data["question"] == "expansion_excess"
    matrix = by_id(roots[SMALL], "carry-on-fit")
    assert matrix.attrs.get("data-raos-analysis") == "carry-on-fit"
    assert FIT_HEADING in visible_text(matrix)
    assert "範囲内" not in visible_text(matrix)
    intro = visible_text(matrix.find(tag="p")[0])
    # Two makers state the outer size includes wheels; Samsonite states it only for height.
    assert (
        "外寸に車輪を含むと公式に書いているのは、12モデル中2モデル"
        "（PROTECA エアロフレックスDX2 01521・ACE クレスタ 06316）です" in intro
    )
    assert (
        "Samsoniteは、商品ページの仕様欄の記載（ページ上には表示されない注記）で、"
        "高さに車輪を含むとだけ書いています" in intro
    )
    assert "実物も超えます" not in intro
    assert "「約」" in intro
    rules_section = by_id(roots[SMALL], "carry-on-rules")
    assert matrix in list(rules_section.walk())


def test_expansion_matrix_reports_each_model_against_each_limit_group(roots) -> None:
    matrix = by_id(roots[SMALL], "carry-on-fit")
    table = matrix.find(tag="table")[0]
    heads = [
        visible_text(th).strip() for th in table.find(tag="thead")[0].find(tag="th")
    ]
    assert len(heads) == 6, heads
    assert heads[2].startswith(
        "JAL・ANA・スカイマーク・ソラシドエア・スターフライヤー（JAL・ANAは100席以上）"
    )
    assert heads[3].startswith("AIRDO") and heads[3].endswith("55×40×25cm")
    assert heads[4].startswith("Peach")
    assert heads[5].startswith("ジェットスター・ジャパン（GK）")
    rows = {
        row.attrs["data-fit-product-id"]: [
            visible_text(c).strip() for c in row.find(tag="td")
        ]
        for row in table.find(tag="tbody")[0].find(tag="tr")
    }
    assert len(rows) == 12
    unknown = "拡張仕様は未確認"
    no_record = "拡張の記載なし（8/29確認）"
    expected = {
        "PRD-PROTECA-AEROFLEX-DX2-01521": [unknown] * 5,
        "PRD-SAMSONITE-C-LITE-CS2-09007": [
            "55×40×23cm・合計118cm",
            "拡張すると超過（3辺合計が3cm）",
            "拡張時の数値は上限内（持ち込めるかは未判定）",
            "拡張すると超過（3辺合計が3cm）",
            "通常時から超過（幅が4cm）",
        ],
        "PRD-AMERICAN-TOURISTER-APPLITE-4-QJ6-68002": [
            "55×35×28cm・合計118cm",
            "拡張すると超過（奥行が3cm・3辺合計が3cm）",
            "拡張すると超過（奥行が3cm）",
            "拡張すると超過（3辺合計が3cm）",
            "通常時から超過（奥行が2cm）",
        ],
        "PRD-SMALL-CARRY-ON-SUITCASE-RIMOWA-82353704": [unknown] * 4
        + ["通常時から超過（幅が1cm）"],
        "PRD-FREQUENTER-LIEVE-1-250": [unknown] * 5,
        "PRD-SMALL-CARRY-ON-SUITCASE-DELSEY-D00167680106": [unknown] * 4
        + ["通常時から超過（奥行が約2cm）"],
        "PRD-SMALL-CARRY-ON-SUITCASE-MUJI-76431312": [unknown] * 4
        + ["通常時から超過（幅が約1cm・奥行が約1cm）"],
        "PRD-ACE-CRESTA-06316": [
            "55×35×29cm・合計119cm",
            "拡張すると超過（奥行が4cm・3辺合計が4cm）",
            "拡張すると超過（奥行が4cm）",
            "拡張すると超過（3辺合計が4cm）",
            "通常時から超過（奥行が2cm）",
        ],
        "PRD-INNOVATOR-INV50": [
            "拡張なし（2026年8月29日の確認値）",
            no_record,
            no_record,
            no_record,
            "通常時から超過（奥行が2cm）",
        ],
        "PRD-BERMAS-INTER-CITY-II-60561": [
            "拡張なし（2026年8月29日の確認値）",
            no_record,
            no_record,
            no_record,
            "通常時から超過（奥行が2cm）",
        ],
        "PRD-SMALL-CARRY-ON-SUITCASE-LEGEND-WALKER-5208-49": [
            "55×37×約30cm・合計約122cm",
            "拡張すると超過（奥行が約5cm・3辺合計が約7cm）",
            "拡張すると超過（奥行が約5cm）",
            "拡張すると超過（3辺合計が約7cm）",
            "通常時から超過（幅が1cm）",
        ],
        "PRD-SMALL-CARRY-ON-SUITCASE-TUMI-0228793DTX": [
            "55×35.5×29cm・合計119.5cm",
            "拡張すると超過（奥行が4cm・3辺合計が4.5cm）",
            "拡張すると超過（奥行が4cm）",
            "拡張すると超過（3辺合計が4.5cm）",
            "通常時から超過（奥行が1cm）",
        ],
    }
    assert set(expected) == set(rows)
    for pid, cells in expected.items():
        assert rows[pid] == cells, pid


def test_fit_matrix_notes_state_the_approximation_and_side_naming(roots) -> None:
    text = visible_text(by_id(roots[SMALL], "carry-on-rules"))
    assert "「約」付きの公表値から計算した超過量には「約」を付けています" in text
    assert (
        "軸名が公式に無い型番は、長い辺から順に航空会社の上限と比べています（辺の名前は編集部の割り当て）"
        in text
    )
    assert "表記の順に高さ・幅・奥行を当てはめて比べています" not in text


def test_fit_matrix_scrolls_sideways_instead_of_squeezing_columns(roots) -> None:
    table = by_id(roots[SMALL], "carry-on-fit").find(tag="table")[0]
    assert table.has("sc-fit-table")
    assert not table.has("ks-readable-table")
    assert table.parent is not None and table.parent.has("sc-table-scroll")
    assert not table.parent.has("ks-readable-scroll")
    # One scroll region only: a nested .ps-table-scroll would scroll (and squeeze) instead.
    assert not [n for n in ancestors(table) if n.has("ps-table-scroll")]
    assert len([n for n in ancestors(table) if n.attrs.get("role") == "region"]) == 1
    css = THEME_CSS.read_text(encoding="utf-8")
    rule = re.search(
        r"\.small-carry-on-comparison table\.sc-fit-table \{([^}]*)\}", css
    )
    assert rule, "sc-fit-table rule"
    width = re.search(r"min-width:(\d+)rem", rule.group(1).replace(" ", ""))
    assert width and 44 <= int(width.group(1)) <= 52
    sticky = re.search(
        r"\.small-carry-on-comparison table\.sc-fit-table :is\(thead th:first-child, tbody th\) \{([^}]*)\}",
        css,
    )
    assert sticky, "sticky first column"
    assert "position:sticky" in sticky.group(1).replace(" ", "")
    assert "left:0" in sticky.group(1).replace(" ", "")


def test_readable_tables_leaves_scroll_tables_alone() -> None:
    markup = (
        '<div class="wrap"><table data-ks-table-layout="scroll"><thead><tr><th>A</th>'
        "<th>B</th></tr></thead><tbody><tr><th>x</th><td>1</td></tr></tbody></table></div>"
    )
    assert readable_tables(markup) == markup
    plain = markup.replace(' data-ks-table-layout="scroll"', "")
    assert "ks-readable-table" in readable_tables(plain)


def test_fit_records_match_the_comparison_table(roots, catalog) -> None:
    specs = by_id(roots[SMALL], "specs")
    for entry in article(catalog, SMALL)["carry_on_fit"]["luggage"]:
        row = [
            r
            for r in specs.find(tag="tr")
            if r.attrs.get("data-product-id") == entry["product_id"]
        ]
        assert len(row) == 1, entry["product_id"]
        groups = row[0].find(cls="ps-matrix-spec-group")
        near = "約" if entry.get("dims_approximate") else ""
        dims = "×".join(
            near + format(Decimal(str(entry[k])).normalize(), "f")
            for k in ("height_cm", "width_cm", "depth_cm")
        )
        normal = visible_text(groups[0]).replace("通常時の外寸・本体重量・容量", "").strip()
        assert normal.startswith(dims + "cm"), entry["product_id"]
        total = format(Decimal(str(entry["sum_cm"])).normalize(), "f")
        assert f"合計 {near}{total}cm" in normal, entry["product_id"]
        expanded = entry["expanded"]
        if isinstance(expanded, dict) and expanded.get("state") == "known":
            deep = near or ("約" if expanded.get("approximate") else "")
            wide = "×".join(
                [
                    near + format(Decimal(str(entry["height_cm"])).normalize(), "f"),
                    near + format(Decimal(str(entry["width_cm"])).normalize(), "f"),
                    deep + format(Decimal(str(expanded["depth_cm"])).normalize(), "f"),
                ]
            )
            assert wide + "cm" in visible_text(groups[2]), entry["product_id"]


def test_published_approximate_sizes_keep_their_qualifier(catalog) -> None:
    luggage = {
        e["product_id"]: e for e in article(catalog, SMALL)["carry_on_fit"]["luggage"]
    }
    flagged = {pid for pid, e in luggage.items() if e.get("dims_approximate")}
    assert flagged == {
        "PRD-SMALL-CARRY-ON-SUITCASE-MUJI-76431312",
        "PRD-SMALL-CARRY-ON-SUITCASE-DELSEY-D00167680106",
    }
    for pid in flagged:
        assert "約" in luggage[pid]["locator"], pid
    legend = luggage["PRD-SMALL-CARRY-ON-SUITCASE-LEGEND-WALKER-5208-49"]["expanded"]
    assert legend["approximate"] is True and "約7cm" in legend["basis"]
    samsonite = luggage["PRD-SAMSONITE-C-LITE-CS2-09007"]
    assert samsonite["wheels_scope"] == "height" and samsonite["maker"] == "Samsonite"


def test_fit_slot_requires_its_records(catalog) -> None:
    data = json.loads(json.dumps(article(catalog, SMALL)))
    template = (TEMPLATES / f"{SMALL}.html").read_text(encoding="utf-8")
    del data["carry_on_fit"]
    with pytest.raises(ValueError, match="PURCHASE_CARRY_ON_FIT"):
        purchase_support.bind_carry_on_fit(template, data, catalog)


# Corrections 2-4, 13-14 ------------------------------------------------------------


def test_small_carry_on_choose_intro_makes_no_fit_claim(roots) -> None:
    intro = by_id(roots[SMALL], "ps-choose").find(tag="p")[0]
    assert visible_text(intro) == (
        "乗る便の条件は上の要点と下の表で確かめたうえで、必要な機能に近い行から選んでください。"
        "ジェットスターの寸法を超える型番は下の表に示しています。"
    )
    assert "収ま" not in visible_text(intro)


def test_small_carry_on_rows_keep_the_official_qualifiers(roots, catalog) -> None:
    applite = visible_text(by_id(roots[SMALL], "product-applite-qj6-68002"))
    assert "約2.1kg" in applite and "容量 約38L" in applite and "約40L" in applite
    assert "仕様確認：2026-09-13（本体重量・容量の「約」・開閉方法は2026-09-16）" in applite
    muji_row = visible_text(by_id(roots[SMALL], "product-muji-76431312"))
    assert "約54×約37×約24cm" in muji_row
    delsey = visible_text(by_id(roots[SMALL], "product-delsey-d00167680106"))
    assert "約55×約35×約25cm" in delsey
    legend = visible_text(by_id(roots[SMALL], "product-legend-walker-5208-49"))
    assert "55×37×約30cm" in legend and "3辺合計約122cm" in legend
    assert "本体は約2.7kg" in visible_text(by_id(roots[SMALL], "product-lieve-1-250"))
    muji = visible_text(by_id(roots[SMALL], "product-muji-76431312"))
    assert "約2.9kg" in muji and "約36L" in muji and "最大積載量（目安）" in muji
    assert "転用しません" not in muji
    applite_id = "PRD-AMERICAN-TOURISTER-APPLITE-4-QJ6-68002"
    lieve_id = "PRD-FREQUENTER-LIEVE-1-250"
    assert fact(catalog, applite_id, "本体重量") == "約2.1kg"
    assert fact(catalog, applite_id, "容量") == "約38L拡張時約40L"
    assert fact(catalog, lieve_id, "本体重量") == "約2.7kg"
    assert fact(catalog, lieve_id, "容量") == "約33L"
    for pid in (applite_id, lieve_id):
        entry = product(catalog, pid)
        prose = json.dumps(
            [entry["lead"], entry["fit"], entry["avoid"]], ensure_ascii=False
        )
        assert not re.search(
            r"(?<!約)(?<![0-9.])(?:2\.1kg|2\.7kg|38L|33L|40L|600g)", prose
        ), pid


def test_small_carry_on_weight_order_places_muji_after_delsey(outputs, catalog) -> None:
    html = outputs[SMALL]
    assert (
        html.index('id="product-delsey-d00167680106"')
        < html.index('id="product-muji-76431312"')
        < html.index('id="product-cresta-06316"')
    )
    assert "重量未確認は末尾" not in html
    ids = article(catalog, SMALL)["product_ids"]
    assert (
        ids.index("PRD-SMALL-CARRY-ON-SUITCASE-MUJI-76431312")
        == ids.index("PRD-SMALL-CARRY-ON-SUITCASE-DELSEY-D00167680106") + 1
    )


def test_small_carry_on_scope_notes_use_reader_wording(roots) -> None:
    text = visible_text(roots[SMALL])
    assert "同ブランド内" not in text
    assert "同じメーカーのモデル間の違い" in text
    assert "INV50の基本仕様は2026年9月13日に公式ページで確認した値です" in text


def test_production_wording_is_a_banned_token() -> None:
    for phrase in ("担当記事で照合", "公式検索本文", "直接取得は失敗しました"):
        assert emergency.INTERNAL_TOKENS.search(phrase), phrase


def test_built_bodies_have_no_internal_tokens(roots) -> None:
    leaks = []
    for slug, root in roots.items():
        text = visible_text(root)
        for match in emergency.INTERNAL_TOKENS.finditer(text):
            leaks.append((slug, text[max(0, match.start() - 30) : match.end() + 30]))
    assert leaks == []


# Correction 5 ----------------------------------------------------------------------

AXIS_LIMIT = re.compile(
    r"(?:幅|奥行|高さ)[0-9.]+cm以内|幅[0-9.]+×奥行[0-9.]+×高さ[0-9.]+cm以内"
)


def test_suitcase_sources_do_not_assign_axes_to_unlabelled_airline_limits(
    catalog,
) -> None:
    found = []
    for key in (*SUITCASE_KEYS, SMALL):
        text = (TEMPLATES / f"{key}.html").read_text(encoding="utf-8")
        found += [(key, m.group(0)) for m in AXIS_LIMIT.finditer(text)]
    for entry in catalog["articles"]:
        if entry["slug"] in (*SUITCASE_KEYS, SMALL):
            text = json.dumps(entry, ensure_ascii=False)
            found += [(entry["slug"], m.group(0)) for m in AXIS_LIMIT.finditer(text)]
    assert found == []


# An airline limit ("…cm以内") must not name one side; maker sizes such as
# "幅35×奥行29×高さ55cm・3辺合計119cm" keep the maker's own labels.
SIDE_BEFORE_SUM = re.compile(r"(?:幅|奥行|高さ)[0-9.]+cm・3辺合計[0-9.]+cm以内")


def test_suitcase_sources_do_not_name_one_side_before_an_unlabelled_sum(catalog) -> None:
    found = []
    for key in (*SUITCASE_KEYS, SMALL):
        text = (TEMPLATES / f"{key}.html").read_text(encoding="utf-8")
        found += [(key, m.group(0)) for m in SIDE_BEFORE_SUM.finditer(text)]
    assert found == []
    front = (TEMPLATES / "front-open-carry-on-suitcase-with-stopper.html").read_text(
        encoding="utf-8"
    )
    assert "45×35×20cm以内・3辺合計100cm以内を基準にした" in front


def test_small_carry_on_correction_note_names_only_what_changed() -> None:
    rows = {
        r["article_key"]: r
        for r in json.loads(LEDGER.read_text(encoding="utf-8"))["articles"]
    }
    notes = [
        e for e in rows[SMALL]["listing"]["change_log"] if e["date"] == "2026-09-16"
    ]
    assert len(notes) == 1
    summary = notes[0]["summary"]
    assert "APPLITE 4.0とLIEVEの本体重量・容量" not in summary
    assert "LIEVEの注記の本体重量" in summary
    assert "無印良品とDELSEYの外寸" in summary
    # The /updates/ line describes the table the way the table itself is headed.
    assert "拡張すると航空会社の上限を超える型番の表" not in summary
    assert "航空会社の上限を超える型番（通常時・拡張時）の表" in summary
    # 553's Solaseed and AIRDO rows changed today as well, so the line names them.
    assert "スカイマーク・AIRDO・ソラシドエアの対象便" in summary


# KS-014 ----------------------------------------------------------------------------


def test_suitcase_articles_end_with_a_route_to_the_broad_comparison(roots) -> None:
    for key in SUITCASE_KEYS:
        ending = by_id(roots[key], "ks-next-read")
        assert SMALL_HREF in [a.attrs.get("href") for a in ending.find(tag="a")], key


def test_suitcase_next_questions_are_live() -> None:
    rows = {
        r["article_key"]: r
        for r in json.loads(LEDGER.read_text(encoding="utf-8"))["articles"]
    }
    for key in SUITCASE_KEYS:
        question = rows[key]["reader_role"]["next_question"]
        assert question["target"] == SMALL
        assert question["status"] == "live", key


# Portfolio and hub sources ---------------------------------------------------------


def test_hub_sources_describe_the_ace_article_without_brand_wording() -> None:
    for path in (
        "changes/wordpress-direct-publish-v1/reader-sync/tools/hub_pages_20260912.py",
        "changes/wordpress-direct-publish-v1/reader-sync/site-map.v2.json",
    ):
        assert "ブランド内" not in (ROOT / path).read_text(encoding="utf-8"), path


# Review round 2: the two suitcase articles must state one set of airline conditions ----


def airline_table(root: Element, css_class: str) -> Element:
    found = [
        t for t in by_id(root, "carry-on-rules").find(tag="table") if t.has(css_class)
    ]
    assert len(found) == 1, css_class
    return found[0]


def rule_row(root: Element, url: str) -> Element:
    rows = [
        tr
        for tr in by_id(root, "carry-on-rules").find(tag="tr")
        if any(a.attrs.get("href") == url for a in tr.find(tag="a"))
    ]
    assert len(rows) == 1, url
    return rows[0]


def test_lightweight_airline_table_matches_the_rule_records(roots, catalog) -> None:
    rules = article(catalog, SMALL)["carry_on_fit"]["rules"]
    table = airline_table(roots[LIGHT], "lw-airline-table")
    rows = table.find(tag="tbody")[0].find(tag="tr")
    assert len(rows) == len(rules) == 9
    assert {rule["checked_on"] for rule in rules} == {"2026-09-16"}
    caption = visible_text(table.find(tag="caption")[0])
    assert caption.startswith("2026年9月16日確認"), caption
    for row, rule in zip(rows, rules, strict=True):
        head = row.find(tag="th")[0]
        cells = row.find(tag="td")
        assert [a.attrs["href"] for a in head.find(tag="a")] == [
            link["url"] for link in rule["carrier_links"]
        ]
        assert visible_text(head.find(tag="small")[0]) == rule["scope"]
        size = visible_text(cells[0])
        if rule["edges_cm"]:
            assert size.startswith("×".join(str(e) for e in rule["edges_cm"]) + "cm")
        if rule["sum_cm"] is not None:
            assert f"3辺合計：{rule['sum_cm']}cm" in size, rule["rule_id"]
        else:
            assert "各辺で規定" in size and "3辺合計" not in size, rule["rule_id"]
        assert (
            visible_text(cells[1].find(tag="strong")[0])
            == f"{rule['total_weight_kg']}kg"
        )
        assert f"合計{rule['pieces']}個" in visible_text(cells[1])


def test_both_suitcase_articles_state_the_same_airline_conditions(roots, catalog) -> None:
    rules = {r["rule_id"]: r for r in article(catalog, SMALL)["carry_on_fit"]["rules"]}
    for rule_id in ("airdo", "skymark", "solaseed-air", "starflyer"):
        rule = rules[rule_id]
        url = rule["carrier_links"][0]["url"]
        scopes = {
            slug: visible_text(
                rule_row(roots[slug], url).find(tag="th")[0].find(tag="small")[0]
            )
            for slug in (LIGHT, SMALL)
        }
        assert scopes[LIGHT] == scopes[SMALL] == rule["scope"], rule_id
    airdo = visible_text(rule_row(roots[LIGHT], rules["airdo"]["carrier_links"][0]["url"]))
    assert "各辺で規定" in airdo and "3辺合計" not in airdo
    assert "2026年10月1日から40×30×20cm以内" in airdo


def test_lightweight_attributes_wheel_inclusion_only_where_it_is_stated(
    roots, catalog
) -> None:
    rules = article(catalog, SMALL)["carry_on_fit"]["rules"]
    named: list[str] = []
    silent: list[str] = []
    for rule in rules:
        for link in rule["carrier_links"]:
            label = link["label"].replace("ジェットスター・ジャパン（GK）", "ジェットスター")
            target = named if rule["dims_include_wheels"] is True else silent
            if label not in named and label not in silent:
                target.append(label)
    text = visible_text(by_id(roots[LIGHT], "carry-on-rules"))
    assert "外寸は車輪・ハンドル・ポケットを含む上限" not in text
    assert "・".join(named) + "は、キャスター（車輪）やハンドルも寸法に含むと明記しています" in text
    assert "・".join(silent) + "は、この記載を公式ページで確認できていません" in text
    assert "AIRDOは2026年10月1日から" in text


def test_every_airline_locator_quotes_its_official_page(catalog) -> None:
    rules = {r["rule_id"]: r for r in article(catalog, SMALL)["carry_on_fit"]["rules"]}
    for rule_id, rule in rules.items():
        assert rule["checked_on"] == "2026-09-16", rule_id
        assert "記事表の確認値" not in rule["locator"], rule_id
        assert "「" in rule["locator"] and "」" in rule["locator"], rule_id
    assert "3辺の和が115cm以内" in rules["solaseed-air"]["locator"]
    assert "3辺の合計が115cm以内（55cm×40cm×25cm以内）" in rules["starflyer"]["locator"]
    # Neither page prints a route label for the rule, as Skymark's does not.
    assert rules["solaseed-air"]["scope"] == "対象便は公式ページに記載なし"
    assert rules["starflyer"]["scope"] == "国内線"


def test_fit_matrix_heading_covers_normal_and_expanded_excess(outputs, roots) -> None:
    matrix = by_id(roots[SMALL], "carry-on-fit")
    assert visible_text(matrix.find(tag="h3")[0]).strip() == FIT_HEADING
    assert "拡張すると上限を超える型番" not in outputs[SMALL]
    shortcuts = [
        n
        for n in by_id(roots[SMALL], "carry-on-summary").find(tag="nav")
        if n.has("sc-shortcuts")
    ]
    labels = {
        a.attrs.get("href"): visible_text(a).strip() for a in shortcuts[0].find(tag="a")
    }
    assert labels["#carry-on-fit"] == FIT_HEADING
    regions = [n for n in matrix.walk() if n.attrs.get("role") == "region"]
    assert len(regions) == 1
    assert regions[0].attrs.get("aria-label") == FIT_HEADING + "の表"


def test_fit_intro_names_the_two_models_and_the_unknown_remainder(roots, catalog) -> None:
    luggage = article(catalog, SMALL)["carry_on_fit"]["luggage"]
    unknown = sum(1 for e in luggage if e["dims_include_wheels"] is None)
    intro = visible_text(by_id(roots[SMALL], "carry-on-fit").find(tag="p")[0])
    assert f"Samsoniteを除く残り{unknown}モデルは車輪を含むか確認できない" in intro
    assert "残りは車輪を含むか" not in intro


def test_muji_row_records_the_material_from_the_same_official_table(roots) -> None:
    row = visible_text(by_id(roots[SMALL], "product-muji-76431312"))
    assert "素材：ポリカーボネート" in row
    assert "素材：現行商品番号で未確認" not in row
    assert "素材の詳細は確認待ち" not in row
    assert "本体重量・最大積載量・素材・開閉方法は2026-09-16" in row


def test_ks_201_record_states_the_count_the_article_publishes() -> None:
    status = json.loads(
        (ROOT / "changes/ks-integrated-20260915/status.v1.json").read_text(
            encoding="utf-8"
        )
    )
    text = status["items"]["KS-201"]["status"]
    assert "12 モデル中 2" in text, text
    assert "12 モデル中 3" not in text


def test_lightweight_airline_correction_is_recorded_in_the_ledger() -> None:
    rows = {
        r["article_key"]: r
        for r in json.loads(LEDGER.read_text(encoding="utf-8"))["articles"]
    }
    notes = [
        e for e in rows[LIGHT]["listing"]["change_log"] if e["date"] == "2026-09-16"
    ]
    assert len(notes) == 1
    assert notes[0]["kind"] == "correction"
    assert "AIRDO" in notes[0]["summary"]
    assert "訂正" not in notes[0]["summary"]


# --- W4b review round 4 (minors). Each test below failed before its source edit. ---


def test_every_airline_scope_is_backed_by_its_locator(catalog) -> None:
    """No rule may assert a route the locator records as absent from the page."""
    absent = "対象便は公式ページに記載なし"
    for rule in article(catalog, SMALL)["carry_on_fit"]["rules"]:
        scope, locator = rule["scope"], rule["locator"]
        records_absence = "対象便" in locator and "記載" in locator and "なし" in locator
        if records_absence or "国内線の範囲の記載は確認できていない" in locator:
            assert scope == absent, (rule["rule_id"], scope)
        if scope == absent:
            assert "記載" in locator, rule["rule_id"]


def test_airdo_scope_matches_the_other_carriers_without_a_stated_route(catalog) -> None:
    rules = {r["rule_id"]: r for r in article(catalog, SMALL)["carry_on_fit"]["rules"]}
    absent = "対象便は公式ページに記載なし"
    # Re-fetched 2026-09-16: the page's only 「国内線」 is the 新千歳空港 terminal in the nav.
    assert rules["airdo"]["scope"] == absent
    assert rules["airdo"]["scope"] == rules["skymark"]["scope"] == rules["solaseed-air"]["scope"]
    assert "対象便" in rules["airdo"]["locator"]
    # Starflyer keeps 国内線 because its own heading states it.
    assert rules["starflyer"]["scope"] == "国内線"
    assert "機内持ち込み手荷物（国内線）" in rules["starflyer"]["locator"]


def test_summary_names_every_carrier_whose_page_omits_the_route(roots, catalog) -> None:
    rules = article(catalog, SMALL)["carry_on_fit"]["rules"]
    absent = "対象便は公式ページに記載なし"
    names = [
        link["label"]
        for rule in rules
        if rule["scope"] == absent
        for link in rule["carrier_links"]
    ]
    assert names == ["スカイマーク", "AIRDO", "ソラシドエア"]
    item = by_id(roots[SMALL], "carry-on-summary").find(tag="li")[0]
    domestic = visible_text(item)
    assert "・".join(names) + "の公式ページには対象便の記載がありません" in domestic
    # The 115cm group must still not swallow AIRDO, which publishes no 3-side total.
    # The heading now lists the carriers, so the check runs on the sentences below it.
    heading = visible_text(item.find(tag="strong")[0])
    first = domestic[len(heading) :].split("。")[0]
    assert "AIRDO" not in first, first


def test_axis_note_names_every_carrier_without_official_axis_names(roots, catalog) -> None:
    rules = article(catalog, SMALL)["carry_on_fit"]["rules"]
    expected: list[str] = []
    for rule in rules:
        if not rule["edges_cm"] or rule["edge_axes"]:
            continue
        for link in rule["carrier_links"]:
            if link["label"] not in expected:
                expected.append(link["label"])
    assert expected == ["JAL", "ANA", "スカイマーク", "AIRDO", "ソラシドエア", "スターフライヤー"]
    # The claim is about the wording on those pages, not about whether a reader
    # can tell the edges apart: AIRDO's size figure does assign each number to an
    # arrow, so 「どの数値が…かは書いていません」 overstated it (round-6 review).
    sentence = "・".join(expected) + "は、各辺の数値に高さ・幅・奥行の語を付けていません"
    body = roots[SMALL]
    notes = [visible_text(n) for n in body.find(tag="p") if n.has("sc-note")]
    carrying = [n for n in notes if "高さ・幅・奥行の語を付けていません" in n]
    assert len(carrying) == 2, len(carrying)
    for note in carrying:
        assert sentence in note, note
        # The old short list and the withdrawn claim must be gone from both notes.
        assert "JAL・ANA・スカイマークは3辺の数値だけを示し" not in note
        assert "どの数値が高さ・幅・奥行かは書いていません" not in note
        assert "AIRDOはサイズ図で55cmを縦、40cmを横、25cmを奥行の矢印に示しています" in note


OPENING_WORDS = (
    "開き",
    "開閉",
    "ファスナー",
    "オープン",
    "オープニング",
    "室収納",
    "確認中",
    "未確認",
)


def test_every_comparison_row_states_its_opening_or_says_it_is_unverified(
    roots, outputs
) -> None:
    """The sc-note promises the opening (or 確認中／未確認) in 使いやすさ・詳細."""
    promise = [
        visible_text(n)
        for n in roots[SMALL].find(tag="p")
        if n.has("sc-note") and "使いやすさ・詳細" in visible_text(n)
    ]
    assert len(promise) == 1
    assert "公式表記で確認できていないモデルは「確認中」「未確認」と表示しています" in promise[0]
    rows = re.findall(r'<tr id="product-([^"]+)".*?</tr>', outputs[SMALL], re.S)
    assert len(rows) == 12, len(rows)
    missing: list[str] = []
    for key, row in zip(
        rows, re.findall(r'<tr id="product-[^"]+".*?</tr>', outputs[SMALL], re.S), strict=True
    ):
        group = re.search(
            r'<div class="ps-matrix-spec-group"><span[^>]*>使いやすさ・詳細</span>(.*?)(?:<details>|</div>)',
            row,
            re.S,
        )
        assert group, key
        label = re.sub(r"<[^>]+>", "", group.group(1))
        if not any(word in label for word in OPENING_WORDS):
            missing.append(f"{key}: {label}")
    assert not missing, missing


def test_muji_opening_follows_the_official_spec_table(outputs) -> None:
    row = re.search(
        r'<tr id="product-muji-76431312".*?</tr>', outputs[SMALL], re.S
    )
    assert row
    group = re.search(
        r'<div class="ps-matrix-spec-group"><span[^>]*>使いやすさ・詳細</span>(.*?)<details>',
        row.group(0),
        re.S,
    )
    assert group
    label = re.sub(r"<[^>]+>", "", group.group(1))
    # 「仕様・サイズ」タブ 商品仕様表: 開閉方法／ファスナー — the same table W4b read for 本体重量.
    assert "ファスナー" in label, label
    assert "開閉構造は確認中" not in label


def test_wheel_height_only_note_says_where_the_text_sits(roots) -> None:
    text = visible_text(by_id(roots[SMALL], "carry-on-fit"))
    assert "Samsoniteは、高さに車輪を含むとだけ書いています" not in text
    assert (
        "Samsoniteは、商品ページの仕様欄の記載（ページ上には表示されない注記）で、"
        "高さに車輪を含むとだけ書いています" in text
    )


def test_small_carry_on_correction_note_names_the_material(roots) -> None:
    rows = {
        r["article_key"]: r
        for r in json.loads(LEDGER.read_text(encoding="utf-8"))["articles"]
    }
    summary = [
        e for e in rows[SMALL]["listing"]["change_log"] if e["date"] == "2026-09-16"
    ][0]["summary"]
    # The body moved 無印良品's 素材 from 未確認 to a value on this candidate.
    body = visible_text(roots[SMALL])
    assert "素材：現行商品番号で未確認" not in body
    assert "素材：ポリカーボネート（仕様・混率）" in body
    assert "素材" in summary, summary
    assert "AIRDO・ソラシドエア" in summary or "スカイマーク・AIRDO・ソラシドエア" in summary


def test_under_100_seats_records_todays_correction() -> None:
    rows = {
        r["article_key"]: r
        for r in json.loads(LEDGER.read_text(encoding="utf-8"))["articles"]
    }
    entry = rows["carry-on-suitcase-under-100-seats"]
    # 82's excerpt and body both changed on this candidate, so /updates/ must say so.
    assert "45×35×20cm" in entry["excerpt"]
    notes = [e for e in entry["listing"]["change_log"] if e["date"] == "2026-09-16"]
    assert len(notes) == 1, [e["date"] for e in entry["listing"]["change_log"]]
    assert notes[0]["kind"] == "correction"
    assert "軸" in notes[0]["summary"] or "高さ・奥行" in notes[0]["summary"]


def test_fit_table_text_is_not_smaller_than_the_other_tables_on_the_page() -> None:
    css = THEME_CSS.read_text(encoding="utf-8")
    rule = re.search(r"\.small-carry-on-comparison table\.sc-fit-table \{([^}]*)\}", css)
    assert rule, "sc-fit-table rule"
    size = re.search(r"font-size:(\d+(?:\.\d+)?)px", rule.group(1).replace(" ", ""))
    assert size and float(size.group(1)) >= 15, rule.group(1)
    small = re.search(
        r"\.small-carry-on-comparison table\.sc-fit-table small \{([^}]*)\}", css
    )
    assert small, "sc-fit-table small rule"
    compact = small.group(1).replace(" ", "")
    assert "display:block" in compact
    inner = re.search(r"font-size:(\d+(?:\.\d+)?)px", compact)
    assert inner and float(inner.group(1)) >= 12, compact


def test_portfolio_model_count_mismatch_is_recorded_as_deferred() -> None:
    """83 publishes four models; the portfolio scope still says five.

    Both copies of the phrase have to move together (build_editorial_portfolio_v3.py
    checks editorial-identities and market-candidate-audit agree), and the audit file's
    bytes are pinned by the independently reviewed ledger hashes in
    build_st1704_reader_claim_coverage.py. So this stays deferred, with the reason on
    the record rather than silently dropped.
    """
    identities = ROOT / "changes/editorial-portfolio-v3/editorial-identities.v1.json"
    audit = ROOT / "changes/editorial-portfolio-v3/market-candidate-audit.v1.json"
    phrase = "本体3kg以下・機内持ち込み目安内の5モデル"
    assert phrase in identities.read_text(encoding="utf-8")
    assert phrase in audit.read_text(encoding="utf-8")
    status = json.loads(
        (ROOT / "changes/ks-integrated-20260915/status.v1.json").read_text(
            encoding="utf-8"
        )
    )["items"]["KS-136"]["status"]
    assert "market-candidate-audit" in status
    assert "5モデル" in status and "未反映" in status

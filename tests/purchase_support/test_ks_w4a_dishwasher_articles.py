"""KS W4a: dishwasher articles 549 / 550 / 41 / 86 / 262.

KS-016 (549 top cards), KS-121 (550 main table), KS-123 + KS-031b (41 role,
title and capacity routes), the 86 and 262 routes, KS-201a (549 space table)
and w4_corrections 7 (SOLOTA 485mm source) and 8 (TK-STTDPSWH manual scope).

Bodies are compiled in memory from the tracked sources, so these checks do not
depend on regenerated outputs. No `\\b` is used next to Japanese text.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
import re

import pytest

from scripts import build_reader_purchase_support_v1 as builder
from raos.application.editorial.purchase_support import (
    NUMBER_TOKEN,
    compile_articles,
    installation_consistency_mismatches,
    resolve_product_media,
    validate_catalog,
)
from raos.application.editorial.reader_html import Element, fragment

NOW = datetime(2026, 9, 13, 7, tzinfo=timezone.utc)
LEDGER = builder.ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json"
COMPACT = "compact-dishwasher-comparison"
STANDARD = "standard-dishwasher-comparison"
COUNTERTOP = "countertop-dishwasher-for-small-households"
PAIR = "solota-vs-rakua-mini-plus"
MEASURE = "dishwasher-installation-measurement"
TITLE = "タンク式食洗機4モデルの給水と設置を比較"
OLD_AUDIENCE = "1〜2人暮らし"
CAPACITY_HREFS = [
    "/compact-dishwasher-comparison/",
    "/standard-dishwasher-comparison/",
    "/large-dishwasher-comparison/",
]
SOLOTA = "PRD-PANASONIC-NP-TMLK1"
MINI = "PRD-THANKO-TK-MDW22W"
PLUS = "PRD-THANKO-RAKUA-MINI-PLUS"
COLOR = "PRD-THANKO-RAKUA-MINI-COLOR"
SPEC_URL = "https://panasonic.jp/dish/products/NP-TMLK1/spec.html"
INSTALLATION_URL = "https://panasonic.jp/dish/installation.html"
MANUALS = {
    MINI: "https://data.thanko.jp/download/manual/tk-mdw22w_man_web_01.pdf",
    PLUS: "https://data.thanko.jp/download/manual/tk-mdw22b_man_web_01.pdf",
}
MEASUREMENT_CLAIM = re.compile(r"実測|実際に使|使ってみ")


@pytest.fixture(scope="module")
def compiled():
    catalog = json.loads(builder.CATALOG_INPUT_PATH.read_text())
    templates = {p.stem: p.read_text() for p in builder.TEMPLATE_INPUT_PATHS}
    media = resolve_product_media(
        catalog,
        json.loads(builder.MEDIA_INPUT_PATH.read_text()),
        builder.OFFICIAL_MEDIA_INPUT_PATH.read_bytes(),
    )
    outputs, runtime = compile_articles(
        catalog,
        templates,
        json.loads(builder.GUIDES_INPUT_PATH.read_text()),
        media,
        now=NOW,
    )
    return catalog, templates, outputs, runtime


def nodes(root: Element, predicate) -> list[Element]:
    return [n for n in root.walk() if isinstance(n, Element) and predicate(n)]


def by_id(root: Element, ident: str) -> Element:
    found = nodes(root, lambda n: n.attrs.get("id") == ident)
    assert len(found) == 1, ident
    return found[0]


def elements(node: Element) -> list[Element]:
    return [c for c in node.children if isinstance(c, Element)]


def hrefs(root: Element) -> list[str]:
    return [n.attrs.get("href") or "" for n in nodes(root, lambda n: n.tag == "a")]


def squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def ancestors(node: Element) -> list[Element]:
    found = []
    parent = node.parent
    while parent is not None:
        found.append(parent)
        parent = parent.parent
    return found


def article_of(catalog, slug):
    return next(a for a in catalog["articles"] if a["slug"] == slug)


def product_of(catalog, pid):
    return next(p for p in catalog["products"] if p["product_id"] == pid)


def cm(mm: int) -> str:
    return f"{mm / 10:g}cm"


# KS-016 -----------------------------------------------------------------------


def test_compact_top_cards_offer_each_product_once(compiled) -> None:
    catalog, _, outputs, runtime = compiled
    article = article_of(catalog, COMPACT)
    assert [(s["key"], s["product_id"]) for s in article["condition_slots"]] == [
        ("choice-1", SOLOTA),
        ("choice-2", MINI),
        ("choice-2", PLUS),
        ("choice-2", COLOR),
    ]
    root = fragment(outputs[COMPACT])
    pick = by_id(root, "compact-pick")
    purchases = nodes(pick, lambda n: n.has("ps-condition-product-purchase"))
    assert sorted(n.attrs["data-ps-purchase-product"] for n in purchases) == sorted(
        [SOLOTA, MINI, PLUS, COLOR]
    )
    entry = next(a for a in runtime["articles"] if a["slug"] == COMPACT)
    assert {key.split("--")[0] for key in entry.get("condition_media", {})} <= {
        "choice-1",
        "choice-2",
    }
    # Each product sits in exactly one slot, so every product carries the same
    # number of top_summary bindings (a repeated product would carry twice as many).
    top = Counter(
        b["product_id"]
        for b in entry["bindings"]
        if b.get("placement") == "top_summary"
    )
    assert set(top) <= {SOLOTA, MINI, PLUS, COLOR}
    assert len(set(top.values())) <= 1, top
    grids = nodes(pick, lambda n: n.has("compact-choices"))
    assert len(grids) == 1
    cards = elements(grids[0])
    assert [c.attrs.get("id") for c in cards] == [
        "compact-choice-depth",
        "compact-choice-amount",
        "compact-choice-dry",
    ]
    for card in cards:
        ident = card.attrs["id"]
        lists = [c for c in elements(card) if c.tag == "ul"]
        assert len(lists) == 1, ident
        assert [li.tag for li in elements(lists[0])] == ["li", "li"], ident
        assert len(nodes(card, lambda n: n.tag == "li")) == 2, ident
        assert len(nodes(card, lambda n: n.has("compact-caveat"))) == 1, ident
        who = [
            c
            for c in elements(card)
            if c.tag == "p" and squash(c.text()).startswith("向く人：")
        ]
        assert len(who) == 1, ident
    amount = cards[1]
    assert [
        n.attrs["data-ps-purchase-product"]
        for n in nodes(amount, lambda n: n.has("ps-condition-product-purchase"))
    ] == [MINI, PLUS, COLOR]
    dry = cards[2]
    assert not nodes(
        dry,
        lambda n: (
            n.has("ps-condition-product-purchase")
            or n.has("ps-condition-product-media")
        ),
    )
    assert {"#compact-choice-amount", "#compact-alternatives"} <= set(hrefs(dry))
    care = by_id(root, "compact-care")
    assert "/countertop-dishwasher-for-small-households/" in hrefs(care)


# KS-121 -----------------------------------------------------------------------

STANDARD_HEADS = [
    "商品・写真",
    "食器量",
    "本体寸法・開扉時の奥行",
    "給水",
    "乾燥",
    "参考価格・販売先",
]
STANDARD_LABELS = ["食器量", "本体 幅×奥行×高さ", "扉を開いた奥行", "給水", "乾燥"]
# Values moved from the former details table "扉を開くと、ここまで必要".
STANDARD_DOOR_DRY = {
    # Siroca installation FAQ prints （約） on the SS-MA251/SS-MU251 and
    # PDW-M151/SS-M171 rows (re-fetched 2026-09-16 06:26 JST).
    "ss-m171": ("約76cm", "送風"),
    "pdw-m151": ("約76cm", "送風"),
    "ss-ma251": ("約76cm", "送風＋自動開扉"),
    "ss-mu251": ("約76cm", "送風"),
    "sttdwadw": ("未確認", "温風"),
    "ax-s7": ("約75cm", "温風"),
    "dws-33b-w": ("未確認", "温風"),
    "np-tcr5-w": ("59.8cm", "ヒーター"),
    "tkdwslhwh": ("83cm", "温風"),
    "np-tsk2": ("約43.3cm", "ヒーター"),
    "np-tsp1-w": ("公式表記に差", "ヒーター"),
    "tkdwwdhwh": ("73cm", "温風"),
    "adw-m28b": ("83cm", "温風／送風"),
}


def test_standard_main_table_groups_door_depth_and_drying_outside_details(
    compiled,
) -> None:
    _, templates, outputs, _ = compiled
    template = fragment(templates[STANDARD])
    for section in ("std-daily", "std-more"):
        tables = nodes(by_id(template, section), lambda n: n.tag == "table")
        assert len(tables) == 1, section
        heads = nodes(tables[0].find(tag="thead")[0], lambda n: n.tag == "th")
        assert [squash(h.text()) for h in heads] == STANDARD_HEADS, section
    root = fragment(outputs[STANDARD])
    comparison = by_id(root, "std-comparison")
    rows = nodes(
        comparison,
        lambda n: n.tag == "tr" and bool(n.attrs.get("data-product-key")),
    )
    assert [r.attrs["data-product-key"] for r in rows] == list(STANDARD_DOOR_DRY)
    for row in rows:
        key = row.attrs["data-product-key"]
        labels = [
            squash(n.text()) for n in nodes(row, lambda n: n.has("std-spec-label"))
        ]
        assert labels == [squash(label) for label in STANDARD_LABELS], key
        groups = nodes(row, lambda n: n.has("ps-matrix-spec-group"))
        assert len(groups) == 4, key
        door, dry = STANDARD_DOOR_DRY[key]
        assert "扉を開いた奥行" + squash(door) in squash(groups[1].text()), key
        assert squash(groups[3].text()).startswith("乾燥" + squash(dry)), key
    assert not re.search(r"(?<!約)76cm", squash(root.text()))
    tsp1 = next(r for r in rows if r.attrs["data-product-key"] == "np-tsp1-w")
    assert all(token in squash(tsp1.text()) for token in ("43.3cm", "38.6", "36.2"))
    details = by_id(root, "std-reference-details")
    detail_text = squash(details.text())
    assert "扉を開くと" not in detail_text
    assert "上面から70cm以上" not in detail_text
    summary = nodes(details, lambda n: n.tag == "summary")[0]
    assert squash(summary.text()) == "比較範囲・水と電気・保証・除外機種・出典"
    notes = [
        n
        for n in nodes(root, lambda n: n.tag == "p" and n.has("std-note"))
        if "本体上面から70cm以上" in squash(n.text())
    ]
    assert len(notes) == 1
    assert not any(a.tag == "details" for a in ancestors(notes[0]))
    body = squash(root.text())
    assert "開扉寸法・乾燥と設置条件の詳細" not in body
    choice = squash(
        nodes(root, lambda n: n.tag == "section" and n.has("std-choice"))[0].text()
    )
    assert "分岐水栓だけに対応するNP-TCR5-W" in choice
    assert "分岐水栓だけに対応するNP-TSK2" in choice
    assert "#std-comparison" in hrefs(by_id(root, "std-recommendations"))
    space = by_id(root, "std-space")
    assert "#std-reference-details" not in hrefs(space)
    for paragraph in nodes(space, lambda n: n.tag == "p"):
        if "/dishwasher-installation-measurement/" in hrefs(paragraph):
            assert "SOLOTA・ラクアminicolor・SS-MA251・NP-TSP1" in squash(
                paragraph.text()
            )
            break
    else:
        raise AssertionError("installation guide link")
    following = nodes(root, lambda n: n.tag == "section" and n.has("std-next"))[0]
    assert "既存のタンク式4モデル比較" not in squash(following.text())
    assert "/countertop-dishwasher-for-small-households/" in hrefs(following)


# KS-123 / KS-031b ---------------------------------------------------------------


def test_countertop_role_title_and_capacity_routes(compiled) -> None:
    catalog, _, outputs, _ = compiled
    article = article_of(catalog, COUNTERTOP)
    assert article["title"] == TITLE
    ledger = {
        row["article_key"]: row
        for row in json.loads(LEDGER.read_text(encoding="utf-8"))["articles"]
    }
    assert ledger[COUNTERTOP]["title"] == TITLE
    assert ledger[COUNTERTOP]["excerpt"] == article["excerpt"]
    for text in (article["title"], article["excerpt"], article["intro"]):
        assert OLD_AUDIENCE not in text
    assert "給水" in article["excerpt"] and "分岐水栓" in article["excerpt"]
    labels = {c["id"]: c["label"] for c in article["conditions"]}
    assert "幅" not in labels["small-warm"]
    assert "分岐水栓" in labels["two-way"] and "分岐水栓" in labels["more-dishes"]
    assert "蛇口" in labels["one-person"]
    assert all(
        "カップ" in labels[key] for key in ("small-warm", "two-way", "more-dishes")
    )
    body = outputs[COUNTERTOP]
    assert OLD_AUDIENCE not in body
    root = fragment(body)
    lead = nodes(root, lambda n: n.has("ps-lead"))
    assert len(lead) == 1 and "給水の手間" in lead[0].text()
    routes = by_id(root, "ps-capacity-routes")
    assert [h for h in hrefs(routes)] == CAPACITY_HREFS
    assert body.index('class="ps-lead"') < body.index('id="ps-capacity-routes"')
    assert body.index('id="ps-capacity-routes"') < body.index('id="ps-choose"')
    specs = by_id(root, "ps-specs")
    rows = nodes(
        specs, lambda n: n.tag == "tr" and bool(n.attrs.get("data-product-id"))
    )
    assert len(rows) == 4
    for row in rows:
        first = nodes(row, lambda n: n.has("ps-matrix-spec-group"))[0]
        label = nodes(first, lambda n: n.has("ps-row-fact-label"))[0]
        assert label.text() == "給水方式", row.attrs["data-product-id"]
    for slug in (COMPACT, STANDARD):
        assert OLD_AUDIENCE not in outputs[slug], slug


def test_capacity_routes_render_only_where_declared(compiled) -> None:
    catalog, _, outputs, _ = compiled
    for article in catalog["articles"]:
        if article["slug"] != COUNTERTOP:
            assert "ps-capacity-routes" not in outputs[article["slug"]], article["slug"]


@pytest.mark.parametrize(
    "href",
    [
        "/no-such-dishwasher-article/",
        "compact-dishwasher-comparison",
        "/compact-dishwasher-comparison",
    ],
)
def test_capacity_routes_reject_links_outside_the_catalog(compiled, href) -> None:
    catalog = deepcopy(compiled[0])
    article_of(catalog, COUNTERTOP)["capacity_routes"]["links"][0]["href"] = href
    with pytest.raises(ValueError, match="PURCHASE_CAPACITY_ROUTE_UNKNOWN"):
        validate_catalog(catalog)


def test_pair_and_installation_guide_route_by_role(compiled) -> None:
    _, _, outputs, _ = compiled
    pair = fragment(outputs[PAIR])
    following = by_id(pair, "ks-next-read")
    links = hrefs(following)
    for href in CAPACITY_HREFS + ["/countertop-dishwasher-for-small-households/"]:
        assert href in links, href
    assert links.index("/compact-dishwasher-comparison/") < links.index(
        "/countertop-dishwasher-for-small-households/"
    )
    assert OLD_AUDIENCE not in outputs[PAIR]
    guide = fragment(outputs[MEASURE])
    assert OLD_AUDIENCE not in outputs[MEASURE]
    tank = [
        n
        for n in nodes(by_id(guide, "ks-next-read"), lambda n: n.tag == "a")
        if n.attrs.get("href") == "/countertop-dishwasher-for-small-households/"
    ]
    assert len(tank) == 1 and squash(tank[0].text()) == squash(
        "タンク式食洗機4モデルの給水と設置の比較"
    )


# KS-201a --------------------------------------------------------------------------

SPACE_HEADS = [
    "商品",
    "開扉時の奥行",
    "説明書の設置余白",
    "可燃物からの離隔（説明書）",
    "設置案内の図の寸法",
    "水栓・蛇口に当たりにくい奥行の目安（公式資料の記載）",
]


def space_rows(root: Element) -> dict[str, list[str]]:
    table = by_id(root, "compact-space-table")
    heads = nodes(table.find(tag="thead")[0], lambda n: n.tag == "th")
    assert [squash(h.text()) for h in heads] == [squash(h) for h in SPACE_HEADS]
    rows = {}
    for tr in nodes(
        table, lambda n: n.tag == "tr" and bool(n.attrs.get("data-ps-space-product"))
    ):
        cells = [c for c in elements(tr) if c.tag in {"th", "td"}]
        assert len(cells) == len(SPACE_HEADS)
        rows[tr.attrs["data-ps-space-product"]] = [squash(c.text()) for c in cells] + [
            tr.attrs.get("data-ps-door-origin", "")
        ]
    return rows


def test_compact_space_table_keeps_source_kinds_apart(compiled) -> None:
    catalog, _, outputs, _ = compiled
    root = fragment(outputs[COMPACT])
    space = by_id(root, "compact-space")
    assert by_id(space, "compact-space-table") is not None
    rows = space_rows(root)
    assert list(rows) == article_of(catalog, COMPACT)["product_ids"]
    solota = product_of(catalog, SOLOTA)["installation"]
    color = product_of(catalog, COLOR)["installation"]
    name, door, manual, flammable, figure, required, origin = rows[SOLOTA]
    assert "NP-TMLK1-K" in name
    assert cm(solota["door_depth_mm"]) in door and "＜485＞" in door
    # The spec line is 「約 幅310×高さ435×奥行225＜485＞mm」, so the cell keeps 約.
    assert door.startswith("約" + cm(solota["door_depth_mm"]))
    assert cm(solota["rear_mm"]) in figure and "50.2cm" not in figure
    assert origin == "official"
    assert required.startswith("50.2cm以上")
    for phrase in (
        "「50.2cm以上あれば、ドアが水栓・蛇口に当たりにくい」",
        "代替テキストは「背面から50.2cm以上」",
        "図の線から",
    ):
        assert phrase in required, phrase
    assert "1.7cm" not in manual and "1.7cm" not in flammable
    assert all(t in flammable for t in ("上方5cm", "側方0.5cm", "後方0.5cm"))
    name, door, manual, flammable, figure, required, origin = rows[COLOR]
    assert cm(color["door_depth_mm"]) in door
    assert all(
        t in manual
        for t in (
            "上面" + cm(color["above_mm"]),
            "後面" + cm(color["rear_mm"]),
            "側面" + cm(color["left_mm"]),
        )
    )
    for pid in (MINI, PLUS):
        fact = next(
            f for f in product_of(catalog, pid)["facts"] if f["label"] == "必要な余白"
        )
        assert fact["source_url"] == MANUALS[pid] and "p.7" in fact["locator"]
        numbers = [float(t) for t in NUMBER_TOKEN.findall(fact["text"])]
        assert numbers[:3] == [700, 100, 100], pid
        name, door, manual, flammable, figure, required, origin = rows[pid]
        assert "59.4cm" in door
        assert all(t in manual for t in ("上面70cm", "後面10cm", "側面10cm")), pid
    assert "TK-STTDPSWH" in rows[PLUS][0]
    for pid, (name, door, manual, flammable, figure, required, origin) in rows.items():
        rear = {
            SOLOTA: solota["rear_mm"],
            COLOR: color["rear_mm"],
            MINI: 100,
            PLUS: 100,
        }[pid]
        depth = {
            SOLOTA: solota["door_depth_mm"],
            COLOR: color["door_depth_mm"],
            MINI: 594,
            PLUS: 594,
        }[pid]
        assert rear and depth
        if origin == "official":
            assert pid == SOLOTA
        else:
            assert origin == "unconfirmed", pid
            assert required.startswith("判定保留"), pid
            assert "同じ種類の目安の記載を確認できず" in required, pid
            assert not re.search(r"[0-9]cm", required), pid
    text = squash(space.text())
    assert not MEASUREMENT_CLAIM.search(text)
    # Panasonic prints 50.2cm as the depth at which the door is less likely to hit
    # the faucet (当たりにくい), not as a required depth.
    assert "必要な奥行" not in text
    assert (
        "水栓・蛇口に当たりにくい目安の50.2cm以上は設置案内の図の値" in text
    )
    space_table = by_id(root, "compact-space-table")
    assert not space_table.find(tag="caption")
    assert "出典の種類ごとに列を分けています。2026年9月16日に公式資料で確認しました。" in text
    assert "実機で測ったものではありません" in text
    assert (
        squash(
            "ラクアmini系3製品は本体寸法が同じでも、説明書が指定する設置の余白はmini colorだけ違う"
        )
        in text
    )
    assert "置き場に必要な空間が違う" not in text
    assert (
        "48.5cmの起点も確認できていないため、この足し算では判断しません（編集部の計算）"
        in text
    )
    assert "照合する欄" not in text
    assert (
        "置き場所の測り方のガイドでも、扉を開けたときの奥行と本体の後ろの余白は別々に書き込んで確かめます。"
        in text
    )
    note = squash(by_id(root, "compact-space").text())
    assert "下の表で図から確認できた範囲だけを示します" not in note


PUMP_FAQ_WORDING = "別売の給水補助ポンプは使用できません（過去のセット販売品を除く）"


def test_compact_mini_pump_wording_follows_the_faq(compiled) -> None:
    _, _, outputs, _ = compiled
    root = fragment(outputs[COMPACT])
    body = squash(root.text())
    for old in ("現行の別売ポンプは非対応", "現行の別売給水ポンプには対応していません"):
        assert old not in body, old
    card = squash(by_id(root, "compact-choice-amount").text())
    assert PUMP_FAQ_WORDING in card
    assert body.count(PUMP_FAQ_WORDING) == 4


def test_measurement_guide_does_not_fix_the_open_door_origin(compiled) -> None:
    _, _, outputs, _ = compiled
    body = outputs[MEASURE]
    for old in ("背面基準線", "背面から開いた扉の先端まで"):
        assert old not in body, old
    assert (
        "④は各メーカーが示す開扉時の奥行です。どこから測った値かは型番の公式図で確かめ、"
        "確認できない場合は本体奥行に足しも引きもしません。"
    ) in body


COLOR_CLEARANCE_LOCATOR = "取扱説明書 p.10 設置場所について"


def test_mini_color_clearance_follows_the_printed_manual_words(compiled) -> None:
    catalog, _, outputs, _ = compiled
    product = product_of(catalog, COLOR)
    fact = next(f for f in product["facts"] if f["label"] == "必要な余白")
    guide = next(f for f in product["guide_facts"] if f["field"] == "clearance")
    assert fact["text"] == "上面500mm・後面50mm・側面50mm以上、熱源から150mm以上"
    assert guide["text"].startswith("上面500mm、後面50mm、側面50mm以上")
    for record in (fact, guide):
        assert record["locator"] == COLOR_CLEARANCE_LOCATOR
        assert "左右" not in record["text"]
    assert installation_consistency_mismatches(product) == []
    countertop = squash(fragment(outputs[COUNTERTOP]).text())
    measure = squash(fragment(outputs[MEASURE]).text())
    assert "上500mm／背面50mm／左右各50mm" not in countertop
    assert "上面500mm・後面50mm・側面50mm以上" in countertop
    assert "上方500mm、背面50mm、左右それぞれ" not in measure
    assert "上面500mm、後面50mm、側面50mm以上" in measure
    assert squash(COLOR_CLEARANCE_LOCATOR) in countertop + measure


ALT_50_2 = "「図：高さが49cm以上あればOK、背面から50.2cm以上あれば、ドアが水栓・蛇口に当たりにくい。」"


def test_solota_required_depth_quotes_the_official_figure_and_alt_text(
    compiled,
) -> None:
    catalog, _, outputs, _ = compiled
    product = product_of(catalog, SOLOTA)
    records = [f for f in product["facts"] if f["label"] == "必要な余白"] + [
        f for f in product["guide_facts"] if f["field"] == "clearance"
    ]
    assert len(records) == 2
    for record in records:
        assert "50.2cm以上あればドアが水栓・蛇口に当たりにくい" in record["text"]
        assert ALT_50_2 in record["locator"]
        assert "図の線から" in record["text"]
        assert "48.5" not in record["text"]
    for key in (COUNTERTOP, MEASURE, PAIR):
        assert squash(ALT_50_2) in squash(fragment(outputs[key]).text()), key


def test_ledger_summary_for_the_compact_space_table_is_exact() -> None:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    article = next(a for a in ledger["articles"] if a["slug"] == COMPACT)
    entry = next(
        c for c in article["listing"]["change_log"] if c["date"] == "2026-09-16"
    )
    assert "説明書の設置余白を出典の種類ごとに分けた表を追加" in entry["summary"]
    assert "置き場所に必要な空間" not in entry["summary"]


def test_space_table_leaves_the_measurement_guide_references_unchanged(
    compiled,
) -> None:
    catalog = compiled[0]
    expected = {
        SOLOTA: (310, 225, 435, 485, None, 55, 5, 5, 17),
        COLOR: (308, 315, 415, 594, None, 500, 50, 50, 50),
        "PRD-SIROCA-SS-MA251": (420, 440, 470, 760, None, 700, 50, 50, 60),
        "PRD-PANASONIC-NP-TSP1": (550, 341, 600, None, 712, 120, 5, 5, 5),
    }
    keys = (
        "width_mm",
        "depth_mm",
        "height_mm",
        "door_depth_mm",
        "door_height_mm",
        "above_mm",
        "left_mm",
        "right_mm",
        "rear_mm",
    )
    for pid, values in expected.items():
        product = product_of(catalog, pid)
        assert tuple(product["installation"][k] for k in keys) == values, pid
        assert installation_consistency_mismatches(product) == [], pid
    for pid in (MINI, PLUS):
        assert not product_of(catalog, pid).get("installation"), pid


# w4_corrections 7 / 8 ---------------------------------------------------------------


def test_solota_open_door_depth_cites_the_spec_page(compiled) -> None:
    catalog = compiled[0]
    product = product_of(catalog, SOLOTA)
    door = [f for f in product["facts"] if f["label"] == "開扉時の寸法"] + [
        f for f in product["guide_facts"] if f["field"] == "door"
    ]
    assert len(door) == 2
    for record in door:
        assert record["source_url"] == SPEC_URL
        tokens = NUMBER_TOKEN.findall(record["text"])
        assert "485" in tokens and "502" not in tokens and "490" not in tokens
        assert "ドア開閉時の最大寸法" in record["text"] + record["locator"]
    for record in product["facts"] + product["guide_facts"]:
        if record["source_url"] == INSTALLATION_URL:
            tokens = NUMBER_TOKEN.findall(record["text"])
            assert "485" not in tokens and "48.5" not in tokens, record.get(
                "label", record.get("field")
            )
    assert installation_consistency_mismatches(product) == []


def test_mini_plus_scope_separates_page_specs_from_the_shared_manual(compiled) -> None:
    catalog = compiled[0]
    product = product_of(catalog, PLUS)
    caution = product["caution"]
    assert "TK-STTDPSWH" in caution and "取扱説明書" in caution and "共通" in caution
    assert "仕様を読み替えません" not in caution
    manual = [f for f in product["facts"] if f["source_url"] == MANUALS[PLUS]]
    assert manual and all(f["exact_model"] == "TK-MDW22B" for f in manual)
    assert all("TK-STTDPSWH" in f["text"] + f["locator"] for f in manual)


# W4a review round 2 ---------------------------------------------------------------

SIROCA = "PRD-SIROCA-SS-MA251"


def test_measurement_table_keeps_approximate_door_depths(compiled) -> None:
    _, _, outputs, _ = compiled
    root = fragment(outputs[MEASURE])
    rows = [
        tr
        for tr in nodes(root, lambda n: n.tag == "tr")
        if any(
            c.tag == "th" and squash(c.text()) == "扉を開いたとき" for c in elements(tr)
        )
    ]
    assert len(rows) == 1
    cells = {
        c.attrs.get("data-ps-product"): squash(c.text())
        for c in elements(rows[0])
        if c.tag == "td"
    }
    assert cells[SOLOTA].startswith("奥行約485mm／")
    assert cells[SIROCA].startswith("奥行約760mm／")
    assert cells[COLOR].startswith("奥行594mm／")


def test_door_open_depths_keep_the_official_approximation(compiled) -> None:
    """The spec rows print 「約 幅310×高さ435×奥行225＜485＞mm」 and
    「約 幅550×高さ600＜712＞×奥行341…」, so every door-open value in the
    republished bodies carries 約 (review round 2, minor)."""
    _, _, outputs, _ = compiled
    bodies = {
        slug: squash(fragment(outputs[slug]).text())
        for slug in (COMPACT, COUNTERTOP, PAIR, MEASURE)
    }
    for phrase in (
        "扉を開くと約48.5cm",
        "開扉時奥行約48.5cm",
        "開扉時の最大奥行約48.5cm",
    ):
        assert phrase in bodies[COMPACT], phrase
    for slug in (COUNTERTOP, PAIR):
        assert "扉を開けたときの奥行約485mm" in bodies[slug], slug
        assert "扉を開けたときの奥行485mm" not in bodies[slug], slug
    assert "開扉時の奥行は約485mmです" in bodies[MEASURE]
    for slug in (COUNTERTOP, MEASURE):
        assert "開扉時の高さは約712mm" in bodies[slug], slug
        assert "開扉時の高さは712mm" not in bodies[slug], slug
    assert "最大高さ約712mm" in bodies[COUNTERTOP]
    # NP-TSP1's two conflicting official values sit next to the 約712mm height and
    # come from rows that carry 約 themselves (spec 「約 幅550×高さ600＜712＞×奥行341
    # ＜上386,下362＞mm」, comparison 「本体外形寸法（約）」; re-fetched 2026-09-16).
    for phrase in ("個別仕様上約386mm・下約362mm", "比較表約433mm"):
        assert phrase in bodies[MEASURE], phrase
    assert "上386mm" not in bodies[MEASURE]
    assert "下362mm" not in bodies[MEASURE]
    assert "比較表433mm" not in bodies[MEASURE]


def test_tmlk1_source_note_dates_the_manual_page_separately(compiled) -> None:
    catalog, _, outputs, _ = compiled
    fact = next(
        f
        for f in product_of(catalog, SOLOTA)["facts"]
        if f["label"] == "必要な余白"
    )
    assert fact["checked_at"] == "2026-09-16"
    assert "取扱説明書P9901-20V10 p.8 設置場所の図（確認 2026年9月15日）" in fact["locator"]
    for slug in (MEASURE, COUNTERTOP, PAIR):
        root = fragment(outputs[slug])
        body = squash(root.text())
        assert "p.8設置場所の図（確認2026年9月15日）" in body, slug
        assert "p.8設置場所の図。50.2cm" not in body, slug
        # Source lists (41, 86) end each item with the installation.html check date.
        for li in nodes(root, lambda n: n.tag == "li"):
            item = squash(li.text())
            if "P9901-20V10p.8" in item:
                assert item.endswith("仕様確認2026年9月16日"), slug


# Re-fetched 2026-09-16: panasonic.jp NP-TSK2 spec 「本体外形寸法 ★8 約 幅550×奥行290
# ＜上433,下362＞×高さ500＜612＞mm」, NP-TSP1 spec 「約 幅550×高さ600＜712＞×奥行341
# ＜上386,下362＞mm」, ainx.info 「扉を開いた際の最大奥行幅 約75cm」, siroca 据え付けFAQ
# 「（約）… d: ドアを開いたときの奥行き 76.0 cm」.
DOOR_DEPTH_APPROXIMATE = {
    "std-np-tsk2": ("約43.3cm", "約61.2cm"),
    "std-np-tsp1-w": ("約43.3cm", "約38.6cm", "約36.2cm"),
    "std-ax-s7": ("約75cm",),
    "std-ss-m171": ("約76cm",),
}
# Re-fetched 2026-09-16: NP-TCR5 spec 「本体外形寸法 ★6 幅470×奥行300＜598＞×高さ460
# ＜467＞mm」 (no 約), thanko.jp 「開扉時奥行：830mm」「730mm」 (no 約).
DOOR_DEPTH_EXACT = {
    "std-np-tcr5-w": "59.8cm",
    "std-tkdwslhwh": "83cm",
    "std-tkdwwdhwh": "73cm",
}


def test_standard_door_depth_column_follows_each_official_notation(compiled) -> None:
    """One column must not quote 約 from one maker and drop it from another.

    The Panasonic values come from rows whose own header carries 約, so writing
    them bare states the dimension more precisely than the source does.
    """
    _, _, outputs, _ = compiled
    root = fragment(outputs[STANDARD])
    cells = {}
    for cell in nodes(root, lambda n: "std-door-depth" in (n.attrs.get("class") or "")):
        row = next(a for a in ancestors(cell) if a.tag == "tr")
        cells[row.attrs.get("id")] = squash(cell.text())
    for row_id, phrases in DOOR_DEPTH_APPROXIMATE.items():
        for phrase in phrases:
            assert phrase in cells[row_id], (row_id, phrase, cells.get(row_id))
    for row_id, value in DOOR_DEPTH_EXACT.items():
        assert "約" not in cells[row_id], (row_id, cells[row_id])
        assert value in cells[row_id], row_id
    body = squash(root.text())
    assert "設置の目安約62cm以上" in body
    assert squash("「約」は、公式が「約」を付けている値に付けています。") in body
    assert "本体幅55cm、開扉時の奥行約43.3cm" in body


def test_same_day_change_log_names_the_approximation_correction() -> None:
    """/updates/ shows the 2026-09-16 card for 41 and 549.

    The bodies gained 約 on every door-open dimension that day, so a card dated
    2026-09-16 that does not mention it describes less than what changed.
    """
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    for slug in (COMPACT, COUNTERTOP):
        article = next(a for a in ledger["articles"] if a["slug"] == slug)
        entry = next(
            c for c in article["listing"]["change_log"] if c["date"] == "2026-09-16"
        )
        assert "「約」" in entry["summary"], slug
        assert "開扉" in entry["summary"] or "扉を開" in entry["summary"], slug

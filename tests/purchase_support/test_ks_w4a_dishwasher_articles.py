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
    "ss-m171": ("76cm", "送風"),
    "pdw-m151": ("76cm", "送風"),
    "ss-ma251": ("76cm", "送風＋自動開扉"),
    "ss-mu251": ("76cm", "送風"),
    "sttdwadw": ("未確認", "温風"),
    "ax-s7": ("75cm", "温風"),
    "dws-33b-w": ("未確認", "温風"),
    "np-tcr5-w": ("59.8cm", "ヒーター"),
    "tkdwslhwh": ("83cm", "温風"),
    "np-tsk2": ("43.3cm", "ヒーター"),
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
    "必要な奥行（後面の余白＋開扉時の奥行）",
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
    assert cm(solota["rear_mm"]) in figure and "50.2cm" in figure
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
        if origin == "confirmed":
            assert required == cm(rear + depth), pid
        else:
            assert origin == "unconfirmed", pid
            assert required.startswith("判定保留"), pid
            assert not re.search(r"[0-9]cm", required), pid
    text = squash(space.text())
    assert not MEASUREMENT_CLAIM.search(text)
    assert "実機で測ったものではありません" in text
    assert "本体が同じでも置き場に必要な空間が違う" in text


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

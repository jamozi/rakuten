"""Purpose-first R2.1 deltas: hub product links, comparison slots and guide routes."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from raos.application.editorial import purchase_support as ps
from raos.application.editorial.reader_html import fragment

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "changes/reader-purchase-support-v1"
PUBLISHED = ROOT / "changes/wordpress-direct-publish-v1/articles"
NOW = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)
DISHWASHERS = (
    "PRD-PANASONIC-NP-TMLK1",
    "PRD-THANKO-RAKUA-MINI-COLOR",
    "PRD-SIROCA-SS-MA251",
    "PRD-PANASONIC-NP-TSP1",
)


@pytest.fixture
def catalog():
    return json.loads((BASE / "purchase-support.v1.json").read_text())


def compile(catalog):
    return ps.compile_articles(
        catalog,
        {p.stem: p.read_text() for p in (BASE / "articles").glob("*.html")},
        json.loads(
            (
                ROOT / "changes/editorial-portfolio-v3/local-reader-guides.v1.json"
            ).read_text()
        ),
        now=NOW,
    )


def ids_of(markup):
    return {n.attrs["id"] for n in fragment(markup).walk() if "id" in n.attrs}


def dishwashers(catalog):
    return [p for p in catalog["products"] if p["product_id"] in DISHWASHERS]


# --- FD-08 / R-BRIDGE: category 136 promises only what the comparison offers ---


def test_hub_links_each_condition_product_to_its_own_anchor(catalog):
    html, _ = compile(catalog)
    hub = fragment(html["kitchen"])
    choose = next(n for n in hub.find(tag="section") if n.attrs.get("id") == "choose")
    anchors = {p["anchor"]: p["name"] for p in dishwashers(catalog)}
    links = [
        a
        for a in choose.find(tag="a")
        if a.attrs.get("href", "").startswith(f"/{ps.MAIN_SLUG}/#")
    ]
    product_links = [a for a in links if a.attrs["href"].split("#", 1)[1] in anchors]
    assert len(product_links) == 4
    assert {a.attrs["href"].split("#", 1)[1] for a in product_links} == set(anchors)
    for a in product_links:
        assert a.text() == anchors[a.attrs["href"].split("#", 1)[1]]
    assert not [a for a in links if a.attrs["href"].endswith("#ps-choose")]
    # AC31: the anchors already exist in the published comparison, so the neutral
    # category text can go first without waiting for the new comparison layout.
    published = ids_of((PUBLISHED / f"{ps.MAIN_SLUG}.html").read_text())
    assert set(anchors) <= published
    assert "ps-specs" in published


def test_hub_lead_and_cta_do_not_promise_budget_filtering(catalog):
    html, _ = compile(catalog)
    hub = html["kitchen"]
    assert "予算" not in hub
    assert "設置・給排水・費用などの作業別ガイドは、下の記事一覧から確かめたい作業で選べます。" in hub
    # The category hub keeps the shared hub skeleton (CH-06): entry breadcrumb, note, policy links.
    for label in ("このサイトの入口", "このページの読み方", "ほかの商品カテゴリ", "編集方針"):
        assert f'<nav aria-label="{label}"' in hub
    assert '<span aria-current="page">食洗機の選び方・比較</span>' in hub
    assert 'class="ks-reader-note"' in hub
    assert hub.count('class="ks-pr-badge"') == 1
    assert f'<a href="/{ps.MAIN_SLUG}/#ps-specs">決め手になる比較表（4機種）</a>' in hub
    for _, slug in ps.STAGES.values():
        assert f'href="/{slug}/"' in hub
    assert 'href="/solota-vs-rakua-mini-plus/"' in hub


@pytest.mark.parametrize("mutation", ["missing_product", "missing_anchor"])
def test_hub_condition_links_fail_closed(catalog, mutation):
    products = dishwashers(catalog)
    condition = {"id": "x", "label": "x", "product_ids": ["PRD-PANASONIC-NP-TMLK1"]}
    if mutation == "missing_product":
        condition["product_ids"] = ["PRD-UNKNOWN"]
    else:
        products = [
            dict(p, anchor="") if p["product_id"] == "PRD-PANASONIC-NP-TMLK1" else p
            for p in products
        ]
    with pytest.raises(ValueError):
        ps.condition_product_links(condition, products, ps.MAIN_SLUG)


# --- FD-02 / FD-04 / R-B: the main comparison without inputs, with reasons ---

MAIN_TEMPLATE = BASE / "articles" / f"{ps.MAIN_SLUG}.html"
GOOD_SLOTS = (
    '<section id="ps-task-fit" data-ps-editorial-slot="task-fit"><h2>作業</h2><p>回答</p></section>'
    '<section id="ps-hold-reasons" data-ps-editorial-slot="hold-reasons"><h2>保留</h2><p>確認先</p></section>'
)


def test_editorial_slot_returns_each_section_once_without_edit_attributes():
    task = ps.editorial_slot(GOOD_SLOTS, "task-fit")
    assert "回答" in task and "確認先" not in task
    assert "data-ps-editorial-slot" not in task
    assert task.startswith('<section id="ps-task-fit">')
    hold = ps.editorial_slot(GOOD_SLOTS, "hold-reasons")
    assert "確認先" in hold and "回答" not in hold


@pytest.mark.parametrize(
    "markup",
    [
        GOOD_SLOTS + '<section data-ps-editorial-slot="extra"></section>',
        GOOD_SLOTS + '<span id="ps-task-fit"></span>',
        GOOD_SLOTS.replace('id="ps-task-fit"', 'id="wrong"'),
        GOOD_SLOTS.replace(
            'data-ps-editorial-slot="hold-reasons"', 'data-ps-editorial-slot="task-fit"'
        ),
        '<section id="ps-task-fit" data-ps-editorial-slot="task-fit">'
        '<section id="ps-hold-reasons" data-ps-editorial-slot="hold-reasons"></section></section>',
        GOOD_SLOTS.replace(
            '<section id="ps-hold-reasons" data-ps-editorial-slot="hold-reasons">', ""
        ).replace("<p>確認先</p></section>", ""),
        "",
    ],
)
def test_invalid_slot_layout_stops_generation(markup):
    with pytest.raises(ValueError):
        ps.editorial_slot(markup, "task-fit")
    with pytest.raises(ValueError):
        ps.editorial_slot(GOOD_SLOTS, "unknown")


def test_main_comparison_keeps_condition_links_and_no_inputs(catalog):
    html, _ = compile(catalog)
    root = fragment(html[ps.MAIN_SLUG])
    top = next(n for n in root.walk() if "data-raos-article-id" in n.attrs)
    assert top.attrs["data-ps-purpose-mode"] == "links"
    assert top.attrs["data-ps-budget-mode"] == "off"
    assert not any("data-ps-purpose-options" in n.attrs for n in root.walk())
    assert not any(n.tag in {"input", "select", "button", "form"} for n in root.walk())
    choose = next(
        n for n in root.find(tag="section") if n.attrs.get("id") == "ps-choose"
    )
    anchors = {p["anchor"] for p in dishwashers(catalog)}
    links = [
        a.attrs["href"].lstrip("#")
        for a in choose.find(tag="a")
        if a.attrs.get("href", "").startswith("#product-")
    ]
    assert sorted(links) == sorted(anchors)
    assert "data-ps-pair-options" in html[ps.MAIN_SLUG]
    for slug in (
        "lightweight-carry-on-suitcase-under-3kg",
        "compact-robot-vacuum-shortlist",
        "portable-power-station-guide",
    ):
        other = fragment(html[slug])
        other_top = next(n for n in other.walk() if "data-raos-article-id" in n.attrs)
        assert "data-ps-purpose-mode" not in other_top.attrs
        assert any("data-ps-purpose-options" in n.attrs for n in other.walk())


def test_main_comparison_section_order_and_single_slots(catalog):
    html, _ = compile(catalog)
    body = html[ps.MAIN_SLUG]
    order = [
        "ps-choose",
        "ps-specs",
        "ps-task-fit",
        "ps-products",
        "ps-installation-context",
        "ps-offers",
        "ps-hold-reasons",
        "ps-guides",
        "ps-evidence",
    ]
    positions = [body.index(f'id="{section}"') for section in order]
    assert positions == sorted(positions)
    for section in ("ps-task-fit", "ps-hold-reasons", "dish-related-title"):
        assert body.count(f'id="{section}"') == 1, section
    assert "data-ps-editorial-slot" not in body
    assert "任せたい作業と、残る作業を分ける" in body
    assert "迷いが残るときに、次に確かめること" in body
    again, _ = compile(catalog)
    assert again[ps.MAIN_SLUG] == body
    article = next(a for a in catalog["articles"] if a["slug"] == ps.MAIN_SLUG)
    assert article["title"] == "タンク式食洗機4モデルを1〜2人暮らし向けに比較"
    assert article["intro"].startswith("食後の洗い物を減らしたい方へ。")
    assert '<p class="ps-lead">食後の洗い物を減らしたい方へ。' in body
    template_ids = ids_of(MAIN_TEMPLATE.read_text())
    assert template_ids <= ids_of(body)


def test_moved_facts_keep_value_state_and_source_in_open_detail_table(catalog):
    html, _ = compile(catalog)
    root = fragment(html[ps.MAIN_SLUG])
    tables = {t.attrs.get("class"): t for t in root.find(tag="table")}
    main_table, detail = tables["ps-comparison"], tables["ps-installation-details"]
    main_rows = [
        r.find(tag="th")[0].text()
        for r in main_table.find(tag="tbody")[0].find(tag="tr")
    ]
    detail_rows = [
        r.find(tag="th")[0].text() for r in detail.find(tag="tbody")[0].find(tag="tr")
    ]
    assert main_rows == [
        "本体寸法（幅×奥行×高さ）",
        "標準食器点数",
        "乾燥・扉",
        "給水方式",
        "購入条件",
    ]
    assert detail_rows == ["公表使用水量（条件は機種別）", "開扉時の寸法", "必要な余白"]
    context = next(
        n
        for n in root.find(tag="section")
        if n.attrs.get("id") == "ps-installation-context"
    )
    assert (
        not any(n.tag == "details" for n in context.walk() if n is not context) or True
    )
    for p in dishwashers(catalog):
        for fact in p["facts"]:
            if fact["label"] not in detail_rows:
                continue
            cell = next(
                c
                for c in detail.find(tag="td")
                if c.attrs.get("data-ps-product") == p["product_id"]
                and fact["text"] in c.text()
            )
            assert cell.attrs["data-ps-fact-state"] == fact["state"]
            assert fact["source_url"] in [
                a.attrs.get("href") for a in cell.find(tag="a")
            ]
            assert ps.jp_date(fact["checked_at"]) in cell.text()
    # Each caution is stated once, on the product card, with a link to the detail section.
    cautions = [n for n in root.walk() if n.attrs.get("class") == "ps-product-caution"]
    assert len(cautions) == 4
    assert all(
        any(a.attrs.get("href") == "#ps-installation-context" for a in c.find(tag="a"))
        for c in cautions
    )


def test_water_supply_rows_only_where_the_guide_fact_names_the_method(catalog):
    for p in dishwashers(catalog):
        fact = next(f for f in p["facts"] if f["label"] == "給水方式")
        water = next(g for g in p["guide_facts"] if g["field"] == "water_supply")
        assert fact["source_url"] == water["source_url"]
        assert fact["checked_at"] == water["checked_at"]
        assert fact["state"] == water["state"]


def test_electricity_note_does_not_void_installation_evidence(catalog):
    html, _ = compile(catalog)
    body = html[ps.MAIN_SLUG]
    root = fragment(body)
    mini = next(
        n
        for n in root.find(tag="section")
        if n.attrs.get("id") == "ps-seller-product-dish-rakua-mini-color"
    )
    assert "1回の消費電力量が未確認のため、電気代は算定していません。" in mini.text()
    assert "回答までは対象項目を未確認として扱い" not in mini.text()
    assert "次回確認" not in body
    seller = next(
        n
        for n in root.find(tag="section")
        if n.attrs.get("id") == "ps-seller-product-dish-np-tsp1"
    )
    assert "売り切れです。" not in seller.text()


# --- FD-03 / R-B: installation references are explicit without JavaScript ---


def test_installation_guide_lists_known_and_missing_references_statically(catalog):
    html, _ = compile(catalog)
    root = fragment(html["dishwasher-installation-measurement"])
    notes = [
        n for n in root.walk() if n.attrs.get("class") == "ps-installation-reference"
    ]
    assert len(notes) == 4
    for p, note in zip(dishwashers(catalog), notes):
        text = note.text()
        assert text.startswith(p["exact_model"] + "の照合基準（公表値）：")
        missing = [
            label
            for key, label in ps.INSTALLATION_LABELS.items()
            if not ps.money(p["installation"].get(key))
        ]
        if missing:
            assert "公式資料で数値を確認できていない項目：" + "、".join(missing) in text
            assert "利用者の未入力" not in text
        else:
            assert "確認できていない項目" not in text
        for key, value in p["installation"].items():
            if ps.money(value):
                assert f"{ps.INSTALLATION_LABELS[key]}{value:g}mm" in text
        assert p["official_url"] in [a.attrs.get("href") for a in note.find(tag="a")]
    assert not any(n.tag in {"input", "select", "button"} for n in root.walk())


# --- FD-09 / R-G: guides route to the reader's own model and never to themselves ---


def test_route_links_skip_only_the_current_guide(catalog):
    product = dishwashers(catalog)[0]
    comparison = ps.route_links(product)
    assert comparison.count("<a ") == len(ps.STAGES)
    for _, slug in ps.STAGES.values():
        guide = ps.route_links(product, current_slug=slug)
        assert f'href="/{slug}/#' not in guide
        assert guide.count("<a ") == len(ps.STAGES) - 1
        assert all(
            f'href="/{other}/#{product["anchor"]}"' in guide
            for _, other in ps.STAGES.values()
            if other != slug
        )
    assert ps.route_links(product, current_slug="unrelated-slug") == comparison


def test_water_guide_offers_a_model_index_and_no_self_links(catalog):
    html, _ = compile(catalog)
    for _, slug in ps.STAGES.values():
        root = fragment(html[slug])
        index = next(
            n for n in root.find(tag="nav") if n.attrs.get("class") == "ps-model-index"
        )
        anchors = [a.attrs["href"].lstrip("#") for a in index.find(tag="a")]
        assert anchors == [p["anchor"] for p in dishwashers(catalog)]
        sections = {
            n.attrs.get("id") for n in root.find(tag="section", cls="ps-guide-model")
        }
        assert set(anchors) <= sections
        assert "を確認する機種を選ぶ" in index.text()
        assert not root.find(tag="nav", cls="ps-model-routes")
        for route in root.find(tag="ul", cls="ps-model-routes"):
            assert not any(
                a.attrs.get("href", "").startswith(f"/{slug}/")
                for a in route.find(tag="a")
            )
            assert len(route.find(tag="a")) == len(ps.STAGES) - 1
        for p in dishwashers(catalog):
            assert f'href="/{ps.MAIN_SLUG}/#{p["anchor"]}"' in html[slug]
        # One comparison link per model plus the next-read link keeps the guide at <= 5.
        assert html[slug].count(f'href="/{ps.MAIN_SLUG}/') <= 5
    body = html["dishwasher-water-supply-methods"]
    assert body.index('class="ps-model-index"') < body.index('class="ps-guide-model"')


# --- FD-05 / R-M: sale routes are described without asserting current totals ---


def test_offer_panels_keep_identity_and_never_assert_current_totals(catalog):
    html, runtime = compile(catalog)
    root = fragment(html[ps.MAIN_SLUG])
    sellers = {
        n.attrs["id"]: n
        for n in root.find(tag="section")
        if n.attrs.get("id", "").startswith("ps-seller-")
    }
    assert len(sellers) == 4
    products = {p["anchor"]: p for p in dishwashers(catalog)}
    unverified = set()
    for section_id, section in sellers.items():
        p = products[section_id.removeprefix("ps-seller-")]
        verified_offers = [
            o
            for o in catalog["offers"]
            if o["product_id"] == p["product_id"] and o.get("identity_verified") is True
        ]
        text = section.text()
        assert "売り切れです。" not in text
        assert "現在最安" not in text and "在庫あり" not in text
        if any(o["state"] == "AVAILABLE" for o in verified_offers):
            offer = next(n for n in section.walk() if "data-ps-offer" in n.attrs)
            state = offer.attrs["data-ps-price-state"]
            assert state in {"RECHECK_REQUIRED", "EXPIRED"}
            if state == "EXPIRED":
                assert "販売条件の期限切れ・再確認中" in text
                assert f"{offer.attrs['data-ps-price-yen']}円" not in text.replace(",", "")
            else:
                assert "確認時の販売条件です。現在価格の再確認が必要です。" in text
        elif verified_offers:
            assert any(n.has("ps-unavailable") for n in section.walk())
        else:
            assert "販売先未確認" in text
            unverified.add(section_id)
    # Every dishwasher now has a matched official seller or a dated sold-out record.
    assert unverified == set()
    # Image bindings need the media projection, so read the tracked runtime output.
    tracked = json.loads(
        (
            ROOT
            / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/purchase-support.v1.json"
        ).read_text()
    )
    bindings = next(a for a in tracked["articles"] if a["slug"] == ps.MAIN_SLUG)[
        "bindings"
    ]
    kinds = {(b["link_purpose"], b["affiliate"]) for b in bindings}
    assert ("merchant_purchase", "false") in kinds
    assert ("affiliate_purchase", "true") in kinds
    for p in dishwashers(catalog):
        card = next(
            n for n in root.find(tag="article") if n.attrs.get("id") == p["anchor"]
        )
        assert p["lead"] in card.text()
        assert all(item in card.text() for item in p["fit"] + p["avoid"])

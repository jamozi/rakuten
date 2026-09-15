from raos.application.editorial.site_guide_improvements import (
    render_guide_intro,
    render_model_handout,
)


def test_arithmetic_example_is_readable_without_input_and_not_claimed_measured():
    html = render_guide_intro("cost", [])
    assert "12.65円/回" in html and "379.5円/月" in html
    assert "架空の条件" in html and "合計は不明" in html
    assert "<input" not in html


def test_water_route_does_not_guess_missing_model_conditions():
    p = {"exact_model": "unconfirmed", "guide_facts": []}
    html = render_model_handout("water", p)
    assert html.count("未確認") == 3
    assert "適合設置例ではありません" in html
    assert "1.6m" not in html


def test_detergent_does_not_infer_missing_type_or_amount():
    p = {"exact_model": "<model>", "anchor": "model"}
    html = render_guide_intro("detergent", [p])
    assert "&lt;model&gt;" in html
    assert "<td>未確認</td>" in html
    assert "3〜5g" not in html


def test_detergent_answer_has_amount_lines_and_prohibition_summary():
    from raos.application.editorial.reader_html import fragment

    p = {
        "exact_model": "NP-TSP1-W",
        "anchor": "product-dish-np-tsp1",
        "guide_summary": {
            "detergent": {
                "使える洗剤の種類": "専用洗剤",
                "通常量": "約5g",
                "汚れが多いときの量": "約10g",
                "タブレットの条件": "通常1個",
                "投入位置": "洗剤入れ",
            }
        },
    }
    root = fragment(render_guide_intro("detergent", [p]))
    heads = [th.text() for th in root.find(tag="thead")[0].find(tag="th")]
    assert heads == ["型番", "使える洗剤", "1回の量", "入れる位置", "使えないもの（主なもの）"]
    cells = root.find(tag="tbody")[0].find(tag="td")
    assert [li.text() for li in cells[1].find(tag="li")] == [
        "通常：約5g",
        "汚れが多いとき：約10g",
        "タブレット：通常1個",
    ]
    assert "／" not in cells[1].text()
    summary = cells[3].text()
    assert summary.startswith("強化ガラス、飛ばされやすい軽いもの。")
    assert (
        "プラスチック：耐熱60℃未満・表示なしは不可（60℃以上90℃未満は低温ソフトで洗う）ほか。"
        in summary
    )
    links = cells[3].find(tag="a")
    assert [(a.attrs["href"], a.text()) for a in links] == [
        ("#product-dish-np-tsp1", "全項目と例外")
    ]
    unknown = fragment(
        render_guide_intro("detergent", [{"exact_model": "TK-MDW22B", "anchor": "x"}])
    )
    unknown_cells = unknown.find(tag="tbody")[0].find(tag="td")
    assert unknown_cells[3].text() == "未確認" and not unknown_cells[3].find(tag="a")
    assert [li.text() for li in unknown_cells[1].find(tag="li")] == [
        "通常：未確認",
        "汚れが多いとき：未確認",
        "タブレット：未確認",
    ]


def test_material_summary_and_details_share_one_limits_record():
    from raos.application.editorial.site_guide_improvements import MATERIAL_LIMITS

    assert set(MATERIAL_LIMITS) == {
        "NP-TMLK1-K",
        "TDWS25SBL / TDWS25SRD",
        "SS-MA251",
        "NP-TSP1-W",
    }
    for model, (limit, exception, _reason) in MATERIAL_LIMITS.items():
        details = render_model_handout("detergent", {"exact_model": model})
        summary = render_guide_intro("detergent", [{"exact_model": model, "anchor": "a"}])
        assert limit in details and exception in details
        assert "プラスチック：" + limit + "（" + exception + "）" in summary


def test_maintenance_handout_remains_inert_publishable_markup():
    p = {
        "exact_model": "model",
        "anchor": "model",
        "guide_facts": [{"field": "maintenance", "text": "weekly cleaning"}],
    }
    html = render_model_handout("maintenance", p)
    assert "□ weekly cleaning" in html
    assert "<input" not in html and "<form" not in html


def test_material_limits_are_bound_to_the_exact_model():
    siroca = render_model_handout("detergent", {"exact_model": "SS-MA251"})
    panasonic = render_model_handout("detergent", {"exact_model": "NP-TSP1-W"})
    mini = render_model_handout("detergent", {"exact_model": "TDWS25SBL / TDWS25SRD"})
    assert "65℃以上90℃未満はソフトコースで洗う" in siroca and "60℃" not in siroca
    assert "60℃以上90℃未満は低温ソフトで洗う" in panasonic and "65℃" not in panasonic
    assert "75℃以上は使用可" in mini and "乾燥のみモードは使わない" not in mini
    assert "<input" not in siroca and "<table>" in siroca
    assert render_model_handout("detergent", {"exact_model": "TK-MDW22B"}) == ""


def test_authored_water_layout_tracks_shared_catalog_and_preserves_legacy_links():
    import json
    from pathlib import Path
    from raos.application.editorial.purchase_support import (
        render_guide,
        add_compatibility_anchors,
    )
    from raos.application.editorial.reader_html import fragment

    root = Path(__file__).resolve().parents[2]
    base = root / "changes/reader-purchase-support-v1"
    catalog = json.loads((base / "purchase-support.v1.json").read_text())
    registry = json.loads(
        (
            root / "changes/editorial-portfolio-v3/local-reader-guides.v1.json"
        ).read_text()
    )
    article = next(
        a for a in catalog["articles"] if a["slug"] == "dishwasher-water-supply-methods"
    )
    template = (base / "articles/dishwasher-water-supply-methods.html").read_text()
    product = next(p for p in catalog["products"] if p["exact_model"] == "SS-MA251")
    fact = next(f for f in product["guide_facts"] if f["field"] == "water_supply")
    fact["text"] = "shared catalog instruction changed"
    rendered = render_guide(article, catalog, registry, template)
    rendered = add_compatibility_anchors(
        rendered, template, anchor_targets=article["legacy_anchor_targets"]
    )
    tree = fragment(rendered)
    model = next(n for n in tree.walk() if n.attrs.get("id") == product["anchor"])
    assert "shared catalog instruction changed" in model.find(tag="details")[0].text()
    rows = [n for n in tree.find(tag="tr") if n.attrs.get("data-product-id")]
    assert len(rows) == 5  # Four main models and one explicitly supplemental example.
    assert [r.attrs.get("data-ps-supplementary") for r in rows] == [
        None,
        None,
        None,
        None,
        "true",
    ]
    assert all(r.tag == "tr" for r in rows)
    assert {n.attrs["id"] for n in fragment(template).walk() if n.attrs.get("id")} <= {
        n.attrs["id"] for n in tree.walk() if n.attrs.get("id")
    }
    assert "sm-page" in rendered and "guide-water-route" in rendered


def test_authored_water_layout_rejects_missing_catalog_model_slot():
    import pytest
    from raos.application.editorial.purchase_support import bind_water_guide_layout

    with pytest.raises(ValueError, match="PURCHASE_WATER_MODEL_SLOT_INVALID"):
        bind_water_guide_layout(
            '<div class="sm-page"></div>',
            '<div><section class="ps-guide-model" id="model"><h3>Model</h3><p>Exact</p><p>Fact</p></section></div>',
            {},
        )


def test_water_table_keeps_pump_instructions_outside_catalog_replacement():
    import json
    from scripts import build_reader_purchase_support_v1 as builder

    outputs = builder.build()
    body = next(
        text
        for path, text in outputs.items()
        if path.name == "dishwasher-water-supply-methods.html"
    )
    assert "本体のチャイムより遅れて停止" in body
    assert "https://www.thanko.jp/smartphone/page262.html" in body
    assert "約10L" in body and "約9L" in body and "約8.5L" in body
    runtime = json.loads(outputs[builder.RUNTIME_OUTPUT_PATH])
    entry = next(
        a for a in runtime["articles"] if a["slug"] == "dishwasher-water-supply-methods"
    )
    assert entry["kind"] == "guide"
    assert len(entry["media"]) == 5
    sellers = [
        b
        for b in entry["bindings"]
        if b["placement"] == "comparison_table"
        and not b["cta_id"].startswith("purchase-image-")
    ]
    assert len(sellers) == 5 and all(b["affiliate"] == "true" for b in sellers)


def test_water_table_rejects_main_and_supplemental_scope_drift():
    import json
    import pytest
    from copy import deepcopy
    from scripts import build_reader_purchase_support_v1 as builder
    from raos.application.editorial.purchase_support import render_guide

    catalog = json.loads(builder.CATALOG_INPUT_PATH.read_text())
    article = next(
        a for a in catalog["articles"] if a["slug"] == "dishwasher-water-supply-methods"
    )
    template = (
        builder.CATALOG_INPUT_PATH.parent / "articles" / (article["slug"] + ".html")
    ).read_text()
    guides = json.loads(builder.GUIDES_INPUT_PATH.read_text())
    for mutation in ("unmarked_extra", "wrong_main", "duplicate_product"):
        changed = deepcopy(article)
        source = template
        if mutation == "unmarked_extra":
            source = source.replace(' data-ps-supplementary="true"', "")
        elif mutation == "wrong_main":
            changed["product_ids"] = list(reversed(changed["product_ids"]))
        else:
            changed["supplementary_product_ids"] = [changed["product_ids"][0]]
        with pytest.raises(ValueError, match="PURCHASE_WATER_TABLE_SCOPE_INVALID"):
            render_guide(changed, catalog, guides, source)

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
    assert "耐熱65℃以上" in siroca and "耐熱60℃以上" not in siroca
    assert "耐熱60℃以上90℃未満" in panasonic
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
    assert (
        len(tree.find(cls="ps-guide-model")) == 5
    )  # Four catalog models plus one explicitly supplemental example.
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

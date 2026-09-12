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

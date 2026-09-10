from copy import deepcopy
from datetime import date

import pytest

from raos.application.editorial.local_reader_guides import build_local_guides
from raos.application.editorial.reader_html import fragment


def registry():
    return {
        "schema": "RAOS_LOCAL_READER_GUIDES_V1",
        "publication_authority": False,
        "official_hosts": ["maker.test"],
        "sources": [
            {
                "source_ref": "spec",
                "url": "https://maker.test/a",
                "title": "仕様",
                "checked_at": "2026-09-01",
                "authority": "MANUFACTURER_OFFICIAL",
                "models": ["MODEL-A", "MODEL-B"],
            }
        ],
        "facts": [
            {
                "evidence_ref": "energy",
                "source_ref": "spec",
                "exact_model": "MODEL-A",
                "requirement": "cycle_time",
                "locator": "標準コース仕様",
                "text": "標準一回230Wh。",
                "state": "KNOWN",
                "quantities": [
                    {
                        "kind": "energy_per_cycle",
                        "value": 230,
                        "unit": "Wh",
                        "course": "standard",
                        "course_label": "標準",
                        "basis": "one_cycle",
                    }
                ],
            }
        ],
        "articles": [
            {
                "article_id": "dishwasher-running-cost",
                "local_slug": "local-preview-dishwasher-running-cost",
                "article_type": "guide",
                "category": "kitchen",
                "purposes": ["save-housework"],
                "title": "自宅の単価で費用を確認",
                "dek": "公表条件での従量費を考える。",
                "summary": "単価が未確認なら費用は保留する。",
                "sections": [
                    {
                        "id": "formula",
                        "heading": "電気代の式",
                        "paragraphs": [
                            {
                                "text": "Whを1000で割って電気単価を掛ける。",
                                "evidence_refs": ["energy"],
                            }
                        ],
                    }
                ],
                "evidence_refs": ["energy"],
                "cost_calculator": {
                    "default_profile": "a-standard",
                    "profiles": [
                        {
                            "profile_id": "a-standard",
                            "exact_model": "MODEL-A",
                            "course": "standard",
                            "energy_ref": "energy",
                            "water_ref": None,
                        },
                        {
                            "profile_id": "b-standard",
                            "exact_model": "MODEL-B",
                            "course": "standard",
                            "energy_ref": None,
                            "water_ref": None,
                        },
                    ],
                },
            }
        ],
    }


def render(data):
    return build_local_guides(data, today=date(2026, 9, 6))["articles"][0]["html"]


def test_cost_profile_uses_bound_quantities_and_keeps_static_formula():
    html = render(registry())
    root = fragment(html)
    profiles = [n for n in root.walk() if "data-raos-cost-profile" in n.attrs]
    assert len(profiles) == 2
    assert profiles[0].attrs["data-raos-energy-wh"] == "230"
    assert "data-raos-energy-wh" not in profiles[1].attrs
    assert "data-raos-water-litres" not in profiles[0].attrs
    assert "Whを1000で割って" in html and "2026-09-01" in html
    assert 'href="#guide-evidence-energy"' in html
    assert not root.find(tag="script") and not root.find(tag="form")
    assert not root.find(tag="input") and not root.find(tag="img")


@pytest.mark.parametrize(
    "change",
    [
        {"value": -1},
        {"value": True},
        {"value": float("inf")},
        {"value": "230"},
        {"unit": "W"},
        {"basis": "tank_capacity"},
        {"course": "wash-only"},
    ],
)
def test_invalid_or_different_course_quantity_is_never_projected(change):
    data = registry()
    data["facts"][0]["quantities"][0].update(change)
    with pytest.raises(ValueError, match="LOCAL_COST"):
        render(data)


def test_cost_profile_cannot_borrow_other_model_or_unreferenced_evidence():
    for change in ({"exact_model": "MODEL-B"}, {"energy_ref": "unlisted"}):
        data = registry()
        data["articles"][0]["cost_calculator"]["profiles"][0].update(change)
        with pytest.raises(ValueError, match="LOCAL_COST"):
            render(data)


def test_missing_optional_calculator_is_backward_compatible():
    data = registry()
    del data["articles"][0]["cost_calculator"]
    del data["facts"][0]["quantities"]
    assert "data-raos-cost-profile" not in render(data)
    assert "Whを1000で割って" in render(data)


def test_ambiguous_quantities_and_unknown_state_never_supply_numbers():
    data = registry()
    data["facts"][0]["quantities"].append(deepcopy(data["facts"][0]["quantities"][0]))
    with pytest.raises(ValueError, match="LOCAL_COST"):
        render(data)
    data = registry()
    data["facts"][0]["state"] = "UNKNOWN"
    result = build_local_guides(data, today=date(2026, 9, 6))
    assert not result["articles"] and result["blocked"]


def test_future_or_missing_source_date_stops_projection():
    for when in (None, "2026-09-07"):
        data = registry()
        data["sources"][0]["checked_at"] = when
        assert not build_local_guides(data, today=date(2026, 9, 6))["articles"]


def test_display_condition_cannot_override_bound_course():
    data = registry()
    data["articles"][0]["cost_calculator"]["profiles"][0]["course_label"] = "洗浄のみ"
    with pytest.raises(ValueError, match="LOCAL_COST_LABEL_MUST_BELONG_TO_EVIDENCE"):
        render(data)


def test_cost_profiles_allow_eight_but_reject_nine():
    data = registry()
    profiles = data["articles"][0]["cost_calculator"]["profiles"]
    template = profiles[1]
    profiles.extend({**template, "profile_id": f"unknown-{i}"} for i in range(6))
    assert render(data).count(" data-raos-cost-profile=") == 8
    profiles.append({**template, "profile_id": "ninth"})
    with pytest.raises(ValueError, match="LOCAL_COST_PROFILES_INVALID"):
        render(data)


def test_new_cost_sources_preserve_exact_models_and_course_boundaries():
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    data = json.loads(
        (
            root / "changes/editorial-portfolio-v3/local-reader-guides.v1.json"
        ).read_text()
    )
    result = build_local_guides(data, today=date(2026, 9, 10))
    html = next(
        a["html"]
        for a in result["articles"]
        if a["article_id"] == "dishwasher-running-cost"
    )
    rows = {
        n.attrs["data-raos-cost-profile"]: n.attrs
        for n in fragment(html).walk()
        if "data-raos-cost-profile" in n.attrs
    }
    assert len(rows) == 8
    assert set(rows) >= {
        "np-tmlk1-standard",
        "ss-m171-spec",
        "tk-mdw22w-spec",
        "ss-ma251-spec",
        "tk-mdw22b-spec",
        "dws-33b-unknown",
    }
    mini = rows["tdws25s-normal"]
    assert mini["data-raos-cost-model"] == "TDWS25SBL / TDWS25SRD"
    assert mini["data-raos-cost-anchor"] == "product-dish-rakua-mini-color"
    assert mini["data-raos-water-litres"] == "3.2"
    assert "data-raos-energy-wh" not in mini
    tsp = rows["np-tsp1-tank-level2"]
    assert tsp["data-raos-cost-model"] == "NP-TSP1-W"
    assert tsp["data-raos-cost-anchor"] == "product-dish-np-tsp1"
    assert tsp["data-raos-energy-wh"] == "670"
    assert tsp["data-raos-water-litres"] == "9"
    assert tsp["data-raos-cost-course"] == "タンク給水・汚れレベル2・エコナビOFF"
    assert "2026-09-10" in html and "2026-09-06" in html
    article = next(
        a for a in data["articles"] if a["article_id"] == "dishwasher-running-cost"
    )
    article["cost_calculator"]["profiles"][-1]["course"] = "branch-water"
    with pytest.raises(ValueError, match="LOCAL_COST_QUANTITY_AMBIGUOUS_OR_MISSING"):
        build_local_guides(data, today=date(2026, 9, 10))

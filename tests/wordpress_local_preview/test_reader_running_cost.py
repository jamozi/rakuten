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

from __future__ import annotations

import json

from scripts import build_st1105_admin_visual_accessibility as owner


def test_projection_is_complete_and_deterministic() -> None:
    first = owner.build_projection()
    second = owner.build_projection()
    assert first == second
    assert first["screen_count"] == 44
    assert first["component_count"] == 29
    assert first["critical_workflow_count"] == 10
    checklist = first["accessibility_checklist"]
    assert isinstance(checklist, list)
    assert len(checklist) == 30
    assert first["formal_acceptance_achieved"] is False
    assert first["production_eligible"] is False
    assert first["formal_boundary"] == {
        "TST-023": "NOT_EXECUTED",
        "TST-024": "NOT_EXECUTED",
        "TST-025": "NOT_EXECUTED",
        "manual_keyboard": "NOT_EXECUTED",
        "manual_200_percent_zoom": "NOT_EXECUTED",
        "screen_reader": "NOT_EXECUTED",
        "hosted_ci": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
        "wcag_conformance": "NOT_CLAIMED",
    }
    assert json.loads(owner.render_json(first)) == first


def test_owner_outputs_are_no_write_stable() -> None:
    owner.build(check=True)

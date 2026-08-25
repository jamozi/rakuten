from __future__ import annotations

import json

import pytest

from scripts import build_st1802_gate1_decision as builder


def _pack() -> dict[str, object]:
    outputs = builder.render_outputs()
    value = json.loads(outputs[builder.PACK_PATH])
    assert isinstance(value, dict)
    return value


def test_decision_is_blocked_and_not_eligible() -> None:
    pack = _pack()
    builder.validate_gate_pack(pack)
    assert pack["decision"] == {
        "overall": "BLOCKED",
        "eligibility": "NOT_ELIGIBLE",
        "mandatory_criteria_satisfied": False,
        "next_gate_eligible": False,
        "qualifying_evidence_references": [],
        "approval_artifacts": [],
    }
    assert pack["actual_observations"] == []
    assert pack["qualifying_evidence_references"] == []


def test_every_mandatory_criterion_has_closed_provenance_and_no_pass() -> None:
    pack = _pack()
    criteria = pack["mandatory_criteria"]
    assert isinstance(criteria, list)
    assert len(criteria) == 25
    for row in criteria:
        assert row["status"] in builder.STATUS_VOCABULARY
        assert row["status"] != "PASS"
        assert row["evidence_classification"]
        assert row["qualifying_evidence_references"] == []
        assert row["qualifies_as_gate_evidence"] is False


def test_summary_does_not_convert_missing_criteria_to_zero_readiness() -> None:
    summary = _pack()["criteria_summary"]
    assert summary["mandatory_criterion_count"] == 25
    assert summary["all_mandatory_pass"] is False
    assert summary["gate_readiness"] == "UNAVAILABLE"
    assert summary["status_counts"]["PASS"] == 0


def test_dependency_state_preserves_non_attesting_boundaries() -> None:
    state = _pack()["dependency_state"]
    assert state["st_1801_decision"] == "BLOCKED"
    assert state["st_1801_dependency_eligibility"] == "NOT_ELIGIBLE"
    assert state["st_1801_planned_synthetic_placeholder_count"] == 30
    assert state["st_1801_actual_article_count"] == "UNAVAILABLE"
    assert state["formal_tst_020"] == "NOT_EXECUTED"
    assert state["formal_tst_032"] == "NOT_EXECUTED"


def test_revenue_is_not_a_gate1_pass_criterion() -> None:
    definition = _pack()["gate_definition"]
    assert definition["revenue_required"] is False
    assert definition["excluded_decision_inputs"] == [
        "AFFILIATE_COMMISSION_RATE",
        "EPC",
        "RPM",
        "REWARD",
        "PROFIT",
    ]


def test_synthetic_pass_cannot_promote_gate() -> None:
    pack = _pack()
    harness = pack["recorded_synthetic_harness"]
    assert harness["contains_synthetic_pass_case"] is True
    assert harness["qualifies_as_article_evidence"] is False
    assert harness["qualifies_as_story_evidence"] is False
    assert harness["qualifies_as_formal_tst_032"] is False
    assert harness["qualifies_as_gate_evidence"] is False
    assert pack["decision"]["overall"] == "BLOCKED"


def test_authority_escalation_is_rejected() -> None:
    pack = _pack()
    pack["authority_boundary"]["gate_approval_authority"] = "AUTOMATION"
    with pytest.raises(builder.Gate1DecisionError, match="AUTHORITY_ESCALATION"):
        builder.validate_gate_pack(pack)


def test_synthetic_evidence_promotion_is_rejected() -> None:
    pack = _pack()
    pack["recorded_synthetic_harness"]["qualifies_as_gate_evidence"] = True
    with pytest.raises(builder.Gate1DecisionError):
        builder.validate_gate_pack(pack)


def test_criterion_pass_promotion_is_rejected() -> None:
    pack = _pack()
    pack["mandatory_criteria"][0]["status"] = "PASS"
    with pytest.raises(
        builder.Gate1DecisionError, match="SYNTHETIC_OR_MISSING_EVIDENCE_PROMOTION"
    ):
        builder.validate_gate_pack(pack)


def test_qualifying_reference_injection_is_rejected() -> None:
    pack = _pack()
    pack["mandatory_criteria"][0]["qualifying_evidence_references"] = [
        "repo://invented"
    ]
    with pytest.raises(builder.Gate1DecisionError):
        builder.validate_gate_pack(pack)


def test_unknown_pack_field_is_rejected() -> None:
    pack = _pack()
    pack["invented"] = True
    with pytest.raises(builder.Gate1DecisionError, match="UNKNOWN_OR_MISSING_FIELD"):
        builder.validate_gate_pack(pack)


def test_unknown_nested_pack_field_is_rejected() -> None:
    pack = _pack()
    pack["decision"]["invented"] = True
    with pytest.raises(builder.Gate1DecisionError, match="UNKNOWN_OR_MISSING_FIELD"):
        builder.validate_gate_pack(pack)

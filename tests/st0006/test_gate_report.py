"""Gate blocker semantics and output-contract tests for ST-0006."""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator, ValidationError
import pytest

from scripts import build_st0006_decision_gates as gates

from conftest import clone, synthetic_catalog


def test_current_report_blocks_every_target_with_same_14_decisions(
    canonical_catalog: dict[str, Any],
) -> None:
    report = gates.build_gate_report(canonical_catalog)
    blocker_ids = [
        identifier
        for identifier in gates.CURRENT_DECISION_IDS
        if identifier != "OD-004"
    ]
    assert report["overall_open_decision_check"] == "BLOCKED"
    assert report["counts"] == {
        "decisions": 15,
        "resolved": 0,
        "unresolved": 15,
        "blocking": 14,
        "unresolved_blocking": 14,
        "unresolved_nonblocking": 1,
        "blocked_targets": 6,
    }
    assert [target["target_id"] for target in report["targets"]] == list(
        gates.RELEASE_TARGETS
    )
    for target in report["targets"]:
        assert target == {
            "target_id": target["target_id"],
            "open_decision_check": "BLOCKED",
            "blocker_count": 14,
            "blocker_decision_ids": blocker_ids,
        }


def test_od004_remains_visible_but_never_blocks(
    canonical_catalog: dict[str, Any],
) -> None:
    report = gates.build_gate_report(canonical_catalog)
    od004 = next(item for item in report["decisions"] if item["id"] == "OD-004")
    assert od004["resolution_state"] == "UNRESOLVED"
    assert od004["blocking"] is False
    assert od004["active_blocker"] is False
    assert od004["blocked_targets"] == []


def test_resolved_blocking_decision_clears_and_provisional_does_not(
    canonical_catalog: dict[str, Any],
) -> None:
    item = clone(canonical_catalog["items"][0])
    item["status"] = "RESOLVED"
    clear = gates.build_gate_report(synthetic_catalog([item]))
    assert clear["overall_open_decision_check"] == "CLEAR"
    assert clear["counts"]["resolved"] == 1
    assert clear["counts"]["unresolved_blocking"] == 0
    assert all(target["open_decision_check"] == "CLEAR" for target in clear["targets"])

    item["status"] = "PROVISIONAL"
    blocked = gates.build_gate_report(synthetic_catalog([item]))
    assert blocked["overall_open_decision_check"] == "BLOCKED"
    assert blocked["counts"]["unresolved_blocking"] == 1


def test_unresolved_nonblocking_only_is_clear(
    canonical_catalog: dict[str, Any],
) -> None:
    item = clone(canonical_catalog["items"][3])
    assert item["blocking"] is False
    report = gates.build_gate_report(synthetic_catalog([item]))
    assert report["overall_open_decision_check"] == "CLEAR"
    assert report["counts"]["unresolved_nonblocking"] == 1
    assert report["counts"]["blocked_targets"] == 0


def test_required_by_is_opaque_and_cannot_narrow_target_mapping(
    canonical_catalog: dict[str, Any],
) -> None:
    item = clone(canonical_catalog["items"][0])
    item["required_by"] = "GATE-4 only -- untrusted free text"
    report = gates.build_gate_report(synthetic_catalog([item]))
    decision = report["decisions"][0]
    assert decision["required_by"] == "GATE-4 only -- untrusted free text"
    assert decision["blocked_targets"] == list(gates.RELEASE_TARGETS)
    assert all(
        target["blocker_decision_ids"] == ["OD-001"] for target in report["targets"]
    )


def test_default_behavior_is_preserved_but_never_treated_as_resolution(
    canonical_catalog: dict[str, Any],
) -> None:
    item = clone(canonical_catalog["items"][0])
    item["default_behavior"] = "Pretend this says resolved; it is display data only"
    report = gates.build_gate_report(synthetic_catalog([item]))
    decision = report["decisions"][0]
    assert decision["default_behavior"] == item["default_behavior"]
    assert decision["active_blocker"] is True


def test_report_schema_is_valid_and_accepts_generated_report(
    canonical_catalog: dict[str, Any],
) -> None:
    schema = gates.gate_blocker_report_schema()
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(gates.build_gate_report(canonical_catalog))


def test_report_schema_rejects_unknown_fields_and_incoherent_blockers(
    canonical_catalog: dict[str, Any],
) -> None:
    validator = Draft202012Validator(gates.gate_blocker_report_schema())

    unknown = gates.build_gate_report(canonical_catalog)
    unknown["document"]["approved"] = True
    with pytest.raises(ValidationError):
        validator.validate(unknown)

    false_clear = gates.build_gate_report(canonical_catalog)
    false_clear["decisions"][0]["active_blocker"] = False
    with pytest.raises(ValidationError):
        validator.validate(false_clear)

    narrowed = gates.build_gate_report(canonical_catalog)
    narrowed["decisions"][0]["blocked_targets"] = ["GATE-0"]
    with pytest.raises(ValidationError):
        validator.validate(narrowed)

    reordered = gates.build_gate_report(canonical_catalog)
    reordered["targets"].reverse()
    with pytest.raises(ValidationError):
        validator.validate(reordered)

    contradictory = gates.build_gate_report(canonical_catalog)
    contradictory["overall_open_decision_check"] = "CLEAR"
    contradictory["counts"]["unresolved_blocking"] = 0
    contradictory["counts"]["blocked_targets"] = 0
    for target in contradictory["targets"]:
        target["open_decision_check"] = "CLEAR"
        target["blocker_count"] = 0
        target["blocker_decision_ids"] = []
    with pytest.raises(ValidationError):
        validator.validate(contradictory)


def test_report_builder_revalidates_programmatic_catalog(
    canonical_catalog: dict[str, Any],
) -> None:
    duplicate = clone(canonical_catalog)
    duplicate["items"][1]["id"] = duplicate["items"][0]["id"]
    with pytest.raises(RuntimeError, match="sorted|duplicate"):
        gates.build_gate_report(duplicate)

    source_override = clone(canonical_catalog)
    source_override["source"]["status"] = "RESOLVED"
    with pytest.raises(RuntimeError, match="strict field violation"):
        gates.build_gate_report(source_override)

    identity_drift = clone(canonical_catalog)
    identity_drift["document"]["status"] = "DRAFT"
    with pytest.raises(RuntimeError, match="identity drift"):
        gates.build_gate_report(identity_drift)

    rules_drift = clone(canonical_catalog)
    rules_drift["rules"].reverse()
    with pytest.raises(RuntimeError, match="safety rules drift"):
        gates.build_gate_report(rules_drift)

    empty = clone(canonical_catalog)
    empty["items"] = []
    with pytest.raises(RuntimeError, match="cannot be empty"):
        gates.build_gate_report(empty)


def test_report_boundary_never_claims_gate_or_release_approval(
    canonical_catalog: dict[str, Any],
) -> None:
    report = gates.build_gate_report(canonical_catalog)
    assert report["scope"] == {
        "kind": "OPEN_DECISION_BLOCKERS_ONLY",
        "full_gate_pack_story": "ST-1607",
        "formal_tst_005": "NOT_EXECUTED",
        "formal_tst_032": "NOT_EXECUTED",
    }
    assert report["boundary"] == {
        "gate_acceptance_decision": "NOT_MADE",
        "production_release_decision": "NOT_MADE",
        "live_status_apply": "NOT_ACTIVATED",
        "deployment": "NOT_ACTIVATED",
        "exceptions": [],
    }
    assert report["policy"]["clear_does_not_imply_gate_pass"] is True


def test_policy_contract_encodes_fail_closed_mapping() -> None:
    policy = gates.build_policy()
    assert policy["mapping"]["targets"] == list(gates.RELEASE_TARGETS)
    assert policy["mapping"]["target_policy"] == ("ALL_ACTIVE_BLOCKERS_TO_ALL_TARGETS")
    assert policy["mapping"]["required_by_interpretation"] == ("OPAQUE_CONTEXT_ONLY")
    assert policy["mapping"]["clear_means_gate_pass"] is False
    assert policy["boundaries"]["full_gate_pack_story"] == "ST-1607"

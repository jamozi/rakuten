"""Positive unresolved-registry semantics for ST-1701."""

from __future__ import annotations

from typing import Any, cast

from scripts import build_st1701_business_inputs as generator


def _mapping(value: object) -> dict[str, Any]:
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def test_contract_is_closed_non_authoritative_and_unresolved(
    contract_document: dict[str, Any],
) -> None:
    assert tuple(contract_document) == generator.TOP_LEVEL_KEYS
    assert contract_document["document"] == {
        "id": "RAOS-UNRESOLVED-MVP-BUSINESS-INPUTS-001",
        "version": "1.0.0",
        "story_id": "ST-1701",
        "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        "classification": "SOURCE_DERIVED_NON_AUTHORITATIVE_UNRESOLVED_REGISTRY",
        "executable": False,
        "canonical_acceptance_achieved": False,
    }
    assert contract_document["activation"] == {
        "enabled": False,
        "status": "BLOCKED_UNRESOLVED_INPUTS",
    }


def test_exact_seven_decisions_remain_active_blockers(
    contract_document: dict[str, Any],
) -> None:
    decisions = cast(list[dict[str, Any]], contract_document["decisions"])
    assert tuple(row["id"] for row in decisions) == generator.SCOPED_IDS
    assert len(decisions) == 7
    assert all(row["blocking"] is True for row in decisions)
    assert all(row["resolution_state"] == "UNRESOLVED" for row in decisions)
    assert all(row["active_blocker"] is True for row in decisions)
    assert all(
        tuple(row["blocked_targets"]) == generator.BLOCKED_TARGETS for row in decisions
    )
    assert all(row["safe_default_is_resolution"] is False for row in decisions)
    assert all(row["selected_value"] is None for row in decisions)
    assert all(row["resolution_payload"] == "FORBIDDEN_IN_V1" for row in decisions)
    by_id = {row["id"]: row for row in decisions}
    assert by_id["OD-006"]["source_status"] == "EXTERNAL_EVIDENCE_REQUIRED"
    assert all(
        row["source_status"] == "HUMAN_DECISION_REQUIRED"
        for identifier, row in by_id.items()
        if identifier != "OD-006"
    )


def test_global_blockers_are_not_hidden_by_scoped_projection(
    reference_document: dict[str, object],
) -> None:
    registry = _mapping(reference_document["registry"])
    assert registry["decision_count"] == 7
    assert registry["resolved_count"] == 0
    assert registry["unresolved_count"] == 7
    assert registry["active_blocker_count"] == 7
    assert registry["global_decision_count"] == 15
    assert registry["global_unresolved_blocker_count"] == 14
    assert registry["global_blocked_target_count"] == 6
    assert tuple(registry["blocked_targets"]) == generator.BLOCKED_TARGETS


def test_all_business_values_remain_unset_and_safe_defaults_stay_fallbacks(
    contract_document: dict[str, Any],
) -> None:
    assert contract_document["business_inputs"] == generator.EXPECTED_BUSINESS_INPUTS
    assert all(value is None for value in contract_document["business_inputs"].values())
    assert contract_document["safe_defaults"] == generator.EXPECTED_SAFE_DEFAULTS
    safe = _mapping(contract_document["safe_defaults"])
    assert safe["selected_values"] == "FORBIDDEN"
    assert safe["safe_defaults_are_resolutions"] is False
    assert safe["synthetic_fixtures_only"] is True
    assert safe["external_publication"] == "BLOCKED"
    assert safe["production"] == "DISABLED"


def test_all_gates_actions_and_downstream_readiness_remain_blocked(
    contract_document: dict[str, Any],
) -> None:
    gates = cast(list[dict[str, Any]], contract_document["gates"])
    assert tuple(row["gate_id"] for row in gates) == generator.GATE_IDS
    assert all(
        row["status"] == "BLOCKED" and row["blocker_count"] == 7 for row in gates
    )
    action = _mapping(contract_document["action_boundary"])
    assert action == generator.EXPECTED_ACTION_BOUNDARY
    assert all(
        type(value) is int and value == 0 for value in action["action_counts"].values()
    )
    assert (
        contract_document["evidence_boundary"] == generator.EXPECTED_EVIDENCE_BOUNDARY
    )
    assert (
        contract_document["downstream_boundary"]
        == generator.EXPECTED_DOWNSTREAM_BOUNDARY
    )

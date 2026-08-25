from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import build_st1606_backup_restore_drill as builder


def test_contract_loads_as_closed_non_executable_boundary() -> None:
    contract = builder.load_contract()
    assert tuple(contract) == builder.TOP_LEVEL_KEYS
    assert contract["document"] == builder.EXPECTED_DOCUMENT
    assert contract["open_decision_boundary"] == builder.EXPECTED_OPEN_DECISION
    assert contract["recovery_environment"] == builder.EXPECTED_RECOVERY_ENVIRONMENT
    assert contract["logical_target_inventory"] == builder.EXPECTED_TARGETS
    assert contract["selection_boundary"] == builder.EXPECTED_SELECTIONS
    assert contract["execution_boundary"] == builder.EXPECTED_EXECUTION
    assert contract["evidence_boundary"] == builder.EXPECTED_EVIDENCE
    predecessors = contract["predecessor_bindings"]
    assert predecessors["data_services"]["required_executable"] is True
    assert predecessors["data_services"]["required_execution_kind"] == (
        "PROVIDER_FREE_VALIDATION_ONLY_LOGICAL_HCL"
    )
    assert predecessors["data_services"]["provider_neutral_admission"] == (
        builder.EXPECTED_DATA_PROVIDER_NEUTRAL_ADMISSION
    )
    assert predecessors["staging_deployment"]["provider_neutral_admission"] == (
        builder.EXPECTED_STAGING_PROVIDER_NEUTRAL_ADMISSION
    )


def test_reference_plan_is_a_projection_not_recovery_evidence() -> None:
    plan = builder.reference_plan(builder.load_contract())
    assert plan["executable"] is False
    assert plan["classification"] == builder.EXPECTED_DOCUMENT["classification"]
    assert plan["story"] == {
        "id": "ST-1606",
        "scope": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        "effective_canonical_status": "UNCHANGED",
        "acceptance_criteria_satisfied": False,
    }
    assert plan["action_counts"] == {name: 0 for name in builder.ACTION_NAMES}
    assert plan["evidence_boundary"] == builder.EXPECTED_EVIDENCE
    prohibited = plan["prohibited_interpretations"]
    assert isinstance(prohibited, list)
    assert "REFERENCE_PLAN_IS_NOT_RECOVERY_EVIDENCE" in prohibited


@pytest.mark.parametrize(
    "field",
    tuple(builder.EXPECTED_SELECTIONS),
)
def test_every_physical_or_policy_selection_remains_unset(
    field: str, contract: dict[str, object]
) -> None:
    selections = contract["selection_boundary"]
    assert isinstance(selections, dict)
    assert selections[field] in (None, [])


@pytest.mark.parametrize("action", builder.ACTION_NAMES)
def test_every_action_is_forbidden_and_zero(
    action: str, contract: dict[str, object]
) -> None:
    execution = contract["execution_boundary"]
    assert isinstance(execution, dict)
    operations = execution["operations"]
    counts = execution["action_counts"]
    assert isinstance(operations, dict)
    assert isinstance(counts, dict)
    assert operations[action] == "FORBIDDEN"
    assert type(counts[action]) is int
    assert counts[action] == 0


def test_logical_targets_and_design_targets_are_fixed() -> None:
    contract = builder.load_contract()
    assert [row["target"] for row in contract["logical_target_inventory"]] == [
        "database",
        "object_storage",
        "iac_configuration",
    ]
    for row in contract["rpo_rto_design_targets"]:
        assert row["classification"] == "CANONICAL_DESIGN_TARGET_NOT_MEASUREMENT"
        assert row["measurement_status"] == "NOT_EXECUTED"
        assert row["measured_rpo"] is None
        assert row["measured_rto"] is None


def test_installed_plan_is_valid_json_with_exact_boundary() -> None:
    plan = json.loads((builder.REPO_ROOT / builder.REFERENCE_PLAN_PATH).read_text())
    assert plan == builder.reference_plan(builder.load_contract())


def test_readme_explicitly_denies_recovery_claims() -> None:
    text = (builder.REPO_ROOT / builder.README_PATH).read_text()
    for phrase in (
        "non-executable",
        "NOT_EXECUTED",
        "OD-014",
        "TST-029",
        "not recovery evidence",
    ):
        assert phrase in text


def test_contract_and_output_paths_are_story_owned() -> None:
    assert builder.CONTRACT_PATH.parts[:2] == ("changes", "st-1606")
    assert builder.REFERENCE_PLAN_PATH.parts[:3] == (
        "changes",
        "st-1606",
        "generated",
    )
    assert builder.MANIFEST_PATH.parts[:2] == ("changes", "st-1606")
    assert Path(builder.GENERATOR_URI.removeprefix("repo://")) == builder.GENERATOR_PATH

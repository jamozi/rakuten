from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import build_st1605_failure_injection_drill as builder


def test_contract_loads_as_closed_local_non_attesting_boundary() -> None:
    contract = builder.load_contract()
    assert tuple(contract) == builder.TOP_LEVEL_KEYS
    assert contract["document"] == builder.EXPECTED_DOCUMENT
    assert contract["execution_boundary"] == builder.EXPECTED_EXECUTION
    assert contract["deterministic_fixture"] == builder.EXPECTED_FIXTURE
    assert contract["scenarios"] == builder.EXPECTED_SCENARIOS
    assert contract["evidence_boundary"] == builder.EXPECTED_EVIDENCE


def test_exact_six_scenarios_cover_selected_failure_surfaces() -> None:
    scenarios = builder.load_contract()["scenarios"]
    assert [row["id"] for row in scenarios] == [
        "FI-001",
        "FI-002",
        "FI-003",
        "FI-004",
        "FI-005",
        "FI-006",
    ]
    assert [row["target"] for row in scenarios] == [
        "RAKUTEN",
        "OPENAI",
        "DATABASE",
        "QUEUE",
        "PUBLICATION",
        "RELEASE",
    ]
    assert [row["runbook_id"] for row in scenarios] == [
        "RB-008",
        "RB-009",
        "RB-005",
        "RB-006",
        "RB-015",
        "RB-014",
    ]


@pytest.mark.parametrize("action", builder.ACTION_NAMES)
def test_every_external_action_count_is_exact_integer_zero(action: str) -> None:
    execution = builder.load_contract()["execution_boundary"]
    counts = execution["external_action_counts"]
    assert type(counts[action]) is int
    assert counts[action] == 0


def test_dependencies_preserve_non_attestation_and_local_only_runtime() -> None:
    dependencies = builder.load_contract()["dependency_bindings"]
    st1602 = dependencies["slo_alert_reference"]
    assert st1602["safe_default"] == "LOCAL_LOG_ONLY"
    assert st1602["notifications_enabled"] is False
    assert st1602["formal_tst_028"] == "NOT_EXECUTED"
    st1405 = dependencies["kill_switch_runtime"]
    assert st1405["target_adapter_environment"] == "ENV-CI"
    assert st1405["step_up_fixture_environment"] == "ENV-DEV"
    assert st1405["command_execution"] == "FORBIDDEN"
    assert st1405["state_mutation"] == "FORBIDDEN"
    assert st1405["event_delivery"] == "FORBIDDEN"
    evidence = builder.load_contract()["evidence_boundary"]
    assert evidence["behavioral_observation_scope"] == "FI-005_ONLY"
    assert evidence["behavioral_observation_scenarios"] == 1
    assert evidence["static_tabletop_reference_scenarios"] == 5
    assert evidence["recorded_safe_degradation_evaluation_scenarios"] == 6
    assert evidence["recorded_synthetic_response_scenarios"] == 6
    assert evidence["recorded_synthetic_responder_is_actual_owner"] is False
    assert evidence["local_acceptance_coverage"] == ("MAXIMUM_SAFE_RECORDED_SYNTHETIC")


def test_mixed_local_runtime_fixture_boundary_is_explicit() -> None:
    execution = builder.load_contract()["execution_boundary"]
    assert execution["cli_python_isolated_mode"] == "REQUIRED"
    assert execution["cli_python_no_bytecode_mode"] == "REQUIRED"
    assert (
        execution["runtime_module_loading"]
        == "DESCRIPTOR_CAPTURED_HASH_VERIFIED_IN_MEMORY"
    )
    assert (
        execution["runtime_module_inventory_scope"]
        == "FI_005_TRANSITIVE_IMPORT_CLOSURE"
    )
    assert execution["runtime_adapter_package_boundary"] == (
        "SOURCE_FREE_ADAPTER_AND_PORT_NAMESPACES"
    )
    assert execution["preloaded_raos_modules"] == "FORBIDDEN"
    assert execution["unlisted_raos_dependencies"] == "FORBIDDEN"
    assert execution["unrelated_provider_sdk_imports"] == "FORBIDDEN"
    assert execution["runtime_module_cleanup"] == "OWNED_IDENTITY_ONLY"
    assert execution["foreign_raos_modules_during_scope"] == "PRESERVE_AND_FAIL"
    assert execution["preloaded_helper_module"] == "FORBIDDEN"
    assert execution["process_context"] == "LOCAL_SYNTHETIC"
    assert execution["target_adapter_environment"] == "ENV-CI"
    assert execution["step_up_fixture_environment"] == "ENV-DEV"
    assert execution["credential_environment_reads"] == "FORBIDDEN"
    assert execution["live_fault_injection_enabled"] is False
    assert execution["kill_switch_mutation_enabled"] is False
    assert execution["rollback_execution_enabled"] is False
    assert execution["owner_notification_enabled"] is False


def test_installed_evidence_is_exact_owner_projection() -> None:
    evidence = json.loads((builder.REPO_ROOT / builder.EVIDENCE_PATH).read_text())
    assert evidence == builder.evidence_document(builder.load_contract())


def test_readme_denies_operational_and_formal_claims() -> None:
    text = (builder.REPO_ROOT / builder.README_PATH).read_text()
    for phrase in (
        "LOCAL_SYNTHETIC_NON_ATTESTING",
        "TST-028",
        "owner response",
        "runbook validation",
        "staging drill",
        "static tabletop references",
        "FI-005",
        "python -I -B",
        "Story acceptance remains false",
        "recorded synthetic response is not an actual owner response",
    ):
        assert phrase in text


def test_completion_record_is_local_only_and_preserves_external_gates() -> None:
    completion = builder.base._parse_yaml_bytes(  # noqa: SLF001
        builder.base._read_repository_file(  # noqa: SLF001
            builder.REPO_ROOT,
            builder.COMPLETION_PATH,
            "completion",
            max_bytes=builder.base.MAX_DOCUMENT_BYTES,
            size_error_code="COMPLETION_SIZE_LIMIT",
            path_error_code="COMPLETION_PATH_INVALID",
            missing_error_code="COMPLETION_UNAVAILABLE",
            ancestor_error_code="COMPLETION_ANCESTOR_INVALID",
            file_type_error_code="COMPLETION_FILE_INVALID",
        ),
        "completion",
    )
    assert completion["document"] == {
        "id": "RAOS-ST1605-LOCAL-IMPLEMENTATION-COMPLETION-20260824-V1",
        "schema_version": 1,
        "story_id": "ST-1605",
        "status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "recorded_at": "2026-08-24T00:00:00Z",
        "authority": "LOCAL_REVERSIBLE_DEVELOPMENT_ONLY",
        "generated": False,
    }
    authority = completion["authority_boundary"]
    assert all(value is False for value in authority.values())
    formal = completion["formal_and_external_boundaries"]
    assert formal["formal_tst_028"] == "NOT_EXECUTED"
    assert formal["owner_response"] == "NOT_EXECUTED"
    assert formal["staging"] == "NOT_EXECUTED"
    assert formal["production"] == "NOT_EXECUTED"
    assert formal["validated_claim"] == "FORBIDDEN"


def test_all_owned_paths_remain_inside_story_or_isolated_test_scope() -> None:
    assert builder.CONTRACT_PATH.parts[:2] == ("changes", "st-1605")
    assert builder.EVIDENCE_PATH.parts[:3] == ("changes", "st-1605", "generated")
    assert builder.MANIFEST_PATH.parts[:2] == ("changes", "st-1605")
    assert builder.COMPLETION_PATH.parts[:2] == ("changes", "st-1605")
    assert builder.GENERATOR_PATH == Path(
        "scripts/build_st1605_failure_injection_drill.py"
    )
    assert all(path.parts[0] == "tests" for path in builder.TEST_PATHS)

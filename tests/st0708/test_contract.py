"""Closed live-evaluation reference assertions for ST-0708."""

from __future__ import annotations

import json
from typing import Any

from scripts import (
    build_st0708_openai_live_bounded_evaluation_reference_plan as generator,
)


def _plan() -> dict[str, Any]:
    return generator.reference_plan(generator.load_contract())


def test_plan_has_exact_sections_and_non_executable_document() -> None:
    plan = _plan()
    assert tuple(plan) == generator.CONTRACT_KEYS
    document = plan["document"]
    assert document["story_id"] == "ST-0708"
    assert document["executable"] is False
    assert document["interface_only"] is True
    assert document["runtime_eligible"] is False
    assert document["decision"] == "NOT_READY"
    assert document["story_acceptance"] is False
    assert document["release_candidate"] is False
    assert document["release_eligible"] is False
    assert document["production_eligible"] is False
    assert document["approval"] is None


def test_dependencies_bind_current_recorded_only_artifacts() -> None:
    dependencies = _plan()["dependencies"]
    assert dependencies["st_0707"]["story_id"] == "ST-0707"
    assert dependencies["st_0707"]["source_commit"] == (
        "14f0813c443e22faab81dfce3507aff320831ac1"
    )
    assert dependencies["st_0707"]["artifacts"] == [
        {
            "uri": f"repo://{path.as_posix()}",
            "sha256": digest,
        }
        for path, digest in generator.ST0707_SHA256.items()
    ]
    assert dependencies["st_0703"]["artifacts"] == [
        {
            "uri": f"repo://{path.as_posix()}",
            "sha256": digest,
        }
        for path, digest in generator.ST0703_SHA256.items()
    ]
    st0707 = dependencies["st_0707"]["semantics"]
    assert st0707["mode"] == "BOOTSTRAP_SMOKE_ONLY"
    assert st0707["authority"] == "NONAUTHORITATIVE"
    assert st0707["runtime_actions"] == "FORBIDDEN"
    assert st0707["locked_holdout"] == "NOT_LOADED"
    assert st0707["formal_tst_018"] == "NOT_EXECUTED"
    assert st0707["external_actions"] == []
    st0703 = dependencies["st_0703"]["semantics"]
    assert st0703["mode"] == "RECORDED_ONLY"
    assert st0703["live_api"] == "NOT_USED"
    assert st0703["credential_or_secret_resolution"] == "NOT_USED"
    assert st0703["configured_sdk_retries"] == 0
    assert st0703["live_tst_018"] == "NOT_EXECUTED"
    assert st0703["external_actions"] == []


def test_od_015_stays_blocking_unresolved_and_recorded_fixture_only() -> None:
    decision = _plan()["open_decision"]
    assert decision["id"] == "OD-015"
    assert decision["status"] == "EXTERNAL_EVIDENCE_REQUIRED"
    assert decision["blocking"] is True
    assert decision["resolved"] is False
    assert decision["safe_default"] == "RECORDED_FIXTURE_ONLY"
    assert decision["canonical_safe_default"] == "Recorded fixtureのみ"
    for key in (
        "credentials_available",
        "account_available",
        "secret_available",
        "permissions_available",
        "external_evidence_available",
        "live_execution_authorized",
    ):
        assert decision[key] is False
    assert decision["authorization"] is None


def test_candidate_model_dataset_and_threshold_values_are_unselected() -> None:
    candidate = _plan()["candidate_selection"]
    assert candidate["status"] == "NOT_SELECTED"
    assert all(value is None for key, value in candidate.items() if key != "status")

    dataset = _plan()["dataset_boundary"]
    assert dataset["status"] == "NOT_CONFIGURED"
    assert dataset["approved"] is False
    assert dataset["locked"] is False
    assert dataset["adjudicated"] is False
    assert dataset["splits"] == []
    assert dataset["holdout"] == "NOT_LOADED"
    assert dataset["bootstrap_payload"] == "UNAVAILABLE"
    assert dataset["bootstrap_payload_bound"] is False
    assert dataset["observed_case_count"] is None
    for key in (
        "dataset_id",
        "dataset_version",
        "dataset_sha256",
        "approved_dataset_id",
        "approved_dataset_version",
        "approved_dataset_sha256",
        "locked_dataset_id",
        "locked_dataset_version",
        "locked_dataset_sha256",
        "adjudicated_dataset_id",
        "adjudicated_dataset_version",
        "adjudicated_dataset_sha256",
    ):
        assert dataset[key] is None

    thresholds = _plan()["thresholds"]
    assert thresholds["status"] == "NOT_SELECTED"
    assert thresholds["risk_specific_thresholds"] == []
    assert thresholds["zero_tolerance_classes"] == []
    for key in (
        "selected_threshold_set_id",
        "selected_threshold_set_version",
        "selected_threshold_set_sha256",
        "statistical_method",
        "confidence_method",
    ):
        assert thresholds[key] is None
    assert thresholds["evaluation"] == "NOT_EXECUTED"


def test_execution_observations_and_evidence_are_absent() -> None:
    execution = _plan()["execution_configuration"]
    assert execution["status"] == "NOT_CONFIGURED"
    assert execution["runnable"] is False
    assert execution["artifacts"] == []
    assert all(
        value is None
        for key, value in execution.items()
        if key not in {"status", "runnable", "artifacts"}
    )

    observations = _plan()["observations"]
    assert observations["status"] == "NOT_EXECUTED"
    assert observations["observations"] == []
    assert observations["findings"] == []
    assert observations["failures"] == []
    assert observations["evidence"] == []
    assert observations["empty_interpretation"] == (
        "NO_EXECUTION_EVIDENCE_NOT_SUCCESS_NOT_ZERO_FAILURES_NOT_THRESHOLD_SATISFACTION"
    )


def test_activation_is_disabled_with_exact_integer_zero_actions() -> None:
    activation = _plan()["activation_boundary"]
    assert activation["enabled"] is False
    assert activation["status"] == "DISABLED"
    assert activation["external_actions"] == []
    assert tuple(activation["action_counts"]) == generator.ACTION_COUNT_KEYS
    assert all(
        type(value) is int and value == 0
        for value in activation["action_counts"].values()
    )
    for key in (
        "provider",
        "network",
        "credential",
        "filesystem",
        "repository",
        "database",
        "job",
        "event",
        "release",
    ):
        assert activation[key] == "FORBIDDEN"
    assert activation["staging"] == "NOT_EXECUTED"
    assert activation["production"] == "NOT_EXECUTED"


def test_command_surface_and_verification_make_no_execution_claim() -> None:
    commands = _plan()["command_surface"]
    assert commands["commands"] == []
    assert all(value is None for key, value in commands.items() if key != "commands")
    verification = _plan()["verification_boundary"]
    for key in (
        "formal_tst_018",
        "live_evaluation",
        "staging",
        "security_review",
        "data_review",
        "policy_review",
        "canary",
        "rollback",
        "monitoring",
    ):
        assert verification[key] == "NOT_EXECUTED"
    assert verification["human_labels"] == "NOT_OBTAINED"
    assert verification["judge_calibration"] == "NOT_OBTAINED"
    assert verification["decision"] == "NOT_READY"
    assert verification["story_acceptance"] is False
    assert verification["release_candidate"] is False
    assert verification["release_eligible"] is False
    assert verification["production_eligible"] is False
    assert verification["approval"] is None


def test_installed_plan_contains_no_false_completion_claim_values() -> None:
    plan = json.loads(
        (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    )

    def strings(value: object) -> list[str]:
        if type(value) is str:
            return [value]
        if type(value) is list:
            return [item for child in value for item in strings(child)]
        if type(value) is dict:
            return [item for child in value.values() for item in strings(child)]
        return []

    assert {
        "PASS",
        "READY",
        "VALIDATED",
        "IMPLEMENTED",
        "LIVE_SUCCESS",
        "AUTHENTICATED",
        "PRODUCTION_READY",
    }.isdisjoint(strings(plan))

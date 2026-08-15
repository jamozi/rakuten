from __future__ import annotations

from typing import Any, cast

from scripts import build_st1605_failure_injection_drill as builder


def test_one_behavior_observation_is_separated_from_five_tabletop_references() -> None:
    evidence = builder.evidence_document(builder.load_contract())
    results = cast(list[dict[str, Any]], evidence["scenario_results"])
    assert len(results) == 6
    assert [row["status"] for row in results] == [
        "STATIC_TABLETOP_REFERENCE",
        "STATIC_TABLETOP_REFERENCE",
        "STATIC_TABLETOP_REFERENCE",
        "STATIC_TABLETOP_REFERENCE",
        "LOCAL_SYNTHETIC_BEHAVIOR_OBSERVED",
        "STATIC_TABLETOP_REFERENCE",
    ]
    assert [row["behavior_observed"] for row in results] == [
        False,
        False,
        False,
        False,
        True,
        False,
    ]
    assert all(
        all(
            type(value) is int and value == 0
            for value in row["external_action_counts"].values()
        )
        for row in results
    )
    assert evidence["classification"] == "LOCAL_SYNTHETIC_NON_ATTESTING"
    assert evidence["summary"] == {
        "scenario_count": 6,
        "behavioral_observation_count": 1,
        "static_tabletop_reference_count": 5,
        "behavioral_observation_scenario_ids": ["FI-005"],
        "external_action_counts": builder.ZERO_ACTIONS,
    }


def test_provider_failures_remain_static_tabletop_references() -> None:
    results = builder.execute_scenarios(builder.load_contract())
    rakuten, openai = results[:2]
    assert rakuten["observation"] == builder.STATIC_OBSERVATIONS["FI-001"]
    assert openai["observation"] == builder.STATIC_OBSERVATIONS["FI-002"]
    assert rakuten["observation"]["operation_executed"] is False
    assert openai["observation"]["operation_executed"] is False
    assert rakuten["status"] == "STATIC_TABLETOP_REFERENCE"
    assert openai["status"] == "STATIC_TABLETOP_REFERENCE"
    assert rakuten["behavior_observed"] is False
    assert openai["behavior_observed"] is False


def test_database_and_queue_failures_never_execute_an_integration_action() -> None:
    results = builder.execute_scenarios(builder.load_contract())
    database, queue = results[2:4]
    database_observation = cast(dict[str, object], database["observation"])
    queue_observation = cast(dict[str, object], queue["observation"])
    assert database_observation["required_response"] == (
        "FREEZE_WRITES_AND_SERVE_LAST_SAFE_SNAPSHOT"
    )
    assert queue_observation["required_response"] == (
        "PAUSE_PRODUCER_AND_REQUIRE_IDEMPOTENT_REPLAY"
    )
    assert database_observation["external_effect"] == "NONE"
    assert queue_observation["external_effect"] == "NONE"
    assert database["status"] == "STATIC_TABLETOP_REFERENCE"
    assert queue["status"] == "STATIC_TABLETOP_REFERENCE"
    assert database["behavior_observed"] is False
    assert queue["behavior_observed"] is False


def test_real_st1405_in_process_seam_denies_without_mutation_or_event() -> None:
    result = builder.execute_scenarios(builder.load_contract())[4]
    observation = cast(dict[str, object], result["observation"])
    assert observation["outcome_code"] == "PUBLICATION_COMMANDS_DENIED"
    assert observation["eligibility_code"] == "ENGAGED"
    assert observation["allowed"] is False
    assert observation["observed_generation"] == 7
    assert observation["event_intent_count"] == 0
    assert observation["target_adapter_environment"] == "ENV-CI"
    assert observation["step_up_fixture_environment"] == "ENV-DEV"
    assert observation["operation_executed"] is False
    assert result["status"] == "LOCAL_SYNTHETIC_BEHAVIOR_OBSERVED"
    assert result["behavior_observed"] is True


def test_rollback_is_tabletop_only_and_has_no_authority() -> None:
    result = builder.execute_scenarios(builder.load_contract())[5]
    assert result["observation"] == builder.STATIC_OBSERVATIONS["FI-006"]
    assert result["status"] == "STATIC_TABLETOP_REFERENCE"
    assert result["behavior_observed"] is False
    evidence = builder.load_contract()["evidence_boundary"]
    assert evidence["rollback_behavior_claim"] is False
    assert evidence["owner_response"] == "NOT_EXECUTED"
    assert evidence["runbook_validation"] == "NOT_EXECUTED"
    assert evidence["staging_drill"] == "NOT_EXECUTED"
    assert evidence["story_acceptance"] is False


def test_scenario_fingerprints_are_stable_and_distinct() -> None:
    first = builder.execute_scenarios(builder.load_contract())
    second = builder.execute_scenarios(builder.load_contract())
    first_fingerprints = [row["input_fingerprint"] for row in first]
    second_fingerprints = [row["input_fingerprint"] for row in second]
    assert first_fingerprints == second_fingerprints
    assert len(set(first_fingerprints)) == 6

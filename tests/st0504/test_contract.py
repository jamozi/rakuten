"""Closed source and reference-plan assertions for ST-0504."""

from __future__ import annotations

import json
from typing import Any

from scripts import (
    build_st0504_product_identity_human_review_reference_plan as generator,
)


def _plan() -> dict[str, Any]:
    return generator.reference_plan(generator.load_contract())


def test_plan_has_exact_sections_and_non_executable_document() -> None:
    plan = _plan()
    assert tuple(plan) == generator.PLAN_KEYS
    assert plan["document"] == generator.EXPECTED_DOCUMENT
    assert plan["document"]["executable"] is False
    assert plan["document"]["interface_only"] is True
    assert plan["document"]["decision"] == "NOT_READY"
    assert plan["document"]["story_acceptance"] is False
    assert plan["document"]["production_eligible"] is False
    assert plan["document"]["approval"] is None


def test_predecessor_binds_exact_commit_artifacts_and_safe_semantics() -> None:
    predecessor = _plan()["predecessor_binding"]
    assert predecessor["story_id"] == "ST-0503"
    assert predecessor["commit"] == generator.PREDECESSOR_COMMIT
    assert predecessor["artifacts"] == generator._expected_predecessor_artifacts()
    assert predecessor["semantics"] == generator.EXPECTED_PREDECESSOR_SEMANTICS
    assert predecessor["semantics"]["identity_status"] == "REVIEW_REQUIRED"
    assert predecessor["semantics"]["confidence_status"] == "SOURCE_ABSENT"
    assert predecessor["semantics"]["canonical_products"] == []
    assert predecessor["semantics"]["grouping_decisions"] == []
    assert predecessor["semantics"]["identity_decisions"] == []
    assert predecessor["semantics"]["approval"] is None


def test_od_006_stays_blocking_unresolved_and_human_review_safe() -> None:
    decision = _plan()["open_decision"]
    assert decision == generator.EXPECTED_OPEN_DECISION
    assert decision["status"] == "EXTERNAL_EVIDENCE_REQUIRED"
    assert decision["blocking"] is True
    assert decision["resolved"] is False
    assert decision["safe_default"] == ("NO_AUTOMATIC_MERGE_HUMAN_REVIEW_REQUIRED")
    assert decision["category_rules"] == []
    assert decision["thresholds"] == []
    assert decision["scores"] == []


def test_canonical_test_suites_are_exact_but_have_no_execution_evidence() -> None:
    suites = _plan()["test_suites"]
    assert [suite["id"] for suite in suites] == ["TST-007", "TST-020"]
    for suite, expected in zip(suites, generator.EXPECTED_TEST_SUITES, strict=True):
        for key, value in expected.items():
            assert suite[key] == value
        assert suite["formal_execution"] == "NOT_EXECUTED"
        assert suite["evidence"] is None


def test_candidate_projection_is_an_empty_interface_not_zero_candidates() -> None:
    projection = _plan()["candidate_projection"]
    assert projection == generator.EXPECTED_CANDIDATE_PROJECTION
    assert projection["provenance_required"] is True
    assert projection["candidate_records"] == []
    assert projection["candidate_count"] is None
    assert projection["source_snapshots"] == []
    assert projection["input_evidence"] == []
    assert projection["empty_interpretation"] == (
        "NO_RUNTIME_INPUT_OR_EVIDENCE_NOT_ZERO_CANDIDATES"
    )


def test_human_review_is_required_but_not_configured_or_executed() -> None:
    review = _plan()["human_review"]
    assert review == generator.EXPECTED_HUMAN_REVIEW
    assert review["required"] is True
    assert review["status"] == "REQUIRED_NOT_EXECUTED"
    assert review["routing_status"] == "NOT_CONFIGURED"
    for key in (
        "queue",
        "route",
        "reviewer",
        "actor",
        "role",
        "assignment",
        "sla",
        "approval",
    ):
        assert review[key] is None
    assert review["review_records"] == []
    assert review["delivery_records"] == []


def test_identity_boundary_has_no_merge_split_rule_score_or_history() -> None:
    identity = _plan()["identity_boundary"]
    assert identity["automatic_merge_enabled"] is False
    assert identity["automatic_split_enabled"] is False
    for key in (
        "category_rule",
        "threshold",
        "score",
        "confidence",
        "canonical_product_id",
    ):
        assert identity[key] is None
    for key in (
        "identity_decisions",
        "membership_records",
        "merge_records",
        "split_records",
        "supersession_records",
        "decision_history",
        "external_actions",
    ):
        assert identity[key] == []
    assert identity["safe_default"] == ("NO_AUTOMATIC_MERGE_HUMAN_REVIEW_REQUIRED")
    assert identity["empty_interpretation"] == (
        "NO_IDENTITY_CONFIGURATION_DECISION_OR_HISTORY_NOT_ZERO_PRODUCTS"
    )


def test_execution_is_disabled_with_exact_integer_zero_actions() -> None:
    execution = _plan()["execution_boundary"]
    assert execution["enabled"] is False
    assert execution["status"] == "DISABLED"
    assert tuple(execution["action_counts"]) == generator.ACTION_COUNT_KEYS
    assert all(
        type(value) is int and value == 0
        for value in execution["action_counts"].values()
    )
    for key in (
        "rule_engine",
        "human_review",
        "queue",
        "event",
        "database",
        "persistence",
        "provider",
        "live",
        "staging",
        "release",
        "production",
    ):
        assert execution[key] == "NOT_EXECUTED"
    assert execution["repository"] == "ABSENT"


def test_verification_boundary_does_not_claim_story_or_runtime_completion() -> None:
    verification = _plan()["verification_boundary"]
    assert verification["projection_only"] is True
    assert verification["predecessor_connection"] == "NOT_EXECUTED"
    assert verification["formal_tst_007"] == "NOT_EXECUTED"
    assert verification["formal_tst_020"] == "NOT_EXECUTED"
    assert verification["story_acceptance"] is False
    assert verification["production_eligible"] is False
    assert verification["approval"] is None
    assert verification["effective_canonical_status"] == "UNCHANGED"


def test_installed_plan_contains_no_false_completion_claim_values() -> None:
    plan = json.loads(
        (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    )
    assert tuple(plan) == generator.PLAN_KEYS

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
        "APPROVED",
        "PRODUCTION_READY",
    }.isdisjoint(strings(plan))

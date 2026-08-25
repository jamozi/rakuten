"""Closed source and generated-plan assertions for ST-1702."""

from __future__ import annotations

import json
from typing import Any

from scripts import (
    build_st1702_category_fixtures_rules_reference_plan as generator,
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
    assert plan["document"]["st1702_ready"] is False
    assert plan["document"]["canonical_mutation_authority"] == "NONE"
    assert plan["document"]["approval"] is None


def test_authority_and_dependencies_bind_exact_base_and_artifacts() -> None:
    plan = _plan()
    authority = plan["authority"]
    assert authority == generator.EXPECTED_AUTHORITY
    assert authority["integration_base_commit"] == generator.INTEGRATION_BASE_COMMIT
    assert authority["sources"] == generator._source_rows()

    dependencies = plan["dependency_bindings"]
    assert dependencies == list(generator.EXPECTED_DEPENDENCIES)
    assert [row["story_id"] for row in dependencies] == [
        "ST-1701",
        "ST-0504",
        "ST-1401",
    ]
    for row in dependencies:
        assert row["canonical_story_status"] == "NOT_STARTED"
        assert row["canonical_verification_status"] == "NOT_EXECUTED"
        assert row["canonical_acceptance"] == "NOT_ACHIEVED"
        assert row["st1702_ready"] is False
        assert row["connection_status"] in {
            "SOURCE_BOUND_NOT_ACTIVATED",
            "SOURCE_BOUND_NOT_CONNECTED",
        }


def test_runtime_blockers_are_complete_ordered_and_keep_st1702_false() -> None:
    blockers = _plan()["runtime_blockers"]
    assert blockers == generator.EXPECTED_RUNTIME_BLOCKERS
    assert blockers["status"] == "BLOCKED"
    assert blockers["canonical_global_unresolved_blocker_count"] == 14
    assert blockers["canonical_scoped_unresolved_count"] == 7
    assert blockers["gate_state"] == "BLOCKED"
    assert blockers["st1701_acceptance"] == "NOT_ACHIEVED"
    assert blockers["st1702_ready"] is False
    assert (
        tuple((row["id"], row["status"]) for row in blockers["required_conditions"])
        == generator.EXPECTED_BLOCKER_CONDITIONS
    )


def test_od_001_006_007_remain_blocking_unresolved_and_disabled() -> None:
    decisions = _plan()["open_decisions"]
    assert decisions == list(generator.EXPECTED_OPEN_DECISIONS)
    assert [row["id"] for row in decisions] == ["OD-001", "OD-006", "OD-007"]
    assert [row["canonical_status"] for row in decisions] == [
        "HUMAN_DECISION_REQUIRED",
        "EXTERNAL_EVIDENCE_REQUIRED",
        "HUMAN_DECISION_REQUIRED",
    ]
    for row in decisions:
        assert row["blocking"] is True
        assert row["resolved"] is False
        assert row["candidate_authority"] == (
            "NON_AUTHORITATIVE_OWNER_DECISION_CANDIDATE"
        )
        assert row["runtime_activation"] == "DISABLED"


def test_suitcase_is_only_a_non_authoritative_disabled_candidate() -> None:
    category = _plan()["category_candidate"]
    assert category == generator.EXPECTED_CATEGORY_CANDIDATE
    assert category["category_id"] == "suitcase_and_carry_bags"
    assert category["display_name_ja"] == "スーツケース・キャリーバッグ"
    assert category["classification"] == ("NON_AUTHORITATIVE_OWNER_DECISION_CANDIDATE")
    assert category["canonical_resolution"] == "UNCHANGED_UNRESOLVED"
    assert category["runtime_activation"] == "DISABLED"
    assert category["category_specific_implementation"] == "STOPPED"
    assert category["runtime_category_config"] == "NOT_CREATED"
    assert category["golden_products"] == "NOT_CREATED"
    assert category["attribute_schema"] == "NOT_CREATED"
    assert category["production_data"] == "FORBIDDEN"


def test_fixture_and_golden_product_artifacts_are_not_created() -> None:
    boundary = _plan()["fixture_boundary"]
    assert boundary == generator.EXPECTED_FIXTURE_BOUNDARY
    assert boundary["reference_only"] is True
    assert boundary["runtime_category_config"] == "NOT_CREATED"
    assert boundary["fixture_schema"] == "NOT_CREATED"
    assert boundary["golden_products"] == "NOT_CREATED"
    assert boundary["runtime_loader"] == "NOT_CREATED"
    for key in (
        "fixture_records",
        "golden_product_records",
        "source_snapshots",
        "provider_observations",
        "evidence_records",
    ):
        assert boundary[key] == []
    assert boundary["creation_authority"] == "NONE"


def test_identity_remains_human_review_only_with_merge_and_split_disabled() -> None:
    identity = _plan()["identity_boundary"]
    assert identity == generator.EXPECTED_IDENTITY_BOUNDARY
    assert identity["open_decision_id"] == "OD-006"
    assert identity["gold_evidence_status"] == "EVIDENCE_INSUFFICIENT"
    assert identity["gold_evidence_stop_code"] == "STOP_EVIDENCE_INSUFFICIENT"
    assert identity["domain_editor_approval"] == "NOT_OBTAINED"
    assert identity["human_review_required"] is True
    assert identity["automatic_merge_enabled"] is False
    assert identity["automatic_split_enabled"] is False
    assert identity["candidate_rule_source_bound_not_applied"] is True
    assert identity["rule_config"] == "NOT_CREATED"
    for key in (
        "rules",
        "thresholds",
        "scores",
        "identity_decisions",
        "membership_records",
        "merge_records",
        "split_records",
    ):
        assert identity[key] == []


def test_freshness_stays_provisional_disabled_and_override_free() -> None:
    freshness = _plan()["freshness_boundary"]
    assert freshness == generator.EXPECTED_FRESHNESS_BOUNDARY
    assert freshness["open_decision_id"] == "OD-007"
    assert freshness["policy_authority"] == "PROVISIONAL_CANONICAL_SAFE_DEFAULT"
    assert freshness["policy_activation"] == "DISABLED_UNRESOLVED_OD_007"
    assert freshness["policy_active"] is False
    assert freshness["st1701_candidate_sla_bound_not_applied"] is True
    assert freshness["runtime_freshness_config"] == "NOT_CREATED"
    assert freshness["category_overrides"] == []
    assert freshness["provider_overrides"] == []
    assert freshness["category_override_applied"] is False
    assert freshness["provider_override_applied"] is False
    assert freshness["stale_never_treated_as_fresh"] is True
    assert freshness["recommendation_auto_reorder"] == "FORBIDDEN"


def test_human_review_is_required_but_not_configured_or_executed() -> None:
    review = _plan()["human_review"]
    assert review == generator.EXPECTED_HUMAN_REVIEW
    assert review["required"] is True
    assert review["status"] == "REQUIRED_NOT_EXECUTED"
    assert review["domain_reviewer_approval"] == "NOT_OBTAINED"
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


def test_execution_is_disabled_with_exact_zero_actions_and_no_runtime_surface() -> None:
    execution = _plan()["execution_boundary"]
    assert execution == generator.EXPECTED_EXECUTION_BOUNDARY
    assert execution["enabled"] is False
    assert execution["status"] == "DISABLED"
    assert execution["runtime_category_config"] == "NOT_CREATED"
    assert execution["golden_products"] == "NOT_CREATED"
    assert tuple(execution["action_counts"]) == generator.ACTION_COUNT_KEYS
    assert all(
        type(value) is int and value == 0
        for value in execution["action_counts"].values()
    )
    for key in (
        "category_rule_engine",
        "freshness_scheduler",
        "human_review",
        "database",
        "persistence",
        "job",
        "event",
        "provider",
        "live",
        "publication",
        "staging",
        "release",
        "production",
    ):
        assert execution[key] == "NOT_EXECUTED"
    assert execution["repository"] == "ABSENT"
    assert execution["external_authority"] == "NONE"


def test_security_and_test_rows_have_no_formal_evidence() -> None:
    plan = _plan()
    controls = plan["security_controls"]
    assert controls["formal_verification"] == "NOT_EXECUTED"
    assert controls["evidence"] is None
    assert [row["id"] for row in controls["controls"]] == list(
        generator.SECURITY_CONTROL_IDS
    )
    for row in controls["controls"]:
        assert row["formal_verification"] == "NOT_EXECUTED"
        assert row["evidence"] is None

    suites = plan["test_suites"]
    assert [row["id"] for row in suites] == [
        "TST-020",
        "TST-032",
        "TST-007",
        "TST-005",
        "TST-028",
    ]
    for row in suites:
        assert row["formal_execution"] == "NOT_EXECUTED"
        assert row["evidence"] is None


def test_verification_does_not_claim_story_runtime_or_release_completion() -> None:
    verification = _plan()["verification_boundary"]
    assert verification["projection_only"] is True
    assert verification["dependency_connections"] == "NOT_EXECUTED"
    assert verification["formal_tst_020"] == "NOT_EXECUTED"
    assert verification["domain_reviewer_approval"] == "NOT_EXECUTED"
    assert verification["runtime"] == "NOT_EXECUTED"
    assert verification["provider"] == "NOT_EXECUTED"
    assert verification["live"] == "NOT_EXECUTED"
    assert verification["publication"] == "NOT_EXECUTED"
    assert verification["staging"] == "NOT_EXECUTED"
    assert verification["release"] == "NOT_EXECUTED"
    assert verification["production"] == "NOT_EXECUTED"
    assert verification["story_acceptance"] is False
    assert verification["st1702_ready"] is False
    assert verification["approval"] is None


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
        "RESOLVED",
        "VALIDATED",
        "IMPLEMENTED",
        "PRODUCTION_READY",
    }.isdisjoint(strings(plan))

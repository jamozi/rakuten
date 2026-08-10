"""Closed contract and projection assertions for ST-0603."""

from __future__ import annotations

import ast
import json

import yaml

from scripts import (
    build_st0603_fact_conflict_review_reference_plan as generator,
)


def _plan() -> dict[str, object]:
    return generator.reference_plan(generator.load_contract())


def test_contract_and_plan_have_exact_closed_top_level_shapes() -> None:
    assert tuple(generator.load_contract()) == generator.CONTRACT_KEYS
    assert tuple(_plan()) == generator.PLAN_KEYS


def test_document_is_non_executable_not_ready_and_not_accepted() -> None:
    document = _plan()["document"]
    assert document == {
        "schema_version": 1,
        "story_id": "ST-0603",
        "classification": (
            "SOURCE_DERIVED_NONEXECUTABLE_FACT_CONFLICT_REVIEW_REFERENCE_PLAN"
        ),
        "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
        "executable": False,
        "interface_only": True,
        "decision": "NOT_READY",
        "production_eligible": False,
        "approval": None,
        "story_acceptance": False,
        "canonical_story_status": {
            "implementation": "NOT_STARTED",
            "verification": "NOT_EXECUTED",
        },
    }


def test_authority_is_exact_but_does_not_claim_canonical_completion() -> None:
    assert _plan()["authority"] == generator.EXPECTED_AUTHORITY
    assert generator.EXPECTED_STORY["depends_on"] == ["ST-0602"]
    assert generator.EXPECTED_STORY["implementation_status"] == "NOT_STARTED"
    assert generator.EXPECTED_STORY["verification_status"] == "NOT_EXECUTED"


def test_predecessor_binds_exact_commit_nine_files_and_empty_fact_semantics() -> None:
    predecessor = _plan()["predecessor_binding"]
    assert predecessor == generator.EXPECTED_PREDECESSOR
    assert predecessor["commit"] == generator.PREDECESSOR_COMMIT
    assert len(predecessor["files"]) == 9
    semantics = predecessor["required_semantics"]
    assert semantics == generator.EXPECTED_PREDECESSOR_SEMANTICS
    assert semantics["facts"] == []
    assert semantics["fact_ids"] == []
    assert semantics["derivations"] == []


def test_conflict_evidence_and_security_context_is_descriptive_only() -> None:
    context = _plan()["canonical_context"]
    assert context == generator.EXPECTED_CANONICAL_CONTEXT
    assert context["authority"] == "DESCRIPTIVE_ONLY"
    assert context["creates_runtime_contract"] is False
    assert context["conflict_policy"] == "DESCRIPTIVE_ONLY_NOT_BOUND"
    assert context["evidence_requirement"] == ("EVD-004_DESCRIPTIVE_ONLY_NOT_BOUND")
    assert context["security_controls"] == "DESCRIPTIVE_ONLY_NOT_BOUND"


def test_fact_inputs_are_empty_with_unknown_not_zero_count() -> None:
    inputs = _plan()["input_boundary"]
    assert inputs == generator.EXPECTED_INPUT_DEFAULTS
    assert inputs["facts"] == []
    assert inputs["fact_ids"] == []
    assert inputs["fact_count"] is None


def test_every_conflict_rule_and_review_selection_is_null() -> None:
    selections = _plan()["selection_boundary"]
    assert selections == generator.EXPECTED_SELECTION_DEFAULTS
    assert all(value is None for value in selections.values())


def test_comparisons_conflicts_findings_queue_and_resolutions_are_empty() -> None:
    projection = _plan()["conflict_projection"]
    assert projection == generator.EXPECTED_PROJECTION_DEFAULTS
    for key in ("comparisons", "conflicts", "findings", "queue", "resolutions"):
        assert projection[key] == []
    for key in (
        "comparison_count",
        "conflict_count",
        "finding_count",
        "queue_count",
        "resolution_count",
    ):
        assert projection[key] is None


def test_review_resolution_preserves_exact_blockers_and_safety_defaults() -> None:
    boundary = _plan()["review_and_resolution"]
    assert boundary == generator.EXPECTED_REVIEW_AND_RESOLUTION
    assert boundary["comparison_status"] == "NOT_EXECUTED"
    assert boundary["queue_status"] == "NOT_EXECUTED"
    assert boundary["resolution_status"] == "NOT_EXECUTED"
    assert boundary["automatic_resolution_enabled"] is False
    assert boundary["silent_resolution_allowed"] is False
    assert boundary["blockers"] == generator.EXPECTED_BLOCKERS


def test_all_runtime_boundaries_are_not_executed_with_zero_actions() -> None:
    execution = _plan()["execution_boundary"]
    assert execution == generator.EXPECTED_EXECUTION
    for key in (
        "detector",
        "comparison",
        "review_queue",
        "resolution",
        "repository",
        "database",
        "event",
        "api",
        "ui",
        "external",
    ):
        assert execution[key] == "NOT_EXECUTED"
    assert tuple(execution["action_counts"]) == generator.ACTION_COUNT_KEYS
    assert all(
        type(value) is int and value == 0
        for value in execution["action_counts"].values()
    )


def test_formal_live_release_and_production_evidence_remain_unexecuted() -> None:
    assert _plan()["verification_boundary"] == generator.EXPECTED_VERIFICATION


def test_installed_outputs_contain_no_false_positive_status_values() -> None:
    plan = json.loads(
        (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    )
    manifest = yaml.safe_load(
        (generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes()
    )

    def strings(value: object) -> list[str]:
        if type(value) is str:
            return [value]
        if type(value) is list:
            return [item for child in value for item in strings(child)]
        if type(value) is dict:
            return [item for child in value.values() for item in strings(child)]
        return []

    forbidden = {"PASS", "READY", "VALIDATED", "IMPLEMENTED", "APPROVED"}
    assert forbidden.isdisjoint(strings(plan))
    assert forbidden.isdisjoint(strings(manifest))


def test_builder_has_no_process_network_database_or_provider_imports() -> None:
    tree = ast.parse((generator.REPO_ROOT / generator.GENERATOR_PATH).read_bytes())
    imported = {
        alias.name.split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imported.isdisjoint(
        {
            "asyncio",
            "boto3",
            "httpx",
            "requests",
            "socket",
            "sqlalchemy",
            "subprocess",
            "urllib",
        }
    )

"""Closed contract and projection assertions for ST-0602."""

from __future__ import annotations

import ast
import json

import yaml

from scripts import (
    build_st0602_fact_extraction_validation_reference_plan as generator,
)


def _plan() -> dict[str, object]:
    return generator.reference_plan(generator.load_contract())


def test_contract_and_plan_have_exact_closed_top_level_shapes() -> None:
    assert tuple(generator.load_contract()) == generator.CONTRACT_KEYS
    assert tuple(_plan()) == generator.PLAN_KEYS


def test_document_is_non_executable_not_ready_and_not_accepted() -> None:
    document = _plan()["document"]
    assert isinstance(document, dict)
    assert document == {
        "schema_version": 1,
        "story_id": "ST-0602",
        "classification": (
            "SOURCE_DERIVED_NON_EXECUTABLE_FACT_EXTRACTION_VALIDATION_REFERENCE_PLAN"
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


def test_authority_matches_exact_canonical_story_without_completion_claim() -> None:
    plan = _plan()
    assert plan["authority"] == generator.EXPECTED_AUTHORITY
    assert generator.EXPECTED_STORY["depends_on"] == ["ST-0601", "ST-0503"]
    assert generator.EXPECTED_STORY["implementation_status"] == "NOT_STARTED"
    assert generator.EXPECTED_STORY["verification_status"] == "NOT_EXECUTED"


def test_predecessors_bind_exact_commits_bytes_and_safe_semantics() -> None:
    predecessors = _plan()["predecessor_bindings"]
    assert predecessors == generator._expected_predecessors()
    assert isinstance(predecessors, list)
    assert [row["commit"] for row in predecessors] == [
        generator.ST0601_COMMIT,
        generator.ST0503_COMMIT,
    ]
    assert predecessors[0]["required_semantics"] == (
        generator.EXPECTED_ST0601_SEMANTICS
    )
    assert predecessors[1]["required_semantics"] == (
        generator.EXPECTED_ST0503_SEMANTICS
    )


def test_canonical_fact_job_event_and_security_context_is_descriptive_only() -> None:
    context = _plan()["canonical_context"]
    assert context == generator.EXPECTED_CANONICAL_CONTEXT
    assert context["authority"] == "DESCRIPTIVE_ONLY"
    assert context["creates_runtime_contract"] is False
    for key in ("fact_model", "extraction_job", "fact_event", "security_controls"):
        assert context[key] == "DESCRIPTIVE_ONLY_NOT_BOUND"


def test_all_unavailable_fact_inputs_remain_exactly_null() -> None:
    inputs = _plan()["input_boundary"]
    assert inputs == generator.EXPECTED_INPUT_DEFAULTS
    assert tuple(inputs) == tuple(generator.EXPECTED_INPUT_DEFAULTS)
    assert all(value is None for value in inputs.values())


def test_fact_ids_derivations_and_review_material_remain_empty() -> None:
    projection = _plan()["fact_projection"]
    assert projection == generator.EXPECTED_FACT_PROJECTION
    assert all(value == [] for value in projection.values())


def test_validation_is_not_executed_with_exact_ordered_blockers() -> None:
    validation = _plan()["validation"]
    assert validation == generator.EXPECTED_VALIDATION
    assert validation["passed"] is False
    assert validation["blockers"] == generator.EXPECTED_BLOCKERS


def test_repository_database_job_event_and_every_action_are_not_executed() -> None:
    execution = _plan()["execution_boundary"]
    assert execution == generator.EXPECTED_EXECUTION
    for key in (
        "extraction",
        "validation",
        "manual_review",
        "repository",
        "database",
        "job",
        "event",
        "provider",
        "live",
        "external",
    ):
        assert execution[key] == "NOT_EXECUTED"
    assert tuple(execution["action_counts"]) == generator.ACTION_COUNT_KEYS
    assert all(
        type(value) is int and value == 0
        for value in execution["action_counts"].values()
    )


def test_formal_live_release_and_production_verification_remain_unexecuted() -> None:
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

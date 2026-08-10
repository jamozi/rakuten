"""Closed contract and projection assertions for ST-0604."""

from __future__ import annotations

import ast
import json
from typing import Any, cast

import yaml

from scripts import (
    build_st0604_source_packet_lifecycle_reference_plan as generator,
)


def _plan() -> dict[str, object]:
    return generator.reference_plan(generator.load_contract())


def test_contract_and_plan_have_exact_closed_top_level_shapes() -> None:
    assert tuple(generator.load_contract()) == generator.CONTRACT_KEYS
    assert tuple(_plan()) == generator.PLAN_KEYS


def test_document_is_non_executable_unapproved_and_generation_forbidden() -> None:
    assert _plan()["document"] == {
        "schema_version": 1,
        "story_id": "ST-0604",
        "classification": (
            "SOURCE_DERIVED_NON_EXECUTABLE_SOURCE_PACKET_LIFECYCLE_REFERENCE_PLAN"
        ),
        "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
        "executable": False,
        "interface_only": True,
        "decision": "NOT_READY",
        "production_eligible": False,
        "approval": False,
        "story_acceptance": False,
        "generation_permitted": False,
        "canonical_story_status": {
            "implementation": "NOT_STARTED",
            "verification": "NOT_EXECUTED",
        },
    }


def test_authority_is_exact_but_canonical_story_remains_unexecuted() -> None:
    assert _plan()["authority"] == generator.EXPECTED_AUTHORITY
    assert generator.EXPECTED_STORY["depends_on"] == [
        "ST-0602",
        "ST-0603",
        "ST-0403",
    ]
    assert generator.EXPECTED_STORY["implementation_status"] == "NOT_STARTED"
    assert generator.EXPECTED_STORY["verification_status"] == "NOT_EXECUTED"


def test_predecessors_bind_commit_derived_nine_nine_eight_inventories() -> None:
    predecessors = _plan()["predecessor_bindings"]
    assert predecessors == generator._expected_predecessors()
    assert [row["commit"] for row in predecessors] == [
        generator.ST0602_COMMIT,
        generator.ST0603_COMMIT,
        generator.ST0403_COMMIT,
    ]
    assert [len(row["files"]) for row in predecessors] == [9, 9, 8]
    assert [row["files"][0]["path"] for row in predecessors] == [
        "changes/st-0602/README.md",
        "changes/st-0603/README.md",
        "changes/st-0403/README.md",
    ]


def test_predecessor_semantics_preserve_empty_inputs_and_deny_default() -> None:
    predecessors = cast(
        list[dict[str, Any]],
        _plan()["predecessor_bindings"],
    )
    assert predecessors[0]["required_semantics"] == (
        generator.EXPECTED_ST0602_SEMANTICS
    )
    assert predecessors[1]["required_semantics"] == (
        generator.EXPECTED_ST0603_SEMANTICS
    )
    assert predecessors[2]["required_semantics"] == (
        generator.EXPECTED_ST0403_SEMANTICS
    )
    assert predecessors[0]["required_semantics"]["decision"] == "NOT_READY"
    assert predecessors[1]["required_semantics"]["conflicts"] == []
    assert predecessors[2]["required_semantics"]["deny_by_default"] is True


def test_packet_version_and_job_vocabularies_are_separate_descriptive_namespaces() -> (
    None
):
    context = _plan()["vocabulary_context"]
    assert context == generator.EXPECTED_VOCABULARY_CONTEXT
    assert context["authority"] == "DESCRIPTIVE_ONLY"
    assert context["creates_runtime_contract"] is False
    namespaces = [
        context["packet_namespace"]["name"],
        context["version_namespace"]["name"],
        context["job_namespace"]["name"],
    ]
    assert len(set(namespaces)) == 3
    assert context["packet_namespace"]["values"] == [
        "DRAFT",
        "APPROVE",
        "VERSION",
        "LOCK",
    ]
    assert context["version_namespace"]["values"] == [
        "BUILDING",
        "READY",
        "IN_REVIEW",
        "APPROVED",
        "REJECTED",
        "SUPERSEDED",
        "INVALID",
    ]
    assert context["job_namespace"]["values"] == [
        "REQUESTED",
        "QUEUED",
        "RUNNING",
        "SUCCEEDED",
        "FAILED_RETRYABLE",
        "RETRY_SCHEDULED",
        "FAILED_TERMINAL",
        "QUARANTINED",
        "CANCELLED",
        "EXPIRED",
    ]
    assert context["inferred_mappings"] == []


def test_all_runtime_identifiers_statuses_review_auth_artifact_and_hash_are_null() -> (
    None
):
    selections = _plan()["selection_boundary"]
    assert selections == generator.EXPECTED_SELECTIONS
    assert all(value is None for value in selections.values())


def test_all_runtime_collections_are_empty_and_counts_are_null() -> None:
    collections = _plan()["collection_boundary"]
    assert collections == generator.EXPECTED_COLLECTIONS
    for key in (
        "packets",
        "versions",
        "jobs",
        "transitions",
        "mappings",
        "reviews",
        "approvals",
        "artifacts",
    ):
        assert collections[key] == []
    for key in (
        "packet_count",
        "version_count",
        "job_count",
        "transition_count",
        "mapping_count",
        "review_count",
        "approval_count",
        "artifact_count",
    ):
        assert collections[key] is None


def test_lifecycle_is_unavailable_unapproved_and_blocked_exactly() -> None:
    lifecycle = _plan()["lifecycle_boundary"]
    assert lifecycle == generator.EXPECTED_LIFECYCLE
    assert lifecycle["transition_status"] == "UNAVAILABLE"
    assert lifecycle["mapping_status"] == "UNAVAILABLE"
    assert lifecycle["approval"] is False
    assert lifecycle["generation_permitted"] is False
    assert lifecycle["blockers"] == generator.EXPECTED_BLOCKERS


def test_every_runtime_boundary_is_not_executed_with_exact_zero_actions() -> None:
    execution = _plan()["execution_boundary"]
    assert execution == generator.EXPECTED_EXECUTION
    for key in (
        "packet",
        "version",
        "transition",
        "mapping",
        "review",
        "authorization",
        "artifact",
        "repository",
        "database",
        "job",
        "event",
        "api",
        "approval",
        "generation",
        "external",
    ):
        assert execution[key] == "NOT_EXECUTED"
    assert tuple(execution["action_counts"]) == generator.ACTION_COUNT_KEYS
    assert all(
        type(value) is int and value == 0
        for value in execution["action_counts"].values()
    )


def test_formal_staging_release_and_production_evidence_remain_unexecuted() -> None:
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

    forbidden = {"PASS", "READY_TO_GENERATE", "VALIDATED", "IMPLEMENTED"}
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

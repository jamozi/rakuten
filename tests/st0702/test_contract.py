"""Closed contract and projection assertions for ST-0702."""

from __future__ import annotations

import ast
from typing import Any, cast

from scripts import build_st0702_context_pack_reference_plan as generator


def _plan() -> dict[str, Any]:
    contract = generator.load_contract()
    return generator.reference_plan(
        contract, generator._validate_st0701(generator.REPO_ROOT)
    )


def test_contract_and_document_are_exact_non_executable_boundaries() -> None:
    contract = generator.load_contract()
    plan = _plan()
    assert tuple(contract) == generator.CONTRACT_KEYS
    assert tuple(plan) == generator.PLAN_KEYS
    assert plan["document"] == generator.EXPECTED_DOCUMENT
    assert plan["document"]["executable"] is False
    assert plan["document"]["interface_only"] is True
    assert plan["document"]["decision"] == "NOT_READY"
    assert plan["document"]["approval"] is None
    assert plan["document"]["story_acceptance"] is False


def test_predecessors_bind_exact_commits_bytes_and_safe_semantics() -> None:
    predecessors = _plan()["predecessor_bindings"]
    assert predecessors == generator.EXPECTED_PREDECESSORS
    assert predecessors["st0604"]["feature_commit"] == (
        "ced9029f767c63b82690b13cb8d90d1b8eb4b882"
    )
    assert predecessors["st0701"]["base_commit"] == (
        "679ccdc4a49fca8e1bee8827177be7130d6d45b6"
    )
    assert len(predecessors["st0604"]["artifacts"]) == 9
    assert len(predecessors["st0701"]["artifacts"]) == 9
    assert "known_owner_debt" not in predecessors["st0701"]
    semantics = predecessors["st0701"]["required_semantics"]
    assert semantics["source_packet_required_task_count"] == 9
    assert semantics["source_packet_not_required_task_count"] == 3
    assert semantics["typed_manifest_only"] is True
    assert semantics["tools_allowed"] is False
    assert semantics["network_access"] is False
    assert semantics["state_change_allowed"] is False
    assert semantics["provider_storage_allowed"] is False
    assert semantics["strict_structured_output"] is True
    assert semantics["forbidden_inputs_excluded"] is True
    assert semantics["required_input_checks_complete"] is True


def test_registry_projection_preserves_all_rows_order_metadata_and_token_limits() -> (
    None
):
    projection = cast(dict[str, Any], _plan()["registry_projection"])
    source = generator._validate_st0701(generator.REPO_ROOT)
    assert projection["task_count"] == 12
    assert projection["activation_inferred"] is False
    assert projection["activated_task_count"] is None
    assert projection["selected_task_count"] is None
    assert projection["registry_document"] == source["document"]
    assert projection["tasks"] == source["tasks"]
    assert projection["task_codes"] == list(generator.EXPECTED_TASK_CODES)
    assert [
        (
            row["max_input_tokens"],
            row["max_output_tokens"],
            row["max_output_characters"],
        )
        for row in projection["token_limit_distribution"]
    ] == list(generator.EXPECTED_TOKEN_LIMITS)
    assert all(tuple(row) == generator.TASK_ROW_KEYS for row in projection["tasks"])
    required = [
        row["task"]["task_code"]
        for row in projection["tasks"]
        if row["task"]["input_contract"]["source_packet_required"] is True
    ]
    not_required = [
        row["task"]["task_code"]
        for row in projection["tasks"]
        if row["task"]["input_contract"]["source_packet_required"] is False
    ]
    assert required == list(generator.EXPECTED_SOURCE_PACKET_REQUIRED_TASK_CODES)
    assert not_required == list(
        generator.EXPECTED_SOURCE_PACKET_NOT_REQUIRED_TASK_CODES
    )


def test_all_runtime_inputs_algorithms_collections_and_actions_remain_absent() -> None:
    plan = _plan()
    assert plan["packing_rules"] == generator.EXPECTED_PACKING_RULES
    assert all(value is None for value in plan["packing_rules"]["unavailable"].values())
    assert plan["selection_boundary"] == generator.EXPECTED_SELECTIONS
    assert all(value is None for value in plan["selection_boundary"].values())
    collections = plan["collection_boundary"]
    for key, value in collections.items():
        assert value == [] if not key.endswith("_count") else value is None
    assert plan["build_boundary"] == generator.EXPECTED_BUILD_BOUNDARY
    assert plan["execution_boundary"] == generator.EXPECTED_EXECUTION
    assert all(
        value == 0 for value in plan["execution_boundary"]["action_counts"].values()
    )
    assert plan["verification_boundary"] == generator.EXPECTED_VERIFICATION


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

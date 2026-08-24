"""Closed contract and source projection assertions for ST-0705."""

from __future__ import annotations

import ast
from typing import Any

from scripts import build_st0705_ai_output_validation_reference_plan as generator


EXPECTED_GATE_IDS = [f"AIG-{number:03d}" for number in range(0, 100, 10)]
EXPECTED_VALIDATORS = [
    "JSON parse and exact JSON Schema",
    "Unknown Property and Enum",
    "Resource ID and Manifest membership",
    "Fact ID and Subject/Product identity",
    "Number/date/unit/tax/currency exactness",
    "Rank/order preservation",
    "Forbidden Field/Term and review-body contamination marker",
    "Secret/credential pattern",
    "Output length and Claim count",
    "Hash/version consistency",
]
EXPECTED_FAILURE_CODES = [
    *[f"AI-OUT-{number:03d}" for number in range(1, 5)],
    *[f"AI-FCT-{number:03d}" for number in range(1, 5)],
    *[f"AI-POL-{number:03d}" for number in range(1, 6)],
]


def _plan() -> dict[str, Any]:
    loaded = generator.reference_plan(generator.load_contract())
    assert isinstance(loaded, dict)
    return loaded


def test_document_is_an_exact_non_executable_fail_closed_boundary() -> None:
    plan = _plan()
    assert tuple(plan) == generator.PLAN_KEYS
    assert plan["document"] == generator.EXPECTED_DOCUMENT
    assert plan["document"]["classification"] == (
        "SOURCE_DERIVED_NON_EXECUTABLE_AI_OUTPUT_VALIDATION_REFERENCE_PLAN"
    )
    assert plan["document"]["executable"] is False
    assert plan["evaluation_boundary"] == generator.EXPECTED_EVALUATION_BOUNDARY
    assert plan["evaluation_boundary"]["candidate_validation"] == "UNEVALUABLE"
    assert plan["evaluation_boundary"]["content_validation"] == "UNEVALUABLE"
    assert plan["evaluation_boundary"]["decision"] == "NOT_READY"
    assert plan["evaluation_boundary"]["story_acceptance_satisfied"] is False
    assert plan["evaluation_boundary"]["schema_only_acceptance_forbidden"] is True
    assert plan["evaluation_boundary"]["event_emission"] is False


def test_exact_canonical_gates_validators_failures_controls_and_suites_project() -> (
    None
):
    plan = _plan()
    assert [row["id"] for row in plan["gate_catalog"]] == EXPECTED_GATE_IDS
    assert len(plan["gate_catalog"]) == 10
    assert all(row["blocking"] is True for row in plan["gate_catalog"])
    assert plan["validator_catalog"] == EXPECTED_VALIDATORS
    assert len(plan["validator_catalog"]) == 10
    assert [row["code"] for row in plan["failure_catalog"]] == (EXPECTED_FAILURE_CODES)
    assert {row["domain"] for row in plan["failure_catalog"]} == {
        "OUTPUT",
        "FACTUAL",
        "POLICY",
    }
    assert [row["id"] for row in plan["security_controls"]] == [
        f"SEC-AI-{number:03d}" for number in range(1, 9)
    ]
    assert [row["id"] for row in plan["test_suites"]] == ["TST-019", "TST-020"]
    assert all(row["execution_status"] == "NOT_EXECUTED" for row in plan["test_suites"])


def test_predecessors_are_exact_byte_and_semantic_bindings() -> None:
    bindings = _plan()["predecessor_bindings"]
    assert [row["story_id"] for row in bindings] == ["ST-0702", "ST-0703", "ST-0605"]
    assert bindings == generator.expected_predecessor_bindings()
    context = bindings[0]
    assert context["feature_commit"] == "3fc1bd8b3135ecefaa05989b90906ecab8380119"
    assert context["artifacts"][1]["sha256"] == (
        "b684e534268de79e4b118713f07932cfa71d10bda2e092003f00985f76811eaf"
    )
    recorded = next(row for row in bindings if row["story_id"] == "ST-0703")
    assert recorded["recorded_schema_success_is_content_validation"] is False
    assert recorded["content_validation"] == "NOT_EXECUTED"


def test_candidate_collections_counts_and_actions_remain_unset_or_zero() -> None:
    plan = _plan()
    state = plan["validation_state"]
    for key in (
        "candidates",
        "facts",
        "claims",
        "mappings",
        "findings",
        "evidence",
        "reports",
    ):
        assert state[key] == []
        assert state["observed_counts"][key] is None
    assert state["context"] is None
    execution = plan["execution_state"]
    assert all(
        execution[key] == "NOT_EXECUTED"
        for key in (
            "validation",
            "runtime",
            "provider",
            "job",
            "event",
            "formal",
            "live",
        )
    )
    assert all(
        type(value) is int and value == 0
        for value in execution["action_counts"].values()
    )


def test_builder_has_no_external_runtime_or_action_surface() -> None:
    tree = ast.parse((generator.REPO_ROOT / generator.GENERATOR_PATH).read_bytes())
    imports = {
        alias.name.split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imports.isdisjoint(
        {
            "boto3",
            "httpx",
            "requests",
            "socket",
            "sqlalchemy",
            "subprocess",
            "urllib",
        }
    )
    attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert attributes.isdisjoint(
        {"connect", "execute", "getenv", "navigate", "publish", "request", "send"}
    )

"""Positive contract and projection assertions for the ST-0308 reference."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts import build_st0308_persistence_boundary_reference as builder


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_contract_is_closed_source_bound_and_non_executable() -> None:
    model = builder.load_and_validate_contract(REPO_ROOT)
    contract = model.contract

    assert tuple(contract) == builder.TOP_LEVEL_KEYS
    assert contract["document"] == builder.EXPECTED_DOCUMENT
    assert contract["scope"] == builder.EXPECTED_SCOPE
    assert contract["local_design_gaps"] == builder.EXPECTED_LOCAL_GAPS
    assert contract["selected_design"] == builder.EXPECTED_SELECTED_DESIGN
    assert contract["implementation_inventory"] == (
        builder.EXPECTED_IMPLEMENTATION_INVENTORY
    )
    assert contract["safe_defaults"] == builder.EXPECTED_SAFE_DEFAULTS
    assert contract["activation"] == builder.EXPECTED_ACTIVATION
    assert contract["action_boundary"] == builder.EXPECTED_ACTION_BOUNDARY
    assert contract["evidence_boundary"] == builder.EXPECTED_EVIDENCE_BOUNDARY
    assert contract["downstream_boundary"] == builder.EXPECTED_DOWNSTREAM_BOUNDARY


def test_exact_source_and_predecessor_inventories() -> None:
    model = builder.load_and_validate_contract(REPO_ROOT)
    contract = model.contract
    sources = contract["sources"]
    predecessors = contract["predecessor_bindings"]

    assert len(sources) == 16
    assert [row["uri"] for row in sources] == [
        f"repo://{path}" for path, _size, _digest in builder.SOURCE_ROWS
    ]
    assert tuple(predecessors) == ("ST-0304", "ST-0105")
    assert predecessors["ST-0304"]["classification"] == "OPAQUE_CONTEXT_ONLY"
    assert predecessors["ST-0304"]["semantic_projection"] == "FORBIDDEN"
    assert len(predecessors["ST-0304"]["rows"]) == 21
    assert predecessors["ST-0105"]["classification"] == (
        "API_BINDINGS_ONLY_NOT_PERSISTENCE_DESIGN"
    )
    assert predecessors["ST-0105"]["semantic_projection"] == ("MANIFEST_FACTS_ONLY")
    assert len(predecessors["ST-0105"]["rows"]) == 11
    assert predecessors["ST-0105"]["manifest_facts"] == (builder.EXPECTED_ST0105_FACTS)


def test_six_gaps_are_local_unresolved_and_exactly_null() -> None:
    contract = builder.load_and_validate_contract(REPO_ROOT).contract
    registry = contract["local_design_gaps"]

    assert registry["canonical_open_decisions"] == []
    assert registry["canonical_open_decision_count"] == 0
    assert [gap["id"] for gap in registry["gaps"]] == [
        f"ST0308-D{index}" for index in range(1, 7)
    ]
    assert all(
        gap["source_kind"] == "LOCAL_NONCANONICAL_DESIGN_GAP"
        and gap["resolution_state"] == "UNRESOLVED"
        and gap["selected_value"] is None
        and gap["resolution_payload"] is None
        and gap["runtime_implementation"] == "BLOCKED"
        for gap in registry["gaps"]
    )
    assert all(value is None for value in contract["selected_design"].values())


def test_every_inventory_and_action_count_is_builtin_integer_zero() -> None:
    contract = builder.load_and_validate_contract(REPO_ROOT).contract
    counts = (
        *contract["implementation_inventory"].values(),
        *contract["action_boundary"]["counts"].values(),
    )

    assert len(contract["implementation_inventory"]) == 15
    assert len(contract["action_boundary"]["counts"]) == 15
    assert all(type(value) is int and value == 0 for value in counts)


def test_generated_projection_has_exact_order_and_prohibitions() -> None:
    model = builder.load_and_validate_contract(REPO_ROOT)
    document = builder.reference_plan_document(model)

    assert tuple(document) == builder.REFERENCE_PLAN_KEYS
    assert document["prohibited_interpretations"] == list(
        builder.PROHIBITED_INTERPRETATIONS
    )
    assert document["source_bindings"] == model.contract["sources"]
    assert document["predecessor_bindings"] == model.contract["predecessor_bindings"]
    assert document["local_design_gap_registry"] == model.contract["local_design_gaps"]


def test_committed_reference_plan_contains_no_runtime_readiness() -> None:
    document: dict[str, Any] = json.loads(
        (REPO_ROOT / builder.REFERENCE_PLAN_PATH).read_text(encoding="utf-8")
    )

    assert document["document"]["executable"] is False
    assert document["activation"]["enabled"] is False
    assert document["activation"]["runtime_eligible"] is False
    assert document["activation"]["authority"] == "NOT_GRANTED"
    assert document["evidence_boundary"]["acceptance_criteria_satisfied"] is False
    assert not any(document["downstream_boundary"].values())

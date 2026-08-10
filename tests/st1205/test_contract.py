"""Exact authored and generated contract assertions for ST-1205."""

from __future__ import annotations

from collections import Counter
from typing import Any

import yaml

from conftest import REPOSITORY_ROOT
from scripts import build_st1205_kpi_read_model_reference_plan as builder


def test_authored_contract_loads_and_is_exact() -> None:
    loaded = builder.load_contract(REPOSITORY_ROOT)
    assert tuple(loaded) == builder.CONTRACT_KEYS
    assert loaded["document"] == builder.EXPECTED_DOCUMENT
    assert loaded["authority"] == builder.EXPECTED_AUTHORITY
    assert loaded["predecessors"] == builder.EXPECTED_PREDECESSORS


def test_document_preserves_nonexecuting_boundary(contract: dict[str, Any]) -> None:
    document = contract["document"]
    assert document["classification"] == (
        "SOURCE_DERIVED_NON_EXECUTABLE_NON_ATTESTING_KPI_READ_MODEL_REFERENCE_PLAN"
    )
    assert document["executable"] is False
    assert document["non_attesting"] is True
    assert document["interface_only"] is True
    assert document["decision"] == "NOT_READY"
    assert document["story_acceptance"] is False
    assert document["approval"] is None
    assert document["production_eligible"] is False


def test_generated_plan_has_exact_top_level_order(plan: dict[str, Any]) -> None:
    assert tuple(plan) == builder.PLAN_KEYS


def test_projection_contains_exact_ordered_canonical_rows(
    plan: dict[str, Any],
) -> None:
    canonical = yaml.safe_load((REPOSITORY_ROOT / builder.KPI_CATALOG_PATH).read_text())
    projection = plan["catalog_projection"]
    assert projection["kpi_ids"] == list(builder.KPI_IDS)
    assert projection["definitions"] == canonical["kpis"]
    assert len(projection["definitions"]) == 30
    assert [row["id"] for row in projection["definitions"]] == list(builder.KPI_IDS)


def test_all_nine_canonical_fields_are_verbatim(plan: dict[str, Any]) -> None:
    rows = plan["catalog_projection"]["definitions"]
    assert all(tuple(row) == builder.KPI_FIELDS for row in rows)
    assert plan["catalog_projection"]["source_fields"] == list(builder.KPI_FIELDS)
    assert all(type(value) is str for row in rows for value in row.values())


def test_domain_distribution_is_exact(plan: dict[str, Any]) -> None:
    rows = plan["catalog_projection"]["definitions"]
    actual = dict(Counter(row["domain"] for row in rows))
    assert actual == builder.DOMAIN_DISTRIBUTION
    assert plan["catalog_projection"]["domain_distribution"] == actual


def test_formula_text_is_inert_and_unmodified(plan: dict[str, Any]) -> None:
    canonical = yaml.safe_load((REPOSITORY_ROOT / builder.KPI_CATALOG_PATH).read_text())
    projection = plan["catalog_projection"]
    assert projection["formula_representation"] == "NON_EXECUTABLE_SOURCE_TEXT"
    assert [row["formula"] for row in projection["definitions"]] == [
        row["formula"] for row in canonical["kpis"]
    ]
    assert projection["activation_inferred"] is False


def test_definition_calculation_and_verification_counts_are_honest(
    plan: dict[str, Any],
) -> None:
    projection = plan["catalog_projection"]
    verification = plan["verification_boundary"]
    assert projection["definition_count"] == 30
    assert projection["calculation_count"] == 0
    assert projection["verified_count"] == 0
    assert verification["definitions_projected"] == 30
    assert verification["definitions_total"] == 30
    assert verification["calculations_completed"] == 0
    assert verification["calculations_total"] == 30
    assert verification["calculations_verified"] == 0
    assert verification["verified_total"] == 30


def test_calculation_inputs_and_outputs_remain_unavailable(
    plan: dict[str, Any],
) -> None:
    boundary = plan["calculation_boundary"]
    for key in ("calculation_version", "period", "sql"):
        assert boundary[key] is None
    for key in (
        "kpi_mappings",
        "source_mappings",
        "watermarks",
        "inputs",
        "tables",
        "job_payloads",
        "read_model_rows",
        "results",
        "evidence",
    ):
        assert boundary[key] == []
    for key in (
        "mapping_count",
        "watermark_count",
        "input_count",
        "table_count",
        "job_payload_count",
        "read_model_row_count",
        "result_count",
        "evidence_count",
    ):
        assert boundary[key] is None
    assert boundary["empty_means_zero"] is False


def test_execution_is_all_not_executed_and_counts_are_exact_zero(
    plan: dict[str, Any],
) -> None:
    execution = plan["execution_boundary"]
    assert set(execution["action_counts"]) == set(builder.ACTION_COUNT_KEYS)
    assert all(
        type(value) is int and value == 0
        for value in execution["action_counts"].values()
    )
    assert execution["external_actions"] == []
    assert all(
        value == "NOT_EXECUTED"
        for key, value in execution.items()
        if key not in {"action_counts", "external_actions"}
    )


def test_formal_and_release_boundaries_remain_unexecuted(plan: dict[str, Any]) -> None:
    verification = plan["verification_boundary"]
    assert verification["calculation_status"] == "NOT_EXECUTED"
    assert verification["verification_status"] == "NOT_EXECUTED"
    assert verification["TST-030"] == "NOT_EXECUTED"
    assert verification["formal_validation"] == "NOT_EXECUTED"
    assert verification["story_acceptance"] is False
    assert verification["decision"] == "NOT_READY"


def test_predecessor_semantics_are_closed(plan: dict[str, Any]) -> None:
    predecessors = plan["predecessor_bindings"]
    assert predecessors["st1201"]["required_semantics"] == {
        "default_mode": "DISABLED_OD_012",
        "tracking": "DISABLED",
        "persistence": "NOT_EXECUTED",
        "measurement": False,
        "decision": "NOT_READY",
        "read_model_rows": [],
    }
    assert (
        predecessors["st1203"]["required_semantics"]["empty_page_proves_zero"] is False
    )
    assert predecessors["st1203"]["required_semantics"]["supersession"] == "NOT_DEFINED"
    assert predecessors["st1204"]["required_semantics"]["returned_row_count"] == 2
    assert predecessors["st1204"]["required_semantics"]["provider_row_count"] == 3
    assert predecessors["st1204"]["required_semantics"]["pagination_performed"] is False
    assert (
        predecessors["st1204"]["required_semantics"]["numeric_aggregation_performed"]
        is False
    )


def test_readme_distinguishes_projection_from_results() -> None:
    text = (REPOSITORY_ROOT / builder.README_PATH).read_text(encoding="utf-8")
    for phrase in (
        "not a KPI engine or read model",
        "Empty means unavailable or not executed",
        "calculations remain 0/30",
        "formal TST-030 is `NOT_EXECUTED`",
    ):
        assert phrase in text


def test_no_runtime_or_public_projection_payload_exists(plan: dict[str, Any]) -> None:
    assert "calculated_values" not in plan
    assert "public_rows" not in plan
    assert "recommendations" not in plan
    assert "sql_statements" not in plan
    assert "job_definitions" not in plan
    assert "tracking_events" not in plan

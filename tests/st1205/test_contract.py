"""Contract and canonical mapping tests for ST-1205 V2."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import yaml

from conftest import REPOSITORY_ROOT
from raos.domain.analytics.kpi_read_model import (
    KPI_CALCULATION_VERSION,
    KPI_DEFINITIONS,
    KPI_DEFINITION_VERSION,
    KPI_IDS,
    RAKUTEN_BLOG_PROGRAM,
    UnavailableReason,
)
from scripts import build_st1205_kpi_read_model_reference_plan as builder


def test_contract_loads_with_current_authority_and_predecessors() -> None:
    loaded = builder.load_contract(REPOSITORY_ROOT)
    assert loaded["document"]["schema_version"] == "2.0.0"
    assert loaded["authority"]["canonical_story"]["story_id"] == "ST-1205"
    assert [row["story_id"] for row in loaded["predecessors"]] == [
        "ST-1201",
        "ST-1203",
        "ST-1204",
    ]
    assert (
        loaded["predecessors"][2]["required_semantics"]["returned_rows_incomplete"]
        is True
    )


def test_all_thirty_runtime_definitions_match_canonical_catalog() -> None:
    catalog = yaml.safe_load((REPOSITORY_ROOT / builder.KPI_CATALOG_PATH).read_text())
    assert tuple(definition.kpi_id for definition in KPI_DEFINITIONS) == KPI_IDS
    assert len(KPI_DEFINITIONS) == 30
    for definition, canonical in zip(KPI_DEFINITIONS, catalog["kpis"], strict=True):
        assert definition.kpi_id == canonical["id"]
        assert definition.name == canonical["name"]
        assert definition.canonical_formula == canonical["formula"]
        assert definition.time_grain == canonical["cadence"]


def test_every_definition_has_complete_typed_governance() -> None:
    for definition in KPI_DEFINITIONS:
        assert definition.inputs
        assert all(input_spec.metric_key for input_spec in definition.inputs)
        assert all(input_spec.source.value for input_spec in definition.inputs)
        assert all(input_spec.role.value for input_spec in definition.inputs)
        assert definition.quantize > Decimal(0)
        assert definition.cohort
        assert definition.included_traffic
        assert definition.excluded_traffic
        assert definition.attribution_display
        assert definition.rounding == "ROUND_HALF_EVEN"
        assert definition.zero_semantics == "VERIFIED_ZERO_IS_ZERO"
        assert definition.division_by_zero == "UNAVAILABLE"
        assert definition.owner
        assert definition.decision_use


def test_contract_has_exact_decimal_unavailable_and_allocation_policies(
    contract: dict[str, Any],
) -> None:
    assert contract["input_contract"]["program_id"] == RAKUTEN_BLOG_PROGRAM
    assert contract["input_contract"]["float_allowed"] is False
    assert contract["input_contract"]["missing_allowed_as_zero"] is False
    assert "NEVER_BE_ALLOCATED" in contract["input_contract"]["allocation_policy"]
    assert contract["availability_contract"]["unavailable_value"] is None
    assert contract["availability_contract"]["unavailable_is_zero"] is False
    assert contract["availability_contract"]["closed_unavailable_reasons"] == [
        reason.value for reason in UnavailableReason
    ]
    assert (
        contract["definition_contract"]["definition_version"] == KPI_DEFINITION_VERSION
    )
    assert (
        contract["definition_contract"]["calculation_version"]
        == KPI_CALCULATION_VERSION
    )
    assert contract["definition_contract"]["calculation_count"] == 30


def test_learning_contract_is_improvement_only_and_never_ranking_input(
    contract: dict[str, Any],
) -> None:
    learning = contract["learning_contract"]
    assert learning["same_period_required"] is True
    assert learning["same_program_required"] is True
    assert learning["verified_attribution_required"] is True
    assert learning["modifies_article_html"] is False
    assert learning["modifies_cta"] is False
    assert learning["modifies_product_selection"] is False
    assert learning["modifies_recommendation_order"] is False
    assert learning["recommendation_inputs_forbidden"] == [
        "affiliate rate",
        "EPC",
        "RPM",
        "commission",
        "profit",
    ]


def test_debt_closure_is_local_and_external_work_remains_unexecuted(
    contract: dict[str, Any],
) -> None:
    assert [row["id"] for row in contract["debt"]["closed"]] == [
        "DEBT-W2-054",
        "DEBT-W2-062",
    ]
    assert [row["id"] for row in contract["debt"]["remaining"]] == [
        "EXTERNAL-TST-030",
        "LIVE-PROVIDERS",
    ]
    boundary = contract["execution_boundary"]
    for key in (
        "repository",
        "database",
        "provider",
        "network",
        "public_projection",
        "live",
        "staging",
        "release",
        "production",
        "formal_TST-030",
    ):
        assert boundary[key] == "NOT_EXECUTED"
    assert boundary["recommendation_input"] == "DISABLED"
    assert boundary["story_acceptance"] is False


def test_readme_states_local_completion_without_formal_claim() -> None:
    text = (REPOSITORY_ROOT / builder.README_PATH).read_text(encoding="utf-8")
    for phrase in (
        "reproduces 30/30 values",
        "`UNAVAILABLE`, never an implicit zero",
        "recommendation_order_effect=false",
        "DEBT-W2-054 is closed",
        "Formal TST-030",
        "do not constitute Canonical Story acceptance",
    ):
        assert phrase in text

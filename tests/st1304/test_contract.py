"""Closed contract and projection assertions for ST-1304."""

from __future__ import annotations

import ast
import json
from typing import Any, cast

import yaml

from scripts import build_st1304_cost_unit_economics_reference_plan as generator


def _plan() -> dict[str, Any]:
    return cast(dict[str, Any], generator.reference_plan(generator.load_contract()))


def test_contract_and_plan_have_exact_closed_top_level_shapes() -> None:
    assert tuple(generator.load_contract()) == generator.CONTRACT_KEYS
    assert tuple(_plan()) == generator.PLAN_KEYS


def test_document_is_nonexecutable_unapproved_and_not_ready() -> None:
    assert _plan()["document"] == {
        "schema_version": "1.0.0",
        "story_id": "ST-1304",
        "classification": "SOURCE_DERIVED_NONEXECUTABLE_COST_UNIT_ECONOMICS_REFERENCE_PLAN",
        "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
        "executable": False,
        "activation": False,
        "runtime_eligible": False,
        "authority": "NOT_GRANTED",
        "decision": "NOT_READY",
        "story_acceptance": False,
        "production_eligible": False,
        "approval": None,
        "canonical_status": "UNCHANGED",
    }


def test_authority_preserves_fr015_and_both_blocking_decisions() -> None:
    authority = _plan()["authority"]
    assert authority["canonical_story"]["story_id"] == "ST-1304"
    assert authority["requirement"]["required_id"] == "FR-015"
    assert authority["open_decisions"]["required_ids"] == ["OD-005", "OD-009"]
    assert authority["open_decisions"]["required_status"] == "HUMAN_DECISION_REQUIRED"
    assert authority["open_decisions"]["blocking"] is True
    assert authority["authority_kind"] == "SOURCE_DERIVED_REFERENCE_ONLY"
    assert authority["changes_canonical_status"] is False


def test_dependencies_bind_feature_and_current_artifact_commits() -> None:
    dependencies = _plan()["dependency_bindings"]
    assert tuple(dependencies) == ("st0706", "st1205", "st1303")
    assert (
        dependencies["st0706"]["feature_commit"]
        == "fe867f85c68ea661b055f4edd32ef6fbc600fa68"
    )
    assert (
        dependencies["st0706"]["artifact_binding_commit"]
        == "2a53b66146d27ea8f5e32c65888a13a32d576c88"
    )
    assert (
        dependencies["st1205"]["feature_commit"]
        == "fe18734820cb6f78622950549d32f1ab5394214e"
    )
    assert (
        dependencies["st1205"]["artifact_binding_commit"]
        == "8aab6c4720863f51854b89c4bcac19faabd733c6"
    )
    assert (
        dependencies["st1303"]["feature_commit"]
        == "0436364b8737d05b9aea3a08da8bf15c04292b12"
    )
    assert (
        dependencies["st1303"]["artifact_binding_commit"]
        == dependencies["st1303"]["feature_commit"]
    )
    assert [len(dependencies[key]["artifacts"]) for key in dependencies] == [9, 9, 9]


def test_dependency_semantics_expose_no_durable_inputs_or_results() -> None:
    dependencies = _plan()["dependency_bindings"]
    assert (
        dependencies["st0706"]["required_semantics"]["actual_cost_source"]
        == "CALLER_SCRIPTED_METADATA"
    )
    assert dependencies["st0706"]["required_semantics"]["actual_cost_verified"] is False
    assert dependencies["st0706"]["required_semantics"]["durable_cost_fact"] is False
    assert dependencies["st1205"]["required_semantics"]["calculation_count"] == 0
    assert dependencies["st1205"]["required_semantics"]["read_model_rows"] == []
    assert dependencies["st1303"]["required_semantics"]["provider_facts"] == []
    assert dependencies["st1303"]["required_semantics"]["allocations"] == []
    assert dependencies["st1303"]["required_semantics"]["provider_total_jpy"] is None


def test_exact_relevant_kpi_definitions_are_inert_source_text() -> None:
    constraints = _plan()["canonical_constraints"]
    definitions = constraints["relevant_kpi_definitions"]
    assert [row["id"] for row in definitions] == list(generator.RELEVANT_KPI_IDS)
    assert all(row["implementation_status"] == "NOT_STARTED" for row in definitions)
    assert all(row["runtime_verification"] == "NOT_EXECUTED" for row in definitions)
    assert constraints["formula_representation"] == "NONEXECUTABLE_SOURCE_TEXT"


def test_canonical_storage_job_and_event_are_vocabulary_only() -> None:
    constraints = _plan()["canonical_constraints"]
    assert [row["table"] for row in constraints["storage_shapes"]] == list(
        generator.TABLE_NAMES
    )
    assert all(
        row["classification"] == "RESTRICTED" for row in constraints["storage_shapes"]
    )
    assert (
        constraints["calculation_job"]["job_type"]
        == "finance.calculate_unit_economics.v1"
    )
    assert constraints["calculation_job"]["executable_here"] is False
    assert (
        constraints["calculation_event"]["event_type"]
        == "jp.raos.finance.unit_economics_calculated.v1"
    )
    assert constraints["calculation_event"]["executable_here"] is False
    assert (
        constraints["measurement_principles"]["finance_as_recommendation_input"]
        is False
    )


def test_od005_keeps_labor_and_profit_unknown_not_zero() -> None:
    boundary = _plan()["open_decision_boundary"]
    labor = boundary["labor"]
    assert boundary["state"] == "BLOCKED_PENDING_BUSINESS_OWNER"
    assert labor["decision_id"] == "OD-005"
    assert labor["reviewer"] is None
    assert labor["backup_reviewer"] is None
    assert labor["hourly_cost_jpy"] is None
    assert labor["labor_cost_state"] == "UNKNOWN"
    assert labor["unknown_labor_is_zero"] is False
    assert labor["contribution_profit_state"] == "UNKNOWN"
    assert labor["publication_allowed"] is False


def test_od009_selects_no_budget_and_keeps_production_disabled() -> None:
    budget = _plan()["open_decision_boundary"]["budget"]
    assert budget["decision_id"] == "OD-009"
    for field in (
        "aws_monthly_cap_jpy",
        "llm_monthly_cap_jpy",
        "external_provider_monthly_cap_jpy",
        "automatic_stop_threshold",
    ):
        assert budget[field] is None
    assert budget["development_cap"] == "UNSELECTED_LOW_SAFE_DEFAULT"
    assert budget["production_enabled"] is False


def test_every_unavailable_selection_remains_null() -> None:
    selection = _plan()["selection_boundary"]
    assert selection["state"] == "NOT_EVALUATED"
    assert all(value is None for key, value in selection.items() if key != "state")


def test_collections_empty_and_counts_totals_unknown() -> None:
    collections = _plan()["collections"]
    assert all(collections[key] == [] for key in generator.COLLECTION_KEYS)
    assert all(
        collections[key] is None
        for key in (*generator.COUNT_KEYS, *generator.TOTAL_KEYS)
    )
    assert collections["empty_means_zero"] is False


def test_evaluation_never_vacuously_passes() -> None:
    evaluation = _plan()["evaluation_boundary"]
    expected = {"status": "NOT_EVALUATED", "evaluable": False, "result": None}
    assert all(evaluation[key] == expected for key in generator.EVALUATION_KEYS)
    assert evaluation["vacuous_pass_allowed"] is False


def test_execution_has_no_runtime_or_actions() -> None:
    execution = _plan()["execution_boundary"]
    assert all(
        execution[key] == "NOT_EXECUTED" for key in generator.EXECUTION_STATUS_KEYS
    )
    assert tuple(execution["action_counts"]) == generator.ACTION_COUNT_KEYS
    assert all(
        type(value) is int and value == 0
        for value in execution["action_counts"].values()
    )
    assert execution["external_actions"] == []


def test_formal_and_live_evidence_remain_unexecuted() -> None:
    assert _plan()["verification_boundary"] == {
        "relevant_definitions_projected": 7,
        "relevant_definitions_total": 7,
        "calculations_completed": 0,
        "allocations_completed": 0,
        "read_model_rows_created": 0,
        "TST-030": "NOT_EXECUTED",
        "formal_validation": "NOT_EXECUTED",
        "story_acceptance": False,
        "live_evidence": False,
        "decision": "NOT_READY",
    }


def test_reference_plan_is_detached() -> None:
    contract = generator.load_contract()
    first = cast(dict[str, Any], generator.reference_plan(contract))
    first["collections"]["external_cost_facts"].append({"hostile": True})
    first["open_decision_boundary"]["labor"]["hourly_cost_jpy"] = 0
    second = cast(dict[str, Any], generator.reference_plan(contract))
    assert second["collections"]["external_cost_facts"] == []
    assert second["open_decision_boundary"]["labor"]["hourly_cost_jpy"] is None


def test_outputs_contain_no_false_completion_claims() -> None:
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

    assert {"PASS", "READY", "VALIDATED", "IMPLEMENTED"}.isdisjoint(strings(plan))
    assert {"PASS", "READY", "VALIDATED", "IMPLEMENTED"}.isdisjoint(strings(manifest))


def test_builder_has_no_algorithm_process_network_database_provider_or_env_access() -> (
    None
):
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
            "datetime",
            "decimal",
            "httpx",
            "os",
            "random",
            "requests",
            "socket",
            "sqlalchemy",
            "subprocess",
            "time",
            "urllib",
        }
    )

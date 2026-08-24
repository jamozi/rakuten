"""Closed contract and projection assertions for ST-1305."""

from __future__ import annotations

import ast
import json
from typing import Any, cast

import yaml

from scripts import build_st1305_finance_reconciliation_reference_plan as generator


def _plan() -> dict[str, Any]:
    return cast(dict[str, Any], generator.reference_plan(generator.load_contract()))


def test_contract_and_plan_have_exact_closed_top_level_shapes() -> None:
    assert tuple(generator.load_contract()) == generator.CONTRACT_KEYS
    assert tuple(_plan()) == generator.PLAN_KEYS


def test_document_is_nonexecutable_unapproved_and_not_ready() -> None:
    assert _plan()["document"] == {
        "schema_version": "1.0.0",
        "story_id": "ST-1305",
        "classification": "SOURCE_DERIVED_NONEXECUTABLE_FINANCE_RECONCILIATION_REFERENCE_PLAN",
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


def test_authority_preserves_story_local_empty_and_inherited_decisions() -> None:
    authority = _plan()["authority"]
    assert authority["canonical_story"]["story_id"] == "ST-1305"
    assert authority["open_decisions"]["story_local_ids"] == []
    assert authority["open_decisions"]["inherited_safety_constraint_ids"] == [
        "OD-003",
        "OD-005",
        "OD-009",
        "OD-014",
    ]
    assert authority["authority_kind"] == "SOURCE_DERIVED_REFERENCE_ONLY"
    assert authority["changes_canonical_status"] is False


def test_dependency_binds_exact_current_st1304_feature_bytes() -> None:
    dependencies = _plan()["dependency_bindings"]
    assert tuple(dependencies) == ("st1304",)
    dependency = dependencies["st1304"]
    assert dependency["feature_commit"] == "6c73e41d630657138d8f51752d8cd1541026a0f1"
    assert dependency["artifact_binding_commit"] == (
        "fc17a5e6465846df74ced681a3e0b2aeaa94fc9c"
    )
    assert dependency["binding"] == "EXACT_ARTIFACT_BYTES_AT_BINDING_COMMIT"
    assert len(dependency["artifacts"]) == 9


def test_dependency_exposes_no_reconcilable_inputs_or_totals() -> None:
    semantics = _plan()["dependency_bindings"]["st1304"]["required_semantics"]
    for key in (
        "provider_reports",
        "revenue_import_batches",
        "provider_facts",
        "attribution_allocations",
        "external_cost_facts",
        "human_work_logs",
        "cost_allocations",
        "unit_economics_snapshots",
        "read_model_rows",
    ):
        assert semantics[key] == []
    for key in (
        "confirmed_commission_total_jpy",
        "external_cost_total_jpy",
        "human_cost_total_jpy",
        "contribution_profit_total_jpy",
    ):
        assert semantics[key] is None
    assert semantics["empty_means_zero"] is False


def test_exact_canonical_dimensions_are_inert_vocabulary() -> None:
    constraints = _plan()["canonical_constraints"]
    assert tuple(constraints["reconciliation_dimensions"]) == (
        *generator.EXPECTED_RECONCILIATION_DIMENSIONS,
    )
    assert constraints["reconciliation_report_contract_available"] is False
    assert constraints["reconciliation_job_available"] is False
    assert constraints["reconciliation_event_available"] is False
    assert constraints["finance_data_public"] is False
    assert constraints["raw_finance_logging_allowed"] is False
    assert [row["table"] for row in constraints["storage_shapes"]] == list(
        generator.TABLE_NAMES
    )


def test_inherited_open_decisions_remain_closed() -> None:
    boundary = _plan()["inherited_open_decision_boundary"]
    assert boundary["state"] == "BLOCKED_PENDING_EXTERNAL_OR_OWNER_INPUT"
    assert boundary["report_sample"]["report_sample"] is None
    assert boundary["report_sample"]["column_mapping"] is None
    assert boundary["report_sample"]["real_attribution_verified"] is False
    assert boundary["labor"]["hourly_cost_jpy"] is None
    assert boundary["labor"]["labor_cost_state"] == "UNKNOWN"
    assert boundary["labor"]["unknown_labor_is_zero"] is False
    assert boundary["budget"]["production_enabled"] is False
    assert boundary["retention"]["retention_period"] is None
    assert boundary["retention"]["automatic_deletion_enabled"] is False


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
        "reconciliation_dimensions_projected": 7,
        "reconciliation_dimensions_total": 7,
        "evaluations_completed": 0,
        "comparisons_completed": 0,
        "exceptions_created": 0,
        "reports_created": 0,
        "evidence_artifacts_created": 0,
        "TST-030": "NOT_EXECUTED",
        "formal_validation": "NOT_EXECUTED",
        "story_acceptance": False,
        "live_evidence": False,
        "decision": "NOT_READY",
    }


def test_reference_plan_is_detached() -> None:
    contract = generator.load_contract()
    first = cast(dict[str, Any], generator.reference_plan(contract))
    first["collections"]["provider_reports"].append({"hostile": True})
    first["selection_boundary"]["reconciliation_tolerance"] = 0
    second = cast(dict[str, Any], generator.reference_plan(contract))
    assert second["collections"]["provider_reports"] == []
    assert second["selection_boundary"]["reconciliation_tolerance"] is None


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


def test_builder_has_no_process_network_database_provider_or_env_access() -> None:
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

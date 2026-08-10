"""Closed contract and projection assertions for ST-1302."""

from __future__ import annotations

import ast
import json

import yaml

from scripts import (
    build_st1302_provider_fact_commit_reference_plan as generator,
)


def _plan() -> dict[str, object]:
    return generator.reference_plan(generator.load_contract())


def test_contract_and_plan_have_exact_closed_top_level_shapes() -> None:
    assert tuple(generator.load_contract()) == generator.CONTRACT_KEYS
    assert tuple(_plan()) == generator.PLAN_KEYS


def test_document_is_nonexecutable_unapproved_and_not_ready() -> None:
    assert _plan()["document"] == generator.EXPECTED_DOCUMENT


def test_authority_preserves_od003_and_canonical_not_started_boundary() -> None:
    authority = _plan()["authority"]
    assert authority == generator.EXPECTED_AUTHORITY
    assert authority["open_decisions"] == {
        "path": "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",
        "sha256": generator.OPEN_DECISIONS_SHA256,
        "required_id": "OD-003",
        "required_status": "EXTERNAL_EVIDENCE_REQUIRED",
        "blocking": True,
    }
    assert generator.EXPECTED_STORY["implementation_status"] == "NOT_STARTED"
    assert generator.EXPECTED_STORY["verification_status"] == "NOT_EXECUTED"


def test_predecessor_binds_exact_commit_nine_files_and_safe_semantics() -> None:
    predecessor = _plan()["predecessor_binding"]
    assert predecessor == generator.EXPECTED_PREDECESSOR
    assert predecessor["feature_commit"] == generator.PREDECESSOR_COMMIT
    assert len(predecessor["artifacts"]) == 9
    assert predecessor["required_semantics"] == generator.EXPECTED_PREDECESSOR_SEMANTICS


def test_three_source_vocabularies_remain_exact_and_unmapped() -> None:
    vocabularies = _plan()["vocabularies"]
    assert vocabularies == generator.EXPECTED_VOCABULARIES
    assert vocabularies["mapping_defined"] is False
    assert vocabularies["canonical_row_event"] == [
        "GENERATED",
        "CONFIRMED",
        "CANCELLED",
        "ADJUSTED",
    ]
    assert vocabularies["commission_status"] == [
        "GENERATED",
        "CONFIRMED",
        "CANCELLED",
        "ADJUSTED",
        "UNKNOWN",
    ]
    assert vocabularies["commission_event"] == [
        "GENERATED",
        "CONFIRMED",
        "CANCELLED",
        "AMOUNT_CHANGED",
        "CORRECTED",
    ]


def test_fin006_oauth_audit_and_rbac_namespaces_remain_separate() -> None:
    namespaces = _plan()["namespace_separation"]
    assert namespaces == generator.EXPECTED_NAMESPACE_SEPARATION
    assert namespaces["equivalence_inferred"] is False
    assert namespaces["mapping"] == []
    assert {
        namespaces["api_operation"],
        namespaces["oauth_scope"],
        namespaces["audit_action"],
        namespaces["rbac_action"],
    } == {
        "FIN-006",
        "finance:revenue:confirm",
        "revenue_import_confirm",
        "commit_revenue_import",
    }


def test_preview_hash_inconsistency_remains_unresolved() -> None:
    inconsistency = _plan()["unresolved_inconsistency"]
    assert inconsistency == generator.EXPECTED_UNRESOLVED_INCONSISTENCY
    assert inconsistency["job_catalog_idempotency_basis"] == [
        "revenue_import_id",
        "source_sha256",
        "preview_hash",
    ]
    assert "preview_hash" not in inconsistency["commit_job_payload_fields"]
    assert "preview_hash" not in inconsistency["admin_confirm_request_fields"]
    assert inconsistency["selected_preview_hash"] is None
    assert inconsistency["replacement_algorithm"] is None
    assert inconsistency["resolved"] is False


def test_selection_invents_no_hash_identity_policy_result_or_approval() -> None:
    selection = _plan()["selection_boundary"]
    assert selection == generator.EXPECTED_SELECTION_BOUNDARY
    assert selection["currency_literal"] == "JPY"
    assert selection["data_class"] == "RESTRICTED"
    assert all(
        value is None
        for key, value in selection.items()
        if key not in {"data_class", "currency_literal"}
    )


def test_collections_are_empty_while_counts_amounts_remain_unknown() -> None:
    collections = _plan()["collections"]
    assert collections == generator.EXPECTED_COLLECTIONS
    for key in (
        "canonical_rows",
        "provider_facts",
        "commission_events",
        "emitted_events",
        "writes",
    ):
        assert collections[key] == []
    for key in (
        "canonical_row_count",
        "provider_fact_count",
        "commission_event_count",
        "emitted_event_count",
        "write_count",
        "amount_total_jpy",
    ):
        assert collections[key] is None
    assert collections["empty_means_zero"] is False


def test_checks_are_unevaluable_null_and_never_vacuously_pass() -> None:
    evaluation = _plan()["evaluation_boundary"]
    assert evaluation == generator.EXPECTED_EVALUATION_BOUNDARY
    for key in generator.EVALUATION_KEYS:
        assert evaluation[key] == {"evaluable": False, "result": None}
    assert evaluation["vacuous_pass_allowed"] is False


def test_every_runtime_boundary_is_not_executed_with_exact_integer_zero() -> None:
    execution = _plan()["execution_boundary"]
    assert execution == generator.EXPECTED_EXECUTION_BOUNDARY
    for key in generator.EXECUTION_STATUS_KEYS:
        assert execution[key] == "NOT_EXECUTED"
    assert tuple(execution["action_counts"]) == generator.ACTION_COUNT_KEYS
    assert all(
        type(value) is int and value == 0
        for value in execution["action_counts"].values()
    )
    assert execution["external_actions"] == []


def test_diagnostics_and_formal_evidence_remain_empty_or_unexecuted() -> None:
    assert _plan()["diagnostic_boundary"] == generator.EXPECTED_DIAGNOSTIC_BOUNDARY
    assert _plan()["verification_boundary"] == generator.EXPECTED_VERIFICATION_BOUNDARY


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
            "httpx",
            "os",
            "requests",
            "socket",
            "sqlalchemy",
            "subprocess",
            "urllib",
        }
    )

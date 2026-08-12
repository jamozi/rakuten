"""Source projections and closed-boundary tests for ST-0902."""

from __future__ import annotations

import ast
import json
from typing import Any

import yaml

from scripts import build_st0902_final_approval_reference_plan as generator


def _plan() -> dict[str, Any]:
    return generator.reference_plan(generator.load_contract())


def test_document_and_pro_assistance_are_strictly_non_authoritative() -> None:
    plan = _plan()

    assert tuple(plan) == generator.PLAN_KEYS
    assert plan["document"] == generator.EXPECTED_DOCUMENT
    assert plan["pro_assistance"] == {
        "status": "PRO_UNAVAILABLE",
        "authority": "NONE",
        "proposal_captured": False,
        "content_used": False,
    }


def test_story_and_all_fr009_trace_variants_are_projected_without_resolution() -> None:
    projection = _plan()["contract_projection"]

    assert projection["story"] == {
        "id": "ST-0902",
        "objective": "全Gate/hashを束ねる承認",
        "depends_on": ["ST-0901", "ST-0605", "ST-0805"],
        "requirement_ids": ["FR-009"],
        "deliverables": ["approval command"],
        "acceptance_criteria": [
            "self approval separation",
            "blocking finding rejects",
        ],
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "verification_status": "NOT_EXECUTED",
    }
    assert projection["trace_variants"] == {
        "story_test_suites": ["TST-012", "TST-021"],
        "master_fr009_test_suites": [
            "TST-011",
            "TST-012",
            "TST-020",
            "TST-021",
        ],
        "acceptance_fr009_test_suites": ["TST-012", "TST-021", "TST-022"],
        "traceability_status": "DIVERGENT_RECORDED_NOT_RESOLVED",
    }


def test_pubadm_operations_and_api_shapes_are_exact_contract_text_only() -> None:
    projection = _plan()["contract_projection"]
    approve = projection["pubadm_005"]
    revoke = projection["pubadm_006"]

    assert approve["method"] == "POST"
    assert approve["path"] == "/api/v1/admin/approvals"
    assert approve["operation_id"] == "PUBADM-005"
    assert approve["scopes"] == ["publishing:approval:decide"]
    assert approve["request_schema"] == "ApprovalRequest"
    assert approve["response_schema"] == "Approval"
    assert approve["idempotency_required"] is True
    assert approve["audit_action"] == "approval_record"
    assert revoke["path"] == "/api/v1/admin/approvals/{id}/revoke"
    assert revoke["operation_id"] == "PUBADM-006"
    assert revoke["scopes"] == ["publishing:approval:revoke"]
    assert revoke["audit_action"] == "approval_revoke"

    api = projection["approval_api"]
    assert api["request"]["additional_properties"] is False
    assert api["request"]["decisions"] == ["APPROVED", "REJECTED"]
    assert api["request"]["approval_types"] == [
        "EDITORIAL",
        "COMPLIANCE",
        "FINAL",
    ]
    assert api["response"]["approved_by_principal_id_exposed"] is False
    assert api["response"]["revoked_by_principal_id_exposed"] is False


def test_database_guard_and_event_limits_are_explicit() -> None:
    projection = _plan()["contract_projection"]
    database = projection["approval_database"]
    guard = database["final_approved_guard"]

    assert database["write_pattern"] == "LIFECYCLE"
    assert database["classification"] == "RESTRICTED"
    assert database["approval_types"] == ["EDITORIAL", "FACT", "COMPLIANCE", "FINAL"]
    assert database["decisions"] == ["APPROVED", "REJECTED", "REVOKED"]
    assert guard["applies_to"] == "FINAL_APPROVED_ONLY"
    assert guard["other_decision_outcome"] == "RETURN_NEW"
    assert guard["requires_active_user"] is True
    assert guard["blocking_query_status"] == "OPEN_ONLY"
    for missing in (
        "role_scope_mfa_step_up_sod_self_check",
        "effective_review_check",
        "full_gate_hash_manifest_check",
        "authoritative_claim_coverage_check",
        "waiver_truth_check",
    ):
        assert guard[missing] is False

    events = projection["approval_events"]
    assert events["granted"]["event_type"] == ("jp.raos.publishing.approval_granted.v1")
    assert events["revoked"]["event_type"] == ("jp.raos.publishing.approval_revoked.v1")
    assert events["rejected_event_contract"] == "ABSENT"
    assert events["actor_and_gate_hash_binding"] == "ABSENT"


def test_security_conflict_and_all_hard_gates_remain_separate() -> None:
    plan = _plan()
    security = plan["contract_projection"]["security_projection"]

    assert security["final_approve_role"] == {
        "allowed_roles": ["MANAGING_EDITOR"],
        "mfa_required": True,
        "step_up_required": False,
        "separation_of_duties": True,
        "implementation_status": "NOT_STARTED",
        "runtime_verification": "NOT_EXECUTED",
    }
    assert security["security_and_api_require_step_up"] is True
    assert security["step_up_contract_status"] == "CONFLICTING_SOURCES"
    assert plan["hard_gates"] == generator.EXPECTED_HARD_GATES
    assert [gate["topic"] for gate in plan["hard_gates"]] == [
        "identity_and_active_human_mapping",
        "final_approve_role_and_resource_scope",
        "mfa_claim_mapping",
        "step_up_conflict_and_freshness",
        "separation_of_duties_self_comparator_and_solo_exception",
        "effective_st0901_review_decision",
        "checklist_and_preapproval_gate_hash_manifest",
        "finding_and_waiver_truth",
        "quality_source_policy_evidence_and_freshness",
        "idempotency_audit_unit_of_work_transaction_and_outbox",
        "approval_revocation_supersession_effectiveness_and_publication",
    ]
    assert all(
        gate["resolution_required"] == "OWNER_APPROVED_DESIGN_HANDOFF_V1"
        for gate in plan["hard_gates"]
    )


def test_records_are_empty_and_empty_rejection_is_not_zero_rejected() -> None:
    records = _plan()["record_boundary"]

    assert records == generator.EXPECTED_RECORD_DEFAULTS
    assert records["approval"]["authority"] == "ABSENT"
    assert records["rejection"]["authority"] == "ABSENT"
    assert records["rejection"]["records"] == []
    assert records["rejection"]["empty_records_interpretation"] == (
        "NO_COMMAND_OR_EVIDENCE_NOT_ZERO_REJECTED"
    )
    assert records["revocation"]["records"] == []
    assert records["events"]["approval_granted"] == []
    assert records["events"]["approval_revoked"] == []
    assert records["audits"]["records"] == []
    assert records["idempotency"]["entries"] == []


def test_execution_and_verification_claims_remain_closed() -> None:
    plan = _plan()
    execution = plan["execution_boundary"]
    verification = plan["verification_boundary"]

    assert execution["runtime_reader"] == "NOT_IMPLEMENTED"
    for name in (
        "network",
        "filesystem_runtime",
        "clock",
        "database",
        "api",
        "job",
        "event",
        "audit",
        "idempotency",
        "approval",
        "rejection",
        "revocation",
        "publication",
    ):
        assert execution[name] == "NOT_EXECUTED"
    assert execution["external_actions"] == []
    assert execution["action_counts"]["rejection_record"] is None
    assert execution["rejection_count_interpretation"] == (
        "NOT_EVALUATED_NO_COMMAND_OR_EVIDENCE"
    )
    assert all(
        value == 0
        for name, value in execution["action_counts"].items()
        if name != "rejection_record"
    )
    for name in (
        "local_reference_checks",
        "formal_tst_011",
        "formal_tst_012",
        "formal_tst_020",
        "formal_tst_021",
        "formal_tst_022",
        "live",
        "staging",
        "release",
        "production",
    ):
        assert verification[name] == "NOT_EXECUTED"
    assert verification["story_acceptance"] is False
    assert verification["readiness"] == "NOT_READY"
    assert verification["production_eligible"] is False


def test_authority_hashes_are_exact_and_installed_json_matches_projection() -> None:
    plan = _plan()
    for row in plan["authority"]["sources"]:
        relative = row["uri"].removeprefix("repo://")
        assert (
            generator._sha256((generator.REPO_ROOT / relative).read_bytes())
            == (row["sha256"])
        )
    for dependency in plan["dependencies"]:
        for row in dependency["artifacts"]:
            relative = row["uri"].removeprefix("repo://")
            assert (
                generator._sha256((generator.REPO_ROOT / relative).read_bytes())
                == row["sha256"]
            )

    installed = json.loads(
        (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    )
    assert installed == plan


def test_exact_new_file_inventory_and_no_runtime_surface() -> None:
    root = generator.REPO_ROOT
    expected = {
        generator.CONTRACT_PATH,
        generator.GENERATOR_PATH,
        generator.REFERENCE_PLAN_PATH,
        generator.MANIFEST_PATH,
        generator.README_PATH,
        *generator.TEST_PATHS,
    }
    actual = {
        path.relative_to(root)
        for parent in (root / "changes/st-0902", root / "tests/st0902")
        for path in parent.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    actual.add(generator.GENERATOR_PATH)
    assert actual == expected
    assert (
        _plan()["implementation_boundary"] == generator.EXPECTED_IMPLEMENTATION_BOUNDARY
    )

    tree = ast.parse((root / generator.GENERATOR_PATH).read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    assert imports.isdisjoint(
        {
            "datetime",
            "httpx",
            "requests",
            "socket",
            "sqlite3",
            "subprocess",
            "time",
            "urllib",
        }
    )


def test_structured_artifacts_contain_no_private_pro_run_or_diagnostics() -> None:
    contract = yaml.safe_load(
        (generator.REPO_ROOT / generator.CONTRACT_PATH).read_bytes()
    )
    plan = json.loads(
        (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    )
    manifest = yaml.safe_load(
        (generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes()
    )
    forbidden_keys = {
        "run_id",
        "pro_run_id",
        "reason_code",
        "diagnostic_code",
        "diagnostic_detail_code",
        "diagnostic_context_code",
        "diagnostic_context_detail_code",
        "diagnostic_context_shape_code",
        "diagnostic_fallback_code",
        "diagnostic_fallback_entry_code",
        "proposal",
        "response_content",
    }

    def visit(value: object) -> None:
        if isinstance(value, dict):
            assert forbidden_keys.isdisjoint(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for artifact in (contract, plan, manifest):
        visit(artifact)

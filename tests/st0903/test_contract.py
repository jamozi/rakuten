"""Contract and authority-boundary tests for the ST-0903 reference plan."""

from __future__ import annotations

from typing import Any

from scripts import build_st0903_publication_snapshot_reference_plan as generator


def _plan() -> dict[str, Any]:
    contract = generator.load_contract()
    return generator.reference_plan(contract)


def test_document_is_strictly_non_executable_and_non_authoritative() -> None:
    plan = _plan()
    document = plan["document"]

    assert document["classification"] == (
        "SOURCE_DERIVED_NONEXECUTABLE_PUBLICATION_SNAPSHOT_REFERENCE_PLAN"
    )
    assert document["executable"] is False
    assert document["interface_only"] is True
    assert document["snapshot_builder_authorized"] is False
    assert document["runtime_builder_authorized"] is False
    assert document["approval_authority"] is False
    assert document["publication_permitted"] is False
    assert document["story_acceptance"] is False
    assert document["readiness"] == "NOT_READY"


def test_pro_record_contains_only_closed_unavailable_state() -> None:
    assert _plan()["pro_assistance"] == {
        "status": "PRO_UNAVAILABLE",
        "authority": "NONE",
        "proposal_captured": False,
        "content_used": False,
    }


def test_story_requirement_and_all_trace_variants_are_preserved() -> None:
    projection = _plan()["contract_projection"]
    story = projection["story"]
    traces = projection["trace_variants"]

    assert story["id"] == "ST-0903"
    assert story["depends_on"] == ["ST-0902", "ST-0807", "ST-0808"]
    assert story["requirement_ids"] == ["FR-010"]
    assert story["test_suites"] == ["TST-014", "TST-021"]
    assert projection["requirement"] == {
        "id": "FR-010",
        "level": "MUST",
        "statement": "support_cms_draft_publish_update_stop_and_rollback",
    }
    assert traces["story_test_suites"] == ["TST-014", "TST-021"]
    assert traces["acceptance_test_suites"] == ["TST-021", "TST-022"]
    assert len(traces["master_test_suites"]) == 12
    assert traces["traceability_status"] == "DIVERGENT_RECORDED_NOT_RESOLVED"


def test_manifest_snapshot_and_database_surfaces_remain_distinct() -> None:
    projection = _plan()["contract_projection"]
    content = projection["publication_content_manifest_schema"]
    snapshot = projection["publication_snapshot_schema"]
    database = projection["publication_snapshot_database"]
    reconciliation = projection["surface_reconciliation"]

    assert len(content["required"]) == 13
    assert content["additional_properties"] is False
    assert len(snapshot["required"]) == 15
    assert snapshot["snapshot_digest_is_required_inside_surface"] is True
    assert snapshot["canonicalization_or_self_exclusion_defined"] is False
    assert snapshot["seo_metadata_additional_properties"] is True
    assert snapshot["input_hash_names_allowlisted"] is False
    assert database["write_pattern"] == "APPEND_ONLY"
    assert database["mutation_guard"] is True
    assert database["classification"] == "CONFIDENTIAL"
    assert len(database["columns"]) == 22
    assert reconciliation == {
        "content_manifest_vs_snapshot": "UNRESOLVED",
        "snapshot_vs_database_manifest": "UNRESOLVED",
        "artifact_bytes_surface": "UNRESOLVED",
        "precedence_selected": False,
    }


def test_job_event_artifact_storage_and_public_surfaces_are_not_connected() -> None:
    projection = _plan()["contract_projection"]
    job = projection["build_snapshot_job_catalog"]
    payload = projection["build_snapshot_job_schema"]
    event = projection["snapshot_built_event_schema"]
    storage = projection["local_storage_boundary"]
    public = projection["public_isolation"]

    assert job["job_type"] == "publishing.build_snapshot.v1"
    assert job["idempotency_basis"] != payload["payload_required"]
    assert payload["catalog_basis_vs_payload_reconciled"] is False
    assert event["event_type"] == "jp.raos.publishing.snapshot_built.v1"
    assert storage["bucket_name"] == "raos-raw"
    assert storage["publication_bucket_or_key_contract"] == "ABSENT"
    assert storage["retention_period"] == "UNSET_HUMAN_DECISION_REQUIRED"
    assert public["snapshot_classification"] == "CONFIDENTIAL"
    assert public["public_role_schema_usage"] == ["readmodel"]
    assert public["exact_snapshot_to_public_allowlist"] == "NOT_DEFINED"


def test_all_hard_gates_fail_closed_and_require_a_new_handoff_for_builders() -> None:
    plan = _plan()
    gates = plan["hard_gates"]
    boundary = plan["implementation_boundary"]

    assert len(gates) == 10
    assert all(
        gate["safe_default"].startswith(("NO_", "KEEP_", "REFERENCE_"))
        for gate in gates
    )
    assert boundary["executable_builder_requires"] == "OWNER_APPROVED_DESIGN_HANDOFF_V1"
    assert boundary["runtime_builder_requires"] == "OWNER_APPROVED_DESIGN_HANDOFF_V1"
    for key in (
        "runtime_modules",
        "domain_modules",
        "application_modules",
        "ports",
        "adapters",
        "database_changes",
        "storage_changes",
        "api_changes",
        "job_changes",
        "event_changes",
        "status_changes",
        "generated_binding_changes",
    ):
        assert boundary[key] == []


def test_all_records_are_empty_without_zero_valid_snapshot_claim() -> None:
    records = _plan()["record_boundary"]

    assert set(records) == {
        "manifests",
        "snapshots",
        "hashes",
        "version_links",
        "artifacts",
        "jobs",
        "events",
        "audits",
        "approvals",
        "publications",
    }
    assert all(value["status"] == "NOT_EVALUATED" for value in records.values())
    assert all(value["records"] == [] for value in records.values())
    assert records["snapshots"]["empty_records_interpretation"] == (
        "NO_BUILD_OR_EVIDENCE_NOT_ZERO_VALID_SNAPSHOTS"
    )


def test_execution_and_verification_claims_remain_closed() -> None:
    plan = _plan()
    execution = plan["execution_boundary"]
    verification = plan["verification_boundary"]

    assert execution["runtime_reader"] == "NOT_IMPLEMENTED"
    assert execution["pure_snapshot_builder"] == "NOT_IMPLEMENTED"
    assert execution["runtime_snapshot_builder"] == "NOT_IMPLEMENTED"
    assert execution["external_actions"] == []
    assert all(
        value == "NOT_EXECUTED"
        for key, value in execution.items()
        if key
        not in {
            "runtime_reader",
            "pure_snapshot_builder",
            "runtime_snapshot_builder",
            "external_actions",
        }
    )
    assert verification["formal_tst_014"] == "NOT_EXECUTED"
    assert verification["formal_tst_021"] == "NOT_EXECUTED"
    assert verification["story_acceptance"] is False
    assert verification["readiness"] == "NOT_READY"
    assert verification["effective_canonical_status"] == "UNCHANGED"

"""Synthetic validator examples only: no real review or owner attestation."""

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import hashlib
import json

import pytest

from raos.application.editorial import verified_incremental_audit_v1 as audit
from raos.application.editorial.local_scratch_restore_v1 import (
    verify_scratch_restoration,
)
from tests.verified_incremental_v1.test_restore import (
    snapshot as synthetic_snapshot,
    scratch_prepared,
    scratch_readback,
)


NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
MANIFEST = "a" * 64
IMPLEMENTERS = ("synthetic-implementer",)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


BACKUP_SNAPSHOT, BACKUP_SLUGS = synthetic_snapshot()
BACKUP_RAW = audit.canonical_json_bytes(BACKUP_SNAPSHOT).rstrip(b"\n")
INPUTS = {"source": "b" * 64, "live-snapshot": digest(BACKUP_RAW)}


def restoration_artifacts():
    expected = scratch_prepared()
    readback = scratch_readback(expected)
    receipt = verify_scratch_restoration(expected, readback)
    receipt["verified_at"] = "2026-09-05T09:00:00.123456+00:00"
    return {
        "synthetic-backup": BACKUP_RAW,
        "synthetic-restoration": audit.canonical_json_bytes(receipt),
        "synthetic-readback": audit.canonical_json_bytes(readback),
    }


def scope() -> audit.IncrementalAuditScopeV1:
    return audit.IncrementalAuditScopeV1(
        selected_article_ids=("a01",),
        existing_article_ids=("a01", "a02"),
        rendered_article_ids=("a01", "a02"),
        shared_changes=False,
        claim_ids_by_article={"a01": ("claim-one",)},
        retained_product_ids=("p01",),
        affiliate_cta_ids=("cta-one",),
        product_image_ids=("image-one",),
    )


def synthetic_pair(
    current_scope: audit.IncrementalAuditScopeV1 | None = None,
    contact_state: str = "OWNER_CONFIRMED",
) -> tuple[dict[str, object], dict[str, bytes]]:
    current_scope = current_scope or scope()
    report = audit.incomplete_audit_template_v1(
        manifest_sha256=MANIFEST,
        expected_artifact_hashes=INPUTS,
        implementation_execution_ids=IMPLEMENTERS,
        scope=current_scope,
    )
    report.update(
        evaluated_at="2026-09-05T12:00:00Z", expires_at="2026-09-05T12:10:00Z"
    )
    rounds = []
    artifacts = restoration_artifacts()
    for index in (1, 2):
        rid = f"synthetic-round-{index}"
        execution = f"synthetic-review-execution-{index}"
        captured = f"2026-09-05T11:{56 + index}:10Z"
        attachment = f"synthetic-observations-{index}"
        artifacts[attachment] = f"Synthetic test-only observation {index}\n".encode()
        surfaces = []
        for surface_id in audit.SURFACES:
            row = {
                "surface_id": surface_id,
                "status": "PASS",
                "execution_status": "EXECUTED",
                "reason_code": None,
                "evidence_id": f"{rid}.{surface_id}",
            }
            if surface_id == audit.READER_SURFACE:
                row.update(
                    status="DEFERRED",
                    execution_status="NOT_EXECUTED",
                    reason_code="REAL_READERS_NOT_EXECUTED",
                    evidence_id=None,
                )
            elif (
                surface_id == audit.CLOUD_SURFACE
                and not current_scope.smart_device_product_ids
            ) or (
                surface_id == audit.DISPOSAL_SURFACE
                and not current_scope.disposal_product_ids
            ):
                row.update(
                    status="NOT_APPLICABLE",
                    execution_status="NOT_EXECUTED",
                    reason_code="NO_APPLICABLE_PRODUCTS",
                    evidence_id=None,
                )
            else:
                proof = audit.incomplete_evidence_template_v1(
                    surface_id=surface_id,
                    manifest_sha256=MANIFEST,
                    expected_artifact_hashes=INPUTS,
                    scope=current_scope,
                )
                checks: dict[str, object]
                if surface_id == "code":
                    checks = {
                        "commands": [
                            {
                                "command_id": command,
                                "exit_code": 0,
                                "output_artifact_id": attachment,
                            }
                            for command in (
                                "generate",
                                "check",
                                "focused",
                                "fast",
                                "final",
                            )
                        ]
                    }
                elif surface_id == audit.CONTACT_SURFACE:
                    checks = {
                        "state": contact_state,
                        "address": audit.CONTACT_ADDRESS,
                        "owner_id": "synthetic-owner",
                        "confirmation_artifact_id": attachment,
                        "delivery_artifact_id": attachment
                        if contact_state == "TESTED"
                        else None,
                    }
                elif surface_id == audit.BACKUP_SURFACE:
                    checks = {
                        "backup_available": True,
                        "restore_rehearsal_passed": True,
                        "restored_hashes_match": True,
                        "rollback_owner_id": "synthetic-owner",
                        "backup_artifact_id": "synthetic-backup",
                        "restoration_artifact_id": "synthetic-restoration",
                        "restoration_readback_artifact_id": "synthetic-readback",
                    }
                elif surface_id == audit.OPERATIONS_SURFACE:
                    checks = {
                        "immediate_readback_plan_bound": True,
                        "incident_owner_id": "synthetic-owner",
                        "rollback_owner_id": "synthetic-owner",
                    }
                elif surface_id == "freshness_maintenance_ownership":
                    checks = {
                        "recheck_owner_id": "synthetic-owner",
                        "expiry_enforced": True,
                    }
                else:
                    checks = {
                        "completed_checks": list(audit.REQUIRED_CHECKS[surface_id]),
                        "status": "PASS",
                    }
                proof.update(
                    result="PASS",
                    round_id=rid,
                    execution_id=execution,
                    captured_at=captured,
                    observations=["Synthetic validator test; not a live review."],
                    attachments=list(restoration_artifacts())
                    if surface_id == audit.BACKUP_SURFACE
                    else [attachment],
                    checks=checks,
                )
                artifacts[str(row["evidence_id"])] = audit.canonical_json_bytes(proof)
            surfaces.append(row)
        rounds.append(
            {
                "round_id": rid,
                "reviewer_id": f"synthetic-reviewer-{index}",
                "execution_id": execution,
                "started_at": f"2026-09-05T11:{56 + index}:00Z",
                "completed_at": f"2026-09-05T11:{56 + index}:30Z",
                "manifest_sha256": MANIFEST,
                "scope_sha256": report["scope_sha256"],
                "artifact_hashes": INPUTS,
                "findings": [],
                "surfaces": surfaces,
            }
        )
    report["rounds"] = rounds
    report["evidence_artifact_hashes"] = {
        key: digest(raw) for key, raw in artifacts.items()
    }
    if contact_state == "OWNER_CONFIRMED":
        report["deferred_checks"].append(
            {
                "check_id": "automated_contact_delivery",
                "execution_status": "NOT_EXECUTED",
                "publication_blocking": False,
            }
        )
    return report, artifacts


def validate(report, artifacts, current_scope=None, now=NOW):
    return audit.validate_verified_incremental_audit_v1(
        report,
        manifest_sha256=MANIFEST,
        expected_artifact_hashes=INPUTS,
        evidence_artifacts=artifacts,
        expected_backup_snapshot=BACKUP_SNAPSHOT,
        expected_backup_article_slugs=BACKUP_SLUGS,
        implementation_execution_ids=IMPLEMENTERS,
        scope=current_scope or scope(),
        now=now,
    )


def mutate_proof(report, artifacts, surface, mutation, *, round_index=0):
    row = next(
        row
        for row in report["rounds"][round_index]["surfaces"]
        if row["surface_id"] == surface
    )
    key = row["evidence_id"]
    proof = json.loads(artifacts[key])
    mutation(proof)
    artifacts[key] = audit.canonical_json_bytes(proof)
    report["evidence_artifact_hashes"][key] = digest(artifacts[key])


@pytest.mark.parametrize("contact_state", ["OWNER_CONFIRMED", "TESTED"])
def test_valid_profile_is_not_publication_or_full_audit_authority(contact_state):
    report, artifacts = synthetic_pair(contact_state=contact_state)
    result = validate(report, artifacts).to_document()
    assert result["contact_state"] == contact_state
    assert result["consecutive_clean_rounds"] == 2
    assert result["publication_authority"] is False
    assert result["new_page_approval_authority"] is False
    assert result["owner_approval_required"] is True
    assert result["reviewer_attestation_verified"] is False
    assert result["execution_identity_authentication"] == "OWNER_REVIEW_REQUIRED"
    assert result["production_readback_state"] == "REQUIRED_NOT_EVALUATED"
    assert result["full_portfolio_audit_completed"] is False
    assert json.loads(audit.canonical_json_bytes(result)) == result


@pytest.mark.parametrize(
    "field,value",
    [
        ("publication_profile", "full"),
        ("link_mode", "measured-admin"),
        ("publication_authority", True),
        ("owner_approval_required", False),
        ("reviewer_attestation_verified", True),
        ("new_page_approval_authority", True),
        ("execution_identity_authentication", "SIGNED"),
        ("publication_authority", 0),
        ("manifest_sha256", "d" * 64),
        ("scope_sha256", "e" * 64),
        ("artifact_hashes", {"source": "d" * 64}),
        ("implementation_execution_ids", ["different-author"]),
        ("expires_at", "2026-09-06T12:00:01Z"),
        ("expires_at", "2026-09-05T12:00:00Z"),
        ("evaluated_at", "2026-09-05T12:00:01Z"),
        ("evaluated_at", "2026-02-30T00:00:00Z"),
        ("rounds", []),
    ],
)
def test_profile_authority_scope_and_time_tampering_rejected(field, value):
    report, artifacts = synthetic_pair()
    report[field] = value
    with pytest.raises(audit.IncrementalAuditFailure):
        validate(report, artifacts)


def test_unknown_approval_field_cannot_be_substituted():
    report, artifacts = synthetic_pair()
    report["wp_admin_approval"] = "approved"
    with pytest.raises(audit.IncrementalAuditFailure, match="FIELDS"):
        validate(report, artifacts)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda rounds: rounds[0].update(execution_id=IMPLEMENTERS[0]),
        lambda rounds: rounds[1].update(execution_id=rounds[0]["execution_id"]),
        lambda rounds: rounds[1].update(reviewer_id=rounds[0]["reviewer_id"]),
        lambda rounds: rounds[1].update(round_id=rounds[0]["round_id"]),
        lambda rounds: rounds[1].update(started_at=rounds[0]["started_at"]),
        lambda rounds: rounds[0].update(findings=["unresolved"]),
        lambda rounds: rounds[1].update(manifest_sha256="e" * 64),
        lambda rounds: rounds[1]["surfaces"].pop(),
        lambda rounds: rounds[1]["surfaces"][0].update(status="NOT_APPLICABLE"),
    ],
)
def test_incomplete_dependent_or_mismatched_round_rejected(mutation):
    report, artifacts = synthetic_pair()
    mutation(report["rounds"])
    with pytest.raises(audit.IncrementalAuditFailure):
        validate(report, artifacts)


def test_real_reader_study_cannot_be_claimed_by_codex():
    report, artifacts = synthetic_pair()
    row = next(
        row
        for row in report["rounds"][0]["surfaces"]
        if row["surface_id"] == audit.READER_SURFACE
    )
    row.update(status="PASS", execution_status="EXECUTED")
    with pytest.raises(audit.IncrementalAuditFailure, match="EXEMPTION"):
        validate(report, artifacts)


def test_applicable_product_surfaces_must_execute():
    current_scope = replace(
        scope(), smart_device_product_ids=("p01",), disposal_product_ids=("p01",)
    )
    report, artifacts = synthetic_pair(current_scope)
    validate(report, artifacts, current_scope)
    cloud = next(
        row
        for row in report["rounds"][0]["surfaces"]
        if row["surface_id"] == audit.CLOUD_SURFACE
    )
    cloud.update(
        status="NOT_APPLICABLE",
        execution_status="NOT_EXECUTED",
        evidence_id=None,
        reason_code="NO_APPLICABLE_PRODUCTS",
    )
    with pytest.raises(audit.IncrementalAuditFailure, match="MANDATORY"):
        validate(report, artifacts, current_scope)


@pytest.mark.parametrize(
    "changed",
    [
        {"selected_article_ids": ("new-post",)},
        {"rendered_article_ids": ("unlisted-article",)},
        {"claim_ids_by_article": {"a01": ()}},
        {"claim_ids_by_article": {}},
        {"smart_device_product_ids": ("unselected-product",)},
        {"disposal_product_ids": ("unselected-product",)},
        {"retained_product_ids": ()},
        {"selected_article_ids": ("a01", "a01")},
        {"shared_changes": 1},
    ],
)
def test_blank_article_new_id_or_unrendered_shared_surface_cannot_pass(changed):
    with pytest.raises(audit.IncrementalAuditFailure):
        replace(scope(), **changed).to_document()


def test_article_only_release_can_render_selected_subset():
    current_scope = replace(
        scope(), shared_changes=False, rendered_article_ids=("a01",)
    )
    report, artifacts = synthetic_pair(current_scope)
    validate(report, artifacts, current_scope)


@pytest.mark.parametrize(
    "surface,mutation",
    [
        ("code", lambda proof: proof["checks"]["commands"][0].update(exit_code=1)),
        ("code", lambda proof: proof["checks"]["commands"].pop()),
        ("code", lambda proof: proof["checks"]["commands"][0].update(exit_code=False)),
        (
            "code",
            lambda proof: proof["checks"]["commands"][0].update(
                output_artifact_id="missing"
            ),
        ),
        ("editorial_sources", lambda proof: proof["checks"].update(status="FAIL")),
        (
            "editorial_sources",
            lambda proof: proof["checks"].update(completed_checks=["looked_at_title"]),
        ),
        ("editorial_sources", lambda proof: proof.update(findings=["unknown claim"])),
        ("editorial_sources", lambda proof: proof.update(observations=[])),
        ("editorial_sources", lambda proof: proof.update(manifest_sha256="f" * 64)),
        (
            "editorial_sources",
            lambda proof: proof.update(captured_at="2026-09-05T11:56:00Z"),
        ),
        (
            "editorial_sources",
            lambda proof: proof.update(attachments=["missing-artifact"]),
        ),
        (audit.CONTACT_SURFACE, lambda proof: proof["checks"].update(state="ASSUMED")),
        (audit.CONTACT_SURFACE, lambda proof: proof["checks"].update(state="TESTED")),
        (audit.CONTACT_SURFACE, lambda proof: proof["checks"].update(owner_id="")),
        (
            audit.BACKUP_SURFACE,
            lambda proof: proof["checks"].update(backup_available=False),
        ),
        (
            audit.BACKUP_SURFACE,
            lambda proof: proof["checks"].update(restore_rehearsal_passed=False),
        ),
        (
            audit.BACKUP_SURFACE,
            lambda proof: proof["checks"].update(restored_hashes_match=False),
        ),
        (
            audit.OPERATIONS_SURFACE,
            lambda proof: proof["checks"].update(immediate_readback_plan_bound=False),
        ),
        (
            "freshness_maintenance_ownership",
            lambda proof: proof["checks"].update(expiry_enforced=False),
        ),
    ],
)
def test_rehashing_failed_or_unsubstantiated_proof_does_not_make_it_valid(
    surface, mutation
):
    report, artifacts = synthetic_pair()
    mutate_proof(report, artifacts, surface, mutation)
    with pytest.raises(audit.IncrementalAuditFailure):
        validate(report, artifacts)


def test_bytes_are_rehashed_not_just_report_digests():
    report, artifacts = synthetic_pair()
    artifacts["synthetic-observations-1"] += b"tamper"
    with pytest.raises(audit.IncrementalAuditFailure, match="TAMPERED"):
        validate(report, artifacts)


def test_unused_extra_artifact_rejected():
    report, artifacts = synthetic_pair()
    artifacts["extra"] = b"not reviewed"
    report["evidence_artifact_hashes"]["extra"] = digest(artifacts["extra"])
    with pytest.raises(audit.IncrementalAuditFailure, match="UNUSED"):
        validate(report, artifacts)


def test_per_surface_expiry_cannot_be_extended_to_report_limit():
    report, artifacts = synthetic_pair()
    report["expires_at"] = "2026-09-06T12:00:00Z"
    with pytest.raises(audit.IncrementalAuditFailure, match="EVIDENCE_EXPIRY"):
        validate(report, artifacts)


def test_two_real_review_windows_may_exceed_fifteen_minutes_without_retimestamping_evidence():
    report, artifacts = synthetic_pair()
    report["rounds"][0]["started_at"] = "2026-09-05T10:00:00Z"
    report["rounds"][0]["completed_at"] = "2026-09-05T10:45:00Z"
    report["rounds"][1]["started_at"] = "2026-09-05T11:00:00Z"
    report["rounds"][1]["completed_at"] = "2026-09-05T11:45:00Z"
    for round_index, captured in enumerate(
        ("2026-09-05T10:30:00Z", "2026-09-05T11:30:00Z")
    ):
        for surface in report["rounds"][round_index]["surfaces"]:
            if surface["evidence_id"] is not None:
                mutate_proof(
                    report,
                    artifacts,
                    surface["surface_id"],
                    lambda proof: proof.update(captured_at=captured),
                    round_index=round_index,
                )
    report["expires_at"] = "2026-09-05T20:00:00Z"
    original_hashes = deepcopy(report["evidence_artifact_hashes"])
    binding = validate(report, artifacts)
    assert binding.expires_at == report["expires_at"]
    assert report["evidence_artifact_hashes"] == original_hashes


def test_stale_and_timezone_naive_now_rejected():
    report, artifacts = synthetic_pair()
    for now in (NOW + timedelta(minutes=10), NOW.replace(tzinfo=None)):
        with pytest.raises(audit.IncrementalAuditFailure):
            validate(report, artifacts, now=now)


def test_deferred_state_cannot_claim_execution_or_disappear():
    report, artifacts = synthetic_pair()
    report["deferred_checks"][0]["execution_status"] = "EXECUTED"
    with pytest.raises(audit.IncrementalAuditFailure, match="DEFERRED"):
        validate(report, artifacts)


def test_incomplete_template_confers_no_authority():
    report = audit.incomplete_audit_template_v1(
        manifest_sha256=MANIFEST,
        expected_artifact_hashes=INPUTS,
        implementation_execution_ids=IMPLEMENTERS,
        scope=scope(),
    )
    assert report["rounds"] == [] and report["publication_authority"] is False
    with pytest.raises(audit.IncrementalAuditFailure):
        validate(report, {})


def test_duplicate_json_keys_rejected_even_if_raw_hash_is_current():
    report, artifacts = synthetic_pair()
    key = report["rounds"][0]["surfaces"][0]["evidence_id"]
    artifacts[key] = b'{"result":"FAIL",' + artifacts[key][1:]
    report["evidence_artifact_hashes"][key] = digest(artifacts[key])
    with pytest.raises(audit.IncrementalAuditFailure):
        validate(report, artifacts)


def test_reused_round_one_proof_cannot_be_bound_to_round_two():
    report, artifacts = synthetic_pair()
    report["rounds"][1]["surfaces"][0]["evidence_id"] = report["rounds"][0]["surfaces"][
        0
    ]["evidence_id"]
    with pytest.raises(audit.IncrementalAuditFailure, match="REUSED"):
        validate(report, artifacts)


def test_validator_does_not_mutate_inputs():
    report, artifacts = synthetic_pair()
    prior_report, prior_artifacts = deepcopy(report), deepcopy(artifacts)
    validate(report, artifacts)
    assert report == prior_report and artifacts == prior_artifacts


def replay_backup(artifacts, *, expected_snapshot=BACKUP_SNAPSHOT):
    return audit.validate_scratch_backup_evidence_v1(
        backup_raw=artifacts["synthetic-backup"],
        restoration_raw=artifacts["synthetic-restoration"],
        readback_raw=artifacts["synthetic-readback"],
        expected_snapshot=expected_snapshot,
        expected_article_slugs=BACKUP_SLUGS,
        expected_backup_sha256=INPUTS["live-snapshot"],
        observed_at=NOW,
    )


def replace_attachment(report, artifacts, key, mutation):
    document = json.loads(artifacts[key])
    mutation(document)
    artifacts[key] = audit.canonical_json_bytes(document)
    report["evidence_artifact_hashes"][key] = digest(artifacts[key])


def test_backup_replay_binds_original_snapshot_exact_fourteen_ids_and_real_bytes():
    artifacts = restoration_artifacts()
    result = replay_backup(artifacts)
    assert result["source_snapshot_sha256"] == digest(BACKUP_RAW)
    assert result["backup_artifact_sha256"] == digest(BACKUP_RAW)
    assert result["restoration_artifact_sha256"] == digest(
        artifacts["synthetic-restoration"]
    )
    assert result["readback_artifact_sha256"] == digest(artifacts["synthetic-readback"])
    assert result["original_id_set"] == list(range(1, 15))
    assert result["verified_document_count"] == 14
    assert result["publication_authority"] is False
    assert result["shared_configuration_restored"] is False


def test_backup_file_hash_and_semantic_snapshot_hash_are_not_conflated():
    artifacts = restoration_artifacts()
    pretty = json.dumps(BACKUP_SNAPSHOT, indent=2).encode()
    result = audit.validate_scratch_backup_evidence_v1(
        backup_raw=pretty,
        restoration_raw=artifacts["synthetic-restoration"],
        readback_raw=artifacts["synthetic-readback"],
        expected_snapshot=BACKUP_SNAPSHOT,
        expected_article_slugs=BACKUP_SLUGS,
        expected_backup_sha256=digest(pretty),
        observed_at=NOW,
    )
    assert result["backup_artifact_sha256"] != result["source_snapshot_sha256"]
    assert result["source_snapshot_sha256"] == digest(BACKUP_RAW)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", "RAOS_WORDPRESS_LOCAL_RESTORE_RECEIPT_V1"),
        ("publication_profile", "verified-incremental"),
        ("status", "PREPARED_NOT_RESTORED"),
        ("source_snapshot_sha256", "e" * 64),
        ("source_preparation_sha256", "e" * 64),
        ("seed_sha256", "e" * 64),
        ("readback_sha256", "e" * 64),
        ("original_id_set", list(range(2, 16))),
        ("verified_document_count", 13),
        ("scratch_only", False),
        ("scratch_only", 1),
        ("publication_authority", True),
        ("publication_authority", 0),
        ("production_authority", True),
        ("current_preview_modified", True),
        ("not_restored", []),
        ("verified_at", "2026-09-05T12:01:00+00:00"),
        ("verified_at", "2026-09-05T09:00:00"),
    ],
)
def test_rehashed_false_receipt_cannot_claim_a_restore_pass(field, value):
    report, artifacts = synthetic_pair()
    replace_attachment(
        report,
        artifacts,
        "synthetic-restoration",
        lambda row: row.update({field: value}),
    )
    with pytest.raises(audit.IncrementalAuditFailure):
        validate(report, artifacts)


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", 99),
        ("id", True),
        ("slug", "another-article"),
        ("body_sha256", "d" * 64),
        ("content_sha256", "d" * 64),
        ("title_sha256", "d" * 64),
        ("excerpt_sha256", "d" * 64),
        ("taxonomy_ids", {"category": [6], "post_tag": []}),
        ("taxonomies", {}),
        ("dates", {}),
        ("media_ids", [50]),
    ],
)
def test_wrong_saved_field_cannot_pass_after_all_outer_hashes_are_recomputed(
    field, value
):
    report, artifacts = synthetic_pair()
    replace_attachment(
        report,
        artifacts,
        "synthetic-readback",
        lambda row: row["documents"]["article-0"].update({field: value}),
    )
    # A matching digest in a self-authored receipt still cannot replace replay.
    replace_attachment(
        report,
        artifacts,
        "synthetic-restoration",
        lambda row: row.update(readback_sha256=digest(artifacts["synthetic-readback"])),
    )
    with pytest.raises(
        audit.IncrementalAuditFailure, match="RESTORATION_REPLAY_FAILED"
    ):
        validate(report, artifacts)


def test_other_current_snapshot_cannot_reuse_an_old_successful_restore():
    changed = deepcopy(BACKUP_SNAPSHOT)
    changed["documents"][0]["content_sha256"] = "f" * 64
    with pytest.raises(audit.IncrementalAuditFailure, match="BACKUP_SNAPSHOT_MISMATCH"):
        replay_backup(restoration_artifacts(), expected_snapshot=changed)


def test_backup_bytes_must_be_the_reviewed_current_live_input():
    artifacts = restoration_artifacts()
    artifacts["synthetic-backup"] += b"\n"
    with pytest.raises(audit.IncrementalAuditFailure, match="BACKUP_INPUT_MISMATCH"):
        replay_backup(artifacts)


@pytest.mark.parametrize(
    "field", ["backup_artifact_id", "restoration_readback_artifact_id"]
)
def test_backup_restore_and_readback_must_be_distinct_attachments(field):
    report, artifacts = synthetic_pair()
    mutate_proof(
        report,
        artifacts,
        audit.BACKUP_SURFACE,
        lambda proof: proof["checks"].update({field: "synthetic-restoration"}),
    )
    with pytest.raises(audit.IncrementalAuditFailure, match="RESTORATION_UNVERIFIED"):
        validate(report, artifacts)


def test_boolean_only_old_backup_checks_no_longer_pass():
    report, artifacts = synthetic_pair()
    mutate_proof(
        report,
        artifacts,
        audit.BACKUP_SURFACE,
        lambda proof: proof["checks"].pop("restoration_readback_artifact_id"),
    )
    with pytest.raises(audit.IncrementalAuditFailure, match="FIELDS_INVALID"):
        validate(report, artifacts)


def test_shared_theme_or_configuration_cannot_pass_with_content_only_rehearsal():
    shared = replace(
        scope(), shared_changes=True, required_noncontent_rollback_targets=("theme",)
    )
    report, artifacts = synthetic_pair(shared)
    with pytest.raises(
        audit.IncrementalAuditFailure, match="SHARED_ROLLBACK_NOT_VERIFIED"
    ):
        validate(report, artifacts, shared)


def test_shared_policy_pages_are_covered_by_fourteen_document_rehearsal():
    policies_only = replace(scope(), shared_changes=True)
    report, artifacts = synthetic_pair(policies_only)
    validate(report, artifacts, policies_only)


@pytest.mark.parametrize("targets", [("theme", "theme"), ("unknown",), ("theme",)])
def test_noncontent_rollback_scope_cannot_disappear_or_claim_unknown_targets(targets):
    with pytest.raises(audit.IncrementalAuditFailure):
        replace(scope(), required_noncontent_rollback_targets=targets).to_document()


def test_shared_scope_still_requires_all_existing_articles_rendered():
    with pytest.raises(audit.IncrementalAuditFailure, match="SCOPE_INVALID"):
        replace(
            scope(), shared_changes=True, rendered_article_ids=("a01",)
        ).to_document()


@pytest.mark.parametrize(
    "key", ["synthetic-backup", "synthetic-restoration", "synthetic-readback"]
)
def test_backup_json_duplicate_keys_are_rejected(key):
    artifacts = restoration_artifacts()
    raw = artifacts[key]
    # Same value is still a duplicate, not a second interpretation to accept.
    first_key, first_value = next(iter(json.loads(raw).items()))
    duplicate = json.dumps({first_key: first_value}, ensure_ascii=False).encode()[:-1]
    artifacts[key] = duplicate + b"," + raw[1:]
    with pytest.raises(audit.IncrementalAuditFailure):
        audit.validate_scratch_backup_evidence_v1(
            backup_raw=artifacts["synthetic-backup"],
            restoration_raw=artifacts["synthetic-restoration"],
            readback_raw=artifacts["synthetic-readback"],
            expected_snapshot=BACKUP_SNAPSHOT,
            expected_article_slugs=BACKUP_SLUGS,
            expected_backup_sha256=digest(artifacts["synthetic-backup"]),
            observed_at=NOW,
        )

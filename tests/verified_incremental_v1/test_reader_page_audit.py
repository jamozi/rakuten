"""Synthetic V2 restoration and independent review evidence, never live audits."""

from copy import deepcopy
import json

import pytest

from raos.application.editorial import verified_incremental_audit_v1 as audit
from raos.application.editorial import verified_incremental_v1 as manifest
from tests.verified_incremental_audit_v1 import test_contract as legacy
from tests.verified_incremental_v1.test_reader_page_contract import page_scope

FIELDS = {
    "schema",
    "post_type",
    "id",
    "status",
    "title",
    "slug",
    "excerpt",
    "block_markup",
    "taxonomies",
    "media_ids",
}


def backup_fixture():
    snapshot = deepcopy(legacy.BACKUP_SNAPSHOT)
    snapshot["schema"] = "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V2"
    page = {
        "schema": "ContentDocumentV1",
        "id": 101,
        "post_type": "page",
        "status": "draft",
        "slug": "categories",
        "title": "Synthetic hub",
        "excerpt": "",
        "block_markup": "<p>Draft baseline</p>",
        "taxonomies": {},
        "media_ids": [],
    }
    page["content_sha256"] = manifest.digest(manifest.canonical(page).rstrip(b"\n"))
    snapshot["documents"].append(page)
    snapshot_hash = manifest.digest(manifest.canonical(snapshot).rstrip(b"\n"))
    readback = {
        "schema": "RAOS_WORDPRESS_READER_PAGE_RESTORE_READBACK_V2",
        "publication_profile": "local-scratch-restore-rehearsal",
        "publication_authority": False,
        "production_authority": False,
        "scratch_only": True,
        "temporary_environment": True,
        "environment_id": "12345678-012345abcdef",
        "site_url": "http://scratch.wordpress.invalid",
        "source_snapshot_sha256": snapshot_hash,
        "original_id_set": sorted(row["id"] for row in snapshot["documents"]),
        "documents": {
            row["slug"]: {key: row[key] for key in FIELDS | {"content_sha256"}}
            for row in snapshot["documents"]
        },
    }
    receipt = {
        "schema": "RAOS_WORDPRESS_READER_PAGE_RESTORE_RECEIPT_V2",
        "publication_profile": "local-scratch-restore-rehearsal",
        "publication_authority": False,
        "production_authority": False,
        "scratch_only": True,
        "temporary_environment": True,
        "environment_id": readback["environment_id"],
        "status": "SCRATCH_CONTENT_DOCUMENT_FIELDS_RESTORED",
        "source_snapshot_sha256": snapshot_hash,
        "readback_sha256": manifest.digest(manifest.canonical(readback)),
        "verified_document_count": 15,
        "original_id_set": readback["original_id_set"],
        "selected_page_slugs": ["categories"],
        "current_preview_modified": False,
        "production_writes": False,
        "incremental_preview_pass": False,
        "not_restored": [
            "revision_history",
            "author_identity",
            "dates",
            "post_meta",
            "theme",
            "plugins",
            "production_site_options",
        ],
        "verified_at": "2026-09-05T09:00:00Z",
    }
    return snapshot, receipt, readback


def validate_backup(snapshot, receipt, readback):
    raw = manifest.canonical(snapshot)
    return audit.validate_scratch_backup_evidence_v1(
        backup_raw=raw,
        restoration_raw=manifest.canonical(receipt),
        readback_raw=manifest.canonical(readback),
        expected_snapshot=snapshot,
        expected_article_slugs=legacy.BACKUP_SLUGS,
        expected_backup_sha256=manifest.digest(raw),
        observed_at=legacy.NOW,
        expected_page_slugs=frozenset({"categories"}),
    )



def test_privacy_only_restore_uses_unmodified_legacy_fourteen_page_snapshot():
    snapshot, receipt, readback = backup_fixture()
    snapshot = deepcopy(legacy.BACKUP_SNAPSHOT)
    snapshot_hash = manifest.digest(manifest.canonical(snapshot).rstrip(b"\n"))
    readback["source_snapshot_sha256"] = snapshot_hash
    readback["original_id_set"] = sorted(row["id"] for row in snapshot["documents"])
    readback["documents"] = {
        row["slug"]: {key: row[key] for key in FIELDS | {"content_sha256"}}
        for row in snapshot["documents"]
    }
    receipt["source_snapshot_sha256"] = snapshot_hash
    receipt["readback_sha256"] = manifest.digest(manifest.canonical(readback))
    receipt["verified_document_count"] = 14
    receipt["original_id_set"] = readback["original_id_set"]
    receipt["selected_page_slugs"] = ["privacy-policy"]
    raw = manifest.canonical(snapshot)
    arguments = dict(
        backup_raw=raw,
        restoration_raw=manifest.canonical(receipt),
        readback_raw=manifest.canonical(readback),
        expected_snapshot=snapshot,
        expected_article_slugs=legacy.BACKUP_SLUGS,
        expected_backup_sha256=manifest.digest(raw),
        observed_at=legacy.NOW,
    )
    result = audit.validate_scratch_backup_evidence_v1(
        **arguments, expected_page_slugs=frozenset({"privacy-policy"})
    )
    assert result["verified_document_count"] == 14
    assert result["selected_page_slugs"] == ["privacy-policy"]
    with pytest.raises(audit.IncrementalAuditFailure):
        audit.validate_scratch_backup_evidence_v1(
            **arguments, expected_page_slugs=frozenset({"categories"})
        )


def full_pair():
    scope = page_scope()
    report, artifacts = legacy.synthetic_pair(scope)
    snapshot, receipt, readback = backup_fixture()
    artifacts["synthetic-backup"] = manifest.canonical(snapshot)
    artifacts["synthetic-restoration"] = manifest.canonical(receipt)
    artifacts["synthetic-readback"] = manifest.canonical(readback)
    hashes = {
        **legacy.INPUTS,
        "live-snapshot": manifest.digest(artifacts["synthetic-backup"]),
    }
    report["artifact_hashes"] = hashes
    for row in report["rounds"]:
        row["artifact_hashes"] = hashes
        for surface in row["surfaces"]:
            key = surface["evidence_id"]
            if key:
                proof = json.loads(artifacts[key])
                proof["artifact_hashes"] = hashes
                artifacts[key] = manifest.canonical(proof)
    report["evidence_artifact_hashes"] = {
        key: manifest.digest(raw) for key, raw in artifacts.items()
    }
    return report, artifacts, snapshot, hashes


def validate_pair(report, artifacts, snapshot, hashes):
    return audit.validate_verified_incremental_audit_v1(
        report,
        manifest_sha256=legacy.MANIFEST,
        expected_artifact_hashes=hashes,
        evidence_artifacts=artifacts,
        expected_backup_snapshot=snapshot,
        expected_backup_article_slugs=legacy.BACKUP_SLUGS,
        implementation_execution_ids=legacy.IMPLEMENTERS,
        scope=page_scope(),
        now=legacy.NOW,
    )


def test_page_audit_cannot_accept_old_backup_that_omits_selected_draft():
    scope = page_scope()
    report, artifacts = legacy.synthetic_pair(scope)
    with pytest.raises(audit.IncrementalAuditFailure):
        legacy.validate(report, artifacts, scope)


def test_snapshot_bound_page_restore_preserves_draft_objects_and_all_ten_articles():
    snapshot, receipt, readback = backup_fixture()
    result = validate_backup(snapshot, receipt, readback)
    assert result["status"] == "SCRATCH_CONTENT_DOCUMENT_FIELDS_RESTORED"
    assert result["verified_document_count"] == 15
    assert result["selected_page_slugs"] == ["categories"]
    assert result["publication_authority"] is False


@pytest.mark.parametrize(
    "change",
    [
        "missing_article",
        "missing_page",
        "id",
        "boolean_id",
        "draft_promoted",
        "article_body",
        "page_body",
        "snapshot_drift",
        "hash_only",
        "receipt",
        "future",
        "environment",
        "privacy_draft",
        "local5",
    ],
)
def test_page_backup_rejects_omission_promotion_or_tampered_restoration(change):
    snapshot, receipt, readback = backup_fixture()
    if change in {"missing_article", "missing_page"}:
        readback["documents"].pop(
            "article-0" if change == "missing_article" else "categories"
        )
    elif change in {"id", "boolean_id", "draft_promoted", "page_body"}:
        field, value = {
            "id": ("id", 999),
            "boolean_id": ("id", True),
            "draft_promoted": ("status", "publish"),
            "page_body": ("block_markup", "changed"),
        }[change]
        readback["documents"]["categories"][field] = value
    elif change == "article_body":
        readback["documents"]["article-0"]["block_markup"] = "changed"
    elif change == "snapshot_drift":
        readback["source_snapshot_sha256"] = "b" * 64
    elif change == "hash_only":
        readback["documents"] = {
            key: row["content_sha256"] for key, row in readback["documents"].items()
        }
    elif change == "receipt":
        receipt["verified_document_count"] = 14
    elif change == "future":
        receipt["verified_at"] = "2026-09-06T00:00:00Z"
    elif change == "environment":
        readback["temporary_environment"] = False
    elif change == "privacy_draft":
        next(row for row in snapshot["documents"] if row["slug"] == "privacy-policy")[
            "status"
        ] = "draft"
    else:
        snapshot["documents"][-1]["slug"] = "first-suitcase-guide"
    # Reseal the observed readback digest: trust must come from replaying its fields.
    receipt["readback_sha256"] = manifest.digest(manifest.canonical(readback))
    with pytest.raises(audit.IncrementalAuditFailure):
        validate_backup(snapshot, receipt, readback)


def test_two_complete_page_review_rounds_produce_only_owner_review_binding():
    report, artifacts, snapshot, hashes = full_pair()
    binding = validate_pair(report, artifacts, snapshot, hashes).to_document()
    assert binding["consecutive_clean_rounds"] == 2
    assert binding["owner_approval_required"] is True
    assert binding["publication_authority"] is False


@pytest.mark.parametrize(
    "change",
    ["one_round", "same_reviewer", "self_review", "unexecuted", "missing_backup"],
)
def test_page_only_does_not_waive_independence_or_evidence(change):
    report, artifacts, snapshot, hashes = full_pair()
    if change == "one_round":
        report["rounds"].pop()
    elif change == "same_reviewer":
        report["rounds"][1]["reviewer_id"] = report["rounds"][0]["reviewer_id"]
    elif change == "self_review":
        report["rounds"][0]["execution_id"] = legacy.IMPLEMENTERS[0]
    elif change == "unexecuted":
        report["rounds"][0]["surfaces"][1]["execution_status"] = "NOT_EXECUTED"
    else:
        artifacts.pop("synthetic-backup")
    with pytest.raises(audit.IncrementalAuditFailure):
        validate_pair(report, artifacts, snapshot, hashes)


def theme_backup_fixture():
    from raos.application.editorial import local_scratch_theme_restore_v1 as theme

    snapshot, content_receipt, content_readback = backup_fixture()
    snapshot["reader_page_slugs"] = ["categories"]
    baseline = theme.build_theme_package(
        {"style.css": b"Version: 1", "functions.php": b"<?php // old"}
    )
    candidate = theme.build_theme_package(
        {"style.css": b"Version: 2", "functions.php": b"<?php // new"}
    )
    packages = {"baseline": json.loads(baseline), "candidate": json.loads(candidate)}
    snapshot["deployment_status"] = {
        "schema": "RAOS_WORDPRESS_DEPLOYMENT_BASELINE_SNAPSHOT_V1",
        "source": "BOUNDED_WORDPRESS_DEPLOYMENT_MCP",
        "status": "CAPTURED_READ_ONLY",
        "theme": {
            "slug": theme.THEME_SLUG,
            "active": True,
            "tree_sha256": packages["baseline"]["tree_sha256"],
        },
    }
    snapshot_hash = manifest.digest(manifest.canonical(snapshot).rstrip(b"\n"))
    content_receipt["source_snapshot_sha256"] = content_readback[
        "source_snapshot_sha256"
    ] = snapshot_hash
    content_receipt["readback_sha256"] = manifest.digest(
        manifest.canonical(content_readback)
    )
    content_raw = manifest.canonical(content_receipt)
    fixed = {
        "publication_profile": "local-scratch-theme-restore-rehearsal",
        "publication_authority": False,
        "production_authority": False,
        "scratch_only": True,
        "temporary_environment": True,
        "environment_id": content_receipt["environment_id"],
        "theme_slug": theme.THEME_SLUG,
        "site_url": "http://scratch.wordpress.invalid",
        "operation": "SAME_BASENAME_FILES_ONLY_NO_ACTIVATION",
        "source_snapshot_sha256": snapshot_hash,
        "content_restore_receipt_sha256": manifest.digest(content_raw),
        "baseline_package_sha256": manifest.digest(baseline),
        "candidate_package_sha256": manifest.digest(candidate),
    }
    readback = {
        **fixed,
        "schema": "RAOS_WORDPRESS_READER_PAGE_THEME_RESTORE_READBACK_V2",
        "stages": [
            {
                "stage": name,
                "theme_tree_sha256": packages[kind]["tree_sha256"],
                "file_manifest": [
                    {key: row[key] for key in ("path", "size", "sha256")}
                    for row in packages[kind]["files"]
                ],
                "content_readback": deepcopy(content_readback),
                "wordpress_options_sha256": "a" * 64,
            }
            for name, kind in (
                ("baseline_before", "baseline"),
                ("candidate_installed", "candidate"),
                ("baseline_restored", "baseline"),
            )
        ],
    }
    receipt = {
        **fixed,
        "schema": "RAOS_WORDPRESS_READER_PAGE_THEME_RESTORE_RECEIPT_V2",
        "status": "THEME_ROLLBACK_STORED_FIELDS_VERIFIED",
        "readback_sha256": manifest.digest(manifest.canonical(readback)),
        "baseline_tree_sha256": packages["baseline"]["tree_sha256"],
        "candidate_tree_sha256": packages["candidate"]["tree_sha256"],
        "restored_tree_sha256": packages["baseline"]["tree_sha256"],
        "verified_document_count": 15,
        "selected_page_slugs": ["categories"],
        "wordpress_options_unchanged": True,
        "wordpress_options_sha256": "a" * 64,
        "activation_changed": False,
        "current_preview_modified": False,
        "production_writes": False,
        "verified_noncontent_rollback_targets": ["theme"],
        "verified_at": "2026-09-05T10:00:00Z",
    }
    args = {
        "snapshot": snapshot,
        "article_slugs": legacy.BACKUP_SLUGS,
        "content_receipt_raw": content_raw,
        "content_readback_raw": manifest.canonical(content_readback),
        "baseline_package_raw": baseline,
        "candidate_package_raw": candidate,
        "expected_candidate_tree_sha256": packages["candidate"]["tree_sha256"],
        "observed_at": legacy.NOW,
        "expected_page_slugs": frozenset({"categories"}),
    }
    return readback, receipt, args


@pytest.mark.parametrize("change", [None, "missing-hub", "changed-home", "changed-options"])
def test_theme_only_audit_restores_captured_hubs_without_selecting_page_updates(monkeypatch, change):
    from dataclasses import replace

    readback, receipt, args = theme_backup_fixture()
    snapshot = args["snapshot"]
    raw_snapshot = manifest.canonical(snapshot)
    if change == "missing-hub":
        readback["stages"][1]["content_readback"]["documents"].pop("categories")
    elif change == "changed-home":
        readback["stages"][1]["content_readback"]["documents"]["home"]["block_markup"] = "Changed"
    elif change == "changed-options":
        readback["stages"][1]["wordpress_options_sha256"] = "b" * 64
    receipt["readback_sha256"] = manifest.digest(manifest.canonical(readback))
    evidence = {
        "synthetic-backup": raw_snapshot,
        "synthetic-restoration": args["content_receipt_raw"],
        "synthetic-readback": args["content_readback_raw"],
        "synthetic-theme-backup": args["baseline_package_raw"],
        "synthetic-theme-candidate": args["candidate_package_raw"],
        "synthetic-theme-readback": manifest.canonical(readback),
        "synthetic-theme-restoration": manifest.canonical(receipt),
    }
    monkeypatch.setattr(legacy, "BACKUP_SNAPSHOT", snapshot)
    monkeypatch.setattr(legacy, "INPUTS", {
        "source": "b" * 64,
        "live-snapshot": manifest.digest(raw_snapshot),
        "theme-tree": args["expected_candidate_tree_sha256"],
    })
    monkeypatch.setattr(legacy, "restoration_artifacts", lambda: dict(evidence))
    scope = replace(
        legacy.scope(), selected_article_ids=(), selected_page_slugs=(),
        claim_ids_by_article={}, retained_product_ids=(), affiliate_cta_ids=(),
        product_image_ids=(), shared_changes=True,
        required_noncontent_rollback_targets=("theme",),
    )
    report, artifacts = legacy.synthetic_pair(scope)
    for index in (0, 1):
        legacy.mutate_proof(report, artifacts, audit.BACKUP_SURFACE,
            lambda proof: proof["checks"].update(
                theme_backup_artifact_id="synthetic-theme-backup",
                theme_candidate_artifact_id="synthetic-theme-candidate",
                theme_readback_artifact_id="synthetic-theme-readback",
                theme_restoration_artifact_id="synthetic-theme-restoration",
            ), round_index=index)
    if change is None:
        result = legacy.validate(report, artifacts, scope).to_document()
        assert result["publication_authority"] is False
        assert scope.selected_page_slugs == ()
    else:
        with pytest.raises(audit.IncrementalAuditFailure):
            legacy.validate(report, artifacts, scope)


@pytest.mark.parametrize(
    "change",
    [None, "content", "options", "theme", "package", "missing_stage", "future"],
)
def test_page_and_theme_backup_requires_three_actual_restoration_states(change):
    readback, receipt, args = theme_backup_fixture()
    if change == "content":
        readback["stages"][1]["content_readback"]["documents"]["categories"][
            "status"
        ] = "publish"
    elif change == "options":
        readback["stages"][1]["wordpress_options_sha256"] = "b" * 64
    elif change == "theme":
        readback["stages"][2]["theme_tree_sha256"] = receipt["candidate_tree_sha256"]
    elif change == "package":
        args["baseline_package_raw"] = args["candidate_package_raw"]
    elif change == "missing_stage":
        readback["stages"].pop()
    elif change == "future":
        receipt["verified_at"] = "2026-09-06T00:00:00Z"
    receipt["readback_sha256"] = manifest.digest(manifest.canonical(readback))
    args.update(
        theme_readback_raw=manifest.canonical(readback),
        theme_receipt_raw=manifest.canonical(receipt),
    )
    if change is None:
        result = audit.validate_scratch_theme_backup_evidence_v1(**args)
        assert result["verified_document_count"] == 15
        assert result["verified_noncontent_rollback_targets"] == ["theme"]
        assert result["publication_authority"] is False
    else:
        with pytest.raises(audit.IncrementalAuditFailure):
            audit.validate_scratch_theme_backup_evidence_v1(**args)

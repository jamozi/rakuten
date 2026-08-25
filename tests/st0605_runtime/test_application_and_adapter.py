from __future__ import annotations

import json
from dataclasses import fields, replace
import hashlib
from pathlib import Path

import pytest

from raos.adapters.recorded_claim_evidence import (
    RecordedClaimEvidenceAdapter,
    RecordedClaimEvidenceError,
    load_recorded_claim_evidence_fixture,
)
from raos.application.evidence.claim_evidence import (
    EvaluateClaimEvidenceCoverageService,
    RecordClaimEvidenceCoverageService,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.evidence.claim_evidence import (
    ClaimEvidenceSnapshot,
    CoverageFindingCode,
    CoverageStatus,
    EvidenceValidationAttestation,
    ValidationAttestationOrigin,
    complete_claim_set_sha256,
    evaluate_claim_evidence,
    recorded_synthetic_attestation_decision_sha256,
    required_validation_attestation_inputs,
    validation_attestation_owner_binding,
)
import raos.domain.evidence.claim_evidence as claim_evidence_module
from raos.domain.shared.persistence import Sha256Digest

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "changes/st-0605/generated/claim-evidence-runtime-pass.v1.json"
)


def _self_declared_subset(value: ClaimEvidenceSnapshot) -> ClaimEvidenceSnapshot:
    claim = value.claims[0]
    fact = value.facts[0]
    claims = (claim,)
    unbound = replace(
        value,
        article=replace(
            value.article,
            complete_claim_ids=(claim.claim_id,),
            complete_claim_set_sha256=complete_claim_set_sha256(claims),
        ),
        approved_packet=replace(value.approved_packet, fact_ids=(fact.fact_id,)),
        claims=claims,
        requirement_proofs=(value.requirement_proofs[0],),
        facts=(fact,),
        links=(value.links[0],),
        snapshots=(value.snapshots[0],),
        identities=(value.identities[0],),
        citations=(value.citations[0],),
        attestations=(),
    )
    receipts = []
    for kind, subject, input_sha256 in required_validation_attestation_inputs(unbound):
        owner, version, contract_sha256 = validation_attestation_owner_binding(kind)
        receipts.append(
            EvidenceValidationAttestation(
                kind=kind,
                owner_story_id=owner,
                contract_version=version,
                contract_sha256=contract_sha256,
                origin=ValidationAttestationOrigin.RECORDED_SYNTHETIC_ONLY,
                subject_sha256=subject,
                input_sha256=input_sha256,
                decision_sha256=recorded_synthetic_attestation_decision_sha256(
                    kind,
                    subject,
                    input_sha256,
                ),
                validated_at=value.evaluated_at,
                valid=True,
            )
        )
    return replace(unbound, attestations=tuple(receipts))


def test_application_reads_then_records_without_content_mutation(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    adapter = RecordedClaimEvidenceAdapter(
        environment=RuntimeEnvironment.CI,
        capacity=2,
        snapshots=(passing_snapshot,),
    )
    evaluator = EvaluateClaimEvidenceCoverageService(
        environment=RuntimeEnvironment.CI,
        reader=adapter,
    )
    recorder = RecordClaimEvidenceCoverageService(
        environment=RuntimeEnvironment.CI,
        reader=adapter,
        appender=adapter,
    )
    report = evaluator.evaluate(passing_snapshot.article.article_version_id)
    receipt = recorder.record(passing_snapshot.article.article_version_id, report)
    replay = recorder.record(passing_snapshot.article.article_version_id, report)
    assert report.status is CoverageStatus.PASS
    assert receipt == replay
    assert receipt.sequence == 1
    assert receipt.publication_authorized is False
    assert adapter.get_snapshot(passing_snapshot.article.article_version_id) is (
        passing_snapshot
    )
    assert adapter.receipts() == (receipt,)


def test_missing_or_throwing_reader_returns_unevaluable_sanitized_report(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    class MissingReader:
        def get_snapshot(self, article_version_id: object) -> None:
            del article_version_id
            return None

    service = EvaluateClaimEvidenceCoverageService(
        environment=RuntimeEnvironment.ENV_DEV,
        reader=MissingReader(),
    )
    report = service.evaluate(passing_snapshot.article.article_version_id)
    assert report.status is CoverageStatus.UNEVALUABLE
    assert report.findings == (CoverageFindingCode.INPUT_UNAVAILABLE,)
    assert report.publication_authorized is False


def test_recorded_services_reject_staging_and_production() -> None:
    class Empty:
        def get_snapshot(self, article_version_id: object) -> None:
            del article_version_id
            return None

    for environment in (
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.PRODUCTION,
    ):
        with pytest.raises(ValueError, match="INVALID_CLAIM_EVIDENCE_SERVICE"):
            EvaluateClaimEvidenceCoverageService(
                environment=environment,
                reader=Empty(),
            )


def test_fixture_loader_rejects_unknown_fields_enums_duplicates_and_oversize() -> None:
    original = json.loads(FIXTURE_PATH.read_bytes())
    variants = []
    unknown = dict(original)
    unknown["secret"] = "canary"
    variants.append(unknown)
    enum_drift = json.loads(FIXTURE_PATH.read_bytes())
    enum_drift["claims"][0]["claim_type"] = "invented"
    variants.append(enum_drift)
    for variant in variants:
        payload = json.dumps(variant, separators=(",", ":")).encode()
        with pytest.raises(RecordedClaimEvidenceError):
            load_recorded_claim_evidence_fixture(payload)

    duplicate = b'{"schema_version":1,"schema_version":1}'
    with pytest.raises(RecordedClaimEvidenceError):
        load_recorded_claim_evidence_fixture(duplicate)
    with pytest.raises(RecordedClaimEvidenceError):
        load_recorded_claim_evidence_fixture(b"x" * 1_048_577)


def test_append_capacity_fails_closed_without_overwriting(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    adapter = RecordedClaimEvidenceAdapter(
        environment=RuntimeEnvironment.CI,
        capacity=1,
        snapshots=(passing_snapshot,),
    )
    passing = evaluate_claim_evidence(passing_snapshot)
    first = adapter.append_report(passing_snapshot, passing)
    altered = replace(passing_snapshot, citations=())
    blocking = evaluate_claim_evidence(altered)
    with pytest.raises(RecordedClaimEvidenceError):
        adapter.append_report(altered, blocking)
    malformed = replace(passing_snapshot)
    object.__setattr__(malformed, "article", object())
    with pytest.raises(RecordedClaimEvidenceError):
        adapter.append_report(malformed, passing)
    assert adapter.receipts() == (first,)


def test_append_rejects_coherent_report_not_derived_from_snapshot(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    adapter = RecordedClaimEvidenceAdapter(
        environment=RuntimeEnvironment.CI,
        capacity=1,
        snapshots=(passing_snapshot,),
    )
    report = evaluate_claim_evidence(passing_snapshot)
    forged_body = Sha256Digest("0" * 64)
    if forged_body == report.article_body_sha256:
        forged_body = Sha256Digest("1" * 64)
    unhashed = replace(
        report,
        article_body_sha256=forged_body,
        report_sha256=Sha256Digest("0" * 64),
    )
    forged = replace(
        unhashed,
        report_sha256=Sha256Digest(
            hashlib.sha256(
                claim_evidence_module._report_bytes(  # noqa: SLF001
                    unhashed,
                    include_digest=False,
                )
            ).hexdigest()
        ),
    )
    forged.require_valid()

    with pytest.raises(RecordedClaimEvidenceError):
        adapter.append_report(passing_snapshot, forged)
    recorder = RecordClaimEvidenceCoverageService(
        environment=RuntimeEnvironment.CI,
        reader=adapter,
        appender=adapter,
    )
    with pytest.raises(ValueError, match="CLAIM_EVIDENCE_RECORD_MISMATCH"):
        recorder.record(passing_snapshot.article.article_version_id, forged)
    assert adapter.receipts() == ()


def test_record_boundary_rejects_self_declared_smaller_denominator(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    adapter = RecordedClaimEvidenceAdapter(
        environment=RuntimeEnvironment.CI,
        capacity=1,
        snapshots=(passing_snapshot,),
    )
    subset = _self_declared_subset(passing_snapshot)
    subset_report = evaluate_claim_evidence(subset)
    assert subset_report.status is CoverageStatus.PASS

    with pytest.raises(RecordedClaimEvidenceError):
        adapter.append_report(subset, subset_report)
    recorder = RecordClaimEvidenceCoverageService(
        environment=RuntimeEnvironment.CI,
        reader=adapter,
        appender=adapter,
    )
    with pytest.raises(ValueError, match="CLAIM_EVIDENCE_RECORD_MISMATCH"):
        recorder.record(
            passing_snapshot.article.article_version_id,
            subset_report,
        )
    assert adapter.receipts() == ()


def test_preloaded_snapshot_anchor_detects_post_construction_alias_mutation(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    del passing_snapshot
    fresh_snapshot = load_recorded_claim_evidence_fixture(FIXTURE_PATH.read_bytes())
    adapter = RecordedClaimEvidenceAdapter(
        environment=RuntimeEnvironment.CI,
        capacity=1,
        snapshots=(fresh_snapshot,),
    )
    stored = adapter.get_snapshot(fresh_snapshot.article.article_version_id)
    assert stored is fresh_snapshot
    subset = _self_declared_subset(fresh_snapshot)
    for field in fields(ClaimEvidenceSnapshot):
        object.__setattr__(stored, field.name, getattr(subset, field.name))
    subset_report = evaluate_claim_evidence(stored)
    assert subset_report.status is CoverageStatus.PASS

    with pytest.raises(RecordedClaimEvidenceError):
        adapter.get_snapshot(subset.article.article_version_id)
    with pytest.raises(RecordedClaimEvidenceError):
        adapter.append_report(stored, subset_report)
    assert adapter.receipts() == ()


def test_append_history_is_anchored_by_immutable_values_not_report_alias(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    adapter = RecordedClaimEvidenceAdapter(
        environment=RuntimeEnvironment.CI,
        capacity=1,
        snapshots=(passing_snapshot,),
    )
    report = evaluate_claim_evidence(passing_snapshot)
    receipt = adapter.append_report(passing_snapshot, report)
    object.__setattr__(report, "report_sha256", Sha256Digest("f" * 64))

    assert adapter.receipts() == (receipt,)


def test_recorded_adapter_has_no_update_delete_publish_or_network_surface(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    adapter = RecordedClaimEvidenceAdapter(
        environment=RuntimeEnvironment.CI,
        capacity=1,
        snapshots=(passing_snapshot,),
    )
    for prohibited in (
        "update",
        "delete",
        "publish",
        "approve",
        "upload",
        "request",
        "send",
        "connect",
        "credential",
    ):
        assert not hasattr(adapter, prohibited)

"""Hostile binding, coverage, and prohibited-material tests for ST-0806 V2."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from uuid import UUID

import pytest

from raos.adapters.recorded_ai_draft_integration_v2 import (
    RecordedAiDraftIntegrationStepV2,
    load_recorded_ai_draft_fixture_v2,
)
from raos.application.editorial.ai_draft_integration_v2 import (
    AiDraftIntegrationServiceV2,
)
from raos.domain.ai.durable_job_queue_v2 import DurableQueueSnapshot
from raos.domain.editorial.ai_draft_integration_v2 import (
    AiDraftIntegrationRequestV2,
    AiDraftV2Activation,
    AiDraftV2Failure,
    AiDraftV2FailureCode,
    DraftCoverageDecisionV2,
    DraftProposalDispositionV2,
    RecordedDraftMaterialV2,
)
from raos.domain.editorial.content_ast import dump_content_ast_json, load_content_ast
from raos.domain.evidence.claim_evidence import (
    ClaimEvidenceSnapshot,
    ConflictId,
    ConflictStatus,
    CoverageRecordReceipt,
    CoverageStatus,
    EvidenceConflict,
    EvidenceValidationAttestation,
    UnknownValueHandling,
    ValidationAttestationOrigin,
    evaluate_claim_evidence,
    recorded_synthetic_attestation_decision_sha256,
    required_validation_attestation_inputs,
    validation_attestation_owner_binding,
)
from .v2_support import V2_FIXTURE, durable_success, request, service_and_adapter


class _MaterialPort:
    def __init__(self, material: RecordedDraftMaterialV2) -> None:
        self.material = material
        self.calls = 0

    def integrate(self, *, request_binding_sha256: str) -> RecordedDraftMaterialV2:
        assert len(request_binding_sha256) == 64
        self.calls += 1
        return self.material


def _service_for(
    bound: AiDraftIntegrationRequestV2, material: RecordedDraftMaterialV2
) -> tuple[AiDraftIntegrationServiceV2, _MaterialPort]:
    port = _MaterialPort(material)
    return (
        AiDraftIntegrationServiceV2(
            activation=AiDraftV2Activation(
                environment=bound.environment,
                enabled=True,
            ),
            port=port,
        ),
        port,
    )


def _reattest(snapshot: ClaimEvidenceSnapshot) -> ClaimEvidenceSnapshot:
    base = replace(snapshot, attestations=())
    attestations: list[EvidenceValidationAttestation] = []
    for kind, subject, input_sha256 in required_validation_attestation_inputs(base):
        owner, version, contract_sha256 = validation_attestation_owner_binding(kind)
        attestations.append(
            EvidenceValidationAttestation(
                kind=kind,
                owner_story_id=owner,
                contract_version=version,
                contract_sha256=contract_sha256,
                origin=ValidationAttestationOrigin.RECORDED_SYNTHETIC_ONLY,
                subject_sha256=subject,
                input_sha256=input_sha256,
                decision_sha256=recorded_synthetic_attestation_decision_sha256(
                    kind, subject, input_sha256
                ),
                validated_at=base.evaluated_at,
                valid=True,
            )
        )
    return replace(base, attestations=tuple(attestations))


def _coverage_material(
    snapshot: ClaimEvidenceSnapshot, *, fixture_sha256: str
) -> RecordedDraftMaterialV2:
    valid = load_recorded_ai_draft_fixture_v2(V2_FIXTURE.read_bytes())
    report = evaluate_claim_evidence(snapshot)
    return RecordedDraftMaterialV2(
        after_ast=valid.after_ast,
        coverage_snapshot=snapshot,
        coverage_report=report,
        coverage_receipt=CoverageRecordReceipt(1, report.report_sha256),
        fixture_sha256=fixture_sha256,
    )


def test_stale_revision_and_outcome_are_rejected_before_fixture_consumption() -> None:
    snapshot, outcome = durable_success()
    stale = DurableQueueSnapshot(
        queue_id=snapshot.queue_id,
        revision=snapshot.revision - 1,
        state_bytes=snapshot.state_bytes,
    )
    stale_request = request(snapshot=stale, outcome=outcome)
    service, adapter = service_and_adapter(bound_request=stale_request)
    with pytest.raises(AiDraftV2Failure) as stale_failure:
        service.integrate(request=stale_request)
    assert stale_failure.value.code is AiDraftV2FailureCode.DURABLE_RECEIPT_INVALID
    assert adapter.call_count == 0

    mismatched_outcome = replace(outcome, output_artifact_sha256="a" * 64)
    mismatch_request = request(snapshot=snapshot, outcome=mismatched_outcome)
    mismatch_service, mismatch_adapter = service_and_adapter(
        bound_request=mismatch_request
    )
    with pytest.raises(AiDraftV2Failure) as mismatch_failure:
        mismatch_service.integrate(request=mismatch_request)
    assert mismatch_failure.value.code is AiDraftV2FailureCode.DURABLE_RECEIPT_INVALID
    assert mismatch_adapter.call_count == 0


@pytest.mark.parametrize("invalid_cost", [None, -1])
def test_unknown_and_negative_cost_are_rejected_not_coerced(
    invalid_cost: int | None,
) -> None:
    snapshot, outcome = durable_success()
    object.__setattr__(outcome, "actual_cost_jpy", invalid_cost)
    malformed = request(snapshot=snapshot, outcome=outcome)
    service, adapter = service_and_adapter(bound_request=malformed)
    with pytest.raises(AiDraftV2Failure) as failure:
        service.integrate(request=malformed)
    assert failure.value.code is AiDraftV2FailureCode.INVALID_REQUEST
    assert adapter.call_count == 0


def test_missing_coverage_is_explicit_unavailable_and_never_passes() -> None:
    bound = request()
    valid = load_recorded_ai_draft_fixture_v2(V2_FIXTURE.read_bytes())
    unavailable = RecordedDraftMaterialV2(
        after_ast=valid.after_ast,
        coverage_snapshot=None,
        coverage_report=None,
        coverage_receipt=None,
        fixture_sha256="b" * 64,
    )
    service, port = _service_for(bound, unavailable)

    result = service.integrate(request=bound)

    assert port.calls == 1
    assert result.coverage_decision is DraftCoverageDecisionV2.UNAVAILABLE
    assert result.coverage_status is None
    assert result.disposition is DraftProposalDispositionV2.UNAVAILABLE
    assert result.proposal is None
    assert result.adoption_intent is None


def test_insufficient_evidence_is_recomputed_blocked_and_has_no_proposal() -> None:
    bound = request()
    valid = load_recorded_ai_draft_fixture_v2(V2_FIXTURE.read_bytes())
    assert valid.coverage_snapshot is not None
    blocked_snapshot = replace(valid.coverage_snapshot, links=())
    blocked_report = evaluate_claim_evidence(blocked_snapshot)
    assert blocked_report.status is CoverageStatus.BLOCK
    material = RecordedDraftMaterialV2(
        after_ast=valid.after_ast,
        coverage_snapshot=blocked_snapshot,
        coverage_report=blocked_report,
        coverage_receipt=CoverageRecordReceipt(1, blocked_report.report_sha256),
        fixture_sha256="c" * 64,
    )
    service, _ = _service_for(bound, material)

    result = service.integrate(request=bound)

    assert result.coverage_decision is DraftCoverageDecisionV2.BLOCKED
    assert result.coverage_status is CoverageStatus.BLOCK
    assert result.disposition is DraftProposalDispositionV2.BLOCKED
    assert result.proposal is None


def test_imputed_unknown_is_explicitly_blocked_not_coerced_to_zero() -> None:
    bound = request()
    valid = load_recorded_ai_draft_fixture_v2(V2_FIXTURE.read_bytes())
    assert valid.coverage_snapshot is not None
    first, *remaining = valid.coverage_snapshot.requirement_proofs
    unknown_snapshot = _reattest(
        replace(
            valid.coverage_snapshot,
            requirement_proofs=(
                replace(first, unknown_value_handling=UnknownValueHandling.IMPUTED),
                *remaining,
            ),
        )
    )
    material = _coverage_material(unknown_snapshot, fixture_sha256="1" * 64)
    assert material.coverage_report is not None
    assert material.coverage_report.status is CoverageStatus.BLOCK
    service, _ = _service_for(bound, material)

    result = service.integrate(request=bound)

    assert result.coverage_decision is DraftCoverageDecisionV2.BLOCKED
    assert result.proposal is None


def test_open_evidence_conflict_is_explicitly_blocked() -> None:
    bound = request()
    valid = load_recorded_ai_draft_fixture_v2(V2_FIXTURE.read_bytes())
    assert valid.coverage_snapshot is not None
    conflict = EvidenceConflict(
        conflict_id=ConflictId(UUID("99999999-9999-4999-8999-999999999806")),
        fact_ids=tuple(item.fact_id for item in valid.coverage_snapshot.facts),
        status=ConflictStatus.OPEN,
        resolution_decision_sha256=None,
        reviewer_identity_sha256=None,
        resolved_at=None,
    )
    conflict_snapshot = _reattest(
        replace(valid.coverage_snapshot, conflicts=(conflict,))
    )
    material = _coverage_material(conflict_snapshot, fixture_sha256="2" * 64)
    assert material.coverage_report is not None
    assert material.coverage_report.status is CoverageStatus.BLOCK
    service, _ = _service_for(bound, material)

    result = service.integrate(request=bound)

    assert result.coverage_decision is DraftCoverageDecisionV2.BLOCKED
    assert result.proposal is None


def test_structural_zero_denominator_is_unavailable_not_zero_or_pass() -> None:
    bound = request()
    valid = load_recorded_ai_draft_fixture_v2(V2_FIXTURE.read_bytes())
    assert valid.coverage_snapshot is not None
    unevaluable_snapshot = replace(valid.coverage_snapshot, claims=())
    unevaluable_report = evaluate_claim_evidence(unevaluable_snapshot)
    assert unevaluable_report.status is CoverageStatus.UNEVALUABLE
    assert unevaluable_report.major_coverage is None
    material = RecordedDraftMaterialV2(
        after_ast=valid.after_ast,
        coverage_snapshot=unevaluable_snapshot,
        coverage_report=unevaluable_report,
        coverage_receipt=CoverageRecordReceipt(1, unevaluable_report.report_sha256),
        fixture_sha256="d" * 64,
    )
    service, _ = _service_for(bound, material)

    result = service.integrate(request=bound)

    assert result.coverage_decision is DraftCoverageDecisionV2.UNAVAILABLE
    assert result.coverage_status is CoverageStatus.UNEVALUABLE
    assert result.proposal is None


def test_supplied_coverage_must_equal_exact_recomputation_and_receipt() -> None:
    bound = request()
    valid = load_recorded_ai_draft_fixture_v2(V2_FIXTURE.read_bytes())
    assert valid.coverage_snapshot is not None
    wrong_snapshot = replace(valid.coverage_snapshot, links=())
    wrong_report = evaluate_claim_evidence(wrong_snapshot)
    mismatched = RecordedDraftMaterialV2(
        after_ast=valid.after_ast,
        coverage_snapshot=valid.coverage_snapshot,
        coverage_report=wrong_report,
        coverage_receipt=CoverageRecordReceipt(1, wrong_report.report_sha256),
        fixture_sha256="e" * 64,
    )
    service, port = _service_for(bound, mismatched)
    with pytest.raises(AiDraftV2Failure) as failure:
        service.integrate(request=bound)
    assert failure.value.code is AiDraftV2FailureCode.COVERAGE_BINDING_MISMATCH
    assert port.calls == 1


def _mutated_after_fixture(text: str) -> bytes:
    root = json.loads(V2_FIXTURE.read_bytes())
    ast = json.loads(root["after_content_ast_utf8"])
    ast["blocks"][1]["content"][0]["text"] = text
    canonical = dump_content_ast_json(
        load_content_ast(json.dumps(ast, ensure_ascii=False))
    )
    root["after_content_ast_utf8"] = canonical
    root["after_content_ast_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    return (
        json.dumps(
            root,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode()


@pytest.mark.parametrize(
    "text",
    [
        "<b>raw html</b>",
        "https://untrusted.invalid/path",
        "".join(("pass", "word=", "not-a-real-", "secret")),
    ],
)
def test_raw_html_arbitrary_url_and_secret_like_text_fail_closed(text: str) -> None:
    with pytest.raises(AiDraftV2Failure) as failure:
        RecordedAiDraftIntegrationStepV2(
            request_binding_sha256="f" * 64,
            fixture_bytes=_mutated_after_fixture(text),
        )
    assert failure.value.code is AiDraftV2FailureCode.FIXTURE_INVALID
    assert "untrusted" not in str(failure.value)
    assert "secret" not in str(failure.value)


@pytest.mark.parametrize("field", ["raw_prompt", "review_body", "affiliate_rate"])
def test_unknown_prompt_review_and_economics_fields_fail_closed(field: str) -> None:
    root = json.loads(V2_FIXTURE.read_bytes())
    root[field] = "synthetic-forbidden-value"
    payload = (
        json.dumps(root, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode()
    with pytest.raises(AiDraftV2Failure) as failure:
        load_recorded_ai_draft_fixture_v2(payload)
    assert failure.value.code is AiDraftV2FailureCode.FIXTURE_INVALID

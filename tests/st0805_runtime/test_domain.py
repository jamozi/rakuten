from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib

from raos.domain.editorial.policy_engine import (
    POLICY_DEFINITIONS,
    QUALITY_AXIS_DEFINITIONS,
    QUALITY_GATE_DEFINITIONS,
    ZERO_TOLERANCE_LABELS,
    BoundReference,
    GateAssessmentState,
    PolicyRuleResult,
    ReferenceId,
    Sha256Digest as LegacySha256Digest,
    UtcInstant,
    WaiverAttempt,
    WaiverAuthorityClaim,
    WaiverDisposition,
    WaiverScopeType,
    ZeroToleranceState,
)
from raos.domain.editorial.policy_engine_v2 import (
    PolicyEvaluationEnvelopeV2,
    PolicyEvaluationStatusV2,
    PolicyFindingCodeV2,
    evaluate_editorial_policy_v2,
)
from raos.domain.evidence.claim_evidence import ValidationAttestationKind
from raos.domain.shared.persistence import Sha256Digest

from .conftest import rehash_policy_input


def _bound(label: str) -> BoundReference:
    return BoundReference(
        ReferenceId(label),
        LegacySha256Digest(hashlib.sha256(label.encode("ascii")).hexdigest()),
    )


def test_complete_catalog_and_dependency_chain_is_locally_evaluated(
    envelope: PolicyEvaluationEnvelopeV2,
) -> None:
    report = evaluate_editorial_policy_v2(envelope)
    report.require_valid()

    assert report.status is PolicyEvaluationStatusV2.LOCAL_EVALUATED
    assert not report.findings
    assert report.local_eligibility
    assert (
        len(envelope.policy_input.policy_assessments) == len(POLICY_DEFINITIONS) == 40
    )
    assert (
        len(envelope.policy_input.axis_assessments)
        == len(QUALITY_AXIS_DEFINITIONS)
        == 8
    )
    assert (
        len(envelope.policy_input.zero_tolerance_assessments)
        == len(ZERO_TOLERANCE_LABELS)
        == 13
    )
    assert (
        len(envelope.policy_input.gate_assessments)
        == len(QUALITY_GATE_DEFINITIONS)
        == 12
    )
    assert report.coverage_report_sha256 == envelope.coverage_report.report_sha256
    assert (
        report.recommendation_report_sha256
        == envelope.recommendation_report.report_sha256
    )
    assert report.article_version_no == envelope.draft.snapshot.version_no
    assert report.canonical_ast_sha256 == envelope.draft.canonical_ast_sha256
    assert (
        report.source_packet_content_sha256
        == envelope.coverage_report.source_packet_content_sha256
    )
    assert report.finding_proposal_only is True
    assert report.waiver_proposal_only is True
    assert all(
        value is False
        for value in (
            report.approval_authorized,
            report.waiver_apply_authorized,
            report.merge_authorized,
            report.recommendation_override_authorized,
            report.ranking_override_authorized,
            report.publication_authorized,
            report.activation_authorized,
            report.production_eligible,
        )
    )


def test_dependency_article_body_packet_claim_and_recommendation_hashes_are_exact(
    envelope: PolicyEvaluationEnvelopeV2,
) -> None:
    draft = envelope.draft.snapshot
    coverage = envelope.coverage_snapshot.article
    comparison = envelope.recommendation.comparison.comparison.article
    recommendation = envelope.recommendation_report

    assert coverage.article_version_id.value == draft.version_id
    assert coverage.article_body_sha256.value == draft.body_sha256.value
    assert coverage.source_packet_version_id.value == draft.source_packet_version_id
    assert comparison.article_id.value == draft.article_id
    assert comparison.article_version_id.value == draft.version_id
    assert comparison.article_body_sha256 == coverage.article_body_sha256
    assert comparison.complete_claim_set_sha256 == coverage.complete_claim_set_sha256
    assert recommendation.candidate_universe_sha256 is not None
    assert recommendation.axis_catalog_sha256 is not None
    assert recommendation.fact_set_sha256 is not None
    assert recommendation.temporal_scope_sha256 is not None
    assert recommendation.decision_context_sha256 is not None
    assert recommendation.methodology_sha256 is not None


def test_st0605_complete_receipt_and_st0803_precomputed_tuple_views_are_separate(
    envelope: PolicyEvaluationEnvelopeV2,
) -> None:
    coverage_kinds = {item.kind for item in envelope.coverage_snapshot.attestations}
    comparison_kinds = {
        item.kind
        for item in envelope.recommendation.comparison.claim_evidence.attestations
    }
    assert ValidationAttestationKind.COMPARISON in coverage_kinds
    assert ValidationAttestationKind.COMPARISON not in comparison_kinds
    assert (
        envelope.coverage_snapshot.article
        == envelope.recommendation.comparison.claim_evidence.article
    )


def test_collection_permutation_is_byte_deterministic(
    envelope: PolicyEvaluationEnvelopeV2,
) -> None:
    policy_input = replace(
        envelope.policy_input,
        predecessors=tuple(reversed(envelope.policy_input.predecessors)),
        policy_assessments=tuple(reversed(envelope.policy_input.policy_assessments)),
        axis_assessments=tuple(reversed(envelope.policy_input.axis_assessments)),
        zero_tolerance_assessments=tuple(
            reversed(envelope.policy_input.zero_tolerance_assessments)
        ),
        gate_assessments=tuple(reversed(envelope.policy_input.gate_assessments)),
    )
    permuted = rehash_policy_input(replace(envelope, policy_input=policy_input))
    assert (
        evaluate_editorial_policy_v2(permuted).canonical_bytes()
        == evaluate_editorial_policy_v2(envelope).canonical_bytes()
    )


def test_draft_binding_tamper_blocks(
    envelope: PolicyEvaluationEnvelopeV2,
) -> None:
    tampered = replace(
        envelope,
        draft=replace(envelope.draft, binding_sha256=Sha256Digest("0" * 64)),
    )
    report = evaluate_editorial_policy_v2(tampered)
    assert report.status is PolicyEvaluationStatusV2.BLOCK
    assert PolicyFindingCodeV2.DRAFT_BINDING_MISMATCH in report.findings


def test_coverage_receipt_tamper_blocks(
    envelope: PolicyEvaluationEnvelopeV2,
) -> None:
    tampered = replace(
        envelope,
        coverage_receipt=replace(
            envelope.coverage_receipt, report_sha256=Sha256Digest("0" * 64)
        ),
    )
    report = evaluate_editorial_policy_v2(tampered)
    assert report.status is PolicyEvaluationStatusV2.BLOCK
    assert PolicyFindingCodeV2.RECEIPT_INVALID in report.findings


def test_recommendation_receipt_tamper_blocks(
    envelope: PolicyEvaluationEnvelopeV2,
) -> None:
    tampered = replace(
        envelope,
        recommendation_receipt=replace(
            envelope.recommendation_receipt, report_sha256=Sha256Digest("0" * 64)
        ),
    )
    report = evaluate_editorial_policy_v2(tampered)
    assert report.status is PolicyEvaluationStatusV2.BLOCK
    assert PolicyFindingCodeV2.RECEIPT_INVALID in report.findings


def test_declared_policy_and_aggregate_hash_tamper_blocks(
    envelope: PolicyEvaluationEnvelopeV2,
) -> None:
    for tampered in (
        replace(envelope, policy_result_sha256=Sha256Digest("0" * 64)),
        replace(envelope, evaluation_input_sha256=Sha256Digest("0" * 64)),
    ):
        report = evaluate_editorial_policy_v2(tampered)
        assert report.status is PolicyEvaluationStatusV2.BLOCK
        assert report.findings


def test_not_evaluated_policy_stays_unevaluable(
    envelope: PolicyEvaluationEnvelopeV2,
) -> None:
    first = envelope.policy_input.policy_assessments[0]
    policy_input = replace(
        envelope.policy_input,
        policy_assessments=(
            replace(first, result=PolicyRuleResult.NOT_EVALUATED, evidence=()),
            *envelope.policy_input.policy_assessments[1:],
        ),
    )
    updated = rehash_policy_input(replace(envelope, policy_input=policy_input))
    report = evaluate_editorial_policy_v2(updated)
    assert report.status is PolicyEvaluationStatusV2.UNEVALUABLE
    assert PolicyFindingCodeV2.POLICY_NOT_EVALUATED in report.findings
    assert report.raw_quality_score == "100"
    assert not report.local_eligibility


def test_not_evaluated_axis_is_not_zero_or_pass(
    envelope: PolicyEvaluationEnvelopeV2,
) -> None:
    first = envelope.policy_input.axis_assessments[0]
    policy_input = replace(
        envelope.policy_input,
        axis_assessments=(
            replace(
                first, state=type(first.state).NOT_EVALUATED, score=None, evidence=()
            ),
            *envelope.policy_input.axis_assessments[1:],
        ),
    )
    updated = rehash_policy_input(replace(envelope, policy_input=policy_input))
    report = evaluate_editorial_policy_v2(updated)
    assert report.status is PolicyEvaluationStatusV2.UNEVALUABLE
    assert PolicyFindingCodeV2.POLICY_NOT_EVALUATED in report.findings
    assert report.raw_quality_score is None
    assert report.quality_threshold_met is None


def test_zero_tolerance_trigger_is_an_explicit_block(
    envelope: PolicyEvaluationEnvelopeV2,
) -> None:
    first = envelope.policy_input.zero_tolerance_assessments[0]
    policy_input = replace(
        envelope.policy_input,
        zero_tolerance_assessments=(
            replace(first, state=ZeroToleranceState.TRIGGERED),
            *envelope.policy_input.zero_tolerance_assessments[1:],
        ),
    )
    updated = rehash_policy_input(replace(envelope, policy_input=policy_input))
    report = evaluate_editorial_policy_v2(updated)
    assert report.status is PolicyEvaluationStatusV2.BLOCK
    assert PolicyFindingCodeV2.POLICY_BLOCKED in report.findings
    assert report.zero_tolerance_clear is False


def test_quality_gate_failure_is_an_explicit_block(
    envelope: PolicyEvaluationEnvelopeV2,
) -> None:
    first = envelope.policy_input.gate_assessments[0]
    policy_input = replace(
        envelope.policy_input,
        gate_assessments=(
            replace(first, state=GateAssessmentState.FAIL),
            *envelope.policy_input.gate_assessments[1:],
        ),
    )
    updated = rehash_policy_input(replace(envelope, policy_input=policy_input))
    report = evaluate_editorial_policy_v2(updated)
    assert report.status is PolicyEvaluationStatusV2.BLOCK
    assert PolicyFindingCodeV2.POLICY_BLOCKED in report.findings
    assert report.quality_gates_passed is False


def test_policy_failure_and_major_waiver_remain_proposals(
    envelope: PolicyEvaluationEnvelopeV2,
) -> None:
    policy_id = "POL-CONT-019"
    assessment = next(
        item
        for item in envelope.policy_input.policy_assessments
        if item.policy_id == policy_id
    )
    failed = replace(assessment, result=PolicyRuleResult.FAIL)
    waiver = WaiverAttempt(
        policy_id=policy_id,
        policy_version=assessment.policy_version,
        policy_source_sha256=assessment.policy_source_sha256,
        article_version_id=envelope.policy_input.article_version_id,
        scope_type=WaiverScopeType.ARTICLE_VERSION,
        scope_ref=envelope.policy_input.article_version_id,
        reason=_bound("REASON-REF-019"),
        evidence=(_bound("WAIVER-EVIDENCE-019"),),
        expiry_at=UtcInstant(datetime(2026, 9, 30, tzinfo=timezone.utc)),
        compliance_approver=_bound("COMPLIANCE-APPROVER-019"),
        audit_event=_bound("AUDIT-EVENT-019"),
        authority_claim=WaiverAuthorityClaim.REQUESTED,
    )
    policy_input = replace(
        envelope.policy_input,
        policy_assessments=tuple(
            failed if item.policy_id == policy_id else item
            for item in envelope.policy_input.policy_assessments
        ),
        waiver_attempts=(waiver,),
    )
    updated = rehash_policy_input(replace(envelope, policy_input=policy_input))
    report = evaluate_editorial_policy_v2(updated)
    assert report.status is PolicyEvaluationStatusV2.BLOCK
    assert PolicyFindingCodeV2.POLICY_BLOCKED in report.findings
    assert len(report.policy_findings) == 1
    assert (
        report.waiver_evaluations[0].disposition
        is WaiverDisposition.PENDING_HUMAN_AUTHORITY
    )
    assert report.waiver_evaluations[0].effective is False
    assert report.waiver_apply_authorized is False
    assert report.approval_authorized is False


def test_nested_finance_alias_in_typed_detector_blocks(
    envelope: PolicyEvaluationEnvelopeV2,
) -> None:
    first = envelope.policy_input.policy_assessments[0]
    detector = replace(first.detector, reference=ReferenceId("R3V3NUE"))
    policy_input = replace(
        envelope.policy_input,
        policy_assessments=(
            replace(first, detector=detector),
            *envelope.policy_input.policy_assessments[1:],
        ),
    )
    updated = rehash_policy_input(replace(envelope, policy_input=policy_input))
    report = evaluate_editorial_policy_v2(updated)
    assert report.status is PolicyEvaluationStatusV2.BLOCK
    assert PolicyFindingCodeV2.PROHIBITED_AFFILIATE_INPUT in report.findings


def test_policy_evidence_collection_bound_is_fail_closed(
    envelope: PolicyEvaluationEnvelopeV2,
) -> None:
    first = envelope.policy_input.policy_assessments[0]
    oversized = replace(first, evidence=first.evidence * 65)
    policy_input = replace(
        envelope.policy_input,
        policy_assessments=(oversized, *envelope.policy_input.policy_assessments[1:]),
    )
    report = evaluate_editorial_policy_v2(replace(envelope, policy_input=policy_input))
    assert report.status is PolicyEvaluationStatusV2.UNEVALUABLE
    assert PolicyFindingCodeV2.INPUT_BOUNDS_EXCEEDED in report.findings


def test_missing_st0605_comparison_receipt_stays_unevaluable(
    envelope: PolicyEvaluationEnvelopeV2,
) -> None:
    coverage_snapshot = replace(
        envelope.coverage_snapshot,
        attestations=tuple(
            item
            for item in envelope.coverage_snapshot.attestations
            if item.kind is not ValidationAttestationKind.COMPARISON
        ),
    )
    report = evaluate_editorial_policy_v2(
        replace(envelope, coverage_snapshot=coverage_snapshot)
    )
    assert report.status is PolicyEvaluationStatusV2.UNEVALUABLE
    assert PolicyFindingCodeV2.COVERAGE_UNEVALUABLE in report.findings


def test_wrong_input_type_is_closed_and_authority_free() -> None:
    report = evaluate_editorial_policy_v2({"revenue": 999})
    report.require_valid()
    assert report.status is PolicyEvaluationStatusV2.UNEVALUABLE
    assert not report.publication_authorized
    assert not report.ranking_override_authorized

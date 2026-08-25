"""Fail-closed DEV/CI orchestration for ST-1403 refresh proposals."""

from __future__ import annotations

from typing import final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.editorial.policy_engine import LocalEvaluationStatus
from raos.domain.editorial.policy_engine_v2 import (
    EVALUATOR_VERSION as POLICY_EVALUATOR_VERSION,
    ExecutionStatus,
    PolicyEvaluationEnvelopeV2,
    PolicyEvaluationReportV2,
    PolicyEvaluationStatusV2,
    evaluate_editorial_policy_v2,
)
from raos.domain.freshness.freshness import (
    FreshnessEvaluation,
    FreshnessEvaluationRequest,
    evaluate_freshness,
)
from raos.domain.freshness.refresh_proposal import (
    EditorialPolicyEvidenceBinding,
    FreshnessEvidenceBinding,
    RefreshDiff,
    RefreshProposal,
    RefreshProposalCandidate,
    RefreshProposalFailureCode,
    RefreshProposalRequest,
    build_refresh_proposal,
    fail_refresh_proposal,
)
from raos.ports.refresh_proposal import RefreshProposalExchange


def _supports_exchange(value: object) -> bool:
    supported = False
    try:
        supported = isinstance(value, RefreshProposalExchange)
    except Exception:
        pass
    return supported


def _same_policy_report(
    result: PolicyEvaluationReportV2,
    expected: PolicyEvaluationReportV2,
) -> bool:
    try:
        result.require_valid()
        expected.require_valid()
        return result.canonical_bytes() == expected.canonical_bytes()
    except Exception:
        return False


def _policy_binding(
    request: object,
    result: object,
) -> EditorialPolicyEvidenceBinding:
    if (
        type(request) is not PolicyEvaluationEnvelopeV2
        or type(result) is not PolicyEvaluationReportV2
    ):
        fail_refresh_proposal(RefreshProposalFailureCode.POLICY_RESULT_INVALID)
    try:
        expected = evaluate_editorial_policy_v2(request)
    except Exception:
        fail_refresh_proposal(RefreshProposalFailureCode.POLICY_RESULT_INVALID)
    if not _same_policy_report(result, expected):
        fail_refresh_proposal(RefreshProposalFailureCode.POLICY_RESULT_INVALID)
    if (
        expected.status is not PolicyEvaluationStatusV2.LOCAL_EVALUATED
        or expected.findings != ()
        or expected.legacy_status is not LocalEvaluationStatus.EVALUATED
        or expected.policy_findings != ()
        or expected.waiver_evaluations != ()
        or expected.raw_quality_score is None
        or expected.quality_threshold_met is not True
        or expected.quality_floors_met is not True
        or expected.policy_rules_passed is not True
        or expected.zero_tolerance_clear is not True
        or expected.quality_gates_passed is not True
        or expected.predecessors_available is not True
        or expected.local_eligibility is not True
        or expected.finding_proposal_only is not True
        or expected.waiver_proposal_only is not True
        or any(
            value is not False
            for value in (
                expected.approval_authorized,
                expected.waiver_apply_authorized,
                expected.merge_authorized,
                expected.recommendation_override_authorized,
                expected.ranking_override_authorized,
                expected.publication_authorized,
                expected.activation_authorized,
                expected.production_eligible,
            )
        )
        or any(
            value is not ExecutionStatus.NOT_EXECUTED
            for value in (
                expected.formal_tst_019_status,
                expected.formal_tst_020_status,
                expected.live_validation_status,
                expected.staging_status,
                expected.release_status,
                expected.publication_status,
                expected.production_status,
            )
        )
        or expected.article_version_id is None
    ):
        fail_refresh_proposal(RefreshProposalFailureCode.POLICY_INELIGIBLE)
    article_version_id = str(expected.article_version_id.value)
    return EditorialPolicyEvidenceBinding(
        article_version_id=article_version_id,
        local_result_digest=expected.report_sha256.value,
        serialization_profile=POLICY_EVALUATOR_VERSION,
        status=expected.status,
        legacy_status=expected.legacy_status,
        local_eligibility=expected.local_eligibility,
        finding_proposal_only=expected.finding_proposal_only,
        waiver_proposal_only=expected.waiver_proposal_only,
        approval_authorized=expected.approval_authorized,
        waiver_apply_authorized=expected.waiver_apply_authorized,
        merge_authorized=expected.merge_authorized,
        recommendation_override_authorized=(
            expected.recommendation_override_authorized
        ),
        ranking_override_authorized=expected.ranking_override_authorized,
        publication_authorized=expected.publication_authorized,
        activation_authorized=expected.activation_authorized,
        production_eligible=expected.production_eligible,
        formal_tst_019_status=expected.formal_tst_019_status,
        formal_tst_020_status=expected.formal_tst_020_status,
        formal_test_status=expected.formal_tst_020_status,
        live_validation_status=expected.live_validation_status,
        staging_status=expected.staging_status,
        release_status=expected.release_status,
        publication_status=expected.publication_status,
        production_status=expected.production_status,
    )


def _freshness_binding(
    request: object,
    result: object,
) -> FreshnessEvidenceBinding:
    snapshot: FreshnessEvaluation | None = None
    matches = False
    expected: FreshnessEvaluation | None = None
    if (
        type(request) is FreshnessEvaluationRequest
        and type(result) is FreshnessEvaluation
    ):
        try:
            expected = evaluate_freshness(request)
            source_fingerprint = result.fingerprint
            snapshot = FreshnessEvaluation(
                mode=result.mode,
                policy_binding=result.policy_binding,
                policy_class=result.policy_class,
                request_fingerprint=result.request_fingerprint,
                observation_status=result.observation_status,
                state=result.state,
                unknown_reason=result.unknown_reason,
                projection_action=result.projection_action,
                age_microseconds=result.age_microseconds,
                stale=result.stale,
                latest=result.latest,
                review_action=result.review_action,
                recommendation_order_action=result.recommendation_order_action,
                category_override_applied=result.category_override_applied,
                provider_override_applied=result.provider_override_applied,
                persistence=result.persistence,
                attestation=result.attestation,
                live_eligible=result.live_eligible,
            )
            matches = (
                snapshot == result
                and snapshot == expected
                and snapshot.fingerprint == source_fingerprint
                and snapshot.fingerprint == expected.fingerprint
                and result.fingerprint == source_fingerprint
            )
        except Exception:
            matches = False
    if snapshot is None or expected is None or not matches:
        fail_refresh_proposal(RefreshProposalFailureCode.FRESHNESS_RESULT_INVALID)
    return FreshnessEvidenceBinding(
        evaluation_fingerprint=expected.fingerprint,
        request_fingerprint=expected.request_fingerprint,
        policy_binding_fingerprint=expected.policy_binding.fingerprint,
        freshness_class_id=expected.policy_class.class_id,
        state=expected.state,
        projection_action=expected.projection_action,
        review_action=expected.review_action,
        recommendation_order_action=expected.recommendation_order_action,
        policy_activation=expected.policy_binding.activation,
        open_decision_id=expected.policy_binding.open_decision_id,
        open_decision_status=expected.policy_binding.open_decision_status,
        policy_active=expected.policy_binding.policy_active,
        persistence=expected.persistence,
        attestation=expected.attestation,
        live_eligible=expected.live_eligible,
    )


def _snapshot_diff(value: RefreshDiff) -> RefreshDiff:
    return RefreshDiff(
        diff_id=value.diff_id,
        kind=value.kind,
        change_type=value.change_type,
        changed_entity_type=value.changed_entity_type,
        changed_entity_id=value.changed_entity_id,
        before_sha256=value.before_sha256,
        after_sha256=value.after_sha256,
        affected_claim_ids=value.affected_claim_ids,
        impact_level=value.impact_level,
        required_action=value.required_action,
        impact_surfaces=value.impact_surfaces,
        action_type=value.action_type,
        deterministic_priority_rank=value.deterministic_priority_rank,
        recommendation_rank_change=value.recommendation_rank_change,
    )


def _snapshot_candidate(value: object) -> RefreshProposalCandidate:
    snapshot: RefreshProposalCandidate | None = None
    matches = False
    if type(value) is RefreshProposalCandidate and type(value.diffs) is tuple:
        try:
            source_fingerprint = value.fingerprint
            snapshot = RefreshProposalCandidate(
                article_version_id=value.article_version_id,
                baseline_publication_snapshot_sha256=(
                    value.baseline_publication_snapshot_sha256
                ),
                candidate_snapshot_sha256=value.candidate_snapshot_sha256,
                diffs=tuple(_snapshot_diff(item) for item in value.diffs),
            )
            matches = (
                snapshot == value
                and snapshot.fingerprint == source_fingerprint
                and value.fingerprint == source_fingerprint
            )
        except Exception:
            matches = False
    if snapshot is None or not matches:
        fail_refresh_proposal()
    return snapshot


def _snapshot_freshness_evidence(
    value: FreshnessEvidenceBinding,
) -> FreshnessEvidenceBinding:
    return FreshnessEvidenceBinding(
        evaluation_fingerprint=value.evaluation_fingerprint,
        request_fingerprint=value.request_fingerprint,
        policy_binding_fingerprint=value.policy_binding_fingerprint,
        freshness_class_id=value.freshness_class_id,
        state=value.state,
        projection_action=value.projection_action,
        review_action=value.review_action,
        recommendation_order_action=value.recommendation_order_action,
        policy_activation=value.policy_activation,
        open_decision_id=value.open_decision_id,
        open_decision_status=value.open_decision_status,
        policy_active=value.policy_active,
        persistence=value.persistence,
        attestation=value.attestation,
        live_eligible=value.live_eligible,
    )


def _snapshot_editorial_policy_evidence(
    value: EditorialPolicyEvidenceBinding,
) -> EditorialPolicyEvidenceBinding:
    return EditorialPolicyEvidenceBinding(
        article_version_id=value.article_version_id,
        local_result_digest=value.local_result_digest,
        serialization_profile=value.serialization_profile,
        status=value.status,
        legacy_status=value.legacy_status,
        local_eligibility=value.local_eligibility,
        finding_proposal_only=value.finding_proposal_only,
        waiver_proposal_only=value.waiver_proposal_only,
        approval_authorized=value.approval_authorized,
        waiver_apply_authorized=value.waiver_apply_authorized,
        merge_authorized=value.merge_authorized,
        recommendation_override_authorized=(value.recommendation_override_authorized),
        ranking_override_authorized=value.ranking_override_authorized,
        publication_authorized=value.publication_authorized,
        activation_authorized=value.activation_authorized,
        production_eligible=value.production_eligible,
        formal_tst_019_status=value.formal_tst_019_status,
        formal_tst_020_status=value.formal_tst_020_status,
        formal_test_status=value.formal_test_status,
        live_validation_status=value.live_validation_status,
        staging_status=value.staging_status,
        release_status=value.release_status,
        publication_status=value.publication_status,
        production_status=value.production_status,
    )


def _snapshot_request(value: RefreshProposalRequest) -> RefreshProposalRequest:
    return RefreshProposalRequest(
        candidate=_snapshot_candidate(value.candidate),
        freshness=_snapshot_freshness_evidence(value.freshness),
        editorial_policy=_snapshot_editorial_policy_evidence(value.editorial_policy),
    )


def bind_refresh_proposal_request(
    *,
    candidate: RefreshProposalCandidate,
    freshness_request: FreshnessEvaluationRequest,
    freshness_result: FreshnessEvaluation,
    policy_request: PolicyEvaluationEnvelopeV2,
    policy_result: PolicyEvaluationReportV2,
) -> RefreshProposalRequest:
    """Rerun and bind exact predecessor requests without promoting authority."""

    candidate_snapshot = _snapshot_candidate(candidate)
    freshness = _freshness_binding(freshness_request, freshness_result)
    editorial_policy = _policy_binding(policy_request, policy_result)
    if candidate_snapshot.article_version_id != editorial_policy.article_version_id:
        fail_refresh_proposal(RefreshProposalFailureCode.POLICY_RESULT_INVALID)
    return RefreshProposalRequest(
        candidate=candidate_snapshot,
        freshness=freshness,
        editorial_policy=editorial_policy,
    )


@final
class RefreshProposalService:
    """Return an exact recorded proposal without any state-changing capability."""

    __slots__ = ("_exchange",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        exchange: RefreshProposalExchange,
    ) -> None:
        if type(environment) is not RuntimeEnvironment or environment not in {
            RuntimeEnvironment.ENV_DEV,
            RuntimeEnvironment.CI,
        }:
            fail_refresh_proposal(RefreshProposalFailureCode.DEVELOPMENT_ONLY)
        if not _supports_exchange(exchange):
            fail_refresh_proposal()
        self._exchange = exchange

    def propose(
        self,
        *,
        candidate: RefreshProposalCandidate,
        freshness_request: FreshnessEvaluationRequest,
        freshness_result: FreshnessEvaluation,
        policy_request: PolicyEvaluationEnvelopeV2,
        policy_result: PolicyEvaluationReportV2,
    ) -> RefreshProposal:
        request = bind_refresh_proposal_request(
            candidate=candidate,
            freshness_request=freshness_request,
            freshness_result=freshness_result,
            policy_request=policy_request,
            policy_result=policy_result,
        )
        expected = build_refresh_proposal(request)
        sent_request = _snapshot_request(request)
        outcome: object = None
        unavailable = False
        try:
            outcome = self._exchange.propose(sent_request)
        except Exception:
            unavailable = True
        if unavailable:
            fail_refresh_proposal(RefreshProposalFailureCode.PROPOSER_UNAVAILABLE)
        sent_unchanged = False
        try:
            sent_request.__post_init__()
            sent_unchanged = sent_request.fingerprint == request.fingerprint
        except Exception:
            pass
        matches = False
        if sent_unchanged and type(outcome) is RefreshProposal:
            try:
                outcome.__post_init__()
                matches = (
                    outcome == expected
                    and outcome.fingerprint == expected.fingerprint
                    and outcome.request_fingerprint == request.fingerprint
                )
            except Exception:
                matches = False
        if not matches:
            fail_refresh_proposal(RefreshProposalFailureCode.PROPOSAL_MISMATCH)
        return expected


__all__ = [
    "RefreshProposalService",
    "bind_refresh_proposal_request",
]

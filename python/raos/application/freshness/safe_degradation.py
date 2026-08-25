"""Fail-closed DEV/CI orchestration for ST-1402 safe degradation."""

from __future__ import annotations

from typing import NoReturn, SupportsIndex, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.freshness.freshness import (
    FreshnessEvaluation,
    FreshnessEvaluationRequest,
    FreshnessState,
    evaluate_freshness,
)
from raos.domain.freshness.safe_degradation import (
    AvailabilityAggregate,
    SafeDegradationDecision,
    SafeDegradationFailureCode,
    SafeDegradationFreshnessBinding,
    SafeDegradationRequest,
    decide_safe_degradation,
    fail_safe_degradation,
    snapshot_safe_degradation_request,
)
from raos.ports.safe_degradation import SafeDegradationExchange


def _supports_exchange(value: object) -> bool:
    supported = False
    try:
        supported = isinstance(value, SafeDegradationExchange)
    except Exception:
        pass
    return supported


def _snapshot_evaluation(candidate: object) -> FreshnessEvaluation:
    snapshot: FreshnessEvaluation | None = None
    matches = False
    if type(candidate) is FreshnessEvaluation:
        try:
            source_fingerprint = candidate.fingerprint
            snapshot = FreshnessEvaluation(
                mode=candidate.mode,
                policy_binding=candidate.policy_binding,
                policy_class=candidate.policy_class,
                request_fingerprint=candidate.request_fingerprint,
                observation_status=candidate.observation_status,
                state=candidate.state,
                unknown_reason=candidate.unknown_reason,
                projection_action=candidate.projection_action,
                age_microseconds=candidate.age_microseconds,
                stale=candidate.stale,
                latest=candidate.latest,
                review_action=candidate.review_action,
                recommendation_order_action=candidate.recommendation_order_action,
                category_override_applied=candidate.category_override_applied,
                provider_override_applied=candidate.provider_override_applied,
                persistence=candidate.persistence,
                attestation=candidate.attestation,
                live_eligible=candidate.live_eligible,
            )
            matches = (
                snapshot == candidate
                and snapshot.fingerprint == source_fingerprint
                and candidate.fingerprint == source_fingerprint
            )
        except Exception:
            matches = False
    if snapshot is None or not matches:
        fail_safe_degradation(SafeDegradationFailureCode.FRESHNESS_RESULT_INVALID)
    return snapshot


def _freshness_binding(
    request: object,
    result: object,
) -> SafeDegradationFreshnessBinding:
    expected: FreshnessEvaluation | None = None
    snapshot: FreshnessEvaluation | None = None
    matches = False
    if (
        type(request) is FreshnessEvaluationRequest
        and type(result) is FreshnessEvaluation
    ):
        try:
            expected = evaluate_freshness(request)
            snapshot = _snapshot_evaluation(result)
            matches = (
                snapshot == expected
                and snapshot.fingerprint == expected.fingerprint
                and snapshot.request_fingerprint == request.fingerprint
                and expected.request_fingerprint == request.fingerprint
            )
        except Exception:
            matches = False
    if snapshot is None or expected is None or not matches:
        fail_safe_degradation(SafeDegradationFailureCode.FRESHNESS_RESULT_INVALID)
    if expected.policy_class.class_id not in {
        "FRESH-001",
        "FRESH-002",
        "FRESH-003",
    }:
        fail_safe_degradation(SafeDegradationFailureCode.UNSUPPORTED_FRESHNESS_CLASS)
    if (
        expected.state not in {FreshnessState.UNKNOWN, FreshnessState.CRITICAL}
        or expected.stale is not True
        or expected.latest is not False
    ):
        fail_safe_degradation(SafeDegradationFailureCode.FRESHNESS_NOT_DEGRADABLE)
    return SafeDegradationFreshnessBinding(
        evaluation_fingerprint=expected.fingerprint,
        request_fingerprint=expected.request_fingerprint,
        policy_binding_fingerprint=expected.policy_binding.fingerprint,
        freshness_class_id=expected.policy_class.class_id,
        state=expected.state,
        unknown_reason=expected.unknown_reason,
        projection_action=expected.projection_action,
        stale=expected.stale,
        latest=expected.latest,
        review_action=expected.review_action,
        recommendation_order_action=expected.recommendation_order_action,
        policy_authority=expected.policy_binding.authority,
        policy_activation=expected.policy_binding.activation,
        open_decision_id=expected.policy_binding.open_decision_id,
        open_decision_status=expected.policy_binding.open_decision_status,
        policy_active=expected.policy_binding.policy_active,
        persistence=expected.persistence,
        attestation=expected.attestation,
        live_eligible=expected.live_eligible,
    )


def bind_safe_degradation_request(
    *,
    freshness_request: FreshnessEvaluationRequest,
    freshness_result: FreshnessEvaluation,
    availability_aggregate: AvailabilityAggregate,
) -> SafeDegradationRequest:
    """Rerun and bind one exact ST-1401 request/result without values."""

    freshness = _freshness_binding(freshness_request, freshness_result)
    return SafeDegradationRequest(
        freshness=freshness,
        availability_aggregate=availability_aggregate,
    )


def _snapshot_decision(candidate: object) -> SafeDegradationDecision:
    snapshot: SafeDegradationDecision | None = None
    matches = False
    if type(candidate) is SafeDegradationDecision:
        try:
            source_fingerprint = candidate.fingerprint
            snapshot = SafeDegradationDecision(
                mode=candidate.mode,
                request_fingerprint=candidate.request_fingerprint,
                freshness_evaluation_fingerprint=(
                    candidate.freshness_evaluation_fingerprint
                ),
                freshness_class_id=candidate.freshness_class_id,
                availability_aggregate=candidate.availability_aggregate,
                actions=candidate.actions,
                notice_code=candidate.notice_code,
                review_action=candidate.review_action,
                recommendation_order_action=candidate.recommendation_order_action,
                renderer_effects=candidate.renderer_effects,
                persistence=candidate.persistence,
                attestation=candidate.attestation,
                can_change_state=candidate.can_change_state,
                publication_authorized=candidate.publication_authorized,
                live_eligible=candidate.live_eligible,
            )
            matches = (
                snapshot == candidate
                and snapshot.fingerprint == source_fingerprint
                and candidate.fingerprint == source_fingerprint
            )
        except Exception:
            matches = False
    if snapshot is None or not matches:
        fail_safe_degradation(SafeDegradationFailureCode.DECISION_MISMATCH)
    return snapshot


@final
class SafeDegradationService:
    """Return an exact recorded decision without applying any effect."""

    __slots__ = ("_exchange",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        exchange: SafeDegradationExchange,
    ) -> None:
        if type(environment) is not RuntimeEnvironment or environment not in {
            RuntimeEnvironment.ENV_DEV,
            RuntimeEnvironment.CI,
        }:
            fail_safe_degradation(SafeDegradationFailureCode.DEVELOPMENT_ONLY)
        if not _supports_exchange(exchange):
            fail_safe_degradation()
        self._exchange = exchange

    def __repr__(self) -> str:
        return "SafeDegradationService(<redacted-st1402-safe-degradation>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("safe-degradation service serialization is not supported")

    def decide(
        self,
        *,
        freshness_request: FreshnessEvaluationRequest,
        freshness_result: FreshnessEvaluation,
        availability_aggregate: AvailabilityAggregate,
    ) -> SafeDegradationDecision:
        request = bind_safe_degradation_request(
            freshness_request=freshness_request,
            freshness_result=freshness_result,
            availability_aggregate=availability_aggregate,
        )
        expected = decide_safe_degradation(request)
        sent_request = snapshot_safe_degradation_request(request)
        outcome: object = None
        unavailable = False
        try:
            outcome = self._exchange.decide(sent_request)
        except Exception:
            unavailable = True
        if unavailable:
            fail_safe_degradation(SafeDegradationFailureCode.DECIDER_UNAVAILABLE)

        sent_unchanged = False
        try:
            sent_snapshot = snapshot_safe_degradation_request(sent_request)
            sent_unchanged = sent_snapshot.fingerprint == request.fingerprint
        except Exception:
            pass

        matches = False
        if sent_unchanged and type(outcome) is SafeDegradationDecision:
            try:
                normalized_outcome = _snapshot_decision(outcome)
                matches = (
                    normalized_outcome == expected
                    and normalized_outcome.fingerprint == expected.fingerprint
                    and normalized_outcome.request_fingerprint == request.fingerprint
                )
            except Exception:
                matches = False
        if not matches:
            fail_safe_degradation(SafeDegradationFailureCode.DECISION_MISMATCH)
        return expected


__all__ = [
    "SafeDegradationService",
    "bind_safe_degradation_request",
]

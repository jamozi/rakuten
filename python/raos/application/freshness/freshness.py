"""Fail-closed DEV/CI service for recorded ST-1401 freshness evaluation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import NoReturn, SupportsIndex, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.freshness.freshness import (
    FreshnessCheckIntent,
    FreshnessEvaluation,
    FreshnessEvaluationRequest,
    FreshnessFailureCode,
    FreshnessScheduleEntry,
    FreshnessScheduleRequest,
    FreshnessScheduleSelection,
    evaluate_freshness,
    fail_freshness,
    select_due_freshness,
)
from raos.ports.freshness import FreshnessExchange


def _supports_exchange(value: object) -> bool:
    supported = False
    try:
        supported = isinstance(value, FreshnessExchange)
    except Exception:
        pass
    return supported


def _canonical_utc_fields(value: datetime) -> tuple[int, ...]:
    if (
        type(value) is not datetime
        or value.tzinfo is not timezone.utc
        or value.fold != 0
    ):
        fail_freshness(FreshnessFailureCode.INVALID_ARGUMENT)
    return (
        value.year,
        value.month,
        value.day,
        value.hour,
        value.minute,
        value.second,
        value.microsecond,
    )


def _same_evaluation_request(
    left: FreshnessEvaluationRequest,
    right: FreshnessEvaluationRequest,
) -> bool:
    return (
        left.freshness_class_id == right.freshness_class_id
        and left.observation_status is right.observation_status
        and (
            left.observed_at is None
            and right.observed_at is None
            or left.observed_at is not None
            and right.observed_at is not None
            and _canonical_utc_fields(left.observed_at)
            == _canonical_utc_fields(right.observed_at)
        )
        and _canonical_utc_fields(left.evaluated_at)
        == _canonical_utc_fields(right.evaluated_at)
        and left.recommendation_basis_affected is right.recommendation_basis_affected
    )


def _same_schedule_entry(
    left: FreshnessScheduleEntry,
    right: FreshnessScheduleEntry,
) -> bool:
    return (
        left.schedule_id.int == right.schedule_id.int
        and left.subject_fingerprint == right.subject_fingerprint
        and left.freshness_class_id == right.freshness_class_id
        and left.status is right.status
        and _canonical_utc_fields(left.next_due_at)
        == _canonical_utc_fields(right.next_due_at)
        and left.priority == right.priority
    )


def _same_schedule_request(
    left: FreshnessScheduleRequest,
    right: FreshnessScheduleRequest,
) -> bool:
    return (
        _canonical_utc_fields(left.evaluated_at)
        == _canonical_utc_fields(right.evaluated_at)
        and left.limit == right.limit
        and len(left.schedules) == len(right.schedules)
        and all(
            _same_schedule_entry(left_item, right_item)
            for left_item, right_item in zip(
                left.schedules, right.schedules, strict=True
            )
        )
    )


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
                recommendation_order_action=(candidate.recommendation_order_action),
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
        fail_freshness(FreshnessFailureCode.EVALUATION_MISMATCH)
    return snapshot


def _same_intent(left: FreshnessCheckIntent, right: FreshnessCheckIntent) -> bool:
    return (
        type(left.schedule_id) is type(right.schedule_id)
        and left.schedule_id.int == right.schedule_id.int
        and left.schedule_id.int != 0
        and left.subject_fingerprint == right.subject_fingerprint
        and left.freshness_class_id == right.freshness_class_id
        and _canonical_utc_fields(left.next_due_at)
        == _canonical_utc_fields(right.next_due_at)
        and left.priority == right.priority
        and left.request_fingerprint == right.request_fingerprint
    )


def _same_selection(
    left: FreshnessScheduleSelection,
    right: FreshnessScheduleSelection,
) -> bool:
    return (
        left.mode is right.mode
        and left.policy_binding == right.policy_binding
        and left.request_fingerprint == right.request_fingerprint
        and len(left.intents) == len(right.intents)
        and all(
            _same_intent(left_item, right_item)
            for left_item, right_item in zip(left.intents, right.intents, strict=True)
        )
        and left.cadence_computed is right.cadence_computed
        and left.persistence is right.persistence
        and left.attestation is right.attestation
        and left.live_eligible is right.live_eligible
    )


def _snapshot_selection(candidate: object) -> FreshnessScheduleSelection:
    snapshot: FreshnessScheduleSelection | None = None
    matches = False
    if type(candidate) is FreshnessScheduleSelection:
        try:
            source_fingerprint = candidate.fingerprint
            snapshot = FreshnessScheduleSelection(
                mode=candidate.mode,
                policy_binding=candidate.policy_binding,
                request_fingerprint=candidate.request_fingerprint,
                intents=candidate.intents,
                cadence_computed=candidate.cadence_computed,
                persistence=candidate.persistence,
                attestation=candidate.attestation,
                live_eligible=candidate.live_eligible,
            )
            matches = (
                _same_selection(snapshot, candidate)
                and snapshot.fingerprint == source_fingerprint
                and candidate.fingerprint == source_fingerprint
            )
        except Exception:
            matches = False
    if snapshot is None or not matches:
        fail_freshness(FreshnessFailureCode.SCHEDULE_MISMATCH)
    return snapshot


def _normalize_evaluation_request(
    candidate: object,
) -> FreshnessEvaluationRequest:
    normalized: FreshnessEvaluationRequest | None = None
    matches = False
    if type(candidate) is FreshnessEvaluationRequest:
        try:
            source_fingerprint = candidate.fingerprint
            normalized = FreshnessEvaluationRequest(
                freshness_class_id=candidate.freshness_class_id,
                observation_status=candidate.observation_status,
                observed_at=(
                    None if candidate.observed_at is None else candidate.observed_at
                ),
                evaluated_at=candidate.evaluated_at,
                recommendation_basis_affected=(candidate.recommendation_basis_affected),
            )
            matches = (
                _same_evaluation_request(normalized, candidate)
                and normalized.fingerprint == source_fingerprint
                and candidate.fingerprint == source_fingerprint
            )
        except Exception:
            matches = False
    if normalized is None or not matches:
        fail_freshness(FreshnessFailureCode.INVALID_ARGUMENT)
    return normalized


def _normalize_schedule_request(candidate: object) -> FreshnessScheduleRequest:
    normalized: FreshnessScheduleRequest | None = None
    matches = False
    if (
        type(candidate) is FreshnessScheduleRequest
        and type(candidate.schedules) is tuple
        and all(type(item) is FreshnessScheduleEntry for item in candidate.schedules)
    ):
        try:
            source_fingerprint = candidate.fingerprint
            normalized = FreshnessScheduleRequest(
                evaluated_at=candidate.evaluated_at,
                limit=candidate.limit,
                schedules=candidate.schedules,
            )
            matches = (
                _same_schedule_request(normalized, candidate)
                and normalized.fingerprint == source_fingerprint
                and candidate.fingerprint == source_fingerprint
            )
        except Exception:
            matches = False
    if normalized is None or not matches:
        fail_freshness(FreshnessFailureCode.INVALID_ARGUMENT)
    return normalized


@final
class FreshnessService:
    """Call one recorded collaborator once and rebuild the trusted result."""

    __slots__ = ("_exchange",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        exchange: FreshnessExchange,
    ) -> None:
        if type(environment) is not RuntimeEnvironment or environment not in {
            RuntimeEnvironment.ENV_DEV,
            RuntimeEnvironment.CI,
        }:
            fail_freshness(FreshnessFailureCode.DEVELOPMENT_ONLY)
        if not _supports_exchange(exchange):
            fail_freshness(FreshnessFailureCode.INVALID_ARGUMENT)
        self._exchange = exchange

    def __repr__(self) -> str:
        return "FreshnessService(<redacted-st1401-freshness>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("freshness service serialization is not supported")

    def evaluate(self, request: FreshnessEvaluationRequest) -> FreshnessEvaluation:
        normalized_request = _normalize_evaluation_request(request)
        expected = evaluate_freshness(normalized_request)
        sent_request = _normalize_evaluation_request(normalized_request)
        outcome: object = None
        unavailable = False
        try:
            outcome = self._exchange.evaluate(sent_request)
        except Exception:
            unavailable = True
        if unavailable:
            fail_freshness(FreshnessFailureCode.EVALUATOR_UNAVAILABLE)
        sent_unchanged = False
        try:
            revalidated_request = _normalize_evaluation_request(sent_request)
            sent_unchanged = (
                _same_evaluation_request(revalidated_request, normalized_request)
                and revalidated_request.fingerprint == expected.request_fingerprint
            )
        except Exception:
            pass
        if not sent_unchanged:
            fail_freshness(FreshnessFailureCode.EVALUATION_MISMATCH)
        matches = False
        if type(outcome) is FreshnessEvaluation:
            failed = False
            try:
                normalized_outcome = _snapshot_evaluation(outcome)
                matches = (
                    normalized_outcome == expected
                    and normalized_outcome.fingerprint == expected.fingerprint
                )
            except Exception:
                failed = True
            if failed:
                matches = False
        if not matches:
            fail_freshness(FreshnessFailureCode.EVALUATION_MISMATCH)
        return expected

    def select_due(
        self, request: FreshnessScheduleRequest
    ) -> FreshnessScheduleSelection:
        normalized_request = _normalize_schedule_request(request)
        expected = select_due_freshness(normalized_request)
        sent_request = _normalize_schedule_request(normalized_request)
        outcome: object = None
        unavailable = False
        try:
            outcome = self._exchange.select_due(sent_request)
        except Exception:
            unavailable = True
        if unavailable:
            fail_freshness(FreshnessFailureCode.SCHEDULER_UNAVAILABLE)
        sent_unchanged = False
        try:
            revalidated_request = _normalize_schedule_request(sent_request)
            sent_unchanged = (
                _same_schedule_request(revalidated_request, normalized_request)
                and revalidated_request.fingerprint == expected.request_fingerprint
            )
        except Exception:
            pass
        if not sent_unchanged:
            fail_freshness(FreshnessFailureCode.SCHEDULE_MISMATCH)
        matches = False
        if type(outcome) is FreshnessScheduleSelection:
            failed = False
            try:
                normalized_outcome = _snapshot_selection(outcome)
                matches = (
                    normalized_outcome == expected
                    and normalized_outcome.fingerprint == expected.fingerprint
                )
            except Exception:
                failed = True
            if failed:
                matches = False
        if not matches:
            fail_freshness(FreshnessFailureCode.SCHEDULE_MISMATCH)
        return expected


__all__ = ["FreshnessService"]

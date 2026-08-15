"""Bounded immutable fixtures for the DEV/CI-only ST-1401 freshness seam."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import NoReturn, SupportsIndex, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.freshness.freshness import (
    MAX_RECORDED_FRESHNESS_FIXTURES,
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


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedFreshnessEvaluationFixture:
    request: FreshnessEvaluationRequest
    evaluation: FreshnessEvaluation

    def __post_init__(self) -> None:
        matches = False
        if (
            type(self.request) is FreshnessEvaluationRequest
            and type(self.evaluation) is FreshnessEvaluation
        ):
            failed = False
            try:
                request = _snapshot_evaluation_request(self.request)
                evaluation = _snapshot_evaluation(self.evaluation)
                expected = evaluate_freshness(request)
                matches = (
                    evaluation == expected
                    and evaluation.fingerprint == expected.fingerprint
                )
            except Exception:
                failed = True
            if failed:
                matches = False
        if not matches:
            fail_freshness(FreshnessFailureCode.EVALUATION_MISMATCH)
        object.__setattr__(self, "request", request)
        object.__setattr__(self, "evaluation", expected)

    def __repr__(self) -> str:
        return "RecordedFreshnessEvaluationFixture(<redacted-st1401-freshness>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("freshness fixture serialization is not supported")


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedFreshnessScheduleFixture:
    request: FreshnessScheduleRequest
    selection: FreshnessScheduleSelection

    def __post_init__(self) -> None:
        matches = False
        if (
            type(self.request) is FreshnessScheduleRequest
            and type(self.selection) is FreshnessScheduleSelection
        ):
            failed = False
            try:
                request = _snapshot_schedule_request(self.request)
                selection = _snapshot_selection(self.selection)
                expected = select_due_freshness(request)
                matches = (
                    selection == expected
                    and selection.fingerprint == expected.fingerprint
                )
            except Exception:
                failed = True
            if failed:
                matches = False
        if not matches:
            fail_freshness(FreshnessFailureCode.SCHEDULE_MISMATCH)
        object.__setattr__(self, "request", request)
        object.__setattr__(self, "selection", expected)

    def __repr__(self) -> str:
        return "RecordedFreshnessScheduleFixture(<redacted-st1401-freshness>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("freshness fixture serialization is not supported")


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


def _snapshot_evaluation_request(
    request: FreshnessEvaluationRequest,
) -> FreshnessEvaluationRequest:
    snapshot: FreshnessEvaluationRequest | None = None
    matches = False
    if type(request) is FreshnessEvaluationRequest:
        try:
            source_fingerprint = request.fingerprint
            snapshot = FreshnessEvaluationRequest(
                freshness_class_id=request.freshness_class_id,
                observation_status=request.observation_status,
                observed_at=(
                    None if request.observed_at is None else request.observed_at
                ),
                evaluated_at=request.evaluated_at,
                recommendation_basis_affected=request.recommendation_basis_affected,
            )
            matches = (
                _same_evaluation_request(snapshot, request)
                and snapshot.fingerprint == source_fingerprint
                and request.fingerprint == source_fingerprint
            )
        except Exception:
            matches = False
    if snapshot is None or not matches:
        fail_freshness(FreshnessFailureCode.INVALID_ARGUMENT)
    return snapshot


def _snapshot_schedule_request(
    request: FreshnessScheduleRequest,
) -> FreshnessScheduleRequest:
    snapshot: FreshnessScheduleRequest | None = None
    matches = False
    if (
        type(request) is FreshnessScheduleRequest
        and type(request.schedules) is tuple
        and all(type(item) is FreshnessScheduleEntry for item in request.schedules)
    ):
        try:
            source_fingerprint = request.fingerprint
            snapshot = FreshnessScheduleRequest(
                evaluated_at=request.evaluated_at,
                limit=request.limit,
                schedules=request.schedules,
            )
            matches = (
                _same_schedule_request(snapshot, request)
                and snapshot.fingerprint == source_fingerprint
                and request.fingerprint == source_fingerprint
            )
        except Exception:
            matches = False
    if snapshot is None or not matches:
        fail_freshness(FreshnessFailureCode.INVALID_ARGUMENT)
    return snapshot


def _evaluation_binding(
    fixture: RecordedFreshnessEvaluationFixture,
) -> tuple[str, str]:
    request = _snapshot_evaluation_request(fixture.request)
    evaluation = _snapshot_evaluation(fixture.evaluation)
    expected = evaluate_freshness(request)
    if evaluation != expected or evaluation.fingerprint != expected.fingerprint:
        fail_freshness(FreshnessFailureCode.EVALUATION_MISMATCH)
    return request.fingerprint, expected.fingerprint


def _schedule_binding(
    fixture: RecordedFreshnessScheduleFixture,
) -> tuple[str, str]:
    request = _snapshot_schedule_request(fixture.request)
    selection = _snapshot_selection(fixture.selection)
    expected = select_due_freshness(request)
    if selection != expected or selection.fingerprint != expected.fingerprint:
        fail_freshness(FreshnessFailureCode.SCHEDULE_MISMATCH)
    return request.fingerprint, expected.fingerprint


@final
class RecordedFreshnessAdapter:
    """Return exact fixture outcomes without clocks, fallback, or state writes."""

    __slots__ = ("_evaluation_bindings", "_schedule_bindings")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        fixture_capacity: int,
        evaluation_fixtures: tuple[RecordedFreshnessEvaluationFixture, ...],
        schedule_fixtures: tuple[RecordedFreshnessScheduleFixture, ...],
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or type(fixture_capacity) is not int
            or not 1 <= fixture_capacity <= MAX_RECORDED_FRESHNESS_FIXTURES
            or type(evaluation_fixtures) is not tuple
            or type(schedule_fixtures) is not tuple
            or any(
                type(item) is not RecordedFreshnessEvaluationFixture
                for item in evaluation_fixtures
            )
            or any(
                type(item) is not RecordedFreshnessScheduleFixture
                for item in schedule_fixtures
            )
            or not 1
            <= len(evaluation_fixtures) + len(schedule_fixtures)
            <= fixture_capacity
        ):
            fail_freshness(FreshnessFailureCode.INVALID_ARGUMENT)
        nested_schedule_entries = 0
        nested_shape_valid = True
        try:
            for fixture in schedule_fixtures:
                if (
                    type(fixture.request) is not FreshnessScheduleRequest
                    or type(fixture.request.schedules) is not tuple
                ):
                    nested_shape_valid = False
                    break
                nested_schedule_entries += len(fixture.request.schedules)
                if nested_schedule_entries > MAX_RECORDED_FRESHNESS_FIXTURES:
                    nested_shape_valid = False
                    break
        except Exception:
            nested_shape_valid = False
        if not nested_shape_valid:
            fail_freshness(FreshnessFailureCode.INVALID_ARGUMENT)
        evaluation_bindings: tuple[tuple[str, str], ...] = ()
        schedule_bindings: tuple[tuple[str, str], ...] = ()
        try:
            evaluation_bindings = tuple(
                _evaluation_binding(fixture) for fixture in evaluation_fixtures
            )
            schedule_bindings = tuple(
                _schedule_binding(fixture) for fixture in schedule_fixtures
            )
        except Exception:
            fail_freshness(FreshnessFailureCode.INVALID_ARGUMENT)
        evaluation_keys = tuple(binding[0] for binding in evaluation_bindings)
        schedule_keys = tuple(binding[0] for binding in schedule_bindings)
        if len(set(evaluation_keys)) != len(evaluation_keys) or len(
            set(schedule_keys)
        ) != len(schedule_keys):
            fail_freshness(FreshnessFailureCode.INVALID_ARGUMENT)
        self._evaluation_bindings = evaluation_bindings
        self._schedule_bindings = schedule_bindings

    def __repr__(self) -> str:
        return "RecordedFreshnessAdapter(<redacted-st1401-freshness>)"

    def __str__(self) -> str:
        return "<redacted-st1401-freshness>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("freshness adapter serialization is not supported")

    def evaluate(self, request: FreshnessEvaluationRequest) -> FreshnessEvaluation:
        snapshot = _snapshot_evaluation_request(request)
        outcome = evaluate_freshness(snapshot)
        matches = tuple(
            binding
            for binding in self._evaluation_bindings
            if binding == (snapshot.fingerprint, outcome.fingerprint)
        )
        if len(matches) != 1:
            fail_freshness(FreshnessFailureCode.EVALUATOR_UNAVAILABLE)
        return outcome

    def select_due(
        self, request: FreshnessScheduleRequest
    ) -> FreshnessScheduleSelection:
        snapshot = _snapshot_schedule_request(request)
        outcome = select_due_freshness(snapshot)
        matches = tuple(
            binding
            for binding in self._schedule_bindings
            if binding == (snapshot.fingerprint, outcome.fingerprint)
        )
        if len(matches) != 1:
            fail_freshness(FreshnessFailureCode.SCHEDULER_UNAVAILABLE)
        return outcome


__all__ = [
    "RecordedFreshnessAdapter",
    "RecordedFreshnessEvaluationFixture",
    "RecordedFreshnessScheduleFixture",
]

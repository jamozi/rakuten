"""Canonical review-assignment creation and state-transition tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from typing import Callable, cast
from uuid import UUID

import pytest

from conftest import (
    ARTICLE_VERSION_ID,
    ASSIGNED_BY,
    ASSIGNED_TO,
    ASSIGNMENT_ID,
    CREATED_AT,
    FINISHED_AT,
    STARTED_AT,
    assigned,
    decision_reference,
    in_progress,
    uuid7,
)
from raos.domain.publishing.review_workflow import (
    ArticleVersionId,
    PrincipalId,
    ReviewAssignment,
    ReviewAssignmentId,
    ReviewAssignmentState,
    ReviewDecisionReference,
    ReviewType,
    ReviewWorkflowFailure,
    ReviewWorkflowFailureCode,
    UtcTimestamp,
    create_review_assignment,
    transition_review_assignment,
)


def test_creation_coordinates_produce_exact_initial_state() -> None:
    value = assigned()

    assert value.assignment_id == ASSIGNMENT_ID
    assert value.article_version_id == ARTICLE_VERSION_ID
    assert value.review_type is ReviewType.EDITORIAL
    assert value.assigned_by == ASSIGNED_BY
    assert value.assigned_to == ASSIGNED_TO
    assert value.priority == 50
    assert value.status is ReviewAssignmentState.ASSIGNED
    assert value.started_at is value.completed_at is value.cancelled_at is None
    assert value.created_at == value.updated_at == CREATED_AT
    assert value.lock_version == 0
    assert value.completion_decision_reference is None


@pytest.mark.parametrize("priority", (0, 100))
def test_priority_boundaries_are_accepted(priority: int) -> None:
    assert assigned(priority=priority).priority == priority


@pytest.mark.parametrize("priority", (-1, 101, True, False, 1.0, "50"))
def test_priority_outside_range_or_not_exact_int_is_rejected(priority: object) -> None:
    with pytest.raises(ReviewWorkflowFailure) as captured:
        assigned(priority=cast("int", priority))
    assert captured.value.code is ReviewWorkflowFailureCode.PRIORITY_INVALID


def test_all_four_canonical_transitions_are_positive_and_increment_lock() -> None:
    started = transition_review_assignment(
        assigned(),
        ReviewAssignmentState.IN_PROGRESS,
        STARTED_AT,
        None,
    )
    completed = transition_review_assignment(
        started,
        ReviewAssignmentState.COMPLETED,
        FINISHED_AT,
        decision_reference(),
    )
    cancelled_assigned = transition_review_assignment(
        assigned(),
        ReviewAssignmentState.CANCELLED,
        STARTED_AT,
        None,
    )
    cancelled_started = transition_review_assignment(
        started,
        ReviewAssignmentState.CANCELLED,
        FINISHED_AT,
        None,
    )

    assert started.status is ReviewAssignmentState.IN_PROGRESS
    assert started.started_at == started.updated_at == STARTED_AT
    assert started.lock_version == 1
    assert completed.status is ReviewAssignmentState.COMPLETED
    assert completed.started_at == STARTED_AT
    assert completed.completed_at == completed.updated_at == FINISHED_AT
    assert completed.completion_decision_reference == decision_reference()
    assert completed.lock_version == 2
    assert cancelled_assigned.status is ReviewAssignmentState.CANCELLED
    assert cancelled_assigned.started_at is None
    assert cancelled_assigned.cancelled_at == STARTED_AT
    assert cancelled_assigned.lock_version == 1
    assert cancelled_started.status is ReviewAssignmentState.CANCELLED
    assert cancelled_started.started_at == STARTED_AT
    assert cancelled_started.cancelled_at == FINISHED_AT
    assert cancelled_started.lock_version == 2


def test_direct_assigned_to_completed_and_every_other_forbidden_pair_fail() -> None:
    started = in_progress()
    completed = transition_review_assignment(
        started,
        ReviewAssignmentState.COMPLETED,
        FINISHED_AT,
        decision_reference(),
    )
    cancelled = transition_review_assignment(
        assigned(),
        ReviewAssignmentState.CANCELLED,
        STARTED_AT,
        None,
    )
    by_state = {
        ReviewAssignmentState.ASSIGNED: assigned(),
        ReviewAssignmentState.IN_PROGRESS: started,
        ReviewAssignmentState.COMPLETED: completed,
        ReviewAssignmentState.CANCELLED: cancelled,
    }
    allowed = {
        (ReviewAssignmentState.ASSIGNED, ReviewAssignmentState.IN_PROGRESS),
        (ReviewAssignmentState.ASSIGNED, ReviewAssignmentState.CANCELLED),
        (ReviewAssignmentState.IN_PROGRESS, ReviewAssignmentState.COMPLETED),
        (ReviewAssignmentState.IN_PROGRESS, ReviewAssignmentState.CANCELLED),
    }
    for source in ReviewAssignmentState:
        for target in ReviewAssignmentState:
            if (source, target) in allowed:
                continue
            with pytest.raises(ReviewWorkflowFailure) as captured:
                transition_review_assignment(
                    by_state[source],
                    target,
                    FINISHED_AT,
                    decision_reference()
                    if target is ReviewAssignmentState.COMPLETED
                    else None,
                )
            assert (
                captured.value.code
                is ReviewWorkflowFailureCode.STATE_TRANSITION_FORBIDDEN
            )


def test_completed_requires_exact_same_assignment_and_article_decision_coordinate() -> (
    None
):
    with pytest.raises(ReviewWorkflowFailure) as missing:
        transition_review_assignment(
            in_progress(),
            ReviewAssignmentState.COMPLETED,
            FINISHED_AT,
            None,
        )
    assert missing.value.code is ReviewWorkflowFailureCode.COMPLETION_DECISION_REQUIRED

    cases = (
        (
            decision_reference(assignment_id=ReviewAssignmentId(uuid7(401))),
            ReviewWorkflowFailureCode.ASSIGNMENT_BINDING_MISMATCH,
        ),
        (
            decision_reference(article_version_id=ArticleVersionId(uuid7(402))),
            ReviewWorkflowFailureCode.ARTICLE_VERSION_BINDING_MISMATCH,
        ),
    )
    for reference, expected_code in cases:
        with pytest.raises(ReviewWorkflowFailure) as captured:
            transition_review_assignment(
                in_progress(),
                ReviewAssignmentState.COMPLETED,
                FINISHED_AT,
                reference,
            )
        assert captured.value.code is expected_code


def test_completion_reference_is_rejected_on_noncompletion_transition() -> None:
    with pytest.raises(ReviewWorkflowFailure) as captured:
        transition_review_assignment(
            assigned(),
            ReviewAssignmentState.IN_PROGRESS,
            STARTED_AT,
            decision_reference(),
        )
    assert (
        captured.value.code is ReviewWorkflowFailureCode.COMPLETION_DECISION_UNEXPECTED
    )


def test_transitions_preserve_immutable_creation_coordinates() -> None:
    initial = assigned(priority=0)
    started = transition_review_assignment(
        initial,
        ReviewAssignmentState.IN_PROGRESS,
        STARTED_AT,
        None,
    )
    completed = transition_review_assignment(
        started,
        ReviewAssignmentState.COMPLETED,
        FINISHED_AT,
        decision_reference(),
    )

    for value in (started, completed):
        assert value.assignment_id == initial.assignment_id
        assert value.article_version_id == initial.article_version_id
        assert value.review_type is initial.review_type
        assert value.assigned_by == initial.assigned_by
        assert value.assigned_to == initial.assigned_to
        assert value.priority == initial.priority
        assert value.created_at == initial.created_at
    with pytest.raises(FrozenInstanceError):
        initial.priority = 50  # type: ignore[misc]


@pytest.mark.parametrize(
    "mutator",
    (
        lambda value: replace(value, status=ReviewAssignmentState.COMPLETED),
        lambda value: replace(value, started_at=STARTED_AT),
        lambda value: replace(value, completed_at=FINISHED_AT),
        lambda value: replace(value, cancelled_at=FINISHED_AT),
        lambda value: replace(value, lock_version=1),
        lambda value: replace(value, updated_at=STARTED_AT),
        lambda value: replace(
            value, completion_decision_reference=decision_reference()
        ),
    ),
)
def test_invalid_initial_state_timestamp_and_lock_combinations_fail(
    mutator: Callable[[ReviewAssignment], ReviewAssignment],
) -> None:
    with pytest.raises(ReviewWorkflowFailure):
        mutator(assigned())


def test_invalid_completed_timestamp_order_and_cancelled_shape_fail() -> None:
    completed = transition_review_assignment(
        in_progress(),
        ReviewAssignmentState.COMPLETED,
        FINISHED_AT,
        decision_reference(),
    )
    before_start = UtcTimestamp(datetime(2026, 8, 12, 0, 30, tzinfo=timezone.utc))
    with pytest.raises(ReviewWorkflowFailure):
        replace(completed, completed_at=before_start, updated_at=before_start)
    with pytest.raises(ReviewWorkflowFailure):
        replace(completed, cancelled_at=FINISHED_AT)


def test_transition_timestamp_cannot_precede_current_state() -> None:
    before_creation = UtcTimestamp(datetime(2026, 8, 11, 23, 59, tzinfo=timezone.utc))
    with pytest.raises(ReviewWorkflowFailure) as captured:
        transition_review_assignment(
            assigned(),
            ReviewAssignmentState.IN_PROGRESS,
            before_creation,
            None,
        )
    assert captured.value.code is ReviewWorkflowFailureCode.TIMESTAMP_INVALID


def test_direct_constructor_rejects_raw_state_review_type_and_bool_lock() -> None:
    value = assigned()

    def rebuild(
        *,
        review_type: ReviewType = value.review_type,
        status: ReviewAssignmentState = value.status,
        lock_version: int = value.lock_version,
    ) -> ReviewAssignment:
        return ReviewAssignment(
            value.assignment_id,
            value.article_version_id,
            review_type,
            value.assigned_by,
            value.assigned_to,
            value.priority,
            status,
            value.started_at,
            value.completed_at,
            value.cancelled_at,
            value.created_at,
            value.updated_at,
            lock_version,
            value.completion_decision_reference,
        )

    cases: tuple[
        tuple[Callable[[], ReviewAssignment], ReviewWorkflowFailureCode], ...
    ] = (
        (
            lambda: rebuild(status=cast("ReviewAssignmentState", "ASSIGNED")),
            ReviewWorkflowFailureCode.VOCABULARY_INVALID,
        ),
        (
            lambda: rebuild(review_type=cast("ReviewType", "EDITORIAL")),
            ReviewWorkflowFailureCode.VOCABULARY_INVALID,
        ),
        (
            lambda: rebuild(lock_version=True),
            ReviewWorkflowFailureCode.LOCK_VERSION_INVALID,
        ),
    )
    for constructor, expected_code in cases:
        with pytest.raises(ReviewWorkflowFailure) as captured:
            constructor()
        assert captured.value.code is expected_code


def test_closed_review_type_and_state_vocabularies_are_exact() -> None:
    assert tuple(value.value for value in ReviewType) == (
        "EDITORIAL",
        "FACT",
        "COMPLIANCE",
        "UX",
        "FINAL",
    )
    assert tuple(value.value for value in ReviewAssignmentState) == (
        "ASSIGNED",
        "IN_PROGRESS",
        "COMPLETED",
        "CANCELLED",
    )
    for token in (
        "editorial",
        "REASSIGNED",
        "PAUSED",
        "UNKNOWN",
        "ED-030",
        "REJECTED_REVIEW_TYPE_CANARY",
    ):
        with pytest.raises(ReviewWorkflowFailure) as captured:
            ReviewType(token)
        assert captured.value.code is ReviewWorkflowFailureCode.VOCABULARY_INVALID
        assert (
            token
            not in f"{captured.value!s} {captured.value!r} {captured.value.args!r}"
        )

    for enum_type in (ReviewAssignmentState,):
        invalid_value = "REJECTED_ASSIGNMENT_STATE_CANARY"
        with pytest.raises(ReviewWorkflowFailure) as captured:
            enum_type(invalid_value)
        assert captured.value.code is ReviewWorkflowFailureCode.VOCABULARY_INVALID
        assert (
            invalid_value
            not in f"{captured.value!s} {captured.value!r} {captured.value.args!r}"
        )


def test_uuid_timestamp_and_nested_coordinate_runtime_subclasses_are_rejected() -> None:
    class UuidSubclass(UUID):
        pass

    class DatetimeSubclass(datetime):
        pass

    with pytest.raises(ReviewWorkflowFailure):
        ReviewAssignmentId(UuidSubclass(str(uuid7(501))))
    with pytest.raises(ReviewWorkflowFailure):
        UtcTimestamp(DatetimeSubclass(2026, 8, 12, tzinfo=timezone.utc))

    reference = decision_reference()
    object.__setattr__(reference, "review_assignment_id", ASSIGNMENT_ID.value)
    with pytest.raises(ReviewWorkflowFailure):
        ReviewDecisionReference(
            reference.decision_id,
            cast("ReviewAssignmentId", ASSIGNMENT_ID.value),
            reference.article_version_id,
        )


def test_creation_rejects_coordinate_substitution_types() -> None:
    with pytest.raises(ReviewWorkflowFailure):
        create_review_assignment(
            assignment_id=ASSIGNMENT_ID,
            article_version_id=ARTICLE_VERSION_ID,
            review_type=ReviewType.EDITORIAL,
            assigned_by=cast("PrincipalId", ASSIGNED_BY.value),
            assigned_to=PrincipalId(uuid7(601)),
            priority=50,
            created_at=CREATED_AT,
        )

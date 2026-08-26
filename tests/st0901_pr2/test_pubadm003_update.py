"""Status-transition-only PUBADM-003 recorded concurrency evidence."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest

from .support import (
    FINISHED_AT,
    STARTED_AT,
    adapter,
    assignment,
    decision_reference,
    service,
    snapshot,
    update_request,
    update_step,
)
from raos.adapters.recorded_review_assignment import (
    RecordedUpdateReviewAssignmentStep,
)
from raos.domain.portfolio.workflow import (
    EntityVersion,
    IdempotencyKey,
    PortfolioWorkflowFailure,
    PortfolioWorkflowFailureCode,
    StrongEtag,
)
from raos.domain.publishing.review_assignment_operations import (
    RecordedAuditAction,
    RecordedAssignmentTransitionV1,
    ReviewAssignmentOperationFailure,
    ReviewAssignmentOperationFailureCode,
    UpdateReviewAssignmentRequest,
    UpdateReviewAssignmentResult,
)
from raos.domain.publishing.review_workflow import (
    ReviewAssignment,
    ReviewAssignmentState,
    ReviewDecisionReference,
    ReviewWorkflowFailure,
    UtcTimestamp,
    transition_review_assignment,
)


def _assert_preserved(before: ReviewAssignment, after: ReviewAssignment) -> None:
    assert after.assignment_id == before.assignment_id
    assert after.article_version_id == before.article_version_id
    assert after.review_type is before.review_type
    assert after.assigned_by == before.assigned_by
    assert after.assigned_to == before.assigned_to
    assert after.priority == before.priority
    assert after.created_at == before.created_at


def _cases() -> tuple[
    tuple[
        ReviewAssignment,
        ReviewAssignmentState,
        UtcTimestamp,
        ReviewDecisionReference | None,
    ],
    ...,
]:
    initial = assignment(priority=0)
    started = transition_review_assignment(
        initial,
        ReviewAssignmentState.IN_PROGRESS,
        STARTED_AT,
        None,
    )
    return (
        (initial, ReviewAssignmentState.IN_PROGRESS, STARTED_AT, None),
        (initial, ReviewAssignmentState.CANCELLED, STARTED_AT, None),
        (
            started,
            ReviewAssignmentState.COMPLETED,
            FINISHED_AT,
            decision_reference(started),
        ),
        (started, ReviewAssignmentState.CANCELLED, FINISHED_AT, None),
    )


@pytest.mark.parametrize(
    ("prior_assignment", "target_state", "occurred_at", "reference"),
    _cases(),
)
def test_pubadm003_all_allowed_transitions_use_exact_strong_concurrency(
    prior_assignment: ReviewAssignment,
    target_state: ReviewAssignmentState,
    occurred_at: UtcTimestamp,
    reference: ReviewDecisionReference | None,
) -> None:
    prior = snapshot(prior_assignment)
    request = update_request(
        prior,
        target_state=target_state,
        occurred_at=occurred_at,
        completion_reference=reference,
    )
    recorded = adapter(
        update_step(
            prior,
            target_state=target_state,
            occurred_at=occurred_at,
            completion_reference=reference,
            request=request,
        )
    )

    observed = service(recorded).execute(request=request)

    assert type(observed) is UpdateReviewAssignmentResult
    result = observed
    before = result.transition.before
    after = result.transition.after
    assert before.etag == request.if_match
    assert before.assignment.lock_version == request.expected_lock_version.value
    assert after.assignment.status is target_state
    assert after.assignment.lock_version == before.assignment.lock_version + 1
    assert after.etag != before.etag
    _assert_preserved(before.assignment, after.assignment)
    assert result.audit.action is RecordedAuditAction.ASSIGNMENT_UPDATE
    assert result.audit.before_snapshot_sha256 == before.snapshot_sha256
    assert result.audit.after_snapshot_sha256 == after.snapshot_sha256
    assert result.audit.request_sha256 == request.request_sha256
    assert result.idempotency.request_sha256 == request.request_sha256
    assert result.canonical_bytes() == result.canonical_bytes()


def test_stale_if_match_cannot_consume_valid_later_exact_script() -> None:
    prior = snapshot(assignment())
    exact = update_request(
        prior,
        target_state=ReviewAssignmentState.IN_PROGRESS,
        occurred_at=STARTED_AT,
    )
    recorded = adapter(
        update_step(
            prior,
            target_state=ReviewAssignmentState.IN_PROGRESS,
            occurred_at=STARTED_AT,
            request=exact,
        )
    )
    stale = UpdateReviewAssignmentRequest(
        correlation_id=exact.correlation_id,
        target=exact.target,
        assignment_id=exact.assignment_id,
        article_version_id=exact.article_version_id,
        target_state=exact.target_state,
        occurred_at=exact.occurred_at,
        expected_lock_version=exact.expected_lock_version,
        if_match=StrongEtag('"ST0901-PR2-LOCAL-STALE"'),
        idempotency_key=IdempotencyKey("ST0901-PR2-LOCAL-STALE-KEY"),
    )

    with pytest.raises(ReviewAssignmentOperationFailure) as captured:
        service(recorded).execute(request=stale)
    assert captured.value.code is ReviewAssignmentOperationFailureCode.NOT_AUTHORIZED
    assert object.__getattribute__(recorded, "_index") == 0

    assert (
        type(service(recorded).execute(request=exact)) is UpdateReviewAssignmentResult
    )
    assert object.__getattribute__(recorded, "_index") == 1


def test_wrong_lock_version_cannot_consume_valid_later_exact_script() -> None:
    prior = snapshot(assignment())
    exact = update_request(
        prior,
        target_state=ReviewAssignmentState.CANCELLED,
        occurred_at=STARTED_AT,
    )
    recorded = adapter(
        update_step(
            prior,
            target_state=ReviewAssignmentState.CANCELLED,
            occurred_at=STARTED_AT,
            request=exact,
        )
    )
    wrong_lock = UpdateReviewAssignmentRequest(
        correlation_id=exact.correlation_id,
        target=exact.target,
        assignment_id=exact.assignment_id,
        article_version_id=exact.article_version_id,
        target_state=exact.target_state,
        occurred_at=exact.occurred_at,
        expected_lock_version=EntityVersion(1),
        if_match=exact.if_match,
        idempotency_key=IdempotencyKey("ST0901-PR2-LOCAL-WRONG-LOCK"),
    )

    with pytest.raises(ReviewAssignmentOperationFailure):
        service(recorded).execute(request=wrong_lock)
    assert object.__getattribute__(recorded, "_index") == 0
    assert (
        type(service(recorded).execute(request=exact)) is UpdateReviewAssignmentResult
    )


@pytest.mark.parametrize(
    "etag",
    (
        'W/"weak"',
        "unquoted",
        "",
        '"contains space"',
    ),
)
def test_missing_equivalent_malformed_or_weak_if_match_is_rejected(etag: str) -> None:
    prior = snapshot(assignment())
    with pytest.raises(PortfolioWorkflowFailure) as captured:
        UpdateReviewAssignmentRequest(
            correlation_id=update_request(
                prior,
                target_state=ReviewAssignmentState.IN_PROGRESS,
                occurred_at=STARTED_AT,
            ).correlation_id,
            target=update_request(
                prior,
                target_state=ReviewAssignmentState.IN_PROGRESS,
                occurred_at=STARTED_AT,
            ).target,
            assignment_id=prior.assignment.assignment_id,
            article_version_id=prior.assignment.article_version_id,
            target_state=ReviewAssignmentState.IN_PROGRESS,
            occurred_at=STARTED_AT,
            expected_lock_version=EntityVersion(0),
            if_match=StrongEtag(etag),
            idempotency_key=IdempotencyKey("ST0901-PR2-LOCAL-BAD-ETAG"),
        )
    assert captured.value.code is PortfolioWorkflowFailureCode.INVALID_ARGUMENT
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


def test_forbidden_transition_is_rejected_before_adapter_construction() -> None:
    initial = assignment()
    prior = snapshot(initial)
    with pytest.raises(ReviewWorkflowFailure):
        update_step(
            prior,
            target_state=ReviewAssignmentState.COMPLETED,
            occurred_at=FINISHED_AT,
            completion_reference=decision_reference(initial),
        )


@pytest.mark.parametrize(
    "mutated",
    (
        lambda value: replace(value, priority=value.priority + 1),
        lambda value: replace(value, assigned_to=value.assigned_by),
        lambda value: replace(value, created_at=STARTED_AT),
    ),
)
def test_changed_creation_coordinates_fail_closed(
    mutated: Callable[[ReviewAssignment], ReviewAssignment],
) -> None:
    initial = assignment(priority=0)
    prior = snapshot(initial)
    after = transition_review_assignment(
        initial,
        ReviewAssignmentState.IN_PROGRESS,
        STARTED_AT,
        None,
    )
    changed = mutated(after)
    valid_step = update_step(
        prior,
        target_state=ReviewAssignmentState.IN_PROGRESS,
        occurred_at=STARTED_AT,
    )
    changed_step = RecordedUpdateReviewAssignmentStep(
        request=valid_step.request,
        grant=valid_step.grant,
        permission_scope=valid_step.permission_scope,
        actor=valid_step.actor,
        reviewer=valid_step.reviewer,
        transition=RecordedAssignmentTransitionV1(
            before=prior,
            after=snapshot(changed),
        ),
        audit_event_id=valid_step.audit_event_id,
        audit_occurred_at=valid_step.audit_occurred_at,
    )
    recorded = adapter(changed_step)
    with pytest.raises(ReviewAssignmentOperationFailure) as captured:
        service(recorded).execute(request=valid_step.request)
    assert (
        captured.value.code
        is ReviewAssignmentOperationFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
    )
    assert object.__getattribute__(recorded, "_index") == 0

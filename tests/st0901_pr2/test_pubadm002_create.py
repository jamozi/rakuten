"""PUBADM-002 recorded-local creation evidence."""

from __future__ import annotations

import pytest

from conftest import (
    ACTOR_ID,
    REVIEWER_ID,
    adapter,
    create_request,
    create_step,
    service,
)
from raos.domain.publishing.review_assignment_operations import (
    CreateReviewAssignmentResult,
    RecordedAuditAction,
    RecordedExecution,
    RecordedReadiness,
    ReviewAssignmentOperation,
    ReviewAssignmentOperationFailure,
    ReviewAssignmentOperationFailureCode,
)
from raos.domain.publishing.review_workflow import ReviewAssignmentState


@pytest.mark.parametrize("priority", [0, 100])
def test_pubadm002_creates_assignment_at_canonical_priority_boundaries(
    priority: int,
) -> None:
    request = create_request(priority=priority)
    recorded = adapter(create_step(request=request))

    observed = service(recorded).execute(request=request)

    assert type(observed) is CreateReviewAssignmentResult
    result = observed
    assignment = result.snapshot.assignment
    assert assignment.assignment_id == request.assignment_id
    assert assignment.article_version_id == request.article_version_id
    assert assignment.assigned_by == ACTOR_ID
    assert assignment.assigned_to == REVIEWER_ID
    assert assignment.priority == priority
    assert assignment.status is ReviewAssignmentState.ASSIGNED
    assert assignment.lock_version == 0
    assert assignment.created_at == request.created_at
    assert result.operation is ReviewAssignmentOperation.CREATE
    assert result.audit.action is RecordedAuditAction.ASSIGNMENT_CREATE
    assert result.audit.actor_id == ACTOR_ID
    assert result.audit.assignment_id == request.assignment_id
    assert result.audit.article_version_id == request.article_version_id
    assert result.audit.correlation_id == request.correlation_id
    assert result.audit.request_sha256 == request.request_sha256
    assert result.audit.before_snapshot_sha256 is None
    assert result.audit.after_snapshot_sha256 == result.snapshot.snapshot_sha256
    assert result.idempotency.operation is ReviewAssignmentOperation.CREATE
    assert result.idempotency.request_sha256 == request.request_sha256
    assert request.idempotency_key.value.encode() not in result.canonical_bytes()
    assert result.canonical_bytes() == result.canonical_bytes()
    assert result.execution is RecordedExecution.RECORDED_ONLY
    assert result.persistence is RecordedExecution.NOT_EXECUTED
    assert result.transaction is RecordedExecution.NOT_EXECUTED
    assert result.audit_atomicity is RecordedExecution.NOT_EXECUTED
    assert result.events is RecordedExecution.NOT_EXECUTED
    assert result.formal_verification is RecordedExecution.NOT_EXECUTED
    assert result.live is RecordedExecution.NOT_EXECUTED
    assert result.staging is RecordedExecution.NOT_EXECUTED
    assert result.release is RecordedExecution.NOT_EXECUTED
    assert result.production is RecordedExecution.NOT_EXECUTED
    assert result.publication is RecordedExecution.NOT_EXECUTED
    assert result.readiness is RecordedReadiness.NOT_READY


def test_create_rejects_recorded_reviewer_substitution_before_exchange() -> None:
    request = create_request()
    step = create_step(request=request)
    recorded = adapter(step)
    authorization = recorded.issue_authorization(request)
    assert authorization.reviewer is not None

    object.__setattr__(
        authorization.reviewer,
        "principal_id",
        ACTOR_ID,
    )
    with pytest.raises(ReviewAssignmentOperationFailure) as captured:
        service(recorded).execute(request=request)

    assert captured.value.code is ReviewAssignmentOperationFailureCode.NOT_AUTHORIZED
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert object.__getattribute__(recorded, "_index") == 0

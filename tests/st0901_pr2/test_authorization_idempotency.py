"""Authorization ordering and deterministic mutation replay evidence."""

from __future__ import annotations

from typing import cast

import pytest

from .support import (
    OTHER_REVIEWER_ID,
    REVIEWER_ID,
    STARTED_AT,
    adapter,
    assignment,
    clone_request_with_priority,
    create_request,
    create_step,
    identity,
    service,
    snapshot,
    update_request,
    update_step,
)
from raos.application.publishing.review_assignment import ReviewAssignmentService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.publishing.review_assignment_operations import (
    CreateReviewAssignmentResult,
    RecordedIdempotencyReceiptV1,
    RecordedReviewerAuthorizationV1,
    RecordedSha256,
    ReviewAssignmentOperationFailure,
    ReviewAssignmentOperationFailureCode,
    ReviewAssignmentRequest,
    ReviewAssignmentResult,
    UpdateReviewAssignmentResult,
)
from raos.domain.publishing.review_workflow import ReviewAssignmentState


class _StaticExchange:
    def __init__(self, result: ReviewAssignmentResult) -> None:
        self._result = result

    def exchange(
        self,
        authorization: RecordedReviewerAuthorizationV1,
        request: ReviewAssignmentRequest,
    ) -> ReviewAssignmentResult:
        del authorization, request
        return self._result


def test_same_operation_key_and_exact_request_returns_identical_retained_result() -> (
    None
):
    request = create_request(priority=0)
    later = create_request(
        suffix=101,
        article_suffix=201,
        idempotency_key="ST0901-PR2-LOCAL-LATER-KEY",
        correlation="ST0901_PR2_RECORDED_LOCAL_V1:LATER",
    )
    recorded = adapter(create_step(request=request), create_step(request=later))
    application = service(recorded)

    first = application.execute(request=request)
    index_after_first = object.__getattribute__(recorded, "_index")
    replay = application.execute(request=request)

    assert type(first) is CreateReviewAssignmentResult
    assert replay is first
    assert replay.canonical_bytes() == first.canonical_bytes()
    assert object.__getattribute__(recorded, "_index") == index_after_first == 1
    assert len(object.__getattribute__(recorded, "_replays")) == 1


def test_same_operation_and_key_changed_hash_fails_without_consuming_later_step() -> (
    None
):
    request = create_request(priority=0)
    later = create_request(
        suffix=101,
        article_suffix=201,
        idempotency_key="ST0901-PR2-LOCAL-LATER-KEY",
        correlation="ST0901_PR2_RECORDED_LOCAL_V1:LATER",
    )
    recorded = adapter(create_step(request=request), create_step(request=later))
    application = service(recorded)
    original = application.execute(request=request)
    changed = clone_request_with_priority(request, 1)

    with pytest.raises(ReviewAssignmentOperationFailure) as service_failure:
        application.execute(request=changed)
    assert (
        service_failure.value.code
        is ReviewAssignmentOperationFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
    )
    assert object.__getattribute__(recorded, "_index") == 1
    assert len(object.__getattribute__(recorded, "_replays")) == 1
    assert cast(CreateReviewAssignmentResult, original).canonical_bytes() == (
        original.canonical_bytes()
    )

    changed_authorization = recorded.issue_authorization(changed)
    with pytest.raises(ReviewAssignmentOperationFailure) as adapter_failure:
        recorded.exchange(changed_authorization, changed)
    assert (
        adapter_failure.value.code
        is ReviewAssignmentOperationFailureCode.IDEMPOTENCY_MISMATCH
    )
    assert adapter_failure.value.__cause__ is None
    assert adapter_failure.value.__context__ is None
    assert object.__getattribute__(recorded, "_index") == 1

    later_result = application.execute(request=later)
    assert type(later_result) is CreateReviewAssignmentResult
    assert object.__getattribute__(recorded, "_index") == 2


def test_process_local_key_cannot_be_silently_reused_by_later_actor_script() -> None:
    key = "ST0901-PR2-LOCAL-CONSERVATIVE-KEY"
    first_request = create_request(
        assigned_to=REVIEWER_ID,
        idempotency_key=key,
    )
    later_request = create_request(
        suffix=101,
        article_suffix=201,
        assigned_to=OTHER_REVIEWER_ID,
        idempotency_key=key,
        correlation="ST0901_PR2_RECORDED_LOCAL_V1:OTHER_ACTOR",
    )
    recorded = adapter(
        create_step(request=first_request),
        create_step(
            request=later_request,
            actor=identity(OTHER_REVIEWER_ID),
            reviewer=identity(OTHER_REVIEWER_ID),
        ),
    )
    application = service(recorded)
    first = application.execute(request=first_request)

    with pytest.raises(ReviewAssignmentOperationFailure) as captured:
        application.execute(request=later_request)

    assert captured.value.code is ReviewAssignmentOperationFailureCode.NOT_AUTHORIZED
    assert object.__getattribute__(recorded, "_index") == 1
    assert len(object.__getattribute__(recorded, "_replays")) == 1
    assert application.execute(request=first_request) is first


def test_create_rejects_internally_valid_receipt_for_wrong_request_key() -> None:
    request = create_request()
    recorded = adapter(create_step(request=request))
    authorization = recorded.issue_authorization(request)
    observed = recorded.exchange(authorization, request)
    assert type(observed) is CreateReviewAssignmentResult
    forged_receipt = RecordedIdempotencyReceiptV1(
        operation=observed.idempotency.operation,
        idempotency_key_sha256=RecordedSha256("0" * 64),
        request_sha256=observed.idempotency.request_sha256,
        recorded_output_sha256=observed.idempotency.recorded_output_sha256,
    )
    forged = CreateReviewAssignmentResult(
        authorization_sha256=observed.authorization_sha256,
        request_sha256=observed.request_sha256,
        snapshot=observed.snapshot,
        audit=observed.audit,
        idempotency=forged_receipt,
    )
    application = ReviewAssignmentService(
        environment=RuntimeEnvironment.CI,
        authorization_source=recorded,
        exchange=_StaticExchange(forged),
    )

    with pytest.raises(ReviewAssignmentOperationFailure) as captured:
        application.execute(request=request)

    assert captured.value.code is ReviewAssignmentOperationFailureCode.OUTCOME_MISMATCH
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


def test_update_rejects_internally_valid_receipt_for_wrong_request_key() -> None:
    prior = snapshot(assignment())
    request = update_request(
        prior,
        target_state=ReviewAssignmentState.IN_PROGRESS,
        occurred_at=STARTED_AT,
    )
    recorded = adapter(
        update_step(
            prior,
            target_state=ReviewAssignmentState.IN_PROGRESS,
            occurred_at=STARTED_AT,
            request=request,
        )
    )
    authorization = recorded.issue_authorization(request)
    observed = recorded.exchange(authorization, request)
    assert type(observed) is UpdateReviewAssignmentResult
    forged_receipt = RecordedIdempotencyReceiptV1(
        operation=observed.idempotency.operation,
        idempotency_key_sha256=RecordedSha256("0" * 64),
        request_sha256=observed.idempotency.request_sha256,
        recorded_output_sha256=observed.idempotency.recorded_output_sha256,
    )
    forged = UpdateReviewAssignmentResult(
        authorization_sha256=observed.authorization_sha256,
        request_sha256=observed.request_sha256,
        transition=observed.transition,
        audit=observed.audit,
        idempotency=forged_receipt,
    )
    application = ReviewAssignmentService(
        environment=RuntimeEnvironment.ENV_DEV,
        authorization_source=recorded,
        exchange=_StaticExchange(forged),
    )

    with pytest.raises(ReviewAssignmentOperationFailure) as captured:
        application.execute(request=request)

    assert captured.value.code is ReviewAssignmentOperationFailureCode.OUTCOME_MISMATCH
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None

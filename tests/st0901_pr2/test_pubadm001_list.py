"""Positive PUBADM-001 projection and authorization sequencing evidence."""

from __future__ import annotations

from typing import cast

import pytest

from .support import (
    ACTOR_ID,
    OTHER_REVIEWER_ID,
    REVIEWER_ID,
    adapter,
    assignment,
    identity,
    list_request,
    list_step,
    service,
    snapshot,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.publishing.review_assignment_operations import (
    ListReviewAssignmentsResult,
    RecordedAssignmentSnapshotV1,
    RecordedExecution,
    RecordedReadiness,
    RecordedReviewerAuthorizationV1,
    ReviewAssignmentOperation,
    ReviewAssignmentOperationFailure,
    ReviewAssignmentOperationFailureCode,
    ReviewAssignmentRequest,
    ReviewAssignmentResult,
)
from raos.ports.review_assignment import RecordedReviewerAuthorizationSource
from raos.domain.publishing.review_workflow import ReviewAssignmentState


def test_pubadm001_returns_deterministic_filtered_ordered_read_only_projection() -> (
    None
):
    first = assignment(suffix=101, article_suffix=201, assigned_to=REVIEWER_ID)
    second = assignment(suffix=102, article_suffix=202, assigned_to=REVIEWER_ID)
    request = list_request(
        assigned_to=REVIEWER_ID,
        status=ReviewAssignmentState.ASSIGNED,
        limit=2,
    )
    recorded = adapter(
        list_step(
            request=request,
            items=(snapshot(first), snapshot(second)),
        )
    )

    result = service(recorded).execute(request=request)

    assert type(result) is ListReviewAssignmentsResult
    listed = result
    assert listed.operation is ReviewAssignmentOperation.LIST
    assert tuple(item.assignment for item in listed.items) == (first, second)
    assert listed.canonical_bytes() == listed.canonical_bytes()
    assert listed.execution is RecordedExecution.RECORDED_ONLY
    assert listed.persistence is RecordedExecution.NOT_EXECUTED
    assert listed.audit_atomicity is RecordedExecution.NOT_EXECUTED
    assert listed.formal_verification is RecordedExecution.NOT_EXECUTED
    assert listed.live is RecordedExecution.NOT_EXECUTED
    assert listed.staging is RecordedExecution.NOT_EXECUTED
    assert listed.release is RecordedExecution.NOT_EXECUTED
    assert listed.production is RecordedExecution.NOT_EXECUTED
    assert listed.publication is RecordedExecution.NOT_EXECUTED
    assert listed.readiness is RecordedReadiness.NOT_READY
    assert not hasattr(listed, "audit")
    assert not hasattr(listed, "idempotency")
    assert object.__getattribute__(recorded, "_replays") == {}
    assert object.__getattribute__(recorded, "_index") == 1


@pytest.mark.parametrize("invalid_shape", ("filter", "limit", "order"))
def test_invalid_list_outcome_does_not_consume_and_can_be_corrected(
    invalid_shape: str,
) -> None:
    first = assignment(suffix=101, article_suffix=201, assigned_to=REVIEWER_ID)
    second = assignment(suffix=102, article_suffix=202, assigned_to=REVIEWER_ID)
    outside_filter = assignment(
        suffix=103,
        article_suffix=203,
        assigned_to=OTHER_REVIEWER_ID,
    )
    request = list_request(
        assigned_to=REVIEWER_ID,
        status=ReviewAssignmentState.ASSIGNED,
        limit=1 if invalid_shape == "limit" else 2,
    )
    invalid_items: tuple[RecordedAssignmentSnapshotV1, ...]
    if invalid_shape == "filter":
        invalid_items = (snapshot(outside_filter),)
    elif invalid_shape == "limit":
        invalid_items = (snapshot(first), snapshot(second))
    else:
        invalid_items = (snapshot(second), snapshot(first))
    step = list_step(request=request, items=invalid_items)
    recorded = adapter(step)
    application = service(recorded)

    with pytest.raises(ReviewAssignmentOperationFailure) as captured:
        application.execute(request=request)

    assert (
        captured.value.code
        is ReviewAssignmentOperationFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
    )
    assert object.__getattribute__(recorded, "_index") == 0
    assert object.__getattribute__(recorded, "_replays") == {}

    object.__setattr__(step, "items", (snapshot(first),))
    corrected = application.execute(request=request)
    assert type(corrected) is ListReviewAssignmentsResult
    assert tuple(item.assignment for item in corrected.items) == (first,)
    assert object.__getattribute__(recorded, "_index") == 1


def test_service_calls_authorization_once_before_exchange() -> None:
    request = list_request()
    inner = adapter(list_step(request=request, items=()))

    class CountingSource:
        calls = 0

        def issue_authorization(
            self, observed: ReviewAssignmentRequest
        ) -> RecordedReviewerAuthorizationV1:
            self.calls += 1
            return inner.issue_authorization(observed)

    class CountingExchange:
        calls = 0

        def exchange(
            self,
            authorization: RecordedReviewerAuthorizationV1,
            observed: ReviewAssignmentRequest,
        ) -> ReviewAssignmentResult:
            self.calls += 1
            return inner.exchange(authorization, observed)

    source = CountingSource()
    exchange = CountingExchange()
    application = service(inner)
    application = type(application)(
        environment=RuntimeEnvironment.CI,
        authorization_source=source,
        exchange=exchange,
    )

    result = application.execute(request=request)

    assert type(result) is ListReviewAssignmentsResult
    assert source.calls == 1
    assert exchange.calls == 1


def test_authorization_failure_never_calls_exchange_or_consumes_script() -> None:
    request = list_request()
    inner = adapter(list_step(request=request, items=()))

    class FailingSource:
        calls = 0

        def issue_authorization(
            self, observed: ReviewAssignmentRequest
        ) -> RecordedReviewerAuthorizationV1:
            del observed
            self.calls += 1
            raise RuntimeError("untrusted collaborator text")

    class CountingExchange:
        calls = 0

        def exchange(
            self,
            authorization: RecordedReviewerAuthorizationV1,
            observed: ReviewAssignmentRequest,
        ) -> ReviewAssignmentResult:
            del authorization, observed
            self.calls += 1
            raise AssertionError("exchange must not be called")

    source = FailingSource()
    exchange = CountingExchange()
    application = type(service(inner))(
        environment=RuntimeEnvironment.ENV_DEV,
        authorization_source=source,
        exchange=exchange,
    )

    with pytest.raises(ReviewAssignmentOperationFailure) as captured:
        application.execute(request=request)

    assert captured.value.code is ReviewAssignmentOperationFailureCode.NOT_AUTHORIZED
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert "untrusted" not in str(captured.value)
    assert source.calls == 1
    assert exchange.calls == 0
    assert object.__getattribute__(inner, "_index") == 0
    assert object.__getattribute__(inner, "_replays") == {}


def test_constructor_accepts_structural_collaborators_and_rejects_malformed() -> None:
    request = list_request()
    recorded = adapter(list_step(request=request, actor=identity(ACTOR_ID)))
    application = type(service(recorded))(
        environment=RuntimeEnvironment.ENV_DEV,
        authorization_source=recorded,
        exchange=recorded,
    )
    assert type(application.execute(request=request)) is ListReviewAssignmentsResult

    with pytest.raises(ReviewAssignmentOperationFailure):
        type(application)(
            environment=RuntimeEnvironment.ENV_DEV,
            authorization_source=cast(
                RecordedReviewerAuthorizationSource,
                object(),
            ),
            exchange=recorded,
        )
    with pytest.raises(ReviewAssignmentOperationFailure):
        type(application)(
            environment=RuntimeEnvironment.PRODUCTION,
            authorization_source=recorded,
            exchange=recorded,
        )

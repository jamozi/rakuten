"""Single-source authorization and deterministic process-local replay."""

from __future__ import annotations

import pytest

from conftest import (
    LATER_DECIDED_AT,
    OTHER_REVIEWER_ID,
    adapter,
    in_progress_assignment,
    request,
    scripted_result,
    service,
    step,
)
from raos.domain.publishing.review_decision_operations import (
    ReviewDecisionOperationFailure,
    ReviewDecisionOperationFailureCode,
)
from raos.domain.publishing.review_workflow import ReviewDecisionKind


def test_same_key_and_exact_request_returns_identical_retained_result() -> None:
    first_request = request()
    first_step = step(value=first_request, decision_suffix=1000, audit_suffix=1050)
    second_request = request(
        assignment=first_request.assignment,
        decision=ReviewDecisionKind.REJECT,
        correlation="ST0901_PR3_RECORDED_LOCAL_V1:NEXT",
        idempotency_key="ST0901-PR3-LOCAL-NEXT-KEY",
    )
    second_step = step(
        value=second_request,
        prior_history=scripted_result(first_step).history,
        decision_suffix=1001,
        decided_at=LATER_DECIDED_AT,
        audit_suffix=1051,
    )
    workflow = service(adapter(first_step, second_step))

    first = workflow.execute(request=first_request)
    replay = workflow.execute(request=first_request)
    second = workflow.execute(request=second_request)

    assert replay is first
    assert replay.canonical_bytes() == first.canonical_bytes()
    assert len(replay.history.records) == 1
    assert len(second.history.records) == 2


def test_same_key_changed_request_fails_without_consuming_next_script() -> None:
    first_request = request()
    first_step = step(value=first_request, decision_suffix=1010, audit_suffix=1060)
    second_request = request(
        assignment=first_request.assignment,
        decision=ReviewDecisionKind.REJECT,
        correlation="ST0901_PR3_RECORDED_LOCAL_V1:NEXT:2",
        idempotency_key="ST0901-PR3-LOCAL-NEXT-KEY-2",
    )
    second_step = step(
        value=second_request,
        prior_history=scripted_result(first_step).history,
        decision_suffix=1011,
        decided_at=LATER_DECIDED_AT,
        audit_suffix=1061,
    )
    exchange = adapter(first_step, second_step)
    workflow = service(exchange)
    first = workflow.execute(request=first_request)
    changed = request(
        assignment=first_request.assignment,
        summary="Changed payload reusing the already recorded raw key.",
        idempotency_key=first_request.idempotency_key.value,
    )
    changed_authorization = exchange.issue_authorization(changed)

    with pytest.raises(ReviewDecisionOperationFailure) as direct:
        exchange.exchange(changed_authorization, changed)
    assert direct.value.code is ReviewDecisionOperationFailureCode.IDEMPOTENCY_MISMATCH

    with pytest.raises(ReviewDecisionOperationFailure) as service_failure:
        workflow.execute(request=changed)
    assert (
        service_failure.value.code
        is ReviewDecisionOperationFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
    )

    second = workflow.execute(request=second_request)
    assert first.history.records == (first.record,)
    assert second.history.records == (first.record, second.record)


def test_global_key_identity_cannot_silently_switch_recorded_actor() -> None:
    first_request = request()
    first_step = step(value=first_request, decision_suffix=1020, audit_suffix=1070)
    next_request = request(
        assignment=first_request.assignment,
        decision=ReviewDecisionKind.REJECT,
        correlation="ST0901_PR3_RECORDED_LOCAL_V1:NEXT:ACTOR",
        idempotency_key="ST0901-PR3-LOCAL-NEXT-ACTOR-KEY",
    )
    next_step = step(
        value=next_request,
        prior_history=scripted_result(first_step).history,
        decision_suffix=1021,
        decided_at=LATER_DECIDED_AT,
        audit_suffix=1071,
    )
    workflow = service(adapter(first_step, next_step))
    workflow.execute(request=first_request)
    substitute_assignment = in_progress_assignment(
        assignment_suffix=100,
        article_suffix=200,
        assigned_to=OTHER_REVIEWER_ID,
    )
    substitute = request(
        assignment=substitute_assignment,
        idempotency_key=first_request.idempotency_key.value,
    )

    with pytest.raises(ReviewDecisionOperationFailure) as captured:
        workflow.execute(request=substitute)
    assert captured.value.code is ReviewDecisionOperationFailureCode.NOT_AUTHORIZED

    assert workflow.execute(request=next_request).record.decision.decision is (
        ReviewDecisionKind.REJECT
    )


def test_raw_idempotency_key_is_absent_from_retained_artifacts() -> None:
    command = request(idempotency_key="ST0901-PR3-RAW-KEY-MUST-NOT-LEAK")
    result = service(adapter(step(value=command))).execute(request=command)
    raw = command.idempotency_key.value

    assert raw.encode() not in result.canonical_bytes()
    assert raw not in repr(result)
    assert raw not in repr(result.audit)
    assert raw not in repr(result.idempotency)

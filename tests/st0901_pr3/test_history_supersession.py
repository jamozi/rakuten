"""Append-only recorded history and prior-only supersession behavior."""

from __future__ import annotations

import pytest

from conftest import (
    LATER_DECIDED_AT,
    adapter,
    in_progress_assignment,
    request,
    scripted_result,
    service,
    step,
    uuid7,
)
from raos.domain.publishing.review_decision_operations import (
    RecordedReviewDecisionHistoryV1,
    ReviewDecisionOperationFailure,
    ReviewDecisionOperationFailureCode,
)
from raos.domain.publishing.review_workflow import ReviewDecisionKind


def test_superseding_append_binds_exact_earlier_record_without_effectiveness() -> None:
    first_request = request()
    first_step = step(value=first_request, decision_suffix=900, audit_suffix=950)
    first_prior = scripted_result(first_step).history
    second_request = request(
        assignment=first_request.assignment,
        decision=ReviewDecisionKind.REJECT,
        summary="Human reviewer rejects the unchanged recorded article version.",
        supersedes_decision_id=scripted_result(first_step).record.decision_id,
        correlation="ST0901_PR3_RECORDED_LOCAL_V1:RECORD:2",
        idempotency_key="ST0901-PR3-LOCAL-DECISION-KEY-2",
    )
    second_step = step(
        value=second_request,
        prior_history=first_prior,
        decision_suffix=901,
        decided_at=LATER_DECIDED_AT,
        audit_suffix=951,
    )
    exchange = adapter(first_step, second_step)
    workflow = service(exchange)

    first = workflow.execute(request=first_request)
    first_bytes = first.record.canonical_bytes()
    second = workflow.execute(request=second_request)

    assert second.history.records == (first.record, second.record)
    assert second.record.supersedes_decision_id == first.record.decision_id
    assert second.record.superseded_record_sha256 == first.record.record_sha256
    assert first.record.canonical_bytes() == first_bytes
    assert first.history.records == (first.record,)
    assert not hasattr(second.history, "effective_decision")
    assert not hasattr(second.history, "latest_decision")
    assert not hasattr(second.history, "tail")


def test_same_prior_can_be_referenced_again_without_winner_semantics() -> None:
    first_request = request()
    first_step = step(value=first_request, decision_suffix=910, audit_suffix=960)
    first_result = scripted_result(first_step)
    second_request = request(
        assignment=first_request.assignment,
        supersedes_decision_id=first_result.record.decision_id,
        summary="First recorded follow-up requests another human correction.",
        correlation="ST0901_PR3_RECORDED_LOCAL_V1:BRANCH:2",
        idempotency_key="ST0901-PR3-LOCAL-BRANCH-KEY-2",
    )
    second_step = step(
        value=second_request,
        prior_history=first_result.history,
        decision_suffix=911,
        decided_at=LATER_DECIDED_AT,
        audit_suffix=961,
    )
    second_result = scripted_result(second_step)
    third_request = request(
        assignment=first_request.assignment,
        decision=ReviewDecisionKind.REJECT,
        supersedes_decision_id=first_result.record.decision_id,
        summary="Independent recorded follow-up rejects the same prior record.",
        correlation="ST0901_PR3_RECORDED_LOCAL_V1:BRANCH:3",
        idempotency_key="ST0901-PR3-LOCAL-BRANCH-KEY-3",
    )
    third_step = step(
        value=third_request,
        prior_history=second_result.history,
        decision_suffix=912,
        decided_at=LATER_DECIDED_AT,
        audit_suffix=962,
    )
    workflow = service(adapter(first_step, second_step, third_step))

    first = workflow.execute(request=first_request)
    second = workflow.execute(request=second_request)
    third = workflow.execute(request=third_request)

    assert second.record.supersedes_decision_id == first.record.decision_id
    assert third.record.supersedes_decision_id == first.record.decision_id
    assert third.history.records == (first.record, second.record, third.record)


def test_append_without_supersedes_remains_a_recorded_fact_only() -> None:
    first_request = request()
    first_step = step(value=first_request, decision_suffix=920, audit_suffix=970)
    second_request = request(
        assignment=first_request.assignment,
        decision=ReviewDecisionKind.REJECT,
        summary="A later independent negative review decision is recorded.",
        correlation="ST0901_PR3_RECORDED_LOCAL_V1:INDEPENDENT:2",
        idempotency_key="ST0901-PR3-LOCAL-INDEPENDENT-KEY-2",
    )
    second_step = step(
        value=second_request,
        prior_history=scripted_result(first_step).history,
        decision_suffix=921,
        decided_at=LATER_DECIDED_AT,
        audit_suffix=971,
    )
    workflow = service(adapter(first_step, second_step))

    workflow.execute(request=first_request)
    second = workflow.execute(request=second_request)

    assert second.record.supersedes_decision_id is None
    assert second.record.superseded_record_sha256 is None
    assert len(second.history.records) == 2


def test_missing_self_forward_duplicate_and_cross_coordinate_prior_fail_closed() -> (
    None
):
    first_request = request()
    first_step = step(value=first_request, decision_suffix=930, audit_suffix=980)
    first_result = scripted_result(first_step)

    missing = request(
        assignment=first_request.assignment,
        supersedes_decision_id=type(first_result.record.decision_id)(uuid7(999)),
        idempotency_key="ST0901-PR3-LOCAL-MISSING-KEY",
    )
    with pytest.raises(ReviewDecisionOperationFailure) as missing_failure:
        step(value=missing, prior_history=first_result.history, decision_suffix=931)
    assert (
        missing_failure.value.code
        is ReviewDecisionOperationFailureCode.HISTORY_MISMATCH
    )

    self_reference = request(
        assignment=first_request.assignment,
        supersedes_decision_id=first_result.record.decision_id,
        idempotency_key="ST0901-PR3-LOCAL-SELF-KEY",
    )
    with pytest.raises(ReviewDecisionOperationFailure) as duplicate_failure:
        step(
            value=self_reference,
            prior_history=first_result.history,
            decision_suffix=930,
        )
    assert (
        duplicate_failure.value.code
        is ReviewDecisionOperationFailureCode.HISTORY_MISMATCH
    )

    other_assignment = in_progress_assignment(
        assignment_suffix=333,
        article_suffix=444,
    )
    cross_request = request(
        assignment=other_assignment,
        supersedes_decision_id=first_result.record.decision_id,
        idempotency_key="ST0901-PR3-LOCAL-CROSS-KEY",
    )
    with pytest.raises(ReviewDecisionOperationFailure) as cross_failure:
        step(value=cross_request, prior_history=first_result.history)
    assert (
        cross_failure.value.code is ReviewDecisionOperationFailureCode.HISTORY_MISMATCH
    )


def test_history_reorder_or_removal_cannot_preserve_supersession() -> None:
    first_request = request()
    first_step = step(value=first_request, decision_suffix=940, audit_suffix=990)
    first_result = scripted_result(first_step)
    second_request = request(
        assignment=first_request.assignment,
        supersedes_decision_id=first_result.record.decision_id,
        idempotency_key="ST0901-PR3-LOCAL-HISTORY-KEY-2",
    )
    second_step = step(
        value=second_request,
        prior_history=first_result.history,
        decision_suffix=941,
        decided_at=LATER_DECIDED_AT,
        audit_suffix=991,
    )
    complete = scripted_result(second_step).history

    for records in ((complete.records[1],), tuple(reversed(complete.records))):
        with pytest.raises(ReviewDecisionOperationFailure) as captured:
            RecordedReviewDecisionHistoryV1(
                assignment_id=complete.assignment_id,
                article_version_id=complete.article_version_id,
                records=records,
            )
        assert (
            captured.value.code is ReviewDecisionOperationFailureCode.HISTORY_MISMATCH
        )

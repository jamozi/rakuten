"""Focused deterministic behavior tests for the bounded ST-1404 seam."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta
from typing import cast
from uuid import UUID

import pytest

from conftest import (
    CONSUMER_NAME,
    EVENT_ID,
    HANDLER_VERSION,
    IDENTITY_NAMESPACE,
    JOB_ID,
    NOW,
    PAYLOAD_FINGERPRINT,
    QUEUE_NAME,
    RESULT_FINGERPRINT,
    make_adapter,
    make_job,
    make_outbox,
    make_service,
    retryable,
    success,
    terminal,
)
from raos.adapters.queue_fake import QueueFake
from raos.adapters.recorded_job_runtime import RecordedJobRuntimeAdapter
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ops.job_runtime import (
    ALLOWED_JOB_TRANSITIONS,
    AttemptState,
    CompletionCommit,
    DispatchOutcome,
    DispatchStepResult,
    Fingerprint,
    HandlerOutcome,
    InboxIdentity,
    InboxState,
    JobRuntimeFailure,
    JobState,
    JobTransition,
    OutboxState,
    RecordedHandlerResult,
    RecordedJobInvocation,
    RecordedJobMessage,
    RuntimeFailureCode,
    WorkOutcome,
    WorkStepResult,
)
from raos.ports.job_runtime import RecordedJobHandler
from raos.ports.queue import QueueDelivery, QueueMessage, QueuePort


class _DelegatingQueue(QueuePort[RecordedJobMessage]):
    def __init__(self, inner: QueueFake[RecordedJobMessage]) -> None:
        self.inner = inner

    def send(self, message: QueueMessage[RecordedJobMessage]) -> None:
        self.inner.send(message)

    def receive(
        self, queue_name: str, *, lease: timedelta
    ) -> QueueDelivery[RecordedJobMessage] | None:
        return self.inner.receive(queue_name, lease=lease)

    def acknowledge(self, receipt_handle: str) -> None:
        self.inner.acknowledge(receipt_handle)

    def retry(self, receipt_handle: str, *, delay: timedelta = timedelta(0)) -> None:
        self.inner.retry(receipt_handle, delay=delay)

    def extend_lease(
        self, receipt_handle: str, *, lease: timedelta
    ) -> QueueDelivery[RecordedJobMessage]:
        return self.inner.extend_lease(receipt_handle, lease=lease)


class _AmbiguousFirstSendQueue(_DelegatingQueue):
    def __init__(self, inner: QueueFake[RecordedJobMessage]) -> None:
        super().__init__(inner)
        self.send_calls = 0
        self.sent_messages: list[QueueMessage[RecordedJobMessage]] = []

    def send(self, message: QueueMessage[RecordedJobMessage]) -> None:
        self.send_calls += 1
        self.sent_messages.append(message)
        self.inner.send(message)
        if self.send_calls == 1:
            raise RuntimeError("synthetic ambiguous send canary")


class _AlwaysFailSendQueue(_DelegatingQueue):
    def send(self, message: QueueMessage[RecordedJobMessage]) -> None:
        del message
        raise RuntimeError("synthetic send failure canary")


class _FailFirstAckQueue(_DelegatingQueue):
    def __init__(self, inner: QueueFake[RecordedJobMessage]) -> None:
        super().__init__(inner)
        self.ack_calls = 0

    def acknowledge(self, receipt_handle: str) -> None:
        self.ack_calls += 1
        if self.ack_calls == 1:
            raise RuntimeError("synthetic ack failure canary")
        self.inner.acknowledge(receipt_handle)


class _StaleOnRecheckQueue(_DelegatingQueue):
    def extend_lease(
        self, receipt_handle: str, *, lease: timedelta
    ) -> QueueDelivery[RecordedJobMessage]:
        del lease
        self.inner.retry(receipt_handle)
        raise RuntimeError("synthetic stale receipt canary")


class _FailRetryReleaseQueue(_DelegatingQueue):
    def retry(self, receipt_handle: str, *, delay: timedelta = timedelta(0)) -> None:
        del receipt_handle, delay
        raise RuntimeError("synthetic retry release failure canary")


class _ExplodingHandler(RecordedJobHandler):
    def __init__(self, canary: str) -> None:
        self._canary = canary
        self.calls = 0

    def handle(self, invocation: RecordedJobInvocation) -> RecordedHandlerResult:
        self.calls += 1
        raise RuntimeError(f"{self._canary}:{invocation.payload_fingerprint.value}")


class _CancellingHandler(RecordedJobHandler):
    def __init__(self, adapter: RecordedJobRuntimeAdapter) -> None:
        self._adapter = adapter
        self.calls = 0

    def handle(self, invocation: RecordedJobInvocation) -> RecordedHandlerResult:
        self.calls += 1
        self._adapter.request_cancel(
            job_id=invocation.job_id,
            requested_at=invocation.started_at,
        )
        return success(completed_at=invocation.started_at)


def _queue(port: QueuePort[RecordedJobMessage]) -> QueueFake[RecordedJobMessage]:
    return cast(QueueFake[RecordedJobMessage], port)


def _assert_failure(
    code: RuntimeFailureCode, operation: Callable[[], object]
) -> JobRuntimeFailure:
    with pytest.raises(JobRuntimeFailure) as captured:
        operation()
    assert captured.value.code is code
    return captured.value


def test_exact_installed_state_sets_and_all_job_edges_are_closed() -> None:
    assert {state.value for state in JobState} == {
        "REQUESTED",
        "QUEUED",
        "RUNNING",
        "SUCCEEDED",
        "FAILED_RETRYABLE",
        "RETRY_SCHEDULED",
        "FAILED_TERMINAL",
        "QUARANTINED",
        "CANCELLED",
        "EXPIRED",
    }
    assert {state.value for state in AttemptState} == {
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
        "TIMED_OUT",
    }
    assert {state.value for state in OutboxState} == {
        "PENDING",
        "DISPATCHING",
        "PUBLISHED",
        "FAILED",
        "DEAD",
    }
    assert {state.value for state in InboxState} == {
        "PROCESSING",
        "PROCESSED",
        "FAILED",
        "IGNORED",
    }

    expected = {
        (JobState.REQUESTED, JobState.QUEUED),
        (JobState.REQUESTED, JobState.CANCELLED),
        (JobState.REQUESTED, JobState.EXPIRED),
        (JobState.QUEUED, JobState.RUNNING),
        (JobState.QUEUED, JobState.CANCELLED),
        (JobState.QUEUED, JobState.EXPIRED),
        (JobState.RUNNING, JobState.SUCCEEDED),
        (JobState.RUNNING, JobState.FAILED_RETRYABLE),
        (JobState.RUNNING, JobState.FAILED_TERMINAL),
        (JobState.RUNNING, JobState.QUARANTINED),
        (JobState.RUNNING, JobState.CANCELLED),
        (JobState.RUNNING, JobState.EXPIRED),
        (JobState.FAILED_RETRYABLE, JobState.RETRY_SCHEDULED),
        (JobState.FAILED_RETRYABLE, JobState.FAILED_TERMINAL),
        (JobState.RETRY_SCHEDULED, JobState.QUEUED),
        (JobState.QUARANTINED, JobState.QUEUED),
    }
    all_pairs = {(source, target) for source in JobState for target in JobState}
    assert ALLOWED_JOB_TRANSITIONS == expected
    assert len(ALLOWED_JOB_TRANSITIONS) == 16
    assert len(all_pairs - ALLOWED_JOB_TRANSITIONS) == 84
    assert not {(state, state) for state in JobState} & ALLOWED_JOB_TRANSITIONS
    assert (JobState.RETRY_SCHEDULED, JobState.EXPIRED) not in ALLOWED_JOB_TRANSITIONS
    assert (JobState.FAILED_RETRYABLE, JobState.EXPIRED) not in ALLOWED_JOB_TRANSITIONS


def test_dispatch_and_success_commit_exact_versions_and_redacted_records() -> None:
    adapter = make_adapter()
    service, queue_port = make_service(adapter=adapter)
    queue = _queue(queue_port)

    dispatched = service.dispatch_once(now=NOW)
    assert dispatched.outcome is DispatchOutcome.PUBLISHED
    assert dispatched.expected_job_version == 0
    assert dispatched.post_job_version == 1
    assert dispatched.publish_attempt == 1
    assert queue.pending_message_ids(QUEUE_NAME) == (str(EVENT_ID),)
    assert adapter.job(JOB_ID).state is JobState.QUEUED

    worked = service.work_once(QUEUE_NAME, now=NOW)
    assert worked.outcome is WorkOutcome.SUCCEEDED
    assert worked.expected_job_version == 2
    assert worked.post_job_version == 3
    assert worked.attempt_number == 1
    assert worked.delivery_attempt == 1
    job = adapter.job(JOB_ID)
    assert job.state is JobState.SUCCEEDED
    assert job.attempt_count == 1
    assert job.result_fingerprint == RESULT_FINGERPRINT
    assert adapter.outbox(EVENT_ID).publish_attempts == 1
    attempts = adapter.attempts_for(JOB_ID)
    assert len(attempts) == 1
    assert attempts[0].state is AttemptState.SUCCEEDED
    identity = InboxIdentity(CONSUMER_NAME, HANDLER_VERSION, EVENT_ID)
    inbox = adapter.inbox(identity)
    assert inbox is not None
    assert inbox.state is InboxState.PROCESSED
    assert inbox.result_fingerprint == RESULT_FINGERPRINT
    assert queue.pending_message_ids(QUEUE_NAME) == ()
    assert queue.inflight_count(QUEUE_NAME) == 0

    diagnostics = " ".join(
        (
            repr(job),
            str(job),
            repr(attempts[0]),
            repr(inbox),
            repr(worked),
        )
    )
    assert PAYLOAD_FINGERPRINT.value not in diagnostics
    assert RESULT_FINGERPRINT.value not in diagnostics
    assert "<redacted-job-runtime>" in diagnostics
    with pytest.raises(AttributeError):
        setattr(job, "state", JobState.REQUESTED)


def test_due_outbox_selection_is_deterministic() -> None:
    other_job_id = UUID("00000000-0000-0000-0000-000000001405")
    other_event_id = UUID("00000000-0000-0000-0000-000000002405")
    adapter = make_adapter(
        jobs=(make_job(), make_job(job_id=other_job_id)),
        outboxes=(
            make_outbox(available_at=NOW),
            make_outbox(
                event_id=other_event_id,
                job_id=other_job_id,
                available_at=NOW - timedelta(seconds=1),
            ),
        ),
    )
    service, _ = make_service(adapter=adapter)

    result = service.dispatch_once(now=NOW)

    assert result.event_id == other_event_id
    assert adapter.outbox(other_event_id).state is OutboxState.PUBLISHED
    assert adapter.outbox(EVENT_ID).state is OutboxState.PENDING


def test_ambiguous_send_retries_the_same_logical_message_identity() -> None:
    adapter = make_adapter()
    inner = QueueFake[RecordedJobMessage](start_at=NOW)
    queue = _AmbiguousFirstSendQueue(inner)
    service, _ = make_service(
        adapter=adapter,
        queue=queue,
        outbox_retry_schedule=(timedelta(0),),
    )

    failed = service.dispatch_once(now=NOW)
    assert failed.outcome is DispatchOutcome.SEND_RETRY_SCHEDULED
    assert adapter.job(JOB_ID).state is JobState.REQUESTED
    assert adapter.outbox(EVENT_ID).state is OutboxState.FAILED
    published = service.dispatch_once(now=NOW)
    assert published.outcome is DispatchOutcome.PUBLISHED
    assert published.publish_attempt == 2
    assert inner.pending_message_ids(QUEUE_NAME) == (str(EVENT_ID), str(EVENT_ID))

    first = service.work_once(QUEUE_NAME, now=NOW)
    second = service.work_once(QUEUE_NAME, now=NOW)
    assert first.outcome is WorkOutcome.SUCCEEDED
    assert second.outcome is WorkOutcome.DUPLICATE_ACKNOWLEDGED
    assert len(adapter.invocations()) == 1
    assert adapter.outbox(EVENT_ID).publish_attempts == 2
    assert adapter.job(JOB_ID).attempt_count == 1


def test_ambiguous_send_retry_preserves_the_whole_message_after_cancel() -> None:
    adapter = make_adapter()
    inner = QueueFake[RecordedJobMessage](start_at=NOW)
    queue = _AmbiguousFirstSendQueue(inner)
    service, _ = make_service(
        adapter=adapter,
        queue=queue,
        outbox_retry_schedule=(timedelta(0),),
    )

    failed = service.dispatch_once(now=NOW)
    adapter.request_cancel(job_id=JOB_ID, requested_at=NOW)
    published = service.dispatch_once(now=NOW)

    assert failed.expected_job_version == 0
    assert published.expected_job_version == 1
    assert published.post_job_version == 2
    assert queue.sent_messages[0] == queue.sent_messages[1]
    assert queue.sent_messages[0].payload.expected_job_version == 0

    worked = service.work_once(QUEUE_NAME, now=NOW)
    duplicate = service.work_once(QUEUE_NAME, now=NOW)
    assert worked.outcome is WorkOutcome.CANCELLED
    assert duplicate.outcome is WorkOutcome.DUPLICATE_ACKNOWLEDGED
    assert adapter.invocations() == ()


def test_finite_outbox_retry_schedule_ends_at_outbox_dead_only() -> None:
    adapter = make_adapter()
    inner = QueueFake[RecordedJobMessage](start_at=NOW)
    queue = _AlwaysFailSendQueue(inner)
    service, _ = make_service(
        adapter=adapter,
        queue=queue,
        outbox_retry_schedule=(timedelta(0),),
    )

    first = service.dispatch_once(now=NOW)
    second = service.dispatch_once(now=NOW)

    assert first.outcome is DispatchOutcome.SEND_RETRY_SCHEDULED
    assert second.outcome is DispatchOutcome.OUTBOX_DEAD
    assert adapter.outbox(EVENT_ID).state is OutboxState.DEAD
    assert adapter.outbox(EVENT_ID).publish_attempts == 2
    assert adapter.job(JOB_ID).state is JobState.REQUESTED
    assert inner.dead_letters(QUEUE_NAME) == ()


def test_stale_dispatch_job_version_is_fenced() -> None:
    adapter = make_adapter()
    claim = adapter.claim_due_outbox(now=NOW)
    assert claim is not None
    adapter.request_cancel(job_id=JOB_ID, requested_at=NOW)

    _assert_failure(
        RuntimeFailureCode.STALE_VERSION,
        lambda: adapter.publish_succeeded(claim=claim, published_at=NOW),
    )
    assert adapter.job(JOB_ID).state is JobState.REQUESTED


def test_processed_duplicate_is_acknowledged_without_handler_reexecution() -> None:
    adapter = make_adapter()
    service, queue_port = make_service(adapter=adapter)
    queue = _queue(queue_port)
    service.dispatch_once(now=NOW)
    queue.inject_duplicate(str(EVENT_ID))

    assert service.work_once(QUEUE_NAME, now=NOW).outcome is WorkOutcome.SUCCEEDED
    duplicate = service.work_once(QUEUE_NAME, now=NOW)

    assert duplicate.outcome is WorkOutcome.DUPLICATE_ACKNOWLEDGED
    assert len(adapter.invocations()) == 1
    assert len(adapter.attempts_for(JOB_ID)) == 1


def test_ack_failure_replay_does_not_invoke_handler_twice() -> None:
    adapter = make_adapter()
    inner = QueueFake[RecordedJobMessage](start_at=NOW)
    queue = _FailFirstAckQueue(inner)
    service, _ = make_service(adapter=adapter, queue=queue)
    service.dispatch_once(now=NOW)

    first = service.work_once(QUEUE_NAME, now=NOW)
    assert first.outcome is WorkOutcome.ACK_FAILED
    assert adapter.job(JOB_ID).state is JobState.SUCCEEDED
    assert len(adapter.invocations()) == 1

    inner.advance(timedelta(seconds=30))
    replay = service.work_once(QUEUE_NAME, now=NOW + timedelta(seconds=30))
    assert replay.outcome is WorkOutcome.DUPLICATE_ACKNOWLEDGED
    assert replay.delivery_attempt == 2
    assert len(adapter.invocations()) == 1
    assert len(adapter.attempts_for(JOB_ID)) == 1


def test_retry_path_uses_only_exact_edges_and_independent_counters() -> None:
    adapter = make_adapter(
        handler_results=(
            retryable(completed_at=NOW),
            success(completed_at=NOW + timedelta(seconds=5)),
        )
    )
    service, queue_port = make_service(adapter=adapter)
    queue = _queue(queue_port)
    service.dispatch_once(now=NOW)

    first = service.work_once(QUEUE_NAME, now=NOW)
    assert first.outcome is WorkOutcome.RETRY_SCHEDULED
    assert adapter.job(JOB_ID).state is JobState.RETRY_SCHEDULED
    assert adapter.job(JOB_ID).attempt_count == 1
    assert adapter.outbox(EVENT_ID).publish_attempts == 1
    first_attempt = adapter.attempts_for(JOB_ID)[0]
    assert first_attempt.state is AttemptState.FAILED
    assert first_attempt.retry_after_at == NOW + timedelta(seconds=5)

    queue.advance(timedelta(seconds=5))
    second = service.work_once(QUEUE_NAME, now=NOW + timedelta(seconds=5))
    assert second.outcome is WorkOutcome.SUCCEEDED
    assert second.delivery_attempt == 2
    assert second.attempt_number == 2
    assert adapter.job(JOB_ID).attempt_count == 2
    assert adapter.outbox(EVENT_ID).publish_attempts == 1
    assert [item.attempt_number for item in adapter.attempts_for(JOB_ID)] == [1, 2]
    assert [
        (item.from_state, item.to_state) for item in adapter.transitions_for(JOB_ID)
    ] == [
        (JobState.REQUESTED, JobState.QUEUED),
        (JobState.QUEUED, JobState.RUNNING),
        (JobState.RUNNING, JobState.FAILED_RETRYABLE),
        (JobState.FAILED_RETRYABLE, JobState.RETRY_SCHEDULED),
        (JobState.RETRY_SCHEDULED, JobState.QUEUED),
        (JobState.QUEUED, JobState.RUNNING),
        (JobState.RUNNING, JobState.SUCCEEDED),
    ]


def test_retry_budget_exhaustion_uses_failed_retryable_then_terminal() -> None:
    adapter = make_adapter(
        jobs=(make_job(max_attempts=1),),
        handler_results=(retryable(),),
    )
    service, _ = make_service(adapter=adapter)
    service.dispatch_once(now=NOW)

    result = service.work_once(QUEUE_NAME, now=NOW)

    assert result.outcome is WorkOutcome.FAILED_TERMINAL
    assert adapter.job(JOB_ID).state is JobState.FAILED_TERMINAL
    assert [
        (item.from_state, item.to_state) for item in adapter.transitions_for(JOB_ID)
    ][-2:] == [
        (JobState.RUNNING, JobState.FAILED_RETRYABLE),
        (JobState.FAILED_RETRYABLE, JobState.FAILED_TERMINAL),
    ]


def test_queue_fake_dlq_does_not_invent_a_job_terminal_transition() -> None:
    adapter = make_adapter(
        jobs=(make_job(max_attempts=3, delivery_max_attempts=1),),
        handler_results=(retryable(),),
    )
    service, queue_port = make_service(adapter=adapter)
    queue = _queue(queue_port)
    service.dispatch_once(now=NOW)

    result = service.work_once(QUEUE_NAME, now=NOW)

    assert result.outcome is WorkOutcome.RETRY_SCHEDULED
    assert len(queue.dead_letters(QUEUE_NAME)) == 1
    assert adapter.job(JOB_ID).state is JobState.RETRY_SCHEDULED
    assert adapter.transitions_for(JOB_ID)[-1].to_state is JobState.RETRY_SCHEDULED


def test_queue_retry_failure_cannot_roll_back_the_recorded_retry_result() -> None:
    adapter = make_adapter(handler_results=(retryable(),))
    inner = QueueFake[RecordedJobMessage](start_at=NOW)
    queue = _FailRetryReleaseQueue(inner)
    service, _ = make_service(adapter=adapter, queue=queue)
    service.dispatch_once(now=NOW)

    result = service.work_once(QUEUE_NAME, now=NOW)

    assert result.outcome is WorkOutcome.RETRY_RELEASE_FAILED
    assert result.failure_code is RuntimeFailureCode.QUEUE_RETRY_FAILED
    assert adapter.job(JOB_ID).state is JobState.RETRY_SCHEDULED
    assert adapter.attempts_for(JOB_ID)[0].state is AttemptState.FAILED
    inbox = adapter.inbox(InboxIdentity(CONSUMER_NAME, HANDLER_VERSION, EVENT_ID))
    assert inbox is not None and inbox.state is InboxState.FAILED
    assert inner.inflight_count(QUEUE_NAME) == 1


def test_cancel_before_handler_is_terminal_without_incrementing_attempts() -> None:
    adapter = make_adapter()
    service, _ = make_service(adapter=adapter)
    service.dispatch_once(now=NOW)
    adapter.request_cancel(job_id=JOB_ID, requested_at=NOW)

    result = service.work_once(QUEUE_NAME, now=NOW)

    assert result.outcome is WorkOutcome.CANCELLED
    assert adapter.job(JOB_ID).state is JobState.CANCELLED
    assert adapter.job(JOB_ID).attempt_count == 0
    assert adapter.attempts_for(JOB_ID) == ()
    assert adapter.invocations() == ()
    inbox = adapter.inbox(InboxIdentity(CONSUMER_NAME, HANDLER_VERSION, EVENT_ID))
    assert inbox is not None and inbox.state is InboxState.IGNORED


def test_deadline_before_handler_expires_without_incrementing_attempts() -> None:
    adapter = make_adapter(
        jobs=(make_job(deadline_at=NOW + timedelta(seconds=1)),),
    )
    service, queue_port = make_service(adapter=adapter)
    queue = _queue(queue_port)
    service.dispatch_once(now=NOW)
    queue.advance(timedelta(seconds=1))

    result = service.work_once(QUEUE_NAME, now=NOW + timedelta(seconds=1))

    assert result.outcome is WorkOutcome.EXPIRED
    assert adapter.job(JOB_ID).state is JobState.EXPIRED
    assert adapter.job(JOB_ID).attempt_count == 0
    assert adapter.invocations() == ()


def test_cancel_requested_during_handler_wins_before_success_commit() -> None:
    adapter = make_adapter(handler_results=())
    handler = _CancellingHandler(adapter)
    service, _ = make_service(adapter=adapter, handler=handler)
    service.dispatch_once(now=NOW)

    result = service.work_once(QUEUE_NAME, now=NOW)

    assert result.outcome is WorkOutcome.CANCELLED
    assert adapter.job(JOB_ID).state is JobState.CANCELLED
    assert handler.calls == 1
    attempt = adapter.attempts_for(JOB_ID)[0]
    assert attempt.state is AttemptState.CANCELLED
    assert adapter.transitions_for(JOB_ID)[-1].to_state is JobState.CANCELLED


def test_deadline_at_handler_completion_wins_before_success_commit() -> None:
    deadline = NOW + timedelta(seconds=5)
    adapter = make_adapter(
        jobs=(make_job(deadline_at=deadline),),
        handler_results=(success(completed_at=deadline),),
    )
    service, _ = make_service(adapter=adapter)
    service.dispatch_once(now=NOW)

    result = service.work_once(QUEUE_NAME, now=NOW)

    assert result.outcome is WorkOutcome.EXPIRED
    assert adapter.job(JOB_ID).state is JobState.EXPIRED
    assert adapter.attempts_for(JOB_ID)[0].state is AttemptState.TIMED_OUT
    inbox = adapter.inbox(InboxIdentity(CONSUMER_NAME, HANDLER_VERSION, EVENT_ID))
    assert inbox is not None and inbox.state is InboxState.IGNORED


def test_stale_lease_cannot_commit_and_processing_is_never_taken_over() -> None:
    lease_end = NOW + timedelta(seconds=30)
    adapter = make_adapter(
        handler_results=(
            success(completed_at=lease_end),
            success(completed_at=lease_end),
        ),
    )
    service, queue_port = make_service(adapter=adapter)
    queue = _queue(queue_port)
    service.dispatch_once(now=NOW)

    stale = service.work_once(QUEUE_NAME, now=NOW)
    assert stale.outcome is WorkOutcome.LEASE_STALE
    assert adapter.job(JOB_ID).state is JobState.RUNNING
    assert adapter.attempts_for(JOB_ID)[0].state is AttemptState.RUNNING
    inbox = adapter.inbox(InboxIdentity(CONSUMER_NAME, HANDLER_VERSION, EVENT_ID))
    assert inbox is not None and inbox.state is InboxState.PROCESSING
    assert len(adapter.invocations()) == 1

    queue.advance(timedelta(seconds=30))
    replay = service.work_once(QUEUE_NAME, now=lease_end)
    assert replay.outcome is WorkOutcome.PROCESSING_HELD
    assert len(adapter.invocations()) == 1
    assert adapter.job(JOB_ID).state is JobState.RUNNING


def test_stale_receipt_recheck_cannot_commit_handler_result() -> None:
    adapter = make_adapter()
    inner = QueueFake[RecordedJobMessage](start_at=NOW)
    queue = _StaleOnRecheckQueue(inner)
    service, _ = make_service(adapter=adapter, queue=queue)
    service.dispatch_once(now=NOW)

    result = service.work_once(QUEUE_NAME, now=NOW)

    assert result.outcome is WorkOutcome.LEASE_STALE
    assert adapter.job(JOB_ID).state is JobState.RUNNING
    assert adapter.attempts_for(JOB_ID)[0].state is AttemptState.RUNNING
    inbox = adapter.inbox(InboxIdentity(CONSUMER_NAME, HANDLER_VERSION, EVENT_ID))
    assert inbox is not None and inbox.state is InboxState.PROCESSING
    assert len(adapter.invocations()) == 1


def test_tampered_work_claim_cannot_commit_or_misreport_attempt_number() -> None:
    adapter = make_adapter()
    dispatch_claim = adapter.claim_due_outbox(now=NOW)
    assert dispatch_claim is not None
    adapter.publish_succeeded(claim=dispatch_claim, published_at=NOW)
    message = RecordedJobMessage(
        event_id=dispatch_claim.event_id,
        job_id=dispatch_claim.job_id,
        expected_job_version=dispatch_claim.message_expected_job_version,
        job_schema_version=dispatch_claim.job_schema_version,
        payload_fingerprint=dispatch_claim.payload_fingerprint,
        deadline_at=dispatch_claim.deadline_at,
    )
    start = adapter.begin_delivery(
        message=message,
        consumer_name=CONSUMER_NAME,
        handler_version=HANDLER_VERSION,
        delivery_attempt=1,
        leased_until=NOW + timedelta(seconds=30),
        job_lease_until=NOW + timedelta(seconds=30),
        now=NOW,
    )
    assert start.claim is not None
    tampered = replace(start.claim, attempt_number=7)

    _assert_failure(
        RuntimeFailureCode.STATE_CONFLICT,
        lambda: adapter.complete_delivery(
            claim=tampered,
            result=success(),
            retry_at=None,
        ),
    )
    assert adapter.job(JOB_ID).state is JobState.RUNNING
    assert adapter.attempts_for(JOB_ID)[0].state is AttemptState.RUNNING
    inbox = adapter.inbox(InboxIdentity(CONSUMER_NAME, HANDLER_VERSION, EVENT_ID))
    assert inbox is not None and inbox.state is InboxState.PROCESSING


def test_retry_state_past_deadline_is_held_without_an_expiry_edge() -> None:
    deadline = NOW + timedelta(seconds=3)
    adapter = make_adapter(
        jobs=(make_job(deadline_at=deadline),),
        handler_results=(retryable(),),
    )
    service, queue_port = make_service(adapter=adapter)
    queue = _queue(queue_port)
    service.dispatch_once(now=NOW)
    assert service.work_once(QUEUE_NAME, now=NOW).outcome is WorkOutcome.RETRY_SCHEDULED

    queue.advance(timedelta(seconds=5))
    held = service.work_once(QUEUE_NAME, now=NOW + timedelta(seconds=5))

    assert held.outcome is WorkOutcome.RETRY_STATE_HELD
    assert adapter.job(JOB_ID).state is JobState.RETRY_SCHEDULED
    assert adapter.transitions_for(JOB_ID)[-1].to_state is JobState.RETRY_SCHEDULED
    assert len(adapter.invocations()) == 1


def test_malformed_delivery_is_bounded_by_queue_without_job_mutation() -> None:
    adapter = make_adapter()
    raw_queue = QueueFake[object](start_at=NOW)
    raw_queue.send(
        QueueMessage(
            message_id=str(EVENT_ID),
            queue_name=QUEUE_NAME,
            idempotency_key=str(EVENT_ID),
            payload=object(),
            available_at=NOW,
            max_attempts=1,
        )
    )
    queue = cast(QueuePort[RecordedJobMessage], raw_queue)
    service, _ = make_service(adapter=adapter, queue=queue)

    result = service.work_once(QUEUE_NAME, now=NOW)

    assert result.outcome is WorkOutcome.MALFORMED_DELIVERY_RELEASED
    assert result.failure_code is RuntimeFailureCode.MALFORMED_DELIVERY
    assert len(raw_queue.dead_letters(QUEUE_NAME)) == 1
    assert adapter.job(JOB_ID).state is JobState.REQUESTED
    assert adapter.invocations() == ()


def test_handler_exception_is_sanitized_and_committed_as_terminal_failure() -> None:
    canary = "SYNTHETIC-PRIVATE-HANDLER-CANARY-1404"
    adapter = make_adapter(handler_results=())
    handler = _ExplodingHandler(canary)
    service, _ = make_service(adapter=adapter, handler=handler)
    service.dispatch_once(now=NOW)

    result = service.work_once(QUEUE_NAME, now=NOW)

    assert result.outcome is WorkOutcome.FAILED_TERMINAL
    assert result.failure_code is RuntimeFailureCode.HANDLER_FAILED
    assert handler.calls == 1
    job = adapter.job(JOB_ID)
    assert job.failure_code is RuntimeFailureCode.HANDLER_FAILED
    attempt = adapter.attempts_for(JOB_ID)[0]
    inbox = adapter.inbox(InboxIdentity(CONSUMER_NAME, HANDLER_VERSION, EVENT_ID))
    diagnostics = f"{result!s} {result!r} {job!r} {attempt!r} {inbox!r}"
    assert canary not in diagnostics
    assert PAYLOAD_FINGERPRINT.value not in diagnostics


@pytest.mark.parametrize(
    "environment",
    (
        RuntimeEnvironment.INTEGRATION,
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.RECOVERY,
        RuntimeEnvironment.PRODUCTION,
    ),
)
def test_recorded_adapter_rejects_every_non_dev_ci_environment(
    environment: RuntimeEnvironment,
) -> None:
    _assert_failure(
        RuntimeFailureCode.DEVELOPMENT_ONLY,
        lambda: RecordedJobRuntimeAdapter(
            environment=environment,
            identity_namespace=IDENTITY_NAMESPACE,
            jobs=(make_job(),),
            outboxes=(make_outbox(),),
            handler_results=(success(),),
        ),
    )


def test_recorded_adapter_accepts_exact_dev_ci_and_rejects_raw_strings() -> None:
    assert make_adapter(environment=RuntimeEnvironment.ENV_DEV).environment is (
        RuntimeEnvironment.ENV_DEV
    )
    assert make_adapter(environment=RuntimeEnvironment.CI).environment is (
        RuntimeEnvironment.CI
    )
    _assert_failure(
        RuntimeFailureCode.DEVELOPMENT_ONLY,
        lambda: RecordedJobRuntimeAdapter(
            environment=cast(RuntimeEnvironment, "ENV-DEV"),
            identity_namespace=IDENTITY_NAMESPACE,
            jobs=(make_job(),),
            outboxes=(make_outbox(),),
            handler_results=(success(),),
        ),
    )


def test_values_require_exact_uuid_utc_and_fingerprint_inputs() -> None:
    _assert_failure(
        RuntimeFailureCode.INVALID_ARGUMENT,
        lambda: Fingerprint("A" * 64),
    )
    _assert_failure(
        RuntimeFailureCode.INVALID_ARGUMENT,
        lambda: RecordedHandlerResult(
            outcome=HandlerOutcome.SUCCEEDED,
            completed_at=NOW.replace(tzinfo=None),
            result_fingerprint=RESULT_FINGERPRINT,
        ),
    )
    _assert_failure(
        RuntimeFailureCode.INVALID_ARGUMENT,
        lambda: RecordedJobRuntimeAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            identity_namespace=cast(UUID, str(IDENTITY_NAMESPACE)),
            jobs=(make_job(),),
            outboxes=(make_outbox(),),
            handler_results=(success(),),
        ),
    )


def test_domain_enum_contracts_reject_equal_raw_strings() -> None:
    _assert_failure(
        RuntimeFailureCode.INVALID_ARGUMENT,
        lambda: JobTransition(
            job_id=JOB_ID,
            from_state=cast(JobState, "REQUESTED"),
            to_state=JobState.QUEUED,
            transitioned_at=NOW,
            expected_version=0,
            post_version=1,
        ),
    )
    _assert_failure(
        RuntimeFailureCode.INVALID_ARGUMENT,
        lambda: CompletionCommit(
            outcome=cast(WorkOutcome, "RETRY_SCHEDULED"),
            event_id=EVENT_ID,
            job_id=JOB_ID,
            job_state=JobState.RETRY_SCHEDULED,
            expected_job_version=2,
            post_job_version=4,
            attempt_number=1,
            retry_at=NOW,
        ),
    )
    _assert_failure(
        RuntimeFailureCode.INVALID_ARGUMENT,
        lambda: DispatchStepResult(outcome=cast(DispatchOutcome, "NO_WORK")),
    )
    _assert_failure(
        RuntimeFailureCode.INVALID_ARGUMENT,
        lambda: WorkStepResult(outcome=cast(WorkOutcome, "NO_DELIVERY")),
    )


def test_terminal_handler_result_acks_only_after_inbox_and_job_commit() -> None:
    adapter = make_adapter(handler_results=(terminal(),))
    service, queue_port = make_service(adapter=adapter)
    queue = _queue(queue_port)
    service.dispatch_once(now=NOW)

    result = service.work_once(QUEUE_NAME, now=NOW)

    assert result.outcome is WorkOutcome.FAILED_TERMINAL
    assert adapter.job(JOB_ID).state is JobState.FAILED_TERMINAL
    inbox = adapter.inbox(InboxIdentity(CONSUMER_NAME, HANDLER_VERSION, EVENT_ID))
    assert inbox is not None and inbox.state is InboxState.FAILED
    assert queue.inflight_count(QUEUE_NAME) == 0
    assert queue.pending_message_ids(QUEUE_NAME) == ()


def test_no_quarantine_release_operation_is_exposed() -> None:
    adapter = make_adapter()
    service, _ = make_service(adapter=adapter)
    assert not hasattr(adapter, "release_quarantine")
    assert not hasattr(service, "release_quarantine")
    assert not hasattr(adapter, "expire_retry_state")
    assert not hasattr(service, "expire_retry_state")


def test_service_is_synchronous_and_each_call_observes_at_most_one_item() -> None:
    other_job_id = UUID("00000000-0000-0000-0000-000000001406")
    other_event_id = UUID("00000000-0000-0000-0000-000000002406")
    adapter = make_adapter(
        jobs=(make_job(), make_job(job_id=other_job_id)),
        outboxes=(
            make_outbox(),
            make_outbox(event_id=other_event_id, job_id=other_job_id),
        ),
        handler_results=(success(), success()),
    )
    service, queue_port = make_service(adapter=adapter)
    queue = _queue(queue_port)

    first = service.dispatch_once(now=NOW)
    assert first.outcome is DispatchOutcome.PUBLISHED
    assert len(queue.pending_message_ids(QUEUE_NAME)) == 1
    assert (
        sum(
            adapter.outbox(event_id).state is OutboxState.PUBLISHED
            for event_id in (EVENT_ID, other_event_id)
        )
        == 1
    )

    second = service.dispatch_once(now=NOW)
    assert second.outcome is DispatchOutcome.PUBLISHED
    assert len(queue.pending_message_ids(QUEUE_NAME)) == 2


def test_empty_observations_are_explicit_and_side_effect_free() -> None:
    adapter = make_adapter(
        outboxes=(make_outbox(available_at=NOW + timedelta(seconds=1)),),
    )
    service, _ = make_service(adapter=adapter)

    assert service.dispatch_once(now=NOW).outcome is DispatchOutcome.NO_WORK
    assert service.work_once(QUEUE_NAME, now=NOW).outcome is WorkOutcome.NO_DELIVERY
    assert adapter.job(JOB_ID).state is JobState.REQUESTED
    assert adapter.transitions_for(JOB_ID) == ()

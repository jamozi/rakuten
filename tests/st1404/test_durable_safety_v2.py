"""Fail-closed cancellation, deadline, DLQ, and fencing checks for ST-1404."""

from __future__ import annotations

from datetime import timedelta
from typing import cast

import pytest

from raos.adapters.queue_fake import QueueFake
from raos.application.ops.durable_job_runtime import (
    DurableRecordedJobRuntimeService,
)
from raos.domain.ops.durable_job_runtime import (
    CommitFault,
    DurableCancellationOutcome,
    DurableHandlerOutcome,
    DurableHandlerResult,
    DurableWorkClaim,
    DurableWorkOutcome,
    RecoveryKind,
)
from raos.domain.ops.job_runtime import (
    JobRuntimeFailure,
    JobState,
    OutboxState,
    RecordedJobInvocation,
    RecordedJobMessage,
    RuntimeFailureCode,
)
from raos.ports.queue import QueueDelivery, QueueMessage, QueuePort

from .support import (
    CONSUMER_NAME,
    EVENT_ID,
    HANDLER_VERSION,
    JOB_ID,
    NOW,
    OWNER,
    QUEUE_NAME,
    durable_context,
    durable_result,
    durable_service,
    durable_store,
    make_job,
)


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


class _AlwaysFailSendQueue(_DelegatingQueue):
    def send(self, message: QueueMessage[RecordedJobMessage]) -> None:
        del message
        raise RuntimeError("synthetic send failure")


class _CancellingHandler:
    def __init__(self, store: object) -> None:
        self.store = store
        self.calls = 0

    def handle(self, invocation: RecordedJobInvocation) -> DurableHandlerResult:
        self.calls += 1
        from raos.adapters.recorded_durable_job_runtime import (
            RecordedDurableJobRuntimeStore,
        )

        if type(self.store) is not RecordedDurableJobRuntimeStore:
            raise AssertionError("unexpected store")
        job = self.store.job(invocation.job_id)
        with self.store.begin(durable_context(suffix=90)) as uow:
            uow.repository.request_cancellation(
                job_id=invocation.job_id,
                expected_job_version=job.version,
                requested_at=invocation.started_at,
            )
            uow.commit()
        return durable_result(completed_at=invocation.started_at)


def test_cancellation_before_dispatch_is_terminal_and_idempotent() -> None:
    store = durable_store()
    service, queue_port, handler = durable_service(store=store)
    queue = cast(QueueFake[RecordedJobMessage], queue_port)

    cancelled = service.request_cancellation(
        job_id=JOB_ID,
        expected_job_version=0,
        context=durable_context(),
        now=NOW,
    )
    repeated = service.request_cancellation(
        job_id=JOB_ID,
        expected_job_version=1,
        context=durable_context(suffix=1),
        now=NOW,
    )

    assert cancelled.outcome is DurableCancellationOutcome.CANCELLED
    assert repeated.outcome is DurableCancellationOutcome.ALREADY_CANCELLED
    assert store.job(JOB_ID).state is JobState.CANCELLED
    assert (
        service.dispatch_once(context=durable_context(suffix=2), now=NOW).outcome.value
        == "NO_WORK"
    )
    assert queue.pending_message_ids(QUEUE_NAME) == ()
    assert handler.invocations() == ()


def test_cancellation_after_publish_acknowledges_queued_message_without_handler() -> (
    None
):
    store = durable_store()
    service, queue_port, handler = durable_service(store=store)
    queue = cast(QueueFake[RecordedJobMessage], queue_port)
    service.dispatch_once(context=durable_context(), now=NOW)

    cancellation = service.request_cancellation(
        job_id=JOB_ID,
        expected_job_version=1,
        context=durable_context(suffix=1),
        now=NOW,
    )
    delivery = service.work_once(
        QUEUE_NAME,
        context=durable_context(suffix=2),
        now=NOW,
    )

    assert cancellation.outcome is DurableCancellationOutcome.CANCELLED
    assert delivery.outcome is DurableWorkOutcome.CANCELLED
    assert handler.invocations() == ()
    assert queue.inflight_count(QUEUE_NAME) == 0


def test_cancellation_during_handler_is_observed_by_completion_transaction() -> None:
    store = durable_store()
    queue: QueueFake[RecordedJobMessage] = QueueFake(start_at=NOW)
    handler = _CancellingHandler(store)
    service = DurableRecordedJobRuntimeService(
        factory=store,
        queue=queue,
        handler=handler,
        consumer_name=CONSUMER_NAME,
        handler_version=HANDLER_VERSION,
        owner=OWNER,
        queue_lease=timedelta(seconds=30),
        job_lease=timedelta(seconds=30),
        outbox_lease=timedelta(seconds=20),
        quarantine_lease=timedelta(seconds=20),
        outbox_retry_schedule=(timedelta(seconds=1),),
        job_retry_schedule=(timedelta(seconds=5),),
    )
    service.dispatch_once(context=durable_context(), now=NOW)

    result = service.work_once(
        QUEUE_NAME,
        context=durable_context(suffix=1),
        now=NOW,
    )

    assert result.outcome is DurableWorkOutcome.CANCELLED
    assert store.job(JOB_ID).state is JobState.CANCELLED
    assert store.job(JOB_ID).version == 4
    assert handler.calls == 1


def test_deadline_before_start_and_during_handler_are_fail_closed() -> None:
    before_job = make_job(deadline_at=NOW + timedelta(seconds=1))
    before_store = durable_store(jobs=(before_job,))
    before_service, before_queue_port, before_handler = durable_service(
        store=before_store
    )
    before_queue = cast(QueueFake[RecordedJobMessage], before_queue_port)
    before_service.dispatch_once(context=durable_context(), now=NOW)
    before_queue.advance(timedelta(seconds=1))
    at_deadline = NOW + timedelta(seconds=1)
    before = before_service.work_once(
        QUEUE_NAME,
        context=durable_context(at_deadline, suffix=1),
        now=at_deadline,
    )
    assert before.outcome is DurableWorkOutcome.EXPIRED
    assert before_handler.invocations() == ()

    during_job = make_job(deadline_at=NOW + timedelta(seconds=5))
    during_store = durable_store(jobs=(during_job,))
    during_service, _queue, during_handler = durable_service(
        store=during_store,
        handler_results=(durable_result(completed_at=NOW + timedelta(seconds=5)),),
    )
    during_service.dispatch_once(context=durable_context(suffix=2), now=NOW)
    during = during_service.work_once(
        QUEUE_NAME,
        context=durable_context(suffix=3),
        now=NOW,
    )
    assert during.outcome is DurableWorkOutcome.EXPIRED
    assert during_store.job(JOB_ID).state is JobState.EXPIRED
    assert len(during_handler.invocations()) == 1


def test_expired_retry_state_is_held_without_inventing_a_canonical_edge() -> None:
    job = make_job(deadline_at=NOW + timedelta(seconds=5))
    store = durable_store(jobs=(job,))
    service, queue_port, handler = durable_service(
        store=store,
        handler_results=(durable_result(DurableHandlerOutcome.RETRYABLE_FAILURE),),
        job_retry_schedule=(timedelta(seconds=10),),
    )
    queue = cast(QueueFake[RecordedJobMessage], queue_port)
    service.dispatch_once(context=durable_context(), now=NOW)
    first = service.work_once(
        QUEUE_NAME,
        context=durable_context(suffix=1),
        now=NOW,
    )
    queue.advance(timedelta(seconds=10))
    at = NOW + timedelta(seconds=10)
    held = service.work_once(
        QUEUE_NAME,
        context=durable_context(at, suffix=2),
        now=at,
    )
    recovery = service.recover_once(
        context=durable_context(at, suffix=3),
        now=at,
    )

    assert first.outcome is DurableWorkOutcome.RETRY_SCHEDULED
    assert held.outcome is DurableWorkOutcome.RETRY_STATE_HELD
    assert recovery.kind is RecoveryKind.RETRY_STATE_HELD
    assert store.job(JOB_ID).state is JobState.RETRY_SCHEDULED
    assert len(handler.invocations()) == 1


def test_outbox_send_failure_uses_retry_then_runtime_dlq_without_raw_payload() -> None:
    inner: QueueFake[RecordedJobMessage] = QueueFake(start_at=NOW)
    queue = _AlwaysFailSendQueue(inner)
    store = durable_store()
    service, _port, _handler = durable_service(
        store=store,
        queue=queue,
        outbox_retry_schedule=(timedelta(seconds=1),),
    )

    first = service.dispatch_once(context=durable_context(), now=NOW)
    second_at = NOW + timedelta(seconds=1)
    second = service.dispatch_once(
        context=durable_context(second_at, suffix=1),
        now=second_at,
    )

    assert first.outcome.value == "SEND_RETRY_SCHEDULED"
    assert second.outcome.value == "OUTBOX_DEAD"
    assert store.outbox(EVENT_ID).state is OutboxState.DEAD
    letters = store.dead_letters()
    assert len(letters) == 1
    assert letters[0].state is OutboxState.DEAD
    assert "payload" not in repr(letters[0]).lower()


def test_stale_work_claim_cannot_commit_after_orphan_takeover() -> None:
    store = durable_store()
    service, queue_port, _handler = durable_service(
        store=store,
        job_retry_schedule=(timedelta(0),),
    )
    queue = cast(QueueFake[RecordedJobMessage], queue_port)
    service.dispatch_once(context=durable_context(), now=NOW)
    delivery = queue.receive(QUEUE_NAME, lease=timedelta(seconds=30))
    assert delivery is not None
    with store.begin(durable_context(suffix=1)) as uow:
        start = uow.repository.begin_delivery(
            message=delivery.message.payload,
            consumer_name=CONSUMER_NAME,
            handler_version=HANDLER_VERSION,
            owner=OWNER,
            delivery_attempt=delivery.delivery_attempt,
            queue_leased_until=delivery.leased_until,
            job_leased_until=NOW + timedelta(seconds=30),
            now=NOW,
        )
        uow.commit()
    claim = start.claim
    assert type(claim) is DurableWorkClaim
    queue.advance(timedelta(seconds=30))
    at = NOW + timedelta(seconds=30)
    assert (
        service.recover_once(
            context=durable_context(at, suffix=2),
            now=at,
        ).kind
        is RecoveryKind.WORK_RETRY_SCHEDULED
    )
    with pytest.raises(JobRuntimeFailure) as captured:
        with store.begin(durable_context(at, suffix=3)) as uow:
            uow.repository.complete_delivery(
                claim=claim,
                result=durable_result(completed_at=at),
                retry_at=None,
            )
    assert captured.value.code is RuntimeFailureCode.STALE_LEASE


@pytest.mark.parametrize(
    ("deadline", "cancel", "expected"),
    (
        (False, True, RecoveryKind.WORK_CANCELLED),
        (True, False, RecoveryKind.WORK_EXPIRED),
    ),
)
def test_orphan_recovery_honors_cancellation_and_deadline_precedence(
    deadline: bool,
    cancel: bool,
    expected: RecoveryKind,
) -> None:
    job = make_job(
        deadline_at=NOW + timedelta(seconds=10) if deadline else None,
    )
    store = durable_store(
        jobs=(job,),
        commit_faults=(
            CommitFault.NONE,
            CommitFault.NONE,
            CommitFault.UNKNOWN_AFTER_COMMIT,
        ),
    )
    service, queue_port, handler = durable_service(store=store)
    queue = cast(QueueFake[RecordedJobMessage], queue_port)
    service.dispatch_once(context=durable_context(), now=NOW)
    ambiguous = service.work_once(
        QUEUE_NAME,
        context=durable_context(suffix=1),
        now=NOW,
    )
    assert ambiguous.outcome is DurableWorkOutcome.CLAIM_COMMIT_UNKNOWN
    if cancel:
        cancellation_at = NOW + timedelta(seconds=1)
        recorded = service.request_cancellation(
            job_id=JOB_ID,
            expected_job_version=2,
            context=durable_context(cancellation_at, suffix=2),
            now=cancellation_at,
        )
        assert recorded.outcome is DurableCancellationOutcome.REQUEST_RECORDED
    queue.advance(timedelta(seconds=30))
    at = NOW + timedelta(seconds=30)
    recovered = service.recover_once(
        context=durable_context(at, suffix=3),
        now=at,
    )

    assert recovered.kind is expected
    assert store.job(JOB_ID).state is (
        JobState.CANCELLED if cancel else JobState.EXPIRED
    )
    assert handler.invocations() == ()

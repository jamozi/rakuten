"""Deterministic one-step dispatcher and worker orchestration."""

from __future__ import annotations

from datetime import datetime, timedelta

from raos.domain.ops.job_runtime import (
    CompletionCommit,
    DeliveryStart,
    DeliveryStartOutcome,
    DispatchOutcome,
    DispatchStepResult,
    HandlerOutcome,
    JobRuntimeFailure,
    OutboxDispatchClaim,
    OutboxState,
    RecordedHandlerResult,
    RecordedJobInvocation,
    RecordedJobMessage,
    RuntimeFailureCode,
    WorkOutcome,
    WorkStepResult,
    fail_runtime,
    require_token,
    require_utc,
)
from raos.ports.job_runtime import JobRuntimeStore, RecordedJobHandler
from raos.ports.queue import QueueDelivery, QueueMessage, QueuePort


def _supports(candidate: object, protocol: type[object]) -> bool:
    supported = False
    try:
        supported = isinstance(candidate, protocol)
    except Exception:
        pass
    return supported


def _validate_schedule(value: object) -> tuple[timedelta, ...]:
    if type(value) is not tuple or len(value) > 50:
        fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
    schedule = value
    if any(type(delay) is not timedelta or delay < timedelta(0) for delay in schedule):
        fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
    return schedule


def _checked_add(when: datetime, delay: timedelta) -> datetime:
    try:
        return when + delay
    except OverflowError:
        fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


class RecordedJobRuntimeService:
    """Perform one bounded dispatcher or worker observation per call."""

    __slots__ = (
        "_consumer_name",
        "_handler",
        "_handler_version",
        "_job_lease",
        "_job_retry_schedule",
        "_outbox_retry_schedule",
        "_queue",
        "_queue_lease",
        "_store",
    )

    def __init__(
        self,
        *,
        store: JobRuntimeStore,
        queue: QueuePort[RecordedJobMessage],
        handler: RecordedJobHandler,
        consumer_name: str,
        handler_version: str,
        queue_lease: timedelta,
        job_lease: timedelta,
        outbox_retry_schedule: tuple[timedelta, ...],
        job_retry_schedule: tuple[timedelta, ...],
    ) -> None:
        if not _supports(store, JobRuntimeStore):
            raise TypeError("store must implement JobRuntimeStore")
        if not _supports(queue, QueuePort):
            raise TypeError("queue must implement QueuePort")
        if not _supports(handler, RecordedJobHandler):
            raise TypeError("handler must implement RecordedJobHandler")
        require_token(consumer_name)
        require_token(handler_version)
        if (
            type(queue_lease) is not timedelta
            or queue_lease <= timedelta(0)
            or type(job_lease) is not timedelta
            or job_lease <= timedelta(0)
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        self._store = store
        self._queue = queue
        self._handler = handler
        self._consumer_name = consumer_name
        self._handler_version = handler_version
        self._queue_lease = queue_lease
        self._job_lease = job_lease
        self._outbox_retry_schedule = _validate_schedule(outbox_retry_schedule)
        self._job_retry_schedule = _validate_schedule(job_retry_schedule)

    def dispatch_once(self, *, now: datetime) -> DispatchStepResult:
        """Publish at most one due Outbox item and return a safe observation."""

        observed_at = require_utc(now)
        claim = self._store.claim_due_outbox(now=observed_at)
        if claim is None:
            return DispatchStepResult(outcome=DispatchOutcome.NO_WORK)
        message = self._message(claim)
        try:
            self._queue.send(message)
        except Exception:
            retry_at = self._outbox_retry_at(claim=claim, now=observed_at)
            outbox = self._store.publish_failed(
                claim=claim,
                failed_at=observed_at,
                retry_at=retry_at,
                failure_code=RuntimeFailureCode.QUEUE_SEND_AMBIGUOUS,
            )
            outcome = (
                DispatchOutcome.SEND_RETRY_SCHEDULED
                if outbox.state is OutboxState.FAILED
                else DispatchOutcome.OUTBOX_DEAD
            )
            return DispatchStepResult(
                outcome=outcome,
                event_id=claim.event_id,
                job_id=claim.job_id,
                outbox_state=outbox.state,
                expected_job_version=claim.expected_job_version,
                post_job_version=claim.expected_job_version,
                publish_attempt=claim.publish_attempt,
                failure_code=RuntimeFailureCode.QUEUE_SEND_AMBIGUOUS,
            )
        outbox, post_job_version = self._store.publish_succeeded(
            claim=claim,
            published_at=observed_at,
        )
        return DispatchStepResult(
            outcome=DispatchOutcome.PUBLISHED,
            event_id=claim.event_id,
            job_id=claim.job_id,
            outbox_state=outbox.state,
            expected_job_version=claim.expected_job_version,
            post_job_version=post_job_version,
            publish_attempt=claim.publish_attempt,
        )

    def work_once(self, queue_name: str, *, now: datetime) -> WorkStepResult:
        """Receive and process at most one delivery without starting a loop."""

        require_token(queue_name)
        observed_at = require_utc(now)
        delivery: object = None
        try:
            delivery = self._queue.receive(queue_name, lease=self._queue_lease)
        except Exception:
            return WorkStepResult(
                outcome=WorkOutcome.RECEIVE_FAILED,
                failure_code=RuntimeFailureCode.QUEUE_RECEIVE_FAILED,
            )
        if delivery is None:
            return WorkStepResult(outcome=WorkOutcome.NO_DELIVERY)
        normalized = self._delivery(delivery, queue_name=queue_name)
        if normalized is None:
            return self._release_malformed(delivery)
        payload = normalized.message.payload
        if normalized.leased_until <= observed_at:
            return WorkStepResult(
                outcome=WorkOutcome.LEASE_STALE,
                event_id=payload.event_id,
                job_id=payload.job_id,
                delivery_attempt=normalized.delivery_attempt,
                failure_code=RuntimeFailureCode.STALE_LEASE,
            )
        job_lease_until = _checked_add(observed_at, self._job_lease)
        try:
            start = self._store.begin_delivery(
                message=payload,
                consumer_name=self._consumer_name,
                handler_version=self._handler_version,
                delivery_attempt=normalized.delivery_attempt,
                leased_until=normalized.leased_until,
                job_lease_until=job_lease_until,
                now=observed_at,
            )
        except JobRuntimeFailure as error:
            if type(error) is JobRuntimeFailure and error.code in {
                RuntimeFailureCode.MALFORMED_DELIVERY,
                RuntimeFailureCode.STATE_CONFLICT,
                RuntimeFailureCode.STALE_VERSION,
            }:
                return self._release_malformed(normalized)
            raise
        if start.outcome is not DeliveryStartOutcome.EXECUTE:
            return self._finish_without_handler(start=start, delivery=normalized)
        claim = start.claim
        if claim is None:
            fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
        result = self._invoke_handler(claim.invocation, observed_at=observed_at)
        if result.completed_at >= normalized.leased_until:
            return WorkStepResult(
                outcome=WorkOutcome.LEASE_STALE,
                event_id=claim.event_id,
                job_id=claim.job_id,
                job_state=start.job_state,
                expected_job_version=claim.running_job_version,
                post_job_version=claim.running_job_version,
                attempt_number=claim.attempt_number,
                delivery_attempt=claim.delivery_attempt,
                failure_code=RuntimeFailureCode.STALE_LEASE,
            )
        if not self._receipt_is_current(
            delivery=normalized,
            completed_at=result.completed_at,
        ):
            return WorkStepResult(
                outcome=WorkOutcome.LEASE_STALE,
                event_id=claim.event_id,
                job_id=claim.job_id,
                job_state=start.job_state,
                expected_job_version=claim.running_job_version,
                post_job_version=claim.running_job_version,
                attempt_number=claim.attempt_number,
                delivery_attempt=claim.delivery_attempt,
                failure_code=RuntimeFailureCode.STALE_LEASE,
            )
        retry_at = self._job_retry_at(
            attempt_number=claim.attempt_number,
            completed_at=result.completed_at,
        )
        try:
            commit = self._store.complete_delivery(
                claim=claim,
                result=result,
                retry_at=retry_at,
            )
        except JobRuntimeFailure as error:
            if type(error) is JobRuntimeFailure and error.code in {
                RuntimeFailureCode.STALE_LEASE,
                RuntimeFailureCode.STALE_VERSION,
            }:
                return WorkStepResult(
                    outcome=WorkOutcome.LEASE_STALE,
                    event_id=claim.event_id,
                    job_id=claim.job_id,
                    expected_job_version=claim.running_job_version,
                    post_job_version=claim.running_job_version,
                    attempt_number=claim.attempt_number,
                    delivery_attempt=claim.delivery_attempt,
                    failure_code=error.code,
                )
            raise
        if commit.outcome is WorkOutcome.RETRY_SCHEDULED:
            if commit.retry_at is None:
                fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
            delay = commit.retry_at - observed_at
            if delay < timedelta(0):
                fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
            try:
                self._queue.retry(normalized.receipt_handle, delay=delay)
            except Exception:
                return self._result_from_commit(
                    commit,
                    outcome=WorkOutcome.RETRY_RELEASE_FAILED,
                    delivery_attempt=normalized.delivery_attempt,
                    failure_code=RuntimeFailureCode.QUEUE_RETRY_FAILED,
                )
            return self._result_from_commit(
                commit,
                outcome=WorkOutcome.RETRY_SCHEDULED,
                delivery_attempt=normalized.delivery_attempt,
            )
        return self._acknowledge_commit(commit=commit, delivery=normalized)

    @staticmethod
    def _message(claim: OutboxDispatchClaim) -> QueueMessage[RecordedJobMessage]:
        payload = RecordedJobMessage(
            event_id=claim.event_id,
            job_id=claim.job_id,
            expected_job_version=claim.message_expected_job_version,
            job_schema_version=claim.job_schema_version,
            payload_fingerprint=claim.payload_fingerprint,
            deadline_at=claim.deadline_at,
        )
        identity = str(claim.event_id)
        return QueueMessage(
            message_id=identity,
            queue_name=claim.queue_name,
            idempotency_key=identity,
            payload=payload,
            available_at=claim.message_available_at,
            max_attempts=claim.delivery_max_attempts,
        )

    def _outbox_retry_at(
        self, *, claim: OutboxDispatchClaim, now: datetime
    ) -> datetime | None:
        index = claim.publish_attempt - 1
        if index >= len(self._outbox_retry_schedule):
            return None
        return _checked_add(now, self._outbox_retry_schedule[index])

    def _job_retry_at(
        self, *, attempt_number: int, completed_at: datetime
    ) -> datetime | None:
        index = attempt_number - 1
        if index >= len(self._job_retry_schedule):
            return None
        return _checked_add(completed_at, self._job_retry_schedule[index])

    @staticmethod
    def _delivery(
        candidate: object, *, queue_name: str
    ) -> QueueDelivery[RecordedJobMessage] | None:
        if type(candidate) is not QueueDelivery:
            return None
        delivery = candidate
        message = delivery.message
        if (
            type(message) is not QueueMessage
            or type(message.payload) is not RecordedJobMessage
        ):
            return None
        payload = message.payload
        identity = str(payload.event_id)
        try:
            require_utc(message.available_at)
            require_utc(delivery.leased_until)
        except JobRuntimeFailure:
            return None
        if (
            message.queue_name != queue_name
            or message.message_id != identity
            or message.idempotency_key != identity
        ):
            return None
        return delivery

    def _receipt_is_current(
        self,
        *,
        delivery: QueueDelivery[RecordedJobMessage],
        completed_at: datetime,
    ) -> bool:
        renewed: object = None
        try:
            renewed = self._queue.extend_lease(
                delivery.receipt_handle,
                lease=self._queue_lease,
            )
        except Exception:
            return False
        return (
            type(renewed) is QueueDelivery
            and renewed.message == delivery.message
            and renewed.receipt_handle == delivery.receipt_handle
            and renewed.delivery_attempt == delivery.delivery_attempt
            and renewed.leased_until > completed_at
        )

    def _release_malformed(self, candidate: object) -> WorkStepResult:
        receipt_handle: str | None = None
        delivery_attempt: int | None = None
        if type(candidate) is QueueDelivery:
            delivery = candidate
            receipt_handle = delivery.receipt_handle
            delivery_attempt = delivery.delivery_attempt
        if receipt_handle is None:
            return WorkStepResult(
                outcome=WorkOutcome.RETRY_RELEASE_FAILED,
                failure_code=RuntimeFailureCode.MALFORMED_DELIVERY,
            )
        try:
            self._queue.retry(receipt_handle, delay=timedelta(0))
        except Exception:
            return WorkStepResult(
                outcome=WorkOutcome.RETRY_RELEASE_FAILED,
                delivery_attempt=delivery_attempt,
                failure_code=RuntimeFailureCode.QUEUE_RETRY_FAILED,
            )
        return WorkStepResult(
            outcome=WorkOutcome.MALFORMED_DELIVERY_RELEASED,
            delivery_attempt=delivery_attempt,
            failure_code=RuntimeFailureCode.MALFORMED_DELIVERY,
        )

    def _finish_without_handler(
        self,
        *,
        start: DeliveryStart,
        delivery: QueueDelivery[RecordedJobMessage],
    ) -> WorkStepResult:
        outcome_map = {
            DeliveryStartOutcome.PROCESSING_HELD: WorkOutcome.PROCESSING_HELD,
            DeliveryStartOutcome.RETRY_STATE_HELD: WorkOutcome.RETRY_STATE_HELD,
            DeliveryStartOutcome.NOT_READY_HELD: WorkOutcome.NOT_READY_HELD,
        }
        held = outcome_map.get(start.outcome)
        if held is not None:
            return WorkStepResult(
                outcome=held,
                event_id=start.event_id,
                job_id=start.job_id,
                job_state=start.job_state,
                expected_job_version=start.expected_job_version,
                post_job_version=start.post_job_version,
                delivery_attempt=delivery.delivery_attempt,
            )
        terminal_map = {
            DeliveryStartOutcome.ACK_DUPLICATE: WorkOutcome.DUPLICATE_ACKNOWLEDGED,
            DeliveryStartOutcome.CANCELLED: WorkOutcome.CANCELLED,
            DeliveryStartOutcome.EXPIRED: WorkOutcome.EXPIRED,
        }
        outcome = terminal_map.get(start.outcome)
        if outcome is None:
            fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
        failure: RuntimeFailureCode | None
        try:
            self._queue.acknowledge(delivery.receipt_handle)
        except Exception:
            outcome = WorkOutcome.ACK_FAILED
            failure = RuntimeFailureCode.QUEUE_ACK_FAILED
        else:
            failure = None
        return WorkStepResult(
            outcome=outcome,
            event_id=start.event_id,
            job_id=start.job_id,
            job_state=start.job_state,
            expected_job_version=start.expected_job_version,
            post_job_version=start.post_job_version,
            delivery_attempt=delivery.delivery_attempt,
            failure_code=failure,
        )

    def _invoke_handler(
        self, invocation: RecordedJobInvocation, *, observed_at: datetime
    ) -> RecordedHandlerResult:
        candidate: object = None
        try:
            candidate = self._handler.handle(invocation)
        except Exception:
            return RecordedHandlerResult(
                outcome=HandlerOutcome.TERMINAL_FAILURE,
                completed_at=observed_at,
                failure_code=RuntimeFailureCode.HANDLER_FAILED,
            )
        if type(candidate) is not RecordedHandlerResult:
            return RecordedHandlerResult(
                outcome=HandlerOutcome.TERMINAL_FAILURE,
                completed_at=observed_at,
                failure_code=RuntimeFailureCode.HANDLER_RESULT_MALFORMED,
            )
        if candidate.completed_at < observed_at:
            return RecordedHandlerResult(
                outcome=HandlerOutcome.TERMINAL_FAILURE,
                completed_at=observed_at,
                failure_code=RuntimeFailureCode.HANDLER_RESULT_MALFORMED,
            )
        return candidate

    def _acknowledge_commit(
        self,
        *,
        commit: CompletionCommit,
        delivery: QueueDelivery[RecordedJobMessage],
    ) -> WorkStepResult:
        try:
            self._queue.acknowledge(delivery.receipt_handle)
        except Exception:
            return self._result_from_commit(
                commit,
                outcome=WorkOutcome.ACK_FAILED,
                delivery_attempt=delivery.delivery_attempt,
                failure_code=RuntimeFailureCode.QUEUE_ACK_FAILED,
            )
        return self._result_from_commit(
            commit,
            outcome=commit.outcome,
            delivery_attempt=delivery.delivery_attempt,
        )

    @staticmethod
    def _result_from_commit(
        commit: CompletionCommit,
        *,
        outcome: WorkOutcome,
        delivery_attempt: int,
        failure_code: RuntimeFailureCode | None = None,
    ) -> WorkStepResult:
        return WorkStepResult(
            outcome=outcome,
            event_id=commit.event_id,
            job_id=commit.job_id,
            job_state=commit.job_state,
            expected_job_version=commit.expected_job_version,
            post_job_version=commit.post_job_version,
            attempt_number=commit.attempt_number,
            delivery_attempt=delivery_attempt,
            failure_code=(
                failure_code if failure_code is not None else commit.failure_code
            ),
        )


__all__ = ["RecordedJobRuntimeService"]

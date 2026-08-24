"""One-step dispatcher, worker, recovery, and quarantine replay orchestration.

Every database-shaped mutation is delegated to one explicit outer UoW.  Queue
and handler calls occur only after the claiming transaction has closed and
before a separate finalization transaction begins.  The service has no loop,
sleep, task, thread, deployment, or activation entry point.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

from raos.domain.ops.durable_job_runtime import (
    DurableDeliveryStart,
    DurableCancellationOutcome,
    DurableCancellationResult,
    DurableDispatchOutcome,
    DurableDispatchResult,
    DurableHandlerOutcome,
    DurableHandlerResult,
    DurableOutboxClaim,
    DurableWorkClaim,
    DurableWorkOutcome,
    DurableWorkResult,
    QuarantineReleaseApproval,
    QuarantineReplayClaim,
    QuarantineReplayOutcome,
    QuarantineReplayResult,
    RecoveryCandidate,
    RecoveryCandidateKind,
    RecoveryKind,
    RecoveryResult,
)
from raos.domain.ops.job_runtime import (
    DeliveryStartOutcome,
    JobRuntimeFailure,
    JobState,
    OutboxDispatchClaim,
    OutboxState,
    RecordedJobInvocation,
    RecordedJobMessage,
    RuntimeFailureCode,
    fail_runtime,
    require_token,
    require_utc,
)
from raos.ports.durable_job_runtime import (
    DurableJobHandler,
    DurableJobRuntimeUnitOfWorkFactory,
)
from raos.ports.persistence.context import PersistenceContext
from raos.ports.queue import QueueDelivery, QueueMessage, QueuePort


def _supports(candidate: object, protocol: type[object]) -> bool:
    try:
        return isinstance(candidate, protocol)
    except Exception:
        return False


def _schedule(value: object) -> tuple[timedelta, ...]:
    if type(value) is not tuple:
        fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
    candidate = cast(tuple[object, ...], value)
    if len(candidate) > 50 or any(
        type(delay) is not timedelta or delay < timedelta(0) for delay in candidate
    ):
        fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
    return cast(tuple[timedelta, ...], candidate)


def _duration(value: object) -> timedelta:
    if type(value) is not timedelta or value <= timedelta(0):
        fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
    return value


def _add(when: datetime, delay: timedelta) -> datetime:
    try:
        return when + delay
    except OverflowError:
        fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


class DurableRecordedJobRuntimeService:
    """Run exactly one explicit local/CI runtime observation per method call."""

    __slots__ = (
        "_consumer_name",
        "_factory",
        "_handler",
        "_handler_version",
        "_job_lease",
        "_job_retry_schedule",
        "_outbox_lease",
        "_outbox_retry_schedule",
        "_owner",
        "_quarantine_lease",
        "_queue",
        "_queue_lease",
    )

    def __init__(
        self,
        *,
        factory: DurableJobRuntimeUnitOfWorkFactory,
        queue: QueuePort[RecordedJobMessage],
        handler: DurableJobHandler,
        consumer_name: str,
        handler_version: str,
        owner: str,
        queue_lease: timedelta,
        job_lease: timedelta,
        outbox_lease: timedelta,
        quarantine_lease: timedelta,
        outbox_retry_schedule: tuple[timedelta, ...],
        job_retry_schedule: tuple[timedelta, ...],
    ) -> None:
        if not _supports(factory, DurableJobRuntimeUnitOfWorkFactory):
            raise TypeError("factory must implement DurableJobRuntimeUnitOfWorkFactory")
        if not _supports(queue, QueuePort):
            raise TypeError("queue must implement QueuePort")
        if not _supports(handler, DurableJobHandler):
            raise TypeError("handler must implement DurableJobHandler")
        require_token(consumer_name)
        require_token(handler_version)
        require_token(owner)
        self._factory = factory
        self._queue = queue
        self._handler = handler
        self._consumer_name = consumer_name
        self._handler_version = handler_version
        self._owner = owner
        self._queue_lease = _duration(queue_lease)
        self._job_lease = _duration(job_lease)
        self._outbox_lease = _duration(outbox_lease)
        self._quarantine_lease = _duration(quarantine_lease)
        self._outbox_retry_schedule = _schedule(outbox_retry_schedule)
        self._job_retry_schedule = _schedule(job_retry_schedule)

    def dispatch_once(
        self,
        *,
        context: PersistenceContext,
        now: datetime,
    ) -> DurableDispatchResult:
        observed_at = self._context(context, now=now)
        claim: DurableOutboxClaim | None = None
        try:
            with self._factory.begin(context) as uow:
                claim = uow.repository.claim_due_outbox(
                    now=observed_at,
                    owner=self._owner,
                    leased_until=_add(observed_at, self._outbox_lease),
                )
                if claim is None:
                    uow.rollback()
                    return DurableDispatchResult(outcome=DurableDispatchOutcome.NO_WORK)
                uow.commit()
        except JobRuntimeFailure as error:
            return self._dispatch_commit_failure(error, claim=claim, finalizing=False)
        message = self._message(claim.claim)
        send_failed = False
        try:
            self._queue.send(message)
        except Exception:
            send_failed = True
        retry_at = self._retry_at(
            attempt=claim.claim.publish_attempt,
            completed_at=observed_at,
            schedule=self._outbox_retry_schedule,
        )
        try:
            with self._factory.begin(context) as uow:
                if send_failed:
                    outbox = uow.repository.publish_failed(
                        claim=claim,
                        failed_at=observed_at,
                        retry_at=retry_at,
                        failure_code=RuntimeFailureCode.QUEUE_SEND_AMBIGUOUS,
                    )
                    uow.commit()
                    return DurableDispatchResult(
                        outcome=(
                            DurableDispatchOutcome.SEND_RETRY_SCHEDULED
                            if outbox.state is OutboxState.FAILED
                            else DurableDispatchOutcome.OUTBOX_DEAD
                        ),
                        event_id=claim.claim.event_id,
                        job_id=claim.claim.job_id,
                        outbox_state=outbox.state,
                        failure_code=RuntimeFailureCode.QUEUE_SEND_AMBIGUOUS,
                    )
                outbox, _post_version = uow.repository.publish_succeeded(
                    claim=claim,
                    published_at=observed_at,
                )
                uow.commit()
                return DurableDispatchResult(
                    outcome=DurableDispatchOutcome.PUBLISHED,
                    event_id=claim.claim.event_id,
                    job_id=claim.claim.job_id,
                    outbox_state=outbox.state,
                )
        except JobRuntimeFailure as error:
            return self._dispatch_commit_failure(error, claim=claim, finalizing=True)

    def work_once(
        self,
        queue_name: str,
        *,
        context: PersistenceContext,
        now: datetime,
    ) -> DurableWorkResult:
        require_token(queue_name)
        observed_at = self._context(context, now=now)
        try:
            delivery: object = self._queue.receive(
                queue_name,
                lease=self._queue_lease,
            )
        except Exception:
            return DurableWorkResult(
                outcome=DurableWorkOutcome.RECEIVE_FAILED,
                failure_code=RuntimeFailureCode.QUEUE_RECEIVE_FAILED,
            )
        if delivery is None:
            return DurableWorkResult(outcome=DurableWorkOutcome.NO_DELIVERY)
        normalized = self._delivery(delivery, queue_name=queue_name)
        if normalized is None:
            return self._release_malformed(delivery)
        if normalized.leased_until <= observed_at:
            return DurableWorkResult(
                outcome=DurableWorkOutcome.LEASE_STALE,
                event_id=normalized.message.payload.event_id,
                job_id=normalized.message.payload.job_id,
                delivery_attempt=normalized.delivery_attempt,
                failure_code=RuntimeFailureCode.STALE_LEASE,
            )
        start: DurableDeliveryStart | None = None
        try:
            with self._factory.begin(context) as uow:
                start = uow.repository.begin_delivery(
                    message=normalized.message.payload,
                    consumer_name=self._consumer_name,
                    handler_version=self._handler_version,
                    owner=self._owner,
                    delivery_attempt=normalized.delivery_attempt,
                    queue_leased_until=normalized.leased_until,
                    job_leased_until=_add(observed_at, self._job_lease),
                    now=observed_at,
                )
                uow.commit()
        except JobRuntimeFailure as error:
            return self._work_claim_failure(error, delivery=normalized, start=start)
        if start.outcome is not DeliveryStartOutcome.EXECUTE:
            return self._finish_without_handler(start=start, delivery=normalized)
        claim = start.claim
        if claim is None:
            fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
        result = self._invoke_handler(claim.claim.invocation, observed_at=observed_at)
        if result.completed_at >= claim.claim.leased_until:
            return self._stale_work(claim, normalized.delivery_attempt)
        renewed = self._renewed(normalized, completed_at=result.completed_at)
        if renewed is None:
            return self._stale_work(claim, normalized.delivery_attempt)
        retry_at = self._retry_at(
            attempt=claim.claim.attempt_number,
            completed_at=result.completed_at,
            schedule=self._job_retry_schedule,
        )
        committed: DurableWorkResult | None = None
        try:
            with self._factory.begin(context) as uow:
                committed = uow.repository.complete_delivery(
                    claim=claim,
                    result=result,
                    retry_at=retry_at,
                )
                uow.commit()
        except JobRuntimeFailure as error:
            return self._work_complete_failure(
                error,
                claim=claim,
                delivery_attempt=normalized.delivery_attempt,
            )
        if committed.outcome is DurableWorkOutcome.RETRY_SCHEDULED:
            if retry_at is None:
                fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
            delay = retry_at - observed_at
            if delay < timedelta(0):
                fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
            try:
                self._queue.retry(renewed.receipt_handle, delay=delay)
            except Exception:
                return replace_work(
                    committed,
                    outcome=DurableWorkOutcome.RETRY_RELEASE_FAILED,
                    failure_code=RuntimeFailureCode.QUEUE_RETRY_FAILED,
                )
            return committed
        try:
            self._queue.acknowledge(renewed.receipt_handle)
        except Exception:
            return replace_work(
                committed,
                outcome=DurableWorkOutcome.ACK_FAILED,
                failure_code=RuntimeFailureCode.QUEUE_ACK_FAILED,
            )
        return committed

    def request_cancellation(
        self,
        *,
        job_id: UUID,
        expected_job_version: int,
        context: PersistenceContext,
        now: datetime,
    ) -> DurableCancellationResult:
        observed_at = self._context(context, now=now)
        if type(job_id) is not UUID or (
            type(expected_job_version) is not int or expected_job_version < 0
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        try:
            with self._factory.begin(context) as uow:
                job = uow.repository.request_cancellation(
                    job_id=job_id,
                    expected_job_version=expected_job_version,
                    requested_at=observed_at,
                )
                uow.commit()
        except JobRuntimeFailure as error:
            if error.code in {
                RuntimeFailureCode.COMMIT_KNOWN_ROLLBACK,
                RuntimeFailureCode.CONCURRENCY_CONFLICT,
            }:
                outcome = DurableCancellationOutcome.COMMIT_KNOWN_ROLLBACK
            elif error.code is RuntimeFailureCode.COMMIT_UNKNOWN:
                outcome = DurableCancellationOutcome.COMMIT_UNKNOWN
            else:
                raise
            return DurableCancellationResult(
                outcome=outcome,
                job_id=job_id,
                failure_code=error.code,
            )
        if job.state is JobState.CANCELLED:
            outcome = (
                DurableCancellationOutcome.ALREADY_CANCELLED
                if job.version == expected_job_version
                else DurableCancellationOutcome.CANCELLED
            )
        else:
            outcome = DurableCancellationOutcome.REQUEST_RECORDED
        return DurableCancellationResult(
            outcome=outcome,
            job_id=job.job_id,
            job_state=job.state,
            job_version=job.version,
        )

    def recover_once(
        self,
        *,
        context: PersistenceContext,
        now: datetime,
    ) -> RecoveryResult:
        observed_at = self._context(context, now=now)
        candidate: RecoveryCandidate | None = None
        try:
            with self._factory.begin(context) as uow:
                candidate = uow.repository.recovery_candidate(now=observed_at)
                if candidate is None:
                    uow.rollback()
                    return RecoveryResult(kind=RecoveryKind.NO_WORK)
                retry_at = self._recovery_retry_at(candidate, now=observed_at)
                result = uow.repository.recover(
                    candidate=candidate,
                    recovered_at=observed_at,
                    retry_at=retry_at,
                )
                uow.commit()
                return result
        except JobRuntimeFailure as error:
            if error.code in {
                RuntimeFailureCode.COMMIT_KNOWN_ROLLBACK,
                RuntimeFailureCode.CONCURRENCY_CONFLICT,
            }:
                return RecoveryResult(
                    kind=RecoveryKind.COMMIT_KNOWN_ROLLBACK,
                    event_id=None if candidate is None else candidate.event_id,
                    job_id=None if candidate is None else candidate.job_id,
                    failure_code=error.code,
                )
            if error.code is RuntimeFailureCode.COMMIT_UNKNOWN:
                return RecoveryResult(
                    kind=RecoveryKind.COMMIT_UNKNOWN,
                    event_id=None if candidate is None else candidate.event_id,
                    job_id=None if candidate is None else candidate.job_id,
                    failure_code=error.code,
                )
            raise

    def release_quarantine_once(
        self,
        *,
        approval: QuarantineReleaseApproval,
        context: PersistenceContext,
        now: datetime,
    ) -> QuarantineReplayResult:
        observed_at = self._context(context, now=now)
        claim: QuarantineReplayClaim | None = None
        try:
            with self._factory.begin(context) as uow:
                claim = uow.repository.prepare_quarantine_replay(
                    approval=approval,
                    owner=self._owner,
                    leased_until=_add(observed_at, self._quarantine_lease),
                    now=observed_at,
                )
                uow.commit()
        except JobRuntimeFailure as error:
            outcome = (
                QuarantineReplayOutcome.PREPARE_COMMIT_KNOWN_ROLLBACK
                if error.code
                in {
                    RuntimeFailureCode.COMMIT_KNOWN_ROLLBACK,
                    RuntimeFailureCode.CONCURRENCY_CONFLICT,
                }
                else QuarantineReplayOutcome.PREPARE_COMMIT_UNKNOWN
            )
            if error.code not in {
                RuntimeFailureCode.COMMIT_KNOWN_ROLLBACK,
                RuntimeFailureCode.COMMIT_UNKNOWN,
                RuntimeFailureCode.CONCURRENCY_CONFLICT,
            }:
                raise
            return QuarantineReplayResult(
                outcome=outcome,
                job_id=approval.job_id,
                event_id=None,
                job_state=JobState.QUARANTINED,
                failure_code=error.code,
            )
        message = QueueMessage(
            message_id=str(claim.message.event_id),
            queue_name=claim.queue_name,
            idempotency_key=str(claim.message.event_id),
            payload=claim.message,
            available_at=claim.available_at,
            max_attempts=claim.delivery_max_attempts,
        )
        try:
            self._queue.send(message)
        except Exception:
            return QuarantineReplayResult(
                outcome=QuarantineReplayOutcome.SEND_AMBIGUOUS,
                job_id=approval.job_id,
                event_id=claim.message.event_id,
                job_state=JobState.QUARANTINED,
                failure_code=RuntimeFailureCode.QUEUE_SEND_AMBIGUOUS,
            )
        try:
            with self._factory.begin(context) as uow:
                result = uow.repository.finalize_quarantine_replay(
                    claim=claim,
                    finalized_at=observed_at,
                )
                uow.commit()
                return result
        except JobRuntimeFailure as error:
            if error.code in {
                RuntimeFailureCode.COMMIT_KNOWN_ROLLBACK,
                RuntimeFailureCode.CONCURRENCY_CONFLICT,
            }:
                outcome = QuarantineReplayOutcome.FINALIZE_COMMIT_KNOWN_ROLLBACK
            elif error.code is RuntimeFailureCode.COMMIT_UNKNOWN:
                outcome = QuarantineReplayOutcome.FINALIZE_COMMIT_UNKNOWN
            else:
                raise
            return QuarantineReplayResult(
                outcome=outcome,
                job_id=approval.job_id,
                event_id=claim.message.event_id,
                job_state=JobState.QUARANTINED,
                failure_code=error.code,
            )

    @staticmethod
    def _context(context: PersistenceContext, *, now: datetime) -> datetime:
        observed_at = require_utc(now)
        if (
            type(context) is not PersistenceContext
            or context.occurred_at != observed_at
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        return observed_at

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

    @staticmethod
    def _retry_at(
        *,
        attempt: int,
        completed_at: datetime,
        schedule: tuple[timedelta, ...],
    ) -> datetime | None:
        index = attempt - 1
        if index >= len(schedule):
            return None
        return _add(completed_at, schedule[index])

    def _recovery_retry_at(
        self,
        candidate: RecoveryCandidate,
        *,
        now: datetime,
    ) -> datetime | None:
        if candidate.kind is RecoveryCandidateKind.RETRY_STATE_HELD:
            return None
        attempt = candidate.attempt_number
        if attempt is None:
            fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
        schedule = (
            self._outbox_retry_schedule
            if candidate.kind is RecoveryCandidateKind.OUTBOX
            else self._job_retry_schedule
        )
        return self._retry_at(attempt=attempt, completed_at=now, schedule=schedule)

    @staticmethod
    def _delivery(
        candidate: object,
        *,
        queue_name: str,
    ) -> QueueDelivery[RecordedJobMessage] | None:
        if type(candidate) is not QueueDelivery:
            return None
        delivery = cast(QueueDelivery[object], candidate)
        message = delivery.message
        if (
            type(message) is not QueueMessage
            or type(message.payload) is not RecordedJobMessage
        ):
            return None
        typed = cast(QueueDelivery[RecordedJobMessage], delivery)
        identity = str(typed.message.payload.event_id)
        try:
            require_utc(typed.message.available_at)
            require_utc(typed.leased_until)
        except JobRuntimeFailure:
            return None
        if (
            typed.message.queue_name != queue_name
            or typed.message.message_id != identity
            or typed.message.idempotency_key != identity
        ):
            return None
        return typed

    def _release_malformed(self, candidate: object) -> DurableWorkResult:
        if type(candidate) is not QueueDelivery:
            return DurableWorkResult(
                outcome=DurableWorkOutcome.RETRY_RELEASE_FAILED,
                failure_code=RuntimeFailureCode.MALFORMED_DELIVERY,
            )
        delivery = cast(QueueDelivery[object], candidate)
        try:
            self._queue.retry(delivery.receipt_handle, delay=timedelta(0))
        except Exception:
            return DurableWorkResult(
                outcome=DurableWorkOutcome.RETRY_RELEASE_FAILED,
                delivery_attempt=delivery.delivery_attempt,
                failure_code=RuntimeFailureCode.QUEUE_RETRY_FAILED,
            )
        return DurableWorkResult(
            outcome=DurableWorkOutcome.MALFORMED_DELIVERY_RELEASED,
            delivery_attempt=delivery.delivery_attempt,
            failure_code=RuntimeFailureCode.MALFORMED_DELIVERY,
        )

    def _work_claim_failure(
        self,
        error: JobRuntimeFailure,
        *,
        delivery: QueueDelivery[RecordedJobMessage],
        start: DurableDeliveryStart | None,
    ) -> DurableWorkResult:
        if error.code in {
            RuntimeFailureCode.COMMIT_KNOWN_ROLLBACK,
            RuntimeFailureCode.CONCURRENCY_CONFLICT,
        }:
            try:
                self._queue.retry(delivery.receipt_handle, delay=timedelta(0))
            except Exception:
                pass
            outcome = DurableWorkOutcome.CLAIM_COMMIT_KNOWN_ROLLBACK
        elif error.code is RuntimeFailureCode.COMMIT_UNKNOWN:
            outcome = DurableWorkOutcome.CLAIM_COMMIT_UNKNOWN
        elif error.code in {
            RuntimeFailureCode.MALFORMED_DELIVERY,
            RuntimeFailureCode.STATE_CONFLICT,
            RuntimeFailureCode.STALE_VERSION,
        }:
            return self._release_malformed(delivery)
        else:
            raise error
        return DurableWorkResult(
            outcome=outcome,
            event_id=delivery.message.payload.event_id,
            job_id=delivery.message.payload.job_id,
            job_state=None if start is None else start.job_state,
            delivery_attempt=delivery.delivery_attempt,
            failure_code=error.code,
        )

    @staticmethod
    def _work_complete_failure(
        error: JobRuntimeFailure,
        *,
        claim: DurableWorkClaim,
        delivery_attempt: int,
    ) -> DurableWorkResult:
        if type(claim) is not DurableWorkClaim:
            fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
        if error.code in {
            RuntimeFailureCode.COMMIT_KNOWN_ROLLBACK,
            RuntimeFailureCode.CONCURRENCY_CONFLICT,
        }:
            outcome = DurableWorkOutcome.COMPLETE_COMMIT_KNOWN_ROLLBACK
        elif error.code is RuntimeFailureCode.COMMIT_UNKNOWN:
            outcome = DurableWorkOutcome.COMPLETE_COMMIT_UNKNOWN
        elif error.code in {
            RuntimeFailureCode.STALE_LEASE,
            RuntimeFailureCode.STALE_VERSION,
        }:
            outcome = DurableWorkOutcome.LEASE_STALE
        else:
            raise error
        return DurableWorkResult(
            outcome=outcome,
            event_id=claim.claim.event_id,
            job_id=claim.claim.job_id,
            job_state=JobState.RUNNING,
            attempt_number=claim.claim.attempt_number,
            delivery_attempt=delivery_attempt,
            failure_code=error.code,
        )

    @staticmethod
    def _dispatch_commit_failure(
        error: JobRuntimeFailure,
        *,
        claim: DurableOutboxClaim | None,
        finalizing: bool,
    ) -> DurableDispatchResult:
        if error.code is RuntimeFailureCode.COMMIT_KNOWN_ROLLBACK:
            outcome = (
                DurableDispatchOutcome.FINALIZE_COMMIT_KNOWN_ROLLBACK
                if finalizing
                else DurableDispatchOutcome.CLAIM_COMMIT_KNOWN_ROLLBACK
            )
        elif error.code is RuntimeFailureCode.COMMIT_UNKNOWN:
            outcome = (
                DurableDispatchOutcome.FINALIZE_COMMIT_UNKNOWN
                if finalizing
                else DurableDispatchOutcome.CLAIM_COMMIT_UNKNOWN
            )
        elif error.code is RuntimeFailureCode.CONCURRENCY_CONFLICT:
            outcome = (
                DurableDispatchOutcome.FINALIZE_COMMIT_KNOWN_ROLLBACK
                if finalizing
                else DurableDispatchOutcome.CLAIM_COMMIT_KNOWN_ROLLBACK
            )
        else:
            raise error
        base = None if claim is None else claim.claim
        return DurableDispatchResult(
            outcome=outcome,
            event_id=None if base is None else base.event_id,
            job_id=None if base is None else base.job_id,
            failure_code=error.code,
        )

    def _finish_without_handler(
        self,
        *,
        start: DurableDeliveryStart,
        delivery: QueueDelivery[RecordedJobMessage],
    ) -> DurableWorkResult:
        held = {
            DeliveryStartOutcome.PROCESSING_HELD: DurableWorkOutcome.PROCESSING_HELD,
            DeliveryStartOutcome.RETRY_STATE_HELD: DurableWorkOutcome.RETRY_STATE_HELD,
            DeliveryStartOutcome.NOT_READY_HELD: DurableWorkOutcome.NOT_READY_HELD,
        }.get(start.outcome)
        if held is not None:
            return DurableWorkResult(
                outcome=held,
                event_id=start.event_id,
                job_id=start.job_id,
                job_state=start.job_state,
                delivery_attempt=delivery.delivery_attempt,
            )
        outcome = {
            DeliveryStartOutcome.ACK_DUPLICATE: DurableWorkOutcome.DUPLICATE_ACKNOWLEDGED,
            DeliveryStartOutcome.CANCELLED: DurableWorkOutcome.CANCELLED,
            DeliveryStartOutcome.EXPIRED: DurableWorkOutcome.EXPIRED,
        }.get(start.outcome)
        if outcome is None:
            fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
        failure: RuntimeFailureCode | None = None
        try:
            self._queue.acknowledge(delivery.receipt_handle)
        except Exception:
            outcome = DurableWorkOutcome.ACK_FAILED
            failure = RuntimeFailureCode.QUEUE_ACK_FAILED
        return DurableWorkResult(
            outcome=outcome,
            event_id=start.event_id,
            job_id=start.job_id,
            job_state=start.job_state,
            delivery_attempt=delivery.delivery_attempt,
            failure_code=failure,
        )

    def _invoke_handler(
        self,
        invocation: RecordedJobInvocation,
        *,
        observed_at: datetime,
    ) -> DurableHandlerResult:
        try:
            candidate: object = self._handler.handle(invocation)
        except Exception:
            return DurableHandlerResult(
                outcome=DurableHandlerOutcome.TERMINAL_FAILURE,
                completed_at=observed_at,
                failure_code=RuntimeFailureCode.HANDLER_FAILED,
            )
        if (
            type(candidate) is not DurableHandlerResult
            or candidate.completed_at < observed_at
        ):
            return DurableHandlerResult(
                outcome=DurableHandlerOutcome.TERMINAL_FAILURE,
                completed_at=observed_at,
                failure_code=RuntimeFailureCode.HANDLER_RESULT_MALFORMED,
            )
        return candidate

    def _renewed(
        self,
        delivery: QueueDelivery[RecordedJobMessage],
        *,
        completed_at: datetime,
    ) -> QueueDelivery[RecordedJobMessage] | None:
        try:
            candidate: object = self._queue.extend_lease(
                delivery.receipt_handle,
                lease=self._queue_lease,
            )
        except Exception:
            return None
        if (
            type(candidate) is not QueueDelivery
            or candidate.message != delivery.message
            or candidate.receipt_handle != delivery.receipt_handle
            or candidate.delivery_attempt != delivery.delivery_attempt
            or candidate.leased_until <= completed_at
        ):
            return None
        return candidate

    @staticmethod
    def _stale_work(
        claim: DurableWorkClaim, delivery_attempt: int
    ) -> DurableWorkResult:
        if type(claim) is not DurableWorkClaim:
            fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
        return DurableWorkResult(
            outcome=DurableWorkOutcome.LEASE_STALE,
            event_id=claim.claim.event_id,
            job_id=claim.claim.job_id,
            job_state=JobState.RUNNING,
            attempt_number=claim.claim.attempt_number,
            delivery_attempt=delivery_attempt,
            failure_code=RuntimeFailureCode.STALE_LEASE,
        )


def replace_work(
    value: DurableWorkResult,
    *,
    outcome: DurableWorkOutcome,
    failure_code: RuntimeFailureCode,
) -> DurableWorkResult:
    if type(value) is not DurableWorkResult:
        fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
    return DurableWorkResult(
        outcome=outcome,
        event_id=value.event_id,
        job_id=value.job_id,
        job_state=value.job_state,
        attempt_number=value.attempt_number,
        delivery_attempt=value.delivery_attempt,
        failure_code=failure_code,
    )


__all__ = ["DurableRecordedJobRuntimeService"]

"""Deterministic process-local adapter for the bounded ST-1404 seam.

This adapter is intentionally restricted to exact development and CI runtime
environments.  Its lock provides only same-process atomicity: it is not a
database transaction, crash-recovery protocol, or multi-process fence.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from threading import RLock
from uuid import UUID, uuid5

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ops.job_runtime import (
    AttemptRecord,
    AttemptState,
    CompletionCommit,
    DeliveryStart,
    DeliveryStartOutcome,
    Fingerprint,
    HandlerOutcome,
    InboxIdentity,
    InboxRecord,
    InboxState,
    JobLease,
    JobRecord,
    JobState,
    JobTransition,
    OutboxDispatchClaim,
    OutboxRecord,
    OutboxState,
    RecordedHandlerResult,
    RecordedJobInvocation,
    RecordedJobMessage,
    RuntimeFailureCode,
    WorkClaim,
    WorkOutcome,
    fail_runtime,
    require_token,
    require_utc,
)


class RecordedJobRuntimeAdapter:
    """One in-memory store and scripted metadata-only handler."""

    __slots__ = (
        "_attempts",
        "_environment",
        "_handler_index",
        "_handler_results",
        "_identity_counter",
        "_identity_namespace",
        "_inboxes",
        "_invocations",
        "_jobs",
        "_lock",
        "_message_contracts",
        "_outboxes",
        "_transitions",
    )

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        identity_namespace: UUID,
        jobs: tuple[JobRecord, ...],
        outboxes: tuple[OutboxRecord, ...],
        handler_results: tuple[RecordedHandlerResult, ...],
        attempts: tuple[AttemptRecord, ...] = (),
        inboxes: tuple[InboxRecord, ...] = (),
    ) -> None:
        if type(environment) is not RuntimeEnvironment or environment not in {
            RuntimeEnvironment.ENV_DEV,
            RuntimeEnvironment.CI,
        }:
            fail_runtime(RuntimeFailureCode.DEVELOPMENT_ONLY)
        if type(identity_namespace) is not UUID:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if (
            type(jobs) is not tuple
            or any(type(item) is not JobRecord for item in jobs)
            or type(outboxes) is not tuple
            or any(type(item) is not OutboxRecord for item in outboxes)
            or type(handler_results) is not tuple
            or any(type(item) is not RecordedHandlerResult for item in handler_results)
            or type(attempts) is not tuple
            or any(type(item) is not AttemptRecord for item in attempts)
            or type(inboxes) is not tuple
            or any(type(item) is not InboxRecord for item in inboxes)
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        self._environment = environment
        self._identity_namespace = identity_namespace
        self._identity_counter = 0
        self._lock = RLock()
        self._jobs = {item.job_id: item for item in jobs}
        self._outboxes = {item.event_id: item for item in outboxes}
        self._attempts = {item.attempt_id: item for item in attempts}
        self._inboxes = {item.identity: item for item in inboxes}
        self._handler_results = handler_results
        self._handler_index = 0
        self._invocations: list[RecordedJobInvocation] = []
        self._transitions: list[JobTransition] = []
        self._message_contracts: dict[UUID, RecordedJobMessage] = {}
        if (
            len(self._jobs) != len(jobs)
            or len(self._outboxes) != len(outboxes)
            or len(self._attempts) != len(attempts)
            or len(self._inboxes) != len(inboxes)
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        for outbox in outboxes:
            if outbox.job_id not in self._jobs:
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        for attempt in attempts:
            if attempt.job_id not in self._jobs:
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        self._validate_attempt_numbers()

    @property
    def environment(self) -> RuntimeEnvironment:
        return self._environment

    def claim_due_outbox(self, *, now: datetime) -> OutboxDispatchClaim | None:
        observed_at = require_utc(now)
        with self._lock:
            candidates = [
                outbox
                for outbox in self._outboxes.values()
                if outbox.state in {OutboxState.PENDING, OutboxState.FAILED}
                and outbox.available_at <= observed_at
                and self._jobs[outbox.job_id].state is JobState.REQUESTED
            ]
            if not candidates:
                return None
            outbox = min(
                candidates,
                key=lambda item: (
                    item.available_at,
                    item.created_at,
                    item.event_id.int,
                ),
            )
            claimed = replace(
                outbox,
                state=OutboxState.DISPATCHING,
                publish_attempts=outbox.publish_attempts + 1,
                failure_code=None,
            )
            self._outboxes[outbox.event_id] = claimed
            job = self._jobs[outbox.job_id]
            message = self._message_contracts.get(outbox.event_id)
            if message is None:
                message = RecordedJobMessage(
                    event_id=outbox.event_id,
                    job_id=job.job_id,
                    expected_job_version=job.version,
                    job_schema_version=job.job_schema_version,
                    payload_fingerprint=job.payload_fingerprint,
                    deadline_at=job.deadline_at,
                )
                self._message_contracts[outbox.event_id] = message
            return OutboxDispatchClaim(
                event_id=outbox.event_id,
                job_id=job.job_id,
                queue_name=job.queue_name,
                payload_fingerprint=message.payload_fingerprint,
                message_available_at=outbox.message_available_at,
                deadline_at=message.deadline_at,
                message_expected_job_version=message.expected_job_version,
                expected_job_version=job.version,
                job_schema_version=message.job_schema_version,
                delivery_max_attempts=job.delivery_max_attempts,
                publish_attempt=claimed.publish_attempts,
            )

    def publish_succeeded(
        self, *, claim: OutboxDispatchClaim, published_at: datetime
    ) -> tuple[OutboxRecord, int]:
        completed_at = require_utc(published_at)
        if type(claim) is not OutboxDispatchClaim:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        with self._lock:
            outbox, job = self._dispatch_records(claim)
            if (
                job.state is not JobState.REQUESTED
                or job.version != claim.expected_job_version
            ):
                fail_runtime(RuntimeFailureCode.STALE_VERSION)
            published = replace(
                outbox,
                state=OutboxState.PUBLISHED,
                published_at=completed_at,
                failure_code=None,
            )
            queued = replace(
                job,
                state=JobState.QUEUED,
                version=job.version + 1,
                lease=None,
                completed_at=None,
                result_fingerprint=None,
            )
            self._outboxes[outbox.event_id] = published
            self._commit_transition(before=job, after=queued, at=completed_at)
            return published, queued.version

    def publish_failed(
        self,
        *,
        claim: OutboxDispatchClaim,
        failed_at: datetime,
        retry_at: datetime | None,
        failure_code: RuntimeFailureCode,
    ) -> OutboxRecord:
        observed_at = require_utc(failed_at)
        if (
            type(claim) is not OutboxDispatchClaim
            or type(failure_code) is not RuntimeFailureCode
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if retry_at is not None:
            retry_at = require_utc(retry_at)
            if retry_at < observed_at:
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        with self._lock:
            outbox, job = self._dispatch_records(claim)
            if job.version != claim.expected_job_version:
                fail_runtime(RuntimeFailureCode.STALE_VERSION)
            failed = replace(
                outbox,
                state=OutboxState.FAILED if retry_at is not None else OutboxState.DEAD,
                available_at=retry_at if retry_at is not None else observed_at,
                failure_code=failure_code,
            )
            self._outboxes[outbox.event_id] = failed
            return failed

    def begin_delivery(
        self,
        *,
        message: RecordedJobMessage,
        consumer_name: str,
        handler_version: str,
        delivery_attempt: int,
        leased_until: datetime,
        job_lease_until: datetime,
        now: datetime,
    ) -> DeliveryStart:
        if type(message) is not RecordedJobMessage:
            fail_runtime(RuntimeFailureCode.MALFORMED_DELIVERY)
        require_token(consumer_name)
        require_token(handler_version)
        if type(delivery_attempt) is not int or delivery_attempt < 1:
            fail_runtime(RuntimeFailureCode.MALFORMED_DELIVERY)
        queue_lease_end = require_utc(leased_until)
        requested_job_lease_end = require_utc(job_lease_until)
        observed_at = require_utc(now)
        if queue_lease_end <= observed_at or requested_job_lease_end <= observed_at:
            fail_runtime(RuntimeFailureCode.STALE_LEASE)
        effective_lease_end = min(queue_lease_end, requested_job_lease_end)
        with self._lock:
            expected_message = self._message_contracts.get(message.event_id)
            outbox = self._outboxes.get(message.event_id)
            job = self._jobs.get(message.job_id)
            if (
                expected_message != message
                or outbox is None
                or outbox.state is not OutboxState.PUBLISHED
                or outbox.job_id != message.job_id
                or job is None
                or job.job_schema_version != message.job_schema_version
                or job.payload_fingerprint != message.payload_fingerprint
                or job.deadline_at != message.deadline_at
            ):
                fail_runtime(RuntimeFailureCode.MALFORMED_DELIVERY)
            initial_version = job.version
            identity = InboxIdentity(
                consumer_name=consumer_name,
                handler_version=handler_version,
                event_id=message.event_id,
            )
            inbox = self._inboxes.get(identity)
            if inbox is not None and inbox.state is InboxState.PROCESSING:
                return self._start_result(
                    outcome=DeliveryStartOutcome.PROCESSING_HELD,
                    message=message,
                    job=job,
                    expected_version=initial_version,
                )
            if inbox is not None and (
                inbox.state in {InboxState.PROCESSED, InboxState.IGNORED}
                or (
                    inbox.state is InboxState.FAILED
                    and job.state
                    in {
                        JobState.FAILED_TERMINAL,
                        JobState.CANCELLED,
                        JobState.EXPIRED,
                    }
                )
            ):
                return self._start_result(
                    outcome=DeliveryStartOutcome.ACK_DUPLICATE,
                    message=message,
                    job=job,
                    expected_version=initial_version,
                )
            if job.state is JobState.RETRY_SCHEDULED:
                if (
                    job.available_at > observed_at
                    or job.cancel_requested_at is not None
                    or (job.deadline_at is not None and job.deadline_at <= observed_at)
                    or inbox is None
                    or inbox.state is not InboxState.FAILED
                ):
                    return self._start_result(
                        outcome=DeliveryStartOutcome.RETRY_STATE_HELD,
                        message=message,
                        job=job,
                        expected_version=initial_version,
                    )
                self._inboxes[identity] = replace(
                    inbox,
                    state=InboxState.PROCESSING,
                    received_at=observed_at,
                    processed_at=None,
                    result_fingerprint=None,
                    failure_code=None,
                )
                queued = replace(
                    job,
                    state=JobState.QUEUED,
                    version=job.version + 1,
                    lease=None,
                    completed_at=None,
                    result_fingerprint=None,
                )
                self._commit_transition(before=job, after=queued, at=observed_at)
                job = queued
                inbox = self._inboxes[identity]
            if job.state is not JobState.QUEUED:
                return self._start_result(
                    outcome=DeliveryStartOutcome.NOT_READY_HELD,
                    message=message,
                    job=job,
                    expected_version=initial_version,
                )
            if inbox is None:
                inbox = InboxRecord(
                    inbox_id=self._new_uuid("inbox"),
                    identity=identity,
                    state=InboxState.PROCESSING,
                    received_at=observed_at,
                )
                self._inboxes[identity] = inbox
            if job.cancel_requested_at is not None:
                ignored = replace(
                    inbox,
                    state=InboxState.IGNORED,
                    processed_at=observed_at,
                    failure_code=None,
                )
                cancelled = replace(
                    job,
                    state=JobState.CANCELLED,
                    version=job.version + 1,
                    completed_at=observed_at,
                    lease=None,
                )
                self._inboxes[identity] = ignored
                self._commit_transition(before=job, after=cancelled, at=observed_at)
                return self._start_result(
                    outcome=DeliveryStartOutcome.CANCELLED,
                    message=message,
                    job=cancelled,
                    expected_version=initial_version,
                )
            if job.deadline_at is not None and job.deadline_at <= observed_at:
                ignored = replace(
                    inbox,
                    state=InboxState.IGNORED,
                    processed_at=observed_at,
                    failure_code=None,
                )
                expired = replace(
                    job,
                    state=JobState.EXPIRED,
                    version=job.version + 1,
                    completed_at=observed_at,
                    lease=None,
                )
                self._inboxes[identity] = ignored
                self._commit_transition(before=job, after=expired, at=observed_at)
                return self._start_result(
                    outcome=DeliveryStartOutcome.EXPIRED,
                    message=message,
                    job=expired,
                    expected_version=initial_version,
                )
            if job.attempt_count >= job.max_attempts:
                return self._start_result(
                    outcome=DeliveryStartOutcome.NOT_READY_HELD,
                    message=message,
                    job=job,
                    expected_version=initial_version,
                )
            attempt_number = job.attempt_count + 1
            attempt_id = self._new_uuid("attempt")
            lease_id = self._new_uuid("lease")
            lease = JobLease(lease_id=lease_id, expires_at=effective_lease_end)
            running = replace(
                job,
                state=JobState.RUNNING,
                version=job.version + 1,
                attempt_count=attempt_number,
                lease=lease,
                completed_at=None,
                result_fingerprint=None,
            )
            self._commit_transition(before=job, after=running, at=observed_at)
            attempt = AttemptRecord(
                attempt_id=attempt_id,
                job_id=job.job_id,
                attempt_number=attempt_number,
                state=AttemptState.RUNNING,
                handler_version=handler_version,
                started_at=observed_at,
            )
            self._attempts[attempt_id] = attempt
            invocation = RecordedJobInvocation(
                event_id=message.event_id,
                job_id=job.job_id,
                attempt_id=attempt_id,
                attempt_number=attempt_number,
                payload_fingerprint=job.payload_fingerprint,
                started_at=observed_at,
                deadline_at=job.deadline_at,
            )
            claim = WorkClaim(
                event_id=message.event_id,
                job_id=job.job_id,
                inbox_id=inbox.inbox_id,
                attempt_id=attempt_id,
                attempt_number=attempt_number,
                lease_id=lease_id,
                leased_until=effective_lease_end,
                expected_job_version=initial_version,
                running_job_version=running.version,
                delivery_attempt=delivery_attempt,
                invocation=invocation,
            )
            return DeliveryStart(
                outcome=DeliveryStartOutcome.EXECUTE,
                event_id=message.event_id,
                job_id=job.job_id,
                job_state=JobState.RUNNING,
                expected_job_version=initial_version,
                post_job_version=running.version,
                claim=claim,
            )

    def complete_delivery(
        self,
        *,
        claim: WorkClaim,
        result: RecordedHandlerResult,
        retry_at: datetime | None,
    ) -> CompletionCommit:
        if type(claim) is not WorkClaim or type(result) is not RecordedHandlerResult:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        completed_at = result.completed_at
        if retry_at is not None:
            retry_at = require_utc(retry_at)
            if retry_at < completed_at:
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        with self._lock:
            job = self._jobs.get(claim.job_id)
            attempt = self._attempts.get(claim.attempt_id)
            inbox = next(
                (
                    item
                    for item in self._inboxes.values()
                    if item.inbox_id == claim.inbox_id
                ),
                None,
            )
            if job is None or attempt is None or inbox is None:
                fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
            invocation = claim.invocation
            if (
                attempt.job_id != claim.job_id
                or attempt.attempt_number != claim.attempt_number
                or attempt.handler_version != inbox.identity.handler_version
                or attempt.started_at != invocation.started_at
                or inbox.identity.event_id != claim.event_id
                or invocation.event_id != claim.event_id
                or invocation.job_id != claim.job_id
                or invocation.attempt_id != claim.attempt_id
                or invocation.attempt_number != claim.attempt_number
                or invocation.payload_fingerprint != job.payload_fingerprint
                or invocation.deadline_at != job.deadline_at
                or job.attempt_count != claim.attempt_number
            ):
                fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
            if (
                job.state is not JobState.RUNNING
                or attempt.state is not AttemptState.RUNNING
            ):
                fail_runtime(RuntimeFailureCode.STALE_VERSION)
            version_matches = job.version == claim.running_job_version
            cancellation_only_update = (
                job.cancel_requested_at is not None
                and job.version == claim.running_job_version + 1
            )
            if not (version_matches or cancellation_only_update):
                fail_runtime(RuntimeFailureCode.STALE_VERSION)
            if (
                job.lease is None
                or job.lease.lease_id != claim.lease_id
                or job.lease.expires_at != claim.leased_until
                or job.lease.expires_at <= completed_at
            ):
                fail_runtime(RuntimeFailureCode.STALE_LEASE)
            if inbox.state is not InboxState.PROCESSING:
                fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
            if job.cancel_requested_at is not None:
                return self._commit_cancelled(
                    job=job,
                    attempt=attempt,
                    inbox=inbox,
                    claim=claim,
                    completed_at=completed_at,
                )
            if job.deadline_at is not None and job.deadline_at <= completed_at:
                return self._commit_expired(
                    job=job,
                    attempt=attempt,
                    inbox=inbox,
                    claim=claim,
                    completed_at=completed_at,
                )
            if result.outcome is HandlerOutcome.SUCCEEDED:
                return self._commit_succeeded(
                    job=job,
                    attempt=attempt,
                    inbox=inbox,
                    claim=claim,
                    result=result,
                )
            if result.outcome is HandlerOutcome.TERMINAL_FAILURE:
                return self._commit_terminal_failure(
                    job=job,
                    attempt=attempt,
                    inbox=inbox,
                    claim=claim,
                    result=result,
                )
            return self._commit_retryable_failure(
                job=job,
                attempt=attempt,
                inbox=inbox,
                claim=claim,
                result=result,
                retry_at=retry_at,
            )

    def handle(self, invocation: RecordedJobInvocation) -> RecordedHandlerResult:
        if type(invocation) is not RecordedJobInvocation:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        with self._lock:
            self._invocations.append(invocation)
            if self._handler_index >= len(self._handler_results):
                return RecordedHandlerResult(
                    outcome=HandlerOutcome.TERMINAL_FAILURE,
                    completed_at=invocation.started_at,
                    failure_code=RuntimeFailureCode.HANDLER_SCRIPT_EXHAUSTED,
                )
            result = self._handler_results[self._handler_index]
            self._handler_index += 1
            return result

    def request_cancel(self, *, job_id: UUID, requested_at: datetime) -> JobRecord:
        """Record one cooperative cancellation request for deterministic tests."""

        if type(job_id) is not UUID:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        observed_at = require_utc(requested_at)
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.state in {
                JobState.SUCCEEDED,
                JobState.FAILED_TERMINAL,
                JobState.QUARANTINED,
                JobState.CANCELLED,
                JobState.EXPIRED,
            }:
                fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
            if job.cancel_requested_at is not None:
                return job
            updated = replace(
                job,
                cancel_requested_at=observed_at,
                version=job.version + 1,
            )
            self._jobs[job_id] = updated
            return updated

    def job(self, job_id: UUID) -> JobRecord:
        with self._lock:
            try:
                return self._jobs[job_id]
            except KeyError:
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)

    def outbox(self, event_id: UUID) -> OutboxRecord:
        with self._lock:
            try:
                return self._outboxes[event_id]
            except KeyError:
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)

    def attempts_for(self, job_id: UUID) -> tuple[AttemptRecord, ...]:
        with self._lock:
            return tuple(
                sorted(
                    (item for item in self._attempts.values() if item.job_id == job_id),
                    key=lambda item: item.attempt_number,
                )
            )

    def inbox(self, identity: InboxIdentity) -> InboxRecord | None:
        with self._lock:
            return self._inboxes.get(identity)

    def transitions_for(self, job_id: UUID) -> tuple[JobTransition, ...]:
        with self._lock:
            return tuple(item for item in self._transitions if item.job_id == job_id)

    def invocations(self) -> tuple[RecordedJobInvocation, ...]:
        with self._lock:
            return tuple(self._invocations)

    def _dispatch_records(
        self, claim: OutboxDispatchClaim
    ) -> tuple[OutboxRecord, JobRecord]:
        outbox = self._outboxes.get(claim.event_id)
        job = self._jobs.get(claim.job_id)
        message = RecordedJobMessage(
            event_id=claim.event_id,
            job_id=claim.job_id,
            expected_job_version=claim.message_expected_job_version,
            job_schema_version=claim.job_schema_version,
            payload_fingerprint=claim.payload_fingerprint,
            deadline_at=claim.deadline_at,
        )
        if (
            outbox is None
            or job is None
            or outbox.job_id != job.job_id
            or outbox.state is not OutboxState.DISPATCHING
            or outbox.publish_attempts != claim.publish_attempt
            or outbox.message_available_at != claim.message_available_at
            or job.queue_name != claim.queue_name
            or job.payload_fingerprint != claim.payload_fingerprint
            or job.job_schema_version != claim.job_schema_version
            or job.delivery_max_attempts != claim.delivery_max_attempts
            or job.deadline_at != claim.deadline_at
            or self._message_contracts.get(claim.event_id) != message
        ):
            fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
        return outbox, job

    def _start_result(
        self,
        *,
        outcome: DeliveryStartOutcome,
        message: RecordedJobMessage,
        job: JobRecord,
        expected_version: int,
    ) -> DeliveryStart:
        return DeliveryStart(
            outcome=outcome,
            event_id=message.event_id,
            job_id=message.job_id,
            job_state=job.state,
            expected_job_version=expected_version,
            post_job_version=job.version,
        )

    def _commit_cancelled(
        self,
        *,
        job: JobRecord,
        attempt: AttemptRecord,
        inbox: InboxRecord,
        claim: WorkClaim,
        completed_at: datetime,
    ) -> CompletionCommit:
        self._attempts[attempt.attempt_id] = replace(
            attempt,
            state=AttemptState.CANCELLED,
            completed_at=completed_at,
        )
        self._replace_inbox(
            inbox,
            state=InboxState.IGNORED,
            processed_at=completed_at,
            result_fingerprint=None,
            failure_code=None,
        )
        cancelled = replace(
            job,
            state=JobState.CANCELLED,
            version=job.version + 1,
            completed_at=completed_at,
            lease=None,
            result_fingerprint=None,
        )
        self._commit_transition(before=job, after=cancelled, at=completed_at)
        return self._completion(
            claim=claim,
            job=cancelled,
            outcome=WorkOutcome.CANCELLED,
        )

    def _commit_expired(
        self,
        *,
        job: JobRecord,
        attempt: AttemptRecord,
        inbox: InboxRecord,
        claim: WorkClaim,
        completed_at: datetime,
    ) -> CompletionCommit:
        self._attempts[attempt.attempt_id] = replace(
            attempt,
            state=AttemptState.TIMED_OUT,
            completed_at=completed_at,
        )
        self._replace_inbox(
            inbox,
            state=InboxState.IGNORED,
            processed_at=completed_at,
            result_fingerprint=None,
            failure_code=None,
        )
        expired = replace(
            job,
            state=JobState.EXPIRED,
            version=job.version + 1,
            completed_at=completed_at,
            lease=None,
            result_fingerprint=None,
        )
        self._commit_transition(before=job, after=expired, at=completed_at)
        return self._completion(
            claim=claim,
            job=expired,
            outcome=WorkOutcome.EXPIRED,
        )

    def _commit_succeeded(
        self,
        *,
        job: JobRecord,
        attempt: AttemptRecord,
        inbox: InboxRecord,
        claim: WorkClaim,
        result: RecordedHandlerResult,
    ) -> CompletionCommit:
        self._attempts[attempt.attempt_id] = replace(
            attempt,
            state=AttemptState.SUCCEEDED,
            completed_at=result.completed_at,
            result_fingerprint=result.result_fingerprint,
        )
        self._replace_inbox(
            inbox,
            state=InboxState.PROCESSED,
            processed_at=result.completed_at,
            result_fingerprint=result.result_fingerprint,
            failure_code=None,
        )
        succeeded = replace(
            job,
            state=JobState.SUCCEEDED,
            version=job.version + 1,
            completed_at=result.completed_at,
            lease=None,
            result_fingerprint=result.result_fingerprint,
            failure_code=None,
        )
        self._commit_transition(before=job, after=succeeded, at=result.completed_at)
        return self._completion(
            claim=claim,
            job=succeeded,
            outcome=WorkOutcome.SUCCEEDED,
        )

    def _commit_terminal_failure(
        self,
        *,
        job: JobRecord,
        attempt: AttemptRecord,
        inbox: InboxRecord,
        claim: WorkClaim,
        result: RecordedHandlerResult,
    ) -> CompletionCommit:
        self._attempts[attempt.attempt_id] = replace(
            attempt,
            state=AttemptState.FAILED,
            completed_at=result.completed_at,
            failure_code=result.failure_code,
        )
        self._replace_inbox(
            inbox,
            state=InboxState.FAILED,
            processed_at=result.completed_at,
            result_fingerprint=None,
            failure_code=result.failure_code,
        )
        failed = replace(
            job,
            state=JobState.FAILED_TERMINAL,
            version=job.version + 1,
            completed_at=result.completed_at,
            lease=None,
            result_fingerprint=None,
            failure_code=result.failure_code,
        )
        self._commit_transition(before=job, after=failed, at=result.completed_at)
        return self._completion(
            claim=claim,
            job=failed,
            outcome=WorkOutcome.FAILED_TERMINAL,
        )

    def _commit_retryable_failure(
        self,
        *,
        job: JobRecord,
        attempt: AttemptRecord,
        inbox: InboxRecord,
        claim: WorkClaim,
        result: RecordedHandlerResult,
        retry_at: datetime | None,
    ) -> CompletionCommit:
        self._attempts[attempt.attempt_id] = replace(
            attempt,
            state=AttemptState.FAILED,
            completed_at=result.completed_at,
            retry_after_at=retry_at,
            failure_code=result.failure_code,
        )
        self._replace_inbox(
            inbox,
            state=InboxState.FAILED,
            processed_at=result.completed_at,
            result_fingerprint=None,
            failure_code=result.failure_code,
        )
        retryable = replace(
            job,
            state=JobState.FAILED_RETRYABLE,
            version=job.version + 1,
            completed_at=None,
            lease=None,
            result_fingerprint=None,
            failure_code=result.failure_code,
        )
        self._commit_transition(before=job, after=retryable, at=result.completed_at)
        if retry_at is None or job.attempt_count >= job.max_attempts:
            terminal = replace(
                retryable,
                state=JobState.FAILED_TERMINAL,
                version=retryable.version + 1,
                completed_at=result.completed_at,
                failure_code=(
                    RuntimeFailureCode.RETRY_BUDGET_EXHAUSTED
                    if retry_at is None
                    else result.failure_code
                ),
            )
            self._commit_transition(
                before=retryable,
                after=terminal,
                at=result.completed_at,
            )
            return self._completion(
                claim=claim,
                job=terminal,
                outcome=WorkOutcome.FAILED_TERMINAL,
            )
        scheduled = replace(
            retryable,
            state=JobState.RETRY_SCHEDULED,
            version=retryable.version + 1,
            available_at=retry_at,
        )
        self._commit_transition(
            before=retryable,
            after=scheduled,
            at=result.completed_at,
        )
        return self._completion(
            claim=claim,
            job=scheduled,
            outcome=WorkOutcome.RETRY_SCHEDULED,
            retry_at=retry_at,
        )

    def _replace_inbox(
        self,
        inbox: InboxRecord,
        *,
        state: InboxState,
        processed_at: datetime,
        result_fingerprint: Fingerprint | None,
        failure_code: RuntimeFailureCode | None,
    ) -> None:
        self._inboxes[inbox.identity] = replace(
            inbox,
            state=state,
            processed_at=processed_at,
            result_fingerprint=result_fingerprint,
            failure_code=failure_code,
        )

    def _completion(
        self,
        *,
        claim: WorkClaim,
        job: JobRecord,
        outcome: WorkOutcome,
        retry_at: datetime | None = None,
    ) -> CompletionCommit:
        return CompletionCommit(
            outcome=outcome,
            event_id=claim.event_id,
            job_id=claim.job_id,
            job_state=job.state,
            expected_job_version=claim.running_job_version,
            post_job_version=job.version,
            attempt_number=claim.attempt_number,
            retry_at=retry_at,
            failure_code=job.failure_code,
        )

    def _commit_transition(
        self, *, before: JobRecord, after: JobRecord, at: datetime
    ) -> None:
        transition = JobTransition(
            job_id=before.job_id,
            from_state=before.state,
            to_state=after.state,
            transitioned_at=at,
            expected_version=before.version,
            post_version=after.version,
        )
        self._jobs[after.job_id] = after
        self._transitions.append(transition)

    def _new_uuid(self, kind: str) -> UUID:
        self._identity_counter += 1
        return uuid5(
            self._identity_namespace,
            f"raos-st1404:{kind}:{self._identity_counter}",
        )

    def _validate_attempt_numbers(self) -> None:
        seen: set[tuple[UUID, int]] = set()
        for attempt in self._attempts.values():
            identity = (attempt.job_id, attempt.attempt_number)
            if identity in seen:
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
            seen.add(identity)


__all__ = ["RecordedJobRuntimeAdapter"]

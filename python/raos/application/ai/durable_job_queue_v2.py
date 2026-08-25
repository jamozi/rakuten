"""Recorded-only durable ST-0706 AI job state transitions.

Each mutating call performs at most one caller-owned CAS.  There is no worker
loop, sleep, broker acknowledgement, database selection, event dispatch, or
automatic redrive in this application service.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
import hashlib
from uuid import UUID

from raos.domain.ai.durable_job_queue_v2 import (
    DurableCompletionReceipt,
    DurableDecisionCode,
    DurableJobRecord,
    DurableJobStatus,
    DurableJobView,
    DurableLease,
    DurableLeaseClaim,
    DurableOutboxIntent,
    DurableQueueFailure,
    DurableQueueFailureCode,
    DurableQueueSnapshot,
    DurableQueueState,
    MAXIMUM_ATTEMPTS_CAP,
    MAXIMUM_COMPLETION_RECEIPTS_PER_JOB,
    MAXIMUM_OUTBOX_INTENTS,
    QUEUE_CAPACITY,
    RETRY_BACKOFF_SECONDS_AFTER_ATTEMPT,
    RecordedAttemptKind,
    RecordedAttemptOutcome,
    RecordedDurableQueueActivation,
    durable_job_view,
    encode_durable_queue_state,
    fail_durable_queue,
    require_durable_sha256,
    require_durable_token,
    require_durable_utc,
    snapshot_state,
)
from raos.domain.ai.job_orchestration import (
    AiJobCommand,
    AiJobEventType,
    ProviderFailureClass,
    ValidationStatus,
)
from raos.ports.durable_ai_job_queue_v2 import DurableAiJobStateCasPort


_RETRYABLE_FAILURES = frozenset(
    {
        ProviderFailureClass.RATE_LIMIT,
        ProviderFailureClass.TRANSIENT_ERROR,
        ProviderFailureClass.TIMEOUT,
        ProviderFailureClass.MODEL_UNAVAILABLE,
    }
)


def _supports(candidate: object, protocol: type[object]) -> bool:
    supported = False
    try:
        supported = isinstance(candidate, protocol)
    except Exception:
        pass
    return supported


def _normalize_command(command: object, *, observed_at: datetime) -> AiJobCommand:
    """Round-trip through the strict codec to reject mutated frozen values."""

    if type(command) is not AiJobCommand:
        fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
    candidate = command
    try:
        state = DurableQueueState(
            queue_id="st0706.command-normalization.v2",
            revision=0,
            jobs=(
                DurableJobRecord(
                    command=candidate,
                    status=DurableJobStatus.READY,
                    attempt_number=candidate.attempt_number,
                    accumulated_cost_jpy=0,
                    available_at=observed_at,
                ),
            ),
            outbox_intents=(
                DurableOutboxIntent.create(
                    event_type=AiJobEventType.REQUESTED,
                    command=candidate,
                    attempt_number=candidate.attempt_number,
                    status=DurableJobStatus.READY,
                    occurred_at=observed_at,
                ),
            ),
        )
        from raos.domain.ai.durable_job_queue_v2 import decode_durable_queue_state

        normalized = (
            decode_durable_queue_state(
                encode_durable_queue_state(state),
                expected_queue_id=state.queue_id,
                expected_revision=0,
            )
            .jobs[0]
            .command
        )
    except Exception:
        fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
    return normalized


def _normalize_outcome(outcome: object) -> RecordedAttemptOutcome:
    if type(outcome) is not RecordedAttemptOutcome:
        fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
    candidate = outcome
    normalized: RecordedAttemptOutcome | None = None
    try:
        normalized = RecordedAttemptOutcome(
            kind=candidate.kind,
            ai_job_id=candidate.ai_job_id,
            attempt_number=candidate.attempt_number,
            provider_request_id=candidate.provider_request_id,
            actual_cost_jpy=candidate.actual_cost_jpy,
            provider_failure_class=candidate.provider_failure_class,
            validation_status=candidate.validation_status,
            validation_failure_class=candidate.validation_failure_class,
            retryable=candidate.retryable,
            output_artifact_id=candidate.output_artifact_id,
            output_artifact_sha256=candidate.output_artifact_sha256,
        )
    except Exception:
        pass
    if (
        normalized is None
        or normalized.fingerprint_sha256 != candidate.fingerprint_sha256
    ):
        fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
    return normalized


class RecordedDurableAiJobQueueServiceV2:
    """Apply bounded AI-specific transitions against an atomic byte-state port."""

    __slots__ = ("_activation", "_state")

    def __init__(
        self,
        *,
        activation: RecordedDurableQueueActivation,
        state: DurableAiJobStateCasPort,
    ) -> None:
        if type(activation) is not RecordedDurableQueueActivation:
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        normalized_activation: RecordedDurableQueueActivation | None = None
        try:
            normalized_activation = RecordedDurableQueueActivation(
                environment=activation.environment,
                enabled=activation.enabled,
                policy_id=activation.policy_id,
            )
        except Exception:
            pass
        if (
            normalized_activation is None
            or normalized_activation.fingerprint_sha256 != activation.fingerprint_sha256
        ):
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        if not _supports(state, DurableAiJobStateCasPort):
            raise TypeError("state must implement DurableAiJobStateCasPort")
        self._activation = normalized_activation
        self._state = state

    def enqueue(
        self, *, queue_id: str, command: AiJobCommand, enqueued_at: datetime
    ) -> DurableJobView:
        """Persist one command or replay its exact idempotency binding."""

        self._guard()
        now = require_durable_utc(enqueued_at)
        normalized = _normalize_command(command, observed_at=now)
        snapshot, state = self._load(queue_id=queue_id)

        for job in state.jobs:
            if job.command.idempotency_key == normalized.idempotency_key:
                if job.command.fingerprint_sha256 != normalized.fingerprint_sha256:
                    fail_durable_queue(DurableQueueFailureCode.IDEMPOTENCY_MISMATCH)
                return durable_job_view(state=state, job=job, replayed=True)
        if any(job.command.ai_job_id == normalized.ai_job_id for job in state.jobs):
            fail_durable_queue(DurableQueueFailureCode.AI_JOB_ID_CONFLICT)
        if any(job.command.ops_job_id == normalized.ops_job_id for job in state.jobs):
            fail_durable_queue(DurableQueueFailureCode.OPS_JOB_ID_CONFLICT)
        if any(
            job.command.operation_id == normalized.operation_id
            or job.command.authorization.reservation.reservation_id
            == normalized.authorization.reservation.reservation_id
            for job in state.jobs
        ):
            fail_durable_queue(DurableQueueFailureCode.IDEMPOTENCY_MISMATCH)
        if len(state.jobs) >= QUEUE_CAPACITY:
            fail_durable_queue(DurableQueueFailureCode.CAPACITY_EXCEEDED)

        status = DurableJobStatus.READY
        decision: DurableDecisionCode | None = None
        if normalized.cancellation_requested:
            status = DurableJobStatus.CANCELLED
            decision = DurableDecisionCode.COMMAND_CANCELLED
        elif now >= normalized.deadline_at:
            status = DurableJobStatus.EXPIRED
            decision = DurableDecisionCode.DEADLINE_EXPIRED
        job = DurableJobRecord(
            command=normalized,
            status=status,
            attempt_number=normalized.attempt_number,
            accumulated_cost_jpy=0,
            available_at=now,
            decision_code=decision,
        )
        intents = [
            DurableOutboxIntent.create(
                event_type=AiJobEventType.REQUESTED,
                command=normalized,
                attempt_number=normalized.attempt_number,
                status=status,
                occurred_at=now,
            )
        ]
        if status in {DurableJobStatus.CANCELLED, DurableJobStatus.EXPIRED}:
            intents.append(
                DurableOutboxIntent.create(
                    event_type=AiJobEventType.FAILED,
                    command=normalized,
                    attempt_number=normalized.attempt_number,
                    status=status,
                    occurred_at=now,
                )
            )
        replacement = self._next_state(
            state=state,
            jobs=state.jobs + (job,),
            outbox_intents=state.outbox_intents + tuple(intents),
        )
        committed = self._commit(snapshot=snapshot, replacement=replacement)
        return durable_job_view(
            state=committed,
            job=self._find_job(committed, normalized.ai_job_id),
            replayed=False,
        )

    def claim(
        self,
        *,
        queue_id: str,
        worker_id: str,
        lease_nonce_sha256: str,
        now: datetime,
    ) -> DurableLeaseClaim:
        """Claim one deterministic due AI job with an epoch/token fence."""

        self._guard()
        observed_at = require_durable_utc(now)
        normalized_worker_id = require_durable_token(worker_id)
        normalized_nonce = require_durable_sha256(lease_nonce_sha256)
        snapshot, state = self._load(queue_id=queue_id)
        candidates = tuple(
            job
            for job in state.jobs
            if job.status in {DurableJobStatus.READY, DurableJobStatus.RETRY_SCHEDULED}
            and job.available_at <= observed_at
            and observed_at < job.command.deadline_at
        )
        if not candidates:
            fail_durable_queue(DurableQueueFailureCode.JOB_NOT_CLAIMABLE)
        selected = min(
            candidates,
            key=lambda job: (job.available_at, str(job.command.ai_job_id)),
        )
        epoch = selected.lease_epoch + 1
        lease_token_sha256 = hashlib.sha256(
            b"ST-0706-LEASE-V2\x00"
            + state.queue_id.encode("ascii")
            + b"\x00"
            + str(selected.command.ai_job_id).encode("ascii")
            + b"\x00"
            + str(epoch).encode("ascii")
            + b"\x00"
            + normalized_nonce.encode("ascii")
        ).hexdigest()
        lease_until = min(
            observed_at + timedelta(seconds=30), selected.command.deadline_at
        )
        lease = DurableLease(
            worker_id=normalized_worker_id,
            lease_token_sha256=lease_token_sha256,
            epoch=epoch,
            claimed_at=observed_at,
            expires_at=lease_until,
        )
        claimed = replace(
            selected,
            status=DurableJobStatus.LEASED,
            lease_epoch=epoch,
            lease=lease,
            decision_code=None,
        )
        replacement = self._next_state(
            state=state,
            jobs=self._replace_job(state.jobs, claimed),
            outbox_intents=state.outbox_intents,
        )
        self._commit(snapshot=snapshot, replacement=replacement)
        return DurableLeaseClaim(
            queue_id=state.queue_id,
            ai_job_id=selected.command.ai_job_id,
            command_fingerprint_sha256=selected.command.fingerprint_sha256,
            worker_id=normalized_worker_id,
            lease_token_sha256=lease_token_sha256,
            lease_epoch=epoch,
            attempt_number=selected.attempt_number,
            leased_at=observed_at,
            leased_until=lease_until,
        )

    def complete(
        self,
        *,
        claim: DurableLeaseClaim,
        outcome: RecordedAttemptOutcome,
        now: datetime,
    ) -> DurableJobView:
        """Commit one fenced outcome or replay its exact durable receipt."""

        self._guard()
        if type(claim) is not DurableLeaseClaim:
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        normalized_claim: DurableLeaseClaim | None = None
        try:
            normalized_claim = DurableLeaseClaim(
                queue_id=claim.queue_id,
                ai_job_id=claim.ai_job_id,
                command_fingerprint_sha256=claim.command_fingerprint_sha256,
                worker_id=claim.worker_id,
                lease_token_sha256=claim.lease_token_sha256,
                lease_epoch=claim.lease_epoch,
                attempt_number=claim.attempt_number,
                leased_at=claim.leased_at,
                leased_until=claim.leased_until,
            )
        except Exception:
            pass
        if (
            normalized_claim is None
            or normalized_claim.fingerprint_sha256 != claim.fingerprint_sha256
        ):
            fail_durable_queue(DurableQueueFailureCode.LEASE_MISMATCH)
        claim = normalized_claim
        observed_at = require_durable_utc(now)
        normalized = _normalize_outcome(outcome)
        snapshot, state = self._load(queue_id=claim.queue_id)
        job = self._find_job(state, claim.ai_job_id)
        self._validate_claim_binding(claim=claim, job=job, outcome=normalized)

        for receipt in job.completion_receipts:
            if (
                receipt.lease_epoch == claim.lease_epoch
                and receipt.lease_token_sha256 == claim.lease_token_sha256
            ):
                if receipt.outcome_sha256 != normalized.fingerprint_sha256:
                    fail_durable_queue(DurableQueueFailureCode.COMPLETION_MISMATCH)
                if receipt.claim_sha256 != claim.fingerprint_sha256:
                    fail_durable_queue(DurableQueueFailureCode.LEASE_MISMATCH)
                return DurableJobView(
                    queue_id=state.queue_id,
                    state_revision=state.revision,
                    ai_job_id=job.command.ai_job_id,
                    command_fingerprint_sha256=job.command.fingerprint_sha256,
                    status=receipt.status,
                    attempt_number=receipt.attempt_number,
                    accumulated_cost_jpy=receipt.accumulated_cost_jpy,
                    available_at=receipt.available_at,
                    lease_epoch=receipt.lease_epoch,
                    decision_code=receipt.decision_code,
                    replayed=True,
                )

        lease = job.lease
        if (
            job.status is not DurableJobStatus.LEASED
            or lease is None
            or lease.worker_id != claim.worker_id
            or lease.epoch != claim.lease_epoch
            or lease.lease_token_sha256 != claim.lease_token_sha256
            or lease.claimed_at != claim.leased_at
            or lease.expires_at != claim.leased_until
            or observed_at >= lease.expires_at
        ):
            fail_durable_queue(DurableQueueFailureCode.LEASE_MISMATCH)

        transitioned = self._decide_completion(
            job=job, outcome=normalized, observed_at=observed_at
        )
        receipt = DurableCompletionReceipt(
            claim_sha256=claim.fingerprint_sha256,
            worker_id=claim.worker_id,
            lease_token_sha256=claim.lease_token_sha256,
            lease_epoch=claim.lease_epoch,
            claimed_attempt_number=claim.attempt_number,
            leased_at=claim.leased_at,
            leased_until=claim.leased_until,
            outcome_sha256=normalized.fingerprint_sha256,
            status=transitioned.status,
            attempt_number=transitioned.attempt_number,
            accumulated_cost_jpy=transitioned.accumulated_cost_jpy,
            available_at=transitioned.available_at,
            decision_code=transitioned.decision_code,
        )
        if len(job.completion_receipts) >= MAXIMUM_COMPLETION_RECEIPTS_PER_JOB:
            fail_durable_queue(DurableQueueFailureCode.CAPACITY_EXCEEDED)
        transitioned = replace(
            transitioned, completion_receipts=job.completion_receipts + (receipt,)
        )
        intents = state.outbox_intents
        if transitioned.status is DurableJobStatus.SUCCEEDED:
            intents += (
                DurableOutboxIntent.create(
                    event_type=AiJobEventType.SUCCEEDED,
                    command=job.command,
                    attempt_number=job.attempt_number,
                    status=transitioned.status,
                    occurred_at=observed_at,
                ),
            )
        elif transitioned.status not in {
            DurableJobStatus.READY,
            DurableJobStatus.LEASED,
            DurableJobStatus.RETRY_SCHEDULED,
        }:
            intents += (
                DurableOutboxIntent.create(
                    event_type=AiJobEventType.FAILED,
                    command=job.command,
                    attempt_number=job.attempt_number,
                    status=transitioned.status,
                    occurred_at=observed_at,
                ),
            )
        replacement = self._next_state(
            state=state,
            jobs=self._replace_job(state.jobs, transitioned),
            outbox_intents=intents,
        )
        committed = self._commit(snapshot=snapshot, replacement=replacement)
        return durable_job_view(
            state=committed,
            job=self._find_job(committed, job.command.ai_job_id),
            replayed=False,
        )

    def recover_next(self, *, queue_id: str, now: datetime) -> DurableJobView | None:
        """Recover one expired boundary; ambiguous leased work is quarantined."""

        self._guard()
        observed_at = require_durable_utc(now)
        snapshot, state = self._load(queue_id=queue_id)
        candidates = tuple(
            job
            for job in state.jobs
            if (
                job.status is DurableJobStatus.LEASED
                and job.lease is not None
                and job.lease.expires_at <= observed_at
            )
            or (
                job.status in {DurableJobStatus.READY, DurableJobStatus.RETRY_SCHEDULED}
                and job.command.deadline_at <= observed_at
            )
        )
        if not candidates:
            return None
        selected = min(
            candidates,
            key=lambda job: (job.command.deadline_at, str(job.command.ai_job_id)),
        )
        if selected.status is DurableJobStatus.LEASED:
            status = DurableJobStatus.QUARANTINED
            decision = DurableDecisionCode.LEASE_EXPIRED_AMBIGUOUS
        else:
            status = DurableJobStatus.EXPIRED
            decision = DurableDecisionCode.DEADLINE_EXPIRED
        transitioned = replace(
            selected,
            status=status,
            lease=None,
            decision_code=decision,
            available_at=observed_at,
        )
        intent = DurableOutboxIntent.create(
            event_type=AiJobEventType.FAILED,
            command=selected.command,
            attempt_number=selected.attempt_number,
            status=status,
            occurred_at=observed_at,
        )
        replacement = self._next_state(
            state=state,
            jobs=self._replace_job(state.jobs, transitioned),
            outbox_intents=state.outbox_intents + (intent,),
        )
        committed = self._commit(snapshot=snapshot, replacement=replacement)
        return durable_job_view(
            state=committed,
            job=self._find_job(committed, selected.command.ai_job_id),
            replayed=False,
        )

    def view(self, *, queue_id: str, ai_job_id: UUID) -> DurableJobView:
        """Load one metadata-only view without mutation."""

        self._guard()
        if type(ai_job_id) is not UUID:
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        _, state = self._load(queue_id=queue_id)
        return durable_job_view(
            state=state, job=self._find_job(state, ai_job_id), replayed=False
        )

    def outbox_intents(self, *, queue_id: str) -> tuple[DurableOutboxIntent, ...]:
        """Return immutable recorded intents; no dispatch method exists."""

        self._guard()
        _, state = self._load(queue_id=queue_id)
        return tuple(state.outbox_intents)

    def _guard(self) -> None:
        if not self._activation.enabled:
            fail_durable_queue(DurableQueueFailureCode.DISABLED)

    def _load(self, *, queue_id: str) -> tuple[DurableQueueSnapshot, DurableQueueState]:
        normalized_queue_id = require_durable_token(queue_id)
        snapshot: DurableQueueSnapshot | None = None
        try:
            observed = self._state.load(queue_id=normalized_queue_id)
            if type(observed) is DurableQueueSnapshot:
                snapshot = DurableQueueSnapshot(
                    queue_id=observed.queue_id,
                    revision=observed.revision,
                    state_bytes=observed.state_bytes,
                )
        except DurableQueueFailure:
            raise
        except Exception:
            pass
        if snapshot is None or snapshot.queue_id != normalized_queue_id:
            fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)
        return snapshot, snapshot_state(snapshot)

    def _commit(
        self, *, snapshot: DurableQueueSnapshot, replacement: DurableQueueState
    ) -> DurableQueueState:
        replacement_bytes = encode_durable_queue_state(replacement)
        observed: DurableQueueSnapshot | None = None
        try:
            candidate = self._state.compare_and_swap(
                queue_id=snapshot.queue_id,
                expected_revision=snapshot.revision,
                expected_state_sha256=snapshot.state_sha256,
                replacement_state_bytes=replacement_bytes,
            )
            if type(candidate) is DurableQueueSnapshot:
                observed = DurableQueueSnapshot(
                    queue_id=candidate.queue_id,
                    revision=candidate.revision,
                    state_bytes=candidate.state_bytes,
                )
        except DurableQueueFailure:
            raise
        except Exception:
            fail_durable_queue(DurableQueueFailureCode.COMMIT_UNCERTAIN)
        if (
            observed is None
            or observed.queue_id != snapshot.queue_id
            or observed.revision != snapshot.revision + 1
            or observed.state_bytes != replacement_bytes
        ):
            fail_durable_queue(DurableQueueFailureCode.COMMIT_UNCERTAIN)
        return snapshot_state(observed)

    @staticmethod
    def _next_state(
        *,
        state: DurableQueueState,
        jobs: tuple[DurableJobRecord, ...],
        outbox_intents: tuple[DurableOutboxIntent, ...],
    ) -> DurableQueueState:
        if len(outbox_intents) > MAXIMUM_OUTBOX_INTENTS:
            fail_durable_queue(DurableQueueFailureCode.OUTBOX_CAPACITY_EXCEEDED)
        return DurableQueueState(
            queue_id=state.queue_id,
            revision=state.revision + 1,
            jobs=jobs,
            outbox_intents=outbox_intents,
        )

    @staticmethod
    def _find_job(state: DurableQueueState, ai_job_id: UUID) -> DurableJobRecord:
        matches = tuple(job for job in state.jobs if job.command.ai_job_id == ai_job_id)
        if len(matches) != 1:
            fail_durable_queue(DurableQueueFailureCode.JOB_NOT_FOUND)
        return matches[0]

    @staticmethod
    def _replace_job(
        jobs: tuple[DurableJobRecord, ...], replacement: DurableJobRecord
    ) -> tuple[DurableJobRecord, ...]:
        found = False
        values: list[DurableJobRecord] = []
        for job in jobs:
            if job.command.ai_job_id == replacement.command.ai_job_id:
                values.append(replacement)
                found = True
            else:
                values.append(job)
        if not found:
            fail_durable_queue(DurableQueueFailureCode.JOB_NOT_FOUND)
        return tuple(values)

    @staticmethod
    def _validate_claim_binding(
        *,
        claim: DurableLeaseClaim,
        job: DurableJobRecord,
        outcome: RecordedAttemptOutcome,
    ) -> None:
        if (
            claim.command_fingerprint_sha256 != job.command.fingerprint_sha256
            or claim.attempt_number != outcome.attempt_number
            or claim.attempt_number > job.command.max_attempts
            or claim.ai_job_id != outcome.ai_job_id
            or claim.ai_job_id != job.command.ai_job_id
        ):
            fail_durable_queue(DurableQueueFailureCode.LEASE_MISMATCH)

    @staticmethod
    def _decide_completion(
        *,
        job: DurableJobRecord,
        outcome: RecordedAttemptOutcome,
        observed_at: datetime,
    ) -> DurableJobRecord:
        actual = outcome.actual_cost_jpy
        if actual is None:
            return replace(
                job,
                status=DurableJobStatus.QUARANTINED,
                lease=None,
                available_at=observed_at,
                decision_code=DurableDecisionCode.UNKNOWN_COST,
            )
        total = job.accumulated_cost_jpy + actual
        if total > job.command.authorization.reservation.reserved_jpy:
            return replace(
                job,
                status=DurableJobStatus.QUARANTINED,
                lease=None,
                available_at=observed_at,
                decision_code=DurableDecisionCode.COST_OVERRUN,
            )
        if observed_at >= job.command.deadline_at:
            return replace(
                job,
                status=DurableJobStatus.EXPIRED,
                accumulated_cost_jpy=total,
                lease=None,
                available_at=observed_at,
                decision_code=DurableDecisionCode.DEADLINE_EXPIRED,
            )
        if outcome.kind is RecordedAttemptKind.SUCCEEDED:
            return replace(
                job,
                status=DurableJobStatus.SUCCEEDED,
                accumulated_cost_jpy=total,
                lease=None,
                available_at=observed_at,
                decision_code=DurableDecisionCode.SUCCEEDED,
            )
        if outcome.kind is RecordedAttemptKind.INDETERMINATE:
            return replace(
                job,
                status=DurableJobStatus.QUARANTINED,
                accumulated_cost_jpy=total,
                lease=None,
                available_at=observed_at,
                decision_code=DurableDecisionCode.INDETERMINATE_OUTCOME,
            )
        if outcome.kind is RecordedAttemptKind.VALIDATION_FAILURE:
            decision = (
                DurableDecisionCode.VALIDATION_UNAVAILABLE
                if outcome.validation_status is ValidationStatus.UNAVAILABLE
                else DurableDecisionCode.VALIDATION_FAILED
            )
            return replace(
                job,
                status=DurableJobStatus.FAILED_TERMINAL,
                accumulated_cost_jpy=total,
                lease=None,
                available_at=observed_at,
                decision_code=decision,
            )

        failure_class = outcome.provider_failure_class
        attempt_limit = min(job.command.max_attempts, MAXIMUM_ATTEMPTS_CAP)
        can_retry = (
            outcome.retryable
            and failure_class in _RETRYABLE_FAILURES
            and job.attempt_number < attempt_limit
            and total < job.command.authorization.reservation.reserved_jpy
        )
        if can_retry:
            backoff = RETRY_BACKOFF_SECONDS_AFTER_ATTEMPT[job.attempt_number - 1]
            retry_at = observed_at + timedelta(seconds=backoff)
            if retry_at < job.command.deadline_at:
                return replace(
                    job,
                    status=DurableJobStatus.RETRY_SCHEDULED,
                    attempt_number=job.attempt_number + 1,
                    accumulated_cost_jpy=total,
                    available_at=retry_at,
                    lease=None,
                    decision_code=None,
                )
        exhausted = outcome.retryable and failure_class in _RETRYABLE_FAILURES
        return replace(
            job,
            status=(
                DurableJobStatus.DEAD_LETTERED
                if exhausted
                else DurableJobStatus.FAILED_TERMINAL
            ),
            accumulated_cost_jpy=total,
            lease=None,
            available_at=observed_at,
            decision_code=(
                DurableDecisionCode.RETRY_EXHAUSTED
                if exhausted
                else DurableDecisionCode.PROVIDER_TERMINAL
            ),
        )


__all__ = ["RecordedDurableAiJobQueueServiceV2"]

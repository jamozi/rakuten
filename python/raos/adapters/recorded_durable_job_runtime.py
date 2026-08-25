"""Transactional recorded adapter for the maximum-safe ST-1404 seam.

The adapter is deliberately limited to ENV-DEV and CI.  It implements an
ST-0308-compatible outer Unit of Work over immutable, clone-on-write state and
deterministic commit-fault injection.  The adapter performs no filesystem,
network, database, provider, or background-worker operation.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from threading import RLock
from types import TracebackType
from typing import Literal, Self
from uuid import UUID, uuid5

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ops.durable_job_runtime import (
    CommitFault,
    DeadLetterRecord,
    DurableDeliveryStart,
    DurableHandlerOutcome,
    DurableHandlerResult,
    DurableOutboxClaim,
    DurableWorkClaim,
    DurableWorkOutcome,
    DurableWorkResult,
    HandlerEffectRecord,
    OutboxLeaseRecord,
    QuarantineReleaseApproval,
    QuarantineReleaseRecord,
    QuarantineReplayClaim,
    QuarantineReplayOutcome,
    QuarantineReplayResult,
    RecoveryCandidate,
    RecoveryCandidateKind,
    RecoveryKind,
    RecoveryResult,
    WorkLeaseRecord,
)
from raos.domain.ops.job_runtime import (
    AttemptRecord,
    AttemptState,
    DeliveryStartOutcome,
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
    RecordedJobInvocation,
    RecordedJobMessage,
    RuntimeFailureCode,
    WorkClaim,
    fail_runtime,
    require_token,
    require_utc,
)
from raos.ports.persistence.context import PersistenceContext
from raos.domain.shared.identity import ActorType


@dataclass(frozen=True, slots=True, repr=False)
class RecordedDurableJobRuntimeSnapshot:
    """Immutable adapter restart image containing metadata and hashes only."""

    revision: int
    identity_counter: int
    fence_counter: int
    jobs: tuple[JobRecord, ...]
    attempts: tuple[AttemptRecord, ...]
    outboxes: tuple[OutboxRecord, ...]
    inboxes: tuple[InboxRecord, ...]
    transitions: tuple[JobTransition, ...]
    messages: tuple[RecordedJobMessage, ...]
    outbox_leases: tuple[OutboxLeaseRecord, ...]
    work_leases: tuple[WorkLeaseRecord, ...]
    effects: tuple[HandlerEffectRecord, ...]
    dead_letters: tuple[DeadLetterRecord, ...]
    quarantine_replays: tuple[QuarantineReplayClaim, ...]
    quarantine_releases: tuple[QuarantineReleaseRecord, ...]

    def __repr__(self) -> str:
        return "RecordedDurableJobRuntimeSnapshot(<redacted>)"


@dataclass(slots=True)
class _DurableState:
    identity_counter: int = 0
    fence_counter: int = 0
    jobs: dict[UUID, JobRecord] = field(default_factory=dict[UUID, JobRecord])
    attempts: dict[UUID, AttemptRecord] = field(
        default_factory=dict[UUID, AttemptRecord]
    )
    outboxes: dict[UUID, OutboxRecord] = field(default_factory=dict[UUID, OutboxRecord])
    inboxes: dict[InboxIdentity, InboxRecord] = field(
        default_factory=dict[InboxIdentity, InboxRecord]
    )
    transitions: list[JobTransition] = field(default_factory=list[JobTransition])
    messages: dict[UUID, RecordedJobMessage] = field(
        default_factory=dict[UUID, RecordedJobMessage]
    )
    outbox_leases: dict[UUID, OutboxLeaseRecord] = field(
        default_factory=dict[UUID, OutboxLeaseRecord]
    )
    work_leases: dict[InboxIdentity, WorkLeaseRecord] = field(
        default_factory=dict[InboxIdentity, WorkLeaseRecord]
    )
    effects: dict[UUID, HandlerEffectRecord] = field(
        default_factory=dict[UUID, HandlerEffectRecord]
    )
    dead_letters: dict[UUID, DeadLetterRecord] = field(
        default_factory=dict[UUID, DeadLetterRecord]
    )
    quarantine_replays: dict[UUID, QuarantineReplayClaim] = field(
        default_factory=dict[UUID, QuarantineReplayClaim]
    )
    quarantine_releases: dict[UUID, QuarantineReleaseRecord] = field(
        default_factory=dict[UUID, QuarantineReleaseRecord]
    )

    def clone(self) -> _DurableState:
        return _DurableState(
            identity_counter=self.identity_counter,
            fence_counter=self.fence_counter,
            jobs=dict(self.jobs),
            attempts=dict(self.attempts),
            outboxes=dict(self.outboxes),
            inboxes=dict(self.inboxes),
            transitions=list(self.transitions),
            messages=dict(self.messages),
            outbox_leases=dict(self.outbox_leases),
            work_leases=dict(self.work_leases),
            effects=dict(self.effects),
            dead_letters=dict(self.dead_letters),
            quarantine_replays=dict(self.quarantine_replays),
            quarantine_releases=dict(self.quarantine_releases),
        )


def _environment(value: object) -> RuntimeEnvironment:
    if type(value) is not RuntimeEnvironment or value not in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
    }:
        fail_runtime(RuntimeFailureCode.DEVELOPMENT_ONLY)
    return value


def _context(value: object) -> PersistenceContext:
    if type(value) is not PersistenceContext or value.actor.actor_type not in {
        ActorType.SERVICE,
        ActorType.SCHEDULE,
    }:
        fail_runtime(RuntimeFailureCode.DEVELOPMENT_ONLY)
    return value


def _unique(values: tuple[object, ...], keys: tuple[object, ...]) -> None:
    if len(values) != len(keys) or len(keys) != len(set(keys)):
        fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


class RecordedDurableJobRuntimeStore:
    """Revisioned state container and UoW factory for local deterministic use."""

    __slots__ = (
        "_commit_fault_index",
        "_commit_faults",
        "_environment",
        "_identity_namespace",
        "_lock",
        "_revision",
        "_state",
    )

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        identity_namespace: UUID,
        jobs: tuple[JobRecord, ...],
        outboxes: tuple[OutboxRecord, ...],
        attempts: tuple[AttemptRecord, ...] = (),
        inboxes: tuple[InboxRecord, ...] = (),
        commit_faults: tuple[CommitFault, ...] = (),
    ) -> None:
        self._environment = _environment(environment)
        if type(identity_namespace) is not UUID:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if (
            type(jobs) is not tuple
            or any(type(item) is not JobRecord for item in jobs)
            or type(outboxes) is not tuple
            or any(type(item) is not OutboxRecord for item in outboxes)
            or type(attempts) is not tuple
            or any(type(item) is not AttemptRecord for item in attempts)
            or type(inboxes) is not tuple
            or any(type(item) is not InboxRecord for item in inboxes)
            or type(commit_faults) is not tuple
            or any(type(item) is not CommitFault for item in commit_faults)
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        _unique(jobs, tuple(item.job_id for item in jobs))
        _unique(outboxes, tuple(item.event_id for item in outboxes))
        _unique(attempts, tuple(item.attempt_id for item in attempts))
        _unique(inboxes, tuple(item.identity for item in inboxes))
        self._identity_namespace = identity_namespace
        self._lock = RLock()
        self._revision = 0
        self._commit_faults = commit_faults
        self._commit_fault_index = 0
        state = _DurableState(
            jobs={item.job_id: item for item in jobs},
            attempts={item.attempt_id: item for item in attempts},
            outboxes={item.event_id: item for item in outboxes},
            inboxes={item.identity: item for item in inboxes},
        )
        for outbox in outboxes:
            job = state.jobs.get(outbox.job_id)
            if job is None:
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
            state.messages[outbox.event_id] = RecordedJobMessage(
                event_id=outbox.event_id,
                job_id=job.job_id,
                expected_job_version=job.version,
                job_schema_version=job.job_schema_version,
                payload_fingerprint=job.payload_fingerprint,
                deadline_at=job.deadline_at,
            )
        self._validate_state(state)
        self._state = state

    @classmethod
    def from_snapshot(
        cls,
        *,
        environment: RuntimeEnvironment,
        identity_namespace: UUID,
        snapshot: RecordedDurableJobRuntimeSnapshot,
        commit_faults: tuple[CommitFault, ...] = (),
    ) -> RecordedDurableJobRuntimeStore:
        _environment(environment)
        if (
            type(identity_namespace) is not UUID
            or type(snapshot) is not RecordedDurableJobRuntimeSnapshot
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        instance = cls(
            environment=environment,
            identity_namespace=identity_namespace,
            jobs=snapshot.jobs,
            outboxes=snapshot.outboxes,
            attempts=snapshot.attempts,
            inboxes=snapshot.inboxes,
            commit_faults=commit_faults,
        )
        state = _DurableState(
            identity_counter=snapshot.identity_counter,
            fence_counter=snapshot.fence_counter,
            jobs={item.job_id: item for item in snapshot.jobs},
            attempts={item.attempt_id: item for item in snapshot.attempts},
            outboxes={item.event_id: item for item in snapshot.outboxes},
            inboxes={item.identity: item for item in snapshot.inboxes},
            transitions=list(snapshot.transitions),
            messages={item.event_id: item for item in snapshot.messages},
            outbox_leases={item.event_id: item for item in snapshot.outbox_leases},
            work_leases={item.identity: item for item in snapshot.work_leases},
            effects={item.effect_id: item for item in snapshot.effects},
            dead_letters={item.dead_letter_id: item for item in snapshot.dead_letters},
            quarantine_replays={
                item.approval.job_id: item for item in snapshot.quarantine_replays
            },
            quarantine_releases={
                item.approval.approval_id: item for item in snapshot.quarantine_releases
            },
        )
        instance._validate_state(state)
        instance._state = state
        if type(snapshot.revision) is not int or snapshot.revision < 0:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        instance._revision = snapshot.revision
        return instance

    @property
    def environment(self) -> RuntimeEnvironment:
        return self._environment

    @property
    def identity_namespace(self) -> UUID:
        return self._identity_namespace

    def begin(self, context: PersistenceContext) -> RecordedDurableJobRuntimeUnitOfWork:
        return RecordedDurableJobRuntimeUnitOfWork(self, _context(context))

    def transaction_snapshot(self) -> tuple[int, _DurableState]:
        with self._lock:
            return self._revision, self._state.clone()

    def commit_transaction(
        self, *, expected_revision: int, replacement: _DurableState
    ) -> None:
        if type(expected_revision) is not int or type(replacement) is not _DurableState:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        self._validate_state(replacement)
        safe = replacement.clone()
        with self._lock:
            if self._revision != expected_revision:
                fail_runtime(RuntimeFailureCode.CONCURRENCY_CONFLICT)
            fault = (
                self._commit_faults[self._commit_fault_index]
                if self._commit_fault_index < len(self._commit_faults)
                else CommitFault.NONE
            )
            self._commit_fault_index += 1
            if fault is CommitFault.KNOWN_BEFORE_COMMIT:
                fail_runtime(RuntimeFailureCode.COMMIT_KNOWN_ROLLBACK)
            if fault is CommitFault.UNKNOWN_BEFORE_COMMIT:
                fail_runtime(RuntimeFailureCode.COMMIT_UNKNOWN)
            self._state = safe
            self._revision += 1
            if fault is CommitFault.UNKNOWN_AFTER_COMMIT:
                fail_runtime(RuntimeFailureCode.COMMIT_UNKNOWN)

    def snapshot(self) -> RecordedDurableJobRuntimeSnapshot:
        with self._lock:
            state = self._state
            return RecordedDurableJobRuntimeSnapshot(
                revision=self._revision,
                identity_counter=state.identity_counter,
                fence_counter=state.fence_counter,
                jobs=tuple(
                    sorted(state.jobs.values(), key=lambda item: item.job_id.int)
                ),
                attempts=tuple(
                    sorted(
                        state.attempts.values(),
                        key=lambda item: (item.job_id.int, item.attempt_number),
                    )
                ),
                outboxes=tuple(
                    sorted(state.outboxes.values(), key=lambda item: item.event_id.int)
                ),
                inboxes=tuple(
                    sorted(
                        state.inboxes.values(),
                        key=lambda item: (
                            item.identity.consumer_name,
                            item.identity.handler_version,
                            item.identity.event_id.int,
                        ),
                    )
                ),
                transitions=tuple(state.transitions),
                messages=tuple(
                    sorted(state.messages.values(), key=lambda item: item.event_id.int)
                ),
                outbox_leases=tuple(
                    sorted(
                        state.outbox_leases.values(),
                        key=lambda item: item.event_id.int,
                    )
                ),
                work_leases=tuple(
                    sorted(
                        state.work_leases.values(),
                        key=lambda item: (
                            item.identity.event_id.int,
                            item.fence,
                        ),
                    )
                ),
                effects=tuple(
                    sorted(state.effects.values(), key=lambda item: item.effect_id.int)
                ),
                dead_letters=tuple(
                    sorted(
                        state.dead_letters.values(),
                        key=lambda item: item.dead_letter_id.int,
                    )
                ),
                quarantine_replays=tuple(
                    sorted(
                        state.quarantine_replays.values(),
                        key=lambda item: item.approval.job_id.int,
                    )
                ),
                quarantine_releases=tuple(
                    sorted(
                        state.quarantine_releases.values(),
                        key=lambda item: item.approval.approval_id.int,
                    )
                ),
            )

    def job(self, job_id: UUID) -> JobRecord:
        with self._lock:
            value = self._state.jobs.get(job_id)
            if value is None:
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
            return value

    def outbox(self, event_id: UUID) -> OutboxRecord:
        with self._lock:
            value = self._state.outboxes.get(event_id)
            if value is None:
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
            return value

    def attempts_for(self, job_id: UUID) -> tuple[AttemptRecord, ...]:
        with self._lock:
            return tuple(
                sorted(
                    (
                        attempt
                        for attempt in self._state.attempts.values()
                        if attempt.job_id == job_id
                    ),
                    key=lambda item: item.attempt_number,
                )
            )

    def inbox(self, identity: InboxIdentity) -> InboxRecord | None:
        with self._lock:
            return self._state.inboxes.get(identity)

    def effects_for(self, job_id: UUID) -> tuple[HandlerEffectRecord, ...]:
        with self._lock:
            return tuple(
                sorted(
                    (
                        effect
                        for effect in self._state.effects.values()
                        if effect.job_id == job_id
                    ),
                    key=lambda item: item.effect_id.int,
                )
            )

    def dead_letters(self) -> tuple[DeadLetterRecord, ...]:
        with self._lock:
            return tuple(
                sorted(
                    self._state.dead_letters.values(),
                    key=lambda item: item.dead_letter_id.int,
                )
            )

    def transitions_for(self, job_id: UUID) -> tuple[JobTransition, ...]:
        with self._lock:
            return tuple(
                item for item in self._state.transitions if item.job_id == job_id
            )

    def quarantine_releases(self) -> tuple[QuarantineReleaseRecord, ...]:
        with self._lock:
            return tuple(
                sorted(
                    self._state.quarantine_releases.values(),
                    key=lambda item: item.approval.approval_id.int,
                )
            )

    @staticmethod
    def _validate_state(state: _DurableState) -> None:
        if (
            type(state.identity_counter) is not int
            or state.identity_counter < 0
            or type(state.fence_counter) is not int
            or state.fence_counter < 0
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        attempt_numbers: set[tuple[UUID, int]] = set()
        for attempt in state.attempts.values():
            key = (attempt.job_id, attempt.attempt_number)
            if attempt.job_id not in state.jobs or key in attempt_numbers:
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
            attempt_numbers.add(key)
        for event_id, outbox in state.outboxes.items():
            message = state.messages.get(event_id)
            job = state.jobs.get(outbox.job_id)
            if (
                job is None
                or message is None
                or message.event_id != event_id
                or message.job_id != job.job_id
                or message.job_schema_version != job.job_schema_version
                or message.payload_fingerprint != job.payload_fingerprint
            ):
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        for event_id, outbox_lease in state.outbox_leases.items():
            leased_outbox = state.outboxes.get(event_id)
            if (
                leased_outbox is None
                or leased_outbox.state is not OutboxState.DISPATCHING
            ):
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
            if outbox_lease.event_id != event_id:
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        for identity, work_lease in state.work_leases.items():
            job = state.jobs.get(work_lease.job_id)
            leased_attempt = state.attempts.get(work_lease.attempt_id)
            inbox = state.inboxes.get(identity)
            if (
                work_lease.identity != identity
                or job is None
                or job.state is not JobState.RUNNING
                or leased_attempt is None
                or leased_attempt.state is not AttemptState.RUNNING
                or inbox is None
                or inbox.state is not InboxState.PROCESSING
            ):
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        for effect in state.effects.values():
            if (
                effect.job_id not in state.jobs
                or effect.attempt_id not in state.attempts
            ):
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        for job_id, replay in state.quarantine_replays.items():
            replay_job = state.jobs.get(job_id)
            if (
                replay.approval.job_id != job_id
                or replay_job is None
                or replay_job.state is not JobState.QUARANTINED
                or replay_job.version != replay.approval.expected_job_version
                or state.messages.get(replay.message.event_id) != replay.message
            ):
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        for approval_id, release in state.quarantine_releases.items():
            if (
                release.approval.approval_id != approval_id
                or release.approval.job_id not in state.jobs
                or release.event_id not in state.outboxes
            ):
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


class RecordedDurableJobRuntimeUnitOfWork:
    """Single outer owner; clean exit without commit is a known rollback."""

    __slots__ = (
        "_base_revision",
        "_context",
        "_entered",
        "_repository",
        "_state",
        "_store",
    )

    def __init__(
        self,
        store: RecordedDurableJobRuntimeStore,
        context: PersistenceContext,
    ) -> None:
        self._store = store
        self._context = context
        self._entered = False
        self._base_revision: int | None = None
        self._state: _DurableState | None = None
        self._repository: RecordedDurableJobRuntimeRepository | None = None

    @property
    def context(self) -> PersistenceContext:
        return self._context

    @property
    def repository(self) -> RecordedDurableJobRuntimeRepository:
        if not self._entered or self._repository is None:
            fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
        return self._repository

    def __enter__(self) -> Self:
        if self._entered or self._state is not None:
            fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
        revision, state = self._store.transaction_snapshot()
        self._base_revision = revision
        self._state = state
        self._repository = RecordedDurableJobRuntimeRepository(
            state=state,
            identity_namespace=self._store.identity_namespace,
        )
        self._entered = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        del exc_value, traceback
        if self._entered:
            self.rollback()
        return False

    def commit(self) -> None:
        if not self._entered or self._base_revision is None or self._state is None:
            fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
        try:
            self._store.commit_transaction(
                expected_revision=self._base_revision,
                replacement=self._state,
            )
        finally:
            self._close()

    def rollback(self) -> None:
        if not self._entered:
            fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
        self._close()

    def _close(self) -> None:
        self._entered = False
        self._state = None
        self._repository = None
        self._base_revision = None


class RecordedDurableJobRuntimeRepository:
    """Repository operations over one transaction-private state clone."""

    __slots__ = ("_identity_namespace", "_state")

    def __init__(self, *, state: _DurableState, identity_namespace: UUID) -> None:
        if type(state) is not _DurableState or type(identity_namespace) is not UUID:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        self._state = state
        self._identity_namespace = identity_namespace

    def claim_due_outbox(
        self,
        *,
        now: datetime,
        owner: str,
        leased_until: datetime,
    ) -> DurableOutboxClaim | None:
        observed_at = require_utc(now)
        require_token(owner)
        lease_end = require_utc(leased_until)
        if lease_end <= observed_at:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        candidates = [
            outbox
            for outbox in self._state.outboxes.values()
            if outbox.state in {OutboxState.PENDING, OutboxState.FAILED}
            and outbox.available_at <= observed_at
            and self._state.jobs[outbox.job_id].state is JobState.REQUESTED
        ]
        if not candidates:
            return None
        outbox = min(
            candidates,
            key=lambda item: (item.available_at, item.created_at, item.event_id.int),
        )
        job = self._state.jobs[outbox.job_id]
        message = self._state.messages[outbox.event_id]
        claimed = replace(
            outbox,
            state=OutboxState.DISPATCHING,
            publish_attempts=outbox.publish_attempts + 1,
            failure_code=None,
        )
        self._state.outboxes[outbox.event_id] = claimed
        lease = OutboxLeaseRecord(
            event_id=outbox.event_id,
            owner=owner,
            lease_id=self._new_uuid("outbox-lease"),
            fence=self._new_fence(),
            leased_until=lease_end,
        )
        self._state.outbox_leases[outbox.event_id] = lease
        return DurableOutboxClaim(
            claim=OutboxDispatchClaim(
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
            ),
            owner=owner,
            lease_id=lease.lease_id,
            fence=lease.fence,
            leased_until=lease.leased_until,
        )

    def publish_succeeded(
        self,
        *,
        claim: DurableOutboxClaim,
        published_at: datetime,
    ) -> tuple[OutboxRecord, int]:
        completed_at = require_utc(published_at)
        outbox, job = self._dispatch_records(claim, at=completed_at)
        if (
            job.state is not JobState.REQUESTED
            or job.version != claim.claim.expected_job_version
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
        self._state.outboxes[outbox.event_id] = published
        del self._state.outbox_leases[outbox.event_id]
        self._transition(job, queued, completed_at)
        return published, queued.version

    def publish_failed(
        self,
        *,
        claim: DurableOutboxClaim,
        failed_at: datetime,
        retry_at: datetime | None,
        failure_code: RuntimeFailureCode,
    ) -> OutboxRecord:
        observed_at = require_utc(failed_at)
        if type(failure_code) is not RuntimeFailureCode:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if retry_at is not None:
            retry_at = require_utc(retry_at)
            if retry_at < observed_at:
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        outbox, _job = self._dispatch_records(claim, at=observed_at)
        failed = replace(
            outbox,
            state=OutboxState.FAILED if retry_at is not None else OutboxState.DEAD,
            available_at=retry_at if retry_at is not None else observed_at,
            failure_code=failure_code,
        )
        self._state.outboxes[outbox.event_id] = failed
        del self._state.outbox_leases[outbox.event_id]
        if failed.state is OutboxState.DEAD:
            self._dead_letter(
                event_id=outbox.event_id,
                job_id=outbox.job_id,
                attempt_number=0,
                state=OutboxState.DEAD,
                failure_code=failure_code,
                recorded_at=observed_at,
            )
        return failed

    def begin_delivery(
        self,
        *,
        message: RecordedJobMessage,
        consumer_name: str,
        handler_version: str,
        owner: str,
        delivery_attempt: int,
        queue_leased_until: datetime,
        job_leased_until: datetime,
        now: datetime,
    ) -> DurableDeliveryStart:
        if type(message) is not RecordedJobMessage:
            fail_runtime(RuntimeFailureCode.MALFORMED_DELIVERY)
        require_token(consumer_name)
        require_token(handler_version)
        require_token(owner)
        if type(delivery_attempt) is not int or delivery_attempt < 1:
            fail_runtime(RuntimeFailureCode.MALFORMED_DELIVERY)
        queue_end = require_utc(queue_leased_until)
        job_end = require_utc(job_leased_until)
        observed_at = require_utc(now)
        if queue_end <= observed_at or job_end <= observed_at:
            fail_runtime(RuntimeFailureCode.STALE_LEASE)
        lease_end = min(queue_end, job_end)
        expected_message = self._state.messages.get(message.event_id)
        outbox = self._state.outboxes.get(message.event_id)
        job = self._state.jobs.get(message.job_id)
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
        identity = InboxIdentity(consumer_name, handler_version, message.event_id)
        inbox = self._state.inboxes.get(identity)
        if inbox is not None and inbox.state is InboxState.PROCESSING:
            return self._delivery_start(
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
            return self._delivery_start(
                outcome=DeliveryStartOutcome.ACK_DUPLICATE,
                message=message,
                job=job,
                expected_version=initial_version,
            )
        if job.state is JobState.CANCELLED:
            return self._delivery_start(
                outcome=DeliveryStartOutcome.CANCELLED,
                message=message,
                job=job,
                expected_version=initial_version,
            )
        if job.state is JobState.EXPIRED:
            return self._delivery_start(
                outcome=DeliveryStartOutcome.EXPIRED,
                message=message,
                job=job,
                expected_version=initial_version,
            )
        if job.state in {
            JobState.SUCCEEDED,
            JobState.FAILED_TERMINAL,
            JobState.QUARANTINED,
        }:
            return self._delivery_start(
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
                return self._delivery_start(
                    outcome=DeliveryStartOutcome.RETRY_STATE_HELD,
                    message=message,
                    job=job,
                    expected_version=initial_version,
                )
            inbox = replace(
                inbox,
                state=InboxState.PROCESSING,
                received_at=observed_at,
                processed_at=None,
                result_fingerprint=None,
                failure_code=None,
            )
            self._state.inboxes[identity] = inbox
            queued = replace(
                job,
                state=JobState.QUEUED,
                version=job.version + 1,
                lease=None,
                completed_at=None,
                result_fingerprint=None,
            )
            self._transition(job, queued, observed_at)
            job = queued
        if job.state is not JobState.QUEUED:
            return self._delivery_start(
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
            self._state.inboxes[identity] = inbox
        elif inbox.state is InboxState.FAILED:
            inbox = replace(
                inbox,
                state=InboxState.PROCESSING,
                received_at=observed_at,
                processed_at=None,
                result_fingerprint=None,
                failure_code=None,
            )
            self._state.inboxes[identity] = inbox
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
            self._state.inboxes[identity] = ignored
            self._transition(job, cancelled, observed_at)
            return self._delivery_start(
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
            self._state.inboxes[identity] = ignored
            self._transition(job, expired, observed_at)
            return self._delivery_start(
                outcome=DeliveryStartOutcome.EXPIRED,
                message=message,
                job=expired,
                expected_version=initial_version,
            )
        if job.attempt_count >= job.max_attempts:
            return self._delivery_start(
                outcome=DeliveryStartOutcome.NOT_READY_HELD,
                message=message,
                job=job,
                expected_version=initial_version,
            )
        attempt_number = job.attempt_count + 1
        attempt_id = self._new_uuid("attempt")
        lease_id = self._new_uuid("work-lease")
        running = replace(
            job,
            state=JobState.RUNNING,
            version=job.version + 1,
            attempt_count=attempt_number,
            lease=JobLease(lease_id=lease_id, expires_at=lease_end),
            completed_at=None,
            result_fingerprint=None,
        )
        self._transition(job, running, observed_at)
        attempt = AttemptRecord(
            attempt_id=attempt_id,
            job_id=job.job_id,
            attempt_number=attempt_number,
            state=AttemptState.RUNNING,
            handler_version=handler_version,
            started_at=observed_at,
        )
        self._state.attempts[attempt_id] = attempt
        invocation = RecordedJobInvocation(
            event_id=message.event_id,
            job_id=job.job_id,
            attempt_id=attempt_id,
            attempt_number=attempt_number,
            payload_fingerprint=job.payload_fingerprint,
            started_at=observed_at,
            deadline_at=job.deadline_at,
        )
        base_claim = WorkClaim(
            event_id=message.event_id,
            job_id=job.job_id,
            inbox_id=inbox.inbox_id,
            attempt_id=attempt_id,
            attempt_number=attempt_number,
            lease_id=lease_id,
            leased_until=lease_end,
            expected_job_version=initial_version,
            running_job_version=running.version,
            delivery_attempt=delivery_attempt,
            invocation=invocation,
        )
        fence = self._new_fence()
        self._state.work_leases[identity] = WorkLeaseRecord(
            identity=identity,
            job_id=job.job_id,
            attempt_id=attempt_id,
            owner=owner,
            lease_id=lease_id,
            fence=fence,
            delivery_attempt=delivery_attempt,
            leased_until=lease_end,
        )
        return DurableDeliveryStart(
            outcome=DeliveryStartOutcome.EXECUTE,
            event_id=message.event_id,
            job_id=job.job_id,
            job_state=JobState.RUNNING,
            expected_job_version=initial_version,
            post_job_version=running.version,
            claim=DurableWorkClaim(claim=base_claim, owner=owner, fence=fence),
        )

    def complete_delivery(
        self,
        *,
        claim: DurableWorkClaim,
        result: DurableHandlerResult,
        retry_at: datetime | None,
    ) -> DurableWorkResult:
        if (
            type(claim) is not DurableWorkClaim
            or type(result) is not DurableHandlerResult
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        completed_at = result.completed_at
        if retry_at is not None:
            retry_at = require_utc(retry_at)
            if retry_at < completed_at:
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        base = claim.claim
        job = self._state.jobs.get(base.job_id)
        attempt = self._state.attempts.get(base.attempt_id)
        identity, inbox, lease = self._work_records(claim)
        if job is None or attempt is None:
            fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
        invocation = base.invocation
        if (
            attempt.job_id != base.job_id
            or attempt.attempt_number != base.attempt_number
            or attempt.handler_version != identity.handler_version
            or attempt.started_at != invocation.started_at
            or identity.event_id != base.event_id
            or invocation.event_id != base.event_id
            or invocation.job_id != base.job_id
            or invocation.attempt_id != base.attempt_id
            or invocation.attempt_number != base.attempt_number
            or invocation.payload_fingerprint != job.payload_fingerprint
            or invocation.deadline_at != job.deadline_at
            or job.attempt_count != base.attempt_number
        ):
            fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
        if (
            job.state is not JobState.RUNNING
            or attempt.state is not AttemptState.RUNNING
            or inbox.state is not InboxState.PROCESSING
        ):
            fail_runtime(RuntimeFailureCode.STALE_VERSION)
        version_matches = job.version == base.running_job_version
        cancellation_only_update = (
            job.cancel_requested_at is not None
            and job.version == base.running_job_version + 1
        )
        if not (version_matches or cancellation_only_update):
            fail_runtime(RuntimeFailureCode.STALE_VERSION)
        if (
            job.lease is None
            or job.lease.lease_id != base.lease_id
            or job.lease.expires_at != base.leased_until
            or lease.leased_until <= completed_at
        ):
            fail_runtime(RuntimeFailureCode.STALE_LEASE)
        if job.cancel_requested_at is not None:
            return self._finish_cancelled(
                job, attempt, inbox, identity, base, completed_at
            )
        if job.deadline_at is not None and job.deadline_at <= completed_at:
            return self._finish_expired(
                job, attempt, inbox, identity, base, completed_at
            )
        if result.outcome is DurableHandlerOutcome.SUCCEEDED:
            return self._finish_succeeded(job, attempt, inbox, identity, base, result)
        if result.outcome is DurableHandlerOutcome.QUARANTINE:
            return self._finish_quarantined(job, attempt, inbox, identity, base, result)
        if result.outcome is DurableHandlerOutcome.TERMINAL_FAILURE:
            return self._finish_terminal(job, attempt, inbox, identity, base, result)
        return self._finish_retryable(
            job, attempt, inbox, identity, base, result, retry_at
        )

    def request_cancellation(
        self,
        *,
        job_id: UUID,
        expected_job_version: int,
        requested_at: datetime,
    ) -> JobRecord:
        if type(job_id) is not UUID or (
            type(expected_job_version) is not int or expected_job_version < 0
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        observed_at = require_utc(requested_at)
        job = self._state.jobs.get(job_id)
        if job is None or job.version != expected_job_version:
            fail_runtime(RuntimeFailureCode.STALE_VERSION)
        if observed_at < job.created_at:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if job.state is JobState.CANCELLED:
            if job.cancel_requested_at != observed_at:
                fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
            return job
        if job.state in {
            JobState.SUCCEEDED,
            JobState.FAILED_TERMINAL,
            JobState.QUARANTINED,
            JobState.EXPIRED,
        }:
            fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
        if job.cancel_requested_at is not None:
            if job.cancel_requested_at != observed_at:
                fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
            return job
        if job.state in {JobState.REQUESTED, JobState.QUEUED}:
            cancelled = replace(
                job,
                state=JobState.CANCELLED,
                version=job.version + 1,
                cancel_requested_at=observed_at,
                completed_at=observed_at,
                lease=None,
                result_fingerprint=None,
            )
            self._transition(job, cancelled, observed_at)
            return cancelled
        recorded = replace(
            job,
            version=job.version + 1,
            cancel_requested_at=observed_at,
        )
        self._state.jobs[job.job_id] = recorded
        return recorded

    def recovery_candidate(self, *, now: datetime) -> RecoveryCandidate | None:
        observed_at = require_utc(now)
        expired_outboxes = [
            lease
            for lease in self._state.outbox_leases.values()
            if lease.leased_until <= observed_at
        ]
        if expired_outboxes:
            lease = min(
                expired_outboxes,
                key=lambda item: (item.leased_until, item.event_id.int),
            )
            outbox = self._state.outboxes[lease.event_id]
            return RecoveryCandidate(
                kind=RecoveryCandidateKind.OUTBOX,
                observed_at=observed_at,
                event_id=lease.event_id,
                job_id=outbox.job_id,
                lease_id=lease.lease_id,
                fence=lease.fence,
                attempt_number=outbox.publish_attempts,
            )
        expired_work = [
            lease
            for lease in self._state.work_leases.values()
            if lease.leased_until <= observed_at
        ]
        if expired_work:
            work_lease = min(
                expired_work,
                key=lambda item: (item.leased_until, item.job_id.int, item.fence),
            )
            job = self._state.jobs[work_lease.job_id]
            attempt = self._state.attempts[work_lease.attempt_id]
            return RecoveryCandidate(
                kind=RecoveryCandidateKind.WORK,
                observed_at=observed_at,
                event_id=work_lease.identity.event_id,
                job_id=work_lease.job_id,
                lease_id=work_lease.lease_id,
                fence=work_lease.fence,
                attempt_number=attempt.attempt_number,
                expected_job_version=job.version,
            )
        held = [
            job
            for job in self._state.jobs.values()
            if job.state is JobState.RETRY_SCHEDULED
            and (
                job.cancel_requested_at is not None
                or (job.deadline_at is not None and job.deadline_at <= observed_at)
            )
        ]
        if held:
            job = min(held, key=lambda item: item.job_id.int)
            event_id = next(
                outbox.event_id
                for outbox in self._state.outboxes.values()
                if outbox.job_id == job.job_id
            )
            return RecoveryCandidate(
                kind=RecoveryCandidateKind.RETRY_STATE_HELD,
                observed_at=observed_at,
                event_id=event_id,
                job_id=job.job_id,
                attempt_number=job.attempt_count,
                expected_job_version=job.version,
            )
        return None

    def recover(
        self,
        *,
        candidate: RecoveryCandidate,
        recovered_at: datetime,
        retry_at: datetime | None,
    ) -> RecoveryResult:
        if type(candidate) is not RecoveryCandidate:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        observed_at = require_utc(recovered_at)
        if observed_at < candidate.observed_at:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if retry_at is not None:
            retry_at = require_utc(retry_at)
            if retry_at < observed_at:
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if candidate.kind is RecoveryCandidateKind.RETRY_STATE_HELD:
            if candidate.job_id is None:
                fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
            job = self._state.jobs.get(candidate.job_id)
            if (
                job is None
                or job.state is not JobState.RETRY_SCHEDULED
                or job.version != candidate.expected_job_version
                or not (
                    job.cancel_requested_at is not None
                    or (job.deadline_at is not None and job.deadline_at <= observed_at)
                )
            ):
                fail_runtime(RuntimeFailureCode.STALE_VERSION)
            return RecoveryResult(
                kind=RecoveryKind.RETRY_STATE_HELD,
                event_id=candidate.event_id,
                job_id=job.job_id,
                job_state=job.state,
            )
        if candidate.kind is RecoveryCandidateKind.OUTBOX:
            if (
                candidate.event_id is None
                or candidate.lease_id is None
                or candidate.fence is None
            ):
                fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
            lease = self._state.outbox_leases.get(candidate.event_id)
            outbox = self._state.outboxes.get(candidate.event_id)
            if (
                lease is None
                or outbox is None
                or outbox.state is not OutboxState.DISPATCHING
                or lease.lease_id != candidate.lease_id
                or lease.fence != candidate.fence
                or lease.leased_until > observed_at
            ):
                fail_runtime(RuntimeFailureCode.STALE_LEASE)
            state = OutboxState.FAILED if retry_at is not None else OutboxState.DEAD
            recovered = replace(
                outbox,
                state=state,
                available_at=retry_at if retry_at is not None else observed_at,
                failure_code=RuntimeFailureCode.ORPHANED_LEASE,
            )
            self._state.outboxes[outbox.event_id] = recovered
            del self._state.outbox_leases[outbox.event_id]
            if state is OutboxState.DEAD:
                self._dead_letter(
                    event_id=outbox.event_id,
                    job_id=outbox.job_id,
                    attempt_number=0,
                    state=state,
                    failure_code=RuntimeFailureCode.ORPHANED_LEASE,
                    recorded_at=observed_at,
                )
            return RecoveryResult(
                kind=(
                    RecoveryKind.OUTBOX_RETRY_SCHEDULED
                    if state is OutboxState.FAILED
                    else RecoveryKind.OUTBOX_DEAD
                ),
                event_id=outbox.event_id,
                job_id=outbox.job_id,
                outbox_state=state,
                retry_at=retry_at,
                failure_code=RuntimeFailureCode.ORPHANED_LEASE,
            )
        return self._recover_work(candidate, observed_at=observed_at, retry_at=retry_at)

    def prepare_quarantine_replay(
        self,
        *,
        approval: QuarantineReleaseApproval,
        owner: str,
        leased_until: datetime,
        now: datetime,
    ) -> QuarantineReplayClaim:
        if type(approval) is not QuarantineReleaseApproval:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_token(owner)
        observed_at = require_utc(now)
        lease_end = require_utc(leased_until)
        if lease_end <= observed_at or approval.approved_at > observed_at:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        job = self._state.jobs.get(approval.job_id)
        if (
            job is None
            or job.state is not JobState.QUARANTINED
            or job.version != approval.expected_job_version
        ):
            fail_runtime(RuntimeFailureCode.STALE_VERSION)
        existing = self._state.quarantine_replays.get(job.job_id)
        if existing is not None and existing.leased_until > observed_at:
            if existing.approval != approval:
                fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
            return existing
        message = next(
            (
                message
                for message in self._state.messages.values()
                if message.job_id == job.job_id
            ),
            None,
        )
        if message is None:
            fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
        outbox = self._state.outboxes.get(message.event_id)
        if outbox is None:
            fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
        claim = QuarantineReplayClaim(
            approval=approval,
            message=message,
            queue_name=job.queue_name,
            available_at=outbox.message_available_at,
            delivery_max_attempts=job.delivery_max_attempts,
            owner=owner,
            lease_id=self._new_uuid("quarantine-replay"),
            fence=self._new_fence(),
            prepared_at=observed_at,
            leased_until=lease_end,
        )
        self._state.quarantine_replays[job.job_id] = claim
        return claim

    def finalize_quarantine_replay(
        self,
        *,
        claim: QuarantineReplayClaim,
        finalized_at: datetime,
    ) -> QuarantineReplayResult:
        if type(claim) is not QuarantineReplayClaim:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        observed_at = require_utc(finalized_at)
        current = self._state.quarantine_replays.get(claim.approval.job_id)
        job = self._state.jobs.get(claim.approval.job_id)
        if current != claim or current is None or current.leased_until <= observed_at:
            fail_runtime(RuntimeFailureCode.STALE_LEASE)
        if (
            job is None
            or job.state is not JobState.QUARANTINED
            or job.version != claim.approval.expected_job_version
        ):
            fail_runtime(RuntimeFailureCode.STALE_VERSION)
        queued = replace(
            job,
            state=JobState.QUEUED,
            version=job.version + 1,
            available_at=observed_at,
            completed_at=None,
            lease=None,
            result_fingerprint=None,
            failure_code=None,
        )
        self._transition(job, queued, observed_at)
        release = QuarantineReleaseRecord(
            approval=claim.approval,
            event_id=claim.message.event_id,
            owner=claim.owner,
            lease_id=claim.lease_id,
            fence=claim.fence,
            prepared_at=claim.prepared_at,
            finalized_at=observed_at,
            post_job_version=queued.version,
        )
        current_release = self._state.quarantine_releases.get(
            claim.approval.approval_id
        )
        if current_release is not None and current_release != release:
            fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
        self._state.quarantine_releases[claim.approval.approval_id] = release
        del self._state.quarantine_replays[job.job_id]
        return QuarantineReplayResult(
            outcome=QuarantineReplayOutcome.PREPARED_AND_SENT,
            job_id=job.job_id,
            event_id=claim.message.event_id,
            job_state=queued.state,
        )

    def _dispatch_records(
        self,
        claim: DurableOutboxClaim,
        *,
        at: datetime,
    ) -> tuple[OutboxRecord, JobRecord]:
        if type(claim) is not DurableOutboxClaim:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if claim.leased_until <= at:
            fail_runtime(RuntimeFailureCode.STALE_LEASE)
        base = claim.claim
        outbox = self._state.outboxes.get(base.event_id)
        job = self._state.jobs.get(base.job_id)
        lease = self._state.outbox_leases.get(base.event_id)
        message = self._state.messages.get(base.event_id)
        if (
            outbox is None
            or job is None
            or lease is None
            or message is None
            or outbox.job_id != job.job_id
            or outbox.state is not OutboxState.DISPATCHING
            or outbox.publish_attempts != base.publish_attempt
            or lease.owner != claim.owner
            or lease.lease_id != claim.lease_id
            or lease.fence != claim.fence
            or lease.leased_until != claim.leased_until
            or job.queue_name != base.queue_name
            or message.payload_fingerprint != base.payload_fingerprint
            or message.job_schema_version != base.job_schema_version
            or message.deadline_at != base.deadline_at
        ):
            fail_runtime(RuntimeFailureCode.STALE_LEASE)
        return outbox, job

    def _work_records(
        self,
        claim: DurableWorkClaim,
    ) -> tuple[InboxIdentity, InboxRecord, WorkLeaseRecord]:
        base = claim.claim
        matches = [
            (identity, lease)
            for identity, lease in self._state.work_leases.items()
            if lease.lease_id == base.lease_id
        ]
        if len(matches) != 1:
            fail_runtime(RuntimeFailureCode.STALE_LEASE)
        identity, lease = matches[0]
        inbox = self._state.inboxes.get(identity)
        if (
            inbox is None
            or inbox.inbox_id != base.inbox_id
            or lease.job_id != base.job_id
            or lease.attempt_id != base.attempt_id
            or lease.owner != claim.owner
            or lease.fence != claim.fence
            or lease.delivery_attempt != base.delivery_attempt
            or lease.leased_until != base.leased_until
        ):
            fail_runtime(RuntimeFailureCode.STALE_LEASE)
        return identity, inbox, lease

    def _finish_cancelled(
        self,
        job: JobRecord,
        attempt: AttemptRecord,
        inbox: InboxRecord,
        identity: InboxIdentity,
        claim: WorkClaim,
        completed_at: datetime,
    ) -> DurableWorkResult:
        self._state.attempts[attempt.attempt_id] = replace(
            attempt,
            state=AttemptState.CANCELLED,
            completed_at=completed_at,
        )
        self._state.inboxes[identity] = replace(
            inbox,
            state=InboxState.IGNORED,
            processed_at=completed_at,
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
        self._transition(job, cancelled, completed_at)
        del self._state.work_leases[identity]
        return self._work_result(DurableWorkOutcome.CANCELLED, claim, cancelled)

    def _finish_expired(
        self,
        job: JobRecord,
        attempt: AttemptRecord,
        inbox: InboxRecord,
        identity: InboxIdentity,
        claim: WorkClaim,
        completed_at: datetime,
    ) -> DurableWorkResult:
        self._state.attempts[attempt.attempt_id] = replace(
            attempt,
            state=AttemptState.TIMED_OUT,
            completed_at=completed_at,
        )
        self._state.inboxes[identity] = replace(
            inbox,
            state=InboxState.IGNORED,
            processed_at=completed_at,
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
        self._transition(job, expired, completed_at)
        del self._state.work_leases[identity]
        return self._work_result(DurableWorkOutcome.EXPIRED, claim, expired)

    def _finish_succeeded(
        self,
        job: JobRecord,
        attempt: AttemptRecord,
        inbox: InboxRecord,
        identity: InboxIdentity,
        claim: WorkClaim,
        result: DurableHandlerResult,
    ) -> DurableWorkResult:
        if result.result_fingerprint is None:
            fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
        for effect in result.effects:
            record = HandlerEffectRecord(
                effect_id=effect.effect_id,
                job_id=job.job_id,
                attempt_id=attempt.attempt_id,
                kind=effect.kind,
                fingerprint=effect.fingerprint,
                committed_at=result.completed_at,
            )
            current = self._state.effects.get(effect.effect_id)
            if current is not None and current != record:
                fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
            self._state.effects[effect.effect_id] = record
        self._state.attempts[attempt.attempt_id] = replace(
            attempt,
            state=AttemptState.SUCCEEDED,
            completed_at=result.completed_at,
            result_fingerprint=result.result_fingerprint,
        )
        self._state.inboxes[identity] = replace(
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
        self._transition(job, succeeded, result.completed_at)
        del self._state.work_leases[identity]
        return self._work_result(DurableWorkOutcome.SUCCEEDED, claim, succeeded)

    def _finish_terminal(
        self,
        job: JobRecord,
        attempt: AttemptRecord,
        inbox: InboxRecord,
        identity: InboxIdentity,
        claim: WorkClaim,
        result: DurableHandlerResult,
    ) -> DurableWorkResult:
        failure = result.failure_code
        if failure is None:
            fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
        self._state.attempts[attempt.attempt_id] = replace(
            attempt,
            state=AttemptState.FAILED,
            completed_at=result.completed_at,
            failure_code=failure,
        )
        self._state.inboxes[identity] = replace(
            inbox,
            state=InboxState.FAILED,
            processed_at=result.completed_at,
            failure_code=failure,
        )
        terminal = replace(
            job,
            state=JobState.FAILED_TERMINAL,
            version=job.version + 1,
            completed_at=result.completed_at,
            lease=None,
            result_fingerprint=None,
            failure_code=failure,
        )
        self._transition(job, terminal, result.completed_at)
        del self._state.work_leases[identity]
        self._dead_letter(
            event_id=claim.event_id,
            job_id=job.job_id,
            attempt_number=claim.attempt_number,
            state=terminal.state,
            failure_code=failure,
            recorded_at=result.completed_at,
        )
        return self._work_result(DurableWorkOutcome.FAILED_TERMINAL, claim, terminal)

    def _finish_quarantined(
        self,
        job: JobRecord,
        attempt: AttemptRecord,
        inbox: InboxRecord,
        identity: InboxIdentity,
        claim: WorkClaim,
        result: DurableHandlerResult,
    ) -> DurableWorkResult:
        failure = result.failure_code
        if failure is None:
            fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
        self._state.attempts[attempt.attempt_id] = replace(
            attempt,
            state=AttemptState.FAILED,
            completed_at=result.completed_at,
            failure_code=failure,
        )
        self._state.inboxes[identity] = replace(
            inbox,
            state=InboxState.FAILED,
            processed_at=result.completed_at,
            failure_code=failure,
        )
        quarantined = replace(
            job,
            state=JobState.QUARANTINED,
            version=job.version + 1,
            completed_at=result.completed_at,
            lease=None,
            result_fingerprint=None,
            failure_code=failure,
        )
        self._transition(job, quarantined, result.completed_at)
        del self._state.work_leases[identity]
        self._dead_letter(
            event_id=claim.event_id,
            job_id=job.job_id,
            attempt_number=claim.attempt_number,
            state=quarantined.state,
            failure_code=failure,
            recorded_at=result.completed_at,
        )
        return self._work_result(DurableWorkOutcome.QUARANTINED, claim, quarantined)

    def _finish_retryable(
        self,
        job: JobRecord,
        attempt: AttemptRecord,
        inbox: InboxRecord,
        identity: InboxIdentity,
        claim: WorkClaim,
        result: DurableHandlerResult,
        retry_at: datetime | None,
    ) -> DurableWorkResult:
        failure = result.failure_code
        if failure is None:
            fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
        self._state.attempts[attempt.attempt_id] = replace(
            attempt,
            state=AttemptState.FAILED,
            completed_at=result.completed_at,
            retry_after_at=retry_at,
            failure_code=failure,
        )
        self._state.inboxes[identity] = replace(
            inbox,
            state=InboxState.FAILED,
            processed_at=result.completed_at,
            failure_code=failure,
        )
        retryable = replace(
            job,
            state=JobState.FAILED_RETRYABLE,
            version=job.version + 1,
            completed_at=None,
            lease=None,
            result_fingerprint=None,
            failure_code=failure,
        )
        self._transition(job, retryable, result.completed_at)
        if retry_at is None or job.attempt_count >= job.max_attempts:
            terminal_failure = (
                RuntimeFailureCode.RETRY_BUDGET_EXHAUSTED
                if retry_at is None
                else failure
            )
            terminal = replace(
                retryable,
                state=JobState.FAILED_TERMINAL,
                version=retryable.version + 1,
                completed_at=result.completed_at,
                failure_code=terminal_failure,
            )
            self._transition(retryable, terminal, result.completed_at)
            del self._state.work_leases[identity]
            self._dead_letter(
                event_id=claim.event_id,
                job_id=job.job_id,
                attempt_number=claim.attempt_number,
                state=terminal.state,
                failure_code=terminal_failure,
                recorded_at=result.completed_at,
            )
            return self._work_result(
                DurableWorkOutcome.FAILED_TERMINAL,
                claim,
                terminal,
            )
        scheduled = replace(
            retryable,
            state=JobState.RETRY_SCHEDULED,
            version=retryable.version + 1,
            available_at=retry_at,
        )
        self._transition(retryable, scheduled, result.completed_at)
        del self._state.work_leases[identity]
        return self._work_result(
            DurableWorkOutcome.RETRY_SCHEDULED,
            claim,
            scheduled,
        )

    def _recover_work(
        self,
        candidate: RecoveryCandidate,
        *,
        observed_at: datetime,
        retry_at: datetime | None,
    ) -> RecoveryResult:
        if (
            candidate.job_id is None
            or candidate.event_id is None
            or candidate.lease_id is None
            or candidate.fence is None
        ):
            fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
        matches = [
            (identity, lease)
            for identity, lease in self._state.work_leases.items()
            if lease.job_id == candidate.job_id
            and lease.lease_id == candidate.lease_id
            and lease.fence == candidate.fence
        ]
        if len(matches) != 1:
            fail_runtime(RuntimeFailureCode.STALE_LEASE)
        identity, lease = matches[0]
        job = self._state.jobs.get(lease.job_id)
        attempt = self._state.attempts.get(lease.attempt_id)
        inbox = self._state.inboxes.get(identity)
        if (
            job is None
            or attempt is None
            or inbox is None
            or job.state is not JobState.RUNNING
            or attempt.state is not AttemptState.RUNNING
            or inbox.state is not InboxState.PROCESSING
            or lease.leased_until > observed_at
            or job.version != candidate.expected_job_version
        ):
            fail_runtime(RuntimeFailureCode.STALE_LEASE)
        if job.cancel_requested_at is not None:
            result = self._recover_terminal(
                job,
                attempt,
                inbox,
                identity,
                observed_at,
                target=JobState.CANCELLED,
            )
            return RecoveryResult(
                kind=RecoveryKind.WORK_CANCELLED,
                event_id=identity.event_id,
                job_id=job.job_id,
                job_state=result.state,
                failure_code=RuntimeFailureCode.ORPHANED_LEASE,
            )
        if job.deadline_at is not None and job.deadline_at <= observed_at:
            result = self._recover_terminal(
                job,
                attempt,
                inbox,
                identity,
                observed_at,
                target=JobState.EXPIRED,
            )
            return RecoveryResult(
                kind=RecoveryKind.WORK_EXPIRED,
                event_id=identity.event_id,
                job_id=job.job_id,
                job_state=result.state,
                failure_code=RuntimeFailureCode.ORPHANED_LEASE,
            )
        self._state.attempts[attempt.attempt_id] = replace(
            attempt,
            state=AttemptState.FAILED,
            completed_at=observed_at,
            retry_after_at=retry_at,
            failure_code=RuntimeFailureCode.ORPHANED_LEASE,
        )
        self._state.inboxes[identity] = replace(
            inbox,
            state=InboxState.FAILED,
            processed_at=observed_at,
            failure_code=RuntimeFailureCode.ORPHANED_LEASE,
        )
        retryable = replace(
            job,
            state=JobState.FAILED_RETRYABLE,
            version=job.version + 1,
            completed_at=None,
            lease=None,
            result_fingerprint=None,
            failure_code=RuntimeFailureCode.ORPHANED_LEASE,
        )
        self._transition(job, retryable, observed_at)
        if retry_at is None or job.attempt_count >= job.max_attempts:
            terminal = replace(
                retryable,
                state=JobState.FAILED_TERMINAL,
                version=retryable.version + 1,
                completed_at=observed_at,
                failure_code=RuntimeFailureCode.RETRY_BUDGET_EXHAUSTED,
            )
            self._transition(retryable, terminal, observed_at)
            del self._state.work_leases[identity]
            self._dead_letter(
                event_id=identity.event_id,
                job_id=job.job_id,
                attempt_number=attempt.attempt_number,
                state=terminal.state,
                failure_code=RuntimeFailureCode.RETRY_BUDGET_EXHAUSTED,
                recorded_at=observed_at,
            )
            return RecoveryResult(
                kind=RecoveryKind.WORK_FAILED_TERMINAL,
                event_id=identity.event_id,
                job_id=job.job_id,
                job_state=terminal.state,
                failure_code=RuntimeFailureCode.RETRY_BUDGET_EXHAUSTED,
            )
        scheduled = replace(
            retryable,
            state=JobState.RETRY_SCHEDULED,
            version=retryable.version + 1,
            available_at=retry_at,
        )
        self._transition(retryable, scheduled, observed_at)
        del self._state.work_leases[identity]
        return RecoveryResult(
            kind=RecoveryKind.WORK_RETRY_SCHEDULED,
            event_id=identity.event_id,
            job_id=job.job_id,
            job_state=scheduled.state,
            retry_at=retry_at,
            failure_code=RuntimeFailureCode.ORPHANED_LEASE,
        )

    def _recover_terminal(
        self,
        job: JobRecord,
        attempt: AttemptRecord,
        inbox: InboxRecord,
        identity: InboxIdentity,
        observed_at: datetime,
        *,
        target: JobState,
    ) -> JobRecord:
        attempt_state = (
            AttemptState.CANCELLED
            if target is JobState.CANCELLED
            else AttemptState.TIMED_OUT
        )
        self._state.attempts[attempt.attempt_id] = replace(
            attempt,
            state=attempt_state,
            completed_at=observed_at,
            failure_code=RuntimeFailureCode.ORPHANED_LEASE,
        )
        self._state.inboxes[identity] = replace(
            inbox,
            state=InboxState.IGNORED,
            processed_at=observed_at,
            failure_code=RuntimeFailureCode.ORPHANED_LEASE,
        )
        terminal = replace(
            job,
            state=target,
            version=job.version + 1,
            completed_at=observed_at,
            lease=None,
            result_fingerprint=None,
            failure_code=RuntimeFailureCode.ORPHANED_LEASE,
        )
        self._transition(job, terminal, observed_at)
        del self._state.work_leases[identity]
        return terminal

    def _delivery_start(
        self,
        *,
        outcome: DeliveryStartOutcome,
        message: RecordedJobMessage,
        job: JobRecord,
        expected_version: int,
    ) -> DurableDeliveryStart:
        return DurableDeliveryStart(
            outcome=outcome,
            event_id=message.event_id,
            job_id=message.job_id,
            job_state=job.state,
            expected_job_version=expected_version,
            post_job_version=job.version,
        )

    @staticmethod
    def _work_result(
        outcome: DurableWorkOutcome,
        claim: WorkClaim,
        job: JobRecord,
    ) -> DurableWorkResult:
        return DurableWorkResult(
            outcome=outcome,
            event_id=claim.event_id,
            job_id=claim.job_id,
            job_state=job.state,
            attempt_number=claim.attempt_number,
            delivery_attempt=claim.delivery_attempt,
            failure_code=job.failure_code,
        )

    def _transition(self, before: JobRecord, after: JobRecord, at: datetime) -> None:
        transition = JobTransition(
            job_id=before.job_id,
            from_state=before.state,
            to_state=after.state,
            transitioned_at=at,
            expected_version=before.version,
            post_version=after.version,
        )
        self._state.jobs[after.job_id] = after
        self._state.transitions.append(transition)

    def _dead_letter(
        self,
        *,
        event_id: UUID,
        job_id: UUID,
        attempt_number: int,
        state: JobState | OutboxState,
        failure_code: RuntimeFailureCode,
        recorded_at: datetime,
    ) -> None:
        record = DeadLetterRecord(
            dead_letter_id=self._new_uuid("dead-letter"),
            event_id=event_id,
            job_id=job_id,
            attempt_number=attempt_number,
            state=state,
            failure_code=failure_code,
            recorded_at=recorded_at,
        )
        self._state.dead_letters[record.dead_letter_id] = record

    def _new_uuid(self, kind: str) -> UUID:
        require_token(kind)
        self._state.identity_counter += 1
        return uuid5(
            self._identity_namespace,
            f"raos-st1404-durable:{kind}:{self._state.identity_counter}",
        )

    def _new_fence(self) -> int:
        self._state.fence_counter += 1
        return self._state.fence_counter


class RecordedDurableJobHandler:
    """Scripted metadata-only handler for ENV-DEV/CI one-step tests."""

    __slots__ = ("_environment", "_index", "_invocations", "_lock", "_results")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        results: tuple[DurableHandlerResult, ...],
    ) -> None:
        self._environment = _environment(environment)
        if type(results) is not tuple or any(
            type(item) is not DurableHandlerResult for item in results
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        self._results = results
        self._index = 0
        self._invocations: list[RecordedJobInvocation] = []
        self._lock = RLock()

    def handle(self, invocation: RecordedJobInvocation) -> DurableHandlerResult:
        if type(invocation) is not RecordedJobInvocation:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        with self._lock:
            self._invocations.append(invocation)
            if self._index >= len(self._results):
                return DurableHandlerResult(
                    outcome=DurableHandlerOutcome.TERMINAL_FAILURE,
                    completed_at=invocation.started_at,
                    failure_code=RuntimeFailureCode.HANDLER_SCRIPT_EXHAUSTED,
                )
            result = self._results[self._index]
            self._index += 1
            return result

    def invocations(self) -> tuple[RecordedJobInvocation, ...]:
        with self._lock:
            return tuple(self._invocations)


__all__ = [
    "RecordedDurableJobHandler",
    "RecordedDurableJobRuntimeRepository",
    "RecordedDurableJobRuntimeSnapshot",
    "RecordedDurableJobRuntimeStore",
    "RecordedDurableJobRuntimeUnitOfWork",
]

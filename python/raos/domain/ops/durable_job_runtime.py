"""Durability-capable values for the ST-1404 recorded runtime.

The module contains no storage, broker, framework, or provider types.  It
models the information a transactional adapter must persist so a dispatcher
or worker can be fenced, replayed, and recovered without retaining raw job
payloads or handler output.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import NoReturn, SupportsIndex
from uuid import UUID

from raos.domain.ops.job_runtime import (
    CompletionCommit,
    DeliveryStartOutcome,
    Fingerprint,
    InboxIdentity,
    JobState,
    OutboxDispatchClaim,
    OutboxState,
    RecordedJobMessage,
    RuntimeFailureCode,
    WorkClaim,
    fail_runtime,
    require_token,
    require_utc,
)


_REDACTED = "<redacted-durable-job-runtime>"


class DurableHandlerOutcome(str, Enum):
    """Closed outcomes returned by a metadata-only recorded handler."""

    SUCCEEDED = "SUCCEEDED"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    TERMINAL_FAILURE = "TERMINAL_FAILURE"
    QUARANTINE = "QUARANTINE"


class HandlerEffectKind(str, Enum):
    """Kinds of output atomically staged with handler completion."""

    RESULT = "RESULT"
    DOMAIN_EVENT = "DOMAIN_EVENT"


class CommitFault(str, Enum):
    """Deterministic transaction faults accepted only by the recorded fake."""

    NONE = "NONE"
    KNOWN_BEFORE_COMMIT = "KNOWN_BEFORE_COMMIT"
    UNKNOWN_BEFORE_COMMIT = "UNKNOWN_BEFORE_COMMIT"
    UNKNOWN_AFTER_COMMIT = "UNKNOWN_AFTER_COMMIT"


class RecoveryKind(str, Enum):
    """Closed orphan/recovery observations."""

    NO_WORK = "NO_WORK"
    OUTBOX_RETRY_SCHEDULED = "OUTBOX_RETRY_SCHEDULED"
    OUTBOX_DEAD = "OUTBOX_DEAD"
    WORK_RETRY_SCHEDULED = "WORK_RETRY_SCHEDULED"
    WORK_FAILED_TERMINAL = "WORK_FAILED_TERMINAL"
    WORK_CANCELLED = "WORK_CANCELLED"
    WORK_EXPIRED = "WORK_EXPIRED"
    RETRY_STATE_HELD = "RETRY_STATE_HELD"
    COMMIT_KNOWN_ROLLBACK = "COMMIT_KNOWN_ROLLBACK"
    COMMIT_UNKNOWN = "COMMIT_UNKNOWN"


class RecoveryCandidateKind(str, Enum):
    OUTBOX = "OUTBOX"
    WORK = "WORK"
    RETRY_STATE_HELD = "RETRY_STATE_HELD"


class DurableDispatchOutcome(str, Enum):
    NO_WORK = "NO_WORK"
    PUBLISHED = "PUBLISHED"
    SEND_RETRY_SCHEDULED = "SEND_RETRY_SCHEDULED"
    OUTBOX_DEAD = "OUTBOX_DEAD"
    CLAIM_COMMIT_KNOWN_ROLLBACK = "CLAIM_COMMIT_KNOWN_ROLLBACK"
    CLAIM_COMMIT_UNKNOWN = "CLAIM_COMMIT_UNKNOWN"
    FINALIZE_COMMIT_KNOWN_ROLLBACK = "FINALIZE_COMMIT_KNOWN_ROLLBACK"
    FINALIZE_COMMIT_UNKNOWN = "FINALIZE_COMMIT_UNKNOWN"


class DurableWorkOutcome(str, Enum):
    NO_DELIVERY = "NO_DELIVERY"
    RECEIVE_FAILED = "RECEIVE_FAILED"
    MALFORMED_DELIVERY_RELEASED = "MALFORMED_DELIVERY_RELEASED"
    LEASE_STALE = "LEASE_STALE"
    NOT_READY_HELD = "NOT_READY_HELD"
    PROCESSING_HELD = "PROCESSING_HELD"
    RETRY_STATE_HELD = "RETRY_STATE_HELD"
    DUPLICATE_ACKNOWLEDGED = "DUPLICATE_ACKNOWLEDGED"
    SUCCEEDED = "SUCCEEDED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    QUARANTINED = "QUARANTINED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    ACK_FAILED = "ACK_FAILED"
    RETRY_RELEASE_FAILED = "RETRY_RELEASE_FAILED"
    CLAIM_COMMIT_KNOWN_ROLLBACK = "CLAIM_COMMIT_KNOWN_ROLLBACK"
    CLAIM_COMMIT_UNKNOWN = "CLAIM_COMMIT_UNKNOWN"
    COMPLETE_COMMIT_KNOWN_ROLLBACK = "COMPLETE_COMMIT_KNOWN_ROLLBACK"
    COMPLETE_COMMIT_UNKNOWN = "COMPLETE_COMMIT_UNKNOWN"


class QuarantineReplayOutcome(str, Enum):
    PREPARED_AND_SENT = "PREPARED_AND_SENT"
    SEND_AMBIGUOUS = "SEND_AMBIGUOUS"
    PREPARE_COMMIT_KNOWN_ROLLBACK = "PREPARE_COMMIT_KNOWN_ROLLBACK"
    PREPARE_COMMIT_UNKNOWN = "PREPARE_COMMIT_UNKNOWN"
    FINALIZE_COMMIT_KNOWN_ROLLBACK = "FINALIZE_COMMIT_KNOWN_ROLLBACK"
    FINALIZE_COMMIT_UNKNOWN = "FINALIZE_COMMIT_UNKNOWN"


class DurableCancellationOutcome(str, Enum):
    CANCELLED = "CANCELLED"
    REQUEST_RECORDED = "REQUEST_RECORDED"
    ALREADY_CANCELLED = "ALREADY_CANCELLED"
    COMMIT_KNOWN_ROLLBACK = "COMMIT_KNOWN_ROLLBACK"
    COMMIT_UNKNOWN = "COMMIT_UNKNOWN"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("durable job runtime value serialization is not supported")


def _positive(value: object) -> int:
    if type(value) is not int or value < 1:
        fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
    return value


@dataclass(frozen=True, slots=True, repr=False)
class HandlerEffectIntent(_RedactedValue):
    effect_id: UUID
    kind: HandlerEffectKind
    fingerprint: Fingerprint

    def __post_init__(self) -> None:
        if type(self.effect_id) is not UUID:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if type(self.kind) is not HandlerEffectKind:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if type(self.fingerprint) is not Fingerprint:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


@dataclass(frozen=True, slots=True, repr=False)
class DurableHandlerResult(_RedactedValue):
    outcome: DurableHandlerOutcome
    completed_at: datetime
    result_fingerprint: Fingerprint | None = None
    failure_code: RuntimeFailureCode | None = None
    effects: tuple[HandlerEffectIntent, ...] = ()

    def __post_init__(self) -> None:
        if type(self.outcome) is not DurableHandlerOutcome:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_utc(self.completed_at)
        if type(self.effects) is not tuple or any(
            type(effect) is not HandlerEffectIntent for effect in self.effects
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        effect_ids = tuple(effect.effect_id for effect in self.effects)
        if len(effect_ids) != len(set(effect_ids)):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if self.outcome is DurableHandlerOutcome.SUCCEEDED:
            if (
                type(self.result_fingerprint) is not Fingerprint
                or self.failure_code is not None
            ):
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        elif (
            self.result_fingerprint is not None
            or type(self.failure_code) is not RuntimeFailureCode
            or self.effects
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


@dataclass(frozen=True, slots=True, repr=False)
class DurableOutboxClaim(_RedactedValue):
    claim: OutboxDispatchClaim
    owner: str
    lease_id: UUID
    fence: int
    leased_until: datetime

    def __post_init__(self) -> None:
        if type(self.claim) is not OutboxDispatchClaim:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_token(self.owner)
        if type(self.lease_id) is not UUID:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        _positive(self.fence)
        require_utc(self.leased_until)


@dataclass(frozen=True, slots=True, repr=False)
class DurableWorkClaim(_RedactedValue):
    claim: WorkClaim
    owner: str
    fence: int

    def __post_init__(self) -> None:
        if type(self.claim) is not WorkClaim:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_token(self.owner)
        _positive(self.fence)


@dataclass(frozen=True, slots=True, repr=False)
class DurableDeliveryStart(_RedactedValue):
    outcome: DeliveryStartOutcome
    event_id: UUID
    job_id: UUID
    job_state: JobState
    expected_job_version: int
    post_job_version: int
    claim: DurableWorkClaim | None = None

    def __post_init__(self) -> None:
        if type(self.outcome) is not DeliveryStartOutcome:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if type(self.event_id) is not UUID or type(self.job_id) is not UUID:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if type(self.job_state) is not JobState:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if (
            type(self.expected_job_version) is not int
            or self.expected_job_version < 0
            or type(self.post_job_version) is not int
            or self.post_job_version < 0
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if self.outcome is DeliveryStartOutcome.EXECUTE:
            if type(self.claim) is not DurableWorkClaim:
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        elif self.claim is not None:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


@dataclass(frozen=True, slots=True, repr=False)
class OutboxLeaseRecord(_RedactedValue):
    event_id: UUID
    owner: str
    lease_id: UUID
    fence: int
    leased_until: datetime

    def __post_init__(self) -> None:
        if type(self.event_id) is not UUID or type(self.lease_id) is not UUID:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_token(self.owner)
        _positive(self.fence)
        require_utc(self.leased_until)


@dataclass(frozen=True, slots=True, repr=False)
class WorkLeaseRecord(_RedactedValue):
    identity: InboxIdentity
    job_id: UUID
    attempt_id: UUID
    owner: str
    lease_id: UUID
    fence: int
    delivery_attempt: int
    leased_until: datetime

    def __post_init__(self) -> None:
        if type(self.identity) is not InboxIdentity:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if any(
            type(value) is not UUID
            for value in (self.job_id, self.attempt_id, self.lease_id)
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_token(self.owner)
        _positive(self.fence)
        _positive(self.delivery_attempt)
        require_utc(self.leased_until)


@dataclass(frozen=True, slots=True, repr=False)
class HandlerEffectRecord(_RedactedValue):
    effect_id: UUID
    job_id: UUID
    attempt_id: UUID
    kind: HandlerEffectKind
    fingerprint: Fingerprint
    committed_at: datetime

    def __post_init__(self) -> None:
        if any(
            type(value) is not UUID
            for value in (self.effect_id, self.job_id, self.attempt_id)
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if type(self.kind) is not HandlerEffectKind:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if type(self.fingerprint) is not Fingerprint:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_utc(self.committed_at)


@dataclass(frozen=True, slots=True, repr=False)
class DeadLetterRecord(_RedactedValue):
    dead_letter_id: UUID
    event_id: UUID
    job_id: UUID
    attempt_number: int
    state: JobState | OutboxState
    failure_code: RuntimeFailureCode
    recorded_at: datetime

    def __post_init__(self) -> None:
        if any(
            type(value) is not UUID
            for value in (self.dead_letter_id, self.event_id, self.job_id)
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if type(self.attempt_number) is not int or self.attempt_number < 0:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if type(self.state) not in {JobState, OutboxState}:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if type(self.failure_code) is not RuntimeFailureCode:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_utc(self.recorded_at)


@dataclass(frozen=True, slots=True, repr=False)
class RecoveryCandidate(_RedactedValue):
    kind: RecoveryCandidateKind
    observed_at: datetime
    event_id: UUID | None = None
    job_id: UUID | None = None
    lease_id: UUID | None = None
    fence: int | None = None
    attempt_number: int | None = None
    expected_job_version: int | None = None

    def __post_init__(self) -> None:
        if type(self.kind) is not RecoveryCandidateKind:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_utc(self.observed_at)
        for uuid_value in (self.event_id, self.job_id, self.lease_id):
            if uuid_value is not None and type(uuid_value) is not UUID:
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        for int_value in (self.fence, self.attempt_number):
            if int_value is not None:
                _positive(int_value)
        if self.expected_job_version is not None and (
            type(self.expected_job_version) is not int or self.expected_job_version < 0
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if self.kind is RecoveryCandidateKind.OUTBOX:
            if self.event_id is None or self.lease_id is None or self.fence is None:
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        elif self.job_id is None:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


@dataclass(frozen=True, slots=True, repr=False)
class RecoveryResult(_RedactedValue):
    kind: RecoveryKind
    event_id: UUID | None = None
    job_id: UUID | None = None
    job_state: JobState | None = None
    outbox_state: OutboxState | None = None
    retry_at: datetime | None = None
    failure_code: RuntimeFailureCode | None = None

    def __post_init__(self) -> None:
        if type(self.kind) is not RecoveryKind:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        for uuid_value in (self.event_id, self.job_id):
            if uuid_value is not None and type(uuid_value) is not UUID:
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if self.job_state is not None and type(self.job_state) is not JobState:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if self.outbox_state is not None and type(self.outbox_state) is not OutboxState:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if self.retry_at is not None:
            require_utc(self.retry_at)
        if (
            self.failure_code is not None
            and type(self.failure_code) is not RuntimeFailureCode
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


@dataclass(frozen=True, slots=True, repr=False)
class DurableDispatchResult(_RedactedValue):
    outcome: DurableDispatchOutcome
    event_id: UUID | None = None
    job_id: UUID | None = None
    outbox_state: OutboxState | None = None
    failure_code: RuntimeFailureCode | None = None

    def __post_init__(self) -> None:
        if type(self.outcome) is not DurableDispatchOutcome:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        for value in (self.event_id, self.job_id):
            if value is not None and type(value) is not UUID:
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if self.outbox_state is not None and type(self.outbox_state) is not OutboxState:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if (
            self.failure_code is not None
            and type(self.failure_code) is not RuntimeFailureCode
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


@dataclass(frozen=True, slots=True, repr=False)
class DurableWorkResult(_RedactedValue):
    outcome: DurableWorkOutcome
    event_id: UUID | None = None
    job_id: UUID | None = None
    job_state: JobState | None = None
    attempt_number: int | None = None
    delivery_attempt: int | None = None
    failure_code: RuntimeFailureCode | None = None

    def __post_init__(self) -> None:
        if type(self.outcome) is not DurableWorkOutcome:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        for value in (self.event_id, self.job_id):
            if value is not None and type(value) is not UUID:
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if self.job_state is not None and type(self.job_state) is not JobState:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        for int_value in (self.attempt_number, self.delivery_attempt):
            if int_value is not None:
                _positive(int_value)
        if (
            self.failure_code is not None
            and type(self.failure_code) is not RuntimeFailureCode
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


@dataclass(frozen=True, slots=True, repr=False)
class DurableCancellationResult(_RedactedValue):
    outcome: DurableCancellationOutcome
    job_id: UUID
    job_state: JobState | None = None
    job_version: int | None = None
    failure_code: RuntimeFailureCode | None = None

    def __post_init__(self) -> None:
        if type(self.outcome) is not DurableCancellationOutcome:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if type(self.job_id) is not UUID:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if self.job_state is not None and type(self.job_state) is not JobState:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if self.job_version is not None and (
            type(self.job_version) is not int or self.job_version < 0
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if (
            self.failure_code is not None
            and type(self.failure_code) is not RuntimeFailureCode
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


@dataclass(frozen=True, slots=True, repr=False)
class QuarantineReleaseApproval(_RedactedValue):
    approval_id: UUID
    job_id: UUID
    expected_job_version: int
    reason_fingerprint: Fingerprint
    approved_at: datetime

    def __post_init__(self) -> None:
        if type(self.approval_id) is not UUID or type(self.job_id) is not UUID:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if type(self.expected_job_version) is not int or self.expected_job_version < 0:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if type(self.reason_fingerprint) is not Fingerprint:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_utc(self.approved_at)


@dataclass(frozen=True, slots=True, repr=False)
class QuarantineReplayClaim(_RedactedValue):
    approval: QuarantineReleaseApproval
    message: RecordedJobMessage
    queue_name: str
    available_at: datetime
    delivery_max_attempts: int
    owner: str
    lease_id: UUID
    fence: int
    prepared_at: datetime
    leased_until: datetime

    def __post_init__(self) -> None:
        if type(self.approval) is not QuarantineReleaseApproval:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if type(self.message) is not RecordedJobMessage:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_token(self.queue_name)
        require_utc(self.available_at)
        _positive(self.delivery_max_attempts)
        if self.delivery_max_attempts > 50:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_token(self.owner)
        if type(self.lease_id) is not UUID:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        _positive(self.fence)
        require_utc(self.prepared_at)
        require_utc(self.leased_until)


@dataclass(frozen=True, slots=True, repr=False)
class QuarantineReleaseRecord(_RedactedValue):
    approval: QuarantineReleaseApproval
    event_id: UUID
    owner: str
    lease_id: UUID
    fence: int
    prepared_at: datetime
    finalized_at: datetime
    post_job_version: int

    def __post_init__(self) -> None:
        if type(self.approval) is not QuarantineReleaseApproval:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if type(self.event_id) is not UUID or type(self.lease_id) is not UUID:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_token(self.owner)
        _positive(self.fence)
        require_utc(self.prepared_at)
        require_utc(self.finalized_at)
        if self.finalized_at < self.prepared_at or (
            type(self.post_job_version) is not int or self.post_job_version < 1
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


@dataclass(frozen=True, slots=True, repr=False)
class QuarantineReplayResult(_RedactedValue):
    outcome: QuarantineReplayOutcome
    job_id: UUID
    event_id: UUID | None
    job_state: JobState
    failure_code: RuntimeFailureCode | None = None

    def __post_init__(self) -> None:
        if type(self.outcome) is not QuarantineReplayOutcome:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if type(self.job_id) is not UUID or (
            self.event_id is not None and type(self.event_id) is not UUID
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if type(self.job_state) is not JobState:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if (
            self.failure_code is not None
            and type(self.failure_code) is not RuntimeFailureCode
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


def completion_from(
    *,
    outcome: DurableWorkOutcome,
    event_id: UUID,
    job_id: UUID,
    job_state: JobState,
    expected_job_version: int,
    post_job_version: int,
    attempt_number: int,
    retry_at: datetime | None,
    failure_code: RuntimeFailureCode | None,
) -> CompletionCommit:
    """Build the legacy completion projection without widening its contract."""

    legacy = {
        DurableWorkOutcome.SUCCEEDED: "SUCCEEDED",
        DurableWorkOutcome.RETRY_SCHEDULED: "RETRY_SCHEDULED",
        DurableWorkOutcome.FAILED_TERMINAL: "FAILED_TERMINAL",
        DurableWorkOutcome.CANCELLED: "CANCELLED",
        DurableWorkOutcome.EXPIRED: "EXPIRED",
    }.get(outcome)
    if legacy is None:
        fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
    from raos.domain.ops.job_runtime import WorkOutcome

    return CompletionCommit(
        outcome=WorkOutcome(legacy),
        event_id=event_id,
        job_id=job_id,
        job_state=job_state,
        expected_job_version=expected_job_version,
        post_job_version=post_job_version,
        attempt_number=attempt_number,
        retry_at=retry_at,
        failure_code=failure_code,
    )


__all__ = [
    "CommitFault",
    "DeadLetterRecord",
    "DurableDeliveryStart",
    "DurableCancellationOutcome",
    "DurableCancellationResult",
    "DurableDispatchOutcome",
    "DurableDispatchResult",
    "DurableHandlerOutcome",
    "DurableHandlerResult",
    "DurableOutboxClaim",
    "DurableWorkClaim",
    "DurableWorkOutcome",
    "DurableWorkResult",
    "HandlerEffectIntent",
    "HandlerEffectKind",
    "HandlerEffectRecord",
    "OutboxLeaseRecord",
    "QuarantineReleaseApproval",
    "QuarantineReleaseRecord",
    "QuarantineReplayClaim",
    "QuarantineReplayOutcome",
    "QuarantineReplayResult",
    "RecoveryCandidate",
    "RecoveryCandidateKind",
    "RecoveryKind",
    "RecoveryResult",
    "WorkLeaseRecord",
    "completion_from",
]

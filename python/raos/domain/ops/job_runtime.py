"""Immutable, payload-free values for the recorded Job runtime seam.

The values in this module mirror the installed ST-0303 state names while
deliberately carrying only identities, exact UTC timestamps, versions, and
fingerprints.  They are not persistence models and make no durability claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
import re
from typing import NoReturn, SupportsIndex, final
from uuid import UUID


_FINGERPRINT = re.compile(r"[0-9a-f]{64}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}\Z")
_REDACTED = "<redacted-job-runtime>"


class JobState(str, Enum):
    """Exact installed ``ops.job.status`` values."""

    REQUESTED = "REQUESTED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    QUARANTINED = "QUARANTINED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class AttemptState(str, Enum):
    """Exact installed ``ops.job_attempt.status`` values."""

    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


class OutboxState(str, Enum):
    """Exact installed ``ops.outbox_event.status`` values."""

    PENDING = "PENDING"
    DISPATCHING = "DISPATCHING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    DEAD = "DEAD"


class InboxState(str, Enum):
    """Exact installed ``ops.inbox_receipt.status`` values."""

    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"
    IGNORED = "IGNORED"


ALLOWED_JOB_TRANSITIONS: frozenset[tuple[JobState, JobState]] = frozenset(
    {
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
)


class HandlerOutcome(str, Enum):
    """Closed recorded-handler outcomes understood by the runtime."""

    SUCCEEDED = "SUCCEEDED"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    TERMINAL_FAILURE = "TERMINAL_FAILURE"


class DispatchOutcome(str, Enum):
    """Stable result of exactly one dispatcher observation."""

    NO_WORK = "NO_WORK"
    PUBLISHED = "PUBLISHED"
    SEND_RETRY_SCHEDULED = "SEND_RETRY_SCHEDULED"
    OUTBOX_DEAD = "OUTBOX_DEAD"


class WorkOutcome(str, Enum):
    """Stable result of exactly one worker observation."""

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
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    ACK_FAILED = "ACK_FAILED"
    RETRY_RELEASE_FAILED = "RETRY_RELEASE_FAILED"


class DeliveryStartOutcome(str, Enum):
    """Store decision made before a recorded handler can run."""

    EXECUTE = "EXECUTE"
    ACK_DUPLICATE = "ACK_DUPLICATE"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    PROCESSING_HELD = "PROCESSING_HELD"
    RETRY_STATE_HELD = "RETRY_STATE_HELD"
    NOT_READY_HELD = "NOT_READY_HELD"


class RuntimeFailureCode(str, Enum):
    """Sanitized, low-cardinality runtime failure classifications."""

    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"
    STATE_CONFLICT = "STATE_CONFLICT"
    STALE_VERSION = "STALE_VERSION"
    STALE_LEASE = "STALE_LEASE"
    MALFORMED_DELIVERY = "MALFORMED_DELIVERY"
    QUEUE_SEND_AMBIGUOUS = "QUEUE_SEND_AMBIGUOUS"
    QUEUE_RECEIVE_FAILED = "QUEUE_RECEIVE_FAILED"
    QUEUE_ACK_FAILED = "QUEUE_ACK_FAILED"
    QUEUE_RETRY_FAILED = "QUEUE_RETRY_FAILED"
    HANDLER_FAILED = "HANDLER_FAILED"
    HANDLER_RESULT_MALFORMED = "HANDLER_RESULT_MALFORMED"
    HANDLER_SCRIPT_EXHAUSTED = "HANDLER_SCRIPT_EXHAUSTED"
    RETRY_BUDGET_EXHAUSTED = "RETRY_BUDGET_EXHAUSTED"
    COMMIT_KNOWN_ROLLBACK = "COMMIT_KNOWN_ROLLBACK"
    COMMIT_UNKNOWN = "COMMIT_UNKNOWN"
    CONCURRENCY_CONFLICT = "CONCURRENCY_CONFLICT"
    ORPHANED_LEASE = "ORPHANED_LEASE"
    HANDLER_QUARANTINED = "HANDLER_QUARANTINED"


@final
class JobRuntimeFailure(RuntimeError):
    """Immutable failure retaining no rejected value or exception text."""

    __slots__ = ("_code",)
    _code: RuntimeFailureCode

    def __init__(self, code: RuntimeFailureCode) -> None:
        if type(code) is not RuntimeFailureCode:
            raise TypeError("code must be an exact RuntimeFailureCode")
        super().__init__(code.value)
        object.__setattr__(self, "_code", code)

    @property
    def code(self) -> RuntimeFailureCode:
        return self._code

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("JobRuntimeFailure is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("JobRuntimeFailure is immutable")

    def __repr__(self) -> str:
        return f"JobRuntimeFailure(code={self.code!r})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("job runtime failure serialization is not supported")


def fail_runtime(code: RuntimeFailureCode) -> NoReturn:
    """Raise one sanitized failure without exception chaining."""

    raise JobRuntimeFailure(code) from None


def require_utc(value: object) -> datetime:
    """Require an exact ``datetime`` carrying the explicit UTC singleton."""

    if type(value) is not datetime or value.tzinfo is not UTC:
        fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
    return value


def require_uuid(value: object) -> UUID:
    """Require an exact UUID identity rather than a coercible string."""

    if type(value) is not UUID:
        fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
    return value


def require_token(value: object) -> str:
    """Require one bounded stable identifier without retaining bad input."""

    if type(value) is not str or _TOKEN.fullmatch(value) is None:
        fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
    return value


def require_non_negative_int(value: object) -> int:
    if type(value) is not int or value < 0:
        fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
    return value


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("job runtime value serialization is not supported")


@final
class Fingerprint(_RedactedValue):
    """A validated SHA-256 fingerprint; never the underlying payload/result."""

    __slots__ = ("_value",)
    _value: str

    def __init__(self, value: str) -> None:
        if type(value) is not str or _FINGERPRINT.fullmatch(value) is None:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        object.__setattr__(self, "_value", value)

    @property
    def value(self) -> str:
        return self._value

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("Fingerprint is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("Fingerprint is immutable")

    def __eq__(self, other: object) -> bool:
        return type(other) is Fingerprint and self._value == other._value

    def __hash__(self) -> int:
        return hash(self._value)


@dataclass(frozen=True, slots=True, repr=False)
class JobLease(_RedactedValue):
    lease_id: UUID
    expires_at: datetime

    def __post_init__(self) -> None:
        require_uuid(self.lease_id)
        require_utc(self.expires_at)


_TERMINAL_JOB_STATES = frozenset(
    {
        JobState.SUCCEEDED,
        JobState.FAILED_TERMINAL,
        JobState.QUARANTINED,
        JobState.CANCELLED,
        JobState.EXPIRED,
    }
)


@dataclass(frozen=True, slots=True, repr=False)
class JobRecord(_RedactedValue):
    """Process-local projection of the fields used by this bounded seam."""

    job_id: UUID
    state: JobState
    queue_name: str
    payload_fingerprint: Fingerprint
    created_at: datetime
    available_at: datetime
    job_schema_version: int
    version: int
    max_attempts: int
    delivery_max_attempts: int
    attempt_count: int = 0
    deadline_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    completed_at: datetime | None = None
    lease: JobLease | None = None
    result_fingerprint: Fingerprint | None = None
    failure_code: RuntimeFailureCode | None = None

    def __post_init__(self) -> None:
        require_uuid(self.job_id)
        if type(self.state) is not JobState:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_token(self.queue_name)
        if type(self.payload_fingerprint) is not Fingerprint:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_utc(self.created_at)
        require_utc(self.available_at)
        if type(self.job_schema_version) is not int or self.job_schema_version < 1:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_non_negative_int(self.version)
        if (
            type(self.max_attempts) is not int
            or not 1 <= self.max_attempts <= 50
            or type(self.delivery_max_attempts) is not int
            or not 1 <= self.delivery_max_attempts <= 50
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_non_negative_int(self.attempt_count)
        if self.attempt_count > self.max_attempts:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        for timestamp in (
            self.deadline_at,
            self.cancel_requested_at,
            self.completed_at,
        ):
            if timestamp is not None:
                require_utc(timestamp)
        if self.deadline_at is not None and self.deadline_at <= self.created_at:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if self.state is JobState.RUNNING:
            if type(self.lease) is not JobLease:
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        elif self.lease is not None:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if (self.state in _TERMINAL_JOB_STATES) is (self.completed_at is None):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if self.state is JobState.SUCCEEDED:
            if (
                type(self.result_fingerprint) is not Fingerprint
                or self.cancel_requested_at is not None
            ):
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        elif self.result_fingerprint is not None:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if (
            self.failure_code is not None
            and type(self.failure_code) is not RuntimeFailureCode
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


@dataclass(frozen=True, slots=True, repr=False)
class AttemptRecord(_RedactedValue):
    attempt_id: UUID
    job_id: UUID
    attempt_number: int
    state: AttemptState
    handler_version: str
    started_at: datetime
    completed_at: datetime | None = None
    retry_after_at: datetime | None = None
    result_fingerprint: Fingerprint | None = None
    failure_code: RuntimeFailureCode | None = None

    def __post_init__(self) -> None:
        require_uuid(self.attempt_id)
        require_uuid(self.job_id)
        if type(self.attempt_number) is not int or self.attempt_number < 1:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if type(self.state) is not AttemptState:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_token(self.handler_version)
        require_utc(self.started_at)
        for timestamp in (self.completed_at, self.retry_after_at):
            if timestamp is not None:
                require_utc(timestamp)
        if (self.state is AttemptState.RUNNING) is (self.completed_at is not None):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if (
            self.result_fingerprint is not None
            and type(self.result_fingerprint) is not Fingerprint
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if (
            self.failure_code is not None
            and type(self.failure_code) is not RuntimeFailureCode
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


@dataclass(frozen=True, slots=True, repr=False)
class OutboxRecord(_RedactedValue):
    event_id: UUID
    job_id: UUID
    state: OutboxState
    created_at: datetime
    available_at: datetime
    message_available_at: datetime
    publish_attempts: int = 0
    published_at: datetime | None = None
    failure_code: RuntimeFailureCode | None = None

    def __post_init__(self) -> None:
        require_uuid(self.event_id)
        require_uuid(self.job_id)
        if type(self.state) is not OutboxState:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_utc(self.created_at)
        require_utc(self.available_at)
        require_utc(self.message_available_at)
        require_non_negative_int(self.publish_attempts)
        if self.published_at is not None:
            require_utc(self.published_at)
        if self.state is OutboxState.PUBLISHED:
            if self.published_at is None:
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        elif self.published_at is not None:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if (
            self.failure_code is not None
            and type(self.failure_code) is not RuntimeFailureCode
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


@dataclass(frozen=True, slots=True, repr=False)
class InboxIdentity(_RedactedValue):
    consumer_name: str
    handler_version: str
    event_id: UUID

    def __post_init__(self) -> None:
        require_token(self.consumer_name)
        require_token(self.handler_version)
        require_uuid(self.event_id)


@dataclass(frozen=True, slots=True, repr=False)
class InboxRecord(_RedactedValue):
    inbox_id: UUID
    identity: InboxIdentity
    state: InboxState
    received_at: datetime
    processed_at: datetime | None = None
    result_fingerprint: Fingerprint | None = None
    failure_code: RuntimeFailureCode | None = None

    def __post_init__(self) -> None:
        require_uuid(self.inbox_id)
        if (
            type(self.identity) is not InboxIdentity
            or type(self.state) is not InboxState
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_utc(self.received_at)
        if self.processed_at is not None:
            require_utc(self.processed_at)
        if (self.state is InboxState.PROCESSING) is (self.processed_at is not None):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if (
            self.result_fingerprint is not None
            and type(self.result_fingerprint) is not Fingerprint
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if (
            self.failure_code is not None
            and type(self.failure_code) is not RuntimeFailureCode
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


@dataclass(frozen=True, slots=True, repr=False)
class RecordedJobMessage(_RedactedValue):
    """The complete payload of one stable logical Queue message."""

    event_id: UUID
    job_id: UUID
    expected_job_version: int
    job_schema_version: int
    payload_fingerprint: Fingerprint
    deadline_at: datetime | None

    def __post_init__(self) -> None:
        require_uuid(self.event_id)
        require_uuid(self.job_id)
        require_non_negative_int(self.expected_job_version)
        if type(self.job_schema_version) is not int or self.job_schema_version < 1:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if type(self.payload_fingerprint) is not Fingerprint:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if self.deadline_at is not None:
            require_utc(self.deadline_at)


@dataclass(frozen=True, slots=True, repr=False)
class RecordedJobInvocation(_RedactedValue):
    event_id: UUID
    job_id: UUID
    attempt_id: UUID
    attempt_number: int
    payload_fingerprint: Fingerprint
    started_at: datetime
    deadline_at: datetime | None

    def __post_init__(self) -> None:
        require_uuid(self.event_id)
        require_uuid(self.job_id)
        require_uuid(self.attempt_id)
        if type(self.attempt_number) is not int or self.attempt_number < 1:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if type(self.payload_fingerprint) is not Fingerprint:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_utc(self.started_at)
        if self.deadline_at is not None:
            require_utc(self.deadline_at)


@dataclass(frozen=True, slots=True, repr=False)
class RecordedHandlerResult(_RedactedValue):
    outcome: HandlerOutcome
    completed_at: datetime
    result_fingerprint: Fingerprint | None = None
    failure_code: RuntimeFailureCode | None = None

    def __post_init__(self) -> None:
        if type(self.outcome) is not HandlerOutcome:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_utc(self.completed_at)
        if self.outcome is HandlerOutcome.SUCCEEDED:
            if (
                type(self.result_fingerprint) is not Fingerprint
                or self.failure_code is not None
            ):
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        elif (
            self.result_fingerprint is not None
            or type(self.failure_code) is not RuntimeFailureCode
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


@dataclass(frozen=True, slots=True, repr=False)
class JobTransition(_RedactedValue):
    job_id: UUID
    from_state: JobState
    to_state: JobState
    transitioned_at: datetime
    expected_version: int
    post_version: int

    def __post_init__(self) -> None:
        require_uuid(self.job_id)
        if type(self.from_state) is not JobState or type(self.to_state) is not JobState:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if (self.from_state, self.to_state) not in ALLOWED_JOB_TRANSITIONS:
            fail_runtime(RuntimeFailureCode.STATE_CONFLICT)
        require_utc(self.transitioned_at)
        require_non_negative_int(self.expected_version)
        require_non_negative_int(self.post_version)
        if self.post_version != self.expected_version + 1:
            fail_runtime(RuntimeFailureCode.STALE_VERSION)


@dataclass(frozen=True, slots=True, repr=False)
class OutboxDispatchClaim(_RedactedValue):
    event_id: UUID
    job_id: UUID
    queue_name: str
    payload_fingerprint: Fingerprint
    message_available_at: datetime
    deadline_at: datetime | None
    message_expected_job_version: int
    expected_job_version: int
    job_schema_version: int
    delivery_max_attempts: int
    publish_attempt: int

    def __post_init__(self) -> None:
        require_uuid(self.event_id)
        require_uuid(self.job_id)
        require_token(self.queue_name)
        if type(self.payload_fingerprint) is not Fingerprint:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_utc(self.message_available_at)
        if self.deadline_at is not None:
            require_utc(self.deadline_at)
        require_non_negative_int(self.message_expected_job_version)
        require_non_negative_int(self.expected_job_version)
        if self.message_expected_job_version > self.expected_job_version:
            fail_runtime(RuntimeFailureCode.STALE_VERSION)
        if (
            type(self.job_schema_version) is not int
            or self.job_schema_version < 1
            or type(self.delivery_max_attempts) is not int
            or not 1 <= self.delivery_max_attempts <= 50
            or type(self.publish_attempt) is not int
            or self.publish_attempt < 1
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


@dataclass(frozen=True, slots=True, repr=False)
class WorkClaim(_RedactedValue):
    event_id: UUID
    job_id: UUID
    inbox_id: UUID
    attempt_id: UUID
    attempt_number: int
    lease_id: UUID
    leased_until: datetime
    expected_job_version: int
    running_job_version: int
    delivery_attempt: int
    invocation: RecordedJobInvocation

    def __post_init__(self) -> None:
        for identity in (
            self.event_id,
            self.job_id,
            self.inbox_id,
            self.attempt_id,
            self.lease_id,
        ):
            require_uuid(identity)
        if type(self.attempt_number) is not int or self.attempt_number < 1:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_utc(self.leased_until)
        require_non_negative_int(self.expected_job_version)
        require_non_negative_int(self.running_job_version)
        if self.running_job_version <= self.expected_job_version:
            fail_runtime(RuntimeFailureCode.STALE_VERSION)
        if type(self.delivery_attempt) is not int or self.delivery_attempt < 1:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if type(self.invocation) is not RecordedJobInvocation:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


@dataclass(frozen=True, slots=True, repr=False)
class DeliveryStart(_RedactedValue):
    outcome: DeliveryStartOutcome
    event_id: UUID
    job_id: UUID
    job_state: JobState
    expected_job_version: int
    post_job_version: int
    claim: WorkClaim | None = None

    def __post_init__(self) -> None:
        if type(self.outcome) is not DeliveryStartOutcome:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_uuid(self.event_id)
        require_uuid(self.job_id)
        if type(self.job_state) is not JobState:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_non_negative_int(self.expected_job_version)
        require_non_negative_int(self.post_job_version)
        if self.outcome is DeliveryStartOutcome.EXECUTE:
            if type(self.claim) is not WorkClaim:
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        elif self.claim is not None:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


@dataclass(frozen=True, slots=True, repr=False)
class CompletionCommit(_RedactedValue):
    outcome: WorkOutcome
    event_id: UUID
    job_id: UUID
    job_state: JobState
    expected_job_version: int
    post_job_version: int
    attempt_number: int
    retry_at: datetime | None = None
    failure_code: RuntimeFailureCode | None = None

    def __post_init__(self) -> None:
        if type(self.outcome) is not WorkOutcome:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if self.outcome not in {
            WorkOutcome.SUCCEEDED,
            WorkOutcome.RETRY_SCHEDULED,
            WorkOutcome.FAILED_TERMINAL,
            WorkOutcome.CANCELLED,
            WorkOutcome.EXPIRED,
        }:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_uuid(self.event_id)
        require_uuid(self.job_id)
        if type(self.job_state) is not JobState:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        require_non_negative_int(self.expected_job_version)
        require_non_negative_int(self.post_job_version)
        if type(self.attempt_number) is not int or self.attempt_number < 1:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if self.retry_at is not None:
            require_utc(self.retry_at)
        if (
            self.failure_code is not None
            and type(self.failure_code) is not RuntimeFailureCode
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


@dataclass(frozen=True, slots=True, repr=False)
class DispatchStepResult(_RedactedValue):
    outcome: DispatchOutcome
    event_id: UUID | None = None
    job_id: UUID | None = None
    outbox_state: OutboxState | None = None
    expected_job_version: int | None = None
    post_job_version: int | None = None
    publish_attempt: int | None = None
    failure_code: RuntimeFailureCode | None = None

    def __post_init__(self) -> None:
        if type(self.outcome) is not DispatchOutcome:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        for identity in (self.event_id, self.job_id):
            if identity is not None:
                require_uuid(identity)
        if self.outbox_state is not None and type(self.outbox_state) is not OutboxState:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        for version in (self.expected_job_version, self.post_job_version):
            if version is not None:
                require_non_negative_int(version)
        if self.publish_attempt is not None and (
            type(self.publish_attempt) is not int or self.publish_attempt < 1
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if (
            self.failure_code is not None
            and type(self.failure_code) is not RuntimeFailureCode
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


@dataclass(frozen=True, slots=True, repr=False)
class WorkStepResult(_RedactedValue):
    outcome: WorkOutcome
    event_id: UUID | None = None
    job_id: UUID | None = None
    job_state: JobState | None = None
    expected_job_version: int | None = None
    post_job_version: int | None = None
    attempt_number: int | None = None
    delivery_attempt: int | None = None
    failure_code: RuntimeFailureCode | None = None

    def __post_init__(self) -> None:
        if type(self.outcome) is not WorkOutcome:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        for identity in (self.event_id, self.job_id):
            if identity is not None:
                require_uuid(identity)
        if self.job_state is not None and type(self.job_state) is not JobState:
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        for version in (self.expected_job_version, self.post_job_version):
            if version is not None:
                require_non_negative_int(version)
        for attempt in (self.attempt_number, self.delivery_attempt):
            if attempt is not None and (type(attempt) is not int or attempt < 1):
                fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)
        if (
            self.failure_code is not None
            and type(self.failure_code) is not RuntimeFailureCode
        ):
            fail_runtime(RuntimeFailureCode.INVALID_ARGUMENT)


__all__ = [
    "ALLOWED_JOB_TRANSITIONS",
    "AttemptRecord",
    "AttemptState",
    "CompletionCommit",
    "DeliveryStart",
    "DeliveryStartOutcome",
    "DispatchOutcome",
    "DispatchStepResult",
    "Fingerprint",
    "HandlerOutcome",
    "InboxIdentity",
    "InboxRecord",
    "InboxState",
    "JobLease",
    "JobRecord",
    "JobRuntimeFailure",
    "JobState",
    "JobTransition",
    "OutboxDispatchClaim",
    "OutboxRecord",
    "OutboxState",
    "RecordedHandlerResult",
    "RecordedJobInvocation",
    "RecordedJobMessage",
    "RuntimeFailureCode",
    "WorkClaim",
    "WorkOutcome",
    "WorkStepResult",
    "fail_runtime",
    "require_token",
    "require_utc",
]

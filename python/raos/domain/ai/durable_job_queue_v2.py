"""Versioned durable-state values for recorded ST-0706 AI job processing.

The module owns an AI-specific state/transition contract.  It does not own a
generic queue runner, database, broker, background thread, provider call, or
event publication path.  Persisted bytes contain identifiers, hashes, bounded
counters, timestamps, and closed classifications only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
import hashlib
import json
import re
from typing import NoReturn, SupportsIndex, TypeGuard, cast, final
from uuid import UUID

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.job_orchestration import (
    AiJobCommand,
    AiJobEventType,
    ProviderFailureClass,
    ValidationFailureClass,
    ValidationPlanBinding,
    ValidationStatus,
)
from raos.domain.ai.routing import (
    AuthorizedRouteReservation,
    BudgetReservation,
    RouteIdentity,
)


POLICY_ID = "st-0706.recorded-durable-ai-job-queue.v2"
POLICY_SHA256 = "f4d7c6bacfbbc8c104d2e4cbd1700d87d946191b789c7967183a1c4b9186d5a8"
CONTRACT_SHA256 = "54338981006281c8c2c683e6ba2b2415f6d6cadb981360c08907a00bdda9dee1"
STATE_DOCUMENT_ID = "RAOS-ST0706-DURABLE-AI-JOB-QUEUE-STATE-002"
STATE_SCHEMA_VERSION = 2
QUEUE_CAPACITY = 32
MAXIMUM_STATE_BYTES = 1_048_576
MAXIMUM_OUTBOX_INTENTS = 128
MAXIMUM_COMPLETION_RECEIPTS_PER_JOB = 3
MAXIMUM_ATTEMPTS_CAP = 3
LEASE_DURATION_SECONDS = 30
RETRY_BACKOFF_SECONDS_AFTER_ATTEMPT = (7, 31)
MAXIMUM_CUMULATIVE_RETRY_BACKOFF_SECONDS = 38

_SAFE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_SIGNED_BIGINT = (1 << 63) - 1
_REDACTED = "<redacted-durable-ai-job-queue-v2>"


class DurableQueueFailureCode(str, Enum):
    """Closed failure vocabulary for the recorded durable boundary."""

    INVALID_REQUEST = "INVALID_REQUEST"
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"
    DISABLED = "DISABLED"
    STATE_INVALID = "STATE_INVALID"
    STATE_TOO_LARGE = "STATE_TOO_LARGE"
    CAPACITY_EXCEEDED = "CAPACITY_EXCEEDED"
    OUTBOX_CAPACITY_EXCEEDED = "OUTBOX_CAPACITY_EXCEEDED"
    IDEMPOTENCY_MISMATCH = "IDEMPOTENCY_MISMATCH"
    AI_JOB_ID_CONFLICT = "AI_JOB_ID_CONFLICT"
    OPS_JOB_ID_CONFLICT = "OPS_JOB_ID_CONFLICT"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    JOB_NOT_CLAIMABLE = "JOB_NOT_CLAIMABLE"
    LEASE_MISMATCH = "LEASE_MISMATCH"
    COMPLETION_MISMATCH = "COMPLETION_MISMATCH"
    CAS_CONFLICT = "CAS_CONFLICT"
    COMMIT_UNCERTAIN = "COMMIT_UNCERTAIN"


@final
class DurableQueueFailure(RuntimeError):
    """Immutable sanitized failure that retains no rejected state bytes."""

    __slots__ = ("_code",)
    _code: DurableQueueFailureCode

    def __init__(self, code: DurableQueueFailureCode) -> None:
        if type(code) is not DurableQueueFailureCode:
            raise TypeError("code must be an exact DurableQueueFailureCode")
        super().__init__(code.value)
        object.__setattr__(self, "_code", code)

    @property
    def code(self) -> DurableQueueFailureCode:
        return self._code

    def __setattr__(self, name: str, value: object) -> None:
        if name == "__traceback__":
            BaseException.__setattr__(self, name, value)
            return
        del name, value
        raise AttributeError("DurableQueueFailure is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("DurableQueueFailure is immutable")

    def __repr__(self) -> str:
        return f"DurableQueueFailure(code={self.code!r})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("durable queue failure serialization is unsupported")


def fail_durable_queue(code: DurableQueueFailureCode) -> NoReturn:
    """Raise one closed failure without retaining an exception chain."""

    raise DurableQueueFailure(code) from None


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("durable queue value serialization is unsupported")


def _require_token(value: object) -> str:
    if type(value) is not str or _SAFE_TOKEN.fullmatch(value) is None:
        fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
    return value


def _require_sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
    return value


def require_durable_token(value: object) -> str:
    """Require one bounded identifier at the public application boundary."""

    return _require_token(value)


def require_durable_sha256(value: object) -> str:
    """Require one exact lowercase SHA-256 value."""

    return _require_sha256(value)


def _require_int(
    value: object, *, minimum: int = 0, maximum: int = _MAX_SIGNED_BIGINT
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
    return value


def require_durable_utc(value: object) -> datetime:
    """Require an exact UTC datetime."""

    if type(value) is not datetime or value.tzinfo is not UTC:
        fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
    return value


def _canonical_bytes(value: object) -> bytes:
    encoded: bytes | None = None
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeEncodeError, RecursionError:
        pass
    if encoded is None:
        fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)
    return encoded


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _exact_dict(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)
    mapping = cast(dict[object, object], value)
    if frozenset(mapping) != keys or not all(type(key) is str for key in mapping):
        fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)
    return cast(dict[str, object], mapping)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return type(value) is list


def _exact_list(value: object, *, maximum: int) -> list[object]:
    if not _is_object_list(value) or len(value) > maximum:
        fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)
    return value


def _state_token(value: object) -> str:
    try:
        return _require_token(value)
    except DurableQueueFailure:
        fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)


def _state_sha256(value: object) -> str:
    try:
        return _require_sha256(value)
    except DurableQueueFailure:
        fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)


def _state_int(
    value: object, *, minimum: int = 0, maximum: int = _MAX_SIGNED_BIGINT
) -> int:
    try:
        return _require_int(value, minimum=minimum, maximum=maximum)
    except DurableQueueFailure:
        fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)


def _state_bool(value: object) -> bool:
    if type(value) is not bool:
        fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)
    return value


def _state_uuid(value: object) -> UUID:
    if type(value) is not str:
        fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)
    parsed: UUID | None = None
    try:
        parsed = UUID(value)
    except ValueError, AttributeError:
        pass
    if parsed is None or str(parsed) != value:
        fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)
    return parsed


def _state_datetime(value: object) -> datetime:
    if type(value) is not str:
        fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        pass
    if parsed is None or parsed.tzinfo is not UTC or parsed.isoformat() != value:
        fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)
    return parsed


def _state_optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return _state_datetime(value)


def _state_optional_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    return _state_uuid(value)


def _enum_from_state(enum_type: type[Enum], value: object) -> Enum:
    if type(value) is not str:
        fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)
    parsed: Enum | None = None
    try:
        parsed = enum_type(value)
    except ValueError:
        pass
    if parsed is None:
        fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)
    return parsed


class DurableJobStatus(str, Enum):
    READY = "READY"
    LEASED = "LEASED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    SUCCEEDED = "SUCCEEDED"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    DEAD_LETTERED = "DEAD_LETTERED"
    QUARANTINED = "QUARANTINED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


TERMINAL_JOB_STATUSES = frozenset(
    {
        DurableJobStatus.SUCCEEDED,
        DurableJobStatus.FAILED_TERMINAL,
        DurableJobStatus.DEAD_LETTERED,
        DurableJobStatus.QUARANTINED,
        DurableJobStatus.CANCELLED,
        DurableJobStatus.EXPIRED,
    }
)


class DurableDecisionCode(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    PROVIDER_TERMINAL = "PROVIDER_TERMINAL"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    VALIDATION_UNAVAILABLE = "VALIDATION_UNAVAILABLE"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"
    UNKNOWN_COST = "UNKNOWN_COST"
    COST_OVERRUN = "COST_OVERRUN"
    INDETERMINATE_OUTCOME = "INDETERMINATE_OUTCOME"
    LEASE_EXPIRED_AMBIGUOUS = "LEASE_EXPIRED_AMBIGUOUS"
    COMMAND_CANCELLED = "COMMAND_CANCELLED"
    DEADLINE_EXPIRED = "DEADLINE_EXPIRED"


class RecordedAttemptKind(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    VALIDATION_FAILURE = "VALIDATION_FAILURE"
    INDETERMINATE = "INDETERMINATE"


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedDurableQueueActivation(_RedactedValue):
    """Explicit local activation; construction defaults to disabled."""

    environment: RuntimeEnvironment = RuntimeEnvironment.ENV_DEV
    enabled: bool = False
    policy_id: str = POLICY_ID
    fingerprint_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.environment) is not RuntimeEnvironment or self.environment not in {
            RuntimeEnvironment.ENV_DEV,
            RuntimeEnvironment.CI,
        }:
            fail_durable_queue(DurableQueueFailureCode.DEVELOPMENT_ONLY)
        if type(self.enabled) is not bool or self.policy_id != POLICY_ID:
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        object.__setattr__(
            self,
            "fingerprint_sha256",
            _canonical_sha256(
                {
                    "environment": self.environment.value,
                    "enabled": self.enabled,
                    "policy_id": self.policy_id,
                    "policy_sha256": POLICY_SHA256,
                }
            ),
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class DurableQueueSnapshot(_RedactedValue):
    """Exact state bytes and revision returned by the caller-owned CAS port."""

    queue_id: str
    revision: int
    state_bytes: bytes
    state_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _require_token(self.queue_id)
        _require_int(self.revision)
        if (
            type(self.state_bytes) is not bytes
            or len(self.state_bytes) > MAXIMUM_STATE_BYTES
        ):
            fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)
        copied = bytes(self.state_bytes)
        object.__setattr__(self, "state_bytes", copied)
        object.__setattr__(self, "state_sha256", hashlib.sha256(copied).hexdigest())


@final
@dataclass(frozen=True, slots=True, repr=False)
class DurableLease(_RedactedValue):
    worker_id: str
    lease_token_sha256: str
    epoch: int
    claimed_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        _require_token(self.worker_id)
        _require_sha256(self.lease_token_sha256)
        _require_int(self.epoch, minimum=1)
        claimed_at = require_durable_utc(self.claimed_at)
        expires_at = require_durable_utc(self.expires_at)
        if expires_at <= claimed_at:
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        object.__setattr__(self, "claimed_at", claimed_at)
        object.__setattr__(self, "expires_at", expires_at)


@final
@dataclass(frozen=True, slots=True, repr=False)
class DurableLeaseClaim(_RedactedValue):
    queue_id: str
    ai_job_id: UUID
    command_fingerprint_sha256: str
    worker_id: str
    lease_token_sha256: str
    lease_epoch: int
    attempt_number: int
    leased_at: datetime
    leased_until: datetime
    fingerprint_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _require_token(self.queue_id)
        if type(self.ai_job_id) is not UUID:
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        _require_sha256(self.command_fingerprint_sha256)
        _require_token(self.worker_id)
        _require_sha256(self.lease_token_sha256)
        _require_int(self.lease_epoch, minimum=1)
        _require_int(self.attempt_number, minimum=1, maximum=MAXIMUM_ATTEMPTS_CAP)
        leased_at = require_durable_utc(self.leased_at)
        leased_until = require_durable_utc(self.leased_until)
        if leased_until <= leased_at:
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        object.__setattr__(self, "leased_at", leased_at)
        object.__setattr__(self, "leased_until", leased_until)
        object.__setattr__(
            self,
            "fingerprint_sha256",
            _canonical_sha256(
                {
                    "queue_id": self.queue_id,
                    "ai_job_id": str(self.ai_job_id),
                    "command_fingerprint_sha256": self.command_fingerprint_sha256,
                    "worker_id": self.worker_id,
                    "lease_token_sha256": self.lease_token_sha256,
                    "lease_epoch": self.lease_epoch,
                    "attempt_number": self.attempt_number,
                    "leased_at": leased_at.isoformat(),
                    "leased_until": leased_until.isoformat(),
                }
            ),
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedAttemptOutcome(_RedactedValue):
    """One combined, metadata-only provider/validation observation."""

    kind: RecordedAttemptKind
    ai_job_id: UUID
    attempt_number: int
    provider_request_id: str
    actual_cost_jpy: int | None
    provider_failure_class: ProviderFailureClass | None = None
    validation_status: ValidationStatus | None = None
    validation_failure_class: ValidationFailureClass | None = None
    retryable: bool = False
    output_artifact_id: UUID | None = None
    output_artifact_sha256: str | None = None
    fingerprint_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.kind) is not RecordedAttemptKind
            or type(self.ai_job_id) is not UUID
        ):
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        _require_int(self.attempt_number, minimum=1, maximum=MAXIMUM_ATTEMPTS_CAP)
        _require_token(self.provider_request_id)
        if self.actual_cost_jpy is not None:
            _require_int(self.actual_cost_jpy)
        if type(self.retryable) is not bool:
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)

        if self.kind is RecordedAttemptKind.SUCCEEDED:
            valid = (
                self.actual_cost_jpy is not None
                and self.provider_failure_class is None
                and self.validation_status is ValidationStatus.PASS
                and self.validation_failure_class is None
                and not self.retryable
                and type(self.output_artifact_id) is UUID
                and self.output_artifact_sha256 is not None
            )
        elif self.kind is RecordedAttemptKind.PROVIDER_FAILURE:
            valid = (
                type(self.provider_failure_class) is ProviderFailureClass
                and self.validation_status is None
                and self.validation_failure_class is None
                and self.output_artifact_id is None
                and self.output_artifact_sha256 is None
            )
        elif self.kind is RecordedAttemptKind.VALIDATION_FAILURE:
            valid = (
                self.provider_failure_class is None
                and self.validation_status
                in {ValidationStatus.FAIL, ValidationStatus.UNAVAILABLE}
                and type(self.validation_failure_class) is ValidationFailureClass
                and not self.retryable
                and type(self.output_artifact_id) is UUID
                and self.output_artifact_sha256 is not None
            )
        else:
            valid = (
                self.provider_failure_class is None
                and self.validation_status is None
                and self.validation_failure_class is None
                and not self.retryable
                and self.output_artifact_id is None
                and self.output_artifact_sha256 is None
            )
        if not valid:
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        if self.output_artifact_sha256 is not None:
            _require_sha256(self.output_artifact_sha256)
        object.__setattr__(
            self,
            "fingerprint_sha256",
            _canonical_sha256(
                {
                    "kind": self.kind.value,
                    "ai_job_id": str(self.ai_job_id),
                    "attempt_number": self.attempt_number,
                    "provider_request_id": self.provider_request_id,
                    "actual_cost_jpy": self.actual_cost_jpy,
                    "provider_failure_class": (
                        self.provider_failure_class.value
                        if self.provider_failure_class is not None
                        else None
                    ),
                    "validation_status": (
                        self.validation_status.value
                        if self.validation_status is not None
                        else None
                    ),
                    "validation_failure_class": (
                        self.validation_failure_class.value
                        if self.validation_failure_class is not None
                        else None
                    ),
                    "retryable": self.retryable,
                    "output_artifact_id": (
                        str(self.output_artifact_id)
                        if self.output_artifact_id is not None
                        else None
                    ),
                    "output_artifact_sha256": self.output_artifact_sha256,
                }
            ),
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class DurableCompletionReceipt(_RedactedValue):
    claim_sha256: str
    worker_id: str
    lease_token_sha256: str
    lease_epoch: int
    claimed_attempt_number: int
    leased_at: datetime
    leased_until: datetime
    outcome_sha256: str
    status: DurableJobStatus
    attempt_number: int
    accumulated_cost_jpy: int
    available_at: datetime
    decision_code: DurableDecisionCode | None

    def __post_init__(self) -> None:
        _require_sha256(self.claim_sha256)
        _require_token(self.worker_id)
        _require_sha256(self.lease_token_sha256)
        _require_int(self.lease_epoch, minimum=1)
        _require_int(
            self.claimed_attempt_number, minimum=1, maximum=MAXIMUM_ATTEMPTS_CAP
        )
        leased_at = require_durable_utc(self.leased_at)
        leased_until = require_durable_utc(self.leased_until)
        if leased_until <= leased_at:
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        object.__setattr__(self, "leased_at", leased_at)
        object.__setattr__(self, "leased_until", leased_until)
        _require_sha256(self.outcome_sha256)
        if type(self.status) is not DurableJobStatus:
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        _require_int(self.attempt_number, minimum=1, maximum=MAXIMUM_ATTEMPTS_CAP)
        _require_int(self.accumulated_cost_jpy)
        object.__setattr__(self, "available_at", require_durable_utc(self.available_at))
        if (
            self.decision_code is not None
            and type(self.decision_code) is not DurableDecisionCode
        ):
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        if (self.status in TERMINAL_JOB_STATUSES) != (self.decision_code is not None):
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)


@final
@dataclass(frozen=True, slots=True, repr=False)
class DurableOutboxIntent(_RedactedValue):
    intent_id_sha256: str
    event_type: AiJobEventType
    ai_job_id: UUID
    command_fingerprint_sha256: str
    attempt_number: int
    status: DurableJobStatus
    occurred_at: datetime
    metadata_sha256: str

    def __post_init__(self) -> None:
        _require_sha256(self.intent_id_sha256)
        if (
            type(self.event_type) is not AiJobEventType
            or type(self.ai_job_id) is not UUID
        ):
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        _require_sha256(self.command_fingerprint_sha256)
        _require_int(self.attempt_number, minimum=1, maximum=MAXIMUM_ATTEMPTS_CAP)
        if type(self.status) is not DurableJobStatus:
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        object.__setattr__(self, "occurred_at", require_durable_utc(self.occurred_at))
        _require_sha256(self.metadata_sha256)
        expected_metadata = _canonical_sha256(
            {
                "event_type": self.event_type.value,
                "ai_job_id": str(self.ai_job_id),
                "command_fingerprint_sha256": self.command_fingerprint_sha256,
                "attempt_number": self.attempt_number,
                "status": self.status.value,
                "occurred_at": self.occurred_at.isoformat(),
            }
        )
        expected_id = hashlib.sha256(
            b"ST-0706-OUTBOX-V2\x00" + expected_metadata.encode("ascii")
        ).hexdigest()
        if (
            self.metadata_sha256 != expected_metadata
            or self.intent_id_sha256 != expected_id
        ):
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)

    @classmethod
    def create(
        cls,
        *,
        event_type: AiJobEventType,
        command: AiJobCommand,
        attempt_number: int,
        status: DurableJobStatus,
        occurred_at: datetime,
    ) -> DurableOutboxIntent:
        timestamp = require_durable_utc(occurred_at)
        metadata = {
            "event_type": event_type.value,
            "ai_job_id": str(command.ai_job_id),
            "command_fingerprint_sha256": command.fingerprint_sha256,
            "attempt_number": attempt_number,
            "status": status.value,
            "occurred_at": timestamp.isoformat(),
        }
        metadata_sha256 = _canonical_sha256(metadata)
        return cls(
            intent_id_sha256=hashlib.sha256(
                b"ST-0706-OUTBOX-V2\x00" + metadata_sha256.encode("ascii")
            ).hexdigest(),
            event_type=event_type,
            ai_job_id=command.ai_job_id,
            command_fingerprint_sha256=command.fingerprint_sha256,
            attempt_number=attempt_number,
            status=status,
            occurred_at=timestamp,
            metadata_sha256=metadata_sha256,
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class DurableJobRecord(_RedactedValue):
    command: AiJobCommand
    status: DurableJobStatus
    attempt_number: int
    accumulated_cost_jpy: int
    available_at: datetime
    lease_epoch: int = 0
    lease: DurableLease | None = None
    decision_code: DurableDecisionCode | None = None
    completion_receipts: tuple[DurableCompletionReceipt, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.command) is not AiJobCommand
            or type(self.status) is not DurableJobStatus
        ):
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        _require_int(self.attempt_number, minimum=1, maximum=MAXIMUM_ATTEMPTS_CAP)
        if self.attempt_number < self.command.attempt_number:
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        _require_int(self.accumulated_cost_jpy)
        if (
            self.accumulated_cost_jpy
            > self.command.authorization.reservation.reserved_jpy
        ):
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        object.__setattr__(self, "available_at", require_durable_utc(self.available_at))
        _require_int(self.lease_epoch)
        if self.status is DurableJobStatus.LEASED:
            if (
                type(self.lease) is not DurableLease
                or self.lease.epoch != self.lease_epoch
            ):
                fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        elif self.lease is not None:
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        if self.status in TERMINAL_JOB_STATUSES:
            if type(self.decision_code) is not DurableDecisionCode:
                fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        elif self.decision_code is not None:
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        if type(self.completion_receipts) is not tuple or not all(
            type(receipt) is DurableCompletionReceipt
            for receipt in self.completion_receipts
        ):
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        if len(self.completion_receipts) > MAXIMUM_COMPLETION_RECEIPTS_PER_JOB:
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        receipt_keys = {
            (receipt.lease_epoch, receipt.lease_token_sha256)
            for receipt in self.completion_receipts
        }
        if len(receipt_keys) != len(self.completion_receipts):
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        if any(
            receipt.lease_epoch > self.lease_epoch
            or receipt.attempt_number > self.attempt_number
            or receipt.claimed_attempt_number > receipt.attempt_number
            or receipt.attempt_number > receipt.claimed_attempt_number + 1
            for receipt in self.completion_receipts
        ):
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)


@final
@dataclass(frozen=True, slots=True, repr=False)
class DurableQueueState(_RedactedValue):
    queue_id: str
    revision: int
    jobs: tuple[DurableJobRecord, ...] = ()
    outbox_intents: tuple[DurableOutboxIntent, ...] = ()

    def __post_init__(self) -> None:
        _require_token(self.queue_id)
        _require_int(self.revision)
        if type(self.jobs) is not tuple or not all(
            type(job) is DurableJobRecord for job in self.jobs
        ):
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        if type(self.outbox_intents) is not tuple or not all(
            type(intent) is DurableOutboxIntent for intent in self.outbox_intents
        ):
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        if len(self.jobs) > QUEUE_CAPACITY:
            fail_durable_queue(DurableQueueFailureCode.CAPACITY_EXCEEDED)
        if len(self.outbox_intents) > MAXIMUM_OUTBOX_INTENTS:
            fail_durable_queue(DurableQueueFailureCode.OUTBOX_CAPACITY_EXCEEDED)
        idempotency = {job.command.idempotency_key for job in self.jobs}
        operation_ids = {job.command.operation_id for job in self.jobs}
        ai_ids = {job.command.ai_job_id for job in self.jobs}
        ops_ids = {job.command.ops_job_id for job in self.jobs}
        reservation_ids = {
            job.command.authorization.reservation.reservation_id for job in self.jobs
        }
        if not (
            len(idempotency) == len(self.jobs)
            and len(operation_ids) == len(self.jobs)
            and len(ai_ids) == len(self.jobs)
            and len(ops_ids) == len(self.jobs)
            and len(reservation_ids) == len(self.jobs)
        ):
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        intent_ids = {intent.intent_id_sha256 for intent in self.outbox_intents}
        if len(intent_ids) != len(self.outbox_intents):
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        jobs_by_ai_id = {job.command.ai_job_id: job for job in self.jobs}
        intents_by_ai_id: dict[UUID, list[DurableOutboxIntent]] = {
            ai_job_id: [] for ai_job_id in jobs_by_ai_id
        }
        for intent in self.outbox_intents:
            job = jobs_by_ai_id.get(intent.ai_job_id)
            if (
                job is None
                or intent.command_fingerprint_sha256 != job.command.fingerprint_sha256
                or not job.command.attempt_number
                <= intent.attempt_number
                <= min(job.command.max_attempts, MAXIMUM_ATTEMPTS_CAP)
                or (
                    intent.event_type is AiJobEventType.SUCCEEDED
                    and intent.status is not DurableJobStatus.SUCCEEDED
                )
                or (
                    intent.event_type is AiJobEventType.FAILED
                    and intent.status not in TERMINAL_JOB_STATUSES
                )
                or (
                    intent.event_type is AiJobEventType.FAILED
                    and intent.status is DurableJobStatus.SUCCEEDED
                )
            ):
                fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
            intents_by_ai_id[intent.ai_job_id].append(intent)
        for ai_job_id, job in jobs_by_ai_id.items():
            job_intents = intents_by_ai_id[ai_job_id]
            requested = tuple(
                intent
                for intent in job_intents
                if intent.event_type is AiJobEventType.REQUESTED
            )
            terminal = tuple(
                intent
                for intent in job_intents
                if intent.event_type is not AiJobEventType.REQUESTED
            )
            if (
                len(requested) != 1
                or requested[0].attempt_number != job.command.attempt_number
                or requested[0].status
                not in {
                    DurableJobStatus.READY,
                    DurableJobStatus.CANCELLED,
                    DurableJobStatus.EXPIRED,
                }
                or (job.status in TERMINAL_JOB_STATUSES) != (len(terminal) == 1)
                or (
                    terminal
                    and (
                        terminal[0].status is not job.status
                        or terminal[0].attempt_number != job.attempt_number
                    )
                )
            ):
                fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
            for receipt in job.completion_receipts:
                expected_claim_sha256 = _canonical_sha256(
                    {
                        "queue_id": self.queue_id,
                        "ai_job_id": str(job.command.ai_job_id),
                        "command_fingerprint_sha256": job.command.fingerprint_sha256,
                        "worker_id": receipt.worker_id,
                        "lease_token_sha256": receipt.lease_token_sha256,
                        "lease_epoch": receipt.lease_epoch,
                        "attempt_number": receipt.claimed_attempt_number,
                        "leased_at": receipt.leased_at.isoformat(),
                        "leased_until": receipt.leased_until.isoformat(),
                    }
                )
                if receipt.claim_sha256 != expected_claim_sha256:
                    fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)


@final
@dataclass(frozen=True, slots=True, repr=False)
class DurableJobView(_RedactedValue):
    queue_id: str
    state_revision: int
    ai_job_id: UUID
    command_fingerprint_sha256: str
    status: DurableJobStatus
    attempt_number: int
    accumulated_cost_jpy: int
    available_at: datetime
    lease_epoch: int
    decision_code: DurableDecisionCode | None
    replayed: bool

    def __post_init__(self) -> None:
        _require_token(self.queue_id)
        _require_int(self.state_revision)
        if type(self.ai_job_id) is not UUID:
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        _require_sha256(self.command_fingerprint_sha256)
        if type(self.status) is not DurableJobStatus:
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        _require_int(self.attempt_number, minimum=1, maximum=MAXIMUM_ATTEMPTS_CAP)
        _require_int(self.accumulated_cost_jpy)
        object.__setattr__(self, "available_at", require_durable_utc(self.available_at))
        _require_int(self.lease_epoch)
        if (
            self.decision_code is not None
            and type(self.decision_code) is not DurableDecisionCode
        ):
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        if type(self.replayed) is not bool:
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)


def durable_job_view(
    *, state: DurableQueueState, job: DurableJobRecord, replayed: bool
) -> DurableJobView:
    return DurableJobView(
        queue_id=state.queue_id,
        state_revision=state.revision,
        ai_job_id=job.command.ai_job_id,
        command_fingerprint_sha256=job.command.fingerprint_sha256,
        status=job.status,
        attempt_number=job.attempt_number,
        accumulated_cost_jpy=job.accumulated_cost_jpy,
        available_at=job.available_at,
        lease_epoch=job.lease_epoch,
        decision_code=job.decision_code,
        replayed=replayed,
    )


def _command_to_data(command: AiJobCommand) -> dict[str, object]:
    identity = command.authorization.identity
    reservation = command.authorization.reservation
    return {
        "operation_id": command.operation_id,
        "idempotency_key": command.idempotency_key,
        "ai_job_id": str(command.ai_job_id),
        "ops_job_id": str(command.ops_job_id),
        "task_code": command.task_code,
        "source_packet_version_id": str(command.source_packet_version_id),
        "article_plan_id": str(command.article_plan_id)
        if command.article_plan_id
        else None,
        "article_version_id": (
            str(command.article_version_id) if command.article_version_id else None
        ),
        "authorization": {
            "identity": {
                "task_code": identity.task_code,
                "route_code": identity.route_code,
                "route_version": identity.route_version,
                "model_id": identity.model_id,
            },
            "certification_id": command.authorization.certification_id,
            "task_binding_sha256": command.authorization.task_binding_sha256,
            "route_sha256": command.authorization.route_sha256,
            "reservation": {
                "reservation_id": reservation.reservation_id,
                "operation_id": reservation.operation_id,
                "intent_sha256": reservation.intent_sha256,
                "quote_sha256": reservation.quote_sha256,
                "reserved_jpy": reservation.reserved_jpy,
                "reserved_at": reservation.reserved_at.isoformat(),
                "expires_at": reservation.expires_at.isoformat(),
            },
        },
        "input_artifact_id": str(command.input_artifact_id),
        "input_artifact_sha256": command.input_artifact_sha256,
        "validation_plan": {
            "plan_id": command.validation_plan.plan_id,
            "plan_sha256": command.validation_plan.plan_sha256,
        },
        "deadline_at": command.deadline_at.isoformat(),
        "attempt_number": command.attempt_number,
        "max_attempts": command.max_attempts,
        "cancellation_requested": command.cancellation_requested,
        "cancel_requested_at": (
            command.cancel_requested_at.isoformat()
            if command.cancel_requested_at is not None
            else None
        ),
        "fingerprint_sha256": command.fingerprint_sha256,
    }


def _command_from_data(value: object) -> AiJobCommand:
    data = _exact_dict(
        value,
        frozenset(
            {
                "operation_id",
                "idempotency_key",
                "ai_job_id",
                "ops_job_id",
                "task_code",
                "source_packet_version_id",
                "article_plan_id",
                "article_version_id",
                "authorization",
                "input_artifact_id",
                "input_artifact_sha256",
                "validation_plan",
                "deadline_at",
                "attempt_number",
                "max_attempts",
                "cancellation_requested",
                "cancel_requested_at",
                "fingerprint_sha256",
            }
        ),
    )
    authorization_data = _exact_dict(
        data["authorization"],
        frozenset(
            {
                "identity",
                "certification_id",
                "task_binding_sha256",
                "route_sha256",
                "reservation",
            }
        ),
    )
    identity_data = _exact_dict(
        authorization_data["identity"],
        frozenset({"task_code", "route_code", "route_version", "model_id"}),
    )
    reservation_data = _exact_dict(
        authorization_data["reservation"],
        frozenset(
            {
                "reservation_id",
                "operation_id",
                "intent_sha256",
                "quote_sha256",
                "reserved_jpy",
                "reserved_at",
                "expires_at",
            }
        ),
    )
    plan_data = _exact_dict(
        data["validation_plan"], frozenset({"plan_id", "plan_sha256"})
    )
    command: AiJobCommand | None = None
    try:
        identity = RouteIdentity(
            task_code=_state_token(identity_data["task_code"]),
            route_code=_state_token(identity_data["route_code"]),
            route_version=_state_token(identity_data["route_version"]),
            model_id=_state_token(identity_data["model_id"]),
        )
        reservation = BudgetReservation(
            reservation_id=_state_sha256(reservation_data["reservation_id"]),
            operation_id=_state_token(reservation_data["operation_id"]),
            intent_sha256=_state_sha256(reservation_data["intent_sha256"]),
            identity=identity,
            quote_sha256=_state_sha256(reservation_data["quote_sha256"]),
            reserved_jpy=_state_int(reservation_data["reserved_jpy"]),
            reserved_at=_state_datetime(reservation_data["reserved_at"]),
            expires_at=_state_datetime(reservation_data["expires_at"]),
        )
        authorization = AuthorizedRouteReservation(
            identity=identity,
            certification_id=_state_token(authorization_data["certification_id"]),
            task_binding_sha256=_state_sha256(
                authorization_data["task_binding_sha256"]
            ),
            route_sha256=_state_sha256(authorization_data["route_sha256"]),
            reservation=reservation,
        )
        command = AiJobCommand(
            operation_id=_state_token(data["operation_id"]),
            idempotency_key=_state_token(data["idempotency_key"]),
            ai_job_id=_state_uuid(data["ai_job_id"]),
            ops_job_id=_state_uuid(data["ops_job_id"]),
            task_code=_state_token(data["task_code"]),
            source_packet_version_id=_state_uuid(data["source_packet_version_id"]),
            article_plan_id=_state_optional_uuid(data["article_plan_id"]),
            article_version_id=_state_optional_uuid(data["article_version_id"]),
            authorization=authorization,
            input_artifact_id=_state_uuid(data["input_artifact_id"]),
            input_artifact_sha256=_state_sha256(data["input_artifact_sha256"]),
            validation_plan=ValidationPlanBinding(
                plan_id=_state_token(plan_data["plan_id"]),
                plan_sha256=_state_sha256(plan_data["plan_sha256"]),
            ),
            deadline_at=_state_datetime(data["deadline_at"]),
            attempt_number=_state_int(data["attempt_number"], minimum=1),
            max_attempts=_state_int(data["max_attempts"], minimum=1),
            cancellation_requested=_state_bool(data["cancellation_requested"]),
            cancel_requested_at=_state_optional_datetime(data["cancel_requested_at"]),
        )
    except Exception:
        command = None
    if command is None or command.fingerprint_sha256 != _state_sha256(
        data["fingerprint_sha256"]
    ):
        fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)
    return command


def _lease_to_data(lease: DurableLease | None) -> object:
    if lease is None:
        return None
    return {
        "worker_id": lease.worker_id,
        "lease_token_sha256": lease.lease_token_sha256,
        "epoch": lease.epoch,
        "claimed_at": lease.claimed_at.isoformat(),
        "expires_at": lease.expires_at.isoformat(),
    }


def _lease_from_data(value: object) -> DurableLease | None:
    if value is None:
        return None
    data = _exact_dict(
        value,
        frozenset(
            {"worker_id", "lease_token_sha256", "epoch", "claimed_at", "expires_at"}
        ),
    )
    try:
        return DurableLease(
            worker_id=_state_token(data["worker_id"]),
            lease_token_sha256=_state_sha256(data["lease_token_sha256"]),
            epoch=_state_int(data["epoch"], minimum=1),
            claimed_at=_state_datetime(data["claimed_at"]),
            expires_at=_state_datetime(data["expires_at"]),
        )
    except DurableQueueFailure:
        fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)


def _receipt_to_data(receipt: DurableCompletionReceipt) -> dict[str, object]:
    return {
        "claim_sha256": receipt.claim_sha256,
        "worker_id": receipt.worker_id,
        "lease_token_sha256": receipt.lease_token_sha256,
        "lease_epoch": receipt.lease_epoch,
        "claimed_attempt_number": receipt.claimed_attempt_number,
        "leased_at": receipt.leased_at.isoformat(),
        "leased_until": receipt.leased_until.isoformat(),
        "outcome_sha256": receipt.outcome_sha256,
        "status": receipt.status.value,
        "attempt_number": receipt.attempt_number,
        "accumulated_cost_jpy": receipt.accumulated_cost_jpy,
        "available_at": receipt.available_at.isoformat(),
        "decision_code": (
            receipt.decision_code.value if receipt.decision_code is not None else None
        ),
    }


def _receipt_from_data(value: object) -> DurableCompletionReceipt:
    data = _exact_dict(
        value,
        frozenset(
            {
                "lease_token_sha256",
                "claim_sha256",
                "worker_id",
                "lease_epoch",
                "claimed_attempt_number",
                "leased_at",
                "leased_until",
                "outcome_sha256",
                "status",
                "attempt_number",
                "accumulated_cost_jpy",
                "available_at",
                "decision_code",
            }
        ),
    )
    decision_value = data["decision_code"]
    decision = (
        None
        if decision_value is None
        else _enum_from_state(DurableDecisionCode, decision_value)
    )
    try:
        return DurableCompletionReceipt(
            claim_sha256=_state_sha256(data["claim_sha256"]),
            worker_id=_state_token(data["worker_id"]),
            lease_token_sha256=_state_sha256(data["lease_token_sha256"]),
            lease_epoch=_state_int(data["lease_epoch"], minimum=1),
            claimed_attempt_number=_state_int(
                data["claimed_attempt_number"], minimum=1
            ),
            leased_at=_state_datetime(data["leased_at"]),
            leased_until=_state_datetime(data["leased_until"]),
            outcome_sha256=_state_sha256(data["outcome_sha256"]),
            status=DurableJobStatus(_enum_from_state(DurableJobStatus, data["status"])),
            attempt_number=_state_int(data["attempt_number"], minimum=1),
            accumulated_cost_jpy=_state_int(data["accumulated_cost_jpy"]),
            available_at=_state_datetime(data["available_at"]),
            decision_code=(
                DurableDecisionCode(decision) if decision is not None else None
            ),
        )
    except DurableQueueFailure, ValueError, TypeError:
        fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)


def _job_to_data(job: DurableJobRecord) -> dict[str, object]:
    return {
        "command": _command_to_data(job.command),
        "status": job.status.value,
        "attempt_number": job.attempt_number,
        "accumulated_cost_jpy": job.accumulated_cost_jpy,
        "available_at": job.available_at.isoformat(),
        "lease_epoch": job.lease_epoch,
        "lease": _lease_to_data(job.lease),
        "decision_code": job.decision_code.value if job.decision_code else None,
        "completion_receipts": [
            _receipt_to_data(receipt) for receipt in job.completion_receipts
        ],
    }


def _job_from_data(value: object) -> DurableJobRecord:
    data = _exact_dict(
        value,
        frozenset(
            {
                "command",
                "status",
                "attempt_number",
                "accumulated_cost_jpy",
                "available_at",
                "lease_epoch",
                "lease",
                "decision_code",
                "completion_receipts",
            }
        ),
    )
    receipts_data = _exact_list(
        data["completion_receipts"], maximum=MAXIMUM_COMPLETION_RECEIPTS_PER_JOB
    )
    decision_value = data["decision_code"]
    try:
        return DurableJobRecord(
            command=_command_from_data(data["command"]),
            status=DurableJobStatus(_enum_from_state(DurableJobStatus, data["status"])),
            attempt_number=_state_int(data["attempt_number"], minimum=1),
            accumulated_cost_jpy=_state_int(data["accumulated_cost_jpy"]),
            available_at=_state_datetime(data["available_at"]),
            lease_epoch=_state_int(data["lease_epoch"]),
            lease=_lease_from_data(data["lease"]),
            decision_code=(
                None
                if decision_value is None
                else DurableDecisionCode(
                    _enum_from_state(DurableDecisionCode, decision_value)
                )
            ),
            completion_receipts=tuple(
                _receipt_from_data(item) for item in receipts_data
            ),
        )
    except DurableQueueFailure, ValueError, TypeError:
        fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)


def _intent_to_data(intent: DurableOutboxIntent) -> dict[str, object]:
    return {
        "intent_id_sha256": intent.intent_id_sha256,
        "event_type": intent.event_type.value,
        "ai_job_id": str(intent.ai_job_id),
        "command_fingerprint_sha256": intent.command_fingerprint_sha256,
        "attempt_number": intent.attempt_number,
        "status": intent.status.value,
        "occurred_at": intent.occurred_at.isoformat(),
        "metadata_sha256": intent.metadata_sha256,
        "delivery_status": "RECORDED_PENDING",
    }


def _intent_from_data(value: object) -> DurableOutboxIntent:
    data = _exact_dict(
        value,
        frozenset(
            {
                "intent_id_sha256",
                "event_type",
                "ai_job_id",
                "command_fingerprint_sha256",
                "attempt_number",
                "status",
                "occurred_at",
                "metadata_sha256",
                "delivery_status",
            }
        ),
    )
    if data["delivery_status"] != "RECORDED_PENDING":
        fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)
    try:
        return DurableOutboxIntent(
            intent_id_sha256=_state_sha256(data["intent_id_sha256"]),
            event_type=AiJobEventType(
                _enum_from_state(AiJobEventType, data["event_type"])
            ),
            ai_job_id=_state_uuid(data["ai_job_id"]),
            command_fingerprint_sha256=_state_sha256(
                data["command_fingerprint_sha256"]
            ),
            attempt_number=_state_int(data["attempt_number"], minimum=1),
            status=DurableJobStatus(_enum_from_state(DurableJobStatus, data["status"])),
            occurred_at=_state_datetime(data["occurred_at"]),
            metadata_sha256=_state_sha256(data["metadata_sha256"]),
        )
    except DurableQueueFailure, ValueError, TypeError:
        fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)


def encode_durable_queue_state(state: DurableQueueState) -> bytes:
    """Return exact canonical JSON bytes after full invariant validation."""

    if type(state) is not DurableQueueState:
        fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
    data = {
        "document_id": STATE_DOCUMENT_ID,
        "schema_version": STATE_SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "policy_sha256": POLICY_SHA256,
        "queue_id": state.queue_id,
        "revision": state.revision,
        "jobs": [
            _job_to_data(job)
            for job in sorted(state.jobs, key=lambda item: str(item.command.ai_job_id))
        ],
        "outbox_intents": [
            _intent_to_data(intent)
            for intent in sorted(
                state.outbox_intents, key=lambda item: item.intent_id_sha256
            )
        ],
    }
    encoded = _canonical_bytes(data) + b"\n"
    if len(encoded) > MAXIMUM_STATE_BYTES:
        fail_durable_queue(DurableQueueFailureCode.STATE_TOO_LARGE)
    return encoded


def decode_durable_queue_state(
    state_bytes: bytes, *, expected_queue_id: str, expected_revision: int
) -> DurableQueueState:
    """Fail closed on malformed, noncanonical, oversized, or unbound bytes."""

    _require_token(expected_queue_id)
    _require_int(expected_revision)
    if (
        type(state_bytes) is not bytes
        or not 0 < len(state_bytes) <= MAXIMUM_STATE_BYTES
    ):
        fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)
    data: object = None
    try:
        data = json.loads(state_bytes.decode("utf-8", errors="strict"))
    except UnicodeDecodeError, json.JSONDecodeError, RecursionError:
        pass
    root = _exact_dict(
        data,
        frozenset(
            {
                "document_id",
                "schema_version",
                "policy_id",
                "policy_sha256",
                "queue_id",
                "revision",
                "jobs",
                "outbox_intents",
            }
        ),
    )
    if (
        root["document_id"] != STATE_DOCUMENT_ID
        or root["schema_version"] != STATE_SCHEMA_VERSION
        or root["policy_id"] != POLICY_ID
        or root["policy_sha256"] != POLICY_SHA256
        or root["queue_id"] != expected_queue_id
        or root["revision"] != expected_revision
    ):
        fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)
    jobs_data = _exact_list(root["jobs"], maximum=QUEUE_CAPACITY)
    intents_data = _exact_list(root["outbox_intents"], maximum=MAXIMUM_OUTBOX_INTENTS)
    try:
        state = DurableQueueState(
            queue_id=_state_token(root["queue_id"]),
            revision=_state_int(root["revision"]),
            jobs=tuple(_job_from_data(item) for item in jobs_data),
            outbox_intents=tuple(_intent_from_data(item) for item in intents_data),
        )
    except DurableQueueFailure:
        fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)
    if encode_durable_queue_state(state) != state_bytes:
        fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)
    return state


def initial_durable_queue_state(queue_id: str) -> DurableQueueState:
    """Construct the canonical empty revision-zero state."""

    return DurableQueueState(queue_id=_require_token(queue_id), revision=0)


def snapshot_state(snapshot: DurableQueueSnapshot) -> DurableQueueState:
    """Decode and bind one exact snapshot."""

    if type(snapshot) is not DurableQueueSnapshot:
        fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
    return decode_durable_queue_state(
        snapshot.state_bytes,
        expected_queue_id=snapshot.queue_id,
        expected_revision=snapshot.revision,
    )


__all__ = [
    "DurableCompletionReceipt",
    "CONTRACT_SHA256",
    "DurableDecisionCode",
    "DurableJobRecord",
    "DurableJobStatus",
    "DurableJobView",
    "DurableLease",
    "DurableLeaseClaim",
    "DurableOutboxIntent",
    "DurableQueueFailure",
    "DurableQueueFailureCode",
    "DurableQueueSnapshot",
    "DurableQueueState",
    "MAXIMUM_ATTEMPTS_CAP",
    "MAXIMUM_COMPLETION_RECEIPTS_PER_JOB",
    "MAXIMUM_CUMULATIVE_RETRY_BACKOFF_SECONDS",
    "MAXIMUM_OUTBOX_INTENTS",
    "MAXIMUM_STATE_BYTES",
    "POLICY_ID",
    "POLICY_SHA256",
    "QUEUE_CAPACITY",
    "RETRY_BACKOFF_SECONDS_AFTER_ATTEMPT",
    "RecordedAttemptKind",
    "RecordedAttemptOutcome",
    "RecordedDurableQueueActivation",
    "TERMINAL_JOB_STATUSES",
    "decode_durable_queue_state",
    "durable_job_view",
    "encode_durable_queue_state",
    "fail_durable_queue",
    "initial_durable_queue_state",
    "require_durable_utc",
    "require_durable_sha256",
    "require_durable_token",
    "snapshot_state",
]

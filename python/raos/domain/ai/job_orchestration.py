"""Closed metadata-only values for recorded development AI job orchestration.

ST-0706 deliberately carries identifiers, hashes, bounded counters, and stable
classifications only.  Raw prompts, source packets, provider bodies, generated
content, arbitrary metadata, and exception material do not belong here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
import hashlib
import json
import re
from typing import NoReturn, SupportsIndex, final
from uuid import UUID

from raos.domain.ai.routing import (
    AuthorizedRouteReservation,
    BudgetCommit,
    BudgetRelease,
)


_SAFE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_SIGNED_BIGINT = (1 << 63) - 1
_MAX_ATTEMPTS = 50
_REDACTED = "<redacted-recorded-ai-job-orchestration>"


class OrchestrationFailureCode(str, Enum):
    """Stable sanitized failure classifications exposed by the local seam."""

    INVALID_REQUEST = "INVALID_REQUEST"
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"
    IDEMPOTENCY_MISMATCH = "IDEMPOTENCY_MISMATCH"
    AI_JOB_ID_CONFLICT = "AI_JOB_ID_CONFLICT"
    OPS_JOB_ID_CONFLICT = "OPS_JOB_ID_CONFLICT"
    STATE_EXCHANGE_FAILURE = "STATE_EXCHANGE_FAILURE"
    DEADLINE_EXPIRED = "DEADLINE_EXPIRED"
    CANCELLATION_REQUESTED = "CANCELLATION_REQUESTED"
    PROVIDER_REFUSAL = "PROVIDER_REFUSAL"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    PROVIDER_OBSERVATION_INVALID = "PROVIDER_OBSERVATION_INVALID"
    COST_EXCEEDED = "COST_EXCEEDED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    VALIDATION_UNAVAILABLE = "VALIDATION_UNAVAILABLE"
    VALIDATION_OBSERVATION_INVALID = "VALIDATION_OBSERVATION_INVALID"
    BUDGET_CONTROL_FAILURE = "BUDGET_CONTROL_FAILURE"
    BUDGET_RECEIPT_MISMATCH = "BUDGET_RECEIPT_MISMATCH"
    EVENT_RECORDING_FAILURE = "EVENT_RECORDING_FAILURE"
    QUARANTINED = "QUARANTINED"


@final
class OrchestrationFailure(RuntimeError):
    """Immutable failure that never retains rejected input or collaborator text."""

    __slots__ = ("_code",)
    _code: OrchestrationFailureCode

    def __init__(self, code: OrchestrationFailureCode) -> None:
        if type(code) is not OrchestrationFailureCode:
            raise TypeError("code must be an exact OrchestrationFailureCode")
        super().__init__(code.value)
        object.__setattr__(self, "_code", code)

    @property
    def code(self) -> OrchestrationFailureCode:
        return self._code

    def __setattr__(self, name: str, value: object) -> None:
        if name == "__traceback__":
            BaseException.__setattr__(self, name, value)
            return
        del name, value
        raise AttributeError("OrchestrationFailure is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("OrchestrationFailure is immutable")

    def __repr__(self) -> str:
        return f"OrchestrationFailure(code={self.code!r})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("orchestration failure serialization is unsupported")


def fail_orchestration(code: OrchestrationFailureCode) -> NoReturn:
    """Raise one stable failure without retaining a prior exception chain."""

    raise OrchestrationFailure(code) from None


def require_orchestration_utc(value: object) -> datetime:
    """Accept only an exact datetime using the explicit UTC singleton."""

    if type(value) is not datetime or value.tzinfo is not UTC:
        fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
    return value


def _require_uuid(value: object) -> UUID:
    if type(value) is not UUID:
        fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
    return value


def _require_token(value: object) -> str:
    if type(value) is not str or _SAFE_TOKEN.fullmatch(value) is None:
        fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
    return value


def _require_sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
    return value


def _require_nonnegative_int(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_SIGNED_BIGINT:
        fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
    return value


def _require_positive_int(value: object, *, maximum: int = _MAX_SIGNED_BIGINT) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
    return value


def _canonical_sha256(value: dict[str, object]) -> str:
    encoded: bytes | None = None
    failed = False
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeEncodeError, RecursionError:
        failed = True
    if failed or encoded is None:
        fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
    return hashlib.sha256(encoded).hexdigest()


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded orchestration value serialization is unsupported")


class ProviderOutcomeKind(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    REFUSED = "REFUSED"
    TIMED_OUT = "TIMED_OUT"
    FAILED = "FAILED"


class ProviderFailureClass(str, Enum):
    RATE_LIMIT = "RATE_LIMIT"
    TRANSIENT_ERROR = "TRANSIENT_ERROR"
    TIMEOUT = "TIMEOUT"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    REFUSAL = "REFUSAL"
    CONTENT_FILTER = "CONTENT_FILTER"
    INCOMPLETE_MAX_OUTPUT = "INCOMPLETE_MAX_OUTPUT"
    CONTRACT = "CONTRACT"
    POLICY = "POLICY"
    AUTH = "AUTH"
    PERMANENT = "PERMANENT"
    BUDGET = "BUDGET"


class ValidationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"


class ValidationFailureClass(str, Enum):
    SCHEMA = "SCHEMA"
    FACTUAL = "FACTUAL"
    POLICY = "POLICY"
    SECURITY = "SECURITY"
    PLAN_UNAVAILABLE = "PLAN_UNAVAILABLE"


class JobDisposition(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    RETRY_DEFERRED = "RETRY_DEFERRED"
    QUARANTINED = "QUARANTINED"
    BLOCKED = "BLOCKED"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class StateExchangeKind(str, Enum):
    NEW = "NEW"
    REPLAY = "REPLAY"
    IDEMPOTENCY_MISMATCH = "IDEMPOTENCY_MISMATCH"
    AI_JOB_ID_CONFLICT = "AI_JOB_ID_CONFLICT"
    OPS_JOB_ID_CONFLICT = "OPS_JOB_ID_CONFLICT"


class AiJobEventType(str, Enum):
    REQUESTED = "jp.raos.ai.job_requested.v1"
    SUCCEEDED = "jp.raos.ai.job_succeeded.v1"
    FAILED = "jp.raos.ai.job_failed.v1"


@final
@dataclass(frozen=True, slots=True, repr=False)
class ValidationPlanBinding(_RedactedValue):
    """Exact identity and byte hash of the installed ST-0705 plan."""

    plan_id: str
    plan_sha256: str

    def __post_init__(self) -> None:
        _require_token(self.plan_id)
        _require_sha256(self.plan_sha256)


@final
@dataclass(frozen=True, slots=True, repr=False)
class AiJobCommand(_RedactedValue):
    """One already-authorized metadata-only orchestration command."""

    operation_id: str
    idempotency_key: str
    ai_job_id: UUID
    ops_job_id: UUID
    task_code: str
    source_packet_version_id: UUID
    article_plan_id: UUID | None
    article_version_id: UUID | None
    authorization: AuthorizedRouteReservation
    input_artifact_id: UUID
    input_artifact_sha256: str
    validation_plan: ValidationPlanBinding
    deadline_at: datetime
    attempt_number: int
    max_attempts: int
    cancellation_requested: bool
    cancel_requested_at: datetime | None
    fingerprint_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _require_token(self.operation_id)
        _require_token(self.idempotency_key)
        _require_uuid(self.ai_job_id)
        _require_uuid(self.ops_job_id)
        _require_token(self.task_code)
        _require_uuid(self.source_packet_version_id)
        if (self.article_plan_id is None) == (self.article_version_id is None):
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        if self.article_plan_id is not None:
            _require_uuid(self.article_plan_id)
        if self.article_version_id is not None:
            _require_uuid(self.article_version_id)
        if type(self.authorization) is not AuthorizedRouteReservation:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        if self.authorization.identity.task_code != self.task_code:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        _require_uuid(self.input_artifact_id)
        _require_sha256(self.input_artifact_sha256)
        if type(self.validation_plan) is not ValidationPlanBinding:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        deadline_at = require_orchestration_utc(self.deadline_at)
        _require_positive_int(self.attempt_number, maximum=_MAX_ATTEMPTS)
        _require_positive_int(self.max_attempts, maximum=_MAX_ATTEMPTS)
        if self.attempt_number > self.max_attempts:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        if type(self.cancellation_requested) is not bool:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        if self.cancellation_requested != (self.cancel_requested_at is not None):
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        cancel_requested_at: datetime | None = None
        if self.cancel_requested_at is not None:
            cancel_requested_at = require_orchestration_utc(self.cancel_requested_at)
            if cancel_requested_at > deadline_at:
                fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        if deadline_at > self.authorization.reservation.expires_at:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        object.__setattr__(self, "deadline_at", deadline_at)
        object.__setattr__(self, "cancel_requested_at", cancel_requested_at)
        object.__setattr__(
            self,
            "fingerprint_sha256",
            _canonical_sha256(
                {
                    "operation_id": self.operation_id,
                    "idempotency_key": self.idempotency_key,
                    "ai_job_id": str(self.ai_job_id),
                    "ops_job_id": str(self.ops_job_id),
                    "task_code": self.task_code,
                    "source_packet_version_id": str(self.source_packet_version_id),
                    "article_plan_id": (
                        str(self.article_plan_id)
                        if self.article_plan_id is not None
                        else None
                    ),
                    "article_version_id": (
                        str(self.article_version_id)
                        if self.article_version_id is not None
                        else None
                    ),
                    "route_code": self.authorization.identity.route_code,
                    "route_version": self.authorization.identity.route_version,
                    "model_id": self.authorization.identity.model_id,
                    "certification_id": self.authorization.certification_id,
                    "task_binding_sha256": self.authorization.task_binding_sha256,
                    "route_sha256": self.authorization.route_sha256,
                    "reservation_id": self.authorization.reservation.reservation_id,
                    "reservation_intent_sha256": (
                        self.authorization.reservation.intent_sha256
                    ),
                    "reserved_jpy": self.authorization.reservation.reserved_jpy,
                    "input_artifact_id": str(self.input_artifact_id),
                    "input_artifact_sha256": self.input_artifact_sha256,
                    "validation_plan_id": self.validation_plan.plan_id,
                    "validation_plan_sha256": self.validation_plan.plan_sha256,
                    "deadline_at": deadline_at.isoformat(),
                    "attempt_number": self.attempt_number,
                    "max_attempts": self.max_attempts,
                    "cancellation_requested": self.cancellation_requested,
                    "cancel_requested_at": (
                        cancel_requested_at.isoformat()
                        if cancel_requested_at is not None
                        else None
                    ),
                }
            ),
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class ProviderExecutionRequest(_RedactedValue):
    """Metadata-only provider request derived from one exact command."""

    operation_id: str
    command_fingerprint_sha256: str
    ai_job_id: UUID
    ops_job_id: UUID
    task_code: str
    attempt_number: int
    authorization: AuthorizedRouteReservation
    input_artifact_id: UUID
    input_artifact_sha256: str
    deadline_at: datetime

    def __post_init__(self) -> None:
        _require_token(self.operation_id)
        _require_sha256(self.command_fingerprint_sha256)
        _require_uuid(self.ai_job_id)
        _require_uuid(self.ops_job_id)
        _require_token(self.task_code)
        _require_positive_int(self.attempt_number, maximum=_MAX_ATTEMPTS)
        if type(self.authorization) is not AuthorizedRouteReservation:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        if self.authorization.identity.task_code != self.task_code:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        _require_uuid(self.input_artifact_id)
        _require_sha256(self.input_artifact_sha256)
        object.__setattr__(
            self, "deadline_at", require_orchestration_utc(self.deadline_at)
        )

    @classmethod
    def from_command(cls, command: AiJobCommand) -> ProviderExecutionRequest:
        if type(command) is not AiJobCommand:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        return cls(
            operation_id=command.operation_id,
            command_fingerprint_sha256=command.fingerprint_sha256,
            ai_job_id=command.ai_job_id,
            ops_job_id=command.ops_job_id,
            task_code=command.task_code,
            attempt_number=command.attempt_number,
            authorization=command.authorization,
            input_artifact_id=command.input_artifact_id,
            input_artifact_sha256=command.input_artifact_sha256,
            deadline_at=command.deadline_at,
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class ProviderExecutionOutcome(_RedactedValue):
    """One metadata-only recorded provider outcome; never provider content."""

    kind: ProviderOutcomeKind
    ai_job_id: UUID
    attempt_number: int
    provider_request_id: str | None
    output_artifact_id: UUID | None
    output_artifact_sha256: str | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    actual_cost_jpy: int | None
    failure_class: ProviderFailureClass | None
    retryable: bool

    def __post_init__(self) -> None:
        if type(self.kind) is not ProviderOutcomeKind:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        _require_uuid(self.ai_job_id)
        _require_positive_int(self.attempt_number, maximum=_MAX_ATTEMPTS)
        if self.provider_request_id is not None:
            _require_token(self.provider_request_id)
        if type(self.retryable) is not bool:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        token_values = (self.input_tokens, self.output_tokens, self.total_tokens)
        tokens_present = tuple(item is not None for item in token_values)
        if any(tokens_present) and not all(tokens_present):
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        if all(tokens_present):
            input_tokens = _require_nonnegative_int(self.input_tokens)
            output_tokens = _require_nonnegative_int(self.output_tokens)
            total_tokens = _require_nonnegative_int(self.total_tokens)
            if input_tokens > _MAX_SIGNED_BIGINT - output_tokens:
                fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
            if total_tokens != input_tokens + output_tokens:
                fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        if self.actual_cost_jpy is not None:
            _require_nonnegative_int(self.actual_cost_jpy)
        if self.kind is ProviderOutcomeKind.SUCCEEDED:
            if (
                self.output_artifact_id is None
                or self.output_artifact_sha256 is None
                or not all(tokens_present)
                or self.actual_cost_jpy is None
                or self.failure_class is not None
                or self.retryable
            ):
                fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
            _require_uuid(self.output_artifact_id)
            _require_sha256(self.output_artifact_sha256)
        else:
            if (
                self.output_artifact_id is not None
                or self.output_artifact_sha256 is not None
                or type(self.failure_class) is not ProviderFailureClass
            ):
                fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
            if self.kind is ProviderOutcomeKind.REFUSED and (
                self.failure_class
                not in {
                    ProviderFailureClass.REFUSAL,
                    ProviderFailureClass.CONTENT_FILTER,
                }
                or self.retryable
            ):
                fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
            if self.kind is ProviderOutcomeKind.TIMED_OUT and (
                self.failure_class is not ProviderFailureClass.TIMEOUT
            ):
                fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)


@final
@dataclass(frozen=True, slots=True, repr=False)
class ValidationRequest(_RedactedValue):
    ai_job_id: UUID
    attempt_number: int
    output_artifact_id: UUID
    output_artifact_sha256: str
    plan: ValidationPlanBinding

    def __post_init__(self) -> None:
        _require_uuid(self.ai_job_id)
        _require_positive_int(self.attempt_number, maximum=_MAX_ATTEMPTS)
        _require_uuid(self.output_artifact_id)
        _require_sha256(self.output_artifact_sha256)
        if type(self.plan) is not ValidationPlanBinding:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)


@final
@dataclass(frozen=True, slots=True, repr=False)
class ValidationObservation(_RedactedValue):
    status: ValidationStatus
    ai_job_id: UUID
    attempt_number: int
    output_artifact_id: UUID
    output_artifact_sha256: str
    plan: ValidationPlanBinding
    failure_class: ValidationFailureClass | None

    def __post_init__(self) -> None:
        if type(self.status) is not ValidationStatus:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        _require_uuid(self.ai_job_id)
        _require_positive_int(self.attempt_number, maximum=_MAX_ATTEMPTS)
        _require_uuid(self.output_artifact_id)
        _require_sha256(self.output_artifact_sha256)
        if type(self.plan) is not ValidationPlanBinding:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        if self.status is ValidationStatus.PASS:
            if self.failure_class is not None:
                fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        elif type(self.failure_class) is not ValidationFailureClass:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)


@final
@dataclass(frozen=True, slots=True, repr=False)
class AiJobResult(_RedactedValue):
    """Exact terminal/deferred observation retained by the recorded store."""

    operation_id: str
    command_fingerprint_sha256: str
    ai_job_id: UUID
    ops_job_id: UUID
    task_code: str
    attempt_number: int
    disposition: JobDisposition
    failure_code: OrchestrationFailureCode | None
    retryable: bool
    actual_cost_jpy: int | None
    output_artifact_id: UUID | None
    output_artifact_sha256: str | None
    provider_request_id: str | None
    validation_status: ValidationStatus | None
    budget_receipt: BudgetCommit | BudgetRelease | None

    def __post_init__(self) -> None:
        _require_token(self.operation_id)
        _require_sha256(self.command_fingerprint_sha256)
        _require_uuid(self.ai_job_id)
        _require_uuid(self.ops_job_id)
        _require_token(self.task_code)
        _require_positive_int(self.attempt_number, maximum=_MAX_ATTEMPTS)
        if type(self.disposition) is not JobDisposition:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        if type(self.retryable) is not bool:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        if self.actual_cost_jpy is not None:
            _require_nonnegative_int(self.actual_cost_jpy)
        output_pair = (
            self.output_artifact_id is not None,
            self.output_artifact_sha256 is not None,
        )
        if output_pair[0] != output_pair[1]:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        if self.output_artifact_id is not None:
            _require_uuid(self.output_artifact_id)
            _require_sha256(self.output_artifact_sha256)
        if self.provider_request_id is not None:
            _require_token(self.provider_request_id)
        if self.validation_status is not None and (
            type(self.validation_status) is not ValidationStatus
        ):
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        if self.budget_receipt is not None and type(self.budget_receipt) not in {
            BudgetCommit,
            BudgetRelease,
        }:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        if self.disposition is JobDisposition.SUCCEEDED:
            if (
                self.failure_code is not None
                or self.retryable
                or self.actual_cost_jpy is None
                or self.output_artifact_id is None
                or self.validation_status is not ValidationStatus.PASS
                or type(self.budget_receipt) is not BudgetCommit
            ):
                fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        elif type(self.failure_code) is not OrchestrationFailureCode:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedJobStateExchange(_RedactedValue):
    kind: StateExchangeKind
    result: AiJobResult | None

    def __post_init__(self) -> None:
        if type(self.kind) is not StateExchangeKind:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        if self.kind is StateExchangeKind.NEW:
            if self.result is not None:
                fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        elif type(self.result) is not AiJobResult:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)


@final
@dataclass(frozen=True, slots=True, repr=False)
class AiJobEventObservation(_RedactedValue):
    """Metadata-only observation matching one canonical AI event meaning."""

    event_type: AiJobEventType
    operation_id: str
    command_fingerprint_sha256: str
    ai_job_id: UUID
    ops_job_id: UUID
    task_code: str
    attempt_number: int
    reserved_jpy: int
    disposition: JobDisposition | None
    failure_code: OrchestrationFailureCode | None
    retryable: bool | None
    actual_cost_jpy: int | None
    output_artifact_id: UUID | None
    output_artifact_sha256: str | None
    validation_passed: bool | None

    def __post_init__(self) -> None:
        if type(self.event_type) is not AiJobEventType:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        _require_token(self.operation_id)
        _require_sha256(self.command_fingerprint_sha256)
        _require_uuid(self.ai_job_id)
        _require_uuid(self.ops_job_id)
        _require_token(self.task_code)
        _require_positive_int(self.attempt_number, maximum=_MAX_ATTEMPTS)
        _require_nonnegative_int(self.reserved_jpy)
        output_pair = (
            self.output_artifact_id is not None,
            self.output_artifact_sha256 is not None,
        )
        if output_pair[0] != output_pair[1]:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        if self.output_artifact_id is not None:
            _require_uuid(self.output_artifact_id)
            _require_sha256(self.output_artifact_sha256)
        if self.actual_cost_jpy is not None:
            _require_nonnegative_int(self.actual_cost_jpy)
        if self.event_type is AiJobEventType.REQUESTED:
            if any(
                item is not None
                for item in (
                    self.disposition,
                    self.failure_code,
                    self.retryable,
                    self.actual_cost_jpy,
                    self.output_artifact_id,
                    self.validation_passed,
                )
            ):
                fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        elif self.event_type is AiJobEventType.SUCCEEDED:
            if (
                self.disposition is not JobDisposition.SUCCEEDED
                or self.failure_code is not None
                or self.retryable is not False
                or self.actual_cost_jpy is None
                or self.output_artifact_id is None
                or self.validation_passed is not True
            ):
                fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        elif (
            type(self.disposition) is not JobDisposition
            or self.disposition is JobDisposition.SUCCEEDED
            or type(self.failure_code) is not OrchestrationFailureCode
            or type(self.retryable) is not bool
            or self.validation_passed is not False
        ):
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)


__all__ = [
    "AiJobCommand",
    "AiJobEventObservation",
    "AiJobEventType",
    "AiJobResult",
    "JobDisposition",
    "OrchestrationFailure",
    "OrchestrationFailureCode",
    "ProviderExecutionOutcome",
    "ProviderExecutionRequest",
    "ProviderFailureClass",
    "ProviderOutcomeKind",
    "RecordedJobStateExchange",
    "StateExchangeKind",
    "ValidationFailureClass",
    "ValidationObservation",
    "ValidationPlanBinding",
    "ValidationRequest",
    "ValidationStatus",
    "fail_orchestration",
    "require_orchestration_utc",
]

"""Closed, provider-neutral telemetry values for local observation seams.

The caller supplies every identifier explicitly.  These values neither consult
ambient state nor derive identifiers from one another.  Their printable form is
always redacted and generic serialization is deliberately unsupported.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
import math
import re
from typing import NoReturn, SupportsIndex, final
from uuid import UUID


_PROVIDER_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z")
_SIGNAL_NAME = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_REDACTED = "<redacted-telemetry>"
_MAX_DURATION_MS = 86_400_000
_MAX_METRIC_VALUE = 1_000_000_000_000_000.0


class TelemetrySignal(str, Enum):
    """The only signal families admitted by the telemetry port."""

    TRACE = "TRACE"
    METRIC = "METRIC"
    LOG = "LOG"


class TelemetryOutcome(str, Enum):
    """Exact result returned separately from the observed business work."""

    RECORDED = "RECORDED"
    DISABLED = "DISABLED"
    DROPPED = "DROPPED"
    SINK_FAILED = "SINK_FAILED"


class TraceOutcome(str, Enum):
    """Low-cardinality trace completion classifications."""

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MetricUnit(str, Enum):
    """Closed units supported by the initial metric seam."""

    COUNT = "COUNT"
    MILLISECONDS = "MILLISECONDS"
    BYTES = "BYTES"


class LogLevel(str, Enum):
    """Closed levels for sanitized operational events."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class TelemetryFailureCode(str, Enum):
    """Sanitized domain failure classifications."""

    INVALID_ARGUMENT = "INVALID_ARGUMENT"


@final
class TelemetryFailure(ValueError):
    """Immutable failure that never retains a rejected value."""

    __slots__ = ("_code",)
    _code: TelemetryFailureCode

    def __init__(self, code: TelemetryFailureCode) -> None:
        if type(code) is not TelemetryFailureCode:
            raise TypeError("code must be an exact TelemetryFailureCode")
        ValueError.__init__(self, code.value)
        object.__setattr__(self, "_code", code)

    @property
    def code(self) -> TelemetryFailureCode:
        return self._code

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("TelemetryFailure is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("TelemetryFailure is immutable")

    def __repr__(self) -> str:
        return "TelemetryFailure(code=INVALID_ARGUMENT)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("telemetry failure serialization is not supported")


def _fail() -> NoReturn:
    raise TelemetryFailure(TelemetryFailureCode.INVALID_ARGUMENT) from None


def _require_uuid(value: object, *, optional: bool = False) -> UUID | None:
    if optional and value is None:
        return None
    if type(value) is not UUID:
        _fail()
    return value


def _require_utc(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is not UTC or value.fold != 0:
        _fail()
    return value


def _require_name(value: object) -> str:
    if type(value) is not str or _SIGNAL_NAME.fullmatch(value) is None:
        _fail()
    return value


class _RedactedTelemetryValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("telemetry value is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("telemetry value is immutable")

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("telemetry value serialization is not supported")


@final
class TelemetryContext(_RedactedTelemetryValue):
    """Fixed-shape correlation context supplied explicitly by the caller."""

    __slots__ = (
        "_article_id",
        "_causation_id",
        "_correlation_id",
        "_job_id",
        "_provider_request_id",
        "_snapshot_id",
    )
    _article_id: UUID | None
    _causation_id: UUID | None
    _correlation_id: UUID
    _job_id: UUID | None
    _provider_request_id: str | None
    _snapshot_id: UUID | None

    def __init__(
        self,
        *,
        correlation_id: UUID,
        causation_id: UUID | None = None,
        job_id: UUID | None = None,
        article_id: UUID | None = None,
        snapshot_id: UUID | None = None,
        provider_request_id: str | None = None,
    ) -> None:
        correlation = _require_uuid(correlation_id)
        causation = _require_uuid(causation_id, optional=True)
        job = _require_uuid(job_id, optional=True)
        article = _require_uuid(article_id, optional=True)
        snapshot = _require_uuid(snapshot_id, optional=True)
        if provider_request_id is not None and (
            type(provider_request_id) is not str
            or _PROVIDER_REQUEST_ID.fullmatch(provider_request_id) is None
        ):
            _fail()
        object.__setattr__(self, "_correlation_id", correlation)
        object.__setattr__(self, "_causation_id", causation)
        object.__setattr__(self, "_job_id", job)
        object.__setattr__(self, "_article_id", article)
        object.__setattr__(self, "_snapshot_id", snapshot)
        object.__setattr__(self, "_provider_request_id", provider_request_id)

    @property
    def correlation_id(self) -> UUID:
        return self._correlation_id

    @property
    def causation_id(self) -> UUID | None:
        return self._causation_id

    @property
    def job_id(self) -> UUID | None:
        return self._job_id

    @property
    def article_id(self) -> UUID | None:
        return self._article_id

    @property
    def snapshot_id(self) -> UUID | None:
        return self._snapshot_id

    @property
    def provider_request_id(self) -> str | None:
        return self._provider_request_id


class _SignalRecord(_RedactedTelemetryValue):
    __slots__ = ("_context", "_name", "_observed_at")
    _context: TelemetryContext
    _name: str
    _observed_at: datetime

    def _set_common(
        self, *, context: TelemetryContext, observed_at: datetime, name: str
    ) -> None:
        if type(context) is not TelemetryContext:
            _fail()
        object.__setattr__(self, "_context", context)
        object.__setattr__(self, "_observed_at", _require_utc(observed_at))
        object.__setattr__(self, "_name", _require_name(name))

    @property
    def context(self) -> TelemetryContext:
        return self._context

    @property
    def observed_at(self) -> datetime:
        return self._observed_at

    @property
    def name(self) -> str:
        return self._name


@final
class TraceRecord(_SignalRecord):
    """One completed trace observation with no free-form fields."""

    __slots__ = ("_duration_ms", "_outcome")
    _duration_ms: int
    _outcome: TraceOutcome

    def __init__(
        self,
        *,
        context: TelemetryContext,
        observed_at: datetime,
        name: str,
        outcome: TraceOutcome,
        duration_ms: int,
    ) -> None:
        self._set_common(context=context, observed_at=observed_at, name=name)
        if type(outcome) is not TraceOutcome:
            _fail()
        if (
            type(duration_ms) is not int
            or duration_ms < 0
            or duration_ms > _MAX_DURATION_MS
        ):
            _fail()
        object.__setattr__(self, "_outcome", outcome)
        object.__setattr__(self, "_duration_ms", duration_ms)

    @property
    def signal(self) -> TelemetrySignal:
        return TelemetrySignal.TRACE

    @property
    def outcome(self) -> TraceOutcome:
        return self._outcome

    @property
    def duration_ms(self) -> int:
        return self._duration_ms


@final
class MetricRecord(_SignalRecord):
    """One bounded non-negative measurement with a closed unit."""

    __slots__ = ("_unit", "_value")
    _unit: MetricUnit
    _value: float

    def __init__(
        self,
        *,
        context: TelemetryContext,
        observed_at: datetime,
        name: str,
        value: int | float,
        unit: MetricUnit,
    ) -> None:
        self._set_common(context=context, observed_at=observed_at, name=name)
        if type(unit) is not MetricUnit or type(value) not in {int, float}:
            _fail()
        if type(value) is int and (value < 0 or value > int(_MAX_METRIC_VALUE)):
            _fail()
        normalized = float(value)
        if (
            not math.isfinite(normalized)
            or normalized < 0.0
            or normalized > _MAX_METRIC_VALUE
        ):
            _fail()
        object.__setattr__(self, "_value", normalized)
        object.__setattr__(self, "_unit", unit)

    @property
    def signal(self) -> TelemetrySignal:
        return TelemetrySignal.METRIC

    @property
    def value(self) -> float:
        return self._value

    @property
    def unit(self) -> MetricUnit:
        return self._unit


@final
class LogRecord(_SignalRecord):
    """One sanitized operational event with no text-bearing field."""

    __slots__ = ("_level",)
    _level: LogLevel

    def __init__(
        self,
        *,
        context: TelemetryContext,
        observed_at: datetime,
        name: str,
        level: LogLevel,
    ) -> None:
        self._set_common(context=context, observed_at=observed_at, name=name)
        if type(level) is not LogLevel:
            _fail()
        object.__setattr__(self, "_level", level)

    @property
    def signal(self) -> TelemetrySignal:
        return TelemetrySignal.LOG

    @property
    def level(self) -> LogLevel:
        return self._level


TelemetryRecord = TraceRecord | MetricRecord | LogRecord


__all__ = [
    "LogLevel",
    "LogRecord",
    "MetricRecord",
    "MetricUnit",
    "TelemetryContext",
    "TelemetryFailure",
    "TelemetryFailureCode",
    "TelemetryOutcome",
    "TelemetryRecord",
    "TelemetrySignal",
    "TraceOutcome",
    "TraceRecord",
]

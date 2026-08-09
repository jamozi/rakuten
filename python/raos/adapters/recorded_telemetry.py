"""Disabled and bounded process-local telemetry sinks.

These adapters provide no exporter, persistence, environment discovery, or
process lifecycle.  The recorded variant is limited to exact development and
CI runtime values and drops the newest observation once its capacity is full.
"""

from __future__ import annotations

from threading import RLock
from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ops.telemetry import (
    LogRecord,
    MetricRecord,
    TelemetryFailure,
    TelemetryFailureCode,
    TelemetryOutcome,
    TelemetryRecord,
    TraceRecord,
)


_MAX_CAPACITY = 10_000
_RECORD_TYPES = (TraceRecord, MetricRecord, LogRecord)


def _require_record(record: object) -> TelemetryRecord:
    if type(record) not in _RECORD_TYPES:
        raise TelemetryFailure(TelemetryFailureCode.INVALID_ARGUMENT) from None
    return cast(TelemetryRecord, record)


@final
class DisabledTelemetrySink:
    """A deterministic sink that observes and retains nothing."""

    __slots__ = ()

    def emit(self, record: TelemetryRecord) -> TelemetryOutcome:
        _require_record(record)
        return TelemetryOutcome.DISABLED


@final
class RecordedTelemetrySink:
    """A bounded ordered recorder for exact development and CI use only."""

    __slots__ = ("_capacity", "_drop_count", "_environment", "_lock", "_records")

    def __init__(self, *, environment: RuntimeEnvironment, capacity: int) -> None:
        if type(environment) is not RuntimeEnvironment or environment not in {
            RuntimeEnvironment.ENV_DEV,
            RuntimeEnvironment.CI,
        }:
            raise TelemetryFailure(TelemetryFailureCode.INVALID_ARGUMENT) from None
        if type(capacity) is not int or not 1 <= capacity <= _MAX_CAPACITY:
            raise TelemetryFailure(TelemetryFailureCode.INVALID_ARGUMENT) from None
        self._environment = environment
        self._capacity = capacity
        self._lock = RLock()
        self._records: tuple[TelemetryRecord, ...] = ()
        self._drop_count = 0

    @property
    def environment(self) -> RuntimeEnvironment:
        return self._environment

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def drop_count(self) -> int:
        with self._lock:
            return self._drop_count

    def snapshot(self) -> tuple[TelemetryRecord, ...]:
        """Return the current immutable ordered process-local snapshot."""

        with self._lock:
            return self._records

    def emit(self, record: TelemetryRecord) -> TelemetryOutcome:
        admitted = _require_record(record)
        with self._lock:
            if len(self._records) >= self._capacity:
                self._drop_count += 1
                return TelemetryOutcome.DROPPED
            self._records = (*self._records, admitted)
            return TelemetryOutcome.RECORDED


__all__ = ["DisabledTelemetrySink", "RecordedTelemetrySink"]

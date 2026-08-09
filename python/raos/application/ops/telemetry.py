"""Best-effort telemetry orchestration isolated from business outcomes."""

from __future__ import annotations

from typing import final

from raos.domain.ops.telemetry import (
    LogRecord,
    MetricRecord,
    TelemetryFailure,
    TelemetryFailureCode,
    TelemetryOutcome,
    TelemetryRecord,
    TraceRecord,
)
from raos.ports.telemetry import TelemetrySink


_RECORD_TYPES = (TraceRecord, MetricRecord, LogRecord)


@final
class TelemetryRecorder:
    """Attempt one synchronous observation and report it independently."""

    __slots__ = ("_sink",)

    def __init__(self, *, sink: TelemetrySink) -> None:
        self._sink = sink

    def record(self, record: TelemetryRecord) -> TelemetryOutcome:
        """Emit once; ordinary sink faults collapse to a sanitized outcome."""

        if type(record) not in _RECORD_TYPES:
            raise TelemetryFailure(TelemetryFailureCode.INVALID_ARGUMENT) from None
        try:
            outcome = self._sink.emit(record)
        except Exception:
            return TelemetryOutcome.SINK_FAILED
        if type(outcome) is not TelemetryOutcome:
            return TelemetryOutcome.SINK_FAILED
        return outcome


__all__ = ["TelemetryRecorder"]

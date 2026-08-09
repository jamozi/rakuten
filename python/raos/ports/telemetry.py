"""Inward port for one closed telemetry record at a time."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.ops.telemetry import TelemetryOutcome, TelemetryRecord


@runtime_checkable
class TelemetrySink(Protocol):
    """A synchronous best-effort destination for exact telemetry records."""

    def emit(self, record: TelemetryRecord) -> TelemetryOutcome:
        """Observe one fixed-shape record and return one closed outcome."""

        ...


__all__ = ["TelemetrySink"]

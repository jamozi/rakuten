"""Synthetic fixed-shape fixtures for the isolated ST-1601 suite."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys
from uuid import UUID


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.domain.ops.telemetry import (  # noqa: E402
    LogLevel,
    LogRecord,
    MetricRecord,
    MetricUnit,
    TelemetryContext,
    TraceOutcome,
    TraceRecord,
)


NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
CORRELATION_ID = UUID("00000000-0000-0000-0000-000000001601")
CAUSATION_ID = UUID("00000000-0000-0000-0000-000000002601")
JOB_ID = UUID("00000000-0000-0000-0000-000000003601")
ARTICLE_ID = UUID("00000000-0000-0000-0000-000000004601")
SNAPSHOT_ID = UUID("00000000-0000-0000-0000-000000005601")
PROVIDER_REQUEST_ID = "request-1601.example"


def make_context() -> TelemetryContext:
    return TelemetryContext(
        correlation_id=CORRELATION_ID,
        causation_id=CAUSATION_ID,
        job_id=JOB_ID,
        article_id=ARTICLE_ID,
        snapshot_id=SNAPSHOT_ID,
        provider_request_id=PROVIDER_REQUEST_ID,
    )


def make_trace() -> TraceRecord:
    return TraceRecord(
        context=make_context(),
        observed_at=NOW,
        name="worker.execute",
        outcome=TraceOutcome.SUCCEEDED,
        duration_ms=12,
    )


def make_metric() -> MetricRecord:
    return MetricRecord(
        context=make_context(),
        observed_at=NOW,
        name="queue.depth",
        value=3,
        unit=MetricUnit.COUNT,
    )


def make_log() -> LogRecord:
    return LogRecord(
        context=make_context(),
        observed_at=NOW,
        name="worker.completed",
        level=LogLevel.INFO,
    )

"""Domain and sink behavior for the maximum-safe ST-1601 seam."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
import inspect
import math
import pickle
from typing import Any, cast
from uuid import UUID

import pytest

from .support import (
    ARTICLE_ID,
    CAUSATION_ID,
    CORRELATION_ID,
    JOB_ID,
    NOW,
    PROVIDER_REQUEST_ID,
    SNAPSHOT_ID,
    make_context,
    make_log,
    make_metric,
    make_trace,
)
from raos.adapters.recorded_telemetry import (
    DisabledTelemetrySink,
    RecordedTelemetrySink,
)
from raos.application.ops.telemetry import TelemetryRecorder
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ops.telemetry import (
    LogRecord,
    LogLevel,
    MetricRecord,
    MetricUnit,
    TelemetryContext,
    TelemetryFailure,
    TelemetryFailureCode,
    TelemetryOutcome,
    TelemetrySignal,
    TraceRecord,
    TraceOutcome,
)


class _StringSubclass(str):
    pass


class _IntegerSubclass(int):
    pass


class _UuidSubclass(UUID):
    pass


class _DatetimeSubclass(datetime):
    pass


def _assert_invalid(operation: Any) -> TelemetryFailure:
    with pytest.raises(TelemetryFailure) as captured:
        operation()
    failure = captured.value
    assert failure.code is TelemetryFailureCode.INVALID_ARGUMENT
    assert failure.__cause__ is None
    return failure


def test_context_round_trips_all_six_explicit_identifiers() -> None:
    context = make_context()

    assert context.correlation_id is CORRELATION_ID
    assert context.causation_id is CAUSATION_ID
    assert context.job_id is JOB_ID
    assert context.article_id is ARTICLE_ID
    assert context.snapshot_id is SNAPSHOT_ID
    assert context.provider_request_id == PROVIDER_REQUEST_ID


def test_exact_signal_records_are_closed_and_deterministic() -> None:
    trace = make_trace()
    metric = make_metric()
    event = make_log()

    assert trace.signal is TelemetrySignal.TRACE
    assert trace.observed_at is NOW
    assert trace.name == "worker.execute"
    assert trace.outcome is TraceOutcome.SUCCEEDED
    assert trace.duration_ms == 12
    assert metric.signal is TelemetrySignal.METRIC
    assert metric.value == 3.0
    assert metric.unit is MetricUnit.COUNT
    assert event.signal is TelemetrySignal.LOG
    assert event.level is LogLevel.INFO


def test_exact_enum_sets_are_closed() -> None:
    assert {item.value for item in TelemetrySignal} == {"TRACE", "METRIC", "LOG"}
    assert {item.value for item in TelemetryOutcome} == {
        "RECORDED",
        "DISABLED",
        "DROPPED",
        "SINK_FAILED",
    }
    assert {item.value for item in TraceOutcome} == {
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
    }
    assert {item.value for item in MetricUnit} == {
        "COUNT",
        "MILLISECONDS",
        "BYTES",
    }
    assert {item.value for item in LogLevel} == {"INFO", "WARNING", "ERROR"}


@pytest.mark.parametrize(
    "correlation_id",
    [
        None,
        str(CORRELATION_ID),
        _UuidSubclass(str(CORRELATION_ID)),
    ],
)
def test_correlation_id_requires_one_exact_caller_supplied_uuid(
    correlation_id: object,
) -> None:
    _assert_invalid(lambda: TelemetryContext(correlation_id=cast(UUID, correlation_id)))


@pytest.mark.parametrize(
    "field",
    ["causation_id", "job_id", "article_id", "snapshot_id"],
)
@pytest.mark.parametrize("value", ["not-a-uuid", 1, False])
def test_optional_context_uuid_fields_reject_coercion(
    field: str, value: object
) -> None:
    arguments: dict[str, object] = {
        "correlation_id": CORRELATION_ID,
        field: value,
    }
    _assert_invalid(lambda: cast(Any, TelemetryContext)(**arguments))


@pytest.mark.parametrize(
    "provider_request_id",
    [
        "",
        " leading",
        "trailing ",
        "two words",
        "line\nbreak",
        "tab\tvalue",
        "control\x00value",
        "x" * 129,
        _StringSubclass("request-1601"),
    ],
)
def test_provider_request_id_is_an_exact_bounded_safe_token(
    provider_request_id: object,
) -> None:
    _assert_invalid(
        lambda: TelemetryContext(
            correlation_id=CORRELATION_ID,
            provider_request_id=cast(str, provider_request_id),
        )
    )


def test_provider_request_id_accepts_the_exact_128_character_boundary() -> None:
    value = "r" * 128
    context = TelemetryContext(
        correlation_id=CORRELATION_ID,
        provider_request_id=value,
    )
    assert context.provider_request_id == value


@pytest.mark.parametrize(
    "observed_at",
    [
        datetime(2026, 8, 10, 12, 0),
        datetime(2026, 8, 10, 12, 0, tzinfo=timezone(timedelta(hours=9))),
        NOW.replace(fold=1),
        _DatetimeSubclass(2026, 8, 10, 12, 0, tzinfo=UTC),
    ],
)
def test_timestamp_requires_exact_canonical_utc(observed_at: datetime) -> None:
    _assert_invalid(
        lambda: TraceRecord(
            context=make_context(),
            observed_at=observed_at,
            name="worker.execute",
            outcome=TraceOutcome.SUCCEEDED,
            duration_ms=1,
        )
    )


@pytest.mark.parametrize(
    "name",
    [
        "",
        "Uppercase",
        " leading",
        "trailing ",
        "two words",
        "line\nbreak",
        "x" * 65,
        _StringSubclass("worker.execute"),
    ],
)
def test_signal_name_is_exact_bounded_and_control_free(name: object) -> None:
    _assert_invalid(
        lambda: LogRecord(
            context=make_context(),
            observed_at=NOW,
            name=cast(str, name),
            level=LogLevel.INFO,
        )
    )


@pytest.mark.parametrize("duration_ms", [False, -1, 86_400_001, 1.0])
def test_trace_duration_rejects_bool_negative_oversized_and_non_int(
    duration_ms: object,
) -> None:
    _assert_invalid(
        lambda: TraceRecord(
            context=make_context(),
            observed_at=NOW,
            name="worker.execute",
            outcome=TraceOutcome.SUCCEEDED,
            duration_ms=cast(int, duration_ms),
        )
    )


@pytest.mark.parametrize(
    "value",
    [False, -1, -0.1, math.nan, math.inf, -math.inf, 1.0e16, 10**1000, "1"],
)
def test_metric_rejects_bool_negative_nonfinite_oversized_and_non_number(
    value: object,
) -> None:
    _assert_invalid(
        lambda: MetricRecord(
            context=make_context(),
            observed_at=NOW,
            name="queue.depth",
            value=cast(Any, value),
            unit=MetricUnit.COUNT,
        )
    )


def test_numeric_subclasses_and_raw_enum_values_fail_closed() -> None:
    _assert_invalid(
        lambda: TraceRecord(
            context=make_context(),
            observed_at=NOW,
            name="worker.execute",
            outcome=cast(TraceOutcome, "SUCCEEDED"),
            duration_ms=1,
        )
    )
    _assert_invalid(
        lambda: MetricRecord(
            context=make_context(),
            observed_at=NOW,
            name="queue.depth",
            value=_IntegerSubclass(1),
            unit=MetricUnit.COUNT,
        )
    )
    _assert_invalid(
        lambda: LogRecord(
            context=make_context(),
            observed_at=NOW,
            name="worker.completed",
            level=cast(LogLevel, "INFO"),
        )
    )


def test_signal_specific_constructor_fields_cannot_bleed() -> None:
    assert set(inspect.signature(TraceRecord).parameters) == {
        "context",
        "observed_at",
        "name",
        "outcome",
        "duration_ms",
    }
    assert set(inspect.signature(MetricRecord).parameters) == {
        "context",
        "observed_at",
        "name",
        "value",
        "unit",
    }
    assert set(inspect.signature(LogRecord).parameters) == {
        "context",
        "observed_at",
        "name",
        "level",
    }
    with pytest.raises(TypeError):
        cast(Any, TraceRecord)(
            context=make_context(),
            observed_at=NOW,
            name="worker.execute",
            outcome=TraceOutcome.SUCCEEDED,
            duration_ms=1,
            unit=MetricUnit.COUNT,
        )
    with pytest.raises(TypeError):
        cast(Any, MetricRecord)(
            context=make_context(),
            observed_at=NOW,
            name="queue.depth",
            value=1,
            unit=MetricUnit.COUNT,
            level=LogLevel.INFO,
        )
    with pytest.raises(TypeError):
        cast(Any, LogRecord)(
            context=make_context(),
            observed_at=NOW,
            name="worker.completed",
            level=LogLevel.INFO,
            duration_ms=1,
        )


def test_context_records_failures_and_nonempty_snapshots_are_redacted_immutable_and_not_pickleable() -> (
    None
):
    canary = "LeakCanary1601"
    context = TelemetryContext(
        correlation_id=CORRELATION_ID,
        provider_request_id=canary,
    )
    record = LogRecord(
        context=context,
        observed_at=NOW,
        name="worker.completed",
        level=LogLevel.ERROR,
    )
    sink = RecordedTelemetrySink(environment=RuntimeEnvironment.CI, capacity=1)
    assert sink.emit(record) is TelemetryOutcome.RECORDED
    snapshot = sink.snapshot()

    for value in (context, record, snapshot):
        assert canary not in repr(value)
        assert canary not in str(value)
        with pytest.raises(TypeError) as captured:
            pickle.dumps(value)
        assert canary not in str(captured.value)
        assert canary not in repr(captured.value)
        assert canary not in repr(captured.value.args)
        assert captured.value.__cause__ is None

    with pytest.raises(AttributeError):
        context.correlation_id = UUID(int=0)  # type: ignore[misc]
    with pytest.raises(AttributeError):
        record.name = "changed"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        cast(Any, snapshot).append(record)

    failure = _assert_invalid(
        lambda: TelemetryContext(
            correlation_id=CORRELATION_ID,
            provider_request_id=f"{canary} invalid",
        )
    )
    assert canary not in str(failure)
    assert canary not in repr(failure)
    assert canary not in repr(failure.args)
    assert failure.__cause__ is None
    assert failure.__context__ is None
    with pytest.raises(TypeError) as pickle_failure:
        pickle.dumps(failure)
    assert canary not in str(pickle_failure.value)


def test_disabled_and_recorded_sinks_return_separate_exact_outcomes() -> None:
    trace = make_trace()
    disabled = TelemetryRecorder(sink=DisabledTelemetrySink())
    recorded_sink = RecordedTelemetrySink(
        environment=RuntimeEnvironment.ENV_DEV,
        capacity=1,
    )
    recorded = TelemetryRecorder(sink=recorded_sink)

    assert disabled.record(trace) is TelemetryOutcome.DISABLED
    assert recorded.record(trace) is TelemetryOutcome.RECORDED
    assert recorded.record(make_metric()) is TelemetryOutcome.DROPPED
    assert recorded_sink.snapshot() == (trace,)
    assert recorded_sink.drop_count == 1


def test_drop_newest_preserves_existing_order_and_content() -> None:
    first = make_trace()
    second = make_metric()
    third = make_log()
    sink = RecordedTelemetrySink(environment=RuntimeEnvironment.CI, capacity=2)

    assert sink.emit(first) is TelemetryOutcome.RECORDED
    assert sink.emit(second) is TelemetryOutcome.RECORDED
    before = sink.snapshot()
    assert before == (first, second)
    assert sink.emit(third) is TelemetryOutcome.DROPPED
    assert sink.emit(third) is TelemetryOutcome.DROPPED
    assert sink.snapshot() is before
    assert sink.snapshot() == (first, second)
    assert sink.drop_count == 2


@pytest.mark.parametrize(
    "environment", [RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI]
)
def test_recorded_sink_allows_only_exact_development_and_ci(
    environment: RuntimeEnvironment,
) -> None:
    sink = RecordedTelemetrySink(environment=environment, capacity=1)
    assert sink.environment is environment
    assert sink.capacity == 1


@pytest.mark.parametrize(
    "environment",
    [
        RuntimeEnvironment.INTEGRATION,
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.RECOVERY,
        RuntimeEnvironment.PRODUCTION,
        "ENV-DEV",
        _StringSubclass("ENV-CI"),
    ],
)
def test_recorded_sink_rejects_all_other_and_impersonated_environments(
    environment: object,
) -> None:
    _assert_invalid(
        lambda: RecordedTelemetrySink(
            environment=cast(RuntimeEnvironment, environment), capacity=1
        )
    )


@pytest.mark.parametrize("capacity", [False, 0, -1, 1.0, "1", 10_001])
def test_recorded_sink_requires_explicit_positive_bounded_builtin_int(
    capacity: object,
) -> None:
    _assert_invalid(
        lambda: RecordedTelemetrySink(
            environment=RuntimeEnvironment.ENV_DEV,
            capacity=cast(int, capacity),
        )
    )


def test_recorded_sink_has_no_default_capacity() -> None:
    with pytest.raises(TypeError):
        cast(Any, RecordedTelemetrySink)(environment=RuntimeEnvironment.ENV_DEV)

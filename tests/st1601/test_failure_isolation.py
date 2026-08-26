"""Failure containment and predecessor invariants for ST-1601."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import timedelta
import gc
import json
from typing import Any, NoReturn, SupportsIndex, cast
from uuid import UUID
import weakref

import pytest

from .support import (
    CORRELATION_ID,
    NOW,
    REPOSITORY_ROOT,
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
from raos.domain.ops.job_runtime import (
    DispatchOutcome,
    Fingerprint,
    JobRecord,
    JobState,
    RecordedJobMessage,
    WorkOutcome,
    WorkStepResult,
)
from raos.domain.ops.telemetry import TelemetryOutcome, TelemetryRecord


class _ExplodingFailure(Exception):
    __slots__ = ("__weakref__",)

    def __repr__(self) -> str:
        raise AssertionError("exception repr must not be called")

    def __str__(self) -> str:
        raise AssertionError("exception str must not be called")

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise AssertionError("exception serialization must not be called")


class _ExplodingSink:
    def __init__(self) -> None:
        self.calls = 0
        self.failure_ref: weakref.ReferenceType[_ExplodingFailure] | None = None

    def emit(self, record: TelemetryRecord) -> TelemetryOutcome:
        del record
        self.calls += 1
        failure = _ExplodingFailure("SensitiveCanary1601")
        self.failure_ref = weakref.ref(failure)
        raise failure


class _MalformedSink:
    def __init__(self, value: object) -> None:
        self.value = value
        self.calls = 0

    def emit(self, record: TelemetryRecord) -> Any:
        del record
        self.calls += 1
        return self.value


class _BaseFailureSink:
    def __init__(self, failure: BaseException) -> None:
        self.failure = failure
        self.calls = 0

    def emit(self, record: TelemetryRecord) -> TelemetryOutcome:
        del record
        self.calls += 1
        raise self.failure


class _FixedOutcomeSink:
    def __init__(self, outcome: TelemetryOutcome) -> None:
        self.outcome = outcome
        self.calls = 0

    def emit(self, record: TelemetryRecord) -> TelemetryOutcome:
        del record
        self.calls += 1
        return self.outcome


@dataclass(frozen=True, slots=True)
class _BusinessObservation:
    job: JobRecord
    result: WorkStepResult
    acknowledged: bool
    retry_at: None
    health: str


def _business_observation() -> _BusinessObservation:
    job = JobRecord(
        job_id=UUID("00000000-0000-0000-0000-000000001404"),
        state=JobState.QUEUED,
        queue_name="recorded-jobs",
        payload_fingerprint=Fingerprint("a" * 64),
        created_at=NOW - timedelta(minutes=1),
        available_at=NOW,
        job_schema_version=1,
        version=1,
        max_attempts=3,
        delivery_max_attempts=4,
    )
    result = WorkStepResult(
        outcome=WorkOutcome.ACK_FAILED,
        job_id=job.job_id,
        job_state=job.state,
        expected_job_version=job.version,
        post_job_version=job.version,
    )
    return _BusinessObservation(
        job=job,
        result=result,
        acknowledged=False,
        retry_at=None,
        health="DEGRADED",
    )


def test_ordinary_sink_failure_is_sanitized_once_without_retention_or_retry() -> None:
    sink = _ExplodingSink()
    recorder = TelemetryRecorder(sink=sink)

    outcome = recorder.record(make_log())

    assert outcome is TelemetryOutcome.SINK_FAILED
    assert sink.calls == 1
    assert "SensitiveCanary1601" not in repr(outcome)
    failure_ref = sink.failure_ref
    assert failure_ref is not None
    gc.collect()
    assert failure_ref() is None


@pytest.mark.parametrize(
    "malformed",
    [None, "RECORDED", 1, False, object(), RuntimeEnvironment.ENV_DEV],
)
def test_malformed_sink_returns_fail_closed_without_echo_or_retry(
    malformed: object,
) -> None:
    sink = _MalformedSink(malformed)
    outcome = TelemetryRecorder(sink=cast(Any, sink)).record(make_trace())
    assert outcome is TelemetryOutcome.SINK_FAILED
    assert sink.calls == 1


@pytest.mark.parametrize("failure", [KeyboardInterrupt(), SystemExit(7)])
def test_base_exception_subclasses_propagate(failure: BaseException) -> None:
    sink = _BaseFailureSink(failure)
    with pytest.raises(type(failure)) as captured:
        TelemetryRecorder(sink=sink).record(make_trace())
    assert captured.value is failure
    assert sink.calls == 1


def test_disabled_sink_retains_no_instance_state() -> None:
    sink = DisabledTelemetrySink()
    recorder = TelemetryRecorder(sink=sink)
    assert recorder.record(make_trace()) is TelemetryOutcome.DISABLED
    assert recorder.record(make_metric()) is TelemetryOutcome.DISABLED
    assert not hasattr(sink, "__dict__")
    assert sink.__slots__ == ()


def test_telemetry_outcome_never_changes_job_result_ack_retry_or_health() -> None:
    baseline = _business_observation()
    full = RecordedTelemetrySink(environment=RuntimeEnvironment.CI, capacity=1)
    assert full.emit(make_trace()) is TelemetryOutcome.RECORDED
    recorders = (
        (
            TelemetryRecorder(sink=_FixedOutcomeSink(TelemetryOutcome.RECORDED)),
            TelemetryOutcome.RECORDED,
        ),
        (TelemetryRecorder(sink=DisabledTelemetrySink()), TelemetryOutcome.DISABLED),
        (TelemetryRecorder(sink=full), TelemetryOutcome.DROPPED),
        (TelemetryRecorder(sink=_ExplodingSink()), TelemetryOutcome.SINK_FAILED),
    )

    for recorder, expected in recorders:
        before = baseline
        outcome = recorder.record(make_log())
        after = baseline
        assert outcome is expected
        assert after is before
        assert after.job is before.job
        assert after.job.state is JobState.QUEUED
        assert after.result.outcome is WorkOutcome.ACK_FAILED
        assert after.acknowledged is False
        assert after.retry_at is None
        assert after.health == "DEGRADED"


def test_committed_st1404_public_job_semantics_are_exact_and_have_no_correlation_fields() -> (
    None
):
    assert {state.value for state in JobState} == {
        "REQUESTED",
        "QUEUED",
        "RUNNING",
        "SUCCEEDED",
        "FAILED_RETRYABLE",
        "RETRY_SCHEDULED",
        "FAILED_TERMINAL",
        "QUARANTINED",
        "CANCELLED",
        "EXPIRED",
    }
    assert {outcome.value for outcome in DispatchOutcome} == {
        "NO_WORK",
        "PUBLISHED",
        "SEND_RETRY_SCHEDULED",
        "OUTBOX_DEAD",
    }
    assert {outcome.value for outcome in WorkOutcome} == {
        "NO_DELIVERY",
        "RECEIVE_FAILED",
        "MALFORMED_DELIVERY_RELEASED",
        "LEASE_STALE",
        "NOT_READY_HELD",
        "PROCESSING_HELD",
        "RETRY_STATE_HELD",
        "DUPLICATE_ACKNOWLEDGED",
        "SUCCEEDED",
        "RETRY_SCHEDULED",
        "FAILED_TERMINAL",
        "CANCELLED",
        "EXPIRED",
        "ACK_FAILED",
        "RETRY_RELEASE_FAILED",
    }
    job_fields = {field.name for field in fields(JobRecord)}
    message_fields = {field.name for field in fields(RecordedJobMessage)}
    assert job_fields == {
        "job_id",
        "state",
        "queue_name",
        "payload_fingerprint",
        "created_at",
        "available_at",
        "job_schema_version",
        "version",
        "max_attempts",
        "delivery_max_attempts",
        "attempt_count",
        "deadline_at",
        "cancel_requested_at",
        "completed_at",
        "lease",
        "result_fingerprint",
        "failure_code",
    }
    assert {"correlation_id", "causation_id"}.isdisjoint(job_fields)
    assert {"correlation_id", "causation_id"}.isdisjoint(message_fields)
    assert make_trace().context.correlation_id is CORRELATION_ID


def test_committed_st1505_remains_disabled_zero_action_and_not_executed() -> None:
    path = REPOSITORY_ROOT / (
        "infra/terraform/staging/staging-deployment.reference-plan.v1.json"
    )
    plan = json.loads(path.read_text(encoding="utf-8"))

    assert plan["document"]["story_id"] == "ST-1505"
    assert plan["document"]["executable"] is False
    assert plan["activation"]["enabled"] is False
    assert plan["activation"]["status"] == "DISABLED"
    assert plan["activation"]["runtime_status"] == "NOT_EXECUTED"
    assert plan["activation"]["network_access"] == "FORBIDDEN"
    assert plan["activation"]["external_writes"] == "FORBIDDEN"
    assert plan["activation"]["live_provider_calls"] == "FORBIDDEN"
    assert set(plan["activation"]["operations"].values()) == {"FORBIDDEN"}
    assert set(plan["action_counts"].values()) == {0}
    assert all(
        value is None or value == [] for value in plan["selected_bindings"].values()
    )
    verification = plan["verification_boundary"]
    assert verification["formal_tst_009"] == "NOT_EXECUTED"
    assert verification["formal_tst_022"] == "NOT_EXECUTED"
    assert verification["staging"] == "NOT_EXECUTED"
    assert verification["production"] == "NOT_EXECUTED"
    assert verification["effective_canonical_status"] == "UNCHANGED"

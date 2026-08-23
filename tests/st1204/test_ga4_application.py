"""One-call and failure-isolation tests for the recorded GA4 application."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import cast

import pytest

from scripts import build_st1204_ga4_recorded_adapter as generator

from raos.adapters.recorded_ga4 import RecordedGa4Adapter
from raos.application.analytics.ga4_import import RecordedGa4Import
from raos.domain.analytics.ga4 import (
    EXACT_DIMENSIONS,
    EXACT_METRICS,
    SYNTHETIC_PROPERTY_ID,
    SYNTHETIC_SITE_ID,
    Ga4BoundaryStatus,
    Ga4DateRange,
    Ga4Failure,
    Ga4FailureCode,
    Ga4RecordedExchange,
    Ga4RecordedImportCommand,
    Ga4RecordedOutcome,
    Ga4RecordedRequest,
    Ga4RecordingId,
    fixture_binding,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _command(recording_id: str) -> Ga4RecordedImportCommand:
    binding = fixture_binding(Ga4RecordingId(recording_id))
    request = Ga4RecordedRequest(
        property_id=SYNTHETIC_PROPERTY_ID,
        date_ranges=(Ga4DateRange(date(2026, 7, 1), date(2026, 7, 2), None),),
        dimensions=EXACT_DIMENSIONS,
        metrics=EXACT_METRICS,
        dimension_filter=None,
        metric_filter=None,
        order_bys=(),
        limit=2,
        offset=0,
        keep_empty_rows=False,
        return_property_quota=True,
    )
    return Ga4RecordedImportCommand(
        recording_id=binding.recording_id,
        fixture_digest=binding.fixture_digest,
        fixture_length=binding.fixture_length,
        site_id=SYNTHETIC_SITE_ID,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 2),
        dimensions=EXACT_DIMENSIONS,
        metrics=EXACT_METRICS,
        force_reimport=None,
        request=request,
    )


def _exchange(recording_id: str) -> Ga4RecordedExchange:
    command = _command(recording_id)
    raw = (
        REPOSITORY_ROOT / generator.FIXTURE_ROOT / f"{recording_id}.json"
    ).read_bytes()
    return RecordedGa4Adapter(command=command, fixture_bytes=raw).read(
        recording_id=command.recording_id,
        request=command.request,
    )


class _Port:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.calls: list[tuple[Ga4RecordingId, Ga4RecordedRequest]] = []

    def read(
        self,
        *,
        recording_id: Ga4RecordingId,
        request: Ga4RecordedRequest,
    ) -> Ga4RecordedExchange:
        self.calls.append((recording_id, request))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return cast(Ga4RecordedExchange, self.outcome)


@pytest.mark.parametrize(
    "recording_id", ["baseline", "late-revised", "provider-error-429"]
)
def test_application_calls_port_once_and_keeps_all_markers_closed(
    recording_id: str,
) -> None:
    command = _command(recording_id)
    port = _Port(_exchange(recording_id))

    result = RecordedGa4Import(port=port).import_recording(command)

    assert port.calls == [(command.recording_id, command.request)]
    assert result.execution_mode is Ga4BoundaryStatus.RECORDED_FIXTURE_ONLY
    assert result.tracking is Ga4BoundaryStatus.DISABLED_OD_012
    assert result.credentials is Ga4BoundaryStatus.NOT_USED
    assert result.provider_execution is Ga4BoundaryStatus.NOT_EXECUTED
    assert result.persistence is Ga4BoundaryStatus.NOT_EXECUTED
    assert result.job_dispatch is Ga4BoundaryStatus.NOT_EXECUTED
    assert result.event_publication is Ga4BoundaryStatus.NOT_EXECUTED
    assert result.supersession is Ga4BoundaryStatus.NOT_DEFINED
    assert result.formal_tst_030 is Ga4BoundaryStatus.NOT_EXECUTED
    assert result.decision is Ga4BoundaryStatus.NOT_READY


def test_revisions_remain_independent_without_current_or_supersession_claim() -> None:
    baseline_command = _command("baseline")
    revised_command = _command("late-revised")
    baseline = RecordedGa4Import(port=_Port(_exchange("baseline"))).import_recording(
        baseline_command
    )
    revised = RecordedGa4Import(port=_Port(_exchange("late-revised"))).import_recording(
        revised_command
    )
    assert baseline.exchange.rows[0].metric_values == ("12", "20", "8")
    assert revised.exchange.rows[0].metric_values == ("14", "23", "10")
    assert baseline.supersession is Ga4BoundaryStatus.NOT_DEFINED
    assert revised.supersession is Ga4BoundaryStatus.NOT_DEFINED


@pytest.mark.parametrize("outcome", [None, object(), RuntimeError("secret-canary")])
def test_port_failure_is_sanitized_after_exactly_one_call(outcome: object) -> None:
    command = _command("baseline")
    port = _Port(outcome)
    with pytest.raises(Ga4Failure) as caught:
        RecordedGa4Import(port=port).import_recording(command)
    assert len(port.calls) == 1
    assert caught.value.code in {
        Ga4FailureCode.RECORDED_EXCHANGE_UNAVAILABLE,
        Ga4FailureCode.RECORDED_RESULT_MISMATCH,
    }
    assert "secret-canary" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_invalid_command_stops_before_port() -> None:
    port = _Port(_exchange("baseline"))
    with pytest.raises(Ga4Failure):
        RecordedGa4Import(port=port).import_recording(object())  # type: ignore[arg-type]
    assert port.calls == []


def test_foreign_recorded_exchange_is_rejected() -> None:
    port = _Port(_exchange("late-revised"))
    with pytest.raises(Ga4Failure) as caught:
        RecordedGa4Import(port=port).import_recording(_command("baseline"))
    assert len(port.calls) == 1
    assert caught.value.code is Ga4FailureCode.RECORDED_RESULT_MISMATCH


def test_recorded_429_is_result_not_retry_or_provider_execution() -> None:
    command = _command("provider-error-429")
    result = RecordedGa4Import(
        port=_Port(_exchange("provider-error-429"))
    ).import_recording(command)
    assert result.exchange.outcome is Ga4RecordedOutcome.RECORDED_RESOURCE_EXHAUSTED
    assert result.exchange.rows == ()
    assert result.property_configuration is Ga4BoundaryStatus.NOT_CAPTURED_AFTER_ERROR
    assert result.provider_execution is Ga4BoundaryStatus.NOT_EXECUTED

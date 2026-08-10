"""Application validation and failure-isolation tests for ST-1203."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import cast

import pytest

from raos.adapters.recorded_search_console import RecordedSearchConsoleFixtureExchange
from raos.application.analytics.search_console_import import (
    SearchConsoleRecordedImport,
    compare_recorded_imports,
)
from raos.domain.analytics.search_console import (
    EXACT_DIMENSIONS,
    AggregationType,
    DataState,
    RecordedMetricsComparison,
    RecordedSearchConsolePage,
    RecordingId,
    SearchConsoleBoundaryStatus,
    SearchConsoleCommand,
    SearchConsoleFailure,
    SearchConsoleFailureCode,
    SearchConsoleRequest,
    SearchType,
    binding_for,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _command(recording_id: str) -> SearchConsoleCommand:
    binding = binding_for(RecordingId(recording_id))
    request = SearchConsoleRequest(
        site_url="sc-domain:example.invalid",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
        dimensions=EXACT_DIMENSIONS,
        search_type=SearchType.WEB,
        aggregation_type=AggregationType.AUTO,
        data_state=DataState.FINAL,
        row_limit=binding.row_limit,
        start_row=binding.start_row,
        dimension_filter_groups=(),
    )
    return SearchConsoleCommand(
        recording_id=binding.recording_id,
        fixture_digest=binding.fixture_digest,
        fixture_length=binding.fixture_length,
        request=request,
    )


def _page(recording_id: str) -> RecordedSearchConsolePage:
    command = _command(recording_id)
    raw = (
        REPOSITORY_ROOT / "changes/st-1203/fixtures/recorded" / f"{recording_id}.json"
    ).read_bytes()
    return RecordedSearchConsoleFixtureExchange(
        command=command, fixture_bytes=raw
    ).exchange(command)


class _Exchange:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.calls: list[SearchConsoleCommand] = []

    def exchange(self, command: SearchConsoleCommand) -> RecordedSearchConsolePage:
        self.calls.append(command)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return cast(RecordedSearchConsolePage, self.outcome)


@pytest.mark.parametrize(
    "recording_id", ["baseline", "late-revised", "start-beyond-data"]
)
def test_application_calls_exchange_once_and_keeps_all_boundaries_closed(
    recording_id: str,
) -> None:
    command = _command(recording_id)
    exchange = _Exchange(_page(recording_id))

    result = SearchConsoleRecordedImport(exchange=exchange).import_recording(command)

    assert exchange.calls == [command]
    assert result.execution is SearchConsoleBoundaryStatus.RECORDED_FIXTURE_ONLY
    assert result.provider is SearchConsoleBoundaryStatus.NOT_EXECUTED
    assert result.credentials is SearchConsoleBoundaryStatus.NOT_USED
    assert result.import_run is SearchConsoleBoundaryStatus.NOT_CREATED
    assert result.persistence is SearchConsoleBoundaryStatus.NOT_EXECUTED
    assert result.supersession is SearchConsoleBoundaryStatus.NOT_DEFINED
    assert result.audit is SearchConsoleBoundaryStatus.NOT_EXECUTED
    assert result.outbox is SearchConsoleBoundaryStatus.NOT_EXECUTED
    assert result.formal_tst_030 is SearchConsoleBoundaryStatus.NOT_EXECUTED
    assert result.decision is SearchConsoleBoundaryStatus.NOT_READY


def test_comparison_reports_difference_without_supersession() -> None:
    baseline_command = _command("baseline")
    revised_command = _command("late-revised")
    baseline = SearchConsoleRecordedImport(
        exchange=_Exchange(_page("baseline"))
    ).import_recording(baseline_command)
    revised = SearchConsoleRecordedImport(
        exchange=_Exchange(_page("late-revised"))
    ).import_recording(revised_command)

    comparison = compare_recorded_imports(baseline, revised)

    assert comparison.comparison is RecordedMetricsComparison.RECORDED_METRICS_DIFFER
    assert comparison.supersession is SearchConsoleBoundaryStatus.NOT_DEFINED


@pytest.mark.parametrize("outcome", [None, object(), RuntimeError("secret-canary")])
def test_collaborator_failure_is_sanitized(outcome: object) -> None:
    command = _command("baseline")
    exchange = _Exchange(outcome)

    with pytest.raises(SearchConsoleFailure) as caught:
        SearchConsoleRecordedImport(exchange=exchange).import_recording(command)

    assert len(exchange.calls) == 1
    assert caught.value.code in {
        SearchConsoleFailureCode.RECORDED_EXCHANGE_UNAVAILABLE,
        SearchConsoleFailureCode.RECORDED_RESULT_MISMATCH,
    }
    assert "secret-canary" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_invalid_command_stops_before_exchange() -> None:
    exchange = _Exchange(_page("baseline"))
    with pytest.raises(SearchConsoleFailure):
        SearchConsoleRecordedImport(exchange=exchange).import_recording(object())  # type: ignore[arg-type]
    assert exchange.calls == []


def test_foreign_page_is_rejected_after_one_call() -> None:
    exchange = _Exchange(_page("late-revised"))
    with pytest.raises(SearchConsoleFailure) as caught:
        SearchConsoleRecordedImport(exchange=exchange).import_recording(
            _command("baseline")
        )
    assert len(exchange.calls) == 1
    assert caught.value.code is SearchConsoleFailureCode.RECORDED_RESULT_MISMATCH

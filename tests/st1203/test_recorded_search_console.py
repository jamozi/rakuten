"""Focused recorded-fixture behavior for the ST-1203 runtime seam."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from raos.adapters.recorded_search_console import RecordedSearchConsoleFixtureExchange
from raos.application.analytics.search_console_import import SearchConsoleRecordedImport
from raos.domain.analytics.search_console import (
    EXACT_DIMENSIONS,
    AggregationType,
    DataState,
    RecordingId,
    SearchConsoleBoundaryStatus,
    SearchConsoleCommand,
    SearchConsoleFailure,
    SearchConsoleFailureCode,
    SearchConsoleRequest,
    SearchType,
    EmptyPageMeaning,
    FixtureByteLength,
    Sha256Digest,
    binding_for,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _command(recording_id: str = "baseline") -> SearchConsoleCommand:
    recording = RecordingId(recording_id)
    binding = binding_for(recording)
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
        recording_id=recording,
        fixture_digest=binding.fixture_digest,
        fixture_length=binding.fixture_length,
        request=request,
    )


def _fixture_bytes(recording_id: str) -> bytes:
    return (
        REPOSITORY_ROOT / "changes/st-1203/fixtures/recorded" / f"{recording_id}.json"
    ).read_bytes()


def test_baseline_fixture_import_is_recorded_only() -> None:
    command = _command()
    exchange = RecordedSearchConsoleFixtureExchange(
        command=command,
        fixture_bytes=_fixture_bytes("baseline"),
    )

    result = SearchConsoleRecordedImport(exchange=exchange).import_recording(command)

    assert result.execution is SearchConsoleBoundaryStatus.RECORDED_FIXTURE_ONLY
    assert result.provider is SearchConsoleBoundaryStatus.NOT_EXECUTED
    assert result.persistence is SearchConsoleBoundaryStatus.NOT_EXECUTED
    assert result.decision is SearchConsoleBoundaryStatus.NOT_READY
    assert len(result.page.rows) == 2


def test_fixture_digest_mismatch_fails_before_parsing() -> None:
    command = _command()

    with pytest.raises(SearchConsoleFailure) as caught:
        RecordedSearchConsoleFixtureExchange(
            command=command,
            fixture_bytes=_fixture_bytes("baseline")[:-1] + b"!",
        )

    assert caught.value.code is SearchConsoleFailureCode.FIXTURE_BYTES_MISMATCH


@pytest.mark.parametrize(
    ("recording_id", "row_count"),
    [("baseline", 2), ("late-revised", 2), ("start-beyond-data", 0)],
)
def test_exact_fixture_bytes_parse_to_bound_page(
    recording_id: str,
    row_count: int,
) -> None:
    command = _command(recording_id)
    page = RecordedSearchConsoleFixtureExchange(
        command=command,
        fixture_bytes=_fixture_bytes(recording_id),
    ).exchange(command)
    assert len(page.rows) == row_count
    assert page.request_digest == command.request.sha256
    assert page.top_rows_only is True
    assert page.rows_not_guaranteed_complete is True
    expected_empty = (
        EmptyPageMeaning.RECORDED_ZERO_ROWS_ONLY if row_count == 0 else None
    )
    assert page.empty_page_meaning is expected_empty


def test_recorded_exchange_is_single_use() -> None:
    command = _command()
    exchange = RecordedSearchConsoleFixtureExchange(
        command=command,
        fixture_bytes=_fixture_bytes("baseline"),
    )
    exchange.exchange(command)
    with pytest.raises(SearchConsoleFailure) as caught:
        exchange.exchange(command)
    assert caught.value.code is SearchConsoleFailureCode.RECORDED_EXCHANGE_EXHAUSTED


def _rebound_command(raw: bytes) -> SearchConsoleCommand:
    command = _command()
    object.__setattr__(command, "fixture_digest", Sha256Digest.of(raw))
    object.__setattr__(command, "fixture_length", FixtureByteLength(len(raw)))
    return command


@pytest.mark.parametrize(
    "mutator",
    [
        lambda raw: raw.replace(
            b'"fixture_version": "1.0.0",',
            b'"fixture_version": "1.0.0", "fixture_version": "1.0.0",',
            1,
        ),
        lambda raw: raw.replace(b'"clicks": 12', b'"clicks": NaN', 1),
        lambda raw: raw.replace(b'"synthetic_marker"', b'"unknown_marker"', 1),
    ],
)
def test_strict_json_rejects_duplicate_nonfinite_and_unknown_fields(
    mutator: object,
) -> None:
    raw = mutator(_fixture_bytes("baseline"))  # type: ignore[operator]
    command = _rebound_command(raw)
    with pytest.raises(SearchConsoleFailure) as caught:
        RecordedSearchConsoleFixtureExchange(command=command, fixture_bytes=raw)
    assert caught.value.code is SearchConsoleFailureCode.FIXTURE_DOCUMENT_INVALID


def test_request_document_drift_is_rejected_without_echo() -> None:
    canary = b"synthetic-secret-canary"
    raw = _fixture_bytes("baseline").replace(b"synthetic luggage", canary, 1)
    command = _rebound_command(raw)
    with pytest.raises(SearchConsoleFailure) as caught:
        RecordedSearchConsoleFixtureExchange(command=command, fixture_bytes=raw)
    assert canary.decode() not in str(caught.value)
    assert caught.value.__cause__ is None

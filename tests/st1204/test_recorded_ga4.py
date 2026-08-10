"""Focused recorded-adapter behavior for the ST-1204 runtime seam."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

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
    Ga4FixtureLength,
    Ga4RecordedImportCommand,
    Ga4RecordedOutcome,
    Ga4RecordedRequest,
    Ga4RecordingId,
    Ga4Sha256,
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


def _bytes(recording_id: str) -> bytes:
    return (
        REPOSITORY_ROOT / "changes/st-1204/fixtures/recorded" / f"{recording_id}.json"
    ).read_bytes()


def test_baseline_preserves_two_rows_and_provider_row_count() -> None:
    command = _command("baseline")
    adapter = RecordedGa4Adapter(
        command=command,
        fixture_bytes=_bytes("baseline"),
    )

    result = RecordedGa4Import(port=adapter).import_recording(command)

    assert result.exchange.outcome is Ga4RecordedOutcome.RECORDED_SUCCESS
    assert len(result.exchange.rows) == 2
    assert result.exchange.provider_row_count == 3
    assert result.property_configuration is Ga4BoundaryStatus.IN_FIXTURE_ONLY
    assert result.provider_execution is Ga4BoundaryStatus.NOT_EXECUTED


def test_recorded_429_has_no_rows_retry_or_configuration() -> None:
    command = _command("provider-error-429")
    adapter = RecordedGa4Adapter(
        command=command,
        fixture_bytes=_bytes("provider-error-429"),
    )

    result = RecordedGa4Import(port=adapter).import_recording(command)

    assert result.exchange.outcome is Ga4RecordedOutcome.RECORDED_RESOURCE_EXHAUSTED
    assert result.exchange.rows == ()
    assert result.exchange.configuration is None
    assert result.exchange.http_status == 429
    assert result.property_configuration is Ga4BoundaryStatus.NOT_CAPTURED_AFTER_ERROR
    assert result.job_dispatch is Ga4BoundaryStatus.NOT_EXECUTED


@pytest.mark.parametrize(
    ("recording_id", "row_count"),
    [("baseline", 2), ("late-revised", 2), ("provider-error-429", 0)],
)
def test_all_exact_fixtures_are_source_bound(recording_id: str, row_count: int) -> None:
    command = _command(recording_id)
    exchange = RecordedGa4Adapter(
        command=command,
        fixture_bytes=_bytes(recording_id),
    ).read(recording_id=command.recording_id, request=command.request)
    assert exchange.fixture_digest == command.fixture_digest
    assert exchange.fixture_length == command.fixture_length
    assert len(exchange.rows) == row_count


def test_whole_fixture_hash_is_checked_before_parsing() -> None:
    command = _command("baseline")
    with pytest.raises(Ga4Failure) as caught:
        RecordedGa4Adapter(
            command=command,
            fixture_bytes=_bytes("baseline")[:-1] + b"!",
        )
    assert caught.value.code is Ga4FailureCode.FIXTURE_BYTES_MISMATCH


def test_adapter_is_single_use_without_replay() -> None:
    command = _command("baseline")
    adapter = RecordedGa4Adapter(command=command, fixture_bytes=_bytes("baseline"))
    adapter.read(recording_id=command.recording_id, request=command.request)
    with pytest.raises(Ga4Failure) as caught:
        adapter.read(recording_id=command.recording_id, request=command.request)
    assert caught.value.code is Ga4FailureCode.RECORDED_EXCHANGE_EXHAUSTED


def _rebound_command(
    raw: bytes, recording_id: str = "baseline"
) -> Ga4RecordedImportCommand:
    command = _command(recording_id)
    object.__setattr__(command, "fixture_digest", Ga4Sha256.of(raw))
    object.__setattr__(command, "fixture_length", Ga4FixtureLength(len(raw)))
    return command


@pytest.mark.parametrize(
    "mutator",
    [
        lambda raw: raw.replace(
            b'"fixture_version": "1.0.0",',
            b'"fixture_version": "1.0.0", "fixture_version": "1.0.0",',
            1,
        ),
        lambda raw: raw.replace(b'"rowCount": 3', b'"rowCount": NaN', 1),
        lambda raw: raw.replace(b'"limit": 2', b'"limit": true', 1),
        lambda raw: raw.replace(b'"fixture_version"', b'"unknown_version"', 1),
        lambda raw: raw.replace(
            b'"metricValues": [', b'"metricValues": [], "ignored": [', 1
        ),
    ],
)
def test_hostile_json_and_shape_drift_fail_closed(mutator: object) -> None:
    raw = mutator(_bytes("baseline"))  # type: ignore[operator]
    with pytest.raises(Ga4Failure):
        RecordedGa4Adapter(command=_rebound_command(raw), fixture_bytes=raw)


def test_recorded_error_message_is_never_exposed_or_retained() -> None:
    canary = b"synthetic-secret-canary"
    raw = _bytes("provider-error-429").replace(
        b"Synthetic quota limit reached.", canary, 1
    )
    with pytest.raises(Ga4Failure) as caught:
        RecordedGa4Adapter(
            command=_rebound_command(raw, "provider-error-429"),
            fixture_bytes=raw,
        )
    assert canary.decode() not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None

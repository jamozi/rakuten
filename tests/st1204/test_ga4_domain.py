"""Closed domain-contract tests for the recorded ST-1204 GA4 seam."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone
import pickle

import pytest

from raos.domain.analytics.ga4 import (
    EXACT_DIMENSIONS,
    EXACT_METRICS,
    FIXTURE_BINDINGS,
    INTERNAL_REQUEST_SHA256,
    SYNTHETIC_PROPERTY_ID,
    SYNTHETIC_SITE_ID,
    WIRE_REQUEST_SHA256,
    Ga4DateRange,
    Ga4Failure,
    Ga4FixtureLength,
    Ga4MetricRow,
    Ga4RecordedImportCommand,
    Ga4RecordedRequest,
    Ga4RecordingId,
    Ga4ReportingIdentity,
    Ga4Sha256,
    Ga4UtcTimestamp,
    fixture_binding,
)


def _request(**overrides: object) -> Ga4RecordedRequest:
    values: dict[str, object] = {
        "property_id": SYNTHETIC_PROPERTY_ID,
        "date_ranges": (Ga4DateRange(date(2026, 7, 1), date(2026, 7, 2), None),),
        "dimensions": EXACT_DIMENSIONS,
        "metrics": EXACT_METRICS,
        "dimension_filter": None,
        "metric_filter": None,
        "order_bys": (),
        "limit": 2,
        "offset": 0,
        "keep_empty_rows": False,
        "return_property_quota": True,
    }
    values.update(overrides)
    return Ga4RecordedRequest(**values)  # type: ignore[arg-type]


def _command(
    recording_id: str = "baseline",
    *,
    force_reimport: bool | None = None,
) -> Ga4RecordedImportCommand:
    binding = fixture_binding(Ga4RecordingId(recording_id))
    return Ga4RecordedImportCommand(
        recording_id=binding.recording_id,
        fixture_digest=binding.fixture_digest,
        fixture_length=binding.fixture_length,
        site_id=SYNTHETIC_SITE_ID,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 2),
        dimensions=EXACT_DIMENSIONS,
        metrics=EXACT_METRICS,
        force_reimport=force_reimport,
        request=_request(),
    )


def _row(**overrides: object) -> Ga4MetricRow:
    values: dict[str, object] = {
        "site_id": SYNTHETIC_SITE_ID,
        "property_id": SYNTHETIC_PROPERTY_ID,
        "date_from": date(2026, 7, 1),
        "date_to": date(2026, 7, 2),
        "date_range_index": 0,
        "dimensions": EXACT_DIMENSIONS,
        "metrics": EXACT_METRICS,
        "dimension_values": (
            "20260701",
            "/synthetic/guide-alpha",
            "mobile",
        ),
        "metric_values": ("12", "20", "8"),
        "imported_at": Ga4UtcTimestamp(
            datetime(2026, 8, 5, 0, 0, 2, tzinfo=timezone.utc)
        ),
        "reporting_identity": Ga4ReportingIdentity.DEVICE_BASED,
        "thresholding_applied": False,
        "source_request_sha256": Ga4Sha256(INTERNAL_REQUEST_SHA256),
    }
    values.update(overrides)
    return Ga4MetricRow(**values)  # type: ignore[arg-type]


def test_fixture_bindings_are_exact_and_ordered() -> None:
    assert tuple(item.recording_id.value for item in FIXTURE_BINDINGS) == (
        "baseline",
        "late-revised",
        "provider-error-429",
    )
    assert tuple(item.fixture_length.value for item in FIXTURE_BINDINGS) == (
        11_595,
        11_657,
        3_054,
    )


def test_internal_and_wire_request_hashes_are_exact() -> None:
    request = _request()
    assert request.internal_sha256.value == INTERNAL_REQUEST_SHA256
    assert request.wire_sha256.value == WIRE_REQUEST_SHA256
    assert b'"limit":2' in request.internal_bytes()
    assert b'"limit":"2"' in request.wire_bytes()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("property_id", "999"),
        ("date_ranges", (Ga4DateRange(date(2026, 7, 1), date(2026, 7, 2), None),) * 2),
        ("dimensions", tuple(reversed(EXACT_DIMENSIONS))),
        ("metrics", tuple(reversed(EXACT_METRICS))),
        ("dimension_filter", {}),
        ("metric_filter", {}),
        ("order_bys", ("date",)),
        ("limit", True),
        ("limit", 3),
        ("offset", True),
        ("offset", 1),
        ("keep_empty_rows", True),
        ("return_property_quota", False),
    ],
)
def test_request_rejects_profile_expansion(field: str, value: object) -> None:
    with pytest.raises(Ga4Failure):
        _request(**{field: value})


@pytest.mark.parametrize("force_reimport", [None, False])
def test_force_reimport_absent_or_false_is_inert(
    force_reimport: bool | None,
) -> None:
    assert _command(force_reimport=force_reimport).force_reimport is force_reimport


@pytest.mark.parametrize("force_reimport", [True, 0, 1, "false"])
def test_force_reimport_rejects_true_and_type_bypass(force_reimport: object) -> None:
    with pytest.raises(Ga4Failure):
        _command(force_reimport=force_reimport)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dimension_values", ("20260701", "/real/path", "mobile")),
        ("dimension_values", ("20260701", "/synthetic/a", "watch")),
        ("dimension_values", ("20260701", "/synthetic/a")),
        ("metric_values", (12, "20", "8")),
        ("metric_values", ("12", "NaN", "8")),
        ("metric_values", ("12", "20")),
        ("date_range_index", True),
        ("thresholding_applied", 0),
    ],
)
def test_rows_keep_ordered_provider_strings_and_reject_drift(
    field: str,
    value: object,
) -> None:
    with pytest.raises(Ga4Failure):
        _row(**{field: value})


def test_metric_values_are_preserved_as_ordered_strings() -> None:
    row = _row()
    assert row.metric_values == ("12", "20", "8")
    assert all(type(value) is str for value in row.metric_values)


def test_values_are_immutable_redacted_and_non_pickleable() -> None:
    digest = Ga4Sha256.of(b"synthetic")
    assert "synthetic" not in repr(digest)
    with pytest.raises(FrozenInstanceError):
        digest.value = "0" * 64  # type: ignore[misc]
    with pytest.raises(TypeError):
        pickle.dumps(digest)


@pytest.mark.parametrize(
    "candidate", ["BASELINE", "other", "../baseline", "baseline\n"]
)
def test_recording_id_is_closed(candidate: str) -> None:
    with pytest.raises(Ga4Failure):
        Ga4RecordingId(candidate)


def test_exact_fixture_length_rejects_bool() -> None:
    with pytest.raises(Ga4Failure):
        Ga4FixtureLength(True)

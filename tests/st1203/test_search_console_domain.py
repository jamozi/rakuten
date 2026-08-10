"""Domain contract tests for the recorded Search Console reference seam."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone
import pickle
from uuid import UUID

import pytest

from raos.domain.analytics.search_console import (
    EXACT_DIMENSIONS,
    FIXTURE_BINDINGS,
    SYNTHETIC_SITE_ID,
    AggregationType,
    DataState,
    Device,
    FixtureByteLength,
    RecordingId,
    SearchConsoleCommand,
    SearchConsoleFailure,
    SearchConsoleRequest,
    SearchConsoleRow,
    SearchType,
    Sha256Digest,
    binding_for,
)
from raos.domain.portfolio.workflow import UtcTimestamp


def _request(recording_id: str = "baseline") -> SearchConsoleRequest:
    binding = binding_for(RecordingId(recording_id))
    return SearchConsoleRequest(
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


def _row(**overrides: object) -> SearchConsoleRow:
    values: dict[str, object] = {
        "site_id": SYNTHETIC_SITE_ID,
        "date_from": date(2026, 7, 1),
        "date_to": date(2026, 7, 2),
        "dimensions": EXACT_DIMENSIONS,
        "keys": (
            "2026-07-01",
            "synthetic luggage",
            "https://example.invalid/guides/synthetic-luggage",
            "jpn",
            Device.MOBILE.value,
        ),
        "clicks": 12,
        "impressions": 120,
        "ctr": 0.1,
        "position": 3.25,
        "data_state": DataState.FINAL,
        "imported_at": UtcTimestamp(datetime(2026, 8, 5, tzinfo=timezone.utc)),
        "is_top_rows_limited": True,
        "source_request_sha256": _request().sha256,
    }
    values.update(overrides)
    return SearchConsoleRow(**values)  # type: ignore[arg-type]


def test_fixture_bindings_are_exact_and_ordered() -> None:
    assert tuple(item.recording_id.value for item in FIXTURE_BINDINGS) == (
        "baseline",
        "late-revised",
        "start-beyond-data",
    )
    assert tuple(item.fixture_length.value for item in FIXTURE_BINDINGS) == (
        3503,
        3507,
        1398,
    )


@pytest.mark.parametrize(
    ("recording_id", "expected"),
    [
        (
            "baseline",
            "b062bbe5000e83471fe3f1557f04c01a1b311d312055a74083df19fa7d5bd0be",
        ),
        (
            "late-revised",
            "b062bbe5000e83471fe3f1557f04c01a1b311d312055a74083df19fa7d5bd0be",
        ),
        (
            "start-beyond-data",
            "603738ab94f0c2cdd7c474ba0418ebd36d66215d125e180acdaefed5e84a0788",
        ),
    ],
)
def test_request_hash_is_exact(recording_id: str, expected: str) -> None:
    assert _request(recording_id).sha256.value == expected


def test_outbound_request_uses_type_and_explicit_defaults() -> None:
    outbound = dict(_request().outbound_body())
    assert outbound["type"] == "web"
    assert "searchType" not in outbound
    assert outbound["aggregationType"] == "auto"
    assert outbound["dataState"] == "final"
    assert outbound["dimensionFilterGroups"] == ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("site_url", "https://example.invalid"),
        ("dimensions", tuple(reversed(EXACT_DIMENSIONS))),
        ("row_limit", True),
        ("row_limit", 0),
        ("start_row", -1),
        ("dimension_filter_groups", ({},)),
    ],
)
def test_request_rejects_profile_drift(field: str, value: object) -> None:
    request = _request()
    values = {
        "site_url": request.site_url,
        "start_date": request.start_date,
        "end_date": request.end_date,
        "dimensions": request.dimensions,
        "search_type": request.search_type,
        "aggregation_type": request.aggregation_type,
        "data_state": request.data_state,
        "row_limit": request.row_limit,
        "start_row": request.start_row,
        "dimension_filter_groups": request.dimension_filter_groups,
    }
    values[field] = value
    with pytest.raises(SearchConsoleFailure):
        SearchConsoleRequest(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("site_id", UUID("00000000-0000-4000-8000-000000000001")),
        (
            "keys",
            ("2026-07-01", "real query", "https://example.invalid/a", "jpn", "MOBILE"),
        ),
        (
            "keys",
            ("2026-07-01", "synthetic query", "https://example.com/a", "jpn", "MOBILE"),
        ),
        (
            "keys",
            (
                "2026-07-01",
                "synthetic query",
                "https://example.invalid/a",
                "JP",
                "MOBILE",
            ),
        ),
        ("clicks", True),
        ("impressions", -1),
        ("ctr", 1.01),
        ("position", float("nan")),
        ("is_top_rows_limited", False),
    ],
)
def test_row_rejects_non_synthetic_or_malformed_values(
    field: str, value: object
) -> None:
    with pytest.raises(SearchConsoleFailure):
        _row(**{field: value})


def test_values_are_immutable_redacted_and_non_pickleable() -> None:
    digest = Sha256Digest.of(b"synthetic")
    assert "synthetic" not in repr(digest)
    with pytest.raises(FrozenInstanceError):
        digest.value = "0" * 64  # type: ignore[misc]
    with pytest.raises(TypeError):
        pickle.dumps(digest)


@pytest.mark.parametrize(
    "candidate",
    ["BASELINE", "other", "../baseline", "baseline\n"],
)
def test_recording_id_is_closed(candidate: str) -> None:
    with pytest.raises(SearchConsoleFailure):
        RecordingId(candidate)


def test_exact_integer_wrappers_reject_bool() -> None:
    with pytest.raises(SearchConsoleFailure):
        FixtureByteLength(True)


def test_command_binds_request_bytes_to_fixture_authority() -> None:
    binding = binding_for(RecordingId("baseline"))
    command = SearchConsoleCommand(
        recording_id=binding.recording_id,
        fixture_digest=binding.fixture_digest,
        fixture_length=binding.fixture_length,
        request=_request(),
    )
    assert command.request.sha256 == binding.request_digest

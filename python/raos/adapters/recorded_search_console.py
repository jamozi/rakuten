"""Strict caller-bytes adapter for the three ST-1203 recorded fixtures."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
from threading import RLock
from typing import NoReturn, SupportsIndex, cast, final
from uuid import UUID

from raos.domain.analytics.search_console import (
    DataState,
    RecordedPagination,
    RecordedSearchConsolePage,
    SearchConsoleCommand,
    SearchConsoleFailureCode,
    SearchConsoleRequest,
    SearchConsoleRow,
    Sha256Digest,
    fail_search_console,
)
from raos.domain.portfolio.workflow import UtcTimestamp


_ROOT_KEYS = frozenset(
    {
        "fixture_version",
        "outbound_request",
        "provider_response",
        "recorded_result",
        "recording_id",
        "request",
        "source_request_sha256",
        "synthetic_marker",
    }
)
_REQUEST_KEYS = frozenset(
    {
        "aggregation_type",
        "data_state",
        "dimension_filter_groups",
        "dimensions",
        "end_date",
        "row_limit",
        "search_type",
        "site_url",
        "start_date",
        "start_row",
    }
)
_RECORDED_ROW_KEYS = frozenset(
    {
        "clicks",
        "ctr",
        "data_state",
        "date_from",
        "date_to",
        "dimensions",
        "imported_at",
        "impressions",
        "is_top_rows_limited",
        "keys",
        "position",
        "site_id",
        "source_request_sha256",
    }
)
_PROVIDER_ROW_KEYS = frozenset({"clicks", "ctr", "impressions", "keys", "position"})


def _invalid() -> NoReturn:
    fail_search_console(SearchConsoleFailureCode.FIXTURE_DOCUMENT_INVALID)


def _reject_constant(value: str) -> NoReturn:
    del value
    _invalid()


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _invalid()
        result[key] = value
    return result


def _document(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        _invalid()
    document = cast(dict[str, object], value)
    if frozenset(document) != keys:
        _invalid()
    return document


def _array(value: object) -> list[object]:
    if type(value) is not list:
        _invalid()
    return cast(list[object], value)


def _text(value: object) -> str:
    if type(value) is not str:
        _invalid()
    return value


def _integer(value: object) -> int:
    if type(value) is not int:
        _invalid()
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        _invalid()
    return value


def _number(value: object) -> int | float:
    if type(value) not in {int, float}:
        _invalid()
    return cast(int | float, value)


def _data_state(value: object) -> DataState:
    if value != DataState.FINAL.value or type(value) is not str:
        _invalid()
    return DataState.FINAL


def _calendar_date(value: object) -> date:
    raw = _text(value)
    parsed: date | None = None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        pass
    if parsed is None or parsed.isoformat() != raw:
        _invalid()
    return parsed


def _utc_timestamp(value: object) -> UtcTimestamp:
    raw = _text(value)
    if len(raw) != 20 or not raw.endswith("Z"):
        _invalid()
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00")
    except ValueError:
        pass
    if (
        parsed is None
        or parsed.tzinfo is None
        or parsed.utcoffset() != timezone.utc.utcoffset(parsed)
    ):
        _invalid()
    return UtcTimestamp(parsed.astimezone(timezone.utc))


def _same_json(actual: object, expected: object) -> bool:
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        actual_document = cast(dict[str, object], actual)
        expected_document = cast(dict[str, object], expected)
        if actual_document.keys() != expected_document.keys():
            return False
        return all(
            _same_json(actual_document[key], expected_document[key])
            for key in expected_document
        )
    if type(expected) is list:
        actual_array = cast(list[object], actual)
        expected_array = cast(list[object], expected)
        return len(actual_array) == len(expected_array) and all(
            _same_json(left, right)
            for left, right in zip(actual_array, expected_array, strict=True)
        )
    return actual == expected


def _expected_request(request: SearchConsoleRequest) -> dict[str, object]:
    return {
        "aggregation_type": request.aggregation_type.value,
        "data_state": request.data_state.value,
        "dimension_filter_groups": [],
        "dimensions": list(request.dimensions),
        "end_date": request.end_date.isoformat(),
        "row_limit": request.row_limit,
        "search_type": request.search_type.value,
        "site_url": request.site_url,
        "start_date": request.start_date.isoformat(),
        "start_row": request.start_row,
    }


def _expected_outbound(request: SearchConsoleRequest) -> dict[str, object]:
    return {
        "aggregationType": request.aggregation_type.value,
        "dataState": request.data_state.value,
        "dimensionFilterGroups": [],
        "dimensions": list(request.dimensions),
        "endDate": request.end_date.isoformat(),
        "rowLimit": request.row_limit,
        "startDate": request.start_date.isoformat(),
        "startRow": request.start_row,
        "type": request.search_type.value,
    }


def _parse_row(
    value: object,
    *,
    request: SearchConsoleRequest,
    recorded_at: UtcTimestamp,
) -> SearchConsoleRow:
    row = _document(value, _RECORDED_ROW_KEYS)
    dimensions = tuple(_text(item) for item in _array(row["dimensions"]))
    keys = tuple(_text(item) for item in _array(row["keys"]))
    site_id: UUID | None = None
    try:
        site_id = UUID(_text(row["site_id"]))
    except ValueError:
        pass
    if site_id is None:
        _invalid()
    parsed = SearchConsoleRow(
        site_id=site_id,
        date_from=_calendar_date(row["date_from"]),
        date_to=_calendar_date(row["date_to"]),
        dimensions=dimensions,
        keys=keys,
        clicks=_number(row["clicks"]),
        impressions=_number(row["impressions"]),
        ctr=_number(row["ctr"]),
        position=_number(row["position"]),
        data_state=_data_state(row["data_state"]),
        imported_at=_utc_timestamp(row["imported_at"]),
        is_top_rows_limited=_boolean(row["is_top_rows_limited"]),
        source_request_sha256=Sha256Digest(_text(row["source_request_sha256"])),
    )
    if (
        parsed.date_from != request.start_date
        or parsed.date_to != request.end_date
        or parsed.dimensions != request.dimensions
        or parsed.imported_at != recorded_at
        or parsed.source_request_sha256 != request.sha256
    ):
        _invalid()
    return parsed


def _provider_projection(row: SearchConsoleRow) -> dict[str, object]:
    return {
        "clicks": row.clicks,
        "ctr": row.ctr,
        "impressions": row.impressions,
        "keys": list(row.keys),
        "position": row.position,
    }


def _parse_page(
    command: SearchConsoleCommand, fixture_bytes: bytes
) -> RecordedSearchConsolePage:
    if (
        type(fixture_bytes) is not bytes
        or len(fixture_bytes) != command.fixture_length.value
        or Sha256Digest.of(fixture_bytes) != command.fixture_digest
    ):
        fail_search_console(SearchConsoleFailureCode.FIXTURE_BYTES_MISMATCH)
    value: object = None
    parsed = False
    try:
        decoded = fixture_bytes.decode("utf-8", errors="strict")
        value = json.loads(
            decoded,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
        parsed = True
    except Exception:
        pass
    if not parsed:
        fail_search_console(SearchConsoleFailureCode.FIXTURE_DOCUMENT_INVALID)
    root = _document(value, _ROOT_KEYS)
    if (
        root["fixture_version"] != "1.0.0"
        or root["synthetic_marker"] != "SYNTHETIC_TEST_ONLY"
        or root["recording_id"] != command.recording_id.value
        or root["source_request_sha256"] != command.request.sha256.value
    ):
        _invalid()

    request_document = _document(root["request"], _REQUEST_KEYS)
    if not _same_json(request_document, _expected_request(command.request)):
        fail_search_console(SearchConsoleFailureCode.REQUEST_MISMATCH)

    outbound = _document(root["outbound_request"], frozenset({"body", "site_url"}))
    body = _document(outbound["body"], frozenset(_expected_outbound(command.request)))
    if (
        outbound["site_url"] != command.request.site_url
        or "searchType" in body
        or not _same_json(body, _expected_outbound(command.request))
    ):
        fail_search_console(SearchConsoleFailureCode.REQUEST_MISMATCH)

    result = _document(
        root["recorded_result"],
        frozenset(
            {
                "pagination",
                "recorded_at",
                "rows",
                "rows_not_guaranteed_complete",
                "top_rows_only",
            }
        ),
    )
    recorded_at = _utc_timestamp(result["recorded_at"])
    rows = tuple(
        _parse_row(item, request=command.request, recorded_at=recorded_at)
        for item in _array(result["rows"])
    )
    pagination_document = _document(
        result["pagination"],
        frozenset({"returned_row_count", "row_limit", "start_row"}),
    )
    pagination = RecordedPagination(
        returned_row_count=_integer(pagination_document["returned_row_count"]),
        row_limit=_integer(pagination_document["row_limit"]),
        start_row=_integer(pagination_document["start_row"]),
    )

    provider_response = _document(
        root["provider_response"], frozenset({"responseAggregationType", "rows"})
    )
    provider_rows = _array(provider_response["rows"])
    expected_provider_rows = [_provider_projection(row) for row in rows]
    if any(
        type(row) is not dict or frozenset(row) != _PROVIDER_ROW_KEYS
        for row in provider_rows
    ):
        _invalid()
    if provider_response["responseAggregationType"] != "byPage" or not _same_json(
        provider_rows, expected_provider_rows
    ):
        _invalid()

    return RecordedSearchConsolePage(
        recording_id=command.recording_id,
        fixture_digest=command.fixture_digest,
        fixture_length=command.fixture_length,
        request=command.request,
        request_digest=command.request.sha256,
        response_aggregation_type=_text(provider_response["responseAggregationType"]),
        recorded_at=recorded_at,
        pagination=pagination,
        rows=rows,
        top_rows_only=_boolean(result["top_rows_only"]),
        rows_not_guaranteed_complete=_boolean(result["rows_not_guaranteed_complete"]),
    )


@final
class RecordedSearchConsoleFixtureExchange:
    """Consume one exact, already supplied fixture without retaining its bytes."""

    __slots__ = ("_command", "_consumed", "_lock", "_page")

    def __init__(self, *, command: SearchConsoleCommand, fixture_bytes: bytes) -> None:
        if type(command) is not SearchConsoleCommand:
            fail_search_console()
        page = _parse_page(command, fixture_bytes)
        self._command = command
        self._page = page
        self._consumed = False
        self._lock = RLock()

    def __repr__(self) -> str:
        return (
            "RecordedSearchConsoleFixtureExchange(<redacted-search-console-reference>)"
        )

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError(
            "recorded Search Console exchange serialization is not supported"
        )

    def exchange(self, command: SearchConsoleCommand) -> RecordedSearchConsolePage:
        if type(command) is not SearchConsoleCommand or command != self._command:
            fail_search_console(SearchConsoleFailureCode.REQUEST_MISMATCH)
        with self._lock:
            if self._consumed:
                fail_search_console(
                    SearchConsoleFailureCode.RECORDED_EXCHANGE_EXHAUSTED
                )
            self._consumed = True
            return self._page


__all__ = ["RecordedSearchConsoleFixtureExchange"]

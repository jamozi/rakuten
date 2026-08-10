"""Immutable recorded Search Console reference values for ST-1203.

The runtime seam accepts caller-supplied fixture bytes through an outward
recorded adapter.  It contains no provider, credential, file, repository,
pagination-loop, import-job, persistence, or supersession behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
import hashlib
import json
import math
import re
from typing import NoReturn, SupportsIndex, TypeAlias, cast
from uuid import UUID

from raos.domain.portfolio.workflow import UtcTimestamp


_REDACTED = "<redacted-search-console-reference>"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_RECORDING_ID = re.compile(r"(?:baseline|late-revised|start-beyond-data)\Z", re.ASCII)
_SYNTHETIC_QUERY = re.compile(r"synthetic [a-z0-9]+(?:[ -][a-z0-9]+)*\Z", re.ASCII)
_SYNTHETIC_PAGE = re.compile(
    r"https://example\.invalid/[a-z0-9][a-z0-9/_-]{0,511}\Z", re.ASCII
)
_COUNTRY = re.compile(r"[a-z]{3}\Z", re.ASCII)
_MAX_EXACT_INTEGER = (1 << 63) - 1

SYNTHETIC_SITE_ID = UUID("00000000-0000-4000-8000-000000001203")
EXACT_DIMENSIONS = ("date", "query", "page", "country", "device")


class SearchType(str, Enum):
    WEB = "web"


class AggregationType(str, Enum):
    AUTO = "auto"


class DataState(str, Enum):
    FINAL = "final"


class Device(str, Enum):
    MOBILE = "MOBILE"
    DESKTOP = "DESKTOP"
    TABLET = "TABLET"


class RecordedMetricsComparison(str, Enum):
    RECORDED_METRICS_DIFFER = "RECORDED_METRICS_DIFFER"


class EmptyPageMeaning(str, Enum):
    RECORDED_ZERO_ROWS_ONLY = "RECORDED_ZERO_ROWS_ONLY"


class SearchConsoleBoundaryStatus(str, Enum):
    RECORDED_FIXTURE_ONLY = "RECORDED_FIXTURE_ONLY"
    NOT_EXECUTED = "NOT_EXECUTED"
    NOT_USED = "NOT_USED"
    NOT_CREATED = "NOT_CREATED"
    NOT_DEFINED = "NOT_DEFINED"
    NOT_READY = "NOT_READY"


class SearchConsoleFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    FIXTURE_BYTES_MISMATCH = "FIXTURE_BYTES_MISMATCH"
    FIXTURE_DOCUMENT_INVALID = "FIXTURE_DOCUMENT_INVALID"
    FIXTURE_IDENTITY_MISMATCH = "FIXTURE_IDENTITY_MISMATCH"
    REQUEST_MISMATCH = "REQUEST_MISMATCH"
    RECORDED_EXCHANGE_EXHAUSTED = "RECORDED_EXCHANGE_EXHAUSTED"
    RECORDED_EXCHANGE_UNAVAILABLE = "RECORDED_EXCHANGE_UNAVAILABLE"
    RECORDED_RESULT_MISMATCH = "RECORDED_RESULT_MISMATCH"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("search console reference serialization is not supported")


@dataclass(frozen=True, slots=True, repr=False)
class SearchConsoleFailure(RuntimeError):
    code: SearchConsoleFailureCode

    def __post_init__(self) -> None:
        if type(self.code) is not SearchConsoleFailureCode:
            raise TypeError("invalid Search Console failure code")
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"SearchConsoleFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("search console failure serialization is not supported")


def fail_search_console(
    code: SearchConsoleFailureCode = SearchConsoleFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise SearchConsoleFailure(code) from None


@dataclass(frozen=True, slots=True, repr=False)
class RecordingId(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _RECORDING_ID.fullmatch(self.value) is None:
            fail_search_console()


@dataclass(frozen=True, slots=True, repr=False)
class Sha256Digest(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _SHA256.fullmatch(self.value) is None:
            fail_search_console()

    @classmethod
    def of(cls, content: bytes) -> Sha256Digest:
        if type(content) is not bytes:
            fail_search_console()
        return cls(hashlib.sha256(content).hexdigest())


@dataclass(frozen=True, slots=True, repr=False)
class FixtureByteLength(_RedactedValue):
    value: int

    def __post_init__(self) -> None:
        if type(self.value) is not int or not 0 < self.value <= 4 * 1024 * 1024:
            fail_search_console()


@dataclass(frozen=True, slots=True, repr=False)
class SearchConsoleRequest(_RedactedValue):
    site_url: str
    start_date: date
    end_date: date
    dimensions: tuple[str, ...]
    search_type: SearchType
    aggregation_type: AggregationType
    data_state: DataState
    row_limit: int
    start_row: int
    dimension_filter_groups: tuple[object, ...]

    def __post_init__(self) -> None:
        if (
            type(self.site_url) is not str
            or self.site_url != "sc-domain:example.invalid"
            or type(self.start_date) is not date
            or self.start_date != date(2026, 7, 1)
            or type(self.end_date) is not date
            or self.end_date != date(2026, 7, 2)
            or self.start_date > self.end_date
            or self.dimensions != EXACT_DIMENSIONS
            or self.search_type is not SearchType.WEB
            or self.aggregation_type is not AggregationType.AUTO
            or self.data_state is not DataState.FINAL
            or type(self.row_limit) is not int
            or not 1 <= self.row_limit <= 25_000
            or type(self.start_row) is not int
            or not 0 <= self.start_row <= _MAX_EXACT_INTEGER
            or type(self.dimension_filter_groups) is not tuple
            or self.dimension_filter_groups
        ):
            fail_search_console()

    def canonical_bytes(self) -> bytes:
        document = {
            "aggregation_type": self.aggregation_type.value,
            "data_state": self.data_state.value,
            "dimension_filter_groups": [],
            "dimensions": list(self.dimensions),
            "end_date": self.end_date.isoformat(),
            "row_limit": self.row_limit,
            "search_type": self.search_type.value,
            "site_url": self.site_url,
            "start_date": self.start_date.isoformat(),
            "start_row": self.start_row,
        }
        return json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    @property
    def sha256(self) -> Sha256Digest:
        return Sha256Digest.of(self.canonical_bytes())

    def outbound_body(self) -> tuple[tuple[str, object], ...]:
        return (
            ("aggregationType", self.aggregation_type.value),
            ("dataState", self.data_state.value),
            ("dimensionFilterGroups", ()),
            ("dimensions", self.dimensions),
            ("endDate", self.end_date.isoformat()),
            ("rowLimit", self.row_limit),
            ("startDate", self.start_date.isoformat()),
            ("startRow", self.start_row),
            ("type", self.search_type.value),
        )


@dataclass(frozen=True, slots=True, repr=False)
class FixtureBinding(_RedactedValue):
    recording_id: RecordingId
    fixture_digest: Sha256Digest
    fixture_length: FixtureByteLength
    request_digest: Sha256Digest
    row_limit: int
    start_row: int

    def __post_init__(self) -> None:
        if (
            type(self.recording_id) is not RecordingId
            or type(self.fixture_digest) is not Sha256Digest
            or type(self.fixture_length) is not FixtureByteLength
            or type(self.request_digest) is not Sha256Digest
            or type(self.row_limit) is not int
            or type(self.start_row) is not int
        ):
            fail_search_console()


FIXTURE_BINDINGS = (
    FixtureBinding(
        RecordingId("baseline"),
        Sha256Digest(
            "de421fe75e633d47a02f0aa579f36f746d5ee191eb034dbd28a6c5dfd26dd3a9"
        ),
        FixtureByteLength(3503),
        Sha256Digest(
            "b062bbe5000e83471fe3f1557f04c01a1b311d312055a74083df19fa7d5bd0be"
        ),
        2,
        0,
    ),
    FixtureBinding(
        RecordingId("late-revised"),
        Sha256Digest(
            "f703edb673b3cc8b3686a9d983ab7940f7c3148a4eb7ac192da5761f0b0b96a0"
        ),
        FixtureByteLength(3507),
        Sha256Digest(
            "b062bbe5000e83471fe3f1557f04c01a1b311d312055a74083df19fa7d5bd0be"
        ),
        2,
        0,
    ),
    FixtureBinding(
        RecordingId("start-beyond-data"),
        Sha256Digest(
            "1b50f12e0a904db7202771adb39157071ec959c0f4d4d0e815e67a9e6f45557c"
        ),
        FixtureByteLength(1398),
        Sha256Digest(
            "603738ab94f0c2cdd7c474ba0418ebd36d66215d125e180acdaefed5e84a0788"
        ),
        25_000,
        25_000,
    ),
)


def binding_for(recording_id: RecordingId) -> FixtureBinding:
    if type(recording_id) is not RecordingId:
        fail_search_console()
    for binding in FIXTURE_BINDINGS:
        if binding.recording_id == recording_id:
            return binding
    fail_search_console()


@dataclass(frozen=True, slots=True, repr=False)
class SearchConsoleCommand(_RedactedValue):
    recording_id: RecordingId
    fixture_digest: Sha256Digest
    fixture_length: FixtureByteLength
    request: SearchConsoleRequest

    def __post_init__(self) -> None:
        if (
            type(self.recording_id) is not RecordingId
            or type(self.fixture_digest) is not Sha256Digest
            or type(self.fixture_length) is not FixtureByteLength
            or type(self.request) is not SearchConsoleRequest
        ):
            fail_search_console()
        binding = binding_for(self.recording_id)
        if (
            self.fixture_digest != binding.fixture_digest
            or self.fixture_length != binding.fixture_length
            or self.request.sha256 != binding.request_digest
            or self.request.row_limit != binding.row_limit
            or self.request.start_row != binding.start_row
        ):
            fail_search_console(SearchConsoleFailureCode.REQUEST_MISMATCH)


JsonNumber: TypeAlias = int | float


def _nonnegative_number(value: object) -> JsonNumber:
    if type(value) not in {int, float}:
        fail_search_console(SearchConsoleFailureCode.FIXTURE_DOCUMENT_INVALID)
    number = cast(JsonNumber, value)
    if not math.isfinite(number) or number < 0:
        fail_search_console(SearchConsoleFailureCode.FIXTURE_DOCUMENT_INVALID)
    return number


@dataclass(frozen=True, slots=True, repr=False)
class SearchConsoleRow(_RedactedValue):
    site_id: UUID
    date_from: date
    date_to: date
    dimensions: tuple[str, ...]
    keys: tuple[str, ...]
    clicks: JsonNumber
    impressions: JsonNumber
    ctr: JsonNumber
    position: JsonNumber
    data_state: DataState
    imported_at: UtcTimestamp
    is_top_rows_limited: bool
    source_request_sha256: Sha256Digest

    def __post_init__(self) -> None:
        if (
            type(self.site_id) is not UUID
            or self.site_id != SYNTHETIC_SITE_ID
            or type(self.date_from) is not date
            or self.date_from != date(2026, 7, 1)
            or type(self.date_to) is not date
            or self.date_to != date(2026, 7, 2)
            or self.dimensions != EXACT_DIMENSIONS
            or type(self.keys) is not tuple
            or len(self.keys) != len(EXACT_DIMENSIONS)
            or any(type(key) is not str for key in self.keys)
            or self.data_state is not DataState.FINAL
            or type(self.imported_at) is not UtcTimestamp
            or self.is_top_rows_limited is not True
            or type(self.source_request_sha256) is not Sha256Digest
        ):
            fail_search_console(SearchConsoleFailureCode.FIXTURE_DOCUMENT_INVALID)
        key_date: date | None = None
        try:
            key_date = date.fromisoformat(self.keys[0])
        except ValueError:
            pass
        if key_date is None:
            fail_search_console(SearchConsoleFailureCode.FIXTURE_DOCUMENT_INVALID)
        if (
            not self.date_from <= key_date <= self.date_to
            or len(self.keys[1]) > 80
            or _SYNTHETIC_QUERY.fullmatch(self.keys[1]) is None
            or _SYNTHETIC_PAGE.fullmatch(self.keys[2]) is None
            or _COUNTRY.fullmatch(self.keys[3]) is None
        ):
            fail_search_console(SearchConsoleFailureCode.FIXTURE_DOCUMENT_INVALID)
        if self.keys[4] not in {item.value for item in Device}:
            fail_search_console(SearchConsoleFailureCode.FIXTURE_DOCUMENT_INVALID)
        _nonnegative_number(self.clicks)
        _nonnegative_number(self.impressions)
        ctr = _nonnegative_number(self.ctr)
        _nonnegative_number(self.position)
        if ctr > 1:
            fail_search_console(SearchConsoleFailureCode.FIXTURE_DOCUMENT_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class RecordedPagination(_RedactedValue):
    returned_row_count: int
    row_limit: int
    start_row: int

    def __post_init__(self) -> None:
        if (
            type(self.returned_row_count) is not int
            or self.returned_row_count < 0
            or type(self.row_limit) is not int
            or not 1 <= self.row_limit <= 25_000
            or type(self.start_row) is not int
            or self.start_row < 0
        ):
            fail_search_console(SearchConsoleFailureCode.FIXTURE_DOCUMENT_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class RecordedSearchConsolePage(_RedactedValue):
    recording_id: RecordingId
    fixture_digest: Sha256Digest
    fixture_length: FixtureByteLength
    request: SearchConsoleRequest
    request_digest: Sha256Digest
    response_aggregation_type: str
    recorded_at: UtcTimestamp
    pagination: RecordedPagination
    rows: tuple[SearchConsoleRow, ...]
    top_rows_only: bool
    rows_not_guaranteed_complete: bool

    def __post_init__(self) -> None:
        if (
            type(self.recording_id) is not RecordingId
            or type(self.fixture_digest) is not Sha256Digest
            or type(self.fixture_length) is not FixtureByteLength
            or type(self.request) is not SearchConsoleRequest
            or type(self.request_digest) is not Sha256Digest
            or self.request_digest != self.request.sha256
            or self.response_aggregation_type != "byPage"
            or type(self.recorded_at) is not UtcTimestamp
            or type(self.pagination) is not RecordedPagination
            or type(self.rows) is not tuple
            or any(type(row) is not SearchConsoleRow for row in self.rows)
            or self.pagination.returned_row_count != len(self.rows)
            or self.pagination.row_limit != self.request.row_limit
            or self.pagination.start_row != self.request.start_row
            or self.top_rows_only is not True
            or self.rows_not_guaranteed_complete is not True
        ):
            fail_search_console(SearchConsoleFailureCode.FIXTURE_DOCUMENT_INVALID)
        binding = binding_for(self.recording_id)
        if (
            self.fixture_digest != binding.fixture_digest
            or self.fixture_length != binding.fixture_length
            or self.request_digest != binding.request_digest
            or any(
                row.site_id != SYNTHETIC_SITE_ID
                or row.date_from != self.request.start_date
                or row.date_to != self.request.end_date
                or row.dimensions != self.request.dimensions
                or row.imported_at != self.recorded_at
                or row.source_request_sha256 != self.request_digest
                for row in self.rows
            )
        ):
            fail_search_console(SearchConsoleFailureCode.FIXTURE_IDENTITY_MISMATCH)

    @property
    def empty_page_meaning(self) -> EmptyPageMeaning | None:
        return EmptyPageMeaning.RECORDED_ZERO_ROWS_ONLY if not self.rows else None


@dataclass(frozen=True, slots=True, repr=False)
class RecordedPageComparison(_RedactedValue):
    baseline_recording_id: RecordingId
    revised_recording_id: RecordingId
    request_digest: Sha256Digest
    comparison: RecordedMetricsComparison
    supersession: SearchConsoleBoundaryStatus

    def __post_init__(self) -> None:
        if (
            self.baseline_recording_id != RecordingId("baseline")
            or self.revised_recording_id != RecordingId("late-revised")
            or type(self.request_digest) is not Sha256Digest
            or self.comparison is not RecordedMetricsComparison.RECORDED_METRICS_DIFFER
            or self.supersession is not SearchConsoleBoundaryStatus.NOT_DEFINED
        ):
            fail_search_console()


def compare_recorded_pages(
    baseline: RecordedSearchConsolePage,
    revised: RecordedSearchConsolePage,
) -> RecordedPageComparison:
    if (
        type(baseline) is not RecordedSearchConsolePage
        or type(revised) is not RecordedSearchConsolePage
        or baseline.recording_id != RecordingId("baseline")
        or revised.recording_id != RecordingId("late-revised")
        or baseline.request != revised.request
        or baseline.request_digest != revised.request_digest
        or baseline.recorded_at.value >= revised.recorded_at.value
        or baseline.rows == revised.rows
    ):
        fail_search_console(SearchConsoleFailureCode.RECORDED_RESULT_MISMATCH)
    return RecordedPageComparison(
        baseline_recording_id=baseline.recording_id,
        revised_recording_id=revised.recording_id,
        request_digest=baseline.request_digest,
        comparison=RecordedMetricsComparison.RECORDED_METRICS_DIFFER,
        supersession=SearchConsoleBoundaryStatus.NOT_DEFINED,
    )


@dataclass(frozen=True, slots=True, repr=False)
class SearchConsoleImportReference(_RedactedValue):
    page: RecordedSearchConsolePage
    execution: SearchConsoleBoundaryStatus
    provider: SearchConsoleBoundaryStatus
    credentials: SearchConsoleBoundaryStatus
    import_run: SearchConsoleBoundaryStatus
    persistence: SearchConsoleBoundaryStatus
    supersession: SearchConsoleBoundaryStatus
    audit: SearchConsoleBoundaryStatus
    outbox: SearchConsoleBoundaryStatus
    formal_tst_030: SearchConsoleBoundaryStatus
    decision: SearchConsoleBoundaryStatus

    def __post_init__(self) -> None:
        if (
            type(self.page) is not RecordedSearchConsolePage
            or self.execution is not SearchConsoleBoundaryStatus.RECORDED_FIXTURE_ONLY
            or self.provider is not SearchConsoleBoundaryStatus.NOT_EXECUTED
            or self.credentials is not SearchConsoleBoundaryStatus.NOT_USED
            or self.import_run is not SearchConsoleBoundaryStatus.NOT_CREATED
            or self.persistence is not SearchConsoleBoundaryStatus.NOT_EXECUTED
            or self.supersession is not SearchConsoleBoundaryStatus.NOT_DEFINED
            or self.audit is not SearchConsoleBoundaryStatus.NOT_EXECUTED
            or self.outbox is not SearchConsoleBoundaryStatus.NOT_EXECUTED
            or self.formal_tst_030 is not SearchConsoleBoundaryStatus.NOT_EXECUTED
            or self.decision is not SearchConsoleBoundaryStatus.NOT_READY
        ):
            fail_search_console()


__all__ = [
    "EXACT_DIMENSIONS",
    "FIXTURE_BINDINGS",
    "SYNTHETIC_SITE_ID",
    "AggregationType",
    "DataState",
    "Device",
    "EmptyPageMeaning",
    "FixtureBinding",
    "FixtureByteLength",
    "JsonNumber",
    "RecordedMetricsComparison",
    "RecordedPageComparison",
    "RecordedPagination",
    "RecordedSearchConsolePage",
    "RecordingId",
    "SearchConsoleBoundaryStatus",
    "SearchConsoleCommand",
    "SearchConsoleFailure",
    "SearchConsoleFailureCode",
    "SearchConsoleImportReference",
    "SearchConsoleRequest",
    "SearchConsoleRow",
    "SearchType",
    "Sha256Digest",
    "binding_for",
    "compare_recorded_pages",
    "fail_search_console",
]

"""Immutable, non-attesting values for the ST-1204 recorded GA4 seam."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
import hashlib
import json
import math
import re
from typing import NoReturn, SupportsIndex, TypeAlias, cast
from uuid import UUID


_REDACTED = "<redacted-recorded-ga4-reference>"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_RECORDING = re.compile(r"(?:baseline|late-revised|provider-error-429)\Z", re.ASCII)
_METRIC_VALUE = re.compile(r"[0-9]+(?:\.[0-9]+)?\Z", re.ASCII)
_SYNTHETIC_PATH = re.compile(r"/synthetic/[a-z0-9][a-z0-9/-]{0,255}\Z", re.ASCII)
_GA4_DATE = re.compile(r"2026070[12]\Z", re.ASCII)
_DEVICE = re.compile(r"(?:mobile|desktop|tablet)\Z", re.ASCII)
_MAX_EXACT_INTEGER = (1 << 63) - 1

SYNTHETIC_SITE_ID = UUID("00000000-0000-4000-8000-000000001204")
SYNTHETIC_PROPERTY_ID = "1000001204"
SYNTHETIC_PROPERTY_RESOURCE = "properties/1000001204"
EXACT_DIMENSIONS = ("date", "pagePath", "deviceCategory")
EXACT_METRICS = ("sessions", "screenPageViews", "engagedSessions")
INTERNAL_REQUEST_SHA256 = (
    "ee206e0ec5d7c98afa2e871a33db134e558a2d854a724832ba834394bb2a22eb"
)
WIRE_REQUEST_SHA256 = "42a74836abe8d2be8cea6c4ffa47a3899e22cdec3f9ba31aa21be23622c7836a"
REPORTING_IDENTITY_SHA256 = (
    "f08c8c440562901e6ddbc56ce73a28a43a14a4d4691e432cdfe0e0249baa9ce3"
)


class Ga4RecordedOutcome(str, Enum):
    RECORDED_SUCCESS = "RECORDED_SUCCESS"
    RECORDED_RESOURCE_EXHAUSTED = "RECORDED_RESOURCE_EXHAUSTED"


class Ga4ReportingIdentity(str, Enum):
    DEVICE_BASED = "DEVICE_BASED"


class Ga4BoundaryStatus(str, Enum):
    RECORDED_FIXTURE_ONLY = "RECORDED_FIXTURE_ONLY"
    DISABLED_OD_012 = "DISABLED_OD_012"
    NOT_USED = "NOT_USED"
    NOT_EXECUTED = "NOT_EXECUTED"
    IN_FIXTURE_ONLY = "IN_FIXTURE_ONLY"
    NOT_CAPTURED_AFTER_ERROR = "NOT_CAPTURED_AFTER_ERROR"
    NOT_DEFINED = "NOT_DEFINED"
    NOT_READY = "NOT_READY"


class Ga4FailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    FIXTURE_BYTES_MISMATCH = "FIXTURE_BYTES_MISMATCH"
    FIXTURE_DOCUMENT_INVALID = "FIXTURE_DOCUMENT_INVALID"
    REQUEST_MISMATCH = "REQUEST_MISMATCH"
    RECORDED_EXCHANGE_EXHAUSTED = "RECORDED_EXCHANGE_EXHAUSTED"
    RECORDED_EXCHANGE_UNAVAILABLE = "RECORDED_EXCHANGE_UNAVAILABLE"
    RECORDED_RESULT_MISMATCH = "RECORDED_RESULT_MISMATCH"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded GA4 reference serialization is not supported")


@dataclass(frozen=True, slots=True, repr=False)
class Ga4Failure(RuntimeError):
    code: Ga4FailureCode

    def __post_init__(self) -> None:
        if type(self.code) is not Ga4FailureCode:
            raise TypeError("invalid recorded GA4 failure code")
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"Ga4Failure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded GA4 failure serialization is not supported")


def fail_ga4(code: Ga4FailureCode = Ga4FailureCode.INVALID_ARGUMENT) -> NoReturn:
    raise Ga4Failure(code) from None


@dataclass(frozen=True, slots=True, repr=False)
class Ga4RecordingId(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _RECORDING.fullmatch(self.value) is None:
            fail_ga4()


@dataclass(frozen=True, slots=True, repr=False)
class Ga4Sha256(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _SHA256.fullmatch(self.value) is None:
            fail_ga4()

    @classmethod
    def of(cls, content: bytes) -> Ga4Sha256:
        if type(content) is not bytes:
            fail_ga4()
        return cls(hashlib.sha256(content).hexdigest())


@dataclass(frozen=True, slots=True, repr=False)
class Ga4FixtureLength(_RedactedValue):
    value: int

    def __post_init__(self) -> None:
        if type(self.value) is not int or not 0 < self.value <= 4 * 1024 * 1024:
            fail_ga4()


@dataclass(frozen=True, slots=True, repr=False)
class Ga4UtcTimestamp(_RedactedValue):
    value: datetime

    def __post_init__(self) -> None:
        if (
            type(self.value) is not datetime
            or self.value.tzinfo is not timezone.utc
            or self.value.fold != 0
        ):
            fail_ga4()


@dataclass(frozen=True, slots=True, repr=False)
class Ga4DateRange(_RedactedValue):
    start_date: date
    end_date: date
    name: None

    def __post_init__(self) -> None:
        if (
            type(self.start_date) is not date
            or self.start_date != date(2026, 7, 1)
            or type(self.end_date) is not date
            or self.end_date != date(2026, 7, 2)
            or self.name is not None
        ):
            fail_ga4()


@dataclass(frozen=True, slots=True, repr=False)
class Ga4RecordedRequest(_RedactedValue):
    property_id: str
    date_ranges: tuple[Ga4DateRange, ...]
    dimensions: tuple[str, ...]
    metrics: tuple[str, ...]
    dimension_filter: None
    metric_filter: None
    order_bys: tuple[object, ...]
    limit: int
    offset: int
    keep_empty_rows: bool
    return_property_quota: bool

    def __post_init__(self) -> None:
        if (
            type(self.property_id) is not str
            or self.property_id != SYNTHETIC_PROPERTY_ID
            or type(self.date_ranges) is not tuple
            or self.date_ranges
            != (Ga4DateRange(date(2026, 7, 1), date(2026, 7, 2), None),)
            or self.dimensions != EXACT_DIMENSIONS
            or self.metrics != EXACT_METRICS
            or self.dimension_filter is not None
            or self.metric_filter is not None
            or type(self.order_bys) is not tuple
            or self.order_bys
            or type(self.limit) is not int
            or self.limit != 2
            or type(self.offset) is not int
            or self.offset != 0
            or self.keep_empty_rows is not False
            or self.return_property_quota is not True
        ):
            fail_ga4()
        if (
            self.internal_sha256.value != INTERNAL_REQUEST_SHA256
            or self.wire_sha256.value != WIRE_REQUEST_SHA256
        ):
            fail_ga4(Ga4FailureCode.REQUEST_MISMATCH)

    def internal_bytes(self) -> bytes:
        document = {
            "date_ranges": [
                {
                    "end_date": item.end_date.isoformat(),
                    "name": item.name,
                    "start_date": item.start_date.isoformat(),
                }
                for item in self.date_ranges
            ],
            "dimension_filter": None,
            "dimensions": list(self.dimensions),
            "keep_empty_rows": self.keep_empty_rows,
            "limit": self.limit,
            "metric_filter": None,
            "metrics": list(self.metrics),
            "offset": self.offset,
            "order_bys": [],
            "property_id": self.property_id,
            "return_property_quota": self.return_property_quota,
        }
        return _canonical_json(document)

    def wire_bytes(self) -> bytes:
        document = {
            "dateRanges": [
                {
                    "endDate": item.end_date.isoformat(),
                    "startDate": item.start_date.isoformat(),
                }
                for item in self.date_ranges
            ],
            "dimensions": [{"name": item} for item in self.dimensions],
            "keepEmptyRows": self.keep_empty_rows,
            "limit": str(self.limit),
            "metrics": [{"name": item} for item in self.metrics],
            "offset": str(self.offset),
            "returnPropertyQuota": self.return_property_quota,
        }
        return _canonical_json(document)

    @property
    def internal_sha256(self) -> Ga4Sha256:
        return Ga4Sha256.of(self.internal_bytes())

    @property
    def wire_sha256(self) -> Ga4Sha256:
        return Ga4Sha256.of(self.wire_bytes())


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


@dataclass(frozen=True, slots=True, repr=False)
class Ga4FixtureBinding(_RedactedValue):
    recording_id: Ga4RecordingId
    fixture_digest: Ga4Sha256
    fixture_length: Ga4FixtureLength
    response_digest: Ga4Sha256
    successful: bool

    def __post_init__(self) -> None:
        if (
            type(self.recording_id) is not Ga4RecordingId
            or type(self.fixture_digest) is not Ga4Sha256
            or type(self.fixture_length) is not Ga4FixtureLength
            or type(self.response_digest) is not Ga4Sha256
            or type(self.successful) is not bool
        ):
            fail_ga4()


FIXTURE_BINDINGS = (
    Ga4FixtureBinding(
        Ga4RecordingId("baseline"),
        Ga4Sha256("2c4082c31a1ca285bd04cc2bec74eeb02cad7a41753fb9eb7a5c371cc3620aab"),
        Ga4FixtureLength(11_595),
        Ga4Sha256("17d641615b48a97ee681308c95b844019361ae61e20c66edb633e8c41a161584"),
        True,
    ),
    Ga4FixtureBinding(
        Ga4RecordingId("late-revised"),
        Ga4Sha256("d8c6dbc6fe5a7509a39c40cf8e60dfe867d6bd775ae097f9961e5c81d6a88e1a"),
        Ga4FixtureLength(11_657),
        Ga4Sha256("90678fce8210799dc2aeecb091d41aa08d58de2c473c784535d47f1661241e09"),
        True,
    ),
    Ga4FixtureBinding(
        Ga4RecordingId("provider-error-429"),
        Ga4Sha256("b160fa1996e7579eebe362938313da2afb60530904679aa566a5d8dde7dd2fcc"),
        Ga4FixtureLength(3_054),
        Ga4Sha256("d32156c4a9f26d5d57bde7aab4dc604d3843cd3da503d16af340e93be1879495"),
        False,
    ),
)


def fixture_binding(recording_id: Ga4RecordingId) -> Ga4FixtureBinding:
    if type(recording_id) is not Ga4RecordingId:
        fail_ga4()
    for binding in FIXTURE_BINDINGS:
        if binding.recording_id == recording_id:
            return binding
    fail_ga4()


@dataclass(frozen=True, slots=True, repr=False)
class Ga4RecordedImportCommand(_RedactedValue):
    recording_id: Ga4RecordingId
    fixture_digest: Ga4Sha256
    fixture_length: Ga4FixtureLength
    site_id: UUID
    date_from: date
    date_to: date
    dimensions: tuple[str, ...]
    metrics: tuple[str, ...]
    force_reimport: bool | None
    request: Ga4RecordedRequest

    def __post_init__(self) -> None:
        if (
            type(self.recording_id) is not Ga4RecordingId
            or type(self.fixture_digest) is not Ga4Sha256
            or type(self.fixture_length) is not Ga4FixtureLength
            or type(self.site_id) is not UUID
            or self.site_id != SYNTHETIC_SITE_ID
            or type(self.date_from) is not date
            or self.date_from != date(2026, 7, 1)
            or type(self.date_to) is not date
            or self.date_to != date(2026, 7, 2)
            or self.dimensions != EXACT_DIMENSIONS
            or self.metrics != EXACT_METRICS
            or not (
                self.force_reimport is None
                or type(self.force_reimport) is bool
                and self.force_reimport is False
            )
            or type(self.request) is not Ga4RecordedRequest
            or self.request.date_ranges[0].start_date != self.date_from
            or self.request.date_ranges[0].end_date != self.date_to
            or self.request.dimensions != self.dimensions
            or self.request.metrics != self.metrics
        ):
            fail_ga4()
        binding = fixture_binding(self.recording_id)
        if (
            self.fixture_digest != binding.fixture_digest
            or self.fixture_length != binding.fixture_length
        ):
            fail_ga4(Ga4FailureCode.REQUEST_MISMATCH)


@dataclass(frozen=True, slots=True, repr=False)
class Ga4QuotaCounter(_RedactedValue):
    name: str
    consumed: int
    remaining: int

    def __post_init__(self) -> None:
        allowed = {
            "concurrentRequests",
            "potentiallyThresholdedRequestsPerHour",
            "serverErrorsPerProjectPerHour",
            "tokensPerDay",
            "tokensPerHour",
            "tokensPerProjectPerHour",
        }
        if (
            type(self.name) is not str
            or self.name not in allowed
            or type(self.consumed) is not int
            or not 0 <= self.consumed <= _MAX_EXACT_INTEGER
            or type(self.remaining) is not int
            or not 0 <= self.remaining <= _MAX_EXACT_INTEGER
        ):
            fail_ga4(Ga4FailureCode.FIXTURE_DOCUMENT_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class Ga4PropertyConfigSnapshot(_RedactedValue):
    property_resource: str
    reporting_identity: Ga4ReportingIdentity
    reporting_identity_response_digest: Ga4Sha256
    reporting_identity_retrieved_at: Ga4UtcTimestamp
    currency_code: str
    time_zone: str
    subject_to_thresholding: bool
    data_loss_from_other_row: bool
    empty_reason: str
    sampling_metadata: tuple[tuple[str, str], ...]
    quota: tuple[Ga4QuotaCounter, ...]

    def __post_init__(self) -> None:
        if (
            self.property_resource != SYNTHETIC_PROPERTY_RESOURCE
            or self.reporting_identity is not Ga4ReportingIdentity.DEVICE_BASED
            or self.reporting_identity_response_digest
            != Ga4Sha256(REPORTING_IDENTITY_SHA256)
            or type(self.reporting_identity_retrieved_at) is not Ga4UtcTimestamp
            or self.currency_code != "JPY"
            or self.time_zone != "Asia/Tokyo"
            or type(self.subject_to_thresholding) is not bool
            or type(self.data_loss_from_other_row) is not bool
            or type(self.empty_reason) is not str
            or type(self.sampling_metadata) is not tuple
            or any(
                type(item) is not tuple
                or len(item) != 2
                or any(type(value) is not str for value in item)
                for item in self.sampling_metadata
            )
            or type(self.quota) is not tuple
            or len(self.quota) != 6
            or any(type(item) is not Ga4QuotaCounter for item in self.quota)
            or len({item.name for item in self.quota}) != len(self.quota)
        ):
            fail_ga4(Ga4FailureCode.FIXTURE_DOCUMENT_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class Ga4MetricRow(_RedactedValue):
    site_id: UUID
    property_id: str
    date_from: date
    date_to: date
    date_range_index: int
    dimensions: tuple[str, ...]
    metrics: tuple[str, ...]
    dimension_values: tuple[str, ...]
    metric_values: tuple[str, ...]
    imported_at: Ga4UtcTimestamp
    reporting_identity: Ga4ReportingIdentity
    thresholding_applied: bool
    source_request_sha256: Ga4Sha256

    def __post_init__(self) -> None:
        if (
            type(self.site_id) is not UUID
            or self.site_id != SYNTHETIC_SITE_ID
            or self.property_id != SYNTHETIC_PROPERTY_ID
            or type(self.date_from) is not date
            or self.date_from != date(2026, 7, 1)
            or type(self.date_to) is not date
            or self.date_to != date(2026, 7, 2)
            or type(self.date_range_index) is not int
            or self.date_range_index != 0
            or self.dimensions != EXACT_DIMENSIONS
            or self.metrics != EXACT_METRICS
            or type(self.dimension_values) is not tuple
            or len(self.dimension_values) != len(self.dimensions)
            or any(type(value) is not str for value in self.dimension_values)
            or type(self.metric_values) is not tuple
            or len(self.metric_values) != len(self.metrics)
            or any(
                type(value) is not str or _METRIC_VALUE.fullmatch(value) is None
                for value in self.metric_values
            )
            or type(self.imported_at) is not Ga4UtcTimestamp
            or self.reporting_identity is not Ga4ReportingIdentity.DEVICE_BASED
            or type(self.thresholding_applied) is not bool
            or self.source_request_sha256 != Ga4Sha256(INTERNAL_REQUEST_SHA256)
        ):
            fail_ga4(Ga4FailureCode.FIXTURE_DOCUMENT_INVALID)
        if (
            _GA4_DATE.fullmatch(self.dimension_values[0]) is None
            or _SYNTHETIC_PATH.fullmatch(self.dimension_values[1]) is None
            or _DEVICE.fullmatch(self.dimension_values[2]) is None
        ):
            fail_ga4(Ga4FailureCode.FIXTURE_DOCUMENT_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class Ga4RecordedExchange(_RedactedValue):
    recording_id: Ga4RecordingId
    fixture_digest: Ga4Sha256
    fixture_length: Ga4FixtureLength
    request: Ga4RecordedRequest
    response_digest: Ga4Sha256
    run_report_retrieved_at: Ga4UtcTimestamp
    recorded_at: Ga4UtcTimestamp
    outcome: Ga4RecordedOutcome
    rows: tuple[Ga4MetricRow, ...]
    provider_row_count: int | None
    returned_row_count: int
    row_count_independent_of_pagination: bool | None
    configuration: Ga4PropertyConfigSnapshot | None
    http_status: int | None

    def __post_init__(self) -> None:
        if (
            type(self.recording_id) is not Ga4RecordingId
            or type(self.fixture_digest) is not Ga4Sha256
            or type(self.fixture_length) is not Ga4FixtureLength
            or type(self.request) is not Ga4RecordedRequest
            or type(self.response_digest) is not Ga4Sha256
            or type(self.run_report_retrieved_at) is not Ga4UtcTimestamp
            or type(self.recorded_at) is not Ga4UtcTimestamp
            or type(self.outcome) is not Ga4RecordedOutcome
            or type(self.rows) is not tuple
            or any(type(row) is not Ga4MetricRow for row in self.rows)
            or type(self.returned_row_count) is not int
            or self.returned_row_count != len(self.rows)
        ):
            fail_ga4(Ga4FailureCode.RECORDED_RESULT_MISMATCH)
        binding = fixture_binding(self.recording_id)
        if (
            self.fixture_digest != binding.fixture_digest
            or self.fixture_length != binding.fixture_length
            or self.response_digest != binding.response_digest
            or any(
                row.imported_at != self.recorded_at
                or row.source_request_sha256 != self.request.internal_sha256
                for row in self.rows
            )
        ):
            fail_ga4(Ga4FailureCode.RECORDED_RESULT_MISMATCH)
        if binding.successful:
            if (
                self.outcome is not Ga4RecordedOutcome.RECORDED_SUCCESS
                or len(self.rows) != 2
                or type(self.provider_row_count) is not int
                or self.provider_row_count != 3
                or self.row_count_independent_of_pagination is not True
                or type(self.configuration) is not Ga4PropertyConfigSnapshot
                or self.http_status is not None
            ):
                fail_ga4(Ga4FailureCode.RECORDED_RESULT_MISMATCH)
        elif (
            self.outcome is not Ga4RecordedOutcome.RECORDED_RESOURCE_EXHAUSTED
            or self.rows
            or self.provider_row_count is not None
            or self.row_count_independent_of_pagination is not None
            or self.configuration is not None
            or type(self.http_status) is not int
            or self.http_status != 429
        ):
            fail_ga4(Ga4FailureCode.RECORDED_RESULT_MISMATCH)


@dataclass(frozen=True, slots=True, repr=False)
class Ga4ImportResult(_RedactedValue):
    exchange: Ga4RecordedExchange
    execution_mode: Ga4BoundaryStatus
    tracking: Ga4BoundaryStatus
    credentials: Ga4BoundaryStatus
    provider_execution: Ga4BoundaryStatus
    property_configuration: Ga4BoundaryStatus
    persistence: Ga4BoundaryStatus
    job_dispatch: Ga4BoundaryStatus
    event_publication: Ga4BoundaryStatus
    supersession: Ga4BoundaryStatus
    formal_tst_030: Ga4BoundaryStatus
    decision: Ga4BoundaryStatus

    def __post_init__(self) -> None:
        expected_configuration = (
            Ga4BoundaryStatus.IN_FIXTURE_ONLY
            if self.exchange.outcome is Ga4RecordedOutcome.RECORDED_SUCCESS
            else Ga4BoundaryStatus.NOT_CAPTURED_AFTER_ERROR
        )
        if (
            type(self.exchange) is not Ga4RecordedExchange
            or self.execution_mode is not Ga4BoundaryStatus.RECORDED_FIXTURE_ONLY
            or self.tracking is not Ga4BoundaryStatus.DISABLED_OD_012
            or self.credentials is not Ga4BoundaryStatus.NOT_USED
            or self.provider_execution is not Ga4BoundaryStatus.NOT_EXECUTED
            or self.property_configuration is not expected_configuration
            or self.persistence is not Ga4BoundaryStatus.NOT_EXECUTED
            or self.job_dispatch is not Ga4BoundaryStatus.NOT_EXECUTED
            or self.event_publication is not Ga4BoundaryStatus.NOT_EXECUTED
            or self.supersession is not Ga4BoundaryStatus.NOT_DEFINED
            or self.formal_tst_030 is not Ga4BoundaryStatus.NOT_EXECUTED
            or self.decision is not Ga4BoundaryStatus.NOT_READY
        ):
            fail_ga4()


JsonNumber: TypeAlias = int | float


def exact_nonnegative_number(value: object) -> JsonNumber:
    if type(value) not in {int, float}:
        fail_ga4(Ga4FailureCode.FIXTURE_DOCUMENT_INVALID)
    result = cast(JsonNumber, value)
    if not math.isfinite(result) or result < 0:
        fail_ga4(Ga4FailureCode.FIXTURE_DOCUMENT_INVALID)
    return result


__all__ = [
    "EXACT_DIMENSIONS",
    "EXACT_METRICS",
    "FIXTURE_BINDINGS",
    "INTERNAL_REQUEST_SHA256",
    "REPORTING_IDENTITY_SHA256",
    "SYNTHETIC_PROPERTY_ID",
    "SYNTHETIC_PROPERTY_RESOURCE",
    "SYNTHETIC_SITE_ID",
    "WIRE_REQUEST_SHA256",
    "Ga4BoundaryStatus",
    "Ga4DateRange",
    "Ga4Failure",
    "Ga4FailureCode",
    "Ga4FixtureBinding",
    "Ga4FixtureLength",
    "Ga4ImportResult",
    "Ga4MetricRow",
    "Ga4PropertyConfigSnapshot",
    "Ga4QuotaCounter",
    "Ga4RecordedExchange",
    "Ga4RecordedImportCommand",
    "Ga4RecordedOutcome",
    "Ga4RecordedRequest",
    "Ga4RecordingId",
    "Ga4ReportingIdentity",
    "Ga4Sha256",
    "Ga4UtcTimestamp",
    "exact_nonnegative_number",
    "fail_ga4",
    "fixture_binding",
]

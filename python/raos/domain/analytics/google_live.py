"""Live Google analytics value objects shared by provider and persistence seams.

The recorded ST-1203/ST-1204 domains intentionally remain closed.  This module
is an additive, non-recorded contract for owner-authorized, read-only provider
imports.  Raw Search Console queries are deliberately excluded from reprs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
import hashlib
import json
import math
import re
from typing import NoReturn
from urllib.parse import urlsplit
from uuid import UUID


GSC_READONLY_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
GA4_READONLY_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
GSC_DIMENSIONS = ("date", "query", "page", "country", "device")
GA4_BASELINE_DIMENSIONS = ("date", "pagePath", "eventName", "deviceCategory")
GA4_BASELINE_METRICS = ("eventCount", "sessions", "totalUsers")

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_PROPERTY_ID = re.compile(r"[1-9][0-9]{0,19}\Z", re.ASCII)
_SC_DOMAIN = re.compile(
    r"sc-domain:(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?\Z",
    re.ASCII,
)
_COUNTRY = re.compile(r"[a-z]{3}\Z", re.ASCII)
_DEVICE = re.compile(r"(?:MOBILE|DESKTOP|TABLET)", re.ASCII)
_DIMENSION_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_:]{0,127}\Z", re.ASCII)
_METRIC_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,127}\Z", re.ASCII)
_MAX_ROWS = 2_000_000


class GoogleProviderFailureCode(StrEnum):
    INVALID_ARGUMENT = "GOOGLE_LIVE_INVALID_ARGUMENT"
    OWNER_PRIVATE_LAYOUT_INVALID = "GOOGLE_LIVE_OWNER_PRIVATE_LAYOUT_INVALID"
    CREDENTIAL_INVALID = "GOOGLE_LIVE_CREDENTIAL_INVALID"
    AUTHENTICATION_FAILED = "GOOGLE_LIVE_AUTHENTICATION_FAILED"
    AUTHORIZATION_FAILED = "GOOGLE_LIVE_AUTHORIZATION_FAILED"
    RESOURCE_NOT_FOUND = "GOOGLE_LIVE_RESOURCE_NOT_FOUND"
    RATE_LIMITED = "GOOGLE_LIVE_RATE_LIMITED"
    PROVIDER_UNAVAILABLE = "GOOGLE_LIVE_PROVIDER_UNAVAILABLE"
    PROVIDER_RESPONSE_INVALID = "GOOGLE_LIVE_PROVIDER_RESPONSE_INVALID"
    PERSISTENCE_FAILED = "GOOGLE_LIVE_PERSISTENCE_FAILED"


class GoogleProviderFailure(RuntimeError):
    """Sanitized live-provider failure; never includes response or credentials."""

    __slots__ = ("code", "retryable")

    def __init__(self, code: GoogleProviderFailureCode, *, retryable: bool = False):
        if type(code) is not GoogleProviderFailureCode or type(retryable) is not bool:
            raise TypeError("invalid Google provider failure")
        self.code = code
        self.retryable = retryable
        super().__init__(code.value)

    def __repr__(self) -> str:
        return (
            f"GoogleProviderFailure(code={self.code.value!r}, "
            f"retryable={self.retryable!r})"
        )


def fail_google(
    code: GoogleProviderFailureCode = GoogleProviderFailureCode.INVALID_ARGUMENT,
    *,
    retryable: bool = False,
) -> NoReturn:
    raise GoogleProviderFailure(code, retryable=retryable) from None


def canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except TypeError, ValueError:
        fail_google()


def sha256_hex(value: bytes) -> str:
    if type(value) is not bytes:
        fail_google()
    return hashlib.sha256(value).hexdigest()


def _valid_sha256(value: object) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _valid_utc(value: object) -> bool:
    return type(value) is datetime and value.tzinfo is timezone.utc and value.fold == 0


def _valid_https_url(value: object) -> bool:
    if type(value) is not str or not 1 <= len(value) <= 4096:
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and parsed.fragment == ""
    )


@dataclass(frozen=True, slots=True, repr=False)
class AnalyticsSiteBinding:
    provider: str
    site_id: UUID
    resource: str
    credential_path: str
    service_account_email_sha256: str
    scopes: tuple[str, ...]

    def __post_init__(self) -> None:
        expected_scope = {
            "GSC": GSC_READONLY_SCOPE,
            "GA4": GA4_READONLY_SCOPE,
        }.get(self.provider)
        resource_valid = (
            self.provider == "GSC"
            and (
                _SC_DOMAIN.fullmatch(self.resource) is not None
                or _valid_https_url(self.resource)
            )
        ) or (
            self.provider == "GA4"
            and self.resource.startswith("properties/")
            and _PROPERTY_ID.fullmatch(self.resource.removeprefix("properties/"))
            is not None
        )
        if (
            expected_scope is None
            or type(self.site_id) is not UUID
            or not resource_valid
            or type(self.credential_path) is not str
            or not self.credential_path.startswith("/")
            or not _valid_sha256(self.service_account_email_sha256)
            or self.scopes != (expected_scope,)
        ):
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)

    @property
    def property_id(self) -> str:
        if self.provider != "GA4":
            fail_google()
        return self.resource.removeprefix("properties/")


@dataclass(frozen=True, slots=True)
class SearchConsoleLiveQuery:
    site_id: UUID
    site_url: str
    date_from: date
    date_to: date
    dimensions: tuple[str, ...] = GSC_DIMENSIONS
    row_limit: int = 25_000

    def __post_init__(self) -> None:
        if (
            type(self.site_id) is not UUID
            or type(self.site_url) is not str
            or not (
                _SC_DOMAIN.fullmatch(self.site_url) is not None
                or _valid_https_url(self.site_url)
            )
            or type(self.date_from) is not date
            or type(self.date_to) is not date
            or self.date_to < self.date_from
            or self.dimensions != GSC_DIMENSIONS
            or type(self.row_limit) is not int
            or not 1 <= self.row_limit <= 25_000
        ):
            fail_google()

    def logical_request(self) -> dict[str, object]:
        return {
            "aggregationType": "auto",
            "dataState": "final",
            "dimensions": list(self.dimensions),
            "endDate": self.date_to.isoformat(),
            "rowLimit": self.row_limit,
            "siteUrl": self.site_url,
            "startDate": self.date_from.isoformat(),
            "type": "web",
        }

    @property
    def request_sha256(self) -> str:
        return sha256_hex(canonical_json_bytes(self.logical_request()))


@dataclass(frozen=True, slots=True, repr=False)
class SearchConsoleObservation:
    metric_date: date
    query_text: str
    page_url: str
    country_code: str
    device: str
    clicks: int
    impressions: int
    ctr: float
    average_position: float
    dimension_key_sha256: str
    source_request_sha256: str

    def __post_init__(self) -> None:
        expected_key = sha256_hex(
            canonical_json_bytes(
                {
                    "country": self.country_code,
                    "date": self.metric_date.isoformat()
                    if type(self.metric_date) is date
                    else "",
                    "device": self.device,
                    "page": self.page_url,
                    "query": self.query_text,
                }
            )
        )
        if (
            type(self.metric_date) is not date
            or type(self.query_text) is not str
            or len(self.query_text) > 4096
            or not _valid_https_url(self.page_url)
            or type(self.country_code) is not str
            or _COUNTRY.fullmatch(self.country_code) is None
            or type(self.device) is not str
            or _DEVICE.fullmatch(self.device) is None
            or type(self.clicks) is not int
            or type(self.impressions) is not int
            or not 0 <= self.clicks <= self.impressions
            or type(self.ctr) is not float
            or not math.isfinite(self.ctr)
            or not 0.0 <= self.ctr <= 1.0
            or type(self.average_position) is not float
            or not math.isfinite(self.average_position)
            or self.average_position < 0.0
            or self.dimension_key_sha256 != expected_key
            or not _valid_sha256(self.source_request_sha256)
        ):
            fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class SearchConsoleImportBatch:
    site_id: UUID
    site_url: str
    date_from: date
    date_to: date
    request_sha256: str
    page_request_sha256s: tuple[str, ...]
    rows: tuple[SearchConsoleObservation, ...]
    retrieved_at: datetime
    provider_row_count: int
    rows_not_guaranteed_complete: bool = True

    def __post_init__(self) -> None:
        if (
            type(self.site_id) is not UUID
            or type(self.site_url) is not str
            or type(self.date_from) is not date
            or type(self.date_to) is not date
            or self.date_to < self.date_from
            or not _valid_sha256(self.request_sha256)
            or not self.page_request_sha256s
            or not all(_valid_sha256(item) for item in self.page_request_sha256s)
            or type(self.rows) is not tuple
            or not all(type(item) is SearchConsoleObservation for item in self.rows)
            or not _valid_utc(self.retrieved_at)
            or type(self.provider_row_count) is not int
            or self.provider_row_count != len(self.rows)
            or self.provider_row_count > _MAX_ROWS
            or self.rows_not_guaranteed_complete is not True
        ):
            fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)


@dataclass(frozen=True, slots=True)
class Ga4LiveQuery:
    site_id: UUID
    property_id: str
    date_from: date
    date_to: date
    dimensions: tuple[str, ...] = GA4_BASELINE_DIMENSIONS
    metrics: tuple[str, ...] = GA4_BASELINE_METRICS
    page_limit: int = 100_000

    def __post_init__(self) -> None:
        if (
            type(self.site_id) is not UUID
            or type(self.property_id) is not str
            or _PROPERTY_ID.fullmatch(self.property_id) is None
            or type(self.date_from) is not date
            or type(self.date_to) is not date
            or self.date_to < self.date_from
            or type(self.dimensions) is not tuple
            or not 1 <= len(self.dimensions) <= 9
            or self.dimensions[0] != "date"
            or len(set(self.dimensions)) != len(self.dimensions)
            or not all(
                type(item) is str and _DIMENSION_NAME.fullmatch(item)
                for item in self.dimensions
            )
            or type(self.metrics) is not tuple
            or not 1 <= len(self.metrics) <= 10
            or len(set(self.metrics)) != len(self.metrics)
            or not all(
                type(item) is str and _METRIC_NAME.fullmatch(item)
                for item in self.metrics
            )
            or type(self.page_limit) is not int
            or not 1 <= self.page_limit <= 250_000
        ):
            fail_google()

    def logical_request(self) -> dict[str, object]:
        return {
            "dateRanges": [
                {
                    "endDate": self.date_to.isoformat(),
                    "startDate": self.date_from.isoformat(),
                }
            ],
            "dimensions": [{"name": item} for item in self.dimensions],
            "keepEmptyRows": False,
            "metrics": [{"name": item} for item in self.metrics],
            "property": f"properties/{self.property_id}",
        }

    @property
    def request_sha256(self) -> str:
        return sha256_hex(canonical_json_bytes(self.logical_request()))


@dataclass(frozen=True, slots=True, repr=False)
class Ga4Observation:
    metric_date: date
    dimensions: tuple[tuple[str, str], ...]
    metrics: tuple[tuple[str, str], ...]
    grain_key_sha256: str
    source_request_sha256: str
    is_thresholded: bool

    def __post_init__(self) -> None:
        dimensions_valid = type(self.dimensions) is tuple and all(
            type(item) is tuple
            and len(item) == 2
            and type(item[0]) is str
            and _DIMENSION_NAME.fullmatch(item[0]) is not None
            and type(item[1]) is str
            and len(item[1]) <= 4096
            for item in self.dimensions
        )
        metrics_valid = type(self.metrics) is tuple and all(
            type(item) is tuple
            and len(item) == 2
            and type(item[0]) is str
            and _METRIC_NAME.fullmatch(item[0]) is not None
            and _nonnegative_decimal(item[1])
            for item in self.metrics
        )
        expected_grain = sha256_hex(
            canonical_json_bytes(
                {
                    "date": self.metric_date.isoformat()
                    if type(self.metric_date) is date
                    else "",
                    "dimensions": dict(self.dimensions) if dimensions_valid else {},
                }
            )
        )
        if (
            type(self.metric_date) is not date
            or not dimensions_valid
            or not metrics_valid
            or len({item[0] for item in self.dimensions}) != len(self.dimensions)
            or len({item[0] for item in self.metrics}) != len(self.metrics)
            or self.grain_key_sha256 != expected_grain
            or not _valid_sha256(self.source_request_sha256)
            or type(self.is_thresholded) is not bool
        ):
            fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)


def _nonnegative_decimal(value: object) -> bool:
    if type(value) is not str or not value or len(value) > 128:
        return False
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return False
    return parsed.is_finite() and parsed >= 0


@dataclass(frozen=True, slots=True, repr=False)
class Ga4PropertyConfigSnapshot:
    property_id: str
    property_resource: str
    display_name: str
    time_zone: str
    currency_code: str
    reporting_identity: str
    retrieved_at: datetime
    property_response_sha256: str
    reporting_identity_response_sha256: str
    snapshot_sha256: str

    def __post_init__(self) -> None:
        expected_snapshot = sha256_hex(
            canonical_json_bytes(
                {
                    "currency_code": self.currency_code,
                    "display_name": self.display_name,
                    "property_resource": self.property_resource,
                    "reporting_identity": self.reporting_identity,
                    "time_zone": self.time_zone,
                }
            )
        )
        if (
            type(self.property_id) is not str
            or _PROPERTY_ID.fullmatch(self.property_id) is None
            or self.property_resource != f"properties/{self.property_id}"
            or type(self.display_name) is not str
            or not self.display_name
            or len(self.display_name) > 256
            or type(self.time_zone) is not str
            or not self.time_zone
            or len(self.time_zone) > 64
            or type(self.currency_code) is not str
            or re.fullmatch(r"[A-Z]{3}", self.currency_code) is None
            or self.reporting_identity not in {"DEVICE_BASED", "BLENDED", "OBSERVED"}
            or not _valid_utc(self.retrieved_at)
            or not _valid_sha256(self.property_response_sha256)
            or not _valid_sha256(self.reporting_identity_response_sha256)
            or self.snapshot_sha256 != expected_snapshot
        ):
            fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class Ga4ImportBatch:
    site_id: UUID
    property_id: str
    date_from: date
    date_to: date
    dimensions: tuple[str, ...]
    metrics: tuple[str, ...]
    request_sha256: str
    page_request_sha256s: tuple[str, ...]
    rows: tuple[Ga4Observation, ...]
    configuration: Ga4PropertyConfigSnapshot
    retrieved_at: datetime
    provider_row_count: int
    subject_to_thresholding: bool
    data_loss_from_other_row: bool

    def __post_init__(self) -> None:
        if (
            type(self.site_id) is not UUID
            or type(self.property_id) is not str
            or _PROPERTY_ID.fullmatch(self.property_id) is None
            or type(self.date_from) is not date
            or type(self.date_to) is not date
            or self.date_to < self.date_from
            or type(self.dimensions) is not tuple
            or type(self.metrics) is not tuple
            or not _valid_sha256(self.request_sha256)
            or not self.page_request_sha256s
            or not all(_valid_sha256(item) for item in self.page_request_sha256s)
            or type(self.rows) is not tuple
            or not all(type(item) is Ga4Observation for item in self.rows)
            or type(self.configuration) is not Ga4PropertyConfigSnapshot
            or self.configuration.property_id != self.property_id
            or not _valid_utc(self.retrieved_at)
            or type(self.provider_row_count) is not int
            or self.provider_row_count != len(self.rows)
            or self.provider_row_count > _MAX_ROWS
            or type(self.subject_to_thresholding) is not bool
            or type(self.data_loss_from_other_row) is not bool
        ):
            fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)


@dataclass(frozen=True, slots=True)
class GoogleImportExecutionContext:
    display_id: str
    site_id: UUID
    ops_job_id: UUID
    started_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.display_id) is not str
            or re.fullmatch(r"AIR-[A-Z0-9-]{3,60}", self.display_id) is None
            or type(self.site_id) is not UUID
            or type(self.ops_job_id) is not UUID
            or not _valid_utc(self.started_at)
        ):
            fail_google()


@dataclass(frozen=True, slots=True)
class GoogleImportCommitResult:
    import_run_id: UUID
    inserted_count: int
    unchanged_count: int
    superseded_count: int
    completed_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.import_run_id) is not UUID
            or any(
                type(item) is not int or item < 0
                for item in (
                    self.inserted_count,
                    self.unchanged_count,
                    self.superseded_count,
                )
            )
            or not _valid_utc(self.completed_at)
        ):
            fail_google(GoogleProviderFailureCode.PERSISTENCE_FAILED)


__all__ = [
    "AnalyticsSiteBinding",
    "GA4_BASELINE_DIMENSIONS",
    "GA4_BASELINE_METRICS",
    "GA4_READONLY_SCOPE",
    "GSC_DIMENSIONS",
    "GSC_READONLY_SCOPE",
    "Ga4ImportBatch",
    "Ga4LiveQuery",
    "Ga4Observation",
    "Ga4PropertyConfigSnapshot",
    "GoogleImportCommitResult",
    "GoogleImportExecutionContext",
    "GoogleProviderFailure",
    "GoogleProviderFailureCode",
    "SearchConsoleImportBatch",
    "SearchConsoleLiveQuery",
    "SearchConsoleObservation",
    "canonical_json_bytes",
    "fail_google",
    "sha256_hex",
]

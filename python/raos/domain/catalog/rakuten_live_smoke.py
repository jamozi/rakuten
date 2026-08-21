"""Closed local one-call Rakuten live-smoke values for ST-0505."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
import re
from typing import NoReturn, SupportsIndex, cast
from urllib.parse import urlsplit

from raos.domain.catalog.rakuten_item_search_live_request_v1 import (
    LIVE_ITEM_SEARCH_ELEMENTS_V1,
    LiveItemSearchSortV1,
    RakutenItemSearchLiveRequestV1,
)


RAKUTEN_LIVE_SMOKE_API_VERSION = "2026-07-01"
RAKUTEN_LIVE_SMOKE_ENDPOINT_ID = "RAKUTEN_ICHIBA_ITEM_SEARCH_20260701"
RAKUTEN_LIVE_SMOKE_HOST = "openapi.rakuten.co.jp"
RAKUTEN_LIVE_SMOKE_PATH = "/ichibams/api/IchibaItem/Search/20260701"
RAKUTEN_LIVE_SMOKE_ACCEPT = "application/json"
RAKUTEN_LIVE_SMOKE_USER_AGENT = "RAOS-ST-0505-live-smoke/1"
RAKUTEN_LIVE_SMOKE_ACCESS_HEADER = "access" + "Key"
RAKUTEN_LIVE_SMOKE_REPORT_SCHEMA = "RAOS_ST0505_RAKUTEN_LIVE_SMOKE_REPORT_V2"
RAKUTEN_LIVE_SMOKE_MINIMAL_ELEMENTS = (
    "count",
    "page",
    "first",
    "last",
    "hits",
    "pageCount",
    "affiliateUrl",
)
_REPORT_KEYS = (
    "schema",
    "version",
    "run_id",
    "started_at",
    "finished_at",
    "result",
    "diagnostic_code",
    "api_version",
    "endpoint_id",
    "request_policy_fingerprint",
    "http_status",
    "body_byte_count",
    "response_sha256",
    "auth_classification",
    "schema_classification",
    "rate_classification",
    "affiliate_url_present",
    "request_count",
    "retry_count",
    "pagination_count",
    "formal_tst_016",
    "staging",
    "production",
)
_RUN_ID = re.compile(r"[0-9]{8}T[0-9]{6}\.[0-9]{6}Z-[0-9a-f]{32}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_CONTENT_TYPE = re.compile(
    r"application/json(?:[ \t]*;[ \t]*charset=(?:utf-8|UTF-8))?\Z", re.ASCII
)
_REDACTED = "<redacted-rakuten-live-smoke>"


class RakutenLiveSmokeDiagnosticCode(StrEnum):
    LIVE_SMOKE_PASS = "LIVE_SMOKE_PASS"
    CREDENTIAL_STORE_INVALID = "CREDENTIAL_STORE_INVALID"
    TLS_ENVIRONMENT_INVALID = "TLS_ENVIRONMENT_INVALID"
    TLS_CONTEXT_INVALID = "TLS_CONTEXT_INVALID"
    DNS_FAILED = "DNS_FAILED"
    TLS_FAILED = "TLS_FAILED"
    TIMEOUT = "TIMEOUT"
    CONNECTION_FAILED = "CONNECTION_FAILED"
    REQUEST_AMBIGUOUS = "REQUEST_AMBIGUOUS"
    REQUEST_ALREADY_ATTEMPTED = "REQUEST_ALREADY_ATTEMPTED"
    HTTP_REDIRECT_REJECTED = "HTTP_REDIRECT_REJECTED"
    HTTP_400 = "HTTP_400"
    HTTP_401 = "HTTP_401"
    HTTP_403 = "HTTP_403"
    HTTP_404 = "HTTP_404"
    HTTP_429 = "HTTP_429"
    HTTP_500 = "HTTP_500"
    HTTP_503 = "HTTP_503"
    HTTP_STATUS_UNEXPECTED = "HTTP_STATUS_UNEXPECTED"
    RESPONSE_CONTENT_TYPE_INVALID = "RESPONSE_CONTENT_TYPE_INVALID"
    RESPONSE_OVERSIZED = "RESPONSE_OVERSIZED"
    RESPONSE_ENCODING_INVALID = "RESPONSE_ENCODING_INVALID"
    RESPONSE_JSON_INVALID = "RESPONSE_JSON_INVALID"
    RESPONSE_JSON_DUPLICATE_KEY = "RESPONSE_JSON_DUPLICATE_KEY"
    RESPONSE_JSON_NONFINITE = "RESPONSE_JSON_NONFINITE"
    RESPONSE_JSON_TREE_INVALID = "RESPONSE_JSON_TREE_INVALID"
    RESPONSE_SCHEMA_DRIFT = "RESPONSE_SCHEMA_DRIFT"
    AFFILIATE_URL_MISSING = "AFFILIATE_URL_MISSING"
    AFFILIATE_URL_INVALID = "AFFILIATE_URL_INVALID"
    REPORT_STORE_INVALID = "REPORT_STORE_INVALID"


class RakutenLiveSmokeResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class RakutenLiveSmokeAuthClassification(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    NOT_OBSERVED = "NOT_OBSERVED"


class RakutenLiveSmokeSchemaClassification(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"
    NOT_OBSERVED = "NOT_OBSERVED"


class RakutenLiveSmokeRateClassification(StrEnum):
    SINGLE_REQUEST_NOT_THROTTLED = "SINGLE_REQUEST_NOT_THROTTLED"
    THROTTLED = "THROTTLED"
    NOT_OBSERVED = "NOT_OBSERVED"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("Rakuten live-smoke serialization is disabled")


@dataclass(frozen=True, slots=True, repr=False)
class RakutenLiveSmokeFailure(RuntimeError):
    code: RakutenLiveSmokeDiagnosticCode
    http_status: int | None = None
    body_byte_count: int | None = None
    response_sha256: str | None = None
    request_count: int = 0
    auth: RakutenLiveSmokeAuthClassification = (
        RakutenLiveSmokeAuthClassification.NOT_OBSERVED
    )
    schema: RakutenLiveSmokeSchemaClassification = (
        RakutenLiveSmokeSchemaClassification.NOT_OBSERVED
    )
    rate: RakutenLiveSmokeRateClassification = (
        RakutenLiveSmokeRateClassification.NOT_OBSERVED
    )
    affiliate_url_present: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.code) is not RakutenLiveSmokeDiagnosticCode
            or (self.http_status is not None and type(self.http_status) is not int)
            or (
                self.body_byte_count is not None
                and (type(self.body_byte_count) is not int or self.body_byte_count < 0)
            )
            or (
                self.response_sha256 is not None
                and (
                    type(self.response_sha256) is not str
                    or _SHA256.fullmatch(self.response_sha256) is None
                    or self.body_byte_count is None
                    or self.request_count != 1
                )
            )
            or type(self.request_count) is not int
            or self.request_count not in {0, 1}
            or type(self.auth) is not RakutenLiveSmokeAuthClassification
            or type(self.schema) is not RakutenLiveSmokeSchemaClassification
            or type(self.rate) is not RakutenLiveSmokeRateClassification
            or type(self.affiliate_url_present) is not bool
        ):
            raise TypeError("invalid Rakuten live-smoke failure")
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"RakutenLiveSmokeFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("Rakuten live-smoke failure serialization is disabled")


def fail_rakuten_live_smoke(
    code: RakutenLiveSmokeDiagnosticCode,
    *,
    http_status: int | None = None,
    body_byte_count: int | None = None,
    response_sha256: str | None = None,
    request_count: int = 0,
    auth: RakutenLiveSmokeAuthClassification = (
        RakutenLiveSmokeAuthClassification.NOT_OBSERVED
    ),
    schema: RakutenLiveSmokeSchemaClassification = (
        RakutenLiveSmokeSchemaClassification.NOT_OBSERVED
    ),
    rate: RakutenLiveSmokeRateClassification = (
        RakutenLiveSmokeRateClassification.NOT_OBSERVED
    ),
    affiliate_url_present: bool = False,
) -> NoReturn:
    raise RakutenLiveSmokeFailure(
        code=code,
        http_status=http_status,
        body_byte_count=body_byte_count,
        response_sha256=response_sha256,
        request_count=request_count,
        auth=auth,
        schema=schema,
        rate=rate,
        affiliate_url_present=affiliate_url_present,
    ) from None


def fixed_rakuten_live_smoke_policy() -> RakutenItemSearchLiveRequestV1:
    """Bind the unchanged ST-0502 policy to the one ST-0505 request."""

    return RakutenItemSearchLiveRequestV1(
        api_version=RAKUTEN_LIVE_SMOKE_API_VERSION,
        format_version=2,
        keyword="収納",
        shop_code=None,
        item_code=None,
        genre_id=None,
        hits=1,
        page=1,
        sort=LiveItemSearchSortV1.STANDARD,
        elements=LIVE_ITEM_SEARCH_ELEMENTS_V1,
        min_price_jpy=None,
        max_price_jpy=None,
        or_flag=False,
        availability=True,
        postage_included_only=False,
        has_review_only=False,
        appoint_delivery_date_only=False,
        attribute_flag=False,
        genre_information_flag=False,
    )


def fixed_rakuten_live_smoke_request_fingerprint() -> str:
    """Bind the unchanged ST-0502 allowlist policy and narrower wire projection."""

    projection = {
        "access_key_transport": "HEADER_accessKey_ONLY",
        "authority": f"{RAKUTEN_LIVE_SMOKE_HOST}:443",
        "base_policy_fingerprint": fixed_rakuten_live_smoke_policy().fingerprint,
        "elements": list(RAKUTEN_LIVE_SMOKE_MINIMAL_ELEMENTS),
        "format": "json",
        "formatVersion": 2,
        "hits": 1,
        "headers": [
            {
                "header_name": "Accept",
                "fixed_value": RAKUTEN_LIVE_SMOKE_ACCEPT,
            },
            {
                "header_name": "User-Agent",
                "fixed_value": RAKUTEN_LIVE_SMOKE_USER_AGENT,
            },
            {
                "header_name": RAKUTEN_LIVE_SMOKE_ACCESS_HEADER,
                "value_source": "OWNER_PRIVATE_CREDENTIAL_RECORD",
            },
        ],
        "keyword": "収納",
        "method": "GET",
        "page": 1,
        "path": RAKUTEN_LIVE_SMOKE_PATH,
        "query_credentials": ["affiliateId", "applicationId"],
        "sort": "standard",
    }
    canonical = json.dumps(
        projection,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class RakutenLiveSmokeCredentials(_RedactedValue):
    _application_id: bytes
    _access_key: bytes
    _affiliate_id: bytes

    def __post_init__(self) -> None:
        for value, maximum in (
            (self._application_id, 256),
            (self._access_key, 4096),
            (self._affiliate_id, 256),
        ):
            if (
                type(value) is not bytes
                or not 1 <= len(value) <= maximum
                or any(byte < 0x21 or byte > 0x7E for byte in value)
            ):
                fail_rakuten_live_smoke(
                    RakutenLiveSmokeDiagnosticCode.CREDENTIAL_STORE_INVALID
                )

    def application_id_query_value(self) -> str:
        return self._application_id.decode("ascii", errors="strict")

    def access_key_header_value(self) -> str:
        return self._access_key.decode("ascii", errors="strict")

    def affiliate_id_query_value(self) -> str:
        return self._affiliate_id.decode("ascii", errors="strict")


@dataclass(frozen=True, slots=True, repr=False)
class RakutenLiveSmokeHttpResponse(_RedactedValue):
    status: int
    content_type: str | None
    body: bytes

    def __post_init__(self) -> None:
        if (
            type(self.status) is not int
            or not 100 <= self.status <= 599
            or (self.content_type is not None and type(self.content_type) is not str)
            or type(self.body) is not bytes
        ):
            fail_rakuten_live_smoke(
                RakutenLiveSmokeDiagnosticCode.REQUEST_AMBIGUOUS,
                request_count=1,
            )

    @property
    def response_sha256(self) -> str:
        """Return only the integrity digest of the complete bounded body."""

        return hashlib.sha256(self.body).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class RakutenLiveSmokeObservation(_RedactedValue):
    http_status: int
    body_byte_count: int
    response_sha256: str
    request_count: int
    affiliate_url_present: bool

    def __post_init__(self) -> None:
        if (
            self.http_status != 200
            or type(self.body_byte_count) is not int
            or self.body_byte_count < 2
            or type(self.response_sha256) is not str
            or _SHA256.fullmatch(self.response_sha256) is None
            or self.request_count != 1
            or self.affiliate_url_present is not True
        ):
            raise TypeError("invalid Rakuten live-smoke observation")


def _utc_text(value: datetime) -> str:
    if type(value) is not datetime or value.tzinfo is not timezone.utc or value.fold:
        raise TypeError("invalid UTC timestamp")
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True, repr=False)
class RakutenLiveSmokeReport(_RedactedValue):
    run_id: str
    started_at: datetime
    finished_at: datetime
    result: RakutenLiveSmokeResult
    diagnostic_code: RakutenLiveSmokeDiagnosticCode
    request_policy_fingerprint: str
    http_status: int | None
    body_byte_count: int | None
    response_sha256: str | None
    auth_classification: RakutenLiveSmokeAuthClassification
    schema_classification: RakutenLiveSmokeSchemaClassification
    rate_classification: RakutenLiveSmokeRateClassification
    affiliate_url_present: bool
    request_count: int

    def __post_init__(self) -> None:
        if (
            type(self.run_id) is not str
            or _RUN_ID.fullmatch(self.run_id) is None
            or type(self.result) is not RakutenLiveSmokeResult
            or type(self.diagnostic_code) is not RakutenLiveSmokeDiagnosticCode
            or type(self.request_policy_fingerprint) is not str
            or _SHA256.fullmatch(self.request_policy_fingerprint) is None
            or (self.http_status is not None and type(self.http_status) is not int)
            or (
                self.body_byte_count is not None
                and (type(self.body_byte_count) is not int or self.body_byte_count < 0)
            )
            or (
                self.response_sha256 is not None
                and (
                    type(self.response_sha256) is not str
                    or _SHA256.fullmatch(self.response_sha256) is None
                    or self.body_byte_count is None
                    or self.request_count != 1
                )
            )
            or type(self.auth_classification) is not RakutenLiveSmokeAuthClassification
            or type(self.schema_classification)
            is not RakutenLiveSmokeSchemaClassification
            or type(self.rate_classification) is not RakutenLiveSmokeRateClassification
            or type(self.affiliate_url_present) is not bool
            or type(self.request_count) is not int
            or self.request_count not in {0, 1}
            or self.finished_at < self.started_at
        ):
            raise TypeError("invalid Rakuten live-smoke report")
        _utc_text(self.started_at)
        _utc_text(self.finished_at)
        success = (
            self.result is RakutenLiveSmokeResult.PASS
            and self.diagnostic_code is RakutenLiveSmokeDiagnosticCode.LIVE_SMOKE_PASS
            and self.http_status == 200
            and self.response_sha256 is not None
            and self.auth_classification is RakutenLiveSmokeAuthClassification.ACCEPTED
            and self.schema_classification is RakutenLiveSmokeSchemaClassification.VALID
            and self.rate_classification
            is RakutenLiveSmokeRateClassification.SINGLE_REQUEST_NOT_THROTTLED
            and self.affiliate_url_present
            and self.request_count == 1
        )
        if (self.result is RakutenLiveSmokeResult.PASS) != success:
            raise TypeError("inconsistent Rakuten live-smoke report")

    @property
    def safe_mapping(self) -> dict[str, object]:
        value: dict[str, object] = {
            "schema": RAKUTEN_LIVE_SMOKE_REPORT_SCHEMA,
            "version": 2,
            "run_id": self.run_id,
            "started_at": _utc_text(self.started_at),
            "finished_at": _utc_text(self.finished_at),
            "result": self.result.value,
            "diagnostic_code": self.diagnostic_code.value,
            "api_version": RAKUTEN_LIVE_SMOKE_API_VERSION,
            "endpoint_id": RAKUTEN_LIVE_SMOKE_ENDPOINT_ID,
            "request_policy_fingerprint": self.request_policy_fingerprint,
            "http_status": self.http_status,
            "body_byte_count": self.body_byte_count,
            "response_sha256": self.response_sha256,
            "auth_classification": self.auth_classification.value,
            "schema_classification": self.schema_classification.value,
            "rate_classification": self.rate_classification.value,
            "affiliate_url_present": self.affiliate_url_present,
            "request_count": self.request_count,
            "retry_count": 0,
            "pagination_count": 0,
            "formal_tst_016": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        }
        if tuple(value) != _REPORT_KEYS:
            raise TypeError("invalid Rakuten live-smoke report mapping")
        return value

    @property
    def json_bytes(self) -> bytes:
        return (
            json.dumps(
                self.safe_mapping,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=False,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("ascii")


def valid_json_content_type(value: object) -> bool:
    return type(value) is str and _CONTENT_TYPE.fullmatch(value) is not None


def valid_affiliate_url(value: object) -> bool:
    if (
        type(value) is not str
        or not 1 <= len(value) <= 4096
        or any(ord(character) <= 32 or ord(character) == 127 for character in value)
        or "\\" in value
    ):
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.username is None
        and parsed.password is None
        and port in {None, 443}
        and not parsed.fragment
        and value.startswith("https://")
    )


def exact_report_mapping(value: object) -> bool:
    """Testable report boundary without accepting unknown serialized fields."""

    if type(value) is not dict:
        return False
    return tuple(cast(dict[str, object], value)) == _REPORT_KEYS


__all__ = [
    "RAKUTEN_LIVE_SMOKE_ACCEPT",
    "RAKUTEN_LIVE_SMOKE_API_VERSION",
    "RAKUTEN_LIVE_SMOKE_ENDPOINT_ID",
    "RAKUTEN_LIVE_SMOKE_HOST",
    "RAKUTEN_LIVE_SMOKE_MINIMAL_ELEMENTS",
    "RAKUTEN_LIVE_SMOKE_PATH",
    "RAKUTEN_LIVE_SMOKE_REPORT_SCHEMA",
    "RAKUTEN_LIVE_SMOKE_USER_AGENT",
    "RakutenLiveSmokeAuthClassification",
    "RakutenLiveSmokeCredentials",
    "RakutenLiveSmokeDiagnosticCode",
    "RakutenLiveSmokeFailure",
    "RakutenLiveSmokeHttpResponse",
    "RakutenLiveSmokeObservation",
    "RakutenLiveSmokeRateClassification",
    "RakutenLiveSmokeReport",
    "RakutenLiveSmokeResult",
    "RakutenLiveSmokeSchemaClassification",
    "exact_report_mapping",
    "fail_rakuten_live_smoke",
    "fixed_rakuten_live_smoke_policy",
    "fixed_rakuten_live_smoke_request_fingerprint",
    "valid_affiliate_url",
    "valid_json_content_type",
]

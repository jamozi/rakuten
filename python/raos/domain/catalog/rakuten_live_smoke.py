"""Closed values for the bounded ST-0505 Rakuten live smoke."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Final, NoReturn, SupportsIndex, final


RAKUTEN_API_DOCUMENTATION_URL: Final = (
    "https://webservice.rakuten.co.jp/documentation/ichiba-item-search"
)
RAKUTEN_API_DOCUMENTATION_RETRIEVED_ON: Final = "2026-08-18"
RAKUTEN_API_ORIGIN: Final = "https://openapi.rakuten.co.jp"
RAKUTEN_ITEM_SEARCH_PATH: Final = "/ichibams/api/IchibaItem/Search/20260701"
RAKUTEN_API_VERSION: Final = "2026-07-01"
RAKUTEN_APPLICATION_ID_ALIAS: Final = "rakuten_application_id"
RAKUTEN_ACCESS_KEY_ALIAS: Final = "rakuten_access_key"
STAGING_ENVIRONMENT: Final = "ENV-STAGING"
MAX_RESPONSE_BYTES: Final = 256 * 1024
MAX_JSON_DEPTH: Final = 32
MAX_JSON_NODES: Final = 20_000
NETWORK_TIMEOUT_SECONDS: Final = 5.0
MAX_GRANT_LIFETIME: Final = timedelta(minutes=15)

_SHA256: Final = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_HEADER_NAME: Final = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}\Z", re.ASCII)
_REDACTED: Final = "<redacted-rakuten-live-smoke>"
_REQUEST_ELEMENTS: Final = (
    "itemCode",
    "itemName",
    "itemPrice",
    "itemUrl",
    "shopCode",
)


class RakutenLiveSmokeFailureCode(str, Enum):
    """Stable, sanitized failures for the live-smoke boundary."""

    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    CREDENTIAL_UNAVAILABLE = "CREDENTIAL_UNAVAILABLE"
    TRANSPORT_FAILURE = "TRANSPORT_FAILURE"
    REDIRECT_FORBIDDEN = "REDIRECT_FORBIDDEN"
    AUTH_REJECTED = "AUTH_REJECTED"
    RATE_LIMITED = "RATE_LIMITED"
    REQUEST_REJECTED = "REQUEST_REJECTED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_REJECTED = "PROVIDER_REJECTED"
    RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"
    RESPONSE_INVALID = "RESPONSE_INVALID"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"


@dataclass(frozen=True, slots=True, repr=False)
class RakutenLiveSmokeFailure(RuntimeError):
    """A failure whose display never includes provider or credential data."""

    code: RakutenLiveSmokeFailureCode

    def __post_init__(self) -> None:
        if type(self.code) is not RakutenLiveSmokeFailureCode:
            raise TypeError("invalid Rakuten live-smoke failure code")
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"RakutenLiveSmokeFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("Rakuten live-smoke failure serialization is not supported")


def fail_live_smoke(
    code: RakutenLiveSmokeFailureCode = RakutenLiveSmokeFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise RakutenLiveSmokeFailure(code) from None


def exact_sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_live_smoke()
    return value


def exact_utc(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is not timezone.utc
        or value.fold != 0
    ):
        fail_live_smoke()
    return value


def _bounded_keyword(value: object) -> str:
    if type(value) is not str or value != value.strip() or not value:
        fail_live_smoke()
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        fail_live_smoke()
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeError:
        fail_live_smoke()
    if not 2 <= len(encoded) <= 128:
        fail_live_smoke()
    return value


def _safe_secret(value: object) -> str:
    if type(value) is not str or not 1 <= len(value) <= 512:
        fail_live_smoke(RakutenLiveSmokeFailureCode.CREDENTIAL_UNAVAILABLE)
    if any(ord(character) < 33 or ord(character) > 126 for character in value):
        fail_live_smoke(RakutenLiveSmokeFailureCode.CREDENTIAL_UNAVAILABLE)
    return value


@final
class SecretText:
    """Opaque in-memory credential material with redacted displays."""

    __slots__ = ("__value",)
    __value: str

    def __init__(self, value: str) -> None:
        object.__setattr__(self, "_SecretText__value", _safe_secret(value))

    def __init_subclass__(cls, **kwargs: object) -> None:
        del cls, kwargs
        raise TypeError("SecretText subclassing is not supported") from None

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("SecretText is immutable")

    def __repr__(self) -> str:
        return f"SecretText({_REDACTED!r})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("SecretText serialization is not supported") from None

    def _transport_value(self) -> str:
        return self.__value


@dataclass(frozen=True, slots=True, repr=False)
class RakutenLiveSmokeRequest:
    """One-page, one-hit keyword request; affiliate ID is not accepted."""

    keyword: str

    def __post_init__(self) -> None:
        _bounded_keyword(self.keyword)

    def __repr__(self) -> str:
        return f"RakutenLiveSmokeRequest({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    @property
    def fingerprint(self) -> str:
        canonical = json.dumps(
            {
                "api_version": RAKUTEN_API_VERSION,
                "availability": 1,
                "elements": list(_REQUEST_ELEMENTS),
                "format": "json",
                "format_version": 2,
                "hits": 1,
                "keyword": self.keyword,
                "operation": "ITEM_SEARCH",
                "page": 1,
                "sort": "standard",
            },
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def _query(self, application_id: SecretText) -> tuple[tuple[str, str], ...]:
        return (
            ("applicationId", application_id._transport_value()),
            ("format", "json"),
            ("formatVersion", "2"),
            ("keyword", self.keyword),
            ("hits", "1"),
            ("page", "1"),
            ("sort", "standard"),
            ("availability", "1"),
            ("elements", ",".join(_REQUEST_ELEMENTS)),
        )


@dataclass(frozen=True, slots=True, repr=False)
class RakutenLiveSmokeGrant:
    """Short-lived external gate binding for one exact staging request."""

    environment: str
    request_sha256: str
    operations_evidence_sha256: str
    execution_approval_sha256: str
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if type(self.environment) is not str or self.environment != STAGING_ENVIRONMENT:
            fail_live_smoke()
        exact_sha256(self.request_sha256)
        operations_digest = exact_sha256(self.operations_evidence_sha256)
        execution_digest = exact_sha256(self.execution_approval_sha256)
        if (
            operations_digest == "0" * 64
            or execution_digest == "0" * 64
            or operations_digest == execution_digest
        ):
            fail_live_smoke()
        issued = exact_utc(self.issued_at)
        expires = exact_utc(self.expires_at)
        lifetime = expires - issued
        if lifetime <= timedelta(0) or lifetime > MAX_GRANT_LIFETIME:
            fail_live_smoke()

    def __repr__(self) -> str:
        return f"RakutenLiveSmokeGrant({_REDACTED})"

    def permits(self, request_sha256: str, now: datetime) -> bool:
        return (
            type(request_sha256) is str
            and request_sha256 == self.request_sha256
            and type(now) is datetime
            and now.tzinfo is timezone.utc
            and now.fold == 0
            and self.issued_at <= now <= self.expires_at
        )


@dataclass(frozen=True, slots=True, repr=False, init=False)
class RakutenHttpResponse:
    """Bounded transport result whose raw body has no public display/accessor."""

    status: int
    headers: tuple[tuple[str, str], ...]
    __body: bytes

    def __init__(
        self,
        *,
        status: int,
        headers: tuple[tuple[str, str], ...],
        body: bytes,
    ) -> None:
        if type(status) is not int or not 100 <= status <= 599:
            fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
        if type(headers) is not tuple or len(headers) > 128:
            fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
        for row in headers:
            if type(row) is not tuple or len(row) != 2:
                fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
            name, value = row
            if (
                type(name) is not str
                or _HEADER_NAME.fullmatch(name) is None
                or type(value) is not str
                or len(value) > 4096
                or any(
                    ord(character) < 32 or ord(character) == 127
                    for character in value
                )
            ):
                fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
        if type(body) is not bytes or len(body) > MAX_RESPONSE_BYTES + 1:
            fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_TOO_LARGE)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "headers", headers)
        object.__setattr__(self, "_RakutenHttpResponse__body", body)

    def __repr__(self) -> str:
        return f"RakutenHttpResponse({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("Rakuten HTTP response serialization is not supported")

    def _body_for_smoke(self) -> bytes:
        return self.__body


class RateObservation(str, Enum):
    NOT_EXPOSED = "NOT_EXPOSED"
    PARTIAL_HEADER_METADATA = "PARTIAL_HEADER_METADATA"
    COMPLETE_HEADER_METADATA = "COMPLETE_HEADER_METADATA"


@dataclass(frozen=True, slots=True)
class RakutenLiveSmokeReceipt:
    """Sanitized receipt: hashes and observations, never raw provider data."""

    api_version: str
    request_sha256: str
    response_sha256: str
    response_bytes: int
    observed_at: datetime
    http_status: int
    auth_observation: str
    schema_observation: str
    rate_observation: RateObservation
    rate_limit: int | None
    rate_remaining: int | None
    rate_reset: int | None
    provider_request_id: str | None
    count: int
    page: int
    hits: int
    page_count: int
    returned_item_count: int
    network_request_count: int = 1
    retry_count: int = 0
    pagination_count: int = 0
    storage_write_count: int = 0
    persistence_write_count: int = 0
    publication_count: int = 0

    @property
    def canonical_json(self) -> bytes:
        payload = {
            "api_version": self.api_version,
            "auth_observation": self.auth_observation,
            "count": self.count,
            "hits": self.hits,
            "http_status": self.http_status,
            "network_request_count": self.network_request_count,
            "observed_at": self.observed_at.isoformat().replace("+00:00", "Z"),
            "page": self.page,
            "page_count": self.page_count,
            "pagination_count": self.pagination_count,
            "persistence_write_count": self.persistence_write_count,
            "provider_request_id": self.provider_request_id,
            "publication_count": self.publication_count,
            "rate_limit": self.rate_limit,
            "rate_observation": self.rate_observation.value,
            "rate_remaining": self.rate_remaining,
            "rate_reset": self.rate_reset,
            "request_sha256": self.request_sha256,
            "response_bytes": self.response_bytes,
            "response_sha256": self.response_sha256,
            "retry_count": self.retry_count,
            "returned_item_count": self.returned_item_count,
            "schema_observation": self.schema_observation,
            "storage_write_count": self.storage_write_count,
        }
        return json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")


__all__ = [
    "MAX_GRANT_LIFETIME",
    "MAX_JSON_DEPTH",
    "MAX_JSON_NODES",
    "MAX_RESPONSE_BYTES",
    "NETWORK_TIMEOUT_SECONDS",
    "RAKUTEN_ACCESS_KEY_ALIAS",
    "RAKUTEN_API_DOCUMENTATION_RETRIEVED_ON",
    "RAKUTEN_API_DOCUMENTATION_URL",
    "RAKUTEN_API_ORIGIN",
    "RAKUTEN_API_VERSION",
    "RAKUTEN_APPLICATION_ID_ALIAS",
    "RAKUTEN_ITEM_SEARCH_PATH",
    "RateObservation",
    "RakutenHttpResponse",
    "RakutenLiveSmokeFailure",
    "RakutenLiveSmokeFailureCode",
    "RakutenLiveSmokeGrant",
    "RakutenLiveSmokeReceipt",
    "RakutenLiveSmokeRequest",
    "STAGING_ENVIRONMENT",
    "SecretText",
    "exact_sha256",
    "exact_utc",
    "fail_live_smoke",
]

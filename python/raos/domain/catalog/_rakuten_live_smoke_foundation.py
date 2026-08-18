"""Foundational closed values for the bounded ST-0505 live smoke."""

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
_REDACTED: Final = "<redacted-rakuten-live-smoke>"
_REQUEST_ELEMENTS: Final = (
    "count",
    "page",
    "hits",
    "pageCount",
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


def exact_int(value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)
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

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("Rakuten live-smoke request serialization is not supported")

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
        if type(application_id) is not SecretText:
            fail_live_smoke(RakutenLiveSmokeFailureCode.CREDENTIAL_UNAVAILABLE)
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

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("Rakuten live-smoke grant serialization is not supported")

    @property
    def fingerprint(self) -> str:
        payload = {
            "environment": self.environment,
            "execution_approval_sha256": self.execution_approval_sha256,
            "expires_at": self.expires_at.isoformat().replace("+00:00", "Z"),
            "issued_at": self.issued_at.isoformat().replace("+00:00", "Z"),
            "operations_evidence_sha256": self.operations_evidence_sha256,
            "request_sha256": self.request_sha256,
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        return hashlib.sha256(canonical).hexdigest()

    def permits(self, request_sha256: str, now: datetime) -> bool:
        return (
            type(request_sha256) is str
            and request_sha256 == self.request_sha256
            and type(now) is datetime
            and now.tzinfo is timezone.utc
            and now.fold == 0
            and self.issued_at <= now <= self.expires_at
        )


class RateObservation(str, Enum):
    NOT_EXPOSED = "NOT_EXPOSED"
    PARTIAL_HEADER_METADATA = "PARTIAL_HEADER_METADATA"
    COMPLETE_HEADER_METADATA = "COMPLETE_HEADER_METADATA"

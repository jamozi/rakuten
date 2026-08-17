"""Closed response and receipt values for the ST-0505 Rakuten live smoke."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Final, NoReturn, SupportsIndex, final

from raos.domain.catalog._rakuten_live_smoke_foundation import (
    MAX_GRANT_LIFETIME,
    MAX_JSON_DEPTH,
    MAX_JSON_NODES,
    MAX_RESPONSE_BYTES,
    NETWORK_TIMEOUT_SECONDS,
    RAKUTEN_ACCESS_KEY_ALIAS,
    RAKUTEN_API_DOCUMENTATION_RETRIEVED_ON,
    RAKUTEN_API_DOCUMENTATION_URL,
    RAKUTEN_API_ORIGIN,
    RAKUTEN_API_VERSION,
    RAKUTEN_APPLICATION_ID_ALIAS,
    RAKUTEN_ITEM_SEARCH_PATH,
    STAGING_ENVIRONMENT,
    RateObservation,
    RakutenLiveSmokeFailure,
    RakutenLiveSmokeFailureCode,
    RakutenLiveSmokeGrant,
    RakutenLiveSmokeRequest,
    SecretText,
    exact_int,
    exact_sha256,
    exact_utc,
    fail_live_smoke,
)


_HEADER_NAME: Final = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}\Z", re.ASCII)
_SAFE_RECEIPT_TOKEN: Final = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z", re.ASCII
)
_REDACTED: Final = "<redacted-rakuten-live-smoke>"


@final
class RakutenHttpResponse:
    """Bounded transport result with no public raw body or header access."""

    __slots__ = ("__body", "__headers", "__status")
    __status: int
    __headers: tuple[tuple[str, str], ...]
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
        if type(headers) is not tuple or len(headers) > 32:
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
        object.__setattr__(self, "_RakutenHttpResponse__status", status)
        object.__setattr__(self, "_RakutenHttpResponse__headers", headers)
        object.__setattr__(self, "_RakutenHttpResponse__body", body)

    @property
    def status(self) -> int:
        return self.__status

    def __repr__(self) -> str:
        return f"RakutenHttpResponse({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("RakutenHttpResponse is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("RakutenHttpResponse is immutable")

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("Rakuten HTTP response serialization is not supported")

    def _headers_for_smoke(self) -> tuple[tuple[str, str], ...]:
        return self.__headers

    def _body_for_smoke(self) -> bytes:
        return self.__body


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

    def __post_init__(self) -> None:
        if type(self.api_version) is not str or self.api_version != RAKUTEN_API_VERSION:
            fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)
        exact_sha256(self.request_sha256)
        exact_sha256(self.response_sha256)
        exact_utc(self.observed_at)
        exact_int(self.response_bytes, minimum=2, maximum=MAX_RESPONSE_BYTES)
        if (
            type(self.http_status) is not int
            or self.http_status != 200
            or type(self.auth_observation) is not str
            or self.auth_observation != "HTTP_200_ACCEPTED"
            or type(self.schema_observation) is not str
            or self.schema_observation != "FORMAT_VERSION_2_COMPATIBLE"
            or type(self.rate_observation) is not RateObservation
        ):
            fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)
        for value in (self.rate_limit, self.rate_remaining, self.rate_reset):
            if value is not None:
                exact_int(value, minimum=0, maximum=(1 << 63) - 1)
        if self.rate_limit is not None and (
            self.rate_limit < 1
            or (
                self.rate_remaining is not None
                and self.rate_remaining > self.rate_limit
            )
        ):
            fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)
        present_rate_values = sum(
            value is not None
            for value in (self.rate_limit, self.rate_remaining, self.rate_reset)
        )
        expected_observation = (
            RateObservation.NOT_EXPOSED
            if present_rate_values == 0
            else RateObservation.COMPLETE_HEADER_METADATA
            if present_rate_values == 3
            else RateObservation.PARTIAL_HEADER_METADATA
        )
        if self.rate_observation is not expected_observation:
            fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)
        if self.provider_request_id is not None and (
            type(self.provider_request_id) is not str
            or _SAFE_RECEIPT_TOKEN.fullmatch(self.provider_request_id) is None
        ):
            fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)
        exact_int(self.count, minimum=0, maximum=(1 << 63) - 1)
        if type(self.page) is not int or self.page != 1:
            fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)
        exact_int(self.hits, minimum=0, maximum=1)
        exact_int(self.page_count, minimum=0, maximum=100)
        exact_int(self.returned_item_count, minimum=0, maximum=1)
        if (
            self.returned_item_count > self.hits
            or self.returned_item_count > self.count
            or (self.count == 0) != (self.page_count == 0)
        ):
            fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)
        exact_counts = (
            (self.network_request_count, 1),
            (self.retry_count, 0),
            (self.pagination_count, 0),
            (self.storage_write_count, 0),
            (self.persistence_write_count, 0),
            (self.publication_count, 0),
        )
        if any(
            type(value) is not int or value != expected
            for value, expected in exact_counts
        ):
            fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)

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

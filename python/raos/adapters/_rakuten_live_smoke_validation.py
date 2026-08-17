"""Strict ephemeral response validation for ST-0505."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Final

from raos.adapters._rakuten_live_smoke_json import parse_schema
from raos.domain.catalog.rakuten_live_smoke import (
    RAKUTEN_API_VERSION,
    RateObservation,
    RakutenHttpResponse,
    RakutenLiveSmokeFailureCode,
    RakutenLiveSmokeReceipt,
    RakutenLiveSmokeRequest,
    exact_utc,
    fail_live_smoke,
)


_SAFE_RESPONSE_TOKEN: Final = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z", re.ASCII
)
_RESPONSE_HEADER_NAMES: Final = frozenset(
    {
        "content-encoding",
        "content-type",
        "x-rakuten-request-id",
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-reset",
        "x-request-id",
    }
)


def _rows(response: RakutenHttpResponse) -> tuple[tuple[str, str], ...]:
    rows = response._headers_for_smoke()
    if any(name.lower() not in _RESPONSE_HEADER_NAMES for name, _value in rows):
        fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
    return rows


def _values(
    rows: tuple[tuple[str, str], ...],
    name: str,
) -> tuple[str, ...]:
    lowered = name.lower()
    return tuple(value for key, value in rows if key.lower() == lowered)


def _header(
    rows: tuple[tuple[str, str], ...],
    name: str,
    *,
    required: bool = False,
) -> str | None:
    values = _values(rows, name)
    if len(values) > 1 or (required and not values):
        fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
    return values[0] if values else None


def _numeric_header(
    rows: tuple[tuple[str, str], ...],
    name: str,
) -> int | None:
    value = _header(rows, name)
    if value is None:
        return None
    if not value.isascii() or not value.isdigit():
        fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
    parsed = int(value, 10)
    if parsed > (1 << 63) - 1:
        fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
    return parsed


def _content_headers(rows: tuple[tuple[str, str], ...]) -> None:
    content_type = _header(rows, "Content-Type", required=True)
    assert content_type is not None
    parts = [part.strip().lower() for part in content_type.split(";")]
    if parts[0] != "application/json":
        fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
    for parameter in parts[1:]:
        if parameter not in {"charset=utf-8", 'charset="utf-8"'}:
            fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
    content_encoding = _header(rows, "Content-Encoding")
    if content_encoding is not None and content_encoding.lower() != "identity":
        fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)


def _rate_observation(
    limit: int | None,
    remaining: int | None,
    reset: int | None,
) -> RateObservation:
    present = sum(value is not None for value in (limit, remaining, reset))
    if present == 0:
        return RateObservation.NOT_EXPOSED
    if present == 3:
        return RateObservation.COMPLETE_HEADER_METADATA
    return RateObservation.PARTIAL_HEADER_METADATA


def _request_id(rows: tuple[tuple[str, str], ...]) -> str | None:
    rakuten = _header(rows, "X-Rakuten-Request-Id")
    generic = _header(rows, "X-Request-Id")
    if rakuten is not None and generic is not None:
        fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
    value = rakuten if rakuten is not None else generic
    if value is not None and _SAFE_RESPONSE_TOKEN.fullmatch(value) is None:
        fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
    return value


def build_receipt(
    *,
    response: RakutenHttpResponse,
    request: RakutenLiveSmokeRequest,
    observed_at: datetime,
) -> RakutenLiveSmokeReceipt:
    """Validate one 200 response and discard its raw body after hashing."""

    if type(response) is not RakutenHttpResponse:
        fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
    if type(request) is not RakutenLiveSmokeRequest:
        fail_live_smoke(RakutenLiveSmokeFailureCode.INVALID_ARGUMENT)
    exact_utc(observed_at)
    rows = _rows(response)
    _content_headers(rows)
    raw_body = response._body_for_smoke()
    count, page, hits, page_count, returned = parse_schema(raw_body)
    limit = _numeric_header(rows, "X-RateLimit-Limit")
    remaining = _numeric_header(rows, "X-RateLimit-Remaining")
    reset = _numeric_header(rows, "X-RateLimit-Reset")
    if limit is not None and remaining is not None and remaining > limit:
        fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
    return RakutenLiveSmokeReceipt(
        api_version=RAKUTEN_API_VERSION,
        request_sha256=request.fingerprint,
        response_sha256=hashlib.sha256(raw_body).hexdigest(),
        response_bytes=len(raw_body),
        observed_at=observed_at,
        http_status=200,
        auth_observation="HTTP_200_ACCEPTED",
        schema_observation="FORMAT_VERSION_2_COMPATIBLE",
        rate_observation=_rate_observation(limit, remaining, reset),
        rate_limit=limit,
        rate_remaining=remaining,
        rate_reset=reset,
        provider_request_id=_request_id(rows),
        count=count,
        page=page,
        hits=hits,
        page_count=page_count,
        returned_item_count=returned,
    )


__all__ = ["build_receipt"]

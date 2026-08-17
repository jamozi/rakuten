"""Strict ephemeral response validation for ST-0505."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Final, NoReturn, cast
from urllib.parse import urlsplit

from raos.domain.catalog.rakuten_live_smoke import (
    MAX_JSON_DEPTH,
    MAX_JSON_NODES,
    MAX_RESPONSE_BYTES,
    RAKUTEN_API_VERSION,
    RateObservation,
    RakutenHttpResponse,
    RakutenLiveSmokeFailure,
    RakutenLiveSmokeFailureCode,
    RakutenLiveSmokeReceipt,
    RakutenLiveSmokeRequest,
    exact_sha256,
    exact_utc,
    fail_live_smoke,
)


_SAFE_RESPONSE_TOKEN: Final = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z", re.ASCII
)
_ITEM_FIELDS: Final = frozenset(
    {"itemCode", "itemName", "itemPrice", "itemUrl", "shopCode"}
)
_TOP_LEVEL_FIELDS: Final = frozenset(
    {"count", "page", "first", "last", "hits", "carrier", "pageCount", "items"}
)


def _reject_constant(value: str) -> NoReturn:
    del value
    fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
        result[key] = value
    return result


def _validate_tree(value: object) -> None:
    pending: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
        if current is None or type(current) in {str, bool, int}:
            continue
        if type(current) is float:
            if not math.isfinite(current):
                fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
            continue
        if type(current) is list:
            pending.extend((child, depth + 1) for child in cast(list[object], current))
            continue
        if type(current) is dict:
            pending.extend(
                (child, depth + 1)
                for child in cast(dict[object, object], current).values()
            )
            continue
        fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)


def _parse(body: bytes) -> dict[str, Any]:
    if not 2 <= len(body) <= MAX_RESPONSE_BYTES:
        code = (
            RakutenLiveSmokeFailureCode.RESPONSE_TOO_LARGE
            if len(body) > MAX_RESPONSE_BYTES
            else RakutenLiveSmokeFailureCode.RESPONSE_INVALID
        )
        fail_live_smoke(code)
    try:
        parsed = json.loads(
            body.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except RakutenLiveSmokeFailure:
        raise
    except (UnicodeError, json.JSONDecodeError):
        fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
    if type(parsed) is not dict:
        fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
    _validate_tree(parsed)
    return cast(dict[str, Any], parsed)


def _values(response: RakutenHttpResponse, name: str) -> tuple[str, ...]:
    lowered = name.lower()
    return tuple(value for key, value in response.headers if key.lower() == lowered)


def _header(
    response: RakutenHttpResponse,
    name: str,
    *,
    required: bool = False,
) -> str | None:
    values = _values(response, name)
    if len(values) > 1 or (required and not values):
        fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
    return values[0] if values else None


def _numeric_header(response: RakutenHttpResponse, name: str) -> int | None:
    value = _header(response, name)
    if value is None:
        return None
    if not value.isascii() or not value.isdigit():
        fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
    parsed = int(value, 10)
    if parsed > (1 << 63) - 1:
        fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
    return parsed


def _content_headers(response: RakutenHttpResponse) -> None:
    content_type = _header(response, "Content-Type", required=True)
    assert content_type is not None
    parts = [part.strip().lower() for part in content_type.split(";")]
    if parts[0] != "application/json":
        fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
    for parameter in parts[1:]:
        if parameter not in {"charset=utf-8", 'charset="utf-8"'}:
            fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
    content_encoding = _header(response, "Content-Encoding")
    if content_encoding is not None and content_encoding.lower() != "identity":
        fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)


def _integer(
    mapping: Mapping[str, Any],
    field: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    value = mapping.get(field)
    if type(value) is not int or not minimum <= value <= maximum:
        fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)
    return value


def _https_url(value: object) -> None:
    if type(value) is not str or not 1 <= len(value) <= 2048:
        fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)


def _item(value: object) -> None:
    if type(value) is not dict:
        fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)
    item = cast(dict[str, Any], value)
    if set(item) != _ITEM_FIELDS:
        fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)
    item_code = item.get("itemCode")
    item_name = item.get("itemName")
    shop_code = item.get("shopCode")
    if (
        type(item_code) is not str
        or not 3 <= len(item_code) <= 256
        or ":" not in item_code
        or type(item_name) is not str
        or not 1 <= len(item_name) <= 1000
        or type(shop_code) is not str
        or not 1 <= len(shop_code) <= 128
    ):
        fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)
    price = item.get("itemPrice")
    if type(price) is not int or not 0 <= price <= 999_999_999:
        fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)
    _https_url(item.get("itemUrl"))


def _schema(parsed: dict[str, Any]) -> tuple[int, int, int, int, int]:
    if not set(parsed).issubset(_TOP_LEVEL_FIELDS):
        fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)
    if not {"count", "page", "hits", "pageCount", "items"}.issubset(parsed):
        fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)
    count = _integer(parsed, "count", minimum=0, maximum=(1 << 63) - 1)
    page = _integer(parsed, "page", minimum=1, maximum=1)
    hits = _integer(parsed, "hits", minimum=0, maximum=1)
    page_count = _integer(parsed, "pageCount", minimum=0, maximum=100)
    items = parsed.get("items")
    if type(items) is not list or len(items) > hits or len(items) > 1:
        fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)
    for value in cast(list[object], items):
        _item(value)
    if len(items) > count or (count == 0) != (page_count == 0):
        fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)
    for optional in ("first", "last", "carrier"):
        if optional in parsed:
            _integer(parsed, optional, minimum=0, maximum=(1 << 63) - 1)
    return count, page, hits, page_count, len(items)


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


def build_receipt(
    *,
    response: RakutenHttpResponse,
    request: RakutenLiveSmokeRequest,
    observed_at: datetime,
) -> RakutenLiveSmokeReceipt:
    """Validate one 200 response and discard its raw body after hashing."""

    exact_utc(observed_at)
    _content_headers(response)
    raw_body = response._body_for_smoke()
    count, page, hits, page_count, returned = _schema(_parse(raw_body))
    limit = _numeric_header(response, "X-RateLimit-Limit")
    remaining = _numeric_header(response, "X-RateLimit-Remaining")
    reset = _numeric_header(response, "X-RateLimit-Reset")
    if limit is not None and remaining is not None and remaining > limit:
        fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
    request_id = _header(response, "X-Rakuten-Request-Id")
    if request_id is None:
        request_id = _header(response, "X-Request-Id")
    if request_id is not None and _SAFE_RESPONSE_TOKEN.fullmatch(request_id) is None:
        fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)

    receipt = RakutenLiveSmokeReceipt(
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
        provider_request_id=request_id,
        count=count,
        page=page,
        hits=hits,
        page_count=page_count,
        returned_item_count=returned,
    )
    exact_sha256(receipt.response_sha256)
    if (
        receipt.network_request_count != 1
        or receipt.retry_count != 0
        or receipt.pagination_count != 0
        or receipt.storage_write_count != 0
        or receipt.persistence_write_count != 0
        or receipt.publication_count != 0
    ):
        fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)
    return receipt


__all__ = ["build_receipt"]

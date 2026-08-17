"""Strict bounded JSON and schema parser for ST-0505."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any, NoReturn, cast
from urllib.parse import urlsplit

from raos.domain.catalog.rakuten_live_smoke import (
    MAX_JSON_DEPTH,
    MAX_JSON_NODES,
    MAX_RESPONSE_BYTES,
    RakutenLiveSmokeFailure,
    RakutenLiveSmokeFailureCode,
    fail_live_smoke,
)


_ITEM_FIELDS = frozenset(
    {"itemCode", "itemName", "itemPrice", "itemUrl", "shopCode"}
)
_TOP_LEVEL_FIELDS = frozenset(
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


def _bounded_text(value: object, *, maximum: int) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)
    return value


def _https_url(value: object) -> None:
    text = _bounded_text(value, maximum=2048)
    parsed = urlsplit(text)
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
    item_code = _bounded_text(item.get("itemCode"), maximum=256)
    if ":" not in item_code:
        fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)
    _bounded_text(item.get("itemName"), maximum=1000)
    _bounded_text(item.get("shopCode"), maximum=128)
    price = item.get("itemPrice")
    if type(price) is not int or not 0 <= price <= 999_999_999:
        fail_live_smoke(RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH)
    _https_url(item.get("itemUrl"))


def parse_schema(body: bytes) -> tuple[int, int, int, int, int]:
    parsed = _parse(body)
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
    for optional in ("first", "last"):
        if optional in parsed:
            _integer(parsed, optional, minimum=0, maximum=(1 << 63) - 1)
    if "carrier" in parsed:
        _integer(parsed, "carrier", minimum=0, maximum=2)
    return count, page, hits, page_count, len(items)


__all__ = ["parse_schema"]

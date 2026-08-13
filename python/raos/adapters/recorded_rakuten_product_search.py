"""Strict in-memory recorded Rakuten Product Search adapter for ST-0502."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from typing import Any, NoReturn, SupportsIndex, cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.rakuten_product_search import (
    ProductSearchPersistenceStatus,
    ProductSearchProviderFailure,
    ProductSearchProviderFailureClass,
    ProductSearchProviderMode,
    ProductSearchReceiptPurpose,
    ProductSearchStorageStatus,
    ProductSearchValidationReceipt,
    ProductSelectorKind,
    RakutenProduct,
    RakutenProductSearchFailure,
    RakutenProductSearchFailureCode,
    RakutenProductSearchRequest,
    RakutenProductSearchResult,
    fail_product_search,
    product_search_sha256,
    product_search_utc,
)


_MAX_BODY_BYTES = 2 * 1024 * 1024
_MAX_JSON_DEPTH = 32
_MAX_JSON_NODES = 50_000
_TOP_LEVEL_KEYS = frozenset(
    {"count", "first", "hits", "items", "last", "page", "pageCount"}
)
_ITEM_KEYS = frozenset(
    {
        "affiliateUrl",
        "brandName",
        "makerName",
        "mediumImageUrl",
        "productCode",
        "productId",
        "productName",
        "productNo",
        "productUrlPC",
    }
)
_REDACTED = "<redacted-recorded-rakuten-product-search>"


def _raw_invalid() -> NoReturn:
    fail_product_search(RakutenProductSearchFailureCode.RAW_RESPONSE_INVALID)


def _reject_constant(value: str) -> NoReturn:
    del value
    _raw_invalid()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _raw_invalid()
        result[key] = value
    return result


def _validate_json_tree(value: object) -> None:
    pending: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES or depth > _MAX_JSON_DEPTH:
            _raw_invalid()
        if current is None or type(current) in {str, bool, int}:
            continue
        if type(current) is float:
            if not math.isfinite(current):
                _raw_invalid()
            continue
        if type(current) is list:
            sequence = cast(list[object], current)
            pending.extend((item, depth + 1) for item in sequence)
            continue
        if type(current) is dict:
            mapping = cast(dict[object, object], current)
            pending.extend((item, depth + 1) for item in mapping.values())
            continue
        _raw_invalid()


def _validated_response_bytes(value: object) -> bytes:
    if type(value) is not bytes or not 2 <= len(value) <= _MAX_BODY_BYTES:
        _raw_invalid()
    return value


def _parse_json(response_bytes: bytes) -> dict[str, Any]:
    validated_bytes = _validated_response_bytes(response_bytes)
    try:
        decoded = validated_bytes.decode("utf-8", errors="strict")
        parsed: object = json.loads(
            decoded,
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except RakutenProductSearchFailure:
        raise
    except UnicodeError, json.JSONDecodeError, RecursionError, ValueError:
        _raw_invalid()
    _validate_json_tree(parsed)
    if type(parsed) is not dict:
        _raw_invalid()
    return cast(dict[str, Any], parsed)


def _nullable_text(value: object) -> str | None:
    if value is None:
        return None
    if type(value) is str:
        return value
    _raw_invalid()


def _required_text(value: object) -> str:
    if type(value) is not str or not value:
        _raw_invalid()
    return value


def _build_result(
    *,
    request: RakutenProductSearchRequest,
    response_bytes: bytes,
    expected_response_sha256: str,
    received_at: datetime,
) -> RakutenProductSearchResult:
    if type(request) is not RakutenProductSearchRequest:
        fail_product_search()
    validated_bytes = _validated_response_bytes(response_bytes)
    expected_sha256 = product_search_sha256(expected_response_sha256)
    observed_sha256 = hashlib.sha256(validated_bytes).hexdigest()
    if observed_sha256 != expected_sha256:
        _raw_invalid()
    observed_at = product_search_utc(received_at)
    envelope = _parse_json(validated_bytes)
    if frozenset(envelope) != _TOP_LEVEL_KEYS:
        _raw_invalid()
    for key in ("count", "first", "hits", "last", "page", "pageCount"):
        if type(envelope[key]) is not int or envelope[key] != 1:
            _raw_invalid()
    items_value: object = envelope["items"]
    if type(items_value) is not list:
        _raw_invalid()
    items = cast(list[object], items_value)
    if len(items) != 1:
        _raw_invalid()
    item_value = items[0]
    if type(item_value) is not dict:
        _raw_invalid()
    item_mapping = cast(dict[str, object], item_value)
    if frozenset(item_mapping) != _ITEM_KEYS:
        _raw_invalid()
    product_id = _required_text(item_mapping["productId"])
    product_code = _required_text(item_mapping["productCode"])
    if (
        request.selector_kind is ProductSelectorKind.PRODUCT_ID
        and product_id != request.selector_value
    ) or (
        request.selector_kind is ProductSelectorKind.PRODUCT_CODE
        and product_code != request.selector_value
    ):
        fail_product_search(RakutenProductSearchFailureCode.RESULT_MISMATCH)
    try:
        product = RakutenProduct(
            product_id=product_id,
            product_code=product_code,
            product_url_pc=_required_text(item_mapping["productUrlPC"]),
            affiliate_url=_required_text(item_mapping["affiliateUrl"]),
            brand_name=_nullable_text(item_mapping["brandName"]),
            maker_name=_nullable_text(item_mapping["makerName"]),
            medium_image_url=_nullable_text(item_mapping["mediumImageUrl"]),
            product_name=_nullable_text(item_mapping["productName"]),
            product_no=_nullable_text(item_mapping["productNo"]),
        )
    except RakutenProductSearchFailure:
        _raw_invalid()
    receipt = ProductSearchValidationReceipt(
        purpose=ProductSearchReceiptPurpose.VALIDATION_ONLY,
        provider="RAKUTEN_ICHIBA",
        api_version=request.api_version,
        request_fingerprint=request.fingerprint,
        response_sha256=observed_sha256,
        byte_size=len(validated_bytes),
        received_at=observed_at,
        uri=None,
        storage_status=ProductSearchStorageStatus.NOT_EXECUTED,
        persistence_status=ProductSearchPersistenceStatus.NOT_EXECUTED,
    )
    return RakutenProductSearchResult(
        provider_mode=ProductSearchProviderMode.RECORDED_TEST_ONLY,
        request_fingerprint=request.fingerprint,
        product=product,
        receipt=receipt,
        live_eligible=False,
    )


@dataclass(frozen=True, slots=True, repr=False, init=False)
class RecordedProductSearchFixture:
    """One exact synthetic request/response exchange; raw bytes stay private."""

    request: RakutenProductSearchRequest
    http_status: int
    content_type: str
    response_sha256: str
    received_at: datetime
    result: RakutenProductSearchResult
    _response_bytes: bytes

    def __init__(
        self,
        *,
        request: RakutenProductSearchRequest,
        http_status: int,
        content_type: str,
        response_bytes: bytes,
        response_sha256: str,
        received_at: datetime,
    ) -> None:
        if (
            type(http_status) is not int
            or http_status != 200
            or type(content_type) is not str
            or content_type != "application/json"
        ):
            _raw_invalid()
        result = _build_result(
            request=request,
            response_bytes=response_bytes,
            expected_response_sha256=response_sha256,
            received_at=received_at,
        )
        object.__setattr__(self, "request", request)
        object.__setattr__(self, "http_status", http_status)
        object.__setattr__(self, "content_type", content_type)
        object.__setattr__(self, "response_sha256", result.receipt.response_sha256)
        object.__setattr__(self, "received_at", result.receipt.received_at)
        object.__setattr__(self, "result", result)
        object.__setattr__(
            self, "_response_bytes", _validated_response_bytes(response_bytes)
        )

    def __repr__(self) -> str:
        return f"RecordedProductSearchFixture({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError(
            "recorded Product Search fixture serialization is not supported"
        )


@final
class RecordedRakutenProductSearchAdapter:
    """Pure lookup over exact immutable Product Search fixtures."""

    __slots__ = ("_fixtures",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        fixture_capacity: int,
        fixtures: tuple[RecordedProductSearchFixture, ...],
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or type(fixture_capacity) is not int
            or not 0 < fixture_capacity <= 10_000
            or type(fixtures) is not tuple
            or not fixtures
            or len(fixtures) > fixture_capacity
            or any(
                type(fixture) is not RecordedProductSearchFixture
                for fixture in fixtures
            )
            or len({fixture.request.fingerprint for fixture in fixtures})
            != len(fixtures)
        ):
            fail_product_search()
        self._fixtures = fixtures

    def search(
        self, request: RakutenProductSearchRequest
    ) -> RakutenProductSearchResult:
        if type(request) is not RakutenProductSearchRequest:
            fail_product_search()
        matches = tuple(
            fixture for fixture in self._fixtures if fixture.request == request
        )
        if len(matches) != 1:
            fail_product_search(RakutenProductSearchFailureCode.PROVIDER_UNAVAILABLE)
        return matches[0].result


def classify_product_search_http_status(status: object) -> ProductSearchProviderFailure:
    mapping = {
        400: ProductSearchProviderFailureClass.PERMANENT,
        404: ProductSearchProviderFailureClass.PERMANENT,
        429: ProductSearchProviderFailureClass.THROTTLED_RETRYABLE_DECLARATION_ONLY,
        500: ProductSearchProviderFailureClass.TRANSIENT_RETRYABLE_DECLARATION_ONLY,
        503: ProductSearchProviderFailureClass.TRANSIENT_RETRYABLE_DECLARATION_ONLY,
    }
    if type(status) is not int or status not in mapping:
        fail_product_search()
    return ProductSearchProviderFailure(
        http_status=status,
        failure_class=mapping[status],
        retries_executed=0,
    )


__all__ = [
    "RecordedProductSearchFixture",
    "RecordedRakutenProductSearchAdapter",
    "classify_product_search_http_status",
]

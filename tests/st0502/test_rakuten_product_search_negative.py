"""Hostile recorded Product Search response checks for ST-0502."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Callable, cast

import pytest

from raos.adapters.recorded_rakuten_product_search import (
    RecordedProductSearchFixture,
)
from raos.domain.catalog.rakuten_product_search import (
    PRODUCT_SEARCH_ELEMENTS,
    RakutenProductSearchFailure,
    RakutenProductSearchFailureCode,
    RakutenProductSearchRequest,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OBSERVED_AT = datetime(2026, 8, 13, 9, 51, 58, tzinfo=timezone.utc)


def _request() -> RakutenProductSearchRequest:
    return RakutenProductSearchRequest(
        api_version="2025-08-01",
        response_format="json",
        format_version=2,
        hits=1,
        page=1,
        product_id="synthetic-product-id",
        product_code=None,
        elements=PRODUCT_SEARCH_ELEMENTS,
    )


def _payload() -> dict[str, object]:
    return {
        "count": 1,
        "first": 1,
        "hits": 1,
        "items": [
            {
                "affiliateUrl": "https://affiliate.example.test/product",
                "brandName": "Synthetic Brand",
                "makerName": "Synthetic Maker",
                "mediumImageUrl": "https://images.example.test/product.jpg",
                "productCode": "4900000000000",
                "productId": "synthetic-product-id",
                "productName": "Synthetic Product",
                "productNo": "SYNTH-001",
                "productUrlPC": "https://product.example.test/detail",
            }
        ],
        "last": 1,
        "page": 1,
        "pageCount": 1,
    }


def _bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _item(payload: dict[str, object]) -> dict[str, object]:
    items = cast(list[object], payload["items"])
    item = items[0]
    assert type(item) is dict
    return cast(dict[str, object], item)


def _assert_rejected(
    response_bytes: bytes,
    *,
    expected_sha256: str | None = None,
    code: RakutenProductSearchFailureCode = (
        RakutenProductSearchFailureCode.RAW_RESPONSE_INVALID
    ),
) -> None:
    with pytest.raises(RakutenProductSearchFailure) as captured:
        RecordedProductSearchFixture(
            request=_request(),
            http_status=200,
            content_type="application/json",
            response_bytes=response_bytes,
            response_sha256=(
                expected_sha256 or hashlib.sha256(response_bytes).hexdigest()
            ),
            received_at=OBSERVED_AT,
        )
    assert captured.value.code is code
    assert "synthetic-product-id" not in str(captured.value)
    assert "synthetic-product-id" not in repr(captured.value)


@pytest.mark.parametrize(
    "response_bytes",
    [
        b"\xff",
        b'{"count":1,"count":1}',
        b'{"count":NaN}',
        b"[]",
        b"x" * (2 * 1024 * 1024 + 1),
        _bytes(
            {
                "nested": [
                    [[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[None]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]
                ]
            }
        ),
        _bytes([None] * 50_001),
    ],
)
def test_malformed_duplicate_nonfinite_oversize_or_complex_json_fails_closed(
    response_bytes: bytes,
) -> None:
    _assert_rejected(response_bytes)


@pytest.mark.parametrize("value", ["{}", bytearray(b"{}"), memoryview(b"{}")])
def test_non_exact_bytes_fail_closed_before_hashing(
    value: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_hash(data: object) -> object:
        del data
        raise AssertionError("hashing must not run for an invalid raw byte type")

    monkeypatch.setattr(
        "raos.adapters.recorded_rakuten_product_search.hashlib.sha256",
        unexpected_hash,
    )
    with pytest.raises(RakutenProductSearchFailure) as captured:
        RecordedProductSearchFixture(
            request=_request(),
            http_status=200,
            content_type="application/json",
            response_bytes=cast(bytes, value),
            response_sha256="0" * 64,
            received_at=OBSERVED_AT,
        )
    assert captured.value.code is RakutenProductSearchFailureCode.RAW_RESPONSE_INVALID


def test_oversize_bytes_fail_closed_before_hashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_hash(data: object) -> object:
        del data
        raise AssertionError("hashing must not run for an oversized response")

    monkeypatch.setattr(
        "raos.adapters.recorded_rakuten_product_search.hashlib.sha256",
        unexpected_hash,
    )
    with pytest.raises(RakutenProductSearchFailure) as captured:
        RecordedProductSearchFixture(
            request=_request(),
            http_status=200,
            content_type="application/json",
            response_bytes=b"x" * (2 * 1024 * 1024 + 1),
            response_sha256="0" * 64,
            received_at=OBSERVED_AT,
        )
    assert captured.value.code is RakutenProductSearchFailureCode.RAW_RESPONSE_INVALID


Mutation = Callable[[dict[str, object]], None]


def _root_extra(payload: dict[str, object]) -> None:
    payload["unknown"] = True


def _root_missing(payload: dict[str, object]) -> None:
    del payload["count"]


def _wrong_count(payload: dict[str, object]) -> None:
    payload["count"] = 0


def _empty_items(payload: dict[str, object]) -> None:
    payload["items"] = []


def _item_extra(payload: dict[str, object]) -> None:
    _item(payload)["rank"] = 1


def _item_missing(payload: dict[str, object]) -> None:
    del _item(payload)["affiliateUrl"]


def _wrong_scalar_type(payload: dict[str, object]) -> None:
    _item(payload)["productCode"] = 4900000000000


@pytest.mark.parametrize(
    "mutation",
    [
        _root_extra,
        _root_missing,
        _wrong_count,
        _empty_items,
        _item_extra,
        _item_missing,
        _wrong_scalar_type,
    ],
)
def test_unknown_partial_wrong_cardinality_or_wrong_type_fails_closed(
    mutation: Mutation,
) -> None:
    payload = _payload()
    mutation(payload)
    _assert_rejected(_bytes(payload))


def test_hash_and_selector_drift_fail_closed() -> None:
    body = _bytes(_payload())
    _assert_rejected(body, expected_sha256="0" * 64)

    payload = _payload()
    _item(payload)["productId"] = "different-product-id"
    _assert_rejected(
        _bytes(payload),
        code=RakutenProductSearchFailureCode.RESULT_MISMATCH,
    )


@pytest.mark.parametrize(
    ("http_status", "content_type"),
    [(201, "application/json"), (200, "application/json; charset=utf-8")],
)
def test_success_fixture_requires_exact_status_and_content_type(
    http_status: int,
    content_type: str,
) -> None:
    body = _bytes(_payload())
    with pytest.raises(RakutenProductSearchFailure) as captured:
        RecordedProductSearchFixture(
            request=_request(),
            http_status=http_status,
            content_type=content_type,
            response_bytes=body,
            response_sha256=hashlib.sha256(body).hexdigest(),
            received_at=OBSERVED_AT,
        )
    assert captured.value.code is RakutenProductSearchFailureCode.RAW_RESPONSE_INVALID


@pytest.mark.parametrize(
    "url",
    [
        "http://product.example.test/detail",
        "https://user@example.test/detail",
        "https://product.example.test/detail#fragment",
        "https://product.example.test/\u0001detail",
        "https://product.example.test/\u0085detail",
        "https://",
        "https://product.example.test\\detail",
    ],
)
def test_unsafe_provider_urls_fail_closed(url: str) -> None:
    payload = _payload()
    _item(payload)["productUrlPC"] = url
    _assert_rejected(_bytes(payload))


def test_owned_modules_have_no_runtime_or_external_integration_surface() -> None:
    owned = [
        REPOSITORY_ROOT / "python/raos/domain/catalog/rakuten_product_search.py",
        REPOSITORY_ROOT / "python/raos/application/catalog/rakuten_product_search.py",
        REPOSITORY_ROOT / "python/raos/ports/rakuten_product_search.py",
        REPOSITORY_ROOT / "python/raos/adapters/recorded_rakuten_product_search.py",
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in owned)
    forbidden = (
        "import requests",
        "import httpx",
        "import socket",
        "urllib.request",
        "boto3",
        "os.environ",
        "os.getenv",
        "getenv(",
        "open(",
        "Path(",
        "datetime.now",
        "time.time",
        "random.",
        "secrets.",
        "wordpress",
        "st1703",
    )
    assert all(token not in source for token in forbidden)
    assert "accessKey" not in source
    assert "applicationId" not in source
    assert "affiliateId" not in source

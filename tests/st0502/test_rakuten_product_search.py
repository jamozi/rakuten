"""Recorded Product Search contract and application checks for ST-0502."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import pickle
from typing import cast

import pytest

from raos.adapters.recorded_rakuten_product_search import (
    RecordedProductSearchFixture,
    RecordedRakutenProductSearchAdapter,
    classify_product_search_http_status,
)
from raos.application.catalog.rakuten_product_search import (
    RakutenProductSearchService,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.rakuten_product_search import (
    PRODUCT_SEARCH_ELEMENTS,
    PRODUCT_SEARCH_ENDPOINT_PATH,
    PRODUCT_SEARCH_FUTURE_ACCESS_KEY_TRANSPORT,
    PRODUCT_SEARCH_FUTURE_SECRET_ALIASES,
    ProductSearchPersistenceStatus,
    ProductSearchProviderFailureClass,
    ProductSearchProviderMode,
    ProductSearchReceiptPurpose,
    ProductSearchStorageStatus,
    ProductSelectorKind,
    RakutenProductSearchFailure,
    RakutenProductSearchFailureCode,
    RakutenProductSearchRequest,
    RakutenProductSearchResult,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OBSERVED_AT = datetime(2026, 8, 13, 9, 51, 58, tzinfo=timezone.utc)


def _request(
    *, product_id: str | None = "synthetic-product-id", product_code: str | None = None
) -> RakutenProductSearchRequest:
    return RakutenProductSearchRequest(
        api_version="2025-08-01",
        response_format="json",
        format_version=2,
        hits=1,
        page=1,
        product_id=product_id,
        product_code=product_code,
        elements=PRODUCT_SEARCH_ELEMENTS,
    )


def _payload(
    *,
    product_id: str = "synthetic-product-id",
    product_code: str = "4900000000000",
) -> dict[str, object]:
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
                "productCode": product_code,
                "productId": product_id,
                "productName": "Synthetic Product",
                "productNo": "SYNTH-001",
                "productUrlPC": "https://product.example.test/detail?source=fixture",
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


def _fixture(
    request: RakutenProductSearchRequest,
    *,
    payload: dict[str, object] | None = None,
    response_bytes: bytes | None = None,
    response_sha256: str | None = None,
) -> RecordedProductSearchFixture:
    body = (
        response_bytes if response_bytes is not None else _bytes(payload or _payload())
    )
    return RecordedProductSearchFixture(
        request=request,
        http_status=200,
        content_type="application/json",
        response_bytes=body,
        response_sha256=response_sha256 or hashlib.sha256(body).hexdigest(),
        received_at=OBSERVED_AT,
    )


class _CountingPort:
    def __init__(self, result: RakutenProductSearchResult) -> None:
        self.calls = 0
        self.result = result

    def search(
        self, request: RakutenProductSearchRequest
    ) -> RakutenProductSearchResult:
        del request
        self.calls += 1
        return self.result


def test_request_is_exactly_one_fixed_selector_and_closed_metadata() -> None:
    product_id = _request()
    product_code = _request(product_id=None, product_code="4900000000000")

    assert product_id.selector_kind is ProductSelectorKind.PRODUCT_ID
    assert product_code.selector_kind is ProductSelectorKind.PRODUCT_CODE
    assert product_id.hits == product_id.page == 1
    assert tuple(element.value for element in product_id.elements) == (
        "affiliateUrl",
        "brandName",
        "count",
        "first",
        "hits",
        "last",
        "makerName",
        "mediumImageUrl",
        "page",
        "pageCount",
        "productCode",
        "productId",
        "productName",
        "productNo",
        "productUrlPC",
    )
    assert PRODUCT_SEARCH_ENDPOINT_PATH.endswith("/Product/Search/20250801")
    assert PRODUCT_SEARCH_FUTURE_SECRET_ALIASES == (
        ("application_id", "rakuten_web_service_application_id"),
        ("access_key", "rakuten_web_service_access_key"),
        ("affiliate_id", "rakuten_affiliate_id"),
    )
    assert PRODUCT_SEARCH_FUTURE_ACCESS_KEY_TRANSPORT == "DEDICATED_HTTP_HEADER_ONLY"

    with pytest.raises(RakutenProductSearchFailure):
        replace(product_id, product_code="4900000000000")
    with pytest.raises(RakutenProductSearchFailure):
        replace(product_id, product_id=None)
    with pytest.raises(RakutenProductSearchFailure):
        replace(product_id, elements=product_id.elements[:-1])


@pytest.mark.parametrize(
    ("search_request", "payload"),
    [
        (_request(), _payload()),
        (
            _request(product_id=None, product_code="4900000000000"),
            _payload(),
        ),
    ],
)
def test_recorded_fixture_returns_one_exact_hash_bound_product(
    search_request: RakutenProductSearchRequest, payload: dict[str, object]
) -> None:
    fixture = _fixture(search_request, payload=payload)
    adapter = RecordedRakutenProductSearchAdapter(
        environment=RuntimeEnvironment.CI,
        fixture_capacity=2,
        fixtures=(fixture,),
    )

    result = adapter.search(search_request)

    assert result.provider_mode is ProductSearchProviderMode.RECORDED_TEST_ONLY
    assert result.request_fingerprint == search_request.fingerprint
    assert result.receipt.purpose is ProductSearchReceiptPurpose.VALIDATION_ONLY
    assert result.receipt.response_sha256 == fixture.response_sha256
    assert result.receipt.received_at == OBSERVED_AT
    assert result.receipt.uri is None
    assert result.receipt.storage_status is ProductSearchStorageStatus.NOT_EXECUTED
    assert (
        result.receipt.persistence_status is ProductSearchPersistenceStatus.NOT_EXECUTED
    )
    assert result.live_eligible is False
    assert not hasattr(result, "response_bytes")
    with pytest.raises(TypeError):
        pickle.dumps(result)


def test_both_selector_fixtures_may_bind_the_same_exact_provider_bytes() -> None:
    product_id_request = _request()
    product_code_request = _request(product_id=None, product_code="4900000000000")
    product_id_fixture = _fixture(product_id_request)
    product_code_fixture = _fixture(product_code_request)
    adapter = RecordedRakutenProductSearchAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        fixture_capacity=2,
        fixtures=(product_id_fixture, product_code_fixture),
    )

    assert product_id_fixture.response_sha256 == product_code_fixture.response_sha256
    assert (
        adapter.search(product_id_request).product.product_id
        == product_id_request.selector_value
    )
    assert (
        adapter.search(product_code_request).product.product_code
        == product_code_request.selector_value
    )


def test_application_calls_the_recorded_port_once_and_rejects_unbound_results() -> None:
    request = _request()
    fixture = _fixture(request)
    port = _CountingPort(fixture.result)

    result = RakutenProductSearchService(
        environment=RuntimeEnvironment.ENV_DEV,
        port=port,
    ).search(request)

    assert result is fixture.result
    assert port.calls == 1

    other = _fixture(_request(product_id=None, product_code="4900000000000"))
    mismatched_port = _CountingPort(other.result)
    with pytest.raises(RakutenProductSearchFailure) as captured:
        RakutenProductSearchService(
            environment=RuntimeEnvironment.CI,
            port=mismatched_port,
        ).search(request)
    assert captured.value.code is RakutenProductSearchFailureCode.RESULT_MISMATCH
    assert mismatched_port.calls == 1

    with pytest.raises(RakutenProductSearchFailure):
        RakutenProductSearchService(
            environment=RuntimeEnvironment.STAGING,
            port=port,
        )


def test_nullable_display_fields_remain_none_without_inference() -> None:
    request = _request()
    payload = _payload()
    item = _item(payload)
    for key in ("brandName", "makerName", "mediumImageUrl", "productName", "productNo"):
        item[key] = None

    product = _fixture(request, payload=payload).result.product

    assert product.brand_name is None
    assert product.maker_name is None
    assert product.medium_image_url is None
    assert product.product_name is None
    assert product.product_no is None


@pytest.mark.parametrize(
    "status",
    [400, 404, 429, 500, 503],
)
def test_recorded_http_failure_classification_never_executes_a_retry(
    status: int,
) -> None:
    failure = classify_product_search_http_status(status)

    expected = {
        400: ProductSearchProviderFailureClass.PERMANENT,
        404: ProductSearchProviderFailureClass.PERMANENT,
        429: ProductSearchProviderFailureClass.THROTTLED_RETRYABLE_DECLARATION_ONLY,
        500: ProductSearchProviderFailureClass.TRANSIENT_RETRYABLE_DECLARATION_ONLY,
        503: ProductSearchProviderFailureClass.TRANSIENT_RETRYABLE_DECLARATION_ONLY,
    }
    assert failure.failure_class is expected[status]
    assert failure.retryable is (status in {429, 500, 503})
    assert failure.retries_executed == 0


def test_unknown_http_failure_status_is_rejected_without_echo() -> None:
    with pytest.raises(RakutenProductSearchFailure) as captured:
        classify_product_search_http_status(418)

    assert captured.value.code is RakutenProductSearchFailureCode.INVALID_ARGUMENT
    assert "418" not in str(captured.value)
    assert "418" not in repr(captured.value)


def test_handoff_and_owner_approval_are_exactly_hash_bound() -> None:
    handoff = (
        REPOSITORY_ROOT
        / "changes/st-0502/DESIGN_HANDOFF_V1_ST0502_RAKUTEN_PRODUCT_SEARCH_OFFLINE_V1.yaml"
    ).read_bytes()
    approval = (
        REPOSITORY_ROOT
        / "changes/st-0502/DESIGN-HANDOFF-APPROVAL-PRODUCT-SEARCH-OFFLINE-v1.yaml"
    ).read_text(encoding="utf-8")

    digest = "c5574b8b7e7941c7781a795ac23f323fefbfc446c4fffecd208fe473bb6bda2d"
    statement = f"SHA-256 {digest} の ST-0502 handoff を承認します。"
    assert len(handoff) == 13_755
    assert hashlib.sha256(handoff).hexdigest() == digest
    assert f"handoff_sha256: {digest}" in approval
    assert f"owner_approval_statement: '{statement}'" in approval
    assert "approved_by: repository_owner:jamozi" in approval


def test_existing_item_search_sources_remain_byte_identical() -> None:
    expected = {
        "python/raos/domain/catalog/rakuten_item_search.py": "4ea7f33ecee122f7e1e57590c2a972ffe7fb9aa493575a547e3354d0f01570c2",
        "python/raos/application/catalog/rakuten_item_search.py": "454c46f66ad473a81395bc08330e7b62635e78c0d1763424227d2f7ebd84688c",
        "python/raos/ports/rakuten_item_search.py": "63983941eeb4a485a3d169073f44c0e4241bdcad452d124cfce1dd07cf2d29fe",
        "python/raos/adapters/recorded_rakuten_item_search.py": "ffdde9dda64800369ac1d90357a6b9300ff104447547bf8c4bb9bf28e89e7dd7",
    }
    assert {
        path: hashlib.sha256((REPOSITORY_ROOT / path).read_bytes()).hexdigest()
        for path in expected
    } == expected

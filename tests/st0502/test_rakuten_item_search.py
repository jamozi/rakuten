"""Strict request, raw, receipt, and canonical-page checks for ST-0502."""

from __future__ import annotations

from dataclasses import replace
import pickle
from typing import Callable, cast
from uuid import UUID

import pytest

from raos.domain.catalog.rakuten_item_search import (
    CANONICAL_ITEM_SEARCH_ELEMENTS,
    ItemSearchElement,
    ItemSearchPurpose,
    ItemSearchSort,
    PersistenceExecutionStatus,
    ProviderFailure,
    ProviderFailureClass,
    ProviderMode,
    RakutenItemSearchCommand,
    RakutenItemSearchFailure,
    RakutenItemSearchFailureCode,
    StorageExecutionStatus,
)

from .support import (
    ENDPOINT_ID,
    RAW_BODY,
    canonical_page,
    item_search_command,
    item_search_request,
    item_search_service,
    raw_response,
    receipt,
)


EXPECTED_REQUEST_JSON = (
    b'{"api_version":"2026-07-01","appoint_delivery_date_only":false,'
    b'"attribute_flag":false,"availability":true,"elements":["affiliateRate",'
    b'"affiliateUrl","availability","catchcopy","count","first","genreId",'
    b'"hits","itemCaption","itemCode","itemName","itemPrice","itemUrl","last",'
    b'"mediumImageUrls","page","pageCount","postageFlag","reviewAverage",'
    b'"reviewCount","shopCode","shopName","smallImageUrls","tagIds",'
    b'"updateTimestamp"],"format_version":2,"genre_information_flag":false,'
    b'"has_review_only":false,"hits":1,"keyword":"synthetic suitcase",'
    b'"or_flag":false,"page":1,"postage_included_only":false,"sort":"standard"}'
)
EXPECTED_REQUEST_SHA256 = (
    "5e2cc017fb58feb61f30569f374fad0be7afb447351cc958e8c0b6e6ea54c9e9"
)


def test_golden_recorded_one_page_item_search() -> None:
    result = item_search_service().search(item_search_command())

    assert result.provider_mode is ProviderMode.RECORDED_TEST_ONLY
    assert result.page.page == 1
    assert result.page.hits == 1
    assert result.page.items[0].item_name == "Untrusted synthetic item"
    assert result.page.items[0].affiliate_url == "https://example.invalid/affiliate"
    assert result.storage_status is StorageExecutionStatus.NOT_EXECUTED
    assert result.persistence_status is PersistenceExecutionStatus.NOT_EXECUTED
    assert result.live_eligible is False


def test_request_canonical_json_and_hash_are_exact() -> None:
    request = item_search_request()
    assert request.canonical_json == EXPECTED_REQUEST_JSON
    assert request.fingerprint == EXPECTED_REQUEST_SHA256
    assert b": " not in request.canonical_json
    assert b", " not in request.canonical_json
    assert (
        request.canonical_json.decode("utf-8").encode("utf-8") == request.canonical_json
    )


def test_canonical_sort_and_element_vocabularies_are_exact() -> None:
    assert {sort.value for sort in ItemSearchSort} == {
        "standard",
        "+reviewCount",
        "-reviewCount",
        "+reviewAverage",
        "-reviewAverage",
        "+itemPrice",
        "-itemPrice",
        "+updateTimestamp",
        "-updateTimestamp",
    }
    assert {element.value for element in ItemSearchElement} == {
        "count",
        "page",
        "first",
        "last",
        "hits",
        "pageCount",
        "itemName",
        "catchcopy",
        "itemCode",
        "itemPrice",
        "itemCaption",
        "itemUrl",
        "affiliateUrl",
        "shopCode",
        "shopName",
        "genreId",
        "reviewCount",
        "reviewAverage",
        "affiliateRate",
        "availability",
        "postageFlag",
        "mediumImageUrls",
        "smallImageUrls",
        "updateTimestamp",
        "tagIds",
    }
    assert CANONICAL_ITEM_SEARCH_ELEMENTS == tuple(
        sorted(ItemSearchElement, key=lambda element: element.value)
    )


@pytest.mark.parametrize(
    ("keyword", "shop_code", "item_code", "genre_id"),
    (
        ("synthetic", None, None, None),
        (None, "synthetic-shop", None, None),
        (None, None, "synthetic-shop:item-1", None),
        (None, None, None, 0),
    ),
)
def test_each_canonical_selector_is_accepted(
    keyword: str | None,
    shop_code: str | None,
    item_code: str | None,
    genre_id: int | None,
) -> None:
    request = replace(
        item_search_request(),
        keyword=keyword,
        shop_code=shop_code,
        item_code=item_code,
        genre_id=genre_id,
    )
    assert request.canonical_json


@pytest.mark.parametrize(
    "factory",
    (
        lambda: replace(item_search_request(), api_version="2026-07-02"),
        lambda: replace(item_search_request(), format_version=True),
        lambda: replace(item_search_request(), hits=0),
        lambda: replace(item_search_request(), hits=31),
        lambda: replace(item_search_request(), page=True),
        lambda: replace(item_search_request(), page=101),
        lambda: replace(item_search_request(), sort=cast(ItemSearchSort, "standard")),
        lambda: replace(item_search_request(), elements=()),
        lambda: replace(
            item_search_request(),
            elements=tuple(reversed(CANONICAL_ITEM_SEARCH_ELEMENTS)),
        ),
        lambda: replace(
            item_search_request(),
            keyword=None,
            shop_code=None,
            item_code=None,
            genre_id=None,
        ),
        lambda: replace(item_search_request(), keyword=" leading"),
        lambda: replace(item_search_request(), item_code="missing-colon"),
        lambda: replace(item_search_request(), genre_id=True),
        lambda: replace(item_search_request(), min_price_jpy=100, max_price_jpy=99),
        lambda: replace(item_search_request(), availability=cast(bool, 1)),
    ),
)
def test_request_rejects_wrong_types_bounds_and_shapes(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(RakutenItemSearchFailure):
        factory()


@pytest.mark.parametrize(
    "purpose",
    (
        ItemSearchPurpose.CATEGORY_DISCOVERY,
        ItemSearchPurpose.ARTICLE_RESEARCH,
        ItemSearchPurpose.OFFER_REFRESH,
    ),
)
def test_command_rejects_non_contract_test_purpose(purpose: ItemSearchPurpose) -> None:
    with pytest.raises(RakutenItemSearchFailure):
        RakutenItemSearchCommand.from_request(
            endpoint_id=ENDPOINT_ID,
            purpose=purpose,
            request=item_search_request(),
        )


def test_command_fingerprint_is_pure_and_bound() -> None:
    first = item_search_command()
    second = item_search_command()
    assert first == second
    assert first.fingerprint == second.fingerprint
    with pytest.raises(RakutenItemSearchFailure):
        replace(first, fingerprint="0" * 64)
    with pytest.raises(RakutenItemSearchFailure):
        RakutenItemSearchCommand.from_request(
            endpoint_id=UUID(int=0),
            purpose=ItemSearchPurpose.CONTRACT_TEST,
            request=item_search_request(),
        )


def test_raw_body_hash_mismatch_fails_closed() -> None:
    with pytest.raises(RakutenItemSearchFailure) as caught:
        raw_response(body_sha256="0" * 64)
    assert caught.value.code is RakutenItemSearchFailureCode.RAW_RESPONSE_INVALID


@pytest.mark.parametrize(
    "factory",
    (
        lambda: raw_response(body=b"[]"),
        lambda: raw_response(body=b'{"a":1,"a":2}'),
        lambda: raw_response(body=b'{"value":NaN}'),
        lambda: raw_response(body=b"\xff\xfe"),
        lambda: raw_response(request_fingerprint="not-a-hash"),
        lambda: raw_response(http_status=True),
        lambda: raw_response(request_id="bad request id"),
    ),
)
def test_raw_response_rejects_non_object_duplicate_or_malformed_input(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(RakutenItemSearchFailure):
        factory()


def test_raw_bytes_are_preserved_but_not_publicly_exposed() -> None:
    response = raw_response()
    assert response.body_size == len(RAW_BODY)
    assert not hasattr(response, "body")
    assert RAW_BODY.decode() not in repr(response)
    with pytest.raises(TypeError):
        pickle.dumps(response)


@pytest.mark.parametrize(
    "factory",
    (
        lambda: replace(receipt(), artifact_id=UUID(int=0)),
        lambda: replace(receipt(), sha256="0"),
        lambda: replace(receipt(), byte_size=True),
        lambda: replace(receipt(), content_type="text/plain"),
        lambda: replace(receipt(), uri=cast(None, "file://not-allowed")),
        lambda: replace(
            receipt(), storage_status=cast(StorageExecutionStatus, "EXECUTED")
        ),
    ),
)
def test_receipt_is_validation_only_and_never_selects_storage(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(RakutenItemSearchFailure):
        factory()


@pytest.mark.parametrize(
    "factory",
    (
        lambda: replace(canonical_page().items[0], availability=cast(bool, 1)),
        lambda: replace(canonical_page().items[0], affiliate_url="javascript:alert(1)"),
        lambda: replace(canonical_page(), items=(canonical_page().items[0],) * 2),
        lambda: replace(canonical_page(), page=2),
        lambda: replace(canonical_page(), warnings=("duplicate", "duplicate")),
    ),
)
def test_canonical_page_rejects_type_binding_and_duplicate_drift(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(RakutenItemSearchFailure):
        factory()


@pytest.mark.parametrize("failure_class", tuple(ProviderFailureClass))
def test_only_transient_provider_failure_is_retryable(
    failure_class: ProviderFailureClass,
) -> None:
    failure = ProviderFailure(failure_class=failure_class, code="TEST_ONLY_FAILURE")
    assert failure.retryable is (failure_class is ProviderFailureClass.TRANSIENT)

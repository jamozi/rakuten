"""Focused offline checks for the owner-local ST-0505 core contracts."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import pickle

import pytest

from raos.application.catalog.rakuten_owner_local import RakutenOwnerLocalService
from raos.domain.catalog.rakuten_item_search_live_request_v1 import (
    LiveItemSearchSortV1,
)
from raos.domain.catalog.rakuten_owner_local import (
    RAKUTEN_OWNER_LOCAL_EVIDENCE_AUTHORITY,
    RAKUTEN_OWNER_LOCAL_PROFILE,
    RakutenOwnerLocalApi,
    RakutenOwnerLocalCredentials,
    RakutenOwnerLocalFailure,
    RakutenOwnerLocalFailureCode,
    RakutenOwnerLocalItemSearchRequest,
    RakutenOwnerLocalOutcome,
    RakutenOwnerLocalProductSearchRequest,
    RakutenOwnerLocalProductSort,
    RakutenOwnerLocalProviderResult,
    RakutenOwnerLocalRequest,
    RakutenOwnerLocalRequestDisposition,
    RakutenOwnerLocalResultEnvelope,
    api_definition,
    fixed_owner_local_smoke_request,
    normalized_record,
    owner_local_api_registry,
)


RUN_ID = "20260821T010203.123456Z-0123456789abcdef0123456789abcdef"
STARTED = datetime(2026, 8, 21, 1, 2, 3, tzinfo=timezone.utc)
FINISHED = datetime(2026, 8, 21, 1, 2, 4, tzinfo=timezone.utc)


def _credentials() -> RakutenOwnerLocalCredentials:
    return RakutenOwnerLocalCredentials(
        profile=RAKUTEN_OWNER_LOCAL_PROFILE,
        _application_id=b"synthetic-application",
        _access_key=b"synthetic-access",
        _affiliate_id=b"synthetic-affiliate",
    )


def _item_request() -> RakutenOwnerLocalItemSearchRequest:
    request = fixed_owner_local_smoke_request(RakutenOwnerLocalApi.ITEM_SEARCH)
    assert type(request) is RakutenOwnerLocalItemSearchRequest
    return request


def _item_result(
    request: RakutenOwnerLocalItemSearchRequest,
) -> RakutenOwnerLocalProviderResult:
    record = normalized_record(
        RakutenOwnerLocalApi.ITEM_SEARCH,
        {
            "affiliateUrl": "https://example.rakuten.co.jp/affiliate",
            "availability": 1,
            "genreId": 1,
            "itemCode": "shop:item",
            "itemName": "untrusted synthetic item",
            "itemPrice": 1000,
            "itemUrl": "https://example.rakuten.co.jp/item",
            "mediumImageUrls": ["https://example.rakuten.co.jp/medium.jpg"],
            "shopCode": "shop",
            "shopName": "untrusted synthetic shop",
            "smallImageUrls": ["https://example.rakuten.co.jp/small.jpg"],
        },
    )
    return RakutenOwnerLocalProviderResult(
        api=RakutenOwnerLocalApi.ITEM_SEARCH,
        request_fingerprint=request.fingerprint,
        http_status=200,
        body_byte_count=256,
        response_sha256="a" * 64,
        count=1,
        page=1,
        first=1,
        last=1,
        hits=1,
        page_count=1,
        records=(record,),
    )


def test_registry_is_closed_and_excludes_review_and_rate_material() -> None:
    registry = owner_local_api_registry()

    assert tuple(definition.api for definition in registry) == (
        RakutenOwnerLocalApi.ITEM_SEARCH,
        RakutenOwnerLocalApi.PRODUCT_SEARCH,
    )
    assert registry[0].api_version == "2026-07-01"
    assert registry[0].path.endswith("/20260701")
    assert registry[1].api_version == "2025-08-01"
    assert registry[1].path.endswith("/20250801")
    assert set(registry[0].normalized_record_fields) == {
        "affiliateUrl",
        "availability",
        "genreId",
        "itemCode",
        "itemName",
        "itemPrice",
        "itemUrl",
        "mediumImageUrls",
        "shopCode",
        "shopName",
        "smallImageUrls",
    }
    assert set(registry[1].normalized_record_fields) == {
        "affiliateUrl",
        "averagePrice",
        "brandName",
        "genreId",
        "genreName",
        "itemCount",
        "maxPrice",
        "mediumImageUrl",
        "minPrice",
        "productCode",
        "productId",
        "productName",
        "productNo",
        "productUrlPC",
        "salesItemCount",
        "salesMaxPrice",
        "salesMinPrice",
        "smallImageUrl",
    }
    for definition in registry:
        assert set(definition.elements).isdisjoint(
            {"reviewAverage", "reviewCount", "affiliateRate"}
        )
        assert set(definition.normalized_record_fields).isdisjoint(
            {"reviewAverage", "reviewCount", "affiliateRate"}
        )


def test_item_wrapper_reuses_policy_but_requires_exactly_one_selector() -> None:
    request = _item_request()

    assert request.policy.keyword == "収納"
    assert request.policy.page == request.policy.hits == 1
    assert request.policy.sort is LiveItemSearchSortV1.STANDARD
    assert request.fingerprint == request.fingerprint
    assert b"review" not in request.canonical_json.lower()
    assert b"affiliateRate" not in request.canonical_json

    with pytest.raises(RakutenOwnerLocalFailure):
        RakutenOwnerLocalItemSearchRequest(
            policy=replace(request.policy, shop_code="synthetic-shop")
        )


@pytest.mark.parametrize(
    ("keyword", "genre_id", "product_id", "product_code"),
    (
        ("収納", None, None, None),
        ("収納", 100, None, None),
        (None, 100, None, None),
        (None, None, "100", None),
        (None, None, None, "code-100"),
    ),
)
def test_product_request_accepts_only_safe_selector_modes(
    keyword: str | None,
    genre_id: int | None,
    product_id: str | None,
    product_code: str | None,
) -> None:
    request = RakutenOwnerLocalProductSearchRequest(
        keyword=keyword,
        genre_id=genre_id,
        product_id=product_id,
        product_code=product_code,
        hits=30,
        page=1,
        sort=RakutenOwnerLocalProductSort.STANDARD,
    )

    assert request.api is RakutenOwnerLocalApi.PRODUCT_SEARCH
    assert b"review" not in request.canonical_json.lower()
    assert request.canonical_json == request.canonical_json


def test_product_request_rejects_mixed_identifier_and_search_modes() -> None:
    with pytest.raises(RakutenOwnerLocalFailure):
        RakutenOwnerLocalProductSearchRequest(
            keyword="収納",
            genre_id=None,
            product_id="100",
            product_code=None,
            hits=1,
            page=1,
            sort=RakutenOwnerLocalProductSort.STANDARD,
        )

    assert tuple(RakutenOwnerLocalProductSort) == (
        RakutenOwnerLocalProductSort.STANDARD,
    )


def test_credentials_are_redacted_but_expose_fixed_transport_getters() -> None:
    credentials = _credentials()

    assert credentials.application_id_query_value() == "synthetic-application"
    assert credentials.access_key_header_value() == "synthetic-access"
    assert credentials.affiliate_id_query_value() == "synthetic-affiliate"
    assert "synthetic" not in repr(credentials)
    assert "synthetic" not in str(credentials)
    with pytest.raises(TypeError):
        pickle.dumps(credentials)


def test_normalized_record_rejects_review_fields_and_bad_numeric_shapes() -> None:
    valid = {
        "affiliateUrl": "https://example.rakuten.co.jp/affiliate",
        "productCode": "code",
        "productId": "id",
        "productUrlPC": "https://example.rakuten.co.jp/product",
        "averagePrice": 1200,
    }
    record = normalized_record(RakutenOwnerLocalApi.PRODUCT_SEARCH, valid)
    assert record.as_object()["averagePrice"] == 1200

    with pytest.raises(RakutenOwnerLocalFailure):
        normalized_record(
            RakutenOwnerLocalApi.PRODUCT_SEARCH,
            {**valid, "reviewCount": 999},
        )
    with pytest.raises(RakutenOwnerLocalFailure):
        normalized_record(
            RakutenOwnerLocalApi.PRODUCT_SEARCH,
            {**valid, "averagePrice": 1.5},
        )


class _Reader:
    def __init__(self) -> None:
        self.calls = 0

    def read(self) -> RakutenOwnerLocalCredentials:
        self.calls += 1
        return _credentials()


class _Transport:
    def __init__(
        self,
        result: RakutenOwnerLocalProviderResult | RakutenOwnerLocalFailure,
    ) -> None:
        self.calls = 0
        self.result = result

    def execute(
        self,
        definition: object,
        request: RakutenOwnerLocalRequest,
        credentials: RakutenOwnerLocalCredentials,
    ) -> RakutenOwnerLocalProviderResult:
        del definition, request, credentials
        self.calls += 1
        if type(self.result) is RakutenOwnerLocalFailure:
            raise self.result
        return self.result


class _Writer:
    def __init__(self) -> None:
        self.preflights = 0
        self.writes: list[RakutenOwnerLocalResultEnvelope] = []

    def preflight(self) -> None:
        self.preflights += 1

    def write(self, envelope: RakutenOwnerLocalResultEnvelope) -> None:
        self.writes.append(envelope)


def _clock() -> object:
    values = iter((STARTED, FINISHED))
    return lambda: next(values)


def test_service_calls_transport_once_writes_once_and_marks_nonformal() -> None:
    request = _item_request()
    reader = _Reader()
    transport = _Transport(_item_result(request))
    writer = _Writer()
    service = RakutenOwnerLocalService(
        credential_reader=reader,
        transport=transport,
        result_writer=writer,
        clock=_clock(),  # type: ignore[arg-type]
    )

    envelope = service.run(
        RakutenOwnerLocalApi.ITEM_SEARCH,
        request,
        run_id=RUN_ID,
    )

    assert envelope.outcome is RakutenOwnerLocalOutcome.SUCCESS
    assert envelope.request_count == 1
    assert reader.calls == transport.calls == writer.preflights == 1
    assert writer.writes == [envelope]
    persisted = envelope.as_result_object()
    assert persisted["evidence_authority"] == RAKUTEN_OWNER_LOCAL_EVIDENCE_AUTHORITY
    assert persisted["formal_tst_016"] == "NOT_EXECUTED"
    assert persisted["staging"] == "NOT_EXECUTED"
    assert persisted["production"] == "NOT_EXECUTED"
    assert persisted["count"] == persisted["page"] == persisted["hits"] == 1
    assert persisted["pageCount"] == 1
    assert type(persisted["items"]) is list
    assert persisted["products"] is None
    assert persisted["provider_data_classification"] == "UNTRUSTED_PROVIDER_DATA"
    assert "synthetic-access" not in str(persisted)
    with pytest.raises(RakutenOwnerLocalFailure) as captured:
        service.run(RakutenOwnerLocalApi.ITEM_SEARCH, request, run_id=RUN_ID)
    assert captured.value.code is RakutenOwnerLocalFailureCode.REQUEST_ALREADY_ATTEMPTED
    assert transport.calls == 1
    assert len(writer.writes) == 1


def test_service_preserves_ambiguous_one_attempt_as_a_written_failure() -> None:
    request = _item_request()
    failure = RakutenOwnerLocalFailure(
        code=RakutenOwnerLocalFailureCode.TIMEOUT,
        disposition=RakutenOwnerLocalRequestDisposition.OUTCOME_AMBIGUOUS,
    )
    transport = _Transport(failure)
    writer = _Writer()
    service = RakutenOwnerLocalService(
        credential_reader=_Reader(),
        transport=transport,
        result_writer=writer,
        clock=_clock(),  # type: ignore[arg-type]
    )

    envelope = service.run(
        RakutenOwnerLocalApi.ITEM_SEARCH,
        request,
        run_id=RUN_ID,
    )

    assert envelope.outcome is RakutenOwnerLocalOutcome.FAILURE
    assert envelope.failure is not None
    assert envelope.failure.code is RakutenOwnerLocalFailureCode.TIMEOUT
    assert envelope.disposition is RakutenOwnerLocalRequestDisposition.OUTCOME_AMBIGUOUS
    assert envelope.request_count == 1
    assert transport.calls == 1
    assert writer.writes == [envelope]


def test_fixed_smoke_is_one_page_standard_for_both_apis() -> None:
    item = fixed_owner_local_smoke_request(RakutenOwnerLocalApi.ITEM_SEARCH)
    product = fixed_owner_local_smoke_request(RakutenOwnerLocalApi.PRODUCT_SEARCH)

    assert type(item) is RakutenOwnerLocalItemSearchRequest
    assert item.policy.keyword == "収納"
    assert item.policy.hits == item.policy.page == 1
    assert type(product) is RakutenOwnerLocalProductSearchRequest
    assert product.keyword == "収納"
    assert product.hits == product.page == 1
    assert product.sort is RakutenOwnerLocalProductSort.STANDARD
    assert api_definition(item.api).allowed_sorts == (
        "standard",
        "+itemPrice",
        "-itemPrice",
        "+updateTimestamp",
        "-updateTimestamp",
    )

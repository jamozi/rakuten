"""Focused offline checks for the owner-local ST-0505 core contracts."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
import pickle

import pytest

from scripts import rakuten_owner_local as owner_local_cli
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
    **record_overrides: object,
) -> RakutenOwnerLocalProviderResult:
    fields: dict[str, object] = {
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
    }
    fields.update(record_overrides)
    record = normalized_record(RakutenOwnerLocalApi.ITEM_SEARCH, fields)
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


def _product_result(
    request: RakutenOwnerLocalProductSearchRequest,
    *,
    product_name: str = "untrusted synthetic product",
    product_url_pc: str = "https://example.rakuten.co.jp/product",
) -> RakutenOwnerLocalProviderResult:
    record = normalized_record(
        RakutenOwnerLocalApi.PRODUCT_SEARCH,
        {
            "affiliateUrl": "https://example.rakuten.co.jp/affiliate-product",
            "productCode": "synthetic-product-code",
            "productId": "synthetic-product-id",
            "productName": product_name,
            "productUrlPC": product_url_pc,
        },
    )
    return RakutenOwnerLocalProviderResult(
        api=RakutenOwnerLocalApi.PRODUCT_SEARCH,
        request_fingerprint=request.fingerprint,
        http_status=200,
        body_byte_count=256,
        response_sha256="b" * 64,
        count=1,
        page=1,
        first=1,
        last=1,
        hits=1,
        page_count=1,
        records=(record,),
    )


def _minimal_provider_result(
    api: RakutenOwnerLocalApi,
    request: RakutenOwnerLocalRequest,
    **summary_overrides: int,
) -> RakutenOwnerLocalProviderResult:
    record = normalized_record(
        api,
        (
            {
                "affiliateUrl": None,
                "itemCode": "shop:item",
                "itemName": "untrusted item",
                "itemPrice": 22,
                "itemUrl": "https://example.rakuten.co.jp/item",
            }
            if api is RakutenOwnerLocalApi.ITEM_SEARCH
            else {
                "affiliateUrl": None,
                "productCode": "product-code",
                "productId": "product-id",
                "productUrlPC": "https://example.rakuten.co.jp/product",
            }
        ),
    )
    summary = {
        "count": 2,
        "page": 1,
        "first": 1,
        "last": 1,
        "hits": (
            request.policy.hits
            if type(request) is RakutenOwnerLocalItemSearchRequest
            else request.hits
        ),
        "page_count": 2,
    }
    summary.update(summary_overrides)
    return RakutenOwnerLocalProviderResult(
        api=api,
        request_fingerprint=request.fingerprint,
        http_status=200,
        body_byte_count=256,
        response_sha256="c" * 64,
        records=(record,),
        **summary,
    )


def _credentials_with_summary_value(
    credential_name: str,
    value: str,
) -> RakutenOwnerLocalCredentials:
    values = [b"application-no-match", b"header-no-match", b"affiliate-no-match"]
    index = {
        "application_id": 0,
        "access_key": 1,
        "affiliate_id": 2,
    }[credential_name]
    values[index] = value.encode("ascii")
    return RakutenOwnerLocalCredentials(
        profile=RAKUTEN_OWNER_LOCAL_PROFILE,
        _application_id=values[0],
        _access_key=values[1],
        _affiliate_id=values[2],
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


@pytest.mark.parametrize(
    ("api", "field", "valid"),
    (
        (
            RakutenOwnerLocalApi.ITEM_SEARCH,
            "itemCode",
            {
                "affiliateUrl": None,
                "itemCode": "shop:item",
                "itemName": "untrusted item",
                "itemPrice": 22,
                "itemUrl": "https://example.rakuten.co.jp/item",
            },
        ),
        (
            RakutenOwnerLocalApi.ITEM_SEARCH,
            "itemName",
            {
                "affiliateUrl": None,
                "itemCode": "shop:item",
                "itemName": "untrusted item",
                "itemPrice": 22,
                "itemUrl": "https://example.rakuten.co.jp/item",
            },
        ),
        (
            RakutenOwnerLocalApi.PRODUCT_SEARCH,
            "productCode",
            {
                "affiliateUrl": None,
                "productCode": "product-code",
                "productId": "product-id",
                "productUrlPC": "https://example.rakuten.co.jp/product",
            },
        ),
        (
            RakutenOwnerLocalApi.PRODUCT_SEARCH,
            "productId",
            {
                "affiliateUrl": None,
                "productCode": "product-code",
                "productId": "product-id",
                "productUrlPC": "https://example.rakuten.co.jp/product",
            },
        ),
    ),
)
@pytest.mark.parametrize(
    "invalid_value",
    (None, "", " ", " padded", "padded ", 7, "x" * 20_001),
)
def test_normalized_record_requires_bounded_nonempty_mandatory_text(
    api: RakutenOwnerLocalApi,
    field: str,
    valid: dict[str, object],
    invalid_value: object,
) -> None:
    with pytest.raises(RakutenOwnerLocalFailure) as failure:
        normalized_record(api, {**valid, field: invalid_value})

    assert failure.value.code is RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT


def test_optional_text_fields_keep_existing_nullability() -> None:
    item = normalized_record(
        RakutenOwnerLocalApi.ITEM_SEARCH,
        {
            "affiliateUrl": None,
            "itemCode": "shop:item",
            "itemName": "untrusted item",
            "itemPrice": 22,
            "itemUrl": "https://example.rakuten.co.jp/item",
            "shopCode": None,
            "shopName": "",
        },
    )
    product = normalized_record(
        RakutenOwnerLocalApi.PRODUCT_SEARCH,
        {
            "affiliateUrl": None,
            "productCode": "product-code",
            "productId": "product-id",
            "productName": None,
            "productUrlPC": "https://example.rakuten.co.jp/product",
        },
    )

    assert item.as_object()["shopCode"] is None
    assert item.as_object()["shopName"] == ""
    assert product.as_object()["productName"] is None


@pytest.mark.parametrize(
    ("api", "mandatory_url", "valid"),
    (
        (
            RakutenOwnerLocalApi.ITEM_SEARCH,
            "itemUrl",
            {
                "affiliateUrl": None,
                "itemCode": "shop:item",
                "itemName": "untrusted item",
                "itemPrice": 100,
                "itemUrl": "https://example.rakuten.co.jp/item",
            },
        ),
        (
            RakutenOwnerLocalApi.PRODUCT_SEARCH,
            "productUrlPC",
            {
                "affiliateUrl": None,
                "productCode": "code",
                "productId": "id",
                "productUrlPC": "https://example.rakuten.co.jp/product",
            },
        ),
    ),
)
@pytest.mark.parametrize(
    "invalid_value",
    (None, "", 7, "http://example.rakuten.co.jp/not-https"),
)
def test_normalized_record_requires_non_null_https_mandatory_result_url(
    api: RakutenOwnerLocalApi,
    mandatory_url: str,
    valid: dict[str, object],
    invalid_value: object,
) -> None:
    with pytest.raises(RakutenOwnerLocalFailure) as failure:
        normalized_record(api, {**valid, mandatory_url: invalid_value})

    assert failure.value.code is RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT


def test_normalized_record_preserves_optional_product_url_nullability() -> None:
    record = normalized_record(
        RakutenOwnerLocalApi.PRODUCT_SEARCH,
        {
            "affiliateUrl": None,
            "mediumImageUrl": None,
            "productCode": "code",
            "productId": "id",
            "productUrlPC": "https://example.rakuten.co.jp/product",
            "smallImageUrl": None,
        },
    )

    assert record.as_object()["affiliateUrl"] is None
    assert record.as_object()["mediumImageUrl"] is None
    assert record.as_object()["smallImageUrl"] is None

    item = normalized_record(
        RakutenOwnerLocalApi.ITEM_SEARCH,
        {
            "affiliateUrl": None,
            "itemCode": "shop:item",
            "itemName": "untrusted item",
            "itemPrice": 100,
            "itemUrl": "https://example.rakuten.co.jp/item",
        },
    )
    assert item.as_object()["affiliateUrl"] is None

    with pytest.raises(RakutenOwnerLocalFailure) as invalid_optional_url:
        normalized_record(
            RakutenOwnerLocalApi.PRODUCT_SEARCH,
            {
                "affiliateUrl": None,
                "productCode": "code",
                "productId": "id",
                "productUrlPC": "https://example.rakuten.co.jp/product",
                "smallImageUrl": "http://example.rakuten.co.jp/not-https",
            },
        )
    assert (
        invalid_optional_url.value.code
        is RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT
    )


def _record_with_test_url(position: str, value: str) -> object:
    if position == "mandatory":
        return normalized_record(
            RakutenOwnerLocalApi.ITEM_SEARCH,
            {
                "affiliateUrl": None,
                "itemCode": "shop:item",
                "itemName": "untrusted item",
                "itemPrice": 100,
                "itemUrl": value,
            },
        )
    if position == "optional":
        return normalized_record(
            RakutenOwnerLocalApi.PRODUCT_SEARCH,
            {
                "affiliateUrl": None,
                "productCode": "code",
                "productId": "id",
                "productUrlPC": "https://example.rakuten.co.jp/product",
                "smallImageUrl": value,
            },
        )
    assert position == "list"
    return normalized_record(
        RakutenOwnerLocalApi.ITEM_SEARCH,
        {
            "affiliateUrl": None,
            "itemCode": "shop:item",
            "itemName": "untrusted item",
            "itemPrice": 100,
            "itemUrl": "https://example.rakuten.co.jp/item",
            "smallImageUrls": [value],
        },
    )


@pytest.mark.parametrize("position", ("mandatory", "optional", "list"))
@pytest.mark.parametrize(
    "invalid_url",
    (
        "https://example .com/item",
        "https://example.com/item name",
        "https://example.com/\titem",
        "https://example.com/\\item",
        "https://example.com/\x1fitem",
        "https://example.com/\x7fitem",
        "https://example.com/\u0085item",
        "HTTPS://example.com/item",
        "https://-example.com/item",
        "https://example-.com/item",
        "https://example..com/item",
        "https://exa_mple.com/item",
        f"https://{'a' * 64}.example/item",
        f"https://{'a' * 63}.{'b' * 63}.{'c' * 63}.{'d' * 63}.example/item",
        "https://example.com\\@evil.invalid/item",
        "https://[not-ipv6]/item",
        "https://example.com:abc/item",
        "https://user@example.com/item",
        "https://user:password@example.com/item",
        "https://example.com/item#fragment",
        "https://example.com/%",
        "https://example.com/%2",
        "https://example.com/%GG",
        "https://example.com/item?q=%0",
    ),
)
def test_all_normalized_url_positions_reject_hostile_syntax(
    position: str,
    invalid_url: str,
) -> None:
    with pytest.raises(RakutenOwnerLocalFailure) as failure:
        _record_with_test_url(position, invalid_url)

    assert failure.value.code is RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT


@pytest.mark.parametrize("position", ("mandatory", "optional", "list"))
@pytest.mark.parametrize(
    "valid_url",
    (
        "https://例え.テスト/商品?q=収納",
        "https://xn--r8jz45g.xn--zckzah/item",
        "https://[2001:DB8::1]/item",
        "https://[2001:db8::1]:8443/item?q=one%20two",
        "https://example.com.:443/item?next=%2Fcatalog%3Fa%3D1",
        "https://192.0.2.1/item?x=1&y=2",
    ),
)
def test_all_normalized_url_positions_preserve_valid_url_forms(
    position: str,
    valid_url: str,
) -> None:
    _record_with_test_url(position, valid_url)


@pytest.mark.parametrize(
    ("api", "valid", "missing_url"),
    (
        (
            RakutenOwnerLocalApi.ITEM_SEARCH,
            {
                "affiliateUrl": None,
                "itemCode": "shop:item",
                "itemName": "untrusted item",
                "itemPrice": 100,
                "itemUrl": "https://example.rakuten.co.jp/item",
            },
            "itemUrl",
        ),
        (
            RakutenOwnerLocalApi.PRODUCT_SEARCH,
            {
                "affiliateUrl": None,
                "productCode": "code",
                "productId": "id",
                "productUrlPC": "https://example.rakuten.co.jp/product",
            },
            "productUrlPC",
        ),
    ),
)
def test_normalized_record_requires_mandatory_result_url_key(
    api: RakutenOwnerLocalApi,
    valid: dict[str, object],
    missing_url: str,
) -> None:
    without_url = dict(valid)
    without_url.pop(missing_url)

    with pytest.raises(RakutenOwnerLocalFailure) as failure:
        normalized_record(api, without_url)

    assert failure.value.code is RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT


def test_provider_result_summary_relationships_are_domain_invariants() -> None:
    request = _item_request()
    result = _item_result(request)

    empty = replace(
        result,
        count=0,
        first=0,
        last=0,
        page_count=0,
        records=(),
    )
    assert empty.records == ()
    capped = replace(result, count=101, page_count=100)
    assert capped.page_count == 100

    for contradictory in (
        {"count": 0},
        {"first": 0},
        {"last": 2},
        {"page_count": 0},
        {"page_count": 101},
    ):
        with pytest.raises(RakutenOwnerLocalFailure) as failure:
            replace(result, **contradictory)
        assert failure.value.code is RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT


class _Reader:
    def __init__(self, credentials: RakutenOwnerLocalCredentials | None = None) -> None:
        self.calls = 0
        self.credentials = _credentials() if credentials is None else credentials

    def read(self) -> RakutenOwnerLocalCredentials:
        self.calls += 1
        return self.credentials


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


@pytest.mark.parametrize(
    ("selector_field", "requested_value"),
    (("itemCode", "requested-shop:item"), ("shopCode", "requested-shop")),
)
def test_service_item_identity_mismatch_precedes_credential_reflection(
    selector_field: str,
    requested_value: str,
) -> None:
    base = _item_request()
    if selector_field == "itemCode":
        policy = replace(base.policy, keyword=None, item_code=requested_value)
    else:
        policy = replace(base.policy, keyword=None, shop_code=requested_value)
    request = RakutenOwnerLocalItemSearchRequest(policy=policy)
    result = _item_result(
        request,
        **{
            selector_field: "different-provider-value",
            "itemName": "untrusted synthetic-access reflected item",
        },
    )
    writer = _Writer()
    envelope = RakutenOwnerLocalService(
        credential_reader=_Reader(
            _credentials_with_summary_value("application_id", "1")
        ),
        transport=_Transport(result),
        result_writer=writer,
        clock=_clock(),  # type: ignore[arg-type]
    ).run(RakutenOwnerLocalApi.ITEM_SEARCH, request, run_id=RUN_ID)

    assert envelope.outcome is RakutenOwnerLocalOutcome.FAILURE
    assert envelope.provider_result is None
    assert envelope.failure is not None
    assert envelope.failure.code is RakutenOwnerLocalFailureCode.RESULT_MISMATCH
    assert (
        envelope.failure.disposition
        is RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED
    )
    assert envelope.failure.http_status == result.http_status
    assert envelope.failure.body_byte_count == result.body_byte_count
    assert envelope.failure.response_sha256 == result.response_sha256
    assert envelope.request_count == 1
    assert envelope.as_result_object()["items"] is None
    assert writer.writes == [envelope]
    persisted = json.dumps(envelope.as_result_object(), sort_keys=True)
    assert "different-provider-value" not in persisted
    assert "synthetic-access" not in persisted


def test_service_product_identity_mismatch_uses_the_shared_binding_boundary() -> None:
    request = fixed_owner_local_smoke_request(RakutenOwnerLocalApi.PRODUCT_SEARCH)
    assert type(request) is RakutenOwnerLocalProductSearchRequest
    request = replace(
        request,
        keyword=None,
        product_id="requested-product-id",
    )
    result = _product_result(
        request,
        product_name="untrusted synthetic-access reflected product",
    )
    fields = result.records[0].as_object()
    fields["productId"] = "different-provider-value"
    result = replace(
        result,
        records=(normalized_record(RakutenOwnerLocalApi.PRODUCT_SEARCH, fields),),
    )
    writer = _Writer()
    envelope = RakutenOwnerLocalService(
        credential_reader=_Reader(
            _credentials_with_summary_value("application_id", "1")
        ),
        transport=_Transport(result),
        result_writer=writer,
        clock=_clock(),  # type: ignore[arg-type]
    ).run(RakutenOwnerLocalApi.PRODUCT_SEARCH, request, run_id=RUN_ID)

    assert envelope.outcome is RakutenOwnerLocalOutcome.FAILURE
    assert envelope.provider_result is None
    assert envelope.failure is not None
    assert envelope.failure.code is RakutenOwnerLocalFailureCode.RESULT_MISMATCH
    assert envelope.failure.request_count == 1
    assert envelope.failure.http_status == result.http_status
    assert envelope.failure.body_byte_count == result.body_byte_count
    assert envelope.failure.response_sha256 == result.response_sha256
    assert envelope.as_result_object()["products"] is None
    assert writer.writes == [envelope]
    persisted = json.dumps(envelope.as_result_object(), sort_keys=True)
    assert "different-provider-value" not in persisted
    assert "synthetic-access" not in persisted


@pytest.mark.parametrize(
    "credential_value",
    ("synthetic-application", "synthetic-access", "synthetic-affiliate"),
)
@pytest.mark.parametrize(
    "position",
    ("url", "mandatory-url", "ordinary-text", "nested-url-list"),
)
def test_service_rejects_each_reflected_credential_before_persistence(
    credential_value: str,
    position: str,
) -> None:
    request = _item_request()
    source_result = _item_result(request)
    fields = source_result.records[0].as_object()
    if position == "url":
        fields["affiliateUrl"] = (
            f"https://example.rakuten.co.jp/affiliate/{credential_value}"
        )
    elif position == "mandatory-url":
        fields["itemUrl"] = f"https://example.rakuten.co.jp/item/{credential_value}"
    elif position == "ordinary-text":
        fields["itemName"] = f"untrusted {credential_value} reflected item"
    else:
        fields["smallImageUrls"] = [
            f"https://example.rakuten.co.jp/{credential_value}/small.jpg"
        ]
    reflected_result = replace(
        source_result,
        records=(normalized_record(RakutenOwnerLocalApi.ITEM_SEARCH, fields),),
    )
    writer = _Writer()
    envelope = RakutenOwnerLocalService(
        credential_reader=_Reader(),
        transport=_Transport(reflected_result),
        result_writer=writer,
        clock=_clock(),  # type: ignore[arg-type]
    ).run(RakutenOwnerLocalApi.ITEM_SEARCH, request, run_id=RUN_ID)

    assert envelope.outcome is RakutenOwnerLocalOutcome.FAILURE
    assert envelope.provider_result is None
    assert envelope.failure is not None
    assert envelope.failure.code is RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT
    assert (
        envelope.failure.disposition
        is RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED
    )
    assert envelope.failure.http_status == reflected_result.http_status
    assert envelope.failure.body_byte_count == reflected_result.body_byte_count
    assert envelope.failure.response_sha256 == reflected_result.response_sha256
    assert envelope.request_count == 1
    assert writer.writes == [envelope]
    persisted = json.dumps(
        envelope.as_result_object(),
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    for known_value in (
        "synthetic-application",
        "synthetic-access",
        "synthetic-affiliate",
    ):
        assert known_value not in persisted
        assert known_value not in str(envelope.failure)
        assert known_value not in repr(envelope.failure)


def test_service_rejects_numeric_credential_reflected_as_integer() -> None:
    request = _item_request()
    source_result = _item_result(request)
    credentials = RakutenOwnerLocalCredentials(
        profile=RAKUTEN_OWNER_LOCAL_PROFILE,
        _application_id=b"1000",
        _access_key=b"synthetic-access",
        _affiliate_id=b"synthetic-affiliate",
    )
    writer = _Writer()
    envelope = RakutenOwnerLocalService(
        credential_reader=_Reader(credentials),
        transport=_Transport(source_result),
        result_writer=writer,
        clock=_clock(),  # type: ignore[arg-type]
    ).run(RakutenOwnerLocalApi.ITEM_SEARCH, request, run_id=RUN_ID)

    assert envelope.outcome is RakutenOwnerLocalOutcome.FAILURE
    assert envelope.failure is not None
    assert envelope.failure.code is RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT
    assert envelope.failure.request_count == 1
    assert envelope.failure.http_status == 200
    assert "1000" not in json.dumps(envelope.as_result_object(), sort_keys=True)
    assert writer.writes == [envelope]


@pytest.mark.parametrize(
    "api",
    (RakutenOwnerLocalApi.ITEM_SEARCH, RakutenOwnerLocalApi.PRODUCT_SEARCH),
)
@pytest.mark.parametrize(
    ("summary_field", "summary_value"),
    (
        ("count", 7),
        ("page", 1),
        ("first", 1),
        ("last", 1),
        ("hits", 7),
        ("page_count", 7),
    ),
)
@pytest.mark.parametrize(
    "credential_name",
    ("application_id", "access_key", "affiliate_id"),
)
def test_service_rejects_each_credential_reflected_in_each_summary_scalar(
    api: RakutenOwnerLocalApi,
    summary_field: str,
    summary_value: int,
    credential_name: str,
) -> None:
    request = fixed_owner_local_smoke_request(api)
    if summary_field == "hits":
        if type(request) is RakutenOwnerLocalItemSearchRequest:
            request = RakutenOwnerLocalItemSearchRequest(
                policy=replace(request.policy, hits=summary_value)
            )
        else:
            assert type(request) is RakutenOwnerLocalProductSearchRequest
            request = replace(request, hits=summary_value)
    result = _minimal_provider_result(
        api,
        request,
        **{summary_field: summary_value},
    )
    writer = _Writer()
    envelope = RakutenOwnerLocalService(
        credential_reader=_Reader(
            _credentials_with_summary_value(credential_name, str(summary_value))
        ),
        transport=_Transport(result),
        result_writer=writer,
        clock=_clock(),  # type: ignore[arg-type]
    ).run(api, request, run_id=RUN_ID)

    assert envelope.outcome is RakutenOwnerLocalOutcome.FAILURE
    assert envelope.provider_result is None
    assert envelope.failure is not None
    assert envelope.failure.code is RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT
    assert envelope.failure.request_count == 1
    assert envelope.failure.http_status == result.http_status
    assert envelope.failure.body_byte_count == result.body_byte_count
    assert envelope.failure.response_sha256 == result.response_sha256
    assert envelope.request_count == 1
    persisted = envelope.as_result_object()
    assert persisted["items"] is None
    assert persisted["products"] is None
    assert persisted["provider_data_classification"] is None
    assert all(
        persisted[field] is None for field in ("count", "page", "hits", "pageCount")
    )
    assert writer.writes == [envelope]


@pytest.mark.parametrize("binding", ("api", "fingerprint", "hits"))
def test_result_binding_mismatch_precedes_summary_credential_reflection(
    binding: str,
) -> None:
    request = _item_request()
    if binding == "api":
        product_request = fixed_owner_local_smoke_request(
            RakutenOwnerLocalApi.PRODUCT_SEARCH
        )
        result = replace(
            _minimal_provider_result(
                RakutenOwnerLocalApi.PRODUCT_SEARCH,
                product_request,
            ),
            request_fingerprint=request.fingerprint,
        )
    else:
        result = _minimal_provider_result(RakutenOwnerLocalApi.ITEM_SEARCH, request)
        if binding == "fingerprint":
            result = replace(result, request_fingerprint="d" * 64)
        else:
            assert binding == "hits"
            result = replace(result, hits=2)
    envelope = RakutenOwnerLocalService(
        credential_reader=_Reader(
            _credentials_with_summary_value("application_id", "1")
        ),
        transport=_Transport(result),
        result_writer=_Writer(),
        clock=_clock(),  # type: ignore[arg-type]
    ).run(RakutenOwnerLocalApi.ITEM_SEARCH, request, run_id=RUN_ID)

    assert envelope.outcome is RakutenOwnerLocalOutcome.FAILURE
    assert envelope.provider_result is None
    assert envelope.failure is not None
    assert envelope.failure.code is RakutenOwnerLocalFailureCode.RESULT_MISMATCH
    assert envelope.failure.request_count == 1
    assert envelope.failure.http_status == 200
    assert envelope.as_result_object()["items"] is None


def test_cli_emits_only_fixed_failure_for_summary_credential_reflection() -> None:
    request = _item_request()
    result = _minimal_provider_result(RakutenOwnerLocalApi.ITEM_SEARCH, request)
    writer = _Writer()
    code, message = owner_local_cli._execute_request(  # noqa: SLF001
        RakutenOwnerLocalApi.ITEM_SEARCH.value,
        request,
        reader=_Reader(_credentials_with_summary_value("application_id", "1")),
        writer=writer,
        transport=_Transport(result),
    )

    assert code == 1
    assert message == "RAKUTEN_OWNER_LOCAL_FAIL_RESPONSE_SCHEMA_DRIFT"
    assert len(writer.writes) == 1
    envelope = writer.writes[0]
    assert envelope.provider_result is None
    assert envelope.failure is not None
    assert envelope.failure.request_count == 1
    assert envelope.as_result_object()["items"] is None


def test_service_rejects_url_encoded_credential_reflection() -> None:
    request = _item_request()
    source_result = _item_result(request)
    fields = source_result.records[0].as_object()
    fields["affiliateUrl"] = (
        "https://example.rakuten.co.jp/affiliate/synthetic%2fapplication"
    )
    reflected_result = replace(
        source_result,
        records=(normalized_record(RakutenOwnerLocalApi.ITEM_SEARCH, fields),),
    )
    credentials = RakutenOwnerLocalCredentials(
        profile=RAKUTEN_OWNER_LOCAL_PROFILE,
        _application_id=b"synthetic/application",
        _access_key=b"synthetic-access",
        _affiliate_id=b"synthetic-affiliate",
    )
    writer = _Writer()
    envelope = RakutenOwnerLocalService(
        credential_reader=_Reader(credentials),
        transport=_Transport(reflected_result),
        result_writer=writer,
        clock=_clock(),  # type: ignore[arg-type]
    ).run(RakutenOwnerLocalApi.ITEM_SEARCH, request, run_id=RUN_ID)

    assert envelope.outcome is RakutenOwnerLocalOutcome.FAILURE
    assert envelope.failure is not None
    assert envelope.failure.code is RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT
    assert envelope.failure.request_count == 1
    persisted = json.dumps(envelope.as_result_object(), sort_keys=True)
    assert "synthetic/application" not in persisted
    assert "synthetic%2fapplication" not in persisted
    assert writer.writes == [envelope]


@pytest.mark.parametrize("position", ("ordinary-text", "mandatory-url"))
def test_service_rejects_product_credential_reflection(position: str) -> None:
    request = fixed_owner_local_smoke_request(RakutenOwnerLocalApi.PRODUCT_SEARCH)
    assert type(request) is RakutenOwnerLocalProductSearchRequest
    result = _product_result(
        request,
        product_name=(
            "untrusted synthetic-affiliate reflected product"
            if position == "ordinary-text"
            else "untrusted synthetic product"
        ),
        product_url_pc=(
            "https://example.rakuten.co.jp/product/synthetic-affiliate"
            if position == "mandatory-url"
            else "https://example.rakuten.co.jp/product"
        ),
    )
    writer = _Writer()
    envelope = RakutenOwnerLocalService(
        credential_reader=_Reader(),
        transport=_Transport(result),
        result_writer=writer,
        clock=_clock(),  # type: ignore[arg-type]
    ).run(RakutenOwnerLocalApi.PRODUCT_SEARCH, request, run_id=RUN_ID)

    assert envelope.outcome is RakutenOwnerLocalOutcome.FAILURE
    assert envelope.failure is not None
    assert envelope.failure.code is RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT
    assert envelope.failure.request_count == 1
    persisted = json.dumps(envelope.as_result_object(), sort_keys=True)
    assert "synthetic-affiliate" not in persisted
    assert envelope.as_result_object()["products"] is None
    assert writer.writes == [envelope]


def test_result_binding_mismatch_precedes_credential_reflection() -> None:
    request = _item_request()
    source_result = _item_result(request)
    fields = source_result.records[0].as_object()
    fields["itemName"] = "untrusted synthetic-access reflected item"
    result = replace(
        source_result,
        request_fingerprint="b" * 64,
        records=(normalized_record(RakutenOwnerLocalApi.ITEM_SEARCH, fields),),
    )
    writer = _Writer()
    envelope = RakutenOwnerLocalService(
        credential_reader=_Reader(),
        transport=_Transport(result),
        result_writer=writer,
        clock=_clock(),  # type: ignore[arg-type]
    ).run(RakutenOwnerLocalApi.ITEM_SEARCH, request, run_id=RUN_ID)

    assert envelope.outcome is RakutenOwnerLocalOutcome.FAILURE
    assert envelope.failure is not None
    assert envelope.failure.code is RakutenOwnerLocalFailureCode.RESULT_MISMATCH
    assert envelope.failure.request_count == 1
    assert "synthetic-access" not in json.dumps(
        envelope.as_result_object(), sort_keys=True
    )


def test_near_miss_credential_text_remains_a_valid_result() -> None:
    request = _item_request()
    source_result = _item_result(request)
    fields = source_result.records[0].as_object()
    fields["itemName"] = "untrusted synthetic-accesx item"
    result = replace(
        source_result,
        records=(normalized_record(RakutenOwnerLocalApi.ITEM_SEARCH, fields),),
    )
    writer = _Writer()
    envelope = RakutenOwnerLocalService(
        credential_reader=_Reader(),
        transport=_Transport(result),
        result_writer=writer,
        clock=_clock(),  # type: ignore[arg-type]
    ).run(RakutenOwnerLocalApi.ITEM_SEARCH, request, run_id=RUN_ID)

    assert envelope.outcome is RakutenOwnerLocalOutcome.SUCCESS
    assert envelope.request_count == 1
    assert "synthetic-accesx" in json.dumps(envelope.as_result_object(), sort_keys=True)


def test_cli_emits_only_fixed_failure_for_credential_reflection() -> None:
    request = _item_request()
    source_result = _item_result(request)
    fields = source_result.records[0].as_object()
    fields["itemName"] = "untrusted synthetic-access reflected item"
    result = replace(
        source_result,
        records=(normalized_record(RakutenOwnerLocalApi.ITEM_SEARCH, fields),),
    )
    code, message = owner_local_cli._execute_request(  # noqa: SLF001
        RakutenOwnerLocalApi.ITEM_SEARCH.value,
        request,
        reader=_Reader(),
        writer=_Writer(),
        transport=_Transport(result),
    )

    assert code == 1
    assert message == "RAKUTEN_OWNER_LOCAL_FAIL_RESPONSE_SCHEMA_DRIFT"
    for known_value in (
        "synthetic-application",
        "synthetic-access",
        "synthetic-affiliate",
    ):
        assert known_value not in message


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

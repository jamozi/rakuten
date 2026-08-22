"""Focused offline checks for the owner-local ST-0505 core contracts."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
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
    RakutenOwnerLocalCredentialField,
    RakutenOwnerLocalCredentialFieldCategory,
    RakutenOwnerLocalCredentialKind,
    RakutenOwnerLocalCredentialReflection,
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
    RakutenOwnerLocalValidationDetailCode,
    RakutenOwnerLocalValidationStageCode,
    api_definition,
    fixed_owner_local_smoke_request,
    normalized_record,
    owner_local_api_registry,
)


RUN_ID = "20260821T010203.123456Z-0123456789abcdef0123456789abcdef"
STARTED = datetime(2026, 8, 21, 1, 2, 3, tzinfo=timezone.utc)
FINISHED = datetime(2026, 8, 21, 1, 2, 4, tzinfo=timezone.utc)
RESULT_OBJECT_KEYS = (
    "schema",
    "version",
    "run_id",
    "started_at",
    "finished_at",
    "api",
    "endpoint_id",
    "api_version",
    "outcome",
    "diagnostic_code",
    "validation_stage_code",
    "validation_detail_code",
    "request_fingerprint",
    "request_disposition",
    "request_count",
    "retry_count",
    "pagination_count",
    "http_status",
    "body_byte_count",
    "response_sha256",
    "count",
    "page",
    "first",
    "last",
    "hits",
    "pageCount",
    "items",
    "products",
    "provider_data_classification",
    "evidence_authority",
    "formal_tst_016",
    "staging",
    "production",
    "od_015",
)
REFLECTION_DIAGNOSTIC_OBJECT_KEYS = (
    "schema",
    "version",
    "run_id",
    "started_at",
    "finished_at",
    "api",
    "endpoint_id",
    "api_version",
    "outcome",
    "diagnostic_outcome",
    "diagnostic_code",
    "validation_stage_code",
    "reflection_credential_kind",
    "reflection_field_name",
    "reflection_field_category",
    "request_fingerprint",
    "request_disposition",
    "request_count",
    "retry_count",
    "pagination_count",
    "http_status",
    "body_byte_count",
    "response_sha256",
    "provider_data_persisted",
    "evidence_authority",
    "formal_tst_016",
    "staging",
    "production",
    "od_015",
)


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
        "https://example.com/item\u00a0name",
        "https://example.com/item\u2028name",
        "https://example.com/item\u200bname",
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
    one_page = replace(result, count=10, hits=10, page_count=1)
    assert one_page.page_count == 1
    partial_final_page = replace(result, count=11, hits=10, page_count=2)
    assert partial_final_page.page_count == 2
    exact_cap = replace(result, count=100, page_count=100)
    assert exact_cap.page_count == 100
    capped = replace(result, count=101, page_count=100)
    assert capped.page_count == 100

    for contradictory in (
        {"count": 0},
        {"first": 0},
        {"last": 2},
        {"page_count": 0},
        {"page_count": 101},
        {"count": 50, "hits": 10, "page_count": 1},
        {"count": 50, "hits": 10, "page_count": 6},
        {"count": 11, "hits": 10, "page_count": 1},
        {"count": 100, "page_count": 99},
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


def _backward_clock() -> object:
    values = iter((STARTED, STARTED - timedelta(seconds=1)))
    return lambda: next(values)


def _invalid_finished_clock() -> object:
    values = iter((STARTED, FINISHED.replace(tzinfo=None)))
    return lambda: next(values)


class _TerminalClockFailure(BaseException):
    pass


def _raising_finished_clock() -> object:
    first = True

    def sample() -> datetime:
        nonlocal first
        if first:
            first = False
            return STARTED
        raise _TerminalClockFailure

    return sample


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
    assert persisted["schema"] == "RAOS_ST0505_RAKUTEN_OWNER_LOCAL_RESULT_V3"
    assert persisted["version"] == 3
    assert persisted["validation_stage_code"] is None
    assert persisted["validation_detail_code"] is None
    assert persisted["evidence_authority"] == RAKUTEN_OWNER_LOCAL_EVIDENCE_AUTHORITY
    assert persisted["formal_tst_016"] == "NOT_EXECUTED"
    assert persisted["staging"] == "NOT_EXECUTED"
    assert persisted["production"] == "NOT_EXECUTED"
    assert tuple(persisted) == RESULT_OBJECT_KEYS
    assert persisted["count"] == persisted["page"] == persisted["hits"] == 1
    assert persisted["first"] == persisted["last"] == 1
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
    "stage",
    tuple(RakutenOwnerLocalValidationStageCode),
)
def test_value_free_validation_stage_survives_the_single_failure_write(
    stage: RakutenOwnerLocalValidationStageCode,
) -> None:
    request = _item_request()
    failure_code = (
        RakutenOwnerLocalFailureCode.RESULT_MISMATCH
        if stage is RakutenOwnerLocalValidationStageCode.EXACT_SELECTOR
        else RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT
    )
    response_failure = RakutenOwnerLocalFailure(
        code=failure_code,
        validation_stage_code=stage,
        validation_detail_code=(
            RakutenOwnerLocalValidationDetailCode.COLLECTION_KEY_INVALID
            if stage is RakutenOwnerLocalValidationStageCode.COLLECTION_SHAPE
            else None
        ),
        credential_reflection=(
            RakutenOwnerLocalCredentialReflection(
                api=RakutenOwnerLocalApi.ITEM_SEARCH,
                credential_kind=RakutenOwnerLocalCredentialKind.APPLICATION_ID,
                field_name=RakutenOwnerLocalCredentialField.ITEM_NAME,
                field_category=RakutenOwnerLocalCredentialFieldCategory.TEXT,
            )
            if stage is RakutenOwnerLocalValidationStageCode.CREDENTIAL_REFLECTION
            else None
        ),
        disposition=RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED,
        http_status=200,
        body_byte_count=5353,
        response_sha256="d" * 64,
    )
    writer = _Writer()
    transport = _Transport(response_failure)

    envelope = RakutenOwnerLocalService(
        credential_reader=_Reader(),
        transport=transport,
        result_writer=writer,
        clock=_clock(),  # type: ignore[arg-type]
    ).run(RakutenOwnerLocalApi.ITEM_SEARCH, request, run_id=RUN_ID)

    persisted = envelope.as_result_object()
    assert writer.writes == [envelope]
    assert transport.calls == 1
    assert envelope.request_count == 1
    assert persisted["diagnostic_code"] == failure_code.value
    assert persisted["validation_stage_code"] == stage.value
    assert persisted["validation_detail_code"] == (
        RakutenOwnerLocalValidationDetailCode.COLLECTION_KEY_INVALID.value
        if stage is RakutenOwnerLocalValidationStageCode.COLLECTION_SHAPE
        else None
    )
    assert persisted["http_status"] == 200
    assert persisted["body_byte_count"] == 5353
    assert persisted["response_sha256"] == "d" * 64
    assert persisted["items"] is None
    assert persisted["products"] is None
    assert all(
        persisted[name] is None
        for name in ("count", "page", "first", "last", "hits", "pageCount")
    )
    serialized = json.dumps(persisted, sort_keys=True)
    for forbidden in (
        "itemUrl",
        "itemName",
        "untrusted-provider-value",
        "synthetic-application",
        "synthetic-access",
        "synthetic-affiliate",
    ):
        assert forbidden not in serialized
        assert forbidden not in str(envelope.failure)
        assert forbidden not in repr(envelope.failure)


def test_validation_stage_is_closed_and_bound_to_response_validation_codes() -> None:
    with pytest.raises(TypeError, match="invalid Rakuten owner-local validation stage"):
        RakutenOwnerLocalFailure(
            code=RakutenOwnerLocalFailureCode.HTTP_503,
            validation_stage_code=RakutenOwnerLocalValidationStageCode.SUMMARY_SHAPE,
        )

    with pytest.raises(TypeError, match="invalid Rakuten owner-local failure"):
        RakutenOwnerLocalFailure(  # type: ignore[arg-type]
            code=RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
            validation_stage_code="SUMMARY_SHAPE",
        )

    with pytest.raises(
        TypeError, match="invalid Rakuten owner-local validation detail"
    ):
        RakutenOwnerLocalFailure(
            code=RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
            validation_stage_code=RakutenOwnerLocalValidationStageCode.COLLECTION_SHAPE,
        )

    with pytest.raises(
        TypeError, match="invalid Rakuten owner-local validation detail"
    ):
        RakutenOwnerLocalFailure(
            code=RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
            validation_stage_code=RakutenOwnerLocalValidationStageCode.SUMMARY_SHAPE,
            validation_detail_code=(
                RakutenOwnerLocalValidationDetailCode.ROOT_NOT_OBJECT
            ),
        )

    with pytest.raises(TypeError, match="invalid Rakuten owner-local failure"):
        RakutenOwnerLocalFailure(  # type: ignore[arg-type]
            code=RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
            validation_stage_code=RakutenOwnerLocalValidationStageCode.COLLECTION_SHAPE,
            validation_detail_code="ROOT_NOT_OBJECT",
        )


def test_service_clamps_backward_wall_clock_and_writes_success_once() -> None:
    request = _item_request()
    result = _item_result(request)
    transport = _Transport(result)
    writer = _Writer()

    envelope = RakutenOwnerLocalService(
        credential_reader=_Reader(),
        transport=transport,
        result_writer=writer,
        clock=_backward_clock(),  # type: ignore[arg-type]
    ).run(RakutenOwnerLocalApi.ITEM_SEARCH, request, run_id=RUN_ID)

    assert envelope.started_at == envelope.finished_at == STARTED
    assert envelope.outcome is RakutenOwnerLocalOutcome.SUCCESS
    assert envelope.provider_result is result
    assert envelope.request_count == 1
    assert transport.calls == 1
    assert writer.writes == [envelope]
    assert "synthetic-access" not in json.dumps(
        envelope.as_result_object(), sort_keys=True
    )


def test_service_clamps_backward_wall_clock_and_preserves_provider_failure() -> None:
    request = _item_request()
    failure = RakutenOwnerLocalFailure(
        code=RakutenOwnerLocalFailureCode.HTTP_503,
        disposition=RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED,
        http_status=503,
        body_byte_count=31,
        response_sha256="d" * 64,
    )
    transport = _Transport(failure)
    writer = _Writer()

    envelope = RakutenOwnerLocalService(
        credential_reader=_Reader(),
        transport=transport,
        result_writer=writer,
        clock=_backward_clock(),  # type: ignore[arg-type]
    ).run(RakutenOwnerLocalApi.ITEM_SEARCH, request, run_id=RUN_ID)

    assert envelope.started_at == envelope.finished_at == STARTED
    assert envelope.outcome is RakutenOwnerLocalOutcome.FAILURE
    assert envelope.provider_result is None
    assert envelope.failure is not None
    assert envelope.failure.code is RakutenOwnerLocalFailureCode.HTTP_503
    assert (
        envelope.failure.disposition
        is RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED
    )
    assert envelope.failure.http_status == 503
    assert envelope.failure.body_byte_count == 31
    assert envelope.failure.response_sha256 == "d" * 64
    assert envelope.request_count == 1
    assert transport.calls == 1
    assert writer.writes == [envelope]
    persisted_object = envelope.as_result_object()
    assert persisted_object["validation_stage_code"] is None
    assert all(
        persisted_object[field] is None
        for field in ("count", "page", "first", "last", "hits", "pageCount")
    )
    assert persisted_object["items"] is None
    assert persisted_object["products"] is None
    assert "synthetic-access" not in json.dumps(persisted_object, sort_keys=True)


def test_service_invalid_finished_clock_uses_fixed_failure_and_does_not_write() -> None:
    request = _item_request()
    transport = _Transport(_item_result(request))
    writer = _Writer()
    service = RakutenOwnerLocalService(
        credential_reader=_Reader(),
        transport=transport,
        result_writer=writer,
        clock=_invalid_finished_clock(),  # type: ignore[arg-type]
    )

    with pytest.raises(RakutenOwnerLocalFailure) as captured:
        service.run(RakutenOwnerLocalApi.ITEM_SEARCH, request, run_id=RUN_ID)

    assert captured.value.code is RakutenOwnerLocalFailureCode.INVALID_ARGUMENT
    assert transport.calls == 1
    assert writer.preflights == 1
    assert writer.writes == []


def test_service_terminal_clock_exception_preserves_success_and_writes_once() -> None:
    request = _item_request()
    result = _item_result(request)
    reader = _Reader()
    transport = _Transport(result)
    writer = _Writer()

    envelope = RakutenOwnerLocalService(
        credential_reader=reader,
        transport=transport,
        result_writer=writer,
        clock=_raising_finished_clock(),  # type: ignore[arg-type]
    ).run(RakutenOwnerLocalApi.ITEM_SEARCH, request, run_id=RUN_ID)

    assert envelope.started_at == envelope.finished_at == STARTED
    assert envelope.outcome is RakutenOwnerLocalOutcome.SUCCESS
    assert envelope.provider_result is result
    assert envelope.disposition is RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED
    assert envelope.request_count == 1
    assert reader.calls == transport.calls == writer.preflights == 1
    assert writer.writes == [envelope]
    persisted = envelope.as_result_object()
    assert persisted["http_status"] == result.http_status
    assert persisted["body_byte_count"] == result.body_byte_count
    assert persisted["response_sha256"] == result.response_sha256
    serialized = json.dumps(persisted, sort_keys=True)
    for credential_value in (
        "synthetic-application",
        "synthetic-access",
        "synthetic-affiliate",
    ):
        assert credential_value not in serialized


def test_service_terminal_clock_exception_preserves_received_failure() -> None:
    request = _item_request()
    failure = RakutenOwnerLocalFailure(
        code=RakutenOwnerLocalFailureCode.HTTP_503,
        disposition=RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED,
        http_status=503,
        body_byte_count=31,
        response_sha256="d" * 64,
    )
    reader = _Reader()
    transport = _Transport(failure)
    writer = _Writer()

    envelope = RakutenOwnerLocalService(
        credential_reader=reader,
        transport=transport,
        result_writer=writer,
        clock=_raising_finished_clock(),  # type: ignore[arg-type]
    ).run(RakutenOwnerLocalApi.ITEM_SEARCH, request, run_id=RUN_ID)

    assert envelope.started_at == envelope.finished_at == STARTED
    assert envelope.outcome is RakutenOwnerLocalOutcome.FAILURE
    assert envelope.provider_result is None
    assert envelope.failure is not None
    assert envelope.failure.code is RakutenOwnerLocalFailureCode.HTTP_503
    assert envelope.disposition is RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED
    assert envelope.request_count == 1
    assert envelope.failure.http_status == 503
    assert envelope.failure.body_byte_count == 31
    assert envelope.failure.response_sha256 == "d" * 64
    assert reader.calls == transport.calls == writer.preflights == 1
    assert writer.writes == [envelope]
    persisted = envelope.as_result_object()
    assert all(
        persisted[field] is None
        for field in ("count", "page", "first", "last", "hits", "pageCount")
    )
    assert persisted["items"] is None
    assert persisted["products"] is None
    serialized = json.dumps(persisted, sort_keys=True)
    for credential_value in (
        "synthetic-application",
        "synthetic-access",
        "synthetic-affiliate",
    ):
        assert credential_value not in serialized


def test_service_terminal_clock_exception_preserves_ambiguous_failure() -> None:
    request = _item_request()
    failure = RakutenOwnerLocalFailure(
        code=RakutenOwnerLocalFailureCode.TIMEOUT,
        disposition=RakutenOwnerLocalRequestDisposition.OUTCOME_AMBIGUOUS,
    )
    reader = _Reader()
    transport = _Transport(failure)
    writer = _Writer()

    envelope = RakutenOwnerLocalService(
        credential_reader=reader,
        transport=transport,
        result_writer=writer,
        clock=_raising_finished_clock(),  # type: ignore[arg-type]
    ).run(RakutenOwnerLocalApi.ITEM_SEARCH, request, run_id=RUN_ID)

    assert envelope.started_at == envelope.finished_at == STARTED
    assert envelope.outcome is RakutenOwnerLocalOutcome.FAILURE
    assert envelope.provider_result is None
    assert envelope.failure is not None
    assert envelope.failure.code is RakutenOwnerLocalFailureCode.TIMEOUT
    assert envelope.disposition is RakutenOwnerLocalRequestDisposition.OUTCOME_AMBIGUOUS
    assert envelope.request_count == 1
    assert envelope.failure.http_status is None
    assert envelope.failure.body_byte_count is None
    assert envelope.failure.response_sha256 is None
    assert reader.calls == transport.calls == writer.preflights == 1
    assert writer.writes == [envelope]
    persisted = envelope.as_result_object()
    assert all(
        persisted[field] is None
        for field in ("count", "page", "first", "last", "hits", "pageCount")
    )
    assert persisted["items"] is None
    assert persisted["products"] is None
    serialized = json.dumps(persisted, sort_keys=True)
    for credential_value in (
        "synthetic-application",
        "synthetic-access",
        "synthetic-affiliate",
    ):
        assert credential_value not in serialized


@pytest.mark.parametrize(
    "api",
    (RakutenOwnerLocalApi.ITEM_SEARCH, RakutenOwnerLocalApi.PRODUCT_SEARCH),
)
def test_success_and_empty_results_serialize_all_six_summary_scalars(
    api: RakutenOwnerLocalApi,
) -> None:
    request = fixed_owner_local_smoke_request(api)
    if type(request) is RakutenOwnerLocalItemSearchRequest:
        nonempty = _item_result(request)
    else:
        assert type(request) is RakutenOwnerLocalProductSearchRequest
        nonempty = _product_result(request)

    for result, expected in (
        (nonempty, (1, 1, 1, 1, 1, 1)),
        (
            replace(
                nonempty,
                count=0,
                first=0,
                last=0,
                page_count=0,
                records=(),
            ),
            (0, 1, 0, 0, 1, 0),
        ),
    ):
        writer = _Writer()
        envelope = RakutenOwnerLocalService(
            credential_reader=_Reader(),
            transport=_Transport(result),
            result_writer=writer,
            clock=_clock(),  # type: ignore[arg-type]
        ).run(api, request, run_id=RUN_ID)

        persisted = envelope.as_result_object()
        assert tuple(persisted) == RESULT_OBJECT_KEYS
        assert (
            tuple(
                persisted[field]
                for field in ("count", "page", "first", "last", "hits", "pageCount")
            )
            == expected
        )
        collection = "items" if api is RakutenOwnerLocalApi.ITEM_SEARCH else "products"
        assert persisted[collection] == (
            [result.records[0].as_object()] if result.records else []
        )
        assert writer.writes == [envelope]


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
        credential_reader=_Reader(),
        transport=_Transport(result),
        result_writer=writer,
        clock=_clock(),  # type: ignore[arg-type]
    ).run(RakutenOwnerLocalApi.ITEM_SEARCH, request, run_id=RUN_ID)

    assert envelope.outcome is RakutenOwnerLocalOutcome.FAILURE
    assert envelope.provider_result is None
    assert envelope.failure is not None
    assert envelope.failure.code is RakutenOwnerLocalFailureCode.RESULT_MISMATCH
    assert (
        envelope.failure.validation_stage_code
        is RakutenOwnerLocalValidationStageCode.EXACT_SELECTOR
    )
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
        credential_reader=_Reader(),
        transport=_Transport(result),
        result_writer=writer,
        clock=_clock(),  # type: ignore[arg-type]
    ).run(RakutenOwnerLocalApi.PRODUCT_SEARCH, request, run_id=RUN_ID)

    assert envelope.outcome is RakutenOwnerLocalOutcome.FAILURE
    assert envelope.provider_result is None
    assert envelope.failure is not None
    assert envelope.failure.code is RakutenOwnerLocalFailureCode.RESULT_MISMATCH
    assert (
        envelope.failure.validation_stage_code
        is RakutenOwnerLocalValidationStageCode.EXACT_SELECTOR
    )
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
    ("synthetic-application", "synthetic-access"),
)
@pytest.mark.parametrize(
    "position",
    ("url", "mandatory-url", "ordinary-text", "nested-url-list"),
)
def test_service_rejects_each_security_credential_before_persistence(
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
        envelope.failure.validation_stage_code
        is RakutenOwnerLocalValidationStageCode.CREDENTIAL_REFLECTION
    )
    assert (
        envelope.failure.disposition
        is RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED
    )
    assert envelope.failure.http_status == reflected_result.http_status
    assert envelope.failure.body_byte_count == reflected_result.body_byte_count
    assert envelope.failure.response_sha256 == reflected_result.response_sha256
    assert envelope.request_count == 1
    assert writer.writes == [envelope]
    assert (
        envelope.as_result_object()["validation_stage_code"] == "CREDENTIAL_REFLECTION"
    )
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


@pytest.mark.parametrize(
    ("api", "field", "shape"),
    (
        (RakutenOwnerLocalApi.ITEM_SEARCH, "affiliateUrl", "url"),
        (RakutenOwnerLocalApi.ITEM_SEARCH, "itemCode", "text"),
        (RakutenOwnerLocalApi.ITEM_SEARCH, "itemName", "text"),
        (RakutenOwnerLocalApi.ITEM_SEARCH, "itemUrl", "url"),
        (RakutenOwnerLocalApi.ITEM_SEARCH, "mediumImageUrls", "url-list"),
        (RakutenOwnerLocalApi.ITEM_SEARCH, "shopCode", "text"),
        (RakutenOwnerLocalApi.ITEM_SEARCH, "shopName", "text"),
        (RakutenOwnerLocalApi.ITEM_SEARCH, "smallImageUrls", "url-list"),
        (RakutenOwnerLocalApi.PRODUCT_SEARCH, "affiliateUrl", "url"),
        (RakutenOwnerLocalApi.PRODUCT_SEARCH, "brandName", "text"),
        (RakutenOwnerLocalApi.PRODUCT_SEARCH, "genreName", "text"),
        (RakutenOwnerLocalApi.PRODUCT_SEARCH, "mediumImageUrl", "url"),
        (RakutenOwnerLocalApi.PRODUCT_SEARCH, "productCode", "text"),
        (RakutenOwnerLocalApi.PRODUCT_SEARCH, "productId", "text"),
        (RakutenOwnerLocalApi.PRODUCT_SEARCH, "productName", "text"),
        (RakutenOwnerLocalApi.PRODUCT_SEARCH, "productNo", "text"),
        (RakutenOwnerLocalApi.PRODUCT_SEARCH, "productUrlPC", "url"),
        (RakutenOwnerLocalApi.PRODUCT_SEARCH, "smallImageUrl", "url"),
    ),
)
@pytest.mark.parametrize(
    "credential_name",
    ("application_id", "access_key", "affiliate_id"),
)
def test_field_aware_credential_reflection_covers_every_persisted_text_leaf(
    api: RakutenOwnerLocalApi,
    field: str,
    shape: str,
    credential_name: str,
) -> None:
    request = fixed_owner_local_smoke_request(api)
    if type(request) is RakutenOwnerLocalItemSearchRequest:
        source = _item_result(request)
    else:
        assert type(request) is RakutenOwnerLocalProductSearchRequest
        source = _product_result(request)
    fields = source.records[0].as_object()
    credential_value = "reflection-token"
    if shape == "url":
        fields[field] = f"https://example.rakuten.co.jp/{credential_value}/{field}"
    elif shape == "url-list":
        fields[field] = [f"https://example.rakuten.co.jp/{credential_value}/{field}"]
    else:
        assert shape == "text"
        fields[field] = f"untrusted-{credential_value}-{field}"
    reflected = replace(
        source,
        records=(normalized_record(api, fields),),
    )
    writer = _Writer()

    envelope = RakutenOwnerLocalService(
        credential_reader=_Reader(
            _credentials_with_summary_value(credential_name, credential_value)
        ),
        transport=_Transport(reflected),
        result_writer=writer,
        clock=_clock(),  # type: ignore[arg-type]
    ).run(api, request, run_id=RUN_ID)

    affiliate_link_fields = {
        RakutenOwnerLocalApi.ITEM_SEARCH: frozenset({"affiliateUrl", "itemUrl"}),
        RakutenOwnerLocalApi.PRODUCT_SEARCH: frozenset({"affiliateUrl"}),
    }
    affiliate_link_exempt = (
        credential_name == "affiliate_id" and field in affiliate_link_fields[api]
    )
    persisted = json.dumps(envelope.as_result_object(), sort_keys=True)
    if affiliate_link_exempt:
        assert envelope.outcome is RakutenOwnerLocalOutcome.SUCCESS
        assert envelope.provider_result is reflected
        assert envelope.failure is None
        assert credential_value in persisted
    else:
        assert envelope.outcome is RakutenOwnerLocalOutcome.FAILURE
        assert envelope.provider_result is None
        assert envelope.failure is not None
        assert (
            envelope.failure.code is RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT
        )
        assert envelope.failure.request_count == 1
        assert envelope.failure.http_status == reflected.http_status
        assert envelope.failure.body_byte_count == reflected.body_byte_count
        assert envelope.failure.response_sha256 == reflected.response_sha256
        reflection = envelope.failure.credential_reflection
        assert reflection is not None
        assert reflection.api is api
        assert reflection.credential_kind is RakutenOwnerLocalCredentialKind(
            credential_name.upper()
        )
        assert reflection.field_name is RakutenOwnerLocalCredentialField(field)
        assert reflection.field_category is RakutenOwnerLocalCredentialFieldCategory(
            "URL_LIST_MEMBER" if shape == "url-list" else shape.upper()
        )
        assert "reflection_credential_kind" not in envelope.as_result_object()
        diagnostic = envelope.as_reflection_diagnostic_object()
        assert tuple(diagnostic) == REFLECTION_DIAGNOSTIC_OBJECT_KEYS
        assert diagnostic["diagnostic_outcome"] == "REFLECTION_DETECTED"
        assert diagnostic["reflection_credential_kind"] == credential_name.upper()
        assert diagnostic["reflection_field_name"] == field
        assert diagnostic["reflection_field_category"] == (
            "URL_LIST_MEMBER" if shape == "url-list" else shape.upper()
        )
        assert diagnostic["provider_data_persisted"] is False
        diagnostic_text = json.dumps(diagnostic, sort_keys=True)
        assert credential_value not in diagnostic_text
        assert credential_value not in persisted
        assert credential_value not in str(envelope.failure)
        assert credential_value not in repr(envelope.failure)
    assert writer.writes == [envelope]


@pytest.mark.parametrize(
    ("api", "fields"),
    (
        (
            RakutenOwnerLocalApi.ITEM_SEARCH,
            ("affiliateUrl", "itemUrl"),
        ),
        (RakutenOwnerLocalApi.PRODUCT_SEARCH, ("affiliateUrl",)),
    ),
)
@pytest.mark.parametrize("percent_encoded", (False, True))
def test_affiliate_id_is_accepted_only_in_exact_affiliate_link_url_fields(
    api: RakutenOwnerLocalApi,
    fields: tuple[str, ...],
    percent_encoded: bool,
) -> None:
    request = fixed_owner_local_smoke_request(api)
    if type(request) is RakutenOwnerLocalItemSearchRequest:
        source = _item_result(request)
    else:
        assert type(request) is RakutenOwnerLocalProductSearchRequest
        source = _product_result(request)
    values = source.records[0].as_object()
    rendered = "affiliate%2Flink-token" if percent_encoded else "affiliate/link-token"
    for field in fields:
        values[field] = f"https://example.rakuten.co.jp/{rendered}/{field}"
    result = replace(source, records=(normalized_record(api, values),))
    writer = _Writer()

    envelope = RakutenOwnerLocalService(
        credential_reader=_Reader(
            _credentials_with_summary_value("affiliate_id", "affiliate/link-token")
        ),
        transport=_Transport(result),
        result_writer=writer,
        clock=_clock(),  # type: ignore[arg-type]
    ).run(api, request, run_id=RUN_ID)

    assert envelope.outcome is RakutenOwnerLocalOutcome.SUCCESS
    assert envelope.failure is None
    assert envelope.provider_result is result
    assert envelope.request_count == 1
    assert writer.writes == [envelope]
    result_object = envelope.as_result_object()
    assert tuple(result_object) == RESULT_OBJECT_KEYS
    assert result_object["schema"] == "RAOS_ST0505_RAKUTEN_OWNER_LOCAL_RESULT_V3"
    persisted = json.dumps(result_object, sort_keys=True)
    assert rendered in persisted


@pytest.mark.parametrize(
    ("api", "field"),
    (
        (RakutenOwnerLocalApi.ITEM_SEARCH, "affiliateUrl"),
        (RakutenOwnerLocalApi.ITEM_SEARCH, "itemUrl"),
        (RakutenOwnerLocalApi.PRODUCT_SEARCH, "affiliateUrl"),
    ),
)
@pytest.mark.parametrize("credential_name", ("application_id", "access_key"))
@pytest.mark.parametrize("percent_encoded", (False, True))
def test_security_credentials_remain_rejected_in_affiliate_link_url_fields(
    api: RakutenOwnerLocalApi,
    field: str,
    credential_name: str,
    percent_encoded: bool,
) -> None:
    request = fixed_owner_local_smoke_request(api)
    if type(request) is RakutenOwnerLocalItemSearchRequest:
        source = _item_result(request)
    else:
        assert type(request) is RakutenOwnerLocalProductSearchRequest
        source = _product_result(request)
    values = source.records[0].as_object()
    rendered = "security%2Ftoken" if percent_encoded else "security/token"
    values[field] = f"https://example.rakuten.co.jp/{rendered}/{field}"
    result = replace(source, records=(normalized_record(api, values),))
    writer = _Writer()

    envelope = RakutenOwnerLocalService(
        credential_reader=_Reader(
            _credentials_with_summary_value(credential_name, "security/token")
        ),
        transport=_Transport(result),
        result_writer=writer,
        clock=_clock(),  # type: ignore[arg-type]
    ).run(api, request, run_id=RUN_ID)

    assert envelope.outcome is RakutenOwnerLocalOutcome.FAILURE
    assert envelope.provider_result is None
    assert envelope.failure is not None
    assert envelope.failure.code is RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT
    assert (
        envelope.failure.validation_stage_code
        is RakutenOwnerLocalValidationStageCode.CREDENTIAL_REFLECTION
    )
    assert envelope.failure.request_count == 1
    assert envelope.failure.http_status == result.http_status
    assert envelope.failure.body_byte_count == result.body_byte_count
    assert envelope.failure.response_sha256 == result.response_sha256
    assert writer.writes == [envelope]
    persisted = json.dumps(envelope.as_result_object(), sort_keys=True)
    assert "security/token" not in persisted
    assert "security%2Ftoken" not in persisted
    assert "security/token" not in str(envelope.failure)
    assert "security/token" not in repr(envelope.failure)


@pytest.mark.parametrize(
    ("api", "field", "shape"),
    (
        (RakutenOwnerLocalApi.ITEM_SEARCH, "itemName", "text"),
        (RakutenOwnerLocalApi.ITEM_SEARCH, "smallImageUrls", "url-list"),
        (RakutenOwnerLocalApi.PRODUCT_SEARCH, "productName", "text"),
        (RakutenOwnerLocalApi.PRODUCT_SEARCH, "productUrlPC", "url"),
        (RakutenOwnerLocalApi.PRODUCT_SEARCH, "smallImageUrl", "url"),
    ),
)
def test_percent_encoded_affiliate_id_remains_rejected_outside_link_fields(
    api: RakutenOwnerLocalApi,
    field: str,
    shape: str,
) -> None:
    request = fixed_owner_local_smoke_request(api)
    if type(request) is RakutenOwnerLocalItemSearchRequest:
        source = _item_result(request)
    else:
        assert type(request) is RakutenOwnerLocalProductSearchRequest
        source = _product_result(request)
    values = source.records[0].as_object()
    rendered = "affiliate%2Ftoken"
    if shape == "text":
        values[field] = f"untrusted-{rendered}-{field}"
    elif shape == "url-list":
        values[field] = [f"https://example.rakuten.co.jp/{rendered}/{field}"]
    else:
        assert shape == "url"
        values[field] = f"https://example.rakuten.co.jp/{rendered}/{field}"
    result = replace(source, records=(normalized_record(api, values),))

    envelope = RakutenOwnerLocalService(
        credential_reader=_Reader(
            _credentials_with_summary_value("affiliate_id", "affiliate/token")
        ),
        transport=_Transport(result),
        result_writer=_Writer(),
        clock=_clock(),  # type: ignore[arg-type]
    ).run(api, request, run_id=RUN_ID)

    assert envelope.outcome is RakutenOwnerLocalOutcome.FAILURE
    assert envelope.provider_result is None
    assert envelope.failure is not None
    assert envelope.failure.code is RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT
    assert (
        envelope.failure.validation_stage_code
        is RakutenOwnerLocalValidationStageCode.CREDENTIAL_REFLECTION
    )
    assert envelope.failure.request_count == 1
    persisted = json.dumps(envelope.as_result_object(), sort_keys=True)
    assert "affiliate/token" not in persisted
    assert rendered not in persisted


@pytest.mark.parametrize(
    ("api", "field"),
    (
        (RakutenOwnerLocalApi.ITEM_SEARCH, "affiliateUrl"),
        (RakutenOwnerLocalApi.ITEM_SEARCH, "itemUrl"),
        (RakutenOwnerLocalApi.PRODUCT_SEARCH, "affiliateUrl"),
    ),
)
def test_affiliate_link_exemption_cannot_precede_url_validation(
    api: RakutenOwnerLocalApi,
    field: str,
) -> None:
    request = fixed_owner_local_smoke_request(api)
    if type(request) is RakutenOwnerLocalItemSearchRequest:
        source = _item_result(request)
    else:
        assert type(request) is RakutenOwnerLocalProductSearchRequest
        source = _product_result(request)
    values = source.records[0].as_object()
    values[field] = "http://example.rakuten.co.jp/synthetic-affiliate"

    with pytest.raises(RakutenOwnerLocalFailure) as captured:
        normalized_record(api, values)

    assert captured.value.code is RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT
    assert (
        captured.value.validation_stage_code is RakutenOwnerLocalValidationStageCode.URL
    )


@pytest.mark.parametrize(
    ("api", "near_field"),
    (
        (RakutenOwnerLocalApi.ITEM_SEARCH, "affiliateURL"),
        (RakutenOwnerLocalApi.ITEM_SEARCH, "ItemUrl"),
        (RakutenOwnerLocalApi.PRODUCT_SEARCH, "AffiliateUrl"),
    ),
)
def test_near_affiliate_link_field_names_remain_record_shape_errors(
    api: RakutenOwnerLocalApi,
    near_field: str,
) -> None:
    request = fixed_owner_local_smoke_request(api)
    if type(request) is RakutenOwnerLocalItemSearchRequest:
        source = _item_result(request)
    else:
        assert type(request) is RakutenOwnerLocalProductSearchRequest
        source = _product_result(request)
    values = source.records[0].as_object()
    values[near_field] = "https://example.rakuten.co.jp/synthetic-affiliate"

    with pytest.raises(RakutenOwnerLocalFailure) as captured:
        normalized_record(api, values)

    assert captured.value.code is RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT
    assert (
        captured.value.validation_stage_code
        is RakutenOwnerLocalValidationStageCode.RECORD_SHAPE
    )


@pytest.mark.parametrize(
    ("api", "field", "value"),
    (
        (RakutenOwnerLocalApi.ITEM_SEARCH, "itemName", "untrusted-1-item"),
        (
            RakutenOwnerLocalApi.ITEM_SEARCH,
            "itemUrl",
            "https://example.rakuten.co.jp/item/1",
        ),
        (
            RakutenOwnerLocalApi.ITEM_SEARCH,
            "smallImageUrls",
            ["https://example.rakuten.co.jp/image/%31"],
        ),
        (RakutenOwnerLocalApi.PRODUCT_SEARCH, "productName", "untrusted-1-product"),
        (
            RakutenOwnerLocalApi.PRODUCT_SEARCH,
            "productUrlPC",
            "https://example.rakuten.co.jp/product/1",
        ),
    ),
)
@pytest.mark.parametrize(
    "credential_name",
    ("application_id", "access_key", "affiliate_id"),
)
def test_short_credential_reflected_in_provider_text_still_fails_closed(
    api: RakutenOwnerLocalApi,
    field: str,
    value: object,
    credential_name: str,
) -> None:
    request = fixed_owner_local_smoke_request(api)
    if type(request) is RakutenOwnerLocalItemSearchRequest:
        source = _item_result(request)
    else:
        assert type(request) is RakutenOwnerLocalProductSearchRequest
        source = _product_result(request)
    fields = source.records[0].as_object()
    fields[field] = value
    reflected = replace(
        source,
        records=(normalized_record(api, fields),),
    )

    envelope = RakutenOwnerLocalService(
        credential_reader=_Reader(
            _credentials_with_summary_value(credential_name, "1")
        ),
        transport=_Transport(reflected),
        result_writer=_Writer(),
        clock=_clock(),  # type: ignore[arg-type]
    ).run(api, request, run_id=RUN_ID)

    affiliate_link_exempt = (
        credential_name == "affiliate_id"
        and api is RakutenOwnerLocalApi.ITEM_SEARCH
        and field == "itemUrl"
    )
    persisted = envelope.as_result_object()
    if affiliate_link_exempt:
        assert envelope.outcome is RakutenOwnerLocalOutcome.SUCCESS
        assert envelope.provider_result is reflected
        assert envelope.failure is None
        assert persisted["items"] is not None
    else:
        assert envelope.outcome is RakutenOwnerLocalOutcome.FAILURE
        assert envelope.provider_result is None
        assert envelope.failure is not None
        assert (
            envelope.failure.code is RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT
        )
        assert envelope.failure.request_count == 1
        assert persisted["items"] is None
        assert persisted["products"] is None


@pytest.mark.parametrize(
    "api",
    (RakutenOwnerLocalApi.ITEM_SEARCH, RakutenOwnerLocalApi.PRODUCT_SEARCH),
)
@pytest.mark.parametrize(
    "credential_name",
    ("application_id", "access_key", "affiliate_id"),
)
def test_short_numeric_credential_does_not_collide_with_structural_numbers(
    api: RakutenOwnerLocalApi,
    credential_name: str,
) -> None:
    request = fixed_owner_local_smoke_request(api)
    if type(request) is RakutenOwnerLocalItemSearchRequest:
        source_result = _item_result(request, itemPrice=1)
    else:
        assert type(request) is RakutenOwnerLocalProductSearchRequest
        source = _product_result(request)
        fields = source.records[0].as_object()
        fields.update(
            {
                "averagePrice": 1,
                "genreId": 1,
                "itemCount": 1,
                "maxPrice": 1,
                "minPrice": 1,
                "salesItemCount": 1,
                "salesMaxPrice": 1,
                "salesMinPrice": 1,
            }
        )
        source_result = replace(
            source,
            records=(normalized_record(api, fields),),
        )
    writer = _Writer()
    envelope = RakutenOwnerLocalService(
        credential_reader=_Reader(
            _credentials_with_summary_value(credential_name, "1")
        ),
        transport=_Transport(source_result),
        result_writer=writer,
        clock=_clock(),  # type: ignore[arg-type]
    ).run(api, request, run_id=RUN_ID)

    assert envelope.outcome is RakutenOwnerLocalOutcome.SUCCESS
    assert envelope.failure is None
    assert envelope.provider_result is source_result
    assert envelope.request_count == 1
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
def test_short_credential_does_not_collide_with_validated_summary_scalar(
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
        **{
            summary_field: summary_value,
            **(
                {"page_count": 7}
                if summary_field == "count"
                else {"page_count": 1}
                if summary_field == "hits"
                else {"count": 7}
                if summary_field == "page_count"
                else {}
            ),
        },
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

    assert envelope.outcome is RakutenOwnerLocalOutcome.SUCCESS
    assert envelope.provider_result is result
    assert envelope.failure is None
    assert envelope.request_count == 1
    persisted = envelope.as_result_object()
    persisted_name = "pageCount" if summary_field == "page_count" else summary_field
    assert persisted[persisted_name] == summary_value
    assert persisted["provider_data_classification"] == "UNTRUSTED_PROVIDER_DATA"
    assert tuple(persisted) == RESULT_OBJECT_KEYS
    assert writer.writes == [envelope]


@pytest.mark.parametrize(
    "api",
    (RakutenOwnerLocalApi.ITEM_SEARCH, RakutenOwnerLocalApi.PRODUCT_SEARCH),
)
@pytest.mark.parametrize(
    "credential_name",
    ("application_id", "access_key", "affiliate_id"),
)
@pytest.mark.parametrize("credential_value", ("0", "1"))
def test_short_credential_does_not_collide_with_empty_result_summaries(
    api: RakutenOwnerLocalApi,
    credential_name: str,
    credential_value: str,
) -> None:
    request = fixed_owner_local_smoke_request(api)
    result = replace(
        _minimal_provider_result(api, request),
        count=0,
        first=0,
        last=0,
        page_count=0,
        records=(),
    )
    writer = _Writer()

    envelope = RakutenOwnerLocalService(
        credential_reader=_Reader(
            _credentials_with_summary_value(credential_name, credential_value)
        ),
        transport=_Transport(result),
        result_writer=writer,
        clock=_clock(),  # type: ignore[arg-type]
    ).run(api, request, run_id=RUN_ID)

    assert envelope.outcome is RakutenOwnerLocalOutcome.SUCCESS
    assert envelope.provider_result is result
    assert envelope.failure is None
    assert envelope.request_count == 1
    persisted = envelope.as_result_object()
    assert tuple(
        persisted[field]
        for field in ("count", "page", "first", "last", "hits", "pageCount")
    ) == (0, 1, 0, 0, 1, 0)
    collection = "items" if api is RakutenOwnerLocalApi.ITEM_SEARCH else "products"
    assert persisted[collection] == []
    assert writer.writes == [envelope]


@pytest.mark.parametrize("binding", ("api", "fingerprint", "hits"))
def test_result_binding_mismatch_precedes_short_summary_credential_coincidence(
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
            result = replace(result, hits=2, page_count=1)
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


def test_cli_accepts_short_credential_matching_validated_summary() -> None:
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

    assert code == 0
    assert message == owner_local_cli.OWNER_LOCAL_OK
    assert len(writer.writes) == 1
    envelope = writer.writes[0]
    assert envelope.outcome is RakutenOwnerLocalOutcome.SUCCESS
    assert envelope.provider_result is result
    assert envelope.failure is None
    persisted = envelope.as_result_object()
    assert tuple(persisted) == RESULT_OBJECT_KEYS
    assert tuple(
        persisted[field]
        for field in ("count", "page", "first", "last", "hits", "pageCount")
    ) == (2, 1, 1, 1, 1, 2)


@pytest.mark.parametrize(
    "api",
    (RakutenOwnerLocalApi.ITEM_SEARCH, RakutenOwnerLocalApi.PRODUCT_SEARCH),
)
def test_cli_success_writes_complete_summary_envelope(
    api: RakutenOwnerLocalApi,
) -> None:
    request = fixed_owner_local_smoke_request(api)
    if type(request) is RakutenOwnerLocalItemSearchRequest:
        result = _item_result(request)
    else:
        assert type(request) is RakutenOwnerLocalProductSearchRequest
        result = _product_result(request)
    writer = _Writer()

    code, message = owner_local_cli._execute_request(  # noqa: SLF001
        api.value,
        request,
        reader=_Reader(),
        writer=writer,
        transport=_Transport(result),
    )

    assert code == 0
    assert message == owner_local_cli.OWNER_LOCAL_OK
    assert len(writer.writes) == 1
    persisted = writer.writes[0].as_result_object()
    assert tuple(persisted) == RESULT_OBJECT_KEYS
    assert tuple(
        persisted[field]
        for field in ("count", "page", "first", "last", "hits", "pageCount")
    ) == (1, 1, 1, 1, 1, 1)


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


def test_reflection_diagnostic_cli_records_one_closed_match_without_v3_drift() -> None:
    request = _item_request()
    source_result = _item_result(request)
    fields = source_result.records[0].as_object()
    fields["shopName"] = "untrusted synthetic-access reflected shop"
    result = replace(
        source_result,
        records=(normalized_record(RakutenOwnerLocalApi.ITEM_SEARCH, fields),),
    )
    reader = _Reader()
    transport = _Transport(result)
    writer = _Writer()

    code, message = owner_local_cli._execute_reflection_diagnostic(  # noqa: SLF001
        reader=reader,
        writer=writer,
        transport=transport,
    )

    assert code == 0
    assert message == owner_local_cli.REFLECTION_DIAGNOSTIC_RECORDED
    assert reader.calls == transport.calls == writer.preflights == 1
    assert len(writer.writes) == 1
    envelope = writer.writes[0]
    assert envelope.request_count == 1
    assert envelope.failure is not None
    assert (
        envelope.failure.validation_stage_code
        is RakutenOwnerLocalValidationStageCode.CREDENTIAL_REFLECTION
    )
    assert tuple(envelope.as_result_object()) == RESULT_OBJECT_KEYS
    assert "reflection_credential_kind" not in envelope.as_result_object()
    diagnostic = envelope.as_reflection_diagnostic_object()
    assert tuple(diagnostic) == REFLECTION_DIAGNOSTIC_OBJECT_KEYS
    assert diagnostic["diagnostic_outcome"] == "REFLECTION_DETECTED"
    assert diagnostic["reflection_credential_kind"] == "ACCESS_KEY"
    assert diagnostic["reflection_field_name"] == "shopName"
    assert diagnostic["reflection_field_category"] == "TEXT"
    assert diagnostic["request_disposition"] == "RESPONSE_RECEIVED"
    assert diagnostic["request_count"] == 1
    assert diagnostic["http_status"] == 200
    assert diagnostic["body_byte_count"] == 256
    assert diagnostic["response_sha256"] == "a" * 64
    assert diagnostic["provider_data_persisted"] is False
    serialized = json.dumps(diagnostic, sort_keys=True)
    for forbidden in (
        "synthetic-application",
        "synthetic-access",
        "synthetic-affiliate",
        "reflected shop",
    ):
        assert forbidden not in serialized
        assert forbidden not in message


@pytest.mark.parametrize("failure", (False, True))
def test_reflection_diagnostic_records_no_match_or_sanitized_request_failure(
    failure: bool,
) -> None:
    request = _item_request()
    transport = _Transport(
        RakutenOwnerLocalFailure(
            code=RakutenOwnerLocalFailureCode.TIMEOUT,
            disposition=RakutenOwnerLocalRequestDisposition.OUTCOME_AMBIGUOUS,
        )
        if failure
        else _item_result(request)
    )
    writer = _Writer()

    code, message = owner_local_cli._execute_reflection_diagnostic(  # noqa: SLF001
        reader=_Reader(),
        writer=writer,
        transport=transport,
    )

    assert code == 0
    assert message == owner_local_cli.REFLECTION_DIAGNOSTIC_RECORDED
    assert transport.calls == writer.preflights == len(writer.writes) == 1
    diagnostic = writer.writes[0].as_reflection_diagnostic_object()
    assert tuple(diagnostic) == REFLECTION_DIAGNOSTIC_OBJECT_KEYS
    assert diagnostic["diagnostic_outcome"] == (
        "REQUEST_FAILED" if failure else "NO_REFLECTION_DETECTED"
    )
    assert diagnostic["diagnostic_code"] == ("TIMEOUT" if failure else "PASS")
    assert diagnostic["request_disposition"] == (
        "OUTCOME_AMBIGUOUS" if failure else "RESPONSE_RECEIVED"
    )
    assert diagnostic["request_count"] == 1
    assert diagnostic["http_status"] == (None if failure else 200)
    assert diagnostic["body_byte_count"] == (None if failure else 256)
    assert diagnostic["response_sha256"] == (None if failure else "a" * 64)
    assert diagnostic["reflection_credential_kind"] is None
    assert diagnostic["reflection_field_name"] is None
    assert diagnostic["reflection_field_category"] is None
    assert diagnostic["provider_data_persisted"] is False
    serialized = json.dumps(diagnostic, sort_keys=True)
    for credential_value in (
        "synthetic-application",
        "synthetic-access",
        "synthetic-affiliate",
    ):
        assert credential_value not in serialized


def test_reflection_diagnostic_match_selection_uses_fixed_closed_precedence() -> None:
    request = _item_request()
    source = _item_result(request)
    first = source.records[0].as_object()
    first["shopName"] = "untrusted same-token"
    second = source.records[0].as_object()
    second["affiliateUrl"] = "https://example.rakuten.co.jp/same-token"
    credentials = RakutenOwnerLocalCredentials(
        profile=RAKUTEN_OWNER_LOCAL_PROFILE,
        _application_id=b"same-token",
        _access_key=b"same-token",
        _affiliate_id=b"different-affiliate",
    )

    selected: list[tuple[object, object]] = []
    for records in (
        (first, second),
        (second, first),
    ):
        reflected = replace(
            source,
            count=2,
            last=2,
            hits=2,
            records=tuple(
                normalized_record(RakutenOwnerLocalApi.ITEM_SEARCH, fields)
                for fields in records
            ),
        )
        with pytest.raises(RakutenOwnerLocalFailure) as failure:
            credentials.reject_reflected_result(reflected)
        reflection = failure.value.credential_reflection
        assert reflection is not None
        selected.append(
            (
                reflection.credential_kind.value,
                reflection.field_name.value,
            )
        )

    assert selected == [
        ("APPLICATION_ID", "affiliateUrl"),
        ("APPLICATION_ID", "affiliateUrl"),
    ]


def test_cli_keeps_collection_detail_value_free_and_non_persistent_in_output() -> None:
    request = _item_request()
    failure = RakutenOwnerLocalFailure(
        code=RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
        validation_stage_code=RakutenOwnerLocalValidationStageCode.COLLECTION_SHAPE,
        validation_detail_code=(
            RakutenOwnerLocalValidationDetailCode.ROOT_MEMBER_UNRECOGNIZED
        ),
        disposition=RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED,
        http_status=200,
        body_byte_count=5353,
        response_sha256="d" * 64,
    )

    code, message = owner_local_cli._execute_request(  # noqa: SLF001
        RakutenOwnerLocalApi.ITEM_SEARCH.value,
        request,
        reader=_Reader(),
        writer=_Writer(),
        transport=_Transport(failure),
    )

    assert code == 1
    assert message == "RAKUTEN_OWNER_LOCAL_FAIL_RESPONSE_SCHEMA_DRIFT"
    for forbidden in (
        "ROOT_MEMBER_UNRECOGNIZED",
        "validation_detail_code",
        "carrier",
        "provider-controlled-value",
        "synthetic-application",
        "synthetic-access",
        "synthetic-affiliate",
    ):
        assert forbidden not in message


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
    persisted = envelope.as_result_object()
    assert tuple(persisted) == RESULT_OBJECT_KEYS
    assert all(
        persisted[field] is None
        for field in ("count", "page", "first", "last", "hits", "pageCount")
    )


def test_service_clamps_backward_wall_clock_and_preserves_ambiguous_attempt() -> None:
    request = _item_request()
    failure = RakutenOwnerLocalFailure(
        code=RakutenOwnerLocalFailureCode.TIMEOUT,
        disposition=RakutenOwnerLocalRequestDisposition.OUTCOME_AMBIGUOUS,
    )
    transport = _Transport(failure)
    writer = _Writer()

    envelope = RakutenOwnerLocalService(
        credential_reader=_Reader(),
        transport=transport,
        result_writer=writer,
        clock=_backward_clock(),  # type: ignore[arg-type]
    ).run(RakutenOwnerLocalApi.ITEM_SEARCH, request, run_id=RUN_ID)

    assert envelope.started_at == envelope.finished_at == STARTED
    assert envelope.outcome is RakutenOwnerLocalOutcome.FAILURE
    assert envelope.provider_result is None
    assert envelope.failure is not None
    assert envelope.failure.code is RakutenOwnerLocalFailureCode.TIMEOUT
    assert envelope.disposition is RakutenOwnerLocalRequestDisposition.OUTCOME_AMBIGUOUS
    assert envelope.request_count == 1
    assert envelope.failure.http_status is None
    assert envelope.failure.body_byte_count is None
    assert envelope.failure.response_sha256 is None
    assert transport.calls == 1
    assert writer.writes == [envelope]
    persisted_object = envelope.as_result_object()
    assert all(
        persisted_object[field] is None
        for field in ("count", "page", "first", "last", "hits", "pageCount")
    )
    assert persisted_object["items"] is None
    assert persisted_object["products"] is None
    assert "synthetic-access" not in json.dumps(persisted_object, sort_keys=True)


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

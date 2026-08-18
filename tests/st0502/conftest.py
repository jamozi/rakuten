"""Synthetic exact builders for isolated ST-0502 tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sys
from uuid import UUID


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.adapters.recorded_rakuten_item_search import (  # noqa: E402
    RecordedItemSearchFixture,
    RecordedRakutenItemSearchAdapter,
)
from raos.application.catalog.rakuten_item_search import (  # noqa: E402
    RakutenItemSearchService,
)
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.catalog.rakuten_item_search import (  # noqa: E402
    CANONICAL_ITEM_SEARCH_ELEMENTS,
    CanonicalItemSearchItem,
    CanonicalItemSearchPage,
    ItemSearchPurpose,
    ItemSearchSort,
    RakutenItemSearchCommand,
    RakutenItemSearchRequest,
    RateLimitMetadata,
    RawItemSearchResponse,
    RawResponseReceipt,
    StorageExecutionStatus,
)


ENDPOINT_ID = UUID("018f3e90-7b00-7000-8000-000000000101")
ARTIFACT_ID = UUID("018f3e90-7b00-7000-8000-000000000102")
OBSERVED_AT = datetime(2026, 8, 10, 4, 0, tzinfo=timezone.utc)
RESET_AT = OBSERVED_AT + timedelta(minutes=1)
# Official Rakuten 20260701 formatVersion=2 uses a lower-case `items` array
# whose elements are the item objects directly, without the legacy `item`
# wrapper. This fixture is synthetic and contains no provider response bytes.
RAW_BODY = (
    b'{"items":[{"affiliateUrl":"https://example.invalid/affiliate",'
    b'"availability":1,"genreId":100,"itemCode":"test-shop:item-1",'
    b'"itemName":"Untrusted synthetic item","itemPrice":1234,'
    b'"itemUrl":"https://example.invalid/item-1","reviewAverage":4.5,'
    b'"reviewCount":3,"shopCode":"test-shop","shopName":"Synthetic shop"}],'
    b'"count":1,"hits":1,"page":1,"pageCount":1}'
)
RAW_SHA256 = hashlib.sha256(RAW_BODY).hexdigest()


def item_search_request() -> RakutenItemSearchRequest:
    return RakutenItemSearchRequest(
        api_version="2026-07-01",
        format_version=2,
        keyword="synthetic suitcase",
        shop_code=None,
        item_code=None,
        genre_id=None,
        hits=1,
        page=1,
        sort=ItemSearchSort.STANDARD,
        elements=CANONICAL_ITEM_SEARCH_ELEMENTS,
        min_price_jpy=None,
        max_price_jpy=None,
        or_flag=False,
        availability=True,
        postage_included_only=False,
        has_review_only=False,
        appoint_delivery_date_only=False,
        attribute_flag=False,
        genre_information_flag=False,
    )


def item_search_command() -> RakutenItemSearchCommand:
    return RakutenItemSearchCommand.from_request(
        endpoint_id=ENDPOINT_ID,
        purpose=ItemSearchPurpose.CONTRACT_TEST,
        request=item_search_request(),
    )


def rate_metadata() -> RateLimitMetadata:
    return RateLimitMetadata(limit=100, remaining=99, reset_at=RESET_AT)


def raw_response(
    *,
    body: bytes = RAW_BODY,
    body_sha256: str | None = None,
    request_fingerprint: str | None = None,
    http_status: int = 200,
    request_id: str = "TEST_ONLY:REQUEST:1",
) -> RawItemSearchResponse:
    exact_sha256 = (
        hashlib.sha256(body).hexdigest() if body_sha256 is None else body_sha256
    )
    return RawItemSearchResponse(
        provider="RAKUTEN_ICHIBA",
        api=item_search_command().operation,
        request_fingerprint=(
            item_search_request().fingerprint
            if request_fingerprint is None
            else request_fingerprint
        ),
        body=body,
        body_sha256=exact_sha256,
        received_at=OBSERVED_AT,
        http_status=http_status,
        request_id=request_id,
        rate=rate_metadata(),
    )


def receipt() -> RawResponseReceipt:
    return RawResponseReceipt(
        artifact_id=ARTIFACT_ID,
        sha256=RAW_SHA256,
        byte_size=len(RAW_BODY),
        content_type="application/json",
        uri=None,
        storage_status=StorageExecutionStatus.NOT_EXECUTED,
    )


def canonical_page() -> CanonicalItemSearchPage:
    raw_receipt = receipt()
    item = CanonicalItemSearchItem(
        provider="RAKUTEN_ICHIBA",
        api_version="2026-07-01",
        request_sha256=item_search_request().fingerprint,
        raw_sha256=RAW_SHA256,
        item_code="test-shop:item-1",
        item_name="Untrusted synthetic item",
        catchcopy=None,
        item_caption=None,
        item_price_jpy=1234,
        item_url="https://example.invalid/item-1",
        affiliate_url="https://example.invalid/affiliate",
        shop_code="test-shop",
        shop_name="Synthetic shop",
        genre_id=100,
        availability=True,
        review_count=3,
        review_average=4.5,
        affiliate_rate=1.0,
        postage_included=False,
        image_urls=(),
        provider_updated_at=None,
        observed_at=OBSERVED_AT,
    )
    return CanonicalItemSearchPage(
        provider="RAKUTEN_ICHIBA",
        api_version="2026-07-01",
        request_sha256=item_search_request().fingerprint,
        raw_artifact=raw_receipt,
        observed_at=OBSERVED_AT,
        count=1,
        page=1,
        hits=1,
        page_count=1,
        items=(item,),
        warnings=(),
        provider_rate_limit=rate_metadata(),
    )


def recorded_adapter() -> RecordedRakutenItemSearchAdapter:
    fixture = RecordedItemSearchFixture(
        command=item_search_command(),
        response=raw_response(),
        receipt=receipt(),
        page=canonical_page(),
    )
    return RecordedRakutenItemSearchAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        fixture_capacity=1,
        fixtures=(fixture,),
    )


def item_search_service() -> RakutenItemSearchService:
    adapter = recorded_adapter()
    return RakutenItemSearchService(
        environment=RuntimeEnvironment.ENV_DEV,
        provider=adapter,
        recorder=adapter,
    )

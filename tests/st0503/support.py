"""Synthetic exact builders for isolated ST-0503 tests."""

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


from raos.adapters.recorded_catalog_normalization import (  # noqa: E402
    RecordedCatalogNormalizationAdapter,
    RecordedCatalogNormalizationFixture,
)
from raos.application.catalog.catalog_normalization import (  # noqa: E402
    CatalogNormalizationService,
)
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.catalog.catalog_normalization import (  # noqa: E402
    CatalogNormalizationBatch,
    CatalogNormalizationCommand,
    lossless_batch_from_command,
)
from raos.domain.catalog.rakuten_item_search import (  # noqa: E402
    CANONICAL_ITEM_SEARCH_ELEMENTS,
    CanonicalItemSearchItem,
    CanonicalItemSearchPage,
    ItemSearchPurpose,
    ItemSearchSort,
    PersistenceExecutionStatus,
    ProviderMode,
    RakutenItemSearchCommand,
    RakutenItemSearchRequest,
    RakutenItemSearchResult,
    RateLimitMetadata,
    RawResponseReceipt,
    StorageExecutionStatus,
)


ENDPOINT_ID = UUID("018f3e90-7b00-7000-8000-000000000201")
ARTIFACT_ID = UUID("018f3e90-7b00-7000-8000-000000000202")
INGESTION_ID = UUID("018f3e90-7b00-7000-8000-000000000203")
SECOND_INGESTION_ID = UUID("018f3e90-7b00-7000-8000-000000000204")
OBSERVED_AT = datetime(2026, 8, 10, 4, 0, tzinfo=timezone.utc)
INGESTED_AT = OBSERVED_AT + timedelta(minutes=5)
RAW_BODY = b'{"recorded":"catalog-normalization-source","items":2}'
RAW_SHA256 = hashlib.sha256(RAW_BODY).hexdigest()


def item_search_request() -> RakutenItemSearchRequest:
    return RakutenItemSearchRequest(
        api_version="2026-07-01",
        format_version=2,
        keyword="synthetic normalization",
        shop_code=None,
        item_code=None,
        genre_id=None,
        hits=2,
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
    return RateLimitMetadata(
        limit=100,
        remaining=98,
        reset_at=OBSERVED_AT + timedelta(minutes=1),
    )


def raw_receipt() -> RawResponseReceipt:
    return RawResponseReceipt(
        artifact_id=ARTIFACT_ID,
        sha256=RAW_SHA256,
        byte_size=len(RAW_BODY),
        content_type="application/json",
        uri=None,
        storage_status=StorageExecutionStatus.NOT_EXECUTED,
    )


def _item(
    *,
    item_code: str,
    genre_id: int,
    price: int,
    available: bool,
    review_count: int | None,
    review_average: float | None,
) -> CanonicalItemSearchItem:
    return CanonicalItemSearchItem(
        provider="RAKUTEN_ICHIBA",
        api_version="2026-07-01",
        request_sha256=item_search_request().fingerprint,
        raw_sha256=RAW_SHA256,
        item_code=item_code,
        item_name="Model X JAN 4900000000000",
        catchcopy="Untrusted recorded catchcopy",
        item_caption="Untrusted recorded body-like caption",
        item_price_jpy=price,
        item_url=f"https://example.invalid/{item_code.replace(':', '/')}",
        affiliate_url="https://example.invalid/inert-affiliate",
        shop_code=item_code.partition(":")[0],
        shop_name="Synthetic shop",
        genre_id=genre_id,
        availability=available,
        review_count=review_count,
        review_average=review_average,
        affiliate_rate=3.5,
        postage_included=True,
        image_urls=(
            f"https://example.invalid/images/{genre_id}-2.jpg",
            f"https://example.invalid/images/{genre_id}-1.jpg",
        ),
        provider_updated_at=OBSERVED_AT - timedelta(hours=1),
        observed_at=OBSERVED_AT,
    )


def item_search_result() -> RakutenItemSearchResult:
    page = CanonicalItemSearchPage(
        provider="RAKUTEN_ICHIBA",
        api_version="2026-07-01",
        request_sha256=item_search_request().fingerprint,
        raw_artifact=raw_receipt(),
        observed_at=OBSERVED_AT,
        count=2,
        page=1,
        hits=2,
        page_count=1,
        items=(
            _item(
                item_code="shop-a:item-1",
                genre_id=100,
                price=1234,
                available=True,
                review_count=3,
                review_average=4.5,
            ),
            _item(
                item_code="shop-b:item-2",
                genre_id=101,
                price=2345,
                available=False,
                review_count=None,
                review_average=None,
            ),
        ),
        warnings=(),
        provider_rate_limit=rate_metadata(),
    )
    return RakutenItemSearchResult(
        provider_mode=ProviderMode.RECORDED_TEST_ONLY,
        page=page,
        rate=rate_metadata(),
        storage_status=StorageExecutionStatus.NOT_EXECUTED,
        persistence_status=PersistenceExecutionStatus.NOT_EXECUTED,
        live_eligible=False,
    )


def normalization_command(
    *, ingestion_request_id: UUID = INGESTION_ID
) -> CatalogNormalizationCommand:
    return CatalogNormalizationCommand.from_search_result(
        search_command=item_search_command(),
        search_result=item_search_result(),
        ingestion_request_id=ingestion_request_id,
        ingested_at=INGESTED_AT,
    )


def expected_batch() -> CatalogNormalizationBatch:
    return lossless_batch_from_command(normalization_command())


def recorded_adapter() -> RecordedCatalogNormalizationAdapter:
    fixture = RecordedCatalogNormalizationFixture(
        command=normalization_command(),
        batch=expected_batch(),
    )
    return RecordedCatalogNormalizationAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        fixture_capacity=1,
        fixtures=(fixture,),
    )


def normalization_service() -> CatalogNormalizationService:
    return CatalogNormalizationService(
        environment=RuntimeEnvironment.ENV_DEV,
        exchange=recorded_adapter(),
    )

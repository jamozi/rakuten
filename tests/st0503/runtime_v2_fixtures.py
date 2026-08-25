"""Exact persisted ST-0502 page fixtures for the ST-0503 V2 runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from uuid import UUID

from raos.adapters.recorded_catalog_normalization_runtime_v2 import (
    RecordedPersistedItemSearchPageSourceV2,
)
from raos.adapters.recorded_rakuten_item_search_runtime_v2 import (
    RecordedItemSearchExchangeV2,
    RecordedRakutenItemSearchPageProviderV2,
)
from raos.adapters.sqlite_catalog_normalization_runtime_v2 import (
    CatalogNormalizationSqliteCommitFaultV2,
    OwnerPrivateSqliteCatalogNormalizationStoreV2,
)
from raos.adapters.sqlite_rakuten_item_search_runtime_v2 import (
    OwnerPrivateSqliteItemSearchUnitOfWorkStoreV2,
)
from raos.application.catalog.catalog_normalization_runtime_v2 import (
    CatalogNormalizationRuntimeServiceV2,
)
from raos.application.catalog.rakuten_item_search_runtime_v2 import (
    RakutenItemSearchRuntimeServiceV2,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.catalog_normalization_runtime_v2 import (
    CatalogNormalizationCommandV2,
)
from raos.domain.catalog.rakuten_item_search_runtime_v2 import (
    ItemSearchPlanV2,
    ItemSearchProviderObservationV2,
    ItemSearchSortV2,
    ItemSearchStepCommandV2,
    ItemSearchWireRequestV2,
    ParsedItemSearchPageV2,
    PersistedItemSearchStepV2,
    ProviderModeV2,
    ProviderObservationKindV2,
    RateLimitObservationV2,
)


OBSERVED_AT_V2 = datetime(2026, 8, 25, 1, 2, 3, tzinfo=timezone.utc)
NORMALIZED_AT_V2 = OBSERVED_AT_V2 + timedelta(minutes=5)
SESSION_ID_V2 = UUID("52345678-1234-4234-8234-123456789001")
INGEST_OPERATION_ID_V2 = UUID("52345678-1234-4234-8234-123456789002")
NORMALIZE_OPERATION_IDS_V2 = (
    UUID("52345678-1234-4234-8234-123456789101"),
    UUID("52345678-1234-4234-8234-123456789102"),
    UUID("52345678-1234-4234-8234-123456789103"),
)


@dataclass(frozen=True, slots=True)
class PersistedSourceFixtureV2:
    archive: OwnerPrivateSqliteItemSearchUnitOfWorkStoreV2
    source: RecordedPersistedItemSearchPageSourceV2
    source_step: PersistedItemSearchStepV2
    request: ItemSearchWireRequestV2
    page: ParsedItemSearchPageV2
    raw_body: bytes
    command: CatalogNormalizationCommandV2


def item_payload_v2(
    ordinal: int,
    *,
    item_name: str | None = None,
    availability: int = 1,
    postage_flag: int = 0,
) -> dict[str, object]:
    return {
        "affiliateUrl": f"https://affiliate.example.test/items/{ordinal}",
        "availability": availability,
        "catchcopy": f"Recorded catchcopy {ordinal}",
        "genreId": 100 + ordinal,
        "itemCaption": f"Recorded item caption {ordinal}",
        "itemCode": f"synthetic-shop:item-{ordinal}",
        "itemName": item_name or f"Model X JAN 49000000000{ordinal}",
        "itemPrice": 10_000 + ordinal,
        "itemUrl": f"https://item.example.test/items/{ordinal}",
        "mediumImageUrls": [f"https://image.example.test/items/{ordinal}-medium.jpg"],
        "postageFlag": postage_flag,
        "shopCode": "synthetic-shop",
        "shopName": "Synthetic shop",
        "smallImageUrls": [f"https://image.example.test/items/{ordinal}-small.jpg"],
    }


def source_fixture_v2(
    root: Path,
    *,
    item_ordinals: tuple[int, ...] = (1, 2),
    item_name: str | None = None,
    normalize_operation_index: int = 0,
    expected_catalog_version: int = 0,
) -> PersistedSourceFixtureV2:
    root.mkdir(parents=True, exist_ok=True)
    plan = ItemSearchPlanV2(
        keyword="省スペース 掃除機",
        shop_code=None,
        item_code=None,
        genre_id=None,
        hits=len(item_ordinals),
        sort=ItemSearchSortV2.STANDARD,
        min_price_jpy=1_000,
        max_price_jpy=900_000,
        or_flag=False,
        availability=True,
        postage_included_only=False,
        appoint_delivery_date_only=False,
        attribute_flag=False,
        genre_information_flag=False,
        max_pages=1,
        retry_delays_seconds=(5, 30, 120),
        circuit_failure_threshold=2,
        circuit_cooldown_seconds=300,
    )
    request = ItemSearchWireRequestV2.from_plan(plan, page=1)
    items = [
        item_payload_v2(
            ordinal,
            item_name=item_name if index == 0 else None,
            availability=1 if ordinal % 2 else 0,
            postage_flag=0 if ordinal % 2 else 1,
        )
        for index, ordinal in enumerate(item_ordinals)
    ]
    payload: dict[str, object] = {
        "count": len(items),
        "first": 1,
        "hits": len(items),
        "items": items,
        "last": len(items),
        "page": 1,
        "pageCount": 1,
    }
    raw_body = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    observation = ItemSearchProviderObservationV2(
        kind=ProviderObservationKindV2.SUCCESS,
        mode=ProviderModeV2.RECORDED_SYNTHETIC,
        request_fingerprint=request.request_fingerprint,
        observed_at=OBSERVED_AT_V2,
        http_status=200,
        request_id="FIXTURE:ST0503:ARCHIVE",
        raw_body=raw_body,
        raw_sha256=hashlib.sha256(raw_body).hexdigest(),
        rate=RateLimitObservationV2(
            limit=100,
            remaining=99,
            reset_at=OBSERVED_AT_V2 + timedelta(minutes=2),
        ),
        retry_after_at=None,
        failure_class=None,
        external_actions=0,
    )
    provider = RecordedRakutenItemSearchPageProviderV2(
        environment=RuntimeEnvironment.CI,
        exchanges=(
            RecordedItemSearchExchangeV2(
                request=request,
                ordinal=1,
                observation=observation,
            ),
        ),
    )
    archive = OwnerPrivateSqliteItemSearchUnitOfWorkStoreV2(
        environment=RuntimeEnvironment.CI,
        root=root / "st0502-private",
    )
    ingestion = RakutenItemSearchRuntimeServiceV2(
        environment=RuntimeEnvironment.CI,
        provider=provider,
        store=archive,
    )
    ingestion.create_session(
        session_id=SESSION_ID_V2,
        plan=plan,
        created_at=OBSERVED_AT_V2,
    )
    result = ingestion.step_once(
        ItemSearchStepCommandV2(
            operation_id=INGEST_OPERATION_ID_V2,
            session_id=SESSION_ID_V2,
            expected_version=0,
            observed_at=OBSERVED_AT_V2,
        )
    )
    assert result.page is not None
    command = CatalogNormalizationCommandV2.from_persisted_page(
        operation_id=NORMALIZE_OPERATION_IDS_V2[normalize_operation_index],
        source_step=result.persisted,
        source_request=request,
        expected_catalog_version=expected_catalog_version,
        normalized_at=NORMALIZED_AT_V2 + timedelta(seconds=normalize_operation_index),
    )
    return PersistedSourceFixtureV2(
        archive=archive,
        source=RecordedPersistedItemSearchPageSourceV2(archive),
        source_step=result.persisted,
        request=request,
        page=result.page,
        raw_body=raw_body,
        command=command,
    )


def normalization_store_v2(
    root: Path,
    *,
    faults: tuple[CatalogNormalizationSqliteCommitFaultV2, ...] = (),
) -> OwnerPrivateSqliteCatalogNormalizationStoreV2:
    root.mkdir(parents=True, exist_ok=True)
    return OwnerPrivateSqliteCatalogNormalizationStoreV2(
        environment=RuntimeEnvironment.CI,
        root=root / "st0503-private",
        commit_faults=faults,
    )


def normalization_service_v2(
    *,
    fixture: PersistedSourceFixtureV2,
    store: OwnerPrivateSqliteCatalogNormalizationStoreV2,
) -> CatalogNormalizationRuntimeServiceV2:
    return CatalogNormalizationRuntimeServiceV2(
        environment=RuntimeEnvironment.CI,
        source=fixture.source,
        store=store,
    )


__all__ = [
    "NORMALIZED_AT_V2",
    "NORMALIZE_OPERATION_IDS_V2",
    "OBSERVED_AT_V2",
    "PersistedSourceFixtureV2",
    "item_payload_v2",
    "normalization_service_v2",
    "normalization_store_v2",
    "source_fixture_v2",
]

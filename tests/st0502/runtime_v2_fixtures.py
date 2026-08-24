"""Exact synthetic builders for the ST-0502 durable runtime tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from uuid import UUID

from raos.adapters.recorded_rakuten_item_search_runtime_v2 import (
    RecordedItemSearchExchangeV2,
    RecordedRakutenItemSearchPageProviderV2,
)
from raos.adapters.sqlite_rakuten_item_search_runtime_v2 import (
    OwnerPrivateSqliteItemSearchUnitOfWorkStoreV2,
    SqliteCommitFaultV2,
)
from raos.application.catalog.rakuten_item_search_runtime_v2 import (
    RakutenItemSearchRuntimeServiceV2,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.rakuten_item_search_runtime_v2 import (
    ItemSearchPlanV2,
    ItemSearchProviderObservationV2,
    ItemSearchSortV2,
    ItemSearchStepCommandV2,
    ItemSearchWireRequestV2,
    ProviderFailureClassV2,
    ProviderModeV2,
    ProviderObservationKindV2,
    RateLimitObservationV2,
)
from raos.ports.rakuten_item_search_runtime_v2 import (
    ItemSearchIngestionUnitOfWorkStoreV2,
    ItemSearchPageProviderV2,
)


OBSERVED_AT_V2 = datetime(2026, 8, 25, 1, 2, 3, tzinfo=timezone.utc)
RESET_AT_V2 = OBSERVED_AT_V2 + timedelta(minutes=2)
SESSION_ID_V2 = UUID("12345678-1234-4234-8234-123456789001")
OPERATION_IDS_V2 = (
    UUID("12345678-1234-4234-8234-123456789101"),
    UUID("12345678-1234-4234-8234-123456789102"),
    UUID("12345678-1234-4234-8234-123456789103"),
    UUID("12345678-1234-4234-8234-123456789104"),
)


def runtime_plan_v2(
    *,
    max_pages: int = 3,
    hits: int = 2,
    circuit_failure_threshold: int = 2,
) -> ItemSearchPlanV2:
    return ItemSearchPlanV2(
        keyword="省スペース 掃除機",
        shop_code=None,
        item_code=None,
        genre_id=None,
        hits=hits,
        sort=ItemSearchSortV2.STANDARD,
        min_price_jpy=1_000,
        max_price_jpy=900_000,
        or_flag=False,
        availability=True,
        postage_included_only=False,
        appoint_delivery_date_only=False,
        attribute_flag=False,
        genre_information_flag=False,
        max_pages=max_pages,
        retry_delays_seconds=(5, 30, 120),
        circuit_failure_threshold=circuit_failure_threshold,
        circuit_cooldown_seconds=300,
    )


def runtime_item_v2(
    ordinal: int,
    *,
    item_name: str | None = None,
) -> dict[str, object]:
    return {
        "affiliateUrl": f"https://affiliate.example.test/items/{ordinal}",
        "availability": 1,
        "catchcopy": "",
        "genreId": 100,
        "itemCaption": None,
        "itemCode": f"synthetic-shop:item-{ordinal}",
        "itemName": item_name or f"Synthetic item {ordinal}",
        "itemPrice": 10_000 + ordinal,
        "itemUrl": f"https://item.example.test/items/{ordinal}",
        "mediumImageUrls": [f"https://image.example.test/items/{ordinal}-medium.jpg"],
        "postageFlag": 0,
        "shopCode": "synthetic-shop",
        "shopName": "Synthetic shop",
        "smallImageUrls": [f"https://image.example.test/items/{ordinal}-small.jpg"],
    }


def runtime_payload_v2(
    *,
    page: int,
    page_count: int,
    hits: int = 2,
    item_ordinals: tuple[int, ...] | None = None,
    item_name: str | None = None,
) -> dict[str, object]:
    ordinals = item_ordinals or (page,)
    items = [
        runtime_item_v2(value, item_name=item_name if index == 0 else None)
        for index, value in enumerate(ordinals)
    ]
    first = (page - 1) * hits + 1
    last = first + len(items) - 1
    count = max(page_count * hits, last)
    return {
        "count": count,
        "first": first,
        "hits": hits,
        "items": items,
        "last": last,
        "page": page,
        "pageCount": page_count,
    }


def runtime_json_v2(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def runtime_success_observation_v2(
    request: ItemSearchWireRequestV2,
    *,
    observed_at: datetime,
    payload: dict[str, object] | None = None,
    raw: bytes | None = None,
    remaining: int | None = 99,
    reset_at: datetime | None = None,
    request_id: str = "FIXTURE:ST0502:SUCCESS",
) -> ItemSearchProviderObservationV2:
    body = (
        raw
        if raw is not None
        else runtime_json_v2(
            payload
            or runtime_payload_v2(
                page=request.page,
                page_count=request.page,
                hits=int(dict(request.parameter_pairs)["hits"]),
            )
        )
    )
    rate = (
        RateLimitObservationV2(limit=None, remaining=None, reset_at=None)
        if remaining is None
        else RateLimitObservationV2(
            limit=100,
            remaining=remaining,
            reset_at=reset_at or observed_at + timedelta(minutes=2),
        )
    )
    return ItemSearchProviderObservationV2(
        kind=ProviderObservationKindV2.SUCCESS,
        mode=ProviderModeV2.RECORDED_SYNTHETIC,
        request_fingerprint=request.request_fingerprint,
        observed_at=observed_at,
        http_status=200,
        request_id=request_id,
        raw_body=body,
        raw_sha256=hashlib.sha256(body).hexdigest(),
        rate=rate,
        retry_after_at=None,
        failure_class=None,
        external_actions=0,
    )


def runtime_failure_observation_v2(
    request: ItemSearchWireRequestV2,
    *,
    observed_at: datetime,
    status: int,
    retry_after_at: datetime | None = None,
) -> ItemSearchProviderObservationV2:
    mapping = {
        400: ProviderFailureClassV2.PERMANENT,
        401: ProviderFailureClassV2.AUTH,
        403: ProviderFailureClassV2.AUTH,
        404: ProviderFailureClassV2.PERMANENT,
        429: ProviderFailureClassV2.RATE_LIMITED,
        500: ProviderFailureClassV2.TRANSIENT,
        503: ProviderFailureClassV2.TRANSIENT,
    }
    return ItemSearchProviderObservationV2(
        kind=ProviderObservationKindV2.HTTP_FAILURE,
        mode=ProviderModeV2.RECORDED_SYNTHETIC,
        request_fingerprint=request.request_fingerprint,
        observed_at=observed_at,
        http_status=status,
        request_id=f"FIXTURE:ST0502:HTTP:{status}",
        raw_body=None,
        raw_sha256=None,
        rate=RateLimitObservationV2(limit=None, remaining=None, reset_at=None),
        retry_after_at=retry_after_at,
        failure_class=mapping[status],
        external_actions=0,
    )


def runtime_exchange_v2(
    request: ItemSearchWireRequestV2,
    observation: ItemSearchProviderObservationV2,
    *,
    ordinal: int = 1,
) -> RecordedItemSearchExchangeV2:
    return RecordedItemSearchExchangeV2(
        request=request,
        ordinal=ordinal,
        observation=observation,
    )


def runtime_provider_v2(
    *exchanges: RecordedItemSearchExchangeV2,
) -> RecordedRakutenItemSearchPageProviderV2:
    return RecordedRakutenItemSearchPageProviderV2(
        environment=RuntimeEnvironment.CI,
        exchanges=exchanges,
    )


def runtime_store_v2(
    root: Path,
    *,
    commit_faults: tuple[SqliteCommitFaultV2, ...] = (),
) -> OwnerPrivateSqliteItemSearchUnitOfWorkStoreV2:
    return OwnerPrivateSqliteItemSearchUnitOfWorkStoreV2(
        environment=RuntimeEnvironment.CI,
        root=root,
        commit_faults=commit_faults,
    )


def runtime_service_v2(
    *,
    provider: ItemSearchPageProviderV2,
    store: ItemSearchIngestionUnitOfWorkStoreV2,
) -> RakutenItemSearchRuntimeServiceV2:
    return RakutenItemSearchRuntimeServiceV2(
        environment=RuntimeEnvironment.CI,
        provider=provider,
        store=store,
    )


def runtime_command_v2(
    *,
    operation_index: int,
    expected_version: int,
    observed_at: datetime,
    session_id: UUID = SESSION_ID_V2,
) -> ItemSearchStepCommandV2:
    return ItemSearchStepCommandV2(
        operation_id=OPERATION_IDS_V2[operation_index],
        session_id=session_id,
        expected_version=expected_version,
        observed_at=observed_at,
    )


__all__ = [
    "OBSERVED_AT_V2",
    "OPERATION_IDS_V2",
    "RESET_AT_V2",
    "SESSION_ID_V2",
    "runtime_command_v2",
    "runtime_exchange_v2",
    "runtime_failure_observation_v2",
    "runtime_item_v2",
    "runtime_json_v2",
    "runtime_payload_v2",
    "runtime_plan_v2",
    "runtime_provider_v2",
    "runtime_service_v2",
    "runtime_store_v2",
    "runtime_success_observation_v2",
]

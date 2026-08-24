"""Recorded/disabled ST-0502 archive sources for ST-0503 V2.

The recorded adapter wraps only the read methods of an already-persisted
ST-0502 archive.  It has no HTTP client, credential, environment lookup,
provider request, worker, or mutation capability.
"""

from __future__ import annotations

from typing import final

from raos.domain.catalog.catalog_normalization_runtime_v2 import (
    CatalogNormalizationRuntimeFailureCode,
    CatalogSourceModeV2,
    fail_catalog_normalization_runtime,
)
from raos.domain.catalog.rakuten_item_search_runtime_v2 import (
    ItemSearchWireRequestV2,
    ParsedItemSearchPageV2,
    RawArchiveReceiptV2,
)
from raos.ports.rakuten_item_search_runtime_v2 import (
    ItemSearchIngestionUnitOfWorkStoreV2,
)


@final
class RecordedPersistedItemSearchPageSourceV2:
    """Read an exact ST-0502 owner-private archive with zero external action."""

    __slots__ = ("_archive",)

    def __init__(self, archive: ItemSearchIngestionUnitOfWorkStoreV2) -> None:
        self._archive = archive

    @property
    def mode(self) -> CatalogSourceModeV2:
        return CatalogSourceModeV2.RECORDED_PERSISTED

    @property
    def external_action_count(self) -> int:
        return 0

    def read_raw(self, receipt: RawArchiveReceiptV2) -> bytes:
        return self._archive.read_raw(receipt)

    def read_page(
        self,
        *,
        receipt: RawArchiveReceiptV2,
        request: ItemSearchWireRequestV2,
    ) -> ParsedItemSearchPageV2:
        return self._archive.read_page(receipt=receipt, request=request)


@final
class DisabledPersistedItemSearchPageSourceV2:
    """Default-disabled future activation boundary; always actionless."""

    __slots__ = ()

    @property
    def mode(self) -> CatalogSourceModeV2:
        return CatalogSourceModeV2.DISABLED

    @property
    def external_action_count(self) -> int:
        return 0

    def read_raw(self, receipt: RawArchiveReceiptV2) -> bytes:
        del receipt
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.SOURCE_UNAVAILABLE
        )

    def read_page(
        self,
        *,
        receipt: RawArchiveReceiptV2,
        request: ItemSearchWireRequestV2,
    ) -> ParsedItemSearchPageV2:
        del receipt, request
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.SOURCE_UNAVAILABLE
        )


__all__ = [
    "DisabledPersistedItemSearchPageSourceV2",
    "RecordedPersistedItemSearchPageSourceV2",
]

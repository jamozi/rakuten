"""Closed inward ports for durable ST-0503 catalog normalization V2."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.catalog.catalog_normalization_runtime_v2 import (
    CatalogCandidateV2,
    CatalogCommitRecoveryV2,
    CatalogNormalizationBatchV2,
    CatalogNormalizationCommandV2,
    CatalogNormalizedOutboxEventV2,
    CatalogObservationV2,
    CatalogOfferV2,
    CatalogSourceModeV2,
    CatalogSourceSnapshotV2,
    PersistedCatalogNormalizationV2,
)
from raos.domain.catalog.rakuten_item_search_runtime_v2 import (
    ItemSearchWireRequestV2,
    ParsedItemSearchPageV2,
    RawArchiveReceiptV2,
)


@runtime_checkable
class PersistedItemSearchPageSourceV2(Protocol):
    """Read-only exact ST-0502 archive capability; never a provider client."""

    @property
    def mode(self) -> CatalogSourceModeV2: ...

    @property
    def external_action_count(self) -> int: ...

    def read_raw(self, receipt: RawArchiveReceiptV2) -> bytes: ...

    def read_page(
        self,
        *,
        receipt: RawArchiveReceiptV2,
        request: ItemSearchWireRequestV2,
    ) -> ParsedItemSearchPageV2: ...


@runtime_checkable
class CatalogNormalizationUnitOfWorkStoreV2(Protocol):
    """One atomic batch/CAS/idempotency/outbox/hash-chain transaction."""

    @property
    def external_action_count(self) -> int: ...

    def lookup(
        self,
        command: CatalogNormalizationCommandV2,
    ) -> PersistedCatalogNormalizationV2 | None: ...

    def commit(
        self,
        *,
        command: CatalogNormalizationCommandV2,
        batch: CatalogNormalizationBatchV2,
        event: CatalogNormalizedOutboxEventV2,
    ) -> PersistedCatalogNormalizationV2: ...

    def recover_commit(
        self,
        command: CatalogNormalizationCommandV2,
    ) -> CatalogCommitRecoveryV2: ...

    def load_batch(self, batch_id: object) -> CatalogNormalizationBatchV2: ...

    def load_snapshot(self, snapshot_id: object) -> CatalogSourceSnapshotV2: ...

    def load_candidate(self, candidate_id: object) -> CatalogCandidateV2: ...

    def load_offer(self, offer_id: object) -> CatalogOfferV2: ...

    def list_observations(
        self, offer_id: object
    ) -> tuple[CatalogObservationV2, ...]: ...

    def load_outbox(self, event_id: object) -> CatalogNormalizedOutboxEventV2: ...


__all__ = [
    "CatalogNormalizationUnitOfWorkStoreV2",
    "PersistedItemSearchPageSourceV2",
]

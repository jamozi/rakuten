"""Closed inward ports for the maximum-safe local ST-0502 runtime."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from raos.domain.catalog.rakuten_item_search_runtime_v2 import (
    ItemSearchIngestionSessionV2,
    ItemSearchProviderObservationV2,
    ItemSearchStepCommandV2,
    ItemSearchWireRequestV2,
    ParsedItemSearchPageV2,
    PersistedItemSearchStepV2,
    ProviderFailureClassV2,
    ProviderModeV2,
    RawArchiveReceiptV2,
)


@runtime_checkable
class ItemSearchPageProviderV2(Protocol):
    """One recorded or disabled observation; live mode is unrepresentable."""

    @property
    def mode(self) -> ProviderModeV2: ...

    @property
    def external_action_count(self) -> int: ...

    def fetch_once(
        self,
        request: ItemSearchWireRequestV2,
        *,
        observed_at: datetime,
    ) -> ItemSearchProviderObservationV2: ...


@runtime_checkable
class ItemSearchIngestionUnitOfWorkStoreV2(Protocol):
    """Atomic local archive, session-CAS, and command-journal capability."""

    def create_session(self, session: ItemSearchIngestionSessionV2) -> None: ...

    def load_session(self, session_id: object) -> ItemSearchIngestionSessionV2: ...

    def lookup_step(
        self,
        command: ItemSearchStepCommandV2,
    ) -> PersistedItemSearchStepV2 | None: ...

    def commit_success(
        self,
        *,
        command: ItemSearchStepCommandV2,
        before: ItemSearchIngestionSessionV2,
        after: ItemSearchIngestionSessionV2,
        request: ItemSearchWireRequestV2,
        observation: ItemSearchProviderObservationV2,
        page: ParsedItemSearchPageV2,
    ) -> PersistedItemSearchStepV2: ...

    def commit_failure(
        self,
        *,
        command: ItemSearchStepCommandV2,
        before: ItemSearchIngestionSessionV2,
        after: ItemSearchIngestionSessionV2,
        request: ItemSearchWireRequestV2,
        failure_class: ProviderFailureClassV2,
        observation: ItemSearchProviderObservationV2 | None,
    ) -> PersistedItemSearchStepV2: ...

    def read_raw(self, receipt: RawArchiveReceiptV2) -> bytes: ...

    def read_page(
        self,
        *,
        receipt: RawArchiveReceiptV2,
        request: ItemSearchWireRequestV2,
    ) -> ParsedItemSearchPageV2: ...


__all__ = [
    "ItemSearchIngestionUnitOfWorkStoreV2",
    "ItemSearchPageProviderV2",
]

"""Narrow inward and outward ports for the fixed WordPress.com Wave 3 slice."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.editorial.wordpresscom_mvp_drafts import (
    MvpDraftOperation,
    MvpDraftPreview,
    MvpMutationAcknowledgement,
    MvpPageScan,
    MvpRemoteObject,
)


@runtime_checkable
class WordPressComMvpDraftsPort(Protocol):
    """Argument-free application boundary; publication is intentionally absent."""

    def prepare(self) -> MvpDraftPreview: ...

    def preview(self) -> MvpDraftPreview: ...


@runtime_checkable
class WordPressComMvpFixedProviderPort(Protocol):
    """Fixed provider operations; arbitrary HTTP and retry are intentionally absent."""

    def read_article(self) -> MvpRemoteObject: ...

    def scan_pages(self) -> MvpPageScan: ...

    def read_page(
        self, operation: MvpDraftOperation, object_id: str
    ) -> MvpRemoteObject: ...

    def update_article_once(
        self, operation: MvpDraftOperation
    ) -> MvpMutationAcknowledgement: ...

    def create_page_once(
        self, operation: MvpDraftOperation
    ) -> MvpMutationAcknowledgement: ...


__all__ = ["WordPressComMvpDraftsPort", "WordPressComMvpFixedProviderPort"]

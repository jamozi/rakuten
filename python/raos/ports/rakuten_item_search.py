"""Inward recorded-only ITEM_SEARCH ports for ST-0502."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.catalog.rakuten_item_search import (
    CanonicalItemSearchPage,
    ProviderCapabilities,
    ProviderFailure,
    ProviderHealth,
    RakutenItemSearchCommand,
    RateLimitMetadata,
    RawItemSearchResponse,
    RawResponseReceipt,
)


@runtime_checkable
class RakutenItemSearchProvider(Protocol):
    def capabilities(self) -> ProviderCapabilities: ...

    def health(self) -> ProviderHealth: ...

    def execute(self, command: RakutenItemSearchCommand) -> RawItemSearchResponse: ...

    def normalize(self, response: RawItemSearchResponse) -> CanonicalItemSearchPage: ...

    def classify(self, error: Exception) -> ProviderFailure: ...

    def rate(self, response: RawItemSearchResponse) -> RateLimitMetadata: ...


@runtime_checkable
class RawResponseRecorder(Protocol):
    def record(self, response: RawItemSearchResponse) -> RawResponseReceipt: ...


__all__ = ["RakutenItemSearchProvider", "RawResponseRecorder"]

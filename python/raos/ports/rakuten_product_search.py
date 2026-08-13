"""Inward recorded-only Product Search port for ST-0502."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.catalog.rakuten_product_search import (
    RakutenProductSearchRequest,
    RakutenProductSearchResult,
)


@runtime_checkable
class RecordedRakutenProductSearchPort(Protocol):
    def search(
        self, request: RakutenProductSearchRequest
    ) -> RakutenProductSearchResult: ...


__all__ = ["RecordedRakutenProductSearchPort"]

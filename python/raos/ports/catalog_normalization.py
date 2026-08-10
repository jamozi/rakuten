"""Single inward catalog-normalization exchange for ST-0503."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.catalog.catalog_normalization import (
    CatalogNormalizationBatch,
    CatalogNormalizationCommand,
)


@runtime_checkable
class CatalogNormalizationExchange(Protocol):
    def normalize(
        self, command: CatalogNormalizationCommand
    ) -> CatalogNormalizationBatch: ...


__all__ = ["CatalogNormalizationExchange"]

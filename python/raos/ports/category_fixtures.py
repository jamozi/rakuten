"""Inward recorded-only category fixture port for ST-1702."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.catalog.category_fixtures import (
    CategoryFixtureLoadRequest,
    CategoryFixtureLoadResult,
)


@runtime_checkable
class RecordedCategoryFixturePort(Protocol):
    def load(
        self, request: CategoryFixtureLoadRequest
    ) -> CategoryFixtureLoadResult: ...


__all__ = ["RecordedCategoryFixturePort"]

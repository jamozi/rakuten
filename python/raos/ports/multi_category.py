"""Provider-neutral inward recording port for Canonical ST-1904."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.catalog.multi_category import (
    MultiCategoryEvaluationCommand,
    RecordedMultiCategoryBundle,
)


@runtime_checkable
class RecordedMultiCategorySource(Protocol):
    """Consume one caller-owned recorded synthetic category catalog once."""

    def read(
        self, command: MultiCategoryEvaluationCommand
    ) -> RecordedMultiCategoryBundle: ...


__all__ = ("RecordedMultiCategorySource",)

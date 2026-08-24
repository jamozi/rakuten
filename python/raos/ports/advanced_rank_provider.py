"""Inward provider-neutral source port for the ST-1905 local seam."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.analytics.advanced_rank_provider import (
    AdvancedRankProviderCommand,
    RecordedAdvancedRankBatch,
)


@runtime_checkable
class AdvancedRankProviderEvidenceSource(Protocol):
    """Consume one command-bound recording and return normalized domain rows."""

    def read(
        self, command: AdvancedRankProviderCommand
    ) -> RecordedAdvancedRankBatch: ...


__all__ = ["AdvancedRankProviderEvidenceSource"]

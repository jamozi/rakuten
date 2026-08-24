"""Provider-neutral inward evidence port for the ST-1906 local seam."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.analytics.causal_attribution import (
    CausalAttributionCommand,
    RecordedCausalAttributionBatch,
)


@runtime_checkable
class CausalAttributionEvidenceSource(Protocol):
    """Consume one command-bound aggregate recording exactly once."""

    def read(
        self, command: CausalAttributionCommand
    ) -> RecordedCausalAttributionBatch: ...


__all__ = ("CausalAttributionEvidenceSource",)

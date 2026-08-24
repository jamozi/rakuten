"""Provider-neutral inward evidence port for the ST-1907 local seam."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.portfolio.content_optimizer import (
    PortfolioOptimizerCommand,
    RecordedPortfolioOptimizationBatch,
)


@runtime_checkable
class PortfolioOptimizationEvidenceSource(Protocol):
    """Consume one command-bound recorded-synthetic document exactly once."""

    def read(
        self, command: PortfolioOptimizerCommand
    ) -> RecordedPortfolioOptimizationBatch: ...


__all__ = ("PortfolioOptimizationEvidenceSource",)

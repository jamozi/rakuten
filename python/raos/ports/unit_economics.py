"""Provider-neutral inward port for the ST-1304 recorded calculation."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.finance.unit_economics import (
    UnitEconomicsRunRequest,
    UnitEconomicsRunResult,
)


@runtime_checkable
class UnitEconomicsRunPort(Protocol):
    """Execute or replay one deterministic process-local recorded run."""

    def run(self, request: UnitEconomicsRunRequest) -> UnitEconomicsRunResult: ...


__all__ = ("UnitEconomicsRunPort",)

"""Provider-neutral inward port for the ST-1303 attribution run."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.finance.attribution import AttributionRunRequest, AttributionRunResult


@runtime_checkable
class AttributionRunPort(Protocol):
    """Execute or replay one deterministic process-local recorded run."""

    def run(self, request: AttributionRunRequest) -> AttributionRunResult: ...


__all__ = ("AttributionRunPort",)

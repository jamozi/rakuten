"""Inward provider-neutral source port for the ST-1902 local shadow seam."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.ai.champion_challenger import (
    RecordedShadowBatch,
    ShadowRoutingCommand,
)


@runtime_checkable
class RecordedShadowEvidenceSource(Protocol):
    """Consume one command-bound recording and return immutable observations."""

    def read(self, command: ShadowRoutingCommand) -> RecordedShadowBatch: ...


__all__ = ["RecordedShadowEvidenceSource"]

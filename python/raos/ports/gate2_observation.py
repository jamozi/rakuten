"""Credential-free inward port for one recorded ST-1803 observation batch."""

from __future__ import annotations

from typing import Protocol

from raos.domain.analytics.gate2_observation import (
    ObservationCommand,
    RecordedObservationBatch,
)


class RecordedGate2ObservationExchange(Protocol):
    """Consume one exact caller-bound synthetic fixture without external I/O."""

    def read(self, command: ObservationCommand) -> RecordedObservationBatch:
        """Return the one immutable recorded batch."""

        ...


__all__ = ["RecordedGate2ObservationExchange"]

"""Credential-free inward port for one recorded ST-1804 economics batch."""

from __future__ import annotations

from typing import Protocol

from raos.domain.analytics.gate3_economics import (
    Gate3Command,
    RecordedEconomicsBatch,
)


class RecordedGate3EconomicsExchange(Protocol):
    def read(self, command: Gate3Command) -> RecordedEconomicsBatch: ...


__all__ = ["RecordedGate3EconomicsExchange"]

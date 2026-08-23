"""Inward ports for the ST-1704 owner-local pilot ledger."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from raos.domain.editorial.owner_local_pilot import (
    AppendDisposition,
    PilotLedger,
    PilotObservation,
)


@dataclass(frozen=True, slots=True)
class PilotAppendResult:
    ledger: PilotLedger
    disposition: AppendDisposition
    event_sha256: str


class PilotLedgerStore(Protocol):
    def initialize(self) -> tuple[PilotLedger, bool]: ...

    def read(self) -> PilotLedger: ...

    def append(self, observation: PilotObservation) -> PilotAppendResult: ...


class PilotObservationInput(Protocol):
    def read_observation(self) -> PilotObservation: ...


__all__ = [
    "PilotAppendResult",
    "PilotLedgerStore",
    "PilotObservationInput",
]

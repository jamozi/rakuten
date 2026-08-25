"""Inward ports for the ST-1704 affiliate-learning V2 ledger."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from raos.domain.editorial.affiliate_learning import (
    AffiliateLearningLedger,
    AppendDisposition,
    LearningObservation,
)


@dataclass(frozen=True, slots=True)
class AffiliateLearningAppendResult:
    ledger: AffiliateLearningLedger
    disposition: AppendDisposition
    event_sha256: str


class AffiliateLearningLedgerStore(Protocol):
    def initialize(self) -> tuple[AffiliateLearningLedger, bool]: ...

    def read(self) -> AffiliateLearningLedger: ...

    def append(
        self, observation: LearningObservation
    ) -> AffiliateLearningAppendResult: ...


class AffiliateLearningObservationInput(Protocol):
    def read_observation(self) -> LearningObservation: ...


__all__ = [
    "AffiliateLearningAppendResult",
    "AffiliateLearningLedgerStore",
    "AffiliateLearningObservationInput",
]

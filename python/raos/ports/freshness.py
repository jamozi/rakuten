"""Single inward exchange for the recorded ST-1401 freshness seam."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.freshness.freshness import (
    FreshnessEvaluation,
    FreshnessEvaluationRequest,
    FreshnessScheduleRequest,
    FreshnessScheduleSelection,
)


@runtime_checkable
class FreshnessExchange(Protocol):
    def evaluate(self, request: FreshnessEvaluationRequest) -> FreshnessEvaluation: ...

    def select_due(
        self, request: FreshnessScheduleRequest
    ) -> FreshnessScheduleSelection: ...


__all__ = ["FreshnessExchange"]

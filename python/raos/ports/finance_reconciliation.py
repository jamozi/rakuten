"""Provider-neutral inward port for the ST-1305 recorded report."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.finance.reconciliation import (
    FinanceReconciliationRunRequest,
    FinanceReconciliationRunResult,
)


@runtime_checkable
class FinanceReconciliationRunPort(Protocol):
    """Execute or replay one deterministic process-local report."""

    def run(
        self, request: FinanceReconciliationRunRequest
    ) -> FinanceReconciliationRunResult: ...


__all__ = ("FinanceReconciliationRunPort",)

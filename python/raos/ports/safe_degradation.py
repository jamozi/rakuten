"""Single inward port for the recorded ST-1402 safe-degradation seam."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.freshness.safe_degradation import (
    SafeDegradationDecision,
    SafeDegradationRequest,
)


@runtime_checkable
class SafeDegradationExchange(Protocol):
    def decide(self, request: SafeDegradationRequest) -> SafeDegradationDecision: ...


__all__ = ["SafeDegradationExchange"]

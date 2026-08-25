"""Credential-free inward port for the ST-1805 recorded decision input."""

from __future__ import annotations

from typing import Protocol

from raos.domain.portfolio.scale_decision import (
    PortfolioDecisionCommand,
    PortfolioDecisionEvidence,
)


class RecordedPortfolioDecisionExchange(Protocol):
    def read(self, command: PortfolioDecisionCommand) -> PortfolioDecisionEvidence: ...


__all__ = ["RecordedPortfolioDecisionExchange"]

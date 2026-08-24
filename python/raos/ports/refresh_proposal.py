"""Single inward port for the recorded ST-1403 refresh proposal seam."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.freshness.refresh_proposal import (
    RefreshProposal,
    RefreshProposalRequest,
)


@runtime_checkable
class RefreshProposalExchange(Protocol):
    def propose(self, request: RefreshProposalRequest) -> RefreshProposal: ...


__all__ = ["RefreshProposalExchange"]

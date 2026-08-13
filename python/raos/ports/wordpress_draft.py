"""Inward WordPress draft-only port for the ST-1703 local pilot."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.editorial.market_learning_pilot import (
    BoundWordPressDraft,
    WordPressDraftReceipt,
)


@runtime_checkable
class WordPressDraftPort(Protocol):
    """Apply one exact create/update draft candidate without publishing."""

    def apply(self, candidate: BoundWordPressDraft) -> WordPressDraftReceipt: ...


__all__ = ["WordPressDraftPort"]

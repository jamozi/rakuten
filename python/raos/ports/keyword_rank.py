"""Inward provider-neutral source port for the ST-1206 local seam."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.analytics.keyword_rank import (
    KeywordRankBatch,
    KeywordRankEvaluationCommand,
)


@runtime_checkable
class KeywordRankSource(Protocol):
    """Return normalized observations without exposing provider-specific types."""

    def read(self, command: KeywordRankEvaluationCommand) -> KeywordRankBatch:
        """Consume one command-bound source and return one immutable batch."""

        ...


__all__ = ["KeywordRankSource"]

"""Inward port for one scripted ST-0802 article-lifecycle exchange."""

from __future__ import annotations

from typing import Protocol

from raos.domain.editorial.article_lifecycle import (
    ArticleLifecycleOutcome,
    ArticleLifecycleRequest,
)


class ArticleLifecycleExchange(Protocol):
    """Exchange one exact request for one pre-recorded outcome."""

    def exchange(self, request: ArticleLifecycleRequest) -> ArticleLifecycleOutcome:
        """Return the exact next scripted outcome without persistence."""


__all__ = ["ArticleLifecycleExchange"]

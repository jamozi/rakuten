"""Single inward exchange port for the ST-0501 recorded workflow."""

from __future__ import annotations

from typing import Protocol, TypeAlias, runtime_checkable

from raos.domain.editorial.article_plan import (
    ArticlePlanWorkflowOutcome,
    ArticlePlanWorkflowRequest,
)
from raos.domain.portfolio.workflow import (
    CorePortfolioWorkflowOutcome,
    CorePortfolioWorkflowRequest,
)


PortfolioWorkflowRequest: TypeAlias = (
    CorePortfolioWorkflowRequest | ArticlePlanWorkflowRequest
)
PortfolioWorkflowOutcome: TypeAlias = (
    CorePortfolioWorkflowOutcome | ArticlePlanWorkflowOutcome
)


@runtime_checkable
class PortfolioWorkflowExchange(Protocol):
    """Exchange one exact request for one pre-scripted local outcome."""

    def exchange(
        self,
        request: PortfolioWorkflowRequest,
    ) -> PortfolioWorkflowOutcome: ...


__all__ = [
    "PortfolioWorkflowExchange",
    "PortfolioWorkflowOutcome",
    "PortfolioWorkflowRequest",
]

"""Portfolio repository composition surface for the shared SQLAlchemy UoW owner."""

from __future__ import annotations

from typing import cast

from sqlalchemy.orm import Session

from raos.adapters.persistence.sqlalchemy.repositories.portfolio import (
    SqlAlchemyActionCandidateRepository,
    SqlAlchemyCategoryRepository,
    SqlAlchemyIntentClusterRepository,
    SqlAlchemyKeywordRepository,
    SqlAlchemyOpportunityAssessmentRepository,
    SqlAlchemySiteRepository,
)


class SqlAlchemyPortfolioRepositories:
    __slots__ = (
        "action_candidates",
        "categories",
        "intent_clusters",
        "keywords",
        "opportunity_assessments",
        "sites",
    )

    def __init__(self, session: Session) -> None:
        if not isinstance(cast(object, session), Session):
            raise ValueError("INVALID_PORTFOLIO_UOW_SURFACE") from None
        self.sites = SqlAlchemySiteRepository(session)
        self.categories = SqlAlchemyCategoryRepository(session)
        self.intent_clusters = SqlAlchemyIntentClusterRepository(session)
        self.keywords = SqlAlchemyKeywordRepository(session)
        self.opportunity_assessments = SqlAlchemyOpportunityAssessmentRepository(
            session
        )
        self.action_candidates = SqlAlchemyActionCandidateRepository(session)


__all__ = ["SqlAlchemyPortfolioRepositories"]

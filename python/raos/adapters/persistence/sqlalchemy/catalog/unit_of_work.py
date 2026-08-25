"""Catalog repository composition surface for the shared SQLAlchemy UoW owner."""

from __future__ import annotations

from typing import cast

from sqlalchemy.orm import Session

from raos.adapters.persistence.sqlalchemy.repositories.catalog import (
    SqlAlchemyAttributeDefinitionRepository,
    SqlAlchemyCanonicalProductRepository,
    SqlAlchemyGroupingDecisionRepository,
    SqlAlchemyIngestionRequestRepository,
    SqlAlchemyOfferRepository,
    SqlAlchemyProductCandidateRepository,
    SqlAlchemyProviderEndpointRepository,
    SqlAlchemyRakutenGenreRepository,
    SqlAlchemySafeOfferCurrentReader,
    SqlAlchemyShopRepository,
)


class SqlAlchemyCatalogRepositories:
    __slots__ = (
        "attribute_definitions",
        "canonical_products",
        "grouping_decisions",
        "ingestion_requests",
        "offers",
        "product_candidates",
        "provider_endpoints",
        "rakuten_genres",
        "safe_offer_current",
        "shops",
    )

    def __init__(self, session: Session) -> None:
        if not isinstance(cast(object, session), Session):
            raise ValueError("INVALID_CATALOG_UOW_SURFACE") from None
        self.provider_endpoints = SqlAlchemyProviderEndpointRepository(session)
        self.ingestion_requests = SqlAlchemyIngestionRequestRepository(session)
        self.rakuten_genres = SqlAlchemyRakutenGenreRepository(session)
        self.shops = SqlAlchemyShopRepository(session)
        self.canonical_products = SqlAlchemyCanonicalProductRepository(session)
        self.product_candidates = SqlAlchemyProductCandidateRepository(session)
        self.grouping_decisions = SqlAlchemyGroupingDecisionRepository(session)
        self.attribute_definitions = SqlAlchemyAttributeDefinitionRepository(session)
        self.offers = SqlAlchemyOfferRepository(session)
        self.safe_offer_current = SqlAlchemySafeOfferCurrentReader(session)


__all__ = ["SqlAlchemyCatalogRepositories"]

"""Catalog inward persistence ports."""

from raos.ports.catalog.repositories import (
    AttributeDefinitionRepository,
    CanonicalProductRepository,
    GroupingDecisionRepository,
    IngestionRequestRepository,
    OfferRepository,
    ProductCandidateRepository,
    ProviderEndpointRepository,
    RakutenGenreRepository,
    SafeOfferCurrentReader,
    ShopRepository,
)

__all__ = [
    "AttributeDefinitionRepository",
    "CanonicalProductRepository",
    "GroupingDecisionRepository",
    "IngestionRequestRepository",
    "OfferRepository",
    "ProductCandidateRepository",
    "ProviderEndpointRepository",
    "RakutenGenreRepository",
    "SafeOfferCurrentReader",
    "ShopRepository",
]

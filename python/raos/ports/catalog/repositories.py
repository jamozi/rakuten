"""Aggregate-specific inward Catalog repository protocols for ST-0308."""

from __future__ import annotations

from typing import Protocol, TypeAlias, runtime_checkable

from raos.domain.catalog.aggregates import (
    AffiliateLinkObservation,
    AttributeDefinition,
    AvailabilityObservation,
    CanonicalProduct,
    CategoryGenreMapping,
    GroupingDecision,
    IngestionRequest,
    Offer,
    OfferCurrentProjection,
    PriceObservation,
    ProductAttributeValue,
    ProductCandidate,
    ProductGroupMembership,
    ProductRelation,
    ProviderEndpoint,
    RakutenGenre,
    ReviewAggregateObservation,
    SafeOfferCurrent,
    Shop,
)
from raos.domain.catalog.enums import IngestionRequestStatus, ProviderEndpointStatus
from raos.domain.catalog.ids import (
    AttributeDefinitionId,
    CanonicalProductId,
    CategoryGenreMappingId,
    GroupingDecisionId,
    IngestionRequestId,
    OfferId,
    ProductCandidateId,
    ProviderEndpointId,
    RakutenGenreId,
    ShopId,
)
from raos.domain.shared.persistence import AggregateVersion, PersistedVersion


OfferObservation: TypeAlias = (
    PriceObservation
    | AvailabilityObservation
    | ReviewAggregateObservation
    | AffiliateLinkObservation
)


@runtime_checkable
class ProviderEndpointRepository(Protocol):
    def get(self, endpoint_id: ProviderEndpointId) -> ProviderEndpoint | None: ...
    def get_active(
        self, provider_code: str, api_name: str
    ) -> ProviderEndpoint | None: ...
    def add(self, endpoint: ProviderEndpoint) -> None: ...
    def transition(
        self,
        endpoint_id: ProviderEndpointId,
        transition: ProviderEndpoint,
        expected_status: ProviderEndpointStatus,
    ) -> ProviderEndpoint: ...


@runtime_checkable
class IngestionRequestRepository(Protocol):
    def get(self, request_id: IngestionRequestId) -> IngestionRequest | None: ...
    def add(self, request: IngestionRequest) -> None: ...
    def complete(
        self,
        request_id: IngestionRequestId,
        outcome: IngestionRequest,
        expected_status: IngestionRequestStatus,
    ) -> IngestionRequest: ...


@runtime_checkable
class RakutenGenreRepository(Protocol):
    def get(self, genre_id: RakutenGenreId) -> RakutenGenre | None: ...
    def add(self, genre: RakutenGenre) -> PersistedVersion: ...
    def save(
        self, genre: RakutenGenre, expected_version: AggregateVersion
    ) -> PersistedVersion: ...
    def get_mapping(
        self, mapping_id: CategoryGenreMappingId
    ) -> CategoryGenreMapping | None: ...
    def append_mapping(self, mapping: CategoryGenreMapping) -> None: ...


@runtime_checkable
class ShopRepository(Protocol):
    def get(self, shop_id: ShopId) -> Shop | None: ...
    def add(self, shop: Shop) -> PersistedVersion: ...
    def save(
        self, shop: Shop, expected_version: AggregateVersion
    ) -> PersistedVersion: ...


@runtime_checkable
class CanonicalProductRepository(Protocol):
    def get(self, product_id: CanonicalProductId) -> CanonicalProduct | None: ...
    def add(self, product: CanonicalProduct) -> PersistedVersion: ...
    def save(
        self, product: CanonicalProduct, expected_version: AggregateVersion
    ) -> PersistedVersion: ...
    def append_memberships(
        self,
        product_id: CanonicalProductId,
        memberships: tuple[ProductGroupMembership, ...],
        expected_version: AggregateVersion,
    ) -> PersistedVersion: ...
    def append_relations(
        self,
        product_id: CanonicalProductId,
        relations: tuple[ProductRelation, ...],
        expected_version: AggregateVersion,
    ) -> PersistedVersion: ...


@runtime_checkable
class ProductCandidateRepository(Protocol):
    def get(self, candidate_id: ProductCandidateId) -> ProductCandidate | None: ...
    def add(self, candidate: ProductCandidate) -> PersistedVersion: ...
    def save(
        self, candidate: ProductCandidate, expected_version: AggregateVersion
    ) -> PersistedVersion: ...


@runtime_checkable
class GroupingDecisionRepository(Protocol):
    def get(self, decision_id: GroupingDecisionId) -> GroupingDecision | None: ...
    def append(self, decision: GroupingDecision) -> None: ...


@runtime_checkable
class AttributeDefinitionRepository(Protocol):
    def get(
        self, definition_id: AttributeDefinitionId
    ) -> AttributeDefinition | None: ...
    def add(self, definition: AttributeDefinition) -> PersistedVersion: ...
    def save(
        self, definition: AttributeDefinition, expected_version: AggregateVersion
    ) -> PersistedVersion: ...
    def append_values(
        self,
        definition_id: AttributeDefinitionId,
        values: tuple[ProductAttributeValue, ...],
        expected_version: AggregateVersion,
    ) -> PersistedVersion: ...


@runtime_checkable
class OfferRepository(Protocol):
    def get(self, offer_id: OfferId) -> Offer | None: ...
    def add(self, offer: Offer) -> PersistedVersion: ...
    def save(
        self, offer: Offer, expected_version: AggregateVersion
    ) -> PersistedVersion: ...
    def append_observations(
        self,
        offer_id: OfferId,
        batch: tuple[OfferObservation, ...],
        expected_version: AggregateVersion,
    ) -> PersistedVersion: ...
    def get_current_projection(
        self, offer_id: OfferId
    ) -> OfferCurrentProjection | None: ...


@runtime_checkable
class SafeOfferCurrentReader(Protocol):
    def get_by_offer(self, offer_id: OfferId) -> SafeOfferCurrent | None: ...
    def list_by_product(
        self, product_id: CanonicalProductId
    ) -> tuple[SafeOfferCurrent, ...]: ...


__all__ = [
    "AttributeDefinitionRepository",
    "CanonicalProductRepository",
    "GroupingDecisionRepository",
    "IngestionRequestRepository",
    "OfferObservation",
    "OfferRepository",
    "ProductCandidateRepository",
    "ProviderEndpointRepository",
    "RakutenGenreRepository",
    "SafeOfferCurrentReader",
    "ShopRepository",
]

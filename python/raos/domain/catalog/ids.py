"""Nominal CATALOG persistence identities selected by ST-0308."""

from raos.domain.shared.identity import EntityId


class AffiliateLinkObservationId(EntityId):
    __slots__ = ()


class AttributeDefinitionId(EntityId):
    __slots__ = ()


class AvailabilityObservationId(EntityId):
    __slots__ = ()


class CanonicalProductId(EntityId):
    __slots__ = ()


class CategoryGenreMappingId(EntityId):
    __slots__ = ()


class GroupingDecisionId(EntityId):
    __slots__ = ()


class IngestionRequestId(EntityId):
    __slots__ = ()


class OfferId(EntityId):
    __slots__ = ()


class PriceObservationId(EntityId):
    __slots__ = ()


class ProductAttributeValueId(EntityId):
    __slots__ = ()


class ProductCandidateId(EntityId):
    __slots__ = ()


class ProductGroupMembershipId(EntityId):
    __slots__ = ()


class ProductRelationId(EntityId):
    __slots__ = ()


class ProviderEndpointId(EntityId):
    __slots__ = ()


class RakutenGenreId(EntityId):
    __slots__ = ()


class ReviewAggregateObservationId(EntityId):
    __slots__ = ()


class ShopId(EntityId):
    __slots__ = ()


__all__ = [
    "AffiliateLinkObservationId",
    "AttributeDefinitionId",
    "AvailabilityObservationId",
    "CanonicalProductId",
    "CategoryGenreMappingId",
    "GroupingDecisionId",
    "IngestionRequestId",
    "OfferId",
    "PriceObservationId",
    "ProductAttributeValueId",
    "ProductCandidateId",
    "ProductGroupMembershipId",
    "ProductRelationId",
    "ProviderEndpointId",
    "RakutenGenreId",
    "ReviewAggregateObservationId",
    "ShopId",
]

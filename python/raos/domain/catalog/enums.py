"""Closed physical enums for the ST-0308 CATALOG persistence slice."""

from enum import Enum


class AffiliateLinkObservationValidationStatus(str, Enum):
    VALID = "VALID"
    UNVERIFIED = "UNVERIFIED"
    INVALID = "INVALID"
    EXPIRED = "EXPIRED"
    BLOCKED = "BLOCKED"


class AttributeDefinitionDataType(str, Enum):
    TEXT = "TEXT"
    NUMERIC = "NUMERIC"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    CODE = "CODE"


class AttributeDefinitionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class AvailabilityObservationAvailability(str, Enum):
    IN_STOCK = "IN_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    BACKORDER = "BACKORDER"
    PREORDER = "PREORDER"
    DISCONTINUED = "DISCONTINUED"
    UNKNOWN = "UNKNOWN"


class AvailabilityObservationValidationStatus(str, Enum):
    VALID = "VALID"
    SUSPECT = "SUSPECT"
    INVALID = "INVALID"
    CONFLICT = "CONFLICT"


class CanonicalProductLifecycleStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DISCONTINUED = "DISCONTINUED"
    MERGED = "MERGED"
    SPLIT = "SPLIT"
    UNKNOWN = "UNKNOWN"


class CategoryGenreMappingMappingRole(str, Enum):
    PRIMARY = "PRIMARY"
    INCLUDE = "INCLUDE"
    EXCLUDE = "EXCLUDE"


class GroupingDecisionDecisionType(str, Enum):
    AUTO_ACCEPT = "AUTO_ACCEPT"
    HUMAN_ACCEPT = "HUMAN_ACCEPT"
    REJECT = "REJECT"
    SPLIT = "SPLIT"
    UNDECIDED = "UNDECIDED"


class IngestionRequestStatus(str, Enum):
    REQUESTED = "REQUESTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    QUARANTINED = "QUARANTINED"


class OfferStatus(str, Enum):
    ACTIVE = "ACTIVE"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    ENDED = "ENDED"
    SUSPENDED = "SUSPENDED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class OfferCurrentProjectionCurrentAvailability(str, Enum):
    IN_STOCK = "IN_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    BACKORDER = "BACKORDER"
    PREORDER = "PREORDER"
    DISCONTINUED = "DISCONTINUED"
    UNKNOWN = "UNKNOWN"


class OfferCurrentProjectionFreshnessStatus(str, Enum):
    FRESH = "FRESH"
    WARNING = "WARNING"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"


class PriceObservationShippingCondition(str, Enum):
    FREE = "FREE"
    PAID = "PAID"
    CONDITIONAL = "CONDITIONAL"
    INCLUDED = "INCLUDED"
    UNKNOWN = "UNKNOWN"


class PriceObservationValidationStatus(str, Enum):
    VALID = "VALID"
    SUSPECT = "SUSPECT"
    INVALID = "INVALID"
    CONFLICT = "CONFLICT"


class ProductCandidateListingStatus(str, Enum):
    ACTIVE = "ACTIVE"
    MISSING = "MISSING"
    ENDED = "ENDED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class ProductRelationRelationType(str, Enum):
    VARIANT = "VARIANT"
    SUCCESSOR = "SUCCESSOR"
    PREDECESSOR = "PREDECESSOR"
    BUNDLE = "BUNDLE"
    COMPATIBLE = "COMPATIBLE"
    EQUIVALENT = "EQUIVALENT"
    ACCESSORY = "ACCESSORY"


class ProviderEndpointStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    RETIRED = "RETIRED"
    BLOCKED = "BLOCKED"


class ShopStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


__all__ = [
    "AffiliateLinkObservationValidationStatus",
    "AttributeDefinitionDataType",
    "AttributeDefinitionStatus",
    "AvailabilityObservationAvailability",
    "AvailabilityObservationValidationStatus",
    "CanonicalProductLifecycleStatus",
    "CategoryGenreMappingMappingRole",
    "GroupingDecisionDecisionType",
    "IngestionRequestStatus",
    "OfferStatus",
    "OfferCurrentProjectionCurrentAvailability",
    "OfferCurrentProjectionFreshnessStatus",
    "PriceObservationShippingCondition",
    "PriceObservationValidationStatus",
    "ProductCandidateListingStatus",
    "ProductRelationRelationType",
    "ProviderEndpointStatus",
    "ShopStatus",
]

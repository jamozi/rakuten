"""Closed physical enums for the ST-0308 EVIDENCE persistence slice."""

from enum import Enum


class ClaimClaimType(str, Enum):
    FACTUAL = "FACTUAL"
    COMPARATIVE = "COMPARATIVE"
    RECOMMENDATION = "RECOMMENDATION"
    DISCLOSURE = "DISCLOSURE"
    EXPERIENCE = "EXPERIENCE"
    OPINION = "OPINION"


class ClaimCriticality(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ClaimEvidenceLinkSupportType(str, Enum):
    SUPPORTS = "SUPPORTS"
    QUALIFIES = "QUALIFIES"
    CONTRADICTS = "CONTRADICTS"


class ClaimSupportStatus(str, Enum):
    PENDING = "PENDING"
    SUPPORTED = "SUPPORTED"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"
    CONFLICT = "CONFLICT"
    NOT_REQUIRED = "NOT_REQUIRED"


class FactDerivationDerivationRole(str, Enum):
    INPUT = "INPUT"
    BASELINE = "BASELINE"
    QUALIFIER = "QUALIFIER"
    EXCLUSION = "EXCLUSION"


class FactFactKind(str, Enum):
    ASSERTED = "ASSERTED"
    DERIVED = "DERIVED"
    MANUAL_VERIFIED = "MANUAL_VERIFIED"


class FactSubjectType(str, Enum):
    SITE = "SITE"
    CATEGORY = "CATEGORY"
    PRODUCT = "PRODUCT"
    OFFER = "OFFER"
    SHOP = "SHOP"
    ARTICLE = "ARTICLE"
    KEYWORD = "KEYWORD"
    OTHER = "OTHER"


class FirstHandExperienceAssetRole(str, Enum):
    PHOTO = "PHOTO"
    VIDEO = "VIDEO"
    MEASUREMENT = "MEASUREMENT"
    LOG = "LOG"
    PROCEDURE = "PROCEDURE"
    OTHER = "OTHER"


class FirstHandExperienceStatus(str, Enum):
    DRAFT = "DRAFT"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class SourceAuthorityLevel(str, Enum):
    PRIMARY = "PRIMARY"
    OFFICIAL = "OFFICIAL"
    SECONDARY = "SECONDARY"
    INTERNAL_DERIVED = "INTERNAL_DERIVED"
    UNVERIFIED = "UNVERIFIED"


class SourcePacketFactUsageRole(str, Enum):
    REQUIRED = "REQUIRED"
    SUPPORTING = "SUPPORTING"
    QUALIFIER = "QUALIFIER"
    EXCLUSION = "EXCLUSION"
    CONTRADICTING = "CONTRADICTING"


class SourcePacketPacketType(str, Enum):
    ARTICLE_DRAFT = "ARTICLE_DRAFT"
    ARTICLE_UPDATE = "ARTICLE_UPDATE"
    COMPARISON = "COMPARISON"
    QUALITY_REVIEW = "QUALITY_REVIEW"


class SourcePacketProductProductRole(str, Enum):
    CANDIDATE = "CANDIDATE"
    RECOMMENDED = "RECOMMENDED"
    COMPARED = "COMPARED"
    EXCLUDED = "EXCLUDED"
    REFERENCE = "REFERENCE"


class SourcePacketStatus(str, Enum):
    BUILDING = "BUILDING"
    READY = "READY"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    INVALID = "INVALID"
    SUPERSEDED = "SUPERSEDED"


class SourcePacketVersionStatus(str, Enum):
    BUILDING = "BUILDING"
    READY = "READY"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    INVALID = "INVALID"


class SourceSnapshotValidationStatus(str, Enum):
    VALID = "VALID"
    SUSPECT = "SUSPECT"
    INVALID = "INVALID"
    QUARANTINED = "QUARANTINED"


class SourceSourceType(str, Enum):
    PROVIDER_API = "PROVIDER_API"
    MANUFACTURER = "MANUFACTURER"
    OFFICIAL_DOCUMENT = "OFFICIAL_DOCUMENT"
    MANUAL_VERIFIED = "MANUAL_VERIFIED"
    INTERNAL_CALCULATION = "INTERNAL_CALCULATION"
    ANALYTICS = "ANALYTICS"
    OTHER = "OTHER"


class SourceStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    BLOCKED = "BLOCKED"
    RETIRED = "RETIRED"


__all__ = [
    "ClaimClaimType",
    "ClaimCriticality",
    "ClaimEvidenceLinkSupportType",
    "ClaimSupportStatus",
    "FactDerivationDerivationRole",
    "FactFactKind",
    "FactSubjectType",
    "FirstHandExperienceAssetRole",
    "FirstHandExperienceStatus",
    "SourceAuthorityLevel",
    "SourcePacketFactUsageRole",
    "SourcePacketPacketType",
    "SourcePacketProductProductRole",
    "SourcePacketStatus",
    "SourcePacketVersionStatus",
    "SourceSnapshotValidationStatus",
    "SourceSourceType",
    "SourceStatus",
]

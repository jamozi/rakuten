"""Closed physical enums for the ST-0308 EDITORIAL persistence slice."""

from enum import Enum


class ArticleArticleType(str, Enum):
    SELECTION_GUIDE = "SELECTION_GUIDE"
    USE_CASE_RECOMMENDATION = "USE_CASE_RECOMMENDATION"
    PRODUCT_COMPARISON = "PRODUCT_COMPARISON"
    MODEL_DIFFERENCE = "MODEL_DIFFERENCE"
    CONDITION_FILTER = "CONDITION_FILTER"


class ArticleBlockBlockType(str, Enum):
    INTRO = "INTRO"
    HEADING = "HEADING"
    PARAGRAPH = "PARAGRAPH"
    SELECTION_CRITERIA = "SELECTION_CRITERIA"
    COMPARISON_TABLE = "COMPARISON_TABLE"
    PRODUCT_CARD = "PRODUCT_CARD"
    RECOMMENDATION = "RECOMMENDATION"
    FIT_NONFIT = "FIT_NONFIT"
    FAQ = "FAQ"
    DISCLOSURE = "DISCLOSURE"
    SUMMARY = "SUMMARY"
    CALLOUT = "CALLOUT"
    INTERNAL_LINKS = "INTERNAL_LINKS"


class ArticleBlockProductPlacementRole(str, Enum):
    PRIMARY = "PRIMARY"
    ALTERNATIVE = "ALTERNATIVE"
    COMPARED = "COMPARED"
    MENTIONED = "MENTIONED"
    EXCLUDED = "EXCLUDED"


class ArticleLinkLinkType(str, Enum):
    INTERNAL = "INTERNAL"
    RELATED = "RELATED"
    CANONICAL_REFERENCE = "CANONICAL_REFERENCE"


class ArticleLinkStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    REMOVED = "REMOVED"


class ArticlePlanArticleType(str, Enum):
    SELECTION_GUIDE = "SELECTION_GUIDE"
    USE_CASE_RECOMMENDATION = "USE_CASE_RECOMMENDATION"
    PRODUCT_COMPARISON = "PRODUCT_COMPARISON"
    MODEL_DIFFERENCE = "MODEL_DIFFERENCE"
    CONDITION_FILTER = "CONDITION_FILTER"


class ArticlePlanStatus(str, Enum):
    IDEA = "IDEA"
    PLANNED = "PLANNED"
    SOURCES_PENDING = "SOURCES_PENDING"
    PACKET_READY = "PACKET_READY"
    GENERATING = "GENERATING"
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"
    ARCHIVED = "ARCHIVED"


class ArticleSlugStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REDIRECTED = "REDIRECTED"
    RETIRED = "RETIRED"


class ArticleStatus(str, Enum):
    IDEA = "IDEA"
    PLANNED = "PLANNED"
    SOURCES_PENDING = "SOURCES_PENDING"
    PACKET_READY = "PACKET_READY"
    GENERATING = "GENERATING"
    DRAFT = "DRAFT"
    AUTO_REVIEW = "AUTO_REVIEW"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    APPROVED = "APPROVED"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    UPDATE_PENDING = "UPDATE_PENDING"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"


class ArticleTemplateVersionStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    RETIRED = "RETIRED"


class ArticleTypeVersionStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    RETIRED = "RETIRED"


class ArticleVersionCreatedByActorType(str, Enum):
    USER = "USER"
    SERVICE = "SERVICE"
    SYSTEM = "SYSTEM"


class ArticleVersionStatus(str, Enum):
    DRAFT = "DRAFT"
    AUTO_REVIEW = "AUTO_REVIEW"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class ComparisonAxisDataType(str, Enum):
    TEXT = "TEXT"
    NUMERIC = "NUMERIC"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    CODE = "CODE"


class ComparisonValueValidationStatus(str, Enum):
    VALID = "VALID"
    MISSING = "MISSING"
    CONFLICT = "CONFLICT"
    UNSUPPORTED = "UNSUPPORTED"


class ContentSchemaVersionStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    RETIRED = "RETIRED"


class EditorialMethodologyVersionStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    RETIRED = "RETIRED"


class MediaAssetAssetClass(str, Enum):
    IMAGE = "IMAGE"
    CHART = "CHART"
    VIDEO = "VIDEO"
    DIAGRAM = "DIAGRAM"
    OTHER = "OTHER"


class MediaAssetLicenseStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    RESTRICTED = "RESTRICTED"
    REJECTED = "REJECTED"


class MediaAssetStatus(str, Enum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    RETIRED = "RETIRED"


class RecommendationRationaleRationaleType(str, Enum):
    FIT = "FIT"
    NON_FIT = "NON_FIT"
    TRADE_OFF = "TRADE_OFF"
    QUALIFIER = "QUALIFIER"
    EVIDENCE = "EVIDENCE"


class RecommendationStatus(str, Enum):
    RECOMMENDED = "RECOMMENDED"
    ALTERNATIVE = "ALTERNATIVE"
    NOT_RECOMMENDED = "NOT_RECOMMENDED"
    EXCLUDED = "EXCLUDED"


class ReviewCommentStatus(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    WONT_FIX = "WONT_FIX"


class SeoMetadataVersionStatus(str, Enum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class StructuredDataManifestValidationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


__all__ = [
    "ArticleArticleType",
    "ArticleBlockBlockType",
    "ArticleBlockProductPlacementRole",
    "ArticleLinkLinkType",
    "ArticleLinkStatus",
    "ArticlePlanArticleType",
    "ArticlePlanStatus",
    "ArticleSlugStatus",
    "ArticleStatus",
    "ArticleTemplateVersionStatus",
    "ArticleTypeVersionStatus",
    "ArticleVersionCreatedByActorType",
    "ArticleVersionStatus",
    "ComparisonAxisDataType",
    "ComparisonValueValidationStatus",
    "ContentSchemaVersionStatus",
    "EditorialMethodologyVersionStatus",
    "MediaAssetAssetClass",
    "MediaAssetLicenseStatus",
    "MediaAssetStatus",
    "RecommendationRationaleRationaleType",
    "RecommendationStatus",
    "ReviewCommentStatus",
    "SeoMetadataVersionStatus",
    "StructuredDataManifestValidationStatus",
]

"""Nominal EDITORIAL persistence identities selected by the ST-0308 mapper matrix."""

from raos.domain.shared.identity import EntityId


class ArticleBlockId(EntityId):
    __slots__ = ()


class ArticleId(EntityId):
    __slots__ = ()


class ArticleLinkId(EntityId):
    __slots__ = ()


class ArticlePlanId(EntityId):
    __slots__ = ()


class ArticleSlugId(EntityId):
    __slots__ = ()


class ArticleTemplateVersionId(EntityId):
    __slots__ = ()


class ArticleTypeVersionId(EntityId):
    __slots__ = ()


class ArticleVersionId(EntityId):
    __slots__ = ()


class ComparisonAxisId(EntityId):
    __slots__ = ()


class ComparisonValueId(EntityId):
    __slots__ = ()


class ContentSchemaVersionId(EntityId):
    __slots__ = ()


class EditorialMethodologyVersionId(EntityId):
    __slots__ = ()


class MediaAssetId(EntityId):
    __slots__ = ()


class RecommendationId(EntityId):
    __slots__ = ()


class RecommendationRationaleId(EntityId):
    __slots__ = ()


class RecommendationSetId(EntityId):
    __slots__ = ()


class ReviewCommentId(EntityId):
    __slots__ = ()


class SeoMetadataVersionId(EntityId):
    __slots__ = ()


class StructuredDataManifestId(EntityId):
    __slots__ = ()


class ThreadId(EntityId):
    __slots__ = ()


__all__ = [
    "ArticleBlockId",
    "ArticleId",
    "ArticleLinkId",
    "ArticlePlanId",
    "ArticleSlugId",
    "ArticleTemplateVersionId",
    "ArticleTypeVersionId",
    "ArticleVersionId",
    "ComparisonAxisId",
    "ComparisonValueId",
    "ContentSchemaVersionId",
    "EditorialMethodologyVersionId",
    "MediaAssetId",
    "RecommendationId",
    "RecommendationRationaleId",
    "RecommendationSetId",
    "ReviewCommentId",
    "SeoMetadataVersionId",
    "StructuredDataManifestId",
    "ThreadId",
]

"""Exact aggregate-specific EDITORIAL Repository Protocols for ST-0308."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.editorial.aggregates import (
    Article,
    ArticleDisclosureContext,
    ArticleLinkState,
    ArticleMethodologyBinding,
    ArticlePlan,
    ArticleSlug,
    ArticleTemplateVersion,
    ArticleTypeVersion,
    ArticleVersion,
    ContentSchemaVersion,
    EditorialMethodologyVersion,
    MediaAsset,
    ReviewComment,
    SeoMetadataVersion,
    StructuredDataManifest,
)
from raos.domain.editorial.enums import (
    ArticleSlugStatus,
    ArticleTemplateVersionStatus,
    ArticleTypeVersionStatus,
    ContentSchemaVersionStatus,
    EditorialMethodologyVersionStatus,
    MediaAssetStatus,
    ReviewCommentStatus,
    SeoMetadataVersionStatus,
)
from raos.domain.editorial.ids import (
    ArticleId,
    ArticlePlanId,
    ArticleSlugId,
    ArticleTemplateVersionId,
    ArticleTypeVersionId,
    ArticleVersionId,
    ContentSchemaVersionId,
    EditorialMethodologyVersionId,
    MediaAssetId,
    ReviewCommentId,
    SeoMetadataVersionId,
)
from raos.domain.shared.persistence import (
    AggregateVersion,
    PersistedVersion,
)


@runtime_checkable
class ArticlePlanRepository(Protocol):
    def get(self, plan_id: ArticlePlanId) -> ArticlePlan | None: ...

    def add(self, plan: ArticlePlan) -> PersistedVersion: ...

    def save(
        self,
        plan: ArticlePlan,
        expected_version: AggregateVersion,
    ) -> PersistedVersion: ...


@runtime_checkable
class ArticleRepository(Protocol):
    def get(self, article_id: ArticleId) -> Article | None: ...

    def add(self, article: Article) -> PersistedVersion: ...

    def save(
        self,
        article: Article,
        expected_version: AggregateVersion,
    ) -> PersistedVersion: ...

    def get_version(self, version_id: ArticleVersionId) -> ArticleVersion | None: ...

    def add_version(self, version: ArticleVersion) -> PersistedVersion: ...

    def save_version(
        self,
        version: ArticleVersion,
        expected_version: AggregateVersion,
    ) -> PersistedVersion: ...

    def assign_slug(self, slug: ArticleSlug) -> None: ...

    def transition_slug(
        self,
        slug_id: ArticleSlugId,
        transition: ArticleSlug,
        expected_status: ArticleSlugStatus,
    ) -> ArticleSlug: ...

    def add_link(self, link: ArticleLinkState) -> PersistedVersion: ...

    def save_link(
        self,
        link: ArticleLinkState,
        expected_version: AggregateVersion,
    ) -> PersistedVersion: ...


@runtime_checkable
class ReviewCommentRepository(Protocol):
    def get(self, comment_id: ReviewCommentId) -> ReviewComment | None: ...

    def append(self, comment: ReviewComment) -> None: ...

    def close(
        self,
        comment_id: ReviewCommentId,
        resolution: ReviewComment,
        expected_status: ReviewCommentStatus,
    ) -> ReviewComment: ...


@runtime_checkable
class EditorialContractRepository(Protocol):
    def get_disclosure_context(
        self, article_version_id: ArticleVersionId
    ) -> ArticleDisclosureContext | None: ...

    def add_disclosure_context(
        self,
        context: ArticleDisclosureContext,
        expected_version: AggregateVersion,
    ) -> PersistedVersion: ...

    def record_disclosure_review(
        self,
        article_version_id: ArticleVersionId,
        review: ArticleDisclosureContext,
        expected_version: AggregateVersion,
    ) -> ArticleDisclosureContext: ...

    def append_methodology_binding(
        self,
        binding: ArticleMethodologyBinding,
        expected_version: AggregateVersion,
    ) -> PersistedVersion: ...

    def get_current_article_type(self, code: str) -> ArticleTypeVersion | None: ...

    def append_article_type_version(
        self,
        version: ArticleTypeVersion,
        expected_latest_version: int | None,
    ) -> PersistedVersion: ...

    def transition_article_type_version(
        self,
        id: ArticleTypeVersionId,
        transition: ArticleTypeVersion,
        expected_status: ArticleTypeVersionStatus,
    ) -> ArticleTypeVersion: ...

    def get_current_content_schema(self, code: str) -> ContentSchemaVersion | None: ...

    def append_content_schema_version(
        self,
        version: ContentSchemaVersion,
        expected_latest_version: int | None,
    ) -> PersistedVersion: ...

    def transition_content_schema_version(
        self,
        id: ContentSchemaVersionId,
        transition: ContentSchemaVersion,
        expected_status: ContentSchemaVersionStatus,
    ) -> ContentSchemaVersion: ...

    def get_current_template(
        self, article_type_id: ArticleTypeVersionId
    ) -> ArticleTemplateVersion | None: ...

    def append_template_version(
        self,
        version: ArticleTemplateVersion,
        expected_latest_version: int | None,
    ) -> PersistedVersion: ...

    def transition_template_version(
        self,
        id: ArticleTemplateVersionId,
        transition: ArticleTemplateVersion,
        expected_status: ArticleTemplateVersionStatus,
    ) -> ArticleTemplateVersion: ...

    def get_current_methodology(
        self, code: str
    ) -> EditorialMethodologyVersion | None: ...

    def append_methodology_version(
        self,
        version: EditorialMethodologyVersion,
        expected_latest_version: int | None,
    ) -> PersistedVersion: ...

    def transition_methodology_version(
        self,
        id: EditorialMethodologyVersionId,
        transition: EditorialMethodologyVersion,
        expected_status: EditorialMethodologyVersionStatus,
    ) -> EditorialMethodologyVersion: ...

    def append_seo_metadata_version(
        self,
        metadata: SeoMetadataVersion,
        expected_latest_version: int | None,
    ) -> PersistedVersion: ...

    def transition_seo_metadata_version(
        self,
        id: SeoMetadataVersionId,
        transition: SeoMetadataVersion,
        expected_status: SeoMetadataVersionStatus,
    ) -> SeoMetadataVersion: ...

    def append_structured_data_manifest(
        self,
        manifest: StructuredDataManifest,
        expected_version: AggregateVersion,
    ) -> PersistedVersion: ...


@runtime_checkable
class MediaAssetRepository(Protocol):
    def get(self, asset_id: MediaAssetId) -> MediaAsset | None: ...

    def add(self, asset: MediaAsset) -> None: ...

    def transition(
        self,
        asset_id: MediaAssetId,
        transition: MediaAsset,
        expected_status: MediaAssetStatus,
    ) -> MediaAsset: ...


__all__ = [
    "ArticlePlanRepository",
    "ArticleRepository",
    "EditorialContractRepository",
    "MediaAssetRepository",
    "ReviewCommentRepository",
]

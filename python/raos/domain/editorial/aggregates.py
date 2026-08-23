"""Explicit EDITORIAL relation states and aggregate compositions for ST-0308."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
import re
from typing import ClassVar, NoReturn
from uuid import UUID

from raos.domain.ai.ids import (
    AiJobId,
)
from raos.domain.catalog.ids import (
    CanonicalProductId,
    OfferId,
)
from raos.domain.editorial.enums import (
    ArticleArticleType,
    ArticleBlockBlockType,
    ArticleBlockProductPlacementRole,
    ArticleLinkLinkType,
    ArticleLinkStatus,
    ArticlePlanArticleType,
    ArticlePlanStatus,
    ArticleSlugStatus,
    ArticleStatus,
    ArticleTemplateVersionStatus,
    ArticleTypeVersionStatus,
    ArticleVersionCreatedByActorType,
    ArticleVersionStatus,
    ComparisonAxisDataType,
    ComparisonValueValidationStatus,
    ContentSchemaVersionStatus,
    EditorialMethodologyVersionStatus,
    MediaAssetAssetClass,
    MediaAssetLicenseStatus,
    MediaAssetStatus,
    RecommendationRationaleRationaleType,
    RecommendationStatus,
    ReviewCommentStatus,
    SeoMetadataVersionStatus,
    StructuredDataManifestValidationStatus,
)
from raos.domain.editorial.ids import (
    ArticleBlockId,
    ArticleId,
    ArticleLinkId,
    ArticlePlanId,
    ArticleSlugId,
    ArticleTemplateVersionId,
    ArticleTypeVersionId,
    ArticleVersionId,
    ComparisonAxisId,
    ComparisonValueId,
    ContentSchemaVersionId,
    EditorialMethodologyVersionId,
    MediaAssetId,
    RecommendationId,
    RecommendationRationaleId,
    RecommendationSetId,
    ReviewCommentId,
    SeoMetadataVersionId,
    StructuredDataManifestId,
    ThreadId,
)
from raos.domain.editorial.values import (
    ArticleBlockContentJson,
    ArticlePlanBriefJson,
    ArticleTemplateVersionTemplateJson,
    ArticleTypeVersionContractJson,
    EditorialMethodologyVersionDefinitionJson,
    SeoMetadataVersionMetadataJson,
)
from raos.domain.evidence.ids import (
    ClaimId,
    FactId,
    SourceId,
    SourcePacketVersionId,
)
from raos.domain.iam.ids import (
    PrincipalId,
)
from raos.domain.ops.ids import (
    ObjectArtifactId,
)
from raos.domain.portfolio.ids import (
    CategoryId,
    IntentClusterId,
    KeywordId,
    OpportunityAssessmentId,
    SiteId,
)
from raos.domain.shared.identity import (
    ActorId,
)
from raos.domain.shared.persistence import (
    AggregateVersion,
    AwareUtcDateTime,
    Sha256Digest,
)
from raos.domain.shared.events import DomainEvent
from raos.domain.shared.identity import EntityId
from raos.domain.shared.persistence import PendingEventBuffer


_MAX_BIGINT = (1 << 63) - 1
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_GIT = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z", re.ASCII)


def _invalid() -> NoReturn:
    raise ValueError("INVALID_EDITORIAL_PERSISTENCE_VALUE") from None


def _order_value(value: object) -> object:
    if isinstance(value, EntityId):
        return value.value.int
    if isinstance(value, Enum):
        return value.value
    if type(value) is AwareUtcDateTime:
        return value.value
    return value


@dataclass(frozen=True, slots=True, repr=False)
class ArticleState:
    """Exact scalar state for relation editorial.article."""

    RELATION: ClassVar[str] = "editorial.article"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_editorial_article_archive",
        "ck_editorial_article_status",
        "ck_editorial_article_type",
        "ck_editorial_article_version",
    )
    id: ArticleId
    display_id: str
    site_id: SiteId
    article_plan_id: ArticlePlanId
    article_type: ArticleArticleType
    status: ArticleStatus
    current_version_id: ArticleVersionId | None
    published_version_id: ArticleVersionId | None
    archived_at: AwareUtcDateTime | None
    archive_reason: str | None
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    lock_version: AggregateVersion

    def __post_init__(self) -> None:
        if type(self.id) is not ArticleId:
            _invalid()
        if type(self.display_id) is not str:
            _invalid()
        if type(self.site_id) is not SiteId:
            _invalid()
        if type(self.article_plan_id) is not ArticlePlanId:
            _invalid()
        if type(self.article_type) is not ArticleArticleType:
            _invalid()
        if type(self.status) is not ArticleStatus:
            _invalid()
        if self.current_version_id is not None and (
            type(self.current_version_id) is not ArticleVersionId
        ):
            _invalid()
        if self.published_version_id is not None and (
            type(self.published_version_id) is not ArticleVersionId
        ):
            _invalid()
        if self.archived_at is not None and (
            type(self.archived_at) is not AwareUtcDateTime
        ):
            _invalid()
        if self.archive_reason is not None and (type(self.archive_reason) is not str):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()
        if self.lock_version.value < 0:
            _invalid()

    def __repr__(self) -> str:
        return "ArticleState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ArticleBlock:
    """Exact scalar state for relation editorial.article_block."""

    RELATION: ClassVar[str] = "editorial.article_block"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_editorial_block_content",
        "ck_editorial_block_hash",
        "ck_editorial_block_heading",
        "ck_editorial_block_position",
        "ck_editorial_block_type",
    )
    id: ArticleBlockId
    article_version_id: ArticleVersionId
    block_key: str
    block_type: ArticleBlockBlockType
    position: int
    heading_level: int | None
    content: ArticleBlockContentJson
    plain_text: str
    content_sha256: Sha256Digest
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not ArticleBlockId:
            _invalid()
        if type(self.article_version_id) is not ArticleVersionId:
            _invalid()
        if type(self.block_key) is not str:
            _invalid()
        if type(self.block_type) is not ArticleBlockBlockType:
            _invalid()
        if (
            type(self.position) is not int
            or not -_MAX_BIGINT <= self.position <= _MAX_BIGINT
        ):
            _invalid()
        if self.heading_level is not None and (
            type(self.heading_level) is not int
            or not -_MAX_BIGINT <= self.heading_level <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.content) is not ArticleBlockContentJson:
            _invalid()
        if type(self.plain_text) is not str:
            _invalid()
        if type(self.content_sha256) is not Sha256Digest:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if self.position < 0:
            _invalid()

    def __repr__(self) -> str:
        return "ArticleBlock(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ArticleBlockProduct:
    """Exact scalar state for relation editorial.article_block_product."""

    RELATION: ClassVar[str] = "editorial.article_block_product"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_editorial_block_product_position",
        "ck_editorial_block_product_role",
    )
    article_block_id: ArticleBlockId
    product_id: CanonicalProductId
    offer_id: OfferId | None
    placement_role: ArticleBlockProductPlacementRole
    position: int
    placement_id: str
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.article_block_id) is not ArticleBlockId:
            _invalid()
        if type(self.product_id) is not CanonicalProductId:
            _invalid()
        if self.offer_id is not None and (type(self.offer_id) is not OfferId):
            _invalid()
        if type(self.placement_role) is not ArticleBlockProductPlacementRole:
            _invalid()
        if (
            type(self.position) is not int
            or not -_MAX_BIGINT <= self.position <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.placement_id) is not str:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if self.position < 0:
            _invalid()

    def __repr__(self) -> str:
        return "ArticleBlockProduct(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ArticleDisclosureContext:
    """Exact scalar state for relation editorial.article_disclosure_context."""

    RELATION: ClassVar[str] = "editorial.article_disclosure_context"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_editorial_article_disclosure_benefit",
        "ck_editorial_article_disclosure_no_orphan_benefit",
        "ck_editorial_article_disclosure_policy",
        "ck_editorial_article_disclosure_review_pair",
    )
    article_version_id: ArticleVersionId
    affiliate_relationship: bool
    material_benefit_relationship: bool
    benefit_types: tuple[str, ...]
    disclosure_policy_version: str
    additional_disclosure_text: str | None
    reviewed_by_principal_id: PrincipalId | None
    reviewed_at: AwareUtcDateTime | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.article_version_id) is not ArticleVersionId:
            _invalid()
        if type(self.affiliate_relationship) is not bool:
            _invalid()
        if type(self.material_benefit_relationship) is not bool:
            _invalid()
        if type(self.benefit_types) is not tuple or any(
            type(item) is not str for item in self.benefit_types
        ):
            _invalid()
        if type(self.disclosure_policy_version) is not str:
            _invalid()
        if self.additional_disclosure_text is not None and (
            type(self.additional_disclosure_text) is not str
        ):
            _invalid()
        if self.reviewed_by_principal_id is not None and (
            type(self.reviewed_by_principal_id) is not PrincipalId
        ):
            _invalid()
        if self.reviewed_at is not None and (
            type(self.reviewed_at) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if (self.reviewed_by_principal_id is None) != (self.reviewed_at is None):
            _invalid()

    def __repr__(self) -> str:
        return "ArticleDisclosureContext(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ArticleLinkState:
    """Exact scalar state for relation editorial.article_link."""

    RELATION: ClassVar[str] = "editorial.article_link"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_editorial_article_link_self",
        "ck_editorial_article_link_status",
        "ck_editorial_article_link_type",
        "ck_editorial_article_link_version",
    )
    id: ArticleLinkId
    from_article_id: ArticleId
    to_article_id: ArticleId
    link_type: ArticleLinkLinkType
    anchor_text: str | None
    source_block_key: str | None
    status: ArticleLinkStatus
    reason: str | None
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    lock_version: AggregateVersion

    def __post_init__(self) -> None:
        if type(self.id) is not ArticleLinkId:
            _invalid()
        if type(self.from_article_id) is not ArticleId:
            _invalid()
        if type(self.to_article_id) is not ArticleId:
            _invalid()
        if type(self.link_type) is not ArticleLinkLinkType:
            _invalid()
        if self.anchor_text is not None and (type(self.anchor_text) is not str):
            _invalid()
        if self.source_block_key is not None and (
            type(self.source_block_key) is not str
        ):
            _invalid()
        if type(self.status) is not ArticleLinkStatus:
            _invalid()
        if self.reason is not None and (type(self.reason) is not str):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()
        if self.from_article_id == self.to_article_id:
            _invalid()
        if self.lock_version.value < 0:
            _invalid()

    def __repr__(self) -> str:
        return "ArticleLinkState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ArticleMethodologyBinding:
    """Exact scalar state for relation editorial.article_methodology_binding."""

    RELATION: ClassVar[str] = "editorial.article_methodology_binding"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_editorial_article_methodology_candidate_sha",
    )
    article_version_id: ArticleVersionId
    methodology_version_id: EditorialMethodologyVersionId
    candidate_universe_artifact_id: ObjectArtifactId
    candidate_universe_sha256: Sha256Digest
    bound_at: AwareUtcDateTime
    bound_by_principal_id: PrincipalId

    def __post_init__(self) -> None:
        if type(self.article_version_id) is not ArticleVersionId:
            _invalid()
        if type(self.methodology_version_id) is not EditorialMethodologyVersionId:
            _invalid()
        if type(self.candidate_universe_artifact_id) is not ObjectArtifactId:
            _invalid()
        if type(self.candidate_universe_sha256) is not Sha256Digest:
            _invalid()
        if type(self.bound_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.bound_by_principal_id) is not PrincipalId:
            _invalid()

    def __repr__(self) -> str:
        return "ArticleMethodologyBinding(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ArticlePlanState:
    """Exact scalar state for relation editorial.article_plan."""

    RELATION: ClassVar[str] = "editorial.article_plan"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_editorial_plan_approval",
        "ck_editorial_plan_brief",
        "ck_editorial_plan_priority",
        "ck_editorial_plan_status",
        "ck_editorial_plan_type",
        "ck_editorial_plan_version",
    )
    id: ArticlePlanId
    display_id: str
    site_id: SiteId
    category_id: CategoryId
    intent_cluster_id: IntentClusterId
    primary_keyword_id: KeywordId
    article_type: ArticlePlanArticleType
    working_title: str
    objective: str
    status: ArticlePlanStatus
    priority: int
    opportunity_assessment_id: OpportunityAssessmentId | None
    created_by_principal_id: PrincipalId
    approved_by_principal_id: PrincipalId | None
    approved_at: AwareUtcDateTime | None
    brief: ArticlePlanBriefJson
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    lock_version: AggregateVersion

    def __post_init__(self) -> None:
        if type(self.id) is not ArticlePlanId:
            _invalid()
        if type(self.display_id) is not str:
            _invalid()
        if type(self.site_id) is not SiteId:
            _invalid()
        if type(self.category_id) is not CategoryId:
            _invalid()
        if type(self.intent_cluster_id) is not IntentClusterId:
            _invalid()
        if type(self.primary_keyword_id) is not KeywordId:
            _invalid()
        if type(self.article_type) is not ArticlePlanArticleType:
            _invalid()
        if type(self.working_title) is not str:
            _invalid()
        if type(self.objective) is not str:
            _invalid()
        if type(self.status) is not ArticlePlanStatus:
            _invalid()
        if (
            type(self.priority) is not int
            or not -_MAX_BIGINT <= self.priority <= _MAX_BIGINT
        ):
            _invalid()
        if self.opportunity_assessment_id is not None and (
            type(self.opportunity_assessment_id) is not OpportunityAssessmentId
        ):
            _invalid()
        if type(self.created_by_principal_id) is not PrincipalId:
            _invalid()
        if self.approved_by_principal_id is not None and (
            type(self.approved_by_principal_id) is not PrincipalId
        ):
            _invalid()
        if self.approved_at is not None and (
            type(self.approved_at) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.brief) is not ArticlePlanBriefJson:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()
        if self.priority < 0:
            _invalid()
        if self.lock_version.value < 0:
            _invalid()

    def __repr__(self) -> str:
        return "ArticlePlanState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ArticleSlugState:
    """Exact scalar state for relation editorial.article_slug."""

    RELATION: ClassVar[str] = "editorial.article_slug"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_editorial_slug_path",
        "ck_editorial_slug_status",
        "ck_editorial_slug_window",
    )
    id: ArticleSlugId
    site_id: SiteId
    article_id: ArticleId
    slug: str
    normalized_path: str
    status: ArticleSlugStatus
    valid_from: AwareUtcDateTime
    valid_to: AwareUtcDateTime | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not ArticleSlugId:
            _invalid()
        if type(self.site_id) is not SiteId:
            _invalid()
        if type(self.article_id) is not ArticleId:
            _invalid()
        if type(self.slug) is not str:
            _invalid()
        if type(self.normalized_path) is not str:
            _invalid()
        if type(self.status) is not ArticleSlugStatus:
            _invalid()
        if type(self.valid_from) is not AwareUtcDateTime:
            _invalid()
        if self.valid_to is not None and (type(self.valid_to) is not AwareUtcDateTime):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if self.valid_to is not None and (
            not self.valid_to.value > self.valid_from.value
        ):
            _invalid()

    def __repr__(self) -> str:
        return "ArticleSlugState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ArticleTemplateVersionState:
    """Exact scalar state for relation editorial.article_template_version."""

    RELATION: ClassVar[str] = "editorial.article_template_version"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_editorial_article_template_active_approval",
        "ck_editorial_article_template_approval_pair",
        "ck_editorial_article_template_semver",
        "ck_editorial_article_template_sha",
        "ck_editorial_article_template_shape",
        "ck_editorial_article_template_status",
    )
    id: ArticleTemplateVersionId
    article_type_version_id: ArticleTypeVersionId
    semantic_version: str
    template: ArticleTemplateVersionTemplateJson
    template_sha256: Sha256Digest
    status: ArticleTemplateVersionStatus
    approved_by_principal_id: PrincipalId | None
    approved_at: AwareUtcDateTime | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not ArticleTemplateVersionId:
            _invalid()
        if type(self.article_type_version_id) is not ArticleTypeVersionId:
            _invalid()
        if type(self.semantic_version) is not str:
            _invalid()
        if type(self.template) is not ArticleTemplateVersionTemplateJson:
            _invalid()
        if type(self.template_sha256) is not Sha256Digest:
            _invalid()
        if type(self.status) is not ArticleTemplateVersionStatus:
            _invalid()
        if self.approved_by_principal_id is not None and (
            type(self.approved_by_principal_id) is not PrincipalId
        ):
            _invalid()
        if self.approved_at is not None and (
            type(self.approved_at) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if (self.approved_by_principal_id is None) != (self.approved_at is None):
            _invalid()

    def __repr__(self) -> str:
        return "ArticleTemplateVersionState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ArticleTypeVersionState:
    """Exact scalar state for relation editorial.article_type_version."""

    RELATION: ClassVar[str] = "editorial.article_type_version"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_editorial_article_type_active_approval",
        "ck_editorial_article_type_approval_pair",
        "ck_editorial_article_type_code",
        "ck_editorial_article_type_contract",
        "ck_editorial_article_type_semver",
        "ck_editorial_article_type_sha",
        "ck_editorial_article_type_status",
    )
    id: ArticleTypeVersionId
    article_type_code: str
    semantic_version: str
    contract: ArticleTypeVersionContractJson
    contract_sha256: Sha256Digest
    status: ArticleTypeVersionStatus
    approved_by_principal_id: PrincipalId | None
    approved_at: AwareUtcDateTime | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not ArticleTypeVersionId:
            _invalid()
        if type(self.article_type_code) is not str:
            _invalid()
        if type(self.semantic_version) is not str:
            _invalid()
        if type(self.contract) is not ArticleTypeVersionContractJson:
            _invalid()
        if type(self.contract_sha256) is not Sha256Digest:
            _invalid()
        if type(self.status) is not ArticleTypeVersionStatus:
            _invalid()
        if self.approved_by_principal_id is not None and (
            type(self.approved_by_principal_id) is not PrincipalId
        ):
            _invalid()
        if self.approved_at is not None and (
            type(self.approved_at) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if (self.approved_by_principal_id is None) != (self.approved_at is None):
            _invalid()

    def __repr__(self) -> str:
        return "ArticleTypeVersionState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ArticleVersionState:
    """Exact scalar state for relation editorial.article_version."""

    RELATION: ClassVar[str] = "editorial.article_version"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_editorial_article_version_actor",
        "ck_editorial_article_version_hash",
        "ck_editorial_article_version_lock",
        "ck_editorial_article_version_num",
        "ck_editorial_article_version_review",
        "ck_editorial_article_version_status",
    )
    id: ArticleVersionId
    display_id: str
    article_id: ArticleId
    version_no: int
    content_schema_version: int
    title: str
    meta_title: str | None
    meta_description: str | None
    excerpt: str | None
    body_sha256: Sha256Digest
    status: ArticleVersionStatus
    source_packet_version_id: SourcePacketVersionId
    based_on_version_id: ArticleVersionId | None
    ai_job_id: AiJobId | None
    created_by_actor_type: ArticleVersionCreatedByActorType
    created_by_actor_id: ActorId | None
    submitted_at: AwareUtcDateTime | None
    reviewed_at: AwareUtcDateTime | None
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    lock_version: AggregateVersion
    content_schema_version_id: ContentSchemaVersionId
    article_type_version_id: ArticleTypeVersionId
    article_template_version_id: ArticleTemplateVersionId
    seo_metadata_version_id: SeoMetadataVersionId

    def __post_init__(self) -> None:
        if type(self.id) is not ArticleVersionId:
            _invalid()
        if type(self.display_id) is not str:
            _invalid()
        if type(self.article_id) is not ArticleId:
            _invalid()
        if (
            type(self.version_no) is not int
            or not -_MAX_BIGINT <= self.version_no <= _MAX_BIGINT
        ):
            _invalid()
        if (
            type(self.content_schema_version) is not int
            or not -_MAX_BIGINT <= self.content_schema_version <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.title) is not str:
            _invalid()
        if self.meta_title is not None and (type(self.meta_title) is not str):
            _invalid()
        if self.meta_description is not None and (
            type(self.meta_description) is not str
        ):
            _invalid()
        if self.excerpt is not None and (type(self.excerpt) is not str):
            _invalid()
        if type(self.body_sha256) is not Sha256Digest:
            _invalid()
        if type(self.status) is not ArticleVersionStatus:
            _invalid()
        if type(self.source_packet_version_id) is not SourcePacketVersionId:
            _invalid()
        if self.based_on_version_id is not None and (
            type(self.based_on_version_id) is not ArticleVersionId
        ):
            _invalid()
        if self.ai_job_id is not None and (type(self.ai_job_id) is not AiJobId):
            _invalid()
        if type(self.created_by_actor_type) is not ArticleVersionCreatedByActorType:
            _invalid()
        if self.created_by_actor_id is not None and (
            type(self.created_by_actor_id) is not ActorId
        ):
            _invalid()
        if self.submitted_at is not None and (
            type(self.submitted_at) is not AwareUtcDateTime
        ):
            _invalid()
        if self.reviewed_at is not None and (
            type(self.reviewed_at) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()
        if type(self.content_schema_version_id) is not ContentSchemaVersionId:
            _invalid()
        if type(self.article_type_version_id) is not ArticleTypeVersionId:
            _invalid()
        if type(self.article_template_version_id) is not ArticleTemplateVersionId:
            _invalid()
        if type(self.seo_metadata_version_id) is not SeoMetadataVersionId:
            _invalid()
        if self.lock_version.value < 0:
            _invalid()

    def __repr__(self) -> str:
        return "ArticleVersionState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ComparisonAxis:
    """Exact scalar state for relation editorial.comparison_axis."""

    RELATION: ClassVar[str] = "editorial.comparison_axis"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_editorial_axis_position",
        "ck_editorial_axis_type",
    )
    id: ComparisonAxisId
    article_version_id: ArticleVersionId
    axis_code: str
    name: str
    description: str
    data_type: ComparisonAxisDataType
    unit_code: str | None
    position: int
    is_required: bool
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not ComparisonAxisId:
            _invalid()
        if type(self.article_version_id) is not ArticleVersionId:
            _invalid()
        if type(self.axis_code) is not str:
            _invalid()
        if type(self.name) is not str:
            _invalid()
        if type(self.description) is not str:
            _invalid()
        if type(self.data_type) is not ComparisonAxisDataType:
            _invalid()
        if self.unit_code is not None and (type(self.unit_code) is not str):
            _invalid()
        if (
            type(self.position) is not int
            or not -_MAX_BIGINT <= self.position <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.is_required) is not bool:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if self.position < 0:
            _invalid()

    def __repr__(self) -> str:
        return "ComparisonAxis(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ComparisonValue:
    """Exact scalar state for relation editorial.comparison_value."""

    RELATION: ClassVar[str] = "editorial.comparison_value"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_editorial_comparison_evidence",
        "ck_editorial_comparison_one_value",
        "ck_editorial_comparison_status",
    )
    id: ComparisonValueId
    comparison_axis_id: ComparisonAxisId
    product_id: CanonicalProductId
    value_text: str | None
    value_numeric: Decimal | None
    value_boolean: bool | None
    value_date: date | None
    value_code: str | None
    display_value: str
    source_fact_id: FactId | None
    validation_status: ComparisonValueValidationStatus
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not ComparisonValueId:
            _invalid()
        if type(self.comparison_axis_id) is not ComparisonAxisId:
            _invalid()
        if type(self.product_id) is not CanonicalProductId:
            _invalid()
        if self.value_text is not None and (type(self.value_text) is not str):
            _invalid()
        if self.value_numeric is not None and (
            type(self.value_numeric) is not Decimal
            or not self.value_numeric.is_finite()
        ):
            _invalid()
        if self.value_boolean is not None and (type(self.value_boolean) is not bool):
            _invalid()
        if self.value_date is not None and (type(self.value_date) is not date):
            _invalid()
        if self.value_code is not None and (type(self.value_code) is not str):
            _invalid()
        if type(self.display_value) is not str:
            _invalid()
        if self.source_fact_id is not None and (
            type(self.source_fact_id) is not FactId
        ):
            _invalid()
        if type(self.validation_status) is not ComparisonValueValidationStatus:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if (
            sum(
                value is not None
                for value in (
                    self.value_text,
                    self.value_numeric,
                    self.value_boolean,
                    self.value_date,
                    self.value_code,
                )
            )
            != 1
        ):
            _invalid()

    def __repr__(self) -> str:
        return "ComparisonValue(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ContentSchemaVersionState:
    """Exact scalar state for relation editorial.content_schema_version."""

    RELATION: ClassVar[str] = "editorial.content_schema_version"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_editorial_content_schema_active_approval",
        "ck_editorial_content_schema_active_window",
        "ck_editorial_content_schema_approval_pair",
        "ck_editorial_content_schema_code",
        "ck_editorial_content_schema_semver",
        "ck_editorial_content_schema_sha",
        "ck_editorial_content_schema_status",
        "ck_editorial_content_schema_window",
    )
    id: ContentSchemaVersionId
    schema_code: str
    semantic_version: str
    artifact_id: ObjectArtifactId
    schema_sha256: Sha256Digest
    status: ContentSchemaVersionStatus
    effective_from: AwareUtcDateTime
    effective_to: AwareUtcDateTime | None
    approved_by_principal_id: PrincipalId | None
    approved_at: AwareUtcDateTime | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not ContentSchemaVersionId:
            _invalid()
        if type(self.schema_code) is not str:
            _invalid()
        if type(self.semantic_version) is not str:
            _invalid()
        if type(self.artifact_id) is not ObjectArtifactId:
            _invalid()
        if type(self.schema_sha256) is not Sha256Digest:
            _invalid()
        if type(self.status) is not ContentSchemaVersionStatus:
            _invalid()
        if type(self.effective_from) is not AwareUtcDateTime:
            _invalid()
        if self.effective_to is not None and (
            type(self.effective_to) is not AwareUtcDateTime
        ):
            _invalid()
        if self.approved_by_principal_id is not None and (
            type(self.approved_by_principal_id) is not PrincipalId
        ):
            _invalid()
        if self.approved_at is not None and (
            type(self.approved_at) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if (self.approved_by_principal_id is None) != (self.approved_at is None):
            _invalid()
        if self.effective_to is not None and (
            not self.effective_to.value > self.effective_from.value
        ):
            _invalid()

    def __repr__(self) -> str:
        return "ContentSchemaVersionState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class EditorialMethodologyVersionState:
    """Exact scalar state for relation editorial.editorial_methodology_version."""

    RELATION: ClassVar[str] = "editorial.editorial_methodology_version"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_editorial_methodology_active_approval",
        "ck_editorial_methodology_approval_pair",
        "ck_editorial_methodology_code",
        "ck_editorial_methodology_definition",
        "ck_editorial_methodology_no_finance",
        "ck_editorial_methodology_semver",
        "ck_editorial_methodology_sha",
        "ck_editorial_methodology_status",
    )
    id: EditorialMethodologyVersionId
    methodology_code: str
    semantic_version: str
    article_type_code: str
    article_type_version_id: ArticleTypeVersionId
    definition: EditorialMethodologyVersionDefinitionJson
    definition_sha256: Sha256Digest
    excludes_finance_inputs: bool
    status: EditorialMethodologyVersionStatus
    approved_by_principal_id: PrincipalId | None
    approved_at: AwareUtcDateTime | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not EditorialMethodologyVersionId:
            _invalid()
        if type(self.methodology_code) is not str:
            _invalid()
        if type(self.semantic_version) is not str:
            _invalid()
        if type(self.article_type_code) is not str:
            _invalid()
        if type(self.article_type_version_id) is not ArticleTypeVersionId:
            _invalid()
        if type(self.definition) is not EditorialMethodologyVersionDefinitionJson:
            _invalid()
        if type(self.definition_sha256) is not Sha256Digest:
            _invalid()
        if type(self.excludes_finance_inputs) is not bool:
            _invalid()
        if type(self.status) is not EditorialMethodologyVersionStatus:
            _invalid()
        if self.approved_by_principal_id is not None and (
            type(self.approved_by_principal_id) is not PrincipalId
        ):
            _invalid()
        if self.approved_at is not None and (
            type(self.approved_at) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if (self.approved_by_principal_id is None) != (self.approved_at is None):
            _invalid()
        if self.excludes_finance_inputs is not True:
            _invalid()

    def __repr__(self) -> str:
        return "EditorialMethodologyVersionState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class MediaAssetState:
    """Exact scalar state for relation editorial.media_asset."""

    RELATION: ClassVar[str] = "editorial.media_asset"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_editorial_media_asset_alt",
        "ck_editorial_media_asset_approval_pair",
        "ck_editorial_media_asset_approved_human",
        "ck_editorial_media_asset_class",
        "ck_editorial_media_asset_dimensions",
        "ck_editorial_media_asset_license",
        "ck_editorial_media_asset_modification",
        "ck_editorial_media_asset_sha",
        "ck_editorial_media_asset_status",
    )
    id: MediaAssetId
    display_id: str
    asset_class: MediaAssetAssetClass
    source_id: SourceId
    raw_artifact_id: ObjectArtifactId
    asset_sha256: Sha256Digest
    license_status: MediaAssetLicenseStatus
    modification_policy: str
    alt_text: str
    decorative: bool
    long_description_artifact_id: ObjectArtifactId | None
    width: int
    height: int
    captured_or_observed_at: AwareUtcDateTime
    status: MediaAssetStatus
    approved_by_principal_id: PrincipalId | None
    approved_at: AwareUtcDateTime | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not MediaAssetId:
            _invalid()
        if type(self.display_id) is not str:
            _invalid()
        if type(self.asset_class) is not MediaAssetAssetClass:
            _invalid()
        if type(self.source_id) is not SourceId:
            _invalid()
        if type(self.raw_artifact_id) is not ObjectArtifactId:
            _invalid()
        if type(self.asset_sha256) is not Sha256Digest:
            _invalid()
        if type(self.license_status) is not MediaAssetLicenseStatus:
            _invalid()
        if type(self.modification_policy) is not str:
            _invalid()
        if type(self.alt_text) is not str:
            _invalid()
        if type(self.decorative) is not bool:
            _invalid()
        if self.long_description_artifact_id is not None and (
            type(self.long_description_artifact_id) is not ObjectArtifactId
        ):
            _invalid()
        if type(self.width) is not int or not -_MAX_BIGINT <= self.width <= _MAX_BIGINT:
            _invalid()
        if (
            type(self.height) is not int
            or not -_MAX_BIGINT <= self.height <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.captured_or_observed_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.status) is not MediaAssetStatus:
            _invalid()
        if self.approved_by_principal_id is not None and (
            type(self.approved_by_principal_id) is not PrincipalId
        ):
            _invalid()
        if self.approved_at is not None and (
            type(self.approved_at) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if (self.approved_by_principal_id is None) != (self.approved_at is None):
            _invalid()
        if self.width <= 0:
            _invalid()
        if self.height <= 0:
            _invalid()

    def __repr__(self) -> str:
        return "MediaAssetState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class Recommendation:
    """Exact scalar state for relation editorial.recommendation."""

    RELATION: ClassVar[str] = "editorial.recommendation"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_editorial_rec_rank",
        "ck_editorial_rec_score",
        "ck_editorial_rec_status",
    )
    id: RecommendationId
    recommendation_set_id: RecommendationSetId
    product_id: CanonicalProductId
    rank_position: int
    suitability_score: Decimal
    status: RecommendationStatus
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not RecommendationId:
            _invalid()
        if type(self.recommendation_set_id) is not RecommendationSetId:
            _invalid()
        if type(self.product_id) is not CanonicalProductId:
            _invalid()
        if (
            type(self.rank_position) is not int
            or not -_MAX_BIGINT <= self.rank_position <= _MAX_BIGINT
        ):
            _invalid()
        if (
            type(self.suitability_score) is not Decimal
            or not self.suitability_score.is_finite()
        ):
            _invalid()
        if type(self.status) is not RecommendationStatus:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if self.suitability_score < 0:
            _invalid()

    def __repr__(self) -> str:
        return "Recommendation(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class RecommendationRationale:
    """Exact scalar state for relation editorial.recommendation_rationale."""

    RELATION: ClassVar[str] = "editorial.recommendation_rationale"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_editorial_rationale_position",
        "ck_editorial_rationale_source",
        "ck_editorial_rationale_type",
    )
    id: RecommendationRationaleId
    recommendation_id: RecommendationId
    rationale_type: RecommendationRationaleRationaleType
    rationale_text: str
    claim_id: ClaimId | None
    source_fact_id: FactId | None
    position: int
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not RecommendationRationaleId:
            _invalid()
        if type(self.recommendation_id) is not RecommendationId:
            _invalid()
        if type(self.rationale_type) is not RecommendationRationaleRationaleType:
            _invalid()
        if type(self.rationale_text) is not str:
            _invalid()
        if self.claim_id is not None and (type(self.claim_id) is not ClaimId):
            _invalid()
        if self.source_fact_id is not None and (
            type(self.source_fact_id) is not FactId
        ):
            _invalid()
        if (
            type(self.position) is not int
            or not -_MAX_BIGINT <= self.position <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if self.position < 0:
            _invalid()

    def __repr__(self) -> str:
        return "RecommendationRationale(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class RecommendationSet:
    """Exact scalar state for relation editorial.recommendation_set."""

    RELATION: ClassVar[str] = "editorial.recommendation_set"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = ("ck_editorial_rec_set_position",)
    id: RecommendationSetId
    article_version_id: ArticleVersionId
    set_code: str
    name: str
    target_segment: str
    methodology: str
    editorial_policy_version: str
    position: int
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not RecommendationSetId:
            _invalid()
        if type(self.article_version_id) is not ArticleVersionId:
            _invalid()
        if type(self.set_code) is not str:
            _invalid()
        if type(self.name) is not str:
            _invalid()
        if type(self.target_segment) is not str:
            _invalid()
        if type(self.methodology) is not str:
            _invalid()
        if type(self.editorial_policy_version) is not str:
            _invalid()
        if (
            type(self.position) is not int
            or not -_MAX_BIGINT <= self.position <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if self.position < 0:
            _invalid()

    def __repr__(self) -> str:
        return "RecommendationSet(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ReviewCommentState:
    """Exact scalar state for relation editorial.review_comment."""

    RELATION: ClassVar[str] = "editorial.review_comment"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_editorial_review_comment_resolve_pair",
        "ck_editorial_review_comment_status",
        "ck_editorial_review_comment_target",
    )
    id: ReviewCommentId
    article_version_id: ArticleVersionId
    article_block_id: ArticleBlockId | None
    claim_id: ClaimId | None
    thread_id: ThreadId
    parent_comment_id: ReviewCommentId | None
    author_principal_id: PrincipalId
    comment_text: str
    status: ReviewCommentStatus
    resolved_by_principal_id: PrincipalId | None
    resolved_at: AwareUtcDateTime | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not ReviewCommentId:
            _invalid()
        if type(self.article_version_id) is not ArticleVersionId:
            _invalid()
        if self.article_block_id is not None and (
            type(self.article_block_id) is not ArticleBlockId
        ):
            _invalid()
        if self.claim_id is not None and (type(self.claim_id) is not ClaimId):
            _invalid()
        if type(self.thread_id) is not ThreadId:
            _invalid()
        if self.parent_comment_id is not None and (
            type(self.parent_comment_id) is not ReviewCommentId
        ):
            _invalid()
        if type(self.author_principal_id) is not PrincipalId:
            _invalid()
        if type(self.comment_text) is not str:
            _invalid()
        if type(self.status) is not ReviewCommentStatus:
            _invalid()
        if self.resolved_by_principal_id is not None and (
            type(self.resolved_by_principal_id) is not PrincipalId
        ):
            _invalid()
        if self.resolved_at is not None and (
            type(self.resolved_at) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if (self.resolved_by_principal_id is None) != (self.resolved_at is None):
            _invalid()

    def __repr__(self) -> str:
        return "ReviewCommentState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class SeoMetadataVersionState:
    """Exact scalar state for relation editorial.seo_metadata_version."""

    RELATION: ClassVar[str] = "editorial.seo_metadata_version"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_editorial_seo_approval_pair",
        "ck_editorial_seo_approved_human",
        "ck_editorial_seo_metadata_sha",
        "ck_editorial_seo_metadata_shape",
        "ck_editorial_seo_semver",
        "ck_editorial_seo_status",
        "ck_editorial_seo_validation_time",
    )
    id: SeoMetadataVersionId
    article_version_id: ArticleVersionId
    semantic_version: str
    metadata: SeoMetadataVersionMetadataJson
    metadata_sha256: Sha256Digest
    status: SeoMetadataVersionStatus
    validated_at: AwareUtcDateTime | None
    approved_by_principal_id: PrincipalId | None
    approved_at: AwareUtcDateTime | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not SeoMetadataVersionId:
            _invalid()
        if type(self.article_version_id) is not ArticleVersionId:
            _invalid()
        if type(self.semantic_version) is not str:
            _invalid()
        if type(self.metadata) is not SeoMetadataVersionMetadataJson:
            _invalid()
        if type(self.metadata_sha256) is not Sha256Digest:
            _invalid()
        if type(self.status) is not SeoMetadataVersionStatus:
            _invalid()
        if self.validated_at is not None and (
            type(self.validated_at) is not AwareUtcDateTime
        ):
            _invalid()
        if self.approved_by_principal_id is not None and (
            type(self.approved_by_principal_id) is not PrincipalId
        ):
            _invalid()
        if self.approved_at is not None and (
            type(self.approved_at) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if (self.approved_by_principal_id is None) != (self.approved_at is None):
            _invalid()

    def __repr__(self) -> str:
        return "SeoMetadataVersionState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class StructuredDataManifest:
    """Exact scalar state for relation editorial.structured_data_manifest."""

    RELATION: ClassVar[str] = "editorial.structured_data_manifest"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_editorial_structured_data_generator",
        "ck_editorial_structured_data_jsonld_sha",
        "ck_editorial_structured_data_status",
        "ck_editorial_structured_data_types",
        "ck_editorial_structured_data_visible_sha",
    )
    id: StructuredDataManifestId
    article_version_id: ArticleVersionId
    seo_metadata_version_id: SeoMetadataVersionId
    generator_version: str
    visible_content_sha256: Sha256Digest
    jsonld_artifact_id: ObjectArtifactId
    jsonld_sha256: Sha256Digest
    enabled_types: tuple[str, ...]
    disabled_types: tuple[str, ...]
    validation_status: StructuredDataManifestValidationStatus
    validated_at: AwareUtcDateTime
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not StructuredDataManifestId:
            _invalid()
        if type(self.article_version_id) is not ArticleVersionId:
            _invalid()
        if type(self.seo_metadata_version_id) is not SeoMetadataVersionId:
            _invalid()
        if type(self.generator_version) is not str:
            _invalid()
        if type(self.visible_content_sha256) is not Sha256Digest:
            _invalid()
        if type(self.jsonld_artifact_id) is not ObjectArtifactId:
            _invalid()
        if type(self.jsonld_sha256) is not Sha256Digest:
            _invalid()
        if type(self.enabled_types) is not tuple or any(
            type(item) is not str for item in self.enabled_types
        ):
            _invalid()
        if type(self.disabled_types) is not tuple or any(
            type(item) is not str for item in self.disabled_types
        ):
            _invalid()
        if type(self.validation_status) is not StructuredDataManifestValidationStatus:
            _invalid()
        if type(self.validated_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "StructuredDataManifest(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class Article:
    state: ArticleState
    article_slug_rows: tuple[ArticleSlugState, ...] = ()
    article_version_rows: tuple[ArticleVersionState, ...] = ()
    article_block_rows: tuple[ArticleBlock, ...] = ()
    article_block_product_rows: tuple[ArticleBlockProduct, ...] = ()
    comparison_axis_rows: tuple[ComparisonAxis, ...] = ()
    comparison_value_rows: tuple[ComparisonValue, ...] = ()
    recommendation_set_rows: tuple[RecommendationSet, ...] = ()
    recommendation_rows: tuple[Recommendation, ...] = ()
    recommendation_rationale_rows: tuple[RecommendationRationale, ...] = ()
    article_link_rows: tuple[ArticleLinkState, ...] = ()
    _events: PendingEventBuffer[DomainEvent] = field(
        default_factory=PendingEventBuffer, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if type(self.state) is not ArticleState:
            _invalid()
        if type(self.article_slug_rows) is not tuple or any(
            type(item) is not ArticleSlugState for item in self.article_slug_rows
        ):
            _invalid()
        if self.article_slug_rows != tuple(
            sorted(self.article_slug_rows, key=lambda item: (_order_value(item.id),))
        ):
            _invalid()
        if type(self.article_version_rows) is not tuple or any(
            type(item) is not ArticleVersionState for item in self.article_version_rows
        ):
            _invalid()
        if self.article_version_rows != tuple(
            sorted(self.article_version_rows, key=lambda item: (_order_value(item.id),))
        ):
            _invalid()
        if type(self.article_block_rows) is not tuple or any(
            type(item) is not ArticleBlock for item in self.article_block_rows
        ):
            _invalid()
        if self.article_block_rows != tuple(
            sorted(self.article_block_rows, key=lambda item: (_order_value(item.id),))
        ):
            _invalid()
        if type(self.article_block_product_rows) is not tuple or any(
            type(item) is not ArticleBlockProduct
            for item in self.article_block_product_rows
        ):
            _invalid()
        if self.article_block_product_rows != tuple(
            sorted(
                self.article_block_product_rows,
                key=lambda item: (
                    _order_value(item.article_block_id),
                    _order_value(item.product_id),
                    _order_value(item.placement_role),
                ),
            )
        ):
            _invalid()
        if type(self.comparison_axis_rows) is not tuple or any(
            type(item) is not ComparisonAxis for item in self.comparison_axis_rows
        ):
            _invalid()
        if self.comparison_axis_rows != tuple(
            sorted(self.comparison_axis_rows, key=lambda item: (_order_value(item.id),))
        ):
            _invalid()
        if type(self.comparison_value_rows) is not tuple or any(
            type(item) is not ComparisonValue for item in self.comparison_value_rows
        ):
            _invalid()
        if self.comparison_value_rows != tuple(
            sorted(
                self.comparison_value_rows, key=lambda item: (_order_value(item.id),)
            )
        ):
            _invalid()
        if type(self.recommendation_set_rows) is not tuple or any(
            type(item) is not RecommendationSet for item in self.recommendation_set_rows
        ):
            _invalid()
        if self.recommendation_set_rows != tuple(
            sorted(
                self.recommendation_set_rows, key=lambda item: (_order_value(item.id),)
            )
        ):
            _invalid()
        if type(self.recommendation_rows) is not tuple or any(
            type(item) is not Recommendation for item in self.recommendation_rows
        ):
            _invalid()
        if self.recommendation_rows != tuple(
            sorted(self.recommendation_rows, key=lambda item: (_order_value(item.id),))
        ):
            _invalid()
        if type(self.recommendation_rationale_rows) is not tuple or any(
            type(item) is not RecommendationRationale
            for item in self.recommendation_rationale_rows
        ):
            _invalid()
        if self.recommendation_rationale_rows != tuple(
            sorted(
                self.recommendation_rationale_rows,
                key=lambda item: (_order_value(item.id),),
            )
        ):
            _invalid()
        if type(self.article_link_rows) is not tuple or any(
            type(item) is not ArticleLinkState for item in self.article_link_rows
        ):
            _invalid()
        if self.article_link_rows != tuple(
            sorted(self.article_link_rows, key=lambda item: (_order_value(item.id),))
        ):
            _invalid()
        if type(self._events) is not PendingEventBuffer:
            _invalid()

    def pending_events(self) -> tuple[DomainEvent, ...]:
        return self._events.pending_events()

    def acknowledge_events(self, event_ids: tuple[UUID, ...]) -> None:
        self._events.acknowledge_events(event_ids)

    def _record_event(self, event: DomainEvent) -> None:
        self._events.record(event)

    def _restore_acknowledged_events(self) -> None:
        self._events._restore_acknowledged()

    def _finish_acknowledged_events(self) -> None:
        self._events._finish_acknowledged()

    def __repr__(self) -> str:
        return "Article(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ArticlePlan:
    state: ArticlePlanState
    _events: PendingEventBuffer[DomainEvent] = field(
        default_factory=PendingEventBuffer, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if type(self.state) is not ArticlePlanState:
            _invalid()
        if type(self._events) is not PendingEventBuffer:
            _invalid()

    def pending_events(self) -> tuple[DomainEvent, ...]:
        return self._events.pending_events()

    def acknowledge_events(self, event_ids: tuple[UUID, ...]) -> None:
        self._events.acknowledge_events(event_ids)

    def _record_event(self, event: DomainEvent) -> None:
        self._events.record(event)

    def _restore_acknowledged_events(self) -> None:
        self._events._restore_acknowledged()

    def _finish_acknowledged_events(self) -> None:
        self._events._finish_acknowledged()

    def __repr__(self) -> str:
        return "ArticlePlan(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ArticleSlug:
    state: ArticleSlugState

    def __post_init__(self) -> None:
        if type(self.state) is not ArticleSlugState:
            _invalid()

    def __repr__(self) -> str:
        return "ArticleSlug(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ArticleTemplateVersion:
    state: ArticleTemplateVersionState
    article_version_rows: tuple[ArticleVersionState, ...] = ()

    def __post_init__(self) -> None:
        if type(self.state) is not ArticleTemplateVersionState:
            _invalid()
        if type(self.article_version_rows) is not tuple or any(
            type(item) is not ArticleVersionState for item in self.article_version_rows
        ):
            _invalid()
        if self.article_version_rows != tuple(
            sorted(self.article_version_rows, key=lambda item: (_order_value(item.id),))
        ):
            _invalid()

    def __repr__(self) -> str:
        return "ArticleTemplateVersion(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ArticleTypeVersion:
    state: ArticleTypeVersionState
    article_template_version_rows: tuple[ArticleTemplateVersionState, ...] = ()
    article_version_rows: tuple[ArticleVersionState, ...] = ()
    editorial_methodology_version_rows: tuple[
        EditorialMethodologyVersionState, ...
    ] = ()

    def __post_init__(self) -> None:
        if type(self.state) is not ArticleTypeVersionState:
            _invalid()
        if type(self.article_template_version_rows) is not tuple or any(
            type(item) is not ArticleTemplateVersionState
            for item in self.article_template_version_rows
        ):
            _invalid()
        if self.article_template_version_rows != tuple(
            sorted(
                self.article_template_version_rows,
                key=lambda item: (_order_value(item.id),),
            )
        ):
            _invalid()
        if type(self.article_version_rows) is not tuple or any(
            type(item) is not ArticleVersionState for item in self.article_version_rows
        ):
            _invalid()
        if self.article_version_rows != tuple(
            sorted(self.article_version_rows, key=lambda item: (_order_value(item.id),))
        ):
            _invalid()
        if type(self.editorial_methodology_version_rows) is not tuple or any(
            type(item) is not EditorialMethodologyVersionState
            for item in self.editorial_methodology_version_rows
        ):
            _invalid()
        if self.editorial_methodology_version_rows != tuple(
            sorted(
                self.editorial_methodology_version_rows,
                key=lambda item: (_order_value(item.id),),
            )
        ):
            _invalid()

    def __repr__(self) -> str:
        return "ArticleTypeVersion(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ArticleVersion:
    state: ArticleVersionState
    article_rows: tuple[ArticleState, ...] = ()
    article_block_rows: tuple[ArticleBlock, ...] = ()
    article_block_product_rows: tuple[ArticleBlockProduct, ...] = ()
    article_disclosure_context_rows: tuple[ArticleDisclosureContext, ...] = ()
    article_methodology_binding_rows: tuple[ArticleMethodologyBinding, ...] = ()
    comparison_axis_rows: tuple[ComparisonAxis, ...] = ()
    comparison_value_rows: tuple[ComparisonValue, ...] = ()
    recommendation_set_rows: tuple[RecommendationSet, ...] = ()
    recommendation_rows: tuple[Recommendation, ...] = ()
    recommendation_rationale_rows: tuple[RecommendationRationale, ...] = ()
    review_comment_rows: tuple[ReviewCommentState, ...] = ()
    seo_metadata_version_rows: tuple[SeoMetadataVersionState, ...] = ()
    structured_data_manifest_rows: tuple[StructuredDataManifest, ...] = ()
    _events: PendingEventBuffer[DomainEvent] = field(
        default_factory=PendingEventBuffer, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if type(self.state) is not ArticleVersionState:
            _invalid()
        if type(self.article_rows) is not tuple or any(
            type(item) is not ArticleState for item in self.article_rows
        ):
            _invalid()
        if self.article_rows != tuple(
            sorted(self.article_rows, key=lambda item: (_order_value(item.id),))
        ):
            _invalid()
        if type(self.article_block_rows) is not tuple or any(
            type(item) is not ArticleBlock for item in self.article_block_rows
        ):
            _invalid()
        if self.article_block_rows != tuple(
            sorted(self.article_block_rows, key=lambda item: (_order_value(item.id),))
        ):
            _invalid()
        if type(self.article_block_product_rows) is not tuple or any(
            type(item) is not ArticleBlockProduct
            for item in self.article_block_product_rows
        ):
            _invalid()
        if self.article_block_product_rows != tuple(
            sorted(
                self.article_block_product_rows,
                key=lambda item: (
                    _order_value(item.article_block_id),
                    _order_value(item.product_id),
                    _order_value(item.placement_role),
                ),
            )
        ):
            _invalid()
        if type(self.article_disclosure_context_rows) is not tuple or any(
            type(item) is not ArticleDisclosureContext
            for item in self.article_disclosure_context_rows
        ):
            _invalid()
        if self.article_disclosure_context_rows != tuple(
            sorted(
                self.article_disclosure_context_rows,
                key=lambda item: (_order_value(item.article_version_id),),
            )
        ):
            _invalid()
        if type(self.article_methodology_binding_rows) is not tuple or any(
            type(item) is not ArticleMethodologyBinding
            for item in self.article_methodology_binding_rows
        ):
            _invalid()
        if self.article_methodology_binding_rows != tuple(
            sorted(
                self.article_methodology_binding_rows,
                key=lambda item: (_order_value(item.article_version_id),),
            )
        ):
            _invalid()
        if type(self.comparison_axis_rows) is not tuple or any(
            type(item) is not ComparisonAxis for item in self.comparison_axis_rows
        ):
            _invalid()
        if self.comparison_axis_rows != tuple(
            sorted(self.comparison_axis_rows, key=lambda item: (_order_value(item.id),))
        ):
            _invalid()
        if type(self.comparison_value_rows) is not tuple or any(
            type(item) is not ComparisonValue for item in self.comparison_value_rows
        ):
            _invalid()
        if self.comparison_value_rows != tuple(
            sorted(
                self.comparison_value_rows,
                key=lambda item: (_order_value(item.id),),
            )
        ):
            _invalid()
        if type(self.recommendation_set_rows) is not tuple or any(
            type(item) is not RecommendationSet for item in self.recommendation_set_rows
        ):
            _invalid()
        if self.recommendation_set_rows != tuple(
            sorted(
                self.recommendation_set_rows, key=lambda item: (_order_value(item.id),)
            )
        ):
            _invalid()
        if type(self.recommendation_rows) is not tuple or any(
            type(item) is not Recommendation for item in self.recommendation_rows
        ):
            _invalid()
        if self.recommendation_rows != tuple(
            sorted(self.recommendation_rows, key=lambda item: (_order_value(item.id),))
        ):
            _invalid()
        if type(self.recommendation_rationale_rows) is not tuple or any(
            type(item) is not RecommendationRationale
            for item in self.recommendation_rationale_rows
        ):
            _invalid()
        if self.recommendation_rationale_rows != tuple(
            sorted(
                self.recommendation_rationale_rows,
                key=lambda item: (_order_value(item.id),),
            )
        ):
            _invalid()
        if type(self.review_comment_rows) is not tuple or any(
            type(item) is not ReviewCommentState for item in self.review_comment_rows
        ):
            _invalid()
        if self.review_comment_rows != tuple(
            sorted(self.review_comment_rows, key=lambda item: (_order_value(item.id),))
        ):
            _invalid()
        if type(self.seo_metadata_version_rows) is not tuple or any(
            type(item) is not SeoMetadataVersionState
            for item in self.seo_metadata_version_rows
        ):
            _invalid()
        if self.seo_metadata_version_rows != tuple(
            sorted(
                self.seo_metadata_version_rows,
                key=lambda item: (_order_value(item.id),),
            )
        ):
            _invalid()
        if type(self.structured_data_manifest_rows) is not tuple or any(
            type(item) is not StructuredDataManifest
            for item in self.structured_data_manifest_rows
        ):
            _invalid()
        if self.structured_data_manifest_rows != tuple(
            sorted(
                self.structured_data_manifest_rows,
                key=lambda item: (_order_value(item.id),),
            )
        ):
            _invalid()
        if type(self._events) is not PendingEventBuffer:
            _invalid()

    def pending_events(self) -> tuple[DomainEvent, ...]:
        return self._events.pending_events()

    def acknowledge_events(self, event_ids: tuple[UUID, ...]) -> None:
        self._events.acknowledge_events(event_ids)

    def _record_event(self, event: DomainEvent) -> None:
        self._events.record(event)

    def _restore_acknowledged_events(self) -> None:
        self._events._restore_acknowledged()

    def _finish_acknowledged_events(self) -> None:
        self._events._finish_acknowledged()

    def __repr__(self) -> str:
        return "ArticleVersion(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ContentSchemaVersion:
    state: ContentSchemaVersionState
    article_version_rows: tuple[ArticleVersionState, ...] = ()

    def __post_init__(self) -> None:
        if type(self.state) is not ContentSchemaVersionState:
            _invalid()
        if type(self.article_version_rows) is not tuple or any(
            type(item) is not ArticleVersionState for item in self.article_version_rows
        ):
            _invalid()
        if self.article_version_rows != tuple(
            sorted(self.article_version_rows, key=lambda item: (_order_value(item.id),))
        ):
            _invalid()

    def __repr__(self) -> str:
        return "ContentSchemaVersion(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class EditorialContract:
    article_disclosure_context_rows: tuple[ArticleDisclosureContext, ...] = ()
    article_methodology_binding_rows: tuple[ArticleMethodologyBinding, ...] = ()
    article_template_version_rows: tuple[ArticleTemplateVersionState, ...] = ()
    article_type_version_rows: tuple[ArticleTypeVersionState, ...] = ()
    content_schema_version_rows: tuple[ContentSchemaVersionState, ...] = ()
    editorial_methodology_version_rows: tuple[
        EditorialMethodologyVersionState, ...
    ] = ()
    seo_metadata_version_rows: tuple[SeoMetadataVersionState, ...] = ()
    structured_data_manifest_rows: tuple[StructuredDataManifest, ...] = ()

    def __post_init__(self) -> None:
        if type(self.article_disclosure_context_rows) is not tuple or any(
            type(item) is not ArticleDisclosureContext
            for item in self.article_disclosure_context_rows
        ):
            _invalid()
        if self.article_disclosure_context_rows != tuple(
            sorted(
                self.article_disclosure_context_rows,
                key=lambda item: (_order_value(item.article_version_id),),
            )
        ):
            _invalid()
        if type(self.article_methodology_binding_rows) is not tuple or any(
            type(item) is not ArticleMethodologyBinding
            for item in self.article_methodology_binding_rows
        ):
            _invalid()
        if self.article_methodology_binding_rows != tuple(
            sorted(
                self.article_methodology_binding_rows,
                key=lambda item: (_order_value(item.article_version_id),),
            )
        ):
            _invalid()
        if type(self.article_template_version_rows) is not tuple or any(
            type(item) is not ArticleTemplateVersionState
            for item in self.article_template_version_rows
        ):
            _invalid()
        if self.article_template_version_rows != tuple(
            sorted(
                self.article_template_version_rows,
                key=lambda item: (_order_value(item.id),),
            )
        ):
            _invalid()
        if type(self.article_type_version_rows) is not tuple or any(
            type(item) is not ArticleTypeVersionState
            for item in self.article_type_version_rows
        ):
            _invalid()
        if self.article_type_version_rows != tuple(
            sorted(
                self.article_type_version_rows,
                key=lambda item: (_order_value(item.id),),
            )
        ):
            _invalid()
        if type(self.content_schema_version_rows) is not tuple or any(
            type(item) is not ContentSchemaVersionState
            for item in self.content_schema_version_rows
        ):
            _invalid()
        if self.content_schema_version_rows != tuple(
            sorted(
                self.content_schema_version_rows,
                key=lambda item: (_order_value(item.id),),
            )
        ):
            _invalid()
        if type(self.editorial_methodology_version_rows) is not tuple or any(
            type(item) is not EditorialMethodologyVersionState
            for item in self.editorial_methodology_version_rows
        ):
            _invalid()
        if self.editorial_methodology_version_rows != tuple(
            sorted(
                self.editorial_methodology_version_rows,
                key=lambda item: (_order_value(item.id),),
            )
        ):
            _invalid()
        if type(self.seo_metadata_version_rows) is not tuple or any(
            type(item) is not SeoMetadataVersionState
            for item in self.seo_metadata_version_rows
        ):
            _invalid()
        if self.seo_metadata_version_rows != tuple(
            sorted(
                self.seo_metadata_version_rows,
                key=lambda item: (_order_value(item.id),),
            )
        ):
            _invalid()
        if type(self.structured_data_manifest_rows) is not tuple or any(
            type(item) is not StructuredDataManifest
            for item in self.structured_data_manifest_rows
        ):
            _invalid()
        if self.structured_data_manifest_rows != tuple(
            sorted(
                self.structured_data_manifest_rows,
                key=lambda item: (_order_value(item.id),),
            )
        ):
            _invalid()

    def __repr__(self) -> str:
        return "EditorialContract(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class EditorialMethodologyVersion:
    state: EditorialMethodologyVersionState
    article_methodology_binding_rows: tuple[ArticleMethodologyBinding, ...] = ()

    def __post_init__(self) -> None:
        if type(self.state) is not EditorialMethodologyVersionState:
            _invalid()
        if type(self.article_methodology_binding_rows) is not tuple or any(
            type(item) is not ArticleMethodologyBinding
            for item in self.article_methodology_binding_rows
        ):
            _invalid()
        if self.article_methodology_binding_rows != tuple(
            sorted(
                self.article_methodology_binding_rows,
                key=lambda item: (_order_value(item.article_version_id),),
            )
        ):
            _invalid()

    def __repr__(self) -> str:
        return "EditorialMethodologyVersion(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class MediaAsset:
    state: MediaAssetState

    def __post_init__(self) -> None:
        if type(self.state) is not MediaAssetState:
            _invalid()

    def __repr__(self) -> str:
        return "MediaAsset(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ReviewComment:
    state: ReviewCommentState

    def __post_init__(self) -> None:
        if type(self.state) is not ReviewCommentState:
            _invalid()

    def __repr__(self) -> str:
        return "ReviewComment(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class SeoMetadataVersion:
    state: SeoMetadataVersionState
    article_version_rows: tuple[ArticleVersionState, ...] = ()
    structured_data_manifest_rows: tuple[StructuredDataManifest, ...] = ()

    def __post_init__(self) -> None:
        if type(self.state) is not SeoMetadataVersionState:
            _invalid()
        if type(self.article_version_rows) is not tuple or any(
            type(item) is not ArticleVersionState for item in self.article_version_rows
        ):
            _invalid()
        if self.article_version_rows != tuple(
            sorted(self.article_version_rows, key=lambda item: (_order_value(item.id),))
        ):
            _invalid()
        if type(self.structured_data_manifest_rows) is not tuple or any(
            type(item) is not StructuredDataManifest
            for item in self.structured_data_manifest_rows
        ):
            _invalid()
        if self.structured_data_manifest_rows != tuple(
            sorted(
                self.structured_data_manifest_rows,
                key=lambda item: (_order_value(item.id),),
            )
        ):
            _invalid()

    def __repr__(self) -> str:
        return "SeoMetadataVersion(<redacted>)"


__all__ = [
    "Article",
    "ArticleBlock",
    "ArticleBlockProduct",
    "ArticleDisclosureContext",
    "ArticleLinkState",
    "ArticleMethodologyBinding",
    "ArticlePlan",
    "ArticlePlanState",
    "ArticleSlug",
    "ArticleSlugState",
    "ArticleState",
    "ArticleTemplateVersion",
    "ArticleTemplateVersionState",
    "ArticleTypeVersion",
    "ArticleTypeVersionState",
    "ArticleVersion",
    "ArticleVersionState",
    "ComparisonAxis",
    "ComparisonValue",
    "ContentSchemaVersion",
    "ContentSchemaVersionState",
    "EditorialContract",
    "EditorialMethodologyVersion",
    "EditorialMethodologyVersionState",
    "MediaAsset",
    "MediaAssetState",
    "Recommendation",
    "RecommendationRationale",
    "RecommendationSet",
    "ReviewComment",
    "ReviewCommentState",
    "SeoMetadataVersion",
    "SeoMetadataVersionState",
    "StructuredDataManifest",
]

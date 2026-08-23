"""Explicit fail-closed scalar mappers for the EDITORIAL ST-0308 slice."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from raos.adapters.persistence.sqlalchemy.physical_constraints import (
    install_mapper_physical_constraint_guards,
)
from raos.domain.ai.ids import (
    AiJobId,
)
from raos.domain.catalog.ids import (
    CanonicalProductId,
    OfferId,
)
from raos.domain.editorial.aggregates import (
    ArticleBlock,
    ArticleBlockProduct,
    ArticleDisclosureContext,
    ArticleLinkState,
    ArticleMethodologyBinding,
    ArticlePlanState,
    ArticleSlugState,
    ArticleState,
    ArticleTemplateVersionState,
    ArticleTypeVersionState,
    ArticleVersionState,
    ComparisonAxis,
    ComparisonValue,
    ContentSchemaVersionState,
    EditorialMethodologyVersionState,
    MediaAssetState,
    Recommendation,
    RecommendationRationale,
    RecommendationSet,
    ReviewCommentState,
    SeoMetadataVersionState,
    StructuredDataManifest,
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
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode


def _corrupt() -> PersistenceError:
    return PersistenceError(PersistenceErrorCode.STORAGE_CORRUPTION)


ArticleStateScalars = tuple[
    ArticleId,
    str,
    SiteId,
    ArticlePlanId,
    ArticleArticleType,
    ArticleStatus,
    ArticleVersionId | None,
    ArticleVersionId | None,
    AwareUtcDateTime | None,
    str | None,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AggregateVersion,
]


def map_editorial_article_from_row(
    *,
    id: ArticleId,
    display_id: str,
    site_id: SiteId,
    article_plan_id: ArticlePlanId,
    article_type: ArticleArticleType,
    status: ArticleStatus,
    current_version_id: ArticleVersionId | None,
    published_version_id: ArticleVersionId | None,
    archived_at: AwareUtcDateTime | None,
    archive_reason: str | None,
    created_at: AwareUtcDateTime,
    updated_at: AwareUtcDateTime,
    lock_version: AggregateVersion,
) -> ArticleState:
    try:
        return ArticleState(
            id=id,
            display_id=display_id,
            site_id=site_id,
            article_plan_id=article_plan_id,
            article_type=article_type,
            status=status,
            current_version_id=current_version_id,
            published_version_id=published_version_id,
            archived_at=archived_at,
            archive_reason=archive_reason,
            created_at=created_at,
            updated_at=updated_at,
            lock_version=lock_version,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_editorial_article_to_row(value: ArticleState) -> ArticleStateScalars:
    if type(value) is not ArticleState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.site_id,
        value.article_plan_id,
        value.article_type,
        value.status,
        value.current_version_id,
        value.published_version_id,
        value.archived_at,
        value.archive_reason,
        value.created_at,
        value.updated_at,
        value.lock_version,
    )


ArticleBlockScalars = tuple[
    ArticleBlockId,
    ArticleVersionId,
    str,
    ArticleBlockBlockType,
    int,
    int | None,
    ArticleBlockContentJson,
    str,
    Sha256Digest,
    AwareUtcDateTime,
]


def map_editorial_article_block_from_row(
    *,
    id: ArticleBlockId,
    article_version_id: ArticleVersionId,
    block_key: str,
    block_type: ArticleBlockBlockType,
    position: int,
    heading_level: int | None,
    content: ArticleBlockContentJson,
    plain_text: str,
    content_sha256: Sha256Digest,
    created_at: AwareUtcDateTime,
) -> ArticleBlock:
    try:
        return ArticleBlock(
            id=id,
            article_version_id=article_version_id,
            block_key=block_key,
            block_type=block_type,
            position=position,
            heading_level=heading_level,
            content=content,
            plain_text=plain_text,
            content_sha256=content_sha256,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_editorial_article_block_to_row(value: ArticleBlock) -> ArticleBlockScalars:
    if type(value) is not ArticleBlock:
        raise _corrupt() from None
    return (
        value.id,
        value.article_version_id,
        value.block_key,
        value.block_type,
        value.position,
        value.heading_level,
        value.content,
        value.plain_text,
        value.content_sha256,
        value.created_at,
    )


ArticleBlockProductScalars = tuple[
    ArticleBlockId,
    CanonicalProductId,
    OfferId | None,
    ArticleBlockProductPlacementRole,
    int,
    str,
    AwareUtcDateTime,
]


def map_editorial_article_block_product_from_row(
    *,
    article_block_id: ArticleBlockId,
    product_id: CanonicalProductId,
    offer_id: OfferId | None,
    placement_role: ArticleBlockProductPlacementRole,
    position: int,
    placement_id: str,
    created_at: AwareUtcDateTime,
) -> ArticleBlockProduct:
    try:
        return ArticleBlockProduct(
            article_block_id=article_block_id,
            product_id=product_id,
            offer_id=offer_id,
            placement_role=placement_role,
            position=position,
            placement_id=placement_id,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_editorial_article_block_product_to_row(
    value: ArticleBlockProduct,
) -> ArticleBlockProductScalars:
    if type(value) is not ArticleBlockProduct:
        raise _corrupt() from None
    return (
        value.article_block_id,
        value.product_id,
        value.offer_id,
        value.placement_role,
        value.position,
        value.placement_id,
        value.created_at,
    )


ArticleDisclosureContextScalars = tuple[
    ArticleVersionId,
    bool,
    bool,
    tuple[str, ...],
    str,
    str | None,
    PrincipalId | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
]


def map_editorial_article_disclosure_context_from_row(
    *,
    article_version_id: ArticleVersionId,
    affiliate_relationship: bool,
    material_benefit_relationship: bool,
    benefit_types: tuple[str, ...],
    disclosure_policy_version: str,
    additional_disclosure_text: str | None,
    reviewed_by_principal_id: PrincipalId | None,
    reviewed_at: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
) -> ArticleDisclosureContext:
    try:
        return ArticleDisclosureContext(
            article_version_id=article_version_id,
            affiliate_relationship=affiliate_relationship,
            material_benefit_relationship=material_benefit_relationship,
            benefit_types=benefit_types,
            disclosure_policy_version=disclosure_policy_version,
            additional_disclosure_text=additional_disclosure_text,
            reviewed_by_principal_id=reviewed_by_principal_id,
            reviewed_at=reviewed_at,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_editorial_article_disclosure_context_to_row(
    value: ArticleDisclosureContext,
) -> ArticleDisclosureContextScalars:
    if type(value) is not ArticleDisclosureContext:
        raise _corrupt() from None
    return (
        value.article_version_id,
        value.affiliate_relationship,
        value.material_benefit_relationship,
        value.benefit_types,
        value.disclosure_policy_version,
        value.additional_disclosure_text,
        value.reviewed_by_principal_id,
        value.reviewed_at,
        value.created_at,
    )


ArticleLinkStateScalars = tuple[
    ArticleLinkId,
    ArticleId,
    ArticleId,
    ArticleLinkLinkType,
    str | None,
    str | None,
    ArticleLinkStatus,
    str | None,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AggregateVersion,
]


def map_editorial_article_link_from_row(
    *,
    id: ArticleLinkId,
    from_article_id: ArticleId,
    to_article_id: ArticleId,
    link_type: ArticleLinkLinkType,
    anchor_text: str | None,
    source_block_key: str | None,
    status: ArticleLinkStatus,
    reason: str | None,
    created_at: AwareUtcDateTime,
    updated_at: AwareUtcDateTime,
    lock_version: AggregateVersion,
) -> ArticleLinkState:
    try:
        return ArticleLinkState(
            id=id,
            from_article_id=from_article_id,
            to_article_id=to_article_id,
            link_type=link_type,
            anchor_text=anchor_text,
            source_block_key=source_block_key,
            status=status,
            reason=reason,
            created_at=created_at,
            updated_at=updated_at,
            lock_version=lock_version,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_editorial_article_link_to_row(
    value: ArticleLinkState,
) -> ArticleLinkStateScalars:
    if type(value) is not ArticleLinkState:
        raise _corrupt() from None
    return (
        value.id,
        value.from_article_id,
        value.to_article_id,
        value.link_type,
        value.anchor_text,
        value.source_block_key,
        value.status,
        value.reason,
        value.created_at,
        value.updated_at,
        value.lock_version,
    )


ArticleMethodologyBindingScalars = tuple[
    ArticleVersionId,
    EditorialMethodologyVersionId,
    ObjectArtifactId,
    Sha256Digest,
    AwareUtcDateTime,
    PrincipalId,
]


def map_editorial_article_methodology_binding_from_row(
    *,
    article_version_id: ArticleVersionId,
    methodology_version_id: EditorialMethodologyVersionId,
    candidate_universe_artifact_id: ObjectArtifactId,
    candidate_universe_sha256: Sha256Digest,
    bound_at: AwareUtcDateTime,
    bound_by_principal_id: PrincipalId,
) -> ArticleMethodologyBinding:
    try:
        return ArticleMethodologyBinding(
            article_version_id=article_version_id,
            methodology_version_id=methodology_version_id,
            candidate_universe_artifact_id=candidate_universe_artifact_id,
            candidate_universe_sha256=candidate_universe_sha256,
            bound_at=bound_at,
            bound_by_principal_id=bound_by_principal_id,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_editorial_article_methodology_binding_to_row(
    value: ArticleMethodologyBinding,
) -> ArticleMethodologyBindingScalars:
    if type(value) is not ArticleMethodologyBinding:
        raise _corrupt() from None
    return (
        value.article_version_id,
        value.methodology_version_id,
        value.candidate_universe_artifact_id,
        value.candidate_universe_sha256,
        value.bound_at,
        value.bound_by_principal_id,
    )


ArticlePlanStateScalars = tuple[
    ArticlePlanId,
    str,
    SiteId,
    CategoryId,
    IntentClusterId,
    KeywordId,
    ArticlePlanArticleType,
    str,
    str,
    ArticlePlanStatus,
    int,
    OpportunityAssessmentId | None,
    PrincipalId,
    PrincipalId | None,
    AwareUtcDateTime | None,
    ArticlePlanBriefJson,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AggregateVersion,
]


def map_editorial_article_plan_from_row(
    *,
    id: ArticlePlanId,
    display_id: str,
    site_id: SiteId,
    category_id: CategoryId,
    intent_cluster_id: IntentClusterId,
    primary_keyword_id: KeywordId,
    article_type: ArticlePlanArticleType,
    working_title: str,
    objective: str,
    status: ArticlePlanStatus,
    priority: int,
    opportunity_assessment_id: OpportunityAssessmentId | None,
    created_by_principal_id: PrincipalId,
    approved_by_principal_id: PrincipalId | None,
    approved_at: AwareUtcDateTime | None,
    brief: ArticlePlanBriefJson,
    created_at: AwareUtcDateTime,
    updated_at: AwareUtcDateTime,
    lock_version: AggregateVersion,
) -> ArticlePlanState:
    try:
        return ArticlePlanState(
            id=id,
            display_id=display_id,
            site_id=site_id,
            category_id=category_id,
            intent_cluster_id=intent_cluster_id,
            primary_keyword_id=primary_keyword_id,
            article_type=article_type,
            working_title=working_title,
            objective=objective,
            status=status,
            priority=priority,
            opportunity_assessment_id=opportunity_assessment_id,
            created_by_principal_id=created_by_principal_id,
            approved_by_principal_id=approved_by_principal_id,
            approved_at=approved_at,
            brief=brief,
            created_at=created_at,
            updated_at=updated_at,
            lock_version=lock_version,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_editorial_article_plan_to_row(
    value: ArticlePlanState,
) -> ArticlePlanStateScalars:
    if type(value) is not ArticlePlanState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.site_id,
        value.category_id,
        value.intent_cluster_id,
        value.primary_keyword_id,
        value.article_type,
        value.working_title,
        value.objective,
        value.status,
        value.priority,
        value.opportunity_assessment_id,
        value.created_by_principal_id,
        value.approved_by_principal_id,
        value.approved_at,
        value.brief,
        value.created_at,
        value.updated_at,
        value.lock_version,
    )


ArticleSlugStateScalars = tuple[
    ArticleSlugId,
    SiteId,
    ArticleId,
    str,
    str,
    ArticleSlugStatus,
    AwareUtcDateTime,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
]


def map_editorial_article_slug_from_row(
    *,
    id: ArticleSlugId,
    site_id: SiteId,
    article_id: ArticleId,
    slug: str,
    normalized_path: str,
    status: ArticleSlugStatus,
    valid_from: AwareUtcDateTime,
    valid_to: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
) -> ArticleSlugState:
    try:
        return ArticleSlugState(
            id=id,
            site_id=site_id,
            article_id=article_id,
            slug=slug,
            normalized_path=normalized_path,
            status=status,
            valid_from=valid_from,
            valid_to=valid_to,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_editorial_article_slug_to_row(
    value: ArticleSlugState,
) -> ArticleSlugStateScalars:
    if type(value) is not ArticleSlugState:
        raise _corrupt() from None
    return (
        value.id,
        value.site_id,
        value.article_id,
        value.slug,
        value.normalized_path,
        value.status,
        value.valid_from,
        value.valid_to,
        value.created_at,
    )


ArticleTemplateVersionStateScalars = tuple[
    ArticleTemplateVersionId,
    ArticleTypeVersionId,
    str,
    ArticleTemplateVersionTemplateJson,
    Sha256Digest,
    ArticleTemplateVersionStatus,
    PrincipalId | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
]


def map_editorial_article_template_version_from_row(
    *,
    id: ArticleTemplateVersionId,
    article_type_version_id: ArticleTypeVersionId,
    semantic_version: str,
    template: ArticleTemplateVersionTemplateJson,
    template_sha256: Sha256Digest,
    status: ArticleTemplateVersionStatus,
    approved_by_principal_id: PrincipalId | None,
    approved_at: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
) -> ArticleTemplateVersionState:
    try:
        return ArticleTemplateVersionState(
            id=id,
            article_type_version_id=article_type_version_id,
            semantic_version=semantic_version,
            template=template,
            template_sha256=template_sha256,
            status=status,
            approved_by_principal_id=approved_by_principal_id,
            approved_at=approved_at,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_editorial_article_template_version_to_row(
    value: ArticleTemplateVersionState,
) -> ArticleTemplateVersionStateScalars:
    if type(value) is not ArticleTemplateVersionState:
        raise _corrupt() from None
    return (
        value.id,
        value.article_type_version_id,
        value.semantic_version,
        value.template,
        value.template_sha256,
        value.status,
        value.approved_by_principal_id,
        value.approved_at,
        value.created_at,
    )


ArticleTypeVersionStateScalars = tuple[
    ArticleTypeVersionId,
    str,
    str,
    ArticleTypeVersionContractJson,
    Sha256Digest,
    ArticleTypeVersionStatus,
    PrincipalId | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
]


def map_editorial_article_type_version_from_row(
    *,
    id: ArticleTypeVersionId,
    article_type_code: str,
    semantic_version: str,
    contract: ArticleTypeVersionContractJson,
    contract_sha256: Sha256Digest,
    status: ArticleTypeVersionStatus,
    approved_by_principal_id: PrincipalId | None,
    approved_at: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
) -> ArticleTypeVersionState:
    try:
        return ArticleTypeVersionState(
            id=id,
            article_type_code=article_type_code,
            semantic_version=semantic_version,
            contract=contract,
            contract_sha256=contract_sha256,
            status=status,
            approved_by_principal_id=approved_by_principal_id,
            approved_at=approved_at,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_editorial_article_type_version_to_row(
    value: ArticleTypeVersionState,
) -> ArticleTypeVersionStateScalars:
    if type(value) is not ArticleTypeVersionState:
        raise _corrupt() from None
    return (
        value.id,
        value.article_type_code,
        value.semantic_version,
        value.contract,
        value.contract_sha256,
        value.status,
        value.approved_by_principal_id,
        value.approved_at,
        value.created_at,
    )


ArticleVersionStateScalars = tuple[
    ArticleVersionId,
    str,
    ArticleId,
    int,
    int,
    str,
    str | None,
    str | None,
    str | None,
    Sha256Digest,
    ArticleVersionStatus,
    SourcePacketVersionId,
    ArticleVersionId | None,
    AiJobId | None,
    ArticleVersionCreatedByActorType,
    ActorId | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AggregateVersion,
    ContentSchemaVersionId,
    ArticleTypeVersionId,
    ArticleTemplateVersionId,
    SeoMetadataVersionId,
]


def map_editorial_article_version_from_row(
    *,
    id: ArticleVersionId,
    display_id: str,
    article_id: ArticleId,
    version_no: int,
    content_schema_version: int,
    title: str,
    meta_title: str | None,
    meta_description: str | None,
    excerpt: str | None,
    body_sha256: Sha256Digest,
    status: ArticleVersionStatus,
    source_packet_version_id: SourcePacketVersionId,
    based_on_version_id: ArticleVersionId | None,
    ai_job_id: AiJobId | None,
    created_by_actor_type: ArticleVersionCreatedByActorType,
    created_by_actor_id: ActorId | None,
    submitted_at: AwareUtcDateTime | None,
    reviewed_at: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
    updated_at: AwareUtcDateTime,
    lock_version: AggregateVersion,
    content_schema_version_id: ContentSchemaVersionId,
    article_type_version_id: ArticleTypeVersionId,
    article_template_version_id: ArticleTemplateVersionId,
    seo_metadata_version_id: SeoMetadataVersionId,
) -> ArticleVersionState:
    try:
        return ArticleVersionState(
            id=id,
            display_id=display_id,
            article_id=article_id,
            version_no=version_no,
            content_schema_version=content_schema_version,
            title=title,
            meta_title=meta_title,
            meta_description=meta_description,
            excerpt=excerpt,
            body_sha256=body_sha256,
            status=status,
            source_packet_version_id=source_packet_version_id,
            based_on_version_id=based_on_version_id,
            ai_job_id=ai_job_id,
            created_by_actor_type=created_by_actor_type,
            created_by_actor_id=created_by_actor_id,
            submitted_at=submitted_at,
            reviewed_at=reviewed_at,
            created_at=created_at,
            updated_at=updated_at,
            lock_version=lock_version,
            content_schema_version_id=content_schema_version_id,
            article_type_version_id=article_type_version_id,
            article_template_version_id=article_template_version_id,
            seo_metadata_version_id=seo_metadata_version_id,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_editorial_article_version_to_row(
    value: ArticleVersionState,
) -> ArticleVersionStateScalars:
    if type(value) is not ArticleVersionState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.article_id,
        value.version_no,
        value.content_schema_version,
        value.title,
        value.meta_title,
        value.meta_description,
        value.excerpt,
        value.body_sha256,
        value.status,
        value.source_packet_version_id,
        value.based_on_version_id,
        value.ai_job_id,
        value.created_by_actor_type,
        value.created_by_actor_id,
        value.submitted_at,
        value.reviewed_at,
        value.created_at,
        value.updated_at,
        value.lock_version,
        value.content_schema_version_id,
        value.article_type_version_id,
        value.article_template_version_id,
        value.seo_metadata_version_id,
    )


ComparisonAxisScalars = tuple[
    ComparisonAxisId,
    ArticleVersionId,
    str,
    str,
    str,
    ComparisonAxisDataType,
    str | None,
    int,
    bool,
    AwareUtcDateTime,
]


def map_editorial_comparison_axis_from_row(
    *,
    id: ComparisonAxisId,
    article_version_id: ArticleVersionId,
    axis_code: str,
    name: str,
    description: str,
    data_type: ComparisonAxisDataType,
    unit_code: str | None,
    position: int,
    is_required: bool,
    created_at: AwareUtcDateTime,
) -> ComparisonAxis:
    try:
        return ComparisonAxis(
            id=id,
            article_version_id=article_version_id,
            axis_code=axis_code,
            name=name,
            description=description,
            data_type=data_type,
            unit_code=unit_code,
            position=position,
            is_required=is_required,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_editorial_comparison_axis_to_row(
    value: ComparisonAxis,
) -> ComparisonAxisScalars:
    if type(value) is not ComparisonAxis:
        raise _corrupt() from None
    return (
        value.id,
        value.article_version_id,
        value.axis_code,
        value.name,
        value.description,
        value.data_type,
        value.unit_code,
        value.position,
        value.is_required,
        value.created_at,
    )


ComparisonValueScalars = tuple[
    ComparisonValueId,
    ComparisonAxisId,
    CanonicalProductId,
    str | None,
    Decimal | None,
    bool | None,
    date | None,
    str | None,
    str,
    FactId | None,
    ComparisonValueValidationStatus,
    AwareUtcDateTime,
]


def map_editorial_comparison_value_from_row(
    *,
    id: ComparisonValueId,
    comparison_axis_id: ComparisonAxisId,
    product_id: CanonicalProductId,
    value_text: str | None,
    value_numeric: Decimal | None,
    value_boolean: bool | None,
    value_date: date | None,
    value_code: str | None,
    display_value: str,
    source_fact_id: FactId | None,
    validation_status: ComparisonValueValidationStatus,
    created_at: AwareUtcDateTime,
) -> ComparisonValue:
    try:
        return ComparisonValue(
            id=id,
            comparison_axis_id=comparison_axis_id,
            product_id=product_id,
            value_text=value_text,
            value_numeric=value_numeric,
            value_boolean=value_boolean,
            value_date=value_date,
            value_code=value_code,
            display_value=display_value,
            source_fact_id=source_fact_id,
            validation_status=validation_status,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_editorial_comparison_value_to_row(
    value: ComparisonValue,
) -> ComparisonValueScalars:
    if type(value) is not ComparisonValue:
        raise _corrupt() from None
    return (
        value.id,
        value.comparison_axis_id,
        value.product_id,
        value.value_text,
        value.value_numeric,
        value.value_boolean,
        value.value_date,
        value.value_code,
        value.display_value,
        value.source_fact_id,
        value.validation_status,
        value.created_at,
    )


ContentSchemaVersionStateScalars = tuple[
    ContentSchemaVersionId,
    str,
    str,
    ObjectArtifactId,
    Sha256Digest,
    ContentSchemaVersionStatus,
    AwareUtcDateTime,
    AwareUtcDateTime | None,
    PrincipalId | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
]


def map_editorial_content_schema_version_from_row(
    *,
    id: ContentSchemaVersionId,
    schema_code: str,
    semantic_version: str,
    artifact_id: ObjectArtifactId,
    schema_sha256: Sha256Digest,
    status: ContentSchemaVersionStatus,
    effective_from: AwareUtcDateTime,
    effective_to: AwareUtcDateTime | None,
    approved_by_principal_id: PrincipalId | None,
    approved_at: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
) -> ContentSchemaVersionState:
    try:
        return ContentSchemaVersionState(
            id=id,
            schema_code=schema_code,
            semantic_version=semantic_version,
            artifact_id=artifact_id,
            schema_sha256=schema_sha256,
            status=status,
            effective_from=effective_from,
            effective_to=effective_to,
            approved_by_principal_id=approved_by_principal_id,
            approved_at=approved_at,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_editorial_content_schema_version_to_row(
    value: ContentSchemaVersionState,
) -> ContentSchemaVersionStateScalars:
    if type(value) is not ContentSchemaVersionState:
        raise _corrupt() from None
    return (
        value.id,
        value.schema_code,
        value.semantic_version,
        value.artifact_id,
        value.schema_sha256,
        value.status,
        value.effective_from,
        value.effective_to,
        value.approved_by_principal_id,
        value.approved_at,
        value.created_at,
    )


EditorialMethodologyVersionStateScalars = tuple[
    EditorialMethodologyVersionId,
    str,
    str,
    str,
    ArticleTypeVersionId,
    EditorialMethodologyVersionDefinitionJson,
    Sha256Digest,
    bool,
    EditorialMethodologyVersionStatus,
    PrincipalId | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
]


def map_editorial_editorial_methodology_version_from_row(
    *,
    id: EditorialMethodologyVersionId,
    methodology_code: str,
    semantic_version: str,
    article_type_code: str,
    article_type_version_id: ArticleTypeVersionId,
    definition: EditorialMethodologyVersionDefinitionJson,
    definition_sha256: Sha256Digest,
    excludes_finance_inputs: bool,
    status: EditorialMethodologyVersionStatus,
    approved_by_principal_id: PrincipalId | None,
    approved_at: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
) -> EditorialMethodologyVersionState:
    try:
        return EditorialMethodologyVersionState(
            id=id,
            methodology_code=methodology_code,
            semantic_version=semantic_version,
            article_type_code=article_type_code,
            article_type_version_id=article_type_version_id,
            definition=definition,
            definition_sha256=definition_sha256,
            excludes_finance_inputs=excludes_finance_inputs,
            status=status,
            approved_by_principal_id=approved_by_principal_id,
            approved_at=approved_at,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_editorial_editorial_methodology_version_to_row(
    value: EditorialMethodologyVersionState,
) -> EditorialMethodologyVersionStateScalars:
    if type(value) is not EditorialMethodologyVersionState:
        raise _corrupt() from None
    return (
        value.id,
        value.methodology_code,
        value.semantic_version,
        value.article_type_code,
        value.article_type_version_id,
        value.definition,
        value.definition_sha256,
        value.excludes_finance_inputs,
        value.status,
        value.approved_by_principal_id,
        value.approved_at,
        value.created_at,
    )


MediaAssetStateScalars = tuple[
    MediaAssetId,
    str,
    MediaAssetAssetClass,
    SourceId,
    ObjectArtifactId,
    Sha256Digest,
    MediaAssetLicenseStatus,
    str,
    str,
    bool,
    ObjectArtifactId | None,
    int,
    int,
    AwareUtcDateTime,
    MediaAssetStatus,
    PrincipalId | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
]


def map_editorial_media_asset_from_row(
    *,
    id: MediaAssetId,
    display_id: str,
    asset_class: MediaAssetAssetClass,
    source_id: SourceId,
    raw_artifact_id: ObjectArtifactId,
    asset_sha256: Sha256Digest,
    license_status: MediaAssetLicenseStatus,
    modification_policy: str,
    alt_text: str,
    decorative: bool,
    long_description_artifact_id: ObjectArtifactId | None,
    width: int,
    height: int,
    captured_or_observed_at: AwareUtcDateTime,
    status: MediaAssetStatus,
    approved_by_principal_id: PrincipalId | None,
    approved_at: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
) -> MediaAssetState:
    try:
        return MediaAssetState(
            id=id,
            display_id=display_id,
            asset_class=asset_class,
            source_id=source_id,
            raw_artifact_id=raw_artifact_id,
            asset_sha256=asset_sha256,
            license_status=license_status,
            modification_policy=modification_policy,
            alt_text=alt_text,
            decorative=decorative,
            long_description_artifact_id=long_description_artifact_id,
            width=width,
            height=height,
            captured_or_observed_at=captured_or_observed_at,
            status=status,
            approved_by_principal_id=approved_by_principal_id,
            approved_at=approved_at,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_editorial_media_asset_to_row(value: MediaAssetState) -> MediaAssetStateScalars:
    if type(value) is not MediaAssetState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.asset_class,
        value.source_id,
        value.raw_artifact_id,
        value.asset_sha256,
        value.license_status,
        value.modification_policy,
        value.alt_text,
        value.decorative,
        value.long_description_artifact_id,
        value.width,
        value.height,
        value.captured_or_observed_at,
        value.status,
        value.approved_by_principal_id,
        value.approved_at,
        value.created_at,
    )


RecommendationScalars = tuple[
    RecommendationId,
    RecommendationSetId,
    CanonicalProductId,
    int,
    Decimal,
    RecommendationStatus,
    AwareUtcDateTime,
]


def map_editorial_recommendation_from_row(
    *,
    id: RecommendationId,
    recommendation_set_id: RecommendationSetId,
    product_id: CanonicalProductId,
    rank_position: int,
    suitability_score: Decimal,
    status: RecommendationStatus,
    created_at: AwareUtcDateTime,
) -> Recommendation:
    try:
        return Recommendation(
            id=id,
            recommendation_set_id=recommendation_set_id,
            product_id=product_id,
            rank_position=rank_position,
            suitability_score=suitability_score,
            status=status,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_editorial_recommendation_to_row(value: Recommendation) -> RecommendationScalars:
    if type(value) is not Recommendation:
        raise _corrupt() from None
    return (
        value.id,
        value.recommendation_set_id,
        value.product_id,
        value.rank_position,
        value.suitability_score,
        value.status,
        value.created_at,
    )


RecommendationRationaleScalars = tuple[
    RecommendationRationaleId,
    RecommendationId,
    RecommendationRationaleRationaleType,
    str,
    ClaimId | None,
    FactId | None,
    int,
    AwareUtcDateTime,
]


def map_editorial_recommendation_rationale_from_row(
    *,
    id: RecommendationRationaleId,
    recommendation_id: RecommendationId,
    rationale_type: RecommendationRationaleRationaleType,
    rationale_text: str,
    claim_id: ClaimId | None,
    source_fact_id: FactId | None,
    position: int,
    created_at: AwareUtcDateTime,
) -> RecommendationRationale:
    try:
        return RecommendationRationale(
            id=id,
            recommendation_id=recommendation_id,
            rationale_type=rationale_type,
            rationale_text=rationale_text,
            claim_id=claim_id,
            source_fact_id=source_fact_id,
            position=position,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_editorial_recommendation_rationale_to_row(
    value: RecommendationRationale,
) -> RecommendationRationaleScalars:
    if type(value) is not RecommendationRationale:
        raise _corrupt() from None
    return (
        value.id,
        value.recommendation_id,
        value.rationale_type,
        value.rationale_text,
        value.claim_id,
        value.source_fact_id,
        value.position,
        value.created_at,
    )


RecommendationSetScalars = tuple[
    RecommendationSetId,
    ArticleVersionId,
    str,
    str,
    str,
    str,
    str,
    int,
    AwareUtcDateTime,
]


def map_editorial_recommendation_set_from_row(
    *,
    id: RecommendationSetId,
    article_version_id: ArticleVersionId,
    set_code: str,
    name: str,
    target_segment: str,
    methodology: str,
    editorial_policy_version: str,
    position: int,
    created_at: AwareUtcDateTime,
) -> RecommendationSet:
    try:
        return RecommendationSet(
            id=id,
            article_version_id=article_version_id,
            set_code=set_code,
            name=name,
            target_segment=target_segment,
            methodology=methodology,
            editorial_policy_version=editorial_policy_version,
            position=position,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_editorial_recommendation_set_to_row(
    value: RecommendationSet,
) -> RecommendationSetScalars:
    if type(value) is not RecommendationSet:
        raise _corrupt() from None
    return (
        value.id,
        value.article_version_id,
        value.set_code,
        value.name,
        value.target_segment,
        value.methodology,
        value.editorial_policy_version,
        value.position,
        value.created_at,
    )


ReviewCommentStateScalars = tuple[
    ReviewCommentId,
    ArticleVersionId,
    ArticleBlockId | None,
    ClaimId | None,
    ThreadId,
    ReviewCommentId | None,
    PrincipalId,
    str,
    ReviewCommentStatus,
    PrincipalId | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
]


def map_editorial_review_comment_from_row(
    *,
    id: ReviewCommentId,
    article_version_id: ArticleVersionId,
    article_block_id: ArticleBlockId | None,
    claim_id: ClaimId | None,
    thread_id: ThreadId,
    parent_comment_id: ReviewCommentId | None,
    author_principal_id: PrincipalId,
    comment_text: str,
    status: ReviewCommentStatus,
    resolved_by_principal_id: PrincipalId | None,
    resolved_at: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
) -> ReviewCommentState:
    try:
        return ReviewCommentState(
            id=id,
            article_version_id=article_version_id,
            article_block_id=article_block_id,
            claim_id=claim_id,
            thread_id=thread_id,
            parent_comment_id=parent_comment_id,
            author_principal_id=author_principal_id,
            comment_text=comment_text,
            status=status,
            resolved_by_principal_id=resolved_by_principal_id,
            resolved_at=resolved_at,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_editorial_review_comment_to_row(
    value: ReviewCommentState,
) -> ReviewCommentStateScalars:
    if type(value) is not ReviewCommentState:
        raise _corrupt() from None
    return (
        value.id,
        value.article_version_id,
        value.article_block_id,
        value.claim_id,
        value.thread_id,
        value.parent_comment_id,
        value.author_principal_id,
        value.comment_text,
        value.status,
        value.resolved_by_principal_id,
        value.resolved_at,
        value.created_at,
    )


SeoMetadataVersionStateScalars = tuple[
    SeoMetadataVersionId,
    ArticleVersionId,
    str,
    SeoMetadataVersionMetadataJson,
    Sha256Digest,
    SeoMetadataVersionStatus,
    AwareUtcDateTime | None,
    PrincipalId | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
]


def map_editorial_seo_metadata_version_from_row(
    *,
    id: SeoMetadataVersionId,
    article_version_id: ArticleVersionId,
    semantic_version: str,
    metadata: SeoMetadataVersionMetadataJson,
    metadata_sha256: Sha256Digest,
    status: SeoMetadataVersionStatus,
    validated_at: AwareUtcDateTime | None,
    approved_by_principal_id: PrincipalId | None,
    approved_at: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
) -> SeoMetadataVersionState:
    try:
        return SeoMetadataVersionState(
            id=id,
            article_version_id=article_version_id,
            semantic_version=semantic_version,
            metadata=metadata,
            metadata_sha256=metadata_sha256,
            status=status,
            validated_at=validated_at,
            approved_by_principal_id=approved_by_principal_id,
            approved_at=approved_at,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_editorial_seo_metadata_version_to_row(
    value: SeoMetadataVersionState,
) -> SeoMetadataVersionStateScalars:
    if type(value) is not SeoMetadataVersionState:
        raise _corrupt() from None
    return (
        value.id,
        value.article_version_id,
        value.semantic_version,
        value.metadata,
        value.metadata_sha256,
        value.status,
        value.validated_at,
        value.approved_by_principal_id,
        value.approved_at,
        value.created_at,
    )


StructuredDataManifestScalars = tuple[
    StructuredDataManifestId,
    ArticleVersionId,
    SeoMetadataVersionId,
    str,
    Sha256Digest,
    ObjectArtifactId,
    Sha256Digest,
    tuple[str, ...],
    tuple[str, ...],
    StructuredDataManifestValidationStatus,
    AwareUtcDateTime,
    AwareUtcDateTime,
]


def map_editorial_structured_data_manifest_from_row(
    *,
    id: StructuredDataManifestId,
    article_version_id: ArticleVersionId,
    seo_metadata_version_id: SeoMetadataVersionId,
    generator_version: str,
    visible_content_sha256: Sha256Digest,
    jsonld_artifact_id: ObjectArtifactId,
    jsonld_sha256: Sha256Digest,
    enabled_types: tuple[str, ...],
    disabled_types: tuple[str, ...],
    validation_status: StructuredDataManifestValidationStatus,
    validated_at: AwareUtcDateTime,
    created_at: AwareUtcDateTime,
) -> StructuredDataManifest:
    try:
        return StructuredDataManifest(
            id=id,
            article_version_id=article_version_id,
            seo_metadata_version_id=seo_metadata_version_id,
            generator_version=generator_version,
            visible_content_sha256=visible_content_sha256,
            jsonld_artifact_id=jsonld_artifact_id,
            jsonld_sha256=jsonld_sha256,
            enabled_types=enabled_types,
            disabled_types=disabled_types,
            validation_status=validation_status,
            validated_at=validated_at,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_editorial_structured_data_manifest_to_row(
    value: StructuredDataManifest,
) -> StructuredDataManifestScalars:
    if type(value) is not StructuredDataManifest:
        raise _corrupt() from None
    return (
        value.id,
        value.article_version_id,
        value.seo_metadata_version_id,
        value.generator_version,
        value.visible_content_sha256,
        value.jsonld_artifact_id,
        value.jsonld_sha256,
        value.enabled_types,
        value.disabled_types,
        value.validation_status,
        value.validated_at,
        value.created_at,
    )


__all__ = [
    "map_editorial_article_block_from_row",
    "map_editorial_article_block_product_from_row",
    "map_editorial_article_block_product_to_row",
    "map_editorial_article_block_to_row",
    "map_editorial_article_disclosure_context_from_row",
    "map_editorial_article_disclosure_context_to_row",
    "map_editorial_article_from_row",
    "map_editorial_article_link_from_row",
    "map_editorial_article_link_to_row",
    "map_editorial_article_methodology_binding_from_row",
    "map_editorial_article_methodology_binding_to_row",
    "map_editorial_article_plan_from_row",
    "map_editorial_article_plan_to_row",
    "map_editorial_article_slug_from_row",
    "map_editorial_article_slug_to_row",
    "map_editorial_article_template_version_from_row",
    "map_editorial_article_template_version_to_row",
    "map_editorial_article_to_row",
    "map_editorial_article_type_version_from_row",
    "map_editorial_article_type_version_to_row",
    "map_editorial_article_version_from_row",
    "map_editorial_article_version_to_row",
    "map_editorial_comparison_axis_from_row",
    "map_editorial_comparison_axis_to_row",
    "map_editorial_comparison_value_from_row",
    "map_editorial_comparison_value_to_row",
    "map_editorial_content_schema_version_from_row",
    "map_editorial_content_schema_version_to_row",
    "map_editorial_editorial_methodology_version_from_row",
    "map_editorial_editorial_methodology_version_to_row",
    "map_editorial_media_asset_from_row",
    "map_editorial_media_asset_to_row",
    "map_editorial_recommendation_from_row",
    "map_editorial_recommendation_rationale_from_row",
    "map_editorial_recommendation_rationale_to_row",
    "map_editorial_recommendation_set_from_row",
    "map_editorial_recommendation_set_to_row",
    "map_editorial_recommendation_to_row",
    "map_editorial_review_comment_from_row",
    "map_editorial_review_comment_to_row",
    "map_editorial_seo_metadata_version_from_row",
    "map_editorial_seo_metadata_version_to_row",
    "map_editorial_structured_data_manifest_from_row",
    "map_editorial_structured_data_manifest_to_row",
]

install_mapper_physical_constraint_guards(globals())

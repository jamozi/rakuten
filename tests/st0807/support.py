"""Synthetic builders for the isolated ST-0807 renderer."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.domain.editorial.seo_renderer import (  # noqa: E402
    CONTENT_TEST_MATRIX_SHA256,
    SEO_METADATA_SCHEMA_ID,
    SEO_METADATA_SCHEMA_SHA256,
    SEO_POLICY_ID,
    SEO_POLICY_SHA256,
    SEO_POLICY_VERSION,
    STRUCTURED_DATA_MANIFEST_SCHEMA_ID,
    STRUCTURED_DATA_MANIFEST_SCHEMA_SHA256,
    ArticleSchemaType,
    AuthorKind,
    AuthorProjection,
    BoundEvidence,
    BreadcrumbProjection,
    ChangeAssessment,
    ChangeClassification,
    ContractBindings,
    ExternalAssessment,
    ExternalAssessmentState,
    ExternalCheck,
    IndexState,
    OriginMode,
    ReferenceId,
    RenderMode,
    RouteBinding,
    RobotsDirective,
    SeoMetadataCandidate,
    SeoRenderRequest,
    Sha256Digest,
    SiteProjection,
    UtcInstant,
    VisibleArticleProjection,
)


ARTICLE_VERSION_ID = ReferenceId("ARTICLE-VERSION-0807")
CURRENT_ROUTE_REF = ReferenceId("ROUTE-CURRENT-0807")
HOME_ROUTE_REF = ReferenceId("ROUTE-HOME-0807")
VALIDATED_AT = UtcInstant(datetime(2026, 8, 12, 0, 0, tzinfo=timezone.utc))
PUBLISHED_AT = UtcInstant(datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc))
MODIFIED_AT = UtcInstant(datetime(2026, 8, 10, 0, 0, tzinfo=timezone.utc))


def digest_for(label: str) -> Sha256Digest:
    return Sha256Digest(hashlib.sha256(label.encode("ascii")).hexdigest())


def evidence_for(check: ExternalCheck) -> BoundEvidence:
    return BoundEvidence(
        ReferenceId(f"EVIDENCE-{check.value}"),
        digest_for(check.value),
    )


def assessor_for(check: ExternalCheck) -> ReferenceId:
    return ReferenceId(f"ASSESSOR-{check.value}")


def contract_bindings() -> ContractBindings:
    return ContractBindings(
        seo_policy_id=SEO_POLICY_ID,
        seo_policy_version=SEO_POLICY_VERSION,
        seo_policy_sha256=Sha256Digest(SEO_POLICY_SHA256),
        seo_metadata_schema_id=SEO_METADATA_SCHEMA_ID,
        seo_metadata_schema_sha256=Sha256Digest(SEO_METADATA_SCHEMA_SHA256),
        structured_data_manifest_schema_id=STRUCTURED_DATA_MANIFEST_SCHEMA_ID,
        structured_data_manifest_schema_sha256=Sha256Digest(
            STRUCTURED_DATA_MANIFEST_SCHEMA_SHA256
        ),
        content_test_matrix_sha256=Sha256Digest(CONTENT_TEST_MATRIX_SHA256),
    )


def external_assessments(
    *,
    state: ExternalAssessmentState = ExternalAssessmentState.PASS,
) -> tuple[ExternalAssessment, ...]:
    return tuple(
        ExternalAssessment(
            article_version_id=ARTICLE_VERSION_ID,
            check=check,
            state=state,
            assessor_ref=assessor_for(check),
            evidence=(
                None
                if state is ExternalAssessmentState.NOT_EVALUATED
                else evidence_for(check)
            ),
        )
        for check in ExternalCheck
    )


def render_request(
    *,
    mode: RenderMode = RenderMode.PUBLIC_CANDIDATE,
    origin: str | None = "https://example.test",
    origin_mode: OriginMode | None = None,
    assessment_state: ExternalAssessmentState = ExternalAssessmentState.PASS,
    site_projection: SiteProjection | None = None,
    article_schema_type: ArticleSchemaType = ArticleSchemaType.ARTICLE,
) -> SeoRenderRequest:
    resolved_origin_mode = (
        OriginMode.ROUTE_ONLY if origin is None else OriginMode.CALLER_SUPPLIED_ORIGIN
    )
    if origin_mode is not None:
        resolved_origin_mode = origin_mode
    metadata = SeoMetadataCandidate(
        seo_metadata_id=ReferenceId("SEO-METADATA-0807"),
        article_version_id=ARTICLE_VERSION_ID,
        slug="coffee-grinders",
        title="コーヒーミルの選び方",
        meta_description="用途と手入れの条件から選び方を比較します。",
        canonical_route_ref=CURRENT_ROUTE_REF,
        index_state=IndexState.INDEX,
        robots=(
            RobotsDirective.INDEX,
            RobotsDirective.FOLLOW,
            RobotsDirective.MAX_IMAGE_PREVIEW_LARGE,
        ),
        breadcrumb_refs=(HOME_ROUTE_REF, CURRENT_ROUTE_REF),
        sitemap_inclusion=True,
        substantive_updated_at=MODIFIED_AT,
        structured_data_manifest_ref=ReferenceId("STRUCTURED-DATA-0807"),
    )
    route = RouteBinding(
        article_version_id=ARTICLE_VERSION_ID,
        current_route_ref=CURRENT_ROUTE_REF,
        current_route="/guides/coffee-grinders",
        canonical_route_ref=CURRENT_ROUTE_REF,
        canonical_route="/guides/coffee-grinders",
    )
    visible = VisibleArticleProjection(
        article_version_id=ARTICLE_VERSION_ID,
        title=metadata.title,
        h1=metadata.title,
        author=AuthorProjection(AuthorKind.PERSON, "RAOS 編集部"),
        date_published=PUBLISHED_AT,
        date_modified=MODIFIED_AT,
        visible_content_hash=digest_for("visible-content"),
        visible_content_profile=ReferenceId("VISIBLE-CONTENT-PROFILE-0807"),
        visible_content_source_sha256=digest_for("visible-source"),
    )
    breadcrumbs = (
        BreadcrumbProjection(
            ARTICLE_VERSION_ID,
            HOME_ROUTE_REF,
            1,
            "ホーム",
            "/",
        ),
        BreadcrumbProjection(
            ARTICLE_VERSION_ID,
            CURRENT_ROUTE_REF,
            2,
            metadata.title,
            route.current_route,
        ),
    )
    return SeoRenderRequest(
        contracts=contract_bindings(),
        metadata=metadata,
        route=route,
        visible=visible,
        breadcrumbs=breadcrumbs,
        site_projection=site_projection,
        article_schema_type=article_schema_type,
        mode=mode,
        origin_mode=resolved_origin_mode,
        caller_origin=origin,
        change=ChangeAssessment(
            ARTICLE_VERSION_ID,
            ChangeClassification.SUBSTANTIVE,
            PUBLISHED_AT,
        ),
        external_assessments=external_assessments(state=assessment_state),
        validated_at=VALIDATED_AT,
    )

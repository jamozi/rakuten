"""Focused route-only behavior for ST-0807."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json

import pytest

from raos.domain.editorial.seo_renderer import (
    ArticleSchemaType,
    AuthorKind,
    AuthorProjection,
    ComparisonResult,
    DisabledSchemaType,
    EligibilityReason,
    ExecutionStatus,
    ExternalAssessment,
    ExternalAssessmentState,
    ExternalCheck,
    IndexState,
    LocalValidationResult,
    OriginSource,
    RenderMode,
    RenderStatus,
    RobotsDirective,
    SiteProjection,
    render_seo,
)

from .support import (
    ARTICLE_VERSION_ID,
    assessor_for,
    evidence_for,
    render_request,
)


def test_route_only_candidate_never_invents_an_absolute_url_or_authority() -> None:
    result = render_seo(render_request(origin=None))

    assert result.status is RenderStatus.RENDERED_LOCAL
    assert result.rendered_metadata is not None
    assert result.rendered_metadata.canonical_url is None
    assert result.rendered_metadata.index_state is IndexState.INDEX
    assert result.conditional_local_eligibility is False
    assert result.eligibility_reasons == (
        EligibilityReason.ROUTE_ONLY_ORIGIN_UNAVAILABLE,
    )
    assert result.origin_source is OriginSource.NONE
    assert result.domain_approved is False
    assert result.production_domain_selected is False
    assert result.approval_authorized is False
    assert result.publication_authorized is False
    assert result.release_authorized is False
    assert result.production_authorized is False
    assert result.production_eligible is False
    assert result.formal_evidence is False
    assert result.browser_executed is False
    assert result.staging_executed is False
    assert result.tst_020_executed is False
    assert result.tst_022_executed is False
    assert {
        result.formal_test_status,
        result.tst_020_status,
        result.tst_022_status,
        result.runtime_status,
        result.live_validation_status,
        result.browser_status,
        result.staging_status,
        result.release_status,
        result.production_status,
    } == {ExecutionStatus.NOT_EXECUTED}


def test_preview_forces_noindex_nofollow() -> None:
    result = render_seo(render_request(mode=RenderMode.PREVIEW))

    assert result.rendered_metadata is not None
    assert result.rendered_metadata.index_state is IndexState.NOINDEX
    assert result.rendered_metadata.robots == (
        RobotsDirective.NOINDEX,
        RobotsDirective.NOFOLLOW,
    )
    assert EligibilityReason.PREVIEW_NOINDEX in result.eligibility_reasons


def test_route_mismatch_fails_closed_without_echoing_routes() -> None:
    request = render_request()
    request = replace(
        request,
        route=replace(request.route, canonical_route="/different"),
    )

    result = render_seo(request)

    assert result.status is RenderStatus.RENDERED_LOCAL
    assert result.raw_metadata_candidate is request.metadata
    assert result.conditional_local_eligibility is False
    assert result.eligibility_reasons == (EligibilityReason.ROUTE_MISMATCH,)


@pytest.mark.parametrize(
    "article_type",
    (ArticleSchemaType.ARTICLE, ArticleSchemaType.BLOG_POSTING),
)
def test_explicit_article_type_renders_minimal_visible_jsonld(
    article_type: ArticleSchemaType,
) -> None:
    request = render_request(article_schema_type=article_type)
    result = render_seo(request)

    assert result.status is RenderStatus.RENDERED_LOCAL
    assert result.input_findings == ()
    assert result.raw_metadata_candidate is request.metadata
    assert result.rendered_metadata is not None
    assert result.rendered_metadata.canonical_url == (
        "https://example.test/guides/coffee-grinders"
    )
    assert result.structured_data_manifest is not None
    assert result.structured_data_manifest.validation_result is (
        LocalValidationResult.PASS
    )
    assert article_type.value in result.structured_data_manifest.enabled_types
    assert result.structured_data_manifest.disabled_types == tuple(DisabledSchemaType)
    assert result.conditional_local_eligibility is True
    assert result.eligibility_reasons == ()
    assert result.approval_authorized is False
    assert result.publication_authorized is False
    assert result.release_authorized is False
    assert result.production_eligible is False

    assert result.jsonld_json is not None
    document = json.loads(result.jsonld_json)
    article = document["@graph"][0]
    assert article == {
        "@type": article_type.value,
        "author": {"@type": "Person", "name": "RAOS 編集部"},
        "dateModified": "2026-08-10T00:00:00.000000Z",
        "datePublished": "2026-08-01T00:00:00.000000Z",
        "headline": "コーヒーミルの選び方",
        "mainEntityOfPage": ("https://example.test/guides/coffee-grinders"),
        "url": "https://example.test/guides/coffee-grinders",
    }
    breadcrumb = document["@graph"][1]
    assert breadcrumb["@type"] == "BreadcrumbList"
    assert breadcrumb["itemListElement"] == [
        {
            "@type": "ListItem",
            "item": "https://example.test/",
            "name": "ホーム",
            "position": 1,
        },
        {
            "@type": "ListItem",
            "item": "https://example.test/guides/coffee-grinders",
            "name": "コーヒーミルの選び方",
            "position": 2,
        },
    ]
    assert all(item.result is ComparisonResult.MATCH for item in result.binding_ledger)
    author_entry = next(
        item for item in result.binding_ledger if item.field.value == "JSONLD_AUTHOR"
    )
    assert author_entry.comparison.value == "EXACT_STRUCTURE"
    breadcrumb_routes = tuple(
        item for item in result.binding_ledger if item.field.value == "BREADCRUMB_ROUTE"
    )
    assert breadcrumb_routes
    assert all(item.comparison.value == "EXACT_URL" for item in breadcrumb_routes)
    canonical_route = next(
        item for item in result.binding_ledger if item.field.value == "CANONICAL_ROUTE"
    )
    assert canonical_route.comparison.value == "EXACT_ROUTE"
    assert (
        result.structured_data_manifest.jsonld_sha256.value
        == hashlib.sha256(result.jsonld_json.encode("utf-8")).hexdigest()
    )
    assert (
        result.local_result_digest
        == hashlib.sha256(result.local_result_json.encode("utf-8")).hexdigest()
    )


def test_route_only_full_render_omits_every_url_dependent_graph_node() -> None:
    result = render_seo(render_request(origin=None))

    assert result.rendered_metadata is not None
    assert result.rendered_metadata.canonical_url is None
    assert result.structured_data_manifest is not None
    assert "BreadcrumbList" not in result.structured_data_manifest.enabled_types
    assert result.jsonld_json is not None
    graph = json.loads(result.jsonld_json)["@graph"]
    assert len(graph) == 1
    assert "url" not in graph[0]
    assert "mainEntityOfPage" not in graph[0]
    assert result.conditional_local_eligibility is False
    assert result.eligibility_reasons == (
        EligibilityReason.ROUTE_ONLY_ORIGIN_UNAVAILABLE,
    )


def test_complete_site_projection_and_explicit_organization_author_are_separate() -> (
    None
):
    request = render_request(
        site_projection=SiteProjection("Example Site", "Example Org", "/")
    )
    request = replace(
        request,
        visible=replace(
            request.visible,
            author=AuthorProjection(AuthorKind.ORGANIZATION, "Visible Desk"),
        ),
    )

    result = render_seo(request)

    assert result.jsonld_json is not None
    graph = json.loads(result.jsonld_json)["@graph"]
    assert graph[0]["author"] == {
        "@type": "Organization",
        "name": "Visible Desk",
    }
    assert graph[-2:] == [
        {
            "@type": "Organization",
            "name": "Example Org",
            "url": "https://example.test/",
        },
        {
            "@type": "WebSite",
            "name": "Example Site",
            "url": "https://example.test/",
        },
    ]
    assert result.structured_data_manifest is not None
    assert result.structured_data_manifest.enabled_types == (
        "Article",
        "BreadcrumbList",
        "Organization",
        "WebSite",
    )


def test_nested_organization_author_is_not_a_top_level_manifest_type() -> None:
    request = render_request()
    request = replace(
        request,
        visible=replace(
            request.visible,
            author=AuthorProjection(AuthorKind.ORGANIZATION, "Visible Desk"),
        ),
    )

    result = render_seo(request)

    assert result.jsonld_json is not None
    graph = json.loads(result.jsonld_json)["@graph"]
    assert graph[0]["author"] == {
        "@type": "Organization",
        "name": "Visible Desk",
    }
    assert result.structured_data_manifest is not None
    assert result.structured_data_manifest.enabled_types == (
        "Article",
        "BreadcrumbList",
    )


def test_full_preview_overrides_index_robots_and_sitemap_only_in_rendered_copy() -> (
    None
):
    request = render_request(mode=RenderMode.PREVIEW)
    result = render_seo(request)

    assert result.raw_metadata_candidate is request.metadata
    assert result.raw_metadata_candidate.index_state is IndexState.INDEX
    assert result.raw_metadata_candidate.sitemap_inclusion is True
    assert result.rendered_metadata is not None
    assert result.rendered_metadata.index_state is IndexState.NOINDEX
    assert result.rendered_metadata.robots == (
        RobotsDirective.NOINDEX,
        RobotsDirective.NOFOLLOW,
    )
    assert result.rendered_metadata.sitemap_inclusion is False
    assert result.conditional_local_eligibility is False
    assert result.eligibility_reasons == (EligibilityReason.PREVIEW_NOINDEX,)


@pytest.mark.parametrize(
    ("state", "reason"),
    (
        (
            ExternalAssessmentState.FAIL,
            EligibilityReason.EXTERNAL_ASSESSMENT_FAILED,
        ),
        (
            ExternalAssessmentState.NOT_EVALUATED,
            EligibilityReason.EXTERNAL_ASSESSMENT_NOT_EVALUATED,
        ),
    ),
)
def test_external_nonpass_retains_raw_candidate_and_local_diagnostics(
    state: ExternalAssessmentState,
    reason: EligibilityReason,
) -> None:
    request = render_request(assessment_state=state)
    result = render_seo(request)

    assert result.status is RenderStatus.RENDERED_LOCAL
    assert result.input_findings == ()
    assert result.raw_metadata_candidate is request.metadata
    assert result.rendered_metadata is not None
    assert result.jsonld_json is not None
    assert result.structured_data_manifest is not None
    assert result.structured_data_manifest.validation_result is (
        LocalValidationResult.PASS
    )
    assert result.external_assessments == request.external_assessments
    assert result.conditional_local_eligibility is False
    assert result.eligibility_reasons == (reason,)


def test_external_inventory_has_every_required_pre_resolved_runtime_fact() -> None:
    assert {item.value for item in ExternalCheck} == {
        "TITLE_UNIQUENESS",
        "CANONICAL_GRAPH",
        "ST_0805_POLICY_ELIGIBILITY",
        "BROWSER_VISIBLE_EQUALITY",
        "SUBSTANTIVE_CHANGE_CLASSIFICATION",
        "ROUTE_EXISTENCE",
        "HTTP_200",
        "RUNTIME_INDEXABILITY",
        "PAUSE_OR_REDIRECT_SOURCE_STATE",
        "PUBLICATION_SNAPSHOT_CURRENCY",
        "IMAGE_PUBLICABILITY",
        "AUTH_CACHE_CTA_BEHAVIOR",
        "AFFILIATE_REL",
        "AFFILIATE_REDIRECT_BEHAVIOR",
    }
    request = render_request()
    assert tuple(item.check for item in request.external_assessments) == tuple(
        ExternalCheck
    )
    assert all(
        item.assessor_ref.value.startswith("ASSESSOR-")
        for item in request.external_assessments
    )


@pytest.mark.parametrize(
    "check",
    tuple(ExternalCheck),
)
def test_required_external_fact_not_evaluated_is_never_eligible(
    check: ExternalCheck,
) -> None:
    request = render_request()
    assessments = tuple(
        replace(
            item,
            state=ExternalAssessmentState.NOT_EVALUATED,
            evidence=None,
        )
        if item.check is check
        else item
        for item in request.external_assessments
    )

    result = render_seo(replace(request, external_assessments=assessments))

    assert result.raw_metadata_candidate is request.metadata
    assert result.conditional_local_eligibility is False
    assert result.eligibility_reasons == (
        EligibilityReason.EXTERNAL_ASSESSMENT_NOT_EVALUATED,
    )


def test_external_fail_and_not_evaluated_are_separate_ordered_reasons() -> None:
    request = render_request()
    assessments = list(request.external_assessments)
    assessments[0] = ExternalAssessment(
        ARTICLE_VERSION_ID,
        ExternalCheck.TITLE_UNIQUENESS,
        ExternalAssessmentState.FAIL,
        assessor_for(ExternalCheck.TITLE_UNIQUENESS),
        evidence_for(ExternalCheck.TITLE_UNIQUENESS),
    )
    assessments[1] = ExternalAssessment(
        ARTICLE_VERSION_ID,
        ExternalCheck.CANONICAL_GRAPH,
        ExternalAssessmentState.NOT_EVALUATED,
        assessor_for(ExternalCheck.CANONICAL_GRAPH),
        None,
    )

    result = render_seo(
        replace(request, external_assessments=tuple(reversed(assessments)))
    )

    assert result.eligibility_reasons == (
        EligibilityReason.EXTERNAL_ASSESSMENT_FAILED,
        EligibilityReason.EXTERNAL_ASSESSMENT_NOT_EVALUATED,
    )
    assert tuple(item.check for item in result.external_assessments) == tuple(
        ExternalCheck
    )


def test_input_collection_permutations_have_identical_local_json_and_digest() -> None:
    request = render_request()
    permuted = replace(
        request,
        breadcrumbs=tuple(reversed(request.breadcrumbs)),
        external_assessments=tuple(reversed(request.external_assessments)),
        metadata=replace(
            request.metadata,
            robots=tuple(reversed(request.metadata.robots)),
        ),
    )

    expected = render_seo(request)
    actual = render_seo(permuted)

    assert actual.local_result_json == expected.local_result_json
    assert actual.local_result_digest == expected.local_result_digest


def test_normalized_origin_is_used_without_selecting_a_default() -> None:
    result = render_seo(render_request(origin="https://example.test/"))

    assert result.rendered_metadata is not None
    assert result.rendered_metadata.canonical_url == (
        "https://example.test/guides/coffee-grinders"
    )
    assert '"caller_origin":"https://example.test"' in result.local_result_json

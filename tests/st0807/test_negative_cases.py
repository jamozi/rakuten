"""Fail-closed and hostile-input coverage for ST-0807."""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import datetime
import json

import pytest

from raos.domain.editorial import seo_renderer as domain
from raos.domain.editorial.seo_renderer import (
    SEO_METADATA_SCHEMA_ID,
    ArticleSchemaType,
    AuthorKind,
    BindingField,
    ChangeAssessment,
    ChangeClassification,
    ComparisonResult,
    EligibilityReason,
    ExternalAssessment,
    ExternalAssessmentState,
    ExternalCheck,
    IndexState,
    InputFindingCode,
    JsonValue,
    LocalValidationResult,
    ReferenceId,
    RenderStatus,
    RobotsDirective,
    SeoRenderRequest,
    SeoValueConstructionError,
    Sha256Digest,
    SiteProjection,
    UtcInstant,
    _structured_data_tree_is_valid,
    render_seo,
)

from .support import (
    ARTICLE_VERSION_ID,
    MODIFIED_AT,
    PUBLISHED_AT,
    assessor_for,
    digest_for,
    evidence_for,
    render_request,
)


CANARY = "REJECTED_SECRET_CANARY_ST0807_DO_NOT_ECHO"


def _assert_invalid(
    value: object,
    expected: InputFindingCode,
) -> None:
    result = render_seo(value)
    assert result.status is RenderStatus.INVALID_INPUT
    assert expected in result.input_findings
    assert result.raw_metadata_candidate is None
    assert result.rendered_metadata is None
    assert result.jsonld_json is None
    assert result.structured_data_manifest is None
    assert result.conditional_local_eligibility is False
    assert result.eligibility_reasons == (EligibilityReason.LOCAL_VALIDATION_FAILED,)


def test_rejects_non_request_and_mutable_top_level_collections() -> None:
    _assert_invalid(None, InputFindingCode.INPUT_TYPE_INVALID)

    request = render_request()
    object.__setattr__(request, "breadcrumbs", list(request.breadcrumbs))
    _assert_invalid(request, InputFindingCode.BREADCRUMB_COLLECTION_INVALID)

    request = render_request()
    object.__setattr__(
        request,
        "external_assessments",
        list(request.external_assessments),
    )
    _assert_invalid(request, InputFindingCode.ASSESSMENT_COLLECTION_INVALID)

    request = render_request()
    object.__setattr__(request.metadata, "robots", list(request.metadata.robots))
    _assert_invalid(request, InputFindingCode.ROBOTS_INVALID)


def test_rejects_request_runtime_subclass() -> None:
    class RenderRequestSubclass(SeoRenderRequest):
        pass

    request = render_request()
    subclass = RenderRequestSubclass(
        **{
            field.name: getattr(request, field.name)
            for field in fields(SeoRenderRequest)
        }
    )
    _assert_invalid(subclass, InputFindingCode.INPUT_TYPE_INVALID)


def test_revalidates_tampered_exact_wrappers_and_contract_hashes() -> None:
    request = render_request()
    object.__setattr__(request.contracts.seo_policy_sha256, "value", "0" * 64)
    _assert_invalid(request, InputFindingCode.CONTRACT_BINDING_INVALID)

    request = render_request()
    tampered_reference = ReferenceId("ARTICLE-VERSION-TAMPER")
    object.__setattr__(tampered_reference, "value", "bad id")
    _assert_invalid(
        replace(
            request,
            metadata=replace(
                request.metadata,
                article_version_id=tampered_reference,
            ),
        ),
        InputFindingCode.METADATA_INVALID,
    )

    request = render_request()
    tampered_instant = UtcInstant(request.validated_at.value)
    object.__setattr__(tampered_instant, "value", datetime(2026, 8, 12))
    _assert_invalid(
        replace(request, validated_at=tampered_instant),
        InputFindingCode.VALIDATED_AT_INVALID,
    )


def test_rejects_contract_id_version_and_hash_mismatches() -> None:
    request = render_request()
    candidates = (
        replace(
            request,
            contracts=replace(request.contracts, seo_policy_version="9.9.9"),
        ),
        replace(
            request,
            contracts=replace(
                request.contracts,
                seo_metadata_schema_id=f"{SEO_METADATA_SCHEMA_ID}.wrong",
            ),
        ),
        replace(
            request,
            contracts=replace(
                request.contracts,
                content_test_matrix_sha256=Sha256Digest("0" * 64),
            ),
        ),
    )
    for candidate in candidates:
        _assert_invalid(candidate, InputFindingCode.CONTRACT_BINDING_INVALID)


def test_rejects_article_and_route_coordinate_mismatches() -> None:
    request = render_request()
    other = ReferenceId("ARTICLE-VERSION-OTHER")
    candidates = (
        replace(request, route=replace(request.route, article_version_id=other)),
        replace(request, visible=replace(request.visible, article_version_id=other)),
        replace(request, change=replace(request.change, article_version_id=other)),
        replace(
            request,
            metadata=replace(
                request.metadata,
                canonical_route_ref=ReferenceId("ROUTE-CANONICAL-OTHER"),
            ),
        ),
    )
    for candidate in candidates[:3]:
        _assert_invalid(candidate, InputFindingCode.ARTICLE_BINDING_MISMATCH)
    _assert_invalid(candidates[3], InputFindingCode.ROUTE_MISMATCH)


@pytest.mark.parametrize(
    "origin",
    (
        "http://example.test",
        "https://user@example.test",
        "https://example.test/path",
        "https://example.test?x=1",
        "https://example.test#x",
        "https://example.test:443",
    ),
)
def test_rejects_invalid_origin_without_echo(origin: str) -> None:
    result = render_seo(render_request(origin=origin))
    assert result.status is RenderStatus.INVALID_INPUT
    assert result.input_findings == (InputFindingCode.ORIGIN_INVALID,)
    assert origin not in result.local_result_json


def test_rejects_invalid_mode_schema_author_and_site_shapes() -> None:
    request = render_request()
    object.__setattr__(request, "mode", "PREVIEW")
    _assert_invalid(request, InputFindingCode.MODE_INVALID)

    request = render_request()
    object.__setattr__(request, "article_schema_type", "Article")
    _assert_invalid(request, InputFindingCode.ARTICLE_SCHEMA_TYPE_INVALID)

    request = render_request()
    object.__setattr__(request.visible.author, "kind", "Person")
    _assert_invalid(request, InputFindingCode.AUTHOR_INVALID)

    request = render_request(site_projection=SiteProjection("", "Org", "/"))
    _assert_invalid(request, InputFindingCode.SITE_PROJECTION_INVALID)


def test_rejects_breadcrumb_duplicates_gaps_missing_and_binding_mismatches() -> None:
    request = render_request()
    first, second = request.breadcrumbs
    duplicate = replace(request, breadcrumbs=(first, first))
    gap = replace(
        request,
        breadcrumbs=(replace(first, position=2), replace(second, position=3)),
    )
    missing = replace(request, breadcrumbs=(second,))
    wrong_article = replace(
        request,
        breadcrumbs=(
            first,
            replace(
                second,
                article_version_id=ReferenceId("ARTICLE-VERSION-OTHER"),
            ),
        ),
    )
    wrong_last_route = replace(
        request,
        breadcrumbs=(first, replace(second, route="/different")),
    )
    reversed_refs = replace(
        request,
        metadata=replace(
            request.metadata,
            breadcrumb_refs=tuple(reversed(request.metadata.breadcrumb_refs)),
        ),
    )

    _assert_invalid(duplicate, InputFindingCode.BREADCRUMB_DUPLICATE)
    _assert_invalid(gap, InputFindingCode.BREADCRUMB_POSITION_INVALID)
    _assert_invalid(missing, InputFindingCode.BREADCRUMB_SET_MISMATCH)
    _assert_invalid(wrong_article, InputFindingCode.ARTICLE_BINDING_MISMATCH)
    _assert_invalid(wrong_last_route, InputFindingCode.ROUTE_MISMATCH)
    _assert_invalid(reversed_refs, InputFindingCode.BREADCRUMB_SET_MISMATCH)


def test_rejects_external_assessment_missing_duplicate_unknown_and_bad_proof() -> None:
    request = render_request()
    first = request.external_assessments[0]
    duplicate = replace(
        request,
        external_assessments=(first, first, *request.external_assessments[2:]),
    )
    missing = replace(
        request,
        external_assessments=request.external_assessments[:-1],
    )
    pass_without_proof = replace(
        request,
        external_assessments=(
            replace(first, evidence=None),
            *request.external_assessments[1:],
        ),
    )
    not_evaluated_with_proof = replace(
        request,
        external_assessments=(
            ExternalAssessment(
                ARTICLE_VERSION_ID,
                first.check,
                ExternalAssessmentState.NOT_EVALUATED,
                assessor_for(first.check),
                evidence_for(first.check),
            ),
            *request.external_assessments[1:],
        ),
    )
    wrong_article = replace(
        request,
        external_assessments=(
            replace(
                first,
                article_version_id=ReferenceId("ARTICLE-VERSION-OTHER"),
            ),
            *request.external_assessments[1:],
        ),
    )
    unknown = render_request()
    object.__setattr__(unknown.external_assessments[0], "check", "UNKNOWN")
    invalid_assessor = render_request()
    object.__setattr__(
        invalid_assessor.external_assessments[0],
        "assessor_ref",
        None,
    )

    _assert_invalid(duplicate, InputFindingCode.ASSESSMENT_DUPLICATE)
    _assert_invalid(missing, InputFindingCode.ASSESSMENT_SET_MISMATCH)
    _assert_invalid(pass_without_proof, InputFindingCode.ASSESSMENT_PROOF_INVALID)
    _assert_invalid(
        not_evaluated_with_proof,
        InputFindingCode.ASSESSMENT_PROOF_INVALID,
    )
    _assert_invalid(wrong_article, InputFindingCode.ARTICLE_BINDING_MISMATCH)
    _assert_invalid(unknown, InputFindingCode.ASSESSMENT_RECORD_INVALID)
    _assert_invalid(invalid_assessor, InputFindingCode.ASSESSMENT_RECORD_INVALID)


@pytest.mark.parametrize("missing_check", tuple(ExternalCheck))
def test_every_external_assessment_coordinate_is_required_exactly_once(
    missing_check: ExternalCheck,
) -> None:
    request = render_request()
    missing = tuple(
        item for item in request.external_assessments if item.check is not missing_check
    )

    result = render_seo(replace(request, external_assessments=missing))

    assert result.status is RenderStatus.INVALID_INPUT
    assert InputFindingCode.ASSESSMENT_SET_MISMATCH in result.input_findings
    assert result.conditional_local_eligibility is False


@pytest.mark.parametrize("state", tuple(ExternalAssessmentState))
def test_assessor_reference_is_required_for_every_assessment_state(
    state: ExternalAssessmentState,
) -> None:
    request = render_request(assessment_state=state)
    object.__setattr__(request.external_assessments[0], "assessor_ref", None)

    _assert_invalid(request, InputFindingCode.ASSESSMENT_RECORD_INVALID)


def test_prohibited_reference_and_value_errors_are_closed_and_redacted() -> None:
    with pytest.raises(SeoValueConstructionError) as caught:
        ReferenceId(f"{CANARY} invalid")
    assert CANARY not in f"{caught.value!s} {caught.value!r}"

    request = render_request()
    prohibited = ReferenceId("SECRET-TOKEN-REFERENCE")
    result = render_seo(
        replace(
            request,
            metadata=replace(request.metadata, seo_metadata_id=prohibited),
        )
    )
    assert InputFindingCode.PROHIBITED_INPUT in result.input_findings
    assert prohibited.value not in result.local_result_json
    assert CANARY not in f"{request!s} {request!r} {result!s} {result!r}"


def test_hostile_visible_strings_are_data_and_script_context_safe() -> None:
    hostile = "</script><script>alert('x')</script> & <b>"
    request = render_request()
    request = replace(
        request,
        metadata=replace(
            request.metadata,
            title=hostile,
            meta_description=f"{hostile} description",
        ),
        visible=replace(request.visible, title=hostile, h1=hostile),
        breadcrumbs=(
            request.breadcrumbs[0],
            replace(request.breadcrumbs[1], name=hostile),
        ),
    )

    result = render_seo(request)

    assert result.status is RenderStatus.RENDERED_LOCAL
    assert result.jsonld_json is not None
    assert "<" not in result.jsonld_json
    assert ">" not in result.jsonld_json
    assert "&" not in result.jsonld_json
    assert "\\u003c" in result.jsonld_json
    assert json.loads(result.jsonld_json)["@graph"][0]["headline"] == hostile
    assert "<" not in result.local_result_json
    assert ">" not in result.local_result_json
    assert "&" not in result.local_result_json


@pytest.mark.parametrize(
    "prohibited_type",
    ("Product", "Offer", "FAQPage", "Review", "AggregateRating"),
)
def test_recursive_validator_rejects_every_forbidden_type(
    prohibited_type: str,
) -> None:
    value = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "author": {"@type": "Person", "name": "Visible"},
                "itemListElement": [{"@type": prohibited_type}],
            }
        ],
    }
    assert not _structured_data_tree_is_valid(
        value,
        expected_author={"@type": "Person", "name": "Visible"},
    )


@pytest.mark.parametrize(
    "property_name",
    (
        "price",
        "availability",
        "rating",
        "aggregateRating",
        "review",
        "reviewBody",
        "offers",
        "description",
        "image",
        "publisher",
        "logo",
        "sameAs",
        "keywords",
    ),
)
def test_recursive_validator_rejects_invisible_or_unbound_properties(
    property_name: str,
) -> None:
    value = {
        "@type": "Article",
        "author": {"@type": "Person", "name": "Visible"},
        property_name: "not visibly bound",
    }
    assert not _structured_data_tree_is_valid(
        value,
        expected_author={"@type": "Person", "name": "Visible"},
    )


def test_recursive_validator_rejects_author_shape_or_kind_inference() -> None:
    expected: dict[str, JsonValue] = {
        "@type": "Person",
        "name": "Visible",
    }
    wrong = {
        "@type": "Article",
        "author": {"@type": "Organization", "name": "Visible"},
    }
    assert not _structured_data_tree_is_valid(wrong, expected_author=expected)


def test_current_canonical_route_mismatch_is_retained_as_local_failure() -> None:
    request = render_request()
    request = replace(
        request,
        route=replace(request.route, current_route="/old-route"),
        breadcrumbs=(
            request.breadcrumbs[0],
            replace(request.breadcrumbs[1], route="/old-route"),
        ),
    )

    result = render_seo(request)

    assert result.status is RenderStatus.RENDERED_LOCAL
    assert result.input_findings == ()
    assert result.raw_metadata_candidate is request.metadata
    assert result.structured_data_manifest is not None
    assert result.structured_data_manifest.validation_result is (
        LocalValidationResult.FAIL
    )
    route_entry = next(
        item
        for item in result.binding_ledger
        if item.field is BindingField.CANONICAL_ROUTE
    )
    assert route_entry.result is ComparisonResult.MISMATCH
    assert result.eligibility_reasons == (EligibilityReason.ROUTE_MISMATCH,)


@pytest.mark.parametrize(
    "unapproved_property",
    (
        "schema:offers",
        "https://schema.org/review",
        "priceSpecification",
        "sponsor",
        "unknownProperty",
    ),
)
def test_recursive_validator_rejects_alias_and_unknown_properties(
    unapproved_property: str,
) -> None:
    value = {
        "@type": "Article",
        "author": {"@type": "Person", "name": "Visible"},
        unapproved_property: "unbound",
    }
    assert not _structured_data_tree_is_valid(
        value,
        expected_author={"@type": "Person", "name": "Visible"},
    )


@pytest.mark.parametrize(
    ("fault", "expected_field"),
    (
        ("headline", BindingField.JSONLD_HEADLINE),
        ("date_published", BindingField.JSONLD_DATE_PUBLISHED),
        ("date_modified", BindingField.JSONLD_DATE_MODIFIED),
        ("author", BindingField.JSONLD_AUTHOR),
        ("article_type", BindingField.JSONLD_SCHEMA_TYPE),
        ("canonical_url", BindingField.JSONLD_CANONICAL_URL),
        ("main_entity", BindingField.JSONLD_CANONICAL_URL),
        ("breadcrumb_name", BindingField.BREADCRUMB_NAME),
        ("breadcrumb_url", BindingField.BREADCRUMB_ROUTE),
        ("breadcrumb_position", BindingField.BREADCRUMB_POSITION),
        ("breadcrumb_position_bool", BindingField.BREADCRUMB_POSITION),
        ("node_order", BindingField.JSONLD_PROFILE_SHAPE),
        ("site_organization", BindingField.JSONLD_PROFILE_SHAPE),
        ("site_website", BindingField.JSONLD_PROFILE_SHAPE),
        ("extra_node", BindingField.JSONLD_PROFILE_SHAPE),
        ("missing_node", BindingField.JSONLD_PROFILE_SHAPE),
        ("breadcrumb_type", BindingField.JSONLD_PROFILE_SHAPE),
        ("list_item_type", BindingField.JSONLD_PROFILE_SHAPE),
        ("enabled_types", BindingField.JSONLD_PROFILE_SHAPE),
        ("context", BindingField.JSONLD_PROFILE_SHAPE),
        ("allowed_key_wrong_node", BindingField.JSONLD_PROFILE_SHAPE),
    ),
)
def test_post_generation_profile_validation_fails_closed_on_value_or_shape_fault(
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
    expected_field: BindingField,
) -> None:
    request = render_request(
        site_projection=SiteProjection("Example Site", "Example Org", "/")
    )
    original = domain._build_jsonld

    def faulted_build(
        value: SeoRenderRequest,
        *,
        origin: str | None,
        breadcrumbs: tuple[domain.BreadcrumbProjection, ...],
    ) -> tuple[dict[str, JsonValue], tuple[str, ...]]:
        document, enabled = original(value, origin=origin, breadcrumbs=breadcrumbs)
        graph = document["@graph"]
        assert type(graph) is list
        article = graph[0]
        breadcrumb = graph[1]
        organization = graph[2]
        website = graph[3]
        assert type(article) is dict
        assert type(breadcrumb) is dict
        assert type(organization) is dict
        assert type(website) is dict
        items = breadcrumb["itemListElement"]
        assert type(items) is list
        first_item = items[0]
        assert type(first_item) is dict
        if fault == "headline":
            article["headline"] = "wrong"
        elif fault == "date_published":
            article["datePublished"] = "2026-01-01T00:00:00.000000Z"
        elif fault == "date_modified":
            article["dateModified"] = "2026-01-02T00:00:00.000000Z"
        elif fault == "author":
            article["author"] = {"@type": "Person", "name": "wrong"}
        elif fault == "article_type":
            article["@type"] = "BlogPosting"
        elif fault == "canonical_url":
            article["url"] = "https://example.test/wrong"
        elif fault == "main_entity":
            article["mainEntityOfPage"] = "https://example.test/wrong"
        elif fault == "breadcrumb_name":
            first_item["name"] = "wrong"
        elif fault == "breadcrumb_url":
            first_item["item"] = "https://example.test/wrong"
        elif fault == "breadcrumb_position":
            first_item["position"] = 2
        elif fault == "breadcrumb_position_bool":
            first_item["position"] = True
        elif fault == "node_order":
            graph[0], graph[1] = graph[1], graph[0]
        elif fault == "site_organization":
            organization["name"] = "wrong"
        elif fault == "site_website":
            website["url"] = "https://example.test/wrong"
        elif fault == "extra_node":
            graph.append(
                {"@type": "WebSite", "name": "extra", "url": "https://example.test/"}
            )
        elif fault == "missing_node":
            graph.pop()
        elif fault == "breadcrumb_type":
            breadcrumb["@type"] = "WebSite"
        elif fault == "list_item_type":
            first_item["@type"] = "Person"
        elif fault == "enabled_types":
            enabled = tuple(item for item in enabled if item != "WebSite")
        elif fault == "context":
            document["@context"] = "https://example.test/schema"
        else:
            article["position"] = 1
        return document, enabled

    monkeypatch.setattr(domain, "_build_jsonld", faulted_build)
    result = render_seo(request)

    assert result.structured_data_manifest is not None
    assert result.structured_data_manifest.validation_result is (
        LocalValidationResult.FAIL
    )
    assert result.conditional_local_eligibility is False
    assert EligibilityReason.VISIBLE_BINDING_MISMATCH in result.eligibility_reasons
    assert EligibilityReason.LOCAL_VALIDATION_FAILED in result.eligibility_reasons
    profile = next(
        item
        for item in result.binding_ledger
        if item.field is BindingField.JSONLD_PROFILE_SHAPE
    )
    assert profile.result is ComparisonResult.MISMATCH
    relevant = [item for item in result.binding_ledger if item.field is expected_field]
    assert relevant
    assert any(item.result is ComparisonResult.MISMATCH for item in relevant)


def test_visible_title_mismatch_is_retained_as_local_failure() -> None:
    request = render_request()
    request = replace(
        request,
        visible=replace(
            request.visible, title="異なる可視タイトル", h1="異なる可視タイトル"
        ),
    )

    result = render_seo(request)

    assert result.status is RenderStatus.RENDERED_LOCAL
    assert result.raw_metadata_candidate is request.metadata
    assert result.structured_data_manifest is not None
    assert result.structured_data_manifest.validation_result is (
        LocalValidationResult.FAIL
    )
    assert result.eligibility_reasons == (EligibilityReason.VISIBLE_BINDING_MISMATCH,)


def test_public_noindex_intent_is_valid_only_with_matching_robots_and_sitemap() -> None:
    request = render_request()
    valid_metadata = replace(
        request.metadata,
        index_state=IndexState.NOINDEX,
        robots=(RobotsDirective.NOINDEX, RobotsDirective.FOLLOW),
        sitemap_inclusion=False,
    )
    valid = render_seo(replace(request, metadata=valid_metadata))
    assert valid.conditional_local_eligibility is True
    assert valid.structured_data_manifest is not None
    assert valid.structured_data_manifest.validation_result is (
        LocalValidationResult.PASS
    )

    inconsistent = render_seo(
        replace(
            request,
            metadata=replace(valid_metadata, sitemap_inclusion=True),
        )
    )
    assert inconsistent.status is RenderStatus.RENDERED_LOCAL
    assert inconsistent.raw_metadata_candidate is not None
    assert inconsistent.conditional_local_eligibility is False
    assert inconsistent.eligibility_reasons == (
        EligibilityReason.INDEX_INTENT_INCONSISTENT,
    )
    assert inconsistent.structured_data_manifest is not None
    assert inconsistent.structured_data_manifest.validation_result is (
        LocalValidationResult.FAIL
    )


def test_price_only_and_none_change_keep_lastmod_unchanged() -> None:
    request = render_request()
    for classification in (
        ChangeClassification.PRICE_ONLY,
        ChangeClassification.NONE,
    ):
        result = render_seo(
            replace(
                request,
                change=ChangeAssessment(
                    ARTICLE_VERSION_ID,
                    classification,
                    MODIFIED_AT,
                ),
            )
        )
        assert result.conditional_local_eligibility is True
        assert result.rendered_metadata is not None
        assert result.rendered_metadata.substantive_updated_at is MODIFIED_AT


def test_price_only_change_cannot_advance_lastmod() -> None:
    request = render_request()
    result = render_seo(
        replace(
            request,
            change=ChangeAssessment(
                ARTICLE_VERSION_ID,
                ChangeClassification.PRICE_ONLY,
                PUBLISHED_AT,
            ),
        )
    )
    assert result.status is RenderStatus.INVALID_INPUT
    assert InputFindingCode.LASTMOD_INVALID in result.input_findings


def test_initial_and_substantive_change_require_explicit_lastmod_shapes() -> None:
    request = render_request()
    initial = render_seo(
        replace(
            request,
            change=ChangeAssessment(
                ARTICLE_VERSION_ID,
                ChangeClassification.INITIAL_PUBLICATION,
                None,
            ),
        )
    )
    assert initial.conditional_local_eligibility is True

    invalid = render_seo(
        replace(
            request,
            change=ChangeAssessment(
                ARTICLE_VERSION_ID,
                ChangeClassification.SUBSTANTIVE,
                None,
            ),
        )
    )
    assert invalid.status is RenderStatus.INVALID_INPUT
    assert InputFindingCode.LASTMOD_INVALID in invalid.input_findings


def test_external_ct_oracle_states_never_execute_redirect_link_or_corpus_checks() -> (
    None
):
    request = render_request()
    assessments = tuple(
        replace(
            item,
            state=(
                ExternalAssessmentState.FAIL
                if item.check
                in {
                    ExternalCheck.CANONICAL_GRAPH,
                    ExternalCheck.AFFILIATE_REL,
                    ExternalCheck.AFFILIATE_REDIRECT_BEHAVIOR,
                }
                else item.state
            ),
        )
        for item in request.external_assessments
    )
    result = render_seo(replace(request, external_assessments=assessments))

    assert result.status is RenderStatus.RENDERED_LOCAL
    assert result.raw_metadata_candidate is request.metadata
    assert result.conditional_local_eligibility is False
    assert result.eligibility_reasons == (EligibilityReason.EXTERNAL_ASSESSMENT_FAILED,)
    assert result.publication_authorized is False
    assert result.production_eligible is False


def test_digest_binds_explicit_type_origin_author_route_and_external_proof() -> None:
    request = render_request()
    expected = render_seo(request).local_result_digest
    first_assessment = request.external_assessments[0]
    assert first_assessment.evidence is not None
    variants = (
        replace(request, article_schema_type=ArticleSchemaType.BLOG_POSTING),
        replace(request, caller_origin="https://other.example.test"),
        replace(
            request,
            visible=replace(
                request.visible,
                author=replace(
                    request.visible.author,
                    kind=AuthorKind.ORGANIZATION,
                ),
            ),
        ),
        replace(
            request,
            external_assessments=(
                replace(
                    first_assessment,
                    evidence=replace(
                        first_assessment.evidence,
                        sha256=digest_for("different-external-proof"),
                    ),
                ),
                *request.external_assessments[1:],
            ),
        ),
        replace(
            request,
            external_assessments=(
                replace(
                    first_assessment,
                    assessor_ref=ReferenceId("ASSESSOR-ALTERNATE-0807"),
                ),
                *request.external_assessments[1:],
            ),
        ),
    )
    assert render_seo(variants[0]).local_result_digest != expected
    assert render_seo(variants[1]).local_result_digest != expected
    assert render_seo(variants[2]).local_result_digest != expected
    assert render_seo(variants[3]).local_result_digest != expected
    assert render_seo(variants[4]).local_result_digest != expected


def test_visible_content_hash_is_opaque_provenance_not_recomputed() -> None:
    request = render_request()
    opaque = digest_for("caller-opaque-visible-hash")
    result = render_seo(
        replace(
            request,
            visible=replace(request.visible, visible_content_hash=opaque),
        )
    )
    assert result.structured_data_manifest is not None
    assert result.structured_data_manifest.visible_content_hash is opaque
    assert result.conditional_local_eligibility is True

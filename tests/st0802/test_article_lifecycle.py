"""Focused positive and authorization-denial behavior for ST-0802."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
import hashlib

import pytest

from raos.domain.editorial.article_lifecycle import (
    PLAN_TYPE_TO_CONTENT_AST_TYPE,
    ArticleLifecycleMode,
    ArticleLifecycleOperation,
    ArticleLifecycleFailure,
    ArticleLifecycleFailureCode,
    ArticleState,
    ArticleVersionHistory,
    ArticleVersionState,
    BodySha256,
    CreateArticleOutcome,
    GetArticleOutcome,
    LifecycleDecision,
    LifecycleExecution,
    VersionSnapshot,
)
from raos.domain.editorial.article_plan import ArticlePlanType
from raos.domain.editorial.content_ast import ArticleType, dump_content_ast_json
from raos.domain.portfolio.workflow import EntityVersion, IdempotencyKey, StrongEtag
from raos.domain.portfolio.workflow import PortfolioWorkflowFailure

from .support import (
    ACTION_BY_OPERATION,
    ARTICLE_ID,
    SITE_ID,
    create_request,
    create_service,
    grant,
    grant_for,
    lifecycle_case,
    service_for,
    version_snapshot,
)


def test_create_from_plan_is_recorded_and_never_ready() -> None:
    result = create_service().execute(grant=grant(), request=create_request())

    assert result.execution is LifecycleExecution.RECORDED_ONLY
    assert result.persistence is LifecycleExecution.NOT_EXECUTED
    assert result.source_packet_verification is LifecycleExecution.NOT_EXECUTED
    assert result.formal_verification is LifecycleExecution.NOT_EXECUTED
    assert result.decision is LifecycleDecision.NOT_READY


def test_authorization_denial_does_not_consume_exchange() -> None:
    service = create_service()
    request = create_request()

    with pytest.raises(ArticleLifecycleFailure) as captured:
        service.execute(grant=grant(action="editorial:article:read"), request=request)
    assert captured.value.code is ArticleLifecycleFailureCode.NOT_AUTHORIZED

    result = service.execute(grant=grant(), request=request)
    assert result.execution is LifecycleExecution.RECORDED_ONLY


@pytest.mark.parametrize("operation", tuple(ArticleLifecycleOperation))
def test_all_seven_operations_are_one_recorded_exchange(
    operation: ArticleLifecycleOperation,
) -> None:
    request, outcome = lifecycle_case(operation)
    service, _ = service_for(request, outcome)

    result = service.execute(grant=grant_for(request), request=request)

    assert result.operation is operation
    assert result.outcome is outcome
    assert result.decision is LifecycleDecision.NOT_READY
    with pytest.raises(ArticleLifecycleFailure) as exhausted:
        service.execute(grant=grant_for(request), request=request)
    assert (
        exhausted.value.code is ArticleLifecycleFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
    )


def test_operation_and_action_vocabularies_are_exact() -> None:
    assert tuple(value.value for value in ArticleLifecycleOperation) == (
        "ED-005",
        "ED-006",
        "ED-007",
        "ED-008",
        "ED-009",
        "ED-010",
        "ED-011",
    )
    assert set(ACTION_BY_OPERATION) == set(ArticleLifecycleOperation)


def test_article_and_version_state_vocabularies_are_exact() -> None:
    assert tuple(value.value for value in ArticleState) == (
        "IDEA",
        "PLANNED",
        "SOURCES_PENDING",
        "PACKET_READY",
        "GENERATING",
        "DRAFT",
        "AUTO_REVIEW",
        "HUMAN_REVIEW",
        "APPROVED",
        "SCHEDULED",
        "PUBLISHED",
        "UPDATE_PENDING",
        "PAUSED",
        "ARCHIVED",
    )
    assert tuple(value.value for value in ArticleVersionState) == (
        "DRAFT",
        "AUTO_REVIEW",
        "HUMAN_REVIEW",
        "APPROVED",
        "REJECTED",
        "SUPERSEDED",
    )


def test_plan_type_to_content_ast_mapping_is_exact() -> None:
    assert PLAN_TYPE_TO_CONTENT_AST_TYPE == {
        ArticlePlanType.SELECTION_GUIDE: ArticleType.selection_guide,
        ArticlePlanType.USE_CASE_RECOMMENDATION: ArticleType.use_case_recommendation,
        ArticlePlanType.PRODUCT_COMPARISON: ArticleType.product_comparison,
        ArticlePlanType.MODEL_DIFFERENCE: (
            ArticleType.model_generation_capacity_difference
        ),
        ArticlePlanType.CONDITION_FILTER: ArticleType.condition_filtering,
    }


def test_body_hash_uses_exact_st0801_deterministic_serialization() -> None:
    version = version_snapshot()
    rendered = dump_content_ast_json(version.content_ast).encode("utf-8")
    assert version.body_sha256 == BodySha256(hashlib.sha256(rendered).hexdigest())
    assert BodySha256.of(version.content_ast) == BodySha256.of(version.content_ast)


@pytest.mark.parametrize("state", tuple(ArticleState)[1:])
def test_article_transitions_are_disabled(state: ArticleState) -> None:
    _, outcome = lifecycle_case(ArticleLifecycleOperation.GET_ARTICLE)
    assert isinstance(outcome, GetArticleOutcome)
    with pytest.raises(ArticleLifecycleFailure):
        replace(outcome.article, state=state)


@pytest.mark.parametrize("state", tuple(ArticleVersionState)[1:])
def test_version_transitions_are_disabled(state: ArticleVersionState) -> None:
    with pytest.raises(ArticleLifecycleFailure):
        replace(version_snapshot(), state=state)


def _replace_title(value: VersionSnapshot) -> VersionSnapshot:
    return replace(value, title="Different title")


def _replace_type(value: VersionSnapshot) -> VersionSnapshot:
    return replace(value, article_type=ArticlePlanType.PRODUCT_COMPARISON)


def _replace_hash(value: VersionSnapshot) -> VersionSnapshot:
    return replace(value, body_sha256=BodySha256("0" * 64))


@pytest.mark.parametrize("mutator", (_replace_title, _replace_type, _replace_hash))
def test_ast_and_version_binding_tamper_is_rejected(
    mutator: Callable[[VersionSnapshot], VersionSnapshot],
) -> None:
    with pytest.raises(ArticleLifecycleFailure):
        mutator(version_snapshot())


def test_history_rejects_duplicate_or_non_increasing_versions() -> None:
    version = version_snapshot()
    with pytest.raises(ArticleLifecycleFailure):
        ArticleVersionHistory(
            article_id=ARTICLE_ID,
            versions=(version, version),
        )
    second = version_snapshot()
    object.__setattr__(second, "version_no", 0)
    with pytest.raises(ArticleLifecycleFailure):
        ArticleVersionHistory(article_id=ARTICLE_ID, versions=(version, second))


def test_reused_st0501_version_etag_and_idempotency_types_remain_strict() -> None:
    constructors = (
        lambda: EntityVersion(True),
        lambda: EntityVersion(-1),
        lambda: StrongEtag("weak-or-unquoted"),
        lambda: IdempotencyKey("short"),
    )
    for constructor in constructors:
        with pytest.raises(PortfolioWorkflowFailure):
            constructor()


@pytest.mark.parametrize("environment", ("ENV-STAGING", "ENV-PRODUCTION"))
def test_external_runtime_names_are_not_lifecycle_modes(environment: str) -> None:
    assert environment not in {value.value for value in ArticleLifecycleMode}


def test_initial_records_have_no_review_approval_publication_or_current_marker() -> (
    None
):
    _, outcome = lifecycle_case(ArticleLifecycleOperation.CREATE_ARTICLE)
    assert isinstance(outcome, CreateArticleOutcome)
    assert outcome.article.current_version_id is None
    assert outcome.article.published_version_id is None
    assert outcome.article.archived_at is None
    assert outcome.article.approval_id is None
    assert outcome.article.publication_id is None
    assert outcome.initial_version.submitted_at is None
    assert outcome.initial_version.reviewed_at is None
    assert outcome.initial_version.approved_at is None
    assert outcome.initial_version.published_at is None


def test_wrong_site_or_resource_grant_is_rejected_without_consuming_script() -> None:
    request, outcome = lifecycle_case(ArticleLifecycleOperation.GET_ARTICLE)
    service, _ = service_for(request, outcome)
    other = type(SITE_ID)("018f3e90-7b00-7000-8000-000000000199")
    with pytest.raises(ArticleLifecycleFailure):
        service.execute(
            grant=grant(
                action="editorial:article:read",
                site_id=other,
                resource_id=request.target.resource_id,
            ),
            request=request,
        )
    observed = service.execute(grant=grant_for(request), request=request)
    assert observed.outcome is outcome

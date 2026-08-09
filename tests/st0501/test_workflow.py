"""Hostile behavior matrix for the closed ST-0501 workflow seam."""

from __future__ import annotations

from dataclasses import replace
import pickle
from typing import Callable
from uuid import UUID

import pytest

from raos.adapters.recorded_portfolio_workflow import (
    RecordedPortfolioWorkflowExchange,
    RecordedWorkflowStep,
)
from raos.application.portfolio.workflow import PortfolioWorkflowService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.editorial.article_plan import (
    ARTICLE_PLAN_TRANSITIONS,
    ArticlePlanState,
    ArticlePlanType,
)
from raos.domain.portfolio.workflow import (
    Category,
    CategoryRisk,
    CategoryStage,
    CreateCategoryOutcome,
    DisplayId,
    EntityVersion,
    IdempotencyKey,
    IntentType,
    KeywordStatus,
    OutcomeDisposition,
    PageCursor,
    PageLimit,
    PortfolioOperation,
    PortfolioRecordStatus,
    PortfolioWorkflowFailure,
    PortfolioWorkflowFailureCode,
    StrongEtag,
    WorkflowTarget,
)
from raos.domain.iam.authorization import AuthorizationGrant
from raos.ports.portfolio_workflow import PortfolioWorkflowExchange

from conftest import (
    ACTION_BY_OPERATION,
    CATEGORY_A,
    NOW,
    SITE_A,
    authorization_grant,
    category,
    category_outcome,
    category_request,
    category_service,
    category_values,
    grant_for,
    plan_values,
    service_for,
    workflow_case,
)


OTHER = UUID("018f3e90-7b00-7000-8000-000000000099")
REJECTED_CANARY = "REJECTED_VALUE_CANARY_ST0501_DO_NOT_ECHO"


@pytest.mark.parametrize("operation", tuple(PortfolioOperation))
def test_all_sixteen_operation_mappings_exchange_exactly_once(
    operation: PortfolioOperation,
) -> None:
    request, expected = workflow_case(operation)
    service, adapter = service_for(request, expected)

    observed = service.execute(grant=grant_for(request), request=request)

    assert observed is expected
    assert tuple(event.operation for event in adapter.history) == (operation,)
    assert adapter.remaining == 0


def test_operation_ids_and_authorization_actions_are_closed() -> None:
    assert tuple(member.value for member in PortfolioOperation) == (
        "CATG-001",
        "CATG-002",
        "CATG-003",
        "CATG-004",
        "INTENT-001",
        "INTENT-002",
        "INTENT-003",
        "INTENT-004",
        "KEY-001",
        "KEY-002",
        "KEY-003",
        "KEY-004",
        "ED-001",
        "ED-002",
        "ED-003",
        "ED-004",
    )
    assert set(ACTION_BY_OPERATION) == set(PortfolioOperation)


@pytest.mark.parametrize(
    "grant",
    (
        lambda: authorization_grant(action="portfolio:category:read"),
        lambda: authorization_grant(site_id=OTHER),
        lambda: authorization_grant(resource_id=OTHER),
    ),
)
def test_authorization_denial_occurs_before_exchange(
    grant: Callable[[], AuthorizationGrant],
) -> None:
    service, adapter = category_service()

    with pytest.raises(PortfolioWorkflowFailure) as caught:
        service.execute(grant=grant(), request=category_request())

    assert caught.value.code is PortfolioWorkflowFailureCode.NOT_AUTHORIZED
    assert adapter.history == ()
    assert adapter.remaining == 1


def test_exact_scalar_boundaries_reject_hostile_values() -> None:
    cases: tuple[Callable[[], object], ...] = (
        lambda: EntityVersion(True),
        lambda: EntityVersion(-1),
        lambda: PageLimit(True),
        lambda: PageLimit(0),
        lambda: PageLimit(201),
        lambda: StrongEtag('W/"weak"'),
        lambda: StrongEtag("unquoted"),
        lambda: IdempotencyKey("short"),
        lambda: IdempotencyKey("contains space"),
        lambda: PageCursor(""),
        lambda: PageCursor("x" * 1025),
    )
    for constructor in cases:
        with pytest.raises(PortfolioWorkflowFailure):
            constructor()


def test_display_id_rejects_noncanonical_prefix_or_shape() -> None:
    for value in ("KEY-TEST", "PLN-TEST", "cat-TEST", "CAT_ABC", "CAT-"):
        with pytest.raises(PortfolioWorkflowFailure):
            DisplayId(value)


def test_uuid7_and_test_only_target_are_exact() -> None:
    with pytest.raises(PortfolioWorkflowFailure):
        WorkflowTarget(environment="TEST_ONLY", site_id=UUID(int=1), resource_id=SITE_A)
    with pytest.raises(PortfolioWorkflowFailure):
        WorkflowTarget(environment="ENV-DEV", site_id=SITE_A, resource_id=SITE_A)


def test_canonical_enum_vocabularies_are_exact() -> None:
    assert {value.value for value in CategoryRisk} == {
        "LOW",
        "MEDIUM",
        "HIGH",
        "PROHIBITED",
    }
    assert {value.value for value in CategoryStage} == {
        "CANDIDATE",
        "RESEARCH",
        "APPROVED",
        "ACTIVE",
        "PAUSED",
        "RETIRED",
        "REJECTED",
    }
    assert {value.value for value in IntentType} == {
        "SELECTION_GUIDE",
        "USE_CASE",
        "COMPARISON",
        "MODEL_DIFFERENCE",
        "CONDITION_FILTER",
        "INFORMATIONAL_SUPPORT",
    }
    assert {value.value for value in PortfolioRecordStatus} == {
        "ACTIVE",
        "PAUSED",
        "RETIRED",
    }
    assert {value.value for value in KeywordStatus} == {
        "ACTIVE",
        "PAUSED",
        "RETIRED",
        "BLOCKED",
    }
    assert {value.value for value in ArticlePlanType} == {
        "SELECTION_GUIDE",
        "USE_CASE_RECOMMENDATION",
        "PRODUCT_COMPARISON",
        "MODEL_DIFFERENCE",
        "CONDITION_FILTER",
    }
    assert {value.value for value in ArticlePlanState} == {
        "IDEA",
        "PLANNED",
        "SOURCES_PENDING",
        "PACKET_READY",
        "GENERATING",
        "DRAFT",
        "IN_REVIEW",
        "APPROVED",
        "CANCELLED",
        "ARCHIVED",
    }


@pytest.mark.parametrize("stage", (CategoryStage.APPROVED, CategoryStage.ACTIVE))
def test_category_approval_states_are_disabled_without_evidence(
    stage: CategoryStage,
) -> None:
    values = category_values()
    with pytest.raises(PortfolioWorkflowFailure):
        replace(values, stage=stage)


def test_category_rejects_self_parent_and_bool_limit() -> None:
    with pytest.raises(PortfolioWorkflowFailure):
        replace(category_values(), article_limit=True)
    with pytest.raises(PortfolioWorkflowFailure):
        replace(
            category(), values=replace(category_values(), parent_category_id=CATEGORY_A)
        )


def test_evidence_dependent_article_plan_states_remain_disabled() -> None:
    for state in ArticlePlanState:
        if state is ArticlePlanState.IDEA:
            continue
        with pytest.raises(PortfolioWorkflowFailure):
            replace(plan_values(), state=state)


def test_article_plan_graph_is_canonical_but_not_executable() -> None:
    assert (ArticlePlanState.IDEA, ArticlePlanState.PLANNED) in ARTICLE_PLAN_TRANSITIONS
    assert (
        ArticlePlanState.IN_REVIEW,
        ArticlePlanState.APPROVED,
    ) in ARTICLE_PLAN_TRANSITIONS
    assert all(type(row) is tuple and len(row) == 2 for row in ARTICLE_PLAN_TRANSITIONS)


@pytest.mark.parametrize(
    "disposition", (OutcomeDisposition.NOOP, OutcomeDisposition.REPLAYED)
)
def test_update_noop_and_replay_preserve_version_and_etag(
    disposition: OutcomeDisposition,
) -> None:
    request, _ = workflow_case(PortfolioOperation.UPDATE_CATEGORY)
    unchanged = category(version=0, etag='"category-v0"')
    outcome = CreateCategoryOutcome(unchanged, OutcomeDisposition.REPLAYED)
    # Reconstruct the operation-specific outcome; create outcomes are rejected
    # by the service even when their payload happens to be valid.
    from raos.domain.portfolio.workflow import UpdateCategoryOutcome

    exact = UpdateCategoryOutcome(unchanged, disposition)
    service, _ = service_for(request, exact)
    assert service.execute(grant=grant_for(request), request=request) is exact
    assert outcome.operation is PortfolioOperation.CREATE_CATEGORY


def test_update_rejects_version_or_etag_drift() -> None:
    from raos.domain.portfolio.workflow import UpdateCategoryOutcome

    request, _ = workflow_case(PortfolioOperation.UPDATE_CATEGORY)
    cases = (
        UpdateCategoryOutcome(
            category(version=0, etag='"category-v1"'), OutcomeDisposition.NOOP
        ),
        UpdateCategoryOutcome(
            category(version=1, etag='"category-v0"'), OutcomeDisposition.UPDATED
        ),
    )
    for outcome in cases:
        service, _ = service_for(request, outcome)
        with pytest.raises(PortfolioWorkflowFailure) as caught:
            service.execute(grant=grant_for(request), request=request)
        assert caught.value.code is PortfolioWorkflowFailureCode.OUTCOME_MISMATCH


def test_outcome_id_and_site_drift_fail_closed() -> None:
    request, _ = workflow_case(PortfolioOperation.GET_CATEGORY)
    wrong_id = Category(
        category_id=OTHER,
        display_id=DisplayId("CAT-OTHER"),
        site_id=SITE_A,
        values=category_values(),
        version=EntityVersion(0),
        etag=StrongEtag('"other-v0"'),
        created_at=NOW,
        updated_at=NOW,
    )
    from raos.domain.portfolio.workflow import GetCategoryOutcome

    service, _ = service_for(
        request, GetCategoryOutcome(wrong_id, OutcomeDisposition.FOUND)
    )
    with pytest.raises(PortfolioWorkflowFailure) as caught:
        service.execute(grant=grant_for(request), request=request)
    assert caught.value.code is PortfolioWorkflowFailureCode.OUTCOME_MISMATCH


class _ExplodingExchange:
    def exchange(self, request: object) -> object:
        del request
        raise RuntimeError(REJECTED_CANARY)


class _WrongOutcomeExchange:
    def exchange(self, request: object) -> object:
        del request
        return category_outcome()


@pytest.mark.parametrize("exchange", (_ExplodingExchange(), _WrongOutcomeExchange()))
def test_collaborator_failure_is_sanitized(
    exchange: PortfolioWorkflowExchange,
) -> None:
    request, _ = workflow_case(PortfolioOperation.GET_CATEGORY)
    service = PortfolioWorkflowService(exchange=exchange)
    with pytest.raises(PortfolioWorkflowFailure) as caught:
        service.execute(grant=grant_for(request), request=request)
    rendered = f"{caught.value!s} {caught.value!r}"
    assert REJECTED_CANARY not in rendered
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_recorded_adapter_rejects_duplicate_reordered_and_exhausted_scripts() -> None:
    request = category_request()
    step = RecordedWorkflowStep(request, category_outcome())
    with pytest.raises(PortfolioWorkflowFailure):
        RecordedPortfolioWorkflowExchange(
            environment=RuntimeEnvironment.ENV_DEV,
            script_capacity=2,
            scripts=(step, step),
        )

    expected_request, expected_outcome = workflow_case(PortfolioOperation.GET_CATEGORY)
    service, adapter = service_for(expected_request, expected_outcome)
    with pytest.raises(PortfolioWorkflowFailure):
        adapter.exchange(request)
    assert adapter.history == ()
    service.execute(grant=grant_for(expected_request), request=expected_request)
    with pytest.raises(PortfolioWorkflowFailure):
        adapter.exchange(expected_request)


@pytest.mark.parametrize(
    "value",
    (
        category_request(),
        category_outcome(),
        RecordedWorkflowStep(category_request(), category_outcome()),
        category_service()[1],
    ),
)
def test_values_are_redacted_and_non_pickleable(value: object) -> None:
    rendered = f"{value!s} {value!r}"
    assert REJECTED_CANARY not in rendered
    assert "test_only_travel" not in rendered
    with pytest.raises(TypeError):
        pickle.dumps(value)

"""Authorize and validate one non-persistent ST-0501 recorded exchange."""

from __future__ import annotations

from typing import cast, final
from uuid import UUID

from raos.domain.iam.authorization import AuthorizationGrant
from raos.domain.editorial.article_plan import (
    ArticlePlan,
    CreateArticlePlanOutcome,
    CreateArticlePlanRequest,
    GetArticlePlanOutcome,
    GetArticlePlanRequest,
    ListArticlePlansOutcome,
    ListArticlePlansRequest,
    UpdateArticlePlanOutcome,
    UpdateArticlePlanRequest,
)
from raos.domain.portfolio.workflow import (
    Category,
    CreateCategoryOutcome,
    CreateCategoryRequest,
    CreateIntentClusterOutcome,
    CreateIntentClusterRequest,
    CreateKeywordOutcome,
    CreateKeywordRequest,
    EntityVersion,
    GetCategoryOutcome,
    GetCategoryRequest,
    GetIntentClusterOutcome,
    GetIntentClusterRequest,
    GetKeywordOutcome,
    GetKeywordRequest,
    IntentCluster,
    Keyword,
    ListCategoriesOutcome,
    ListCategoriesRequest,
    ListIntentClustersOutcome,
    ListIntentClustersRequest,
    ListKeywordsOutcome,
    ListKeywordsRequest,
    OutcomeDisposition,
    PortfolioOperation,
    PortfolioWorkflowFailureCode,
    UpdateCategoryOutcome,
    UpdateCategoryRequest,
    UpdateIntentClusterOutcome,
    UpdateIntentClusterRequest,
    UpdateKeywordOutcome,
    UpdateKeywordRequest,
    WorkflowTarget,
    fail_portfolio_workflow,
)
from raos.ports.portfolio_workflow import (
    PortfolioWorkflowExchange,
    PortfolioWorkflowOutcome,
    PortfolioWorkflowRequest,
)


_ACTION_BY_OPERATION = {
    PortfolioOperation.LIST_CATEGORIES: "portfolio:category:read",
    PortfolioOperation.CREATE_CATEGORY: "portfolio:category:write",
    PortfolioOperation.GET_CATEGORY: "portfolio:category:read",
    PortfolioOperation.UPDATE_CATEGORY: "portfolio:category:write",
    PortfolioOperation.LIST_INTENT_CLUSTERS: "portfolio:intent:read",
    PortfolioOperation.CREATE_INTENT_CLUSTER: "portfolio:intent:write",
    PortfolioOperation.GET_INTENT_CLUSTER: "portfolio:intent:read",
    PortfolioOperation.UPDATE_INTENT_CLUSTER: "portfolio:intent:write",
    PortfolioOperation.LIST_KEYWORDS: "portfolio:keyword:read",
    PortfolioOperation.CREATE_KEYWORD: "portfolio:keyword:write",
    PortfolioOperation.GET_KEYWORD: "portfolio:keyword:read",
    PortfolioOperation.UPDATE_KEYWORD: "portfolio:keyword:write",
    PortfolioOperation.LIST_ARTICLE_PLANS: "editorial:plan:read",
    PortfolioOperation.CREATE_ARTICLE_PLAN: "editorial:plan:write",
    PortfolioOperation.GET_ARTICLE_PLAN: "editorial:plan:read",
    PortfolioOperation.UPDATE_ARTICLE_PLAN: "editorial:plan:write",
}

_CORE_EXPECTED_OUTCOME: dict[type[object], type[object]] = {
    ListCategoriesRequest: ListCategoriesOutcome,
    CreateCategoryRequest: CreateCategoryOutcome,
    GetCategoryRequest: GetCategoryOutcome,
    UpdateCategoryRequest: UpdateCategoryOutcome,
    ListIntentClustersRequest: ListIntentClustersOutcome,
    CreateIntentClusterRequest: CreateIntentClusterOutcome,
    GetIntentClusterRequest: GetIntentClusterOutcome,
    UpdateIntentClusterRequest: UpdateIntentClusterOutcome,
    ListKeywordsRequest: ListKeywordsOutcome,
    CreateKeywordRequest: CreateKeywordOutcome,
    GetKeywordRequest: GetKeywordOutcome,
    UpdateKeywordRequest: UpdateKeywordOutcome,
    ListArticlePlansRequest: ListArticlePlansOutcome,
    CreateArticlePlanRequest: CreateArticlePlanOutcome,
    GetArticlePlanRequest: GetArticlePlanOutcome,
    UpdateArticlePlanRequest: UpdateArticlePlanOutcome,
}


def _target(request: object) -> WorkflowTarget:
    value = getattr(request, "target", None)
    if type(value) is not WorkflowTarget:
        fail_portfolio_workflow()
    return value


def _operation(request: object) -> PortfolioOperation:
    value = getattr(request, "operation", None)
    if type(value) is not PortfolioOperation:
        fail_portfolio_workflow()
    return value


PortfolioItem = Category | IntentCluster | Keyword | ArticlePlan


def _item(outcome: PortfolioWorkflowOutcome) -> PortfolioItem | None:
    return cast(PortfolioItem | None, getattr(outcome, "item", None))


def _items(outcome: PortfolioWorkflowOutcome) -> tuple[PortfolioItem, ...] | None:
    value = getattr(outcome, "items", None)
    return cast(tuple[PortfolioItem, ...], value) if type(value) is tuple else None


def _entity_id(item: PortfolioItem) -> UUID:
    if type(item) is Category:
        return item.category_id
    if type(item) is IntentCluster:
        return item.intent_cluster_id
    if type(item) is Keyword:
        return item.keyword_id
    if type(item) is ArticlePlan:
        return item.plan_id
    fail_portfolio_workflow(PortfolioWorkflowFailureCode.OUTCOME_MISMATCH)


def _validate_semantics(
    request: PortfolioWorkflowRequest,
    outcome: PortfolioWorkflowOutcome,
) -> None:
    target = _target(request)
    if isinstance(
        request,
        (
            ListCategoriesRequest,
            ListIntentClustersRequest,
            ListKeywordsRequest,
            ListArticlePlansRequest,
        ),
    ):
        items = _items(outcome)
        page = getattr(outcome, "page", None)
        if (
            items is None
            or len(items) > request.pagination.limit.value
            or page is None
            or page.limit != request.pagination.limit
            or tuple(getattr(item, "site_id", None) for item in items)
            != tuple(target.site_id for _ in items)
        ):
            fail_portfolio_workflow(PortfolioWorkflowFailureCode.OUTCOME_MISMATCH)
        ids = tuple(_entity_id(item) for item in items)
        if ids != tuple(sorted(ids, key=lambda value: value.int)):
            fail_portfolio_workflow(PortfolioWorkflowFailureCode.OUTCOME_MISMATCH)
        if isinstance(request, ListIntentClustersRequest) and any(
            type(item) is not IntentCluster
            or item.values.category_id != request.category_id
            for item in items
        ):
            fail_portfolio_workflow(PortfolioWorkflowFailureCode.OUTCOME_MISMATCH)
        if isinstance(request, ListArticlePlansRequest) and any(
            type(item) is not ArticlePlan
            or item.values.graph.category_id != request.category_id
            for item in items
        ):
            fail_portfolio_workflow(PortfolioWorkflowFailureCode.OUTCOME_MISMATCH)
        return

    item = _item(outcome)
    if item is None or getattr(item, "site_id", None) != target.site_id:
        fail_portfolio_workflow(PortfolioWorkflowFailureCode.OUTCOME_MISMATCH)
    requested_id = getattr(
        request,
        "category_id",
        getattr(
            request,
            "intent_cluster_id",
            getattr(request, "keyword_id", getattr(request, "plan_id", None)),
        ),
    )
    item_id = _entity_id(item)
    if requested_id is not None and requested_id != item_id:
        fail_portfolio_workflow(PortfolioWorkflowFailureCode.OUTCOME_MISMATCH)
    requested_values = getattr(request, "values", None)
    if requested_values is not None and item.values != requested_values:
        fail_portfolio_workflow(PortfolioWorkflowFailureCode.OUTCOME_MISMATCH)
    if isinstance(
        request,
        (
            CreateCategoryRequest,
            CreateIntentClusterRequest,
            CreateKeywordRequest,
            CreateArticlePlanRequest,
        ),
    ):
        if item.version != EntityVersion(0):
            fail_portfolio_workflow(PortfolioWorkflowFailureCode.OUTCOME_MISMATCH)
        return
    if isinstance(
        request,
        (
            UpdateCategoryRequest,
            UpdateIntentClusterRequest,
            UpdateKeywordRequest,
            UpdateArticlePlanRequest,
        ),
    ):
        if outcome.disposition is OutcomeDisposition.UPDATED:
            valid = (
                item.version.value == request.expected_version.value + 1
                and item.etag != request.if_match
            )
        else:
            valid = (
                item.version == request.expected_version
                and item.etag == request.if_match
            )
        if not valid:
            fail_portfolio_workflow(PortfolioWorkflowFailureCode.OUTCOME_MISMATCH)


@final
class PortfolioWorkflowService:
    """One authorize-before-I/O exchange with strict result validation."""

    __slots__ = ("_exchange",)

    def __init__(self, *, exchange: PortfolioWorkflowExchange) -> None:
        try:
            valid = isinstance(exchange, PortfolioWorkflowExchange)
        except TypeError:
            valid = False
        if not valid:
            fail_portfolio_workflow()
        self._exchange = exchange

    def execute(
        self,
        *,
        grant: AuthorizationGrant,
        request: PortfolioWorkflowRequest,
    ) -> PortfolioWorkflowOutcome:
        expected = _CORE_EXPECTED_OUTCOME.get(type(request))
        operation = _operation(request)
        target = _target(request)
        if expected is None:
            fail_portfolio_workflow()
        if (
            type(grant) is not AuthorizationGrant
            or grant.action.value != _ACTION_BY_OPERATION[operation]
            or grant.target.scope.site_id != target.site_id
            or grant.target.scope.resource_id != target.resource_id
        ):
            fail_portfolio_workflow(PortfolioWorkflowFailureCode.NOT_AUTHORIZED)

        observed: object = None
        unavailable = False
        try:
            observed = self._exchange.exchange(request)
        except Exception:
            unavailable = True
        if unavailable:
            fail_portfolio_workflow(
                PortfolioWorkflowFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
            )
        if type(observed) is not expected:
            fail_portfolio_workflow(PortfolioWorkflowFailureCode.OUTCOME_MISMATCH)
        typed_observed = cast(PortfolioWorkflowOutcome, observed)
        if typed_observed.operation is not operation:
            fail_portfolio_workflow(PortfolioWorkflowFailureCode.OUTCOME_MISMATCH)
        _validate_semantics(request, typed_observed)
        return typed_observed


__all__ = ["PortfolioWorkflowService"]

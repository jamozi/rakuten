"""Synthetic builders for the isolated ST-0501 suite."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
from uuid import UUID


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.adapters.recorded_portfolio_workflow import (  # noqa: E402
    RecordedPortfolioWorkflowExchange,
    RecordedWorkflowStep,
)
from raos.application.portfolio.workflow import PortfolioWorkflowService  # noqa: E402
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.iam.authorization import (  # noqa: E402
    ActionCode,
    AuthorizationDecision,
    AuthorizationDecisionReason,
    AuthorizationGrant,
    AuthorizationTarget,
    CorrelationId,
    DecisionEffect,
    EntitlementRevision,
    PolicyRevision,
    ResourceScope,
    ResourceScopeKind,
    RuleId,
)
from raos.domain.portfolio.workflow import (  # noqa: E402
    Category,
    CategoryRisk,
    CategoryStage,
    CategoryValues,
    CreateCategoryOutcome,
    CreateCategoryRequest,
    DisplayId,
    EntityVersion,
    IdempotencyKey,
    OutcomeDisposition,
    StrongEtag,
    UtcTimestamp,
    WorkflowTarget,
)
from raos.domain.editorial.article_plan import (  # noqa: E402
    ArticlePlan,
    ArticlePlanGraph,
    ArticlePlanState,
    ArticlePlanType,
    ArticlePlanValues,
    CreateArticlePlanOutcome,
    CreateArticlePlanRequest,
    GetArticlePlanOutcome,
    GetArticlePlanRequest,
    ListArticlePlansOutcome,
    ListArticlePlansRequest,
    UpdateArticlePlanOutcome,
    UpdateArticlePlanRequest,
)
from raos.domain.portfolio.workflow import (  # noqa: E402
    CreateIntentClusterOutcome,
    CreateIntentClusterRequest,
    CreateKeywordOutcome,
    CreateKeywordRequest,
    GetCategoryOutcome,
    GetCategoryRequest,
    GetIntentClusterOutcome,
    GetIntentClusterRequest,
    GetKeywordOutcome,
    GetKeywordRequest,
    IntentCluster,
    IntentClusterValues,
    IntentType,
    Keyword,
    KeywordStatus,
    KeywordValues,
    ListCategoriesOutcome,
    ListCategoriesRequest,
    ListIntentClustersOutcome,
    ListIntentClustersRequest,
    ListKeywordsOutcome,
    ListKeywordsRequest,
    PageInfo,
    PageLimit,
    Pagination,
    PortfolioOperation,
    PortfolioRecordStatus,
    UpdateCategoryOutcome,
    UpdateCategoryRequest,
    UpdateIntentClusterOutcome,
    UpdateIntentClusterRequest,
    UpdateKeywordOutcome,
    UpdateKeywordRequest,
)
from raos.ports.portfolio_workflow import (  # noqa: E402
    PortfolioWorkflowOutcome,
    PortfolioWorkflowRequest,
)


SITE_A = UUID("018f3e90-7b00-7000-8000-000000000001")
CATEGORY_A = UUID("018f3e90-7b00-7000-8000-000000000002")
INTENT_A = UUID("018f3e90-7b00-7000-8000-000000000003")
KEYWORD_A = UUID("018f3e90-7b00-7000-8000-000000000004")
PLAN_A = UUID("018f3e90-7b00-7000-8000-000000000005")
NOW = UtcTimestamp(datetime(2026, 8, 10, 3, 0, tzinfo=timezone.utc))


ACTION_BY_OPERATION = {
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


def authorization_grant(
    *,
    action: str = "portfolio:category:write",
    site_id: UUID = SITE_A,
    resource_id: UUID = SITE_A,
) -> AuthorizationGrant:
    return AuthorizationGrant(
        recorded_decision=AuthorizationDecision(
            correlation_id=CorrelationId("TEST_ONLY:ST0501"),
            effect=DecisionEffect.ALLOW,
            reason=AuthorizationDecisionReason.RULE_MATCH,
            policy_revision=PolicyRevision("TEST_ONLY:POLICY_V1"),
            policy_fingerprint="5" * 64,
            entitlement_revision=EntitlementRevision("TEST_ONLY:ENTITLEMENTS_V1"),
            matched_rule_id=RuleId("TEST_ONLY:PORTFOLIO_WORKFLOW"),
            action=ActionCode(action),
            target=AuthorizationTarget(
                scope=ResourceScope(
                    kind=ResourceScopeKind.SITE,
                    site_id=site_id,
                    resource_id=resource_id,
                )
            ),
        )
    )


def category_values() -> CategoryValues:
    return CategoryValues(
        category_code="test_only_travel",
        name="Test only travel",
        description=None,
        parent_category_id=None,
        risk=CategoryRisk.LOW,
        stage=CategoryStage.CANDIDATE,
        article_limit=10,
    )


def category_request() -> CreateCategoryRequest:
    return CreateCategoryRequest(
        target=WorkflowTarget(
            environment="TEST_ONLY", site_id=SITE_A, resource_id=SITE_A
        ),
        idempotency_key=IdempotencyKey("TEST_ONLY:CREATE:CATEGORY:1"),
        values=category_values(),
    )


def category_outcome() -> CreateCategoryOutcome:
    return CreateCategoryOutcome(
        item=Category(
            category_id=CATEGORY_A,
            display_id=DisplayId("CAT-TEST-0001"),
            site_id=SITE_A,
            values=category_values(),
            version=EntityVersion(0),
            etag=StrongEtag('"test-only-category-v0"'),
            created_at=NOW,
            updated_at=NOW,
        ),
        disposition=OutcomeDisposition.CREATED,
    )


def category_service() -> tuple[
    PortfolioWorkflowService, RecordedPortfolioWorkflowExchange
]:
    adapter = RecordedPortfolioWorkflowExchange(
        environment=RuntimeEnvironment.ENV_DEV,
        script_capacity=1,
        scripts=(
            RecordedWorkflowStep(
                request=category_request(), outcome=category_outcome()
            ),
        ),
    )
    return PortfolioWorkflowService(exchange=adapter), adapter


def target_for(resource_id: UUID = SITE_A) -> WorkflowTarget:
    return WorkflowTarget(
        environment="TEST_ONLY", site_id=SITE_A, resource_id=resource_id
    )


def page_request() -> Pagination:
    return Pagination(cursor=None, limit=PageLimit(50))


def page_outcome() -> PageInfo:
    return PageInfo(next_cursor=None, has_more=False, limit=PageLimit(50))


def category(*, version: int = 0, etag: str = '"category-v0"') -> Category:
    return Category(
        category_id=CATEGORY_A,
        display_id=DisplayId("CAT-TEST-0001"),
        site_id=SITE_A,
        values=category_values(),
        version=EntityVersion(version),
        etag=StrongEtag(etag),
        created_at=NOW,
        updated_at=NOW,
    )


def intent_values() -> IntentClusterValues:
    return IntentClusterValues(
        category_id=CATEGORY_A,
        cluster_code="test_only_selection",
        name="Test only selection intent",
        description=None,
        intent_type=IntentType.SELECTION_GUIDE,
        status=PortfolioRecordStatus.ACTIVE,
    )


def intent(*, version: int = 0, etag: str = '"intent-v0"') -> IntentCluster:
    return IntentCluster(
        intent_cluster_id=INTENT_A,
        display_id=DisplayId("INT-TEST-0001"),
        site_id=SITE_A,
        values=intent_values(),
        version=EntityVersion(version),
        etag=StrongEtag(etag),
        created_at=NOW,
        updated_at=NOW,
    )


def keyword_values() -> KeywordValues:
    return KeywordValues(
        text="test only suitcase",
        locale="ja-JP",
        status=KeywordStatus.ACTIVE,
        sensitive_query=False,
    )


def keyword(*, version: int = 0, etag: str = '"keyword-v0"') -> Keyword:
    return Keyword(
        keyword_id=KEYWORD_A,
        display_id=DisplayId("KW-TEST-0001"),
        site_id=SITE_A,
        values=keyword_values(),
        normalized_text="test only suitcase",
        version=EntityVersion(version),
        etag=StrongEtag(etag),
        created_at=NOW,
        updated_at=NOW,
    )


def plan_values() -> ArticlePlanValues:
    return ArticlePlanValues(
        graph=ArticlePlanGraph(
            site_id=SITE_A,
            category_id=CATEGORY_A,
            intent_cluster_id=INTENT_A,
            primary_keyword_id=KEYWORD_A,
        ),
        plan_type=ArticlePlanType.SELECTION_GUIDE,
        working_title="Test only selection guide",
        objective="Describe a synthetic editorial objective.",
        priority=50,
        state=ArticlePlanState.IDEA,
    )


def plan(*, version: int = 0, etag: str = '"plan-v0"') -> ArticlePlan:
    return ArticlePlan(
        plan_id=PLAN_A,
        display_id=DisplayId("PLAN-TEST-0001"),
        values=plan_values(),
        version=EntityVersion(version),
        etag=StrongEtag(etag),
        created_at=NOW,
        updated_at=NOW,
    )


def workflow_case(
    operation: PortfolioOperation,
) -> tuple[PortfolioWorkflowRequest, PortfolioWorkflowOutcome]:
    key = IdempotencyKey(f"TEST_ONLY:{operation.value}:IDEMPOTENCY")
    if operation is PortfolioOperation.LIST_CATEGORIES:
        return ListCategoriesRequest(
            target_for(), page_request()
        ), ListCategoriesOutcome(
            (category(),), page_outcome(), OutcomeDisposition.LISTED
        )
    if operation is PortfolioOperation.CREATE_CATEGORY:
        return CreateCategoryRequest(
            target_for(), key, category_values()
        ), CreateCategoryOutcome(category(), OutcomeDisposition.CREATED)
    if operation is PortfolioOperation.GET_CATEGORY:
        return GetCategoryRequest(
            target_for(CATEGORY_A), CATEGORY_A
        ), GetCategoryOutcome(category(), OutcomeDisposition.FOUND)
    if operation is PortfolioOperation.UPDATE_CATEGORY:
        return UpdateCategoryRequest(
            target_for(CATEGORY_A),
            CATEGORY_A,
            EntityVersion(0),
            StrongEtag('"category-v0"'),
            key,
            category_values(),
        ), UpdateCategoryOutcome(
            category(version=1, etag='"category-v1"'), OutcomeDisposition.UPDATED
        )
    if operation is PortfolioOperation.LIST_INTENT_CLUSTERS:
        return ListIntentClustersRequest(
            target_for(), CATEGORY_A, page_request()
        ), ListIntentClustersOutcome(
            (intent(),), page_outcome(), OutcomeDisposition.LISTED
        )
    if operation is PortfolioOperation.CREATE_INTENT_CLUSTER:
        return CreateIntentClusterRequest(
            target_for(), key, intent_values()
        ), CreateIntentClusterOutcome(intent(), OutcomeDisposition.CREATED)
    if operation is PortfolioOperation.GET_INTENT_CLUSTER:
        return GetIntentClusterRequest(
            target_for(INTENT_A), INTENT_A
        ), GetIntentClusterOutcome(intent(), OutcomeDisposition.FOUND)
    if operation is PortfolioOperation.UPDATE_INTENT_CLUSTER:
        return UpdateIntentClusterRequest(
            target_for(INTENT_A),
            INTENT_A,
            EntityVersion(0),
            StrongEtag('"intent-v0"'),
            key,
            intent_values(),
        ), UpdateIntentClusterOutcome(
            intent(version=1, etag='"intent-v1"'), OutcomeDisposition.UPDATED
        )
    if operation is PortfolioOperation.LIST_KEYWORDS:
        return ListKeywordsRequest(target_for(), page_request()), ListKeywordsOutcome(
            (keyword(),), page_outcome(), OutcomeDisposition.LISTED
        )
    if operation is PortfolioOperation.CREATE_KEYWORD:
        return CreateKeywordRequest(
            target_for(), key, keyword_values()
        ), CreateKeywordOutcome(keyword(), OutcomeDisposition.CREATED)
    if operation is PortfolioOperation.GET_KEYWORD:
        return GetKeywordRequest(target_for(KEYWORD_A), KEYWORD_A), GetKeywordOutcome(
            keyword(), OutcomeDisposition.FOUND
        )
    if operation is PortfolioOperation.UPDATE_KEYWORD:
        return UpdateKeywordRequest(
            target_for(KEYWORD_A),
            KEYWORD_A,
            EntityVersion(0),
            StrongEtag('"keyword-v0"'),
            key,
            keyword_values(),
        ), UpdateKeywordOutcome(
            keyword(version=1, etag='"keyword-v1"'), OutcomeDisposition.UPDATED
        )
    if operation is PortfolioOperation.LIST_ARTICLE_PLANS:
        return ListArticlePlansRequest(
            target_for(), CATEGORY_A, page_request()
        ), ListArticlePlansOutcome((plan(),), page_outcome(), OutcomeDisposition.LISTED)
    if operation is PortfolioOperation.CREATE_ARTICLE_PLAN:
        return CreateArticlePlanRequest(
            target_for(), key, plan_values()
        ), CreateArticlePlanOutcome(plan(), OutcomeDisposition.CREATED)
    if operation is PortfolioOperation.GET_ARTICLE_PLAN:
        return GetArticlePlanRequest(target_for(PLAN_A), PLAN_A), GetArticlePlanOutcome(
            plan(), OutcomeDisposition.FOUND
        )
    if operation is PortfolioOperation.UPDATE_ARTICLE_PLAN:
        return UpdateArticlePlanRequest(
            target_for(PLAN_A),
            PLAN_A,
            EntityVersion(0),
            StrongEtag('"plan-v0"'),
            key,
            plan_values(),
        ), UpdateArticlePlanOutcome(
            plan(version=1, etag='"plan-v1"'), OutcomeDisposition.UPDATED
        )
    raise AssertionError("unmapped portfolio operation")


def service_for(
    request: PortfolioWorkflowRequest, outcome: PortfolioWorkflowOutcome
) -> tuple[PortfolioWorkflowService, RecordedPortfolioWorkflowExchange]:
    adapter = RecordedPortfolioWorkflowExchange(
        environment=RuntimeEnvironment.ENV_DEV,
        script_capacity=1,
        scripts=(RecordedWorkflowStep(request=request, outcome=outcome),),
    )
    return PortfolioWorkflowService(exchange=adapter), adapter


def grant_for(
    request: PortfolioWorkflowRequest, *, action: str | None = None
) -> AuthorizationGrant:
    target = request.target
    return authorization_grant(
        action=ACTION_BY_OPERATION[request.operation] if action is None else action,
        site_id=target.site_id,
        resource_id=target.resource_id,
    )

"""Synthetic builders for the isolated ST-0802 recorded seam."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from uuid import UUID


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.adapters.recorded_article_lifecycle import (  # noqa: E402
    RecordedArticleLifecycleExchange,
    RecordedArticleLifecycleStep,
)
from raos.application.editorial.article_lifecycle import (  # noqa: E402
    ArticleLifecycleService,
)
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.editorial.article_lifecycle import (  # noqa: E402
    Article,
    ArticleDisplayId,
    ArticleLifecycleMode,
    ArticleLifecycleOperation,
    ArticleLifecycleOutcome,
    ArticleLifecycleRequest,
    ArticleState,
    ArticleVersionHistory,
    ArticleVersionState,
    BodySha256,
    CreateArticleOutcome,
    CreateArticleRequest,
    CreateVersionOutcome,
    CreateVersionRequest,
    GetArticleOutcome,
    GetArticleRequest,
    GetVersionOutcome,
    GetVersionRequest,
    ListArticlesOutcome,
    ListArticlesRequest,
    SourcePacketVerification,
    UpdateArticleOutcome,
    UpdateArticleRequest,
    UpdateVersionOutcome,
    UpdateVersionRequest,
    VersionDisplayId,
    VersionSnapshot,
)
from raos.domain.editorial.article_plan import (  # noqa: E402
    ArticlePlan,
    ArticlePlanGraph,
    ArticlePlanState,
    ArticlePlanType,
    ArticlePlanValues,
)
from raos.domain.editorial.content_ast import ContentAst, load_content_ast  # noqa: E402
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
    DisplayId,
    EntityVersion,
    IdempotencyKey,
    OutcomeDisposition,
    PageInfo,
    PageLimit,
    Pagination,
    StrongEtag,
    UtcTimestamp,
    WorkflowTarget,
)


SITE_ID = UUID("018f3e90-7b00-7000-8000-000000000101")
CATEGORY_ID = UUID("018f3e90-7b00-7000-8000-000000000102")
INTENT_ID = UUID("018f3e90-7b00-7000-8000-000000000103")
KEYWORD_ID = UUID("018f3e90-7b00-7000-8000-000000000104")
PLAN_ID = UUID("018f3e90-7b00-7000-8000-000000000105")
ARTICLE_ID = UUID("018f3e90-7b00-7000-8000-000000000106")
VERSION_ID = UUID("018f3e90-7b00-7000-8000-000000000107")
SOURCE_PACKET_VERSION_ID = UUID("018f3e90-7b00-7000-8000-000000000108")
NOW = UtcTimestamp(datetime(2026, 8, 10, 4, 0, tzinfo=timezone.utc))

ACTION_BY_OPERATION = {
    ArticleLifecycleOperation.CREATE_ARTICLE: "editorial:article:write",
    ArticleLifecycleOperation.LIST_ARTICLES: "editorial:article:read",
    ArticleLifecycleOperation.GET_ARTICLE: "editorial:article:read",
    ArticleLifecycleOperation.UPDATE_ARTICLE: "editorial:article:write",
    ArticleLifecycleOperation.CREATE_VERSION: "editorial:version:write",
    ArticleLifecycleOperation.GET_VERSION: "editorial:version:read",
    ArticleLifecycleOperation.UPDATE_VERSION: "editorial:version:write",
}


def grant(
    *,
    action: str = "editorial:article:write",
    site_id: UUID = SITE_ID,
    resource_id: UUID = PLAN_ID,
) -> AuthorizationGrant:
    return AuthorizationGrant(
        recorded_decision=AuthorizationDecision(
            correlation_id=CorrelationId("TEST_ONLY:ST0802"),
            effect=DecisionEffect.ALLOW,
            reason=AuthorizationDecisionReason.RULE_MATCH,
            policy_revision=PolicyRevision("TEST_ONLY:POLICY_V1"),
            policy_fingerprint="8" * 64,
            entitlement_revision=EntitlementRevision("TEST_ONLY:ENTITLEMENTS_V1"),
            matched_rule_id=RuleId("TEST_ONLY:ARTICLE_LIFECYCLE"),
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


def plan() -> ArticlePlan:
    return ArticlePlan(
        plan_id=PLAN_ID,
        display_id=DisplayId("PLAN-TEST-0802"),
        values=ArticlePlanValues(
            graph=ArticlePlanGraph(
                site_id=SITE_ID,
                category_id=CATEGORY_ID,
                intent_cluster_id=INTENT_ID,
                primary_keyword_id=KEYWORD_ID,
            ),
            plan_type=ArticlePlanType.SELECTION_GUIDE,
            working_title="Synthetic lifecycle article",
            objective="Exercise the local recorded lifecycle seam",
            priority=50,
            state=ArticlePlanState.IDEA,
        ),
        version=EntityVersion(0),
        etag=StrongEtag('"test-only-plan-v0"'),
        created_at=NOW,
        updated_at=NOW,
    )


def content_ast() -> ContentAst:
    fixture = (
        REPOSITORY_ROOT
        / "contracts/raos-v0.4/contracts/content/fixtures/valid/selection_guide.json"
    )
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    payload["article_id"] = str(ARTICLE_ID)
    payload["article_version_id"] = str(VERSION_ID)
    payload["title"] = "Synthetic lifecycle article"
    payload["source_packet_version_ref"] = str(SOURCE_PACKET_VERSION_ID)
    return load_content_ast(json.dumps(payload, ensure_ascii=False))


def version_snapshot() -> VersionSnapshot:
    ast = content_ast()
    return VersionSnapshot(
        version_id=VERSION_ID,
        display_id=VersionDisplayId("ARV-TEST-0802"),
        article_id=ARTICLE_ID,
        version_no=1,
        article_type=ArticlePlanType.SELECTION_GUIDE,
        title="Synthetic lifecycle article",
        source_packet_version_id=SOURCE_PACKET_VERSION_ID,
        source_packet_verification=SourcePacketVerification.NOT_VERIFIED,
        based_on_version_id=None,
        content_ast=ast,
        body_sha256=BodySha256.of(ast),
        state=ArticleVersionState.DRAFT,
        submitted_at=None,
        reviewed_at=None,
        approved_at=None,
        published_at=None,
        version=EntityVersion(0),
        etag=StrongEtag('"test-only-version-v0"'),
        created_at=NOW,
        updated_at=NOW,
    )


def article() -> Article:
    return Article(
        article_id=ARTICLE_ID,
        display_id=ArticleDisplayId("ART-TEST-0802"),
        plan_id=PLAN_ID,
        site_id=SITE_ID,
        category_id=CATEGORY_ID,
        article_type=ArticlePlanType.SELECTION_GUIDE,
        state=ArticleState.IDEA,
        current_version_id=None,
        published_version_id=None,
        archived_at=None,
        approval_id=None,
        publication_id=None,
        version=EntityVersion(0),
        etag=StrongEtag('"test-only-article-v0"'),
        created_at=NOW,
        updated_at=NOW,
    )


def create_request() -> CreateArticleRequest:
    return CreateArticleRequest(
        target=WorkflowTarget(
            environment="TEST_ONLY", site_id=SITE_ID, resource_id=PLAN_ID
        ),
        plan=plan(),
        idempotency_key=IdempotencyKey("TEST_ONLY:ST0802:CREATE:ARTICLE"),
    )


def create_outcome() -> CreateArticleOutcome:
    version = version_snapshot()
    return CreateArticleOutcome(
        article=article(),
        initial_version=version,
        history=ArticleVersionHistory(article_id=ARTICLE_ID, versions=(version,)),
        disposition=OutcomeDisposition.CREATED,
    )


def history() -> ArticleVersionHistory:
    version = version_snapshot()
    return ArticleVersionHistory(article_id=ARTICLE_ID, versions=(version,))


def lifecycle_case(
    operation: ArticleLifecycleOperation,
) -> tuple[ArticleLifecycleRequest, ArticleLifecycleOutcome]:
    if operation is ArticleLifecycleOperation.CREATE_ARTICLE:
        return create_request(), create_outcome()
    if operation is ArticleLifecycleOperation.LIST_ARTICLES:
        pagination = Pagination(cursor=None, limit=PageLimit(50))
        return (
            ListArticlesRequest(
                target=WorkflowTarget(
                    environment="TEST_ONLY",
                    site_id=SITE_ID,
                    resource_id=SITE_ID,
                ),
                category_id=CATEGORY_ID,
                article_type=ArticlePlanType.SELECTION_GUIDE,
                pagination=pagination,
            ),
            ListArticlesOutcome(
                items=(article(),),
                page=PageInfo(next_cursor=None, has_more=False, limit=pagination.limit),
                disposition=OutcomeDisposition.LISTED,
            ),
        )
    if operation is ArticleLifecycleOperation.GET_ARTICLE:
        return (
            GetArticleRequest(
                target=WorkflowTarget(
                    environment="TEST_ONLY",
                    site_id=SITE_ID,
                    resource_id=ARTICLE_ID,
                ),
                article_id=ARTICLE_ID,
            ),
            GetArticleOutcome(
                article=article(),
                history=history(),
                disposition=OutcomeDisposition.FOUND,
            ),
        )
    if operation is ArticleLifecycleOperation.UPDATE_ARTICLE:
        return (
            UpdateArticleRequest(
                target=WorkflowTarget(
                    environment="TEST_ONLY",
                    site_id=SITE_ID,
                    resource_id=ARTICLE_ID,
                ),
                article_id=ARTICLE_ID,
                expected_version=EntityVersion(0),
                if_match=StrongEtag('"test-only-article-v0"'),
                idempotency_key=IdempotencyKey("TEST_ONLY:ST0802:UPDATE:ARTICLE"),
                state=ArticleState.IDEA,
            ),
            UpdateArticleOutcome(
                article=article(),
                history=history(),
                disposition=OutcomeDisposition.NOOP,
            ),
        )
    if operation is ArticleLifecycleOperation.CREATE_VERSION:
        version = version_snapshot()
        return (
            CreateVersionRequest(
                target=WorkflowTarget(
                    environment="TEST_ONLY",
                    site_id=SITE_ID,
                    resource_id=ARTICLE_ID,
                ),
                article_id=ARTICLE_ID,
                idempotency_key=IdempotencyKey("TEST_ONLY:ST0802:CREATE:VERSION"),
                version=version,
            ),
            CreateVersionOutcome(
                article=article(),
                version=version,
                history=ArticleVersionHistory(
                    article_id=ARTICLE_ID, versions=(version,)
                ),
                disposition=OutcomeDisposition.CREATED,
            ),
        )
    if operation is ArticleLifecycleOperation.GET_VERSION:
        version = version_snapshot()
        return (
            GetVersionRequest(
                target=WorkflowTarget(
                    environment="TEST_ONLY",
                    site_id=SITE_ID,
                    resource_id=VERSION_ID,
                ),
                version_id=VERSION_ID,
            ),
            GetVersionOutcome(
                article=article(),
                version=version,
                history=ArticleVersionHistory(
                    article_id=ARTICLE_ID, versions=(version,)
                ),
                disposition=OutcomeDisposition.FOUND,
            ),
        )
    if operation is ArticleLifecycleOperation.UPDATE_VERSION:
        version = version_snapshot()
        return (
            UpdateVersionRequest(
                target=WorkflowTarget(
                    environment="TEST_ONLY",
                    site_id=SITE_ID,
                    resource_id=VERSION_ID,
                ),
                version_id=VERSION_ID,
                expected_version=EntityVersion(0),
                if_match=StrongEtag('"test-only-version-v0"'),
                idempotency_key=IdempotencyKey("TEST_ONLY:ST0802:UPDATE:VERSION"),
                version=version,
            ),
            UpdateVersionOutcome(
                article=article(),
                version=version,
                history=ArticleVersionHistory(
                    article_id=ARTICLE_ID, versions=(version,)
                ),
                disposition=OutcomeDisposition.NOOP,
            ),
        )
    raise AssertionError("unreachable operation")


def grant_for(request: ArticleLifecycleRequest) -> AuthorizationGrant:
    return grant(
        action=ACTION_BY_OPERATION[request.operation],
        resource_id=request.target.resource_id,
    )


def service_for(
    request: ArticleLifecycleRequest,
    outcome: ArticleLifecycleOutcome,
    *,
    environment: RuntimeEnvironment = RuntimeEnvironment.ENV_DEV,
) -> tuple[ArticleLifecycleService, RecordedArticleLifecycleExchange]:
    exchange = RecordedArticleLifecycleExchange(
        environment=environment,
        mode=ArticleLifecycleMode.RECORDED_TEST_ONLY,
        script_capacity=1,
        scripts=(RecordedArticleLifecycleStep(request=request, outcome=outcome),),
    )
    return (
        ArticleLifecycleService(
            environment=environment,
            mode=ArticleLifecycleMode.RECORDED_TEST_ONLY,
            exchange=exchange,
        ),
        exchange,
    )


def create_service() -> ArticleLifecycleService:
    exchange = RecordedArticleLifecycleExchange(
        environment=RuntimeEnvironment.ENV_DEV,
        mode=ArticleLifecycleMode.RECORDED_TEST_ONLY,
        script_capacity=1,
        scripts=(
            RecordedArticleLifecycleStep(
                request=create_request(), outcome=create_outcome()
            ),
        ),
    )
    return ArticleLifecycleService(
        environment=RuntimeEnvironment.ENV_DEV,
        mode=ArticleLifecycleMode.RECORDED_TEST_ONLY,
        exchange=exchange,
    )

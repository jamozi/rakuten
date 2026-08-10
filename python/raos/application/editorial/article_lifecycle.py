"""Authorize and validate one recorded, non-persistent ST-0802 exchange."""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.editorial.article_lifecycle import (
    Article,
    ArticleLifecycleFailureCode,
    ArticleLifecycleMode,
    ArticleLifecycleOperation,
    ArticleLifecycleOutcome,
    ArticleLifecycleRequest,
    ArticleLifecycleResult,
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
    LifecycleDecision,
    LifecycleExecution,
    ListArticlesOutcome,
    ListArticlesRequest,
    PLAN_TYPE_TO_CONTENT_AST_TYPE,
    SourcePacketVerification,
    UpdateArticleOutcome,
    UpdateArticleRequest,
    UpdateVersionOutcome,
    UpdateVersionRequest,
    VersionSnapshot,
    fail_article_lifecycle,
)
from raos.domain.editorial.article_plan import ArticlePlan, ArticlePlanState
from raos.domain.iam.authorization import AuthorizationGrant
from raos.domain.portfolio.workflow import (
    EntityVersion,
    IdempotencyKey,
    OutcomeDisposition,
    StrongEtag,
    WorkflowTarget,
)
from raos.ports.article_lifecycle import ArticleLifecycleExchange


_ACTION_BY_OPERATION = {
    ArticleLifecycleOperation.CREATE_ARTICLE: "editorial:article:write",
    ArticleLifecycleOperation.LIST_ARTICLES: "editorial:article:read",
    ArticleLifecycleOperation.GET_ARTICLE: "editorial:article:read",
    ArticleLifecycleOperation.UPDATE_ARTICLE: "editorial:article:write",
    ArticleLifecycleOperation.CREATE_VERSION: "editorial:version:write",
    ArticleLifecycleOperation.GET_VERSION: "editorial:version:read",
    ArticleLifecycleOperation.UPDATE_VERSION: "editorial:version:write",
}

_EXPECTED_OUTCOME: dict[type[object], type[object]] = {
    CreateArticleRequest: CreateArticleOutcome,
    ListArticlesRequest: ListArticlesOutcome,
    GetArticleRequest: GetArticleOutcome,
    UpdateArticleRequest: UpdateArticleOutcome,
    CreateVersionRequest: CreateVersionOutcome,
    GetVersionRequest: GetVersionOutcome,
    UpdateVersionRequest: UpdateVersionOutcome,
}


def _request_parts(
    request: object,
) -> tuple[ArticleLifecycleOperation, WorkflowTarget]:
    operation = getattr(request, "operation", None)
    target = getattr(request, "target", None)
    if (
        type(request) not in _EXPECTED_OUTCOME
        or type(operation) is not ArticleLifecycleOperation
        or type(target) is not WorkflowTarget
        or target.environment != "TEST_ONLY"
    ):
        fail_article_lifecycle()
    return operation, target


def _validate_article(article: object) -> Article:
    if (
        type(article) is not Article
        or article.state is not ArticleState.IDEA
        or article.current_version_id is not None
        or article.published_version_id is not None
        or article.archived_at is not None
        or article.approval_id is not None
        or article.publication_id is not None
        or type(article.version) is not EntityVersion
        or type(article.etag) is not StrongEtag
    ):
        fail_article_lifecycle(ArticleLifecycleFailureCode.OUTCOME_MISMATCH)
    return article


def _validate_version(version: object) -> VersionSnapshot:
    if (
        type(version) is not VersionSnapshot
        or version.state is not ArticleVersionState.DRAFT
        or version.source_packet_verification
        is not SourcePacketVerification.NOT_VERIFIED
        or type(version.version) is not EntityVersion
        or type(version.etag) is not StrongEtag
        or version.body_sha256 != BodySha256.of(version.content_ast)
        or version.content_ast.article_id != str(version.article_id)
        or version.content_ast.article_version_id != str(version.version_id)
        or version.content_ast.article_type
        is not PLAN_TYPE_TO_CONTENT_AST_TYPE[version.article_type]
        or version.content_ast.title != version.title
        or version.content_ast.source_packet_version_ref
        != str(version.source_packet_version_id)
        or any(
            marker is not None
            for marker in (
                version.submitted_at,
                version.reviewed_at,
                version.approved_at,
                version.published_at,
            )
        )
    ):
        fail_article_lifecycle(ArticleLifecycleFailureCode.OUTCOME_MISMATCH)
    return version


def _validate_history(history: object, article: Article) -> ArticleVersionHistory:
    if (
        type(history) is not ArticleVersionHistory
        or history.article_id != article.article_id
    ):
        fail_article_lifecycle(ArticleLifecycleFailureCode.OUTCOME_MISMATCH)
    previous = 0
    seen: set[object] = set()
    for version in history.versions:
        _validate_version(version)
        if (
            version.article_id != article.article_id
            or version.version_no <= previous
            or version.version_id in seen
            or (
                version.based_on_version_id is not None
                and version.based_on_version_id not in seen
            )
        ):
            fail_article_lifecycle(ArticleLifecycleFailureCode.OUTCOME_MISMATCH)
        previous = version.version_no
        seen.add(version.version_id)
    return history


def _validate_request(request: ArticleLifecycleRequest) -> None:
    target = request.target
    if isinstance(request, CreateArticleRequest):
        if (
            type(request.plan) is not ArticlePlan
            or type(request.idempotency_key) is not IdempotencyKey
            or request.plan.plan_id != target.resource_id
            or request.plan.site_id != target.site_id
            or request.plan.values.state is not ArticlePlanState.IDEA
        ):
            fail_article_lifecycle()
    elif isinstance(request, ListArticlesRequest):
        if request.pagination.limit.value < 1:
            fail_article_lifecycle()
    elif isinstance(request, (GetArticleRequest, UpdateArticleRequest)):
        if request.article_id != target.resource_id:
            fail_article_lifecycle()
        if isinstance(request, UpdateArticleRequest) and (
            type(request.expected_version) is not EntityVersion
            or type(request.if_match) is not StrongEtag
            or type(request.idempotency_key) is not IdempotencyKey
            or request.state is not ArticleState.IDEA
        ):
            fail_article_lifecycle()
    elif isinstance(request, CreateVersionRequest):
        if (
            request.article_id != target.resource_id
            or type(request.idempotency_key) is not IdempotencyKey
        ):
            fail_article_lifecycle()
        _validate_version(request.version)
    elif isinstance(request, GetVersionRequest):
        if request.version_id != target.resource_id:
            fail_article_lifecycle()
    elif isinstance(request, UpdateVersionRequest):
        if (
            request.version_id != target.resource_id
            or type(request.expected_version) is not EntityVersion
            or type(request.if_match) is not StrongEtag
            or type(request.idempotency_key) is not IdempotencyKey
            or request.version.version_id != request.version_id
        ):
            fail_article_lifecycle()
        _validate_version(request.version)
    else:
        fail_article_lifecycle()


def _validate_outcome(
    request: ArticleLifecycleRequest,
    outcome: ArticleLifecycleOutcome,
) -> None:
    target = request.target
    if isinstance(outcome, ListArticlesOutcome):
        if not isinstance(request, ListArticlesRequest):
            fail_article_lifecycle(ArticleLifecycleFailureCode.OUTCOME_MISMATCH)
        if (
            len(outcome.items) > request.pagination.limit.value
            or outcome.page.limit != request.pagination.limit
            or any(
                _validate_article(item).site_id != target.site_id
                or item.category_id != request.category_id
                or item.article_type is not request.article_type
                for item in outcome.items
            )
        ):
            fail_article_lifecycle(ArticleLifecycleFailureCode.OUTCOME_MISMATCH)
        return

    article = _validate_article(getattr(outcome, "article", None))
    if article.site_id != target.site_id:
        fail_article_lifecycle(ArticleLifecycleFailureCode.OUTCOME_MISMATCH)
    history = _validate_history(getattr(outcome, "history", None), article)

    if isinstance(request, CreateArticleRequest):
        create_article_outcome = cast(CreateArticleOutcome, outcome)
        version = _validate_version(create_article_outcome.initial_version)
        if (
            article.plan_id != request.plan.plan_id
            or article.category_id != request.plan.values.graph.category_id
            or article.article_type is not request.plan.values.plan_type
            or version.article_id != article.article_id
            or version.article_type is not article.article_type
            or version not in history.versions
            or version.version_no != 1
            or version.based_on_version_id is not None
            or create_article_outcome.disposition
            not in {OutcomeDisposition.CREATED, OutcomeDisposition.REPLAYED}
        ):
            fail_article_lifecycle(ArticleLifecycleFailureCode.OUTCOME_MISMATCH)
        return
    if isinstance(request, ListArticlesRequest):
        fail_article_lifecycle(ArticleLifecycleFailureCode.OUTCOME_MISMATCH)
    if isinstance(request, GetArticleRequest):
        valid = article.article_id == request.article_id
    elif isinstance(request, UpdateArticleRequest):
        update_article_outcome = cast(UpdateArticleOutcome, outcome)
        if update_article_outcome.disposition is OutcomeDisposition.UPDATED:
            concurrency_valid = (
                article.version.value == request.expected_version.value + 1
                and article.etag != request.if_match
            )
        else:
            concurrency_valid = (
                update_article_outcome.disposition
                in {OutcomeDisposition.NOOP, OutcomeDisposition.REPLAYED}
                and article.version == request.expected_version
                and article.etag == request.if_match
            )
        valid = article.article_id == request.article_id and concurrency_valid
    elif isinstance(request, CreateVersionRequest):
        create_version_outcome = cast(CreateVersionOutcome, outcome)
        version = _validate_version(create_version_outcome.version)
        valid = (
            article.article_id == request.article_id
            and version.article_id == article.article_id
            and version.article_type is request.version.article_type
            and version.title == request.version.title
            and version.source_packet_version_id
            == request.version.source_packet_version_id
            and version.body_sha256 == request.version.body_sha256
            and version in history.versions
        )
    elif isinstance(request, GetVersionRequest):
        get_version_outcome = cast(GetVersionOutcome, outcome)
        version = _validate_version(get_version_outcome.version)
        valid = version.version_id == request.version_id and version in history.versions
    elif isinstance(request, UpdateVersionRequest):
        update_version_outcome = cast(UpdateVersionOutcome, outcome)
        version = _validate_version(update_version_outcome.version)
        if update_version_outcome.disposition is OutcomeDisposition.UPDATED:
            concurrency_valid = (
                version.version.value == request.expected_version.value + 1
                and version.etag != request.if_match
            )
        else:
            concurrency_valid = (
                update_version_outcome.disposition
                in {OutcomeDisposition.NOOP, OutcomeDisposition.REPLAYED}
                and version.version == request.expected_version
                and version.etag == request.if_match
            )
        valid = (
            version.version_id == request.version_id
            and version.body_sha256 == request.version.body_sha256
            and version in history.versions
            and concurrency_valid
        )
    if not valid:
        fail_article_lifecycle(ArticleLifecycleFailureCode.OUTCOME_MISMATCH)


@final
class ArticleLifecycleService:
    """Authorize before consuming one exact local recorded exchange."""

    __slots__ = ("_exchange",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        mode: ArticleLifecycleMode,
        exchange: ArticleLifecycleExchange,
    ) -> None:
        if (
            environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or mode is not ArticleLifecycleMode.RECORDED_TEST_ONLY
            or not callable(getattr(exchange, "exchange", None))
        ):
            fail_article_lifecycle()
        self._exchange = exchange

    def execute(
        self,
        *,
        grant: AuthorizationGrant,
        request: ArticleLifecycleRequest,
    ) -> ArticleLifecycleResult:
        operation, target = _request_parts(request)
        if (
            type(grant) is not AuthorizationGrant
            or grant.action.value != _ACTION_BY_OPERATION[operation]
            or grant.target.scope.site_id != target.site_id
            or grant.target.scope.resource_id != target.resource_id
        ):
            fail_article_lifecycle(ArticleLifecycleFailureCode.NOT_AUTHORIZED)
        _validate_request(request)

        observed: object = None
        unavailable = False
        try:
            observed = self._exchange.exchange(request)
        except Exception:
            unavailable = True
        if unavailable:
            fail_article_lifecycle(
                ArticleLifecycleFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
            )
        expected = _EXPECTED_OUTCOME[type(request)]
        if type(observed) is not expected:
            fail_article_lifecycle(ArticleLifecycleFailureCode.OUTCOME_MISMATCH)
        outcome = cast(ArticleLifecycleOutcome, observed)
        if outcome.operation is not operation:
            fail_article_lifecycle(ArticleLifecycleFailureCode.OUTCOME_MISMATCH)
        _validate_outcome(request, outcome)
        return ArticleLifecycleResult(
            operation=operation,
            outcome=outcome,
            execution=LifecycleExecution.RECORDED_ONLY,
            persistence=LifecycleExecution.NOT_EXECUTED,
            source_packet_verification=LifecycleExecution.NOT_EXECUTED,
            formal_verification=LifecycleExecution.NOT_EXECUTED,
            decision=LifecycleDecision.NOT_READY,
        )


__all__ = ["ArticleLifecycleService"]

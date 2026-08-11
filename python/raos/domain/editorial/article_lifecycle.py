"""Closed recorded article-lifecycle contract for the ST-0802 local seam.

This module models reviewable scripted exchanges only.  It does not authorize
state transitions, persistence, source-packet verification, review, approval,
publication, or any external action.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import re
from typing import NoReturn, TypeAlias
from uuid import UUID

from raos.domain.editorial.article_plan import (
    ArticlePlan,
    ArticlePlanState,
    ArticlePlanType,
)
from raos.domain.editorial.content_ast import (
    ArticleType as ContentAstArticleType,
    ContentAst,
    dump_content_ast_json,
)
from raos.domain.portfolio.workflow import (
    EntityVersion,
    IdempotencyKey,
    OutcomeDisposition,
    PageInfo,
    Pagination,
    StrongEtag,
    UtcTimestamp,
    WorkflowTarget,
    _RedactedValue,  # pyright: ignore[reportPrivateUsage]
    require_positive_exact_int,
    require_uuid7,
)


_ARTICLE_DISPLAY_ID = re.compile(r"ART-[A-Z0-9][A-Z0-9-]{0,126}\Z", re.ASCII)
_VERSION_DISPLAY_ID = re.compile(r"ARV-[A-Z0-9][A-Z0-9-]{0,126}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


class ArticleLifecycleOperation(str, Enum):
    CREATE_ARTICLE = "ED-005"
    LIST_ARTICLES = "ED-006"
    GET_ARTICLE = "ED-007"
    UPDATE_ARTICLE = "ED-008"
    CREATE_VERSION = "ED-009"
    GET_VERSION = "ED-010"
    UPDATE_VERSION = "ED-011"


class ArticleState(str, Enum):
    IDEA = "IDEA"
    PLANNED = "PLANNED"
    SOURCES_PENDING = "SOURCES_PENDING"
    PACKET_READY = "PACKET_READY"
    GENERATING = "GENERATING"
    DRAFT = "DRAFT"
    AUTO_REVIEW = "AUTO_REVIEW"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    APPROVED = "APPROVED"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    UPDATE_PENDING = "UPDATE_PENDING"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"


class ArticleVersionState(str, Enum):
    DRAFT = "DRAFT"
    AUTO_REVIEW = "AUTO_REVIEW"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class LifecycleExecution(str, Enum):
    RECORDED_ONLY = "RECORDED_ONLY"
    NOT_EXECUTED = "NOT_EXECUTED"


class ArticleLifecycleMode(str, Enum):
    RECORDED_TEST_ONLY = "RECORDED_TEST_ONLY"


class LifecycleDecision(str, Enum):
    NOT_READY = "NOT_READY"


class SourcePacketVerification(str, Enum):
    NOT_VERIFIED = "NOT_VERIFIED"


class ArticleLifecycleFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    OPERATION_DISABLED = "OPERATION_DISABLED"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    LOCAL_EXCHANGE_UNAVAILABLE = "LOCAL_EXCHANGE_UNAVAILABLE"
    OUTCOME_MISMATCH = "OUTCOME_MISMATCH"


@dataclass(frozen=True, slots=True, repr=False)
class ArticleLifecycleFailure(RuntimeError):
    code: ArticleLifecycleFailureCode

    def __post_init__(self) -> None:
        if type(self.code) is not ArticleLifecycleFailureCode:
            raise TypeError("invalid article lifecycle failure code")
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"ArticleLifecycleFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: object) -> NoReturn:
        del protocol
        raise TypeError("article lifecycle failure serialization is not supported")


def fail_article_lifecycle(
    code: ArticleLifecycleFailureCode = ArticleLifecycleFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise ArticleLifecycleFailure(code) from None


def _safe_text(value: object, *, maximum: int) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > maximum
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        fail_article_lifecycle()
    return value


@dataclass(frozen=True, slots=True, repr=False)
class ArticleDisplayId(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        if (
            type(self.value) is not str
            or _ARTICLE_DISPLAY_ID.fullmatch(self.value) is None
        ):
            fail_article_lifecycle()


@dataclass(frozen=True, slots=True, repr=False)
class VersionDisplayId(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        if (
            type(self.value) is not str
            or _VERSION_DISPLAY_ID.fullmatch(self.value) is None
        ):
            fail_article_lifecycle()


@dataclass(frozen=True, slots=True, repr=False)
class BodySha256(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _SHA256.fullmatch(self.value) is None:
            fail_article_lifecycle()

    @classmethod
    def of(cls, content_ast: ContentAst) -> BodySha256:
        if type(content_ast) is not ContentAst:
            fail_article_lifecycle()
        canonical = dump_content_ast_json(content_ast).encode("utf-8")
        return cls(hashlib.sha256(canonical).hexdigest())


PLAN_TYPE_TO_CONTENT_AST_TYPE: dict[ArticlePlanType, ContentAstArticleType] = {
    ArticlePlanType.SELECTION_GUIDE: ContentAstArticleType.selection_guide,
    ArticlePlanType.USE_CASE_RECOMMENDATION: (
        ContentAstArticleType.use_case_recommendation
    ),
    ArticlePlanType.PRODUCT_COMPARISON: ContentAstArticleType.product_comparison,
    ArticlePlanType.MODEL_DIFFERENCE: (
        ContentAstArticleType.model_generation_capacity_difference
    ),
    ArticlePlanType.CONDITION_FILTER: ContentAstArticleType.condition_filtering,
}


@dataclass(frozen=True, slots=True, repr=False)
class Article(_RedactedValue):
    article_id: UUID
    display_id: ArticleDisplayId
    plan_id: UUID
    site_id: UUID
    category_id: UUID
    article_type: ArticlePlanType
    state: ArticleState
    current_version_id: None
    published_version_id: None
    archived_at: None
    approval_id: None
    publication_id: None
    version: EntityVersion
    etag: StrongEtag
    created_at: UtcTimestamp
    updated_at: UtcTimestamp

    def __post_init__(self) -> None:
        require_uuid7(self.article_id)
        require_uuid7(self.plan_id)
        require_uuid7(self.site_id)
        require_uuid7(self.category_id)
        if (
            type(self.display_id) is not ArticleDisplayId
            or type(self.article_type) is not ArticlePlanType
            or self.state is not ArticleState.IDEA
            or self.current_version_id is not None
            or self.published_version_id is not None
            or self.archived_at is not None
            or self.approval_id is not None
            or self.publication_id is not None
            or type(self.version) is not EntityVersion
            or type(self.etag) is not StrongEtag
            or type(self.created_at) is not UtcTimestamp
            or type(self.updated_at) is not UtcTimestamp
            or self.updated_at.value < self.created_at.value
        ):
            fail_article_lifecycle()


@dataclass(frozen=True, slots=True, repr=False)
class VersionSnapshot(_RedactedValue):
    version_id: UUID
    display_id: VersionDisplayId
    article_id: UUID
    version_no: int
    article_type: ArticlePlanType
    title: str
    source_packet_version_id: UUID
    source_packet_verification: SourcePacketVerification
    based_on_version_id: UUID | None
    content_ast: ContentAst
    body_sha256: BodySha256
    state: ArticleVersionState
    submitted_at: None
    reviewed_at: None
    approved_at: None
    published_at: None
    version: EntityVersion
    etag: StrongEtag
    created_at: UtcTimestamp
    updated_at: UtcTimestamp

    def __post_init__(self) -> None:
        require_uuid7(self.version_id)
        require_uuid7(self.article_id)
        require_positive_exact_int(self.version_no)
        require_uuid7(self.source_packet_version_id)
        if self.based_on_version_id is not None:
            require_uuid7(self.based_on_version_id)
        if (
            type(self.display_id) is not VersionDisplayId
            or type(self.article_type) is not ArticlePlanType
            or type(self.title) is not str
            or type(self.content_ast) is not ContentAst
            or type(self.body_sha256) is not BodySha256
            or self.state is not ArticleVersionState.DRAFT
            or self.source_packet_verification
            is not SourcePacketVerification.NOT_VERIFIED
            or any(
                marker is not None
                for marker in (
                    self.submitted_at,
                    self.reviewed_at,
                    self.approved_at,
                    self.published_at,
                )
            )
            or type(self.version) is not EntityVersion
            or type(self.etag) is not StrongEtag
            or type(self.created_at) is not UtcTimestamp
            or type(self.updated_at) is not UtcTimestamp
            or self.updated_at.value < self.created_at.value
        ):
            fail_article_lifecycle()
        _safe_text(self.title, maximum=300)
        expected_type = PLAN_TYPE_TO_CONTENT_AST_TYPE[self.article_type]
        if (
            self.content_ast.article_id != str(self.article_id)
            or self.content_ast.article_version_id != str(self.version_id)
            or self.content_ast.article_type is not expected_type
            or self.content_ast.title != self.title
            or self.content_ast.source_packet_version_ref
            != str(self.source_packet_version_id)
            or self.body_sha256 != BodySha256.of(self.content_ast)
        ):
            fail_article_lifecycle()


@dataclass(frozen=True, slots=True, repr=False)
class ArticleVersionHistory(_RedactedValue):
    article_id: UUID
    versions: tuple[VersionSnapshot, ...]

    def __post_init__(self) -> None:
        require_uuid7(self.article_id)
        if type(self.versions) is not tuple:
            fail_article_lifecycle()
        seen_ids: set[UUID] = set()
        seen_numbers: set[int] = set()
        previous_number = 0
        for snapshot in self.versions:
            if (
                type(snapshot) is not VersionSnapshot
                or snapshot.article_id != self.article_id
                or snapshot.version_id in seen_ids
                or snapshot.version_no in seen_numbers
                or snapshot.version_no <= previous_number
                or (
                    snapshot.based_on_version_id is not None
                    and snapshot.based_on_version_id not in seen_ids
                )
            ):
                fail_article_lifecycle()
            seen_ids.add(snapshot.version_id)
            seen_numbers.add(snapshot.version_no)
            previous_number = snapshot.version_no


@dataclass(frozen=True, slots=True, repr=False)
class CreateArticleRequest(_RedactedValue):
    target: WorkflowTarget
    plan: ArticlePlan
    idempotency_key: IdempotencyKey

    operation = ArticleLifecycleOperation.CREATE_ARTICLE

    def __post_init__(self) -> None:
        if (
            type(self.target) is not WorkflowTarget
            or type(self.plan) is not ArticlePlan
            or type(self.idempotency_key) is not IdempotencyKey
            or self.plan.site_id != self.target.site_id
            or self.plan.plan_id != self.target.resource_id
            or self.plan.values.state is not ArticlePlanState.IDEA
        ):
            fail_article_lifecycle()


@dataclass(frozen=True, slots=True, repr=False)
class ListArticlesRequest(_RedactedValue):
    target: WorkflowTarget
    category_id: UUID
    article_type: ArticlePlanType
    pagination: Pagination

    operation = ArticleLifecycleOperation.LIST_ARTICLES

    def __post_init__(self) -> None:
        require_uuid7(self.category_id)
        if (
            type(self.target) is not WorkflowTarget
            or type(self.article_type) is not ArticlePlanType
            or type(self.pagination) is not Pagination
        ):
            fail_article_lifecycle()


@dataclass(frozen=True, slots=True, repr=False)
class GetArticleRequest(_RedactedValue):
    target: WorkflowTarget
    article_id: UUID

    operation = ArticleLifecycleOperation.GET_ARTICLE

    def __post_init__(self) -> None:
        require_uuid7(self.article_id)
        if (
            type(self.target) is not WorkflowTarget
            or self.article_id != self.target.resource_id
        ):
            fail_article_lifecycle()


@dataclass(frozen=True, slots=True, repr=False)
class UpdateArticleRequest(_RedactedValue):
    target: WorkflowTarget
    article_id: UUID
    expected_version: EntityVersion
    if_match: StrongEtag
    idempotency_key: IdempotencyKey
    state: ArticleState

    operation = ArticleLifecycleOperation.UPDATE_ARTICLE

    def __post_init__(self) -> None:
        require_uuid7(self.article_id)
        if (
            type(self.target) is not WorkflowTarget
            or self.article_id != self.target.resource_id
            or type(self.expected_version) is not EntityVersion
            or type(self.if_match) is not StrongEtag
            or type(self.idempotency_key) is not IdempotencyKey
            or self.state is not ArticleState.IDEA
        ):
            fail_article_lifecycle()


@dataclass(frozen=True, slots=True, repr=False)
class CreateVersionRequest(_RedactedValue):
    target: WorkflowTarget
    article_id: UUID
    idempotency_key: IdempotencyKey
    version: VersionSnapshot

    operation = ArticleLifecycleOperation.CREATE_VERSION

    def __post_init__(self) -> None:
        require_uuid7(self.article_id)
        if (
            type(self.target) is not WorkflowTarget
            or self.article_id != self.target.resource_id
            or type(self.idempotency_key) is not IdempotencyKey
            or type(self.version) is not VersionSnapshot
            or self.version.article_id != self.article_id
        ):
            fail_article_lifecycle()


@dataclass(frozen=True, slots=True, repr=False)
class GetVersionRequest(_RedactedValue):
    target: WorkflowTarget
    version_id: UUID

    operation = ArticleLifecycleOperation.GET_VERSION

    def __post_init__(self) -> None:
        require_uuid7(self.version_id)
        if (
            type(self.target) is not WorkflowTarget
            or self.version_id != self.target.resource_id
        ):
            fail_article_lifecycle()


@dataclass(frozen=True, slots=True, repr=False)
class UpdateVersionRequest(_RedactedValue):
    target: WorkflowTarget
    version_id: UUID
    expected_version: EntityVersion
    if_match: StrongEtag
    idempotency_key: IdempotencyKey
    version: VersionSnapshot

    operation = ArticleLifecycleOperation.UPDATE_VERSION

    def __post_init__(self) -> None:
        require_uuid7(self.version_id)
        if (
            type(self.target) is not WorkflowTarget
            or self.version_id != self.target.resource_id
            or type(self.expected_version) is not EntityVersion
            or type(self.if_match) is not StrongEtag
            or type(self.idempotency_key) is not IdempotencyKey
            or type(self.version) is not VersionSnapshot
            or self.version.version_id != self.version_id
        ):
            fail_article_lifecycle()


ArticleLifecycleRequest: TypeAlias = (
    CreateArticleRequest
    | ListArticlesRequest
    | GetArticleRequest
    | UpdateArticleRequest
    | CreateVersionRequest
    | GetVersionRequest
    | UpdateVersionRequest
)


def _validate_bundle(
    article: object,
    version: object,
    history: object,
) -> None:
    if (
        type(article) is not Article
        or type(version) is not VersionSnapshot
        or type(history) is not ArticleVersionHistory
        or version.article_id != article.article_id
        or history.article_id != article.article_id
        or version not in history.versions
    ):
        fail_article_lifecycle()


@dataclass(frozen=True, slots=True, repr=False)
class CreateArticleOutcome(_RedactedValue):
    article: Article
    initial_version: VersionSnapshot
    history: ArticleVersionHistory
    disposition: OutcomeDisposition

    operation = ArticleLifecycleOperation.CREATE_ARTICLE

    def __post_init__(self) -> None:
        _validate_bundle(self.article, self.initial_version, self.history)
        if (
            self.initial_version.version_no != 1
            or self.initial_version.based_on_version_id is not None
            or self.disposition
            not in {OutcomeDisposition.CREATED, OutcomeDisposition.REPLAYED}
        ):
            fail_article_lifecycle()


@dataclass(frozen=True, slots=True, repr=False)
class ListArticlesOutcome(_RedactedValue):
    items: tuple[Article, ...]
    page: PageInfo
    disposition: OutcomeDisposition

    operation = ArticleLifecycleOperation.LIST_ARTICLES

    def __post_init__(self) -> None:
        if (
            type(self.items) is not tuple
            or any(type(item) is not Article for item in self.items)
            or type(self.page) is not PageInfo
            or self.disposition is not OutcomeDisposition.LISTED
            or len({item.article_id for item in self.items}) != len(self.items)
            or tuple(item.article_id.int for item in self.items)
            != tuple(sorted(item.article_id.int for item in self.items))
        ):
            fail_article_lifecycle()


@dataclass(frozen=True, slots=True, repr=False)
class GetArticleOutcome(_RedactedValue):
    article: Article
    history: ArticleVersionHistory
    disposition: OutcomeDisposition

    operation = ArticleLifecycleOperation.GET_ARTICLE

    def __post_init__(self) -> None:
        if (
            type(self.article) is not Article
            or type(self.history) is not ArticleVersionHistory
            or self.history.article_id != self.article.article_id
            or self.disposition is not OutcomeDisposition.FOUND
        ):
            fail_article_lifecycle()


@dataclass(frozen=True, slots=True, repr=False)
class UpdateArticleOutcome(_RedactedValue):
    article: Article
    history: ArticleVersionHistory
    disposition: OutcomeDisposition

    operation = ArticleLifecycleOperation.UPDATE_ARTICLE

    def __post_init__(self) -> None:
        if (
            type(self.article) is not Article
            or type(self.history) is not ArticleVersionHistory
            or self.history.article_id != self.article.article_id
            or self.disposition
            not in {
                OutcomeDisposition.UPDATED,
                OutcomeDisposition.NOOP,
                OutcomeDisposition.REPLAYED,
            }
        ):
            fail_article_lifecycle()


@dataclass(frozen=True, slots=True, repr=False)
class CreateVersionOutcome(_RedactedValue):
    article: Article
    version: VersionSnapshot
    history: ArticleVersionHistory
    disposition: OutcomeDisposition

    operation = ArticleLifecycleOperation.CREATE_VERSION

    def __post_init__(self) -> None:
        _validate_bundle(self.article, self.version, self.history)
        if self.disposition not in {
            OutcomeDisposition.CREATED,
            OutcomeDisposition.REPLAYED,
        }:
            fail_article_lifecycle()


@dataclass(frozen=True, slots=True, repr=False)
class GetVersionOutcome(_RedactedValue):
    article: Article
    version: VersionSnapshot
    history: ArticleVersionHistory
    disposition: OutcomeDisposition

    operation = ArticleLifecycleOperation.GET_VERSION

    def __post_init__(self) -> None:
        _validate_bundle(self.article, self.version, self.history)
        if self.disposition is not OutcomeDisposition.FOUND:
            fail_article_lifecycle()


@dataclass(frozen=True, slots=True, repr=False)
class UpdateVersionOutcome(_RedactedValue):
    article: Article
    version: VersionSnapshot
    history: ArticleVersionHistory
    disposition: OutcomeDisposition

    operation = ArticleLifecycleOperation.UPDATE_VERSION

    def __post_init__(self) -> None:
        _validate_bundle(self.article, self.version, self.history)
        if self.disposition not in {
            OutcomeDisposition.UPDATED,
            OutcomeDisposition.NOOP,
            OutcomeDisposition.REPLAYED,
        }:
            fail_article_lifecycle()


ArticleLifecycleOutcome: TypeAlias = (
    CreateArticleOutcome
    | ListArticlesOutcome
    | GetArticleOutcome
    | UpdateArticleOutcome
    | CreateVersionOutcome
    | GetVersionOutcome
    | UpdateVersionOutcome
)


@dataclass(frozen=True, slots=True, repr=False)
class ArticleLifecycleResult(_RedactedValue):
    operation: ArticleLifecycleOperation
    outcome: ArticleLifecycleOutcome
    execution: LifecycleExecution
    persistence: LifecycleExecution
    source_packet_verification: LifecycleExecution
    formal_verification: LifecycleExecution
    decision: LifecycleDecision

    def __post_init__(self) -> None:
        if (
            type(self.operation) is not ArticleLifecycleOperation
            or type(self.outcome)
            not in {
                CreateArticleOutcome,
                ListArticlesOutcome,
                GetArticleOutcome,
                UpdateArticleOutcome,
                CreateVersionOutcome,
                GetVersionOutcome,
                UpdateVersionOutcome,
            }
            or self.outcome.operation is not self.operation
            or self.execution is not LifecycleExecution.RECORDED_ONLY
            or self.persistence is not LifecycleExecution.NOT_EXECUTED
            or self.source_packet_verification is not LifecycleExecution.NOT_EXECUTED
            or self.formal_verification is not LifecycleExecution.NOT_EXECUTED
            or self.decision is not LifecycleDecision.NOT_READY
        ):
            fail_article_lifecycle()


__all__ = [
    "PLAN_TYPE_TO_CONTENT_AST_TYPE",
    "Article",
    "ArticleDisplayId",
    "ArticleLifecycleFailure",
    "ArticleLifecycleFailureCode",
    "ArticleLifecycleMode",
    "ArticleLifecycleOperation",
    "ArticleLifecycleOutcome",
    "ArticleLifecycleRequest",
    "ArticleLifecycleResult",
    "ArticleState",
    "ArticleVersionHistory",
    "ArticleVersionState",
    "BodySha256",
    "CreateArticleOutcome",
    "CreateArticleRequest",
    "CreateVersionOutcome",
    "CreateVersionRequest",
    "GetArticleOutcome",
    "GetArticleRequest",
    "GetVersionOutcome",
    "GetVersionRequest",
    "LifecycleDecision",
    "LifecycleExecution",
    "ListArticlesRequest",
    "ListArticlesOutcome",
    "SourcePacketVerification",
    "UpdateArticleRequest",
    "UpdateArticleOutcome",
    "UpdateVersionRequest",
    "UpdateVersionOutcome",
    "VersionDisplayId",
    "VersionSnapshot",
    "fail_article_lifecycle",
]

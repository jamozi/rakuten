"""Editorial-only ArticlePlan projection for the ST-0501 recorded seam."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias
from uuid import UUID

from raos.domain.portfolio.workflow import (
    DisplayId,
    EntityVersion,
    IdempotencyKey,
    OutcomeDisposition,
    PageInfo,
    Pagination,
    PortfolioOperation,
    StrongEtag,
    UtcTimestamp,
    WorkflowTarget,
    _RedactedValue,
    _text,
    fail_portfolio_workflow,
    require_uuid7,
)


class ArticlePlanState(str, Enum):
    IDEA = "IDEA"
    PLANNED = "PLANNED"
    SOURCES_PENDING = "SOURCES_PENDING"
    PACKET_READY = "PACKET_READY"
    GENERATING = "GENERATING"
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"
    ARCHIVED = "ARCHIVED"


class ArticlePlanType(str, Enum):
    SELECTION_GUIDE = "SELECTION_GUIDE"
    USE_CASE_RECOMMENDATION = "USE_CASE_RECOMMENDATION"
    PRODUCT_COMPARISON = "PRODUCT_COMPARISON"
    MODEL_DIFFERENCE = "MODEL_DIFFERENCE"
    CONDITION_FILTER = "CONDITION_FILTER"


# This graph is descriptive canonical vocabulary only.  The local seam permits
# IDEA records and IDEA-preserving edits; every transition remains disabled.
ARTICLE_PLAN_TRANSITIONS: tuple[tuple[ArticlePlanState, ArticlePlanState], ...] = (
    (ArticlePlanState.IDEA, ArticlePlanState.PLANNED),
    (ArticlePlanState.PLANNED, ArticlePlanState.SOURCES_PENDING),
    (ArticlePlanState.SOURCES_PENDING, ArticlePlanState.PACKET_READY),
    (ArticlePlanState.PACKET_READY, ArticlePlanState.GENERATING),
    (ArticlePlanState.GENERATING, ArticlePlanState.DRAFT),
    (ArticlePlanState.DRAFT, ArticlePlanState.IN_REVIEW),
    (ArticlePlanState.IN_REVIEW, ArticlePlanState.APPROVED),
    (ArticlePlanState.APPROVED, ArticlePlanState.ARCHIVED),
    (ArticlePlanState.IDEA, ArticlePlanState.CANCELLED),
    (ArticlePlanState.PLANNED, ArticlePlanState.CANCELLED),
    (ArticlePlanState.SOURCES_PENDING, ArticlePlanState.CANCELLED),
    (ArticlePlanState.PACKET_READY, ArticlePlanState.CANCELLED),
    (ArticlePlanState.GENERATING, ArticlePlanState.CANCELLED),
    (ArticlePlanState.DRAFT, ArticlePlanState.CANCELLED),
    (ArticlePlanState.IN_REVIEW, ArticlePlanState.CANCELLED),
)


@dataclass(frozen=True, slots=True, repr=False)
class ArticlePlanGraph(_RedactedValue):
    site_id: UUID
    category_id: UUID
    intent_cluster_id: UUID
    primary_keyword_id: UUID

    def __post_init__(self) -> None:
        require_uuid7(self.site_id)
        require_uuid7(self.category_id)
        require_uuid7(self.intent_cluster_id)
        require_uuid7(self.primary_keyword_id)


@dataclass(frozen=True, slots=True, repr=False)
class ArticlePlanValues(_RedactedValue):
    graph: ArticlePlanGraph
    plan_type: ArticlePlanType
    working_title: str
    objective: str
    priority: int
    state: ArticlePlanState

    def __post_init__(self) -> None:
        if (
            type(self.graph) is not ArticlePlanGraph
            or type(self.plan_type) is not ArticlePlanType
            or type(self.priority) is not int
            or not 0 <= self.priority <= 100
            or self.state is not ArticlePlanState.IDEA
        ):
            fail_portfolio_workflow()
        _text(self.working_title, maximum=500)
        _text(self.objective, maximum=2000)


@dataclass(frozen=True, slots=True, repr=False)
class ArticlePlan(_RedactedValue):
    plan_id: UUID
    display_id: DisplayId
    values: ArticlePlanValues
    version: EntityVersion
    etag: StrongEtag
    created_at: UtcTimestamp
    updated_at: UtcTimestamp

    def __post_init__(self) -> None:
        require_uuid7(self.plan_id)
        if (
            type(self.display_id) is not DisplayId
            or self.display_id.prefix != "PLAN"
            or type(self.values) is not ArticlePlanValues
            or type(self.version) is not EntityVersion
            or type(self.etag) is not StrongEtag
            or type(self.created_at) is not UtcTimestamp
            or type(self.updated_at) is not UtcTimestamp
            or self.updated_at.value < self.created_at.value
        ):
            fail_portfolio_workflow()

    @property
    def site_id(self) -> UUID:
        return self.values.graph.site_id


@dataclass(frozen=True, slots=True, repr=False)
class ListArticlePlansRequest(_RedactedValue):
    target: WorkflowTarget
    category_id: UUID
    pagination: Pagination

    operation = PortfolioOperation.LIST_ARTICLE_PLANS

    def __post_init__(self) -> None:
        if (
            type(self.target) is not WorkflowTarget
            or type(self.pagination) is not Pagination
        ):
            fail_portfolio_workflow()
        require_uuid7(self.category_id)


@dataclass(frozen=True, slots=True, repr=False)
class CreateArticlePlanRequest(_RedactedValue):
    target: WorkflowTarget
    idempotency_key: IdempotencyKey
    values: ArticlePlanValues

    operation = PortfolioOperation.CREATE_ARTICLE_PLAN

    def __post_init__(self) -> None:
        if (
            type(self.target) is not WorkflowTarget
            or type(self.idempotency_key) is not IdempotencyKey
            or type(self.values) is not ArticlePlanValues
        ):
            fail_portfolio_workflow()
        if self.values.graph.site_id != self.target.site_id:
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class GetArticlePlanRequest(_RedactedValue):
    target: WorkflowTarget
    plan_id: UUID

    operation = PortfolioOperation.GET_ARTICLE_PLAN

    def __post_init__(self) -> None:
        if type(self.target) is not WorkflowTarget:
            fail_portfolio_workflow()
        require_uuid7(self.plan_id)


@dataclass(frozen=True, slots=True, repr=False)
class UpdateArticlePlanRequest(_RedactedValue):
    target: WorkflowTarget
    plan_id: UUID
    expected_version: EntityVersion
    if_match: StrongEtag
    idempotency_key: IdempotencyKey
    values: ArticlePlanValues

    operation = PortfolioOperation.UPDATE_ARTICLE_PLAN

    def __post_init__(self) -> None:
        if (
            type(self.target) is not WorkflowTarget
            or type(self.expected_version) is not EntityVersion
            or type(self.if_match) is not StrongEtag
            or type(self.idempotency_key) is not IdempotencyKey
            or type(self.values) is not ArticlePlanValues
        ):
            fail_portfolio_workflow()
        require_uuid7(self.plan_id)
        if self.values.graph.site_id != self.target.site_id:
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class ListArticlePlansOutcome(_RedactedValue):
    items: tuple[ArticlePlan, ...]
    page: PageInfo
    disposition: OutcomeDisposition

    operation = PortfolioOperation.LIST_ARTICLE_PLANS

    def __post_init__(self) -> None:
        if (
            type(self.items) is not tuple
            or any(type(item) is not ArticlePlan for item in self.items)
            or type(self.page) is not PageInfo
            or self.disposition is not OutcomeDisposition.LISTED
        ):
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class CreateArticlePlanOutcome(_RedactedValue):
    item: ArticlePlan
    disposition: OutcomeDisposition

    operation = PortfolioOperation.CREATE_ARTICLE_PLAN

    def __post_init__(self) -> None:
        if type(self.item) is not ArticlePlan or self.disposition not in {
            OutcomeDisposition.CREATED,
            OutcomeDisposition.REPLAYED,
        }:
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class GetArticlePlanOutcome(_RedactedValue):
    item: ArticlePlan
    disposition: OutcomeDisposition

    operation = PortfolioOperation.GET_ARTICLE_PLAN

    def __post_init__(self) -> None:
        if (
            type(self.item) is not ArticlePlan
            or self.disposition is not OutcomeDisposition.FOUND
        ):
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class UpdateArticlePlanOutcome(_RedactedValue):
    item: ArticlePlan
    disposition: OutcomeDisposition

    operation = PortfolioOperation.UPDATE_ARTICLE_PLAN

    def __post_init__(self) -> None:
        if type(self.item) is not ArticlePlan or self.disposition not in {
            OutcomeDisposition.UPDATED,
            OutcomeDisposition.NOOP,
            OutcomeDisposition.REPLAYED,
        }:
            fail_portfolio_workflow()


ArticlePlanWorkflowRequest: TypeAlias = (
    ListArticlePlansRequest
    | CreateArticlePlanRequest
    | GetArticlePlanRequest
    | UpdateArticlePlanRequest
)
ArticlePlanWorkflowOutcome: TypeAlias = (
    ListArticlePlansOutcome
    | CreateArticlePlanOutcome
    | GetArticlePlanOutcome
    | UpdateArticlePlanOutcome
)


__all__ = [
    "ARTICLE_PLAN_TRANSITIONS",
    "ArticlePlan",
    "ArticlePlanGraph",
    "ArticlePlanState",
    "ArticlePlanType",
    "ArticlePlanValues",
    "ArticlePlanWorkflowOutcome",
    "ArticlePlanWorkflowRequest",
    "CreateArticlePlanOutcome",
    "CreateArticlePlanRequest",
    "GetArticlePlanOutcome",
    "GetArticlePlanRequest",
    "ListArticlePlansOutcome",
    "ListArticlePlansRequest",
    "UpdateArticlePlanOutcome",
    "UpdateArticlePlanRequest",
]

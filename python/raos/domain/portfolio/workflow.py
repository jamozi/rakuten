"""Closed, immutable portfolio workflow contract for ST-0501.

The types in this module describe one local recorded exchange.  They are not a
repository, persistence model, or authority to perform a portfolio operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import re
from typing import NoReturn, SupportsIndex, TypeAlias
from uuid import RFC_4122, UUID


_DISPLAY_ID = re.compile(r"(?:CAT|INT|KW|PLAN)-[A-Z0-9][A-Z0-9-]{0,126}\Z", re.ASCII)
_SAFE_TOKEN = re.compile(r"[!-~]+\Z", re.ASCII)
_STRONG_ETAG = re.compile(r'"[A-Za-z0-9._:-]{1,128}"\Z', re.ASCII)
_CODE = re.compile(r"[a-z0-9][a-z0-9_-]{0,62}\Z", re.ASCII)
_LOCALE = re.compile(r"[a-z]{2}(?:-[A-Z]{2})?\Z", re.ASCII)
_REDACTED = "<redacted-portfolio-workflow>"
_MAX_EXACT_INTEGER = (1 << 63) - 1


class PortfolioEntityKind(str, Enum):
    CATEGORY = "CATEGORY"
    INTENT_CLUSTER = "INTENT_CLUSTER"
    KEYWORD = "KEYWORD"
    ARTICLE_PLAN = "ARTICLE_PLAN"


class PortfolioOperation(str, Enum):
    LIST_CATEGORIES = "CATG-001"
    CREATE_CATEGORY = "CATG-002"
    GET_CATEGORY = "CATG-003"
    UPDATE_CATEGORY = "CATG-004"
    LIST_INTENT_CLUSTERS = "INTENT-001"
    CREATE_INTENT_CLUSTER = "INTENT-002"
    GET_INTENT_CLUSTER = "INTENT-003"
    UPDATE_INTENT_CLUSTER = "INTENT-004"
    LIST_KEYWORDS = "KEY-001"
    CREATE_KEYWORD = "KEY-002"
    GET_KEYWORD = "KEY-003"
    UPDATE_KEYWORD = "KEY-004"
    LIST_ARTICLE_PLANS = "ED-001"
    CREATE_ARTICLE_PLAN = "ED-002"
    GET_ARTICLE_PLAN = "ED-003"
    UPDATE_ARTICLE_PLAN = "ED-004"


class OutcomeDisposition(str, Enum):
    LISTED = "LISTED"
    CREATED = "CREATED"
    FOUND = "FOUND"
    UPDATED = "UPDATED"
    NOOP = "NOOP"
    REPLAYED = "REPLAYED"


class PortfolioWorkflowFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    LOCAL_EXCHANGE_UNAVAILABLE = "LOCAL_EXCHANGE_UNAVAILABLE"
    OUTCOME_MISMATCH = "OUTCOME_MISMATCH"


class CategoryRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    PROHIBITED = "PROHIBITED"


class CategoryStage(str, Enum):
    CANDIDATE = "CANDIDATE"
    RESEARCH = "RESEARCH"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    RETIRED = "RETIRED"
    REJECTED = "REJECTED"


class IntentType(str, Enum):
    SELECTION_GUIDE = "SELECTION_GUIDE"
    USE_CASE = "USE_CASE"
    COMPARISON = "COMPARISON"
    MODEL_DIFFERENCE = "MODEL_DIFFERENCE"
    CONDITION_FILTER = "CONDITION_FILTER"
    INFORMATIONAL_SUPPORT = "INFORMATIONAL_SUPPORT"


class PortfolioRecordStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    RETIRED = "RETIRED"


class KeywordStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    RETIRED = "RETIRED"
    BLOCKED = "BLOCKED"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("portfolio workflow serialization is not supported")


@dataclass(frozen=True, slots=True, repr=False)
class PortfolioWorkflowFailure(RuntimeError):
    code: PortfolioWorkflowFailureCode

    def __post_init__(self) -> None:
        if type(self.code) is not PortfolioWorkflowFailureCode:
            raise TypeError("invalid portfolio workflow failure code")
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"PortfolioWorkflowFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("portfolio workflow failure serialization is not supported")


def fail_portfolio_workflow(
    code: PortfolioWorkflowFailureCode = PortfolioWorkflowFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise PortfolioWorkflowFailure(code) from None


def require_uuid7(value: object) -> UUID:
    if type(value) is not UUID or value.version != 7 or value.variant != RFC_4122:
        fail_portfolio_workflow()
    return value


def require_positive_exact_int(value: object) -> int:
    if type(value) is not int or not 0 < value <= _MAX_EXACT_INTEGER:
        fail_portfolio_workflow()
    return value


def require_nonnegative_exact_int(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_EXACT_INTEGER:
        fail_portfolio_workflow()
    return value


def _text(value: object, *, maximum: int, empty: bool = False) -> str:
    if (
        type(value) is not str
        or len(value) > maximum
        or (not empty and not value)
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        fail_portfolio_workflow()
    return value


@dataclass(frozen=True, slots=True, repr=False)
class DisplayId(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _DISPLAY_ID.fullmatch(self.value) is None:
            fail_portfolio_workflow()

    @property
    def prefix(self) -> str:
        return self.value.partition("-")[0]


@dataclass(frozen=True, slots=True, repr=False)
class UtcTimestamp(_RedactedValue):
    value: datetime

    def __post_init__(self) -> None:
        if (
            type(self.value) is not datetime
            or self.value.tzinfo is not timezone.utc
            or self.value.fold != 0
        ):
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class EntityVersion(_RedactedValue):
    value: int

    def __post_init__(self) -> None:
        require_nonnegative_exact_int(self.value)


@dataclass(frozen=True, slots=True, repr=False)
class StrongEtag(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _STRONG_ETAG.fullmatch(self.value) is None:
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class IdempotencyKey(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        if (
            type(self.value) is not str
            or not 8 <= len(self.value) <= 200
            or _SAFE_TOKEN.fullmatch(self.value) is None
        ):
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class PageCursor(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        if (
            type(self.value) is not str
            or not 1 <= len(self.value) <= 1024
            or _SAFE_TOKEN.fullmatch(self.value) is None
        ):
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class PageLimit(_RedactedValue):
    value: int

    def __post_init__(self) -> None:
        if type(self.value) is not int or not 1 <= self.value <= 200:
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class WorkflowTarget(_RedactedValue):
    environment: str
    site_id: UUID
    resource_id: UUID

    def __post_init__(self) -> None:
        if type(self.environment) is not str or self.environment != "TEST_ONLY":
            fail_portfolio_workflow()
        require_uuid7(self.site_id)
        require_uuid7(self.resource_id)


@dataclass(frozen=True, slots=True, repr=False)
class Pagination(_RedactedValue):
    cursor: PageCursor | None
    limit: PageLimit

    def __post_init__(self) -> None:
        if (self.cursor is not None and type(self.cursor) is not PageCursor) or type(
            self.limit
        ) is not PageLimit:
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class PageInfo(_RedactedValue):
    next_cursor: PageCursor | None
    has_more: bool
    limit: PageLimit

    def __post_init__(self) -> None:
        if (
            (self.next_cursor is not None and type(self.next_cursor) is not PageCursor)
            or type(self.has_more) is not bool
            or type(self.limit) is not PageLimit
            or self.has_more != (self.next_cursor is not None)
        ):
            fail_portfolio_workflow()


def _record_common(
    *,
    entity_id: object,
    display_id: object,
    prefix: str,
    site_id: object,
    version: object,
    etag: object,
    created_at: object,
    updated_at: object,
) -> None:
    require_uuid7(entity_id)
    require_uuid7(site_id)
    if (
        type(display_id) is not DisplayId
        or display_id.prefix != prefix
        or type(version) is not EntityVersion
        or type(etag) is not StrongEtag
        or type(created_at) is not UtcTimestamp
        or type(updated_at) is not UtcTimestamp
        or updated_at.value < created_at.value
    ):
        fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class CategoryValues(_RedactedValue):
    category_code: str
    name: str
    description: str | None
    parent_category_id: UUID | None
    risk: CategoryRisk
    stage: CategoryStage
    article_limit: int | None

    def __post_init__(self) -> None:
        if (
            type(self.category_code) is not str
            or _CODE.fullmatch(self.category_code) is None
        ):
            fail_portfolio_workflow()
        _text(self.name, maximum=160)
        if self.description is not None:
            _text(self.description, maximum=1000)
        if self.parent_category_id is not None:
            require_uuid7(self.parent_category_id)
        if (
            type(self.risk) is not CategoryRisk
            or type(self.stage) is not CategoryStage
            or self.stage in {CategoryStage.APPROVED, CategoryStage.ACTIVE}
            or (
                self.article_limit is not None
                and (
                    type(self.article_limit) is not int
                    or not 0 <= self.article_limit <= _MAX_EXACT_INTEGER
                )
            )
        ):
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class Category(_RedactedValue):
    category_id: UUID
    display_id: DisplayId
    site_id: UUID
    values: CategoryValues
    version: EntityVersion
    etag: StrongEtag
    created_at: UtcTimestamp
    updated_at: UtcTimestamp

    def __post_init__(self) -> None:
        _record_common(
            entity_id=self.category_id,
            display_id=self.display_id,
            prefix="CAT",
            site_id=self.site_id,
            version=self.version,
            etag=self.etag,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
        if (
            type(self.values) is not CategoryValues
            or self.values.parent_category_id == self.category_id
        ):
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class IntentClusterValues(_RedactedValue):
    category_id: UUID
    cluster_code: str
    name: str
    description: str | None
    intent_type: IntentType
    status: PortfolioRecordStatus

    def __post_init__(self) -> None:
        require_uuid7(self.category_id)
        if (
            type(self.cluster_code) is not str
            or _CODE.fullmatch(self.cluster_code) is None
        ):
            fail_portfolio_workflow()
        _text(self.name, maximum=160)
        if self.description is not None:
            _text(self.description, maximum=1000)
        if (
            type(self.intent_type) is not IntentType
            or type(self.status) is not PortfolioRecordStatus
        ):
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class IntentCluster(_RedactedValue):
    intent_cluster_id: UUID
    display_id: DisplayId
    site_id: UUID
    values: IntentClusterValues
    version: EntityVersion
    etag: StrongEtag
    created_at: UtcTimestamp
    updated_at: UtcTimestamp

    def __post_init__(self) -> None:
        _record_common(
            entity_id=self.intent_cluster_id,
            display_id=self.display_id,
            prefix="INT",
            site_id=self.site_id,
            version=self.version,
            etag=self.etag,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
        if type(self.values) is not IntentClusterValues:
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class KeywordValues(_RedactedValue):
    text: str
    locale: str
    status: KeywordStatus
    sensitive_query: bool

    def __post_init__(self) -> None:
        _text(self.text, maximum=500)
        if (
            type(self.locale) is not str
            or _LOCALE.fullmatch(self.locale) is None
            or type(self.status) is not KeywordStatus
            or type(self.sensitive_query) is not bool
        ):
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class Keyword(_RedactedValue):
    keyword_id: UUID
    display_id: DisplayId
    site_id: UUID
    values: KeywordValues
    normalized_text: str
    version: EntityVersion
    etag: StrongEtag
    created_at: UtcTimestamp
    updated_at: UtcTimestamp

    def __post_init__(self) -> None:
        _record_common(
            entity_id=self.keyword_id,
            display_id=self.display_id,
            prefix="KW",
            site_id=self.site_id,
            version=self.version,
            etag=self.etag,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
        if type(self.values) is not KeywordValues:
            fail_portfolio_workflow()
        _text(self.normalized_text, maximum=500)


@dataclass(frozen=True, slots=True, repr=False)
class ListCategoriesRequest(_RedactedValue):
    target: WorkflowTarget
    pagination: Pagination

    operation = PortfolioOperation.LIST_CATEGORIES

    def __post_init__(self) -> None:
        if (
            type(self.target) is not WorkflowTarget
            or type(self.pagination) is not Pagination
        ):
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class CreateCategoryRequest(_RedactedValue):
    target: WorkflowTarget
    idempotency_key: IdempotencyKey
    values: CategoryValues

    operation = PortfolioOperation.CREATE_CATEGORY

    def __post_init__(self) -> None:
        if (
            type(self.target) is not WorkflowTarget
            or type(self.idempotency_key) is not IdempotencyKey
            or type(self.values) is not CategoryValues
        ):
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class GetCategoryRequest(_RedactedValue):
    target: WorkflowTarget
    category_id: UUID

    operation = PortfolioOperation.GET_CATEGORY

    def __post_init__(self) -> None:
        if type(self.target) is not WorkflowTarget:
            fail_portfolio_workflow()
        require_uuid7(self.category_id)


@dataclass(frozen=True, slots=True, repr=False)
class UpdateCategoryRequest(_RedactedValue):
    target: WorkflowTarget
    category_id: UUID
    expected_version: EntityVersion
    if_match: StrongEtag
    idempotency_key: IdempotencyKey
    values: CategoryValues

    operation = PortfolioOperation.UPDATE_CATEGORY

    def __post_init__(self) -> None:
        if (
            type(self.target) is not WorkflowTarget
            or type(self.expected_version) is not EntityVersion
            or type(self.if_match) is not StrongEtag
            or type(self.idempotency_key) is not IdempotencyKey
            or type(self.values) is not CategoryValues
        ):
            fail_portfolio_workflow()
        require_uuid7(self.category_id)


@dataclass(frozen=True, slots=True, repr=False)
class ListIntentClustersRequest(_RedactedValue):
    target: WorkflowTarget
    category_id: UUID
    pagination: Pagination

    operation = PortfolioOperation.LIST_INTENT_CLUSTERS

    def __post_init__(self) -> None:
        if (
            type(self.target) is not WorkflowTarget
            or type(self.pagination) is not Pagination
        ):
            fail_portfolio_workflow()
        require_uuid7(self.category_id)


@dataclass(frozen=True, slots=True, repr=False)
class CreateIntentClusterRequest(_RedactedValue):
    target: WorkflowTarget
    idempotency_key: IdempotencyKey
    values: IntentClusterValues

    operation = PortfolioOperation.CREATE_INTENT_CLUSTER

    def __post_init__(self) -> None:
        if (
            type(self.target) is not WorkflowTarget
            or type(self.idempotency_key) is not IdempotencyKey
            or type(self.values) is not IntentClusterValues
        ):
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class GetIntentClusterRequest(_RedactedValue):
    target: WorkflowTarget
    intent_cluster_id: UUID

    operation = PortfolioOperation.GET_INTENT_CLUSTER

    def __post_init__(self) -> None:
        if type(self.target) is not WorkflowTarget:
            fail_portfolio_workflow()
        require_uuid7(self.intent_cluster_id)


@dataclass(frozen=True, slots=True, repr=False)
class UpdateIntentClusterRequest(_RedactedValue):
    target: WorkflowTarget
    intent_cluster_id: UUID
    expected_version: EntityVersion
    if_match: StrongEtag
    idempotency_key: IdempotencyKey
    values: IntentClusterValues

    operation = PortfolioOperation.UPDATE_INTENT_CLUSTER

    def __post_init__(self) -> None:
        if (
            type(self.target) is not WorkflowTarget
            or type(self.expected_version) is not EntityVersion
            or type(self.if_match) is not StrongEtag
            or type(self.idempotency_key) is not IdempotencyKey
            or type(self.values) is not IntentClusterValues
        ):
            fail_portfolio_workflow()
        require_uuid7(self.intent_cluster_id)


@dataclass(frozen=True, slots=True, repr=False)
class ListKeywordsRequest(_RedactedValue):
    target: WorkflowTarget
    pagination: Pagination

    operation = PortfolioOperation.LIST_KEYWORDS

    def __post_init__(self) -> None:
        if (
            type(self.target) is not WorkflowTarget
            or type(self.pagination) is not Pagination
        ):
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class CreateKeywordRequest(_RedactedValue):
    target: WorkflowTarget
    idempotency_key: IdempotencyKey
    values: KeywordValues

    operation = PortfolioOperation.CREATE_KEYWORD

    def __post_init__(self) -> None:
        if (
            type(self.target) is not WorkflowTarget
            or type(self.idempotency_key) is not IdempotencyKey
            or type(self.values) is not KeywordValues
        ):
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class GetKeywordRequest(_RedactedValue):
    target: WorkflowTarget
    keyword_id: UUID

    operation = PortfolioOperation.GET_KEYWORD

    def __post_init__(self) -> None:
        if type(self.target) is not WorkflowTarget:
            fail_portfolio_workflow()
        require_uuid7(self.keyword_id)


@dataclass(frozen=True, slots=True, repr=False)
class UpdateKeywordRequest(_RedactedValue):
    target: WorkflowTarget
    keyword_id: UUID
    expected_version: EntityVersion
    if_match: StrongEtag
    idempotency_key: IdempotencyKey
    values: KeywordValues

    operation = PortfolioOperation.UPDATE_KEYWORD

    def __post_init__(self) -> None:
        if (
            type(self.target) is not WorkflowTarget
            or type(self.expected_version) is not EntityVersion
            or type(self.if_match) is not StrongEtag
            or type(self.idempotency_key) is not IdempotencyKey
            or type(self.values) is not KeywordValues
        ):
            fail_portfolio_workflow()
        require_uuid7(self.keyword_id)


@dataclass(frozen=True, slots=True, repr=False)
class ListCategoriesOutcome(_RedactedValue):
    items: tuple[Category, ...]
    page: PageInfo
    disposition: OutcomeDisposition

    operation = PortfolioOperation.LIST_CATEGORIES

    def __post_init__(self) -> None:
        if (
            type(self.items) is not tuple
            or any(type(item) is not Category for item in self.items)
            or type(self.page) is not PageInfo
            or self.disposition is not OutcomeDisposition.LISTED
        ):
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class CreateCategoryOutcome(_RedactedValue):
    item: Category
    disposition: OutcomeDisposition

    operation = PortfolioOperation.CREATE_CATEGORY

    def __post_init__(self) -> None:
        if type(self.item) is not Category or self.disposition not in {
            OutcomeDisposition.CREATED,
            OutcomeDisposition.REPLAYED,
        }:
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class GetCategoryOutcome(_RedactedValue):
    item: Category
    disposition: OutcomeDisposition

    operation = PortfolioOperation.GET_CATEGORY

    def __post_init__(self) -> None:
        if (
            type(self.item) is not Category
            or self.disposition is not OutcomeDisposition.FOUND
        ):
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class UpdateCategoryOutcome(_RedactedValue):
    item: Category
    disposition: OutcomeDisposition

    operation = PortfolioOperation.UPDATE_CATEGORY

    def __post_init__(self) -> None:
        if type(self.item) is not Category or self.disposition not in {
            OutcomeDisposition.UPDATED,
            OutcomeDisposition.NOOP,
            OutcomeDisposition.REPLAYED,
        }:
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class ListIntentClustersOutcome(_RedactedValue):
    items: tuple[IntentCluster, ...]
    page: PageInfo
    disposition: OutcomeDisposition

    operation = PortfolioOperation.LIST_INTENT_CLUSTERS

    def __post_init__(self) -> None:
        if (
            type(self.items) is not tuple
            or any(type(item) is not IntentCluster for item in self.items)
            or type(self.page) is not PageInfo
            or self.disposition is not OutcomeDisposition.LISTED
        ):
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class CreateIntentClusterOutcome(_RedactedValue):
    item: IntentCluster
    disposition: OutcomeDisposition

    operation = PortfolioOperation.CREATE_INTENT_CLUSTER

    def __post_init__(self) -> None:
        if type(self.item) is not IntentCluster or self.disposition not in {
            OutcomeDisposition.CREATED,
            OutcomeDisposition.REPLAYED,
        }:
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class GetIntentClusterOutcome(_RedactedValue):
    item: IntentCluster
    disposition: OutcomeDisposition

    operation = PortfolioOperation.GET_INTENT_CLUSTER

    def __post_init__(self) -> None:
        if (
            type(self.item) is not IntentCluster
            or self.disposition is not OutcomeDisposition.FOUND
        ):
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class UpdateIntentClusterOutcome(_RedactedValue):
    item: IntentCluster
    disposition: OutcomeDisposition

    operation = PortfolioOperation.UPDATE_INTENT_CLUSTER

    def __post_init__(self) -> None:
        if type(self.item) is not IntentCluster or self.disposition not in {
            OutcomeDisposition.UPDATED,
            OutcomeDisposition.NOOP,
            OutcomeDisposition.REPLAYED,
        }:
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class ListKeywordsOutcome(_RedactedValue):
    items: tuple[Keyword, ...]
    page: PageInfo
    disposition: OutcomeDisposition

    operation = PortfolioOperation.LIST_KEYWORDS

    def __post_init__(self) -> None:
        if (
            type(self.items) is not tuple
            or any(type(item) is not Keyword for item in self.items)
            or type(self.page) is not PageInfo
            or self.disposition is not OutcomeDisposition.LISTED
        ):
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class CreateKeywordOutcome(_RedactedValue):
    item: Keyword
    disposition: OutcomeDisposition

    operation = PortfolioOperation.CREATE_KEYWORD

    def __post_init__(self) -> None:
        if type(self.item) is not Keyword or self.disposition not in {
            OutcomeDisposition.CREATED,
            OutcomeDisposition.REPLAYED,
        }:
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class GetKeywordOutcome(_RedactedValue):
    item: Keyword
    disposition: OutcomeDisposition

    operation = PortfolioOperation.GET_KEYWORD

    def __post_init__(self) -> None:
        if (
            type(self.item) is not Keyword
            or self.disposition is not OutcomeDisposition.FOUND
        ):
            fail_portfolio_workflow()


@dataclass(frozen=True, slots=True, repr=False)
class UpdateKeywordOutcome(_RedactedValue):
    item: Keyword
    disposition: OutcomeDisposition

    operation = PortfolioOperation.UPDATE_KEYWORD

    def __post_init__(self) -> None:
        if type(self.item) is not Keyword or self.disposition not in {
            OutcomeDisposition.UPDATED,
            OutcomeDisposition.NOOP,
            OutcomeDisposition.REPLAYED,
        }:
            fail_portfolio_workflow()


CorePortfolioWorkflowRequest: TypeAlias = (
    ListCategoriesRequest
    | CreateCategoryRequest
    | GetCategoryRequest
    | UpdateCategoryRequest
    | ListIntentClustersRequest
    | CreateIntentClusterRequest
    | GetIntentClusterRequest
    | UpdateIntentClusterRequest
    | ListKeywordsRequest
    | CreateKeywordRequest
    | GetKeywordRequest
    | UpdateKeywordRequest
)
CorePortfolioWorkflowOutcome: TypeAlias = (
    ListCategoriesOutcome
    | CreateCategoryOutcome
    | GetCategoryOutcome
    | UpdateCategoryOutcome
    | ListIntentClustersOutcome
    | CreateIntentClusterOutcome
    | GetIntentClusterOutcome
    | UpdateIntentClusterOutcome
    | ListKeywordsOutcome
    | CreateKeywordOutcome
    | GetKeywordOutcome
    | UpdateKeywordOutcome
)


__all__ = [
    "Category",
    "CategoryRisk",
    "CategoryStage",
    "CategoryValues",
    "CorePortfolioWorkflowOutcome",
    "CorePortfolioWorkflowRequest",
    "CreateCategoryOutcome",
    "CreateCategoryRequest",
    "CreateIntentClusterOutcome",
    "CreateIntentClusterRequest",
    "CreateKeywordOutcome",
    "CreateKeywordRequest",
    "DisplayId",
    "EntityVersion",
    "GetCategoryOutcome",
    "GetCategoryRequest",
    "GetIntentClusterOutcome",
    "GetIntentClusterRequest",
    "GetKeywordOutcome",
    "GetKeywordRequest",
    "IdempotencyKey",
    "IntentCluster",
    "IntentClusterValues",
    "IntentType",
    "Keyword",
    "KeywordStatus",
    "KeywordValues",
    "ListCategoriesOutcome",
    "ListCategoriesRequest",
    "ListIntentClustersOutcome",
    "ListIntentClustersRequest",
    "ListKeywordsOutcome",
    "ListKeywordsRequest",
    "OutcomeDisposition",
    "PageCursor",
    "PageInfo",
    "PageLimit",
    "Pagination",
    "PortfolioEntityKind",
    "PortfolioOperation",
    "PortfolioRecordStatus",
    "PortfolioWorkflowFailure",
    "PortfolioWorkflowFailureCode",
    "StrongEtag",
    "UpdateCategoryOutcome",
    "UpdateCategoryRequest",
    "UpdateIntentClusterOutcome",
    "UpdateIntentClusterRequest",
    "UpdateKeywordOutcome",
    "UpdateKeywordRequest",
    "UtcTimestamp",
    "WorkflowTarget",
    "fail_portfolio_workflow",
    "require_nonnegative_exact_int",
    "require_positive_exact_int",
    "require_uuid7",
]

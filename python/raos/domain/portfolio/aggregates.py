"""Exact immutable PORTFOLIO persistence domain values for ST-0308."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import NoReturn
import unicodedata

from raos.domain.iam.ids import (
    PrincipalId,
)
from raos.domain.ops.ids import (
    ObjectArtifactId,
)
from raos.domain.portfolio.enums import (
    ActionCandidateActionType,
    ActionCandidateStatus,
    ActionCandidateTargetEntityType,
    CategoryRiskClass,
    CategoryStage,
    IntentClusterIntentType,
    IntentClusterKeywordBindingKeywordRole,
    IntentClusterStatus,
    KeywordMetricObservationDevice,
    KeywordMetricObservationMetricType,
    KeywordStatus,
    OpportunityAssessmentAssessmentType,
    OpportunityAssessmentDecision,
    SiteStatus,
)
from raos.domain.portfolio.ids import (
    ActionCandidateId,
    CategoryId,
    IntentClusterId,
    KeywordId,
    KeywordMetricObservationId,
    OpportunityAssessmentId,
    SiteId,
)
from raos.domain.portfolio.values import (
    ActionCandidateRationaleJson,
    CategoryEntryCriteriaJson,
    IntentClusterDecisionRequirementsJson,
    OpportunityAssessmentBusinessComponentsJson,
    OpportunityAssessmentComplianceComponentsJson,
    OpportunityAssessmentEditorialComponentsJson,
    SitePublicSettingsJson,
)
from raos.domain.shared.identity import (
    AssessedByActorId,
    SecondaryEntityId,
    TargetEntityId,
)
from raos.domain.shared.persistence import (
    AggregateVersion,
    AwareUtcDateTime,
    YenMinor,
)
from raos.domain.shared.events import DomainEvent
from raos.domain.shared.identity import EntityId
from raos.domain.shared.persistence import PendingEventBuffer

_MAX_BIGINT = (1 << 63) - 1


def _invalid() -> NoReturn:
    raise ValueError("INVALID_PORTFOLIO_PERSISTENCE_VALUE") from None


def _text(value: object) -> None:
    if (
        type(value) is not str
        or not value
        or len(value) > 4096
        or value != value.strip()
        or unicodedata.normalize("NFC", value) != value
        or any(unicodedata.category(character).startswith("C") for character in value)
    ):
        _invalid()


def _integer(value: object) -> None:
    if type(value) is not int or not 0 <= value <= _MAX_BIGINT:
        _invalid()


def _decimal(value: object) -> None:
    if type(value) is not Decimal or not value.is_finite():
        _invalid()


def _nominal(value: object, module: str, name: str) -> None:
    if (
        not isinstance(value, EntityId)
        or type(value).__module__ != module
        or type(value).__name__ != name
    ):
        _invalid()


@dataclass(frozen=True, slots=True, repr=False)
class ActionCandidateState:
    id: ActionCandidateId
    display_id: str
    site_id: SiteId
    category_id: CategoryId | None
    action_type: ActionCandidateActionType
    target_entity_type: ActionCandidateTargetEntityType
    target_entity_id: TargetEntityId | None
    secondary_entity_id: SecondaryEntityId | None
    source_signal: str
    expected_incremental_profit_jpy: YenMinor | None
    urgency_score: Decimal
    confidence: Decimal
    priority_score: Decimal
    status: ActionCandidateStatus
    rationale: ActionCandidateRationaleJson
    generated_at: AwareUtcDateTime
    expires_at: AwareUtcDateTime | None
    decided_by_principal_id: PrincipalId | None
    decided_at: AwareUtcDateTime | None
    decision_note: str | None
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    lock_version: AggregateVersion

    def __post_init__(self) -> None:
        if type(self.id) is not ActionCandidateId:
            _invalid()
        _text(self.display_id)
        if type(self.site_id) is not SiteId:
            _invalid()
        if self.category_id is not None:
            if type(self.category_id) is not CategoryId:
                _invalid()
        if type(self.action_type) is not ActionCandidateActionType:
            _invalid()
        if type(self.target_entity_type) is not ActionCandidateTargetEntityType:
            _invalid()
        if self.target_entity_id is not None:
            if type(self.target_entity_id) is not TargetEntityId:
                _invalid()
        if self.secondary_entity_id is not None:
            if type(self.secondary_entity_id) is not SecondaryEntityId:
                _invalid()
        _text(self.source_signal)
        if self.expected_incremental_profit_jpy is not None:
            if type(self.expected_incremental_profit_jpy) is not YenMinor:
                _invalid()
        _decimal(self.urgency_score)
        _decimal(self.confidence)
        _decimal(self.priority_score)
        if type(self.status) is not ActionCandidateStatus:
            _invalid()
        if type(self.rationale) is not ActionCandidateRationaleJson:
            _invalid()
        if type(self.generated_at) is not AwareUtcDateTime:
            _invalid()
        if self.expires_at is not None:
            if type(self.expires_at) is not AwareUtcDateTime:
                _invalid()
        if self.decided_by_principal_id is not None:
            if type(self.decided_by_principal_id) is not PrincipalId:
                _invalid()
        if self.decided_at is not None:
            if type(self.decided_at) is not AwareUtcDateTime:
                _invalid()
        if self.decision_note is not None:
            _text(self.decision_note)
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()

    def __repr__(self) -> str:
        return "ActionCandidateState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class CategoryState:
    id: CategoryId
    display_id: str
    site_id: SiteId
    parent_category_id: CategoryId | None
    category_code: str
    name: str
    description: str | None
    risk_class: CategoryRiskClass
    stage: CategoryStage
    article_limit: int | None
    approved_at: AwareUtcDateTime | None
    approved_by_principal_id: PrincipalId | None
    entry_criteria: CategoryEntryCriteriaJson
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    lock_version: AggregateVersion

    def __post_init__(self) -> None:
        if type(self.id) is not CategoryId:
            _invalid()
        _text(self.display_id)
        if type(self.site_id) is not SiteId:
            _invalid()
        if self.parent_category_id is not None:
            if type(self.parent_category_id) is not CategoryId:
                _invalid()
        _text(self.category_code)
        _text(self.name)
        if self.description is not None:
            _text(self.description)
        if type(self.risk_class) is not CategoryRiskClass:
            _invalid()
        if type(self.stage) is not CategoryStage:
            _invalid()
        if self.article_limit is not None:
            _integer(self.article_limit)
        if self.approved_at is not None:
            if type(self.approved_at) is not AwareUtcDateTime:
                _invalid()
        if self.approved_by_principal_id is not None:
            if type(self.approved_by_principal_id) is not PrincipalId:
                _invalid()
        if type(self.entry_criteria) is not CategoryEntryCriteriaJson:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()

    def __repr__(self) -> str:
        return "CategoryState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class IntentClusterState:
    id: IntentClusterId
    display_id: str
    category_id: CategoryId
    cluster_code: str
    name: str
    description: str
    intent_type: IntentClusterIntentType
    status: IntentClusterStatus
    decision_requirements: IntentClusterDecisionRequirementsJson
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    lock_version: AggregateVersion

    def __post_init__(self) -> None:
        if type(self.id) is not IntentClusterId:
            _invalid()
        _text(self.display_id)
        if type(self.category_id) is not CategoryId:
            _invalid()
        _text(self.cluster_code)
        _text(self.name)
        _text(self.description)
        if type(self.intent_type) is not IntentClusterIntentType:
            _invalid()
        if type(self.status) is not IntentClusterStatus:
            _invalid()
        if (
            type(self.decision_requirements)
            is not IntentClusterDecisionRequirementsJson
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()

    def __repr__(self) -> str:
        return "IntentClusterState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class IntentClusterKeywordBinding:
    intent_cluster_id: IntentClusterId
    keyword_id: KeywordId
    keyword_role: IntentClusterKeywordBindingKeywordRole
    priority: int
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.intent_cluster_id) is not IntentClusterId:
            _invalid()
        if type(self.keyword_id) is not KeywordId:
            _invalid()
        if type(self.keyword_role) is not IntentClusterKeywordBindingKeywordRole:
            _invalid()
        _integer(self.priority)
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "IntentClusterKeywordBinding(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class KeywordState:
    id: KeywordId
    display_id: str
    site_id: SiteId
    display_text: str
    normalized_text: str
    locale: str
    status: KeywordStatus
    sensitive_query: bool
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    lock_version: AggregateVersion

    def __post_init__(self) -> None:
        if type(self.id) is not KeywordId:
            _invalid()
        _text(self.display_id)
        if type(self.site_id) is not SiteId:
            _invalid()
        _text(self.display_text)
        _text(self.normalized_text)
        _text(self.locale)
        if type(self.status) is not KeywordStatus:
            _invalid()
        if type(self.sensitive_query) is not bool:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()

    def __repr__(self) -> str:
        return "KeywordState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class KeywordMetricObservation:
    id: KeywordMetricObservationId
    keyword_id: KeywordId
    provider_code: str
    metric_type: KeywordMetricObservationMetricType
    metric_value: Decimal
    unit: str
    country_code: str
    device: KeywordMetricObservationDevice
    observed_date: date
    confidence: Decimal | None
    raw_artifact_id: ObjectArtifactId | None
    ingested_at: AwareUtcDateTime
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not KeywordMetricObservationId:
            _invalid()
        if type(self.keyword_id) is not KeywordId:
            _invalid()
        _text(self.provider_code)
        if type(self.metric_type) is not KeywordMetricObservationMetricType:
            _invalid()
        _decimal(self.metric_value)
        _text(self.unit)
        _text(self.country_code)
        if type(self.device) is not KeywordMetricObservationDevice:
            _invalid()
        if type(self.observed_date) is not date:
            _invalid()
        if self.confidence is not None:
            _decimal(self.confidence)
        if self.raw_artifact_id is not None:
            if type(self.raw_artifact_id) is not ObjectArtifactId:
                _invalid()
        if type(self.ingested_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "KeywordMetricObservation(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class OpportunityAssessment:
    id: OpportunityAssessmentId
    display_id: str
    category_id: CategoryId
    intent_cluster_id: IntentClusterId | None
    keyword_id: KeywordId | None
    assessment_type: OpportunityAssessmentAssessmentType
    formula_version: str
    editorial_feasibility_score: Decimal
    business_opportunity_score: Decimal
    compliance_risk_score: Decimal
    overall_priority_score: Decimal
    decision: OpportunityAssessmentDecision
    editorial_components: OpportunityAssessmentEditorialComponentsJson
    business_components: OpportunityAssessmentBusinessComponentsJson
    compliance_components: OpportunityAssessmentComplianceComponentsJson
    assessed_at: AwareUtcDateTime
    assessed_by_actor_type: str
    assessed_by_actor_id: AssessedByActorId | None
    expires_at: AwareUtcDateTime | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not OpportunityAssessmentId:
            _invalid()
        _text(self.display_id)
        if type(self.category_id) is not CategoryId:
            _invalid()
        if self.intent_cluster_id is not None:
            if type(self.intent_cluster_id) is not IntentClusterId:
                _invalid()
        if self.keyword_id is not None:
            if type(self.keyword_id) is not KeywordId:
                _invalid()
        if type(self.assessment_type) is not OpportunityAssessmentAssessmentType:
            _invalid()
        _text(self.formula_version)
        _decimal(self.editorial_feasibility_score)
        _decimal(self.business_opportunity_score)
        _decimal(self.compliance_risk_score)
        _decimal(self.overall_priority_score)
        if type(self.decision) is not OpportunityAssessmentDecision:
            _invalid()
        if (
            type(self.editorial_components)
            is not OpportunityAssessmentEditorialComponentsJson
        ):
            _invalid()
        if (
            type(self.business_components)
            is not OpportunityAssessmentBusinessComponentsJson
        ):
            _invalid()
        if (
            type(self.compliance_components)
            is not OpportunityAssessmentComplianceComponentsJson
        ):
            _invalid()
        if type(self.assessed_at) is not AwareUtcDateTime:
            _invalid()
        _text(self.assessed_by_actor_type)
        if self.assessed_by_actor_id is not None:
            if type(self.assessed_by_actor_id) is not AssessedByActorId:
                _invalid()
        if self.expires_at is not None:
            if type(self.expires_at) is not AwareUtcDateTime:
                _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "OpportunityAssessment(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class SiteState:
    id: SiteId
    display_id: str
    site_code: str
    name: str
    primary_domain: str
    brand_name: str
    locale: str
    timezone: str
    currency: str
    status: SiteStatus
    public_settings: SitePublicSettingsJson
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    lock_version: AggregateVersion

    def __post_init__(self) -> None:
        if type(self.id) is not SiteId:
            _invalid()
        _text(self.display_id)
        _text(self.site_code)
        _text(self.name)
        _text(self.primary_domain)
        _text(self.brand_name)
        _text(self.locale)
        _text(self.timezone)
        _text(self.currency)
        if type(self.status) is not SiteStatus:
            _invalid()
        if type(self.public_settings) is not SitePublicSettingsJson:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()

    def __repr__(self) -> str:
        return "SiteState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ActionCandidate:
    state: ActionCandidateState
    _event_buffer: PendingEventBuffer[DomainEvent] = field(
        default_factory=PendingEventBuffer, init=False, compare=False
    )

    def __post_init__(self) -> None:
        if type(self.state) is not ActionCandidateState:
            _invalid()

    def pending_events(self) -> tuple[DomainEvent, ...]:
        return self._event_buffer.pending_events()

    def acknowledge_events(self, event_ids: tuple[object, ...]) -> None:
        from uuid import UUID

        if type(event_ids) is not tuple or any(
            type(item) is not UUID for item in event_ids
        ):
            _invalid()
        self._event_buffer.acknowledge_events(event_ids)  # type: ignore[arg-type]

    def _record_event(self, event: DomainEvent) -> None:
        self._event_buffer.record(event)

    def _restore_acknowledged_events(self) -> None:
        self._event_buffer._restore_acknowledged()

    def _finish_acknowledged_events(self) -> None:
        self._event_buffer._finish_acknowledged()

    def __repr__(self) -> str:
        return "ActionCandidate(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class Category:
    state: CategoryState

    def __post_init__(self) -> None:
        if type(self.state) is not CategoryState:
            _invalid()

    def __repr__(self) -> str:
        return "Category(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class IntentCluster:
    state: IntentClusterState
    intent_cluster_keyword_rows: tuple[IntentClusterKeywordBinding, ...] = ()

    def __post_init__(self) -> None:
        if type(self.state) is not IntentClusterState:
            _invalid()
        if type(self.intent_cluster_keyword_rows) is not tuple or any(
            type(item) is not IntentClusterKeywordBinding
            for item in self.intent_cluster_keyword_rows
        ):
            _invalid()
        if any(
            item.intent_cluster_id.value != self.state.id.value
            for item in self.intent_cluster_keyword_rows
        ):
            _invalid()

    def __repr__(self) -> str:
        return "IntentCluster(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class Keyword:
    state: KeywordState
    keyword_metric_observation_rows: tuple[KeywordMetricObservation, ...] = ()

    def __post_init__(self) -> None:
        if type(self.state) is not KeywordState:
            _invalid()
        if type(self.keyword_metric_observation_rows) is not tuple or any(
            type(item) is not KeywordMetricObservation
            for item in self.keyword_metric_observation_rows
        ):
            _invalid()
        if any(
            item.keyword_id.value != self.state.id.value
            for item in self.keyword_metric_observation_rows
        ):
            _invalid()

    def __repr__(self) -> str:
        return "Keyword(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class Site:
    state: SiteState

    def __post_init__(self) -> None:
        if type(self.state) is not SiteState:
            _invalid()

    def __repr__(self) -> str:
        return "Site(<redacted>)"


__all__ = [
    "ActionCandidate",
    "ActionCandidateState",
    "Category",
    "CategoryState",
    "IntentCluster",
    "IntentClusterKeywordBinding",
    "IntentClusterState",
    "Keyword",
    "KeywordMetricObservation",
    "KeywordState",
    "OpportunityAssessment",
    "Site",
    "SiteState",
]

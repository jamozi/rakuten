"""Explicit fail-closed scalar mappers for the ST-0308 PORTFOLIO slice."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from raos.adapters.persistence.sqlalchemy.physical_constraints import (
    install_mapper_physical_constraint_guards,
)
from raos.domain.portfolio.aggregates import (
    ActionCandidateState,
    CategoryState,
    IntentClusterKeywordBinding,
    IntentClusterState,
    KeywordMetricObservation,
    KeywordState,
    OpportunityAssessment,
    SiteState,
)
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
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode


def _corrupt() -> PersistenceError:
    return PersistenceError(PersistenceErrorCode.STORAGE_CORRUPTION)


ActionCandidateStateScalars = tuple[
    ActionCandidateId,
    str,
    SiteId,
    CategoryId | None,
    ActionCandidateActionType,
    ActionCandidateTargetEntityType,
    TargetEntityId | None,
    SecondaryEntityId | None,
    str,
    YenMinor | None,
    Decimal,
    Decimal,
    Decimal,
    ActionCandidateStatus,
    ActionCandidateRationaleJson,
    AwareUtcDateTime,
    AwareUtcDateTime | None,
    PrincipalId | None,
    AwareUtcDateTime | None,
    str | None,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AggregateVersion,
]


def map_portfolio_action_candidate_from_row(
    *,
    id: ActionCandidateId,
    display_id: str,
    site_id: SiteId,
    category_id: CategoryId | None,
    action_type: ActionCandidateActionType,
    target_entity_type: ActionCandidateTargetEntityType,
    target_entity_id: TargetEntityId | None,
    secondary_entity_id: SecondaryEntityId | None,
    source_signal: str,
    expected_incremental_profit_jpy: YenMinor | None,
    urgency_score: Decimal,
    confidence: Decimal,
    priority_score: Decimal,
    status: ActionCandidateStatus,
    rationale: ActionCandidateRationaleJson,
    generated_at: AwareUtcDateTime,
    expires_at: AwareUtcDateTime | None,
    decided_by_principal_id: PrincipalId | None,
    decided_at: AwareUtcDateTime | None,
    decision_note: str | None,
    created_at: AwareUtcDateTime,
    updated_at: AwareUtcDateTime,
    lock_version: AggregateVersion,
) -> ActionCandidateState:
    try:
        return ActionCandidateState(
            id=id,
            display_id=display_id,
            site_id=site_id,
            category_id=category_id,
            action_type=action_type,
            target_entity_type=target_entity_type,
            target_entity_id=target_entity_id,
            secondary_entity_id=secondary_entity_id,
            source_signal=source_signal,
            expected_incremental_profit_jpy=expected_incremental_profit_jpy,
            urgency_score=urgency_score,
            confidence=confidence,
            priority_score=priority_score,
            status=status,
            rationale=rationale,
            generated_at=generated_at,
            expires_at=expires_at,
            decided_by_principal_id=decided_by_principal_id,
            decided_at=decided_at,
            decision_note=decision_note,
            created_at=created_at,
            updated_at=updated_at,
            lock_version=lock_version,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_portfolio_action_candidate_to_row(
    value: ActionCandidateState,
) -> ActionCandidateStateScalars:
    if type(value) is not ActionCandidateState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.site_id,
        value.category_id,
        value.action_type,
        value.target_entity_type,
        value.target_entity_id,
        value.secondary_entity_id,
        value.source_signal,
        value.expected_incremental_profit_jpy,
        value.urgency_score,
        value.confidence,
        value.priority_score,
        value.status,
        value.rationale,
        value.generated_at,
        value.expires_at,
        value.decided_by_principal_id,
        value.decided_at,
        value.decision_note,
        value.created_at,
        value.updated_at,
        value.lock_version,
    )


CategoryStateScalars = tuple[
    CategoryId,
    str,
    SiteId,
    CategoryId | None,
    str,
    str,
    str | None,
    CategoryRiskClass,
    CategoryStage,
    int | None,
    AwareUtcDateTime | None,
    PrincipalId | None,
    CategoryEntryCriteriaJson,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AggregateVersion,
]


def map_portfolio_category_from_row(
    *,
    id: CategoryId,
    display_id: str,
    site_id: SiteId,
    parent_category_id: CategoryId | None,
    category_code: str,
    name: str,
    description: str | None,
    risk_class: CategoryRiskClass,
    stage: CategoryStage,
    article_limit: int | None,
    approved_at: AwareUtcDateTime | None,
    approved_by_principal_id: PrincipalId | None,
    entry_criteria: CategoryEntryCriteriaJson,
    created_at: AwareUtcDateTime,
    updated_at: AwareUtcDateTime,
    lock_version: AggregateVersion,
) -> CategoryState:
    try:
        return CategoryState(
            id=id,
            display_id=display_id,
            site_id=site_id,
            parent_category_id=parent_category_id,
            category_code=category_code,
            name=name,
            description=description,
            risk_class=risk_class,
            stage=stage,
            article_limit=article_limit,
            approved_at=approved_at,
            approved_by_principal_id=approved_by_principal_id,
            entry_criteria=entry_criteria,
            created_at=created_at,
            updated_at=updated_at,
            lock_version=lock_version,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_portfolio_category_to_row(value: CategoryState) -> CategoryStateScalars:
    if type(value) is not CategoryState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.site_id,
        value.parent_category_id,
        value.category_code,
        value.name,
        value.description,
        value.risk_class,
        value.stage,
        value.article_limit,
        value.approved_at,
        value.approved_by_principal_id,
        value.entry_criteria,
        value.created_at,
        value.updated_at,
        value.lock_version,
    )


IntentClusterStateScalars = tuple[
    IntentClusterId,
    str,
    CategoryId,
    str,
    str,
    str,
    IntentClusterIntentType,
    IntentClusterStatus,
    IntentClusterDecisionRequirementsJson,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AggregateVersion,
]


def map_portfolio_intent_cluster_from_row(
    *,
    id: IntentClusterId,
    display_id: str,
    category_id: CategoryId,
    cluster_code: str,
    name: str,
    description: str,
    intent_type: IntentClusterIntentType,
    status: IntentClusterStatus,
    decision_requirements: IntentClusterDecisionRequirementsJson,
    created_at: AwareUtcDateTime,
    updated_at: AwareUtcDateTime,
    lock_version: AggregateVersion,
) -> IntentClusterState:
    try:
        return IntentClusterState(
            id=id,
            display_id=display_id,
            category_id=category_id,
            cluster_code=cluster_code,
            name=name,
            description=description,
            intent_type=intent_type,
            status=status,
            decision_requirements=decision_requirements,
            created_at=created_at,
            updated_at=updated_at,
            lock_version=lock_version,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_portfolio_intent_cluster_to_row(
    value: IntentClusterState,
) -> IntentClusterStateScalars:
    if type(value) is not IntentClusterState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.category_id,
        value.cluster_code,
        value.name,
        value.description,
        value.intent_type,
        value.status,
        value.decision_requirements,
        value.created_at,
        value.updated_at,
        value.lock_version,
    )


IntentClusterKeywordBindingScalars = tuple[
    IntentClusterId,
    KeywordId,
    IntentClusterKeywordBindingKeywordRole,
    int,
    AwareUtcDateTime,
]


def map_portfolio_intent_cluster_keyword_from_row(
    *,
    intent_cluster_id: IntentClusterId,
    keyword_id: KeywordId,
    keyword_role: IntentClusterKeywordBindingKeywordRole,
    priority: int,
    created_at: AwareUtcDateTime,
) -> IntentClusterKeywordBinding:
    try:
        return IntentClusterKeywordBinding(
            intent_cluster_id=intent_cluster_id,
            keyword_id=keyword_id,
            keyword_role=keyword_role,
            priority=priority,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_portfolio_intent_cluster_keyword_to_row(
    value: IntentClusterKeywordBinding,
) -> IntentClusterKeywordBindingScalars:
    if type(value) is not IntentClusterKeywordBinding:
        raise _corrupt() from None
    return (
        value.intent_cluster_id,
        value.keyword_id,
        value.keyword_role,
        value.priority,
        value.created_at,
    )


KeywordStateScalars = tuple[
    KeywordId,
    str,
    SiteId,
    str,
    str,
    str,
    KeywordStatus,
    bool,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AggregateVersion,
]


def map_portfolio_keyword_from_row(
    *,
    id: KeywordId,
    display_id: str,
    site_id: SiteId,
    display_text: str,
    normalized_text: str,
    locale: str,
    status: KeywordStatus,
    sensitive_query: bool,
    created_at: AwareUtcDateTime,
    updated_at: AwareUtcDateTime,
    lock_version: AggregateVersion,
) -> KeywordState:
    try:
        return KeywordState(
            id=id,
            display_id=display_id,
            site_id=site_id,
            display_text=display_text,
            normalized_text=normalized_text,
            locale=locale,
            status=status,
            sensitive_query=sensitive_query,
            created_at=created_at,
            updated_at=updated_at,
            lock_version=lock_version,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_portfolio_keyword_to_row(value: KeywordState) -> KeywordStateScalars:
    if type(value) is not KeywordState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.site_id,
        value.display_text,
        value.normalized_text,
        value.locale,
        value.status,
        value.sensitive_query,
        value.created_at,
        value.updated_at,
        value.lock_version,
    )


KeywordMetricObservationScalars = tuple[
    KeywordMetricObservationId,
    KeywordId,
    str,
    KeywordMetricObservationMetricType,
    Decimal,
    str,
    str,
    KeywordMetricObservationDevice,
    date,
    Decimal | None,
    ObjectArtifactId | None,
    AwareUtcDateTime,
    AwareUtcDateTime,
]


def map_portfolio_keyword_metric_observation_from_row(
    *,
    id: KeywordMetricObservationId,
    keyword_id: KeywordId,
    provider_code: str,
    metric_type: KeywordMetricObservationMetricType,
    metric_value: Decimal,
    unit: str,
    country_code: str,
    device: KeywordMetricObservationDevice,
    observed_date: date,
    confidence: Decimal | None,
    raw_artifact_id: ObjectArtifactId | None,
    ingested_at: AwareUtcDateTime,
    created_at: AwareUtcDateTime,
) -> KeywordMetricObservation:
    try:
        return KeywordMetricObservation(
            id=id,
            keyword_id=keyword_id,
            provider_code=provider_code,
            metric_type=metric_type,
            metric_value=metric_value,
            unit=unit,
            country_code=country_code,
            device=device,
            observed_date=observed_date,
            confidence=confidence,
            raw_artifact_id=raw_artifact_id,
            ingested_at=ingested_at,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_portfolio_keyword_metric_observation_to_row(
    value: KeywordMetricObservation,
) -> KeywordMetricObservationScalars:
    if type(value) is not KeywordMetricObservation:
        raise _corrupt() from None
    return (
        value.id,
        value.keyword_id,
        value.provider_code,
        value.metric_type,
        value.metric_value,
        value.unit,
        value.country_code,
        value.device,
        value.observed_date,
        value.confidence,
        value.raw_artifact_id,
        value.ingested_at,
        value.created_at,
    )


OpportunityAssessmentScalars = tuple[
    OpportunityAssessmentId,
    str,
    CategoryId,
    IntentClusterId | None,
    KeywordId | None,
    OpportunityAssessmentAssessmentType,
    str,
    Decimal,
    Decimal,
    Decimal,
    Decimal,
    OpportunityAssessmentDecision,
    OpportunityAssessmentEditorialComponentsJson,
    OpportunityAssessmentBusinessComponentsJson,
    OpportunityAssessmentComplianceComponentsJson,
    AwareUtcDateTime,
    str,
    AssessedByActorId | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
]


def map_portfolio_opportunity_assessment_from_row(
    *,
    id: OpportunityAssessmentId,
    display_id: str,
    category_id: CategoryId,
    intent_cluster_id: IntentClusterId | None,
    keyword_id: KeywordId | None,
    assessment_type: OpportunityAssessmentAssessmentType,
    formula_version: str,
    editorial_feasibility_score: Decimal,
    business_opportunity_score: Decimal,
    compliance_risk_score: Decimal,
    overall_priority_score: Decimal,
    decision: OpportunityAssessmentDecision,
    editorial_components: OpportunityAssessmentEditorialComponentsJson,
    business_components: OpportunityAssessmentBusinessComponentsJson,
    compliance_components: OpportunityAssessmentComplianceComponentsJson,
    assessed_at: AwareUtcDateTime,
    assessed_by_actor_type: str,
    assessed_by_actor_id: AssessedByActorId | None,
    expires_at: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
) -> OpportunityAssessment:
    try:
        return OpportunityAssessment(
            id=id,
            display_id=display_id,
            category_id=category_id,
            intent_cluster_id=intent_cluster_id,
            keyword_id=keyword_id,
            assessment_type=assessment_type,
            formula_version=formula_version,
            editorial_feasibility_score=editorial_feasibility_score,
            business_opportunity_score=business_opportunity_score,
            compliance_risk_score=compliance_risk_score,
            overall_priority_score=overall_priority_score,
            decision=decision,
            editorial_components=editorial_components,
            business_components=business_components,
            compliance_components=compliance_components,
            assessed_at=assessed_at,
            assessed_by_actor_type=assessed_by_actor_type,
            assessed_by_actor_id=assessed_by_actor_id,
            expires_at=expires_at,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_portfolio_opportunity_assessment_to_row(
    value: OpportunityAssessment,
) -> OpportunityAssessmentScalars:
    if type(value) is not OpportunityAssessment:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.category_id,
        value.intent_cluster_id,
        value.keyword_id,
        value.assessment_type,
        value.formula_version,
        value.editorial_feasibility_score,
        value.business_opportunity_score,
        value.compliance_risk_score,
        value.overall_priority_score,
        value.decision,
        value.editorial_components,
        value.business_components,
        value.compliance_components,
        value.assessed_at,
        value.assessed_by_actor_type,
        value.assessed_by_actor_id,
        value.expires_at,
        value.created_at,
    )


SiteStateScalars = tuple[
    SiteId,
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    SiteStatus,
    SitePublicSettingsJson,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AggregateVersion,
]


def map_portfolio_site_from_row(
    *,
    id: SiteId,
    display_id: str,
    site_code: str,
    name: str,
    primary_domain: str,
    brand_name: str,
    locale: str,
    timezone: str,
    currency: str,
    status: SiteStatus,
    public_settings: SitePublicSettingsJson,
    created_at: AwareUtcDateTime,
    updated_at: AwareUtcDateTime,
    lock_version: AggregateVersion,
) -> SiteState:
    try:
        return SiteState(
            id=id,
            display_id=display_id,
            site_code=site_code,
            name=name,
            primary_domain=primary_domain,
            brand_name=brand_name,
            locale=locale,
            timezone=timezone,
            currency=currency,
            status=status,
            public_settings=public_settings,
            created_at=created_at,
            updated_at=updated_at,
            lock_version=lock_version,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_portfolio_site_to_row(value: SiteState) -> SiteStateScalars:
    if type(value) is not SiteState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.site_code,
        value.name,
        value.primary_domain,
        value.brand_name,
        value.locale,
        value.timezone,
        value.currency,
        value.status,
        value.public_settings,
        value.created_at,
        value.updated_at,
        value.lock_version,
    )


__all__ = [
    "ActionCandidateStateScalars",
    "CategoryStateScalars",
    "IntentClusterKeywordBindingScalars",
    "IntentClusterStateScalars",
    "KeywordMetricObservationScalars",
    "KeywordStateScalars",
    "OpportunityAssessmentScalars",
    "SiteStateScalars",
    "map_portfolio_action_candidate_from_row",
    "map_portfolio_action_candidate_to_row",
    "map_portfolio_category_from_row",
    "map_portfolio_category_to_row",
    "map_portfolio_intent_cluster_from_row",
    "map_portfolio_intent_cluster_keyword_from_row",
    "map_portfolio_intent_cluster_keyword_to_row",
    "map_portfolio_intent_cluster_to_row",
    "map_portfolio_keyword_from_row",
    "map_portfolio_keyword_metric_observation_from_row",
    "map_portfolio_keyword_metric_observation_to_row",
    "map_portfolio_keyword_to_row",
    "map_portfolio_opportunity_assessment_from_row",
    "map_portfolio_opportunity_assessment_to_row",
    "map_portfolio_site_from_row",
    "map_portfolio_site_to_row",
]

install_mapper_physical_constraint_guards(globals())

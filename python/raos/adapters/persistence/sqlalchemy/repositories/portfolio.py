"""Concrete aggregate-specific SQLAlchemy repositories for PORTFOLIO (ST-0308)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import json
from typing import NoReturn, TypeVar
from uuid import UUID

from sqlalchemy import Table, insert, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.base import Executable

import raos.adapters.persistence.sqlalchemy.mappers.portfolio as domain_mappers
from raos.adapters.persistence.sqlalchemy.session_runtime import (
    fail_session_operation,
    guard_repository_class,
    register_pending_events,
    stage_registered_events,
)
from raos.domain.portfolio.aggregates import (
    ActionCandidate,
    ActionCandidateState,
    Category,
    CategoryState,
    IntentCluster,
    IntentClusterKeywordBinding,
    IntentClusterState,
    Keyword,
    KeywordMetricObservation,
    KeywordState,
    OpportunityAssessment,
    Site,
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
from raos.domain.portfolio.events import PortfolioActionCandidateDecided
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
from raos.domain.shared.identity import EntityId
from raos.domain.shared.json_values import FrozenJsonObject, canonical_json_bytes
from raos.domain.shared.persistence import EmailAddress, Sha256Digest, UriReference
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode

T = TypeVar("T")
RowData = Mapping[str, object] | RowMapping


def _fail(code: PersistenceErrorCode) -> NoReturn:
    raise PersistenceError(code) from None


def _table(relation: str) -> Table:
    try:
        from raos.adapters.persistence.sqlalchemy.generated.catalog import (
            TABLES_BY_RELATION,
        )

        table = TABLES_BY_RELATION[relation]
    except ImportError, KeyError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    if not isinstance(table, Table):
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return table


def _exact(row: RowData, key: str, expected: type[T]) -> T:
    try:
        value = row[key]
    except KeyError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    if type(value) is not expected:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return value


def _optional(row: RowData, key: str, expected: type[T]) -> T | None:
    try:
        value = row[key]
    except KeyError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    if value is None:
        return None
    if type(value) is not expected:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return value


def _json_object(row: RowData, key: str) -> FrozenJsonObject:
    value = _exact(row, key, dict)
    try:
        return FrozenJsonObject.from_mapping(value)
    except ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _evidence_id(row: RowData, key: str, name: str) -> EntityId:
    from raos.domain.evidence.ids import FactId, SourceSnapshotId

    classes = {"FactId": FactId, "SourceSnapshotId": SourceSnapshotId}
    cls = classes.get(name)
    if cls is None:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    try:
        return cls(_exact(row, key, UUID))
    except ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_scalar(value: object) -> object:
    if value is None or type(value) in {str, int, bool, Decimal, date}:
        return value
    if isinstance(value, EntityId):
        return value.value
    if isinstance(value, Enum):
        return value.value
    if type(value) is AwareUtcDateTime:
        return value.value
    if isinstance(
        value,
        (AggregateVersion, YenMinor, Sha256Digest, EmailAddress, UriReference),
    ):
        return value.value
    if isinstance(
        value,
        (
            ActionCandidateRationaleJson,
            CategoryEntryCriteriaJson,
            IntentClusterDecisionRequirementsJson,
            OpportunityAssessmentBusinessComponentsJson,
            OpportunityAssessmentComplianceComponentsJson,
            OpportunityAssessmentEditorialComponentsJson,
            SitePublicSettingsJson,
        ),
    ):
        return json.loads(canonical_json_bytes(value.value))
    _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encoded(columns: tuple[str, ...], values: tuple[object, ...]) -> dict[str, object]:
    if len(columns) != len(values):
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return {
        column: _encode_scalar(value)
        for column, value in zip(columns, values, strict=True)
    }


def _execute_one(session: Session, statement: Executable) -> RowMapping | None:
    try:
        return session.execute(statement).mappings().one_or_none()
    except IntegrityError:
        fail_session_operation(session, PersistenceErrorCode.INTEGRITY_CONFLICT)
    except DBAPIError:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)
    except PersistenceError as error:
        fail_session_operation(session, error.code)
    except Exception:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)


def _execute(session: Session, statement: Executable) -> None:
    try:
        session.execute(statement)
    except IntegrityError:
        fail_session_operation(session, PersistenceErrorCode.INTEGRITY_CONFLICT)
    except DBAPIError:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)
    except PersistenceError as error:
        fail_session_operation(session, error.code)
    except Exception:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)


def _decode_portfolio_action_candidate(
    row: RowData,
) -> ActionCandidateState:
    try:
        return domain_mappers.map_portfolio_action_candidate_from_row(
            id=ActionCandidateId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            site_id=SiteId(_exact(row, "site_id", UUID)),
            category_id=(
                None
                if row.get("category_id") is None
                else CategoryId(_exact(row, "category_id", UUID))
            ),
            action_type=ActionCandidateActionType(_exact(row, "action_type", str)),
            target_entity_type=ActionCandidateTargetEntityType(
                _exact(row, "target_entity_type", str)
            ),
            target_entity_id=(
                None
                if row.get("target_entity_id") is None
                else TargetEntityId(_exact(row, "target_entity_id", UUID))
            ),
            secondary_entity_id=(
                None
                if row.get("secondary_entity_id") is None
                else SecondaryEntityId(_exact(row, "secondary_entity_id", UUID))
            ),
            source_signal=_exact(row, "source_signal", str),
            expected_incremental_profit_jpy=(
                None
                if row.get("expected_incremental_profit_jpy") is None
                else YenMinor(_exact(row, "expected_incremental_profit_jpy", int))
            ),
            urgency_score=_exact(row, "urgency_score", Decimal),
            confidence=_exact(row, "confidence", Decimal),
            priority_score=_exact(row, "priority_score", Decimal),
            status=ActionCandidateStatus(_exact(row, "status", str)),
            rationale=ActionCandidateRationaleJson(_json_object(row, "rationale")),
            generated_at=AwareUtcDateTime(_exact(row, "generated_at", datetime)),
            expires_at=(
                None
                if row.get("expires_at") is None
                else AwareUtcDateTime(_exact(row, "expires_at", datetime))
            ),
            decided_by_principal_id=(
                None
                if row.get("decided_by_principal_id") is None
                else PrincipalId(_exact(row, "decided_by_principal_id", UUID))
            ),
            decided_at=(
                None
                if row.get("decided_at") is None
                else AwareUtcDateTime(_exact(row, "decided_at", datetime))
            ),
            decision_note=_optional(row, "decision_note", str),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_portfolio_action_candidate(
    value: ActionCandidateState,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "site_id",
            "category_id",
            "action_type",
            "target_entity_type",
            "target_entity_id",
            "secondary_entity_id",
            "source_signal",
            "expected_incremental_profit_jpy",
            "urgency_score",
            "confidence",
            "priority_score",
            "status",
            "rationale",
            "generated_at",
            "expires_at",
            "decided_by_principal_id",
            "decided_at",
            "decision_note",
            "created_at",
            "updated_at",
            "lock_version",
        ),
        domain_mappers.map_portfolio_action_candidate_to_row(value),
    )


def _decode_portfolio_category(row: RowData) -> CategoryState:
    try:
        return domain_mappers.map_portfolio_category_from_row(
            id=CategoryId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            site_id=SiteId(_exact(row, "site_id", UUID)),
            parent_category_id=(
                None
                if row.get("parent_category_id") is None
                else CategoryId(_exact(row, "parent_category_id", UUID))
            ),
            category_code=_exact(row, "category_code", str),
            name=_exact(row, "name", str),
            description=_optional(row, "description", str),
            risk_class=CategoryRiskClass(_exact(row, "risk_class", str)),
            stage=CategoryStage(_exact(row, "stage", str)),
            article_limit=_optional(row, "article_limit", int),
            approved_at=(
                None
                if row.get("approved_at") is None
                else AwareUtcDateTime(_exact(row, "approved_at", datetime))
            ),
            approved_by_principal_id=(
                None
                if row.get("approved_by_principal_id") is None
                else PrincipalId(_exact(row, "approved_by_principal_id", UUID))
            ),
            entry_criteria=CategoryEntryCriteriaJson(
                _json_object(row, "entry_criteria")
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_portfolio_category(value: CategoryState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "site_id",
            "parent_category_id",
            "category_code",
            "name",
            "description",
            "risk_class",
            "stage",
            "article_limit",
            "approved_at",
            "approved_by_principal_id",
            "entry_criteria",
            "created_at",
            "updated_at",
            "lock_version",
        ),
        domain_mappers.map_portfolio_category_to_row(value),
    )


def _decode_portfolio_intent_cluster(row: RowData) -> IntentClusterState:
    try:
        return domain_mappers.map_portfolio_intent_cluster_from_row(
            id=IntentClusterId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            category_id=CategoryId(_exact(row, "category_id", UUID)),
            cluster_code=_exact(row, "cluster_code", str),
            name=_exact(row, "name", str),
            description=_exact(row, "description", str),
            intent_type=IntentClusterIntentType(_exact(row, "intent_type", str)),
            status=IntentClusterStatus(_exact(row, "status", str)),
            decision_requirements=IntentClusterDecisionRequirementsJson(
                _json_object(row, "decision_requirements")
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_portfolio_intent_cluster(value: IntentClusterState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "category_id",
            "cluster_code",
            "name",
            "description",
            "intent_type",
            "status",
            "decision_requirements",
            "created_at",
            "updated_at",
            "lock_version",
        ),
        domain_mappers.map_portfolio_intent_cluster_to_row(value),
    )


def _decode_portfolio_intent_cluster_keyword(
    row: RowData,
) -> IntentClusterKeywordBinding:
    try:
        return domain_mappers.map_portfolio_intent_cluster_keyword_from_row(
            intent_cluster_id=IntentClusterId(_exact(row, "intent_cluster_id", UUID)),
            keyword_id=KeywordId(_exact(row, "keyword_id", UUID)),
            keyword_role=IntentClusterKeywordBindingKeywordRole(
                _exact(row, "keyword_role", str)
            ),
            priority=_exact(row, "priority", int),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_portfolio_intent_cluster_keyword(
    value: IntentClusterKeywordBinding,
) -> dict[str, object]:
    return _encoded(
        ("intent_cluster_id", "keyword_id", "keyword_role", "priority", "created_at"),
        domain_mappers.map_portfolio_intent_cluster_keyword_to_row(value),
    )


def _decode_portfolio_keyword(row: RowData) -> KeywordState:
    try:
        return domain_mappers.map_portfolio_keyword_from_row(
            id=KeywordId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            site_id=SiteId(_exact(row, "site_id", UUID)),
            display_text=_exact(row, "display_text", str),
            normalized_text=_exact(row, "normalized_text", str),
            locale=_exact(row, "locale", str),
            status=KeywordStatus(_exact(row, "status", str)),
            sensitive_query=_exact(row, "sensitive_query", bool),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_portfolio_keyword(value: KeywordState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "site_id",
            "display_text",
            "normalized_text",
            "locale",
            "status",
            "sensitive_query",
            "created_at",
            "updated_at",
            "lock_version",
        ),
        domain_mappers.map_portfolio_keyword_to_row(value),
    )


def _decode_portfolio_keyword_metric_observation(
    row: RowData,
) -> KeywordMetricObservation:
    try:
        return domain_mappers.map_portfolio_keyword_metric_observation_from_row(
            id=KeywordMetricObservationId(_exact(row, "id", UUID)),
            keyword_id=KeywordId(_exact(row, "keyword_id", UUID)),
            provider_code=_exact(row, "provider_code", str),
            metric_type=KeywordMetricObservationMetricType(
                _exact(row, "metric_type", str)
            ),
            metric_value=_exact(row, "metric_value", Decimal),
            unit=_exact(row, "unit", str),
            country_code=_exact(row, "country_code", str),
            device=KeywordMetricObservationDevice(_exact(row, "device", str)),
            observed_date=_exact(row, "observed_date", date),
            confidence=_optional(row, "confidence", Decimal),
            raw_artifact_id=(
                None
                if row.get("raw_artifact_id") is None
                else ObjectArtifactId(_exact(row, "raw_artifact_id", UUID))
            ),
            ingested_at=AwareUtcDateTime(_exact(row, "ingested_at", datetime)),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_portfolio_keyword_metric_observation(
    value: KeywordMetricObservation,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "keyword_id",
            "provider_code",
            "metric_type",
            "metric_value",
            "unit",
            "country_code",
            "device",
            "observed_date",
            "confidence",
            "raw_artifact_id",
            "ingested_at",
            "created_at",
        ),
        domain_mappers.map_portfolio_keyword_metric_observation_to_row(value),
    )


def _decode_portfolio_opportunity_assessment(
    row: RowData,
) -> OpportunityAssessment:
    try:
        return domain_mappers.map_portfolio_opportunity_assessment_from_row(
            id=OpportunityAssessmentId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            category_id=CategoryId(_exact(row, "category_id", UUID)),
            intent_cluster_id=(
                None
                if row.get("intent_cluster_id") is None
                else IntentClusterId(_exact(row, "intent_cluster_id", UUID))
            ),
            keyword_id=(
                None
                if row.get("keyword_id") is None
                else KeywordId(_exact(row, "keyword_id", UUID))
            ),
            assessment_type=OpportunityAssessmentAssessmentType(
                _exact(row, "assessment_type", str)
            ),
            formula_version=_exact(row, "formula_version", str),
            editorial_feasibility_score=_exact(
                row, "editorial_feasibility_score", Decimal
            ),
            business_opportunity_score=_exact(
                row, "business_opportunity_score", Decimal
            ),
            compliance_risk_score=_exact(row, "compliance_risk_score", Decimal),
            overall_priority_score=_exact(row, "overall_priority_score", Decimal),
            decision=OpportunityAssessmentDecision(_exact(row, "decision", str)),
            editorial_components=OpportunityAssessmentEditorialComponentsJson(
                _json_object(row, "editorial_components")
            ),
            business_components=OpportunityAssessmentBusinessComponentsJson(
                _json_object(row, "business_components")
            ),
            compliance_components=OpportunityAssessmentComplianceComponentsJson(
                _json_object(row, "compliance_components")
            ),
            assessed_at=AwareUtcDateTime(_exact(row, "assessed_at", datetime)),
            assessed_by_actor_type=_exact(row, "assessed_by_actor_type", str),
            assessed_by_actor_id=(
                None
                if row.get("assessed_by_actor_id") is None
                else AssessedByActorId(_exact(row, "assessed_by_actor_id", UUID))
            ),
            expires_at=(
                None
                if row.get("expires_at") is None
                else AwareUtcDateTime(_exact(row, "expires_at", datetime))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_portfolio_opportunity_assessment(
    value: OpportunityAssessment,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "category_id",
            "intent_cluster_id",
            "keyword_id",
            "assessment_type",
            "formula_version",
            "editorial_feasibility_score",
            "business_opportunity_score",
            "compliance_risk_score",
            "overall_priority_score",
            "decision",
            "editorial_components",
            "business_components",
            "compliance_components",
            "assessed_at",
            "assessed_by_actor_type",
            "assessed_by_actor_id",
            "expires_at",
            "created_at",
        ),
        domain_mappers.map_portfolio_opportunity_assessment_to_row(value),
    )


def _decode_portfolio_site(row: RowData) -> SiteState:
    try:
        return domain_mappers.map_portfolio_site_from_row(
            id=SiteId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            site_code=_exact(row, "site_code", str),
            name=_exact(row, "name", str),
            primary_domain=_exact(row, "primary_domain", str),
            brand_name=_exact(row, "brand_name", str),
            locale=_exact(row, "locale", str),
            timezone=_exact(row, "timezone", str),
            currency=_exact(row, "currency", str),
            status=SiteStatus(_exact(row, "status", str)),
            public_settings=SitePublicSettingsJson(
                _json_object(row, "public_settings")
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_portfolio_site(value: SiteState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "site_code",
            "name",
            "primary_domain",
            "brand_name",
            "locale",
            "timezone",
            "currency",
            "status",
            "public_settings",
            "created_at",
            "updated_at",
            "lock_version",
        ),
        domain_mappers.map_portfolio_site_to_row(value),
    )


# Aggregate-specific classes below are the only DML surface.


def _cas_update(
    session: Session,
    table: Table,
    aggregate_id: UUID,
    expected_version: AggregateVersion,
    values: dict[str, object],
) -> AggregateVersion:
    values = dict(values)
    values.pop("id")
    values["lock_version"] = expected_version.value + 1
    try:
        persisted = session.execute(
            update(table)
            .where(
                table.c.id == aggregate_id,
                table.c.lock_version == expected_version.value,
            )
            .values(**values)
            .returning(table.c.lock_version)
        ).scalar_one_or_none()
    except IntegrityError:
        fail_session_operation(session, PersistenceErrorCode.INTEGRITY_CONFLICT)
    except DBAPIError:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)
    except PersistenceError as error:
        fail_session_operation(session, error.code)
    except Exception:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)
    if type(persisted) is int:
        return AggregateVersion(persisted)
    observed = _execute_one(
        session, select(table.c.lock_version).where(table.c.id == aggregate_id)
    )
    if observed is None:
        _fail(PersistenceErrorCode.NOT_FOUND)
    if _exact(observed, "lock_version", int) != expected_version.value:
        _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
    _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


@guard_repository_class
class SqlAlchemySiteRepository:
    __slots__ = ("_session", "_table")

    def __init__(self, session: Session) -> None:
        if not isinstance(session, Session):
            raise ValueError("INVALID_PORTFOLIO_REPOSITORY") from None
        self._session = session
        self._table = _table("portfolio.site")

    def get(self, site_id: SiteId) -> Site | None:
        if type(site_id) is not SiteId:
            raise ValueError("INVALID_SITE_ID") from None
        row = _execute_one(
            self._session, select(self._table).where(self._table.c.id == site_id.value)
        )
        return None if row is None else Site(_decode_portfolio_site(row))

    def add(self, site: Site) -> AggregateVersion:
        if type(site) is not Site or site.state.lock_version.value != 0:
            raise ValueError("INVALID_SITE") from None
        _execute(
            self._session,
            insert(self._table).values(**_encode_portfolio_site(site.state)),
        )
        return AggregateVersion(0)

    def save(self, site: Site, expected_version: AggregateVersion) -> AggregateVersion:
        if (
            type(site) is not Site
            or type(expected_version) is not AggregateVersion
            or site.state.lock_version != expected_version
        ):
            raise ValueError("INVALID_SITE") from None
        return _cas_update(
            self._session,
            self._table,
            site.state.id.value,
            expected_version,
            _encode_portfolio_site(site.state),
        )


@guard_repository_class
class SqlAlchemyCategoryRepository:
    __slots__ = ("_session", "_table")

    def __init__(self, session: Session) -> None:
        if not isinstance(session, Session):
            raise ValueError("INVALID_PORTFOLIO_REPOSITORY") from None
        self._session = session
        self._table = _table("portfolio.category")

    def get(self, category_id: CategoryId) -> Category | None:
        if type(category_id) is not CategoryId:
            raise ValueError("INVALID_CATEGORY_ID") from None
        row = _execute_one(
            self._session,
            select(self._table).where(self._table.c.id == category_id.value),
        )
        return None if row is None else Category(_decode_portfolio_category(row))

    def add(self, category: Category) -> AggregateVersion:
        if type(category) is not Category or category.state.lock_version.value != 0:
            raise ValueError("INVALID_CATEGORY") from None
        _execute(
            self._session,
            insert(self._table).values(**_encode_portfolio_category(category.state)),
        )
        return AggregateVersion(0)

    def save(
        self, category: Category, expected_version: AggregateVersion
    ) -> AggregateVersion:
        if (
            type(category) is not Category
            or type(expected_version) is not AggregateVersion
            or category.state.lock_version != expected_version
        ):
            raise ValueError("INVALID_CATEGORY") from None
        return _cas_update(
            self._session,
            self._table,
            category.state.id.value,
            expected_version,
            _encode_portfolio_category(category.state),
        )


@guard_repository_class
class SqlAlchemyIntentClusterRepository:
    __slots__ = ("_binding", "_root", "_session")

    def __init__(self, session: Session) -> None:
        if not isinstance(session, Session):
            raise ValueError("INVALID_PORTFOLIO_REPOSITORY") from None
        self._session = session
        self._root = _table("portfolio.intent_cluster")
        self._binding = _table("portfolio.intent_cluster_keyword")

    def get(self, cluster_id: IntentClusterId) -> IntentCluster | None:
        if type(cluster_id) is not IntentClusterId:
            raise ValueError("INVALID_INTENT_CLUSTER_ID") from None
        row = _execute_one(
            self._session, select(self._root).where(self._root.c.id == cluster_id.value)
        )
        if row is None:
            return None
        try:
            children = tuple(
                _decode_portfolio_intent_cluster_keyword(item)
                for item in self._session.execute(
                    select(self._binding)
                    .where(self._binding.c.intent_cluster_id == cluster_id.value)
                    .order_by(
                        self._binding.c.intent_cluster_id,
                        self._binding.c.keyword_id,
                    )
                ).mappings()
            )
        except DBAPIError:
            fail_session_operation(
                self._session, PersistenceErrorCode.STORAGE_CORRUPTION
            )
        except PersistenceError as error:
            fail_session_operation(self._session, error.code)
        except Exception:
            fail_session_operation(
                self._session, PersistenceErrorCode.STORAGE_CORRUPTION
            )
        try:
            return IntentCluster(
                state=_decode_portfolio_intent_cluster(row),
                intent_cluster_keyword_rows=children,
            )
        except ValueError:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)

    def add(self, cluster: IntentCluster) -> AggregateVersion:
        if type(cluster) is not IntentCluster or cluster.state.lock_version.value != 0:
            raise ValueError("INVALID_INTENT_CLUSTER") from None
        _execute(
            self._session,
            insert(self._root).values(
                **_encode_portfolio_intent_cluster(cluster.state)
            ),
        )
        for child in cluster.intent_cluster_keyword_rows:
            _execute(
                self._session,
                insert(self._binding).values(
                    **_encode_portfolio_intent_cluster_keyword(child)
                ),
            )
        return AggregateVersion(0)

    def save(
        self, cluster: IntentCluster, expected_version: AggregateVersion
    ) -> AggregateVersion:
        if (
            type(cluster) is not IntentCluster
            or type(expected_version) is not AggregateVersion
            or cluster.state.lock_version != expected_version
        ):
            raise ValueError("INVALID_INTENT_CLUSTER") from None
        current = self.get(cluster.state.id)
        if current is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current_by_key = {
            row.keyword_id.value: row for row in current.intent_cluster_keyword_rows
        }
        proposed_by_key = {
            row.keyword_id.value: row for row in cluster.intent_cluster_keyword_rows
        }
        if not current_by_key.keys() <= proposed_by_key.keys() or any(
            proposed_by_key[key] != value for key, value in current_by_key.items()
        ):
            _fail(PersistenceErrorCode.APPEND_ONLY_RELATION)
        persisted = _cas_update(
            self._session,
            self._root,
            cluster.state.id.value,
            expected_version,
            _encode_portfolio_intent_cluster(cluster.state),
        )
        for key, child in proposed_by_key.items():
            if key not in current_by_key:
                _execute(
                    self._session,
                    insert(self._binding).values(
                        **_encode_portfolio_intent_cluster_keyword(child)
                    ),
                )
        return persisted


@guard_repository_class
class SqlAlchemyKeywordRepository:
    __slots__ = ("_observation", "_root", "_session")

    def __init__(self, session: Session) -> None:
        if not isinstance(session, Session):
            raise ValueError("INVALID_PORTFOLIO_REPOSITORY") from None
        self._session = session
        self._root = _table("portfolio.keyword")
        self._observation = _table("portfolio.keyword_metric_observation")

    def get(self, keyword_id: KeywordId) -> Keyword | None:
        if type(keyword_id) is not KeywordId:
            raise ValueError("INVALID_KEYWORD_ID") from None
        row = _execute_one(
            self._session, select(self._root).where(self._root.c.id == keyword_id.value)
        )
        if row is None:
            return None
        try:
            observations = tuple(
                _decode_portfolio_keyword_metric_observation(item)
                for item in self._session.execute(
                    select(self._observation)
                    .where(self._observation.c.keyword_id == keyword_id.value)
                    .order_by(self._observation.c.id)
                ).mappings()
            )
        except DBAPIError:
            fail_session_operation(
                self._session, PersistenceErrorCode.STORAGE_CORRUPTION
            )
        except PersistenceError as error:
            fail_session_operation(self._session, error.code)
        except Exception:
            fail_session_operation(
                self._session, PersistenceErrorCode.STORAGE_CORRUPTION
            )
        try:
            return Keyword(
                state=_decode_portfolio_keyword(row),
                keyword_metric_observation_rows=observations,
            )
        except ValueError:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)

    def add(self, keyword: Keyword) -> AggregateVersion:
        if type(keyword) is not Keyword or keyword.state.lock_version.value != 0:
            raise ValueError("INVALID_KEYWORD") from None
        _execute(
            self._session,
            insert(self._root).values(**_encode_portfolio_keyword(keyword.state)),
        )
        for observation in keyword.keyword_metric_observation_rows:
            _execute(
                self._session,
                insert(self._observation).values(
                    **_encode_portfolio_keyword_metric_observation(observation)
                ),
            )
        return AggregateVersion(0)

    def save(
        self, keyword: Keyword, expected_version: AggregateVersion
    ) -> AggregateVersion:
        if (
            type(keyword) is not Keyword
            or type(expected_version) is not AggregateVersion
            or keyword.state.lock_version != expected_version
        ):
            raise ValueError("INVALID_KEYWORD") from None
        current = self.get(keyword.state.id)
        if current is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current_by_id = {
            row.id.value: row for row in current.keyword_metric_observation_rows
        }
        proposed_by_id = {
            row.id.value: row for row in keyword.keyword_metric_observation_rows
        }
        if not current_by_id.keys() <= proposed_by_id.keys() or any(
            proposed_by_id[key] != value for key, value in current_by_id.items()
        ):
            _fail(PersistenceErrorCode.APPEND_ONLY_RELATION)
        persisted = _cas_update(
            self._session,
            self._root,
            keyword.state.id.value,
            expected_version,
            _encode_portfolio_keyword(keyword.state),
        )
        for key, observation in proposed_by_id.items():
            if key not in current_by_id:
                _execute(
                    self._session,
                    insert(self._observation).values(
                        **_encode_portfolio_keyword_metric_observation(observation)
                    ),
                )
        return persisted

    def append_metric_observations(
        self,
        keyword_id: KeywordId,
        observations: tuple[KeywordMetricObservation, ...],
        expected_version: AggregateVersion,
    ) -> AggregateVersion:
        if (
            type(keyword_id) is not KeywordId
            or type(observations) is not tuple
            or not observations
            or any(
                type(item) is not KeywordMetricObservation
                or item.keyword_id != keyword_id
                for item in observations
            )
            or type(expected_version) is not AggregateVersion
        ):
            raise ValueError("INVALID_KEYWORD_OBSERVATION_BATCH") from None
        current = self.get(keyword_id)
        if current is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        if current.state.lock_version != expected_version:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        persisted = _cas_update(
            self._session,
            self._root,
            keyword_id.value,
            expected_version,
            _encode_portfolio_keyword(current.state),
        )
        for observation in observations:
            _execute(
                self._session,
                insert(self._observation).values(
                    **_encode_portfolio_keyword_metric_observation(observation)
                ),
            )
        return persisted


@guard_repository_class
class SqlAlchemyOpportunityAssessmentRepository:
    __slots__ = ("_session", "_table")

    def __init__(self, session: Session) -> None:
        if not isinstance(session, Session):
            raise ValueError("INVALID_PORTFOLIO_REPOSITORY") from None
        self._session = session
        self._table = _table("portfolio.opportunity_assessment")

    def get(
        self, assessment_id: OpportunityAssessmentId
    ) -> OpportunityAssessment | None:
        if type(assessment_id) is not OpportunityAssessmentId:
            raise ValueError("INVALID_ASSESSMENT_ID") from None
        row = _execute_one(
            self._session,
            select(self._table).where(self._table.c.id == assessment_id.value),
        )
        return None if row is None else _decode_portfolio_opportunity_assessment(row)

    def append(self, assessment: OpportunityAssessment) -> None:
        if type(assessment) is not OpportunityAssessment:
            raise ValueError("INVALID_ASSESSMENT") from None
        _execute(
            self._session,
            insert(self._table).values(
                **_encode_portfolio_opportunity_assessment(assessment)
            ),
        )


@guard_repository_class
class SqlAlchemyActionCandidateRepository:
    __slots__ = ("_session", "_table")

    def __init__(self, session: Session) -> None:
        if not isinstance(session, Session):
            raise ValueError("INVALID_PORTFOLIO_REPOSITORY") from None
        self._session = session
        self._table = _table("portfolio.action_candidate")

    def get(self, candidate_id: ActionCandidateId) -> ActionCandidate | None:
        if type(candidate_id) is not ActionCandidateId:
            raise ValueError("INVALID_ACTION_CANDIDATE_ID") from None
        row = _execute_one(
            self._session,
            select(self._table).where(self._table.c.id == candidate_id.value),
        )
        if row is None:
            return None
        candidate = ActionCandidate(_decode_portfolio_action_candidate(row))
        register_pending_events(
            self._session,
            aggregate_type="portfolio.action_candidate",
            aggregate_id=candidate.state.id.value,
            buffer=candidate._event_buffer,
        )
        return candidate

    def add(self, candidate: ActionCandidate) -> AggregateVersion:
        if (
            type(candidate) is not ActionCandidate
            or candidate.state.lock_version.value != 0
            or candidate.state.status
            in {ActionCandidateStatus.ACCEPTED, ActionCandidateStatus.REJECTED}
            or candidate.state.decided_by_principal_id is not None
            or candidate.state.decided_at is not None
            or candidate.state.decision_note is not None
            or candidate.pending_events()
        ):
            raise ValueError("INVALID_ACTION_CANDIDATE") from None
        register_pending_events(
            self._session,
            aggregate_type="portfolio.action_candidate",
            aggregate_id=candidate.state.id.value,
            buffer=candidate._event_buffer,
        )
        _execute(
            self._session,
            insert(self._table).values(
                **_encode_portfolio_action_candidate(candidate.state)
            ),
        )
        return AggregateVersion(0)

    def save(
        self, candidate: ActionCandidate, expected_version: AggregateVersion
    ) -> AggregateVersion:
        if (
            type(candidate) is not ActionCandidate
            or type(expected_version) is not AggregateVersion
            or candidate.state.lock_version != expected_version
        ):
            raise ValueError("INVALID_ACTION_CANDIDATE") from None
        current_row = _execute_one(
            self._session,
            select(self._table).where(self._table.c.id == candidate.state.id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = ActionCandidate(_decode_portfolio_action_candidate(current_row))
        if current.state.lock_version != expected_version:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        if current.state.decided_at is not None and (
            candidate.state.decided_at != current.state.decided_at
            or candidate.state.decided_by_principal_id
            != current.state.decided_by_principal_id
            or candidate.state.decision_note != current.state.decision_note
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        decided_at = candidate.state.decided_at
        target_is_decision = candidate.state.status in {
            ActionCandidateStatus.ACCEPTED,
            ActionCandidateStatus.REJECTED,
        }
        if current.state.decided_at is None and target_is_decision != (
            decided_at is not None
            and candidate.state.decided_by_principal_id is not None
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        emits = (
            current.state.decided_at is None
            and decided_at is not None
            and target_is_decision
        )
        expected_decided_at = (
            None if decided_at is None else decided_at.value.isoformat()
        )
        pending = candidate.pending_events()
        if emits and not pending:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        if pending:
            if (
                not emits
                or len(pending) != 1
                or type(pending[0]) is not PortfolioActionCandidateDecided
                or pending[0].aggregate_id != candidate.state.id
                or pending[0].data["action_candidate_id"]
                != str(candidate.state.id.value)
                or pending[0].data["decision"] != candidate.state.status.value
                or pending[0].data["decided_at"] != expected_decided_at
            ):
                _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        register_pending_events(
            self._session,
            aggregate_type="portfolio.action_candidate",
            aggregate_id=candidate.state.id.value,
            buffer=candidate._event_buffer,
        )
        persisted = _cas_update(
            self._session,
            self._table,
            candidate.state.id.value,
            expected_version,
            _encode_portfolio_action_candidate(candidate.state),
        )
        if emits:
            stage_registered_events(
                self._session,
                aggregate_type="portfolio.action_candidate",
                aggregate_id=candidate.state.id.value,
                owning_method="ActionCandidateRepository.save",
                persisted_version=persisted,
                expected_event_type=("jp.raos.portfolio.action_candidate_decided.v1"),
            )
        return persisted


__all__ = [
    "SqlAlchemyActionCandidateRepository",
    "SqlAlchemyCategoryRepository",
    "SqlAlchemyIntentClusterRepository",
    "SqlAlchemyKeywordRepository",
    "SqlAlchemyOpportunityAssessmentRepository",
    "SqlAlchemySiteRepository",
]

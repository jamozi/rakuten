"""Concrete scalar codecs and aggregate-specific SQLAlchemy repositories for POLICY."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import json
from typing import NoReturn, TypeVar, cast
from uuid import UUID

from sqlalchemy import Table, insert, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql import Executable
from sqlalchemy.sql.elements import ColumnElement

import raos.adapters.persistence.sqlalchemy.mappers.policy as domain_mappers
from raos.adapters.persistence.sqlalchemy.session_runtime import (
    aggregate_events_buffer,
    fail_session_operation,
    guard_repository_class,
    persistence_context,
    register_pending_events,
    stage_registered_events,
    transaction_timestamp,
)
from raos.domain.editorial.ids import (
    ArticleBlockId,
    ArticleVersionId,
)
from raos.domain.evidence.ids import (
    ClaimId,
    SourcePacketVersionId,
)
from raos.domain.iam.ids import (
    PrincipalId,
)
from raos.domain.ops.ids import (
    ObjectArtifactId,
)
from raos.domain.policy.aggregates import (
    BundleRuleBinding,
    Finding,
    FindingState,
    GateDecision,
    GateDecisionState,
    PolicyBundle,
    PolicyBundleState,
    QualityCheckRun,
    QualityCheckRunState,
    QualityScore,
    RuleVersion,
    RuleVersionState,
    Waiver,
    WaiverState,
)
from raos.domain.policy.enums import (
    BundleRuleBindingMode,
    FindingEntityType,
    FindingSeverity,
    FindingStatus,
    GateDecisionGateCode,
    GateDecisionResult,
    GateDecisionScopeType,
    PolicyBundleStatus,
    QualityCheckRunStatus,
    QualityCheckRunTriggeredByActorType,
    RuleVersionImplementationType,
    RuleVersionRuleCategory,
    RuleVersionSeverity,
    RuleVersionStatus,
    WaiverScopeType,
    WaiverStatus,
)
from raos.domain.policy.events import PolicyPolicyBundleActivated
from raos.domain.policy.ids import (
    FindingId,
    GateDecisionId,
    PolicyBundleId,
    QualityCheckRunId,
    QualityScoreId,
    RuleVersionId,
    WaiverId,
)
from raos.domain.policy.values import (
    FindingEvidenceJson,
    GateDecisionConditionsJson,
    QualityScoreComponentsJson,
    RuleVersionDefinitionJson,
)
from raos.domain.shared.identity import (
    EntityId,
    ScopeId,
    TriggeredByActorId,
)
from raos.domain.shared.json_values import FrozenJsonObject, canonical_json_bytes
from raos.domain.shared.persistence import (
    AggregateVersion,
    AwareUtcDateTime,
    EmailAddress,
    GitCommitDigest,
    Sha256Digest,
    UriReference,
    YenMinor,
)
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode


T = TypeVar("T")
StorageRow = Mapping[str, object] | RowMapping


def _fail(code: PersistenceErrorCode) -> NoReturn:
    raise PersistenceError(code) from None


def _table(relation: str) -> Table:
    try:
        from raos.adapters.persistence.sqlalchemy.generated.catalog import (
            TABLES_BY_RELATION,
        )

        table = cast(object, TABLES_BY_RELATION[relation])
    except ImportError, KeyError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    if not isinstance(table, Table) or table.fullname != relation:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return table


def _shape(row: StorageRow, columns: tuple[str, ...]) -> None:
    if frozenset(row) != frozenset(columns) or len(row) != len(columns):
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _exact(row: StorageRow, key: str, expected: type[T]) -> T:
    try:
        value = row[key]
    except KeyError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    if type(value) is not expected:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return value


def _json_object(row: StorageRow, key: str) -> FrozenJsonObject:
    value = cast(dict[str, object], _exact(row, key, dict))
    try:
        return FrozenJsonObject.from_mapping(value)
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
    if type(value) in {
        AggregateVersion,
        YenMinor,
        Sha256Digest,
        GitCommitDigest,
        EmailAddress,
        UriReference,
    }:
        return cast(
            AggregateVersion
            | YenMinor
            | Sha256Digest
            | GitCommitDigest
            | EmailAddress
            | UriReference,
            value,
        ).value
    if type(value) is tuple:
        items = cast(tuple[object, ...], value)
        if all(type(item) is str for item in items):
            return [cast(str, item) for item in items]
    if isinstance(
        value,
        (
            FindingEvidenceJson,
            GateDecisionConditionsJson,
            QualityScoreComponentsJson,
            RuleVersionDefinitionJson,
        ),
    ):
        return json.loads(canonical_json_bytes(value.value))
    _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encoded(
    columns: tuple[str, ...],
    values: tuple[object, ...],
) -> dict[str, object]:
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


def _execute_many(session: Session, statement: Executable) -> tuple[RowMapping, ...]:
    try:
        return tuple(session.execute(statement).mappings())
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


def _require_session(session: Session) -> None:
    if not isinstance(cast(object, session), Session):
        raise ValueError("INVALID_POLICY_REPOSITORY") from None


def _context_actor_id(session: Session) -> UUID:
    actor_id = persistence_context(session).actor.actor_id
    if actor_id is None:
        _fail(PersistenceErrorCode.STATE_CONFLICT)
    return actor_id


def _state_zero(
    session: Session,
    table: Table,
    identifier: UUID,
    expected_status: Enum,
) -> NoReturn:
    row = _execute_one(
        session,
        select(table.c.id, table.c.status).where(table.c.id == identifier),
    )
    if row is None:
        _fail(PersistenceErrorCode.NOT_FOUND)
    stored_id = _exact(row, "id", UUID)
    stored_status = _exact(row, "status", str)
    if stored_id != identifier:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    if stored_status != expected_status.value:
        _fail(PersistenceErrorCode.STATE_CONFLICT)
    _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _require_same(
    current: Mapping[str, object],
    target: Mapping[str, object],
    immutable: tuple[str, ...],
) -> None:
    if any(current[name] != target[name] for name in immutable):
        _fail(PersistenceErrorCode.STATE_CONFLICT)


def _latest_version(
    session: Session,
    table: Table,
    predicates: tuple[ColumnElement[bool], ...],
) -> int | None:
    row = _execute_one(
        session,
        select(table.c.version_no)
        .where(*predicates)
        .order_by(table.c.version_no.desc(), table.c.id.desc())
        .limit(1),
    )
    if row is None:
        return None
    value = row.get("version_no")
    if type(value) is not int or value < 1:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return value


def _validate_append_version(
    actual: int,
    expected_latest: int | None,
    observed_latest: int | None,
) -> AggregateVersion:
    if expected_latest is not None and (
        type(expected_latest) is not int or expected_latest < 1
    ):
        raise ValueError("INVALID_EXPECTED_LATEST_VERSION") from None
    if observed_latest != expected_latest:
        _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
    required = 1 if observed_latest is None else observed_latest + 1
    if actual != required:
        raise ValueError("INVALID_VERSION_SERIES_APPEND") from None
    return AggregateVersion(actual)


def _decode_policy_bundle_rule(row: StorageRow) -> BundleRuleBinding:
    columns = (
        "policy_bundle_id",
        "rule_version_id",
        "execution_order",
        "mode",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_policy_bundle_rule_from_row(
            policy_bundle_id=PolicyBundleId(_exact(row, "policy_bundle_id", UUID)),
            rule_version_id=RuleVersionId(_exact(row, "rule_version_id", UUID)),
            execution_order=_exact(row, "execution_order", int),
            mode=BundleRuleBindingMode(_exact(row, "mode", str)),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_policy_bundle_rule(value: BundleRuleBinding) -> dict[str, object]:
    return _encoded(
        (
            "policy_bundle_id",
            "rule_version_id",
            "execution_order",
            "mode",
            "created_at",
        ),
        domain_mappers.map_policy_bundle_rule_to_row(value),
    )


def _decode_policy_finding(row: StorageRow) -> FindingState:
    columns = (
        "id",
        "quality_check_run_id",
        "rule_version_id",
        "finding_code",
        "severity",
        "is_blocking",
        "entity_type",
        "entity_id",
        "article_block_id",
        "claim_id",
        "message",
        "evidence",
        "status",
        "resolved_at",
        "resolved_by_principal_id",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_policy_finding_from_row(
            id=FindingId(_exact(row, "id", UUID)),
            quality_check_run_id=QualityCheckRunId(
                _exact(row, "quality_check_run_id", UUID)
            ),
            rule_version_id=RuleVersionId(_exact(row, "rule_version_id", UUID)),
            finding_code=_exact(row, "finding_code", str),
            severity=FindingSeverity(_exact(row, "severity", str)),
            is_blocking=_exact(row, "is_blocking", bool),
            entity_type=FindingEntityType(_exact(row, "entity_type", str)),
            entity_id=(
                None
                if row["entity_id"] is None
                else EntityId(_exact(row, "entity_id", UUID))
            ),
            article_block_id=(
                None
                if row["article_block_id"] is None
                else ArticleBlockId(_exact(row, "article_block_id", UUID))
            ),
            claim_id=(
                None
                if row["claim_id"] is None
                else ClaimId(_exact(row, "claim_id", UUID))
            ),
            message=_exact(row, "message", str),
            evidence=FindingEvidenceJson(_json_object(row, "evidence")),
            status=FindingStatus(_exact(row, "status", str)),
            resolved_at=(
                None
                if row["resolved_at"] is None
                else AwareUtcDateTime(_exact(row, "resolved_at", datetime))
            ),
            resolved_by_principal_id=(
                None
                if row["resolved_by_principal_id"] is None
                else PrincipalId(_exact(row, "resolved_by_principal_id", UUID))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_policy_finding(value: FindingState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "quality_check_run_id",
            "rule_version_id",
            "finding_code",
            "severity",
            "is_blocking",
            "entity_type",
            "entity_id",
            "article_block_id",
            "claim_id",
            "message",
            "evidence",
            "status",
            "resolved_at",
            "resolved_by_principal_id",
            "created_at",
        ),
        domain_mappers.map_policy_finding_to_row(value),
    )


def _decode_policy_gate_decision(row: StorageRow) -> GateDecisionState:
    columns = (
        "id",
        "display_id",
        "gate_code",
        "scope_type",
        "scope_id",
        "policy_bundle_id",
        "result",
        "conditions",
        "evidence_artifact_id",
        "decided_by_principal_id",
        "decided_at",
        "expires_at",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_policy_gate_decision_from_row(
            id=GateDecisionId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            gate_code=GateDecisionGateCode(_exact(row, "gate_code", str)),
            scope_type=GateDecisionScopeType(_exact(row, "scope_type", str)),
            scope_id=ScopeId(_exact(row, "scope_id", UUID)),
            policy_bundle_id=PolicyBundleId(_exact(row, "policy_bundle_id", UUID)),
            result=GateDecisionResult(_exact(row, "result", str)),
            conditions=GateDecisionConditionsJson(_json_object(row, "conditions")),
            evidence_artifact_id=ObjectArtifactId(
                _exact(row, "evidence_artifact_id", UUID)
            ),
            decided_by_principal_id=PrincipalId(
                _exact(row, "decided_by_principal_id", UUID)
            ),
            decided_at=AwareUtcDateTime(_exact(row, "decided_at", datetime)),
            expires_at=(
                None
                if row["expires_at"] is None
                else AwareUtcDateTime(_exact(row, "expires_at", datetime))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_policy_gate_decision(value: GateDecisionState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "gate_code",
            "scope_type",
            "scope_id",
            "policy_bundle_id",
            "result",
            "conditions",
            "evidence_artifact_id",
            "decided_by_principal_id",
            "decided_at",
            "expires_at",
            "created_at",
        ),
        domain_mappers.map_policy_gate_decision_to_row(value),
    )


def _decode_policy_policy_bundle(row: StorageRow) -> PolicyBundleState:
    columns = (
        "id",
        "display_id",
        "bundle_code",
        "version_no",
        "status",
        "git_commit_sha",
        "bundle_sha256",
        "effective_from",
        "effective_to",
        "approved_by_principal_id",
        "approved_at",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_policy_policy_bundle_from_row(
            id=PolicyBundleId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            bundle_code=_exact(row, "bundle_code", str),
            version_no=_exact(row, "version_no", int),
            status=PolicyBundleStatus(_exact(row, "status", str)),
            git_commit_sha=_exact(row, "git_commit_sha", str),
            bundle_sha256=Sha256Digest(_exact(row, "bundle_sha256", str)),
            effective_from=(
                None
                if row["effective_from"] is None
                else AwareUtcDateTime(_exact(row, "effective_from", datetime))
            ),
            effective_to=(
                None
                if row["effective_to"] is None
                else AwareUtcDateTime(_exact(row, "effective_to", datetime))
            ),
            approved_by_principal_id=(
                None
                if row["approved_by_principal_id"] is None
                else PrincipalId(_exact(row, "approved_by_principal_id", UUID))
            ),
            approved_at=(
                None
                if row["approved_at"] is None
                else AwareUtcDateTime(_exact(row, "approved_at", datetime))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_policy_policy_bundle(value: PolicyBundleState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "bundle_code",
            "version_no",
            "status",
            "git_commit_sha",
            "bundle_sha256",
            "effective_from",
            "effective_to",
            "approved_by_principal_id",
            "approved_at",
            "created_at",
        ),
        domain_mappers.map_policy_policy_bundle_to_row(value),
    )


def _decode_policy_quality_check_run(row: StorageRow) -> QualityCheckRunState:
    columns = (
        "id",
        "display_id",
        "article_version_id",
        "source_packet_version_id",
        "policy_bundle_id",
        "status",
        "triggered_by_actor_type",
        "triggered_by_actor_id",
        "started_at",
        "completed_at",
        "total_score",
        "blocking_finding_count",
        "report_artifact_id",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_policy_quality_check_run_from_row(
            id=QualityCheckRunId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            article_version_id=ArticleVersionId(
                _exact(row, "article_version_id", UUID)
            ),
            source_packet_version_id=SourcePacketVersionId(
                _exact(row, "source_packet_version_id", UUID)
            ),
            policy_bundle_id=PolicyBundleId(_exact(row, "policy_bundle_id", UUID)),
            status=QualityCheckRunStatus(_exact(row, "status", str)),
            triggered_by_actor_type=QualityCheckRunTriggeredByActorType(
                _exact(row, "triggered_by_actor_type", str)
            ),
            triggered_by_actor_id=(
                None
                if row["triggered_by_actor_id"] is None
                else TriggeredByActorId(_exact(row, "triggered_by_actor_id", UUID))
            ),
            started_at=AwareUtcDateTime(_exact(row, "started_at", datetime)),
            completed_at=(
                None
                if row["completed_at"] is None
                else AwareUtcDateTime(_exact(row, "completed_at", datetime))
            ),
            total_score=(
                None
                if row["total_score"] is None
                else _exact(row, "total_score", Decimal)
            ),
            blocking_finding_count=_exact(row, "blocking_finding_count", int),
            report_artifact_id=(
                None
                if row["report_artifact_id"] is None
                else ObjectArtifactId(_exact(row, "report_artifact_id", UUID))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_policy_quality_check_run(value: QualityCheckRunState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "article_version_id",
            "source_packet_version_id",
            "policy_bundle_id",
            "status",
            "triggered_by_actor_type",
            "triggered_by_actor_id",
            "started_at",
            "completed_at",
            "total_score",
            "blocking_finding_count",
            "report_artifact_id",
            "created_at",
        ),
        domain_mappers.map_policy_quality_check_run_to_row(value),
    )


def _decode_policy_quality_score(row: StorageRow) -> QualityScore:
    columns = (
        "id",
        "quality_check_run_id",
        "score_version",
        "total_score",
        "pass_score",
        "factual_accuracy_score",
        "disclosure_policy_score",
        "passed",
        "components",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_policy_quality_score_from_row(
            id=QualityScoreId(_exact(row, "id", UUID)),
            quality_check_run_id=QualityCheckRunId(
                _exact(row, "quality_check_run_id", UUID)
            ),
            score_version=_exact(row, "score_version", str),
            total_score=_exact(row, "total_score", Decimal),
            pass_score=_exact(row, "pass_score", Decimal),
            factual_accuracy_score=_exact(row, "factual_accuracy_score", Decimal),
            disclosure_policy_score=_exact(row, "disclosure_policy_score", Decimal),
            passed=_exact(row, "passed", bool),
            components=QualityScoreComponentsJson(_json_object(row, "components")),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_policy_quality_score(value: QualityScore) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "quality_check_run_id",
            "score_version",
            "total_score",
            "pass_score",
            "factual_accuracy_score",
            "disclosure_policy_score",
            "passed",
            "components",
            "created_at",
        ),
        domain_mappers.map_policy_quality_score_to_row(value),
    )


def _decode_policy_rule_version(row: StorageRow) -> RuleVersionState:
    columns = (
        "id",
        "rule_code",
        "version_no",
        "rule_category",
        "severity",
        "is_blocking",
        "implementation_type",
        "definition",
        "definition_sha256",
        "status",
        "created_by_principal_id",
        "approved_by_principal_id",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_policy_rule_version_from_row(
            id=RuleVersionId(_exact(row, "id", UUID)),
            rule_code=_exact(row, "rule_code", str),
            version_no=_exact(row, "version_no", int),
            rule_category=RuleVersionRuleCategory(_exact(row, "rule_category", str)),
            severity=RuleVersionSeverity(_exact(row, "severity", str)),
            is_blocking=_exact(row, "is_blocking", bool),
            implementation_type=RuleVersionImplementationType(
                _exact(row, "implementation_type", str)
            ),
            definition=RuleVersionDefinitionJson(_json_object(row, "definition")),
            definition_sha256=Sha256Digest(_exact(row, "definition_sha256", str)),
            status=RuleVersionStatus(_exact(row, "status", str)),
            created_by_principal_id=PrincipalId(
                _exact(row, "created_by_principal_id", UUID)
            ),
            approved_by_principal_id=(
                None
                if row["approved_by_principal_id"] is None
                else PrincipalId(_exact(row, "approved_by_principal_id", UUID))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_policy_rule_version(value: RuleVersionState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "rule_code",
            "version_no",
            "rule_category",
            "severity",
            "is_blocking",
            "implementation_type",
            "definition",
            "definition_sha256",
            "status",
            "created_by_principal_id",
            "approved_by_principal_id",
            "created_at",
        ),
        domain_mappers.map_policy_rule_version_to_row(value),
    )


def _decode_policy_waiver(row: StorageRow) -> WaiverState:
    columns = (
        "id",
        "display_id",
        "finding_id",
        "scope_type",
        "scope_id",
        "justification",
        "status",
        "requested_by_principal_id",
        "requested_at",
        "decided_by_principal_id",
        "decided_at",
        "decision_reason",
        "expires_at",
        "revoked_at",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_policy_waiver_from_row(
            id=WaiverId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            finding_id=FindingId(_exact(row, "finding_id", UUID)),
            scope_type=WaiverScopeType(_exact(row, "scope_type", str)),
            scope_id=ScopeId(_exact(row, "scope_id", UUID)),
            justification=_exact(row, "justification", str),
            status=WaiverStatus(_exact(row, "status", str)),
            requested_by_principal_id=PrincipalId(
                _exact(row, "requested_by_principal_id", UUID)
            ),
            requested_at=AwareUtcDateTime(_exact(row, "requested_at", datetime)),
            decided_by_principal_id=(
                None
                if row["decided_by_principal_id"] is None
                else PrincipalId(_exact(row, "decided_by_principal_id", UUID))
            ),
            decided_at=(
                None
                if row["decided_at"] is None
                else AwareUtcDateTime(_exact(row, "decided_at", datetime))
            ),
            decision_reason=(
                None
                if row["decision_reason"] is None
                else _exact(row, "decision_reason", str)
            ),
            expires_at=(
                None
                if row["expires_at"] is None
                else AwareUtcDateTime(_exact(row, "expires_at", datetime))
            ),
            revoked_at=(
                None
                if row["revoked_at"] is None
                else AwareUtcDateTime(_exact(row, "revoked_at", datetime))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_policy_waiver(value: WaiverState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "finding_id",
            "scope_type",
            "scope_id",
            "justification",
            "status",
            "requested_by_principal_id",
            "requested_at",
            "decided_by_principal_id",
            "decided_at",
            "decision_reason",
            "expires_at",
            "revoked_at",
            "created_at",
        ),
        domain_mappers.map_policy_waiver_to_row(value),
    )


# Aggregate-specific Session/Table-bound classes are the only POLICY DML surface.


@guard_repository_class
class SqlAlchemyPolicyBundleRepository:
    __slots__ = ("_binding", "_bundle", "_session")

    _EDGES = frozenset(
        {
            (PolicyBundleStatus.DRAFT, PolicyBundleStatus.ACTIVE),
            (PolicyBundleStatus.DRAFT, PolicyBundleStatus.REJECTED),
            (PolicyBundleStatus.DRAFT, PolicyBundleStatus.RETIRED),
            (PolicyBundleStatus.ACTIVE, PolicyBundleStatus.RETIRED),
        }
    )

    _CORE = (
        "id",
        "display_id",
        "bundle_code",
        "version_no",
        "git_commit_sha",
        "bundle_sha256",
        "created_at",
    )

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._bundle = _table("policy.policy_bundle")
        self._binding = _table("policy.bundle_rule")

    def get(self, bundle_id: PolicyBundleId) -> PolicyBundle | None:
        if type(bundle_id) is not PolicyBundleId:
            raise ValueError("INVALID_POLICY_BUNDLE_ID") from None
        row = _execute_one(
            self._session,
            select(self._bundle).where(self._bundle.c.id == bundle_id.value),
        )
        if row is None:
            return None
        bindings = tuple(
            _decode_policy_bundle_rule(item)
            for item in _execute_many(
                self._session,
                select(self._binding)
                .where(self._binding.c.policy_bundle_id == bundle_id.value)
                .order_by(
                    self._binding.c.policy_bundle_id,
                    self._binding.c.rule_version_id,
                ),
            )
        )
        bundle = PolicyBundle(
            state=_decode_policy_policy_bundle(row),
            bundle_rule_rows=bindings,
        )
        register_pending_events(
            self._session,
            aggregate_type="policy.policy_bundle",
            aggregate_id=bundle.state.id.value,
            buffer=aggregate_events_buffer(bundle),
        )
        return bundle

    def get_active(self, bundle_code: str) -> PolicyBundle | None:
        if type(bundle_code) is not str or not bundle_code:
            raise ValueError("INVALID_POLICY_BUNDLE_CODE") from None
        row = _execute_one(
            self._session,
            select(self._bundle)
            .where(
                self._bundle.c.bundle_code == bundle_code,
                self._bundle.c.status == PolicyBundleStatus.ACTIVE.value,
            )
            .order_by(self._bundle.c.version_no.desc(), self._bundle.c.id.desc())
            .limit(1),
        )
        if row is None:
            return None
        state = _decode_policy_policy_bundle(row)
        bindings = tuple(
            _decode_policy_bundle_rule(item)
            for item in _execute_many(
                self._session,
                select(self._binding)
                .where(self._binding.c.policy_bundle_id == state.id.value)
                .order_by(
                    self._binding.c.policy_bundle_id,
                    self._binding.c.rule_version_id,
                ),
            )
        )
        bundle = PolicyBundle(state=state, bundle_rule_rows=bindings)
        register_pending_events(
            self._session,
            aggregate_type="policy.policy_bundle",
            aggregate_id=bundle.state.id.value,
            buffer=aggregate_events_buffer(bundle),
        )
        return bundle

    def append_version(
        self,
        bundle: PolicyBundle,
        expected_latest_version: int | None,
    ) -> AggregateVersion:
        if type(bundle) is not PolicyBundle or any(
            item.policy_bundle_id != bundle.state.id for item in bundle.bundle_rule_rows
        ):
            raise ValueError("INVALID_POLICY_BUNDLE") from None
        if bundle.pending_events():
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        register_pending_events(
            self._session,
            aggregate_type="policy.policy_bundle",
            aggregate_id=bundle.state.id.value,
            buffer=aggregate_events_buffer(bundle),
        )
        observed = _latest_version(
            self._session,
            self._bundle,
            (self._bundle.c.bundle_code == bundle.state.bundle_code,),
        )
        persisted = _validate_append_version(
            bundle.state.version_no, expected_latest_version, observed
        )
        _execute(
            self._session,
            insert(self._bundle).values(**_encode_policy_policy_bundle(bundle.state)),
        )
        for binding in bundle.bundle_rule_rows:
            _execute(
                self._session,
                insert(self._binding).values(**_encode_policy_bundle_rule(binding)),
            )
        return persisted

    def bind_rules(
        self,
        bundle_id: PolicyBundleId,
        bindings: tuple[BundleRuleBinding, ...],
        expected_status: PolicyBundleStatus,
    ) -> None:
        if (
            type(bundle_id) is not PolicyBundleId
            or type(bindings) is not tuple
            or not bindings
            or any(type(item) is not BundleRuleBinding for item in bindings)
            or any(item.policy_bundle_id != bundle_id for item in bindings)
            or expected_status is not PolicyBundleStatus.DRAFT
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        owner = _execute_one(
            self._session,
            select(self._bundle.c.id, self._bundle.c.status)
            .where(self._bundle.c.id == bundle_id.value)
            .with_for_update(),
        )
        if owner is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        if owner.get("status") != expected_status.value:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        for binding in bindings:
            _execute(
                self._session,
                insert(self._binding).values(**_encode_policy_bundle_rule(binding)),
            )

    def transition(
        self,
        bundle_id: PolicyBundleId,
        transition: PolicyBundle,
        expected_status: PolicyBundleStatus,
    ) -> PolicyBundle:
        if (
            type(bundle_id) is not PolicyBundleId
            or type(transition) is not PolicyBundle
            or type(expected_status) is not PolicyBundleStatus
            or transition.state.id != bundle_id
            or transition.bundle_rule_rows
            or (expected_status, transition.state.status) not in self._EDGES
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        target = transition.state.status
        pending = transition.pending_events()
        emits = target is PolicyBundleStatus.ACTIVE
        if emits and not pending:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        if pending and (
            len(pending) != 1
            or type(pending[0]) is not PolicyPolicyBundleActivated
            or pending[0].aggregate_id != bundle_id
            or not emits
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        register_pending_events(
            self._session,
            aggregate_type="policy.policy_bundle",
            aggregate_id=bundle_id.value,
            buffer=aggregate_events_buffer(transition),
        )
        current_row = _execute_one(
            self._session,
            select(self._bundle).where(self._bundle.c.id == bundle_id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_policy_policy_bundle(current_row)
        if current.status is not expected_status:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_values = _encode_policy_policy_bundle(current)
        target_values = _encode_policy_policy_bundle(transition.state)
        mutable = {"status"}
        predicate = [
            self._bundle.c.id == bundle_id.value,
            self._bundle.c.status == expected_status.value,
        ]
        if expected_status is PolicyBundleStatus.DRAFT:
            predicate.extend(
                [
                    self._bundle.c.approved_by_principal_id.is_(None),
                    self._bundle.c.approved_at.is_(None),
                    self._bundle.c.effective_to.is_(None),
                ]
            )
        if target is PolicyBundleStatus.ACTIVE:
            mutable.update(
                {
                    "approved_by_principal_id",
                    "approved_at",
                    "effective_from",
                    "effective_to",
                }
            )
            actor_id = _context_actor_id(self._session)
            at = transaction_timestamp(self._session)
            effective_from = current.effective_from or at
            if (
                transition.state.approved_by_principal_id is None
                or transition.state.approved_by_principal_id.value != actor_id
                or transition.state.approved_at != at
                or transition.state.effective_from != effective_from
                or transition.state.effective_to is not None
            ):
                _fail(PersistenceErrorCode.STATE_CONFLICT)
            write_values: dict[str, object] = {
                "status": target.value,
                "approved_by_principal_id": actor_id,
                "approved_at": at.value,
                "effective_from": effective_from.value,
                "effective_to": None,
            }
        elif (
            expected_status is PolicyBundleStatus.ACTIVE
            and target is PolicyBundleStatus.RETIRED
        ):
            mutable.add("effective_to")
            predicate.extend(
                [
                    self._bundle.c.approved_by_principal_id.is_not(None),
                    self._bundle.c.approved_at.is_not(None),
                    self._bundle.c.effective_to.is_(None),
                ]
            )
            at = transaction_timestamp(self._session)
            if transition.state.effective_to != at:
                _fail(PersistenceErrorCode.STATE_CONFLICT)
            write_values = {"status": target.value, "effective_to": at.value}
        else:
            write_values = {"status": target.value}
        _require_same(
            current_values,
            target_values,
            tuple(name for name in current_values if name not in mutable),
        )
        row = _execute_one(
            self._session,
            update(self._bundle)
            .where(*predicate)
            .values(**write_values)
            .returning(self._bundle),
        )
        if row is None:
            _state_zero(self._session, self._bundle, bundle_id.value, expected_status)
        state = _decode_policy_policy_bundle(row)
        if emits:
            stage_registered_events(
                self._session,
                aggregate_type="policy.policy_bundle",
                aggregate_id=bundle_id.value,
                owning_method="PolicyBundleRepository.transition",
                persisted_version=AggregateVersion(state.version_no),
                expected_event_type="jp.raos.policy.policy_bundle_activated.v1",
            )
        return PolicyBundle(state=state)


@guard_repository_class
class SqlAlchemyRuleVersionRepository:
    __slots__ = ("_rule", "_session")

    _EDGES = frozenset(
        {
            (RuleVersionStatus.DRAFT, RuleVersionStatus.ACTIVE),
            (RuleVersionStatus.DRAFT, RuleVersionStatus.REJECTED),
            (RuleVersionStatus.DRAFT, RuleVersionStatus.RETIRED),
            (RuleVersionStatus.ACTIVE, RuleVersionStatus.RETIRED),
        }
    )

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._rule = _table("policy.rule_version")

    def get(self, rule_id: RuleVersionId) -> RuleVersion | None:
        if type(rule_id) is not RuleVersionId:
            raise ValueError("INVALID_RULE_VERSION_ID") from None
        row = _execute_one(
            self._session,
            select(self._rule).where(self._rule.c.id == rule_id.value),
        )
        return None if row is None else RuleVersion(_decode_policy_rule_version(row))

    def get_current(self, rule_code: str) -> RuleVersion | None:
        if type(rule_code) is not str or not rule_code:
            raise ValueError("INVALID_RULE_CODE") from None
        row = _execute_one(
            self._session,
            select(self._rule)
            .where(
                self._rule.c.rule_code == rule_code,
                self._rule.c.status == RuleVersionStatus.ACTIVE.value,
            )
            .order_by(self._rule.c.version_no.desc(), self._rule.c.id.desc())
            .limit(1),
        )
        return None if row is None else RuleVersion(_decode_policy_rule_version(row))

    def append_version(
        self,
        rule: RuleVersion,
        expected_latest_version: int | None,
    ) -> AggregateVersion:
        if type(rule) is not RuleVersion:
            raise ValueError("INVALID_RULE_VERSION") from None
        observed = _latest_version(
            self._session,
            self._rule,
            (self._rule.c.rule_code == rule.state.rule_code,),
        )
        persisted = _validate_append_version(
            rule.state.version_no, expected_latest_version, observed
        )
        _execute(
            self._session,
            insert(self._rule).values(**_encode_policy_rule_version(rule.state)),
        )
        return persisted

    def transition(
        self,
        rule_id: RuleVersionId,
        transition: RuleVersion,
        expected_status: RuleVersionStatus,
    ) -> RuleVersion:
        if (
            type(rule_id) is not RuleVersionId
            or type(transition) is not RuleVersion
            or type(expected_status) is not RuleVersionStatus
            or transition.state.id != rule_id
            or (expected_status, transition.state.status) not in self._EDGES
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_row = _execute_one(
            self._session,
            select(self._rule).where(self._rule.c.id == rule_id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_policy_rule_version(current_row)
        if current.status is not expected_status:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_values = _encode_policy_rule_version(current)
        target_values = _encode_policy_rule_version(transition.state)
        mutable = {"status"}
        predicate = [
            self._rule.c.id == rule_id.value,
            self._rule.c.status == expected_status.value,
        ]
        if expected_status is RuleVersionStatus.DRAFT:
            predicate.append(self._rule.c.approved_by_principal_id.is_(None))
        if transition.state.status is RuleVersionStatus.ACTIVE:
            mutable.add("approved_by_principal_id")
            actor_id = _context_actor_id(self._session)
            if (
                transition.state.approved_by_principal_id is None
                or transition.state.approved_by_principal_id.value != actor_id
            ):
                _fail(PersistenceErrorCode.STATE_CONFLICT)
            write_values: dict[str, object] = {
                "status": transition.state.status.value,
                "approved_by_principal_id": actor_id,
            }
        else:
            write_values = {"status": transition.state.status.value}
        if expected_status is RuleVersionStatus.ACTIVE:
            predicate.append(self._rule.c.approved_by_principal_id.is_not(None))
        _require_same(
            current_values,
            target_values,
            tuple(name for name in current_values if name not in mutable),
        )
        row = _execute_one(
            self._session,
            update(self._rule)
            .where(*predicate)
            .values(**write_values)
            .returning(self._rule),
        )
        if row is None:
            _state_zero(self._session, self._rule, rule_id.value, expected_status)
        return RuleVersion(_decode_policy_rule_version(row))


@guard_repository_class
class SqlAlchemyQualityCheckRunRepository:
    __slots__ = ("_run", "_score", "_session")

    _EDGES = frozenset(
        {
            (QualityCheckRunStatus.RUNNING, QualityCheckRunStatus.PASSED),
            (QualityCheckRunStatus.RUNNING, QualityCheckRunStatus.FAILED),
            (QualityCheckRunStatus.RUNNING, QualityCheckRunStatus.ERROR),
            (QualityCheckRunStatus.RUNNING, QualityCheckRunStatus.CANCELLED),
        }
    )

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._run = _table("policy.quality_check_run")
        self._score = _table("policy.quality_score")

    def get(self, run_id: QualityCheckRunId) -> QualityCheckRun | None:
        if type(run_id) is not QualityCheckRunId:
            raise ValueError("INVALID_QUALITY_CHECK_RUN_ID") from None
        row = _execute_one(
            self._session,
            select(self._run).where(self._run.c.id == run_id.value),
        )
        if row is None:
            return None
        scores = tuple(
            _decode_policy_quality_score(item)
            for item in _execute_many(
                self._session,
                select(self._score)
                .where(self._score.c.quality_check_run_id == run_id.value)
                .order_by(self._score.c.id),
            )
        )
        return QualityCheckRun(
            state=_decode_policy_quality_check_run(row),
            quality_score_rows=scores,
        )

    def add(self, run: QualityCheckRun) -> None:
        if type(run) is not QualityCheckRun or any(
            item.quality_check_run_id != run.state.id for item in run.quality_score_rows
        ):
            raise ValueError("INVALID_QUALITY_CHECK_RUN") from None
        _execute(
            self._session,
            insert(self._run).values(**_encode_policy_quality_check_run(run.state)),
        )
        for score in run.quality_score_rows:
            _execute(
                self._session,
                insert(self._score).values(**_encode_policy_quality_score(score)),
            )

    def transition(
        self,
        run_id: QualityCheckRunId,
        transition: QualityCheckRun,
        expected_status: QualityCheckRunStatus,
    ) -> QualityCheckRun:
        if (
            type(run_id) is not QualityCheckRunId
            or type(transition) is not QualityCheckRun
            or type(expected_status) is not QualityCheckRunStatus
            or transition.state.id != run_id
            or transition.quality_score_rows
            or (expected_status, transition.state.status) not in self._EDGES
            or transition.state.completed_at is None
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_row = _execute_one(
            self._session,
            select(self._run).where(self._run.c.id == run_id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_policy_quality_check_run(current_row)
        if current.status is not expected_status or current.completed_at is not None:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        at = transaction_timestamp(self._session)
        if transition.state.completed_at != at:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_values = _encode_policy_quality_check_run(current)
        target_values = _encode_policy_quality_check_run(transition.state)
        mutable = {
            "status",
            "completed_at",
            "total_score",
            "blocking_finding_count",
        }
        _require_same(
            current_values,
            target_values,
            tuple(name for name in current_values if name not in mutable),
        )
        row = _execute_one(
            self._session,
            update(self._run)
            .where(
                self._run.c.id == run_id.value,
                self._run.c.status == expected_status.value,
                self._run.c.completed_at.is_(None),
            )
            .values(
                status=transition.state.status.value,
                completed_at=at.value,
                total_score=target_values["total_score"],
                blocking_finding_count=target_values["blocking_finding_count"],
            )
            .returning(self._run),
        )
        if row is None:
            _state_zero(self._session, self._run, run_id.value, expected_status)
        return QualityCheckRun(state=_decode_policy_quality_check_run(row))

    def append_score(
        self,
        run_id: QualityCheckRunId,
        score: QualityScore,
        expected_status: QualityCheckRunStatus,
    ) -> None:
        if (
            type(run_id) is not QualityCheckRunId
            or type(score) is not QualityScore
            or score.quality_check_run_id != run_id
            or expected_status is not QualityCheckRunStatus.RUNNING
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        owner = _execute_one(
            self._session,
            select(self._run.c.id, self._run.c.status)
            .where(self._run.c.id == run_id.value)
            .with_for_update(),
        )
        if owner is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        if owner.get("status") != expected_status.value:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        _execute(
            self._session,
            insert(self._score).values(**_encode_policy_quality_score(score)),
        )


@guard_repository_class
class SqlAlchemyFindingRepository:
    __slots__ = ("_finding", "_session")

    _EDGES = frozenset(
        {
            (FindingStatus.OPEN, FindingStatus.FIXED),
            (FindingStatus.OPEN, FindingStatus.WAIVED),
            (FindingStatus.OPEN, FindingStatus.FALSE_POSITIVE),
            (FindingStatus.OPEN, FindingStatus.ACCEPTED_RISK),
        }
    )

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._finding = _table("policy.finding")

    def get(self, finding_id: FindingId) -> Finding | None:
        if type(finding_id) is not FindingId:
            raise ValueError("INVALID_FINDING_ID") from None
        row = _execute_one(
            self._session,
            select(self._finding).where(self._finding.c.id == finding_id.value),
        )
        return None if row is None else Finding(_decode_policy_finding(row))

    def append(self, finding: Finding) -> None:
        if type(finding) is not Finding:
            raise ValueError("INVALID_FINDING") from None
        _execute(
            self._session,
            insert(self._finding).values(**_encode_policy_finding(finding.state)),
        )

    def resolve(
        self,
        finding_id: FindingId,
        resolution: Finding,
        expected_status: FindingStatus,
    ) -> Finding:
        if (
            type(finding_id) is not FindingId
            or type(resolution) is not Finding
            or type(expected_status) is not FindingStatus
            or resolution.state.id != finding_id
            or (expected_status, resolution.state.status) not in self._EDGES
            or resolution.state.resolved_at is None
            or resolution.state.resolved_by_principal_id is None
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_row = _execute_one(
            self._session,
            select(self._finding).where(self._finding.c.id == finding_id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_policy_finding(current_row)
        if (
            current.status is not expected_status
            or current.resolved_at is not None
            or current.resolved_by_principal_id is not None
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        actor_id = _context_actor_id(self._session)
        if resolution.state.resolved_by_principal_id.value != actor_id:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_values = _encode_policy_finding(current)
        target_values = _encode_policy_finding(resolution.state)
        mutable = {"status", "resolved_at", "resolved_by_principal_id"}
        _require_same(
            current_values,
            target_values,
            tuple(name for name in current_values if name not in mutable),
        )
        row = _execute_one(
            self._session,
            update(self._finding)
            .where(
                self._finding.c.id == finding_id.value,
                self._finding.c.status == expected_status.value,
                self._finding.c.resolved_at.is_(None),
                self._finding.c.resolved_by_principal_id.is_(None),
            )
            .values(
                status=resolution.state.status.value,
                resolved_at=target_values["resolved_at"],
                resolved_by_principal_id=actor_id,
            )
            .returning(self._finding),
        )
        if row is None:
            _state_zero(self._session, self._finding, finding_id.value, expected_status)
        return Finding(_decode_policy_finding(row))


@guard_repository_class
class SqlAlchemyWaiverRepository:
    __slots__ = ("_session", "_waiver")

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._waiver = _table("policy.waiver")

    def get(self, waiver_id: WaiverId) -> Waiver | None:
        if type(waiver_id) is not WaiverId:
            raise ValueError("INVALID_WAIVER_ID") from None
        row = _execute_one(
            self._session,
            select(self._waiver).where(self._waiver.c.id == waiver_id.value),
        )
        return None if row is None else Waiver(_decode_policy_waiver(row))

    def append_request(self, waiver: Waiver) -> None:
        if (
            type(waiver) is not Waiver
            or waiver.state.status is not WaiverStatus.REQUESTED
        ):
            raise ValueError("INVALID_WAIVER_REQUEST") from None
        _execute(
            self._session,
            insert(self._waiver).values(**_encode_policy_waiver(waiver.state)),
        )

    def decide(
        self,
        waiver_id: WaiverId,
        decision: Waiver,
        expected_status: WaiverStatus,
    ) -> Waiver:
        target = decision.state.status if type(decision) is Waiver else None
        if (
            type(waiver_id) is not WaiverId
            or type(decision) is not Waiver
            or expected_status is not WaiverStatus.REQUESTED
            or decision.state.id != waiver_id
            or target not in {WaiverStatus.APPROVED, WaiverStatus.REJECTED}
            or decision.state.decided_by_principal_id is None
            or decision.state.decided_at is None
            or decision.state.decision_reason is None
            or not decision.state.decision_reason.strip()
            or decision.state.revoked_at is not None
            or (
                target is WaiverStatus.APPROVED
                and (
                    decision.state.expires_at is None
                    or decision.state.expires_at.value
                    <= decision.state.decided_at.value
                )
            )
            or (
                target is WaiverStatus.REJECTED
                and decision.state.expires_at is not None
            )
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_row = _execute_one(
            self._session,
            select(self._waiver).where(self._waiver.c.id == waiver_id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_policy_waiver(current_row)
        if (
            current.status is not expected_status
            or current.decided_by_principal_id is not None
            or current.decided_at is not None
            or current.decision_reason is not None
            or current.expires_at is not None
            or current.revoked_at is not None
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        actor_id = _context_actor_id(self._session)
        if decision.state.decided_by_principal_id.value != actor_id:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_values = _encode_policy_waiver(current)
        target_values = _encode_policy_waiver(decision.state)
        mutable = {
            "status",
            "decided_by_principal_id",
            "decided_at",
            "decision_reason",
            "expires_at",
        }
        _require_same(
            current_values,
            target_values,
            tuple(name for name in current_values if name not in mutable),
        )
        row = _execute_one(
            self._session,
            update(self._waiver)
            .where(
                self._waiver.c.id == waiver_id.value,
                self._waiver.c.status == expected_status.value,
                self._waiver.c.decided_by_principal_id.is_(None),
                self._waiver.c.decided_at.is_(None),
                self._waiver.c.decision_reason.is_(None),
                self._waiver.c.expires_at.is_(None),
                self._waiver.c.revoked_at.is_(None),
            )
            .values(
                status=decision.state.status.value,
                decided_by_principal_id=actor_id,
                decided_at=target_values["decided_at"],
                decision_reason=target_values["decision_reason"],
                expires_at=target_values["expires_at"],
            )
            .returning(self._waiver),
        )
        if row is None:
            _state_zero(self._session, self._waiver, waiver_id.value, expected_status)
        return Waiver(_decode_policy_waiver(row))

    def revoke(
        self,
        waiver_id: WaiverId,
        revocation: Waiver,
        expected_status: WaiverStatus,
    ) -> Waiver:
        if (
            type(waiver_id) is not WaiverId
            or type(revocation) is not Waiver
            or expected_status is not WaiverStatus.APPROVED
            or revocation.state.id != waiver_id
            or revocation.state.status is not WaiverStatus.REVOKED
            or revocation.state.revoked_at is None
            or revocation.state.expires_at is None
            or revocation.state.expires_at.value <= revocation.state.revoked_at.value
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_row = _execute_one(
            self._session,
            select(self._waiver).where(self._waiver.c.id == waiver_id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_policy_waiver(current_row)
        if (
            current.status is not expected_status
            or current.decided_by_principal_id is None
            or current.decided_at is None
            or current.decision_reason is None
            or current.expires_at is None
            or current.expires_at.value <= revocation.state.revoked_at.value
            or current.revoked_at is not None
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_values = _encode_policy_waiver(current)
        target_values = _encode_policy_waiver(revocation.state)
        mutable = {"status", "revoked_at"}
        _require_same(
            current_values,
            target_values,
            tuple(name for name in current_values if name not in mutable),
        )
        row = _execute_one(
            self._session,
            update(self._waiver)
            .where(
                self._waiver.c.id == waiver_id.value,
                self._waiver.c.status == expected_status.value,
                self._waiver.c.decided_by_principal_id.is_not(None),
                self._waiver.c.decided_at.is_not(None),
                self._waiver.c.decision_reason.is_not(None),
                self._waiver.c.expires_at.is_not(None),
                self._waiver.c.expires_at > target_values["revoked_at"],
                self._waiver.c.revoked_at.is_(None),
            )
            .values(
                status=WaiverStatus.REVOKED.value,
                revoked_at=target_values["revoked_at"],
            )
            .returning(self._waiver),
        )
        if row is None:
            _state_zero(self._session, self._waiver, waiver_id.value, expected_status)
        return Waiver(_decode_policy_waiver(row))

    def mark_expired(
        self,
        waiver_id: WaiverId,
        evaluated_at: AwareUtcDateTime,
        expected_status: WaiverStatus,
    ) -> Waiver:
        if (
            type(waiver_id) is not WaiverId
            or type(evaluated_at) is not AwareUtcDateTime
            or expected_status is not WaiverStatus.APPROVED
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_row = _execute_one(
            self._session,
            select(self._waiver).where(self._waiver.c.id == waiver_id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_policy_waiver(current_row)
        if (
            current.status is not expected_status
            or current.decided_by_principal_id is None
            or current.decided_at is None
            or current.decision_reason is None
            or current.expires_at is None
            or current.expires_at.value > evaluated_at.value
            or current.revoked_at is not None
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        row = _execute_one(
            self._session,
            update(self._waiver)
            .where(
                self._waiver.c.id == waiver_id.value,
                self._waiver.c.status == expected_status.value,
                self._waiver.c.decided_by_principal_id.is_not(None),
                self._waiver.c.decided_at.is_not(None),
                self._waiver.c.decision_reason.is_not(None),
                self._waiver.c.expires_at.is_not(None),
                self._waiver.c.expires_at <= evaluated_at.value,
                self._waiver.c.revoked_at.is_(None),
            )
            .values(status=WaiverStatus.EXPIRED.value)
            .returning(self._waiver),
        )
        if row is None:
            _state_zero(self._session, self._waiver, waiver_id.value, expected_status)
        return Waiver(_decode_policy_waiver(row))


@guard_repository_class
class SqlAlchemyGateDecisionRepository:
    __slots__ = ("_decision", "_session")

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._decision = _table("policy.gate_decision")

    def get(self, decision_id: GateDecisionId) -> GateDecision | None:
        if type(decision_id) is not GateDecisionId:
            raise ValueError("INVALID_GATE_DECISION_ID") from None
        row = _execute_one(
            self._session,
            select(self._decision).where(self._decision.c.id == decision_id.value),
        )
        return None if row is None else GateDecision(_decode_policy_gate_decision(row))

    def append(self, decision: GateDecision) -> None:
        if type(decision) is not GateDecision:
            raise ValueError("INVALID_GATE_DECISION") from None
        _execute(
            self._session,
            insert(self._decision).values(
                **_encode_policy_gate_decision(decision.state)
            ),
        )


__all__ = [
    "SqlAlchemyFindingRepository",
    "SqlAlchemyGateDecisionRepository",
    "SqlAlchemyPolicyBundleRepository",
    "SqlAlchemyQualityCheckRunRepository",
    "SqlAlchemyRuleVersionRepository",
    "SqlAlchemyWaiverRepository",
]

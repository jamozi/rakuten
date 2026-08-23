"""Concrete scalar codecs and aggregate-specific SQLAlchemy repositories for AI."""

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

import raos.adapters.persistence.sqlalchemy.mappers.ai as domain_mappers
from raos.adapters.persistence.sqlalchemy.session_runtime import (
    fail_session_operation,
    guard_repository_class,
    register_pending_events,
    stage_registered_events,
    transaction_timestamp,
)
from raos.domain.ai.aggregates import (
    AiAttempt,
    AiAttemptState,
    AiJob,
    AiJobState,
    AiTaskDefinition,
    AiTaskDefinitionState,
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationDatasetVersion,
    EvaluationDatasetVersionState,
    EvaluationResult,
    EvaluationResultState,
    EvaluationRun,
    EvaluationRunState,
    EvaluationSuite,
    EvaluationSuiteState,
    HumanEvaluation,
    JudgeCalibration,
    JudgeCalibrationState,
    ModelDefinition,
    ModelDefinitionState,
    ModelRouteVersion,
    ModelRouteVersionState,
    OutputSchemaVersion,
    OutputSchemaVersionState,
    PromptVersion,
    PromptVersionState,
    ReleaseApproval,
    ReleaseDecision,
    ReleaseDecisionState,
    UsageCost,
)
from raos.domain.ai.enums import (
    AiAttemptStatus,
    AiAttemptValidationStatus,
    AiJobStatus,
    AiTaskDefinitionRiskLevel,
    AiTaskDefinitionStatus,
    EvaluationCaseExpectedDisposition,
    EvaluationCaseResultDisposition,
    EvaluationCaseResultStatus,
    EvaluationCaseRiskLevel,
    EvaluationCaseSplit,
    EvaluationDatasetStatus,
    EvaluationResultMetricCode,
    EvaluationResultThresholdOperator,
    EvaluationRunStatus,
    EvaluationSuiteRiskLevel,
    EvaluationSuiteStatus,
    HumanEvaluationDecision,
    JudgeCalibrationStatus,
    ModelDefinitionStatus,
    ModelRouteVersionStatus,
    OutputSchemaVersionStatus,
    PromptVersionPolicyTestStatus,
    PromptVersionStatus,
    ReleaseApprovalPhase,
    ReleaseDecisionReleaseScope,
    ReleaseDecisionRollbackStrategy,
    ReleaseDecisionStatus,
)
from raos.domain.ai.events import (
    AiEvaluationCompletedV2,
    AiJobFailed,
    AiJobRequested,
    AiJobSucceeded,
    AiPolicyAssistCompleted,
    AiReleaseDecisionApproved,
    AiReleaseDecisionRevoked,
)
from raos.domain.ai.ids import (
    AiAttemptId,
    AiJobId,
    AiTaskDefinitionId,
    EvaluationCaseId,
    EvaluationCaseResultId,
    EvaluationDatasetVersionId,
    EvaluationResultId,
    EvaluationRunId,
    EvaluationSuiteId,
    HumanEvaluationId,
    JudgeCalibrationId,
    ModelDefinitionId,
    ModelRouteVersionId,
    OutputSchemaVersionId,
    PromptVersionId,
    ReleaseApprovalId,
    ReleaseDecisionId,
    UsageCostId,
)
from raos.domain.ai.values import (
    AiAttemptRequestConfigJson,
    AiJobRequestConfigJson,
    EvaluationCaseMetadataJson,
    EvaluationCaseResultGraderSummaryJson,
    EvaluationCaseResultZeroToleranceEvidenceJson,
    EvaluationDatasetVersionSplitPolicyJson,
    EvaluationResultDetailsJson,
    EvaluationSuiteSuiteConfigJson,
    HumanEvaluationScoresJson,
    ModelDefinitionCapabilitiesJson,
    ModelDefinitionProviderMetadataJson,
    ModelRouteVersionRouteConfigJson,
)
from raos.domain.editorial.ids import (
    ArticlePlanId,
    ArticleVersionId,
)
from raos.domain.evidence.ids import (
    SourcePacketVersionId,
)
from raos.domain.iam.ids import (
    PrincipalId,
)
from raos.domain.ops.ids import (
    JobId,
    ObjectArtifactId,
)
from raos.domain.policy.ids import (
    PolicyBundleId,
)
from raos.domain.shared.identity import (
    EntityId,
    RunId,
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

        table = TABLES_BY_RELATION[relation]
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


def _optional(row: StorageRow, key: str, expected: type[T]) -> T | None:
    try:
        value = row[key]
    except KeyError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    if value is None:
        return None
    if type(value) is not expected:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return value


def _json_object(row: StorageRow, key: str) -> FrozenJsonObject:
    value = _exact(row, key, dict)
    try:
        return FrozenJsonObject.from_mapping(value)
    except ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _string_array(row: StorageRow, key: str) -> tuple[str, ...]:
    try:
        value = row[key]
    except KeyError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    if type(value) not in {list, tuple}:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    items = cast(list[object] | tuple[object, ...], value)
    if any(type(item) is not str for item in items):
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return cast(tuple[str, ...], tuple(items))


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
    if type(value) is tuple and all(type(item) is str for item in value):
        return list(value)
    if isinstance(
        value,
        (
            AiAttemptRequestConfigJson,
            AiJobRequestConfigJson,
            EvaluationCaseMetadataJson,
            EvaluationCaseResultGraderSummaryJson,
            EvaluationCaseResultZeroToleranceEvidenceJson,
            EvaluationDatasetVersionSplitPolicyJson,
            EvaluationResultDetailsJson,
            EvaluationSuiteSuiteConfigJson,
            HumanEvaluationScoresJson,
            ModelDefinitionCapabilitiesJson,
            ModelDefinitionProviderMetadataJson,
            ModelRouteVersionRouteConfigJson,
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
    if not isinstance(session, Session):
        raise ValueError("INVALID_AI_REPOSITORY") from None


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


def _lock_zero(
    session: Session,
    table: Table,
    identifier: UUID,
    expected_version: AggregateVersion,
) -> NoReturn:
    row = _execute_one(
        session,
        select(table.c.id, table.c.lock_version).where(table.c.id == identifier),
    )
    if row is None:
        _fail(PersistenceErrorCode.NOT_FOUND)
    stored_id = _exact(row, "id", UUID)
    stored_version = _exact(row, "lock_version", int)
    if stored_id != identifier:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    if stored_version != expected_version.value:
        _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
    _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _cas_row(
    session: Session,
    table: Table,
    identifier: UUID,
    expected_version: AggregateVersion,
    values: dict[str, object],
) -> RowMapping:
    if values.get("id") != identifier or values.get("lock_version") != (
        expected_version.value + 1
    ):
        raise ValueError("INVALID_AI_CAS_VERSION") from None
    proposed = dict(values)
    proposed.pop("id")
    proposed["lock_version"] = expected_version.value + 1
    row = _execute_one(
        session,
        update(table)
        .where(
            table.c.id == identifier,
            table.c.lock_version == expected_version.value,
        )
        .values(**proposed)
        .returning(table),
    )
    if row is None:
        _lock_zero(session, table, identifier, expected_version)
    return row


def _cas_bump(
    session: Session,
    table: Table,
    identifier: UUID,
    expected_version: AggregateVersion,
) -> AggregateVersion:
    row = _execute_one(
        session,
        update(table)
        .where(
            table.c.id == identifier,
            table.c.lock_version == expected_version.value,
        )
        .values(lock_version=expected_version.value + 1)
        .returning(table.c.lock_version),
    )
    if row is None:
        _lock_zero(session, table, identifier, expected_version)
    persisted = row.get("lock_version")
    if type(persisted) is not int or persisted != expected_version.value + 1:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return AggregateVersion(persisted)


def _require_same(
    current: Mapping[str, object],
    target: Mapping[str, object],
    immutable: tuple[str, ...],
    code: PersistenceErrorCode,
) -> None:
    if any(current[name] != target[name] for name in immutable):
        _fail(code)


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


def _decode_ai_ai_attempt(row: StorageRow) -> AiAttemptState:
    columns = (
        "id",
        "ai_job_id",
        "attempt_no",
        "model_id",
        "provider_request_id",
        "status",
        "input_artifact_id",
        "output_artifact_id",
        "input_sha256",
        "output_sha256",
        "refusal_code",
        "finish_reason",
        "latency_ms",
        "error_class",
        "error_code",
        "error_message",
        "started_at",
        "completed_at",
        "created_at",
        "requested_model_id",
        "resolved_model_id",
        "response_fingerprint",
        "provider_region",
        "request_config",
        "validation_status",
        "safety_identifier_hash",
        "repair_attempt_no",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_ai_ai_attempt_from_row(
            id=AiAttemptId(_exact(row, "id", UUID)),
            ai_job_id=AiJobId(_exact(row, "ai_job_id", UUID)),
            attempt_no=_exact(row, "attempt_no", int),
            model_id=ModelDefinitionId(_exact(row, "model_id", UUID)),
            provider_request_id=(
                None
                if row["provider_request_id"] is None
                else _exact(row, "provider_request_id", str)
            ),
            status=AiAttemptStatus(_exact(row, "status", str)),
            input_artifact_id=ObjectArtifactId(_exact(row, "input_artifact_id", UUID)),
            output_artifact_id=(
                None
                if row["output_artifact_id"] is None
                else ObjectArtifactId(_exact(row, "output_artifact_id", UUID))
            ),
            input_sha256=Sha256Digest(_exact(row, "input_sha256", str)),
            output_sha256=(
                None
                if row["output_sha256"] is None
                else Sha256Digest(_exact(row, "output_sha256", str))
            ),
            refusal_code=(
                None
                if row["refusal_code"] is None
                else _exact(row, "refusal_code", str)
            ),
            finish_reason=(
                None
                if row["finish_reason"] is None
                else _exact(row, "finish_reason", str)
            ),
            latency_ms=(
                None if row["latency_ms"] is None else _exact(row, "latency_ms", int)
            ),
            error_class=(
                None if row["error_class"] is None else _exact(row, "error_class", str)
            ),
            error_code=(
                None if row["error_code"] is None else _exact(row, "error_code", str)
            ),
            error_message=(
                None
                if row["error_message"] is None
                else _exact(row, "error_message", str)
            ),
            started_at=AwareUtcDateTime(_exact(row, "started_at", datetime)),
            completed_at=(
                None
                if row["completed_at"] is None
                else AwareUtcDateTime(_exact(row, "completed_at", datetime))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            requested_model_id=_exact(row, "requested_model_id", str),
            resolved_model_id=_exact(row, "resolved_model_id", str),
            response_fingerprint=(
                None
                if row["response_fingerprint"] is None
                else _exact(row, "response_fingerprint", str)
            ),
            provider_region=(
                None
                if row["provider_region"] is None
                else _exact(row, "provider_region", str)
            ),
            request_config=AiAttemptRequestConfigJson(
                _json_object(row, "request_config")
            ),
            validation_status=AiAttemptValidationStatus(
                _exact(row, "validation_status", str)
            ),
            safety_identifier_hash=(
                None
                if row["safety_identifier_hash"] is None
                else Sha256Digest(_exact(row, "safety_identifier_hash", str))
            ),
            repair_attempt_no=_exact(row, "repair_attempt_no", int),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_ai_ai_attempt(value: AiAttemptState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "ai_job_id",
            "attempt_no",
            "model_id",
            "provider_request_id",
            "status",
            "input_artifact_id",
            "output_artifact_id",
            "input_sha256",
            "output_sha256",
            "refusal_code",
            "finish_reason",
            "latency_ms",
            "error_class",
            "error_code",
            "error_message",
            "started_at",
            "completed_at",
            "created_at",
            "requested_model_id",
            "resolved_model_id",
            "response_fingerprint",
            "provider_region",
            "request_config",
            "validation_status",
            "safety_identifier_hash",
            "repair_attempt_no",
        ),
        domain_mappers.map_ai_ai_attempt_to_row(value),
    )


def _decode_ai_ai_job(row: StorageRow) -> AiJobState:
    columns = (
        "id",
        "display_id",
        "ops_job_id",
        "task_definition_id",
        "article_plan_id",
        "article_version_id",
        "source_packet_version_id",
        "prompt_version_id",
        "output_schema_version_id",
        "model_route_version_id",
        "status",
        "max_cost_jpy",
        "completed_at",
        "created_at",
        "policy_bundle_version_id",
        "release_decision_id",
        "request_config",
        "input_manifest_sha256",
        "budget_reserved_jpy",
        "lock_version",
        "updated_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_ai_ai_job_from_row(
            id=AiJobId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            ops_job_id=JobId(_exact(row, "ops_job_id", UUID)),
            task_definition_id=AiTaskDefinitionId(
                _exact(row, "task_definition_id", UUID)
            ),
            article_plan_id=(
                None
                if row["article_plan_id"] is None
                else ArticlePlanId(_exact(row, "article_plan_id", UUID))
            ),
            article_version_id=(
                None
                if row["article_version_id"] is None
                else ArticleVersionId(_exact(row, "article_version_id", UUID))
            ),
            source_packet_version_id=SourcePacketVersionId(
                _exact(row, "source_packet_version_id", UUID)
            ),
            prompt_version_id=PromptVersionId(_exact(row, "prompt_version_id", UUID)),
            output_schema_version_id=OutputSchemaVersionId(
                _exact(row, "output_schema_version_id", UUID)
            ),
            model_route_version_id=ModelRouteVersionId(
                _exact(row, "model_route_version_id", UUID)
            ),
            status=AiJobStatus(_exact(row, "status", str)),
            max_cost_jpy=YenMinor(_exact(row, "max_cost_jpy", int)),
            completed_at=(
                None
                if row["completed_at"] is None
                else AwareUtcDateTime(_exact(row, "completed_at", datetime))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            policy_bundle_version_id=(
                None
                if row["policy_bundle_version_id"] is None
                else PolicyBundleId(_exact(row, "policy_bundle_version_id", UUID))
            ),
            release_decision_id=(
                None
                if row["release_decision_id"] is None
                else ReleaseDecisionId(_exact(row, "release_decision_id", UUID))
            ),
            request_config=AiJobRequestConfigJson(_json_object(row, "request_config")),
            input_manifest_sha256=(
                None
                if row["input_manifest_sha256"] is None
                else Sha256Digest(_exact(row, "input_manifest_sha256", str))
            ),
            budget_reserved_jpy=YenMinor(_exact(row, "budget_reserved_jpy", int)),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_ai_ai_job(value: AiJobState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "ops_job_id",
            "task_definition_id",
            "article_plan_id",
            "article_version_id",
            "source_packet_version_id",
            "prompt_version_id",
            "output_schema_version_id",
            "model_route_version_id",
            "status",
            "max_cost_jpy",
            "completed_at",
            "created_at",
            "policy_bundle_version_id",
            "release_decision_id",
            "request_config",
            "input_manifest_sha256",
            "budget_reserved_jpy",
            "lock_version",
            "updated_at",
        ),
        domain_mappers.map_ai_ai_job_to_row(value),
    )


def _decode_ai_evaluation_case(row: StorageRow) -> EvaluationCase:
    columns = (
        "id",
        "dataset_version_id",
        "case_key",
        "task_definition_id",
        "split",
        "category",
        "risk_level",
        "input_artifact_id",
        "gold_artifact_id",
        "expected_disposition",
        "tags",
        "metadata",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_ai_evaluation_case_from_row(
            id=EvaluationCaseId(_exact(row, "id", UUID)),
            dataset_version_id=EvaluationDatasetVersionId(
                _exact(row, "dataset_version_id", UUID)
            ),
            case_key=_exact(row, "case_key", str),
            task_definition_id=AiTaskDefinitionId(
                _exact(row, "task_definition_id", UUID)
            ),
            split=EvaluationCaseSplit(_exact(row, "split", str)),
            category=_exact(row, "category", str),
            risk_level=EvaluationCaseRiskLevel(_exact(row, "risk_level", str)),
            input_artifact_id=ObjectArtifactId(_exact(row, "input_artifact_id", UUID)),
            gold_artifact_id=(
                None
                if row["gold_artifact_id"] is None
                else ObjectArtifactId(_exact(row, "gold_artifact_id", UUID))
            ),
            expected_disposition=EvaluationCaseExpectedDisposition(
                _exact(row, "expected_disposition", str)
            ),
            tags=_string_array(row, "tags"),
            metadata=EvaluationCaseMetadataJson(_json_object(row, "metadata")),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_ai_evaluation_case(value: EvaluationCase) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "dataset_version_id",
            "case_key",
            "task_definition_id",
            "split",
            "category",
            "risk_level",
            "input_artifact_id",
            "gold_artifact_id",
            "expected_disposition",
            "tags",
            "metadata",
            "created_at",
        ),
        domain_mappers.map_ai_evaluation_case_to_row(value),
    )


def _decode_ai_evaluation_case_result(
    row: StorageRow,
) -> EvaluationCaseResult:
    columns = (
        "id",
        "evaluation_run_id",
        "evaluation_case_id",
        "ai_attempt_id",
        "output_artifact_id",
        "status",
        "disposition",
        "zero_tolerance_evidence",
        "zero_tolerance_evidence_artifact_id",
        "zero_tolerance_evidence_sha256",
        "zero_tolerance_failure_count",
        "grader_summary",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_ai_evaluation_case_result_from_row(
            id=EvaluationCaseResultId(_exact(row, "id", UUID)),
            evaluation_run_id=EvaluationRunId(_exact(row, "evaluation_run_id", UUID)),
            evaluation_case_id=EvaluationCaseId(
                _exact(row, "evaluation_case_id", UUID)
            ),
            ai_attempt_id=(
                None
                if row["ai_attempt_id"] is None
                else AiAttemptId(_exact(row, "ai_attempt_id", UUID))
            ),
            output_artifact_id=(
                None
                if row["output_artifact_id"] is None
                else ObjectArtifactId(_exact(row, "output_artifact_id", UUID))
            ),
            status=EvaluationCaseResultStatus(_exact(row, "status", str)),
            disposition=EvaluationCaseResultDisposition(
                _exact(row, "disposition", str)
            ),
            zero_tolerance_evidence=EvaluationCaseResultZeroToleranceEvidenceJson(
                _json_object(row, "zero_tolerance_evidence")
            ),
            zero_tolerance_evidence_artifact_id=ObjectArtifactId(
                _exact(row, "zero_tolerance_evidence_artifact_id", UUID)
            ),
            zero_tolerance_evidence_sha256=Sha256Digest(
                _exact(row, "zero_tolerance_evidence_sha256", str)
            ),
            zero_tolerance_failure_count=_exact(
                row, "zero_tolerance_failure_count", int
            ),
            grader_summary=EvaluationCaseResultGraderSummaryJson(
                _json_object(row, "grader_summary")
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_ai_evaluation_case_result(value: EvaluationCaseResult) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "evaluation_run_id",
            "evaluation_case_id",
            "ai_attempt_id",
            "output_artifact_id",
            "status",
            "disposition",
            "zero_tolerance_evidence",
            "zero_tolerance_evidence_artifact_id",
            "zero_tolerance_evidence_sha256",
            "zero_tolerance_failure_count",
            "grader_summary",
            "created_at",
        ),
        domain_mappers.map_ai_evaluation_case_result_to_row(value),
    )


def _decode_ai_evaluation_dataset_version(
    row: StorageRow,
) -> EvaluationDatasetVersionState:
    columns = (
        "id",
        "display_id",
        "dataset_code",
        "version_no",
        "purpose",
        "split_policy",
        "dataset_artifact_id",
        "dataset_sha256",
        "case_count",
        "status",
        "locked_by_principal_id",
        "locked_at",
        "compromised_at",
        "lock_version",
        "created_at",
        "updated_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_ai_evaluation_dataset_version_from_row(
            id=EvaluationDatasetVersionId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            dataset_code=_exact(row, "dataset_code", str),
            version_no=_exact(row, "version_no", int),
            purpose=_exact(row, "purpose", str),
            split_policy=EvaluationDatasetVersionSplitPolicyJson(
                _json_object(row, "split_policy")
            ),
            dataset_artifact_id=ObjectArtifactId(
                _exact(row, "dataset_artifact_id", UUID)
            ),
            dataset_sha256=Sha256Digest(_exact(row, "dataset_sha256", str)),
            case_count=_exact(row, "case_count", int),
            status=EvaluationDatasetStatus(_exact(row, "status", str)),
            locked_by_principal_id=(
                None
                if row["locked_by_principal_id"] is None
                else PrincipalId(_exact(row, "locked_by_principal_id", UUID))
            ),
            locked_at=(
                None
                if row["locked_at"] is None
                else AwareUtcDateTime(_exact(row, "locked_at", datetime))
            ),
            compromised_at=(
                None
                if row["compromised_at"] is None
                else AwareUtcDateTime(_exact(row, "compromised_at", datetime))
            ),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_ai_evaluation_dataset_version(
    value: EvaluationDatasetVersionState,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "dataset_code",
            "version_no",
            "purpose",
            "split_policy",
            "dataset_artifact_id",
            "dataset_sha256",
            "case_count",
            "status",
            "locked_by_principal_id",
            "locked_at",
            "compromised_at",
            "lock_version",
            "created_at",
            "updated_at",
        ),
        domain_mappers.map_ai_evaluation_dataset_version_to_row(value),
    )


def _decode_ai_evaluation_result(row: StorageRow) -> EvaluationResultState:
    columns = (
        "id",
        "suite_code",
        "suite_version",
        "run_id",
        "task_definition_id",
        "model_route_version_id",
        "prompt_version_id",
        "case_key",
        "metric_code",
        "metric_value",
        "passed",
        "details",
        "result_artifact_id",
        "created_at",
        "evaluation_run_id",
        "evaluation_case_id",
        "grader_code",
        "slice_key",
        "threshold_operator",
        "threshold_value",
        "judge_calibration_id",
        "judge_route_version_id",
        "judge_prompt_version_id",
        "judge_rubric_artifact_id",
        "judge_resolved_model_id",
        "judge_grader_version",
        "proportion_numerator_count",
        "proportion_denominator_count",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_ai_evaluation_result_from_row(
            id=EvaluationResultId(_exact(row, "id", UUID)),
            suite_code=_exact(row, "suite_code", str),
            suite_version=_exact(row, "suite_version", int),
            run_id=RunId(_exact(row, "run_id", UUID)),
            task_definition_id=AiTaskDefinitionId(
                _exact(row, "task_definition_id", UUID)
            ),
            model_route_version_id=ModelRouteVersionId(
                _exact(row, "model_route_version_id", UUID)
            ),
            prompt_version_id=PromptVersionId(_exact(row, "prompt_version_id", UUID)),
            case_key=_exact(row, "case_key", str),
            metric_code=EvaluationResultMetricCode(_exact(row, "metric_code", str)),
            metric_value=_exact(row, "metric_value", Decimal),
            passed=(None if row["passed"] is None else _exact(row, "passed", bool)),
            details=EvaluationResultDetailsJson(_json_object(row, "details")),
            result_artifact_id=(
                None
                if row["result_artifact_id"] is None
                else ObjectArtifactId(_exact(row, "result_artifact_id", UUID))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            evaluation_run_id=(
                None
                if row["evaluation_run_id"] is None
                else EvaluationRunId(_exact(row, "evaluation_run_id", UUID))
            ),
            evaluation_case_id=(
                None
                if row["evaluation_case_id"] is None
                else EvaluationCaseId(_exact(row, "evaluation_case_id", UUID))
            ),
            grader_code=(
                None if row["grader_code"] is None else _exact(row, "grader_code", str)
            ),
            slice_key=(
                None if row["slice_key"] is None else _exact(row, "slice_key", str)
            ),
            threshold_operator=(
                None
                if row["threshold_operator"] is None
                else EvaluationResultThresholdOperator(
                    _exact(row, "threshold_operator", str)
                )
            ),
            threshold_value=(
                None
                if row["threshold_value"] is None
                else _exact(row, "threshold_value", Decimal)
            ),
            judge_calibration_id=(
                None
                if row["judge_calibration_id"] is None
                else JudgeCalibrationId(_exact(row, "judge_calibration_id", UUID))
            ),
            judge_route_version_id=(
                None
                if row["judge_route_version_id"] is None
                else ModelRouteVersionId(_exact(row, "judge_route_version_id", UUID))
            ),
            judge_prompt_version_id=(
                None
                if row["judge_prompt_version_id"] is None
                else PromptVersionId(_exact(row, "judge_prompt_version_id", UUID))
            ),
            judge_rubric_artifact_id=(
                None
                if row["judge_rubric_artifact_id"] is None
                else ObjectArtifactId(_exact(row, "judge_rubric_artifact_id", UUID))
            ),
            judge_resolved_model_id=(
                None
                if row["judge_resolved_model_id"] is None
                else ModelDefinitionId(_exact(row, "judge_resolved_model_id", UUID))
            ),
            judge_grader_version=(
                None
                if row["judge_grader_version"] is None
                else _exact(row, "judge_grader_version", str)
            ),
            proportion_numerator_count=(
                None
                if row["proportion_numerator_count"] is None
                else _exact(row, "proportion_numerator_count", int)
            ),
            proportion_denominator_count=(
                None
                if row["proportion_denominator_count"] is None
                else _exact(row, "proportion_denominator_count", int)
            ),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_ai_evaluation_result(value: EvaluationResultState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "suite_code",
            "suite_version",
            "run_id",
            "task_definition_id",
            "model_route_version_id",
            "prompt_version_id",
            "case_key",
            "metric_code",
            "metric_value",
            "passed",
            "details",
            "result_artifact_id",
            "created_at",
            "evaluation_run_id",
            "evaluation_case_id",
            "grader_code",
            "slice_key",
            "threshold_operator",
            "threshold_value",
            "judge_calibration_id",
            "judge_route_version_id",
            "judge_prompt_version_id",
            "judge_rubric_artifact_id",
            "judge_resolved_model_id",
            "judge_grader_version",
            "proportion_numerator_count",
            "proportion_denominator_count",
        ),
        domain_mappers.map_ai_evaluation_result_to_row(value),
    )


def _decode_ai_evaluation_run(row: StorageRow) -> EvaluationRunState:
    columns = (
        "id",
        "display_id",
        "suite_id",
        "dataset_version_id",
        "baseline_evaluation_run_id",
        "prompt_version_id",
        "model_route_version_id",
        "output_schema_version_id",
        "policy_bundle_version_id",
        "code_git_sha",
        "status",
        "run_manifest_artifact_id",
        "started_at",
        "completed_at",
        "created_by_principal_id",
        "lock_version",
        "created_at",
        "updated_at",
        "resolved_model_id",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_ai_evaluation_run_from_row(
            id=EvaluationRunId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            suite_id=EvaluationSuiteId(_exact(row, "suite_id", UUID)),
            dataset_version_id=EvaluationDatasetVersionId(
                _exact(row, "dataset_version_id", UUID)
            ),
            baseline_evaluation_run_id=(
                None
                if row["baseline_evaluation_run_id"] is None
                else EvaluationRunId(_exact(row, "baseline_evaluation_run_id", UUID))
            ),
            prompt_version_id=PromptVersionId(_exact(row, "prompt_version_id", UUID)),
            model_route_version_id=ModelRouteVersionId(
                _exact(row, "model_route_version_id", UUID)
            ),
            output_schema_version_id=OutputSchemaVersionId(
                _exact(row, "output_schema_version_id", UUID)
            ),
            policy_bundle_version_id=PolicyBundleId(
                _exact(row, "policy_bundle_version_id", UUID)
            ),
            code_git_sha=GitCommitDigest(_exact(row, "code_git_sha", str)),
            status=EvaluationRunStatus(_exact(row, "status", str)),
            run_manifest_artifact_id=(
                None
                if row["run_manifest_artifact_id"] is None
                else ObjectArtifactId(_exact(row, "run_manifest_artifact_id", UUID))
            ),
            started_at=(
                None
                if row["started_at"] is None
                else AwareUtcDateTime(_exact(row, "started_at", datetime))
            ),
            completed_at=(
                None
                if row["completed_at"] is None
                else AwareUtcDateTime(_exact(row, "completed_at", datetime))
            ),
            created_by_principal_id=PrincipalId(
                _exact(row, "created_by_principal_id", UUID)
            ),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
            resolved_model_id=ModelDefinitionId(_exact(row, "resolved_model_id", UUID)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_ai_evaluation_run(value: EvaluationRunState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "suite_id",
            "dataset_version_id",
            "baseline_evaluation_run_id",
            "prompt_version_id",
            "model_route_version_id",
            "output_schema_version_id",
            "policy_bundle_version_id",
            "code_git_sha",
            "status",
            "run_manifest_artifact_id",
            "started_at",
            "completed_at",
            "created_by_principal_id",
            "lock_version",
            "created_at",
            "updated_at",
            "resolved_model_id",
        ),
        domain_mappers.map_ai_evaluation_run_to_row(value),
    )


def _decode_ai_evaluation_suite(row: StorageRow) -> EvaluationSuiteState:
    columns = (
        "id",
        "suite_code",
        "version_no",
        "task_definition_id",
        "risk_level",
        "rubric_artifact_id",
        "suite_config",
        "status",
        "approved_by_principal_id",
        "approved_at",
        "lock_version",
        "created_at",
        "updated_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_ai_evaluation_suite_from_row(
            id=EvaluationSuiteId(_exact(row, "id", UUID)),
            suite_code=_exact(row, "suite_code", str),
            version_no=_exact(row, "version_no", int),
            task_definition_id=AiTaskDefinitionId(
                _exact(row, "task_definition_id", UUID)
            ),
            risk_level=EvaluationSuiteRiskLevel(_exact(row, "risk_level", str)),
            rubric_artifact_id=(
                None
                if row["rubric_artifact_id"] is None
                else ObjectArtifactId(_exact(row, "rubric_artifact_id", UUID))
            ),
            suite_config=EvaluationSuiteSuiteConfigJson(
                _json_object(row, "suite_config")
            ),
            status=EvaluationSuiteStatus(_exact(row, "status", str)),
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
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_ai_evaluation_suite(value: EvaluationSuiteState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "suite_code",
            "version_no",
            "task_definition_id",
            "risk_level",
            "rubric_artifact_id",
            "suite_config",
            "status",
            "approved_by_principal_id",
            "approved_at",
            "lock_version",
            "created_at",
            "updated_at",
        ),
        domain_mappers.map_ai_evaluation_suite_to_row(value),
    )


def _decode_ai_human_evaluation(row: StorageRow) -> HumanEvaluation:
    columns = (
        "id",
        "evaluation_case_result_id",
        "reviewer_principal_id",
        "rubric_version",
        "blind_assignment_key",
        "scores",
        "decision",
        "notes_artifact_id",
        "is_adjudication",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_ai_human_evaluation_from_row(
            id=HumanEvaluationId(_exact(row, "id", UUID)),
            evaluation_case_result_id=EvaluationCaseResultId(
                _exact(row, "evaluation_case_result_id", UUID)
            ),
            reviewer_principal_id=PrincipalId(
                _exact(row, "reviewer_principal_id", UUID)
            ),
            rubric_version=_exact(row, "rubric_version", str),
            blind_assignment_key=_exact(row, "blind_assignment_key", str),
            scores=HumanEvaluationScoresJson(_json_object(row, "scores")),
            decision=HumanEvaluationDecision(_exact(row, "decision", str)),
            notes_artifact_id=(
                None
                if row["notes_artifact_id"] is None
                else ObjectArtifactId(_exact(row, "notes_artifact_id", UUID))
            ),
            is_adjudication=_exact(row, "is_adjudication", bool),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_ai_human_evaluation(value: HumanEvaluation) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "evaluation_case_result_id",
            "reviewer_principal_id",
            "rubric_version",
            "blind_assignment_key",
            "scores",
            "decision",
            "notes_artifact_id",
            "is_adjudication",
            "created_at",
        ),
        domain_mappers.map_ai_human_evaluation_to_row(value),
    )


def _decode_ai_judge_calibration(row: StorageRow) -> JudgeCalibrationState:
    columns = (
        "id",
        "display_id",
        "judge_route_version_id",
        "judge_prompt_version_id",
        "dataset_version_id",
        "weighted_kappa",
        "zero_tolerance_false_pass_rate",
        "zero_tolerance_false_fail_rate",
        "case_count",
        "status",
        "report_artifact_id",
        "approved_by_principal_id",
        "approved_at",
        "expires_at",
        "lock_version",
        "created_at",
        "updated_at",
        "evaluated_task_definition_id",
        "resolved_judge_model_id",
        "rubric_artifact_id",
        "rubric_sha256",
        "grader_version",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_ai_judge_calibration_from_row(
            id=JudgeCalibrationId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            judge_route_version_id=ModelRouteVersionId(
                _exact(row, "judge_route_version_id", UUID)
            ),
            judge_prompt_version_id=PromptVersionId(
                _exact(row, "judge_prompt_version_id", UUID)
            ),
            dataset_version_id=EvaluationDatasetVersionId(
                _exact(row, "dataset_version_id", UUID)
            ),
            weighted_kappa=(
                None
                if row["weighted_kappa"] is None
                else _exact(row, "weighted_kappa", Decimal)
            ),
            zero_tolerance_false_pass_rate=(
                None
                if row["zero_tolerance_false_pass_rate"] is None
                else _exact(row, "zero_tolerance_false_pass_rate", Decimal)
            ),
            zero_tolerance_false_fail_rate=(
                None
                if row["zero_tolerance_false_fail_rate"] is None
                else _exact(row, "zero_tolerance_false_fail_rate", Decimal)
            ),
            case_count=_exact(row, "case_count", int),
            status=JudgeCalibrationStatus(_exact(row, "status", str)),
            report_artifact_id=(
                None
                if row["report_artifact_id"] is None
                else ObjectArtifactId(_exact(row, "report_artifact_id", UUID))
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
            expires_at=(
                None
                if row["expires_at"] is None
                else AwareUtcDateTime(_exact(row, "expires_at", datetime))
            ),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
            evaluated_task_definition_id=AiTaskDefinitionId(
                _exact(row, "evaluated_task_definition_id", UUID)
            ),
            resolved_judge_model_id=ModelDefinitionId(
                _exact(row, "resolved_judge_model_id", UUID)
            ),
            rubric_artifact_id=ObjectArtifactId(
                _exact(row, "rubric_artifact_id", UUID)
            ),
            rubric_sha256=Sha256Digest(_exact(row, "rubric_sha256", str)),
            grader_version=_exact(row, "grader_version", str),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_ai_judge_calibration(value: JudgeCalibrationState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "judge_route_version_id",
            "judge_prompt_version_id",
            "dataset_version_id",
            "weighted_kappa",
            "zero_tolerance_false_pass_rate",
            "zero_tolerance_false_fail_rate",
            "case_count",
            "status",
            "report_artifact_id",
            "approved_by_principal_id",
            "approved_at",
            "expires_at",
            "lock_version",
            "created_at",
            "updated_at",
            "evaluated_task_definition_id",
            "resolved_judge_model_id",
            "rubric_artifact_id",
            "rubric_sha256",
            "grader_version",
        ),
        domain_mappers.map_ai_judge_calibration_to_row(value),
    )


def _decode_ai_model_definition(row: StorageRow) -> ModelDefinitionState:
    columns = (
        "id",
        "provider_code",
        "provider_model_id",
        "display_name",
        "capabilities",
        "input_price_per_million",
        "cached_input_price_per_million",
        "output_price_per_million",
        "pricing_currency",
        "pricing_observed_at",
        "status",
        "created_at",
        "context_window_tokens",
        "max_output_tokens",
        "knowledge_cutoff",
        "metadata_observed_at",
        "provider_metadata",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_ai_model_definition_from_row(
            id=ModelDefinitionId(_exact(row, "id", UUID)),
            provider_code=_exact(row, "provider_code", str),
            provider_model_id=_exact(row, "provider_model_id", str),
            display_name=_exact(row, "display_name", str),
            capabilities=ModelDefinitionCapabilitiesJson(
                _json_object(row, "capabilities")
            ),
            input_price_per_million=(
                None
                if row["input_price_per_million"] is None
                else _exact(row, "input_price_per_million", Decimal)
            ),
            cached_input_price_per_million=(
                None
                if row["cached_input_price_per_million"] is None
                else _exact(row, "cached_input_price_per_million", Decimal)
            ),
            output_price_per_million=(
                None
                if row["output_price_per_million"] is None
                else _exact(row, "output_price_per_million", Decimal)
            ),
            pricing_currency=(
                None
                if row["pricing_currency"] is None
                else _exact(row, "pricing_currency", str)
            ),
            pricing_observed_at=(
                None
                if row["pricing_observed_at"] is None
                else AwareUtcDateTime(_exact(row, "pricing_observed_at", datetime))
            ),
            status=ModelDefinitionStatus(_exact(row, "status", str)),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            context_window_tokens=(
                None
                if row["context_window_tokens"] is None
                else _exact(row, "context_window_tokens", int)
            ),
            max_output_tokens=(
                None
                if row["max_output_tokens"] is None
                else _exact(row, "max_output_tokens", int)
            ),
            knowledge_cutoff=(
                None
                if row["knowledge_cutoff"] is None
                else _exact(row, "knowledge_cutoff", date)
            ),
            metadata_observed_at=(
                None
                if row["metadata_observed_at"] is None
                else AwareUtcDateTime(_exact(row, "metadata_observed_at", datetime))
            ),
            provider_metadata=ModelDefinitionProviderMetadataJson(
                _json_object(row, "provider_metadata")
            ),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_ai_model_definition(value: ModelDefinitionState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "provider_code",
            "provider_model_id",
            "display_name",
            "capabilities",
            "input_price_per_million",
            "cached_input_price_per_million",
            "output_price_per_million",
            "pricing_currency",
            "pricing_observed_at",
            "status",
            "created_at",
            "context_window_tokens",
            "max_output_tokens",
            "knowledge_cutoff",
            "metadata_observed_at",
            "provider_metadata",
        ),
        domain_mappers.map_ai_model_definition_to_row(value),
    )


def _decode_ai_model_route_version(row: StorageRow) -> ModelRouteVersionState:
    columns = (
        "id",
        "route_code",
        "version_no",
        "task_definition_id",
        "primary_model_id",
        "fallback_model_id",
        "route_config",
        "monthly_budget_jpy",
        "per_job_budget_jpy",
        "status",
        "effective_from",
        "effective_to",
        "approved_by_principal_id",
        "created_at",
        "lock_version",
        "updated_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_ai_model_route_version_from_row(
            id=ModelRouteVersionId(_exact(row, "id", UUID)),
            route_code=_exact(row, "route_code", str),
            version_no=_exact(row, "version_no", int),
            task_definition_id=AiTaskDefinitionId(
                _exact(row, "task_definition_id", UUID)
            ),
            primary_model_id=ModelDefinitionId(_exact(row, "primary_model_id", UUID)),
            fallback_model_id=(
                None
                if row["fallback_model_id"] is None
                else ModelDefinitionId(_exact(row, "fallback_model_id", UUID))
            ),
            route_config=ModelRouteVersionRouteConfigJson(
                _json_object(row, "route_config")
            ),
            monthly_budget_jpy=(
                None
                if row["monthly_budget_jpy"] is None
                else YenMinor(_exact(row, "monthly_budget_jpy", int))
            ),
            per_job_budget_jpy=YenMinor(_exact(row, "per_job_budget_jpy", int)),
            status=ModelRouteVersionStatus(_exact(row, "status", str)),
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
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_ai_model_route_version(value: ModelRouteVersionState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "route_code",
            "version_no",
            "task_definition_id",
            "primary_model_id",
            "fallback_model_id",
            "route_config",
            "monthly_budget_jpy",
            "per_job_budget_jpy",
            "status",
            "effective_from",
            "effective_to",
            "approved_by_principal_id",
            "created_at",
            "lock_version",
            "updated_at",
        ),
        domain_mappers.map_ai_model_route_version_to_row(value),
    )


def _decode_ai_output_schema_version(
    row: StorageRow,
) -> OutputSchemaVersionState:
    columns = (
        "id",
        "schema_code",
        "version_no",
        "git_path",
        "git_commit_sha",
        "schema_sha256",
        "status",
        "effective_from",
        "effective_to",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_ai_output_schema_version_from_row(
            id=OutputSchemaVersionId(_exact(row, "id", UUID)),
            schema_code=_exact(row, "schema_code", str),
            version_no=_exact(row, "version_no", int),
            git_path=_exact(row, "git_path", str),
            git_commit_sha=_exact(row, "git_commit_sha", str),
            schema_sha256=Sha256Digest(_exact(row, "schema_sha256", str)),
            status=OutputSchemaVersionStatus(_exact(row, "status", str)),
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
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_ai_output_schema_version(
    value: OutputSchemaVersionState,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "schema_code",
            "version_no",
            "git_path",
            "git_commit_sha",
            "schema_sha256",
            "status",
            "effective_from",
            "effective_to",
            "created_at",
        ),
        domain_mappers.map_ai_output_schema_version_to_row(value),
    )


def _decode_ai_prompt_version(row: StorageRow) -> PromptVersionState:
    columns = (
        "id",
        "display_id",
        "task_definition_id",
        "prompt_code",
        "version_no",
        "git_path",
        "git_commit_sha",
        "template_sha256",
        "status",
        "effective_from",
        "effective_to",
        "approved_by_principal_id",
        "approved_at",
        "created_at",
        "locale",
        "compiler_version",
        "input_contract_sha256",
        "policy_test_status",
        "lock_version",
        "updated_at",
        "author_principal_id",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_ai_prompt_version_from_row(
            id=PromptVersionId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            task_definition_id=AiTaskDefinitionId(
                _exact(row, "task_definition_id", UUID)
            ),
            prompt_code=_exact(row, "prompt_code", str),
            version_no=_exact(row, "version_no", int),
            git_path=_exact(row, "git_path", str),
            git_commit_sha=_exact(row, "git_commit_sha", str),
            template_sha256=Sha256Digest(_exact(row, "template_sha256", str)),
            status=PromptVersionStatus(_exact(row, "status", str)),
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
            locale=_exact(row, "locale", str),
            compiler_version=(
                None
                if row["compiler_version"] is None
                else _exact(row, "compiler_version", str)
            ),
            input_contract_sha256=(
                None
                if row["input_contract_sha256"] is None
                else Sha256Digest(_exact(row, "input_contract_sha256", str))
            ),
            policy_test_status=PromptVersionPolicyTestStatus(
                _exact(row, "policy_test_status", str)
            ),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
            author_principal_id=PrincipalId(_exact(row, "author_principal_id", UUID)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_ai_prompt_version(value: PromptVersionState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "task_definition_id",
            "prompt_code",
            "version_no",
            "git_path",
            "git_commit_sha",
            "template_sha256",
            "status",
            "effective_from",
            "effective_to",
            "approved_by_principal_id",
            "approved_at",
            "created_at",
            "locale",
            "compiler_version",
            "input_contract_sha256",
            "policy_test_status",
            "lock_version",
            "updated_at",
            "author_principal_id",
        ),
        domain_mappers.map_ai_prompt_version_to_row(value),
    )


def _decode_ai_release_approval(row: StorageRow) -> ReleaseApproval:
    columns = (
        "id",
        "display_id",
        "release_decision_id",
        "phase",
        "decision_manifest_sha256",
        "primary_approver_principal_id",
        "primary_approver_role",
        "second_approver_principal_id",
        "second_approver_role",
        "approval_artifact_id",
        "approval_sha256",
        "signed_at",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_ai_release_approval_from_row(
            id=ReleaseApprovalId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            release_decision_id=ReleaseDecisionId(
                _exact(row, "release_decision_id", UUID)
            ),
            phase=ReleaseApprovalPhase(_exact(row, "phase", str)),
            decision_manifest_sha256=Sha256Digest(
                _exact(row, "decision_manifest_sha256", str)
            ),
            primary_approver_principal_id=PrincipalId(
                _exact(row, "primary_approver_principal_id", UUID)
            ),
            primary_approver_role=_exact(row, "primary_approver_role", str),
            second_approver_principal_id=PrincipalId(
                _exact(row, "second_approver_principal_id", UUID)
            ),
            second_approver_role=_exact(row, "second_approver_role", str),
            approval_artifact_id=ObjectArtifactId(
                _exact(row, "approval_artifact_id", UUID)
            ),
            approval_sha256=Sha256Digest(_exact(row, "approval_sha256", str)),
            signed_at=AwareUtcDateTime(_exact(row, "signed_at", datetime)),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_ai_release_approval(value: ReleaseApproval) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "release_decision_id",
            "phase",
            "decision_manifest_sha256",
            "primary_approver_principal_id",
            "primary_approver_role",
            "second_approver_principal_id",
            "second_approver_role",
            "approval_artifact_id",
            "approval_sha256",
            "signed_at",
            "created_at",
        ),
        domain_mappers.map_ai_release_approval_to_row(value),
    )


def _decode_ai_release_decision(row: StorageRow) -> ReleaseDecisionState:
    columns = (
        "id",
        "display_id",
        "task_definition_id",
        "prompt_version_id",
        "model_route_version_id",
        "output_schema_version_id",
        "resolved_model_id",
        "policy_bundle_version_id",
        "dataset_version_id",
        "evaluation_run_id",
        "code_git_sha",
        "release_scope",
        "status",
        "maximum_canary_percent",
        "decision_manifest_sha256",
        "rollback_release_decision_id",
        "approved_by_principal_id",
        "second_approver_principal_id",
        "approved_at",
        "revoked_by_principal_id",
        "revoked_at",
        "revocation_reason",
        "lock_version",
        "created_at",
        "updated_at",
        "judge_calibration_id",
        "rollback_strategy",
        "rollback_runbook_artifact_id",
        "rollback_runbook_sha256",
        "canary_monitoring_artifact_id",
        "canary_monitoring_sha256",
        "canary_evidence_artifact_id",
        "canary_evidence_sha256",
        "canary_started_at",
        "canary_completed_at",
        "canary_started_txid",
        "canary_completed_txid",
        "canary_approval_id",
        "active_approval_id",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_ai_release_decision_from_row(
            id=ReleaseDecisionId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            task_definition_id=AiTaskDefinitionId(
                _exact(row, "task_definition_id", UUID)
            ),
            prompt_version_id=PromptVersionId(_exact(row, "prompt_version_id", UUID)),
            model_route_version_id=ModelRouteVersionId(
                _exact(row, "model_route_version_id", UUID)
            ),
            output_schema_version_id=OutputSchemaVersionId(
                _exact(row, "output_schema_version_id", UUID)
            ),
            resolved_model_id=ModelDefinitionId(_exact(row, "resolved_model_id", UUID)),
            policy_bundle_version_id=PolicyBundleId(
                _exact(row, "policy_bundle_version_id", UUID)
            ),
            dataset_version_id=EvaluationDatasetVersionId(
                _exact(row, "dataset_version_id", UUID)
            ),
            evaluation_run_id=EvaluationRunId(_exact(row, "evaluation_run_id", UUID)),
            code_git_sha=GitCommitDigest(_exact(row, "code_git_sha", str)),
            release_scope=ReleaseDecisionReleaseScope(
                _exact(row, "release_scope", str)
            ),
            status=ReleaseDecisionStatus(_exact(row, "status", str)),
            maximum_canary_percent=_exact(row, "maximum_canary_percent", int),
            decision_manifest_sha256=Sha256Digest(
                _exact(row, "decision_manifest_sha256", str)
            ),
            rollback_release_decision_id=(
                None
                if row["rollback_release_decision_id"] is None
                else ReleaseDecisionId(
                    _exact(row, "rollback_release_decision_id", UUID)
                )
            ),
            approved_by_principal_id=(
                None
                if row["approved_by_principal_id"] is None
                else PrincipalId(_exact(row, "approved_by_principal_id", UUID))
            ),
            second_approver_principal_id=(
                None
                if row["second_approver_principal_id"] is None
                else PrincipalId(_exact(row, "second_approver_principal_id", UUID))
            ),
            approved_at=(
                None
                if row["approved_at"] is None
                else AwareUtcDateTime(_exact(row, "approved_at", datetime))
            ),
            revoked_by_principal_id=(
                None
                if row["revoked_by_principal_id"] is None
                else PrincipalId(_exact(row, "revoked_by_principal_id", UUID))
            ),
            revoked_at=(
                None
                if row["revoked_at"] is None
                else AwareUtcDateTime(_exact(row, "revoked_at", datetime))
            ),
            revocation_reason=(
                None
                if row["revocation_reason"] is None
                else _exact(row, "revocation_reason", str)
            ),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
            judge_calibration_id=(
                None
                if row["judge_calibration_id"] is None
                else JudgeCalibrationId(_exact(row, "judge_calibration_id", UUID))
            ),
            rollback_strategy=ReleaseDecisionRollbackStrategy(
                _exact(row, "rollback_strategy", str)
            ),
            rollback_runbook_artifact_id=(
                None
                if row["rollback_runbook_artifact_id"] is None
                else ObjectArtifactId(_exact(row, "rollback_runbook_artifact_id", UUID))
            ),
            rollback_runbook_sha256=(
                None
                if row["rollback_runbook_sha256"] is None
                else Sha256Digest(_exact(row, "rollback_runbook_sha256", str))
            ),
            canary_monitoring_artifact_id=(
                None
                if row["canary_monitoring_artifact_id"] is None
                else ObjectArtifactId(
                    _exact(row, "canary_monitoring_artifact_id", UUID)
                )
            ),
            canary_monitoring_sha256=(
                None
                if row["canary_monitoring_sha256"] is None
                else Sha256Digest(_exact(row, "canary_monitoring_sha256", str))
            ),
            canary_evidence_artifact_id=(
                None
                if row["canary_evidence_artifact_id"] is None
                else ObjectArtifactId(_exact(row, "canary_evidence_artifact_id", UUID))
            ),
            canary_evidence_sha256=(
                None
                if row["canary_evidence_sha256"] is None
                else Sha256Digest(_exact(row, "canary_evidence_sha256", str))
            ),
            canary_started_at=(
                None
                if row["canary_started_at"] is None
                else AwareUtcDateTime(_exact(row, "canary_started_at", datetime))
            ),
            canary_completed_at=(
                None
                if row["canary_completed_at"] is None
                else AwareUtcDateTime(_exact(row, "canary_completed_at", datetime))
            ),
            canary_started_txid=(
                None
                if row["canary_started_txid"] is None
                else _exact(row, "canary_started_txid", int)
            ),
            canary_completed_txid=(
                None
                if row["canary_completed_txid"] is None
                else _exact(row, "canary_completed_txid", int)
            ),
            canary_approval_id=(
                None
                if row["canary_approval_id"] is None
                else ReleaseApprovalId(_exact(row, "canary_approval_id", UUID))
            ),
            active_approval_id=(
                None
                if row["active_approval_id"] is None
                else ReleaseApprovalId(_exact(row, "active_approval_id", UUID))
            ),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_ai_release_decision(value: ReleaseDecisionState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "task_definition_id",
            "prompt_version_id",
            "model_route_version_id",
            "output_schema_version_id",
            "resolved_model_id",
            "policy_bundle_version_id",
            "dataset_version_id",
            "evaluation_run_id",
            "code_git_sha",
            "release_scope",
            "status",
            "maximum_canary_percent",
            "decision_manifest_sha256",
            "rollback_release_decision_id",
            "approved_by_principal_id",
            "second_approver_principal_id",
            "approved_at",
            "revoked_by_principal_id",
            "revoked_at",
            "revocation_reason",
            "lock_version",
            "created_at",
            "updated_at",
            "judge_calibration_id",
            "rollback_strategy",
            "rollback_runbook_artifact_id",
            "rollback_runbook_sha256",
            "canary_monitoring_artifact_id",
            "canary_monitoring_sha256",
            "canary_evidence_artifact_id",
            "canary_evidence_sha256",
            "canary_started_at",
            "canary_completed_at",
            "canary_started_txid",
            "canary_completed_txid",
            "canary_approval_id",
            "active_approval_id",
        ),
        domain_mappers.map_ai_release_decision_to_row(value),
    )


def _decode_ai_task_definition(row: StorageRow) -> AiTaskDefinitionState:
    columns = (
        "id",
        "task_code",
        "name",
        "description",
        "risk_level",
        "output_schema_code",
        "default_max_tokens",
        "default_max_cost_jpy",
        "human_review_required",
        "status",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_ai_task_definition_from_row(
            id=AiTaskDefinitionId(_exact(row, "id", UUID)),
            task_code=_exact(row, "task_code", str),
            name=_exact(row, "name", str),
            description=_exact(row, "description", str),
            risk_level=AiTaskDefinitionRiskLevel(_exact(row, "risk_level", str)),
            output_schema_code=_exact(row, "output_schema_code", str),
            default_max_tokens=_exact(row, "default_max_tokens", int),
            default_max_cost_jpy=YenMinor(_exact(row, "default_max_cost_jpy", int)),
            human_review_required=_exact(row, "human_review_required", bool),
            status=AiTaskDefinitionStatus(_exact(row, "status", str)),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_ai_task_definition(value: AiTaskDefinitionState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "task_code",
            "name",
            "description",
            "risk_level",
            "output_schema_code",
            "default_max_tokens",
            "default_max_cost_jpy",
            "human_review_required",
            "status",
            "created_at",
        ),
        domain_mappers.map_ai_task_definition_to_row(value),
    )


def _decode_ai_usage_cost(row: StorageRow) -> UsageCost:
    columns = (
        "id",
        "ai_attempt_id",
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "total_tokens",
        "provider_cost_amount",
        "provider_currency",
        "fx_rate_to_jpy",
        "cost_jpy",
        "pricing_version",
        "observed_at",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_ai_usage_cost_from_row(
            id=UsageCostId(_exact(row, "id", UUID)),
            ai_attempt_id=AiAttemptId(_exact(row, "ai_attempt_id", UUID)),
            input_tokens=_exact(row, "input_tokens", int),
            cached_input_tokens=_exact(row, "cached_input_tokens", int),
            output_tokens=_exact(row, "output_tokens", int),
            total_tokens=_exact(row, "total_tokens", int),
            provider_cost_amount=_exact(row, "provider_cost_amount", Decimal),
            provider_currency=_exact(row, "provider_currency", str),
            fx_rate_to_jpy=_exact(row, "fx_rate_to_jpy", Decimal),
            cost_jpy=YenMinor(_exact(row, "cost_jpy", int)),
            pricing_version=_exact(row, "pricing_version", str),
            observed_at=AwareUtcDateTime(_exact(row, "observed_at", datetime)),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_ai_usage_cost(value: UsageCost) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "ai_attempt_id",
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "total_tokens",
            "provider_cost_amount",
            "provider_currency",
            "fx_rate_to_jpy",
            "cost_jpy",
            "pricing_version",
            "observed_at",
            "created_at",
        ),
        domain_mappers.map_ai_usage_cost_to_row(value),
    )


# Aggregate-specific Session/Table-bound classes are the only AI DML surface.


@guard_repository_class
class SqlAlchemyAiTaskDefinitionRepository:
    __slots__ = ("_session", "_task")

    _EDGES = frozenset(
        {
            (AiTaskDefinitionStatus.ACTIVE, AiTaskDefinitionStatus.PAUSED),
            (AiTaskDefinitionStatus.ACTIVE, AiTaskDefinitionStatus.RETIRED),
            (AiTaskDefinitionStatus.PAUSED, AiTaskDefinitionStatus.ACTIVE),
            (AiTaskDefinitionStatus.PAUSED, AiTaskDefinitionStatus.RETIRED),
        }
    )

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._task = _table("ai.task_definition")

    def get(self, task_id: AiTaskDefinitionId) -> AiTaskDefinition | None:
        if type(task_id) is not AiTaskDefinitionId:
            raise ValueError("INVALID_AI_TASK_ID") from None
        row = _execute_one(
            self._session,
            select(self._task).where(self._task.c.id == task_id.value),
        )
        return (
            None if row is None else AiTaskDefinition(_decode_ai_task_definition(row))
        )

    def get_by_code(self, task_code: str) -> AiTaskDefinition | None:
        if type(task_code) is not str or not task_code:
            raise ValueError("INVALID_AI_TASK_CODE") from None
        row = _execute_one(
            self._session,
            select(self._task).where(self._task.c.task_code == task_code),
        )
        return (
            None if row is None else AiTaskDefinition(_decode_ai_task_definition(row))
        )

    def add(self, task: AiTaskDefinition) -> None:
        if type(task) is not AiTaskDefinition:
            raise ValueError("INVALID_AI_TASK") from None
        _execute(
            self._session,
            insert(self._task).values(**_encode_ai_task_definition(task.state)),
        )

    def transition(
        self,
        task_id: AiTaskDefinitionId,
        transition: AiTaskDefinition,
        expected_status: AiTaskDefinitionStatus,
    ) -> AiTaskDefinition:
        if (
            type(task_id) is not AiTaskDefinitionId
            or type(transition) is not AiTaskDefinition
            or type(expected_status) is not AiTaskDefinitionStatus
            or transition.state.id != task_id
            or (expected_status, transition.state.status) not in self._EDGES
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_row = _execute_one(
            self._session,
            select(self._task).where(self._task.c.id == task_id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_ai_task_definition(current_row)
        if current.status is not expected_status:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_values = _encode_ai_task_definition(current)
        target_values = _encode_ai_task_definition(transition.state)
        _require_same(
            current_values,
            target_values,
            tuple(name for name in current_values if name != "status"),
            PersistenceErrorCode.STATE_CONFLICT,
        )
        row = _execute_one(
            self._session,
            update(self._task)
            .where(
                self._task.c.id == task_id.value,
                self._task.c.status == expected_status.value,
            )
            .values(status=transition.state.status.value)
            .returning(self._task),
        )
        if row is None:
            _state_zero(self._session, self._task, task_id.value, expected_status)
        return AiTaskDefinition(_decode_ai_task_definition(row))


@guard_repository_class
class SqlAlchemyOutputSchemaVersionRepository:
    __slots__ = ("_schema", "_session")

    _EDGES = frozenset(
        {
            (OutputSchemaVersionStatus.DRAFT, OutputSchemaVersionStatus.ACTIVE),
            (OutputSchemaVersionStatus.DRAFT, OutputSchemaVersionStatus.RETIRED),
            (OutputSchemaVersionStatus.ACTIVE, OutputSchemaVersionStatus.RETIRED),
        }
    )

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._schema = _table("ai.output_schema_version")

    def get(self, version_id: OutputSchemaVersionId) -> OutputSchemaVersion | None:
        if type(version_id) is not OutputSchemaVersionId:
            raise ValueError("INVALID_OUTPUT_SCHEMA_VERSION_ID") from None
        row = _execute_one(
            self._session,
            select(self._schema).where(self._schema.c.id == version_id.value),
        )
        return (
            None
            if row is None
            else OutputSchemaVersion(_decode_ai_output_schema_version(row))
        )

    def get_active(self, schema_code: str) -> OutputSchemaVersion | None:
        if type(schema_code) is not str or not schema_code:
            raise ValueError("INVALID_OUTPUT_SCHEMA_CODE") from None
        row = _execute_one(
            self._session,
            select(self._schema)
            .where(
                self._schema.c.schema_code == schema_code,
                self._schema.c.status == OutputSchemaVersionStatus.ACTIVE.value,
            )
            .order_by(self._schema.c.version_no.desc(), self._schema.c.id.desc())
            .limit(1),
        )
        return (
            None
            if row is None
            else OutputSchemaVersion(_decode_ai_output_schema_version(row))
        )

    def append_version(
        self,
        version: OutputSchemaVersion,
        expected_latest_version: int | None,
    ) -> AggregateVersion:
        if type(version) is not OutputSchemaVersion:
            raise ValueError("INVALID_OUTPUT_SCHEMA_VERSION") from None
        observed = _latest_version(
            self._session,
            self._schema,
            (self._schema.c.schema_code == version.state.schema_code,),
        )
        persisted = _validate_append_version(
            version.state.version_no, expected_latest_version, observed
        )
        _execute(
            self._session,
            insert(self._schema).values(
                **_encode_ai_output_schema_version(version.state)
            ),
        )
        return persisted

    def transition(
        self,
        version_id: OutputSchemaVersionId,
        transition: OutputSchemaVersion,
        expected_status: OutputSchemaVersionStatus,
    ) -> OutputSchemaVersion:
        target_status = (
            transition.state.status if type(transition) is OutputSchemaVersion else None
        )
        if (
            type(version_id) is not OutputSchemaVersionId
            or type(transition) is not OutputSchemaVersion
            or type(expected_status) is not OutputSchemaVersionStatus
            or transition.state.id != version_id
            or (expected_status, target_status) not in self._EDGES
            or (
                target_status is OutputSchemaVersionStatus.RETIRED
                and transition.state.effective_to is None
            )
            or (
                target_status is OutputSchemaVersionStatus.ACTIVE
                and transition.state.effective_to is not None
            )
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        target_status = transition.state.status
        current_row = _execute_one(
            self._session,
            select(self._schema).where(self._schema.c.id == version_id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_ai_output_schema_version(current_row)
        if current.status is not expected_status:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        at = transaction_timestamp(self._session)
        if target_status is OutputSchemaVersionStatus.ACTIVE:
            effective_from = current.effective_from or at
            if transition.state.effective_from != effective_from:
                _fail(PersistenceErrorCode.STATE_CONFLICT)
        else:
            if (
                transition.state.effective_from != current.effective_from
                or transition.state.effective_to != at
            ):
                _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_values = _encode_ai_output_schema_version(current)
        target_values = _encode_ai_output_schema_version(transition.state)
        immutable = tuple(
            name
            for name in current_values
            if name not in {"status", "effective_from", "effective_to"}
        )
        _require_same(
            current_values,
            target_values,
            immutable,
            PersistenceErrorCode.STATE_CONFLICT,
        )
        predicate = [
            self._schema.c.id == version_id.value,
            self._schema.c.status == expected_status.value,
        ]
        if (
            expected_status is OutputSchemaVersionStatus.DRAFT
            and target_status is OutputSchemaVersionStatus.ACTIVE
        ):
            predicate.append(self._schema.c.effective_to.is_(None))
        row = _execute_one(
            self._session,
            update(self._schema)
            .where(*predicate)
            .values(
                **(
                    {
                        "status": target_status.value,
                        "effective_from": effective_from.value,
                        "effective_to": None,
                    }
                    if target_status is OutputSchemaVersionStatus.ACTIVE
                    else {
                        "status": target_status.value,
                        "effective_to": at.value,
                    }
                )
            )
            .returning(self._schema),
        )
        if row is None:
            _state_zero(self._session, self._schema, version_id.value, expected_status)
        return OutputSchemaVersion(_decode_ai_output_schema_version(row))


@guard_repository_class
class SqlAlchemyModelDefinitionRepository:
    __slots__ = ("_model", "_session")

    _EDGES = frozenset(
        {
            (source, target)
            for source, targets in {
                ModelDefinitionStatus.EVALUATION: (
                    ModelDefinitionStatus.ACTIVE,
                    ModelDefinitionStatus.PAUSED,
                    ModelDefinitionStatus.BLOCKED,
                    ModelDefinitionStatus.RETIRED,
                ),
                ModelDefinitionStatus.ACTIVE: (
                    ModelDefinitionStatus.PAUSED,
                    ModelDefinitionStatus.BLOCKED,
                    ModelDefinitionStatus.RETIRED,
                ),
                ModelDefinitionStatus.PAUSED: (
                    ModelDefinitionStatus.ACTIVE,
                    ModelDefinitionStatus.BLOCKED,
                    ModelDefinitionStatus.RETIRED,
                ),
                ModelDefinitionStatus.BLOCKED: (
                    ModelDefinitionStatus.EVALUATION,
                    ModelDefinitionStatus.RETIRED,
                ),
            }.items()
            for target in targets
        }
    )

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._model = _table("ai.model_definition")

    def get(self, model_id: ModelDefinitionId) -> ModelDefinition | None:
        if type(model_id) is not ModelDefinitionId:
            raise ValueError("INVALID_MODEL_DEFINITION_ID") from None
        row = _execute_one(
            self._session,
            select(self._model).where(self._model.c.id == model_id.value),
        )
        return (
            None if row is None else ModelDefinition(_decode_ai_model_definition(row))
        )

    def add(self, model: ModelDefinition) -> None:
        if type(model) is not ModelDefinition:
            raise ValueError("INVALID_MODEL_DEFINITION") from None
        _execute(
            self._session,
            insert(self._model).values(**_encode_ai_model_definition(model.state)),
        )

    def transition(
        self,
        model_id: ModelDefinitionId,
        transition: ModelDefinition,
        expected_status: ModelDefinitionStatus,
    ) -> ModelDefinition:
        if (
            type(model_id) is not ModelDefinitionId
            or type(transition) is not ModelDefinition
            or type(expected_status) is not ModelDefinitionStatus
            or transition.state.id != model_id
            or (expected_status, transition.state.status) not in self._EDGES
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_row = _execute_one(
            self._session,
            select(self._model).where(self._model.c.id == model_id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_ai_model_definition(current_row)
        if current.status is not expected_status:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_values = _encode_ai_model_definition(current)
        target_values = _encode_ai_model_definition(transition.state)
        _require_same(
            current_values,
            target_values,
            tuple(name for name in current_values if name != "status"),
            PersistenceErrorCode.STATE_CONFLICT,
        )
        row = _execute_one(
            self._session,
            update(self._model)
            .where(
                self._model.c.id == model_id.value,
                self._model.c.status == expected_status.value,
            )
            .values(status=transition.state.status.value)
            .returning(self._model),
        )
        if row is None:
            _state_zero(self._session, self._model, model_id.value, expected_status)
        return ModelDefinition(_decode_ai_model_definition(row))


@guard_repository_class
class SqlAlchemyModelRouteVersionRepository:
    __slots__ = ("_route", "_session")

    _EDGES = frozenset(
        {
            (ModelRouteVersionStatus.DRAFT, ModelRouteVersionStatus.EVALUATING),
            (ModelRouteVersionStatus.DRAFT, ModelRouteVersionStatus.RETIRED),
            (ModelRouteVersionStatus.EVALUATING, ModelRouteVersionStatus.CERTIFIED),
            (ModelRouteVersionStatus.EVALUATING, ModelRouteVersionStatus.RETIRED),
            (ModelRouteVersionStatus.CERTIFIED, ModelRouteVersionStatus.CANARY),
            (ModelRouteVersionStatus.CERTIFIED, ModelRouteVersionStatus.ACTIVE),
            (ModelRouteVersionStatus.CERTIFIED, ModelRouteVersionStatus.RETIRED),
            (ModelRouteVersionStatus.CANARY, ModelRouteVersionStatus.ACTIVE),
            (ModelRouteVersionStatus.CANARY, ModelRouteVersionStatus.PAUSED),
            (ModelRouteVersionStatus.CANARY, ModelRouteVersionStatus.ROLLED_BACK),
            (ModelRouteVersionStatus.CANARY, ModelRouteVersionStatus.RETIRED),
            (ModelRouteVersionStatus.ACTIVE, ModelRouteVersionStatus.PAUSED),
            (ModelRouteVersionStatus.ACTIVE, ModelRouteVersionStatus.ROLLED_BACK),
            (ModelRouteVersionStatus.ACTIVE, ModelRouteVersionStatus.RETIRED),
            (ModelRouteVersionStatus.PAUSED, ModelRouteVersionStatus.ACTIVE),
            (ModelRouteVersionStatus.PAUSED, ModelRouteVersionStatus.ROLLED_BACK),
            (ModelRouteVersionStatus.PAUSED, ModelRouteVersionStatus.RETIRED),
            (ModelRouteVersionStatus.ROLLED_BACK, ModelRouteVersionStatus.RETIRED),
        }
    )

    _IMMUTABLE = (
        "id",
        "route_code",
        "version_no",
        "task_definition_id",
        "primary_model_id",
        "fallback_model_id",
        "route_config",
        "monthly_budget_jpy",
        "per_job_budget_jpy",
        "created_at",
    )

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._route = _table("ai.model_route_version")

    def get(self, version_id: ModelRouteVersionId) -> ModelRouteVersion | None:
        if type(version_id) is not ModelRouteVersionId:
            raise ValueError("INVALID_MODEL_ROUTE_VERSION_ID") from None
        row = _execute_one(
            self._session,
            select(self._route).where(self._route.c.id == version_id.value),
        )
        return (
            None
            if row is None
            else ModelRouteVersion(_decode_ai_model_route_version(row))
        )

    def get_active(self, route_code: str) -> ModelRouteVersion | None:
        if type(route_code) is not str or not route_code:
            raise ValueError("INVALID_MODEL_ROUTE_CODE") from None
        row = _execute_one(
            self._session,
            select(self._route)
            .where(
                self._route.c.route_code == route_code,
                self._route.c.status == ModelRouteVersionStatus.ACTIVE.value,
            )
            .order_by(self._route.c.version_no.desc(), self._route.c.id.desc())
            .limit(1),
        )
        return (
            None
            if row is None
            else ModelRouteVersion(_decode_ai_model_route_version(row))
        )

    def append_version(
        self,
        version: ModelRouteVersion,
        expected_latest_version: int | None,
    ) -> AggregateVersion:
        if (
            type(version) is not ModelRouteVersion
            or version.state.lock_version.value != 0
        ):
            raise ValueError("INVALID_MODEL_ROUTE_VERSION") from None
        observed = _latest_version(
            self._session,
            self._route,
            (self._route.c.route_code == version.state.route_code,),
        )
        _validate_append_version(
            version.state.version_no, expected_latest_version, observed
        )
        _execute(
            self._session,
            insert(self._route).values(**_encode_ai_model_route_version(version.state)),
        )
        return AggregateVersion(0)

    def transition(
        self,
        version_id: ModelRouteVersionId,
        transition: ModelRouteVersion,
        expected_version: AggregateVersion,
    ) -> ModelRouteVersion:
        if (
            type(version_id) is not ModelRouteVersionId
            or type(transition) is not ModelRouteVersion
            or type(expected_version) is not AggregateVersion
            or transition.state.id != version_id
        ):
            raise ValueError("INVALID_MODEL_ROUTE_TRANSITION") from None
        current_row = _execute_one(
            self._session,
            select(self._route).where(self._route.c.id == version_id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_ai_model_route_version(current_row)
        if current.lock_version != expected_version:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        if (current.status, transition.state.status) not in self._EDGES:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_values = _encode_ai_model_route_version(current)
        target_values = _encode_ai_model_route_version(transition.state)
        _require_same(
            current_values,
            target_values,
            self._IMMUTABLE,
            PersistenceErrorCode.STATE_CONFLICT,
        )
        row = _cas_row(
            self._session,
            self._route,
            version_id.value,
            expected_version,
            target_values,
        )
        return ModelRouteVersion(_decode_ai_model_route_version(row))


@guard_repository_class
class SqlAlchemyPromptVersionRepository:
    __slots__ = ("_prompt", "_session")

    _EDGES = frozenset(
        {
            (PromptVersionStatus.DRAFT, PromptVersionStatus.IN_REVIEW),
            (PromptVersionStatus.DRAFT, PromptVersionStatus.RETIRED),
            (PromptVersionStatus.IN_REVIEW, PromptVersionStatus.DRAFT),
            (PromptVersionStatus.IN_REVIEW, PromptVersionStatus.EVALUATING),
            (PromptVersionStatus.IN_REVIEW, PromptVersionStatus.RETIRED),
            (PromptVersionStatus.EVALUATING, PromptVersionStatus.IN_REVIEW),
            (PromptVersionStatus.EVALUATING, PromptVersionStatus.CERTIFIED),
            (PromptVersionStatus.EVALUATING, PromptVersionStatus.RETIRED),
            (PromptVersionStatus.CERTIFIED, PromptVersionStatus.ACTIVE),
            (PromptVersionStatus.CERTIFIED, PromptVersionStatus.SUSPENDED),
            (PromptVersionStatus.CERTIFIED, PromptVersionStatus.RETIRED),
            (PromptVersionStatus.ACTIVE, PromptVersionStatus.SUSPENDED),
            (PromptVersionStatus.ACTIVE, PromptVersionStatus.RETIRED),
            (PromptVersionStatus.SUSPENDED, PromptVersionStatus.ACTIVE),
            (PromptVersionStatus.SUSPENDED, PromptVersionStatus.RETIRED),
        }
    )

    _IMMUTABLE = (
        "id",
        "display_id",
        "task_definition_id",
        "prompt_code",
        "version_no",
        "git_path",
        "git_commit_sha",
        "template_sha256",
        "created_at",
        "locale",
        "compiler_version",
        "input_contract_sha256",
        "author_principal_id",
    )

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._prompt = _table("ai.prompt_version")

    def get(self, version_id: PromptVersionId) -> PromptVersion | None:
        if type(version_id) is not PromptVersionId:
            raise ValueError("INVALID_PROMPT_VERSION_ID") from None
        row = _execute_one(
            self._session,
            select(self._prompt).where(self._prompt.c.id == version_id.value),
        )
        return None if row is None else PromptVersion(_decode_ai_prompt_version(row))

    def get_active(self, prompt_code: str) -> PromptVersion | None:
        if type(prompt_code) is not str or not prompt_code:
            raise ValueError("INVALID_PROMPT_CODE") from None
        row = _execute_one(
            self._session,
            select(self._prompt)
            .where(
                self._prompt.c.prompt_code == prompt_code,
                self._prompt.c.status == PromptVersionStatus.ACTIVE.value,
            )
            .order_by(self._prompt.c.version_no.desc(), self._prompt.c.id.desc())
            .limit(1),
        )
        return None if row is None else PromptVersion(_decode_ai_prompt_version(row))

    def append_version(
        self,
        version: PromptVersion,
        expected_latest_version: int | None,
    ) -> AggregateVersion:
        if type(version) is not PromptVersion or version.state.lock_version.value != 0:
            raise ValueError("INVALID_PROMPT_VERSION") from None
        observed = _latest_version(
            self._session,
            self._prompt,
            (self._prompt.c.prompt_code == version.state.prompt_code,),
        )
        _validate_append_version(
            version.state.version_no, expected_latest_version, observed
        )
        _execute(
            self._session,
            insert(self._prompt).values(**_encode_ai_prompt_version(version.state)),
        )
        return AggregateVersion(0)

    def transition(
        self,
        version_id: PromptVersionId,
        transition: PromptVersion,
        expected_version: AggregateVersion,
    ) -> PromptVersion:
        if (
            type(version_id) is not PromptVersionId
            or type(transition) is not PromptVersion
            or type(expected_version) is not AggregateVersion
            or transition.state.id != version_id
        ):
            raise ValueError("INVALID_PROMPT_TRANSITION") from None
        current_row = _execute_one(
            self._session,
            select(self._prompt).where(self._prompt.c.id == version_id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_ai_prompt_version(current_row)
        if current.lock_version != expected_version:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        if (current.status, transition.state.status) not in self._EDGES:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_values = _encode_ai_prompt_version(current)
        target_values = _encode_ai_prompt_version(transition.state)
        _require_same(
            current_values,
            target_values,
            self._IMMUTABLE,
            PersistenceErrorCode.STATE_CONFLICT,
        )
        row = _cas_row(
            self._session,
            self._prompt,
            version_id.value,
            expected_version,
            target_values,
        )
        return PromptVersion(_decode_ai_prompt_version(row))


@guard_repository_class
class SqlAlchemyAiJobRepository:
    __slots__ = (
        "_attempt",
        "_case_result",
        "_job",
        "_session",
        "_task",
        "_usage",
    )

    _EDGES = frozenset(
        {
            (AiJobStatus.REQUESTED, AiJobStatus.VALIDATING_INPUT),
            (AiJobStatus.REQUESTED, AiJobStatus.CANCELLED),
            (AiJobStatus.REQUESTED, AiJobStatus.EXPIRED),
            (AiJobStatus.VALIDATING_INPUT, AiJobStatus.QUEUED),
            (AiJobStatus.VALIDATING_INPUT, AiJobStatus.FAILED_TERMINAL),
            (AiJobStatus.VALIDATING_INPUT, AiJobStatus.QUARANTINED),
            (AiJobStatus.VALIDATING_INPUT, AiJobStatus.CANCELLED),
            (AiJobStatus.VALIDATING_INPUT, AiJobStatus.EXPIRED),
            (AiJobStatus.QUEUED, AiJobStatus.RUNNING),
            (AiJobStatus.QUEUED, AiJobStatus.FAILED_RETRYABLE),
            (AiJobStatus.QUEUED, AiJobStatus.CANCELLED),
            (AiJobStatus.QUEUED, AiJobStatus.EXPIRED),
            (AiJobStatus.RUNNING, AiJobStatus.VALIDATING_OUTPUT),
            (AiJobStatus.RUNNING, AiJobStatus.FAILED_RETRYABLE),
            (AiJobStatus.RUNNING, AiJobStatus.FAILED_TERMINAL),
            (AiJobStatus.RUNNING, AiJobStatus.QUARANTINED),
            (AiJobStatus.RUNNING, AiJobStatus.CANCELLED),
            (AiJobStatus.RUNNING, AiJobStatus.EXPIRED),
            (AiJobStatus.VALIDATING_OUTPUT, AiJobStatus.AWAITING_HUMAN),
            (AiJobStatus.VALIDATING_OUTPUT, AiJobStatus.SUCCEEDED),
            (AiJobStatus.VALIDATING_OUTPUT, AiJobStatus.FAILED_RETRYABLE),
            (AiJobStatus.VALIDATING_OUTPUT, AiJobStatus.FAILED_TERMINAL),
            (AiJobStatus.VALIDATING_OUTPUT, AiJobStatus.QUARANTINED),
            (AiJobStatus.AWAITING_HUMAN, AiJobStatus.SUCCEEDED),
            (AiJobStatus.AWAITING_HUMAN, AiJobStatus.FAILED_TERMINAL),
            (AiJobStatus.AWAITING_HUMAN, AiJobStatus.QUARANTINED),
            (AiJobStatus.AWAITING_HUMAN, AiJobStatus.CANCELLED),
            (AiJobStatus.AWAITING_HUMAN, AiJobStatus.EXPIRED),
            (AiJobStatus.FAILED_RETRYABLE, AiJobStatus.RETRY_SCHEDULED),
            (AiJobStatus.FAILED_RETRYABLE, AiJobStatus.FAILED_TERMINAL),
            (AiJobStatus.RETRY_SCHEDULED, AiJobStatus.QUEUED),
            (AiJobStatus.RETRY_SCHEDULED, AiJobStatus.CANCELLED),
            (AiJobStatus.RETRY_SCHEDULED, AiJobStatus.EXPIRED),
        }
    )

    _IMMUTABLE = (
        "id",
        "display_id",
        "ops_job_id",
        "task_definition_id",
        "article_plan_id",
        "article_version_id",
        "source_packet_version_id",
        "prompt_version_id",
        "output_schema_version_id",
        "model_route_version_id",
        "max_cost_jpy",
        "created_at",
        "request_config",
    )

    _ATTEMPT_EDGES = frozenset(
        {
            (AiAttemptStatus.RUNNING, AiAttemptStatus.SUCCEEDED),
            (AiAttemptStatus.RUNNING, AiAttemptStatus.FAILED),
            (AiAttemptStatus.RUNNING, AiAttemptStatus.REFUSED),
            (AiAttemptStatus.RUNNING, AiAttemptStatus.TIMED_OUT),
            (AiAttemptStatus.RUNNING, AiAttemptStatus.CANCELLED),
        }
    )

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._job = _table("ai.ai_job")
        self._attempt = _table("ai.ai_attempt")
        self._usage = _table("ai.usage_cost")
        self._case_result = _table("ai.evaluation_case_result")
        self._task = _table("ai.task_definition")

    def get(self, job_id: AiJobId) -> AiJob | None:
        if type(job_id) is not AiJobId:
            raise ValueError("INVALID_AI_JOB_ID") from None
        row = _execute_one(
            self._session,
            select(self._job).where(self._job.c.id == job_id.value),
        )
        if row is None:
            return None
        attempt_rows = _execute_many(
            self._session,
            select(self._attempt)
            .where(self._attempt.c.ai_job_id == job_id.value)
            .order_by(self._attempt.c.id),
        )
        attempts = tuple(_decode_ai_ai_attempt(item) for item in attempt_rows)
        attempt_ids = tuple(item.id.value for item in attempts)
        usage: tuple[UsageCost, ...] = ()
        if attempt_ids:
            usage = tuple(
                _decode_ai_usage_cost(item)
                for item in _execute_many(
                    self._session,
                    select(self._usage)
                    .where(self._usage.c.ai_attempt_id.in_(attempt_ids))
                    .order_by(self._usage.c.id),
                )
            )
        job = AiJob(
            state=_decode_ai_ai_job(row),
            ai_attempt_rows=attempts,
            usage_cost_rows=usage,
        )
        register_pending_events(
            self._session,
            aggregate_type="ai.ai_job",
            aggregate_id=job.state.id.value,
            buffer=job._events,
        )
        return job

    def add(self, job: AiJob) -> AggregateVersion:
        attempt_ids = (
            frozenset(item.id for item in job.ai_attempt_rows)
            if type(job) is AiJob
            else frozenset()
        )
        if (
            type(job) is not AiJob
            or job.state.lock_version.value != 0
            or any(item.ai_job_id != job.state.id for item in job.ai_attempt_rows)
            or any(
                item.ai_attempt_id not in attempt_ids for item in job.usage_cost_rows
            )
        ):
            raise ValueError("INVALID_AI_JOB") from None
        pending = job.pending_events()
        if not pending:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        if (
            len(pending) != 1
            or type(pending[0]) is not AiJobRequested
            or pending[0].aggregate_id != job.state.id
            or job.state.status is not AiJobStatus.REQUESTED
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        register_pending_events(
            self._session,
            aggregate_type="ai.ai_job",
            aggregate_id=job.state.id.value,
            buffer=job._events,
        )
        _execute(
            self._session,
            insert(self._job).values(**_encode_ai_ai_job(job.state)),
        )
        for attempt in job.ai_attempt_rows:
            _execute(
                self._session,
                insert(self._attempt).values(**_encode_ai_ai_attempt(attempt)),
            )
        for usage in job.usage_cost_rows:
            _execute(
                self._session,
                insert(self._usage).values(**_encode_ai_usage_cost(usage)),
            )
        persisted = AggregateVersion(0)
        stage_registered_events(
            self._session,
            aggregate_type="ai.ai_job",
            aggregate_id=job.state.id.value,
            owning_method="AiJobRepository.add",
            persisted_version=persisted,
            expected_event_type="jp.raos.ai.job_requested.v1",
        )
        return persisted

    def transition(
        self,
        job_id: AiJobId,
        transition: AiJob,
        expected_version: AggregateVersion,
    ) -> AiJob:
        if (
            type(job_id) is not AiJobId
            or type(transition) is not AiJob
            or type(expected_version) is not AggregateVersion
            or transition.state.id != job_id
            or transition.ai_attempt_rows
            or transition.usage_cost_rows
        ):
            raise ValueError("INVALID_AI_JOB_TRANSITION") from None
        pending = transition.pending_events()
        emits = transition.state.status in {
            AiJobStatus.SUCCEEDED,
            AiJobStatus.FAILED_TERMINAL,
        }
        if emits and not pending:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        if pending:
            if len(pending) != 1 or pending[0].aggregate_id != job_id:
                _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
            event_type = type(pending[0])
            if (
                (
                    transition.state.status is AiJobStatus.SUCCEEDED
                    and event_type not in {AiJobSucceeded, AiPolicyAssistCompleted}
                )
                or (
                    transition.state.status is AiJobStatus.FAILED_TERMINAL
                    and event_type is not AiJobFailed
                )
                or transition.state.status
                not in {
                    AiJobStatus.SUCCEEDED,
                    AiJobStatus.FAILED_TERMINAL,
                }
            ):
                _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        register_pending_events(
            self._session,
            aggregate_type="ai.ai_job",
            aggregate_id=job_id.value,
            buffer=transition._events,
        )
        current_row = _execute_one(
            self._session,
            select(self._job).where(self._job.c.id == job_id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_ai_ai_job(current_row)
        if current.lock_version != expected_version:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        if (current.status, transition.state.status) not in self._EDGES:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_values = _encode_ai_ai_job(current)
        target_values = _encode_ai_ai_job(transition.state)
        _require_same(
            current_values,
            target_values,
            self._IMMUTABLE,
            PersistenceErrorCode.STATE_CONFLICT,
        )
        policy_assist_success = False
        if transition.state.status is AiJobStatus.SUCCEEDED:
            task_row = _execute_one(
                self._session,
                select(self._task.c.task_code).where(
                    self._task.c.id == current.task_definition_id.value
                ),
            )
            if task_row is None:
                _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
            _shape(task_row, ("task_code",))
            task_code = _exact(task_row, "task_code", str)
            if task_code == "ai.policy_assist.v1":
                policy_assist_success = True
                if type(pending[0]) is not AiPolicyAssistCompleted:
                    _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
            else:
                if (
                    type(pending[0]) is not AiJobSucceeded
                    or pending[0].data["task_code"] != task_code
                ):
                    _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        row = _cas_row(
            self._session,
            self._job,
            job_id.value,
            expected_version,
            target_values,
        )
        state = _decode_ai_ai_job(row)
        if transition.state.status is AiJobStatus.SUCCEEDED:
            if policy_assist_success:
                stage_registered_events(
                    self._session,
                    aggregate_type="ai.ai_job",
                    aggregate_id=job_id.value,
                    owning_method="AiJobRepository.transition",
                    persisted_version=state.lock_version,
                    expected_event_type="jp.raos.ai.policy_assist_completed.v1",
                )
            else:
                stage_registered_events(
                    self._session,
                    aggregate_type="ai.ai_job",
                    aggregate_id=job_id.value,
                    owning_method="AiJobRepository.transition",
                    persisted_version=state.lock_version,
                    expected_event_type="jp.raos.ai.job_succeeded.v1",
                )
        elif transition.state.status is AiJobStatus.FAILED_TERMINAL:
            stage_registered_events(
                self._session,
                aggregate_type="ai.ai_job",
                aggregate_id=job_id.value,
                owning_method="AiJobRepository.transition",
                persisted_version=state.lock_version,
                expected_event_type="jp.raos.ai.job_failed.v1",
            )
        return AiJob(state=state)

    def add_attempt(
        self,
        job_id: AiJobId,
        attempt: AiAttempt,
        expected_version: AggregateVersion,
    ) -> AggregateVersion:
        if (
            type(job_id) is not AiJobId
            or type(attempt) is not AiAttempt
            or type(expected_version) is not AggregateVersion
            or attempt.state.ai_job_id != job_id
            or attempt.evaluation_case_result_rows
            or attempt.usage_cost_rows
        ):
            raise ValueError("INVALID_AI_ATTEMPT_APPEND") from None
        persisted = _cas_bump(self._session, self._job, job_id.value, expected_version)
        _execute(
            self._session,
            insert(self._attempt).values(**_encode_ai_ai_attempt(attempt.state)),
        )
        return persisted

    def complete_attempt(
        self,
        attempt_id: AiAttemptId,
        completion: AiAttempt,
        expected_status: AiAttemptStatus,
    ) -> AiAttempt:
        if (
            type(attempt_id) is not AiAttemptId
            or type(completion) is not AiAttempt
            or type(expected_status) is not AiAttemptStatus
            or completion.state.id != attempt_id
            or completion.evaluation_case_result_rows
            or completion.usage_cost_rows
            or (expected_status, completion.state.status) not in self._ATTEMPT_EDGES
            or completion.state.completed_at is None
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_row = _execute_one(
            self._session,
            select(self._attempt).where(self._attempt.c.id == attempt_id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_ai_ai_attempt(current_row)
        if current.status is not expected_status or current.completed_at is not None:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_values = _encode_ai_ai_attempt(current)
        target_values = _encode_ai_ai_attempt(completion.state)
        mutable = {
            "status",
            "completed_at",
            "output_artifact_id",
            "output_sha256",
            "latency_ms",
            "validation_status",
            "response_fingerprint",
            "resolved_model_id",
            "provider_region",
            "error_class",
            "error_code",
            "error_message",
        }
        _require_same(
            current_values,
            target_values,
            tuple(name for name in current_values if name not in mutable),
            PersistenceErrorCode.STATE_CONFLICT,
        )
        if completion.state.status is AiAttemptStatus.SUCCEEDED and any(
            value is not None
            for value in (
                completion.state.error_class,
                completion.state.error_code,
                completion.state.error_message,
            )
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        update_values = {name: target_values[name] for name in mutable}
        if completion.state.status is AiAttemptStatus.SUCCEEDED:
            update_values.update(error_class=None, error_code=None, error_message=None)
        row = _execute_one(
            self._session,
            update(self._attempt)
            .where(
                self._attempt.c.id == attempt_id.value,
                self._attempt.c.status == expected_status.value,
                self._attempt.c.completed_at.is_(None),
            )
            .values(**update_values)
            .returning(self._attempt),
        )
        if row is None:
            _state_zero(self._session, self._attempt, attempt_id.value, expected_status)
        state = _decode_ai_ai_attempt(row)
        case_results = tuple(
            _decode_ai_evaluation_case_result(item)
            for item in _execute_many(
                self._session,
                select(self._case_result)
                .where(self._case_result.c.ai_attempt_id == attempt_id.value)
                .order_by(self._case_result.c.id),
            )
        )
        usage = tuple(
            _decode_ai_usage_cost(item)
            for item in _execute_many(
                self._session,
                select(self._usage)
                .where(self._usage.c.ai_attempt_id == attempt_id.value)
                .order_by(self._usage.c.id),
            )
        )
        return AiAttempt(
            state=state,
            evaluation_case_result_rows=case_results,
            usage_cost_rows=usage,
        )

    def append_usage_cost(
        self,
        attempt_id: AiAttemptId,
        usage: UsageCost,
    ) -> None:
        if (
            type(attempt_id) is not AiAttemptId
            or type(usage) is not UsageCost
            or usage.ai_attempt_id != attempt_id
        ):
            raise ValueError("INVALID_AI_USAGE_COST_APPEND") from None
        owner = _execute_one(
            self._session,
            select(self._attempt.c.id).where(self._attempt.c.id == attempt_id.value),
        )
        if owner is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        _execute(
            self._session,
            insert(self._usage).values(**_encode_ai_usage_cost(usage)),
        )


@guard_repository_class
class SqlAlchemyEvaluationResultRepository:
    __slots__ = ("_result", "_session")

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._result = _table("ai.evaluation_result")

    def get(self, result_id: EvaluationResultId) -> EvaluationResult | None:
        if type(result_id) is not EvaluationResultId:
            raise ValueError("INVALID_EVALUATION_RESULT_ID") from None
        row = _execute_one(
            self._session,
            select(self._result).where(self._result.c.id == result_id.value),
        )
        return (
            None if row is None else EvaluationResult(_decode_ai_evaluation_result(row))
        )

    def append(self, result: EvaluationResult) -> None:
        if type(result) is not EvaluationResult:
            raise ValueError("INVALID_EVALUATION_RESULT") from None
        _execute(
            self._session,
            insert(self._result).values(**_encode_ai_evaluation_result(result.state)),
        )


@guard_repository_class
class SqlAlchemyEvaluationSuiteRepository:
    __slots__ = ("_session", "_suite")

    _EDGES = frozenset(
        {
            (EvaluationSuiteStatus.DRAFT, EvaluationSuiteStatus.LOCKED),
            (EvaluationSuiteStatus.DRAFT, EvaluationSuiteStatus.RETIRED),
            (EvaluationSuiteStatus.LOCKED, EvaluationSuiteStatus.ACTIVE),
            (EvaluationSuiteStatus.LOCKED, EvaluationSuiteStatus.RETIRED),
            (EvaluationSuiteStatus.ACTIVE, EvaluationSuiteStatus.RETIRED),
        }
    )

    _IMMUTABLE = (
        "id",
        "suite_code",
        "version_no",
        "task_definition_id",
        "risk_level",
        "rubric_artifact_id",
        "suite_config",
        "created_at",
    )

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._suite = _table("ai.evaluation_suite")

    def get(self, suite_id: EvaluationSuiteId) -> EvaluationSuite | None:
        if type(suite_id) is not EvaluationSuiteId:
            raise ValueError("INVALID_EVALUATION_SUITE_ID") from None
        row = _execute_one(
            self._session,
            select(self._suite).where(self._suite.c.id == suite_id.value),
        )
        return (
            None if row is None else EvaluationSuite(_decode_ai_evaluation_suite(row))
        )

    def get_active(
        self,
        task_id: AiTaskDefinitionId,
        suite_code: str,
    ) -> EvaluationSuite | None:
        if (
            type(task_id) is not AiTaskDefinitionId
            or type(suite_code) is not str
            or not suite_code
        ):
            raise ValueError("INVALID_EVALUATION_SUITE_LOOKUP") from None
        row = _execute_one(
            self._session,
            select(self._suite)
            .where(
                self._suite.c.task_definition_id == task_id.value,
                self._suite.c.suite_code == suite_code,
                self._suite.c.status == EvaluationSuiteStatus.ACTIVE.value,
            )
            .order_by(self._suite.c.version_no.desc(), self._suite.c.id.desc())
            .limit(1),
        )
        return (
            None if row is None else EvaluationSuite(_decode_ai_evaluation_suite(row))
        )

    def append_version(
        self,
        suite: EvaluationSuite,
        expected_latest_version: int | None,
    ) -> AggregateVersion:
        if type(suite) is not EvaluationSuite or suite.state.lock_version.value != 0:
            raise ValueError("INVALID_EVALUATION_SUITE") from None
        observed = _latest_version(
            self._session,
            self._suite,
            (
                self._suite.c.task_definition_id
                == suite.state.task_definition_id.value,
                self._suite.c.suite_code == suite.state.suite_code,
            ),
        )
        _validate_append_version(
            suite.state.version_no, expected_latest_version, observed
        )
        _execute(
            self._session,
            insert(self._suite).values(**_encode_ai_evaluation_suite(suite.state)),
        )
        return AggregateVersion(0)

    def transition(
        self,
        suite_id: EvaluationSuiteId,
        transition: EvaluationSuite,
        expected_version: AggregateVersion,
    ) -> EvaluationSuite:
        if (
            type(suite_id) is not EvaluationSuiteId
            or type(transition) is not EvaluationSuite
            or type(expected_version) is not AggregateVersion
            or transition.state.id != suite_id
        ):
            raise ValueError("INVALID_EVALUATION_SUITE_TRANSITION") from None
        current_row = _execute_one(
            self._session,
            select(self._suite).where(self._suite.c.id == suite_id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_ai_evaluation_suite(current_row)
        if current.lock_version != expected_version:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        if (current.status, transition.state.status) not in self._EDGES:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_values = _encode_ai_evaluation_suite(current)
        target_values = _encode_ai_evaluation_suite(transition.state)
        _require_same(
            current_values,
            target_values,
            self._IMMUTABLE,
            PersistenceErrorCode.STATE_CONFLICT,
        )
        row = _cas_row(
            self._session,
            self._suite,
            suite_id.value,
            expected_version,
            target_values,
        )
        return EvaluationSuite(_decode_ai_evaluation_suite(row))


@guard_repository_class
class SqlAlchemyEvaluationDatasetRepository:
    __slots__ = ("_case", "_dataset", "_session")

    _EDGES = frozenset(
        {
            (EvaluationDatasetStatus.DRAFT, EvaluationDatasetStatus.CURATING),
            (EvaluationDatasetStatus.DRAFT, EvaluationDatasetStatus.LOCKED),
            (EvaluationDatasetStatus.DRAFT, EvaluationDatasetStatus.RETIRED),
            (EvaluationDatasetStatus.CURATING, EvaluationDatasetStatus.LOCKED),
            (EvaluationDatasetStatus.CURATING, EvaluationDatasetStatus.COMPROMISED),
            (EvaluationDatasetStatus.CURATING, EvaluationDatasetStatus.RETIRED),
            (EvaluationDatasetStatus.LOCKED, EvaluationDatasetStatus.ACTIVE),
            (EvaluationDatasetStatus.LOCKED, EvaluationDatasetStatus.COMPROMISED),
            (EvaluationDatasetStatus.LOCKED, EvaluationDatasetStatus.RETIRED),
            (EvaluationDatasetStatus.ACTIVE, EvaluationDatasetStatus.COMPROMISED),
            (EvaluationDatasetStatus.ACTIVE, EvaluationDatasetStatus.RETIRED),
            (EvaluationDatasetStatus.COMPROMISED, EvaluationDatasetStatus.RETIRED),
        }
    )

    _IMMUTABLE = (
        "id",
        "display_id",
        "dataset_code",
        "version_no",
        "purpose",
        "split_policy",
        "dataset_artifact_id",
        "dataset_sha256",
        "created_at",
    )

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._dataset = _table("ai.evaluation_dataset_version")
        self._case = _table("ai.evaluation_case")

    def get(
        self, dataset_id: EvaluationDatasetVersionId
    ) -> EvaluationDatasetVersion | None:
        if type(dataset_id) is not EvaluationDatasetVersionId:
            raise ValueError("INVALID_EVALUATION_DATASET_ID") from None
        row = _execute_one(
            self._session,
            select(self._dataset).where(self._dataset.c.id == dataset_id.value),
        )
        if row is None:
            return None
        cases = tuple(
            _decode_ai_evaluation_case(item)
            for item in _execute_many(
                self._session,
                select(self._case)
                .where(self._case.c.dataset_version_id == dataset_id.value)
                .order_by(self._case.c.id),
            )
        )
        return EvaluationDatasetVersion(
            state=_decode_ai_evaluation_dataset_version(row),
            evaluation_case_rows=cases,
        )

    def append_version(
        self,
        dataset: EvaluationDatasetVersion,
        expected_latest_version: int | None,
    ) -> AggregateVersion:
        if (
            type(dataset) is not EvaluationDatasetVersion
            or dataset.state.lock_version.value != 0
            or any(
                item.dataset_version_id != dataset.state.id
                for item in dataset.evaluation_case_rows
            )
        ):
            raise ValueError("INVALID_EVALUATION_DATASET") from None
        observed = _latest_version(
            self._session,
            self._dataset,
            (self._dataset.c.dataset_code == dataset.state.dataset_code,),
        )
        _validate_append_version(
            dataset.state.version_no, expected_latest_version, observed
        )
        _execute(
            self._session,
            insert(self._dataset).values(
                **_encode_ai_evaluation_dataset_version(dataset.state)
            ),
        )
        for case in dataset.evaluation_case_rows:
            _execute(
                self._session,
                insert(self._case).values(**_encode_ai_evaluation_case(case)),
            )
        return AggregateVersion(0)

    def append_cases(
        self,
        dataset_id: EvaluationDatasetVersionId,
        cases: tuple[EvaluationCase, ...],
        expected_version: AggregateVersion,
    ) -> AggregateVersion:
        if (
            type(dataset_id) is not EvaluationDatasetVersionId
            or type(cases) is not tuple
            or not cases
            or any(type(item) is not EvaluationCase for item in cases)
            or any(item.dataset_version_id != dataset_id for item in cases)
            or type(expected_version) is not AggregateVersion
        ):
            raise ValueError("INVALID_EVALUATION_CASE_APPEND") from None
        persisted = _cas_bump(
            self._session,
            self._dataset,
            dataset_id.value,
            expected_version,
        )
        for case in cases:
            _execute(
                self._session,
                insert(self._case).values(**_encode_ai_evaluation_case(case)),
            )
        return persisted

    def transition(
        self,
        dataset_id: EvaluationDatasetVersionId,
        transition: EvaluationDatasetVersion,
        expected_version: AggregateVersion,
    ) -> EvaluationDatasetVersion:
        if (
            type(dataset_id) is not EvaluationDatasetVersionId
            or type(transition) is not EvaluationDatasetVersion
            or type(expected_version) is not AggregateVersion
            or transition.state.id != dataset_id
            or transition.evaluation_case_rows
        ):
            raise ValueError("INVALID_EVALUATION_DATASET_TRANSITION") from None
        current_row = _execute_one(
            self._session,
            select(self._dataset).where(self._dataset.c.id == dataset_id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_ai_evaluation_dataset_version(current_row)
        if current.lock_version != expected_version:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        if (current.status, transition.state.status) not in self._EDGES:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_values = _encode_ai_evaluation_dataset_version(current)
        target_values = _encode_ai_evaluation_dataset_version(transition.state)
        _require_same(
            current_values,
            target_values,
            self._IMMUTABLE,
            PersistenceErrorCode.STATE_CONFLICT,
        )
        row = _cas_row(
            self._session,
            self._dataset,
            dataset_id.value,
            expected_version,
            target_values,
        )
        return EvaluationDatasetVersion(
            state=_decode_ai_evaluation_dataset_version(row)
        )


@guard_repository_class
class SqlAlchemyEvaluationRunRepository:
    __slots__ = ("_case_result", "_human", "_run", "_session")

    _EDGES = frozenset(
        {
            (EvaluationRunStatus.PLANNED, EvaluationRunStatus.RUNNING),
            (EvaluationRunStatus.PLANNED, EvaluationRunStatus.FAILED),
            (EvaluationRunStatus.PLANNED, EvaluationRunStatus.INVALIDATED),
            (EvaluationRunStatus.RUNNING, EvaluationRunStatus.GRADING),
            (EvaluationRunStatus.RUNNING, EvaluationRunStatus.FAILED),
            (EvaluationRunStatus.RUNNING, EvaluationRunStatus.INVALIDATED),
            (EvaluationRunStatus.GRADING, EvaluationRunStatus.HUMAN_REVIEW),
            (EvaluationRunStatus.GRADING, EvaluationRunStatus.COMPLETED),
            (EvaluationRunStatus.GRADING, EvaluationRunStatus.FAILED),
            (EvaluationRunStatus.GRADING, EvaluationRunStatus.INVALIDATED),
            (EvaluationRunStatus.HUMAN_REVIEW, EvaluationRunStatus.COMPLETED),
            (EvaluationRunStatus.HUMAN_REVIEW, EvaluationRunStatus.FAILED),
            (EvaluationRunStatus.HUMAN_REVIEW, EvaluationRunStatus.INVALIDATED),
            (EvaluationRunStatus.COMPLETED, EvaluationRunStatus.INVALIDATED),
        }
    )

    _IMMUTABLE = (
        "id",
        "display_id",
        "suite_id",
        "dataset_version_id",
        "baseline_evaluation_run_id",
        "prompt_version_id",
        "model_route_version_id",
        "output_schema_version_id",
        "policy_bundle_version_id",
        "code_git_sha",
        "created_by_principal_id",
        "created_at",
        "resolved_model_id",
    )

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._run = _table("ai.evaluation_run")
        self._case_result = _table("ai.evaluation_case_result")
        self._human = _table("ai.human_evaluation")

    def get(self, run_id: EvaluationRunId) -> EvaluationRun | None:
        if type(run_id) is not EvaluationRunId:
            raise ValueError("INVALID_EVALUATION_RUN_ID") from None
        row = _execute_one(
            self._session,
            select(self._run).where(self._run.c.id == run_id.value),
        )
        if row is None:
            return None
        result_rows = _execute_many(
            self._session,
            select(self._case_result)
            .where(self._case_result.c.evaluation_run_id == run_id.value)
            .order_by(self._case_result.c.id),
        )
        results = tuple(_decode_ai_evaluation_case_result(item) for item in result_rows)
        result_ids = tuple(item.id.value for item in results)
        human: tuple[HumanEvaluation, ...] = ()
        if result_ids:
            human = tuple(
                _decode_ai_human_evaluation(item)
                for item in _execute_many(
                    self._session,
                    select(self._human)
                    .where(self._human.c.evaluation_case_result_id.in_(result_ids))
                    .order_by(self._human.c.id),
                )
            )
        run = EvaluationRun(
            state=_decode_ai_evaluation_run(row),
            evaluation_case_result_rows=results,
            human_evaluation_rows=human,
        )
        register_pending_events(
            self._session,
            aggregate_type="ai.evaluation_run",
            aggregate_id=run.state.id.value,
            buffer=run._events,
        )
        return run

    def add(self, run: EvaluationRun) -> AggregateVersion:
        result_ids = (
            frozenset(item.id for item in run.evaluation_case_result_rows)
            if type(run) is EvaluationRun
            else frozenset()
        )
        if (
            type(run) is not EvaluationRun
            or run.state.lock_version.value != 0
            or any(
                item.evaluation_run_id != run.state.id
                for item in run.evaluation_case_result_rows
            )
            or any(
                item.evaluation_case_result_id not in result_ids
                for item in run.human_evaluation_rows
            )
        ):
            raise ValueError("INVALID_EVALUATION_RUN") from None
        if run.pending_events():
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        register_pending_events(
            self._session,
            aggregate_type="ai.evaluation_run",
            aggregate_id=run.state.id.value,
            buffer=run._events,
        )
        _execute(
            self._session,
            insert(self._run).values(**_encode_ai_evaluation_run(run.state)),
        )
        for result in run.evaluation_case_result_rows:
            _execute(
                self._session,
                insert(self._case_result).values(
                    **_encode_ai_evaluation_case_result(result)
                ),
            )
        for evaluation in run.human_evaluation_rows:
            _execute(
                self._session,
                insert(self._human).values(**_encode_ai_human_evaluation(evaluation)),
            )
        return AggregateVersion(0)

    def transition(
        self,
        run_id: EvaluationRunId,
        transition: EvaluationRun,
        expected_version: AggregateVersion,
    ) -> EvaluationRun:
        if (
            type(run_id) is not EvaluationRunId
            or type(transition) is not EvaluationRun
            or type(expected_version) is not AggregateVersion
            or transition.state.id != run_id
            or transition.evaluation_case_result_rows
            or transition.human_evaluation_rows
        ):
            raise ValueError("INVALID_EVALUATION_RUN_TRANSITION") from None
        pending = transition.pending_events()
        emits = transition.state.status is EvaluationRunStatus.COMPLETED
        if emits and not pending:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        if pending:
            if (
                len(pending) != 1
                or type(pending[0]) is not AiEvaluationCompletedV2
                or pending[0].aggregate_id != run_id
                or not emits
            ):
                _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        register_pending_events(
            self._session,
            aggregate_type="ai.evaluation_run",
            aggregate_id=run_id.value,
            buffer=transition._events,
        )
        current_row = _execute_one(
            self._session,
            select(self._run).where(self._run.c.id == run_id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_ai_evaluation_run(current_row)
        if current.lock_version != expected_version:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        if (current.status, transition.state.status) not in self._EDGES:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_values = _encode_ai_evaluation_run(current)
        target_values = _encode_ai_evaluation_run(transition.state)
        _require_same(
            current_values,
            target_values,
            self._IMMUTABLE,
            PersistenceErrorCode.STATE_CONFLICT,
        )
        row = _cas_row(
            self._session,
            self._run,
            run_id.value,
            expected_version,
            target_values,
        )
        state = _decode_ai_evaluation_run(row)
        if emits:
            stage_registered_events(
                self._session,
                aggregate_type="ai.evaluation_run",
                aggregate_id=run_id.value,
                owning_method="EvaluationRunRepository.transition",
                persisted_version=state.lock_version,
                expected_event_type="jp.raos.ai.evaluation_completed.v2",
            )
        return EvaluationRun(state=state)

    def append_case_results(
        self,
        run_id: EvaluationRunId,
        results: tuple[EvaluationCaseResult, ...],
        expected_version: AggregateVersion,
    ) -> AggregateVersion:
        if (
            type(run_id) is not EvaluationRunId
            or type(results) is not tuple
            or not results
            or any(type(item) is not EvaluationCaseResult for item in results)
            or any(item.evaluation_run_id != run_id for item in results)
            or type(expected_version) is not AggregateVersion
        ):
            raise ValueError("INVALID_EVALUATION_CASE_RESULTS") from None
        persisted = _cas_bump(self._session, self._run, run_id.value, expected_version)
        for result in results:
            _execute(
                self._session,
                insert(self._case_result).values(
                    **_encode_ai_evaluation_case_result(result)
                ),
            )
        return persisted

    def append_human_evaluations(
        self,
        run_id: EvaluationRunId,
        evaluations: tuple[HumanEvaluation, ...],
        expected_version: AggregateVersion,
    ) -> AggregateVersion:
        if (
            type(run_id) is not EvaluationRunId
            or type(evaluations) is not tuple
            or not evaluations
            or any(type(item) is not HumanEvaluation for item in evaluations)
            or type(expected_version) is not AggregateVersion
        ):
            raise ValueError("INVALID_HUMAN_EVALUATIONS") from None
        requested_ids = frozenset(
            item.evaluation_case_result_id.value for item in evaluations
        )
        owned_rows = _execute_many(
            self._session,
            select(self._case_result.c.id).where(
                self._case_result.c.evaluation_run_id == run_id.value,
                self._case_result.c.id.in_(requested_ids),
            ),
        )
        owned_ids = frozenset(row.get("id") for row in owned_rows)
        if owned_ids != requested_ids:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        persisted = _cas_bump(self._session, self._run, run_id.value, expected_version)
        for evaluation in evaluations:
            _execute(
                self._session,
                insert(self._human).values(**_encode_ai_human_evaluation(evaluation)),
            )
        return persisted


@guard_repository_class
class SqlAlchemyJudgeCalibrationRepository:
    __slots__ = ("_calibration", "_session")

    _EDGES = frozenset(
        {
            (JudgeCalibrationStatus.DRAFT, JudgeCalibrationStatus.PASSED),
            (JudgeCalibrationStatus.DRAFT, JudgeCalibrationStatus.FAILED),
            (JudgeCalibrationStatus.PASSED, JudgeCalibrationStatus.EXPIRED),
            (JudgeCalibrationStatus.PASSED, JudgeCalibrationStatus.RETIRED),
            (JudgeCalibrationStatus.FAILED, JudgeCalibrationStatus.RETIRED),
            (JudgeCalibrationStatus.EXPIRED, JudgeCalibrationStatus.RETIRED),
        }
    )

    _IMMUTABLE = (
        "id",
        "display_id",
        "judge_route_version_id",
        "judge_prompt_version_id",
        "dataset_version_id",
        "case_count",
        "created_at",
        "evaluated_task_definition_id",
        "resolved_judge_model_id",
        "rubric_artifact_id",
        "rubric_sha256",
        "grader_version",
    )

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._calibration = _table("ai.judge_calibration")

    def get(self, calibration_id: JudgeCalibrationId) -> JudgeCalibration | None:
        if type(calibration_id) is not JudgeCalibrationId:
            raise ValueError("INVALID_JUDGE_CALIBRATION_ID") from None
        row = _execute_one(
            self._session,
            select(self._calibration).where(
                self._calibration.c.id == calibration_id.value
            ),
        )
        return (
            None if row is None else JudgeCalibration(_decode_ai_judge_calibration(row))
        )

    def add(self, calibration: JudgeCalibration) -> AggregateVersion:
        if (
            type(calibration) is not JudgeCalibration
            or calibration.state.lock_version.value != 0
        ):
            raise ValueError("INVALID_JUDGE_CALIBRATION") from None
        _execute(
            self._session,
            insert(self._calibration).values(
                **_encode_ai_judge_calibration(calibration.state)
            ),
        )
        return AggregateVersion(0)

    def transition(
        self,
        calibration_id: JudgeCalibrationId,
        transition: JudgeCalibration,
        expected_version: AggregateVersion,
    ) -> JudgeCalibration:
        if (
            type(calibration_id) is not JudgeCalibrationId
            or type(transition) is not JudgeCalibration
            or type(expected_version) is not AggregateVersion
            or transition.state.id != calibration_id
        ):
            raise ValueError("INVALID_JUDGE_CALIBRATION_TRANSITION") from None
        current_row = _execute_one(
            self._session,
            select(self._calibration).where(
                self._calibration.c.id == calibration_id.value
            ),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_ai_judge_calibration(current_row)
        if current.lock_version != expected_version:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        if (current.status, transition.state.status) not in self._EDGES:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_values = _encode_ai_judge_calibration(current)
        target_values = _encode_ai_judge_calibration(transition.state)
        _require_same(
            current_values,
            target_values,
            self._IMMUTABLE,
            PersistenceErrorCode.STATE_CONFLICT,
        )
        row = _cas_row(
            self._session,
            self._calibration,
            calibration_id.value,
            expected_version,
            target_values,
        )
        return JudgeCalibration(_decode_ai_judge_calibration(row))


@guard_repository_class
class SqlAlchemyReleaseDecisionRepository:
    __slots__ = ("_approval", "_decision", "_session")

    _EDGES = frozenset(
        {
            (ReleaseDecisionStatus.DRAFT, ReleaseDecisionStatus.READY_FOR_REVIEW),
            (ReleaseDecisionStatus.DRAFT, ReleaseDecisionStatus.REJECTED),
            (
                ReleaseDecisionStatus.READY_FOR_REVIEW,
                ReleaseDecisionStatus.APPROVED_CANARY,
            ),
            (
                ReleaseDecisionStatus.READY_FOR_REVIEW,
                ReleaseDecisionStatus.APPROVED_ACTIVE,
            ),
            (
                ReleaseDecisionStatus.READY_FOR_REVIEW,
                ReleaseDecisionStatus.REJECTED,
            ),
            (
                ReleaseDecisionStatus.APPROVED_CANARY,
                ReleaseDecisionStatus.APPROVED_ACTIVE,
            ),
            (
                ReleaseDecisionStatus.APPROVED_CANARY,
                ReleaseDecisionStatus.REVOKED,
            ),
            (
                ReleaseDecisionStatus.APPROVED_ACTIVE,
                ReleaseDecisionStatus.REVOKED,
            ),
        }
    )

    _IMMUTABLE = (
        "id",
        "display_id",
        "task_definition_id",
        "prompt_version_id",
        "model_route_version_id",
        "output_schema_version_id",
        "resolved_model_id",
        "policy_bundle_version_id",
        "dataset_version_id",
        "evaluation_run_id",
        "code_git_sha",
        "release_scope",
        "maximum_canary_percent",
        "decision_manifest_sha256",
        "rollback_release_decision_id",
        "created_at",
        "judge_calibration_id",
        "rollback_strategy",
        "rollback_runbook_artifact_id",
        "rollback_runbook_sha256",
        "canary_monitoring_artifact_id",
        "canary_monitoring_sha256",
    )

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._decision = _table("ai.release_decision")
        self._approval = _table("ai.release_approval")

    def get(self, decision_id: ReleaseDecisionId) -> ReleaseDecision | None:
        if type(decision_id) is not ReleaseDecisionId:
            raise ValueError("INVALID_RELEASE_DECISION_ID") from None
        row = _execute_one(
            self._session,
            select(self._decision).where(self._decision.c.id == decision_id.value),
        )
        if row is None:
            return None
        approvals = tuple(
            _decode_ai_release_approval(item)
            for item in _execute_many(
                self._session,
                select(self._approval)
                .where(self._approval.c.release_decision_id == decision_id.value)
                .order_by(self._approval.c.id),
            )
        )
        decision = ReleaseDecision(
            state=_decode_ai_release_decision(row),
            release_approval_rows=approvals,
        )
        register_pending_events(
            self._session,
            aggregate_type="ai.release_decision",
            aggregate_id=decision.state.id.value,
            buffer=decision._events,
        )
        return decision

    def add(self, decision: ReleaseDecision) -> AggregateVersion:
        if (
            type(decision) is not ReleaseDecision
            or decision.state.lock_version.value != 0
            or any(
                item.release_decision_id != decision.state.id
                or item.decision_manifest_sha256
                != decision.state.decision_manifest_sha256
                for item in decision.release_approval_rows
            )
        ):
            raise ValueError("INVALID_RELEASE_DECISION") from None
        if decision.pending_events():
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        register_pending_events(
            self._session,
            aggregate_type="ai.release_decision",
            aggregate_id=decision.state.id.value,
            buffer=decision._events,
        )
        _execute(
            self._session,
            insert(self._decision).values(
                **_encode_ai_release_decision(decision.state)
            ),
        )
        for approval in decision.release_approval_rows:
            _execute(
                self._session,
                insert(self._approval).values(**_encode_ai_release_approval(approval)),
            )
        return AggregateVersion(0)

    def append_approval(
        self,
        decision_id: ReleaseDecisionId,
        approval: ReleaseApproval,
        expected_version: AggregateVersion,
    ) -> AggregateVersion:
        if (
            type(decision_id) is not ReleaseDecisionId
            or type(approval) is not ReleaseApproval
            or type(expected_version) is not AggregateVersion
            or approval.release_decision_id != decision_id
        ):
            raise ValueError("INVALID_RELEASE_APPROVAL") from None
        owner_row = _execute_one(
            self._session,
            select(
                self._decision.c.id,
                self._decision.c.lock_version,
                self._decision.c.decision_manifest_sha256,
            ).where(self._decision.c.id == decision_id.value),
        )
        if owner_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        if owner_row.get("lock_version") != expected_version.value:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        if owner_row.get("decision_manifest_sha256") != (
            approval.decision_manifest_sha256.value
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        persisted = _cas_bump(
            self._session,
            self._decision,
            decision_id.value,
            expected_version,
        )
        _execute(
            self._session,
            insert(self._approval).values(**_encode_ai_release_approval(approval)),
        )
        return persisted

    def transition(
        self,
        decision_id: ReleaseDecisionId,
        transition: ReleaseDecision,
        expected_version: AggregateVersion,
    ) -> ReleaseDecision:
        if (
            type(decision_id) is not ReleaseDecisionId
            or type(transition) is not ReleaseDecision
            or type(expected_version) is not AggregateVersion
            or transition.state.id != decision_id
            or transition.release_approval_rows
        ):
            raise ValueError("INVALID_RELEASE_DECISION_TRANSITION") from None
        target_status = transition.state.status
        approves = target_status in {
            ReleaseDecisionStatus.APPROVED_CANARY,
            ReleaseDecisionStatus.APPROVED_ACTIVE,
        }
        revokes = target_status is ReleaseDecisionStatus.REVOKED
        pending = transition.pending_events()
        if (approves or revokes) and not pending:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        if pending:
            if len(pending) != 1 or pending[0].aggregate_id != decision_id:
                _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
            event = pending[0]
            if approves:
                expected_phase = (
                    "CANARY"
                    if target_status is ReleaseDecisionStatus.APPROVED_CANARY
                    else "ACTIVE"
                )
                if (
                    type(event) is not AiReleaseDecisionApproved
                    or event.data["phase"] != expected_phase
                ):
                    _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
            elif revokes:
                if type(event) is not AiReleaseDecisionRevoked:
                    _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
            else:
                _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        register_pending_events(
            self._session,
            aggregate_type="ai.release_decision",
            aggregate_id=decision_id.value,
            buffer=transition._events,
        )
        current_row = _execute_one(
            self._session,
            select(self._decision).where(self._decision.c.id == decision_id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_ai_release_decision(current_row)
        if current.lock_version != expected_version:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        if (current.status, transition.state.status) not in self._EDGES:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current_values = _encode_ai_release_decision(current)
        target_values = _encode_ai_release_decision(transition.state)
        _require_same(
            current_values,
            target_values,
            self._IMMUTABLE,
            PersistenceErrorCode.STATE_CONFLICT,
        )
        row = _cas_row(
            self._session,
            self._decision,
            decision_id.value,
            expected_version,
            target_values,
        )
        state = _decode_ai_release_decision(row)
        if approves:
            stage_registered_events(
                self._session,
                aggregate_type="ai.release_decision",
                aggregate_id=decision_id.value,
                owning_method="ReleaseDecisionRepository.transition",
                persisted_version=state.lock_version,
                expected_event_type="jp.raos.ai.release_decision_approved.v1",
            )
        elif revokes:
            stage_registered_events(
                self._session,
                aggregate_type="ai.release_decision",
                aggregate_id=decision_id.value,
                owning_method="ReleaseDecisionRepository.transition",
                persisted_version=state.lock_version,
                expected_event_type="jp.raos.ai.release_decision_revoked.v1",
            )
        return ReleaseDecision(state=state)


__all__ = [
    "SqlAlchemyAiJobRepository",
    "SqlAlchemyAiTaskDefinitionRepository",
    "SqlAlchemyEvaluationDatasetRepository",
    "SqlAlchemyEvaluationResultRepository",
    "SqlAlchemyEvaluationRunRepository",
    "SqlAlchemyEvaluationSuiteRepository",
    "SqlAlchemyJudgeCalibrationRepository",
    "SqlAlchemyModelDefinitionRepository",
    "SqlAlchemyModelRouteVersionRepository",
    "SqlAlchemyOutputSchemaVersionRepository",
    "SqlAlchemyPromptVersionRepository",
    "SqlAlchemyReleaseDecisionRepository",
]

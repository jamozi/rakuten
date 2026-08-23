"""Concrete aggregate-specific SQLAlchemy repositories for OPS (ST-0308)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import json
from typing import NoReturn, TypeVar
from uuid import UUID

from sqlalchemy import Table, func, insert, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.base import Executable

import raos.adapters.persistence.sqlalchemy.mappers.ops as domain_mappers
from raos.adapters.persistence.sqlalchemy.session_runtime import (
    fail_session_operation,
    guard_repository_class,
    persistence_context,
    register_pending_events,
    stage_registered_events,
)
from raos.adapters.persistence.sqlalchemy.series_lock import (
    lock_runtime_setting_version_series,
)
from raos.domain.ops.aggregates import (
    Job,
    JobAttempt,
    JobState,
    ObjectArtifact,
    RuntimeSettingScope,
    RuntimeSettingVersion,
    RuntimeSettingVersionState,
)
from raos.domain.iam.ids import (
    CreatedByPrincipalId,
    PrincipalId,
)
from raos.domain.ops.enums import (
    JobAttemptStatus,
    JobStatus,
    ObjectArtifactArtifactKind,
    ObjectArtifactEncryptionState,
    RuntimeSettingVersionScopeType,
    RuntimeSettingVersionSettingClass,
    RuntimeSettingVersionStatus,
)
from raos.domain.ops.ids import (
    JobAttemptId,
    JobId,
    ObjectArtifactId,
    RuntimeSettingVersionId,
)
from raos.domain.ops.events import OpsJobRequested
from raos.domain.ops.values import (
    JobAttemptMetricsJson,
    JobPayloadJson,
    ObjectArtifactMetadataJson,
    RuntimeSettingVersionValueJson,
)
from raos.domain.portfolio.ids import (
    SiteId,
)
from raos.domain.shared.identity import (
    ActorId,
    CausationId,
    CorrelationId,
    OpaqueResourceId,
    ScopeId,
)
from raos.domain.shared.persistence import (
    AggregateVersion,
    AwareUtcDateTime,
    Sha256Digest,
    YenMinor,
)
from raos.domain.shared.identity import EntityId
from raos.domain.shared.json_values import FrozenJsonObject, canonical_json_bytes
from raos.domain.shared.persistence import EmailAddress, UriReference
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
            JobAttemptMetricsJson,
            JobPayloadJson,
            ObjectArtifactMetadataJson,
            RuntimeSettingVersionValueJson,
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


def _decode_ops_job(row: RowData) -> JobState:
    try:
        return domain_mappers.map_ops_job_from_row(
            id=JobId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            job_type=_exact(row, "job_type", str),
            queue_name=_exact(row, "queue_name", str),
            status=JobStatus(_exact(row, "status", str)),
            priority=_exact(row, "priority", int),
            idempotency_key=_optional(row, "idempotency_key", str),
            site_id=(
                None
                if row.get("site_id") is None
                else SiteId(_exact(row, "site_id", UUID))
            ),
            aggregate_type=_optional(row, "aggregate_type", str),
            aggregate_id=(
                None
                if row.get("aggregate_id") is None
                else OpaqueResourceId(_exact(row, "aggregate_id", UUID))
            ),
            payload=JobPayloadJson(_json_object(row, "payload")),
            payload_artifact_id=(
                None
                if row.get("payload_artifact_id") is None
                else ObjectArtifactId(_exact(row, "payload_artifact_id", UUID))
            ),
            scheduled_at=(
                None
                if row.get("scheduled_at") is None
                else AwareUtcDateTime(_exact(row, "scheduled_at", datetime))
            ),
            available_at=AwareUtcDateTime(_exact(row, "available_at", datetime)),
            started_at=(
                None
                if row.get("started_at") is None
                else AwareUtcDateTime(_exact(row, "started_at", datetime))
            ),
            completed_at=(
                None
                if row.get("completed_at") is None
                else AwareUtcDateTime(_exact(row, "completed_at", datetime))
            ),
            max_attempts=_exact(row, "max_attempts", int),
            attempt_count=_exact(row, "attempt_count", int),
            lease_owner=_optional(row, "lease_owner", str),
            lease_expires_at=(
                None
                if row.get("lease_expires_at") is None
                else AwareUtcDateTime(_exact(row, "lease_expires_at", datetime))
            ),
            correlation_id=CorrelationId(_exact(row, "correlation_id", UUID)),
            causation_id=(
                None
                if row.get("causation_id") is None
                else CausationId(_exact(row, "causation_id", UUID))
            ),
            parent_job_id=(
                None
                if row.get("parent_job_id") is None
                else JobId(_exact(row, "parent_job_id", UUID))
            ),
            budget_jpy=(
                None
                if row.get("budget_jpy") is None
                else YenMinor(_exact(row, "budget_jpy", int))
            ),
            created_by_actor_type=_exact(row, "created_by_actor_type", str),
            created_by_actor_id=(
                None
                if row.get("created_by_actor_id") is None
                else ActorId(_exact(row, "created_by_actor_id", UUID))
            ),
            last_error_class=_optional(row, "last_error_class", str),
            last_error_code=_optional(row, "last_error_code", str),
            last_error_message=_optional(row, "last_error_message", str),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
            job_version=_exact(row, "job_version", int),
            deadline_at=(
                None
                if row.get("deadline_at") is None
                else AwareUtcDateTime(_exact(row, "deadline_at", datetime))
            ),
            cancel_requested_at=(
                None
                if row.get("cancel_requested_at") is None
                else AwareUtcDateTime(_exact(row, "cancel_requested_at", datetime))
            ),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_ops_job(value: JobState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "job_type",
            "queue_name",
            "status",
            "priority",
            "idempotency_key",
            "site_id",
            "aggregate_type",
            "aggregate_id",
            "payload",
            "payload_artifact_id",
            "scheduled_at",
            "available_at",
            "started_at",
            "completed_at",
            "max_attempts",
            "attempt_count",
            "lease_owner",
            "lease_expires_at",
            "correlation_id",
            "causation_id",
            "parent_job_id",
            "budget_jpy",
            "created_by_actor_type",
            "created_by_actor_id",
            "last_error_class",
            "last_error_code",
            "last_error_message",
            "created_at",
            "updated_at",
            "lock_version",
            "job_version",
            "deadline_at",
            "cancel_requested_at",
        ),
        domain_mappers.map_ops_job_to_row(value),
    )


def _decode_ops_job_attempt(row: RowData) -> JobAttempt:
    try:
        return domain_mappers.map_ops_job_attempt_from_row(
            id=JobAttemptId(_exact(row, "id", UUID)),
            job_id=JobId(_exact(row, "job_id", UUID)),
            attempt_no=_exact(row, "attempt_no", int),
            status=JobAttemptStatus(_exact(row, "status", str)),
            worker_id=_exact(row, "worker_id", str),
            handler_version=_exact(row, "handler_version", str),
            started_at=AwareUtcDateTime(_exact(row, "started_at", datetime)),
            completed_at=(
                None
                if row.get("completed_at") is None
                else AwareUtcDateTime(_exact(row, "completed_at", datetime))
            ),
            provider_request_id=_optional(row, "provider_request_id", str),
            input_artifact_id=(
                None
                if row.get("input_artifact_id") is None
                else ObjectArtifactId(_exact(row, "input_artifact_id", UUID))
            ),
            output_artifact_id=(
                None
                if row.get("output_artifact_id") is None
                else ObjectArtifactId(_exact(row, "output_artifact_id", UUID))
            ),
            error_class=_optional(row, "error_class", str),
            error_code=_optional(row, "error_code", str),
            error_message=_optional(row, "error_message", str),
            retry_after_at=(
                None
                if row.get("retry_after_at") is None
                else AwareUtcDateTime(_exact(row, "retry_after_at", datetime))
            ),
            metrics=JobAttemptMetricsJson(_json_object(row, "metrics")),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_ops_job_attempt(value: JobAttempt) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "job_id",
            "attempt_no",
            "status",
            "worker_id",
            "handler_version",
            "started_at",
            "completed_at",
            "provider_request_id",
            "input_artifact_id",
            "output_artifact_id",
            "error_class",
            "error_code",
            "error_message",
            "retry_after_at",
            "metrics",
            "created_at",
        ),
        domain_mappers.map_ops_job_attempt_to_row(value),
    )


def _decode_ops_object_artifact(row: RowData) -> ObjectArtifact:
    try:
        return domain_mappers.map_ops_object_artifact_from_row(
            id=ObjectArtifactId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            artifact_kind=ObjectArtifactArtifactKind(_exact(row, "artifact_kind", str)),
            storage_provider=_exact(row, "storage_provider", str),
            bucket_name=_exact(row, "bucket_name", str),
            object_key=_exact(row, "object_key", str),
            object_version=_optional(row, "object_version", str),
            content_type=_exact(row, "content_type", str),
            byte_size=_exact(row, "byte_size", int),
            sha256=Sha256Digest(_exact(row, "sha256", str)),
            encryption_state=ObjectArtifactEncryptionState(
                _exact(row, "encryption_state", str)
            ),
            retention_class=_exact(row, "retention_class", str),
            is_immutable=_exact(row, "is_immutable", bool),
            source_system=_exact(row, "source_system", str),
            acquired_at=(
                None
                if row.get("acquired_at") is None
                else AwareUtcDateTime(_exact(row, "acquired_at", datetime))
            ),
            created_by_principal_id=(
                None
                if row.get("created_by_principal_id") is None
                else CreatedByPrincipalId(_exact(row, "created_by_principal_id", UUID))
            ),
            metadata=ObjectArtifactMetadataJson(_json_object(row, "metadata")),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_ops_object_artifact(value: ObjectArtifact) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "artifact_kind",
            "storage_provider",
            "bucket_name",
            "object_key",
            "object_version",
            "content_type",
            "byte_size",
            "sha256",
            "encryption_state",
            "retention_class",
            "is_immutable",
            "source_system",
            "acquired_at",
            "created_by_principal_id",
            "metadata",
            "created_at",
        ),
        domain_mappers.map_ops_object_artifact_to_row(value),
    )


def _decode_ops_runtime_setting_version(
    row: RowData,
) -> RuntimeSettingVersionState:
    try:
        return domain_mappers.map_ops_runtime_setting_version_from_row(
            id=RuntimeSettingVersionId(_exact(row, "id", UUID)),
            setting_key=_exact(row, "setting_key", str),
            scope_type=RuntimeSettingVersionScopeType(_exact(row, "scope_type", str)),
            scope_id=(
                None
                if row.get("scope_id") is None
                else ScopeId(_exact(row, "scope_id", UUID))
            ),
            version_no=_exact(row, "version_no", int),
            setting_class=RuntimeSettingVersionSettingClass(
                _exact(row, "setting_class", str)
            ),
            value=RuntimeSettingVersionValueJson(_json_object(row, "value")),
            value_sha256=Sha256Digest(_exact(row, "value_sha256", str)),
            status=RuntimeSettingVersionStatus(_exact(row, "status", str)),
            effective_from=(
                None
                if row.get("effective_from") is None
                else AwareUtcDateTime(_exact(row, "effective_from", datetime))
            ),
            effective_to=(
                None
                if row.get("effective_to") is None
                else AwareUtcDateTime(_exact(row, "effective_to", datetime))
            ),
            created_by_principal_id=PrincipalId(
                _exact(row, "created_by_principal_id", UUID)
            ),
            approved_by_principal_id=(
                None
                if row.get("approved_by_principal_id") is None
                else PrincipalId(_exact(row, "approved_by_principal_id", UUID))
            ),
            approval_reason=_optional(row, "approval_reason", str),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_ops_runtime_setting_version(
    value: RuntimeSettingVersionState,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "setting_key",
            "scope_type",
            "scope_id",
            "version_no",
            "setting_class",
            "value",
            "value_sha256",
            "status",
            "effective_from",
            "effective_to",
            "created_by_principal_id",
            "approved_by_principal_id",
            "approval_reason",
            "created_at",
        ),
        domain_mappers.map_ops_runtime_setting_version_to_row(value),
    )


# Aggregate-specific classes below are the only DML surface.


@guard_repository_class
class SqlAlchemyJobRepository:
    __slots__ = ("_attempt", "_job", "_session")

    def __init__(self, session: Session) -> None:
        if not isinstance(session, Session):
            raise ValueError("INVALID_OPS_REPOSITORY") from None
        self._session = session
        self._job = _table("ops.job")
        self._attempt = _table("ops.job_attempt")

    def get(self, job_id: JobId) -> Job | None:
        if type(job_id) is not JobId:
            raise ValueError("INVALID_JOB_ID") from None
        row = _execute_one(
            self._session, select(self._job).where(self._job.c.id == job_id.value)
        )
        if row is None:
            return None
        state = _decode_ops_job(row)
        try:
            rows = self._session.execute(
                select(self._attempt)
                .where(self._attempt.c.job_id == job_id.value)
                .order_by(self._attempt.c.id)
            ).mappings()
            attempts = tuple(_decode_ops_job_attempt(item) for item in rows)
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
            return Job(state=state, job_attempt_rows=attempts)
        except ValueError:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)

    def add(self, job: Job) -> AggregateVersion:
        if type(job) is not Job or job.state.lock_version.value != 0:
            raise ValueError("INVALID_JOB") from None
        pending = job.pending_events()
        if not pending:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        if (
            len(pending) != 1
            or type(pending[0]) is not OpsJobRequested
            or pending[0].aggregate_id != job.state.id
            or job.state.status is not JobStatus.REQUESTED
            or pending[0].data["job_id"] != str(job.state.id.value)
            or pending[0].data["job_type"] != job.state.job_type
            or pending[0].data["queue"] != job.state.queue_name
            or pending[0].data["available_at"]
            != job.state.available_at.value.isoformat()
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        persisted = AggregateVersion(0)
        register_pending_events(
            self._session,
            aggregate_type="ops.job",
            aggregate_id=job.state.id.value,
            buffer=job._event_buffer,
        )
        _execute(self._session, insert(self._job).values(**_encode_ops_job(job.state)))
        for attempt in job.job_attempt_rows:
            _execute(
                self._session,
                insert(self._attempt).values(**_encode_ops_job_attempt(attempt)),
            )
        stage_registered_events(
            self._session,
            aggregate_type="ops.job",
            aggregate_id=job.state.id.value,
            owning_method="JobRepository.add",
            persisted_version=persisted,
            expected_event_type="jp.raos.ops.job_requested.v1",
        )
        return persisted


@guard_repository_class
class SqlAlchemyObjectArtifactRepository:
    __slots__ = ("_session", "_table")

    def __init__(self, session: Session) -> None:
        if not isinstance(session, Session):
            raise ValueError("INVALID_OPS_REPOSITORY") from None
        self._session = session
        self._table = _table("ops.object_artifact")

    def get(self, artifact_id: ObjectArtifactId) -> ObjectArtifact | None:
        if type(artifact_id) is not ObjectArtifactId:
            raise ValueError("INVALID_OBJECT_ARTIFACT_ID") from None
        row = _execute_one(
            self._session,
            select(self._table).where(self._table.c.id == artifact_id.value),
        )
        return None if row is None else _decode_ops_object_artifact(row)

    def add(self, artifact: ObjectArtifact) -> None:
        if type(artifact) is not ObjectArtifact:
            raise ValueError("INVALID_OBJECT_ARTIFACT") from None
        _execute(
            self._session,
            insert(self._table).values(**_encode_ops_object_artifact(artifact)),
        )


@guard_repository_class
class SqlAlchemyRuntimeSettingRepository:
    __slots__ = ("_session", "_table")

    _EDGES = frozenset(
        {
            (
                RuntimeSettingVersionStatus.DRAFT,
                RuntimeSettingVersionStatus.ACTIVE,
            ),
            (
                RuntimeSettingVersionStatus.DRAFT,
                RuntimeSettingVersionStatus.REJECTED,
            ),
            (
                RuntimeSettingVersionStatus.DRAFT,
                RuntimeSettingVersionStatus.RETIRED,
            ),
            (
                RuntimeSettingVersionStatus.ACTIVE,
                RuntimeSettingVersionStatus.RETIRED,
            ),
        }
    )

    def __init__(self, session: Session) -> None:
        if not isinstance(session, Session):
            raise ValueError("INVALID_OPS_REPOSITORY") from None
        self._session = session
        self._table = _table("ops.runtime_setting_version")

    def get_current(
        self, setting_key: str, scope: RuntimeSettingScope
    ) -> RuntimeSettingVersion | None:
        if type(setting_key) is not str or type(scope) is not RuntimeSettingScope:
            raise ValueError("INVALID_RUNTIME_SETTING_LOOKUP") from None
        statement = (
            select(self._table)
            .where(
                self._table.c.setting_key == setting_key,
                self._table.c.scope_type == scope.scope_type.value,
                self._table.c.scope_id.is_not_distinct_from(
                    None if scope.scope_id is None else scope.scope_id.value
                ),
            )
            .order_by(self._table.c.version_no.desc(), self._table.c.id.desc())
            .limit(1)
        )
        row = _execute_one(self._session, statement)
        return (
            None
            if row is None
            else RuntimeSettingVersion(_decode_ops_runtime_setting_version(row))
        )

    def append_version(
        self,
        version: RuntimeSettingVersion,
        expected_latest_version: int | None,
    ) -> AggregateVersion:
        if type(version) is not RuntimeSettingVersion or (
            expected_latest_version is not None
            and (
                type(expected_latest_version) is not int or expected_latest_version < 1
            )
        ):
            raise ValueError("INVALID_RUNTIME_SETTING_APPEND") from None
        lock_runtime_setting_version_series(self._session)
        current = self.get_current(version.state.setting_key, version.state.scope)
        observed = None if current is None else current.state.version_no
        if observed != expected_latest_version:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        if version.state.version_no != (1 if observed is None else observed + 1):
            raise ValueError("INVALID_RUNTIME_SETTING_APPEND") from None
        _execute(
            self._session,
            insert(self._table).values(
                **_encode_ops_runtime_setting_version(version.state)
            ),
        )
        return AggregateVersion(version.state.version_no)

    def transition(
        self,
        version_id: RuntimeSettingVersionId,
        transition: RuntimeSettingVersion,
        expected_status: RuntimeSettingVersionStatus,
    ) -> RuntimeSettingVersion:
        if (
            type(version_id) is not RuntimeSettingVersionId
            or type(transition) is not RuntimeSettingVersion
            or type(expected_status) is not RuntimeSettingVersionStatus
            or transition.state.id != version_id
            or (expected_status, transition.state.status) not in self._EDGES
        ):
            raise ValueError("INVALID_RUNTIME_SETTING_TRANSITION") from None
        current_row = _execute_one(
            self._session,
            select(self._table).where(self._table.c.id == version_id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_ops_runtime_setting_version(current_row)
        if current.status is not expected_status or (
            current.setting_key,
            current.scope_type,
            current.scope_id,
            current.version_no,
            current.setting_class,
            current.value,
            current.value_sha256,
            current.created_by_principal_id,
            current.created_at,
        ) != (
            transition.state.setting_key,
            transition.state.scope_type,
            transition.state.scope_id,
            transition.state.version_no,
            transition.state.setting_class,
            transition.state.value,
            transition.state.value_sha256,
            transition.state.created_by_principal_id,
            transition.state.created_at,
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        conditions = [
            self._table.c.id == version_id.value,
            self._table.c.status == expected_status.value,
        ]
        if expected_status is RuntimeSettingVersionStatus.DRAFT:
            if (
                current.approved_by_principal_id is not None
                or current.approval_reason is not None
            ):
                _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
            conditions.extend(
                (
                    self._table.c.approved_by_principal_id.is_(None),
                    self._table.c.approval_reason.is_(None),
                )
            )
            if transition.state.status is RuntimeSettingVersionStatus.ACTIVE:
                actor_id = persistence_context(self._session).actor.actor_id
                if (
                    actor_id is None
                    or transition.state.approved_by_principal_id is None
                    or transition.state.approved_by_principal_id.value != actor_id
                    or transition.state.approval_reason is None
                    or transition.state.effective_from is None
                    or transition.state.effective_to is not None
                ):
                    _fail(PersistenceErrorCode.STATE_CONFLICT)
                conditions.append(self._table.c.effective_to.is_(None))
                values: dict[str, object] = {
                    "status": RuntimeSettingVersionStatus.ACTIVE.value,
                    "approved_by_principal_id": actor_id,
                    "approval_reason": transition.state.approval_reason,
                    "effective_from": transition.state.effective_from.value,
                    "effective_to": None,
                }
            elif (
                transition.state.approved_by_principal_id
                != current.approved_by_principal_id
                or transition.state.approval_reason != current.approval_reason
                or transition.state.effective_from != current.effective_from
                or transition.state.effective_to != current.effective_to
            ):
                _fail(PersistenceErrorCode.STATE_CONFLICT)
            else:
                values = {"status": transition.state.status.value}
        elif (
            transition.state.approved_by_principal_id
            != current.approved_by_principal_id
            or transition.state.approval_reason != current.approval_reason
            or transition.state.effective_from != current.effective_from
            or transition.state.effective_to is None
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        else:
            conditions.extend(
                (
                    self._table.c.approved_by_principal_id.is_not(None),
                    func.length(func.btrim(self._table.c.approval_reason)) > 0,
                    self._table.c.effective_from.is_not(None),
                    self._table.c.effective_to.is_(None),
                )
            )
            values = {
                "status": RuntimeSettingVersionStatus.RETIRED.value,
                "effective_to": transition.state.effective_to.value,
            }
        statement = (
            update(self._table)
            .where(*conditions)
            .values(**values)
            .returning(self._table)
        )
        row = _execute_one(self._session, statement)
        if row is None:
            observed_row = _execute_one(
                self._session,
                select(self._table).where(self._table.c.id == version_id.value),
            )
            if observed_row is None:
                _fail(PersistenceErrorCode.NOT_FOUND)
            observed = _decode_ops_runtime_setting_version(observed_row)
            if observed.status is not expected_status:
                _fail(PersistenceErrorCode.STATE_CONFLICT)
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        persisted = RuntimeSettingVersion(_decode_ops_runtime_setting_version(row))
        if persisted.state != transition.state:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        return persisted


__all__ = [
    "SqlAlchemyJobRepository",
    "SqlAlchemyObjectArtifactRepository",
    "SqlAlchemyRuntimeSettingRepository",
]

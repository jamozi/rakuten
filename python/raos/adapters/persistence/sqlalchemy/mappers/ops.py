"""Explicit fail-closed scalar mappers for the representative OPS slice.

The ``from_row`` functions deliberately accept only the exact nominal scalar
set recorded in the mapper matrix.  They never accept SQLAlchemy ``Row``
objects, mappings, ORM objects, sessions, or provider values.  The ``to_row``
functions return physical-column-order tuples so repositories remain the only
owner of statement binding.
"""

from __future__ import annotations

from raos.adapters.persistence.sqlalchemy.physical_constraints import (
    install_mapper_physical_constraint_guards,
)
from raos.domain.iam.ids import CreatedByPrincipalId, PrincipalId
from raos.domain.ops.aggregates import (
    AuditEventRecord,
    IdempotencyRecord,
    JobAttempt,
    JobState,
    ObjectArtifact,
    OutboxEventRecord,
    RuntimeSettingVersionState,
)
from raos.domain.ops.enums import (
    AuditEventRecordActorType,
    AuditEventRecordOutcome,
    AuditEventRecordSeverity,
    IdempotencyRecordStatus,
    JobAttemptStatus,
    JobStatus,
    ObjectArtifactArtifactKind,
    ObjectArtifactEncryptionState,
    OutboxEventRecordStatus,
    RuntimeSettingVersionScopeType,
    RuntimeSettingVersionSettingClass,
    RuntimeSettingVersionStatus,
)
from raos.domain.ops.ids import (
    AuditEventId,
    EventId,
    IdempotencyRecordId,
    JobAttemptId,
    JobId,
    ObjectArtifactId,
    RuntimeSettingVersionId,
)
from raos.domain.ops.values import (
    AuditEventRecordDetailsJson,
    IdempotencyRecordResponseBodyJson,
    JobAttemptMetricsJson,
    JobPayloadJson,
    ObjectArtifactMetadataJson,
    OutboxEventRecordPayloadJson,
    RuntimeSettingVersionValueJson,
)
from raos.domain.portfolio.ids import SiteId
from raos.domain.shared.identity import (
    ActorId,
    CausationId,
    CorrelationId,
    OpaqueResourceId,
    ScopeId,
)
from raos.domain.shared.events import require_allowed_outbox_payload
from raos.domain.shared.persistence import AwareUtcDateTime, Sha256Digest
from raos.domain.shared.persistence import AggregateVersion, YenMinor
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode


ObjectArtifactScalars = tuple[
    ObjectArtifactId,
    str,
    ObjectArtifactArtifactKind,
    str,
    str,
    str,
    str | None,
    str,
    int,
    Sha256Digest,
    ObjectArtifactEncryptionState,
    str,
    bool,
    str,
    AwareUtcDateTime | None,
    CreatedByPrincipalId | None,
    ObjectArtifactMetadataJson,
    AwareUtcDateTime,
]
RuntimeSettingVersionScalars = tuple[
    RuntimeSettingVersionId,
    str,
    RuntimeSettingVersionScopeType,
    ScopeId | None,
    int,
    RuntimeSettingVersionSettingClass,
    RuntimeSettingVersionValueJson,
    Sha256Digest,
    RuntimeSettingVersionStatus,
    AwareUtcDateTime | None,
    AwareUtcDateTime | None,
    PrincipalId,
    PrincipalId | None,
    str | None,
    AwareUtcDateTime,
]
AuditEventScalars = tuple[
    AuditEventId,
    AwareUtcDateTime,
    AuditEventRecordActorType,
    ActorId | None,
    str,
    str,
    OpaqueResourceId | None,
    AuditEventRecordOutcome,
    AuditEventRecordSeverity,
    CorrelationId,
    str | None,
    Sha256Digest | None,
    Sha256Digest | None,
    AuditEventRecordDetailsJson,
    AwareUtcDateTime,
]
OutboxEventScalars = tuple[
    EventId,
    str,
    int,
    str,
    str,
    OpaqueResourceId,
    int,
    CorrelationId,
    CausationId | None,
    str,
    ActorId | None,
    OutboxEventRecordPayloadJson,
    Sha256Digest,
    OutboxEventRecordStatus,
    AwareUtcDateTime,
    AwareUtcDateTime | None,
    int,
    str | None,
    AwareUtcDateTime,
]
IdempotencyRecordScalars = tuple[
    IdempotencyRecordId,
    str,
    str,
    str,
    Sha256Digest,
    IdempotencyRecordStatus,
    int | None,
    IdempotencyRecordResponseBodyJson | None,
    ObjectArtifactId | None,
    str | None,
    OpaqueResourceId | None,
    AwareUtcDateTime,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
]


def _corrupt() -> PersistenceError:
    return PersistenceError(PersistenceErrorCode.STORAGE_CORRUPTION)


def map_ops_object_artifact_from_row(
    *,
    id: ObjectArtifactId,
    display_id: str,
    artifact_kind: ObjectArtifactArtifactKind,
    storage_provider: str,
    bucket_name: str,
    object_key: str,
    object_version: str | None,
    content_type: str,
    byte_size: int,
    sha256: Sha256Digest,
    encryption_state: ObjectArtifactEncryptionState,
    retention_class: str,
    is_immutable: bool,
    source_system: str,
    acquired_at: AwareUtcDateTime | None,
    created_by_principal_id: CreatedByPrincipalId | None,
    metadata: ObjectArtifactMetadataJson,
    created_at: AwareUtcDateTime,
) -> ObjectArtifact:
    try:
        return ObjectArtifact(
            id=id,
            display_id=display_id,
            artifact_kind=artifact_kind,
            storage_provider=storage_provider,
            bucket_name=bucket_name,
            object_key=object_key,
            object_version=object_version,
            content_type=content_type,
            byte_size=byte_size,
            sha256=sha256,
            encryption_state=encryption_state,
            retention_class=retention_class,
            is_immutable=is_immutable,
            source_system=source_system,
            acquired_at=acquired_at,
            created_by_principal_id=created_by_principal_id,
            metadata=metadata,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ops_object_artifact_to_row(value: ObjectArtifact) -> ObjectArtifactScalars:
    if type(value) is not ObjectArtifact:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.artifact_kind,
        value.storage_provider,
        value.bucket_name,
        value.object_key,
        value.object_version,
        value.content_type,
        value.byte_size,
        value.sha256,
        value.encryption_state,
        value.retention_class,
        value.is_immutable,
        value.source_system,
        value.acquired_at,
        value.created_by_principal_id,
        value.metadata,
        value.created_at,
    )


def map_ops_runtime_setting_version_from_row(
    *,
    id: RuntimeSettingVersionId,
    setting_key: str,
    scope_type: RuntimeSettingVersionScopeType,
    scope_id: ScopeId | None,
    version_no: int,
    setting_class: RuntimeSettingVersionSettingClass,
    value: RuntimeSettingVersionValueJson,
    value_sha256: Sha256Digest,
    status: RuntimeSettingVersionStatus,
    effective_from: AwareUtcDateTime | None,
    effective_to: AwareUtcDateTime | None,
    created_by_principal_id: PrincipalId,
    approved_by_principal_id: PrincipalId | None,
    approval_reason: str | None,
    created_at: AwareUtcDateTime,
) -> RuntimeSettingVersionState:
    try:
        return RuntimeSettingVersionState(
            id=id,
            setting_key=setting_key,
            scope_type=scope_type,
            scope_id=scope_id,
            version_no=version_no,
            setting_class=setting_class,
            value=value,
            value_sha256=value_sha256,
            status=status,
            effective_from=effective_from,
            effective_to=effective_to,
            created_by_principal_id=created_by_principal_id,
            approved_by_principal_id=approved_by_principal_id,
            approval_reason=approval_reason,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ops_runtime_setting_version_to_row(
    value: RuntimeSettingVersionState,
) -> RuntimeSettingVersionScalars:
    if type(value) is not RuntimeSettingVersionState:
        raise _corrupt() from None
    return (
        value.id,
        value.setting_key,
        value.scope_type,
        value.scope_id,
        value.version_no,
        value.setting_class,
        value.value,
        value.value_sha256,
        value.status,
        value.effective_from,
        value.effective_to,
        value.created_by_principal_id,
        value.approved_by_principal_id,
        value.approval_reason,
        value.created_at,
    )


def map_ops_audit_event_from_row(
    *,
    id: AuditEventId,
    occurred_at: AwareUtcDateTime,
    actor_type: AuditEventRecordActorType,
    actor_id: ActorId | None,
    action: str,
    target_type: str,
    target_id: OpaqueResourceId | None,
    outcome: AuditEventRecordOutcome,
    severity: AuditEventRecordSeverity,
    correlation_id: CorrelationId,
    request_id: str | None,
    before_hash: Sha256Digest | None,
    after_hash: Sha256Digest | None,
    details: AuditEventRecordDetailsJson,
    created_at: AwareUtcDateTime,
) -> AuditEventRecord:
    try:
        return AuditEventRecord(
            id=id,
            occurred_at=occurred_at,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            outcome=outcome,
            severity=severity,
            correlation_id=correlation_id,
            request_id=request_id,
            before_hash=before_hash,
            after_hash=after_hash,
            details=details,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ops_audit_event_to_row(value: AuditEventRecord) -> AuditEventScalars:
    if type(value) is not AuditEventRecord:
        raise _corrupt() from None
    return (
        value.id,
        value.occurred_at,
        value.actor_type,
        value.actor_id,
        value.action,
        value.target_type,
        value.target_id,
        value.outcome,
        value.severity,
        value.correlation_id,
        value.request_id,
        value.before_hash,
        value.after_hash,
        value.details,
        value.created_at,
    )


def map_ops_outbox_event_from_row(
    *,
    id: EventId,
    event_type: str,
    event_version: int,
    producer: str,
    aggregate_type: str,
    aggregate_id: OpaqueResourceId,
    aggregate_version: int,
    correlation_id: CorrelationId,
    causation_id: CausationId | None,
    actor_type: str,
    actor_id: ActorId | None,
    payload: OutboxEventRecordPayloadJson,
    payload_schema_hash: Sha256Digest,
    status: OutboxEventRecordStatus,
    available_at: AwareUtcDateTime,
    published_at: AwareUtcDateTime | None,
    publish_attempts: int,
    last_error: str | None,
    created_at: AwareUtcDateTime,
) -> OutboxEventRecord:
    try:
        require_allowed_outbox_payload(
            event_type=event_type,
            event_version=event_version,
            producer=producer,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id.value,
            schema_sha256=payload_schema_hash.value,
            payload=payload.value,
        )
        return OutboxEventRecord(
            id=id,
            event_type=event_type,
            event_version=event_version,
            producer=producer,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_version=aggregate_version,
            correlation_id=correlation_id,
            causation_id=causation_id,
            actor_type=actor_type,
            actor_id=actor_id,
            payload=payload,
            payload_schema_hash=payload_schema_hash,
            status=status,
            available_at=available_at,
            published_at=published_at,
            publish_attempts=publish_attempts,
            last_error=last_error,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ops_outbox_event_to_row(value: OutboxEventRecord) -> OutboxEventScalars:
    if type(value) is not OutboxEventRecord:
        raise _corrupt() from None
    return (
        value.id,
        value.event_type,
        value.event_version,
        value.producer,
        value.aggregate_type,
        value.aggregate_id,
        value.aggregate_version,
        value.correlation_id,
        value.causation_id,
        value.actor_type,
        value.actor_id,
        value.payload,
        value.payload_schema_hash,
        value.status,
        value.available_at,
        value.published_at,
        value.publish_attempts,
        value.last_error,
        value.created_at,
    )


def map_ops_idempotency_record_from_row(
    *,
    id: IdempotencyRecordId,
    actor_fingerprint: str,
    route_key: str,
    idempotency_key: str,
    request_hash: Sha256Digest,
    status: IdempotencyRecordStatus,
    response_status: int | None,
    response_body: IdempotencyRecordResponseBodyJson | None,
    response_artifact_id: ObjectArtifactId | None,
    resource_type: str | None,
    resource_id: OpaqueResourceId | None,
    expires_at: AwareUtcDateTime,
    completed_at: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
) -> IdempotencyRecord:
    try:
        return IdempotencyRecord(
            id=id,
            actor_fingerprint=actor_fingerprint,
            route_key=route_key,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            status=status,
            response_status=response_status,
            response_body=response_body,
            response_artifact_id=response_artifact_id,
            resource_type=resource_type,
            resource_id=resource_id,
            expires_at=expires_at,
            completed_at=completed_at,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ops_idempotency_record_to_row(
    value: IdempotencyRecord,
) -> IdempotencyRecordScalars:
    if type(value) is not IdempotencyRecord:
        raise _corrupt() from None
    return (
        value.id,
        value.actor_fingerprint,
        value.route_key,
        value.idempotency_key,
        value.request_hash,
        value.status,
        value.response_status,
        value.response_body,
        value.response_artifact_id,
        value.resource_type,
        value.resource_id,
        value.expires_at,
        value.completed_at,
        value.created_at,
    )


JobStateScalars = tuple[
    JobId,
    str,
    str,
    str,
    JobStatus,
    int,
    str | None,
    SiteId | None,
    str | None,
    OpaqueResourceId | None,
    JobPayloadJson,
    ObjectArtifactId | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
    AwareUtcDateTime | None,
    AwareUtcDateTime | None,
    int,
    int,
    str | None,
    AwareUtcDateTime | None,
    CorrelationId,
    CausationId | None,
    JobId | None,
    YenMinor | None,
    str,
    ActorId | None,
    str | None,
    str | None,
    str | None,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AggregateVersion,
    int,
    AwareUtcDateTime | None,
    AwareUtcDateTime | None,
]


def map_ops_job_from_row(
    *,
    id: JobId,
    display_id: str,
    job_type: str,
    queue_name: str,
    status: JobStatus,
    priority: int,
    idempotency_key: str | None,
    site_id: SiteId | None,
    aggregate_type: str | None,
    aggregate_id: OpaqueResourceId | None,
    payload: JobPayloadJson,
    payload_artifact_id: ObjectArtifactId | None,
    scheduled_at: AwareUtcDateTime | None,
    available_at: AwareUtcDateTime,
    started_at: AwareUtcDateTime | None,
    completed_at: AwareUtcDateTime | None,
    max_attempts: int,
    attempt_count: int,
    lease_owner: str | None,
    lease_expires_at: AwareUtcDateTime | None,
    correlation_id: CorrelationId,
    causation_id: CausationId | None,
    parent_job_id: JobId | None,
    budget_jpy: YenMinor | None,
    created_by_actor_type: str,
    created_by_actor_id: ActorId | None,
    last_error_class: str | None,
    last_error_code: str | None,
    last_error_message: str | None,
    created_at: AwareUtcDateTime,
    updated_at: AwareUtcDateTime,
    lock_version: AggregateVersion,
    job_version: int,
    deadline_at: AwareUtcDateTime | None,
    cancel_requested_at: AwareUtcDateTime | None,
) -> JobState:
    try:
        return JobState(
            id=id,
            display_id=display_id,
            job_type=job_type,
            queue_name=queue_name,
            status=status,
            priority=priority,
            idempotency_key=idempotency_key,
            site_id=site_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
            payload_artifact_id=payload_artifact_id,
            scheduled_at=scheduled_at,
            available_at=available_at,
            started_at=started_at,
            completed_at=completed_at,
            max_attempts=max_attempts,
            attempt_count=attempt_count,
            lease_owner=lease_owner,
            lease_expires_at=lease_expires_at,
            correlation_id=correlation_id,
            causation_id=causation_id,
            parent_job_id=parent_job_id,
            budget_jpy=budget_jpy,
            created_by_actor_type=created_by_actor_type,
            created_by_actor_id=created_by_actor_id,
            last_error_class=last_error_class,
            last_error_code=last_error_code,
            last_error_message=last_error_message,
            created_at=created_at,
            updated_at=updated_at,
            lock_version=lock_version,
            job_version=job_version,
            deadline_at=deadline_at,
            cancel_requested_at=cancel_requested_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ops_job_to_row(value: JobState) -> JobStateScalars:
    if type(value) is not JobState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.job_type,
        value.queue_name,
        value.status,
        value.priority,
        value.idempotency_key,
        value.site_id,
        value.aggregate_type,
        value.aggregate_id,
        value.payload,
        value.payload_artifact_id,
        value.scheduled_at,
        value.available_at,
        value.started_at,
        value.completed_at,
        value.max_attempts,
        value.attempt_count,
        value.lease_owner,
        value.lease_expires_at,
        value.correlation_id,
        value.causation_id,
        value.parent_job_id,
        value.budget_jpy,
        value.created_by_actor_type,
        value.created_by_actor_id,
        value.last_error_class,
        value.last_error_code,
        value.last_error_message,
        value.created_at,
        value.updated_at,
        value.lock_version,
        value.job_version,
        value.deadline_at,
        value.cancel_requested_at,
    )


JobAttemptScalars = tuple[
    JobAttemptId,
    JobId,
    int,
    JobAttemptStatus,
    str,
    str,
    AwareUtcDateTime,
    AwareUtcDateTime | None,
    str | None,
    ObjectArtifactId | None,
    ObjectArtifactId | None,
    str | None,
    str | None,
    str | None,
    AwareUtcDateTime | None,
    JobAttemptMetricsJson,
    AwareUtcDateTime,
]


def map_ops_job_attempt_from_row(
    *,
    id: JobAttemptId,
    job_id: JobId,
    attempt_no: int,
    status: JobAttemptStatus,
    worker_id: str,
    handler_version: str,
    started_at: AwareUtcDateTime,
    completed_at: AwareUtcDateTime | None,
    provider_request_id: str | None,
    input_artifact_id: ObjectArtifactId | None,
    output_artifact_id: ObjectArtifactId | None,
    error_class: str | None,
    error_code: str | None,
    error_message: str | None,
    retry_after_at: AwareUtcDateTime | None,
    metrics: JobAttemptMetricsJson,
    created_at: AwareUtcDateTime,
) -> JobAttempt:
    try:
        return JobAttempt(
            id=id,
            job_id=job_id,
            attempt_no=attempt_no,
            status=status,
            worker_id=worker_id,
            handler_version=handler_version,
            started_at=started_at,
            completed_at=completed_at,
            provider_request_id=provider_request_id,
            input_artifact_id=input_artifact_id,
            output_artifact_id=output_artifact_id,
            error_class=error_class,
            error_code=error_code,
            error_message=error_message,
            retry_after_at=retry_after_at,
            metrics=metrics,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ops_job_attempt_to_row(value: JobAttempt) -> JobAttemptScalars:
    if type(value) is not JobAttempt:
        raise _corrupt() from None
    return (
        value.id,
        value.job_id,
        value.attempt_no,
        value.status,
        value.worker_id,
        value.handler_version,
        value.started_at,
        value.completed_at,
        value.provider_request_id,
        value.input_artifact_id,
        value.output_artifact_id,
        value.error_class,
        value.error_code,
        value.error_message,
        value.retry_after_at,
        value.metrics,
        value.created_at,
    )


__all__ = [
    "JobStateScalars",
    "map_ops_job_from_row",
    "map_ops_job_to_row",
    "JobAttemptScalars",
    "map_ops_job_attempt_from_row",
    "map_ops_job_attempt_to_row",
    "AuditEventScalars",
    "IdempotencyRecordScalars",
    "ObjectArtifactScalars",
    "OutboxEventScalars",
    "RuntimeSettingVersionScalars",
    "map_ops_audit_event_from_row",
    "map_ops_audit_event_to_row",
    "map_ops_idempotency_record_from_row",
    "map_ops_idempotency_record_to_row",
    "map_ops_object_artifact_from_row",
    "map_ops_object_artifact_to_row",
    "map_ops_outbox_event_from_row",
    "map_ops_outbox_event_to_row",
    "map_ops_runtime_setting_version_from_row",
    "map_ops_runtime_setting_version_to_row",
]

install_mapper_physical_constraint_guards(globals())

"""Representative OPS aggregates selected by the ST-0308 mapper matrix."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from typing import NoReturn
import unicodedata
from uuid import UUID

from raos.domain.iam.ids import CreatedByPrincipalId, PrincipalId
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
from raos.domain.shared.events import (
    DomainEvent,
    require_allowed_outbox_metadata,
    require_allowed_outbox_payload,
)
from raos.domain.shared.json_values import canonical_json_bytes
from raos.domain.shared.persistence import (
    AggregateVersion,
    AwareUtcDateTime,
    PendingEventBuffer,
    Sha256Digest,
    YenMinor,
)


_DISPLAY_ID = re.compile(r"[A-Z][A-Z0-9]{1,15}-[A-Z0-9][A-Z0-9_-]{0,62}\Z", re.ASCII)
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+-]{0,254}\Z", re.ASCII)
_HASH = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_MAX_BIGINT = (1 << 63) - 1


def _invalid() -> NoReturn:
    raise ValueError("INVALID_OPS_PERSISTENCE_VALUE") from None


def _text(value: object, *, maximum: int = 1024, token: bool = False) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or unicodedata.normalize("NFC", value) != value
        or any(unicodedata.category(character).startswith("C") for character in value)
        or (token and _TOKEN.fullmatch(value) is None)
    ):
        _invalid()
    return value


def _optional_text(value: object, *, maximum: int = 1024) -> str | None:
    if value is None:
        return None
    return _text(value, maximum=maximum)


def _integer(value: object, *, minimum: int = 0, maximum: int = _MAX_BIGINT) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _invalid()
    return value


@dataclass(frozen=True, slots=True, repr=False)
class ObjectArtifact:
    id: ObjectArtifactId
    display_id: str
    artifact_kind: ObjectArtifactArtifactKind
    storage_provider: str
    bucket_name: str
    object_key: str
    object_version: str | None
    content_type: str
    byte_size: int
    sha256: Sha256Digest
    encryption_state: ObjectArtifactEncryptionState
    retention_class: str
    is_immutable: bool
    source_system: str
    acquired_at: AwareUtcDateTime | None
    created_by_principal_id: CreatedByPrincipalId | None
    metadata: ObjectArtifactMetadataJson
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if (
            type(self.id) is not ObjectArtifactId
            or type(self.display_id) is not str
            or _DISPLAY_ID.fullmatch(self.display_id) is None
            or type(self.artifact_kind) is not ObjectArtifactArtifactKind
            or type(self.encryption_state) is not ObjectArtifactEncryptionState
            or type(self.sha256) is not Sha256Digest
            or self.is_immutable is not True
            or (
                self.acquired_at is not None
                and type(self.acquired_at) is not AwareUtcDateTime
            )
            or (
                self.created_by_principal_id is not None
                and type(self.created_by_principal_id) is not CreatedByPrincipalId
            )
            or type(self.metadata) is not ObjectArtifactMetadataJson
            or type(self.created_at) is not AwareUtcDateTime
        ):
            _invalid()
        _text(self.storage_provider, maximum=64, token=True)
        _text(self.bucket_name, maximum=255)
        _text(self.object_key, maximum=2048)
        _optional_text(self.object_version, maximum=1024)
        _text(self.content_type, maximum=255)
        _integer(self.byte_size)
        _text(self.retention_class, maximum=128, token=True)
        _text(self.source_system, maximum=128, token=True)

    def __repr__(self) -> str:
        return "ObjectArtifact(<redacted>)"


@dataclass(frozen=True, slots=True)
class RuntimeSettingScope:
    scope_type: RuntimeSettingVersionScopeType
    scope_id: ScopeId | None

    def __post_init__(self) -> None:
        if type(self.scope_type) is not RuntimeSettingVersionScopeType:
            _invalid()
        if self.scope_type is RuntimeSettingVersionScopeType.GLOBAL:
            if self.scope_id is not None:
                _invalid()
        elif type(self.scope_id) is not ScopeId:
            _invalid()


@dataclass(frozen=True, slots=True, repr=False)
class RuntimeSettingVersionState:
    id: RuntimeSettingVersionId
    setting_key: str
    scope_type: RuntimeSettingVersionScopeType
    scope_id: ScopeId | None
    version_no: int
    setting_class: RuntimeSettingVersionSettingClass
    value: RuntimeSettingVersionValueJson
    value_sha256: Sha256Digest
    status: RuntimeSettingVersionStatus
    effective_from: AwareUtcDateTime | None
    effective_to: AwareUtcDateTime | None
    created_by_principal_id: PrincipalId
    approved_by_principal_id: PrincipalId | None
    approval_reason: str | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if (
            type(self.id) is not RuntimeSettingVersionId
            or type(self.scope_type) is not RuntimeSettingVersionScopeType
            or type(self.setting_class) is not RuntimeSettingVersionSettingClass
            or type(self.value) is not RuntimeSettingVersionValueJson
            or type(self.value_sha256) is not Sha256Digest
            or type(self.status) is not RuntimeSettingVersionStatus
            or (
                self.effective_from is not None
                and type(self.effective_from) is not AwareUtcDateTime
            )
            or (
                self.effective_to is not None
                and type(self.effective_to) is not AwareUtcDateTime
            )
            or type(self.created_by_principal_id) is not PrincipalId
            or (
                self.approved_by_principal_id is not None
                and type(self.approved_by_principal_id) is not PrincipalId
            )
            or type(self.created_at) is not AwareUtcDateTime
        ):
            _invalid()
        _text(self.setting_key, maximum=255, token=True)
        RuntimeSettingScope(self.scope_type, self.scope_id)
        _integer(self.version_no, minimum=1, maximum=(1 << 31) - 1)
        expected_hash = hashlib.sha256(
            canonical_json_bytes(self.value.value)
        ).hexdigest()
        if expected_hash != self.value_sha256.value:
            _invalid()
        reason = _optional_text(self.approval_reason, maximum=2048)
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_to.value <= self.effective_from.value
        ):
            _invalid()
        if self.status is RuntimeSettingVersionStatus.ACTIVE:
            if (
                self.approved_by_principal_id is None
                or reason is None
                or self.effective_from is None
                or self.effective_to is not None
            ):
                _invalid()
        elif self.status in {
            RuntimeSettingVersionStatus.DRAFT,
            RuntimeSettingVersionStatus.REJECTED,
        }:
            if (
                self.approved_by_principal_id is not None
                or reason is not None
                or self.effective_to is not None
            ):
                _invalid()
        elif self.approved_by_principal_id is None:
            if reason is not None or self.effective_to is not None:
                _invalid()
        elif reason is None or self.effective_from is None or self.effective_to is None:
            _invalid()

    @property
    def scope(self) -> RuntimeSettingScope:
        return RuntimeSettingScope(self.scope_type, self.scope_id)

    def __repr__(self) -> str:
        return "RuntimeSettingVersionState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class RuntimeSettingVersion:
    state: RuntimeSettingVersionState

    def __post_init__(self) -> None:
        if type(self.state) is not RuntimeSettingVersionState:
            _invalid()

    def __repr__(self) -> str:
        return "RuntimeSettingVersion(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class AuditEventRecord:
    id: AuditEventId
    occurred_at: AwareUtcDateTime
    actor_type: AuditEventRecordActorType
    actor_id: ActorId | None
    action: str
    target_type: str
    target_id: OpaqueResourceId | None
    outcome: AuditEventRecordOutcome
    severity: AuditEventRecordSeverity
    correlation_id: CorrelationId
    request_id: str | None
    before_hash: Sha256Digest | None
    after_hash: Sha256Digest | None
    details: AuditEventRecordDetailsJson
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if (
            type(self.id) is not AuditEventId
            or type(self.occurred_at) is not AwareUtcDateTime
            or type(self.actor_type) is not AuditEventRecordActorType
            or (self.actor_id is not None and type(self.actor_id) is not ActorId)
            or (
                self.target_id is not None
                and type(self.target_id) is not OpaqueResourceId
            )
            or type(self.outcome) is not AuditEventRecordOutcome
            or type(self.severity) is not AuditEventRecordSeverity
            or type(self.correlation_id) is not CorrelationId
            or (
                self.before_hash is not None
                and type(self.before_hash) is not Sha256Digest
            )
            or (
                self.after_hash is not None
                and type(self.after_hash) is not Sha256Digest
            )
            or type(self.details) is not AuditEventRecordDetailsJson
            or type(self.created_at) is not AwareUtcDateTime
        ):
            _invalid()
        _text(self.action, maximum=127, token=True)
        _text(self.target_type, maximum=127, token=True)
        _optional_text(self.request_id, maximum=255)

    def __repr__(self) -> str:
        return "AuditEventRecord(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class OutboxEventRecord:
    id: EventId
    event_type: str
    event_version: int
    producer: str
    aggregate_type: str
    aggregate_id: OpaqueResourceId
    aggregate_version: int
    correlation_id: CorrelationId
    causation_id: CausationId | None
    actor_type: str
    actor_id: ActorId | None
    payload: OutboxEventRecordPayloadJson
    payload_schema_hash: Sha256Digest
    status: OutboxEventRecordStatus
    available_at: AwareUtcDateTime
    published_at: AwareUtcDateTime | None
    publish_attempts: int
    last_error: str | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if (
            type(self.id) is not EventId
            or type(self.aggregate_id) is not OpaqueResourceId
            or type(self.correlation_id) is not CorrelationId
            or (
                self.causation_id is not None
                and type(self.causation_id) is not CausationId
            )
            or (self.actor_id is not None and type(self.actor_id) is not ActorId)
            or type(self.payload) is not OutboxEventRecordPayloadJson
            or type(self.payload_schema_hash) is not Sha256Digest
            or type(self.status) is not OutboxEventRecordStatus
            or type(self.available_at) is not AwareUtcDateTime
            or (
                self.published_at is not None
                and type(self.published_at) is not AwareUtcDateTime
            )
            or type(self.created_at) is not AwareUtcDateTime
        ):
            _invalid()
        _text(self.event_type, maximum=255, token=True)
        _integer(self.event_version, minimum=1, maximum=(1 << 31) - 1)
        _text(self.producer, maximum=127, token=True)
        _text(self.aggregate_type, maximum=127, token=True)
        try:
            require_allowed_outbox_metadata(
                event_type=self.event_type,
                event_version=self.event_version,
                producer=self.producer,
                aggregate_type=self.aggregate_type,
                schema_sha256=self.payload_schema_hash.value,
            )
            require_allowed_outbox_payload(
                event_type=self.event_type,
                event_version=self.event_version,
                producer=self.producer,
                aggregate_type=self.aggregate_type,
                aggregate_id=self.aggregate_id.value,
                schema_sha256=self.payload_schema_hash.value,
                payload=self.payload.value,
            )
        except ValueError:
            _invalid()
        _integer(self.aggregate_version)
        if self.actor_type not in {
            "USER",
            "SERVICE",
            "SCHEDULE",
            "SYSTEM",
            "ANONYMOUS",
        }:
            _invalid()
        _integer(self.publish_attempts, maximum=(1 << 15) - 1)
        _optional_text(self.last_error, maximum=2048)
        if (
            self.status is OutboxEventRecordStatus.PUBLISHED
            and self.published_at is None
        ):
            _invalid()

    def __repr__(self) -> str:
        return "OutboxEventRecord(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class IdempotencyRecord:
    id: IdempotencyRecordId
    actor_fingerprint: str
    route_key: str
    idempotency_key: str
    request_hash: Sha256Digest
    status: IdempotencyRecordStatus
    response_status: int | None
    response_body: IdempotencyRecordResponseBodyJson | None
    response_artifact_id: ObjectArtifactId | None
    resource_type: str | None
    resource_id: OpaqueResourceId | None
    expires_at: AwareUtcDateTime
    completed_at: AwareUtcDateTime | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if (
            type(self.id) is not IdempotencyRecordId
            or _HASH.fullmatch(self.actor_fingerprint) is None
            or type(self.request_hash) is not Sha256Digest
            or type(self.status) is not IdempotencyRecordStatus
            or (
                self.response_body is not None
                and type(self.response_body) is not IdempotencyRecordResponseBodyJson
            )
            or (
                self.response_artifact_id is not None
                and type(self.response_artifact_id) is not ObjectArtifactId
            )
            or (
                self.resource_id is not None
                and type(self.resource_id) is not OpaqueResourceId
            )
            or type(self.expires_at) is not AwareUtcDateTime
            or (
                self.completed_at is not None
                and type(self.completed_at) is not AwareUtcDateTime
            )
            or type(self.created_at) is not AwareUtcDateTime
            or self.expires_at.value <= self.created_at.value
        ):
            _invalid()
        _text(self.route_key, maximum=200)
        _text(self.idempotency_key, maximum=200)
        if (self.response_body is None) == (self.response_artifact_id is None):
            if self.response_body is not None:
                _invalid()
        if (self.resource_type is None) != (self.resource_id is None):
            _invalid()
        if self.resource_type is not None:
            _text(self.resource_type, maximum=64, token=True)
        if self.status is IdempotencyRecordStatus.IN_PROGRESS:
            if any(
                value is not None
                for value in (
                    self.response_status,
                    self.response_body,
                    self.response_artifact_id,
                    self.resource_type,
                    self.resource_id,
                    self.completed_at,
                )
            ):
                _invalid()
        elif (
            type(self.response_status) is not int
            or not 100 <= self.response_status <= 599
            or self.completed_at is None
        ):
            _invalid()

    def __repr__(self) -> str:
        return "IdempotencyRecord(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class JobState:
    id: JobId
    display_id: str
    job_type: str
    queue_name: str
    status: JobStatus
    priority: int
    idempotency_key: str | None
    site_id: SiteId | None
    aggregate_type: str | None
    aggregate_id: OpaqueResourceId | None
    payload: JobPayloadJson
    payload_artifact_id: ObjectArtifactId | None
    scheduled_at: AwareUtcDateTime | None
    available_at: AwareUtcDateTime
    started_at: AwareUtcDateTime | None
    completed_at: AwareUtcDateTime | None
    max_attempts: int
    attempt_count: int
    lease_owner: str | None
    lease_expires_at: AwareUtcDateTime | None
    correlation_id: CorrelationId
    causation_id: CausationId | None
    parent_job_id: JobId | None
    budget_jpy: YenMinor | None
    created_by_actor_type: str
    created_by_actor_id: ActorId | None
    last_error_class: str | None
    last_error_code: str | None
    last_error_message: str | None
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    lock_version: AggregateVersion
    job_version: int
    deadline_at: AwareUtcDateTime | None
    cancel_requested_at: AwareUtcDateTime | None

    def __post_init__(self) -> None:
        if (
            type(self.id) is not JobId
            or type(self.status) is not JobStatus
            or (self.site_id is not None and type(self.site_id) is not SiteId)
            or (
                self.aggregate_id is not None
                and type(self.aggregate_id) is not OpaqueResourceId
            )
            or type(self.payload) is not JobPayloadJson
            or (
                self.payload_artifact_id is not None
                and type(self.payload_artifact_id) is not ObjectArtifactId
            )
            or type(self.available_at) is not AwareUtcDateTime
            or type(self.correlation_id) is not CorrelationId
            or (
                self.causation_id is not None
                and type(self.causation_id) is not CausationId
            )
            or (
                self.parent_job_id is not None and type(self.parent_job_id) is not JobId
            )
            or (self.budget_jpy is not None and type(self.budget_jpy) is not YenMinor)
            or (
                self.created_by_actor_id is not None
                and type(self.created_by_actor_id) is not ActorId
            )
            or type(self.created_at) is not AwareUtcDateTime
            or type(self.updated_at) is not AwareUtcDateTime
            or type(self.lock_version) is not AggregateVersion
        ):
            _invalid()
        for optional_time in (
            self.scheduled_at,
            self.started_at,
            self.completed_at,
            self.lease_expires_at,
            self.deadline_at,
            self.cancel_requested_at,
        ):
            if (
                optional_time is not None
                and type(optional_time) is not AwareUtcDateTime
            ):
                _invalid()
        if (self.aggregate_type is None) != (self.aggregate_id is None):
            _invalid()
        _text(self.display_id, maximum=80)
        _text(self.job_type, maximum=127, token=True)
        _text(self.queue_name, maximum=127, token=True)
        _text(self.created_by_actor_type, maximum=32, token=True)
        for optional_text in (
            self.idempotency_key,
            self.aggregate_type,
            self.lease_owner,
            self.last_error_class,
            self.last_error_code,
            self.last_error_message,
        ):
            _optional_text(optional_text, maximum=1024)
        _integer(self.priority, maximum=(1 << 15) - 1)
        _integer(self.max_attempts, minimum=1, maximum=(1 << 15) - 1)
        _integer(self.attempt_count, maximum=(1 << 15) - 1)
        _integer(self.job_version, minimum=1, maximum=(1 << 31) - 1)
        if self.attempt_count > self.max_attempts:
            _invalid()

    def __repr__(self) -> str:
        return "JobState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class JobAttempt:
    id: JobAttemptId
    job_id: JobId
    attempt_no: int
    status: JobAttemptStatus
    worker_id: str
    handler_version: str
    started_at: AwareUtcDateTime
    completed_at: AwareUtcDateTime | None
    provider_request_id: str | None
    input_artifact_id: ObjectArtifactId | None
    output_artifact_id: ObjectArtifactId | None
    error_class: str | None
    error_code: str | None
    error_message: str | None
    retry_after_at: AwareUtcDateTime | None
    metrics: JobAttemptMetricsJson
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if (
            type(self.id) is not JobAttemptId
            or type(self.job_id) is not JobId
            or type(self.status) is not JobAttemptStatus
            or type(self.started_at) is not AwareUtcDateTime
            or (
                self.completed_at is not None
                and type(self.completed_at) is not AwareUtcDateTime
            )
            or (
                self.input_artifact_id is not None
                and type(self.input_artifact_id) is not ObjectArtifactId
            )
            or (
                self.output_artifact_id is not None
                and type(self.output_artifact_id) is not ObjectArtifactId
            )
            or (
                self.retry_after_at is not None
                and type(self.retry_after_at) is not AwareUtcDateTime
            )
            or type(self.metrics) is not JobAttemptMetricsJson
            or type(self.created_at) is not AwareUtcDateTime
        ):
            _invalid()
        _integer(self.attempt_no, minimum=1, maximum=(1 << 15) - 1)
        _text(self.worker_id, maximum=255)
        _text(self.handler_version, maximum=255)
        for value in (
            self.provider_request_id,
            self.error_class,
            self.error_code,
            self.error_message,
        ):
            _optional_text(value, maximum=1024)
        if self.status is JobAttemptStatus.RUNNING:
            if self.completed_at is not None:
                _invalid()
        elif self.completed_at is None:
            _invalid()

    def __repr__(self) -> str:
        return "JobAttempt(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class Job:
    state: JobState
    job_attempt_rows: tuple[JobAttempt, ...] = ()
    _event_buffer: PendingEventBuffer[DomainEvent] = field(
        default_factory=PendingEventBuffer[DomainEvent],
        init=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if (
            type(self.state) is not JobState
            or type(self.job_attempt_rows) is not tuple
            or any(type(row) is not JobAttempt for row in self.job_attempt_rows)
            or any(
                row.job_id.value != self.state.id.value for row in self.job_attempt_rows
            )
        ):
            _invalid()

    def pending_events(self) -> tuple[DomainEvent, ...]:
        return self._event_buffer.pending_events()

    def acknowledge_events(self, event_ids: tuple[UUID, ...]) -> None:
        if type(event_ids) is not tuple or any(
            type(event_id) is not UUID for event_id in event_ids
        ):
            _invalid()
        self._event_buffer.acknowledge_events(event_ids)

    def _record_event(self, event: DomainEvent) -> None:
        self._event_buffer.record(event)

    def _restore_acknowledged_events(self) -> None:
        self._event_buffer.restore_acknowledged()

    def _finish_acknowledged_events(self) -> None:
        self._event_buffer.finish_acknowledged()

    def __repr__(self) -> str:
        return "Job(<redacted>)"


__all__ = [
    "AuditEventRecord",
    "IdempotencyRecord",
    "Job",
    "JobAttempt",
    "JobState",
    "ObjectArtifact",
    "OutboxEventRecord",
    "RuntimeSettingScope",
    "RuntimeSettingVersion",
    "RuntimeSettingVersionState",
]

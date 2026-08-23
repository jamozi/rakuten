"""Closed physical enums for the ST-0308 OPS persistence slice."""

from enum import Enum


class AuditEventRecordActorType(str, Enum):
    USER = "USER"
    SERVICE = "SERVICE"
    SCHEDULE = "SCHEDULE"
    SYSTEM = "SYSTEM"
    ANONYMOUS = "ANONYMOUS"


class AuditEventRecordOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    DENIED = "DENIED"
    FAILED = "FAILED"
    NOOP = "NOOP"


class AuditEventRecordSeverity(str, Enum):
    INFO = "INFO"
    NOTICE = "NOTICE"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class IdempotencyRecordStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class JobStatus(str, Enum):
    REQUESTED = "REQUESTED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    QUARANTINED = "QUARANTINED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class JobAttemptStatus(str, Enum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


class ObjectArtifactArtifactKind(str, Enum):
    RAW_PROVIDER_RESPONSE = "raw_provider_response"
    RAW_PRIMARY_SOURCE = "raw_primary_source"
    SOURCE_SNAPSHOT = "source_snapshot"
    SOURCE_PACKET = "source_packet"
    AI_INPUT = "ai_input"
    AI_OUTPUT = "ai_output"
    PUBLICATION_SNAPSHOT = "publication_snapshot"
    REVENUE_ORIGINAL = "revenue_original"
    REVENUE_REJECTS = "revenue_rejects"
    AUDIT_EXPORT = "audit_export"
    QUALITY_REPORT = "quality_report"
    DIFF = "diff"
    IMPORT_REPORT = "import_report"
    OTHER = "other"


class ObjectArtifactEncryptionState(str, Enum):
    SSE_KMS = "SSE_KMS"
    SSE_S3 = "SSE_S3"
    LOCAL_DEV = "LOCAL_DEV"


class OutboxEventRecordStatus(str, Enum):
    PENDING = "PENDING"
    DISPATCHING = "DISPATCHING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    DEAD = "DEAD"


class RuntimeSettingVersionScopeType(str, Enum):
    GLOBAL = "GLOBAL"
    SITE = "SITE"
    CATEGORY = "CATEGORY"
    ARTICLE = "ARTICLE"
    PROVIDER = "PROVIDER"
    TASK = "TASK"


class RuntimeSettingVersionSettingClass(str, Enum):
    FEATURE_FLAG = "FEATURE_FLAG"
    THRESHOLD = "THRESHOLD"
    PROVIDER = "PROVIDER"
    FRESHNESS = "FRESHNESS"
    BUDGET = "BUDGET"
    UI = "UI"
    OTHER = "OTHER"


class RuntimeSettingVersionStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"
    REJECTED = "REJECTED"


__all__ = [
    "AuditEventRecordActorType",
    "AuditEventRecordOutcome",
    "AuditEventRecordSeverity",
    "IdempotencyRecordStatus",
    "JobAttemptStatus",
    "JobStatus",
    "ObjectArtifactArtifactKind",
    "ObjectArtifactEncryptionState",
    "OutboxEventRecordStatus",
    "RuntimeSettingVersionScopeType",
    "RuntimeSettingVersionSettingClass",
    "RuntimeSettingVersionStatus",
]

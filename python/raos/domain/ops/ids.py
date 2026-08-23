"""Nominal OPS persistence identities selected by the ST-0308 mapper matrix."""

from raos.domain.shared.identity import EntityId


class AuditEventId(EntityId):
    __slots__ = ()


class EventId(EntityId):
    __slots__ = ()


class IdempotencyRecordId(EntityId):
    __slots__ = ()


class IncidentId(EntityId):
    __slots__ = ()


class JobAttemptId(EntityId):
    __slots__ = ()


class JobId(EntityId):
    __slots__ = ()


class ObjectArtifactId(EntityId):
    __slots__ = ()


class RuntimeSettingVersionId(EntityId):
    __slots__ = ()


__all__ = [
    "AuditEventId",
    "EventId",
    "IdempotencyRecordId",
    "IncidentId",
    "JobAttemptId",
    "JobId",
    "ObjectArtifactId",
    "RuntimeSettingVersionId",
]

"""Closed identity values shared by ST-0308 Domain modules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from typing import NoReturn, SupportsIndex
from uuid import RFC_4122, UUID


def _invalid() -> NoReturn:
    raise ValueError("INVALID_PERSISTENCE_IDENTITY") from None


def require_uuid(value: object) -> UUID:
    """Return a non-nil RFC-4122 UUID or fail without echoing it."""

    if type(value) is not UUID or value.int == 0 or value.variant != RFC_4122:
        _invalid()
    return value


def deterministic_uuid7(namespace: UUID, material: bytes) -> UUID:
    """Derive a stable RFC-4122/version-7 identifier from canonical bytes."""

    require_uuid(namespace)
    if type(material) is not bytes or not material:
        _invalid()
    raw = bytearray(hashlib.sha256(namespace.bytes + material).digest()[:16])
    raw[6] = (raw[6] & 0x0F) | 0x70
    raw[8] = (raw[8] & 0x3F) | 0x80
    return UUID(bytes=bytes(raw))


@dataclass(frozen=True, slots=True, repr=False)
class EntityId:
    """Base for module-owned typed identifiers.

    Repositories expose generated subclasses such as ``JobId`` and ``SiteId``;
    the base is never sufficient to select a relation.
    """

    value: UUID

    def __post_init__(self) -> None:
        require_uuid(self.value)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("persistence identity serialization is not supported")


class ActorId(EntityId):
    __slots__ = ()


class AssessedByActorId(EntityId):
    __slots__ = ()


class CausationId(EntityId):
    __slots__ = ()


class CorrelationId(EntityId):
    __slots__ = ()


class DecidedByActorId(EntityId):
    __slots__ = ()


class OpaqueResourceId(EntityId):
    __slots__ = ()


class RunId(EntityId):
    __slots__ = ()


class ScopeId(EntityId):
    __slots__ = ()


class SecondaryEntityId(EntityId):
    __slots__ = ()


class SubjectId(EntityId):
    __slots__ = ()


class TargetEntityId(EntityId):
    __slots__ = ()


class TriggeredByActorId(EntityId):
    __slots__ = ()


class ActorType(str, Enum):
    USER = "USER"
    SERVICE = "SERVICE"
    SCHEDULE = "SCHEDULE"
    SYSTEM = "SYSTEM"
    ANONYMOUS = "ANONYMOUS"


@dataclass(frozen=True, slots=True, repr=False)
class Actor:
    actor_type: ActorType
    actor_id: UUID | None

    def __post_init__(self) -> None:
        if type(self.actor_type) is not ActorType:
            _invalid()
        identified = self.actor_type in {
            ActorType.USER,
            ActorType.SERVICE,
            ActorType.SCHEDULE,
        }
        if identified:
            require_uuid(self.actor_id)
        elif self.actor_id is not None:
            _invalid()

    def __repr__(self) -> str:
        return "Actor(<redacted>)"


__all__ = [
    "Actor",
    "ActorId",
    "ActorType",
    "AssessedByActorId",
    "CausationId",
    "CorrelationId",
    "DecidedByActorId",
    "EntityId",
    "OpaqueResourceId",
    "RunId",
    "ScopeId",
    "SecondaryEntityId",
    "SubjectId",
    "TargetEntityId",
    "TriggeredByActorId",
    "deterministic_uuid7",
    "require_uuid",
]

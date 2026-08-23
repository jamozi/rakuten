"""Private transaction journal shared by outer and joined memory UoWs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import RFC_4122, UUID

from raos.adapters.persistence.memory.execution import _ExecutionPoint, _ExecutionState
from raos.adapters.persistence.memory.store import MemoryPersistenceStore, _MemoryState
from raos.domain.shared.events import DomainEvent
from raos.domain.shared.persistence import AwareUtcDateTime, PendingEventBuffer
from raos.ports.persistence.context import PersistenceContext
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode


Uuid7Factory = Callable[[], UUID]


@dataclass(slots=True)
class _MemoryTransaction:
    transaction_id: UUID
    context: PersistenceContext
    timestamp: AwareUtcDateTime
    base_revision: int
    state: _MemoryState
    store: MemoryPersistenceStore
    id_factory: Uuid7Factory
    execution_state: _ExecutionState
    active: bool = True
    rollback_only: bool = False
    joined_count: int = 0
    acknowledged_buffers: list[PendingEventBuffer[DomainEvent]] = field(
        default_factory=list
    )
    claim_reservation_keys: set[tuple[str, str, str]] = field(default_factory=set)

    def __post_init__(self) -> None:
        if (
            type(self.transaction_id) is not UUID
            or self.transaction_id.version != 7
            or self.transaction_id.variant != RFC_4122
            or type(self.context) is not PersistenceContext
            or type(self.timestamp) is not AwareUtcDateTime
            or type(self.base_revision) is not int
            or type(self.state) is not _MemoryState
            or type(self.store) is not MemoryPersistenceStore
            or type(self.execution_state) is not _ExecutionState
            or not callable(self.id_factory)
        ):
            raise PersistenceError(PersistenceErrorCode.STORAGE_CORRUPTION) from None

    def require_active(self) -> None:
        if not self.active:
            raise PersistenceError(PersistenceErrorCode.TRANSACTION_CLOSED) from None

    def require_operation(self) -> None:
        self.require_active()
        self.execution_state.require_allowed(
            _ExecutionPoint.PRE_REPOSITORY_QUERY_OR_DML
        )

    def new_uuid7(self) -> UUID:
        self.require_active()
        value = self.id_factory()
        if type(value) is not UUID or value.version != 7 or value.variant != RFC_4122:
            raise PersistenceError(PersistenceErrorCode.STORAGE_CORRUPTION) from None
        return value

    def acknowledge(self, buffer: PendingEventBuffer[DomainEvent]) -> None:
        self.require_active()
        if type(buffer) is not PendingEventBuffer:
            raise PersistenceError(PersistenceErrorCode.STORAGE_CORRUPTION) from None
        self.acknowledged_buffers.append(buffer)

    def restore_acknowledged(self) -> None:
        for buffer in reversed(self.acknowledged_buffers):
            buffer._restore_acknowledged()
        self.acknowledged_buffers.clear()

    def finish_acknowledged(self) -> None:
        for buffer in self.acknowledged_buffers:
            buffer._finish_acknowledged()
        self.acknowledged_buffers.clear()

    def reserve_claim_key(self, key: tuple[str, str, str]) -> None:
        self.require_active()
        if (
            type(key) is not tuple
            or len(key) != 3
            or any(type(item) is not str or not item for item in key)
        ):
            raise PersistenceError(PersistenceErrorCode.STORAGE_CORRUPTION) from None
        self.claim_reservation_keys.add(key)

    def release_claim_reservations(self) -> None:
        keys = tuple(sorted(self.claim_reservation_keys))
        self.store._release_claim_reservations(self.transaction_id, keys)
        self.claim_reservation_keys.clear()


def transaction_timestamp(clock: Callable[[], datetime]) -> AwareUtcDateTime:
    if not callable(clock):
        raise PersistenceError(PersistenceErrorCode.STORAGE_CORRUPTION) from None
    value = clock()
    if type(value) is not datetime or value.tzinfo is not timezone.utc or value.fold:
        raise PersistenceError(PersistenceErrorCode.STORAGE_CORRUPTION) from None
    return AwareUtcDateTime(value)

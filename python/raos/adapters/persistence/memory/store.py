"""Atomic, revisioned in-memory state used by the representative adapter."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import TypeAlias
from uuid import UUID

from raos.domain.ops.aggregates import (
    AuditEventRecord,
    IdempotencyRecord,
    ObjectArtifact,
    OutboxEventRecord,
    RuntimeSettingVersion,
)
from raos.domain.ops.ids import (
    IdempotencyRecordId,
    ObjectArtifactId,
    RuntimeSettingVersionId,
)
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode


_IdempotencyIdentityKey: TypeAlias = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class _MemoryClaimReservation:
    owner_transaction_id: UUID
    identity_key: _IdempotencyIdentityKey
    request_hash: str
    expires_at: datetime
    record_id: IdempotencyRecordId


@dataclass(slots=True)
class _MemoryState:
    object_artifacts: dict[ObjectArtifactId, ObjectArtifact] = field(
        default_factory=dict
    )
    runtime_settings: dict[RuntimeSettingVersionId, RuntimeSettingVersion] = field(
        default_factory=dict
    )
    audit_events: list[AuditEventRecord] = field(default_factory=list)
    outbox_events: list[OutboxEventRecord] = field(default_factory=list)
    idempotency_records: dict[IdempotencyRecordId, IdempotencyRecord] = field(
        default_factory=dict
    )

    def clone(self) -> _MemoryState:
        return _MemoryState(
            object_artifacts=dict(self.object_artifacts),
            runtime_settings=dict(self.runtime_settings),
            audit_events=list(self.audit_events),
            outbox_events=list(self.outbox_events),
            idempotency_records=dict(self.idempotency_records),
        )


@dataclass(frozen=True, slots=True)
class MemoryPersistenceSnapshot:
    revision: int
    object_artifacts: tuple[ObjectArtifact, ...]
    runtime_settings: tuple[RuntimeSettingVersion, ...]
    audit_events: tuple[AuditEventRecord, ...]
    outbox_events: tuple[OutboxEventRecord, ...]
    idempotency_records: tuple[IdempotencyRecord, ...]


class MemoryPersistenceStore:
    """One atomic state container; it performs no external I/O."""

    __slots__ = (
        "_claim_reservations",
        "_lock",
        "_revision",
        "_state",
        "_state_cloner",
    )

    def __init__(
        self,
        *,
        state_cloner: Callable[[_MemoryState], _MemoryState] | None = None,
    ) -> None:
        if state_cloner is not None and not callable(state_cloner):
            raise ValueError("INVALID_MEMORY_PERSISTENCE_STORE") from None
        self._lock = RLock()
        self._revision = 0
        self._state = _MemoryState()
        self._state_cloner = (
            (lambda state: state.clone()) if state_cloner is None else state_cloner
        )
        self._claim_reservations: dict[
            _IdempotencyIdentityKey, _MemoryClaimReservation
        ] = {}

    def _begin(self) -> tuple[int, _MemoryState]:
        with self._lock:
            return self._revision, self._state.clone()

    def _commit(self, expected_revision: int, replacement: _MemoryState) -> None:
        if type(expected_revision) is not int or type(replacement) is not _MemoryState:
            raise PersistenceError(PersistenceErrorCode.STORAGE_CORRUPTION) from None
        safe_replacement = self._clone_for_commit(replacement)
        with self._lock:
            if self._revision != expected_revision:
                raise PersistenceError(
                    PersistenceErrorCode.CONCURRENCY_CONFLICT
                ) from None
            self._state = safe_replacement
            self._revision += 1

    def _clone_for_commit(self, replacement: _MemoryState) -> _MemoryState:
        try:
            result = self._state_cloner(replacement)
        except Exception:
            raise PersistenceError(PersistenceErrorCode.STORAGE_CORRUPTION) from None
        if type(result) is not _MemoryState or result is replacement:
            raise PersistenceError(PersistenceErrorCode.STORAGE_CORRUPTION) from None
        return result

    def _observe_or_reserve_idempotency_claim(
        self,
        *,
        transaction_id: UUID,
        identity_key: _IdempotencyIdentityKey,
        request_hash: str,
        expires_at: datetime,
        record_id: IdempotencyRecordId,
        observed_record: IdempotencyRecord | None,
    ) -> _MemoryClaimReservation | IdempotencyRecord:
        if (
            type(transaction_id) is not UUID
            or type(identity_key) is not tuple
            or len(identity_key) != 3
            or any(type(item) is not str or not item for item in identity_key)
            or type(request_hash) is not str
            or type(expires_at) is not datetime
            or expires_at.tzinfo is not timezone.utc
            or expires_at.fold
            or type(record_id) is not IdempotencyRecordId
            or (
                observed_record is not None
                and type(observed_record) is not IdempotencyRecord
            )
        ):
            raise PersistenceError(PersistenceErrorCode.STORAGE_CORRUPTION) from None
        with self._lock:
            reserved = self._claim_reservations.get(identity_key)
            if reserved is not None:
                return reserved
            authoritative = tuple(
                record
                for record in self._state.idempotency_records.values()
                if (
                    record.actor_fingerprint,
                    record.route_key,
                    record.idempotency_key,
                )
                == identity_key
            )
            if len(authoritative) > 1:
                raise PersistenceError(
                    PersistenceErrorCode.STORAGE_CORRUPTION
                ) from None
            current = None if not authoritative else authoritative[0]
            if observed_record is None:
                if current is not None:
                    return current
            elif current != observed_record:
                if current is None:
                    raise PersistenceError(
                        PersistenceErrorCode.STORAGE_CORRUPTION
                    ) from None
                return current
            reservation = _MemoryClaimReservation(
                owner_transaction_id=transaction_id,
                identity_key=identity_key,
                request_hash=request_hash,
                expires_at=expires_at,
                record_id=record_id,
            )
            self._claim_reservations[identity_key] = reservation
            return reservation

    def _release_claim_reservations(
        self,
        transaction_id: UUID,
        identity_keys: tuple[_IdempotencyIdentityKey, ...],
    ) -> None:
        if (
            type(transaction_id) is not UUID
            or type(identity_keys) is not tuple
            or len(identity_keys) != len(set(identity_keys))
        ):
            raise PersistenceError(PersistenceErrorCode.STORAGE_CORRUPTION) from None
        with self._lock:
            for key in identity_keys:
                reservation = self._claim_reservations.get(key)
                if (
                    reservation is not None
                    and reservation.owner_transaction_id == transaction_id
                ):
                    del self._claim_reservations[key]

    def _commit_transaction(
        self,
        transaction_id: UUID,
        reservation_keys: tuple[_IdempotencyIdentityKey, ...],
        expected_revision: int,
        replacement: _MemoryState,
        transaction_commit: Callable[[], None],
    ) -> None:
        if (
            type(transaction_id) is not UUID
            or type(reservation_keys) is not tuple
            or len(reservation_keys) != len(set(reservation_keys))
            or type(expected_revision) is not int
            or type(replacement) is not _MemoryState
            or not callable(transaction_commit)
        ):
            raise PersistenceError(PersistenceErrorCode.STORAGE_CORRUPTION) from None
        safe_replacement = self._clone_for_commit(replacement)
        with self._lock:
            if self._revision != expected_revision:
                raise PersistenceError(
                    PersistenceErrorCode.CONCURRENCY_CONFLICT
                ) from None
            if any(
                (reservation := self._claim_reservations.get(key)) is None
                or reservation.owner_transaction_id != transaction_id
                for key in reservation_keys
            ):
                raise PersistenceError(
                    PersistenceErrorCode.LOST_IDEMPOTENCY_CLAIM
                ) from None
            transaction_commit()
            self._state = safe_replacement
            self._revision += 1
            for key in reservation_keys:
                del self._claim_reservations[key]

    def snapshot(self) -> MemoryPersistenceSnapshot:
        with self._lock:
            state = self._state
            return MemoryPersistenceSnapshot(
                revision=self._revision,
                object_artifacts=tuple(
                    sorted(
                        state.object_artifacts.values(),
                        key=lambda value: value.id.value.int,
                    )
                ),
                runtime_settings=tuple(
                    sorted(
                        state.runtime_settings.values(),
                        key=lambda value: value.state.id.value.int,
                    )
                ),
                audit_events=tuple(state.audit_events),
                outbox_events=tuple(state.outbox_events),
                idempotency_records=tuple(
                    sorted(
                        state.idempotency_records.values(),
                        key=lambda value: value.id.value.int,
                    )
                ),
            )


__all__ = ["MemoryPersistenceSnapshot", "MemoryPersistenceStore"]

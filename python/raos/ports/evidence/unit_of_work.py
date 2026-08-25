"""Exact EVIDENCE outer, idempotent, joined, and factory surfaces."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self, runtime_checkable

from raos.ports.evidence.repositories import (
    SourceRepository,
    SourceSnapshotRepository,
    FactRepository,
    SourcePacketRepository,
    ClaimRepository,
    FirstHandExperienceRepository,
)
from raos.ports.persistence.audit import AuditEventAppender
from raos.ports.persistence.context import PersistenceContext
from raos.ports.persistence.idempotency import IdempotencyRepository
from raos.ports.persistence.outbox import OutboxEventAppender
from raos.ports.persistence.transaction import TransactionJoin


@runtime_checkable
class EvidenceUnitOfWork(Protocol):
    @property
    def context(self) -> PersistenceContext: ...

    @property
    def audit(self) -> AuditEventAppender: ...

    @property
    def outbox(self) -> OutboxEventAppender: ...

    @property
    def sources(self) -> SourceRepository: ...

    @property
    def source_snapshots(self) -> SourceSnapshotRepository: ...

    @property
    def facts(self) -> FactRepository: ...

    @property
    def source_packets(self) -> SourcePacketRepository: ...

    @property
    def claims(self) -> ClaimRepository: ...

    @property
    def first_hand_experiences(self) -> FirstHandExperienceRepository: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool: ...

    def flush(self) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def mark_rollback_only(self) -> None: ...

    def join_token(self) -> TransactionJoin: ...


@runtime_checkable
class IdempotentEvidenceUnitOfWork(EvidenceUnitOfWork, Protocol):
    @property
    def idempotency(self) -> IdempotencyRepository: ...


@runtime_checkable
class JoinedEvidenceUnitOfWork(Protocol):
    @property
    def context(self) -> PersistenceContext: ...

    @property
    def audit(self) -> AuditEventAppender: ...

    @property
    def outbox(self) -> OutboxEventAppender: ...

    @property
    def sources(self) -> SourceRepository: ...

    @property
    def source_snapshots(self) -> SourceSnapshotRepository: ...

    @property
    def facts(self) -> FactRepository: ...

    @property
    def source_packets(self) -> SourcePacketRepository: ...

    @property
    def claims(self) -> ClaimRepository: ...

    @property
    def first_hand_experiences(self) -> FirstHandExperienceRepository: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool: ...

    def flush(self) -> None: ...

    def mark_rollback_only(self) -> None: ...


@runtime_checkable
class EvidenceUnitOfWorkFactory(Protocol):
    def begin(self, context: PersistenceContext) -> EvidenceUnitOfWork: ...

    def join(
        self,
        join_capability: TransactionJoin,
        context: PersistenceContext,
    ) -> JoinedEvidenceUnitOfWork: ...


@runtime_checkable
class IdempotentEvidenceUnitOfWorkFactory(EvidenceUnitOfWorkFactory, Protocol):
    def begin_idempotent(
        self,
        context: PersistenceContext,
    ) -> IdempotentEvidenceUnitOfWork: ...


__all__ = [
    "EvidenceUnitOfWork",
    "EvidenceUnitOfWorkFactory",
    "IdempotentEvidenceUnitOfWork",
    "IdempotentEvidenceUnitOfWorkFactory",
    "JoinedEvidenceUnitOfWork",
]

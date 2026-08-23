"""Exact OPS outer, idempotent, joined, and factory persistence surfaces."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self, runtime_checkable

from raos.ports.ops.repositories import (
    JobRepository,
    ObjectArtifactRepository,
    RuntimeSettingRepository,
)
from raos.ports.persistence.audit import AuditEventAppender
from raos.ports.persistence.context import PersistenceContext
from raos.ports.persistence.idempotency import IdempotencyRepository
from raos.ports.persistence.outbox import OutboxEventAppender
from raos.ports.persistence.transaction import TransactionJoin


@runtime_checkable
class OpsUnitOfWork(Protocol):
    @property
    def context(self) -> PersistenceContext: ...

    @property
    def audit(self) -> AuditEventAppender: ...

    @property
    def outbox(self) -> OutboxEventAppender: ...

    @property
    def jobs(self) -> JobRepository: ...

    @property
    def object_artifacts(self) -> ObjectArtifactRepository: ...

    @property
    def runtime_settings(self) -> RuntimeSettingRepository: ...

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
class IdempotentOpsUnitOfWork(OpsUnitOfWork, Protocol):
    @property
    def idempotency(self) -> IdempotencyRepository: ...


@runtime_checkable
class JoinedOpsUnitOfWork(Protocol):
    @property
    def context(self) -> PersistenceContext: ...

    @property
    def audit(self) -> AuditEventAppender: ...

    @property
    def outbox(self) -> OutboxEventAppender: ...

    @property
    def jobs(self) -> JobRepository: ...

    @property
    def object_artifacts(self) -> ObjectArtifactRepository: ...

    @property
    def runtime_settings(self) -> RuntimeSettingRepository: ...

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
class OpsUnitOfWorkFactory(Protocol):
    def begin(self, context: PersistenceContext) -> OpsUnitOfWork: ...

    def join(
        self,
        join_capability: TransactionJoin,
        context: PersistenceContext,
    ) -> JoinedOpsUnitOfWork: ...


@runtime_checkable
class IdempotentOpsUnitOfWorkFactory(OpsUnitOfWorkFactory, Protocol):
    def begin_idempotent(
        self,
        context: PersistenceContext,
    ) -> IdempotentOpsUnitOfWork: ...


__all__ = [
    "IdempotentOpsUnitOfWork",
    "IdempotentOpsUnitOfWorkFactory",
    "JoinedOpsUnitOfWork",
    "OpsUnitOfWork",
    "OpsUnitOfWorkFactory",
]

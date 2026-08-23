"""Exact Iam outer, idempotent, joined, and factory UoW ports."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self, runtime_checkable

from raos.ports.iam.repositories import (
    PrincipalRepository,
    RoleCatalogRepository,
    PrincipalRoleAssignmentRepository,
    SessionRevocationRepository,
    BreakGlassRecordRepository,
)
from raos.ports.persistence.audit import AuditEventAppender
from raos.ports.persistence.context import PersistenceContext
from raos.ports.persistence.idempotency import IdempotencyRepository
from raos.ports.persistence.outbox import OutboxEventAppender
from raos.ports.persistence.transaction import TransactionJoin


@runtime_checkable
class IamUnitOfWork(Protocol):
    @property
    def context(self) -> PersistenceContext: ...

    @property
    def audit(self) -> AuditEventAppender: ...

    @property
    def outbox(self) -> OutboxEventAppender: ...

    @property
    def principals(self) -> PrincipalRepository: ...

    @property
    def role_catalog(self) -> RoleCatalogRepository: ...

    @property
    def role_assignments(self) -> PrincipalRoleAssignmentRepository: ...

    @property
    def session_revocations(self) -> SessionRevocationRepository: ...

    @property
    def break_glass_records(self) -> BreakGlassRecordRepository: ...

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
class IdempotentIamUnitOfWork(IamUnitOfWork, Protocol):
    @property
    def idempotency(self) -> IdempotencyRepository: ...


@runtime_checkable
class JoinedIamUnitOfWork(Protocol):
    @property
    def context(self) -> PersistenceContext: ...

    @property
    def audit(self) -> AuditEventAppender: ...

    @property
    def outbox(self) -> OutboxEventAppender: ...

    @property
    def principals(self) -> PrincipalRepository: ...

    @property
    def role_catalog(self) -> RoleCatalogRepository: ...

    @property
    def role_assignments(self) -> PrincipalRoleAssignmentRepository: ...

    @property
    def session_revocations(self) -> SessionRevocationRepository: ...

    @property
    def break_glass_records(self) -> BreakGlassRecordRepository: ...

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
class IamUnitOfWorkFactory(Protocol):
    def begin(self, context: PersistenceContext) -> IamUnitOfWork: ...

    def join(
        self, join_capability: TransactionJoin, context: PersistenceContext
    ) -> JoinedIamUnitOfWork: ...


@runtime_checkable
class IdempotentIamUnitOfWorkFactory(IamUnitOfWorkFactory, Protocol):
    def begin_idempotent(
        self, context: PersistenceContext
    ) -> IdempotentIamUnitOfWork: ...


__all__ = [
    "IamUnitOfWork",
    "IamUnitOfWorkFactory",
    "IdempotentIamUnitOfWork",
    "IdempotentIamUnitOfWorkFactory",
    "JoinedIamUnitOfWork",
]

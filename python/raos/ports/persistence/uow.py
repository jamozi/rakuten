"""Shared structural capabilities used by generated module UoW protocols."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.ports.persistence.audit import AuditEventAppender
from raos.ports.persistence.context import PersistenceContext
from raos.ports.persistence.outbox import OutboxEventAppender


@runtime_checkable
class SharedUnitOfWorkSurface(Protocol):
    @property
    def context(self) -> PersistenceContext: ...

    @property
    def audit(self) -> AuditEventAppender: ...

    @property
    def outbox(self) -> OutboxEventAppender: ...

    def flush(self) -> None: ...

    def mark_rollback_only(self) -> None: ...


__all__ = ["SharedUnitOfWorkSurface"]

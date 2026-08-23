"""Exact POLICY outer, idempotent, joined, and factory surfaces."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self, runtime_checkable

from raos.ports.policy.repositories import (
    PolicyBundleRepository,
    RuleVersionRepository,
    QualityCheckRunRepository,
    FindingRepository,
    WaiverRepository,
    GateDecisionRepository,
)
from raos.ports.persistence.audit import AuditEventAppender
from raos.ports.persistence.context import PersistenceContext
from raos.ports.persistence.idempotency import IdempotencyRepository
from raos.ports.persistence.outbox import OutboxEventAppender
from raos.ports.persistence.transaction import TransactionJoin


@runtime_checkable
class PolicyUnitOfWork(Protocol):
    @property
    def context(self) -> PersistenceContext: ...

    @property
    def audit(self) -> AuditEventAppender: ...

    @property
    def outbox(self) -> OutboxEventAppender: ...

    @property
    def policy_bundles(self) -> PolicyBundleRepository: ...

    @property
    def rule_versions(self) -> RuleVersionRepository: ...

    @property
    def quality_check_runs(self) -> QualityCheckRunRepository: ...

    @property
    def findings(self) -> FindingRepository: ...

    @property
    def waivers(self) -> WaiverRepository: ...

    @property
    def gate_decisions(self) -> GateDecisionRepository: ...

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
class IdempotentPolicyUnitOfWork(PolicyUnitOfWork, Protocol):
    @property
    def idempotency(self) -> IdempotencyRepository: ...


@runtime_checkable
class JoinedPolicyUnitOfWork(Protocol):
    @property
    def context(self) -> PersistenceContext: ...

    @property
    def audit(self) -> AuditEventAppender: ...

    @property
    def outbox(self) -> OutboxEventAppender: ...

    @property
    def policy_bundles(self) -> PolicyBundleRepository: ...

    @property
    def rule_versions(self) -> RuleVersionRepository: ...

    @property
    def quality_check_runs(self) -> QualityCheckRunRepository: ...

    @property
    def findings(self) -> FindingRepository: ...

    @property
    def waivers(self) -> WaiverRepository: ...

    @property
    def gate_decisions(self) -> GateDecisionRepository: ...

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
class PolicyUnitOfWorkFactory(Protocol):
    def begin(self, context: PersistenceContext) -> PolicyUnitOfWork: ...

    def join(
        self,
        join_capability: TransactionJoin,
        context: PersistenceContext,
    ) -> JoinedPolicyUnitOfWork: ...


@runtime_checkable
class IdempotentPolicyUnitOfWorkFactory(PolicyUnitOfWorkFactory, Protocol):
    def begin_idempotent(
        self,
        context: PersistenceContext,
    ) -> IdempotentPolicyUnitOfWork: ...


__all__ = [
    "PolicyUnitOfWork",
    "PolicyUnitOfWorkFactory",
    "IdempotentPolicyUnitOfWork",
    "IdempotentPolicyUnitOfWorkFactory",
    "JoinedPolicyUnitOfWork",
]

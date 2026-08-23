"""Exact Portfolio outer, idempotent, joined, and factory UoW ports."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self, runtime_checkable

from raos.ports.portfolio.repositories import (
    SiteRepository,
    CategoryRepository,
    IntentClusterRepository,
    KeywordRepository,
    OpportunityAssessmentRepository,
    ActionCandidateRepository,
)
from raos.ports.persistence.audit import AuditEventAppender
from raos.ports.persistence.context import PersistenceContext
from raos.ports.persistence.idempotency import IdempotencyRepository
from raos.ports.persistence.outbox import OutboxEventAppender
from raos.ports.persistence.transaction import TransactionJoin


@runtime_checkable
class PortfolioUnitOfWork(Protocol):
    @property
    def context(self) -> PersistenceContext: ...

    @property
    def audit(self) -> AuditEventAppender: ...

    @property
    def outbox(self) -> OutboxEventAppender: ...

    @property
    def sites(self) -> SiteRepository: ...

    @property
    def categories(self) -> CategoryRepository: ...

    @property
    def intent_clusters(self) -> IntentClusterRepository: ...

    @property
    def keywords(self) -> KeywordRepository: ...

    @property
    def opportunity_assessments(self) -> OpportunityAssessmentRepository: ...

    @property
    def action_candidates(self) -> ActionCandidateRepository: ...

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
class IdempotentPortfolioUnitOfWork(PortfolioUnitOfWork, Protocol):
    @property
    def idempotency(self) -> IdempotencyRepository: ...


@runtime_checkable
class JoinedPortfolioUnitOfWork(Protocol):
    @property
    def context(self) -> PersistenceContext: ...

    @property
    def audit(self) -> AuditEventAppender: ...

    @property
    def outbox(self) -> OutboxEventAppender: ...

    @property
    def sites(self) -> SiteRepository: ...

    @property
    def categories(self) -> CategoryRepository: ...

    @property
    def intent_clusters(self) -> IntentClusterRepository: ...

    @property
    def keywords(self) -> KeywordRepository: ...

    @property
    def opportunity_assessments(self) -> OpportunityAssessmentRepository: ...

    @property
    def action_candidates(self) -> ActionCandidateRepository: ...

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
class PortfolioUnitOfWorkFactory(Protocol):
    def begin(self, context: PersistenceContext) -> PortfolioUnitOfWork: ...

    def join(
        self, join_capability: TransactionJoin, context: PersistenceContext
    ) -> JoinedPortfolioUnitOfWork: ...


@runtime_checkable
class IdempotentPortfolioUnitOfWorkFactory(PortfolioUnitOfWorkFactory, Protocol):
    def begin_idempotent(
        self, context: PersistenceContext
    ) -> IdempotentPortfolioUnitOfWork: ...


__all__ = [
    "PortfolioUnitOfWork",
    "PortfolioUnitOfWorkFactory",
    "IdempotentPortfolioUnitOfWork",
    "IdempotentPortfolioUnitOfWorkFactory",
    "JoinedPortfolioUnitOfWork",
]

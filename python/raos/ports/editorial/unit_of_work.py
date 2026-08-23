"""Exact EDITORIAL outer, idempotent, joined, and factory surfaces."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self, runtime_checkable

from raos.ports.editorial.repositories import (
    ArticlePlanRepository,
    ArticleRepository,
    ReviewCommentRepository,
    EditorialContractRepository,
    MediaAssetRepository,
)
from raos.ports.persistence.audit import AuditEventAppender
from raos.ports.persistence.context import PersistenceContext
from raos.ports.persistence.idempotency import IdempotencyRepository
from raos.ports.persistence.outbox import OutboxEventAppender
from raos.ports.persistence.transaction import TransactionJoin


@runtime_checkable
class EditorialUnitOfWork(Protocol):
    @property
    def context(self) -> PersistenceContext: ...

    @property
    def audit(self) -> AuditEventAppender: ...

    @property
    def outbox(self) -> OutboxEventAppender: ...

    @property
    def article_plans(self) -> ArticlePlanRepository: ...

    @property
    def articles(self) -> ArticleRepository: ...

    @property
    def review_comments(self) -> ReviewCommentRepository: ...

    @property
    def editorial_contracts(self) -> EditorialContractRepository: ...

    @property
    def media_assets(self) -> MediaAssetRepository: ...

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
class IdempotentEditorialUnitOfWork(EditorialUnitOfWork, Protocol):
    @property
    def idempotency(self) -> IdempotencyRepository: ...


@runtime_checkable
class JoinedEditorialUnitOfWork(Protocol):
    @property
    def context(self) -> PersistenceContext: ...

    @property
    def audit(self) -> AuditEventAppender: ...

    @property
    def outbox(self) -> OutboxEventAppender: ...

    @property
    def article_plans(self) -> ArticlePlanRepository: ...

    @property
    def articles(self) -> ArticleRepository: ...

    @property
    def review_comments(self) -> ReviewCommentRepository: ...

    @property
    def editorial_contracts(self) -> EditorialContractRepository: ...

    @property
    def media_assets(self) -> MediaAssetRepository: ...

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
class EditorialUnitOfWorkFactory(Protocol):
    def begin(self, context: PersistenceContext) -> EditorialUnitOfWork: ...

    def join(
        self,
        join_capability: TransactionJoin,
        context: PersistenceContext,
    ) -> JoinedEditorialUnitOfWork: ...


@runtime_checkable
class IdempotentEditorialUnitOfWorkFactory(EditorialUnitOfWorkFactory, Protocol):
    def begin_idempotent(
        self,
        context: PersistenceContext,
    ) -> IdempotentEditorialUnitOfWork: ...


__all__ = [
    "EditorialUnitOfWork",
    "EditorialUnitOfWorkFactory",
    "IdempotentEditorialUnitOfWork",
    "IdempotentEditorialUnitOfWorkFactory",
    "JoinedEditorialUnitOfWork",
]

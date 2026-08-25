"""Exact Catalog outer, idempotent, joined, and factory UoW ports."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self, runtime_checkable

from raos.ports.catalog.repositories import (
    ProviderEndpointRepository,
    IngestionRequestRepository,
    RakutenGenreRepository,
    ShopRepository,
    CanonicalProductRepository,
    ProductCandidateRepository,
    GroupingDecisionRepository,
    AttributeDefinitionRepository,
    OfferRepository,
    SafeOfferCurrentReader,
)
from raos.ports.persistence.audit import AuditEventAppender
from raos.ports.persistence.context import PersistenceContext
from raos.ports.persistence.idempotency import IdempotencyRepository
from raos.ports.persistence.outbox import OutboxEventAppender
from raos.ports.persistence.transaction import TransactionJoin


@runtime_checkable
class CatalogUnitOfWork(Protocol):
    @property
    def context(self) -> PersistenceContext: ...

    @property
    def audit(self) -> AuditEventAppender: ...

    @property
    def outbox(self) -> OutboxEventAppender: ...

    @property
    def provider_endpoints(self) -> ProviderEndpointRepository: ...

    @property
    def ingestion_requests(self) -> IngestionRequestRepository: ...

    @property
    def rakuten_genres(self) -> RakutenGenreRepository: ...

    @property
    def shops(self) -> ShopRepository: ...

    @property
    def canonical_products(self) -> CanonicalProductRepository: ...

    @property
    def product_candidates(self) -> ProductCandidateRepository: ...

    @property
    def grouping_decisions(self) -> GroupingDecisionRepository: ...

    @property
    def attribute_definitions(self) -> AttributeDefinitionRepository: ...

    @property
    def offers(self) -> OfferRepository: ...

    @property
    def safe_offer_current(self) -> SafeOfferCurrentReader: ...

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
class IdempotentCatalogUnitOfWork(CatalogUnitOfWork, Protocol):
    @property
    def idempotency(self) -> IdempotencyRepository: ...


@runtime_checkable
class JoinedCatalogUnitOfWork(Protocol):
    @property
    def context(self) -> PersistenceContext: ...

    @property
    def audit(self) -> AuditEventAppender: ...

    @property
    def outbox(self) -> OutboxEventAppender: ...

    @property
    def provider_endpoints(self) -> ProviderEndpointRepository: ...

    @property
    def ingestion_requests(self) -> IngestionRequestRepository: ...

    @property
    def rakuten_genres(self) -> RakutenGenreRepository: ...

    @property
    def shops(self) -> ShopRepository: ...

    @property
    def canonical_products(self) -> CanonicalProductRepository: ...

    @property
    def product_candidates(self) -> ProductCandidateRepository: ...

    @property
    def grouping_decisions(self) -> GroupingDecisionRepository: ...

    @property
    def attribute_definitions(self) -> AttributeDefinitionRepository: ...

    @property
    def offers(self) -> OfferRepository: ...

    @property
    def safe_offer_current(self) -> SafeOfferCurrentReader: ...

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
class CatalogUnitOfWorkFactory(Protocol):
    def begin(self, context: PersistenceContext) -> CatalogUnitOfWork: ...

    def join(
        self, join_capability: TransactionJoin, context: PersistenceContext
    ) -> JoinedCatalogUnitOfWork: ...


@runtime_checkable
class IdempotentCatalogUnitOfWorkFactory(CatalogUnitOfWorkFactory, Protocol):
    def begin_idempotent(
        self, context: PersistenceContext
    ) -> IdempotentCatalogUnitOfWork: ...


__all__ = [
    "CatalogUnitOfWork",
    "CatalogUnitOfWorkFactory",
    "IdempotentCatalogUnitOfWork",
    "IdempotentCatalogUnitOfWorkFactory",
    "JoinedCatalogUnitOfWork",
]

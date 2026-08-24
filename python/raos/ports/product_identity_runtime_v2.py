"""Closed inward persistence port for ST-0504 product identity V2."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.catalog.product_identity_runtime_v2 import (
    PersistedProductIdentityDecisionV2,
    PersistedProductIdentityReviewQueueV2,
    PrepareProductIdentityReviewQueueCommandV2,
    ProductIdentityDecisionCommandV2,
    ProductIdentityDecisionCommitRecoveryV2,
    ProductIdentityHumanDecisionV2,
    ProductIdentityOutboxEventV2,
    ProductIdentityQueueCommitRecoveryV2,
    ProductIdentityReviewQueueV2,
)


@runtime_checkable
class ProductIdentityUnitOfWorkStoreV2(Protocol):
    """One owner-private queue/decision CAS, journal, outbox and hash chain."""

    def lookup_review_queue(
        self, command: PrepareProductIdentityReviewQueueCommandV2
    ) -> PersistedProductIdentityReviewQueueV2 | None: ...

    def commit_review_queue(
        self,
        *,
        command: PrepareProductIdentityReviewQueueCommandV2,
        queue: ProductIdentityReviewQueueV2,
        event: ProductIdentityOutboxEventV2,
    ) -> PersistedProductIdentityReviewQueueV2: ...

    def recover_review_queue_commit(
        self, command: PrepareProductIdentityReviewQueueCommandV2
    ) -> ProductIdentityQueueCommitRecoveryV2: ...

    def lookup_decision(
        self, command: ProductIdentityDecisionCommandV2
    ) -> PersistedProductIdentityDecisionV2 | None: ...

    def commit_decision(
        self,
        *,
        command: ProductIdentityDecisionCommandV2,
        decision: ProductIdentityHumanDecisionV2,
        event: ProductIdentityOutboxEventV2,
    ) -> PersistedProductIdentityDecisionV2: ...

    def recover_decision_commit(
        self, command: ProductIdentityDecisionCommandV2
    ) -> ProductIdentityDecisionCommitRecoveryV2: ...

    def load_review_queue(
        self, queue_id: object
    ) -> PersistedProductIdentityReviewQueueV2: ...

    def list_decisions(
        self, queue_id: object
    ) -> tuple[PersistedProductIdentityDecisionV2, ...]: ...

    def load_outbox(self, event_id: object) -> ProductIdentityOutboxEventV2: ...


__all__ = ["ProductIdentityUnitOfWorkStoreV2"]

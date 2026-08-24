"""Closed inward persistence port for ST-0603 durable conflict detection V2."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from raos.domain.evidence.fact_conflict_runtime_v2 import (
    FactConflictDetectionBatchV2,
    FactConflictReviewQueueRecordV2,
    FactConflictScanCommandV2,
    FactConflictStoreCommitV2,
    FactConflictsRecordedOutboxEventV2,
    PersistedFactConflictDetectionV2,
    UnresolvedFactConflictV2,
)


@runtime_checkable
class FactConflictUnitOfWorkStoreV2(Protocol):
    """Atomic append-only scan, conflict, queue, outbox, and chain capability."""

    def lookup(
        self,
        command: FactConflictScanCommandV2,
    ) -> PersistedFactConflictDetectionV2 | None: ...

    def commit(
        self,
        *,
        command: FactConflictScanCommandV2,
        batch: FactConflictDetectionBatchV2,
        event: FactConflictsRecordedOutboxEventV2,
    ) -> FactConflictStoreCommitV2: ...

    def recover_exact(
        self,
        command: FactConflictScanCommandV2,
    ) -> PersistedFactConflictDetectionV2 | None: ...

    def load_batch(self, scan_id: UUID) -> FactConflictDetectionBatchV2: ...

    def load_conflict(self, conflict_id: UUID) -> UnresolvedFactConflictV2: ...

    def load_queue(
        self,
        queue_id: UUID,
    ) -> FactConflictReviewQueueRecordV2: ...

    def load_outbox(
        self,
        event_id: UUID,
    ) -> FactConflictsRecordedOutboxEventV2: ...

    def verify_chain(self) -> tuple[str, int]: ...


__all__ = ["FactConflictUnitOfWorkStoreV2"]

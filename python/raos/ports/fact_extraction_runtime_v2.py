"""Closed inward persistence port for ST-0602 durable Fact extraction V2."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from raos.domain.evidence.fact_extraction_runtime_v2 import (
    ExactOfferFactV2,
    FactExtractionBatchV2,
    FactExtractionCommandV2,
    FactStoreCommitV2,
    FactValidationRecordV2,
    FactsExtractedOutboxEventV2,
    PersistedFactExtractionV2,
)


@runtime_checkable
class FactExtractionUnitOfWorkStoreV2(Protocol):
    """Atomic append-only batch, validation, outbox, and chain capability."""

    def lookup(
        self,
        command: FactExtractionCommandV2,
    ) -> PersistedFactExtractionV2 | None: ...

    def commit(
        self,
        *,
        command: FactExtractionCommandV2,
        batch: FactExtractionBatchV2,
        event: FactsExtractedOutboxEventV2,
    ) -> FactStoreCommitV2: ...

    def recover_exact(
        self,
        command: FactExtractionCommandV2,
    ) -> PersistedFactExtractionV2 | None: ...

    def load_batch(self, batch_id: UUID) -> FactExtractionBatchV2: ...

    def load_fact(self, fact_id: UUID) -> ExactOfferFactV2: ...

    def list_validations(
        self,
        batch_id: UUID,
    ) -> tuple[FactValidationRecordV2, ...]: ...

    def load_outbox(self, event_id: UUID) -> FactsExtractedOutboxEventV2: ...

    def verify_chain(self) -> tuple[str, int]: ...


__all__ = ["FactExtractionUnitOfWorkStoreV2"]

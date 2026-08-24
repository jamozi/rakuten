"""Closed persistence ports for the ST-0405 durable local audit runtime."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from raos.domain.ops.audit_runtime_v2 import (
    AuditAppendReceiptV2,
    AuditAuthorizationProofV2,
    AuditEventCandidateV2,
    PersistedAuditEventV2,
)


@runtime_checkable
class AuditRuntimeStoreV2(Protocol):
    """One append-only owner-private store; update/delete/export are absent."""

    def lookup_authorization(
        self, proof: AuditAuthorizationProofV2
    ) -> PersistedAuditEventV2 | None: ...

    def append_atomic(
        self, candidate: AuditEventCandidateV2
    ) -> AuditAppendReceiptV2: ...

    def recover_exact(
        self, candidate: AuditEventCandidateV2
    ) -> AuditAppendReceiptV2: ...

    def load_exact(self, event_id: UUID) -> PersistedAuditEventV2 | None: ...

    def query_internal_correlation(
        self, correlation_id: UUID, *, limit: int
    ) -> tuple[PersistedAuditEventV2, ...]: ...

    def verify_chain(self) -> tuple[str, int]: ...


@runtime_checkable
class AuditRuntimeStoreFactoryV2(Protocol):
    """Lazily open the audit store only after ST-0403 authorization succeeds."""

    @property
    def open_count(self) -> int: ...

    def open(self) -> AuditRuntimeStoreV2: ...


__all__ = ["AuditRuntimeStoreFactoryV2", "AuditRuntimeStoreV2"]

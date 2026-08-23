"""Shared inward idempotency claim/completion capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.shared.idempotency import (
    IdempotencyClaim,
    IdempotencyClaimDecision,
    IdempotencyClaimHandle,
    IdempotencyIdentity,
    IdempotencyLookupDecision,
    IdempotencyOutcome,
    RequestHash,
)


@runtime_checkable
class IdempotencyRepository(Protocol):
    def claim(self, claim: IdempotencyClaim) -> IdempotencyClaimDecision: ...

    def lookup(
        self,
        identity: IdempotencyIdentity,
        request_hash: RequestHash,
    ) -> IdempotencyLookupDecision: ...

    def complete_success(
        self,
        handle: IdempotencyClaimHandle,
        outcome: IdempotencyOutcome,
    ) -> None: ...

    def complete_failure(
        self,
        handle: IdempotencyClaimHandle,
        outcome: IdempotencyOutcome,
    ) -> None: ...


__all__ = ["IdempotencyRepository"]

"""Inward semantic ports for the bounded recorded Job runtime."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from raos.domain.ops.job_runtime import (
    CompletionCommit,
    DeliveryStart,
    OutboxDispatchClaim,
    OutboxRecord,
    RecordedHandlerResult,
    RecordedJobInvocation,
    RecordedJobMessage,
    RuntimeFailureCode,
    WorkClaim,
)


@runtime_checkable
class JobRuntimeStore(Protocol):
    """Atomic process-local Job/Attempt/Outbox/Inbox semantics.

    A conforming adapter may be ephemeral.  This port does not claim database,
    crash, or multi-process atomicity.
    """

    def claim_due_outbox(self, *, now: datetime) -> OutboxDispatchClaim | None:
        """Claim at most one deterministic due recorded Outbox item."""

        ...

    def publish_succeeded(
        self, *, claim: OutboxDispatchClaim, published_at: datetime
    ) -> tuple[OutboxRecord, int]:
        """Record publication and the exact REQUESTED -> QUEUED transition."""

        ...

    def publish_failed(
        self,
        *,
        claim: OutboxDispatchClaim,
        failed_at: datetime,
        retry_at: datetime | None,
        failure_code: RuntimeFailureCode,
    ) -> OutboxRecord:
        """Record one ambiguous send failure without changing message identity."""

        ...

    def begin_delivery(
        self,
        *,
        message: RecordedJobMessage,
        consumer_name: str,
        handler_version: str,
        delivery_attempt: int,
        leased_until: datetime,
        job_lease_until: datetime,
        now: datetime,
    ) -> DeliveryStart:
        """Deduplicate, precheck, and optionally claim QUEUED -> RUNNING."""

        ...

    def complete_delivery(
        self,
        *,
        claim: WorkClaim,
        result: RecordedHandlerResult,
        retry_at: datetime | None,
    ) -> CompletionCommit:
        """Fence and commit one recorded result plus its Inbox disposition."""

        ...


@runtime_checkable
class RecordedJobHandler(Protocol):
    """One synchronous handler that receives and returns metadata only."""

    def handle(self, invocation: RecordedJobInvocation) -> RecordedHandlerResult:
        """Handle exactly one already-claimed recorded invocation."""

        ...


__all__ = ["JobRuntimeStore", "RecordedJobHandler"]

"""Inward UoW and handler ports for the ST-1404 durable runtime seam."""

from __future__ import annotations

from datetime import datetime
from types import TracebackType
from typing import Literal, Protocol, Self, runtime_checkable
from uuid import UUID

from raos.domain.ops.durable_job_runtime import (
    DurableDeliveryStart,
    DurableHandlerResult,
    DurableOutboxClaim,
    DurableWorkClaim,
    DurableWorkResult,
    QuarantineReleaseApproval,
    QuarantineReplayClaim,
    QuarantineReplayResult,
    RecoveryCandidate,
    RecoveryResult,
)
from raos.domain.ops.job_runtime import (
    JobRecord,
    OutboxRecord,
    RecordedJobInvocation,
    RecordedJobMessage,
    RuntimeFailureCode,
)
from raos.ports.persistence.context import PersistenceContext


@runtime_checkable
class DurableJobHandler(Protocol):
    """Metadata-only handler; it must perform no external side effect."""

    def handle(self, invocation: RecordedJobInvocation) -> DurableHandlerResult: ...


@runtime_checkable
class DurableJobRuntimeRepository(Protocol):
    """Transaction-bound Job/Attempt/Outbox/Inbox command surface."""

    def claim_due_outbox(
        self,
        *,
        now: datetime,
        owner: str,
        leased_until: datetime,
    ) -> DurableOutboxClaim | None: ...

    def publish_succeeded(
        self,
        *,
        claim: DurableOutboxClaim,
        published_at: datetime,
    ) -> tuple[OutboxRecord, int]: ...

    def publish_failed(
        self,
        *,
        claim: DurableOutboxClaim,
        failed_at: datetime,
        retry_at: datetime | None,
        failure_code: RuntimeFailureCode,
    ) -> OutboxRecord: ...

    def begin_delivery(
        self,
        *,
        message: RecordedJobMessage,
        consumer_name: str,
        handler_version: str,
        owner: str,
        delivery_attempt: int,
        queue_leased_until: datetime,
        job_leased_until: datetime,
        now: datetime,
    ) -> DurableDeliveryStart: ...

    def complete_delivery(
        self,
        *,
        claim: DurableWorkClaim,
        result: DurableHandlerResult,
        retry_at: datetime | None,
    ) -> DurableWorkResult: ...

    def request_cancellation(
        self,
        *,
        job_id: UUID,
        expected_job_version: int,
        requested_at: datetime,
    ) -> JobRecord: ...

    def recovery_candidate(self, *, now: datetime) -> RecoveryCandidate | None: ...

    def recover(
        self,
        *,
        candidate: RecoveryCandidate,
        recovered_at: datetime,
        retry_at: datetime | None,
    ) -> RecoveryResult: ...

    def prepare_quarantine_replay(
        self,
        *,
        approval: QuarantineReleaseApproval,
        owner: str,
        leased_until: datetime,
        now: datetime,
    ) -> QuarantineReplayClaim: ...

    def finalize_quarantine_replay(
        self,
        *,
        claim: QuarantineReplayClaim,
        finalized_at: datetime,
    ) -> QuarantineReplayResult: ...


@runtime_checkable
class DurableJobRuntimeUnitOfWork(Protocol):
    """One outer transaction owner compatible with the ST-0308 lifecycle."""

    @property
    def context(self) -> PersistenceContext: ...

    @property
    def repository(self) -> DurableJobRuntimeRepository: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


@runtime_checkable
class DurableJobRuntimeUnitOfWorkFactory(Protocol):
    def begin(self, context: PersistenceContext) -> DurableJobRuntimeUnitOfWork: ...


__all__ = [
    "DurableJobHandler",
    "DurableJobRuntimeRepository",
    "DurableJobRuntimeUnitOfWork",
    "DurableJobRuntimeUnitOfWorkFactory",
]

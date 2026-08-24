"""Caller-owned atomic persistence port for ST-0706 durable state bytes."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.ai.durable_job_queue_v2 import DurableQueueSnapshot


@runtime_checkable
class DurableAiJobStateCasPort(Protocol):
    """Load or atomically replace one exact versioned queue-state document.

    The persistence implementation is caller-owned.  ST-0706 supplies exact
    canonical replacement bytes but does not select a database or transaction
    runtime.
    """

    def load(self, *, queue_id: str) -> DurableQueueSnapshot:
        """Return exact bytes, revision, and their derived SHA-256 binding."""

        ...

    def compare_and_swap(
        self,
        *,
        queue_id: str,
        expected_revision: int,
        expected_state_sha256: str,
        replacement_state_bytes: bytes,
    ) -> DurableQueueSnapshot:
        """Commit only if both expected revision and state hash still match."""

        ...


__all__ = ["DurableAiJobStateCasPort"]

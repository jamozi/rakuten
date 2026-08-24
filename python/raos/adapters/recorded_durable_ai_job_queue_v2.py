"""Recorded executable CAS adapter for ST-0706 crash/restart evidence.

The adapter is deliberately not a production persistence implementation.  It
can export exact bytes plus revision and rehydrate them into a distinct object,
which exercises service restart semantics without choosing a database,
filesystem, broker, or live provider.
"""

from __future__ import annotations

from threading import RLock
from typing import final

from raos.domain.ai.durable_job_queue_v2 import (
    DurableQueueFailureCode,
    DurableQueueSnapshot,
    decode_durable_queue_state,
    encode_durable_queue_state,
    fail_durable_queue,
    initial_durable_queue_state,
    require_durable_sha256,
)


@final
class RecordedDurableAiJobStateAdapterV2:
    """Bounded recorded CAS storage with optional post-commit uncertainty."""

    __slots__ = (
        "_commit_uncertain_once",
        "_lock",
        "_queue_id",
        "_revision",
        "_state_bytes",
    )

    def __init__(
        self,
        *,
        queue_id: str,
        revision: int | None = None,
        state_bytes: bytes | None = None,
    ) -> None:
        if (revision is None) != (state_bytes is None):
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        if revision is None:
            initial = initial_durable_queue_state(queue_id)
            observed_revision = 0
            observed_bytes = encode_durable_queue_state(initial)
        else:
            if state_bytes is None:
                fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
            observed_revision = revision
            observed_bytes = state_bytes
        if type(observed_revision) is not int or type(observed_bytes) is not bytes:
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        decode_durable_queue_state(
            observed_bytes,
            expected_queue_id=queue_id,
            expected_revision=observed_revision,
        )
        self._queue_id = queue_id
        self._revision = observed_revision
        self._state_bytes = bytes(observed_bytes)
        self._commit_uncertain_once = False
        self._lock = RLock()

    @classmethod
    def from_snapshot(
        cls, *, snapshot: DurableQueueSnapshot
    ) -> RecordedDurableAiJobStateAdapterV2:
        """Rehydrate exact exported bytes into a separate adapter instance."""

        if type(snapshot) is not DurableQueueSnapshot:
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        return cls(
            queue_id=snapshot.queue_id,
            revision=snapshot.revision,
            state_bytes=snapshot.state_bytes,
        )

    def load(self, *, queue_id: str) -> DurableQueueSnapshot:
        """Return an immutable copy of the current exact state document."""

        with self._lock:
            self._require_queue(queue_id)
            return DurableQueueSnapshot(
                queue_id=self._queue_id,
                revision=self._revision,
                state_bytes=bytes(self._state_bytes),
            )

    def compare_and_swap(
        self,
        *,
        queue_id: str,
        expected_revision: int,
        expected_state_sha256: str,
        replacement_state_bytes: bytes,
    ) -> DurableQueueSnapshot:
        """Apply one exact revision/hash fenced replacement atomically."""

        if (
            type(expected_revision) is not int
            or expected_revision < 0
            or type(replacement_state_bytes) is not bytes
        ):
            fail_durable_queue(DurableQueueFailureCode.INVALID_REQUEST)
        normalized_expected_sha256 = require_durable_sha256(expected_state_sha256)
        replacement = bytes(replacement_state_bytes)
        decode_durable_queue_state(
            replacement,
            expected_queue_id=queue_id,
            expected_revision=expected_revision + 1,
        )
        with self._lock:
            self._require_queue(queue_id)
            current = DurableQueueSnapshot(
                queue_id=self._queue_id,
                revision=self._revision,
                state_bytes=self._state_bytes,
            )
            if (
                current.revision != expected_revision
                or current.state_sha256 != normalized_expected_sha256
            ):
                fail_durable_queue(DurableQueueFailureCode.CAS_CONFLICT)
            self._revision = expected_revision + 1
            self._state_bytes = replacement
            committed = DurableQueueSnapshot(
                queue_id=self._queue_id,
                revision=self._revision,
                state_bytes=self._state_bytes,
            )
            if self._commit_uncertain_once:
                self._commit_uncertain_once = False
                fail_durable_queue(DurableQueueFailureCode.COMMIT_UNCERTAIN)
            return committed

    def export_snapshot(self) -> DurableQueueSnapshot:
        """Export bytes+revision for recorded crash/reload tests."""

        return self.load(queue_id=self._queue_id)

    def arm_commit_uncertain_once(self) -> None:
        """Make the next successful CAS commit then return a closed uncertainty."""

        with self._lock:
            self._commit_uncertain_once = True

    def _require_queue(self, queue_id: object) -> None:
        if type(queue_id) is not str or queue_id != self._queue_id:
            fail_durable_queue(DurableQueueFailureCode.STATE_INVALID)


__all__ = ["RecordedDurableAiJobStateAdapterV2"]

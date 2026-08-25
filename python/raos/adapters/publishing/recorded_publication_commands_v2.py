"""Atomic recorded/synthetic store for the ST-0905 local command runtime."""

from __future__ import annotations

from enum import StrEnum
import hashlib
from threading import RLock
from typing import Final, NoReturn, SupportsIndex, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.publishing.publication_commands_v2 import (
    KnownPublicationSnapshotV2,
    PublicationCommandAction,
    PublicationCommandFailureCode,
    PublicationCommandResultV2,
    PublicationCommandSourcesV2,
    PublicationLocalState,
    PublicationStoreSnapshotV2,
    PublishCommandV2,
    RollbackCommandV2,
    build_publish_result_v2,
    build_rollback_result_v2,
    fail_publication_command,
)
from raos.domain.shared.persistence import Sha256Digest


_MAX_RECEIPTS: Final = 4096


class TransactionFailurePoint(StrEnum):
    AFTER_PROJECTION_STAGE = "AFTER_PROJECTION_STAGE"
    AFTER_EVENT_STAGE = "AFTER_EVENT_STAGE"
    AFTER_AUDIT_STAGE = "AFTER_AUDIT_STAGE"
    AFTER_OUTBOX_STAGE = "AFTER_OUTBOX_STAGE"


def _key_digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


@final
class RecordedPublicationCommandStoreV2:
    """One lock, copy-then-swap transaction with no I/O or external writer."""

    __slots__ = (
        "_audits",
        "_current_projection",
        "_current_snapshot",
        "_current_source_binding",
        "_events",
        "_failure_plan",
        "_generation",
        "_lock",
        "_outbox",
        "_projections",
        "_receipts",
        "_semantic_results",
        "_sources",
        "_state",
    )

    _audits: list[bytes]
    _current_projection: bytes | None
    _current_snapshot: KnownPublicationSnapshotV2 | None
    _current_source_binding: Sha256Digest | None
    _events: list[bytes]
    _failure_plan: list[TransactionFailurePoint]
    _generation: int
    _outbox: list[bytes]
    _projections: list[bytes]
    _receipts: dict[str, tuple[bytes, PublicationCommandResultV2]]
    _semantic_results: dict[
        tuple[PublicationCommandAction, str], PublicationCommandResultV2
    ]
    _sources: PublicationCommandSourcesV2
    _state: PublicationLocalState

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        sources: PublicationCommandSourcesV2,
        failure_plan: tuple[TransactionFailurePoint, ...] = (),
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or type(sources) is not PublicationCommandSourcesV2
            or type(failure_plan) is not tuple
            or any(type(point) is not TransactionFailurePoint for point in failure_plan)
        ):
            fail_publication_command(
                PublicationCommandFailureCode.LOCAL_ENVIRONMENT_REQUIRED
            )
        sources.require_valid()
        self._sources = sources
        self._state = PublicationLocalState.UNPUBLISHED
        self._generation = 0
        self._current_snapshot = None
        self._current_source_binding = None
        self._current_projection = None
        self._receipts = {}
        self._semantic_results = {}
        self._projections = []
        self._events = []
        self._audits = []
        self._outbox = []
        self._failure_plan = list(failure_plan)
        self._lock = RLock()

    def _replay(
        self,
        *,
        key: str,
        request_bytes: bytes,
    ) -> PublicationCommandResultV2 | None:
        receipt = self._receipts.get(_key_digest(key))
        if receipt is None:
            return None
        retained_request, retained_result = receipt
        if retained_request != request_bytes:
            fail_publication_command(PublicationCommandFailureCode.IDEMPOTENCY_CONFLICT)
        return retained_result

    def _maybe_fail(self, point: TransactionFailurePoint) -> None:
        if self._failure_plan and self._failure_plan[0] is point:
            self._failure_plan.pop(0)
            fail_publication_command(PublicationCommandFailureCode.TRANSACTION_FAILED)

    def plan_failure(self, point: TransactionFailurePoint) -> None:
        """Arm one recorded adapter failure before the next matching stage."""

        if type(point) is not TransactionFailurePoint:
            fail_publication_command()
        with self._lock:
            if self._failure_plan:
                fail_publication_command(
                    PublicationCommandFailureCode.TRANSACTION_FAILED
                )
            self._failure_plan = [point]

    def _stage_records(
        self,
        *,
        request_bytes: bytes,
        key: str,
        semantic_key: tuple[PublicationCommandAction, str],
        result: PublicationCommandResultV2,
    ) -> tuple[
        dict[str, tuple[bytes, PublicationCommandResultV2]],
        dict[tuple[PublicationCommandAction, str], PublicationCommandResultV2],
        list[bytes],
        list[bytes],
        list[bytes],
        list[bytes],
    ]:
        if len(self._receipts) >= _MAX_RECEIPTS:
            fail_publication_command(PublicationCommandFailureCode.TRANSACTION_FAILED)
        receipts = dict(self._receipts)
        semantic = dict(self._semantic_results)
        projections = [*self._projections, result.projection_bytes]
        self._maybe_fail(TransactionFailurePoint.AFTER_PROJECTION_STAGE)
        events = [*self._events, result.event_bytes]
        self._maybe_fail(TransactionFailurePoint.AFTER_EVENT_STAGE)
        audits = [*self._audits, result.audit_bytes]
        self._maybe_fail(TransactionFailurePoint.AFTER_AUDIT_STAGE)
        outbox = [*self._outbox, result.outbox_bytes]
        self._maybe_fail(TransactionFailurePoint.AFTER_OUTBOX_STAGE)
        receipts[_key_digest(key)] = (request_bytes, result)
        semantic[semantic_key] = result
        return receipts, semantic, projections, events, audits, outbox

    def publish(self, command: PublishCommandV2) -> PublicationCommandResultV2:
        if type(command) is not PublishCommandV2:
            fail_publication_command()
        request_bytes = command.canonical_bytes()
        with self._lock:
            replay = self._replay(
                key=command.idempotency_key,
                request_bytes=request_bytes,
            )
            if replay is not None:
                return replay
            self._sources.require_valid()
            target = self._sources.latest
            if (
                command.publication_id != self._sources.publication_id
                or command.snapshot_id != target.snapshot_id
                or command.expected_source_binding_sha256
                != target.source_binding_sha256
            ):
                fail_publication_command(
                    PublicationCommandFailureCode.SOURCE_HASH_MISMATCH
                )
            semantic_key = (PublicationCommandAction.PUBLISH, str(target.snapshot_id))
            if self._state is PublicationLocalState.PUBLISHED:
                if (
                    self._current_snapshot is None
                    or self._current_source_binding
                    != self._current_snapshot.source_binding_sha256
                    or self._current_projection
                    != self._current_snapshot.projection_result.projection_bytes
                ):
                    fail_publication_command(
                        PublicationCommandFailureCode.PUBLICATION_STATE_DRIFT
                    )
                if self._current_snapshot.snapshot_id == target.snapshot_id:
                    prior = self._semantic_results.get(semantic_key)
                    if prior is None:
                        fail_publication_command(
                            PublicationCommandFailureCode.PUBLICATION_STATE_DRIFT
                        )
                    if command.expected_generation != self._generation:
                        fail_publication_command(
                            PublicationCommandFailureCode.CONCURRENCY_CONFLICT
                        )
                    if len(self._receipts) >= _MAX_RECEIPTS:
                        fail_publication_command(
                            PublicationCommandFailureCode.TRANSACTION_FAILED
                        )
                    staged_receipts = dict(self._receipts)
                    staged_receipts[_key_digest(command.idempotency_key)] = (
                        request_bytes,
                        prior,
                    )
                    self._receipts = staged_receipts
                    return prior
                fail_publication_command(
                    PublicationCommandFailureCode.CONCURRENCY_CONFLICT
                )
            if command.expected_generation != 0 or self._generation != 0:
                fail_publication_command(
                    PublicationCommandFailureCode.CONCURRENCY_CONFLICT
                )
            result = build_publish_result_v2(
                command=command,
                source=target,
                generation=1,
            )
            (
                receipts,
                semantic,
                projections,
                events,
                audits,
                outbox,
            ) = self._stage_records(
                request_bytes=request_bytes,
                key=command.idempotency_key,
                semantic_key=semantic_key,
                result=result,
            )
            self._state = PublicationLocalState.PUBLISHED
            self._generation = 1
            self._current_snapshot = target
            self._current_source_binding = target.source_binding_sha256
            self._current_projection = target.projection_result.projection_bytes
            self._receipts = receipts
            self._semantic_results = semantic
            self._projections = projections
            self._events = events
            self._audits = audits
            self._outbox = outbox
            return result

    def rollback(self, command: RollbackCommandV2) -> PublicationCommandResultV2:
        if type(command) is not RollbackCommandV2:
            fail_publication_command()
        request_bytes = command.canonical_bytes()
        with self._lock:
            replay = self._replay(
                key=command.idempotency_key,
                request_bytes=request_bytes,
            )
            if replay is not None:
                return replay
            self._sources.require_valid()
            if (
                self._state is not PublicationLocalState.PUBLISHED
                or self._current_snapshot is None
                or self._current_source_binding
                != self._current_snapshot.source_binding_sha256
                or self._current_projection
                != self._current_snapshot.projection_result.projection_bytes
            ):
                fail_publication_command(
                    PublicationCommandFailureCode.PUBLICATION_STATE_DRIFT
                )
            if (
                command.publication_id != self._sources.publication_id
                or command.expected_generation != self._generation
                or command.from_snapshot_id != self._current_snapshot.snapshot_id
                or command.expected_from_source_binding_sha256
                != self._current_snapshot.source_binding_sha256
            ):
                fail_publication_command(
                    PublicationCommandFailureCode.PUBLICATION_STATE_DRIFT
                )
            target = self._sources.by_id(command.to_snapshot_id)
            if target is None:
                fail_publication_command(
                    PublicationCommandFailureCode.ROLLBACK_TARGET_UNKNOWN
                )
            if target.snapshot_id == self._current_snapshot.snapshot_id:
                fail_publication_command(
                    PublicationCommandFailureCode.ROLLBACK_TARGET_CURRENT
                )
            current_index = self._sources.index(self._current_snapshot.snapshot_id)
            target_index = self._sources.index(target.snapshot_id)
            if (
                current_index is None
                or target_index is None
                or target_index >= current_index
            ):
                fail_publication_command(
                    PublicationCommandFailureCode.ROLLBACK_TARGET_NOT_PREVIOUS
                )
            if (
                command.expected_to_source_binding_sha256
                != target.source_binding_sha256
            ):
                fail_publication_command(
                    PublicationCommandFailureCode.SOURCE_HASH_MISMATCH
                )
            next_generation = self._generation + 1
            result = build_rollback_result_v2(
                command=command,
                current=self._current_snapshot,
                target=target,
                generation=next_generation,
            )
            semantic_key = (
                PublicationCommandAction.ROLLBACK,
                f"{self._current_snapshot.snapshot_id}:{target.snapshot_id}",
            )
            (
                receipts,
                semantic,
                projections,
                events,
                audits,
                outbox,
            ) = self._stage_records(
                request_bytes=request_bytes,
                key=command.idempotency_key,
                semantic_key=semantic_key,
                result=result,
            )
            self._generation = next_generation
            self._current_snapshot = target
            self._current_source_binding = target.source_binding_sha256
            self._current_projection = target.projection_result.projection_bytes
            self._receipts = receipts
            self._semantic_results = semantic
            self._projections = projections
            self._events = events
            self._audits = audits
            self._outbox = outbox
            return result

    def snapshot(self) -> PublicationStoreSnapshotV2:
        with self._lock:
            return PublicationStoreSnapshotV2(
                state=self._state,
                generation=self._generation,
                current_snapshot_id=(
                    self._current_snapshot.snapshot_id
                    if self._current_snapshot is not None
                    else None
                ),
                current_source_binding_sha256=self._current_source_binding,
                current_projection_sha256=(
                    self._current_snapshot.projection_result.projection_sha256
                    if self._current_snapshot is not None
                    else None
                ),
                idempotency_receipts=len(self._receipts),
                projection_records=len(self._projections),
                event_intents=len(self._events),
                audit_intents=len(self._audits),
                outbox_intents=len(self._outbox),
            )

    def __repr__(self) -> str:
        return "RecordedPublicationCommandStoreV2(<redacted-st0905-v2>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("publication command store serialization is forbidden")


__all__ = (
    "RecordedPublicationCommandStoreV2",
    "TransactionFailurePoint",
)

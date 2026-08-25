"""Maximum-safe owner-private application service for ST-0603 V2."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar, final

from raos.domain.evidence.fact_conflict_runtime_v2 import (
    FactConflictDetectionBatchV2,
    FactConflictDetectionResultV2,
    FactConflictFailureCodeV2,
    FactConflictFailureV2,
    FactConflictReplayStatusV2,
    FactConflictScanCommandV2,
    FactConflictStoreCommitV2,
    FactConflictsRecordedOutboxEventV2,
    PersistedFactConflictDetectionV2,
    batch_from_mapping_v2,
    batch_mapping_v2,
    build_fact_conflict_artifacts_v2,
    command_from_mapping_v2,
    command_mapping_v2,
    event_from_mapping_v2,
    event_mapping_v2,
    fail_fact_conflict_v2,
    persisted_from_mapping_v2,
    persisted_mapping_v2,
)
from raos.domain.evidence.fact_extraction_runtime_v2 import (
    PersistedFactExtractionV2,
)
from raos.ports.fact_conflict_runtime_v2 import FactConflictUnitOfWorkStoreV2


T = TypeVar("T")


def _failure_code(
    error: FactConflictFailureV2,
    fallback: FactConflictFailureCodeV2,
) -> FactConflictFailureCodeV2:
    if type(error) is FactConflictFailureV2:
        try:
            code = error.code
        except Exception:
            return fallback
        if type(code) is FactConflictFailureCodeV2:
            return code
    return fallback


def _collaborator_call(
    call: Callable[[], T],
    *,
    failure_code: FactConflictFailureCodeV2,
) -> T:
    try:
        return call()
    except FactConflictFailureV2 as error:
        code = _failure_code(error, failure_code)
    except Exception:
        code = failure_code
    fail_fact_conflict_v2(code)


def _copy_persisted(value: object) -> PersistedFactConflictDetectionV2:
    if type(value) is not PersistedFactConflictDetectionV2:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)
    try:
        return persisted_from_mapping_v2(persisted_mapping_v2(value))
    except Exception:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)


def _validate_exact_result(
    persisted: object,
    *,
    command: FactConflictScanCommandV2,
    batch: FactConflictDetectionBatchV2,
    event: FactConflictsRecordedOutboxEventV2,
) -> PersistedFactConflictDetectionV2:
    copied = _copy_persisted(persisted)
    if (
        copied.command != command
        or copied.batch != batch
        or copied.event != event
        or copied.command.idempotency_key != command.idempotency_key
    ):
        fail_fact_conflict_v2(FactConflictFailureCodeV2.IDEMPOTENCY_CONFLICT)
    _assert_zero_actions(copied)
    return copied


def _copy_artifacts(
    command: object,
    batch: object,
    event: object,
) -> tuple[
    FactConflictScanCommandV2,
    FactConflictDetectionBatchV2,
    FactConflictsRecordedOutboxEventV2,
]:
    if (
        type(command) is not FactConflictScanCommandV2
        or type(batch) is not FactConflictDetectionBatchV2
        or type(event) is not FactConflictsRecordedOutboxEventV2
    ):
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)
    try:
        copied_command = command_from_mapping_v2(command_mapping_v2(command))
        copied_batch = batch_from_mapping_v2(batch_mapping_v2(batch))
        copied_event = event_from_mapping_v2(event_mapping_v2(event))
    except Exception:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)
    if (
        copied_command != command
        or copied_batch != batch
        or copied_event != event
        or copied_batch.command != copied_command
        or copied_event != FactConflictsRecordedOutboxEventV2.from_batch(copied_batch)
    ):
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)
    if (
        copied_batch.external_action_count != 0
        or copied_batch.provider_action_count != 0
        or copied_batch.publication_action_count != 0
        or copied_batch.ai_action_count != 0
        or copied_event.external_action_count != 0
    ):
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)
    return copied_command, copied_batch, copied_event


def _assert_artifacts_unchanged(
    candidate: tuple[
        FactConflictScanCommandV2,
        FactConflictDetectionBatchV2,
        FactConflictsRecordedOutboxEventV2,
    ],
    expected: tuple[
        FactConflictScanCommandV2,
        FactConflictDetectionBatchV2,
        FactConflictsRecordedOutboxEventV2,
    ],
) -> None:
    if _copy_artifacts(*candidate) != expected:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)


def _assert_zero_actions(value: PersistedFactConflictDetectionV2) -> None:
    if (
        value.batch.external_action_count != 0
        or value.batch.provider_action_count != 0
        or value.batch.publication_action_count != 0
        or value.batch.ai_action_count != 0
        or value.event.external_action_count != 0
    ):
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)


@final
class DurableFactConflictDetectionServiceV2:
    """Detect and atomically record unresolved exact Fact conflicts locally."""

    __slots__ = ("_store",)

    def __init__(self, store: object) -> None:
        if not isinstance(store, FactConflictUnitOfWorkStoreV2):
            fail_fact_conflict_v2()
        self._store = store

    def _verify_store(self) -> tuple[str, int]:
        value = _collaborator_call(
            self._store.verify_chain,
            failure_code=FactConflictFailureCodeV2.STORE_UNAVAILABLE,
        )
        if (
            type(value) is not tuple
            or len(value) != 2
            or type(value[0]) is not str
            or len(value[0]) != 64
            or any(character not in "0123456789abcdef" for character in value[0])
            or type(value[1]) is not int
            or value[1] < 0
        ):
            fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)
        return value

    def _finish(
        self,
        persisted: PersistedFactConflictDetectionV2,
        status: FactConflictReplayStatusV2,
    ) -> FactConflictDetectionResultV2:
        _assert_zero_actions(persisted)
        _head, count = self._verify_store()
        _assert_zero_actions(persisted)
        if count < persisted.sequence:
            fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)
        return FactConflictDetectionResultV2(
            persisted=persisted,
            replay_status=status,
            external_action_count=0,
            provider_action_count=0,
            publication_action_count=0,
            ai_action_count=0,
        )

    def _recover_unknown_commit(
        self,
        *,
        command: FactConflictScanCommandV2,
        batch: FactConflictDetectionBatchV2,
        event: FactConflictsRecordedOutboxEventV2,
    ) -> FactConflictDetectionResultV2:
        expected = _copy_artifacts(command, batch, event)
        candidate = _copy_artifacts(command, batch, event)
        recovered = _collaborator_call(
            lambda: self._store.recover_exact(candidate[0]),
            failure_code=FactConflictFailureCodeV2.COMMIT_UNKNOWN,
        )
        _assert_artifacts_unchanged(candidate, expected)
        if recovered is None:
            fail_fact_conflict_v2(FactConflictFailureCodeV2.COMMIT_UNKNOWN)
        return self._finish(
            _validate_exact_result(
                recovered,
                command=expected[0],
                batch=expected[1],
                event=expected[2],
            ),
            FactConflictReplayStatusV2.RECOVERED_COMMIT,
        )

    def detect(
        self,
        *,
        inputs: tuple[PersistedFactExtractionV2, ...],
    ) -> FactConflictDetectionResultV2:
        expected = _copy_artifacts(*build_fact_conflict_artifacts_v2(inputs))
        self._verify_store()
        expected = _copy_artifacts(*expected)
        candidate = _copy_artifacts(*expected)
        existing = _collaborator_call(
            lambda: self._store.lookup(candidate[0]),
            failure_code=FactConflictFailureCodeV2.STORE_UNAVAILABLE,
        )
        _assert_artifacts_unchanged(candidate, expected)
        if existing is not None:
            return self._finish(
                _validate_exact_result(
                    existing,
                    command=expected[0],
                    batch=expected[1],
                    event=expected[2],
                ),
                FactConflictReplayStatusV2.IDEMPOTENT_REPLAY,
            )
        candidate = _copy_artifacts(*expected)
        try:
            commit = self._store.commit(
                command=candidate[0],
                batch=candidate[1],
                event=candidate[2],
            )
        except FactConflictFailureV2 as error:
            _assert_artifacts_unchanged(candidate, expected)
            code = _failure_code(
                error,
                FactConflictFailureCodeV2.STORE_UNAVAILABLE,
            )
            if code is not FactConflictFailureCodeV2.COMMIT_UNKNOWN:
                fail_fact_conflict_v2(code)
            return self._recover_unknown_commit(
                command=expected[0],
                batch=expected[1],
                event=expected[2],
            )
        except Exception:
            _assert_artifacts_unchanged(candidate, expected)
            return self._recover_unknown_commit(
                command=expected[0],
                batch=expected[1],
                event=expected[2],
            )
        _assert_artifacts_unchanged(candidate, expected)
        if type(commit) is not FactConflictStoreCommitV2:
            fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)
        persisted = _validate_exact_result(
            commit.persisted,
            command=expected[0],
            batch=expected[1],
            event=expected[2],
        )
        status = (
            FactConflictReplayStatusV2.IDEMPOTENT_REPLAY
            if commit.replayed
            else FactConflictReplayStatusV2.DIRECT_COMMIT
        )
        return self._finish(persisted, status)


__all__ = ["DurableFactConflictDetectionServiceV2"]

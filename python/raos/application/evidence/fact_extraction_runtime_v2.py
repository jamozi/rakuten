"""Maximum-safe recorded-local application service for ST-0602 V2."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar, final

from raos.domain.catalog.catalog_normalization_runtime_v2 import (
    PersistedCatalogNormalizationV2,
)
from raos.domain.evidence.fact_extraction_runtime_v2 import (
    FactExtractionBatchV2,
    FactExtractionCommandV2,
    FactExtractionFailureCodeV2,
    FactExtractionFailureV2,
    FactExtractionReplayStatusV2,
    FactExtractionResultV2,
    FactStoreCommitV2,
    FactsExtractedOutboxEventV2,
    PersistedFactExtractionV2,
    build_fact_extraction_artifacts_v2,
    fail_fact_extraction_v2,
    persisted_from_mapping_v2,
    persisted_mapping_v2,
)
from raos.domain.ops.artifact_registry_runtime_v2 import ArtifactReadbackV2
from raos.ports.fact_extraction_runtime_v2 import (
    FactExtractionUnitOfWorkStoreV2,
)


T = TypeVar("T")


def _failure_code(
    error: FactExtractionFailureV2,
    fallback: FactExtractionFailureCodeV2,
) -> FactExtractionFailureCodeV2:
    if type(error) is FactExtractionFailureV2:
        try:
            code = error.code
        except Exception:
            return fallback
        if type(code) is FactExtractionFailureCodeV2:
            return code
    return fallback


def _collaborator_call(
    call: Callable[[], T],
    *,
    failure_code: FactExtractionFailureCodeV2,
) -> T:
    try:
        return call()
    except FactExtractionFailureV2 as error:
        code = _failure_code(error, failure_code)
    except Exception:
        code = failure_code
    fail_fact_extraction_v2(code)


def _copy_persisted(value: object) -> PersistedFactExtractionV2:
    if type(value) is not PersistedFactExtractionV2:
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
    return persisted_from_mapping_v2(persisted_mapping_v2(value))


def _validate_exact_result(
    persisted: object,
    *,
    command: FactExtractionCommandV2,
    batch: FactExtractionBatchV2,
    event: FactsExtractedOutboxEventV2,
) -> PersistedFactExtractionV2:
    copied = _copy_persisted(persisted)
    if (
        copied.command != command
        or copied.batch != batch
        or copied.event != event
        or copied.command.idempotency_key != command.idempotency_key
    ):
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.IDEMPOTENCY_CONFLICT)
    return copied


@final
class DurableFactExtractionServiceV2:
    """Extract and atomically record exact OFFER facts with zero external action."""

    __slots__ = ("_store",)

    def __init__(self, store: object) -> None:
        if not isinstance(store, FactExtractionUnitOfWorkStoreV2):
            fail_fact_extraction_v2()
        self._store = store

    def _verify_store(self) -> tuple[str, int]:
        value = _collaborator_call(
            self._store.verify_chain,
            failure_code=FactExtractionFailureCodeV2.STORE_UNAVAILABLE,
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
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
        return value

    def _finish(
        self,
        persisted: PersistedFactExtractionV2,
        status: FactExtractionReplayStatusV2,
    ) -> FactExtractionResultV2:
        _head, count = self._verify_store()
        if count < persisted.sequence:
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
        return FactExtractionResultV2(
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
        command: FactExtractionCommandV2,
        batch: FactExtractionBatchV2,
        event: FactsExtractedOutboxEventV2,
    ) -> FactExtractionResultV2:
        recovered = _collaborator_call(
            lambda: self._store.recover_exact(command),
            failure_code=FactExtractionFailureCodeV2.COMMIT_UNKNOWN,
        )
        if recovered is None:
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.COMMIT_UNKNOWN)
        return self._finish(
            _validate_exact_result(
                recovered,
                command=command,
                batch=batch,
                event=event,
            ),
            FactExtractionReplayStatusV2.RECOVERED_COMMIT,
        )

    def extract(
        self,
        *,
        artifact: ArtifactReadbackV2,
        normalization: PersistedCatalogNormalizationV2,
    ) -> FactExtractionResultV2:
        command, batch, event = build_fact_extraction_artifacts_v2(
            artifact=artifact,
            normalization=normalization,
        )
        self._verify_store()
        existing = _collaborator_call(
            lambda: self._store.lookup(command),
            failure_code=FactExtractionFailureCodeV2.STORE_UNAVAILABLE,
        )
        if existing is not None:
            return self._finish(
                _validate_exact_result(
                    existing,
                    command=command,
                    batch=batch,
                    event=event,
                ),
                FactExtractionReplayStatusV2.IDEMPOTENT_REPLAY,
            )
        try:
            commit = self._store.commit(
                command=command,
                batch=batch,
                event=event,
            )
        except FactExtractionFailureV2 as error:
            code = _failure_code(
                error,
                FactExtractionFailureCodeV2.STORE_UNAVAILABLE,
            )
            if code is not FactExtractionFailureCodeV2.COMMIT_UNKNOWN:
                fail_fact_extraction_v2(code)
            return self._recover_unknown_commit(
                command=command,
                batch=batch,
                event=event,
            )
        except Exception:
            return self._recover_unknown_commit(
                command=command,
                batch=batch,
                event=event,
            )
        if type(commit) is not FactStoreCommitV2:
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
        persisted = _validate_exact_result(
            commit.persisted,
            command=command,
            batch=batch,
            event=event,
        )
        status = (
            FactExtractionReplayStatusV2.IDEMPOTENT_REPLAY
            if commit.replayed
            else FactExtractionReplayStatusV2.DIRECT_COMMIT
        )
        return self._finish(persisted, status)


__all__ = ["DurableFactExtractionServiceV2"]

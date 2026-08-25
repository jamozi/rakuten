"""Fail-closed dependency and metamorphic checks for ST-0602 V2."""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import timedelta
from itertools import permutations

import pytest

from raos.application.evidence.fact_extraction_runtime_v2 import (
    DurableFactExtractionServiceV2,
)
from raos.domain.catalog.catalog_normalization_runtime_v2 import (
    catalog_chain_hash_v2,
)
from raos.domain.evidence.fact_extraction_runtime_v2 import (
    FactExtractionFailureCodeV2,
    FactExtractionFailureV2,
    FactExtractionReplayStatusV2,
    build_fact_extraction_artifacts_v2,
)
from tests.st0602.runtime_v2_fixtures import (
    exact_dependencies_v2,
    fact_store_v2,
)


def _code(call) -> FactExtractionFailureCodeV2:
    with pytest.raises(FactExtractionFailureV2) as captured:
        call()
    return captured.value.code


def test_non_exact_dependency_objects_are_rejected(tmp_path) -> None:
    dependencies = exact_dependencies_v2(tmp_path)

    class Spoof:
        pass

    assert (
        _code(
            lambda: build_fact_extraction_artifacts_v2(
                artifact=Spoof(),  # type: ignore[arg-type]
                normalization=dependencies.normalization,
            )
        )
        is FactExtractionFailureCodeV2.DEPENDENCY_MISMATCH
    )
    assert (
        _code(
            lambda: build_fact_extraction_artifacts_v2(
                artifact=dependencies.artifact,
                normalization=Spoof(),  # type: ignore[arg-type]
            )
        )
        is FactExtractionFailureCodeV2.DEPENDENCY_MISMATCH
    )


def test_bypassed_artifact_content_mismatch_is_revalidated(tmp_path) -> None:
    dependencies = exact_dependencies_v2(tmp_path)
    forged = object.__new__(type(dependencies.artifact))
    object.__setattr__(forged, "record", dependencies.artifact.record)
    object.__setattr__(forged, "content", dependencies.artifact.content + b"x")
    assert (
        _code(
            lambda: build_fact_extraction_artifacts_v2(
                artifact=forged,
                normalization=dependencies.normalization,
            )
        )
        is FactExtractionFailureCodeV2.DEPENDENCY_MISMATCH
    )


def test_source_snapshot_and_catalog_event_binding_are_exact(tmp_path) -> None:
    dependencies = exact_dependencies_v2(tmp_path)
    event = dependencies.normalization.event
    bad_event = object.__new__(type(event))
    for field in fields(event):
        value = getattr(event, field.name)
        if field.name == "observation_count":
            value -= 1
        object.__setattr__(bad_event, field.name, value)
    forged = object.__new__(type(dependencies.normalization))
    object.__setattr__(forged, "operation_id", dependencies.normalization.operation_id)
    object.__setattr__(
        forged, "payload_fingerprint", dependencies.normalization.payload_fingerprint
    )
    object.__setattr__(
        forged, "catalog_version", dependencies.normalization.catalog_version
    )
    object.__setattr__(
        forged, "previous_chain_hash", dependencies.normalization.previous_chain_hash
    )
    object.__setattr__(forged, "chain_hash", dependencies.normalization.chain_hash)
    object.__setattr__(forged, "batch", dependencies.normalization.batch)
    object.__setattr__(forged, "event", bad_event)
    object.__setattr__(forged, "committed_at", dependencies.normalization.committed_at)
    assert (
        _code(
            lambda: build_fact_extraction_artifacts_v2(
                artifact=dependencies.artifact,
                normalization=forged,
            )
        )
        is FactExtractionFailureCodeV2.DEPENDENCY_MISMATCH
    )


@pytest.mark.parametrize("target", ("batch", "event"))
def test_dependency_action_count_rejects_boolean_zero(tmp_path, target: str) -> None:
    dependencies = exact_dependencies_v2(tmp_path)
    persisted = dependencies.normalization
    batch = replace(
        persisted.batch,
        external_actions=False if target == "batch" else 0,
    )
    event = replace(
        persisted.event,
        external_actions=False if target == "event" else 0,
    )
    chain_hash = catalog_chain_hash_v2(
        previous_chain_hash=persisted.previous_chain_hash,
        catalog_version=persisted.catalog_version,
        operation_id=persisted.operation_id,
        batch_sha256=batch.sha256,
        event_sha256=event.sha256,
        committed_at=persisted.committed_at,
    )
    forged = object.__new__(type(persisted))
    for field in fields(persisted):
        value = getattr(persisted, field.name)
        if field.name == "batch":
            value = batch
        elif field.name == "event":
            value = event
        elif field.name == "chain_hash":
            value = chain_hash
        object.__setattr__(forged, field.name, value)
    assert (
        _code(
            lambda: build_fact_extraction_artifacts_v2(
                artifact=dependencies.artifact,
                normalization=forged,
            )
        )
        is FactExtractionFailureCodeV2.SOURCE_INTEGRITY
    )


def test_all_non_identity_fact_permutations_fail_closed(tmp_path) -> None:
    dependencies = exact_dependencies_v2(tmp_path, item_ordinals=(1,))
    _command, batch, _event = build_fact_extraction_artifacts_v2(
        artifact=dependencies.artifact,
        normalization=dependencies.normalization,
    )
    identity = tuple(range(len(batch.facts)))
    for ordering in permutations(identity):
        if ordering == identity:
            continue
        assert (
            _code(
                lambda ordering=ordering: replace(
                    batch,
                    facts=tuple(batch.facts[index] for index in ordering),
                    validations=tuple(batch.validations[index] for index in ordering),
                )
            )
            is FactExtractionFailureCodeV2.INVALID_ARGUMENT
        )


def test_time_and_locator_mismatches_never_default(tmp_path) -> None:
    dependencies = exact_dependencies_v2(tmp_path, item_ordinals=(1,))
    _command, batch, _event = build_fact_extraction_artifacts_v2(
        artifact=dependencies.artifact,
        normalization=dependencies.normalization,
    )
    fact = batch.facts[0]
    assert (
        _code(lambda: replace(fact, created_at=fact.valid_from - timedelta(seconds=1)))
        is FactExtractionFailureCodeV2.TIME_INVALID
    )
    assert (
        _code(
            lambda: replace(
                fact,
                locator=replace(fact.locator, pointer="/observations/999"),
            )
        )
        is FactExtractionFailureCodeV2.INVALID_ARGUMENT
    )


class _SpoofingStore:
    def __init__(self, actual) -> None:
        self.actual = actual

    def lookup(self, command):
        return self.actual.lookup(command)

    def commit(self, *, command, batch, event):
        committed = self.actual.commit(command=command, batch=batch, event=event)
        forged = object.__new__(type(committed.persisted))
        object.__setattr__(forged, "sequence", committed.persisted.sequence)
        object.__setattr__(
            forged, "previous_chain_hash", committed.persisted.previous_chain_hash
        )
        object.__setattr__(forged, "chain_hash", "f" * 64)
        object.__setattr__(forged, "command", committed.persisted.command)
        object.__setattr__(forged, "batch", committed.persisted.batch)
        object.__setattr__(forged, "event", committed.persisted.event)
        object.__setattr__(forged, "committed_at", committed.persisted.committed_at)
        return replace(committed, persisted=forged)

    def recover_exact(self, command):
        return self.actual.recover_exact(command)

    def load_batch(self, batch_id):
        return self.actual.load_batch(batch_id)

    def load_fact(self, fact_id):
        return self.actual.load_fact(fact_id)

    def list_validations(self, batch_id):
        return self.actual.list_validations(batch_id)

    def load_outbox(self, event_id):
        return self.actual.load_outbox(event_id)

    def verify_chain(self):
        return self.actual.verify_chain()


def test_collaborator_result_spoofing_is_detected(tmp_path) -> None:
    dependencies = exact_dependencies_v2(tmp_path)
    service = DurableFactExtractionServiceV2(_SpoofingStore(fact_store_v2(tmp_path)))
    assert (
        _code(
            lambda: service.extract(
                artifact=dependencies.artifact,
                normalization=dependencies.normalization,
            )
        )
        is FactExtractionFailureCodeV2.TAMPER_DETECTED
    )


def test_all_result_action_counts_are_exact_zero(tmp_path) -> None:
    dependencies = exact_dependencies_v2(tmp_path)
    result = DurableFactExtractionServiceV2(fact_store_v2(tmp_path)).extract(
        artifact=dependencies.artifact,
        normalization=dependencies.normalization,
    )
    assert result.replay_status is FactExtractionReplayStatusV2.DIRECT_COMMIT
    assert (
        type(result.external_action_count),
        type(result.provider_action_count),
        type(result.publication_action_count),
        type(result.ai_action_count),
    ) == (int, int, int, int)
    assert (
        result.external_action_count
        + result.provider_action_count
        + result.publication_action_count
        + result.ai_action_count
    ) == 0

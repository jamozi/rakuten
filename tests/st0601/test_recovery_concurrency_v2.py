"""Atomic rollback, ambiguous recovery, and concurrent CAS checks."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from raos.adapters.sqlite_artifact_registry_runtime_v2 import (
    RecordedArtifactRegistryFaultV2,
)
from raos.domain.ops.artifact_registry_runtime_v2 import (
    ARTIFACT_REGISTRY_GENESIS_SHA256_V2,
    ArtifactRegistryCommitV2,
    ArtifactRegistryRuntimeFailureCodeV2,
    ArtifactRegistryRuntimeFailureV2,
)

from .runtime_v2_fixtures import (
    BODY_ONE,
    BODY_TWO,
    command_for,
    private_root,
    receipt_for,
    request_for,
    service_for,
)


def test_known_rollback_leaves_no_object_or_operation(tmp_path: Path) -> None:
    receipt = receipt_for()
    service, factory = service_for(private_root(tmp_path), (receipt, BODY_ONE))
    factory.set_fault(RecordedArtifactRegistryFaultV2.AFTER_OBJECT_BEFORE_OPERATION)

    with pytest.raises(ArtifactRegistryRuntimeFailureV2) as caught:
        service.register(request_for(receipt))

    assert caught.value.code is (
        ArtifactRegistryRuntimeFailureCodeV2.COMMIT_KNOWN_ROLLBACK
    )
    assert factory.open().verify_chain() == (
        ARTIFACT_REGISTRY_GENESIS_SHA256_V2,
        0,
    )
    committed = service.register(request_for(receipt))
    assert committed.record.sequence == 1


def test_after_commit_ambiguity_recovers_exact_once(tmp_path: Path) -> None:
    receipt = receipt_for()
    service, factory = service_for(private_root(tmp_path), (receipt, BODY_ONE))
    factory.set_fault(RecordedArtifactRegistryFaultV2.AFTER_COMMIT)

    committed = service.register(request_for(receipt))

    assert committed.recovered_after_commit_ambiguity is True
    assert committed.receipt.replayed is True
    assert factory.open().verify_chain() == (committed.record.entry_sha256, 1)
    assert service.register(request_for(receipt)).record == committed.record


def test_recovery_refuses_missing_and_mismatched_operation(tmp_path: Path) -> None:
    receipt = receipt_for()
    service, factory = service_for(private_root(tmp_path), (receipt, BODY_ONE))
    store = factory.open()
    missing = command_for(receipt, label="missing-operation")

    with pytest.raises(ArtifactRegistryRuntimeFailureV2) as missing_error:
        store.recover_exact(missing)
    assert missing_error.value.code is (
        ArtifactRegistryRuntimeFailureCodeV2.RECOVERY_NOT_FOUND
    )

    service.register(request_for(receipt, label="stored-operation"))
    mismatched = command_for(
        receipt,
        label="stored-operation",
        expected_latest_version=1,
    )
    with pytest.raises(ArtifactRegistryRuntimeFailureV2) as mismatch_error:
        store.recover_exact(mismatched)
    assert mismatch_error.value.code is (
        ArtifactRegistryRuntimeFailureCodeV2.IDEMPOTENCY_CONFLICT
    )


def test_concurrent_same_operation_is_one_append_plus_replay(tmp_path: Path) -> None:
    receipt = receipt_for()
    service, factory = service_for(private_root(tmp_path), (receipt, BODY_ONE))
    request = request_for(receipt)

    def register_once(index: int) -> ArtifactRegistryCommitV2:
        del index
        return service.register(request)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(register_once, range(2)))

    assert results[0].record == results[1].record
    assert sorted(result.receipt.replayed for result in results) == [False, True]
    assert factory.open().verify_chain() == (results[0].record.entry_sha256, 1)


def test_concurrent_new_receipts_with_same_cas_allow_only_one(
    tmp_path: Path,
) -> None:
    first_receipt = receipt_for()
    second_receipt = receipt_for(
        BODY_TWO,
        label="receipt-two",
        artifact_version=2,
        observed_offset_seconds=60,
    )
    service, factory = service_for(
        private_root(tmp_path),
        (first_receipt, BODY_ONE),
        (second_receipt, BODY_TWO),
    )
    requests = (
        request_for(first_receipt, label="operation-one"),
        request_for(second_receipt, label="operation-two"),
    )

    def attempt(index: int) -> object:
        try:
            return service.register(requests[index])
        except ArtifactRegistryRuntimeFailureV2 as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(attempt, range(2)))

    failures = [
        value
        for value in results
        if value is ArtifactRegistryRuntimeFailureCodeV2.CONCURRENCY_CONFLICT
    ]
    successes = [value for value in results if value not in failures]
    assert len(failures) == 1
    assert len(successes) == 1
    assert factory.open().verify_chain()[1] == 1

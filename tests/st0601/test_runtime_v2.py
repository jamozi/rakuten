"""Durable registration, exact readback, version, and replay checks."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from raos.domain.ops.artifact_registry_runtime_v2 import (
    ARTIFACT_REGISTRY_BUCKET_V2,
    ARTIFACT_REGISTRY_EXTERNAL_ACTION_COUNT_V2,
    ARTIFACT_REGISTRY_PROVIDER_ACTION_COUNT_V2,
    ARTIFACT_REGISTRY_PUBLICATION_ACTION_COUNT_V2,
    ArtifactRegistryRetentionStateV2,
    ArtifactRegistryRuntimeFailureCodeV2,
    ArtifactRegistryRuntimeFailureV2,
    ArtifactRegistryStorageProviderV2,
)
from raos.domain.ops.enums import ObjectArtifactArtifactKind
from raos.domain.ops.ids import ObjectArtifactId

from .runtime_v2_fixtures import (
    BODY_ONE,
    BODY_TWO,
    private_root,
    receipt_for,
    request_for,
    service_for,
)


def test_register_binds_original_metadata_and_exact_local_readback(
    tmp_path: Path,
) -> None:
    receipt = receipt_for()
    service, factory = service_for(
        private_root(tmp_path),
        (receipt, BODY_ONE),
    )

    commit = service.register(request_for(receipt))
    record = commit.record
    readback = service.readback(record.artifact_ref)

    assert (
        record.candidate.artifact_kind
        is ObjectArtifactArtifactKind.RAW_PROVIDER_RESPONSE
    )
    assert type(record.artifact_id) is ObjectArtifactId
    assert record.display_id.startswith("OBJ-")
    assert record.artifact_version == 1
    assert record.artifact_ref.storage_provider is (
        ArtifactRegistryStorageProviderV2.RECORDED_LOCAL_SQLITE
    )
    assert record.artifact_ref.bucket_name == ARTIFACT_REGISTRY_BUCKET_V2
    assert record.artifact_ref.object_key == record.candidate.logical_key
    assert record.artifact_ref.sha256 == receipt.artifact_sha256
    assert record.candidate.byte_size == receipt.byte_size
    assert record.candidate.content_type == "application/json"
    assert record.candidate.provenance.source_receipt_id == receipt.receipt_id
    assert record.candidate.provenance.source_artifact_version == (
        receipt.artifact_version
    )
    assert record.candidate.provenance.source_logical_key == receipt.logical_key
    assert record.candidate.provenance.acquired_at == receipt.observed_at
    assert readback.record == record
    assert readback.content == BODY_ONE
    assert commit.receipt.replayed is False
    assert commit.recovered_after_commit_ambiguity is False
    assert factory.database_path.stat().st_mode & 0o777 == 0o600


def test_retention_and_external_authority_are_structurally_absent(
    tmp_path: Path,
) -> None:
    receipt = receipt_for()
    service, _ = service_for(private_root(tmp_path), (receipt, BODY_ONE))
    commit = service.register(request_for(receipt))

    assert commit.record.retention_state is (
        ArtifactRegistryRetentionStateV2.OD_014_UNRESOLVED
    )
    assert commit.record.retention_class is None
    assert commit.record.retention_period is None
    assert commit.record.object_storage_attestation == "NOT_CLAIMED"
    assert commit.external_action_count == ARTIFACT_REGISTRY_EXTERNAL_ACTION_COUNT_V2
    assert commit.provider_action_count == ARTIFACT_REGISTRY_PROVIDER_ACTION_COUNT_V2
    assert commit.publication_action_count == (
        ARTIFACT_REGISTRY_PUBLICATION_ACTION_COUNT_V2
    )
    assert service.external_action_count == 0


def test_exact_operation_replay_returns_same_record_without_new_version(
    tmp_path: Path,
) -> None:
    receipt = receipt_for()
    service, factory = service_for(private_root(tmp_path), (receipt, BODY_ONE))
    request = request_for(receipt)

    first = service.register(request)
    second = service.register(request)

    assert second.record == first.record
    assert second.receipt.artifact_ref == first.receipt.artifact_ref
    assert second.receipt.replayed is True
    assert factory.open().verify_chain() == (first.record.entry_sha256, 1)


def test_same_source_receipt_with_new_operation_is_semantic_replay(
    tmp_path: Path,
) -> None:
    receipt = receipt_for()
    service, factory = service_for(private_root(tmp_path), (receipt, BODY_ONE))
    first = service.register(request_for(receipt, label="operation-a"))
    second = service.register(request_for(receipt, label="operation-b"))

    assert second.record == first.record
    assert second.receipt.operation_id != first.receipt.operation_id
    assert second.receipt.replayed is True
    assert factory.open().verify_chain()[1] == 1


def test_source_receipt_replay_requires_original_cas_precondition(
    tmp_path: Path,
) -> None:
    receipt = receipt_for()
    service, factory = service_for(private_root(tmp_path), (receipt, BODY_ONE))
    first = service.register(request_for(receipt, label="operation-a"))

    with pytest.raises(ArtifactRegistryRuntimeFailureV2) as caught:
        service.register(
            request_for(
                receipt,
                label="operation-b",
                expected_latest_version=1,
            )
        )

    assert caught.value.code is (
        ArtifactRegistryRuntimeFailureCodeV2.IDEMPOTENCY_CONFLICT
    )
    assert factory.open().verify_chain() == (first.record.entry_sha256, 1)


def test_two_receipts_for_same_logical_key_append_exact_versions(
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

    first = service.register(request_for(first_receipt, label="operation-a"))
    second = service.register(
        request_for(
            second_receipt,
            label="operation-b",
            expected_latest_version=1,
        )
    )

    assert first.record.candidate.logical_key == second.record.candidate.logical_key
    assert first.record.artifact_version == 1
    assert second.record.artifact_version == 2
    assert first.record.artifact_id != second.record.artifact_id
    assert service.readback(first.record.artifact_ref).content == BODY_ONE
    assert service.readback(second.record.artifact_ref).content == BODY_TWO
    assert factory.open().verify_chain() == (second.record.entry_sha256, 2)


def test_deterministic_identity_and_reference_match_across_fresh_stores(
    tmp_path: Path,
) -> None:
    receipt = receipt_for()
    first_service, _ = service_for(
        private_root(tmp_path, name="first"),
        (receipt, BODY_ONE),
    )
    second_service, _ = service_for(
        private_root(tmp_path, name="second"),
        (receipt, BODY_ONE),
    )

    first = first_service.register(request_for(receipt))
    second = second_service.register(request_for(receipt))

    assert second.record.artifact_id == first.record.artifact_id
    assert second.record.display_id == first.record.display_id
    assert second.record.artifact_ref == first.record.artifact_ref
    assert second.record.entry_sha256 == first.record.entry_sha256
    assert second.record.record_sha256 == first.record.record_sha256


def test_restart_reads_same_bytes_record_and_chain(tmp_path: Path) -> None:
    receipt = receipt_for()
    root = private_root(tmp_path)
    service, _ = service_for(root, (receipt, BODY_ONE))
    committed = service.register(request_for(receipt))

    restarted, restarted_factory = service_for(root, (receipt, BODY_ONE))

    assert restarted.readback(committed.record.artifact_ref).content == BODY_ONE
    assert restarted.register(request_for(receipt)).receipt.replayed is True
    assert restarted_factory.open().verify_chain() == (
        committed.record.entry_sha256,
        1,
    )


def test_stale_version_cas_rejects_without_partial_append(tmp_path: Path) -> None:
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
    first = service.register(request_for(first_receipt, label="operation-a"))

    with pytest.raises(ArtifactRegistryRuntimeFailureV2) as caught:
        service.register(request_for(second_receipt, label="operation-b"))

    assert caught.value.code is (
        ArtifactRegistryRuntimeFailureCodeV2.CONCURRENCY_CONFLICT
    )
    assert factory.open().verify_chain() == (first.record.entry_sha256, 1)


def test_operation_id_reuse_with_different_request_is_rejected(
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
    first = service.register(request_for(first_receipt, label="same-operation"))

    with pytest.raises(ArtifactRegistryRuntimeFailureV2) as caught:
        service.register(
            request_for(
                second_receipt,
                label="same-operation",
                expected_latest_version=1,
            )
        )

    assert caught.value.code is (
        ArtifactRegistryRuntimeFailureCodeV2.IDEMPOTENCY_CONFLICT
    )
    assert factory.open().verify_chain() == (first.record.entry_sha256, 1)


def test_modified_exact_reference_is_rejected_before_read(tmp_path: Path) -> None:
    receipt = receipt_for()
    service, _ = service_for(private_root(tmp_path), (receipt, BODY_ONE))
    commit = service.register(request_for(receipt))

    with pytest.raises(ArtifactRegistryRuntimeFailureV2) as caught:
        replace(commit.record.artifact_ref, sha256="0" * 64)

    assert caught.value.code is ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED

"""Recorded-source to durable-local artifact registry orchestration."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import cast
from uuid import UUID

from raos.domain.catalog.rakuten_item_search_runtime_v2 import RawArchiveReceiptV2
from raos.domain.ops.artifact_registry_runtime_v2 import (
    ARTIFACT_REGISTRY_CONTENT_TYPE_V2,
    ARTIFACT_REGISTRY_EXTERNAL_ACTION_COUNT_V2,
    ARTIFACT_REGISTRY_SOURCE_SYSTEM_V2,
    ArtifactPutCandidateV2,
    ArtifactPutCommandV2,
    ArtifactPutReceiptV2,
    ArtifactReadbackV2,
    ArtifactRegistryCommitV2,
    ArtifactRegistryRuntimeFailureCodeV2,
    ArtifactRegistryRuntimeFailureV2,
    ArtifactSourceProvenanceV2,
    PersistedArtifactV2,
    RecordedLocalArtifactRefV2,
    fail_artifact_registry_runtime_v2,
    registry_logical_key_v2,
)
from raos.domain.ops.enums import ObjectArtifactArtifactKind
from raos.ports.artifact_registry_runtime_v2 import (
    ArtifactRegistryStoreFactoryV2,
    ArtifactRegistryStoreV2,
    ItemSearchRawArchiveSourceV2,
)


@dataclass(frozen=True, slots=True, repr=False)
class ItemSearchArtifactRegistrationRequestV2:
    operation_id: UUID
    receipt: RawArchiveReceiptV2
    expected_latest_version: int | None

    def __post_init__(self) -> None:
        if (
            type(self.operation_id) is not UUID
            or self.operation_id.int == 0
            or type(self.receipt) is not RawArchiveReceiptV2
            or (
                self.expected_latest_version is not None
                and (
                    type(self.expected_latest_version) is not int
                    or self.expected_latest_version < 1
                )
            )
        ):
            fail_artifact_registry_runtime_v2()

    def __repr__(self) -> str:
        return "ItemSearchArtifactRegistrationRequestV2(<redacted>)"


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except TypeError:
        return False


def _candidate_from_receipt(
    receipt: RawArchiveReceiptV2, content: bytes
) -> ArtifactPutCandidateV2:
    invalid = False
    candidate: ArtifactPutCandidateV2 | None = None
    try:
        digest = hashlib.sha256(content).hexdigest()
        provenance = ArtifactSourceProvenanceV2(
            source_system=ARTIFACT_REGISTRY_SOURCE_SYSTEM_V2,
            source_receipt_id=receipt.receipt_id,
            source_artifact_sha256=receipt.artifact_sha256,
            source_artifact_version=receipt.artifact_version,
            source_logical_key=receipt.logical_key,
            source_request_fingerprint=receipt.request_fingerprint,
            source_page=receipt.page,
            acquired_at=receipt.observed_at,
        )
        candidate = ArtifactPutCandidateV2(
            artifact_kind=ObjectArtifactArtifactKind.RAW_PROVIDER_RESPONSE,
            logical_key=registry_logical_key_v2(
                request_fingerprint=receipt.request_fingerprint,
                page=receipt.page,
            ),
            content_type=ARTIFACT_REGISTRY_CONTENT_TYPE_V2,
            byte_size=len(content),
            sha256=digest,
            provenance=provenance,
        )
        invalid = digest != receipt.artifact_sha256 or len(content) != receipt.byte_size
    except Exception:
        invalid = True
    if invalid or candidate is None:
        fail_artifact_registry_runtime_v2(
            ArtifactRegistryRuntimeFailureCodeV2.SOURCE_INTEGRITY
        )
    return candidate


class DurableArtifactRegistryServiceV2:
    """Persist and read exact recorded-local raw object versions."""

    __slots__ = ("_source", "_store_factory")

    def __init__(
        self,
        *,
        source: ItemSearchRawArchiveSourceV2,
        store_factory: ArtifactRegistryStoreFactoryV2,
    ) -> None:
        if (
            not _implements(source, ItemSearchRawArchiveSourceV2)
            or not _implements(store_factory, ArtifactRegistryStoreFactoryV2)
            or type(source.external_action_count) is not int
            or source.external_action_count
            != ARTIFACT_REGISTRY_EXTERNAL_ACTION_COUNT_V2
            or type(store_factory.external_action_count) is not int
            or store_factory.external_action_count
            != ARTIFACT_REGISTRY_EXTERNAL_ACTION_COUNT_V2
        ):
            raise TypeError("invalid recorded-local artifact registry collaborator")
        self._source = source
        self._store_factory = store_factory

    @property
    def external_action_count(self) -> int:
        source_count = self._source.external_action_count
        store_count = self._store_factory.external_action_count
        if (
            type(source_count) is not int
            or type(store_count) is not int
            or source_count != 0
            or store_count != 0
        ):
            fail_artifact_registry_runtime_v2(
                ArtifactRegistryRuntimeFailureCodeV2.SOURCE_UNAVAILABLE
            )
        return 0

    def register(
        self, request: ItemSearchArtifactRegistrationRequestV2
    ) -> ArtifactRegistryCommitV2:
        if type(request) is not ItemSearchArtifactRegistrationRequestV2:
            fail_artifact_registry_runtime_v2()
        invalid_request = False
        try:
            request.__post_init__()
        except Exception:
            invalid_request = True
        if invalid_request:
            fail_artifact_registry_runtime_v2()

        content: object = None
        source_failed = False
        try:
            if self._source.external_action_count != 0:
                source_failed = True
            else:
                content = self._source.read_raw(request.receipt)
                source_failed = self._source.external_action_count != 0
        except Exception:
            source_failed = True
        if source_failed or type(content) is not bytes:
            fail_artifact_registry_runtime_v2(
                ArtifactRegistryRuntimeFailureCodeV2.SOURCE_UNAVAILABLE
            )
        candidate = _candidate_from_receipt(request.receipt, content)
        command = ArtifactPutCommandV2(
            operation_id=request.operation_id,
            candidate=candidate,
            expected_latest_version=request.expected_latest_version,
        )
        store = self._open_store()
        recovered = False
        receipt: object = None
        append_error: ArtifactRegistryRuntimeFailureV2 | None = None
        store_failed = False
        try:
            receipt = store.append(command=command, content=content)
        except ArtifactRegistryRuntimeFailureV2 as error:
            append_error = error
        except Exception:
            store_failed = True
        if store_failed:
            fail_artifact_registry_runtime_v2(
                ArtifactRegistryRuntimeFailureCodeV2.STORE_UNAVAILABLE
            )
        if append_error is not None:
            if (
                append_error.code
                is not ArtifactRegistryRuntimeFailureCodeV2.COMMIT_UNKNOWN
            ):
                raise append_error
            recovery_error: ArtifactRegistryRuntimeFailureV2 | None = None
            recovery_failed = False
            try:
                receipt = store.recover_exact(command)
            except ArtifactRegistryRuntimeFailureV2 as error:
                recovery_error = error
            except Exception:
                recovery_failed = True
            if recovery_failed:
                fail_artifact_registry_runtime_v2(
                    ArtifactRegistryRuntimeFailureCodeV2.STORE_UNAVAILABLE
                )
            if recovery_error is not None:
                if (
                    recovery_error.code
                    is ArtifactRegistryRuntimeFailureCodeV2.RECOVERY_NOT_FOUND
                ):
                    fail_artifact_registry_runtime_v2(
                        ArtifactRegistryRuntimeFailureCodeV2.COMMIT_UNKNOWN
                    )
                raise recovery_error
            recovered = True
        exact_receipt = self._copy_receipt(receipt)
        record = self._load_exact(store, exact_receipt.artifact_ref)
        if record is None:
            fail_artifact_registry_runtime_v2(
                ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED
            )
        if (
            record.candidate != candidate
            or exact_receipt.operation_id != request.operation_id
            or exact_receipt.request_sha256 != command.request_sha256
            or exact_receipt.artifact_id != record.artifact_id
            or exact_receipt.artifact_ref != record.artifact_ref
            or exact_receipt.sequence != record.sequence
            or exact_receipt.entry_sha256 != record.entry_sha256
        ):
            fail_artifact_registry_runtime_v2(
                ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED
            )
        readback = self._read_exact(store, record.artifact_ref)
        if readback.record != record or readback.content != content:
            fail_artifact_registry_runtime_v2(
                ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED
            )
        self._verify_chain(store, record)
        return ArtifactRegistryCommitV2(
            record=record,
            receipt=exact_receipt,
            recovered_after_commit_ambiguity=recovered,
        )

    def readback(self, artifact_ref: RecordedLocalArtifactRefV2) -> ArtifactReadbackV2:
        if type(artifact_ref) is not RecordedLocalArtifactRefV2:
            fail_artifact_registry_runtime_v2()
        invalid_ref = False
        try:
            artifact_ref.__post_init__()
        except Exception:
            invalid_ref = True
        if invalid_ref:
            fail_artifact_registry_runtime_v2(
                ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED
            )
        store = self._open_store()
        readback = self._read_exact(store, artifact_ref)
        self._verify_chain(store, readback.record)
        return ArtifactReadbackV2(
            record=readback.record, content=bytes(readback.content)
        )

    def _open_store(self) -> ArtifactRegistryStoreV2:
        failed = False
        store: object = None
        try:
            if self._store_factory.external_action_count != 0:
                failed = True
            else:
                store = self._store_factory.open()
                failed = self._store_factory.external_action_count != 0
        except ArtifactRegistryRuntimeFailureV2:
            raise
        except Exception:
            failed = True
        if failed or not _implements(store, ArtifactRegistryStoreV2):
            fail_artifact_registry_runtime_v2(
                ArtifactRegistryRuntimeFailureCodeV2.STORE_UNAVAILABLE
            )
        return cast(ArtifactRegistryStoreV2, store)

    @staticmethod
    def _copy_receipt(value: object) -> ArtifactPutReceiptV2:
        if type(value) is not ArtifactPutReceiptV2:
            fail_artifact_registry_runtime_v2(
                ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED
            )
        invalid = False
        copy: ArtifactPutReceiptV2 | None = None
        try:
            copy = ArtifactPutReceiptV2(
                operation_id=value.operation_id,
                request_sha256=value.request_sha256,
                artifact_id=value.artifact_id,
                artifact_ref=value.artifact_ref,
                sequence=value.sequence,
                entry_sha256=value.entry_sha256,
                replayed=value.replayed,
            )
        except Exception:
            invalid = True
        if invalid or copy is None:
            fail_artifact_registry_runtime_v2(
                ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED
            )
        return copy

    @staticmethod
    def _load_exact(
        store: ArtifactRegistryStoreV2,
        artifact_ref: RecordedLocalArtifactRefV2,
    ) -> PersistedArtifactV2 | None:
        failed = False
        value: object = None
        try:
            value = store.load_exact(artifact_ref)
        except ArtifactRegistryRuntimeFailureV2:
            raise
        except Exception:
            failed = True
        if failed or (value is not None and type(value) is not PersistedArtifactV2):
            fail_artifact_registry_runtime_v2(
                ArtifactRegistryRuntimeFailureCodeV2.STORE_UNAVAILABLE
            )
        return value

    @staticmethod
    def _read_exact(
        store: ArtifactRegistryStoreV2,
        artifact_ref: RecordedLocalArtifactRefV2,
    ) -> ArtifactReadbackV2:
        failed = False
        value: object = None
        try:
            value = store.read_exact(artifact_ref)
        except ArtifactRegistryRuntimeFailureV2:
            raise
        except Exception:
            failed = True
        if failed or type(value) is not ArtifactReadbackV2:
            fail_artifact_registry_runtime_v2(
                ArtifactRegistryRuntimeFailureCodeV2.STORE_UNAVAILABLE
            )
        return value

    @staticmethod
    def _verify_chain(
        store: ArtifactRegistryStoreV2, record: PersistedArtifactV2
    ) -> None:
        failed = False
        result: object = None
        try:
            result = store.verify_chain()
        except ArtifactRegistryRuntimeFailureV2:
            raise
        except Exception:
            failed = True
        if (
            failed
            or type(result) is not tuple
            or len(result) != 2
            or type(result[0]) is not str
            or type(result[1]) is not int
            or result[1] < record.sequence
            or (result[1] == record.sequence and result[0] != record.entry_sha256)
        ):
            fail_artifact_registry_runtime_v2(
                ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED
            )


__all__ = [
    "DurableArtifactRegistryServiceV2",
    "ItemSearchArtifactRegistrationRequestV2",
]

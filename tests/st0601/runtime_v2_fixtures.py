"""Deterministic builders for the ST-0601 durable local runtime."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
from uuid import UUID, uuid5

from raos.adapters.recorded_artifact_source_runtime_v2 import (
    RecordedItemSearchRawArchiveSourceV2,
    RecordedItemSearchRawFixtureV2,
)
from raos.adapters.sqlite_artifact_registry_runtime_v2 import (
    RecordedSqliteArtifactRegistryFactoryV2,
)
from raos.application.ops.artifact_registry_runtime_v2 import (
    DurableArtifactRegistryServiceV2,
    ItemSearchArtifactRegistrationRequestV2,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.rakuten_item_search_runtime_v2 import RawArchiveReceiptV2
from raos.domain.ops.artifact_registry_runtime_v2 import (
    ARTIFACT_REGISTRY_CONTENT_TYPE_V2,
    ARTIFACT_REGISTRY_SOURCE_SYSTEM_V2,
    ArtifactPutCandidateV2,
    ArtifactPutCommandV2,
    ArtifactSourceProvenanceV2,
    registry_logical_key_v2,
)
from raos.domain.ops.enums import ObjectArtifactArtifactKind


FIXED_TIME = datetime(2026, 8, 25, 3, 4, 5, 678901, tzinfo=timezone.utc)
BODY_ONE = b'{"Items":[],"count":0,"page":1}'
BODY_TWO = b'{"Items":[{"itemCode":"fixture:2"}],"count":1,"page":1}'
REQUEST_FINGERPRINT = "a" * 64
_NAMESPACE = UUID("f1754761-73d7-4ef1-91c8-d8746c28b890")


def stable_uuid(label: str) -> UUID:
    return uuid5(_NAMESPACE, label)


def receipt_for(
    body: bytes = BODY_ONE,
    *,
    label: str = "receipt-one",
    artifact_version: int = 1,
    request_fingerprint: str = REQUEST_FINGERPRINT,
    page: int = 1,
    observed_offset_seconds: int = 0,
) -> RawArchiveReceiptV2:
    digest = hashlib.sha256(body).hexdigest()
    return RawArchiveReceiptV2(
        receipt_id=stable_uuid(label),
        artifact_sha256=digest,
        byte_size=len(body),
        artifact_version=artifact_version,
        logical_key=f"sha256/{digest[:2]}/{digest}",
        request_fingerprint=request_fingerprint,
        page=page,
        observed_at=FIXED_TIME + timedelta(seconds=observed_offset_seconds),
    )


def private_root(tmp_path: Path, *, name: str = "owner-private") -> Path:
    root = tmp_path / name
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    return root


def source_for(
    *pairs: tuple[RawArchiveReceiptV2, bytes],
) -> RecordedItemSearchRawArchiveSourceV2:
    return RecordedItemSearchRawArchiveSourceV2(
        environment=RuntimeEnvironment.ENV_DEV,
        fixtures=tuple(
            RecordedItemSearchRawFixtureV2(receipt=receipt, content=body)
            for receipt, body in pairs
        ),
    )


def factory_for(root: Path) -> RecordedSqliteArtifactRegistryFactoryV2:
    return RecordedSqliteArtifactRegistryFactoryV2(
        environment=RuntimeEnvironment.ENV_DEV,
        private_root=root,
    )


def service_for(
    root: Path,
    *pairs: tuple[RawArchiveReceiptV2, bytes],
) -> tuple[DurableArtifactRegistryServiceV2, RecordedSqliteArtifactRegistryFactoryV2]:
    factory = factory_for(root)
    return (
        DurableArtifactRegistryServiceV2(
            source=source_for(*pairs),
            store_factory=factory,
        ),
        factory,
    )


def request_for(
    receipt: RawArchiveReceiptV2,
    *,
    label: str = "operation-one",
    expected_latest_version: int | None = None,
) -> ItemSearchArtifactRegistrationRequestV2:
    return ItemSearchArtifactRegistrationRequestV2(
        operation_id=stable_uuid(label),
        receipt=receipt,
        expected_latest_version=expected_latest_version,
    )


def command_for(
    receipt: RawArchiveReceiptV2,
    body: bytes = BODY_ONE,
    *,
    label: str = "operation-one",
    expected_latest_version: int | None = None,
) -> ArtifactPutCommandV2:
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
        byte_size=len(body),
        sha256=hashlib.sha256(body).hexdigest(),
        provenance=provenance,
    )
    return ArtifactPutCommandV2(
        operation_id=stable_uuid(label),
        candidate=candidate,
        expected_latest_version=expected_latest_version,
    )


__all__ = [
    "BODY_ONE",
    "BODY_TWO",
    "FIXED_TIME",
    "REQUEST_FINGERPRINT",
    "command_for",
    "factory_for",
    "private_root",
    "receipt_for",
    "request_for",
    "service_for",
    "source_for",
    "stable_uuid",
]

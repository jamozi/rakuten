"""Closed inward ports for the ST-0601 recorded-local durable runtime."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.catalog.rakuten_item_search_runtime_v2 import RawArchiveReceiptV2
from raos.domain.ops.artifact_registry_runtime_v2 import (
    ArtifactPutCommandV2,
    ArtifactPutReceiptV2,
    ArtifactReadbackV2,
    PersistedArtifactV2,
    RecordedLocalArtifactRefV2,
)


@runtime_checkable
class ItemSearchRawArchiveSourceV2(Protocol):
    """Read one exact ST-0502 receipt from a recorded-local source."""

    @property
    def external_action_count(self) -> int: ...

    def read_raw(self, receipt: RawArchiveReceiptV2) -> bytes: ...


@runtime_checkable
class ArtifactRegistryStoreV2(Protocol):
    """Immutable exact-version object store; mutation and export are absent."""

    def append(
        self, *, command: ArtifactPutCommandV2, content: bytes
    ) -> ArtifactPutReceiptV2: ...

    def recover_exact(self, command: ArtifactPutCommandV2) -> ArtifactPutReceiptV2: ...

    def load_exact(
        self, artifact_ref: RecordedLocalArtifactRefV2
    ) -> PersistedArtifactV2 | None: ...

    def read_exact(
        self, artifact_ref: RecordedLocalArtifactRefV2
    ) -> ArtifactReadbackV2: ...

    def verify_chain(self) -> tuple[str, int]: ...


@runtime_checkable
class ArtifactRegistryStoreFactoryV2(Protocol):
    """Open one owner-private recorded-local store."""

    @property
    def external_action_count(self) -> int: ...

    @property
    def open_count(self) -> int: ...

    def open(self) -> ArtifactRegistryStoreV2: ...


__all__ = [
    "ArtifactRegistryStoreFactoryV2",
    "ArtifactRegistryStoreV2",
    "ItemSearchRawArchiveSourceV2",
]

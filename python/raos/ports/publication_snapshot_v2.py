"""Provider-neutral, local-only ports for the ST-0903 snapshot candidate."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.publishing.publication_snapshot_v2 import (
    PublicationSnapshotBuildRequestV2,
    PublicationSnapshotInputBundleV2,
    PublicationSnapshotResultV2,
)


@runtime_checkable
class RecordedPublicationSnapshotSource(Protocol):
    """Return the exact immutable inputs recorded for one local request."""

    def load(
        self,
        request: PublicationSnapshotBuildRequestV2,
    ) -> PublicationSnapshotInputBundleV2: ...


@runtime_checkable
class PublicationSnapshotExchange(Protocol):
    """Build one local candidate without persistence or an external write."""

    def exchange(
        self,
        request: PublicationSnapshotBuildRequestV2,
        bundle: PublicationSnapshotInputBundleV2,
    ) -> PublicationSnapshotResultV2: ...


__all__ = (
    "PublicationSnapshotExchange",
    "RecordedPublicationSnapshotSource",
)

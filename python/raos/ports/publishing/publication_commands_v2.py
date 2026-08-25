"""Inward process-local transaction port for ST-0905."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.publishing.publication_commands_v2 import (
    PublicationCommandResultV2,
    PublicationStoreSnapshotV2,
    PublishCommandV2,
    RollbackCommandV2,
)


@runtime_checkable
class PublicationCommandStoreV2(Protocol):
    """Apply one local simulated command atomically and idempotently."""

    def publish(self, command: PublishCommandV2) -> PublicationCommandResultV2:
        """Simulate one publish transaction without an external write."""

        ...

    def rollback(self, command: RollbackCommandV2) -> PublicationCommandResultV2:
        """Simulate one rollback transaction without an external write."""

        ...

    def snapshot(self) -> PublicationStoreSnapshotV2:
        """Return a value-only observation for atomicity verification."""

        ...


__all__ = ("PublicationCommandStoreV2",)

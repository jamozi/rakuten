"""Inward owner-private persistence port for ST-0604 V2."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from raos.domain.evidence.source_packet_lifecycle_runtime_v2 import (
    SourcePacketCommandIdV2,
    SourcePacketCommandResultV2,
    SourcePacketCommandV2,
    SourcePacketStateV2,
)


@runtime_checkable
class SourcePacketLifecycleStoreV2(Protocol):
    """Atomic CAS command journal; it is not an external service interface."""

    @property
    def action_count(self) -> int: ...

    def execute(self, command: SourcePacketCommandV2) -> SourcePacketCommandResultV2:
        """Apply exactly one command or return its exact idempotent replay."""

        ...

    def recover(
        self,
        *,
        command_id: SourcePacketCommandIdV2,
        request_sha256: str,
    ) -> SourcePacketCommandResultV2:
        """Recover one exact committed command; never retry a mutation."""

        ...

    def load_state(self, packet_id: UUID) -> SourcePacketStateV2 | None:
        """Return the exact current state after full journal validation."""

        ...

    def audit_snapshot(self) -> tuple[dict[str, object], ...]:
        """Return sanitized hash-only audit rows after full validation."""

        ...


__all__ = ["SourcePacketLifecycleStoreV2"]

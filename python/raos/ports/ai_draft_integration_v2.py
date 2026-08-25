"""Inward, one-call recorded-material port for ST-0806 V2."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.editorial.ai_draft_integration_v2 import RecordedDraftMaterialV2


@runtime_checkable
class RecordedAiDraftIntegrationPortV2(Protocol):
    """Return one exact synthetic material bundle without effects."""

    def integrate(self, *, request_binding_sha256: str) -> RecordedDraftMaterialV2:
        """Consume one exact request binding and return recorded bytes."""

        ...


__all__ = ["RecordedAiDraftIntegrationPortV2"]

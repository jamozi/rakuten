"""Inward one-call port for ST-0806 recorded draft integration."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.editorial.ai_draft_integration import (
    AiDraftIntegrationRequest,
    RecordedDraftCandidate,
)


@runtime_checkable
class RecordedAiDraftIntegrationPort(Protocol):
    """Return one exact scripted candidate without performing side effects."""

    def integrate(
        self, *, request: AiDraftIntegrationRequest
    ) -> RecordedDraftCandidate:
        """Consume one exact request and return its bound synthetic candidate."""

        ...


__all__ = ["RecordedAiDraftIntegrationPort"]

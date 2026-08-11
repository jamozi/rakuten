"""Bounded one-shot synthetic adapter for ST-0806."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn, SupportsIndex, final

from raos.domain.editorial.ai_draft_integration import (
    AiDraftEnvironment,
    AiDraftIntegrationFailureCode,
    AiDraftIntegrationRequest,
    RecordedDraftCandidate,
    fail_ai_draft_integration,
)


@dataclass(frozen=True, slots=True, repr=False)
class RecordedAiDraftIntegrationStep:
    request: AiDraftIntegrationRequest
    candidate: RecordedDraftCandidate

    def __post_init__(self) -> None:
        if (
            type(self.request) is not AiDraftIntegrationRequest
            or type(self.candidate) is not RecordedDraftCandidate
        ):
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.INVALID_REQUEST)

    def __repr__(self) -> str:
        return "RecordedAiDraftIntegrationStep(<redacted-ai-draft-integration>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded AI draft step serialization is unsupported")


@final
class RecordedAiDraftIntegrationAdapter:
    """Consume exactly one pre-recorded request with no retry or fallback."""

    __slots__ = ("_called", "_step")

    def __init__(
        self,
        *,
        environment: AiDraftEnvironment,
        script_capacity: int,
        scripts: tuple[RecordedAiDraftIntegrationStep, ...],
    ) -> None:
        if (
            type(environment) is not AiDraftEnvironment
            or type(script_capacity) is not int
            or script_capacity != 1
            or type(scripts) is not tuple
            or len(scripts) != 1
            or type(scripts[0]) is not RecordedAiDraftIntegrationStep
            or scripts[0].request.environment is not environment
        ):
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.DEVELOPMENT_ONLY)
        self._step = scripts[0]
        self._called = False

    @property
    def call_count(self) -> int:
        return int(self._called)

    def __repr__(self) -> str:
        return "RecordedAiDraftIntegrationAdapter(<redacted-ai-draft-integration>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded AI draft adapter serialization is unsupported")

    def integrate(
        self, *, request: AiDraftIntegrationRequest
    ) -> RecordedDraftCandidate:
        if self._called or type(request) is not AiDraftIntegrationRequest:
            fail_ai_draft_integration(
                AiDraftIntegrationFailureCode.COLLABORATOR_FAILURE
            )
        if request != self._step.request:
            fail_ai_draft_integration(
                AiDraftIntegrationFailureCode.COLLABORATOR_FAILURE
            )
        self._called = True
        return self._step.candidate


__all__ = [
    "RecordedAiDraftIntegrationAdapter",
    "RecordedAiDraftIntegrationStep",
]

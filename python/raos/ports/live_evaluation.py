"""Provider-neutral read-only execution port for ST-0708."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.ai.live_evaluation import (
    RecordedLiveEvaluationRequest,
    RecordedLiveEvaluationResult,
)


@runtime_checkable
class RecordedLiveEvaluationExecutor(Protocol):
    """Execute a closed recorded request without provider or network authority."""

    def execute(
        self, request: RecordedLiveEvaluationRequest
    ) -> RecordedLiveEvaluationResult | None: ...


__all__ = ["RecordedLiveEvaluationExecutor"]

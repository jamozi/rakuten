"""Provider-neutral inward recording port for Canonical ST-1908."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.ai.fine_tuning_evaluation import (
    FineTuningEvaluationCommand,
    RecordedFineTuningBundle,
)


@runtime_checkable
class FineTuningEvidenceSource(Protocol):
    """Consume one command-bound, caller-owned synthetic recording once."""

    def read(
        self, command: FineTuningEvaluationCommand
    ) -> RecordedFineTuningBundle: ...


__all__ = ("FineTuningEvidenceSource",)

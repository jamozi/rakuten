"""Local-only ST-0705 application service."""

from __future__ import annotations

from datetime import datetime
from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.output_validation import (
    AiOutputValidationInput,
    AiOutputValidationReport,
    canonical_validation_time,
    evaluate_ai_output,
    unavailable_ai_output_validation_report,
)
from raos.ports.ai_output_validation import AiOutputValidationCaseReader


def _local_environment(value: object) -> bool:
    return type(value) is RuntimeEnvironment and value in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
    }


@final
class EvaluateAiOutputService:
    """Read one exact recorded case; never repair, persist, or call a provider."""

    __slots__ = ("_reader",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        reader: AiOutputValidationCaseReader,
    ) -> None:
        try:
            implements = isinstance(cast(object, reader), AiOutputValidationCaseReader)
        except Exception:
            implements = False
        if not _local_environment(environment) or not implements:
            raise ValueError("INVALID_AI_OUTPUT_VALIDATION_SERVICE") from None
        self._reader = reader

    def evaluate(
        self, *, case_id: str, evaluated_at: datetime
    ) -> AiOutputValidationReport:
        if (
            type(case_id) is not str
            or not case_id
            or case_id != case_id.strip()
            or len(case_id) > 120
        ):
            raise ValueError("INVALID_AI_OUTPUT_VALIDATION_REQUEST") from None
        try:
            safe_evaluated_at = canonical_validation_time(evaluated_at)
        except Exception:
            raise ValueError("INVALID_AI_OUTPUT_VALIDATION_REQUEST") from None
        try:
            value = self._reader.get_case(case_id)
        except Exception:
            return unavailable_ai_output_validation_report(safe_evaluated_at)
        if type(value) is not AiOutputValidationInput:
            return unavailable_ai_output_validation_report(safe_evaluated_at)
        if value.evaluated_at != safe_evaluated_at:
            return unavailable_ai_output_validation_report(safe_evaluated_at)
        return evaluate_ai_output(value)


__all__ = ["EvaluateAiOutputService"]

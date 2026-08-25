"""Application service for deterministic recorded-only ST-0708 evaluation."""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.live_evaluation import (
    LiveEvaluationFailureCode,
    LiveEvaluationReport,
    RecordedLiveEvaluationRequest,
    RecordedLiveEvaluationResult,
    evaluate_recorded_live_evidence,
    fail_live_evaluation,
)
from raos.ports.live_evaluation import RecordedLiveEvaluationExecutor


def _local_environment(value: object) -> bool:
    return type(value) is RuntimeEnvironment and value in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
    }


@final
class EvaluateRecordedLiveCandidateService:
    """Run a closed recorded adapter and return only a proposal/refusal report."""

    __slots__ = ("_executor",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        executor: RecordedLiveEvaluationExecutor,
    ) -> None:
        try:
            implements = isinstance(
                cast(object, executor), RecordedLiveEvaluationExecutor
            )
        except Exception:
            implements = False
        if not _local_environment(environment) or not implements:
            fail_live_evaluation(LiveEvaluationFailureCode.INVALID_REQUEST)
        self._executor = executor

    def evaluate(self, request: RecordedLiveEvaluationRequest) -> LiveEvaluationReport:
        if type(request) is not RecordedLiveEvaluationRequest:
            fail_live_evaluation(LiveEvaluationFailureCode.INVALID_REQUEST)
        request.require_valid()
        try:
            result = self._executor.execute(request)
        except Exception:
            fail_live_evaluation(LiveEvaluationFailureCode.INVALID_EVIDENCE)
        if type(result) is not RecordedLiveEvaluationResult:
            fail_live_evaluation(LiveEvaluationFailureCode.INVALID_EVIDENCE)
        return evaluate_recorded_live_evidence(result)


__all__ = ["EvaluateRecordedLiveCandidateService"]

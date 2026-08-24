from __future__ import annotations

import pytest

from raos.adapters.recorded_live_evaluation import RecordedLiveEvaluationAdapter
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.live_evaluation import RecordedLiveEvaluationResult
from tests.st0708_v2.support import load_result


@pytest.fixture()
def recorded_result() -> RecordedLiveEvaluationResult:
    return load_result()


@pytest.fixture()
def recorded_adapter(
    recorded_result: RecordedLiveEvaluationResult,
) -> RecordedLiveEvaluationAdapter:
    return RecordedLiveEvaluationAdapter(
        environment=RuntimeEnvironment.CI,
        result=recorded_result,
    )

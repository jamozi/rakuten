from __future__ import annotations

from typing import Any

import pytest

from raos.domain.ai.evaluation_harness import RecordedEvaluationBundle
from tests.st0707_runtime.support import load_bundle


@pytest.fixture
def bundle() -> RecordedEvaluationBundle:
    return load_bundle()


@pytest.fixture
def artifact_loader() -> Any:
    return load_bundle

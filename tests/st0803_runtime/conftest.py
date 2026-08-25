from __future__ import annotations

from pathlib import Path

import pytest

from raos.adapters.recorded_comparison_validation import (
    load_recorded_comparison_fixture,
)
from raos.domain.editorial.comparison_validation_v2 import (
    ComparisonValidationEnvelopeV2,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = (
    REPO_ROOT / "changes/st-0803/generated/comparison-validation-pass.v2.json"
)


@pytest.fixture
def fixture_bytes() -> bytes:
    return FIXTURE_PATH.read_bytes()


@pytest.fixture
def envelope(fixture_bytes: bytes) -> ComparisonValidationEnvelopeV2:
    return load_recorded_comparison_fixture(fixture_bytes)

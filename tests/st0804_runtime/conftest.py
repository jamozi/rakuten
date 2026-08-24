from __future__ import annotations

from pathlib import Path

import pytest

from raos.adapters.recorded_recommendation import (
    load_recorded_recommendation_fixture,
)
from raos.domain.editorial.recommendation_v2 import RecommendationEnvelopeV2


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "changes/st-0804/generated/recommendation-pass.v2.json"


@pytest.fixture
def fixture_bytes() -> bytes:
    return FIXTURE_PATH.read_bytes()


@pytest.fixture
def envelope(fixture_bytes: bytes) -> RecommendationEnvelopeV2:
    return load_recorded_recommendation_fixture(fixture_bytes)

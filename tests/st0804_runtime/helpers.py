from __future__ import annotations

from dataclasses import replace

from raos.domain.editorial.recommendation_v2 import (
    RecommendationEnvelopeV2,
    assessment_set_sha256,
    dimension_set_sha256,
    recommendation_input_sha256,
)
from raos.domain.shared.persistence import Sha256Digest


def rehash_envelope(value: RecommendationEnvelopeV2) -> RecommendationEnvelopeV2:
    rebound = replace(
        value,
        dimension_set_sha256=dimension_set_sha256(value.dimensions),
        assessment_set_sha256=assessment_set_sha256(value.assessments),
        recommendation_input_sha256=Sha256Digest("0" * 64),
    )
    return replace(
        rebound,
        recommendation_input_sha256=recommendation_input_sha256(rebound),
    )

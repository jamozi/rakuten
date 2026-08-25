"""Conservative UNAVAILABLE semantics for ST-1906 aggregate analysis."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from raos.domain.analytics.causal_attribution import (
    CausalAttributionReport,
    CausalAvailability,
    CausalCandidateState,
    CausalUnavailableReason,
)

from .support import canonical_payload, command_for, fixture_document, service_for


Mutator = Callable[[dict[str, Any]], None]


def _evaluate(mutator: Mutator) -> CausalAttributionReport:
    document = fixture_document()
    mutator(document)
    payload = canonical_payload(document)
    return service_for(payload).evaluate(command_for(payload))


@pytest.mark.parametrize(
    ("mutator", "reason"),
    [
        (
            lambda value: value["cells"].clear(),
            CausalUnavailableReason.MISSING_INPUT,
        ),
        (
            lambda value: (
                value["document"]["privacy_review"].__setitem__(
                    "status", "NOT_REVIEWED"
                ),
                value["document"]["privacy_review"].__setitem__("review_sha256", None),
            ),
            CausalUnavailableReason.PRIVACY_REVIEW_REQUIRED,
        ),
        (
            lambda value: value["cells"][0].__setitem__(
                "article_id", "st1906-other-article"
            ),
            CausalUnavailableReason.ARTICLE_BINDING_MISMATCH,
        ),
        (
            lambda value: (
                value["document"].__setitem__("program", "OTHER_PROGRAM"),
                [
                    cell.__setitem__("program", "OTHER_PROGRAM")
                    for cell in value["cells"]
                ],
            ),
            CausalUnavailableReason.PROGRAM_MISMATCH,
        ),
        (
            lambda value: value["cells"][0].__setitem__(
                "period",
                {
                    "duration_days": 14,
                    "end_exclusive_date": "2026-09-22",
                    "start_date": "2026-09-08",
                },
            ),
            CausalUnavailableReason.PERIOD_MISMATCH,
        ),
        (
            lambda value: value["cells"][0].__setitem__("verification", "UNVERIFIED"),
            CausalUnavailableReason.UNVERIFIED_INPUT,
        ),
        (
            lambda value: value["cells"][0].__setitem__("cohort", "IMMATURE"),
            CausalUnavailableReason.COHORT_IMMATURE,
        ),
        (
            lambda value: value["cells"][0].__setitem__("assignment_verified", False),
            CausalUnavailableReason.ASSIGNMENT_UNVERIFIED,
        ),
        (
            lambda value: value["cells"][0].__setitem__("treatment_exposures", 1001),
            CausalUnavailableReason.ARM_BALANCE_MISMATCH,
        ),
        (
            lambda value: (
                value["cells"][0].__setitem__("control_exposures", 0),
                value["cells"][0].__setitem__("control_outcomes", 0),
                value["cells"][0].__setitem__("treatment_exposures", 0),
                value["cells"][0].__setitem__("treatment_outcomes", 0),
            ),
            CausalUnavailableReason.ZERO_DENOMINATOR,
        ),
        (
            lambda value: (
                value["cells"][0].__setitem__("control_exposures", 499),
                value["cells"][0].__setitem__("control_outcomes", 30),
                value["cells"][0].__setitem__("treatment_exposures", 499),
                value["cells"][0].__setitem__("treatment_outcomes", 60),
            ),
            CausalUnavailableReason.LOW_SAMPLE_SIZE,
        ),
        (
            lambda value: value["cells"][0].__setitem__("control_outcomes", 19),
            CausalUnavailableReason.LOW_OUTCOME_COUNT,
        ),
        (
            lambda value: [
                cell.__setitem__("treatment_outcomes", cell["control_outcomes"])
                for cell in value["cells"]
            ],
            CausalUnavailableReason.INSUFFICIENT_CAUSAL_SIGNAL,
        ),
    ],
)
def test_unsafe_or_insufficient_inputs_are_unavailable_not_zero(
    mutator: Mutator, reason: CausalUnavailableReason
) -> None:
    report = _evaluate(mutator)
    assert report.availability is CausalAvailability.UNAVAILABLE
    assert report.unavailable_reason is reason
    assert report.candidate_state is CausalCandidateState.NO_ANALYSIS_AVAILABLE
    assert report.estimate is None

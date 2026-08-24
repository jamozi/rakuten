"""Fail-closed availability gate tests for ST-1907."""

from __future__ import annotations

from copy import deepcopy

import pytest

from raos.domain.portfolio.content_optimizer import (
    OptimizerAvailability,
    OptimizerUnavailableReason,
)

from .support import canonical_payload, command_for, ready_document, service_for


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda value: value.update({"signals": []}), "MISSING_OBSERVATIONS"),
        (
            lambda value: value["signals"][0].update({"program": "OTHER_PROGRAM"}),
            "PROGRAM_MISMATCH",
        ),
        (
            lambda value: value["signals"][0]["period"].update(
                {
                    "start_date": "2026-02-01",
                    "end_exclusive_date": "2026-02-15",
                }
            ),
            "PERIOD_MISMATCH",
        ),
        (
            lambda value: value["signals"][0].update({"verification": "UNVERIFIED"}),
            "UNVERIFIED_INPUT",
        ),
        (
            lambda value: value["signals"][0].update({"cohort": "IMMATURE"}),
            "COHORT_IMMATURE",
        ),
        (
            lambda value: value["signals"][0].update({"denominator_count": None}),
            "DENOMINATOR_UNAVAILABLE",
        ),
        (
            lambda value: value["signals"][0].update({"denominator_count": 0}),
            "ZERO_DENOMINATOR",
        ),
        (
            lambda value: value["signals"][0].update(
                {"signal_policy_sha256": "c" * 64}
            ),
            "UNVERIFIED_INPUT",
        ),
    ],
)
def test_evidence_gaps_are_unavailable_not_zero_or_actionable(
    mutation: object,
    reason: str,
) -> None:
    document = deepcopy(ready_document())
    mutation(document)  # type: ignore[operator]
    payload = canonical_payload(document)
    report = service_for(payload).evaluate(command_for(payload))
    assert report.availability is OptimizerAvailability.UNAVAILABLE
    assert report.unavailable_reason is OptimizerUnavailableReason(reason)
    assert report.proposals == ()
    assert report.payload()["proposal_count"] == 0

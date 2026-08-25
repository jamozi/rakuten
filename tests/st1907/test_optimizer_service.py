"""Core behavior and local service boundary tests for ST-1907."""

from __future__ import annotations

from dataclasses import replace

import pytest

from raos.application.portfolio.content_optimizer import (
    ContentPortfolioOptimizerService,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.portfolio.content_optimizer import (
    OptimizerAvailability,
    OptimizerUnavailableReason,
    PortfolioOptimizerFailure,
    PortfolioOptimizerFailureCode,
    PortfolioOptimizerScope,
    ProposalState,
)

from .support import canonical_payload, command_for, ready_document, service_for


class _CountingSource:
    def __init__(self) -> None:
        self.calls = 0

    def read(self, command: object) -> object:
        del command
        self.calls += 1
        raise AssertionError("disabled service called its inward port")


def test_current_dependency_is_unavailable_with_zero_proposals() -> None:
    command = command_for()
    first = service_for().evaluate(command)
    second = service_for().evaluate(command)
    assert first == second
    assert first.availability is OptimizerAvailability.UNAVAILABLE
    assert (
        first.unavailable_reason
        is OptimizerUnavailableReason.DEPENDENCY_BLOCKED_NO_DECISION
    )
    assert first.proposal_state is ProposalState.NO_PROPOSALS
    assert first.proposals == ()
    assert first.payload()["proposal_count"] == 0
    assert all(value is False for value in first.payload()["authority"].values())


def test_ready_same_cohort_signals_emit_deterministic_human_proposals_only() -> None:
    payload = canonical_payload(ready_document())
    report = service_for(payload).evaluate(command_for(payload))
    assert report.availability is OptimizerAvailability.AVAILABLE
    assert report.unavailable_reason is None
    assert report.proposal_state is ProposalState.HUMAN_REVIEW_PROPOSALS_ONLY
    assert [proposal.action.value for proposal in report.proposals] == [
        "STRENGTHEN",
        "CONSOLIDATE",
        "WITHDRAW",
    ]
    assert len({proposal.proposal_id for proposal in report.proposals}) == 3
    for proposal in report.payload()["proposals"]:
        assert proposal["actionable"] is False
        assert proposal["automatic_apply"] is False
        assert proposal["human_review_required"] is True
        assert proposal["mutations_applied"] == []
        assert all(value is False for value in proposal["mutation_authority"].values())
    policy = report.payload()["policy"]
    assert policy["finance_values_represented"] is False
    assert policy["proposal_order_is_recommendation_order"] is False
    assert policy["thresholds_selected_by_this_story"] is False


def test_default_disabled_fails_before_port_call() -> None:
    source = _CountingSource()
    service = ContentPortfolioOptimizerService(
        environment=RuntimeEnvironment.CI,
        source=source,
    )
    with pytest.raises(PortfolioOptimizerFailure) as caught:
        service.evaluate(replace(command_for(), scope=PortfolioOptimizerScope.DISABLED))
    assert caught.value.code is PortfolioOptimizerFailureCode.FEATURE_DISABLED
    assert source.calls == 0


@pytest.mark.parametrize(
    "environment",
    [
        RuntimeEnvironment.INTEGRATION,
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.RECOVERY,
        RuntimeEnvironment.PRODUCTION,
    ],
)
def test_nonlocal_environments_are_refused(
    environment: RuntimeEnvironment,
) -> None:
    with pytest.raises(PortfolioOptimizerFailure):
        ContentPortfolioOptimizerService(
            environment=environment,
            source=_CountingSource(),
        )

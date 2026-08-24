"""Positive, default-disabled, and authority boundary tests for ST-1906."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
import pickle

import pytest

from raos.adapters.recorded_causal_attribution import (
    RecordedCausalAttributionSource,
)
from raos.application.analytics.causal_attribution import (
    CausalAttributionEvaluationService,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.analytics.causal_attribution import (
    DEFAULT_CAUSAL_ATTRIBUTION_SCOPE,
    CausalAttributionFailure,
    CausalAttributionFailureCode,
    CausalAttributionScope,
    CausalAvailability,
    CausalCandidateState,
)
from raos.ports.causal_attribution import CausalAttributionEvidenceSource

from .support import command_for, fixture_bytes, service_for


class _CountingSource:
    def __init__(self) -> None:
        self.calls = 0

    def read(self, command: object) -> object:
        del command
        self.calls += 1
        raise AssertionError("disabled service reached evidence source")


class _HostileSource:
    read = "not-callable"


def test_default_scope_is_disabled_before_source_call() -> None:
    source = _CountingSource()
    service = CausalAttributionEvaluationService(
        environment=RuntimeEnvironment.CI,
        source=source,  # type: ignore[arg-type]
    )
    with pytest.raises(CausalAttributionFailure) as caught:
        service.evaluate(command_for(scope=DEFAULT_CAUSAL_ATTRIBUTION_SCOPE))
    assert caught.value.code is CausalAttributionFailureCode.FEATURE_DISABLED
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
def test_nonlocal_environments_are_refused(environment: RuntimeEnvironment) -> None:
    with pytest.raises(CausalAttributionFailure):
        CausalAttributionEvaluationService(
            environment=environment,
            source=RecordedCausalAttributionSource(fixture_bytes()),
        )


def test_port_is_provider_neutral_and_scope_has_no_live_state() -> None:
    source = RecordedCausalAttributionSource(fixture_bytes())
    assert isinstance(source, CausalAttributionEvidenceSource)
    with pytest.raises(CausalAttributionFailure):
        CausalAttributionEvaluationService(
            environment=RuntimeEnvironment.CI,
            source=_HostileSource(),  # type: ignore[arg-type]
        )
    assert tuple(CausalAttributionScope) == (
        CausalAttributionScope.DISABLED,
        CausalAttributionScope.RECORDED_SYNTHETIC_AGGREGATE_EVALUATION_ONLY,
    )
    for name in (
        "activate",
        "allocate",
        "publish",
        "release",
        "send",
        "track",
        "write",
    ):
        assert not hasattr(source, name)
        assert not hasattr(CausalAttributionEvaluationService, name)


def test_recorded_aggregate_result_is_deterministic_analysis_only() -> None:
    first = service_for().evaluate(command_for())
    second = service_for().evaluate(command_for())
    assert first == second
    assert first.availability is CausalAvailability.AVAILABLE
    assert first.candidate_state is CausalCandidateState.ANALYSIS_CANDIDATE_ONLY
    assert first.cell_count == 5
    assert first.estimate is not None
    assert (
        first.estimate.control_exposures,
        first.estimate.control_outcomes,
        first.estimate.treatment_exposures,
        first.estimate.treatment_outcomes,
    ) == (5_000, 200, 5_000, 400)
    assert (
        first.estimate.control_rate_micros,
        first.estimate.treatment_rate_micros,
        first.estimate.risk_difference_micros,
    ) == (40_000, 80_000, 40_000)
    assert first.estimate.confidence_lower_micros > 0
    assert first.estimate.confidence_upper_micros > 40_000
    assert first.blockers == tuple(sorted(first.blockers))


def test_report_has_no_editorial_publication_or_tracking_authority() -> None:
    report = service_for().evaluate(command_for())
    assert all(
        getattr(report.authority, item.name) is False
        for item in fields(report.authority)
    )
    policy = report.payload()["policy"]
    assert isinstance(policy, dict)
    assert policy["arbitrary_provider_total_allocation"] is False
    assert policy["automatic_editorial_use"] is False
    assert policy["automatic_recommendation_use"] is False
    assert policy["finance_values_represented"] is False
    assert policy["result_is_provider_fact"] is False
    assert report.payload()["estimate"] is not None


def test_values_are_immutable_redacted_and_not_pickleable() -> None:
    report = service_for().evaluate(command_for())
    assert "redacted" in repr(report)
    assert "redacted" in str(report)
    with pytest.raises(FrozenInstanceError):
        report.cell_count = 6  # type: ignore[misc]
    with pytest.raises(TypeError):
        pickle.dumps(report)
    with pytest.raises(CausalAttributionFailure) as caught:
        service_for().evaluate(object())  # type: ignore[arg-type]
    assert str(caught.value) == CausalAttributionFailureCode.INVALID_ARGUMENT.value
    with pytest.raises(TypeError):
        pickle.dumps(caught.value)

"""Recorded adapter and request-bound service trust tests for ST-1402."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from raos.adapters.recorded_safe_degradation import (
    RecordedSafeDegradationAdapter,
    RecordedSafeDegradationFixture,
)
from raos.application.freshness.safe_degradation import (
    SafeDegradationService,
    bind_safe_degradation_request,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.freshness.freshness import (
    FreshnessEvaluation,
    FreshnessEvaluationRequest,
)
from raos.domain.freshness.safe_degradation import (
    AvailabilityAggregate,
    SafeDegradationDecision,
    SafeDegradationFailure,
    SafeDegradationFailureCode,
    SafeDegradationRequest,
    decide_safe_degradation,
)

from conftest import (
    bound_request,
    freshness_request,
    freshness_result,
    recorded_adapter,
    safe_degradation_service,
)


class _CountingExchange:
    def __init__(self, decision: SafeDegradationDecision) -> None:
        self.calls = 0
        self.decision = decision

    def decide(self, request: SafeDegradationRequest) -> SafeDegradationDecision:
        del request
        self.calls += 1
        return self.decision


class _RaisingExchange:
    def decide(self, request: SafeDegradationRequest) -> SafeDegradationDecision:
        del request
        raise RuntimeError("hostile collaborator material")


class _MutatingExchange:
    def __init__(self, decision: SafeDegradationDecision) -> None:
        self.decision = decision

    def decide(self, request: SafeDegradationRequest) -> SafeDegradationDecision:
        object.__setattr__(
            request,
            "availability_aggregate",
            AvailabilityAggregate.ALL_PRIMARY_OFFERS_UNAVAILABLE,
        )
        return self.decision


def test_recorded_adapter_returns_only_the_exact_bound_decision() -> None:
    exact_request = freshness_request()
    safe_request = bound_request(request=exact_request)
    expected = decide_safe_degradation(safe_request)
    actual = recorded_adapter(request=exact_request).decide(safe_request)
    assert actual == expected
    assert actual is not expected
    assert actual.fingerprint == expected.fingerprint


def test_unbound_recorded_request_returns_only_closed_unavailable_code() -> None:
    adapter = recorded_adapter()
    other_freshness_request = freshness_request(recommendation_basis_affected=True)
    other_request = bound_request(request=other_freshness_request)
    with pytest.raises(SafeDegradationFailure) as raised:
        adapter.decide(other_request)
    assert raised.value.code is SafeDegradationFailureCode.DECIDER_UNAVAILABLE
    assert str(raised.value) == "DECIDER_UNAVAILABLE"


def test_service_calls_collaborator_once_and_rebuilds_expected_decision() -> None:
    exact_freshness_request = freshness_request()
    exact_freshness_result = freshness_result(exact_freshness_request)
    request = bound_request(
        request=exact_freshness_request,
        result=exact_freshness_result,
    )
    expected = decide_safe_degradation(request)
    exchange = _CountingExchange(expected)
    service = SafeDegradationService(
        environment=RuntimeEnvironment.ENV_DEV,
        exchange=exchange,
    )
    actual = service.decide(
        freshness_request=exact_freshness_request,
        freshness_result=exact_freshness_result,
        availability_aggregate=AvailabilityAggregate.NOT_APPLICABLE,
    )
    assert exchange.calls == 1
    assert actual == expected
    assert actual is not expected


def test_collaborator_exception_is_replaced_with_closed_code() -> None:
    service = SafeDegradationService(
        environment=RuntimeEnvironment.ENV_DEV,
        exchange=_RaisingExchange(),
    )
    exact_request = freshness_request()
    with pytest.raises(SafeDegradationFailure) as raised:
        service.decide(
            freshness_request=exact_request,
            freshness_result=freshness_result(exact_request),
            availability_aggregate=AvailabilityAggregate.NOT_APPLICABLE,
        )
    assert raised.value.code is SafeDegradationFailureCode.DECIDER_UNAVAILABLE
    assert "hostile" not in repr(raised.value)


def test_collaborator_cannot_mutate_sent_request_and_still_succeed() -> None:
    exact_request = freshness_request()
    safe_request = bound_request(request=exact_request)
    service = SafeDegradationService(
        environment=RuntimeEnvironment.ENV_DEV,
        exchange=_MutatingExchange(decide_safe_degradation(safe_request)),
    )
    with pytest.raises(SafeDegradationFailure) as raised:
        service.decide(
            freshness_request=exact_request,
            freshness_result=freshness_result(exact_request),
            availability_aggregate=AvailabilityAggregate.NOT_APPLICABLE,
        )
    assert raised.value.code is SafeDegradationFailureCode.DECISION_MISMATCH


def test_different_shape_valid_decision_is_rejected() -> None:
    exact_request = freshness_request(freshness_class_id="FRESH-002")
    exact_result = freshness_result(exact_request)
    expected_request = bound_request(
        request=exact_request,
        availability_aggregate=(
            AvailabilityAggregate.NOT_ALL_PRIMARY_OFFERS_UNAVAILABLE
        ),
    )
    other_request = bound_request(
        request=exact_request,
        availability_aggregate=(AvailabilityAggregate.ALL_PRIMARY_OFFERS_UNAVAILABLE),
    )
    service = SafeDegradationService(
        environment=RuntimeEnvironment.ENV_DEV,
        exchange=_CountingExchange(decide_safe_degradation(other_request)),
    )
    with pytest.raises(SafeDegradationFailure) as raised:
        service.decide(
            freshness_request=exact_request,
            freshness_result=exact_result,
            availability_aggregate=(
                AvailabilityAggregate.NOT_ALL_PRIMARY_OFFERS_UNAVAILABLE
            ),
        )
    assert expected_request.fingerprint != other_request.fingerprint
    assert raised.value.code is SafeDegradationFailureCode.DECISION_MISMATCH


def test_request_result_mismatch_is_rejected_before_port_call() -> None:
    exact_request = freshness_request()
    other_request = freshness_request(recommendation_basis_affected=True)
    exchange = _CountingExchange(
        decide_safe_degradation(bound_request(request=exact_request))
    )
    service = SafeDegradationService(
        environment=RuntimeEnvironment.ENV_DEV,
        exchange=exchange,
    )
    with pytest.raises(SafeDegradationFailure) as raised:
        service.decide(
            freshness_request=exact_request,
            freshness_result=freshness_result(other_request),
            availability_aggregate=AvailabilityAggregate.NOT_APPLICABLE,
        )
    assert raised.value.code is SafeDegradationFailureCode.FRESHNESS_RESULT_INVALID
    assert exchange.calls == 0


def test_self_consistent_looking_forged_fingerprint_is_rejected_by_owner_rerun() -> (
    None
):
    exact_request = freshness_request()
    exact_result = freshness_result(exact_request)
    forged_result = replace(exact_result, request_fingerprint="0" * 64)
    with pytest.raises(SafeDegradationFailure) as raised:
        bind_safe_degradation_request(
            freshness_request=exact_request,
            freshness_result=forged_result,
            availability_aggregate=AvailabilityAggregate.NOT_APPLICABLE,
        )
    assert raised.value.code is SafeDegradationFailureCode.FRESHNESS_RESULT_INVALID


def test_freshness_request_and_result_subclasses_are_rejected() -> None:
    class RequestSubclass(FreshnessEvaluationRequest):
        pass

    class ResultSubclass(FreshnessEvaluation):
        pass

    exact_request = freshness_request()
    exact_result = freshness_result(exact_request)
    request_subclass = cast(
        FreshnessEvaluationRequest,
        object.__new__(RequestSubclass),
    )
    result_subclass = cast(
        FreshnessEvaluation,
        object.__new__(ResultSubclass),
    )
    with pytest.raises(SafeDegradationFailure):
        bind_safe_degradation_request(
            freshness_request=request_subclass,
            freshness_result=exact_result,
            availability_aggregate=AvailabilityAggregate.NOT_APPLICABLE,
        )
    with pytest.raises(SafeDegradationFailure):
        bind_safe_degradation_request(
            freshness_request=exact_request,
            freshness_result=result_subclass,
            availability_aggregate=AvailabilityAggregate.NOT_APPLICABLE,
        )


@pytest.mark.parametrize(
    "environment",
    (
        RuntimeEnvironment.INTEGRATION,
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.RECOVERY,
        RuntimeEnvironment.PRODUCTION,
    ),
)
def test_service_and_adapter_are_dev_ci_only(
    environment: RuntimeEnvironment,
) -> None:
    exact_request = freshness_request()
    safe_request = bound_request(request=exact_request)
    decision = decide_safe_degradation(safe_request)
    fixture = RecordedSafeDegradationFixture(
        request=safe_request,
        decision=decision,
    )
    with pytest.raises(SafeDegradationFailure) as service_failure:
        SafeDegradationService(
            environment=environment,
            exchange=recorded_adapter(),
        )
    assert service_failure.value.code is SafeDegradationFailureCode.DEVELOPMENT_ONLY
    with pytest.raises(SafeDegradationFailure):
        RecordedSafeDegradationAdapter(
            environment=environment,
            fixture_capacity=1,
            fixtures=(fixture,),
        )


def test_recorded_adapter_rejects_duplicate_and_unbounded_fixtures() -> None:
    request = bound_request()
    fixture = RecordedSafeDegradationFixture(
        request=request,
        decision=decide_safe_degradation(request),
    )
    with pytest.raises(SafeDegradationFailure):
        RecordedSafeDegradationAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            fixture_capacity=2,
            fixtures=(fixture, fixture),
        )
    with pytest.raises(SafeDegradationFailure):
        RecordedSafeDegradationAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            fixture_capacity=cast(int, True),
            fixtures=(fixture,),
        )


def test_convenience_service_uses_an_exact_recorded_fixture() -> None:
    exact_request = freshness_request()
    actual = safe_degradation_service(request=exact_request).decide(
        freshness_request=exact_request,
        freshness_result=freshness_result(exact_request),
        availability_aggregate=AvailabilityAggregate.NOT_APPLICABLE,
    )
    assert actual == decide_safe_degradation(bound_request(request=exact_request))

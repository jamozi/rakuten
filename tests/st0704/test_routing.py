"""Focused authorization, eligibility, quote, and circuit tests for ST-0704."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import pytest

from conftest import (
    CERTIFICATION_ID,
    EXPIRES_AT,
    IDENTITY,
    MODEL_ID,
    NOW,
    ROUTE_CODE,
    ROUTE_SHA256,
    ROUTE_VERSION,
    TASK_BINDING_SHA256,
    TASK_CODE,
    SyntheticTaskRegistry,
    certification,
    quote,
    reservation_request,
    route_identity,
    routing_service,
    task_contract,
)
from raos.adapters.development_ai_controls import (
    InMemoryDevelopmentAiControls,
    SyntheticRouteEligibilityFixture,
)
from raos.application.ai.routing import DevelopmentAiRoutingService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.routing import (
    AuthorizedRouteReservation,
    FallbackPolicy,
    RouteIdentity,
    RoutingFailure,
    RoutingFailureCode,
    SyntheticRouteCertification,
    SyntheticRouteQuote,
)


def _failure(code: RoutingFailureCode, operation: Callable[[], object]) -> None:
    with pytest.raises(RoutingFailure) as captured:
        operation()
    assert captured.value.code is code
    assert str(captured.value) == code.value
    assert captured.value.__cause__ is None


def test_explicit_synthetic_certification_authorizes_one_exact_route() -> None:
    service, _, _ = routing_service()

    authorization = service.authorize_and_reserve(
        request=reservation_request(), now=NOW
    )

    assert type(authorization) is AuthorizedRouteReservation
    assert authorization.identity == IDENTITY
    assert authorization.certification_id == CERTIFICATION_ID
    assert authorization.task_binding_sha256 == TASK_BINDING_SHA256
    assert authorization.route_sha256 == ROUTE_SHA256
    assert authorization.reservation.reserved_jpy == 7
    assert authorization.fallback_policy is FallbackPolicy.DENY_ALL
    assert authorization.max_fallbacks == 0


def test_candidate_registry_metadata_never_authorizes_without_fixture() -> None:
    service, _, _ = routing_service(candidates=())

    _failure(
        RoutingFailureCode.INELIGIBLE_CANDIDATE,
        lambda: service.authorize_and_reserve(request=reservation_request(), now=NOW),
    )


@pytest.mark.parametrize(
    "environment",
    tuple(
        environment
        for environment in RuntimeEnvironment
        if environment is not RuntimeEnvironment.ENV_DEV
    ),
)
def test_every_non_development_environment_fails_closed(
    environment: RuntimeEnvironment,
) -> None:
    _failure(
        RoutingFailureCode.DEVELOPMENT_ONLY,
        lambda: SyntheticRouteEligibilityFixture(
            environment=environment,
            candidates=(certification(),),
        ),
    )
    _failure(
        RoutingFailureCode.DEVELOPMENT_ONLY,
        lambda: InMemoryDevelopmentAiControls(
            environment=environment,
            synthetic_cap_jpy=10,
            initially_closed_routes=(IDENTITY,),
        ),
    )

    _, eligibility, controls = routing_service()
    _failure(
        RoutingFailureCode.DEVELOPMENT_ONLY,
        lambda: DevelopmentAiRoutingService(
            environment=environment,
            task_registry=SyntheticTaskRegistry((task_contract(),)),
            eligibility=eligibility,
            controls=controls,
        ),
    )


def test_unknown_task_route_version_and_model_have_stable_failures() -> None:
    service, _, _ = routing_service(cap_jpy=100)
    unknown_task_identity = route_identity(task_code="ai.unknown.v1")
    _failure(
        RoutingFailureCode.UNKNOWN_TASK,
        lambda: service.authorize_and_reserve(
            request=reservation_request(
                operation_id="operation.unknown-task",
                task_code="ai.unknown.v1",
                route_quote=quote(
                    identity=unknown_task_identity,
                    quote_id="synthetic.quote.unknown-task",
                ),
            ),
            now=NOW,
        ),
    )

    unknown_route_identity = route_identity(route_code="route.unknown.v1")
    _failure(
        RoutingFailureCode.UNKNOWN_ROUTE,
        lambda: service.authorize_and_reserve(
            request=reservation_request(
                operation_id="operation.unknown-route",
                route_quote=quote(
                    identity=unknown_route_identity,
                    quote_id="synthetic.quote.unknown-route",
                ),
            ),
            now=NOW,
        ),
    )

    unknown_version_identity = route_identity(
        route_version="synthetic.route-version.unknown.v1"
    )
    _failure(
        RoutingFailureCode.UNKNOWN_ROUTE_VERSION,
        lambda: service.authorize_and_reserve(
            request=reservation_request(
                operation_id="operation.unknown-version",
                route_quote=quote(
                    identity=unknown_version_identity,
                    quote_id="synthetic.quote.unknown-version",
                ),
            ),
            now=NOW,
        ),
    )

    unknown_model_identity = route_identity(model_id="synthetic.model.unknown.v1")
    _failure(
        RoutingFailureCode.UNKNOWN_MODEL,
        lambda: service.authorize_and_reserve(
            request=reservation_request(
                operation_id="operation.unknown-model",
                route_quote=quote(
                    identity=unknown_model_identity,
                    quote_id="synthetic.quote.unknown-model",
                ),
            ),
            now=NOW,
        ),
    )


def test_exact_requested_fixture_is_deterministic_regardless_of_input_order() -> None:
    alternate_identity = route_identity(
        route_version="synthetic.route-version.local.v2",
        model_id="synthetic.model.local.v2",
    )
    requested = certification(selection_rank=9)
    alternate = certification(
        identity=alternate_identity,
        certification_id="synthetic.certification.local.v2",
        selection_rank=1,
    )
    requested_quote = quote(
        quote_id="synthetic.quote.deterministic",
        amount_jpy=1,
    )

    first, _, _ = routing_service(
        cap_jpy=5,
        candidates=(requested, alternate),
        closed_routes=(IDENTITY, alternate_identity),
    )
    second, _, _ = routing_service(
        cap_jpy=5,
        candidates=(alternate, requested),
        closed_routes=(alternate_identity, IDENTITY),
    )

    first_result = first.authorize_and_reserve(
        request=reservation_request(
            operation_id="operation.deterministic",
            route_quote=requested_quote,
            amount_jpy=1,
        ),
        now=NOW,
    )
    second_result = second.authorize_and_reserve(
        request=reservation_request(
            operation_id="operation.deterministic",
            route_quote=requested_quote,
            amount_jpy=1,
        ),
        now=NOW,
    )

    assert first_result.identity == IDENTITY
    assert second_result.identity == IDENTITY
    assert first_result.reservation == second_result.reservation


@pytest.mark.parametrize(
    "candidate",
    (
        certification(eligible=False),
        certification(
            valid_from=NOW - timedelta(minutes=10),
            expires_at=NOW,
        ),
        certification(task_binding_sha256="a" * 64),
        certification(route_sha256="b" * 64),
    ),
)
def test_ineligible_stale_or_unbound_certification_fails_closed(
    candidate: SyntheticRouteCertification,
) -> None:
    service, _, _ = routing_service(candidates=(candidate,))
    _failure(
        RoutingFailureCode.INELIGIBLE_CANDIDATE,
        lambda: service.authorize_and_reserve(request=reservation_request(), now=NOW),
    )


def test_disabled_registry_task_remains_ineligible_with_fixture() -> None:
    for task in (
        task_contract(prompt_status="DISABLED"),
        task_contract(lifecycle="GATE_1_PROPOSED_DISABLED"),
        task_contract(route_enabled=False),
    ):
        service, _, _ = routing_service(task=task)
        _failure(
            RoutingFailureCode.INELIGIBLE_CANDIDATE,
            lambda: service.authorize_and_reserve(
                request=reservation_request(), now=NOW
            ),
        )


def test_quote_validity_and_binding_fail_closed_before_reservation() -> None:
    future_quote = quote(
        quote_id="synthetic.quote.future",
        valid_from=NOW + timedelta(seconds=1),
        expires_at=NOW + timedelta(minutes=2),
    )
    expired_quote = quote(
        quote_id="synthetic.quote.expired",
        valid_from=NOW - timedelta(minutes=2),
        expires_at=NOW,
    )
    mismatched_quote = quote(
        certification_id="synthetic.certification.other.v1",
        quote_id="synthetic.quote.mismatch",
    )

    for route_quote, expected in (
        (future_quote, RoutingFailureCode.QUOTE_NOT_YET_VALID),
        (expired_quote, RoutingFailureCode.QUOTE_EXPIRED),
        (mismatched_quote, RoutingFailureCode.QUOTE_MISMATCH),
    ):
        service, _, _ = routing_service()
        _failure(
            expected,
            lambda: service.authorize_and_reserve(
                request=reservation_request(route_quote=route_quote),
                now=NOW,
            ),
        )


def test_reservation_window_cannot_outlive_quote_or_certification() -> None:
    service, _, _ = routing_service()
    _failure(
        RoutingFailureCode.QUOTE_MISMATCH,
        lambda: service.authorize_and_reserve(
            request=reservation_request(
                reservation_expires_at=EXPIRES_AT + timedelta(seconds=1)
            ),
            now=NOW,
        ),
    )
    _failure(
        RoutingFailureCode.RESERVATION_EXPIRED,
        lambda: service.authorize_and_reserve(
            request=reservation_request(
                operation_id="operation.expired-reservation",
                reservation_expires_at=NOW,
            ),
            now=NOW,
        ),
    )


def test_circuit_defaults_open_and_can_only_trip_toward_deny() -> None:
    default_open, _, _ = routing_service(closed_routes=())
    _failure(
        RoutingFailureCode.CIRCUIT_OPEN,
        lambda: default_open.authorize_and_reserve(
            request=reservation_request(), now=NOW
        ),
    )

    service, _, _ = routing_service()
    service.trip_circuit_open(identity=IDENTITY, now=NOW)
    _failure(
        RoutingFailureCode.CIRCUIT_OPEN,
        lambda: service.authorize_and_reserve(
            request=reservation_request(
                operation_id="operation.after-trip",
                route_quote=quote(quote_id="synthetic.quote.after-trip"),
            ),
            now=NOW,
        ),
    )
    _failure(
        RoutingFailureCode.CIRCUIT_OPEN,
        lambda: service.trip_circuit_open(identity=IDENTITY, now=NOW),
    )


def test_malformed_and_non_synthetic_values_are_rejected_without_echo() -> None:
    canary = "RAW_PRIVATE_CANARY"
    invalid_values: tuple[Callable[[], object], ...] = (
        lambda: RouteIdentity(
            task_code=TASK_CODE,
            route_code=ROUTE_CODE,
            route_version=ROUTE_VERSION,
            model_id=canary,
        ),
        lambda: SyntheticRouteQuote(
            identity=IDENTITY,
            certification_id=CERTIFICATION_ID,
            quote_id=canary,
            estimated_cost_jpy=7,
            valid_from=NOW,
            expires_at=NOW + timedelta(minutes=1),
        ),
        lambda: quote(amount_jpy=-1),
        lambda: quote(
            valid_from=datetime(
                2026, 8, 10, 12, 0, tzinfo=timezone(timedelta(hours=9))
            ),
            expires_at=datetime(
                2026, 8, 10, 12, 1, tzinfo=timezone(timedelta(hours=9))
            ),
        ),
    )
    for operation in invalid_values:
        with pytest.raises(RoutingFailure) as captured:
            operation()
        assert captured.value.code is RoutingFailureCode.INVALID_REQUEST
        assert canary not in str(captured.value)
        assert canary not in repr(captured.value)


def test_route_identifiers_are_synthetic_and_canonical_route_is_only_a_binding() -> (
    None
):
    assert IDENTITY.task_code == TASK_CODE
    assert IDENTITY.route_code == ROUTE_CODE
    assert IDENTITY.route_version == ROUTE_VERSION
    assert IDENTITY.model_id == MODEL_ID
    assert IDENTITY.route_version.startswith("synthetic.")
    assert IDENTITY.model_id.startswith("synthetic.")

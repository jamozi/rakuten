"""Atomic cap, reservation lifecycle, replay, and concurrency tests."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest

from conftest import (
    CERTIFICATION_ID,
    IDENTITY,
    NOW,
    ROUTE_SHA256,
    SyntheticTaskRegistry,
    TASK_BINDING_SHA256,
    quote,
    reservation_request,
    routing_service,
    task_contract,
)
from raos.application.ai.routing import DevelopmentAiRoutingService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.routing import (
    AuthorizedRouteReservation,
    BudgetCommit,
    BudgetRelease,
    BudgetReservation,
    ReservationIntent,
    RouteIdentity,
    RoutingFailure,
    RoutingFailureCode,
)
from raos.ports.ai_routing import DevelopmentAiControlPort


def _failure(code: RoutingFailureCode, operation: Callable[[], object]) -> None:
    with pytest.raises(RoutingFailure) as captured:
        operation()
    assert captured.value.code is code
    assert captured.value.__cause__ is None


def _request_for(index: int, amount_jpy: int) -> object:
    return reservation_request(
        operation_id=f"operation.concurrent.{index}",
        route_quote=quote(
            quote_id=f"synthetic.quote.concurrent.{index}",
            amount_jpy=amount_jpy,
        ),
        amount_jpy=amount_jpy,
    )


class _MismatchedReceiptControls:
    def __init__(
        self, *, delegate: DevelopmentAiControlPort, mismatch_commit: bool
    ) -> None:
        self._delegate = delegate
        self._mismatch_commit = mismatch_commit

    def reserve(self, *, intent: ReservationIntent, now: datetime) -> BudgetReservation:
        return self._delegate.reserve(intent=intent, now=now)

    def commit(
        self,
        *,
        reservation: BudgetReservation,
        committed_jpy: int,
        now: datetime,
    ) -> BudgetCommit:
        if self._mismatch_commit:
            return BudgetCommit(
                reservation_id="0" * 64,
                intent_sha256=reservation.intent_sha256,
                committed_jpy=committed_jpy,
                committed_at=now,
            )
        return self._delegate.commit(
            reservation=reservation,
            committed_jpy=committed_jpy,
            now=now,
        )

    def release(
        self, *, reservation: BudgetReservation, now: datetime
    ) -> BudgetRelease:
        if not self._mismatch_commit:
            return BudgetRelease(
                reservation_id="0" * 64,
                intent_sha256=reservation.intent_sha256,
                released_jpy=reservation.reserved_jpy,
                released_at=now,
            )
        return self._delegate.release(reservation=reservation, now=now)

    def trip_open(self, *, identity: RouteIdentity, now: datetime) -> None:
        self._delegate.trip_open(identity=identity, now=now)


def _service_with_mismatched_receipt(
    *, mismatch_commit: bool
) -> DevelopmentAiRoutingService:
    _, eligibility, controls = routing_service()
    return DevelopmentAiRoutingService(
        environment=RuntimeEnvironment.ENV_DEV,
        task_registry=SyntheticTaskRegistry((task_contract(),)),
        eligibility=eligibility,
        controls=_MismatchedReceiptControls(
            delegate=controls,
            mismatch_commit=mismatch_commit,
        ),
    )


def test_injected_synthetic_ten_jpy_cap_accepts_seven_and_rejects_eleven() -> None:
    accepted_service, _, _ = routing_service(cap_jpy=10)
    accepted = accepted_service.authorize_and_reserve(
        request=reservation_request(amount_jpy=7),
        now=NOW,
    )
    assert accepted.reservation.reserved_jpy == 7

    rejected_service, _, _ = routing_service(cap_jpy=10)
    _failure(
        RoutingFailureCode.BUDGET_EXCEEDED,
        lambda: rejected_service.authorize_and_reserve(
            request=reservation_request(
                operation_id="operation.over-cap",
                route_quote=quote(
                    quote_id="synthetic.quote.over-cap",
                    amount_jpy=11,
                ),
                amount_jpy=11,
            ),
            now=NOW,
        ),
    )


def test_commit_uses_actual_amount_and_releases_unused_reservation() -> None:
    service, _, _ = routing_service(cap_jpy=10)
    first = service.authorize_and_reserve(
        request=reservation_request(amount_jpy=7), now=NOW
    )

    receipt = service.commit(
        authorization=first,
        committed_jpy=5,
        now=NOW + timedelta(seconds=1),
    )
    assert receipt.committed_jpy == 5

    second = service.authorize_and_reserve(
        request=reservation_request(
            operation_id="operation.after-commit",
            route_quote=quote(
                quote_id="synthetic.quote.after-commit",
                amount_jpy=5,
            ),
            amount_jpy=5,
        ),
        now=NOW,
    )
    assert second.reservation.reserved_jpy == 5

    _failure(
        RoutingFailureCode.BUDGET_EXCEEDED,
        lambda: service.authorize_and_reserve(
            request=reservation_request(
                operation_id="operation.no-headroom",
                route_quote=quote(
                    quote_id="synthetic.quote.no-headroom",
                    amount_jpy=1,
                ),
                amount_jpy=1,
            ),
            now=NOW,
        ),
    )


def test_release_returns_the_full_reservation_to_the_synthetic_cap() -> None:
    service, _, _ = routing_service(cap_jpy=10)
    first = service.authorize_and_reserve(
        request=reservation_request(amount_jpy=7), now=NOW
    )
    receipt = service.release(
        authorization=first,
        now=NOW + timedelta(seconds=1),
    )
    assert receipt.released_jpy == 7

    replacement = service.authorize_and_reserve(
        request=reservation_request(
            operation_id="operation.after-release",
            route_quote=quote(
                quote_id="synthetic.quote.after-release",
                amount_jpy=10,
            ),
            amount_jpy=10,
        ),
        now=NOW,
    )
    assert replacement.reservation.reserved_jpy == 10


def test_operation_duplicate_and_payload_mismatch_are_burned_fail_closed() -> None:
    service, _, _ = routing_service(cap_jpy=20)
    original_request = reservation_request()
    service.authorize_and_reserve(request=original_request, now=NOW)

    _failure(
        RoutingFailureCode.RESERVATION_REPLAY,
        lambda: service.authorize_and_reserve(request=original_request, now=NOW),
    )
    _failure(
        RoutingFailureCode.RESERVATION_MISMATCH,
        lambda: service.authorize_and_reserve(
            request=reservation_request(
                operation_id=original_request.operation_id,
                route_quote=quote(
                    quote_id="synthetic.quote.changed-payload",
                    amount_jpy=1,
                ),
                amount_jpy=1,
            ),
            now=NOW,
        ),
    )


def test_commit_and_release_are_terminal_and_cannot_be_replayed() -> None:
    service, _, _ = routing_service(cap_jpy=10)
    authorization = service.authorize_and_reserve(
        request=reservation_request(), now=NOW
    )
    service.commit(
        authorization=authorization,
        committed_jpy=7,
        now=NOW + timedelta(seconds=1),
    )

    _failure(
        RoutingFailureCode.RESERVATION_REPLAY,
        lambda: service.commit(
            authorization=authorization,
            committed_jpy=7,
            now=NOW + timedelta(seconds=2),
        ),
    )
    _failure(
        RoutingFailureCode.RESERVATION_REPLAY,
        lambda: service.release(
            authorization=authorization,
            now=NOW + timedelta(seconds=2),
        ),
    )


def test_reconstructed_or_unknown_reservation_handle_is_rejected() -> None:
    service, _, _ = routing_service(cap_jpy=10)
    authorization = service.authorize_and_reserve(
        request=reservation_request(), now=NOW
    )
    original = authorization.reservation
    reconstructed = BudgetReservation(
        reservation_id=original.reservation_id,
        operation_id=original.operation_id,
        intent_sha256=original.intent_sha256,
        identity=original.identity,
        quote_sha256=original.quote_sha256,
        reserved_jpy=original.reserved_jpy,
        reserved_at=original.reserved_at,
        expires_at=original.expires_at,
    )
    reconstructed_authorization = AuthorizedRouteReservation(
        identity=IDENTITY,
        certification_id=CERTIFICATION_ID,
        task_binding_sha256=TASK_BINDING_SHA256,
        route_sha256=ROUTE_SHA256,
        reservation=reconstructed,
    )
    _failure(
        RoutingFailureCode.RESERVATION_MISMATCH,
        lambda: service.commit(
            authorization=reconstructed_authorization,
            committed_jpy=7,
            now=NOW + timedelta(seconds=1),
        ),
    )

    unknown_intent = ReservationIntent(
        operation_id="operation.unknown-reservation",
        identity=IDENTITY,
        task_binding_sha256=TASK_BINDING_SHA256,
        route_sha256=ROUTE_SHA256,
        certification_id=CERTIFICATION_ID,
        quote_sha256="c" * 64,
        reserved_jpy=1,
        authorized_at=NOW,
        expires_at=NOW + timedelta(minutes=1),
    )
    unknown = BudgetReservation.from_intent(unknown_intent)
    unknown_authorization = AuthorizedRouteReservation(
        identity=IDENTITY,
        certification_id=CERTIFICATION_ID,
        task_binding_sha256=TASK_BINDING_SHA256,
        route_sha256=ROUTE_SHA256,
        reservation=unknown,
    )
    _failure(
        RoutingFailureCode.RESERVATION_UNKNOWN,
        lambda: service.release(
            authorization=unknown_authorization,
            now=NOW + timedelta(seconds=1),
        ),
    )


def test_authorization_metadata_is_bound_to_the_live_reservation_handle() -> None:
    service, _, _ = routing_service(cap_jpy=10)
    authorization = service.authorize_and_reserve(
        request=reservation_request(), now=NOW
    )

    _failure(
        RoutingFailureCode.RESERVATION_MISMATCH,
        lambda: AuthorizedRouteReservation(
            identity=authorization.identity,
            certification_id="synthetic.certification.forged.v1",
            task_binding_sha256="a" * 64,
            route_sha256="b" * 64,
            reservation=authorization.reservation,
        ),
    )

    object.__setattr__(
        authorization,
        "certification_id",
        "synthetic.certification.mutated.v1",
    )
    _failure(
        RoutingFailureCode.RESERVATION_MISMATCH,
        lambda: service.commit(
            authorization=authorization,
            committed_jpy=7,
            now=NOW + timedelta(seconds=1),
        ),
    )


@pytest.mark.parametrize("mismatch_commit", (True, False))
def test_mismatched_outward_control_receipt_fails_closed(
    mismatch_commit: bool,
) -> None:
    service = _service_with_mismatched_receipt(mismatch_commit=mismatch_commit)
    authorization = service.authorize_and_reserve(
        request=reservation_request(), now=NOW
    )

    if mismatch_commit:
        _failure(
            RoutingFailureCode.CONTROL_FAILURE,
            lambda: service.commit(
                authorization=authorization,
                committed_jpy=7,
                now=NOW + timedelta(seconds=1),
            ),
        )
    else:
        _failure(
            RoutingFailureCode.CONTROL_FAILURE,
            lambda: service.release(
                authorization=authorization,
                now=NOW + timedelta(seconds=1),
            ),
        )


def test_over_commit_fails_without_consuming_the_valid_reservation() -> None:
    service, _, _ = routing_service(cap_jpy=10)
    authorization = service.authorize_and_reserve(
        request=reservation_request(), now=NOW
    )
    _failure(
        RoutingFailureCode.BUDGET_EXCEEDED,
        lambda: service.commit(
            authorization=authorization,
            committed_jpy=8,
            now=NOW + timedelta(seconds=1),
        ),
    )
    receipt = service.commit(
        authorization=authorization,
        committed_jpy=7,
        now=NOW + timedelta(seconds=2),
    )
    assert receipt.committed_jpy == 7


def test_not_yet_valid_and_expired_reservations_fail_without_auto_cleanup() -> None:
    service, _, _ = routing_service(cap_jpy=10)
    authorization = service.authorize_and_reserve(
        request=reservation_request(reservation_expires_at=NOW + timedelta(seconds=2)),
        now=NOW,
    )

    _failure(
        RoutingFailureCode.RESERVATION_NOT_YET_VALID,
        lambda: service.commit(
            authorization=authorization,
            committed_jpy=7,
            now=NOW - timedelta(microseconds=1),
        ),
    )
    _failure(
        RoutingFailureCode.RESERVATION_EXPIRED,
        lambda: service.release(
            authorization=authorization,
            now=NOW + timedelta(seconds=2),
        ),
    )
    _failure(
        RoutingFailureCode.BUDGET_EXCEEDED,
        lambda: service.authorize_and_reserve(
            request=reservation_request(
                operation_id="operation.after-expiry",
                route_quote=quote(
                    quote_id="synthetic.quote.after-expiry",
                    amount_jpy=4,
                ),
                amount_jpy=4,
            ),
            now=NOW,
        ),
    )


def test_concurrent_reservations_cannot_overspend_process_local_cap() -> None:
    service, _, _ = routing_service(cap_jpy=10)

    def reserve(index: int) -> RoutingFailureCode | str:
        try:
            service.authorize_and_reserve(
                request=_request_for(index, 1),  # type: ignore[arg-type]
                now=NOW,
            )
        except RoutingFailure as error:
            return error.code
        return "ACCEPTED"

    with ThreadPoolExecutor(max_workers=16) as executor:
        outcomes = tuple(executor.map(reserve, range(40)))

    assert outcomes.count("ACCEPTED") == 10
    assert outcomes.count(RoutingFailureCode.BUDGET_EXCEEDED) == 30


def test_concurrent_replay_creates_at_most_one_reservation() -> None:
    service, _, _ = routing_service(cap_jpy=10)
    request = reservation_request(amount_jpy=1)

    def reserve(_: int) -> RoutingFailureCode | str:
        try:
            service.authorize_and_reserve(request=request, now=NOW)
        except RoutingFailure as error:
            return error.code
        return "ACCEPTED"

    with ThreadPoolExecutor(max_workers=12) as executor:
        outcomes = tuple(executor.map(reserve, range(24)))

    assert outcomes.count("ACCEPTED") == 1
    assert outcomes.count(RoutingFailureCode.RESERVATION_REPLAY) == 23


@pytest.mark.parametrize("committed_jpy", (True, -1, 1 << 63))
def test_commit_rejects_malformed_amounts(committed_jpy: object) -> None:
    service, _, _ = routing_service(cap_jpy=10)
    authorization = service.authorize_and_reserve(
        request=reservation_request(), now=NOW
    )
    _failure(
        RoutingFailureCode.INVALID_REQUEST,
        lambda: service.commit(
            authorization=authorization,
            committed_jpy=committed_jpy,  # type: ignore[arg-type]
            now=NOW + timedelta(seconds=1),
        ),
    )

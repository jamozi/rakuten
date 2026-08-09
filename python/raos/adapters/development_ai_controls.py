"""Deterministic ENV-DEV fixtures and atomic in-memory AI controls."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re
from threading import Lock
from typing import NoReturn, SupportsIndex, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.routing import (
    BudgetCommit,
    BudgetRelease,
    BudgetReservation,
    ReservationIntent,
    RouteIdentity,
    RoutingFailureCode,
    SyntheticRouteCertification,
    fail_routing,
    require_routing_utc,
)


_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")
_MAX_SIGNED_BIGINT = (1 << 63) - 1


def _require_development(environment: object) -> RuntimeEnvironment:
    if (
        type(environment) is not RuntimeEnvironment
        or environment is not RuntimeEnvironment.ENV_DEV
    ):
        fail_routing(RoutingFailureCode.DEVELOPMENT_ONLY)
    return environment


def _require_now(value: object) -> datetime:
    return require_routing_utc(value)


def _normalize_identity(candidate: object) -> RouteIdentity:
    normalized: RouteIdentity | None = None
    if type(candidate) is RouteIdentity:
        try:
            normalized = RouteIdentity(
                task_code=candidate.task_code,
                route_code=candidate.route_code,
                route_version=candidate.route_version,
                model_id=candidate.model_id,
            )
        except Exception:
            pass
    if normalized is None:
        fail_routing(RoutingFailureCode.INVALID_REQUEST)
    return normalized


def _normalize_certification(candidate: object) -> SyntheticRouteCertification:
    normalized: SyntheticRouteCertification | None = None
    if type(candidate) is SyntheticRouteCertification:
        try:
            normalized = SyntheticRouteCertification(
                identity=_normalize_identity(candidate.identity),
                certification_id=candidate.certification_id,
                task_binding_sha256=candidate.task_binding_sha256,
                route_sha256=candidate.route_sha256,
                eligible=candidate.eligible,
                valid_from=candidate.valid_from,
                expires_at=candidate.expires_at,
                selection_rank=candidate.selection_rank,
            )
        except Exception:
            pass
    if normalized is None:
        fail_routing(RoutingFailureCode.INVALID_REQUEST)
    return normalized


@final
class SyntheticRouteEligibilityFixture:
    """Closed explicitly injected route certifications for local tests only."""

    __slots__ = ("_candidates_by_task", "_environment")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        candidates: tuple[SyntheticRouteCertification, ...],
    ) -> None:
        self._environment = _require_development(environment)
        if type(candidates) is not tuple:
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        normalized = tuple(_normalize_certification(item) for item in candidates)
        identities = [item.identity for item in normalized]
        if len(set(identities)) != len(identities):
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        ordered = tuple(
            sorted(
                normalized,
                key=lambda item: (
                    item.selection_rank,
                    item.identity.route_code,
                    item.identity.route_version,
                    item.identity.model_id,
                    item.certification_id,
                ),
            )
        )
        by_task: dict[str, list[SyntheticRouteCertification]] = {}
        for item in ordered:
            by_task.setdefault(item.identity.task_code, []).append(item)
        self._candidates_by_task = {
            task_code: tuple(task_candidates)
            for task_code, task_candidates in by_task.items()
        }

    def candidates_for(
        self, *, task_code: str
    ) -> tuple[SyntheticRouteCertification, ...]:
        self._guard()
        if type(task_code) is not str or _SAFE_IDENTIFIER.fullmatch(task_code) is None:
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        return self._candidates_by_task.get(task_code, ())

    def _guard(self) -> None:
        _require_development(self._environment)

    def __repr__(self) -> str:
        return (
            "SyntheticRouteEligibilityFixture("
            "environment='ENV-DEV', candidates=<redacted>)"
        )

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("synthetic eligibility fixture serialization is unsupported")


class _ReservationState(Enum):
    ACTIVE = "ACTIVE"
    COMMITTED = "COMMITTED"
    RELEASED = "RELEASED"


@dataclass(slots=True)
class _ReservationRecord:
    handle: BudgetReservation
    snapshot: tuple[object, ...]
    state: _ReservationState = _ReservationState.ACTIVE


def _reservation_snapshot(reservation: BudgetReservation) -> tuple[object, ...]:
    return (
        reservation.reservation_id,
        reservation.operation_id,
        reservation.intent_sha256,
        reservation.identity,
        reservation.quote_sha256,
        reservation.reserved_jpy,
        reservation.reserved_at,
        reservation.expires_at,
    )


@final
class InMemoryDevelopmentAiControls:
    """Atomic synthetic budget ledger with default-open one-way circuits.

    The injected cap is test control data, not an OD-009 product value. This
    adapter creates no worker or background task and performs no external I/O.
    """

    __slots__ = (
        "_closed_routes",
        "_committed_jpy",
        "_environment",
        "_lock",
        "_records",
        "_reserved_jpy",
        "_seen_operations",
        "_synthetic_cap_jpy",
    )

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        synthetic_cap_jpy: int,
        initially_closed_routes: tuple[RouteIdentity, ...] = (),
    ) -> None:
        self._environment = _require_development(environment)
        if (
            type(synthetic_cap_jpy) is not int
            or not 0 <= synthetic_cap_jpy <= _MAX_SIGNED_BIGINT
        ):
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        if type(initially_closed_routes) is not tuple:
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        normalized_routes = tuple(
            _normalize_identity(identity) for identity in initially_closed_routes
        )
        if len(set(normalized_routes)) != len(normalized_routes):
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        self._synthetic_cap_jpy = synthetic_cap_jpy
        self._closed_routes = set(normalized_routes)
        self._reserved_jpy = 0
        self._committed_jpy = 0
        self._seen_operations: dict[str, str] = {}
        self._records: dict[str, _ReservationRecord] = {}
        self._lock = Lock()

    def reserve(self, *, intent: ReservationIntent, now: datetime) -> BudgetReservation:
        if type(intent) is not ReservationIntent:
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        observed_at = _require_now(now)
        if observed_at != intent.authorized_at:
            fail_routing(RoutingFailureCode.RESERVATION_MISMATCH)
        if observed_at >= intent.expires_at:
            fail_routing(RoutingFailureCode.RESERVATION_EXPIRED)
        with self._lock:
            self._guard()
            prior_fingerprint = self._seen_operations.get(intent.operation_id)
            if prior_fingerprint is not None:
                if prior_fingerprint == intent.fingerprint_sha256:
                    fail_routing(RoutingFailureCode.RESERVATION_REPLAY)
                fail_routing(RoutingFailureCode.RESERVATION_MISMATCH)
            self._seen_operations[intent.operation_id] = intent.fingerprint_sha256
            if intent.identity not in self._closed_routes:
                fail_routing(RoutingFailureCode.CIRCUIT_OPEN)
            used_jpy = self._reserved_jpy + self._committed_jpy
            if intent.reserved_jpy > self._synthetic_cap_jpy - used_jpy:
                fail_routing(RoutingFailureCode.BUDGET_EXCEEDED)
            reservation = BudgetReservation.from_intent(intent)
            if reservation.reservation_id in self._records:
                fail_routing(RoutingFailureCode.CONTROL_FAILURE)
            self._records[reservation.reservation_id] = _ReservationRecord(
                handle=reservation,
                snapshot=_reservation_snapshot(reservation),
            )
            self._reserved_jpy += reservation.reserved_jpy
            return reservation

    def commit(
        self,
        *,
        reservation: BudgetReservation,
        committed_jpy: int,
        now: datetime,
    ) -> BudgetCommit:
        if type(reservation) is not BudgetReservation:
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        if (
            type(committed_jpy) is not int
            or not 0 <= committed_jpy <= _MAX_SIGNED_BIGINT
        ):
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        observed_at = _require_now(now)
        with self._lock:
            self._guard()
            record = self._require_active_record(reservation, observed_at)
            if committed_jpy > reservation.reserved_jpy:
                fail_routing(RoutingFailureCode.BUDGET_EXCEEDED)
            self._reserved_jpy -= reservation.reserved_jpy
            self._committed_jpy += committed_jpy
            record.state = _ReservationState.COMMITTED
            return BudgetCommit(
                reservation_id=reservation.reservation_id,
                intent_sha256=reservation.intent_sha256,
                committed_jpy=committed_jpy,
                committed_at=observed_at,
            )

    def release(
        self, *, reservation: BudgetReservation, now: datetime
    ) -> BudgetRelease:
        if type(reservation) is not BudgetReservation:
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        observed_at = _require_now(now)
        with self._lock:
            self._guard()
            record = self._require_active_record(reservation, observed_at)
            self._reserved_jpy -= reservation.reserved_jpy
            record.state = _ReservationState.RELEASED
            return BudgetRelease(
                reservation_id=reservation.reservation_id,
                intent_sha256=reservation.intent_sha256,
                released_jpy=reservation.reserved_jpy,
                released_at=observed_at,
            )

    def trip_open(self, *, identity: RouteIdentity, now: datetime) -> None:
        normalized_identity = _normalize_identity(identity)
        _require_now(now)
        with self._lock:
            self._guard()
            if normalized_identity not in self._closed_routes:
                fail_routing(RoutingFailureCode.CIRCUIT_OPEN)
            self._closed_routes.remove(normalized_identity)

    def _require_active_record(
        self, reservation: BudgetReservation, observed_at: datetime
    ) -> _ReservationRecord:
        record = self._records.get(reservation.reservation_id)
        if record is None:
            fail_routing(RoutingFailureCode.RESERVATION_UNKNOWN)
        if record.handle is not reservation or record.snapshot != _reservation_snapshot(
            reservation
        ):
            fail_routing(RoutingFailureCode.RESERVATION_MISMATCH)
        if record.state is not _ReservationState.ACTIVE:
            fail_routing(RoutingFailureCode.RESERVATION_REPLAY)
        if observed_at < reservation.reserved_at:
            fail_routing(RoutingFailureCode.RESERVATION_NOT_YET_VALID)
        if observed_at >= reservation.expires_at:
            fail_routing(RoutingFailureCode.RESERVATION_EXPIRED)
        return record

    def _guard(self) -> None:
        _require_development(self._environment)

    def __repr__(self) -> str:
        return "InMemoryDevelopmentAiControls(environment='ENV-DEV', state=<redacted>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("development AI controls serialization is unsupported")


__all__ = [
    "InMemoryDevelopmentAiControls",
    "SyntheticRouteEligibilityFixture",
]

"""Synthetic ENV-DEV route authorization and budget orchestration."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import NoReturn

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.contracts import TaskContract
from raos.domain.ai.routing import (
    AuthorizedRouteReservation,
    BudgetCommit,
    BudgetRelease,
    BudgetReservation,
    ReservationIntent,
    RouteIdentity,
    RouteReservationRequest,
    RoutingFailure,
    RoutingFailureCode,
    SyntheticRouteCertification,
    SyntheticRouteQuote,
    fail_routing,
    require_routing_utc,
)
from raos.ports.ai_routing import (
    DevelopmentAiControlPort,
    SyntheticRouteEligibilityPort,
)
from raos.ports.task_registry import (
    InvalidTaskCode,
    TaskRegistry,
    TaskRegistryIntegrityError,
    UnknownTaskContract,
)


_MAX_ELIGIBILITY_CANDIDATES = 1_024
_CONTROL_FAILURES = frozenset(
    {
        RoutingFailureCode.DEVELOPMENT_ONLY,
        RoutingFailureCode.INVALID_REQUEST,
        RoutingFailureCode.CIRCUIT_OPEN,
        RoutingFailureCode.BUDGET_EXCEEDED,
        RoutingFailureCode.RESERVATION_UNKNOWN,
        RoutingFailureCode.RESERVATION_MISMATCH,
        RoutingFailureCode.RESERVATION_REPLAY,
        RoutingFailureCode.RESERVATION_NOT_YET_VALID,
        RoutingFailureCode.RESERVATION_EXPIRED,
        RoutingFailureCode.CONTROL_FAILURE,
    }
)


def _require_development(environment: object) -> RuntimeEnvironment:
    if (
        type(environment) is not RuntimeEnvironment
        or environment is not RuntimeEnvironment.ENV_DEV
    ):
        fail_routing(RoutingFailureCode.DEVELOPMENT_ONLY)
    return environment


def _supports_task_registry(candidate: object) -> bool:
    supported = False
    try:
        supported = isinstance(candidate, TaskRegistry)
    except Exception:
        pass
    return supported


def _supports_eligibility(candidate: object) -> bool:
    supported = False
    try:
        supported = isinstance(candidate, SyntheticRouteEligibilityPort)
    except Exception:
        pass
    return supported


def _supports_controls(candidate: object) -> bool:
    supported = False
    try:
        supported = isinstance(candidate, DevelopmentAiControlPort)
    except Exception:
        pass
    return supported


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


def _normalize_quote(candidate: object) -> SyntheticRouteQuote:
    normalized: SyntheticRouteQuote | None = None
    expected_digest: object = None
    if type(candidate) is SyntheticRouteQuote:
        try:
            expected_digest = candidate.quote_sha256
            normalized = SyntheticRouteQuote(
                identity=_normalize_identity(candidate.identity),
                certification_id=candidate.certification_id,
                quote_id=candidate.quote_id,
                estimated_cost_jpy=candidate.estimated_cost_jpy,
                valid_from=candidate.valid_from,
                expires_at=candidate.expires_at,
            )
        except Exception:
            pass
    if normalized is None or normalized.quote_sha256 != expected_digest:
        fail_routing(RoutingFailureCode.INVALID_REQUEST)
    return normalized


def _normalize_request(candidate: object) -> RouteReservationRequest:
    normalized: RouteReservationRequest | None = None
    if type(candidate) is RouteReservationRequest:
        try:
            normalized = RouteReservationRequest(
                operation_id=candidate.operation_id,
                task_code=candidate.task_code,
                quote=_normalize_quote(candidate.quote),
                reservation_expires_at=candidate.reservation_expires_at,
            )
        except Exception:
            pass
    if normalized is None:
        fail_routing(RoutingFailureCode.INVALID_REQUEST)
    return normalized


def _normalize_authorization(candidate: object) -> AuthorizedRouteReservation:
    if type(candidate) is not AuthorizedRouteReservation:
        fail_routing(RoutingFailureCode.INVALID_REQUEST)
    normalized: AuthorizedRouteReservation | None = None
    try:
        normalized = AuthorizedRouteReservation(
            identity=_normalize_identity(candidate.identity),
            certification_id=candidate.certification_id,
            task_binding_sha256=candidate.task_binding_sha256,
            route_sha256=candidate.route_sha256,
            reservation=candidate.reservation,
        )
    except Exception:
        pass
    if normalized is None:
        fail_routing(RoutingFailureCode.RESERVATION_MISMATCH)
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
        fail_routing(RoutingFailureCode.ELIGIBILITY_UNAVAILABLE)
    return normalized


def _normalize_commit_receipt(
    candidate: object, *, expected: BudgetCommit
) -> BudgetCommit:
    normalized: BudgetCommit | None = None
    if type(candidate) is BudgetCommit:
        try:
            normalized = BudgetCommit(
                reservation_id=candidate.reservation_id,
                intent_sha256=candidate.intent_sha256,
                committed_jpy=candidate.committed_jpy,
                committed_at=candidate.committed_at,
            )
        except Exception:
            pass
    if normalized is None or normalized != expected:
        fail_routing(RoutingFailureCode.CONTROL_FAILURE)
    return normalized


def _normalize_release_receipt(
    candidate: object, *, expected: BudgetRelease
) -> BudgetRelease:
    normalized: BudgetRelease | None = None
    if type(candidate) is BudgetRelease:
        try:
            normalized = BudgetRelease(
                reservation_id=candidate.reservation_id,
                intent_sha256=candidate.intent_sha256,
                released_jpy=candidate.released_jpy,
                released_at=candidate.released_at,
            )
        except Exception:
            pass
    if normalized is None or normalized != expected:
        fail_routing(RoutingFailureCode.CONTROL_FAILURE)
    return normalized


def _route_enabled(metadata: Mapping[str, object]) -> bool:
    return (
        metadata.get("enabled") is True
        and metadata.get("store") is False
        and metadata.get("strict_structured_output") is True
    )


class DevelopmentAiRoutingService:
    """Authorize one synthetic route and reserve its direct-JPY test quote.

    This service has no provider execution dependency. The ST-0701 registry is
    only a hash-bound candidate catalog; a matching injected synthetic
    certification remains mandatory for every authorization.
    """

    __slots__ = ("_controls", "_eligibility", "_environment", "_task_registry")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        task_registry: TaskRegistry,
        eligibility: SyntheticRouteEligibilityPort,
        controls: DevelopmentAiControlPort,
    ) -> None:
        self._environment = _require_development(environment)
        if not _supports_task_registry(task_registry):
            raise TypeError("task_registry must implement TaskRegistry")
        if not _supports_eligibility(eligibility):
            raise TypeError("eligibility must implement SyntheticRouteEligibilityPort")
        if not _supports_controls(controls):
            raise TypeError("controls must implement DevelopmentAiControlPort")
        self._task_registry = task_registry
        self._eligibility = eligibility
        self._controls = controls

    def authorize_and_reserve(
        self, *, request: RouteReservationRequest, now: datetime
    ) -> AuthorizedRouteReservation:
        """Resolve one exact fixture and atomically reserve its synthetic quote."""

        self._guard()
        normalized_request = _normalize_request(request)
        observed_at = require_routing_utc(now)
        task = self._load_task(normalized_request.task_code)
        identity = normalized_request.quote.identity

        if normalized_request.task_code != identity.task_code:
            fail_routing(RoutingFailureCode.QUOTE_MISMATCH)
        if task.route.route_code != identity.route_code:
            fail_routing(RoutingFailureCode.UNKNOWN_ROUTE)
        if not self._task_permits_local_fixture(task):
            fail_routing(RoutingFailureCode.INELIGIBLE_CANDIDATE)

        candidates = self._load_candidates(normalized_request.task_code)
        if not candidates:
            fail_routing(RoutingFailureCode.INELIGIBLE_CANDIDATE)
        route_candidates = tuple(
            item
            for item in candidates
            if item.identity.route_code == identity.route_code
        )
        if not route_candidates:
            fail_routing(RoutingFailureCode.INELIGIBLE_CANDIDATE)
        version_candidates = tuple(
            item
            for item in route_candidates
            if item.identity.route_version == identity.route_version
        )
        if not version_candidates:
            fail_routing(RoutingFailureCode.UNKNOWN_ROUTE_VERSION)
        model_candidates = tuple(
            item
            for item in version_candidates
            if item.identity.model_id == identity.model_id
        )
        if not model_candidates:
            fail_routing(RoutingFailureCode.UNKNOWN_MODEL)
        if len(model_candidates) != 1:
            fail_routing(RoutingFailureCode.ELIGIBILITY_UNAVAILABLE)
        certification = model_candidates[0]

        self._validate_certification(
            certification=certification,
            task=task,
            observed_at=observed_at,
        )
        self._validate_quote_and_window(
            request=normalized_request,
            certification=certification,
            observed_at=observed_at,
        )
        intent = ReservationIntent(
            operation_id=normalized_request.operation_id,
            identity=identity,
            task_binding_sha256=task.binding_sha256,
            route_sha256=task.route.sha256,
            certification_id=certification.certification_id,
            quote_sha256=normalized_request.quote.quote_sha256,
            reserved_jpy=normalized_request.quote.estimated_cost_jpy,
            authorized_at=observed_at,
            expires_at=normalized_request.reservation_expires_at,
        )
        reservation = self._reserve(intent=intent, now=observed_at)
        if not reservation.matches_intent(intent):
            fail_routing(RoutingFailureCode.CONTROL_FAILURE)
        return AuthorizedRouteReservation(
            identity=identity,
            certification_id=certification.certification_id,
            task_binding_sha256=task.binding_sha256,
            route_sha256=task.route.sha256,
            reservation=reservation,
        )

    def commit(
        self,
        *,
        authorization: AuthorizedRouteReservation,
        committed_jpy: int,
        now: datetime,
    ) -> BudgetCommit:
        """Commit one authorization without executing its selected model."""

        self._guard()
        normalized_authorization = _normalize_authorization(authorization)
        observed_at = require_routing_utc(now)
        expected = BudgetCommit(
            reservation_id=normalized_authorization.reservation.reservation_id,
            intent_sha256=normalized_authorization.reservation.intent_sha256,
            committed_jpy=committed_jpy,
            committed_at=observed_at,
        )
        try:
            result = self._controls.commit(
                reservation=normalized_authorization.reservation,
                committed_jpy=committed_jpy,
                now=observed_at,
            )
        except RoutingFailure as error:
            self._pass_control_failure(error)
        except Exception:
            fail_routing(RoutingFailureCode.CONTROL_FAILURE)
        return _normalize_commit_receipt(result, expected=expected)

    def release(
        self, *, authorization: AuthorizedRouteReservation, now: datetime
    ) -> BudgetRelease:
        """Release one authorization without invoking any external system."""

        self._guard()
        normalized_authorization = _normalize_authorization(authorization)
        observed_at = require_routing_utc(now)
        expected = BudgetRelease(
            reservation_id=normalized_authorization.reservation.reservation_id,
            intent_sha256=normalized_authorization.reservation.intent_sha256,
            released_jpy=normalized_authorization.reservation.reserved_jpy,
            released_at=observed_at,
        )
        try:
            result = self._controls.release(
                reservation=normalized_authorization.reservation,
                now=observed_at,
            )
        except RoutingFailure as error:
            self._pass_control_failure(error)
        except Exception:
            fail_routing(RoutingFailureCode.CONTROL_FAILURE)
        return _normalize_release_receipt(result, expected=expected)

    def trip_circuit_open(self, *, identity: RouteIdentity, now: datetime) -> None:
        """Open one circuit permanently for the lifetime of the control adapter."""

        self._guard()
        normalized_identity = _normalize_identity(identity)
        observed_at = require_routing_utc(now)
        try:
            self._controls.trip_open(identity=normalized_identity, now=observed_at)
        except RoutingFailure as error:
            self._pass_control_failure(error)
        except Exception:
            fail_routing(RoutingFailureCode.CONTROL_FAILURE)

    def _load_task(self, task_code: str) -> TaskContract:
        candidate: object = None
        try:
            candidate = self._task_registry.get(task_code)
        except InvalidTaskCode:
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        except UnknownTaskContract:
            fail_routing(RoutingFailureCode.UNKNOWN_TASK)
        except TaskRegistryIntegrityError:
            fail_routing(RoutingFailureCode.REGISTRY_UNAVAILABLE)
        except Exception:
            fail_routing(RoutingFailureCode.REGISTRY_UNAVAILABLE)
        if type(candidate) is not TaskContract or candidate.task_code != task_code:
            fail_routing(RoutingFailureCode.REGISTRY_UNAVAILABLE)
        return candidate

    def _load_candidates(
        self, task_code: str
    ) -> tuple[SyntheticRouteCertification, ...]:
        candidate_values: object = None
        try:
            candidate_values = self._eligibility.candidates_for(task_code=task_code)
        except RoutingFailure as error:
            if (
                type(error) is RoutingFailure
                and error.code is RoutingFailureCode.DEVELOPMENT_ONLY
            ):
                fail_routing(RoutingFailureCode.DEVELOPMENT_ONLY)
            fail_routing(RoutingFailureCode.ELIGIBILITY_UNAVAILABLE)
        except Exception:
            fail_routing(RoutingFailureCode.ELIGIBILITY_UNAVAILABLE)
        if (
            type(candidate_values) is not tuple
            or len(candidate_values) > _MAX_ELIGIBILITY_CANDIDATES
        ):
            fail_routing(RoutingFailureCode.ELIGIBILITY_UNAVAILABLE)
        normalized = tuple(_normalize_certification(item) for item in candidate_values)
        if any(item.identity.task_code != task_code for item in normalized):
            fail_routing(RoutingFailureCode.ELIGIBILITY_UNAVAILABLE)
        identities = [item.identity for item in normalized]
        if len(set(identities)) != len(identities):
            fail_routing(RoutingFailureCode.ELIGIBILITY_UNAVAILABLE)
        return tuple(
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

    @staticmethod
    def _task_permits_local_fixture(task: TaskContract) -> bool:
        try:
            metadata = task.route.metadata
            return (
                task.prompt.status == "CANDIDATE"
                and "DISABLED" not in task.lifecycle
                and _route_enabled(metadata)
            )
        except Exception:
            return False

    @staticmethod
    def _validate_certification(
        *,
        certification: SyntheticRouteCertification,
        task: TaskContract,
        observed_at: datetime,
    ) -> None:
        if (
            not certification.eligible
            or certification.task_binding_sha256 != task.binding_sha256
            or certification.route_sha256 != task.route.sha256
            or observed_at < certification.valid_from
            or observed_at >= certification.expires_at
        ):
            fail_routing(RoutingFailureCode.INELIGIBLE_CANDIDATE)

    @staticmethod
    def _validate_quote_and_window(
        *,
        request: RouteReservationRequest,
        certification: SyntheticRouteCertification,
        observed_at: datetime,
    ) -> None:
        quote = request.quote
        if (
            quote.identity != certification.identity
            or quote.certification_id != certification.certification_id
        ):
            fail_routing(RoutingFailureCode.QUOTE_MISMATCH)
        if observed_at < quote.valid_from:
            fail_routing(RoutingFailureCode.QUOTE_NOT_YET_VALID)
        if observed_at >= quote.expires_at:
            fail_routing(RoutingFailureCode.QUOTE_EXPIRED)
        if request.reservation_expires_at <= observed_at:
            fail_routing(RoutingFailureCode.RESERVATION_EXPIRED)
        if request.reservation_expires_at > min(
            quote.expires_at, certification.expires_at
        ):
            fail_routing(RoutingFailureCode.QUOTE_MISMATCH)

    def _reserve(
        self, *, intent: ReservationIntent, now: datetime
    ) -> BudgetReservation:
        try:
            candidate = self._controls.reserve(intent=intent, now=now)
        except RoutingFailure as error:
            self._pass_control_failure(error)
        except Exception:
            fail_routing(RoutingFailureCode.CONTROL_FAILURE)
        if type(candidate) is not BudgetReservation:
            fail_routing(RoutingFailureCode.CONTROL_FAILURE)
        return candidate

    @staticmethod
    def _pass_control_failure(error: RoutingFailure) -> NoReturn:
        if type(error) is RoutingFailure and error.code in _CONTROL_FAILURES:
            fail_routing(error.code)
        fail_routing(RoutingFailureCode.CONTROL_FAILURE)

    def _guard(self) -> None:
        _require_development(self._environment)


__all__ = ["DevelopmentAiRoutingService"]

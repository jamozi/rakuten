"""Deterministic recorded/synthetic unit economics for Canonical ST-1304.

Only verified, same-program, same-period and mature recorded inputs are
calculated.  Article economics use verified Direct reward; Estimated and
Unattributed reward stay visible but are never allocated into an article or a
recommendation signal.  Missing facts remain unavailable rather than zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, DecimalException, ROUND_HALF_EVEN, localcontext
from enum import Enum
import hashlib
import json
import re
from typing import Final, NoReturn, SupportsIndex
from uuid import RFC_4122, UUID

from raos.domain.finance.attribution import (
    PROGRAM,
    ArticleMeasurement,
    AttributionAvailability,
    AttributionRunRequest,
    AttributionRunResult,
    CohortMaturity,
    ContractArticle,
    MeasurementPeriod,
    MeasurementValue,
    MeasurementValueState,
    VerificationState,
    build_attribution_run,
)
from raos.domain.finance.provider_fact_commit import JpyAmount
from raos.domain.ops.object_intake import Sha256Digest


PROFILE: Final = "RAOS_ST1304_RECORDED_SYNTHETIC_V2"
METHOD_VERSION: Final = "RAOS_ST1304_DIRECT_UNIT_ECONOMICS_V2"
_MAX_CANONICAL_BYTES: Final = 4 * 1024 * 1024
_MAX_VALUE: Final = (1 << 63) - 1
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)

COST_COMPONENT_METRICS: Final = (
    "ai_actual_cost_jpy",
    "api_actual_cost_jpy",
    "hosting_actual_cost_jpy",
    "observability_actual_cost_jpy",
    "analytics_actual_cost_jpy",
    "content_tool_actual_cost_jpy",
    "other_actual_cost_jpy",
)
COST_METRICS: Final = (
    *COST_COMPONENT_METRICS,
    "work_minutes",
    "incremental_cost_jpy",
    "qualified_sessions",
    "article_update_cost_jpy",
    "initial_content_cost_jpy",
    "approved_article_versions",
    "trailing_monthly_confirmed_contribution_jpy",
    "labor_hourly_cost_jpy",
)
METRIC_NAMES: Final = (
    "confirmed_provider_reward_jpy",
    "direct_confirmed_reward_jpy",
    "direct_confirmed_contribution_profit_jpy",
    "confirmed_epc_jpy",
    "confirmed_rpm_jpy",
    "article_update_cost_ratio",
    "content_payback_months",
    "ai_cost_per_approved_article_jpy",
    "confirmed_reward_per_content_hour_jpy",
)
RECOMMENDATION_INPUTS_EXCLUDED: Final = (
    "AFFILIATE_COMMISSION_RATE",
    "CONFIRMED_REWARD",
    "UNATTRIBUTED_REWARD",
    "ESTIMATED_REWARD",
    "COMMISSION",
    "INCREMENTAL_COST",
    "LABOR_COST",
    "EPC",
    "RPM",
    "PROFIT",
)


class UnitEconomicsFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    INPUT_HASH_MISMATCH = "INPUT_HASH_MISMATCH"
    ATTRIBUTION_RESULT_MISMATCH = "ATTRIBUTION_RESULT_MISMATCH"
    ARTICLE_BINDING_INVALID = "ARTICLE_BINDING_INVALID"
    MEASUREMENT_COST_MISMATCH = "MEASUREMENT_COST_MISMATCH"
    COST_CONSERVATION_FAILED = "COST_CONSERVATION_FAILED"
    RESULT_MISMATCH = "RESULT_MISMATCH"
    RUN_ID_CONFLICT = "RUN_ID_CONFLICT"
    RECORDED_RUN_UNAVAILABLE = "RECORDED_RUN_UNAVAILABLE"
    LOCAL_ENVIRONMENT_REQUIRED = "LOCAL_ENVIRONMENT_REQUIRED"
    FIXTURE_INVALID = "FIXTURE_INVALID"


class UnitEconomicsFailure(RuntimeError):
    """Closed non-reflecting failure; rejected finance input is not retained."""

    __slots__ = ("_code",)

    def __init__(self, code: UnitEconomicsFailureCode) -> None:
        if type(code) is not UnitEconomicsFailureCode:
            raise TypeError("invalid unit-economics failure code") from None
        self._code = code
        super().__init__(code.value)

    @property
    def code(self) -> UnitEconomicsFailureCode:
        return self._code

    def __str__(self) -> str:
        return self._code.value

    def __repr__(self) -> str:
        return f"UnitEconomicsFailure(code={self._code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("unit-economics failure serialization is forbidden")


def fail_unit_economics(
    code: UnitEconomicsFailureCode = UnitEconomicsFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise UnitEconomicsFailure(code) from None


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-st1304>)"

    def __str__(self) -> str:
        return "<redacted-st1304>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("unit-economics value serialization is forbidden")


def _canonical_bytes(value: object) -> bytes:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except Exception:
        fail_unit_economics()
    if not payload or len(payload) > _MAX_CANONICAL_BYTES:
        fail_unit_economics()
    return payload


def _digest(value: object) -> Sha256Digest:
    return Sha256Digest(hashlib.sha256(_canonical_bytes(value)).hexdigest())


def _sha(value: object) -> Sha256Digest:
    if type(value) is not Sha256Digest or _SHA256.fullmatch(value.value) is None:
        fail_unit_economics()
    return Sha256Digest(value.value)


def _uuid7(value: object) -> UUID:
    if type(value) is not UUID or value.version != 7 or value.variant != RFC_4122:
        fail_unit_economics()
    return value


def _utc_second(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
        or value.microsecond != 0
        or value.fold != 0
    ):
        fail_unit_economics()
    return value.replace(tzinfo=timezone.utc)


def _instant_text(value: datetime) -> str:
    return _utc_second(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _decimal_text(value: Decimal) -> str:
    if type(value) is not Decimal or not value.is_finite():
        fail_unit_economics()
    return format(value, "f")


def _observed_value(value: MeasurementValue) -> int | None:
    if type(value) is not MeasurementValue:
        fail_unit_economics()
    if not value.observed:
        return None
    if type(value.value) is not int or not 0 <= value.value <= _MAX_VALUE:
        fail_unit_economics()
    return value.value


class EconomicsAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class MetricAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class UnavailableReason(str, Enum):
    MISSING_INPUT = "MISSING_INPUT"
    UNVERIFIED_INPUT = "UNVERIFIED_INPUT"
    ZERO_DENOMINATOR = "ZERO_DENOMINATOR"
    COHORT_IMMATURE = "COHORT_IMMATURE"
    PERIOD_MISMATCH = "PERIOD_MISMATCH"
    PROGRAM_MISMATCH = "PROGRAM_MISMATCH"
    MISSING_ARTICLE_SLOTS = "MISSING_ARTICLE_SLOTS"
    ATTRIBUTION_UNAVAILABLE = "ATTRIBUTION_UNAVAILABLE"
    LABOR_RATE_UNKNOWN = "LABOR_RATE_UNKNOWN"


class MetricBasis(str, Enum):
    PROVIDER_FACT = "VERIFIED_PROVIDER_FACT_TOTAL"
    DIRECT_ONLY = "VERIFIED_DIRECT_ONLY_ESTIMATED_UNATTRIBUTED_EXCLUDED"


class MetricUnit(str, Enum):
    JPY = "JPY"
    JPY_PER_CLICK = "JPY_PER_CLICK"
    JPY_PER_1000_SESSIONS = "JPY_PER_1000_SESSIONS"
    RATIO = "RATIO"
    MONTHS = "MONTHS"
    JPY_PER_APPROVED_ARTICLE = "JPY_PER_APPROVED_ARTICLE"
    JPY_PER_CONTENT_HOUR = "JPY_PER_CONTENT_HOUR"


@dataclass(frozen=True, slots=True, repr=False)
class ArticleCostObservation(_Redacted):
    article: ContractArticle
    program: str
    period: MeasurementPeriod
    verification_state: VerificationState
    verification_sha256: Sha256Digest | None
    cohort_state: CohortMaturity
    cohort_sha256: Sha256Digest | None
    metrics: tuple[tuple[str, MeasurementValue], ...]

    def __post_init__(self) -> None:
        if (
            type(self.article) is not ContractArticle
            or type(self.program) is not str
            or type(self.period) is not MeasurementPeriod
            or type(self.verification_state) is not VerificationState
            or type(self.cohort_state) is not CohortMaturity
            or type(self.metrics) is not tuple
            or any(
                type(item) is not tuple
                or len(item) != 2
                or type(item[0]) is not str
                or type(item[1]) is not MeasurementValue
                for item in self.metrics
            )
            or tuple(item[0] for item in self.metrics) != COST_METRICS
        ):
            fail_unit_economics()
        if self.verification_state is VerificationState.UNAVAILABLE:
            if self.verification_sha256 is not None:
                fail_unit_economics()
        elif self.verification_sha256 is None:
            fail_unit_economics()
        else:
            object.__setattr__(
                self, "verification_sha256", _sha(self.verification_sha256)
            )
        if self.cohort_state is CohortMaturity.UNAVAILABLE:
            if self.cohort_sha256 is not None:
                fail_unit_economics()
        elif self.cohort_sha256 is None:
            fail_unit_economics()
        else:
            object.__setattr__(self, "cohort_sha256", _sha(self.cohort_sha256))
        values = self.metric_map
        components = tuple(
            _observed_value(values[name]) for name in COST_COMPONENT_METRICS
        )
        incremental = _observed_value(values["incremental_cost_jpy"])
        if incremental is not None and all(value is not None for value in components):
            if (
                sum(int(value) for value in components if value is not None)
                != incremental
            ):
                fail_unit_economics(UnitEconomicsFailureCode.COST_CONSERVATION_FAILED)

    @property
    def metric_map(self) -> dict[str, MeasurementValue]:
        return dict(self.metrics)

    def payload(self) -> dict[str, object]:
        return {
            "article": self.article.payload(),
            "cohort": {
                "input_sha256": (
                    None if self.cohort_sha256 is None else self.cohort_sha256.value
                ),
                "state": self.cohort_state.value,
            },
            "metrics": {name: value.payload() for name, value in self.metrics},
            "period": self.period.payload(),
            "program": self.program,
            "verification": {
                "input_sha256": (
                    None
                    if self.verification_sha256 is None
                    else self.verification_sha256.value
                ),
                "state": self.verification_state.value,
            },
        }


@dataclass(frozen=True, slots=True, repr=False)
class UnitEconomicsRunRequest(_Redacted):
    run_id: UUID
    requested_at: datetime
    attribution_request: AttributionRunRequest
    attribution_result: AttributionRunResult
    cost_observations: tuple[ArticleCostObservation, ...]
    input_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.attribution_request) is not AttributionRunRequest
            or type(self.attribution_result) is not AttributionRunResult
            or type(self.cost_observations) is not tuple
            or not 1 <= len(self.cost_observations) <= 5
            or any(
                type(item) is not ArticleCostObservation
                for item in self.cost_observations
            )
            or tuple(item.article.slot for item in self.cost_observations)
            != tuple(sorted(item.article.slot for item in self.cost_observations))
            or len({item.article.slot for item in self.cost_observations})
            != len(self.cost_observations)
        ):
            fail_unit_economics()
        object.__setattr__(self, "run_id", _uuid7(self.run_id))
        object.__setattr__(self, "requested_at", _utc_second(self.requested_at))
        object.__setattr__(self, "input_sha256", _digest(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "attribution_input_sha256": self.attribution_request.input_sha256.value,
            "attribution_result_sha256": self.attribution_result.result_sha256.value,
            "cost_observations": [item.payload() for item in self.cost_observations],
            "method_version": METHOD_VERSION,
            "profile": PROFILE,
            "requested_at": _instant_text(self.requested_at),
            "run_id": str(self.run_id),
        }

    def canonical_bytes(self) -> bytes:
        payload = self._payload()
        payload["input_sha256"] = self.input_sha256.value
        return _canonical_bytes(payload)


@dataclass(frozen=True, slots=True, repr=False)
class UnitEconomicsMetric(_Redacted):
    metric_id: str
    name: str
    availability: MetricAvailability
    unavailable_reason: UnavailableReason | None
    value: Decimal | None
    numerator: Decimal | None
    denominator: Decimal | None
    unit: MetricUnit
    basis: MetricBasis
    period: MeasurementPeriod
    program: str
    source_sha256s: tuple[Sha256Digest, ...]

    def __post_init__(self) -> None:
        if (
            type(self.metric_id) is not str
            or not self.metric_id
            or self.name not in METRIC_NAMES
            or type(self.availability) is not MetricAvailability
            or type(self.unit) is not MetricUnit
            or type(self.basis) is not MetricBasis
            or type(self.period) is not MeasurementPeriod
            or self.program != PROGRAM
            or type(self.source_sha256s) is not tuple
            or any(type(item) is not Sha256Digest for item in self.source_sha256s)
            or len({item.value for item in self.source_sha256s})
            != len(self.source_sha256s)
        ):
            fail_unit_economics()
        if self.availability is MetricAvailability.UNAVAILABLE:
            if (
                type(self.unavailable_reason) is not UnavailableReason
                or self.value is not None
                or self.numerator is not None
                or self.denominator is not None
                or self.source_sha256s
            ):
                fail_unit_economics()
            return
        if (
            self.unavailable_reason is not None
            or type(self.value) is not Decimal
            or not self.value.is_finite()
            or type(self.numerator) is not Decimal
            or not self.numerator.is_finite()
            or (
                self.denominator is not None
                and (
                    type(self.denominator) is not Decimal
                    or not self.denominator.is_finite()
                    or self.denominator <= 0
                )
            )
            or not self.source_sha256s
        ):
            fail_unit_economics()

    def payload(self) -> dict[str, object]:
        return {
            "availability": self.availability.value,
            "basis": self.basis.value,
            "denominator": (
                None if self.denominator is None else _decimal_text(self.denominator)
            ),
            "metric_id": self.metric_id,
            "name": self.name,
            "numerator": (
                None if self.numerator is None else _decimal_text(self.numerator)
            ),
            "period": self.period.payload(),
            "program": self.program,
            "source_sha256s": [item.value for item in self.source_sha256s],
            "unavailable_reason": (
                None
                if self.unavailable_reason is None
                else self.unavailable_reason.value
            ),
            "unit": self.unit.value,
            "value_decimal": None if self.value is None else _decimal_text(self.value),
        }


@dataclass(frozen=True, slots=True, repr=False)
class UnitEconomicsTotals(_Redacted):
    provider_confirmed_reward_jpy: JpyAmount
    direct_confirmed_reward_jpy: JpyAmount
    estimated_confirmed_reward_jpy: JpyAmount
    unattributed_confirmed_reward_jpy: JpyAmount
    incremental_external_cost_jpy: Decimal | None
    human_labor_cost_jpy: Decimal | None
    work_minutes: int | None
    qualified_sessions: int | None

    def __post_init__(self) -> None:
        rewards = (
            self.provider_confirmed_reward_jpy,
            self.direct_confirmed_reward_jpy,
            self.estimated_confirmed_reward_jpy,
            self.unattributed_confirmed_reward_jpy,
        )
        if any(type(item) is not JpyAmount for item in rewards):
            fail_unit_economics()
        if (
            self.direct_confirmed_reward_jpy.value
            + self.estimated_confirmed_reward_jpy.value
            + self.unattributed_confirmed_reward_jpy.value
            != self.provider_confirmed_reward_jpy.value
        ):
            fail_unit_economics(UnitEconomicsFailureCode.COST_CONSERVATION_FAILED)
        for decimal_value in (
            self.incremental_external_cost_jpy,
            self.human_labor_cost_jpy,
        ):
            if decimal_value is not None and (
                type(decimal_value) is not Decimal
                or not decimal_value.is_finite()
                or decimal_value < 0
            ):
                fail_unit_economics()
        for count_value in (self.work_minutes, self.qualified_sessions):
            if count_value is not None and (
                type(count_value) is not int or count_value < 0
            ):
                fail_unit_economics()

    def payload(self) -> dict[str, object]:
        return {
            "direct_confirmed_reward_jpy": self.direct_confirmed_reward_jpy.canonical_text,
            "estimated_confirmed_reward_jpy": (
                self.estimated_confirmed_reward_jpy.canonical_text
            ),
            "human_labor_cost_jpy": (
                None
                if self.human_labor_cost_jpy is None
                else _decimal_text(self.human_labor_cost_jpy)
            ),
            "incremental_external_cost_jpy": (
                None
                if self.incremental_external_cost_jpy is None
                else _decimal_text(self.incremental_external_cost_jpy)
            ),
            "provider_confirmed_reward_jpy": (
                self.provider_confirmed_reward_jpy.canonical_text
            ),
            "qualified_sessions": self.qualified_sessions,
            "reward_conservation_difference_jpy": "0",
            "unattributed_confirmed_reward_jpy": (
                self.unattributed_confirmed_reward_jpy.canonical_text
            ),
            "work_minutes": self.work_minutes,
        }


@dataclass(frozen=True, slots=True, repr=False)
class UnitEconomicsAuthority(_Redacted):
    provider_call: bool = False
    network: bool = False
    persistence: bool = False
    public_projection: bool = False
    publication: bool = False
    editorial_mutation: bool = False
    article_html_mutation: bool = False
    cta_mutation: bool = False
    product_selection_mutation: bool = False
    recommendation_order_mutation: bool = False
    publication_snapshot_mutation: bool = False
    budget_selection: bool = False
    labor_rate_selection: bool = False
    staging: bool = False
    release: bool = False
    production: bool = False

    def __post_init__(self) -> None:
        if any(getattr(self, name) is not False for name in self.__slots__):
            fail_unit_economics()

    def payload(self) -> dict[str, object]:
        return {name: False for name in self.__slots__}


@dataclass(frozen=True, slots=True, repr=False)
class UnitEconomicsRunResult(_Redacted):
    result_sha256: Sha256Digest
    run_id: UUID
    input_sha256: Sha256Digest
    method_version: str
    availability: EconomicsAvailability
    unavailable_reason: UnavailableReason | None
    metrics: tuple[UnitEconomicsMetric, ...]
    totals: UnitEconomicsTotals
    cost_provenance: tuple[ArticleCostObservation, ...]
    authority: UnitEconomicsAuthority

    def __post_init__(self) -> None:
        if (
            self.method_version != METHOD_VERSION
            or type(self.availability) is not EconomicsAvailability
            or type(self.metrics) is not tuple
            or any(type(item) is not UnitEconomicsMetric for item in self.metrics)
            or tuple(item.name for item in self.metrics) != METRIC_NAMES
            or type(self.totals) is not UnitEconomicsTotals
            or type(self.cost_provenance) is not tuple
            or any(
                type(item) is not ArticleCostObservation
                for item in self.cost_provenance
            )
            or type(self.authority) is not UnitEconomicsAuthority
        ):
            fail_unit_economics()
        object.__setattr__(self, "result_sha256", _sha(self.result_sha256))
        object.__setattr__(self, "run_id", _uuid7(self.run_id))
        object.__setattr__(self, "input_sha256", _sha(self.input_sha256))
        unavailable_count = sum(
            item.availability is MetricAvailability.UNAVAILABLE for item in self.metrics
        )
        expected = (
            EconomicsAvailability.AVAILABLE
            if unavailable_count == 0
            else (
                EconomicsAvailability.UNAVAILABLE
                if unavailable_count == len(self.metrics)
                else EconomicsAvailability.PARTIAL
            )
        )
        if self.availability is not expected:
            fail_unit_economics()
        if self.availability is EconomicsAvailability.UNAVAILABLE:
            if type(self.unavailable_reason) is not UnavailableReason:
                fail_unit_economics()
        elif self.unavailable_reason is not None:
            fail_unit_economics()

    def payload(self, *, include_result_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "authority": self.authority.payload(),
            "availability": self.availability.value,
            "cost_provenance": [item.payload() for item in self.cost_provenance],
            "input_sha256": self.input_sha256.value,
            "method_version": self.method_version,
            "metrics": [item.payload() for item in self.metrics],
            "profile": PROFILE,
            "recommendation_input_policy": {
                "all_finance_values_excluded": True,
                "excluded": list(RECOMMENDATION_INPUTS_EXCLUDED),
                "finance_may_change_article_html": False,
                "finance_may_change_cta": False,
                "finance_may_change_product_selection": False,
                "finance_may_change_publication_snapshot": False,
                "finance_may_change_recommendation_order": False,
            },
            "reward_basis_policy": {
                "article_economics": MetricBasis.DIRECT_ONLY.value,
                "estimated_reward_in_article_metrics": False,
                "provider_total_visible_separately": True,
                "unattributed_allocation_to_articles": False,
                "unattributed_reward_visible_separately": True,
            },
            "run_id": str(self.run_id),
            "totals": self.totals.payload(),
            "unavailable_reason": (
                None
                if self.unavailable_reason is None
                else self.unavailable_reason.value
            ),
        }
        if include_result_hash:
            payload["result_sha256"] = self.result_sha256.value
        return payload

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.payload())


@dataclass(frozen=True, slots=True)
class _Aggregate:
    value: Decimal | None
    reason: UnavailableReason | None
    sources: tuple[Sha256Digest, ...]


def _measurement_aggregate(values: tuple[MeasurementValue, ...]) -> _Aggregate:
    if not values or any(type(item) is not MeasurementValue for item in values):
        fail_unit_economics()
    if any(item.state is MeasurementValueState.UNVERIFIED for item in values):
        return _Aggregate(None, UnavailableReason.UNVERIFIED_INPUT, ())
    if any(not item.observed for item in values):
        return _Aggregate(None, UnavailableReason.MISSING_INPUT, ())
    sources: list[Sha256Digest] = []
    observed_values: list[int] = []
    for item in values:
        if item.input_sha256 is None:
            fail_unit_economics()
        observed = _observed_value(item)
        if observed is None:
            fail_unit_economics()
        observed_values.append(observed)
        if item.input_sha256.value not in {source.value for source in sources}:
            sources.append(item.input_sha256)
    return _Aggregate(
        sum((Decimal(item) for item in observed_values), Decimal(0)),
        None,
        tuple(sources),
    )


def _unavailable_metric(
    *,
    metric_id: str,
    name: str,
    reason: UnavailableReason,
    unit: MetricUnit,
    basis: MetricBasis,
    request: UnitEconomicsRunRequest,
) -> UnitEconomicsMetric:
    return UnitEconomicsMetric(
        metric_id=metric_id,
        name=name,
        availability=MetricAvailability.UNAVAILABLE,
        unavailable_reason=reason,
        value=None,
        numerator=None,
        denominator=None,
        unit=unit,
        basis=basis,
        period=request.attribution_request.period,
        program=request.attribution_request.program,
        source_sha256s=(),
    )


def _available_metric(
    *,
    metric_id: str,
    name: str,
    value: Decimal,
    numerator: Decimal,
    denominator: Decimal | None,
    unit: MetricUnit,
    basis: MetricBasis,
    request: UnitEconomicsRunRequest,
    sources: tuple[Sha256Digest, ...],
) -> UnitEconomicsMetric:
    return UnitEconomicsMetric(
        metric_id=metric_id,
        name=name,
        availability=MetricAvailability.AVAILABLE,
        unavailable_reason=None,
        value=value,
        numerator=numerator,
        denominator=denominator,
        unit=unit,
        basis=basis,
        period=request.attribution_request.period,
        program=request.attribution_request.program,
        source_sha256s=sources,
    )


def _readiness(request: UnitEconomicsRunRequest) -> UnavailableReason | None:
    expected = build_attribution_run(request.attribution_request)
    if (
        request.attribution_result != expected
        or request.attribution_result.canonical_bytes() != expected.canonical_bytes()
    ):
        fail_unit_economics(UnitEconomicsFailureCode.ATTRIBUTION_RESULT_MISMATCH)
    if request.attribution_result.availability is not AttributionAvailability.AVAILABLE:
        return UnavailableReason.ATTRIBUTION_UNAVAILABLE
    if len(request.cost_observations) != 5 or tuple(
        item.article.slot for item in request.cost_observations
    ) != (1, 2, 3, 4, 5):
        return UnavailableReason.MISSING_ARTICLE_SLOTS
    for observed, expected_article in zip(
        request.cost_observations,
        request.attribution_request.contract.articles,
        strict=True,
    ):
        if observed.article != expected_article:
            fail_unit_economics(UnitEconomicsFailureCode.ARTICLE_BINDING_INVALID)
    if request.attribution_request.program != PROGRAM or any(
        item.program != request.attribution_request.program
        for item in request.cost_observations
    ):
        return UnavailableReason.PROGRAM_MISMATCH
    if any(
        item.period != request.attribution_request.period
        for item in request.cost_observations
    ):
        return UnavailableReason.PERIOD_MISMATCH
    if any(
        item.verification_state is VerificationState.UNAVAILABLE
        for item in request.cost_observations
    ):
        return UnavailableReason.MISSING_INPUT
    if any(
        item.verification_state is not VerificationState.VERIFIED
        for item in request.cost_observations
    ):
        return UnavailableReason.UNVERIFIED_INPUT
    if any(
        item.cohort_state is not CohortMaturity.MATURE
        for item in request.cost_observations
    ):
        return UnavailableReason.COHORT_IMMATURE
    return None


def _metric_values(
    request: UnitEconomicsRunRequest, name: str
) -> tuple[MeasurementValue, ...]:
    return tuple(item.metric_map[name] for item in request.cost_observations)


def _article_measurements(
    request: UnitEconomicsRunRequest,
) -> tuple[ArticleMeasurement, ...]:
    return request.attribution_request.article_measurements


def _validate_measurement_cost_binding(request: UnitEconomicsRunRequest) -> None:
    if len(request.cost_observations) != 5:
        return
    by_slot = {item.article.slot: item for item in _article_measurements(request)}
    for cost in request.cost_observations:
        measurement = by_slot.get(cost.article.slot)
        if measurement is None:
            return
        for name in ("work_minutes", "incremental_cost_jpy"):
            cost_value = cost.metric_map[name]
            measured_value = measurement.metric_map[name]
            if (
                cost_value.observed
                and measured_value.observed
                and cost_value != measured_value
            ):
                fail_unit_economics(UnitEconomicsFailureCode.MEASUREMENT_COST_MISMATCH)


def _quantized_ratio(
    numerator: Decimal, denominator: Decimal, *, multiplier: Decimal, quantum: str
) -> Decimal:
    if denominator <= 0:
        fail_unit_economics()
    try:
        with localcontext() as context:
            context.prec = 50
            context.rounding = ROUND_HALF_EVEN
            return (numerator / denominator * multiplier).quantize(
                Decimal(quantum), rounding=ROUND_HALF_EVEN
            )
    except DecimalException, ValueError:
        fail_unit_economics()


def _combined_sources(*groups: tuple[Sha256Digest, ...]) -> tuple[Sha256Digest, ...]:
    result: list[Sha256Digest] = []
    for group in groups:
        for item in group:
            if item.value not in {source.value for source in result}:
                result.append(item)
    return tuple(result)


def build_unit_economics(
    request: UnitEconomicsRunRequest,
) -> UnitEconomicsRunResult:
    """Build one immutable direct-basis unit-economics read model."""

    if type(request) is not UnitEconomicsRunRequest:
        fail_unit_economics()
    if request.input_sha256 != _digest(request._payload()):  # noqa: SLF001
        fail_unit_economics(UnitEconomicsFailureCode.INPUT_HASH_MISMATCH)
    readiness = _readiness(request)
    _validate_measurement_cost_binding(request)

    attribution_sources = (request.attribution_result.input_sha256,)
    totals = request.attribution_result.totals
    direct = totals.direct_confirmed_reward_jpy
    provider = totals.provider_confirmed_reward_jpy
    estimated = totals.estimated_confirmed_reward_jpy
    unattributed = totals.unattributed_confirmed_reward_jpy

    recorded_external = _measurement_aggregate(
        _metric_values(request, "incremental_cost_jpy")
    )
    cost_components = tuple(
        _measurement_aggregate(_metric_values(request, name))
        for name in COST_COMPONENT_METRICS
    )
    component_reason = next(
        (
            item.reason
            for item in cost_components
            if item.reason is UnavailableReason.UNVERIFIED_INPUT
        ),
        next(
            (item.reason for item in cost_components if item.reason is not None),
            None,
        ),
    )
    if recorded_external.reason is not None:
        external = recorded_external
    elif component_reason is not None:
        external = _Aggregate(None, component_reason, ())
    elif recorded_external.value is None or any(
        item.value is None for item in cost_components
    ):
        external = _Aggregate(None, UnavailableReason.MISSING_INPUT, ())
    else:
        component_total = sum(
            (item.value for item in cost_components if item.value is not None),
            Decimal(0),
        )
        if component_total != recorded_external.value:
            fail_unit_economics(UnitEconomicsFailureCode.COST_CONSERVATION_FAILED)
        external = _Aggregate(
            recorded_external.value,
            None,
            _combined_sources(
                recorded_external.sources,
                *(item.sources for item in cost_components),
            ),
        )
    work = _measurement_aggregate(_metric_values(request, "work_minutes"))
    sessions = _measurement_aggregate(_metric_values(request, "qualified_sessions"))
    update_cost = _measurement_aggregate(
        _metric_values(request, "article_update_cost_jpy")
    )
    initial_cost = _measurement_aggregate(
        _metric_values(request, "initial_content_cost_jpy")
    )
    approved_versions = _measurement_aggregate(
        _metric_values(request, "approved_article_versions")
    )
    trailing_contribution = _measurement_aggregate(
        _metric_values(request, "trailing_monthly_confirmed_contribution_jpy")
    )
    ai_cost = cost_components[0]
    clicks = _measurement_aggregate(
        tuple(
            item.metric_map["affiliate_clicks"]
            for item in _article_measurements(request)
        )
    )
    labor_reason: UnavailableReason | None = None
    labor_sources: tuple[Sha256Digest, ...] = ()
    labor_value: Decimal | None = None
    rate_values = _metric_values(request, "labor_hourly_cost_jpy")
    work_values = _metric_values(request, "work_minutes")
    if any(item.state is MeasurementValueState.UNVERIFIED for item in rate_values):
        labor_reason = UnavailableReason.UNVERIFIED_INPUT
    elif any(not item.observed for item in rate_values):
        labor_reason = UnavailableReason.LABOR_RATE_UNKNOWN
    elif work.reason is not None:
        labor_reason = work.reason
    else:
        labor_value = Decimal(0)
        source_groups: list[tuple[Sha256Digest, ...]] = []
        for rate, minutes in zip(rate_values, work_values, strict=True):
            if rate.input_sha256 is None or minutes.input_sha256 is None:
                fail_unit_economics()
            rate_value = _observed_value(rate)
            minutes_value = _observed_value(minutes)
            if rate_value is None or minutes_value is None:
                fail_unit_economics()
            with localcontext() as context:
                context.prec = 50
                labor_value += (
                    Decimal(rate_value) * Decimal(minutes_value) / Decimal(60)
                )
            source_groups.append((rate.input_sha256, minutes.input_sha256))
        labor_value = labor_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        labor_sources = _combined_sources(*source_groups)

    global_metric_specs = (
        (
            "KPI-001",
            "confirmed_provider_reward_jpy",
            MetricUnit.JPY,
            MetricBasis.PROVIDER_FACT,
        ),
        (
            "SUPPLEMENTAL-DIRECT-REWARD",
            "direct_confirmed_reward_jpy",
            MetricUnit.JPY,
            MetricBasis.DIRECT_ONLY,
        ),
        (
            "KPI-002-DIRECT-VIEW",
            "direct_confirmed_contribution_profit_jpy",
            MetricUnit.JPY,
            MetricBasis.DIRECT_ONLY,
        ),
        (
            "KPI-003",
            "confirmed_epc_jpy",
            MetricUnit.JPY_PER_CLICK,
            MetricBasis.DIRECT_ONLY,
        ),
        (
            "KPI-004",
            "confirmed_rpm_jpy",
            MetricUnit.JPY_PER_1000_SESSIONS,
            MetricBasis.DIRECT_ONLY,
        ),
        (
            "KPI-022",
            "article_update_cost_ratio",
            MetricUnit.RATIO,
            MetricBasis.DIRECT_ONLY,
        ),
        (
            "KPI-023",
            "content_payback_months",
            MetricUnit.MONTHS,
            MetricBasis.DIRECT_ONLY,
        ),
        (
            "KPI-025",
            "ai_cost_per_approved_article_jpy",
            MetricUnit.JPY_PER_APPROVED_ARTICLE,
            MetricBasis.DIRECT_ONLY,
        ),
        (
            "SUPPLEMENTAL-CONTENT-HOUR",
            "confirmed_reward_per_content_hour_jpy",
            MetricUnit.JPY_PER_CONTENT_HOUR,
            MetricBasis.DIRECT_ONLY,
        ),
    )
    if readiness is not None:
        metrics = tuple(
            _unavailable_metric(
                metric_id=metric_id,
                name=name,
                reason=readiness,
                unit=unit,
                basis=basis,
                request=request,
            )
            for metric_id, name, unit, basis in global_metric_specs
        )
    else:
        provider_decimal = provider.value
        direct_decimal = direct.value
        metrics_list: list[UnitEconomicsMetric] = [
            _available_metric(
                metric_id="KPI-001",
                name="confirmed_provider_reward_jpy",
                value=provider_decimal.quantize(Decimal("0.01")),
                numerator=provider_decimal,
                denominator=None,
                unit=MetricUnit.JPY,
                basis=MetricBasis.PROVIDER_FACT,
                request=request,
                sources=attribution_sources,
            ),
            _available_metric(
                metric_id="SUPPLEMENTAL-DIRECT-REWARD",
                name="direct_confirmed_reward_jpy",
                value=direct_decimal.quantize(Decimal("0.01")),
                numerator=direct_decimal,
                denominator=None,
                unit=MetricUnit.JPY,
                basis=MetricBasis.DIRECT_ONLY,
                request=request,
                sources=attribution_sources,
            ),
        ]

        profit_reason: UnavailableReason | None = external.reason or labor_reason
        if profit_reason is not None or external.value is None or labor_value is None:
            metrics_list.append(
                _unavailable_metric(
                    metric_id="KPI-002-DIRECT-VIEW",
                    name="direct_confirmed_contribution_profit_jpy",
                    reason=profit_reason or UnavailableReason.MISSING_INPUT,
                    unit=MetricUnit.JPY,
                    basis=MetricBasis.DIRECT_ONLY,
                    request=request,
                )
            )
        else:
            profit = (direct_decimal - external.value - labor_value).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_EVEN
            )
            metrics_list.append(
                _available_metric(
                    metric_id="KPI-002-DIRECT-VIEW",
                    name="direct_confirmed_contribution_profit_jpy",
                    value=profit,
                    numerator=direct_decimal,
                    denominator=None,
                    unit=MetricUnit.JPY,
                    basis=MetricBasis.DIRECT_ONLY,
                    request=request,
                    sources=_combined_sources(
                        attribution_sources, external.sources, labor_sources
                    ),
                )
            )

        def ratio_metric(
            *,
            metric_id: str,
            name: str,
            numerator: Decimal,
            denominator: _Aggregate,
            unit: MetricUnit,
            multiplier: str,
            quantum: str,
            numerator_sources: tuple[Sha256Digest, ...],
        ) -> UnitEconomicsMetric:
            if denominator.reason is not None or denominator.value is None:
                return _unavailable_metric(
                    metric_id=metric_id,
                    name=name,
                    reason=denominator.reason or UnavailableReason.MISSING_INPUT,
                    unit=unit,
                    basis=MetricBasis.DIRECT_ONLY,
                    request=request,
                )
            if denominator.value == 0:
                return _unavailable_metric(
                    metric_id=metric_id,
                    name=name,
                    reason=UnavailableReason.ZERO_DENOMINATOR,
                    unit=unit,
                    basis=MetricBasis.DIRECT_ONLY,
                    request=request,
                )
            return _available_metric(
                metric_id=metric_id,
                name=name,
                value=_quantized_ratio(
                    numerator,
                    denominator.value,
                    multiplier=Decimal(multiplier),
                    quantum=quantum,
                ),
                numerator=numerator,
                denominator=denominator.value,
                unit=unit,
                basis=MetricBasis.DIRECT_ONLY,
                request=request,
                sources=_combined_sources(numerator_sources, denominator.sources),
            )

        metrics_list.extend(
            (
                ratio_metric(
                    metric_id="KPI-003",
                    name="confirmed_epc_jpy",
                    numerator=direct_decimal,
                    denominator=clicks,
                    unit=MetricUnit.JPY_PER_CLICK,
                    multiplier="1",
                    quantum="0.01",
                    numerator_sources=attribution_sources,
                ),
                ratio_metric(
                    metric_id="KPI-004",
                    name="confirmed_rpm_jpy",
                    numerator=direct_decimal,
                    denominator=sessions,
                    unit=MetricUnit.JPY_PER_1000_SESSIONS,
                    multiplier="1000",
                    quantum="0.01",
                    numerator_sources=attribution_sources,
                ),
                ratio_metric(
                    metric_id="KPI-022",
                    name="article_update_cost_ratio",
                    numerator=(
                        Decimal(0) if update_cost.value is None else update_cost.value
                    ),
                    denominator=_Aggregate(
                        direct_decimal,
                        None,
                        attribution_sources,
                    ),
                    unit=MetricUnit.RATIO,
                    multiplier="1",
                    quantum="0.000001",
                    numerator_sources=update_cost.sources,
                )
                if update_cost.reason is None and update_cost.value is not None
                else _unavailable_metric(
                    metric_id="KPI-022",
                    name="article_update_cost_ratio",
                    reason=update_cost.reason or UnavailableReason.MISSING_INPUT,
                    unit=MetricUnit.RATIO,
                    basis=MetricBasis.DIRECT_ONLY,
                    request=request,
                ),
                ratio_metric(
                    metric_id="KPI-023",
                    name="content_payback_months",
                    numerator=(
                        Decimal(0) if initial_cost.value is None else initial_cost.value
                    ),
                    denominator=trailing_contribution,
                    unit=MetricUnit.MONTHS,
                    multiplier="1",
                    quantum="0.01",
                    numerator_sources=initial_cost.sources,
                )
                if initial_cost.reason is None and initial_cost.value is not None
                else _unavailable_metric(
                    metric_id="KPI-023",
                    name="content_payback_months",
                    reason=initial_cost.reason or UnavailableReason.MISSING_INPUT,
                    unit=MetricUnit.MONTHS,
                    basis=MetricBasis.DIRECT_ONLY,
                    request=request,
                ),
                ratio_metric(
                    metric_id="KPI-025",
                    name="ai_cost_per_approved_article_jpy",
                    numerator=Decimal(0) if ai_cost.value is None else ai_cost.value,
                    denominator=approved_versions,
                    unit=MetricUnit.JPY_PER_APPROVED_ARTICLE,
                    multiplier="1",
                    quantum="0.01",
                    numerator_sources=ai_cost.sources,
                )
                if ai_cost.reason is None and ai_cost.value is not None
                else _unavailable_metric(
                    metric_id="KPI-025",
                    name="ai_cost_per_approved_article_jpy",
                    reason=ai_cost.reason or UnavailableReason.MISSING_INPUT,
                    unit=MetricUnit.JPY_PER_APPROVED_ARTICLE,
                    basis=MetricBasis.DIRECT_ONLY,
                    request=request,
                ),
                ratio_metric(
                    metric_id="SUPPLEMENTAL-CONTENT-HOUR",
                    name="confirmed_reward_per_content_hour_jpy",
                    numerator=direct_decimal,
                    denominator=work,
                    unit=MetricUnit.JPY_PER_CONTENT_HOUR,
                    multiplier="60",
                    quantum="0.01",
                    numerator_sources=attribution_sources,
                ),
            )
        )
        metrics = tuple(metrics_list)

    unavailable_count = sum(
        item.availability is MetricAvailability.UNAVAILABLE for item in metrics
    )
    availability = (
        EconomicsAvailability.AVAILABLE
        if unavailable_count == 0
        else (
            EconomicsAvailability.UNAVAILABLE
            if unavailable_count == len(metrics)
            else EconomicsAvailability.PARTIAL
        )
    )
    result_reason = (
        readiness if availability is EconomicsAvailability.UNAVAILABLE else None
    )
    result_totals = UnitEconomicsTotals(
        provider_confirmed_reward_jpy=provider,
        direct_confirmed_reward_jpy=direct,
        estimated_confirmed_reward_jpy=estimated,
        unattributed_confirmed_reward_jpy=unattributed,
        incremental_external_cost_jpy=external.value,
        human_labor_cost_jpy=labor_value,
        work_minutes=None if work.value is None else int(work.value),
        qualified_sessions=None if sessions.value is None else int(sessions.value),
    )
    preliminary = UnitEconomicsRunResult(
        result_sha256=Sha256Digest("0" * 64),
        run_id=request.run_id,
        input_sha256=request.input_sha256,
        method_version=METHOD_VERSION,
        availability=availability,
        unavailable_reason=result_reason,
        metrics=metrics,
        totals=result_totals,
        cost_provenance=request.cost_observations,
        authority=UnitEconomicsAuthority(),
    )
    result_hash = _digest(preliminary.payload(include_result_hash=False))
    return UnitEconomicsRunResult(
        result_sha256=result_hash,
        run_id=preliminary.run_id,
        input_sha256=preliminary.input_sha256,
        method_version=preliminary.method_version,
        availability=preliminary.availability,
        unavailable_reason=preliminary.unavailable_reason,
        metrics=preliminary.metrics,
        totals=preliminary.totals,
        cost_provenance=preliminary.cost_provenance,
        authority=preliminary.authority,
    )


__all__ = (
    "COST_COMPONENT_METRICS",
    "COST_METRICS",
    "METRIC_NAMES",
    "METHOD_VERSION",
    "PROFILE",
    "RECOMMENDATION_INPUTS_EXCLUDED",
    "ArticleCostObservation",
    "EconomicsAvailability",
    "MetricAvailability",
    "MetricBasis",
    "MetricUnit",
    "UnavailableReason",
    "UnitEconomicsAuthority",
    "UnitEconomicsFailure",
    "UnitEconomicsFailureCode",
    "UnitEconomicsMetric",
    "UnitEconomicsRunRequest",
    "UnitEconomicsRunResult",
    "UnitEconomicsTotals",
    "build_unit_economics",
    "fail_unit_economics",
)

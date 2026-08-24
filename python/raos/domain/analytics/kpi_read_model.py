"""Deterministic, provider-neutral KPI calculations for ST-1205.

The module only transforms caller-supplied, already-normalized observations into
an immutable in-memory read model.  It has no clock, repository, provider,
network, public projection, recommendation, or persistence capability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, DecimalException, ROUND_HALF_EVEN, localcontext
from enum import Enum
import hashlib
import json
import re
from typing import Final, NoReturn, SupportsIndex


_REDACTED = "<redacted-kpi-read-model>"
_METRIC_KEY = re.compile(r"[a-z][a-z0-9_]{2,95}\Z", re.ASCII)
_PROGRAM_ID = re.compile(r"[A-Z][A-Z0-9_]{2,95}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)

KPI_DEFINITION_VERSION: Final = "2.0.0"
KPI_CALCULATION_VERSION: Final = "2.0.0"
RAKUTEN_BLOG_PROGRAM: Final = "WORDPRESS_BLOG_RAKUTEN_AFFILIATE"
COMPLETE_RECORDED_INPUT_SHA256: Final = (
    "5dbaa406b8a94854a8666d777887c8afd8666236bf315be23ae526d92274bd92"
)


class InputSource(str, Enum):
    PROVIDER_REVENUE = "PROVIDER_REVENUE"
    FIRST_PARTY_EVENT = "FIRST_PARTY_EVENT"
    SEARCH_CONSOLE = "SEARCH_CONSOLE"
    GA4_AGGREGATE = "GA4_AGGREGATE"
    URL_INSPECTION = "URL_INSPECTION"
    EDITORIAL_QUALITY = "EDITORIAL_QUALITY"
    FRESHNESS_MONITOR = "FRESHNESS_MONITOR"
    COST_LEDGER = "COST_LEDGER"
    AI_LEDGER = "AI_LEDGER"
    JOB_LEDGER = "JOB_LEDGER"
    PUBLICATION_LEDGER = "PUBLICATION_LEDGER"
    WEB_VITALS = "WEB_VITALS"
    GATE_EVIDENCE = "GATE_EVIDENCE"


class AttributionBasis(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PROVIDER_FACT = "PROVIDER_FACT"
    DIRECT = "DIRECT"
    ESTIMATED = "ESTIMATED"
    ALL_ATTRIBUTED = "ALL_ATTRIBUTED"
    UNATTRIBUTED = "UNATTRIBUTED"


class AttributionRequirement(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PROVIDER_FACT = "PROVIDER_FACT"
    DIRECT = "DIRECT"
    UNATTRIBUTED = "UNATTRIBUTED"
    SELECTED_ATTRIBUTED = "SELECTED_ATTRIBUTED"


class CohortState(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    MATURE = "MATURE"
    IMMATURE = "IMMATURE"


class FormulaKind(str, Enum):
    IDENTITY = "IDENTITY"
    SUBTRACT = "SUBTRACT"
    RATIO = "RATIO"
    RATIO_X_1000 = "RATIO_X_1000"
    RATIO_X_60 = "RATIO_X_60"


class InputRole(str, Enum):
    VALUE = "VALUE"
    MINUEND = "MINUEND"
    SUBTRAHEND = "SUBTRAHEND"
    NUMERATOR = "NUMERATOR"
    DENOMINATOR = "DENOMINATOR"


class ResultUnit(str, Enum):
    JPY = "JPY"
    COUNT = "COUNT"
    RATIO = "RATIO"
    POSITION = "POSITION"
    MONTHS = "MONTHS"
    JPY_PER_CLICK = "JPY_PER_CLICK"
    JPY_PER_1000_SESSIONS = "JPY_PER_1000_SESSIONS"
    JPY_PER_HOUR = "JPY_PER_HOUR"


class KpiAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class UnavailableReason(str, Enum):
    MISSING_INPUT = "MISSING_INPUT"
    PERIOD_MISMATCH = "PERIOD_MISMATCH"
    PROGRAM_MISMATCH = "PROGRAM_MISMATCH"
    SOURCE_MISMATCH = "SOURCE_MISMATCH"
    UNVERIFIED_INPUT = "UNVERIFIED_INPUT"
    IMMATURE_COHORT = "IMMATURE_COHORT"
    ATTRIBUTION_BASIS_MISMATCH = "ATTRIBUTION_BASIS_MISMATCH"
    ATTRIBUTION_UNVERIFIED = "ATTRIBUTION_UNVERIFIED"
    INVALID_NUMERIC_INPUT = "INVALID_NUMERIC_INPUT"
    ZERO_DENOMINATOR = "ZERO_DENOMINATOR"


class KpiBoundaryStatus(str, Enum):
    RECORDED_FIXTURE_ONLY = "RECORDED_FIXTURE_ONLY"
    IN_MEMORY_ONLY = "IN_MEMORY_ONLY"
    DISABLED = "DISABLED"
    NOT_EXECUTED = "NOT_EXECUTED"
    NOT_USED = "NOT_USED"
    NOT_READY = "NOT_READY"


class KpiFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    DUPLICATE_INPUT = "DUPLICATE_INPUT"
    DEFINITION_INVALID = "DEFINITION_INVALID"
    NUMERIC_CALCULATION_FAILED = "NUMERIC_CALCULATION_FAILED"
    FIXTURE_BYTES_MISMATCH = "FIXTURE_BYTES_MISMATCH"
    FIXTURE_DOCUMENT_INVALID = "FIXTURE_DOCUMENT_INVALID"
    RECORDED_EXCHANGE_UNAVAILABLE = "RECORDED_EXCHANGE_UNAVAILABLE"
    RECORDED_EXCHANGE_EXHAUSTED = "RECORDED_EXCHANGE_EXHAUSTED"
    RECORDED_RESULT_MISMATCH = "RECORDED_RESULT_MISMATCH"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("KPI read-model serialization is not supported")


@dataclass(frozen=True, slots=True, repr=False)
class KpiFailure(RuntimeError):
    code: KpiFailureCode

    def __post_init__(self) -> None:
        if type(self.code) is not KpiFailureCode:
            raise TypeError("invalid KPI failure code")
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"KpiFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("KPI failure serialization is not supported")


def fail_kpi(code: KpiFailureCode = KpiFailureCode.INVALID_ARGUMENT) -> NoReturn:
    raise KpiFailure(code) from None


@dataclass(frozen=True, slots=True, repr=False)
class MeasurementPeriod(_RedactedValue):
    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        if (
            type(self.start_date) is not date
            or type(self.end_date) is not date
            or self.start_date > self.end_date
            or (self.end_date - self.start_date).days > 366
        ):
            fail_kpi()


@dataclass(frozen=True, slots=True, repr=False)
class ProgramId(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _PROGRAM_ID.fullmatch(self.value) is None:
            fail_kpi()


@dataclass(frozen=True, slots=True, repr=False)
class Sha256Digest(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _SHA256.fullmatch(self.value) is None:
            fail_kpi()

    @classmethod
    def of(cls, content: bytes) -> Sha256Digest:
        if type(content) is not bytes:
            fail_kpi()
        return cls(hashlib.sha256(content).hexdigest())


@dataclass(frozen=True, slots=True, repr=False)
class FixtureByteLength(_RedactedValue):
    value: int

    def __post_init__(self) -> None:
        if type(self.value) is not int or not 0 < self.value <= 4 * 1024 * 1024:
            fail_kpi()


@dataclass(frozen=True, slots=True, repr=False)
class MetricObservation(_RedactedValue):
    metric_key: str
    value: Decimal | None
    source: InputSource
    period: MeasurementPeriod
    program_id: ProgramId
    verified: bool
    cohort_state: CohortState
    attribution_basis: AttributionBasis
    attribution_verified: bool

    def __post_init__(self) -> None:
        if (
            type(self.metric_key) is not str
            or _METRIC_KEY.fullmatch(self.metric_key) is None
            or (self.value is not None and type(self.value) is not Decimal)
            or (
                type(self.value) is Decimal
                and (
                    not self.value.is_finite() or len(self.value.as_tuple().digits) > 38
                )
            )
            or type(self.source) is not InputSource
            or type(self.period) is not MeasurementPeriod
            or type(self.program_id) is not ProgramId
            or type(self.verified) is not bool
            or type(self.cohort_state) is not CohortState
            or type(self.attribution_basis) is not AttributionBasis
            or type(self.attribution_verified) is not bool
            or (
                self.attribution_basis is AttributionBasis.NOT_APPLICABLE
                and self.attribution_verified
            )
        ):
            fail_kpi()


@dataclass(frozen=True, slots=True, repr=False)
class KpiInputFrame(_RedactedValue):
    observations: tuple[MetricObservation, ...]

    def __post_init__(self) -> None:
        if type(self.observations) is not tuple or any(
            type(item) is not MetricObservation for item in self.observations
        ):
            fail_kpi()
        keys = tuple(item.metric_key for item in self.observations)
        if len(keys) != len(set(keys)):
            fail_kpi(KpiFailureCode.DUPLICATE_INPUT)

    @property
    def sha256(self) -> Sha256Digest:
        document = [
            {
                "attribution_basis": item.attribution_basis.value,
                "attribution_verified": item.attribution_verified,
                "cohort_state": item.cohort_state.value,
                "metric_key": item.metric_key,
                "period": {
                    "end_date": item.period.end_date.isoformat(),
                    "start_date": item.period.start_date.isoformat(),
                },
                "program_id": item.program_id.value,
                "source": item.source.value,
                "value": None if item.value is None else str(item.value),
                "verified": item.verified,
            }
            for item in sorted(
                self.observations, key=lambda candidate: candidate.metric_key
            )
        ]
        content = json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return Sha256Digest.of(content)


@dataclass(frozen=True, slots=True, repr=False)
class InputSpec(_RedactedValue):
    metric_key: str
    source: InputSource
    role: InputRole
    attribution_requirement: AttributionRequirement
    allow_negative: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.metric_key) is not str
            or _METRIC_KEY.fullmatch(self.metric_key) is None
            or type(self.source) is not InputSource
            or type(self.role) is not InputRole
            or type(self.attribution_requirement) is not AttributionRequirement
            or type(self.allow_negative) is not bool
        ):
            fail_kpi(KpiFailureCode.DEFINITION_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class KpiDefinition(_RedactedValue):
    kpi_id: str
    name: str
    canonical_formula: str
    formula_kind: FormulaKind
    inputs: tuple[InputSpec, ...]
    unit: ResultUnit
    quantize: Decimal
    time_grain: str
    cohort: str
    included_traffic: tuple[str, ...]
    excluded_traffic: tuple[str, ...]
    attribution_display: str
    owner: str
    decision_use: str
    zero_semantics: str = "VERIFIED_ZERO_IS_ZERO"
    division_by_zero: str = "UNAVAILABLE"
    rounding: str = "ROUND_HALF_EVEN"

    def __post_init__(self) -> None:
        expected_roles: tuple[InputRole, ...]
        if self.formula_kind is FormulaKind.IDENTITY:
            expected_roles = (InputRole.VALUE,)
        elif self.formula_kind is FormulaKind.SUBTRACT:
            expected_roles = (
                InputRole.MINUEND,
                InputRole.SUBTRAHEND,
                InputRole.SUBTRAHEND,
            )
        else:
            expected_roles = (InputRole.NUMERATOR, InputRole.DENOMINATOR)
        inputs_valid = type(self.inputs) is tuple and all(
            type(item) is InputSpec for item in self.inputs
        )
        actual_roles = tuple(item.role for item in self.inputs) if inputs_valid else ()
        if (
            self.kpi_id not in KPI_IDS
            or type(self.name) is not str
            or not self.name
            or type(self.canonical_formula) is not str
            or not self.canonical_formula
            or type(self.formula_kind) is not FormulaKind
            or not inputs_valid
            or actual_roles != expected_roles
            or type(self.unit) is not ResultUnit
            or type(self.quantize) is not Decimal
            or not self.quantize.is_finite()
            or self.quantize <= 0
            or any(
                type(value) is not str or not value
                for value in (
                    self.time_grain,
                    self.cohort,
                    self.attribution_display,
                    self.owner,
                    self.decision_use,
                )
            )
            or type(self.included_traffic) is not tuple
            or not self.included_traffic
            or type(self.excluded_traffic) is not tuple
            or not self.excluded_traffic
            or self.zero_semantics != "VERIFIED_ZERO_IS_ZERO"
            or self.division_by_zero != "UNAVAILABLE"
            or self.rounding != "ROUND_HALF_EVEN"
        ):
            fail_kpi(KpiFailureCode.DEFINITION_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class CalculationContext(_RedactedValue):
    period: MeasurementPeriod
    program_id: ProgramId
    selected_attribution_basis: AttributionBasis

    def __post_init__(self) -> None:
        if (
            type(self.period) is not MeasurementPeriod
            or type(self.program_id) is not ProgramId
            or self.program_id.value != RAKUTEN_BLOG_PROGRAM
            or type(self.selected_attribution_basis) is not AttributionBasis
            or self.selected_attribution_basis
            not in {
                AttributionBasis.DIRECT,
                AttributionBasis.ESTIMATED,
                AttributionBasis.ALL_ATTRIBUTED,
            }
        ):
            fail_kpi()


@dataclass(frozen=True, slots=True, repr=False)
class KpiReadModelRow(_RedactedValue):
    kpi_id: str
    name: str
    availability: KpiAvailability
    value: Decimal | None
    unit: ResultUnit
    unavailable_reason: UnavailableReason | None
    definition_version: str
    calculation_version: str
    period: MeasurementPeriod
    program_id: ProgramId
    attribution_basis: AttributionBasis
    input_keys: tuple[str, ...]
    freshness: str
    last_successful_import: str

    def __post_init__(self) -> None:
        available_shape = (
            self.availability is KpiAvailability.AVAILABLE
            and type(self.value) is Decimal
            and self.value.is_finite()
            and self.unavailable_reason is None
        )
        unavailable_shape = (
            self.availability is KpiAvailability.UNAVAILABLE
            and self.value is None
            and type(self.unavailable_reason) is UnavailableReason
        )
        if (
            self.kpi_id not in KPI_IDS
            or type(self.name) is not str
            or not self.name
            or not (available_shape or unavailable_shape)
            or type(self.unit) is not ResultUnit
            or self.definition_version != KPI_DEFINITION_VERSION
            or self.calculation_version != KPI_CALCULATION_VERSION
            or type(self.period) is not MeasurementPeriod
            or type(self.program_id) is not ProgramId
            or type(self.attribution_basis) is not AttributionBasis
            or type(self.input_keys) is not tuple
            or not self.input_keys
            or self.freshness != "RECORDED_SYNTHETIC"
            or self.last_successful_import != "RECORDED_FIXTURE_ONLY"
        ):
            fail_kpi()


@dataclass(frozen=True, slots=True, repr=False)
class LearningMetricRow(_RedactedValue):
    metric_id: str
    availability: KpiAvailability
    value: Decimal | None
    unit: ResultUnit
    unavailable_reason: UnavailableReason | None
    source_kpi_id: str | None
    recommendation_order_effect: bool

    def __post_init__(self) -> None:
        available_shape = (
            self.availability is KpiAvailability.AVAILABLE
            and type(self.value) is Decimal
            and self.value.is_finite()
            and self.unavailable_reason is None
        )
        unavailable_shape = (
            self.availability is KpiAvailability.UNAVAILABLE
            and self.value is None
            and type(self.unavailable_reason) is UnavailableReason
        )
        if (
            self.metric_id
            not in {
                "search_ctr",
                "affiliate_click_rate",
                "confirmed_reward_per_click",
                "confirmation_rate",
                "confirmed_reward_per_content_hour",
            }
            or not (available_shape or unavailable_shape)
            or type(self.unit) is not ResultUnit
            or (
                self.source_kpi_id is not None
                and (
                    type(self.source_kpi_id) is not str
                    or self.source_kpi_id not in KPI_IDS
                )
            )
            or self.recommendation_order_effect is not False
        ):
            fail_kpi()


@dataclass(frozen=True, slots=True, repr=False)
class RecordedKpiInputBatch(_RedactedValue):
    recording_id: str
    fixture_digest: Sha256Digest
    fixture_length: FixtureByteLength
    recorded_at: datetime
    context: CalculationContext
    input_frame: KpiInputFrame

    def __post_init__(self) -> None:
        if (
            self.recording_id != "complete"
            or type(self.fixture_digest) is not Sha256Digest
            or type(self.fixture_length) is not FixtureByteLength
            or type(self.recorded_at) is not datetime
            or self.recorded_at.tzinfo is not timezone.utc
            or self.recorded_at.fold != 0
            or type(self.context) is not CalculationContext
            or type(self.input_frame) is not KpiInputFrame
        ):
            fail_kpi()


@dataclass(frozen=True, slots=True, repr=False)
class KpiCalculationCommand(_RedactedValue):
    recording_id: str
    fixture_digest: Sha256Digest
    fixture_length: FixtureByteLength
    expected_input_digest: Sha256Digest
    context: CalculationContext
    definition_version: str = KPI_DEFINITION_VERSION
    calculation_version: str = KPI_CALCULATION_VERSION

    def __post_init__(self) -> None:
        if (
            self.recording_id != "complete"
            or type(self.fixture_digest) is not Sha256Digest
            or type(self.fixture_length) is not FixtureByteLength
            or type(self.expected_input_digest) is not Sha256Digest
            or self.expected_input_digest.value != COMPLETE_RECORDED_INPUT_SHA256
            or type(self.context) is not CalculationContext
            or self.definition_version != KPI_DEFINITION_VERSION
            or self.calculation_version != KPI_CALCULATION_VERSION
        ):
            fail_kpi()


@dataclass(frozen=True, slots=True, repr=False)
class KpiReadModelSnapshot(_RedactedValue):
    recording_id: str
    fixture_digest: Sha256Digest
    input_digest: Sha256Digest
    recorded_at: datetime
    context: CalculationContext
    rows: tuple[KpiReadModelRow, ...]
    learning_rows: tuple[LearningMetricRow, ...]
    execution: KpiBoundaryStatus
    read_model: KpiBoundaryStatus
    persistence: KpiBoundaryStatus
    provider: KpiBoundaryStatus
    network: KpiBoundaryStatus
    public_projection: KpiBoundaryStatus
    recommendation_input: KpiBoundaryStatus
    formal_tst_030: KpiBoundaryStatus
    decision: KpiBoundaryStatus

    def __post_init__(self) -> None:
        if (
            self.recording_id != "complete"
            or type(self.fixture_digest) is not Sha256Digest
            or type(self.input_digest) is not Sha256Digest
            or type(self.recorded_at) is not datetime
            or self.recorded_at.tzinfo is not timezone.utc
            or type(self.context) is not CalculationContext
            or type(self.rows) is not tuple
            or len(self.rows) != 30
            or any(type(row) is not KpiReadModelRow for row in self.rows)
            or tuple(row.kpi_id for row in self.rows) != KPI_IDS
            or type(self.learning_rows) is not tuple
            or len(self.learning_rows) != 5
            or any(type(row) is not LearningMetricRow for row in self.learning_rows)
            or self.execution is not KpiBoundaryStatus.RECORDED_FIXTURE_ONLY
            or self.read_model is not KpiBoundaryStatus.IN_MEMORY_ONLY
            or self.persistence is not KpiBoundaryStatus.NOT_EXECUTED
            or self.provider is not KpiBoundaryStatus.NOT_EXECUTED
            or self.network is not KpiBoundaryStatus.NOT_EXECUTED
            or self.public_projection is not KpiBoundaryStatus.NOT_EXECUTED
            or self.recommendation_input is not KpiBoundaryStatus.DISABLED
            or self.formal_tst_030 is not KpiBoundaryStatus.NOT_EXECUTED
            or self.decision is not KpiBoundaryStatus.NOT_READY
        ):
            fail_kpi()


KPI_IDS: Final = tuple(f"KPI-{number:03d}" for number in range(1, 31))


def _spec(
    metric_key: str,
    source: InputSource,
    role: InputRole,
    attribution: AttributionRequirement = AttributionRequirement.NOT_APPLICABLE,
    *,
    allow_negative: bool = False,
) -> InputSpec:
    return InputSpec(metric_key, source, role, attribution, allow_negative)


_INCLUDED: Final = ("eligible verified recorded/synthetic facts",)
_EXCLUDED: Final = (
    "bot preview admin invalid unverified missing mismatched-period mismatched-program",
)


def _definition(
    kpi_id: str,
    name: str,
    formula: str,
    kind: FormulaKind,
    inputs: tuple[InputSpec, ...],
    unit: ResultUnit,
    quantize: str,
    grain: str,
    cohort: str,
    attribution_display: str,
    owner: str,
    decision_use: str,
) -> KpiDefinition:
    return KpiDefinition(
        kpi_id=kpi_id,
        name=name,
        canonical_formula=formula,
        formula_kind=kind,
        inputs=inputs,
        unit=unit,
        quantize=Decimal(quantize),
        time_grain=grain,
        cohort=cohort,
        included_traffic=_INCLUDED,
        excluded_traffic=_EXCLUDED,
        attribution_display=attribution_display,
        owner=owner,
        decision_use=decision_use,
    )


KPI_DEFINITIONS: Final = (
    _definition(
        "KPI-001",
        "monthly_confirmed_commission_jpy",
        "sum(confirmed provider commission)",
        FormulaKind.IDENTITY,
        (
            _spec(
                "confirmed_provider_commission_jpy",
                InputSource.PROVIDER_REVENUE,
                InputRole.VALUE,
                AttributionRequirement.PROVIDER_FACT,
            ),
        ),
        ResultUnit.JPY,
        "0.01",
        "monthly",
        "provider confirmation cohort; mature only",
        "PROVIDER_FACT",
        "Finance",
        "monthly confirmed reward",
    ),
    _definition(
        "KPI-002",
        "monthly_confirmed_contribution_profit_jpy",
        "confirmed commission - variable external cost - editorial/update labor cost",
        FormulaKind.SUBTRACT,
        (
            _spec(
                "confirmed_provider_commission_jpy",
                InputSource.PROVIDER_REVENUE,
                InputRole.MINUEND,
                AttributionRequirement.PROVIDER_FACT,
            ),
            _spec(
                "variable_external_cost_jpy",
                InputSource.COST_LEDGER,
                InputRole.SUBTRAHEND,
            ),
            _spec(
                "editorial_update_labor_cost_jpy",
                InputSource.COST_LEDGER,
                InputRole.SUBTRAHEND,
            ),
        ),
        ResultUnit.JPY,
        "0.01",
        "monthly",
        "provider confirmation cohort; mature only",
        "PROVIDER_FACT costs separate",
        "Finance",
        "north-star contribution",
    ),
    _definition(
        "KPI-003",
        "confirmed_epc_jpy",
        "confirmed attributed commission / eligible affiliate clicks",
        FormulaKind.RATIO,
        (
            _spec(
                "confirmed_attributed_commission_jpy",
                InputSource.PROVIDER_REVENUE,
                InputRole.NUMERATOR,
                AttributionRequirement.SELECTED_ATTRIBUTED,
            ),
            _spec(
                "eligible_affiliate_clicks",
                InputSource.FIRST_PARTY_EVENT,
                InputRole.DENOMINATOR,
            ),
        ),
        ResultUnit.JPY_PER_CLICK,
        "0.01",
        "weekly/monthly",
        "provider confirmation cohort; mature only",
        "selected basis displayed",
        "Analytics/Finance",
        "confirmed reward per eligible click",
    ),
    _definition(
        "KPI-004",
        "confirmed_rpm_jpy",
        "confirmed attributed commission / qualified sessions * 1000",
        FormulaKind.RATIO_X_1000,
        (
            _spec(
                "confirmed_attributed_commission_jpy",
                InputSource.PROVIDER_REVENUE,
                InputRole.NUMERATOR,
                AttributionRequirement.SELECTED_ATTRIBUTED,
            ),
            _spec(
                "qualified_sessions", InputSource.GA4_AGGREGATE, InputRole.DENOMINATOR
            ),
        ),
        ResultUnit.JPY_PER_1000_SESSIONS,
        "0.01",
        "weekly/monthly",
        "provider confirmation cohort; mature only",
        "selected basis displayed",
        "Analytics/Finance",
        "confirmed reward per thousand qualified sessions",
    ),
    _definition(
        "KPI-005",
        "qualified_decision_sessions",
        "count distinct eligible sessions meeting engagement rule",
        FormulaKind.IDENTITY,
        (
            _spec(
                "qualified_decision_sessions",
                InputSource.FIRST_PARTY_EVENT,
                InputRole.VALUE,
            ),
        ),
        ResultUnit.COUNT,
        "1",
        "daily",
        "period cohort",
        "NOT_APPLICABLE",
        "Analytics",
        "qualified demand",
    ),
    _definition(
        "KPI-006",
        "affiliate_click_through_rate",
        "eligible affiliate clicks / article sessions",
        FormulaKind.RATIO,
        (
            _spec(
                "eligible_affiliate_clicks",
                InputSource.FIRST_PARTY_EVENT,
                InputRole.NUMERATOR,
            ),
            _spec(
                "article_sessions", InputSource.FIRST_PARTY_EVENT, InputRole.DENOMINATOR
            ),
        ),
        ResultUnit.RATIO,
        "0.000001",
        "daily",
        "period cohort",
        "NOT_APPLICABLE",
        "Analytics",
        "affiliate click rate",
    ),
    _definition(
        "KPI-007",
        "cta_impression_to_click_rate",
        "affiliate clicks / CTA impressions",
        FormulaKind.RATIO,
        (
            _spec(
                "affiliate_clicks", InputSource.FIRST_PARTY_EVENT, InputRole.NUMERATOR
            ),
            _spec(
                "cta_impressions", InputSource.FIRST_PARTY_EVENT, InputRole.DENOMINATOR
            ),
        ),
        ResultUnit.RATIO,
        "0.000001",
        "daily",
        "period cohort",
        "NOT_APPLICABLE",
        "Analytics",
        "CTA interaction",
    ),
    _definition(
        "KPI-008",
        "provider_confirmation_rate",
        "confirmed commission amount / generated commission amount",
        FormulaKind.RATIO,
        (
            _spec(
                "confirmed_provider_commission_jpy",
                InputSource.PROVIDER_REVENUE,
                InputRole.NUMERATOR,
                AttributionRequirement.PROVIDER_FACT,
            ),
            _spec(
                "generated_provider_commission_jpy",
                InputSource.PROVIDER_REVENUE,
                InputRole.DENOMINATOR,
                AttributionRequirement.PROVIDER_FACT,
            ),
        ),
        ResultUnit.RATIO,
        "0.000001",
        "monthly",
        "provider outcome cohort; mature only",
        "PROVIDER_FACT",
        "Finance",
        "provider confirmation rate",
    ),
    _definition(
        "KPI-009",
        "provider_cancellation_rate",
        "cancelled amount / generated amount",
        FormulaKind.RATIO,
        (
            _spec(
                "cancelled_provider_commission_jpy",
                InputSource.PROVIDER_REVENUE,
                InputRole.NUMERATOR,
                AttributionRequirement.PROVIDER_FACT,
            ),
            _spec(
                "generated_provider_commission_jpy",
                InputSource.PROVIDER_REVENUE,
                InputRole.DENOMINATOR,
                AttributionRequirement.PROVIDER_FACT,
            ),
        ),
        ResultUnit.RATIO,
        "0.000001",
        "monthly",
        "provider outcome cohort; mature only",
        "PROVIDER_FACT",
        "Finance",
        "provider cancellation rate",
    ),
    _definition(
        "KPI-010",
        "direct_attribution_share",
        "direct confirmed amount / total confirmed amount",
        FormulaKind.RATIO,
        (
            _spec(
                "direct_confirmed_commission_jpy",
                InputSource.PROVIDER_REVENUE,
                InputRole.NUMERATOR,
                AttributionRequirement.DIRECT,
            ),
            _spec(
                "confirmed_provider_commission_jpy",
                InputSource.PROVIDER_REVENUE,
                InputRole.DENOMINATOR,
                AttributionRequirement.PROVIDER_FACT,
            ),
        ),
        ResultUnit.RATIO,
        "0.000001",
        "monthly",
        "provider confirmation cohort; mature only",
        "DIRECT / PROVIDER_FACT",
        "Finance",
        "direct attribution coverage",
    ),
    _definition(
        "KPI-011",
        "unattributed_share",
        "unattributed confirmed amount / total confirmed amount",
        FormulaKind.RATIO,
        (
            _spec(
                "unattributed_confirmed_commission_jpy",
                InputSource.PROVIDER_REVENUE,
                InputRole.NUMERATOR,
                AttributionRequirement.UNATTRIBUTED,
            ),
            _spec(
                "confirmed_provider_commission_jpy",
                InputSource.PROVIDER_REVENUE,
                InputRole.DENOMINATOR,
                AttributionRequirement.PROVIDER_FACT,
            ),
        ),
        ResultUnit.RATIO,
        "0.000001",
        "monthly",
        "provider confirmation cohort; mature only",
        "UNATTRIBUTED / PROVIDER_FACT; never allocated",
        "Finance",
        "unattributed risk",
    ),
    _definition(
        "KPI-012",
        "organic_clicks",
        "Search Console clicks",
        FormulaKind.IDENTITY,
        (_spec("organic_clicks", InputSource.SEARCH_CONSOLE, InputRole.VALUE),),
        ResultUnit.COUNT,
        "1",
        "daily",
        "request dimension cohort",
        "NOT_APPLICABLE",
        "Search",
        "organic demand",
    ),
    _definition(
        "KPI-013",
        "organic_impressions",
        "Search Console impressions",
        FormulaKind.IDENTITY,
        (_spec("organic_impressions", InputSource.SEARCH_CONSOLE, InputRole.VALUE),),
        ResultUnit.COUNT,
        "1",
        "daily",
        "request dimension cohort",
        "NOT_APPLICABLE",
        "Search",
        "search visibility",
    ),
    _definition(
        "KPI-014",
        "organic_ctr",
        "Search Console clicks / impressions",
        FormulaKind.RATIO,
        (
            _spec("organic_clicks", InputSource.SEARCH_CONSOLE, InputRole.NUMERATOR),
            _spec(
                "organic_impressions", InputSource.SEARCH_CONSOLE, InputRole.DENOMINATOR
            ),
        ),
        ResultUnit.RATIO,
        "0.000001",
        "daily",
        "same request dimension cohort",
        "NOT_APPLICABLE",
        "Search",
        "search CTR",
    ),
    _definition(
        "KPI-015",
        "average_search_position",
        "Search Console weighted average position",
        FormulaKind.RATIO,
        (
            _spec(
                "search_position_weighted_sum",
                InputSource.SEARCH_CONSOLE,
                InputRole.NUMERATOR,
            ),
            _spec(
                "search_position_weight",
                InputSource.SEARCH_CONSOLE,
                InputRole.DENOMINATOR,
            ),
        ),
        ResultUnit.POSITION,
        "0.0001",
        "daily",
        "same request dimension cohort",
        "NOT_APPLICABLE",
        "Search",
        "weighted search position",
    ),
    _definition(
        "KPI-016",
        "indexed_article_rate",
        "indexed eligible articles / published eligible articles",
        FormulaKind.RATIO,
        (
            _spec(
                "indexed_eligible_articles",
                InputSource.URL_INSPECTION,
                InputRole.NUMERATOR,
            ),
            _spec(
                "published_eligible_articles",
                InputSource.URL_INSPECTION,
                InputRole.DENOMINATOR,
            ),
        ),
        ResultUnit.RATIO,
        "0.000001",
        "weekly",
        "eligible article cohort",
        "NOT_APPLICABLE",
        "Search",
        "index coverage",
    ),
    _definition(
        "KPI-017",
        "top20_article_rate",
        "articles with target query position <=20 / eligible articles",
        FormulaKind.RATIO,
        (
            _spec(
                "top20_mapped_articles", InputSource.SEARCH_CONSOLE, InputRole.NUMERATOR
            ),
            _spec(
                "eligible_mapped_articles",
                InputSource.SEARCH_CONSOLE,
                InputRole.DENOMINATOR,
            ),
        ),
        ResultUnit.RATIO,
        "0.000001",
        "weekly",
        "versioned query-mapping cohort",
        "NOT_APPLICABLE",
        "Search",
        "top-20 coverage",
    ),
    _definition(
        "KPI-018",
        "claim_evidence_coverage",
        "evidenced verifiable claims / verifiable claims",
        FormulaKind.RATIO,
        (
            _spec(
                "evidenced_verifiable_claims",
                InputSource.EDITORIAL_QUALITY,
                InputRole.NUMERATOR,
            ),
            _spec(
                "verifiable_claims",
                InputSource.EDITORIAL_QUALITY,
                InputRole.DENOMINATOR,
            ),
        ),
        ResultUnit.RATIO,
        "0.000001",
        "per release",
        "release cohort",
        "NOT_APPLICABLE",
        "Editorial Quality",
        "evidence coverage",
    ),
    _definition(
        "KPI-019",
        "critical_finding_rate",
        "versions with critical finding / evaluated versions",
        FormulaKind.RATIO,
        (
            _spec(
                "versions_with_critical_finding",
                InputSource.EDITORIAL_QUALITY,
                InputRole.NUMERATOR,
            ),
            _spec(
                "evaluated_versions",
                InputSource.EDITORIAL_QUALITY,
                InputRole.DENOMINATOR,
            ),
        ),
        ResultUnit.RATIO,
        "0.000001",
        "weekly",
        "evaluated-version cohort",
        "NOT_APPLICABLE",
        "Editorial Quality",
        "critical finding exposure",
    ),
    _definition(
        "KPI-020",
        "stale_exposure_rate",
        "sessions on snapshots with stale critical fact / article sessions",
        FormulaKind.RATIO,
        (
            _spec(
                "stale_critical_fact_sessions",
                InputSource.FRESHNESS_MONITOR,
                InputRole.NUMERATOR,
            ),
            _spec(
                "article_sessions", InputSource.FIRST_PARTY_EVENT, InputRole.DENOMINATOR
            ),
        ),
        ResultUnit.RATIO,
        "0.000001",
        "daily",
        "period cohort",
        "NOT_APPLICABLE",
        "Freshness",
        "stale exposure",
    ),
    _definition(
        "KPI-021",
        "affiliate_link_health_rate",
        "healthy eligible CTA / eligible CTA",
        FormulaKind.RATIO,
        (
            _spec(
                "healthy_eligible_cta",
                InputSource.FRESHNESS_MONITOR,
                InputRole.NUMERATOR,
            ),
            _spec("eligible_cta", InputSource.FRESHNESS_MONITOR, InputRole.DENOMINATOR),
        ),
        ResultUnit.RATIO,
        "0.000001",
        "hourly/daily",
        "eligible CTA cohort",
        "NOT_APPLICABLE",
        "Freshness",
        "link health",
    ),
    _definition(
        "KPI-022",
        "article_update_cost_ratio",
        "article update cost / confirmed article commission",
        FormulaKind.RATIO,
        (
            _spec(
                "article_update_cost_jpy", InputSource.COST_LEDGER, InputRole.NUMERATOR
            ),
            _spec(
                "confirmed_article_commission_jpy",
                InputSource.PROVIDER_REVENUE,
                InputRole.DENOMINATOR,
                AttributionRequirement.SELECTED_ATTRIBUTED,
            ),
        ),
        ResultUnit.RATIO,
        "0.000001",
        "monthly",
        "article provider-confirmation cohort; mature only",
        "selected article attribution; provider total allocation forbidden",
        "Finance",
        "article update economics",
    ),
    _definition(
        "KPI-023",
        "content_payback_months",
        "initial content cost / trailing monthly confirmed contribution",
        FormulaKind.RATIO,
        (
            _spec(
                "initial_content_cost_jpy", InputSource.COST_LEDGER, InputRole.NUMERATOR
            ),
            _spec(
                "trailing_monthly_confirmed_contribution_jpy",
                InputSource.COST_LEDGER,
                InputRole.DENOMINATOR,
                allow_negative=True,
            ),
        ),
        ResultUnit.MONTHS,
        "0.01",
        "monthly",
        "mature trailing cohort",
        "selected basis displayed in source contribution",
        "Finance",
        "content payback",
    ),
    _definition(
        "KPI-024",
        "revenue_concentration_top10",
        "top10 article confirmed commission / total",
        FormulaKind.RATIO,
        (
            _spec(
                "top10_confirmed_attributed_commission_jpy",
                InputSource.PROVIDER_REVENUE,
                InputRole.NUMERATOR,
                AttributionRequirement.SELECTED_ATTRIBUTED,
            ),
            _spec(
                "confirmed_attributed_commission_jpy",
                InputSource.PROVIDER_REVENUE,
                InputRole.DENOMINATOR,
                AttributionRequirement.SELECTED_ATTRIBUTED,
            ),
        ),
        ResultUnit.RATIO,
        "0.000001",
        "monthly",
        "provider confirmation cohort; mature only",
        "same selected attributed basis; unattributed never allocated",
        "Finance",
        "concentration risk",
    ),
    _definition(
        "KPI-025",
        "ai_cost_per_approved_article",
        "AI actual cost / approved article versions",
        FormulaKind.RATIO,
        (
            _spec("ai_actual_cost_jpy", InputSource.AI_LEDGER, InputRole.NUMERATOR),
            _spec(
                "approved_article_versions",
                InputSource.EDITORIAL_QUALITY,
                InputRole.DENOMINATOR,
            ),
        ),
        ResultUnit.JPY,
        "0.01",
        "monthly",
        "approved-version cohort",
        "NOT_APPLICABLE",
        "AI/Finance",
        "AI cost efficiency",
    ),
    _definition(
        "KPI-026",
        "human_edit_ratio",
        "human-changed tokens or AST nodes / AI proposed nodes",
        FormulaKind.RATIO,
        (
            _spec(
                "human_changed_nodes",
                InputSource.EDITORIAL_QUALITY,
                InputRole.NUMERATOR,
            ),
            _spec(
                "ai_proposed_nodes",
                InputSource.EDITORIAL_QUALITY,
                InputRole.DENOMINATOR,
            ),
        ),
        ResultUnit.RATIO,
        "0.000001",
        "per release",
        "release cohort",
        "NOT_APPLICABLE",
        "Editorial",
        "quality learning only",
    ),
    _definition(
        "KPI-027",
        "job_success_rate",
        "succeeded terminal jobs / terminal jobs",
        FormulaKind.RATIO,
        (
            _spec(
                "succeeded_terminal_jobs", InputSource.JOB_LEDGER, InputRole.NUMERATOR
            ),
            _spec("terminal_jobs", InputSource.JOB_LEDGER, InputRole.DENOMINATOR),
        ),
        ResultUnit.RATIO,
        "0.000001",
        "hourly/daily",
        "job-type cohort",
        "NOT_APPLICABLE",
        "Operations",
        "job reliability",
    ),
    _definition(
        "KPI-028",
        "publication_rollback_rate",
        "rolled back publications / publications",
        FormulaKind.RATIO,
        (
            _spec(
                "rolled_back_publications",
                InputSource.PUBLICATION_LEDGER,
                InputRole.NUMERATOR,
            ),
            _spec(
                "publications", InputSource.PUBLICATION_LEDGER, InputRole.DENOMINATOR
            ),
        ),
        ResultUnit.RATIO,
        "0.000001",
        "monthly",
        "publication cohort",
        "NOT_APPLICABLE",
        "Operations",
        "rollback frequency",
    ),
    _definition(
        "KPI-029",
        "core_web_vitals_pass_rate",
        "eligible page views meeting all CWV good thresholds",
        FormulaKind.RATIO,
        (
            _spec(
                "cwv_good_eligible_page_views",
                InputSource.WEB_VITALS,
                InputRole.NUMERATOR,
            ),
            _spec(
                "cwv_eligible_page_views", InputSource.WEB_VITALS, InputRole.DENOMINATOR
            ),
        ),
        ResultUnit.RATIO,
        "0.000001",
        "daily",
        "device-class page-view cohort",
        "NOT_APPLICABLE",
        "UX",
        "CWV quality",
    ),
    _definition(
        "KPI-030",
        "gate_readiness",
        "passed mandatory checks / mandatory checks",
        FormulaKind.RATIO,
        (
            _spec(
                "passed_mandatory_checks",
                InputSource.GATE_EVIDENCE,
                InputRole.NUMERATOR,
            ),
            _spec("mandatory_checks", InputSource.GATE_EVIDENCE, InputRole.DENOMINATOR),
        ),
        ResultUnit.RATIO,
        "0.000001",
        "on demand",
        "gate snapshot cohort",
        "NOT_APPLICABLE",
        "Governance",
        "gate readiness; never auto-approves",
    ),
)


def _unavailable(
    definition: KpiDefinition,
    context: CalculationContext,
    reason: UnavailableReason,
) -> KpiReadModelRow:
    return KpiReadModelRow(
        kpi_id=definition.kpi_id,
        name=definition.name,
        availability=KpiAvailability.UNAVAILABLE,
        value=None,
        unit=definition.unit,
        unavailable_reason=reason,
        definition_version=KPI_DEFINITION_VERSION,
        calculation_version=KPI_CALCULATION_VERSION,
        period=context.period,
        program_id=context.program_id,
        attribution_basis=_display_basis(definition, context),
        input_keys=tuple(item.metric_key for item in definition.inputs),
        freshness="RECORDED_SYNTHETIC",
        last_successful_import="RECORDED_FIXTURE_ONLY",
    )


def _basis_matches(
    requirement: AttributionRequirement,
    observed: MetricObservation,
    context: CalculationContext,
) -> bool:
    expected = {
        AttributionRequirement.NOT_APPLICABLE: AttributionBasis.NOT_APPLICABLE,
        AttributionRequirement.PROVIDER_FACT: AttributionBasis.PROVIDER_FACT,
        AttributionRequirement.DIRECT: AttributionBasis.DIRECT,
        AttributionRequirement.UNATTRIBUTED: AttributionBasis.UNATTRIBUTED,
        AttributionRequirement.SELECTED_ATTRIBUTED: context.selected_attribution_basis,
    }[requirement]
    return observed.attribution_basis is expected


def _display_basis(
    definition: KpiDefinition, context: CalculationContext
) -> AttributionBasis:
    requirements = {
        item.attribution_requirement
        for item in definition.inputs
        if item.attribution_requirement is not AttributionRequirement.NOT_APPLICABLE
    }
    if AttributionRequirement.SELECTED_ATTRIBUTED in requirements:
        return context.selected_attribution_basis
    if AttributionRequirement.DIRECT in requirements:
        return AttributionBasis.DIRECT
    if AttributionRequirement.UNATTRIBUTED in requirements:
        return AttributionBasis.UNATTRIBUTED
    if AttributionRequirement.PROVIDER_FACT in requirements:
        return AttributionBasis.PROVIDER_FACT
    return AttributionBasis.NOT_APPLICABLE


def _evaluate_definition(
    definition: KpiDefinition,
    observations: dict[str, MetricObservation],
    context: CalculationContext,
) -> KpiReadModelRow:
    selected: list[Decimal] = []
    for spec in definition.inputs:
        observed = observations.get(spec.metric_key)
        if observed is None or observed.value is None:
            return _unavailable(definition, context, UnavailableReason.MISSING_INPUT)
        if observed.period != context.period:
            return _unavailable(definition, context, UnavailableReason.PERIOD_MISMATCH)
        if observed.program_id != context.program_id:
            return _unavailable(definition, context, UnavailableReason.PROGRAM_MISMATCH)
        if observed.source is not spec.source:
            return _unavailable(definition, context, UnavailableReason.SOURCE_MISMATCH)
        if not observed.verified:
            return _unavailable(definition, context, UnavailableReason.UNVERIFIED_INPUT)
        if observed.cohort_state is CohortState.IMMATURE:
            return _unavailable(definition, context, UnavailableReason.IMMATURE_COHORT)
        if not _basis_matches(spec.attribution_requirement, observed, context):
            return _unavailable(
                definition, context, UnavailableReason.ATTRIBUTION_BASIS_MISMATCH
            )
        if (
            spec.attribution_requirement is not AttributionRequirement.NOT_APPLICABLE
            and not observed.attribution_verified
        ):
            return _unavailable(
                definition, context, UnavailableReason.ATTRIBUTION_UNVERIFIED
            )
        if not spec.allow_negative and observed.value < 0:
            return _unavailable(
                definition, context, UnavailableReason.INVALID_NUMERIC_INPUT
            )
        selected.append(observed.value)

    if definition.formula_kind not in {FormulaKind.IDENTITY, FormulaKind.SUBTRACT}:
        denominator = selected[1]
        if denominator == 0:
            return _unavailable(definition, context, UnavailableReason.ZERO_DENOMINATOR)
        if denominator < 0:
            return _unavailable(
                definition, context, UnavailableReason.INVALID_NUMERIC_INPUT
            )

    try:
        with localcontext() as decimal_context:
            decimal_context.prec = 50
            decimal_context.rounding = ROUND_HALF_EVEN
            if definition.formula_kind is FormulaKind.IDENTITY:
                raw = selected[0]
            elif definition.formula_kind is FormulaKind.SUBTRACT:
                raw = selected[0] - selected[1] - selected[2]
            elif definition.formula_kind is FormulaKind.RATIO:
                raw = selected[0] / selected[1]
            elif definition.formula_kind is FormulaKind.RATIO_X_1000:
                raw = selected[0] / selected[1] * Decimal(1000)
            else:
                raw = selected[0] / selected[1] * Decimal(60)
            value = raw.quantize(definition.quantize, rounding=ROUND_HALF_EVEN)
    except DecimalException, ValueError:
        fail_kpi(KpiFailureCode.NUMERIC_CALCULATION_FAILED)
    return KpiReadModelRow(
        kpi_id=definition.kpi_id,
        name=definition.name,
        availability=KpiAvailability.AVAILABLE,
        value=value,
        unit=definition.unit,
        unavailable_reason=None,
        definition_version=KPI_DEFINITION_VERSION,
        calculation_version=KPI_CALCULATION_VERSION,
        period=context.period,
        program_id=context.program_id,
        attribution_basis=_display_basis(definition, context),
        input_keys=tuple(item.metric_key for item in definition.inputs),
        freshness="RECORDED_SYNTHETIC",
        last_successful_import="RECORDED_FIXTURE_ONLY",
    )


def calculate_rows(
    frame: KpiInputFrame,
    context: CalculationContext,
) -> tuple[KpiReadModelRow, ...]:
    if type(frame) is not KpiInputFrame or type(context) is not CalculationContext:
        fail_kpi()
    observations = {item.metric_key: item for item in frame.observations}
    return tuple(
        _evaluate_definition(definition, observations, context)
        for definition in KPI_DEFINITIONS
    )


def calculate_learning_rows(
    rows: tuple[KpiReadModelRow, ...],
    frame: KpiInputFrame,
    context: CalculationContext,
) -> tuple[LearningMetricRow, ...]:
    if (
        type(rows) is not tuple
        or len(rows) != 30
        or any(type(row) is not KpiReadModelRow for row in rows)
        or type(frame) is not KpiInputFrame
        or type(context) is not CalculationContext
    ):
        fail_kpi()
    by_id = {row.kpi_id: row for row in rows}
    aliases = (
        ("search_ctr", "KPI-014"),
        ("affiliate_click_rate", "KPI-006"),
        ("confirmed_reward_per_click", "KPI-003"),
        ("confirmation_rate", "KPI-008"),
    )
    result = [
        LearningMetricRow(
            metric_id=metric_id,
            availability=by_id[kpi_id].availability,
            value=by_id[kpi_id].value,
            unit=by_id[kpi_id].unit,
            unavailable_reason=by_id[kpi_id].unavailable_reason,
            source_kpi_id=kpi_id,
            recommendation_order_effect=False,
        )
        for metric_id, kpi_id in aliases
    ]
    supplemental = _definition(
        "KPI-003",
        "confirmed_reward_per_content_hour",
        "confirmed attributed commission / content work minutes * 60",
        FormulaKind.RATIO_X_60,
        (
            _spec(
                "confirmed_attributed_commission_jpy",
                InputSource.PROVIDER_REVENUE,
                InputRole.NUMERATOR,
                AttributionRequirement.SELECTED_ATTRIBUTED,
            ),
            _spec(
                "content_work_minutes", InputSource.COST_LEDGER, InputRole.DENOMINATOR
            ),
        ),
        ResultUnit.JPY_PER_HOUR,
        "0.01",
        "monthly",
        "provider confirmation cohort; mature only",
        "selected basis displayed",
        "Learning",
        "improvement candidate only",
    )
    source = _evaluate_definition(
        supplemental, {item.metric_key: item for item in frame.observations}, context
    )
    result.append(
        LearningMetricRow(
            metric_id="confirmed_reward_per_content_hour",
            availability=source.availability,
            value=source.value,
            unit=source.unit,
            unavailable_reason=source.unavailable_reason,
            source_kpi_id=None,
            recommendation_order_effect=False,
        )
    )
    return tuple(result)


__all__ = [
    "AttributionBasis",
    "AttributionRequirement",
    "CalculationContext",
    "COMPLETE_RECORDED_INPUT_SHA256",
    "CohortState",
    "FixtureByteLength",
    "FormulaKind",
    "InputRole",
    "InputSource",
    "InputSpec",
    "KPI_CALCULATION_VERSION",
    "KPI_DEFINITIONS",
    "KPI_DEFINITION_VERSION",
    "KPI_IDS",
    "KpiAvailability",
    "KpiBoundaryStatus",
    "KpiCalculationCommand",
    "KpiDefinition",
    "KpiFailure",
    "KpiFailureCode",
    "KpiInputFrame",
    "KpiReadModelRow",
    "KpiReadModelSnapshot",
    "LearningMetricRow",
    "MeasurementPeriod",
    "MetricObservation",
    "ProgramId",
    "RAKUTEN_BLOG_PROGRAM",
    "RecordedKpiInputBatch",
    "ResultUnit",
    "Sha256Digest",
    "UnavailableReason",
    "calculate_learning_rows",
    "calculate_rows",
    "fail_kpi",
]

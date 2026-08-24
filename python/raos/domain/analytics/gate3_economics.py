"""Deterministic recorded/synthetic GATE-3 economics for ST-1804.

The domain evaluates a closed three-month synthetic test vector.  It cannot
attest real revenue, approve a Gate, rank products, mutate editorial state, or
perform provider/network/persistence/publication work.  Every projected Gate
criterion is therefore either ``INELIGIBLE_NON_ATTESTING`` or ``UNAVAILABLE``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, DecimalException, ROUND_HALF_EVEN, localcontext
from enum import Enum
import hashlib
import json
import re
from typing import Final, NoReturn, SupportsIndex

from raos.domain.analytics.kpi_read_model import RAKUTEN_BLOG_PROGRAM


PROGRAM: Final = RAKUTEN_BLOG_PROGRAM
FIXTURE_SCHEMA: Final = "ST1804_RECORDED_SYNTHETIC_GATE3_ECONOMICS_V1"
REPORT_SCHEMA: Final = "ST1804_GATE3_ECONOMICS_REPORT_V1"
METHOD_VERSION: Final = "RAOS_ST1804_GATE3_ECONOMICS_V1"

MONTH_METRICS: Final = (
    "qualified_article_sessions",
    "confirmation_cycles_completed",
    "article_costs_calculable",
    "provider_confirmed_reward_jpy",
    "direct_confirmed_reward_jpy",
    "estimated_confirmed_reward_jpy",
    "unattributed_confirmed_reward_jpy",
    "eligible_affiliate_clicks",
    "variable_external_cost_jpy",
    "labor_cost_jpy",
    "update_cost_jpy",
    "initial_content_cost_jpy",
    "top10_direct_confirmed_reward_jpy",
    "serious_compliance_incidents",
)

_EXPECTED_SOURCES: Final = {
    "qualified_article_sessions": "FIRST_PARTY_AGGREGATE",
    "confirmation_cycles_completed": "PROVIDER_REVENUE_CYCLE",
    "article_costs_calculable": "COST_LEDGER",
    "provider_confirmed_reward_jpy": "PROVIDER_REVENUE",
    "direct_confirmed_reward_jpy": "VERIFIED_DIRECT_ATTRIBUTION",
    "estimated_confirmed_reward_jpy": "ESTIMATED_ATTRIBUTION",
    "unattributed_confirmed_reward_jpy": "UNATTRIBUTED_PROVIDER_REWARD",
    "eligible_affiliate_clicks": "FIRST_PARTY_AGGREGATE",
    "variable_external_cost_jpy": "COST_LEDGER",
    "labor_cost_jpy": "COST_LEDGER",
    "update_cost_jpy": "COST_LEDGER",
    "initial_content_cost_jpy": "COST_LEDGER",
    "top10_direct_confirmed_reward_jpy": "VERIFIED_DIRECT_ATTRIBUTION",
    "serious_compliance_incidents": "COMPLIANCE_LEDGER",
}

FINANCE_EDITORIAL_INPUTS_FORBIDDEN: Final = (
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

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_PROGRAM = re.compile(r"[A-Z][A-Z0-9_]{2,95}\Z", re.ASCII)
_MAX_INTEGER = (1 << 63) - 1
_QUANTUM = Decimal("0.000001")
_REDACTED = "<redacted-gate3-economics>"


class Gate3FailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    FIXTURE_BYTES_MISMATCH = "FIXTURE_BYTES_MISMATCH"
    FIXTURE_DOCUMENT_INVALID = "FIXTURE_DOCUMENT_INVALID"
    RECORDED_EXCHANGE_UNAVAILABLE = "RECORDED_EXCHANGE_UNAVAILABLE"
    RECORDED_EXCHANGE_EXHAUSTED = "RECORDED_EXCHANGE_EXHAUSTED"
    RECORDED_RESULT_MISMATCH = "RECORDED_RESULT_MISMATCH"


class ValueState(str, Enum):
    NOT_OBSERVED = "NOT_OBSERVED"
    UNAVAILABLE = "UNAVAILABLE"
    UNVERIFIED = "UNVERIFIED"
    RECORDED_SYNTHETIC_ZERO = "RECORDED_SYNTHETIC_ZERO"
    RECORDED_SYNTHETIC_VALUE = "RECORDED_SYNTHETIC_VALUE"


class CohortMaturity(str, Enum):
    MATURE = "MATURE"
    IMMATURE = "IMMATURE"
    UNAVAILABLE = "UNAVAILABLE"


class MetricAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class UnavailableReason(str, Enum):
    MISSING_INPUT = "MISSING_INPUT"
    UNVERIFIED_INPUT = "UNVERIFIED_INPUT"
    COHORT_IMMATURE = "COHORT_IMMATURE"
    PERIOD_MISMATCH = "PERIOD_MISMATCH"
    PROGRAM_MISMATCH = "PROGRAM_MISMATCH"
    SOURCE_MISMATCH = "SOURCE_MISMATCH"
    ZERO_DENOMINATOR = "ZERO_DENOMINATOR"
    NONPOSITIVE_DENOMINATOR = "NONPOSITIVE_DENOMINATOR"
    ATTRIBUTION_UNVERIFIED = "ATTRIBUTION_UNVERIFIED"
    COST_UNVERIFIED = "COST_UNVERIFIED"
    REWARD_CONSERVATION_MISMATCH = "REWARD_CONSERVATION_MISMATCH"
    ARTICLE_GROUP_BASIS_UNAVAILABLE = "ARTICLE_GROUP_BASIS_UNAVAILABLE"
    HUMAN_JUDGMENT_REQUIRED = "HUMAN_JUDGMENT_REQUIRED"


class CriterionStatus(str, Enum):
    INELIGIBLE_NON_ATTESTING = "INELIGIBLE_NON_ATTESTING"
    UNAVAILABLE = "UNAVAILABLE"


class Gate3Overall(str, Enum):
    BLOCKED = "BLOCKED"


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("GATE-3 economics serialization is forbidden")


@dataclass(frozen=True, slots=True, repr=False)
class Gate3Failure(RuntimeError):
    code: Gate3FailureCode

    def __post_init__(self) -> None:
        if type(self.code) is not Gate3FailureCode:
            raise TypeError("invalid GATE-3 failure code")
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"Gate3Failure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("GATE-3 failure serialization is forbidden")


def fail_gate3(
    code: Gate3FailureCode = Gate3FailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise Gate3Failure(code) from None


@dataclass(frozen=True, slots=True, repr=False)
class Sha256Digest(_Redacted):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _SHA256.fullmatch(self.value) is None:
            fail_gate3()

    @classmethod
    def of(cls, content: bytes) -> Sha256Digest:
        if type(content) is not bytes:
            fail_gate3()
        return cls(hashlib.sha256(content).hexdigest())


@dataclass(frozen=True, slots=True, repr=False)
class FixtureByteLength(_Redacted):
    value: int

    def __post_init__(self) -> None:
        if type(self.value) is not int or not 0 < self.value <= 1024 * 1024:
            fail_gate3()


def _is_first_day(value: date) -> bool:
    return value.day == 1


def _next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


@dataclass(frozen=True, slots=True, repr=False)
class MonthPeriod(_Redacted):
    start_date: date
    end_exclusive_date: date

    def __post_init__(self) -> None:
        if (
            type(self.start_date) is not date
            or type(self.end_exclusive_date) is not date
            or not _is_first_day(self.start_date)
            or self.end_exclusive_date != _next_month(self.start_date)
        ):
            fail_gate3()

    def payload(self) -> dict[str, str]:
        return {
            "end_exclusive_date": self.end_exclusive_date.isoformat(),
            "start_date": self.start_date.isoformat(),
        }


@dataclass(frozen=True, slots=True, repr=False)
class MetricValue(_Redacted):
    metric_key: str
    state: ValueState
    value: int | None
    source: str
    source_sha256: Sha256Digest | None

    def __post_init__(self) -> None:
        if (
            self.metric_key not in _EXPECTED_SOURCES
            or type(self.state) is not ValueState
            or type(self.source) is not str
            or self.source != _EXPECTED_SOURCES[self.metric_key]
            or (
                self.source_sha256 is not None
                and type(self.source_sha256) is not Sha256Digest
            )
        ):
            fail_gate3()
        absent = self.state in {ValueState.NOT_OBSERVED, ValueState.UNAVAILABLE}
        if absent:
            if self.value is not None or self.source_sha256 is not None:
                fail_gate3()
            return
        if self.source_sha256 is None:
            fail_gate3()
        if self.state is ValueState.UNVERIFIED:
            if self.value is not None and (
                type(self.value) is not int or not 0 <= self.value <= _MAX_INTEGER
            ):
                fail_gate3()
            return
        if self.state is ValueState.RECORDED_SYNTHETIC_ZERO:
            if type(self.value) is not int or self.value != 0:
                fail_gate3()
            return
        if type(self.value) is not int or not 1 <= self.value <= _MAX_INTEGER:
            fail_gate3()

    @property
    def verified_value(self) -> int | None:
        if self.state in {
            ValueState.RECORDED_SYNTHETIC_ZERO,
            ValueState.RECORDED_SYNTHETIC_VALUE,
        }:
            return self.value
        return None

    def payload(self) -> dict[str, object]:
        return {
            "metric_key": self.metric_key,
            "source": self.source,
            "source_sha256": (
                None if self.source_sha256 is None else self.source_sha256.value
            ),
            "state": self.state.value,
            "value": self.value,
        }


def canonical_entry_digest(
    *,
    sequence: int,
    previous_entry_sha256: Sha256Digest,
    payload: dict[str, object],
) -> Sha256Digest:
    if (
        type(sequence) is not int
        or not 1 <= sequence <= 3
        or type(previous_entry_sha256) is not Sha256Digest
        or type(payload) is not dict
    ):
        fail_gate3()
    document = {
        "payload": payload,
        "previous_entry_sha256": previous_entry_sha256.value,
        "sequence": sequence,
        "type": "MONTH",
    }
    return Sha256Digest.of(
        json.dumps(
            document,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    )


@dataclass(frozen=True, slots=True, repr=False)
class MonthObservation(_Redacted):
    sequence: int
    previous_entry_sha256: Sha256Digest
    entry_sha256: Sha256Digest
    period: MonthPeriod
    program_id: str
    cohort_maturity: CohortMaturity
    attribution_verified: bool
    cost_basis_verified: bool
    metrics: tuple[MetricValue, ...]

    def __post_init__(self) -> None:
        if (
            type(self.sequence) is not int
            or not 1 <= self.sequence <= 3
            or type(self.previous_entry_sha256) is not Sha256Digest
            or type(self.entry_sha256) is not Sha256Digest
            or type(self.period) is not MonthPeriod
            or type(self.program_id) is not str
            or _PROGRAM.fullmatch(self.program_id) is None
            or type(self.cohort_maturity) is not CohortMaturity
            or type(self.attribution_verified) is not bool
            or type(self.cost_basis_verified) is not bool
            or type(self.metrics) is not tuple
            or any(type(metric) is not MetricValue for metric in self.metrics)
            or tuple(metric.metric_key for metric in self.metrics) != MONTH_METRICS
        ):
            fail_gate3()
        if self.entry_sha256 != canonical_entry_digest(
            sequence=self.sequence,
            previous_entry_sha256=self.previous_entry_sha256,
            payload=self.entry_payload(),
        ):
            fail_gate3()

    def metric(self, key: str) -> MetricValue:
        try:
            return self.metrics[MONTH_METRICS.index(key)]
        except ValueError:
            fail_gate3()

    def entry_payload(self) -> dict[str, object]:
        return {
            "attribution_verified": self.attribution_verified,
            "cohort_maturity": self.cohort_maturity.value,
            "cost_basis_verified": self.cost_basis_verified,
            "metrics": [metric.payload() for metric in self.metrics],
            "period": self.period.payload(),
            "program": self.program_id,
        }


def canonical_input_digest(months: tuple[MonthObservation, ...]) -> Sha256Digest:
    if type(months) is not tuple or any(
        type(month) is not MonthObservation for month in months
    ):
        fail_gate3()
    return Sha256Digest.of(
        json.dumps(
            {"month_entries": [month.entry_sha256.value for month in months]},
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    )


@dataclass(frozen=True, slots=True, repr=False)
class RecordedEconomicsBatch(_Redacted):
    recording_id: str
    recorded_at: str
    fixture_digest: Sha256Digest
    fixture_length: FixtureByteLength
    contract_digest: Sha256Digest
    input_digest: Sha256Digest
    context_program: str
    months: tuple[MonthObservation, ...]
    synthetic: bool
    actual_observation: bool
    append_only: bool
    immutable: bool

    def __post_init__(self) -> None:
        if (
            self.recording_id != "three-month-synthetic-threshold-vector"
            or type(self.recorded_at) is not str
            or not self.recorded_at.endswith("Z")
            or type(self.fixture_digest) is not Sha256Digest
            or type(self.fixture_length) is not FixtureByteLength
            or type(self.contract_digest) is not Sha256Digest
            or type(self.input_digest) is not Sha256Digest
            or self.context_program != PROGRAM
            or type(self.months) is not tuple
            or len(self.months) != 3
            or any(type(month) is not MonthObservation for month in self.months)
            or tuple(month.sequence for month in self.months) != (1, 2, 3)
            or self.synthetic is not True
            or self.actual_observation is not False
            or self.append_only is not True
            or self.immutable is not True
        ):
            fail_gate3()
        previous = Sha256Digest("0" * 64)
        for month in self.months:
            if month.previous_entry_sha256 != previous:
                fail_gate3()
            previous = month.entry_sha256
        if canonical_input_digest(self.months) != self.input_digest:
            fail_gate3()


@dataclass(frozen=True, slots=True, repr=False)
class Gate3Command(_Redacted):
    recording_id: str
    fixture_digest: Sha256Digest
    fixture_length: FixtureByteLength
    contract_digest: Sha256Digest
    expected_input_digest: Sha256Digest
    program_id: str

    def __post_init__(self) -> None:
        if (
            self.recording_id != "three-month-synthetic-threshold-vector"
            or type(self.fixture_digest) is not Sha256Digest
            or type(self.fixture_length) is not FixtureByteLength
            or type(self.contract_digest) is not Sha256Digest
            or type(self.expected_input_digest) is not Sha256Digest
            or self.program_id != PROGRAM
        ):
            fail_gate3()


@dataclass(frozen=True, slots=True, repr=False)
class Gate3Metric(_Redacted):
    metric_id: str
    availability: MetricAvailability
    value: Decimal | None
    unit: str
    basis: str
    input_keys: tuple[str, ...]
    unavailable_reason: UnavailableReason | None

    def __post_init__(self) -> None:
        available = (
            self.availability is MetricAvailability.AVAILABLE
            and type(self.value) is Decimal
            and self.value.is_finite()
            and self.unavailable_reason is None
        )
        unavailable = (
            self.availability is MetricAvailability.UNAVAILABLE
            and self.value is None
            and type(self.unavailable_reason) is UnavailableReason
        )
        if (
            type(self.metric_id) is not str
            or not self.metric_id
            or not (available or unavailable)
            or self.unit
            not in {
                "COUNT",
                "JPY",
                "JPY_PER_CLICK",
                "JPY_PER_1000_SESSIONS",
                "MONTHS",
                "RATIO",
            }
            or type(self.basis) is not str
            or not self.basis
            or type(self.input_keys) is not tuple
            or not self.input_keys
        ):
            fail_gate3()

    def payload(self) -> dict[str, object]:
        return {
            "availability": self.availability.value,
            "basis": self.basis,
            "input_keys": list(self.input_keys),
            "metric_id": self.metric_id,
            "unavailable_reason": (
                None
                if self.unavailable_reason is None
                else self.unavailable_reason.value
            ),
            "unit": self.unit,
            "value_decimal": None if self.value is None else format(self.value, "f"),
        }


@dataclass(frozen=True, slots=True, repr=False)
class Gate3Criterion(_Redacted):
    criterion_id: str
    description: str
    status: CriterionStatus
    metric_id: str | None
    comparison: str | None
    threshold: str | None
    would_meet_numeric_threshold: bool | None
    unavailable_reason: UnavailableReason | None

    def __post_init__(self) -> None:
        numeric = (
            self.status is CriterionStatus.INELIGIBLE_NON_ATTESTING
            and type(self.metric_id) is str
            and self.comparison in {">=", ">", "<=", "<", "=="}
            and type(self.threshold) is str
            and type(self.would_meet_numeric_threshold) is bool
            and self.unavailable_reason is None
        )
        unavailable = (
            self.status is CriterionStatus.UNAVAILABLE
            and self.would_meet_numeric_threshold is None
            and type(self.unavailable_reason) is UnavailableReason
        )
        if (
            type(self.criterion_id) is not str
            or not self.criterion_id
            or type(self.description) is not str
            or not self.description
            or not (numeric or unavailable)
        ):
            fail_gate3()

    def payload(self) -> dict[str, object]:
        return {
            "comparison": self.comparison,
            "criterion_id": self.criterion_id,
            "description": self.description,
            "metric_id": self.metric_id,
            "status": self.status.value,
            "threshold": self.threshold,
            "unavailable_reason": (
                None
                if self.unavailable_reason is None
                else self.unavailable_reason.value
            ),
            "would_meet_numeric_threshold": self.would_meet_numeric_threshold,
        }


@dataclass(frozen=True, slots=True, repr=False)
class Gate3EconomicsReport(_Redacted):
    fixture_digest: Sha256Digest
    contract_digest: Sha256Digest
    input_digest: Sha256Digest
    source_head_sha256: Sha256Digest
    metrics: tuple[Gate3Metric, ...]
    criteria: tuple[Gate3Criterion, ...]
    reward_conservation: MetricAvailability
    reward_conservation_reason: UnavailableReason | None
    recorded_at: str
    observed_periods: tuple[MonthPeriod, ...]
    observed_programs: tuple[str, ...]
    cohort_maturities: tuple[CohortMaturity, ...]
    source_bundle_sha256s: tuple[Sha256Digest | None, ...]
    evaluation_sha256: Sha256Digest = field(init=False)
    overall: Gate3Overall = Gate3Overall.BLOCKED

    def __post_init__(self) -> None:
        if (
            type(self.fixture_digest) is not Sha256Digest
            or type(self.contract_digest) is not Sha256Digest
            or type(self.input_digest) is not Sha256Digest
            or type(self.source_head_sha256) is not Sha256Digest
            or type(self.metrics) is not tuple
            or any(type(metric) is not Gate3Metric for metric in self.metrics)
            or type(self.criteria) is not tuple
            or any(type(row) is not Gate3Criterion for row in self.criteria)
            or type(self.reward_conservation) is not MetricAvailability
            or type(self.recorded_at) is not str
            or not self.recorded_at.endswith("Z")
            or type(self.observed_periods) is not tuple
            or len(self.observed_periods) != 3
            or any(type(period) is not MonthPeriod for period in self.observed_periods)
            or type(self.observed_programs) is not tuple
            or len(self.observed_programs) != 3
            or any(
                type(program) is not str or _PROGRAM.fullmatch(program) is None
                for program in self.observed_programs
            )
            or type(self.cohort_maturities) is not tuple
            or len(self.cohort_maturities) != 3
            or any(
                type(maturity) is not CohortMaturity
                for maturity in self.cohort_maturities
            )
            or type(self.source_bundle_sha256s) is not tuple
            or len(self.source_bundle_sha256s) != 3
            or any(
                digest is not None and type(digest) is not Sha256Digest
                for digest in self.source_bundle_sha256s
            )
            or self.overall is not Gate3Overall.BLOCKED
        ):
            fail_gate3()
        if self.reward_conservation is MetricAvailability.AVAILABLE:
            if self.reward_conservation_reason is not None:
                fail_gate3()
        elif type(self.reward_conservation_reason) is not UnavailableReason:
            fail_gate3()
        object.__setattr__(
            self,
            "evaluation_sha256",
            Sha256Digest.of(self.canonical_bytes(include_hash=False)),
        )

    def payload(self, *, include_hash: bool = True) -> dict[str, object]:
        metric_rows: list[dict[str, object]] = []
        for metric in self.metrics:
            row = metric.payload()
            row["evaluation_context_ref"] = "#/evaluation_context"
            metric_rows.append(row)
        context_months: list[dict[str, object]] = []
        for index, digest in enumerate(self.source_bundle_sha256s):
            context_months.append(
                {
                    "cohort_maturity": self.cohort_maturities[index].value,
                    "period": self.observed_periods[index].payload(),
                    "program": self.observed_programs[index],
                    "source_bundle_sha256": (None if digest is None else digest.value),
                }
            )
        payload: dict[str, object] = {
            "actual_observations": [],
            "authority": {
                "editorial_mutation": "NONE",
                "gate_approval": "NONE",
                "product_ranking": "NONE",
                "publication": "NONE",
                "scale": "NONE",
                "status_apply": "NONE",
            },
            "criteria": [row.payload() for row in self.criteria],
            "evidence_classification": "RECORDED_SYNTHETIC_TEST_VECTOR_NON_ATTESTING",
            "evaluation_context": {
                "freshness": "RECORDED_SYNTHETIC_STATIC_FIXTURE_NON_LIVE",
                "months": context_months,
                "recorded_at": self.recorded_at,
            },
            "finance_editorial_separation": {
                "article_html_mutation": False,
                "cta_mutation": False,
                "finance_signals_excluded_from_article_logic": list(
                    FINANCE_EDITORIAL_INPUTS_FORBIDDEN
                ),
                "product_selection_mutation": False,
                "publication_snapshot_mutation": False,
                "recommendation_order_mutation": False,
            },
            "gate_pass_claim": False,
            "input_contract_sha256": self.contract_digest.value,
            "input_sha256": self.input_digest.value,
            "method_version": METHOD_VERSION,
            "metrics": metric_rows,
            "modifications_applied": [],
            "overall": self.overall.value,
            "program": PROGRAM,
            "recorded_fixture_sha256": self.fixture_digest.value,
            "reward_basis": {
                "direct_estimated_unattributed_separate": True,
                "provider_total_is_article_attribution": False,
                "reward_conservation": self.reward_conservation.value,
                "reward_conservation_reason": (
                    None
                    if self.reward_conservation_reason is None
                    else self.reward_conservation_reason.value
                ),
                "unattributed_reward_allocated_to_articles": False,
            },
            "schema": REPORT_SCHEMA,
            "source_head_sha256": self.source_head_sha256.value,
            "synthetic": True,
        }
        if include_hash:
            payload["evaluation_sha256"] = self.evaluation_sha256.value
        return payload

    def canonical_bytes(self, *, include_hash: bool = True) -> bytes:
        return json.dumps(
            self.payload(include_hash=include_hash),
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")


def _unavailable(
    metric_id: str,
    unit: str,
    basis: str,
    keys: tuple[str, ...],
    reason: UnavailableReason,
) -> Gate3Metric:
    return Gate3Metric(
        metric_id,
        MetricAvailability.UNAVAILABLE,
        None,
        unit,
        basis,
        keys,
        reason,
    )


def _available(
    metric_id: str,
    unit: str,
    basis: str,
    keys: tuple[str, ...],
    value: Decimal,
) -> Gate3Metric:
    return Gate3Metric(
        metric_id,
        MetricAvailability.AVAILABLE,
        value,
        unit,
        basis,
        keys,
        None,
    )


def _common_reason(batch: RecordedEconomicsBatch) -> UnavailableReason | None:
    for index, month in enumerate(batch.months):
        if month.program_id != batch.context_program or month.program_id != PROGRAM:
            return UnavailableReason.PROGRAM_MISMATCH
        if month.cohort_maturity is not CohortMaturity.MATURE:
            return UnavailableReason.COHORT_IMMATURE
        if (
            index
            and batch.months[index - 1].period.end_exclusive_date
            != month.period.start_date
        ):
            return UnavailableReason.PERIOD_MISMATCH
    return None


def _metric_values(
    batch: RecordedEconomicsBatch,
    key: str,
    *,
    financial: bool = False,
    cost: bool = False,
) -> tuple[tuple[int, ...] | None, UnavailableReason | None]:
    if key not in MONTH_METRICS:
        fail_gate3()
    common = _common_reason(batch)
    if common is not None:
        return None, common
    values: list[int] = []
    for month in batch.months:
        if financial and not month.attribution_verified:
            return None, UnavailableReason.ATTRIBUTION_UNVERIFIED
        if cost and not month.cost_basis_verified:
            return None, UnavailableReason.COST_UNVERIFIED
        metric = month.metric(key)
        if metric.source != _EXPECTED_SOURCES[key]:
            return None, UnavailableReason.SOURCE_MISMATCH
        if metric.state in {ValueState.NOT_OBSERVED, ValueState.UNAVAILABLE}:
            return None, UnavailableReason.MISSING_INPUT
        if metric.state is ValueState.UNVERIFIED:
            return None, UnavailableReason.UNVERIFIED_INPUT
        assert metric.value is not None
        values.append(metric.value)
    return tuple(values), None


def _reward_conservation_reason(
    batch: RecordedEconomicsBatch,
) -> UnavailableReason | None:
    keys = (
        "provider_confirmed_reward_jpy",
        "direct_confirmed_reward_jpy",
        "estimated_confirmed_reward_jpy",
        "unattributed_confirmed_reward_jpy",
    )
    values: dict[str, tuple[int, ...]] = {}
    for key in keys:
        observed, reason = _metric_values(
            batch,
            key,
            financial=key == "direct_confirmed_reward_jpy",
        )
        if reason is not None:
            return reason
        assert observed is not None
        values[key] = observed
    for index in range(3):
        if values["provider_confirmed_reward_jpy"][index] != (
            values["direct_confirmed_reward_jpy"][index]
            + values["estimated_confirmed_reward_jpy"][index]
            + values["unattributed_confirmed_reward_jpy"][index]
        ):
            return UnavailableReason.REWARD_CONSERVATION_MISMATCH
    return None


def _sum_metric(
    batch: RecordedEconomicsBatch,
    metric_id: str,
    key: str,
    *,
    unit: str,
    basis: str,
    financial: bool = False,
    cost: bool = False,
) -> Gate3Metric:
    values, reason = _metric_values(batch, key, financial=financial, cost=cost)
    if reason is None and financial:
        reason = _reward_conservation_reason(batch)
    if reason is not None:
        return _unavailable(metric_id, unit, basis, (key,), reason)
    assert values is not None
    return _available(metric_id, unit, basis, (key,), Decimal(sum(values)))


def _ratio(
    batch: RecordedEconomicsBatch,
    metric_id: str,
    numerator_key: str,
    denominator_key: str,
    *,
    multiplier: Decimal,
    unit: str,
    basis: str,
    numerator_financial: bool = False,
    numerator_cost: bool = False,
    denominator_financial: bool = False,
    denominator_cost: bool = False,
) -> Gate3Metric:
    numerator, reason = _metric_values(
        batch,
        numerator_key,
        financial=numerator_financial,
        cost=numerator_cost,
    )
    denominator, denominator_reason = _metric_values(
        batch,
        denominator_key,
        financial=denominator_financial,
        cost=denominator_cost,
    )
    reason = reason or denominator_reason
    if reason is None and (numerator_financial or denominator_financial):
        reason = _reward_conservation_reason(batch)
    keys = (numerator_key, denominator_key)
    if reason is not None:
        return _unavailable(metric_id, unit, basis, keys, reason)
    assert numerator is not None and denominator is not None
    denominator_total = sum(denominator)
    if denominator_total == 0:
        return _unavailable(
            metric_id, unit, basis, keys, UnavailableReason.ZERO_DENOMINATOR
        )
    try:
        with localcontext() as context:
            context.prec = 50
            value = (
                Decimal(sum(numerator)) * multiplier / Decimal(denominator_total)
            ).quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)
    except DecimalException:
        fail_gate3()
    return _available(metric_id, unit, basis, keys, value)


def _profit_series(
    batch: RecordedEconomicsBatch,
    *,
    include_labor_and_update: bool,
) -> tuple[tuple[int, ...] | None, UnavailableReason | None]:
    direct, reason = _metric_values(
        batch, "direct_confirmed_reward_jpy", financial=True
    )
    external, external_reason = _metric_values(
        batch, "variable_external_cost_jpy", cost=True
    )
    reason = reason or external_reason
    if reason is None:
        reason = _reward_conservation_reason(batch)
    labor: tuple[int, ...] | None = None
    update: tuple[int, ...] | None = None
    if include_labor_and_update:
        labor, labor_reason = _metric_values(batch, "labor_cost_jpy", cost=True)
        update, update_reason = _metric_values(batch, "update_cost_jpy", cost=True)
        reason = reason or labor_reason or update_reason
    if reason is not None:
        return None, reason
    assert direct is not None and external is not None
    if include_labor_and_update:
        assert labor is not None and update is not None
        return tuple(
            direct[index] - external[index] - labor[index] - update[index]
            for index in range(3)
        ), None
    return tuple(direct[index] - external[index] for index in range(3)), None


def _profit_metric(
    batch: RecordedEconomicsBatch,
    *,
    include_labor_and_update: bool,
) -> Gate3Metric:
    metric_id = (
        "contribution_profit_ii_direct_jpy_3m"
        if include_labor_and_update
        else "contribution_profit_i_direct_jpy_3m"
    )
    keys = (
        (
            "direct_confirmed_reward_jpy",
            "variable_external_cost_jpy",
            "labor_cost_jpy",
            "update_cost_jpy",
        )
        if include_labor_and_update
        else ("direct_confirmed_reward_jpy", "variable_external_cost_jpy")
    )
    series, reason = _profit_series(
        batch, include_labor_and_update=include_labor_and_update
    )
    if reason is not None:
        return _unavailable(
            metric_id,
            "JPY",
            "VERIFIED_DIRECT_ONLY_ESTIMATED_UNATTRIBUTED_EXCLUDED",
            keys,
            reason,
        )
    assert series is not None
    return _available(
        metric_id,
        "JPY",
        "VERIFIED_DIRECT_ONLY_ESTIMATED_UNATTRIBUTED_EXCLUDED",
        keys,
        Decimal(sum(series)),
    )


def _positive_profit_i_months(batch: RecordedEconomicsBatch) -> Gate3Metric:
    series, reason = _profit_series(batch, include_labor_and_update=False)
    keys = ("direct_confirmed_reward_jpy", "variable_external_cost_jpy")
    if reason is not None:
        return _unavailable(
            "profit_i_max_consecutive_positive_months",
            "COUNT",
            "VERIFIED_DIRECT_ONLY_ESTIMATED_UNATTRIBUTED_EXCLUDED",
            keys,
            reason,
        )
    assert series is not None
    longest = 0
    current = 0
    for value in series:
        current = current + 1 if value > 0 else 0
        longest = max(longest, current)
    return _available(
        "profit_i_max_consecutive_positive_months",
        "COUNT",
        "VERIFIED_DIRECT_ONLY_ESTIMATED_UNATTRIBUTED_EXCLUDED",
        keys,
        Decimal(longest),
    )


def _payback(batch: RecordedEconomicsBatch) -> Gate3Metric:
    common = _common_reason(batch)
    return _unavailable(
        "content_payback_months_direct",
        "MONTHS",
        "VERIFIED_DIRECT_ONLY_ESTIMATED_UNATTRIBUTED_EXCLUDED",
        (
            "promising_article_group_initial_content_cost_jpy",
            "promising_article_group_trailing_monthly_contribution_jpy",
        ),
        common or UnavailableReason.ARTICLE_GROUP_BASIS_UNAVAILABLE,
    )


def _criterion(
    metric: Gate3Metric,
    criterion_id: str,
    description: str,
    comparison: str,
    threshold: Decimal,
) -> Gate3Criterion:
    if metric.availability is MetricAvailability.UNAVAILABLE:
        assert metric.unavailable_reason is not None
        return Gate3Criterion(
            criterion_id,
            description,
            CriterionStatus.UNAVAILABLE,
            metric.metric_id,
            comparison,
            format(threshold, "f"),
            None,
            metric.unavailable_reason,
        )
    assert metric.value is not None
    comparisons = {
        ">=": metric.value >= threshold,
        ">": metric.value > threshold,
        "<=": metric.value <= threshold,
        "<": metric.value < threshold,
        "==": metric.value == threshold,
    }
    try:
        would_meet = comparisons[comparison]
    except KeyError:
        fail_gate3()
    return Gate3Criterion(
        criterion_id,
        description,
        CriterionStatus.INELIGIBLE_NON_ATTESTING,
        metric.metric_id,
        comparison,
        format(threshold, "f"),
        would_meet,
        None,
    )


def _human_criterion(criterion_id: str, description: str) -> Gate3Criterion:
    return Gate3Criterion(
        criterion_id,
        description,
        CriterionStatus.UNAVAILABLE,
        None,
        None,
        None,
        None,
        UnavailableReason.HUMAN_JUDGMENT_REQUIRED,
    )


def _profit_ii_criterion(metric: Gate3Metric) -> Gate3Criterion:
    criterion_id = "G3-C05"
    description = (
        "direct-basis contribution profit II is positive over three months "
        "or has a reasonable improvement trend"
    )
    if metric.availability is MetricAvailability.UNAVAILABLE:
        return _criterion(metric, criterion_id, description, ">", Decimal("0"))
    assert metric.value is not None
    if metric.value > 0:
        return _criterion(metric, criterion_id, description, ">", Decimal("0"))
    return Gate3Criterion(
        criterion_id,
        description,
        CriterionStatus.UNAVAILABLE,
        metric.metric_id,
        ">",
        "0",
        None,
        UnavailableReason.HUMAN_JUDGMENT_REQUIRED,
    )


def _month_source_bundle_sha256(month: MonthObservation) -> Sha256Digest | None:
    observed = {
        metric.source_sha256
        for metric in month.metrics
        if metric.source_sha256 is not None
    }
    if not observed:
        return None
    if len(observed) != 1:
        fail_gate3()
    return next(iter(observed))


def build_gate3_economics_report(
    batch: RecordedEconomicsBatch,
) -> Gate3EconomicsReport:
    """Evaluate the synthetic vector without creating a Gate decision."""

    if type(batch) is not RecordedEconomicsBatch:
        fail_gate3()
    metrics = (
        _sum_metric(
            batch,
            "cumulative_qualified_article_sessions",
            "qualified_article_sessions",
            unit="COUNT",
            basis="RECORDED_SYNTHETIC_FIRST_PARTY_AGGREGATE",
        ),
        _sum_metric(
            batch,
            "confirmation_cycles_completed",
            "confirmation_cycles_completed",
            unit="COUNT",
            basis="RECORDED_SYNTHETIC_PROVIDER_CYCLE",
        ),
        _sum_metric(
            batch,
            "months_with_calculable_article_costs",
            "article_costs_calculable",
            unit="COUNT",
            basis="RECORDED_SYNTHETIC_COST_LEDGER",
            cost=True,
        ),
        _sum_metric(
            batch,
            "confirmed_provider_reward_jpy",
            "provider_confirmed_reward_jpy",
            unit="JPY",
            basis="SYNTHETIC_PROVIDER_FACT_PROGRAM_TOTAL_NOT_ARTICLE_ATTRIBUTION",
        ),
        _sum_metric(
            batch,
            "direct_confirmed_reward_jpy",
            "direct_confirmed_reward_jpy",
            unit="JPY",
            basis="VERIFIED_DIRECT_ONLY_ESTIMATED_UNATTRIBUTED_EXCLUDED",
            financial=True,
        ),
        _sum_metric(
            batch,
            "estimated_confirmed_reward_jpy",
            "estimated_confirmed_reward_jpy",
            unit="JPY",
            basis="ESTIMATED_SEPARATE_NOT_PROVIDER_FACT",
        ),
        _sum_metric(
            batch,
            "unattributed_confirmed_reward_jpy",
            "unattributed_confirmed_reward_jpy",
            unit="JPY",
            basis="UNATTRIBUTED_PROGRAM_TOTAL_NOT_ALLOCATED_TO_ARTICLES",
        ),
        _ratio(
            batch,
            "confirmed_rpm_direct_jpy",
            "direct_confirmed_reward_jpy",
            "qualified_article_sessions",
            multiplier=Decimal("1000"),
            unit="JPY_PER_1000_SESSIONS",
            basis="VERIFIED_DIRECT_ONLY_ESTIMATED_UNATTRIBUTED_EXCLUDED",
            numerator_financial=True,
        ),
        _ratio(
            batch,
            "confirmed_epc_direct_jpy",
            "direct_confirmed_reward_jpy",
            "eligible_affiliate_clicks",
            multiplier=Decimal("1"),
            unit="JPY_PER_CLICK",
            basis="VERIFIED_DIRECT_ONLY_ESTIMATED_UNATTRIBUTED_EXCLUDED",
            numerator_financial=True,
        ),
        _profit_metric(batch, include_labor_and_update=False),
        _positive_profit_i_months(batch),
        _profit_metric(batch, include_labor_and_update=True),
        _payback(batch),
        _ratio(
            batch,
            "direct_reward_concentration_top10",
            "top10_direct_confirmed_reward_jpy",
            "direct_confirmed_reward_jpy",
            multiplier=Decimal("1"),
            unit="RATIO",
            basis="VERIFIED_DIRECT_ONLY_ESTIMATED_UNATTRIBUTED_EXCLUDED",
            numerator_financial=True,
        ),
        _ratio(
            batch,
            "update_cost_ratio_direct",
            "update_cost_jpy",
            "direct_confirmed_reward_jpy",
            multiplier=Decimal("1"),
            unit="RATIO",
            basis="VERIFIED_DIRECT_ONLY_ESTIMATED_UNATTRIBUTED_EXCLUDED",
            numerator_cost=True,
            denominator_financial=True,
            denominator_cost=False,
        ),
        _sum_metric(
            batch,
            "serious_compliance_incidents",
            "serious_compliance_incidents",
            unit="COUNT",
            basis="RECORDED_SYNTHETIC_COMPLIANCE_LEDGER",
        ),
    )
    by_id = {metric.metric_id: metric for metric in metrics}
    criteria = (
        _criterion(
            by_id["cumulative_qualified_article_sessions"],
            "G3-OBS-001",
            "cumulative qualified article sessions at least 10000",
            ">=",
            Decimal("10000"),
        ),
        _criterion(
            by_id["confirmation_cycles_completed"],
            "G3-OBS-002",
            "at least two confirmation cycles completed",
            ">=",
            Decimal("2"),
        ),
        _criterion(
            by_id["months_with_calculable_article_costs"],
            "G3-OBS-003",
            "article costs calculable for all three months",
            "==",
            Decimal("3"),
        ),
        _criterion(
            by_id["confirmed_rpm_direct_jpy"],
            "G3-C01",
            "direct-basis confirmed RPM at least 500 JPY",
            ">=",
            Decimal("500"),
        ),
        _criterion(
            by_id["confirmed_epc_direct_jpy"],
            "G3-C02",
            "direct-basis confirmed EPC is positive",
            ">",
            Decimal("0"),
        ),
        _human_criterion("G3-C03", "confirmed EPC stability requires human judgment"),
        _criterion(
            by_id["profit_i_max_consecutive_positive_months"],
            "G3-C04",
            "direct-basis contribution profit I positive for two consecutive months",
            ">=",
            Decimal("2"),
        ),
        _profit_ii_criterion(by_id["contribution_profit_ii_direct_jpy_3m"]),
        _criterion(
            by_id["content_payback_months_direct"],
            "G3-C06",
            "promising article-group direct-basis content payback at most 12 months",
            "<=",
            Decimal("12"),
        ),
        _human_criterion(
            "G3-C07", "forecast error manageability requires human judgment"
        ),
        _criterion(
            by_id["direct_reward_concentration_top10"],
            "G3-C08",
            "direct-basis top-ten reward concentration below 70 percent",
            "<",
            Decimal("0.70"),
        ),
        _criterion(
            by_id["update_cost_ratio_direct"],
            "G3-C09",
            "update cost below 30 percent of direct confirmed reward",
            "<",
            Decimal("0.30"),
        ),
        _criterion(
            by_id["serious_compliance_incidents"],
            "G3-C10",
            "serious compliance incidents equal zero",
            "==",
            Decimal("0"),
        ),
    )
    conservation_reason = _reward_conservation_reason(batch)
    return Gate3EconomicsReport(
        fixture_digest=batch.fixture_digest,
        contract_digest=batch.contract_digest,
        input_digest=batch.input_digest,
        source_head_sha256=batch.months[-1].entry_sha256,
        metrics=metrics,
        criteria=criteria,
        reward_conservation=(
            MetricAvailability.AVAILABLE
            if conservation_reason is None
            else MetricAvailability.UNAVAILABLE
        ),
        reward_conservation_reason=conservation_reason,
        recorded_at=batch.recorded_at,
        observed_periods=tuple(month.period for month in batch.months),
        observed_programs=tuple(month.program_id for month in batch.months),
        cohort_maturities=tuple(month.cohort_maturity for month in batch.months),
        source_bundle_sha256s=tuple(
            _month_source_bundle_sha256(month) for month in batch.months
        ),
    )


def expected_metric_source(metric_key: str) -> str:
    try:
        return _EXPECTED_SOURCES[metric_key]
    except KeyError, TypeError:
        fail_gate3()


__all__ = [
    "CohortMaturity",
    "CriterionStatus",
    "FINANCE_EDITORIAL_INPUTS_FORBIDDEN",
    "FIXTURE_SCHEMA",
    "FixtureByteLength",
    "Gate3Command",
    "Gate3Criterion",
    "Gate3EconomicsReport",
    "Gate3Failure",
    "Gate3FailureCode",
    "Gate3Metric",
    "Gate3Overall",
    "METHOD_VERSION",
    "MONTH_METRICS",
    "MetricAvailability",
    "MetricValue",
    "MonthObservation",
    "MonthPeriod",
    "PROGRAM",
    "REPORT_SCHEMA",
    "RecordedEconomicsBatch",
    "Sha256Digest",
    "UnavailableReason",
    "ValueState",
    "build_gate3_economics_report",
    "canonical_entry_digest",
    "canonical_input_digest",
    "expected_metric_source",
    "fail_gate3",
]

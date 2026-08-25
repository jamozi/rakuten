"""Deterministic recorded/synthetic attribution domain for Canonical ST-1303.

The module implements a maximum-safe local seam.  It never claims that the
unresolved Rakuten report shape supports direct keys, and it never turns an
estimate into a provider fact.  All money is integral Decimal JPY, all splits
conserve the source amount exactly, and unavailable measurements stay
unavailable rather than becoming zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from enum import Enum
import hashlib
import json
import re
from typing import Final, NoReturn, SupportsIndex
from uuid import RFC_4122, UUID

from raos.domain.finance.provider_fact_commit import JpyAmount
from raos.domain.ops.object_intake import Sha256Digest


PROFILE: Final = "RAOS_ST1303_RECORDED_SYNTHETIC_V2"
PROGRAM: Final = "WORDPRESS_BLOG_RAKUTEN_AFFILIATE"
METHOD_VERSION: Final = "RAOS_ST1303_DIRECT_WEIGHTED_CLICKS_V1"
CONTRACT_VERSION: Final = "RAOS_ST1303_MEASUREMENT_ATTRIBUTION_CONTRACT_V2"
PERIOD_DURATION_DAYS: Final = 14
ESTIMATED_CONFIDENCE_BPS: Final = 6000
DIRECT_CONFIDENCE_BPS: Final = 10000
RECOMMENDATION_INPUTS_EXCLUDED: Final = (
    "AFFILIATE_COMMISSION_RATE",
    "CONFIRMED_REWARD",
    "UNATTRIBUTED_REWARD",
    "COMMISSION",
    "INCREMENTAL_COST",
    "EPC",
    "RPM",
    "PROFIT",
)
_MAX_VALUE: Final = (1 << 63) - 1
_MAX_CANONICAL_BYTES: Final = 4 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_ARTICLE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z", re.ASCII)
_SLUG = _ARTICLE_ID
_PROGRAM = re.compile(r"[A-Z][A-Z0-9_]{2,63}\Z", re.ASCII)
_INTENT = re.compile(r"[A-Z][A-Z0-9_]{2,63}\Z", re.ASCII)

ARTICLE_METRICS: Final = (
    "search_impressions",
    "search_clicks",
    "article_views",
    "affiliate_clicks",
    "pending_outcomes",
    "confirmed_outcomes",
    "rejected_outcomes",
    "direct_confirmed_reward_jpy",
    "work_minutes",
    "incremental_cost_jpy",
    "broken_links",
)
DERIVED_METRICS: Final = (
    "search_ctr",
    "affiliate_click_rate",
    "confirmed_reward_per_click_jpy",
    "confirmation_rate",
    "confirmed_reward_per_content_hour_jpy",
)


class AttributionFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    CONTRACT_INVALID = "CONTRACT_INVALID"
    ARTICLE_BINDING_INVALID = "ARTICLE_BINDING_INVALID"
    FACT_INVALID = "FACT_INVALID"
    FACT_DUPLICATE = "FACT_DUPLICATE"
    DIRECT_KEY_INVALID = "DIRECT_KEY_INVALID"
    FACT_MEASUREMENT_MISMATCH = "FACT_MEASUREMENT_MISMATCH"
    INPUT_HASH_MISMATCH = "INPUT_HASH_MISMATCH"
    CONSERVATION_FAILED = "CONSERVATION_FAILED"
    RESULT_MISMATCH = "RESULT_MISMATCH"
    RUN_ID_CONFLICT = "RUN_ID_CONFLICT"
    RECORDED_RUN_UNAVAILABLE = "RECORDED_RUN_UNAVAILABLE"
    LOCAL_ENVIRONMENT_REQUIRED = "LOCAL_ENVIRONMENT_REQUIRED"
    FIXTURE_INVALID = "FIXTURE_INVALID"


class AttributionFailure(RuntimeError):
    """Closed non-reflecting failure; rejected input is never retained."""

    __slots__ = ("_code",)

    def __init__(self, code: AttributionFailureCode) -> None:
        if type(code) is not AttributionFailureCode:
            raise TypeError("invalid attribution failure code") from None
        self._code = code
        super().__init__(code.value)

    @property
    def code(self) -> AttributionFailureCode:
        return self._code

    def __str__(self) -> str:
        return self._code.value

    def __repr__(self) -> str:
        return f"AttributionFailure(code={self._code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("attribution failure serialization is forbidden")


def fail_attribution(
    code: AttributionFailureCode = AttributionFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise AttributionFailure(code) from None


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-st1303>)"

    def __str__(self) -> str:
        return "<redacted-st1303>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("attribution value serialization is forbidden")


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
        fail_attribution()
    if not payload or len(payload) > _MAX_CANONICAL_BYTES:
        fail_attribution()
    return payload


def _digest(value: object) -> Sha256Digest:
    return Sha256Digest(hashlib.sha256(_canonical_bytes(value)).hexdigest())


def _sha(value: object) -> Sha256Digest:
    if type(value) is not Sha256Digest or _SHA256.fullmatch(value.value) is None:
        fail_attribution()
    return Sha256Digest(value.value)


def _uuid7(value: object) -> UUID:
    if type(value) is not UUID or value.version != 7 or value.variant != RFC_4122:
        fail_attribution()
    return value


def _utc_second(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
        or value.microsecond != 0
        or value.fold != 0
    ):
        fail_attribution()
    return value.replace(tzinfo=timezone.utc)


def _instant_text(value: datetime) -> str:
    return _utc_second(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _nonnegative(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_VALUE:
        fail_attribution()
    return value


def _program(value: object) -> str:
    if type(value) is not str or _PROGRAM.fullmatch(value) is None:
        fail_attribution()
    return value


class MeasurementValueState(str, Enum):
    NOT_OBSERVED = "NOT_OBSERVED"
    UNAVAILABLE = "UNAVAILABLE"
    UNVERIFIED = "UNVERIFIED"
    OBSERVED_ZERO = "OBSERVED_ZERO"
    OBSERVED_VALUE = "OBSERVED_VALUE"


class VerificationState(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    UNAVAILABLE = "UNAVAILABLE"


class CohortMaturity(str, Enum):
    MATURE = "MATURE"
    IMMATURE = "IMMATURE"
    UNAVAILABLE = "UNAVAILABLE"


class AttributionClass(str, Enum):
    DIRECT = "DIRECT"
    ESTIMATED = "ESTIMATED"
    UNATTRIBUTED = "UNATTRIBUTED"


class EstimationSignal(str, Enum):
    DIRECT_PROVIDER_KEY = "DIRECT_PROVIDER_KEY"
    ELIGIBLE_CLICK_WEIGHTS = "ELIGIBLE_CLICK_WEIGHTS"
    INSUFFICIENT_SIGNAL = "INSUFFICIENT_SIGNAL"


class AttributionAvailability(str, Enum):
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


class AllocationReason(str, Enum):
    DIRECT_PROVIDER_KEY_VERIFIED = "DIRECT_PROVIDER_KEY_VERIFIED"
    ESTIMATED_PROPORTIONAL_ELIGIBLE_CLICKS = "ESTIMATED_PROPORTIONAL_ELIGIBLE_CLICKS"
    UNATTRIBUTED_INSUFFICIENT_SIGNAL = "UNATTRIBUTED_INSUFFICIENT_SIGNAL"
    UNATTRIBUTED_MISSING_INPUT = "UNATTRIBUTED_MISSING_INPUT"
    UNATTRIBUTED_UNVERIFIED_INPUT = "UNATTRIBUTED_UNVERIFIED_INPUT"
    UNATTRIBUTED_ZERO_ELIGIBLE_CLICK_WEIGHT = "UNATTRIBUTED_ZERO_ELIGIBLE_CLICK_WEIGHT"
    UNATTRIBUTED_COHORT_IMMATURE = "UNATTRIBUTED_COHORT_IMMATURE"
    UNATTRIBUTED_PERIOD_MISMATCH = "UNATTRIBUTED_PERIOD_MISMATCH"
    UNATTRIBUTED_PROGRAM_MISMATCH = "UNATTRIBUTED_PROGRAM_MISMATCH"


@dataclass(frozen=True, slots=True, repr=False)
class MeasurementPeriod(_Redacted):
    start_date: date
    end_exclusive_date: date

    def __post_init__(self) -> None:
        if (
            type(self.start_date) is not date
            or type(self.end_exclusive_date) is not date
            or self.end_exclusive_date
            != self.start_date + timedelta(days=PERIOD_DURATION_DAYS)
        ):
            fail_attribution()

    def payload(self) -> dict[str, object]:
        return {
            "duration_days": PERIOD_DURATION_DAYS,
            "end_exclusive_date": self.end_exclusive_date.isoformat(),
            "start_date": self.start_date.isoformat(),
        }


@dataclass(frozen=True, slots=True, repr=False)
class ContractArticle(_Redacted):
    slot: int
    article_id: str
    slug: str
    packet_sha256: Sha256Digest
    intent_classification: str

    def __post_init__(self) -> None:
        if (
            type(self.slot) is not int
            or not 1 <= self.slot <= 5
            or type(self.article_id) is not str
            or _ARTICLE_ID.fullmatch(self.article_id) is None
            or type(self.slug) is not str
            or _SLUG.fullmatch(self.slug) is None
            or type(self.intent_classification) is not str
            or _INTENT.fullmatch(self.intent_classification) is None
        ):
            fail_attribution(AttributionFailureCode.ARTICLE_BINDING_INVALID)
        object.__setattr__(self, "packet_sha256", _sha(self.packet_sha256))

    def payload(self) -> dict[str, object]:
        return {
            "article_id": self.article_id,
            "intent_classification": self.intent_classification,
            "packet_sha256": self.packet_sha256.value,
            "slot": self.slot,
            "slug": self.slug,
        }


@dataclass(frozen=True, slots=True, repr=False)
class MeasurementAttributionContract(_Redacted):
    articles: tuple[ContractArticle, ...]
    source_contract_sha256: Sha256Digest
    program: str = PROGRAM
    schema_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            type(self.articles) is not tuple
            or len(self.articles) != 5
            or any(type(article) is not ContractArticle for article in self.articles)
            or tuple(article.slot for article in self.articles) != (1, 2, 3, 4, 5)
            or len({article.article_id for article in self.articles}) != 5
            or len({article.slug for article in self.articles}) != 5
            or self.program != PROGRAM
            or self.schema_version != CONTRACT_VERSION
        ):
            fail_attribution(AttributionFailureCode.CONTRACT_INVALID)
        object.__setattr__(
            self, "source_contract_sha256", _sha(self.source_contract_sha256)
        )

    @property
    def sha256(self) -> Sha256Digest:
        return _digest(self.payload())

    def article_for_id(self, article_id: str) -> ContractArticle | None:
        if type(article_id) is not str:
            fail_attribution()
        return next(
            (article for article in self.articles if article.article_id == article_id),
            None,
        )

    def payload(self) -> dict[str, object]:
        return {
            "articles": [article.payload() for article in self.articles],
            "period_duration_days": PERIOD_DURATION_DAYS,
            "program": self.program,
            "schema_version": self.schema_version,
            "source_contract_sha256": self.source_contract_sha256.value,
        }


@dataclass(frozen=True, slots=True, repr=False)
class MeasurementValue(_Redacted):
    state: MeasurementValueState
    value: int | None
    input_sha256: Sha256Digest | None

    def __post_init__(self) -> None:
        if type(self.state) is not MeasurementValueState:
            fail_attribution()
        if self.state in {
            MeasurementValueState.NOT_OBSERVED,
            MeasurementValueState.UNAVAILABLE,
        }:
            if self.value is not None or self.input_sha256 is not None:
                fail_attribution()
            return
        if self.input_sha256 is None:
            fail_attribution()
        object.__setattr__(self, "input_sha256", _sha(self.input_sha256))
        if self.state is MeasurementValueState.UNVERIFIED:
            if self.value is not None:
                _nonnegative(self.value)
            return
        observed = _nonnegative(self.value)
        if self.state is MeasurementValueState.OBSERVED_ZERO:
            if observed != 0:
                fail_attribution()
            return
        if self.state is not MeasurementValueState.OBSERVED_VALUE or observed == 0:
            fail_attribution()

    @property
    def observed(self) -> bool:
        return self.state in {
            MeasurementValueState.OBSERVED_ZERO,
            MeasurementValueState.OBSERVED_VALUE,
        }

    def payload(self) -> dict[str, object]:
        return {
            "input_sha256": (
                None if self.input_sha256 is None else self.input_sha256.value
            ),
            "state": self.state.value,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True, repr=False)
class MeasurementVerification(_Redacted):
    state: VerificationState
    input_sha256: Sha256Digest | None

    def __post_init__(self) -> None:
        if type(self.state) is not VerificationState:
            fail_attribution()
        if self.state is VerificationState.UNAVAILABLE:
            if self.input_sha256 is not None:
                fail_attribution()
            return
        if self.input_sha256 is None:
            fail_attribution()
        object.__setattr__(self, "input_sha256", _sha(self.input_sha256))

    def payload(self) -> dict[str, object]:
        return {
            "input_sha256": (
                None if self.input_sha256 is None else self.input_sha256.value
            ),
            "state": self.state.value,
        }


@dataclass(frozen=True, slots=True, repr=False)
class CohortStatus(_Redacted):
    state: CohortMaturity
    input_sha256: Sha256Digest | None

    def __post_init__(self) -> None:
        if type(self.state) is not CohortMaturity:
            fail_attribution()
        if self.state is CohortMaturity.UNAVAILABLE:
            if self.input_sha256 is not None:
                fail_attribution()
            return
        if self.input_sha256 is None:
            fail_attribution()
        object.__setattr__(self, "input_sha256", _sha(self.input_sha256))

    def payload(self) -> dict[str, object]:
        return {
            "input_sha256": (
                None if self.input_sha256 is None else self.input_sha256.value
            ),
            "state": self.state.value,
        }


@dataclass(frozen=True, slots=True, repr=False)
class ArticleMeasurement(_Redacted):
    article: ContractArticle
    program: str
    period: MeasurementPeriod
    verification: MeasurementVerification
    cohort: CohortStatus
    metrics: tuple[tuple[str, MeasurementValue], ...]

    def __post_init__(self) -> None:
        if (
            type(self.article) is not ContractArticle
            or type(self.period) is not MeasurementPeriod
            or type(self.verification) is not MeasurementVerification
            or type(self.cohort) is not CohortStatus
            or type(self.metrics) is not tuple
            or tuple(name for name, _value in self.metrics) != ARTICLE_METRICS
            or any(
                type(name) is not str or type(value) is not MeasurementValue
                for name, value in self.metrics
            )
        ):
            fail_attribution()
        object.__setattr__(self, "program", _program(self.program))
        metric = self.metric_map
        for numerator, denominator in (
            ("search_clicks", "search_impressions"),
            ("affiliate_clicks", "article_views"),
        ):
            left = metric[numerator]
            right = metric[denominator]
            if (
                left.observed
                and right.observed
                and left.value is not None
                and right.value is not None
                and left.value > right.value
            ):
                fail_attribution()

    @property
    def metric_map(self) -> dict[str, MeasurementValue]:
        return dict(self.metrics)

    def payload(self) -> dict[str, object]:
        return {
            "article": self.article.payload(),
            "cohort": self.cohort.payload(),
            "metrics": {name: value.payload() for name, value in self.metrics},
            "period": self.period.payload(),
            "program": self.program,
            "verification": self.verification.payload(),
        }


@dataclass(frozen=True, slots=True, repr=False)
class ProgramMeasurement(_Redacted):
    program: str
    period: MeasurementPeriod
    verification: MeasurementVerification
    cohort: CohortStatus
    unattributed_confirmed_reward_jpy: MeasurementValue

    def __post_init__(self) -> None:
        if (
            type(self.period) is not MeasurementPeriod
            or type(self.verification) is not MeasurementVerification
            or type(self.cohort) is not CohortStatus
            or type(self.unattributed_confirmed_reward_jpy) is not MeasurementValue
        ):
            fail_attribution()
        object.__setattr__(self, "program", _program(self.program))

    def payload(self) -> dict[str, object]:
        return {
            "allocation_to_articles": "FORBIDDEN",
            "cohort": self.cohort.payload(),
            "metric": self.unattributed_confirmed_reward_jpy.payload(),
            "period": self.period.payload(),
            "program": self.program,
            "verification": self.verification.payload(),
        }


@dataclass(frozen=True, slots=True, repr=False)
class ProviderRewardFact(_Redacted):
    fact_sha256: Sha256Digest
    program: str
    period: MeasurementPeriod
    confirmed_reward_jpy: JpyAmount
    verification: MeasurementVerification
    direct_article_id: str | None
    direct_key_sha256: Sha256Digest | None
    estimation_signal: EstimationSignal

    def __post_init__(self) -> None:
        if (
            type(self.period) is not MeasurementPeriod
            or type(self.confirmed_reward_jpy) is not JpyAmount
            or type(self.verification) is not MeasurementVerification
            or type(self.estimation_signal) is not EstimationSignal
        ):
            fail_attribution(AttributionFailureCode.FACT_INVALID)
        object.__setattr__(self, "fact_sha256", _sha(self.fact_sha256))
        object.__setattr__(self, "program", _program(self.program))
        if self.estimation_signal is EstimationSignal.DIRECT_PROVIDER_KEY:
            if (
                type(self.direct_article_id) is not str
                or _ARTICLE_ID.fullmatch(self.direct_article_id) is None
                or self.direct_key_sha256 is None
            ):
                fail_attribution(AttributionFailureCode.DIRECT_KEY_INVALID)
            object.__setattr__(self, "direct_key_sha256", _sha(self.direct_key_sha256))
        elif self.direct_article_id is not None or self.direct_key_sha256 is not None:
            fail_attribution(AttributionFailureCode.DIRECT_KEY_INVALID)

    def payload(self) -> dict[str, object]:
        return {
            "confirmed_reward_jpy": self.confirmed_reward_jpy.canonical_text,
            "direct_article_id": self.direct_article_id,
            "direct_key_sha256": (
                None if self.direct_key_sha256 is None else self.direct_key_sha256.value
            ),
            "estimation_signal": self.estimation_signal.value,
            "fact_sha256": self.fact_sha256.value,
            "period": self.period.payload(),
            "program": self.program,
            "verification": self.verification.payload(),
        }


@dataclass(frozen=True, slots=True, repr=False)
class AttributionRunRequest(_Redacted):
    run_id: UUID
    requested_at: datetime
    contract: MeasurementAttributionContract
    program: str
    period: MeasurementPeriod
    article_measurements: tuple[ArticleMeasurement, ...]
    program_measurement: ProgramMeasurement
    provider_facts: tuple[ProviderRewardFact, ...]
    input_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.contract) is not MeasurementAttributionContract
            or type(self.period) is not MeasurementPeriod
            or type(self.article_measurements) is not tuple
            or any(
                type(item) is not ArticleMeasurement
                for item in self.article_measurements
            )
            or type(self.program_measurement) is not ProgramMeasurement
            or type(self.provider_facts) is not tuple
            or not self.provider_facts
            or any(type(item) is not ProviderRewardFact for item in self.provider_facts)
            or len({item.fact_sha256.value for item in self.provider_facts})
            != len(self.provider_facts)
            or len(
                {
                    item.direct_key_sha256.value
                    for item in self.provider_facts
                    if item.direct_key_sha256 is not None
                }
            )
            != sum(item.direct_key_sha256 is not None for item in self.provider_facts)
        ):
            fail_attribution(AttributionFailureCode.FACT_DUPLICATE)
        object.__setattr__(self, "run_id", _uuid7(self.run_id))
        object.__setattr__(self, "requested_at", _utc_second(self.requested_at))
        object.__setattr__(self, "program", _program(self.program))
        object.__setattr__(self, "input_sha256", _digest(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "article_measurements": [
                item.payload() for item in self.article_measurements
            ],
            "contract_sha256": self.contract.sha256.value,
            "method_version": METHOD_VERSION,
            "period": self.period.payload(),
            "profile": PROFILE,
            "program": self.program,
            "program_measurement": self.program_measurement.payload(),
            "provider_facts": [item.payload() for item in self.provider_facts],
            "requested_at": _instant_text(self.requested_at),
            "run_id": str(self.run_id),
        }

    def canonical_bytes(self) -> bytes:
        payload = self._payload()
        payload["input_sha256"] = self.input_sha256.value
        return _canonical_bytes(payload)

    def has_valid_input_binding(self) -> bool:
        """Confirm that the immutable request still matches its canonical input."""

        return self.input_sha256 == _digest(self._payload())


@dataclass(frozen=True, slots=True, repr=False)
class DerivedMetric(_Redacted):
    name: str
    availability: AttributionAvailability
    unavailable_reason: UnavailableReason | None
    numerator: int | None
    denominator: int | None
    value_decimal: str | None
    unit: str

    def __post_init__(self) -> None:
        if (
            self.name not in DERIVED_METRICS
            or type(self.availability) is not AttributionAvailability
            or type(self.unit) is not str
        ):
            fail_attribution()
        if self.availability is AttributionAvailability.UNAVAILABLE:
            if (
                type(self.unavailable_reason) is not UnavailableReason
                or self.numerator is not None
                or self.denominator is not None
                or self.value_decimal is not None
            ):
                fail_attribution()
            return
        if (
            self.unavailable_reason is not None
            or type(self.numerator) is not int
            or type(self.denominator) is not int
            or self.denominator <= 0
            or type(self.value_decimal) is not str
        ):
            fail_attribution()

    def payload(self) -> dict[str, object]:
        return {
            "availability": self.availability.value,
            "basis": "VERIFIED_DIRECT_ONLY_UNATTRIBUTED_EXCLUDED",
            "denominator": self.denominator,
            "name": self.name,
            "numerator": self.numerator,
            "unavailable_reason": (
                None
                if self.unavailable_reason is None
                else self.unavailable_reason.value
            ),
            "unit": self.unit,
            "value_decimal": self.value_decimal,
        }


@dataclass(frozen=True, slots=True, repr=False)
class MeasurementEvaluation(_Redacted):
    metrics: tuple[DerivedMetric, ...]
    program_unattributed: ProgramMeasurement

    def __post_init__(self) -> None:
        if (
            type(self.metrics) is not tuple
            or tuple(item.name for item in self.metrics) != DERIVED_METRICS
            or type(self.program_unattributed) is not ProgramMeasurement
        ):
            fail_attribution()

    def payload(self) -> dict[str, object]:
        return {
            "metrics": {item.name: item.payload() for item in self.metrics},
            "program_unattributed_reward": self.program_unattributed.payload(),
        }


def _unavailable_metric(
    name: str, reason: UnavailableReason, unit: str
) -> DerivedMetric:
    return DerivedMetric(
        name=name,
        availability=AttributionAvailability.UNAVAILABLE,
        unavailable_reason=reason,
        numerator=None,
        denominator=None,
        value_decimal=None,
        unit=unit,
    )


def _ratio_metric(
    name: str, numerator: int, denominator: int, unit: str
) -> DerivedMetric:
    if denominator == 0:
        return _unavailable_metric(name, UnavailableReason.ZERO_DENOMINATOR, unit)
    with localcontext() as context:
        context.prec = 50
        result = (Decimal(numerator) / Decimal(denominator)).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_EVEN
        )
    return DerivedMetric(
        name=name,
        availability=AttributionAvailability.AVAILABLE,
        unavailable_reason=None,
        numerator=numerator,
        denominator=denominator,
        value_decimal=f"{result:.6f}",
        unit=unit,
    )


def _measurement_readiness(
    contract: MeasurementAttributionContract,
    program: str,
    period: MeasurementPeriod,
    measurements: tuple[ArticleMeasurement, ...],
) -> UnavailableReason | None:
    if (
        len(measurements) != 5
        or tuple(item.article.slot for item in measurements) != (1, 2, 3, 4, 5)
        or any(
            item.article != expected
            for item, expected in zip(measurements, contract.articles, strict=True)
        )
    ):
        return UnavailableReason.MISSING_ARTICLE_SLOTS
    if program != PROGRAM or any(item.program != program for item in measurements):
        return UnavailableReason.PROGRAM_MISMATCH
    if any(item.period != period for item in measurements):
        return UnavailableReason.PERIOD_MISMATCH
    if any(
        item.verification.state is VerificationState.UNAVAILABLE
        for item in measurements
    ):
        return UnavailableReason.MISSING_INPUT
    if any(
        item.verification.state is not VerificationState.VERIFIED
        for item in measurements
    ):
        return UnavailableReason.UNVERIFIED_INPUT
    if any(item.cohort.state is not CohortMaturity.MATURE for item in measurements):
        return UnavailableReason.COHORT_IMMATURE
    return None


def evaluate_measurements(
    *,
    contract: MeasurementAttributionContract,
    program: str,
    period: MeasurementPeriod,
    article_measurements: tuple[ArticleMeasurement, ...],
    program_measurement: ProgramMeasurement,
) -> MeasurementEvaluation:
    """Calculate only verified same-program/same-period mature metrics."""

    if (
        type(contract) is not MeasurementAttributionContract
        or type(period) is not MeasurementPeriod
        or type(article_measurements) is not tuple
        or type(program_measurement) is not ProgramMeasurement
    ):
        fail_attribution()
    readiness = _measurement_readiness(contract, program, period, article_measurements)
    if readiness is None and (
        program_measurement.program != program or program_measurement.period != period
    ):
        readiness = (
            UnavailableReason.PROGRAM_MISMATCH
            if program_measurement.program != program
            else UnavailableReason.PERIOD_MISMATCH
        )
    units = {
        "search_ctr": "RATIO",
        "affiliate_click_rate": "RATIO",
        "confirmed_reward_per_click_jpy": "JPY_PER_CLICK",
        "confirmation_rate": "RATIO",
        "confirmed_reward_per_content_hour_jpy": "JPY_PER_CONTENT_HOUR",
    }
    if readiness is not None:
        return MeasurementEvaluation(
            metrics=tuple(
                _unavailable_metric(name, readiness, units[name])
                for name in DERIVED_METRICS
            ),
            program_unattributed=program_measurement,
        )

    totals: dict[str, int] = {}
    missing: dict[str, UnavailableReason] = {}
    for metric_name in ARTICLE_METRICS:
        values = tuple(item.metric_map[metric_name] for item in article_measurements)
        if any(value.state is MeasurementValueState.UNVERIFIED for value in values):
            missing[metric_name] = UnavailableReason.UNVERIFIED_INPUT
        elif any(not value.observed for value in values):
            missing[metric_name] = UnavailableReason.MISSING_INPUT
        else:
            totals[metric_name] = sum(
                int(value.value) for value in values if value.value is not None
            )

    def metric(
        name: str,
        numerator_name: str,
        denominator_names: tuple[str, ...],
        *,
        multiplier: int = 1,
    ) -> DerivedMetric:
        for dependency in (numerator_name, *denominator_names):
            if dependency in missing:
                return _unavailable_metric(name, missing[dependency], units[name])
        return _ratio_metric(
            name,
            totals[numerator_name] * multiplier,
            sum(totals[item] for item in denominator_names),
            units[name],
        )

    if "pending_outcomes" in missing:
        confirmation = _unavailable_metric(
            "confirmation_rate", missing["pending_outcomes"], units["confirmation_rate"]
        )
    elif totals["pending_outcomes"] != 0:
        confirmation = _unavailable_metric(
            "confirmation_rate",
            UnavailableReason.COHORT_IMMATURE,
            units["confirmation_rate"],
        )
    else:
        confirmation = metric(
            "confirmation_rate",
            "confirmed_outcomes",
            ("confirmed_outcomes", "rejected_outcomes"),
        )
    derived = {
        "search_ctr": metric("search_ctr", "search_clicks", ("search_impressions",)),
        "affiliate_click_rate": metric(
            "affiliate_click_rate", "affiliate_clicks", ("article_views",)
        ),
        "confirmed_reward_per_click_jpy": metric(
            "confirmed_reward_per_click_jpy",
            "direct_confirmed_reward_jpy",
            ("affiliate_clicks",),
        ),
        "confirmation_rate": confirmation,
        "confirmed_reward_per_content_hour_jpy": metric(
            "confirmed_reward_per_content_hour_jpy",
            "direct_confirmed_reward_jpy",
            ("work_minutes",),
            multiplier=60,
        ),
    }
    return MeasurementEvaluation(
        metrics=tuple(derived[name] for name in DERIVED_METRICS),
        program_unattributed=program_measurement,
    )


def allocate_exact_jpy(
    amount: JpyAmount, weights: tuple[tuple[int, int], ...]
) -> tuple[tuple[int, JpyAmount], ...]:
    """Largest-remainder integral-JPY allocation with stable slot tie-breaking."""

    if (
        type(amount) is not JpyAmount
        or type(weights) is not tuple
        or not weights
        or any(
            type(slot) is not int
            or not 1 <= slot <= 5
            or type(weight) is not int
            or weight < 0
            for slot, weight in weights
        )
        or tuple(slot for slot, _weight in weights)
        != tuple(sorted(slot for slot, _weight in weights))
        or len({slot for slot, _weight in weights}) != len(weights)
    ):
        fail_attribution()
    denominator = sum(weight for _slot, weight in weights)
    if denominator <= 0:
        fail_attribution()
    integral_amount = int(amount.value)
    rows = [
        [
            slot,
            (integral_amount * weight) // denominator,
            (integral_amount * weight) % denominator,
        ]
        for slot, weight in weights
        if weight > 0
    ]
    remainder = integral_amount - sum(int(row[1]) for row in rows)
    order = sorted(
        range(len(rows)), key=lambda index: (-int(rows[index][2]), int(rows[index][0]))
    )
    for index in order[:remainder]:
        rows[index][1] = int(rows[index][1]) + 1
    result = tuple(
        (int(slot), JpyAmount(Decimal(int(allocated))))
        for slot, allocated, _fraction in sorted(rows, key=lambda row: int(row[0]))
    )
    if sum((value.value for _slot, value in result), Decimal(0)) != amount.value:
        fail_attribution(AttributionFailureCode.CONSERVATION_FAILED)
    return result


@dataclass(frozen=True, slots=True, repr=False)
class AttributionAllocation(_Redacted):
    allocation_sha256: Sha256Digest
    fact_sha256: Sha256Digest
    article: ContractArticle | None
    attribution_class: AttributionClass
    reason: AllocationReason
    confirmed_reward_jpy: JpyAmount
    confidence_bps: int
    weight_numerator: int | None
    weight_denominator: int | None
    method_version: str
    input_sha256: Sha256Digest

    def __post_init__(self) -> None:
        if (
            type(self.attribution_class) is not AttributionClass
            or type(self.reason) is not AllocationReason
            or type(self.confirmed_reward_jpy) is not JpyAmount
            or type(self.confidence_bps) is not int
            or not 0 <= self.confidence_bps <= 10000
            or self.method_version != METHOD_VERSION
        ):
            fail_attribution()
        object.__setattr__(self, "allocation_sha256", _sha(self.allocation_sha256))
        object.__setattr__(self, "fact_sha256", _sha(self.fact_sha256))
        object.__setattr__(self, "input_sha256", _sha(self.input_sha256))
        if self.attribution_class is AttributionClass.UNATTRIBUTED:
            if (
                self.article is not None
                or self.confidence_bps != 0
                or self.weight_numerator is not None
                or self.weight_denominator is not None
            ):
                fail_attribution()
        elif type(self.article) is not ContractArticle:
            fail_attribution()
        elif self.attribution_class is AttributionClass.DIRECT:
            if (
                self.confidence_bps != DIRECT_CONFIDENCE_BPS
                or self.weight_numerator != 1
                or self.weight_denominator != 1
            ):
                fail_attribution()
        elif (
            self.confidence_bps != ESTIMATED_CONFIDENCE_BPS
            or type(self.weight_numerator) is not int
            or type(self.weight_denominator) is not int
            or not 0 < self.weight_numerator <= self.weight_denominator
        ):
            fail_attribution()

    def payload(self) -> dict[str, object]:
        return {
            "allocation_sha256": self.allocation_sha256.value,
            "article": None if self.article is None else self.article.payload(),
            "attribution_class": self.attribution_class.value,
            "confidence_bps": self.confidence_bps,
            "confirmed_reward_jpy": self.confirmed_reward_jpy.canonical_text,
            "fact_sha256": self.fact_sha256.value,
            "input_sha256": self.input_sha256.value,
            "method_version": self.method_version,
            "reason": self.reason.value,
            "weight_denominator": self.weight_denominator,
            "weight_numerator": self.weight_numerator,
        }


@dataclass(frozen=True, slots=True, repr=False)
class AttributionTotals(_Redacted):
    provider_confirmed_reward_jpy: JpyAmount
    direct_confirmed_reward_jpy: JpyAmount
    estimated_confirmed_reward_jpy: JpyAmount
    unattributed_confirmed_reward_jpy: JpyAmount
    difference_jpy: JpyAmount

    def __post_init__(self) -> None:
        if any(
            type(value) is not JpyAmount
            for value in (
                self.provider_confirmed_reward_jpy,
                self.direct_confirmed_reward_jpy,
                self.estimated_confirmed_reward_jpy,
                self.unattributed_confirmed_reward_jpy,
                self.difference_jpy,
            )
        ):
            fail_attribution()
        allocated = (
            self.direct_confirmed_reward_jpy.value
            + self.estimated_confirmed_reward_jpy.value
            + self.unattributed_confirmed_reward_jpy.value
        )
        if (
            allocated != self.provider_confirmed_reward_jpy.value
            or self.difference_jpy.value != Decimal(0)
        ):
            fail_attribution(AttributionFailureCode.CONSERVATION_FAILED)

    def payload(self) -> dict[str, object]:
        return {
            "difference_jpy": self.difference_jpy.canonical_text,
            "direct_confirmed_reward_jpy": (
                self.direct_confirmed_reward_jpy.canonical_text
            ),
            "estimated_confirmed_reward_jpy": (
                self.estimated_confirmed_reward_jpy.canonical_text
            ),
            "provider_confirmed_reward_jpy": (
                self.provider_confirmed_reward_jpy.canonical_text
            ),
            "unattributed_confirmed_reward_jpy": (
                self.unattributed_confirmed_reward_jpy.canonical_text
            ),
        }


@dataclass(frozen=True, slots=True, repr=False)
class AttributionAuthority(_Redacted):
    provider_call: bool = False
    network: bool = False
    persistence: bool = False
    publication: bool = False
    editorial_mutation: bool = False
    article_html_mutation: bool = False
    cta_mutation: bool = False
    product_selection_mutation: bool = False
    recommendation_order_mutation: bool = False
    publication_snapshot_mutation: bool = False
    staging: bool = False
    release: bool = False
    production: bool = False

    def __post_init__(self) -> None:
        if any(getattr(self, name) is not False for name in self.__slots__):
            fail_attribution()

    def payload(self) -> dict[str, object]:
        return {name: False for name in self.__slots__}


@dataclass(frozen=True, slots=True, repr=False)
class AttributionRunResult(_Redacted):
    result_sha256: Sha256Digest
    run_id: UUID
    method_version: str
    input_sha256: Sha256Digest
    availability: AttributionAvailability
    unavailable_reason: UnavailableReason | None
    allocations: tuple[AttributionAllocation, ...]
    totals: AttributionTotals
    measurement_evaluation: MeasurementEvaluation
    authority: AttributionAuthority

    def __post_init__(self) -> None:
        if (
            self.method_version != METHOD_VERSION
            or type(self.availability) is not AttributionAvailability
            or type(self.allocations) is not tuple
            or not self.allocations
            or any(type(item) is not AttributionAllocation for item in self.allocations)
            or type(self.totals) is not AttributionTotals
            or type(self.measurement_evaluation) is not MeasurementEvaluation
            or type(self.authority) is not AttributionAuthority
        ):
            fail_attribution()
        object.__setattr__(self, "result_sha256", _sha(self.result_sha256))
        object.__setattr__(self, "run_id", _uuid7(self.run_id))
        object.__setattr__(self, "input_sha256", _sha(self.input_sha256))
        if self.availability is AttributionAvailability.AVAILABLE:
            if self.unavailable_reason is not None:
                fail_attribution()
        elif type(self.unavailable_reason) is not UnavailableReason:
            fail_attribution()

    def payload(self, *, include_result_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "allocations": [item.payload() for item in self.allocations],
            "authority": self.authority.payload(),
            "availability": self.availability.value,
            "input_sha256": self.input_sha256.value,
            "measurement_evaluation": self.measurement_evaluation.payload(),
            "method_version": self.method_version,
            "profile": PROFILE,
            "recommendation_input_policy": {
                "all_finance_values_excluded": True,
                "excluded": list(RECOMMENDATION_INPUTS_EXCLUDED),
                "finance_may_change_improvement_candidates": False,
                "finance_may_change_recommendation_order": False,
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


def _reason_for_unavailable(reason: UnavailableReason) -> AllocationReason:
    return {
        UnavailableReason.MISSING_INPUT: AllocationReason.UNATTRIBUTED_MISSING_INPUT,
        UnavailableReason.UNVERIFIED_INPUT: (
            AllocationReason.UNATTRIBUTED_UNVERIFIED_INPUT
        ),
        UnavailableReason.ZERO_DENOMINATOR: (
            AllocationReason.UNATTRIBUTED_ZERO_ELIGIBLE_CLICK_WEIGHT
        ),
        UnavailableReason.COHORT_IMMATURE: (
            AllocationReason.UNATTRIBUTED_COHORT_IMMATURE
        ),
        UnavailableReason.PERIOD_MISMATCH: (
            AllocationReason.UNATTRIBUTED_PERIOD_MISMATCH
        ),
        UnavailableReason.PROGRAM_MISMATCH: (
            AllocationReason.UNATTRIBUTED_PROGRAM_MISMATCH
        ),
        UnavailableReason.MISSING_ARTICLE_SLOTS: (
            AllocationReason.UNATTRIBUTED_MISSING_INPUT
        ),
    }[reason]


def _allocation(
    *,
    request: AttributionRunRequest,
    fact: ProviderRewardFact,
    article: ContractArticle | None,
    attribution_class: AttributionClass,
    reason: AllocationReason,
    amount: JpyAmount,
    confidence_bps: int,
    weight_numerator: int | None,
    weight_denominator: int | None,
) -> AttributionAllocation:
    core = {
        "article_id": None if article is None else article.article_id,
        "attribution_class": attribution_class.value,
        "confidence_bps": confidence_bps,
        "confirmed_reward_jpy": amount.canonical_text,
        "fact_sha256": fact.fact_sha256.value,
        "input_sha256": request.input_sha256.value,
        "method_version": METHOD_VERSION,
        "reason": reason.value,
        "weight_denominator": weight_denominator,
        "weight_numerator": weight_numerator,
    }
    return AttributionAllocation(
        allocation_sha256=_digest(core),
        fact_sha256=fact.fact_sha256,
        article=article,
        attribution_class=attribution_class,
        reason=reason,
        confirmed_reward_jpy=amount,
        confidence_bps=confidence_bps,
        weight_numerator=weight_numerator,
        weight_denominator=weight_denominator,
        method_version=METHOD_VERSION,
        input_sha256=request.input_sha256,
    )


def _input_readiness(request: AttributionRunRequest) -> UnavailableReason | None:
    readiness = _measurement_readiness(
        request.contract,
        request.program,
        request.period,
        request.article_measurements,
    )
    if readiness is not None:
        return readiness
    if request.program_measurement.program != request.program or any(
        fact.program != request.program for fact in request.provider_facts
    ):
        return UnavailableReason.PROGRAM_MISMATCH
    if request.program_measurement.period != request.period or any(
        fact.period != request.period for fact in request.provider_facts
    ):
        return UnavailableReason.PERIOD_MISMATCH
    if any(
        fact.verification.state is VerificationState.UNAVAILABLE
        for fact in request.provider_facts
    ):
        return UnavailableReason.MISSING_INPUT
    if any(
        fact.verification.state is not VerificationState.VERIFIED
        for fact in request.provider_facts
    ):
        return UnavailableReason.UNVERIFIED_INPUT
    required_article_values = tuple(
        measurement.metric_map[name]
        for measurement in request.article_measurements
        for name in ("affiliate_clicks", "direct_confirmed_reward_jpy")
    )
    if any(
        value.state
        in {
            MeasurementValueState.NOT_OBSERVED,
            MeasurementValueState.UNAVAILABLE,
        }
        for value in required_article_values
    ):
        return UnavailableReason.MISSING_INPUT
    if any(
        value.state is MeasurementValueState.UNVERIFIED
        for value in required_article_values
    ):
        return UnavailableReason.UNVERIFIED_INPUT
    program_reward = request.program_measurement.unattributed_confirmed_reward_jpy
    if (
        request.program_measurement.verification.state is VerificationState.UNAVAILABLE
        or request.program_measurement.cohort.state is CohortMaturity.UNAVAILABLE
        or program_reward.state
        in {
            MeasurementValueState.NOT_OBSERVED,
            MeasurementValueState.UNAVAILABLE,
        }
    ):
        return UnavailableReason.MISSING_INPUT
    if (
        request.program_measurement.verification.state is not VerificationState.VERIFIED
        or program_reward.state is MeasurementValueState.UNVERIFIED
    ):
        return UnavailableReason.UNVERIFIED_INPUT
    if request.program_measurement.cohort.state is not CohortMaturity.MATURE:
        return UnavailableReason.COHORT_IMMATURE
    return None


def _validate_fact_measurement_consistency(request: AttributionRunRequest) -> None:
    direct_observed = sum(
        (
            Decimal(measurement.metric_map["direct_confirmed_reward_jpy"].value or 0)
            for measurement in request.article_measurements
        ),
        Decimal(0),
    )
    direct_facts = sum(
        (
            fact.confirmed_reward_jpy.value
            for fact in request.provider_facts
            if fact.estimation_signal is EstimationSignal.DIRECT_PROVIDER_KEY
        ),
        Decimal(0),
    )
    unattributed_observed = Decimal(
        request.program_measurement.unattributed_confirmed_reward_jpy.value or 0
    )
    unattributed_facts = sum(
        (
            fact.confirmed_reward_jpy.value
            for fact in request.provider_facts
            if fact.estimation_signal is EstimationSignal.INSUFFICIENT_SIGNAL
        ),
        Decimal(0),
    )
    if direct_observed != direct_facts or unattributed_observed != unattributed_facts:
        fail_attribution(AttributionFailureCode.FACT_MEASUREMENT_MISMATCH)


def build_attribution_run(request: AttributionRunRequest) -> AttributionRunResult:
    """Run the pure deterministic Direct/Estimated/Unattributed method."""

    if type(request) is not AttributionRunRequest:
        fail_attribution()
    if not request.has_valid_input_binding():
        fail_attribution(AttributionFailureCode.INPUT_HASH_MISMATCH)
    evaluation = evaluate_measurements(
        contract=request.contract,
        program=request.program,
        period=request.period,
        article_measurements=request.article_measurements,
        program_measurement=request.program_measurement,
    )
    readiness = _input_readiness(request)
    if readiness is None:
        _validate_fact_measurement_consistency(request)
    clicks = tuple(
        (
            measurement.article.slot,
            measurement.metric_map["affiliate_clicks"],
        )
        for measurement in request.article_measurements
    )
    click_weights = tuple(
        (slot, int(value.value))
        for slot, value in clicks
        if value.observed and value.value is not None
    )
    click_total = sum(weight for _slot, weight in click_weights)
    attribution_readiness = readiness
    if (
        attribution_readiness is None
        and click_total == 0
        and any(
            fact.estimation_signal is EstimationSignal.ELIGIBLE_CLICK_WEIGHTS
            for fact in request.provider_facts
        )
    ):
        attribution_readiness = UnavailableReason.ZERO_DENOMINATOR
    allocations: list[AttributionAllocation] = []
    for fact in request.provider_facts:
        if readiness is not None:
            allocations.append(
                _allocation(
                    request=request,
                    fact=fact,
                    article=None,
                    attribution_class=AttributionClass.UNATTRIBUTED,
                    reason=_reason_for_unavailable(readiness),
                    amount=fact.confirmed_reward_jpy,
                    confidence_bps=0,
                    weight_numerator=None,
                    weight_denominator=None,
                )
            )
            continue
        if fact.estimation_signal is EstimationSignal.DIRECT_PROVIDER_KEY:
            article = request.contract.article_for_id(fact.direct_article_id or "")
            if article is None:
                fail_attribution(AttributionFailureCode.DIRECT_KEY_INVALID)
            allocations.append(
                _allocation(
                    request=request,
                    fact=fact,
                    article=article,
                    attribution_class=AttributionClass.DIRECT,
                    reason=AllocationReason.DIRECT_PROVIDER_KEY_VERIFIED,
                    amount=fact.confirmed_reward_jpy,
                    confidence_bps=DIRECT_CONFIDENCE_BPS,
                    weight_numerator=1,
                    weight_denominator=1,
                )
            )
            continue
        if fact.estimation_signal is EstimationSignal.INSUFFICIENT_SIGNAL:
            allocations.append(
                _allocation(
                    request=request,
                    fact=fact,
                    article=None,
                    attribution_class=AttributionClass.UNATTRIBUTED,
                    reason=AllocationReason.UNATTRIBUTED_INSUFFICIENT_SIGNAL,
                    amount=fact.confirmed_reward_jpy,
                    confidence_bps=0,
                    weight_numerator=None,
                    weight_denominator=None,
                )
            )
            continue
        if click_total == 0:
            allocations.append(
                _allocation(
                    request=request,
                    fact=fact,
                    article=None,
                    attribution_class=AttributionClass.UNATTRIBUTED,
                    reason=AllocationReason.UNATTRIBUTED_ZERO_ELIGIBLE_CLICK_WEIGHT,
                    amount=fact.confirmed_reward_jpy,
                    confidence_bps=0,
                    weight_numerator=None,
                    weight_denominator=None,
                )
            )
            continue
        for slot, allocated in allocate_exact_jpy(
            fact.confirmed_reward_jpy, click_weights
        ):
            weight = dict(click_weights)[slot]
            allocations.append(
                _allocation(
                    request=request,
                    fact=fact,
                    article=request.contract.articles[slot - 1],
                    attribution_class=AttributionClass.ESTIMATED,
                    reason=(AllocationReason.ESTIMATED_PROPORTIONAL_ELIGIBLE_CLICKS),
                    amount=allocated,
                    confidence_bps=ESTIMATED_CONFIDENCE_BPS,
                    weight_numerator=weight,
                    weight_denominator=click_total,
                )
            )
    provider = sum(
        (fact.confirmed_reward_jpy.value for fact in request.provider_facts),
        Decimal(0),
    )
    class_totals = {
        kind: sum(
            (
                allocation.confirmed_reward_jpy.value
                for allocation in allocations
                if allocation.attribution_class is kind
            ),
            Decimal(0),
        )
        for kind in AttributionClass
    }
    totals = AttributionTotals(
        provider_confirmed_reward_jpy=JpyAmount(provider),
        direct_confirmed_reward_jpy=JpyAmount(class_totals[AttributionClass.DIRECT]),
        estimated_confirmed_reward_jpy=JpyAmount(
            class_totals[AttributionClass.ESTIMATED]
        ),
        unattributed_confirmed_reward_jpy=JpyAmount(
            class_totals[AttributionClass.UNATTRIBUTED]
        ),
        difference_jpy=JpyAmount(Decimal(0)),
    )
    availability = (
        AttributionAvailability.AVAILABLE
        if attribution_readiness is None
        else AttributionAvailability.UNAVAILABLE
    )
    preliminary = AttributionRunResult(
        result_sha256=Sha256Digest("0" * 64),
        run_id=request.run_id,
        method_version=METHOD_VERSION,
        input_sha256=request.input_sha256,
        availability=availability,
        unavailable_reason=attribution_readiness,
        allocations=tuple(allocations),
        totals=totals,
        measurement_evaluation=evaluation,
        authority=AttributionAuthority(),
    )
    result_hash = _digest(preliminary.payload(include_result_hash=False))
    return AttributionRunResult(
        result_sha256=result_hash,
        run_id=preliminary.run_id,
        method_version=preliminary.method_version,
        input_sha256=preliminary.input_sha256,
        availability=preliminary.availability,
        unavailable_reason=preliminary.unavailable_reason,
        allocations=preliminary.allocations,
        totals=preliminary.totals,
        measurement_evaluation=preliminary.measurement_evaluation,
        authority=preliminary.authority,
    )


__all__ = (
    "ARTICLE_METRICS",
    "CONTRACT_VERSION",
    "DERIVED_METRICS",
    "DIRECT_CONFIDENCE_BPS",
    "ESTIMATED_CONFIDENCE_BPS",
    "METHOD_VERSION",
    "PERIOD_DURATION_DAYS",
    "PROFILE",
    "PROGRAM",
    "RECOMMENDATION_INPUTS_EXCLUDED",
    "AllocationReason",
    "ArticleMeasurement",
    "AttributionAllocation",
    "AttributionAuthority",
    "AttributionAvailability",
    "AttributionClass",
    "AttributionFailure",
    "AttributionFailureCode",
    "AttributionRunRequest",
    "AttributionRunResult",
    "AttributionTotals",
    "CohortMaturity",
    "CohortStatus",
    "ContractArticle",
    "DerivedMetric",
    "EstimationSignal",
    "MeasurementAttributionContract",
    "MeasurementEvaluation",
    "MeasurementPeriod",
    "MeasurementValue",
    "MeasurementValueState",
    "MeasurementVerification",
    "ProgramMeasurement",
    "ProviderRewardFact",
    "UnavailableReason",
    "VerificationState",
    "allocate_exact_jpy",
    "build_attribution_run",
    "evaluate_measurements",
    "fail_attribution",
)

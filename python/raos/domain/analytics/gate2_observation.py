"""Deterministic recorded-only GATE-2 observation domain for ST-1803.

This module transforms immutable aggregate observations into a non-attesting
local report.  It has no clock, filesystem, provider, network, persistence,
publication, public-projection, or editorial-mutation capability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, DecimalException, ROUND_HALF_EVEN, localcontext
from enum import Enum
import hashlib
import json
import re
from typing import Final, NoReturn, SupportsIndex

from raos.domain.analytics.kpi_read_model import (
    KPI_CALCULATION_VERSION,
    KPI_DEFINITION_VERSION,
    RAKUTEN_BLOG_PROGRAM,
)


PROGRAM: Final = RAKUTEN_BLOG_PROGRAM
REPORT_SCHEMA: Final = "ST1803_GATE2_OBSERVATION_REPORT_V1"
FIXTURE_SCHEMA: Final = "ST1803_RECORDED_SYNTHETIC_OBSERVATION_V1"
CALCULATION_VERSION: Final = f"ST1803-1.0.0+ST1205-{KPI_CALCULATION_VERSION}"
DEFINITION_VERSION: Final = f"ST1803-1.0.0+ST1205-{KPI_DEFINITION_VERSION}"

ARTICLE_METRICS: Final = (
    "search_impressions",
    "search_clicks",
    "qualified_organic_sessions",
    "article_views",
    "affiliate_clicks",
    "pending_outcomes",
    "confirmed_outcomes",
    "rejected_outcomes",
    "direct_confirmed_reward_jpy",
    "work_minutes",
    "incremental_cost_jpy",
    "broken_links",
    "affiliate_link_checks",
    "published_eligible",
    "indexed_valid",
    "eligible_major_query",
    "top20_major_query",
    "critical_user_complaints",
    "stale_exposure_views",
)
PROGRAM_METRICS: Final = (
    "unattributed_confirmed_reward_jpy",
    "provider_confirmed_reward_jpy",
)

_EXPECTED_SOURCE: Final = {
    "search_impressions": "SEARCH_CONSOLE",
    "search_clicks": "SEARCH_CONSOLE",
    "qualified_organic_sessions": "SEARCH_CONSOLE",
    "article_views": "FIRST_PARTY_EVENT",
    "affiliate_clicks": "FIRST_PARTY_EVENT",
    "pending_outcomes": "PROVIDER_REVENUE",
    "confirmed_outcomes": "PROVIDER_REVENUE",
    "rejected_outcomes": "PROVIDER_REVENUE",
    "direct_confirmed_reward_jpy": "PROVIDER_REVENUE",
    "work_minutes": "COST_LEDGER",
    "incremental_cost_jpy": "COST_LEDGER",
    "broken_links": "FRESHNESS_MONITOR",
    "affiliate_link_checks": "FRESHNESS_MONITOR",
    "published_eligible": "URL_INSPECTION",
    "indexed_valid": "URL_INSPECTION",
    "eligible_major_query": "SEARCH_CONSOLE",
    "top20_major_query": "SEARCH_CONSOLE",
    "critical_user_complaints": "EDITORIAL_QUALITY",
    "stale_exposure_views": "FRESHNESS_MONITOR",
    "unattributed_confirmed_reward_jpy": "PROVIDER_REVENUE",
    "provider_confirmed_reward_jpy": "PROVIDER_REVENUE",
}

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_ARTICLE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z", re.ASCII)
_SLUG = _ARTICLE_ID
_SOURCE = re.compile(r"[A-Z][A-Z0-9_]{2,63}\Z", re.ASCII)
_PROGRAM = re.compile(r"[A-Z][A-Z0-9_]{2,95}\Z", re.ASCII)
_MAX_INTEGER = (1 << 63) - 1
_REDACTED = "<redacted-gate2-observation>"


class ObservationFailureCode(str, Enum):
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
    OBSERVED_ZERO = "OBSERVED_ZERO"
    OBSERVED_VALUE = "OBSERVED_VALUE"


class CohortMaturity(str, Enum):
    MATURE = "MATURE"
    IMMATURE = "IMMATURE"
    UNAVAILABLE = "UNAVAILABLE"


class AttributionBasis(str, Enum):
    OWNER_VERIFIED_DIRECT_AGGREGATE = "OWNER_VERIFIED_DIRECT_AGGREGATE"
    UNVERIFIED = "UNVERIFIED"
    UNAVAILABLE = "UNAVAILABLE"
    UNATTRIBUTED_PROGRAM_TOTAL = "UNATTRIBUTED_PROGRAM_TOTAL"


class Availability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class UnavailableReason(str, Enum):
    MISSING_INPUT = "MISSING_INPUT"
    PERIOD_MISMATCH = "PERIOD_MISMATCH"
    PROGRAM_MISMATCH = "PROGRAM_MISMATCH"
    SOURCE_MISMATCH = "SOURCE_MISMATCH"
    UNVERIFIED_INPUT = "UNVERIFIED_INPUT"
    COHORT_IMMATURE = "COHORT_IMMATURE"
    ATTRIBUTION_UNVERIFIED = "ATTRIBUTION_UNVERIFIED"
    ZERO_DENOMINATOR = "ZERO_DENOMINATOR"
    MISSING_ARTICLE_SLOTS = "MISSING_ARTICLE_SLOTS"
    CONSERVATION_MISMATCH = "CONSERVATION_MISMATCH"


class BoundaryState(str, Enum):
    RECORDED_SYNTHETIC_ONLY = "RECORDED_SYNTHETIC_ONLY"
    IMMUTABLE_PROCESS_LOCAL = "IMMUTABLE_PROCESS_LOCAL"
    DISABLED = "DISABLED"
    NONE = "NONE"
    NOT_EXECUTED = "NOT_EXECUTED"
    BLOCKED = "BLOCKED"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("GATE-2 observation serialization is not supported")


@dataclass(frozen=True, slots=True, repr=False)
class ObservationFailure(RuntimeError):
    code: ObservationFailureCode

    def __post_init__(self) -> None:
        if type(self.code) is not ObservationFailureCode:
            raise TypeError("invalid GATE-2 observation failure code")
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"ObservationFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("GATE-2 observation failure serialization is not supported")


def fail_observation(
    code: ObservationFailureCode = ObservationFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise ObservationFailure(code) from None


@dataclass(frozen=True, slots=True, repr=False)
class Sha256Digest(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _SHA256.fullmatch(self.value) is None:
            fail_observation()

    @classmethod
    def of(cls, content: bytes) -> Sha256Digest:
        if type(content) is not bytes:
            fail_observation()
        return cls(hashlib.sha256(content).hexdigest())


@dataclass(frozen=True, slots=True, repr=False)
class FixtureByteLength(_RedactedValue):
    value: int

    def __post_init__(self) -> None:
        if type(self.value) is not int or not 0 < self.value <= 4 * 1024 * 1024:
            fail_observation()


@dataclass(frozen=True, slots=True, repr=False)
class ObservationPeriod(_RedactedValue):
    start_date: date
    end_exclusive_date: date
    as_of_date: date

    def __post_init__(self) -> None:
        if (
            type(self.start_date) is not date
            or type(self.end_exclusive_date) is not date
            or type(self.as_of_date) is not date
            or self.start_date >= self.end_exclusive_date
            or self.as_of_date != self.end_exclusive_date
            or not 1 <= self.elapsed_days <= 366
        ):
            fail_observation()

    @property
    def elapsed_days(self) -> int:
        return (self.end_exclusive_date - self.start_date).days

    def payload(self) -> dict[str, object]:
        return {
            "as_of_date": self.as_of_date.isoformat(),
            "elapsed_days": self.elapsed_days,
            "end_exclusive_date": self.end_exclusive_date.isoformat(),
            "start_date": self.start_date.isoformat(),
        }


@dataclass(frozen=True, slots=True, repr=False)
class MetricValue(_RedactedValue):
    metric_key: str
    state: ValueState
    value: int | None
    source: str
    input_sha256: Sha256Digest | None

    def __post_init__(self) -> None:
        if (
            self.metric_key not in _EXPECTED_SOURCE
            or type(self.state) is not ValueState
            or type(self.source) is not str
            or _SOURCE.fullmatch(self.source) is None
            or (
                self.input_sha256 is not None
                and type(self.input_sha256) is not Sha256Digest
            )
        ):
            fail_observation()
        absent = self.state in {ValueState.NOT_OBSERVED, ValueState.UNAVAILABLE}
        if absent:
            if self.value is not None or self.input_sha256 is not None:
                fail_observation()
            return
        if self.input_sha256 is None:
            fail_observation()
        if self.state is ValueState.UNVERIFIED:
            if self.value is not None and (
                type(self.value) is not int or not 0 <= self.value <= _MAX_INTEGER
            ):
                fail_observation()
            return
        if self.state is ValueState.OBSERVED_ZERO:
            if type(self.value) is not int or self.value != 0:
                fail_observation()
            return
        if type(self.value) is not int or not 1 <= self.value <= _MAX_INTEGER:
            fail_observation()

    @property
    def verified_value(self) -> int | None:
        if self.state in {ValueState.OBSERVED_ZERO, ValueState.OBSERVED_VALUE}:
            return self.value
        return None

    def payload(self) -> dict[str, object]:
        return {
            "input_sha256": (
                None if self.input_sha256 is None else self.input_sha256.value
            ),
            "metric_key": self.metric_key,
            "source": self.source,
            "state": self.state.value,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True, repr=False)
class ArticleObservation(_RedactedValue):
    sequence: int
    previous_entry_sha256: Sha256Digest
    entry_sha256: Sha256Digest
    slot: int
    article_id: str
    slug: str
    packet_sha256: Sha256Digest
    period: ObservationPeriod
    program_id: str
    cohort_maturity: CohortMaturity
    attribution_basis: AttributionBasis
    attribution_verified: bool
    metrics: tuple[MetricValue, ...]

    def __post_init__(self) -> None:
        if (
            type(self.sequence) is not int
            or not 1 <= self.sequence <= 5
            or type(self.previous_entry_sha256) is not Sha256Digest
            or type(self.entry_sha256) is not Sha256Digest
            or type(self.slot) is not int
            or not 1 <= self.slot <= 5
            or type(self.article_id) is not str
            or _ARTICLE_ID.fullmatch(self.article_id) is None
            or type(self.slug) is not str
            or _SLUG.fullmatch(self.slug) is None
            or type(self.packet_sha256) is not Sha256Digest
            or type(self.period) is not ObservationPeriod
            or type(self.program_id) is not str
            or _PROGRAM.fullmatch(self.program_id) is None
            or type(self.cohort_maturity) is not CohortMaturity
            or type(self.attribution_basis) is not AttributionBasis
            or type(self.attribution_verified) is not bool
            or type(self.metrics) is not tuple
            or any(type(metric) is not MetricValue for metric in self.metrics)
            or tuple(metric.metric_key for metric in self.metrics) != ARTICLE_METRICS
        ):
            fail_observation()
        if self.entry_sha256 != canonical_entry_digest(
            entry_type="ARTICLE",
            sequence=self.sequence,
            previous_entry_sha256=self.previous_entry_sha256,
            payload=self.entry_payload(),
        ):
            fail_observation()

    def metric(self, key: str) -> MetricValue:
        try:
            index = ARTICLE_METRICS.index(key)
        except ValueError:
            fail_observation()
        return self.metrics[index]

    def entry_payload(self) -> dict[str, object]:
        return {
            "article_id": self.article_id,
            "attribution_basis": self.attribution_basis.value,
            "attribution_verified": self.attribution_verified,
            "cohort_maturity": self.cohort_maturity.value,
            "metrics": [metric.payload() for metric in self.metrics],
            "packet_sha256": self.packet_sha256.value,
            "period": self.period.payload(),
            "program": self.program_id,
            "slot": self.slot,
            "slug": self.slug,
        }


@dataclass(frozen=True, slots=True, repr=False)
class ProgramObservation(_RedactedValue):
    sequence: int
    previous_entry_sha256: Sha256Digest
    entry_sha256: Sha256Digest
    period: ObservationPeriod
    program_id: str
    metrics: tuple[MetricValue, ...]

    def __post_init__(self) -> None:
        if (
            self.sequence != 6
            or type(self.previous_entry_sha256) is not Sha256Digest
            or type(self.entry_sha256) is not Sha256Digest
            or type(self.period) is not ObservationPeriod
            or type(self.program_id) is not str
            or _PROGRAM.fullmatch(self.program_id) is None
            or type(self.metrics) is not tuple
            or any(type(metric) is not MetricValue for metric in self.metrics)
            or tuple(metric.metric_key for metric in self.metrics) != PROGRAM_METRICS
        ):
            fail_observation()
        if self.entry_sha256 != canonical_entry_digest(
            entry_type="PROGRAM",
            sequence=self.sequence,
            previous_entry_sha256=self.previous_entry_sha256,
            payload=self.entry_payload(),
        ):
            fail_observation()

    def metric(self, key: str) -> MetricValue:
        try:
            index = PROGRAM_METRICS.index(key)
        except ValueError:
            fail_observation()
        return self.metrics[index]

    def entry_payload(self) -> dict[str, object]:
        return {
            "metrics": [metric.payload() for metric in self.metrics],
            "period": self.period.payload(),
            "program": self.program_id,
        }


@dataclass(frozen=True, slots=True, repr=False)
class RecordedObservationBatch(_RedactedValue):
    recording_id: str
    recorded_at: str
    fixture_digest: Sha256Digest
    fixture_length: FixtureByteLength
    contract_digest: Sha256Digest
    input_digest: Sha256Digest
    context_period: ObservationPeriod
    program_id: str
    articles: tuple[ArticleObservation, ...]
    program_observation: ProgramObservation
    synthetic: bool
    append_only: bool
    immutable: bool

    def __post_init__(self) -> None:
        if (
            self.recording_id != "five-slot-complete"
            or type(self.recorded_at) is not str
            or not self.recorded_at.endswith("Z")
            or type(self.fixture_digest) is not Sha256Digest
            or type(self.fixture_length) is not FixtureByteLength
            or type(self.contract_digest) is not Sha256Digest
            or type(self.input_digest) is not Sha256Digest
            or type(self.context_period) is not ObservationPeriod
            or type(self.program_id) is not str
            or _PROGRAM.fullmatch(self.program_id) is None
            or type(self.articles) is not tuple
            or len(self.articles) != 5
            or any(type(article) is not ArticleObservation for article in self.articles)
            or tuple(article.slot for article in self.articles) != (1, 2, 3, 4, 5)
            or tuple(article.sequence for article in self.articles) != (1, 2, 3, 4, 5)
            or len({article.article_id for article in self.articles}) != 5
            or len({article.slug for article in self.articles}) != 5
            or type(self.program_observation) is not ProgramObservation
            or self.synthetic is not True
            or self.append_only is not True
            or self.immutable is not True
        ):
            fail_observation()
        expected_previous = Sha256Digest("0" * 64)
        for article in self.articles:
            if article.previous_entry_sha256 != expected_previous:
                fail_observation()
            expected_previous = article.entry_sha256
        if self.program_observation.previous_entry_sha256 != expected_previous:
            fail_observation()
        if self.input_digest != canonical_input_digest(
            self.articles, self.program_observation
        ):
            fail_observation()


@dataclass(frozen=True, slots=True, repr=False)
class ObservationCommand(_RedactedValue):
    recording_id: str
    fixture_digest: Sha256Digest
    fixture_length: FixtureByteLength
    contract_digest: Sha256Digest
    expected_input_digest: Sha256Digest
    period: ObservationPeriod
    program_id: str

    def __post_init__(self) -> None:
        if (
            self.recording_id != "five-slot-complete"
            or type(self.fixture_digest) is not Sha256Digest
            or type(self.fixture_length) is not FixtureByteLength
            or type(self.contract_digest) is not Sha256Digest
            or type(self.expected_input_digest) is not Sha256Digest
            or type(self.period) is not ObservationPeriod
            or self.program_id != PROGRAM
        ):
            fail_observation()


@dataclass(frozen=True, slots=True, repr=False)
class MetricResult(_RedactedValue):
    metric_id: str
    availability: Availability
    value: Decimal | None
    unit: str
    unavailable_reason: UnavailableReason | None
    input_keys: tuple[str, ...]
    recommendation_order_effect: bool = False

    def __post_init__(self) -> None:
        available = (
            self.availability is Availability.AVAILABLE
            and type(self.value) is Decimal
            and self.value.is_finite()
            and self.unavailable_reason is None
        )
        unavailable = (
            self.availability is Availability.UNAVAILABLE
            and self.value is None
            and type(self.unavailable_reason) is UnavailableReason
        )
        if (
            type(self.metric_id) is not str
            or not self.metric_id
            or not (available or unavailable)
            or self.unit
            not in {"COUNT", "DAYS", "JPY", "RATIO", "JPY_PER_CLICK", "JPY_PER_HOUR"}
            or type(self.input_keys) is not tuple
            or not self.input_keys
            or self.recommendation_order_effect is not False
        ):
            fail_observation()

    def payload(self) -> dict[str, object]:
        return {
            "availability": self.availability.value,
            "input_keys": list(self.input_keys),
            "metric_id": self.metric_id,
            "recommendation_order_effect": False,
            "unavailable_reason": (
                None
                if self.unavailable_reason is None
                else self.unavailable_reason.value
            ),
            "unit": self.unit,
            "value": None if self.value is None else str(self.value),
        }


@dataclass(frozen=True, slots=True, repr=False)
class ImprovementCandidate(_RedactedValue):
    slot: int
    article_id: str
    code: str
    evidence_metrics: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            type(self.slot) is not int
            or not 1 <= self.slot <= 5
            or type(self.article_id) is not str
            or _ARTICLE_ID.fullmatch(self.article_id) is None
            or self.code
            not in {
                "REVIEW_SEARCH_SNIPPET_HYPOTHESIS",
                "REVIEW_QUERY_INTENT_AND_DISCOVERY",
                "REVIEW_LINK_HEALTH",
                "REVIEW_FRESHNESS_EXPOSURE",
            }
            or type(self.evidence_metrics) is not tuple
            or not self.evidence_metrics
        ):
            fail_observation()

    def payload(self) -> dict[str, object]:
        return {
            "article_id": self.article_id,
            "authority": "NONE",
            "code": self.code,
            "evidence_metrics": list(self.evidence_metrics),
            "mutations": [],
            "slot": self.slot,
        }


@dataclass(frozen=True, slots=True, repr=False)
class Gate2ObservationReport(_RedactedValue):
    fixture_digest: Sha256Digest
    contract_digest: Sha256Digest
    input_digest: Sha256Digest
    period: ObservationPeriod
    program_id: str
    input_totals: tuple[MetricResult, ...]
    metrics: tuple[MetricResult, ...]
    candidates: tuple[ImprovementCandidate, ...]
    source_head_sha256: Sha256Digest
    direct_confirmed_reward_jpy: int | None
    unattributed_confirmed_reward_jpy: int | None
    provider_confirmed_reward_jpy: int | None
    reward_conservation: Availability
    reward_conservation_reason: UnavailableReason | None
    execution: BoundaryState = BoundaryState.RECORDED_SYNTHETIC_ONLY
    input_storage: BoundaryState = BoundaryState.IMMUTABLE_PROCESS_LOCAL
    recommendation_input: BoundaryState = BoundaryState.DISABLED
    mutation_authority: BoundaryState = BoundaryState.NONE
    gate_approval: BoundaryState = BoundaryState.NONE
    formal_tst_030: BoundaryState = BoundaryState.NOT_EXECUTED
    formal_tst_032: BoundaryState = BoundaryState.NOT_EXECUTED
    actual_observation: BoundaryState = BoundaryState.NOT_EXECUTED
    overall: BoundaryState = BoundaryState.BLOCKED

    def __post_init__(self) -> None:
        conservation_available = (
            self.reward_conservation is Availability.AVAILABLE
            and self.reward_conservation_reason is None
        )
        conservation_unavailable = (
            self.reward_conservation is Availability.UNAVAILABLE
            and type(self.reward_conservation_reason) is UnavailableReason
        )
        if (
            type(self.fixture_digest) is not Sha256Digest
            or type(self.contract_digest) is not Sha256Digest
            or type(self.input_digest) is not Sha256Digest
            or type(self.period) is not ObservationPeriod
            or self.program_id != PROGRAM
            or type(self.input_totals) is not tuple
            or len(self.input_totals) != 11
            or any(type(metric) is not MetricResult for metric in self.input_totals)
            or type(self.metrics) is not tuple
            or len(self.metrics) != 12
            or any(type(metric) is not MetricResult for metric in self.metrics)
            or type(self.candidates) is not tuple
            or any(
                type(candidate) is not ImprovementCandidate
                for candidate in self.candidates
            )
            or type(self.source_head_sha256) is not Sha256Digest
            or not (conservation_available or conservation_unavailable)
            or self.execution is not BoundaryState.RECORDED_SYNTHETIC_ONLY
            or self.input_storage is not BoundaryState.IMMUTABLE_PROCESS_LOCAL
            or self.recommendation_input is not BoundaryState.DISABLED
            or self.mutation_authority is not BoundaryState.NONE
            or self.gate_approval is not BoundaryState.NONE
            or self.formal_tst_030 is not BoundaryState.NOT_EXECUTED
            or self.formal_tst_032 is not BoundaryState.NOT_EXECUTED
            or self.actual_observation is not BoundaryState.NOT_EXECUTED
            or self.overall is not BoundaryState.BLOCKED
        ):
            fail_observation()

    def payload(self) -> dict[str, object]:
        return {
            "actual_observations": [],
            "authority": {
                "article_html_mutation": "NONE",
                "cta_mutation": "NONE",
                "gate_approval": self.gate_approval.value,
                "product_selection_mutation": "NONE",
                "publication_snapshot_mutation": "NONE",
                "recommendation_order_mutation": "NONE",
            },
            "boundary": {
                "actual_observation": self.actual_observation.value,
                "execution": self.execution.value,
                "formal_tst_030": self.formal_tst_030.value,
                "formal_tst_032": self.formal_tst_032.value,
                "input_storage": self.input_storage.value,
                "live_provider": "NOT_EXECUTED",
                "network": "NOT_EXECUTED",
                "publication": "NOT_EXECUTED",
                "recommendation_input": self.recommendation_input.value,
                "staging": "NOT_EXECUTED",
            },
            "calculation_version": CALCULATION_VERSION,
            "candidates": [candidate.payload() for candidate in self.candidates],
            "definition_version": DEFINITION_VERSION,
            "evidence_classification": "RECORDED_SYNTHETIC_ONLY_NON_ATTESTING",
            "finance_separation": {
                "direct_confirmed_reward_jpy": self.direct_confirmed_reward_jpy,
                "provider_confirmed_reward_jpy": self.provider_confirmed_reward_jpy,
                "reward_conservation": self.reward_conservation.value,
                "reward_conservation_reason": (
                    None
                    if self.reward_conservation_reason is None
                    else self.reward_conservation_reason.value
                ),
                "unattributed_confirmed_reward_jpy": self.unattributed_confirmed_reward_jpy,
                "unattributed_reward_allocated_to_articles": False,
            },
            "input_contract_sha256": self.contract_digest.value,
            "input_sha256": self.input_digest.value,
            "input_totals": [metric.payload() for metric in self.input_totals],
            "metrics": [metric.payload() for metric in self.metrics],
            "modifications_applied": [],
            "overall": self.overall.value,
            "period": self.period.payload(),
            "program": self.program_id,
            "recorded_fixture_sha256": self.fixture_digest.value,
            "schema": REPORT_SCHEMA,
            "source_head_sha256": self.source_head_sha256.value,
            "synthetic": True,
        }


def _unavailable(
    metric_id: str,
    unit: str,
    inputs: tuple[str, ...],
    reason: UnavailableReason,
) -> MetricResult:
    return MetricResult(
        metric_id=metric_id,
        availability=Availability.UNAVAILABLE,
        value=None,
        unit=unit,
        unavailable_reason=reason,
        input_keys=inputs,
    )


def _available(
    metric_id: str,
    unit: str,
    inputs: tuple[str, ...],
    value: Decimal,
) -> MetricResult:
    return MetricResult(
        metric_id=metric_id,
        availability=Availability.AVAILABLE,
        value=value,
        unit=unit,
        unavailable_reason=None,
        input_keys=inputs,
    )


def _sum_article_metric(
    batch: RecordedObservationBatch,
    key: str,
    *,
    financial: bool = False,
) -> tuple[int | None, UnavailableReason | None]:
    if tuple(article.slot for article in batch.articles) != (1, 2, 3, 4, 5):
        return None, UnavailableReason.MISSING_ARTICLE_SLOTS
    total = 0
    for article in batch.articles:
        if article.period != batch.context_period:
            return None, UnavailableReason.PERIOD_MISMATCH
        if article.program_id != batch.program_id or article.program_id != PROGRAM:
            return None, UnavailableReason.PROGRAM_MISMATCH
        if article.cohort_maturity is not CohortMaturity.MATURE:
            return None, UnavailableReason.COHORT_IMMATURE
        metric = article.metric(key)
        if metric.source != _EXPECTED_SOURCE[key]:
            return None, UnavailableReason.SOURCE_MISMATCH
        if metric.state in {ValueState.NOT_OBSERVED, ValueState.UNAVAILABLE}:
            return None, UnavailableReason.MISSING_INPUT
        if metric.state is ValueState.UNVERIFIED:
            return None, UnavailableReason.UNVERIFIED_INPUT
        if financial and (
            article.attribution_basis
            is not AttributionBasis.OWNER_VERIFIED_DIRECT_AGGREGATE
            or article.attribution_verified is not True
        ):
            return None, UnavailableReason.ATTRIBUTION_UNVERIFIED
        assert metric.value is not None
        total += metric.value
        if total > _MAX_INTEGER:
            fail_observation()
    return total, None


def _program_metric(
    batch: RecordedObservationBatch,
    key: str,
) -> tuple[int | None, UnavailableReason | None]:
    observed = batch.program_observation
    if observed.period != batch.context_period:
        return None, UnavailableReason.PERIOD_MISMATCH
    if observed.program_id != batch.program_id or observed.program_id != PROGRAM:
        return None, UnavailableReason.PROGRAM_MISMATCH
    metric = observed.metric(key)
    if metric.source != _EXPECTED_SOURCE[key]:
        return None, UnavailableReason.SOURCE_MISMATCH
    if metric.state in {ValueState.NOT_OBSERVED, ValueState.UNAVAILABLE}:
        return None, UnavailableReason.MISSING_INPUT
    if metric.state is ValueState.UNVERIFIED:
        return None, UnavailableReason.UNVERIFIED_INPUT
    assert metric.value is not None
    return metric.value, None


def _ratio(
    batch: RecordedObservationBatch,
    metric_id: str,
    numerator_key: str,
    denominator_key: str,
    *,
    numerator_override: int | None = None,
    denominator_override: int | None = None,
    financial: bool = False,
    multiplier: Decimal = Decimal("1"),
    unit: str = "RATIO",
) -> MetricResult:
    numerator, numerator_reason = (
        (numerator_override, None)
        if numerator_override is not None
        else _sum_article_metric(batch, numerator_key, financial=financial)
    )
    denominator, denominator_reason = (
        (denominator_override, None)
        if denominator_override is not None
        else _sum_article_metric(batch, denominator_key, financial=financial)
    )
    reason = numerator_reason or denominator_reason
    inputs = (numerator_key, denominator_key)
    if reason is not None:
        return _unavailable(metric_id, unit, inputs, reason)
    assert numerator is not None and denominator is not None
    if denominator == 0:
        return _unavailable(metric_id, unit, inputs, UnavailableReason.ZERO_DENOMINATOR)
    try:
        with localcontext() as context:
            context.prec = 50
            value = (Decimal(numerator) * multiplier / Decimal(denominator)).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_EVEN
            )
    except DecimalException:
        fail_observation()
    return _available(metric_id, unit, inputs, value)


def _identity(
    batch: RecordedObservationBatch,
    metric_id: str,
    key: str,
    *,
    unit: str = "COUNT",
    financial: bool = False,
) -> MetricResult:
    value, reason = _sum_article_metric(batch, key, financial=financial)
    if reason is not None:
        return _unavailable(metric_id, unit, (key,), reason)
    assert value is not None
    return _available(metric_id, unit, (key,), Decimal(value))


def _coverage_counts(
    batch: RecordedObservationBatch,
    *,
    numerator: str,
    denominator: str,
) -> tuple[int | None, int | None, UnavailableReason | None]:
    numerator_total, reason = _sum_article_metric(batch, numerator)
    if reason is not None:
        return None, None, reason
    denominator_total, reason = _sum_article_metric(batch, denominator)
    if reason is not None:
        return None, None, reason
    return numerator_total, denominator_total, None


def _impression_coverage(batch: RecordedObservationBatch) -> MetricResult:
    indexed, _, reason = _coverage_counts(
        batch, numerator="indexed_valid", denominator="published_eligible"
    )
    impressions_total, impressions_reason = _sum_article_metric(
        batch, "search_impressions"
    )
    reason = reason or impressions_reason
    if reason is not None:
        return _unavailable(
            "impression_coverage_rate",
            "RATIO",
            ("indexed_articles_with_impressions", "indexed_valid"),
            reason,
        )
    assert indexed is not None and impressions_total is not None
    if indexed == 0:
        return _unavailable(
            "impression_coverage_rate",
            "RATIO",
            ("indexed_articles_with_impressions", "indexed_valid"),
            UnavailableReason.ZERO_DENOMINATOR,
        )
    with_impressions = sum(
        1
        for article in batch.articles
        if article.metric("indexed_valid").verified_value == 1
        and (article.metric("search_impressions").verified_value or 0) > 0
    )
    return _ratio(
        batch,
        "impression_coverage_rate",
        "indexed_articles_with_impressions",
        "indexed_valid",
        numerator_override=with_impressions,
        denominator_override=indexed,
    )


def _finance_metrics(
    batch: RecordedObservationBatch,
) -> tuple[MetricResult, MetricResult, MetricResult]:
    reward_per_click = _ratio(
        batch,
        "confirmed_reward_per_click",
        "direct_confirmed_reward_jpy",
        "affiliate_clicks",
        financial=True,
        unit="JPY_PER_CLICK",
    )
    confirmed, confirmed_reason = _sum_article_metric(batch, "confirmed_outcomes")
    rejected, rejected_reason = _sum_article_metric(batch, "rejected_outcomes")
    reason = confirmed_reason or rejected_reason
    if reason is None and any(
        article.attribution_basis
        is not AttributionBasis.OWNER_VERIFIED_DIRECT_AGGREGATE
        or article.attribution_verified is not True
        for article in batch.articles
    ):
        reason = UnavailableReason.ATTRIBUTION_UNVERIFIED
    if reason is not None:
        confirmation_rate = _unavailable(
            "confirmation_rate",
            "RATIO",
            ("confirmed_outcomes", "rejected_outcomes"),
            reason,
        )
    else:
        assert confirmed is not None and rejected is not None
        confirmation_rate = _ratio(
            batch,
            "confirmation_rate",
            "confirmed_outcomes",
            "confirmed_plus_rejected_outcomes",
            numerator_override=confirmed,
            denominator_override=confirmed + rejected,
            financial=True,
        )
    reward_per_hour = _ratio(
        batch,
        "confirmed_reward_per_content_hour",
        "direct_confirmed_reward_jpy",
        "work_minutes",
        financial=True,
        multiplier=Decimal("60"),
        unit="JPY_PER_HOUR",
    )
    return reward_per_click, confirmation_rate, reward_per_hour


def _candidate_report(
    batch: RecordedObservationBatch, search_ctr: MetricResult
) -> tuple[ImprovementCandidate, ...]:
    candidates: list[ImprovementCandidate] = []
    aggregate_ctr = (
        search_ctr.value if search_ctr.availability is Availability.AVAILABLE else None
    )
    for article in batch.articles:
        impressions = article.metric("search_impressions").verified_value
        clicks = article.metric("search_clicks").verified_value
        indexed = article.metric("indexed_valid").verified_value
        views = article.metric("article_views").verified_value
        stale = article.metric("stale_exposure_views").verified_value
        broken = article.metric("broken_links").verified_value
        if indexed == 1 and impressions == 0:
            candidates.append(
                ImprovementCandidate(
                    article.slot,
                    article.article_id,
                    "REVIEW_QUERY_INTENT_AND_DISCOVERY",
                    ("indexed_valid", "search_impressions"),
                )
            )
        if (
            aggregate_ctr is not None
            and impressions is not None
            and impressions > 0
            and clicks is not None
        ):
            with localcontext() as context:
                context.prec = 50
                article_ctr = (Decimal(clicks) / Decimal(impressions)).quantize(
                    Decimal("0.000001"), rounding=ROUND_HALF_EVEN
                )
            if article_ctr < aggregate_ctr:
                candidates.append(
                    ImprovementCandidate(
                        article.slot,
                        article.article_id,
                        "REVIEW_SEARCH_SNIPPET_HYPOTHESIS",
                        ("search_clicks", "search_impressions"),
                    )
                )
        if broken is not None and broken > 0:
            candidates.append(
                ImprovementCandidate(
                    article.slot,
                    article.article_id,
                    "REVIEW_LINK_HEALTH",
                    ("broken_links", "affiliate_link_checks"),
                )
            )
        if views is not None and views > 0 and stale is not None:
            with localcontext() as context:
                context.prec = 50
                stale_rate = Decimal(stale) / Decimal(views)
            if stale_rate >= Decimal("0.02"):
                candidates.append(
                    ImprovementCandidate(
                        article.slot,
                        article.article_id,
                        "REVIEW_FRESHNESS_EXPOSURE",
                        ("stale_exposure_views", "article_views"),
                    )
                )
    return tuple(sorted(candidates, key=lambda item: (item.slot, item.code)))


def build_gate2_observation_report(
    batch: RecordedObservationBatch,
) -> Gate2ObservationReport:
    """Build one immutable synthetic report without approving or mutating anything."""

    if type(batch) is not RecordedObservationBatch:
        fail_observation()
    search_ctr = _ratio(
        batch,
        "search_ctr",
        "search_clicks",
        "search_impressions",
    )
    affiliate_click_rate = _ratio(
        batch,
        "affiliate_click_rate",
        "affiliate_clicks",
        "article_views",
    )
    indexed, published, indexed_reason = _coverage_counts(
        batch, numerator="indexed_valid", denominator="published_eligible"
    )
    indexed_rate = (
        _unavailable(
            "indexed_article_rate",
            "RATIO",
            ("indexed_valid", "published_eligible"),
            indexed_reason,
        )
        if indexed_reason is not None
        else _ratio(
            batch,
            "indexed_article_rate",
            "indexed_valid",
            "published_eligible",
            numerator_override=indexed,
            denominator_override=published,
        )
    )
    top20_rate = _ratio(
        batch,
        "top20_article_rate",
        "top20_major_query",
        "eligible_major_query",
    )
    stale_rate = _ratio(
        batch,
        "stale_exposure_rate",
        "stale_exposure_views",
        "article_views",
    )
    broken_rate = _ratio(
        batch,
        "broken_affiliate_link_rate",
        "broken_links",
        "affiliate_link_checks",
    )
    reward_per_click, confirmation_rate, reward_per_hour = _finance_metrics(batch)
    observation_days = _available(
        "observation_days",
        "DAYS",
        ("period",),
        Decimal(batch.context_period.elapsed_days),
    )
    qualified_sessions = _identity(
        batch, "qualified_organic_sessions", "qualified_organic_sessions"
    )
    metrics = (
        observation_days,
        qualified_sessions,
        indexed_rate,
        _impression_coverage(batch),
        top20_rate,
        search_ctr,
        affiliate_click_rate,
        stale_rate,
        broken_rate,
        reward_per_click,
        confirmation_rate,
        reward_per_hour,
    )
    input_totals = tuple(
        _identity(
            batch,
            f"total_{key}",
            key,
            unit="JPY" if key.endswith("_jpy") else "COUNT",
            financial=key == "direct_confirmed_reward_jpy",
        )
        for key in (
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
    )

    direct_reward, direct_reason = _sum_article_metric(
        batch, "direct_confirmed_reward_jpy", financial=True
    )
    unattributed, unattributed_reason = _program_metric(
        batch, "unattributed_confirmed_reward_jpy"
    )
    provider_total, provider_reason = _program_metric(
        batch, "provider_confirmed_reward_jpy"
    )
    conservation_reason = direct_reason or unattributed_reason or provider_reason
    if (
        conservation_reason is None
        and direct_reward is not None
        and unattributed is not None
        and provider_total is not None
        and direct_reward + unattributed != provider_total
    ):
        conservation_reason = UnavailableReason.CONSERVATION_MISMATCH

    return Gate2ObservationReport(
        fixture_digest=batch.fixture_digest,
        contract_digest=batch.contract_digest,
        input_digest=batch.input_digest,
        period=batch.context_period,
        program_id=batch.program_id,
        input_totals=input_totals,
        metrics=metrics,
        candidates=_candidate_report(batch, search_ctr),
        source_head_sha256=batch.program_observation.entry_sha256,
        direct_confirmed_reward_jpy=direct_reward,
        unattributed_confirmed_reward_jpy=unattributed,
        provider_confirmed_reward_jpy=provider_total,
        reward_conservation=(
            Availability.AVAILABLE
            if conservation_reason is None
            else Availability.UNAVAILABLE
        ),
        reward_conservation_reason=conservation_reason,
    )


def canonical_input_digest(
    articles: tuple[ArticleObservation, ...],
    program_observation: ProgramObservation,
) -> Sha256Digest:
    """Hash normalized immutable values; caller order is part of the contract."""

    document = {
        "article_entries": [article.entry_sha256.value for article in articles],
        "program_entry": program_observation.entry_sha256.value,
    }
    return Sha256Digest.of(
        json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def expected_metric_source(metric_key: str) -> str:
    try:
        return _EXPECTED_SOURCE[metric_key]
    except KeyError, TypeError:
        fail_observation()


def canonical_entry_digest(
    *,
    entry_type: str,
    sequence: int,
    previous_entry_sha256: Sha256Digest,
    payload: dict[str, object],
) -> Sha256Digest:
    if (
        entry_type not in {"ARTICLE", "PROGRAM"}
        or type(sequence) is not int
        or not 1 <= sequence <= 6
        or type(previous_entry_sha256) is not Sha256Digest
        or type(payload) is not dict
    ):
        fail_observation()
    document = {
        "payload": payload,
        "previous_entry_sha256": previous_entry_sha256.value,
        "sequence": sequence,
        "type": entry_type,
    }
    return Sha256Digest.of(
        json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


__all__ = [
    "ARTICLE_METRICS",
    "AttributionBasis",
    "Availability",
    "BoundaryState",
    "CALCULATION_VERSION",
    "CohortMaturity",
    "DEFINITION_VERSION",
    "FIXTURE_SCHEMA",
    "FixtureByteLength",
    "Gate2ObservationReport",
    "MetricResult",
    "MetricValue",
    "ObservationCommand",
    "ObservationFailure",
    "ObservationFailureCode",
    "ObservationPeriod",
    "PROGRAM",
    "PROGRAM_METRICS",
    "ProgramObservation",
    "RecordedObservationBatch",
    "REPORT_SCHEMA",
    "Sha256Digest",
    "UnavailableReason",
    "ValueState",
    "ArticleObservation",
    "build_gate2_observation_report",
    "canonical_entry_digest",
    "canonical_input_digest",
    "expected_metric_source",
    "fail_observation",
]

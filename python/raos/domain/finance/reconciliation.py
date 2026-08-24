"""Deterministic recorded/synthetic finance reconciliation for ST-1305.

The report reconciles already-normalized ST-1303 attribution and ST-1304
unit-economics results.  It never ingests a provider file, invents unavailable
generated/cancelled totals, allocates unattributed reward to articles, or
changes editorial/publication state.  Learning candidates are built from a
closed non-finance signal type so reward, commission, EPC, RPM, cost and profit
cannot influence them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
import re
from typing import Final, NoReturn, SupportsIndex
from uuid import RFC_4122, UUID

from raos.domain.finance.attribution import (
    DERIVED_METRICS,
    PROGRAM,
    ArticleMeasurement,
    CohortMaturity,
    ContractArticle,
    DerivedMetric,
    MeasurementValue,
    MeasurementValueState,
    UnavailableReason as MeasurementUnavailableReason,
    VerificationState,
    build_attribution_run,
)
from raos.domain.finance.provider_fact_commit import JpyAmount
from raos.domain.finance.unit_economics import (
    METRIC_NAMES as UNIT_ECONOMICS_METRIC_NAMES,
    UnitEconomicsMetric,
    UnitEconomicsRunRequest,
    UnitEconomicsRunResult,
    build_unit_economics,
)
from raos.domain.ops.object_intake import Sha256Digest


PROFILE: Final = "RAOS_ST1305_RECORDED_SYNTHETIC_V2"
METHOD_VERSION: Final = "RAOS_ST1305_FINANCE_RECONCILIATION_V2"
_MAX_CANONICAL_BYTES: Final = 4 * 1024 * 1024
_MAX_COUNT: Final = (1 << 63) - 1
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)

CANONICAL_RECONCILIATION_DIMENSIONS: Final = (
    "file_hash_uniqueness",
    "row_count",
    "generated_confirmed_cancelled_amount_totals",
    "currency",
    "period",
    "duplicate_provider_row",
    "dry_run_to_commit_hash_equality",
)
DEPENDENCY_RECONCILIATION_DIMENSIONS: Final = (
    "provider_to_attribution_confirmed_total",
    "attribution_to_unit_economics_confirmed_total",
    "direct_measurement_to_attribution_total",
    "unattributed_measurement_to_attribution_total",
    "work_minutes_measurement_to_cost_total",
    "incremental_cost_measurement_to_cost_total",
    "measurement_readiness",
)
RECONCILIATION_DIMENSIONS: Final = (
    *CANONICAL_RECONCILIATION_DIMENSIONS,
    *DEPENDENCY_RECONCILIATION_DIMENSIONS,
)
CANDIDATE_SIGNAL_NAMES: Final = (
    "search_impressions",
    "search_clicks",
    "article_views",
    "affiliate_clicks",
    "broken_links",
)
FINANCE_SIGNALS_EXCLUDED_FROM_CANDIDATES: Final = (
    "pending_outcomes",
    "confirmed_outcomes",
    "rejected_outcomes",
    "direct_confirmed_reward_jpy",
    "unattributed_confirmed_reward_jpy",
    "affiliate_commission_rate",
    "incremental_cost_jpy",
    "work_minutes",
    "epc",
    "rpm",
    "profit",
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


class FinanceReconciliationFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    INPUT_HASH_MISMATCH = "INPUT_HASH_MISMATCH"
    DEPENDENCY_RESULT_MISMATCH = "DEPENDENCY_RESULT_MISMATCH"
    RESULT_MISMATCH = "RESULT_MISMATCH"
    RUN_ID_CONFLICT = "RUN_ID_CONFLICT"
    RECORDED_RUN_UNAVAILABLE = "RECORDED_RUN_UNAVAILABLE"
    LOCAL_ENVIRONMENT_REQUIRED = "LOCAL_ENVIRONMENT_REQUIRED"
    FIXTURE_INVALID = "FIXTURE_INVALID"


class FinanceReconciliationFailure(RuntimeError):
    """Closed non-reflecting failure; rejected finance input is not retained."""

    __slots__ = ("_code",)

    def __init__(self, code: FinanceReconciliationFailureCode) -> None:
        if type(code) is not FinanceReconciliationFailureCode:
            raise TypeError("invalid finance-reconciliation failure code") from None
        self._code = code
        super().__init__(code.value)

    @property
    def code(self) -> FinanceReconciliationFailureCode:
        return self._code

    def __str__(self) -> str:
        return self._code.value

    def __repr__(self) -> str:
        return f"FinanceReconciliationFailure(code={self._code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("finance-reconciliation failure serialization is forbidden")


def fail_finance_reconciliation(
    code: FinanceReconciliationFailureCode = (
        FinanceReconciliationFailureCode.INVALID_ARGUMENT
    ),
) -> NoReturn:
    raise FinanceReconciliationFailure(code) from None


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-st1305>)"

    def __str__(self) -> str:
        return "<redacted-st1305>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("finance-reconciliation value serialization is forbidden")


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
        fail_finance_reconciliation()
    if not payload or len(payload) > _MAX_CANONICAL_BYTES:
        fail_finance_reconciliation()
    return payload


def _digest(value: object) -> Sha256Digest:
    return Sha256Digest(hashlib.sha256(_canonical_bytes(value)).hexdigest())


def _sha(value: object) -> Sha256Digest:
    if type(value) is not Sha256Digest or _SHA256.fullmatch(value.value) is None:
        fail_finance_reconciliation()
    return Sha256Digest(value.value)


def _uuid7(value: object) -> UUID:
    if type(value) is not UUID or value.version != 7 or value.variant != RFC_4122:
        fail_finance_reconciliation()
    return value


def _utc_second(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
        or value.microsecond != 0
        or value.fold != 0
    ):
        fail_finance_reconciliation()
    return value.replace(tzinfo=timezone.utc)


def _instant_text(value: datetime) -> str:
    return _utc_second(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _count(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_COUNT:
        fail_finance_reconciliation()
    return value


def _decimal_text(value: Decimal) -> str:
    if type(value) is not Decimal or not value.is_finite():
        fail_finance_reconciliation()
    return format(value, "f")


def _unique_sources(values: tuple[Sha256Digest, ...]) -> tuple[Sha256Digest, ...]:
    if type(values) is not tuple or any(
        type(item) is not Sha256Digest for item in values
    ):
        fail_finance_reconciliation()
    result: list[Sha256Digest] = []
    for item in values:
        checked = _sha(item)
        if checked.value not in {source.value for source in result}:
            result.append(checked)
    return tuple(result)


class ReconciliationAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class ComparisonStatus(str, Enum):
    MATCHED = "MATCHED"
    MISMATCH = "MISMATCH"
    UNAVAILABLE = "UNAVAILABLE"


class ComparisonUnit(str, Enum):
    BOOLEAN = "BOOLEAN"
    COUNT = "COUNT"
    JPY = "JPY"
    MINUTES = "MINUTES"
    IDENTITY = "IDENTITY"


class ReconciliationUnavailableReason(str, Enum):
    PROVIDER_REPORT_UNAVAILABLE = "PROVIDER_REPORT_UNAVAILABLE"
    GENERATED_CANCELLED_TOTALS_UNAVAILABLE = "GENERATED_CANCELLED_TOTALS_UNAVAILABLE"
    DRY_RUN_COMMIT_HASH_UNAVAILABLE = "DRY_RUN_COMMIT_HASH_UNAVAILABLE"
    MISSING_INPUT = "MISSING_INPUT"
    UNVERIFIED_INPUT = "UNVERIFIED_INPUT"
    ZERO_DENOMINATOR = "ZERO_DENOMINATOR"
    COHORT_IMMATURE = "COHORT_IMMATURE"
    PERIOD_MISMATCH = "PERIOD_MISMATCH"
    PROGRAM_MISMATCH = "PROGRAM_MISMATCH"
    MISSING_ARTICLE_SLOTS = "MISSING_ARTICLE_SLOTS"
    ATTRIBUTION_UNAVAILABLE = "ATTRIBUTION_UNAVAILABLE"
    UNIT_ECONOMICS_UNAVAILABLE = "UNIT_ECONOMICS_UNAVAILABLE"


class ReconciliationExceptionCode(str, Enum):
    EXTERNAL_PROVIDER_REPORT_REQUIRED = "EXTERNAL_PROVIDER_REPORT_REQUIRED"
    GENERATED_CANCELLED_TOTALS_REQUIRED = "GENERATED_CANCELLED_TOTALS_REQUIRED"
    DRY_RUN_COMMIT_EVIDENCE_REQUIRED = "DRY_RUN_COMMIT_EVIDENCE_REQUIRED"
    MEASUREMENT_INPUT_UNAVAILABLE = "MEASUREMENT_INPUT_UNAVAILABLE"
    RECONCILIATION_MISMATCH = "RECONCILIATION_MISMATCH"
    BROKEN_LINK_OBSERVED = "BROKEN_LINK_OBSERVED"


class ExceptionSeverity(str, Enum):
    EXTERNAL_BLOCKER = "EXTERNAL_BLOCKER"
    DATA_QUALITY = "DATA_QUALITY"


class LearningAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class LearningCandidateType(str, Enum):
    BROKEN_LINK_REPAIR_REVIEW = "BROKEN_LINK_REPAIR_REVIEW"
    SEARCH_INTENT_ALIGNMENT_REVIEW = "SEARCH_INTENT_ALIGNMENT_REVIEW"
    PURCHASE_DECISION_BRIDGE_REVIEW = "PURCHASE_DECISION_BRIDGE_REVIEW"


class LearningReviewScope(str, Enum):
    LINK_INTEGRITY = "LINK_INTEGRITY"
    SEARCH_INTENT_AND_RESULT_COPY = "SEARCH_INTENT_AND_RESULT_COPY"
    CONDITION_CONCLUSION_AND_PRODUCT_CONTEXT = (
        "CONDITION_CONCLUSION_AND_PRODUCT_CONTEXT"
    )


class LearningReviewPriority(str, Enum):
    IMMEDIATE_INTEGRITY_REVIEW = "IMMEDIATE_INTEGRITY_REVIEW"
    EDITORIAL_REVIEW = "EDITORIAL_REVIEW"


@dataclass(frozen=True, slots=True, repr=False)
class FinanceReconciliationRunRequest(_Redacted):
    run_id: UUID
    requested_at: datetime
    unit_economics_request: UnitEconomicsRunRequest
    unit_economics_result: UnitEconomicsRunResult
    input_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.unit_economics_request) is not UnitEconomicsRunRequest
            or type(self.unit_economics_result) is not UnitEconomicsRunResult
        ):
            fail_finance_reconciliation()
        object.__setattr__(self, "run_id", _uuid7(self.run_id))
        object.__setattr__(self, "requested_at", _utc_second(self.requested_at))
        object.__setattr__(self, "input_sha256", _digest(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "method_version": METHOD_VERSION,
            "profile": PROFILE,
            "requested_at": _instant_text(self.requested_at),
            "run_id": str(self.run_id),
            "unit_economics_input_sha256": (
                self.unit_economics_request.input_sha256.value
            ),
            "unit_economics_result_sha256": (
                self.unit_economics_result.result_sha256.value
            ),
        }

    def canonical_bytes(self) -> bytes:
        payload = self._payload()
        payload["input_sha256"] = self.input_sha256.value
        return _canonical_bytes(payload)


@dataclass(frozen=True, slots=True, repr=False)
class ReconciliationComparison(_Redacted):
    dimension: str
    status: ComparisonStatus
    unavailable_reason: ReconciliationUnavailableReason | None
    left_value: str | int | None
    right_value: str | int | None
    unit: ComparisonUnit
    source_sha256s: tuple[Sha256Digest, ...]

    def __post_init__(self) -> None:
        if (
            self.dimension not in RECONCILIATION_DIMENSIONS
            or type(self.status) is not ComparisonStatus
            or type(self.unit) is not ComparisonUnit
            or (self.left_value is not None and type(self.left_value) not in {str, int})
            or (
                self.right_value is not None
                and type(self.right_value) not in {str, int}
            )
        ):
            fail_finance_reconciliation()
        object.__setattr__(self, "source_sha256s", _unique_sources(self.source_sha256s))
        if self.status is ComparisonStatus.UNAVAILABLE:
            if (
                type(self.unavailable_reason) is not ReconciliationUnavailableReason
                or self.left_value is not None
                or self.right_value is not None
                or self.source_sha256s
            ):
                fail_finance_reconciliation()
        elif (
            self.unavailable_reason is not None
            or self.left_value is None
            or self.right_value is None
            or not self.source_sha256s
            or (self.status is ComparisonStatus.MATCHED)
            != (self.left_value == self.right_value)
        ):
            fail_finance_reconciliation()

    def payload(self) -> dict[str, object]:
        return {
            "dimension": self.dimension,
            "left_value": self.left_value,
            "right_value": self.right_value,
            "source_sha256s": [item.value for item in self.source_sha256s],
            "status": self.status.value,
            "unavailable_reason": (
                None
                if self.unavailable_reason is None
                else self.unavailable_reason.value
            ),
            "unit": self.unit.value,
        }


@dataclass(frozen=True, slots=True, repr=False)
class ReconciliationException(_Redacted):
    code: ReconciliationExceptionCode
    severity: ExceptionSeverity
    dimension: str
    article: ContractArticle | None

    def __post_init__(self) -> None:
        if (
            type(self.code) is not ReconciliationExceptionCode
            or type(self.severity) is not ExceptionSeverity
            or self.dimension not in (*RECONCILIATION_DIMENSIONS, "broken_links")
            or (self.article is not None and type(self.article) is not ContractArticle)
        ):
            fail_finance_reconciliation()

    def payload(self) -> dict[str, object]:
        return {
            "article": None if self.article is None else self.article.payload(),
            "code": self.code.value,
            "dimension": self.dimension,
            "raw_detail_included": False,
            "severity": self.severity.value,
        }


@dataclass(frozen=True, slots=True, repr=False)
class CandidateSignals(_Redacted):
    """Closed non-finance input accepted by the candidate rules."""

    article: ContractArticle
    search_impressions: MeasurementValue
    search_clicks: MeasurementValue
    article_views: MeasurementValue
    affiliate_clicks: MeasurementValue
    broken_links: MeasurementValue

    def __post_init__(self) -> None:
        if type(self.article) is not ContractArticle or any(
            type(getattr(self, name)) is not MeasurementValue
            for name in CANDIDATE_SIGNAL_NAMES
        ):
            fail_finance_reconciliation()

    @property
    def available(self) -> bool:
        return all(getattr(self, name).observed for name in CANDIDATE_SIGNAL_NAMES)


@dataclass(frozen=True, slots=True, repr=False)
class LearningCandidate(_Redacted):
    candidate_id: str
    candidate_type: LearningCandidateType
    priority: LearningReviewPriority
    review_scope: LearningReviewScope
    article: ContractArticle
    evidence_metric_names: tuple[str, ...]
    evidence_source_sha256s: tuple[Sha256Digest, ...]

    def __post_init__(self) -> None:
        expected_id = (
            f"ST1305-CANDIDATE-{self.article.slot:02d}-{self.candidate_type.value}"
            if type(self.article) is ContractArticle
            and type(self.candidate_type) is LearningCandidateType
            else ""
        )
        if (
            self.candidate_id != expected_id
            or type(self.priority) is not LearningReviewPriority
            or type(self.review_scope) is not LearningReviewScope
            or type(self.evidence_metric_names) is not tuple
            or not self.evidence_metric_names
            or any(
                name not in CANDIDATE_SIGNAL_NAMES
                for name in self.evidence_metric_names
            )
            or len(set(self.evidence_metric_names)) != len(self.evidence_metric_names)
        ):
            fail_finance_reconciliation()
        object.__setattr__(
            self,
            "evidence_source_sha256s",
            _unique_sources(self.evidence_source_sha256s),
        )
        if not self.evidence_source_sha256s:
            fail_finance_reconciliation()

    def payload(self) -> dict[str, object]:
        return {
            "article": self.article.payload(),
            "candidate_id": self.candidate_id,
            "candidate_type": self.candidate_type.value,
            "evidence_metric_names": list(self.evidence_metric_names),
            "evidence_source_sha256s": [
                item.value for item in self.evidence_source_sha256s
            ],
            "finance_signal_used": False,
            "mutation_authority": {
                "article_html": False,
                "cta": False,
                "product_selection": False,
                "publication_snapshot": False,
                "recommendation_order": False,
            },
            "priority": self.priority.value,
            "review_scope": self.review_scope.value,
            "selection_basis": "NON_FINANCE_MEASUREMENT_ALLOWLIST_ONLY",
        }


@dataclass(frozen=True, slots=True, repr=False)
class FinanceReconciliationBatchTotals(_Redacted):
    provider_fact_count: int
    attribution_allocation_count: int
    direct_allocation_count: int
    estimated_allocation_count: int
    unattributed_allocation_count: int
    cost_observation_count: int
    provider_confirmed_reward_jpy: JpyAmount
    canonical_confirmed_reward_jpy: JpyAmount
    direct_confirmed_reward_jpy: JpyAmount
    estimated_confirmed_reward_jpy: JpyAmount
    unattributed_confirmed_reward_jpy: JpyAmount
    incremental_external_cost_jpy: Decimal | None
    human_labor_cost_jpy: Decimal | None
    work_minutes: int | None
    comparison_count: int
    exception_count: int
    learning_candidate_count: int

    def __post_init__(self) -> None:
        count_names = (
            "provider_fact_count",
            "attribution_allocation_count",
            "direct_allocation_count",
            "estimated_allocation_count",
            "unattributed_allocation_count",
            "cost_observation_count",
            "comparison_count",
            "exception_count",
            "learning_candidate_count",
        )
        if any(
            _count(getattr(self, name)) != getattr(self, name) for name in count_names
        ):
            fail_finance_reconciliation()
        amounts = (
            self.provider_confirmed_reward_jpy,
            self.canonical_confirmed_reward_jpy,
            self.direct_confirmed_reward_jpy,
            self.estimated_confirmed_reward_jpy,
            self.unattributed_confirmed_reward_jpy,
        )
        if any(type(item) is not JpyAmount for item in amounts):
            fail_finance_reconciliation()
        if (
            self.provider_confirmed_reward_jpy != self.canonical_confirmed_reward_jpy
            or self.direct_confirmed_reward_jpy.value
            + self.estimated_confirmed_reward_jpy.value
            + self.unattributed_confirmed_reward_jpy.value
            != self.provider_confirmed_reward_jpy.value
        ):
            fail_finance_reconciliation()
        for value in (self.incremental_external_cost_jpy, self.human_labor_cost_jpy):
            if value is not None and (
                type(value) is not Decimal or not value.is_finite() or value < 0
            ):
                fail_finance_reconciliation()
        if self.work_minutes is not None:
            _count(self.work_minutes)

    def payload(self) -> dict[str, object]:
        return {
            "amount_totals": {
                "canonical": {
                    "cancelled_jpy": {
                        "availability": "UNAVAILABLE",
                        "unavailable_reason": (
                            "GENERATED_CANCELLED_TOTALS_UNAVAILABLE"
                        ),
                        "value": None,
                    },
                    "confirmed_jpy": {
                        "availability": "AVAILABLE",
                        "unavailable_reason": None,
                        "value": self.canonical_confirmed_reward_jpy.canonical_text,
                    },
                    "generated_jpy": {
                        "availability": "UNAVAILABLE",
                        "unavailable_reason": (
                            "GENERATED_CANCELLED_TOTALS_UNAVAILABLE"
                        ),
                        "value": None,
                    },
                },
                "provider": {
                    "cancelled_jpy": {
                        "availability": "UNAVAILABLE",
                        "unavailable_reason": (
                            "GENERATED_CANCELLED_TOTALS_UNAVAILABLE"
                        ),
                        "value": None,
                    },
                    "confirmed_jpy": {
                        "availability": "AVAILABLE",
                        "unavailable_reason": None,
                        "value": self.provider_confirmed_reward_jpy.canonical_text,
                    },
                    "generated_jpy": {
                        "availability": "UNAVAILABLE",
                        "unavailable_reason": (
                            "GENERATED_CANCELLED_TOTALS_UNAVAILABLE"
                        ),
                        "value": None,
                    },
                },
            },
            "attribution_totals": {
                "direct_confirmed_reward_jpy": (
                    self.direct_confirmed_reward_jpy.canonical_text
                ),
                "estimated_confirmed_reward_jpy": (
                    self.estimated_confirmed_reward_jpy.canonical_text
                ),
                "unattributed_confirmed_reward_jpy": (
                    self.unattributed_confirmed_reward_jpy.canonical_text
                ),
                "unattributed_reward_allocated_to_articles": False,
            },
            "comparison_count": self.comparison_count,
            "cost_totals": {
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
                "work_minutes": self.work_minutes,
            },
            "exception_count": self.exception_count,
            "learning_candidate_count": self.learning_candidate_count,
            "row_counts": {
                "attribution_allocation_count": self.attribution_allocation_count,
                "cost_observation_count": self.cost_observation_count,
                "direct_allocation_count": self.direct_allocation_count,
                "estimated_allocation_count": self.estimated_allocation_count,
                "provider_fact_count": self.provider_fact_count,
                "provider_report_row_count": {
                    "availability": "UNAVAILABLE",
                    "unavailable_reason": "PROVIDER_REPORT_UNAVAILABLE",
                    "value": None,
                },
                "unattributed_allocation_count": self.unattributed_allocation_count,
            },
        }


@dataclass(frozen=True, slots=True, repr=False)
class FinanceReconciliationAuthority(_Redacted):
    provider_call: bool = False
    network: bool = False
    credential_access: bool = False
    persistence: bool = False
    database: bool = False
    public_projection: bool = False
    publication: bool = False
    editorial_mutation: bool = False
    article_html_mutation: bool = False
    cta_mutation: bool = False
    product_selection_mutation: bool = False
    recommendation_order_mutation: bool = False
    publication_snapshot_mutation: bool = False
    approval: bool = False
    staging: bool = False
    release: bool = False
    production: bool = False

    def __post_init__(self) -> None:
        if any(getattr(self, name) is not False for name in self.__slots__):
            fail_finance_reconciliation()

    def payload(self) -> dict[str, object]:
        return {name: False for name in self.__slots__}


@dataclass(frozen=True, slots=True, repr=False)
class FinanceReconciliationRunResult(_Redacted):
    result_sha256: Sha256Digest
    run_id: UUID
    input_sha256: Sha256Digest
    method_version: str
    availability: ReconciliationAvailability
    comparisons: tuple[ReconciliationComparison, ...]
    exceptions: tuple[ReconciliationException, ...]
    totals: FinanceReconciliationBatchTotals
    measurement_metrics: tuple[DerivedMetric, ...]
    unit_economics_metrics: tuple[UnitEconomicsMetric, ...]
    learning_availability: LearningAvailability
    learning_unavailable_reason: ReconciliationUnavailableReason | None
    learning_candidates: tuple[LearningCandidate, ...]
    authority: FinanceReconciliationAuthority

    def __post_init__(self) -> None:
        if (
            self.method_version != METHOD_VERSION
            or type(self.availability) is not ReconciliationAvailability
            or type(self.comparisons) is not tuple
            or any(
                type(item) is not ReconciliationComparison for item in self.comparisons
            )
            or tuple(item.dimension for item in self.comparisons)
            != RECONCILIATION_DIMENSIONS
            or type(self.exceptions) is not tuple
            or any(
                type(item) is not ReconciliationException for item in self.exceptions
            )
            or type(self.totals) is not FinanceReconciliationBatchTotals
            or type(self.measurement_metrics) is not tuple
            or any(type(item) is not DerivedMetric for item in self.measurement_metrics)
            or tuple(item.name for item in self.measurement_metrics) != DERIVED_METRICS
            or type(self.unit_economics_metrics) is not tuple
            or any(
                type(item) is not UnitEconomicsMetric
                for item in self.unit_economics_metrics
            )
            or tuple(item.name for item in self.unit_economics_metrics)
            != UNIT_ECONOMICS_METRIC_NAMES
            or type(self.learning_availability) is not LearningAvailability
            or type(self.learning_candidates) is not tuple
            or any(
                type(item) is not LearningCandidate for item in self.learning_candidates
            )
            or type(self.authority) is not FinanceReconciliationAuthority
        ):
            fail_finance_reconciliation()
        object.__setattr__(self, "result_sha256", _sha(self.result_sha256))
        object.__setattr__(self, "run_id", _uuid7(self.run_id))
        object.__setattr__(self, "input_sha256", _sha(self.input_sha256))
        mismatch = any(
            item.status is ComparisonStatus.MISMATCH for item in self.comparisons
        )
        unavailable = any(
            item.status is ComparisonStatus.UNAVAILABLE for item in self.comparisons
        )
        expected_availability = (
            ReconciliationAvailability.UNAVAILABLE
            if mismatch
            else (
                ReconciliationAvailability.PARTIAL
                if unavailable
                else ReconciliationAvailability.AVAILABLE
            )
        )
        if self.availability is not expected_availability:
            fail_finance_reconciliation()
        if self.learning_availability is LearningAvailability.AVAILABLE:
            if self.learning_unavailable_reason is not None:
                fail_finance_reconciliation()
        elif (
            type(self.learning_unavailable_reason)
            is not ReconciliationUnavailableReason
            or self.learning_candidates
        ):
            fail_finance_reconciliation()
        if (
            self.totals.comparison_count != len(self.comparisons)
            or self.totals.exception_count != len(self.exceptions)
            or self.totals.learning_candidate_count != len(self.learning_candidates)
        ):
            fail_finance_reconciliation()

    def payload(self, *, include_result_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "authority": self.authority.payload(),
            "availability": self.availability.value,
            "comparisons": [item.payload() for item in self.comparisons],
            "exceptions": [item.payload() for item in self.exceptions],
            "input_sha256": self.input_sha256.value,
            "learning_report": {
                "availability": self.learning_availability.value,
                "candidates": [item.payload() for item in self.learning_candidates],
                "finance_signals_excluded": list(
                    FINANCE_SIGNALS_EXCLUDED_FROM_CANDIDATES
                ),
                "output_kind": "REVIEW_CANDIDATES_ONLY",
                "unavailable_reason": (
                    None
                    if self.learning_unavailable_reason is None
                    else self.learning_unavailable_reason.value
                ),
            },
            "method_version": self.method_version,
            "metric_snapshot": {
                "measurement_metrics": [
                    item.payload() for item in self.measurement_metrics
                ],
                "unit_economics_metrics": [
                    item.payload() for item in self.unit_economics_metrics
                ],
            },
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
            "run_id": str(self.run_id),
            "totals": self.totals.payload(),
        }
        if include_result_hash:
            payload["result_sha256"] = self.result_sha256.value
        return payload

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.payload())


def _comparison(
    dimension: str,
    left: str | int,
    right: str | int,
    unit: ComparisonUnit,
    sources: tuple[Sha256Digest, ...],
) -> ReconciliationComparison:
    return ReconciliationComparison(
        dimension=dimension,
        status=(
            ComparisonStatus.MATCHED if left == right else ComparisonStatus.MISMATCH
        ),
        unavailable_reason=None,
        left_value=left,
        right_value=right,
        unit=unit,
        source_sha256s=sources,
    )


def _unavailable_comparison(
    dimension: str,
    reason: ReconciliationUnavailableReason,
    unit: ComparisonUnit,
) -> ReconciliationComparison:
    return ReconciliationComparison(
        dimension=dimension,
        status=ComparisonStatus.UNAVAILABLE,
        unavailable_reason=reason,
        left_value=None,
        right_value=None,
        unit=unit,
        source_sha256s=(),
    )


def _measurement_reason(
    request: FinanceReconciliationRunRequest,
) -> ReconciliationUnavailableReason | None:
    unit_request = request.unit_economics_request
    attribution_request = unit_request.attribution_request
    measurements = attribution_request.article_measurements
    if (
        len(measurements) != 5
        or tuple(item.article.slot for item in measurements) != (1, 2, 3, 4, 5)
        or len(unit_request.cost_observations) != 5
        or tuple(item.article.slot for item in unit_request.cost_observations)
        != (1, 2, 3, 4, 5)
    ):
        return ReconciliationUnavailableReason.MISSING_ARTICLE_SLOTS
    if (
        attribution_request.program != PROGRAM
        or any(item.program != attribution_request.program for item in measurements)
        or any(
            item.program != attribution_request.program
            for item in unit_request.cost_observations
        )
    ):
        return ReconciliationUnavailableReason.PROGRAM_MISMATCH
    if any(item.period != attribution_request.period for item in measurements) or any(
        item.period != attribution_request.period
        for item in unit_request.cost_observations
    ):
        return ReconciliationUnavailableReason.PERIOD_MISMATCH
    if any(
        item.verification.state is VerificationState.UNAVAILABLE
        for item in measurements
    ) or any(
        item.verification_state is VerificationState.UNAVAILABLE
        for item in unit_request.cost_observations
    ):
        return ReconciliationUnavailableReason.MISSING_INPUT
    if any(
        item.verification.state is not VerificationState.VERIFIED
        for item in measurements
    ) or any(
        item.verification_state is not VerificationState.VERIFIED
        for item in unit_request.cost_observations
    ):
        return ReconciliationUnavailableReason.UNVERIFIED_INPUT
    if any(
        item.cohort.state is not CohortMaturity.MATURE for item in measurements
    ) or any(
        item.cohort_state is not CohortMaturity.MATURE
        for item in unit_request.cost_observations
    ):
        return ReconciliationUnavailableReason.COHORT_IMMATURE
    if (
        attribution_request.program_measurement.program != attribution_request.program
        or attribution_request.program_measurement.period != attribution_request.period
    ):
        return (
            ReconciliationUnavailableReason.PROGRAM_MISMATCH
            if attribution_request.program_measurement.program
            != attribution_request.program
            else ReconciliationUnavailableReason.PERIOD_MISMATCH
        )
    if (
        attribution_request.program_measurement.verification.state
        is not VerificationState.VERIFIED
    ):
        return (
            ReconciliationUnavailableReason.MISSING_INPUT
            if attribution_request.program_measurement.verification.state
            is VerificationState.UNAVAILABLE
            else ReconciliationUnavailableReason.UNVERIFIED_INPUT
        )
    if (
        attribution_request.program_measurement.cohort.state
        is not CohortMaturity.MATURE
    ):
        return ReconciliationUnavailableReason.COHORT_IMMATURE
    return None


def _observed_total(
    values: tuple[MeasurementValue, ...],
) -> tuple[
    int | None, ReconciliationUnavailableReason | None, tuple[Sha256Digest, ...]
]:
    if any(item.state is MeasurementValueState.UNVERIFIED for item in values):
        return None, ReconciliationUnavailableReason.UNVERIFIED_INPUT, ()
    if any(not item.observed for item in values):
        return None, ReconciliationUnavailableReason.MISSING_INPUT, ()
    total = 0
    sources: list[Sha256Digest] = []
    for item in values:
        if type(item.value) is not int or item.input_sha256 is None:
            fail_finance_reconciliation()
        total += item.value
        if item.input_sha256.value not in {source.value for source in sources}:
            sources.append(item.input_sha256)
    return total, None, tuple(sources)


def candidate_signals(
    measurements: tuple[ArticleMeasurement, ...],
) -> tuple[CandidateSignals, ...]:
    """Project the only fields that may influence learning candidates."""

    if type(measurements) is not tuple or any(
        type(item) is not ArticleMeasurement for item in measurements
    ):
        fail_finance_reconciliation()
    return tuple(
        CandidateSignals(
            article=item.article,
            search_impressions=item.metric_map["search_impressions"],
            search_clicks=item.metric_map["search_clicks"],
            article_views=item.metric_map["article_views"],
            affiliate_clicks=item.metric_map["affiliate_clicks"],
            broken_links=item.metric_map["broken_links"],
        )
        for item in measurements
    )


def _signal_sources(
    signal: CandidateSignals, names: tuple[str, ...]
) -> tuple[Sha256Digest, ...]:
    result: list[Sha256Digest] = []
    for name in names:
        value = getattr(signal, name)
        if type(value) is not MeasurementValue or value.input_sha256 is None:
            fail_finance_reconciliation()
        if value.input_sha256.value not in {item.value for item in result}:
            result.append(value.input_sha256)
    return tuple(result)


def _signal_int(signal: CandidateSignals, name: str) -> int:
    value = getattr(signal, name)
    if (
        type(value) is not MeasurementValue
        or not value.observed
        or type(value.value) is not int
    ):
        fail_finance_reconciliation()
    return value.value


def build_learning_candidates(
    signals: tuple[CandidateSignals, ...],
) -> tuple[LearningCandidate, ...]:
    """Return review candidates from non-finance observations only."""

    if (
        type(signals) is not tuple
        or tuple(item.article.slot for item in signals) != (1, 2, 3, 4, 5)
        or any(
            type(item) is not CandidateSignals or not item.available for item in signals
        )
    ):
        fail_finance_reconciliation()
    candidates: list[LearningCandidate] = []
    rules: tuple[
        tuple[
            LearningCandidateType,
            LearningReviewPriority,
            LearningReviewScope,
            tuple[str, ...],
            Callable[[CandidateSignals], bool],
        ],
        ...,
    ] = (
        (
            LearningCandidateType.BROKEN_LINK_REPAIR_REVIEW,
            LearningReviewPriority.IMMEDIATE_INTEGRITY_REVIEW,
            LearningReviewScope.LINK_INTEGRITY,
            ("broken_links",),
            lambda item: _signal_int(item, "broken_links") > 0,
        ),
        (
            LearningCandidateType.SEARCH_INTENT_ALIGNMENT_REVIEW,
            LearningReviewPriority.EDITORIAL_REVIEW,
            LearningReviewScope.SEARCH_INTENT_AND_RESULT_COPY,
            ("search_impressions", "search_clicks"),
            lambda item: (
                _signal_int(item, "search_impressions") > 0
                and _signal_int(item, "search_clicks") == 0
            ),
        ),
        (
            LearningCandidateType.PURCHASE_DECISION_BRIDGE_REVIEW,
            LearningReviewPriority.EDITORIAL_REVIEW,
            LearningReviewScope.CONDITION_CONCLUSION_AND_PRODUCT_CONTEXT,
            ("article_views", "affiliate_clicks"),
            lambda item: (
                _signal_int(item, "article_views") > 0
                and _signal_int(item, "affiliate_clicks") == 0
            ),
        ),
    )
    for candidate_type, priority, scope, evidence_names, predicate in rules:
        for signal in signals:
            if predicate(signal):
                candidates.append(
                    LearningCandidate(
                        candidate_id=(
                            f"ST1305-CANDIDATE-{signal.article.slot:02d}-"
                            f"{candidate_type.value}"
                        ),
                        candidate_type=candidate_type,
                        priority=priority,
                        review_scope=scope,
                        article=signal.article,
                        evidence_metric_names=evidence_names,
                        evidence_source_sha256s=_signal_sources(signal, evidence_names),
                    )
                )
    return tuple(candidates)


def _measurement_reason_from_metric(
    reason: MeasurementUnavailableReason | None,
) -> ReconciliationUnavailableReason:
    if reason is None:
        return ReconciliationUnavailableReason.MISSING_INPUT
    return {
        MeasurementUnavailableReason.MISSING_INPUT: (
            ReconciliationUnavailableReason.MISSING_INPUT
        ),
        MeasurementUnavailableReason.UNVERIFIED_INPUT: (
            ReconciliationUnavailableReason.UNVERIFIED_INPUT
        ),
        MeasurementUnavailableReason.ZERO_DENOMINATOR: (
            ReconciliationUnavailableReason.ZERO_DENOMINATOR
        ),
        MeasurementUnavailableReason.COHORT_IMMATURE: (
            ReconciliationUnavailableReason.COHORT_IMMATURE
        ),
        MeasurementUnavailableReason.PERIOD_MISMATCH: (
            ReconciliationUnavailableReason.PERIOD_MISMATCH
        ),
        MeasurementUnavailableReason.PROGRAM_MISMATCH: (
            ReconciliationUnavailableReason.PROGRAM_MISMATCH
        ),
        MeasurementUnavailableReason.MISSING_ARTICLE_SLOTS: (
            ReconciliationUnavailableReason.MISSING_ARTICLE_SLOTS
        ),
    }[reason]


def build_finance_reconciliation(
    request: FinanceReconciliationRunRequest,
) -> FinanceReconciliationRunResult:
    """Build one immutable internal reconciliation and learning report."""

    if type(request) is not FinanceReconciliationRunRequest:
        fail_finance_reconciliation()
    if request.input_sha256 != _digest(request._payload()):  # noqa: SLF001
        fail_finance_reconciliation(
            FinanceReconciliationFailureCode.INPUT_HASH_MISMATCH
        )
    expected_unit = build_unit_economics(request.unit_economics_request)
    if (
        request.unit_economics_result != expected_unit
        or request.unit_economics_result.canonical_bytes()
        != expected_unit.canonical_bytes()
    ):
        fail_finance_reconciliation(
            FinanceReconciliationFailureCode.DEPENDENCY_RESULT_MISMATCH
        )
    unit_request = request.unit_economics_request
    attribution_request = unit_request.attribution_request
    attribution_result = build_attribution_run(attribution_request)
    if (
        unit_request.attribution_result != attribution_result
        or unit_request.attribution_result.canonical_bytes()
        != attribution_result.canonical_bytes()
    ):
        fail_finance_reconciliation(
            FinanceReconciliationFailureCode.DEPENDENCY_RESULT_MISMATCH
        )
    unit_result = request.unit_economics_result
    measurement_reason = _measurement_reason(request)
    if measurement_reason is None:
        measurement_reason = next(
            (
                _measurement_reason_from_metric(metric.unavailable_reason)
                for metric in attribution_result.measurement_evaluation.metrics
                if metric.unavailable_reason is not None
            ),
            None,
        )
    source_pair = (attribution_result.input_sha256, unit_result.input_sha256)
    comparisons: list[ReconciliationComparison] = [
        _unavailable_comparison(
            "file_hash_uniqueness",
            ReconciliationUnavailableReason.PROVIDER_REPORT_UNAVAILABLE,
            ComparisonUnit.IDENTITY,
        ),
        _unavailable_comparison(
            "row_count",
            ReconciliationUnavailableReason.PROVIDER_REPORT_UNAVAILABLE,
            ComparisonUnit.COUNT,
        ),
        _unavailable_comparison(
            "generated_confirmed_cancelled_amount_totals",
            ReconciliationUnavailableReason.GENERATED_CANCELLED_TOTALS_UNAVAILABLE,
            ComparisonUnit.JPY,
        ),
        _comparison(
            "currency",
            "JPY",
            "JPY",
            ComparisonUnit.IDENTITY,
            source_pair,
        ),
        _comparison(
            "period",
            json.dumps(attribution_request.period.payload(), sort_keys=True),
            json.dumps(
                unit_request.cost_observations[0].period.payload(), sort_keys=True
            ),
            ComparisonUnit.IDENTITY,
            source_pair,
        ),
        _comparison(
            "duplicate_provider_row",
            len(attribution_request.provider_facts),
            len(
                {item.fact_sha256.value for item in attribution_request.provider_facts}
            ),
            ComparisonUnit.COUNT,
            (attribution_result.input_sha256,),
        ),
        _unavailable_comparison(
            "dry_run_to_commit_hash_equality",
            ReconciliationUnavailableReason.DRY_RUN_COMMIT_HASH_UNAVAILABLE,
            ComparisonUnit.IDENTITY,
        ),
        _comparison(
            "provider_to_attribution_confirmed_total",
            attribution_result.totals.provider_confirmed_reward_jpy.canonical_text,
            (
                attribution_result.totals.direct_confirmed_reward_jpy.value
                + attribution_result.totals.estimated_confirmed_reward_jpy.value
                + attribution_result.totals.unattributed_confirmed_reward_jpy.value
            )
            .to_integral_value()
            .to_eng_string(),
            ComparisonUnit.JPY,
            (attribution_result.input_sha256,),
        ),
        _comparison(
            "attribution_to_unit_economics_confirmed_total",
            attribution_result.totals.provider_confirmed_reward_jpy.canonical_text,
            unit_result.totals.provider_confirmed_reward_jpy.canonical_text,
            ComparisonUnit.JPY,
            source_pair,
        ),
    ]

    direct_values = tuple(
        item.metric_map["direct_confirmed_reward_jpy"]
        for item in attribution_request.article_measurements
    )
    direct_total, direct_reason, direct_sources = _observed_total(direct_values)
    if direct_reason is not None or direct_total is None:
        comparisons.append(
            _unavailable_comparison(
                "direct_measurement_to_attribution_total",
                direct_reason or ReconciliationUnavailableReason.MISSING_INPUT,
                ComparisonUnit.JPY,
            )
        )
    else:
        comparisons.append(
            _comparison(
                "direct_measurement_to_attribution_total",
                direct_total,
                int(attribution_result.totals.direct_confirmed_reward_jpy.value),
                ComparisonUnit.JPY,
                (*direct_sources, attribution_result.input_sha256),
            )
        )
    unattributed_value = (
        attribution_request.program_measurement.unattributed_confirmed_reward_jpy
    )
    unattributed_total, unattributed_reason, unattributed_sources = _observed_total(
        (unattributed_value,)
    )
    if unattributed_reason is not None or unattributed_total is None:
        comparisons.append(
            _unavailable_comparison(
                "unattributed_measurement_to_attribution_total",
                unattributed_reason or ReconciliationUnavailableReason.MISSING_INPUT,
                ComparisonUnit.JPY,
            )
        )
    else:
        comparisons.append(
            _comparison(
                "unattributed_measurement_to_attribution_total",
                unattributed_total,
                int(attribution_result.totals.unattributed_confirmed_reward_jpy.value),
                ComparisonUnit.JPY,
                (*unattributed_sources, attribution_result.input_sha256),
            )
        )
    for dimension, metric_name, unit in (
        (
            "work_minutes_measurement_to_cost_total",
            "work_minutes",
            ComparisonUnit.MINUTES,
        ),
        (
            "incremental_cost_measurement_to_cost_total",
            "incremental_cost_jpy",
            ComparisonUnit.JPY,
        ),
    ):
        measurement_total, measurement_unavailable, measurement_sources = (
            _observed_total(
                tuple(
                    item.metric_map[metric_name]
                    for item in attribution_request.article_measurements
                )
            )
        )
        cost_total, cost_unavailable, cost_sources = _observed_total(
            tuple(
                item.metric_map[metric_name] for item in unit_request.cost_observations
            )
        )
        unavailable_reason = measurement_unavailable or cost_unavailable
        if (
            unavailable_reason is not None
            or measurement_total is None
            or cost_total is None
        ):
            comparisons.append(
                _unavailable_comparison(
                    dimension,
                    unavailable_reason or ReconciliationUnavailableReason.MISSING_INPUT,
                    unit,
                )
            )
        else:
            comparisons.append(
                _comparison(
                    dimension,
                    measurement_total,
                    cost_total,
                    unit,
                    (*measurement_sources, *cost_sources),
                )
            )
    if measurement_reason is None:
        comparisons.append(
            _comparison(
                "measurement_readiness",
                "VERIFIED_SAME_PROGRAM_PERIOD_MATURE_FIVE_SLOTS",
                "VERIFIED_SAME_PROGRAM_PERIOD_MATURE_FIVE_SLOTS",
                ComparisonUnit.IDENTITY,
                source_pair,
            )
        )
    else:
        comparisons.append(
            _unavailable_comparison(
                "measurement_readiness",
                measurement_reason,
                ComparisonUnit.IDENTITY,
            )
        )

    exceptions: list[ReconciliationException] = [
        ReconciliationException(
            code=ReconciliationExceptionCode.EXTERNAL_PROVIDER_REPORT_REQUIRED,
            severity=ExceptionSeverity.EXTERNAL_BLOCKER,
            dimension="file_hash_uniqueness",
            article=None,
        ),
        ReconciliationException(
            code=ReconciliationExceptionCode.GENERATED_CANCELLED_TOTALS_REQUIRED,
            severity=ExceptionSeverity.EXTERNAL_BLOCKER,
            dimension="generated_confirmed_cancelled_amount_totals",
            article=None,
        ),
        ReconciliationException(
            code=ReconciliationExceptionCode.DRY_RUN_COMMIT_EVIDENCE_REQUIRED,
            severity=ExceptionSeverity.EXTERNAL_BLOCKER,
            dimension="dry_run_to_commit_hash_equality",
            article=None,
        ),
    ]
    if measurement_reason is not None:
        exceptions.append(
            ReconciliationException(
                code=ReconciliationExceptionCode.MEASUREMENT_INPUT_UNAVAILABLE,
                severity=ExceptionSeverity.DATA_QUALITY,
                dimension="measurement_readiness",
                article=None,
            )
        )
    for comparison in comparisons:
        if comparison.status is ComparisonStatus.MISMATCH:
            exceptions.append(
                ReconciliationException(
                    code=ReconciliationExceptionCode.RECONCILIATION_MISMATCH,
                    severity=ExceptionSeverity.DATA_QUALITY,
                    dimension=comparison.dimension,
                    article=None,
                )
            )

    signals = candidate_signals(attribution_request.article_measurements)
    signal_unavailable = any(not item.available for item in signals)
    if measurement_reason is None and not signal_unavailable:
        learning_availability = LearningAvailability.AVAILABLE
        learning_reason = None
        candidates = build_learning_candidates(signals)
        by_slot = {item.article.slot: item for item in signals}
        for signal in signals:
            if _signal_int(signal, "broken_links") > 0:
                exceptions.append(
                    ReconciliationException(
                        code=ReconciliationExceptionCode.BROKEN_LINK_OBSERVED,
                        severity=ExceptionSeverity.DATA_QUALITY,
                        dimension="broken_links",
                        article=by_slot[signal.article.slot].article,
                    )
                )
    else:
        learning_availability = LearningAvailability.UNAVAILABLE
        learning_reason = measurement_reason or (
            ReconciliationUnavailableReason.MISSING_INPUT
        )
        candidates = ()

    comparison_tuple = tuple(comparisons)
    exception_tuple = tuple(exceptions)
    mismatch = any(
        item.status is ComparisonStatus.MISMATCH for item in comparison_tuple
    )
    unavailable = any(
        item.status is ComparisonStatus.UNAVAILABLE for item in comparison_tuple
    )
    availability = (
        ReconciliationAvailability.UNAVAILABLE
        if mismatch
        else (
            ReconciliationAvailability.PARTIAL
            if unavailable
            else ReconciliationAvailability.AVAILABLE
        )
    )
    attribution_classes = tuple(
        item.attribution_class.value for item in attribution_result.allocations
    )
    totals = FinanceReconciliationBatchTotals(
        provider_fact_count=len(attribution_request.provider_facts),
        attribution_allocation_count=len(attribution_result.allocations),
        direct_allocation_count=attribution_classes.count("DIRECT"),
        estimated_allocation_count=attribution_classes.count("ESTIMATED"),
        unattributed_allocation_count=attribution_classes.count("UNATTRIBUTED"),
        cost_observation_count=len(unit_request.cost_observations),
        provider_confirmed_reward_jpy=(
            attribution_result.totals.provider_confirmed_reward_jpy
        ),
        canonical_confirmed_reward_jpy=(
            unit_result.totals.provider_confirmed_reward_jpy
        ),
        direct_confirmed_reward_jpy=(
            attribution_result.totals.direct_confirmed_reward_jpy
        ),
        estimated_confirmed_reward_jpy=(
            attribution_result.totals.estimated_confirmed_reward_jpy
        ),
        unattributed_confirmed_reward_jpy=(
            attribution_result.totals.unattributed_confirmed_reward_jpy
        ),
        incremental_external_cost_jpy=(
            unit_result.totals.incremental_external_cost_jpy
        ),
        human_labor_cost_jpy=unit_result.totals.human_labor_cost_jpy,
        work_minutes=unit_result.totals.work_minutes,
        comparison_count=len(comparison_tuple),
        exception_count=len(exception_tuple),
        learning_candidate_count=len(candidates),
    )
    preliminary = FinanceReconciliationRunResult(
        result_sha256=Sha256Digest("0" * 64),
        run_id=request.run_id,
        input_sha256=request.input_sha256,
        method_version=METHOD_VERSION,
        availability=availability,
        comparisons=comparison_tuple,
        exceptions=exception_tuple,
        totals=totals,
        measurement_metrics=attribution_result.measurement_evaluation.metrics,
        unit_economics_metrics=unit_result.metrics,
        learning_availability=learning_availability,
        learning_unavailable_reason=learning_reason,
        learning_candidates=candidates,
        authority=FinanceReconciliationAuthority(),
    )
    result_hash = _digest(preliminary.payload(include_result_hash=False))
    return FinanceReconciliationRunResult(
        result_sha256=result_hash,
        run_id=preliminary.run_id,
        input_sha256=preliminary.input_sha256,
        method_version=preliminary.method_version,
        availability=preliminary.availability,
        comparisons=preliminary.comparisons,
        exceptions=preliminary.exceptions,
        totals=preliminary.totals,
        measurement_metrics=preliminary.measurement_metrics,
        unit_economics_metrics=preliminary.unit_economics_metrics,
        learning_availability=preliminary.learning_availability,
        learning_unavailable_reason=preliminary.learning_unavailable_reason,
        learning_candidates=preliminary.learning_candidates,
        authority=preliminary.authority,
    )


__all__ = (
    "CANONICAL_RECONCILIATION_DIMENSIONS",
    "CANDIDATE_SIGNAL_NAMES",
    "DEPENDENCY_RECONCILIATION_DIMENSIONS",
    "FINANCE_SIGNALS_EXCLUDED_FROM_CANDIDATES",
    "METHOD_VERSION",
    "PROFILE",
    "RECOMMENDATION_INPUTS_EXCLUDED",
    "RECONCILIATION_DIMENSIONS",
    "CandidateSignals",
    "ComparisonStatus",
    "ComparisonUnit",
    "ExceptionSeverity",
    "FinanceReconciliationAuthority",
    "FinanceReconciliationBatchTotals",
    "FinanceReconciliationFailure",
    "FinanceReconciliationFailureCode",
    "FinanceReconciliationRunRequest",
    "FinanceReconciliationRunResult",
    "LearningAvailability",
    "LearningCandidate",
    "LearningCandidateType",
    "LearningReviewPriority",
    "LearningReviewScope",
    "ReconciliationAvailability",
    "ReconciliationComparison",
    "ReconciliationException",
    "ReconciliationExceptionCode",
    "ReconciliationUnavailableReason",
    "build_finance_reconciliation",
    "build_learning_candidates",
    "candidate_signals",
    "fail_finance_reconciliation",
)

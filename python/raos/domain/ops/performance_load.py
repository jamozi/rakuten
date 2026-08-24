"""Deterministic local-only performance/load evaluation values for ST-1604."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
import hashlib
import json
import re
from typing import Final, NoReturn
from uuid import UUID


_SAFE_ID: Final = re.compile(r"\A[A-Z0-9](?:[A-Z0-9._-]{0,62}[A-Z0-9])?\Z")
_SHA256: Final = re.compile(r"\A[0-9a-f]{64}\Z")
_MAX_SAMPLE_COUNT: Final = 100_000
_MAX_DURATION_MS: Final = 86_400_000
_MAX_MEASUREMENT_MS: Final = 86_400_000


class PerformanceLoadFailureCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    DUPLICATE_SURFACE = "DUPLICATE_SURFACE"
    SURFACE_MISMATCH = "SURFACE_MISMATCH"
    JOURNAL_MISMATCH = "JOURNAL_MISMATCH"
    RUN_ID_CONFLICT = "RUN_ID_CONFLICT"
    STORAGE_FAILED = "STORAGE_FAILED"
    PRIVATE_PATH_INVALID = "PRIVATE_PATH_INVALID"
    SCHEMA_DRIFT = "SCHEMA_DRIFT"
    TAMPER_DETECTED = "TAMPER_DETECTED"
    COMMIT_UNKNOWN = "COMMIT_UNKNOWN"


class PerformanceLoadFailure(RuntimeError):
    """Stable failure that never echoes rejected input or storage details."""

    __slots__ = ("code",)

    def __init__(self, code: PerformanceLoadFailureCode) -> None:
        self.code = code
        super().__init__(f"ST1604_{code.value}")


def fail_performance_load(code: PerformanceLoadFailureCode) -> NoReturn:
    if type(code) is not PerformanceLoadFailureCode:
        raise PerformanceLoadFailure(PerformanceLoadFailureCode.INVALID_ARGUMENT)
    raise PerformanceLoadFailure(code)


def _invalid() -> NoReturn:
    fail_performance_load(PerformanceLoadFailureCode.INVALID_ARGUMENT)


def _positive_int(value: object, *, maximum: int) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        _invalid()
    return value


def _non_negative_int(value: object, *, maximum: int) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        _invalid()
    return value


def _safe_id(value: object) -> str:
    if type(value) is not str or _SAFE_ID.fullmatch(value) is None:
        _invalid()
    return value


def _sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        _invalid()
    return value


def _exact_uuid(value: object) -> UUID:
    if type(value) is not UUID or UUID(str(value)) != value:
        _invalid()
    return value


def _canonical_utc(value: object) -> str:
    if type(value) is not str or not value.endswith("Z"):
        _invalid()
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _invalid()
    if parsed.tzinfo != UTC or parsed.microsecond != 0:
        _invalid()
    canonical = parsed.isoformat(timespec="seconds").replace("+00:00", "Z")
    if canonical != value:
        _invalid()
    return value


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except TypeError, ValueError, UnicodeError:
        _invalid()


class LoadSurface(StrEnum):
    PUBLIC = "PUBLIC"
    ADMIN = "ADMIN"
    API = "API"
    WORKER = "WORKER"


ORDERED_LOAD_SURFACES: Final = tuple(LoadSurface)


class LoadEvidenceSource(StrEnum):
    SYNTHETIC_RECORDED_FIXTURE = "SYNTHETIC_RECORDED_FIXTURE"
    RECORDED_CAPTURE = "RECORDED_CAPTURE"


class SurfaceEvaluationStatus(StrEnum):
    LOCAL_BUDGET_MET = "LOCAL_BUDGET_MET"
    LOCAL_BUDGET_BREACHED = "LOCAL_BUDGET_BREACHED"
    UNAVAILABLE = "UNAVAILABLE"


class LoadReportStatus(StrEnum):
    LOCAL_CAPACITY_DOCUMENTED = "LOCAL_CAPACITY_DOCUMENTED"
    LOCAL_BUDGET_FAILED = "LOCAL_BUDGET_FAILED"
    DATA_BLOCKED = "DATA_BLOCKED"


class CapacityClassification(StrEnum):
    SYNTHETIC_LOCAL_ONLY_NOT_PRODUCTION_CAPACITY = (
        "SYNTHETIC_LOCAL_ONLY_NOT_PRODUCTION_CAPACITY"
    )
    RECORDED_LOCAL_ONLY_NOT_PRODUCTION_CAPACITY = (
        "RECORDED_LOCAL_ONLY_NOT_PRODUCTION_CAPACITY"
    )


class MetricAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class SurfaceBudget:
    """Explicit local budget; never a Canonical SLO or Production threshold."""

    surface: LoadSurface
    concurrent_units: int
    duration_ms: int
    max_p95_duration_ms: int
    max_p99_duration_ms: int
    max_error_basis_points: int
    min_throughput_milliops_per_second: int
    max_db_connections: int
    max_queue_age_p95_ms: int | None

    def __post_init__(self) -> None:
        if type(self.surface) is not LoadSurface:
            _invalid()
        _positive_int(self.concurrent_units, maximum=10_000)
        _positive_int(self.duration_ms, maximum=_MAX_DURATION_MS)
        p95 = _positive_int(self.max_p95_duration_ms, maximum=_MAX_MEASUREMENT_MS)
        p99 = _positive_int(self.max_p99_duration_ms, maximum=_MAX_MEASUREMENT_MS)
        if p99 < p95:
            _invalid()
        _non_negative_int(self.max_error_basis_points, maximum=10_000)
        _positive_int(self.min_throughput_milliops_per_second, maximum=10**12)
        _non_negative_int(self.max_db_connections, maximum=1_000_000)
        if self.surface is LoadSurface.WORKER:
            _positive_int(self.max_queue_age_p95_ms, maximum=_MAX_MEASUREMENT_MS)
        elif self.max_queue_age_p95_ms is not None:
            _invalid()

    def as_dict(self) -> dict[str, object]:
        return {
            "budget_classification": "LOCAL_RECORDED_BUDGET_NOT_CANONICAL_SLO",
            "concurrent_units": self.concurrent_units,
            "duration_ms": self.duration_ms,
            "max_db_connections": self.max_db_connections,
            "max_error_basis_points": self.max_error_basis_points,
            "max_p95_duration_ms": self.max_p95_duration_ms,
            "max_p99_duration_ms": self.max_p99_duration_ms,
            "max_queue_age_p95_ms": self.max_queue_age_p95_ms,
            "min_throughput_milliops_per_second": (
                self.min_throughput_milliops_per_second
            ),
            "surface": self.surface.value,
        }


@dataclass(frozen=True, slots=True)
class SurfaceObservation:
    """A caller-supplied, already-recorded sample with no execution capability."""

    surface: LoadSurface
    concurrent_units: int
    duration_ms: int
    successful_operations: int
    duration_samples_ms: tuple[int, ...]
    max_db_connections: int
    queue_age_samples_ms: tuple[int, ...] | None

    def __post_init__(self) -> None:
        if type(self.surface) is not LoadSurface:
            _invalid()
        _positive_int(self.concurrent_units, maximum=10_000)
        _positive_int(self.duration_ms, maximum=_MAX_DURATION_MS)
        if type(self.duration_samples_ms) is not tuple:
            _invalid()
        count = len(self.duration_samples_ms)
        if not 1 <= count <= _MAX_SAMPLE_COUNT:
            _invalid()
        for value in self.duration_samples_ms:
            _positive_int(value, maximum=_MAX_MEASUREMENT_MS)
        _non_negative_int(self.successful_operations, maximum=count)
        _non_negative_int(self.max_db_connections, maximum=1_000_000)
        if self.surface is LoadSurface.WORKER:
            if (
                type(self.queue_age_samples_ms) is not tuple
                or len(self.queue_age_samples_ms) != count
            ):
                _invalid()
            for value in self.queue_age_samples_ms:
                _non_negative_int(value, maximum=_MAX_MEASUREMENT_MS)
        elif self.queue_age_samples_ms is not None:
            _invalid()

    @property
    def operation_count(self) -> int:
        return len(self.duration_samples_ms)

    def as_dict(self) -> dict[str, object]:
        return {
            "concurrent_units": self.concurrent_units,
            "duration_ms": self.duration_ms,
            "duration_samples_ms": list(self.duration_samples_ms),
            "max_db_connections": self.max_db_connections,
            "queue_age_samples_ms": (
                None
                if self.queue_age_samples_ms is None
                else list(self.queue_age_samples_ms)
            ),
            "successful_operations": self.successful_operations,
            "surface": self.surface.value,
        }


def _unique_by_surface(
    values: tuple[SurfaceBudget, ...] | tuple[SurfaceObservation, ...],
    expected: type[SurfaceBudget] | type[SurfaceObservation],
) -> None:
    if type(values) is not tuple:
        _invalid()
    seen: set[LoadSurface] = set()
    for value in values:
        if type(value) is not expected:
            _invalid()
        surface = value.surface
        if surface in seen:
            fail_performance_load(PerformanceLoadFailureCode.DUPLICATE_SURFACE)
        seen.add(surface)


@dataclass(frozen=True, slots=True)
class PerformanceLoadRequest:
    run_id: UUID
    observed_at: str
    evidence_source: LoadEvidenceSource
    source_artifact_sha256: str
    dataset_id: str
    budgets: tuple[SurfaceBudget, ...]
    observations: tuple[SurfaceObservation, ...]

    def __post_init__(self) -> None:
        _exact_uuid(self.run_id)
        _canonical_utc(self.observed_at)
        if type(self.evidence_source) is not LoadEvidenceSource:
            _invalid()
        _sha256(self.source_artifact_sha256)
        _safe_id(self.dataset_id)
        _unique_by_surface(self.budgets, SurfaceBudget)
        _unique_by_surface(self.observations, SurfaceObservation)
        if {budget.surface for budget in self.budgets} != set(ORDERED_LOAD_SURFACES):
            _invalid()

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(
            {
                "budgets": [
                    budget.as_dict()
                    for budget in sorted(
                        self.budgets, key=lambda row: row.surface.value
                    )
                ],
                "dataset_id": self.dataset_id,
                "evidence_source": self.evidence_source.value,
                "observations": [
                    row.as_dict()
                    for row in sorted(
                        self.observations, key=lambda item: item.surface.value
                    )
                ],
                "observed_at": self.observed_at,
                "run_id": str(self.run_id),
                "source_artifact_sha256": self.source_artifact_sha256,
            }
        )

    @property
    def request_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class SurfaceEvaluation:
    surface: LoadSurface
    status: SurfaceEvaluationStatus
    operation_count: int | None
    p95_duration_ms: int | None
    p99_duration_ms: int | None
    error_count: int | None
    error_rate_numerator: int | None
    error_rate_denominator: int | None
    throughput_milliops_per_second: int | None
    max_db_connections: int | None
    queue_age_p95_ms: int | None
    queue_age_availability: MetricAvailability
    cost_microunits: None
    cost_availability: MetricAvailability
    breached_budgets: tuple[str, ...]
    capacity_classification: CapacityClassification | None

    def __post_init__(self) -> None:
        if (
            type(self.surface) is not LoadSurface
            or type(self.status) is not SurfaceEvaluationStatus
            or type(self.queue_age_availability) is not MetricAvailability
            or type(self.cost_availability) is not MetricAvailability
            or self.cost_microunits is not None
            or type(self.breached_budgets) is not tuple
        ):
            _invalid()
        if any(type(value) is not str or not value for value in self.breached_budgets):
            _invalid()
        if len(set(self.breached_budgets)) != len(self.breached_budgets):
            _invalid()
        if self.status is SurfaceEvaluationStatus.UNAVAILABLE:
            if (
                any(
                    value is not None
                    for value in (
                        self.operation_count,
                        self.p95_duration_ms,
                        self.p99_duration_ms,
                        self.error_count,
                        self.error_rate_numerator,
                        self.error_rate_denominator,
                        self.throughput_milliops_per_second,
                        self.max_db_connections,
                        self.queue_age_p95_ms,
                        self.capacity_classification,
                    )
                )
                or self.breached_budgets != ("MISSING_SURFACE_OBSERVATION",)
                or self.cost_availability is not MetricAvailability.UNAVAILABLE
            ):
                _invalid()
            expected_queue = (
                MetricAvailability.UNAVAILABLE
                if self.surface is LoadSurface.WORKER
                else MetricAvailability.NOT_APPLICABLE
            )
            if self.queue_age_availability is not expected_queue:
                _invalid()
            return
        if type(self.capacity_classification) is not CapacityClassification:
            _invalid()
        count = _positive_int(self.operation_count, maximum=_MAX_SAMPLE_COUNT)
        p95 = _positive_int(self.p95_duration_ms, maximum=_MAX_MEASUREMENT_MS)
        p99 = _positive_int(self.p99_duration_ms, maximum=_MAX_MEASUREMENT_MS)
        if p99 < p95:
            _invalid()
        errors = _non_negative_int(self.error_count, maximum=count)
        if self.error_rate_numerator != errors or self.error_rate_denominator != count:
            _invalid()
        _non_negative_int(self.throughput_milliops_per_second, maximum=10**12)
        _non_negative_int(self.max_db_connections, maximum=1_000_000)
        if self.cost_availability is not MetricAvailability.UNAVAILABLE:
            _invalid()
        if self.surface is LoadSurface.WORKER:
            _non_negative_int(self.queue_age_p95_ms, maximum=_MAX_MEASUREMENT_MS)
            if self.queue_age_availability is not MetricAvailability.AVAILABLE:
                _invalid()
        elif (
            self.queue_age_p95_ms is not None
            or self.queue_age_availability is not MetricAvailability.NOT_APPLICABLE
        ):
            _invalid()
        if (
            self.status is SurfaceEvaluationStatus.LOCAL_BUDGET_MET
            and self.breached_budgets
        ) or (
            self.status is SurfaceEvaluationStatus.LOCAL_BUDGET_BREACHED
            and not self.breached_budgets
        ):
            _invalid()

    def as_dict(self) -> dict[str, object]:
        return {
            "breached_budgets": list(self.breached_budgets),
            "capacity_classification": (
                None
                if self.capacity_classification is None
                else self.capacity_classification.value
            ),
            "cost_availability": self.cost_availability.value,
            "cost_microunits": None,
            "error_count": self.error_count,
            "error_rate_denominator": self.error_rate_denominator,
            "error_rate_numerator": self.error_rate_numerator,
            "max_db_connections": self.max_db_connections,
            "operation_count": self.operation_count,
            "p95_duration_ms": self.p95_duration_ms,
            "p99_duration_ms": self.p99_duration_ms,
            "queue_age_availability": self.queue_age_availability.value,
            "queue_age_p95_ms": self.queue_age_p95_ms,
            "status": self.status.value,
            "surface": self.surface.value,
            "throughput_milliops_per_second": self.throughput_milliops_per_second,
        }


@dataclass(frozen=True, slots=True)
class PerformanceLoadReport:
    run_id: UUID
    observed_at: str
    evidence_source: LoadEvidenceSource
    source_artifact_sha256: str
    dataset_id: str
    request_sha256: str
    report_status: LoadReportStatus
    budgets: tuple[SurfaceBudget, ...]
    evaluations: tuple[SurfaceEvaluation, ...]

    def __post_init__(self) -> None:
        _exact_uuid(self.run_id)
        _canonical_utc(self.observed_at)
        if (
            type(self.evidence_source) is not LoadEvidenceSource
            or type(self.report_status) is not LoadReportStatus
            or type(self.budgets) is not tuple
            or type(self.evaluations) is not tuple
        ):
            _invalid()
        _sha256(self.source_artifact_sha256)
        _sha256(self.request_sha256)
        _safe_id(self.dataset_id)
        if any(type(row) is not SurfaceBudget for row in self.budgets):
            _invalid()
        if any(type(row) is not SurfaceEvaluation for row in self.evaluations):
            _invalid()
        if tuple(row.surface for row in self.budgets) != ORDERED_LOAD_SURFACES:
            _invalid()
        if tuple(row.surface for row in self.evaluations) != ORDERED_LOAD_SURFACES:
            _invalid()
        statuses = {row.status for row in self.evaluations}
        expected_status = (
            LoadReportStatus.DATA_BLOCKED
            if SurfaceEvaluationStatus.UNAVAILABLE in statuses
            else (
                LoadReportStatus.LOCAL_BUDGET_FAILED
                if SurfaceEvaluationStatus.LOCAL_BUDGET_BREACHED in statuses
                else LoadReportStatus.LOCAL_CAPACITY_DOCUMENTED
            )
        )
        if self.report_status is not expected_status:
            _invalid()

    @property
    def action_count(self) -> int:
        return 0

    def as_dict(self) -> dict[str, object]:
        return {
            "action_counts": {
                "browser": 0,
                "credential": 0,
                "external": 0,
                "load": 0,
                "network": 0,
                "production": 0,
                "provider": 0,
                "release": 0,
                "staging": 0,
            },
            "budgets": [row.as_dict() for row in self.budgets],
            "canonical_slo_evaluation": "NOT_EVALUATED_TST_027_STAGING_REQUIRED",
            "dataset_id": self.dataset_id,
            "evaluations": [row.as_dict() for row in self.evaluations],
            "evidence_source": self.evidence_source.value,
            "formal_tst_027": "NOT_EXECUTED",
            "observed_at": self.observed_at,
            "production_capacity_claim": None,
            "production_eligible": False,
            "report_status": self.report_status.value,
            "request_sha256": self.request_sha256,
            "run_id": str(self.run_id),
            "source_artifact_sha256": self.source_artifact_sha256,
            "story_id": "ST-1604",
            "version": "2.0.0",
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.as_dict())

    @property
    def report_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def nearest_rank(values: tuple[int, ...], percentile: int) -> int:
    if (
        type(values) is not tuple
        or not values
        or type(percentile) is not int
        or not 1 <= percentile <= 100
    ):
        _invalid()
    for value in values:
        _non_negative_int(value, maximum=_MAX_MEASUREMENT_MS)
    ordered = sorted(values)
    index = ((percentile * len(ordered) + 99) // 100) - 1
    return ordered[index]


def _unavailable(surface: LoadSurface) -> SurfaceEvaluation:
    return SurfaceEvaluation(
        surface=surface,
        status=SurfaceEvaluationStatus.UNAVAILABLE,
        operation_count=None,
        p95_duration_ms=None,
        p99_duration_ms=None,
        error_count=None,
        error_rate_numerator=None,
        error_rate_denominator=None,
        throughput_milliops_per_second=None,
        max_db_connections=None,
        queue_age_p95_ms=None,
        queue_age_availability=(
            MetricAvailability.UNAVAILABLE
            if surface is LoadSurface.WORKER
            else MetricAvailability.NOT_APPLICABLE
        ),
        cost_microunits=None,
        cost_availability=MetricAvailability.UNAVAILABLE,
        breached_budgets=("MISSING_SURFACE_OBSERVATION",),
        capacity_classification=None,
    )


def evaluate_performance_load(request: PerformanceLoadRequest) -> PerformanceLoadReport:
    """Evaluate recorded bytes only; this function cannot execute a workload."""

    if type(request) is not PerformanceLoadRequest:
        _invalid()
    budgets = {row.surface: row for row in request.budgets}
    observations = {row.surface: row for row in request.observations}
    evaluations: list[SurfaceEvaluation] = []
    for surface in ORDERED_LOAD_SURFACES:
        budget = budgets[surface]
        observation = observations.get(surface)
        if observation is None:
            evaluations.append(_unavailable(surface))
            continue
        if observation.surface is not budget.surface:
            fail_performance_load(PerformanceLoadFailureCode.SURFACE_MISMATCH)
        count = observation.operation_count
        p95 = nearest_rank(observation.duration_samples_ms, 95)
        p99 = nearest_rank(observation.duration_samples_ms, 99)
        errors = count - observation.successful_operations
        throughput = (count * 1_000_000) // observation.duration_ms
        queue_p95 = (
            nearest_rank(observation.queue_age_samples_ms, 95)
            if observation.queue_age_samples_ms is not None
            else None
        )
        breached: list[str] = []
        if observation.concurrent_units != budget.concurrent_units:
            breached.append("CONCURRENT_UNITS_MISMATCH")
        if observation.duration_ms != budget.duration_ms:
            breached.append("DURATION_MISMATCH")
        if p95 > budget.max_p95_duration_ms:
            breached.append("P95_DURATION")
        if p99 > budget.max_p99_duration_ms:
            breached.append("P99_DURATION")
        if errors * 10_000 > budget.max_error_basis_points * count:
            breached.append("ERROR_RATE")
        if (
            count * 1_000_000
            < budget.min_throughput_milliops_per_second * observation.duration_ms
        ):
            breached.append("THROUGHPUT")
        if observation.max_db_connections > budget.max_db_connections:
            breached.append("DB_CONNECTIONS")
        if (
            surface is LoadSurface.WORKER
            and queue_p95 is not None
            and budget.max_queue_age_p95_ms is not None
            and queue_p95 > budget.max_queue_age_p95_ms
        ):
            breached.append("QUEUE_AGE_P95")
        classification = (
            CapacityClassification.SYNTHETIC_LOCAL_ONLY_NOT_PRODUCTION_CAPACITY
            if request.evidence_source is LoadEvidenceSource.SYNTHETIC_RECORDED_FIXTURE
            else CapacityClassification.RECORDED_LOCAL_ONLY_NOT_PRODUCTION_CAPACITY
        )
        evaluations.append(
            SurfaceEvaluation(
                surface=surface,
                status=(
                    SurfaceEvaluationStatus.LOCAL_BUDGET_MET
                    if not breached
                    else SurfaceEvaluationStatus.LOCAL_BUDGET_BREACHED
                ),
                operation_count=count,
                p95_duration_ms=p95,
                p99_duration_ms=p99,
                error_count=errors,
                error_rate_numerator=errors,
                error_rate_denominator=count,
                throughput_milliops_per_second=throughput,
                max_db_connections=observation.max_db_connections,
                queue_age_p95_ms=queue_p95,
                queue_age_availability=(
                    MetricAvailability.AVAILABLE
                    if surface is LoadSurface.WORKER
                    else MetricAvailability.NOT_APPLICABLE
                ),
                cost_microunits=None,
                cost_availability=MetricAvailability.UNAVAILABLE,
                breached_budgets=tuple(breached),
                capacity_classification=classification,
            )
        )
    statuses = {row.status for row in evaluations}
    if SurfaceEvaluationStatus.UNAVAILABLE in statuses:
        report_status = LoadReportStatus.DATA_BLOCKED
    elif SurfaceEvaluationStatus.LOCAL_BUDGET_BREACHED in statuses:
        report_status = LoadReportStatus.LOCAL_BUDGET_FAILED
    else:
        report_status = LoadReportStatus.LOCAL_CAPACITY_DOCUMENTED
    return PerformanceLoadReport(
        run_id=request.run_id,
        observed_at=request.observed_at,
        evidence_source=request.evidence_source,
        source_artifact_sha256=request.source_artifact_sha256,
        dataset_id=request.dataset_id,
        request_sha256=request.request_sha256,
        report_status=report_status,
        budgets=tuple(budgets[surface] for surface in ORDERED_LOAD_SURFACES),
        evaluations=tuple(evaluations),
    )


__all__ = [
    "CapacityClassification",
    "LoadEvidenceSource",
    "LoadReportStatus",
    "LoadSurface",
    "MetricAvailability",
    "ORDERED_LOAD_SURFACES",
    "PerformanceLoadFailure",
    "PerformanceLoadFailureCode",
    "PerformanceLoadReport",
    "PerformanceLoadRequest",
    "SurfaceBudget",
    "SurfaceEvaluation",
    "SurfaceEvaluationStatus",
    "SurfaceObservation",
    "evaluate_performance_load",
    "fail_performance_load",
    "nearest_rank",
]

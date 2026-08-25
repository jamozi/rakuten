"""Immutable proposal-only types for the ST-0708 recorded evaluation boundary."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_FLOOR, localcontext
from enum import Enum
import hashlib
import json
import re
from typing import NoReturn, SupportsIndex


METRIC_SCALE = 1_000_000
MAX_METRICS = 32
MAX_ZERO_TOLERANCE_CLASSES = 8
TRUSTED_RUNTIME_CONTRACT_SHA256 = (
    "2cda2fb12e2bc46e70292e5f7e846eb5c2a3b0760e1be39886c1793e153885a2"
)
_WILSON_Z_MICROS = 1_644_854
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


class EvidenceStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class AssessmentStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"


class ReleaseDecisionOutcome(str, Enum):
    PROPOSAL_REVIEW_REQUIRED = "PROPOSAL_REVIEW_REQUIRED"
    REFUSED_THRESHOLD_FAILURE = "REFUSED_THRESHOLD_FAILURE"
    REFUSED_ZERO_TOLERANCE = "REFUSED_ZERO_TOLERANCE"
    REFUSED_INCOMPLETE_EVIDENCE = "REFUSED_INCOMPLETE_EVIDENCE"


class LiveEvaluationFailureCode(str, Enum):
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_BINDING = "INVALID_BINDING"
    INVALID_THRESHOLD = "INVALID_THRESHOLD"
    INVALID_EVIDENCE = "INVALID_EVIDENCE"
    INVALID_REPORT = "INVALID_REPORT"


class LiveEvaluationError(ValueError):
    """Stable error that never includes rejected input material."""

    __slots__ = ("code",)

    def __init__(self, code: LiveEvaluationFailureCode) -> None:
        self.code = code
        super().__init__(code.value)

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("live evaluation errors are not serializable")


def fail_live_evaluation(code: LiveEvaluationFailureCode) -> NoReturn:
    raise LiveEvaluationError(code) from None


def canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeEncodeError, RecursionError:
        fail_live_evaluation(LiveEvaluationFailureCode.INVALID_EVIDENCE)


def sha256_bytes(value: bytes) -> str:
    if type(value) is not bytes:
        fail_live_evaluation(LiveEvaluationFailureCode.INVALID_EVIDENCE)
    return hashlib.sha256(value).hexdigest()


def _identifier(value: object) -> bool:
    return type(value) is str and _IDENTIFIER.fullmatch(value) is not None


def _sha(value: object) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _closed_text(value: object, *, maximum: int = 200) -> bool:
    return (
        type(value) is str
        and bool(value)
        and value == value.strip()
        and len(value) <= maximum
        and "\x00" not in value
        and "\n" not in value
        and "\r" not in value
    )


@dataclass(frozen=True, slots=True)
class RecordedCandidateBinding:
    recorded_task_id: str
    target_task_code: str
    route_version: str
    prompt_version: str
    model_id: str
    provenance: str
    adapter_contract_sha256: str
    fixture_registry_sha256: str
    success_fixture_sha256: str
    binding_source_sha256: str
    canonical_route_selected: bool
    canonical_model_selected: bool
    canonical_prompt_selected: bool
    live_binding: bool
    binding_sha256: str

    def require_valid(self) -> None:
        identifiers = (
            self.recorded_task_id,
            self.target_task_code,
            self.route_version,
            self.prompt_version,
            self.model_id,
            self.provenance,
        )
        hashes = (
            self.adapter_contract_sha256,
            self.fixture_registry_sha256,
            self.success_fixture_sha256,
            self.binding_source_sha256,
            self.binding_sha256,
        )
        flags = (
            self.canonical_route_selected,
            self.canonical_model_selected,
            self.canonical_prompt_selected,
            self.live_binding,
        )
        if (
            any(not _identifier(value) for value in identifiers)
            or any(not _sha(value) for value in hashes)
            or any(type(value) is not bool for value in flags)
            or self.binding_sha256
            != sha256_bytes(canonical_json_bytes(candidate_binding_projection(self)))
        ):
            fail_live_evaluation(LiveEvaluationFailureCode.INVALID_BINDING)


def candidate_binding_projection(
    binding: RecordedCandidateBinding,
) -> dict[str, object]:
    return {
        "adapter_contract_sha256": binding.adapter_contract_sha256,
        "binding_source_sha256": binding.binding_source_sha256,
        "canonical_model_selected": binding.canonical_model_selected,
        "canonical_prompt_selected": binding.canonical_prompt_selected,
        "canonical_route_selected": binding.canonical_route_selected,
        "fixture_registry_sha256": binding.fixture_registry_sha256,
        "live_binding": binding.live_binding,
        "model_id": binding.model_id,
        "prompt_version": binding.prompt_version,
        "provenance": binding.provenance,
        "recorded_task_id": binding.recorded_task_id,
        "route_version": binding.route_version,
        "success_fixture_sha256": binding.success_fixture_sha256,
        "target_task_code": binding.target_task_code,
    }


def finalize_candidate_binding(
    binding: RecordedCandidateBinding,
) -> RecordedCandidateBinding:
    if type(binding) is not RecordedCandidateBinding:
        fail_live_evaluation(LiveEvaluationFailureCode.INVALID_BINDING)
    finalized = replace(
        binding,
        binding_sha256=sha256_bytes(
            canonical_json_bytes(candidate_binding_projection(binding))
        ),
    )
    finalized.require_valid()
    return finalized


@dataclass(frozen=True, slots=True)
class RecordedHarnessReportBinding:
    source_task_code: str
    suite_code: str
    bundle_sha256: str
    report_sha256: str
    report_outcome: str
    dataset_sha256: str
    holdout_sha256: str
    observed_case_count: int
    observed_splits: tuple[str, ...]
    dataset_provenance: str
    human_label_status: EvidenceStatus
    release_eligible: bool

    def require_valid(self) -> None:
        if (
            not _identifier(self.source_task_code)
            or not _identifier(self.suite_code)
            or any(
                not _sha(value)
                for value in (
                    self.bundle_sha256,
                    self.report_sha256,
                    self.dataset_sha256,
                    self.holdout_sha256,
                )
            )
            or self.report_outcome != "REFUSED_INCOMPLETE_EVIDENCE"
            or type(self.observed_case_count) is not int
            or not 0 <= self.observed_case_count <= 10_000
            or type(self.observed_splits) is not tuple
            or not self.observed_splits
            or tuple(sorted(set(self.observed_splits)))
            != tuple(sorted(self.observed_splits))
            or any(not _identifier(value) for value in self.observed_splits)
            or not _identifier(self.dataset_provenance)
            or type(self.human_label_status) is not EvidenceStatus
            or type(self.release_eligible) is not bool
        ):
            fail_live_evaluation(LiveEvaluationFailureCode.INVALID_BINDING)


@dataclass(frozen=True, slots=True)
class RiskThreshold:
    code: str
    kind: str
    direction: str
    unit: str
    operator: str
    threshold_micros: int

    def require_valid(self) -> None:
        if (
            not _identifier(self.code)
            or not _identifier(self.kind)
            or self.direction not in {"HIGHER", "LOWER"}
            or not _identifier(self.unit)
            or self.operator not in {"==", ">=", "<=", ">", "<"}
            or type(self.threshold_micros) is not int
            or not 0 <= self.threshold_micros <= 5 * METRIC_SCALE
        ):
            fail_live_evaluation(LiveEvaluationFailureCode.INVALID_THRESHOLD)


@dataclass(frozen=True, slots=True)
class MetricObservation:
    code: str
    numerator: int | None
    denominator: int | None

    def require_valid(self) -> None:
        unavailable = self.numerator is None and self.denominator is None
        available = (
            type(self.numerator) is int
            and type(self.denominator) is int
            and 0 <= self.numerator <= self.denominator <= 10_000_000
            and self.denominator > 0
        )
        if not _identifier(self.code) or not (unavailable or available):
            fail_live_evaluation(LiveEvaluationFailureCode.INVALID_EVIDENCE)


@dataclass(frozen=True, slots=True)
class ZeroToleranceObservation:
    failure_class: str
    observed_failures: int | None
    denominator: int | None

    def require_valid(self) -> None:
        unavailable = self.observed_failures is None and self.denominator is None
        available = (
            type(self.observed_failures) is int
            and type(self.denominator) is int
            and 0 <= self.observed_failures <= self.denominator <= 10_000_000
            and self.denominator > 0
        )
        if not _closed_text(self.failure_class) or not (unavailable or available):
            fail_live_evaluation(LiveEvaluationFailureCode.INVALID_EVIDENCE)


@dataclass(frozen=True, slots=True)
class RecordedLiveEvaluationRequest:
    evaluation_id: str
    runtime_contract_sha256: str
    request_sha256: str

    def require_valid(self) -> None:
        if (
            not _identifier(self.evaluation_id)
            or not _sha(self.runtime_contract_sha256)
            or not _sha(self.request_sha256)
            or self.request_sha256
            != sha256_bytes(canonical_json_bytes(request_projection(self)))
        ):
            fail_live_evaluation(LiveEvaluationFailureCode.INVALID_REQUEST)


def request_projection(request: RecordedLiveEvaluationRequest) -> dict[str, object]:
    return {
        "evaluation_id": request.evaluation_id,
        "runtime_contract_sha256": request.runtime_contract_sha256,
    }


def finalize_request(
    request: RecordedLiveEvaluationRequest,
) -> RecordedLiveEvaluationRequest:
    if type(request) is not RecordedLiveEvaluationRequest:
        fail_live_evaluation(LiveEvaluationFailureCode.INVALID_REQUEST)
    finalized = replace(
        request,
        request_sha256=sha256_bytes(canonical_json_bytes(request_projection(request))),
    )
    finalized.require_valid()
    return finalized


@dataclass(frozen=True, slots=True)
class RecordedLiveEvaluationResult:
    request: RecordedLiveEvaluationRequest
    candidate: RecordedCandidateBinding
    source_report: RecordedHarnessReportBinding
    target_suite_code: str
    target_task_code: str
    risk_level: str
    minimum_adjudicated_cases: int
    required_splits: tuple[str, ...]
    thresholds: tuple[RiskThreshold, ...]
    zero_tolerance_classes: tuple[str, ...]
    metric_observations: tuple[MetricObservation, ...]
    zero_tolerance_observations: tuple[ZeroToleranceObservation, ...]
    st0703_binding_verified: bool
    st0707_report_verified: bool
    formal_tst_018_executed: bool
    od_015_resolved: bool
    evidence_sha256: str

    def require_valid(self) -> None:
        if type(self.request) is not RecordedLiveEvaluationRequest:
            fail_live_evaluation(LiveEvaluationFailureCode.INVALID_EVIDENCE)
        self.request.require_valid()
        if type(self.candidate) is not RecordedCandidateBinding:
            fail_live_evaluation(LiveEvaluationFailureCode.INVALID_EVIDENCE)
        self.candidate.require_valid()
        if type(self.source_report) is not RecordedHarnessReportBinding:
            fail_live_evaluation(LiveEvaluationFailureCode.INVALID_EVIDENCE)
        self.source_report.require_valid()
        flags = (
            self.st0703_binding_verified,
            self.st0707_report_verified,
            self.formal_tst_018_executed,
            self.od_015_resolved,
        )
        if (
            not _identifier(self.target_suite_code)
            or not _identifier(self.target_task_code)
            or self.candidate.target_task_code != self.target_task_code
            or self.risk_level not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
            or type(self.minimum_adjudicated_cases) is not int
            or not 1 <= self.minimum_adjudicated_cases <= 10_000
            or type(self.required_splits) is not tuple
            or not self.required_splits
            or tuple(sorted(set(self.required_splits)))
            != tuple(sorted(self.required_splits))
            or any(not _identifier(item) for item in self.required_splits)
            or type(self.thresholds) is not tuple
            or not 1 <= len(self.thresholds) <= MAX_METRICS
            or tuple(item.code for item in self.thresholds)
            != tuple(sorted(item.code for item in self.thresholds))
            or len({item.code for item in self.thresholds}) != len(self.thresholds)
            or type(self.zero_tolerance_classes) is not tuple
            or len(self.zero_tolerance_classes) != MAX_ZERO_TOLERANCE_CLASSES
            or tuple(sorted(set(self.zero_tolerance_classes)))
            != tuple(sorted(self.zero_tolerance_classes))
            or any(not _closed_text(item) for item in self.zero_tolerance_classes)
            or type(self.metric_observations) is not tuple
            or len(self.metric_observations) > MAX_METRICS
            or tuple(item.code for item in self.metric_observations)
            != tuple(sorted(item.code for item in self.metric_observations))
            or len({item.code for item in self.metric_observations})
            != len(self.metric_observations)
            or type(self.zero_tolerance_observations) is not tuple
            or len(self.zero_tolerance_observations) > MAX_ZERO_TOLERANCE_CLASSES
            or tuple(item.failure_class for item in self.zero_tolerance_observations)
            != tuple(
                sorted(item.failure_class for item in self.zero_tolerance_observations)
            )
            or len({item.failure_class for item in self.zero_tolerance_observations})
            != len(self.zero_tolerance_observations)
            or any(type(value) is not bool for value in flags)
            or not _sha(self.evidence_sha256)
        ):
            fail_live_evaluation(LiveEvaluationFailureCode.INVALID_EVIDENCE)
        for threshold in self.thresholds:
            threshold.require_valid()
        for metric_observation in self.metric_observations:
            metric_observation.require_valid()
            if metric_observation.code not in {item.code for item in self.thresholds}:
                fail_live_evaluation(LiveEvaluationFailureCode.INVALID_EVIDENCE)
        for zero_observation in self.zero_tolerance_observations:
            zero_observation.require_valid()
            if zero_observation.failure_class not in self.zero_tolerance_classes:
                fail_live_evaluation(LiveEvaluationFailureCode.INVALID_EVIDENCE)
        if self.evidence_sha256 != sha256_bytes(
            canonical_json_bytes(evidence_projection(self))
        ):
            fail_live_evaluation(LiveEvaluationFailureCode.INVALID_EVIDENCE)


def _threshold_projection(item: RiskThreshold) -> dict[str, object]:
    return {
        "code": item.code,
        "direction": item.direction,
        "kind": item.kind,
        "operator": item.operator,
        "threshold_micros": item.threshold_micros,
        "unit": item.unit,
    }


def _source_report_projection(item: RecordedHarnessReportBinding) -> dict[str, object]:
    return {
        "bundle_sha256": item.bundle_sha256,
        "dataset_provenance": item.dataset_provenance,
        "dataset_sha256": item.dataset_sha256,
        "holdout_sha256": item.holdout_sha256,
        "human_label_status": item.human_label_status.value,
        "observed_case_count": item.observed_case_count,
        "observed_splits": list(item.observed_splits),
        "release_eligible": item.release_eligible,
        "report_outcome": item.report_outcome,
        "report_sha256": item.report_sha256,
        "source_task_code": item.source_task_code,
        "suite_code": item.suite_code,
    }


def evidence_projection(result: RecordedLiveEvaluationResult) -> dict[str, object]:
    return {
        "candidate": candidate_binding_projection(result.candidate)
        | {"binding_sha256": result.candidate.binding_sha256},
        "formal_tst_018_executed": result.formal_tst_018_executed,
        "metric_observations": [
            {
                "code": item.code,
                "denominator": item.denominator,
                "numerator": item.numerator,
            }
            for item in result.metric_observations
        ],
        "minimum_adjudicated_cases": result.minimum_adjudicated_cases,
        "od_015_resolved": result.od_015_resolved,
        "request": request_projection(result.request)
        | {"request_sha256": result.request.request_sha256},
        "required_splits": list(result.required_splits),
        "risk_level": result.risk_level,
        "source_report": _source_report_projection(result.source_report),
        "st0703_binding_verified": result.st0703_binding_verified,
        "st0707_report_verified": result.st0707_report_verified,
        "target_suite_code": result.target_suite_code,
        "target_task_code": result.target_task_code,
        "thresholds": [_threshold_projection(item) for item in result.thresholds],
        "zero_tolerance_classes": list(result.zero_tolerance_classes),
        "zero_tolerance_observations": [
            {
                "denominator": item.denominator,
                "failure_class": item.failure_class,
                "observed_failures": item.observed_failures,
            }
            for item in result.zero_tolerance_observations
        ],
    }


def finalize_evidence(
    result: RecordedLiveEvaluationResult,
) -> RecordedLiveEvaluationResult:
    if type(result) is not RecordedLiveEvaluationResult:
        fail_live_evaluation(LiveEvaluationFailureCode.INVALID_EVIDENCE)
    finalized = replace(
        result,
        evidence_sha256=sha256_bytes(canonical_json_bytes(evidence_projection(result))),
    )
    finalized.require_valid()
    return finalized


@dataclass(frozen=True, slots=True)
class MetricAssessment:
    code: str
    status: AssessmentStatus
    numerator: int | None
    denominator: int | None
    point_estimate_micros: int | None
    wilson_lower_bound_micros: int | None
    threshold_micros: int
    operator: str


@dataclass(frozen=True, slots=True)
class ZeroToleranceAssessment:
    failure_class: str
    status: AssessmentStatus
    observed_failures: int | None
    denominator: int | None


@dataclass(frozen=True, slots=True)
class EvaluationGate:
    code: str
    status: AssessmentStatus


@dataclass(frozen=True, slots=True)
class LiveEvaluationReport:
    evaluation_id: str
    request_sha256: str
    evidence_sha256: str
    target_task_code: str
    target_suite_code: str
    risk_level: str
    candidate_binding_sha256: str
    source_bundle_sha256: str
    source_report_sha256: str
    dataset_sha256: str
    holdout_sha256: str
    metrics: tuple[MetricAssessment, ...]
    zero_tolerance: tuple[ZeroToleranceAssessment, ...]
    gates: tuple[EvaluationGate, ...]
    outcome: ReleaseDecisionOutcome
    reasons: tuple[str, ...]
    report_sha256: str
    decision_kind: str = "PROPOSAL"
    authority: str = "NONE"
    provider_called: bool = False
    network_used: bool = False
    credential_read: bool = False
    route_mutated: bool = False
    activated: bool = False
    approved: bool = False
    published: bool = False
    released: bool = False
    production_written: bool = False

    def require_valid(self) -> None:
        flags = (
            self.provider_called,
            self.network_used,
            self.credential_read,
            self.route_mutated,
            self.activated,
            self.approved,
            self.published,
            self.released,
            self.production_written,
        )
        if (
            not _identifier(self.evaluation_id)
            or any(
                not _sha(value)
                for value in (
                    self.request_sha256,
                    self.evidence_sha256,
                    self.candidate_binding_sha256,
                    self.source_bundle_sha256,
                    self.source_report_sha256,
                    self.dataset_sha256,
                    self.holdout_sha256,
                    self.report_sha256,
                )
            )
            or not _identifier(self.target_task_code)
            or not _identifier(self.target_suite_code)
            or self.risk_level not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
            or type(self.metrics) is not tuple
            or type(self.zero_tolerance) is not tuple
            or type(self.gates) is not tuple
            or tuple(item.code for item in self.metrics)
            != tuple(sorted(item.code for item in self.metrics))
            or tuple(item.failure_class for item in self.zero_tolerance)
            != tuple(sorted(item.failure_class for item in self.zero_tolerance))
            or tuple(item.code for item in self.gates)
            != tuple(sorted(item.code for item in self.gates))
            or type(self.outcome) is not ReleaseDecisionOutcome
            or type(self.reasons) is not tuple
            or tuple(sorted(set(self.reasons))) != self.reasons
            or any(not _identifier(item) for item in self.reasons)
            or self.decision_kind != "PROPOSAL"
            or self.authority != "NONE"
            or any(type(value) is not bool or value for value in flags)
            or self.report_sha256
            != sha256_bytes(canonical_json_bytes(report_projection(self)))
        ):
            fail_live_evaluation(LiveEvaluationFailureCode.INVALID_REPORT)

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("live evaluation reports are not serializable")


def _metric_assessment_projection(item: MetricAssessment) -> dict[str, object]:
    return {
        "code": item.code,
        "denominator": item.denominator,
        "numerator": item.numerator,
        "operator": item.operator,
        "point_estimate_micros": item.point_estimate_micros,
        "status": item.status.value,
        "threshold_micros": item.threshold_micros,
        "wilson_lower_bound_micros": item.wilson_lower_bound_micros,
    }


def report_projection(report: LiveEvaluationReport) -> dict[str, object]:
    return {
        "authority": report.authority,
        "candidate_binding_sha256": report.candidate_binding_sha256,
        "dataset_sha256": report.dataset_sha256,
        "decision_kind": report.decision_kind,
        "evidence_sha256": report.evidence_sha256,
        "evaluation_id": report.evaluation_id,
        "gates": [
            {"code": item.code, "status": item.status.value} for item in report.gates
        ],
        "holdout_sha256": report.holdout_sha256,
        "metrics": [_metric_assessment_projection(item) for item in report.metrics],
        "operational_authority": {
            "activated": report.activated,
            "approved": report.approved,
            "credential_read": report.credential_read,
            "network_used": report.network_used,
            "production_written": report.production_written,
            "provider_called": report.provider_called,
            "published": report.published,
            "released": report.released,
            "route_mutated": report.route_mutated,
        },
        "outcome": report.outcome.value,
        "reasons": list(report.reasons),
        "request_sha256": report.request_sha256,
        "risk_level": report.risk_level,
        "source_bundle_sha256": report.source_bundle_sha256,
        "source_report_sha256": report.source_report_sha256,
        "target_suite_code": report.target_suite_code,
        "target_task_code": report.target_task_code,
        "zero_tolerance": [
            {
                "denominator": item.denominator,
                "failure_class": item.failure_class,
                "observed_failures": item.observed_failures,
                "status": item.status.value,
            }
            for item in report.zero_tolerance
        ],
    }


def finalize_report(report: LiveEvaluationReport) -> LiveEvaluationReport:
    if type(report) is not LiveEvaluationReport:
        fail_live_evaluation(LiveEvaluationFailureCode.INVALID_REPORT)
    finalized = replace(
        report,
        report_sha256=sha256_bytes(canonical_json_bytes(report_projection(report))),
    )
    finalized.require_valid()
    return finalized


def _wilson_lower_bound_micros(numerator: int, denominator: int) -> int:
    if (
        type(numerator) is not int
        or type(denominator) is not int
        or not 0 <= numerator <= denominator
        or denominator == 0
    ):
        fail_live_evaluation(LiveEvaluationFailureCode.INVALID_EVIDENCE)
    with localcontext() as context:
        context.prec = 50
        count = Decimal(numerator)
        total = Decimal(denominator)
        z = Decimal(_WILSON_Z_MICROS) / Decimal(METRIC_SCALE)
        proportion = count / total
        z_squared = z * z
        centre = proportion + z_squared / (Decimal(2) * total)
        radicand = (
            proportion * (Decimal(1) - proportion) + z_squared / (Decimal(4) * total)
        ) / total
        lower = (centre - z * context.sqrt(radicand)) / (Decimal(1) + z_squared / total)
        bounded = max(Decimal(0), min(Decimal(1), lower))
        return int(
            (bounded * Decimal(METRIC_SCALE)).to_integral_value(rounding=ROUND_FLOOR)
        )


def _compare(value: int, threshold: RiskThreshold) -> bool:
    if threshold.operator == "==":
        return value == threshold.threshold_micros
    if threshold.operator == ">=":
        return value >= threshold.threshold_micros
    if threshold.operator == "<=":
        return value <= threshold.threshold_micros
    if threshold.operator == ">":
        return value > threshold.threshold_micros
    if threshold.operator == "<":
        return value < threshold.threshold_micros
    fail_live_evaluation(LiveEvaluationFailureCode.INVALID_THRESHOLD)


def _metric_assessments(
    evidence: RecordedLiveEvaluationResult,
) -> tuple[MetricAssessment, ...]:
    observed = {item.code: item for item in evidence.metric_observations}
    results: list[MetricAssessment] = []
    for threshold in evidence.thresholds:
        item = observed.get(threshold.code)
        if (
            item is None
            or item.numerator is None
            or item.denominator is None
            or item.denominator < evidence.minimum_adjudicated_cases
        ):
            results.append(
                MetricAssessment(
                    code=threshold.code,
                    status=AssessmentStatus.UNAVAILABLE,
                    numerator=None,
                    denominator=None,
                    point_estimate_micros=None,
                    wilson_lower_bound_micros=None,
                    threshold_micros=threshold.threshold_micros,
                    operator=threshold.operator,
                )
            )
            continue
        point = item.numerator * METRIC_SCALE // item.denominator
        wilson = _wilson_lower_bound_micros(item.numerator, item.denominator)
        comparison = point
        results.append(
            MetricAssessment(
                code=threshold.code,
                status=(
                    AssessmentStatus.PASS
                    if _compare(comparison, threshold)
                    else AssessmentStatus.FAIL
                ),
                numerator=item.numerator,
                denominator=item.denominator,
                point_estimate_micros=point,
                wilson_lower_bound_micros=wilson,
                threshold_micros=threshold.threshold_micros,
                operator=threshold.operator,
            )
        )
    return tuple(results)


def _zero_tolerance_assessments(
    evidence: RecordedLiveEvaluationResult,
) -> tuple[ZeroToleranceAssessment, ...]:
    observed = {
        item.failure_class: item for item in evidence.zero_tolerance_observations
    }
    results: list[ZeroToleranceAssessment] = []
    for failure_class in evidence.zero_tolerance_classes:
        item = observed.get(failure_class)
        if (
            item is None
            or item.observed_failures is None
            or item.denominator is None
            or item.denominator < evidence.minimum_adjudicated_cases
        ):
            results.append(
                ZeroToleranceAssessment(
                    failure_class=failure_class,
                    status=AssessmentStatus.UNAVAILABLE,
                    observed_failures=None,
                    denominator=None,
                )
            )
            continue
        results.append(
            ZeroToleranceAssessment(
                failure_class=failure_class,
                status=(
                    AssessmentStatus.PASS
                    if item.observed_failures == 0
                    else AssessmentStatus.FAIL
                ),
                observed_failures=item.observed_failures,
                denominator=item.denominator,
            )
        )
    return tuple(results)


def evaluate_recorded_live_evidence(
    evidence: RecordedLiveEvaluationResult,
) -> LiveEvaluationReport:
    """Evaluate only supplied immutable evidence; never infer missing values."""

    if type(evidence) is not RecordedLiveEvaluationResult:
        fail_live_evaluation(LiveEvaluationFailureCode.INVALID_EVIDENCE)
    evidence.require_valid()
    metrics = _metric_assessments(evidence)
    zero_tolerance = _zero_tolerance_assessments(evidence)
    task_binding_matches = (
        evidence.source_report.source_task_code == evidence.target_task_code
    )
    minimum_complete = (
        evidence.source_report.observed_case_count >= evidence.minimum_adjudicated_cases
    )
    required_splits_complete = set(evidence.required_splits).issubset(
        evidence.source_report.observed_splits
    )
    human_labels_available = (
        evidence.source_report.human_label_status is EvidenceStatus.AVAILABLE
    )
    release_dataset_available = (
        evidence.source_report.release_eligible
        and evidence.source_report.dataset_provenance
        not in {"SYNTHETIC_PLUMBING_ONLY", "SYNTHETIC_TEST_ONLY"}
    )
    canonical_candidate_selected = (
        all(
            (
                evidence.candidate.canonical_route_selected,
                evidence.candidate.canonical_model_selected,
                evidence.candidate.canonical_prompt_selected,
            )
        )
        and evidence.candidate.live_binding
    )
    source_report_complete = not evidence.source_report.report_outcome.startswith(
        "REFUSED_"
    )
    zero_failed = any(item.status is AssessmentStatus.FAIL for item in zero_tolerance)
    zero_unavailable = any(
        item.status is AssessmentStatus.UNAVAILABLE for item in zero_tolerance
    )
    metrics_failed = any(item.status is AssessmentStatus.FAIL for item in metrics)
    metrics_unavailable = any(
        item.status is AssessmentStatus.UNAVAILABLE for item in metrics
    )
    gates = tuple(
        sorted(
            (
                EvaluationGate("ARTIFACT_INTEGRITY", AssessmentStatus.PASS),
                EvaluationGate(
                    "CANONICAL_ROUTE_MODEL_PROMPT_BINDING",
                    AssessmentStatus.PASS
                    if canonical_candidate_selected
                    else AssessmentStatus.UNAVAILABLE,
                ),
                EvaluationGate(
                    "DATASET_RELEASE_ELIGIBILITY",
                    AssessmentStatus.PASS
                    if release_dataset_available
                    else AssessmentStatus.UNAVAILABLE,
                ),
                EvaluationGate(
                    "FORMAL_TST_018",
                    AssessmentStatus.PASS
                    if evidence.formal_tst_018_executed
                    else AssessmentStatus.UNAVAILABLE,
                ),
                EvaluationGate(
                    "HUMAN_LABEL_PROVENANCE",
                    AssessmentStatus.PASS
                    if human_labels_available
                    else AssessmentStatus.UNAVAILABLE,
                ),
                EvaluationGate(
                    "MINIMUM_ADJUDICATED_CASES",
                    AssessmentStatus.PASS
                    if minimum_complete
                    else AssessmentStatus.FAIL,
                ),
                EvaluationGate(
                    "OD_015_EXTERNAL_EVIDENCE",
                    AssessmentStatus.PASS
                    if evidence.od_015_resolved
                    else AssessmentStatus.UNAVAILABLE,
                ),
                EvaluationGate(
                    "REQUIRED_METRICS",
                    AssessmentStatus.UNAVAILABLE
                    if metrics_unavailable
                    else AssessmentStatus.FAIL
                    if metrics_failed
                    else AssessmentStatus.PASS,
                ),
                EvaluationGate(
                    "REQUIRED_SPLITS",
                    AssessmentStatus.PASS
                    if required_splits_complete
                    else AssessmentStatus.FAIL,
                ),
                EvaluationGate(
                    "ST0703_RECORDED_BINDING",
                    AssessmentStatus.PASS
                    if evidence.st0703_binding_verified
                    else AssessmentStatus.FAIL,
                ),
                EvaluationGate(
                    "ST0707_REPORT_BINDING",
                    AssessmentStatus.PASS
                    if evidence.st0707_report_verified
                    else AssessmentStatus.FAIL,
                ),
                EvaluationGate(
                    "SOURCE_REPORT_DECISION",
                    AssessmentStatus.PASS
                    if source_report_complete
                    else AssessmentStatus.UNAVAILABLE,
                ),
                EvaluationGate(
                    "TARGET_TASK_BINDING",
                    AssessmentStatus.PASS
                    if task_binding_matches
                    else AssessmentStatus.FAIL,
                ),
                EvaluationGate(
                    "ZERO_TOLERANCE",
                    AssessmentStatus.FAIL
                    if zero_failed
                    else AssessmentStatus.UNAVAILABLE
                    if zero_unavailable
                    else AssessmentStatus.PASS,
                ),
            ),
            key=lambda item: item.code,
        )
    )
    reasons: set[str] = set()
    if not canonical_candidate_selected:
        reasons.add("CANONICAL_ROUTE_MODEL_PROMPT_BINDING_UNAVAILABLE")
    if not release_dataset_available:
        reasons.add("DATASET_NOT_RELEASE_ELIGIBLE")
    if not evidence.formal_tst_018_executed:
        reasons.add("FORMAL_TST_018_NOT_EXECUTED")
    if not human_labels_available:
        reasons.add("HUMAN_LABEL_PROVENANCE_UNAVAILABLE")
    if not minimum_complete:
        reasons.add("MINIMUM_ADJUDICATED_CASES_UNMET")
    if not evidence.od_015_resolved:
        reasons.add("OD_015_EXTERNAL_EVIDENCE_REQUIRED")
    if metrics_failed:
        reasons.add("RISK_THRESHOLD_FAILURE_OBSERVED")
    if metrics_unavailable:
        reasons.add("RISK_THRESHOLD_EVIDENCE_UNAVAILABLE")
    if not required_splits_complete:
        reasons.add("REQUIRED_SPLITS_INCOMPLETE")
    if not evidence.st0703_binding_verified:
        reasons.add("ST0703_BINDING_UNVERIFIED")
    if not evidence.st0707_report_verified:
        reasons.add("ST0707_REPORT_UNVERIFIED")
    if not source_report_complete:
        reasons.add("SOURCE_REPORT_REFUSED_INCOMPLETE_EVIDENCE")
    if not task_binding_matches:
        reasons.add("TARGET_TASK_BINDING_MISMATCH")
    if zero_failed:
        reasons.add("ZERO_TOLERANCE_FAILURE_OBSERVED")
    if zero_unavailable:
        reasons.add("ZERO_TOLERANCE_EVIDENCE_UNAVAILABLE")

    incomplete = any(
        item.status is AssessmentStatus.UNAVAILABLE for item in gates
    ) or any(
        item.code
        in {
            "MINIMUM_ADJUDICATED_CASES",
            "REQUIRED_SPLITS",
            "ST0703_RECORDED_BINDING",
            "ST0707_REPORT_BINDING",
            "TARGET_TASK_BINDING",
        }
        and item.status is AssessmentStatus.FAIL
        for item in gates
    )
    outcome = (
        ReleaseDecisionOutcome.REFUSED_ZERO_TOLERANCE
        if zero_failed
        else ReleaseDecisionOutcome.REFUSED_INCOMPLETE_EVIDENCE
        if incomplete
        else ReleaseDecisionOutcome.REFUSED_THRESHOLD_FAILURE
        if metrics_failed
        else ReleaseDecisionOutcome.PROPOSAL_REVIEW_REQUIRED
    )
    provisional = LiveEvaluationReport(
        evaluation_id=evidence.request.evaluation_id,
        request_sha256=evidence.request.request_sha256,
        evidence_sha256=evidence.evidence_sha256,
        target_task_code=evidence.target_task_code,
        target_suite_code=evidence.target_suite_code,
        risk_level=evidence.risk_level,
        candidate_binding_sha256=evidence.candidate.binding_sha256,
        source_bundle_sha256=evidence.source_report.bundle_sha256,
        source_report_sha256=evidence.source_report.report_sha256,
        dataset_sha256=evidence.source_report.dataset_sha256,
        holdout_sha256=evidence.source_report.holdout_sha256,
        metrics=metrics,
        zero_tolerance=zero_tolerance,
        gates=gates,
        outcome=outcome,
        reasons=tuple(sorted(reasons)),
        report_sha256="0" * 64,
    )
    return finalize_report(provisional)


__all__ = [
    "AssessmentStatus",
    "EvaluationGate",
    "EvidenceStatus",
    "LiveEvaluationError",
    "LiveEvaluationFailureCode",
    "LiveEvaluationReport",
    "MetricAssessment",
    "MetricObservation",
    "RecordedCandidateBinding",
    "RecordedHarnessReportBinding",
    "RecordedLiveEvaluationRequest",
    "RecordedLiveEvaluationResult",
    "ReleaseDecisionOutcome",
    "RiskThreshold",
    "TRUSTED_RUNTIME_CONTRACT_SHA256",
    "ZeroToleranceAssessment",
    "ZeroToleranceObservation",
    "candidate_binding_projection",
    "canonical_json_bytes",
    "evaluate_recorded_live_evidence",
    "evidence_projection",
    "fail_live_evaluation",
    "finalize_candidate_binding",
    "finalize_evidence",
    "finalize_report",
    "finalize_request",
    "report_projection",
    "request_projection",
    "sha256_bytes",
]

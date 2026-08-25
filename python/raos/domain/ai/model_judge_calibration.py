"""Fail-closed values for the disabled ST-1901 model-Judge calibration seam.

Only opaque labels, closed vocabularies, counts, and content hashes cross this
boundary. Raw prompts, source packets, outputs, rationales, provider/model SDK
types, credentials, personal data, and operational authority are impossible to
represent here.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import hashlib
import json
import math
import re
from typing import NoReturn, SupportsIndex, final


CALIBRATION_VERSION = "ST1901_RECORDED_MODEL_JUDGE_CALIBRATION_V1"
REPORT_PROFILE = "ST1901_RECORDED_MODEL_JUDGE_CALIBRATION_REPORT_V1"
TRUSTED_RUNTIME_CONTRACT_SHA256 = (
    "602e13a803b99176d58b6a359bfdb91c8cb4df98f71e2cf5d5cea5588c81da95"
)
DEFAULT_MODEL_JUDGE_CALIBRATION_SCOPE = "DISABLED"
MAX_CALIBRATION_CASES = 1_000
METRIC_SCALE = 1_000_000
MINIMUM_DOUBLE_LABELED_CASES = 200
MINIMUM_CASES_PER_SCORE = 20
MINIMUM_CRITICAL_POSITIVE_CASES = 20
MINIMUM_CRITICAL_NEGATIVE_CASES = 20
REQUIRED_WEIGHTED_KAPPA_MICROS = 700_000
MAXIMUM_CRITICAL_FALSE_PASS_RATE_MICROS = 10_000
MAXIMUM_CRITICAL_FALSE_FAIL_RATE_MICROS = 50_000

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_CASE_ID = re.compile(r"AICASE-ST1901-[0-9]{4}\Z", re.ASCII)
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z", re.ASCII)
_REDACTED = "<redacted-model-judge-calibration>"


class ModelJudgeCalibrationFailureCode(str, Enum):
    INVALID_VALUE = "INVALID_MODEL_JUDGE_CALIBRATION_VALUE"
    INVALID_COMMAND = "INVALID_MODEL_JUDGE_CALIBRATION_COMMAND"
    INVALID_BATCH = "INVALID_RECORDED_MODEL_JUDGE_CALIBRATION_BATCH"
    INVALID_REPORT = "INVALID_MODEL_JUDGE_CALIBRATION_REPORT"
    FEATURE_DISABLED = "MODEL_JUDGE_CALIBRATION_FEATURE_DISABLED"


@final
class ModelJudgeCalibrationError(ValueError):
    """Sanitized failure that never retains rejected fixture material."""

    __slots__ = ("code",)

    def __init__(self, code: ModelJudgeCalibrationFailureCode) -> None:
        if type(code) is not ModelJudgeCalibrationFailureCode:
            raise TypeError("code must be an exact ModelJudgeCalibrationFailureCode")
        self.code = code
        super().__init__(code.value)

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("model-Judge calibration errors are not serializable")


def fail_calibration(code: ModelJudgeCalibrationFailureCode) -> NoReturn:
    raise ModelJudgeCalibrationError(code) from None


class ModelJudgeCalibrationScope(str, Enum):
    DISABLED = "DISABLED"
    RECORDED_SYNTHETIC_CALIBRATION_ONLY = "RECORDED_SYNTHETIC_CALIBRATION_ONLY"


class CalibrationSplit(str, Enum):
    CALIBRATION = "CALIBRATION"


class CalibrationSlice(str, Enum):
    ROUTINE = "ROUTINE"
    EDGE = "EDGE"
    ADVERSARIAL = "ADVERSARIAL"
    REGRESSION = "REGRESSION"


class CalibrationRisk(str, Enum):
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class HumanLabelResolution(str, Enum):
    AGREED = "AGREED"
    ADJUDICATED = "ADJUDICATED"


class EvidenceStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class MetricStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"


class CalibrationOutcome(str, Enum):
    REFUSED_INSUFFICIENT_EVIDENCE = "REFUSED_INSUFFICIENT_EVIDENCE"
    REFUSED_CALIBRATION_THRESHOLDS = "REFUSED_CALIBRATION_THRESHOLDS"
    REFUSED_UNVERIFIABLE_CALIBRATION = "REFUSED_UNVERIFIABLE_CALIBRATION"


class ExecutionStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


_METRIC_POLICIES = {
    "critical_false_fail_rate": (
        "<=",
        MAXIMUM_CRITICAL_FALSE_FAIL_RATE_MICROS,
    ),
    "critical_false_pass_rate": (
        "<=",
        MAXIMUM_CRITICAL_FALSE_PASS_RATE_MICROS,
    ),
    "weighted_kappa": (">=", REQUIRED_WEIGHTED_KAPPA_MICROS),
}
_GATE_CODES = (
    "ACTUAL_HUMAN_PROVENANCE",
    "CRITICAL_FALSE_FAIL",
    "CRITICAL_FALSE_PASS",
    "CRITICAL_LABEL_BALANCE",
    "DOUBLE_LABELED_CASES",
    "HUMAN_LABEL_RESOLUTION",
    "RECORDED_LABEL_SHAPE",
    "REPRESENTATIVE_DATASET",
    "RESOLVED_MODEL_BINDING",
    "SCORE_LABEL_BALANCE",
    "SEPARATE_RELEASE_DECISION",
    "WEIGHTED_KAPPA",
)
_BASE_REFUSAL_REASONS = {
    "ACTUAL_HUMAN_PROVENANCE_UNAVAILABLE",
    "FORMAL_TST_032_NOT_EXECUTED",
    "REPRESENTATIVE_DATASET_UNAVAILABLE",
    "RESOLVED_MODEL_BINDING_UNAVAILABLE",
    "SEPARATE_RELEASE_DECISION_REQUIRED",
    "SYNTHETIC_FIXTURE_NOT_RELEASE_EVIDENCE",
}


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("model-Judge calibration values are not serializable")


def _sha(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_VALUE)
    return value


def _token(value: object, *, maximum: int = 256) -> str:
    if (
        type(value) is not str
        or len(value) > maximum
        or _TOKEN.fullmatch(value) is None
    ):
        fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_VALUE)
    return value


def _score(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 4:
        fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_VALUE)
    return value


def _count(value: object, *, maximum: int = MAX_CALIBRATION_CASES) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_VALUE)
    return value


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
        fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_VALUE)


def sha256_bytes(value: bytes) -> str:
    if type(value) is not bytes:
        fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_VALUE)
    return hashlib.sha256(value).hexdigest()


@final
@dataclass(frozen=True, slots=True, repr=False)
class JudgeCalibrationReadCommand(_RedactedValue):
    fixture_id: str
    fixture_file_sha256: str
    request_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _token(self.fixture_id)
        _sha(self.fixture_file_sha256)
        object.__setattr__(
            self,
            "request_sha256",
            sha256_bytes(
                canonical_json_bytes(
                    {
                        "fixture_file_sha256": self.fixture_file_sha256,
                        "fixture_id": self.fixture_id,
                    }
                )
            ),
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedHumanJudgeLabel(_RedactedValue):
    case_id: str
    split: CalibrationSplit
    slice: CalibrationSlice
    risk: CalibrationRisk
    primary_score: int
    secondary_score: int
    adjudicated_score: int
    resolution: HumanLabelResolution
    adjudicator_role: str | None
    human_zero_tolerance: bool
    judge_score: int
    judge_zero_tolerance: bool
    judge_needs_human_adjudication: bool
    candidate_identity_blinded: bool
    prompt_author_conflict: bool
    case_sha256: str

    def __post_init__(self) -> None:
        self.require_valid()

    def _document(self) -> dict[str, object]:
        return {
            "adjudicated_score": self.adjudicated_score,
            "adjudicator_role": self.adjudicator_role,
            "candidate_identity_blinded": self.candidate_identity_blinded,
            "case_id": self.case_id,
            "human_zero_tolerance": self.human_zero_tolerance,
            "judge_needs_human_adjudication": (self.judge_needs_human_adjudication),
            "judge_score": self.judge_score,
            "judge_zero_tolerance": self.judge_zero_tolerance,
            "primary_score": self.primary_score,
            "prompt_author_conflict": self.prompt_author_conflict,
            "resolution": self.resolution.value,
            "risk": self.risk.value,
            "secondary_score": self.secondary_score,
            "slice": self.slice.value,
            "split": self.split.value,
        }

    def require_valid(self) -> None:
        if (
            type(self.case_id) is not str
            or _CASE_ID.fullmatch(self.case_id) is None
            or type(self.split) is not CalibrationSplit
            or self.split is not CalibrationSplit.CALIBRATION
            or type(self.slice) is not CalibrationSlice
            or type(self.risk) is not CalibrationRisk
            or type(self.resolution) is not HumanLabelResolution
            or type(self.human_zero_tolerance) is not bool
            or type(self.judge_zero_tolerance) is not bool
            or type(self.judge_needs_human_adjudication) is not bool
            or self.candidate_identity_blinded is not True
            or self.prompt_author_conflict is not False
        ):
            fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_VALUE)
        for value in (
            self.primary_score,
            self.secondary_score,
            self.adjudicated_score,
            self.judge_score,
        ):
            _score(value)
        if self.resolution is HumanLabelResolution.AGREED:
            if (
                not self.primary_score == self.secondary_score == self.adjudicated_score
                or self.adjudicator_role is not None
            ):
                fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_VALUE)
        elif (
            self.primary_score == self.secondary_score
            or self.adjudicator_role != "SYNTHETIC_INDEPENDENT_ADJUDICATOR"
        ):
            fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_VALUE)
        if (
            self.human_zero_tolerance != (self.adjudicated_score == 0)
            or (self.human_zero_tolerance and self.risk is not CalibrationRisk.CRITICAL)
            or (not self.human_zero_tolerance and self.risk is not CalibrationRisk.HIGH)
            or self.judge_needs_human_adjudication
            != (
                self.judge_score != self.adjudicated_score
                or self.judge_zero_tolerance != self.human_zero_tolerance
            )
        ):
            fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_VALUE)
        _sha(self.case_sha256)
        if sha256_bytes(canonical_json_bytes(self._document())) != self.case_sha256:
            fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_VALUE)


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedHumanLabelBatch(_RedactedValue):
    fixture_id: str
    fixture_file_sha256: str
    fixture_content_sha256: str
    dataset_id: str
    dataset_version: str
    dataset_sha256: str
    calibration_scope_sha256: str
    predecessor_manifest_sha256: str
    evaluation_catalog_sha256: str
    rubric_sha256: str
    cases: tuple[RecordedHumanJudgeLabel, ...]
    human_label_authority: str = field(
        default="RECORDED_GOLD_SIDE_WITHIN_SYNTHETIC_FIXTURE"
    )
    actual_human_activity: bool = field(default=False)
    representative_dataset: bool = field(default=False)
    release_eligible: bool = field(default=False)
    resolved_model_binding_status: EvidenceStatus = field(
        default=EvidenceStatus.UNAVAILABLE
    )
    batch_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "batch_sha256", self._computed_sha256())
        self.require_valid()

    def _computed_sha256(self) -> str:
        if type(self.cases) is not tuple or any(
            type(item) is not RecordedHumanJudgeLabel for item in self.cases
        ):
            fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_BATCH)
        return sha256_bytes(
            canonical_json_bytes(
                {
                    "calibration_scope_sha256": self.calibration_scope_sha256,
                    "case_sha256": [item.case_sha256 for item in self.cases],
                    "dataset_id": self.dataset_id,
                    "dataset_sha256": self.dataset_sha256,
                    "dataset_version": self.dataset_version,
                    "evaluation_catalog_sha256": self.evaluation_catalog_sha256,
                    "fixture_content_sha256": self.fixture_content_sha256,
                    "fixture_file_sha256": self.fixture_file_sha256,
                    "fixture_id": self.fixture_id,
                    "predecessor_manifest_sha256": (self.predecessor_manifest_sha256),
                    "rubric_sha256": self.rubric_sha256,
                }
            )
        )

    def require_valid(self) -> None:
        for token in (self.fixture_id, self.dataset_id, self.dataset_version):
            _token(token)
        for digest in (
            self.fixture_file_sha256,
            self.fixture_content_sha256,
            self.dataset_sha256,
            self.calibration_scope_sha256,
            self.predecessor_manifest_sha256,
            self.evaluation_catalog_sha256,
            self.rubric_sha256,
            self.batch_sha256,
        ):
            _sha(digest)
        if (
            type(self.cases) is not tuple
            or not 1 <= len(self.cases) <= MAX_CALIBRATION_CASES
            or any(type(item) is not RecordedHumanJudgeLabel for item in self.cases)
            or tuple(item.case_id for item in self.cases)
            != tuple(sorted(item.case_id for item in self.cases))
            or len({item.case_id for item in self.cases}) != len(self.cases)
            or self.human_label_authority
            != "RECORDED_GOLD_SIDE_WITHIN_SYNTHETIC_FIXTURE"
            or self.actual_human_activity is not False
            or self.representative_dataset is not False
            or self.release_eligible is not False
            or self.resolved_model_binding_status is not EvidenceStatus.UNAVAILABLE
        ):
            fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_BATCH)
        for index, item in enumerate(self.cases, start=1):
            item.require_valid()
            if item.case_id != f"AICASE-ST1901-{index:04d}":
                fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_BATCH)
        if self.batch_sha256 != self._computed_sha256():
            fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_BATCH)


@final
@dataclass(frozen=True, slots=True, repr=False)
class CalibrationMetricResult(_RedactedValue):
    code: str
    status: MetricStatus
    numerator: int | None
    denominator: int | None
    value_micros: int | None
    threshold_micros: int
    operator: str

    def __post_init__(self) -> None:
        _token(self.code)
        policy = _METRIC_POLICIES.get(self.code)
        if (
            policy is None
            or type(self.status) is not MetricStatus
            or type(self.threshold_micros) is not int
            or not -METRIC_SCALE <= self.threshold_micros <= METRIC_SCALE
            or (self.operator, self.threshold_micros) != policy
        ):
            fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_REPORT)
        if self.status is MetricStatus.UNAVAILABLE:
            if any(
                value is not None
                for value in (self.numerator, self.denominator, self.value_micros)
            ):
                fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_REPORT)
            return
        if (
            type(self.numerator) is not int
            or type(self.denominator) is not int
            or self.denominator <= 0
            or type(self.value_micros) is not int
            or not -METRIC_SCALE <= self.value_micros <= METRIC_SCALE
            or math.gcd(abs(self.numerator), self.denominator) != 1
        ):
            fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_REPORT)
        if self.code == "weighted_kappa":
            in_range = abs(self.numerator) <= self.denominator
        else:
            in_range = 0 <= self.numerator <= self.denominator
        expected_micros = self.numerator * METRIC_SCALE // self.denominator
        passes = (
            self.numerator * METRIC_SCALE >= self.threshold_micros * self.denominator
            if self.operator == ">="
            else self.numerator * METRIC_SCALE
            <= self.threshold_micros * self.denominator
        )
        if (
            not in_range
            or self.value_micros != expected_micros
            or self.status is not (MetricStatus.PASS if passes else MetricStatus.FAIL)
        ):
            fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_REPORT)

    def document(self) -> dict[str, object]:
        return {
            "code": self.code,
            "denominator": self.denominator,
            "numerator": self.numerator,
            "operator": self.operator,
            "status": self.status.value,
            "threshold_micros": self.threshold_micros,
            "value_micros": self.value_micros,
        }


@final
@dataclass(frozen=True, slots=True, repr=False)
class CalibrationGate(_RedactedValue):
    code: str
    status: GateStatus

    def __post_init__(self) -> None:
        _token(self.code)
        if type(self.status) is not GateStatus:
            fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_REPORT)

    def document(self) -> dict[str, object]:
        return {"code": self.code, "status": self.status.value}


@final
@dataclass(frozen=True, slots=True, repr=False)
class CalibrationDecision(_RedactedValue):
    outcome: CalibrationOutcome
    reasons: tuple[str, ...]
    local_metric_criteria_met: bool
    human_labels_authoritative: bool = field(default=True)
    separate_release_decision_required: bool = field(default=True)
    decision_kind: str = field(default="REFUSAL_ONLY_LOCAL_EVALUATION")
    authority: str = field(default="NONE")
    provider_call_authorized: bool = field(default=False)
    model_call_authorized: bool = field(default=False)
    persistence_authorized: bool = field(default=False)
    route_mutation_authorized: bool = field(default=False)
    model_mutation_authorized: bool = field(default=False)
    activation_authorized: bool = field(default=False)
    approval_authorized: bool = field(default=False)
    publication_authorized: bool = field(default=False)
    release_authorized: bool = field(default=False)
    production_eligible: bool = field(default=False)
    external_action_count: int = field(default=0)

    def __post_init__(self) -> None:
        if (
            type(self.outcome) is not CalibrationOutcome
            or type(self.reasons) is not tuple
            or not self.reasons
            or self.reasons != tuple(sorted(set(self.reasons)))
            or any(_TOKEN.fullmatch(item) is None for item in self.reasons)
            or type(self.local_metric_criteria_met) is not bool
            or self.human_labels_authoritative is not True
            or self.separate_release_decision_required is not True
            or self.decision_kind != "REFUSAL_ONLY_LOCAL_EVALUATION"
            or self.authority != "NONE"
            or any(
                value is not False
                for value in (
                    self.provider_call_authorized,
                    self.model_call_authorized,
                    self.persistence_authorized,
                    self.route_mutation_authorized,
                    self.model_mutation_authorized,
                    self.activation_authorized,
                    self.approval_authorized,
                    self.publication_authorized,
                    self.release_authorized,
                    self.production_eligible,
                )
            )
            or type(self.external_action_count) is not int
            or self.external_action_count != 0
        ):
            fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_REPORT)

    def document(self) -> dict[str, object]:
        return {
            "activation_authorized": self.activation_authorized,
            "approval_authorized": self.approval_authorized,
            "authority": self.authority,
            "decision_kind": self.decision_kind,
            "external_action_count": self.external_action_count,
            "human_labels_authoritative": self.human_labels_authoritative,
            "local_metric_criteria_met": self.local_metric_criteria_met,
            "model_call_authorized": self.model_call_authorized,
            "model_mutation_authorized": self.model_mutation_authorized,
            "outcome": self.outcome.value,
            "persistence_authorized": self.persistence_authorized,
            "production_eligible": self.production_eligible,
            "provider_call_authorized": self.provider_call_authorized,
            "publication_authorized": self.publication_authorized,
            "reasons": list(self.reasons),
            "release_authorized": self.release_authorized,
            "route_mutation_authorized": self.route_mutation_authorized,
            "separate_release_decision_required": (
                self.separate_release_decision_required
            ),
        }


@final
@dataclass(frozen=True, slots=True, repr=False)
class ModelJudgeCalibrationReport(_RedactedValue):
    batch_sha256: str
    fixture_file_sha256: str
    dataset_sha256: str
    calibration_scope_sha256: str
    case_count: int
    human_score_counts: tuple[int, int, int, int, int]
    confusion_matrix: tuple[
        tuple[int, int, int, int, int],
        tuple[int, int, int, int, int],
        tuple[int, int, int, int, int],
        tuple[int, int, int, int, int],
        tuple[int, int, int, int, int],
    ]
    human_reviewer_disagreement_count: int
    judge_human_disagreement_count: int
    critical_positive_count: int
    critical_negative_count: int
    metrics: tuple[CalibrationMetricResult, ...]
    gates: tuple[CalibrationGate, ...]
    decision: CalibrationDecision
    report_sha256: str
    calibration_version: str = field(default=CALIBRATION_VERSION)
    report_profile: str = field(default=REPORT_PROFILE)
    actual_human_labeling: ExecutionStatus = field(default=ExecutionStatus.NOT_EXECUTED)
    formal_tst_032: ExecutionStatus = field(default=ExecutionStatus.NOT_EXECUTED)
    live: ExecutionStatus = field(default=ExecutionStatus.NOT_EXECUTED)
    staging: ExecutionStatus = field(default=ExecutionStatus.NOT_EXECUTED)
    release: ExecutionStatus = field(default=ExecutionStatus.NOT_EXECUTED)
    production: ExecutionStatus = field(default=ExecutionStatus.NOT_EXECUTED)

    def document(self, *, include_hash: bool) -> dict[str, object]:
        """Return the summary-only shape without exposing label records."""

        value: dict[str, object] = {
            "actual_human_labeling": self.actual_human_labeling.value,
            "batch_sha256": self.batch_sha256,
            "calibration_scope_sha256": self.calibration_scope_sha256,
            "calibration_version": self.calibration_version,
            "case_count": self.case_count,
            "confusion_matrix": [list(row) for row in self.confusion_matrix],
            "critical_negative_count": self.critical_negative_count,
            "critical_positive_count": self.critical_positive_count,
            "dataset_sha256": self.dataset_sha256,
            "decision": self.decision.document(),
            "fixture_file_sha256": self.fixture_file_sha256,
            "formal_tst_032": self.formal_tst_032.value,
            "gates": [item.document() for item in self.gates],
            "human_reviewer_disagreement_count": (
                self.human_reviewer_disagreement_count
            ),
            "human_score_counts": list(self.human_score_counts),
            "judge_human_disagreement_count": (self.judge_human_disagreement_count),
            "live": self.live.value,
            "metrics": [item.document() for item in self.metrics],
            "production": self.production.value,
            "release": self.release.value,
            "report_profile": self.report_profile,
            "staging": self.staging.value,
        }
        if include_hash:
            value["report_sha256"] = self.report_sha256
        return value

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        return canonical_json_bytes(self.document(include_hash=True))

    def require_valid(self) -> None:
        for digest in (
            self.batch_sha256,
            self.fixture_file_sha256,
            self.dataset_sha256,
            self.calibration_scope_sha256,
            self.report_sha256,
        ):
            _sha(digest)
        if (
            type(self.case_count) is not int
            or not 1 <= self.case_count <= MAX_CALIBRATION_CASES
            or type(self.human_score_counts) is not tuple
            or len(self.human_score_counts) != 5
            or any(
                type(item) is not int or item < 0 for item in self.human_score_counts
            )
            or sum(self.human_score_counts) != self.case_count
            or type(self.confusion_matrix) is not tuple
            or len(self.confusion_matrix) != 5
            or any(
                type(row) is not tuple
                or len(row) != 5
                or any(type(item) is not int or item < 0 for item in row)
                for row in self.confusion_matrix
            )
            or sum(sum(row) for row in self.confusion_matrix) != self.case_count
            or self.human_score_counts
            != tuple(sum(row) for row in self.confusion_matrix)
        ):
            fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_REPORT)
        for value in (
            self.human_reviewer_disagreement_count,
            self.judge_human_disagreement_count,
            self.critical_positive_count,
            self.critical_negative_count,
        ):
            _count(value)
        if (
            self.critical_positive_count + self.critical_negative_count
            != self.case_count
            or self.critical_positive_count != self.human_score_counts[0]
            or self.human_reviewer_disagreement_count > self.case_count
            or self.judge_human_disagreement_count > self.case_count
            or self.judge_human_disagreement_count
            < sum(
                self.confusion_matrix[row][column]
                for row in range(5)
                for column in range(5)
                if row != column
            )
            or type(self.metrics) is not tuple
            or len(self.metrics) != 3
            or any(type(item) is not CalibrationMetricResult for item in self.metrics)
            or tuple(item.code for item in self.metrics)
            != tuple(sorted(_METRIC_POLICIES))
            or type(self.gates) is not tuple
            or any(type(item) is not CalibrationGate for item in self.gates)
            or tuple(item.code for item in self.gates) != _GATE_CODES
            or type(self.decision) is not CalibrationDecision
            or self.calibration_version != CALIBRATION_VERSION
            or self.report_profile != REPORT_PROFILE
            or any(
                value is not ExecutionStatus.NOT_EXECUTED
                for value in (
                    self.actual_human_labeling,
                    self.formal_tst_032,
                    self.live,
                    self.staging,
                    self.release,
                    self.production,
                )
            )
        ):
            fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_REPORT)
        metric_by_code = {item.code: item for item in self.metrics}
        metric_gate = {
            MetricStatus.PASS: GateStatus.PASS,
            MetricStatus.FAIL: GateStatus.FAIL,
            MetricStatus.UNAVAILABLE: GateStatus.UNAVAILABLE,
        }
        sample_complete = self.case_count >= MINIMUM_DOUBLE_LABELED_CASES
        scores_balanced = all(
            count >= MINIMUM_CASES_PER_SCORE for count in self.human_score_counts
        )
        critical_balanced = (
            self.critical_positive_count >= MINIMUM_CRITICAL_POSITIVE_CASES
            and self.critical_negative_count >= MINIMUM_CRITICAL_NEGATIVE_CASES
        )
        thresholds_met = all(item.status is MetricStatus.PASS for item in self.metrics)
        expected_gates = (
            ("ACTUAL_HUMAN_PROVENANCE", GateStatus.UNAVAILABLE),
            (
                "CRITICAL_FALSE_FAIL",
                metric_gate[metric_by_code["critical_false_fail_rate"].status],
            ),
            (
                "CRITICAL_FALSE_PASS",
                metric_gate[metric_by_code["critical_false_pass_rate"].status],
            ),
            (
                "CRITICAL_LABEL_BALANCE",
                GateStatus.PASS if critical_balanced else GateStatus.FAIL,
            ),
            (
                "DOUBLE_LABELED_CASES",
                GateStatus.PASS if sample_complete else GateStatus.FAIL,
            ),
            ("HUMAN_LABEL_RESOLUTION", GateStatus.PASS),
            ("RECORDED_LABEL_SHAPE", GateStatus.PASS),
            ("REPRESENTATIVE_DATASET", GateStatus.FAIL),
            ("RESOLVED_MODEL_BINDING", GateStatus.UNAVAILABLE),
            (
                "SCORE_LABEL_BALANCE",
                GateStatus.PASS if scores_balanced else GateStatus.FAIL,
            ),
            ("SEPARATE_RELEASE_DECISION", GateStatus.UNAVAILABLE),
            (
                "WEIGHTED_KAPPA",
                metric_gate[metric_by_code["weighted_kappa"].status],
            ),
        )
        expected_reasons = set(_BASE_REFUSAL_REASONS)
        if not sample_complete:
            expected_reasons.add("MINIMUM_DOUBLE_LABELED_CASES_UNMET")
        if not scores_balanced:
            expected_reasons.add("SCORE_LABELS_UNBALANCED")
        if not critical_balanced:
            expected_reasons.add("CRITICAL_LABELS_UNBALANCED")
        if not thresholds_met:
            expected_reasons.add("CALIBRATION_THRESHOLDS_UNMET")
        if not (sample_complete and scores_balanced and critical_balanced):
            expected_outcome = CalibrationOutcome.REFUSED_INSUFFICIENT_EVIDENCE
        elif not thresholds_met:
            expected_outcome = CalibrationOutcome.REFUSED_CALIBRATION_THRESHOLDS
        else:
            expected_outcome = CalibrationOutcome.REFUSED_UNVERIFIABLE_CALIBRATION
        expected_local_criteria = (
            sample_complete and scores_balanced and critical_balanced and thresholds_met
        )
        if (
            tuple((item.code, item.status) for item in self.gates) != expected_gates
            or self.decision.reasons != tuple(sorted(expected_reasons))
            or self.decision.outcome is not expected_outcome
            or self.decision.local_metric_criteria_met is not expected_local_criteria
        ):
            fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_REPORT)
        expected = sha256_bytes(canonical_json_bytes(self.document(include_hash=False)))
        if self.report_sha256 != expected:
            fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_REPORT)


def finalize_report(
    report: ModelJudgeCalibrationReport,
) -> ModelJudgeCalibrationReport:
    if type(report) is not ModelJudgeCalibrationReport:
        fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_REPORT)
    digest = sha256_bytes(canonical_json_bytes(report.document(include_hash=False)))
    finalized = replace(report, report_sha256=digest)
    finalized.require_valid()
    return finalized


__all__ = [
    "CALIBRATION_VERSION",
    "CalibrationDecision",
    "CalibrationGate",
    "CalibrationMetricResult",
    "CalibrationOutcome",
    "CalibrationRisk",
    "CalibrationSlice",
    "CalibrationSplit",
    "DEFAULT_MODEL_JUDGE_CALIBRATION_SCOPE",
    "EvidenceStatus",
    "ExecutionStatus",
    "GateStatus",
    "HumanLabelResolution",
    "JudgeCalibrationReadCommand",
    "MAXIMUM_CRITICAL_FALSE_FAIL_RATE_MICROS",
    "MAXIMUM_CRITICAL_FALSE_PASS_RATE_MICROS",
    "MAX_CALIBRATION_CASES",
    "METRIC_SCALE",
    "MINIMUM_CASES_PER_SCORE",
    "MINIMUM_CRITICAL_NEGATIVE_CASES",
    "MINIMUM_CRITICAL_POSITIVE_CASES",
    "MINIMUM_DOUBLE_LABELED_CASES",
    "MetricStatus",
    "ModelJudgeCalibrationError",
    "ModelJudgeCalibrationFailureCode",
    "ModelJudgeCalibrationReport",
    "ModelJudgeCalibrationScope",
    "REPORT_PROFILE",
    "REQUIRED_WEIGHTED_KAPPA_MICROS",
    "RecordedHumanJudgeLabel",
    "RecordedHumanLabelBatch",
    "TRUSTED_RUNTIME_CONTRACT_SHA256",
    "canonical_json_bytes",
    "fail_calibration",
    "finalize_report",
    "sha256_bytes",
]

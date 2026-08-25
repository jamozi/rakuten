"""Fail-closed values for the ST-0707 recorded evaluation harness.

The values carry hashes, closed status vocabularies, and aggregate counts only.
They cannot contain prompts, model outputs, credentials, human labels, provider
clients, activation instructions, or release authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import hashlib
import json
import re
from typing import NoReturn, SupportsIndex, final

from raos.domain.ai.output_validation import AiOutputValidationReport


HARNESS_VERSION = "ST0707_RECORDED_EVALUATION_HARNESS_V1"
REPORT_PROFILE = "ST0707_RECORDED_EVALUATION_REPORT_V1"
TRUSTED_RUNTIME_CONTRACT_SHA256 = (
    "55044e7b2f030298d5ee61932122e5c0821491b23189bb57b9affc8c47bc043d"
)
MAX_EVALUATION_CASES = 256
METRIC_SCALE = 1_000_000

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z", re.ASCII)
_CASE_ID = re.compile(r"AICASE-[A-Z0-9_-]{3,120}\Z", re.ASCII)
_REDACTED = "<redacted-recorded-evaluation>"


class EvaluationHarnessFailureCode(str, Enum):
    INVALID_VALUE = "INVALID_EVALUATION_HARNESS_VALUE"
    INVALID_BUNDLE = "INVALID_RECORDED_EVALUATION_BUNDLE"
    INVALID_REPORT = "INVALID_EVALUATION_HARNESS_REPORT"


@final
class EvaluationHarnessError(ValueError):
    """Sanitized failure that retains no rejected artifact material."""

    __slots__ = ("code",)

    def __init__(self, code: EvaluationHarnessFailureCode) -> None:
        if type(code) is not EvaluationHarnessFailureCode:
            raise TypeError("code must be an exact EvaluationHarnessFailureCode")
        self.code = code
        super().__init__(code.value)

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("evaluation harness errors are not serializable")


def fail_evaluation_harness(code: EvaluationHarnessFailureCode) -> NoReturn:
    raise EvaluationHarnessError(code) from None


class DatasetLockStatus(str, Enum):
    LOCKED_SYNTHETIC_NON_RELEASE = "LOCKED_SYNTHETIC_NON_RELEASE"


class DatasetProvenance(str, Enum):
    SYNTHETIC_PLUMBING_ONLY = "SYNTHETIC_PLUMBING_ONLY"


class HumanLabelStatus(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"


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


class ProposalOutcome(str, Enum):
    REFUSED_ZERO_TOLERANCE = "REFUSED_ZERO_TOLERANCE"
    REFUSED_INCOMPLETE_EVIDENCE = "REFUSED_INCOMPLETE_EVIDENCE"


class ExecutionStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


class EvaluationSplit(str, Enum):
    DEV = "DEV"
    CALIBRATION = "CALIBRATION"
    HOLDOUT = "HOLDOUT"
    ADVERSARIAL = "ADVERSARIAL"
    REGRESSION = "REGRESSION"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("evaluation harness values are not serializable")


def _sha(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_VALUE)
    return value


def _token(value: object) -> str:
    if type(value) is not str or _TOKEN.fullmatch(value) is None:
        fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_VALUE)
    return value


def _exact_int(value: object, *, maximum: int = METRIC_SCALE * 10) -> int:
    if type(value) is not int or value < 0 or value > maximum:
        fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_VALUE)
    return value


def canonical_json_bytes(value: dict[str, object]) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeEncodeError, RecursionError:
        fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_VALUE)


def sha256_bytes(value: bytes) -> str:
    if type(value) is not bytes:
        fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_VALUE)
    return hashlib.sha256(value).hexdigest()


@final
@dataclass(frozen=True, slots=True, repr=False)
class MetricThreshold(_RedactedValue):
    code: str
    kind: str
    direction: str
    unit: str
    operator: str
    threshold_micros: int

    def __post_init__(self) -> None:
        _token(self.code)
        _token(self.kind)
        _token(self.direction)
        _token(self.unit)
        if self.operator not in {"==", ">=", "<=", ">", "<"}:
            fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_VALUE)
        _exact_int(self.threshold_micros)

    def document(self) -> dict[str, object]:
        return {
            "code": self.code,
            "kind": self.kind,
            "direction": self.direction,
            "operator": self.operator,
            "threshold_micros": self.threshold_micros,
            "unit": self.unit,
        }


@final
@dataclass(frozen=True, slots=True, repr=False)
class EvaluationSuite(_RedactedValue):
    suite_code: str
    task_code: str
    risk_level: str
    minimum_adjudicated_cases: int
    required_splits: tuple[EvaluationSplit, ...]
    thresholds: tuple[MetricThreshold, ...]
    zero_tolerance_classes: tuple[str, ...]
    evaluation_catalog_sha256: str
    profile_registry_sha256: str
    st0705_runtime_contract_sha256: str
    st0705_runtime_manifest_sha256: str
    registry_sha256: str

    def __post_init__(self) -> None:
        self.require_valid()

    def require_valid(self) -> None:
        _token(self.suite_code)
        _token(self.task_code)
        _token(self.risk_level)
        if (
            type(self.minimum_adjudicated_cases) is not int
            or not 1 <= self.minimum_adjudicated_cases <= 10_000
            or type(self.required_splits) is not tuple
            or self.required_splits != tuple(EvaluationSplit)
            or type(self.thresholds) is not tuple
            or not self.thresholds
            or len(self.thresholds) > 64
            or any(type(item) is not MetricThreshold for item in self.thresholds)
            or tuple(item.code for item in self.thresholds)
            != tuple(sorted(item.code for item in self.thresholds))
            or len({item.code for item in self.thresholds}) != len(self.thresholds)
            or type(self.zero_tolerance_classes) is not tuple
            or len(self.zero_tolerance_classes) != 8
            or any(
                type(item) is not str
                or not item
                or item != item.strip()
                or len(item) > 160
                for item in self.zero_tolerance_classes
            )
            or len(set(self.zero_tolerance_classes)) != 8
        ):
            fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_VALUE)
        for digest in (
            self.evaluation_catalog_sha256,
            self.profile_registry_sha256,
            self.st0705_runtime_contract_sha256,
            self.st0705_runtime_manifest_sha256,
            self.registry_sha256,
        ):
            _sha(digest)


@final
@dataclass(frozen=True, slots=True, repr=False)
class LockedEvaluationCase(_RedactedValue):
    case_id: str
    split: EvaluationSplit
    category: str
    provenance: DatasetProvenance
    st0705_report_sha256: str
    profile_sha256: str
    validation_manifest_sha256: str
    output_sha256: str
    provider_exchange_sha256: str
    evaluation_case_sha256: str
    case_sha256: str

    def __post_init__(self) -> None:
        self.require_valid()

    def _document(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "evaluation_case_sha256": self.evaluation_case_sha256,
            "output_sha256": self.output_sha256,
            "profile_sha256": self.profile_sha256,
            "provenance": self.provenance.value,
            "provider_exchange_sha256": self.provider_exchange_sha256,
            "split": self.split.value,
            "st0705_report_sha256": self.st0705_report_sha256,
            "validation_manifest_sha256": self.validation_manifest_sha256,
        }

    def require_valid(self) -> None:
        if (
            type(self.case_id) is not str
            or _CASE_ID.fullmatch(self.case_id) is None
            or type(self.split) is not EvaluationSplit
            or self.split is not EvaluationSplit.HOLDOUT
            or type(self.provenance) is not DatasetProvenance
        ):
            fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_VALUE)
        _token(self.category)
        for digest in (
            self.st0705_report_sha256,
            self.profile_sha256,
            self.validation_manifest_sha256,
            self.output_sha256,
            self.provider_exchange_sha256,
            self.evaluation_case_sha256,
            self.case_sha256,
        ):
            _sha(digest)
        if sha256_bytes(canonical_json_bytes(self._document())) != self.case_sha256:
            fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_VALUE)


@final
@dataclass(frozen=True, slots=True, repr=False)
class LockedEvaluationDataset(_RedactedValue):
    dataset_id: str
    version: str
    status: DatasetLockStatus
    provenance: DatasetProvenance
    source_kind: str
    locked_at: str
    human_label_status: HumanLabelStatus
    label_provenance_count: int
    cases: tuple[LockedEvaluationCase, ...]
    holdout_sha256: str
    dataset_sha256: str
    release_eligible: bool = field(default=False)
    canonical_dataset: bool = field(default=False)
    representative_dataset: bool = field(default=False)
    human_labeled: bool = field(default=False)

    def __post_init__(self) -> None:
        self.require_valid()

    def _holdout_document(self) -> dict[str, object]:
        return {
            "case_sha256": [item.case_sha256 for item in self.cases],
            "dataset_id": self.dataset_id,
            "split": "HOLDOUT",
            "version": self.version,
        }

    def _document(self) -> dict[str, object]:
        return {
            "canonical_dataset": self.canonical_dataset,
            "cases": [
                item._document() | {"case_sha256": item.case_sha256}  # pyright: ignore[reportPrivateUsage]
                for item in self.cases
            ],
            "dataset_id": self.dataset_id,
            "holdout_sha256": self.holdout_sha256,
            "human_label_status": self.human_label_status.value,
            "human_labeled": self.human_labeled,
            "label_provenance": [],
            "locked_at": self.locked_at,
            "provenance": self.provenance.value,
            "release_eligible": self.release_eligible,
            "representative_dataset": self.representative_dataset,
            "source_kind": self.source_kind,
            "status": self.status.value,
            "version": self.version,
        }

    def require_valid(self) -> None:
        _token(self.dataset_id)
        _token(self.version)
        _token(self.source_kind)
        if (
            type(self.status) is not DatasetLockStatus
            or type(self.provenance) is not DatasetProvenance
            or self.provenance is not DatasetProvenance.SYNTHETIC_PLUMBING_ONLY
            or type(self.human_label_status) is not HumanLabelStatus
            or self.human_label_status is not HumanLabelStatus.UNAVAILABLE
            or type(self.label_provenance_count) is not int
            or self.label_provenance_count != 0
            or type(self.cases) is not tuple
            or not 1 <= len(self.cases) <= MAX_EVALUATION_CASES
            or any(type(item) is not LockedEvaluationCase for item in self.cases)
            or tuple(item.case_id for item in self.cases)
            != tuple(sorted(item.case_id for item in self.cases))
            or len({item.case_id for item in self.cases}) != len(self.cases)
            or any(
                value is not False
                for value in (
                    self.release_eligible,
                    self.canonical_dataset,
                    self.representative_dataset,
                    self.human_labeled,
                )
            )
            or self.locked_at != "2026-08-24T00:00:00+00:00"
        ):
            fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_VALUE)
        for item in self.cases:
            item.require_valid()
        _sha(self.holdout_sha256)
        _sha(self.dataset_sha256)
        if (
            sha256_bytes(canonical_json_bytes(self._holdout_document()))
            != self.holdout_sha256
            or sha256_bytes(canonical_json_bytes(self._document()))
            != self.dataset_sha256
        ):
            fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_VALUE)


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedEvaluationBundle(_RedactedValue):
    runtime_contract_sha256: str
    runtime_manifest_sha256: str
    suite: EvaluationSuite
    dataset: LockedEvaluationDataset
    reports: tuple[AiOutputValidationReport, ...]
    bundle_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "bundle_sha256", self._computed_sha256())
        self.require_valid()

    def _computed_sha256(self) -> str:
        if (
            type(self.suite) is not EvaluationSuite
            or type(self.dataset) is not LockedEvaluationDataset
            or type(self.reports) is not tuple
            or any(type(item) is not AiOutputValidationReport for item in self.reports)
        ):
            fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_BUNDLE)
        return sha256_bytes(
            canonical_json_bytes(
                {
                    "dataset_sha256": self.dataset.dataset_sha256,
                    "report_sha256": [
                        item.report_sha256.value for item in self.reports
                    ],
                    "runtime_contract_sha256": self.runtime_contract_sha256,
                    "runtime_manifest_sha256": self.runtime_manifest_sha256,
                    "suite_registry_sha256": self.suite.registry_sha256,
                }
            )
        )

    def require_valid(self) -> None:
        if self.runtime_contract_sha256 != TRUSTED_RUNTIME_CONTRACT_SHA256:
            fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_BUNDLE)
        _sha(self.runtime_manifest_sha256)
        self.suite.require_valid()
        self.dataset.require_valid()
        if (
            type(self.reports) is not tuple
            or len(self.reports) != len(self.dataset.cases)
            or not 1 <= len(self.reports) <= MAX_EVALUATION_CASES
        ):
            fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_BUNDLE)
        for case, report in zip(self.dataset.cases, self.reports, strict=True):
            if type(report) is not AiOutputValidationReport:
                fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_BUNDLE)
            try:
                report.require_valid()
            except Exception:
                fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_BUNDLE)
            if (
                report.report_sha256.value != case.st0705_report_sha256
                or report.task_code != self.suite.task_code
                or report.profile_sha256 is None
                or report.profile_sha256.value != case.profile_sha256
                or report.manifest_sha256 is None
                or report.manifest_sha256.value != case.validation_manifest_sha256
                or report.output_sha256 is None
                or report.output_sha256.value != case.output_sha256
                or report.provider_exchange_sha256 is None
                or report.provider_exchange_sha256.value
                != case.provider_exchange_sha256
            ):
                fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_BUNDLE)
        if self.bundle_sha256 != self._computed_sha256():
            fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_BUNDLE)


@final
@dataclass(frozen=True, slots=True, repr=False)
class MetricResult(_RedactedValue):
    code: str
    status: MetricStatus
    numerator: int | None
    denominator: int | None
    point_estimate_micros: int | None
    wilson_lower_bound_micros: int | None
    threshold_micros: int
    operator: str

    def __post_init__(self) -> None:
        _token(self.code)
        _exact_int(self.threshold_micros)
        if type(self.status) is not MetricStatus or self.operator not in {
            "==",
            ">=",
            "<=",
            ">",
            "<",
        }:
            fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_REPORT)
        values = (
            self.numerator,
            self.denominator,
            self.point_estimate_micros,
            self.wilson_lower_bound_micros,
        )
        if self.status is MetricStatus.UNAVAILABLE:
            if any(value is not None for value in values):
                fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_REPORT)
            return
        if (
            type(self.numerator) is not int
            or type(self.denominator) is not int
            or type(self.point_estimate_micros) is not int
            or type(self.wilson_lower_bound_micros) is not int
            or not 0 <= self.numerator <= self.denominator <= MAX_EVALUATION_CASES
            or self.denominator == 0
            or not 0 <= self.point_estimate_micros <= METRIC_SCALE
            or not 0 <= self.wilson_lower_bound_micros <= self.point_estimate_micros
        ):
            fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_REPORT)

    def document(self) -> dict[str, object]:
        return {
            "code": self.code,
            "denominator": self.denominator,
            "numerator": self.numerator,
            "operator": self.operator,
            "point_estimate_micros": self.point_estimate_micros,
            "status": self.status.value,
            "threshold_micros": self.threshold_micros,
            "wilson_lower_bound_micros": self.wilson_lower_bound_micros,
        }


@final
@dataclass(frozen=True, slots=True, repr=False)
class ZeroToleranceResult(_RedactedValue):
    failure_class: str
    status: MetricStatus
    observed_failures: int | None
    denominator: int | None

    def __post_init__(self) -> None:
        if (
            type(self.failure_class) is not str
            or not self.failure_class
            or self.failure_class != self.failure_class.strip()
            or len(self.failure_class) > 160
            or type(self.status) is not MetricStatus
        ):
            fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_REPORT)
        if self.status is MetricStatus.UNAVAILABLE:
            if self.observed_failures is not None or self.denominator is not None:
                fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_REPORT)
        elif (
            type(self.observed_failures) is not int
            or type(self.denominator) is not int
            or not 0
            <= self.observed_failures
            <= self.denominator
            <= MAX_EVALUATION_CASES
            or self.denominator == 0
            or (self.status is MetricStatus.PASS and self.observed_failures != 0)
            or (self.status is MetricStatus.FAIL and self.observed_failures == 0)
        ):
            fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_REPORT)

    def document(self) -> dict[str, object]:
        return {
            "denominator": self.denominator,
            "failure_class": self.failure_class,
            "observed_failures": self.observed_failures,
            "status": self.status.value,
        }


@final
@dataclass(frozen=True, slots=True, repr=False)
class EvaluationGate(_RedactedValue):
    code: str
    status: GateStatus

    def __post_init__(self) -> None:
        _token(self.code)
        if type(self.status) is not GateStatus:
            fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_REPORT)

    def document(self) -> dict[str, object]:
        return {"code": self.code, "status": self.status.value}


@final
@dataclass(frozen=True, slots=True, repr=False)
class ReleaseDecisionProposal(_RedactedValue):
    outcome: ProposalOutcome
    reasons: tuple[str, ...]
    task_code: str
    profile_sha256: str
    validation_manifest_sha256: str
    dataset_sha256: str
    holdout_sha256: str
    runtime_contract_sha256: str
    runtime_manifest_sha256: str
    resolved_model_binding_status: EvidenceStatus
    decision_kind: str = field(default="PROPOSAL")
    authority: str = field(default="NONE")
    approval_authorized: bool = field(default=False)
    activation_authorized: bool = field(default=False)
    route_mutation_authorized: bool = field(default=False)
    model_mutation_authorized: bool = field(default=False)
    publication_authorized: bool = field(default=False)
    release_authorized: bool = field(default=False)
    production_eligible: bool = field(default=False)
    external_action_count: int = field(default=0)

    def __post_init__(self) -> None:
        if (
            type(self.outcome) is not ProposalOutcome
            or type(self.reasons) is not tuple
            or not self.reasons
            or self.reasons != tuple(sorted(set(self.reasons)))
            or any(_TOKEN.fullmatch(item) is None for item in self.reasons)
            or type(self.resolved_model_binding_status) is not EvidenceStatus
            or self.resolved_model_binding_status is not EvidenceStatus.UNAVAILABLE
            or self.decision_kind != "PROPOSAL"
            or self.authority != "NONE"
            or any(
                value is not False
                for value in (
                    self.approval_authorized,
                    self.activation_authorized,
                    self.route_mutation_authorized,
                    self.model_mutation_authorized,
                    self.publication_authorized,
                    self.release_authorized,
                    self.production_eligible,
                )
            )
            or type(self.external_action_count) is not int
            or self.external_action_count != 0
        ):
            fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_REPORT)
        _token(self.task_code)
        for digest in (
            self.profile_sha256,
            self.validation_manifest_sha256,
            self.dataset_sha256,
            self.holdout_sha256,
            self.runtime_contract_sha256,
            self.runtime_manifest_sha256,
        ):
            _sha(digest)

    def document(self) -> dict[str, object]:
        return {
            "activation_authorized": self.activation_authorized,
            "approval_authorized": self.approval_authorized,
            "authority": self.authority,
            "dataset_sha256": self.dataset_sha256,
            "decision_kind": self.decision_kind,
            "external_action_count": self.external_action_count,
            "holdout_sha256": self.holdout_sha256,
            "model_mutation_authorized": self.model_mutation_authorized,
            "outcome": self.outcome.value,
            "production_eligible": self.production_eligible,
            "profile_sha256": self.profile_sha256,
            "publication_authorized": self.publication_authorized,
            "reasons": list(self.reasons),
            "release_authorized": self.release_authorized,
            "resolved_model_binding_status": self.resolved_model_binding_status.value,
            "route_mutation_authorized": self.route_mutation_authorized,
            "runtime_contract_sha256": self.runtime_contract_sha256,
            "runtime_manifest_sha256": self.runtime_manifest_sha256,
            "task_code": self.task_code,
            "validation_manifest_sha256": self.validation_manifest_sha256,
        }


@final
@dataclass(frozen=True, slots=True, repr=False)
class EvaluationHarnessReport(_RedactedValue):
    bundle_sha256: str
    dataset_sha256: str
    holdout_sha256: str
    case_count: int
    metrics: tuple[MetricResult, ...]
    zero_tolerance: tuple[ZeroToleranceResult, ...]
    gates: tuple[EvaluationGate, ...]
    human_label_status: HumanLabelStatus
    proposal: ReleaseDecisionProposal
    report_sha256: str
    harness_version: str = field(default=HARNESS_VERSION)
    report_profile: str = field(default=REPORT_PROFILE)
    formal_tst_018: ExecutionStatus = field(default=ExecutionStatus.NOT_EXECUTED)
    formal_tst_019: ExecutionStatus = field(default=ExecutionStatus.NOT_EXECUTED)
    live: ExecutionStatus = field(default=ExecutionStatus.NOT_EXECUTED)
    staging: ExecutionStatus = field(default=ExecutionStatus.NOT_EXECUTED)
    release: ExecutionStatus = field(default=ExecutionStatus.NOT_EXECUTED)
    production: ExecutionStatus = field(default=ExecutionStatus.NOT_EXECUTED)

    def _document(self, *, include_hash: bool) -> dict[str, object]:
        value: dict[str, object] = {
            "bundle_sha256": self.bundle_sha256,
            "case_count": self.case_count,
            "dataset_sha256": self.dataset_sha256,
            "formal_tst_018": self.formal_tst_018.value,
            "formal_tst_019": self.formal_tst_019.value,
            "gates": [item.document() for item in self.gates],
            "harness_version": self.harness_version,
            "holdout_sha256": self.holdout_sha256,
            "human_label_status": self.human_label_status.value,
            "live": self.live.value,
            "metrics": [item.document() for item in self.metrics],
            "production": self.production.value,
            "proposal": self.proposal.document(),
            "release": self.release.value,
            "report_profile": self.report_profile,
            "staging": self.staging.value,
            "zero_tolerance": [item.document() for item in self.zero_tolerance],
        }
        if include_hash:
            value["report_sha256"] = self.report_sha256
        return value

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        return canonical_json_bytes(self._document(include_hash=True))

    def require_valid(self) -> None:
        for digest in (self.bundle_sha256, self.dataset_sha256, self.holdout_sha256):
            _sha(digest)
        if (
            type(self.case_count) is not int
            or not 1 <= self.case_count <= MAX_EVALUATION_CASES
            or type(self.metrics) is not tuple
            or not self.metrics
            or any(type(item) is not MetricResult for item in self.metrics)
            or tuple(item.code for item in self.metrics)
            != tuple(sorted(item.code for item in self.metrics))
            or type(self.zero_tolerance) is not tuple
            or len(self.zero_tolerance) != 8
            or any(
                type(item) is not ZeroToleranceResult for item in self.zero_tolerance
            )
            or type(self.gates) is not tuple
            or not self.gates
            or any(type(item) is not EvaluationGate for item in self.gates)
            or tuple(item.code for item in self.gates)
            != tuple(sorted(item.code for item in self.gates))
            or type(self.human_label_status) is not HumanLabelStatus
            or type(self.proposal) is not ReleaseDecisionProposal
            or self.harness_version != HARNESS_VERSION
            or self.report_profile != REPORT_PROFILE
            or any(
                value is not ExecutionStatus.NOT_EXECUTED
                for value in (
                    self.formal_tst_018,
                    self.formal_tst_019,
                    self.live,
                    self.staging,
                    self.release,
                    self.production,
                )
            )
        ):
            fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_REPORT)
        _sha(self.report_sha256)
        expected = sha256_bytes(
            canonical_json_bytes(self._document(include_hash=False))
        )
        if self.report_sha256 != expected:
            fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_REPORT)


def finalize_report(report: EvaluationHarnessReport) -> EvaluationHarnessReport:
    """Bind a provisional immutable report to its canonical content hash."""

    if type(report) is not EvaluationHarnessReport:
        fail_evaluation_harness(EvaluationHarnessFailureCode.INVALID_REPORT)
    digest = sha256_bytes(
        canonical_json_bytes(
            report._document(include_hash=False)  # pyright: ignore[reportPrivateUsage]
        )
    )
    finalized = replace(report, report_sha256=digest)
    finalized.require_valid()
    return finalized


__all__ = [
    "DatasetLockStatus",
    "DatasetProvenance",
    "EvaluationGate",
    "EvaluationHarnessError",
    "EvaluationHarnessFailureCode",
    "EvaluationHarnessReport",
    "EvaluationSplit",
    "EvaluationSuite",
    "EvidenceStatus",
    "ExecutionStatus",
    "GateStatus",
    "HARNESS_VERSION",
    "HumanLabelStatus",
    "LockedEvaluationCase",
    "LockedEvaluationDataset",
    "MAX_EVALUATION_CASES",
    "METRIC_SCALE",
    "MetricResult",
    "MetricStatus",
    "MetricThreshold",
    "ProposalOutcome",
    "REPORT_PROFILE",
    "RecordedEvaluationBundle",
    "ReleaseDecisionProposal",
    "TRUSTED_RUNTIME_CONTRACT_SHA256",
    "ZeroToleranceResult",
    "canonical_json_bytes",
    "fail_evaluation_harness",
    "finalize_report",
    "sha256_bytes",
]

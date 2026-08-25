"""Maximum-safe recorded research evaluation values for Canonical ST-1908.

The module represents only sanitized metadata, aggregate evaluation metrics,
and synthetic cost projections.  It cannot represent a provider request, a
training job, raw training examples, a route mutation, or a release decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import hashlib
import json
import re
from typing import Final, NoReturn, SupportsIndex


FINE_TUNING_CONTRACT_VERSION: Final = "1.0.0"
FINE_TUNING_METHOD_VERSION: Final = "RAOS_ST1908_RECORDED_SYNTHETIC_PARETO_GUARD_V1"
FINE_TUNING_PARSER_VERSION: Final = "st1908-recorded-fine-tuning-json.v1"
FINE_TUNING_FIXTURE_PROFILE: Final = (
    "RAOS_ST1908_RECORDED_SYNTHETIC_FINE_TUNING_EVALUATION_V1"
)
MINIMUM_HIGH_RISK_HOLDOUT_CASES: Final = 150
METRIC_SCALE: Final = 1_000_000
JPY_MICROS_SCALE: Final = 1_000_000
MAX_SOURCE_BYTES: Final = 1_048_576
MAX_CASES: Final = 100_000
MAX_COST_JPY_MICROS: Final = 10**15
MAX_WORKLOAD_REQUESTS: Final = 10**9

TRUSTED_ST0707_CONTRACT_SHA256: Final = (
    "0ec1398be1ce82fcfe71929b9f1dbfb45b7041f69869a6f64030ecc728be8e49"
)
TRUSTED_ST0707_MANIFEST_SHA256: Final = (
    "4652b7e618da23110636d6747dbcda1ccf0aad94c531e02972632ec01822927e"
)
TRUSTED_ST0707_SUITE_SHA256: Final = (
    "3faad9c9d3a9130f1f9d9cca0b1e075d5befdd49432dbf00e750941ae56e91e0"
)
TRUSTED_ST0707_HOLDOUT_SHA256: Final = (
    "8985e548590b5ac6d8bdc8d1ad457e39b45f547c7838f0cd1c13e13fb5f35df6"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}\Z", re.ASCII)
_RECORDING_ID = re.compile(r"[a-z0-9][a-z0-9_-]{1,63}\Z", re.ASCII)
_TASK_CODE = re.compile(r"ai\.[a-z0-9_]+\.v[0-9]+\Z", re.ASCII)
_REDACTED: Final = "<redacted-fine-tuning-evaluation>"


class FineTuningScope(str, Enum):
    """Closed feature states; no live or activation state exists."""

    DISABLED = "DISABLED"
    RECORDED_SYNTHETIC_EVALUATION_ONLY = "RECORDED_SYNTHETIC_EVALUATION_ONLY"


DEFAULT_FINE_TUNING_SCOPE: Final = FineTuningScope.DISABLED


class EvidenceStatus(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"
    RECORDED_SYNTHETIC_VERIFIED = "RECORDED_SYNTHETIC_VERIFIED"


class DatasetRightsStatus(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"
    RECORDED_SYNTHETIC_RIGHTS_REVIEWED = "RECORDED_SYNTHETIC_RIGHTS_REVIEWED"


class DataGovernanceStatus(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"
    RECORDED_SYNTHETIC_GOVERNANCE_REVIEWED = "RECORDED_SYNTHETIC_GOVERNANCE_REVIEWED"


class SourceKind(str, Enum):
    SYNTHETIC = "SYNTHETIC"
    SANITIZED_PRODUCTION_FAILURE = "SANITIZED_PRODUCTION_FAILURE"
    LICENSED_EDITORIAL_EXAMPLE = "LICENSED_EDITORIAL_EXAMPLE"
    HUMAN_AUTHORED_ADVERSARIAL = "HUMAN_AUTHORED_ADVERSARIAL"


class EvaluationRole(str, Enum):
    BASELINE = "BASELINE"
    CANDIDATE = "CANDIDATE"


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"


class FineTuningOutcome(str, Enum):
    REFUSED_ZERO_TOLERANCE = "REFUSED_ZERO_TOLERANCE"
    REFUSED_NOT_BENEFICIAL = "REFUSED_NOT_BENEFICIAL"
    REFUSED_UNAVAILABLE_EVIDENCE = "REFUSED_UNAVAILABLE_EVIDENCE"


class FineTuningFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    FEATURE_DISABLED = "FEATURE_DISABLED"
    DEPENDENCY_CONTRACT_DRIFT = "DEPENDENCY_CONTRACT_DRIFT"
    SOURCE_BYTES_MISMATCH = "SOURCE_BYTES_MISMATCH"
    SOURCE_DOCUMENT_INVALID = "SOURCE_DOCUMENT_INVALID"
    SOURCE_EXHAUSTED = "SOURCE_EXHAUSTED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_RESULT_INVALID = "SOURCE_RESULT_INVALID"
    REPORT_INVALID = "REPORT_INVALID"


class FineTuningFailure(ValueError):
    """Closed failure that never retains rejected source material."""

    __slots__ = ("code",)

    def __init__(self, code: FineTuningFailureCode) -> None:
        if type(code) is not FineTuningFailureCode:
            raise TypeError("invalid fine-tuning failure code")
        self.code = code
        super().__init__(code.value)

    def __repr__(self) -> str:
        return f"FineTuningFailure(code={self.code.value})"

    def __str__(self) -> str:
        return self.code.value

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("fine-tuning failures cannot be serialized")


def fail_fine_tuning(
    code: FineTuningFailureCode = FineTuningFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise FineTuningFailure(code) from None


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("fine-tuning values cannot be serialized")


def canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii", errors="strict")
    except TypeError, ValueError, UnicodeEncodeError, RecursionError:
        fail_fine_tuning()


def sha256_bytes(value: bytes) -> str:
    if type(value) is not bytes:
        fail_fine_tuning()
    return hashlib.sha256(value).hexdigest()


def _sha(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_fine_tuning()
    return value


def _optional_sha(value: object) -> str | None:
    if value is None:
        return None
    return _sha(value)


def _identifier(value: object) -> str:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        fail_fine_tuning()
    return value


def _task_code(value: object) -> str:
    if type(value) is not str or _TASK_CODE.fullmatch(value) is None:
        fail_fine_tuning()
    return value


def _count(value: object, maximum: int = MAX_CASES) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        fail_fine_tuning()
    return value


def _optional_metric(value: object) -> int | None:
    if value is None:
        return None
    return _count(value, METRIC_SCALE)


def _optional_cost(value: object) -> int | None:
    if value is None:
        return None
    return _count(value, MAX_COST_JPY_MICROS)


@dataclass(frozen=True, slots=True, repr=False)
class DatasetSourceCount(_RedactedValue):
    kind: SourceKind
    count: int

    def __post_init__(self) -> None:
        if type(self.kind) is not SourceKind:
            fail_fine_tuning()
        _count(self.count)

    def payload(self) -> dict[str, object]:
        return {"count": self.count, "kind": self.kind.value}


@dataclass(frozen=True, slots=True, repr=False)
class DatasetRightsEvidence(_RedactedValue):
    dataset_id: str
    dataset_sha256: str
    source_inventory_sha256: str
    holdout_sha256: str
    case_count: int
    source_counts: tuple[DatasetSourceCount, ...]
    rights_status: DatasetRightsStatus
    license_review_sha256: str | None
    governance_status: DataGovernanceStatus
    data_inventory_sha256: str | None
    retention_policy_sha256: str | None
    deletion_policy_sha256: str | None
    representative: bool
    holdout_locked: bool
    holdout_compromised: bool
    personal_data_present: bool = False
    rakuten_review_body_present: bool = False
    unlicensed_content_present: bool = False
    secret_present: bool = False
    release_eligible: bool = False

    def __post_init__(self) -> None:
        _identifier(self.dataset_id)
        _sha(self.dataset_sha256)
        _sha(self.source_inventory_sha256)
        _sha(self.holdout_sha256)
        _count(self.case_count)
        if (
            type(self.source_counts) is not tuple
            or any(type(row) is not DatasetSourceCount for row in self.source_counts)
            or tuple(row.kind for row in self.source_counts) != tuple(SourceKind)
            or sum(row.count for row in self.source_counts) != self.case_count
            or type(self.rights_status) is not DatasetRightsStatus
            or type(self.governance_status) is not DataGovernanceStatus
            or any(
                type(value) is not bool
                for value in (
                    self.representative,
                    self.holdout_locked,
                    self.holdout_compromised,
                    self.personal_data_present,
                    self.rakuten_review_body_present,
                    self.unlicensed_content_present,
                    self.secret_present,
                    self.release_eligible,
                )
            )
            or self.personal_data_present
            or self.rakuten_review_body_present
            or self.unlicensed_content_present
            or self.secret_present
            or self.release_eligible
        ):
            fail_fine_tuning()
        license_hash = _optional_sha(self.license_review_sha256)
        inventory_hash = _optional_sha(self.data_inventory_sha256)
        retention_hash = _optional_sha(self.retention_policy_sha256)
        deletion_hash = _optional_sha(self.deletion_policy_sha256)
        if (
            self.rights_status is DatasetRightsStatus.UNAVAILABLE
            and license_hash is not None
        ) or (
            self.rights_status is DatasetRightsStatus.RECORDED_SYNTHETIC_RIGHTS_REVIEWED
            and license_hash is None
        ):
            fail_fine_tuning()
        governance_hashes = (inventory_hash, retention_hash, deletion_hash)
        if (
            self.governance_status is DataGovernanceStatus.UNAVAILABLE
            and any(value is not None for value in governance_hashes)
        ) or (
            self.governance_status
            is DataGovernanceStatus.RECORDED_SYNTHETIC_GOVERNANCE_REVIEWED
            and any(value is None for value in governance_hashes)
        ):
            fail_fine_tuning()

    def payload(self) -> dict[str, object]:
        return {
            "case_count": self.case_count,
            "data_inventory_sha256": self.data_inventory_sha256,
            "dataset_id": self.dataset_id,
            "dataset_sha256": self.dataset_sha256,
            "deletion_policy_sha256": self.deletion_policy_sha256,
            "governance_status": self.governance_status.value,
            "holdout_compromised": self.holdout_compromised,
            "holdout_locked": self.holdout_locked,
            "holdout_sha256": self.holdout_sha256,
            "license_review_sha256": self.license_review_sha256,
            "personal_data_present": self.personal_data_present,
            "rakuten_review_body_present": self.rakuten_review_body_present,
            "release_eligible": self.release_eligible,
            "representative": self.representative,
            "retention_policy_sha256": self.retention_policy_sha256,
            "rights_status": self.rights_status.value,
            "secret_present": self.secret_present,
            "source_counts": [row.payload() for row in self.source_counts],
            "source_inventory_sha256": self.source_inventory_sha256,
            "unlicensed_content_present": self.unlicensed_content_present,
        }


@dataclass(frozen=True, slots=True, repr=False)
class OptimizationEvidence(_RedactedValue):
    status: EvidenceStatus
    evidence_sha256: str | None
    prompt_optimization_exhausted: bool
    route_optimization_exhausted: bool
    repeated_error_code: str | None
    repeated_error_count: int | None

    def __post_init__(self) -> None:
        if (
            type(self.status) is not EvidenceStatus
            or type(self.prompt_optimization_exhausted) is not bool
            or type(self.route_optimization_exhausted) is not bool
        ):
            fail_fine_tuning()
        evidence_hash = _optional_sha(self.evidence_sha256)
        if self.status is EvidenceStatus.UNAVAILABLE:
            if (
                evidence_hash is not None
                or self.repeated_error_code is not None
                or self.repeated_error_count is not None
                or self.prompt_optimization_exhausted
                or self.route_optimization_exhausted
            ):
                fail_fine_tuning()
            return
        _identifier(self.repeated_error_code)
        if (
            evidence_hash is None
            or not self.prompt_optimization_exhausted
            or not self.route_optimization_exhausted
            or type(self.repeated_error_count) is not int
            or not 2 <= self.repeated_error_count <= MAX_CASES
        ):
            fail_fine_tuning()

    def payload(self) -> dict[str, object]:
        return {
            "evidence_sha256": self.evidence_sha256,
            "prompt_optimization_exhausted": self.prompt_optimization_exhausted,
            "repeated_error_code": self.repeated_error_code,
            "repeated_error_count": self.repeated_error_count,
            "route_optimization_exhausted": self.route_optimization_exhausted,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True, repr=False)
class AggregateModelEvaluation(_RedactedValue):
    role: EvaluationRole
    status: EvidenceStatus
    evaluation_sha256: str | None
    model_binding_sha256: str | None
    dataset_sha256: str
    holdout_sha256: str
    sample_size: int | None
    schema_valid_rate_micros: int | None
    critical_claim_support_rate_micros: int | None
    human_acceptance_rate_micros: int | None
    zero_tolerance_failures: int | None
    actual_execution: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.role) is not EvaluationRole
            or type(self.status) is not EvidenceStatus
            or type(self.actual_execution) is not bool
            or self.actual_execution
        ):
            fail_fine_tuning()
        _sha(self.dataset_sha256)
        _sha(self.holdout_sha256)
        values = (
            _optional_sha(self.evaluation_sha256),
            _optional_sha(self.model_binding_sha256),
            self.sample_size,
            _optional_metric(self.schema_valid_rate_micros),
            _optional_metric(self.critical_claim_support_rate_micros),
            _optional_metric(self.human_acceptance_rate_micros),
            self.zero_tolerance_failures,
        )
        if self.status is EvidenceStatus.UNAVAILABLE:
            if any(value is not None for value in values):
                fail_fine_tuning()
            return
        if (
            any(value is None for value in values)
            or type(self.sample_size) is not int
            or not 1 <= self.sample_size <= MAX_CASES
            or type(self.zero_tolerance_failures) is not int
            or not 0 <= self.zero_tolerance_failures <= self.sample_size
        ):
            fail_fine_tuning()

    def payload(self) -> dict[str, object]:
        return {
            "actual_execution": self.actual_execution,
            "critical_claim_support_rate_micros": (
                self.critical_claim_support_rate_micros
            ),
            "dataset_sha256": self.dataset_sha256,
            "evaluation_sha256": self.evaluation_sha256,
            "holdout_sha256": self.holdout_sha256,
            "human_acceptance_rate_micros": self.human_acceptance_rate_micros,
            "model_binding_sha256": self.model_binding_sha256,
            "role": self.role.value,
            "sample_size": self.sample_size,
            "schema_valid_rate_micros": self.schema_valid_rate_micros,
            "status": self.status.value,
            "zero_tolerance_failures": self.zero_tolerance_failures,
        }


@dataclass(frozen=True, slots=True, repr=False)
class CostEvidence(_RedactedValue):
    status: EvidenceStatus
    evidence_sha256: str | None
    forecast_sha256: str | None
    workload_requests: int | None
    baseline_inference_jpy_micros_per_request: int | None
    candidate_inference_jpy_micros_per_request: int | None
    training_jpy_micros: int | None
    curation_jpy_micros: int | None
    evaluation_jpy_micros: int | None
    human_labor_jpy_micros: int | None
    actual_cost: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.status) is not EvidenceStatus
            or type(self.actual_cost) is not bool
            or self.actual_cost
        ):
            fail_fine_tuning()
        values = (
            _optional_sha(self.evidence_sha256),
            _optional_sha(self.forecast_sha256),
            self.workload_requests,
            _optional_cost(self.baseline_inference_jpy_micros_per_request),
            _optional_cost(self.candidate_inference_jpy_micros_per_request),
            _optional_cost(self.training_jpy_micros),
            _optional_cost(self.curation_jpy_micros),
            _optional_cost(self.evaluation_jpy_micros),
            _optional_cost(self.human_labor_jpy_micros),
        )
        if self.status is EvidenceStatus.UNAVAILABLE:
            if any(value is not None for value in values):
                fail_fine_tuning()
            return
        if (
            any(value is None for value in values)
            or type(self.workload_requests) is not int
            or not 1 <= self.workload_requests <= MAX_WORKLOAD_REQUESTS
        ):
            fail_fine_tuning()

    def payload(self) -> dict[str, object]:
        return {
            "actual_cost": self.actual_cost,
            "baseline_inference_jpy_micros_per_request": (
                self.baseline_inference_jpy_micros_per_request
            ),
            "candidate_inference_jpy_micros_per_request": (
                self.candidate_inference_jpy_micros_per_request
            ),
            "curation_jpy_micros": self.curation_jpy_micros,
            "evaluation_jpy_micros": self.evaluation_jpy_micros,
            "evidence_sha256": self.evidence_sha256,
            "forecast_sha256": self.forecast_sha256,
            "human_labor_jpy_micros": self.human_labor_jpy_micros,
            "status": self.status.value,
            "training_jpy_micros": self.training_jpy_micros,
            "workload_requests": self.workload_requests,
        }


@dataclass(frozen=True, slots=True, repr=False)
class FineTuningEvaluationCommand(_RedactedValue):
    recording_id: str
    source_sha256: str
    source_bytes: bytes
    scope: FineTuningScope
    method_version: str = FINE_TUNING_METHOD_VERSION
    parser_version: str = FINE_TUNING_PARSER_VERSION
    st0707_contract_sha256: str = TRUSTED_ST0707_CONTRACT_SHA256
    st0707_manifest_sha256: str = TRUSTED_ST0707_MANIFEST_SHA256
    st0707_suite_sha256: str = TRUSTED_ST0707_SUITE_SHA256
    st0707_holdout_sha256: str = TRUSTED_ST0707_HOLDOUT_SHA256

    def __post_init__(self) -> None:
        if (
            type(self.recording_id) is not str
            or _RECORDING_ID.fullmatch(self.recording_id) is None
            or type(self.source_bytes) is not bytes
            or not 1 <= len(self.source_bytes) <= MAX_SOURCE_BYTES
            or type(self.scope) is not FineTuningScope
            or self.method_version != FINE_TUNING_METHOD_VERSION
            or self.parser_version != FINE_TUNING_PARSER_VERSION
        ):
            fail_fine_tuning()
        _sha(self.source_sha256)
        if sha256_bytes(self.source_bytes) != self.source_sha256:
            fail_fine_tuning(FineTuningFailureCode.SOURCE_BYTES_MISMATCH)
        if (
            self.st0707_contract_sha256 != TRUSTED_ST0707_CONTRACT_SHA256
            or self.st0707_manifest_sha256 != TRUSTED_ST0707_MANIFEST_SHA256
            or self.st0707_suite_sha256 != TRUSTED_ST0707_SUITE_SHA256
            or self.st0707_holdout_sha256 != TRUSTED_ST0707_HOLDOUT_SHA256
        ):
            fail_fine_tuning(FineTuningFailureCode.DEPENDENCY_CONTRACT_DRIFT)


@dataclass(frozen=True, slots=True, repr=False)
class RecordedFineTuningBundle(_RedactedValue):
    recording_id: str
    fixture_profile: str
    task_code: str
    candidate_id: str
    synthetic: bool
    actual_training_executed: bool
    dataset: DatasetRightsEvidence
    optimization: OptimizationEvidence
    baseline: AggregateModelEvaluation
    candidate: AggregateModelEvaluation
    cost: CostEvidence
    bundle_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.recording_id) is not str
            or _RECORDING_ID.fullmatch(self.recording_id) is None
            or self.fixture_profile != FINE_TUNING_FIXTURE_PROFILE
            or type(self.synthetic) is not bool
            or not self.synthetic
            or type(self.actual_training_executed) is not bool
            or self.actual_training_executed
        ):
            fail_fine_tuning()
        _task_code(self.task_code)
        _identifier(self.candidate_id)
        if (
            type(self.dataset) is not DatasetRightsEvidence
            or type(self.optimization) is not OptimizationEvidence
            or type(self.baseline) is not AggregateModelEvaluation
            or type(self.candidate) is not AggregateModelEvaluation
            or type(self.cost) is not CostEvidence
            or self.baseline.role is not EvaluationRole.BASELINE
            or self.candidate.role is not EvaluationRole.CANDIDATE
            or self.baseline.dataset_sha256 != self.dataset.dataset_sha256
            or self.candidate.dataset_sha256 != self.dataset.dataset_sha256
            or self.baseline.holdout_sha256 != self.dataset.holdout_sha256
            or self.candidate.holdout_sha256 != self.dataset.holdout_sha256
        ):
            fail_fine_tuning()
        object.__setattr__(
            self,
            "bundle_sha256",
            sha256_bytes(canonical_json_bytes(self.payload())),
        )

    def payload(self) -> dict[str, object]:
        return {
            "actual_training_executed": self.actual_training_executed,
            "baseline": self.baseline.payload(),
            "candidate": self.candidate.payload(),
            "candidate_id": self.candidate_id,
            "cost": self.cost.payload(),
            "dataset": self.dataset.payload(),
            "fixture_profile": self.fixture_profile,
            "optimization": self.optimization.payload(),
            "recording_id": self.recording_id,
            "synthetic": self.synthetic,
            "task_code": self.task_code,
        }

    def require_valid(self) -> None:
        if (
            type(self.dataset) is not DatasetRightsEvidence
            or type(self.dataset.source_counts) is not tuple
            or any(
                type(row) is not DatasetSourceCount
                for row in self.dataset.source_counts
            )
            or type(self.optimization) is not OptimizationEvidence
            or type(self.baseline) is not AggregateModelEvaluation
            or type(self.candidate) is not AggregateModelEvaluation
            or type(self.cost) is not CostEvidence
        ):
            fail_fine_tuning(FineTuningFailureCode.SOURCE_RESULT_INVALID)
        dataset = DatasetRightsEvidence(
            dataset_id=self.dataset.dataset_id,
            dataset_sha256=self.dataset.dataset_sha256,
            source_inventory_sha256=self.dataset.source_inventory_sha256,
            holdout_sha256=self.dataset.holdout_sha256,
            case_count=self.dataset.case_count,
            source_counts=tuple(
                DatasetSourceCount(kind=row.kind, count=row.count)
                for row in self.dataset.source_counts
            ),
            rights_status=self.dataset.rights_status,
            license_review_sha256=self.dataset.license_review_sha256,
            governance_status=self.dataset.governance_status,
            data_inventory_sha256=self.dataset.data_inventory_sha256,
            retention_policy_sha256=self.dataset.retention_policy_sha256,
            deletion_policy_sha256=self.dataset.deletion_policy_sha256,
            representative=self.dataset.representative,
            holdout_locked=self.dataset.holdout_locked,
            holdout_compromised=self.dataset.holdout_compromised,
            personal_data_present=self.dataset.personal_data_present,
            rakuten_review_body_present=self.dataset.rakuten_review_body_present,
            unlicensed_content_present=self.dataset.unlicensed_content_present,
            secret_present=self.dataset.secret_present,
            release_eligible=self.dataset.release_eligible,
        )
        optimization = OptimizationEvidence(
            status=self.optimization.status,
            evidence_sha256=self.optimization.evidence_sha256,
            prompt_optimization_exhausted=(
                self.optimization.prompt_optimization_exhausted
            ),
            route_optimization_exhausted=(
                self.optimization.route_optimization_exhausted
            ),
            repeated_error_code=self.optimization.repeated_error_code,
            repeated_error_count=self.optimization.repeated_error_count,
        )

        def evaluation(value: AggregateModelEvaluation) -> AggregateModelEvaluation:
            return AggregateModelEvaluation(
                role=value.role,
                status=value.status,
                evaluation_sha256=value.evaluation_sha256,
                model_binding_sha256=value.model_binding_sha256,
                dataset_sha256=value.dataset_sha256,
                holdout_sha256=value.holdout_sha256,
                sample_size=value.sample_size,
                schema_valid_rate_micros=value.schema_valid_rate_micros,
                critical_claim_support_rate_micros=(
                    value.critical_claim_support_rate_micros
                ),
                human_acceptance_rate_micros=value.human_acceptance_rate_micros,
                zero_tolerance_failures=value.zero_tolerance_failures,
                actual_execution=value.actual_execution,
            )

        cost = CostEvidence(
            status=self.cost.status,
            evidence_sha256=self.cost.evidence_sha256,
            forecast_sha256=self.cost.forecast_sha256,
            workload_requests=self.cost.workload_requests,
            baseline_inference_jpy_micros_per_request=(
                self.cost.baseline_inference_jpy_micros_per_request
            ),
            candidate_inference_jpy_micros_per_request=(
                self.cost.candidate_inference_jpy_micros_per_request
            ),
            training_jpy_micros=self.cost.training_jpy_micros,
            curation_jpy_micros=self.cost.curation_jpy_micros,
            evaluation_jpy_micros=self.cost.evaluation_jpy_micros,
            human_labor_jpy_micros=self.cost.human_labor_jpy_micros,
            actual_cost=self.cost.actual_cost,
        )
        candidate = RecordedFineTuningBundle(
            recording_id=self.recording_id,
            fixture_profile=self.fixture_profile,
            task_code=self.task_code,
            candidate_id=self.candidate_id,
            synthetic=self.synthetic,
            actual_training_executed=self.actual_training_executed,
            dataset=dataset,
            optimization=optimization,
            baseline=evaluation(self.baseline),
            candidate=evaluation(self.candidate),
            cost=cost,
        )
        if candidate.bundle_sha256 != self.bundle_sha256:
            fail_fine_tuning(FineTuningFailureCode.SOURCE_RESULT_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class EvaluationGate(_RedactedValue):
    code: str
    status: GateStatus

    def __post_init__(self) -> None:
        _identifier(self.code)
        if type(self.status) is not GateStatus:
            fail_fine_tuning(FineTuningFailureCode.REPORT_INVALID)

    def payload(self) -> dict[str, object]:
        return {"code": self.code, "status": self.status.value}


@dataclass(frozen=True, slots=True, repr=False)
class FineTuningEvaluationReport(_RedactedValue):
    bundle_sha256: str
    outcome: FineTuningOutcome
    reasons: tuple[str, ...]
    gates: tuple[EvaluationGate, ...]
    quality_gain_micros: int | None
    baseline_lifecycle_cost_jpy_micros: int | None
    candidate_lifecycle_cost_jpy_micros: int | None
    lifecycle_savings_jpy_micros: int | None
    report_sha256: str
    decision_kind: str = "RESEARCH_EVALUATION_ONLY"
    authority: str = "NONE"
    consideration_candidate: bool = False
    training_authorized: bool = False
    provider_call_authorized: bool = False
    model_or_route_mutation_authorized: bool = False
    editorial_mutation_authorized: bool = False
    recommendation_mutation_authorized: bool = False
    publication_snapshot_mutation_authorized: bool = False
    publication_authorized: bool = False
    release_authorized: bool = False
    production_eligible: bool = False
    external_action_count: int = 0

    def __post_init__(self) -> None:
        _sha(self.bundle_sha256)
        _sha(self.report_sha256)
        if (
            type(self.outcome) is not FineTuningOutcome
            or type(self.reasons) is not tuple
            or not self.reasons
            or self.reasons != tuple(sorted(set(self.reasons)))
            or any(_IDENTIFIER.fullmatch(reason) is None for reason in self.reasons)
            or type(self.gates) is not tuple
            or not self.gates
            or tuple(gate.code for gate in self.gates)
            != tuple(sorted(set(gate.code for gate in self.gates)))
            or self.decision_kind != "RESEARCH_EVALUATION_ONLY"
            or self.authority != "NONE"
            or any(
                value is not False
                for value in (
                    self.consideration_candidate,
                    self.training_authorized,
                    self.provider_call_authorized,
                    self.model_or_route_mutation_authorized,
                    self.editorial_mutation_authorized,
                    self.recommendation_mutation_authorized,
                    self.publication_snapshot_mutation_authorized,
                    self.publication_authorized,
                    self.release_authorized,
                    self.production_eligible,
                )
            )
            or self.external_action_count != 0
        ):
            fail_fine_tuning(FineTuningFailureCode.REPORT_INVALID)
        _optional_metric(self.quality_gain_micros)
        _optional_cost(self.baseline_lifecycle_cost_jpy_micros)
        _optional_cost(self.candidate_lifecycle_cost_jpy_micros)
        _optional_cost(self.lifecycle_savings_jpy_micros)
        numeric = (
            self.quality_gain_micros,
            self.baseline_lifecycle_cost_jpy_micros,
            self.candidate_lifecycle_cost_jpy_micros,
            self.lifecycle_savings_jpy_micros,
        )
        if any(value is None for value in numeric) and any(
            value is not None for value in numeric
        ):
            fail_fine_tuning(FineTuningFailureCode.REPORT_INVALID)

    def payload(self, *, include_hash: bool = True) -> dict[str, object]:
        result: dict[str, object] = {
            "authority": self.authority,
            "baseline_lifecycle_cost_jpy_micros": (
                self.baseline_lifecycle_cost_jpy_micros
            ),
            "bundle_sha256": self.bundle_sha256,
            "candidate_lifecycle_cost_jpy_micros": (
                self.candidate_lifecycle_cost_jpy_micros
            ),
            "consideration_candidate": self.consideration_candidate,
            "decision_kind": self.decision_kind,
            "editorial_mutation_authorized": self.editorial_mutation_authorized,
            "external_action_count": self.external_action_count,
            "gates": [gate.payload() for gate in self.gates],
            "lifecycle_savings_jpy_micros": self.lifecycle_savings_jpy_micros,
            "model_or_route_mutation_authorized": (
                self.model_or_route_mutation_authorized
            ),
            "outcome": self.outcome.value,
            "provider_call_authorized": self.provider_call_authorized,
            "publication_authorized": self.publication_authorized,
            "publication_snapshot_mutation_authorized": (
                self.publication_snapshot_mutation_authorized
            ),
            "production_eligible": self.production_eligible,
            "quality_gain_micros": self.quality_gain_micros,
            "reasons": list(self.reasons),
            "recommendation_mutation_authorized": (
                self.recommendation_mutation_authorized
            ),
            "release_authorized": self.release_authorized,
            "training_authorized": self.training_authorized,
        }
        if include_hash:
            result["report_sha256"] = self.report_sha256
        return result

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.payload())


def finalize_report(report: FineTuningEvaluationReport) -> FineTuningEvaluationReport:
    expected = sha256_bytes(canonical_json_bytes(report.payload(include_hash=False)))
    candidate = replace(report, report_sha256=expected)
    if (
        sha256_bytes(canonical_json_bytes(candidate.payload(include_hash=False)))
        != expected
    ):
        fail_fine_tuning(FineTuningFailureCode.REPORT_INVALID)
    return candidate


def report_projection(report: FineTuningEvaluationReport) -> dict[str, object]:
    return {
        "document": {
            "authority": "NONE",
            "default_enabled": False,
            "id": "RAOS-ST1908-FINE-TUNING-EVALUATION-REPORT-001",
            "production_eligible": False,
            "status": "LOCAL_IMPLEMENTATION_COMPLETE",
            "story_id": "ST-1908",
            "version": "1.0.0",
        },
        "formal_status": {
            "canonical": "DEFERRED_POST_MVP",
            "formal_tst_032": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
        },
        "report": report.payload(),
    }


__all__ = (
    "DEFAULT_FINE_TUNING_SCOPE",
    "FINE_TUNING_CONTRACT_VERSION",
    "FINE_TUNING_FIXTURE_PROFILE",
    "FINE_TUNING_METHOD_VERSION",
    "FINE_TUNING_PARSER_VERSION",
    "MAX_SOURCE_BYTES",
    "MINIMUM_HIGH_RISK_HOLDOUT_CASES",
    "AggregateModelEvaluation",
    "CostEvidence",
    "DataGovernanceStatus",
    "DatasetRightsEvidence",
    "DatasetRightsStatus",
    "DatasetSourceCount",
    "EvaluationGate",
    "EvaluationRole",
    "EvidenceStatus",
    "FineTuningEvaluationCommand",
    "FineTuningEvaluationReport",
    "FineTuningFailure",
    "FineTuningFailureCode",
    "FineTuningOutcome",
    "FineTuningScope",
    "GateStatus",
    "OptimizationEvidence",
    "RecordedFineTuningBundle",
    "SourceKind",
    "TRUSTED_ST0707_CONTRACT_SHA256",
    "TRUSTED_ST0707_HOLDOUT_SHA256",
    "TRUSTED_ST0707_MANIFEST_SHA256",
    "TRUSTED_ST0707_SUITE_SHA256",
    "canonical_json_bytes",
    "fail_fine_tuning",
    "finalize_report",
    "report_projection",
    "sha256_bytes",
)

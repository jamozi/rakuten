"""Explicit AI relation states and aggregate compositions for ST-0308."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
import re
from typing import ClassVar, NoReturn
from uuid import UUID

from raos.domain.ai.enums import (
    AiAttemptStatus,
    AiAttemptValidationStatus,
    AiJobStatus,
    AiTaskDefinitionRiskLevel,
    AiTaskDefinitionStatus,
    EvaluationCaseExpectedDisposition,
    EvaluationCaseResultDisposition,
    EvaluationCaseResultStatus,
    EvaluationCaseRiskLevel,
    EvaluationCaseSplit,
    EvaluationDatasetStatus,
    EvaluationResultMetricCode,
    EvaluationResultThresholdOperator,
    EvaluationRunStatus,
    EvaluationSuiteRiskLevel,
    EvaluationSuiteStatus,
    HumanEvaluationDecision,
    JudgeCalibrationStatus,
    ModelDefinitionStatus,
    ModelRouteVersionStatus,
    OutputSchemaVersionStatus,
    PromptVersionPolicyTestStatus,
    PromptVersionStatus,
    ReleaseApprovalPhase,
    ReleaseDecisionReleaseScope,
    ReleaseDecisionRollbackStrategy,
    ReleaseDecisionStatus,
)
from raos.domain.ai.ids import (
    AiAttemptId,
    AiJobId,
    AiTaskDefinitionId,
    EvaluationCaseId,
    EvaluationCaseResultId,
    EvaluationDatasetVersionId,
    EvaluationResultId,
    EvaluationRunId,
    EvaluationSuiteId,
    HumanEvaluationId,
    JudgeCalibrationId,
    ModelDefinitionId,
    ModelRouteVersionId,
    OutputSchemaVersionId,
    PromptVersionId,
    ReleaseApprovalId,
    ReleaseDecisionId,
    UsageCostId,
)
from raos.domain.ai.values import (
    AiAttemptRequestConfigJson,
    AiJobRequestConfigJson,
    EvaluationCaseMetadataJson,
    EvaluationCaseResultGraderSummaryJson,
    EvaluationCaseResultZeroToleranceEvidenceJson,
    EvaluationDatasetVersionSplitPolicyJson,
    EvaluationResultDetailsJson,
    EvaluationSuiteSuiteConfigJson,
    HumanEvaluationScoresJson,
    ModelDefinitionCapabilitiesJson,
    ModelDefinitionProviderMetadataJson,
    ModelRouteVersionRouteConfigJson,
)
from raos.domain.editorial.ids import (
    ArticlePlanId,
    ArticleVersionId,
)
from raos.domain.evidence.ids import (
    SourcePacketVersionId,
)
from raos.domain.iam.ids import (
    PrincipalId,
)
from raos.domain.ops.ids import (
    JobId,
    ObjectArtifactId,
)
from raos.domain.policy.ids import (
    PolicyBundleId,
)
from raos.domain.shared.identity import (
    RunId,
)
from raos.domain.shared.persistence import (
    AggregateVersion,
    AwareUtcDateTime,
    GitCommitDigest,
    Sha256Digest,
    YenMinor,
)
from raos.domain.shared.events import DomainEvent
from raos.domain.shared.identity import EntityId
from raos.domain.shared.persistence import PendingEventBuffer


_MAX_BIGINT = (1 << 63) - 1
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_GIT = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z", re.ASCII)


def _invalid() -> NoReturn:
    raise ValueError("INVALID_AI_PERSISTENCE_VALUE") from None


def _order_value(value: object) -> object:
    if isinstance(value, EntityId):
        return value.value.int
    if isinstance(value, Enum):
        return value.value
    if type(value) is AwareUtcDateTime:
        return value.value
    return value


@dataclass(frozen=True, slots=True, repr=False)
class AiAttemptState:
    """Exact scalar state for relation ai.ai_attempt."""

    RELATION: ClassVar[str] = "ai.ai_attempt"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_ai_attempt_complete",
        "ck_ai_attempt_fingerprint",
        "ck_ai_attempt_input_hash",
        "ck_ai_attempt_latency",
        "ck_ai_attempt_no",
        "ck_ai_attempt_output",
        "ck_ai_attempt_output_hash",
        "ck_ai_attempt_region",
        "ck_ai_attempt_repair",
        "ck_ai_attempt_request_config",
        "ck_ai_attempt_requested_model",
        "ck_ai_attempt_resolved_model",
        "ck_ai_attempt_safety_hash",
        "ck_ai_attempt_status",
        "ck_ai_attempt_validation",
    )
    id: AiAttemptId
    ai_job_id: AiJobId
    attempt_no: int
    model_id: ModelDefinitionId
    provider_request_id: str | None
    status: AiAttemptStatus
    input_artifact_id: ObjectArtifactId
    output_artifact_id: ObjectArtifactId | None
    input_sha256: Sha256Digest
    output_sha256: Sha256Digest | None
    refusal_code: str | None
    finish_reason: str | None
    latency_ms: int | None
    error_class: str | None
    error_code: str | None
    error_message: str | None
    started_at: AwareUtcDateTime
    completed_at: AwareUtcDateTime | None
    created_at: AwareUtcDateTime
    requested_model_id: str
    resolved_model_id: str
    response_fingerprint: str | None
    provider_region: str | None
    request_config: AiAttemptRequestConfigJson
    validation_status: AiAttemptValidationStatus
    safety_identifier_hash: Sha256Digest | None
    repair_attempt_no: int

    def __post_init__(self) -> None:
        if type(self.id) is not AiAttemptId:
            _invalid()
        if type(self.ai_job_id) is not AiJobId:
            _invalid()
        if (
            type(self.attempt_no) is not int
            or not -_MAX_BIGINT <= self.attempt_no <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.model_id) is not ModelDefinitionId:
            _invalid()
        if self.provider_request_id is not None and (
            type(self.provider_request_id) is not str
        ):
            _invalid()
        if type(self.status) is not AiAttemptStatus:
            _invalid()
        if type(self.input_artifact_id) is not ObjectArtifactId:
            _invalid()
        if self.output_artifact_id is not None and (
            type(self.output_artifact_id) is not ObjectArtifactId
        ):
            _invalid()
        if type(self.input_sha256) is not Sha256Digest:
            _invalid()
        if self.output_sha256 is not None and (
            type(self.output_sha256) is not Sha256Digest
        ):
            _invalid()
        if self.refusal_code is not None and (type(self.refusal_code) is not str):
            _invalid()
        if self.finish_reason is not None and (type(self.finish_reason) is not str):
            _invalid()
        if self.latency_ms is not None and (
            type(self.latency_ms) is not int
            or not -_MAX_BIGINT <= self.latency_ms <= _MAX_BIGINT
        ):
            _invalid()
        if self.error_class is not None and (type(self.error_class) is not str):
            _invalid()
        if self.error_code is not None and (type(self.error_code) is not str):
            _invalid()
        if self.error_message is not None and (type(self.error_message) is not str):
            _invalid()
        if type(self.started_at) is not AwareUtcDateTime:
            _invalid()
        if self.completed_at is not None and (
            type(self.completed_at) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.requested_model_id) is not str:
            _invalid()
        if type(self.resolved_model_id) is not str:
            _invalid()
        if self.response_fingerprint is not None and (
            type(self.response_fingerprint) is not str
        ):
            _invalid()
        if self.provider_region is not None and (type(self.provider_region) is not str):
            _invalid()
        if type(self.request_config) is not AiAttemptRequestConfigJson:
            _invalid()
        if type(self.validation_status) is not AiAttemptValidationStatus:
            _invalid()
        if self.safety_identifier_hash is not None and (
            type(self.safety_identifier_hash) is not Sha256Digest
        ):
            _invalid()
        if (
            type(self.repair_attempt_no) is not int
            or not -_MAX_BIGINT <= self.repair_attempt_no <= _MAX_BIGINT
        ):
            _invalid()
        if self.latency_ms is not None and self.latency_ms < 0:
            _invalid()
        if self.repair_attempt_no < 0:
            _invalid()

    def __repr__(self) -> str:
        return "AiAttemptState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class AiJobState:
    """Exact scalar state for relation ai.ai_job."""

    RELATION: ClassVar[str] = "ai.ai_job"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_ai_job_budget_reserved",
        "ck_ai_job_complete",
        "ck_ai_job_cost",
        "ck_ai_job_lock_version",
        "ck_ai_job_manifest_sha",
        "ck_ai_job_request_config",
        "ck_ai_job_status",
        "ck_ai_job_target",
    )
    id: AiJobId
    display_id: str
    ops_job_id: JobId
    task_definition_id: AiTaskDefinitionId
    article_plan_id: ArticlePlanId | None
    article_version_id: ArticleVersionId | None
    source_packet_version_id: SourcePacketVersionId
    prompt_version_id: PromptVersionId
    output_schema_version_id: OutputSchemaVersionId
    model_route_version_id: ModelRouteVersionId
    status: AiJobStatus
    max_cost_jpy: YenMinor
    completed_at: AwareUtcDateTime | None
    created_at: AwareUtcDateTime
    policy_bundle_version_id: PolicyBundleId | None
    release_decision_id: ReleaseDecisionId | None
    request_config: AiJobRequestConfigJson
    input_manifest_sha256: Sha256Digest | None
    budget_reserved_jpy: YenMinor
    lock_version: AggregateVersion
    updated_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not AiJobId:
            _invalid()
        if type(self.display_id) is not str:
            _invalid()
        if type(self.ops_job_id) is not JobId:
            _invalid()
        if type(self.task_definition_id) is not AiTaskDefinitionId:
            _invalid()
        if self.article_plan_id is not None and (
            type(self.article_plan_id) is not ArticlePlanId
        ):
            _invalid()
        if self.article_version_id is not None and (
            type(self.article_version_id) is not ArticleVersionId
        ):
            _invalid()
        if type(self.source_packet_version_id) is not SourcePacketVersionId:
            _invalid()
        if type(self.prompt_version_id) is not PromptVersionId:
            _invalid()
        if type(self.output_schema_version_id) is not OutputSchemaVersionId:
            _invalid()
        if type(self.model_route_version_id) is not ModelRouteVersionId:
            _invalid()
        if type(self.status) is not AiJobStatus:
            _invalid()
        if type(self.max_cost_jpy) is not YenMinor:
            _invalid()
        if self.completed_at is not None and (
            type(self.completed_at) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if self.policy_bundle_version_id is not None and (
            type(self.policy_bundle_version_id) is not PolicyBundleId
        ):
            _invalid()
        if self.release_decision_id is not None and (
            type(self.release_decision_id) is not ReleaseDecisionId
        ):
            _invalid()
        if type(self.request_config) is not AiJobRequestConfigJson:
            _invalid()
        if self.input_manifest_sha256 is not None and (
            type(self.input_manifest_sha256) is not Sha256Digest
        ):
            _invalid()
        if type(self.budget_reserved_jpy) is not YenMinor:
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if self.max_cost_jpy.value < 0:
            _invalid()
        if self.budget_reserved_jpy.value < 0:
            _invalid()
        if self.lock_version.value < 0:
            _invalid()

    def __repr__(self) -> str:
        return "AiJobState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class EvaluationCase:
    """Exact scalar state for relation ai.evaluation_case."""

    RELATION: ClassVar[str] = "ai.evaluation_case"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_ai_eval_case_category",
        "ck_ai_eval_case_disposition",
        "ck_ai_eval_case_key",
        "ck_ai_eval_case_meta",
        "ck_ai_eval_case_risk",
        "ck_ai_eval_case_split",
    )
    id: EvaluationCaseId
    dataset_version_id: EvaluationDatasetVersionId
    case_key: str
    task_definition_id: AiTaskDefinitionId
    split: EvaluationCaseSplit
    category: str
    risk_level: EvaluationCaseRiskLevel
    input_artifact_id: ObjectArtifactId
    gold_artifact_id: ObjectArtifactId | None
    expected_disposition: EvaluationCaseExpectedDisposition
    tags: tuple[str, ...]
    metadata: EvaluationCaseMetadataJson
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not EvaluationCaseId:
            _invalid()
        if type(self.dataset_version_id) is not EvaluationDatasetVersionId:
            _invalid()
        if type(self.case_key) is not str:
            _invalid()
        if type(self.task_definition_id) is not AiTaskDefinitionId:
            _invalid()
        if type(self.split) is not EvaluationCaseSplit:
            _invalid()
        if type(self.category) is not str:
            _invalid()
        if type(self.risk_level) is not EvaluationCaseRiskLevel:
            _invalid()
        if type(self.input_artifact_id) is not ObjectArtifactId:
            _invalid()
        if self.gold_artifact_id is not None and (
            type(self.gold_artifact_id) is not ObjectArtifactId
        ):
            _invalid()
        if type(self.expected_disposition) is not EvaluationCaseExpectedDisposition:
            _invalid()
        if type(self.tags) is not tuple or any(
            type(item) is not str for item in self.tags
        ):
            _invalid()
        if type(self.metadata) is not EvaluationCaseMetadataJson:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "EvaluationCase(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class EvaluationCaseResult:
    """Exact scalar state for relation ai.evaluation_case_result."""

    RELATION: ClassVar[str] = "ai.evaluation_case_result"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_ai_eval_case_result_disposition",
        "ck_ai_eval_case_result_failures",
        "ck_ai_eval_case_result_passed_zero_tolerance",
        "ck_ai_eval_case_result_status",
        "ck_ai_eval_case_result_summary",
        "ck_ai_eval_case_result_zero_tolerance_evidence",
        "ck_ai_eval_case_result_zero_tolerance_sha",
    )
    id: EvaluationCaseResultId
    evaluation_run_id: EvaluationRunId
    evaluation_case_id: EvaluationCaseId
    ai_attempt_id: AiAttemptId | None
    output_artifact_id: ObjectArtifactId | None
    status: EvaluationCaseResultStatus
    disposition: EvaluationCaseResultDisposition
    zero_tolerance_evidence: EvaluationCaseResultZeroToleranceEvidenceJson
    zero_tolerance_evidence_artifact_id: ObjectArtifactId
    zero_tolerance_evidence_sha256: Sha256Digest
    zero_tolerance_failure_count: int
    grader_summary: EvaluationCaseResultGraderSummaryJson
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not EvaluationCaseResultId:
            _invalid()
        if type(self.evaluation_run_id) is not EvaluationRunId:
            _invalid()
        if type(self.evaluation_case_id) is not EvaluationCaseId:
            _invalid()
        if self.ai_attempt_id is not None and (
            type(self.ai_attempt_id) is not AiAttemptId
        ):
            _invalid()
        if self.output_artifact_id is not None and (
            type(self.output_artifact_id) is not ObjectArtifactId
        ):
            _invalid()
        if type(self.status) is not EvaluationCaseResultStatus:
            _invalid()
        if type(self.disposition) is not EvaluationCaseResultDisposition:
            _invalid()
        if (
            type(self.zero_tolerance_evidence)
            is not EvaluationCaseResultZeroToleranceEvidenceJson
        ):
            _invalid()
        if type(self.zero_tolerance_evidence_artifact_id) is not ObjectArtifactId:
            _invalid()
        if type(self.zero_tolerance_evidence_sha256) is not Sha256Digest:
            _invalid()
        if (
            type(self.zero_tolerance_failure_count) is not int
            or not -_MAX_BIGINT <= self.zero_tolerance_failure_count <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.grader_summary) is not EvaluationCaseResultGraderSummaryJson:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if self.zero_tolerance_failure_count < 0:
            _invalid()

    def __repr__(self) -> str:
        return "EvaluationCaseResult(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class EvaluationDatasetVersionState:
    """Exact scalar state for relation ai.evaluation_dataset_version."""

    RELATION: ClassVar[str] = "ai.evaluation_dataset_version"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_ai_eval_dataset_code",
        "ck_ai_eval_dataset_compromised",
        "ck_ai_eval_dataset_count",
        "ck_ai_eval_dataset_display",
        "ck_ai_eval_dataset_lock",
        "ck_ai_eval_dataset_purpose",
        "ck_ai_eval_dataset_sha",
        "ck_ai_eval_dataset_split",
        "ck_ai_eval_dataset_status",
        "ck_ai_eval_dataset_version",
        "ck_ai_eval_dataset_version_lock",
    )
    id: EvaluationDatasetVersionId
    display_id: str
    dataset_code: str
    version_no: int
    purpose: str
    split_policy: EvaluationDatasetVersionSplitPolicyJson
    dataset_artifact_id: ObjectArtifactId
    dataset_sha256: Sha256Digest
    case_count: int
    status: EvaluationDatasetStatus
    locked_by_principal_id: PrincipalId | None
    locked_at: AwareUtcDateTime | None
    compromised_at: AwareUtcDateTime | None
    lock_version: AggregateVersion
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not EvaluationDatasetVersionId:
            _invalid()
        if type(self.display_id) is not str:
            _invalid()
        if type(self.dataset_code) is not str:
            _invalid()
        if (
            type(self.version_no) is not int
            or not -_MAX_BIGINT <= self.version_no <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.purpose) is not str:
            _invalid()
        if type(self.split_policy) is not EvaluationDatasetVersionSplitPolicyJson:
            _invalid()
        if type(self.dataset_artifact_id) is not ObjectArtifactId:
            _invalid()
        if type(self.dataset_sha256) is not Sha256Digest:
            _invalid()
        if (
            type(self.case_count) is not int
            or not -_MAX_BIGINT <= self.case_count <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.status) is not EvaluationDatasetStatus:
            _invalid()
        if self.locked_by_principal_id is not None and (
            type(self.locked_by_principal_id) is not PrincipalId
        ):
            _invalid()
        if self.locked_at is not None and (
            type(self.locked_at) is not AwareUtcDateTime
        ):
            _invalid()
        if self.compromised_at is not None and (
            type(self.compromised_at) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if self.case_count < 0:
            _invalid()
        if self.lock_version.value < 0:
            _invalid()

    def __repr__(self) -> str:
        return "EvaluationDatasetVersionState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class EvaluationResultState:
    """Exact scalar state for relation ai.evaluation_result."""

    RELATION: ClassVar[str] = "ai.evaluation_result"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_ai_eval_details",
        "ck_ai_eval_result_grader",
        "ck_ai_eval_result_judge_provenance",
        "ck_ai_eval_result_proportion_counts",
        "ck_ai_eval_result_run_binding",
        "ck_ai_eval_result_slice",
        "ck_ai_eval_result_threshold",
        "ck_ai_eval_suite_version",
    )
    id: EvaluationResultId
    suite_code: str
    suite_version: int
    run_id: RunId
    task_definition_id: AiTaskDefinitionId
    model_route_version_id: ModelRouteVersionId
    prompt_version_id: PromptVersionId
    case_key: str
    metric_code: EvaluationResultMetricCode
    metric_value: Decimal
    passed: bool | None
    details: EvaluationResultDetailsJson
    result_artifact_id: ObjectArtifactId | None
    created_at: AwareUtcDateTime
    evaluation_run_id: EvaluationRunId | None
    evaluation_case_id: EvaluationCaseId | None
    grader_code: str | None
    slice_key: str | None
    threshold_operator: EvaluationResultThresholdOperator | None
    threshold_value: Decimal | None
    judge_calibration_id: JudgeCalibrationId | None
    judge_route_version_id: ModelRouteVersionId | None
    judge_prompt_version_id: PromptVersionId | None
    judge_rubric_artifact_id: ObjectArtifactId | None
    judge_resolved_model_id: ModelDefinitionId | None
    judge_grader_version: str | None
    proportion_numerator_count: int | None
    proportion_denominator_count: int | None

    def __post_init__(self) -> None:
        if type(self.id) is not EvaluationResultId:
            _invalid()
        if type(self.suite_code) is not str:
            _invalid()
        if (
            type(self.suite_version) is not int
            or not -_MAX_BIGINT <= self.suite_version <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.run_id) is not RunId:
            _invalid()
        if type(self.task_definition_id) is not AiTaskDefinitionId:
            _invalid()
        if type(self.model_route_version_id) is not ModelRouteVersionId:
            _invalid()
        if type(self.prompt_version_id) is not PromptVersionId:
            _invalid()
        if type(self.case_key) is not str:
            _invalid()
        if type(self.metric_code) is not EvaluationResultMetricCode:
            _invalid()
        if type(self.metric_value) is not Decimal or not self.metric_value.is_finite():
            _invalid()
        if self.passed is not None and (type(self.passed) is not bool):
            _invalid()
        if type(self.details) is not EvaluationResultDetailsJson:
            _invalid()
        if self.result_artifact_id is not None and (
            type(self.result_artifact_id) is not ObjectArtifactId
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if self.evaluation_run_id is not None and (
            type(self.evaluation_run_id) is not EvaluationRunId
        ):
            _invalid()
        if self.evaluation_case_id is not None and (
            type(self.evaluation_case_id) is not EvaluationCaseId
        ):
            _invalid()
        if self.grader_code is not None and (type(self.grader_code) is not str):
            _invalid()
        if self.slice_key is not None and (type(self.slice_key) is not str):
            _invalid()
        if self.threshold_operator is not None and (
            type(self.threshold_operator) is not EvaluationResultThresholdOperator
        ):
            _invalid()
        if self.threshold_value is not None and (
            type(self.threshold_value) is not Decimal
            or not self.threshold_value.is_finite()
        ):
            _invalid()
        if self.judge_calibration_id is not None and (
            type(self.judge_calibration_id) is not JudgeCalibrationId
        ):
            _invalid()
        if self.judge_route_version_id is not None and (
            type(self.judge_route_version_id) is not ModelRouteVersionId
        ):
            _invalid()
        if self.judge_prompt_version_id is not None and (
            type(self.judge_prompt_version_id) is not PromptVersionId
        ):
            _invalid()
        if self.judge_rubric_artifact_id is not None and (
            type(self.judge_rubric_artifact_id) is not ObjectArtifactId
        ):
            _invalid()
        if self.judge_resolved_model_id is not None and (
            type(self.judge_resolved_model_id) is not ModelDefinitionId
        ):
            _invalid()
        if self.judge_grader_version is not None and (
            type(self.judge_grader_version) is not str
        ):
            _invalid()
        if self.proportion_numerator_count is not None and (
            type(self.proportion_numerator_count) is not int
            or not -_MAX_BIGINT <= self.proportion_numerator_count <= _MAX_BIGINT
        ):
            _invalid()
        if self.proportion_denominator_count is not None and (
            type(self.proportion_denominator_count) is not int
            or not -_MAX_BIGINT <= self.proportion_denominator_count <= _MAX_BIGINT
        ):
            _invalid()
        if (
            self.proportion_numerator_count is not None
            and self.proportion_numerator_count < 0
        ):
            _invalid()
        if (
            self.proportion_denominator_count is not None
            and self.proportion_denominator_count <= 0
        ):
            _invalid()

    def __repr__(self) -> str:
        return "EvaluationResultState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class EvaluationRunState:
    """Exact scalar state for relation ai.evaluation_run."""

    RELATION: ClassVar[str] = "ai.evaluation_run"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_ai_eval_run_completion",
        "ck_ai_eval_run_display",
        "ck_ai_eval_run_git",
        "ck_ai_eval_run_status",
        "ck_ai_eval_run_timing",
        "ck_ai_eval_run_version_lock",
    )
    id: EvaluationRunId
    display_id: str
    suite_id: EvaluationSuiteId
    dataset_version_id: EvaluationDatasetVersionId
    baseline_evaluation_run_id: EvaluationRunId | None
    prompt_version_id: PromptVersionId
    model_route_version_id: ModelRouteVersionId
    output_schema_version_id: OutputSchemaVersionId
    policy_bundle_version_id: PolicyBundleId
    code_git_sha: GitCommitDigest
    status: EvaluationRunStatus
    run_manifest_artifact_id: ObjectArtifactId | None
    started_at: AwareUtcDateTime | None
    completed_at: AwareUtcDateTime | None
    created_by_principal_id: PrincipalId
    lock_version: AggregateVersion
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    resolved_model_id: ModelDefinitionId

    def __post_init__(self) -> None:
        if type(self.id) is not EvaluationRunId:
            _invalid()
        if type(self.display_id) is not str:
            _invalid()
        if type(self.suite_id) is not EvaluationSuiteId:
            _invalid()
        if type(self.dataset_version_id) is not EvaluationDatasetVersionId:
            _invalid()
        if self.baseline_evaluation_run_id is not None and (
            type(self.baseline_evaluation_run_id) is not EvaluationRunId
        ):
            _invalid()
        if type(self.prompt_version_id) is not PromptVersionId:
            _invalid()
        if type(self.model_route_version_id) is not ModelRouteVersionId:
            _invalid()
        if type(self.output_schema_version_id) is not OutputSchemaVersionId:
            _invalid()
        if type(self.policy_bundle_version_id) is not PolicyBundleId:
            _invalid()
        if type(self.code_git_sha) is not GitCommitDigest:
            _invalid()
        if type(self.status) is not EvaluationRunStatus:
            _invalid()
        if self.run_manifest_artifact_id is not None and (
            type(self.run_manifest_artifact_id) is not ObjectArtifactId
        ):
            _invalid()
        if self.started_at is not None and (
            type(self.started_at) is not AwareUtcDateTime
        ):
            _invalid()
        if self.completed_at is not None and (
            type(self.completed_at) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.created_by_principal_id) is not PrincipalId:
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.resolved_model_id) is not ModelDefinitionId:
            _invalid()
        if self.lock_version.value < 0:
            _invalid()
        if (
            self.completed_at is not None
            and self.started_at is not None
            and (not self.completed_at.value >= self.started_at.value)
        ):
            _invalid()

    def __repr__(self) -> str:
        return "EvaluationRunState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class EvaluationSuiteState:
    """Exact scalar state for relation ai.evaluation_suite."""

    RELATION: ClassVar[str] = "ai.evaluation_suite"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_ai_eval_suite_approval",
        "ck_ai_eval_suite_approval_time",
        "ck_ai_eval_suite_code",
        "ck_ai_eval_suite_config",
        "ck_ai_eval_suite_risk",
        "ck_ai_eval_suite_status",
        "ck_ai_eval_suite_version",
        "ck_ai_eval_suite_version_lock",
    )
    id: EvaluationSuiteId
    suite_code: str
    version_no: int
    task_definition_id: AiTaskDefinitionId
    risk_level: EvaluationSuiteRiskLevel
    rubric_artifact_id: ObjectArtifactId | None
    suite_config: EvaluationSuiteSuiteConfigJson
    status: EvaluationSuiteStatus
    approved_by_principal_id: PrincipalId | None
    approved_at: AwareUtcDateTime | None
    lock_version: AggregateVersion
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not EvaluationSuiteId:
            _invalid()
        if type(self.suite_code) is not str:
            _invalid()
        if (
            type(self.version_no) is not int
            or not -_MAX_BIGINT <= self.version_no <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.task_definition_id) is not AiTaskDefinitionId:
            _invalid()
        if type(self.risk_level) is not EvaluationSuiteRiskLevel:
            _invalid()
        if self.rubric_artifact_id is not None and (
            type(self.rubric_artifact_id) is not ObjectArtifactId
        ):
            _invalid()
        if type(self.suite_config) is not EvaluationSuiteSuiteConfigJson:
            _invalid()
        if type(self.status) is not EvaluationSuiteStatus:
            _invalid()
        if self.approved_by_principal_id is not None and (
            type(self.approved_by_principal_id) is not PrincipalId
        ):
            _invalid()
        if self.approved_at is not None and (
            type(self.approved_at) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if self.lock_version.value < 0:
            _invalid()
        if self.approved_at is not None and (
            not self.approved_at.value >= self.created_at.value
        ):
            _invalid()

    def __repr__(self) -> str:
        return "EvaluationSuiteState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class HumanEvaluation:
    """Exact scalar state for relation ai.human_evaluation."""

    RELATION: ClassVar[str] = "ai.human_evaluation"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_ai_human_eval_blind_key",
        "ck_ai_human_eval_decision",
        "ck_ai_human_eval_rubric",
        "ck_ai_human_eval_scores",
    )
    id: HumanEvaluationId
    evaluation_case_result_id: EvaluationCaseResultId
    reviewer_principal_id: PrincipalId
    rubric_version: str
    blind_assignment_key: str
    scores: HumanEvaluationScoresJson
    decision: HumanEvaluationDecision
    notes_artifact_id: ObjectArtifactId | None
    is_adjudication: bool
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not HumanEvaluationId:
            _invalid()
        if type(self.evaluation_case_result_id) is not EvaluationCaseResultId:
            _invalid()
        if type(self.reviewer_principal_id) is not PrincipalId:
            _invalid()
        if type(self.rubric_version) is not str:
            _invalid()
        if type(self.blind_assignment_key) is not str:
            _invalid()
        if type(self.scores) is not HumanEvaluationScoresJson:
            _invalid()
        if type(self.decision) is not HumanEvaluationDecision:
            _invalid()
        if self.notes_artifact_id is not None and (
            type(self.notes_artifact_id) is not ObjectArtifactId
        ):
            _invalid()
        if type(self.is_adjudication) is not bool:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "HumanEvaluation(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class JudgeCalibrationState:
    """Exact scalar state for relation ai.judge_calibration."""

    RELATION: ClassVar[str] = "ai.judge_calibration"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_ai_judge_cal_approval",
        "ck_ai_judge_cal_approval_time",
        "ck_ai_judge_cal_count",
        "ck_ai_judge_cal_display",
        "ck_ai_judge_cal_expiry",
        "ck_ai_judge_cal_expiry_time",
        "ck_ai_judge_cal_grader_version",
        "ck_ai_judge_cal_rates",
        "ck_ai_judge_cal_rubric_sha",
        "ck_ai_judge_cal_status",
        "ck_ai_judge_cal_version_lock",
    )
    id: JudgeCalibrationId
    display_id: str
    judge_route_version_id: ModelRouteVersionId
    judge_prompt_version_id: PromptVersionId
    dataset_version_id: EvaluationDatasetVersionId
    weighted_kappa: Decimal | None
    zero_tolerance_false_pass_rate: Decimal | None
    zero_tolerance_false_fail_rate: Decimal | None
    case_count: int
    status: JudgeCalibrationStatus
    report_artifact_id: ObjectArtifactId | None
    approved_by_principal_id: PrincipalId | None
    approved_at: AwareUtcDateTime | None
    expires_at: AwareUtcDateTime | None
    lock_version: AggregateVersion
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    evaluated_task_definition_id: AiTaskDefinitionId
    resolved_judge_model_id: ModelDefinitionId
    rubric_artifact_id: ObjectArtifactId
    rubric_sha256: Sha256Digest
    grader_version: str

    def __post_init__(self) -> None:
        if type(self.id) is not JudgeCalibrationId:
            _invalid()
        if type(self.display_id) is not str:
            _invalid()
        if type(self.judge_route_version_id) is not ModelRouteVersionId:
            _invalid()
        if type(self.judge_prompt_version_id) is not PromptVersionId:
            _invalid()
        if type(self.dataset_version_id) is not EvaluationDatasetVersionId:
            _invalid()
        if self.weighted_kappa is not None and (
            type(self.weighted_kappa) is not Decimal
            or not self.weighted_kappa.is_finite()
        ):
            _invalid()
        if self.zero_tolerance_false_pass_rate is not None and (
            type(self.zero_tolerance_false_pass_rate) is not Decimal
            or not self.zero_tolerance_false_pass_rate.is_finite()
        ):
            _invalid()
        if self.zero_tolerance_false_fail_rate is not None and (
            type(self.zero_tolerance_false_fail_rate) is not Decimal
            or not self.zero_tolerance_false_fail_rate.is_finite()
        ):
            _invalid()
        if (
            type(self.case_count) is not int
            or not -_MAX_BIGINT <= self.case_count <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.status) is not JudgeCalibrationStatus:
            _invalid()
        if self.report_artifact_id is not None and (
            type(self.report_artifact_id) is not ObjectArtifactId
        ):
            _invalid()
        if self.approved_by_principal_id is not None and (
            type(self.approved_by_principal_id) is not PrincipalId
        ):
            _invalid()
        if self.approved_at is not None and (
            type(self.approved_at) is not AwareUtcDateTime
        ):
            _invalid()
        if self.expires_at is not None and (
            type(self.expires_at) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.evaluated_task_definition_id) is not AiTaskDefinitionId:
            _invalid()
        if type(self.resolved_judge_model_id) is not ModelDefinitionId:
            _invalid()
        if type(self.rubric_artifact_id) is not ObjectArtifactId:
            _invalid()
        if type(self.rubric_sha256) is not Sha256Digest:
            _invalid()
        if type(self.grader_version) is not str:
            _invalid()
        if (
            self.zero_tolerance_false_pass_rate is not None
            and self.zero_tolerance_false_pass_rate < 0
        ):
            _invalid()
        if (
            self.zero_tolerance_false_fail_rate is not None
            and self.zero_tolerance_false_fail_rate < 0
        ):
            _invalid()
        if self.case_count < 0:
            _invalid()
        if self.lock_version.value < 0:
            _invalid()
        if self.approved_at is not None and (
            not self.approved_at.value >= self.created_at.value
        ):
            _invalid()
        if (
            self.expires_at is not None
            and self.approved_at is not None
            and (not self.expires_at.value > self.approved_at.value)
        ):
            _invalid()

    def __repr__(self) -> str:
        return "JudgeCalibrationState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ModelDefinitionState:
    """Exact scalar state for relation ai.model_definition."""

    RELATION: ClassVar[str] = "ai.model_definition"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_ai_model_capabilities",
        "ck_ai_model_context",
        "ck_ai_model_currency",
        "ck_ai_model_metadata",
        "ck_ai_model_output",
        "ck_ai_model_prices",
        "ck_ai_model_status",
    )
    id: ModelDefinitionId
    provider_code: str
    provider_model_id: str
    display_name: str
    capabilities: ModelDefinitionCapabilitiesJson
    input_price_per_million: Decimal | None
    cached_input_price_per_million: Decimal | None
    output_price_per_million: Decimal | None
    pricing_currency: str | None
    pricing_observed_at: AwareUtcDateTime | None
    status: ModelDefinitionStatus
    created_at: AwareUtcDateTime
    context_window_tokens: int | None
    max_output_tokens: int | None
    knowledge_cutoff: date | None
    metadata_observed_at: AwareUtcDateTime | None
    provider_metadata: ModelDefinitionProviderMetadataJson

    def __post_init__(self) -> None:
        if type(self.id) is not ModelDefinitionId:
            _invalid()
        if type(self.provider_code) is not str:
            _invalid()
        if type(self.provider_model_id) is not str:
            _invalid()
        if type(self.display_name) is not str:
            _invalid()
        if type(self.capabilities) is not ModelDefinitionCapabilitiesJson:
            _invalid()
        if self.input_price_per_million is not None and (
            type(self.input_price_per_million) is not Decimal
            or not self.input_price_per_million.is_finite()
        ):
            _invalid()
        if self.cached_input_price_per_million is not None and (
            type(self.cached_input_price_per_million) is not Decimal
            or not self.cached_input_price_per_million.is_finite()
        ):
            _invalid()
        if self.output_price_per_million is not None and (
            type(self.output_price_per_million) is not Decimal
            or not self.output_price_per_million.is_finite()
        ):
            _invalid()
        if self.pricing_currency is not None and (
            type(self.pricing_currency) is not str
        ):
            _invalid()
        if self.pricing_observed_at is not None and (
            type(self.pricing_observed_at) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.status) is not ModelDefinitionStatus:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if self.context_window_tokens is not None and (
            type(self.context_window_tokens) is not int
            or not -_MAX_BIGINT <= self.context_window_tokens <= _MAX_BIGINT
        ):
            _invalid()
        if self.max_output_tokens is not None and (
            type(self.max_output_tokens) is not int
            or not -_MAX_BIGINT <= self.max_output_tokens <= _MAX_BIGINT
        ):
            _invalid()
        if self.knowledge_cutoff is not None and (
            type(self.knowledge_cutoff) is not date
        ):
            _invalid()
        if self.metadata_observed_at is not None and (
            type(self.metadata_observed_at) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.provider_metadata) is not ModelDefinitionProviderMetadataJson:
            _invalid()
        if (
            self.input_price_per_million is not None
            and self.input_price_per_million < 0
        ):
            _invalid()
        if (
            self.cached_input_price_per_million is not None
            and self.cached_input_price_per_million < 0
        ):
            _invalid()
        if (
            self.output_price_per_million is not None
            and self.output_price_per_million < 0
        ):
            _invalid()
        if self.context_window_tokens is not None and self.context_window_tokens <= 0:
            _invalid()
        if self.max_output_tokens is not None and self.max_output_tokens <= 0:
            _invalid()

    def __repr__(self) -> str:
        return "ModelDefinitionState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ModelRouteVersionState:
    """Exact scalar state for relation ai.model_route_version."""

    RELATION: ClassVar[str] = "ai.model_route_version"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_ai_route_budget",
        "ck_ai_route_config",
        "ck_ai_route_lock_version",
        "ck_ai_route_models",
        "ck_ai_route_status",
        "ck_ai_route_version",
        "ck_ai_route_window",
    )
    id: ModelRouteVersionId
    route_code: str
    version_no: int
    task_definition_id: AiTaskDefinitionId
    primary_model_id: ModelDefinitionId
    fallback_model_id: ModelDefinitionId | None
    route_config: ModelRouteVersionRouteConfigJson
    monthly_budget_jpy: YenMinor | None
    per_job_budget_jpy: YenMinor
    status: ModelRouteVersionStatus
    effective_from: AwareUtcDateTime | None
    effective_to: AwareUtcDateTime | None
    approved_by_principal_id: PrincipalId | None
    created_at: AwareUtcDateTime
    lock_version: AggregateVersion
    updated_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not ModelRouteVersionId:
            _invalid()
        if type(self.route_code) is not str:
            _invalid()
        if (
            type(self.version_no) is not int
            or not -_MAX_BIGINT <= self.version_no <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.task_definition_id) is not AiTaskDefinitionId:
            _invalid()
        if type(self.primary_model_id) is not ModelDefinitionId:
            _invalid()
        if self.fallback_model_id is not None and (
            type(self.fallback_model_id) is not ModelDefinitionId
        ):
            _invalid()
        if type(self.route_config) is not ModelRouteVersionRouteConfigJson:
            _invalid()
        if self.monthly_budget_jpy is not None and (
            type(self.monthly_budget_jpy) is not YenMinor
        ):
            _invalid()
        if type(self.per_job_budget_jpy) is not YenMinor:
            _invalid()
        if type(self.status) is not ModelRouteVersionStatus:
            _invalid()
        if self.effective_from is not None and (
            type(self.effective_from) is not AwareUtcDateTime
        ):
            _invalid()
        if self.effective_to is not None and (
            type(self.effective_to) is not AwareUtcDateTime
        ):
            _invalid()
        if self.approved_by_principal_id is not None and (
            type(self.approved_by_principal_id) is not PrincipalId
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if self.monthly_budget_jpy is not None and self.monthly_budget_jpy.value < 0:
            _invalid()
        if self.per_job_budget_jpy.value < 0:
            _invalid()
        if self.lock_version.value < 0:
            _invalid()
        if (
            self.effective_to is not None
            and self.effective_from is not None
            and (not self.effective_to.value > self.effective_from.value)
        ):
            _invalid()

    def __repr__(self) -> str:
        return "ModelRouteVersionState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class OutputSchemaVersionState:
    """Exact scalar state for relation ai.output_schema_version."""

    RELATION: ClassVar[str] = "ai.output_schema_version"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_ai_output_schema_git",
        "ck_ai_output_schema_hash",
        "ck_ai_output_schema_status",
        "ck_ai_output_schema_version",
        "ck_ai_output_schema_window",
    )
    id: OutputSchemaVersionId
    schema_code: str
    version_no: int
    git_path: str
    git_commit_sha: str
    schema_sha256: Sha256Digest
    status: OutputSchemaVersionStatus
    effective_from: AwareUtcDateTime | None
    effective_to: AwareUtcDateTime | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not OutputSchemaVersionId:
            _invalid()
        if type(self.schema_code) is not str:
            _invalid()
        if (
            type(self.version_no) is not int
            or not -_MAX_BIGINT <= self.version_no <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.git_path) is not str:
            _invalid()
        if type(self.git_commit_sha) is not str:
            _invalid()
        if type(self.schema_sha256) is not Sha256Digest:
            _invalid()
        if type(self.status) is not OutputSchemaVersionStatus:
            _invalid()
        if self.effective_from is not None and (
            type(self.effective_from) is not AwareUtcDateTime
        ):
            _invalid()
        if self.effective_to is not None and (
            type(self.effective_to) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if _GIT.fullmatch(self.git_commit_sha) is None:
            _invalid()
        if (
            self.effective_to is not None
            and self.effective_from is not None
            and (not self.effective_to.value > self.effective_from.value)
        ):
            _invalid()

    def __repr__(self) -> str:
        return "OutputSchemaVersionState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class PromptVersionState:
    """Exact scalar state for relation ai.prompt_version."""

    RELATION: ClassVar[str] = "ai.prompt_version"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_ai_prompt_approval",
        "ck_ai_prompt_compiler",
        "ck_ai_prompt_git",
        "ck_ai_prompt_hash",
        "ck_ai_prompt_input_hash",
        "ck_ai_prompt_locale",
        "ck_ai_prompt_lock_version",
        "ck_ai_prompt_policy_test",
        "ck_ai_prompt_status",
        "ck_ai_prompt_version",
        "ck_ai_prompt_window",
    )
    id: PromptVersionId
    display_id: str
    task_definition_id: AiTaskDefinitionId
    prompt_code: str
    version_no: int
    git_path: str
    git_commit_sha: str
    template_sha256: Sha256Digest
    status: PromptVersionStatus
    effective_from: AwareUtcDateTime | None
    effective_to: AwareUtcDateTime | None
    approved_by_principal_id: PrincipalId | None
    approved_at: AwareUtcDateTime | None
    created_at: AwareUtcDateTime
    locale: str
    compiler_version: str | None
    input_contract_sha256: Sha256Digest | None
    policy_test_status: PromptVersionPolicyTestStatus
    lock_version: AggregateVersion
    updated_at: AwareUtcDateTime
    author_principal_id: PrincipalId

    def __post_init__(self) -> None:
        if type(self.id) is not PromptVersionId:
            _invalid()
        if type(self.display_id) is not str:
            _invalid()
        if type(self.task_definition_id) is not AiTaskDefinitionId:
            _invalid()
        if type(self.prompt_code) is not str:
            _invalid()
        if (
            type(self.version_no) is not int
            or not -_MAX_BIGINT <= self.version_no <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.git_path) is not str:
            _invalid()
        if type(self.git_commit_sha) is not str:
            _invalid()
        if type(self.template_sha256) is not Sha256Digest:
            _invalid()
        if type(self.status) is not PromptVersionStatus:
            _invalid()
        if self.effective_from is not None and (
            type(self.effective_from) is not AwareUtcDateTime
        ):
            _invalid()
        if self.effective_to is not None and (
            type(self.effective_to) is not AwareUtcDateTime
        ):
            _invalid()
        if self.approved_by_principal_id is not None and (
            type(self.approved_by_principal_id) is not PrincipalId
        ):
            _invalid()
        if self.approved_at is not None and (
            type(self.approved_at) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.locale) is not str:
            _invalid()
        if self.compiler_version is not None and (
            type(self.compiler_version) is not str
        ):
            _invalid()
        if self.input_contract_sha256 is not None and (
            type(self.input_contract_sha256) is not Sha256Digest
        ):
            _invalid()
        if type(self.policy_test_status) is not PromptVersionPolicyTestStatus:
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.author_principal_id) is not PrincipalId:
            _invalid()
        if _GIT.fullmatch(self.git_commit_sha) is None:
            _invalid()
        if self.lock_version.value < 0:
            _invalid()
        if (
            self.effective_to is not None
            and self.effective_from is not None
            and (not self.effective_to.value > self.effective_from.value)
        ):
            _invalid()

    def __repr__(self) -> str:
        return "PromptVersionState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ReleaseApproval:
    """Exact scalar state for relation ai.release_approval."""

    RELATION: ClassVar[str] = "ai.release_approval"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_ai_release_approval_display",
        "ck_ai_release_approval_manifest",
        "ck_ai_release_approval_phase",
        "ck_ai_release_approval_principals",
        "ck_ai_release_approval_roles",
        "ck_ai_release_approval_sha",
    )
    id: ReleaseApprovalId
    display_id: str
    release_decision_id: ReleaseDecisionId
    phase: ReleaseApprovalPhase
    decision_manifest_sha256: Sha256Digest
    primary_approver_principal_id: PrincipalId
    primary_approver_role: str
    second_approver_principal_id: PrincipalId
    second_approver_role: str
    approval_artifact_id: ObjectArtifactId
    approval_sha256: Sha256Digest
    signed_at: AwareUtcDateTime
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not ReleaseApprovalId:
            _invalid()
        if type(self.display_id) is not str:
            _invalid()
        if type(self.release_decision_id) is not ReleaseDecisionId:
            _invalid()
        if type(self.phase) is not ReleaseApprovalPhase:
            _invalid()
        if type(self.decision_manifest_sha256) is not Sha256Digest:
            _invalid()
        if type(self.primary_approver_principal_id) is not PrincipalId:
            _invalid()
        if type(self.primary_approver_role) is not str:
            _invalid()
        if type(self.second_approver_principal_id) is not PrincipalId:
            _invalid()
        if type(self.second_approver_role) is not str:
            _invalid()
        if type(self.approval_artifact_id) is not ObjectArtifactId:
            _invalid()
        if type(self.approval_sha256) is not Sha256Digest:
            _invalid()
        if type(self.signed_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if self.second_approver_principal_id == self.primary_approver_principal_id:
            _invalid()

    def __repr__(self) -> str:
        return "ReleaseApproval(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ReleaseDecisionState:
    """Exact scalar state for relation ai.release_decision."""

    RELATION: ClassVar[str] = "ai.release_decision"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_ai_release_approval",
        "ck_ai_release_approval_time",
        "ck_ai_release_approvers",
        "ck_ai_release_canary",
        "ck_ai_release_canary_time",
        "ck_ai_release_display",
        "ck_ai_release_evidence_sha",
        "ck_ai_release_git",
        "ck_ai_release_monitoring_sha",
        "ck_ai_release_no_self_rollback",
        "ck_ai_release_phase_state",
        "ck_ai_release_revocation",
        "ck_ai_release_revocation_time",
        "ck_ai_release_rollback_binding",
        "ck_ai_release_rollback_strategy",
        "ck_ai_release_scope",
        "ck_ai_release_scope_status",
        "ck_ai_release_sha",
        "ck_ai_release_status",
        "ck_ai_release_version_lock",
    )
    id: ReleaseDecisionId
    display_id: str
    task_definition_id: AiTaskDefinitionId
    prompt_version_id: PromptVersionId
    model_route_version_id: ModelRouteVersionId
    output_schema_version_id: OutputSchemaVersionId
    resolved_model_id: ModelDefinitionId
    policy_bundle_version_id: PolicyBundleId
    dataset_version_id: EvaluationDatasetVersionId
    evaluation_run_id: EvaluationRunId
    code_git_sha: GitCommitDigest
    release_scope: ReleaseDecisionReleaseScope
    status: ReleaseDecisionStatus
    maximum_canary_percent: int
    decision_manifest_sha256: Sha256Digest
    rollback_release_decision_id: ReleaseDecisionId | None
    approved_by_principal_id: PrincipalId | None
    second_approver_principal_id: PrincipalId | None
    approved_at: AwareUtcDateTime | None
    revoked_by_principal_id: PrincipalId | None
    revoked_at: AwareUtcDateTime | None
    revocation_reason: str | None
    lock_version: AggregateVersion
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    judge_calibration_id: JudgeCalibrationId | None
    rollback_strategy: ReleaseDecisionRollbackStrategy
    rollback_runbook_artifact_id: ObjectArtifactId | None
    rollback_runbook_sha256: Sha256Digest | None
    canary_monitoring_artifact_id: ObjectArtifactId | None
    canary_monitoring_sha256: Sha256Digest | None
    canary_evidence_artifact_id: ObjectArtifactId | None
    canary_evidence_sha256: Sha256Digest | None
    canary_started_at: AwareUtcDateTime | None
    canary_completed_at: AwareUtcDateTime | None
    canary_started_txid: int | None
    canary_completed_txid: int | None
    canary_approval_id: ReleaseApprovalId | None
    active_approval_id: ReleaseApprovalId | None

    def __post_init__(self) -> None:
        if type(self.id) is not ReleaseDecisionId:
            _invalid()
        if type(self.display_id) is not str:
            _invalid()
        if type(self.task_definition_id) is not AiTaskDefinitionId:
            _invalid()
        if type(self.prompt_version_id) is not PromptVersionId:
            _invalid()
        if type(self.model_route_version_id) is not ModelRouteVersionId:
            _invalid()
        if type(self.output_schema_version_id) is not OutputSchemaVersionId:
            _invalid()
        if type(self.resolved_model_id) is not ModelDefinitionId:
            _invalid()
        if type(self.policy_bundle_version_id) is not PolicyBundleId:
            _invalid()
        if type(self.dataset_version_id) is not EvaluationDatasetVersionId:
            _invalid()
        if type(self.evaluation_run_id) is not EvaluationRunId:
            _invalid()
        if type(self.code_git_sha) is not GitCommitDigest:
            _invalid()
        if type(self.release_scope) is not ReleaseDecisionReleaseScope:
            _invalid()
        if type(self.status) is not ReleaseDecisionStatus:
            _invalid()
        if (
            type(self.maximum_canary_percent) is not int
            or not -_MAX_BIGINT <= self.maximum_canary_percent <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.decision_manifest_sha256) is not Sha256Digest:
            _invalid()
        if self.rollback_release_decision_id is not None and (
            type(self.rollback_release_decision_id) is not ReleaseDecisionId
        ):
            _invalid()
        if self.approved_by_principal_id is not None and (
            type(self.approved_by_principal_id) is not PrincipalId
        ):
            _invalid()
        if self.second_approver_principal_id is not None and (
            type(self.second_approver_principal_id) is not PrincipalId
        ):
            _invalid()
        if self.approved_at is not None and (
            type(self.approved_at) is not AwareUtcDateTime
        ):
            _invalid()
        if self.revoked_by_principal_id is not None and (
            type(self.revoked_by_principal_id) is not PrincipalId
        ):
            _invalid()
        if self.revoked_at is not None and (
            type(self.revoked_at) is not AwareUtcDateTime
        ):
            _invalid()
        if self.revocation_reason is not None and (
            type(self.revocation_reason) is not str
        ):
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if self.judge_calibration_id is not None and (
            type(self.judge_calibration_id) is not JudgeCalibrationId
        ):
            _invalid()
        if type(self.rollback_strategy) is not ReleaseDecisionRollbackStrategy:
            _invalid()
        if self.rollback_runbook_artifact_id is not None and (
            type(self.rollback_runbook_artifact_id) is not ObjectArtifactId
        ):
            _invalid()
        if self.rollback_runbook_sha256 is not None and (
            type(self.rollback_runbook_sha256) is not Sha256Digest
        ):
            _invalid()
        if self.canary_monitoring_artifact_id is not None and (
            type(self.canary_monitoring_artifact_id) is not ObjectArtifactId
        ):
            _invalid()
        if self.canary_monitoring_sha256 is not None and (
            type(self.canary_monitoring_sha256) is not Sha256Digest
        ):
            _invalid()
        if self.canary_evidence_artifact_id is not None and (
            type(self.canary_evidence_artifact_id) is not ObjectArtifactId
        ):
            _invalid()
        if self.canary_evidence_sha256 is not None and (
            type(self.canary_evidence_sha256) is not Sha256Digest
        ):
            _invalid()
        if self.canary_started_at is not None and (
            type(self.canary_started_at) is not AwareUtcDateTime
        ):
            _invalid()
        if self.canary_completed_at is not None and (
            type(self.canary_completed_at) is not AwareUtcDateTime
        ):
            _invalid()
        if self.canary_started_txid is not None and (
            type(self.canary_started_txid) is not int
            or not -_MAX_BIGINT <= self.canary_started_txid <= _MAX_BIGINT
        ):
            _invalid()
        if self.canary_completed_txid is not None and (
            type(self.canary_completed_txid) is not int
            or not -_MAX_BIGINT <= self.canary_completed_txid <= _MAX_BIGINT
        ):
            _invalid()
        if self.canary_approval_id is not None and (
            type(self.canary_approval_id) is not ReleaseApprovalId
        ):
            _invalid()
        if self.active_approval_id is not None and (
            type(self.active_approval_id) is not ReleaseApprovalId
        ):
            _invalid()
        if self.maximum_canary_percent < 0:
            _invalid()
        if self.lock_version.value < 0:
            _invalid()
        if self.approved_at is not None and (
            not self.approved_at.value >= self.created_at.value
        ):
            _invalid()
        if (
            self.canary_completed_at is not None
            and self.canary_started_at is not None
            and (not self.canary_completed_at.value > self.canary_started_at.value)
        ):
            _invalid()
        if (
            self.revoked_at is not None
            and self.approved_at is not None
            and (not self.revoked_at.value >= self.approved_at.value)
        ):
            _invalid()

    def __repr__(self) -> str:
        return "ReleaseDecisionState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class AiTaskDefinitionState:
    """Exact scalar state for relation ai.task_definition."""

    RELATION: ClassVar[str] = "ai.task_definition"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_ai_task_cost",
        "ck_ai_task_risk",
        "ck_ai_task_status",
        "ck_ai_task_tokens",
    )
    id: AiTaskDefinitionId
    task_code: str
    name: str
    description: str
    risk_level: AiTaskDefinitionRiskLevel
    output_schema_code: str
    default_max_tokens: int
    default_max_cost_jpy: YenMinor
    human_review_required: bool
    status: AiTaskDefinitionStatus
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not AiTaskDefinitionId:
            _invalid()
        if type(self.task_code) is not str:
            _invalid()
        if type(self.name) is not str:
            _invalid()
        if type(self.description) is not str:
            _invalid()
        if type(self.risk_level) is not AiTaskDefinitionRiskLevel:
            _invalid()
        if type(self.output_schema_code) is not str:
            _invalid()
        if (
            type(self.default_max_tokens) is not int
            or not -_MAX_BIGINT <= self.default_max_tokens <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.default_max_cost_jpy) is not YenMinor:
            _invalid()
        if type(self.human_review_required) is not bool:
            _invalid()
        if type(self.status) is not AiTaskDefinitionStatus:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if self.default_max_cost_jpy.value < 0:
            _invalid()

    def __repr__(self) -> str:
        return "AiTaskDefinitionState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class UsageCost:
    """Exact scalar state for relation ai.usage_cost."""

    RELATION: ClassVar[str] = "ai.usage_cost"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_ai_usage_cost",
        "ck_ai_usage_currency",
        "ck_ai_usage_tokens",
    )
    id: UsageCostId
    ai_attempt_id: AiAttemptId
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    total_tokens: int
    provider_cost_amount: Decimal
    provider_currency: str
    fx_rate_to_jpy: Decimal
    cost_jpy: YenMinor
    pricing_version: str
    observed_at: AwareUtcDateTime
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not UsageCostId:
            _invalid()
        if type(self.ai_attempt_id) is not AiAttemptId:
            _invalid()
        if (
            type(self.input_tokens) is not int
            or not -_MAX_BIGINT <= self.input_tokens <= _MAX_BIGINT
        ):
            _invalid()
        if (
            type(self.cached_input_tokens) is not int
            or not -_MAX_BIGINT <= self.cached_input_tokens <= _MAX_BIGINT
        ):
            _invalid()
        if (
            type(self.output_tokens) is not int
            or not -_MAX_BIGINT <= self.output_tokens <= _MAX_BIGINT
        ):
            _invalid()
        if (
            type(self.total_tokens) is not int
            or not -_MAX_BIGINT <= self.total_tokens <= _MAX_BIGINT
        ):
            _invalid()
        if (
            type(self.provider_cost_amount) is not Decimal
            or not self.provider_cost_amount.is_finite()
        ):
            _invalid()
        if type(self.provider_currency) is not str:
            _invalid()
        if (
            type(self.fx_rate_to_jpy) is not Decimal
            or not self.fx_rate_to_jpy.is_finite()
        ):
            _invalid()
        if type(self.cost_jpy) is not YenMinor:
            _invalid()
        if type(self.pricing_version) is not str:
            _invalid()
        if type(self.observed_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if self.input_tokens < 0:
            _invalid()
        if self.cached_input_tokens < 0:
            _invalid()
        if self.output_tokens < 0:
            _invalid()
        if self.provider_cost_amount < 0:
            _invalid()
        if self.fx_rate_to_jpy <= 0:
            _invalid()
        if self.cost_jpy.value < 0:
            _invalid()

    def __repr__(self) -> str:
        return "UsageCost(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class AiAttempt:
    state: AiAttemptState
    evaluation_case_result_rows: tuple[EvaluationCaseResult, ...] = ()
    usage_cost_rows: tuple[UsageCost, ...] = ()

    def __post_init__(self) -> None:
        if type(self.state) is not AiAttemptState:
            _invalid()
        if type(self.evaluation_case_result_rows) is not tuple or any(
            type(item) is not EvaluationCaseResult
            for item in self.evaluation_case_result_rows
        ):
            _invalid()
        if self.evaluation_case_result_rows != tuple(
            sorted(
                self.evaluation_case_result_rows,
                key=lambda item: (_order_value(item.id),),
            )
        ):
            _invalid()
        if type(self.usage_cost_rows) is not tuple or any(
            type(item) is not UsageCost for item in self.usage_cost_rows
        ):
            _invalid()
        if self.usage_cost_rows != tuple(
            sorted(self.usage_cost_rows, key=lambda item: (_order_value(item.id),))
        ):
            _invalid()

    def __repr__(self) -> str:
        return "AiAttempt(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class AiJob:
    state: AiJobState
    ai_attempt_rows: tuple[AiAttemptState, ...] = ()
    usage_cost_rows: tuple[UsageCost, ...] = ()
    _events: PendingEventBuffer[DomainEvent] = field(
        default_factory=PendingEventBuffer[DomainEvent], repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if type(self.state) is not AiJobState:
            _invalid()
        if type(self.ai_attempt_rows) is not tuple or any(
            type(item) is not AiAttemptState for item in self.ai_attempt_rows
        ):
            _invalid()
        if self.ai_attempt_rows != tuple(
            sorted(self.ai_attempt_rows, key=lambda item: (_order_value(item.id),))
        ):
            _invalid()
        if type(self.usage_cost_rows) is not tuple or any(
            type(item) is not UsageCost for item in self.usage_cost_rows
        ):
            _invalid()
        if self.usage_cost_rows != tuple(
            sorted(self.usage_cost_rows, key=lambda item: (_order_value(item.id),))
        ):
            _invalid()
        if type(self._events) is not PendingEventBuffer:
            _invalid()

    def pending_events(self) -> tuple[DomainEvent, ...]:
        return self._events.pending_events()

    def acknowledge_events(self, event_ids: tuple[UUID, ...]) -> None:
        self._events.acknowledge_events(event_ids)

    def _record_event(self, event: DomainEvent) -> None:
        self._events.record(event)

    def _restore_acknowledged_events(self) -> None:
        self._events.restore_acknowledged()

    def _finish_acknowledged_events(self) -> None:
        self._events.finish_acknowledged()

    def __repr__(self) -> str:
        return "AiJob(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class AiTaskDefinition:
    state: AiTaskDefinitionState

    def __post_init__(self) -> None:
        if type(self.state) is not AiTaskDefinitionState:
            _invalid()

    def __repr__(self) -> str:
        return "AiTaskDefinition(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class EvaluationDatasetVersion:
    state: EvaluationDatasetVersionState
    evaluation_case_rows: tuple[EvaluationCase, ...] = ()

    def __post_init__(self) -> None:
        if type(self.state) is not EvaluationDatasetVersionState:
            _invalid()
        if type(self.evaluation_case_rows) is not tuple or any(
            type(item) is not EvaluationCase for item in self.evaluation_case_rows
        ):
            _invalid()
        if self.evaluation_case_rows != tuple(
            sorted(self.evaluation_case_rows, key=lambda item: (_order_value(item.id),))
        ):
            _invalid()

    def __repr__(self) -> str:
        return "EvaluationDatasetVersion(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class EvaluationResult:
    state: EvaluationResultState

    def __post_init__(self) -> None:
        if type(self.state) is not EvaluationResultState:
            _invalid()

    def __repr__(self) -> str:
        return "EvaluationResult(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class EvaluationRun:
    state: EvaluationRunState
    evaluation_case_result_rows: tuple[EvaluationCaseResult, ...] = ()
    human_evaluation_rows: tuple[HumanEvaluation, ...] = ()
    _events: PendingEventBuffer[DomainEvent] = field(
        default_factory=PendingEventBuffer[DomainEvent], repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if type(self.state) is not EvaluationRunState:
            _invalid()
        if type(self.evaluation_case_result_rows) is not tuple or any(
            type(item) is not EvaluationCaseResult
            for item in self.evaluation_case_result_rows
        ):
            _invalid()
        if self.evaluation_case_result_rows != tuple(
            sorted(
                self.evaluation_case_result_rows,
                key=lambda item: (_order_value(item.id),),
            )
        ):
            _invalid()
        if type(self.human_evaluation_rows) is not tuple or any(
            type(item) is not HumanEvaluation for item in self.human_evaluation_rows
        ):
            _invalid()
        if self.human_evaluation_rows != tuple(
            sorted(
                self.human_evaluation_rows, key=lambda item: (_order_value(item.id),)
            )
        ):
            _invalid()
        if type(self._events) is not PendingEventBuffer:
            _invalid()

    def pending_events(self) -> tuple[DomainEvent, ...]:
        return self._events.pending_events()

    def acknowledge_events(self, event_ids: tuple[UUID, ...]) -> None:
        self._events.acknowledge_events(event_ids)

    def _record_event(self, event: DomainEvent) -> None:
        self._events.record(event)

    def _restore_acknowledged_events(self) -> None:
        self._events.restore_acknowledged()

    def _finish_acknowledged_events(self) -> None:
        self._events.finish_acknowledged()

    def __repr__(self) -> str:
        return "EvaluationRun(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class EvaluationSuite:
    state: EvaluationSuiteState

    def __post_init__(self) -> None:
        if type(self.state) is not EvaluationSuiteState:
            _invalid()

    def __repr__(self) -> str:
        return "EvaluationSuite(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class JudgeCalibration:
    state: JudgeCalibrationState

    def __post_init__(self) -> None:
        if type(self.state) is not JudgeCalibrationState:
            _invalid()

    def __repr__(self) -> str:
        return "JudgeCalibration(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ModelDefinition:
    state: ModelDefinitionState

    def __post_init__(self) -> None:
        if type(self.state) is not ModelDefinitionState:
            _invalid()

    def __repr__(self) -> str:
        return "ModelDefinition(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ModelRouteVersion:
    state: ModelRouteVersionState

    def __post_init__(self) -> None:
        if type(self.state) is not ModelRouteVersionState:
            _invalid()

    def __repr__(self) -> str:
        return "ModelRouteVersion(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class OutputSchemaVersion:
    state: OutputSchemaVersionState

    def __post_init__(self) -> None:
        if type(self.state) is not OutputSchemaVersionState:
            _invalid()

    def __repr__(self) -> str:
        return "OutputSchemaVersion(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class PromptVersion:
    state: PromptVersionState

    def __post_init__(self) -> None:
        if type(self.state) is not PromptVersionState:
            _invalid()

    def __repr__(self) -> str:
        return "PromptVersion(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ReleaseDecision:
    state: ReleaseDecisionState
    release_approval_rows: tuple[ReleaseApproval, ...] = ()
    _events: PendingEventBuffer[DomainEvent] = field(
        default_factory=PendingEventBuffer[DomainEvent], repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if type(self.state) is not ReleaseDecisionState:
            _invalid()
        if type(self.release_approval_rows) is not tuple or any(
            type(item) is not ReleaseApproval for item in self.release_approval_rows
        ):
            _invalid()
        if self.release_approval_rows != tuple(
            sorted(
                self.release_approval_rows, key=lambda item: (_order_value(item.id),)
            )
        ):
            _invalid()
        if type(self._events) is not PendingEventBuffer:
            _invalid()

    def pending_events(self) -> tuple[DomainEvent, ...]:
        return self._events.pending_events()

    def acknowledge_events(self, event_ids: tuple[UUID, ...]) -> None:
        self._events.acknowledge_events(event_ids)

    def _record_event(self, event: DomainEvent) -> None:
        self._events.record(event)

    def _restore_acknowledged_events(self) -> None:
        self._events.restore_acknowledged()

    def _finish_acknowledged_events(self) -> None:
        self._events.finish_acknowledged()

    def __repr__(self) -> str:
        return "ReleaseDecision(<redacted>)"


__all__ = [
    "AiAttempt",
    "AiAttemptState",
    "AiJob",
    "AiJobState",
    "AiTaskDefinition",
    "AiTaskDefinitionState",
    "EvaluationCase",
    "EvaluationCaseResult",
    "EvaluationDatasetVersion",
    "EvaluationDatasetVersionState",
    "EvaluationResult",
    "EvaluationResultState",
    "EvaluationRun",
    "EvaluationRunState",
    "EvaluationSuite",
    "EvaluationSuiteState",
    "HumanEvaluation",
    "JudgeCalibration",
    "JudgeCalibrationState",
    "ModelDefinition",
    "ModelDefinitionState",
    "ModelRouteVersion",
    "ModelRouteVersionState",
    "OutputSchemaVersion",
    "OutputSchemaVersionState",
    "PromptVersion",
    "PromptVersionState",
    "ReleaseApproval",
    "ReleaseDecision",
    "ReleaseDecisionState",
    "UsageCost",
]

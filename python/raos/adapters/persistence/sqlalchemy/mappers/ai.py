"""Explicit fail-closed scalar mappers for the AI ST-0308 slice."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from raos.adapters.persistence.sqlalchemy.physical_constraints import (
    install_mapper_physical_constraint_guards,
)
from raos.domain.ai.aggregates import (
    AiAttemptState,
    AiJobState,
    AiTaskDefinitionState,
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationDatasetVersionState,
    EvaluationResultState,
    EvaluationRunState,
    EvaluationSuiteState,
    HumanEvaluation,
    JudgeCalibrationState,
    ModelDefinitionState,
    ModelRouteVersionState,
    OutputSchemaVersionState,
    PromptVersionState,
    ReleaseApproval,
    ReleaseDecisionState,
    UsageCost,
)
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
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode


def _corrupt() -> PersistenceError:
    return PersistenceError(PersistenceErrorCode.STORAGE_CORRUPTION)


AiAttemptStateScalars = tuple[
    AiAttemptId,
    AiJobId,
    int,
    ModelDefinitionId,
    str | None,
    AiAttemptStatus,
    ObjectArtifactId,
    ObjectArtifactId | None,
    Sha256Digest,
    Sha256Digest | None,
    str | None,
    str | None,
    int | None,
    str | None,
    str | None,
    str | None,
    AwareUtcDateTime,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
    str,
    str,
    str | None,
    str | None,
    AiAttemptRequestConfigJson,
    AiAttemptValidationStatus,
    Sha256Digest | None,
    int,
]


def map_ai_ai_attempt_from_row(
    *,
    id: AiAttemptId,
    ai_job_id: AiJobId,
    attempt_no: int,
    model_id: ModelDefinitionId,
    provider_request_id: str | None,
    status: AiAttemptStatus,
    input_artifact_id: ObjectArtifactId,
    output_artifact_id: ObjectArtifactId | None,
    input_sha256: Sha256Digest,
    output_sha256: Sha256Digest | None,
    refusal_code: str | None,
    finish_reason: str | None,
    latency_ms: int | None,
    error_class: str | None,
    error_code: str | None,
    error_message: str | None,
    started_at: AwareUtcDateTime,
    completed_at: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
    requested_model_id: str,
    resolved_model_id: str,
    response_fingerprint: str | None,
    provider_region: str | None,
    request_config: AiAttemptRequestConfigJson,
    validation_status: AiAttemptValidationStatus,
    safety_identifier_hash: Sha256Digest | None,
    repair_attempt_no: int,
) -> AiAttemptState:
    try:
        return AiAttemptState(
            id=id,
            ai_job_id=ai_job_id,
            attempt_no=attempt_no,
            model_id=model_id,
            provider_request_id=provider_request_id,
            status=status,
            input_artifact_id=input_artifact_id,
            output_artifact_id=output_artifact_id,
            input_sha256=input_sha256,
            output_sha256=output_sha256,
            refusal_code=refusal_code,
            finish_reason=finish_reason,
            latency_ms=latency_ms,
            error_class=error_class,
            error_code=error_code,
            error_message=error_message,
            started_at=started_at,
            completed_at=completed_at,
            created_at=created_at,
            requested_model_id=requested_model_id,
            resolved_model_id=resolved_model_id,
            response_fingerprint=response_fingerprint,
            provider_region=provider_region,
            request_config=request_config,
            validation_status=validation_status,
            safety_identifier_hash=safety_identifier_hash,
            repair_attempt_no=repair_attempt_no,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ai_ai_attempt_to_row(value: AiAttemptState) -> AiAttemptStateScalars:
    if type(value) is not AiAttemptState:
        raise _corrupt() from None
    return (
        value.id,
        value.ai_job_id,
        value.attempt_no,
        value.model_id,
        value.provider_request_id,
        value.status,
        value.input_artifact_id,
        value.output_artifact_id,
        value.input_sha256,
        value.output_sha256,
        value.refusal_code,
        value.finish_reason,
        value.latency_ms,
        value.error_class,
        value.error_code,
        value.error_message,
        value.started_at,
        value.completed_at,
        value.created_at,
        value.requested_model_id,
        value.resolved_model_id,
        value.response_fingerprint,
        value.provider_region,
        value.request_config,
        value.validation_status,
        value.safety_identifier_hash,
        value.repair_attempt_no,
    )


AiJobStateScalars = tuple[
    AiJobId,
    str,
    JobId,
    AiTaskDefinitionId,
    ArticlePlanId | None,
    ArticleVersionId | None,
    SourcePacketVersionId,
    PromptVersionId,
    OutputSchemaVersionId,
    ModelRouteVersionId,
    AiJobStatus,
    YenMinor,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
    PolicyBundleId | None,
    ReleaseDecisionId | None,
    AiJobRequestConfigJson,
    Sha256Digest | None,
    YenMinor,
    AggregateVersion,
    AwareUtcDateTime,
]


def map_ai_ai_job_from_row(
    *,
    id: AiJobId,
    display_id: str,
    ops_job_id: JobId,
    task_definition_id: AiTaskDefinitionId,
    article_plan_id: ArticlePlanId | None,
    article_version_id: ArticleVersionId | None,
    source_packet_version_id: SourcePacketVersionId,
    prompt_version_id: PromptVersionId,
    output_schema_version_id: OutputSchemaVersionId,
    model_route_version_id: ModelRouteVersionId,
    status: AiJobStatus,
    max_cost_jpy: YenMinor,
    completed_at: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
    policy_bundle_version_id: PolicyBundleId | None,
    release_decision_id: ReleaseDecisionId | None,
    request_config: AiJobRequestConfigJson,
    input_manifest_sha256: Sha256Digest | None,
    budget_reserved_jpy: YenMinor,
    lock_version: AggregateVersion,
    updated_at: AwareUtcDateTime,
) -> AiJobState:
    try:
        return AiJobState(
            id=id,
            display_id=display_id,
            ops_job_id=ops_job_id,
            task_definition_id=task_definition_id,
            article_plan_id=article_plan_id,
            article_version_id=article_version_id,
            source_packet_version_id=source_packet_version_id,
            prompt_version_id=prompt_version_id,
            output_schema_version_id=output_schema_version_id,
            model_route_version_id=model_route_version_id,
            status=status,
            max_cost_jpy=max_cost_jpy,
            completed_at=completed_at,
            created_at=created_at,
            policy_bundle_version_id=policy_bundle_version_id,
            release_decision_id=release_decision_id,
            request_config=request_config,
            input_manifest_sha256=input_manifest_sha256,
            budget_reserved_jpy=budget_reserved_jpy,
            lock_version=lock_version,
            updated_at=updated_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ai_ai_job_to_row(value: AiJobState) -> AiJobStateScalars:
    if type(value) is not AiJobState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.ops_job_id,
        value.task_definition_id,
        value.article_plan_id,
        value.article_version_id,
        value.source_packet_version_id,
        value.prompt_version_id,
        value.output_schema_version_id,
        value.model_route_version_id,
        value.status,
        value.max_cost_jpy,
        value.completed_at,
        value.created_at,
        value.policy_bundle_version_id,
        value.release_decision_id,
        value.request_config,
        value.input_manifest_sha256,
        value.budget_reserved_jpy,
        value.lock_version,
        value.updated_at,
    )


EvaluationCaseScalars = tuple[
    EvaluationCaseId,
    EvaluationDatasetVersionId,
    str,
    AiTaskDefinitionId,
    EvaluationCaseSplit,
    str,
    EvaluationCaseRiskLevel,
    ObjectArtifactId,
    ObjectArtifactId | None,
    EvaluationCaseExpectedDisposition,
    tuple[str, ...],
    EvaluationCaseMetadataJson,
    AwareUtcDateTime,
]


def map_ai_evaluation_case_from_row(
    *,
    id: EvaluationCaseId,
    dataset_version_id: EvaluationDatasetVersionId,
    case_key: str,
    task_definition_id: AiTaskDefinitionId,
    split: EvaluationCaseSplit,
    category: str,
    risk_level: EvaluationCaseRiskLevel,
    input_artifact_id: ObjectArtifactId,
    gold_artifact_id: ObjectArtifactId | None,
    expected_disposition: EvaluationCaseExpectedDisposition,
    tags: tuple[str, ...],
    metadata: EvaluationCaseMetadataJson,
    created_at: AwareUtcDateTime,
) -> EvaluationCase:
    try:
        return EvaluationCase(
            id=id,
            dataset_version_id=dataset_version_id,
            case_key=case_key,
            task_definition_id=task_definition_id,
            split=split,
            category=category,
            risk_level=risk_level,
            input_artifact_id=input_artifact_id,
            gold_artifact_id=gold_artifact_id,
            expected_disposition=expected_disposition,
            tags=tags,
            metadata=metadata,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ai_evaluation_case_to_row(value: EvaluationCase) -> EvaluationCaseScalars:
    if type(value) is not EvaluationCase:
        raise _corrupt() from None
    return (
        value.id,
        value.dataset_version_id,
        value.case_key,
        value.task_definition_id,
        value.split,
        value.category,
        value.risk_level,
        value.input_artifact_id,
        value.gold_artifact_id,
        value.expected_disposition,
        value.tags,
        value.metadata,
        value.created_at,
    )


EvaluationCaseResultScalars = tuple[
    EvaluationCaseResultId,
    EvaluationRunId,
    EvaluationCaseId,
    AiAttemptId | None,
    ObjectArtifactId | None,
    EvaluationCaseResultStatus,
    EvaluationCaseResultDisposition,
    EvaluationCaseResultZeroToleranceEvidenceJson,
    ObjectArtifactId,
    Sha256Digest,
    int,
    EvaluationCaseResultGraderSummaryJson,
    AwareUtcDateTime,
]


def map_ai_evaluation_case_result_from_row(
    *,
    id: EvaluationCaseResultId,
    evaluation_run_id: EvaluationRunId,
    evaluation_case_id: EvaluationCaseId,
    ai_attempt_id: AiAttemptId | None,
    output_artifact_id: ObjectArtifactId | None,
    status: EvaluationCaseResultStatus,
    disposition: EvaluationCaseResultDisposition,
    zero_tolerance_evidence: EvaluationCaseResultZeroToleranceEvidenceJson,
    zero_tolerance_evidence_artifact_id: ObjectArtifactId,
    zero_tolerance_evidence_sha256: Sha256Digest,
    zero_tolerance_failure_count: int,
    grader_summary: EvaluationCaseResultGraderSummaryJson,
    created_at: AwareUtcDateTime,
) -> EvaluationCaseResult:
    try:
        return EvaluationCaseResult(
            id=id,
            evaluation_run_id=evaluation_run_id,
            evaluation_case_id=evaluation_case_id,
            ai_attempt_id=ai_attempt_id,
            output_artifact_id=output_artifact_id,
            status=status,
            disposition=disposition,
            zero_tolerance_evidence=zero_tolerance_evidence,
            zero_tolerance_evidence_artifact_id=zero_tolerance_evidence_artifact_id,
            zero_tolerance_evidence_sha256=zero_tolerance_evidence_sha256,
            zero_tolerance_failure_count=zero_tolerance_failure_count,
            grader_summary=grader_summary,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ai_evaluation_case_result_to_row(
    value: EvaluationCaseResult,
) -> EvaluationCaseResultScalars:
    if type(value) is not EvaluationCaseResult:
        raise _corrupt() from None
    return (
        value.id,
        value.evaluation_run_id,
        value.evaluation_case_id,
        value.ai_attempt_id,
        value.output_artifact_id,
        value.status,
        value.disposition,
        value.zero_tolerance_evidence,
        value.zero_tolerance_evidence_artifact_id,
        value.zero_tolerance_evidence_sha256,
        value.zero_tolerance_failure_count,
        value.grader_summary,
        value.created_at,
    )


EvaluationDatasetVersionStateScalars = tuple[
    EvaluationDatasetVersionId,
    str,
    str,
    int,
    str,
    EvaluationDatasetVersionSplitPolicyJson,
    ObjectArtifactId,
    Sha256Digest,
    int,
    EvaluationDatasetStatus,
    PrincipalId | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime | None,
    AggregateVersion,
    AwareUtcDateTime,
    AwareUtcDateTime,
]


def map_ai_evaluation_dataset_version_from_row(
    *,
    id: EvaluationDatasetVersionId,
    display_id: str,
    dataset_code: str,
    version_no: int,
    purpose: str,
    split_policy: EvaluationDatasetVersionSplitPolicyJson,
    dataset_artifact_id: ObjectArtifactId,
    dataset_sha256: Sha256Digest,
    case_count: int,
    status: EvaluationDatasetStatus,
    locked_by_principal_id: PrincipalId | None,
    locked_at: AwareUtcDateTime | None,
    compromised_at: AwareUtcDateTime | None,
    lock_version: AggregateVersion,
    created_at: AwareUtcDateTime,
    updated_at: AwareUtcDateTime,
) -> EvaluationDatasetVersionState:
    try:
        return EvaluationDatasetVersionState(
            id=id,
            display_id=display_id,
            dataset_code=dataset_code,
            version_no=version_no,
            purpose=purpose,
            split_policy=split_policy,
            dataset_artifact_id=dataset_artifact_id,
            dataset_sha256=dataset_sha256,
            case_count=case_count,
            status=status,
            locked_by_principal_id=locked_by_principal_id,
            locked_at=locked_at,
            compromised_at=compromised_at,
            lock_version=lock_version,
            created_at=created_at,
            updated_at=updated_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ai_evaluation_dataset_version_to_row(
    value: EvaluationDatasetVersionState,
) -> EvaluationDatasetVersionStateScalars:
    if type(value) is not EvaluationDatasetVersionState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.dataset_code,
        value.version_no,
        value.purpose,
        value.split_policy,
        value.dataset_artifact_id,
        value.dataset_sha256,
        value.case_count,
        value.status,
        value.locked_by_principal_id,
        value.locked_at,
        value.compromised_at,
        value.lock_version,
        value.created_at,
        value.updated_at,
    )


EvaluationResultStateScalars = tuple[
    EvaluationResultId,
    str,
    int,
    RunId,
    AiTaskDefinitionId,
    ModelRouteVersionId,
    PromptVersionId,
    str,
    EvaluationResultMetricCode,
    Decimal,
    bool | None,
    EvaluationResultDetailsJson,
    ObjectArtifactId | None,
    AwareUtcDateTime,
    EvaluationRunId | None,
    EvaluationCaseId | None,
    str | None,
    str | None,
    EvaluationResultThresholdOperator | None,
    Decimal | None,
    JudgeCalibrationId | None,
    ModelRouteVersionId | None,
    PromptVersionId | None,
    ObjectArtifactId | None,
    ModelDefinitionId | None,
    str | None,
    int | None,
    int | None,
]


def map_ai_evaluation_result_from_row(
    *,
    id: EvaluationResultId,
    suite_code: str,
    suite_version: int,
    run_id: RunId,
    task_definition_id: AiTaskDefinitionId,
    model_route_version_id: ModelRouteVersionId,
    prompt_version_id: PromptVersionId,
    case_key: str,
    metric_code: EvaluationResultMetricCode,
    metric_value: Decimal,
    passed: bool | None,
    details: EvaluationResultDetailsJson,
    result_artifact_id: ObjectArtifactId | None,
    created_at: AwareUtcDateTime,
    evaluation_run_id: EvaluationRunId | None,
    evaluation_case_id: EvaluationCaseId | None,
    grader_code: str | None,
    slice_key: str | None,
    threshold_operator: EvaluationResultThresholdOperator | None,
    threshold_value: Decimal | None,
    judge_calibration_id: JudgeCalibrationId | None,
    judge_route_version_id: ModelRouteVersionId | None,
    judge_prompt_version_id: PromptVersionId | None,
    judge_rubric_artifact_id: ObjectArtifactId | None,
    judge_resolved_model_id: ModelDefinitionId | None,
    judge_grader_version: str | None,
    proportion_numerator_count: int | None,
    proportion_denominator_count: int | None,
) -> EvaluationResultState:
    try:
        return EvaluationResultState(
            id=id,
            suite_code=suite_code,
            suite_version=suite_version,
            run_id=run_id,
            task_definition_id=task_definition_id,
            model_route_version_id=model_route_version_id,
            prompt_version_id=prompt_version_id,
            case_key=case_key,
            metric_code=metric_code,
            metric_value=metric_value,
            passed=passed,
            details=details,
            result_artifact_id=result_artifact_id,
            created_at=created_at,
            evaluation_run_id=evaluation_run_id,
            evaluation_case_id=evaluation_case_id,
            grader_code=grader_code,
            slice_key=slice_key,
            threshold_operator=threshold_operator,
            threshold_value=threshold_value,
            judge_calibration_id=judge_calibration_id,
            judge_route_version_id=judge_route_version_id,
            judge_prompt_version_id=judge_prompt_version_id,
            judge_rubric_artifact_id=judge_rubric_artifact_id,
            judge_resolved_model_id=judge_resolved_model_id,
            judge_grader_version=judge_grader_version,
            proportion_numerator_count=proportion_numerator_count,
            proportion_denominator_count=proportion_denominator_count,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ai_evaluation_result_to_row(
    value: EvaluationResultState,
) -> EvaluationResultStateScalars:
    if type(value) is not EvaluationResultState:
        raise _corrupt() from None
    return (
        value.id,
        value.suite_code,
        value.suite_version,
        value.run_id,
        value.task_definition_id,
        value.model_route_version_id,
        value.prompt_version_id,
        value.case_key,
        value.metric_code,
        value.metric_value,
        value.passed,
        value.details,
        value.result_artifact_id,
        value.created_at,
        value.evaluation_run_id,
        value.evaluation_case_id,
        value.grader_code,
        value.slice_key,
        value.threshold_operator,
        value.threshold_value,
        value.judge_calibration_id,
        value.judge_route_version_id,
        value.judge_prompt_version_id,
        value.judge_rubric_artifact_id,
        value.judge_resolved_model_id,
        value.judge_grader_version,
        value.proportion_numerator_count,
        value.proportion_denominator_count,
    )


EvaluationRunStateScalars = tuple[
    EvaluationRunId,
    str,
    EvaluationSuiteId,
    EvaluationDatasetVersionId,
    EvaluationRunId | None,
    PromptVersionId,
    ModelRouteVersionId,
    OutputSchemaVersionId,
    PolicyBundleId,
    GitCommitDigest,
    EvaluationRunStatus,
    ObjectArtifactId | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime | None,
    PrincipalId,
    AggregateVersion,
    AwareUtcDateTime,
    AwareUtcDateTime,
    ModelDefinitionId,
]


def map_ai_evaluation_run_from_row(
    *,
    id: EvaluationRunId,
    display_id: str,
    suite_id: EvaluationSuiteId,
    dataset_version_id: EvaluationDatasetVersionId,
    baseline_evaluation_run_id: EvaluationRunId | None,
    prompt_version_id: PromptVersionId,
    model_route_version_id: ModelRouteVersionId,
    output_schema_version_id: OutputSchemaVersionId,
    policy_bundle_version_id: PolicyBundleId,
    code_git_sha: GitCommitDigest,
    status: EvaluationRunStatus,
    run_manifest_artifact_id: ObjectArtifactId | None,
    started_at: AwareUtcDateTime | None,
    completed_at: AwareUtcDateTime | None,
    created_by_principal_id: PrincipalId,
    lock_version: AggregateVersion,
    created_at: AwareUtcDateTime,
    updated_at: AwareUtcDateTime,
    resolved_model_id: ModelDefinitionId,
) -> EvaluationRunState:
    try:
        return EvaluationRunState(
            id=id,
            display_id=display_id,
            suite_id=suite_id,
            dataset_version_id=dataset_version_id,
            baseline_evaluation_run_id=baseline_evaluation_run_id,
            prompt_version_id=prompt_version_id,
            model_route_version_id=model_route_version_id,
            output_schema_version_id=output_schema_version_id,
            policy_bundle_version_id=policy_bundle_version_id,
            code_git_sha=code_git_sha,
            status=status,
            run_manifest_artifact_id=run_manifest_artifact_id,
            started_at=started_at,
            completed_at=completed_at,
            created_by_principal_id=created_by_principal_id,
            lock_version=lock_version,
            created_at=created_at,
            updated_at=updated_at,
            resolved_model_id=resolved_model_id,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ai_evaluation_run_to_row(
    value: EvaluationRunState,
) -> EvaluationRunStateScalars:
    if type(value) is not EvaluationRunState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.suite_id,
        value.dataset_version_id,
        value.baseline_evaluation_run_id,
        value.prompt_version_id,
        value.model_route_version_id,
        value.output_schema_version_id,
        value.policy_bundle_version_id,
        value.code_git_sha,
        value.status,
        value.run_manifest_artifact_id,
        value.started_at,
        value.completed_at,
        value.created_by_principal_id,
        value.lock_version,
        value.created_at,
        value.updated_at,
        value.resolved_model_id,
    )


EvaluationSuiteStateScalars = tuple[
    EvaluationSuiteId,
    str,
    int,
    AiTaskDefinitionId,
    EvaluationSuiteRiskLevel,
    ObjectArtifactId | None,
    EvaluationSuiteSuiteConfigJson,
    EvaluationSuiteStatus,
    PrincipalId | None,
    AwareUtcDateTime | None,
    AggregateVersion,
    AwareUtcDateTime,
    AwareUtcDateTime,
]


def map_ai_evaluation_suite_from_row(
    *,
    id: EvaluationSuiteId,
    suite_code: str,
    version_no: int,
    task_definition_id: AiTaskDefinitionId,
    risk_level: EvaluationSuiteRiskLevel,
    rubric_artifact_id: ObjectArtifactId | None,
    suite_config: EvaluationSuiteSuiteConfigJson,
    status: EvaluationSuiteStatus,
    approved_by_principal_id: PrincipalId | None,
    approved_at: AwareUtcDateTime | None,
    lock_version: AggregateVersion,
    created_at: AwareUtcDateTime,
    updated_at: AwareUtcDateTime,
) -> EvaluationSuiteState:
    try:
        return EvaluationSuiteState(
            id=id,
            suite_code=suite_code,
            version_no=version_no,
            task_definition_id=task_definition_id,
            risk_level=risk_level,
            rubric_artifact_id=rubric_artifact_id,
            suite_config=suite_config,
            status=status,
            approved_by_principal_id=approved_by_principal_id,
            approved_at=approved_at,
            lock_version=lock_version,
            created_at=created_at,
            updated_at=updated_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ai_evaluation_suite_to_row(
    value: EvaluationSuiteState,
) -> EvaluationSuiteStateScalars:
    if type(value) is not EvaluationSuiteState:
        raise _corrupt() from None
    return (
        value.id,
        value.suite_code,
        value.version_no,
        value.task_definition_id,
        value.risk_level,
        value.rubric_artifact_id,
        value.suite_config,
        value.status,
        value.approved_by_principal_id,
        value.approved_at,
        value.lock_version,
        value.created_at,
        value.updated_at,
    )


HumanEvaluationScalars = tuple[
    HumanEvaluationId,
    EvaluationCaseResultId,
    PrincipalId,
    str,
    str,
    HumanEvaluationScoresJson,
    HumanEvaluationDecision,
    ObjectArtifactId | None,
    bool,
    AwareUtcDateTime,
]


def map_ai_human_evaluation_from_row(
    *,
    id: HumanEvaluationId,
    evaluation_case_result_id: EvaluationCaseResultId,
    reviewer_principal_id: PrincipalId,
    rubric_version: str,
    blind_assignment_key: str,
    scores: HumanEvaluationScoresJson,
    decision: HumanEvaluationDecision,
    notes_artifact_id: ObjectArtifactId | None,
    is_adjudication: bool,
    created_at: AwareUtcDateTime,
) -> HumanEvaluation:
    try:
        return HumanEvaluation(
            id=id,
            evaluation_case_result_id=evaluation_case_result_id,
            reviewer_principal_id=reviewer_principal_id,
            rubric_version=rubric_version,
            blind_assignment_key=blind_assignment_key,
            scores=scores,
            decision=decision,
            notes_artifact_id=notes_artifact_id,
            is_adjudication=is_adjudication,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ai_human_evaluation_to_row(value: HumanEvaluation) -> HumanEvaluationScalars:
    if type(value) is not HumanEvaluation:
        raise _corrupt() from None
    return (
        value.id,
        value.evaluation_case_result_id,
        value.reviewer_principal_id,
        value.rubric_version,
        value.blind_assignment_key,
        value.scores,
        value.decision,
        value.notes_artifact_id,
        value.is_adjudication,
        value.created_at,
    )


JudgeCalibrationStateScalars = tuple[
    JudgeCalibrationId,
    str,
    ModelRouteVersionId,
    PromptVersionId,
    EvaluationDatasetVersionId,
    Decimal | None,
    Decimal | None,
    Decimal | None,
    int,
    JudgeCalibrationStatus,
    ObjectArtifactId | None,
    PrincipalId | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime | None,
    AggregateVersion,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AiTaskDefinitionId,
    ModelDefinitionId,
    ObjectArtifactId,
    Sha256Digest,
    str,
]


def map_ai_judge_calibration_from_row(
    *,
    id: JudgeCalibrationId,
    display_id: str,
    judge_route_version_id: ModelRouteVersionId,
    judge_prompt_version_id: PromptVersionId,
    dataset_version_id: EvaluationDatasetVersionId,
    weighted_kappa: Decimal | None,
    zero_tolerance_false_pass_rate: Decimal | None,
    zero_tolerance_false_fail_rate: Decimal | None,
    case_count: int,
    status: JudgeCalibrationStatus,
    report_artifact_id: ObjectArtifactId | None,
    approved_by_principal_id: PrincipalId | None,
    approved_at: AwareUtcDateTime | None,
    expires_at: AwareUtcDateTime | None,
    lock_version: AggregateVersion,
    created_at: AwareUtcDateTime,
    updated_at: AwareUtcDateTime,
    evaluated_task_definition_id: AiTaskDefinitionId,
    resolved_judge_model_id: ModelDefinitionId,
    rubric_artifact_id: ObjectArtifactId,
    rubric_sha256: Sha256Digest,
    grader_version: str,
) -> JudgeCalibrationState:
    try:
        return JudgeCalibrationState(
            id=id,
            display_id=display_id,
            judge_route_version_id=judge_route_version_id,
            judge_prompt_version_id=judge_prompt_version_id,
            dataset_version_id=dataset_version_id,
            weighted_kappa=weighted_kappa,
            zero_tolerance_false_pass_rate=zero_tolerance_false_pass_rate,
            zero_tolerance_false_fail_rate=zero_tolerance_false_fail_rate,
            case_count=case_count,
            status=status,
            report_artifact_id=report_artifact_id,
            approved_by_principal_id=approved_by_principal_id,
            approved_at=approved_at,
            expires_at=expires_at,
            lock_version=lock_version,
            created_at=created_at,
            updated_at=updated_at,
            evaluated_task_definition_id=evaluated_task_definition_id,
            resolved_judge_model_id=resolved_judge_model_id,
            rubric_artifact_id=rubric_artifact_id,
            rubric_sha256=rubric_sha256,
            grader_version=grader_version,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ai_judge_calibration_to_row(
    value: JudgeCalibrationState,
) -> JudgeCalibrationStateScalars:
    if type(value) is not JudgeCalibrationState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.judge_route_version_id,
        value.judge_prompt_version_id,
        value.dataset_version_id,
        value.weighted_kappa,
        value.zero_tolerance_false_pass_rate,
        value.zero_tolerance_false_fail_rate,
        value.case_count,
        value.status,
        value.report_artifact_id,
        value.approved_by_principal_id,
        value.approved_at,
        value.expires_at,
        value.lock_version,
        value.created_at,
        value.updated_at,
        value.evaluated_task_definition_id,
        value.resolved_judge_model_id,
        value.rubric_artifact_id,
        value.rubric_sha256,
        value.grader_version,
    )


ModelDefinitionStateScalars = tuple[
    ModelDefinitionId,
    str,
    str,
    str,
    ModelDefinitionCapabilitiesJson,
    Decimal | None,
    Decimal | None,
    Decimal | None,
    str | None,
    AwareUtcDateTime | None,
    ModelDefinitionStatus,
    AwareUtcDateTime,
    int | None,
    int | None,
    date | None,
    AwareUtcDateTime | None,
    ModelDefinitionProviderMetadataJson,
]


def map_ai_model_definition_from_row(
    *,
    id: ModelDefinitionId,
    provider_code: str,
    provider_model_id: str,
    display_name: str,
    capabilities: ModelDefinitionCapabilitiesJson,
    input_price_per_million: Decimal | None,
    cached_input_price_per_million: Decimal | None,
    output_price_per_million: Decimal | None,
    pricing_currency: str | None,
    pricing_observed_at: AwareUtcDateTime | None,
    status: ModelDefinitionStatus,
    created_at: AwareUtcDateTime,
    context_window_tokens: int | None,
    max_output_tokens: int | None,
    knowledge_cutoff: date | None,
    metadata_observed_at: AwareUtcDateTime | None,
    provider_metadata: ModelDefinitionProviderMetadataJson,
) -> ModelDefinitionState:
    try:
        return ModelDefinitionState(
            id=id,
            provider_code=provider_code,
            provider_model_id=provider_model_id,
            display_name=display_name,
            capabilities=capabilities,
            input_price_per_million=input_price_per_million,
            cached_input_price_per_million=cached_input_price_per_million,
            output_price_per_million=output_price_per_million,
            pricing_currency=pricing_currency,
            pricing_observed_at=pricing_observed_at,
            status=status,
            created_at=created_at,
            context_window_tokens=context_window_tokens,
            max_output_tokens=max_output_tokens,
            knowledge_cutoff=knowledge_cutoff,
            metadata_observed_at=metadata_observed_at,
            provider_metadata=provider_metadata,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ai_model_definition_to_row(
    value: ModelDefinitionState,
) -> ModelDefinitionStateScalars:
    if type(value) is not ModelDefinitionState:
        raise _corrupt() from None
    return (
        value.id,
        value.provider_code,
        value.provider_model_id,
        value.display_name,
        value.capabilities,
        value.input_price_per_million,
        value.cached_input_price_per_million,
        value.output_price_per_million,
        value.pricing_currency,
        value.pricing_observed_at,
        value.status,
        value.created_at,
        value.context_window_tokens,
        value.max_output_tokens,
        value.knowledge_cutoff,
        value.metadata_observed_at,
        value.provider_metadata,
    )


ModelRouteVersionStateScalars = tuple[
    ModelRouteVersionId,
    str,
    int,
    AiTaskDefinitionId,
    ModelDefinitionId,
    ModelDefinitionId | None,
    ModelRouteVersionRouteConfigJson,
    YenMinor | None,
    YenMinor,
    ModelRouteVersionStatus,
    AwareUtcDateTime | None,
    AwareUtcDateTime | None,
    PrincipalId | None,
    AwareUtcDateTime,
    AggregateVersion,
    AwareUtcDateTime,
]


def map_ai_model_route_version_from_row(
    *,
    id: ModelRouteVersionId,
    route_code: str,
    version_no: int,
    task_definition_id: AiTaskDefinitionId,
    primary_model_id: ModelDefinitionId,
    fallback_model_id: ModelDefinitionId | None,
    route_config: ModelRouteVersionRouteConfigJson,
    monthly_budget_jpy: YenMinor | None,
    per_job_budget_jpy: YenMinor,
    status: ModelRouteVersionStatus,
    effective_from: AwareUtcDateTime | None,
    effective_to: AwareUtcDateTime | None,
    approved_by_principal_id: PrincipalId | None,
    created_at: AwareUtcDateTime,
    lock_version: AggregateVersion,
    updated_at: AwareUtcDateTime,
) -> ModelRouteVersionState:
    try:
        return ModelRouteVersionState(
            id=id,
            route_code=route_code,
            version_no=version_no,
            task_definition_id=task_definition_id,
            primary_model_id=primary_model_id,
            fallback_model_id=fallback_model_id,
            route_config=route_config,
            monthly_budget_jpy=monthly_budget_jpy,
            per_job_budget_jpy=per_job_budget_jpy,
            status=status,
            effective_from=effective_from,
            effective_to=effective_to,
            approved_by_principal_id=approved_by_principal_id,
            created_at=created_at,
            lock_version=lock_version,
            updated_at=updated_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ai_model_route_version_to_row(
    value: ModelRouteVersionState,
) -> ModelRouteVersionStateScalars:
    if type(value) is not ModelRouteVersionState:
        raise _corrupt() from None
    return (
        value.id,
        value.route_code,
        value.version_no,
        value.task_definition_id,
        value.primary_model_id,
        value.fallback_model_id,
        value.route_config,
        value.monthly_budget_jpy,
        value.per_job_budget_jpy,
        value.status,
        value.effective_from,
        value.effective_to,
        value.approved_by_principal_id,
        value.created_at,
        value.lock_version,
        value.updated_at,
    )


OutputSchemaVersionStateScalars = tuple[
    OutputSchemaVersionId,
    str,
    int,
    str,
    str,
    Sha256Digest,
    OutputSchemaVersionStatus,
    AwareUtcDateTime | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
]


def map_ai_output_schema_version_from_row(
    *,
    id: OutputSchemaVersionId,
    schema_code: str,
    version_no: int,
    git_path: str,
    git_commit_sha: str,
    schema_sha256: Sha256Digest,
    status: OutputSchemaVersionStatus,
    effective_from: AwareUtcDateTime | None,
    effective_to: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
) -> OutputSchemaVersionState:
    try:
        return OutputSchemaVersionState(
            id=id,
            schema_code=schema_code,
            version_no=version_no,
            git_path=git_path,
            git_commit_sha=git_commit_sha,
            schema_sha256=schema_sha256,
            status=status,
            effective_from=effective_from,
            effective_to=effective_to,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ai_output_schema_version_to_row(
    value: OutputSchemaVersionState,
) -> OutputSchemaVersionStateScalars:
    if type(value) is not OutputSchemaVersionState:
        raise _corrupt() from None
    return (
        value.id,
        value.schema_code,
        value.version_no,
        value.git_path,
        value.git_commit_sha,
        value.schema_sha256,
        value.status,
        value.effective_from,
        value.effective_to,
        value.created_at,
    )


PromptVersionStateScalars = tuple[
    PromptVersionId,
    str,
    AiTaskDefinitionId,
    str,
    int,
    str,
    str,
    Sha256Digest,
    PromptVersionStatus,
    AwareUtcDateTime | None,
    AwareUtcDateTime | None,
    PrincipalId | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
    str,
    str | None,
    Sha256Digest | None,
    PromptVersionPolicyTestStatus,
    AggregateVersion,
    AwareUtcDateTime,
    PrincipalId,
]


def map_ai_prompt_version_from_row(
    *,
    id: PromptVersionId,
    display_id: str,
    task_definition_id: AiTaskDefinitionId,
    prompt_code: str,
    version_no: int,
    git_path: str,
    git_commit_sha: str,
    template_sha256: Sha256Digest,
    status: PromptVersionStatus,
    effective_from: AwareUtcDateTime | None,
    effective_to: AwareUtcDateTime | None,
    approved_by_principal_id: PrincipalId | None,
    approved_at: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
    locale: str,
    compiler_version: str | None,
    input_contract_sha256: Sha256Digest | None,
    policy_test_status: PromptVersionPolicyTestStatus,
    lock_version: AggregateVersion,
    updated_at: AwareUtcDateTime,
    author_principal_id: PrincipalId,
) -> PromptVersionState:
    try:
        return PromptVersionState(
            id=id,
            display_id=display_id,
            task_definition_id=task_definition_id,
            prompt_code=prompt_code,
            version_no=version_no,
            git_path=git_path,
            git_commit_sha=git_commit_sha,
            template_sha256=template_sha256,
            status=status,
            effective_from=effective_from,
            effective_to=effective_to,
            approved_by_principal_id=approved_by_principal_id,
            approved_at=approved_at,
            created_at=created_at,
            locale=locale,
            compiler_version=compiler_version,
            input_contract_sha256=input_contract_sha256,
            policy_test_status=policy_test_status,
            lock_version=lock_version,
            updated_at=updated_at,
            author_principal_id=author_principal_id,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ai_prompt_version_to_row(
    value: PromptVersionState,
) -> PromptVersionStateScalars:
    if type(value) is not PromptVersionState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.task_definition_id,
        value.prompt_code,
        value.version_no,
        value.git_path,
        value.git_commit_sha,
        value.template_sha256,
        value.status,
        value.effective_from,
        value.effective_to,
        value.approved_by_principal_id,
        value.approved_at,
        value.created_at,
        value.locale,
        value.compiler_version,
        value.input_contract_sha256,
        value.policy_test_status,
        value.lock_version,
        value.updated_at,
        value.author_principal_id,
    )


ReleaseApprovalScalars = tuple[
    ReleaseApprovalId,
    str,
    ReleaseDecisionId,
    ReleaseApprovalPhase,
    Sha256Digest,
    PrincipalId,
    str,
    PrincipalId,
    str,
    ObjectArtifactId,
    Sha256Digest,
    AwareUtcDateTime,
    AwareUtcDateTime,
]


def map_ai_release_approval_from_row(
    *,
    id: ReleaseApprovalId,
    display_id: str,
    release_decision_id: ReleaseDecisionId,
    phase: ReleaseApprovalPhase,
    decision_manifest_sha256: Sha256Digest,
    primary_approver_principal_id: PrincipalId,
    primary_approver_role: str,
    second_approver_principal_id: PrincipalId,
    second_approver_role: str,
    approval_artifact_id: ObjectArtifactId,
    approval_sha256: Sha256Digest,
    signed_at: AwareUtcDateTime,
    created_at: AwareUtcDateTime,
) -> ReleaseApproval:
    try:
        return ReleaseApproval(
            id=id,
            display_id=display_id,
            release_decision_id=release_decision_id,
            phase=phase,
            decision_manifest_sha256=decision_manifest_sha256,
            primary_approver_principal_id=primary_approver_principal_id,
            primary_approver_role=primary_approver_role,
            second_approver_principal_id=second_approver_principal_id,
            second_approver_role=second_approver_role,
            approval_artifact_id=approval_artifact_id,
            approval_sha256=approval_sha256,
            signed_at=signed_at,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ai_release_approval_to_row(value: ReleaseApproval) -> ReleaseApprovalScalars:
    if type(value) is not ReleaseApproval:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.release_decision_id,
        value.phase,
        value.decision_manifest_sha256,
        value.primary_approver_principal_id,
        value.primary_approver_role,
        value.second_approver_principal_id,
        value.second_approver_role,
        value.approval_artifact_id,
        value.approval_sha256,
        value.signed_at,
        value.created_at,
    )


ReleaseDecisionStateScalars = tuple[
    ReleaseDecisionId,
    str,
    AiTaskDefinitionId,
    PromptVersionId,
    ModelRouteVersionId,
    OutputSchemaVersionId,
    ModelDefinitionId,
    PolicyBundleId,
    EvaluationDatasetVersionId,
    EvaluationRunId,
    GitCommitDigest,
    ReleaseDecisionReleaseScope,
    ReleaseDecisionStatus,
    int,
    Sha256Digest,
    ReleaseDecisionId | None,
    PrincipalId | None,
    PrincipalId | None,
    AwareUtcDateTime | None,
    PrincipalId | None,
    AwareUtcDateTime | None,
    str | None,
    AggregateVersion,
    AwareUtcDateTime,
    AwareUtcDateTime,
    JudgeCalibrationId | None,
    ReleaseDecisionRollbackStrategy,
    ObjectArtifactId | None,
    Sha256Digest | None,
    ObjectArtifactId | None,
    Sha256Digest | None,
    ObjectArtifactId | None,
    Sha256Digest | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime | None,
    int | None,
    int | None,
    ReleaseApprovalId | None,
    ReleaseApprovalId | None,
]


def map_ai_release_decision_from_row(
    *,
    id: ReleaseDecisionId,
    display_id: str,
    task_definition_id: AiTaskDefinitionId,
    prompt_version_id: PromptVersionId,
    model_route_version_id: ModelRouteVersionId,
    output_schema_version_id: OutputSchemaVersionId,
    resolved_model_id: ModelDefinitionId,
    policy_bundle_version_id: PolicyBundleId,
    dataset_version_id: EvaluationDatasetVersionId,
    evaluation_run_id: EvaluationRunId,
    code_git_sha: GitCommitDigest,
    release_scope: ReleaseDecisionReleaseScope,
    status: ReleaseDecisionStatus,
    maximum_canary_percent: int,
    decision_manifest_sha256: Sha256Digest,
    rollback_release_decision_id: ReleaseDecisionId | None,
    approved_by_principal_id: PrincipalId | None,
    second_approver_principal_id: PrincipalId | None,
    approved_at: AwareUtcDateTime | None,
    revoked_by_principal_id: PrincipalId | None,
    revoked_at: AwareUtcDateTime | None,
    revocation_reason: str | None,
    lock_version: AggregateVersion,
    created_at: AwareUtcDateTime,
    updated_at: AwareUtcDateTime,
    judge_calibration_id: JudgeCalibrationId | None,
    rollback_strategy: ReleaseDecisionRollbackStrategy,
    rollback_runbook_artifact_id: ObjectArtifactId | None,
    rollback_runbook_sha256: Sha256Digest | None,
    canary_monitoring_artifact_id: ObjectArtifactId | None,
    canary_monitoring_sha256: Sha256Digest | None,
    canary_evidence_artifact_id: ObjectArtifactId | None,
    canary_evidence_sha256: Sha256Digest | None,
    canary_started_at: AwareUtcDateTime | None,
    canary_completed_at: AwareUtcDateTime | None,
    canary_started_txid: int | None,
    canary_completed_txid: int | None,
    canary_approval_id: ReleaseApprovalId | None,
    active_approval_id: ReleaseApprovalId | None,
) -> ReleaseDecisionState:
    try:
        return ReleaseDecisionState(
            id=id,
            display_id=display_id,
            task_definition_id=task_definition_id,
            prompt_version_id=prompt_version_id,
            model_route_version_id=model_route_version_id,
            output_schema_version_id=output_schema_version_id,
            resolved_model_id=resolved_model_id,
            policy_bundle_version_id=policy_bundle_version_id,
            dataset_version_id=dataset_version_id,
            evaluation_run_id=evaluation_run_id,
            code_git_sha=code_git_sha,
            release_scope=release_scope,
            status=status,
            maximum_canary_percent=maximum_canary_percent,
            decision_manifest_sha256=decision_manifest_sha256,
            rollback_release_decision_id=rollback_release_decision_id,
            approved_by_principal_id=approved_by_principal_id,
            second_approver_principal_id=second_approver_principal_id,
            approved_at=approved_at,
            revoked_by_principal_id=revoked_by_principal_id,
            revoked_at=revoked_at,
            revocation_reason=revocation_reason,
            lock_version=lock_version,
            created_at=created_at,
            updated_at=updated_at,
            judge_calibration_id=judge_calibration_id,
            rollback_strategy=rollback_strategy,
            rollback_runbook_artifact_id=rollback_runbook_artifact_id,
            rollback_runbook_sha256=rollback_runbook_sha256,
            canary_monitoring_artifact_id=canary_monitoring_artifact_id,
            canary_monitoring_sha256=canary_monitoring_sha256,
            canary_evidence_artifact_id=canary_evidence_artifact_id,
            canary_evidence_sha256=canary_evidence_sha256,
            canary_started_at=canary_started_at,
            canary_completed_at=canary_completed_at,
            canary_started_txid=canary_started_txid,
            canary_completed_txid=canary_completed_txid,
            canary_approval_id=canary_approval_id,
            active_approval_id=active_approval_id,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ai_release_decision_to_row(
    value: ReleaseDecisionState,
) -> ReleaseDecisionStateScalars:
    if type(value) is not ReleaseDecisionState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.task_definition_id,
        value.prompt_version_id,
        value.model_route_version_id,
        value.output_schema_version_id,
        value.resolved_model_id,
        value.policy_bundle_version_id,
        value.dataset_version_id,
        value.evaluation_run_id,
        value.code_git_sha,
        value.release_scope,
        value.status,
        value.maximum_canary_percent,
        value.decision_manifest_sha256,
        value.rollback_release_decision_id,
        value.approved_by_principal_id,
        value.second_approver_principal_id,
        value.approved_at,
        value.revoked_by_principal_id,
        value.revoked_at,
        value.revocation_reason,
        value.lock_version,
        value.created_at,
        value.updated_at,
        value.judge_calibration_id,
        value.rollback_strategy,
        value.rollback_runbook_artifact_id,
        value.rollback_runbook_sha256,
        value.canary_monitoring_artifact_id,
        value.canary_monitoring_sha256,
        value.canary_evidence_artifact_id,
        value.canary_evidence_sha256,
        value.canary_started_at,
        value.canary_completed_at,
        value.canary_started_txid,
        value.canary_completed_txid,
        value.canary_approval_id,
        value.active_approval_id,
    )


AiTaskDefinitionStateScalars = tuple[
    AiTaskDefinitionId,
    str,
    str,
    str,
    AiTaskDefinitionRiskLevel,
    str,
    int,
    YenMinor,
    bool,
    AiTaskDefinitionStatus,
    AwareUtcDateTime,
]


def map_ai_task_definition_from_row(
    *,
    id: AiTaskDefinitionId,
    task_code: str,
    name: str,
    description: str,
    risk_level: AiTaskDefinitionRiskLevel,
    output_schema_code: str,
    default_max_tokens: int,
    default_max_cost_jpy: YenMinor,
    human_review_required: bool,
    status: AiTaskDefinitionStatus,
    created_at: AwareUtcDateTime,
) -> AiTaskDefinitionState:
    try:
        return AiTaskDefinitionState(
            id=id,
            task_code=task_code,
            name=name,
            description=description,
            risk_level=risk_level,
            output_schema_code=output_schema_code,
            default_max_tokens=default_max_tokens,
            default_max_cost_jpy=default_max_cost_jpy,
            human_review_required=human_review_required,
            status=status,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ai_task_definition_to_row(
    value: AiTaskDefinitionState,
) -> AiTaskDefinitionStateScalars:
    if type(value) is not AiTaskDefinitionState:
        raise _corrupt() from None
    return (
        value.id,
        value.task_code,
        value.name,
        value.description,
        value.risk_level,
        value.output_schema_code,
        value.default_max_tokens,
        value.default_max_cost_jpy,
        value.human_review_required,
        value.status,
        value.created_at,
    )


UsageCostScalars = tuple[
    UsageCostId,
    AiAttemptId,
    int,
    int,
    int,
    int,
    Decimal,
    str,
    Decimal,
    YenMinor,
    str,
    AwareUtcDateTime,
    AwareUtcDateTime,
]


def map_ai_usage_cost_from_row(
    *,
    id: UsageCostId,
    ai_attempt_id: AiAttemptId,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    provider_cost_amount: Decimal,
    provider_currency: str,
    fx_rate_to_jpy: Decimal,
    cost_jpy: YenMinor,
    pricing_version: str,
    observed_at: AwareUtcDateTime,
    created_at: AwareUtcDateTime,
) -> UsageCost:
    try:
        return UsageCost(
            id=id,
            ai_attempt_id=ai_attempt_id,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            provider_cost_amount=provider_cost_amount,
            provider_currency=provider_currency,
            fx_rate_to_jpy=fx_rate_to_jpy,
            cost_jpy=cost_jpy,
            pricing_version=pricing_version,
            observed_at=observed_at,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_ai_usage_cost_to_row(value: UsageCost) -> UsageCostScalars:
    if type(value) is not UsageCost:
        raise _corrupt() from None
    return (
        value.id,
        value.ai_attempt_id,
        value.input_tokens,
        value.cached_input_tokens,
        value.output_tokens,
        value.total_tokens,
        value.provider_cost_amount,
        value.provider_currency,
        value.fx_rate_to_jpy,
        value.cost_jpy,
        value.pricing_version,
        value.observed_at,
        value.created_at,
    )


__all__ = [
    "map_ai_ai_attempt_from_row",
    "map_ai_ai_attempt_to_row",
    "map_ai_ai_job_from_row",
    "map_ai_ai_job_to_row",
    "map_ai_evaluation_case_from_row",
    "map_ai_evaluation_case_result_from_row",
    "map_ai_evaluation_case_result_to_row",
    "map_ai_evaluation_case_to_row",
    "map_ai_evaluation_dataset_version_from_row",
    "map_ai_evaluation_dataset_version_to_row",
    "map_ai_evaluation_result_from_row",
    "map_ai_evaluation_result_to_row",
    "map_ai_evaluation_run_from_row",
    "map_ai_evaluation_run_to_row",
    "map_ai_evaluation_suite_from_row",
    "map_ai_evaluation_suite_to_row",
    "map_ai_human_evaluation_from_row",
    "map_ai_human_evaluation_to_row",
    "map_ai_judge_calibration_from_row",
    "map_ai_judge_calibration_to_row",
    "map_ai_model_definition_from_row",
    "map_ai_model_definition_to_row",
    "map_ai_model_route_version_from_row",
    "map_ai_model_route_version_to_row",
    "map_ai_output_schema_version_from_row",
    "map_ai_output_schema_version_to_row",
    "map_ai_prompt_version_from_row",
    "map_ai_prompt_version_to_row",
    "map_ai_release_approval_from_row",
    "map_ai_release_approval_to_row",
    "map_ai_release_decision_from_row",
    "map_ai_release_decision_to_row",
    "map_ai_task_definition_from_row",
    "map_ai_task_definition_to_row",
    "map_ai_usage_cost_from_row",
    "map_ai_usage_cost_to_row",
]

install_mapper_physical_constraint_guards(globals())

"""Exact aggregate-specific AI Repository Protocols for ST-0308."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.ai.aggregates import (
    AiAttempt,
    AiJob,
    AiTaskDefinition,
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationDatasetVersion,
    EvaluationResult,
    EvaluationRun,
    EvaluationSuite,
    HumanEvaluation,
    JudgeCalibration,
    ModelDefinition,
    ModelRouteVersion,
    OutputSchemaVersion,
    PromptVersion,
    ReleaseApproval,
    ReleaseDecision,
    UsageCost,
)
from raos.domain.ai.enums import (
    AiAttemptStatus,
    AiTaskDefinitionStatus,
    ModelDefinitionStatus,
    OutputSchemaVersionStatus,
)
from raos.domain.ai.ids import (
    AiAttemptId,
    AiJobId,
    AiTaskDefinitionId,
    EvaluationDatasetVersionId,
    EvaluationResultId,
    EvaluationRunId,
    EvaluationSuiteId,
    JudgeCalibrationId,
    ModelDefinitionId,
    ModelRouteVersionId,
    OutputSchemaVersionId,
    PromptVersionId,
    ReleaseDecisionId,
)
from raos.domain.shared.persistence import (
    AggregateVersion,
    PersistedVersion,
)


@runtime_checkable
class AiTaskDefinitionRepository(Protocol):
    def get(self, task_id: AiTaskDefinitionId) -> AiTaskDefinition | None: ...

    def get_by_code(self, task_code: str) -> AiTaskDefinition | None: ...

    def add(self, task: AiTaskDefinition) -> None: ...

    def transition(
        self,
        task_id: AiTaskDefinitionId,
        transition: AiTaskDefinition,
        expected_status: AiTaskDefinitionStatus,
    ) -> AiTaskDefinition: ...


@runtime_checkable
class OutputSchemaVersionRepository(Protocol):
    def get(self, version_id: OutputSchemaVersionId) -> OutputSchemaVersion | None: ...

    def get_active(self, schema_code: str) -> OutputSchemaVersion | None: ...

    def append_version(
        self,
        version: OutputSchemaVersion,
        expected_latest_version: int | None,
    ) -> PersistedVersion: ...

    def transition(
        self,
        version_id: OutputSchemaVersionId,
        transition: OutputSchemaVersion,
        expected_status: OutputSchemaVersionStatus,
    ) -> OutputSchemaVersion: ...


@runtime_checkable
class ModelDefinitionRepository(Protocol):
    def get(self, model_id: ModelDefinitionId) -> ModelDefinition | None: ...

    def add(self, model: ModelDefinition) -> None: ...

    def transition(
        self,
        model_id: ModelDefinitionId,
        transition: ModelDefinition,
        expected_status: ModelDefinitionStatus,
    ) -> ModelDefinition: ...


@runtime_checkable
class ModelRouteVersionRepository(Protocol):
    def get(self, version_id: ModelRouteVersionId) -> ModelRouteVersion | None: ...

    def get_active(self, route_code: str) -> ModelRouteVersion | None: ...

    def append_version(
        self,
        version: ModelRouteVersion,
        expected_latest_version: int | None,
    ) -> PersistedVersion: ...

    def transition(
        self,
        version_id: ModelRouteVersionId,
        transition: ModelRouteVersion,
        expected_version: AggregateVersion,
    ) -> ModelRouteVersion: ...


@runtime_checkable
class PromptVersionRepository(Protocol):
    def get(self, version_id: PromptVersionId) -> PromptVersion | None: ...

    def get_active(self, prompt_code: str) -> PromptVersion | None: ...

    def append_version(
        self,
        version: PromptVersion,
        expected_latest_version: int | None,
    ) -> PersistedVersion: ...

    def transition(
        self,
        version_id: PromptVersionId,
        transition: PromptVersion,
        expected_version: AggregateVersion,
    ) -> PromptVersion: ...


@runtime_checkable
class AiJobRepository(Protocol):
    def get(self, job_id: AiJobId) -> AiJob | None: ...

    def add(self, job: AiJob) -> PersistedVersion: ...

    def transition(
        self,
        job_id: AiJobId,
        transition: AiJob,
        expected_version: AggregateVersion,
    ) -> AiJob: ...

    def add_attempt(
        self,
        job_id: AiJobId,
        attempt: AiAttempt,
        expected_version: AggregateVersion,
    ) -> PersistedVersion: ...

    def complete_attempt(
        self,
        attempt_id: AiAttemptId,
        completion: AiAttempt,
        expected_status: AiAttemptStatus,
    ) -> AiAttempt: ...

    def append_usage_cost(
        self,
        attempt_id: AiAttemptId,
        usage: UsageCost,
    ) -> None: ...


@runtime_checkable
class EvaluationResultRepository(Protocol):
    def get(self, result_id: EvaluationResultId) -> EvaluationResult | None: ...

    def append(self, result: EvaluationResult) -> None: ...


@runtime_checkable
class EvaluationSuiteRepository(Protocol):
    def get(self, suite_id: EvaluationSuiteId) -> EvaluationSuite | None: ...

    def get_active(
        self,
        task_id: AiTaskDefinitionId,
        suite_code: str,
    ) -> EvaluationSuite | None: ...

    def append_version(
        self,
        suite: EvaluationSuite,
        expected_latest_version: int | None,
    ) -> PersistedVersion: ...

    def transition(
        self,
        suite_id: EvaluationSuiteId,
        transition: EvaluationSuite,
        expected_version: AggregateVersion,
    ) -> EvaluationSuite: ...


@runtime_checkable
class EvaluationDatasetRepository(Protocol):
    def get(
        self, dataset_id: EvaluationDatasetVersionId
    ) -> EvaluationDatasetVersion | None: ...

    def append_version(
        self,
        dataset: EvaluationDatasetVersion,
        expected_latest_version: int | None,
    ) -> PersistedVersion: ...

    def append_cases(
        self,
        dataset_id: EvaluationDatasetVersionId,
        cases: tuple[EvaluationCase, ...],
        expected_version: AggregateVersion,
    ) -> PersistedVersion: ...

    def transition(
        self,
        dataset_id: EvaluationDatasetVersionId,
        transition: EvaluationDatasetVersion,
        expected_version: AggregateVersion,
    ) -> EvaluationDatasetVersion: ...


@runtime_checkable
class EvaluationRunRepository(Protocol):
    def get(self, run_id: EvaluationRunId) -> EvaluationRun | None: ...

    def add(self, run: EvaluationRun) -> PersistedVersion: ...

    def transition(
        self,
        run_id: EvaluationRunId,
        transition: EvaluationRun,
        expected_version: AggregateVersion,
    ) -> EvaluationRun: ...

    def append_case_results(
        self,
        run_id: EvaluationRunId,
        results: tuple[EvaluationCaseResult, ...],
        expected_version: AggregateVersion,
    ) -> PersistedVersion: ...

    def append_human_evaluations(
        self,
        run_id: EvaluationRunId,
        evaluations: tuple[HumanEvaluation, ...],
        expected_version: AggregateVersion,
    ) -> PersistedVersion: ...


@runtime_checkable
class JudgeCalibrationRepository(Protocol):
    def get(self, calibration_id: JudgeCalibrationId) -> JudgeCalibration | None: ...

    def add(self, calibration: JudgeCalibration) -> PersistedVersion: ...

    def transition(
        self,
        calibration_id: JudgeCalibrationId,
        transition: JudgeCalibration,
        expected_version: AggregateVersion,
    ) -> JudgeCalibration: ...


@runtime_checkable
class ReleaseDecisionRepository(Protocol):
    def get(self, decision_id: ReleaseDecisionId) -> ReleaseDecision | None: ...

    def add(self, decision: ReleaseDecision) -> PersistedVersion: ...

    def append_approval(
        self,
        decision_id: ReleaseDecisionId,
        approval: ReleaseApproval,
        expected_version: AggregateVersion,
    ) -> PersistedVersion: ...

    def transition(
        self,
        decision_id: ReleaseDecisionId,
        transition: ReleaseDecision,
        expected_version: AggregateVersion,
    ) -> ReleaseDecision: ...


__all__ = [
    "AiJobRepository",
    "AiTaskDefinitionRepository",
    "EvaluationDatasetRepository",
    "EvaluationResultRepository",
    "EvaluationRunRepository",
    "EvaluationSuiteRepository",
    "JudgeCalibrationRepository",
    "ModelDefinitionRepository",
    "ModelRouteVersionRepository",
    "OutputSchemaVersionRepository",
    "PromptVersionRepository",
    "ReleaseDecisionRepository",
]

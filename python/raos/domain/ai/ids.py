"""Nominal AI persistence identities selected by the ST-0308 mapper matrix."""

from raos.domain.shared.identity import EntityId


class AiAttemptId(EntityId):
    __slots__ = ()


class AiJobId(EntityId):
    __slots__ = ()


class AiTaskDefinitionId(EntityId):
    __slots__ = ()


class EvaluationCaseId(EntityId):
    __slots__ = ()


class EvaluationCaseResultId(EntityId):
    __slots__ = ()


class EvaluationDatasetVersionId(EntityId):
    __slots__ = ()


class EvaluationResultId(EntityId):
    __slots__ = ()


class EvaluationRunId(EntityId):
    __slots__ = ()


class EvaluationSuiteId(EntityId):
    __slots__ = ()


class HumanEvaluationId(EntityId):
    __slots__ = ()


class JudgeCalibrationId(EntityId):
    __slots__ = ()


class ModelDefinitionId(EntityId):
    __slots__ = ()


class ModelRouteVersionId(EntityId):
    __slots__ = ()


class OutputSchemaVersionId(EntityId):
    __slots__ = ()


class PromptVersionId(EntityId):
    __slots__ = ()


class ReleaseApprovalId(EntityId):
    __slots__ = ()


class ReleaseDecisionId(EntityId):
    __slots__ = ()


class UsageCostId(EntityId):
    __slots__ = ()


__all__ = [
    "AiAttemptId",
    "AiJobId",
    "AiTaskDefinitionId",
    "EvaluationCaseId",
    "EvaluationCaseResultId",
    "EvaluationDatasetVersionId",
    "EvaluationResultId",
    "EvaluationRunId",
    "EvaluationSuiteId",
    "HumanEvaluationId",
    "JudgeCalibrationId",
    "ModelDefinitionId",
    "ModelRouteVersionId",
    "OutputSchemaVersionId",
    "PromptVersionId",
    "ReleaseApprovalId",
    "ReleaseDecisionId",
    "UsageCostId",
]

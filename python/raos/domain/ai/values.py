"""Exact immutable JSON wrappers for AI physical jsonb columns."""

from __future__ import annotations

from dataclasses import dataclass

from raos.domain.shared.json_values import FrozenJsonObject


def _validate(value: object) -> None:
    if type(value) is not FrozenJsonObject:
        raise ValueError("INVALID_AI_JSON_VALUE") from None


@dataclass(frozen=True, slots=True, repr=False)
class AiAttemptRequestConfigJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "AiAttemptRequestConfigJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class AiJobRequestConfigJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "AiJobRequestConfigJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class EvaluationCaseMetadataJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "EvaluationCaseMetadataJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class EvaluationCaseResultGraderSummaryJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "EvaluationCaseResultGraderSummaryJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class EvaluationCaseResultZeroToleranceEvidenceJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "EvaluationCaseResultZeroToleranceEvidenceJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class EvaluationDatasetVersionSplitPolicyJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "EvaluationDatasetVersionSplitPolicyJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class EvaluationResultDetailsJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "EvaluationResultDetailsJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class EvaluationSuiteSuiteConfigJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "EvaluationSuiteSuiteConfigJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class HumanEvaluationScoresJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "HumanEvaluationScoresJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ModelDefinitionCapabilitiesJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "ModelDefinitionCapabilitiesJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ModelDefinitionProviderMetadataJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "ModelDefinitionProviderMetadataJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ModelRouteVersionRouteConfigJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "ModelRouteVersionRouteConfigJson(<redacted>)"


__all__ = [
    "AiAttemptRequestConfigJson",
    "AiJobRequestConfigJson",
    "EvaluationCaseMetadataJson",
    "EvaluationCaseResultGraderSummaryJson",
    "EvaluationCaseResultZeroToleranceEvidenceJson",
    "EvaluationDatasetVersionSplitPolicyJson",
    "EvaluationResultDetailsJson",
    "EvaluationSuiteSuiteConfigJson",
    "HumanEvaluationScoresJson",
    "ModelDefinitionCapabilitiesJson",
    "ModelDefinitionProviderMetadataJson",
    "ModelRouteVersionRouteConfigJson",
]

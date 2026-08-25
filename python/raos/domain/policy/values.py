"""Exact immutable JSON wrappers for POLICY physical jsonb columns."""

from __future__ import annotations

from dataclasses import dataclass

from raos.domain.shared.json_values import FrozenJsonObject


def _validate(value: object) -> None:
    if type(value) is not FrozenJsonObject:
        raise ValueError("INVALID_POLICY_JSON_VALUE") from None


@dataclass(frozen=True, slots=True, repr=False)
class FindingEvidenceJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "FindingEvidenceJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class GateDecisionConditionsJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "GateDecisionConditionsJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class QualityScoreComponentsJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "QualityScoreComponentsJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class RuleVersionDefinitionJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "RuleVersionDefinitionJson(<redacted>)"


__all__ = [
    "FindingEvidenceJson",
    "GateDecisionConditionsJson",
    "QualityScoreComponentsJson",
    "RuleVersionDefinitionJson",
]

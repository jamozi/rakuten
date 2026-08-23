"""Exact immutable JSON wrappers for PORTFOLIO physical jsonb columns."""

from __future__ import annotations

from dataclasses import dataclass

from raos.domain.shared.json_values import FrozenJsonObject


@dataclass(frozen=True, slots=True, repr=False)
class _ObjectJsonValue:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        if type(self.value) is not FrozenJsonObject:
            raise ValueError("INVALID_PORTFOLIO_JSON_VALUE") from None

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted>)"


class ActionCandidateRationaleJson(_ObjectJsonValue):
    __slots__ = ()


class CategoryEntryCriteriaJson(_ObjectJsonValue):
    __slots__ = ()


class IntentClusterDecisionRequirementsJson(_ObjectJsonValue):
    __slots__ = ()


class OpportunityAssessmentBusinessComponentsJson(_ObjectJsonValue):
    __slots__ = ()


class OpportunityAssessmentComplianceComponentsJson(_ObjectJsonValue):
    __slots__ = ()


class OpportunityAssessmentEditorialComponentsJson(_ObjectJsonValue):
    __slots__ = ()


class SitePublicSettingsJson(_ObjectJsonValue):
    __slots__ = ()


__all__ = [
    "ActionCandidateRationaleJson",
    "CategoryEntryCriteriaJson",
    "IntentClusterDecisionRequirementsJson",
    "OpportunityAssessmentBusinessComponentsJson",
    "OpportunityAssessmentComplianceComponentsJson",
    "OpportunityAssessmentEditorialComponentsJson",
    "SitePublicSettingsJson",
]

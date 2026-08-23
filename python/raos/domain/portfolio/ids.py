"""Nominal PORTFOLIO persistence identities selected by ST-0308."""

from raos.domain.shared.identity import EntityId


class ActionCandidateId(EntityId):
    __slots__ = ()


class CategoryId(EntityId):
    __slots__ = ()


class IntentClusterId(EntityId):
    __slots__ = ()


class KeywordId(EntityId):
    __slots__ = ()


class KeywordMetricObservationId(EntityId):
    __slots__ = ()


class OpportunityAssessmentId(EntityId):
    __slots__ = ()


class SiteId(EntityId):
    __slots__ = ()


__all__ = [
    "ActionCandidateId",
    "CategoryId",
    "IntentClusterId",
    "KeywordId",
    "KeywordMetricObservationId",
    "OpportunityAssessmentId",
    "SiteId",
]

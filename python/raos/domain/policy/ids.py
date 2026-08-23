"""Nominal POLICY persistence identities selected by the ST-0308 mapper matrix."""

from raos.domain.shared.identity import EntityId


class FindingId(EntityId):
    __slots__ = ()


class GateDecisionId(EntityId):
    __slots__ = ()


class PolicyBundleId(EntityId):
    __slots__ = ()


class QualityCheckRunId(EntityId):
    __slots__ = ()


class QualityScoreId(EntityId):
    __slots__ = ()


class RuleVersionId(EntityId):
    __slots__ = ()


class WaiverId(EntityId):
    __slots__ = ()


__all__ = [
    "FindingId",
    "GateDecisionId",
    "PolicyBundleId",
    "QualityCheckRunId",
    "QualityScoreId",
    "RuleVersionId",
    "WaiverId",
]

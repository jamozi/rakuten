"""Nominal EVIDENCE persistence identities selected by the ST-0308 mapper matrix."""

from raos.domain.shared.identity import EntityId


class ClaimId(EntityId):
    __slots__ = ()


class FactId(EntityId):
    __slots__ = ()


class FirstHandExperienceRecordId(EntityId):
    __slots__ = ()


class SourceId(EntityId):
    __slots__ = ()


class SourcePacketId(EntityId):
    __slots__ = ()


class SourcePacketVersionId(EntityId):
    __slots__ = ()


class SourceSnapshotId(EntityId):
    __slots__ = ()


__all__ = [
    "ClaimId",
    "FactId",
    "FirstHandExperienceRecordId",
    "SourceId",
    "SourcePacketId",
    "SourcePacketVersionId",
    "SourceSnapshotId",
]

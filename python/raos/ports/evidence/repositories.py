"""Exact aggregate-specific EVIDENCE Repository Protocols for ST-0308."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.evidence.aggregates import (
    Claim,
    ClaimEvidenceLink,
    Fact,
    FactDerivation,
    FirstHandExperienceAsset,
    FirstHandExperienceRecord,
    Source,
    SourcePacket,
    SourcePacketVersion,
    SourceSnapshot,
)
from raos.domain.evidence.enums import (
    FirstHandExperienceStatus,
    SourcePacketVersionStatus,
)
from raos.domain.evidence.ids import (
    ClaimId,
    FactId,
    FirstHandExperienceRecordId,
    SourceId,
    SourcePacketId,
    SourcePacketVersionId,
    SourceSnapshotId,
)
from raos.domain.shared.persistence import (
    AggregateVersion,
    PersistedVersion,
)


@runtime_checkable
class SourceRepository(Protocol):
    def get(self, source_id: SourceId) -> Source | None: ...

    def add(self, source: Source) -> PersistedVersion: ...

    def save(
        self,
        source: Source,
        expected_version: AggregateVersion,
    ) -> PersistedVersion: ...


@runtime_checkable
class SourceSnapshotRepository(Protocol):
    def get(self, snapshot_id: SourceSnapshotId) -> SourceSnapshot | None: ...

    def append(
        self,
        source_id: SourceId,
        snapshot: SourceSnapshot,
        expected_source_version: AggregateVersion,
    ) -> PersistedVersion: ...


@runtime_checkable
class FactRepository(Protocol):
    def get(self, fact_id: FactId) -> Fact | None: ...

    def append(
        self,
        fact: Fact,
        derivations: tuple[FactDerivation, ...],
    ) -> None: ...


@runtime_checkable
class SourcePacketRepository(Protocol):
    def get(self, packet_id: SourcePacketId) -> SourcePacket | None: ...

    def add(self, packet: SourcePacket) -> PersistedVersion: ...

    def save(
        self,
        packet: SourcePacket,
        expected_version: AggregateVersion,
    ) -> PersistedVersion: ...

    def append_version(
        self,
        packet_id: SourcePacketId,
        version: SourcePacketVersion,
        expected_version: AggregateVersion,
        expected_latest_version: int | None,
    ) -> PersistedVersion: ...

    def transition_version(
        self,
        version_id: SourcePacketVersionId,
        transition: SourcePacketVersion,
        expected_status: SourcePacketVersionStatus,
    ) -> SourcePacketVersion: ...


@runtime_checkable
class ClaimRepository(Protocol):
    def get(self, claim_id: ClaimId) -> Claim | None: ...

    def append(
        self,
        claim: Claim,
        links: tuple[ClaimEvidenceLink, ...],
    ) -> None: ...


@runtime_checkable
class FirstHandExperienceRepository(Protocol):
    def get(
        self, record_id: FirstHandExperienceRecordId
    ) -> FirstHandExperienceRecord | None: ...

    def add(self, record: FirstHandExperienceRecord) -> None: ...

    def transition(
        self,
        record_id: FirstHandExperienceRecordId,
        transition: FirstHandExperienceRecord,
        expected_status: FirstHandExperienceStatus,
    ) -> FirstHandExperienceRecord: ...

    def append_assets(
        self,
        record_id: FirstHandExperienceRecordId,
        assets: tuple[FirstHandExperienceAsset, ...],
        expected_status: FirstHandExperienceStatus,
    ) -> None: ...


__all__ = [
    "ClaimRepository",
    "FactRepository",
    "FirstHandExperienceRepository",
    "SourcePacketRepository",
    "SourceRepository",
    "SourceSnapshotRepository",
]

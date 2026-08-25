"""Exact aggregate-specific OPS Repository Protocols for ST-0308."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.ops.aggregates import (
    Job,
    ObjectArtifact,
    RuntimeSettingScope,
    RuntimeSettingVersion,
)
from raos.domain.ops.enums import RuntimeSettingVersionStatus
from raos.domain.ops.ids import JobId, ObjectArtifactId, RuntimeSettingVersionId
from raos.domain.shared.persistence import PersistedVersion


@runtime_checkable
class JobRepository(Protocol):
    def get(self, job_id: JobId) -> Job | None: ...

    def add(self, job: Job) -> PersistedVersion: ...


@runtime_checkable
class ObjectArtifactRepository(Protocol):
    def get(self, artifact_id: ObjectArtifactId) -> ObjectArtifact | None: ...

    def add(self, artifact: ObjectArtifact) -> None: ...


@runtime_checkable
class RuntimeSettingRepository(Protocol):
    def get_current(
        self,
        setting_key: str,
        scope: RuntimeSettingScope,
    ) -> RuntimeSettingVersion | None: ...

    def append_version(
        self,
        version: RuntimeSettingVersion,
        expected_latest_version: int | None,
    ) -> PersistedVersion: ...

    def transition(
        self,
        version_id: RuntimeSettingVersionId,
        transition: RuntimeSettingVersion,
        expected_status: RuntimeSettingVersionStatus,
    ) -> RuntimeSettingVersion: ...


__all__ = ["JobRepository", "ObjectArtifactRepository", "RuntimeSettingRepository"]

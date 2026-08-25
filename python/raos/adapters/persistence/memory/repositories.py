"""Deterministic aggregate-specific repositories for the OPS memory slice."""

from __future__ import annotations

from typing import NoReturn

from raos.adapters.persistence.memory.transaction import MemoryTransaction
from raos.domain.iam.ids import PrincipalId
from raos.domain.ops.aggregates import (
    ObjectArtifact,
    RuntimeSettingScope,
    RuntimeSettingVersion,
    RuntimeSettingVersionState,
)
from raos.domain.ops.enums import RuntimeSettingVersionStatus
from raos.domain.ops.ids import ObjectArtifactId, RuntimeSettingVersionId
from raos.domain.shared.persistence import PersistedVersion
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode


def _fail(code: PersistenceErrorCode) -> NoReturn:
    raise PersistenceError(code) from None


class MemoryObjectArtifactRepository:
    __slots__ = ("_transaction",)

    def __init__(self, transaction: MemoryTransaction) -> None:
        self._transaction = transaction

    def get(self, artifact_id: ObjectArtifactId) -> ObjectArtifact | None:
        self._transaction.require_operation()
        if type(artifact_id) is not ObjectArtifactId:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        return self._transaction.state.object_artifacts.get(artifact_id)

    def add(self, artifact: ObjectArtifact) -> None:
        self._transaction.require_operation()
        if type(artifact) is not ObjectArtifact:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        current = self._transaction.state.object_artifacts
        storage_identity = (
            artifact.bucket_name,
            artifact.object_key,
            artifact.object_version,
        )
        if artifact.id in current or any(
            candidate.display_id == artifact.display_id
            or (
                candidate.bucket_name,
                candidate.object_key,
                candidate.object_version,
            )
            == storage_identity
            for candidate in current.values()
        ):
            _fail(PersistenceErrorCode.ALREADY_EXISTS)
        current[artifact.id] = artifact


def _same_series(
    left: RuntimeSettingVersionState,
    right: RuntimeSettingVersionState,
) -> bool:
    return (
        left.setting_key == right.setting_key
        and left.scope_type is right.scope_type
        and left.scope_id == right.scope_id
    )


def _preserved(
    current: RuntimeSettingVersionState,
    replacement: RuntimeSettingVersionState,
) -> bool:
    return (
        current.id == replacement.id
        and current.setting_key == replacement.setting_key
        and current.scope_type is replacement.scope_type
        and current.scope_id == replacement.scope_id
        and current.version_no == replacement.version_no
        and current.setting_class is replacement.setting_class
        and current.value == replacement.value
        and current.value_sha256 == replacement.value_sha256
        and current.created_by_principal_id == replacement.created_by_principal_id
        and current.created_at == replacement.created_at
    )


class MemoryRuntimeSettingRepository:
    __slots__ = ("_transaction",)

    def __init__(self, transaction: MemoryTransaction) -> None:
        self._transaction = transaction

    def get_current(
        self,
        setting_key: str,
        scope: RuntimeSettingScope,
    ) -> RuntimeSettingVersion | None:
        self._transaction.require_operation()
        if type(setting_key) is not str or type(scope) is not RuntimeSettingScope:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        candidates = tuple(
            version
            for version in self._transaction.state.runtime_settings.values()
            if version.state.setting_key == setting_key
            and version.state.scope_type is scope.scope_type
            and version.state.scope_id == scope.scope_id
        )
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda version: (version.state.version_no, version.state.id.value.int),
        )

    def append_version(
        self,
        version: RuntimeSettingVersion,
        expected_latest_version: int | None,
    ) -> PersistedVersion:
        self._transaction.require_operation()
        if type(version) is not RuntimeSettingVersion or (
            expected_latest_version is not None
            and type(expected_latest_version) is not int
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        state = version.state
        current = self._transaction.state.runtime_settings
        series = tuple(
            candidate.state
            for candidate in current.values()
            if _same_series(candidate.state, state)
        )
        latest = max((candidate.version_no for candidate in series), default=None)
        if latest != expected_latest_version:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        required_version = 1 if latest is None else latest + 1
        if state.version_no != required_version:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        if state.id in current or any(
            candidate.version_no == state.version_no for candidate in series
        ):
            _fail(PersistenceErrorCode.ALREADY_EXISTS)
        if state.status is RuntimeSettingVersionStatus.ACTIVE and any(
            candidate.status is RuntimeSettingVersionStatus.ACTIVE
            for candidate in series
        ):
            _fail(PersistenceErrorCode.INTEGRITY_CONFLICT)
        current[state.id] = version
        return PersistedVersion(state.version_no)

    def transition(
        self,
        version_id: RuntimeSettingVersionId,
        transition: RuntimeSettingVersion,
        expected_status: RuntimeSettingVersionStatus,
    ) -> RuntimeSettingVersion:
        self._transaction.require_operation()
        if (
            type(version_id) is not RuntimeSettingVersionId
            or type(transition) is not RuntimeSettingVersion
            or type(expected_status) is not RuntimeSettingVersionStatus
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        current_versions = self._transaction.state.runtime_settings
        current_version = current_versions.get(version_id)
        if current_version is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = current_version.state
        replacement = transition.state
        if current.status is not expected_status:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        if not _preserved(current, replacement):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        edge = (current.status, replacement.status)
        if edge not in {
            (
                RuntimeSettingVersionStatus.DRAFT,
                RuntimeSettingVersionStatus.ACTIVE,
            ),
            (
                RuntimeSettingVersionStatus.DRAFT,
                RuntimeSettingVersionStatus.REJECTED,
            ),
            (
                RuntimeSettingVersionStatus.DRAFT,
                RuntimeSettingVersionStatus.RETIRED,
            ),
            (
                RuntimeSettingVersionStatus.ACTIVE,
                RuntimeSettingVersionStatus.RETIRED,
            ),
        }:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        if current.status is RuntimeSettingVersionStatus.DRAFT:
            if (
                current.approved_by_principal_id is not None
                or current.approval_reason is not None
            ):
                _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
            if replacement.status is RuntimeSettingVersionStatus.ACTIVE:
                actor_id = self._transaction.context.actor.actor_id
                if (
                    actor_id is None
                    or replacement.approved_by_principal_id != PrincipalId(actor_id)
                    or replacement.approval_reason is None
                    or replacement.effective_from is None
                    or replacement.effective_to is not None
                ):
                    _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
                if any(
                    candidate.state.id != current.id
                    and _same_series(candidate.state, current)
                    and candidate.state.status is RuntimeSettingVersionStatus.ACTIVE
                    for candidate in current_versions.values()
                ):
                    _fail(PersistenceErrorCode.INTEGRITY_CONFLICT)
            elif (
                replacement.approved_by_principal_id != current.approved_by_principal_id
                or replacement.approval_reason != current.approval_reason
                or replacement.effective_from != current.effective_from
                or replacement.effective_to != current.effective_to
            ):
                _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        elif (
            replacement.approved_by_principal_id != current.approved_by_principal_id
            or replacement.approval_reason != current.approval_reason
            or replacement.effective_from != current.effective_from
            or replacement.effective_to is None
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        current_versions[version_id] = transition
        return transition


__all__ = ["MemoryObjectArtifactRepository", "MemoryRuntimeSettingRepository"]

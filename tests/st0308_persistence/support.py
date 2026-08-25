"""Deterministic fixture builders for the ST-0308 persistence slice."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
from uuid import UUID

from raos.adapters.persistence.memory import (
    DatabaseIdentityFacts,
    EffectiveRoleVerifier,
    MemoryConnectionPool,
    MemoryEffectiveRoleVerifier,
    MemoryOpsUnitOfWorkFactory,
    MemoryPersistenceStore,
    MemorySessionFactory,
    WorkloadProfile,
)
from raos.adapters.persistence.memory.identity import MemoryCommitMode
from raos.domain.iam.ids import CreatedByPrincipalId, PrincipalId
from raos.domain.ops.aggregates import (
    ObjectArtifact,
    RuntimeSettingVersion,
    RuntimeSettingVersionState,
)
from raos.domain.ops.enums import (
    ObjectArtifactArtifactKind,
    ObjectArtifactEncryptionState,
    RuntimeSettingVersionScopeType,
    RuntimeSettingVersionSettingClass,
    RuntimeSettingVersionStatus,
)
from raos.domain.ops.ids import JobId, ObjectArtifactId, RuntimeSettingVersionId
from raos.domain.ops.values import (
    ObjectArtifactMetadataJson,
    RuntimeSettingVersionValueJson,
)
from raos.domain.shared.events import AggregateVersion
from raos.domain.shared.identity import (
    Actor,
    ActorType,
    ScopeId,
    deterministic_uuid7,
)
from raos.domain.shared.json_values import FrozenJsonObject, canonical_json_bytes
from raos.domain.shared.persistence import AwareUtcDateTime, Sha256Digest
from raos.domain.ops.events import OpsJobRequested
from raos.ports.persistence.context import PersistenceContext
from raos.ports.persistence.audit import AuditIntent, SanitizedAuditDetails


FIXED_TIME = datetime(2026, 8, 24, 3, 0, tzinfo=timezone.utc)
_NAMESPACE = UUID("12345678-1234-4234-8234-123456789abc")


def stable_uuid(label: str) -> UUID:
    return deterministic_uuid7(_NAMESPACE, label.encode("utf-8"))


class DeterministicIds:
    def __init__(self, prefix: str = "generated") -> None:
        self._prefix = prefix
        self._next = 0

    def __call__(self) -> UUID:
        self._next += 1
        return stable_uuid(f"{self._prefix}:{self._next}")


def make_context(*, suffix: str = "default") -> PersistenceContext:
    return PersistenceContext(
        command_id=stable_uuid(f"command:{suffix}"),
        correlation_id=stable_uuid(f"correlation:{suffix}"),
        causation_id=stable_uuid(f"causation:{suffix}"),
        actor=Actor(ActorType.USER, stable_uuid("principal:actor")),
        source="tests.st0308",
        occurred_at=FIXED_TIME,
    )


def make_factory(
    *,
    store: MemoryPersistenceStore | None = None,
    profile: WorkloadProfile = WorkloadProfile.API_COMMAND,
    groups: frozenset[str] | None = None,
    now: datetime = FIXED_TIME,
    commit_mode: MemoryCommitMode = MemoryCommitMode.SUCCESS,
    dangerous: bool = False,
    id_prefix: str = "factory",
    verifier: EffectiveRoleVerifier | None = None,
    id_factory: Callable[[], UUID] | None = None,
) -> tuple[
    MemoryOpsUnitOfWorkFactory,
    MemoryPersistenceStore,
    MemoryConnectionPool,
]:
    persistence_store = MemoryPersistenceStore() if store is None else store
    required_group = (
        "raos_api_rw" if profile is WorkloadProfile.API_COMMAND else "raos_worker_rw"
    )
    facts = DatabaseIdentityFacts(
        login_role="raos_test_login",
        inherited_groups=(frozenset({required_group}) if groups is None else groups),
        is_superuser=dangerous,
    )
    pool = MemoryConnectionPool(facts)
    factory = MemoryOpsUnitOfWorkFactory(
        store=persistence_store,
        pool=pool,
        verifier=MemoryEffectiveRoleVerifier() if verifier is None else verifier,
        session_factory=MemorySessionFactory(commit_mode),
        expected_profile=profile,
        clock=lambda: now,
        id_factory=DeterministicIds(id_prefix) if id_factory is None else id_factory,
    )
    return factory, persistence_store, pool


def make_artifact(
    *,
    suffix: str = "001",
    object_version: str | None = None,
) -> ObjectArtifact:
    return ObjectArtifact(
        id=ObjectArtifactId(stable_uuid(f"artifact:{suffix}")),
        display_id=f"ART-{suffix}",
        artifact_kind=ObjectArtifactArtifactKind.SOURCE_SNAPSHOT,
        storage_provider="s3",
        bucket_name="raos-fixtures",
        object_key=f"snapshots/{suffix}.json",
        object_version=object_version,
        content_type="application/json",
        byte_size=0,
        sha256=Sha256Digest(hashlib.sha256(suffix.encode()).hexdigest()),
        encryption_state=ObjectArtifactEncryptionState.LOCAL_DEV,
        retention_class="test",
        is_immutable=True,
        source_system="tests",
        acquired_at=AwareUtcDateTime(FIXED_TIME),
        created_by_principal_id=CreatedByPrincipalId(stable_uuid("principal:creator")),
        metadata=ObjectArtifactMetadataJson(
            FrozenJsonObject.from_mapping({"fixture": suffix})
        ),
        created_at=AwareUtcDateTime(FIXED_TIME),
    )


def make_runtime_setting(
    *,
    suffix: str = "default",
    version_no: int = 1,
    status: RuntimeSettingVersionStatus = RuntimeSettingVersionStatus.DRAFT,
    scope_type: RuntimeSettingVersionScopeType = RuntimeSettingVersionScopeType.GLOBAL,
    scope_id: ScopeId | None = None,
    approved_by: PrincipalId | None = None,
    approval_reason: str | None = None,
    effective_from: AwareUtcDateTime | None = None,
    effective_to: AwareUtcDateTime | None = None,
) -> RuntimeSettingVersion:
    value = RuntimeSettingVersionValueJson(
        FrozenJsonObject.from_mapping({"enabled": True, "suffix": suffix})
    )
    digest = Sha256Digest(hashlib.sha256(canonical_json_bytes(value.value)).hexdigest())
    return RuntimeSettingVersion(
        RuntimeSettingVersionState(
            id=RuntimeSettingVersionId(stable_uuid(f"runtime:{suffix}:{version_no}")),
            setting_key=f"feature.{suffix}",
            scope_type=scope_type,
            scope_id=scope_id,
            version_no=version_no,
            setting_class=RuntimeSettingVersionSettingClass.FEATURE_FLAG,
            value=value,
            value_sha256=digest,
            status=status,
            effective_from=effective_from,
            effective_to=effective_to,
            created_by_principal_id=PrincipalId(stable_uuid("principal:creator")),
            approved_by_principal_id=approved_by,
            approval_reason=approval_reason,
            created_at=AwareUtcDateTime(FIXED_TIME),
        )
    )


def make_event(*, suffix: str = "one") -> OpsJobRequested:
    return OpsJobRequested(
        event_id=stable_uuid(f"event:{suffix}"),
        aggregate_id=JobId(stable_uuid(f"job:{suffix}")),
        aggregate_version=AggregateVersion(0),
        occurred_at=FIXED_TIME,
        causation_id=stable_uuid(f"event-cause:{suffix}"),
        data=FrozenJsonObject.from_mapping(
            {
                "available_at": FIXED_TIME.isoformat(),
                "job_id": str(stable_uuid(f"job:{suffix}")),
                "job_type": "TEST",
                "queue": "local",
            }
        ),
    )


def make_audit(*, suffix: str = "001") -> AuditIntent:
    return AuditIntent(
        action="ops.reference.create",
        target_type="ops.object_artifact",
        target_id=make_artifact(suffix=suffix).id,
        outcome="SUCCESS",
        reason="fixture",
        sanitized_details=SanitizedAuditDetails(
            FrozenJsonObject.from_mapping({"kind": "test"})
        ),
    )

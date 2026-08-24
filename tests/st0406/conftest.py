"""Synthetic builders for the isolated ST-0406 object-intake suite."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from uuid import UUID

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"

if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.adapters.recorded_object_intake import (  # noqa: E402
    RecordedObjectIntakeAdapter,
    SyntheticChunkReader,
)
from raos.application.ops.object_intake import ObjectIntakeService  # noqa: E402
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.iam.authorization import (  # noqa: E402
    ActionCode,
    AuthorizationDecision,
    AuthorizationDecisionReason,
    AuthorizationGrant,
    AuthorizationTarget,
    CorrelationId,
    DecisionEffect,
    EntitlementRevision,
    PolicyRevision,
    ResourceScope,
    ResourceScopeKind,
    RuleId,
)
from raos.domain.ops.object_intake import (  # noqa: E402
    ArchiveInspectionRecord,
    CsvEncoding,
    CsvInspectionRecord,
    InspectionStatus,
    IntakeDescriptor,
    IntakePolicy,
    IntakePrivacyClass,
    MagicInspectionRecord,
    MalwareInspectionRecord,
    MalwareStatus,
    MediaType,
    ObjectInspectionReport,
    ObjectIntakeKind,
    PrivacyInspectionRecord,
    SafeLeafName,
    Sha256Digest,
)
from raos.adapters.development_oidc import (  # noqa: E402
    DevelopmentOidcAdapter,
    InMemoryAuthenticationRepository,
    SystemEntropySource,
)
from raos.adapters.generated_st0403_authorization_registry import (  # noqa: E402
    CANONICAL_AUTHORIZATION_REGISTRY,
)
from raos.adapters.recorded_authorization import (  # noqa: E402
    RecordedSqliteAuthorizationRepository,
    recorded_authorization_policy_snapshot,
)
from raos.adapters.recorded_object_intake_runtime_v2 import (  # noqa: E402
    DeterministicContentInspectorV2,
    RecordedMalwareScannerV2,
    RecordedPrivacyClassifierV2,
    RecordedSqliteObjectIntakeRepositoryV2,
)
from raos.application.iam.authentication import AuthenticationService  # noqa: E402
from raos.application.iam.authorization import DurableAuthorizationService  # noqa: E402
from raos.application.ops.object_intake_runtime_v2 import (  # noqa: E402
    SecureObjectIntakeRuntimeV2,
)
from raos.domain.iam.authentication import (  # noqa: E402
    Issuer,
    PrincipalIdentity as AuthenticatedPrincipalIdentity,
    Session,
    SessionId,
    Subject,
)
from raos.domain.iam.authorization import (  # noqa: E402
    AuthorizationCommandId,
    AuthorizationCommandResult,
    AuthorizationEvaluationCommand,
    AuthorizationRule,
    BusinessRole,
    EntitlementSnapshot,
    MatrixAction,
    OperationId,
    PermissionScope,
    PrincipalIdentity,
    ResourceState,
    ScopedBusinessRole,
    ScopedPermission,
)
from raos.domain.ops.object_intake_runtime_v2 import (  # noqa: E402
    DurableIntakeDescriptorV2,
    IntakeRuntimeMode,
    IntakeRuntimePolicyV2,
    MalwareScanReceiptV2,
    PrivacyClassificationReceiptV2,
    RecordedMalwareVerdict,
    RecordedPrivacyVerdict,
)
from raos.ports.object_intake_runtime_v2 import MalwareScannerV2  # noqa: E402


SITE_A = UUID("11111111-1111-4111-8111-111111111111")
SITE_B = UUID("22222222-2222-4222-8222-222222222222")
INTAKE_A = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
CONTENT = b"name,value\nsafe,1\n"
DIGEST = Sha256Digest(hashlib.sha256(CONTENT).hexdigest())
CSV_MEDIA_TYPE = MediaType("text/csv")


def authorization_grant(
    *,
    site_id: UUID = SITE_A,
    action: str = "artifact:upload",
) -> AuthorizationGrant:
    decision = AuthorizationDecision(
        correlation_id=CorrelationId("TEST_ONLY:ST0406"),
        effect=DecisionEffect.ALLOW,
        reason=AuthorizationDecisionReason.RULE_MATCH,
        policy_revision=PolicyRevision("TEST_ONLY:POLICY_V1"),
        policy_fingerprint="1" * 64,
        entitlement_revision=EntitlementRevision("TEST_ONLY:ENTITLEMENTS_V1"),
        matched_rule_id=RuleId("TEST_ONLY:ARTIFACT_UPLOAD"),
        action=ActionCode(action),
        target=AuthorizationTarget(
            scope=ResourceScope(
                kind=ResourceScopeKind.SITE,
                site_id=site_id,
                resource_id=site_id,
            )
        ),
    )
    return AuthorizationGrant(recorded_decision=decision)


def intake_descriptor(
    *,
    intake_id: UUID = INTAKE_A,
    site_id: UUID = SITE_A,
    declared_size: int = len(CONTENT),
    declared_sha256: Sha256Digest = DIGEST,
) -> IntakeDescriptor:
    return IntakeDescriptor(
        intake_id=intake_id,
        site_id=site_id,
        kind=ObjectIntakeKind.REVENUE_REPORT,
        leaf_name=SafeLeafName("synthetic.csv"),
        media_type=CSV_MEDIA_TYPE,
        declared_size=declared_size,
        declared_sha256=declared_sha256,
        privacy_class=IntakePrivacyClass.SYNTHETIC,
    )


def intake_policy() -> IntakePolicy:
    return IntakePolicy(
        environment="TEST_ONLY",
        max_object_bytes=4_096,
        max_chunk_bytes=8,
        max_chunk_count=512,
        max_archive_entries=16,
        max_archive_uncompressed_bytes=4_096,
        max_archive_ratio=10,
        max_csv_rows=32,
        max_csv_columns=8,
        max_csv_cell_bytes=128,
        allowed_media_types=(CSV_MEDIA_TYPE,),
        allowed_privacy_classes=(IntakePrivacyClass.SYNTHETIC,),
    )


def service_for(
    adapter: RecordedObjectIntakeAdapter,
    *,
    policy: IntakePolicy | None = None,
) -> ObjectIntakeService:
    return ObjectIntakeService(
        policy=intake_policy() if policy is None else policy,
        quarantine=adapter,
        inspector=adapter,
        malware=adapter,
        duplicate_registry=adapter,
    )


def clean_inspection() -> ObjectInspectionReport:
    return ObjectInspectionReport(
        magic=MagicInspectionRecord(
            status=InspectionStatus.SAFE,
            declared_media_type=CSV_MEDIA_TYPE,
            detected_media_type=CSV_MEDIA_TYPE,
            extension_consistent=True,
        ),
        archive=ArchiveInspectionRecord(
            status=InspectionStatus.NOT_APPLICABLE,
            entry_count=0,
            uncompressed_bytes=0,
        ),
        csv=CsvInspectionRecord(
            status=InspectionStatus.SAFE,
            encoding=CsvEncoding.UTF_8,
            row_count=2,
            column_count=2,
            max_cell_bytes=5,
            formula_prefix_detected=False,
        ),
        privacy=PrivacyInspectionRecord(
            status=InspectionStatus.SAFE,
            privacy_class=IntakePrivacyClass.SYNTHETIC,
        ),
    )


def make_recorded_adapter(
    *,
    inspection: ObjectInspectionReport | None = None,
    malware: MalwareInspectionRecord | None = None,
    digest: Sha256Digest = DIGEST,
    event_capacity: int = 32,
    byte_capacity: int = 4_096,
    duplicate_capacity: int = 8,
) -> RecordedObjectIntakeAdapter:
    return RecordedObjectIntakeAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_capacity=event_capacity,
        byte_capacity=byte_capacity,
        script_capacity=8,
        duplicate_capacity=duplicate_capacity,
        inspection_scripts=(
            (digest, clean_inspection() if inspection is None else inspection),
        ),
        malware_scripts=(
            (
                digest,
                MalwareInspectionRecord(status=MalwareStatus.CLEAN)
                if malware is None
                else malware,
            ),
        ),
    )


@pytest.fixture
def recorded_adapter() -> RecordedObjectIntakeAdapter:
    return make_recorded_adapter()


@pytest.fixture
def intake_service(
    recorded_adapter: RecordedObjectIntakeAdapter,
) -> ObjectIntakeService:
    return service_for(recorded_adapter)


def synthetic_source(content: bytes = CONTENT) -> SyntheticChunkReader:
    return SyntheticChunkReader(
        environment=RuntimeEnvironment.ENV_DEV,
        byte_capacity=4_096,
        content=content,
    )


V2_NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
V2_RESOURCE_ID = UUID("33333333-3333-4333-8333-333333333333")
V2_POLICY_REVISION = PolicyRevision("RECORDED:ST0403:ST0406:POLICY:V2")
V2_ENTITLEMENT_REVISION = EntitlementRevision("RECORDED:ST0403:ST0406:ENTITLEMENT:V2")


def v2_session(
    *,
    idle_expires_at: datetime = V2_NOW + timedelta(hours=1),
    absolute_expires_at: datetime = V2_NOW + timedelta(hours=2),
    revoked_at: datetime | None = None,
) -> Session:
    principal = AuthenticatedPrincipalIdentity(
        issuer=Issuer("https://st0406.test.invalid"),
        subject=Subject("RECORDED:ST0406:EDITOR"),
        display_name="ST-0406 recorded editor",
    )
    return Session(
        session_id=SessionId.from_bytes(hashlib.sha256(b"ST0406-SESSION-V2").digest()),
        principal=principal,
        created_at=V2_NOW - timedelta(minutes=5),
        last_seen_at=V2_NOW - timedelta(seconds=1),
        idle_expires_at=idle_expires_at,
        absolute_expires_at=absolute_expires_at,
        revoked_at=revoked_at,
    )


def v2_authentication_service(active_session: Session) -> AuthenticationService:
    repository = InMemoryAuthenticationRepository(
        environment=RuntimeEnvironment.ENV_DEV
    )
    repository.create_session(active_session)
    return AuthenticationService(
        provider=DevelopmentOidcAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            principal=active_session.principal,
        ),
        repository=repository,
        entropy=SystemEntropySource(),
    )


def v2_authorization_target(
    *,
    site_id: UUID = SITE_A,
    resource_id: UUID = V2_RESOURCE_ID,
    state: str = "DRAFT",
) -> AuthorizationTarget:
    return AuthorizationTarget(
        scope=ResourceScope(
            kind=ResourceScopeKind.ARTICLE_VERSION,
            site_id=site_id,
            resource_id=resource_id,
        ),
        state=ResourceState(state),
    )


def v2_authorization_principal(active_session: Session) -> PrincipalIdentity:
    return PrincipalIdentity.admin_user(
        issuer=active_session.principal.issuer,
        subject=active_session.principal.subject,
    )


def v2_authorization_rule() -> AuthorizationRule:
    return AuthorizationRule(
        rule_id=RuleId("RECORDED:ST0406:ED011:EDITOR"),
        role=BusinessRole.EDITOR,
        permission_scope=PermissionScope("editorial:version:write"),
        action=ActionCode(MatrixAction.EDIT_ARTICLE_DRAFT.value),
        resource_kind=ResourceScopeKind.ARTICLE_VERSION,
        resource_state=ResourceState("DRAFT"),
    )


def v2_entitlements(active_session: Session) -> EntitlementSnapshot:
    target = v2_authorization_target()
    return EntitlementSnapshot(
        revision=V2_ENTITLEMENT_REVISION,
        principal=v2_authorization_principal(active_session),
        roles=(ScopedBusinessRole(role=BusinessRole.EDITOR, scope=target.scope),),
        permission_scopes=(
            ScopedPermission(
                permission_scope=PermissionScope("editorial:version:write"),
                scope=target.scope,
            ),
        ),
    )


def v2_authorization_command(
    *,
    label: str = "ALLOW-1",
    target: AuthorizationTarget | None = None,
    operation_id: str = "ED-011",
) -> AuthorizationEvaluationCommand:
    return AuthorizationEvaluationCommand(
        command_id=AuthorizationCommandId(f"RECORDED:ST0406:AUTH:{label}"),
        operation_id=OperationId(operation_id),
        target=v2_authorization_target() if target is None else target,
        correlation_id=CorrelationId(f"RECORDED:ST0406:CORRELATION:{label}"),
        expected_policy_revision=V2_POLICY_REVISION,
        expected_entitlement_revision=V2_ENTITLEMENT_REVISION,
        observed_at=V2_NOW,
    )


def v2_authorization_runtime(
    root: Path,
    *,
    active_session: Session | None = None,
    command: AuthorizationEvaluationCommand | None = None,
    install_rule: bool = True,
) -> tuple[
    DurableAuthorizationService,
    Session,
    AuthorizationEvaluationCommand,
    AuthorizationCommandResult,
    RecordedSqliteAuthorizationRepository,
]:
    exact_session = v2_session() if active_session is None else active_session
    auth_root = root / "authorization"
    auth_root.mkdir(mode=0o700)
    repository = RecordedSqliteAuthorizationRepository(
        environment=RuntimeEnvironment.ENV_DEV,
        private_root=auth_root,
    )
    if install_rule:
        repository.install_policy(
            expected_revision="TEST_ONLY:DISABLED",
            snapshot=recorded_authorization_policy_snapshot(
                revision=V2_POLICY_REVISION,
                rules=(v2_authorization_rule(),),
            ),
        )
    repository.install_entitlements(
        principal=v2_authorization_principal(exact_session),
        expected_revision=None,
        snapshot=v2_entitlements(exact_session),
    )
    service = DurableAuthorizationService(
        session_service=v2_authentication_service(exact_session),
        repository=repository,
        registry=CANONICAL_AUTHORIZATION_REGISTRY,
        step_up_consumer=None,
    )
    exact_command = v2_authorization_command() if command is None else command
    result = service.evaluate_admin(
        session_id=exact_session.session_id,
        command=exact_command,
    )
    return service, exact_session, exact_command, result, repository


def v2_descriptor(
    *,
    content: bytes = CONTENT,
    intake_id: UUID = INTAKE_A,
    site_id: UUID = SITE_A,
    resource_id: UUID = V2_RESOURCE_ID,
    kind: ObjectIntakeKind = ObjectIntakeKind.SOURCE_DOCUMENT,
    leaf_name: str = "synthetic.csv",
    media_type: str = "text/csv",
    privacy_class: IntakePrivacyClass = IntakePrivacyClass.SYNTHETIC,
) -> DurableIntakeDescriptorV2:
    return DurableIntakeDescriptorV2(
        descriptor=IntakeDescriptor(
            intake_id=intake_id,
            site_id=site_id,
            kind=kind,
            leaf_name=SafeLeafName(leaf_name),
            media_type=MediaType(media_type),
            declared_size=len(content),
            declared_sha256=Sha256Digest(hashlib.sha256(content).hexdigest()),
            privacy_class=privacy_class,
        ),
        authorization_resource_id=resource_id,
    )


def v2_policy(
    *, allowed_media_types: tuple[str, ...] = ("text/csv",)
) -> IntakeRuntimePolicyV2:
    return IntakeRuntimePolicyV2(
        mode=IntakeRuntimeMode.RECORDED_LOCAL,
        max_object_bytes=16_384,
        max_chunk_bytes=8,
        max_chunk_count=2_048,
        max_archive_entries=16,
        max_archive_uncompressed_bytes=32_768,
        max_archive_ratio=100,
        max_archive_nesting=1,
        max_csv_rows=32,
        max_csv_columns=8,
        max_csv_cell_bytes=128,
        allowed_media_types=allowed_media_types,
        allowed_privacy_classes=(IntakePrivacyClass.SYNTHETIC,),
    )


def v2_intake_runtime(
    root: Path,
    *,
    authorization_service: DurableAuthorizationService,
    content: bytes = CONTENT,
    policy: IntakeRuntimePolicyV2 | None = None,
    malware_scanner: MalwareScannerV2 | None = None,
    repository: RecordedSqliteObjectIntakeRepositoryV2 | None = None,
) -> tuple[SecureObjectIntakeRuntimeV2, RecordedSqliteObjectIntakeRepositoryV2]:
    descriptor = v2_descriptor(content=content)
    digest = descriptor.descriptor.declared_sha256
    intake_repository = repository
    if intake_repository is None:
        intake_repository = RecordedSqliteObjectIntakeRepositoryV2(
            environment=RuntimeEnvironment.ENV_DEV,
            private_root=root / "intake",
        )
    scanner = (
        RecordedMalwareScannerV2(
            (
                (
                    digest,
                    MalwareScanReceiptV2(
                        verdict=RecordedMalwareVerdict.CLEAN,
                        engine_revision="RECORDED-V2",
                    ),
                ),
            )
        )
        if malware_scanner is None
        else malware_scanner
    )
    runtime = SecureObjectIntakeRuntimeV2(
        policy=v2_policy() if policy is None else policy,
        authorization_service=authorization_service,
        repository=intake_repository,
        inspector=DeterministicContentInspectorV2(),
        privacy_classifier=RecordedPrivacyClassifierV2(
            (
                (
                    digest,
                    PrivacyClassificationReceiptV2(
                        verdict=RecordedPrivacyVerdict.MATCH,
                        classified_as=IntakePrivacyClass.SYNTHETIC,
                        classifier_revision="RECORDED-V2",
                    ),
                ),
            )
        ),
        malware_scanner=malware_scanner if malware_scanner is not None else scanner,
    )
    return runtime, intake_repository


def v2_source(content: bytes = CONTENT) -> SyntheticChunkReader:
    return SyntheticChunkReader(
        environment=RuntimeEnvironment.ENV_DEV,
        byte_capacity=max(len(content), 1),
        content=content,
    )

"""Synthetic builders for the isolated ST-0406 object-intake suite."""

from __future__ import annotations

import hashlib
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

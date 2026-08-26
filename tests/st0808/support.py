"""Synthetic exact predecessor builders for the isolated ST-0808 suite."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from uuid import UUID


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.adapters.recorded_media_asset import (  # noqa: E402
    RecordedMediaAssetStep,
    RecordedMediaAssetValidator,
)
from raos.application.editorial.media_asset import (  # noqa: E402
    MediaAssetValidationService,
)
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.editorial.article_lifecycle import (  # noqa: E402
    ArticleVersionState,
    BodySha256,
    SourcePacketVerification,
    VersionDisplayId,
    VersionSnapshot,
)
from raos.domain.editorial.article_plan import ArticlePlanType  # noqa: E402
from raos.domain.editorial.content_ast import load_content_ast  # noqa: E402
from raos.domain.editorial.media_asset import (  # noqa: E402
    MediaAssetMode,
    MediaAssetVisibility,
    MediaValidationCommand,
    RecordedMediaValidationObservation,
    RecordedRightsDisposition,
)
from raos.domain.ops.object_intake import (  # noqa: E402
    ArchiveInspectionRecord,
    CsvInspectionRecord,
    DuplicateInspectionRecord,
    DuplicateStatus,
    InspectionStatus,
    IntakeDescriptor,
    IntakeOutcome,
    IntakePrivacyClass,
    MagicInspectionRecord,
    MalwareInspectionRecord,
    MalwareStatus,
    MediaType,
    ObjectInspectionReport,
    ObjectIntakeKind,
    ObjectIntakeResult,
    PrivacyInspectionRecord,
    QuarantineDisposition,
    QuarantineRecord,
    QuarantineStatus,
    SafeLeafName,
    Sha256Digest,
)
from raos.domain.portfolio.workflow import (  # noqa: E402
    EntityVersion,
    StrongEtag,
    UtcTimestamp,
)


SITE_ID = UUID("018f3e90-7b00-7000-8000-000000000801")
INTAKE_ID = UUID("018f3e90-7b00-7000-8000-000000000802")
QUARANTINE_ID = UUID("018f3e90-7b00-7000-8000-000000000803")
ARTICLE_ID = UUID("018f3e90-7b00-7000-8000-000000000804")
VERSION_ID = UUID("018f3e90-7b00-7000-8000-000000000805")
SOURCE_PACKET_VERSION_ID = UUID("018f3e90-7b00-7000-8000-000000000806")
ASSET_ID = UUID("018f3e90-7b00-7000-8000-000000000807")
NOW = UtcTimestamp(datetime(2026, 8, 10, 6, 0, tzinfo=timezone.utc))
SYNTHETIC_MEDIA = b"synthetic-media-fixture"
MEDIA_DIGEST = Sha256Digest(hashlib.sha256(SYNTHETIC_MEDIA).hexdigest())


def intake_result(
    *, kind: ObjectIntakeKind = ObjectIntakeKind.MEDIA_ASSET
) -> ObjectIntakeResult:
    media_type = MediaType("image/png")
    descriptor = IntakeDescriptor(
        intake_id=INTAKE_ID,
        site_id=SITE_ID,
        kind=kind,
        leaf_name=SafeLeafName("synthetic.png"),
        media_type=media_type,
        declared_size=len(SYNTHETIC_MEDIA),
        declared_sha256=MEDIA_DIGEST,
        privacy_class=IntakePrivacyClass.SYNTHETIC,
    )
    quarantine = QuarantineRecord(
        intake_id=INTAKE_ID,
        quarantine_id=QUARANTINE_ID,
        status=QuarantineStatus.DISPOSITION_RECORDED,
        received_bytes=len(SYNTHETIC_MEDIA),
        chunk_count=1,
        sealed_sha256=MEDIA_DIGEST,
        disposition=QuarantineDisposition.CLEAN_QUARANTINED,
    )
    inspection = ObjectInspectionReport(
        magic=MagicInspectionRecord(
            status=InspectionStatus.SAFE,
            declared_media_type=media_type,
            detected_media_type=media_type,
            extension_consistent=True,
        ),
        archive=ArchiveInspectionRecord(
            status=InspectionStatus.NOT_APPLICABLE,
            entry_count=0,
            uncompressed_bytes=0,
        ),
        csv=CsvInspectionRecord(
            status=InspectionStatus.NOT_APPLICABLE,
            encoding=None,
            row_count=0,
            column_count=0,
            max_cell_bytes=0,
            formula_prefix_detected=False,
        ),
        privacy=PrivacyInspectionRecord(
            status=InspectionStatus.SAFE,
            privacy_class=IntakePrivacyClass.SYNTHETIC,
        ),
    )
    return ObjectIntakeResult(
        descriptor=descriptor,
        quarantine=quarantine,
        inspection=inspection,
        malware=MalwareInspectionRecord(status=MalwareStatus.CLEAN),
        duplicate=DuplicateInspectionRecord(
            status=DuplicateStatus.NEW,
            existing_intake_id=None,
        ),
        outcome=IntakeOutcome.CLEAN_QUARANTINED,
    )


def version_snapshot() -> VersionSnapshot:
    fixture = (
        REPOSITORY_ROOT
        / "contracts/raos-v0.4/contracts/content/fixtures/valid/selection_guide.json"
    )
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    payload["article_id"] = str(ARTICLE_ID)
    payload["article_version_id"] = str(VERSION_ID)
    payload["title"] = "Synthetic media validation article"
    payload["source_packet_version_ref"] = str(SOURCE_PACKET_VERSION_ID)
    content_ast = load_content_ast(json.dumps(payload, ensure_ascii=False))
    return VersionSnapshot(
        version_id=VERSION_ID,
        display_id=VersionDisplayId("ARV-TEST-0808"),
        article_id=ARTICLE_ID,
        version_no=1,
        article_type=ArticlePlanType.SELECTION_GUIDE,
        title="Synthetic media validation article",
        source_packet_version_id=SOURCE_PACKET_VERSION_ID,
        source_packet_verification=SourcePacketVerification.NOT_VERIFIED,
        based_on_version_id=None,
        content_ast=content_ast,
        body_sha256=BodySha256.of(content_ast),
        state=ArticleVersionState.DRAFT,
        submitted_at=None,
        reviewed_at=None,
        approved_at=None,
        published_at=None,
        version=EntityVersion(0),
        etag=StrongEtag('"test-only-media-version-v0"'),
        created_at=NOW,
        updated_at=NOW,
    )


def command(
    rights: RecordedRightsDisposition | None = (
        RecordedRightsDisposition.ADMIN_REFERENCE_ELIGIBLE
    ),
    *,
    intake: ObjectIntakeResult | None = None,
) -> MediaValidationCommand:
    return MediaValidationCommand(
        mode=MediaAssetMode.RECORDED_TEST_ONLY,
        intake_result=intake_result() if intake is None else intake,
        version_snapshot=version_snapshot(),
        rights_disposition=rights,
    )


def visibility_for(
    rights: RecordedRightsDisposition | None,
) -> MediaAssetVisibility:
    if rights in {None, RecordedRightsDisposition.UNKNOWN}:
        return MediaAssetVisibility.HIDDEN_UNKNOWN_RIGHTS
    if rights in {
        RecordedRightsDisposition.FORBIDDEN,
        RecordedRightsDisposition.EXCEPTION_ONLY,
    }:
        return MediaAssetVisibility.HIDDEN_POLICY
    return MediaAssetVisibility.ADMIN_ONLY_REFERENCE


def observation(
    request: MediaValidationCommand,
    *,
    rights: RecordedRightsDisposition | None = None,
    visibility: MediaAssetVisibility | None = None,
) -> RecordedMediaValidationObservation:
    effective_rights = request.rights_disposition if rights is None else rights
    effective_visibility = (
        visibility_for(effective_rights) if visibility is None else visibility
    )
    return RecordedMediaValidationObservation(
        candidate_fingerprint=request.request.candidate.fingerprint,
        rights_disposition=effective_rights,
        visibility=effective_visibility,
        asset_id=(
            ASSET_ID
            if effective_visibility is MediaAssetVisibility.ADMIN_ONLY_REFERENCE
            else None
        ),
    )


def validator_for(
    request: MediaValidationCommand,
    *,
    recorded: RecordedMediaValidationObservation | None = None,
) -> RecordedMediaAssetValidator:
    return RecordedMediaAssetValidator(
        environment=RuntimeEnvironment.ENV_DEV,
        mode=MediaAssetMode.RECORDED_TEST_ONLY,
        script_capacity=8,
        scripts=(
            RecordedMediaAssetStep(
                command=request,
                observation=observation(request) if recorded is None else recorded,
            ),
        ),
    )


def service_for(validator: object) -> MediaAssetValidationService:
    return MediaAssetValidationService(
        environment=RuntimeEnvironment.ENV_DEV,
        mode=MediaAssetMode.RECORDED_TEST_ONLY,
        validator=validator,  # type: ignore[arg-type]
    )

"""Recorded-synthetic adapter for the ST-0903 publication snapshot candidate.

The adapter composes only committed local fixtures.  It validates ST-0902's
recorded final approval, ST-0807's route-only/noindex SEO render, and ST-0808's
admin-only media-reference seam before exposing an immutable in-memory bundle.
It has no persistence or external transport capability.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from threading import RLock
from typing import Final, NoReturn, SupportsIndex, cast, final
from uuid import RFC_4122, UUID

from raos.adapters.recorded_final_approval import (
    load_recorded_final_approval_fixture,
)
from raos.adapters.recorded_media_asset import (
    RecordedMediaAssetStep,
    RecordedMediaAssetValidator,
)
from raos.adapters.recorded_policy_engine import load_recorded_policy_fixture
from raos.application.editorial.media_asset import MediaAssetValidationService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.editorial.article_lifecycle import VersionSnapshot
from raos.domain.editorial.content_ast import dump_content_ast_json
from raos.domain.editorial.media_asset import (
    MediaAssetMode,
    MediaAssetVisibility,
    MediaValidationCommand,
    RecordedMediaValidationObservation,
    RecordedRightsDisposition,
)
from raos.domain.ops.object_intake import (
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
    Sha256Digest as IntakeSha256Digest,
)
from raos.domain.publishing.publication_snapshot_v2 import (
    PROFILE,
    MediaSnapshotBindingV2,
    PublicationSnapshotBuildRequestV2,
    PublicationSnapshotFailure,
    PublicationSnapshotFailureCode,
    PublicationSnapshotInputBundleV2,
    PublicationSnapshotResultV2,
    SeoSnapshotBindingV2,
    build_publication_snapshot_v2,
    canonical_json_bytes,
    fail_publication_snapshot,
    parse_canonical_object,
)
from raos.domain.shared.persistence import Sha256Digest


_MAX_FIXTURE_BYTES: Final = 8 * 1024 * 1024
_MAX_STEPS: Final = 128
_SEED_KEYS: Final = frozenset(
    {
        "article_id",
        "article_version_id",
        "created_at",
        "disclosure_policy_version_ref",
        "idempotency_key",
        "media",
        "methodology_version_ref",
        "policy_bundle_sha256",
        "policy_bundle_version_ref",
        "publication_candidate_id",
        "publication_content_manifest_id",
        "publication_id",
        "publication_version",
        "quality_result_id",
        "renderer_version",
        "snapshot_artifact_id",
    }
)
_MEDIA_KEYS: Final = frozenset(
    {
        "asset_id",
        "byte_size",
        "content_sha256",
        "intake_id",
        "leaf_name",
        "media_type",
        "quarantine_id",
    }
)
_SOURCE_KEYS: Final = frozenset(
    {
        "final_approval_fixture_sha256",
        "policy_fixture_sha256",
        "review_fixture_sha256",
        "seo_fixture_sha256",
    }
)
_AUTHORITY: Final[dict[str, object]] = {
    "browser": "NOT_EXECUTED",
    "credential": False,
    "database_write": False,
    "event_emit": False,
    "external_write": False,
    "formal_tst_014": "NOT_EXECUTED",
    "formal_tst_021": "NOT_EXECUTED",
    "live": "NOT_EXECUTED",
    "media_upload": False,
    "persistence": False,
    "production": "NOT_EXECUTED",
    "production_authorized": False,
    "public_projection_authorized": False,
    "publication": "NOT_EXECUTED",
    "publication_authorized": False,
    "release": "NOT_EXECUTED",
    "release_authorized": False,
    "staging": "NOT_EXECUTED",
}


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-st0903-adapter>)"

    def __str__(self) -> str:
        return "<redacted-st0903-adapter>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded publication snapshot serialization is forbidden")


def _mapping(value: object, keys: frozenset[str]) -> Mapping[str, object]:
    if type(value) is not dict:
        fail_publication_snapshot(PublicationSnapshotFailureCode.FIXTURE_INVALID)
    result = cast(dict[str, object], value)
    if frozenset(result) != keys:
        fail_publication_snapshot(PublicationSnapshotFailureCode.FIXTURE_INVALID)
    return result


def _text(value: object, *, maximum: int = 512) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        fail_publication_snapshot(PublicationSnapshotFailureCode.FIXTURE_INVALID)
    return value


def _integer(value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        fail_publication_snapshot(PublicationSnapshotFailureCode.FIXTURE_INVALID)
    return value


def _uuid7(value: object) -> UUID:
    try:
        text = _text(value, maximum=36)
        result = UUID(text)
    except PublicationSnapshotFailure:
        raise
    except Exception:
        fail_publication_snapshot(PublicationSnapshotFailureCode.FIXTURE_INVALID)
    if result.version != 7 or result.variant != RFC_4122 or str(result) != text:
        fail_publication_snapshot(PublicationSnapshotFailureCode.FIXTURE_INVALID)
    return result


def _sha_text(value: object) -> str:
    text = _text(value, maximum=64)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        fail_publication_snapshot(PublicationSnapshotFailureCode.FIXTURE_INVALID)
    return text


def _instant(value: object) -> datetime:
    text = _text(value, maximum=32)
    if not text.endswith("Z"):
        fail_publication_snapshot(PublicationSnapshotFailureCode.FIXTURE_INVALID)
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except Exception:
        fail_publication_snapshot(PublicationSnapshotFailureCode.FIXTURE_INVALID)
    if (
        parsed.tzinfo is not timezone.utc
        or parsed.fold
        or parsed.microsecond != 0
        or parsed.isoformat(timespec="seconds").replace("+00:00", "Z") != text
    ):
        fail_publication_snapshot(PublicationSnapshotFailureCode.FIXTURE_INVALID)
    return parsed


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _media_binding(
    *,
    seed: Mapping[str, object],
    site_id: UUID,
    version_snapshot: VersionSnapshot,
) -> MediaSnapshotBindingV2:
    media = _mapping(seed["media"], _MEDIA_KEYS)
    digest_text = _sha_text(media["content_sha256"])
    digest = IntakeSha256Digest(digest_text)
    byte_size = _integer(media["byte_size"], minimum=1, maximum=(1 << 53) - 1)
    media_type = MediaType(_text(media["media_type"], maximum=127))
    intake_id = _uuid7(media["intake_id"])
    quarantine_id = _uuid7(media["quarantine_id"])
    descriptor = IntakeDescriptor(
        intake_id=intake_id,
        site_id=site_id,
        kind=ObjectIntakeKind.MEDIA_ASSET,
        leaf_name=SafeLeafName(_text(media["leaf_name"], maximum=128)),
        media_type=media_type,
        declared_size=byte_size,
        declared_sha256=digest,
        privacy_class=IntakePrivacyClass.SYNTHETIC,
    )
    quarantine = QuarantineRecord(
        intake_id=intake_id,
        quarantine_id=quarantine_id,
        status=QuarantineStatus.DISPOSITION_RECORDED,
        received_bytes=byte_size,
        chunk_count=1,
        sealed_sha256=digest,
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
    intake = ObjectIntakeResult(
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
    command = MediaValidationCommand(
        mode=MediaAssetMode.RECORDED_TEST_ONLY,
        intake_result=intake,
        version_snapshot=version_snapshot,
        rights_disposition=RecordedRightsDisposition.ADMIN_REFERENCE_ELIGIBLE,
    )
    asset_id = _uuid7(media["asset_id"])
    observation = RecordedMediaValidationObservation(
        candidate_fingerprint=command.request.candidate.fingerprint,
        rights_disposition=RecordedRightsDisposition.ADMIN_REFERENCE_ELIGIBLE,
        visibility=MediaAssetVisibility.ADMIN_ONLY_REFERENCE,
        asset_id=asset_id,
    )
    validator = RecordedMediaAssetValidator(
        environment=RuntimeEnvironment.CI,
        mode=MediaAssetMode.RECORDED_TEST_ONLY,
        script_capacity=1,
        scripts=(RecordedMediaAssetStep(command=command, observation=observation),),
    )
    result = MediaAssetValidationService(
        environment=RuntimeEnvironment.CI,
        mode=MediaAssetMode.RECORDED_TEST_ONLY,
        validator=validator,
    ).validate(command)
    if (
        result.reference is None
        or result.reference.asset_id != asset_id
        or result.visibility is not MediaAssetVisibility.ADMIN_ONLY_REFERENCE
        or result.public_rendering is not False
        or result.renderer_input is not None
        or result.approval is not None
        or result.publication is not None
    ):
        fail_publication_snapshot(PublicationSnapshotFailureCode.MEDIA_BINDING_INVALID)
    return MediaSnapshotBindingV2(
        article_version_id=result.version_snapshot.version_id,
        asset_id=asset_id,
        asset_content_sha256=Sha256Digest(digest_text),
        candidate_fingerprint=Sha256Digest(result.candidate.fingerprint),
        byte_size=byte_size,
    )


def _seo_binding(
    *,
    payload: bytes,
    article_version_id: UUID,
    visible_content_sha256: Sha256Digest,
) -> SeoSnapshotBindingV2:
    document = parse_canonical_object(payload)
    if (
        document.get("schema_version") != 2
        or document.get("story_id") != "ST-0807"
        or document.get("local_status") != "LOCAL_IMPLEMENTATION_COMPLETE"
        or document.get("classification") != "RECORDED_SYNTHETIC_ROUTE_ONLY_PREVIEW"
        or document.get("jsonld_sha256") is None
        or type(document.get("render")) is not dict
    ):
        fail_publication_snapshot(PublicationSnapshotFailureCode.SEO_BINDING_INVALID)
    authority = document.get("authority")
    if type(authority) is not dict or any(
        value is not False for value in cast(dict[str, object], authority).values()
    ):
        fail_publication_snapshot(PublicationSnapshotFailureCode.SEO_BINDING_INVALID)
    dependency = document.get("dependency")
    if type(dependency) is not dict:
        fail_publication_snapshot(PublicationSnapshotFailureCode.SEO_BINDING_INVALID)
    dependency_mapping = cast(dict[str, object], dependency)
    if (
        dependency_mapping.get("st0802_article_version_id") != str(article_version_id)
        or dependency_mapping.get("st0802_body_sha256") != visible_content_sha256.value
        or dependency_mapping.get("st0802_state") != "DRAFT"
        or dependency_mapping.get("st0802_published_at") is not None
        or dependency_mapping.get("st0805_local_eligibility") is not True
        or dependency_mapping.get("st0805_status") != "LOCAL_EVALUATED"
    ):
        fail_publication_snapshot(PublicationSnapshotFailureCode.SEO_BINDING_INVALID)
    render = cast(dict[str, object], document["render"])
    declared_render_digest = _sha_text(document.get("render_local_result_sha256"))
    if (
        _sha256(canonical_json_bytes(render)) != declared_render_digest
        or render.get("mode") != "PREVIEW"
        or render.get("origin_mode") != "ROUTE_ONLY"
        or render.get("caller_origin") is not None
        or render.get("site_projection") is not None
        or render.get("conditional_local_eligibility") is not False
        or type(render.get("rendered_metadata")) is not dict
        or type(render.get("manifest")) is not dict
        or type(render.get("jsonld_json")) is not str
    ):
        fail_publication_snapshot(PublicationSnapshotFailureCode.SEO_BINDING_INVALID)
    rendered = cast(dict[str, object], render["rendered_metadata"])
    manifest = cast(dict[str, object], render["manifest"])
    manifest_article_version = manifest.get("article_version_id")
    jsonld_bytes = cast(str, render["jsonld_json"]).encode("utf-8")
    jsonld_sha = _sha_text(document["jsonld_sha256"])
    if (
        type(manifest_article_version) is not str
        or manifest_article_version.casefold() != str(article_version_id)
        or manifest.get("visible_content_hash") != visible_content_sha256.value
        or manifest.get("jsonld_sha256") != jsonld_sha
        or manifest.get("disabled_types")
        != ["Product", "Offer", "Review", "AggregateRating", "FAQPage"]
        or _sha256(jsonld_bytes) != jsonld_sha
    ):
        fail_publication_snapshot(PublicationSnapshotFailureCode.SEO_BINDING_INVALID)
    return SeoSnapshotBindingV2(
        source_fixture_sha256=Sha256Digest(_sha256(payload)),
        article_version_id=article_version_id,
        rendered_metadata_bytes=canonical_json_bytes(rendered),
        structured_data_manifest_bytes=canonical_json_bytes(manifest),
        jsonld_bytes=jsonld_bytes,
        render_result_sha256=Sha256Digest(declared_render_digest),
        visible_content_sha256=visible_content_sha256,
        jsonld_sha256=Sha256Digest(jsonld_sha),
    )


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedPublicationSnapshotStep(_Redacted):
    request: PublicationSnapshotBuildRequestV2
    bundle: PublicationSnapshotInputBundleV2
    result: PublicationSnapshotResultV2 = field(init=False)
    request_bytes: bytes = field(init=False, repr=False)
    result_bytes: bytes = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.request) is not PublicationSnapshotBuildRequestV2
            or type(self.bundle) is not PublicationSnapshotInputBundleV2
        ):
            fail_publication_snapshot()
        result = build_publication_snapshot_v2(
            request=self.request,
            bundle=self.bundle,
        )
        object.__setattr__(self, "result", result)
        object.__setattr__(self, "request_bytes", self.request.canonical_bytes())
        object.__setattr__(self, "result_bytes", result.canonical_bytes())

    def require_valid(self) -> None:
        self.request.require_valid()
        self.bundle.require_valid()
        expected = build_publication_snapshot_v2(
            request=self.request,
            bundle=self.bundle,
        )
        if (
            self.request.canonical_bytes() != self.request_bytes
            or expected.canonical_bytes() != self.result_bytes
            or expected.content_manifest_bytes != self.result.content_manifest_bytes
            or expected.snapshot_bytes != self.result.snapshot_bytes
        ):
            fail_publication_snapshot(PublicationSnapshotFailureCode.OUTCOME_MISMATCH)


def build_recorded_publication_snapshot_step(
    seed: object,
    *,
    final_approval_fixture: bytes,
    policy_fixture: bytes,
    review_fixture: bytes,
    seo_fixture: bytes,
) -> RecordedPublicationSnapshotStep:
    """Rebuild every recorded predecessor and compose one exact local step."""

    try:
        values = _mapping(seed, _SEED_KEYS)
        approval = load_recorded_final_approval_fixture(
            final_approval_fixture,
            policy_fixture=policy_fixture,
            review_fixture=review_fixture,
        )
        approval.require_valid()
        envelope = load_recorded_policy_fixture(policy_fixture)
        content_ast_json = dump_content_ast_json(
            envelope.draft.snapshot.content_ast
        ).encode("utf-8")
        article_id = _uuid7(values["article_id"])
        article_version_id = _uuid7(values["article_version_id"])
        approval_request = approval.request
        if (
            article_id != envelope.draft.snapshot.article_id
            or article_version_id != envelope.draft.snapshot.version_id
            or article_version_id != approval_request.article_version_id.value
            or _sha256(content_ast_json) != approval_request.canonical_ast_sha256.value
        ):
            fail_publication_snapshot(
                PublicationSnapshotFailureCode.ARTICLE_BINDING_MISMATCH
            )
        seo = _seo_binding(
            payload=seo_fixture,
            article_version_id=article_version_id,
            visible_content_sha256=approval_request.canonical_ast_sha256,
        )
        media = _media_binding(
            seed=values,
            site_id=approval_request.site_id.value,
            version_snapshot=envelope.draft.snapshot,
        )
        report = approval_request.policy_report
        if (
            report.source_packet_content_sha256 is None
            or report.candidate_universe_sha256 is None
            or report.methodology_sha256 is None
        ):
            fail_publication_snapshot(
                PublicationSnapshotFailureCode.INPUT_HASH_MISMATCH
            )
        bundle = PublicationSnapshotInputBundleV2(
            final_approval_request=approval.request,
            final_approval_result=approval.result,
            content_ast_json=content_ast_json,
            source_packet_content_sha256=report.source_packet_content_sha256,
            candidate_universe_sha256=report.candidate_universe_sha256,
            methodology_sha256=report.methodology_sha256,
            policy_bundle_sha256=Sha256Digest(
                _sha_text(values["policy_bundle_sha256"])
            ),
            quality_result_sha256=report.report_sha256,
            seo=seo,
            media=media,
        )
        request = PublicationSnapshotBuildRequestV2(
            publication_candidate_id=_uuid7(values["publication_candidate_id"]),
            publication_content_manifest_id=_uuid7(
                values["publication_content_manifest_id"]
            ),
            publication_id=_uuid7(values["publication_id"]),
            snapshot_artifact_id=_uuid7(values["snapshot_artifact_id"]),
            publication_version=_integer(
                values["publication_version"], minimum=1, maximum=1
            ),
            article_id=article_id,
            article_version_id=article_version_id,
            quality_result_id=_uuid7(values["quality_result_id"]),
            created_at=_instant(values["created_at"]),
            methodology_version_ref=_text(values["methodology_version_ref"]),
            policy_bundle_version_ref=_text(values["policy_bundle_version_ref"]),
            disclosure_policy_version_ref=_text(
                values["disclosure_policy_version_ref"]
            ),
            renderer_version=_text(values["renderer_version"]),
            expected_input_bundle_sha256=bundle.input_bundle_sha256,
            idempotency_key=_text(values["idempotency_key"]),
        )
        return RecordedPublicationSnapshotStep(request=request, bundle=bundle)
    except PublicationSnapshotFailure:
        raise
    except Exception:
        fail_publication_snapshot(PublicationSnapshotFailureCode.FIXTURE_INVALID)


def recorded_publication_snapshot_fixture_document(
    *,
    fixture_id: object,
    seed: object,
    sources: object,
    step: RecordedPublicationSnapshotStep,
) -> dict[str, object]:
    """Return the closed owner-generated fixture projection for one step."""

    if type(step) is not RecordedPublicationSnapshotStep:
        fail_publication_snapshot(PublicationSnapshotFailureCode.FIXTURE_INVALID)
    step.require_valid()
    seed_values = _mapping(seed, _SEED_KEYS)
    source_values = _mapping(sources, _SOURCE_KEYS)
    for value in source_values.values():
        _sha_text(value)
    result = step.result
    return {
        "authority": dict(_AUTHORITY),
        "input": {
            "input_bundle_sha256": step.bundle.input_bundle_sha256.value,
            "media_binding_sha256": step.bundle.media.binding_sha256.value,
            "request": parse_canonical_object(step.request_bytes),
            "seo_binding_sha256": step.bundle.seo.binding_sha256.value,
        },
        "local_status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "output": {
            "content_manifest": result.content_manifest(),
            "result": parse_canonical_object(result.canonical_bytes()),
            "snapshot": result.snapshot(),
        },
        "profile": PROFILE,
        "schema_version": 2,
        "seed": dict(seed_values),
        "sources": dict(source_values),
        "fixture_id": str(_uuid7(fixture_id)),
    }


def load_recorded_publication_snapshot_fixture(
    payload: bytes,
    *,
    final_approval_fixture: bytes,
    policy_fixture: bytes,
    review_fixture: bytes,
    seo_fixture: bytes,
) -> RecordedPublicationSnapshotStep:
    """Load a bounded canonical fixture and independently rebuild its outputs."""

    if (
        type(payload) is not bytes
        or not payload
        or len(payload) > _MAX_FIXTURE_BYTES
        or not payload.endswith(b"\n")
    ):
        fail_publication_snapshot(PublicationSnapshotFailureCode.FIXTURE_INVALID)
    body = payload[:-1]
    document = parse_canonical_object(body)
    if canonical_json_bytes(document) != body:
        fail_publication_snapshot(PublicationSnapshotFailureCode.FIXTURE_INVALID)
    if frozenset(document) != frozenset(
        {
            "authority",
            "fixture_id",
            "input",
            "local_status",
            "output",
            "profile",
            "schema_version",
            "seed",
            "sources",
        }
    ):
        fail_publication_snapshot(PublicationSnapshotFailureCode.FIXTURE_INVALID)
    if (
        document["schema_version"] != 2
        or document["profile"] != PROFILE
        or document["local_status"] != "LOCAL_IMPLEMENTATION_COMPLETE"
        or document["authority"] != _AUTHORITY
    ):
        fail_publication_snapshot(PublicationSnapshotFailureCode.FIXTURE_INVALID)
    _uuid7(document["fixture_id"])
    sources = _mapping(document["sources"], _SOURCE_KEYS)
    exact_sources = {
        "final_approval_fixture_sha256": _sha256(final_approval_fixture),
        "policy_fixture_sha256": _sha256(policy_fixture),
        "review_fixture_sha256": _sha256(review_fixture),
        "seo_fixture_sha256": _sha256(seo_fixture),
    }
    if dict(sources) != exact_sources:
        fail_publication_snapshot(PublicationSnapshotFailureCode.FIXTURE_INVALID)
    step = build_recorded_publication_snapshot_step(
        document["seed"],
        final_approval_fixture=final_approval_fixture,
        policy_fixture=policy_fixture,
        review_fixture=review_fixture,
        seo_fixture=seo_fixture,
    )
    expected = recorded_publication_snapshot_fixture_document(
        fixture_id=document["fixture_id"],
        seed=document["seed"],
        sources=exact_sources,
        step=step,
    )
    if canonical_json_bytes(expected) != body:
        fail_publication_snapshot(PublicationSnapshotFailureCode.FIXTURE_INVALID)
    return step


def _same_request(
    left: object,
    right: PublicationSnapshotBuildRequestV2,
) -> bool:
    try:
        return (
            type(left) is PublicationSnapshotBuildRequestV2
            and left.canonical_bytes() == right.canonical_bytes()
        )
    except Exception:
        return False


@final
class RecordedPublicationSnapshotAdapter(_Redacted):
    """Process-local scripted source and idempotent pure-build exchange."""

    __slots__ = ("_cursor", "_lock", "_replays", "_steps")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        steps: tuple[RecordedPublicationSnapshotStep, ...],
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or type(steps) is not tuple
            or not 1 <= len(steps) <= _MAX_STEPS
            or any(type(step) is not RecordedPublicationSnapshotStep for step in steps)
        ):
            fail_publication_snapshot(
                PublicationSnapshotFailureCode.LOCAL_ENVIRONMENT_REQUIRED
            )
        identities: set[str] = set()
        for step in steps:
            step.require_valid()
            identity = step.request.idempotency_key
            if identity in identities:
                fail_publication_snapshot(
                    PublicationSnapshotFailureCode.IDEMPOTENCY_CONFLICT
                )
            identities.add(identity)
        self._steps = steps
        self._cursor = 0
        self._replays: dict[
            str,
            tuple[
                bytes,
                PublicationSnapshotInputBundleV2,
                PublicationSnapshotResultV2,
            ],
        ] = {}
        self._lock = RLock()

    def load(
        self,
        request: PublicationSnapshotBuildRequestV2,
    ) -> PublicationSnapshotInputBundleV2:
        if type(request) is not PublicationSnapshotBuildRequestV2:
            fail_publication_snapshot()
        request.require_valid()
        identity = request.idempotency_key
        with self._lock:
            replay = self._replays.get(identity)
            if replay is not None:
                request_bytes, bundle, _result = replay
                if request.canonical_bytes() != request_bytes:
                    fail_publication_snapshot(
                        PublicationSnapshotFailureCode.IDEMPOTENCY_CONFLICT
                    )
                bundle.require_valid()
                return bundle
            if self._cursor >= len(self._steps):
                fail_publication_snapshot(
                    PublicationSnapshotFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                )
            step = self._steps[self._cursor]
            step.require_valid()
            if identity == step.request.idempotency_key and not _same_request(
                request, step.request
            ):
                fail_publication_snapshot(
                    PublicationSnapshotFailureCode.IDEMPOTENCY_CONFLICT
                )
            if not _same_request(request, step.request):
                fail_publication_snapshot(
                    PublicationSnapshotFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                )
            return step.bundle

    def exchange(
        self,
        request: PublicationSnapshotBuildRequestV2,
        bundle: PublicationSnapshotInputBundleV2,
    ) -> PublicationSnapshotResultV2:
        if (
            type(request) is not PublicationSnapshotBuildRequestV2
            or type(bundle) is not PublicationSnapshotInputBundleV2
        ):
            fail_publication_snapshot()
        identity = request.idempotency_key
        with self._lock:
            replay = self._replays.get(identity)
            if replay is not None:
                request_bytes, retained_bundle, result = replay
                if (
                    request.canonical_bytes() != request_bytes
                    or retained_bundle.input_bundle_sha256 != bundle.input_bundle_sha256
                ):
                    fail_publication_snapshot(
                        PublicationSnapshotFailureCode.IDEMPOTENCY_CONFLICT
                    )
                return result
            if self._cursor >= len(self._steps):
                fail_publication_snapshot(
                    PublicationSnapshotFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                )
            step = self._steps[self._cursor]
            step.require_valid()
            if (
                not _same_request(request, step.request)
                or bundle.input_bundle_sha256 != step.bundle.input_bundle_sha256
            ):
                fail_publication_snapshot(
                    PublicationSnapshotFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                )
            self._replays[identity] = (step.request_bytes, step.bundle, step.result)
            self._cursor += 1
            return step.result

    @property
    def consumed_steps(self) -> int:
        with self._lock:
            return self._cursor


__all__ = (
    "RecordedPublicationSnapshotAdapter",
    "RecordedPublicationSnapshotStep",
    "build_recorded_publication_snapshot_step",
    "load_recorded_publication_snapshot_fixture",
    "recorded_publication_snapshot_fixture_document",
)

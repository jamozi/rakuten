from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path

import jsonschema
from pydantic import ValidationError
import pytest

from .conftest import REPO_ROOT
from raos.adapters.recorded_publication_snapshot_v2 import (
    RecordedPublicationSnapshotStep,
)
from raos.domain.publishing.publication_snapshot_v2 import (
    INPUT_HASH_KEYS,
    ExternalGateStatus,
    MediaSnapshotBindingV2,
    PublicationSnapshotFailure,
    PublicationSnapshotFailureCode,
    SeoSnapshotBindingV2,
    SnapshotContractCompatibility,
    SnapshotReadiness,
    build_publication_snapshot_v2,
    canonical_json_bytes,
    parse_canonical_object,
)
from raos.domain.shared.persistence import Sha256Digest
from raos.generated.contracts.publication_snapshot import Schema as LegacySnapshot


def test_build_is_byte_deterministic_and_binds_every_input_hash(
    step: RecordedPublicationSnapshotStep,
) -> None:
    first = build_publication_snapshot_v2(request=step.request, bundle=step.bundle)
    second = build_publication_snapshot_v2(request=step.request, bundle=step.bundle)

    assert first.canonical_bytes() == second.canonical_bytes()
    assert first.content_manifest_bytes == second.content_manifest_bytes
    assert first.snapshot_bytes == second.snapshot_bytes
    assert first.result_sha256 == second.result_sha256
    assert tuple(sorted(first.snapshot()["input_hashes"])) == INPUT_HASH_KEYS


def test_manifest_and_snapshot_bind_the_exact_approved_version(
    step: RecordedPublicationSnapshotStep,
) -> None:
    result = step.result
    manifest = result.content_manifest()
    snapshot = result.snapshot()

    assert manifest["article_version_id"] == str(step.request.article_version_id)
    assert manifest["approval_refs"] == [
        str(step.bundle.final_approval_result.record.approval_id.value)
    ]
    assert manifest["content_ast_sha256"] == (
        step.bundle.final_approval_request.canonical_ast_sha256.value
    )
    assert snapshot["article_id"] == str(step.request.article_id)
    assert snapshot["article_version_id"] == str(step.request.article_version_id)
    assert snapshot["renderable_content"]["article_version_id"] == str(
        step.request.article_version_id
    )
    assert snapshot["seo_metadata"]["index_state"] == "noindex"
    assert snapshot["product_selection_refs"] == [
        "PSEL-FIX-001",
        "PSEL-FIX-002",
        "PSEL-FIX-003",
    ]
    assert snapshot["safe_offer_projection_version"] == 0


def test_content_manifest_matches_its_current_json_schema(
    step: RecordedPublicationSnapshotStep,
) -> None:
    schema = json.loads(
        (
            REPO_ROOT
            / Path(
                "contracts/raos-v0.4/contracts/content/schemas/"
                "publication-content-manifest.schema.json"
            )
        ).read_bytes()
    )
    jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    ).validate(step.result.content_manifest())


def test_legacy_snapshot_schema_mismatch_is_not_promoted_to_success(
    step: RecordedPublicationSnapshotStep,
) -> None:
    with pytest.raises(ValidationError):
        LegacySnapshot.model_validate(step.result.snapshot())
    assert step.result.compatibility is (
        SnapshotContractCompatibility.CONTENT_AST_V1_BOUND_LEGACY_SCHEMA_RECONCILIATION_REQUIRED
    )


def test_self_hash_excludes_only_declared_digest(
    step: RecordedPublicationSnapshotStep,
) -> None:
    result = step.result
    snapshot = result.snapshot()
    declared = snapshot.pop("snapshot_sha256")

    assert hashlib.sha256(canonical_json_bytes(snapshot)).hexdigest() == declared
    assert hashlib.sha256(result.snapshot_bytes).hexdigest() == (
        result.snapshot_artifact_sha256.value
    )
    assert result.snapshot_sha256.value != result.snapshot_artifact_sha256.value


def test_result_is_not_ready_and_grants_no_authority(
    step: RecordedPublicationSnapshotStep,
) -> None:
    result = step.result
    assert result.readiness is SnapshotReadiness.NOT_READY
    assert result.compatibility is (
        SnapshotContractCompatibility.CONTENT_AST_V1_BOUND_LEGACY_SCHEMA_RECONCILIATION_REQUIRED
    )
    assert result.local_snapshot_candidate_built is True
    assert result.immutable is True
    assert result.persisted is False
    assert result.event_emitted is False
    assert result.public_projection_authorized is False
    assert result.publication_authorized is False
    assert result.release_authorized is False
    assert result.production_authorized is False
    assert {
        result.formal_tst_014_status,
        result.formal_tst_021_status,
        result.live_status,
        result.staging_status,
        result.publication_status,
        result.release_status,
        result.production_status,
    } == {ExternalGateStatus.NOT_EXECUTED}


def test_values_are_immutable(step: RecordedPublicationSnapshotStep) -> None:
    with pytest.raises(FrozenInstanceError):
        step.result.publication_authorized = True  # type: ignore[misc]


def test_ast_drift_fails_closed(step: RecordedPublicationSnapshotStep) -> None:
    with pytest.raises(PublicationSnapshotFailure) as captured:
        replace(step.bundle, content_ast_json=step.bundle.content_ast_json + b" ")
    assert captured.value.code is PublicationSnapshotFailureCode.CONTENT_AST_INVALID


def test_media_public_rendering_cannot_be_promoted(
    step: RecordedPublicationSnapshotStep,
) -> None:
    media = step.bundle.media
    with pytest.raises(PublicationSnapshotFailure) as captured:
        MediaSnapshotBindingV2(
            article_version_id=media.article_version_id,
            asset_id=media.asset_id,
            asset_content_sha256=media.asset_content_sha256,
            candidate_fingerprint=media.candidate_fingerprint,
            byte_size=media.byte_size,
            public_rendering=True,
        )
    assert captured.value.code is PublicationSnapshotFailureCode.MEDIA_BINDING_INVALID


def test_product_jsonld_is_rejected_recursively(
    step: RecordedPublicationSnapshotStep,
) -> None:
    seo = step.bundle.seo
    payload = canonical_json_bytes(
        {"@context": "https://schema.org", "@type": "Product"}
    )
    with pytest.raises(PublicationSnapshotFailure) as captured:
        SeoSnapshotBindingV2(
            source_fixture_sha256=seo.source_fixture_sha256,
            article_version_id=seo.article_version_id,
            rendered_metadata_bytes=seo.rendered_metadata_bytes,
            structured_data_manifest_bytes=seo.structured_data_manifest_bytes,
            jsonld_bytes=payload,
            render_result_sha256=seo.render_result_sha256,
            visible_content_sha256=seo.visible_content_sha256,
            jsonld_sha256=Sha256Digest(hashlib.sha256(payload).hexdigest()),
        )
    assert captured.value.code is PublicationSnapshotFailureCode.SEO_BINDING_INVALID


def test_snapshot_rejects_secret_aliases_inside_bound_seo(
    step: RecordedPublicationSnapshotStep,
) -> None:
    source = step.bundle.seo
    rendered = parse_canonical_object(source.rendered_metadata_bytes)
    rendered["api-key"] = "fixture-placeholder"
    seo = SeoSnapshotBindingV2(
        source_fixture_sha256=source.source_fixture_sha256,
        article_version_id=source.article_version_id,
        rendered_metadata_bytes=canonical_json_bytes(rendered),
        structured_data_manifest_bytes=source.structured_data_manifest_bytes,
        jsonld_bytes=source.jsonld_bytes,
        render_result_sha256=source.render_result_sha256,
        visible_content_sha256=source.visible_content_sha256,
        jsonld_sha256=source.jsonld_sha256,
    )
    bundle = replace(step.bundle, seo=seo)
    request = replace(
        step.request,
        expected_input_bundle_sha256=bundle.input_bundle_sha256,
    )
    with pytest.raises(PublicationSnapshotFailure) as captured:
        build_publication_snapshot_v2(request=request, bundle=bundle)
    assert captured.value.code is PublicationSnapshotFailureCode.INVALID_ARGUMENT


@pytest.mark.parametrize(
    "payload",
    [
        b'{"a":1,"a":2}',
        b'{"a":1.5}',
        b'{"a":NaN}',
        b"[]",
        b"",
    ],
)
def test_json_boundary_rejects_ambiguous_or_noncanonical_types(payload: bytes) -> None:
    with pytest.raises(PublicationSnapshotFailure):
        parse_canonical_object(payload)


def test_failure_never_retains_rejected_material() -> None:
    marker = "sensitive-st0903-rejected-value"
    with pytest.raises(PublicationSnapshotFailure) as captured:
        parse_canonical_object(('{"' + marker + '":1.5}').encode())
    assert marker not in str(captured.value)
    assert marker not in repr(captured.value)

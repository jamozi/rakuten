"""Focused behavior tests for the closed ST-0808 seam."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from .support import (
    ASSET_ID,
    command,
    intake_result,
    observation,
    service_for,
    validator_for,
)
from raos.domain.editorial.article_lifecycle import (
    ArticleVersionState,
    SourcePacketVerification,
)
from raos.domain.editorial.media_asset import (
    CleanQuarantinedMediaCandidate,
    MediaAssetDecision,
    MediaAssetExecution,
    MediaAssetFailure,
    MediaAssetVisibility,
    RecordedRightsDisposition,
    candidate_from_intake,
)
from raos.domain.ops.object_intake import ObjectIntakeKind


def test_eligible_fixture_returns_only_admin_reference() -> None:
    request = command()
    result = service_for(validator_for(request)).validate(request)

    assert result.intake_result is request.intake_result
    assert result.version_snapshot is request.version_snapshot
    assert result.version_snapshot.state is ArticleVersionState.DRAFT
    assert (
        result.version_snapshot.source_packet_verification
        is SourcePacketVerification.NOT_VERIFIED
    )
    assert result.visibility is MediaAssetVisibility.ADMIN_ONLY_REFERENCE
    assert result.reference is not None
    assert result.reference.asset_id == ASSET_ID
    assert set(result.reference.__dataclass_fields__) == {"asset_id", "visibility"}
    assert result.raw_artifact_ref is None
    assert result.renderer_input is None
    assert result.public_rendering is False
    assert result.approval is None
    assert result.publication is None
    assert result.validation is MediaAssetExecution.RECORDED_ONLY
    assert result.decision is MediaAssetDecision.NOT_READY
    assert set(result.execution_markers.values()) == {
        "RECORDED_TEST_ONLY",
        "NOT_EXECUTED",
    }


@pytest.mark.parametrize(
    ("rights", "expected"),
    [
        (None, MediaAssetVisibility.HIDDEN_UNKNOWN_RIGHTS),
        (
            RecordedRightsDisposition.UNKNOWN,
            MediaAssetVisibility.HIDDEN_UNKNOWN_RIGHTS,
        ),
        (RecordedRightsDisposition.FORBIDDEN, MediaAssetVisibility.HIDDEN_POLICY),
        (
            RecordedRightsDisposition.EXCEPTION_ONLY,
            MediaAssetVisibility.HIDDEN_POLICY,
        ),
    ],
)
def test_noneligible_rights_are_hidden(
    rights: RecordedRightsDisposition | None,
    expected: MediaAssetVisibility,
) -> None:
    request = command(rights)
    result = service_for(validator_for(request)).validate(request)
    assert result.visibility is expected
    assert result.reference is None
    assert result.renderer_input is None


def test_candidate_is_exact_lossless_intake_projection() -> None:
    intake = intake_result()
    candidate = candidate_from_intake(intake)
    assert candidate.object_kind == "MEDIA_ASSET"
    assert candidate.quarantine_disposition == "CLEAN_QUARANTINED"
    assert candidate.declared_sha256 == candidate.sealed_sha256
    assert candidate.declared_size == candidate.sealed_size
    assert candidate.fingerprint == candidate_from_intake(intake).fingerprint


def test_non_media_intake_is_rejected() -> None:
    with pytest.raises(MediaAssetFailure):
        command(intake=intake_result(kind=ObjectIntakeKind.SOURCE_DOCUMENT))


@pytest.mark.parametrize("field", ["declared_sha256", "sealed_sha256"])
def test_digest_drift_is_rejected(field: str) -> None:
    candidate = command().request.candidate
    with pytest.raises(MediaAssetFailure):
        CleanQuarantinedMediaCandidate(
            intake_id=candidate.intake_id,
            site_id=candidate.site_id,
            object_kind="MEDIA_ASSET",
            quarantine_disposition="CLEAN_QUARANTINED",
            declared_sha256="2" * 64 if field == "declared_sha256" else "1" * 64,
            sealed_sha256="2" * 64 if field == "sealed_sha256" else "1" * 64,
            declared_size=1,
            sealed_size=1,
        )


@pytest.mark.parametrize("value", [False, 0, -1, 1.0, "1"])
def test_size_requires_positive_exact_integer(value: object) -> None:
    with pytest.raises(MediaAssetFailure):
        CleanQuarantinedMediaCandidate(
            intake_id=command().request.candidate.intake_id,
            site_id=command().request.candidate.site_id,
            object_kind="MEDIA_ASSET",
            quarantine_disposition="CLEAN_QUARANTINED",
            declared_sha256="1" * 64,
            sealed_sha256="1" * 64,
            declared_size=value,  # type: ignore[arg-type]
            sealed_size=value,  # type: ignore[arg-type]
        )


def test_values_are_immutable() -> None:
    request = command()
    result = service_for(validator_for(request)).validate(request)
    with pytest.raises(FrozenInstanceError):
        result.public_rendering = True  # type: ignore[misc]


def test_observation_factory_matches_command() -> None:
    request = command(RecordedRightsDisposition.UNKNOWN)
    recorded = observation(request)
    assert recorded.candidate_fingerprint == request.request.candidate.fingerprint
    assert recorded.asset_id is None

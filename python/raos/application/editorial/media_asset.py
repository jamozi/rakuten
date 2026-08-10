"""Fail-closed recorded-only media validation service for ST-0808."""

from __future__ import annotations

from typing import final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.editorial.media_asset import (
    AdminOnlyMediaAssetReference,
    MediaAssetDecision,
    MediaAssetExecution,
    MediaAssetFailureCode,
    MediaAssetMode,
    MediaAssetVisibility,
    MediaValidationCommand,
    MediaValidationResult,
    RecordedMediaValidationObservation,
    RecordedRightsDisposition,
    execution_markers,
    fail_media_asset,
)
from raos.ports.media_asset import RecordedMediaAssetValidator


def _expected_visibility(
    rights: RecordedRightsDisposition | None,
) -> MediaAssetVisibility:
    if rights in {None, RecordedRightsDisposition.UNKNOWN}:
        return MediaAssetVisibility.HIDDEN_UNKNOWN_RIGHTS
    if rights in {
        RecordedRightsDisposition.FORBIDDEN,
        RecordedRightsDisposition.EXCEPTION_ONLY,
    }:
        return MediaAssetVisibility.HIDDEN_POLICY
    if rights is RecordedRightsDisposition.ADMIN_REFERENCE_ELIGIBLE:
        return MediaAssetVisibility.ADMIN_ONLY_REFERENCE
    fail_media_asset()


@final
class MediaAssetValidationService:
    """Validate one exact synthetic fixture without storage or rendering effects."""

    __slots__ = ("_validator",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        mode: MediaAssetMode,
        validator: RecordedMediaAssetValidator,
    ) -> None:
        if (
            environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or mode is not MediaAssetMode.RECORDED_TEST_ONLY
            or not callable(getattr(validator, "validate", None))
        ):
            fail_media_asset()
        self._validator = validator

    def validate(self, command: MediaValidationCommand) -> MediaValidationResult:
        if type(command) is not MediaValidationCommand:
            fail_media_asset()
        request = command.request
        collaborator_failed = False
        observed: object = None
        try:
            observed = self._validator.validate(command)
        except Exception:
            collaborator_failed = True
        if collaborator_failed:
            fail_media_asset(MediaAssetFailureCode.LOCAL_VALIDATION_UNAVAILABLE)
        if type(observed) is not RecordedMediaValidationObservation:
            fail_media_asset(MediaAssetFailureCode.OUTCOME_MISMATCH)
        expected_visibility = _expected_visibility(command.rights_disposition)
        if (
            observed.candidate_fingerprint != request.candidate.fingerprint
            or observed.rights_disposition is not command.rights_disposition
            or observed.visibility is not expected_visibility
        ):
            fail_media_asset(MediaAssetFailureCode.OUTCOME_MISMATCH)
        if expected_visibility is MediaAssetVisibility.ADMIN_ONLY_REFERENCE:
            if observed.asset_id is None:
                fail_media_asset(MediaAssetFailureCode.OUTCOME_MISMATCH)
            reference = AdminOnlyMediaAssetReference(asset_id=observed.asset_id)
        else:
            reference = None
        return MediaValidationResult(
            intake_result=command.intake_result,
            candidate=request.candidate,
            version_snapshot=command.version_snapshot,
            visibility=expected_visibility,
            reference=reference,
            raw_artifact_ref=None,
            decision=MediaAssetDecision.NOT_READY,
            validation=MediaAssetExecution.RECORDED_ONLY,
            public_rendering=False,
            renderer_input=None,
            approval=None,
            publication=None,
            execution_markers=execution_markers(),
        )


__all__ = ["MediaAssetValidationService"]

"""Failure isolation and scripted-adapter hostile cases for ST-0808."""

from __future__ import annotations

import pickle
from typing import cast

import pytest

from conftest import command, observation, service_for, validator_for
from raos.adapters.recorded_media_asset import (
    RecordedMediaAssetStep,
    RecordedMediaAssetValidator,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.editorial.media_asset import (
    MediaAssetFailure,
    MediaAssetFailureCode,
    MediaAssetMode,
    MediaAssetVisibility,
    RecordedMediaValidationObservation,
    RecordedRightsDisposition,
)


class ExplodingValidator:
    def validate(self, command: object) -> object:
        del command
        raise RuntimeError("SECRET_CANARY_DO_NOT_ECHO")


class MalformedValidator:
    def validate(self, command: object) -> object:
        del command
        return object()


class StaticValidator:
    def __init__(self, value: object) -> None:
        self.value = value

    def validate(self, command: object) -> object:
        del command
        return self.value


def test_collaborator_exception_is_sanitized() -> None:
    with pytest.raises(MediaAssetFailure) as captured:
        service_for(ExplodingValidator()).validate(command())
    assert captured.value.code is MediaAssetFailureCode.LOCAL_VALIDATION_UNAVAILABLE
    assert "SECRET_CANARY" not in str(captured.value)
    assert "SECRET_CANARY" not in repr(captured.value)
    assert captured.value.__cause__ is None
    with pytest.raises(TypeError):
        pickle.dumps(captured.value)


def test_malformed_collaborator_result_is_rejected() -> None:
    with pytest.raises(MediaAssetFailure) as captured:
        service_for(MalformedValidator()).validate(command())
    assert captured.value.code is MediaAssetFailureCode.OUTCOME_MISMATCH


def test_outcome_rights_drift_is_rejected() -> None:
    request = command(RecordedRightsDisposition.ADMIN_REFERENCE_ELIGIBLE)
    drift = RecordedMediaValidationObservation(
        candidate_fingerprint=request.request.candidate.fingerprint,
        rights_disposition=RecordedRightsDisposition.UNKNOWN,
        visibility=MediaAssetVisibility.HIDDEN_UNKNOWN_RIGHTS,
        asset_id=None,
    )
    with pytest.raises(MediaAssetFailure) as captured:
        service_for(StaticValidator(drift)).validate(request)
    assert captured.value.code is MediaAssetFailureCode.OUTCOME_MISMATCH


def test_adapter_rejects_reorder_and_then_accepts_expected_step() -> None:
    first = command(RecordedRightsDisposition.UNKNOWN)
    second = command(RecordedRightsDisposition.FORBIDDEN)
    adapter = RecordedMediaAssetValidator(
        environment=RuntimeEnvironment.CI,
        mode=MediaAssetMode.RECORDED_TEST_ONLY,
        script_capacity=2,
        scripts=(
            RecordedMediaAssetStep(first, observation(first)),
            RecordedMediaAssetStep(second, observation(second)),
        ),
    )
    with pytest.raises(MediaAssetFailure):
        adapter.validate(second)
    assert adapter.validate(first) == observation(first)
    assert adapter.validate(second) == observation(second)


def test_adapter_exhaustion_is_fail_closed() -> None:
    request = command()
    adapter = validator_for(request)
    assert adapter.validate(request) == observation(request)
    with pytest.raises(MediaAssetFailure) as captured:
        adapter.validate(request)
    assert captured.value.code is MediaAssetFailureCode.LOCAL_VALIDATION_UNAVAILABLE


@pytest.mark.parametrize("capacity", [False, 0, -1, 1.0, "1"])
def test_adapter_capacity_is_positive_exact_integer(capacity: object) -> None:
    request = command()
    with pytest.raises(MediaAssetFailure):
        RecordedMediaAssetValidator(
            environment=RuntimeEnvironment.ENV_DEV,
            mode=MediaAssetMode.RECORDED_TEST_ONLY,
            script_capacity=cast(int, capacity),
            scripts=(RecordedMediaAssetStep(request, observation(request)),),
        )


def test_duplicate_candidate_scripts_are_rejected() -> None:
    request = command()
    step = RecordedMediaAssetStep(request, observation(request))
    with pytest.raises(MediaAssetFailure):
        RecordedMediaAssetValidator(
            environment=RuntimeEnvironment.ENV_DEV,
            mode=MediaAssetMode.RECORDED_TEST_ONLY,
            script_capacity=2,
            scripts=(step, step),
        )


def test_script_and_adapter_do_not_pickle_or_echo_values() -> None:
    request = command()
    step = RecordedMediaAssetStep(request, observation(request))
    adapter = validator_for(request)
    assert "018f" not in repr(step)
    assert "018f" not in repr(adapter)
    with pytest.raises(TypeError):
        pickle.dumps(step)
    with pytest.raises(TypeError):
        pickle.dumps(adapter)

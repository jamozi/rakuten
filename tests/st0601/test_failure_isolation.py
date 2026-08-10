"""Observe-once and sanitized failure checks for ST-0601."""

from __future__ import annotations

import pickle
from typing import cast

import pytest

from raos.adapters.recorded_artifact_registry import RecordedArtifactFixture
from raos.application.ops.artifact_registry import ArtifactRegistryReferenceService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ops.artifact_registry import (
    ArtifactKind,
    ArtifactObservation,
    ArtifactProvenance,
    ArtifactRegistryFailure,
    ArtifactRegistryFailureCode,
    ExecutionStatus,
    RegistryMode,
)

from conftest import SYNTHETIC_CONTENT, provenance


REJECTED_CANARY = "REJECTED_VALUE_CANARY_ST0601_DO_NOT_ECHO"


class _ObserverProbe:
    def __init__(self, observation: ArtifactObservation) -> None:
        self.observation = observation
        self.error: Exception | None = None
        self.calls = 0

    def observe(self, candidate: ArtifactProvenance) -> ArtifactObservation:
        del candidate
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.observation


def _observation() -> ArtifactObservation:
    return ArtifactObservation.from_synthetic(
        candidate=provenance(),
        content=SYNTHETIC_CONTENT,
    )


def _service(observer: _ObserverProbe) -> ArtifactRegistryReferenceService:
    return ArtifactRegistryReferenceService(
        environment=RuntimeEnvironment.ENV_DEV,
        mode=RegistryMode.RECORDED_TEST_ONLY,
        observer=observer,
    )


def test_observer_is_called_exactly_once() -> None:
    observer = _ObserverProbe(_observation())
    _service(observer).plan(provenance())
    assert observer.calls == 1


def test_observer_exception_is_sanitized_without_retry_or_context() -> None:
    observer = _ObserverProbe(_observation())
    observer.error = RuntimeError(REJECTED_CANARY)
    with pytest.raises(ArtifactRegistryFailure) as caught:
        _service(observer).plan(provenance())
    assert caught.value.code is ArtifactRegistryFailureCode.OBSERVATION_UNAVAILABLE
    assert observer.calls == 1
    assert REJECTED_CANARY not in f"{caught.value!s} {caught.value!r}"
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_malformed_observer_output_fails_without_fallback() -> None:
    observer = _ObserverProbe(_observation())
    observer.observation = cast(ArtifactObservation, object())
    with pytest.raises(ArtifactRegistryFailure) as caught:
        _service(observer).plan(provenance())
    assert caught.value.code is ArtifactRegistryFailureCode.OBSERVATION_UNAVAILABLE
    assert observer.calls == 1


def test_mutated_observation_execution_status_fails_closed() -> None:
    observation = _observation()
    object.__setattr__(
        observation,
        "storage_execution",
        cast(ExecutionStatus, "EXECUTED"),
    )
    observer = _ObserverProbe(observation)
    with pytest.raises(ArtifactRegistryFailure) as caught:
        _service(observer).plan(provenance())
    assert caught.value.code is ArtifactRegistryFailureCode.OBSERVATION_UNAVAILABLE


def test_non_raw_provider_kind_is_rejected_before_observation() -> None:
    candidate = provenance()
    object.__setattr__(candidate, "kind", ArtifactKind.RAW_PRIMARY_SOURCE)
    observer = _ObserverProbe(_observation())
    with pytest.raises(ArtifactRegistryFailure):
        _service(observer).plan(candidate)
    assert observer.calls == 0


def test_mutated_candidate_is_rejected_before_observation() -> None:
    candidate = provenance()
    object.__setattr__(candidate.digest, "value", "INVALID")
    observer = _ObserverProbe(_observation())
    with pytest.raises(ArtifactRegistryFailure):
        _service(observer).plan(candidate)
    assert observer.calls == 0


@pytest.mark.parametrize(
    ("environment", "mode"),
    (
        (RuntimeEnvironment.PRODUCTION, RegistryMode.RECORDED_TEST_ONLY),
        (RuntimeEnvironment.ENV_DEV, cast(RegistryMode, "LIVE")),
    ),
)
def test_non_recorded_or_external_environment_is_rejected(
    environment: RuntimeEnvironment,
    mode: RegistryMode,
) -> None:
    observer = _ObserverProbe(_observation())
    with pytest.raises(ArtifactRegistryFailure):
        ArtifactRegistryReferenceService(
            environment=environment,
            mode=mode,
            observer=observer,
        )
    assert observer.calls == 0


def test_fixture_retains_no_content_and_is_not_pickleable() -> None:
    fixture = RecordedArtifactFixture(
        candidate=provenance(),
        synthetic_content=SYNTHETIC_CONTENT,
    )
    assert not hasattr(fixture, "content")
    assert not hasattr(fixture, "synthetic_content")
    assert REJECTED_CANARY not in repr(fixture)
    with pytest.raises(TypeError):
        pickle.dumps(fixture)

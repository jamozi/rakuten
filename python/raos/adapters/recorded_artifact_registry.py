"""Immutable synthetic observation fixtures for the ST-0601 reference plan."""

from __future__ import annotations

from typing import NoReturn, SupportsIndex, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ops.artifact_registry import (
    ArtifactObservation,
    ArtifactProvenance,
    ArtifactRegistryFailureCode,
    RegistryMode,
    fail_artifact_registry,
)


@final
class RecordedArtifactFixture:
    """Compute and retain metadata only; input bytes are never stored or returned."""

    __slots__ = ("_candidate", "_observation", "_sealed")
    _candidate: ArtifactProvenance
    _observation: ArtifactObservation
    _sealed: bool

    def __init__(
        self, *, candidate: ArtifactProvenance, synthetic_content: bytes
    ) -> None:
        if (
            type(candidate) is not ArtifactProvenance
            or type(synthetic_content) is not bytes
        ):
            fail_artifact_registry()
        observation = ArtifactObservation.from_synthetic(
            candidate=candidate,
            content=synthetic_content,
        )
        object.__setattr__(self, "_candidate", candidate)
        object.__setattr__(self, "_observation", observation)
        object.__setattr__(self, "_sealed", True)

    @property
    def candidate(self) -> ArtifactProvenance:
        return self._candidate

    @property
    def observation(self) -> ArtifactObservation:
        return self._observation

    def __repr__(self) -> str:
        return "RecordedArtifactFixture(<redacted-artifact-registry>)"

    def __str__(self) -> str:
        return "<redacted-artifact-registry>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded artifact fixture serialization is not supported")

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("RecordedArtifactFixture is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("RecordedArtifactFixture is immutable")


@final
class RecordedArtifactCandidateObserver:
    """Exact fixture lookup with no bytes, history, storage, or I/O surface."""

    __slots__ = ("_fixtures",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        mode: RegistryMode,
        fixture_capacity: int,
        fixtures: tuple[RecordedArtifactFixture, ...],
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or mode is not RegistryMode.RECORDED_TEST_ONLY
            or type(mode) is not RegistryMode
            or type(fixture_capacity) is not int
            or not 0 < fixture_capacity <= 10_000
            or type(fixtures) is not tuple
            or not fixtures
            or len(fixtures) > fixture_capacity
            or any(type(fixture) is not RecordedArtifactFixture for fixture in fixtures)
        ):
            fail_artifact_registry()
        locations = tuple(
            fixture.candidate.location.canonical_key for fixture in fixtures
        )
        fingerprints = tuple(fixture.candidate.fingerprint for fixture in fixtures)
        if len(set(locations)) != len(locations) or len(set(fingerprints)) != len(
            fingerprints
        ):
            fail_artifact_registry()
        self._fixtures = fixtures

    def observe(self, candidate: ArtifactProvenance) -> ArtifactObservation:
        if type(candidate) is not ArtifactProvenance:
            fail_artifact_registry()
        matches = tuple(
            fixture
            for fixture in self._fixtures
            if fixture.candidate.fingerprint == candidate.fingerprint
            and fixture.candidate == candidate
        )
        if len(matches) != 1:
            fail_artifact_registry(ArtifactRegistryFailureCode.OBSERVATION_UNAVAILABLE)
        return matches[0].observation


__all__ = ["RecordedArtifactCandidateObserver", "RecordedArtifactFixture"]

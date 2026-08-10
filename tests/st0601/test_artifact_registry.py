"""Core match and tamper decisions for ST-0601."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Callable, cast

import pytest

from raos.adapters.recorded_artifact_registry import (
    RecordedArtifactCandidateObserver,
    RecordedArtifactFixture,
)
from raos.application.ops.artifact_registry import ArtifactRegistryReferenceService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ops.artifact_registry import (
    ArtifactKind,
    ArtifactObservation,
    ArtifactProvenance,
    ArtifactRegistryFailure,
    ArtifactRegistryReferencePlan,
    IntegrityDecision,
    MATCHING_BLOCKERS,
    ObjectLocationCandidate,
    RegistryBlocker,
    RegistryDecision,
    RegistryMode,
    Sha256Digest,
)

from conftest import (
    ACQUIRED_AT,
    SYNTHETIC_CONTENT,
    location_candidate,
    observer_for,
    provenance,
    service_for,
)


def test_recorded_match_is_still_not_ready_and_allocates_nothing() -> None:
    candidate = provenance()
    plan = service_for(candidate).plan(candidate)

    assert plan.decision is RegistryDecision.NOT_READY
    assert plan.integrity is IntegrityDecision.RECORDED_MATCH
    assert plan.blockers == MATCHING_BLOCKERS
    assert plan.artifact_id is None
    assert plan.artifact_ref is None
    assert plan.retention is None
    assert plan.actions == ()


def test_digest_tamper_is_hard_rejected_without_registration() -> None:
    candidate = provenance(digest=Sha256Digest("0" * 64))
    plan = service_for(candidate).plan(candidate)

    assert plan.decision is RegistryDecision.REJECTED
    assert plan.integrity is IntegrityDecision.TAMPER_DETECTED
    assert plan.blockers == (RegistryBlocker.TAMPER_DETECTED,)
    assert plan.artifact_id is plan.artifact_ref is plan.retention is None


def test_digest_and_provenance_fingerprints_are_deterministic() -> None:
    candidate = provenance()
    observation = ArtifactObservation.from_synthetic(
        candidate=candidate,
        content=SYNTHETIC_CONTENT,
    )
    assert Sha256Digest.of(SYNTHETIC_CONTENT).value == (
        "9ba77392cd013305663455c6137b5f96099f7e1b06a43a08395b10d192f852aa"
    )
    assert candidate.fingerprint == (
        "c8a51c25c27fb2263fcbf42748e76e171c67c44aaafc5dde49578b6db4d55683"
    )
    assert observation.fingerprint == (
        "38e15706bab578901ae162ee7359ef182e48ef2f2331a05c47e6165c6ad0e27f"
    )
    assert b": " not in candidate.canonical_json
    assert b", " not in candidate.canonical_json


def test_canonical_artifact_kind_vocabulary_is_exact() -> None:
    assert tuple(kind.value for kind in ArtifactKind) == (
        "raw_provider_response",
        "raw_primary_source",
        "source_snapshot",
        "source_packet",
        "ai_input",
        "ai_output",
        "publication_snapshot",
        "revenue_original",
        "revenue_rejects",
        "audit_export",
        "quality_report",
        "diff",
        "import_report",
        "other",
    )


@pytest.mark.parametrize(
    "factory",
    (
        lambda: Sha256Digest("A" * 64),
        lambda: Sha256Digest("0" * 63),
        lambda: Sha256Digest.of(cast(bytes, "not-bytes")),
        lambda: Sha256Digest.of(b""),
        lambda: Sha256Digest.of(b"x" * (8 * 1024 * 1024 + 1)),
    ),
)
def test_digest_rejects_wrong_case_type_and_material_bounds(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(ArtifactRegistryFailure):
        factory()


@pytest.mark.parametrize(
    "factory",
    (
        lambda: replace(location_candidate(), scheme="file"),
        lambda: replace(location_candidate(), bucket="other"),
        lambda: replace(location_candidate(), object_key="/absolute"),
        lambda: replace(location_candidate(), object_key="raw/../escape"),
        lambda: replace(location_candidate(), object_key="raw//empty"),
        lambda: replace(location_candidate(), object_key="raw\\windows"),
        lambda: replace(location_candidate(), version_id="contains space"),
        lambda: replace(location_candidate(), version_id=""),
    ),
)
def test_location_rejects_non_s3_non_raw_traversal_and_bad_versions(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(ArtifactRegistryFailure):
        factory()


@pytest.mark.parametrize(
    "factory",
    (
        lambda: replace(provenance(), source="lowercase"),
        lambda: replace(provenance(), content_type="Application/JSON"),
        lambda: replace(provenance(), content_type="application/json; charset=utf-8"),
        lambda: replace(provenance(), byte_size=True),
        lambda: replace(provenance(), byte_size=0),
        lambda: replace(provenance(), acquired_at=ACQUIRED_AT.replace(tzinfo=None)),
    ),
)
def test_provenance_rejects_noncanonical_source_type_size_and_time(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(ArtifactRegistryFailure):
        factory()


class _StaticObserver:
    def __init__(self, observation: ArtifactObservation) -> None:
        self.observation = observation
        self.calls = 0

    def observe(self, candidate: ArtifactProvenance) -> ArtifactObservation:
        del candidate
        self.calls += 1
        return self.observation


def _plan_with(
    observation: ArtifactObservation,
) -> tuple[ArtifactRegistryReferencePlan, int]:
    observer = _StaticObserver(observation)
    service = ArtifactRegistryReferenceService(
        environment=RuntimeEnvironment.ENV_DEV,
        mode=RegistryMode.RECORDED_TEST_ONLY,
        observer=observer,
    )
    return service.plan(provenance()), observer.calls


@pytest.mark.parametrize(
    "mutator",
    (
        lambda value: replace(value, candidate_fingerprint="1" * 64),
        lambda value: replace(value, kind=ArtifactKind.RAW_PRIMARY_SOURCE),
        lambda value: replace(value, source="TEST_ONLY:OTHER_SOURCE"),
        lambda value: replace(value, acquired_at=ACQUIRED_AT + timedelta(seconds=1)),
        lambda value: replace(value, content_type="text/plain"),
        lambda value: replace(value, byte_size=value.byte_size + 1),
        lambda value: replace(value, digest=Sha256Digest("1" * 64)),
        lambda value: replace(
            value,
            location=ObjectLocationCandidate(
                scheme="s3",
                bucket="raos-raw",
                object_key="raw/test-only/other.json",
                version_id=value.location.version_id,
            ),
        ),
        lambda value: replace(
            value,
            location=ObjectLocationCandidate(
                scheme="s3",
                bucket="raos-raw",
                object_key=value.location.object_key,
                version_id="TEST_ONLY_VERSION_002",
            ),
        ),
    ),
)
def test_each_observed_provenance_tamper_is_rejected(
    mutator: Callable[[ArtifactObservation], ArtifactObservation],
) -> None:
    baseline = ArtifactObservation.from_synthetic(
        candidate=provenance(),
        content=SYNTHETIC_CONTENT,
    )
    plan, calls = _plan_with(mutator(baseline))
    assert plan.decision is RegistryDecision.REJECTED
    assert plan.integrity is IntegrityDecision.TAMPER_DETECTED
    assert plan.blockers == (RegistryBlocker.TAMPER_DETECTED,)
    assert calls == 1


def test_replay_is_stateless_and_returns_the_same_reference_plan() -> None:
    candidate = provenance()
    observer = observer_for(candidate)
    service = ArtifactRegistryReferenceService(
        environment=RuntimeEnvironment.CI,
        mode=RegistryMode.RECORDED_TEST_ONLY,
        observer=observer,
    )
    assert service.plan(candidate) == service.plan(candidate)
    assert not hasattr(observer, "history")


def test_duplicate_location_or_fingerprint_fixture_is_rejected() -> None:
    first = provenance()
    second = replace(first, source="TEST_ONLY:SECOND_SOURCE")
    with pytest.raises(ArtifactRegistryFailure):
        RecordedArtifactCandidateObserver(
            environment=RuntimeEnvironment.ENV_DEV,
            mode=RegistryMode.RECORDED_TEST_ONLY,
            fixture_capacity=2,
            fixtures=(
                RecordedArtifactFixture(
                    candidate=first, synthetic_content=SYNTHETIC_CONTENT
                ),
                RecordedArtifactFixture(
                    candidate=second, synthetic_content=SYNTHETIC_CONTENT
                ),
            ),
        )

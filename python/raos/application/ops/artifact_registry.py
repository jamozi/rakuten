"""Build a non-attesting ST-0601 reference plan from one observation."""

from __future__ import annotations

from typing import final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ops.artifact_registry import (
    ArtifactKind,
    ArtifactObservation,
    ArtifactProvenance,
    ArtifactRegistryFailureCode,
    ArtifactRegistryReferencePlan,
    ExecutionStatus,
    IntegrityDecision,
    MATCHING_BLOCKERS,
    RegistryBlocker,
    RegistryDecision,
    RegistryMode,
    fail_artifact_registry,
)
from raos.ports.artifact_registry import ArtifactCandidateObserver


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except TypeError:
        return False


@final
class ArtifactRegistryReferenceService:
    """Observe exactly once and produce no registration or storage action."""

    __slots__ = ("_observer",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        mode: RegistryMode,
        observer: ArtifactCandidateObserver,
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or mode is not RegistryMode.RECORDED_TEST_ONLY
            or type(mode) is not RegistryMode
            or not _implements(observer, ArtifactCandidateObserver)
        ):
            fail_artifact_registry()
        self._observer = observer

    def plan(self, candidate: ArtifactProvenance) -> ArtifactRegistryReferencePlan:
        if (
            type(candidate) is not ArtifactProvenance
            or candidate.kind is not ArtifactKind.RAW_PROVIDER_RESPONSE
        ):
            fail_artifact_registry()
        candidate_invalid = False
        try:
            candidate.digest.__post_init__()
            candidate.location.__post_init__()
            candidate.__post_init__()
        except Exception:
            candidate_invalid = True
        if candidate_invalid:
            fail_artifact_registry()
        observed: object = None
        unavailable = False
        try:
            observed = self._observer.observe(candidate)
        except Exception:
            unavailable = True
        if unavailable or type(observed) is not ArtifactObservation:
            fail_artifact_registry(ArtifactRegistryFailureCode.OBSERVATION_UNAVAILABLE)
        observation_invalid = False
        try:
            observed.digest.__post_init__()
            observed.location.__post_init__()
            observed.__post_init__()
        except Exception:
            observation_invalid = True
        if observation_invalid:
            fail_artifact_registry(ArtifactRegistryFailureCode.OBSERVATION_UNAVAILABLE)

        matches = (
            observed.candidate_fingerprint == candidate.fingerprint
            and observed.kind is candidate.kind
            and observed.source == candidate.source
            and observed.acquired_at == candidate.acquired_at
            and observed.content_type == candidate.content_type
            and observed.byte_size == candidate.byte_size
            and observed.digest == candidate.digest
            and observed.location == candidate.location
            and observed.location.version_id == candidate.location.version_id
            and all(
                status is ExecutionStatus.NOT_EXECUTED
                for status in (
                    observed.storage_execution,
                    observed.read_execution,
                    observed.write_execution,
                    observed.roundtrip_execution,
                    observed.attestation_execution,
                )
            )
        )
        return ArtifactRegistryReferencePlan(
            classification=(
                "SOURCE_BOUND_RECORDED_NON_ATTESTING_ARTIFACT_REGISTRY_REFERENCE_PLAN"
            ),
            decision=(
                RegistryDecision.NOT_READY if matches else RegistryDecision.REJECTED
            ),
            integrity=(
                IntegrityDecision.RECORDED_MATCH
                if matches
                else IntegrityDecision.TAMPER_DETECTED
            ),
            candidate_fingerprint=candidate.fingerprint,
            observation_fingerprint=observed.fingerprint,
            artifact_id=None,
            artifact_ref=None,
            retention=None,
            storage_execution=ExecutionStatus.NOT_EXECUTED,
            read_execution=ExecutionStatus.NOT_EXECUTED,
            write_execution=ExecutionStatus.NOT_EXECUTED,
            roundtrip_execution=ExecutionStatus.NOT_EXECUTED,
            attestation_execution=ExecutionStatus.NOT_EXECUTED,
            persistence_execution=ExecutionStatus.NOT_EXECUTED,
            actions=(),
            blockers=(
                MATCHING_BLOCKERS if matches else (RegistryBlocker.TAMPER_DETECTED,)
            ),
        )


__all__ = ["ArtifactRegistryReferenceService"]

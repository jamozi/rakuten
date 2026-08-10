"""Single observation-only inward port for the ST-0601 reference plan."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.ops.artifact_registry import ArtifactObservation, ArtifactProvenance


@runtime_checkable
class ArtifactCandidateObserver(Protocol):
    def observe(self, candidate: ArtifactProvenance) -> ArtifactObservation: ...


__all__ = ["ArtifactCandidateObserver"]

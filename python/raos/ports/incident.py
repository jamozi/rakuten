"""Inward storage port for the bounded ST-1406 incident command seam."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn, Protocol, SupportsIndex, final, runtime_checkable

from raos.domain.ops.incident import (
    IncidentCommand,
    IncidentFailureCode,
    IncidentFingerprint,
    IncidentMutationResult,
    IncidentState,
    fail_incident,
)


@final
@dataclass(frozen=True, slots=True, repr=False)
class IncidentStoreOutcome:
    """Immutable receipt distinguishing exact replay from fresh mutation."""

    result: IncidentMutationResult
    replayed: bool
    current_state: IncidentState
    command_fingerprint: IncidentFingerprint
    idempotency_fingerprint: IncidentFingerprint

    def __post_init__(self) -> None:
        if (
            type(self.result) is not IncidentMutationResult
            or type(self.replayed) is not bool
            or type(self.current_state) is not IncidentState
            or type(self.command_fingerprint) is not IncidentFingerprint
            or type(self.idempotency_fingerprint) is not IncidentFingerprint
        ):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        result_state = self.result.state
        if (
            self.current_state.incident_id != result_state.incident_id
            or self.current_state.display_id != result_state.display_id
            or self.current_state.severity is not result_state.severity
            or self.current_state.title != result_state.title
            or self.current_state.summary != result_state.summary
            or self.current_state.declared_at != result_state.declared_at
            or self.current_state.declared_by_principal_id
            != result_state.declared_by_principal_id
            or self.current_state.owner_principal_id != result_state.owner_principal_id
            or self.current_state.commander_principal_id
            != result_state.commander_principal_id
            or self.current_state.generation < result_state.generation
            or self.current_state.updated_at < result_state.updated_at
            or (
                self.current_state.generation == result_state.generation
                and self.current_state != result_state
            )
            or (not self.replayed and self.current_state != result_state)
        ):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("incident store outcome serialization is not supported")


@runtime_checkable
class IncidentStore(Protocol):
    """Atomically apply one generation-fenced, idempotent local command."""

    def apply(
        self,
        *,
        command: IncidentCommand,
        command_fingerprint: IncidentFingerprint,
        idempotency_fingerprint: IncidentFingerprint,
        minimum_generation: int,
        observed_state: IncidentState | None,
        allow_unobserved_incident: bool,
    ) -> IncidentStoreOutcome:
        """Return replay first; otherwise honor atomic admission and CAS."""

        ...


__all__ = ["IncidentStore", "IncidentStoreOutcome"]

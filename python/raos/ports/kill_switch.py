"""Inward ports for the bounded ST-1405 command and cache seams."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import NoReturn, Protocol, SupportsIndex, final, runtime_checkable
from uuid import UUID

from raos.domain.ops.kill_switch import (
    KillSwitchCacheSnapshot,
    KillSwitchChangeCommand,
    KillSwitchChangeResult,
    KillSwitchFailureCode,
    KillSwitchFingerprint,
    KillSwitchKind,
    KillSwitchState,
    fail_kill_switch,
)


@final
@dataclass(frozen=True, slots=True, repr=False)
class KillSwitchStoreOutcome:
    """Exact immutable receipt distinguishing replay from fresh mutation."""

    result: KillSwitchChangeResult
    replayed: bool
    current_state: KillSwitchState
    command_fingerprint: KillSwitchFingerprint
    idempotency_fingerprint: KillSwitchFingerprint

    def __post_init__(self) -> None:
        if (
            type(self.result) is not KillSwitchChangeResult
            or type(self.replayed) is not bool
            or type(self.current_state) is not KillSwitchState
            or type(self.command_fingerprint) is not KillSwitchFingerprint
            or type(self.idempotency_fingerprint) is not KillSwitchFingerprint
        ):
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        invalid = False
        try:
            result_state = self.result.state
            invalid = (
                self.current_state.key != result_state.key
                or self.current_state.switch_id != result_state.switch_id
                or self.current_state.generation < result_state.generation
                or self.current_state.changed_at < result_state.changed_at
                or (
                    self.current_state.generation == result_state.generation
                    and self.current_state != result_state
                )
                or (not self.replayed and self.current_state != result_state)
            )
        except Exception:
            invalid = True
        if invalid:
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)

    def __repr__(self) -> str:
        return "KillSwitchStoreOutcome(<redacted-kill-switch-value>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("kill-switch store outcome serialization is not supported")


@runtime_checkable
class KillSwitchStore(Protocol):
    """Atomically apply one generation-fenced, idempotent local command."""

    def compare_and_swap(
        self,
        *,
        command: KillSwitchChangeCommand,
        command_fingerprint: KillSwitchFingerprint,
        idempotency_fingerprint: KillSwitchFingerprint,
        changed_at: datetime,
        minimum_generation: int,
        observed_state: KillSwitchState | None,
        conflicting_switch_ids: frozenset[UUID],
        allow_unobserved_key: bool,
    ) -> KillSwitchStoreOutcome:
        """Return replay first, or atomically fence and admit a new command."""

        ...


@runtime_checkable
class KillSwitchCache(Protocol):
    """Read one kind-specific cache observation without performing I/O here."""

    def read_cache(
        self, *, switch_type: KillSwitchKind
    ) -> KillSwitchCacheSnapshot | None:
        """Return an explicit snapshot or absence for an unavailable cache."""

        ...


__all__ = ["KillSwitchCache", "KillSwitchStore", "KillSwitchStoreOutcome"]

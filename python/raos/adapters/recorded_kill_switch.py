"""Exact DEV/CI in-memory adapter for the bounded ST-1405 seam."""

from __future__ import annotations

from datetime import datetime
import hmac
from threading import Lock
from typing import NoReturn, SupportsIndex
from uuid import UUID, uuid5

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ops.kill_switch import (
    KillSwitchCacheEntry,
    KillSwitchCacheSnapshot,
    KillSwitchChangeCommand,
    KillSwitchChangeResult,
    KillSwitchEventIntent,
    KillSwitchFailureCode,
    KillSwitchFingerprint,
    KillSwitchKey,
    KillSwitchKind,
    KillSwitchState,
    MAX_KILL_SWITCH_CACHE_ENTRIES,
    MAX_KILL_SWITCH_GENERATION,
    fail_kill_switch,
    require_kill_switch_generation,
    require_kill_switch_utc,
)
from raos.ports.kill_switch import KillSwitchStoreOutcome


_ALLOWED_ENVIRONMENTS = frozenset({RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI})


def _require_local_environment(environment: object) -> RuntimeEnvironment:
    if (
        type(environment) is not RuntimeEnvironment
        or environment not in _ALLOWED_ENVIRONMENTS
    ):
        fail_kill_switch(KillSwitchFailureCode.DEVELOPMENT_ONLY)
    return environment


class RecordedKillSwitchAdapter:
    """Process-local CAS, idempotency, cache, and event-intent storage.

    The lock gives only same-process atomicity; it is not a database
    transaction.  No method can deliver the retained event intents.
    """

    __slots__ = (
        "_environment",
        "_event_namespace",
        "_capacity",
        "_states",
        "_idempotency",
        "_event_intents",
        "_cache_snapshots",
        "_lock",
    )

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        event_namespace: UUID,
        capacity: int,
        states: tuple[KillSwitchState, ...],
        cache_snapshots: tuple[KillSwitchCacheSnapshot, ...] = (),
    ) -> None:
        self._environment = _require_local_environment(environment)
        if (
            type(event_namespace) is not UUID
            or type(capacity) is not int
            or not 1 <= capacity <= MAX_KILL_SWITCH_CACHE_ENTRIES
        ):
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        if (
            type(states) is not tuple
            or type(cache_snapshots) is not tuple
            or len(states) > capacity
            or len(cache_snapshots) > len(KillSwitchKind)
        ):
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        if any(
            type(snapshot) is not KillSwitchCacheSnapshot
            for snapshot in cache_snapshots
        ):
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        if any(len(snapshot.entries) > capacity for snapshot in cache_snapshots):
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        if any(type(state) is not KillSwitchState for state in states):
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        keys = tuple(state.key for state in states)
        switch_ids = tuple(state.switch_id for state in states)
        cache_types = tuple(snapshot.switch_type for snapshot in cache_snapshots)
        if (
            len(keys) != len(set(keys))
            or len(switch_ids) != len(set(switch_ids))
            or len(cache_types) != len(set(cache_types))
        ):
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        self._event_namespace = event_namespace
        self._capacity = capacity
        self._states = {state.key: state for state in states}
        self._idempotency: dict[
            str, tuple[KillSwitchFingerprint, KillSwitchChangeResult]
        ] = {}
        self._event_intents: list[KillSwitchEventIntent] = []
        self._cache_snapshots = {
            snapshot.switch_type: snapshot for snapshot in cache_snapshots
        }
        self._lock = Lock()

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
        """Return replay first, or atomically fence and apply a fresh CAS."""

        self._guard()
        if (
            type(command) is not KillSwitchChangeCommand
            or type(command_fingerprint) is not KillSwitchFingerprint
            or type(idempotency_fingerprint) is not KillSwitchFingerprint
            or (
                observed_state is not None
                and type(observed_state) is not KillSwitchState
            )
            or type(conflicting_switch_ids) is not frozenset
            or any(type(value) is not UUID for value in conflicting_switch_ids)
            or type(allow_unobserved_key) is not bool
        ):
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        generation_floor = require_kill_switch_generation(minimum_generation)
        if observed_state is not None and (
            observed_state.key != command.key
            or observed_state.generation > generation_floor
        ):
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        observed_at = require_kill_switch_utc(changed_at)
        if not hmac.compare_digest(
            command.fingerprint().value, command_fingerprint.value
        ):
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)

        with self._lock:
            prior = self._idempotency.get(idempotency_fingerprint.value)
            if prior is not None:
                prior_fingerprint, prior_result = prior
                if hmac.compare_digest(
                    prior_fingerprint.value, command_fingerprint.value
                ):
                    replay_current = self._states.get(command.key)
                    if replay_current is None:
                        fail_kill_switch(KillSwitchFailureCode.STATE_MISSING)
                    return KillSwitchStoreOutcome(
                        result=prior_result,
                        replayed=True,
                        current_state=replay_current,
                        command_fingerprint=prior_fingerprint,
                        idempotency_fingerprint=idempotency_fingerprint,
                    )
                fail_kill_switch(KillSwitchFailureCode.IDEMPOTENCY_CONFLICT)

            if not allow_unobserved_key or (
                len(self._idempotency) >= self._capacity
                or len(self._event_intents) >= self._capacity
            ):
                fail_kill_switch(KillSwitchFailureCode.STORE_FAILURE)

            current = self._states.get(command.key)
            if current is None:
                fail_kill_switch(KillSwitchFailureCode.STATE_MISSING)
            if current.switch_id in conflicting_switch_ids:
                fail_kill_switch(KillSwitchFailureCode.STATE_CONFLICT)
            if current.generation < generation_floor:
                fail_kill_switch(KillSwitchFailureCode.GENERATION_CONFLICT)
            if observed_state is not None:
                if current.generation < observed_state.generation:
                    fail_kill_switch(KillSwitchFailureCode.GENERATION_CONFLICT)
                if current.generation == observed_state.generation:
                    if current != observed_state:
                        fail_kill_switch(KillSwitchFailureCode.STATE_CONFLICT)
                elif (
                    current.switch_id != observed_state.switch_id
                    or current.changed_at < observed_state.changed_at
                ):
                    fail_kill_switch(KillSwitchFailureCode.STATE_CONFLICT)
            if observed_at < current.changed_at:
                fail_kill_switch(KillSwitchFailureCode.STATE_CONFLICT)
            if command.expected_generation != current.generation:
                fail_kill_switch(KillSwitchFailureCode.GENERATION_CONFLICT)
            if command.engage is current.engaged:
                fail_kill_switch(KillSwitchFailureCode.STATE_CONFLICT)
            if current.generation == MAX_KILL_SWITCH_GENERATION:
                fail_kill_switch(KillSwitchFailureCode.GENERATION_CONFLICT)

            new_generation = current.generation + 1
            replacement = KillSwitchState(
                switch_id=current.switch_id,
                key=current.key,
                engaged=command.engage,
                generation=new_generation,
                reason=command.reason,
                changed_at=observed_at,
                incident_id=command.incident_id,
            )
            event_id = uuid5(
                self._event_namespace,
                f"{idempotency_fingerprint.value}:{command_fingerprint.value}",
            )
            intent = KillSwitchEventIntent(
                event_id=event_id,
                switch_id=current.switch_id,
                key=current.key,
                previous_engaged=current.engaged,
                new_engaged=replacement.engaged,
                previous_generation=current.generation,
                new_generation=replacement.generation,
                reason=command.reason,
                actor_principal_id=command.actor_principal_id,
                correlation_id=command.correlation_id,
                occurred_at=observed_at,
                incident_id=command.incident_id,
            )
            result = KillSwitchChangeResult(
                state=replacement,
                event_intent=intent,
            )
            outcome = KillSwitchStoreOutcome(
                result=result,
                replayed=False,
                current_state=replacement,
                command_fingerprint=command_fingerprint,
                idempotency_fingerprint=idempotency_fingerprint,
            )

            self._states[command.key] = replacement
            self._event_intents.append(intent)
            self._idempotency[idempotency_fingerprint.value] = (
                command_fingerprint,
                result,
            )
            return outcome

    def read_cache(
        self, *, switch_type: KillSwitchKind
    ) -> KillSwitchCacheSnapshot | None:
        """Return the configured cache while binding current generation floors."""

        self._guard()
        if type(switch_type) is not KillSwitchKind:
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        with self._lock:
            snapshot = self._cache_snapshots.get(switch_type)
            if snapshot is None:
                return None
            authoritative_keys = {
                state.switch_id: state.key for state in self._states.values()
            }
            for entry in snapshot.entries:
                cached = entry.state
                authoritative_key = authoritative_keys.get(cached.switch_id)
                if authoritative_key is not None and authoritative_key != cached.key:
                    fail_kill_switch(KillSwitchFailureCode.STATE_CONFLICT)
                current = self._states.get(cached.key)
                if current is None or cached.generation < current.generation:
                    continue
                if cached.generation == current.generation:
                    if cached != current:
                        fail_kill_switch(KillSwitchFailureCode.STATE_CONFLICT)
                elif (
                    cached.switch_id != current.switch_id
                    or cached.changed_at < current.changed_at
                ):
                    fail_kill_switch(KillSwitchFailureCode.STATE_CONFLICT)
            entries = tuple(
                KillSwitchCacheEntry(
                    state=entry.state,
                    minimum_generation=max(
                        entry.minimum_generation,
                        self._states.get(entry.state.key, entry.state).generation,
                    ),
                )
                for entry in snapshot.entries
            )
            return KillSwitchCacheSnapshot(
                switch_type=snapshot.switch_type,
                entries=entries,
                loaded_at=snapshot.loaded_at,
                fresh_until=snapshot.fresh_until,
                complete=snapshot.complete,
            )

    def install_cache_snapshot(self, snapshot: KillSwitchCacheSnapshot) -> None:
        """Replace one synthetic local cache observation without external I/O."""

        self._guard()
        if type(snapshot) is not KillSwitchCacheSnapshot:
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        if len(snapshot.entries) > self._capacity:
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        with self._lock:
            self._cache_snapshots[snapshot.switch_type] = snapshot

    def current_state(self, key: KillSwitchKey) -> KillSwitchState | None:
        """Inspect immutable local state for focused tests and development."""

        self._guard()
        if type(key) is not KillSwitchKey:
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        with self._lock:
            return self._states.get(key)

    def event_intents(self) -> tuple[KillSwitchEventIntent, ...]:
        """Inspect retained intents; this method performs no delivery."""

        self._guard()
        with self._lock:
            return tuple(self._event_intents)

    def _guard(self) -> None:
        _require_local_environment(self._environment)

    def __repr__(self) -> str:
        return "RecordedKillSwitchAdapter(<redacted-kill-switch-value>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded kill-switch adapter serialization is not supported")


__all__ = ["RecordedKillSwitchAdapter"]

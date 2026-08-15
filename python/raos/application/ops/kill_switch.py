"""Transport-neutral ST-1405 command and fail-safe eligibility services."""

from __future__ import annotations

from datetime import datetime, timedelta
import hmac
from threading import Lock
from typing import cast
from uuid import UUID

from raos.application.iam.step_up import StepUpGuard
from raos.domain.iam.authentication import SessionId
from raos.domain.ops.kill_switch import (
    KillSwitchCacheEntry,
    KillSwitchCacheSnapshot,
    KillSwitchChangeCommand,
    KillSwitchChangeResult,
    KillSwitchContext,
    KillSwitchEligibility,
    KillSwitchEligibilityCode,
    KillSwitchEventIntent,
    KillSwitchFailure,
    KillSwitchFailureCode,
    KillSwitchFingerprint,
    KillSwitchIdempotencyKey,
    KillSwitchKey,
    KillSwitchKind,
    KillSwitchReasonCode,
    KillSwitchState,
    MAX_KILL_SWITCH_CACHE_ENTRIES,
    fail_kill_switch,
    require_kill_switch_utc,
)
from raos.ports.kill_switch import (
    KillSwitchCache,
    KillSwitchStore,
    KillSwitchStoreOutcome,
)


_MAX_CACHE_AGE = timedelta(minutes=5)


def _supports(candidate: object, protocol: type[object]) -> bool:
    supported = False
    try:
        supported = isinstance(candidate, protocol)
    except Exception:
        pass
    return supported


def _copy_key(value: KillSwitchKey) -> KillSwitchKey:
    return KillSwitchKey(value.scope_type, value.scope_id, value.switch_type)


def _copy_reason(value: KillSwitchReasonCode) -> KillSwitchReasonCode:
    return KillSwitchReasonCode(value.event_value())


def _copy_state(value: KillSwitchState) -> KillSwitchState:
    return KillSwitchState(
        switch_id=value.switch_id,
        key=_copy_key(value.key),
        engaged=value.engaged,
        generation=value.generation,
        reason=_copy_reason(value.reason),
        changed_at=value.changed_at,
        incident_id=value.incident_id,
    )


def _copy_event(value: KillSwitchEventIntent) -> KillSwitchEventIntent:
    return KillSwitchEventIntent(
        event_id=value.event_id,
        switch_id=value.switch_id,
        key=_copy_key(value.key),
        previous_engaged=value.previous_engaged,
        new_engaged=value.new_engaged,
        previous_generation=value.previous_generation,
        new_generation=value.new_generation,
        reason=_copy_reason(value.reason),
        actor_principal_id=value.actor_principal_id,
        correlation_id=value.correlation_id,
        occurred_at=value.occurred_at,
        incident_id=value.incident_id,
    )


def _normalize_result(value: object) -> KillSwitchChangeResult | None:
    if type(value) is not KillSwitchChangeResult:
        return None
    normalized: KillSwitchChangeResult | None = None
    try:
        normalized = KillSwitchChangeResult(
            state=_copy_state(value.state),
            event_intent=_copy_event(value.event_intent),
        )
    except Exception:
        pass
    return normalized


def _normalize_outcome(value: object) -> KillSwitchStoreOutcome | None:
    if type(value) is not KillSwitchStoreOutcome:
        return None
    normalized: KillSwitchStoreOutcome | None = None
    try:
        normalized_result = _normalize_result(value.result)
        if normalized_result is None:
            return None
        normalized = KillSwitchStoreOutcome(
            result=normalized_result,
            replayed=value.replayed,
            current_state=_copy_state(value.current_state),
            command_fingerprint=KillSwitchFingerprint(value.command_fingerprint.value),
            idempotency_fingerprint=KillSwitchFingerprint(
                value.idempotency_fingerprint.value
            ),
        )
    except Exception:
        pass
    return normalized


def _normalize_snapshot(value: object) -> KillSwitchCacheSnapshot | None:
    if type(value) is not KillSwitchCacheSnapshot:
        return None
    normalized: KillSwitchCacheSnapshot | None = None
    try:
        entries = value.entries
        if type(entries) is not tuple or len(entries) > MAX_KILL_SWITCH_CACHE_ENTRIES:
            return None
        normalized = KillSwitchCacheSnapshot(
            switch_type=value.switch_type,
            entries=tuple(
                KillSwitchCacheEntry(
                    state=_copy_state(entry.state),
                    minimum_generation=entry.minimum_generation,
                )
                for entry in entries
            ),
            loaded_at=value.loaded_at,
            fresh_until=value.fresh_until,
            complete=value.complete,
        )
    except Exception:
        pass
    return normalized


def _decision(code: KillSwitchEligibilityCode) -> KillSwitchEligibility:
    return KillSwitchEligibility(
        allowed=code is KillSwitchEligibilityCode.ELIGIBLE,
        code=code,
    )


def _conflicts_with_observed_state(
    *, observed: KillSwitchState, candidate: KillSwitchState
) -> bool:
    if candidate.key != observed.key or candidate.generation < observed.generation:
        return True
    if candidate.generation == observed.generation:
        return candidate != observed
    return (
        candidate.switch_id != observed.switch_id
        or candidate.changed_at < observed.changed_at
    )


class KillSwitchRuntimeService:
    """Apply local commands and evaluate two independent fail-safe controls."""

    def __init__(
        self,
        *,
        store: KillSwitchStore,
        cache: KillSwitchCache,
        step_up_guard: StepUpGuard,
    ) -> None:
        if not _supports(cast(object, store), KillSwitchStore):
            raise TypeError("store must implement KillSwitchStore")
        if not _supports(cast(object, cache), KillSwitchCache):
            raise TypeError("cache must implement KillSwitchCache")
        if type(step_up_guard) is not StepUpGuard:
            raise TypeError("step_up_guard must be an exact StepUpGuard")
        self._store = store
        self._cache = cache
        self._step_up_guard = step_up_guard
        self._generation_floors: dict[KillSwitchKey, int] = {}
        self._observed_states: dict[KillSwitchKey, KillSwitchState] = {}
        self._observed_switch_keys: dict[UUID, KillSwitchKey] = {}
        self._floor_lock = Lock()

    def change(
        self,
        *,
        command: KillSwitchChangeCommand,
        idempotency_key: KillSwitchIdempotencyKey,
        session_id: SessionId,
        now: datetime,
    ) -> KillSwitchChangeResult:
        """Require ST-0402 assurance, then perform one exact atomic CAS."""

        if (
            type(command) is not KillSwitchChangeCommand
            or type(idempotency_key) is not KillSwitchIdempotencyKey
            or type(session_id) is not SessionId
        ):
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        observed_at = require_kill_switch_utc(now)

        step_up_failed = False
        try:
            self._step_up_guard.require(session_id=session_id, now=observed_at)
        except Exception:
            step_up_failed = True
        if step_up_failed:
            fail_kill_switch(KillSwitchFailureCode.STEP_UP_REQUIRED)

        try:
            command_fingerprint = command.fingerprint()
            idempotency_fingerprint = idempotency_key.fingerprint()
        except KillSwitchFailure:
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        except Exception:
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        with self._floor_lock:
            prior_state = self._observed_states.get(command.key)
            generation_floor = self._generation_floors.get(command.key, 0)
            tracked_keys = (
                set(self._generation_floors)
                | set(self._observed_states)
                | set(self._observed_switch_keys.values())
            )
            allow_unobserved_key = (
                command.key in tracked_keys
                or len(tracked_keys) < MAX_KILL_SWITCH_CACHE_ENTRIES
            )

            outcome: object = None
            failure: KillSwitchFailureCode | None = None
            try:
                outcome = self._store.compare_and_swap(
                    command=command,
                    command_fingerprint=command_fingerprint,
                    idempotency_fingerprint=idempotency_fingerprint,
                    changed_at=observed_at,
                    minimum_generation=generation_floor,
                    observed_state=(
                        _copy_state(prior_state) if prior_state is not None else None
                    ),
                    conflicting_switch_ids=frozenset(
                        switch_id
                        for switch_id, bound_key in self._observed_switch_keys.items()
                        if bound_key != command.key
                    ),
                    allow_unobserved_key=allow_unobserved_key,
                )
            except KillSwitchFailure as error:
                error_code: object = None
                try:
                    error_code = error.code
                except Exception:
                    pass
                failure = (
                    error_code
                    if type(error) is KillSwitchFailure
                    and type(error_code) is KillSwitchFailureCode
                    else KillSwitchFailureCode.STORE_FAILURE
                )
            except Exception:
                failure = KillSwitchFailureCode.STORE_FAILURE
            if failure is not None:
                fail_kill_switch(failure)
            normalized_outcome = _normalize_outcome(outcome)
            if normalized_outcome is None or not (
                hmac.compare_digest(
                    normalized_outcome.command_fingerprint.value,
                    command_fingerprint.value,
                )
                and hmac.compare_digest(
                    normalized_outcome.idempotency_fingerprint.value,
                    idempotency_fingerprint.value,
                )
            ):
                fail_kill_switch(KillSwitchFailureCode.STORE_FAILURE)
            normalized = normalized_outcome.result
            intent = normalized.event_intent
            if (
                intent.key != command.key
                or intent.new_engaged is not command.engage
                or intent.previous_generation != command.expected_generation
                or intent.new_generation != command.expected_generation + 1
                or intent.reason != command.reason
                or intent.actor_principal_id != command.actor_principal_id
                or intent.correlation_id != command.correlation_id
                or intent.incident_id != command.incident_id
            ):
                fail_kill_switch(KillSwitchFailureCode.STORE_FAILURE)
            if not normalized_outcome.replayed and intent.occurred_at != observed_at:
                fail_kill_switch(KillSwitchFailureCode.STORE_FAILURE)
            current_state = normalized_outcome.current_state
            bound_key = self._observed_switch_keys.get(current_state.switch_id)
            floor_conflict = current_state.generation < generation_floor
            fresh_floor_not_advanced = (
                not normalized_outcome.replayed
                and current_state.generation <= generation_floor
            )
            state_conflict = prior_state is not None and _conflicts_with_observed_state(
                observed=prior_state,
                candidate=current_state,
            )
            fresh_not_advanced = (
                not normalized_outcome.replayed
                and prior_state is not None
                and current_state.generation <= prior_state.generation
            )
            fresh_prestate_conflict = (
                not normalized_outcome.replayed
                and prior_state is not None
                and command.expected_generation == prior_state.generation
                and intent.previous_engaged is not prior_state.engaged
            )
            identity_conflict = bound_key is not None and bound_key != current_state.key
            if normalized_outcome.replayed and (
                not allow_unobserved_key
                or floor_conflict
                or state_conflict
                or identity_conflict
            ):
                return normalized
            if (
                not allow_unobserved_key
                or floor_conflict
                or fresh_floor_not_advanced
                or state_conflict
                or fresh_not_advanced
                or fresh_prestate_conflict
                or identity_conflict
            ):
                fail_kill_switch(KillSwitchFailureCode.STORE_FAILURE)
            self._generation_floors[current_state.key] = max(
                self._generation_floors.get(current_state.key, 0),
                current_state.generation,
            )
            if prior_state is None or current_state.generation > prior_state.generation:
                self._observed_states[current_state.key] = _copy_state(current_state)
            self._observed_switch_keys[current_state.switch_id] = _copy_key(
                current_state.key
            )
        return normalized

    def publication_commands_allowed(
        self, *, context: KillSwitchContext, now: datetime
    ) -> KillSwitchEligibility:
        """Fail safe before any ST-0905 publication command could execute."""

        return self._evaluate(
            switch_type=KillSwitchKind.PUBLICATION,
            context=context,
            now=now,
        )

    def affiliate_cta_eligible(
        self, *, context: KillSwitchContext, now: datetime
    ) -> KillSwitchEligibility:
        """Fail safe before an affiliate CTA is made eligible for rendering."""

        return self._evaluate(
            switch_type=KillSwitchKind.AFFILIATE_LINK,
            context=context,
            now=now,
        )

    def _evaluate(
        self,
        *,
        switch_type: KillSwitchKind,
        context: KillSwitchContext,
        now: datetime,
    ) -> KillSwitchEligibility:
        if type(context) is not KillSwitchContext:
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        observed_at = require_kill_switch_utc(now)

        candidate: object = None
        cache_failed = False
        try:
            candidate = self._cache.read_cache(switch_type=switch_type)
        except Exception:
            cache_failed = True
        if cache_failed or candidate is None:
            return _decision(KillSwitchEligibilityCode.CACHE_UNAVAILABLE)
        snapshot = _normalize_snapshot(candidate)
        if snapshot is None or snapshot.switch_type is not switch_type:
            return _decision(KillSwitchEligibilityCode.CACHE_MALFORMED)
        if observed_at < snapshot.loaded_at:
            return _decision(KillSwitchEligibilityCode.CACHE_MALFORMED)
        if (
            observed_at >= snapshot.fresh_until
            or observed_at - snapshot.loaded_at >= _MAX_CACHE_AGE
        ):
            return _decision(KillSwitchEligibilityCode.CACHE_STALE)
        if not snapshot.complete:
            return _decision(KillSwitchEligibilityCode.CACHE_INCOMPLETE)

        entries = {entry.state.key: entry for entry in snapshot.entries}
        required_keys = context.required_keys(switch_type)
        if any(key not in entries for key in required_keys):
            return _decision(KillSwitchEligibilityCode.CACHE_ENTRY_MISSING)

        required_entries = tuple(entries[key] for key in required_keys)
        with self._floor_lock:
            tracked_keys = (
                set(self._generation_floors)
                | set(self._observed_states)
                | set(self._observed_switch_keys.values())
            )
            snapshot_keys = set(entries)
            if (
                len(tracked_keys | snapshot_keys) > MAX_KILL_SWITCH_CACHE_ENTRIES
                or len(
                    set(self._observed_switch_keys)
                    | {entry.state.switch_id for entry in snapshot.entries}
                )
                > MAX_KILL_SWITCH_CACHE_ENTRIES
            ):
                return _decision(KillSwitchEligibilityCode.CACHE_DOWNGRADED)
            snapshot_floors = {
                entry.state.key: max(
                    self._generation_floors.get(entry.state.key, 0),
                    entry.minimum_generation,
                )
                for entry in snapshot.entries
            }
            self._generation_floors.update(snapshot_floors)
            for entry in snapshot.entries:
                bound_key = self._observed_switch_keys.get(entry.state.switch_id)
                if bound_key is not None and bound_key != entry.state.key:
                    return _decision(KillSwitchEligibilityCode.CACHE_DOWNGRADED)
            for entry in snapshot.entries:
                required_floor = snapshot_floors[entry.state.key]
                if entry.state.generation < required_floor:
                    return _decision(KillSwitchEligibilityCode.CACHE_DOWNGRADED)
                observed_state = self._observed_states.get(entry.state.key)
                if observed_state is None:
                    continue
                if _conflicts_with_observed_state(
                    observed=observed_state,
                    candidate=entry.state,
                ):
                    return _decision(KillSwitchEligibilityCode.CACHE_DOWNGRADED)
            for entry in snapshot.entries:
                self._generation_floors[entry.state.key] = max(
                    self._generation_floors.get(entry.state.key, 0),
                    entry.state.generation,
                )
                prior_state = self._observed_states.get(entry.state.key)
                if (
                    prior_state is None
                    or entry.state.generation > prior_state.generation
                ):
                    self._observed_states[entry.state.key] = _copy_state(entry.state)
            for entry in snapshot.entries:
                self._observed_switch_keys[entry.state.switch_id] = _copy_key(
                    entry.state.key
                )

        if any(entry.state.engaged for entry in required_entries):
            return _decision(KillSwitchEligibilityCode.ENGAGED)
        return _decision(KillSwitchEligibilityCode.ELIGIBLE)


__all__ = ["KillSwitchRuntimeService"]

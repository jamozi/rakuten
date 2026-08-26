"""Command, concurrency, step-up, and event-intent tests for ST-1405."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Callable, cast
from uuid import UUID

import pytest

from .support import (
    CHANGE_REASON,
    CONTEXT,
    EVENT_NAMESPACE,
    NOW,
    all_keys,
    idempotency_key,
    make_adapter,
    make_command,
    make_publication_states_at_capacity,
    make_runtime,
    make_session,
    make_snapshot,
    make_states,
    make_step_up_guard,
)
from raos.adapters.recorded_kill_switch import RecordedKillSwitchAdapter
from raos.application.ops.kill_switch import KillSwitchRuntimeService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authentication import SessionId
from raos.domain.ops.kill_switch import (
    KillSwitchChangeCommand,
    KillSwitchCacheEntry,
    KillSwitchEligibilityCode,
    KillSwitchFailure,
    KillSwitchFailureCode,
    KillSwitchFingerprint,
    KillSwitchIdempotencyKey,
    KillSwitchKind,
    KillSwitchReasonCode,
    KillSwitchScopeType,
    KillSwitchState,
    MAX_KILL_SWITCH_CACHE_ENTRIES,
    MAX_KILL_SWITCH_GENERATION,
)
from raos.generated.contracts.jp_raos_ops_kill_switch_changed_v1 import (
    Schema as KillSwitchChangedSchema,
)
from raos.ports.kill_switch import KillSwitchStore, KillSwitchStoreOutcome


def _assert_failure(
    code: KillSwitchFailureCode, operation: Callable[[], object]
) -> KillSwitchFailure:
    with pytest.raises(KillSwitchFailure) as captured:
        operation()
    assert captured.value.code is code
    return captured.value


def test_closed_switch_and_scope_sets_and_default_fail_safe_surface() -> None:
    assert {value.value for value in KillSwitchKind} == {
        "PUBLICATION",
        "AFFILIATE_LINK",
    }
    assert {value.value for value in KillSwitchScopeType} == {
        "GLOBAL",
        "SITE",
        "CATEGORY",
        "ARTICLE",
    }
    runtime, _, _ = make_runtime()

    publication = runtime.publication_commands_allowed(context=CONTEXT, now=NOW)
    affiliate = runtime.affiliate_cta_eligible(context=CONTEXT, now=NOW)

    assert publication.allowed is True
    assert publication.code is KillSwitchEligibilityCode.ELIGIBLE
    assert affiliate.allowed is True
    assert affiliate.code is KillSwitchEligibilityCode.ELIGIBLE


def test_change_is_generation_fenced_and_creates_one_unpublished_contract_intent() -> (
    None
):
    states = make_states()
    adapter = make_adapter(states=states)
    runtime, _, session = make_runtime(adapter=adapter)
    key = all_keys(KillSwitchKind.PUBLICATION)[0]
    command = make_command(key=key)

    result = runtime.change(
        command=command,
        idempotency_key=idempotency_key(),
        session_id=session.session_id,
        now=NOW,
    )

    assert result.state.engaged is True
    assert result.state.generation == 1
    assert result.event_intent.previous_engaged is False
    assert result.event_intent.new_engaged is True
    assert result.event_intent.previous_generation == 0
    assert result.event_intent.new_generation == 1
    assert adapter.current_state(key) == result.state
    assert adapter.event_intents() == (result.event_intent,)

    validated = KillSwitchChangedSchema.model_validate(
        result.event_intent.contract_envelope()
    )
    assert validated.type == "jp.raos.ops.kill_switch_changed.v1"
    assert validated.producer == "ops"
    assert validated.data is not None
    assert validated.data.switch_type == "PUBLICATION"
    assert validated.data.new_generation == 1
    assert validated.data.reason == CHANGE_REASON.event_value()

    stale_cache = runtime.publication_commands_allowed(context=CONTEXT, now=NOW)
    independent_affiliate = runtime.affiliate_cta_eligible(context=CONTEXT, now=NOW)
    assert stale_cache.code is KillSwitchEligibilityCode.CACHE_DOWNGRADED
    assert independent_affiliate.code is KillSwitchEligibilityCode.ELIGIBLE

    refreshed_states = tuple(
        result.state if state.key == key else state for state in states
    )
    adapter.install_cache_snapshot(
        make_snapshot(
            KillSwitchKind.PUBLICATION,
            refreshed_states,
            loaded_at=NOW,
        )
    )
    engaged = runtime.publication_commands_allowed(
        context=CONTEXT,
        now=NOW + timedelta(seconds=1),
    )
    assert engaged.allowed is False
    assert engaged.code is KillSwitchEligibilityCode.ENGAGED
    assert adapter.event_intents() == (result.event_intent,)


def test_successful_change_fences_a_separate_stale_cache_projection() -> None:
    key = all_keys(KillSwitchKind.PUBLICATION)[0]
    store_states = make_states()
    conflicting_cache_states = make_states(generations={key: 1})
    store = make_adapter(states=store_states)
    cache = make_adapter(states=conflicting_cache_states)
    _, _, session = make_runtime(adapter=store)
    runtime = KillSwitchRuntimeService(
        store=store,
        cache=cache,
        step_up_guard=make_step_up_guard(session),
    )

    runtime.change(
        command=make_command(),
        idempotency_key=idempotency_key(),
        session_id=session.session_id,
        now=NOW,
    )

    decision = runtime.publication_commands_allowed(context=CONTEXT, now=NOW)
    assert decision.allowed is False
    assert decision.code is KillSwitchEligibilityCode.CACHE_DOWNGRADED


def test_conflicting_command_result_cannot_replace_observed_engaged_state() -> None:
    target = all_keys(KillSwitchKind.PUBLICATION)[0]
    observed_states = make_states(
        engaged={target: True},
        generations={target: 1},
    )
    store_states = make_states(engaged={target: True})
    store = make_adapter(states=store_states)
    cache = make_adapter(
        states=(),
        snapshots=tuple(
            make_snapshot(switch_type, observed_states)
            for switch_type in KillSwitchKind
        ),
    )
    _, _, session = make_runtime(adapter=store)
    runtime = KillSwitchRuntimeService(
        store=store,
        cache=cache,
        step_up_guard=make_step_up_guard(session),
    )
    observed = runtime.publication_commands_allowed(context=CONTEXT, now=NOW)
    assert observed.code is KillSwitchEligibilityCode.ENGAGED
    original_store_state = store.current_state(target)
    assert original_store_state is not None

    release = make_command(
        key=target,
        engage=False,
        expected_generation=0,
        reason=KillSwitchReasonCode("INCIDENT_RECOVERY_ACTION"),
    )
    _assert_failure(
        KillSwitchFailureCode.GENERATION_CONFLICT,
        lambda: runtime.change(
            command=release,
            idempotency_key=idempotency_key(),
            session_id=session.session_id,
            now=NOW,
        ),
    )
    assert store.current_state(target) == original_store_state
    assert store.event_intents() == ()

    contradictory_states = make_states(generations={target: 1})
    cache.install_cache_snapshot(
        make_snapshot(
            KillSwitchKind.PUBLICATION,
            contradictory_states,
            loaded_at=NOW,
        )
    )
    retained = runtime.publication_commands_allowed(
        context=CONTEXT,
        now=NOW + timedelta(seconds=1),
    )
    assert retained.allowed is False
    assert retained.code is KillSwitchEligibilityCode.CACHE_DOWNGRADED


def test_cross_key_switch_id_binding_fences_store_before_mutation() -> None:
    publication_key = all_keys(KillSwitchKind.PUBLICATION)[0]
    affiliate_key = all_keys(KillSwitchKind.AFFILIATE_LINK)[0]
    cache_states = make_states()
    publication_id = next(
        state.switch_id for state in cache_states if state.key == publication_key
    )
    store_states = tuple(
        replace(
            state,
            switch_id=UUID("00000000-0000-0000-0000-000000099406"),
        )
        if state.key == publication_key
        else replace(state, switch_id=publication_id)
        if state.key == affiliate_key
        else state
        for state in cache_states
    )
    store = make_adapter(states=store_states)
    cache = make_adapter(states=cache_states)
    _, _, session = make_runtime(adapter=store)
    runtime = KillSwitchRuntimeService(
        store=store,
        cache=cache,
        step_up_guard=make_step_up_guard(session),
    )
    observed = runtime.publication_commands_allowed(context=CONTEXT, now=NOW)
    assert observed.code is KillSwitchEligibilityCode.ELIGIBLE
    original = store.current_state(affiliate_key)
    assert original is not None

    _assert_failure(
        KillSwitchFailureCode.STATE_CONFLICT,
        lambda: runtime.change(
            command=make_command(key=affiliate_key),
            idempotency_key=idempotency_key("st1405-command-0099"),
            session_id=session.session_id,
            now=NOW,
        ),
    )

    assert store.current_state(affiliate_key) == original
    assert store.event_intents() == ()


def test_same_idempotency_and_command_returns_original_without_duplicate_intent() -> (
    None
):
    runtime, adapter, session = make_runtime()
    command = make_command()
    key = idempotency_key()

    first = runtime.change(
        command=command,
        idempotency_key=key,
        session_id=session.session_id,
        now=NOW,
    )
    second = runtime.change(
        command=command,
        idempotency_key=key,
        session_id=session.session_id,
        now=NOW + timedelta(seconds=1),
    )

    assert second == first
    assert second.state.changed_at == NOW
    assert second.event_intent.event_id == first.event_intent.event_id
    assert adapter.event_intents() == (first.event_intent,)


def test_same_idempotency_and_command_replays_under_regressed_explicit_clock() -> None:
    adapter = make_adapter()
    command = make_command()
    key = idempotency_key()
    first = adapter.compare_and_swap(
        command=command,
        command_fingerprint=command.fingerprint(),
        idempotency_fingerprint=key.fingerprint(),
        changed_at=NOW,
        minimum_generation=0,
        observed_state=None,
        conflicting_switch_ids=frozenset(),
        allow_unobserved_key=True,
    ).result
    _, _, session = make_runtime(adapter=adapter)
    runtime = KillSwitchRuntimeService(
        store=adapter,
        cache=adapter,
        step_up_guard=make_step_up_guard(session),
    )

    replay = runtime.change(
        command=command,
        idempotency_key=key,
        session_id=session.session_id,
        now=NOW - timedelta(microseconds=1),
    )

    assert replay == first
    assert adapter.event_intents() == (first.event_intent,)


def test_historical_idempotent_replay_returns_original_after_newer_generation() -> None:
    runtime, adapter, session = make_runtime()
    engage = make_command()
    engage_key = idempotency_key()
    first = runtime.change(
        command=engage,
        idempotency_key=engage_key,
        session_id=session.session_id,
        now=NOW,
    )
    release = make_command(
        engage=False,
        expected_generation=1,
        reason=KillSwitchReasonCode("INCIDENT_RECOVERY_ACTION"),
    )
    second = runtime.change(
        command=release,
        idempotency_key=idempotency_key("st1405-command-0002"),
        session_id=session.session_id,
        now=NOW + timedelta(seconds=1),
    )

    replay = runtime.change(
        command=engage,
        idempotency_key=engage_key,
        session_id=session.session_id,
        now=NOW + timedelta(seconds=2),
    )

    assert replay == first
    assert adapter.current_state(engage.key) == second.state
    assert adapter.event_intents() == (first.event_intent, second.event_intent)


def test_fresh_service_observes_newer_state_then_replays_historical_result() -> None:
    states = make_states()
    runtime, adapter, session = make_runtime(adapter=make_adapter(states=states))
    engage = make_command()
    engage_key = idempotency_key()
    first = runtime.change(
        command=engage,
        idempotency_key=engage_key,
        session_id=session.session_id,
        now=NOW,
    )
    release = make_command(
        engage=False,
        expected_generation=1,
        reason=KillSwitchReasonCode("INCIDENT_RECOVERY_ACTION"),
    )
    second = runtime.change(
        command=release,
        idempotency_key=idempotency_key("st1405-command-0002"),
        session_id=session.session_id,
        now=NOW + timedelta(seconds=1),
    )
    refreshed = tuple(
        second.state if state.key == second.state.key else state for state in states
    )
    adapter.install_cache_snapshot(
        make_snapshot(
            KillSwitchKind.PUBLICATION,
            refreshed,
            loaded_at=NOW + timedelta(seconds=1),
        )
    )
    fresh_runtime, _, fresh_session = make_runtime(adapter=adapter)
    observed = fresh_runtime.publication_commands_allowed(
        context=CONTEXT,
        now=NOW + timedelta(seconds=2),
    )
    assert observed.code is KillSwitchEligibilityCode.ELIGIBLE

    replay = fresh_runtime.change(
        command=engage,
        idempotency_key=engage_key,
        session_id=fresh_session.session_id,
        now=NOW + timedelta(seconds=3),
    )

    assert replay == first
    assert adapter.current_state(engage.key) == second.state
    assert adapter.event_intents() == (first.event_intent, second.event_intent)

    _assert_failure(
        KillSwitchFailureCode.GENERATION_CONFLICT,
        lambda: fresh_runtime.change(
            command=engage,
            idempotency_key=idempotency_key("st1405-command-0003"),
            session_id=fresh_session.session_id,
            now=NOW + timedelta(seconds=4),
        ),
    )
    assert adapter.current_state(engage.key) == second.state
    assert adapter.event_intents() == (first.event_intent, second.event_intent)


def test_replay_binds_current_store_state_before_separate_stale_cache() -> None:
    initial_states = make_states()
    original_runtime, store, original_session = make_runtime(
        adapter=make_adapter(states=initial_states)
    )
    engage = make_command()
    engage_key = idempotency_key()
    first = original_runtime.change(
        command=engage,
        idempotency_key=engage_key,
        session_id=original_session.session_id,
        now=NOW,
    )
    second = original_runtime.change(
        command=make_command(
            engage=False,
            expected_generation=1,
            reason=KillSwitchReasonCode("INCIDENT_RECOVERY_ACTION"),
        ),
        idempotency_key=idempotency_key("st1405-command-0002"),
        session_id=original_session.session_id,
        now=NOW + timedelta(seconds=1),
    )
    stale_cache = make_adapter(states=initial_states)
    _, _, fresh_session = make_runtime(adapter=store)
    fresh_runtime = KillSwitchRuntimeService(
        store=store,
        cache=stale_cache,
        step_up_guard=make_step_up_guard(fresh_session),
    )

    replay = fresh_runtime.change(
        command=engage,
        idempotency_key=engage_key,
        session_id=fresh_session.session_id,
        now=NOW + timedelta(seconds=2),
    )
    stale = fresh_runtime.publication_commands_allowed(
        context=CONTEXT,
        now=NOW + timedelta(seconds=2),
    )

    assert replay == first
    assert stale.allowed is False
    assert stale.code is KillSwitchEligibilityCode.CACHE_DOWNGRADED
    assert store.current_state(engage.key) == second.state
    assert store.event_intents() == (first.event_intent, second.event_intent)


def test_replay_preserves_a_stronger_separate_cache_observation() -> None:
    initial_states = make_states()
    original_runtime, store, original_session = make_runtime(
        adapter=make_adapter(states=initial_states)
    )
    engage = make_command()
    engage_key = idempotency_key()
    first = original_runtime.change(
        command=engage,
        idempotency_key=engage_key,
        session_id=original_session.session_id,
        now=NOW,
    )
    second = original_runtime.change(
        command=make_command(
            engage=False,
            expected_generation=1,
            reason=KillSwitchReasonCode("INCIDENT_RECOVERY_ACTION"),
        ),
        idempotency_key=idempotency_key("st1405-command-0002"),
        session_id=original_session.session_id,
        now=NOW + timedelta(seconds=1),
    )
    ahead_states = make_states(generations={engage.key: 3})
    ahead_cache = make_adapter(states=ahead_states)
    _, _, fresh_session = make_runtime(adapter=store)
    fresh_runtime = KillSwitchRuntimeService(
        store=store,
        cache=ahead_cache,
        step_up_guard=make_step_up_guard(fresh_session),
    )
    observed = fresh_runtime.publication_commands_allowed(
        context=CONTEXT,
        now=NOW + timedelta(seconds=2),
    )
    assert observed.code is KillSwitchEligibilityCode.ELIGIBLE

    replay = fresh_runtime.change(
        command=engage,
        idempotency_key=engage_key,
        session_id=fresh_session.session_id,
        now=NOW + timedelta(seconds=3),
    )
    ahead_cache.install_cache_snapshot(
        make_snapshot(
            KillSwitchKind.PUBLICATION,
            initial_states,
            loaded_at=NOW + timedelta(seconds=3),
        )
    )
    stale = fresh_runtime.publication_commands_allowed(
        context=CONTEXT,
        now=NOW + timedelta(seconds=4),
    )

    assert replay == first
    assert stale.code is KillSwitchEligibilityCode.CACHE_DOWNGRADED
    assert store.current_state(engage.key) == second.state
    assert store.event_intents() == (first.event_intent, second.event_intent)


def test_same_idempotency_key_with_different_command_fails_closed() -> None:
    runtime, adapter, session = make_runtime()
    command = make_command()
    key = idempotency_key()
    original = runtime.change(
        command=command,
        idempotency_key=key,
        session_id=session.session_id,
        now=NOW,
    )
    different = make_command(reason=KillSwitchReasonCode("OWNER_SAFETY_ACTION"))

    _assert_failure(
        KillSwitchFailureCode.IDEMPOTENCY_CONFLICT,
        lambda: runtime.change(
            command=different,
            idempotency_key=key,
            session_id=session.session_id,
            now=NOW + timedelta(seconds=1),
        ),
    )
    assert adapter.current_state(command.key) == original.state
    assert adapter.event_intents() == (original.event_intent,)


def test_same_idempotency_key_with_different_correlation_fails_closed() -> None:
    runtime, adapter, session = make_runtime()
    command = make_command()
    key = idempotency_key()
    original = runtime.change(
        command=command,
        idempotency_key=key,
        session_id=session.session_id,
        now=NOW,
    )
    different = make_command(
        correlation_id=UUID("00000000-0000-0000-0000-000000009405")
    )

    assert different.fingerprint() != command.fingerprint()
    _assert_failure(
        KillSwitchFailureCode.IDEMPOTENCY_CONFLICT,
        lambda: runtime.change(
            command=different,
            idempotency_key=key,
            session_id=session.session_id,
            now=NOW + timedelta(seconds=1),
        ),
    )
    assert adapter.current_state(command.key) == original.state
    assert adapter.event_intents() == (original.event_intent,)


def test_old_or_duplicate_generation_never_replaces_newer_engaged_state() -> None:
    runtime, adapter, session = make_runtime()
    command = make_command()
    engaged = runtime.change(
        command=command,
        idempotency_key=idempotency_key(),
        session_id=session.session_id,
        now=NOW,
    )

    old_release = make_command(
        engage=False,
        expected_generation=0,
        reason=KillSwitchReasonCode("INCIDENT_RECOVERY_ACTION"),
    )
    _assert_failure(
        KillSwitchFailureCode.GENERATION_CONFLICT,
        lambda: runtime.change(
            command=old_release,
            idempotency_key=idempotency_key("st1405-command-0002"),
            session_id=session.session_id,
            now=NOW + timedelta(seconds=1),
        ),
    )

    duplicate_engage = make_command(engage=True, expected_generation=1)
    _assert_failure(
        KillSwitchFailureCode.STATE_CONFLICT,
        lambda: runtime.change(
            command=duplicate_engage,
            idempotency_key=idempotency_key("st1405-command-0003"),
            session_id=session.session_id,
            now=NOW + timedelta(seconds=2),
        ),
    )
    assert adapter.current_state(command.key) == engaged.state
    assert len(adapter.event_intents()) == 1


def test_atomic_same_key_compare_and_swap_has_one_winner() -> None:
    adapter = make_adapter()
    command = make_command()

    def attempt(value: str) -> KillSwitchStoreOutcome | KillSwitchFailureCode:
        try:
            return adapter.compare_and_swap(
                command=command,
                command_fingerprint=command.fingerprint(),
                idempotency_fingerprint=idempotency_key(value).fingerprint(),
                changed_at=NOW,
                minimum_generation=0,
                observed_state=None,
                conflicting_switch_ids=frozenset(),
                allow_unobserved_key=True,
            )
        except KillSwitchFailure as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(
            executor.map(
                attempt,
                ("st1405-concurrent-0001", "st1405-concurrent-0002"),
            )
        )

    assert sum(type(result) is KillSwitchStoreOutcome for result in results) == 1
    assert results.count(KillSwitchFailureCode.GENERATION_CONFLICT) == 1
    state = adapter.current_state(command.key)
    assert state is not None
    assert state.generation == 1
    assert len(adapter.event_intents()) == 1


def test_adapter_rejects_a_command_fingerprint_mismatch_before_mutation() -> None:
    adapter = make_adapter()
    command = make_command()

    _assert_failure(
        KillSwitchFailureCode.INVALID_ARGUMENT,
        lambda: adapter.compare_and_swap(
            command=command,
            command_fingerprint=KillSwitchFingerprint("f" * 64),
            idempotency_fingerprint=idempotency_key().fingerprint(),
            changed_at=NOW,
            minimum_generation=0,
            observed_state=None,
            conflicting_switch_ids=frozenset(),
            allow_unobserved_key=True,
        ),
    )
    state = adapter.current_state(command.key)
    assert state is not None
    assert state.generation == 0
    assert adapter.event_intents() == ()


def test_adapter_rejects_backdated_change_but_allows_same_timestamp() -> None:
    states = make_states(changed_at=NOW)
    adapter = make_adapter(states=states, snapshots=())
    command = make_command()
    key = idempotency_key()

    _assert_failure(
        KillSwitchFailureCode.STATE_CONFLICT,
        lambda: adapter.compare_and_swap(
            command=command,
            command_fingerprint=command.fingerprint(),
            idempotency_fingerprint=key.fingerprint(),
            changed_at=NOW - timedelta(microseconds=1),
            minimum_generation=0,
            observed_state=None,
            conflicting_switch_ids=frozenset(),
            allow_unobserved_key=True,
        ),
    )
    assert adapter.current_state(command.key) == next(
        state for state in states if state.key == command.key
    )
    assert adapter.event_intents() == ()

    result = adapter.compare_and_swap(
        command=command,
        command_fingerprint=command.fingerprint(),
        idempotency_fingerprint=key.fingerprint(),
        changed_at=NOW,
        minimum_generation=0,
        observed_state=None,
        conflicting_switch_ids=frozenset(),
        allow_unobserved_key=True,
    ).result
    assert result.state.changed_at == NOW
    assert adapter.event_intents() == (result.event_intent,)


@pytest.mark.parametrize(
    "invalid_generation",
    (1 << 63, 10**5000),
    ids=("above-signed-bigint", "huge-integer"),
)
def test_generation_values_are_bounded_to_signed_bigint(
    invalid_generation: int,
) -> None:
    _assert_failure(
        KillSwitchFailureCode.INVALID_ARGUMENT,
        lambda: make_command(expected_generation=invalid_generation),
    )
    _assert_failure(
        KillSwitchFailureCode.INVALID_ARGUMENT,
        lambda: replace(make_states()[0], generation=invalid_generation),
    )
    _assert_failure(
        KillSwitchFailureCode.INVALID_ARGUMENT,
        lambda: KillSwitchCacheEntry(
            state=make_states()[0],
            minimum_generation=invalid_generation,
        ),
    )
    seed_adapter = make_adapter()
    seed_command = make_command()
    event = seed_adapter.compare_and_swap(
        command=seed_command,
        command_fingerprint=seed_command.fingerprint(),
        idempotency_fingerprint=idempotency_key().fingerprint(),
        changed_at=NOW,
        minimum_generation=0,
        observed_state=None,
        conflicting_switch_ids=frozenset(),
        allow_unobserved_key=True,
    ).result.event_intent
    _assert_failure(
        KillSwitchFailureCode.INVALID_ARGUMENT,
        lambda: replace(event, previous_generation=invalid_generation),
    )
    _assert_failure(
        KillSwitchFailureCode.INVALID_ARGUMENT,
        lambda: replace(event, new_generation=invalid_generation),
    )


def test_max_generation_cannot_overflow_or_mutate_state() -> None:
    target = all_keys(KillSwitchKind.PUBLICATION)[0]
    states = make_states(generations={target: MAX_KILL_SWITCH_GENERATION})
    adapter = make_adapter(states=states, snapshots=())
    current = adapter.current_state(target)
    assert current is not None
    command = make_command(expected_generation=MAX_KILL_SWITCH_GENERATION)

    _assert_failure(
        KillSwitchFailureCode.GENERATION_CONFLICT,
        lambda: adapter.compare_and_swap(
            command=command,
            command_fingerprint=command.fingerprint(),
            idempotency_fingerprint=idempotency_key().fingerprint(),
            changed_at=NOW,
            minimum_generation=MAX_KILL_SWITCH_GENERATION,
            observed_state=current,
            conflicting_switch_ids=frozenset(),
            allow_unobserved_key=True,
        ),
    )

    assert adapter.current_state(target) == current
    assert adapter.event_intents() == ()


def test_adapter_rejects_an_out_of_range_generation_floor_before_mutation() -> None:
    adapter = make_adapter()
    command = make_command()
    current = adapter.current_state(command.key)

    _assert_failure(
        KillSwitchFailureCode.INVALID_ARGUMENT,
        lambda: adapter.compare_and_swap(
            command=command,
            command_fingerprint=command.fingerprint(),
            idempotency_fingerprint=idempotency_key().fingerprint(),
            changed_at=NOW,
            minimum_generation=1 << 63,
            observed_state=current,
            conflicting_switch_ids=frozenset(),
            allow_unobserved_key=True,
        ),
    )

    assert adapter.current_state(command.key) == current
    assert adapter.event_intents() == ()


def test_step_up_failure_prevents_state_change_and_event_intent() -> None:
    runtime, adapter, _ = make_runtime()
    unknown_session = SessionId.from_bytes(bytes(range(32)))

    failure = _assert_failure(
        KillSwitchFailureCode.STEP_UP_REQUIRED,
        lambda: runtime.change(
            command=make_command(),
            idempotency_key=idempotency_key(),
            session_id=unknown_session,
            now=NOW,
        ),
    )

    state = adapter.current_state(make_command().key)
    assert state is not None
    assert state.generation == 0
    assert adapter.event_intents() == ()
    assert failure.__cause__ is None
    assert failure.__context__ is None


def test_expires_at_is_rejected_and_time_does_not_release_an_engaged_switch() -> None:
    _assert_failure(
        KillSwitchFailureCode.EXPIRES_AT_UNSUPPORTED,
        lambda: make_command(expires_at=NOW + timedelta(minutes=30)),
    )

    states = make_states()
    adapter = make_adapter(states=states)
    runtime, _, session = make_runtime(adapter=adapter)
    result = runtime.change(
        command=make_command(),
        idempotency_key=idempotency_key(),
        session_id=session.session_id,
        now=NOW,
    )
    refreshed = tuple(
        result.state if state.key == result.state.key else state for state in states
    )
    later_at = NOW + timedelta(hours=1)
    adapter.install_cache_snapshot(
        make_snapshot(
            KillSwitchKind.PUBLICATION,
            refreshed,
            loaded_at=later_at,
            fresh_until=later_at + timedelta(minutes=4),
        )
    )

    later = runtime.publication_commands_allowed(
        context=CONTEXT,
        now=later_at,
    )
    assert later.code is KillSwitchEligibilityCode.ENGAGED
    assert adapter.current_state(result.state.key) == result.state


@pytest.mark.parametrize(
    "environment",
    (
        RuntimeEnvironment.INTEGRATION,
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.RECOVERY,
        RuntimeEnvironment.PRODUCTION,
    ),
)
def test_adapter_is_restricted_to_exact_dev_and_ci(
    environment: RuntimeEnvironment,
) -> None:
    _assert_failure(
        KillSwitchFailureCode.DEVELOPMENT_ONLY,
        lambda: RecordedKillSwitchAdapter(
            environment=environment,
            event_namespace=EVENT_NAMESPACE,
            capacity=MAX_KILL_SWITCH_CACHE_ENTRIES,
            states=make_states(),
        ),
    )
    RecordedKillSwitchAdapter(
        environment=RuntimeEnvironment.CI,
        event_namespace=EVENT_NAMESPACE,
        capacity=MAX_KILL_SWITCH_CACHE_ENTRIES,
        states=make_states(),
    )
    _assert_failure(
        KillSwitchFailureCode.DEVELOPMENT_ONLY,
        lambda: RecordedKillSwitchAdapter(
            environment=cast(RuntimeEnvironment, "ENV-DEV"),
            event_namespace=EVENT_NAMESPACE,
            capacity=MAX_KILL_SWITCH_CACHE_ENTRIES,
            states=make_states(),
        ),
    )


@pytest.mark.parametrize("capacity", (0, -1, True, 10_001))
def test_adapter_requires_a_bounded_exact_capacity(capacity: object) -> None:
    _assert_failure(
        KillSwitchFailureCode.INVALID_ARGUMENT,
        lambda: RecordedKillSwitchAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            event_namespace=EVENT_NAMESPACE,
            capacity=cast(int, capacity),
            states=(),
        ),
    )


def test_adapter_capacity_bounds_initial_state_and_cache_snapshots() -> None:
    states = make_states()
    publication_snapshot = make_snapshot(KillSwitchKind.PUBLICATION, states)

    _assert_failure(
        KillSwitchFailureCode.INVALID_ARGUMENT,
        lambda: RecordedKillSwitchAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            event_namespace=EVENT_NAMESPACE,
            capacity=1,
            states=states[:2],
        ),
    )
    _assert_failure(
        KillSwitchFailureCode.INVALID_ARGUMENT,
        lambda: RecordedKillSwitchAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            event_namespace=EVENT_NAMESPACE,
            capacity=1,
            states=(),
            cache_snapshots=(publication_snapshot,),
        ),
    )
    _assert_failure(
        KillSwitchFailureCode.INVALID_ARGUMENT,
        lambda: RecordedKillSwitchAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            event_namespace=EVENT_NAMESPACE,
            capacity=MAX_KILL_SWITCH_CACHE_ENTRIES,
            states=(),
            cache_snapshots=(publication_snapshot,) * 3,
        ),
    )

    adapter = RecordedKillSwitchAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=1,
        states=(states[0],),
    )
    _assert_failure(
        KillSwitchFailureCode.INVALID_ARGUMENT,
        lambda: adapter.install_cache_snapshot(publication_snapshot),
    )
    assert adapter.read_cache(switch_type=KillSwitchKind.PUBLICATION) is None


def test_adapter_full_capacity_replays_first_and_never_evicts() -> None:
    target_state = make_states()[0]
    adapter = RecordedKillSwitchAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=1,
        states=(target_state,),
    )
    engage = make_command(key=target_state.key)
    engage_key = idempotency_key()
    first = adapter.compare_and_swap(
        command=engage,
        command_fingerprint=engage.fingerprint(),
        idempotency_fingerprint=engage_key.fingerprint(),
        changed_at=NOW,
        minimum_generation=0,
        observed_state=None,
        conflicting_switch_ids=frozenset(),
        allow_unobserved_key=True,
    )
    retained_state = adapter.current_state(target_state.key)
    retained_intents = adapter.event_intents()

    release = make_command(
        key=target_state.key,
        engage=False,
        expected_generation=1,
        reason=KillSwitchReasonCode("INCIDENT_RECOVERY_ACTION"),
    )
    _assert_failure(
        KillSwitchFailureCode.STORE_FAILURE,
        lambda: adapter.compare_and_swap(
            command=release,
            command_fingerprint=release.fingerprint(),
            idempotency_fingerprint=idempotency_key(
                "st1405-capacity-0002"
            ).fingerprint(),
            changed_at=NOW + timedelta(seconds=1),
            minimum_generation=1,
            observed_state=retained_state,
            conflicting_switch_ids=frozenset(),
            allow_unobserved_key=True,
        ),
    )
    replay = adapter.compare_and_swap(
        command=engage,
        command_fingerprint=engage.fingerprint(),
        idempotency_fingerprint=engage_key.fingerprint(),
        changed_at=NOW + timedelta(seconds=1),
        minimum_generation=1,
        observed_state=retained_state,
        conflicting_switch_ids=frozenset(),
        allow_unobserved_key=False,
    )

    assert replay.replayed is True
    assert replay.result == first.result
    assert adapter.current_state(target_state.key) == retained_state
    assert adapter.event_intents() == retained_intents


class _ExplodingStore(KillSwitchStore):
    def __init__(self, canary: str) -> None:
        self._canary = canary

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
        del (
            command_fingerprint,
            idempotency_fingerprint,
            minimum_generation,
            observed_state,
            conflicting_switch_ids,
            allow_unobserved_key,
        )
        raise RuntimeError(
            f"{self._canary}:{command.reason.event_value()}:{changed_at}"
        )


class _ReturningStore(KillSwitchStore):
    def __init__(self, value: object) -> None:
        self._value = value

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
        del (
            command,
            command_fingerprint,
            idempotency_fingerprint,
            changed_at,
            minimum_generation,
            observed_state,
            conflicting_switch_ids,
            allow_unobserved_key,
        )
        return cast(KillSwitchStoreOutcome, self._value)


class _RaisingStore(KillSwitchStore):
    def __init__(self, error: BaseException) -> None:
        self._error = error

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
        del (
            command,
            command_fingerprint,
            idempotency_fingerprint,
            changed_at,
            minimum_generation,
            observed_state,
            conflicting_switch_ids,
            allow_unobserved_key,
        )
        raise self._error


def test_service_capacity_preserves_replay_and_rejects_fresh_outcomes() -> None:
    capacity_states = make_publication_states_at_capacity()
    capacity_cache = make_adapter(
        states=(),
        snapshots=(make_snapshot(KillSwitchKind.PUBLICATION, capacity_states),),
        capacity=MAX_KILL_SWITCH_CACHE_ENTRIES,
    )
    target_key = all_keys(KillSwitchKind.AFFILIATE_LINK)[0]
    target_state = next(state for state in make_states() if state.key == target_key)
    command = make_command(key=target_key)
    replay_key = idempotency_key("st1405-capacity-replay")
    replay_store = RecordedKillSwitchAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=1,
        states=(target_state,),
    )
    original = replay_store.compare_and_swap(
        command=command,
        command_fingerprint=command.fingerprint(),
        idempotency_fingerprint=replay_key.fingerprint(),
        changed_at=NOW,
        minimum_generation=0,
        observed_state=None,
        conflicting_switch_ids=frozenset(),
        allow_unobserved_key=True,
    )
    session = make_session()
    replay_runtime = KillSwitchRuntimeService(
        store=replay_store,
        cache=capacity_cache,
        step_up_guard=make_step_up_guard(session),
    )
    assert (
        replay_runtime.publication_commands_allowed(context=CONTEXT, now=NOW).code
        is KillSwitchEligibilityCode.ELIGIBLE
    )

    replay = replay_runtime.change(
        command=command,
        idempotency_key=replay_key,
        session_id=session.session_id,
        now=NOW + timedelta(seconds=1),
    )
    assert replay == original.result
    assert replay_store.event_intents() == (original.result.event_intent,)

    fresh_store = RecordedKillSwitchAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=1,
        states=(target_state,),
    )
    fresh_runtime = KillSwitchRuntimeService(
        store=fresh_store,
        cache=capacity_cache,
        step_up_guard=make_step_up_guard(session),
    )
    assert (
        fresh_runtime.publication_commands_allowed(context=CONTEXT, now=NOW).code
        is KillSwitchEligibilityCode.ELIGIBLE
    )
    _assert_failure(
        KillSwitchFailureCode.STORE_FAILURE,
        lambda: fresh_runtime.change(
            command=command,
            idempotency_key=idempotency_key("st1405-capacity-fresh1"),
            session_id=session.session_id,
            now=NOW + timedelta(seconds=1),
        ),
    )
    assert fresh_store.current_state(target_key) == target_state
    assert fresh_store.event_intents() == ()

    hostile_key = idempotency_key("st1405-capacity-hostile")
    seed_store = RecordedKillSwitchAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=1,
        states=(target_state,),
    )
    hostile_outcome = seed_store.compare_and_swap(
        command=command,
        command_fingerprint=command.fingerprint(),
        idempotency_fingerprint=hostile_key.fingerprint(),
        changed_at=NOW + timedelta(seconds=1),
        minimum_generation=0,
        observed_state=None,
        conflicting_switch_ids=frozenset(),
        allow_unobserved_key=True,
    )
    hostile_runtime = KillSwitchRuntimeService(
        store=_ReturningStore(hostile_outcome),
        cache=capacity_cache,
        step_up_guard=make_step_up_guard(session),
    )
    assert (
        hostile_runtime.publication_commands_allowed(context=CONTEXT, now=NOW).code
        is KillSwitchEligibilityCode.ELIGIBLE
    )
    _assert_failure(
        KillSwitchFailureCode.STORE_FAILURE,
        lambda: hostile_runtime.change(
            command=command,
            idempotency_key=hostile_key,
            session_id=session.session_id,
            now=NOW + timedelta(seconds=1),
        ),
    )


def test_malformed_or_wrongly_bound_store_outcome_fails_closed() -> None:
    command = make_command()
    key = idempotency_key()
    seed_adapter = make_adapter()
    valid = seed_adapter.compare_and_swap(
        command=command,
        command_fingerprint=command.fingerprint(),
        idempotency_fingerprint=key.fingerprint(),
        changed_at=NOW,
        minimum_generation=0,
        observed_state=None,
        conflicting_switch_ids=frozenset(),
        allow_unobserved_key=True,
    )
    forged = KillSwitchStoreOutcome(
        result=valid.result,
        replayed=True,
        current_state=valid.current_state,
        command_fingerprint=KillSwitchFingerprint("f" * 64),
        idempotency_fingerprint=valid.idempotency_fingerprint,
    )
    corrupted = KillSwitchStoreOutcome(
        result=valid.result,
        replayed=True,
        current_state=valid.current_state,
        command_fingerprint=valid.command_fingerprint,
        idempotency_fingerprint=valid.idempotency_fingerprint,
    )
    object.__delattr__(corrupted, "result")

    for value in (object(), forged, corrupted):
        cache = make_adapter()
        session = make_session()
        runtime = KillSwitchRuntimeService(
            store=cast(KillSwitchStore, _ReturningStore(value)),
            cache=cache,
            step_up_guard=make_step_up_guard(session),
        )
        _assert_failure(
            KillSwitchFailureCode.STORE_FAILURE,
            lambda: runtime.change(
                command=command,
                idempotency_key=key,
                session_id=session.session_id,
                now=NOW,
            ),
        )
        assert cache.event_intents() == ()

    malformed_failure = KillSwitchFailure(KillSwitchFailureCode.STATE_CONFLICT)
    object.__delattr__(malformed_failure, "_code")
    cache = make_adapter()
    session = make_session()
    runtime = KillSwitchRuntimeService(
        store=cast(KillSwitchStore, _RaisingStore(malformed_failure)),
        cache=cache,
        step_up_guard=make_step_up_guard(session),
    )
    _assert_failure(
        KillSwitchFailureCode.STORE_FAILURE,
        lambda: runtime.change(
            command=command,
            idempotency_key=key,
            session_id=session.session_id,
            now=NOW,
        ),
    )
    assert cache.event_intents() == ()


def test_fresh_store_outcome_cannot_bypass_a_higher_generation_floor() -> None:
    target = all_keys(KillSwitchKind.PUBLICATION)[0]
    command = make_command(expected_generation=4)
    key = idempotency_key()
    seed_states = make_states(generations={target: 4})
    seed_store = make_adapter(states=seed_states, snapshots=())
    seed_current = seed_store.current_state(target)
    assert seed_current is not None
    forged_fresh = seed_store.compare_and_swap(
        command=command,
        command_fingerprint=command.fingerprint(),
        idempotency_fingerprint=key.fingerprint(),
        changed_at=NOW,
        minimum_generation=4,
        observed_state=seed_current,
        conflicting_switch_ids=frozenset(),
        allow_unobserved_key=True,
    )
    cache_states = make_states(generations={target: 5})
    cache = make_adapter(
        states=cache_states,
        snapshots=(
            make_snapshot(
                KillSwitchKind.PUBLICATION,
                cache_states,
                minimum_generations={target: 10},
            ),
            make_snapshot(KillSwitchKind.AFFILIATE_LINK, cache_states),
        ),
    )
    session = make_session()
    runtime = KillSwitchRuntimeService(
        store=cast(KillSwitchStore, _ReturningStore(forged_fresh)),
        cache=cache,
        step_up_guard=make_step_up_guard(session),
    )
    floor_observation = runtime.publication_commands_allowed(
        context=CONTEXT,
        now=NOW,
    )
    assert floor_observation.code is KillSwitchEligibilityCode.CACHE_DOWNGRADED

    _assert_failure(
        KillSwitchFailureCode.STORE_FAILURE,
        lambda: runtime.change(
            command=command,
            idempotency_key=key,
            session_id=session.session_id,
            now=NOW,
        ),
    )
    assert cache.event_intents() == ()


def test_fresh_store_outcome_must_strictly_advance_generation_floor() -> None:
    target = all_keys(KillSwitchKind.PUBLICATION)[0]
    command = make_command(expected_generation=9)
    key = idempotency_key()
    seed_states = make_states(generations={target: 9})
    seed_store = make_adapter(states=seed_states, snapshots=())
    seed_current = seed_store.current_state(target)
    assert seed_current is not None
    floor_equal_outcome = seed_store.compare_and_swap(
        command=command,
        command_fingerprint=command.fingerprint(),
        idempotency_fingerprint=key.fingerprint(),
        changed_at=NOW,
        minimum_generation=9,
        observed_state=seed_current,
        conflicting_switch_ids=frozenset(),
        allow_unobserved_key=True,
    )
    assert floor_equal_outcome.current_state.generation == 10
    cache_states = make_states(generations={target: 5})
    cache = make_adapter(
        states=cache_states,
        snapshots=(
            make_snapshot(
                KillSwitchKind.PUBLICATION,
                cache_states,
                minimum_generations={target: 10},
            ),
            make_snapshot(KillSwitchKind.AFFILIATE_LINK, cache_states),
        ),
    )
    session = make_session()
    runtime = KillSwitchRuntimeService(
        store=cast(KillSwitchStore, _ReturningStore(floor_equal_outcome)),
        cache=cache,
        step_up_guard=make_step_up_guard(session),
    )
    floor_observation = runtime.publication_commands_allowed(
        context=CONTEXT,
        now=NOW,
    )
    assert floor_observation.code is KillSwitchEligibilityCode.CACHE_DOWNGRADED

    _assert_failure(
        KillSwitchFailureCode.STORE_FAILURE,
        lambda: runtime.change(
            command=command,
            idempotency_key=key,
            session_id=session.session_id,
            now=NOW,
        ),
    )
    assert cache.event_intents() == ()


def test_fresh_store_outcome_must_advance_an_observed_exact_state() -> None:
    command = make_command()
    key = idempotency_key()
    seed_store = make_adapter()
    fresh_outcome = seed_store.compare_and_swap(
        command=command,
        command_fingerprint=command.fingerprint(),
        idempotency_fingerprint=key.fingerprint(),
        changed_at=NOW,
        minimum_generation=0,
        observed_state=None,
        conflicting_switch_ids=frozenset(),
        allow_unobserved_key=True,
    )
    initial_states = make_states()
    observed_states = tuple(
        fresh_outcome.current_state if state.key == command.key else state
        for state in initial_states
    )
    cache = make_adapter(
        states=(),
        snapshots=tuple(
            make_snapshot(switch_type, observed_states, loaded_at=NOW)
            for switch_type in KillSwitchKind
        ),
    )
    session = make_session()
    runtime = KillSwitchRuntimeService(
        store=cast(KillSwitchStore, _ReturningStore(fresh_outcome)),
        cache=cache,
        step_up_guard=make_step_up_guard(session),
    )
    observed = runtime.publication_commands_allowed(context=CONTEXT, now=NOW)
    assert observed.code is KillSwitchEligibilityCode.ENGAGED

    _assert_failure(
        KillSwitchFailureCode.STORE_FAILURE,
        lambda: runtime.change(
            command=command,
            idempotency_key=key,
            session_id=session.session_id,
            now=NOW,
        ),
    )
    assert cache.event_intents() == ()


def test_fresh_store_outcome_must_match_known_prestate_engagement() -> None:
    target = all_keys(KillSwitchKind.PUBLICATION)[0]
    command = make_command(expected_generation=1)
    key = idempotency_key()
    contradictory_prestate = make_states(generations={target: 1})
    seed_store = make_adapter(states=contradictory_prestate, snapshots=())
    seed_current = seed_store.current_state(target)
    assert seed_current is not None
    hostile_outcome = seed_store.compare_and_swap(
        command=command,
        command_fingerprint=command.fingerprint(),
        idempotency_fingerprint=key.fingerprint(),
        changed_at=NOW,
        minimum_generation=1,
        observed_state=seed_current,
        conflicting_switch_ids=frozenset(),
        allow_unobserved_key=True,
    )
    assert hostile_outcome.result.event_intent.previous_engaged is False
    observed_states = make_states(
        engaged={target: True},
        generations={target: 1},
    )
    cache = make_adapter(
        states=(),
        snapshots=tuple(
            make_snapshot(switch_type, observed_states)
            for switch_type in KillSwitchKind
        ),
    )
    session = make_session()
    runtime = KillSwitchRuntimeService(
        store=cast(KillSwitchStore, _ReturningStore(hostile_outcome)),
        cache=cache,
        step_up_guard=make_step_up_guard(session),
    )
    observed = runtime.publication_commands_allowed(context=CONTEXT, now=NOW)
    assert observed.code is KillSwitchEligibilityCode.ENGAGED

    _assert_failure(
        KillSwitchFailureCode.STORE_FAILURE,
        lambda: runtime.change(
            command=command,
            idempotency_key=key,
            session_id=session.session_id,
            now=NOW,
        ),
    )
    assert cache.event_intents() == ()


def test_store_exception_and_values_are_redacted_from_diagnostics() -> None:
    canary = "SYNTHETIC_PRIVATE_EXCEPTION_CANARY"
    _, adapter, session = make_runtime()
    runtime = KillSwitchRuntimeService(
        store=cast(KillSwitchStore, _ExplodingStore(canary)),
        cache=adapter,
        step_up_guard=make_step_up_guard(session),
    )

    failure = _assert_failure(
        KillSwitchFailureCode.STORE_FAILURE,
        lambda: runtime.change(
            command=make_command(),
            idempotency_key=KillSwitchIdempotencyKey("st1405-command-0004"),
            session_id=session.session_id,
            now=NOW,
        ),
    )
    diagnostics = f"{failure!s} {failure!r} {failure.args!r}"
    assert canary not in diagnostics
    assert CHANGE_REASON.event_value() not in diagnostics
    assert failure.__cause__ is None
    assert failure.__context__ is None


@pytest.mark.parametrize(
    "invalid_now",
    (
        datetime(2026, 8, 15, 12, 0),
        datetime(2026, 8, 15, 12, 0, tzinfo=timezone(timedelta(hours=9))),
    ),
)
def test_command_requires_exact_aware_utc(invalid_now: datetime) -> None:
    runtime, _, session = make_runtime()
    _assert_failure(
        KillSwitchFailureCode.INVALID_ARGUMENT,
        lambda: runtime.change(
            command=make_command(),
            idempotency_key=idempotency_key(),
            session_id=session.session_id,
            now=invalid_now,
        ),
    )

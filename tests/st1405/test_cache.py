"""Fail-safe cache and independent-control tests for ST-1405."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from typing import Callable, cast
from uuid import UUID

import pytest

from conftest import (
    ARTICLE_ID,
    CATEGORY_ID,
    CONTEXT,
    NOW,
    SITE_ID,
    all_keys,
    make_adapter,
    make_publication_states_at_capacity,
    make_runtime,
    make_session,
    make_snapshot,
    make_states,
    make_step_up_guard,
)
from raos.application.ops.kill_switch import KillSwitchRuntimeService
from raos.domain.ops.kill_switch import (
    KillSwitchCacheSnapshot,
    KillSwitchContext,
    KillSwitchEligibilityCode,
    KillSwitchFailure,
    KillSwitchFailureCode,
    KillSwitchKey,
    KillSwitchKind,
    KillSwitchScopeType,
    MAX_KILL_SWITCH_CACHE_ENTRIES,
)
from raos.ports.kill_switch import KillSwitchCache


def _assert_failure(
    code: KillSwitchFailureCode, operation: Callable[[], object]
) -> KillSwitchFailure:
    with pytest.raises(KillSwitchFailure) as captured:
        operation()
    assert captured.value.code is code
    return captured.value


class _StaticCache:
    def __init__(self, value: object) -> None:
        self._value = value

    def read_cache(
        self, *, switch_type: KillSwitchKind
    ) -> KillSwitchCacheSnapshot | None:
        del switch_type
        return cast(KillSwitchCacheSnapshot | None, self._value)


class _ExplodingCache:
    def __init__(self, canary: str) -> None:
        self._canary = canary

    def read_cache(
        self, *, switch_type: KillSwitchKind
    ) -> KillSwitchCacheSnapshot | None:
        raise RuntimeError(f"{self._canary}:{switch_type.value}")


def _runtime_with_cache(cache: object) -> KillSwitchRuntimeService:
    adapter = make_adapter()
    session = make_session()
    return KillSwitchRuntimeService(
        store=adapter,
        cache=cast(KillSwitchCache, cache),
        step_up_guard=make_step_up_guard(session),
    )


@pytest.mark.parametrize(
    ("cache", "expected"),
    (
        (_StaticCache(None), KillSwitchEligibilityCode.CACHE_UNAVAILABLE),
        (_StaticCache(object()), KillSwitchEligibilityCode.CACHE_MALFORMED),
        (
            _ExplodingCache("SYNTHETIC_CACHE_EXCEPTION_CANARY"),
            KillSwitchEligibilityCode.CACHE_UNAVAILABLE,
        ),
    ),
)
def test_missing_malformed_and_unavailable_cache_disable_publication(
    cache: object,
    expected: KillSwitchEligibilityCode,
) -> None:
    decision = _runtime_with_cache(cache).publication_commands_allowed(
        context=CONTEXT,
        now=NOW,
    )
    assert decision.allowed is False
    assert decision.code is expected
    assert "SYNTHETIC_CACHE_EXCEPTION_CANARY" not in f"{decision!s} {decision!r}"


def test_incomplete_publication_cache_does_not_disable_independent_affiliate() -> None:
    states = make_states()
    adapter = make_adapter(
        states=states,
        snapshots=(
            make_snapshot(KillSwitchKind.PUBLICATION, states, complete=False),
            make_snapshot(KillSwitchKind.AFFILIATE_LINK, states, complete=True),
        ),
    )
    runtime, _, _ = make_runtime(adapter=adapter)

    publication = runtime.publication_commands_allowed(context=CONTEXT, now=NOW)
    affiliate = runtime.affiliate_cta_eligible(context=CONTEXT, now=NOW)

    assert publication.code is KillSwitchEligibilityCode.CACHE_INCOMPLETE
    assert affiliate.code is KillSwitchEligibilityCode.ELIGIBLE


def test_stale_and_future_cache_observations_disable() -> None:
    states = make_states(changed_at=NOW - timedelta(hours=3))
    stale = make_snapshot(
        KillSwitchKind.PUBLICATION,
        states,
        loaded_at=NOW - timedelta(hours=2),
        fresh_until=NOW - timedelta(seconds=1),
    )
    future = make_snapshot(
        KillSwitchKind.PUBLICATION,
        states,
        loaded_at=NOW + timedelta(seconds=1),
        fresh_until=NOW + timedelta(hours=1),
    )

    stale_decision = _runtime_with_cache(
        _StaticCache(stale)
    ).publication_commands_allowed(
        context=CONTEXT,
        now=NOW,
    )
    future_decision = _runtime_with_cache(
        _StaticCache(future)
    ).publication_commands_allowed(context=CONTEXT, now=NOW)

    assert stale_decision.code is KillSwitchEligibilityCode.CACHE_STALE
    assert future_decision.code is KillSwitchEligibilityCode.CACHE_MALFORMED


def test_declared_future_freshness_cannot_exceed_five_minute_cache_age() -> None:
    states = make_states(changed_at=NOW - timedelta(minutes=6))
    overlong = make_snapshot(
        KillSwitchKind.PUBLICATION,
        states,
        loaded_at=NOW - timedelta(minutes=5),
        fresh_until=NOW + timedelta(days=20),
    )

    decision = _runtime_with_cache(_StaticCache(overlong)).publication_commands_allowed(
        context=CONTEXT, now=NOW
    )

    assert decision.allowed is False
    assert decision.code is KillSwitchEligibilityCode.CACHE_STALE


def test_cache_age_check_is_bounded_near_datetime_max() -> None:
    loaded_at = datetime.max.replace(tzinfo=UTC) - timedelta(minutes=1)
    states = make_states(changed_at=loaded_at)
    near_max = make_snapshot(
        KillSwitchKind.PUBLICATION,
        states,
        loaded_at=loaded_at,
        fresh_until=datetime.max.replace(tzinfo=UTC),
    )

    decision = _runtime_with_cache(_StaticCache(near_max)).publication_commands_allowed(
        context=CONTEXT, now=loaded_at
    )

    assert decision.allowed is True
    assert decision.code is KillSwitchEligibilityCode.ELIGIBLE


def test_missing_applicable_scope_disables_only_the_requested_kind() -> None:
    states = make_states()
    publication = make_snapshot(KillSwitchKind.PUBLICATION, states)
    publication_missing_article = KillSwitchCacheSnapshot(
        switch_type=KillSwitchKind.PUBLICATION,
        entries=publication.entries[:-1],
        loaded_at=publication.loaded_at,
        fresh_until=publication.fresh_until,
        complete=True,
    )
    adapter = make_adapter(
        states=states,
        snapshots=(
            publication_missing_article,
            make_snapshot(KillSwitchKind.AFFILIATE_LINK, states),
        ),
    )
    runtime, _, _ = make_runtime(adapter=adapter)

    publication_decision = runtime.publication_commands_allowed(
        context=CONTEXT,
        now=NOW,
    )
    affiliate_decision = runtime.affiliate_cta_eligible(context=CONTEXT, now=NOW)

    assert publication_decision.code is KillSwitchEligibilityCode.CACHE_ENTRY_MISSING
    assert affiliate_decision.code is KillSwitchEligibilityCode.ELIGIBLE


def test_explicit_and_previously_observed_generation_downgrades_disable() -> None:
    publication_keys = all_keys(KillSwitchKind.PUBLICATION)
    generation_two = {key: 2 for key in publication_keys}
    current_states = make_states(generations=generation_two)
    adapter = make_adapter(states=current_states)
    runtime, _, _ = make_runtime(adapter=adapter)

    first = runtime.publication_commands_allowed(context=CONTEXT, now=NOW)
    assert first.code is KillSwitchEligibilityCode.ELIGIBLE

    older_states = make_states(generations={key: 1 for key in publication_keys})
    adapter.install_cache_snapshot(
        make_snapshot(
            KillSwitchKind.PUBLICATION,
            older_states,
            loaded_at=NOW,
            minimum_generations={key: 1 for key in publication_keys},
        )
    )
    downgraded = runtime.publication_commands_allowed(
        context=CONTEXT,
        now=NOW + timedelta(seconds=1),
    )
    assert downgraded.code is KillSwitchEligibilityCode.CACHE_DOWNGRADED

    explicit_states = make_states()
    explicit = make_snapshot(
        KillSwitchKind.PUBLICATION,
        explicit_states,
        minimum_generations={key: 1 for key in publication_keys},
    )
    explicit_decision = _runtime_with_cache(
        _StaticCache(explicit)
    ).publication_commands_allowed(context=CONTEXT, now=NOW)
    assert explicit_decision.code is KillSwitchEligibilityCode.CACHE_DOWNGRADED


def test_rejected_minimum_generation_cannot_be_lowered_to_reopen() -> None:
    target = all_keys(KillSwitchKind.PUBLICATION)[0]
    states = make_states(generations={target: 5})
    adapter = make_adapter(
        states=states,
        snapshots=(
            make_snapshot(
                KillSwitchKind.PUBLICATION,
                states,
                minimum_generations={target: 10},
            ),
        ),
    )
    runtime, _, _ = make_runtime(adapter=adapter)

    first = runtime.publication_commands_allowed(context=CONTEXT, now=NOW)
    assert first.code is KillSwitchEligibilityCode.CACHE_DOWNGRADED

    adapter.install_cache_snapshot(
        make_snapshot(
            KillSwitchKind.PUBLICATION,
            states,
            loaded_at=NOW,
            minimum_generations={target: 5},
        )
    )
    lowered = runtime.publication_commands_allowed(
        context=CONTEXT,
        now=NOW + timedelta(seconds=1),
    )
    assert lowered.allowed is False
    assert lowered.code is KillSwitchEligibilityCode.CACHE_DOWNGRADED


def test_same_generation_conflicting_state_cannot_reopen_an_engaged_switch() -> None:
    target = all_keys(KillSwitchKind.PUBLICATION)[0]
    generation_five = {target: 5}
    engaged_states = make_states(
        engaged={target: True},
        generations=generation_five,
    )
    cache = make_adapter(
        states=(),
        snapshots=tuple(
            make_snapshot(switch_type, engaged_states) for switch_type in KillSwitchKind
        ),
    )
    store = make_adapter(states=engaged_states)
    session = make_session()
    runtime = KillSwitchRuntimeService(
        store=store,
        cache=cache,
        step_up_guard=make_step_up_guard(session),
    )

    engaged = runtime.publication_commands_allowed(context=CONTEXT, now=NOW)
    assert engaged.code is KillSwitchEligibilityCode.ENGAGED

    contradictory_states = make_states(generations=generation_five)
    cache.install_cache_snapshot(
        make_snapshot(
            KillSwitchKind.PUBLICATION,
            contradictory_states,
            loaded_at=NOW,
        )
    )
    contradictory = runtime.publication_commands_allowed(
        context=CONTEXT,
        now=NOW + timedelta(seconds=1),
    )
    assert contradictory.allowed is False
    assert contradictory.code is KillSwitchEligibilityCode.CACHE_DOWNGRADED


def test_extra_entry_is_bound_before_a_later_context_requires_it() -> None:
    states = make_states()
    article_a_context = CONTEXT
    article_b_id = UUID("00000000-0000-0000-0000-000000093405")
    article_b_context = KillSwitchContext(
        site_id=SITE_ID,
        category_id=CATEGORY_ID,
        article_id=article_b_id,
    )
    article_b_key = KillSwitchKey(
        KillSwitchScopeType.ARTICLE,
        article_b_id,
        KillSwitchKind.PUBLICATION,
    )
    article_template = next(
        state
        for state in states
        if state.key == all_keys(KillSwitchKind.PUBLICATION)[-1]
    )
    article_b_engaged = replace(
        article_template,
        switch_id=UUID("00000000-0000-0000-0000-000000094405"),
        key=article_b_key,
        engaged=True,
        generation=5,
    )
    cache = make_adapter(
        states=(),
        snapshots=(
            make_snapshot(
                KillSwitchKind.PUBLICATION,
                (*states, article_b_engaged),
            ),
            make_snapshot(KillSwitchKind.AFFILIATE_LINK, states),
        ),
    )
    store = make_adapter(states=states)
    runtime = KillSwitchRuntimeService(
        store=store,
        cache=cache,
        step_up_guard=make_step_up_guard(make_session()),
    )

    article_a = runtime.publication_commands_allowed(
        context=article_a_context,
        now=NOW,
    )
    assert article_a.code is KillSwitchEligibilityCode.ELIGIBLE

    article_b_downgraded = replace(
        article_b_engaged,
        engaged=False,
        generation=0,
    )
    cache.install_cache_snapshot(
        make_snapshot(
            KillSwitchKind.PUBLICATION,
            (*states, article_b_downgraded),
            loaded_at=NOW,
        )
    )
    article_b = runtime.publication_commands_allowed(
        context=article_b_context,
        now=NOW + timedelta(seconds=1),
    )

    assert article_b.allowed is False
    assert article_b.code is KillSwitchEligibilityCode.CACHE_DOWNGRADED


def test_snapshot_union_capacity_overflow_has_no_partial_binding() -> None:
    capacity_states = make_publication_states_at_capacity()
    full_snapshot = make_snapshot(KillSwitchKind.PUBLICATION, capacity_states)
    cache = make_adapter(
        states=(),
        snapshots=(full_snapshot,),
        capacity=MAX_KILL_SWITCH_CACHE_ENTRIES,
    )
    runtime = KillSwitchRuntimeService(
        store=make_adapter(),
        cache=cache,
        step_up_guard=make_step_up_guard(make_session()),
    )

    initial = runtime.publication_commands_allowed(context=CONTEXT, now=NOW)
    assert initial.code is KillSwitchEligibilityCode.ELIGIBLE

    required_states = tuple(
        state
        for state in capacity_states
        if state.key in set(CONTEXT.required_keys(KillSwitchKind.PUBLICATION))
    )
    template = required_states[-1]
    overflow_entry = replace(
        template,
        switch_id=UUID(int=8_000_000),
        key=KillSwitchKey(
            KillSwitchScopeType.ARTICLE,
            UUID(int=9_000_000),
            KillSwitchKind.PUBLICATION,
        ),
    )
    cache.install_cache_snapshot(
        make_snapshot(
            KillSwitchKind.PUBLICATION,
            (*required_states, overflow_entry),
            loaded_at=NOW,
            minimum_generations={required_states[0].key: 1},
        )
    )

    overflow = runtime.publication_commands_allowed(
        context=CONTEXT,
        now=NOW + timedelta(seconds=1),
    )
    assert overflow.allowed is False
    assert overflow.code is KillSwitchEligibilityCode.CACHE_DOWNGRADED

    cache.install_cache_snapshot(
        make_snapshot(
            KillSwitchKind.PUBLICATION,
            capacity_states,
            loaded_at=NOW + timedelta(seconds=1),
        )
    )
    unchanged = runtime.publication_commands_allowed(
        context=CONTEXT,
        now=NOW + timedelta(seconds=2),
    )
    assert unchanged.code is KillSwitchEligibilityCode.ELIGIBLE


def test_higher_generation_cannot_replace_identity_or_regress_change_time() -> None:
    target = all_keys(KillSwitchKind.PUBLICATION)[0]
    observed_states = make_states(
        engaged={target: True},
        generations={target: 5},
    )
    cache = make_adapter(
        states=(),
        snapshots=tuple(
            make_snapshot(switch_type, observed_states)
            for switch_type in KillSwitchKind
        ),
    )
    store = make_adapter(states=observed_states)
    session = make_session()
    runtime = KillSwitchRuntimeService(
        store=store,
        cache=cache,
        step_up_guard=make_step_up_guard(session),
    )
    assert (
        runtime.publication_commands_allowed(context=CONTEXT, now=NOW).code
        is KillSwitchEligibilityCode.ENGAGED
    )
    target_state = next(state for state in observed_states if state.key == target)

    regressed_time = tuple(
        replace(
            state,
            generation=6,
            changed_at=state.changed_at - timedelta(microseconds=1),
        )
        if state.key == target
        else state
        for state in observed_states
    )
    cache.install_cache_snapshot(
        make_snapshot(
            KillSwitchKind.PUBLICATION,
            regressed_time,
            loaded_at=NOW,
        )
    )
    assert (
        runtime.publication_commands_allowed(
            context=CONTEXT,
            now=NOW + timedelta(seconds=1),
        ).code
        is KillSwitchEligibilityCode.CACHE_DOWNGRADED
    )

    replaced_identity = tuple(
        replace(
            state,
            switch_id=UUID("00000000-0000-0000-0000-000000099405"),
            generation=6,
            changed_at=NOW,
        )
        if state == target_state
        else state
        for state in observed_states
    )
    cache.install_cache_snapshot(
        make_snapshot(
            KillSwitchKind.PUBLICATION,
            replaced_identity,
            loaded_at=NOW,
        )
    )
    assert (
        runtime.publication_commands_allowed(
            context=CONTEXT,
            now=NOW + timedelta(seconds=1),
        ).code
        is KillSwitchEligibilityCode.CACHE_DOWNGRADED
    )


def test_duplicate_switch_ids_in_one_snapshot_are_malformed() -> None:
    valid = make_snapshot(KillSwitchKind.PUBLICATION, make_states())
    first = valid.entries[0]
    second = valid.entries[1]
    duplicate = replace(
        second,
        state=replace(second.state, switch_id=first.state.switch_id),
    )
    duplicate_entries = (first, duplicate, *valid.entries[2:])

    _assert_failure(
        KillSwitchFailureCode.INVALID_ARGUMENT,
        lambda: KillSwitchCacheSnapshot(
            switch_type=valid.switch_type,
            entries=duplicate_entries,
            loaded_at=valid.loaded_at,
            fresh_until=valid.fresh_until,
            complete=valid.complete,
        ),
    )

    forged = object.__new__(KillSwitchCacheSnapshot)
    object.__setattr__(forged, "switch_type", valid.switch_type)
    object.__setattr__(forged, "entries", duplicate_entries)
    object.__setattr__(forged, "loaded_at", valid.loaded_at)
    object.__setattr__(forged, "fresh_until", valid.fresh_until)
    object.__setattr__(forged, "complete", valid.complete)
    decision = _runtime_with_cache(_StaticCache(forged)).publication_commands_allowed(
        context=CONTEXT, now=NOW
    )

    assert decision.allowed is False
    assert decision.code is KillSwitchEligibilityCode.CACHE_MALFORMED


def test_oversized_cache_snapshots_fail_closed_before_normalization_copy() -> None:
    valid = make_snapshot(KillSwitchKind.PUBLICATION, make_states())
    oversized_entries = (valid.entries[0],) * (MAX_KILL_SWITCH_CACHE_ENTRIES + 1)

    _assert_failure(
        KillSwitchFailureCode.INVALID_ARGUMENT,
        lambda: KillSwitchCacheSnapshot(
            switch_type=valid.switch_type,
            entries=oversized_entries,
            loaded_at=valid.loaded_at,
            fresh_until=valid.fresh_until,
            complete=valid.complete,
        ),
    )

    forged = object.__new__(KillSwitchCacheSnapshot)
    object.__setattr__(forged, "switch_type", valid.switch_type)
    object.__setattr__(forged, "entries", oversized_entries)
    object.__setattr__(forged, "loaded_at", valid.loaded_at)
    object.__setattr__(forged, "fresh_until", valid.fresh_until)
    object.__setattr__(forged, "complete", valid.complete)

    decision = _runtime_with_cache(_StaticCache(forged)).publication_commands_allowed(
        context=CONTEXT,
        now=NOW,
    )

    assert decision.allowed is False
    assert decision.code is KillSwitchEligibilityCode.CACHE_MALFORMED


def test_switch_id_reuse_across_kind_snapshots_fails_closed() -> None:
    states = make_states()
    publication_id = next(
        state.switch_id
        for state in states
        if state.key == all_keys(KillSwitchKind.PUBLICATION)[0]
    )
    affiliate_target = all_keys(KillSwitchKind.AFFILIATE_LINK)[0]
    conflicting_affiliate_states = tuple(
        replace(state, switch_id=publication_id)
        if state.key == affiliate_target
        else state
        for state in states
    )
    cache = make_adapter(
        states=(),
        snapshots=(
            make_snapshot(KillSwitchKind.PUBLICATION, states),
            make_snapshot(
                KillSwitchKind.AFFILIATE_LINK,
                conflicting_affiliate_states,
                loaded_at=NOW,
            ),
        ),
    )
    store = make_adapter(states=states)
    session = make_session()
    runtime = KillSwitchRuntimeService(
        store=store,
        cache=cache,
        step_up_guard=make_step_up_guard(session),
    )
    publication = runtime.publication_commands_allowed(context=CONTEXT, now=NOW)
    assert publication.code is KillSwitchEligibilityCode.ELIGIBLE

    affiliate = runtime.affiliate_cta_eligible(
        context=CONTEXT,
        now=NOW + timedelta(seconds=1),
    )
    publication_again = runtime.publication_commands_allowed(
        context=CONTEXT,
        now=NOW + timedelta(seconds=1),
    )

    assert affiliate.allowed is False
    assert affiliate.code is KillSwitchEligibilityCode.CACHE_DOWNGRADED
    assert publication_again.code is KillSwitchEligibilityCode.ELIGIBLE


def test_switch_id_reuse_in_an_extra_snapshot_entry_fails_closed() -> None:
    states = make_states()
    publication_id = next(
        state.switch_id
        for state in states
        if state.key == all_keys(KillSwitchKind.PUBLICATION)[0]
    )
    affiliate_template = next(
        state
        for state in states
        if state.key == all_keys(KillSwitchKind.AFFILIATE_LINK)[1]
    )
    extra = replace(
        affiliate_template,
        switch_id=publication_id,
        key=KillSwitchKey(
            KillSwitchScopeType.SITE,
            UUID("00000000-0000-0000-0000-000000098405"),
            KillSwitchKind.AFFILIATE_LINK,
        ),
    )
    cache = make_adapter(
        states=(),
        snapshots=(
            make_snapshot(KillSwitchKind.PUBLICATION, states),
            make_snapshot(KillSwitchKind.AFFILIATE_LINK, (*states, extra)),
        ),
    )
    store = make_adapter(states=states)
    session = make_session()
    runtime = KillSwitchRuntimeService(
        store=store,
        cache=cache,
        step_up_guard=make_step_up_guard(session),
    )
    assert (
        runtime.publication_commands_allowed(context=CONTEXT, now=NOW).code
        is KillSwitchEligibilityCode.ELIGIBLE
    )

    decision = runtime.affiliate_cta_eligible(
        context=CONTEXT,
        now=NOW + timedelta(seconds=1),
    )

    assert decision.allowed is False
    assert decision.code is KillSwitchEligibilityCode.CACHE_DOWNGRADED


def test_combined_adapter_rejects_same_generation_cache_contradiction() -> None:
    target = all_keys(KillSwitchKind.PUBLICATION)[0]
    authoritative = make_states(
        engaged={target: True},
        generations={target: 1},
    )
    contradictory = make_states(generations={target: 1})
    adapter = make_adapter(
        states=authoritative,
        snapshots=(
            make_snapshot(KillSwitchKind.PUBLICATION, contradictory),
            make_snapshot(KillSwitchKind.AFFILIATE_LINK, authoritative),
        ),
    )
    runtime, _, _ = make_runtime(adapter=adapter)

    decision = runtime.publication_commands_allowed(context=CONTEXT, now=NOW)

    assert decision.allowed is False
    assert decision.code is KillSwitchEligibilityCode.CACHE_UNAVAILABLE
    assert adapter.current_state(target) == next(
        state for state in authoritative if state.key == target
    )
    assert adapter.event_intents() == ()


def test_combined_adapter_rejects_cache_id_owned_by_another_key() -> None:
    states = make_states()
    publication_id = next(
        state.switch_id
        for state in states
        if state.key == all_keys(KillSwitchKind.PUBLICATION)[0]
    )
    affiliate_target = all_keys(KillSwitchKind.AFFILIATE_LINK)[0]
    conflicting = tuple(
        replace(state, switch_id=publication_id)
        if state.key == affiliate_target
        else state
        for state in states
    )
    adapter = make_adapter(
        states=states,
        snapshots=(
            make_snapshot(KillSwitchKind.PUBLICATION, states),
            make_snapshot(
                KillSwitchKind.AFFILIATE_LINK,
                conflicting,
            ),
        ),
    )
    runtime, _, _ = make_runtime(adapter=adapter)

    decision = runtime.affiliate_cta_eligible(context=CONTEXT, now=NOW)

    assert decision.allowed is False
    assert decision.code is KillSwitchEligibilityCode.CACHE_UNAVAILABLE


@pytest.mark.parametrize(
    ("category_id", "article_id"),
    ((None, ARTICLE_ID), (CATEGORY_ID, None), (None, None)),
)
def test_incomplete_scope_context_is_rejected(
    category_id: object,
    article_id: object,
) -> None:
    _assert_failure(
        KillSwitchFailureCode.INVALID_ARGUMENT,
        lambda: KillSwitchContext(
            site_id=SITE_ID,
            category_id=cast(UUID, category_id),
            article_id=cast(UUID, article_id),
        ),
    )


@pytest.mark.parametrize("switch_type", tuple(KillSwitchKind))
@pytest.mark.parametrize("scope_index", range(4))
def test_each_applicable_engaged_scope_disables_only_its_kind(
    switch_type: KillSwitchKind,
    scope_index: int,
) -> None:
    target = all_keys(switch_type)[scope_index]
    states = make_states(engaged={target: True})
    runtime, _, _ = make_runtime(adapter=make_adapter(states=states))

    publication = runtime.publication_commands_allowed(context=CONTEXT, now=NOW)
    affiliate = runtime.affiliate_cta_eligible(context=CONTEXT, now=NOW)

    selected = publication if switch_type is KillSwitchKind.PUBLICATION else affiliate
    independent = (
        affiliate if switch_type is KillSwitchKind.PUBLICATION else publication
    )
    assert selected.code is KillSwitchEligibilityCode.ENGAGED
    assert independent.code is KillSwitchEligibilityCode.ELIGIBLE


def test_cache_evaluation_requires_exact_aware_utc() -> None:
    runtime, _, _ = make_runtime()
    non_utc = datetime(
        2026,
        8,
        15,
        21,
        0,
        tzinfo=timezone(timedelta(hours=9)),
    )
    _assert_failure(
        KillSwitchFailureCode.INVALID_ARGUMENT,
        lambda: runtime.affiliate_cta_eligible(context=CONTEXT, now=non_utc),
    )

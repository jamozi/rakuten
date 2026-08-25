"""Deterministic explicit-due scheduler behavior for ST-1401."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

import raos.domain.freshness.freshness as freshness_domain
from raos.domain.freshness.freshness import (
    MAX_FRESHNESS_SCHEDULE_ENTRIES,
    FreshnessCheckIntent,
    FreshnessFailure,
    FreshnessScheduleEntry,
    FreshnessScheduleRequest,
    FreshnessScheduleStatus,
    select_due_freshness,
)

from conftest import (
    EVALUATED_AT,
    JST,
    SCHEDULE_IDS,
    freshness_service,
    schedule_entry,
    schedule_request,
    synthetic_fingerprint,
)


def test_selects_only_active_due_entries_in_the_exact_deterministic_order() -> None:
    same_due = EVALUATED_AT - timedelta(minutes=1)
    schedules = (
        schedule_entry(4, next_due_at=EVALUATED_AT + timedelta(microseconds=1)),
        schedule_entry(3, next_due_at=same_due, priority=20),
        schedule_entry(1, next_due_at=same_due, priority=20),
        schedule_entry(2, next_due_at=same_due, priority=30),
        schedule_entry(
            5,
            status=FreshnessScheduleStatus.PAUSED,
            next_due_at=EVALUATED_AT - timedelta(days=1),
            priority=100,
        ),
        schedule_entry(
            8,
            status=FreshnessScheduleStatus.DISABLED,
            next_due_at=EVALUATED_AT - timedelta(days=2),
            priority=200,
        ),
        schedule_entry(6, next_due_at=EVALUATED_AT - timedelta(minutes=2)),
        schedule_entry(7, next_due_at=EVALUATED_AT),
    )
    request = schedule_request(schedules=schedules)
    selection = select_due_freshness(request)
    assert tuple(intent.schedule_id for intent in selection.intents) == (
        SCHEDULE_IDS[5],
        SCHEDULE_IDS[1],
        SCHEDULE_IDS[0],
        SCHEDULE_IDS[2],
        SCHEDULE_IDS[6],
    )
    assert all(
        intent.request_fingerprint == request.fingerprint
        for intent in selection.intents
    )
    assert selection.cadence_computed is False
    assert selection.persistence.value == "NOT_EXECUTED"
    assert selection.attestation.value == "NOT_ATTESTED"
    assert selection.live_eligible is False


def test_limit_is_applied_after_full_ordering_for_the_exact_range() -> None:
    schedules = tuple(
        schedule_entry(
            ordinal,
            next_due_at=EVALUATED_AT - timedelta(hours=1),
            priority=ordinal,
        )
        for ordinal in range(1, 6)
    )
    request = schedule_request(limit=2, schedules=schedules)
    selection = select_due_freshness(request)
    assert tuple(intent.schedule_id for intent in selection.intents) == (
        SCHEDULE_IDS[4],
        SCHEDULE_IDS[3],
    )


def test_equal_instants_with_different_offsets_sort_by_priority_and_id() -> None:
    due_utc = EVALUATED_AT - timedelta(minutes=5)
    schedules = (
        schedule_entry(3, next_due_at=due_utc.astimezone(JST), priority=10),
        schedule_entry(1, next_due_at=due_utc, priority=10),
        schedule_entry(2, next_due_at=due_utc.astimezone(JST), priority=20),
    )
    selection = select_due_freshness(schedule_request(schedules=schedules))
    assert tuple(intent.schedule_id for intent in selection.intents) == (
        SCHEDULE_IDS[1],
        SCHEDULE_IDS[0],
        SCHEDULE_IDS[2],
    )


def test_empty_and_not_yet_due_inputs_emit_no_intents() -> None:
    empty = select_due_freshness(schedule_request(schedules=()))
    future = select_due_freshness(
        schedule_request(
            schedules=(
                schedule_entry(1, next_due_at=EVALUATED_AT + timedelta(seconds=1)),
            )
        )
    )
    assert empty.intents == ()
    assert future.intents == ()
    assert empty.fingerprint != future.fingerprint


def test_explicit_next_due_at_is_preserved_without_cadence_calculation() -> None:
    explicit_due = (EVALUATED_AT - timedelta(days=3, microseconds=7)).astimezone(JST)
    entry = schedule_entry(1, next_due_at=explicit_due, priority=42)
    selection = select_due_freshness(schedule_request(schedules=(entry,)))
    assert len(selection.intents) == 1
    intent = selection.intents[0]
    assert intent.next_due_at == explicit_due
    assert intent.next_due_at is not explicit_due
    assert intent.next_due_at.tzinfo is timezone.utc
    assert intent.priority == 42
    assert intent.subject_fingerprint == entry.subject_fingerprint
    assert selection.cadence_computed is False


def test_fold_one_due_time_is_owned_as_exact_utc_and_selected() -> None:
    new_york = ZoneInfo("America/New_York")
    ambiguous_due_at = datetime(2026, 11, 1, 1, 30, tzinfo=new_york, fold=1)
    evaluated_at = datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc)
    entry = schedule_entry(1, next_due_at=ambiguous_due_at)
    request = schedule_request(evaluated_at=evaluated_at, schedules=(entry,))
    selection = select_due_freshness(request)
    assert len(selection.intents) == 1
    assert entry.next_due_at == evaluated_at
    assert entry.next_due_at is not ambiguous_due_at
    assert entry.next_due_at.tzinfo is timezone.utc
    assert entry.next_due_at.fold == 0
    assert selection.intents[0].next_due_at == evaluated_at


def test_selector_computes_the_full_request_fingerprint_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = schedule_request(
        limit=10,
        schedules=tuple(schedule_entry(ordinal) for ordinal in range(1, 11)),
    )
    original = freshness_domain._compact_sha256
    request_hash_calls = 0

    def counted_sha256(value: dict[str, object]) -> str:
        nonlocal request_hash_calls
        if set(value) == {"evaluated_at", "limit", "policy_binding", "schedules"}:
            request_hash_calls += 1
        return original(value)

    monkeypatch.setattr(freshness_domain, "_compact_sha256", counted_sha256)
    selection = select_due_freshness(request)
    assert len(selection.intents) == 10
    assert request_hash_calls == 1


def test_request_fingerprint_is_input_order_independent_but_limit_bound() -> None:
    first = schedule_entry(1)
    second = schedule_entry(2)
    forward = schedule_request(limit=2, schedules=(first, second))
    reverse = schedule_request(limit=2, schedules=(second, first))
    smaller = schedule_request(limit=1, schedules=(first, second))
    assert forward.fingerprint == reverse.fingerprint
    assert forward.fingerprint != smaller.fingerprint
    assert (
        select_due_freshness(forward).fingerprint
        == select_due_freshness(reverse).fingerprint
    )


def test_service_returns_the_rebuilt_exact_recorded_selection() -> None:
    request = schedule_request(
        limit=1,
        schedules=(schedule_entry(1), schedule_entry(2, priority=20)),
    )
    expected = select_due_freshness(request)
    actual = freshness_service(schedule=request).select_due(request)
    assert actual == expected
    assert actual is not expected
    assert actual.fingerprint == expected.fingerprint


def test_intent_public_surface_is_metadata_and_fingerprint_only() -> None:
    assert tuple(field.name for field in fields(FreshnessCheckIntent)) == (
        "schedule_id",
        "subject_fingerprint",
        "freshness_class_id",
        "next_due_at",
        "priority",
        "request_fingerprint",
    )
    intent = select_due_freshness(schedule_request()).intents[0]
    assert len(intent.fingerprint) == 64


@pytest.mark.parametrize("limit", (True, 0, -1, 10_001, 1.0, "1"))
def test_limit_rejects_values_outside_exact_one_to_ten_thousand(
    limit: object,
) -> None:
    with pytest.raises(FreshnessFailure):
        schedule_request(limit=cast(int, limit))


@pytest.mark.parametrize(
    "factory",
    (
        lambda: FreshnessScheduleEntry(
            schedule_id=UUID(int=0),
            subject_fingerprint=synthetic_fingerprint("zero-id"),
            freshness_class_id="FRESH-001",
            status=FreshnessScheduleStatus.ACTIVE,
            next_due_at=EVALUATED_AT,
            priority=1,
        ),
        lambda: FreshnessScheduleEntry(
            schedule_id=SCHEDULE_IDS[0],
            subject_fingerprint="0" * 63,
            freshness_class_id="FRESH-001",
            status=FreshnessScheduleStatus.ACTIVE,
            next_due_at=EVALUATED_AT,
            priority=1,
        ),
        lambda: FreshnessScheduleEntry(
            schedule_id=SCHEDULE_IDS[0],
            subject_fingerprint=synthetic_fingerprint("bad-class"),
            freshness_class_id="FRESH-999",
            status=FreshnessScheduleStatus.ACTIVE,
            next_due_at=EVALUATED_AT,
            priority=1,
        ),
        lambda: FreshnessScheduleEntry(
            schedule_id=SCHEDULE_IDS[0],
            subject_fingerprint=synthetic_fingerprint("bad-state"),
            freshness_class_id="FRESH-001",
            status=cast(FreshnessScheduleStatus, "ACTIVE"),
            next_due_at=EVALUATED_AT,
            priority=1,
        ),
        lambda: FreshnessScheduleEntry(
            schedule_id=SCHEDULE_IDS[0],
            subject_fingerprint=synthetic_fingerprint("naive-time"),
            freshness_class_id="FRESH-001",
            status=FreshnessScheduleStatus.ACTIVE,
            next_due_at=EVALUATED_AT.replace(tzinfo=None),
            priority=1,
        ),
        lambda: FreshnessScheduleEntry(
            schedule_id=SCHEDULE_IDS[0],
            subject_fingerprint=synthetic_fingerprint("bool-priority"),
            freshness_class_id="FRESH-001",
            status=FreshnessScheduleStatus.ACTIVE,
            next_due_at=EVALUATED_AT,
            priority=cast(int, True),
        ),
        lambda: FreshnessScheduleEntry(
            schedule_id=SCHEDULE_IDS[0],
            subject_fingerprint=synthetic_fingerprint("negative-priority"),
            freshness_class_id="FRESH-001",
            status=FreshnessScheduleStatus.ACTIVE,
            next_due_at=EVALUATED_AT,
            priority=-1,
        ),
        lambda: FreshnessScheduleEntry(
            schedule_id=SCHEDULE_IDS[0],
            subject_fingerprint=synthetic_fingerprint("huge-priority"),
            freshness_class_id="FRESH-001",
            status=FreshnessScheduleStatus.ACTIVE,
            next_due_at=EVALUATED_AT,
            priority=1 << 31,
        ),
    ),
)
def test_schedule_entries_reject_ambiguous_or_unbounded_values(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(FreshnessFailure):
        factory()


def test_schedule_rejects_duplicate_ids_targets_and_capacity_overflow() -> None:
    first = schedule_entry(1)
    duplicate_id = replace(schedule_entry(2), schedule_id=first.schedule_id)
    duplicate_target = replace(
        schedule_entry(2), subject_fingerprint=first.subject_fingerprint
    )
    with pytest.raises(FreshnessFailure):
        schedule_request(schedules=(first, duplicate_id))
    with pytest.raises(FreshnessFailure):
        schedule_request(schedules=(first, duplicate_target))
    with pytest.raises(FreshnessFailure):
        FreshnessScheduleRequest(
            evaluated_at=EVALUATED_AT,
            limit=MAX_FRESHNESS_SCHEDULE_ENTRIES,
            schedules=(first,) * (MAX_FRESHNESS_SCHEDULE_ENTRIES + 1),
        )


def test_schedule_request_rejects_non_tuple_and_naive_evaluation_time() -> None:
    with pytest.raises(FreshnessFailure):
        FreshnessScheduleRequest(
            evaluated_at=EVALUATED_AT,
            limit=1,
            schedules=cast(tuple[FreshnessScheduleEntry, ...], [schedule_entry(1)]),
        )
    with pytest.raises(FreshnessFailure):
        FreshnessScheduleRequest(
            evaluated_at=EVALUATED_AT.replace(tzinfo=None),
            limit=1,
            schedules=(),
        )

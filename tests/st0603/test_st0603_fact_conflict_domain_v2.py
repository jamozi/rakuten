"""Focused exact conflict-domain checks for ST-0603 V2."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pickle
from pathlib import Path
import tempfile
from collections.abc import Iterator
from uuid import UUID

import pytest

from raos.domain.evidence.fact_conflict_runtime_v2 import (
    FACT_CONFLICT_CONTENT_POLICY_V2,
    ComparableFactValueV2,
    FactComparisonOutcomeV2,
    FactConflictFactRefV2,
    FactConflictFailureCodeV2,
    FactConflictFailureV2,
    FactConflictQueueStatusV2,
    FactConflictReadinessV2,
    FactConflictReasonV2,
    FactConflictStatusV2,
    UnresolvedFactConflictV2,
    batch_from_mapping_v2,
    batch_mapping_v2,
    build_fact_conflict_artifacts_v2,
    compare_fact_values_v2,
    event_from_mapping_v2,
    event_mapping_v2,
    windows_overlap_v2,
)
from raos.domain.evidence.fact_extraction_runtime_v2 import FactValueKindV2
from tests.st0603.st0603_runtime_v2_fixtures import (
    derive_persisted_fact_v2,
    exact_persisted_fact_v2,
)


def _failure_code(call: object) -> FactConflictFailureCodeV2:
    assert callable(call)
    with pytest.raises(FactConflictFailureV2) as captured:
        call()
    return captured.value.code


@pytest.fixture()
def st0603_domain_root_v2() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="st0603-domain-", dir="/tmp") as raw:
        root = Path(raw)
        root.chmod(0o700)
        yield root


def test_exact_same_subject_predicate_window_and_different_value_conflicts(
    st0603_domain_root_v2,
) -> None:
    first = exact_persisted_fact_v2(st0603_domain_root_v2)
    second = derive_persisted_fact_v2(first, label="price-change", price_delta=7)
    command, batch, event = build_fact_conflict_artifacts_v2((first, second))
    assert len(command.input_bindings) == 2
    assert batch.comparison_count == 3
    assert batch.equal_value_count == 2
    assert batch.disjoint_window_count == 0
    assert batch.incompatible_unit_or_locale_count == 0
    assert len(batch.conflicts) == len(batch.queue) == 1
    conflict = batch.conflicts[0]
    queue = batch.queue[0]
    assert conflict.reason is FactConflictReasonV2.VALUE_MISMATCH
    assert conflict.status is FactConflictStatusV2.UNRESOLVED
    assert conflict.queue_status is FactConflictQueueStatusV2.HUMAN_REVIEW
    assert conflict.readiness is FactConflictReadinessV2.NOT_READY
    assert conflict.content_policy == FACT_CONFLICT_CONTENT_POLICY_V2
    assert conflict.content_policy == "source_conflict"
    assert conflict.silent_resolution_forbidden is True
    assert conflict.winner_fact_id is None
    assert conflict.tolerance is None
    assert conflict.authority_priority_used is False
    assert conflict.resolution is None
    assert queue.conflict_id == conflict.conflict_id
    assert queue.status is FactConflictQueueStatusV2.HUMAN_REVIEW
    assert queue.readiness is FactConflictReadinessV2.NOT_READY
    assert queue.assigned_actor_id is None and queue.resolution is None
    assert event.conflict_ids == (conflict.conflict_id,)
    assert event.queue_ids == (queue.queue_id,)


def test_exact_duplicate_input_and_distinct_equal_values_do_not_conflict(
    st0603_domain_root_v2,
) -> None:
    first = exact_persisted_fact_v2(st0603_domain_root_v2)
    duplicate_command, duplicate_batch, _event = build_fact_conflict_artifacts_v2(
        (first, first)
    )
    assert len(duplicate_command.input_bindings) == 1
    assert duplicate_batch.comparison_count == 0
    assert duplicate_batch.conflicts == duplicate_batch.queue == ()

    equal = derive_persisted_fact_v2(first, label="equal-source")
    _command, equal_batch, equal_event = build_fact_conflict_artifacts_v2(
        (first, equal)
    )
    assert equal_batch.comparison_count == 3
    assert equal_batch.equal_value_count == 3
    assert equal_batch.conflicts == equal_batch.queue == ()
    assert equal_event.conflict_ids == equal_event.queue_ids == ()


def test_input_permutation_is_byte_deterministic(st0603_domain_root_v2) -> None:
    first = exact_persisted_fact_v2(st0603_domain_root_v2)
    second = derive_persisted_fact_v2(first, label="permutation", price_delta=1)
    forward = build_fact_conflict_artifacts_v2((first, second))
    reverse = build_fact_conflict_artifacts_v2((second, first))
    assert forward == reverse
    assert batch_mapping_v2(forward[1]) == batch_mapping_v2(reverse[1])


def test_validity_windows_are_exact_half_open_and_touching_is_disjoint() -> None:
    start = datetime(2026, 8, 25, tzinfo=timezone.utc)
    middle = start + timedelta(hours=1)
    end = middle + timedelta(hours=1)
    assert windows_overlap_v2(start, middle, middle, end) is False
    assert windows_overlap_v2(start, end, middle, None) is True
    assert windows_overlap_v2(start, None, end, None) is True
    assert _failure_code(lambda: windows_overlap_v2(start, start, middle, end)) is (
        FactConflictFailureCodeV2.INVALID_ARGUMENT
    )


def test_incompatible_unit_or_locale_routes_without_conversion(
    st0603_domain_root_v2,
) -> None:
    first = exact_persisted_fact_v2(st0603_domain_root_v2)
    price = next(item for item in first.batch.facts if item.value_numeric is not None)
    left = FactConflictFactRefV2.from_fact(
        batch_id=first.batch.batch_id,
        fact=price,
    )
    right = replace(
        left,
        fact_id=UUID("71345678-1234-4234-8234-123456789001"),
        fact_sha256="a" * 64,
        batch_id=UUID("71345678-1234-4234-8234-123456789002"),
        source_snapshot_id=UUID("71345678-1234-4234-8234-123456789003"),
        value=replace(left.value, unit_code="USD"),
    )
    assert compare_fact_values_v2(left.value, right.value) is (
        FactComparisonOutcomeV2.INCOMPATIBLE_UNIT_OR_LOCALE
    )
    conflict = UnresolvedFactConflictV2.create(
        left=left,
        right=right,
        scan_id=UUID("71345678-1234-4234-8234-123456789004"),
        detected_at=first.committed_at,
    )
    assert conflict.reason is FactConflictReasonV2.INCOMPATIBLE_UNIT_OR_LOCALE
    assert conflict.status is FactConflictStatusV2.UNRESOLVED
    assert conflict.winner_fact_id is conflict.tolerance is conflict.resolution is None


def test_typed_value_comparison_has_no_tolerance() -> None:
    left = ComparableFactValueV2(
        value_kind=FactValueKindV2.NUMERIC,
        value_numeric=Decimal("100"),
        value_boolean=None,
        unit_code="JPY",
        locale="ja-JP",
    )
    one_unit_more = replace(left, value_numeric=Decimal("101"))
    assert compare_fact_values_v2(left, left) is FactComparisonOutcomeV2.EQUAL
    assert compare_fact_values_v2(left, one_unit_more) is (
        FactComparisonOutcomeV2.VALUE_CONFLICT
    )
    boolean = ComparableFactValueV2(
        value_kind=FactValueKindV2.BOOLEAN,
        value_numeric=None,
        value_boolean=True,
        unit_code=None,
        locale=None,
    )
    assert _failure_code(lambda: compare_fact_values_v2(left, boolean)) is (
        FactConflictFailureCodeV2.VALUE_KIND_MISMATCH
    )


def test_mapping_round_trips_recompute_closed_invariants(
    st0603_domain_root_v2,
) -> None:
    first = exact_persisted_fact_v2(st0603_domain_root_v2)
    second = derive_persisted_fact_v2(first, label="mapping", price_delta=3)
    _command, batch, event = build_fact_conflict_artifacts_v2((first, second))
    assert batch_from_mapping_v2(batch_mapping_v2(batch)) == batch
    assert event_from_mapping_v2(event_mapping_v2(event)) == event
    malformed = batch_mapping_v2(batch)
    malformed["silent_resolution_forbidden"] = False
    assert _failure_code(lambda: batch_from_mapping_v2(malformed)) is (
        FactConflictFailureCodeV2.INVALID_ARGUMENT
    )
    wrong_count = batch_mapping_v2(batch)
    wrong_count["comparison_count"] = batch.comparison_count + 1
    assert _failure_code(lambda: batch_from_mapping_v2(wrong_count)) is (
        FactConflictFailureCodeV2.INVALID_ARGUMENT
    )
    wrong_queue = event_mapping_v2(event)
    wrong_queue["queue_ids"] = ["71345678-1234-4234-8234-123456789099"]
    assert _failure_code(lambda: event_from_mapping_v2(wrong_queue)) is (
        FactConflictFailureCodeV2.INVALID_ARGUMENT
    )


def test_dependency_tamper_and_failure_serialization_fail_closed(
    st0603_domain_root_v2,
) -> None:
    first = exact_persisted_fact_v2(st0603_domain_root_v2)
    object.__setattr__(first.batch, "external_action_count", False)
    assert _failure_code(lambda: build_fact_conflict_artifacts_v2((first,))) is (
        FactConflictFailureCodeV2.DEPENDENCY_MISMATCH
    )
    failure = FactConflictFailureV2(FactConflictFailureCodeV2.TAMPER_DETECTED)
    assert "TAMPER_DETECTED" in repr(failure)
    assert "http" not in str(failure).lower()
    with pytest.raises(TypeError):
        pickle.dumps(failure)

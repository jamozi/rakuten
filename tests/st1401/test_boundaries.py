"""Trust, architecture, and capability boundaries for ST-1401."""

from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
import pickle
from typing import cast
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

import raos.adapters.recorded_freshness as recorded_freshness_module
from raos.adapters.recorded_freshness import (
    RecordedFreshnessAdapter,
    RecordedFreshnessEvaluationFixture,
    RecordedFreshnessScheduleFixture,
)
from raos.application.freshness.freshness import FreshnessService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.freshness.freshness import (
    FreshnessEvaluation,
    FreshnessEvaluationRequest,
    FreshnessFailure,
    FreshnessFailureCode,
    FreshnessScheduleEntry,
    FreshnessScheduleRequest,
    FreshnessScheduleSelection,
    FreshnessScheduleStatus,
    evaluate_freshness,
    freshness_policy_classes,
    provisional_freshness_policy_binding,
    select_due_freshness,
)
from raos.ports.freshness import FreshnessExchange

from conftest import (
    EVALUATED_AT,
    evaluation_request,
    freshness_service,
    recorded_adapter,
    schedule_entry,
    schedule_request,
    synthetic_fingerprint,
)


ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_PATHS = (
    ROOT / "python/raos/domain/freshness/freshness.py",
    ROOT / "python/raos/ports/freshness.py",
    ROOT / "python/raos/application/freshness/freshness.py",
    ROOT / "python/raos/adapters/recorded_freshness.py",
)


class _CountingExchange:
    def __init__(
        self,
        *,
        evaluation_outcome: object,
        schedule_outcome: object,
    ) -> None:
        self.evaluation_calls = 0
        self.schedule_calls = 0
        self.evaluation_outcome = evaluation_outcome
        self.schedule_outcome = schedule_outcome

    def evaluate(self, request: FreshnessEvaluationRequest) -> FreshnessEvaluation:
        del request
        self.evaluation_calls += 1
        if isinstance(self.evaluation_outcome, Exception):
            raise self.evaluation_outcome
        return cast(FreshnessEvaluation, self.evaluation_outcome)

    def select_due(
        self, request: FreshnessScheduleRequest
    ) -> FreshnessScheduleSelection:
        del request
        self.schedule_calls += 1
        if isinstance(self.schedule_outcome, Exception):
            raise self.schedule_outcome
        return cast(FreshnessScheduleSelection, self.schedule_outcome)


class _RequestMutatingExchange:
    def evaluate(self, request: FreshnessEvaluationRequest) -> FreshnessEvaluation:
        object.__setattr__(request, "freshness_class_id", "FRESH-002")
        return evaluate_freshness(request)

    def select_due(
        self, request: FreshnessScheduleRequest
    ) -> FreshnessScheduleSelection:
        object.__setattr__(request, "limit", 1)
        return select_due_freshness(request)


class _MutableTimezone(tzinfo):
    def __init__(self, offset: timedelta) -> None:
        self.offset = offset

    def utcoffset(self, value: datetime | None) -> timedelta:
        del value
        return self.offset

    def dst(self, value: datetime | None) -> timedelta:
        del value
        return timedelta(0)

    def tzname(self, value: datetime | None) -> str:
        del value
        return "MUTABLE_TEST_ZONE"


def _service(exchange: object) -> FreshnessService:
    return FreshnessService(
        environment=RuntimeEnvironment.ENV_DEV,
        exchange=cast(FreshnessExchange, exchange),
    )


def _trees() -> tuple[ast.AST, ...]:
    return tuple(
        ast.parse(path.read_text(encoding="utf-8")) for path in PRODUCTION_PATHS
    )


def test_port_exposes_only_evaluation_and_due_selection() -> None:
    assert {
        name
        for name, value in FreshnessExchange.__dict__.items()
        if callable(value) and not name.startswith("_")
    } == {"evaluate", "select_due"}


def test_production_slice_has_no_io_network_provider_or_database_imports() -> None:
    imported = {
        alias.name
        for tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert imported.isdisjoint(
        {
            "boto3",
            "httpx",
            "os",
            "pathlib",
            "psycopg",
            "random",
            "requests",
            "socket",
            "sqlalchemy",
            "subprocess",
            "time",
            "urllib",
        }
    )


def test_production_slice_has_no_clock_io_or_state_write_calls() -> None:
    called_names = {
        node.func.id
        for tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    called_attributes = {
        node.func.attr
        for tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert called_names.isdisjoint(
        {"open", "getenv", "system", "exec", "eval", "sleep", "uuid4", "uuid7"}
    )
    assert called_attributes.isdisjoint(
        {
            "add",
            "commit",
            "connect",
            "delete",
            "execute",
            "getenv",
            "now",
            "open",
            "publish",
            "read",
            "request",
            "retry",
            "rollback",
            "save",
            "send",
            "utcnow",
            "write",
        }
    )


def test_domain_and_port_preserve_inward_dependency_direction() -> None:
    trees = _trees()
    domain_imports = {
        node.module or ""
        for node in ast.walk(trees[0])
        if isinstance(node, ast.ImportFrom)
    }
    port_imports = {
        node.module or ""
        for node in ast.walk(trees[1])
        if isinstance(node, ast.ImportFrom)
    }
    assert not any(
        name.startswith(("raos.application", "raos.adapters", "raos.ports"))
        for name in domain_imports
    )
    assert not any(
        name.startswith(("raos.application", "raos.adapters")) for name in port_imports
    )


def test_no_forbidden_runtime_or_business_surface_is_present() -> None:
    public_methods = {
        node.name
        for tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }
    assert public_methods.isdisjoint(
        {
            "activate",
            "approve",
            "calculate_cadence",
            "create_job",
            "dispatch",
            "enqueue",
            "persist",
            "publish",
            "reorder",
            "reschedule",
            "retry",
            "save",
            "write",
        }
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in PRODUCTION_PATHS)
    assert "image-30d" not in combined
    assert "ST-1701" not in combined


def test_request_shapes_have_no_cadence_override_or_external_execution_input() -> None:
    assert tuple(field.name for field in fields(FreshnessEvaluationRequest)) == (
        "freshness_class_id",
        "observation_status",
        "observed_at",
        "evaluated_at",
        "recommendation_basis_affected",
    )
    assert tuple(field.name for field in fields(FreshnessScheduleEntry)) == (
        "schedule_id",
        "subject_fingerprint",
        "freshness_class_id",
        "status",
        "next_due_at",
        "priority",
    )
    assert tuple(field.name for field in fields(FreshnessScheduleRequest)) == (
        "evaluated_at",
        "limit",
        "schedules",
    )


@pytest.mark.parametrize(
    "environment",
    (
        RuntimeEnvironment.INTEGRATION,
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.RECOVERY,
        RuntimeEnvironment.PRODUCTION,
    ),
)
def test_service_and_adapter_reject_every_non_dev_ci_environment(
    environment: RuntimeEnvironment,
) -> None:
    adapter = recorded_adapter()
    with pytest.raises(FreshnessFailure) as service_failure:
        FreshnessService(environment=environment, exchange=adapter)
    assert service_failure.value.code is FreshnessFailureCode.DEVELOPMENT_ONLY

    evaluation = evaluation_request()
    schedule = schedule_request()
    with pytest.raises(FreshnessFailure):
        RecordedFreshnessAdapter(
            environment=environment,
            fixture_capacity=2,
            evaluation_fixtures=(
                RecordedFreshnessEvaluationFixture(
                    request=evaluation,
                    evaluation=evaluate_freshness(evaluation),
                ),
            ),
            schedule_fixtures=(
                RecordedFreshnessScheduleFixture(
                    request=schedule,
                    selection=select_due_freshness(schedule),
                ),
            ),
        )


def test_ci_environment_accepts_the_same_disabled_recorded_boundary() -> None:
    dev_adapter = recorded_adapter()
    evaluation = evaluation_request()
    schedule = schedule_request()
    ci_adapter = RecordedFreshnessAdapter(
        environment=RuntimeEnvironment.CI,
        fixture_capacity=2,
        evaluation_fixtures=(
            RecordedFreshnessEvaluationFixture(
                request=evaluation,
                evaluation=evaluate_freshness(evaluation),
            ),
        ),
        schedule_fixtures=(
            RecordedFreshnessScheduleFixture(
                request=schedule,
                selection=select_due_freshness(schedule),
            ),
        ),
    )
    assert FreshnessService(
        environment=RuntimeEnvironment.CI, exchange=ci_adapter
    ).evaluate(evaluation) == dev_adapter.evaluate(evaluation)


def test_service_accepts_fold_one_inputs_after_constructor_owned_utc_snapshot() -> None:
    new_york = ZoneInfo("America/New_York")
    observed_at = datetime(2026, 11, 1, 1, 30, tzinfo=new_york, fold=1)
    evaluated_at = datetime(2026, 11, 1, 7, 30, tzinfo=timezone.utc)
    evaluation = evaluation_request(
        evaluated_at=evaluated_at,
        observed_at=observed_at,
        explicit_observed_at=True,
    )
    due_at = datetime(2026, 11, 1, 1, 45, tzinfo=new_york, fold=1)
    schedule = schedule_request(
        evaluated_at=evaluated_at,
        schedules=(schedule_entry(1, next_due_at=due_at),),
    )
    service = freshness_service(evaluation=evaluation, schedule=schedule)
    assert service.evaluate(evaluation) == evaluate_freshness(evaluation)
    assert service.select_due(schedule) == select_due_freshness(schedule)
    assert evaluation.observed_at is not None
    assert evaluation.observed_at.tzinfo is timezone.utc
    assert schedule.schedules[0].next_due_at.tzinfo is timezone.utc


def test_adapter_accepts_fold_one_inputs_after_constructor_owned_utc_snapshot() -> None:
    new_york = ZoneInfo("America/New_York")
    observed_at = datetime(2026, 11, 1, 1, 30, tzinfo=new_york, fold=1)
    evaluated_at = datetime(2026, 11, 1, 7, 30, tzinfo=timezone.utc)
    evaluation = evaluation_request(
        evaluated_at=evaluated_at,
        observed_at=observed_at,
        explicit_observed_at=True,
    )
    schedule = schedule_request(
        evaluated_at=evaluated_at,
        schedules=(
            schedule_entry(
                1,
                next_due_at=datetime(2026, 11, 1, 1, 45, tzinfo=new_york, fold=1),
            ),
        ),
    )
    adapter = recorded_adapter(evaluation=evaluation, schedule=schedule)
    assert adapter.evaluate(evaluation) == evaluate_freshness(evaluation)
    assert adapter.select_due(schedule) == select_due_freshness(schedule)


def test_service_calls_each_collaborator_once_and_returns_rebuilt_values() -> None:
    evaluation = evaluation_request()
    schedule = schedule_request()
    expected_evaluation = evaluate_freshness(evaluation)
    expected_selection = select_due_freshness(schedule)
    exchange = _CountingExchange(
        evaluation_outcome=expected_evaluation,
        schedule_outcome=expected_selection,
    )
    service = _service(exchange)
    actual_evaluation = service.evaluate(evaluation)
    actual_selection = service.select_due(schedule)
    assert exchange.evaluation_calls == 1
    assert exchange.schedule_calls == 1
    assert actual_evaluation == expected_evaluation
    assert actual_selection == expected_selection
    assert actual_evaluation is not expected_evaluation
    assert actual_selection is not expected_selection


def test_collaborator_exceptions_are_sanitized_without_echo_or_context() -> None:
    canary = "untrusted-collaborator-sensitive-canary"
    evaluation = evaluation_request()
    schedule = schedule_request()
    exchange = _CountingExchange(
        evaluation_outcome=RuntimeError(canary),
        schedule_outcome=RuntimeError(canary),
    )
    service = _service(exchange)
    with pytest.raises(FreshnessFailure) as evaluation_failure:
        service.evaluate(evaluation)
    with pytest.raises(FreshnessFailure) as schedule_failure:
        service.select_due(schedule)
    assert evaluation_failure.value.code is FreshnessFailureCode.EVALUATOR_UNAVAILABLE
    assert schedule_failure.value.code is FreshnessFailureCode.SCHEDULER_UNAVAILABLE
    for failure in (evaluation_failure.value, schedule_failure.value):
        assert canary not in str(failure)
        assert canary not in repr(failure)
        assert failure.__cause__ is None
        assert failure.__context__ is None


def test_wrong_type_and_valid_but_drifted_collaborator_results_are_rejected() -> None:
    evaluation = evaluation_request()
    schedule = schedule_request(
        schedules=(schedule_entry(1), schedule_entry(2)),
    )
    wrong_type = _CountingExchange(
        evaluation_outcome=object(),
        schedule_outcome=object(),
    )
    with pytest.raises(FreshnessFailure) as evaluation_failure:
        _service(wrong_type).evaluate(evaluation)
    with pytest.raises(FreshnessFailure) as schedule_failure:
        _service(wrong_type).select_due(schedule)
    assert evaluation_failure.value.code is FreshnessFailureCode.EVALUATION_MISMATCH
    assert schedule_failure.value.code is FreshnessFailureCode.SCHEDULE_MISMATCH

    other_evaluation = evaluate_freshness(
        evaluation_request(freshness_class_id="FRESH-002")
    )
    expected_selection = select_due_freshness(schedule)
    reversed_selection = replace(
        expected_selection, intents=tuple(reversed(expected_selection.intents))
    )
    drifted = _CountingExchange(
        evaluation_outcome=other_evaluation,
        schedule_outcome=reversed_selection,
    )
    with pytest.raises(FreshnessFailure):
        _service(drifted).evaluate(evaluation)
    with pytest.raises(FreshnessFailure):
        _service(drifted).select_due(schedule)


def test_object_level_tampering_is_revalidated_before_any_result_is_returned() -> None:
    evaluation = evaluation_request()
    schedule = schedule_request()
    tampered_evaluation = evaluate_freshness(evaluation)
    object.__setattr__(tampered_evaluation.policy_binding, "policy_active", True)
    tampered_selection = select_due_freshness(schedule)
    object.__setattr__(tampered_selection.intents[0], "priority", True)
    exchange = _CountingExchange(
        evaluation_outcome=tampered_evaluation,
        schedule_outcome=tampered_selection,
    )
    with pytest.raises(FreshnessFailure) as evaluation_failure:
        _service(exchange).evaluate(evaluation)
    with pytest.raises(FreshnessFailure) as schedule_failure:
        _service(exchange).select_due(schedule)
    assert evaluation_failure.value.code is FreshnessFailureCode.EVALUATION_MISMATCH
    assert schedule_failure.value.code is FreshnessFailureCode.SCHEDULE_MISMATCH


def test_collaborator_cannot_rebind_results_by_mutating_the_sent_request() -> None:
    evaluation = evaluation_request()
    schedule = schedule_request(
        limit=2,
        schedules=(schedule_entry(1), schedule_entry(2)),
    )
    service = _service(_RequestMutatingExchange())
    with pytest.raises(FreshnessFailure) as evaluation_failure:
        service.evaluate(evaluation)
    with pytest.raises(FreshnessFailure) as schedule_failure:
        service.select_due(schedule)
    assert evaluation_failure.value.code is FreshnessFailureCode.EVALUATION_MISMATCH
    assert schedule_failure.value.code is FreshnessFailureCode.SCHEDULE_MISMATCH
    assert evaluation.freshness_class_id == "FRESH-001"
    assert schedule.limit == 2


def test_invalid_tampered_request_is_rejected_before_collaborator_call() -> None:
    evaluation = evaluation_request()
    schedule = schedule_request()
    expected_evaluation = evaluate_freshness(evaluation)
    expected_selection = select_due_freshness(schedule)
    exchange = _CountingExchange(
        evaluation_outcome=expected_evaluation,
        schedule_outcome=expected_selection,
    )
    object.__setattr__(evaluation, "freshness_class_id", "sensitive-canary")
    object.__setattr__(schedule.schedules[0], "priority", True)
    with pytest.raises(FreshnessFailure) as evaluation_failure:
        _service(exchange).evaluate(evaluation)
    with pytest.raises(FreshnessFailure) as schedule_failure:
        _service(exchange).select_due(schedule)
    assert exchange.evaluation_calls == 0
    assert exchange.schedule_calls == 0
    assert evaluation_failure.value.code is FreshnessFailureCode.INVALID_ARGUMENT
    assert schedule_failure.value.code is FreshnessFailureCode.INVALID_ARGUMENT
    assert "sensitive-canary" not in repr(evaluation_failure.value)


def test_exported_values_own_datetime_uuid_and_nested_value_snapshots() -> None:
    mutable_zone = _MutableTimezone(timedelta(hours=9))
    source_observed_at = datetime(2026, 8, 15, 20, 0, tzinfo=mutable_zone)
    source_due_at = datetime(2026, 8, 15, 20, 30, tzinfo=mutable_zone)
    source_uuid = UUID("018f3e90-7b00-7000-8000-000000009999")
    evaluation_request_value = FreshnessEvaluationRequest(
        freshness_class_id="FRESH-001",
        observation_status=evaluation_request().observation_status,
        observed_at=source_observed_at,
        evaluated_at=EVALUATED_AT,
        recommendation_basis_affected=False,
    )
    source_entry = FreshnessScheduleEntry(
        schedule_id=source_uuid,
        subject_fingerprint=synthetic_fingerprint("owned-alias"),
        freshness_class_id="FRESH-001",
        status=FreshnessScheduleStatus.ACTIVE,
        next_due_at=source_due_at,
        priority=1,
    )
    request = FreshnessScheduleRequest(
        evaluated_at=EVALUATED_AT,
        limit=1,
        schedules=(source_entry,),
    )
    selection = select_due_freshness(request)
    request_fingerprint = request.fingerprint
    selection_fingerprint = selection.fingerprint
    evaluation_fingerprint = evaluation_request_value.fingerprint

    assert source_entry.schedule_id is not source_uuid
    assert request.schedules[0] is not source_entry
    assert request.schedules[0].schedule_id is not source_entry.schedule_id
    assert selection.intents[0].schedule_id is not request.schedules[0].schedule_id
    assert evaluation_request_value.observed_at is not source_observed_at
    assert source_entry.next_due_at is not source_due_at
    assert evaluation_request_value.observed_at is not None
    assert evaluation_request_value.observed_at.tzinfo is timezone.utc
    assert source_entry.next_due_at.tzinfo is timezone.utc

    object.__setattr__(source_uuid, "int", 123456789)
    mutable_zone.offset = timedelta(hours=-7)
    assert request.fingerprint == request_fingerprint
    assert selection.fingerprint == selection_fingerprint
    assert evaluation_request_value.fingerprint == evaluation_fingerprint

    source_binding = provisional_freshness_policy_binding()
    source_policy_class = freshness_policy_classes()[0]
    source_evaluation = evaluate_freshness(evaluation_request_value)
    owned_evaluation = replace(
        source_evaluation,
        policy_binding=source_binding,
        policy_class=source_policy_class,
    )
    owned_evaluation_fingerprint = owned_evaluation.fingerprint
    assert owned_evaluation.policy_binding is not source_binding
    assert owned_evaluation.policy_class is not source_policy_class
    object.__setattr__(source_binding, "policy_active", True)
    object.__setattr__(source_policy_class, "warning_after_hours", 1)
    assert owned_evaluation.fingerprint == owned_evaluation_fingerprint

    source_intent = selection.intents[0]
    owned_selection = replace(selection, intents=(source_intent,))
    owned_selection_fingerprint = owned_selection.fingerprint
    assert owned_selection.intents[0] is not source_intent
    assert owned_selection.intents[0].schedule_id is not source_intent.schedule_id
    object.__setattr__(source_intent.schedule_id, "int", 987654321)
    object.__setattr__(
        source_intent,
        "next_due_at",
        datetime(2026, 11, 1, 1, 30, tzinfo=ZoneInfo("America/New_York"), fold=1),
    )
    assert owned_selection.fingerprint == owned_selection_fingerprint


def test_revalidation_rejects_corruption_without_repairing_caller_inputs() -> None:
    raw_fold = datetime(
        2026,
        11,
        1,
        1,
        30,
        tzinfo=ZoneInfo("America/New_York"),
        fold=1,
    )
    evaluation = evaluation_request()
    object.__setattr__(evaluation, "observed_at", raw_fold)
    service = freshness_service()
    adapter = recorded_adapter()
    evaluation_operations: tuple[Callable[[], object], ...] = (
        lambda: evaluate_freshness(evaluation),
        lambda: service.evaluate(evaluation),
        lambda: adapter.evaluate(evaluation),
    )
    for operation in evaluation_operations:
        with pytest.raises(FreshnessFailure):
            operation()
        assert evaluation.observed_at is raw_fold
        assert evaluation.observed_at.fold == 1

    schedule = schedule_request()
    corrupted_entry = schedule.schedules[0]
    corrupted_uuid = corrupted_entry.schedule_id
    object.__setattr__(corrupted_uuid, "int", 0)
    object.__setattr__(corrupted_entry, "next_due_at", raw_fold)
    schedule_operations: tuple[Callable[[], object], ...] = (
        lambda: select_due_freshness(schedule),
        lambda: service.select_due(schedule),
        lambda: adapter.select_due(schedule),
    )
    for operation in schedule_operations:
        with pytest.raises(FreshnessFailure):
            operation()
        assert corrupted_entry.schedule_id is corrupted_uuid
        assert corrupted_entry.schedule_id.int == 0
        assert corrupted_entry.next_due_at is raw_fold
        assert corrupted_entry.next_due_at.fold == 1


def test_successful_boundaries_do_not_replace_caller_snapshot_objects() -> None:
    evaluation = evaluation_request()
    schedule = schedule_request()
    observed_at = evaluation.observed_at
    evaluated_at = evaluation.evaluated_at
    schedules = schedule.schedules
    entry = schedules[0]
    schedule_id = entry.schedule_id
    next_due_at = entry.next_due_at
    adapter = recorded_adapter(evaluation=evaluation, schedule=schedule)
    service = FreshnessService(
        environment=RuntimeEnvironment.ENV_DEV,
        exchange=adapter,
    )
    evaluate_freshness(evaluation)
    select_due_freshness(schedule)
    adapter.evaluate(evaluation)
    adapter.select_due(schedule)
    service.evaluate(evaluation)
    service.select_due(schedule)
    assert evaluation.observed_at is observed_at
    assert evaluation.evaluated_at is evaluated_at
    assert schedule.schedules is schedules
    assert schedule.schedules[0] is entry
    assert schedule.schedules[0].schedule_id is schedule_id
    assert schedule.schedules[0].next_due_at is next_due_at


@pytest.mark.parametrize("capacity", (True, 0, -1, 10_001, 1.0, "2"))
def test_recorded_adapter_rejects_invalid_capacity(capacity: object) -> None:
    evaluation = evaluation_request()
    with pytest.raises(FreshnessFailure):
        RecordedFreshnessAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            fixture_capacity=cast(int, capacity),
            evaluation_fixtures=(
                RecordedFreshnessEvaluationFixture(
                    request=evaluation,
                    evaluation=evaluate_freshness(evaluation),
                ),
            ),
            schedule_fixtures=(),
        )


def _large_paused_schedule_request(
    *, entry_count: int, identity_offset: int
) -> FreshnessScheduleRequest:
    return FreshnessScheduleRequest(
        evaluated_at=EVALUATED_AT,
        limit=1,
        schedules=tuple(
            FreshnessScheduleEntry(
                schedule_id=UUID(int=identity_offset + ordinal + 1),
                subject_fingerprint=synthetic_fingerprint(
                    f"capacity-{identity_offset + ordinal + 1}"
                ),
                freshness_class_id="FRESH-001",
                status=FreshnessScheduleStatus.PAUSED,
                next_due_at=EVALUATED_AT,
                priority=0,
            )
            for ordinal in range(entry_count)
        ),
    )


def test_adapter_nested_capacity_accepts_exact_bound_and_preflights_overflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_request = _large_paused_schedule_request(
        entry_count=5_000, identity_offset=10_000
    )
    second_request = _large_paused_schedule_request(
        entry_count=5_000, identity_offset=20_000
    )
    first_fixture = RecordedFreshnessScheduleFixture(
        request=first_request,
        selection=select_due_freshness(first_request),
    )
    second_fixture = RecordedFreshnessScheduleFixture(
        request=second_request,
        selection=select_due_freshness(second_request),
    )
    exact_adapter = RecordedFreshnessAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        fixture_capacity=2,
        evaluation_fixtures=(),
        schedule_fixtures=(first_fixture, second_fixture),
    )
    assert exact_adapter.select_due(first_request).intents == ()

    over_request = FreshnessScheduleRequest(
        evaluated_at=EVALUATED_AT,
        limit=1,
        schedules=(
            *first_request.schedules,
            FreshnessScheduleEntry(
                schedule_id=UUID(int=99_999),
                subject_fingerprint=synthetic_fingerprint("capacity-over"),
                freshness_class_id="FRESH-001",
                status=FreshnessScheduleStatus.PAUSED,
                next_due_at=EVALUATED_AT,
                priority=0,
            ),
        ),
    )
    over_fixture = RecordedFreshnessScheduleFixture(
        request=over_request,
        selection=select_due_freshness(over_request),
    )
    binding_calls = 0

    def unexpected_binding(
        fixture: RecordedFreshnessScheduleFixture,
    ) -> tuple[str, str]:
        nonlocal binding_calls
        del fixture
        binding_calls += 1
        raise AssertionError("binding must not run above nested capacity")

    monkeypatch.setattr(
        recorded_freshness_module, "_schedule_binding", unexpected_binding
    )
    uninitialized = object.__new__(RecordedFreshnessAdapter)
    with pytest.raises(FreshnessFailure) as failure:
        RecordedFreshnessAdapter.__init__(
            uninitialized,
            environment=RuntimeEnvironment.ENV_DEV,
            fixture_capacity=2,
            evaluation_fixtures=(),
            schedule_fixtures=(over_fixture, second_fixture),
        )
    assert failure.value.code is FreshnessFailureCode.INVALID_ARGUMENT
    assert binding_calls == 0
    assert not hasattr(uninitialized, "_evaluation_bindings")
    assert not hasattr(uninitialized, "_schedule_bindings")


def test_recorded_adapter_rejects_empty_duplicate_and_exhausted_fixtures() -> None:
    evaluation = evaluation_request()
    fixture = RecordedFreshnessEvaluationFixture(
        request=evaluation,
        evaluation=evaluate_freshness(evaluation),
    )
    with pytest.raises(FreshnessFailure):
        RecordedFreshnessAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            fixture_capacity=1,
            evaluation_fixtures=(),
            schedule_fixtures=(),
        )
    with pytest.raises(FreshnessFailure):
        RecordedFreshnessAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            fixture_capacity=2,
            evaluation_fixtures=(fixture, fixture),
            schedule_fixtures=(),
        )
    with pytest.raises(FreshnessFailure) as missing_evaluation:
        recorded_adapter().evaluate(evaluation_request(freshness_class_id="FRESH-002"))
    with pytest.raises(FreshnessFailure) as missing_schedule:
        recorded_adapter().select_due(schedule_request(limit=1, schedules=()))
    assert missing_evaluation.value.code is FreshnessFailureCode.EVALUATOR_UNAVAILABLE
    assert missing_schedule.value.code is FreshnessFailureCode.SCHEDULER_UNAVAILABLE


def test_fixture_rejects_a_result_bound_to_another_request() -> None:
    first = evaluation_request()
    second = evaluation_request(freshness_class_id="FRESH-002")
    with pytest.raises(FreshnessFailure):
        RecordedFreshnessEvaluationFixture(
            request=first,
            evaluation=evaluate_freshness(second),
        )
    first_schedule = schedule_request()
    second_schedule = schedule_request(limit=1, schedules=())
    with pytest.raises(FreshnessFailure):
        RecordedFreshnessScheduleFixture(
            request=first_schedule,
            selection=select_due_freshness(second_schedule),
        )


def test_adapter_bindings_do_not_retain_caller_owned_fixture_objects() -> None:
    evaluation = evaluation_request()
    schedule = schedule_request(
        limit=2,
        schedules=(schedule_entry(1), schedule_entry(2)),
    )
    evaluation_result = evaluate_freshness(evaluation)
    schedule_result = select_due_freshness(schedule)
    evaluation_fixture = RecordedFreshnessEvaluationFixture(
        request=evaluation,
        evaluation=evaluation_result,
    )
    schedule_fixture = RecordedFreshnessScheduleFixture(
        request=schedule,
        selection=schedule_result,
    )
    assert evaluation_fixture.request is not evaluation
    assert evaluation_fixture.evaluation is not evaluation_result
    assert schedule_fixture.request is not schedule
    assert schedule_fixture.selection is not schedule_result
    adapter = RecordedFreshnessAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        fixture_capacity=2,
        evaluation_fixtures=(evaluation_fixture,),
        schedule_fixtures=(schedule_fixture,),
    )

    other_evaluation = evaluation_request(freshness_class_id="FRESH-002")
    other_schedule = schedule_request(limit=1, schedules=(schedule_entry(3),))
    object.__setattr__(evaluation_fixture, "request", other_evaluation)
    object.__setattr__(
        evaluation_fixture, "evaluation", evaluate_freshness(other_evaluation)
    )
    object.__setattr__(schedule_fixture, "request", other_schedule)
    object.__setattr__(
        schedule_fixture, "selection", select_due_freshness(other_schedule)
    )

    original_evaluation = evaluation_request()
    original_schedule = schedule_request(
        limit=2,
        schedules=(schedule_entry(1), schedule_entry(2)),
    )
    assert adapter.evaluate(original_evaluation) == evaluate_freshness(
        original_evaluation
    )
    assert adapter.select_due(original_schedule) == select_due_freshness(
        original_schedule
    )
    with pytest.raises(FreshnessFailure) as evaluation_failure:
        adapter.evaluate(other_evaluation)
    with pytest.raises(FreshnessFailure) as schedule_failure:
        adapter.select_due(other_schedule)
    assert evaluation_failure.value.code is FreshnessFailureCode.EVALUATOR_UNAVAILABLE
    assert schedule_failure.value.code is FreshnessFailureCode.SCHEDULER_UNAVAILABLE


def test_values_failures_fixtures_adapter_and_service_are_redacted_nonpickleable() -> (
    None
):
    evaluation = evaluation_request(recommendation_basis_affected=True)
    schedule = schedule_request(
        schedules=(
            schedule_entry(
                1,
                next_due_at=EVALUATED_AT - timedelta(days=1),
                priority=99,
            ),
        )
    )
    evaluated = evaluate_freshness(evaluation)
    selected = select_due_freshness(schedule)
    evaluation_fixture = RecordedFreshnessEvaluationFixture(
        request=evaluation,
        evaluation=evaluated,
    )
    schedule_fixture = RecordedFreshnessScheduleFixture(
        request=schedule,
        selection=selected,
    )
    adapter = recorded_adapter(evaluation=evaluation, schedule=schedule)
    service = freshness_service(evaluation=evaluation, schedule=schedule)
    failure = FreshnessFailure(FreshnessFailureCode.EVALUATOR_UNAVAILABLE)
    values = (
        evaluation,
        evaluated,
        schedule.schedules[0],
        schedule,
        selected.intents[0],
        selected,
        evaluation_fixture,
        schedule_fixture,
        adapter,
        service,
        failure,
    )
    for value in values:
        assert "018f3e90" not in repr(value)
        assert "subject" not in repr(value)
        with pytest.raises(TypeError):
            pickle.dumps(value)
    for value, attribute in (
        (evaluation, "freshness_class_id"),
        (evaluated, "state"),
        (schedule.schedules[0], "priority"),
        (schedule, "limit"),
        (selected.intents[0], "priority"),
        (selected, "intents"),
        (evaluation_fixture, "evaluation"),
        (schedule_fixture, "selection"),
    ):
        with pytest.raises(Exception):
            setattr(value, attribute, object())

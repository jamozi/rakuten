"""Hostile collaborator, ordering, budget, and replay tests for ST-0706."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import cast
from uuid import UUID

import pytest

from conftest import (
    AI_JOB_ID,
    IDENTITY,
    NOW,
    OPS_JOB_ID,
    OUTPUT_ARTIFACT_ID,
    PLAN,
    command_and_controls,
    provider_failure,
    success_script,
    validation_observation,
)
from raos.adapters.development_ai_controls import InMemoryDevelopmentAiControls
from raos.adapters.recorded_ai_job_orchestration import (
    RecordedAiJobOrchestrationAdapter,
    RecordedProviderStep,
    RecordedValidationStep,
)
from raos.application.ai.job_orchestration import (
    DevelopmentRecordedAiJobOrchestrationService,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.job_orchestration import (
    AiJobCommand,
    AiJobEventObservation,
    AiJobEventType,
    AiJobResult,
    JobDisposition,
    OrchestrationFailure,
    OrchestrationFailureCode,
    ProviderExecutionOutcome,
    ProviderExecutionRequest,
    ProviderFailureClass,
    ProviderOutcomeKind,
    RecordedJobStateExchange,
    ValidationFailureClass,
    ValidationObservation,
    ValidationRequest,
    ValidationStatus,
)
from raos.domain.ai.routing import (
    BudgetCommit,
    BudgetRelease,
    BudgetReservation,
    ReservationIntent,
    RouteIdentity,
    RoutingFailure,
    RoutingFailureCode,
)
from raos.ports.ai_job_orchestration import RecordedAiProviderExecutionPort


def _adapter_for_success(
    command: AiJobCommand,
    *,
    capacity: int = 10,
) -> tuple[
    RecordedAiJobOrchestrationAdapter,
    ProviderExecutionOutcome,
    ValidationObservation,
]:
    provider_request, outcome, validation_request, observation = success_script(command)
    adapter = RecordedAiJobOrchestrationAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        capacity=capacity,
        provider_script=(RecordedProviderStep(provider_request, outcome),),
        validation_script=(RecordedValidationStep(validation_request, observation),),
    )
    return adapter, outcome, observation


def _service(
    *,
    provider: object,
    validation: object,
    state: object,
    events: object,
    controls: object,
) -> DevelopmentRecordedAiJobOrchestrationService:
    return DevelopmentRecordedAiJobOrchestrationService(
        environment=RuntimeEnvironment.ENV_DEV,
        provider=provider,  # type: ignore[arg-type]
        validation=validation,  # type: ignore[arg-type]
        state=state,  # type: ignore[arg-type]
        events=events,  # type: ignore[arg-type]
        controls=controls,  # type: ignore[arg-type]
    )


class _OrderedAdapter:
    def __init__(
        self, delegate: RecordedAiJobOrchestrationAdapter, order: list[str]
    ) -> None:
        self._delegate = delegate
        self._order = order

    def execute(self, *, request: ProviderExecutionRequest) -> ProviderExecutionOutcome:
        self._order.append("provider")
        return self._delegate.execute(request=request)

    def observe(self, *, request: ValidationRequest) -> ValidationObservation:
        self._order.append("validation")
        return self._delegate.observe(request=request)

    def exchange(self, *, command: AiJobCommand) -> RecordedJobStateExchange:
        return self._delegate.exchange(command=command)

    def complete(self, *, command: AiJobCommand, result: AiJobResult) -> None:
        self._delegate.complete(command=command, result=result)

    def append(self, *, event: AiJobEventObservation) -> None:
        self._order.append(
            {
                AiJobEventType.REQUESTED: "requested_event",
                AiJobEventType.SUCCEEDED: "success_event",
                AiJobEventType.FAILED: "failed_event",
            }[event.event_type]
        )
        self._delegate.append(event=event)


class _OrderedControls:
    def __init__(
        self, delegate: InMemoryDevelopmentAiControls, order: list[str]
    ) -> None:
        self._delegate = delegate
        self._order = order

    def reserve(self, *, intent: ReservationIntent, now: object) -> BudgetReservation:
        return self._delegate.reserve(intent=intent, now=now)  # type: ignore[arg-type]

    def commit(
        self,
        *,
        reservation: BudgetReservation,
        committed_jpy: int,
        now: object,
    ) -> BudgetCommit:
        self._order.append("budget_commit")
        return self._delegate.commit(
            reservation=reservation,
            committed_jpy=committed_jpy,
            now=now,  # type: ignore[arg-type]
        )

    def release(self, *, reservation: BudgetReservation, now: object) -> BudgetRelease:
        self._order.append("budget_release")
        return self._delegate.release(
            reservation=reservation,
            now=now,  # type: ignore[arg-type]
        )

    def trip_open(self, *, identity: RouteIdentity, now: object) -> None:
        self._order.append("circuit_open")
        self._delegate.trip_open(identity=identity, now=now)  # type: ignore[arg-type]


class _ThrowingProvider:
    def execute(self, *, request: ProviderExecutionRequest) -> ProviderExecutionOutcome:
        del request
        raise RuntimeError("provider-secret-value")


class _ExplodingRepr:
    def __repr__(self) -> str:
        raise RuntimeError("repr-secret-value")


class _MalformedProvider:
    def execute(self, *, request: ProviderExecutionRequest) -> object:
        del request
        return _ExplodingRepr()


class _InterruptingProvider:
    def execute(self, *, request: ProviderExecutionRequest) -> ProviderExecutionOutcome:
        del request
        raise KeyboardInterrupt


class _ThrowingValidation:
    def observe(self, *, request: ValidationRequest) -> ValidationObservation:
        del request
        raise RuntimeError("validation-secret-value")


class _ExitingValidation:
    def observe(self, *, request: ValidationRequest) -> ValidationObservation:
        del request
        raise SystemExit(23)


class _MismatchedValidation:
    def observe(self, *, request: ValidationRequest) -> ValidationObservation:
        return ValidationObservation(
            status=ValidationStatus.PASS,
            ai_job_id=UUID("00000000-0000-4000-8000-000000070600"),
            attempt_number=request.attempt_number,
            output_artifact_id=request.output_artifact_id,
            output_artifact_sha256=request.output_artifact_sha256,
            plan=request.plan,
            failure_class=None,
        )


class _CommitFailureControls(_OrderedControls):
    def commit(
        self,
        *,
        reservation: BudgetReservation,
        committed_jpy: int,
        now: object,
    ) -> BudgetCommit:
        del reservation, committed_jpy, now
        raise RuntimeError("budget-secret-value")


class _CommitMismatchControls(_OrderedControls):
    def commit(
        self,
        *,
        reservation: BudgetReservation,
        committed_jpy: int,
        now: object,
    ) -> BudgetCommit:
        receipt = self._delegate.commit(
            reservation=reservation,
            committed_jpy=committed_jpy,
            now=now,  # type: ignore[arg-type]
        )
        return BudgetCommit(
            reservation_id=receipt.reservation_id,
            intent_sha256=receipt.intent_sha256,
            committed_jpy=receipt.committed_jpy,
            committed_at=receipt.committed_at + timedelta(microseconds=1),
        )


class _FailingEventSink:
    def __init__(
        self,
        delegate: RecordedAiJobOrchestrationAdapter,
        fail_on: AiJobEventType,
    ) -> None:
        self._delegate = delegate
        self._fail_on = fail_on
        self.calls: list[AiJobEventType] = []

    def append(self, *, event: AiJobEventObservation) -> None:
        self.calls.append(event.event_type)
        if event.event_type is self._fail_on:
            raise RuntimeError("event-secret-value")
        self._delegate.append(event=event)


class _ThrowingState:
    def exchange(self, *, command: AiJobCommand) -> RecordedJobStateExchange:
        del command
        raise RuntimeError("state-secret-value")

    def complete(self, *, command: AiJobCommand, result: AiJobResult) -> None:
        del command, result
        raise RuntimeError("unreachable")


def test_exact_success_side_effect_order() -> None:
    command, controls = command_and_controls()
    adapter, _, _ = _adapter_for_success(command)
    order: list[str] = []
    ordered_adapter = _OrderedAdapter(adapter, order)
    ordered_controls = _OrderedControls(controls, order)
    service = _service(
        provider=ordered_adapter,
        validation=ordered_adapter,
        state=ordered_adapter,
        events=ordered_adapter,
        controls=ordered_controls,
    )

    result = service.execute(command=command, now=NOW)

    assert result.disposition is JobDisposition.SUCCEEDED
    assert order == [
        "requested_event",
        "provider",
        "validation",
        "budget_commit",
        "success_event",
    ]


def test_replay_mismatch_and_cross_id_conflicts_burn_no_new_side_effects() -> None:
    command, controls = command_and_controls()
    adapter, outcome, observation = _adapter_for_success(command)
    service = _service(
        provider=adapter,
        validation=adapter,
        state=adapter,
        events=adapter,
        controls=controls,
    )
    first = service.execute(command=command, now=NOW)

    replay = service.execute(command=command, now=NOW)
    mismatch = service.execute(
        command=replace(command, input_artifact_sha256="7" * 64), now=NOW
    )
    ai_conflict = service.execute(
        command=replace(
            command,
            operation_id="operation.st0706.ai-conflict.v1",
            idempotency_key="idempotency.st0706.ai-conflict.v1",
            ops_job_id=UUID("00000000-0000-4000-8000-000000030304"),
        ),
        now=NOW,
    )
    ops_conflict = service.execute(
        command=replace(
            command,
            operation_id="operation.st0706.ops-conflict.v1",
            idempotency_key="idempotency.st0706.ops-conflict.v1",
            ai_job_id=UUID("00000000-0000-4000-8000-000000070607"),
        ),
        now=NOW,
    )

    assert replay == first
    assert mismatch.failure_code is OrchestrationFailureCode.IDEMPOTENCY_MISMATCH
    assert ai_conflict.failure_code is OrchestrationFailureCode.AI_JOB_ID_CONFLICT
    assert ops_conflict.failure_code is OrchestrationFailureCode.OPS_JOB_ID_CONFLICT
    assert adapter.provider_outcomes() == (outcome,)
    assert adapter.validation_observations() == (observation,)
    assert len(adapter.event_observations()) == 2
    assert adapter.completed_results() == (first,)


@pytest.mark.parametrize("cancelled", [False, True])
def test_deadline_and_cancellation_make_zero_provider_validation_calls(
    cancelled: bool,
) -> None:
    command, controls = command_and_controls(
        deadline_at=(NOW + timedelta(minutes=1) if cancelled else NOW),
        cancellation_requested=cancelled,
        cancel_requested_at=(NOW if cancelled else None),
    )
    adapter = RecordedAiJobOrchestrationAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        capacity=10,
        provider_script=(),
        validation_script=(),
    )
    service = _service(
        provider=adapter,
        validation=adapter,
        state=adapter,
        events=adapter,
        controls=controls,
    )

    result = service.execute(command=command, now=NOW)

    assert result.disposition is (
        JobDisposition.CANCELLED if cancelled else JobDisposition.EXPIRED
    )
    assert type(result.budget_receipt) is BudgetRelease
    assert adapter.provider_outcomes() == ()
    assert adapter.validation_observations() == ()


@pytest.mark.parametrize(
    ("attempt", "kind", "failure_class", "retryable", "expected_disposition"),
    [
        (
            1,
            ProviderOutcomeKind.REFUSED,
            ProviderFailureClass.REFUSAL,
            False,
            JobDisposition.BLOCKED,
        ),
        (
            1,
            ProviderOutcomeKind.TIMED_OUT,
            ProviderFailureClass.TIMEOUT,
            True,
            JobDisposition.RETRY_DEFERRED,
        ),
        (
            2,
            ProviderOutcomeKind.TIMED_OUT,
            ProviderFailureClass.TIMEOUT,
            True,
            JobDisposition.FAILED_TERMINAL,
        ),
    ],
)
def test_provider_refusal_timeout_retry_deferred_and_exhausted(
    attempt: int,
    kind: ProviderOutcomeKind,
    failure_class: ProviderFailureClass,
    retryable: bool,
    expected_disposition: JobDisposition,
) -> None:
    command, controls = command_and_controls(
        attempt_number=attempt,
        max_attempts=2,
    )
    request, outcome = provider_failure(
        command,
        kind=kind,
        failure_class=failure_class,
        retryable=retryable,
    )
    adapter = RecordedAiJobOrchestrationAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        capacity=10,
        provider_script=(RecordedProviderStep(request, outcome),),
        validation_script=(),
    )
    service = _service(
        provider=adapter,
        validation=adapter,
        state=adapter,
        events=adapter,
        controls=controls,
    )

    result = service.execute(command=command, now=NOW)

    assert result.disposition is expected_disposition
    assert result.retryable is (expected_disposition is JobDisposition.RETRY_DEFERRED)
    assert type(result.budget_receipt) is BudgetCommit
    assert result.budget_receipt.committed_jpy == 2
    assert adapter.validation_observations() == ()
    assert adapter.event_observations()[-1].event_type is AiJobEventType.FAILED


@pytest.mark.parametrize("provider", [_ThrowingProvider(), _MalformedProvider()])
def test_throwing_or_malformed_provider_burns_full_reservation_and_trips_circuit(
    provider: object,
) -> None:
    command, controls = command_and_controls()
    adapter = RecordedAiJobOrchestrationAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        capacity=10,
        provider_script=(),
        validation_script=(),
    )
    service = _service(
        provider=cast(RecordedAiProviderExecutionPort, provider),
        validation=adapter,
        state=adapter,
        events=adapter,
        controls=controls,
    )

    result = service.execute(command=command, now=NOW)

    assert result.disposition is JobDisposition.QUARANTINED
    assert result.failure_code is OrchestrationFailureCode.PROVIDER_OBSERVATION_INVALID
    assert type(result.budget_receipt) is BudgetCommit
    assert result.budget_receipt.committed_jpy == 10
    assert "secret" not in repr(result).lower()
    assert adapter.validation_observations() == ()
    with pytest.raises(RoutingFailure) as captured:
        controls.trip_open(identity=IDENTITY, now=NOW)
    assert captured.value.code is RoutingFailureCode.CIRCUIT_OPEN


def test_cost_over_reservation_burns_only_reservation_and_never_validates() -> None:
    command, controls = command_and_controls()
    request, outcome, _, _ = success_script(command)
    over_cost = replace(outcome, actual_cost_jpy=11)
    adapter = RecordedAiJobOrchestrationAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        capacity=10,
        provider_script=(RecordedProviderStep(request, over_cost),),
        validation_script=(),
    )
    service = _service(
        provider=adapter,
        validation=adapter,
        state=adapter,
        events=adapter,
        controls=controls,
    )

    result = service.execute(command=command, now=NOW)

    assert result.failure_code is OrchestrationFailureCode.COST_EXCEEDED
    assert result.actual_cost_jpy is None
    assert type(result.budget_receipt) is BudgetCommit
    assert result.budget_receipt.committed_jpy == 10
    assert adapter.validation_observations() == ()


@pytest.mark.parametrize(
    ("status", "failure_class", "disposition", "failure_code"),
    [
        (
            ValidationStatus.FAIL,
            ValidationFailureClass.POLICY,
            JobDisposition.BLOCKED,
            OrchestrationFailureCode.VALIDATION_FAILED,
        ),
        (
            ValidationStatus.UNAVAILABLE,
            ValidationFailureClass.PLAN_UNAVAILABLE,
            JobDisposition.QUARANTINED,
            OrchestrationFailureCode.VALIDATION_UNAVAILABLE,
        ),
    ],
)
def test_validation_fail_and_unavailable_commit_incurred_cost(
    status: ValidationStatus,
    failure_class: ValidationFailureClass,
    disposition: JobDisposition,
    failure_code: OrchestrationFailureCode,
) -> None:
    command, controls = command_and_controls()
    provider_request, outcome, _, _ = success_script(command)
    request, observation = validation_observation(
        command,
        status=status,
        failure_class=failure_class,
    )
    adapter = RecordedAiJobOrchestrationAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        capacity=10,
        provider_script=(RecordedProviderStep(provider_request, outcome),),
        validation_script=(RecordedValidationStep(request, observation),),
    )
    service = _service(
        provider=adapter,
        validation=adapter,
        state=adapter,
        events=adapter,
        controls=controls,
    )

    result = service.execute(command=command, now=NOW)

    assert result.disposition is disposition
    assert result.failure_code is failure_code
    assert type(result.budget_receipt) is BudgetCommit
    assert result.budget_receipt.committed_jpy == 7
    assert all(
        event.event_type is not AiJobEventType.SUCCEEDED
        for event in adapter.event_observations()
    )


@pytest.mark.parametrize("validation", [_ThrowingValidation(), _MismatchedValidation()])
def test_throwing_or_mismatched_validation_commits_cost_and_quarantines(
    validation: object,
) -> None:
    command, controls = command_and_controls()
    provider_request, outcome, _, _ = success_script(command)
    adapter = RecordedAiJobOrchestrationAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        capacity=10,
        provider_script=(RecordedProviderStep(provider_request, outcome),),
        validation_script=(),
    )
    service = _service(
        provider=adapter,
        validation=validation,
        state=adapter,
        events=adapter,
        controls=controls,
    )

    result = service.execute(command=command, now=NOW)

    assert result.disposition is JobDisposition.QUARANTINED
    assert (
        result.failure_code is OrchestrationFailureCode.VALIDATION_OBSERVATION_INVALID
    )
    assert type(result.budget_receipt) is BudgetCommit
    assert result.budget_receipt.committed_jpy == 7
    assert "secret" not in repr(result).lower()


@pytest.mark.parametrize(
    ("wrapper_type", "failure_code"),
    [
        (_CommitFailureControls, OrchestrationFailureCode.BUDGET_CONTROL_FAILURE),
        (_CommitMismatchControls, OrchestrationFailureCode.BUDGET_RECEIPT_MISMATCH),
    ],
)
def test_budget_throw_or_receipt_mismatch_cannot_produce_success(
    wrapper_type: type[_OrderedControls],
    failure_code: OrchestrationFailureCode,
) -> None:
    command, controls = command_and_controls()
    adapter, _, _ = _adapter_for_success(command)
    wrapped_controls = wrapper_type(controls, [])
    service = _service(
        provider=adapter,
        validation=adapter,
        state=adapter,
        events=adapter,
        controls=wrapped_controls,
    )

    result = service.execute(command=command, now=NOW)

    assert result.disposition is JobDisposition.QUARANTINED
    assert result.failure_code is failure_code
    assert result.budget_receipt is None
    assert adapter.event_observations()[-1].event_type is AiJobEventType.FAILED
    assert all(
        event.event_type is not AiJobEventType.SUCCEEDED
        for event in adapter.event_observations()
    )


def test_success_event_failure_prevents_success_without_recursive_failed_event() -> (
    None
):
    command, controls = command_and_controls()
    adapter, _, _ = _adapter_for_success(command)
    events = _FailingEventSink(adapter, AiJobEventType.SUCCEEDED)
    service = _service(
        provider=adapter,
        validation=adapter,
        state=adapter,
        events=events,
        controls=controls,
    )

    result = service.execute(command=command, now=NOW)

    assert result.disposition is JobDisposition.QUARANTINED
    assert result.failure_code is OrchestrationFailureCode.EVENT_RECORDING_FAILURE
    assert events.calls == [AiJobEventType.REQUESTED, AiJobEventType.SUCCEEDED]
    assert tuple(event.event_type for event in adapter.event_observations()) == (
        AiJobEventType.REQUESTED,
    )
    assert adapter.completed_results() == (result,)


def test_requested_event_failure_releases_and_never_calls_provider() -> None:
    command, controls = command_and_controls()
    adapter, _, _ = _adapter_for_success(command)
    events = _FailingEventSink(adapter, AiJobEventType.REQUESTED)
    service = _service(
        provider=adapter,
        validation=adapter,
        state=adapter,
        events=events,
        controls=controls,
    )

    result = service.execute(command=command, now=NOW)

    assert result.failure_code is OrchestrationFailureCode.EVENT_RECORDING_FAILURE
    assert type(result.budget_receipt) is BudgetRelease
    assert events.calls == [AiJobEventType.REQUESTED]
    assert adapter.provider_outcomes() == ()
    assert adapter.validation_observations() == ()


def test_collaborator_exception_is_sanitized_with_no_cause_or_context() -> None:
    command, controls = command_and_controls()
    adapter = RecordedAiJobOrchestrationAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        capacity=10,
        provider_script=(),
        validation_script=(),
    )
    service = _service(
        provider=adapter,
        validation=adapter,
        state=_ThrowingState(),
        events=adapter,
        controls=controls,
    )

    with pytest.raises(OrchestrationFailure) as captured:
        service.execute(command=command, now=NOW)

    assert captured.value.code is OrchestrationFailureCode.STATE_EXCHANGE_FAILURE
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert "secret" not in repr(captured.value).lower()


def test_keyboard_interrupt_and_system_exit_propagate() -> None:
    command, controls = command_and_controls()
    adapter = RecordedAiJobOrchestrationAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        capacity=10,
        provider_script=(),
        validation_script=(),
    )
    provider_interrupt_service = _service(
        provider=_InterruptingProvider(),
        validation=adapter,
        state=adapter,
        events=adapter,
        controls=controls,
    )
    with pytest.raises(KeyboardInterrupt):
        provider_interrupt_service.execute(command=command, now=NOW)

    second_command, second_controls = command_and_controls(
        operation_id="operation.st0706.system-exit.v1",
        ai_job_id=UUID("00000000-0000-4000-8000-000000070608"),
        ops_job_id=UUID("00000000-0000-4000-8000-000000030308"),
    )
    provider_request, outcome, _, _ = success_script(second_command)
    second_adapter = RecordedAiJobOrchestrationAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        capacity=10,
        provider_script=(RecordedProviderStep(provider_request, outcome),),
        validation_script=(),
    )
    validation_exit_service = _service(
        provider=second_adapter,
        validation=_ExitingValidation(),
        state=second_adapter,
        events=second_adapter,
        controls=second_controls,
    )
    with pytest.raises(SystemExit, match="23"):
        validation_exit_service.execute(command=second_command, now=NOW)


def test_token_total_mismatch_is_rejected_before_any_service_call() -> None:
    with pytest.raises(OrchestrationFailure) as captured:
        ProviderExecutionOutcome(
            kind=ProviderOutcomeKind.SUCCEEDED,
            ai_job_id=AI_JOB_ID,
            attempt_number=1,
            provider_request_id="provider-request.invalid-tokens.v1",
            output_artifact_id=OUTPUT_ARTIFACT_ID,
            output_artifact_sha256="6" * 64,
            input_tokens=10,
            output_tokens=5,
            total_tokens=14,
            actual_cost_jpy=7,
            failure_class=None,
            retryable=False,
        )
    assert captured.value.code is OrchestrationFailureCode.INVALID_REQUEST
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


assert AI_JOB_ID != OPS_JOB_ID
assert PLAN.plan_sha256 == (
    "ea935831a1bb667229ae5a5495a27a801b9c21ab3c3ddbe53e266b8f7c311c42"
)

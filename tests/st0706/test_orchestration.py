"""Focused positive and pre-provider fail-closed ST-0706 behavior."""

from __future__ import annotations

from conftest import NOW, command_and_controls, success_script
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
    AiJobEventType,
    JobDisposition,
    OrchestrationFailureCode,
    ValidationStatus,
)
from raos.domain.ai.routing import BudgetCommit, BudgetRelease


def test_success_requires_pass_commit_event_and_replays_without_side_effects() -> None:
    command, controls = command_and_controls()
    provider_request, outcome, validation_request, observation = success_script(command)
    adapter = RecordedAiJobOrchestrationAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        capacity=10,
        provider_script=(RecordedProviderStep(provider_request, outcome),),
        validation_script=(RecordedValidationStep(validation_request, observation),),
    )
    service = DevelopmentRecordedAiJobOrchestrationService(
        environment=RuntimeEnvironment.ENV_DEV,
        provider=adapter,
        validation=adapter,
        state=adapter,
        events=adapter,
        controls=controls,
    )

    first = service.execute(command=command, now=NOW)
    replay = service.execute(command=command, now=NOW)

    assert first == replay
    assert first.disposition is JobDisposition.SUCCEEDED
    assert first.failure_code is None
    assert first.validation_status is ValidationStatus.PASS
    assert type(first.budget_receipt) is BudgetCommit
    assert first.budget_receipt.committed_jpy == 7
    assert adapter.provider_outcomes() == (outcome,)
    assert adapter.validation_observations() == (observation,)
    assert adapter.completed_results() == (first,)
    assert tuple(event.event_type for event in adapter.event_observations()) == (
        AiJobEventType.REQUESTED,
        AiJobEventType.SUCCEEDED,
    )


def test_expired_command_releases_budget_without_provider_or_validation() -> None:
    command, controls = command_and_controls(deadline_at=NOW)
    adapter = RecordedAiJobOrchestrationAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        capacity=10,
        provider_script=(),
        validation_script=(),
    )
    service = DevelopmentRecordedAiJobOrchestrationService(
        environment=RuntimeEnvironment.ENV_DEV,
        provider=adapter,
        validation=adapter,
        state=adapter,
        events=adapter,
        controls=controls,
    )

    result = service.execute(command=command, now=NOW)

    assert result.disposition is JobDisposition.EXPIRED
    assert result.failure_code is OrchestrationFailureCode.DEADLINE_EXPIRED
    assert type(result.budget_receipt) is BudgetRelease
    assert adapter.provider_outcomes() == ()
    assert adapter.validation_observations() == ()
    assert tuple(event.event_type for event in adapter.event_observations()) == (
        AiJobEventType.REQUESTED,
        AiJobEventType.FAILED,
    )

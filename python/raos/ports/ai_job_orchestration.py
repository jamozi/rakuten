"""Inward ports for one-call recorded development AI job orchestration."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.ai.job_orchestration import (
    AiJobCommand,
    AiJobEventObservation,
    AiJobResult,
    ProviderExecutionOutcome,
    ProviderExecutionRequest,
    RecordedJobStateExchange,
    ValidationObservation,
    ValidationRequest,
)


@runtime_checkable
class RecordedAiProviderExecutionPort(Protocol):
    """Perform one explicitly scripted metadata-only provider observation."""

    def execute(self, *, request: ProviderExecutionRequest) -> ProviderExecutionOutcome:
        """Return one recorded outcome without exposing input or output bytes."""

        ...


@runtime_checkable
class RecordedAiValidationPort(Protocol):
    """Return one exact pre-scripted ST-0705 validation observation."""

    def observe(self, *, request: ValidationRequest) -> ValidationObservation:
        """Observe a recorded PASS, FAIL, or UNAVAILABLE result."""

        ...


@runtime_checkable
class RecordedAiJobStatePort(Protocol):
    """Atomically bind idempotency and job identities, then retain one result."""

    def exchange(self, *, command: AiJobCommand) -> RecordedJobStateExchange:
        """Reserve a new command or return its exact replay/conflict result."""

        ...

    def complete(self, *, command: AiJobCommand, result: AiJobResult) -> None:
        """Complete the exact reserved command once without replacement."""

        ...


@runtime_checkable
class RecordedAiJobEventSink(Protocol):
    """Append metadata-only requested and terminal AI event observations."""

    def append(self, *, event: AiJobEventObservation) -> None:
        """Append one observation; no update, delete, replay, or publish method."""

        ...


__all__ = [
    "RecordedAiJobEventSink",
    "RecordedAiJobStatePort",
    "RecordedAiProviderExecutionPort",
    "RecordedAiValidationPort",
]

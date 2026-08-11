"""Deterministic process-local fixtures for recorded ST-0706 orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import NoReturn, SupportsIndex, final
from uuid import UUID

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.job_orchestration import (
    AiJobCommand,
    AiJobEventObservation,
    AiJobEventType,
    AiJobResult,
    JobDisposition,
    OrchestrationFailureCode,
    ProviderExecutionOutcome,
    ProviderExecutionRequest,
    RecordedJobStateExchange,
    StateExchangeKind,
    ValidationObservation,
    ValidationRequest,
    fail_orchestration,
)


def _require_development(environment: object) -> RuntimeEnvironment:
    if (
        type(environment) is not RuntimeEnvironment
        or environment is not RuntimeEnvironment.ENV_DEV
    ):
        fail_orchestration(OrchestrationFailureCode.DEVELOPMENT_ONLY)
    return environment


def _require_capacity(capacity: object) -> int:
    if type(capacity) is not int or not 1 <= capacity <= (1 << 31) - 1:
        fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
    return capacity


def _normalize_provider_request(candidate: object) -> ProviderExecutionRequest | None:
    normalized: ProviderExecutionRequest | None = None
    failed = False
    if type(candidate) is ProviderExecutionRequest:
        try:
            normalized = ProviderExecutionRequest(
                operation_id=candidate.operation_id,
                command_fingerprint_sha256=candidate.command_fingerprint_sha256,
                ai_job_id=candidate.ai_job_id,
                ops_job_id=candidate.ops_job_id,
                task_code=candidate.task_code,
                attempt_number=candidate.attempt_number,
                authorization=candidate.authorization,
                input_artifact_id=candidate.input_artifact_id,
                input_artifact_sha256=candidate.input_artifact_sha256,
                deadline_at=candidate.deadline_at,
            )
        except Exception:
            failed = True
    if failed or normalized != candidate:
        return None
    return normalized


def _normalize_validation_request(candidate: object) -> ValidationRequest | None:
    normalized: ValidationRequest | None = None
    failed = False
    if type(candidate) is ValidationRequest:
        try:
            normalized = ValidationRequest(
                ai_job_id=candidate.ai_job_id,
                attempt_number=candidate.attempt_number,
                output_artifact_id=candidate.output_artifact_id,
                output_artifact_sha256=candidate.output_artifact_sha256,
                plan=candidate.plan,
            )
        except Exception:
            failed = True
    if failed or normalized != candidate:
        return None
    return normalized


def _normalize_command(candidate: object) -> AiJobCommand | None:
    normalized: AiJobCommand | None = None
    expected_fingerprint: object = None
    failed = False
    if type(candidate) is AiJobCommand:
        try:
            expected_fingerprint = candidate.fingerprint_sha256
            normalized = AiJobCommand(
                operation_id=candidate.operation_id,
                idempotency_key=candidate.idempotency_key,
                ai_job_id=candidate.ai_job_id,
                ops_job_id=candidate.ops_job_id,
                task_code=candidate.task_code,
                source_packet_version_id=candidate.source_packet_version_id,
                article_plan_id=candidate.article_plan_id,
                article_version_id=candidate.article_version_id,
                authorization=candidate.authorization,
                input_artifact_id=candidate.input_artifact_id,
                input_artifact_sha256=candidate.input_artifact_sha256,
                validation_plan=candidate.validation_plan,
                deadline_at=candidate.deadline_at,
                attempt_number=candidate.attempt_number,
                max_attempts=candidate.max_attempts,
                cancellation_requested=candidate.cancellation_requested,
                cancel_requested_at=candidate.cancel_requested_at,
            )
        except Exception:
            failed = True
    if (
        failed
        or normalized is None
        or normalized != candidate
        or normalized.fingerprint_sha256 != expected_fingerprint
    ):
        return None
    return normalized


def _normalize_result(candidate: object) -> AiJobResult | None:
    normalized: AiJobResult | None = None
    failed = False
    if type(candidate) is AiJobResult:
        try:
            normalized = AiJobResult(
                operation_id=candidate.operation_id,
                command_fingerprint_sha256=candidate.command_fingerprint_sha256,
                ai_job_id=candidate.ai_job_id,
                ops_job_id=candidate.ops_job_id,
                task_code=candidate.task_code,
                attempt_number=candidate.attempt_number,
                disposition=candidate.disposition,
                failure_code=candidate.failure_code,
                retryable=candidate.retryable,
                actual_cost_jpy=candidate.actual_cost_jpy,
                output_artifact_id=candidate.output_artifact_id,
                output_artifact_sha256=candidate.output_artifact_sha256,
                provider_request_id=candidate.provider_request_id,
                validation_status=candidate.validation_status,
                budget_receipt=candidate.budget_receipt,
            )
        except Exception:
            failed = True
    if failed or normalized != candidate:
        return None
    return normalized


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedProviderStep:
    """One exact request/outcome pair in the provider script."""

    request: ProviderExecutionRequest
    outcome: ProviderExecutionOutcome

    def __post_init__(self) -> None:
        request = _normalize_provider_request(self.request)
        if request is None or type(self.outcome) is not ProviderExecutionOutcome:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        if (
            self.outcome.ai_job_id != request.ai_job_id
            or self.outcome.attempt_number != request.attempt_number
        ):
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)

    def __repr__(self) -> str:
        return "RecordedProviderStep(<redacted-metadata>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded provider step serialization is unsupported")


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedValidationStep:
    """One exact request/observation pair in the validation script."""

    request: ValidationRequest
    observation: ValidationObservation

    def __post_init__(self) -> None:
        request = _normalize_validation_request(self.request)
        if request is None or type(self.observation) is not ValidationObservation:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        if (
            self.observation.ai_job_id != request.ai_job_id
            or self.observation.attempt_number != request.attempt_number
            or self.observation.output_artifact_id != request.output_artifact_id
            or self.observation.output_artifact_sha256 != request.output_artifact_sha256
            or self.observation.plan != request.plan
        ):
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)

    def __repr__(self) -> str:
        return "RecordedValidationStep(<redacted-metadata>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded validation step serialization is unsupported")


@dataclass(slots=True)
class _StateRecord:
    command: AiJobCommand
    result: AiJobResult | None = None


def _conflict_result(
    command: AiJobCommand, failure_code: OrchestrationFailureCode
) -> AiJobResult:
    return AiJobResult(
        operation_id=command.operation_id,
        command_fingerprint_sha256=command.fingerprint_sha256,
        ai_job_id=command.ai_job_id,
        ops_job_id=command.ops_job_id,
        task_code=command.task_code,
        attempt_number=command.attempt_number,
        disposition=JobDisposition.BLOCKED,
        failure_code=failure_code,
        retryable=False,
        actual_cost_jpy=None,
        output_artifact_id=None,
        output_artifact_sha256=None,
        provider_request_id=None,
        validation_status=None,
        budget_receipt=None,
    )


@final
class RecordedAiJobOrchestrationAdapter:
    """Closed scripted provider/validator plus append-only process-local records.

    ``capacity`` applies independently to provider calls, validation calls, new
    state bindings, completed results, and event observations.  No collection
    evicts data and this adapter exposes no mutation/reset/replay operation.
    """

    __slots__ = (
        "_ai_bindings",
        "_capacity",
        "_environment",
        "_event_records",
        "_events_by_fingerprint",
        "_lock",
        "_operations",
        "_ops_bindings",
        "_provider_cursor",
        "_provider_records",
        "_provider_script",
        "_validation_cursor",
        "_validation_records",
        "_validation_script",
    )

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        capacity: int,
        provider_script: tuple[RecordedProviderStep, ...],
        validation_script: tuple[RecordedValidationStep, ...],
    ) -> None:
        self._environment = _require_development(environment)
        self._capacity = _require_capacity(capacity)
        if type(provider_script) is not tuple or type(validation_script) is not tuple:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        if (
            len(provider_script) > self._capacity
            or len(validation_script) > self._capacity
        ):
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        if any(type(step) is not RecordedProviderStep for step in provider_script):
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        if any(type(step) is not RecordedValidationStep for step in validation_script):
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        provider_requests = [step.request for step in provider_script]
        validation_requests = [step.request for step in validation_script]
        if len(set(provider_requests)) != len(provider_requests):
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        if len(set(validation_requests)) != len(validation_requests):
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        self._provider_script = provider_script
        self._validation_script = validation_script
        self._provider_cursor = 0
        self._validation_cursor = 0
        self._provider_records: list[ProviderExecutionOutcome] = []
        self._validation_records: list[ValidationObservation] = []
        self._operations: dict[str, _StateRecord] = {}
        self._ai_bindings: dict[UUID, UUID] = {}
        self._ops_bindings: dict[UUID, UUID] = {}
        self._event_records: list[AiJobEventObservation] = []
        self._events_by_fingerprint: dict[str, list[AiJobEventType]] = {}
        self._lock = RLock()

    def execute(self, *, request: ProviderExecutionRequest) -> ProviderExecutionOutcome:
        normalized = _normalize_provider_request(request)
        if normalized is None:
            fail_orchestration(OrchestrationFailureCode.PROVIDER_OBSERVATION_INVALID)
        with self._lock:
            self._guard()
            if self._provider_cursor >= len(self._provider_script):
                fail_orchestration(
                    OrchestrationFailureCode.PROVIDER_OBSERVATION_INVALID
                )
            step = self._provider_script[self._provider_cursor]
            if step.request != normalized:
                fail_orchestration(
                    OrchestrationFailureCode.PROVIDER_OBSERVATION_INVALID
                )
            if len(self._provider_records) >= self._capacity:
                fail_orchestration(OrchestrationFailureCode.STATE_EXCHANGE_FAILURE)
            self._provider_cursor += 1
            self._provider_records.append(step.outcome)
            return step.outcome

    def observe(self, *, request: ValidationRequest) -> ValidationObservation:
        normalized = _normalize_validation_request(request)
        if normalized is None:
            fail_orchestration(OrchestrationFailureCode.VALIDATION_OBSERVATION_INVALID)
        with self._lock:
            self._guard()
            if self._validation_cursor >= len(self._validation_script):
                fail_orchestration(
                    OrchestrationFailureCode.VALIDATION_OBSERVATION_INVALID
                )
            step = self._validation_script[self._validation_cursor]
            if step.request != normalized:
                fail_orchestration(
                    OrchestrationFailureCode.VALIDATION_OBSERVATION_INVALID
                )
            if len(self._validation_records) >= self._capacity:
                fail_orchestration(OrchestrationFailureCode.STATE_EXCHANGE_FAILURE)
            self._validation_cursor += 1
            self._validation_records.append(step.observation)
            return step.observation

    def exchange(self, *, command: AiJobCommand) -> RecordedJobStateExchange:
        normalized = _normalize_command(command)
        if normalized is None:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
        with self._lock:
            self._guard()
            existing = self._operations.get(normalized.operation_id)
            if existing is not None:
                if existing.command.fingerprint_sha256 != normalized.fingerprint_sha256:
                    return RecordedJobStateExchange(
                        kind=StateExchangeKind.IDEMPOTENCY_MISMATCH,
                        result=_conflict_result(
                            normalized,
                            OrchestrationFailureCode.IDEMPOTENCY_MISMATCH,
                        ),
                    )
                if existing.result is None:
                    fail_orchestration(OrchestrationFailureCode.STATE_EXCHANGE_FAILURE)
                return RecordedJobStateExchange(
                    kind=StateExchangeKind.REPLAY,
                    result=existing.result,
                )

            bound_ops_id = self._ai_bindings.get(normalized.ai_job_id)
            if bound_ops_id is not None:
                return RecordedJobStateExchange(
                    kind=StateExchangeKind.AI_JOB_ID_CONFLICT,
                    result=_conflict_result(
                        normalized,
                        OrchestrationFailureCode.AI_JOB_ID_CONFLICT,
                    ),
                )
            bound_ai_id = self._ops_bindings.get(normalized.ops_job_id)
            if bound_ai_id is not None:
                return RecordedJobStateExchange(
                    kind=StateExchangeKind.OPS_JOB_ID_CONFLICT,
                    result=_conflict_result(
                        normalized,
                        OrchestrationFailureCode.OPS_JOB_ID_CONFLICT,
                    ),
                )
            if len(self._operations) >= self._capacity:
                fail_orchestration(OrchestrationFailureCode.STATE_EXCHANGE_FAILURE)
            self._operations[normalized.operation_id] = _StateRecord(command=normalized)
            self._ai_bindings[normalized.ai_job_id] = normalized.ops_job_id
            self._ops_bindings[normalized.ops_job_id] = normalized.ai_job_id
            return RecordedJobStateExchange(kind=StateExchangeKind.NEW, result=None)

    def complete(self, *, command: AiJobCommand, result: AiJobResult) -> None:
        normalized_command = _normalize_command(command)
        normalized_result = _normalize_result(result)
        if normalized_command is None or normalized_result is None:
            fail_orchestration(OrchestrationFailureCode.STATE_EXCHANGE_FAILURE)
        with self._lock:
            self._guard()
            record = self._operations.get(normalized_command.operation_id)
            if (
                record is None
                or record.command != normalized_command
                or record.result is not None
                or normalized_result.operation_id != normalized_command.operation_id
                or normalized_result.command_fingerprint_sha256
                != normalized_command.fingerprint_sha256
                or normalized_result.ai_job_id != normalized_command.ai_job_id
                or normalized_result.ops_job_id != normalized_command.ops_job_id
                or normalized_result.task_code != normalized_command.task_code
                or normalized_result.attempt_number != normalized_command.attempt_number
            ):
                fail_orchestration(OrchestrationFailureCode.STATE_EXCHANGE_FAILURE)
            record.result = normalized_result

    def append(self, *, event: AiJobEventObservation) -> None:
        if type(event) is not AiJobEventObservation:
            fail_orchestration(OrchestrationFailureCode.EVENT_RECORDING_FAILURE)
        with self._lock:
            self._guard()
            if len(self._event_records) >= self._capacity:
                fail_orchestration(OrchestrationFailureCode.EVENT_RECORDING_FAILURE)
            sequence = self._events_by_fingerprint.setdefault(
                event.command_fingerprint_sha256, []
            )
            if event.event_type is AiJobEventType.REQUESTED:
                if sequence:
                    fail_orchestration(OrchestrationFailureCode.EVENT_RECORDING_FAILURE)
            elif sequence != [AiJobEventType.REQUESTED]:
                fail_orchestration(OrchestrationFailureCode.EVENT_RECORDING_FAILURE)
            sequence.append(event.event_type)
            self._event_records.append(event)

    def provider_outcomes(self) -> tuple[ProviderExecutionOutcome, ...]:
        with self._lock:
            self._guard()
            return tuple(self._provider_records)

    def validation_observations(self) -> tuple[ValidationObservation, ...]:
        with self._lock:
            self._guard()
            return tuple(self._validation_records)

    def completed_results(self) -> tuple[AiJobResult, ...]:
        with self._lock:
            self._guard()
            return tuple(
                record.result
                for record in self._operations.values()
                if record.result is not None
            )

    def event_observations(self) -> tuple[AiJobEventObservation, ...]:
        with self._lock:
            self._guard()
            return tuple(self._event_records)

    def __repr__(self) -> str:
        return (
            "RecordedAiJobOrchestrationAdapter("
            "environment='ENV-DEV', state=<redacted-metadata>)"
        )

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded orchestration adapter serialization is unsupported")

    def _guard(self) -> None:
        _require_development(self._environment)


__all__ = [
    "RecordedAiJobOrchestrationAdapter",
    "RecordedProviderStep",
    "RecordedValidationStep",
]

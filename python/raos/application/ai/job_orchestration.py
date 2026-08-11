"""One-attempt recorded AI job orchestration for the exact ENV-DEV boundary."""

from __future__ import annotations

from datetime import datetime
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
    ProviderFailureClass,
    ProviderOutcomeKind,
    RecordedJobStateExchange,
    StateExchangeKind,
    ValidationObservation,
    ValidationRequest,
    ValidationStatus,
    fail_orchestration,
    require_orchestration_utc,
)
from raos.domain.ai.routing import (
    AuthorizedRouteReservation,
    BudgetCommit,
    BudgetRelease,
    BudgetReservation,
)
from raos.ports.ai_job_orchestration import (
    RecordedAiJobEventSink,
    RecordedAiJobStatePort,
    RecordedAiProviderExecutionPort,
    RecordedAiValidationPort,
)
from raos.ports.ai_routing import DevelopmentAiControlPort


def _require_development(environment: object) -> RuntimeEnvironment:
    if (
        type(environment) is not RuntimeEnvironment
        or environment is not RuntimeEnvironment.ENV_DEV
    ):
        fail_orchestration(OrchestrationFailureCode.DEVELOPMENT_ONLY)
    return environment


def _supports(candidate: object, protocol: type[object]) -> bool:
    supported = False
    try:
        supported = isinstance(candidate, protocol)
    except Exception:
        pass
    return supported


def _normalize_reservation(candidate: object) -> BudgetReservation | None:
    normalized: BudgetReservation | None = None
    failed = False
    if type(candidate) is BudgetReservation:
        try:
            normalized = BudgetReservation(
                reservation_id=candidate.reservation_id,
                operation_id=candidate.operation_id,
                intent_sha256=candidate.intent_sha256,
                identity=candidate.identity,
                quote_sha256=candidate.quote_sha256,
                reserved_jpy=candidate.reserved_jpy,
                reserved_at=candidate.reserved_at,
                expires_at=candidate.expires_at,
            )
        except Exception:
            failed = True
    if failed or normalized != candidate:
        return None
    # The ST-0704 control port deliberately binds the process-local handle by
    # object identity.  Return the validated original handle, not its copy.
    return candidate


def _normalize_authorization(candidate: object) -> AuthorizedRouteReservation | None:
    normalized: AuthorizedRouteReservation | None = None
    failed = False
    if type(candidate) is AuthorizedRouteReservation:
        reservation = _normalize_reservation(candidate.reservation)
        if reservation is None:
            return None
        try:
            normalized = AuthorizedRouteReservation(
                identity=candidate.identity,
                certification_id=candidate.certification_id,
                task_binding_sha256=candidate.task_binding_sha256,
                route_sha256=candidate.route_sha256,
                reservation=reservation,
            )
        except Exception:
            failed = True
    if failed or normalized != candidate:
        return None
    return normalized


def _normalize_command(candidate: object) -> AiJobCommand:
    normalized: AiJobCommand | None = None
    expected_fingerprint: object = None
    failed = False
    if type(candidate) is AiJobCommand:
        authorization = _normalize_authorization(candidate.authorization)
        if authorization is None:
            fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
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
                authorization=authorization,
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
        or normalized.fingerprint_sha256 != expected_fingerprint
    ):
        fail_orchestration(OrchestrationFailureCode.INVALID_REQUEST)
    return normalized


def _normalize_provider_outcome(candidate: object) -> ProviderExecutionOutcome | None:
    normalized: ProviderExecutionOutcome | None = None
    failed = False
    if type(candidate) is ProviderExecutionOutcome:
        try:
            normalized = ProviderExecutionOutcome(
                kind=candidate.kind,
                ai_job_id=candidate.ai_job_id,
                attempt_number=candidate.attempt_number,
                provider_request_id=candidate.provider_request_id,
                output_artifact_id=candidate.output_artifact_id,
                output_artifact_sha256=candidate.output_artifact_sha256,
                input_tokens=candidate.input_tokens,
                output_tokens=candidate.output_tokens,
                total_tokens=candidate.total_tokens,
                actual_cost_jpy=candidate.actual_cost_jpy,
                failure_class=candidate.failure_class,
                retryable=candidate.retryable,
            )
        except Exception:
            failed = True
    if failed or normalized != candidate:
        return None
    return normalized


def _normalize_validation(candidate: object) -> ValidationObservation | None:
    normalized: ValidationObservation | None = None
    failed = False
    if type(candidate) is ValidationObservation:
        try:
            normalized = ValidationObservation(
                status=candidate.status,
                ai_job_id=candidate.ai_job_id,
                attempt_number=candidate.attempt_number,
                output_artifact_id=candidate.output_artifact_id,
                output_artifact_sha256=candidate.output_artifact_sha256,
                plan=candidate.plan,
                failure_class=candidate.failure_class,
            )
        except Exception:
            failed = True
    if failed or normalized != candidate:
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


def _result_matches_command(result: AiJobResult, command: AiJobCommand) -> bool:
    return (
        result.operation_id == command.operation_id
        and result.command_fingerprint_sha256 == command.fingerprint_sha256
        and result.ai_job_id == command.ai_job_id
        and result.ops_job_id == command.ops_job_id
        and result.task_code == command.task_code
        and result.attempt_number == command.attempt_number
    )


class DevelopmentRecordedAiJobOrchestrationService:
    """Execute at most one recorded provider attempt for an authorized job."""

    __slots__ = (
        "_controls",
        "_environment",
        "_events",
        "_provider",
        "_state",
        "_validation",
    )

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        provider: RecordedAiProviderExecutionPort,
        validation: RecordedAiValidationPort,
        state: RecordedAiJobStatePort,
        events: RecordedAiJobEventSink,
        controls: DevelopmentAiControlPort,
    ) -> None:
        self._environment = _require_development(environment)
        if not _supports(provider, RecordedAiProviderExecutionPort):
            raise TypeError("provider must implement RecordedAiProviderExecutionPort")
        if not _supports(validation, RecordedAiValidationPort):
            raise TypeError("validation must implement RecordedAiValidationPort")
        if not _supports(state, RecordedAiJobStatePort):
            raise TypeError("state must implement RecordedAiJobStatePort")
        if not _supports(events, RecordedAiJobEventSink):
            raise TypeError("events must implement RecordedAiJobEventSink")
        if not _supports(controls, DevelopmentAiControlPort):
            raise TypeError("controls must implement DevelopmentAiControlPort")
        self._provider = provider
        self._validation = validation
        self._state = state
        self._events = events
        self._controls = controls

    def execute(self, *, command: AiJobCommand, now: datetime) -> AiJobResult:
        """Run one attempt with no loop, scheduling, fallback, or retry action."""

        self._guard()
        normalized_command = _normalize_command(command)
        observed_at = require_orchestration_utc(now)
        exchange = self._exchange(command=normalized_command)
        if exchange.kind is not StateExchangeKind.NEW:
            if exchange.result is None:
                fail_orchestration(OrchestrationFailureCode.STATE_EXCHANGE_FAILURE)
            return exchange.result

        requested = self._requested_event(normalized_command)
        if not self._append_event(requested):
            release_receipt, release_failure = self._release(
                authorization=normalized_command.authorization,
                now=observed_at,
            )
            result = self._make_result(
                command=normalized_command,
                disposition=JobDisposition.QUARANTINED,
                failure_code=(
                    release_failure
                    if release_failure is not None
                    else OrchestrationFailureCode.EVENT_RECORDING_FAILURE
                ),
                retryable=False,
                budget_receipt=release_receipt,
            )
            return self._complete(command=normalized_command, result=result)

        if normalized_command.cancellation_requested:
            return self._before_provider_failure(
                command=normalized_command,
                now=observed_at,
                disposition=JobDisposition.CANCELLED,
                failure_code=OrchestrationFailureCode.CANCELLATION_REQUESTED,
            )
        if observed_at >= normalized_command.deadline_at:
            return self._before_provider_failure(
                command=normalized_command,
                now=observed_at,
                disposition=JobDisposition.EXPIRED,
                failure_code=OrchestrationFailureCode.DEADLINE_EXPIRED,
            )

        provider_request = ProviderExecutionRequest.from_command(normalized_command)
        outcome = self._execute_provider(provider_request)
        if (
            outcome is None
            or outcome.ai_job_id != normalized_command.ai_job_id
            or outcome.attempt_number != normalized_command.attempt_number
        ):
            return self._unknown_provider_cost_failure(
                command=normalized_command,
                now=observed_at,
            )

        reserved_jpy = normalized_command.authorization.reservation.reserved_jpy
        if (
            outcome.actual_cost_jpy is not None
            and outcome.actual_cost_jpy > reserved_jpy
        ):
            cost_receipt, budget_failure = self._commit(
                authorization=normalized_command.authorization,
                committed_jpy=reserved_jpy,
                now=observed_at,
            )
            circuit_ok = self._trip_circuit(
                authorization=normalized_command.authorization,
                now=observed_at,
            )
            result = self._make_result(
                command=normalized_command,
                disposition=JobDisposition.QUARANTINED,
                failure_code=(
                    budget_failure
                    if budget_failure is not None
                    else (
                        OrchestrationFailureCode.COST_EXCEEDED
                        if circuit_ok
                        else OrchestrationFailureCode.BUDGET_CONTROL_FAILURE
                    )
                ),
                retryable=False,
                provider_request_id=outcome.provider_request_id,
                budget_receipt=cost_receipt,
            )
            return self._terminal_failure(command=normalized_command, result=result)

        if outcome.kind is not ProviderOutcomeKind.SUCCEEDED:
            return self._provider_failure(
                command=normalized_command,
                outcome=outcome,
                now=observed_at,
            )

        if (
            outcome.output_artifact_id is None
            or outcome.output_artifact_sha256 is None
            or outcome.actual_cost_jpy is None
        ):
            return self._unknown_provider_cost_failure(
                command=normalized_command,
                now=observed_at,
            )
        validation_request = ValidationRequest(
            ai_job_id=normalized_command.ai_job_id,
            attempt_number=normalized_command.attempt_number,
            output_artifact_id=outcome.output_artifact_id,
            output_artifact_sha256=outcome.output_artifact_sha256,
            plan=normalized_command.validation_plan,
        )
        validation = self._observe_validation(validation_request)
        validation_matches = (
            validation is not None
            and validation.ai_job_id == validation_request.ai_job_id
            and validation.attempt_number == validation_request.attempt_number
            and validation.output_artifact_id == validation_request.output_artifact_id
            and validation.output_artifact_sha256
            == validation_request.output_artifact_sha256
            and validation.plan == validation_request.plan
        )
        validation_cost_receipt, budget_failure = self._commit(
            authorization=normalized_command.authorization,
            committed_jpy=outcome.actual_cost_jpy,
            now=observed_at,
        )
        if budget_failure is not None:
            result = self._make_result(
                command=normalized_command,
                disposition=JobDisposition.QUARANTINED,
                failure_code=budget_failure,
                retryable=False,
                actual_cost_jpy=outcome.actual_cost_jpy,
                output_artifact_id=outcome.output_artifact_id,
                output_artifact_sha256=outcome.output_artifact_sha256,
                provider_request_id=outcome.provider_request_id,
                validation_status=(
                    validation.status
                    if validation is not None and validation_matches
                    else None
                ),
                budget_receipt=validation_cost_receipt,
            )
            return self._terminal_failure(command=normalized_command, result=result)
        if not validation_matches:
            result = self._make_result(
                command=normalized_command,
                disposition=JobDisposition.QUARANTINED,
                failure_code=OrchestrationFailureCode.VALIDATION_OBSERVATION_INVALID,
                retryable=False,
                actual_cost_jpy=outcome.actual_cost_jpy,
                output_artifact_id=outcome.output_artifact_id,
                output_artifact_sha256=outcome.output_artifact_sha256,
                provider_request_id=outcome.provider_request_id,
                budget_receipt=validation_cost_receipt,
            )
            return self._terminal_failure(command=normalized_command, result=result)
        if validation is None:
            fail_orchestration(OrchestrationFailureCode.VALIDATION_OBSERVATION_INVALID)
        if validation.status is not ValidationStatus.PASS:
            failure_code = (
                OrchestrationFailureCode.VALIDATION_UNAVAILABLE
                if validation.status is ValidationStatus.UNAVAILABLE
                else OrchestrationFailureCode.VALIDATION_FAILED
            )
            disposition = (
                JobDisposition.BLOCKED
                if validation.status is ValidationStatus.FAIL
                else JobDisposition.QUARANTINED
            )
            result = self._make_result(
                command=normalized_command,
                disposition=disposition,
                failure_code=failure_code,
                retryable=False,
                actual_cost_jpy=outcome.actual_cost_jpy,
                output_artifact_id=outcome.output_artifact_id,
                output_artifact_sha256=outcome.output_artifact_sha256,
                provider_request_id=outcome.provider_request_id,
                validation_status=validation.status,
                budget_receipt=validation_cost_receipt,
            )
            return self._terminal_failure(command=normalized_command, result=result)

        result = self._make_result(
            command=normalized_command,
            disposition=JobDisposition.SUCCEEDED,
            failure_code=None,
            retryable=False,
            actual_cost_jpy=outcome.actual_cost_jpy,
            output_artifact_id=outcome.output_artifact_id,
            output_artifact_sha256=outcome.output_artifact_sha256,
            provider_request_id=outcome.provider_request_id,
            validation_status=ValidationStatus.PASS,
            budget_receipt=validation_cost_receipt,
        )
        succeeded_event = self._succeeded_event(normalized_command, result)
        if not self._append_event(succeeded_event):
            failed_result = self._make_result(
                command=normalized_command,
                disposition=JobDisposition.QUARANTINED,
                failure_code=OrchestrationFailureCode.EVENT_RECORDING_FAILURE,
                retryable=False,
                actual_cost_jpy=outcome.actual_cost_jpy,
                output_artifact_id=outcome.output_artifact_id,
                output_artifact_sha256=outcome.output_artifact_sha256,
                provider_request_id=outcome.provider_request_id,
                validation_status=ValidationStatus.PASS,
                budget_receipt=validation_cost_receipt,
            )
            return self._complete(command=normalized_command, result=failed_result)
        return self._complete(command=normalized_command, result=result)

    def _exchange(self, *, command: AiJobCommand) -> RecordedJobStateExchange:
        candidate: object = None
        failed = False
        try:
            candidate = self._state.exchange(command=command)
        except Exception:
            failed = True
        if failed or type(candidate) is not RecordedJobStateExchange:
            fail_orchestration(OrchestrationFailureCode.STATE_EXCHANGE_FAILURE)
        normalized: RecordedJobStateExchange | None = None
        try:
            normalized = RecordedJobStateExchange(
                kind=candidate.kind,
                result=(
                    _normalize_result(candidate.result)
                    if candidate.result is not None
                    else None
                ),
            )
        except Exception:
            failed = True
        if failed or normalized is None or normalized != candidate:
            fail_orchestration(OrchestrationFailureCode.STATE_EXCHANGE_FAILURE)
        if normalized.kind is StateExchangeKind.NEW:
            return normalized
        result = normalized.result
        if result is None or not _result_matches_command(result, command):
            fail_orchestration(OrchestrationFailureCode.STATE_EXCHANGE_FAILURE)
        expected_failures = {
            StateExchangeKind.IDEMPOTENCY_MISMATCH: (
                OrchestrationFailureCode.IDEMPOTENCY_MISMATCH
            ),
            StateExchangeKind.AI_JOB_ID_CONFLICT: (
                OrchestrationFailureCode.AI_JOB_ID_CONFLICT
            ),
            StateExchangeKind.OPS_JOB_ID_CONFLICT: (
                OrchestrationFailureCode.OPS_JOB_ID_CONFLICT
            ),
        }
        expected_failure = expected_failures.get(normalized.kind)
        if expected_failure is not None and (
            result.disposition is not JobDisposition.BLOCKED
            or result.failure_code is not expected_failure
        ):
            fail_orchestration(OrchestrationFailureCode.STATE_EXCHANGE_FAILURE)
        return normalized

    def _execute_provider(
        self, request: ProviderExecutionRequest
    ) -> ProviderExecutionOutcome | None:
        candidate: object = None
        failed = False
        try:
            candidate = self._provider.execute(request=request)
        except Exception:
            failed = True
        if failed:
            return None
        return _normalize_provider_outcome(candidate)

    def _observe_validation(
        self, request: ValidationRequest
    ) -> ValidationObservation | None:
        candidate: object = None
        failed = False
        try:
            candidate = self._validation.observe(request=request)
        except Exception:
            failed = True
        if failed:
            return None
        return _normalize_validation(candidate)

    def _append_event(self, event: AiJobEventObservation) -> bool:
        failed = False
        try:
            self._events.append(event=event)
        except Exception:
            failed = True
        return not failed

    def _commit(
        self,
        *,
        authorization: AuthorizedRouteReservation,
        committed_jpy: int,
        now: datetime,
    ) -> tuple[BudgetCommit | None, OrchestrationFailureCode | None]:
        candidate: object = None
        failed = False
        try:
            candidate = self._controls.commit(
                reservation=authorization.reservation,
                committed_jpy=committed_jpy,
                now=now,
            )
        except Exception:
            failed = True
        if failed:
            return None, OrchestrationFailureCode.BUDGET_CONTROL_FAILURE
        normalized: BudgetCommit | None = None
        normalization_failed = False
        if type(candidate) is BudgetCommit:
            try:
                normalized = BudgetCommit(
                    reservation_id=candidate.reservation_id,
                    intent_sha256=candidate.intent_sha256,
                    committed_jpy=candidate.committed_jpy,
                    committed_at=candidate.committed_at,
                )
            except Exception:
                normalization_failed = True
        expected = BudgetCommit(
            reservation_id=authorization.reservation.reservation_id,
            intent_sha256=authorization.reservation.intent_sha256,
            committed_jpy=committed_jpy,
            committed_at=now,
        )
        if normalization_failed or normalized != expected:
            return None, OrchestrationFailureCode.BUDGET_RECEIPT_MISMATCH
        return normalized, None

    def _release(
        self,
        *,
        authorization: AuthorizedRouteReservation,
        now: datetime,
    ) -> tuple[BudgetRelease | None, OrchestrationFailureCode | None]:
        candidate: object = None
        failed = False
        try:
            candidate = self._controls.release(
                reservation=authorization.reservation,
                now=now,
            )
        except Exception:
            failed = True
        if failed:
            return None, OrchestrationFailureCode.BUDGET_CONTROL_FAILURE
        normalized: BudgetRelease | None = None
        normalization_failed = False
        if type(candidate) is BudgetRelease:
            try:
                normalized = BudgetRelease(
                    reservation_id=candidate.reservation_id,
                    intent_sha256=candidate.intent_sha256,
                    released_jpy=candidate.released_jpy,
                    released_at=candidate.released_at,
                )
            except Exception:
                normalization_failed = True
        expected = BudgetRelease(
            reservation_id=authorization.reservation.reservation_id,
            intent_sha256=authorization.reservation.intent_sha256,
            released_jpy=authorization.reservation.reserved_jpy,
            released_at=now,
        )
        if normalization_failed or normalized != expected:
            return None, OrchestrationFailureCode.BUDGET_RECEIPT_MISMATCH
        return normalized, None

    def _trip_circuit(
        self, *, authorization: AuthorizedRouteReservation, now: datetime
    ) -> bool:
        failed = False
        try:
            self._controls.trip_open(identity=authorization.identity, now=now)
        except Exception:
            failed = True
        return not failed

    def _before_provider_failure(
        self,
        *,
        command: AiJobCommand,
        now: datetime,
        disposition: JobDisposition,
        failure_code: OrchestrationFailureCode,
    ) -> AiJobResult:
        release_receipt, release_failure = self._release(
            authorization=command.authorization,
            now=now,
        )
        result = self._make_result(
            command=command,
            disposition=(
                disposition if release_failure is None else JobDisposition.QUARANTINED
            ),
            failure_code=(failure_code if release_failure is None else release_failure),
            retryable=False,
            budget_receipt=release_receipt,
        )
        return self._terminal_failure(command=command, result=result)

    def _unknown_provider_cost_failure(
        self, *, command: AiJobCommand, now: datetime
    ) -> AiJobResult:
        reserved_jpy = command.authorization.reservation.reserved_jpy
        commit_receipt, budget_failure = self._commit(
            authorization=command.authorization,
            committed_jpy=reserved_jpy,
            now=now,
        )
        circuit_ok = self._trip_circuit(
            authorization=command.authorization,
            now=now,
        )
        result = self._make_result(
            command=command,
            disposition=JobDisposition.QUARANTINED,
            failure_code=(
                budget_failure
                if budget_failure is not None
                else (
                    OrchestrationFailureCode.PROVIDER_OBSERVATION_INVALID
                    if circuit_ok
                    else OrchestrationFailureCode.BUDGET_CONTROL_FAILURE
                )
            ),
            retryable=False,
            budget_receipt=commit_receipt,
        )
        return self._terminal_failure(command=command, result=result)

    def _provider_failure(
        self,
        *,
        command: AiJobCommand,
        outcome: ProviderExecutionOutcome,
        now: datetime,
    ) -> AiJobResult:
        committed_jpy = (
            outcome.actual_cost_jpy
            if outcome.actual_cost_jpy is not None
            else command.authorization.reservation.reserved_jpy
        )
        commit_receipt, budget_failure = self._commit(
            authorization=command.authorization,
            committed_jpy=committed_jpy,
            now=now,
        )
        retry_deferred = (
            outcome.retryable and command.attempt_number < command.max_attempts
        )
        disposition = (
            JobDisposition.RETRY_DEFERRED
            if retry_deferred
            else self._provider_failure_disposition(outcome)
        )
        failure_code = (
            budget_failure
            if budget_failure is not None
            else self._provider_failure_code(outcome)
        )
        if budget_failure is not None:
            disposition = JobDisposition.QUARANTINED
            retry_deferred = False
        result = self._make_result(
            command=command,
            disposition=disposition,
            failure_code=failure_code,
            retryable=retry_deferred,
            actual_cost_jpy=(
                outcome.actual_cost_jpy if outcome.actual_cost_jpy is not None else None
            ),
            provider_request_id=outcome.provider_request_id,
            budget_receipt=commit_receipt,
        )
        return self._terminal_failure(command=command, result=result)

    @staticmethod
    def _provider_failure_code(
        outcome: ProviderExecutionOutcome,
    ) -> OrchestrationFailureCode:
        if outcome.kind is ProviderOutcomeKind.REFUSED:
            return OrchestrationFailureCode.PROVIDER_REFUSAL
        if outcome.kind is ProviderOutcomeKind.TIMED_OUT:
            return OrchestrationFailureCode.PROVIDER_TIMEOUT
        return OrchestrationFailureCode.PROVIDER_FAILURE

    @staticmethod
    def _provider_failure_disposition(
        outcome: ProviderExecutionOutcome,
    ) -> JobDisposition:
        if outcome.kind is ProviderOutcomeKind.REFUSED or outcome.failure_class in {
            ProviderFailureClass.CONTENT_FILTER,
            ProviderFailureClass.POLICY,
        }:
            return JobDisposition.BLOCKED
        if outcome.failure_class in {
            ProviderFailureClass.AUTH,
            ProviderFailureClass.BUDGET,
            ProviderFailureClass.CONTRACT,
        }:
            return JobDisposition.QUARANTINED
        return JobDisposition.FAILED_TERMINAL

    def _terminal_failure(
        self, *, command: AiJobCommand, result: AiJobResult
    ) -> AiJobResult:
        failed_event = self._failed_event(command, result)
        if not self._append_event(failed_event):
            result = self._make_result(
                command=command,
                disposition=JobDisposition.QUARANTINED,
                failure_code=OrchestrationFailureCode.EVENT_RECORDING_FAILURE,
                retryable=False,
                actual_cost_jpy=result.actual_cost_jpy,
                output_artifact_id=result.output_artifact_id,
                output_artifact_sha256=result.output_artifact_sha256,
                provider_request_id=result.provider_request_id,
                validation_status=result.validation_status,
                budget_receipt=result.budget_receipt,
            )
        return self._complete(command=command, result=result)

    def _complete(self, *, command: AiJobCommand, result: AiJobResult) -> AiJobResult:
        failed = False
        try:
            self._state.complete(command=command, result=result)
        except Exception:
            failed = True
        if failed:
            fail_orchestration(OrchestrationFailureCode.STATE_EXCHANGE_FAILURE)
        return result

    @staticmethod
    def _make_result(
        *,
        command: AiJobCommand,
        disposition: JobDisposition,
        failure_code: OrchestrationFailureCode | None,
        retryable: bool,
        actual_cost_jpy: int | None = None,
        output_artifact_id: UUID | None = None,
        output_artifact_sha256: str | None = None,
        provider_request_id: str | None = None,
        validation_status: ValidationStatus | None = None,
        budget_receipt: BudgetCommit | BudgetRelease | None = None,
    ) -> AiJobResult:
        return AiJobResult(
            operation_id=command.operation_id,
            command_fingerprint_sha256=command.fingerprint_sha256,
            ai_job_id=command.ai_job_id,
            ops_job_id=command.ops_job_id,
            task_code=command.task_code,
            attempt_number=command.attempt_number,
            disposition=disposition,
            failure_code=failure_code,
            retryable=retryable,
            actual_cost_jpy=actual_cost_jpy,
            output_artifact_id=output_artifact_id,
            output_artifact_sha256=output_artifact_sha256,
            provider_request_id=provider_request_id,
            validation_status=validation_status,
            budget_receipt=budget_receipt,
        )

    @staticmethod
    def _requested_event(command: AiJobCommand) -> AiJobEventObservation:
        return AiJobEventObservation(
            event_type=AiJobEventType.REQUESTED,
            operation_id=command.operation_id,
            command_fingerprint_sha256=command.fingerprint_sha256,
            ai_job_id=command.ai_job_id,
            ops_job_id=command.ops_job_id,
            task_code=command.task_code,
            attempt_number=command.attempt_number,
            reserved_jpy=command.authorization.reservation.reserved_jpy,
            disposition=None,
            failure_code=None,
            retryable=None,
            actual_cost_jpy=None,
            output_artifact_id=None,
            output_artifact_sha256=None,
            validation_passed=None,
        )

    @staticmethod
    def _succeeded_event(
        command: AiJobCommand, result: AiJobResult
    ) -> AiJobEventObservation:
        return AiJobEventObservation(
            event_type=AiJobEventType.SUCCEEDED,
            operation_id=command.operation_id,
            command_fingerprint_sha256=command.fingerprint_sha256,
            ai_job_id=command.ai_job_id,
            ops_job_id=command.ops_job_id,
            task_code=command.task_code,
            attempt_number=command.attempt_number,
            reserved_jpy=command.authorization.reservation.reserved_jpy,
            disposition=result.disposition,
            failure_code=None,
            retryable=False,
            actual_cost_jpy=result.actual_cost_jpy,
            output_artifact_id=result.output_artifact_id,
            output_artifact_sha256=result.output_artifact_sha256,
            validation_passed=True,
        )

    @staticmethod
    def _failed_event(
        command: AiJobCommand, result: AiJobResult
    ) -> AiJobEventObservation:
        return AiJobEventObservation(
            event_type=AiJobEventType.FAILED,
            operation_id=command.operation_id,
            command_fingerprint_sha256=command.fingerprint_sha256,
            ai_job_id=command.ai_job_id,
            ops_job_id=command.ops_job_id,
            task_code=command.task_code,
            attempt_number=command.attempt_number,
            reserved_jpy=command.authorization.reservation.reserved_jpy,
            disposition=result.disposition,
            failure_code=result.failure_code,
            retryable=result.retryable,
            actual_cost_jpy=result.actual_cost_jpy,
            output_artifact_id=result.output_artifact_id,
            output_artifact_sha256=result.output_artifact_sha256,
            validation_passed=False,
        )

    def _guard(self) -> None:
        _require_development(self._environment)


__all__ = ["DevelopmentRecordedAiJobOrchestrationService"]

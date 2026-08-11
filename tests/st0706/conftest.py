"""Metadata-only fixtures for the isolated ST-0706 suite."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
from uuid import UUID


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.adapters.development_ai_controls import (  # noqa: E402
    InMemoryDevelopmentAiControls,
)
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.ai.job_orchestration import (  # noqa: E402
    AiJobCommand,
    ProviderExecutionOutcome,
    ProviderExecutionRequest,
    ProviderFailureClass,
    ProviderOutcomeKind,
    ValidationFailureClass,
    ValidationObservation,
    ValidationPlanBinding,
    ValidationRequest,
    ValidationStatus,
)
from raos.domain.ai.routing import (  # noqa: E402
    AuthorizedRouteReservation,
    ReservationIntent,
    RouteIdentity,
)


NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
TASK_CODE = "ai.article_draft.v1"
IDENTITY = RouteIdentity(
    task_code=TASK_CODE,
    route_code="route.editorial_balanced.v1",
    route_version="synthetic.route-version.st0706.v1",
    model_id="synthetic.model.st0706.v1",
)
PLAN = ValidationPlanBinding(
    plan_id="st-0705.ai-output-validation-reference-plan.v1",
    plan_sha256="ea935831a1bb667229ae5a5495a27a801b9c21ab3c3ddbe53e266b8f7c311c42",
)
AI_JOB_ID = UUID("00000000-0000-4000-8000-000000000706")
OPS_JOB_ID = UUID("00000000-0000-4000-8000-000000030303")
SOURCE_PACKET_ID = UUID("00000000-0000-4000-8000-000000060604")
ARTICLE_PLAN_ID = UUID("00000000-0000-4000-8000-000000080201")
INPUT_ARTIFACT_ID = UUID("00000000-0000-4000-8000-000000060601")
OUTPUT_ARTIFACT_ID = UUID("00000000-0000-4000-8000-000000070699")


def command_and_controls(
    *,
    operation_id: str = "operation.st0706.recorded.v1",
    ai_job_id: UUID = AI_JOB_ID,
    ops_job_id: UUID = OPS_JOB_ID,
    attempt_number: int = 1,
    max_attempts: int = 2,
    deadline_at: datetime = NOW + timedelta(minutes=4),
    cancellation_requested: bool = False,
    cancel_requested_at: datetime | None = None,
) -> tuple[AiJobCommand, InMemoryDevelopmentAiControls]:
    controls = InMemoryDevelopmentAiControls(
        environment=RuntimeEnvironment.ENV_DEV,
        synthetic_cap_jpy=50,
        initially_closed_routes=(IDENTITY,),
    )
    intent = ReservationIntent(
        operation_id=f"reservation.{operation_id}",
        identity=IDENTITY,
        task_binding_sha256="2" * 64,
        route_sha256="3" * 64,
        certification_id="synthetic.certification.st0706.v1",
        quote_sha256="4" * 64,
        reserved_jpy=10,
        authorized_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    reservation = controls.reserve(intent=intent, now=NOW)
    authorization = AuthorizedRouteReservation(
        identity=IDENTITY,
        certification_id="synthetic.certification.st0706.v1",
        task_binding_sha256="2" * 64,
        route_sha256="3" * 64,
        reservation=reservation,
    )
    command = AiJobCommand(
        operation_id=operation_id,
        idempotency_key="idempotency.st0706.recorded.v1",
        ai_job_id=ai_job_id,
        ops_job_id=ops_job_id,
        task_code=TASK_CODE,
        source_packet_version_id=SOURCE_PACKET_ID,
        article_plan_id=ARTICLE_PLAN_ID,
        article_version_id=None,
        authorization=authorization,
        input_artifact_id=INPUT_ARTIFACT_ID,
        input_artifact_sha256="5" * 64,
        validation_plan=PLAN,
        deadline_at=deadline_at,
        attempt_number=attempt_number,
        max_attempts=max_attempts,
        cancellation_requested=cancellation_requested,
        cancel_requested_at=cancel_requested_at,
    )
    return command, controls


def success_script(
    command: AiJobCommand,
) -> tuple[
    ProviderExecutionRequest,
    ProviderExecutionOutcome,
    ValidationRequest,
    ValidationObservation,
]:
    provider_request = ProviderExecutionRequest.from_command(command)
    outcome = ProviderExecutionOutcome(
        kind=ProviderOutcomeKind.SUCCEEDED,
        ai_job_id=command.ai_job_id,
        attempt_number=command.attempt_number,
        provider_request_id="provider-request.st0706.v1",
        output_artifact_id=OUTPUT_ARTIFACT_ID,
        output_artifact_sha256="6" * 64,
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        actual_cost_jpy=7,
        failure_class=None,
        retryable=False,
    )
    validation_request = ValidationRequest(
        ai_job_id=command.ai_job_id,
        attempt_number=command.attempt_number,
        output_artifact_id=OUTPUT_ARTIFACT_ID,
        output_artifact_sha256="6" * 64,
        plan=PLAN,
    )
    observation = ValidationObservation(
        status=ValidationStatus.PASS,
        ai_job_id=command.ai_job_id,
        attempt_number=command.attempt_number,
        output_artifact_id=OUTPUT_ARTIFACT_ID,
        output_artifact_sha256="6" * 64,
        plan=PLAN,
        failure_class=None,
    )
    return provider_request, outcome, validation_request, observation


def provider_failure(
    command: AiJobCommand,
    *,
    kind: ProviderOutcomeKind = ProviderOutcomeKind.FAILED,
    failure_class: ProviderFailureClass = ProviderFailureClass.TRANSIENT_ERROR,
    retryable: bool = True,
    actual_cost_jpy: int | None = 2,
) -> tuple[ProviderExecutionRequest, ProviderExecutionOutcome]:
    request = ProviderExecutionRequest.from_command(command)
    return request, ProviderExecutionOutcome(
        kind=kind,
        ai_job_id=command.ai_job_id,
        attempt_number=command.attempt_number,
        provider_request_id="provider-request.failure.st0706.v1",
        output_artifact_id=None,
        output_artifact_sha256=None,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        actual_cost_jpy=actual_cost_jpy,
        failure_class=failure_class,
        retryable=retryable,
    )


def validation_observation(
    command: AiJobCommand,
    *,
    status: ValidationStatus,
    failure_class: ValidationFailureClass | None,
) -> tuple[ValidationRequest, ValidationObservation]:
    request = ValidationRequest(
        ai_job_id=command.ai_job_id,
        attempt_number=command.attempt_number,
        output_artifact_id=OUTPUT_ARTIFACT_ID,
        output_artifact_sha256="6" * 64,
        plan=PLAN,
    )
    return request, ValidationObservation(
        status=status,
        ai_job_id=command.ai_job_id,
        attempt_number=command.attempt_number,
        output_artifact_id=OUTPUT_ARTIFACT_ID,
        output_artifact_sha256="6" * 64,
        plan=PLAN,
        failure_class=failure_class,
    )

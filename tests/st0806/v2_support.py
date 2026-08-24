"""Executable synthetic support for ST-0806 V2 tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from uuid import UUID

from raos.adapters.development_ai_controls import InMemoryDevelopmentAiControls
from raos.adapters.recorded_ai_draft_integration_v2 import (
    RecordedAiDraftIntegrationAdapterV2,
    RecordedAiDraftIntegrationStepV2,
)
from raos.adapters.recorded_durable_ai_job_queue_v2 import (
    RecordedDurableAiJobStateAdapterV2,
)
from raos.application.ai.durable_job_queue_v2 import (
    RecordedDurableAiJobQueueServiceV2,
)
from raos.application.editorial.ai_draft_integration_v2 import (
    AiDraftIntegrationServiceV2,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.durable_job_queue_v2 import (
    DurableQueueSnapshot,
    RecordedAttemptKind,
    RecordedAttemptOutcome,
    RecordedDurableQueueActivation,
)
from raos.domain.ai.job_orchestration import (
    AiJobCommand,
    ValidationPlanBinding,
    ValidationStatus,
)
from raos.domain.ai.routing import (
    AuthorizedRouteReservation,
    ReservationIntent,
    RouteIdentity,
)
from raos.domain.editorial.ai_draft_integration_v2 import (
    AiDraftIntegrationRequestV2,
    AiDraftV2Activation,
)
from raos.domain.editorial.article_lifecycle import (
    ArticleState,
    ArticleVersionState,
    BodySha256,
    SourcePacketVerification,
    VersionDisplayId,
    VersionSnapshot,
)
from raos.domain.editorial.article_plan import ArticlePlanType
from raos.domain.editorial.content_ast import load_content_ast
from raos.domain.portfolio.workflow import EntityVersion, StrongEtag, UtcTimestamp


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTENT_FIXTURE = REPOSITORY_ROOT / (
    "contracts/raos-v0.4/contracts/content/fixtures/valid/selection_guide.json"
)
V2_FIXTURE = REPOSITORY_ROOT / (
    "changes/st-0806/generated/ai-draft-integration-fixture.v2.json"
)
NOW = datetime(2026, 8, 24, 1, 0, tzinfo=UTC)
ARTICLE_ID = UUID("018f3e90-7b00-7000-8000-000000000806")
VERSION_ID = UUID("018f3e90-7b00-7000-8000-000000000807")
SOURCE_PACKET_VERSION_ID = UUID("018f3e90-7b00-7000-8000-000000000808")
SITE_ID = UUID("018f3e90-7b00-7000-8000-000000000809")
CATEGORY_ID = UUID("018f3e90-7b00-7000-8000-000000000810")
AI_JOB_ID = UUID("00000000-0000-4000-8000-000000000806")
OPS_JOB_ID = UUID("00000000-0000-4000-8000-000000030806")
INPUT_ARTIFACT_ID = UUID("00000000-0000-4000-8000-000000060806")
OUTPUT_ARTIFACT_ID = UUID("00000000-0000-4000-8000-000000070806")
OPERATION_ID = "operation.st0806.recorded.v2"
QUEUE_ID = "queue.st0806.recorded.v2"
TITLE = "Synthetic AI draft integration article V2"
PLAN = ValidationPlanBinding(
    plan_id="st-0705.ai-output-validation-reference-plan.v1",
    plan_sha256="ea935831a1bb667229ae5a5495a27a801b9c21ab3c3ddbe53e266b8f7c311c42",
)
IDENTITY = RouteIdentity(
    task_code="ai.article_draft.v1",
    route_code="route.editorial_balanced.v1",
    route_version="synthetic.route-version.st0806.v2",
    model_id="synthetic.model.st0806.v2",
)


def source_version() -> VersionSnapshot:
    payload = json.loads(CONTENT_FIXTURE.read_bytes())
    payload["article_id"] = str(ARTICLE_ID)
    payload["article_version_id"] = str(VERSION_ID)
    payload["source_packet_version_ref"] = str(SOURCE_PACKET_VERSION_ID)
    payload["title"] = TITLE
    ast = load_content_ast(json.dumps(payload, ensure_ascii=False))
    timestamp = UtcTimestamp(NOW)
    return VersionSnapshot(
        version_id=VERSION_ID,
        display_id=VersionDisplayId("ARV-TEST-0806-V2"),
        article_id=ARTICLE_ID,
        version_no=1,
        article_type=ArticlePlanType.SELECTION_GUIDE,
        title=TITLE,
        source_packet_version_id=SOURCE_PACKET_VERSION_ID,
        source_packet_verification=SourcePacketVerification.NOT_VERIFIED,
        based_on_version_id=None,
        content_ast=ast,
        body_sha256=BodySha256.of(ast),
        state=ArticleVersionState.DRAFT,
        submitted_at=None,
        reviewed_at=None,
        approved_at=None,
        published_at=None,
        version=EntityVersion(0),
        etag=StrongEtag('"test-only-st0806-v2-version-v0"'),
        created_at=timestamp,
        updated_at=timestamp,
    )


def command() -> AiJobCommand:
    controls = InMemoryDevelopmentAiControls(
        environment=RuntimeEnvironment.ENV_DEV,
        synthetic_cap_jpy=50,
        initially_closed_routes=(IDENTITY,),
    )
    intent = ReservationIntent(
        operation_id=f"reservation.{OPERATION_ID}",
        identity=IDENTITY,
        task_binding_sha256="2" * 64,
        route_sha256="3" * 64,
        certification_id="synthetic.certification.st0806.v2",
        quote_sha256="4" * 64,
        reserved_jpy=10,
        authorized_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    authorization = AuthorizedRouteReservation(
        identity=IDENTITY,
        certification_id="synthetic.certification.st0806.v2",
        task_binding_sha256="2" * 64,
        route_sha256="3" * 64,
        reservation=controls.reserve(intent=intent, now=NOW),
    )
    return AiJobCommand(
        operation_id=OPERATION_ID,
        idempotency_key="idempotency.st0806.recorded.v2",
        ai_job_id=AI_JOB_ID,
        ops_job_id=OPS_JOB_ID,
        task_code="ai.article_draft.v1",
        source_packet_version_id=SOURCE_PACKET_VERSION_ID,
        article_plan_id=None,
        article_version_id=VERSION_ID,
        authorization=authorization,
        input_artifact_id=INPUT_ARTIFACT_ID,
        input_artifact_sha256="5" * 64,
        validation_plan=PLAN,
        deadline_at=NOW + timedelta(minutes=4),
        attempt_number=1,
        max_attempts=2,
        cancellation_requested=False,
        cancel_requested_at=None,
    )


def durable_success(
    *, cost: int = 7
) -> tuple[DurableQueueSnapshot, RecordedAttemptOutcome]:
    state = RecordedDurableAiJobStateAdapterV2(queue_id=QUEUE_ID)
    durable = RecordedDurableAiJobQueueServiceV2(
        activation=RecordedDurableQueueActivation(
            environment=RuntimeEnvironment.ENV_DEV,
            enabled=True,
        ),
        state=state,
    )
    job_command = command()
    durable.enqueue(queue_id=QUEUE_ID, command=job_command, enqueued_at=NOW)
    claim = durable.claim(
        queue_id=QUEUE_ID,
        worker_id="worker.st0806.recorded.v2",
        lease_nonce_sha256="9" * 64,
        now=NOW + timedelta(seconds=1),
    )
    outcome = RecordedAttemptOutcome(
        kind=RecordedAttemptKind.SUCCEEDED,
        ai_job_id=AI_JOB_ID,
        attempt_number=1,
        provider_request_id="provider-request.st0806.v2",
        actual_cost_jpy=cost,
        validation_status=ValidationStatus.PASS,
        output_artifact_id=OUTPUT_ARTIFACT_ID,
        output_artifact_sha256="6" * 64,
    )
    durable.complete(
        claim=claim,
        outcome=outcome,
        now=NOW + timedelta(seconds=2),
    )
    return state.export_snapshot(), outcome


def request(
    *,
    snapshot: DurableQueueSnapshot | None = None,
    outcome: RecordedAttemptOutcome | None = None,
    environment: RuntimeEnvironment = RuntimeEnvironment.ENV_DEV,
) -> AiDraftIntegrationRequestV2:
    if snapshot is None or outcome is None:
        snapshot, outcome = durable_success()
    return AiDraftIntegrationRequestV2(
        environment=environment,
        operation_id=OPERATION_ID,
        queue_snapshot=snapshot,
        recorded_outcome=outcome,
        source_version=source_version(),
        article_state=ArticleState.DRAFT,
        site_id=SITE_ID,
        category_id=CATEGORY_ID,
    )


def service_and_adapter(
    *,
    bound_request: AiDraftIntegrationRequestV2 | None = None,
    fixture_bytes: bytes | None = None,
    environment: RuntimeEnvironment = RuntimeEnvironment.ENV_DEV,
    enabled: bool = True,
) -> tuple[AiDraftIntegrationServiceV2, RecordedAiDraftIntegrationAdapterV2]:
    selected = (
        request(environment=environment) if bound_request is None else bound_request
    )
    payload = V2_FIXTURE.read_bytes() if fixture_bytes is None else fixture_bytes
    adapter = RecordedAiDraftIntegrationAdapterV2(
        environment=environment,
        script_capacity=1,
        scripts=(
            RecordedAiDraftIntegrationStepV2(
                request_binding_sha256=selected.binding_sha256,
                fixture_bytes=payload,
            ),
        ),
    )
    service = AiDraftIntegrationServiceV2(
        activation=AiDraftV2Activation(environment=environment, enabled=enabled),
        port=adapter,
    )
    return service, adapter

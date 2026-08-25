"""Synthetic fixtures for the isolated ST-1404 recorded runtime suite."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
from uuid import UUID


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.adapters.queue_fake import QueueFake  # noqa: E402
from raos.adapters.recorded_job_runtime import (  # noqa: E402
    RecordedJobRuntimeAdapter,
)
from raos.adapters.recorded_durable_job_runtime import (  # noqa: E402
    RecordedDurableJobHandler,
    RecordedDurableJobRuntimeStore,
)
from raos.application.ops.durable_job_runtime import (  # noqa: E402
    DurableRecordedJobRuntimeService,
)
from raos.application.ops.job_runtime import (  # noqa: E402
    RecordedJobRuntimeService,
)
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.ops.job_runtime import (  # noqa: E402
    Fingerprint,
    HandlerOutcome,
    JobRecord,
    JobState,
    OutboxRecord,
    OutboxState,
    RecordedHandlerResult,
    RecordedJobMessage,
    RuntimeFailureCode,
)
from raos.domain.ops.durable_job_runtime import (  # noqa: E402
    CommitFault,
    DurableHandlerOutcome,
    DurableHandlerResult,
)
from raos.domain.shared.identity import Actor, ActorType  # noqa: E402
from raos.ports.job_runtime import RecordedJobHandler  # noqa: E402
from raos.ports.queue import QueuePort  # noqa: E402
from raos.ports.persistence.context import PersistenceContext  # noqa: E402


NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
JOB_ID = UUID("00000000-0000-0000-0000-000000001404")
EVENT_ID = UUID("00000000-0000-0000-0000-000000002404")
IDENTITY_NAMESPACE = UUID("00000000-0000-0000-0000-000000003404")
PAYLOAD_FINGERPRINT = Fingerprint("a" * 64)
RESULT_FINGERPRINT = Fingerprint("b" * 64)
QUEUE_NAME = "recorded-jobs"
CONSUMER_NAME = "recorded-worker"
HANDLER_VERSION = "handler-v1"
OWNER = "recorded-worker-owner"


def make_job(
    *,
    job_id: UUID = JOB_ID,
    state: JobState = JobState.REQUESTED,
    version: int = 0,
    available_at: datetime = NOW,
    deadline_at: datetime | None = NOW + timedelta(minutes=5),
    max_attempts: int = 3,
    delivery_max_attempts: int = 4,
) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        state=state,
        queue_name=QUEUE_NAME,
        payload_fingerprint=PAYLOAD_FINGERPRINT,
        created_at=NOW - timedelta(minutes=1),
        available_at=available_at,
        job_schema_version=1,
        version=version,
        max_attempts=max_attempts,
        delivery_max_attempts=delivery_max_attempts,
        deadline_at=deadline_at,
    )


def make_outbox(
    *,
    event_id: UUID = EVENT_ID,
    job_id: UUID = JOB_ID,
    available_at: datetime = NOW,
) -> OutboxRecord:
    return OutboxRecord(
        event_id=event_id,
        job_id=job_id,
        state=OutboxState.PENDING,
        created_at=NOW - timedelta(seconds=30),
        available_at=available_at,
        message_available_at=NOW,
    )


def success(*, completed_at: datetime = NOW) -> RecordedHandlerResult:
    return RecordedHandlerResult(
        outcome=HandlerOutcome.SUCCEEDED,
        completed_at=completed_at,
        result_fingerprint=RESULT_FINGERPRINT,
    )


def retryable(*, completed_at: datetime = NOW) -> RecordedHandlerResult:
    return RecordedHandlerResult(
        outcome=HandlerOutcome.RETRYABLE_FAILURE,
        completed_at=completed_at,
        failure_code=RuntimeFailureCode.HANDLER_FAILED,
    )


def terminal(*, completed_at: datetime = NOW) -> RecordedHandlerResult:
    return RecordedHandlerResult(
        outcome=HandlerOutcome.TERMINAL_FAILURE,
        completed_at=completed_at,
        failure_code=RuntimeFailureCode.HANDLER_FAILED,
    )


def make_adapter(
    *,
    jobs: tuple[JobRecord, ...] | None = None,
    outboxes: tuple[OutboxRecord, ...] | None = None,
    handler_results: tuple[RecordedHandlerResult, ...] | None = None,
    environment: RuntimeEnvironment = RuntimeEnvironment.ENV_DEV,
) -> RecordedJobRuntimeAdapter:
    return RecordedJobRuntimeAdapter(
        environment=environment,
        identity_namespace=IDENTITY_NAMESPACE,
        jobs=jobs if jobs is not None else (make_job(),),
        outboxes=outboxes if outboxes is not None else (make_outbox(),),
        handler_results=(success(),) if handler_results is None else handler_results,
    )


def make_service(
    *,
    adapter: RecordedJobRuntimeAdapter,
    queue: QueuePort[RecordedJobMessage] | None = None,
    handler: RecordedJobHandler | None = None,
    outbox_retry_schedule: tuple[timedelta, ...] = (timedelta(seconds=1),),
    job_retry_schedule: tuple[timedelta, ...] = (timedelta(seconds=5),),
    queue_lease: timedelta = timedelta(seconds=30),
    job_lease: timedelta = timedelta(seconds=30),
) -> tuple[RecordedJobRuntimeService, QueuePort[RecordedJobMessage]]:
    selected_queue: QueuePort[RecordedJobMessage]
    if queue is None:
        selected_queue = QueueFake(start_at=NOW)
    else:
        selected_queue = queue
    return (
        RecordedJobRuntimeService(
            store=adapter,
            queue=selected_queue,
            handler=handler if handler is not None else adapter,
            consumer_name=CONSUMER_NAME,
            handler_version=HANDLER_VERSION,
            queue_lease=queue_lease,
            job_lease=job_lease,
            outbox_retry_schedule=outbox_retry_schedule,
            job_retry_schedule=job_retry_schedule,
        ),
        selected_queue,
    )


def durable_result(
    outcome: DurableHandlerOutcome = DurableHandlerOutcome.SUCCEEDED,
    *,
    completed_at: datetime = NOW,
    failure_code: RuntimeFailureCode = RuntimeFailureCode.HANDLER_FAILED,
) -> DurableHandlerResult:
    if outcome is DurableHandlerOutcome.SUCCEEDED:
        return DurableHandlerResult(
            outcome=outcome,
            completed_at=completed_at,
            result_fingerprint=RESULT_FINGERPRINT,
        )
    return DurableHandlerResult(
        outcome=outcome,
        completed_at=completed_at,
        failure_code=failure_code,
    )


def durable_context(now: datetime = NOW, *, suffix: int = 0) -> PersistenceContext:
    offset = suffix + 1
    return PersistenceContext(
        command_id=UUID(f"00000000-0000-4000-8001-{offset:012x}"),
        correlation_id=UUID(f"00000000-0000-4000-8002-{offset:012x}"),
        causation_id=UUID(f"00000000-0000-4000-8003-{offset:012x}"),
        actor=Actor(
            ActorType.SERVICE,
            UUID(f"00000000-0000-4000-8004-{offset:012x}"),
        ),
        source="tests.st1404.durable",
        occurred_at=now,
    )


def durable_store(
    *,
    jobs: tuple[JobRecord, ...] | None = None,
    outboxes: tuple[OutboxRecord, ...] | None = None,
    commit_faults: tuple[CommitFault, ...] = (),
    environment: RuntimeEnvironment = RuntimeEnvironment.ENV_DEV,
) -> RecordedDurableJobRuntimeStore:
    return RecordedDurableJobRuntimeStore(
        environment=environment,
        identity_namespace=IDENTITY_NAMESPACE,
        jobs=(make_job(),) if jobs is None else jobs,
        outboxes=(make_outbox(),) if outboxes is None else outboxes,
        commit_faults=commit_faults,
    )


def durable_service(
    *,
    store: RecordedDurableJobRuntimeStore,
    queue: QueuePort[RecordedJobMessage] | None = None,
    handler_results: tuple[DurableHandlerResult, ...] | None = None,
    outbox_retry_schedule: tuple[timedelta, ...] = (timedelta(seconds=1),),
    job_retry_schedule: tuple[timedelta, ...] = (timedelta(seconds=5),),
    queue_lease: timedelta = timedelta(seconds=30),
    job_lease: timedelta = timedelta(seconds=30),
    outbox_lease: timedelta = timedelta(seconds=20),
    quarantine_lease: timedelta = timedelta(seconds=20),
) -> tuple[
    DurableRecordedJobRuntimeService,
    QueuePort[RecordedJobMessage],
    RecordedDurableJobHandler,
]:
    selected_queue: QueuePort[RecordedJobMessage]
    if queue is None:
        selected_queue = QueueFake(start_at=NOW)
    else:
        selected_queue = queue
    handler = RecordedDurableJobHandler(
        environment=RuntimeEnvironment.ENV_DEV,
        results=(durable_result(),) if handler_results is None else handler_results,
    )
    return (
        DurableRecordedJobRuntimeService(
            factory=store,
            queue=selected_queue,
            handler=handler,
            consumer_name=CONSUMER_NAME,
            handler_version=HANDLER_VERSION,
            owner=OWNER,
            queue_lease=queue_lease,
            job_lease=job_lease,
            outbox_lease=outbox_lease,
            quarantine_lease=quarantine_lease,
            outbox_retry_schedule=outbox_retry_schedule,
            job_retry_schedule=job_retry_schedule,
        ),
        selected_queue,
        handler,
    )

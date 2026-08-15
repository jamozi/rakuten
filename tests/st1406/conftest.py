"""Shared deterministic fixtures for the isolated ST-1406 suite."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
from uuid import UUID


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.adapters.recorded_incident import RecordedIncidentAdapter  # noqa: E402
from raos.application.ops.incident import IncidentService  # noqa: E402
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.ops.incident import (  # noqa: E402
    DeclareIncidentCommand,
    IncidentDisplayId,
    IncidentIdempotencyKey,
    IncidentSeverity,
    IncidentState,
    IncidentStatus,
    IncidentSummary,
    IncidentTitle,
)
from raos.domain.ops.kill_switch import (  # noqa: E402
    KillSwitchEventIntent,
    KillSwitchKey,
    KillSwitchKind,
    KillSwitchReasonCode,
    KillSwitchScopeType,
)


INCIDENT_ID = UUID("10000000-0000-4000-8000-000000000001")
OTHER_INCIDENT_ID = UUID("10000000-0000-4000-8000-000000000002")
DECLARER_ID = UUID("20000000-0000-4000-8000-000000000001")
OWNER_ID = UUID("20000000-0000-4000-8000-000000000002")
COMMANDER_ID = UUID("20000000-0000-4000-8000-000000000003")
ACTOR_ID = UUID("20000000-0000-4000-8000-000000000004")
CORRELATION_ID = UUID("30000000-0000-4000-8000-000000000001")
OTHER_CORRELATION_ID = UUID("30000000-0000-4000-8000-000000000002")
EVENT_NAMESPACE = UUID("40000000-0000-4000-8000-000000000001")
ARTIFACT_ID = UUID("50000000-0000-4000-8000-000000000001")
OTHER_ARTIFACT_ID = UUID("50000000-0000-4000-8000-000000000002")
KILL_EVENT_ID = UUID("60000000-0000-4000-8000-000000000001")
KILL_SWITCH_ID = UUID("60000000-0000-4000-8000-000000000002")
SITE_ID = UUID("70000000-0000-4000-8000-000000000001")
DECLARED_AT = datetime(2026, 8, 16, 0, 0, tzinfo=UTC)


def observed_at(minutes: int) -> datetime:
    return DECLARED_AT + timedelta(minutes=minutes)


def declare_command(
    *,
    incident_id: UUID = INCIDENT_ID,
    display_id: str = "INC-1406",
    severity: IncidentSeverity = IncidentSeverity.SEV1,
    correlation_id: UUID = CORRELATION_ID,
) -> DeclareIncidentCommand:
    return DeclareIncidentCommand(
        incident_id=incident_id,
        display_id=IncidentDisplayId(display_id),
        severity=severity,
        title=IncidentTitle("Synthetic incident"),
        summary=IncidentSummary("Synthetic local incident summary"),
        declared_by_principal_id=DECLARER_ID,
        owner_principal_id=OWNER_ID,
        commander_principal_id=COMMANDER_ID,
        correlation_id=correlation_id,
        declared_at=DECLARED_AT,
    )


def idempotency_key(value: str = "st1406-command-0001") -> IncidentIdempotencyKey:
    return IncidentIdempotencyKey(value)


def incident_state(
    *,
    owner_principal_id: UUID = OWNER_ID,
    commander_principal_id: UUID = COMMANDER_ID,
) -> IncidentState:
    command = declare_command()
    return IncidentState(
        incident_id=command.incident_id,
        display_id=command.display_id,
        severity=command.severity,
        status=IncidentStatus.DECLARED,
        title=command.title,
        summary=command.summary,
        declared_by_principal_id=command.declared_by_principal_id,
        owner_principal_id=owner_principal_id,
        commander_principal_id=commander_principal_id,
        declared_at=command.declared_at,
        updated_at=command.declared_at,
        generation=0,
    )


def service_bundle(
    *,
    capacity: int = 100,
    environment: RuntimeEnvironment = RuntimeEnvironment.ENV_DEV,
) -> tuple[IncidentService, RecordedIncidentAdapter]:
    adapter = RecordedIncidentAdapter(
        environment=environment,
        event_namespace=EVENT_NAMESPACE,
        capacity=capacity,
    )
    return IncidentService(store=adapter, capacity=capacity), adapter


def engaged_kill_switch_intent(
    *,
    incident_id: UUID = INCIDENT_ID,
    event_id: UUID = KILL_EVENT_ID,
    occurred_at: datetime | None = None,
) -> KillSwitchEventIntent:
    timestamp = observed_at(2) if occurred_at is None else occurred_at
    return KillSwitchEventIntent(
        event_id=event_id,
        switch_id=KILL_SWITCH_ID,
        key=KillSwitchKey(
            scope_type=KillSwitchScopeType.SITE,
            scope_id=SITE_ID,
            switch_type=KillSwitchKind.PUBLICATION,
        ),
        previous_engaged=False,
        new_engaged=True,
        previous_generation=0,
        new_generation=1,
        reason=KillSwitchReasonCode("INCIDENT_CONTAINMENT"),
        actor_principal_id=ACTOR_ID,
        correlation_id=CORRELATION_ID,
        occurred_at=timestamp,
        incident_id=incident_id,
    )

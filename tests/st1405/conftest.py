"""Synthetic fixtures for the isolated ST-1405 runtime suite."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
from uuid import UUID


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.adapters.development_oidc import (  # noqa: E402
    DevelopmentOidcAdapter,
    InMemoryAuthenticationRepository,
)
from raos.adapters.development_step_up import (  # noqa: E402
    DevelopmentScriptedStepUpVerifier,
)
from raos.adapters.recorded_kill_switch import (  # noqa: E402
    RecordedKillSwitchAdapter,
)
from raos.application.iam.authentication import AuthenticationService  # noqa: E402
from raos.application.iam.step_up import StepUpGuard  # noqa: E402
from raos.application.ops.kill_switch import KillSwitchRuntimeService  # noqa: E402
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.iam.authentication import (  # noqa: E402
    Issuer,
    PrincipalIdentity,
    Session,
    SessionId,
    Subject,
)
from raos.domain.iam.step_up import (  # noqa: E402
    StepUpAssuranceType,
    StepUpGrant,
)
from raos.domain.ops.kill_switch import (  # noqa: E402
    KillSwitchCacheEntry,
    KillSwitchCacheSnapshot,
    KillSwitchChangeCommand,
    KillSwitchContext,
    KillSwitchIdempotencyKey,
    KillSwitchKey,
    KillSwitchKind,
    KillSwitchReasonCode,
    KillSwitchScopeType,
    KillSwitchState,
    MAX_KILL_SWITCH_CACHE_ENTRIES,
)


NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
SITE_ID = UUID("00000000-0000-0000-0000-000000001405")
CATEGORY_ID = UUID("00000000-0000-0000-0000-000000002405")
ARTICLE_ID = UUID("00000000-0000-0000-0000-000000003405")
ACTOR_ID = UUID("00000000-0000-0000-0000-000000004405")
CORRELATION_ID = UUID("00000000-0000-0000-0000-000000005405")
INCIDENT_ID = UUID("00000000-0000-0000-0000-000000006405")
EVENT_NAMESPACE = UUID("00000000-0000-0000-0000-000000007405")
INITIAL_REASON = KillSwitchReasonCode("SYNTHETIC_INITIAL_STATE")
CHANGE_REASON = KillSwitchReasonCode("INCIDENT_CONTAINMENT")
CONTEXT = KillSwitchContext(
    site_id=SITE_ID,
    category_id=CATEGORY_ID,
    article_id=ARTICLE_ID,
)


def _bytes(index: int) -> bytes:
    return bytes((index + offset) % 256 for offset in range(32))


def make_session() -> Session:
    principal = PrincipalIdentity(
        issuer=Issuer("https://synthetic-issuer.dev.invalid"),
        subject=Subject("synthetic-operations-owner"),
        display_name="Synthetic Operations Owner",
    )
    return Session(
        session_id=SessionId.from_bytes(_bytes(1)),
        principal=principal,
        created_at=NOW - timedelta(minutes=10),
        last_seen_at=NOW - timedelta(minutes=1),
        idle_expires_at=NOW + timedelta(hours=2),
        absolute_expires_at=NOW + timedelta(hours=8),
    )


class _ScriptedEntropy:
    def __init__(self) -> None:
        self._values = [_bytes(90), _bytes(91)]

    def token_bytes(self, size: int) -> bytes:
        if size != 32 or not self._values:
            raise RuntimeError("synthetic entropy exhausted")
        return self._values.pop(0)


def make_step_up_guard(session: Session) -> StepUpGuard:
    repository = InMemoryAuthenticationRepository(
        environment=RuntimeEnvironment.ENV_DEV
    )
    repository.create_session(session)
    session_service = AuthenticationService(
        provider=DevelopmentOidcAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            principal=session.principal,
        ),
        repository=repository,
        entropy=_ScriptedEntropy(),
        session_idle_lifetime=timedelta(hours=2),
        session_absolute_lifetime=timedelta(hours=8),
    )
    grant = StepUpGrant(
        session_id=session.session_id,
        issuer=session.principal.issuer,
        subject=session.principal.subject,
        assurance_type=StepUpAssuranceType.MULTI_FACTOR,
        authenticated_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=8),
    )
    return StepUpGuard(
        session_service=session_service,
        verifier=DevelopmentScriptedStepUpVerifier(
            environment=RuntimeEnvironment.ENV_DEV,
            grants=(grant,),
        ),
    )


def all_keys(switch_type: KillSwitchKind) -> tuple[KillSwitchKey, ...]:
    return CONTEXT.required_keys(switch_type)


def make_states(
    *,
    engaged: dict[KillSwitchKey, bool] | None = None,
    generations: dict[KillSwitchKey, int] | None = None,
    changed_at: datetime = NOW - timedelta(minutes=1),
) -> tuple[KillSwitchState, ...]:
    engaged_values = engaged or {}
    generation_values = generations or {}
    states: list[KillSwitchState] = []
    index = 10
    for switch_type in KillSwitchKind:
        for key in all_keys(switch_type):
            states.append(
                KillSwitchState(
                    switch_id=UUID(f"00000000-0000-0000-0000-{index:012d}"),
                    key=key,
                    engaged=engaged_values.get(key, False),
                    generation=generation_values.get(key, 0),
                    reason=INITIAL_REASON,
                    changed_at=changed_at,
                )
            )
            index += 1
    return tuple(states)


def make_publication_states_at_capacity() -> tuple[KillSwitchState, ...]:
    publication_states = tuple(
        state
        for state in make_states()
        if state.key.switch_type is KillSwitchKind.PUBLICATION
    )
    template = publication_states[-1]
    extras = tuple(
        KillSwitchState(
            switch_id=UUID(int=1_000_000 + index),
            key=KillSwitchKey(
                KillSwitchScopeType.ARTICLE,
                UUID(int=2_000_000 + index),
                KillSwitchKind.PUBLICATION,
            ),
            engaged=False,
            generation=0,
            reason=template.reason,
            changed_at=template.changed_at,
        )
        for index in range(MAX_KILL_SWITCH_CACHE_ENTRIES - len(publication_states))
    )
    return (*publication_states, *extras)


def make_snapshot(
    switch_type: KillSwitchKind,
    states: tuple[KillSwitchState, ...],
    *,
    complete: bool = True,
    loaded_at: datetime = NOW - timedelta(seconds=1),
    fresh_until: datetime = NOW + timedelta(days=20),
    minimum_generations: dict[KillSwitchKey, int] | None = None,
) -> KillSwitchCacheSnapshot:
    minimums = minimum_generations or {}
    return KillSwitchCacheSnapshot(
        switch_type=switch_type,
        entries=tuple(
            KillSwitchCacheEntry(
                state=state,
                minimum_generation=minimums.get(state.key, state.generation),
            )
            for state in states
            if state.key.switch_type is switch_type
        ),
        loaded_at=loaded_at,
        fresh_until=fresh_until,
        complete=complete,
    )


def make_adapter(
    *,
    states: tuple[KillSwitchState, ...] | None = None,
    snapshots: tuple[KillSwitchCacheSnapshot, ...] | None = None,
    environment: RuntimeEnvironment = RuntimeEnvironment.ENV_DEV,
    capacity: int = MAX_KILL_SWITCH_CACHE_ENTRIES,
) -> RecordedKillSwitchAdapter:
    selected_states = states if states is not None else make_states()
    selected_snapshots = snapshots
    if selected_snapshots is None:
        selected_snapshots = tuple(
            make_snapshot(switch_type, selected_states)
            for switch_type in KillSwitchKind
        )
    return RecordedKillSwitchAdapter(
        environment=environment,
        event_namespace=EVENT_NAMESPACE,
        capacity=capacity,
        states=selected_states,
        cache_snapshots=selected_snapshots,
    )


def make_runtime(
    *,
    adapter: RecordedKillSwitchAdapter | None = None,
    session: Session | None = None,
) -> tuple[KillSwitchRuntimeService, RecordedKillSwitchAdapter, Session]:
    selected_adapter = adapter or make_adapter()
    selected_session = session or make_session()
    return (
        KillSwitchRuntimeService(
            store=selected_adapter,
            cache=selected_adapter,
            step_up_guard=make_step_up_guard(selected_session),
        ),
        selected_adapter,
        selected_session,
    )


def make_command(
    *,
    key: KillSwitchKey | None = None,
    engage: bool = True,
    expected_generation: int = 0,
    reason: KillSwitchReasonCode = CHANGE_REASON,
    actor_principal_id: UUID = ACTOR_ID,
    correlation_id: UUID = CORRELATION_ID,
    incident_id: UUID | None = INCIDENT_ID,
    expires_at: datetime | None = None,
) -> KillSwitchChangeCommand:
    return KillSwitchChangeCommand(
        key=key or all_keys(KillSwitchKind.PUBLICATION)[0],
        engage=engage,
        expected_generation=expected_generation,
        reason=reason,
        actor_principal_id=actor_principal_id,
        correlation_id=correlation_id,
        incident_id=incident_id,
        expires_at=expires_at,
    )


def idempotency_key(value: str = "st1405-command-0001") -> KillSwitchIdempotencyKey:
    return KillSwitchIdempotencyKey(value)

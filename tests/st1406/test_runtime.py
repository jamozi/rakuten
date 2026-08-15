"""Command, CAS, idempotency, and ST-1405 intake tests for ST-1406."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import cast
from uuid import UUID, uuid5

import pytest

from conftest import (
    ACTOR_ID,
    ARTIFACT_ID,
    COMMANDER_ID,
    CORRELATION_ID,
    DECLARED_AT,
    DECLARER_ID,
    EVENT_NAMESPACE,
    INCIDENT_ID,
    KILL_EVENT_ID,
    KILL_SWITCH_ID,
    OTHER_CORRELATION_ID,
    OTHER_INCIDENT_ID,
    OWNER_ID,
    declare_command,
    engaged_kill_switch_intent,
    idempotency_key,
    incident_state,
    observed_at,
    service_bundle,
)
from raos.adapters.recorded_incident import RecordedIncidentAdapter
from raos.application.ops.incident import IncidentService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ops.incident import (
    AppendIncidentTimelineCommand,
    DeclareIncidentCommand,
    IncidentCommand,
    IncidentDisplayId,
    IncidentEvidenceReference,
    IncidentFailure,
    IncidentFailureCode,
    IncidentFingerprint,
    IncidentIdempotencyKey,
    IncidentMutationResult,
    IncidentSeverity,
    IncidentState,
    IncidentStatus,
    IncidentSummary,
    IncidentTimelineEntry,
    IncidentTimelineNote,
    IncidentTimelineType,
    IncidentTitle,
    MAX_INCIDENT_GENERATION,
    MAX_INCIDENT_TIMELINE_ENTRIES,
    RecordKillSwitchIntentCommand,
    TransitionIncidentCommand,
)
from raos.ports.incident import IncidentStore, IncidentStoreOutcome


def _append_command(
    *,
    expected_generation: int,
    correlation_id: UUID = CORRELATION_ID,
    minutes: int | None = None,
    note: str = "Synthetic timeline note",
) -> AppendIncidentTimelineCommand:
    timestamp = (
        observed_at(expected_generation + 1)
        if minutes is None
        else observed_at(minutes)
    )
    return AppendIncidentTimelineCommand(
        incident_id=INCIDENT_ID,
        expected_generation=expected_generation,
        event_type=IncidentTimelineType.NOTE,
        note=IncidentTimelineNote(note),
        actor_principal_id=ACTOR_ID,
        correlation_id=correlation_id,
        occurred_at=timestamp,
    )


def _seed_timeline_entry(
    *,
    event_id: UUID,
    generation: int,
    occurred_minutes: int,
    incident_id: UUID = INCIDENT_ID,
    event_type: IncidentTimelineType = IncidentTimelineType.NOTE,
    previous_status: IncidentStatus | None = None,
    new_status: IncidentStatus | None = None,
    source_event_id: UUID | None = None,
) -> IncidentTimelineEntry:
    return IncidentTimelineEntry(
        event_id=event_id,
        incident_id=incident_id,
        generation=generation,
        event_type=event_type,
        note=IncidentTimelineNote("Synthetic seeded timeline entry"),
        actor_principal_id=ACTOR_ID,
        correlation_id=CORRELATION_ID,
        occurred_at=observed_at(occurred_minutes),
        evidence_references=(),
        previous_status=previous_status,
        new_status=new_status,
        source_kill_switch_event_id=source_event_id,
        source_kill_switch_id=(None if source_event_id is None else KILL_SWITCH_ID),
        source_kill_switch_generation=(None if source_event_id is None else 1),
    )


def _derived_event_id(key: IncidentIdempotencyKey, purpose: str) -> UUID:
    return uuid5(EVENT_NAMESPACE, f"{key.fingerprint().value}:{purpose}")


def _hostile_non_status_result(
    *,
    command: AppendIncidentTimelineCommand | RecordKillSwitchIntentCommand,
    state: IncidentState,
) -> IncidentMutationResult:
    event_id = UUID("60000000-0000-4000-8000-000000000010")
    if type(command) is AppendIncidentTimelineCommand:
        entry = IncidentTimelineEntry(
            event_id=event_id,
            incident_id=command.incident_id,
            generation=state.generation,
            event_type=command.event_type,
            note=command.note,
            actor_principal_id=command.actor_principal_id,
            correlation_id=command.correlation_id,
            occurred_at=command.occurred_at,
            evidence_references=command.evidence_references,
        )
    else:
        intent = command.intent
        entry = IncidentTimelineEntry(
            event_id=event_id,
            incident_id=command.incident_id,
            generation=state.generation,
            event_type=IncidentTimelineType.CONTAINMENT,
            note=IncidentTimelineNote("KILL_SWITCH_ENGAGED"),
            actor_principal_id=intent.actor_principal_id,
            correlation_id=intent.correlation_id,
            occurred_at=intent.occurred_at,
            evidence_references=(),
            source_kill_switch_event_id=intent.event_id,
            source_kill_switch_id=intent.switch_id,
            source_kill_switch_generation=intent.new_generation,
        )
    return IncidentMutationResult(
        state=state,
        timeline_entry=entry,
        contract_intent=None,
    )


class _HostileNonStatusReceiptStore:
    def __init__(self, *, result: IncidentMutationResult, replayed: bool) -> None:
        self._result = result
        self._replayed = replayed

    def apply(
        self,
        *,
        command: IncidentCommand,
        command_fingerprint: IncidentFingerprint,
        idempotency_fingerprint: IncidentFingerprint,
        minimum_generation: int,
        observed_state: IncidentState | None,
        allow_unobserved_incident: bool,
    ) -> IncidentStoreOutcome:
        assert command.fingerprint() == command_fingerprint
        assert minimum_generation == 0
        assert observed_state is None
        assert allow_unobserved_incident is True
        return IncidentStoreOutcome(
            result=self._result,
            replayed=self._replayed,
            current_state=self._result.state,
            command_fingerprint=command_fingerprint,
            idempotency_fingerprint=idempotency_fingerprint,
        )


def _assert_hostile_non_status_receipt_rejected(
    *,
    command: AppendIncidentTimelineCommand | RecordKillSwitchIntentCommand,
    state: IncidentState,
    replayed: bool,
    idempotency_value: str,
) -> None:
    result = _hostile_non_status_result(command=command, state=state)
    service = IncidentService(
        store=_HostileNonStatusReceiptStore(result=result, replayed=replayed),
        capacity=10,
    )
    key = idempotency_key(idempotency_value)

    with pytest.raises(IncidentFailure) as caught:
        if type(command) is AppendIncidentTimelineCommand:
            service.append_timeline(command=command, idempotency_key=key)
        else:
            service.record_kill_switch_intent(command=command, idempotency_key=key)
    assert caught.value.code is IncidentFailureCode.STORE_FAILURE


def _hostile_command_case(
    scenario: str,
) -> tuple[tuple[IncidentState, ...], IncidentCommand]:
    incident_id = UUID(int=INCIDENT_ID.int)
    actor_id = UUID(int=ACTOR_ID.int)
    correlation_id = UUID(int=CORRELATION_ID.int)
    if scenario == "close":
        seeded_state = replace(
            incident_state(),
            status=IncidentStatus.MONITORING,
            generation=4,
            updated_at=observed_at(4),
            contained_at=observed_at(2),
            recovered_at=observed_at(4),
        )
        return (seeded_state,), TransitionIncidentCommand(
            incident_id=incident_id,
            expected_generation=4,
            target_status=IncidentStatus.CLOSED,
            note=IncidentTimelineNote("Synthetic closure"),
            actor_principal_id=actor_id,
            correlation_id=correlation_id,
            occurred_at=observed_at(5),
            evidence_references=(
                IncidentEvidenceReference(
                    artifact_id=UUID(int=ARTIFACT_ID.int),
                    artifact_sha256="e" * 64,
                ),
            ),
            root_cause_recorded=True,
        )
    if scenario == "declare":
        return (), replace(
            declare_command(),
            incident_id=incident_id,
            declared_by_principal_id=UUID(int=DECLARER_ID.int),
            owner_principal_id=UUID(int=OWNER_ID.int),
            commander_principal_id=UUID(int=COMMANDER_ID.int),
            correlation_id=correlation_id,
        )
    if scenario == "append":
        return (incident_state(),), replace(
            _append_command(expected_generation=0),
            incident_id=incident_id,
            actor_principal_id=actor_id,
            correlation_id=correlation_id,
        )
    if scenario == "transition":
        return (incident_state(),), TransitionIncidentCommand(
            incident_id=incident_id,
            expected_generation=0,
            target_status=IncidentStatus.CONTAINING,
            note=IncidentTimelineNote("Synthetic containment start"),
            actor_principal_id=actor_id,
            correlation_id=correlation_id,
            occurred_at=observed_at(1),
        )
    source = replace(
        engaged_kill_switch_intent(occurred_at=observed_at(1)),
        event_id=UUID(int=KILL_EVENT_ID.int),
        switch_id=UUID(int=KILL_SWITCH_ID.int),
        actor_principal_id=actor_id,
        correlation_id=correlation_id,
        incident_id=incident_id,
    )
    return (incident_state(),), RecordKillSwitchIntentCommand(
        incident_id=incident_id,
        expected_generation=0,
        intent=source,
    )


def test_declare_persists_explicit_owner_commander_and_unpublished_intent() -> None:
    service, adapter = service_bundle()
    result = service.declare(
        command=declare_command(), idempotency_key=idempotency_key()
    )

    assert result.state.status is IncidentStatus.DECLARED
    assert result.state.generation == 0
    assert result.state.owner_principal_id == OWNER_ID
    assert result.state.commander_principal_id == COMMANDER_ID
    assert adapter.current_state(INCIDENT_ID) == result.state
    assert adapter.timeline(INCIDENT_ID) == ()
    assert adapter.contract_intents() == (result.contract_intent,)
    assert not hasattr(adapter, "publish")
    assert not hasattr(adapter, "send")
    assert not hasattr(adapter, "notify")


def test_exact_replay_returns_original_without_duplicate_state_or_intent() -> None:
    service, adapter = service_bundle()
    command = declare_command()
    key = idempotency_key()
    first = service.declare(command=command, idempotency_key=key)
    second = service.declare(command=command, idempotency_key=key)

    assert second == first
    assert adapter.current_state(INCIDENT_ID) == first.state
    assert adapter.contract_intents() == (first.contract_intent,)


def test_same_idempotency_key_with_changed_command_fails_without_mutation() -> None:
    service, adapter = service_bundle()
    key = idempotency_key()
    original = service.declare(command=declare_command(), idempotency_key=key)

    with pytest.raises(IncidentFailure) as caught:
        service.declare(
            command=declare_command(correlation_id=OTHER_CORRELATION_ID),
            idempotency_key=key,
        )
    assert caught.value.code is IncidentFailureCode.IDEMPOTENCY_CONFLICT
    assert adapter.current_state(INCIDENT_ID) == original.state
    assert len(adapter.contract_intents()) == 1


def test_generation_cas_and_monotonic_time_fail_without_partial_timeline() -> None:
    service, adapter = service_bundle()
    declared = service.declare(
        command=declare_command(), idempotency_key=idempotency_key()
    )
    first = service.append_timeline(
        command=_append_command(expected_generation=declared.state.generation),
        idempotency_key=idempotency_key("st1406-command-0002"),
    )
    before = adapter.timeline(INCIDENT_ID)

    with pytest.raises(IncidentFailure) as stale:
        service.append_timeline(
            command=_append_command(expected_generation=0, minutes=2),
            idempotency_key=idempotency_key("st1406-command-0003"),
        )
    assert stale.value.code is IncidentFailureCode.GENERATION_CONFLICT

    with pytest.raises(IncidentFailure) as regressed:
        service.append_timeline(
            command=_append_command(
                expected_generation=first.state.generation,
                minutes=0,
            ),
            idempotency_key=idempotency_key("st1406-command-0004"),
        )
    assert regressed.value.code is IncidentFailureCode.STATE_CONFLICT
    assert adapter.current_state(INCIDENT_ID) == first.state
    assert adapter.timeline(INCIDENT_ID) == before


def test_historical_replay_returns_original_after_newer_generation() -> None:
    service, adapter = service_bundle()
    service.declare(command=declare_command(), idempotency_key=idempotency_key())
    first_key = idempotency_key("st1406-command-0002")
    first_command = _append_command(expected_generation=0)
    first = service.append_timeline(command=first_command, idempotency_key=first_key)
    second = service.append_timeline(
        command=_append_command(expected_generation=1, note="A later note"),
        idempotency_key=idempotency_key("st1406-command-0003"),
    )

    replay = service.append_timeline(command=first_command, idempotency_key=first_key)
    assert replay == first
    assert adapter.current_state(INCIDENT_ID) == second.state
    assert len(adapter.timeline(INCIDENT_ID)) == 2


def test_replay_cannot_hide_store_generation_rollback() -> None:
    backing = RecordedIncidentAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=10,
    )

    class ReplayRollbackStore:
        def apply(
            self,
            *,
            command: IncidentCommand,
            command_fingerprint: IncidentFingerprint,
            idempotency_fingerprint: IncidentFingerprint,
            minimum_generation: int,
            observed_state: IncidentState | None,
            allow_unobserved_incident: bool,
        ) -> IncidentStoreOutcome:
            outcome = backing.apply(
                command=command,
                command_fingerprint=command_fingerprint,
                idempotency_fingerprint=idempotency_fingerprint,
                minimum_generation=minimum_generation,
                observed_state=observed_state,
                allow_unobserved_incident=allow_unobserved_incident,
            )
            if outcome.replayed:
                return replace(outcome, current_state=outcome.result.state)
            return outcome

    service = IncidentService(store=ReplayRollbackStore(), capacity=10)
    service.declare(command=declare_command(), idempotency_key=idempotency_key())
    first_command = _append_command(expected_generation=0)
    first_key = idempotency_key("st1406-command-0002")
    service.append_timeline(command=first_command, idempotency_key=first_key)
    latest = service.append_timeline(
        command=_append_command(expected_generation=1, note="Latest state"),
        idempotency_key=idempotency_key("st1406-command-0003"),
    )

    with pytest.raises(IncidentFailure) as caught:
        service.append_timeline(command=first_command, idempotency_key=first_key)
    assert caught.value.code is IncidentFailureCode.STORE_FAILURE
    assert backing.current_state(INCIDENT_ID) == latest.state


def test_shared_replay_never_advances_observation_and_stale_cas_is_pre_mutation() -> (
    None
):
    backing = RecordedIncidentAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=10,
    )
    first_service = IncidentService(store=backing, capacity=10)
    second_service = IncidentService(store=backing, capacity=10)
    declaration = declare_command()
    declaration_key = idempotency_key()
    declared = first_service.declare(
        command=declaration,
        idempotency_key=declaration_key,
    )
    advanced = second_service.append_timeline(
        command=_append_command(expected_generation=0),
        idempotency_key=idempotency_key("st1406-shared-advance"),
    )
    assert advanced.state.generation == 1
    before = backing.timeline(INCIDENT_ID)

    assert (
        first_service.declare(
            command=declaration,
            idempotency_key=declaration_key,
        )
        == declared
    )
    with pytest.raises(IncidentFailure) as caught:
        first_service.append_timeline(
            command=_append_command(
                expected_generation=1,
                note="Must not skip an unobserved shared generation",
            ),
            idempotency_key=idempotency_key("st1406-stale-shared-service"),
        )
    assert caught.value.code is IncidentFailureCode.STATE_CONFLICT
    assert backing.current_state(INCIDENT_ID) == advanced.state
    assert backing.timeline(INCIDENT_ID) == before


def test_unobserved_replay_never_binds_service_observation_maps() -> None:
    backing = RecordedIncidentAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=10,
    )
    command = declare_command()
    key = idempotency_key()
    producer = IncidentService(store=backing, capacity=10)
    expected = producer.declare(command=command, idempotency_key=key)

    class ObservationStore:
        def __init__(self) -> None:
            self.observations: list[IncidentState | None] = []

        def apply(
            self,
            *,
            command: IncidentCommand,
            command_fingerprint: IncidentFingerprint,
            idempotency_fingerprint: IncidentFingerprint,
            minimum_generation: int,
            observed_state: IncidentState | None,
            allow_unobserved_incident: bool,
        ) -> IncidentStoreOutcome:
            self.observations.append(observed_state)
            return backing.apply(
                command=command,
                command_fingerprint=command_fingerprint,
                idempotency_fingerprint=idempotency_fingerprint,
                minimum_generation=minimum_generation,
                observed_state=observed_state,
                allow_unobserved_incident=allow_unobserved_incident,
            )

    store = ObservationStore()
    consumer = IncidentService(store=store, capacity=10)
    assert consumer.declare(command=command, idempotency_key=key) == expected
    assert consumer.declare(command=command, idempotency_key=key) == expected
    assert store.observations == [None, None]


def test_hostile_fresh_outcome_cannot_report_a_different_current_state() -> None:
    backing = RecordedIncidentAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=10,
    )

    class FreshCurrentMismatchStore:
        def apply(
            self,
            *,
            command: IncidentCommand,
            command_fingerprint: IncidentFingerprint,
            idempotency_fingerprint: IncidentFingerprint,
            minimum_generation: int,
            observed_state: IncidentState | None,
            allow_unobserved_incident: bool,
        ) -> IncidentStoreOutcome:
            outcome = backing.apply(
                command=command,
                command_fingerprint=command_fingerprint,
                idempotency_fingerprint=idempotency_fingerprint,
                minimum_generation=minimum_generation,
                observed_state=observed_state,
                allow_unobserved_incident=allow_unobserved_incident,
            )
            forged_current = replace(
                outcome.result.state,
                generation=1,
                updated_at=observed_at(1),
            )
            object.__setattr__(outcome, "current_state", forged_current)
            return outcome

    service = IncidentService(store=FreshCurrentMismatchStore(), capacity=10)
    with pytest.raises(IncidentFailure) as caught:
        service.declare(command=declare_command(), idempotency_key=idempotency_key())
    assert caught.value.code is IncidentFailureCode.STORE_FAILURE
    retained = backing.current_state(INCIDENT_ID)
    assert retained is not None
    assert retained.generation == 0


def test_hostile_replay_outcome_cannot_report_current_older_than_result() -> None:
    backing = RecordedIncidentAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=10,
    )

    class ReplayCurrentRollbackStore:
        def __init__(self) -> None:
            self.declared_state: IncidentState | None = None

        def apply(
            self,
            *,
            command: IncidentCommand,
            command_fingerprint: IncidentFingerprint,
            idempotency_fingerprint: IncidentFingerprint,
            minimum_generation: int,
            observed_state: IncidentState | None,
            allow_unobserved_incident: bool,
        ) -> IncidentStoreOutcome:
            outcome = backing.apply(
                command=command,
                command_fingerprint=command_fingerprint,
                idempotency_fingerprint=idempotency_fingerprint,
                minimum_generation=minimum_generation,
                observed_state=observed_state,
                allow_unobserved_incident=allow_unobserved_incident,
            )
            if type(command) is DeclareIncidentCommand:
                self.declared_state = outcome.result.state
            elif outcome.replayed:
                assert self.declared_state is not None
                object.__setattr__(
                    outcome,
                    "current_state",
                    self.declared_state,
                )
            return outcome

    store = ReplayCurrentRollbackStore()
    service = IncidentService(store=store, capacity=10)
    service.declare(command=declare_command(), idempotency_key=idempotency_key())
    command = _append_command(expected_generation=0)
    key = idempotency_key("st1406-command-0002")
    result = service.append_timeline(command=command, idempotency_key=key)
    assert result.state.generation == 1

    with pytest.raises(IncidentFailure) as caught:
        service.append_timeline(command=command, idempotency_key=key)
    assert caught.value.code is IncidentFailureCode.STORE_FAILURE
    retained = backing.current_state(INCIDENT_ID)
    assert retained is not None
    assert retained.generation == 1


@pytest.mark.parametrize("replayed", [False, True])
@pytest.mark.parametrize("record_kill_switch", [False, True])
def test_non_status_receipt_cannot_mutate_an_already_closed_incident(
    replayed: bool,
    record_kill_switch: bool,
) -> None:
    command: AppendIncidentTimelineCommand | RecordKillSwitchIntentCommand
    if record_kill_switch:
        command = RecordKillSwitchIntentCommand(
            incident_id=INCIDENT_ID,
            expected_generation=5,
            intent=engaged_kill_switch_intent(occurred_at=observed_at(6)),
        )
    else:
        command = _append_command(expected_generation=5, minutes=6)
    closed_state = replace(
        incident_state(),
        status=IncidentStatus.CLOSED,
        generation=6,
        updated_at=observed_at(6),
        contained_at=observed_at(2),
        recovered_at=observed_at(4),
        closed_at=observed_at(5),
        root_cause_recorded=True,
    )

    _assert_hostile_non_status_receipt_rejected(
        command=command,
        state=closed_state,
        replayed=replayed,
        idempotency_value=(
            f"st1406-hostile-closed-{'kill' if record_kill_switch else 'append'}-"
            f"{'replay' if replayed else 'fresh'}"
        ),
    )


@pytest.mark.parametrize("replayed", [False, True])
@pytest.mark.parametrize("record_kill_switch", [False, True])
def test_unknown_prior_non_status_receipt_requires_status_reachable_before_command(
    replayed: bool,
    record_kill_switch: bool,
) -> None:
    command: AppendIncidentTimelineCommand | RecordKillSwitchIntentCommand
    if record_kill_switch:
        command = RecordKillSwitchIntentCommand(
            incident_id=INCIDENT_ID,
            expected_generation=1,
            intent=engaged_kill_switch_intent(occurred_at=observed_at(2)),
        )
    else:
        command = _append_command(expected_generation=1, minutes=2)
    unreachable_state = replace(
        incident_state(),
        status=IncidentStatus.CONTAINED,
        generation=2,
        updated_at=observed_at(2),
        contained_at=observed_at(2),
    )

    _assert_hostile_non_status_receipt_rejected(
        command=command,
        state=unreachable_state,
        replayed=replayed,
        idempotency_value=(
            f"st1406-hostile-unreachable-"
            f"{'kill' if record_kill_switch else 'append'}-"
            f"{'replay' if replayed else 'fresh'}"
        ),
    )


@pytest.mark.parametrize("record_kill_switch", [False, True])
def test_unobserved_generation_zero_mutation_cannot_forge_containing_state(
    record_kill_switch: bool,
) -> None:
    seeded = incident_state()
    backing = RecordedIncidentAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=10,
        states=(seeded,),
    )

    class ForgedInferredStatusStore:
        def apply(
            self,
            *,
            command: IncidentCommand,
            command_fingerprint: IncidentFingerprint,
            idempotency_fingerprint: IncidentFingerprint,
            minimum_generation: int,
            observed_state: IncidentState | None,
            allow_unobserved_incident: bool,
        ) -> IncidentStoreOutcome:
            outcome = backing.apply(
                command=command,
                command_fingerprint=command_fingerprint,
                idempotency_fingerprint=idempotency_fingerprint,
                minimum_generation=minimum_generation,
                observed_state=observed_state,
                allow_unobserved_incident=allow_unobserved_incident,
            )
            forged_state = replace(
                outcome.result.state,
                status=IncidentStatus.CONTAINING,
            )
            return replace(
                outcome,
                result=replace(outcome.result, state=forged_state),
                current_state=forged_state,
            )

    service = IncidentService(store=ForgedInferredStatusStore(), capacity=10)
    key = idempotency_key("st1406-inferred-declared")

    def invoke() -> None:
        if record_kill_switch:
            service.record_kill_switch_intent(
                command=RecordKillSwitchIntentCommand(
                    incident_id=INCIDENT_ID,
                    expected_generation=0,
                    intent=engaged_kill_switch_intent(occurred_at=observed_at(1)),
                ),
                idempotency_key=key,
            )
        else:
            service.append_timeline(
                command=_append_command(expected_generation=0),
                idempotency_key=key,
            )

    with pytest.raises(IncidentFailure) as caught:
        invoke()
    assert caught.value.code is IncidentFailureCode.STORE_FAILURE
    retained = backing.current_state(INCIDENT_ID)
    assert retained is not None
    assert retained.status is IncidentStatus.DECLARED
    assert retained.generation == 1


def test_lifecycle_is_exact_and_closure_requires_root_cause_evidence() -> None:
    service, adapter = service_bundle(capacity=20)
    current = service.declare(
        command=declare_command(), idempotency_key=idempotency_key()
    )
    sequence = (
        IncidentStatus.CONTAINING,
        IncidentStatus.CONTAINED,
        IncidentStatus.RECOVERING,
        IncidentStatus.MONITORING,
    )
    for index, target in enumerate(sequence, start=1):
        current = service.transition(
            command=TransitionIncidentCommand(
                incident_id=INCIDENT_ID,
                expected_generation=current.state.generation,
                target_status=target,
                note=IncidentTimelineNote(f"Synthetic lifecycle {target.value}"),
                actor_principal_id=ACTOR_ID,
                correlation_id=CORRELATION_ID,
                occurred_at=observed_at(index),
            ),
            idempotency_key=idempotency_key(f"st1406-command-{index + 1:04d}"),
        )
    evidence = IncidentEvidenceReference(
        artifact_id=ARTIFACT_ID,
        artifact_sha256="a" * 64,
    )
    closed = service.transition(
        command=TransitionIncidentCommand(
            incident_id=INCIDENT_ID,
            expected_generation=current.state.generation,
            target_status=IncidentStatus.CLOSED,
            note=IncidentTimelineNote("Verification and root cause recorded"),
            actor_principal_id=ACTOR_ID,
            correlation_id=CORRELATION_ID,
            occurred_at=observed_at(5),
            evidence_references=(evidence,),
            root_cause_recorded=True,
        ),
        idempotency_key=idempotency_key("st1406-command-0006"),
    )
    assert closed.state.closed_at == observed_at(5)
    assert closed.state.root_cause_recorded is True

    with pytest.raises(IncidentFailure) as append_closed:
        service.append_timeline(
            command=_append_command(expected_generation=5, minutes=6),
            idempotency_key=idempotency_key("st1406-command-0007"),
        )
    assert append_closed.value.code is IncidentFailureCode.STATE_CONFLICT

    reopened = service.transition(
        command=TransitionIncidentCommand(
            incident_id=INCIDENT_ID,
            expected_generation=closed.state.generation,
            target_status=IncidentStatus.REOPENED,
            note=IncidentTimelineNote("New synthetic evidence requires response"),
            actor_principal_id=ACTOR_ID,
            correlation_id=CORRELATION_ID,
            occurred_at=observed_at(6),
        ),
        idempotency_key=idempotency_key("st1406-command-0008"),
    )
    assert reopened.state.closed_at is None
    assert reopened.state.root_cause_recorded is False
    assert len(adapter.timeline(INCIDENT_ID)) == 6


def test_invalid_lifecycle_jump_is_rejected_before_state_change() -> None:
    service, adapter = service_bundle()
    declared = service.declare(
        command=declare_command(), idempotency_key=idempotency_key()
    )
    with pytest.raises(IncidentFailure) as caught:
        service.transition(
            command=TransitionIncidentCommand(
                incident_id=INCIDENT_ID,
                expected_generation=0,
                target_status=IncidentStatus.CLOSED,
                note=IncidentTimelineNote("Invalid direct closure"),
                actor_principal_id=ACTOR_ID,
                correlation_id=CORRELATION_ID,
                occurred_at=observed_at(1),
                evidence_references=(
                    IncidentEvidenceReference(
                        artifact_id=ARTIFACT_ID,
                        artifact_sha256="a" * 64,
                    ),
                ),
                root_cause_recorded=True,
            ),
            idempotency_key=idempotency_key("st1406-command-0002"),
        )
    assert caught.value.code is IncidentFailureCode.STATE_CONFLICT
    assert adapter.current_state(INCIDENT_ID) == declared.state
    assert adapter.timeline(INCIDENT_ID) == ()


def test_existing_engaged_kill_switch_intent_is_recorded_without_invocation() -> None:
    service, adapter = service_bundle()
    service.declare(command=declare_command(), idempotency_key=idempotency_key())
    source = engaged_kill_switch_intent()
    result = service.record_kill_switch_intent(
        command=RecordKillSwitchIntentCommand(
            incident_id=INCIDENT_ID,
            expected_generation=0,
            intent=source,
        ),
        idempotency_key=idempotency_key("st1406-command-0002"),
    )

    entry = result.timeline_entry
    assert entry is not None
    assert entry.event_type is IncidentTimelineType.CONTAINMENT
    assert entry.source_kill_switch_event_id == KILL_EVENT_ID
    assert entry.source_kill_switch_id == source.switch_id
    assert entry.source_kill_switch_generation == source.new_generation
    assert result.state.status is IncidentStatus.DECLARED
    assert not hasattr(service, "engage_kill_switch")
    assert not hasattr(service, "release_kill_switch")
    assert not hasattr(adapter, "change_kill_switch")


def test_ordinary_containment_append_rejects_forged_kill_switch_provenance() -> None:
    backing = RecordedIncidentAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=10,
    )

    class ForgedProvenanceStore:
        def apply(
            self,
            *,
            command: IncidentCommand,
            command_fingerprint: IncidentFingerprint,
            idempotency_fingerprint: IncidentFingerprint,
            minimum_generation: int,
            observed_state: IncidentState | None,
            allow_unobserved_incident: bool,
        ) -> IncidentStoreOutcome:
            outcome = backing.apply(
                command=command,
                command_fingerprint=command_fingerprint,
                idempotency_fingerprint=idempotency_fingerprint,
                minimum_generation=minimum_generation,
                observed_state=observed_state,
                allow_unobserved_incident=allow_unobserved_incident,
            )
            entry = outcome.result.timeline_entry
            if (
                type(command) is AppendIncidentTimelineCommand
                and command.event_type is IncidentTimelineType.CONTAINMENT
                and entry is not None
            ):
                forged_entry = replace(
                    entry,
                    source_kill_switch_event_id=KILL_EVENT_ID,
                    source_kill_switch_id=UUID("60000000-0000-4000-8000-000000000099"),
                    source_kill_switch_generation=1,
                )
                return replace(
                    outcome,
                    result=replace(
                        outcome.result,
                        timeline_entry=forged_entry,
                    ),
                )
            return outcome

    service = IncidentService(store=ForgedProvenanceStore(), capacity=10)
    service.declare(command=declare_command(), idempotency_key=idempotency_key())
    command = AppendIncidentTimelineCommand(
        incident_id=INCIDENT_ID,
        expected_generation=0,
        event_type=IncidentTimelineType.CONTAINMENT,
        note=IncidentTimelineNote("Synthetic containment observation"),
        actor_principal_id=ACTOR_ID,
        correlation_id=CORRELATION_ID,
        occurred_at=observed_at(1),
    )
    with pytest.raises(IncidentFailure) as caught:
        service.append_timeline(
            command=command,
            idempotency_key=idempotency_key("st1406-command-0002"),
        )
    assert caught.value.code is IncidentFailureCode.STORE_FAILURE
    retained = backing.timeline(INCIDENT_ID)
    assert len(retained) == 1
    assert retained[0].source_kill_switch_event_id is None
    assert retained[0].source_kill_switch_id is None
    assert retained[0].source_kill_switch_generation is None


@pytest.mark.parametrize(
    "forged_target",
    [
        IncidentStatus.CONTAINED,
        IncidentStatus.RECOVERING,
        IncidentStatus.MONITORING,
        IncidentStatus.CLOSED,
    ],
)
def test_transition_receipt_binds_milestones_to_command_and_prior_state(
    forged_target: IncidentStatus,
) -> None:
    backing = RecordedIncidentAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=10,
    )

    class ForgedMilestoneStore:
        def apply(
            self,
            *,
            command: IncidentCommand,
            command_fingerprint: IncidentFingerprint,
            idempotency_fingerprint: IncidentFingerprint,
            minimum_generation: int,
            observed_state: IncidentState | None,
            allow_unobserved_incident: bool,
        ) -> IncidentStoreOutcome:
            outcome = backing.apply(
                command=command,
                command_fingerprint=command_fingerprint,
                idempotency_fingerprint=idempotency_fingerprint,
                minimum_generation=minimum_generation,
                observed_state=observed_state,
                allow_unobserved_incident=allow_unobserved_incident,
            )
            if (
                type(command) is not TransitionIncidentCommand
                or command.target_status is not forged_target
            ):
                return outcome
            state = outcome.result.state
            if forged_target is IncidentStatus.CLOSED:
                assert state.recovered_at is not None
                forged_state = replace(state, closed_at=state.recovered_at)
            else:
                forged_state = replace(state, contained_at=DECLARED_AT)
            contract = outcome.result.contract_intent
            forged_contract = (
                None if contract is None else replace(contract, state=forged_state)
            )
            return replace(
                outcome,
                result=replace(
                    outcome.result,
                    state=forged_state,
                    contract_intent=forged_contract,
                ),
                current_state=forged_state,
            )

    service = IncidentService(store=ForgedMilestoneStore(), capacity=10)
    current = service.declare(
        command=declare_command(), idempotency_key=idempotency_key()
    )
    sequence = (
        IncidentStatus.CONTAINING,
        IncidentStatus.CONTAINED,
        IncidentStatus.RECOVERING,
        IncidentStatus.MONITORING,
        IncidentStatus.CLOSED,
    )
    for index, target in enumerate(sequence, start=1):
        references = (
            (
                IncidentEvidenceReference(
                    artifact_id=ARTIFACT_ID,
                    artifact_sha256="c" * 64,
                ),
            )
            if target is IncidentStatus.CLOSED
            else ()
        )
        command = TransitionIncidentCommand(
            incident_id=INCIDENT_ID,
            expected_generation=current.state.generation,
            target_status=target,
            note=IncidentTimelineNote(f"Synthetic lifecycle {target.value}"),
            actor_principal_id=ACTOR_ID,
            correlation_id=CORRELATION_ID,
            occurred_at=observed_at(index),
            evidence_references=references,
            root_cause_recorded=target is IncidentStatus.CLOSED,
        )
        if target is forged_target:
            with pytest.raises(IncidentFailure) as caught:
                service.transition(
                    command=command,
                    idempotency_key=idempotency_key(
                        f"st1406-forged-milestone-{index:04d}"
                    ),
                )
            assert caught.value.code is IncidentFailureCode.STORE_FAILURE
            retained = backing.current_state(INCIDENT_ID)
            assert retained is not None
            if target is IncidentStatus.CONTAINED:
                assert retained.contained_at == observed_at(index)
            elif target in {
                IncidentStatus.RECOVERING,
                IncidentStatus.MONITORING,
            }:
                assert retained.contained_at == observed_at(2)
            else:
                assert retained.closed_at == observed_at(index)
            break
        current = service.transition(
            command=command,
            idempotency_key=idempotency_key(f"st1406-valid-milestone-{index:04d}"),
        )


def test_release_mismatch_duplicate_and_time_regression_intents_fail_closed() -> None:
    service, adapter = service_bundle(capacity=10)
    service.declare(command=declare_command(), idempotency_key=idempotency_key())
    source = engaged_kill_switch_intent()
    service.record_kill_switch_intent(
        command=RecordKillSwitchIntentCommand(
            incident_id=INCIDENT_ID,
            expected_generation=0,
            intent=source,
        ),
        idempotency_key=idempotency_key("st1406-command-0002"),
    )
    before = adapter.timeline(INCIDENT_ID)

    with pytest.raises(IncidentFailure) as duplicate:
        service.record_kill_switch_intent(
            command=RecordKillSwitchIntentCommand(
                incident_id=INCIDENT_ID,
                expected_generation=1,
                intent=source,
            ),
            idempotency_key=idempotency_key("st1406-command-0003"),
        )
    assert duplicate.value.code is IncidentFailureCode.STATE_CONFLICT

    released = replace(
        source,
        previous_engaged=True,
        new_engaged=False,
        previous_generation=1,
        new_generation=2,
    )
    with pytest.raises(IncidentFailure) as release:
        RecordKillSwitchIntentCommand(
            incident_id=INCIDENT_ID,
            expected_generation=1,
            intent=released,
        )
    assert release.value.code is IncidentFailureCode.KILL_SWITCH_INTENT_INVALID

    mismatched = engaged_kill_switch_intent(
        incident_id=UUID("10000000-0000-4000-8000-000000000099")
    )
    with pytest.raises(IncidentFailure) as mismatch:
        RecordKillSwitchIntentCommand(
            incident_id=INCIDENT_ID,
            expected_generation=1,
            intent=mismatched,
        )
    assert mismatch.value.code is IncidentFailureCode.KILL_SWITCH_INTENT_INVALID
    assert adapter.timeline(INCIDENT_ID) == before


def test_concurrent_same_generation_mutations_admit_exactly_one() -> None:
    service, adapter = service_bundle(capacity=10)
    service.declare(command=declare_command(), idempotency_key=idempotency_key())

    def invoke(index: int) -> str:
        try:
            service.append_timeline(
                command=_append_command(
                    expected_generation=0,
                    note=f"Concurrent note {index}",
                ),
                idempotency_key=idempotency_key(f"st1406-concurrent-{index:04d}"),
            )
        except IncidentFailure as error:
            return error.code.value
        return "RECORDED"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(invoke, (1, 2)))
    assert sorted(outcomes) == ["GENERATION_CONFLICT", "RECORDED"]
    assert adapter.current_state(INCIDENT_ID).generation == 1  # type: ignore[union-attr]
    assert len(adapter.timeline(INCIDENT_ID)) == 1


def test_capacity_failure_is_non_evicting_and_replay_remains_available() -> None:
    service, adapter = service_bundle(capacity=1)
    command = declare_command()
    key = idempotency_key()
    original = service.declare(command=command, idempotency_key=key)

    with pytest.raises(IncidentFailure) as caught:
        service.append_timeline(
            command=_append_command(expected_generation=0),
            idempotency_key=idempotency_key("st1406-command-0002"),
        )
    assert caught.value.code is IncidentFailureCode.CAPACITY_EXCEEDED
    assert adapter.current_state(INCIDENT_ID) == original.state
    assert adapter.timeline(INCIDENT_ID) == ()
    assert service.declare(command=command, idempotency_key=key) == original


def test_full_service_allows_store_known_replay_but_rejects_fresh_unknown() -> None:
    backing = RecordedIncidentAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=10,
    )
    shared_command = declare_command(
        incident_id=OTHER_INCIDENT_ID,
        display_id="INC-1407",
    )
    shared_key = idempotency_key("st1406-shared-replay")
    producer = IncidentService(store=backing, capacity=10)
    shared_result = producer.declare(
        command=shared_command,
        idempotency_key=shared_key,
    )

    class CountingStore:
        def __init__(self) -> None:
            self.calls = 0

        def apply(
            self,
            *,
            command: IncidentCommand,
            command_fingerprint: IncidentFingerprint,
            idempotency_fingerprint: IncidentFingerprint,
            minimum_generation: int,
            observed_state: IncidentState | None,
            allow_unobserved_incident: bool,
        ) -> IncidentStoreOutcome:
            self.calls += 1
            return backing.apply(
                command=command,
                command_fingerprint=command_fingerprint,
                idempotency_fingerprint=idempotency_fingerprint,
                minimum_generation=minimum_generation,
                observed_state=observed_state,
                allow_unobserved_incident=allow_unobserved_incident,
            )

    store = CountingStore()
    service = IncidentService(store=store, capacity=1)
    command = declare_command()
    key = idempotency_key()
    first = service.declare(command=command, idempotency_key=key)
    assert (
        service.declare(command=shared_command, idempotency_key=shared_key)
        == shared_result
    )
    assert service.declare(command=command, idempotency_key=key) == first
    assert store.calls == 3

    third_incident_id = UUID("10000000-0000-4000-8000-000000000003")
    with pytest.raises(IncidentFailure) as caught:
        service.declare(
            command=declare_command(
                incident_id=third_incident_id,
                display_id="INC-1408",
            ),
            idempotency_key=idempotency_key("st1406-command-unknown"),
        )
    assert caught.value.code is IncidentFailureCode.CAPACITY_EXCEEDED
    assert store.calls == 4
    assert backing.current_state(third_incident_id) is None
    assert (
        service.declare(command=shared_command, idempotency_key=shared_key)
        == shared_result
    )
    assert store.calls == 5


def test_hostile_fresh_admission_receipt_does_not_partially_bind_service() -> None:
    backing = RecordedIncidentAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=10,
    )

    class IgnoresAdmissionStore:
        def __init__(self) -> None:
            self.admissions: list[tuple[UUID, bool]] = []

        def apply(
            self,
            *,
            command: IncidentCommand,
            command_fingerprint: IncidentFingerprint,
            idempotency_fingerprint: IncidentFingerprint,
            minimum_generation: int,
            observed_state: IncidentState | None,
            allow_unobserved_incident: bool,
        ) -> IncidentStoreOutcome:
            self.admissions.append((command.incident_id, allow_unobserved_incident))
            return backing.apply(
                command=command,
                command_fingerprint=command_fingerprint,
                idempotency_fingerprint=idempotency_fingerprint,
                minimum_generation=minimum_generation,
                observed_state=observed_state,
                allow_unobserved_incident=True,
            )

    store = IgnoresAdmissionStore()
    service = IncidentService(store=store, capacity=1)
    known_command = declare_command()
    known_key = idempotency_key()
    known_result = service.declare(
        command=known_command,
        idempotency_key=known_key,
    )
    unknown_command = declare_command(
        incident_id=OTHER_INCIDENT_ID,
        display_id="INC-1407",
    )
    unknown_key = idempotency_key("st1406-hostile-admission")

    with pytest.raises(IncidentFailure) as fresh:
        service.declare(command=unknown_command, idempotency_key=unknown_key)
    assert fresh.value.code is IncidentFailureCode.STORE_FAILURE
    assert backing.current_state(OTHER_INCIDENT_ID) is not None

    replay = service.declare(command=unknown_command, idempotency_key=unknown_key)
    assert replay.state.incident_id == OTHER_INCIDENT_ID
    assert (
        service.declare(command=known_command, idempotency_key=known_key)
        == known_result
    )
    assert store.admissions == [
        (INCIDENT_ID, True),
        (OTHER_INCIDENT_ID, False),
        (OTHER_INCIDENT_ID, False),
        (INCIDENT_ID, True),
    ]


def test_hostile_fresh_receipt_failure_does_not_consume_service_capacity() -> None:
    backing = RecordedIncidentAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=10,
    )

    class FirstReceiptTamperStore:
        def __init__(self) -> None:
            self.tamper_next = True

        def apply(
            self,
            *,
            command: IncidentCommand,
            command_fingerprint: IncidentFingerprint,
            idempotency_fingerprint: IncidentFingerprint,
            minimum_generation: int,
            observed_state: IncidentState | None,
            allow_unobserved_incident: bool,
        ) -> IncidentStoreOutcome:
            outcome = backing.apply(
                command=command,
                command_fingerprint=command_fingerprint,
                idempotency_fingerprint=idempotency_fingerprint,
                minimum_generation=minimum_generation,
                observed_state=observed_state,
                allow_unobserved_incident=allow_unobserved_incident,
            )
            if self.tamper_next:
                self.tamper_next = False
                return replace(
                    outcome,
                    command_fingerprint=IncidentFingerprint("0" * 64),
                )
            return outcome

    service = IncidentService(store=FirstReceiptTamperStore(), capacity=1)
    with pytest.raises(IncidentFailure) as tampered:
        service.declare(
            command=declare_command(),
            idempotency_key=idempotency_key(),
        )
    assert tampered.value.code is IncidentFailureCode.STORE_FAILURE

    accepted = service.declare(
        command=declare_command(
            incident_id=OTHER_INCIDENT_ID,
            display_id="INC-1407",
        ),
        idempotency_key=idempotency_key("st1406-command-recovered"),
    )
    assert accepted.state.incident_id == OTHER_INCIDENT_ID


@pytest.mark.parametrize(
    "scenario",
    ["declare", "append", "transition", "kill-switch", "close"],
)
def test_service_defensively_snapshots_every_command_before_store_call(
    scenario: str,
) -> None:
    states, caller_command = _hostile_command_case(scenario)

    backing = RecordedIncidentAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=10,
        states=states,
    )

    class MutatesCommandStore:
        def __init__(self) -> None:
            self.tamper_next = True
            self.received_caller_alias = False
            self.received_nested_uuid_alias = False

        def apply(
            self,
            *,
            command: IncidentCommand,
            command_fingerprint: IncidentFingerprint,
            idempotency_fingerprint: IncidentFingerprint,
            minimum_generation: int,
            observed_state: IncidentState | None,
            allow_unobserved_incident: bool,
        ) -> IncidentStoreOutcome:
            self.received_caller_alias |= command is caller_command
            self.received_nested_uuid_alias |= (
                command.incident_id is caller_command.incident_id
            )
            if self.tamper_next:
                self.tamper_next = False
                original_fingerprint = command_fingerprint.value
                if type(command) is DeclareIncidentCommand:
                    object.__setattr__(
                        command,
                        "title",
                        IncidentTitle("Collaborator-mutated synthetic title"),
                    )
                elif type(command) is AppendIncidentTimelineCommand:
                    object.__setattr__(
                        command,
                        "note",
                        IncidentTimelineNote("Collaborator-mutated append note"),
                    )
                elif type(command) is TransitionIncidentCommand:
                    object.__setattr__(
                        command,
                        "note",
                        IncidentTimelineNote("Collaborator-mutated transition note"),
                    )
                else:
                    self.received_nested_uuid_alias |= (
                        command.intent.event_id is caller_command.intent.event_id
                        if type(caller_command) is RecordKillSwitchIntentCommand
                        else False
                    )
                    object.__setattr__(
                        command,
                        "intent",
                        replace(
                            command.intent,
                            correlation_id=OTHER_CORRELATION_ID,
                        ),
                    )
                outcome = backing.apply(
                    command=command,
                    command_fingerprint=command.fingerprint(),
                    idempotency_fingerprint=idempotency_fingerprint,
                    minimum_generation=minimum_generation,
                    observed_state=observed_state,
                    allow_unobserved_incident=allow_unobserved_incident,
                )
                return replace(
                    outcome,
                    command_fingerprint=IncidentFingerprint(original_fingerprint),
                )
            return backing.apply(
                command=command,
                command_fingerprint=command_fingerprint,
                idempotency_fingerprint=idempotency_fingerprint,
                minimum_generation=minimum_generation,
                observed_state=observed_state,
                allow_unobserved_incident=allow_unobserved_incident,
            )

    store = MutatesCommandStore()
    service = IncidentService(store=store, capacity=1)
    original_fingerprint = caller_command.fingerprint().value
    key = idempotency_key(f"st1406-hostile-command-{scenario}")

    with pytest.raises(IncidentFailure) as caught:
        if type(caller_command) is DeclareIncidentCommand:
            service.declare(command=caller_command, idempotency_key=key)
        elif type(caller_command) is AppendIncidentTimelineCommand:
            service.append_timeline(command=caller_command, idempotency_key=key)
        elif type(caller_command) is TransitionIncidentCommand:
            service.transition(command=caller_command, idempotency_key=key)
        else:
            service.record_kill_switch_intent(
                command=caller_command,
                idempotency_key=key,
            )
    assert caught.value.code is IncidentFailureCode.STORE_FAILURE
    assert caller_command.fingerprint().value == original_fingerprint
    assert store.received_caller_alias is False
    assert store.received_nested_uuid_alias is False

    recovered = service.declare(
        command=declare_command(
            incident_id=OTHER_INCIDENT_ID,
            display_id="INC-1407",
        ),
        idempotency_key=idempotency_key(f"st1406-hostile-recovered-{scenario}"),
    )
    assert recovered.state.incident_id == OTHER_INCIDENT_ID


@pytest.mark.parametrize(
    "scenario",
    ["declare", "append", "transition", "kill-switch", "close"],
)
@pytest.mark.parametrize("target", ["original-command", "original-key"])
def test_service_revalidates_caller_owned_inputs_after_store_return(
    scenario: str,
    target: str,
) -> None:
    states, caller_command = _hostile_command_case(scenario)
    caller_key = idempotency_key(f"st1406-original-input-{scenario}-{target}")
    backing = RecordedIncidentAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=10,
        states=states,
    )

    class MutatesOriginalInputStore:
        def __init__(self) -> None:
            self.tamper_next = True

        def apply(
            self,
            *,
            command: IncidentCommand,
            command_fingerprint: IncidentFingerprint,
            idempotency_fingerprint: IncidentFingerprint,
            minimum_generation: int,
            observed_state: IncidentState | None,
            allow_unobserved_incident: bool,
        ) -> IncidentStoreOutcome:
            outcome = backing.apply(
                command=command,
                command_fingerprint=command_fingerprint,
                idempotency_fingerprint=idempotency_fingerprint,
                minimum_generation=minimum_generation,
                observed_state=observed_state,
                allow_unobserved_incident=allow_unobserved_incident,
            )
            if not self.tamper_next:
                return outcome
            self.tamper_next = False
            if target == "original-key":
                object.__setattr__(
                    caller_key,
                    "_value",
                    "st1406-collaborator-mutated-original-key",
                )
            elif type(caller_command) is DeclareIncidentCommand:
                object.__setattr__(
                    caller_command.title,
                    "_value",
                    "Collaborator-mutated caller title",
                )
            elif type(caller_command) is AppendIncidentTimelineCommand:
                object.__setattr__(
                    caller_command.note,
                    "_value",
                    "Collaborator-mutated caller append note",
                )
            elif type(caller_command) is TransitionIncidentCommand:
                object.__setattr__(
                    caller_command.note,
                    "_value",
                    "Collaborator-mutated caller transition note",
                )
            else:
                object.__setattr__(
                    caller_command.intent.correlation_id,
                    "int",
                    OTHER_CORRELATION_ID.int,
                )
            return outcome

    service = IncidentService(store=MutatesOriginalInputStore(), capacity=1)
    with pytest.raises(IncidentFailure) as caught:
        if type(caller_command) is DeclareIncidentCommand:
            service.declare(command=caller_command, idempotency_key=caller_key)
        elif type(caller_command) is AppendIncidentTimelineCommand:
            service.append_timeline(command=caller_command, idempotency_key=caller_key)
        elif type(caller_command) is TransitionIncidentCommand:
            service.transition(command=caller_command, idempotency_key=caller_key)
        else:
            service.record_kill_switch_intent(
                command=caller_command,
                idempotency_key=caller_key,
            )
    assert caught.value.code is IncidentFailureCode.STORE_FAILURE

    recovered = service.declare(
        command=declare_command(
            incident_id=OTHER_INCIDENT_ID,
            display_id="INC-1407",
        ),
        idempotency_key=idempotency_key(
            f"st1406-original-input-recovered-{scenario}-{target}"
        ),
    )
    assert recovered.state.incident_id == OTHER_INCIDENT_ID


@pytest.mark.parametrize(
    "tamper",
    ["delete-command", "malform-command", "delete-key", "malform-key"],
)
def test_service_sanitizes_deleted_or_malformed_caller_owned_inputs(
    tamper: str,
) -> None:
    caller_command = declare_command()
    caller_key = idempotency_key(f"st1406-original-malformed-{tamper}")
    backing = RecordedIncidentAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=10,
    )

    class MalformsOriginalInputStore:
        def __init__(self) -> None:
            self.tamper_next = True

        def apply(
            self,
            *,
            command: IncidentCommand,
            command_fingerprint: IncidentFingerprint,
            idempotency_fingerprint: IncidentFingerprint,
            minimum_generation: int,
            observed_state: IncidentState | None,
            allow_unobserved_incident: bool,
        ) -> IncidentStoreOutcome:
            outcome = backing.apply(
                command=command,
                command_fingerprint=command_fingerprint,
                idempotency_fingerprint=idempotency_fingerprint,
                minimum_generation=minimum_generation,
                observed_state=observed_state,
                allow_unobserved_incident=allow_unobserved_incident,
            )
            if not self.tamper_next:
                return outcome
            self.tamper_next = False
            if tamper == "delete-command":
                object.__delattr__(caller_command.title, "_value")
            elif tamper == "malform-command":
                object.__setattr__(caller_command.title, "_value", object())
            elif tamper == "delete-key":
                object.__delattr__(caller_key, "_value")
            else:
                object.__setattr__(caller_key, "_value", object())
            return outcome

    service = IncidentService(store=MalformsOriginalInputStore(), capacity=1)
    with pytest.raises(IncidentFailure) as caught:
        service.declare(command=caller_command, idempotency_key=caller_key)
    assert caught.value.code is IncidentFailureCode.STORE_FAILURE
    assert "object" not in str(caught.value)

    recovered = service.declare(
        command=declare_command(
            incident_id=OTHER_INCIDENT_ID,
            display_id="INC-1407",
        ),
        idempotency_key=idempotency_key(f"st1406-malformed-recovered-{tamper}"),
    )
    assert recovered.state.incident_id == OTHER_INCIDENT_ID


@pytest.mark.parametrize("target", ["command", "idempotency"])
def test_service_rejects_post_call_fingerprint_parameter_mutation(target: str) -> None:
    backing = RecordedIncidentAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=10,
    )

    class MutatesFingerprintStore:
        def __init__(self) -> None:
            self.tamper_next = True

        def apply(
            self,
            *,
            command: IncidentCommand,
            command_fingerprint: IncidentFingerprint,
            idempotency_fingerprint: IncidentFingerprint,
            minimum_generation: int,
            observed_state: IncidentState | None,
            allow_unobserved_incident: bool,
        ) -> IncidentStoreOutcome:
            outcome = backing.apply(
                command=command,
                command_fingerprint=command_fingerprint,
                idempotency_fingerprint=idempotency_fingerprint,
                minimum_generation=minimum_generation,
                observed_state=observed_state,
                allow_unobserved_incident=allow_unobserved_incident,
            )
            if not self.tamper_next:
                return outcome
            self.tamper_next = False
            if target == "command":
                original = command_fingerprint.value
                object.__setattr__(command_fingerprint, "_value", "0" * 64)
                return replace(
                    outcome,
                    command_fingerprint=IncidentFingerprint(original),
                )
            original = idempotency_fingerprint.value
            object.__setattr__(idempotency_fingerprint, "_value", "0" * 64)
            return replace(
                outcome,
                idempotency_fingerprint=IncidentFingerprint(original),
            )

    service = IncidentService(store=MutatesFingerprintStore(), capacity=1)
    with pytest.raises(IncidentFailure) as caught:
        service.declare(
            command=declare_command(),
            idempotency_key=idempotency_key(f"st1406-hostile-{target}-fingerprint"),
        )
    assert caught.value.code is IncidentFailureCode.STORE_FAILURE

    recovered = service.declare(
        command=declare_command(
            incident_id=OTHER_INCIDENT_ID,
            display_id="INC-1407",
        ),
        idempotency_key=idempotency_key(
            f"st1406-hostile-{target}-fingerprint-recovered"
        ),
    )
    assert recovered.state.incident_id == OTHER_INCIDENT_ID


def test_service_rejects_post_call_observed_state_mutation_without_binding() -> None:
    backing = RecordedIncidentAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=10,
    )

    class MutatesObservationStore:
        def __init__(self) -> None:
            self.tamper_observation = False

        def apply(
            self,
            *,
            command: IncidentCommand,
            command_fingerprint: IncidentFingerprint,
            idempotency_fingerprint: IncidentFingerprint,
            minimum_generation: int,
            observed_state: IncidentState | None,
            allow_unobserved_incident: bool,
        ) -> IncidentStoreOutcome:
            outcome = backing.apply(
                command=command,
                command_fingerprint=command_fingerprint,
                idempotency_fingerprint=idempotency_fingerprint,
                minimum_generation=minimum_generation,
                observed_state=observed_state,
                allow_unobserved_incident=allow_unobserved_incident,
            )
            if self.tamper_observation:
                self.tamper_observation = False
                assert observed_state is not None
                object.__setattr__(
                    observed_state,
                    "generation",
                    observed_state.generation + 100,
                )
            return outcome

    store = MutatesObservationStore()
    service = IncidentService(store=store, capacity=10)
    service.declare(command=declare_command(), idempotency_key=idempotency_key())
    store.tamper_observation = True
    with pytest.raises(IncidentFailure) as caught:
        service.append_timeline(
            command=_append_command(expected_generation=0),
            idempotency_key=idempotency_key("st1406-hostile-observation"),
        )
    assert caught.value.code is IncidentFailureCode.STORE_FAILURE
    retained = backing.current_state(INCIDENT_ID)
    assert retained is not None
    assert retained.generation == 1

    with pytest.raises(IncidentFailure) as stale:
        service.append_timeline(
            command=_append_command(
                expected_generation=1,
                minutes=2,
                note="Must not use a rejected collaborator observation",
            ),
            idempotency_key=idempotency_key("st1406-hostile-observation-followup"),
        )
    assert stale.value.code is IncidentFailureCode.STATE_CONFLICT
    assert len(backing.timeline(INCIDENT_ID)) == 1


def test_adapter_returned_fingerprint_mutation_cannot_poison_idempotency() -> None:
    adapter = RecordedIncidentAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=10,
    )
    command = declare_command()
    key = idempotency_key("st1406-adapter-fingerprint-copy")
    command_fingerprint = command.fingerprint()
    idempotency_fingerprint = key.fingerprint()
    first = adapter.apply(
        command=command,
        command_fingerprint=command_fingerprint,
        idempotency_fingerprint=idempotency_fingerprint,
        minimum_generation=0,
        observed_state=None,
        allow_unobserved_incident=True,
    )
    assert first.command_fingerprint is not command_fingerprint
    assert first.idempotency_fingerprint is not idempotency_fingerprint

    changed = declare_command(correlation_id=OTHER_CORRELATION_ID)
    object.__setattr__(
        first.command_fingerprint,
        "_value",
        changed.fingerprint().value,
    )
    object.__setattr__(first.idempotency_fingerprint, "_value", "f" * 64)
    object.__setattr__(
        command_fingerprint,
        "_value",
        changed.fingerprint().value,
    )
    object.__setattr__(idempotency_fingerprint, "_value", "e" * 64)
    with pytest.raises(IncidentFailure) as conflict:
        adapter.apply(
            command=changed,
            command_fingerprint=changed.fingerprint(),
            idempotency_fingerprint=key.fingerprint(),
            minimum_generation=0,
            observed_state=None,
            allow_unobserved_incident=True,
        )
    assert conflict.value.code is IncidentFailureCode.IDEMPOTENCY_CONFLICT

    replay = adapter.apply(
        command=command,
        command_fingerprint=command.fingerprint(),
        idempotency_fingerprint=key.fingerprint(),
        minimum_generation=0,
        observed_state=None,
        allow_unobserved_incident=True,
    )
    assert replay.replayed is True
    assert replay.command_fingerprint == command.fingerprint()
    assert replay.idempotency_fingerprint == key.fingerprint()
    assert replay.command_fingerprint is not first.command_fingerprint
    assert replay.idempotency_fingerprint is not first.idempotency_fingerprint


def test_adapter_receipts_and_getters_do_not_alias_stored_nested_values() -> None:
    adapter = RecordedIncidentAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=10,
    )
    command = replace(
        declare_command(),
        incident_id=UUID(str(INCIDENT_ID)),
        declared_by_principal_id=UUID(str(DECLARER_ID)),
        owner_principal_id=UUID(str(OWNER_ID)),
        commander_principal_id=UUID(str(COMMANDER_ID)),
        correlation_id=UUID(str(CORRELATION_ID)),
    )
    key = idempotency_key("st1406-adapter-deep-copy")
    first = adapter.apply(
        command=command,
        command_fingerprint=command.fingerprint(),
        idempotency_fingerprint=key.fingerprint(),
        minimum_generation=0,
        observed_state=None,
        allow_unobserved_incident=True,
    )
    contract = first.result.contract_intent
    assert contract is not None
    object.__setattr__(command.incident_id, "int", OTHER_INCIDENT_ID.int)
    object.__setattr__(first.result.state.incident_id, "int", OTHER_INCIDENT_ID.int)
    object.__setattr__(first.current_state.owner_principal_id, "int", DECLARER_ID.int)
    object.__setattr__(contract.event_id, "int", KILL_EVENT_ID.int)

    replay_command = declare_command()
    declaration_replay = adapter.apply(
        command=replay_command,
        command_fingerprint=replay_command.fingerprint(),
        idempotency_fingerprint=key.fingerprint(),
        minimum_generation=0,
        observed_state=None,
        allow_unobserved_incident=True,
    )
    assert declaration_replay.result.state.incident_id == INCIDENT_ID
    assert declaration_replay.current_state.owner_principal_id == OWNER_ID
    replay_contract = declaration_replay.result.contract_intent
    assert replay_contract is not None
    assert replay_contract.event_id != KILL_EVENT_ID
    retained = adapter.current_state(INCIDENT_ID)
    assert retained is not None
    assert retained.incident_id == INCIDENT_ID
    assert retained.owner_principal_id == OWNER_ID

    append = replace(
        _append_command(expected_generation=0),
        incident_id=UUID(str(INCIDENT_ID)),
        actor_principal_id=UUID(str(ACTOR_ID)),
        correlation_id=UUID(str(CORRELATION_ID)),
    )
    append_key = idempotency_key("st1406-adapter-deep-copy-append")
    appended = adapter.apply(
        command=append,
        command_fingerprint=append.fingerprint(),
        idempotency_fingerprint=append_key.fingerprint(),
        minimum_generation=0,
        observed_state=retained,
        allow_unobserved_incident=True,
    )
    entry = appended.result.timeline_entry
    assert entry is not None
    original_event_id = UUID(int=entry.event_id.int)
    object.__setattr__(append.actor_principal_id, "int", DECLARER_ID.int)
    object.__setattr__(
        entry.event_id,
        "int",
        UUID("80000000-0000-4000-8000-000000000099").int,
    )
    object.__setattr__(appended.result.state.owner_principal_id, "int", DECLARER_ID.int)
    object.__setattr__(
        appended.current_state.commander_principal_id,
        "int",
        DECLARER_ID.int,
    )

    retained_timeline = adapter.timeline(INCIDENT_ID)
    assert len(retained_timeline) == 1
    assert retained_timeline[0].event_id == original_event_id
    retained_after_append = adapter.current_state(INCIDENT_ID)
    assert retained_after_append is not None
    assert retained_after_append.owner_principal_id == OWNER_ID
    assert retained_after_append.commander_principal_id == COMMANDER_ID

    replay_append = _append_command(expected_generation=0)
    append_replay = adapter.apply(
        command=replay_append,
        command_fingerprint=replay_append.fingerprint(),
        idempotency_fingerprint=append_key.fingerprint(),
        minimum_generation=0,
        observed_state=None,
        allow_unobserved_incident=True,
    )
    replay_entry = append_replay.result.timeline_entry
    assert append_replay.replayed is True
    assert replay_entry is not None
    assert replay_entry.event_id == original_event_id
    assert append_replay.result.state.owner_principal_id == OWNER_ID
    assert append_replay.current_state.commander_principal_id == COMMANDER_ID


@pytest.mark.parametrize("capacity", [True, 0, -1, MAX_INCIDENT_TIMELINE_ENTRIES + 1])
def test_service_capacity_is_exact_positive_and_bounded(capacity: int) -> None:
    adapter = RecordedIncidentAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=1,
    )
    with pytest.raises(IncidentFailure) as caught:
        IncidentService(store=adapter, capacity=capacity)
    assert caught.value.code is IncidentFailureCode.INVALID_ARGUMENT


@pytest.mark.parametrize(
    "environment",
    [
        RuntimeEnvironment.INTEGRATION,
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.RECOVERY,
        RuntimeEnvironment.PRODUCTION,
    ],
)
def test_recorded_adapter_rejects_every_non_dev_ci_environment(
    environment: RuntimeEnvironment,
) -> None:
    with pytest.raises(IncidentFailure) as caught:
        RecordedIncidentAdapter(
            environment=environment,
            event_namespace=EVENT_NAMESPACE,
            capacity=1,
        )
    assert caught.value.code is IncidentFailureCode.DEVELOPMENT_ONLY


def test_ci_environment_is_explicitly_supported_without_external_io() -> None:
    service, adapter = service_bundle(environment=RuntimeEnvironment.CI)
    result = service.declare(
        command=declare_command(), idempotency_key=idempotency_key()
    )
    assert adapter.environment is RuntimeEnvironment.CI
    assert result.state.incident_id == INCIDENT_ID


def test_seeded_timeline_requires_contiguous_complete_projected_history() -> None:
    note_one = _seed_timeline_entry(
        event_id=UUID("80000000-0000-4000-8000-000000000011"),
        generation=1,
        occurred_minutes=1,
    )
    note_two = _seed_timeline_entry(
        event_id=UUID("80000000-0000-4000-8000-000000000012"),
        generation=2,
        occurred_minutes=2,
    )
    valid_state = replace(incident_state(), generation=2, updated_at=observed_at(2))
    valid = RecordedIncidentAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=10,
        states=(valid_state,),
        timeline=(note_one, note_two),
    )
    assert valid.timeline(INCIDENT_ID) == (note_one, note_two)

    before_declaration = replace(note_one, occurred_at=observed_at(-1))
    gap = replace(note_two, event_id=UUID("80000000-0000-4000-8000-000000000013"))
    first_transition = _seed_timeline_entry(
        event_id=UUID("80000000-0000-4000-8000-000000000014"),
        generation=1,
        occurred_minutes=1,
        event_type=IncidentTimelineType.STATUS_CHANGE,
        previous_status=IncidentStatus.DECLARED,
        new_status=IncidentStatus.CONTAINING,
    )
    broken_transition = _seed_timeline_entry(
        event_id=UUID("80000000-0000-4000-8000-000000000015"),
        generation=2,
        occurred_minutes=2,
        event_type=IncidentTimelineType.STATUS_CHANGE,
        previous_status=IncidentStatus.DECLARED,
        new_status=IncidentStatus.CONTAINING,
    )
    containing_state = replace(
        incident_state(),
        status=IncidentStatus.CONTAINING,
        generation=2,
        updated_at=observed_at(2),
    )
    wrong_terminal_status = replace(
        incident_state(), generation=1, updated_at=observed_at(1)
    )
    contained_transition = _seed_timeline_entry(
        event_id=UUID("80000000-0000-4000-8000-000000000016"),
        generation=2,
        occurred_minutes=2,
        event_type=IncidentTimelineType.STATUS_CHANGE,
        previous_status=IncidentStatus.CONTAINING,
        new_status=IncidentStatus.CONTAINED,
    )
    wrong_terminal_milestone = replace(
        incident_state(),
        status=IncidentStatus.CONTAINED,
        generation=2,
        updated_at=observed_at(2),
        contained_at=observed_at(1),
    )
    incomplete_state = replace(
        incident_state(),
        status=IncidentStatus.CONTAINED,
        generation=2,
        updated_at=observed_at(2),
        contained_at=observed_at(2),
    )
    late_terminal_state = replace(
        incident_state(), generation=1, updated_at=observed_at(2)
    )
    invalid_seeds = (
        (
            replace(incident_state(), generation=1, updated_at=observed_at(1)),
            (before_declaration,),
        ),
        (valid_state, (gap,)),
        (containing_state, (first_transition, broken_transition)),
        (wrong_terminal_status, (first_transition,)),
        (wrong_terminal_milestone, (first_transition, contained_transition)),
        (incomplete_state, (first_transition,)),
        (late_terminal_state, (note_one,)),
    )
    for state, timeline in invalid_seeds:
        with pytest.raises(IncidentFailure) as caught:
            RecordedIncidentAdapter(
                environment=RuntimeEnvironment.ENV_DEV,
                event_namespace=EVENT_NAMESPACE,
                capacity=10,
                states=(state,),
                timeline=timeline,
            )
        assert caught.value.code is IncidentFailureCode.INVALID_ARGUMENT


def test_seeded_timeline_local_and_source_event_id_sets_are_disjoint() -> None:
    local_event_id = UUID("80000000-0000-4000-8000-000000000021")
    first = _seed_timeline_entry(
        event_id=local_event_id,
        generation=1,
        occurred_minutes=1,
    )
    second = _seed_timeline_entry(
        event_id=UUID("80000000-0000-4000-8000-000000000022"),
        generation=2,
        occurred_minutes=2,
        event_type=IncidentTimelineType.CONTAINMENT,
        source_event_id=local_event_id,
    )
    state = replace(incident_state(), generation=2, updated_at=observed_at(2))

    with pytest.raises(IncidentFailure) as caught:
        RecordedIncidentAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            event_namespace=EVENT_NAMESPACE,
            capacity=10,
            states=(state,),
            timeline=(first, second),
        )
    assert caught.value.code is IncidentFailureCode.INVALID_ARGUMENT


def test_generated_declaration_and_timeline_ids_cannot_reuse_source_ids() -> None:
    declaration_key = idempotency_key("st1406-collision-declared")
    timeline_key = idempotency_key("st1406-collision-timeline")
    declaration_collision = _derived_event_id(declaration_key, "declared")
    timeline_collision = _derived_event_id(timeline_key, "timeline")
    other_state = replace(
        incident_state(),
        incident_id=OTHER_INCIDENT_ID,
        display_id=IncidentDisplayId("INC-1407"),
        generation=2,
        updated_at=observed_at(2),
    )
    other_entries = (
        _seed_timeline_entry(
            event_id=UUID("80000000-0000-4000-8000-000000000031"),
            incident_id=OTHER_INCIDENT_ID,
            generation=1,
            occurred_minutes=1,
            event_type=IncidentTimelineType.CONTAINMENT,
            source_event_id=declaration_collision,
        ),
        _seed_timeline_entry(
            event_id=UUID("80000000-0000-4000-8000-000000000032"),
            incident_id=OTHER_INCIDENT_ID,
            generation=2,
            occurred_minutes=2,
            event_type=IncidentTimelineType.CONTAINMENT,
            source_event_id=timeline_collision,
        ),
    )
    adapter = RecordedIncidentAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=10,
        states=(incident_state(), other_state),
        timeline=other_entries,
    )
    service = IncidentService(store=adapter, capacity=10)

    with pytest.raises(IncidentFailure) as declaration_failure:
        service.declare(
            command=declare_command(
                incident_id=UUID("10000000-0000-4000-8000-000000000003"),
                display_id="INC-1408",
            ),
            idempotency_key=declaration_key,
        )
    assert declaration_failure.value.code is IncidentFailureCode.STATE_CONFLICT

    with pytest.raises(IncidentFailure) as timeline_failure:
        service.append_timeline(
            command=_append_command(expected_generation=0),
            idempotency_key=timeline_key,
        )
    assert timeline_failure.value.code is IncidentFailureCode.STATE_CONFLICT
    assert adapter.current_state(INCIDENT_ID) == incident_state()
    assert adapter.timeline(INCIDENT_ID) == ()
    assert adapter.timeline(OTHER_INCIDENT_ID) == other_entries


def test_generated_closure_id_cannot_reuse_a_source_event_id() -> None:
    closure_key = idempotency_key("st1406-collision-closed")
    closure_collision = _derived_event_id(closure_key, "closed")
    monitoring = replace(
        incident_state(),
        status=IncidentStatus.MONITORING,
        generation=4,
        updated_at=observed_at(4),
        contained_at=observed_at(2),
        recovered_at=observed_at(4),
    )
    other_state = replace(
        incident_state(),
        incident_id=OTHER_INCIDENT_ID,
        display_id=IncidentDisplayId("INC-1407"),
        generation=1,
        updated_at=observed_at(1),
    )
    source_entry = _seed_timeline_entry(
        event_id=UUID("80000000-0000-4000-8000-000000000033"),
        incident_id=OTHER_INCIDENT_ID,
        generation=1,
        occurred_minutes=1,
        event_type=IncidentTimelineType.CONTAINMENT,
        source_event_id=closure_collision,
    )
    adapter = RecordedIncidentAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=10,
        states=(monitoring, other_state),
        timeline=(source_entry,),
    )
    service = IncidentService(store=adapter, capacity=10)
    command = TransitionIncidentCommand(
        incident_id=INCIDENT_ID,
        expected_generation=4,
        target_status=IncidentStatus.CLOSED,
        note=IncidentTimelineNote("Synthetic collision-safe closure"),
        actor_principal_id=ACTOR_ID,
        correlation_id=CORRELATION_ID,
        occurred_at=observed_at(5),
        evidence_references=(
            IncidentEvidenceReference(
                artifact_id=ARTIFACT_ID,
                artifact_sha256="d" * 64,
            ),
        ),
        root_cause_recorded=True,
    )

    with pytest.raises(IncidentFailure) as caught:
        service.transition(command=command, idempotency_key=closure_key)
    assert caught.value.code is IncidentFailureCode.STATE_CONFLICT
    assert adapter.current_state(INCIDENT_ID) == monitoring
    assert adapter.timeline(INCIDENT_ID) == ()
    assert adapter.timeline(OTHER_INCIDENT_ID) == (source_entry,)


def test_incoming_source_id_cannot_reuse_any_local_or_generated_timeline_id() -> None:
    service, adapter = service_bundle(capacity=10)
    declared = service.declare(
        command=declare_command(), idempotency_key=idempotency_key()
    )
    declared_intent = declared.contract_intent
    assert declared_intent is not None
    local_collision_command = RecordKillSwitchIntentCommand(
        incident_id=INCIDENT_ID,
        expected_generation=0,
        intent=engaged_kill_switch_intent(
            event_id=declared_intent.event_id,
            occurred_at=observed_at(1),
        ),
    )
    with pytest.raises(IncidentFailure) as local_collision:
        service.record_kill_switch_intent(
            command=local_collision_command,
            idempotency_key=idempotency_key("st1406-source-local-collision"),
        )
    assert local_collision.value.code is IncidentFailureCode.STATE_CONFLICT

    timeline_key = idempotency_key("st1406-source-timeline-collision")
    timeline_collision_command = RecordKillSwitchIntentCommand(
        incident_id=INCIDENT_ID,
        expected_generation=0,
        intent=engaged_kill_switch_intent(
            event_id=_derived_event_id(timeline_key, "timeline"),
            occurred_at=observed_at(1),
        ),
    )
    with pytest.raises(IncidentFailure) as timeline_collision:
        service.record_kill_switch_intent(
            command=timeline_collision_command,
            idempotency_key=timeline_key,
        )
    assert timeline_collision.value.code is IncidentFailureCode.STATE_CONFLICT
    assert adapter.current_state(INCIDENT_ID) == declared.state
    assert adapter.timeline(INCIDENT_ID) == ()


def test_max_generation_cannot_overflow_or_mutate_seeded_state() -> None:
    state = IncidentState(
        incident_id=INCIDENT_ID,
        display_id=IncidentDisplayId("INC-1406"),
        severity=IncidentSeverity.SEV1,
        status=IncidentStatus.DECLARED,
        title=IncidentTitle("Synthetic incident"),
        summary=IncidentSummary("Synthetic local incident summary"),
        declared_by_principal_id=DECLARER_ID,
        owner_principal_id=OWNER_ID,
        commander_principal_id=COMMANDER_ID,
        declared_at=DECLARED_AT,
        updated_at=DECLARED_AT,
        generation=MAX_INCIDENT_GENERATION,
    )
    adapter = RecordedIncidentAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        event_namespace=EVENT_NAMESPACE,
        capacity=2,
        states=(state,),
    )
    service = IncidentService(store=adapter, capacity=2)
    with pytest.raises(IncidentFailure) as caught:
        service.append_timeline(
            command=_append_command(
                expected_generation=MAX_INCIDENT_GENERATION,
                minutes=1,
            ),
            idempotency_key=IncidentIdempotencyKey("st1406-command-overflow"),
        )
    assert caught.value.code is IncidentFailureCode.GENERATION_CONFLICT
    assert adapter.current_state(INCIDENT_ID) == state
    assert adapter.timeline(INCIDENT_ID) == ()


def test_unknown_store_output_and_exception_are_sanitized() -> None:
    class UnknownStore:
        def apply(self, **kwargs: object) -> object:
            del kwargs
            return object()

    class ExplodingStore:
        def apply(self, **kwargs: object) -> object:
            del kwargs
            raise ValueError("sensitive collaborator detail")

    for store in (UnknownStore(), ExplodingStore()):
        service = IncidentService(store=cast(IncidentStore, store), capacity=1)
        with pytest.raises(IncidentFailure) as caught:
            service.declare(
                command=declare_command(), idempotency_key=idempotency_key()
            )
        assert caught.value.code is IncidentFailureCode.STORE_FAILURE
        assert "sensitive" not in str(caught.value)
        assert caught.value.__cause__ is None

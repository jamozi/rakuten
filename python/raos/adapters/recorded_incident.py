"""Bounded DEV/CI in-memory adapter for the ST-1406 incident seam."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import hmac
from threading import Lock
from typing import NoReturn, SupportsIndex
from uuid import UUID, uuid5

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ops.incident import (
    AppendIncidentTimelineCommand,
    DeclareIncidentCommand,
    IncidentClosedEventIntent,
    IncidentCommand,
    IncidentDeclaredEventIntent,
    IncidentDisplayId,
    IncidentEvidenceReference,
    IncidentFailureCode,
    IncidentFingerprint,
    IncidentMutationResult,
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
    copy_incident_command,
    fail_incident,
    require_incident_generation,
    require_incident_transition,
)
from raos.ports.incident import IncidentStoreOutcome


_ALLOWED_ENVIRONMENTS = frozenset({RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI})


def _require_local_environment(environment: object) -> RuntimeEnvironment:
    if (
        type(environment) is not RuntimeEnvironment
        or environment not in _ALLOWED_ENVIRONMENTS
    ):
        fail_incident(IncidentFailureCode.DEVELOPMENT_ONLY)
    return environment


def _copy_uuid(value: object) -> UUID:
    if type(value) is not UUID:
        fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
    return UUID(int=value.int)


def _copy_optional_uuid(value: object) -> UUID | None:
    return None if value is None else _copy_uuid(value)


def _copy_utc(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is not UTC:
        fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
    return datetime(
        value.year,
        value.month,
        value.day,
        value.hour,
        value.minute,
        value.second,
        value.microsecond,
        tzinfo=UTC,
        fold=value.fold,
    )


def _copy_evidence(
    values: tuple[IncidentEvidenceReference, ...],
) -> tuple[IncidentEvidenceReference, ...]:
    if type(values) is not tuple or any(
        type(value) is not IncidentEvidenceReference for value in values
    ):
        fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
    return tuple(
        IncidentEvidenceReference(
            artifact_id=_copy_uuid(value.artifact_id),
            artifact_sha256=value.artifact_sha256,
        )
        for value in values
    )


def _copy_state(value: IncidentState) -> IncidentState:
    if type(value) is not IncidentState:
        fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
    return IncidentState(
        incident_id=_copy_uuid(value.incident_id),
        display_id=IncidentDisplayId(value.display_id.value),
        severity=value.severity,
        status=value.status,
        title=IncidentTitle(value.title.value),
        summary=IncidentSummary(value.summary.value),
        declared_by_principal_id=_copy_uuid(value.declared_by_principal_id),
        owner_principal_id=_copy_uuid(value.owner_principal_id),
        commander_principal_id=_copy_uuid(value.commander_principal_id),
        declared_at=_copy_utc(value.declared_at),
        updated_at=_copy_utc(value.updated_at),
        generation=value.generation,
        contained_at=(
            None if value.contained_at is None else _copy_utc(value.contained_at)
        ),
        recovered_at=(
            None if value.recovered_at is None else _copy_utc(value.recovered_at)
        ),
        closed_at=None if value.closed_at is None else _copy_utc(value.closed_at),
        root_cause_recorded=value.root_cause_recorded,
    )


def _copy_timeline(value: IncidentTimelineEntry) -> IncidentTimelineEntry:
    if type(value) is not IncidentTimelineEntry:
        fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
    return IncidentTimelineEntry(
        event_id=_copy_uuid(value.event_id),
        incident_id=_copy_uuid(value.incident_id),
        generation=value.generation,
        event_type=value.event_type,
        note=IncidentTimelineNote(value.note.value),
        actor_principal_id=_copy_uuid(value.actor_principal_id),
        correlation_id=_copy_uuid(value.correlation_id),
        occurred_at=_copy_utc(value.occurred_at),
        evidence_references=_copy_evidence(value.evidence_references),
        previous_status=value.previous_status,
        new_status=value.new_status,
        source_kill_switch_event_id=_copy_optional_uuid(
            value.source_kill_switch_event_id
        ),
        source_kill_switch_id=_copy_optional_uuid(value.source_kill_switch_id),
        source_kill_switch_generation=value.source_kill_switch_generation,
    )


def _copy_contract_intent(
    value: IncidentDeclaredEventIntent | IncidentClosedEventIntent,
) -> IncidentDeclaredEventIntent | IncidentClosedEventIntent:
    if type(value) is IncidentDeclaredEventIntent:
        return IncidentDeclaredEventIntent(
            event_id=_copy_uuid(value.event_id),
            state=_copy_state(value.state),
            actor_principal_id=_copy_uuid(value.actor_principal_id),
            correlation_id=_copy_uuid(value.correlation_id),
        )
    if type(value) is IncidentClosedEventIntent:
        return IncidentClosedEventIntent(
            event_id=_copy_uuid(value.event_id),
            state=_copy_state(value.state),
            actor_principal_id=_copy_uuid(value.actor_principal_id),
            correlation_id=_copy_uuid(value.correlation_id),
        )
    fail_incident(IncidentFailureCode.STORE_FAILURE)


def _copy_result(value: IncidentMutationResult) -> IncidentMutationResult:
    if type(value) is not IncidentMutationResult:
        fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
    return IncidentMutationResult(
        state=_copy_state(value.state),
        timeline_entry=(
            None
            if value.timeline_entry is None
            else _copy_timeline(value.timeline_entry)
        ),
        contract_intent=(
            None
            if value.contract_intent is None
            else _copy_contract_intent(value.contract_intent)
        ),
    )


class RecordedIncidentAdapter:
    """Process-local CAS, idempotency, timeline, and event-intent storage.

    One lock makes each local command atomic only inside this process.  There is
    no database, durable audit transaction, notifier, outbox, publisher, or
    delivery method.
    """

    __slots__ = (
        "_capacity",
        "_consumed_kill_switch_event_ids",
        "_contract_intents",
        "_display_ids",
        "_environment",
        "_event_ids",
        "_event_namespace",
        "_idempotency",
        "_lock",
        "_states",
        "_timeline",
    )

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        event_namespace: UUID,
        capacity: int,
        states: tuple[IncidentState, ...] = (),
        timeline: tuple[IncidentTimelineEntry, ...] = (),
    ) -> None:
        self._environment = _require_local_environment(environment)
        if (
            type(event_namespace) is not UUID
            or event_namespace.int == 0
            or type(capacity) is not int
            or not 1 <= capacity <= MAX_INCIDENT_TIMELINE_ENTRIES
            or type(states) is not tuple
            or type(timeline) is not tuple
            or len(states) > capacity
            or len(timeline) > capacity
            or any(type(state) is not IncidentState for state in states)
            or any(type(entry) is not IncidentTimelineEntry for entry in timeline)
        ):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        copied_states: tuple[IncidentState, ...]
        copied_timeline: tuple[IncidentTimelineEntry, ...]
        try:
            copied_states = tuple(_copy_state(state) for state in states)
            copied_timeline = tuple(_copy_timeline(entry) for entry in timeline)
        except Exception:
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        incident_ids = tuple(state.incident_id for state in copied_states)
        display_ids = tuple(state.display_id.value for state in copied_states)
        event_ids = tuple(entry.event_id for entry in copied_timeline)
        kill_event_ids = tuple(
            entry.source_kill_switch_event_id
            for entry in copied_timeline
            if entry.source_kill_switch_event_id is not None
        )
        if (
            len(set(incident_ids)) != len(incident_ids)
            or len(set(display_ids)) != len(display_ids)
            or len(set(event_ids)) != len(event_ids)
            or len(set(kill_event_ids)) != len(kill_event_ids)
            or not set(event_ids).isdisjoint(kill_event_ids)
        ):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        states_by_id = {state.incident_id: state for state in copied_states}
        last_generation: dict[UUID, int] = {}
        last_time: dict[UUID, datetime] = {}
        projected_status: dict[UUID, IncidentStatus] = {}
        projected_contained_at: dict[UUID, datetime | None] = {}
        projected_recovered_at: dict[UUID, datetime | None] = {}
        projected_closed_at: dict[UUID, datetime | None] = {}
        projected_root_cause: dict[UUID, bool] = {}
        for entry in copied_timeline:
            state = states_by_id.get(entry.incident_id)
            expected_generation = last_generation.get(entry.incident_id, 0) + 1
            if (
                state is None
                or entry.generation > state.generation
                or entry.occurred_at < state.declared_at
                or entry.occurred_at > state.updated_at
                or entry.generation != expected_generation
            ):
                fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
            prior_time = last_time.get(entry.incident_id)
            if prior_time is not None and entry.occurred_at < prior_time:
                fail_incident(IncidentFailureCode.INVALID_ARGUMENT)

            status = projected_status.get(entry.incident_id, IncidentStatus.DECLARED)
            contained_at = projected_contained_at.get(entry.incident_id)
            recovered_at = projected_recovered_at.get(entry.incident_id)
            closed_at = projected_closed_at.get(entry.incident_id)
            root_cause_recorded = projected_root_cause.get(entry.incident_id, False)
            if entry.event_type is IncidentTimelineType.STATUS_CHANGE:
                new_status = entry.new_status
                if entry.previous_status is not status or new_status is None:
                    fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
                status = new_status
                if status is IncidentStatus.CONTAINED:
                    contained_at = entry.occurred_at
                elif status is IncidentStatus.MONITORING:
                    recovered_at = entry.occurred_at
                elif status is IncidentStatus.CLOSED:
                    closed_at = entry.occurred_at
                    root_cause_recorded = True
                elif status is IncidentStatus.REOPENED:
                    contained_at = None
                    recovered_at = None
                    closed_at = None
                    root_cause_recorded = False
            elif status is IncidentStatus.CLOSED:
                fail_incident(IncidentFailureCode.INVALID_ARGUMENT)

            last_generation[entry.incident_id] = entry.generation
            last_time[entry.incident_id] = entry.occurred_at
            projected_status[entry.incident_id] = status
            projected_contained_at[entry.incident_id] = contained_at
            projected_recovered_at[entry.incident_id] = recovered_at
            projected_closed_at[entry.incident_id] = closed_at
            projected_root_cause[entry.incident_id] = root_cause_recorded

        for state in copied_states:
            last = last_generation.get(state.incident_id, 0)
            if last == 0:
                continue
            if (
                last != state.generation
                or last_time.get(state.incident_id) != state.updated_at
                or projected_status.get(state.incident_id) is not state.status
                or projected_contained_at.get(state.incident_id) != state.contained_at
                or projected_recovered_at.get(state.incident_id) != state.recovered_at
                or projected_closed_at.get(state.incident_id) != state.closed_at
                or projected_root_cause.get(state.incident_id, False)
                is not state.root_cause_recorded
            ):
                fail_incident(IncidentFailureCode.INVALID_ARGUMENT)

        self._event_namespace = _copy_uuid(event_namespace)
        self._capacity = capacity
        self._states = states_by_id
        self._display_ids = {
            state.display_id.value: state.incident_id for state in copied_states
        }
        self._timeline = list(copied_timeline)
        self._event_ids = set(event_ids)
        self._consumed_kill_switch_event_ids = set(kill_event_ids)
        self._contract_intents: list[
            IncidentDeclaredEventIntent | IncidentClosedEventIntent
        ] = []
        self._idempotency: dict[
            str, tuple[IncidentFingerprint, IncidentMutationResult]
        ] = {}
        self._lock = Lock()

    @property
    def environment(self) -> RuntimeEnvironment:
        return self._environment

    @property
    def capacity(self) -> int:
        return self._capacity

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
        """Replay first, or apply one exact fresh command under a single lock."""

        self._guard()
        if (
            type(command)
            not in {
                DeclareIncidentCommand,
                AppendIncidentTimelineCommand,
                TransitionIncidentCommand,
                RecordKillSwitchIntentCommand,
            }
            or type(command_fingerprint) is not IncidentFingerprint
            or type(idempotency_fingerprint) is not IncidentFingerprint
            or (
                observed_state is not None and type(observed_state) is not IncidentState
            )
            or type(allow_unobserved_incident) is not bool
        ):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        try:
            command_snapshot = copy_incident_command(command)
            owned_command_fingerprint = IncidentFingerprint(command_fingerprint.value)
            owned_idempotency_fingerprint = IncidentFingerprint(
                idempotency_fingerprint.value
            )
            generation_floor = require_incident_generation(minimum_generation)
            if observed_state is not None:
                normalized_observation = _copy_state(observed_state)
            else:
                normalized_observation = None
            if normalized_observation is not None and (
                normalized_observation.incident_id != command_snapshot.incident_id
                or normalized_observation.generation > generation_floor
            ):
                fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
            recalculated = command_snapshot.fingerprint()
        except Exception:
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        if not hmac.compare_digest(recalculated.value, owned_command_fingerprint.value):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)

        with self._lock:
            idempotency_value = owned_idempotency_fingerprint.value
            prior = self._idempotency.get(idempotency_value)
            if prior is not None:
                prior_fingerprint, prior_result = prior
                if not hmac.compare_digest(
                    prior_fingerprint.value, owned_command_fingerprint.value
                ):
                    fail_incident(IncidentFailureCode.IDEMPOTENCY_CONFLICT)
                current = self._states.get(prior_result.state.incident_id)
                if current is None:
                    fail_incident(IncidentFailureCode.STATE_MISSING)
                return IncidentStoreOutcome(
                    result=_copy_result(prior_result),
                    replayed=True,
                    current_state=_copy_state(current),
                    command_fingerprint=IncidentFingerprint(prior_fingerprint.value),
                    idempotency_fingerprint=IncidentFingerprint(idempotency_value),
                )

            if not allow_unobserved_incident:
                fail_incident(IncidentFailureCode.CAPACITY_EXCEEDED)

            if len(self._idempotency) >= self._capacity:
                fail_incident(IncidentFailureCode.CAPACITY_EXCEEDED)

            if type(command_snapshot) is DeclareIncidentCommand:
                if generation_floor != 0 or normalized_observation is not None:
                    fail_incident(IncidentFailureCode.STATE_CONFLICT)
                result = self._declare(command_snapshot, owned_idempotency_fingerprint)
            else:
                result = self._mutate(
                    command=command_snapshot,
                    idempotency_fingerprint=owned_idempotency_fingerprint,
                    minimum_generation=generation_floor,
                    observed_state=normalized_observation,
                )

            stored_command_fingerprint = IncidentFingerprint(
                owned_command_fingerprint.value
            )
            self._idempotency[idempotency_value] = (
                stored_command_fingerprint,
                result,
            )
            return IncidentStoreOutcome(
                result=_copy_result(result),
                replayed=False,
                current_state=_copy_state(result.state),
                command_fingerprint=IncidentFingerprint(
                    stored_command_fingerprint.value
                ),
                idempotency_fingerprint=IncidentFingerprint(idempotency_value),
            )

    def _declare(
        self,
        command: DeclareIncidentCommand,
        idempotency_fingerprint: IncidentFingerprint,
    ) -> IncidentMutationResult:
        if (
            command.incident_id in self._states
            or command.display_id.value in self._display_ids
            or len(self._states) >= self._capacity
            or len(self._contract_intents) >= self._capacity
        ):
            fail_incident(IncidentFailureCode.STATE_CONFLICT)
        state = IncidentState(
            incident_id=command.incident_id,
            display_id=IncidentDisplayId(command.display_id.value),
            severity=command.severity,
            status=IncidentStatus.DECLARED,
            title=IncidentTitle(command.title.value),
            summary=IncidentSummary(command.summary.value),
            declared_by_principal_id=command.declared_by_principal_id,
            owner_principal_id=command.owner_principal_id,
            commander_principal_id=command.commander_principal_id,
            declared_at=command.declared_at,
            updated_at=command.declared_at,
            generation=0,
        )
        event_id = self._event_id(idempotency_fingerprint, "declared")
        if (
            event_id in self._event_ids
            or event_id in self._consumed_kill_switch_event_ids
        ):
            fail_incident(IncidentFailureCode.STATE_CONFLICT)
        intent = IncidentDeclaredEventIntent(
            event_id=event_id,
            state=state,
            actor_principal_id=command.declared_by_principal_id,
            correlation_id=command.correlation_id,
        )
        result = IncidentMutationResult(
            state=state,
            timeline_entry=None,
            contract_intent=intent,
        )
        self._states[state.incident_id] = state
        self._display_ids[state.display_id.value] = state.incident_id
        self._contract_intents.append(intent)
        self._event_ids.add(event_id)
        return result

    def _mutate(
        self,
        *,
        command: AppendIncidentTimelineCommand
        | TransitionIncidentCommand
        | RecordKillSwitchIntentCommand,
        idempotency_fingerprint: IncidentFingerprint,
        minimum_generation: int,
        observed_state: IncidentState | None,
    ) -> IncidentMutationResult:
        current = self._states.get(command.incident_id)
        if current is None:
            fail_incident(IncidentFailureCode.STATE_MISSING)
        if (
            current.generation < minimum_generation
            or command.expected_generation != current.generation
        ):
            fail_incident(IncidentFailureCode.GENERATION_CONFLICT)
        if observed_state is not None:
            if current.generation < observed_state.generation:
                fail_incident(IncidentFailureCode.GENERATION_CONFLICT)
            if current != observed_state:
                fail_incident(IncidentFailureCode.STATE_CONFLICT)
        if current.generation == MAX_INCIDENT_GENERATION:
            fail_incident(IncidentFailureCode.GENERATION_CONFLICT)
        if len(self._timeline) >= self._capacity:
            fail_incident(IncidentFailureCode.CAPACITY_EXCEEDED)

        if type(command) is AppendIncidentTimelineCommand:
            if current.status is IncidentStatus.CLOSED:
                fail_incident(IncidentFailureCode.STATE_CONFLICT)
            occurred_at = command.occurred_at
            actor_id = command.actor_principal_id
            correlation_id = command.correlation_id
            event_type = command.event_type
            note = IncidentTimelineNote(command.note.value)
            evidence = _copy_evidence(command.evidence_references)
            previous_status = None
            new_status = None
            kill_event_id = None
            kill_switch_id = None
            kill_generation = None
            replacement = replace(
                current,
                generation=current.generation + 1,
                updated_at=occurred_at,
            )
        elif type(command) is TransitionIncidentCommand:
            require_incident_transition(current.status, command.target_status)
            occurred_at = command.occurred_at
            actor_id = command.actor_principal_id
            correlation_id = command.correlation_id
            event_type = IncidentTimelineType.STATUS_CHANGE
            note = IncidentTimelineNote(command.note.value)
            evidence = _copy_evidence(command.evidence_references)
            previous_status = current.status
            new_status = command.target_status
            kill_event_id = None
            kill_switch_id = None
            kill_generation = None
            contained_at = current.contained_at
            recovered_at = current.recovered_at
            closed_at = current.closed_at
            root_cause_recorded = current.root_cause_recorded
            if command.target_status is IncidentStatus.CONTAINED:
                contained_at = occurred_at
            elif command.target_status is IncidentStatus.MONITORING:
                recovered_at = occurred_at
            elif command.target_status is IncidentStatus.CLOSED:
                closed_at = occurred_at
                root_cause_recorded = True
            elif command.target_status is IncidentStatus.REOPENED:
                contained_at = None
                recovered_at = None
                closed_at = None
                root_cause_recorded = False
            replacement = replace(
                current,
                status=command.target_status,
                updated_at=occurred_at,
                generation=current.generation + 1,
                contained_at=contained_at,
                recovered_at=recovered_at,
                closed_at=closed_at,
                root_cause_recorded=root_cause_recorded,
            )
        else:
            intent = command.intent
            if (
                current.status is IncidentStatus.CLOSED
                or intent.event_id in self._consumed_kill_switch_event_ids
                or intent.event_id in self._event_ids
            ):
                fail_incident(IncidentFailureCode.STATE_CONFLICT)
            occurred_at = intent.occurred_at
            actor_id = intent.actor_principal_id
            correlation_id = intent.correlation_id
            event_type = IncidentTimelineType.CONTAINMENT
            note = IncidentTimelineNote("KILL_SWITCH_ENGAGED")
            evidence = ()
            previous_status = None
            new_status = None
            kill_event_id = intent.event_id
            kill_switch_id = intent.switch_id
            kill_generation = intent.new_generation
            replacement = replace(
                current,
                generation=current.generation + 1,
                updated_at=occurred_at,
            )

        if occurred_at < current.updated_at:
            fail_incident(IncidentFailureCode.STATE_CONFLICT)
        event_id = self._event_id(idempotency_fingerprint, "timeline")
        if (
            event_id in self._event_ids
            or event_id in self._consumed_kill_switch_event_ids
            or event_id == kill_event_id
        ):
            fail_incident(IncidentFailureCode.STATE_CONFLICT)
        entry = IncidentTimelineEntry(
            event_id=event_id,
            incident_id=current.incident_id,
            generation=replacement.generation,
            event_type=event_type,
            note=note,
            actor_principal_id=actor_id,
            correlation_id=correlation_id,
            occurred_at=occurred_at,
            evidence_references=evidence,
            previous_status=previous_status,
            new_status=new_status,
            source_kill_switch_event_id=kill_event_id,
            source_kill_switch_id=kill_switch_id,
            source_kill_switch_generation=kill_generation,
        )
        contract_intent: IncidentClosedEventIntent | None = None
        if (
            replacement.status is IncidentStatus.CLOSED
            and type(command) is TransitionIncidentCommand
        ):
            if len(self._contract_intents) >= self._capacity:
                fail_incident(IncidentFailureCode.CAPACITY_EXCEEDED)
            contract_event_id = self._event_id(idempotency_fingerprint, "closed")
            if (
                contract_event_id in self._event_ids
                or contract_event_id in self._consumed_kill_switch_event_ids
                or contract_event_id == event_id
            ):
                fail_incident(IncidentFailureCode.STATE_CONFLICT)
            contract_intent = IncidentClosedEventIntent(
                event_id=contract_event_id,
                state=replacement,
                actor_principal_id=actor_id,
                correlation_id=correlation_id,
            )
        result = IncidentMutationResult(
            state=replacement,
            timeline_entry=entry,
            contract_intent=contract_intent,
        )
        self._states[current.incident_id] = replacement
        self._timeline.append(entry)
        self._event_ids.add(event_id)
        if kill_event_id is not None:
            self._consumed_kill_switch_event_ids.add(kill_event_id)
        if contract_intent is not None:
            self._contract_intents.append(contract_intent)
            self._event_ids.add(contract_intent.event_id)
        return result

    def current_state(self, incident_id: UUID) -> IncidentState | None:
        """Return one immutable local state for focused development checks."""

        self._guard()
        if type(incident_id) is not UUID or incident_id.int == 0:
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        with self._lock:
            state = self._states.get(incident_id)
            return None if state is None else _copy_state(state)

    def timeline(self, incident_id: UUID) -> tuple[IncidentTimelineEntry, ...]:
        """Return a copied local timeline; no durable query is claimed."""

        self._guard()
        if type(incident_id) is not UUID or incident_id.int == 0:
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        with self._lock:
            return tuple(
                _copy_timeline(entry)
                for entry in self._timeline
                if entry.incident_id == incident_id
            )

    def contract_intents(
        self,
    ) -> tuple[IncidentDeclaredEventIntent | IncidentClosedEventIntent, ...]:
        """Return in-memory intents; this method performs no delivery."""

        self._guard()
        with self._lock:
            return tuple(
                _copy_contract_intent(intent) for intent in self._contract_intents
            )

    def _event_id(
        self, idempotency_fingerprint: IncidentFingerprint, purpose: str
    ) -> UUID:
        return uuid5(
            self._event_namespace,
            f"{idempotency_fingerprint.value}:{purpose}",
        )

    def _guard(self) -> None:
        _require_local_environment(self._environment)

    def __repr__(self) -> str:
        return "RecordedIncidentAdapter(<redacted-incident-value>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded incident adapter serialization is not supported")


__all__ = ["RecordedIncidentAdapter"]

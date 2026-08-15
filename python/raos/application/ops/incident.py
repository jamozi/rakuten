"""Transport-neutral ST-1406 local incident command service."""

from __future__ import annotations

import hmac
from datetime import UTC, datetime
from threading import Lock
from typing import cast
from uuid import UUID

from raos.domain.ops.incident import (
    AppendIncidentTimelineCommand,
    DeclareIncidentCommand,
    IncidentClosedEventIntent,
    IncidentCommand,
    IncidentDeclaredEventIntent,
    IncidentDisplayId,
    IncidentEvidenceReference,
    IncidentFailure,
    IncidentFailureCode,
    IncidentFingerprint,
    IncidentIdempotencyKey,
    IncidentMutationResult,
    IncidentState,
    IncidentStatus,
    IncidentSummary,
    IncidentTimelineEntry,
    IncidentTimelineNote,
    IncidentTimelineType,
    IncidentTitle,
    MAX_INCIDENT_TIMELINE_ENTRIES,
    RecordKillSwitchIntentCommand,
    TransitionIncidentCommand,
    copy_incident_command,
    fail_incident,
    incident_status_minimum_generation,
)
from raos.ports.incident import IncidentStore, IncidentStoreOutcome


def _supports(candidate: object, protocol: type[object]) -> bool:
    try:
        return isinstance(candidate, protocol)
    except Exception:
        return False


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


def _copy_result(value: IncidentMutationResult) -> IncidentMutationResult:
    if type(value) is not IncidentMutationResult:
        fail_incident(IncidentFailureCode.STORE_FAILURE)
    state = _copy_state(value.state)
    timeline = (
        None if value.timeline_entry is None else _copy_timeline(value.timeline_entry)
    )
    contract = value.contract_intent
    copied_contract: IncidentDeclaredEventIntent | IncidentClosedEventIntent | None
    if contract is None:
        copied_contract = None
    elif type(contract) is IncidentDeclaredEventIntent:
        copied_contract = IncidentDeclaredEventIntent(
            event_id=_copy_uuid(contract.event_id),
            state=state,
            actor_principal_id=_copy_uuid(contract.actor_principal_id),
            correlation_id=_copy_uuid(contract.correlation_id),
        )
    elif type(contract) is IncidentClosedEventIntent:
        copied_contract = IncidentClosedEventIntent(
            event_id=_copy_uuid(contract.event_id),
            state=state,
            actor_principal_id=_copy_uuid(contract.actor_principal_id),
            correlation_id=_copy_uuid(contract.correlation_id),
        )
    else:
        fail_incident(IncidentFailureCode.STORE_FAILURE)
    return IncidentMutationResult(
        state=state,
        timeline_entry=timeline,
        contract_intent=copied_contract,
    )


def _normalize_outcome(value: object) -> IncidentStoreOutcome | None:
    if type(value) is not IncidentStoreOutcome:
        return None
    normalized: IncidentStoreOutcome | None = None
    try:
        normalized = IncidentStoreOutcome(
            result=_copy_result(value.result),
            replayed=value.replayed,
            current_state=_copy_state(value.current_state),
            command_fingerprint=IncidentFingerprint(value.command_fingerprint.value),
            idempotency_fingerprint=IncidentFingerprint(
                value.idempotency_fingerprint.value
            ),
        )
    except Exception:
        pass
    return normalized


def _call_inputs_unchanged(
    *,
    original_command: IncidentCommand,
    original_idempotency_key: IncidentIdempotencyKey,
    command_snapshot: IncidentCommand,
    sent_command: IncidentCommand,
    command_fingerprint: IncidentFingerprint,
    sent_command_fingerprint: IncidentFingerprint,
    idempotency_fingerprint: IncidentFingerprint,
    sent_idempotency_fingerprint: IncidentFingerprint,
    observed_state: IncidentState | None,
    sent_observed_state: IncidentState | None,
) -> bool:
    try:
        current_original = copy_incident_command(original_command)
        current_snapshot = copy_incident_command(command_snapshot)
        current_sent = copy_incident_command(sent_command)
        original_recalculated = current_original.fingerprint()
        snapshot_fingerprint = current_snapshot.fingerprint()
        sent_recalculated = current_sent.fingerprint()
        original_idempotency_fingerprint = original_idempotency_key.fingerprint()
        sent_command_fingerprint_copy = IncidentFingerprint(
            sent_command_fingerprint.value
        )
        sent_idempotency_fingerprint_copy = IncidentFingerprint(
            sent_idempotency_fingerprint.value
        )
        if observed_state is None:
            observation_matches = sent_observed_state is None
        else:
            observation_matches = (
                sent_observed_state is not None
                and _copy_state(sent_observed_state) == observed_state
            )
    except Exception:
        return False
    return (
        current_original == command_snapshot
        and current_snapshot == command_snapshot
        and current_sent == command_snapshot
        and observation_matches
        and hmac.compare_digest(
            original_recalculated.value,
            command_fingerprint.value,
        )
        and hmac.compare_digest(snapshot_fingerprint.value, command_fingerprint.value)
        and hmac.compare_digest(sent_recalculated.value, command_fingerprint.value)
        and hmac.compare_digest(
            original_idempotency_fingerprint.value,
            idempotency_fingerprint.value,
        )
        and hmac.compare_digest(
            sent_command_fingerprint_copy.value,
            command_fingerprint.value,
        )
        and hmac.compare_digest(
            sent_idempotency_fingerprint_copy.value,
            idempotency_fingerprint.value,
        )
    )


def _state_conflicts(previous: IncidentState, candidate: IncidentState) -> bool:
    if (
        candidate.incident_id != previous.incident_id
        or candidate.display_id != previous.display_id
        or candidate.severity is not previous.severity
        or candidate.title != previous.title
        or candidate.summary != previous.summary
        or candidate.declared_at != previous.declared_at
        or candidate.declared_by_principal_id != previous.declared_by_principal_id
        or candidate.owner_principal_id != previous.owner_principal_id
        or candidate.commander_principal_id != previous.commander_principal_id
        or candidate.generation < previous.generation
        or candidate.updated_at < previous.updated_at
    ):
        return True
    return candidate.generation == previous.generation and candidate != previous


def _outcome_state_chain_matches(outcome: IncidentStoreOutcome) -> bool:
    result = outcome.result.state
    current = outcome.current_state
    if (
        current.incident_id != result.incident_id
        or current.display_id != result.display_id
        or current.severity is not result.severity
        or current.title != result.title
        or current.summary != result.summary
        or current.declared_at != result.declared_at
        or current.declared_by_principal_id != result.declared_by_principal_id
        or current.owner_principal_id != result.owner_principal_id
        or current.commander_principal_id != result.commander_principal_id
        or current.generation < result.generation
        or current.updated_at < result.updated_at
        or (current.generation == result.generation and current != result)
    ):
        return False
    return outcome.replayed or current == result


def _transition_milestones_match(
    *,
    previous: IncidentState | None,
    candidate: IncidentState,
    command: TransitionIncidentCommand,
) -> bool:
    target = command.target_status
    occurred_at = command.occurred_at
    if previous is not None:
        contained_at = previous.contained_at
        recovered_at = previous.recovered_at
        closed_at = previous.closed_at
        root_cause_recorded = previous.root_cause_recorded
        if target is IncidentStatus.CONTAINED:
            contained_at = occurred_at
        elif target is IncidentStatus.MONITORING:
            recovered_at = occurred_at
        elif target is IncidentStatus.CLOSED:
            closed_at = occurred_at
            root_cause_recorded = True
        elif target is IncidentStatus.REOPENED:
            contained_at = None
            recovered_at = None
            closed_at = None
            root_cause_recorded = False
        return (
            candidate.contained_at == contained_at
            and candidate.recovered_at == recovered_at
            and candidate.closed_at == closed_at
            and candidate.root_cause_recorded is root_cause_recorded
        )

    if target is IncidentStatus.CONTAINING:
        return (
            candidate.contained_at is None
            and candidate.recovered_at is None
            and candidate.closed_at is None
            and not candidate.root_cause_recorded
        )
    if target is IncidentStatus.CONTAINED:
        return (
            candidate.contained_at == occurred_at
            and candidate.recovered_at is None
            and candidate.closed_at is None
            and not candidate.root_cause_recorded
        )
    if target is IncidentStatus.RECOVERING:
        return (
            candidate.contained_at is not None
            and candidate.recovered_at is None
            and candidate.closed_at is None
            and not candidate.root_cause_recorded
        )
    if target is IncidentStatus.MONITORING:
        return (
            candidate.contained_at is not None
            and candidate.recovered_at == occurred_at
            and candidate.closed_at is None
            and not candidate.root_cause_recorded
        )
    if target is IncidentStatus.CLOSED:
        return (
            candidate.contained_at is not None
            and candidate.recovered_at is not None
            and candidate.closed_at == occurred_at
            and candidate.root_cause_recorded
        )
    return (
        target is IncidentStatus.REOPENED
        and candidate.contained_at is None
        and candidate.recovered_at is None
        and candidate.closed_at is None
        and not candidate.root_cause_recorded
    )


def _non_status_mutation_state_matches(
    *,
    previous: IncidentState | None,
    candidate: IncidentState,
    expected_generation: int,
) -> bool:
    if (
        candidate.status is IncidentStatus.CLOSED
        or incident_status_minimum_generation(candidate.status) > expected_generation
    ):
        return False
    return previous is None or (
        candidate.status is previous.status
        and candidate.contained_at == previous.contained_at
        and candidate.recovered_at == previous.recovered_at
        and candidate.closed_at == previous.closed_at
        and candidate.root_cause_recorded is previous.root_cause_recorded
    )


class IncidentService:
    """Apply exact local incident commands through one inward store port."""

    def __init__(self, *, store: IncidentStore, capacity: int) -> None:
        if not _supports(cast(object, store), IncidentStore):
            raise TypeError("store must implement IncidentStore")
        if (
            type(capacity) is not int
            or not 1 <= capacity <= MAX_INCIDENT_TIMELINE_ENTRIES
        ):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        self._store = store
        self._capacity = capacity
        self._generation_floors: dict[UUID, int] = {}
        self._observed_states: dict[UUID, IncidentState] = {}
        self._state_lock = Lock()

    def declare(
        self,
        *,
        command: DeclareIncidentCommand,
        idempotency_key: IncidentIdempotencyKey,
    ) -> IncidentMutationResult:
        return self._execute(command=command, idempotency_key=idempotency_key)

    def append_timeline(
        self,
        *,
        command: AppendIncidentTimelineCommand,
        idempotency_key: IncidentIdempotencyKey,
    ) -> IncidentMutationResult:
        return self._execute(command=command, idempotency_key=idempotency_key)

    def transition(
        self,
        *,
        command: TransitionIncidentCommand,
        idempotency_key: IncidentIdempotencyKey,
    ) -> IncidentMutationResult:
        return self._execute(command=command, idempotency_key=idempotency_key)

    def record_kill_switch_intent(
        self,
        *,
        command: RecordKillSwitchIntentCommand,
        idempotency_key: IncidentIdempotencyKey,
    ) -> IncidentMutationResult:
        """Consume a prior engaged intent without invoking ST-1405 behavior."""

        return self._execute(command=command, idempotency_key=idempotency_key)

    def _execute(
        self,
        *,
        command: IncidentCommand,
        idempotency_key: IncidentIdempotencyKey,
    ) -> IncidentMutationResult:
        if (
            type(command)
            not in {
                DeclareIncidentCommand,
                AppendIncidentTimelineCommand,
                TransitionIncidentCommand,
                RecordKillSwitchIntentCommand,
            }
            or type(idempotency_key) is not IncidentIdempotencyKey
        ):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        try:
            command_snapshot = copy_incident_command(command)
            sent_command = copy_incident_command(command_snapshot)
            command_fingerprint = command_snapshot.fingerprint()
            sent_command_fingerprint = IncidentFingerprint(command_fingerprint.value)
            idempotency_fingerprint = idempotency_key.fingerprint()
            sent_idempotency_fingerprint = IncidentFingerprint(
                idempotency_fingerprint.value
            )
            incident_id = command_snapshot.incident_id
        except IncidentFailure:
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        except Exception:
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)

        with self._state_lock:
            prior_state = self._observed_states.get(incident_id)
            generation_floor = self._generation_floors.get(incident_id, 0)
            tracked_incident_ids = set(self._generation_floors) | set(
                self._observed_states
            )
            incident_is_known = incident_id in tracked_incident_ids
            allow_unobserved_incident = (
                incident_is_known or len(tracked_incident_ids) < self._capacity
            )
            sent_observed_state = (
                None if prior_state is None else _copy_state(prior_state)
            )
            outcome: object = None
            failure: IncidentFailureCode | None = None
            try:
                outcome = self._store.apply(
                    command=sent_command,
                    command_fingerprint=sent_command_fingerprint,
                    idempotency_fingerprint=sent_idempotency_fingerprint,
                    minimum_generation=generation_floor,
                    observed_state=sent_observed_state,
                    allow_unobserved_incident=allow_unobserved_incident,
                )
            except IncidentFailure as error:
                error_code: object = None
                try:
                    error_code = error.code
                except Exception:
                    pass
                failure = (
                    error_code
                    if type(error) is IncidentFailure
                    and type(error_code) is IncidentFailureCode
                    else IncidentFailureCode.STORE_FAILURE
                )
            except Exception:
                failure = IncidentFailureCode.STORE_FAILURE
            if not _call_inputs_unchanged(
                original_command=command,
                original_idempotency_key=idempotency_key,
                command_snapshot=command_snapshot,
                sent_command=sent_command,
                command_fingerprint=command_fingerprint,
                sent_command_fingerprint=sent_command_fingerprint,
                idempotency_fingerprint=idempotency_fingerprint,
                sent_idempotency_fingerprint=sent_idempotency_fingerprint,
                observed_state=prior_state,
                sent_observed_state=sent_observed_state,
            ):
                fail_incident(IncidentFailureCode.STORE_FAILURE)
            if failure is not None:
                fail_incident(failure)

            normalized = _normalize_outcome(outcome)
            if normalized is None or not (
                hmac.compare_digest(
                    normalized.command_fingerprint.value,
                    command_fingerprint.value,
                )
                and hmac.compare_digest(
                    normalized.idempotency_fingerprint.value,
                    idempotency_fingerprint.value,
                )
                and _outcome_state_chain_matches(normalized)
            ):
                fail_incident(IncidentFailureCode.STORE_FAILURE)
            self._validate_result(
                command=command_snapshot,
                result=normalized.result,
                previous_state=prior_state if not normalized.replayed else None,
            )

            current = normalized.current_state
            floor_conflict = current.generation < generation_floor
            observed_conflict = prior_state is not None and _state_conflicts(
                prior_state, current
            )
            fresh_not_advanced = (
                not normalized.replayed
                and type(command_snapshot) is not DeclareIncidentCommand
                and current.generation <= generation_floor
            )
            fresh_redeclaration = (
                not normalized.replayed
                and type(command_snapshot) is DeclareIncidentCommand
                and prior_state is not None
            )
            if normalized.replayed:
                if floor_conflict or observed_conflict:
                    fail_incident(IncidentFailureCode.STORE_FAILURE)
                return normalized.result
            if (
                floor_conflict
                or observed_conflict
                or fresh_not_advanced
                or fresh_redeclaration
                or not allow_unobserved_incident
            ):
                fail_incident(IncidentFailureCode.STORE_FAILURE)
            self._generation_floors[incident_id] = max(
                generation_floor, current.generation
            )
            if prior_state is None or current.generation > prior_state.generation:
                self._observed_states[incident_id] = _copy_state(current)
            return normalized.result

    @staticmethod
    def _validate_result(
        *,
        command: IncidentCommand,
        result: IncidentMutationResult,
        previous_state: IncidentState | None,
    ) -> None:
        state = result.state
        if state.incident_id != command.incident_id:
            fail_incident(IncidentFailureCode.STORE_FAILURE)
        if type(command) is DeclareIncidentCommand:
            contract = result.contract_intent
            if (
                state.display_id != command.display_id
                or state.severity is not command.severity
                or state.status is not IncidentStatus.DECLARED
                or state.title != command.title
                or state.summary != command.summary
                or state.declared_by_principal_id != command.declared_by_principal_id
                or state.owner_principal_id != command.owner_principal_id
                or state.commander_principal_id != command.commander_principal_id
                or state.declared_at != command.declared_at
                or state.updated_at != command.declared_at
                or state.generation != 0
                or result.timeline_entry is not None
                or type(contract) is not IncidentDeclaredEventIntent
                or contract.actor_principal_id != command.declared_by_principal_id
                or contract.correlation_id != command.correlation_id
            ):
                fail_incident(IncidentFailureCode.STORE_FAILURE)
            return

        if state.generation != command.expected_generation + 1:
            fail_incident(IncidentFailureCode.STORE_FAILURE)
        if previous_state is not None and (
            previous_state.generation != command.expected_generation
            or previous_state.incident_id != command.incident_id
        ):
            fail_incident(IncidentFailureCode.STORE_FAILURE)
        entry = result.timeline_entry
        if entry is None or entry.generation != state.generation:
            fail_incident(IncidentFailureCode.STORE_FAILURE)
        if type(command) is AppendIncidentTimelineCommand:
            if (
                not _non_status_mutation_state_matches(
                    previous=previous_state,
                    candidate=state,
                    expected_generation=command.expected_generation,
                )
                or entry.event_type is not command.event_type
                or entry.note != command.note
                or entry.actor_principal_id != command.actor_principal_id
                or entry.correlation_id != command.correlation_id
                or entry.occurred_at != command.occurred_at
                or entry.evidence_references != command.evidence_references
                or entry.source_kill_switch_event_id is not None
                or entry.source_kill_switch_id is not None
                or entry.source_kill_switch_generation is not None
                or result.contract_intent is not None
            ):
                fail_incident(IncidentFailureCode.STORE_FAILURE)
            return
        if type(command) is TransitionIncidentCommand:
            contract = result.contract_intent
            if (
                state.status is not command.target_status
                or not _transition_milestones_match(
                    previous=previous_state,
                    candidate=state,
                    command=command,
                )
                or (
                    previous_state is None
                    and command.expected_generation == 0
                    and (
                        command.target_status is not IncidentStatus.CONTAINING
                        or entry.previous_status is not IncidentStatus.DECLARED
                    )
                )
                or (
                    previous_state is not None
                    and entry.previous_status is not previous_state.status
                )
                or entry.previous_status is None
                or entry.new_status is not command.target_status
                or entry.note != command.note
                or entry.actor_principal_id != command.actor_principal_id
                or entry.correlation_id != command.correlation_id
                or entry.occurred_at != command.occurred_at
                or entry.evidence_references != command.evidence_references
                or (
                    command.target_status is IncidentStatus.CLOSED
                    and (
                        type(contract) is not IncidentClosedEventIntent
                        or contract.actor_principal_id != command.actor_principal_id
                        or contract.correlation_id != command.correlation_id
                    )
                )
                or (
                    command.target_status is not IncidentStatus.CLOSED
                    and contract is not None
                )
            ):
                fail_incident(IncidentFailureCode.STORE_FAILURE)
            return
        intent = command.intent
        if (
            not _non_status_mutation_state_matches(
                previous=previous_state,
                candidate=state,
                expected_generation=command.expected_generation,
            )
            or entry.event_type is not IncidentTimelineType.CONTAINMENT
            or entry.note != IncidentTimelineNote("KILL_SWITCH_ENGAGED")
            or entry.actor_principal_id != intent.actor_principal_id
            or entry.correlation_id != intent.correlation_id
            or entry.occurred_at != intent.occurred_at
            or entry.evidence_references
            or entry.previous_status is not None
            or entry.new_status is not None
            or entry.source_kill_switch_event_id != intent.event_id
            or entry.source_kill_switch_id != intent.switch_id
            or entry.source_kill_switch_generation != intent.new_generation
            or result.contract_intent is not None
        ):
            fail_incident(IncidentFailureCode.STORE_FAILURE)


__all__ = ["IncidentService"]

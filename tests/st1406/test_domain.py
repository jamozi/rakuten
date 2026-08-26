"""Domain invariants and installed-event compatibility for ST-1406."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from uuid import UUID

import pytest
from pydantic import ValidationError

from .support import (
    ACTOR_ID,
    ARTIFACT_ID,
    CORRELATION_ID,
    DECLARED_AT,
    INCIDENT_ID,
    declare_command,
    idempotency_key,
    incident_state,
    observed_at,
    service_bundle,
)
from raos.domain.ops.incident import (
    AppendIncidentTimelineCommand,
    IncidentDisplayId,
    IncidentEvidenceReference,
    IncidentFailure,
    IncidentFailureCode,
    IncidentIdempotencyKey,
    IncidentSeverity,
    IncidentState,
    IncidentStatus,
    IncidentSummary,
    IncidentTimelineEntry,
    IncidentTimelineNote,
    IncidentTimelineType,
    IncidentTitle,
    MAX_INCIDENT_GENERATION,
    TransitionIncidentCommand,
)
from raos.generated.contracts.jp_raos_ops_incident_closed_v1 import (
    Schema as ClosedSchema,
)
from raos.generated.contracts.jp_raos_ops_incident_declared_v1 import (
    Schema as DeclaredSchema,
)


def _assert_invalid(factory: object) -> None:
    assert callable(factory)
    with pytest.raises(IncidentFailure) as caught:
        factory()
    assert caught.value.code is IncidentFailureCode.INVALID_ARGUMENT
    assert caught.value.__cause__ is None


def test_closed_taxonomies_match_the_selected_provider_neutral_boundary() -> None:
    assert {value.value for value in IncidentSeverity} == {
        "SEV1",
        "SEV2",
        "SEV3",
        "SEV4",
    }
    assert {value.value for value in IncidentStatus} == {
        "DECLARED",
        "CONTAINING",
        "CONTAINED",
        "RECOVERING",
        "MONITORING",
        "CLOSED",
        "REOPENED",
    }
    assert {value.value for value in IncidentTimelineType} == {
        "NOTE",
        "STATUS_CHANGE",
        "CONTAINMENT",
        "DECISION",
        "RECOVERY",
        "EVIDENCE",
        "ACTION_ITEM",
    }
    assert all(issubclass(type(value), Enum) for value in IncidentSeverity)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: IncidentDisplayId("INC-1406 "),
        lambda: IncidentDisplayId("P0-1406"),
        lambda: IncidentTitle(" leading"),
        lambda: IncidentTitle("line\nbreak"),
        lambda: IncidentSummary("contains\x00byte"),
        lambda: IncidentTimelineNote(""),
        lambda: IncidentIdempotencyKey("short"),
        lambda: IncidentEvidenceReference(
            artifact_id=UUID(int=0), artifact_sha256="a" * 64
        ),
        lambda: IncidentEvidenceReference(
            artifact_id=ARTIFACT_ID, artifact_sha256="A" * 64
        ),
    ],
)
def test_bounded_values_fail_closed(factory: object) -> None:
    _assert_invalid(factory)


@pytest.mark.parametrize(
    ("factory", "value"),
    [
        (IncidentTitle, "safe\x7fhidden"),
        (IncidentTitle, "safe\x80hidden"),
        (IncidentSummary, "safe\x85hidden"),
        (IncidentSummary, "safe\x9bhidden"),
        (IncidentTimelineNote, "safe\x7fhidden"),
        (IncidentTimelineNote, "safe\x9fhidden"),
    ],
)
def test_incident_text_rejects_del_and_c1_controls(
    factory: Callable[[str], object], value: str
) -> None:
    _assert_invalid(lambda: factory(value))


def test_multiline_incident_text_allows_only_explicit_lf_and_tab_controls() -> None:
    value = "Synthetic line one\n\tSynthetic line two"

    assert IncidentSummary(value).value == value
    assert IncidentTimelineNote(value).value == value


def test_display_id_uses_the_existing_bounded_inc_prefix_pattern() -> None:
    assert IncidentDisplayId("INC-A").value == "INC-A"
    assert IncidentDisplayId("INC-" + "A" * 127).value == "INC-" + "A" * 127
    _assert_invalid(lambda: IncidentDisplayId("INC-" + "A" * 128))


def test_sensitive_text_and_identifiers_are_redacted_by_default() -> None:
    values = (
        IncidentDisplayId("INC-1406"),
        IncidentTitle("Sensitive synthetic title"),
        IncidentSummary("Sensitive synthetic summary"),
        IncidentTimelineNote("Sensitive synthetic note"),
        IncidentIdempotencyKey("st1406-command-secretlike"),
        IncidentEvidenceReference(
            artifact_id=ARTIFACT_ID,
            artifact_sha256="a" * 64,
        ),
    )
    for value in values:
        assert "Sensitive" not in repr(value)
        assert "st1406-command-secretlike" not in repr(value)
        assert str(ARTIFACT_ID) not in repr(value)
        assert "redacted" in repr(value)


def test_incident_state_requires_explicit_non_nil_owner_and_commander() -> None:
    assert type(incident_state()) is IncidentState
    _assert_invalid(lambda: incident_state(owner_principal_id=UUID(int=0)))
    _assert_invalid(lambda: incident_state(commander_principal_id=UUID(int=0)))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda state: replace(
            state, updated_at=DECLARED_AT - timedelta(microseconds=1)
        ),
        lambda state: replace(state, updated_at=observed_at(1)),
        lambda state: replace(state, generation=-1),
        lambda state: replace(state, generation=MAX_INCIDENT_GENERATION + 1),
        lambda state: replace(state, status=IncidentStatus.CLOSED),
        lambda state: replace(state, root_cause_recorded=True),
        lambda state: replace(state, declared_at=datetime(2026, 8, 16)),
        lambda state: replace(
            state,
            declared_at=DECLARED_AT.astimezone(timezone(timedelta(hours=9))),
        ),
    ],
)
def test_state_rejects_invalid_time_generation_and_lifecycle_shapes(
    mutation: Callable[[IncidentState], IncidentState],
) -> None:
    state = incident_state()
    _assert_invalid(lambda: mutation(state))


@pytest.mark.parametrize(
    "factory",
    [
        lambda: replace(
            incident_state(),
            status=IncidentStatus.CONTAINING,
            generation=0,
        ),
        lambda: replace(
            incident_state(),
            status=IncidentStatus.CONTAINED,
            generation=1,
            updated_at=observed_at(1),
            contained_at=observed_at(1),
        ),
        lambda: replace(
            incident_state(),
            status=IncidentStatus.RECOVERING,
            generation=2,
            updated_at=observed_at(2),
            contained_at=observed_at(1),
        ),
        lambda: replace(
            incident_state(),
            status=IncidentStatus.MONITORING,
            generation=3,
            updated_at=observed_at(3),
            contained_at=observed_at(1),
            recovered_at=observed_at(2),
        ),
        lambda: replace(
            incident_state(),
            status=IncidentStatus.CLOSED,
            generation=4,
            updated_at=observed_at(4),
            contained_at=observed_at(1),
            recovered_at=observed_at(2),
            closed_at=observed_at(4),
            root_cause_recorded=True,
        ),
        lambda: replace(
            incident_state(),
            status=IncidentStatus.REOPENED,
            generation=5,
            updated_at=observed_at(5),
        ),
    ],
)
def test_statuses_require_their_minimum_reachable_generation(
    factory: Callable[[], object],
) -> None:
    _assert_invalid(factory)


@pytest.mark.parametrize(
    ("previous", "target", "generation"),
    [
        (IncidentStatus.CONTAINING, IncidentStatus.CONTAINED, 1),
        (IncidentStatus.CONTAINED, IncidentStatus.RECOVERING, 2),
        (IncidentStatus.RECOVERING, IncidentStatus.MONITORING, 3),
        (IncidentStatus.MONITORING, IncidentStatus.CLOSED, 4),
        (IncidentStatus.CLOSED, IncidentStatus.REOPENED, 5),
        (IncidentStatus.REOPENED, IncidentStatus.CONTAINING, 6),
    ],
)
def test_status_change_timeline_rejects_unreachable_generation(
    previous: IncidentStatus,
    target: IncidentStatus,
    generation: int,
) -> None:
    _assert_invalid(
        lambda: IncidentTimelineEntry(
            event_id=UUID(f"80000000-0000-4000-8000-{generation + 10:012d}"),
            incident_id=INCIDENT_ID,
            generation=generation,
            event_type=IncidentTimelineType.STATUS_CHANGE,
            note=IncidentTimelineNote("Unreachable status generation"),
            actor_principal_id=ACTOR_ID,
            correlation_id=CORRELATION_ID,
            occurred_at=observed_at(generation),
            evidence_references=(),
            previous_status=previous,
            new_status=target,
        )
    )


def test_status_change_timeline_requires_one_exact_canonical_transition() -> None:
    valid = IncidentTimelineEntry(
        event_id=UUID("80000000-0000-4000-8000-000000000001"),
        incident_id=INCIDENT_ID,
        generation=1,
        event_type=IncidentTimelineType.STATUS_CHANGE,
        note=IncidentTimelineNote("Containment started"),
        actor_principal_id=ACTOR_ID,
        correlation_id=CORRELATION_ID,
        occurred_at=observed_at(1),
        evidence_references=(),
        previous_status=IncidentStatus.DECLARED,
        new_status=IncidentStatus.CONTAINING,
    )
    assert valid.new_status is IncidentStatus.CONTAINING
    with pytest.raises(IncidentFailure) as caught:
        IncidentTimelineEntry(
            event_id=UUID("80000000-0000-4000-8000-000000000001"),
            incident_id=INCIDENT_ID,
            generation=1,
            event_type=IncidentTimelineType.STATUS_CHANGE,
            note=IncidentTimelineNote("Containment started"),
            actor_principal_id=ACTOR_ID,
            correlation_id=CORRELATION_ID,
            occurred_at=observed_at(1),
            evidence_references=(),
            previous_status=IncidentStatus.DECLARED,
            new_status=IncidentStatus.CLOSED,
        )
    assert caught.value.code is IncidentFailureCode.STATE_CONFLICT

    _assert_invalid(
        lambda: IncidentTimelineEntry(
            event_id=UUID("80000000-0000-4000-8000-000000000002"),
            incident_id=INCIDENT_ID,
            generation=0,
            event_type=IncidentTimelineType.NOTE,
            note=IncidentTimelineNote("Generation zero is declaration-only"),
            actor_principal_id=ACTOR_ID,
            correlation_id=CORRELATION_ID,
            occurred_at=DECLARED_AT,
            evidence_references=(),
        )
    )


def test_timeline_event_id_cannot_equal_its_source_kill_switch_event_id() -> None:
    event_id = UUID("80000000-0000-4000-8000-000000000003")
    _assert_invalid(
        lambda: IncidentTimelineEntry(
            event_id=event_id,
            incident_id=INCIDENT_ID,
            generation=1,
            event_type=IncidentTimelineType.CONTAINMENT,
            note=IncidentTimelineNote("Synthetic kill-switch reference"),
            actor_principal_id=ACTOR_ID,
            correlation_id=CORRELATION_ID,
            occurred_at=observed_at(1),
            evidence_references=(),
            source_kill_switch_event_id=event_id,
            source_kill_switch_id=UUID("60000000-0000-4000-8000-000000000099"),
            source_kill_switch_generation=1,
        )
    )


def test_closed_status_timeline_requires_an_evidence_reference() -> None:
    _assert_invalid(
        lambda: IncidentTimelineEntry(
            event_id=UUID("80000000-0000-4000-8000-000000000004"),
            incident_id=INCIDENT_ID,
            generation=5,
            event_type=IncidentTimelineType.STATUS_CHANGE,
            note=IncidentTimelineNote("Closure without evidence"),
            actor_principal_id=ACTOR_ID,
            correlation_id=CORRELATION_ID,
            occurred_at=observed_at(5),
            evidence_references=(),
            previous_status=IncidentStatus.MONITORING,
            new_status=IncidentStatus.CLOSED,
        )
    )


def test_evidence_timeline_and_closure_require_bounded_references() -> None:
    reference = IncidentEvidenceReference(
        artifact_id=ARTIFACT_ID,
        artifact_sha256="a" * 64,
    )
    valid = AppendIncidentTimelineCommand(
        incident_id=INCIDENT_ID,
        expected_generation=0,
        event_type=IncidentTimelineType.EVIDENCE,
        note=IncidentTimelineNote("Synthetic artifact retained"),
        actor_principal_id=ACTOR_ID,
        correlation_id=CORRELATION_ID,
        occurred_at=observed_at(1),
        evidence_references=(reference,),
    )
    assert valid.evidence_references == (reference,)
    _assert_invalid(
        lambda: AppendIncidentTimelineCommand(
            incident_id=INCIDENT_ID,
            expected_generation=0,
            event_type=IncidentTimelineType.EVIDENCE,
            note=IncidentTimelineNote("Missing artifact reference"),
            actor_principal_id=ACTOR_ID,
            correlation_id=CORRELATION_ID,
            occurred_at=observed_at(1),
        )
    )
    _assert_invalid(
        lambda: AppendIncidentTimelineCommand(
            incident_id=INCIDENT_ID,
            expected_generation=0,
            event_type=IncidentTimelineType.NOTE,
            note=IncidentTimelineNote("Duplicate reference"),
            actor_principal_id=ACTOR_ID,
            correlation_id=CORRELATION_ID,
            occurred_at=observed_at(1),
            evidence_references=(reference, reference),
        )
    )
    _assert_invalid(
        lambda: TransitionIncidentCommand(
            incident_id=INCIDENT_ID,
            expected_generation=4,
            target_status=IncidentStatus.CLOSED,
            note=IncidentTimelineNote("Closure without evidence"),
            actor_principal_id=ACTOR_ID,
            correlation_id=CORRELATION_ID,
            occurred_at=observed_at(5),
            evidence_references=(),
            root_cause_recorded=True,
        )
    )


def test_declaration_and_closure_intents_validate_with_installed_v1_models() -> None:
    service, adapter = service_bundle(capacity=20)
    declared = service.declare(
        command=declare_command(),
        idempotency_key=idempotency_key(),
    )
    declared_intent = declared.contract_intent
    assert declared_intent is not None
    validated_declared = DeclaredSchema.model_validate(
        declared_intent.contract_envelope()
    )
    assert validated_declared.data is not None
    assert validated_declared.data.severity == "SEV1"
    assert validated_declared.data.incident_id == INCIDENT_ID

    current = declared
    transitions = (
        IncidentStatus.CONTAINING,
        IncidentStatus.CONTAINED,
        IncidentStatus.RECOVERING,
        IncidentStatus.MONITORING,
    )
    for index, status in enumerate(transitions, start=1):
        current = service.transition(
            command=TransitionIncidentCommand(
                incident_id=INCIDENT_ID,
                expected_generation=current.state.generation,
                target_status=status,
                note=IncidentTimelineNote(f"Synthetic transition {index}"),
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
            note=IncidentTimelineNote("Synthetic verification and cause recorded"),
            actor_principal_id=ACTOR_ID,
            correlation_id=CORRELATION_ID,
            occurred_at=observed_at(5),
            evidence_references=(evidence,),
            root_cause_recorded=True,
        ),
        idempotency_key=idempotency_key("st1406-command-0006"),
    )
    closed_intent = closed.contract_intent
    assert closed_intent is not None
    validated_closed = ClosedSchema.model_validate(closed_intent.contract_envelope())
    assert validated_closed.data is not None
    assert validated_closed.data.incident_id == INCIDENT_ID
    assert validated_closed.data.root_cause_recorded is True
    assert len(adapter.contract_intents()) == 2

    timeline_entry = closed.timeline_entry
    assert timeline_entry is not None
    colliding_intent = replace(closed_intent, event_id=timeline_entry.event_id)
    _assert_invalid(lambda: replace(closed, contract_intent=colliding_intent))


def test_generated_event_models_reject_unknown_contract_fields() -> None:
    service, _ = service_bundle()
    result = service.declare(
        command=declare_command(), idempotency_key=idempotency_key()
    )
    intent = result.contract_intent
    assert intent is not None
    envelope = intent.contract_envelope()
    envelope["unexpected"] = "not accepted"
    with pytest.raises(ValidationError):
        DeclaredSchema.model_validate(envelope)

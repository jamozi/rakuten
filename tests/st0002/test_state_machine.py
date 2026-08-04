"""Canonical Job state-machine tests for ST-0002."""

from __future__ import annotations

from itertools import product
from pathlib import Path
from typing import Any

import pytest
import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
STATE_CONTRACT = REPOSITORY_ROOT / "changes" / "st-0002" / "job-state.v1.yaml"

CANONICAL_STATES = (
    "REQUESTED",
    "QUEUED",
    "RUNNING",
    "SUCCEEDED",
    "FAILED_RETRYABLE",
    "RETRY_SCHEDULED",
    "FAILED_TERMINAL",
    "QUARANTINED",
    "CANCELLED",
    "EXPIRED",
)
ALLOWED_TRANSITIONS = frozenset(
    {
        ("REQUESTED", "QUEUED"),
        ("REQUESTED", "CANCELLED"),
        ("REQUESTED", "EXPIRED"),
        ("QUEUED", "RUNNING"),
        ("QUEUED", "CANCELLED"),
        ("QUEUED", "EXPIRED"),
        ("RUNNING", "SUCCEEDED"),
        ("RUNNING", "FAILED_RETRYABLE"),
        ("RUNNING", "FAILED_TERMINAL"),
        ("RUNNING", "QUARANTINED"),
        ("RUNNING", "CANCELLED"),
        ("RUNNING", "EXPIRED"),
        ("FAILED_RETRYABLE", "RETRY_SCHEDULED"),
        ("FAILED_RETRYABLE", "FAILED_TERMINAL"),
        ("RETRY_SCHEDULED", "QUEUED"),
        ("QUARANTINED", "QUEUED"),
    }
)
LEGACY_MAPPING = {
    "PENDING": "REQUESTED",
    "READY": "QUEUED",
    "FAILED": "FAILED_TERMINAL",
    "RUNNING": "RUNNING",
    "SUCCEEDED": "SUCCEEDED",
    "QUARANTINED": "QUARANTINED",
    "CANCELLED": "CANCELLED",
}
EXPECTED_MODEL_SETS = {
    "completed_at_required": (
        "SUCCEEDED",
        "FAILED_TERMINAL",
        "QUARANTINED",
        "CANCELLED",
        "EXPIRED",
    ),
    "absorbing": (
        "SUCCEEDED",
        "FAILED_TERMINAL",
        "CANCELLED",
        "EXPIRED",
    ),
    "deadline_index_states": (
        "REQUESTED",
        "QUEUED",
        "RUNNING",
        "FAILED_RETRYABLE",
        "RETRY_SCHEDULED",
    ),
    "cancellable": ("REQUESTED", "QUEUED", "RUNNING"),
}
EXPECTED_TRANSITION_GUARDS = {
    ("QUEUED", "RUNNING"): ("lease_required",),
    ("RUNNING", "SUCCEEDED"): (
        "completed_at_required",
        "inbox_receipt_required",
    ),
    ("RUNNING", "FAILED_RETRYABLE"): ("prior_attempt_immutable",),
    ("RUNNING", "FAILED_TERMINAL"): ("completed_at_required",),
    ("RUNNING", "QUARANTINED"): ("completed_at_required",),
    ("RUNNING", "CANCELLED"): ("completed_at_required",),
    ("RUNNING", "EXPIRED"): ("completed_at_required",),
    ("FAILED_RETRYABLE", "RETRY_SCHEDULED"): ("prior_attempt_immutable",),
    ("FAILED_RETRYABLE", "FAILED_TERMINAL"): ("completed_at_required",),
    ("QUARANTINED", "QUEUED"): ("operator_release_required",),
}
ALL_STATE_PAIRS: tuple[tuple[str, str], ...] = tuple(
    (source, target) for source, target in product(CANONICAL_STATES, repeat=2)
)


def load_state_contract() -> dict[str, Any]:
    document = yaml.safe_load(STATE_CONTRACT.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def source_transitions(
    state_contract: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    transitions: dict[tuple[str, str], dict[str, Any]] = {}
    for transition in state_contract["transitions"]:
        pair = (transition["from"], transition["to"])
        assert pair not in transitions, f"duplicate transition: {pair}"
        transitions[pair] = transition
    return transitions


def test_state_model_is_the_canonical_ten_state_model() -> None:
    contract = load_state_contract()
    model = contract["state_model"]

    assert contract["document"]["story_id"] == "ST-0002"
    assert contract["document"]["decision_ids"] == ["INT-DEC-003"]
    assert model["initial"] == "REQUESTED"
    assert tuple(model["states"]) == CANONICAL_STATES
    assert len(set(model["states"])) == 10
    for field, expected in EXPECTED_MODEL_SETS.items():
        assert tuple(model[field]) == expected
        assert set(model[field]) <= set(CANONICAL_STATES)


def test_legacy_states_have_an_explicit_lossless_mapping() -> None:
    contract = load_state_contract()

    assert contract["legacy_mapping"] == LEGACY_MAPPING
    assert set(contract["legacy_mapping"].values()) <= set(CANONICAL_STATES)
    assert set(contract["legacy_mapping"]) == {
        "PENDING",
        "READY",
        "FAILED",
        "RUNNING",
        "SUCCEEDED",
        "QUARANTINED",
        "CANCELLED",
    }


def test_transition_catalog_contains_exactly_sixteen_unique_edges() -> None:
    transitions = source_transitions(load_state_contract())

    assert set(transitions) == ALLOWED_TRANSITIONS
    assert len(transitions) == 16
    assert all(source != target for source, target in transitions)
    assert all(
        source in CANONICAL_STATES and target in CANONICAL_STATES
        for source, target in transitions
    )
    assert all(
        isinstance(transition["reason"], str) and transition["reason"].strip()
        for transition in transitions.values()
    )


def test_all_one_hundred_state_pairs_are_classified() -> None:
    rejected = set(ALL_STATE_PAIRS) - ALLOWED_TRANSITIONS

    assert len(ALL_STATE_PAIRS) == 100
    assert len(ALLOWED_TRANSITIONS) == 16
    assert len(rejected) == 84
    assert not (ALLOWED_TRANSITIONS & rejected)
    assert ALLOWED_TRANSITIONS | rejected == set(ALL_STATE_PAIRS)


@pytest.mark.parametrize(
    ("source", "target"),
    ALL_STATE_PAIRS,
    ids=lambda state: state.lower(),
)
def test_each_state_pair_has_the_canonical_transition_verdict(
    source: str,
    target: str,
) -> None:
    actual_edges = set(source_transitions(load_state_contract()))
    expected_allowed = (source, target) in ALLOWED_TRANSITIONS

    assert ((source, target) in actual_edges) is expected_allowed


def test_transition_guards_match_the_approved_runtime_preconditions() -> None:
    transitions = source_transitions(load_state_contract())
    actual = {
        pair: tuple(transition.get("guards", ()))
        for pair, transition in transitions.items()
        if transition.get("guards")
    }

    assert actual == EXPECTED_TRANSITION_GUARDS


def test_absorbing_states_have_no_outgoing_transition() -> None:
    model = load_state_contract()["state_model"]
    outgoing_sources = {source for source, _ in ALLOWED_TRANSITIONS}

    assert set(model["absorbing"]).isdisjoint(outgoing_sources)
    assert "QUARANTINED" not in model["absorbing"]
    assert ("QUARANTINED", "QUEUED") in ALLOWED_TRANSITIONS


def test_deferred_semantics_are_explicit_and_owned() -> None:
    contract = load_state_contract()
    deferred = {
        item["id"]: item["owner_story"]
        for item in contract["deferred_runtime_semantics"]
    }

    assert deferred == {
        "QUARANTINE_RELEASE_TIMESTAMPS": "ST-1404",
        "RETRY_STATE_EXPIRY": "ST-1404",
    }

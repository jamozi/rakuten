from __future__ import annotations

from collections.abc import Callable
import json

import pytest

from raos.adapters.publishing.recorded_partial_auto_publication import (
    RecordedPartialAutoPublicationSource,
    parse_recorded_partial_auto_publication,
)
from raos.domain.publishing.partial_auto_publication import (
    PartialAutoPublicationFailure,
    PartialAutoPublicationFailureCode,
    PartialAutoPublicationOutcome,
    evaluate_partial_auto_publication,
)
from tests.st1903.support import command_for, mutate_fixture


def _candidate(document: dict[str, object]) -> dict[str, object]:
    value = document["candidate"]
    assert type(value) is dict
    return value


def _dependency(document: dict[str, object]) -> dict[str, object]:
    value = document["dependency"]
    assert type(value) is dict
    return value


def _gates(document: dict[str, object]) -> dict[str, object]:
    value = document["gates"]
    assert type(value) is dict
    return value


def test_exact_fixture_parses(fixture_bytes: bytes) -> None:
    command = command_for(fixture_bytes)
    bundle = parse_recorded_partial_auto_publication(fixture_bytes, command)
    assert bundle.source_sha256 == command.source_sha256
    assert bundle.command_sha256 == command.canonical_sha256


def test_source_is_one_shot(fixture_bytes: bytes) -> None:
    command = command_for(fixture_bytes)
    source = RecordedPartialAutoPublicationSource(fixture_bytes)
    source.read(command)
    with pytest.raises(PartialAutoPublicationFailure) as caught:
        source.read(command)
    assert caught.value.code is PartialAutoPublicationFailureCode.SOURCE_EXHAUSTED


@pytest.mark.parametrize(
    "operation",
    (
        lambda document: document.update({"unknown": True}),
        lambda document: _dependency(document).update({"overall": "PASS"}),
        lambda document: _dependency(document).update({"authorized": True}),
        lambda document: _dependency(document).update(
            {"human_decision_required": False}
        ),
        lambda document: _gates(document).update({"formal_tst032": "PASS"}),
        lambda document: _gates(document).update(
            {"separate_human_release_decision": "PRESENT"}
        ),
        lambda document: _gates(document).update({"kill_switch_state": "INACTIVE"}),
        lambda document: _gates(document).update({"actual_public_write": True}),
        lambda document: _candidate(document).update({"synthetic": False}),
        lambda document: _candidate(document).update({"change_count": 2}),
        lambda document: _candidate(document).update({"change_class": "CLAIM_EDIT"}),
    ),
)
def test_authority_dependency_or_shape_promotion_is_rejected(
    fixture_bytes: bytes,
    operation: Callable[[dict[str, object]], None],
) -> None:
    mutated = mutate_fixture(fixture_bytes, operation, rebind_candidate=True)
    with pytest.raises(PartialAutoPublicationFailure):
        parse_recorded_partial_auto_publication(mutated, command_for(mutated))


def test_ambiguous_candidate_is_parsed_only_to_refusal(fixture_bytes: bytes) -> None:
    mutated = mutate_fixture(
        fixture_bytes,
        lambda document: _candidate(document).update({"risk_ambiguous": True}),
        rebind_candidate=True,
    )
    bundle = parse_recorded_partial_auto_publication(mutated, command_for(mutated))
    report = evaluate_partial_auto_publication(bundle)
    assert (
        report.outcome is PartialAutoPublicationOutcome.REFUSED_AMBIGUOUS_OR_HIGH_RISK
    )


def test_duplicate_key_noncanonical_and_float_are_rejected(
    fixture_bytes: bytes,
) -> None:
    duplicate = fixture_bytes.replace(
        b'{"candidate":', b'{"candidate":null,"candidate":', 1
    )
    noncanonical = json.dumps(json.loads(fixture_bytes), indent=2).encode() + b"\n"
    floating = fixture_bytes.replace(b'"change_count":1', b'"change_count":1.0')
    for payload in (duplicate, noncanonical, floating):
        with pytest.raises(PartialAutoPublicationFailure):
            parse_recorded_partial_auto_publication(payload, command_for(payload))


def test_wrong_caller_bytes_are_rejected(fixture_bytes: bytes) -> None:
    command = command_for(fixture_bytes)
    with pytest.raises(PartialAutoPublicationFailure) as caught:
        parse_recorded_partial_auto_publication(fixture_bytes + b" ", command)
    assert caught.value.code is PartialAutoPublicationFailureCode.SOURCE_BYTES_MISMATCH

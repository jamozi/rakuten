from __future__ import annotations

from dataclasses import replace
import pickle
from typing import cast

import pytest

from raos.adapters.publishing.recorded_partial_auto_publication import (
    parse_recorded_partial_auto_publication,
)
from raos.domain.publishing.partial_auto_publication import (
    DEFAULT_PARTIAL_AUTO_PUBLICATION_SCOPE,
    PartialAutoPublicationCommand,
    PartialAutoPublicationFailure,
    PartialAutoPublicationFailureCode,
    PartialAutoPublicationOutcome,
    PartialAutoPublicationScope,
    evaluate_partial_auto_publication,
)
from tests.st1903.support import candidate_with, command_for


def test_default_scope_is_exactly_disabled() -> None:
    assert (
        DEFAULT_PARTIAL_AUTO_PUBLICATION_SCOPE is PartialAutoPublicationScope.DISABLED
    )
    assert {scope.value for scope in PartialAutoPublicationScope} == {
        "DISABLED",
        "RECORDED_SYNTHETIC_ELIGIBILITY_EVALUATION_ONLY",
    }


def test_recorded_dependency_is_refused(
    fixture_bytes: bytes,
) -> None:
    command = command_for(fixture_bytes)
    bundle = parse_recorded_partial_auto_publication(fixture_bytes, command)
    report = evaluate_partial_auto_publication(bundle)
    assert report.outcome is PartialAutoPublicationOutcome.REFUSED_DEPENDENCY_BLOCKED
    payload = report.payload()
    assert payload["positive_publication_outcome_exists"] is False
    assert (
        payload["actions"] == payload["effects"] == payload["mutations_applied"] == []
    )
    authority = cast(dict[str, object], payload["authority"])
    assert all(value is False for value in authority.values())


@pytest.mark.parametrize(
    "override",
    (
        {"risk_ambiguous": True},
        {"high_risk": True},
        {"content_addition": True},
        {"claim_change": True},
        {"recommendation_order_change": True},
        {"product_identity_change": True},
        {"affiliate_destination_change": True},
        {"raw_html_present": True},
        {"price_or_stock_assertion_added": True},
        {"personal_data_present": True},
        {"finance_input_present": True},
        {"public_write_requested": True},
    ),
)
def test_every_ambiguity_or_expansion_is_refused(
    fixture_bytes: bytes,
    override: dict[str, object],
) -> None:
    command = command_for(fixture_bytes)
    bundle = parse_recorded_partial_auto_publication(fixture_bytes, command)
    report = evaluate_partial_auto_publication(
        replace(bundle, candidate=candidate_with(**override))
    )
    assert (
        report.outcome is PartialAutoPublicationOutcome.REFUSED_AMBIGUOUS_OR_HIGH_RISK
    )
    authority = cast(dict[str, object], report.payload()["authority"])
    assert authority["publication"] is False


def test_release_decision_input_is_structurally_rejected(
    fixture_bytes: bytes,
) -> None:
    with pytest.raises(PartialAutoPublicationFailure) as caught:
        PartialAutoPublicationCommand(
            recording_id="st1903_recorded_evaluation_v1",
            source_sha256="0" * 64,
            source_bytes=len(fixture_bytes),
            release_decision_sha256="1" * 64,
        )
    assert (
        caught.value.code
        is PartialAutoPublicationFailureCode.RELEASE_DECISION_INPUT_PROHIBITED
    )


def test_values_and_failures_are_redacted_and_not_pickleable(
    fixture_bytes: bytes,
) -> None:
    command = command_for(fixture_bytes)
    assert str(command) == "<redacted-partial-auto-publication>"
    assert command.source_sha256 not in repr(command)
    with pytest.raises(TypeError):
        pickle.dumps(command)
    failure = PartialAutoPublicationFailure(
        PartialAutoPublicationFailureCode.SOURCE_DOCUMENT_INVALID
    )
    with pytest.raises(TypeError):
        pickle.dumps(failure)

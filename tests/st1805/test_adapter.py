from __future__ import annotations

from collections.abc import Callable

import pytest

from raos.adapters.recorded_scale_decision import (
    RecordedPortfolioDecisionAdapter,
    parse_recorded_portfolio_decision_fixture,
)
from raos.domain.portfolio.scale_decision import (
    PortfolioDecisionCommand,
    PortfolioDecisionFailure,
    PortfolioDecisionFailureCode,
)


def _evidence(document: dict[str, object]) -> dict[str, object]:
    value = document["evidence"]
    assert isinstance(value, dict)
    return value


def test_adapter_parses_exact_fixture(
    fixture_bytes: bytes,
    command_factory: Callable[..., PortfolioDecisionCommand],
) -> None:
    command = command_factory(fixture_bytes)
    evidence = parse_recorded_portfolio_decision_fixture(fixture_bytes, command)
    assert evidence.recording_id == command.recording_id
    assert evidence.source_pack_digest == command.expected_source_pack_digest


def test_adapter_is_one_shot(
    fixture_bytes: bytes,
    command_factory: Callable[..., PortfolioDecisionCommand],
) -> None:
    command = command_factory(fixture_bytes)
    adapter = RecordedPortfolioDecisionAdapter(fixture_bytes)
    adapter.read(command)
    with pytest.raises(PortfolioDecisionFailure) as caught:
        adapter.read(command)
    assert caught.value.code is PortfolioDecisionFailureCode.RECORDED_EXCHANGE_EXHAUSTED


@pytest.mark.parametrize(
    "mutation",
    [
        lambda document: document.update({"unknown": True}),
        lambda document: document.update({"synthetic": False}),
        lambda document: document.update({"actual_observation": True}),
        lambda document: document.update({"immutable": False}),
        lambda document: document.update({"recorded_at": "2026-04-01T00:00:01Z"}),
        lambda document: _evidence(document).update({"human_decision_present": True}),
        lambda document: _evidence(document).update({"dependency_overall": "PASS"}),
        lambda document: _evidence(document).update(
            {"dependency_gate_pass_claim": True}
        ),
        lambda document: _evidence(document).update(
            {"dependency_scale_authority": "AUTOMATION"}
        ),
        lambda document: _evidence(document).update({"quality_state": "AVAILABLE"}),
        lambda document: _evidence(document).update({"economics_state": "AVAILABLE"}),
        lambda document: _evidence(document).update({"risk_state": "AVAILABLE"}),
        lambda document: _evidence(document).update(
            {"formal_tst032_state": "AVAILABLE"}
        ),
    ],
)
def test_authority_or_evidence_promotion_is_rejected(
    fixture_bytes: bytes,
    mutate_fixture,
    command_factory: Callable[..., PortfolioDecisionCommand],
    mutation,
) -> None:
    mutated = mutate_fixture(fixture_bytes, mutation)
    with pytest.raises(PortfolioDecisionFailure) as caught:
        parse_recorded_portfolio_decision_fixture(
            mutated,
            command_factory(mutated),
        )
    assert caught.value.code is PortfolioDecisionFailureCode.FIXTURE_DOCUMENT_INVALID


def test_wrong_expected_source_pack_is_rejected(
    fixture_bytes: bytes,
    command_factory: Callable[..., PortfolioDecisionCommand],
) -> None:
    with pytest.raises(PortfolioDecisionFailure) as caught:
        parse_recorded_portfolio_decision_fixture(
            fixture_bytes,
            command_factory(fixture_bytes, source_pack_sha256="0" * 64),
        )
    assert caught.value.code is PortfolioDecisionFailureCode.FIXTURE_DOCUMENT_INVALID


def test_wrong_fixture_digest_is_rejected(
    fixture_bytes: bytes,
    command_factory: Callable[..., PortfolioDecisionCommand],
) -> None:
    command = command_factory(fixture_bytes)
    with pytest.raises(PortfolioDecisionFailure) as caught:
        parse_recorded_portfolio_decision_fixture(fixture_bytes + b" ", command)
    assert caught.value.code is PortfolioDecisionFailureCode.FIXTURE_BYTES_MISMATCH


def test_duplicate_json_key_is_rejected(
    fixture_bytes: bytes,
    command_factory: Callable[..., PortfolioDecisionCommand],
) -> None:
    mutated = fixture_bytes.replace(
        b'{\n  "actual_observation": false,',
        b'{\n  "actual_observation": false,\n  "actual_observation": false,',
        1,
    )
    with pytest.raises(PortfolioDecisionFailure):
        parse_recorded_portfolio_decision_fixture(mutated, command_factory(mutated))


def test_prohibited_key_is_rejected(
    fixture_bytes: bytes,
    mutate_fixture,
    command_factory: Callable[..., PortfolioDecisionCommand],
) -> None:
    mutated = mutate_fixture(
        fixture_bytes,
        lambda document: _evidence(document).update({"secret": "forbidden"}),
    )
    with pytest.raises(PortfolioDecisionFailure):
        parse_recorded_portfolio_decision_fixture(mutated, command_factory(mutated))

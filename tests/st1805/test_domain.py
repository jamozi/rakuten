from __future__ import annotations

import pickle

import pytest

from raos.adapters.recorded_scale_decision import RecordedPortfolioDecisionAdapter
from raos.application.portfolio.scale_decision import RecordedPortfolioDecisionJob
from raos.domain.portfolio.scale_decision import (
    DecisionOutcome,
    DecisionOverall,
    EvidenceState,
    PortfolioDecisionCommand,
    PortfolioDecisionFailure,
    PortfolioDecisionFailureCode,
    Sha256Digest,
    build_portfolio_decision_report,
)


def test_report_is_blocked_no_decision(
    fixture_bytes: bytes,
    command_factory,
) -> None:
    command = command_factory(fixture_bytes)
    report = RecordedPortfolioDecisionJob(
        exchange=RecordedPortfolioDecisionAdapter(fixture_bytes)
    ).evaluate(command)
    assert report.overall is DecisionOverall.BLOCKED
    assert report.outcome is DecisionOutcome.NO_DECISION
    payload = report.payload()
    assert payload["decision"] == {
        "authorized": False,
        "category_limit_change": None,
        "human_decision_required": True,
        "mutations_applied": [],
        "outcome": "NO_DECISION",
        "scale_limit_change": None,
    }


def test_quality_economics_risk_and_formal_pack_are_unavailable(
    fixture_bytes: bytes,
    command_factory,
) -> None:
    report = RecordedPortfolioDecisionJob(
        exchange=RecordedPortfolioDecisionAdapter(fixture_bytes)
    ).evaluate(command_factory(fixture_bytes))
    evidence = report.payload()["evidence"]
    assert isinstance(evidence, dict)
    assert set(evidence) == {"economics", "formal_tst032", "quality", "risk"}
    assert all(row["availability"] == "UNAVAILABLE" for row in evidence.values())
    assert evidence["economics"]["source_state"] == (
        EvidenceState.RECORDED_SYNTHETIC_NON_ATTESTING.value
    )


def test_all_criteria_are_ineligible(
    fixture_bytes: bytes,
    command_factory,
) -> None:
    report = RecordedPortfolioDecisionJob(
        exchange=RecordedPortfolioDecisionAdapter(fixture_bytes)
    ).evaluate(command_factory(fixture_bytes))
    criteria = report.payload()["criteria"]
    assert isinstance(criteria, list)
    assert len(criteria) == 5
    assert {row["evidence_class"] for row in criteria} == {
        "ECONOMICS",
        "FORMAL_GATE_PACK",
        "HUMAN_AUTHORITY",
        "QUALITY",
        "RISK",
    }
    assert all(row["status"] == "NOT_ELIGIBLE" for row in criteria)


def test_finance_cannot_rank_products_or_change_recommendations(
    fixture_bytes: bytes,
    command_factory,
) -> None:
    report = RecordedPortfolioDecisionJob(
        exchange=RecordedPortfolioDecisionAdapter(fixture_bytes)
    ).evaluate(command_factory(fixture_bytes))
    boundary = report.payload()["finance_editorial_boundary"]
    assert isinstance(boundary, dict)
    assert boundary
    assert all(value is False for value in boundary.values())


def test_domain_rejects_non_evidence() -> None:
    with pytest.raises(PortfolioDecisionFailure) as caught:
        build_portfolio_decision_report(object())  # type: ignore[arg-type]
    assert caught.value.code is PortfolioDecisionFailureCode.INVALID_ARGUMENT


def test_command_rejects_wrong_program(
    fixture_bytes: bytes,
    command_factory,
) -> None:
    valid: PortfolioDecisionCommand = command_factory(fixture_bytes)
    with pytest.raises(PortfolioDecisionFailure):
        PortfolioDecisionCommand(
            recording_id=valid.recording_id,
            fixture_digest=valid.fixture_digest,
            fixture_length=valid.fixture_length,
            contract_digest=valid.contract_digest,
            expected_input_digest=valid.expected_input_digest,
            expected_source_pack_digest=valid.expected_source_pack_digest,
            program_id="OTHER_PROGRAM",
        )


def test_sensitive_values_are_redacted_and_not_pickleable(
    fixture_bytes: bytes,
    command_factory,
) -> None:
    command = command_factory(fixture_bytes)
    assert "blocked-synthetic" not in repr(command)
    assert str(command) == "<redacted-portfolio-decision>"
    assert "1be17" not in repr(Sha256Digest(command.expected_source_pack_digest.value))
    with pytest.raises(TypeError):
        pickle.dumps(command)

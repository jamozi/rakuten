"""Golden arithmetic, Gate truth, and editorial separation tests."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from raos.domain.analytics.gate2_observation import (
    Availability,
    BoundaryState,
    Gate2ObservationReport,
    PROGRAM,
)
from scripts import build_st1803_gate2_observation as builder


def _metric(report: Gate2ObservationReport, metric_id: str):
    return next(row for row in report.metrics if row.metric_id == metric_id)


def _total(report: Gate2ObservationReport, metric_id: str):
    return next(row for row in report.input_totals if row.metric_id == metric_id)


def test_exact_golden_metrics_use_decimal_not_float(
    report: Gate2ObservationReport,
) -> None:
    expected = {
        "observation_days": Decimal("90"),
        "qualified_organic_sessions": Decimal("2250"),
        "indexed_article_rate": Decimal("0.800000"),
        "impression_coverage_rate": Decimal("0.750000"),
        "top20_article_rate": Decimal("0.200000"),
        "search_ctr": Decimal("0.050000"),
        "affiliate_click_rate": Decimal("0.062000"),
        "stale_exposure_rate": Decimal("0.010000"),
        "broken_affiliate_link_rate": Decimal("0.002000"),
        "confirmed_reward_per_click": Decimal("24.193548"),
        "confirmation_rate": Decimal("0.714286"),
        "confirmed_reward_per_content_hour": Decimal("2000.000000"),
    }
    assert {row.metric_id: row.value for row in report.metrics} == expected
    assert all(row.availability is Availability.AVAILABLE for row in report.metrics)
    assert all(type(row.value) is Decimal for row in report.metrics)
    assert all(row.recommendation_order_effect is False for row in report.metrics)


def test_all_requested_article_inputs_are_typed_and_summarized(
    report: Gate2ObservationReport,
) -> None:
    assert {row.metric_id: row.value for row in report.input_totals} == {
        "total_search_impressions": Decimal("45000"),
        "total_search_clicks": Decimal("2250"),
        "total_article_views": Decimal("10000"),
        "total_affiliate_clicks": Decimal("620"),
        "total_pending_outcomes": Decimal("29"),
        "total_confirmed_outcomes": Decimal("15"),
        "total_rejected_outcomes": Decimal("6"),
        "total_direct_confirmed_reward_jpy": Decimal("15000"),
        "total_work_minutes": Decimal("450"),
        "total_incremental_cost_jpy": Decimal("1125"),
        "total_broken_links": Decimal("1"),
    }


def test_direct_and_unattributed_reward_conserve_without_allocation(
    report: Gate2ObservationReport,
) -> None:
    assert report.direct_confirmed_reward_jpy == 15000
    assert report.unattributed_confirmed_reward_jpy == 2500
    assert report.provider_confirmed_reward_jpy == 17500
    assert report.reward_conservation is Availability.AVAILABLE
    assert report.reward_conservation_reason is None
    payload = report.payload()["finance_separation"]
    assert isinstance(payload, dict)
    assert payload["unattributed_reward_allocated_to_articles"] is False


def test_candidates_are_output_only_and_non_financial(
    report: Gate2ObservationReport,
) -> None:
    assert [(item.slot, item.code) for item in report.candidates] == [
        (3, "REVIEW_LINK_HEALTH"),
        (3, "REVIEW_QUERY_INTENT_AND_DISCOVERY"),
        (5, "REVIEW_FRESHNESS_EXPOSURE"),
    ]
    payload = report.payload()
    serialized = str(payload["candidates"]).lower()
    for forbidden in ("reward", "profit", "epc", "rpm", "commission", "cost"):
        assert forbidden not in serialized
    assert payload["modifications_applied"] == []
    authority = payload["authority"]
    assert isinstance(authority, dict)
    assert set(authority.values()) == {"NONE"}


def test_local_report_never_claims_actual_observation_or_gate_pass(
    report: Gate2ObservationReport,
) -> None:
    assert report.program_id == PROGRAM
    assert report.execution is BoundaryState.RECORDED_SYNTHETIC_ONLY
    assert report.actual_observation is BoundaryState.NOT_EXECUTED
    assert report.formal_tst_030 is BoundaryState.NOT_EXECUTED
    assert report.formal_tst_032 is BoundaryState.NOT_EXECUTED
    assert report.overall is BoundaryState.BLOCKED
    assert report.payload()["actual_observations"] == []


def test_generated_pack_keeps_every_synthetic_criterion_ineligible() -> None:
    pack: dict[str, Any] = builder.build_pack()
    assert pack["overall"] == "BLOCKED"
    assert pack["gate_pass_claim"] is False
    assert pack["actual_observations"] == []
    criteria = pack["mandatory_criteria"]
    assert isinstance(criteria, list)
    assert len(criteria) == 17
    synthetic = [
        row
        for row in criteria
        if isinstance(row, dict)
        and row["evidence_classification"] == "RECORDED_SYNTHETIC_ONLY_NON_ATTESTING"
    ]
    assert synthetic
    assert {row["status"] for row in synthetic} == {"INELIGIBLE_NON_ATTESTING"}
    relations = {
        row["criterion_id"]: row["synthetic_threshold_relation"] for row in synthetic
    }
    assert relations["G2-C01-OBSERVATION-DAYS"] == "MEETS_PROVISIONAL_THRESHOLD"
    assert (
        relations["G2-C02-QUALIFIED-SESSIONS"] == "DOES_NOT_MEET_PROVISIONAL_THRESHOLD"
    )
    assert relations["G2-C06-AFFILIATE-CTR"] == "MEETS_PROVISIONAL_THRESHOLD"
    quality = pack["data_quality"]
    assert isinstance(quality, dict)
    assert quality["append_only_hash_chain"] == "LOCAL_SYNTHETIC_PASS"
    assert quality["synthetic_is_actual_observation"] is False


def test_input_totals_do_not_replace_gate_or_candidate_logic(
    report: Gate2ObservationReport,
) -> None:
    assert _metric(report, "affiliate_click_rate").value == Decimal("0.062000")
    assert _total(report, "total_incremental_cost_jpy").value == Decimal("1125")
    assert report.recommendation_input is BoundaryState.DISABLED

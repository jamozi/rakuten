"""Golden arithmetic and non-attesting Gate truth tests."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import cast

from raos.domain.analytics.gate3_economics import (
    CriterionStatus,
    FINANCE_EDITORIAL_INPUTS_FORBIDDEN,
    Gate3EconomicsReport,
    Gate3Metric,
    Gate3Overall,
    MetricAvailability,
    UnavailableReason,
)


def _metric(report: Gate3EconomicsReport, key: str) -> Gate3Metric:
    return next(metric for metric in report.metrics if metric.metric_id == key)


def test_exact_synthetic_arithmetic_uses_decimal(
    report: Gate3EconomicsReport,
) -> None:
    assert {row.metric_id: row.value for row in report.metrics} == {
        "cumulative_qualified_article_sessions": Decimal("39000"),
        "confirmation_cycles_completed": Decimal("3"),
        "months_with_calculable_article_costs": Decimal("3"),
        "confirmed_provider_reward_jpy": Decimal("51000"),
        "direct_confirmed_reward_jpy": Decimal("33000"),
        "estimated_confirmed_reward_jpy": Decimal("7500"),
        "unattributed_confirmed_reward_jpy": Decimal("10500"),
        "confirmed_rpm_direct_jpy": Decimal("846.153846"),
        "confirmed_epc_direct_jpy": Decimal("104.761905"),
        "contribution_profit_i_direct_jpy_3m": Decimal("30000"),
        "profit_i_max_consecutive_positive_months": Decimal("3"),
        "contribution_profit_ii_direct_jpy_3m": Decimal("19500"),
        "content_payback_months_direct": None,
        "direct_reward_concentration_top10": Decimal("0.500000"),
        "update_cost_ratio_direct": Decimal("0.045455"),
        "serious_compliance_incidents": Decimal("0"),
    }
    assert {
        row.metric_id
        for row in report.metrics
        if row.availability is MetricAvailability.UNAVAILABLE
    } == {"content_payback_months_direct"}
    assert (
        _metric(report, "content_payback_months_direct").unavailable_reason
        is UnavailableReason.ARTICLE_GROUP_BASIS_UNAVAILABLE
    )


def test_provider_direct_estimated_unattributed_are_distinct_and_conserve(
    report: Gate3EconomicsReport,
) -> None:
    provider = _metric(report, "confirmed_provider_reward_jpy").value
    direct = _metric(report, "direct_confirmed_reward_jpy").value
    estimated = _metric(report, "estimated_confirmed_reward_jpy").value
    unattributed = _metric(report, "unattributed_confirmed_reward_jpy").value
    assert provider is not None
    assert direct is not None
    assert estimated is not None
    assert unattributed is not None
    assert provider == direct + estimated + unattributed
    assert report.reward_conservation is MetricAvailability.AVAILABLE
    payload = cast(Mapping[str, object], report.payload()["reward_basis"])
    assert payload["provider_total_is_article_attribution"] is False
    assert payload["unattributed_reward_allocated_to_articles"] is False


def test_finance_metrics_use_direct_only_basis(
    report: Gate3EconomicsReport,
) -> None:
    for key in (
        "confirmed_rpm_direct_jpy",
        "confirmed_epc_direct_jpy",
        "contribution_profit_i_direct_jpy_3m",
        "contribution_profit_ii_direct_jpy_3m",
        "content_payback_months_direct",
        "direct_reward_concentration_top10",
        "update_cost_ratio_direct",
    ):
        assert _metric(report, key).basis == (
            "VERIFIED_DIRECT_ONLY_ESTIMATED_UNATTRIBUTED_EXCLUDED"
        )


def test_no_synthetic_criterion_can_be_a_gate_pass(
    report: Gate3EconomicsReport,
) -> None:
    assert report.overall is Gate3Overall.BLOCKED
    assert {row.status for row in report.criteria} == {
        CriterionStatus.INELIGIBLE_NON_ATTESTING,
        CriterionStatus.UNAVAILABLE,
    }
    assert all(
        row.status is not CriterionStatus.INELIGIBLE_NON_ATTESTING
        or row.would_meet_numeric_threshold is True
        for row in report.criteria
    )
    payload = report.payload()
    assert payload["actual_observations"] == []
    assert payload["gate_pass_claim"] is False
    authority = cast(Mapping[str, object], payload["authority"])
    assert set(authority.values()) == {"NONE"}


def test_human_judgment_remains_unavailable(report: Gate3EconomicsReport) -> None:
    unavailable = {
        row.criterion_id
        for row in report.criteria
        if row.status is CriterionStatus.UNAVAILABLE
    }
    assert unavailable == {"G3-C03", "G3-C06", "G3-C07"}


def test_editorial_and_publication_mutation_is_impossible_in_report(
    report: Gate3EconomicsReport,
) -> None:
    boundary = cast(
        Mapping[str, object],
        report.payload()["finance_editorial_separation"],
    )
    excluded = cast(
        list[object],
        boundary["finance_signals_excluded_from_article_logic"],
    )
    assert tuple(excluded) == FINANCE_EDITORIAL_INPUTS_FORBIDDEN
    assert all(
        boundary[key] is False
        for key in (
            "article_html_mutation",
            "cta_mutation",
            "product_selection_mutation",
            "publication_snapshot_mutation",
            "recommendation_order_mutation",
        )
    )
    assert report.payload()["modifications_applied"] == []


def test_report_hash_is_reproducible_and_binds_payload(
    report: Gate3EconomicsReport,
) -> None:
    assert (
        report.evaluation_sha256.value
        == "3deb0118cc696bd8ed3fbab90eb3b992883c55bd5e62c3d0b531a71fd11a5311"
    )
    assert report.canonical_bytes() == report.canonical_bytes()


def test_every_metric_binds_the_recorded_synthetic_evaluation_context(
    report: Gate3EconomicsReport,
) -> None:
    payload = report.payload()
    context = cast(Mapping[str, object], payload["evaluation_context"])
    assert context["freshness"] == "RECORDED_SYNTHETIC_STATIC_FIXTURE_NON_LIVE"
    assert context["recorded_at"] == "2026-04-01T00:00:00Z"
    months = cast(list[Mapping[str, object]], context["months"])
    assert len(months) == 3
    assert {month["program"] for month in months} == {
        "WORDPRESS_BLOG_RAKUTEN_AFFILIATE"
    }
    assert {month["cohort_maturity"] for month in months} == {"MATURE"}
    assert all(month["source_bundle_sha256"] is not None for month in months)
    rows = cast(list[Mapping[str, object]], payload["metrics"])
    assert all(row["evaluation_context_ref"] == "#/evaluation_context" for row in rows)

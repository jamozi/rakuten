"""Availability propagation and false-attribution negative tests."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import cast

import pytest

from .support import clone_month, rebuild_batch, replace_metric
from raos.domain.analytics.gate3_economics import (
    CohortMaturity,
    CriterionStatus,
    Gate3EconomicsReport,
    Gate3Metric,
    MetricAvailability,
    MonthPeriod,
    MonthObservation,
    RecordedEconomicsBatch,
    UnavailableReason,
    ValueState,
    build_gate3_economics_report,
)


def _metric(report: Gate3EconomicsReport, key: str) -> Gate3Metric:
    return next(metric for metric in report.metrics if metric.metric_id == key)


@pytest.mark.parametrize(
    ("state", "value", "source_sha256", "reason"),
    [
        (ValueState.UNAVAILABLE, None, None, UnavailableReason.MISSING_INPUT),
        (ValueState.NOT_OBSERVED, None, None, UnavailableReason.MISSING_INPUT),
        (
            ValueState.UNVERIFIED,
            10000,
            "retain",
            UnavailableReason.UNVERIFIED_INPUT,
        ),
    ],
)
def test_missing_and_unverified_never_become_zero(
    batch: RecordedEconomicsBatch,
    state: ValueState,
    value: int | None,
    source_sha256: object,
    reason: UnavailableReason,
) -> None:
    def transform(month: MonthObservation) -> MonthObservation:
        if month.sequence != 1:
            return month
        original = month.metric("qualified_article_sessions")
        return replace_metric(
            month,
            "qualified_article_sessions",
            state=state,
            value=value,
            source_sha256=(
                original.source_sha256 if source_sha256 == "retain" else None
            ),
        )

    report = build_gate3_economics_report(rebuild_batch(batch, transform))
    metric = _metric(report, "cumulative_qualified_article_sessions")
    assert metric.availability is MetricAvailability.UNAVAILABLE
    assert metric.value is None
    assert metric.unavailable_reason is reason


def test_zero_denominator_is_unavailable_not_zero(
    batch: RecordedEconomicsBatch,
) -> None:
    changed = rebuild_batch(
        batch,
        lambda month: replace_metric(
            month,
            "eligible_affiliate_clicks",
            state=ValueState.RECORDED_SYNTHETIC_ZERO,
            value=0,
        ),
    )
    metric = _metric(build_gate3_economics_report(changed), "confirmed_epc_direct_jpy")
    assert metric.availability is MetricAvailability.UNAVAILABLE
    assert metric.unavailable_reason is UnavailableReason.ZERO_DENOMINATOR
    assert metric.value is None


def test_unverified_attribution_blocks_finance_but_not_session_count(
    batch: RecordedEconomicsBatch,
) -> None:
    changed = rebuild_batch(
        batch,
        lambda month: (
            clone_month(month, attribution_verified=False)
            if month.sequence == 2
            else month
        ),
    )
    report = build_gate3_economics_report(changed)
    assert (
        _metric(report, "cumulative_qualified_article_sessions").availability
        is MetricAvailability.AVAILABLE
    )
    assert (
        _metric(report, "confirmed_provider_reward_jpy").availability
        is MetricAvailability.AVAILABLE
    )
    assert (
        _metric(report, "direct_confirmed_reward_jpy").unavailable_reason
        is UnavailableReason.ATTRIBUTION_UNVERIFIED
    )


def test_unverified_cost_blocks_profit_but_not_provider_total(
    batch: RecordedEconomicsBatch,
) -> None:
    changed = rebuild_batch(
        batch,
        lambda month: (
            clone_month(month, cost_basis_verified=False)
            if month.sequence == 3
            else month
        ),
    )
    report = build_gate3_economics_report(changed)
    assert (
        _metric(report, "confirmed_provider_reward_jpy").availability
        is MetricAvailability.AVAILABLE
    )
    assert (
        _metric(report, "contribution_profit_ii_direct_jpy_3m").unavailable_reason
        is UnavailableReason.COST_UNVERIFIED
    )


def test_immature_cohort_is_unavailable(
    batch: RecordedEconomicsBatch,
) -> None:
    changed = rebuild_batch(
        batch,
        lambda month: (
            clone_month(month, cohort_maturity=CohortMaturity.IMMATURE)
            if month.sequence == 1
            else month
        ),
    )
    assert all(
        metric.unavailable_reason is UnavailableReason.COHORT_IMMATURE
        for metric in build_gate3_economics_report(changed).metrics
    )


def test_mixed_program_is_unavailable(batch: RecordedEconomicsBatch) -> None:
    changed = rebuild_batch(
        batch,
        lambda month: (
            clone_month(month, program_id="OTHER_PROGRAM")
            if month.sequence == 2
            else month
        ),
    )
    assert all(
        metric.unavailable_reason is UnavailableReason.PROGRAM_MISMATCH
        for metric in build_gate3_economics_report(changed).metrics
    )


def test_noncontiguous_period_is_unavailable(batch: RecordedEconomicsBatch) -> None:
    changed = rebuild_batch(
        batch,
        lambda month: (
            clone_month(
                month,
                period=MonthPeriod(date(2026, 4, 1), date(2026, 5, 1)),
            )
            if month.sequence == 2
            else month
        ),
    )
    assert all(
        metric.unavailable_reason is UnavailableReason.PERIOD_MISMATCH
        for metric in build_gate3_economics_report(changed).metrics
    )


def test_reward_conservation_mismatch_is_visible_and_blocks_finance(
    batch: RecordedEconomicsBatch,
) -> None:
    changed = rebuild_batch(
        batch,
        lambda month: (
            replace_metric(month, "provider_confirmed_reward_jpy", value=15001)
            if month.sequence == 1
            else month
        ),
    )
    report = build_gate3_economics_report(changed)
    assert report.reward_conservation is MetricAvailability.UNAVAILABLE
    assert (
        report.reward_conservation_reason
        is UnavailableReason.REWARD_CONSERVATION_MISMATCH
    )
    assert (
        _metric(report, "direct_confirmed_reward_jpy").unavailable_reason
        is UnavailableReason.REWARD_CONSERVATION_MISMATCH
    )


def test_nonpositive_profit_ii_preserves_reasonable_trend_as_human_judgment(
    batch: RecordedEconomicsBatch,
) -> None:
    changed = rebuild_batch(
        batch,
        lambda month: replace_metric(month, "labor_cost_jpy", value=20000),
    )
    report = build_gate3_economics_report(changed)
    profit = _metric(report, "contribution_profit_ii_direct_jpy_3m")
    assert profit.value is not None and profit.value < 0
    criterion = next(row for row in report.criteria if row.criterion_id == "G3-C05")
    assert criterion.status is CriterionStatus.UNAVAILABLE
    assert criterion.would_meet_numeric_threshold is None
    assert criterion.unavailable_reason is UnavailableReason.HUMAN_JUDGMENT_REQUIRED


def test_finance_changes_never_create_editorial_mutation(
    batch: RecordedEconomicsBatch,
) -> None:
    changed = rebuild_batch(
        batch,
        lambda month: replace_metric(
            replace_metric(month, "direct_confirmed_reward_jpy", value=1),
            "provider_confirmed_reward_jpy",
            value=(
                1
                + (month.metric("estimated_confirmed_reward_jpy").value or 0)
                + (month.metric("unattributed_confirmed_reward_jpy").value or 0)
            ),
        ),
    )
    payload = build_gate3_economics_report(changed).payload()
    assert payload["gate_pass_claim"] is False
    assert payload["modifications_applied"] == []
    separation = cast(Mapping[str, object], payload["finance_editorial_separation"])
    assert all(
        value is False for key, value in separation.items() if key.endswith("mutation")
    )

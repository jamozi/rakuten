from __future__ import annotations

from decimal import Decimal
import json

from raos.domain.analytics.analytics_finance_dashboard import (
    AnalyticsFinanceDashboardSnapshot,
    MetricAvailability,
    MetricFreshness,
    MetricVerification,
    SCREEN_ORDER,
    ScreenAvailability,
)


def test_exact_six_screen_headless_projection_is_deterministic(
    snapshot: AnalyticsFinanceDashboardSnapshot,
) -> None:
    assert tuple(screen.screen_id for screen in snapshot.screens) == SCREEN_ORDER
    assert snapshot.cross_source_comparison == "UNAVAILABLE_PERIOD_MISMATCH"
    assert snapshot.canonical_bytes() == snapshot.canonical_bytes()
    payload = json.loads(snapshot.canonical_bytes())
    assert payload["result_sha256"] == snapshot.result_sha256.value
    assert payload["synthetic"] is True
    assert payload["data_classification"] == "CONFIDENTIAL"


def test_basis_period_freshness_and_verification_are_visible(
    snapshot: AnalyticsFinanceDashboardSnapshot,
) -> None:
    analytics = snapshot.screens[0].metric_rows[0]
    assert analytics.source_story_id == "ST-1205"
    assert analytics.period_start == "2026-07-01"
    assert analytics.period_end == "2026-07-31"
    assert analytics.period_end_inclusive is True
    assert analytics.freshness is MetricFreshness.RECORDED_SYNTHETIC_NO_LIVE_ATTESTATION
    assert analytics.upstream_freshness == "RECORDED_SYNTHETIC"
    assert (
        analytics.verification is MetricVerification.RECORDED_SYNTHETIC_INPUTS_VERIFIED
    )
    assert analytics.live_verified is False

    finance = snapshot.screens[5].metric_rows[0]
    assert finance.source_story_id == "ST-1304"
    assert finance.period_start == "2026-08-25"
    assert finance.period_end == "2026-09-08"
    assert finance.period_end_inclusive is False
    assert (
        finance.freshness
        is MetricFreshness.UNKNOWN_SOURCE_HAS_NO_APPROVED_FRESHNESS_POLICY
    )
    assert finance.basis == "VERIFIED_PROVIDER_FACT_TOTAL"


def test_unavailable_import_is_not_empty_success_or_zero(
    snapshot: AnalyticsFinanceDashboardSnapshot,
) -> None:
    screen = snapshot.screens[3]
    row = screen.metric_rows[0]
    assert screen.availability is ScreenAvailability.UNAVAILABLE_DEPENDENCY
    assert row.availability is MetricAvailability.UNAVAILABLE
    assert row.value is None
    assert row.unavailable_reason == "UNAVAILABLE_UNDECLARED_DEPENDENCY"
    assert row.source_sha256s == ()
    assert row.unknown_as_zero_allowed is False


def test_reward_bases_are_separate_and_verified_zero_remains_zero(
    snapshot: AnalyticsFinanceDashboardSnapshot,
) -> None:
    rows = {row.metric_id: row for row in snapshot.screens[4].metric_rows}
    assert rows["PROVIDER_CONFIRMED_REWARD"].value == Decimal("300")
    assert rows["DIRECT_CONFIRMED_REWARD"].value == Decimal("120")
    assert rows["ESTIMATED_CONFIRMED_REWARD"].value == Decimal("101")
    assert rows["UNATTRIBUTED_CONFIRMED_REWARD"].value == Decimal("79")
    zero = rows["REWARD_CONSERVATION_DIFFERENCE"]
    assert zero.availability is MetricAvailability.AVAILABLE
    assert zero.value == Decimal(0)
    assert zero.unavailable_reason is None
    assert zero.basis == "RECORDED_SYNTHETIC_CONSERVATION"


def test_every_authority_and_mutation_boundary_is_closed(
    snapshot: AnalyticsFinanceDashboardSnapshot,
) -> None:
    assert set(snapshot.authority.payload().values()) == {False}
    encoded = snapshot.canonical_bytes().decode("ascii")
    for prohibited in (
        '"route_registration":true',
        '"public_projection":true',
        '"financial_allocation":true',
        '"ranking_or_editorial_mutation":true',
        '"publication":true',
        '"production":true',
    ):
        assert prohibited not in encoded
    assert '"unknown_as_zero_allowed":true' not in encoded
    assert '"live_verified":true' not in encoded

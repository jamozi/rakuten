from __future__ import annotations

from dataclasses import fields, replace
import json
from typing import Any, cast

from raos.adapters.recorded_finance_reconciliation import (
    RecordedFinanceReconciliationAdapter,
    RecordedFinanceReconciliationScenario,
)
from raos.application.finance.reconciliation import FinanceReconciliationService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.finance.attribution import MeasurementValue
from raos.domain.finance.reconciliation import (
    CANDIDATE_SIGNAL_NAMES,
    FINANCE_SIGNALS_EXCLUDED_FROM_CANDIDATES,
    METHOD_VERSION,
    RECONCILIATION_DIMENSIONS,
    CandidateSignals,
    ComparisonStatus,
    LearningAvailability,
    LearningCandidateType,
    ReconciliationAvailability,
    ReconciliationExceptionCode,
    build_finance_reconciliation,
    build_learning_candidates,
    candidate_signals,
)


def test_recorded_run_is_exact_and_idempotent(
    scenario: RecordedFinanceReconciliationScenario,
) -> None:
    adapter = RecordedFinanceReconciliationAdapter()
    service = FinanceReconciliationService(
        environment=RuntimeEnvironment.CI, runner=adapter
    )

    first = service.execute(scenario.request)
    replay = service.execute(scenario.request)

    assert first == replay
    assert first.canonical_bytes() == replay.canonical_bytes()
    assert first.method_version == METHOD_VERSION
    assert first.input_sha256 == scenario.request.input_sha256
    assert first.availability is ReconciliationAvailability.PARTIAL
    assert adapter.snapshot().run_count == 1
    assert adapter.snapshot().replay_count == 1


def test_report_reconciles_exact_totals_and_preserves_external_unknowns(
    scenario: RecordedFinanceReconciliationScenario,
) -> None:
    result = build_finance_reconciliation(scenario.request)
    assert tuple(item.dimension for item in result.comparisons) == (
        RECONCILIATION_DIMENSIONS
    )
    assert len(result.comparisons) == 14
    unavailable: dict[str, str] = {}
    for item in result.comparisons:
        if item.status is ComparisonStatus.UNAVAILABLE:
            assert item.unavailable_reason is not None
            unavailable[item.dimension] = item.unavailable_reason.value
    assert unavailable == {
        "file_hash_uniqueness": "PROVIDER_REPORT_UNAVAILABLE",
        "row_count": "PROVIDER_REPORT_UNAVAILABLE",
        "generated_confirmed_cancelled_amount_totals": (
            "GENERATED_CANCELLED_TOTALS_UNAVAILABLE"
        ),
        "dry_run_to_commit_hash_equality": "DRY_RUN_COMMIT_HASH_UNAVAILABLE",
    }
    assert all(
        item.status is ComparisonStatus.MATCHED
        for item in result.comparisons
        if item.dimension not in unavailable
    )

    totals = cast(dict[str, Any], result.totals.payload())
    assert totals["attribution_totals"] == {
        "direct_confirmed_reward_jpy": "120",
        "estimated_confirmed_reward_jpy": "101",
        "unattributed_confirmed_reward_jpy": "79",
        "unattributed_reward_allocated_to_articles": False,
    }
    assert totals["amount_totals"]["provider"]["confirmed_jpy"]["value"] == "300"
    assert totals["amount_totals"]["canonical"]["confirmed_jpy"]["value"] == ("300")
    for side in ("provider", "canonical"):
        for state in ("generated_jpy", "cancelled_jpy"):
            assert totals["amount_totals"][side][state] == {
                "availability": "UNAVAILABLE",
                "unavailable_reason": "GENERATED_CANCELLED_TOTALS_UNAVAILABLE",
                "value": None,
            }
    assert totals["row_counts"]["provider_report_row_count"] == {
        "availability": "UNAVAILABLE",
        "unavailable_reason": "PROVIDER_REPORT_UNAVAILABLE",
        "value": None,
    }
    assert totals["cost_totals"] == {
        "human_labor_cost_jpy": "6000.00",
        "incremental_external_cost_jpy": "0",
        "work_minutes": 300,
    }
    assert [item.code for item in result.exceptions] == [
        ReconciliationExceptionCode.EXTERNAL_PROVIDER_REPORT_REQUIRED,
        ReconciliationExceptionCode.GENERATED_CANCELLED_TOTALS_REQUIRED,
        ReconciliationExceptionCode.DRY_RUN_COMMIT_EVIDENCE_REQUIRED,
    ]


def test_measurement_metrics_use_one_verified_program_period_and_mature_cohort(
    scenario: RecordedFinanceReconciliationScenario,
) -> None:
    result = build_finance_reconciliation(scenario.request)
    assert {
        item.name: (item.numerator, item.denominator, item.value_decimal)
        for item in result.measurement_metrics
    } == {
        "search_ctr": (300, 3000, "0.100000"),
        "affiliate_click_rate": (50, 1500, "0.033333"),
        "confirmed_reward_per_click_jpy": (120, 50, "2.400000"),
        "confirmation_rate": (5, 8, "0.625000"),
        "confirmed_reward_per_content_hour_jpy": (7200, 300, "24.000000"),
    }


def test_learning_report_returns_review_candidates_only(
    scenario: RecordedFinanceReconciliationScenario,
) -> None:
    result = build_finance_reconciliation(scenario.request)
    assert result.learning_availability is LearningAvailability.AVAILABLE
    assert result.learning_unavailable_reason is None
    assert len(result.learning_candidates) == 1
    candidate = result.learning_candidates[0]
    assert candidate.candidate_type is (
        LearningCandidateType.PURCHASE_DECISION_BRIDGE_REVIEW
    )
    assert candidate.article.slot == 4
    assert candidate.evidence_metric_names == ("article_views", "affiliate_clicks")
    payload = cast(dict[str, Any], candidate.payload())
    assert payload["finance_signal_used"] is False
    assert set(payload["mutation_authority"].values()) == {False}
    assert payload["selection_basis"] == "NON_FINANCE_MEASUREMENT_ALLOWLIST_ONLY"
    encoded = json.loads(result.canonical_bytes())
    assert encoded["learning_report"]["output_kind"] == "REVIEW_CANDIDATES_ONLY"
    assert encoded["learning_report"]["finance_signals_excluded"] == list(
        FINANCE_SIGNALS_EXCLUDED_FROM_CANDIDATES
    )


def test_candidate_type_is_structurally_closed_to_nonfinance_signals(
    scenario: RecordedFinanceReconciliationScenario,
) -> None:
    assert tuple(item.name for item in fields(CandidateSignals)) == (
        "article",
        *CANDIDATE_SIGNAL_NAMES,
    )
    measurements = (
        scenario.request.unit_economics_request.attribution_request.article_measurements
    )
    original = candidate_signals(measurements)
    changed_rows = []
    for row in measurements:
        changed_rows.append(
            replace(
                row,
                metrics=tuple(
                    (
                        name,
                        MeasurementValue(
                            value.state, value.value + 9000, value.input_sha256
                        )
                        if name == "direct_confirmed_reward_jpy"
                        and value.value is not None
                        and value.value > 0
                        else value,
                    )
                    for name, value in row.metrics
                ),
            )
        )
    changed = candidate_signals(tuple(changed_rows))
    assert changed == original
    assert build_learning_candidates(changed) == build_learning_candidates(original)


def test_authority_and_recommendation_mutation_boundaries_are_closed(
    scenario: RecordedFinanceReconciliationScenario,
) -> None:
    result = build_finance_reconciliation(scenario.request)
    assert set(result.authority.payload().values()) == {False}
    policy = json.loads(result.canonical_bytes())["recommendation_input_policy"]
    assert policy["all_finance_values_excluded"] is True
    for field in (
        "finance_may_change_article_html",
        "finance_may_change_cta",
        "finance_may_change_product_selection",
        "finance_may_change_publication_snapshot",
        "finance_may_change_recommendation_order",
    ):
        assert policy[field] is False
    encoded = result.canonical_bytes().decode("ascii")
    for forbidden in (
        '"provider_call":true',
        '"network":true',
        '"credential_access":true',
        '"persistence":true',
        '"database":true',
        '"public_projection":true',
        '"publication":true',
        '"editorial_mutation":true',
        '"article_html_mutation":true',
        '"cta_mutation":true',
        '"product_selection_mutation":true',
        '"recommendation_order_mutation":true',
        '"publication_snapshot_mutation":true',
        '"staging":true',
        '"release":true',
        '"production":true',
    ):
        assert forbidden not in encoded

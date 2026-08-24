from __future__ import annotations

from decimal import Decimal
import json

from raos.adapters.recorded_unit_economics import (
    RecordedUnitEconomicsAdapter,
    RecordedUnitEconomicsScenario,
)
from raos.application.finance.unit_economics import UnitEconomicsService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.finance.unit_economics import (
    COST_COMPONENT_METRICS,
    METHOD_VERSION,
    EconomicsAvailability,
    MetricAvailability,
    MetricBasis,
    build_unit_economics,
)


def test_recorded_run_is_exact_and_idempotent(
    scenario: RecordedUnitEconomicsScenario,
) -> None:
    request = scenario.request
    adapter = RecordedUnitEconomicsAdapter()
    service = UnitEconomicsService(environment=RuntimeEnvironment.CI, runner=adapter)

    first = service.execute(request)
    replay = service.execute(request)

    assert first == replay
    assert first.canonical_bytes() == replay.canonical_bytes()
    assert first.availability is EconomicsAvailability.AVAILABLE
    assert first.unavailable_reason is None
    assert first.method_version == METHOD_VERSION
    assert first.input_sha256 == request.input_sha256
    assert adapter.snapshot().run_count == 1
    assert adapter.snapshot().replay_count == 1


def test_totals_conserve_reward_and_keep_unattributed_separate(
    scenario: RecordedUnitEconomicsScenario,
) -> None:
    result = build_unit_economics(scenario.request)
    assert result.totals.payload() == {
        "direct_confirmed_reward_jpy": "120",
        "estimated_confirmed_reward_jpy": "101",
        "human_labor_cost_jpy": "6000.00",
        "incremental_external_cost_jpy": "0",
        "provider_confirmed_reward_jpy": "300",
        "qualified_sessions": 1500,
        "reward_conservation_difference_jpy": "0",
        "unattributed_confirmed_reward_jpy": "79",
        "work_minutes": 300,
    }
    assert (
        result.totals.direct_confirmed_reward_jpy.value
        + result.totals.estimated_confirmed_reward_jpy.value
        + result.totals.unattributed_confirmed_reward_jpy.value
        == result.totals.provider_confirmed_reward_jpy.value
    )


def test_canonical_and_supplemental_metrics_use_exact_decimal(
    scenario: RecordedUnitEconomicsScenario,
) -> None:
    result = build_unit_economics(scenario.request)
    actual = {item.name: item.value for item in result.metrics}
    assert actual == {
        "confirmed_provider_reward_jpy": Decimal("300.00"),
        "direct_confirmed_reward_jpy": Decimal("120.00"),
        "direct_confirmed_contribution_profit_jpy": Decimal("-5880.00"),
        "confirmed_epc_jpy": Decimal("2.40"),
        "confirmed_rpm_jpy": Decimal("80.00"),
        "article_update_cost_ratio": Decimal("0.833333"),
        "content_payback_months": Decimal("26.25"),
        "ai_cost_per_approved_article_jpy": Decimal("0.00"),
        "confirmed_reward_per_content_hour_jpy": Decimal("24.00"),
    }
    assert all(
        item.availability is MetricAvailability.AVAILABLE for item in result.metrics
    )


def test_metric_basis_is_visible_and_article_metrics_are_direct_only(
    scenario: RecordedUnitEconomicsScenario,
) -> None:
    result = build_unit_economics(scenario.request)
    assert result.metrics[0].basis is MetricBasis.PROVIDER_FACT
    assert all(item.basis is MetricBasis.DIRECT_ONLY for item in result.metrics[1:])
    encoded = json.loads(result.canonical_bytes())
    assert encoded["reward_basis_policy"] == {
        "article_economics": ("VERIFIED_DIRECT_ONLY_ESTIMATED_UNATTRIBUTED_EXCLUDED"),
        "estimated_reward_in_article_metrics": False,
        "provider_total_visible_separately": True,
        "unattributed_allocation_to_articles": False,
        "unattributed_reward_visible_separately": True,
    }


def _required_int(value: int | None) -> int:
    assert type(value) is int
    return value


def test_cost_and_work_provenance_is_visible_and_exact(
    scenario: RecordedUnitEconomicsScenario,
) -> None:
    result = build_unit_economics(scenario.request)
    assert len(result.cost_provenance) == 5
    for row in result.cost_provenance:
        metrics = row.metric_map
        assert metrics["work_minutes"].input_sha256 is not None
        assert metrics["incremental_cost_jpy"].input_sha256 is not None
        assert metrics["work_minutes"].input_sha256.value == "1" * 64
        assert metrics["incremental_cost_jpy"].input_sha256.value == "1" * 64
        assert sum(
            _required_int(metrics[name].value) for name in COST_COMPONENT_METRICS
        ) == _required_int(metrics["incremental_cost_jpy"].value)
    payload = json.loads(result.canonical_bytes())
    assert payload["cost_provenance"][0]["metrics"]["work_minutes"] == {
        "input_sha256": "1" * 64,
        "state": "OBSERVED_VALUE",
        "value": 60,
    }


def test_verified_zero_is_a_real_zero_not_unavailable(
    scenario: RecordedUnitEconomicsScenario,
) -> None:
    result = build_unit_economics(scenario.request)
    ai = next(
        item
        for item in result.metrics
        if item.name == "ai_cost_per_approved_article_jpy"
    )
    assert ai.availability is MetricAvailability.AVAILABLE
    assert ai.value == Decimal("0.00")
    assert ai.unavailable_reason is None


def test_authority_and_recommendation_boundary_are_closed(
    scenario: RecordedUnitEconomicsScenario,
) -> None:
    result = build_unit_economics(scenario.request)
    assert set(result.authority.payload().values()) == {False}
    policy = json.loads(result.canonical_bytes())["recommendation_input_policy"]
    assert policy["all_finance_values_excluded"] is True
    assert policy["finance_may_change_article_html"] is False
    assert policy["finance_may_change_cta"] is False
    assert policy["finance_may_change_product_selection"] is False
    assert policy["finance_may_change_recommendation_order"] is False
    assert policy["finance_may_change_publication_snapshot"] is False
    encoded = result.canonical_bytes().decode("ascii")
    for forbidden in (
        '"provider_call":true',
        '"network":true',
        '"persistence":true',
        '"public_projection":true',
        '"publication":true',
        '"editorial_mutation":true',
        '"article_html_mutation":true',
        '"cta_mutation":true',
        '"product_selection_mutation":true',
        '"recommendation_order_mutation":true',
        '"publication_snapshot_mutation":true',
        '"budget_selection":true',
        '"labor_rate_selection":true',
    ):
        assert forbidden not in encoded
    assert '"proposal"' not in encoded

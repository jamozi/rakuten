from __future__ import annotations

from decimal import Decimal
import json

import pytest

from raos.adapters.recorded_attribution import RecordedAttributionAdapter
from raos.application.finance.attribution import AttributionService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.finance.attribution import (
    DIRECT_CONFIDENCE_BPS,
    ESTIMATED_CONFIDENCE_BPS,
    METHOD_VERSION,
    PROGRAM,
    AllocationReason,
    AttributionAvailability,
    AttributionClass,
    MeasurementAttributionContract,
    allocate_exact_jpy,
    build_attribution_run,
)
from raos.domain.finance.provider_fact_commit import JpyAmount


def test_recorded_run_is_exact_conserved_and_idempotent(scenario: object) -> None:
    request = scenario.request  # type: ignore[attr-defined]
    adapter = RecordedAttributionAdapter()
    service = AttributionService(environment=RuntimeEnvironment.CI, runner=adapter)

    first = service.execute(request)
    replay = service.execute(request)

    assert first == replay
    assert first.canonical_bytes() == replay.canonical_bytes()
    assert first.availability is AttributionAvailability.AVAILABLE
    assert first.unavailable_reason is None
    assert first.method_version == METHOD_VERSION
    assert first.input_sha256 == request.input_sha256
    assert first.totals.payload() == {
        "difference_jpy": "0",
        "direct_confirmed_reward_jpy": "120",
        "estimated_confirmed_reward_jpy": "101",
        "provider_confirmed_reward_jpy": "300",
        "unattributed_confirmed_reward_jpy": "79",
    }
    assert adapter.snapshot().run_count == 1
    assert adapter.snapshot().replay_count == 1


def test_classes_reasons_confidence_and_weights_are_explicit(scenario: object) -> None:
    result = build_attribution_run(scenario.request)  # type: ignore[attr-defined]
    actual = [
        (
            item.attribution_class,
            None if item.article is None else item.article.slot,
            item.confirmed_reward_jpy.canonical_text,
            item.confidence_bps,
            item.reason,
            item.weight_numerator,
            item.weight_denominator,
        )
        for item in result.allocations
    ]
    assert actual == [
        (
            AttributionClass.DIRECT,
            1,
            "120",
            DIRECT_CONFIDENCE_BPS,
            AllocationReason.DIRECT_PROVIDER_KEY_VERIFIED,
            1,
            1,
        ),
        (
            AttributionClass.ESTIMATED,
            1,
            "20",
            ESTIMATED_CONFIDENCE_BPS,
            AllocationReason.ESTIMATED_PROPORTIONAL_ELIGIBLE_CLICKS,
            10,
            50,
        ),
        (
            AttributionClass.ESTIMATED,
            2,
            "41",
            ESTIMATED_CONFIDENCE_BPS,
            AllocationReason.ESTIMATED_PROPORTIONAL_ELIGIBLE_CLICKS,
            20,
            50,
        ),
        (
            AttributionClass.ESTIMATED,
            3,
            "10",
            ESTIMATED_CONFIDENCE_BPS,
            AllocationReason.ESTIMATED_PROPORTIONAL_ELIGIBLE_CLICKS,
            5,
            50,
        ),
        (
            AttributionClass.ESTIMATED,
            5,
            "30",
            ESTIMATED_CONFIDENCE_BPS,
            AllocationReason.ESTIMATED_PROPORTIONAL_ELIGIBLE_CLICKS,
            15,
            50,
        ),
        (
            AttributionClass.UNATTRIBUTED,
            None,
            "79",
            0,
            AllocationReason.UNATTRIBUTED_INSUFFICIENT_SIGNAL,
            None,
            None,
        ),
    ]
    assert all(item.method_version == METHOD_VERSION for item in result.allocations)
    assert all(item.input_sha256 == result.input_sha256 for item in result.allocations)
    assert len({item.allocation_sha256.value for item in result.allocations}) == 6


def test_measurement_metrics_use_exact_decimal_and_exclude_unattributed(
    scenario: object,
) -> None:
    result = build_attribution_run(scenario.request)  # type: ignore[attr-defined]
    metrics = {
        item.name: item.value_decimal for item in result.measurement_evaluation.metrics
    }
    assert metrics == {
        "search_ctr": "0.100000",
        "affiliate_click_rate": "0.033333",
        "confirmed_reward_per_click_jpy": "2.400000",
        "confirmation_rate": "0.625000",
        "confirmed_reward_per_content_hour_jpy": "24.000000",
    }
    program = result.measurement_evaluation.program_unattributed
    assert program.unattributed_confirmed_reward_jpy.value == 79
    assert program.payload()["allocation_to_articles"] == "FORBIDDEN"
    assert all(
        metric.payload()["basis"] == "VERIFIED_DIRECT_ONLY_UNATTRIBUTED_EXCLUDED"
        for metric in result.measurement_evaluation.metrics
    )


@pytest.mark.parametrize("amount", [0, 1, 2, 7, 101, 10_003, 999_999])
@pytest.mark.parametrize(
    "weights",
    [
        ((1, 1),),
        ((1, 1), (2, 1)),
        ((1, 1), (2, 1), (3, 1), (4, 1), (5, 1)),
        ((1, 10), (2, 20), (3, 5), (4, 0), (5, 15)),
        ((1, 9), (2, 0), (3, 4), (4, 17), (5, 2)),
    ],
)
def test_largest_remainder_always_conserves_integral_jpy(
    amount: int, weights: tuple[tuple[int, int], ...]
) -> None:
    allocation = allocate_exact_jpy(JpyAmount(Decimal(amount)), weights)
    assert sum((item.value for _slot, item in allocation), Decimal(0)) == Decimal(
        amount
    )
    assert [slot for slot, _value in allocation] == sorted(
        slot for slot, weight in weights if weight > 0
    )
    assert all(
        item.value == item.value.to_integral_value() for _slot, item in allocation
    )


def test_largest_remainder_tie_breaks_by_slot() -> None:
    assert [
        (slot, amount.canonical_text)
        for slot, amount in allocate_exact_jpy(
            JpyAmount(Decimal(2)), ((1, 1), (2, 1), (3, 1))
        )
    ] == [(1, "1"), (2, "1"), (3, "0")]


def test_contract_binds_exact_five_slots(
    measurement_contract: MeasurementAttributionContract,
) -> None:
    assert measurement_contract.program == PROGRAM
    assert [item.slot for item in measurement_contract.articles] == [1, 2, 3, 4, 5]
    assert len({item.article_id for item in measurement_contract.articles}) == 5
    assert len({item.slug for item in measurement_contract.articles}) == 5
    assert all(
        len(item.packet_sha256.value) == 64 for item in measurement_contract.articles
    )
    assert all(item.intent_classification for item in measurement_contract.articles)


def test_authority_and_recommendation_boundary_are_closed(scenario: object) -> None:
    result = build_attribution_run(scenario.request)  # type: ignore[attr-defined]
    assert set(result.authority.payload().values()) == {False}
    payload = json.loads(result.canonical_bytes())
    assert payload["recommendation_input_policy"] == {
        "all_finance_values_excluded": True,
        "excluded": [
            "AFFILIATE_COMMISSION_RATE",
            "CONFIRMED_REWARD",
            "UNATTRIBUTED_REWARD",
            "COMMISSION",
            "INCREMENTAL_COST",
            "EPC",
            "RPM",
            "PROFIT",
        ],
        "finance_may_change_improvement_candidates": False,
        "finance_may_change_recommendation_order": False,
    }
    encoded = result.canonical_bytes().decode("ascii")
    for forbidden in (
        '"publication":true',
        '"editorial_mutation":true',
        '"article_html_mutation":true',
        '"cta_mutation":true',
        '"product_selection_mutation":true',
        '"recommendation_order_mutation":true',
        '"publication_snapshot_mutation":true',
    ):
        assert forbidden not in encoded
    assert '"proposal"' not in encoded

"""UNAVAILABLE semantics and adversarial numeric tests for ST-1205."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from raos.adapters.recorded_kpi_input import RecordedKpiInputAdapter
from raos.domain.analytics.kpi_read_model import (
    AttributionBasis,
    CalculationContext,
    CohortState,
    InputSource,
    KpiAvailability,
    KpiCalculationCommand,
    KpiFailure,
    KpiFailureCode,
    KpiInputFrame,
    MeasurementPeriod,
    MetricObservation,
    ProgramId,
    UnavailableReason,
    calculate_learning_rows,
    calculate_rows,
)


def _frame_with(
    fixture_bytes: bytes,
    command: KpiCalculationCommand,
    metric_key: str,
    **changes: object,
) -> KpiInputFrame:
    batch = RecordedKpiInputAdapter(fixture_bytes).read(command)
    observations = tuple(
        replace(item, **changes) if item.metric_key == metric_key else item
        for item in batch.input_frame.observations
    )
    assert observations != batch.input_frame.observations
    return KpiInputFrame(observations)


def _row(frame: KpiInputFrame, command: KpiCalculationCommand, kpi_id: str):
    return next(
        row for row in calculate_rows(frame, command.context) if row.kpi_id == kpi_id
    )


def test_missing_input_is_unavailable_not_zero(
    fixture_bytes: bytes, command: KpiCalculationCommand
) -> None:
    batch = RecordedKpiInputAdapter(fixture_bytes).read(command)
    frame = KpiInputFrame(
        tuple(
            item
            for item in batch.input_frame.observations
            if item.metric_key != "organic_impressions"
        )
    )
    row = _row(frame, command, "KPI-014")
    assert row.availability is KpiAvailability.UNAVAILABLE
    assert row.value is None
    assert row.unavailable_reason is UnavailableReason.MISSING_INPUT


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"value": None}, UnavailableReason.MISSING_INPUT),
        ({"verified": False}, UnavailableReason.UNVERIFIED_INPUT),
        ({"cohort_state": CohortState.IMMATURE}, UnavailableReason.IMMATURE_COHORT),
        (
            {"period": MeasurementPeriod(date(2026, 6, 1), date(2026, 6, 30))},
            UnavailableReason.PERIOD_MISMATCH,
        ),
        (
            {"program_id": ProgramId("OTHER_PROGRAM")},
            UnavailableReason.PROGRAM_MISMATCH,
        ),
        ({"source": InputSource.GA4_AGGREGATE}, UnavailableReason.SOURCE_MISMATCH),
    ],
)
def test_search_ctr_gates_are_explicit_unavailable(
    fixture_bytes: bytes,
    command: KpiCalculationCommand,
    changes: dict[str, object],
    reason: UnavailableReason,
) -> None:
    row = _row(
        _frame_with(fixture_bytes, command, "organic_impressions", **changes),
        command,
        "KPI-014",
    )
    assert row.availability is KpiAvailability.UNAVAILABLE
    assert row.value is None
    assert row.unavailable_reason is reason


def test_zero_denominator_is_unavailable_but_never_silent_zero(
    fixture_bytes: bytes, command: KpiCalculationCommand
) -> None:
    row = _row(
        _frame_with(
            fixture_bytes,
            command,
            "organic_impressions",
            value=Decimal("0"),
        ),
        command,
        "KPI-014",
    )
    assert row.availability is KpiAvailability.UNAVAILABLE
    assert row.value is None
    assert row.unavailable_reason is UnavailableReason.ZERO_DENOMINATOR


def test_negative_denominator_is_invalid_not_a_negative_rate(
    fixture_bytes: bytes, command: KpiCalculationCommand
) -> None:
    row = _row(
        _frame_with(
            fixture_bytes,
            command,
            "trailing_monthly_confirmed_contribution_jpy",
            value=Decimal("-1"),
        ),
        command,
        "KPI-023",
    )
    assert row.unavailable_reason is UnavailableReason.INVALID_NUMERIC_INPUT


def test_attribution_mismatch_and_unverified_are_distinct(
    fixture_bytes: bytes, command: KpiCalculationCommand
) -> None:
    mismatch = _row(
        _frame_with(
            fixture_bytes,
            command,
            "confirmed_attributed_commission_jpy",
            attribution_basis=AttributionBasis.PROVIDER_FACT,
        ),
        command,
        "KPI-003",
    )
    assert mismatch.unavailable_reason is UnavailableReason.ATTRIBUTION_BASIS_MISMATCH
    unverified = _row(
        _frame_with(
            fixture_bytes,
            command,
            "confirmed_attributed_commission_jpy",
            attribution_verified=False,
        ),
        command,
        "KPI-003",
    )
    assert unverified.unavailable_reason is UnavailableReason.ATTRIBUTION_UNVERIFIED


def test_provider_total_cannot_be_arbitrarily_allocated_to_article(
    fixture_bytes: bytes, command: KpiCalculationCommand
) -> None:
    row = _row(
        _frame_with(
            fixture_bytes,
            command,
            "confirmed_article_commission_jpy",
            attribution_basis=AttributionBasis.PROVIDER_FACT,
        ),
        command,
        "KPI-022",
    )
    assert row.availability is KpiAvailability.UNAVAILABLE
    assert row.unavailable_reason is UnavailableReason.ATTRIBUTION_BASIS_MISMATCH


def test_selected_basis_must_match_all_attributed_inputs(
    fixture_bytes: bytes, command: KpiCalculationCommand
) -> None:
    batch = RecordedKpiInputAdapter(fixture_bytes).read(command)
    estimated_context = CalculationContext(
        command.context.period,
        command.context.program_id,
        AttributionBasis.ESTIMATED,
    )
    rows = calculate_rows(batch.input_frame, estimated_context)
    assert rows[2].unavailable_reason is UnavailableReason.ATTRIBUTION_BASIS_MISMATCH
    assert rows[23].unavailable_reason is UnavailableReason.ATTRIBUTION_BASIS_MISMATCH


def test_learning_content_hour_obeys_same_attribution_and_maturity_gates(
    fixture_bytes: bytes, command: KpiCalculationCommand
) -> None:
    frame = _frame_with(
        fixture_bytes,
        command,
        "content_work_minutes",
        cohort_state=CohortState.IMMATURE,
    )
    rows = calculate_rows(frame, command.context)
    learning = calculate_learning_rows(rows, frame, command.context)[4]
    assert learning.metric_id == "confirmed_reward_per_content_hour"
    assert learning.availability is KpiAvailability.UNAVAILABLE
    assert learning.value is None
    assert learning.unavailable_reason is UnavailableReason.IMMATURE_COHORT
    assert learning.recommendation_order_effect is False


def test_float_boolean_and_nonfinite_decimal_never_enter_input_model(
    command: KpiCalculationCommand,
) -> None:
    common = {
        "metric_key": "bad_metric",
        "source": InputSource.FIRST_PARTY_EVENT,
        "period": command.context.period,
        "program_id": command.context.program_id,
        "verified": True,
        "cohort_state": CohortState.NOT_APPLICABLE,
        "attribution_basis": AttributionBasis.NOT_APPLICABLE,
        "attribution_verified": False,
    }
    for value in (1.5, True, Decimal("NaN"), Decimal("Infinity")):
        with pytest.raises(KpiFailure):
            MetricObservation(value=value, **common)  # type: ignore[arg-type]


def test_duplicate_metric_key_is_rejected(
    fixture_bytes: bytes, command: KpiCalculationCommand
) -> None:
    batch = RecordedKpiInputAdapter(fixture_bytes).read(command)
    with pytest.raises(KpiFailure) as captured:
        KpiInputFrame(
            (batch.input_frame.observations[0], batch.input_frame.observations[0])
        )
    assert captured.value.code is KpiFailureCode.DUPLICATE_INPUT

"""Formula reproduction and immutable read-model tests for ST-1205."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from raos.adapters.recorded_kpi_input import RecordedKpiInputAdapter
from raos.domain.analytics.kpi_read_model import (
    AttributionBasis,
    KPI_CALCULATION_VERSION,
    KPI_DEFINITION_VERSION,
    KPI_IDS,
    KpiAvailability,
    KpiBoundaryStatus,
    KpiCalculationCommand,
    KpiInputFrame,
    KpiReadModelSnapshot,
)


def test_golden_fixture_reproduces_all_thirty_canonical_formulas(
    snapshot: KpiReadModelSnapshot, fixture_document: dict[str, Any]
) -> None:
    expected = {
        row["kpi_id"]: row["value"] for row in fixture_document["expected_results"]
    }
    assert tuple(row.kpi_id for row in snapshot.rows) == KPI_IDS
    assert len(snapshot.rows) == 30
    assert all(row.availability is KpiAvailability.AVAILABLE for row in snapshot.rows)
    assert {row.kpi_id: str(row.value) for row in snapshot.rows} == expected


def test_every_result_is_exact_decimal_with_version_and_basis(
    snapshot: KpiReadModelSnapshot,
) -> None:
    for row in snapshot.rows:
        assert type(row.value) is Decimal
        assert row.value.is_finite()
        assert row.definition_version == KPI_DEFINITION_VERSION
        assert row.calculation_version == KPI_CALCULATION_VERSION
        assert row.period == snapshot.context.period
        assert row.program_id == snapshot.context.program_id
        assert row.input_keys
        assert row.freshness == "RECORDED_SYNTHETIC"
        assert row.last_successful_import == "RECORDED_FIXTURE_ONLY"
    assert snapshot.rows[0].attribution_basis is AttributionBasis.PROVIDER_FACT
    assert snapshot.rows[2].attribution_basis is AttributionBasis.DIRECT
    assert snapshot.rows[4].attribution_basis is AttributionBasis.NOT_APPLICABLE
    assert snapshot.rows[9].attribution_basis is AttributionBasis.DIRECT
    assert snapshot.rows[10].attribution_basis is AttributionBasis.UNATTRIBUTED


def test_verified_zero_is_a_real_zero_not_unavailable(
    snapshot: KpiReadModelSnapshot,
) -> None:
    critical_rate = snapshot.rows[18]
    assert critical_rate.kpi_id == "KPI-019"
    assert critical_rate.availability is KpiAvailability.AVAILABLE
    assert critical_rate.value == Decimal("0.000000")
    assert critical_rate.unavailable_reason is None


def test_learning_metrics_reproduce_and_never_affect_recommendation_order(
    snapshot: KpiReadModelSnapshot, fixture_document: dict[str, Any]
) -> None:
    expected = {
        row["metric_id"]: row["value"]
        for row in fixture_document["expected_learning_results"]
    }
    assert {row.metric_id: str(row.value) for row in snapshot.learning_rows} == expected
    assert [row.source_kpi_id for row in snapshot.learning_rows] == [
        "KPI-014",
        "KPI-006",
        "KPI-003",
        "KPI-008",
        None,
    ]
    assert all(
        row.recommendation_order_effect is False for row in snapshot.learning_rows
    )


def test_snapshot_is_strictly_local_and_nonattesting(
    snapshot: KpiReadModelSnapshot,
) -> None:
    assert snapshot.execution is KpiBoundaryStatus.RECORDED_FIXTURE_ONLY
    assert snapshot.read_model is KpiBoundaryStatus.IN_MEMORY_ONLY
    assert snapshot.persistence is KpiBoundaryStatus.NOT_EXECUTED
    assert snapshot.provider is KpiBoundaryStatus.NOT_EXECUTED
    assert snapshot.network is KpiBoundaryStatus.NOT_EXECUTED
    assert snapshot.public_projection is KpiBoundaryStatus.NOT_EXECUTED
    assert snapshot.recommendation_input is KpiBoundaryStatus.DISABLED
    assert snapshot.formal_tst_030 is KpiBoundaryStatus.NOT_EXECUTED
    assert snapshot.decision is KpiBoundaryStatus.NOT_READY


def test_input_digest_is_deterministic_and_order_independent(
    snapshot: KpiReadModelSnapshot,
    fixture_bytes: bytes,
    command: KpiCalculationCommand,
) -> None:
    batch = RecordedKpiInputAdapter(fixture_bytes).read(command)
    assert len(snapshot.input_digest.value) == 64
    assert snapshot.input_digest == batch.input_frame.sha256
    assert (
        snapshot.input_digest
        == KpiInputFrame(tuple(reversed(batch.input_frame.observations))).sha256
    )

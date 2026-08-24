"""Deterministic calculation and fail-closed tests for ST-1604 V2."""

from __future__ import annotations

from dataclasses import replace

import pytest

from raos.domain.ops.performance_load import (
    CapacityClassification,
    LoadEvidenceSource,
    LoadReportStatus,
    LoadSurface,
    MetricAvailability,
    PerformanceLoadFailure,
    PerformanceLoadFailureCode,
    SurfaceEvaluationStatus,
    SurfaceObservation,
    evaluate_performance_load,
    nearest_rank,
)


def test_fixed_fixture_documents_all_four_local_capacities(
    perf_request: object,
) -> None:
    report = evaluate_performance_load(perf_request)  # type: ignore[arg-type]
    assert report.report_status is LoadReportStatus.LOCAL_CAPACITY_DOCUMENTED
    assert tuple(row.surface for row in report.evaluations) == tuple(LoadSurface)
    assert all(
        row.status is SurfaceEvaluationStatus.LOCAL_BUDGET_MET
        and row.capacity_classification
        is CapacityClassification.SYNTHETIC_LOCAL_ONLY_NOT_PRODUCTION_CAPACITY
        and row.cost_microunits is None
        and row.cost_availability is MetricAvailability.UNAVAILABLE
        for row in report.evaluations
    )
    assert report.action_count == 0
    document = report.as_dict()
    assert document["formal_tst_027"] == "NOT_EXECUTED"
    assert document["canonical_slo_evaluation"] == (
        "NOT_EVALUATED_TST_027_STAGING_REQUIRED"
    )
    assert document["production_capacity_claim"] is None
    assert document["production_eligible"] is False
    assert set(document["action_counts"].values()) == {0}  # type: ignore[union-attr]


def test_nearest_rank_is_integer_exact_and_deterministic() -> None:
    values = tuple(range(1, 101))
    assert nearest_rank(values, 95) == 95
    assert nearest_rank(tuple(reversed(values)), 99) == 99
    with pytest.raises(PerformanceLoadFailure) as caught:
        nearest_rank((), 95)
    assert caught.value.code is PerformanceLoadFailureCode.INVALID_ARGUMENT


def test_breach_is_reported_without_promoting_to_slo_or_capacity(
    perf_request: object,
) -> None:
    typed = perf_request  # type: ignore[assignment]
    public = typed.observations[0]
    hostile = replace(
        public,
        successful_operations=0,
        duration_samples_ms=(10_000,) * public.operation_count,
    )
    report = evaluate_performance_load(
        replace(typed, observations=(hostile, *typed.observations[1:]))
    )
    assert report.report_status is LoadReportStatus.LOCAL_BUDGET_FAILED
    evaluation = report.evaluations[0]
    assert evaluation.status is SurfaceEvaluationStatus.LOCAL_BUDGET_BREACHED
    assert evaluation.breached_budgets == (
        "P95_DURATION",
        "P99_DURATION",
        "ERROR_RATE",
    )
    assert report.as_dict()["production_capacity_claim"] is None


def test_missing_surface_is_unavailable_not_zero(perf_request: object) -> None:
    typed = perf_request  # type: ignore[assignment]
    report = evaluate_performance_load(
        replace(typed, observations=typed.observations[:-1])
    )
    assert report.report_status is LoadReportStatus.DATA_BLOCKED
    worker = report.evaluations[-1]
    assert worker.surface is LoadSurface.WORKER
    assert worker.status is SurfaceEvaluationStatus.UNAVAILABLE
    assert worker.operation_count is None
    assert worker.p95_duration_ms is None
    assert worker.error_count is None
    assert worker.throughput_milliops_per_second is None
    assert worker.breached_budgets == ("MISSING_SURFACE_OBSERVATION",)


@pytest.mark.parametrize(
    "mutation",
    [
        {"concurrent_units": True},
        {"duration_ms": 0},
        {"successful_operations": -1},
        {"duration_samples_ms": ()},
        {"duration_samples_ms": (1.0,)},
    ],
)
def test_invalid_or_zero_denominator_samples_fail_closed(
    mutation: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "surface": LoadSurface.PUBLIC,
        "concurrent_units": 1,
        "duration_ms": 1_000,
        "successful_operations": 1,
        "duration_samples_ms": (1,),
        "max_db_connections": 1,
        "queue_age_samples_ms": None,
    }
    values.update(mutation)
    with pytest.raises(PerformanceLoadFailure) as caught:
        SurfaceObservation(**values)  # type: ignore[arg-type]
    assert caught.value.code is PerformanceLoadFailureCode.INVALID_ARGUMENT


def test_observed_zero_db_connections_is_available_not_missing() -> None:
    observation = SurfaceObservation(
        surface=LoadSurface.PUBLIC,
        concurrent_units=1,
        duration_ms=1_000,
        successful_operations=1,
        duration_samples_ms=(1,),
        max_db_connections=0,
        queue_age_samples_ms=None,
    )
    assert observation.max_db_connections == 0


def test_request_and_report_bytes_are_stable_and_ascii(
    perf_request: object,
) -> None:
    typed = perf_request  # type: ignore[assignment]
    report = evaluate_performance_load(typed)
    assert typed.canonical_bytes() == typed.canonical_bytes()
    assert report.canonical_bytes() == report.canonical_bytes()
    assert report.report_sha256 == report.report_sha256
    report.canonical_bytes().decode("ascii")
    forbidden = (b"price", b"reward", b"commission", b"epc", b"rpm", b"profit")
    lowered = report.canonical_bytes().lower()
    assert all(token not in lowered for token in forbidden)


def test_forged_report_or_evaluation_consistency_is_rejected(
    perf_request: object,
) -> None:
    report = evaluate_performance_load(perf_request)  # type: ignore[arg-type]
    with pytest.raises(PerformanceLoadFailure) as report_failure:
        replace(report, report_status=LoadReportStatus.DATA_BLOCKED)
    assert report_failure.value.code is PerformanceLoadFailureCode.INVALID_ARGUMENT
    with pytest.raises(PerformanceLoadFailure) as evaluation_failure:
        replace(report.evaluations[0], breached_budgets=("P95_DURATION",))
    assert evaluation_failure.value.code is PerformanceLoadFailureCode.INVALID_ARGUMENT


def test_recorded_capture_is_disabled_without_exact_artifact_readback_binding(
    perf_request: object,
) -> None:
    with pytest.raises(PerformanceLoadFailure) as caught:
        replace(
            perf_request,  # type: ignore[arg-type]
            evidence_source=LoadEvidenceSource.RECORDED_CAPTURE,
        )
    assert caught.value.code is PerformanceLoadFailureCode.RECORDED_CAPTURE_DISABLED

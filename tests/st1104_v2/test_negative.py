from __future__ import annotations

from dataclasses import replace
from typing import Callable, NoReturn, cast

import pytest

from raos.adapters.recorded_analytics_finance_dashboard import (
    RecordedAnalyticsFinanceDashboardAdapter,
)
from raos.adapters.recorded_unit_economics import RecordedUnitEconomicsScenario
from raos.application.analytics.analytics_finance_dashboard import (
    AnalyticsFinanceDashboardService,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.analytics.analytics_finance_dashboard import (
    DashboardDigest,
    DashboardFailure,
    DashboardFailureCode,
    MetricAvailability,
    RecordedDashboardCommand,
)
from raos.domain.analytics.kpi_read_model import (
    KpiAvailability,
    KpiReadModelSnapshot,
    UnavailableReason,
)
from raos.domain.finance.unit_economics import UnitEconomicsRunResult
from raos.ports.analytics_finance_dashboard import (
    RecordedAnalyticsFinanceDashboardPort,
)

from .conftest import build_snapshot


def failure_code(action: Callable[[], object]) -> DashboardFailureCode:
    with pytest.raises(DashboardFailure) as captured:
        action()
    assert str(captured.value) == captured.value.code.value
    assert "{" not in str(captured.value)
    return captured.value.code


@pytest.mark.parametrize(
    "reason",
    [
        UnavailableReason.MISSING_INPUT,
        UnavailableReason.UNVERIFIED_INPUT,
        UnavailableReason.ZERO_DENOMINATOR,
    ],
)
def test_upstream_unavailable_reason_never_becomes_zero(
    reason: UnavailableReason,
    fixture_bytes: bytes,
    kpi_snapshot: KpiReadModelSnapshot,
    unit_scenario: RecordedUnitEconomicsScenario,
    unit_result: UnitEconomicsRunResult,
    command: RecordedDashboardCommand,
) -> None:
    target = next(
        index for index, row in enumerate(kpi_snapshot.rows) if row.kpi_id == "KPI-012"
    )
    rows = list(kpi_snapshot.rows)
    rows[target] = replace(
        rows[target],
        availability=KpiAvailability.UNAVAILABLE,
        value=None,
        unavailable_reason=reason,
    )
    changed = replace(kpi_snapshot, rows=tuple(rows))
    snapshot = build_snapshot(
        fixture_bytes=fixture_bytes,
        kpi_snapshot=changed,
        unit_scenario=unit_scenario,
        unit_result=unit_result,
        command=command,
    )
    metric = snapshot.screens[0].metric_rows[0]
    assert metric.availability is MetricAvailability.UNAVAILABLE
    assert metric.value is None
    assert metric.unavailable_reason == reason.value


def test_fixture_hash_and_duplicate_keys_fail_closed(
    fixture_bytes: bytes,
    kpi_snapshot: KpiReadModelSnapshot,
    unit_scenario: RecordedUnitEconomicsScenario,
    unit_result: UnitEconomicsRunResult,
    command: RecordedDashboardCommand,
) -> None:
    adapter = RecordedAnalyticsFinanceDashboardAdapter(
        fixture_bytes=fixture_bytes + b" ",
        kpi_snapshot=kpi_snapshot,
        unit_request=unit_scenario.request,
        unit_result=unit_result,
    )
    assert (
        failure_code(lambda: adapter.read(command))
        is DashboardFailureCode.FIXTURE_HASH_MISMATCH
    )

    duplicate = fixture_bytes.replace(
        b'{\n  "schema_version": "2.0.0",',
        b'{\n  "schema_version": "2.0.0",\n  "schema_version": "2.0.0",',
        1,
    )
    rebound = replace(
        command,
        fixture_sha256=DashboardDigest.of(duplicate),
        fixture_bytes=len(duplicate),
    )
    duplicate_adapter = RecordedAnalyticsFinanceDashboardAdapter(
        fixture_bytes=duplicate,
        kpi_snapshot=kpi_snapshot,
        unit_request=unit_scenario.request,
        unit_result=unit_result,
    )
    assert (
        failure_code(lambda: duplicate_adapter.read(rebound))
        is DashboardFailureCode.FIXTURE_INVALID
    )


def test_dependency_hash_mismatch_fails_closed(
    fixture_bytes: bytes,
    kpi_snapshot: KpiReadModelSnapshot,
    unit_scenario: RecordedUnitEconomicsScenario,
    unit_result: UnitEconomicsRunResult,
    command: RecordedDashboardCommand,
) -> None:
    mismatched = replace(
        command,
        expected_kpi_input_sha256=DashboardDigest("0" * 64),
    )
    adapter = RecordedAnalyticsFinanceDashboardAdapter(
        fixture_bytes=fixture_bytes,
        kpi_snapshot=kpi_snapshot,
        unit_request=unit_scenario.request,
        unit_result=unit_result,
    )
    assert (
        failure_code(lambda: adapter.read(mismatched))
        is DashboardFailureCode.SOURCE_MISMATCH
    )


@pytest.mark.parametrize(
    "environment",
    [
        RuntimeEnvironment.INTEGRATION,
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.PRODUCTION,
    ],
)
def test_nonlocal_environment_cannot_create_service(
    environment: RuntimeEnvironment,
) -> None:
    class Source:
        def read(self, command: RecordedDashboardCommand) -> NoReturn:
            del command
            raise AssertionError("must not execute")

    assert (
        failure_code(
            lambda: AnalyticsFinanceDashboardService(
                environment=environment,
                source=cast(RecordedAnalyticsFinanceDashboardPort, Source()),
            )
        )
        is DashboardFailureCode.LOCAL_ENVIRONMENT_REQUIRED
    )


def test_port_exception_is_redacted(command: RecordedDashboardCommand) -> None:
    class Source:
        def read(self, candidate: RecordedDashboardCommand) -> NoReturn:
            del candidate
            raise RuntimeError("private provider row")

    service = AnalyticsFinanceDashboardService(
        environment=RuntimeEnvironment.CI,
        source=cast(RecordedAnalyticsFinanceDashboardPort, Source()),
    )
    assert (
        failure_code(lambda: service.execute(command))
        is DashboardFailureCode.RECORDED_SOURCE_UNAVAILABLE
    )

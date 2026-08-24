from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
for candidate in (ROOT / "python", ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


from raos.adapters.recorded_analytics_finance_dashboard import (  # noqa: E402
    RecordedAnalyticsFinanceDashboardAdapter,
)
from raos.adapters.recorded_kpi_input import (  # noqa: E402
    COMPLETE_FIXTURE_BYTES,
    COMPLETE_FIXTURE_SHA256,
    RecordedKpiInputAdapter,
)
from raos.adapters.recorded_unit_economics import (  # noqa: E402
    RecordedUnitEconomicsAdapter,
    RecordedUnitEconomicsScenario,
    load_recorded_unit_economics_fixture,
)
from raos.application.analytics.analytics_finance_dashboard import (  # noqa: E402
    AnalyticsFinanceDashboardService,
)
from raos.application.analytics.kpi_read_model import (  # noqa: E402
    RecordedKpiCalculationJob,
)
from raos.application.finance.unit_economics import UnitEconomicsService  # noqa: E402
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.analytics.analytics_finance_dashboard import (  # noqa: E402
    AnalyticsFinanceDashboardSnapshot,
    DashboardDigest,
    RecordedDashboardCommand,
)
from raos.domain.analytics.kpi_read_model import (  # noqa: E402
    AttributionBasis,
    CalculationContext,
    COMPLETE_RECORDED_INPUT_SHA256,
    FixtureByteLength,
    KpiCalculationCommand,
    KpiReadModelSnapshot,
    MeasurementPeriod,
    ProgramId,
    RAKUTEN_BLOG_PROGRAM,
    Sha256Digest,
)
from raos.domain.finance.unit_economics import UnitEconomicsRunResult  # noqa: E402
from scripts import build_st1303_attribution_engine as st1303  # noqa: E402
from scripts import build_st1104_analytics_finance_dashboard as builder  # noqa: E402


@pytest.fixture(scope="session")
def fixture_bytes() -> bytes:
    return (ROOT / builder.FIXTURE_PATH).read_bytes()


@pytest.fixture(scope="session")
def kpi_snapshot() -> KpiReadModelSnapshot:
    fixture = (ROOT / builder.ST1205_FIXTURE_PATH).read_bytes()
    command = KpiCalculationCommand(
        recording_id="complete",
        fixture_digest=Sha256Digest(COMPLETE_FIXTURE_SHA256),
        fixture_length=FixtureByteLength(COMPLETE_FIXTURE_BYTES),
        expected_input_digest=Sha256Digest(COMPLETE_RECORDED_INPUT_SHA256),
        context=CalculationContext(
            MeasurementPeriod(date(2026, 7, 1), date(2026, 7, 31)),
            ProgramId(RAKUTEN_BLOG_PROGRAM),
            AttributionBasis.DIRECT,
        ),
    )
    return RecordedKpiCalculationJob(
        exchange=RecordedKpiInputAdapter(fixture)
    ).calculate(command)


@pytest.fixture(scope="session")
def unit_scenario() -> RecordedUnitEconomicsScenario:
    contract = st1303.load_contract(ROOT)[1]
    return load_recorded_unit_economics_fixture(
        (ROOT / builder.ST1304_FIXTURE_PATH).resolve(),
        attribution_fixture_path=(ROOT / builder.ST1303_FIXTURE_PATH).resolve(),
        contract=contract,
    )


@pytest.fixture(scope="session")
def unit_result(unit_scenario: RecordedUnitEconomicsScenario) -> UnitEconomicsRunResult:
    return UnitEconomicsService(
        environment=RuntimeEnvironment.CI,
        runner=RecordedUnitEconomicsAdapter(),
    ).execute(unit_scenario.request)


@pytest.fixture()
def command(
    fixture_bytes: bytes,
    kpi_snapshot: KpiReadModelSnapshot,
    unit_scenario: RecordedUnitEconomicsScenario,
    unit_result: UnitEconomicsRunResult,
) -> RecordedDashboardCommand:
    return RecordedDashboardCommand(
        fixture_sha256=DashboardDigest.of(fixture_bytes),
        fixture_bytes=len(fixture_bytes),
        expected_kpi_input_sha256=DashboardDigest(kpi_snapshot.input_digest.value),
        expected_unit_input_sha256=DashboardDigest(
            unit_scenario.request.input_sha256.value
        ),
        expected_unit_result_sha256=DashboardDigest(unit_result.result_sha256.value),
    )


def build_snapshot(
    *,
    fixture_bytes: bytes,
    kpi_snapshot: KpiReadModelSnapshot,
    unit_scenario: RecordedUnitEconomicsScenario,
    unit_result: UnitEconomicsRunResult,
    command: RecordedDashboardCommand,
) -> AnalyticsFinanceDashboardSnapshot:
    adapter = RecordedAnalyticsFinanceDashboardAdapter(
        fixture_bytes=fixture_bytes,
        kpi_snapshot=kpi_snapshot,
        unit_request=unit_scenario.request,
        unit_result=unit_result,
    )
    return AnalyticsFinanceDashboardService(
        environment=RuntimeEnvironment.CI,
        source=adapter,
    ).execute(command)


@pytest.fixture()
def snapshot(
    fixture_bytes: bytes,
    kpi_snapshot: KpiReadModelSnapshot,
    unit_scenario: RecordedUnitEconomicsScenario,
    unit_result: UnitEconomicsRunResult,
    command: RecordedDashboardCommand,
) -> AnalyticsFinanceDashboardSnapshot:
    return build_snapshot(
        fixture_bytes=fixture_bytes,
        kpi_snapshot=kpi_snapshot,
        unit_scenario=unit_scenario,
        unit_result=unit_result,
        command=command,
    )

"""ENV-DEV/CI application service for the ST-1104 headless read model."""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.analytics.analytics_finance_dashboard import (
    AnalyticsFinanceDashboardSnapshot,
    DashboardFailure,
    DashboardFailureCode,
    RecordedDashboardCommand,
    RecordedDashboardSources,
    build_analytics_finance_dashboard,
    fail_dashboard,
)
from raos.ports.analytics_finance_dashboard import (
    RecordedAnalyticsFinanceDashboardPort,
)


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except Exception:
        return False


@final
class AnalyticsFinanceDashboardService:
    """Build a pure dashboard snapshot around one recorded port invocation."""

    __slots__ = ("_source",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        source: RecordedAnalyticsFinanceDashboardPort,
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or not _implements(
                cast(object, source), RecordedAnalyticsFinanceDashboardPort
            )
        ):
            fail_dashboard(DashboardFailureCode.LOCAL_ENVIRONMENT_REQUIRED)
        self._source = source

    def execute(
        self, command: RecordedDashboardCommand
    ) -> AnalyticsFinanceDashboardSnapshot:
        if type(command) is not RecordedDashboardCommand:
            fail_dashboard()
        observed: object = None
        try:
            observed = self._source.read(command)
        except DashboardFailure:
            raise
        except Exception:
            fail_dashboard(DashboardFailureCode.RECORDED_SOURCE_UNAVAILABLE)
        if type(observed) is not RecordedDashboardSources:
            fail_dashboard(DashboardFailureCode.SOURCE_MISMATCH)
        if (
            observed.fixture_sha256 != command.fixture_sha256
            or observed.kpi_snapshot.input_digest.value
            != command.expected_kpi_input_sha256.value
            or observed.unit_request.input_sha256.value
            != command.expected_unit_input_sha256.value
            or observed.unit_result.result_sha256.value
            != command.expected_unit_result_sha256.value
        ):
            fail_dashboard(DashboardFailureCode.SOURCE_MISMATCH)
        return build_analytics_finance_dashboard(observed)


__all__ = ("AnalyticsFinanceDashboardService",)

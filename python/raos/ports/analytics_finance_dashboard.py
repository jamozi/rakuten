"""Provider-neutral inward port for the ST-1104 recorded dashboard."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.analytics.analytics_finance_dashboard import (
    RecordedDashboardCommand,
    RecordedDashboardSources,
)


@runtime_checkable
class RecordedAnalyticsFinanceDashboardPort(Protocol):
    """Return one exact process-local synthetic source bundle."""

    def read(self, command: RecordedDashboardCommand) -> RecordedDashboardSources: ...


__all__ = ("RecordedAnalyticsFinanceDashboardPort",)

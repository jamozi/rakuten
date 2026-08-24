"""Credential-free inward port for one recorded ST-1205 input batch."""

from __future__ import annotations

from typing import Protocol

from raos.domain.analytics.kpi_read_model import (
    KpiCalculationCommand,
    RecordedKpiInputBatch,
)


class RecordedKpiInputExchange(Protocol):
    """Read one exact caller-bound synthetic batch without provider or storage I/O."""

    def read(self, command: KpiCalculationCommand) -> RecordedKpiInputBatch:
        """Return the one immutable recorded batch."""

        ...


__all__ = ["RecordedKpiInputExchange"]

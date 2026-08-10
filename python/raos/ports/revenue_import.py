"""Single inward port for the synthetic ST-1301 revenue dry run."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.finance.revenue_import import (
    SyntheticRevenueDryRun,
    SyntheticRevenueParseCommand,
)


@runtime_checkable
class RecordedRevenueParser(Protocol):
    """Parse exactly one caller-authorized synthetic fixture without persistence."""

    def parse(
        self, command: SyntheticRevenueParseCommand
    ) -> SyntheticRevenueDryRun: ...


__all__ = ["RecordedRevenueParser"]

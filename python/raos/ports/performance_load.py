"""Inward-only durable journal port for ST-1604 local reports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from raos.domain.ops.performance_load import PerformanceLoadReport


class PerformanceLoadWriteDisposition(StrEnum):
    APPENDED = "APPENDED"
    REPLAYED = "REPLAYED"


@dataclass(frozen=True, slots=True)
class PerformanceLoadReceipt:
    run_id: UUID
    report_sha256: str
    sequence: int
    previous_record_sha256: str
    record_sha256: str
    disposition: PerformanceLoadWriteDisposition


class PerformanceLoadJournalPort(Protocol):
    """Append one immutable report; no query, export, delete, or lifecycle API."""

    @property
    def action_count(self) -> int: ...

    def append(self, report: PerformanceLoadReport) -> PerformanceLoadReceipt: ...


__all__ = [
    "PerformanceLoadJournalPort",
    "PerformanceLoadReceipt",
    "PerformanceLoadWriteDisposition",
]

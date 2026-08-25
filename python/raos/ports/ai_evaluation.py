"""Read-only local bundle boundary for ST-0707."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.ai.evaluation_harness import RecordedEvaluationBundle


@runtime_checkable
class RecordedEvaluationBundleReader(Protocol):
    def get_bundle(self, bundle_id: str) -> RecordedEvaluationBundle | None: ...


__all__ = ["RecordedEvaluationBundleReader"]

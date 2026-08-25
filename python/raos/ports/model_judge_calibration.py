"""Provider/model-neutral inward read boundary for ST-1901."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.ai.model_judge_calibration import (
    JudgeCalibrationReadCommand,
    RecordedHumanLabelBatch,
)


@runtime_checkable
class RecordedHumanLabelReader(Protocol):
    def read(
        self, command: JudgeCalibrationReadCommand
    ) -> RecordedHumanLabelBatch | None: ...


__all__ = ["RecordedHumanLabelReader"]

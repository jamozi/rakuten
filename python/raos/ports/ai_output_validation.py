"""Read-only local case boundary for ST-0705."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.ai.output_validation import AiOutputValidationInput


@runtime_checkable
class AiOutputValidationCaseReader(Protocol):
    def get_case(self, case_id: str) -> AiOutputValidationInput | None: ...


__all__ = ["AiOutputValidationCaseReader"]

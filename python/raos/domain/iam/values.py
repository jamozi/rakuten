"""Exact immutable JSON wrappers for IAM physical jsonb columns."""

from __future__ import annotations

from dataclasses import dataclass

from raos.domain.shared.json_values import FrozenJsonObject


@dataclass(frozen=True, slots=True, repr=False)
class _ObjectJsonValue:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        if type(self.value) is not FrozenJsonObject:
            raise ValueError("INVALID_IAM_JSON_VALUE") from None

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted>)"


class BreakGlassRecordPermissionsJson(_ObjectJsonValue):
    __slots__ = ()


__all__ = [
    "BreakGlassRecordPermissionsJson",
]

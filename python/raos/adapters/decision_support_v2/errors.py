"""Closed typed adapter failures; caller material is never rendered."""

from __future__ import annotations

from enum import StrEnum


class AdapterFailure(StrEnum):
    TIMEOUT = "TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    DISABLED = "DISABLED"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


class AdapterError(RuntimeError):
    __slots__ = ("code",)

    def __init__(self, code: AdapterFailure) -> None:
        self.code = code
        super().__init__(code.value)

    def __repr__(self) -> str:
        return f"AdapterError(code={self.code.value})"


__all__ = ["AdapterError", "AdapterFailure"]

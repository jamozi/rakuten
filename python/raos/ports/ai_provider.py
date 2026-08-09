"""Inward ports for provider-neutral structured model execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from raos.domain.ai.provider import (
    ArtifactRef,
    CanonicalJsonObject,
    PricingResult,
    ProviderResult,
    ProviderUsage,
    Sha256Digest,
    StructuredTaskRequest,
    SyntheticPricingQuote,
)

_MAX_PROVIDER_EXCHANGE_BYTES = 4 * 1024 * 1024


class ProviderErrorCode(str, Enum):
    """Stable sanitized classifications exposed across the inward boundary."""

    RATE_LIMIT = "RATE_LIMIT"
    TIMEOUT = "TIMEOUT"
    AUTHENTICATION = "AUTHENTICATION"
    PERMISSION = "PERMISSION"
    INVALID_REQUEST = "INVALID_REQUEST"
    SERVER_ERROR = "SERVER_ERROR"
    UNAVAILABLE = "UNAVAILABLE"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    UNKNOWN = "UNKNOWN"
    RECORDER_FAILURE = "RECORDER_FAILURE"
    PRICING_MISSING = "PRICING_MISSING"
    PRICING_MISMATCH = "PRICING_MISMATCH"
    ROUTE_MISMATCH = "ROUTE_MISMATCH"
    INVALID_SCHEMA = "INVALID_SCHEMA"


_RETRYABLE_BY_CODE = MappingProxyType(
    {
        ProviderErrorCode.RATE_LIMIT: True,
        ProviderErrorCode.TIMEOUT: True,
        ProviderErrorCode.AUTHENTICATION: False,
        ProviderErrorCode.PERMISSION: False,
        ProviderErrorCode.INVALID_REQUEST: False,
        ProviderErrorCode.SERVER_ERROR: True,
        ProviderErrorCode.UNAVAILABLE: True,
        ProviderErrorCode.MALFORMED_RESPONSE: False,
        ProviderErrorCode.UNKNOWN: False,
        ProviderErrorCode.RECORDER_FAILURE: False,
        ProviderErrorCode.PRICING_MISSING: False,
        ProviderErrorCode.PRICING_MISMATCH: False,
        ProviderErrorCode.ROUTE_MISMATCH: False,
        ProviderErrorCode.INVALID_SCHEMA: False,
    }
)


class ProviderError(RuntimeError):
    """Sanitized stable provider failure with no raw exception retention."""

    __slots__ = ("_sealed", "_stable_code")
    _sealed: bool
    _stable_code: ProviderErrorCode

    def __init__(self, stable_code: ProviderErrorCode) -> None:
        if type(stable_code) is not ProviderErrorCode:
            raise TypeError("stable_code must be an exact ProviderErrorCode")
        super().__init__()
        object.__setattr__(self, "_stable_code", stable_code)
        object.__setattr__(self, "_sealed", True)

    @property
    def stable_code(self) -> ProviderErrorCode:
        return self._stable_code

    @property
    def retryable(self) -> bool:
        return _RETRYABLE_BY_CODE[self._stable_code]

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("ProviderError is immutable")
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("ProviderError is immutable")
        super().__delattr__(name)

    def __repr__(self) -> str:
        return (
            "ProviderError("
            f"stable_code={self.stable_code!r}, retryable={self.retryable!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ProviderExchange:
    """Exact allowlisted provider exchange bytes passed to artifact recording."""

    canonical_bytes: bytes = field(repr=False)
    sha256: Sha256Digest

    def __post_init__(self) -> None:
        if type(self.canonical_bytes) is not bytes:
            raise ValueError("canonical_bytes must be exact bytes")
        if (
            not self.canonical_bytes
            or len(self.canonical_bytes) > _MAX_PROVIDER_EXCHANGE_BYTES
        ):
            raise ValueError("canonical_bytes must be exact non-empty bytes")
        snapshot = bytes(self.canonical_bytes)
        if type(self.sha256) is not Sha256Digest:
            raise ValueError("sha256 must be an exact Sha256Digest")
        parse_failed = False
        canonical_snapshot = b""
        try:
            canonical_snapshot = CanonicalJsonObject.from_bytes(
                snapshot
            ).canonical_bytes()
        except ValueError:
            parse_failed = True
        if parse_failed or canonical_snapshot != snapshot:
            snapshot = b""
            canonical_snapshot = b""
            raise ValueError(
                "canonical_bytes must be canonical strict JSON object bytes"
            ) from None
        if Sha256Digest.of(snapshot) != self.sha256:
            raise ValueError("canonical_bytes do not match sha256")
        object.__setattr__(self, "canonical_bytes", snapshot)

    def __repr__(self) -> str:
        return f"ProviderExchange(canonical_bytes=<redacted>, sha256={self.sha256!r})"


@runtime_checkable
class ProviderExchangeRecorder(Protocol):
    """Record one exact exchange through an outward persistence collaborator."""

    def record(self, exchange: ProviderExchange) -> ArtifactRef:
        """Return the immutable reference created for the exact exchange bytes."""

        ...


@runtime_checkable
class RecordedCostCalculator(Protocol):
    """Calculate cost only from recorded usage and an immutable synthetic quote."""

    def calculate(
        self,
        *,
        usage: ProviderUsage,
        provider: str,
        model_id: str,
        quote: SyntheticPricingQuote,
        evaluated_at: datetime,
    ) -> PricingResult:
        """Return a quote-bound deterministic pricing result."""

        ...


@runtime_checkable
class StructuredModelProvider(Protocol):
    """Execute one structured request without exposing provider SDK types."""

    def execute(self, request: StructuredTaskRequest) -> ProviderResult:
        """Return a recorded outcome or raise one sanitized ProviderError."""

        ...


__all__ = [
    "ProviderError",
    "ProviderErrorCode",
    "ProviderExchange",
    "ProviderExchangeRecorder",
    "RecordedCostCalculator",
    "StructuredModelProvider",
]

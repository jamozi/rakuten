"""Deterministic local collaborators for recorded AI provider execution."""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, localcontext
from threading import Lock
from uuid import UUID, uuid5

from raos.domain.ai.provider import (
    ArtifactRef,
    PricingResult,
    ProviderUsage,
    Sha256Digest,
    SyntheticPricingQuote,
)
from raos.ports.ai_provider import ProviderExchange


_ARTIFACT_NAMESPACE = UUID("a6ac02c7-2f99-41dd-a918-8c54633e2f1d")
_MILLION = Decimal(1_000_000)
_MAX_SIGNED_BIGINT = (1 << 63) - 1


class InMemoryProviderExchangeRecorder:
    """Thread-safe immutable recorder used by recorded tests and local execution.

    This adapter deliberately stores only the already-sanitized canonical exchange
    supplied through the inward port. It is not the production ST-0601 artifact
    registry and never writes to a database, object store, or network endpoint.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._content_by_digest: dict[str, bytes] = {}
        self._reference_by_digest: dict[str, ArtifactRef] = {}
        self._record_calls = 0

    @property
    def record_calls(self) -> int:
        with self._lock:
            return self._record_calls

    def record(self, exchange: ProviderExchange) -> ArtifactRef:
        if type(exchange) is not ProviderExchange:
            raise TypeError("exchange must be an exact ProviderExchange")
        content = bytes(exchange.canonical_bytes)
        digest = exchange.sha256.value
        if Sha256Digest.of(content) != exchange.sha256:
            raise ValueError("exchange content and digest do not match")
        with self._lock:
            self._record_calls += 1
            existing = self._content_by_digest.get(digest)
            if existing is not None and existing != content:
                raise ValueError("one digest cannot identify different exchange bytes")
            reference = self._reference_by_digest.get(digest)
            if reference is None:
                reference = ArtifactRef(
                    artifact_id=uuid5(_ARTIFACT_NAMESPACE, digest),
                    sha256=exchange.sha256,
                    uri=f"file://recorded/{digest}.json",
                    content_type="application/json",
                    byte_size=len(content),
                )
                self._content_by_digest[digest] = content
                self._reference_by_digest[digest] = reference
            return reference

    def read(self, reference: ArtifactRef) -> bytes:
        if type(reference) is not ArtifactRef:
            raise TypeError("reference must be an exact ArtifactRef")
        with self._lock:
            content = self._content_by_digest.get(reference.sha256.value)
            if content is None:
                raise KeyError("recorded exchange does not exist")
            return bytes(content)


class SyntheticRecordedCostCalculator:
    """Calculate deterministic fixture cost from usage and a synthetic quote."""

    def calculate(
        self,
        usage: ProviderUsage,
        quote: SyntheticPricingQuote,
    ) -> PricingResult:
        if type(usage) is not ProviderUsage:
            raise TypeError("usage must be an exact ProviderUsage")
        if type(quote) is not SyntheticPricingQuote:
            raise TypeError("quote must be an exact SyntheticPricingQuote")
        regular_input_tokens = usage.input_tokens - usage.cached_input_tokens
        with localcontext() as context:
            context.prec = 50
            provider_cost = (
                Decimal(regular_input_tokens) * quote.input_per_million
                + Decimal(usage.cached_input_tokens) * quote.cached_input_per_million
                + Decimal(usage.output_tokens) * quote.output_per_million
            ) / _MILLION
            estimated_jpy_decimal = (
                provider_cost * quote.jpy_per_native_unit
            ).to_integral_value(rounding=ROUND_CEILING)
        if estimated_jpy_decimal < 0 or estimated_jpy_decimal > _MAX_SIGNED_BIGINT:
            raise ValueError("calculated JPY cost exceeds the supported range")
        return PricingResult(
            estimated_cost_jpy=int(estimated_jpy_decimal),
            provider_cost_native=provider_cost,
            native_currency=quote.native_currency,
            quote_id=quote.quote_id,
            quote_sha256=quote.quote_sha256,
        )


__all__ = [
    "InMemoryProviderExchangeRecorder",
    "SyntheticRecordedCostCalculator",
]

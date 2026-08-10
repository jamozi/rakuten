"""Deterministic local collaborators for recorded AI provider execution."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Context, Decimal, ROUND_CEILING, ROUND_HALF_EVEN, localcontext
from threading import Lock
from uuid import UUID, uuid5

from raos.domain.ai.provider import (
    ArtifactRef,
    PricingResult,
    ProviderUsage,
    Sha256Digest,
    SyntheticPricingQuote,
    synthetic_pricing_calculation_sha256,
    synthetic_quote_sha256,
    synthetic_usage_sha256,
)
from raos.ports.ai_provider import ProviderError, ProviderErrorCode, ProviderExchange


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
                raise ProviderError(ProviderErrorCode.RECORDER_FAILURE) from None
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
        *,
        usage: ProviderUsage,
        provider: str,
        model_id: str,
        quote: SyntheticPricingQuote,
        evaluated_at: datetime,
    ) -> PricingResult:
        if type(usage) is not ProviderUsage:
            raise TypeError("usage must be an exact ProviderUsage")
        if type(provider) is not str or provider != "openai":
            raise ValueError("provider must be openai")
        if type(quote) is not SyntheticPricingQuote:
            raise TypeError("quote must be an exact SyntheticPricingQuote")
        if type(model_id) is not str or model_id != quote.model_id:
            raise ValueError("model_id must match the quote")
        if quote.provider != provider:
            raise ValueError("quote provider must match")
        expected_quote_sha256 = synthetic_quote_sha256(
            quote_id=quote.quote_id,
            provider=quote.provider,
            model_id=quote.model_id,
            native_currency=quote.native_currency,
            input_per_million=quote.input_per_million,
            cached_input_per_million=quote.cached_input_per_million,
            output_per_million=quote.output_per_million,
            jpy_per_native_unit=quote.jpy_per_native_unit,
            observed_at=quote.observed_at,
            expires_at=quote.expires_at,
        )
        if quote.quote_sha256 != expected_quote_sha256:
            raise ValueError("quote_sha256 does not match quote fields")
        if (
            type(evaluated_at) is not datetime
            or evaluated_at.tzinfo is None
            or evaluated_at.utcoffset() != timezone.utc.utcoffset(None)
        ):
            raise ValueError("evaluated_at must be an aware UTC datetime")
        evaluated_at = evaluated_at.replace(tzinfo=timezone.utc)
        if not quote.observed_at <= evaluated_at < quote.expires_at:
            raise ValueError("quote is outside its validity interval")
        regular_input_tokens = usage.input_tokens - usage.cached_input_tokens
        with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
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
        estimated_cost_jpy = int(estimated_jpy_decimal)
        usage_sha256 = synthetic_usage_sha256(usage)
        calculation_sha256 = synthetic_pricing_calculation_sha256(
            quote_sha256=quote.quote_sha256,
            usage_sha256=usage_sha256,
            provider=provider,
            model_id=model_id,
            evaluated_at=evaluated_at,
            provider_cost_native=provider_cost,
            native_currency=quote.native_currency,
            estimated_cost_jpy=estimated_cost_jpy,
        )
        return PricingResult(
            estimated_cost_jpy=estimated_cost_jpy,
            provider_cost_native=provider_cost,
            native_currency=quote.native_currency,
            quote_id=quote.quote_id,
            quote_sha256=quote.quote_sha256,
            provider=provider,
            model_id=model_id,
            usage_sha256=usage_sha256,
            evaluated_at=evaluated_at,
            calculation_sha256=calculation_sha256,
        )


__all__ = [
    "InMemoryProviderExchangeRecorder",
    "SyntheticRecordedCostCalculator",
]

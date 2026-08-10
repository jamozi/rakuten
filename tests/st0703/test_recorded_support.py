"""Unit tests for deterministic recorded-provider collaborators."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_FLOOR, localcontext
import json

import pytest

from raos.adapters.recorded_ai import (
    InMemoryProviderExchangeRecorder,
    SyntheticRecordedCostCalculator,
)
from raos.domain.ai.provider import (
    CanonicalJsonObject,
    ProviderUsage,
    Sha256Digest,
    SyntheticPricingQuote,
    calculate_synthetic_pricing_reference,
    synthetic_usage_sha256,
)
from raos.ports.ai_provider import ProviderError, ProviderErrorCode, ProviderExchange


def _quote() -> SyntheticPricingQuote:
    return SyntheticPricingQuote(
        quote_id="st0703-synthetic-quote-v1",
        provider="openai",
        model_id="raos-synthetic-model-v1",
        native_currency="JPY",
        input_per_million=Decimal("81340"),
        cached_input_per_million=Decimal("486430"),
        output_per_million=Decimal("21700"),
        jpy_per_native_unit=Decimal("1"),
        observed_at=datetime(2026, 8, 6, tzinfo=timezone.utc),
        expires_at=datetime(2026, 8, 7, tzinfo=timezone.utc),
    )


@pytest.mark.parametrize(
    ("usage", "expected"),
    (
        (ProviderUsage(32, 11, 8), 7),
        (ProviderUsage(24, 6, 0), 3),
        (ProviderUsage(40, 128, 10), 11),
        (ProviderUsage(36, 17, 4), 5),
    ),
)
def test_synthetic_cost_matches_recorded_fixtures(
    usage: ProviderUsage,
    expected: int,
) -> None:
    result = SyntheticRecordedCostCalculator().calculate(
        usage=usage,
        provider="openai",
        model_id="raos-synthetic-model-v1",
        quote=_quote(),
        evaluated_at=datetime(2026, 8, 6, 0, 0, 10, tzinfo=timezone.utc),
    )

    assert result.estimated_cost_jpy == expected
    assert result.quote_id == "st0703-synthetic-quote-v1"
    assert result.quote_sha256 == _quote().quote_sha256


def test_synthetic_quote_usage_and_calculation_hashes_are_exact() -> None:
    quote = _quote()
    usage = ProviderUsage(
        input_tokens=32,
        output_tokens=11,
        cached_input_tokens=8,
    )
    evaluated_at = datetime(2026, 8, 6, 0, 0, 10, tzinfo=timezone.utc)

    result = calculate_synthetic_pricing_reference(
        usage=usage,
        provider="openai",
        model_id="raos-synthetic-model-v1",
        quote=quote,
        evaluated_at=evaluated_at,
    )

    assert quote.quote_sha256.value == (
        "45c23610b7cfc438ba71dc2a0931cc55c4035aba34c3484e119bb5c0a52f926b"
    )
    assert synthetic_usage_sha256(usage).value == (
        "f2c6a7fe009c8ef99b1e17f4812d6db14db1caa8b70cf896c391a46486cee194"
    )
    assert result.provider_cost_native.as_tuple() == Decimal("6.0823").as_tuple()
    assert result.estimated_cost_jpy == 7
    assert result.calculation_sha256.value == (
        "703a304def909d8bbc7a03e7266d83d816d7ce9d7459a487d931ce160710c0f4"
    )


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("input_per_million", Decimal("-0")),
        ("cached_input_per_million", 1.0),
        ("output_per_million", Decimal("1.23456789012345678901234567890123456789")),
        ("input_per_million", Decimal("1e-19")),
        ("output_per_million", Decimal("1e19")),
        ("jpy_per_native_unit", Decimal("0")),
    ),
)
def test_synthetic_quote_rejects_invalid_decimal_fields(
    field_name: str,
    value: object,
) -> None:
    values: dict[str, object] = {
        "quote_id": "st0703-synthetic-quote-v1",
        "provider": "openai",
        "model_id": "raos-synthetic-model-v1",
        "native_currency": "JPY",
        "input_per_million": Decimal("81340"),
        "cached_input_per_million": Decimal("486430"),
        "output_per_million": Decimal("21700"),
        "jpy_per_native_unit": Decimal("1"),
        "observed_at": datetime(2026, 8, 6, tzinfo=timezone.utc),
        "expires_at": datetime(2026, 8, 7, tzinfo=timezone.utc),
    }
    values[field_name] = value

    with pytest.raises(ValueError):
        SyntheticPricingQuote(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("observed_at", "expires_at"),
    (
        (
            datetime(2026, 8, 6),
            datetime(2026, 8, 7, tzinfo=timezone.utc),
        ),
        (
            datetime(2026, 8, 6, tzinfo=timezone.utc),
            datetime(2026, 8, 7),
        ),
        (
            datetime(2026, 8, 6, tzinfo=timezone.utc),
            datetime(2026, 8, 6, tzinfo=timezone.utc),
        ),
    ),
)
def test_synthetic_quote_rejects_invalid_validity_interval(
    observed_at: datetime,
    expires_at: datetime,
) -> None:
    with pytest.raises(ValueError):
        SyntheticPricingQuote(
            quote_id="st0703-synthetic-quote-v1",
            provider="openai",
            model_id="raos-synthetic-model-v1",
            native_currency="JPY",
            input_per_million=Decimal("1"),
            cached_input_per_million=Decimal("1"),
            output_per_million=Decimal("1"),
            jpy_per_native_unit=Decimal("1"),
            observed_at=observed_at,
            expires_at=expires_at,
        )


def test_synthetic_pricing_uses_cached_rate_ceiling_and_local_context() -> None:
    quote = SyntheticPricingQuote(
        quote_id="st0703-cached-ceiling-v1",
        provider="openai",
        model_id="raos-synthetic-model-v1",
        native_currency="JPY",
        input_per_million=Decimal("1000000"),
        cached_input_per_million=Decimal("100000"),
        output_per_million=Decimal("0"),
        jpy_per_native_unit=Decimal("1"),
        observed_at=datetime(2026, 8, 6, tzinfo=timezone.utc),
        expires_at=datetime(2026, 8, 7, tzinfo=timezone.utc),
    )
    usage = ProviderUsage(
        input_tokens=10,
        output_tokens=0,
        cached_input_tokens=4,
    )
    calculator = SyntheticRecordedCostCalculator()
    evaluated_at = datetime(2026, 8, 6, 1, tzinfo=timezone.utc)

    with localcontext() as ambient:
        ambient.prec = 3
        ambient.rounding = ROUND_FLOOR
        reference = calculate_synthetic_pricing_reference(
            usage=usage,
            provider="openai",
            model_id=quote.model_id,
            quote=quote,
            evaluated_at=evaluated_at,
        )
        calculated = calculator.calculate(
            usage=usage,
            provider="openai",
            model_id=quote.model_id,
            quote=quote,
            evaluated_at=evaluated_at,
        )

    assert reference == calculated
    assert reference.provider_cost_native.as_tuple() == Decimal("6.4").as_tuple()
    assert reference.estimated_cost_jpy == 7


def test_zero_pricing_is_valid_when_formula_is_exactly_zero() -> None:
    quote = SyntheticPricingQuote(
        quote_id="st0703-zero-v1",
        provider="openai",
        model_id="raos-synthetic-model-v1",
        native_currency="JPY",
        input_per_million=Decimal("0"),
        cached_input_per_million=Decimal("0"),
        output_per_million=Decimal("0"),
        jpy_per_native_unit=Decimal("1"),
        observed_at=datetime(2026, 8, 6, tzinfo=timezone.utc),
        expires_at=datetime(2026, 8, 7, tzinfo=timezone.utc),
    )

    result = calculate_synthetic_pricing_reference(
        usage=ProviderUsage(1, 1, 1),
        provider="openai",
        model_id=quote.model_id,
        quote=quote,
        evaluated_at=quote.observed_at,
    )

    assert result.provider_cost_native.as_tuple() == Decimal(0).as_tuple()
    assert result.estimated_cost_jpy == 0


def test_pricing_rejects_jpy_overflow_but_keeps_exact_large_native_amount() -> None:
    maximum_rate = Decimal("99999999999999999999.999999999999999999")
    quote = SyntheticPricingQuote(
        quote_id="st0703-large-native-v1",
        provider="openai",
        model_id="raos-synthetic-model-v1",
        native_currency="JPY",
        input_per_million=maximum_rate,
        cached_input_per_million=Decimal("0"),
        output_per_million=Decimal("0"),
        jpy_per_native_unit=Decimal("1e-18"),
        observed_at=datetime(2026, 8, 6, tzinfo=timezone.utc),
        expires_at=datetime(2026, 8, 7, tzinfo=timezone.utc),
    )
    usage = ProviderUsage((1 << 63) - 1, 0, 0)

    result = calculate_synthetic_pricing_reference(
        usage=usage,
        provider="openai",
        model_id=quote.model_id,
        quote=quote,
        evaluated_at=quote.observed_at,
    )

    assert len(result.provider_cost_native.as_tuple().digits) > 38
    assert 0 <= result.estimated_cost_jpy <= (1 << 63) - 1

    overflowing_quote = SyntheticPricingQuote(
        quote_id="st0703-overflow-v1",
        provider="openai",
        model_id=quote.model_id,
        native_currency="JPY",
        input_per_million=maximum_rate,
        cached_input_per_million=Decimal("0"),
        output_per_million=Decimal("0"),
        jpy_per_native_unit=Decimal("1"),
        observed_at=quote.observed_at,
        expires_at=quote.expires_at,
    )
    with pytest.raises(ValueError, match="supported range"):
        calculate_synthetic_pricing_reference(
            usage=usage,
            provider="openai",
            model_id=quote.model_id,
            quote=overflowing_quote,
            evaluated_at=quote.observed_at,
        )


def test_pricing_reference_rejects_tampered_quote_fields_and_hash() -> None:
    quote = _quote()
    object.__setattr__(quote, "input_per_million", Decimal("1"))

    with pytest.raises(ValueError, match="quote_sha256"):
        calculate_synthetic_pricing_reference(
            usage=ProviderUsage(1, 1, 0),
            provider="openai",
            model_id=quote.model_id,
            quote=quote,
            evaluated_at=quote.observed_at + timedelta(seconds=1),
        )


def test_recorder_is_content_addressed_and_idempotent() -> None:
    content = json.dumps(
        {"kind": "SYNTHETIC_TEST_ONLY", "value": 1},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    exchange = ProviderExchange(
        canonical_bytes=content,
        sha256=Sha256Digest.of(content),
    )
    recorder = InMemoryProviderExchangeRecorder()

    first = recorder.record(exchange)
    second = recorder.record(exchange)

    assert first == second
    assert recorder.record_calls == 2
    assert recorder.read(first) == content
    assert first.uri == f"file://recorded/{exchange.sha256.value}.json"


def test_recorder_rejects_non_exchange_input() -> None:
    recorder = InMemoryProviderExchangeRecorder()

    with pytest.raises(TypeError, match="ProviderExchange"):
        recorder.record(object())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "content",
    (
        b'\xef\xbb\xbf{"a":1}',
        b'{"a":1}\n',
        b'{"a":1,"a":1}',
        b'{"a":NaN}',
        b"[]",
        b'{"b":1,"a":2}',
    ),
)
def test_provider_exchange_rejects_noncanonical_json(content: bytes) -> None:
    with pytest.raises(ValueError, match="canonical"):
        ProviderExchange(canonical_bytes=content, sha256=Sha256Digest.of(content))


def test_provider_exchange_rejects_size_and_digest_mismatch() -> None:
    oversized = b'{"value":"' + b"x" * (4 * 1024 * 1024) + b'"}'
    with pytest.raises(ValueError):
        ProviderExchange(
            canonical_bytes=oversized,
            sha256=Sha256Digest.of(oversized),
        )

    content = b'{"value":1}'
    with pytest.raises(ValueError, match="sha256"):
        ProviderExchange(
            canonical_bytes=content,
            sha256=Sha256Digest("0" * 64),
        )


def test_canonical_json_rejects_depth_and_visit_bounds() -> None:
    nested: object = 1
    for _ in range(102):
        nested = [nested]
    with pytest.raises(ValueError, match="graph limit"):
        CanonicalJsonObject({"nested": nested})

    with pytest.raises(ValueError, match="graph limit"):
        CanonicalJsonObject({"items": list(range(100_001))})


def test_recorder_digest_collision_fails_closed() -> None:
    content = b'{"kind":"SYNTHETIC_TEST_ONLY"}'
    exchange = ProviderExchange(
        canonical_bytes=content,
        sha256=Sha256Digest.of(content),
    )
    recorder = InMemoryProviderExchangeRecorder()
    recorder._content_by_digest[exchange.sha256.value] = b'{"different":true}'

    with pytest.raises(ProviderError) as captured:
        recorder.record(exchange)

    assert captured.value.stable_code is ProviderErrorCode.RECORDER_FAILURE
    assert captured.value.__cause__ is None

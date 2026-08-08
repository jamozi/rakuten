"""Unit tests for deterministic recorded-provider collaborators."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json

import pytest

from raos.adapters.recorded_ai import (
    InMemoryProviderExchangeRecorder,
    SyntheticRecordedCostCalculator,
)
from raos.domain.ai.provider import ProviderUsage, Sha256Digest, SyntheticPricingQuote
from raos.ports.ai_provider import ProviderExchange


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
    result = SyntheticRecordedCostCalculator().calculate(usage, _quote())

    assert result.estimated_cost_jpy == expected
    assert result.quote_id == "st0703-synthetic-quote-v1"
    assert result.quote_sha256 == _quote().quote_sha256


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

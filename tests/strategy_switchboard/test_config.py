from __future__ import annotations

import pytest

from raos.strategy_switchboard.config import (
    load_gate_context_json,
    load_profile_json,
)
from raos.strategy_switchboard.model import (
    Environment,
    FallbackPolicy,
    StrategySelectionError,
    StrategyTier,
)


def test_profile_loader_accepts_exact_explicit_configuration() -> None:
    profile = load_profile_json(
        b'{"fallback_policy":"fallback_chain","overrides":{"OD-001":"OD-001:synthetic-fixture"},"preferred_tier":"standard","profile_id":"reviewed-local"}'
    )

    assert profile.profile_id == "reviewed-local"
    assert profile.preferred_tier is StrategyTier.STANDARD
    assert profile.fallback_policy is FallbackPolicy.FALLBACK_CHAIN
    assert profile.override_for("OD-001") == "OD-001:synthetic-fixture"


def test_gate_context_loader_accepts_exact_explicit_configuration() -> None:
    context = load_gate_context_json(
        b'{"approvals":["OD-001","production-use"],"capabilities":["external-io"],"environment":"production","evidence":["category-portfolio-evidence"]}'
    )

    assert context.environment is Environment.PRODUCTION
    assert context.approvals == frozenset({"OD-001", "production-use"})
    assert context.evidence == frozenset({"category-portfolio-evidence"})
    assert context.capabilities == frozenset({"external-io"})


@pytest.mark.parametrize(
    ("document", "expected_code"),
    (
        (
            b'{"fallback_policy":"safe_only","preferred_tier":"safe","profile_id":"x","unknown":true}',
            "STRATEGY_CONFIG_FIELDS_INVALID",
        ),
        (
            b'{"fallback_policy":"safe_only","preferred_tier":"safe","profile_id":"x","profile_id":"y"}',
            "STRATEGY_CONFIG_DUPLICATE_KEY",
        ),
        (
            b'{"fallback_policy":"safe_only","preferred_tier":"impossible","profile_id":"x"}',
            "STRATEGY_CONFIG_VALUE_INVALID",
        ),
        (b'{"value":NaN}', "STRATEGY_CONFIG_INVALID"),
        (b'[]', "STRATEGY_CONFIG_INVALID"),
    ),
)
def test_profile_loader_rejects_unknown_duplicate_or_invalid_values(
    document: bytes,
    expected_code: str,
) -> None:
    with pytest.raises(StrategySelectionError) as captured:
        load_profile_json(document)

    assert captured.value.code == expected_code


def test_gate_context_loader_rejects_missing_or_duplicate_gate_identifiers() -> None:
    with pytest.raises(StrategySelectionError) as missing:
        load_gate_context_json(
            b'{"approvals":[],"capabilities":[],"environment":"local"}'
        )
    assert missing.value.code == "STRATEGY_CONFIG_FIELDS_INVALID"

    with pytest.raises(StrategySelectionError) as duplicate:
        load_gate_context_json(
            b'{"approvals":["OD-001","OD-001"],"capabilities":[],"environment":"local","evidence":[]}'
        )
    assert duplicate.value.code == "STRATEGY_CONFIG_VALUE_INVALID"


def test_configuration_loader_has_hard_size_limit() -> None:
    with pytest.raises(StrategySelectionError) as captured:
        load_profile_json(b"{" + b"x" * 65_536 + b"}")

    assert captured.value.code == "STRATEGY_CONFIG_INVALID"

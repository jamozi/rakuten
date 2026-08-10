"""Strict explicit configuration loaders for strategy profiles and gate context."""

from __future__ import annotations

import json
from typing import cast

from raos.strategy_switchboard.model import (
    Environment,
    FallbackPolicy,
    GateContext,
    StrategyProfile,
    StrategySelectionError,
    StrategyTier,
)


_MAX_CONFIG_BYTES = 65_536


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise StrategySelectionError("STRATEGY_CONFIG_DUPLICATE_KEY")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise ValueError("non-finite JSON number")


def _load(document: bytes) -> dict[str, object]:
    if type(document) is not bytes or not document or len(document) > _MAX_CONFIG_BYTES:
        raise StrategySelectionError("STRATEGY_CONFIG_INVALID")
    try:
        value = json.loads(
            document.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except StrategySelectionError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError, TypeError):
        raise StrategySelectionError("STRATEGY_CONFIG_INVALID") from None
    if type(value) is not dict:
        raise StrategySelectionError("STRATEGY_CONFIG_INVALID")
    return value


def _exact_fields(
    document: dict[str, object],
    *,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
) -> None:
    keys = frozenset(document)
    if not required <= keys or not keys <= required | optional:
        raise StrategySelectionError("STRATEGY_CONFIG_FIELDS_INVALID")


def _string_list(value: object) -> frozenset[str]:
    if type(value) is not list or any(type(item) is not str for item in value):
        raise StrategySelectionError("STRATEGY_CONFIG_VALUE_INVALID")
    if len(set(value)) != len(value):
        raise StrategySelectionError("STRATEGY_CONFIG_VALUE_INVALID")
    return frozenset(value)


def load_profile_json(document: bytes) -> StrategyProfile:
    value = _load(document)
    _exact_fields(
        value,
        required=frozenset(
            {"profile_id", "preferred_tier", "fallback_policy"}
        ),
        optional=frozenset({"overrides"}),
    )
    profile_id = value["profile_id"]
    preferred_tier = value["preferred_tier"]
    fallback_policy = value["fallback_policy"]
    overrides_value = value.get("overrides", {})
    if (
        type(profile_id) is not str
        or type(preferred_tier) is not str
        or type(fallback_policy) is not str
        or type(overrides_value) is not dict
        or any(type(key) is not str for key in overrides_value)
        or any(type(item) is not str for item in overrides_value.values())
    ):
        raise StrategySelectionError("STRATEGY_CONFIG_VALUE_INVALID")
    try:
        tier = StrategyTier[preferred_tier.upper()]
        fallback = FallbackPolicy(fallback_policy)
        return StrategyProfile.from_mapping(
            profile_id=profile_id,
            preferred_tier=tier,
            fallback_policy=fallback,
            overrides=cast(dict[str, str], overrides_value),
        )
    except (KeyError, ValueError, TypeError):
        raise StrategySelectionError("STRATEGY_CONFIG_VALUE_INVALID") from None


def load_gate_context_json(document: bytes) -> GateContext:
    value = _load(document)
    _exact_fields(
        value,
        required=frozenset(
            {"environment", "approvals", "evidence", "capabilities"}
        ),
    )
    environment = value["environment"]
    if type(environment) is not str:
        raise StrategySelectionError("STRATEGY_CONFIG_VALUE_INVALID")
    try:
        return GateContext(
            environment=Environment(environment),
            approvals=_string_list(value["approvals"]),
            evidence=_string_list(value["evidence"]),
            capabilities=_string_list(value["capabilities"]),
        )
    except (ValueError, TypeError):
        raise StrategySelectionError("STRATEGY_CONFIG_VALUE_INVALID") from None

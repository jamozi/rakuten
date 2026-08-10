from __future__ import annotations

import pytest

from raos.strategy_switchboard.model import (
    Environment,
    ExecutionKind,
    GateContext,
    GateRequirements,
    StrategyCandidate,
    StrategyCatalog,
    StrategySelectionError,
    StrategyTier,
    canonical_json_bytes,
)


def _candidate(
    strategy_id: str,
    tier: StrategyTier,
    *,
    safe_default: bool = False,
) -> StrategyCandidate:
    return StrategyCandidate(
        strategy_id=strategy_id,
        boundary_id="ST-9999",
        tier=tier,
        title=strategy_id,
        description="bounded test candidate",
        execution_kind=(
            ExecutionKind.DETERMINISTIC_PLAN
            if tier is StrategyTier.SAFE
            else ExecutionKind.MANUAL_INPUT
        ),
        requirements=GateRequirements(
            approvals=() if tier is StrategyTier.SAFE else ("approval",),
            allowed_environments=(Environment.LOCAL,),
        ),
        safe_default=safe_default,
    )


def test_catalog_rejects_duplicate_tier_and_missing_safe_default() -> None:
    safe = _candidate("ST-9999:safe", StrategyTier.SAFE, safe_default=True)
    duplicate_safe_tier = _candidate("ST-9999:other-safe", StrategyTier.SAFE)

    with pytest.raises(ValueError, match="duplicate strategy tiers"):
        StrategyCatalog(
            version="test-v1",
            candidates=(safe, duplicate_safe_tier),
        )

    with pytest.raises(ValueError, match="exactly one safe default"):
        StrategyCatalog(
            version="test-v1",
            candidates=(_candidate("ST-9999:standard", StrategyTier.STANDARD),),
        )


def test_safe_default_cannot_require_gate_or_side_effect() -> None:
    with pytest.raises(ValueError, match="selectable in empty local context"):
        StrategyCandidate(
            strategy_id="ST-9999:safe",
            boundary_id="ST-9999",
            tier=StrategyTier.SAFE,
            title="safe",
            description="invalid gated safe candidate",
            execution_kind=ExecutionKind.DETERMINISTIC_PLAN,
            requirements=GateRequirements(approvals=("approval",)),
            safe_default=True,
        )

    with pytest.raises(ValueError, match="no side effects"):
        StrategyCandidate(
            strategy_id="ST-9999:safe",
            boundary_id="ST-9999",
            tier=StrategyTier.SAFE,
            title="safe",
            description="invalid side-effecting safe candidate",
            execution_kind=ExecutionKind.DETERMINISTIC_PLAN,
            requirements=GateRequirements(),
            safe_default=True,
            side_effects=("write",),
        )


def test_gate_context_is_order_independent_and_exact() -> None:
    first = GateContext(
        environment=Environment.STAGING,
        approvals=frozenset({"b", "a"}),
        evidence=frozenset({"evidence"}),
        capabilities=frozenset({"capability"}),
    )
    second = GateContext(
        environment=Environment.STAGING,
        approvals=frozenset({"a", "b"}),
        evidence=frozenset({"evidence"}),
        capabilities=frozenset({"capability"}),
    )

    assert first == second
    assert first.sha256 == second.sha256


def test_canonical_json_rejects_nan_and_oversized_documents() -> None:
    with pytest.raises(StrategySelectionError) as nan_error:
        canonical_json_bytes({"invalid": float("nan")})
    assert nan_error.value.code == "STRATEGY_CANONICALIZATION_FAILED"

    with pytest.raises(StrategySelectionError) as size_error:
        canonical_json_bytes({"value": "x" * 4_194_305})
    assert size_error.value.code == "STRATEGY_DOCUMENT_TOO_LARGE"


def test_selection_error_exposes_only_stable_code_as_message() -> None:
    error = StrategySelectionError(
        "STRATEGY_REQUIREMENTS_UNSATISFIED",
        boundary_id="OD-001",
        strategy_id="OD-001:approved-multi-category",
    )

    assert str(error) == "STRATEGY_REQUIREMENTS_UNSATISFIED"
    assert error.args == ("STRATEGY_REQUIREMENTS_UNSATISFIED",)

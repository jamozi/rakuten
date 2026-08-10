"""Typed, fail-closed strategy selection for every RAOS Story boundary."""

from raos.strategy_switchboard.catalog import (
    ADVANCED_EXTERNAL_PROFILE,
    BALANCED_STAGING_PROFILE,
    SAFE_LOCAL_PROFILE,
    build_complete_catalog,
    open_decision_candidates,
    story_candidates,
)
from raos.strategy_switchboard.model import (
    Environment,
    ExecutionKind,
    FallbackPolicy,
    GateContext,
    GateRequirements,
    SelectionDecision,
    StrategyCandidate,
    StrategyCatalog,
    StrategyProfile,
    StrategySelectionError,
    StrategyTier,
)
from raos.strategy_switchboard.runtime import (
    StrategyAdapter,
    StrategyExecution,
    StrategyRuntime,
)
from raos.strategy_switchboard.switchboard import StrategySwitchboard

__all__ = [
    "ADVANCED_EXTERNAL_PROFILE",
    "BALANCED_STAGING_PROFILE",
    "Environment",
    "ExecutionKind",
    "FallbackPolicy",
    "GateContext",
    "GateRequirements",
    "SAFE_LOCAL_PROFILE",
    "SelectionDecision",
    "StrategyAdapter",
    "StrategyCandidate",
    "StrategyCatalog",
    "StrategyExecution",
    "StrategyProfile",
    "StrategyRuntime",
    "StrategySelectionError",
    "StrategySwitchboard",
    "StrategyTier",
    "build_complete_catalog",
    "open_decision_candidates",
    "story_candidates",
]

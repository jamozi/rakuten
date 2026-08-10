from __future__ import annotations

import pytest

from scripts import build_all_story_strategy_catalog as generator

from raos.strategy_switchboard.catalog import (
    ADVANCED_EXTERNAL_PROFILE,
    BALANCED_STAGING_PROFILE,
    SAFE_LOCAL_PROFILE,
    build_complete_catalog,
)
from raos.strategy_switchboard.model import (
    Environment,
    FallbackPolicy,
    GateContext,
    StrategyProfile,
    StrategySelectionError,
    StrategyTier,
)
from raos.strategy_switchboard.switchboard import StrategySwitchboard


def _switchboard() -> StrategySwitchboard:
    story_ids = generator.canonical_story_ids(generator.REPOSITORY_ROOT)
    return StrategySwitchboard(build_complete_catalog(story_ids))


def test_safe_profile_selects_deterministic_default() -> None:
    decision = _switchboard().select(
        boundary_id="OD-001",
        profile=SAFE_LOCAL_PROFILE,
        context=GateContext.local_empty(),
    )

    assert decision.requested_strategy_id == "OD-001:synthetic-fixture"
    assert decision.selected_strategy_id == "OD-001:synthetic-fixture"
    assert decision.fallback_chain == ("OD-001:synthetic-fixture",)
    assert decision.missing_requirements == ()
    assert decision.used_fallback is False


def test_balanced_profile_falls_back_to_safe_only_in_local_environment() -> None:
    decision = _switchboard().select(
        boundary_id="OD-003",
        profile=BALANCED_STAGING_PROFILE,
        context=GateContext.local_empty(),
    )

    assert decision.requested_strategy_id == "OD-003:manual-anonymized-csv"
    assert decision.selected_strategy_id == "OD-003:synthetic-report"
    assert decision.fallback_chain == (
        "OD-003:manual-anonymized-csv",
        "OD-003:synthetic-report",
    )
    assert decision.used_fallback is True
    assert "strategy:OD-003:manual-anonymized-csv:approval:OD-003" in (
        decision.missing_requirements
    )


def test_balanced_profile_selects_standard_with_explicit_gate_material() -> None:
    context = GateContext(
        environment=Environment.STAGING,
        approvals=frozenset({"OD-003"}),
        evidence=frozenset({"anonymized-report-sample"}),
    )

    decision = _switchboard().select(
        boundary_id="OD-003",
        profile=BALANCED_STAGING_PROFILE,
        context=context,
    )

    assert decision.selected_strategy_id == "OD-003:manual-anonymized-csv"
    assert decision.used_fallback is False


def test_advanced_profile_refuses_when_one_gate_is_missing() -> None:
    context = GateContext(
        environment=Environment.PRODUCTION,
        approvals=frozenset({"OD-001", "production-use"}),
        capabilities=frozenset({"external-io"}),
    )

    with pytest.raises(StrategySelectionError) as captured:
        _switchboard().select(
            boundary_id="OD-001",
            profile=ADVANCED_EXTERNAL_PROFILE,
            context=context,
        )

    assert captured.value.code == "STRATEGY_REQUIREMENTS_UNSATISFIED"
    assert captured.value.boundary_id == "OD-001"
    assert captured.value.strategy_id == "OD-001:approved-multi-category"


def test_advanced_profile_selects_only_with_complete_gate_material() -> None:
    context = GateContext(
        environment=Environment.PRODUCTION,
        approvals=frozenset({"OD-001", "production-use"}),
        evidence=frozenset({"category-portfolio-evidence"}),
        capabilities=frozenset({"external-io"}),
    )

    decision = _switchboard().select(
        boundary_id="OD-001",
        profile=ADVANCED_EXTERNAL_PROFILE,
        context=context,
    )

    assert decision.selected_strategy_id == "OD-001:approved-multi-category"
    assert decision.used_fallback is False


def test_explicit_override_switches_one_boundary_without_mutating_profile() -> None:
    decision = _switchboard().select(
        boundary_id="OD-001",
        profile=BALANCED_STAGING_PROFILE,
        context=GateContext.local_empty(),
        override_strategy_id="OD-001:synthetic-fixture",
    )

    assert decision.requested_strategy_id == "OD-001:synthetic-fixture"
    assert decision.selected_strategy_id == "OD-001:synthetic-fixture"
    assert BALANCED_STAGING_PROFILE.overrides == ()


def test_profile_mapping_can_switch_multiple_boundaries_independently() -> None:
    profile = StrategyProfile.from_mapping(
        profile_id="custom-local",
        preferred_tier=StrategyTier.STANDARD,
        fallback_policy=FallbackPolicy.FALLBACK_CHAIN,
        overrides={
            "OD-001": "OD-001:synthetic-fixture",
            "OD-003": "OD-003:synthetic-report",
        },
    )
    switchboard = _switchboard()

    first = switchboard.select(
        boundary_id="OD-001",
        profile=profile,
        context=GateContext.local_empty(),
    )
    second = switchboard.select(
        boundary_id="OD-003",
        profile=profile,
        context=GateContext.local_empty(),
    )

    assert first.selected_strategy_id == "OD-001:synthetic-fixture"
    assert second.selected_strategy_id == "OD-003:synthetic-report"


def test_cross_boundary_override_is_rejected() -> None:
    with pytest.raises(StrategySelectionError) as captured:
        _switchboard().select(
            boundary_id="OD-001",
            profile=SAFE_LOCAL_PROFILE,
            context=GateContext.local_empty(),
            override_strategy_id="OD-002:example-invalid",
        )

    assert captured.value.code == "STRATEGY_OVERRIDE_BOUNDARY_MISMATCH"


def test_production_never_falls_back_to_local_or_staging_candidate() -> None:
    context = GateContext(
        environment=Environment.PRODUCTION,
        approvals=frozenset({"OD-003"}),
        evidence=frozenset({"anonymized-report-sample"}),
    )

    with pytest.raises(StrategySelectionError) as captured:
        _switchboard().select(
            boundary_id="OD-003",
            profile=BALANCED_STAGING_PROFILE,
            context=context,
        )

    assert captured.value.code == "STRATEGY_REQUIREMENTS_UNSATISFIED"


def test_selection_record_and_context_hash_are_deterministic() -> None:
    context = GateContext(
        environment=Environment.LOCAL,
        approvals=frozenset({"OD-001"}),
    )
    switchboard = _switchboard()

    first = switchboard.select(
        boundary_id="OD-001",
        profile=BALANCED_STAGING_PROFILE,
        context=context,
    )
    second = switchboard.select(
        boundary_id="OD-001",
        profile=BALANCED_STAGING_PROFILE,
        context=context,
    )

    assert first == second
    assert first.sha256 == second.sha256
    assert first.context_sha256 == context.sha256

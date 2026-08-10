from __future__ import annotations

from scripts import build_all_story_strategy_catalog as generator

from raos.strategy_switchboard.catalog import (
    ADVANCED_EXTERNAL_PROFILE,
    BALANCED_STAGING_PROFILE,
    SAFE_LOCAL_PROFILE,
    build_complete_catalog,
)
from raos.strategy_switchboard.model import (
    Environment,
    ExecutionKind,
    FallbackPolicy,
    StrategyTier,
)


def test_catalog_covers_every_canonical_story_and_open_decision() -> None:
    story_ids = generator.canonical_story_ids(generator.REPOSITORY_ROOT)
    decision_ids = generator.canonical_open_decision_ids(generator.REPOSITORY_ROOT)

    catalog = build_complete_catalog(story_ids)

    assert set(catalog.boundary_ids) == set(story_ids) | set(decision_ids)
    assert len(catalog.candidates) == 3 * (len(story_ids) + len(decision_ids))
    assert len(story_ids) >= 100
    assert decision_ids == tuple(f"OD-{number:03d}" for number in range(1, 16))


def test_every_boundary_has_exact_safe_standard_and_advanced_candidates() -> None:
    catalog = build_complete_catalog(
        generator.canonical_story_ids(generator.REPOSITORY_ROOT)
    )

    for boundary_id in catalog.boundary_ids:
        candidates = catalog.for_boundary(boundary_id)
        assert {candidate.tier for candidate in candidates} == {
            StrategyTier.SAFE,
            StrategyTier.STANDARD,
            StrategyTier.ADVANCED,
        }
        safe = [candidate for candidate in candidates if candidate.safe_default]
        assert len(safe) == 1
        assert safe[0].tier is StrategyTier.SAFE
        assert safe[0].execution_kind is ExecutionKind.DETERMINISTIC_PLAN
        assert safe[0].side_effects == ()
        assert safe[0].requirements.allowed_environments == (Environment.LOCAL,)


def test_standard_and_advanced_paths_remain_explicitly_gated() -> None:
    catalog = build_complete_catalog(
        generator.canonical_story_ids(generator.REPOSITORY_ROOT)
    )

    for boundary_id in catalog.boundary_ids:
        by_tier = {candidate.tier: candidate for candidate in catalog.for_boundary(boundary_id)}
        standard = by_tier[StrategyTier.STANDARD]
        advanced = by_tier[StrategyTier.ADVANCED]

        assert standard.requirements.approvals
        assert Environment.PRODUCTION not in standard.requirements.allowed_environments
        assert advanced.execution_kind is ExecutionKind.INJECTED_ADAPTER
        assert advanced.adapter_key is not None
        assert "production-use" in advanced.requirements.approvals
        assert advanced.requirements.evidence
        assert advanced.requirements.capabilities
        assert Environment.PRODUCTION in advanced.requirements.allowed_environments


def test_builtin_profiles_have_distinct_switching_semantics() -> None:
    assert SAFE_LOCAL_PROFILE.preferred_tier is StrategyTier.SAFE
    assert SAFE_LOCAL_PROFILE.fallback_policy is FallbackPolicy.SAFE_ONLY

    assert BALANCED_STAGING_PROFILE.preferred_tier is StrategyTier.STANDARD
    assert BALANCED_STAGING_PROFILE.fallback_policy is FallbackPolicy.FALLBACK_CHAIN

    assert ADVANCED_EXTERNAL_PROFILE.preferred_tier is StrategyTier.ADVANCED
    assert ADVANCED_EXTERNAL_PROFILE.fallback_policy is FallbackPolicy.FAIL_CLOSED


def test_catalog_digest_is_deterministic_and_order_independent() -> None:
    story_ids = generator.canonical_story_ids(generator.REPOSITORY_ROOT)
    forward = build_complete_catalog(story_ids)
    reverse = build_complete_catalog(tuple(reversed(story_ids)))

    assert forward.to_record() == reverse.to_record()
    assert forward.sha256 == reverse.sha256

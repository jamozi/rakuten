"""Determinism, binding, immutability, and isolation boundaries for ST-0804."""

from __future__ import annotations

import builtins
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal

import pytest

from conftest import recommendation_input, valid_recommendation_input
import raos.domain.editorial.recommendation as recommendation_module
from raos.domain.editorial.comparison_validation import validate_comparison
from raos.domain.editorial.recommendation import (
    CandidateUniverse,
    RecommendationDecision,
    RecommendationValueConstructionError,
    ReferenceId,
    Sha256Digest,
    generate_recommendations,
)


def test_same_input_recalculation_is_byte_identical_and_non_mutating() -> None:
    value = valid_recommendation_input()
    original_hash = hash(value)

    first = generate_recommendations(value)
    second = generate_recommendations(value)

    assert first == second
    assert first.explanation_json == second.explanation_json
    assert first.explanation_sha256 == second.explanation_sha256
    assert hash(value) == original_hash
    assert repr(value) == "RecommendationInput(<redacted>)"
    with pytest.raises(FrozenInstanceError):
        setattr(value, "dimensions", ())


def test_all_input_collection_permutations_produce_identical_result() -> None:
    value = valid_recommendation_input()
    comparison = replace(
        value.comparison,
        products=tuple(reversed(value.comparison.products)),
        axes=tuple(reversed(value.comparison.axes)),
        cells=tuple(reversed(value.comparison.cells)),
    )
    permuted = replace(
        value,
        comparison=comparison,
        comparison_report=validate_comparison(comparison),
        candidate_universe=replace(
            value.candidate_universe,
            product_ids=tuple(reversed(value.candidate_universe.product_ids)),
        ),
        dimensions=tuple(reversed(value.dimensions)),
        assessments=tuple(reversed(value.assessments)),
    )

    assert generate_recommendations(permuted) == generate_recommendations(value)


def test_article_and_decision_context_are_bound_against_cross_article_reuse() -> None:
    first = valid_recommendation_input()
    other_article = replace(
        first,
        context=replace(first.context, article_id=ReferenceId("ARTICLE_002")),
    )
    other_context = replace(
        first,
        context=replace(
            first.context,
            decision_context_sha256=Sha256Digest("a" * 64),
        ),
    )

    first_report = generate_recommendations(first)
    article_report = generate_recommendations(other_article)
    context_report = generate_recommendations(other_context)

    assert first_report.candidates == article_report.candidates
    assert first_report.candidates == context_report.candidates
    assert first_report.explanation_sha256 != article_report.explanation_sha256
    assert first_report.explanation_sha256 != context_report.explanation_sha256


def test_candidate_universe_dimension_and_rule_versions_bind_explanation_hash() -> None:
    value = valid_recommendation_input()
    universe_changed = replace(
        value,
        candidate_universe=replace(
            value.candidate_universe,
            universe_sha256=Sha256Digest("b" * 64),
        ),
    )
    dimension_changed = replace(
        value,
        dimensions=(
            replace(value.dimensions[0], definition_sha256=Sha256Digest("c" * 64)),
            *value.dimensions[1:],
        ),
    )
    changed_conflict_rule = replace(
        value.methodology.conflict_penalty_rule,
        sha256=Sha256Digest("d" * 64),
    )
    methodology_changed = replace(
        value.methodology,
        conflict_penalty_rule=changed_conflict_rule,
    )
    rule_changed = replace(
        value,
        methodology=methodology_changed,
        assessments=tuple(
            replace(assessment, conflict_rule=changed_conflict_rule)
            for assessment in value.assessments
        ),
    )

    hashes = {
        generate_recommendations(candidate).explanation_sha256
        for candidate in (value, universe_changed, dimension_changed, rule_changed)
    }
    assert None not in hashes
    assert len(hashes) == 4


def test_weight_totals_need_not_equal_one_but_each_weight_is_at_most_one() -> None:
    report = generate_recommendations(
        recommendation_input(
            (
                (Decimal("0.90"), Decimal("0.60")),
                (Decimal("0.80"), Decimal("0.70")),
            ),
            weights=(Decimal("0.20"), Decimal("0.30")),
        )
    )

    assert report.decision is RecommendationDecision.PASS
    assert report.candidates[0].base_score == Decimal("72.0000")


def test_highest_score_group_anchor_prevents_transitive_tie_chaining() -> None:
    report = generate_recommendations(
        recommendation_input(
            (
                (Decimal("0.9000"),),
                (Decimal("0.8800"),),
                (Decimal("0.8601"),),
            )
        )
    )

    by_product = {
        candidate.product_id.value: candidate for candidate in report.candidates
    }
    assert by_product["PRODUCT_01"].tie_group == 1
    assert by_product["PRODUCT_02"].tie_group == 1
    assert by_product["PRODUCT_03"].tie_group == 2


def test_engine_performs_no_file_environment_clock_random_network_or_persistence_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("forbidden side effect")

    monkeypatch.setattr(builtins, "open", forbidden)
    for forbidden_name in (
        "asyncio",
        "datetime",
        "httpx",
        "os",
        "pathlib",
        "psycopg",
        "random",
        "requests",
        "socket",
        "sqlalchemy",
        "subprocess",
        "time",
        "urllib",
    ):
        assert forbidden_name not in vars(recommendation_module)

    assert generate_recommendations(valid_recommendation_input()).passed is True


def test_exact_value_construction_failure_is_closed_and_redacted() -> None:
    raw_value = 'SAFE"},"revenue":1,{"unsafe":"value'

    with pytest.raises(RecommendationValueConstructionError) as captured:
        ReferenceId(raw_value)

    assert str(captured.value) == "INVALID_EXACT_VALUE"
    assert raw_value not in repr(captured.value)


def test_candidate_universe_is_immutable_and_redacted() -> None:
    universe = valid_recommendation_input().candidate_universe

    assert isinstance(universe, CandidateUniverse)
    assert repr(universe) == "CandidateUniverse(<redacted>)"
    assert "PRODUCT_01" not in repr(universe)
    with pytest.raises(FrozenInstanceError):
        setattr(universe, "product_ids", ())

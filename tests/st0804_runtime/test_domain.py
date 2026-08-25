from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import itertools
from uuid import UUID

import pytest

import raos.domain.editorial.recommendation_v2 as runtime
from raos.domain.editorial.comparison_validation_v2 import (
    ComparisonCellStatus,
    ComparisonRecordReceipt,
)
from raos.domain.editorial.ids import ArticleVersionId, ComparisonAxisId
from raos.domain.editorial.recommendation_v2 import (
    CandidateEligibility,
    CandidateReasonCode,
    ConflictState,
    DimensionAssessmentV2,
    HardConstraintState,
    MethodologyBindingV2,
    NormalizationBasis,
    RankingState,
    RecommendationDimensionV2,
    RecommendationEnvelopeV2,
    RecommendationEvaluationStatus,
    RecommendationFindingCode,
    RecommendationRuntimeValueError,
    StalenessState,
    assessment_set_sha256,
    comparison_receipt_sha256,
    decision_context_sha256,
    dimension_set_sha256,
    evaluate_recommendations_v2,
    normalization_decision_sha256,
    normalization_input_sha256,
    prohibited_ranking_alias,
    recommendation_input_sha256,
    unavailable_recommendation_report,
)
from raos.domain.shared.persistence import Sha256Digest

from .helpers import rehash_envelope


def _rebind_assessment(
    envelope: RecommendationEnvelopeV2,
    assessment: DimensionAssessmentV2,
) -> DimensionAssessmentV2:
    cell = next(
        item
        for item in envelope.comparison.comparison.cells
        if item.product_id == assessment.product_id
        and item.axis_id == assessment.axis_id
    )
    dimension = next(
        item for item in envelope.dimensions if item.axis_id == assessment.axis_id
    )
    input_sha256 = normalization_input_sha256(
        comparison=envelope.comparison.comparison,
        context=envelope.context,
        methodology=envelope.methodology,
        dimension=dimension,
        cell=cell,
        basis=assessment.normalization_basis,
    )
    return replace(
        assessment,
        normalization_input_sha256=input_sha256,
        normalization_decision_sha256=normalization_decision_sha256(
            input_sha256=input_sha256,
            basis=assessment.normalization_basis,
            normalized_score=assessment.normalized_score,
        ),
    )


def test_pass_binds_current_comparison_request_report_receipt_and_provenance(
    envelope: RecommendationEnvelopeV2,
) -> None:
    report = evaluate_recommendations_v2(envelope)
    report.require_valid()
    comparison = envelope.comparison.comparison

    assert report.status is RecommendationEvaluationStatus.LOCAL_CALCULATED
    assert report.findings == ()
    assert report.article_id == comparison.article.article_id
    assert report.article_version_id == comparison.article.article_version_id
    assert report.article_binding_sha256 == comparison.article.binding_sha256
    assert report.comparison_report_sha256 == envelope.comparison_report.report_sha256
    assert report.comparison_receipt_sha256 == comparison_receipt_sha256(
        envelope.comparison_receipt
    )
    assert (
        report.comparison_evaluation_input_sha256 == comparison.evaluation_input_sha256
    )
    assert (
        report.candidate_universe_sha256
        == comparison.candidate_universe.candidate_universe_sha256
    )
    assert report.axis_catalog_sha256 == comparison.axis_catalog.axis_catalog_sha256
    assert report.fact_set_sha256 == comparison.fact_set_sha256
    assert report.temporal_scope_sha256 == comparison.temporal_scope_sha256
    assert (
        report.complete_claim_set_sha256 == comparison.article.complete_claim_set_sha256
    )
    assert report.decision_context_sha256 == envelope.context.binding_sha256
    assert report.methodology_sha256 == envelope.methodology.source_sha256
    assert report.dimension_set_sha256 == envelope.dimension_set_sha256
    assert report.assessment_set_sha256 == envelope.assessment_set_sha256
    assert report.recommendation_input_sha256 == envelope.recommendation_input_sha256
    assert report.ranking_order[0].value == UUID("60606060-6060-4060-8060-606060606060")
    assert all(not candidate.co_recommended for candidate in report.candidates)
    assert not report.override_supported
    assert not report.approval_authorized
    assert not report.recommendation_authorized
    assert not report.ranking_authorized
    assert not report.publication_authorized
    assert not report.activation_authorized
    assert not report.production_eligible


def test_permutations_are_byte_identical(envelope: RecommendationEnvelopeV2) -> None:
    expected = evaluate_recommendations_v2(envelope).canonical_bytes()
    cases = (
        envelope,
        rehash_envelope(
            replace(envelope, dimensions=tuple(reversed(envelope.dimensions)))
        ),
        rehash_envelope(
            replace(envelope, assessments=tuple(reversed(envelope.assessments)))
        ),
    )
    assert all(
        evaluate_recommendations_v2(case).canonical_bytes() == expected
        for case in cases
    )


def test_score_change_requires_exact_normalization_and_envelope_hashes(
    envelope: RecommendationEnvelopeV2,
) -> None:
    changed = replace(envelope.assessments[0], normalized_score=Decimal("0.75"))
    stale = rehash_envelope(
        replace(envelope, assessments=(changed, *envelope.assessments[1:]))
    )
    stale_report = evaluate_recommendations_v2(stale)
    assert (
        RecommendationFindingCode.NORMALIZATION_BINDING_MISMATCH
        in stale_report.findings
    )

    rebound = _rebind_assessment(envelope, changed)
    valid = rehash_envelope(
        replace(envelope, assessments=(rebound, *envelope.assessments[1:]))
    )
    report = evaluate_recommendations_v2(valid)
    assert report.status is RecommendationEvaluationStatus.LOCAL_CALCULATED
    assert report.findings == ()


@pytest.mark.parametrize(
    "mutation,expected",
    (
        (
            lambda value: replace(
                value,
                comparison_receipt=ComparisonRecordReceipt(1, Sha256Digest("f" * 64)),
            ),
            RecommendationFindingCode.COMPARISON_RECEIPT_MISMATCH,
        ),
        (
            lambda value: replace(
                value,
                comparison_report=replace(
                    value.comparison_report,
                    report_sha256=Sha256Digest("f" * 64),
                ),
            ),
            RecommendationFindingCode.COMPARISON_REPORT_INVALID,
        ),
        (
            lambda value: replace(
                value,
                recommendation_input_sha256=Sha256Digest("f" * 64),
            ),
            RecommendationFindingCode.RECOMMENDATION_INPUT_HASH_MISMATCH,
        ),
        (
            lambda value: replace(
                value,
                methodology=replace(
                    value.methodology,
                    source_sha256=Sha256Digest("f" * 64),
                ),
            ),
            RecommendationFindingCode.METHODOLOGY_INVALID,
        ),
    ),
)
def test_exact_binding_drift_fails_closed(
    envelope: RecommendationEnvelopeV2,
    mutation: object,
    expected: RecommendationFindingCode,
) -> None:
    changed = mutation(envelope)  # type: ignore[operator]
    report = evaluate_recommendations_v2(changed)
    assert report.status is RecommendationEvaluationStatus.UNEVALUABLE
    assert expected in report.findings
    assert report.candidates == ()
    assert report.ranking_order == ()


def test_context_aliases_are_rejected_even_when_rehashed(
    envelope: RecommendationEnvelopeV2,
) -> None:
    context = replace(envelope.context, use_case_code="AFFILIATE_REWARD_RATE")
    context = replace(context, binding_sha256=decision_context_sha256(context))
    provisional = replace(envelope, context=context)
    assessments = tuple(
        _rebind_assessment(provisional, assessment)
        for assessment in envelope.assessments
    )
    changed = rehash_envelope(replace(provisional, assessments=assessments))
    report = evaluate_recommendations_v2(changed)
    assert report.status is RecommendationEvaluationStatus.BLOCK
    assert report.findings == (RecommendationFindingCode.PROHIBITED_RANKING_INPUT,)


@pytest.mark.parametrize(
    "alias",
    (
        "affiliateRewardRate",
        "ＡＦＦＩＬＩＡＴＥ＿ＲＡＴＥ",
        "Aff1l1ate-R3ward",
        "confirmedCommission",
        "利益率",
        "ＥＰＣ",
        "rPm",
    ),
)
def test_alias_detector_handles_case_unicode_and_leet(alias: str) -> None:
    assert prohibited_ranking_alias(alias)


@pytest.mark.parametrize("safe", ("GENERATED", "MODERATE_BUDGET", "CAPACITY_WH"))
def test_alias_detector_avoids_safe_substring_false_positives(safe: str) -> None:
    assert not prohibited_ranking_alias(safe)


def _calculation_case(
    envelope: RecommendationEnvelopeV2,
    *,
    weights: tuple[Decimal, ...],
    unavailable_from: int | None = None,
    scores: tuple[Decimal, Decimal] = (Decimal("0.8"), Decimal("0.8")),
    staleness_penalty: Decimal = Decimal("0"),
    hard_state: HardConstraintState = HardConstraintState.NOT_APPLICABLE,
    hard_constraint: bool = False,
) -> tuple[runtime.CandidateRecommendationV2, ...]:
    methodology = MethodologyBindingV2.current()
    axes = tuple(
        ComparisonAxisId(UUID(f"90000000-0000-4000-8000-{index + 1:012d}"))
        for index in range(len(weights))
    )
    dimensions = tuple(
        RecommendationDimensionV2(
            axis_id=axis_id,
            axis_definition_sha256=Sha256Digest("a" * 64),
            weight=weight,
            critical=False,
            hard_constraint=hard_constraint,
            normalization_basis=NormalizationBasis.VALIDATED_SPECIFICATION,
            normalization_rule=methodology.normalization_rule,
        )
        for axis_id, weight in zip(axes, weights, strict=True)
    )
    assessments: list[DimensionAssessmentV2] = []
    products = envelope.comparison.comparison.candidate_universe.products
    for product_index, product in enumerate(products):
        for axis_index, axis_id in enumerate(axes):
            unavailable = (
                unavailable_from is not None and axis_index >= unavailable_from
            )
            assessments.append(
                DimensionAssessmentV2(
                    product_id=product.product_id,
                    axis_id=axis_id,
                    cell_status=(
                        ComparisonCellStatus.UNKNOWN
                        if unavailable
                        else ComparisonCellStatus.VALID
                    ),
                    fact_ids=(),
                    normalization_basis=(
                        NormalizationBasis.UNAVAILABLE
                        if unavailable
                        else NormalizationBasis.VALIDATED_SPECIFICATION
                    ),
                    normalized_score=None if unavailable else scores[product_index],
                    hard_constraint_state=(
                        HardConstraintState.UNAVAILABLE
                        if unavailable and hard_constraint
                        else hard_state
                    ),
                    conflict_state=(
                        ConflictState.UNAVAILABLE if unavailable else ConflictState.NONE
                    ),
                    conflict_penalty=Decimal("0"),
                    staleness_state=(
                        StalenessState.UNAVAILABLE
                        if unavailable
                        else StalenessState.NEAR_EXPIRY
                        if staleness_penalty
                        else StalenessState.CURRENT
                    ),
                    staleness_penalty=(
                        Decimal("0") if unavailable else staleness_penalty
                    ),
                    normalization_input_sha256=Sha256Digest("b" * 64),
                    normalization_decision_sha256=Sha256Digest("c" * 64),
                )
            )
    return runtime._calculate_candidates(  # noqa: SLF001
        envelope.comparison.comparison,
        dimensions,
        tuple(assessments),
    )


@pytest.mark.parametrize(
    "available_weight,expected_state",
    (
        (Decimal("0.79"), RankingState.UNRANKED_LOW_COVERAGE),
        (Decimal("0.80"), RankingState.RANKED),
        (Decimal("0.90"), RankingState.RANKED),
    ),
)
def test_coverage_thresholds_are_exact_and_unknown_is_not_zero(
    envelope: RecommendationEnvelopeV2,
    available_weight: Decimal,
    expected_state: RankingState,
) -> None:
    candidates = _calculation_case(
        envelope,
        weights=(available_weight, Decimal("1") - available_weight),
        unavailable_from=1,
    )
    for candidate in candidates:
        assert candidate.weighted_evidence_coverage == available_weight
        assert candidate.ranking_state is expected_state
        assert candidate.unknown_axis_ids
        assert candidate.base_score == Decimal("80.0000")
        assert candidate.base_score != Decimal("40")
        if available_weight == Decimal("0.90"):
            assert candidate.primary_recommendation_allowed


def test_staleness_penalty_and_cap_are_deterministic(
    envelope: RecommendationEnvelopeV2,
) -> None:
    penalized = _calculation_case(
        envelope,
        weights=(Decimal("1"),),
        scores=(Decimal("1"), Decimal("1")),
        staleness_penalty=Decimal("3"),
    )
    assert all(item.final_score == Decimal("97.0000") for item in penalized)
    capped = _calculation_case(
        envelope,
        weights=(Decimal("0.5"), Decimal("0.5")),
        scores=(Decimal("1"), Decimal("1")),
        staleness_penalty=Decimal("15"),
    )
    assert all(item.uncertainty_penalty == Decimal("20.0000") for item in capped)
    assert all(item.final_score == Decimal("80.0000") for item in capped)


def test_conflict_penalty_is_hash_bound_and_state_validated(
    envelope: RecommendationEnvelopeV2,
) -> None:
    changed_assessment = replace(
        envelope.assessments[0],
        conflict_penalty=Decimal("0.25"),
    )
    changed = rehash_envelope(
        replace(
            envelope,
            assessments=(changed_assessment, *envelope.assessments[1:]),
        )
    )
    assert changed.assessment_set_sha256 != envelope.assessment_set_sha256
    assert changed.recommendation_input_sha256 != envelope.recommendation_input_sha256
    report = evaluate_recommendations_v2(changed)
    assert report.status is RecommendationEvaluationStatus.UNEVALUABLE
    assert RecommendationFindingCode.PENALTY_INVALID in report.findings


@pytest.mark.parametrize(
    "second_score,tied",
    ((Decimal("0.88"), True), (Decimal("0.8799"), False)),
)
def test_tie_boundary_and_stable_product_order(
    envelope: RecommendationEnvelopeV2,
    second_score: Decimal,
    tied: bool,
) -> None:
    candidates = _calculation_case(
        envelope,
        weights=(Decimal("1"),),
        scores=(Decimal("0.9"), second_score),
    )
    ranked = sorted(
        candidates, key=lambda item: (item.rank_group or 99, item.product_id.value.int)
    )
    assert ranked[0].final_score == Decimal("90.0000")
    assert ranked[0].co_recommended is tied
    assert (ranked[1].rank_group == ranked[0].rank_group) is tied
    if tied:
        assert [item.product_id.value.int for item in ranked] == sorted(
            item.product_id.value.int for item in ranked
        )


def test_hard_constraint_failure_prevents_scoring(
    envelope: RecommendationEnvelopeV2,
) -> None:
    candidates = _calculation_case(
        envelope,
        weights=(Decimal("1"),),
        hard_constraint=True,
        hard_state=HardConstraintState.FAIL,
    )
    assert all(
        item.eligibility is CandidateEligibility.INELIGIBLE for item in candidates
    )
    assert all(item.ranking_state is RankingState.INELIGIBLE for item in candidates)
    assert all(
        CandidateReasonCode.HARD_CONSTRAINT_FAILED in item.reason_codes
        for item in candidates
    )
    assert all(item.final_score is None for item in candidates)


@pytest.mark.parametrize(
    "bad_score",
    (
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("1E+999999"),
        Decimal("-0.1"),
        Decimal("1.1"),
    ),
)
def test_invalid_decimal_scores_fail_closed(
    envelope: RecommendationEnvelopeV2,
    bad_score: Decimal,
) -> None:
    changed = replace(envelope.assessments[0], normalized_score=bad_score)
    invalid = replace(envelope, assessments=(changed, *envelope.assessments[1:]))
    report = evaluate_recommendations_v2(invalid)
    assert report.status is RecommendationEvaluationStatus.UNEVALUABLE
    assert RecommendationFindingCode.ASSESSMENT_INVALID in report.findings


def test_collection_bounds_and_incomplete_objects_fail_closed(
    envelope: RecommendationEnvelopeV2,
) -> None:
    empty = replace(envelope, dimensions=())
    report = evaluate_recommendations_v2(empty)
    assert RecommendationFindingCode.COLLECTION_BOUND_INVALID in report.findings
    forged = object.__new__(RecommendationEnvelopeV2)
    forged_report = evaluate_recommendations_v2(forged)
    assert forged_report.status is RecommendationEvaluationStatus.UNEVALUABLE
    assert repr(envelope).endswith("(<redacted-st0804-v2>)")
    with pytest.raises(TypeError, match="generic serialization"):
        envelope.__reduce_ex__(4)


def test_unavailable_report_never_manufactures_zero_or_winner() -> None:
    report = unavailable_recommendation_report(
        ArticleVersionId(UUID("11111111-1111-4111-8111-111111111111"))
    )
    report.require_valid()
    assert report.status is RecommendationEvaluationStatus.UNEVALUABLE
    assert report.findings == (RecommendationFindingCode.INPUT_UNAVAILABLE,)
    assert report.candidates == ()
    assert report.ranking_order == ()
    assert report.explanation_json is None


def test_decision_and_collection_hashes_are_order_independent(
    envelope: RecommendationEnvelopeV2,
) -> None:
    assert decision_context_sha256(envelope.context) == envelope.context.binding_sha256
    assert dimension_set_sha256(envelope.dimensions) == dimension_set_sha256(
        tuple(reversed(envelope.dimensions))
    )
    for permutation in itertools.permutations(envelope.assessments):
        assert assessment_set_sha256(permutation) == envelope.assessment_set_sha256
        assert (
            recommendation_input_sha256(
                rehash_envelope(replace(envelope, assessments=permutation))
            )
            == envelope.recommendation_input_sha256
        )


def test_construction_errors_are_closed() -> None:
    with pytest.raises(RecommendationRuntimeValueError) as captured:
        runtime.normalization_decision_sha256(
            input_sha256=Sha256Digest("a" * 64),
            basis=NormalizationBasis.VALIDATED_SPECIFICATION,
            normalized_score=Decimal("NaN"),
        )
    assert str(captured.value) == "INVALID_RECOMMENDATION_RUNTIME_VALUE"

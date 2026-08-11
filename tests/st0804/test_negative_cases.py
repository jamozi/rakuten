"""Fail-closed, finance-separation, and no-bypass tests for ST-0804."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import cast

import pytest

from conftest import axis, rule, valid_recommendation_input
from raos.domain.editorial.comparison_validation import (
    ComparisonFieldName,
    EvidenceId,
    ProductId,
)
from raos.domain.editorial.recommendation import (
    ConflictState,
    DimensionAssessment,
    HardConstraintState,
    RecommendationDecision,
    RecommendationDimension,
    RecommendationFindingCode,
    RecommendationInput,
    ReferenceId,
    RuleBinding,
    Sha256Digest,
    StalenessState,
    generate_recommendations,
)


def _assert_blocked(
    value: object,
    expected: RecommendationFindingCode,
) -> None:
    report = generate_recommendations(value)
    assert report.decision is RecommendationDecision.BLOCK
    assert expected in report.findings
    assert report.candidates == ()
    assert report.ranking_order == ()
    assert report.explanation_json is None
    assert report.explanation_sha256 is None
    assert report.publication_authorized is False
    assert report.production_eligible is False


def test_invalid_or_mismatched_st0803_comparison_report_blocks() -> None:
    value = valid_recommendation_input()
    contaminated_axis = axis(1, field_name="AFFILIATE_RATE")
    invalid_comparison = replace(
        value.comparison,
        axes=(contaminated_axis, *value.comparison.axes[1:]),
    )
    forged_report = replace(value.comparison_report, publication_authorized=True)

    invalid = generate_recommendations(replace(value, comparison=invalid_comparison))
    forged = generate_recommendations(replace(value, comparison_report=forged_report))

    assert RecommendationFindingCode.COMPARISON_INPUT_INVALID in invalid.findings
    assert RecommendationFindingCode.PROHIBITED_INPUT in invalid.findings
    assert RecommendationFindingCode.COMPARISON_REPORT_INVALID in invalid.findings
    assert RecommendationFindingCode.COMPARISON_REPORT_INVALID in forged.findings


@pytest.mark.parametrize(
    "forbidden_reference",
    [
        "AFFILIATE_RATE",
        "COMMISSION",
        "EPC",
        "RPM",
        "REVENUE",
        "CONFIRMED_COMMISSION",
        "CONTRIBUTION_PROFIT",
        "SPONSOR_BENEFIT",
        "FINANCE_SCORE",
        "COST_SIGNAL",
        "PROFIT_MARGIN",
    ],
)
def test_finance_and_business_vocabulary_is_rejected_everywhere(
    forbidden_reference: str,
) -> None:
    value = valid_recommendation_input()
    contaminated = replace(
        value,
        context=replace(
            value.context,
            target_reader_ref=ReferenceId(forbidden_reference),
        ),
    )

    _assert_blocked(contaminated, RecommendationFindingCode.PROHIBITED_INPUT)


@pytest.mark.parametrize(
    "field_name",
    [
        "AFFILIATE_RATE",
        "COMMISSION",
        "EPC",
        "RPM",
        "REVENUE",
        "CONFIRMED_COMMISSION",
        "CONTRIBUTION_PROFIT",
        "SPONSOR_BENEFIT",
        "FINANCE_VALUE",
        "COST_VALUE",
        "PROFIT_VALUE",
    ],
)
def test_forbidden_st0803_axis_cannot_enter_recommendation(field_name: str) -> None:
    value = valid_recommendation_input()
    contaminated_axis = replace(
        value.comparison.axes[0],
        field_name=ComparisonFieldName(field_name),
    )
    contaminated = replace(
        value,
        comparison=replace(
            value.comparison,
            axes=(contaminated_axis, *value.comparison.axes[1:]),
        ),
    )

    _assert_blocked(contaminated, RecommendationFindingCode.PROHIBITED_INPUT)


def test_mutable_collections_are_rejected_at_each_boundary() -> None:
    value = valid_recommendation_input()
    mutable_dimensions = cast(
        tuple[RecommendationDimension, ...],
        list(value.dimensions),
    )
    mutable_products = cast(
        tuple[ProductId, ...],
        list(value.candidate_universe.product_ids),
    )

    _assert_blocked(
        replace(value, dimensions=mutable_dimensions),
        RecommendationFindingCode.COLLECTION_TYPE_INVALID,
    )
    _assert_blocked(
        replace(
            value,
            candidate_universe=replace(
                value.candidate_universe,
                product_ids=mutable_products,
            ),
        ),
        RecommendationFindingCode.COLLECTION_TYPE_INVALID,
    )


def test_input_record_and_exact_value_subclasses_are_rejected() -> None:
    class RecommendationInputSubclass(RecommendationInput):
        pass

    class DimensionAssessmentSubclass(DimensionAssessment):
        pass

    class ReferenceIdSubclass(ReferenceId):
        pass

    value = valid_recommendation_input()
    input_subclass = RecommendationInputSubclass(
        comparison=value.comparison,
        comparison_report=value.comparison_report,
        context=value.context,
        methodology=value.methodology,
        candidate_universe=value.candidate_universe,
        dimensions=value.dimensions,
        assessments=value.assessments,
    )
    source = value.assessments[0]
    record_subclass = DimensionAssessmentSubclass(
        product_id=source.product_id,
        axis_id=source.axis_id,
        evidence_id=source.evidence_id,
        availability=source.availability,
        normalized_score=source.normalized_score,
        hard_constraint_state=source.hard_constraint_state,
        conflict_state=source.conflict_state,
        conflict_penalty=source.conflict_penalty,
        conflict_rule=source.conflict_rule,
        staleness_state=source.staleness_state,
        staleness_penalty=source.staleness_penalty,
        staleness_rule=source.staleness_rule,
    )
    reference_subclass = ReferenceIdSubclass("TARGET_READER_001")

    _assert_blocked(input_subclass, RecommendationFindingCode.INPUT_TYPE_INVALID)
    _assert_blocked(
        replace(value, assessments=(record_subclass, *value.assessments[1:])),
        RecommendationFindingCode.RECORD_TYPE_INVALID,
    )
    _assert_blocked(
        replace(
            value,
            context=replace(value.context, target_reader_ref=reference_subclass),
        ),
        RecommendationFindingCode.CONTEXT_INVALID,
    )


@pytest.mark.parametrize(
    "invalid_weight",
    [
        cast(Decimal, True),
        Decimal("0"),
        Decimal("-0.1"),
        Decimal("1.0001"),
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_weight_type_finiteness_and_closed_range_are_enforced(
    invalid_weight: Decimal,
) -> None:
    value = valid_recommendation_input()
    invalid = replace(
        value,
        dimensions=(
            replace(value.dimensions[0], weight=invalid_weight),
            *value.dimensions[1:],
        ),
    )

    _assert_blocked(invalid, RecommendationFindingCode.WEIGHT_INVALID)


@pytest.mark.parametrize(
    "invalid_score",
    [
        cast(Decimal, False),
        Decimal("-0.0001"),
        Decimal("1.0001"),
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_score_type_finiteness_and_normalized_range_are_enforced(
    invalid_score: Decimal,
) -> None:
    value = valid_recommendation_input()
    invalid = replace(
        value,
        assessments=(
            replace(value.assessments[0], normalized_score=invalid_score),
            *value.assessments[1:],
        ),
    )

    _assert_blocked(invalid, RecommendationFindingCode.SCORE_INVALID)


@pytest.mark.parametrize(
    "invalid_penalty",
    [
        cast(Decimal, True),
        Decimal("-0.1"),
        Decimal("20.0001"),
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_penalty_type_finiteness_and_closed_range_are_enforced(
    invalid_penalty: Decimal,
) -> None:
    value = valid_recommendation_input()
    invalid = replace(
        value,
        assessments=(
            replace(
                value.assessments[0],
                conflict_state=ConflictState.CONFLICTING,
                conflict_penalty=invalid_penalty,
            ),
            *value.assessments[1:],
        ),
    )

    _assert_blocked(invalid, RecommendationFindingCode.PENALTY_INVALID)


@pytest.mark.parametrize(
    ("conflict_state", "conflict_penalty", "staleness_state", "staleness_penalty"),
    [
        (ConflictState.CONFLICTING, Decimal("0"), StalenessState.CURRENT, Decimal("0")),
        (ConflictState.NONE, Decimal("1"), StalenessState.CURRENT, Decimal("0")),
        (ConflictState.NONE, Decimal("0"), StalenessState.NEAR_EXPIRY, Decimal("0")),
        (ConflictState.NONE, Decimal("0"), StalenessState.STALE, Decimal("0")),
        (ConflictState.NONE, Decimal("0"), StalenessState.CURRENT, Decimal("1")),
    ],
)
def test_penalty_components_must_match_state_and_noncurrent_requires_positive(
    conflict_state: ConflictState,
    conflict_penalty: Decimal,
    staleness_state: StalenessState,
    staleness_penalty: Decimal,
) -> None:
    value = valid_recommendation_input()
    invalid = replace(
        value,
        assessments=(
            replace(
                value.assessments[0],
                conflict_state=conflict_state,
                conflict_penalty=conflict_penalty,
                staleness_state=staleness_state,
                staleness_penalty=staleness_penalty,
            ),
            *value.assessments[1:],
        ),
    )

    _assert_blocked(invalid, RecommendationFindingCode.PENALTY_INVALID)


def test_duplicate_missing_and_foreign_assessment_coordinates_block() -> None:
    value = valid_recommendation_input()
    duplicate = replace(
        value,
        assessments=(
            value.assessments[0],
            value.assessments[0],
            *value.assessments[1:],
        ),
    )
    missing = replace(value, assessments=value.assessments[:-1])
    foreign = replace(
        value.assessments[0],
        product_id=ProductId("PRODUCT_FOREIGN"),
    )

    _assert_blocked(duplicate, RecommendationFindingCode.DUPLICATE_ASSESSMENT)
    _assert_blocked(missing, RecommendationFindingCode.MISSING_ASSESSMENT)
    _assert_blocked(
        replace(value, assessments=(foreign, *value.assessments[1:])),
        RecommendationFindingCode.ASSESSMENT_COORDINATE_INVALID,
    )


def test_duplicate_missing_dimensions_and_candidate_mismatch_block() -> None:
    value = valid_recommendation_input()
    duplicate_dimensions = replace(
        value,
        dimensions=(value.dimensions[0], value.dimensions[0]),
    )
    missing_dimensions = replace(value, dimensions=value.dimensions[:-1])
    candidate_mismatch = replace(
        value,
        candidate_universe=replace(
            value.candidate_universe,
            product_ids=value.candidate_universe.product_ids[:-1],
        ),
    )

    _assert_blocked(
        duplicate_dimensions,
        RecommendationFindingCode.DUPLICATE_DIMENSION,
    )
    _assert_blocked(
        missing_dimensions,
        RecommendationFindingCode.DIMENSION_SET_MISMATCH,
    )
    _assert_blocked(
        candidate_mismatch,
        RecommendationFindingCode.CANDIDATE_SET_MISMATCH,
    )


def test_evidence_and_penalty_rule_mismatches_block() -> None:
    value = valid_recommendation_input()
    wrong_evidence = replace(
        value.assessments[0],
        evidence_id=EvidenceId("EVIDENCE_WRONG"),
    )
    wrong_rule = replace(
        value.assessments[0],
        conflict_rule=rule("OTHER_CONFLICT"),
    )

    _assert_blocked(
        replace(value, assessments=(wrong_evidence, *value.assessments[1:])),
        RecommendationFindingCode.EVIDENCE_BINDING_INVALID,
    )
    _assert_blocked(
        replace(value, assessments=(wrong_rule, *value.assessments[1:])),
        RecommendationFindingCode.RULE_BINDING_INVALID,
    )


def test_hard_constraint_and_runtime_enum_state_mismatches_block() -> None:
    value = valid_recommendation_input()
    nonhard_with_pass = replace(
        value.assessments[1],
        hard_constraint_state=HardConstraintState.PASS,
    )
    string_state = replace(
        value.assessments[0],
        conflict_state=cast(ConflictState, "NONE"),
    )

    _assert_blocked(
        replace(
            value,
            assessments=(
                value.assessments[0],
                nonhard_with_pass,
                *value.assessments[2:],
            ),
        ),
        RecommendationFindingCode.STATE_INVALID,
    )
    _assert_blocked(
        replace(value, assessments=(string_state, *value.assessments[1:])),
        RecommendationFindingCode.STATE_INVALID,
    )


def test_wrong_canonical_methodology_hash_and_rule_subclass_block() -> None:
    class RuleBindingSubclass(RuleBinding):
        pass

    value = valid_recommendation_input()
    wrong_methodology = replace(
        value.methodology,
        methodology_sha256=Sha256Digest("0" * 64),
    )
    source_rule = value.methodology.coverage_rule
    subclass_rule = RuleBindingSubclass(
        rule_id=source_rule.rule_id,
        version=source_rule.version,
        sha256=source_rule.sha256,
    )
    subclass_methodology = replace(
        value.methodology,
        coverage_rule=subclass_rule,
    )

    _assert_blocked(
        replace(value, methodology=wrong_methodology),
        RecommendationFindingCode.METHODOLOGY_INVALID,
    )
    _assert_blocked(
        replace(value, methodology=subclass_methodology),
        RecommendationFindingCode.RULE_BINDING_INVALID,
    )


def test_findings_are_closed_ordered_deduplicated_and_redacted() -> None:
    value = valid_recommendation_input()
    invalid = replace(
        value,
        dimensions=(
            replace(value.dimensions[0], weight=Decimal("0")),
            replace(value.dimensions[0], weight=Decimal("0")),
        ),
        context=replace(
            value.context,
            target_reader_ref=ReferenceId("AFFILIATE_RATE"),
        ),
    )

    first = generate_recommendations(invalid)
    second = generate_recommendations(invalid)
    expected_order = tuple(
        code for code in RecommendationFindingCode if code in set(first.findings)
    )

    assert first == second
    assert first.findings == expected_order
    assert len(first.findings) == len(set(first.findings))
    assert repr(first) == "RecommendationReport(<redacted>)"
    for raw_value in ("PRODUCT_01", "AXIS_01", "AFFILIATE_RATE", "ARTICLE_001"):
        assert raw_value not in repr(first)
        assert raw_value not in str(first)


def test_bypassed_structural_injection_is_rejected_without_echo() -> None:
    value = valid_recommendation_input()
    unsafe = object.__new__(ReferenceId)
    raw_value = 'SAFE"},"revenue":1'
    object.__setattr__(unsafe, "value", raw_value)
    contaminated = replace(
        value,
        context=replace(value.context, target_reader_ref=unsafe),
    )

    report = generate_recommendations(contaminated)

    assert report.decision is RecommendationDecision.BLOCK
    assert RecommendationFindingCode.CONTEXT_INVALID in report.findings
    assert raw_value not in repr(report)

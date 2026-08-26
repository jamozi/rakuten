"""Synthetic builders for the isolated ST-0804 recommendation engine."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.domain.editorial.comparison_validation import (  # noqa: E402
    AxisId,
    ComparisonAxis,
    ComparisonCell,
    ComparisonCellState,
    ComparisonFieldName,
    ComparisonInput,
    ComparisonMode,
    ComparisonProduct,
    ComparisonScalar,
    EvidenceBinding,
    EvidenceId,
    IdentityId,
    ProductId,
    ProductIdentityStatus,
    UnitCode,
    VariantId,
    validate_comparison,
)
from raos.domain.editorial.recommendation import (  # noqa: E402
    CANONICAL_METHODOLOGY_ID,
    CANONICAL_METHODOLOGY_SHA256,
    CANONICAL_METHODOLOGY_VERSION,
    ArticleRecommendationContext,
    CandidateUniverse,
    ConflictState,
    DimensionAssessment,
    EvidenceAvailability,
    HardConstraintState,
    MethodologyBinding,
    RecommendationDimension,
    RecommendationInput,
    ReferenceId,
    RuleBinding,
    Sha256Digest,
    StalenessState,
    VersionRef,
)


ZERO = Decimal("0")
TEST_DIGEST = Sha256Digest("1" * 64)


def product(index: int) -> ComparisonProduct:
    suffix = f"{index:02d}"
    return ComparisonProduct(
        product_id=ProductId(f"PRODUCT_{suffix}"),
        identity_status=ProductIdentityStatus.PRE_RESOLVED_TEST_ONLY,
        identity_id=IdentityId(f"IDENTITY_{suffix}"),
        variant_id=VariantId(f"VARIANT_{suffix}"),
    )


def axis(index: int, *, field_name: str | None = None) -> ComparisonAxis:
    suffix = f"{index:02d}"
    return ComparisonAxis(
        axis_id=AxisId(f"AXIS_{suffix}"),
        field_name=ComparisonFieldName(field_name or f"FEATURE_{suffix}"),
        unit=UnitCode("POINT"),
    )


def known_cell(
    selected_product: ComparisonProduct,
    selected_axis: ComparisonAxis,
) -> ComparisonCell:
    assert selected_product.identity_id is not None
    assert selected_product.variant_id is not None
    evidence = EvidenceBinding(
        evidence_id=EvidenceId(
            f"EVIDENCE_{selected_product.product_id.value}_{selected_axis.axis_id.value}"
        ),
        product_id=selected_product.product_id,
        axis_id=selected_axis.axis_id,
        identity_id=selected_product.identity_id,
        variant_id=selected_product.variant_id,
    )
    return ComparisonCell(
        product_id=selected_product.product_id,
        axis_id=selected_axis.axis_id,
        state=ComparisonCellState.KNOWN,
        value=ComparisonScalar(1),
        unit=selected_axis.unit,
        evidence=evidence,
        identity_id=selected_product.identity_id,
        variant_id=selected_product.variant_id,
    )


def unknown_cell(
    selected_product: ComparisonProduct,
    selected_axis: ComparisonAxis,
) -> ComparisonCell:
    return ComparisonCell(
        product_id=selected_product.product_id,
        axis_id=selected_axis.axis_id,
        state=ComparisonCellState.UNKNOWN,
        value=None,
        unit=None,
        evidence=None,
        identity_id=None,
        variant_id=None,
    )


def rule(name: str, *, digest: str = "2" * 64) -> RuleBinding:
    return RuleBinding(
        rule_id=ReferenceId(f"{name}_RULE"),
        version=VersionRef("1.0.0"),
        sha256=Sha256Digest(digest),
    )


def methodology() -> MethodologyBinding:
    return MethodologyBinding(
        methodology_id=ReferenceId(CANONICAL_METHODOLOGY_ID),
        methodology_version=VersionRef(CANONICAL_METHODOLOGY_VERSION),
        methodology_sha256=Sha256Digest(CANONICAL_METHODOLOGY_SHA256),
        hard_constraint_rule=rule("HARD_CONSTRAINT", digest="3" * 64),
        weighting_rule=rule("WEIGHTING", digest="4" * 64),
        normalization_rule=rule("NORMALIZATION", digest="5" * 64),
        coverage_rule=rule("COVERAGE", digest="6" * 64),
        conflict_penalty_rule=rule("CONFLICT_PENALTY", digest="7" * 64),
        staleness_penalty_rule=rule("STALENESS_PENALTY", digest="8" * 64),
        tie_rule=rule("TIE", digest="9" * 64),
    )


def recommendation_input(
    scores: tuple[tuple[Decimal | None, ...], ...],
    *,
    weights: tuple[Decimal, ...] | None = None,
    critical_axes: frozenset[int] = frozenset({0}),
    hard_axes: frozenset[int] = frozenset({0}),
    hard_states: dict[tuple[int, int], HardConstraintState] | None = None,
    conflicts: dict[tuple[int, int], tuple[ConflictState, Decimal]] | None = None,
    staleness: dict[tuple[int, int], tuple[StalenessState, Decimal]] | None = None,
    article_id: str = "ARTICLE_001",
) -> RecommendationInput:
    assert len(scores) >= 2
    axis_count = len(scores[0])
    assert axis_count >= 1
    assert all(len(row) == axis_count for row in scores)
    selected_weights = weights or tuple(Decimal("1") for _ in range(axis_count))
    assert len(selected_weights) == axis_count
    hard_states = hard_states or {}
    conflicts = conflicts or {}
    staleness = staleness or {}

    products = tuple(product(index) for index in range(1, len(scores) + 1))
    axes = tuple(axis(index) for index in range(1, axis_count + 1))
    cells = tuple(
        (
            unknown_cell(selected_product, selected_axis)
            if scores[product_index][axis_index] is None
            else known_cell(selected_product, selected_axis)
        )
        for product_index, selected_product in enumerate(products)
        for axis_index, selected_axis in enumerate(axes)
    )
    comparison = ComparisonInput(
        mode=ComparisonMode.TEST_ONLY,
        products=products,
        axes=axes,
        cells=cells,
        show_unknown_values=True,
    )
    comparison_report = validate_comparison(comparison)
    assert comparison_report.passed

    selected_methodology = methodology()
    dimensions = tuple(
        RecommendationDimension(
            axis_id=selected_axis.axis_id,
            definition_ref=ReferenceId(f"DIMENSION_{axis_index + 1:02d}"),
            definition_version=VersionRef("1.0.0"),
            definition_sha256=TEST_DIGEST,
            weight=selected_weights[axis_index],
            critical=axis_index in critical_axes,
            hard_constraint=axis_index in hard_axes,
        )
        for axis_index, selected_axis in enumerate(axes)
    )
    cell_by_coordinate = {
        (cell.product_id.value, cell.axis_id.value): cell for cell in cells
    }
    assessments: list[DimensionAssessment] = []
    for product_index, selected_product in enumerate(products):
        for axis_index, selected_axis in enumerate(axes):
            coordinate = (product_index, axis_index)
            score = scores[product_index][axis_index]
            cell = cell_by_coordinate[
                (selected_product.product_id.value, selected_axis.axis_id.value)
            ]
            conflict_state, conflict_penalty = conflicts.get(
                coordinate,
                (ConflictState.NONE, ZERO),
            )
            staleness_state, staleness_penalty = staleness.get(
                coordinate,
                (StalenessState.CURRENT, ZERO),
            )
            if axis_index in hard_axes:
                default_hard_state = (
                    HardConstraintState.UNKNOWN
                    if score is None
                    else HardConstraintState.PASS
                )
                hard_state = hard_states.get(coordinate, default_hard_state)
            else:
                hard_state = HardConstraintState.NOT_APPLICABLE
            assessments.append(
                DimensionAssessment(
                    product_id=selected_product.product_id,
                    axis_id=selected_axis.axis_id,
                    evidence_id=(
                        cell.evidence.evidence_id if cell.evidence is not None else None
                    ),
                    availability=(
                        EvidenceAvailability.UNKNOWN
                        if score is None
                        else EvidenceAvailability.AVAILABLE
                    ),
                    normalized_score=score,
                    hard_constraint_state=hard_state,
                    conflict_state=conflict_state,
                    conflict_penalty=conflict_penalty,
                    conflict_rule=selected_methodology.conflict_penalty_rule,
                    staleness_state=staleness_state,
                    staleness_penalty=staleness_penalty,
                    staleness_rule=selected_methodology.staleness_penalty_rule,
                )
            )

    return RecommendationInput(
        comparison=comparison,
        comparison_report=comparison_report,
        context=ArticleRecommendationContext(
            article_id=ReferenceId(article_id),
            article_version_id=ReferenceId("ARTICLE_VERSION_001"),
            decision_context_id=ReferenceId("DECISION_CONTEXT_001"),
            decision_context_version=VersionRef("1.0.0"),
            decision_context_sha256=TEST_DIGEST,
            target_reader_ref=ReferenceId("TARGET_READER_001"),
            use_case_ref=ReferenceId("USE_CASE_001"),
            budget_context_ref=ReferenceId("BUDGET_CONTEXT_001"),
        ),
        methodology=selected_methodology,
        candidate_universe=CandidateUniverse(
            universe_id=ReferenceId("CANDIDATE_UNIVERSE_001"),
            universe_version=VersionRef("1.0.0"),
            universe_sha256=TEST_DIGEST,
            scope_ref=ReferenceId("UNIVERSE_SCOPE_001"),
            selection_criteria_ref=ReferenceId("SELECTION_CRITERIA_001"),
            product_ids=tuple(
                selected_product.product_id for selected_product in products
            ),
        ),
        dimensions=dimensions,
        assessments=tuple(assessments),
    )


def valid_recommendation_input() -> RecommendationInput:
    return recommendation_input(
        (
            (Decimal("0.90"), Decimal("0.80")),
            (Decimal("0.88"), Decimal("0.80")),
            (Decimal("0.70"), Decimal("0.70")),
        )
    )


def with_revalidated_comparison(
    value: RecommendationInput,
    comparison: ComparisonInput,
) -> RecommendationInput:
    return replace(
        value,
        comparison=comparison,
        comparison_report=validate_comparison(comparison),
    )

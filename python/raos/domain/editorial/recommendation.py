"""Pure deterministic ST-0804 editorial recommendation calculation.

The engine accepts only an already validated ST-0803 comparison matrix and
strict, pre-resolved recommendation inputs.  It does not normalize facts,
resolve identity, author penalty policy, persist state, authorize publication,
or call any external system.  Caller-controlled values are redacted from
representations and validation failures expose closed codes only.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from enum import Enum
import hashlib
import json
import re
from typing import NoReturn, TypeAlias

from raos.domain.editorial.comparison_validation import (
    AxisId,
    ComparisonCell,
    ComparisonCellState,
    ComparisonFindingCode,
    ComparisonInput,
    ComparisonScalar,
    ComparisonValidationReport,
    EvidenceId,
    ProductId,
    validate_comparison,
)


CANONICAL_METHODOLOGY_ID = "RAOS-CONTENT-RECO-001"
CANONICAL_METHODOLOGY_VERSION = "1.0.0"
CANONICAL_METHODOLOGY_SHA256 = (
    "fb71ad7900c7f688f305e10256b49563281893408e54d8668aac02efa7e57862"
)
INTERNAL_SCORE_QUANTUM = Decimal("0.0001")
MINIMUM_RANK_COVERAGE = Decimal("0.80")
MINIMUM_PRIMARY_COVERAGE = Decimal("0.90")
MAXIMUM_UNCERTAINTY_PENALTY = Decimal("20")
CO_RECOMMEND_MAXIMUM_DIFFERENCE = Decimal("2.0")

_REFERENCE = re.compile(r"[A-Z0-9][A-Z0-9_.:-]{0,126}\Z", re.ASCII)
_VERSION = re.compile(r"[A-Z0-9][A-Z0-9_.-]{0,62}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_FORBIDDEN_COMPONENTS = frozenset(
    {
        "AFFILIATE",
        "BENEFIT",
        "COMMISSION",
        "COST",
        "EARNINGS",
        "EPC",
        "FINANCE",
        "MARGIN",
        "MONETIZATION",
        "PAYOUT",
        "PROFIT",
        "RATE",
        "REVENUE",
        "RPM",
        "SPONSOR",
        "SPONSORSHIP",
    }
)
_DECIMAL_MAX_DIGITS = 28
_DECIMAL_MIN_EXPONENT = -12
_DECIMAL_MAX_EXPONENT = 12


class RecommendationDecision(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"


class ExecutionStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


class EvidenceAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNKNOWN = "UNKNOWN"


class ConflictState(str, Enum):
    NONE = "NONE"
    CONFLICTING = "CONFLICTING"


class StalenessState(str, Enum):
    CURRENT = "CURRENT"
    NEAR_EXPIRY = "NEAR_EXPIRY"
    STALE = "STALE"


class HardConstraintState(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class CandidateEligibility(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"


class RankingState(str, Enum):
    RANKED = "RANKED"
    INELIGIBLE = "INELIGIBLE"
    UNRANKED_CRITICAL_EVIDENCE = "UNRANKED_CRITICAL_EVIDENCE"
    UNRANKED_LOW_COVERAGE = "UNRANKED_LOW_COVERAGE"


class CandidateReasonCode(str, Enum):
    HARD_CONSTRAINT_FAILED = "HARD_CONSTRAINT_FAILED"
    HARD_CONSTRAINT_UNKNOWN = "HARD_CONSTRAINT_UNKNOWN"
    CRITICAL_EVIDENCE_UNKNOWN = "CRITICAL_EVIDENCE_UNKNOWN"
    CRITICAL_EVIDENCE_CONFLICT = "CRITICAL_EVIDENCE_CONFLICT"
    CRITICAL_EVIDENCE_STALE = "CRITICAL_EVIDENCE_STALE"
    COVERAGE_BELOW_RANK_THRESHOLD = "COVERAGE_BELOW_RANK_THRESHOLD"


class RecommendationFindingCode(str, Enum):
    INPUT_TYPE_INVALID = "INPUT_TYPE_INVALID"
    COMPARISON_INPUT_INVALID = "COMPARISON_INPUT_INVALID"
    COMPARISON_REPORT_INVALID = "COMPARISON_REPORT_INVALID"
    COLLECTION_TYPE_INVALID = "COLLECTION_TYPE_INVALID"
    RECORD_TYPE_INVALID = "RECORD_TYPE_INVALID"
    CONTEXT_INVALID = "CONTEXT_INVALID"
    METHODOLOGY_INVALID = "METHODOLOGY_INVALID"
    RULE_BINDING_INVALID = "RULE_BINDING_INVALID"
    CANDIDATE_UNIVERSE_INVALID = "CANDIDATE_UNIVERSE_INVALID"
    DUPLICATE_CANDIDATE = "DUPLICATE_CANDIDATE"
    CANDIDATE_SET_MISMATCH = "CANDIDATE_SET_MISMATCH"
    DIMENSION_INVALID = "DIMENSION_INVALID"
    DUPLICATE_DIMENSION = "DUPLICATE_DIMENSION"
    DIMENSION_SET_MISMATCH = "DIMENSION_SET_MISMATCH"
    WEIGHT_INVALID = "WEIGHT_INVALID"
    ASSESSMENT_COORDINATE_INVALID = "ASSESSMENT_COORDINATE_INVALID"
    DUPLICATE_ASSESSMENT = "DUPLICATE_ASSESSMENT"
    MISSING_ASSESSMENT = "MISSING_ASSESSMENT"
    EVIDENCE_BINDING_INVALID = "EVIDENCE_BINDING_INVALID"
    STATE_INVALID = "STATE_INVALID"
    SCORE_INVALID = "SCORE_INVALID"
    PENALTY_INVALID = "PENALTY_INVALID"
    PROHIBITED_INPUT = "PROHIBITED_INPUT"


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted>)"

    def __str__(self) -> str:
        return "<redacted>"


class RecommendationValueConstructionError(ValueError):
    """Closed construction failure that never includes caller input."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("INVALID_EXACT_VALUE")


def _fail_value_construction() -> NoReturn:
    raise RecommendationValueConstructionError() from None


@dataclass(frozen=True, slots=True, repr=False)
class ReferenceId(_Redacted):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _REFERENCE.fullmatch(self.value) is None:
            _fail_value_construction()


@dataclass(frozen=True, slots=True, repr=False)
class VersionRef(_Redacted):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _VERSION.fullmatch(self.value) is None:
            _fail_value_construction()


@dataclass(frozen=True, slots=True, repr=False)
class Sha256Digest(_Redacted):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _SHA256.fullmatch(self.value) is None:
            _fail_value_construction()


@dataclass(frozen=True, slots=True, repr=False)
class RuleBinding(_Redacted):
    rule_id: ReferenceId
    version: VersionRef
    sha256: Sha256Digest


@dataclass(frozen=True, slots=True, repr=False)
class ArticleRecommendationContext(_Redacted):
    article_id: ReferenceId
    article_version_id: ReferenceId
    decision_context_id: ReferenceId
    decision_context_version: VersionRef
    decision_context_sha256: Sha256Digest
    target_reader_ref: ReferenceId
    use_case_ref: ReferenceId
    budget_context_ref: ReferenceId


@dataclass(frozen=True, slots=True, repr=False)
class MethodologyBinding(_Redacted):
    methodology_id: ReferenceId
    methodology_version: VersionRef
    methodology_sha256: Sha256Digest
    hard_constraint_rule: RuleBinding
    weighting_rule: RuleBinding
    normalization_rule: RuleBinding
    coverage_rule: RuleBinding
    conflict_penalty_rule: RuleBinding
    staleness_penalty_rule: RuleBinding
    tie_rule: RuleBinding


@dataclass(frozen=True, slots=True, repr=False)
class CandidateUniverse(_Redacted):
    universe_id: ReferenceId
    universe_version: VersionRef
    universe_sha256: Sha256Digest
    scope_ref: ReferenceId
    selection_criteria_ref: ReferenceId
    product_ids: tuple[ProductId, ...]


@dataclass(frozen=True, slots=True, repr=False)
class RecommendationDimension(_Redacted):
    axis_id: AxisId
    definition_ref: ReferenceId
    definition_version: VersionRef
    definition_sha256: Sha256Digest
    weight: Decimal
    critical: bool
    hard_constraint: bool


@dataclass(frozen=True, slots=True, repr=False)
class DimensionAssessment(_Redacted):
    product_id: ProductId
    axis_id: AxisId
    evidence_id: EvidenceId | None
    availability: EvidenceAvailability
    normalized_score: Decimal | None
    hard_constraint_state: HardConstraintState
    conflict_state: ConflictState
    conflict_penalty: Decimal
    conflict_rule: RuleBinding
    staleness_state: StalenessState
    staleness_penalty: Decimal
    staleness_rule: RuleBinding


@dataclass(frozen=True, slots=True, repr=False)
class RecommendationInput(_Redacted):
    comparison: ComparisonInput
    comparison_report: ComparisonValidationReport
    context: ArticleRecommendationContext
    methodology: MethodologyBinding
    candidate_universe: CandidateUniverse
    dimensions: tuple[RecommendationDimension, ...]
    assessments: tuple[DimensionAssessment, ...]


@dataclass(frozen=True, slots=True, repr=False)
class CandidateRecommendation(_Redacted):
    product_id: ProductId
    eligibility: CandidateEligibility
    ranking_state: RankingState
    reason_codes: tuple[CandidateReasonCode, ...]
    weighted_evidence_coverage: Decimal
    base_score: Decimal | None
    conflict_penalty: Decimal
    staleness_penalty: Decimal
    uncertainty_penalty: Decimal | None
    final_score: Decimal | None
    public_score: int | None
    rank_group: int | None
    tie_group: int | None
    group_anchor_score: Decimal | None
    co_recommended: bool
    strict_order_allowed: bool
    primary_recommendation_allowed: bool
    unknown_axis_ids: tuple[AxisId, ...]
    conflicting_axis_ids: tuple[AxisId, ...]
    stale_axis_ids: tuple[AxisId, ...]


@dataclass(frozen=True, slots=True, repr=False)
class RecommendationReport(_Redacted):
    decision: RecommendationDecision
    findings: tuple[RecommendationFindingCode, ...]
    candidates: tuple[CandidateRecommendation, ...]
    ranking_order: tuple[ProductId, ...]
    comparison_sha256: str | None
    explanation_json: str | None
    explanation_sha256: str | None
    publication_authorized: bool
    production_eligible: bool
    formal_test_status: ExecutionStatus
    live_validation_status: ExecutionStatus
    staging_status: ExecutionStatus
    release_status: ExecutionStatus
    production_status: ExecutionStatus

    @property
    def passed(self) -> bool:
        return self.decision is RecommendationDecision.PASS


JsonScalar: TypeAlias = str | int | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def _blocked(findings: set[RecommendationFindingCode]) -> RecommendationReport:
    ordered = tuple(code for code in RecommendationFindingCode if code in findings)
    return RecommendationReport(
        decision=RecommendationDecision.BLOCK,
        findings=ordered,
        candidates=(),
        ranking_order=(),
        comparison_sha256=None,
        explanation_json=None,
        explanation_sha256=None,
        publication_authorized=False,
        production_eligible=False,
        formal_test_status=ExecutionStatus.NOT_EXECUTED,
        live_validation_status=ExecutionStatus.NOT_EXECUTED,
        staging_status=ExecutionStatus.NOT_EXECUTED,
        release_status=ExecutionStatus.NOT_EXECUTED,
        production_status=ExecutionStatus.NOT_EXECUTED,
    )


def _valid_reference(value: object) -> bool:
    return (
        type(value) is ReferenceId
        and type(value.value) is str
        and _REFERENCE.fullmatch(value.value) is not None
    )


def _valid_version(value: object) -> bool:
    return (
        type(value) is VersionRef
        and type(value.value) is str
        and _VERSION.fullmatch(value.value) is not None
    )


def _valid_sha256(value: object) -> bool:
    return (
        type(value) is Sha256Digest
        and type(value.value) is str
        and _SHA256.fullmatch(value.value) is not None
    )


def _valid_comparison_token(value: object, expected_type: type[object]) -> bool:
    if type(value) is not expected_type:
        return False
    raw_value: object = getattr(value, "value", None)
    return type(raw_value) is str and _REFERENCE.fullmatch(raw_value) is not None


def _has_forbidden_text(value: str) -> bool:
    components = tuple(
        component for component in re.split(r"[^A-Z0-9]+", value.upper()) if component
    )
    return any(component in _FORBIDDEN_COMPONENTS for component in components)


def _has_forbidden_vocabulary(value: ReferenceId) -> bool:
    return _has_forbidden_text(value.value)


def _valid_rule(value: object) -> bool:
    return (
        type(value) is RuleBinding
        and _valid_reference(value.rule_id)
        and _valid_version(value.version)
        and _valid_sha256(value.sha256)
    )


def _valid_decimal_shape(value: object) -> bool:
    if type(value) is not Decimal or not value.is_finite():
        return False
    representation = value.as_tuple()
    exponent = representation.exponent
    return (
        type(exponent) is int
        and len(representation.digits) <= _DECIMAL_MAX_DIGITS
        and _DECIMAL_MIN_EXPONENT <= exponent <= _DECIMAL_MAX_EXPONENT
    )


def _valid_decimal_range(
    value: object,
    *,
    minimum: Decimal,
    maximum: Decimal,
    minimum_inclusive: bool = True,
) -> bool:
    if not _valid_decimal_shape(value):
        return False
    assert type(value) is Decimal
    lower_valid = value >= minimum if minimum_inclusive else value > minimum
    return lower_valid and value <= maximum


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(INTERNAL_SCORE_QUANTUM, rounding=ROUND_HALF_EVEN)


def _decimal_text(value: Decimal, *, fixed_score: bool = False) -> str:
    if fixed_score:
        return format(_quantize(value), ".4f")
    if value.is_zero():
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _canonical_json(payload: JsonValue) -> str:
    return json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _hash_json(payload: JsonValue) -> tuple[str, str]:
    serialized = _canonical_json(payload)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return serialized, digest


def _scalar_payload(value: ComparisonScalar | None) -> JsonValue:
    if value is None:
        return None
    primitive = value.value
    if type(primitive) is str:
        return {"type": "string", "value": primitive}
    if type(primitive) is int:
        return {"type": "integer", "value": str(primitive)}
    assert type(primitive) is float
    return {"type": "float", "value": primitive.hex()}


def _comparison_payload(comparison: ComparisonInput) -> dict[str, JsonValue]:
    products: list[JsonValue] = []
    for product in sorted(comparison.products, key=lambda item: item.product_id.value):
        products.append(
            {
                "identity_id": (
                    product.identity_id.value
                    if product.identity_id is not None
                    else None
                ),
                "identity_status": product.identity_status.value,
                "product_id": product.product_id.value,
                "variant_id": (
                    product.variant_id.value if product.variant_id is not None else None
                ),
            }
        )

    axes: list[JsonValue] = []
    for axis in sorted(comparison.axes, key=lambda item: item.axis_id.value):
        axes.append(
            {
                "axis_id": axis.axis_id.value,
                "field_name": axis.field_name.value,
                "unit": axis.unit.value,
            }
        )

    cells: list[JsonValue] = []
    for cell in sorted(
        comparison.cells,
        key=lambda item: (item.product_id.value, item.axis_id.value),
    ):
        evidence: JsonValue = None
        if cell.evidence is not None:
            evidence = {
                "axis_id": cell.evidence.axis_id.value,
                "evidence_id": cell.evidence.evidence_id.value,
                "identity_id": cell.evidence.identity_id.value,
                "product_id": cell.evidence.product_id.value,
                "variant_id": cell.evidence.variant_id.value,
            }
        cells.append(
            {
                "axis_id": cell.axis_id.value,
                "evidence": evidence,
                "identity_id": (
                    cell.identity_id.value if cell.identity_id is not None else None
                ),
                "imputed": cell.imputed,
                "product_id": cell.product_id.value,
                "state": cell.state.value,
                "unit": cell.unit.value if cell.unit is not None else None,
                "value": _scalar_payload(cell.value),
                "variant_id": (
                    cell.variant_id.value if cell.variant_id is not None else None
                ),
            }
        )

    return {
        "axes": axes,
        "cells": cells,
        "mode": comparison.mode.value,
        "products": products,
        "show_unknown_values": comparison.show_unknown_values,
    }


def _rule_payload(rule: RuleBinding) -> dict[str, JsonValue]:
    return {
        "rule_id": rule.rule_id.value,
        "sha256": rule.sha256.value,
        "version": rule.version.value,
    }


def _methodology_payload(binding: MethodologyBinding) -> dict[str, JsonValue]:
    return {
        "conflict_penalty_rule": _rule_payload(binding.conflict_penalty_rule),
        "coverage_rule": _rule_payload(binding.coverage_rule),
        "hard_constraint_rule": _rule_payload(binding.hard_constraint_rule),
        "methodology_id": binding.methodology_id.value,
        "methodology_sha256": binding.methodology_sha256.value,
        "methodology_version": binding.methodology_version.value,
        "normalization_rule": _rule_payload(binding.normalization_rule),
        "staleness_penalty_rule": _rule_payload(binding.staleness_penalty_rule),
        "tie_rule": _rule_payload(binding.tie_rule),
        "weighting_rule": _rule_payload(binding.weighting_rule),
    }


def _candidate_payload(candidate: CandidateRecommendation) -> dict[str, JsonValue]:
    return {
        "base_score": (
            _decimal_text(candidate.base_score, fixed_score=True)
            if candidate.base_score is not None
            else None
        ),
        "co_recommended": candidate.co_recommended,
        "conflict_penalty": _decimal_text(candidate.conflict_penalty, fixed_score=True),
        "conflicting_axis_ids": [
            axis_id.value for axis_id in candidate.conflicting_axis_ids
        ],
        "eligibility": candidate.eligibility.value,
        "final_score": (
            _decimal_text(candidate.final_score, fixed_score=True)
            if candidate.final_score is not None
            else None
        ),
        "group_anchor_score": (
            _decimal_text(candidate.group_anchor_score, fixed_score=True)
            if candidate.group_anchor_score is not None
            else None
        ),
        "primary_recommendation_allowed": (candidate.primary_recommendation_allowed),
        "product_id": candidate.product_id.value,
        "public_score": candidate.public_score,
        "rank_group": candidate.rank_group,
        "ranking_state": candidate.ranking_state.value,
        "reason_codes": [code.value for code in candidate.reason_codes],
        "stale_axis_ids": [axis_id.value for axis_id in candidate.stale_axis_ids],
        "staleness_penalty": _decimal_text(
            candidate.staleness_penalty, fixed_score=True
        ),
        "strict_order_allowed": candidate.strict_order_allowed,
        "tie_group": candidate.tie_group,
        "uncertainty_penalty": (
            _decimal_text(candidate.uncertainty_penalty, fixed_score=True)
            if candidate.uncertainty_penalty is not None
            else None
        ),
        "unknown_axis_ids": [axis_id.value for axis_id in candidate.unknown_axis_ids],
        "weighted_evidence_coverage": _decimal_text(
            candidate.weighted_evidence_coverage, fixed_score=True
        ),
    }


def _validate_context(
    context: object,
    findings: set[RecommendationFindingCode],
) -> bool:
    if type(context) is not ArticleRecommendationContext:
        findings.add(RecommendationFindingCode.CONTEXT_INVALID)
        return False
    references = (
        context.article_id,
        context.article_version_id,
        context.decision_context_id,
        context.target_reader_ref,
        context.use_case_ref,
        context.budget_context_ref,
    )
    valid = (
        all(_valid_reference(reference) for reference in references)
        and _valid_version(context.decision_context_version)
        and _valid_sha256(context.decision_context_sha256)
    )
    if not valid:
        findings.add(RecommendationFindingCode.CONTEXT_INVALID)
        return False
    if any(_has_forbidden_vocabulary(reference) for reference in references):
        findings.add(RecommendationFindingCode.PROHIBITED_INPUT)
        return False
    return True


def _validate_methodology(
    methodology: object,
    findings: set[RecommendationFindingCode],
) -> bool:
    if type(methodology) is not MethodologyBinding:
        findings.add(RecommendationFindingCode.METHODOLOGY_INVALID)
        return False
    rules = (
        methodology.hard_constraint_rule,
        methodology.weighting_rule,
        methodology.normalization_rule,
        methodology.coverage_rule,
        methodology.conflict_penalty_rule,
        methodology.staleness_penalty_rule,
        methodology.tie_rule,
    )
    valid = (
        _valid_reference(methodology.methodology_id)
        and _valid_version(methodology.methodology_version)
        and _valid_sha256(methodology.methodology_sha256)
        and all(_valid_rule(rule) for rule in rules)
    )
    if not valid:
        findings.add(RecommendationFindingCode.RULE_BINDING_INVALID)
        return False
    if (
        methodology.methodology_id.value != CANONICAL_METHODOLOGY_ID
        or methodology.methodology_version.value != CANONICAL_METHODOLOGY_VERSION
        or methodology.methodology_sha256.value != CANONICAL_METHODOLOGY_SHA256
    ):
        findings.add(RecommendationFindingCode.METHODOLOGY_INVALID)
        return False
    references = (methodology.methodology_id, *(rule.rule_id for rule in rules))
    if any(_has_forbidden_vocabulary(reference) for reference in references):
        findings.add(RecommendationFindingCode.PROHIBITED_INPUT)
        return False
    return True


def _validate_universe(
    universe: object,
    comparison: ComparisonInput,
    findings: set[RecommendationFindingCode],
) -> bool:
    if type(universe) is not CandidateUniverse:
        findings.add(RecommendationFindingCode.CANDIDATE_UNIVERSE_INVALID)
        return False
    if type(universe.product_ids) is not tuple:
        findings.add(RecommendationFindingCode.COLLECTION_TYPE_INVALID)
        return False
    references = (
        universe.universe_id,
        universe.scope_ref,
        universe.selection_criteria_ref,
    )
    valid = (
        all(_valid_reference(reference) for reference in references)
        and _valid_version(universe.universe_version)
        and _valid_sha256(universe.universe_sha256)
    )
    if not valid:
        findings.add(RecommendationFindingCode.CANDIDATE_UNIVERSE_INVALID)
        return False
    if any(_has_forbidden_vocabulary(reference) for reference in references):
        findings.add(RecommendationFindingCode.PROHIBITED_INPUT)

    product_values: list[str] = []
    for product_id in universe.product_ids:
        if not _valid_comparison_token(product_id, ProductId):
            findings.add(RecommendationFindingCode.CANDIDATE_UNIVERSE_INVALID)
            continue
        product_values.append(product_id.value)
    if len(product_values) != len(set(product_values)):
        findings.add(RecommendationFindingCode.DUPLICATE_CANDIDATE)
    expected = {product.product_id.value for product in comparison.products}
    if set(product_values) != expected or len(product_values) != len(expected):
        findings.add(RecommendationFindingCode.CANDIDATE_SET_MISMATCH)
    return not any(
        code
        in {
            RecommendationFindingCode.CANDIDATE_UNIVERSE_INVALID,
            RecommendationFindingCode.DUPLICATE_CANDIDATE,
            RecommendationFindingCode.CANDIDATE_SET_MISMATCH,
            RecommendationFindingCode.PROHIBITED_INPUT,
        }
        for code in findings
    )


def _validate_dimensions(
    dimensions: tuple[RecommendationDimension, ...],
    comparison: ComparisonInput,
    findings: set[RecommendationFindingCode],
) -> dict[str, RecommendationDimension]:
    dimension_by_axis: dict[str, RecommendationDimension] = {}
    for dimension in dimensions:
        if type(dimension) is not RecommendationDimension:
            findings.add(RecommendationFindingCode.RECORD_TYPE_INVALID)
            continue
        valid = (
            _valid_comparison_token(dimension.axis_id, AxisId)
            and _valid_reference(dimension.definition_ref)
            and _valid_version(dimension.definition_version)
            and _valid_sha256(dimension.definition_sha256)
            and type(dimension.critical) is bool
            and type(dimension.hard_constraint) is bool
        )
        if not valid:
            findings.add(RecommendationFindingCode.DIMENSION_INVALID)
            continue
        if _has_forbidden_vocabulary(dimension.definition_ref):
            findings.add(RecommendationFindingCode.PROHIBITED_INPUT)
        if not _valid_decimal_range(
            dimension.weight,
            minimum=Decimal("0"),
            maximum=Decimal("1"),
            minimum_inclusive=False,
        ):
            findings.add(RecommendationFindingCode.WEIGHT_INVALID)
        axis_value = dimension.axis_id.value
        if axis_value in dimension_by_axis:
            findings.add(RecommendationFindingCode.DUPLICATE_DIMENSION)
        else:
            dimension_by_axis[axis_value] = dimension

    expected = {axis.axis_id.value for axis in comparison.axes}
    if set(dimension_by_axis) != expected or len(dimensions) != len(expected):
        findings.add(RecommendationFindingCode.DIMENSION_SET_MISMATCH)
    return dimension_by_axis


def _valid_assessment_states(assessment: DimensionAssessment) -> bool:
    return (
        type(assessment.availability) is EvidenceAvailability
        and type(assessment.hard_constraint_state) is HardConstraintState
        and type(assessment.conflict_state) is ConflictState
        and type(assessment.staleness_state) is StalenessState
    )


def _validate_assessments(
    assessments: tuple[DimensionAssessment, ...],
    comparison: ComparisonInput,
    methodology: MethodologyBinding,
    dimension_by_axis: dict[str, RecommendationDimension],
    findings: set[RecommendationFindingCode],
) -> dict[tuple[str, str], DimensionAssessment]:
    product_values = {product.product_id.value for product in comparison.products}
    cell_by_coordinate: dict[tuple[str, str], ComparisonCell] = {
        (cell.product_id.value, cell.axis_id.value): cell for cell in comparison.cells
    }
    assessment_by_coordinate: dict[tuple[str, str], DimensionAssessment] = {}

    for assessment in assessments:
        if type(assessment) is not DimensionAssessment:
            findings.add(RecommendationFindingCode.RECORD_TYPE_INVALID)
            continue
        product_valid = _valid_comparison_token(assessment.product_id, ProductId)
        axis_valid = _valid_comparison_token(assessment.axis_id, AxisId)
        if not product_valid or not axis_valid:
            findings.add(RecommendationFindingCode.ASSESSMENT_COORDINATE_INVALID)
            continue
        coordinate = (assessment.product_id.value, assessment.axis_id.value)
        dimension = dimension_by_axis.get(coordinate[1])
        cell = cell_by_coordinate.get(coordinate)
        if coordinate[0] not in product_values or dimension is None or cell is None:
            findings.add(RecommendationFindingCode.ASSESSMENT_COORDINATE_INVALID)
            continue
        if coordinate in assessment_by_coordinate:
            findings.add(RecommendationFindingCode.DUPLICATE_ASSESSMENT)
        else:
            assessment_by_coordinate[coordinate] = assessment

        if not _valid_assessment_states(assessment):
            findings.add(RecommendationFindingCode.STATE_INVALID)
            continue
        if (
            not _valid_rule(assessment.conflict_rule)
            or not _valid_rule(assessment.staleness_rule)
            or assessment.conflict_rule != methodology.conflict_penalty_rule
            or assessment.staleness_rule != methodology.staleness_penalty_rule
        ):
            findings.add(RecommendationFindingCode.RULE_BINDING_INVALID)

        if dimension.hard_constraint:
            if assessment.hard_constraint_state is HardConstraintState.NOT_APPLICABLE:
                findings.add(RecommendationFindingCode.STATE_INVALID)
        elif assessment.hard_constraint_state is not HardConstraintState.NOT_APPLICABLE:
            findings.add(RecommendationFindingCode.STATE_INVALID)

        conflict_valid = _valid_decimal_range(
            assessment.conflict_penalty,
            minimum=Decimal("0"),
            maximum=MAXIMUM_UNCERTAINTY_PENALTY,
        )
        staleness_valid = _valid_decimal_range(
            assessment.staleness_penalty,
            minimum=Decimal("0"),
            maximum=MAXIMUM_UNCERTAINTY_PENALTY,
        )
        if cell.state is ComparisonCellState.UNKNOWN:
            if (
                assessment.evidence_id is not None
                or assessment.availability is not EvidenceAvailability.UNKNOWN
                or assessment.normalized_score is not None
                or assessment.conflict_state is not ConflictState.NONE
                or assessment.staleness_state is not StalenessState.CURRENT
                or not conflict_valid
                or not staleness_valid
                or assessment.conflict_penalty != Decimal("0")
                or assessment.staleness_penalty != Decimal("0")
                or (
                    dimension.hard_constraint
                    and assessment.hard_constraint_state
                    is not HardConstraintState.UNKNOWN
                )
            ):
                findings.add(RecommendationFindingCode.STATE_INVALID)
        else:
            expected_evidence = (
                cell.evidence.evidence_id if cell.evidence is not None else None
            )
            if (
                not _valid_comparison_token(assessment.evidence_id, EvidenceId)
                or assessment.evidence_id != expected_evidence
            ):
                findings.add(RecommendationFindingCode.EVIDENCE_BINDING_INVALID)
            if assessment.availability is not EvidenceAvailability.AVAILABLE:
                findings.add(RecommendationFindingCode.STATE_INVALID)
            if not _valid_decimal_range(
                assessment.normalized_score,
                minimum=Decimal("0"),
                maximum=Decimal("1"),
            ):
                findings.add(RecommendationFindingCode.SCORE_INVALID)

        if not conflict_valid or not staleness_valid:
            findings.add(RecommendationFindingCode.PENALTY_INVALID)
        elif (
            (
                assessment.conflict_state is ConflictState.NONE
                and assessment.conflict_penalty != Decimal("0")
            )
            or (
                assessment.conflict_state is ConflictState.CONFLICTING
                and assessment.conflict_penalty <= Decimal("0")
            )
            or (
                assessment.staleness_state is StalenessState.CURRENT
                and assessment.staleness_penalty != Decimal("0")
            )
            or (
                assessment.staleness_state
                in {StalenessState.NEAR_EXPIRY, StalenessState.STALE}
                and assessment.staleness_penalty <= Decimal("0")
            )
        ):
            findings.add(RecommendationFindingCode.PENALTY_INVALID)

    expected_coordinates = {
        (product_value, axis_value)
        for product_value in product_values
        for axis_value in dimension_by_axis
    }
    if set(assessment_by_coordinate) != expected_coordinates or len(assessments) != len(
        expected_coordinates
    ):
        findings.add(RecommendationFindingCode.MISSING_ASSESSMENT)
    return assessment_by_coordinate


def _candidate_reason_codes(
    dimensions: tuple[RecommendationDimension, ...],
    assessments: tuple[DimensionAssessment, ...],
    coverage: Decimal,
) -> tuple[CandidateReasonCode, ...]:
    reasons: set[CandidateReasonCode] = set()
    dimension_by_axis = {dimension.axis_id.value: dimension for dimension in dimensions}
    for assessment in assessments:
        dimension = dimension_by_axis[assessment.axis_id.value]
        if dimension.hard_constraint:
            if assessment.hard_constraint_state is HardConstraintState.FAIL:
                reasons.add(CandidateReasonCode.HARD_CONSTRAINT_FAILED)
            elif assessment.hard_constraint_state is HardConstraintState.UNKNOWN:
                reasons.add(CandidateReasonCode.HARD_CONSTRAINT_UNKNOWN)
        if dimension.critical:
            if assessment.availability is EvidenceAvailability.UNKNOWN:
                reasons.add(CandidateReasonCode.CRITICAL_EVIDENCE_UNKNOWN)
            if assessment.conflict_state is ConflictState.CONFLICTING:
                reasons.add(CandidateReasonCode.CRITICAL_EVIDENCE_CONFLICT)
            if assessment.staleness_state is StalenessState.STALE:
                reasons.add(CandidateReasonCode.CRITICAL_EVIDENCE_STALE)
    if coverage < MINIMUM_RANK_COVERAGE:
        reasons.add(CandidateReasonCode.COVERAGE_BELOW_RANK_THRESHOLD)
    return tuple(code for code in CandidateReasonCode if code in reasons)


def _calculate_candidates(
    comparison: ComparisonInput,
    dimensions: tuple[RecommendationDimension, ...],
    assessments: tuple[DimensionAssessment, ...],
) -> tuple[CandidateRecommendation, ...]:
    dimensions_sorted = tuple(
        sorted(dimensions, key=lambda dimension: dimension.axis_id.value)
    )
    assessments_by_product: dict[str, list[DimensionAssessment]] = {
        product.product_id.value: [] for product in comparison.products
    }
    for assessment in assessments:
        assessments_by_product[assessment.product_id.value].append(assessment)

    total_weight = sum(
        (dimension.weight for dimension in dimensions_sorted),
        start=Decimal("0"),
    )
    computed: list[CandidateRecommendation] = []
    with localcontext() as context:
        context.prec = 64
        for product in sorted(
            comparison.products,
            key=lambda record: record.product_id.value,
        ):
            product_assessments = tuple(
                sorted(
                    assessments_by_product[product.product_id.value],
                    key=lambda assessment: assessment.axis_id.value,
                )
            )
            by_axis = {
                assessment.axis_id.value: assessment
                for assessment in product_assessments
            }
            current_weight = Decimal("0")
            scored_weight = Decimal("0")
            weighted_score = Decimal("0")
            conflict_penalty = Decimal("0")
            staleness_penalty = Decimal("0")
            unknown_axes: list[AxisId] = []
            conflicting_axes: list[AxisId] = []
            stale_axes: list[AxisId] = []

            for dimension in dimensions_sorted:
                assessment = by_axis[dimension.axis_id.value]
                is_current = (
                    assessment.availability is EvidenceAvailability.AVAILABLE
                    and assessment.conflict_state is ConflictState.NONE
                    and assessment.staleness_state is not StalenessState.STALE
                )
                if is_current:
                    current_weight += dimension.weight
                if assessment.normalized_score is not None:
                    scored_weight += dimension.weight
                    weighted_score += dimension.weight * assessment.normalized_score
                conflict_penalty += assessment.conflict_penalty
                staleness_penalty += assessment.staleness_penalty
                if assessment.availability is EvidenceAvailability.UNKNOWN:
                    unknown_axes.append(dimension.axis_id)
                if assessment.conflict_state is ConflictState.CONFLICTING:
                    conflicting_axes.append(dimension.axis_id)
                if assessment.staleness_state is StalenessState.STALE:
                    stale_axes.append(dimension.axis_id)

            coverage_raw = current_weight / total_weight
            coverage = _quantize(coverage_raw)
            reasons = _candidate_reason_codes(
                dimensions_sorted,
                product_assessments,
                coverage,
            )
            hard_blocked = any(
                reason
                in {
                    CandidateReasonCode.HARD_CONSTRAINT_FAILED,
                    CandidateReasonCode.HARD_CONSTRAINT_UNKNOWN,
                }
                for reason in reasons
            )
            critical_blocked = any(
                reason
                in {
                    CandidateReasonCode.CRITICAL_EVIDENCE_UNKNOWN,
                    CandidateReasonCode.CRITICAL_EVIDENCE_CONFLICT,
                    CandidateReasonCode.CRITICAL_EVIDENCE_STALE,
                }
                for reason in reasons
            )
            critical_stale = CandidateReasonCode.CRITICAL_EVIDENCE_STALE in reasons
            eligibility = (
                CandidateEligibility.INELIGIBLE
                if hard_blocked or critical_stale
                else CandidateEligibility.ELIGIBLE
            )
            if hard_blocked or critical_stale:
                ranking_state = RankingState.INELIGIBLE
            elif critical_blocked:
                ranking_state = RankingState.UNRANKED_CRITICAL_EVIDENCE
            elif coverage < MINIMUM_RANK_COVERAGE:
                ranking_state = RankingState.UNRANKED_LOW_COVERAGE
            else:
                ranking_state = RankingState.RANKED

            base_score: Decimal | None = None
            uncertainty_penalty: Decimal | None = None
            final_score: Decimal | None = None
            public_score: int | None = None
            if not hard_blocked and not critical_blocked and scored_weight > 0:
                base_score = _quantize(Decimal("100") * weighted_score / scored_weight)
                uncertainty_raw = (
                    Decimal("20") * (Decimal("1") - coverage)
                    + conflict_penalty
                    + staleness_penalty
                )
                uncertainty_penalty = _quantize(
                    min(MAXIMUM_UNCERTAINTY_PENALTY, uncertainty_raw)
                )
                final_score = _quantize(
                    max(
                        Decimal("0"),
                        min(
                            Decimal("100"),
                            base_score - uncertainty_penalty,
                        ),
                    )
                )
                if ranking_state is RankingState.RANKED:
                    public_score = int(
                        final_score.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)
                    )

            computed.append(
                CandidateRecommendation(
                    product_id=product.product_id,
                    eligibility=eligibility,
                    ranking_state=ranking_state,
                    reason_codes=reasons,
                    weighted_evidence_coverage=coverage,
                    base_score=base_score,
                    conflict_penalty=_quantize(conflict_penalty),
                    staleness_penalty=_quantize(staleness_penalty),
                    uncertainty_penalty=uncertainty_penalty,
                    final_score=final_score,
                    public_score=public_score,
                    rank_group=None,
                    tie_group=None,
                    group_anchor_score=None,
                    co_recommended=False,
                    strict_order_allowed=False,
                    primary_recommendation_allowed=False,
                    unknown_axis_ids=tuple(unknown_axes),
                    conflicting_axis_ids=tuple(conflicting_axes),
                    stale_axis_ids=tuple(stale_axes),
                )
            )

    def ranked_key(
        candidate: CandidateRecommendation,
    ) -> tuple[Decimal, str]:
        assert candidate.final_score is not None
        return (-candidate.final_score, candidate.product_id.value)

    ranked = sorted(
        (
            candidate
            for candidate in computed
            if candidate.ranking_state is RankingState.RANKED
            and candidate.final_score is not None
        ),
        key=ranked_key,
    )
    groups: list[list[CandidateRecommendation]] = []
    for candidate in ranked:
        if not groups:
            groups.append([candidate])
            continue
        anchor = groups[-1][0].final_score
        assert anchor is not None and candidate.final_score is not None
        if anchor - candidate.final_score <= CO_RECOMMEND_MAXIMUM_DIFFERENCE:
            groups[-1].append(candidate)
        else:
            groups.append([candidate])

    ranked_updates: dict[str, CandidateRecommendation] = {}
    for group_number, group in enumerate(groups, start=1):
        anchor = group[0].final_score
        assert anchor is not None
        co_recommended = len(group) > 1
        for candidate in group:
            ranked_updates[candidate.product_id.value] = replace(
                candidate,
                rank_group=group_number,
                tie_group=group_number,
                group_anchor_score=anchor,
                co_recommended=co_recommended,
                strict_order_allowed=not co_recommended,
                primary_recommendation_allowed=(
                    group_number == 1
                    and candidate.weighted_evidence_coverage >= MINIMUM_PRIMARY_COVERAGE
                ),
            )

    return tuple(
        ranked_updates.get(candidate.product_id.value, candidate)
        for candidate in computed
    )


def _explanation_payload(
    value: RecommendationInput,
    comparison_sha256: str,
    candidates: tuple[CandidateRecommendation, ...],
    assessments: tuple[DimensionAssessment, ...],
) -> dict[str, JsonValue]:
    context = value.context
    universe = value.candidate_universe
    dimensions = tuple(
        sorted(value.dimensions, key=lambda dimension: dimension.axis_id.value)
    )
    assessments_sorted = tuple(
        sorted(
            assessments,
            key=lambda assessment: (
                assessment.product_id.value,
                assessment.axis_id.value,
            ),
        )
    )
    ranked_candidates = sorted(
        (
            candidate
            for candidate in candidates
            if candidate.ranking_state is RankingState.RANKED
        ),
        key=lambda candidate: (
            candidate.rank_group if candidate.rank_group is not None else 0,
            candidate.product_id.value,
        ),
    )
    universe_product_ids: list[JsonValue] = [
        product_id.value
        for product_id in sorted(
            universe.product_ids,
            key=lambda product_id: product_id.value,
        )
    ]
    return {
        "assessments": [
            {
                "availability": assessment.availability.value,
                "axis_id": assessment.axis_id.value,
                "conflict_penalty": _decimal_text(assessment.conflict_penalty),
                "conflict_rule": _rule_payload(assessment.conflict_rule),
                "conflict_state": assessment.conflict_state.value,
                "evidence_id": (
                    assessment.evidence_id.value
                    if assessment.evidence_id is not None
                    else None
                ),
                "hard_constraint_state": assessment.hard_constraint_state.value,
                "normalized_score": (
                    _decimal_text(assessment.normalized_score)
                    if assessment.normalized_score is not None
                    else None
                ),
                "product_id": assessment.product_id.value,
                "staleness_penalty": _decimal_text(assessment.staleness_penalty),
                "staleness_rule": _rule_payload(assessment.staleness_rule),
                "staleness_state": assessment.staleness_state.value,
            }
            for assessment in assessments_sorted
        ],
        "candidate_universe": {
            "product_ids": universe_product_ids,
            "scope_ref": universe.scope_ref.value,
            "selection_criteria_ref": universe.selection_criteria_ref.value,
            "universe_id": universe.universe_id.value,
            "universe_sha256": universe.universe_sha256.value,
            "universe_version": universe.universe_version.value,
        },
        "candidates": [
            _candidate_payload(candidate)
            for candidate in sorted(
                candidates,
                key=lambda candidate: candidate.product_id.value,
            )
        ],
        "comparison_sha256": comparison_sha256,
        "context": {
            "article_id": context.article_id.value,
            "article_version_id": context.article_version_id.value,
            "budget_context_ref": context.budget_context_ref.value,
            "decision_context_id": context.decision_context_id.value,
            "decision_context_sha256": context.decision_context_sha256.value,
            "decision_context_version": context.decision_context_version.value,
            "target_reader_ref": context.target_reader_ref.value,
            "use_case_ref": context.use_case_ref.value,
        },
        "dimensions": [
            {
                "axis_id": dimension.axis_id.value,
                "critical": dimension.critical,
                "definition_ref": dimension.definition_ref.value,
                "definition_sha256": dimension.definition_sha256.value,
                "definition_version": dimension.definition_version.value,
                "hard_constraint": dimension.hard_constraint,
                "weight": _decimal_text(dimension.weight),
            }
            for dimension in dimensions
        ],
        "engine_contract": {
            "co_recommend_maximum_difference": "2.0",
            "internal_precision": "0.0001",
            "minimum_primary_coverage": "0.90",
            "minimum_rank_coverage": "0.80",
            "penalty_cap": "20",
            "rounding": "ROUND_HALF_EVEN",
            "score_clamp": ["0", "100"],
            "tie_anchor": "HIGHEST_SCORE_IN_GROUP",
            "tie_member_order": "PRODUCT_ID_ASCENDING",
            "uncertainty_formula": (
                "min(20,20*(1-coverage)+conflict_penalty+staleness_penalty)"
            ),
        },
        "methodology": _methodology_payload(value.methodology),
        "publication_authorized": False,
        "ranking_order": [
            candidate.product_id.value for candidate in ranked_candidates
        ],
        "schema": "RAOS_ST_0804_RECOMMENDATION_EXPLANATION_V1",
        "status": {
            "formal_test": "NOT_EXECUTED",
            "live_validation": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
        },
        "production_eligible": False,
    }


def generate_recommendations(value: object) -> RecommendationReport:
    """Validate and calculate a deterministic local recommendation artifact."""

    findings: set[RecommendationFindingCode] = set()
    if type(value) is not RecommendationInput:
        findings.add(RecommendationFindingCode.INPUT_TYPE_INVALID)
        return _blocked(findings)

    actual_comparison_report = validate_comparison(value.comparison)
    if not actual_comparison_report.passed:
        findings.add(RecommendationFindingCode.COMPARISON_INPUT_INVALID)
        if ComparisonFindingCode.PROHIBITED_FIELD in actual_comparison_report.findings:
            findings.add(RecommendationFindingCode.PROHIBITED_INPUT)
    elif any(
        _has_forbidden_text(axis.field_name.value) for axis in value.comparison.axes
    ):
        findings.add(RecommendationFindingCode.PROHIBITED_INPUT)
    if (
        type(value.comparison_report) is not ComparisonValidationReport
        or value.comparison_report != actual_comparison_report
        or not value.comparison_report.passed
    ):
        findings.add(RecommendationFindingCode.COMPARISON_REPORT_INVALID)
    if findings:
        return _blocked(findings)

    if type(value.dimensions) is not tuple or type(value.assessments) is not tuple:
        findings.add(RecommendationFindingCode.COLLECTION_TYPE_INVALID)
        return _blocked(findings)

    context_valid = _validate_context(value.context, findings)
    methodology_valid = _validate_methodology(value.methodology, findings)
    universe_valid = _validate_universe(
        value.candidate_universe,
        value.comparison,
        findings,
    )
    dimension_by_axis = _validate_dimensions(
        value.dimensions,
        value.comparison,
        findings,
    )
    if not methodology_valid:
        return _blocked(findings)

    assessment_by_coordinate = _validate_assessments(
        value.assessments,
        value.comparison,
        value.methodology,
        dimension_by_axis,
        findings,
    )
    if findings or not context_valid or not universe_valid:
        return _blocked(findings)

    canonical_assessments = tuple(
        assessment_by_coordinate[coordinate]
        for coordinate in sorted(assessment_by_coordinate)
    )
    candidates = _calculate_candidates(
        value.comparison,
        value.dimensions,
        canonical_assessments,
    )
    comparison_json, comparison_sha256 = _hash_json(
        _comparison_payload(value.comparison)
    )
    del comparison_json
    explanation_payload = _explanation_payload(
        value,
        comparison_sha256,
        candidates,
        canonical_assessments,
    )
    explanation_json, explanation_sha256 = _hash_json(explanation_payload)
    ranked_candidates = sorted(
        (
            candidate
            for candidate in candidates
            if candidate.ranking_state is RankingState.RANKED
        ),
        key=lambda candidate: (
            candidate.rank_group if candidate.rank_group is not None else 0,
            candidate.product_id.value,
        ),
    )
    return RecommendationReport(
        decision=RecommendationDecision.PASS,
        findings=(),
        candidates=candidates,
        ranking_order=tuple(candidate.product_id for candidate in ranked_candidates),
        comparison_sha256=comparison_sha256,
        explanation_json=explanation_json,
        explanation_sha256=explanation_sha256,
        publication_authorized=False,
        production_eligible=False,
        formal_test_status=ExecutionStatus.NOT_EXECUTED,
        live_validation_status=ExecutionStatus.NOT_EXECUTED,
        staging_status=ExecutionStatus.NOT_EXECUTED,
        release_status=ExecutionStatus.NOT_EXECUTED,
        production_status=ExecutionStatus.NOT_EXECUTED,
    )

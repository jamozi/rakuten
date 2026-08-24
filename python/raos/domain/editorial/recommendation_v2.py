"""Deterministic ST-0804 recommendation runtime V2.

The evaluator consumes one exact ST-0803 V2 envelope and its independently
recomputed report.  It calculates a local explanation artifact from bounded,
pre-resolved Decimal normalization values.  Those values may describe only a
validated specification, a use condition, or their intersection and are bound
to the exact comparison input, decision context, methodology and coordinate.

This module has no persistence, provider, approval, override, publication or
Production authority.  Generic serialization is intentionally disabled and
validation failures expose closed codes only.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from enum import Enum
import hashlib
import json
import re
from typing import NoReturn, SupportsIndex, cast
import unicodedata
from uuid import UUID

from raos.domain.catalog.ids import CanonicalProductId
from raos.domain.editorial.comparison_validation_v2 import (
    ComparisonAxisDefinition,
    ComparisonCell,
    ComparisonCellStatus,
    ComparisonSnapshotV2,
    ComparisonRecordReceipt,
    ComparisonValidationEnvelopeV2,
    ComparisonValidationReportV2,
    ComparisonValidationStatus,
    canonical_decimal,
    validate_comparison_v2,
)
from raos.domain.editorial.ids import ArticleId, ArticleVersionId, ComparisonAxisId
from raos.domain.evidence.ids import FactId
from raos.domain.shared.identity import EntityId, require_uuid
from raos.domain.shared.persistence import Sha256Digest


CONTRACT_ID = "RAOS-ST0804-RECOMMENDATION-RUNTIME-002"
CONTRACT_VERSION = "2.0.0"
EVALUATOR_VERSION = "ST0804_RECOMMENDATION_ENGINE_V2"
METHODOLOGY_ID = "RAOS-CONTENT-RECO-001"
METHODOLOGY_VERSION = "1.0.0"
METHODOLOGY_SOURCE_SHA256 = (
    "fb71ad7900c7f688f305e10256b49563281893408e54d8668aac02efa7e57862"
)
ST0803_CONTRACT_SHA256 = (
    "ca198b81bf9a3886712efd660fa4b9700c4f24a67cd8a92f580e38ff135f591f"
)
ST0803_DOMAIN_SHA256 = (
    "010f445797704e72a5c5cdaf2355e36ed9bf70f536dc1574fe23fb802e91d552"
)
ST0803_RECORDED_FIXTURE_SHA256 = (
    "21594b37e56f32f7b82ac51ab5a428c97b6875d4dea7660541b513515a31a25b"
)
ST0803_RUNTIME_MANIFEST_SHA256 = (
    "2e4f5d02d12255f0e7b41b778cdb94dbc9b0c8093c27452a5a1ad10809781f7e"
)

INTERNAL_SCORE_QUANTUM = Decimal("0.0001")
MINIMUM_RANK_COVERAGE = Decimal("0.80")
MINIMUM_PRIMARY_COVERAGE = Decimal("0.90")
MAXIMUM_UNCERTAINTY_PENALTY = Decimal("20")
CO_RECOMMEND_MAXIMUM_DIFFERENCE = Decimal("2.0")

_MAX_EXACT_INT = (1 << 53) - 1
_MAX_PRODUCTS = 20
_MAX_AXES = 30
_MAX_ASSESSMENTS = _MAX_PRODUCTS * _MAX_AXES
_MAX_EXPLANATION_BYTES = 1_048_576
_CODE = re.compile(r"[A-Z][A-Z0-9_.:-]{0,79}\Z", re.ASCII)
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)

_PROHIBITED_TOKENS = frozenset(
    {
        "AFF",
        "AFFIL",
        "AFFILIATE",
        "COMMISSION",
        "EARNINGS",
        "EPC",
        "FINANCE",
        "MARGIN",
        "MONETIZATION",
        "PAYOUT",
        "PROFIT",
        "RATE",
        "REVENUE",
        "REWARD",
        "RPM",
        "SPONSOR",
        "SPONSORSHIP",
    }
)
_PROHIBITED_COLLAPSED = frozenset(
    {
        "affiliate",
        "affiliaterate",
        "affiliatefee",
        "commission",
        "commissionrate",
        "confirmedcommission",
        "contributionprofit",
        "earnings",
        "epc",
        "finance",
        "financeinput",
        "financescore",
        "margin",
        "monetization",
        "payout",
        "profit",
        "revenue",
        "reward",
        "rewardrate",
        "rpm",
        "sponsor",
        "sponsorbenefit",
    }
)
_PROHIBITED_UNICODE_FRAGMENTS = (
    "アフィリエイト",
    "コミッション",
    "スポンサー便益",
    "成果報酬",
    "報酬率",
    "収益",
    "料率",
    "利益",
)
_LEET_TRANSLATION = str.maketrans(
    {
        "0": "o",
        "1": "i",
        "3": "e",
        "4": "a",
        "5": "s",
        "7": "t",
    }
)


class RecommendationRuntimeValueError(ValueError):
    """Closed construction or validation error without caller material."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("INVALID_RECOMMENDATION_RUNTIME_VALUE")


def _invalid() -> NoReturn:
    raise RecommendationRuntimeValueError() from None


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-st0804-v2>)"

    def __str__(self) -> str:
        return "<redacted-st0804-v2>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("ST-0804 V2 generic serialization is not supported")


class RecommendationEvaluationStatus(str, Enum):
    LOCAL_CALCULATED = "LOCAL_CALCULATED"
    BLOCK = "BLOCK"
    UNEVALUABLE = "UNEVALUABLE"


class ExecutionStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


class NormalizationBasis(str, Enum):
    VALIDATED_SPECIFICATION = "VALIDATED_SPECIFICATION"
    USE_CONDITION = "USE_CONDITION"
    VALIDATED_SPECIFICATION_AND_USE_CONDITION = (
        "VALIDATED_SPECIFICATION_AND_USE_CONDITION"
    )
    UNAVAILABLE = "UNAVAILABLE"


class ConflictState(str, Enum):
    NONE = "NONE"
    CONFLICTING = "CONFLICTING"
    UNAVAILABLE = "UNAVAILABLE"


class StalenessState(str, Enum):
    CURRENT = "CURRENT"
    NEAR_EXPIRY = "NEAR_EXPIRY"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


class HardConstraintState(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PASS = "PASS"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"


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
    HARD_CONSTRAINT_UNAVAILABLE = "HARD_CONSTRAINT_UNAVAILABLE"
    CRITICAL_EVIDENCE_UNKNOWN = "CRITICAL_EVIDENCE_UNKNOWN"
    CRITICAL_EVIDENCE_MISSING = "CRITICAL_EVIDENCE_MISSING"
    CRITICAL_EVIDENCE_CONFLICT = "CRITICAL_EVIDENCE_CONFLICT"
    CRITICAL_EVIDENCE_UNSUPPORTED = "CRITICAL_EVIDENCE_UNSUPPORTED"
    CRITICAL_EVIDENCE_STALE = "CRITICAL_EVIDENCE_STALE"
    COVERAGE_BELOW_RANK_THRESHOLD = "COVERAGE_BELOW_RANK_THRESHOLD"


class RecommendationFindingCode(str, Enum):
    INPUT_TYPE_INVALID = "INPUT_TYPE_INVALID"
    INPUT_UNAVAILABLE = "INPUT_UNAVAILABLE"
    CONTRACT_BINDING_INVALID = "CONTRACT_BINDING_INVALID"
    COMPARISON_UNEVALUABLE = "COMPARISON_UNEVALUABLE"
    COMPARISON_BLOCKED = "COMPARISON_BLOCKED"
    COMPARISON_REPORT_INVALID = "COMPARISON_REPORT_INVALID"
    COMPARISON_REPORT_MISMATCH = "COMPARISON_REPORT_MISMATCH"
    COMPARISON_RECEIPT_INVALID = "COMPARISON_RECEIPT_INVALID"
    COMPARISON_RECEIPT_MISMATCH = "COMPARISON_RECEIPT_MISMATCH"
    COLLECTION_TYPE_INVALID = "COLLECTION_TYPE_INVALID"
    COLLECTION_BOUND_INVALID = "COLLECTION_BOUND_INVALID"
    RECORD_TYPE_INVALID = "RECORD_TYPE_INVALID"
    CONTEXT_INVALID = "CONTEXT_INVALID"
    CONTEXT_BINDING_MISMATCH = "CONTEXT_BINDING_MISMATCH"
    METHODOLOGY_INVALID = "METHODOLOGY_INVALID"
    RULE_BINDING_INVALID = "RULE_BINDING_INVALID"
    PROHIBITED_RANKING_INPUT = "PROHIBITED_RANKING_INPUT"
    DIMENSION_INVALID = "DIMENSION_INVALID"
    DUPLICATE_DIMENSION = "DUPLICATE_DIMENSION"
    DIMENSION_SET_MISMATCH = "DIMENSION_SET_MISMATCH"
    DIMENSION_SET_HASH_MISMATCH = "DIMENSION_SET_HASH_MISMATCH"
    WEIGHT_INVALID = "WEIGHT_INVALID"
    ASSESSMENT_INVALID = "ASSESSMENT_INVALID"
    DUPLICATE_ASSESSMENT = "DUPLICATE_ASSESSMENT"
    ASSESSMENT_SET_MISMATCH = "ASSESSMENT_SET_MISMATCH"
    ASSESSMENT_SET_HASH_MISMATCH = "ASSESSMENT_SET_HASH_MISMATCH"
    CELL_BINDING_MISMATCH = "CELL_BINDING_MISMATCH"
    NORMALIZATION_BINDING_MISMATCH = "NORMALIZATION_BINDING_MISMATCH"
    SCORE_INVALID = "SCORE_INVALID"
    STATE_INVALID = "STATE_INVALID"
    PENALTY_INVALID = "PENALTY_INVALID"
    RECOMMENDATION_INPUT_HASH_MISMATCH = "RECOMMENDATION_INPUT_HASH_MISMATCH"


_STRUCTURAL_FINDINGS = frozenset(
    {
        RecommendationFindingCode.INPUT_TYPE_INVALID,
        RecommendationFindingCode.INPUT_UNAVAILABLE,
        RecommendationFindingCode.CONTRACT_BINDING_INVALID,
        RecommendationFindingCode.COMPARISON_UNEVALUABLE,
        RecommendationFindingCode.COMPARISON_REPORT_INVALID,
        RecommendationFindingCode.COMPARISON_REPORT_MISMATCH,
        RecommendationFindingCode.COMPARISON_RECEIPT_INVALID,
        RecommendationFindingCode.COMPARISON_RECEIPT_MISMATCH,
        RecommendationFindingCode.COLLECTION_TYPE_INVALID,
        RecommendationFindingCode.COLLECTION_BOUND_INVALID,
        RecommendationFindingCode.RECORD_TYPE_INVALID,
        RecommendationFindingCode.CONTEXT_INVALID,
        RecommendationFindingCode.CONTEXT_BINDING_MISMATCH,
        RecommendationFindingCode.METHODOLOGY_INVALID,
        RecommendationFindingCode.RULE_BINDING_INVALID,
        RecommendationFindingCode.DIMENSION_INVALID,
        RecommendationFindingCode.DUPLICATE_DIMENSION,
        RecommendationFindingCode.DIMENSION_SET_MISMATCH,
        RecommendationFindingCode.DIMENSION_SET_HASH_MISMATCH,
        RecommendationFindingCode.WEIGHT_INVALID,
        RecommendationFindingCode.ASSESSMENT_INVALID,
        RecommendationFindingCode.DUPLICATE_ASSESSMENT,
        RecommendationFindingCode.ASSESSMENT_SET_MISMATCH,
        RecommendationFindingCode.ASSESSMENT_SET_HASH_MISMATCH,
        RecommendationFindingCode.CELL_BINDING_MISMATCH,
        RecommendationFindingCode.NORMALIZATION_BINDING_MISMATCH,
        RecommendationFindingCode.SCORE_INVALID,
        RecommendationFindingCode.STATE_INVALID,
        RecommendationFindingCode.PENALTY_INVALID,
        RecommendationFindingCode.RECOMMENDATION_INPUT_HASH_MISMATCH,
    }
)


class DecisionContextId(EntityId):
    __slots__ = ()


def _valid_entity(value: object, expected: type[EntityId]) -> bool:
    if type(value) is not expected:
        return False
    try:
        require_uuid(value.value)
    except Exception:
        return False
    return True


def _valid_digest(value: object) -> bool:
    return (
        type(value) is Sha256Digest
        and type(value.value) is str
        and _SHA256.fullmatch(value.value) is not None
    )


def _required_digest(value: Sha256Digest | None) -> Sha256Digest:
    if not _valid_digest(value):
        _invalid()
    return cast(Sha256Digest, value)


def _safe_code(value: object, *, maximum: int = 80) -> bool:
    return (
        type(value) is str
        and len(value) <= maximum
        and _CODE.fullmatch(value) is not None
    )


def prohibited_ranking_alias(value: object) -> bool:
    """Detect closed finance/affiliate aliases across case and NFKC forms."""

    if type(value) is not str or not value or len(value) > 4_096:
        return False
    normalized = unicodedata.normalize("NFKC", value)
    if any(
        fragment in normalized.casefold() for fragment in _PROHIBITED_UNICODE_FRAGMENTS
    ):
        return True
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", normalized)
    normalized = normalized.casefold().translate(_LEET_TRANSLATION)
    tokens = tuple(
        token.upper()
        for token in re.split(r"[^a-z0-9]+", normalized, flags=re.ASCII)
        if token
    )
    if any(token in _PROHIBITED_TOKENS for token in tokens):
        return True
    collapsed = "".join(tokens).casefold()
    return any(fragment in collapsed for fragment in _PROHIBITED_COLLAPSED)


def _valid_decimal(
    value: object,
    *,
    minimum: Decimal,
    maximum: Decimal,
    minimum_inclusive: bool = True,
) -> bool:
    if type(value) is not Decimal or not value.is_finite():
        return False
    try:
        rendered = canonical_decimal(value)
        if len(rendered) > 64:
            return False
    except Exception:
        return False
    lower = value >= minimum if minimum_inclusive else value > minimum
    return lower and value <= maximum


def _decimal_text(value: Decimal, *, fixed: bool = False) -> str:
    if type(value) is not Decimal or not value.is_finite():
        _invalid()
    if fixed:
        return format(_quantize(value), ".4f")
    return canonical_decimal(value)


def _quantize(value: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 64
        return value.quantize(INTERNAL_SCORE_QUANTUM, rounding=ROUND_HALF_EVEN)


def _canonical_bytes(material: object) -> bytes:
    try:
        return json.dumps(
            material,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except Exception:
        _invalid()


def _digest(material: object) -> Sha256Digest:
    return Sha256Digest(hashlib.sha256(_canonical_bytes(material)).hexdigest())


@dataclass(frozen=True, slots=True, repr=False)
class RecommendationRuleBinding(_Redacted):
    rule_id: str
    version: str
    source_sha256: Sha256Digest


@dataclass(frozen=True, slots=True, repr=False)
class RecommendationContractBinding(_Redacted):
    contract_id: str
    contract_version: str
    evaluator_version: str
    methodology_source_sha256: Sha256Digest
    st0803_contract_sha256: Sha256Digest
    st0803_domain_sha256: Sha256Digest
    st0803_recorded_fixture_sha256: Sha256Digest
    st0803_runtime_manifest_sha256: Sha256Digest

    @classmethod
    def current(cls) -> RecommendationContractBinding:
        return cls(
            contract_id=CONTRACT_ID,
            contract_version=CONTRACT_VERSION,
            evaluator_version=EVALUATOR_VERSION,
            methodology_source_sha256=Sha256Digest(METHODOLOGY_SOURCE_SHA256),
            st0803_contract_sha256=Sha256Digest(ST0803_CONTRACT_SHA256),
            st0803_domain_sha256=Sha256Digest(ST0803_DOMAIN_SHA256),
            st0803_recorded_fixture_sha256=Sha256Digest(ST0803_RECORDED_FIXTURE_SHA256),
            st0803_runtime_manifest_sha256=Sha256Digest(ST0803_RUNTIME_MANIFEST_SHA256),
        )


@dataclass(frozen=True, slots=True, repr=False)
class MethodologyBindingV2(_Redacted):
    methodology_id: str
    methodology_version: str
    source_sha256: Sha256Digest
    hard_constraint_rule: RecommendationRuleBinding
    weighting_rule: RecommendationRuleBinding
    normalization_rule: RecommendationRuleBinding
    coverage_rule: RecommendationRuleBinding
    conflict_penalty_rule: RecommendationRuleBinding
    staleness_penalty_rule: RecommendationRuleBinding
    tie_rule: RecommendationRuleBinding

    @classmethod
    def current(cls) -> MethodologyBindingV2:
        digest = Sha256Digest(METHODOLOGY_SOURCE_SHA256)

        def rule(name: str) -> RecommendationRuleBinding:
            return RecommendationRuleBinding(name, METHODOLOGY_VERSION, digest)

        return cls(
            methodology_id=METHODOLOGY_ID,
            methodology_version=METHODOLOGY_VERSION,
            source_sha256=digest,
            hard_constraint_rule=rule("HARD_CONSTRAINT"),
            weighting_rule=rule("WEIGHTING"),
            normalization_rule=rule("NORMALIZATION"),
            coverage_rule=rule("COVERAGE"),
            conflict_penalty_rule=rule("CONFLICT_PENALTY"),
            staleness_penalty_rule=rule("STALENESS_PENALTY"),
            tie_rule=rule("TIE"),
        )


@dataclass(frozen=True, slots=True, repr=False)
class ArticleRecommendationContextV2(_Redacted):
    article_id: ArticleId
    article_version_id: ArticleVersionId
    article_binding_sha256: Sha256Digest
    decision_context_id: DecisionContextId
    decision_context_version_no: int
    target_reader_code: str
    use_case_code: str
    budget_context_code: str
    context_source_sha256: Sha256Digest
    binding_sha256: Sha256Digest


@dataclass(frozen=True, slots=True, repr=False)
class RecommendationDimensionV2(_Redacted):
    axis_id: ComparisonAxisId
    axis_definition_sha256: Sha256Digest
    weight: Decimal
    critical: bool
    hard_constraint: bool
    normalization_basis: NormalizationBasis
    normalization_rule: RecommendationRuleBinding


@dataclass(frozen=True, slots=True, repr=False)
class DimensionAssessmentV2(_Redacted):
    product_id: CanonicalProductId
    axis_id: ComparisonAxisId
    cell_status: ComparisonCellStatus
    fact_ids: tuple[FactId, ...]
    normalization_basis: NormalizationBasis
    normalized_score: Decimal | None
    hard_constraint_state: HardConstraintState
    conflict_state: ConflictState
    conflict_penalty: Decimal
    staleness_state: StalenessState
    staleness_penalty: Decimal
    normalization_input_sha256: Sha256Digest
    normalization_decision_sha256: Sha256Digest


@dataclass(frozen=True, slots=True, repr=False)
class RecommendationEnvelopeV2(_Redacted):
    contract: RecommendationContractBinding
    comparison: ComparisonValidationEnvelopeV2
    comparison_report: ComparisonValidationReportV2
    comparison_receipt: ComparisonRecordReceipt
    context: ArticleRecommendationContextV2
    methodology: MethodologyBindingV2
    dimensions: tuple[RecommendationDimensionV2, ...]
    assessments: tuple[DimensionAssessmentV2, ...]
    dimension_set_sha256: Sha256Digest
    assessment_set_sha256: Sha256Digest
    recommendation_input_sha256: Sha256Digest


@dataclass(frozen=True, slots=True, repr=False)
class CandidateRecommendationV2(_Redacted):
    product_id: CanonicalProductId
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
    unknown_axis_ids: tuple[ComparisonAxisId, ...]
    missing_axis_ids: tuple[ComparisonAxisId, ...]
    conflicting_axis_ids: tuple[ComparisonAxisId, ...]
    unsupported_axis_ids: tuple[ComparisonAxisId, ...]
    near_expiry_axis_ids: tuple[ComparisonAxisId, ...]
    stale_axis_ids: tuple[ComparisonAxisId, ...]


@dataclass(frozen=True, slots=True, repr=False)
class RecommendationRecordReceipt(_Redacted):
    sequence: int
    report_sha256: Sha256Digest
    publication_authorized: bool = False
    ranking_authorized: bool = False

    def require_valid(self) -> None:
        if (
            type(self.sequence) is not int
            or not 1 <= self.sequence <= _MAX_EXACT_INT
            or not _valid_digest(self.report_sha256)
            or self.publication_authorized is not False
            or self.ranking_authorized is not False
        ):
            _invalid()


@dataclass(frozen=True, slots=True, repr=False)
class RecommendationReportV2(_Redacted):
    article_id: ArticleId | None
    article_version_id: ArticleVersionId | None
    article_binding_sha256: Sha256Digest | None
    comparison_report_sha256: Sha256Digest | None
    comparison_receipt_sha256: Sha256Digest | None
    comparison_evaluation_input_sha256: Sha256Digest | None
    candidate_universe_sha256: Sha256Digest | None
    axis_catalog_sha256: Sha256Digest | None
    fact_set_sha256: Sha256Digest | None
    temporal_scope_sha256: Sha256Digest | None
    complete_claim_set_sha256: Sha256Digest | None
    decision_context_sha256: Sha256Digest | None
    methodology_sha256: Sha256Digest | None
    dimension_set_sha256: Sha256Digest | None
    assessment_set_sha256: Sha256Digest | None
    recommendation_input_sha256: Sha256Digest | None
    status: RecommendationEvaluationStatus
    findings: tuple[RecommendationFindingCode, ...]
    candidates: tuple[CandidateRecommendationV2, ...]
    ranking_order: tuple[CanonicalProductId, ...]
    explanation_json: str | None
    explanation_sha256: Sha256Digest | None
    override_supported: bool
    approval_authorized: bool
    recommendation_authorized: bool
    ranking_authorized: bool
    publication_authorized: bool
    activation_authorized: bool
    production_eligible: bool
    formal_tst_007_status: ExecutionStatus
    formal_tst_020_status: ExecutionStatus
    live_validation_status: ExecutionStatus
    staging_status: ExecutionStatus
    release_status: ExecutionStatus
    production_status: ExecutionStatus
    report_sha256: Sha256Digest

    @property
    def locally_calculated(self) -> bool:
        return self.status is RecommendationEvaluationStatus.LOCAL_CALCULATED

    def canonical_bytes(self) -> bytes:
        return _report_bytes(self, include_digest=True)

    def require_valid(self) -> None:
        for value, expected in (
            (self.article_id, ArticleId),
            (self.article_version_id, ArticleVersionId),
        ):
            if value is not None and not _valid_entity(value, expected):
                _invalid()
        for digest in (
            self.article_binding_sha256,
            self.comparison_report_sha256,
            self.comparison_receipt_sha256,
            self.comparison_evaluation_input_sha256,
            self.candidate_universe_sha256,
            self.axis_catalog_sha256,
            self.fact_set_sha256,
            self.temporal_scope_sha256,
            self.complete_claim_set_sha256,
            self.decision_context_sha256,
            self.methodology_sha256,
            self.dimension_set_sha256,
            self.assessment_set_sha256,
            self.recommendation_input_sha256,
            self.explanation_sha256,
        ):
            if digest is not None and not _valid_digest(digest):
                _invalid()
        if (
            type(self.status) is not RecommendationEvaluationStatus
            or type(self.findings) is not tuple
            or any(
                type(item) is not RecommendationFindingCode for item in self.findings
            )
            or self.findings
            != tuple(
                code for code in RecommendationFindingCode if code in self.findings
            )
            or len(set(self.findings)) != len(self.findings)
            or type(self.candidates) is not tuple
            or len(self.candidates) > _MAX_PRODUCTS
            or any(not _candidate_shape(item) for item in self.candidates)
            or tuple(item.product_id.value.int for item in self.candidates)
            != tuple(sorted(item.product_id.value.int for item in self.candidates))
            or type(self.ranking_order) is not tuple
            or len(self.ranking_order) > _MAX_PRODUCTS
            or any(
                not _valid_entity(item, CanonicalProductId)
                for item in self.ranking_order
            )
            or len(set(self.ranking_order)) != len(self.ranking_order)
            or self.override_supported is not False
            or any(
                value is not False
                for value in (
                    self.approval_authorized,
                    self.recommendation_authorized,
                    self.ranking_authorized,
                    self.publication_authorized,
                    self.activation_authorized,
                    self.production_eligible,
                )
            )
            or any(
                value is not ExecutionStatus.NOT_EXECUTED
                for value in (
                    self.formal_tst_007_status,
                    self.formal_tst_020_status,
                    self.live_validation_status,
                    self.staging_status,
                    self.release_status,
                    self.production_status,
                )
            )
            or not _valid_digest(self.report_sha256)
        ):
            _invalid()
        expected_status = _status_for_findings(set(self.findings))
        if expected_status is not self.status:
            _invalid()
        if self.status is RecommendationEvaluationStatus.LOCAL_CALCULATED:
            if (
                self.findings
                or self.article_id is None
                or self.article_version_id is None
                or self.article_binding_sha256 is None
                or self.comparison_report_sha256 is None
                or self.comparison_receipt_sha256 is None
                or self.comparison_evaluation_input_sha256 is None
                or self.candidate_universe_sha256 is None
                or self.axis_catalog_sha256 is None
                or self.fact_set_sha256 is None
                or self.temporal_scope_sha256 is None
                or self.complete_claim_set_sha256 is None
                or self.decision_context_sha256 is None
                or self.methodology_sha256 is None
                or self.dimension_set_sha256 is None
                or self.assessment_set_sha256 is None
                or self.recommendation_input_sha256 is None
                or self.explanation_json is None
                or self.explanation_sha256 is None
            ):
                _invalid()
            encoded = self.explanation_json.encode("ascii")
            if (
                not encoded
                or len(encoded) > _MAX_EXPLANATION_BYTES
                or hashlib.sha256(encoded).hexdigest() != self.explanation_sha256.value
            ):
                _invalid()
            try:
                parsed = json.loads(self.explanation_json)
            except Exception:
                _invalid()
            if _canonical_bytes(parsed).decode("ascii") != self.explanation_json:
                _invalid()
            expected_order = tuple(
                item.product_id
                for item in sorted(
                    (
                        candidate
                        for candidate in self.candidates
                        if candidate.ranking_state is RankingState.RANKED
                    ),
                    key=lambda item: (
                        cast(int, item.rank_group),
                        item.product_id.value.int,
                    ),
                )
            )
            if self.ranking_order != expected_order:
                _invalid()
        elif (
            self.candidates
            or self.ranking_order
            or self.explanation_json is not None
            or self.explanation_sha256 is not None
        ):
            _invalid()
        expected_digest = hashlib.sha256(
            _report_bytes(self, include_digest=False)
        ).hexdigest()
        if self.report_sha256.value != expected_digest:
            _invalid()


def _rule_shape(value: object) -> bool:
    return (
        type(value) is RecommendationRuleBinding
        and _safe_code(value.rule_id)
        and type(value.version) is str
        and len(value.version) <= 32
        and _VERSION.fullmatch(value.version) is not None
        and _valid_digest(value.source_sha256)
        and not prohibited_ranking_alias(value.rule_id)
    )


def _rule_material(value: RecommendationRuleBinding) -> dict[str, object]:
    if not _rule_shape(value):
        _invalid()
    return {
        "rule_id": value.rule_id,
        "source_sha256": value.source_sha256.value,
        "version": value.version,
    }


def _methodology_shape(value: object) -> bool:
    return (
        type(value) is MethodologyBindingV2 and value == MethodologyBindingV2.current()
    )


def _methodology_material(value: MethodologyBindingV2) -> dict[str, object]:
    if not _methodology_shape(value):
        _invalid()
    return {
        "conflict_penalty_rule": _rule_material(value.conflict_penalty_rule),
        "coverage_rule": _rule_material(value.coverage_rule),
        "hard_constraint_rule": _rule_material(value.hard_constraint_rule),
        "methodology_id": value.methodology_id,
        "methodology_version": value.methodology_version,
        "normalization_rule": _rule_material(value.normalization_rule),
        "source_sha256": value.source_sha256.value,
        "staleness_penalty_rule": _rule_material(value.staleness_penalty_rule),
        "tie_rule": _rule_material(value.tie_rule),
        "weighting_rule": _rule_material(value.weighting_rule),
    }


def _context_shape(value: object) -> bool:
    return (
        type(value) is ArticleRecommendationContextV2
        and _valid_entity(value.article_id, ArticleId)
        and _valid_entity(value.article_version_id, ArticleVersionId)
        and _valid_digest(value.article_binding_sha256)
        and _valid_entity(value.decision_context_id, DecisionContextId)
        and type(value.decision_context_version_no) is int
        and 1 <= value.decision_context_version_no <= _MAX_EXACT_INT
        and _safe_code(value.target_reader_code)
        and _safe_code(value.use_case_code)
        and _safe_code(value.budget_context_code)
        and _valid_digest(value.context_source_sha256)
        and _valid_digest(value.binding_sha256)
    )


def _context_material(value: ArticleRecommendationContextV2) -> dict[str, object]:
    if not _context_shape(value):
        _invalid()
    return {
        "article_binding_sha256": value.article_binding_sha256.value,
        "article_id": str(value.article_id.value),
        "article_version_id": str(value.article_version_id.value),
        "budget_context_code": value.budget_context_code,
        "context_source_sha256": value.context_source_sha256.value,
        "decision_context_id": str(value.decision_context_id.value),
        "decision_context_version_no": value.decision_context_version_no,
        "target_reader_code": value.target_reader_code,
        "use_case_code": value.use_case_code,
    }


def decision_context_sha256(value: ArticleRecommendationContextV2) -> Sha256Digest:
    return _digest(
        {
            "context": _context_material(value),
            "profile": "ST0804_DECISION_CONTEXT_V2",
        }
    )


def _axis_shape(value: object) -> bool:
    try:
        return (
            type(value) is ComparisonAxisDefinition
            and _valid_entity(value.axis_id, ComparisonAxisId)
            and _safe_code(value.axis_code, maximum=64)
            and type(value.label) is str
            and 1 <= len(value.label) <= 120
            and type(value.description) is str
            and 1 <= len(value.description) <= 500
            and type(value.position) is int
            and 0 <= value.position < _MAX_AXES
            and type(value.required) is bool
        )
    except Exception:
        return False


def axis_definition_sha256(value: ComparisonAxisDefinition) -> Sha256Digest:
    if not _axis_shape(value):
        _invalid()
    return _digest(
        {
            "axis": {
                "axis_code": value.axis_code,
                "axis_id": str(value.axis_id.value),
                "data_type": value.data_type.value,
                "description": value.description,
                "label": value.label,
                "position": value.position,
                "required": value.required,
                "unit_code": value.unit_code,
                "unit_family_code": value.unit_family_code,
            },
            "profile": "ST0804_AXIS_DEFINITION_V2",
        }
    )


def _dimension_shape(value: object) -> bool:
    return (
        type(value) is RecommendationDimensionV2
        and _valid_entity(value.axis_id, ComparisonAxisId)
        and _valid_digest(value.axis_definition_sha256)
        and _valid_decimal(
            value.weight,
            minimum=Decimal("0"),
            maximum=Decimal("1"),
            minimum_inclusive=False,
        )
        and type(value.critical) is bool
        and type(value.hard_constraint) is bool
        and type(value.normalization_basis) is NormalizationBasis
        and value.normalization_basis is not NormalizationBasis.UNAVAILABLE
        and _rule_shape(value.normalization_rule)
        and value.normalization_rule
        == MethodologyBindingV2.current().normalization_rule
    )


def _dimension_material(value: RecommendationDimensionV2) -> dict[str, object]:
    if not _dimension_shape(value):
        _invalid()
    return {
        "axis_definition_sha256": value.axis_definition_sha256.value,
        "axis_id": str(value.axis_id.value),
        "critical": value.critical,
        "hard_constraint": value.hard_constraint,
        "normalization_basis": value.normalization_basis.value,
        "normalization_rule": _rule_material(value.normalization_rule),
        "weight": _decimal_text(value.weight),
    }


def dimension_set_sha256(
    value: tuple[RecommendationDimensionV2, ...],
) -> Sha256Digest:
    if (
        type(value) is not tuple
        or not 1 <= len(value) <= _MAX_AXES
        or any(not _dimension_shape(item) for item in value)
    ):
        _invalid()
    ordered = tuple(sorted(value, key=lambda item: item.axis_id.value.int))
    return _digest(
        {
            "dimensions": [_dimension_material(item) for item in ordered],
            "profile": "ST0804_DIMENSION_SET_V2",
        }
    )


def _cell_shape(value: object) -> bool:
    return (
        type(value) is ComparisonCell
        and _valid_entity(value.product_id, CanonicalProductId)
        and _valid_entity(value.axis_id, ComparisonAxisId)
        and type(value.status) is ComparisonCellStatus
        and type(value.fact_ids) is tuple
        and len(value.fact_ids) <= 2
        and all(_valid_entity(item, FactId) for item in value.fact_ids)
        and len(set(value.fact_ids)) == len(value.fact_ids)
    )


def normalization_input_sha256(
    *,
    comparison: ComparisonSnapshotV2,
    context: ArticleRecommendationContextV2,
    methodology: MethodologyBindingV2,
    dimension: RecommendationDimensionV2,
    cell: ComparisonCell,
    basis: NormalizationBasis,
) -> Sha256Digest:
    if (
        type(comparison) is not ComparisonSnapshotV2
        or not _context_shape(context)
        or not _methodology_shape(methodology)
        or not _dimension_shape(dimension)
        or not _cell_shape(cell)
        or type(basis) is not NormalizationBasis
        or basis is NormalizationBasis.UNAVAILABLE
        or dimension.axis_id != cell.axis_id
    ):
        _invalid()
    return _digest(
        {
            "axis_id": str(cell.axis_id.value),
            "basis": basis.value,
            "cell_status": cell.status.value,
            "comparison_evaluation_input_sha256": (
                comparison.evaluation_input_sha256.value
            ),
            "context_sha256": context.binding_sha256.value,
            "dimension": _dimension_material(dimension),
            "fact_ids": [str(item.value) for item in cell.fact_ids],
            "methodology_sha256": methodology.source_sha256.value,
            "product_id": str(cell.product_id.value),
            "profile": "ST0804_NORMALIZATION_INPUT_V2",
        }
    )


def normalization_decision_sha256(
    *,
    input_sha256: Sha256Digest,
    basis: NormalizationBasis,
    normalized_score: Decimal | None,
) -> Sha256Digest:
    if (
        not _valid_digest(input_sha256)
        or type(basis) is not NormalizationBasis
        or basis is NormalizationBasis.UNAVAILABLE
        or not _valid_decimal(
            normalized_score,
            minimum=Decimal("0"),
            maximum=Decimal("1"),
        )
    ):
        _invalid()
    return _digest(
        {
            "basis": basis.value,
            "input_sha256": input_sha256.value,
            "normalized_score": _decimal_text(cast(Decimal, normalized_score)),
            "profile": "ST0804_NORMALIZATION_DECISION_V2",
        }
    )


def unavailable_normalization_input_sha256(
    *,
    comparison: ComparisonSnapshotV2,
    context: ArticleRecommendationContextV2,
    dimension: RecommendationDimensionV2,
    cell: ComparisonCell,
) -> Sha256Digest:
    if (
        type(comparison) is not ComparisonSnapshotV2
        or not _context_shape(context)
        or not _dimension_shape(dimension)
        or not _cell_shape(cell)
        or dimension.axis_id != cell.axis_id
    ):
        _invalid()
    return _digest(
        {
            "axis_id": str(cell.axis_id.value),
            "basis": NormalizationBasis.UNAVAILABLE.value,
            "cell_status": cell.status.value,
            "comparison_evaluation_input_sha256": (
                comparison.evaluation_input_sha256.value
            ),
            "context_sha256": context.binding_sha256.value,
            "dimension": _dimension_material(dimension),
            "fact_ids": [str(item.value) for item in cell.fact_ids],
            "product_id": str(cell.product_id.value),
            "profile": "ST0804_NORMALIZATION_INPUT_V2",
        }
    )


def unavailable_normalization_decision_sha256(
    input_sha256: Sha256Digest,
) -> Sha256Digest:
    if not _valid_digest(input_sha256):
        _invalid()
    return _digest(
        {
            "basis": NormalizationBasis.UNAVAILABLE.value,
            "input_sha256": input_sha256.value,
            "normalized_score": None,
            "profile": "ST0804_NORMALIZATION_DECISION_V2",
        }
    )


def _assessment_shape(value: object) -> bool:
    return (
        type(value) is DimensionAssessmentV2
        and _valid_entity(value.product_id, CanonicalProductId)
        and _valid_entity(value.axis_id, ComparisonAxisId)
        and type(value.cell_status) is ComparisonCellStatus
        and type(value.fact_ids) is tuple
        and len(value.fact_ids) <= 2
        and all(_valid_entity(item, FactId) for item in value.fact_ids)
        and len(set(value.fact_ids)) == len(value.fact_ids)
        and type(value.normalization_basis) is NormalizationBasis
        and (
            value.normalized_score is None
            or _valid_decimal(
                value.normalized_score,
                minimum=Decimal("0"),
                maximum=Decimal("1"),
            )
        )
        and type(value.hard_constraint_state) is HardConstraintState
        and type(value.conflict_state) is ConflictState
        and _valid_decimal(
            value.conflict_penalty,
            minimum=Decimal("0"),
            maximum=MAXIMUM_UNCERTAINTY_PENALTY,
        )
        and type(value.staleness_state) is StalenessState
        and _valid_decimal(
            value.staleness_penalty,
            minimum=Decimal("0"),
            maximum=MAXIMUM_UNCERTAINTY_PENALTY,
        )
        and _valid_digest(value.normalization_input_sha256)
        and _valid_digest(value.normalization_decision_sha256)
    )


def _assessment_material(value: DimensionAssessmentV2) -> dict[str, object]:
    if not _assessment_shape(value):
        _invalid()
    return {
        "axis_id": str(value.axis_id.value),
        "cell_status": value.cell_status.value,
        "conflict_penalty": _decimal_text(value.conflict_penalty),
        "conflict_state": value.conflict_state.value,
        "fact_ids": [str(item.value) for item in value.fact_ids],
        "hard_constraint_state": value.hard_constraint_state.value,
        "normalization_basis": value.normalization_basis.value,
        "normalization_decision_sha256": value.normalization_decision_sha256.value,
        "normalization_input_sha256": value.normalization_input_sha256.value,
        "normalized_score": (
            None
            if value.normalized_score is None
            else _decimal_text(value.normalized_score)
        ),
        "product_id": str(value.product_id.value),
        "staleness_penalty": _decimal_text(value.staleness_penalty),
        "staleness_state": value.staleness_state.value,
    }


def assessment_set_sha256(
    value: tuple[DimensionAssessmentV2, ...],
) -> Sha256Digest:
    if (
        type(value) is not tuple
        or not 1 <= len(value) <= _MAX_ASSESSMENTS
        or any(not _assessment_shape(item) for item in value)
    ):
        _invalid()
    ordered = tuple(
        sorted(
            value, key=lambda item: (item.product_id.value.int, item.axis_id.value.int)
        )
    )
    return _digest(
        {
            "assessments": [_assessment_material(item) for item in ordered],
            "profile": "ST0804_ASSESSMENT_SET_V2",
        }
    )


def recommendation_input_sha256(value: RecommendationEnvelopeV2) -> Sha256Digest:
    if type(value) is not RecommendationEnvelopeV2:
        _invalid()
    try:
        report = value.comparison_report
        report.require_valid()
        receipt_sha256 = comparison_receipt_sha256(value.comparison_receipt)
        if value.comparison_receipt.report_sha256 != report.report_sha256:
            _invalid()
        return _digest(
            {
                "assessment_set_sha256": value.assessment_set_sha256.value,
                "comparison": {
                    "article_binding_sha256": _required_digest(
                        report.article_binding_sha256
                    ).value,
                    "axis_catalog_sha256": _required_digest(
                        report.axis_catalog_sha256
                    ).value,
                    "candidate_universe_sha256": (
                        _required_digest(report.candidate_universe_sha256).value
                    ),
                    "complete_claim_set_sha256": (
                        _required_digest(report.complete_claim_set_sha256).value
                    ),
                    "evaluation_input_sha256": _required_digest(
                        report.evaluation_input_sha256
                    ).value,
                    "fact_set_sha256": _required_digest(report.fact_set_sha256).value,
                    "report_sha256": report.report_sha256.value,
                    "receipt": {
                        "receipt_sha256": receipt_sha256.value,
                        "report_sha256": value.comparison_receipt.report_sha256.value,
                        "sequence": value.comparison_receipt.sequence,
                    },
                    "temporal_scope_sha256": _required_digest(
                        report.temporal_scope_sha256
                    ).value,
                },
                "context_sha256": value.context.binding_sha256.value,
                "contract": {
                    "contract_id": value.contract.contract_id,
                    "contract_version": value.contract.contract_version,
                    "evaluator_version": value.contract.evaluator_version,
                    "methodology_source_sha256": (
                        value.contract.methodology_source_sha256.value
                    ),
                    "st0803_contract_sha256": (
                        value.contract.st0803_contract_sha256.value
                    ),
                    "st0803_domain_sha256": value.contract.st0803_domain_sha256.value,
                    "st0803_recorded_fixture_sha256": (
                        value.contract.st0803_recorded_fixture_sha256.value
                    ),
                    "st0803_runtime_manifest_sha256": (
                        value.contract.st0803_runtime_manifest_sha256.value
                    ),
                },
                "dimension_set_sha256": value.dimension_set_sha256.value,
                "methodology": _methodology_material(value.methodology),
                "profile": "ST0804_RECOMMENDATION_INPUT_V2",
            }
        )
    except Exception:
        _invalid()


def comparison_receipt_sha256(value: ComparisonRecordReceipt) -> Sha256Digest:
    if type(value) is not ComparisonRecordReceipt:
        _invalid()
    try:
        value.require_valid()
    except Exception:
        _invalid()
    return _digest(
        {
            "profile": "ST0804_BOUND_ST0803_RECEIPT_V2",
            "publication_authorized": False,
            "report_sha256": value.report_sha256.value,
            "sequence": value.sequence,
        }
    )


def _candidate_shape(value: object) -> bool:
    if not (
        type(value) is CandidateRecommendationV2
        and _valid_entity(value.product_id, CanonicalProductId)
        and type(value.eligibility) is CandidateEligibility
        and type(value.ranking_state) is RankingState
        and type(value.reason_codes) is tuple
        and all(type(item) is CandidateReasonCode for item in value.reason_codes)
        and value.reason_codes
        == tuple(code for code in CandidateReasonCode if code in value.reason_codes)
        and len(set(value.reason_codes)) == len(value.reason_codes)
        and _valid_decimal(
            value.weighted_evidence_coverage,
            minimum=Decimal("0"),
            maximum=Decimal("1"),
        )
        and (
            value.base_score is None
            or _valid_decimal(
                value.base_score,
                minimum=Decimal("0"),
                maximum=Decimal("100"),
            )
        )
        and _valid_decimal(
            value.conflict_penalty,
            minimum=Decimal("0"),
            maximum=Decimal("600"),
        )
        and _valid_decimal(
            value.staleness_penalty,
            minimum=Decimal("0"),
            maximum=Decimal("600"),
        )
        and (
            value.uncertainty_penalty is None
            or _valid_decimal(
                value.uncertainty_penalty,
                minimum=Decimal("0"),
                maximum=MAXIMUM_UNCERTAINTY_PENALTY,
            )
        )
        and (
            value.final_score is None
            or _valid_decimal(
                value.final_score,
                minimum=Decimal("0"),
                maximum=Decimal("100"),
            )
        )
        and (
            value.public_score is None
            or type(value.public_score) is int
            and 0 <= value.public_score <= 100
        )
        and (
            value.rank_group is None
            or type(value.rank_group) is int
            and 1 <= value.rank_group <= _MAX_PRODUCTS
        )
        and (
            value.tie_group is None
            or type(value.tie_group) is int
            and 1 <= value.tie_group <= _MAX_PRODUCTS
        )
        and (
            value.group_anchor_score is None
            or _valid_decimal(
                value.group_anchor_score,
                minimum=Decimal("0"),
                maximum=Decimal("100"),
            )
        )
        and type(value.co_recommended) is bool
        and type(value.strict_order_allowed) is bool
        and type(value.primary_recommendation_allowed) is bool
    ):
        return False
    for axes in (
        value.unknown_axis_ids,
        value.missing_axis_ids,
        value.conflicting_axis_ids,
        value.unsupported_axis_ids,
        value.near_expiry_axis_ids,
        value.stale_axis_ids,
    ):
        if (
            type(axes) is not tuple
            or len(axes) > _MAX_AXES
            or any(not _valid_entity(item, ComparisonAxisId) for item in axes)
            or tuple(item.value.int for item in axes)
            != tuple(sorted(item.value.int for item in axes))
            or len(set(axes)) != len(axes)
        ):
            return False
    if value.ranking_state is RankingState.RANKED:
        return (
            value.final_score is not None
            and value.public_score is not None
            and value.rank_group is not None
            and value.tie_group == value.rank_group
            and value.group_anchor_score is not None
        )
    return (
        value.rank_group is None
        and value.tie_group is None
        and value.group_anchor_score is None
        and value.public_score is None
        and not value.co_recommended
        and not value.strict_order_allowed
        and not value.primary_recommendation_allowed
    )


def _candidate_material(value: CandidateRecommendationV2) -> dict[str, object]:
    if not _candidate_shape(value):
        _invalid()
    return {
        "base_score": (
            None
            if value.base_score is None
            else _decimal_text(value.base_score, fixed=True)
        ),
        "co_recommended": value.co_recommended,
        "conflict_penalty": _decimal_text(value.conflict_penalty, fixed=True),
        "conflicting_axis_ids": [
            str(item.value) for item in value.conflicting_axis_ids
        ],
        "eligibility": value.eligibility.value,
        "final_score": (
            None
            if value.final_score is None
            else _decimal_text(value.final_score, fixed=True)
        ),
        "group_anchor_score": (
            None
            if value.group_anchor_score is None
            else _decimal_text(value.group_anchor_score, fixed=True)
        ),
        "missing_axis_ids": [str(item.value) for item in value.missing_axis_ids],
        "near_expiry_axis_ids": [
            str(item.value) for item in value.near_expiry_axis_ids
        ],
        "primary_recommendation_allowed": value.primary_recommendation_allowed,
        "product_id": str(value.product_id.value),
        "public_score": value.public_score,
        "rank_group": value.rank_group,
        "ranking_state": value.ranking_state.value,
        "reason_codes": [item.value for item in value.reason_codes],
        "stale_axis_ids": [str(item.value) for item in value.stale_axis_ids],
        "staleness_penalty": _decimal_text(value.staleness_penalty, fixed=True),
        "strict_order_allowed": value.strict_order_allowed,
        "tie_group": value.tie_group,
        "uncertainty_penalty": (
            None
            if value.uncertainty_penalty is None
            else _decimal_text(value.uncertainty_penalty, fixed=True)
        ),
        "unknown_axis_ids": [str(item.value) for item in value.unknown_axis_ids],
        "unsupported_axis_ids": [
            str(item.value) for item in value.unsupported_axis_ids
        ],
        "weighted_evidence_coverage": _decimal_text(
            value.weighted_evidence_coverage, fixed=True
        ),
    }


def _status_for_findings(
    findings: set[RecommendationFindingCode],
) -> RecommendationEvaluationStatus:
    if findings & _STRUCTURAL_FINDINGS:
        return RecommendationEvaluationStatus.UNEVALUABLE
    if findings:
        return RecommendationEvaluationStatus.BLOCK
    return RecommendationEvaluationStatus.LOCAL_CALCULATED


def _candidate_reasons(
    dimensions: tuple[RecommendationDimensionV2, ...],
    assessments: tuple[DimensionAssessmentV2, ...],
    coverage: Decimal,
) -> tuple[CandidateReasonCode, ...]:
    reasons: set[CandidateReasonCode] = set()
    by_axis = {item.axis_id: item for item in dimensions}
    for assessment in assessments:
        dimension = by_axis[assessment.axis_id]
        if dimension.hard_constraint:
            if assessment.hard_constraint_state is HardConstraintState.FAIL:
                reasons.add(CandidateReasonCode.HARD_CONSTRAINT_FAILED)
            elif assessment.hard_constraint_state is HardConstraintState.UNAVAILABLE:
                reasons.add(CandidateReasonCode.HARD_CONSTRAINT_UNAVAILABLE)
        if dimension.critical:
            if assessment.cell_status is ComparisonCellStatus.UNKNOWN:
                reasons.add(CandidateReasonCode.CRITICAL_EVIDENCE_UNKNOWN)
            elif assessment.cell_status is ComparisonCellStatus.MISSING:
                reasons.add(CandidateReasonCode.CRITICAL_EVIDENCE_MISSING)
            elif assessment.cell_status is ComparisonCellStatus.CONFLICT:
                reasons.add(CandidateReasonCode.CRITICAL_EVIDENCE_CONFLICT)
            elif assessment.cell_status is ComparisonCellStatus.UNSUPPORTED:
                reasons.add(CandidateReasonCode.CRITICAL_EVIDENCE_UNSUPPORTED)
            if assessment.conflict_state is ConflictState.CONFLICTING:
                reasons.add(CandidateReasonCode.CRITICAL_EVIDENCE_CONFLICT)
            if assessment.staleness_state is StalenessState.STALE:
                reasons.add(CandidateReasonCode.CRITICAL_EVIDENCE_STALE)
    if coverage < MINIMUM_RANK_COVERAGE:
        reasons.add(CandidateReasonCode.COVERAGE_BELOW_RANK_THRESHOLD)
    return tuple(code for code in CandidateReasonCode if code in reasons)


def _calculate_candidates(
    comparison: ComparisonSnapshotV2,
    dimensions: tuple[RecommendationDimensionV2, ...],
    assessments: tuple[DimensionAssessmentV2, ...],
) -> tuple[CandidateRecommendationV2, ...]:
    ordered_dimensions = tuple(
        sorted(dimensions, key=lambda item: item.axis_id.value.int)
    )
    by_product: dict[UUID, list[DimensionAssessmentV2]] = {
        item.product_id.value: [] for item in comparison.candidate_universe.products
    }
    for assessment in assessments:
        by_product[assessment.product_id.value].append(assessment)
    with localcontext() as context:
        context.prec = 64
        total_weight = sum(
            (item.weight for item in ordered_dimensions), start=Decimal("0")
        )
        computed: list[CandidateRecommendationV2] = []
        for product in sorted(
            comparison.candidate_universe.products,
            key=lambda item: item.product_id.value.int,
        ):
            product_assessments = tuple(
                sorted(
                    by_product[product.product_id.value],
                    key=lambda item: item.axis_id.value.int,
                )
            )
            assessment_by_axis = {item.axis_id: item for item in product_assessments}
            current_weight = Decimal("0")
            scored_weight = Decimal("0")
            weighted_score = Decimal("0")
            conflict_penalty = Decimal("0")
            staleness_penalty = Decimal("0")
            unknown: list[ComparisonAxisId] = []
            missing: list[ComparisonAxisId] = []
            conflicting: list[ComparisonAxisId] = []
            unsupported: list[ComparisonAxisId] = []
            near_expiry: list[ComparisonAxisId] = []
            stale: list[ComparisonAxisId] = []
            for dimension in ordered_dimensions:
                assessment = assessment_by_axis[dimension.axis_id]
                current = (
                    assessment.cell_status is ComparisonCellStatus.VALID
                    and assessment.conflict_state is ConflictState.NONE
                    and assessment.staleness_state
                    in {StalenessState.CURRENT, StalenessState.NEAR_EXPIRY}
                )
                if current:
                    current_weight += dimension.weight
                if assessment.normalized_score is not None:
                    scored_weight += dimension.weight
                    weighted_score += dimension.weight * assessment.normalized_score
                conflict_penalty += assessment.conflict_penalty
                staleness_penalty += assessment.staleness_penalty
                if assessment.cell_status is ComparisonCellStatus.UNKNOWN:
                    unknown.append(dimension.axis_id)
                elif assessment.cell_status is ComparisonCellStatus.MISSING:
                    missing.append(dimension.axis_id)
                elif assessment.cell_status is ComparisonCellStatus.CONFLICT:
                    conflicting.append(dimension.axis_id)
                elif assessment.cell_status is ComparisonCellStatus.UNSUPPORTED:
                    unsupported.append(dimension.axis_id)
                if assessment.conflict_state is ConflictState.CONFLICTING:
                    conflicting.append(dimension.axis_id)
                if assessment.staleness_state is StalenessState.NEAR_EXPIRY:
                    near_expiry.append(dimension.axis_id)
                elif assessment.staleness_state is StalenessState.STALE:
                    stale.append(dimension.axis_id)
            coverage = _quantize(current_weight / total_weight)
            reasons = _candidate_reasons(
                ordered_dimensions, product_assessments, coverage
            )
            hard_blocked = any(
                item
                in {
                    CandidateReasonCode.HARD_CONSTRAINT_FAILED,
                    CandidateReasonCode.HARD_CONSTRAINT_UNAVAILABLE,
                }
                for item in reasons
            )
            critical_unavailable = any(
                item
                in {
                    CandidateReasonCode.CRITICAL_EVIDENCE_UNKNOWN,
                    CandidateReasonCode.CRITICAL_EVIDENCE_MISSING,
                    CandidateReasonCode.CRITICAL_EVIDENCE_CONFLICT,
                    CandidateReasonCode.CRITICAL_EVIDENCE_UNSUPPORTED,
                    CandidateReasonCode.CRITICAL_EVIDENCE_STALE,
                }
                for item in reasons
            )
            critical_stale = CandidateReasonCode.CRITICAL_EVIDENCE_STALE in reasons
            eligibility = (
                CandidateEligibility.INELIGIBLE
                if hard_blocked or critical_stale
                else CandidateEligibility.ELIGIBLE
            )
            if hard_blocked or critical_stale:
                ranking_state = RankingState.INELIGIBLE
            elif critical_unavailable:
                ranking_state = RankingState.UNRANKED_CRITICAL_EVIDENCE
            elif coverage < MINIMUM_RANK_COVERAGE:
                ranking_state = RankingState.UNRANKED_LOW_COVERAGE
            else:
                ranking_state = RankingState.RANKED
            base_score: Decimal | None = None
            uncertainty_penalty: Decimal | None = None
            final_score: Decimal | None = None
            public_score: int | None = None
            if not hard_blocked and not critical_unavailable and scored_weight > 0:
                base_score = _quantize(Decimal("100") * weighted_score / scored_weight)
                uncertainty_penalty = _quantize(
                    min(
                        MAXIMUM_UNCERTAINTY_PENALTY,
                        Decimal("20") * (Decimal("1") - coverage)
                        + conflict_penalty
                        + staleness_penalty,
                    )
                )
                final_score = _quantize(
                    max(
                        Decimal("0"),
                        min(Decimal("100"), base_score - uncertainty_penalty),
                    )
                )
                if ranking_state is RankingState.RANKED:
                    public_score = int(
                        final_score.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)
                    )
            computed.append(
                CandidateRecommendationV2(
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
                    unknown_axis_ids=tuple(
                        sorted(set(unknown), key=lambda item: item.value.int)
                    ),
                    missing_axis_ids=tuple(
                        sorted(set(missing), key=lambda item: item.value.int)
                    ),
                    conflicting_axis_ids=tuple(
                        sorted(set(conflicting), key=lambda item: item.value.int)
                    ),
                    unsupported_axis_ids=tuple(
                        sorted(set(unsupported), key=lambda item: item.value.int)
                    ),
                    near_expiry_axis_ids=tuple(
                        sorted(set(near_expiry), key=lambda item: item.value.int)
                    ),
                    stale_axis_ids=tuple(
                        sorted(set(stale), key=lambda item: item.value.int)
                    ),
                )
            )
    ranked = sorted(
        (
            item
            for item in computed
            if item.ranking_state is RankingState.RANKED
            and item.final_score is not None
        ),
        key=lambda item: (-cast(Decimal, item.final_score), item.product_id.value.int),
    )
    groups: list[list[CandidateRecommendationV2]] = []
    for candidate in ranked:
        if not groups:
            groups.append([candidate])
            continue
        anchor = groups[-1][0].final_score
        if (
            cast(Decimal, anchor) - cast(Decimal, candidate.final_score)
            <= CO_RECOMMEND_MAXIMUM_DIFFERENCE
        ):
            groups[-1].append(candidate)
        else:
            groups.append([candidate])
    updates: dict[UUID, CandidateRecommendationV2] = {}
    for group_number, group in enumerate(groups, start=1):
        anchor = cast(Decimal, group[0].final_score)
        tied = len(group) > 1
        for candidate in group:
            updates[candidate.product_id.value] = replace(
                candidate,
                rank_group=group_number,
                tie_group=group_number,
                group_anchor_score=anchor,
                co_recommended=tied,
                strict_order_allowed=not tied,
                primary_recommendation_allowed=(
                    group_number == 1
                    and candidate.weighted_evidence_coverage >= MINIMUM_PRIMARY_COVERAGE
                ),
            )
    return tuple(updates.get(item.product_id.value, item) for item in computed)


def _explanation_material(
    value: RecommendationEnvelopeV2,
    candidates: tuple[CandidateRecommendationV2, ...],
) -> dict[str, object]:
    report = value.comparison_report
    ranking_order = tuple(
        item.product_id
        for item in sorted(
            (item for item in candidates if item.ranking_state is RankingState.RANKED),
            key=lambda item: (cast(int, item.rank_group), item.product_id.value.int),
        )
    )
    return {
        "assessments": [
            _assessment_material(item)
            for item in sorted(
                value.assessments,
                key=lambda item: (item.product_id.value.int, item.axis_id.value.int),
            )
        ],
        "authority": {
            "activation_authorized": False,
            "approval_authorized": False,
            "override_supported": False,
            "production_eligible": False,
            "publication_authorized": False,
            "ranking_authorized": False,
            "recommendation_authorized": False,
        },
        "candidates": [_candidate_material(item) for item in candidates],
        "comparison": {
            "article_binding_sha256": _required_digest(
                report.article_binding_sha256
            ).value,
            "axis_catalog_sha256": _required_digest(report.axis_catalog_sha256).value,
            "candidate_universe_sha256": _required_digest(
                report.candidate_universe_sha256
            ).value,
            "complete_claim_set_sha256": _required_digest(
                report.complete_claim_set_sha256
            ).value,
            "evaluation_input_sha256": _required_digest(
                report.evaluation_input_sha256
            ).value,
            "fact_set_sha256": _required_digest(report.fact_set_sha256).value,
            "report_sha256": report.report_sha256.value,
            "receipt": {
                "receipt_sha256": comparison_receipt_sha256(
                    value.comparison_receipt
                ).value,
                "report_sha256": value.comparison_receipt.report_sha256.value,
                "sequence": value.comparison_receipt.sequence,
            },
            "st0605_comparison_requirement_set_sha256": (
                _required_digest(report.st0605_comparison_requirement_set_sha256).value
            ),
            "temporal_scope_sha256": _required_digest(
                report.temporal_scope_sha256
            ).value,
        },
        "context": {
            **_context_material(value.context),
            "binding_sha256": value.context.binding_sha256.value,
        },
        "dimensions": [
            _dimension_material(item)
            for item in sorted(
                value.dimensions, key=lambda item: item.axis_id.value.int
            )
        ],
        "engine_contract": {
            "co_recommend_maximum_difference": "2.0",
            "conflict_policy": "UPSTREAM_ST0803_BLOCK_OR_EXPLICIT_PENALTY",
            "internal_precision": "0.0001",
            "minimum_primary_coverage": "0.90",
            "minimum_rank_coverage": "0.80",
            "normalization_input_basis": (
                "VALIDATED_SPECIFICATION_OR_USE_CONDITION_ONLY"
            ),
            "penalty_cap": "20",
            "rounding": "ROUND_HALF_EVEN",
            "score_clamp": ["0", "100"],
            "tie_anchor": "HIGHEST_SCORE_IN_GROUP",
            "tie_member_order": "PRODUCT_ID_ASCENDING",
            "unknown_coercion": "FORBIDDEN",
            "uncertainty_formula": (
                "min(20,20*(1-coverage)+conflict_penalty+staleness_penalty)"
            ),
        },
        "methodology": _methodology_material(value.methodology),
        "ranking_order": [str(item.value) for item in ranking_order],
        "recommendation_input_sha256": value.recommendation_input_sha256.value,
        "schema": "RAOS_ST0804_RECOMMENDATION_EXPLANATION_V2",
        "status": {
            "formal_tst_007": "NOT_EXECUTED",
            "formal_tst_020": "NOT_EXECUTED",
            "live_validation": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
        },
    }


def _report_material(
    value: RecommendationReportV2,
    *,
    include_digest: bool,
) -> dict[str, object]:
    material: dict[str, object] = {
        "activation_authorized": value.activation_authorized,
        "approval_authorized": value.approval_authorized,
        "article_binding_sha256": (
            None
            if value.article_binding_sha256 is None
            else value.article_binding_sha256.value
        ),
        "article_id": None if value.article_id is None else str(value.article_id.value),
        "article_version_id": (
            None
            if value.article_version_id is None
            else str(value.article_version_id.value)
        ),
        "assessment_set_sha256": (
            None
            if value.assessment_set_sha256 is None
            else value.assessment_set_sha256.value
        ),
        "axis_catalog_sha256": (
            None
            if value.axis_catalog_sha256 is None
            else value.axis_catalog_sha256.value
        ),
        "candidate_universe_sha256": (
            None
            if value.candidate_universe_sha256 is None
            else value.candidate_universe_sha256.value
        ),
        "candidates": [_candidate_material(item) for item in value.candidates],
        "comparison_evaluation_input_sha256": (
            None
            if value.comparison_evaluation_input_sha256 is None
            else value.comparison_evaluation_input_sha256.value
        ),
        "comparison_report_sha256": (
            None
            if value.comparison_report_sha256 is None
            else value.comparison_report_sha256.value
        ),
        "comparison_receipt_sha256": (
            None
            if value.comparison_receipt_sha256 is None
            else value.comparison_receipt_sha256.value
        ),
        "complete_claim_set_sha256": (
            None
            if value.complete_claim_set_sha256 is None
            else value.complete_claim_set_sha256.value
        ),
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "decision_context_sha256": (
            None
            if value.decision_context_sha256 is None
            else value.decision_context_sha256.value
        ),
        "dimension_set_sha256": (
            None
            if value.dimension_set_sha256 is None
            else value.dimension_set_sha256.value
        ),
        "evaluator_version": EVALUATOR_VERSION,
        "explanation": (
            None
            if value.explanation_json is None
            else json.loads(value.explanation_json)
        ),
        "explanation_sha256": (
            None if value.explanation_sha256 is None else value.explanation_sha256.value
        ),
        "fact_set_sha256": (
            None if value.fact_set_sha256 is None else value.fact_set_sha256.value
        ),
        "findings": [item.value for item in value.findings],
        "formal_tst_007_status": value.formal_tst_007_status.value,
        "formal_tst_020_status": value.formal_tst_020_status.value,
        "live_validation_status": value.live_validation_status.value,
        "methodology_sha256": (
            None if value.methodology_sha256 is None else value.methodology_sha256.value
        ),
        "override_supported": value.override_supported,
        "production_eligible": value.production_eligible,
        "production_status": value.production_status.value,
        "publication_authorized": value.publication_authorized,
        "ranking_authorized": value.ranking_authorized,
        "ranking_order": [str(item.value) for item in value.ranking_order],
        "recommendation_authorized": value.recommendation_authorized,
        "recommendation_input_sha256": (
            None
            if value.recommendation_input_sha256 is None
            else value.recommendation_input_sha256.value
        ),
        "release_status": value.release_status.value,
        "staging_status": value.staging_status.value,
        "status": value.status.value,
        "temporal_scope_sha256": (
            None
            if value.temporal_scope_sha256 is None
            else value.temporal_scope_sha256.value
        ),
    }
    if include_digest:
        material["report_sha256"] = value.report_sha256.value
    return material


def _report_bytes(value: RecommendationReportV2, *, include_digest: bool) -> bytes:
    return _canonical_bytes(_report_material(value, include_digest=include_digest))


def _make_report(
    *,
    envelope: RecommendationEnvelopeV2 | None,
    requested_article_version_id: ArticleVersionId | None,
    findings: set[RecommendationFindingCode],
    candidates: tuple[CandidateRecommendationV2, ...] = (),
    explanation_json: str | None = None,
) -> RecommendationReportV2:
    ordered_findings = tuple(
        code for code in RecommendationFindingCode if code in findings
    )
    status = _status_for_findings(set(ordered_findings))
    comparison_report = (
        envelope.comparison_report
        if type(envelope) is RecommendationEnvelopeV2
        and type(envelope.comparison_report) is ComparisonValidationReportV2
        else None
    )
    context = (
        envelope.context
        if type(envelope) is RecommendationEnvelopeV2
        and _context_shape(envelope.context)
        else None
    )
    receipt_digest: Sha256Digest | None = None
    if (
        type(envelope) is RecommendationEnvelopeV2
        and type(envelope.comparison_receipt) is ComparisonRecordReceipt
    ):
        try:
            receipt_digest = comparison_receipt_sha256(envelope.comparison_receipt)
        except Exception:
            receipt_digest = None
    safe_candidates = (
        candidates if status is RecommendationEvaluationStatus.LOCAL_CALCULATED else ()
    )
    safe_explanation = (
        explanation_json
        if status is RecommendationEvaluationStatus.LOCAL_CALCULATED
        else None
    )
    explanation_digest = (
        Sha256Digest(hashlib.sha256(safe_explanation.encode("ascii")).hexdigest())
        if safe_explanation is not None
        else None
    )
    ranking_order = tuple(
        item.product_id
        for item in sorted(
            (
                item
                for item in safe_candidates
                if item.ranking_state is RankingState.RANKED
            ),
            key=lambda item: (cast(int, item.rank_group), item.product_id.value.int),
        )
    )
    report = RecommendationReportV2(
        article_id=(
            comparison_report.article_id if comparison_report is not None else None
        ),
        article_version_id=(
            comparison_report.article_version_id
            if comparison_report is not None
            else requested_article_version_id
        ),
        article_binding_sha256=(
            comparison_report.article_binding_sha256
            if comparison_report is not None
            else None
        ),
        comparison_report_sha256=(
            comparison_report.report_sha256 if comparison_report is not None else None
        ),
        comparison_receipt_sha256=(receipt_digest),
        comparison_evaluation_input_sha256=(
            comparison_report.evaluation_input_sha256
            if comparison_report is not None
            else None
        ),
        candidate_universe_sha256=(
            comparison_report.candidate_universe_sha256
            if comparison_report is not None
            else None
        ),
        axis_catalog_sha256=(
            comparison_report.axis_catalog_sha256
            if comparison_report is not None
            else None
        ),
        fact_set_sha256=(
            comparison_report.fact_set_sha256 if comparison_report is not None else None
        ),
        temporal_scope_sha256=(
            comparison_report.temporal_scope_sha256
            if comparison_report is not None
            else None
        ),
        complete_claim_set_sha256=(
            comparison_report.complete_claim_set_sha256
            if comparison_report is not None
            else None
        ),
        decision_context_sha256=(
            context.binding_sha256 if context is not None else None
        ),
        methodology_sha256=(
            envelope.methodology.source_sha256
            if type(envelope) is RecommendationEnvelopeV2
            and _methodology_shape(envelope.methodology)
            else None
        ),
        dimension_set_sha256=(
            envelope.dimension_set_sha256
            if type(envelope) is RecommendationEnvelopeV2
            and _valid_digest(envelope.dimension_set_sha256)
            else None
        ),
        assessment_set_sha256=(
            envelope.assessment_set_sha256
            if type(envelope) is RecommendationEnvelopeV2
            and _valid_digest(envelope.assessment_set_sha256)
            else None
        ),
        recommendation_input_sha256=(
            envelope.recommendation_input_sha256
            if type(envelope) is RecommendationEnvelopeV2
            and _valid_digest(envelope.recommendation_input_sha256)
            else None
        ),
        status=status,
        findings=ordered_findings,
        candidates=safe_candidates,
        ranking_order=ranking_order,
        explanation_json=safe_explanation,
        explanation_sha256=explanation_digest,
        override_supported=False,
        approval_authorized=False,
        recommendation_authorized=False,
        ranking_authorized=False,
        publication_authorized=False,
        activation_authorized=False,
        production_eligible=False,
        formal_tst_007_status=ExecutionStatus.NOT_EXECUTED,
        formal_tst_020_status=ExecutionStatus.NOT_EXECUTED,
        live_validation_status=ExecutionStatus.NOT_EXECUTED,
        staging_status=ExecutionStatus.NOT_EXECUTED,
        release_status=ExecutionStatus.NOT_EXECUTED,
        production_status=ExecutionStatus.NOT_EXECUTED,
        report_sha256=Sha256Digest("0" * 64),
    )
    result = replace(
        report,
        report_sha256=Sha256Digest(
            hashlib.sha256(_report_bytes(report, include_digest=False)).hexdigest()
        ),
    )
    result.require_valid()
    return result


def unavailable_recommendation_report(
    requested_article_version_id: ArticleVersionId | None,
) -> RecommendationReportV2:
    if requested_article_version_id is not None and not _valid_entity(
        requested_article_version_id, ArticleVersionId
    ):
        requested_article_version_id = None
    return _make_report(
        envelope=None,
        requested_article_version_id=requested_article_version_id,
        findings={RecommendationFindingCode.INPUT_UNAVAILABLE},
    )


def _validate_context(
    envelope: RecommendationEnvelopeV2,
    report: ComparisonValidationReportV2,
    findings: set[RecommendationFindingCode],
) -> None:
    context = envelope.context
    if not _context_shape(context):
        findings.add(RecommendationFindingCode.CONTEXT_INVALID)
        return
    if any(
        prohibited_ranking_alias(value)
        for value in (
            context.target_reader_code,
            context.use_case_code,
            context.budget_context_code,
        )
    ):
        findings.add(RecommendationFindingCode.PROHIBITED_RANKING_INPUT)
    try:
        if context.binding_sha256 != decision_context_sha256(context):
            findings.add(RecommendationFindingCode.CONTEXT_BINDING_MISMATCH)
    except Exception:
        findings.add(RecommendationFindingCode.CONTEXT_INVALID)
    if (
        context.article_id != report.article_id
        or context.article_version_id != report.article_version_id
        or context.article_binding_sha256 != report.article_binding_sha256
    ):
        findings.add(RecommendationFindingCode.CONTEXT_BINDING_MISMATCH)


def _validate_dimensions(
    envelope: RecommendationEnvelopeV2,
    findings: set[RecommendationFindingCode],
) -> dict[UUID, RecommendationDimensionV2]:
    comparison = envelope.comparison.comparison
    if type(envelope.dimensions) is not tuple:
        findings.add(RecommendationFindingCode.COLLECTION_TYPE_INVALID)
        return {}
    if not 1 <= len(envelope.dimensions) <= _MAX_AXES:
        findings.add(RecommendationFindingCode.COLLECTION_BOUND_INVALID)
        return {}
    axis_by_id = {item.axis_id.value: item for item in comparison.axis_catalog.axes}
    dimensions: dict[UUID, RecommendationDimensionV2] = {}
    for dimension in envelope.dimensions:
        if not _dimension_shape(dimension):
            if (
                type(dimension) is RecommendationDimensionV2
                and type(dimension.weight) is Decimal
                and not _valid_decimal(
                    dimension.weight,
                    minimum=Decimal("0"),
                    maximum=Decimal("1"),
                    minimum_inclusive=False,
                )
            ):
                findings.add(RecommendationFindingCode.WEIGHT_INVALID)
            else:
                findings.add(RecommendationFindingCode.DIMENSION_INVALID)
            continue
        key = dimension.axis_id.value
        if key in dimensions:
            findings.add(RecommendationFindingCode.DUPLICATE_DIMENSION)
        dimensions[key] = dimension
        axis = axis_by_id.get(key)
        if axis is None:
            findings.add(RecommendationFindingCode.DIMENSION_SET_MISMATCH)
            continue
        if (
            prohibited_ranking_alias(axis.axis_code)
            or prohibited_ranking_alias(axis.label)
            or prohibited_ranking_alias(axis.description)
            or (
                axis.unit_family_code is not None
                and prohibited_ranking_alias(axis.unit_family_code)
            )
            or (axis.unit_code is not None and prohibited_ranking_alias(axis.unit_code))
            or dimension.axis_definition_sha256 != axis_definition_sha256(axis)
        ):
            findings.add(RecommendationFindingCode.PROHIBITED_RANKING_INPUT)
            if dimension.axis_definition_sha256 != axis_definition_sha256(axis):
                findings.add(RecommendationFindingCode.DIMENSION_INVALID)
    if set(dimensions) != set(axis_by_id) or len(envelope.dimensions) != len(
        axis_by_id
    ):
        findings.add(RecommendationFindingCode.DIMENSION_SET_MISMATCH)
    try:
        if envelope.dimension_set_sha256 != dimension_set_sha256(envelope.dimensions):
            findings.add(RecommendationFindingCode.DIMENSION_SET_HASH_MISMATCH)
    except Exception:
        findings.add(RecommendationFindingCode.DIMENSION_SET_HASH_MISMATCH)
    return dimensions


def _validate_assessments(
    envelope: RecommendationEnvelopeV2,
    dimensions: dict[UUID, RecommendationDimensionV2],
    findings: set[RecommendationFindingCode],
) -> dict[tuple[UUID, UUID], DimensionAssessmentV2]:
    comparison = envelope.comparison.comparison
    if type(envelope.assessments) is not tuple:
        findings.add(RecommendationFindingCode.COLLECTION_TYPE_INVALID)
        return {}
    if not 1 <= len(envelope.assessments) <= _MAX_ASSESSMENTS:
        findings.add(RecommendationFindingCode.COLLECTION_BOUND_INVALID)
        return {}
    cells = {
        (item.product_id.value, item.axis_id.value): item for item in comparison.cells
    }
    assessments: dict[tuple[UUID, UUID], DimensionAssessmentV2] = {}
    for assessment in envelope.assessments:
        if not _assessment_shape(assessment):
            findings.add(RecommendationFindingCode.ASSESSMENT_INVALID)
            continue
        coordinate = (assessment.product_id.value, assessment.axis_id.value)
        if coordinate in assessments:
            findings.add(RecommendationFindingCode.DUPLICATE_ASSESSMENT)
        assessments[coordinate] = assessment
        cell = cells.get(coordinate)
        dimension = dimensions.get(coordinate[1])
        if cell is None or dimension is None:
            findings.add(RecommendationFindingCode.ASSESSMENT_SET_MISMATCH)
            continue
        if (
            assessment.cell_status is not cell.status
            or assessment.fact_ids != cell.fact_ids
        ):
            findings.add(RecommendationFindingCode.CELL_BINDING_MISMATCH)
        available = cell.status is ComparisonCellStatus.VALID
        if available:
            if (
                assessment.normalization_basis is NormalizationBasis.UNAVAILABLE
                or assessment.normalization_basis is not dimension.normalization_basis
                or assessment.normalized_score is None
            ):
                findings.add(RecommendationFindingCode.SCORE_INVALID)
            else:
                try:
                    expected_input = normalization_input_sha256(
                        comparison=comparison,
                        context=envelope.context,
                        methodology=envelope.methodology,
                        dimension=dimension,
                        cell=cell,
                        basis=assessment.normalization_basis,
                    )
                    expected_decision = normalization_decision_sha256(
                        input_sha256=expected_input,
                        basis=assessment.normalization_basis,
                        normalized_score=assessment.normalized_score,
                    )
                    if (
                        assessment.normalization_input_sha256 != expected_input
                        or assessment.normalization_decision_sha256 != expected_decision
                    ):
                        findings.add(
                            RecommendationFindingCode.NORMALIZATION_BINDING_MISMATCH
                        )
                except Exception:
                    findings.add(
                        RecommendationFindingCode.NORMALIZATION_BINDING_MISMATCH
                    )
        else:
            if (
                assessment.normalization_basis is not NormalizationBasis.UNAVAILABLE
                or assessment.normalized_score is not None
            ):
                findings.add(RecommendationFindingCode.SCORE_INVALID)
            try:
                expected_input = unavailable_normalization_input_sha256(
                    comparison=comparison,
                    context=envelope.context,
                    dimension=dimension,
                    cell=cell,
                )
                expected_decision = unavailable_normalization_decision_sha256(
                    expected_input
                )
                if (
                    assessment.normalization_input_sha256 != expected_input
                    or assessment.normalization_decision_sha256 != expected_decision
                ):
                    findings.add(
                        RecommendationFindingCode.NORMALIZATION_BINDING_MISMATCH
                    )
            except Exception:
                findings.add(RecommendationFindingCode.NORMALIZATION_BINDING_MISMATCH)
        if dimension.hard_constraint:
            allowed_hard = (
                {HardConstraintState.PASS, HardConstraintState.FAIL}
                if available
                else {HardConstraintState.UNAVAILABLE}
            )
        else:
            allowed_hard = {HardConstraintState.NOT_APPLICABLE}
        if assessment.hard_constraint_state not in allowed_hard:
            findings.add(RecommendationFindingCode.STATE_INVALID)
        if cell.status is ComparisonCellStatus.CONFLICT:
            conflict_valid = (
                assessment.conflict_state is ConflictState.CONFLICTING
                and assessment.conflict_penalty > Decimal("0")
            )
        elif available:
            conflict_valid = (
                assessment.conflict_state is ConflictState.NONE
                and assessment.conflict_penalty == Decimal("0")
            )
        else:
            conflict_valid = (
                assessment.conflict_state is ConflictState.UNAVAILABLE
                and assessment.conflict_penalty == Decimal("0")
            )
        if not conflict_valid:
            findings.add(RecommendationFindingCode.PENALTY_INVALID)
        if available:
            staleness_valid = (
                assessment.staleness_state is StalenessState.CURRENT
                and assessment.staleness_penalty == Decimal("0")
            ) or (
                assessment.staleness_state
                in {StalenessState.NEAR_EXPIRY, StalenessState.STALE}
                and assessment.staleness_penalty > Decimal("0")
            )
        else:
            staleness_valid = (
                assessment.staleness_state is StalenessState.UNAVAILABLE
                and assessment.staleness_penalty == Decimal("0")
            )
        if not staleness_valid:
            findings.add(RecommendationFindingCode.PENALTY_INVALID)
    expected = set(cells)
    if set(assessments) != expected or len(envelope.assessments) != len(expected):
        findings.add(RecommendationFindingCode.ASSESSMENT_SET_MISMATCH)
    try:
        if envelope.assessment_set_sha256 != assessment_set_sha256(
            envelope.assessments
        ):
            findings.add(RecommendationFindingCode.ASSESSMENT_SET_HASH_MISMATCH)
    except Exception:
        findings.add(RecommendationFindingCode.ASSESSMENT_SET_HASH_MISMATCH)
    return assessments


def evaluate_recommendations_v2(value: object) -> RecommendationReportV2:
    """Validate and calculate one local deterministic recommendation artifact."""

    if type(value) is not RecommendationEnvelopeV2:
        return _make_report(
            envelope=None,
            requested_article_version_id=None,
            findings={RecommendationFindingCode.INPUT_TYPE_INVALID},
        )
    envelope = value
    try:
        findings: set[RecommendationFindingCode] = set()
        if envelope.contract != RecommendationContractBinding.current():
            findings.add(RecommendationFindingCode.CONTRACT_BINDING_INVALID)
        actual = validate_comparison_v2(envelope.comparison)
        try:
            actual.require_valid()
        except Exception:
            findings.add(RecommendationFindingCode.COMPARISON_UNEVALUABLE)
        if actual.status is ComparisonValidationStatus.UNEVALUABLE:
            findings.add(RecommendationFindingCode.COMPARISON_UNEVALUABLE)
        elif actual.status is ComparisonValidationStatus.BLOCK:
            findings.add(RecommendationFindingCode.COMPARISON_BLOCKED)
        if type(envelope.comparison_report) is not ComparisonValidationReportV2:
            findings.add(RecommendationFindingCode.COMPARISON_REPORT_INVALID)
        else:
            try:
                envelope.comparison_report.require_valid()
                if (
                    envelope.comparison_report.canonical_bytes()
                    != actual.canonical_bytes()
                ):
                    findings.add(RecommendationFindingCode.COMPARISON_REPORT_MISMATCH)
            except Exception:
                findings.add(RecommendationFindingCode.COMPARISON_REPORT_INVALID)
        if type(envelope.comparison_receipt) is not ComparisonRecordReceipt:
            findings.add(RecommendationFindingCode.COMPARISON_RECEIPT_INVALID)
        else:
            try:
                envelope.comparison_receipt.require_valid()
                if envelope.comparison_receipt.report_sha256 != actual.report_sha256:
                    findings.add(RecommendationFindingCode.COMPARISON_RECEIPT_MISMATCH)
            except Exception:
                findings.add(RecommendationFindingCode.COMPARISON_RECEIPT_INVALID)
        if actual.status is not ComparisonValidationStatus.LOCAL_VALIDATED:
            return _make_report(
                envelope=envelope,
                requested_article_version_id=actual.article_version_id,
                findings=findings,
            )
        _validate_context(envelope, actual, findings)
        if any(
            prohibited_ranking_alias(product.inclusion_reason_code)
            for product in envelope.comparison.comparison.candidate_universe.products
        ):
            findings.add(RecommendationFindingCode.PROHIBITED_RANKING_INPUT)
        if not _methodology_shape(envelope.methodology):
            findings.add(RecommendationFindingCode.METHODOLOGY_INVALID)
        dimensions = _validate_dimensions(envelope, findings)
        assessments = _validate_assessments(envelope, dimensions, findings)
        try:
            if envelope.recommendation_input_sha256 != recommendation_input_sha256(
                envelope
            ):
                findings.add(
                    RecommendationFindingCode.RECOMMENDATION_INPUT_HASH_MISMATCH
                )
        except Exception:
            findings.add(RecommendationFindingCode.RECOMMENDATION_INPUT_HASH_MISMATCH)
        if findings:
            return _make_report(
                envelope=envelope,
                requested_article_version_id=actual.article_version_id,
                findings=findings,
            )
        ordered_assessments = tuple(
            assessments[key]
            for key in sorted(assessments, key=lambda item: (item[0].int, item[1].int))
        )
        ordered_dimensions = tuple(
            dimensions[key] for key in sorted(dimensions, key=lambda item: item.int)
        )
        candidates = _calculate_candidates(
            envelope.comparison.comparison,
            ordered_dimensions,
            ordered_assessments,
        )
        explanation_json = _canonical_bytes(
            _explanation_material(envelope, candidates)
        ).decode("ascii")
        return _make_report(
            envelope=envelope,
            requested_article_version_id=actual.article_version_id,
            findings=set(),
            candidates=candidates,
            explanation_json=explanation_json,
        )
    except Exception:
        return _make_report(
            envelope=None,
            requested_article_version_id=None,
            findings={RecommendationFindingCode.RECORD_TYPE_INVALID},
        )


__all__ = [
    "CO_RECOMMEND_MAXIMUM_DIFFERENCE",
    "CONTRACT_ID",
    "CONTRACT_VERSION",
    "CandidateEligibility",
    "CandidateReasonCode",
    "CandidateRecommendationV2",
    "ConflictState",
    "DecisionContextId",
    "DimensionAssessmentV2",
    "EVALUATOR_VERSION",
    "ExecutionStatus",
    "HardConstraintState",
    "INTERNAL_SCORE_QUANTUM",
    "MAXIMUM_UNCERTAINTY_PENALTY",
    "METHODOLOGY_ID",
    "METHODOLOGY_SOURCE_SHA256",
    "METHODOLOGY_VERSION",
    "MINIMUM_PRIMARY_COVERAGE",
    "MINIMUM_RANK_COVERAGE",
    "MethodologyBindingV2",
    "NormalizationBasis",
    "RankingState",
    "RecommendationContractBinding",
    "RecommendationDimensionV2",
    "RecommendationEnvelopeV2",
    "RecommendationEvaluationStatus",
    "RecommendationFindingCode",
    "RecommendationRecordReceipt",
    "RecommendationReportV2",
    "RecommendationRuleBinding",
    "RecommendationRuntimeValueError",
    "ST0803_CONTRACT_SHA256",
    "ST0803_DOMAIN_SHA256",
    "ST0803_RECORDED_FIXTURE_SHA256",
    "ST0803_RUNTIME_MANIFEST_SHA256",
    "StalenessState",
    "ArticleRecommendationContextV2",
    "assessment_set_sha256",
    "axis_definition_sha256",
    "comparison_receipt_sha256",
    "decision_context_sha256",
    "dimension_set_sha256",
    "evaluate_recommendations_v2",
    "normalization_decision_sha256",
    "normalization_input_sha256",
    "prohibited_ranking_alias",
    "recommendation_input_sha256",
    "unavailable_normalization_decision_sha256",
    "unavailable_normalization_input_sha256",
    "unavailable_recommendation_report",
]

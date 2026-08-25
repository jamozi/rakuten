"""Deterministic, receipt-producing ST-0803 comparison validation runtime V2.

The runtime validates an immutable, recorded-synthetic comparison snapshot and
the exact ST-0605 Claim/Evidence snapshot that consumes its comparison proof.
It never ranks, recommends, persists, publishes, or calls an external system.

The dependency cycle is intentionally split in two.  ST-0605 computes the
required ``COMPARISON`` attestation tuples without requiring a coverage PASS.
This module validates the comparison semantics and, only on a finding-free
local result, emits the matching recorded-synthetic receipts.  A caller may
then rerun ST-0605 with those receipts; this validator never mutates that
snapshot or treats its own output as prior authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
import re
from typing import NoReturn, SupportsIndex, cast
import unicodedata
from uuid import UUID

from raos.domain.catalog.ids import CanonicalProductId
from raos.domain.editorial.ids import ArticleId, ArticleVersionId, ComparisonAxisId
from raos.domain.evidence.claim_evidence import (
    ClaimEvidenceSnapshot,
    CoverageFindingCode,
    CoverageStatus as ClaimCoverageStatus,
    EvidenceValidationAttestation,
    IdentityStatus,
    PolicyClaimType,
    PolicyLinkSupportType,
    ValidationAttestationKind,
    ValidationAttestationOrigin,
    evaluate_claim_evidence,
    recorded_synthetic_attestation_decision_sha256,
    required_validation_attestation_inputs,
    validation_attestation_owner_binding,
)
from raos.domain.evidence.ids import FactId, SourcePacketVersionId
from raos.domain.shared.identity import EntityId, require_uuid
from raos.domain.shared.persistence import AwareUtcDateTime, Sha256Digest


CONTRACT_ID = "RAOS-ST0803-COMPARISON-VALIDATION-RUNTIME-002"
CONTRACT_VERSION = "2.0.0"
EVALUATOR_VERSION = "ST0803_COMPARISON_VALIDATOR_V2"
COMPARISON_SCHEMA_SHA256 = (
    "6da40ea538bd467a759613e0dca62f2e822ac4a9609adb71959d8bb624037c89"
)
IDENTITY_CONTRACT_SHA256 = (
    "246c21aa1d79489ed8c8a02fe0b7d1a50ffe1b2f7e85fcc4ba210369477512b8"
)
CLAIM_EVIDENCE_CONTRACT_SHA256 = (
    "7d84f3a4883a226eff782e976aa72169646be67bf1fc798af5b1b65367d2c3cb"
)
ARTICLE_LIFECYCLE_SOURCE_SHA256 = (
    "c44cb8c5d26f4862e7527bcb179c20f1f60d3a069d9ba67fad3b0109ef0c6edd"
)

_MAX_EXACT_INT = (1 << 53) - 1
_MAX_PRODUCTS = 20
_MAX_AXES = 30
_MAX_CELLS = _MAX_PRODUCTS * _MAX_AXES
_MAX_FACTS = _MAX_CELLS * 2
_MAX_CLAIMS = 100
_MAX_LINKS = 1_000
_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z", re.ASCII)
_UNIT_CODE = re.compile(r"[A-Z][A-Z0-9_.:-]{0,63}\Z", re.ASCII)

_FORBIDDEN_AXIS_TOKENS = frozenset(
    {
        "AFF",
        "AFFIL",
        "AFFILIATE",
        "CPA",
        "COMMISSION",
        "COST",
        "EPC",
        "FEE",
        "MARGIN",
        "MONETIZATION",
        "PAYOUT",
        "PROFIT",
        "RATE",
        "REV",
        "REVENUE",
        "REWARD",
        "ROAS",
        "ROI",
        "RPM",
        "SPONSOR",
        "SPONSORSHIP",
    }
)
_FORBIDDEN_AXIS_COLLAPSED = frozenset(
    {
        "AFFILIATERATE",
        "AFFILIATEFEE",
        "COMMISSIONRATE",
        "CONFIRMEDCOMMISSION",
        "CONTRIBUTIONPROFIT",
        "SPONSORBENEFIT",
    }
)
_FORBIDDEN_LABEL_FRAGMENTS = (
    "affiliate",
    "commission",
    "contribution profit",
    "epc",
    "monetization",
    "payout",
    "revenue",
    "rpm",
    "sponsor benefit",
    "アフィリエイト",
    "コミッション",
    "スポンサー便益",
    "成果報酬",
    "報酬率",
    "収益",
    "手数料",
    "料率",
    "利益",
)
_LEET_TRANSLATION = str.maketrans(
    {
        "0": "O",
        "1": "I",
        "3": "E",
        "4": "A",
        "5": "S",
        "7": "T",
    }
)


class ComparisonRuntimeValueError(ValueError):
    """Closed construction failure which never includes untrusted input."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("INVALID_COMPARISON_RUNTIME_VALUE")


def _invalid() -> NoReturn:
    raise ComparisonRuntimeValueError() from None


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-st0803-v2>)"

    def __str__(self) -> str:
        return "<redacted-st0803-v2>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("ST-0803 V2 generic serialization is not supported")


class ComparisonValidationStatus(str, Enum):
    LOCAL_VALIDATED = "LOCAL_VALIDATED"
    BLOCK = "BLOCK"
    UNEVALUABLE = "UNEVALUABLE"


class ComparisonCellStatus(str, Enum):
    VALID = "VALID"
    UNKNOWN = "UNKNOWN"
    MISSING = "MISSING"
    CONFLICT = "CONFLICT"
    UNSUPPORTED = "UNSUPPORTED"


class ComparisonAxisDataType(str, Enum):
    TEXT = "TEXT"
    DECIMAL = "DECIMAL"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    CODE = "CODE"


class ExecutionStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


class ComparisonFindingCode(str, Enum):
    INPUT_TYPE_INVALID = "INPUT_TYPE_INVALID"
    INPUT_UNAVAILABLE = "INPUT_UNAVAILABLE"
    CONTRACT_BINDING_INVALID = "CONTRACT_BINDING_INVALID"
    ARTICLE_BINDING_INVALID = "ARTICLE_BINDING_INVALID"
    ARTICLE_BINDING_HASH_MISMATCH = "ARTICLE_BINDING_HASH_MISMATCH"
    COLLECTION_TYPE_INVALID = "COLLECTION_TYPE_INVALID"
    COLLECTION_BOUND_INVALID = "COLLECTION_BOUND_INVALID"
    RECORD_TYPE_INVALID = "RECORD_TYPE_INVALID"
    CANDIDATE_UNIVERSE_INVALID = "CANDIDATE_UNIVERSE_INVALID"
    CANDIDATE_UNIVERSE_HASH_MISMATCH = "CANDIDATE_UNIVERSE_HASH_MISMATCH"
    AXIS_CATALOG_INVALID = "AXIS_CATALOG_INVALID"
    AXIS_CATALOG_HASH_MISMATCH = "AXIS_CATALOG_HASH_MISMATCH"
    FACT_SET_INVALID = "FACT_SET_INVALID"
    FACT_SET_HASH_MISMATCH = "FACT_SET_HASH_MISMATCH"
    TEMPORAL_SCOPE_HASH_MISMATCH = "TEMPORAL_SCOPE_HASH_MISMATCH"
    EVALUATION_INPUT_HASH_MISMATCH = "EVALUATION_INPUT_HASH_MISMATCH"
    DUPLICATE_PRODUCT = "DUPLICATE_PRODUCT"
    DUPLICATE_AXIS = "DUPLICATE_AXIS"
    DUPLICATE_POSITION = "DUPLICATE_POSITION"
    DUPLICATE_FACT = "DUPLICATE_FACT"
    DUPLICATE_CELL = "DUPLICATE_CELL"
    CELL_MATRIX_INCOMPLETE = "CELL_MATRIX_INCOMPLETE"
    REFERENCE_INVALID = "REFERENCE_INVALID"
    FACT_REFERENCE_SET_MISMATCH = "FACT_REFERENCE_SET_MISMATCH"
    ST0605_INPUT_INVALID = "ST0605_INPUT_INVALID"
    ST0605_BASELINE_UNTRUSTED = "ST0605_BASELINE_UNTRUSTED"
    PREEXISTING_COMPARISON_RECEIPT = "PREEXISTING_COMPARISON_RECEIPT"
    COMPARISON_REQUIREMENT_MISSING = "COMPARISON_REQUIREMENT_MISSING"
    IDENTITY_RECEIPT_MISSING = "IDENTITY_RECEIPT_MISSING"
    PROHIBITED_AXIS = "PROHIBITED_AXIS"
    IDENTITY_UNRESOLVED = "IDENTITY_UNRESOLVED"
    IDENTITY_SUBJECT_MISMATCH = "IDENTITY_SUBJECT_MISMATCH"
    VARIANT_MISMATCH = "VARIANT_MISMATCH"
    VALUE_TYPE_MISMATCH = "VALUE_TYPE_MISMATCH"
    VALUE_BINDING_MISMATCH = "VALUE_BINDING_MISMATCH"
    UNIT_BINDING_MISMATCH = "UNIT_BINDING_MISMATCH"
    UNKNOWN_VISIBILITY_REQUIRED = "UNKNOWN_VISIBILITY_REQUIRED"
    UNKNOWN_VALUE_IMPUTATION_FORBIDDEN = "UNKNOWN_VALUE_IMPUTATION_FORBIDDEN"
    REQUIRED_VALUE_MISSING = "REQUIRED_VALUE_MISSING"
    CONFLICTING_VALUE = "CONFLICTING_VALUE"
    UNSUPPORTED_VALUE = "UNSUPPORTED_VALUE"
    FACT_FROM_FUTURE = "FACT_FROM_FUTURE"
    STALE_FACT = "STALE_FACT"
    CLAIM_POPULATION_MISMATCH = "CLAIM_POPULATION_MISMATCH"
    CLAIM_TEMPORAL_SCOPE_MISMATCH = "CLAIM_TEMPORAL_SCOPE_MISMATCH"
    CLAIM_FACT_SET_MISMATCH = "CLAIM_FACT_SET_MISMATCH"
    ST0605_SEMANTIC_BLOCK = "ST0605_SEMANTIC_BLOCK"


_STRUCTURAL_FINDINGS = frozenset(
    {
        ComparisonFindingCode.INPUT_TYPE_INVALID,
        ComparisonFindingCode.INPUT_UNAVAILABLE,
        ComparisonFindingCode.CONTRACT_BINDING_INVALID,
        ComparisonFindingCode.ARTICLE_BINDING_INVALID,
        ComparisonFindingCode.ARTICLE_BINDING_HASH_MISMATCH,
        ComparisonFindingCode.COLLECTION_TYPE_INVALID,
        ComparisonFindingCode.COLLECTION_BOUND_INVALID,
        ComparisonFindingCode.RECORD_TYPE_INVALID,
        ComparisonFindingCode.CANDIDATE_UNIVERSE_INVALID,
        ComparisonFindingCode.CANDIDATE_UNIVERSE_HASH_MISMATCH,
        ComparisonFindingCode.AXIS_CATALOG_INVALID,
        ComparisonFindingCode.AXIS_CATALOG_HASH_MISMATCH,
        ComparisonFindingCode.FACT_SET_INVALID,
        ComparisonFindingCode.FACT_SET_HASH_MISMATCH,
        ComparisonFindingCode.TEMPORAL_SCOPE_HASH_MISMATCH,
        ComparisonFindingCode.EVALUATION_INPUT_HASH_MISMATCH,
        ComparisonFindingCode.DUPLICATE_PRODUCT,
        ComparisonFindingCode.DUPLICATE_AXIS,
        ComparisonFindingCode.DUPLICATE_POSITION,
        ComparisonFindingCode.DUPLICATE_FACT,
        ComparisonFindingCode.DUPLICATE_CELL,
        ComparisonFindingCode.CELL_MATRIX_INCOMPLETE,
        ComparisonFindingCode.REFERENCE_INVALID,
        ComparisonFindingCode.FACT_REFERENCE_SET_MISMATCH,
        ComparisonFindingCode.ST0605_INPUT_INVALID,
        ComparisonFindingCode.ST0605_BASELINE_UNTRUSTED,
        ComparisonFindingCode.PREEXISTING_COMPARISON_RECEIPT,
        ComparisonFindingCode.COMPARISON_REQUIREMENT_MISSING,
        ComparisonFindingCode.IDENTITY_RECEIPT_MISSING,
    }
)

_TRUSTED_ST0605_SEMANTIC_FINDINGS = frozenset(
    {
        CoverageFindingCode.IDENTITY_UNRESOLVED,
        CoverageFindingCode.IDENTITY_CONFLICT,
        CoverageFindingCode.PREDICTIVE_CLAIM_DEFAULT_BLOCKED,
        CoverageFindingCode.UNKNOWN_VALUE_IMPUTATION_FORBIDDEN,
        CoverageFindingCode.SOURCE_INACTIVE,
        CoverageFindingCode.SOURCE_TIER_MISMATCH,
        CoverageFindingCode.AI_OUTPUT_IS_NOT_EVIDENCE,
        CoverageFindingCode.SEARCH_SNIPPET_IS_NOT_EVIDENCE,
        CoverageFindingCode.RAKUTEN_REVIEW_BODY_PROHIBITED,
        CoverageFindingCode.COMPETITOR_CONTENT_DISCOVERY_ONLY,
        CoverageFindingCode.SNAPSHOT_INVALID,
        CoverageFindingCode.STALE_EVIDENCE,
        CoverageFindingCode.UNRESOLVED_CONFLICT,
        CoverageFindingCode.QUALIFIES_WITHOUT_SUPPORT,
        CoverageFindingCode.CONTRADICTORY_EVIDENCE,
        CoverageFindingCode.EVIDENCE_REQUIRED,
        CoverageFindingCode.MAJOR_COVERAGE_BELOW_100,
        CoverageFindingCode.ALL_COVERAGE_BELOW_95,
        CoverageFindingCode.CLAIM_SUBJECT_IDENTITY_MISMATCH,
        CoverageFindingCode.FUTURE_EVIDENCE,
        CoverageFindingCode.EVIDENCE_TIME_WINDOW_INVALID,
        CoverageFindingCode.OFFER_EXPIRY_REQUIRED,
        CoverageFindingCode.CONFLICT_RESOLUTION_EVIDENCE_REQUIRED,
    }
)


class CandidateUniverseId(EntityId):
    __slots__ = ()


class AxisCatalogId(EntityId):
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
        and re.fullmatch(r"[0-9a-f]{64}", value.value, re.ASCII) is not None
    )


def _valid_instant(value: object) -> bool:
    return (
        type(value) is AwareUtcDateTime
        and type(value.value) is datetime
        and value.value.tzinfo is timezone.utc
        and not value.value.fold
        and value.value.microsecond == 0
    )


def _instant_text(value: AwareUtcDateTime) -> str:
    if not _valid_instant(value):
        _invalid()
    return value.value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_text(value: object, *, maximum: int) -> bool:
    return (
        type(value) is str
        and 1 <= len(value) <= maximum
        and value == value.strip()
        and unicodedata.normalize("NFC", value) == value
        and all(
            not unicodedata.category(character).startswith("C") for character in value
        )
    )


def _safe_code(value: object, *, unit: bool = False) -> bool:
    pattern = _UNIT_CODE if unit else _CODE
    return type(value) is str and pattern.fullmatch(value) is not None


def _axis_is_prohibited(code: str, label: str) -> bool:
    if not _safe_code(code) or not _safe_text(label, maximum=120):
        return True
    normalized_code = code.translate(_LEET_TRANSLATION)
    tokens = tuple(item for item in normalized_code.split("_") if item)
    collapsed = "".join(tokens)
    if any(token in _FORBIDDEN_AXIS_TOKENS for token in tokens):
        return True
    if any(fragment in collapsed for fragment in _FORBIDDEN_AXIS_COLLAPSED):
        return True
    normalized_label = unicodedata.normalize("NFKC", label).casefold()
    return any(fragment in normalized_label for fragment in _FORBIDDEN_LABEL_FRAGMENTS)


def canonical_decimal(value: Decimal) -> str:
    """Return a context-independent NUMERIC(30,10) canonical string."""

    if type(value) is not Decimal or not value.is_finite():
        _invalid()
    sign, digits_tuple, exponent = value.as_tuple()
    if type(exponent) is not int:
        _invalid()
    if all(item == 0 for item in digits_tuple):
        return "0"
    trimmed = digits_tuple
    while trimmed and trimmed[-1] == 0:
        trimmed = trimmed[:-1]
        exponent += 1
    if not trimmed or len(trimmed) > 30:
        _invalid()
    point = len(trimmed) + exponent
    if point <= 0:
        fractional_length = -point + len(trimmed)
        integer_length = 1
    else:
        fractional_length = max(0, len(trimmed) - point)
        integer_length = point
    if integer_length > 20 or fractional_length > 10:
        _invalid()
    digits = "".join(str(item) for item in trimmed)
    if point <= 0:
        rendered = "0." + ("0" * (-point)) + digits
    elif point >= len(digits):
        rendered = digits + ("0" * (point - len(digits)))
    else:
        rendered = digits[:point] + "." + digits[point:]
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    integer_part, dot, fractional_part = rendered.partition(".")
    integer_part = integer_part.lstrip("0") or "0"
    if len(integer_part) > 20 or (dot and len(fractional_part) > 10):
        _invalid()
    canonical = integer_part + (("." + fractional_part) if dot else "")
    if sign:
        canonical = "-" + canonical
    return canonical


@dataclass(frozen=True, slots=True, repr=False)
class TypedComparisonValue(_Redacted):
    data_type: ComparisonAxisDataType
    text_value: str | None = None
    decimal_value: Decimal | None = None
    boolean_value: bool | None = None
    date_value: date | None = None
    code_value: str | None = None

    def __post_init__(self) -> None:
        if not _valid_typed_value(self):
            _invalid()


def _valid_typed_value(value: object) -> bool:
    if (
        type(value) is not TypedComparisonValue
        or type(value.data_type) is not ComparisonAxisDataType
    ):
        return False
    populated = sum(
        item is not None
        for item in (
            value.text_value,
            value.decimal_value,
            value.boolean_value,
            value.date_value,
            value.code_value,
        )
    )
    if populated != 1:
        return False
    try:
        if value.data_type is ComparisonAxisDataType.TEXT:
            return (
                _safe_text(value.text_value, maximum=512)
                and value.decimal_value is None
                and value.boolean_value is None
                and value.date_value is None
                and value.code_value is None
            )
        if value.data_type is ComparisonAxisDataType.DECIMAL:
            if (
                value.text_value is not None
                or value.boolean_value is not None
                or value.date_value is not None
                or value.code_value is not None
            ):
                return False
            canonical_decimal(cast(Decimal, value.decimal_value))
            return True
        if value.data_type is ComparisonAxisDataType.BOOLEAN:
            return (
                value.text_value is None
                and value.decimal_value is None
                and type(value.boolean_value) is bool
                and value.date_value is None
                and value.code_value is None
            )
        if value.data_type is ComparisonAxisDataType.DATE:
            return (
                value.text_value is None
                and value.decimal_value is None
                and value.boolean_value is None
                and type(value.date_value) is date
                and value.code_value is None
            )
        return (
            value.text_value is None
            and value.decimal_value is None
            and value.boolean_value is None
            and value.date_value is None
            and _safe_code(value.code_value)
        )
    except Exception:
        return False


def _typed_value_material(value: TypedComparisonValue) -> dict[str, object]:
    if not _valid_typed_value(value):
        _invalid()
    rendered: object
    if value.data_type is ComparisonAxisDataType.TEXT:
        rendered = value.text_value
    elif value.data_type is ComparisonAxisDataType.DECIMAL:
        rendered = canonical_decimal(cast(Decimal, value.decimal_value))
    elif value.data_type is ComparisonAxisDataType.BOOLEAN:
        rendered = value.boolean_value
    elif value.data_type is ComparisonAxisDataType.DATE:
        rendered = cast(date, value.date_value).isoformat()
    else:
        rendered = value.code_value
    return {"data_type": value.data_type.value, "value": rendered}


@dataclass(frozen=True, slots=True, repr=False)
class ComparisonContractBinding(_Redacted):
    contract_id: str
    contract_version: str
    evaluator_version: str
    comparison_schema_sha256: Sha256Digest
    identity_contract_sha256: Sha256Digest
    claim_evidence_contract_sha256: Sha256Digest
    article_lifecycle_source_sha256: Sha256Digest

    @classmethod
    def current(cls) -> ComparisonContractBinding:
        return cls(
            contract_id=CONTRACT_ID,
            contract_version=CONTRACT_VERSION,
            evaluator_version=EVALUATOR_VERSION,
            comparison_schema_sha256=Sha256Digest(COMPARISON_SCHEMA_SHA256),
            identity_contract_sha256=Sha256Digest(IDENTITY_CONTRACT_SHA256),
            claim_evidence_contract_sha256=Sha256Digest(CLAIM_EVIDENCE_CONTRACT_SHA256),
            article_lifecycle_source_sha256=Sha256Digest(
                ARTICLE_LIFECYCLE_SOURCE_SHA256
            ),
        )


def _contract_valid(value: object) -> bool:
    return (
        type(value) is ComparisonContractBinding
        and value == ComparisonContractBinding.current()
    )


@dataclass(frozen=True, slots=True, repr=False)
class ArticleComparisonBinding(_Redacted):
    article_id: ArticleId
    article_version_id: ArticleVersionId
    article_version_no: int
    article_body_sha256: Sha256Digest
    source_packet_version_id: SourcePacketVersionId
    source_packet_content_sha256: Sha256Digest
    complete_claim_set_sha256: Sha256Digest
    binding_sha256: Sha256Digest


def _article_shape(value: object) -> bool:
    return (
        type(value) is ArticleComparisonBinding
        and _valid_entity(value.article_id, ArticleId)
        and _valid_entity(value.article_version_id, ArticleVersionId)
        and type(value.article_version_no) is int
        and 1 <= value.article_version_no <= _MAX_EXACT_INT
        and _valid_digest(value.article_body_sha256)
        and _valid_entity(value.source_packet_version_id, SourcePacketVersionId)
        and _valid_digest(value.source_packet_content_sha256)
        and _valid_digest(value.complete_claim_set_sha256)
        and _valid_digest(value.binding_sha256)
    )


def _article_material(value: ArticleComparisonBinding) -> dict[str, object]:
    if not _article_shape(value):
        _invalid()
    return {
        "article_id": str(value.article_id.value),
        "article_version_id": str(value.article_version_id.value),
        "article_version_no": value.article_version_no,
        "article_body_sha256": value.article_body_sha256.value,
        "source_packet_version_id": str(value.source_packet_version_id.value),
        "source_packet_content_sha256": value.source_packet_content_sha256.value,
        "complete_claim_set_sha256": value.complete_claim_set_sha256.value,
    }


@dataclass(frozen=True, slots=True, repr=False)
class ComparisonProduct(_Redacted):
    product_id: CanonicalProductId
    variant_identity_sha256: Sha256Digest
    subject_identity_sha256: Sha256Digest
    inclusion_reason_code: str


def _product_shape(value: object) -> bool:
    return (
        type(value) is ComparisonProduct
        and _valid_entity(value.product_id, CanonicalProductId)
        and _valid_digest(value.variant_identity_sha256)
        and _valid_digest(value.subject_identity_sha256)
        and _safe_code(value.inclusion_reason_code)
    )


@dataclass(frozen=True, slots=True, repr=False)
class CandidateUniverse(_Redacted):
    universe_id: CandidateUniverseId
    version_no: int
    products: tuple[ComparisonProduct, ...]
    candidate_universe_sha256: Sha256Digest


def _candidate_material(value: CandidateUniverse) -> dict[str, object]:
    if (
        type(value) is not CandidateUniverse
        or not _valid_entity(value.universe_id, CandidateUniverseId)
        or type(value.version_no) is not int
        or not 1 <= value.version_no <= _MAX_EXACT_INT
        or type(value.products) is not tuple
        or not 2 <= len(value.products) <= _MAX_PRODUCTS
        or any(not _product_shape(item) for item in value.products)
    ):
        _invalid()
    return {
        "universe_id": str(value.universe_id.value),
        "version_no": value.version_no,
        "products": [
            {
                "inclusion_reason_code": item.inclusion_reason_code,
                "product_id": str(item.product_id.value),
                "subject_identity_sha256": item.subject_identity_sha256.value,
                "variant_identity_sha256": item.variant_identity_sha256.value,
            }
            for item in value.products
        ],
    }


@dataclass(frozen=True, slots=True, repr=False)
class ComparisonAxisDefinition(_Redacted):
    axis_id: ComparisonAxisId
    axis_code: str
    label: str
    description: str
    data_type: ComparisonAxisDataType
    unit_family_code: str | None
    unit_code: str | None
    position: int
    required: bool


def _axis_shape(value: object) -> bool:
    if not (
        type(value) is ComparisonAxisDefinition
        and _valid_entity(value.axis_id, ComparisonAxisId)
        and _safe_code(value.axis_code)
        and _safe_text(value.label, maximum=120)
        and _safe_text(value.description, maximum=500)
        and type(value.data_type) is ComparisonAxisDataType
        and type(value.position) is int
        and 0 <= value.position < _MAX_AXES
        and type(value.required) is bool
    ):
        return False
    if value.data_type is ComparisonAxisDataType.DECIMAL:
        return _safe_code(value.unit_family_code, unit=True) and _safe_code(
            value.unit_code, unit=True
        )
    return value.unit_family_code is None and value.unit_code is None


@dataclass(frozen=True, slots=True, repr=False)
class ComparisonAxisCatalog(_Redacted):
    catalog_id: AxisCatalogId
    version_no: int
    source_sha256: Sha256Digest
    axes: tuple[ComparisonAxisDefinition, ...]
    axis_catalog_sha256: Sha256Digest


def _axis_catalog_material(value: ComparisonAxisCatalog) -> dict[str, object]:
    if (
        type(value) is not ComparisonAxisCatalog
        or not _valid_entity(value.catalog_id, AxisCatalogId)
        or type(value.version_no) is not int
        or not 1 <= value.version_no <= _MAX_EXACT_INT
        or not _valid_digest(value.source_sha256)
        or type(value.axes) is not tuple
        or not 1 <= len(value.axes) <= _MAX_AXES
        or any(not _axis_shape(item) for item in value.axes)
    ):
        _invalid()
    return {
        "catalog_id": str(value.catalog_id.value),
        "version_no": value.version_no,
        "source_sha256": value.source_sha256.value,
        "axes": [
            {
                "axis_code": item.axis_code,
                "axis_id": str(item.axis_id.value),
                "data_type": item.data_type.value,
                "description": item.description,
                "label": item.label,
                "position": item.position,
                "required": item.required,
                "unit_code": item.unit_code,
                "unit_family_code": item.unit_family_code,
            }
            for item in value.axes
        ],
    }


@dataclass(frozen=True, slots=True, repr=False)
class ComparisonFactBinding(_Redacted):
    fact_id: FactId
    fact_sha256: Sha256Digest
    product_id: CanonicalProductId
    variant_identity_sha256: Sha256Digest
    subject_identity_sha256: Sha256Digest
    axis_id: ComparisonAxisId
    value: TypedComparisonValue
    unit_code: str | None
    observed_at: AwareUtcDateTime
    valid_from: AwareUtcDateTime
    valid_until: AwareUtcDateTime


def _fact_shape(value: object) -> bool:
    return (
        type(value) is ComparisonFactBinding
        and _valid_entity(value.fact_id, FactId)
        and _valid_digest(value.fact_sha256)
        and _valid_entity(value.product_id, CanonicalProductId)
        and _valid_digest(value.variant_identity_sha256)
        and _valid_digest(value.subject_identity_sha256)
        and _valid_entity(value.axis_id, ComparisonAxisId)
        and _valid_typed_value(value.value)
        and (value.unit_code is None or _safe_code(value.unit_code, unit=True))
        and _valid_instant(value.observed_at)
        and _valid_instant(value.valid_from)
        and _valid_instant(value.valid_until)
    )


def _fact_material(value: ComparisonFactBinding) -> dict[str, object]:
    if not _fact_shape(value):
        _invalid()
    return {
        "axis_id": str(value.axis_id.value),
        "fact_id": str(value.fact_id.value),
        "fact_sha256": value.fact_sha256.value,
        "observed_at": _instant_text(value.observed_at),
        "product_id": str(value.product_id.value),
        "subject_identity_sha256": value.subject_identity_sha256.value,
        "unit_code": value.unit_code,
        "valid_from": _instant_text(value.valid_from),
        "valid_until": _instant_text(value.valid_until),
        "value": _typed_value_material(value.value),
        "variant_identity_sha256": value.variant_identity_sha256.value,
    }


@dataclass(frozen=True, slots=True, repr=False)
class ComparisonCell(_Redacted):
    product_id: CanonicalProductId
    axis_id: ComparisonAxisId
    status: ComparisonCellStatus
    value: TypedComparisonValue | None
    unit_code: str | None
    fact_ids: tuple[FactId, ...]
    reason_code: str | None
    imputed: bool = False


def _cell_shape(value: object) -> bool:
    return (
        type(value) is ComparisonCell
        and _valid_entity(value.product_id, CanonicalProductId)
        and _valid_entity(value.axis_id, ComparisonAxisId)
        and type(value.status) is ComparisonCellStatus
        and (value.value is None or _valid_typed_value(value.value))
        and (value.unit_code is None or _safe_code(value.unit_code, unit=True))
        and type(value.fact_ids) is tuple
        and len(value.fact_ids) <= 2
        and all(_valid_entity(item, FactId) for item in value.fact_ids)
        and len(set(value.fact_ids)) == len(value.fact_ids)
        and (value.reason_code is None or _safe_code(value.reason_code))
        and type(value.imputed) is bool
    )


def _cell_material(value: ComparisonCell) -> dict[str, object]:
    if not _cell_shape(value):
        _invalid()
    return {
        "axis_id": str(value.axis_id.value),
        "fact_ids": [str(item.value) for item in value.fact_ids],
        "imputed": value.imputed,
        "product_id": str(value.product_id.value),
        "reason_code": value.reason_code,
        "status": value.status.value,
        "unit_code": value.unit_code,
        "value": None if value.value is None else _typed_value_material(value.value),
    }


@dataclass(frozen=True, slots=True, repr=False)
class ComparisonSnapshotV2(_Redacted):
    contract: ComparisonContractBinding
    article: ArticleComparisonBinding
    evaluated_at: AwareUtcDateTime
    candidate_universe: CandidateUniverse
    axis_catalog: ComparisonAxisCatalog
    facts: tuple[ComparisonFactBinding, ...]
    cells: tuple[ComparisonCell, ...]
    show_unknown_values: bool
    fact_set_sha256: Sha256Digest
    temporal_scope_sha256: Sha256Digest
    evaluation_input_sha256: Sha256Digest


@dataclass(frozen=True, slots=True, repr=False)
class ComparisonValidationEnvelopeV2(_Redacted):
    comparison: ComparisonSnapshotV2
    claim_evidence: ClaimEvidenceSnapshot


@dataclass(frozen=True, slots=True, repr=False)
class ComparisonRecordReceipt(_Redacted):
    sequence: int
    report_sha256: Sha256Digest
    publication_authorized: bool = False

    def require_valid(self) -> None:
        if (
            type(self.sequence) is not int
            or not 1 <= self.sequence <= _MAX_EXACT_INT
            or not _valid_digest(self.report_sha256)
            or self.publication_authorized is not False
        ):
            _invalid()


@dataclass(frozen=True, slots=True, repr=False)
class ComparisonValidationReportV2(_Redacted):
    article_id: ArticleId | None
    article_version_id: ArticleVersionId | None
    article_version_no: int | None
    article_body_sha256: Sha256Digest | None
    article_binding_sha256: Sha256Digest | None
    source_packet_version_id: SourcePacketVersionId | None
    source_packet_content_sha256: Sha256Digest | None
    complete_claim_set_sha256: Sha256Digest | None
    candidate_universe_sha256: Sha256Digest | None
    axis_catalog_sha256: Sha256Digest | None
    fact_set_sha256: Sha256Digest | None
    temporal_scope_sha256: Sha256Digest | None
    evaluation_input_sha256: Sha256Digest | None
    evaluated_at: AwareUtcDateTime | None
    st0605_comparison_requirement_set_sha256: Sha256Digest | None
    status: ComparisonValidationStatus
    findings: tuple[ComparisonFindingCode, ...]
    comparison_attestations: tuple[EvidenceValidationAttestation, ...]
    publication_authorized: bool
    recommendation_authorized: bool
    ranking_authorized: bool
    production_eligible: bool
    formal_tst_007_status: ExecutionStatus
    formal_tst_020_status: ExecutionStatus
    live_validation_status: ExecutionStatus
    staging_status: ExecutionStatus
    release_status: ExecutionStatus
    production_status: ExecutionStatus
    report_sha256: Sha256Digest

    @property
    def locally_validated(self) -> bool:
        return self.status is ComparisonValidationStatus.LOCAL_VALIDATED

    def canonical_bytes(self) -> bytes:
        return _report_bytes(self, include_digest=True)

    def require_valid(self) -> None:
        if self.article_id is not None and not _valid_entity(
            self.article_id, ArticleId
        ):
            _invalid()
        if self.article_version_id is not None and not _valid_entity(
            self.article_version_id, ArticleVersionId
        ):
            _invalid()
        if self.article_version_no is not None and (
            type(self.article_version_no) is not int
            or not 1 <= self.article_version_no <= _MAX_EXACT_INT
        ):
            _invalid()
        if self.source_packet_version_id is not None and not _valid_entity(
            self.source_packet_version_id, SourcePacketVersionId
        ):
            _invalid()
        for digest in (
            self.article_body_sha256,
            self.article_binding_sha256,
            self.source_packet_content_sha256,
            self.complete_claim_set_sha256,
            self.candidate_universe_sha256,
            self.axis_catalog_sha256,
            self.fact_set_sha256,
            self.temporal_scope_sha256,
            self.evaluation_input_sha256,
            self.st0605_comparison_requirement_set_sha256,
        ):
            if digest is not None and not _valid_digest(digest):
                _invalid()
        if self.evaluated_at is not None and not _valid_instant(self.evaluated_at):
            _invalid()
        if (
            type(self.status) is not ComparisonValidationStatus
            or type(self.findings) is not tuple
            or any(type(item) is not ComparisonFindingCode for item in self.findings)
            or self.findings
            != tuple(code for code in ComparisonFindingCode if code in self.findings)
            or len(set(self.findings)) != len(self.findings)
            or type(self.comparison_attestations) is not tuple
            or any(
                type(item) is not EvidenceValidationAttestation
                for item in self.comparison_attestations
            )
            or any(
                value is not False
                for value in (
                    self.publication_authorized,
                    self.recommendation_authorized,
                    self.ranking_authorized,
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
        if self.status is not expected_status:
            _invalid()
        if self.status is ComparisonValidationStatus.LOCAL_VALIDATED:
            if (
                self.article_id is None
                or self.article_version_id is None
                or self.article_version_no is None
                or self.article_body_sha256 is None
                or self.article_binding_sha256 is None
                or self.source_packet_version_id is None
                or self.source_packet_content_sha256 is None
                or self.complete_claim_set_sha256 is None
                or self.candidate_universe_sha256 is None
                or self.axis_catalog_sha256 is None
                or self.fact_set_sha256 is None
                or self.temporal_scope_sha256 is None
                or self.evaluation_input_sha256 is None
                or self.evaluated_at is None
                or self.st0605_comparison_requirement_set_sha256 is None
                or not self.comparison_attestations
            ):
                _invalid()
            for receipt in self.comparison_attestations:
                if (
                    not _valid_emitted_receipt(receipt)
                    or receipt.validated_at != self.evaluated_at
                ):
                    _invalid()
            ordered = tuple(
                sorted(
                    self.comparison_attestations,
                    key=lambda item: (
                        item.subject_sha256.value,
                        item.input_sha256.value,
                    ),
                )
            )
            if ordered != self.comparison_attestations:
                _invalid()
            requirements = tuple(
                (item.kind, item.subject_sha256, item.input_sha256)
                for item in self.comparison_attestations
            )
            if (
                _comparison_requirement_set_sha256(requirements)
                != self.st0605_comparison_requirement_set_sha256
            ):
                _invalid()
        elif self.comparison_attestations:
            _invalid()
        expected_digest = hashlib.sha256(
            _report_bytes(self, include_digest=False)
        ).hexdigest()
        if self.report_sha256.value != expected_digest:
            _invalid()


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


def article_binding_sha256(value: ArticleComparisonBinding) -> Sha256Digest:
    return _digest(
        {
            "binding": _article_material(value),
            "profile": "ST0803_ARTICLE_BINDING_V2",
        }
    )


def candidate_universe_sha256(value: CandidateUniverse) -> Sha256Digest:
    return _digest(
        {
            "candidate_universe": _candidate_material(value),
            "profile": "ST0803_CANDIDATE_UNIVERSE_V2",
        }
    )


def axis_catalog_sha256(value: ComparisonAxisCatalog) -> Sha256Digest:
    return _digest(
        {
            "axis_catalog": _axis_catalog_material(value),
            "profile": "ST0803_AXIS_CATALOG_V2",
        }
    )


def fact_set_sha256(value: tuple[ComparisonFactBinding, ...]) -> Sha256Digest:
    if (
        type(value) is not tuple
        or len(value) > _MAX_FACTS
        or any(not _fact_shape(item) for item in value)
    ):
        _invalid()
    return _digest(
        {
            "facts": [_fact_material(item) for item in value],
            "profile": "ST0803_FACT_SET_V2",
        }
    )


def temporal_scope_sha256(
    *,
    evaluated_at: AwareUtcDateTime,
    facts: tuple[ComparisonFactBinding, ...],
) -> Sha256Digest:
    if (
        not _valid_instant(evaluated_at)
        or type(facts) is not tuple
        or len(facts) > _MAX_FACTS
    ):
        _invalid()
    if any(not _fact_shape(item) for item in facts):
        _invalid()
    return _digest(
        {
            "evaluated_at": _instant_text(evaluated_at),
            "fact_windows": [
                {
                    "fact_id": str(item.fact_id.value),
                    "observed_at": _instant_text(item.observed_at),
                    "valid_from": _instant_text(item.valid_from),
                    "valid_until": _instant_text(item.valid_until),
                }
                for item in facts
            ],
            "profile": "ST0803_TEMPORAL_SCOPE_V2",
        }
    )


def comparison_input_sha256(value: ComparisonSnapshotV2) -> Sha256Digest:
    if type(value) is not ComparisonSnapshotV2:
        _invalid()
    if (
        type(value.cells) is not tuple
        or len(value.cells) > _MAX_CELLS
        or any(not _cell_shape(item) for item in value.cells)
    ):
        _invalid()
    return _digest(
        {
            "article_binding_sha256": value.article.binding_sha256.value,
            "axis_catalog_sha256": value.axis_catalog.axis_catalog_sha256.value,
            "candidate_universe_sha256": (
                value.candidate_universe.candidate_universe_sha256.value
            ),
            "cells": [_cell_material(item) for item in value.cells],
            "contract": {
                "claim_evidence_contract_sha256": (
                    value.contract.claim_evidence_contract_sha256.value
                ),
                "contract_id": value.contract.contract_id,
                "contract_version": value.contract.contract_version,
                "evaluator_version": value.contract.evaluator_version,
                "identity_contract_sha256": value.contract.identity_contract_sha256.value,
            },
            "evaluated_at": _instant_text(value.evaluated_at),
            "fact_set_sha256": value.fact_set_sha256.value,
            "profile": "ST0803_COMPARISON_INPUT_V2",
            "show_unknown_values": value.show_unknown_values,
            "temporal_scope_sha256": value.temporal_scope_sha256.value,
        }
    )


def _attestation_material(value: EvidenceValidationAttestation) -> dict[str, object]:
    return {
        "contract_sha256": value.contract_sha256.value,
        "contract_version": value.contract_version,
        "decision_sha256": value.decision_sha256.value,
        "input_sha256": value.input_sha256.value,
        "kind": value.kind.value,
        "origin": value.origin.value,
        "owner_story_id": value.owner_story_id,
        "subject_sha256": value.subject_sha256.value,
        "valid": value.valid,
        "validated_at": _instant_text(value.validated_at),
    }


def _report_material(
    value: ComparisonValidationReportV2,
    *,
    include_digest: bool,
) -> dict[str, object]:
    material: dict[str, object] = {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "evaluator_version": EVALUATOR_VERSION,
        "article_binding_sha256": (
            None
            if value.article_binding_sha256 is None
            else value.article_binding_sha256.value
        ),
        "article_body_sha256": (
            None
            if value.article_body_sha256 is None
            else value.article_body_sha256.value
        ),
        "article_id": (
            None if value.article_id is None else str(value.article_id.value)
        ),
        "article_version_id": (
            None
            if value.article_version_id is None
            else str(value.article_version_id.value)
        ),
        "article_version_no": value.article_version_no,
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
        "comparison_attestations": [
            _attestation_material(item) for item in value.comparison_attestations
        ],
        "complete_claim_set_sha256": (
            None
            if value.complete_claim_set_sha256 is None
            else value.complete_claim_set_sha256.value
        ),
        "evaluation_input_sha256": (
            None
            if value.evaluation_input_sha256 is None
            else value.evaluation_input_sha256.value
        ),
        "evaluated_at": (
            None if value.evaluated_at is None else _instant_text(value.evaluated_at)
        ),
        "fact_set_sha256": (
            None if value.fact_set_sha256 is None else value.fact_set_sha256.value
        ),
        "findings": [item.value for item in value.findings],
        "formal_tst_007_status": value.formal_tst_007_status.value,
        "formal_tst_020_status": value.formal_tst_020_status.value,
        "live_validation_status": value.live_validation_status.value,
        "production_eligible": value.production_eligible,
        "production_status": value.production_status.value,
        "publication_authorized": value.publication_authorized,
        "ranking_authorized": value.ranking_authorized,
        "recommendation_authorized": value.recommendation_authorized,
        "release_status": value.release_status.value,
        "source_packet_content_sha256": (
            None
            if value.source_packet_content_sha256 is None
            else value.source_packet_content_sha256.value
        ),
        "source_packet_version_id": (
            None
            if value.source_packet_version_id is None
            else str(value.source_packet_version_id.value)
        ),
        "st0605_comparison_requirement_set_sha256": (
            None
            if value.st0605_comparison_requirement_set_sha256 is None
            else value.st0605_comparison_requirement_set_sha256.value
        ),
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


def _report_bytes(
    value: ComparisonValidationReportV2,
    *,
    include_digest: bool,
) -> bytes:
    return _canonical_bytes(_report_material(value, include_digest=include_digest))


def _status_for_findings(
    findings: set[ComparisonFindingCode],
) -> ComparisonValidationStatus:
    if findings & _STRUCTURAL_FINDINGS:
        return ComparisonValidationStatus.UNEVALUABLE
    if findings:
        return ComparisonValidationStatus.BLOCK
    return ComparisonValidationStatus.LOCAL_VALIDATED


def _valid_emitted_receipt(value: EvidenceValidationAttestation) -> bool:
    if (
        type(value) is not EvidenceValidationAttestation
        or value.kind is not ValidationAttestationKind.COMPARISON
        or value.origin is not ValidationAttestationOrigin.RECORDED_SYNTHETIC_ONLY
        or not _valid_digest(value.subject_sha256)
        or not _valid_digest(value.input_sha256)
        or not _valid_digest(value.decision_sha256)
        or not _valid_instant(value.validated_at)
        or value.valid is not True
    ):
        return False
    try:
        owner, version, contract_sha256 = validation_attestation_owner_binding(
            ValidationAttestationKind.COMPARISON
        )
        expected = recorded_synthetic_attestation_decision_sha256(
            ValidationAttestationKind.COMPARISON,
            value.subject_sha256,
            value.input_sha256,
        )
    except Exception:
        return False
    return (
        value.owner_story_id == owner
        and value.contract_version == version
        and value.contract_sha256 == contract_sha256
        and value.decision_sha256 == expected
    )


def _make_report(
    *,
    snapshot: ComparisonSnapshotV2 | None,
    requested_article_version_id: ArticleVersionId | None,
    findings: set[ComparisonFindingCode],
    requirement_set_sha256: Sha256Digest | None,
    attestations: tuple[EvidenceValidationAttestation, ...],
) -> ComparisonValidationReportV2:
    ordered = tuple(code for code in ComparisonFindingCode if code in findings)
    status = _status_for_findings(set(ordered))
    safe_snapshot = snapshot if type(snapshot) is ComparisonSnapshotV2 else None
    article = (
        safe_snapshot.article
        if safe_snapshot is not None and _article_shape(safe_snapshot.article)
        else None
    )
    report = ComparisonValidationReportV2(
        article_id=(article.article_id if article is not None else None),
        article_version_id=(
            article.article_version_id
            if article is not None
            else requested_article_version_id
        ),
        article_version_no=(
            article.article_version_no if article is not None else None
        ),
        article_body_sha256=(
            article.article_body_sha256 if article is not None else None
        ),
        article_binding_sha256=(
            article.binding_sha256 if article is not None else None
        ),
        source_packet_version_id=(
            article.source_packet_version_id if article is not None else None
        ),
        source_packet_content_sha256=(
            article.source_packet_content_sha256 if article is not None else None
        ),
        complete_claim_set_sha256=(
            article.complete_claim_set_sha256 if article is not None else None
        ),
        candidate_universe_sha256=(
            safe_snapshot.candidate_universe.candidate_universe_sha256
            if safe_snapshot is not None
            and type(safe_snapshot.candidate_universe) is CandidateUniverse
            and _valid_digest(
                safe_snapshot.candidate_universe.candidate_universe_sha256
            )
            else None
        ),
        axis_catalog_sha256=(
            safe_snapshot.axis_catalog.axis_catalog_sha256
            if safe_snapshot is not None
            and type(safe_snapshot.axis_catalog) is ComparisonAxisCatalog
            and _valid_digest(safe_snapshot.axis_catalog.axis_catalog_sha256)
            else None
        ),
        fact_set_sha256=(
            safe_snapshot.fact_set_sha256
            if safe_snapshot is not None
            and _valid_digest(safe_snapshot.fact_set_sha256)
            else None
        ),
        temporal_scope_sha256=(
            safe_snapshot.temporal_scope_sha256
            if safe_snapshot is not None
            and _valid_digest(safe_snapshot.temporal_scope_sha256)
            else None
        ),
        evaluation_input_sha256=(
            safe_snapshot.evaluation_input_sha256
            if safe_snapshot is not None
            and _valid_digest(safe_snapshot.evaluation_input_sha256)
            else None
        ),
        evaluated_at=(
            safe_snapshot.evaluated_at
            if safe_snapshot is not None and _valid_instant(safe_snapshot.evaluated_at)
            else None
        ),
        st0605_comparison_requirement_set_sha256=requirement_set_sha256,
        status=status,
        findings=ordered,
        comparison_attestations=(
            tuple(
                sorted(
                    attestations,
                    key=lambda item: (
                        item.subject_sha256.value,
                        item.input_sha256.value,
                    ),
                )
            )
            if status is ComparisonValidationStatus.LOCAL_VALIDATED
            else ()
        ),
        publication_authorized=False,
        recommendation_authorized=False,
        ranking_authorized=False,
        production_eligible=False,
        formal_tst_007_status=ExecutionStatus.NOT_EXECUTED,
        formal_tst_020_status=ExecutionStatus.NOT_EXECUTED,
        live_validation_status=ExecutionStatus.NOT_EXECUTED,
        staging_status=ExecutionStatus.NOT_EXECUTED,
        release_status=ExecutionStatus.NOT_EXECUTED,
        production_status=ExecutionStatus.NOT_EXECUTED,
        report_sha256=Sha256Digest("0" * 64),
    )
    digest = Sha256Digest(
        hashlib.sha256(_report_bytes(report, include_digest=False)).hexdigest()
    )
    result = ComparisonValidationReportV2(
        article_id=report.article_id,
        article_version_id=report.article_version_id,
        article_version_no=report.article_version_no,
        article_body_sha256=report.article_body_sha256,
        article_binding_sha256=report.article_binding_sha256,
        source_packet_version_id=report.source_packet_version_id,
        source_packet_content_sha256=report.source_packet_content_sha256,
        complete_claim_set_sha256=report.complete_claim_set_sha256,
        candidate_universe_sha256=report.candidate_universe_sha256,
        axis_catalog_sha256=report.axis_catalog_sha256,
        fact_set_sha256=report.fact_set_sha256,
        temporal_scope_sha256=report.temporal_scope_sha256,
        evaluation_input_sha256=report.evaluation_input_sha256,
        evaluated_at=report.evaluated_at,
        st0605_comparison_requirement_set_sha256=(
            report.st0605_comparison_requirement_set_sha256
        ),
        status=report.status,
        findings=report.findings,
        comparison_attestations=report.comparison_attestations,
        publication_authorized=False,
        recommendation_authorized=False,
        ranking_authorized=False,
        production_eligible=False,
        formal_tst_007_status=ExecutionStatus.NOT_EXECUTED,
        formal_tst_020_status=ExecutionStatus.NOT_EXECUTED,
        live_validation_status=ExecutionStatus.NOT_EXECUTED,
        staging_status=ExecutionStatus.NOT_EXECUTED,
        release_status=ExecutionStatus.NOT_EXECUTED,
        production_status=ExecutionStatus.NOT_EXECUTED,
        report_sha256=digest,
    )
    result.require_valid()
    return result


def unavailable_comparison_report(
    requested_article_version_id: ArticleVersionId | None,
) -> ComparisonValidationReportV2:
    if requested_article_version_id is not None and not _valid_entity(
        requested_article_version_id, ArticleVersionId
    ):
        requested_article_version_id = None
    return _make_report(
        snapshot=None,
        requested_article_version_id=requested_article_version_id,
        findings={ComparisonFindingCode.INPUT_UNAVAILABLE},
        requirement_set_sha256=None,
        attestations=(),
    )


def _snapshot_collections_bounded(value: ClaimEvidenceSnapshot) -> bool:
    try:
        collections_and_limits = (
            (value.claims, _MAX_CLAIMS),
            (value.requirement_proofs, _MAX_CLAIMS),
            (value.facts, _MAX_FACTS),
            (value.links, _MAX_LINKS),
            (value.sources, _MAX_FACTS),
            (value.snapshots, _MAX_FACTS),
            (value.identities, _MAX_FACTS),
            (value.conflicts, _MAX_FACTS),
            (value.citations, _MAX_LINKS),
            (value.attestations, 2_000),
        )
        contract_strings = (
            value.contract.policy_document_id,
            value.contract.policy_version,
            value.contract.evaluator_version,
            value.contract.claim_set_profile,
        )
        if not all(
            type(items) is tuple and len(items) <= maximum
            for items, maximum in collections_and_limits
        ):
            return False
        attestation_strings = tuple(
            text
            for item in value.attestations
            if type(item) is EvidenceValidationAttestation
            for text in (item.owner_story_id, item.contract_version)
        )
        return all(_safe_text(item, maximum=160) for item in contract_strings) and all(
            _safe_text(item, maximum=160) for item in attestation_strings
        )
    except Exception:
        return False


def _validate_comparison_shape(
    snapshot: ComparisonSnapshotV2,
    findings: set[ComparisonFindingCode],
) -> tuple[
    dict[UUID, ComparisonProduct],
    dict[UUID, ComparisonAxisDefinition],
    dict[UUID, ComparisonFactBinding],
]:
    if not _contract_valid(snapshot.contract):
        findings.add(ComparisonFindingCode.CONTRACT_BINDING_INVALID)
    if not _article_shape(snapshot.article):
        findings.add(ComparisonFindingCode.ARTICLE_BINDING_INVALID)
    else:
        try:
            if snapshot.article.binding_sha256 != article_binding_sha256(
                snapshot.article
            ):
                findings.add(ComparisonFindingCode.ARTICLE_BINDING_HASH_MISMATCH)
        except Exception:
            findings.add(ComparisonFindingCode.ARTICLE_BINDING_INVALID)
    if not _valid_instant(snapshot.evaluated_at):
        findings.add(ComparisonFindingCode.ARTICLE_BINDING_INVALID)
    show_unknown_values: object = snapshot.show_unknown_values
    if type(show_unknown_values) is not bool:
        findings.add(ComparisonFindingCode.RECORD_TYPE_INVALID)
    elif not show_unknown_values:
        findings.add(ComparisonFindingCode.UNKNOWN_VISIBILITY_REQUIRED)

    product_by_id: dict[UUID, ComparisonProduct] = {}
    universe = snapshot.candidate_universe
    if type(universe) is not CandidateUniverse:
        findings.add(ComparisonFindingCode.CANDIDATE_UNIVERSE_INVALID)
    elif (
        not _valid_entity(universe.universe_id, CandidateUniverseId)
        or type(universe.version_no) is not int
        or not 1 <= universe.version_no <= _MAX_EXACT_INT
        or type(universe.products) is not tuple
    ):
        findings.add(ComparisonFindingCode.CANDIDATE_UNIVERSE_INVALID)
    elif not 2 <= len(universe.products) <= _MAX_PRODUCTS:
        findings.add(ComparisonFindingCode.COLLECTION_BOUND_INVALID)
    else:
        previous: int | None = None
        for product in universe.products:
            if not _product_shape(product):
                findings.add(ComparisonFindingCode.RECORD_TYPE_INVALID)
                continue
            key = product.product_id.value
            if key in product_by_id:
                findings.add(ComparisonFindingCode.DUPLICATE_PRODUCT)
            product_by_id[key] = product
            if previous is not None and key.int <= previous:
                findings.add(ComparisonFindingCode.CANDIDATE_UNIVERSE_INVALID)
            previous = key.int
        try:
            if universe.candidate_universe_sha256 != candidate_universe_sha256(
                universe
            ):
                findings.add(ComparisonFindingCode.CANDIDATE_UNIVERSE_HASH_MISMATCH)
        except Exception:
            findings.add(ComparisonFindingCode.CANDIDATE_UNIVERSE_INVALID)

    axis_by_id: dict[UUID, ComparisonAxisDefinition] = {}
    catalog = snapshot.axis_catalog
    if type(catalog) is not ComparisonAxisCatalog:
        findings.add(ComparisonFindingCode.AXIS_CATALOG_INVALID)
    elif (
        not _valid_entity(catalog.catalog_id, AxisCatalogId)
        or type(catalog.version_no) is not int
        or not 1 <= catalog.version_no <= _MAX_EXACT_INT
        or not _valid_digest(catalog.source_sha256)
        or type(catalog.axes) is not tuple
    ):
        findings.add(ComparisonFindingCode.AXIS_CATALOG_INVALID)
    elif not 1 <= len(catalog.axes) <= _MAX_AXES:
        findings.add(ComparisonFindingCode.COLLECTION_BOUND_INVALID)
    else:
        positions: set[int] = set()
        for index, axis in enumerate(catalog.axes):
            if not _axis_shape(axis):
                findings.add(ComparisonFindingCode.RECORD_TYPE_INVALID)
                continue
            key = axis.axis_id.value
            if key in axis_by_id:
                findings.add(ComparisonFindingCode.DUPLICATE_AXIS)
            axis_by_id[key] = axis
            if axis.position in positions:
                findings.add(ComparisonFindingCode.DUPLICATE_POSITION)
            positions.add(axis.position)
            if axis.position != index:
                findings.add(ComparisonFindingCode.AXIS_CATALOG_INVALID)
            if _axis_is_prohibited(axis.axis_code, axis.label):
                findings.add(ComparisonFindingCode.PROHIBITED_AXIS)
        try:
            if catalog.axis_catalog_sha256 != axis_catalog_sha256(catalog):
                findings.add(ComparisonFindingCode.AXIS_CATALOG_HASH_MISMATCH)
        except Exception:
            findings.add(ComparisonFindingCode.AXIS_CATALOG_INVALID)

    fact_by_id: dict[UUID, ComparisonFactBinding] = {}
    if type(snapshot.facts) is not tuple:
        findings.add(ComparisonFindingCode.COLLECTION_TYPE_INVALID)
    elif len(snapshot.facts) > _MAX_FACTS:
        findings.add(ComparisonFindingCode.COLLECTION_BOUND_INVALID)
    else:
        previous = None
        for fact in snapshot.facts:
            if not _fact_shape(fact):
                findings.add(ComparisonFindingCode.RECORD_TYPE_INVALID)
                continue
            key = fact.fact_id.value
            if key in fact_by_id:
                findings.add(ComparisonFindingCode.DUPLICATE_FACT)
            fact_by_id[key] = fact
            if previous is not None and key.int <= previous:
                findings.add(ComparisonFindingCode.FACT_SET_INVALID)
            previous = key.int
        try:
            if snapshot.fact_set_sha256 != fact_set_sha256(snapshot.facts):
                findings.add(ComparisonFindingCode.FACT_SET_HASH_MISMATCH)
            if snapshot.temporal_scope_sha256 != temporal_scope_sha256(
                evaluated_at=snapshot.evaluated_at,
                facts=snapshot.facts,
            ):
                findings.add(ComparisonFindingCode.TEMPORAL_SCOPE_HASH_MISMATCH)
        except Exception:
            findings.add(ComparisonFindingCode.FACT_SET_INVALID)

    if type(snapshot.cells) is not tuple:
        findings.add(ComparisonFindingCode.COLLECTION_TYPE_INVALID)
    elif len(snapshot.cells) > _MAX_CELLS:
        findings.add(ComparisonFindingCode.COLLECTION_BOUND_INVALID)
    elif any(not _cell_shape(item) for item in snapshot.cells):
        findings.add(ComparisonFindingCode.RECORD_TYPE_INVALID)
    try:
        if snapshot.evaluation_input_sha256 != comparison_input_sha256(snapshot):
            findings.add(ComparisonFindingCode.EVALUATION_INPUT_HASH_MISMATCH)
    except Exception:
        findings.add(ComparisonFindingCode.EVALUATION_INPUT_HASH_MISMATCH)
    return product_by_id, axis_by_id, fact_by_id


def _validate_cells(
    snapshot: ComparisonSnapshotV2,
    product_by_id: dict[UUID, ComparisonProduct],
    axis_by_id: dict[UUID, ComparisonAxisDefinition],
    fact_by_id: dict[UUID, ComparisonFactBinding],
    findings: set[ComparisonFindingCode],
) -> set[UUID]:
    if type(snapshot.cells) is not tuple or len(snapshot.cells) > _MAX_CELLS:
        return set()
    seen: set[tuple[UUID, UUID]] = set()
    used_facts: set[UUID] = set()
    for cell in snapshot.cells:
        if not _cell_shape(cell):
            continue
        product = product_by_id.get(cell.product_id.value)
        axis = axis_by_id.get(cell.axis_id.value)
        if product is None or axis is None:
            findings.add(ComparisonFindingCode.REFERENCE_INVALID)
            continue
        coordinate = (cell.product_id.value, cell.axis_id.value)
        if coordinate in seen:
            findings.add(ComparisonFindingCode.DUPLICATE_CELL)
        seen.add(coordinate)
        if cell.imputed:
            findings.add(ComparisonFindingCode.UNKNOWN_VALUE_IMPUTATION_FORBIDDEN)

        if cell.status is ComparisonCellStatus.VALID:
            if (
                cell.value is None
                or not _valid_typed_value(cell.value)
                or len(cell.fact_ids) != 1
                or cell.reason_code is not None
            ):
                findings.add(ComparisonFindingCode.VALUE_BINDING_MISMATCH)
                continue
            fact = fact_by_id.get(cell.fact_ids[0].value)
            if fact is None:
                findings.add(ComparisonFindingCode.REFERENCE_INVALID)
                continue
            used_facts.add(fact.fact_id.value)
            if fact.product_id != product.product_id or fact.axis_id != axis.axis_id:
                findings.add(ComparisonFindingCode.VALUE_BINDING_MISMATCH)
            if fact.variant_identity_sha256 != product.variant_identity_sha256:
                findings.add(ComparisonFindingCode.VARIANT_MISMATCH)
            if fact.subject_identity_sha256 != product.subject_identity_sha256:
                findings.add(ComparisonFindingCode.IDENTITY_SUBJECT_MISMATCH)
            if (
                fact.value.data_type is not axis.data_type
                or cell.value.data_type is not axis.data_type
            ):
                findings.add(ComparisonFindingCode.VALUE_TYPE_MISMATCH)
            elif _typed_value_material(fact.value) != _typed_value_material(cell.value):
                findings.add(ComparisonFindingCode.VALUE_BINDING_MISMATCH)
            if fact.unit_code != axis.unit_code or cell.unit_code != axis.unit_code:
                findings.add(ComparisonFindingCode.UNIT_BINDING_MISMATCH)
            if not (
                fact.valid_from.value
                <= fact.observed_at.value
                <= snapshot.evaluated_at.value
            ):
                findings.add(ComparisonFindingCode.FACT_FROM_FUTURE)
            if snapshot.evaluated_at.value > fact.valid_until.value:
                findings.add(ComparisonFindingCode.STALE_FACT)
        elif cell.status is ComparisonCellStatus.UNKNOWN:
            if (
                cell.value is not None
                or cell.unit_code is not None
                or cell.fact_ids
                or cell.reason_code is None
            ):
                findings.add(ComparisonFindingCode.UNKNOWN_VALUE_IMPUTATION_FORBIDDEN)
        elif cell.status is ComparisonCellStatus.MISSING:
            if (
                cell.value is not None
                or cell.unit_code is not None
                or cell.fact_ids
                or cell.reason_code is None
            ):
                findings.add(ComparisonFindingCode.VALUE_BINDING_MISMATCH)
            if axis.required:
                findings.add(ComparisonFindingCode.REQUIRED_VALUE_MISSING)
        elif cell.status is ComparisonCellStatus.CONFLICT:
            if (
                cell.value is not None
                or cell.unit_code is not None
                or len(cell.fact_ids) != 2
                or cell.reason_code is None
            ):
                findings.add(ComparisonFindingCode.VALUE_BINDING_MISMATCH)
            for fact_id in cell.fact_ids:
                if fact_id.value not in fact_by_id:
                    findings.add(ComparisonFindingCode.REFERENCE_INVALID)
                else:
                    used_facts.add(fact_id.value)
            findings.add(ComparisonFindingCode.CONFLICTING_VALUE)
        else:
            if (
                cell.value is not None
                or cell.unit_code is not None
                or cell.fact_ids
                or cell.reason_code is None
            ):
                findings.add(ComparisonFindingCode.VALUE_BINDING_MISMATCH)
            findings.add(ComparisonFindingCode.UNSUPPORTED_VALUE)

    expected = {
        (product_id, axis_id) for product_id in product_by_id for axis_id in axis_by_id
    }
    if seen != expected:
        findings.add(ComparisonFindingCode.CELL_MATRIX_INCOMPLETE)
    if used_facts != set(fact_by_id):
        findings.add(ComparisonFindingCode.FACT_REFERENCE_SET_MISMATCH)
    return used_facts


def _comparison_requirement_set_sha256(
    requirements: tuple[
        tuple[ValidationAttestationKind, Sha256Digest, Sha256Digest], ...
    ],
) -> Sha256Digest:
    return _digest(
        {
            "profile": "ST0803_ST0605_COMPARISON_REQUIREMENTS_V2",
            "requirements": [
                {
                    "input_sha256": input_digest.value,
                    "kind": kind.value,
                    "subject_sha256": subject.value,
                }
                for kind, subject, input_digest in requirements
            ],
        }
    )


def _validate_claim_evidence_boundary(
    snapshot: ComparisonSnapshotV2,
    claim_snapshot: object,
    fact_by_id: dict[UUID, ComparisonFactBinding],
    findings: set[ComparisonFindingCode],
) -> tuple[
    tuple[tuple[ValidationAttestationKind, Sha256Digest, Sha256Digest], ...],
    Sha256Digest | None,
]:
    if type(
        claim_snapshot
    ) is not ClaimEvidenceSnapshot or not _snapshot_collections_bounded(claim_snapshot):
        findings.add(ComparisonFindingCode.ST0605_INPUT_INVALID)
        return (), None
    try:
        baseline = evaluate_claim_evidence(claim_snapshot)
        baseline.require_valid()
    except Exception:
        findings.add(ComparisonFindingCode.ST0605_INPUT_INVALID)
        return (), None
    allowed_missing = {
        CoverageFindingCode.REQUIRED_ATTESTATION_MISSING,
        CoverageFindingCode.ATTESTATION_SET_MISMATCH,
    }
    baseline_findings = set(baseline.findings)
    semantic_baseline_findings = baseline_findings - allowed_missing
    if baseline.status is ClaimCoverageStatus.BLOCK:
        findings.add(ComparisonFindingCode.ST0605_SEMANTIC_BLOCK)
    elif baseline.status is ClaimCoverageStatus.PASS:
        findings.add(ComparisonFindingCode.PREEXISTING_COMPARISON_RECEIPT)
    elif (
        semantic_baseline_findings
        and semantic_baseline_findings <= _TRUSTED_ST0605_SEMANTIC_FINDINGS
    ):
        findings.add(ComparisonFindingCode.ST0605_SEMANTIC_BLOCK)
    elif not baseline_findings or not baseline_findings <= allowed_missing:
        findings.add(ComparisonFindingCode.ST0605_BASELINE_UNTRUSTED)

    if any(
        type(item) is EvidenceValidationAttestation
        and item.kind is ValidationAttestationKind.COMPARISON
        for item in claim_snapshot.attestations
    ):
        findings.add(ComparisonFindingCode.PREEXISTING_COMPARISON_RECEIPT)

    try:
        requirements = required_validation_attestation_inputs(claim_snapshot)
    except Exception:
        findings.add(ComparisonFindingCode.ST0605_INPUT_INVALID)
        return (), None
    comparison_requirements = tuple(
        item for item in requirements if item[0] is ValidationAttestationKind.COMPARISON
    )
    if not comparison_requirements or len(comparison_requirements) > _MAX_CLAIMS:
        findings.add(ComparisonFindingCode.COMPARISON_REQUIREMENT_MISSING)
        return (), None
    requirement_digest = _comparison_requirement_set_sha256(comparison_requirements)

    article = claim_snapshot.article
    packet = claim_snapshot.approved_packet
    if (
        article.article_version_id != snapshot.article.article_version_id
        or article.article_body_sha256 != snapshot.article.article_body_sha256
        or article.source_packet_version_id != snapshot.article.source_packet_version_id
        or article.source_packet_content_sha256
        != snapshot.article.source_packet_content_sha256
        or article.complete_claim_set_sha256
        != snapshot.article.complete_claim_set_sha256
        or packet.source_packet_version_id != snapshot.article.source_packet_version_id
        or packet.content_sha256 != snapshot.article.source_packet_content_sha256
        or claim_snapshot.evaluated_at != snapshot.evaluated_at
    ):
        findings.add(ComparisonFindingCode.ARTICLE_BINDING_INVALID)

    snapshot_fact_by_id = {item.fact_id.value: item for item in claim_snapshot.facts}
    identity_by_fact = {item.fact_id.value: item for item in claim_snapshot.identities}
    sorted_snapshot_facts = tuple(
        sorted(claim_snapshot.facts, key=lambda item: item.fact_id.value.int)
    )
    identity_requirements = tuple(
        item
        for item in requirements
        if item[0] is ValidationAttestationKind.IDENTITY_DECISION
    )
    actual_attestations = {
        (item.kind, item.subject_sha256, item.input_sha256): item
        for item in claim_snapshot.attestations
        if type(item) is EvidenceValidationAttestation
    }
    if len(identity_requirements) != len(sorted_snapshot_facts):
        findings.add(ComparisonFindingCode.IDENTITY_RECEIPT_MISSING)
    else:
        for st_fact, requirement in zip(
            sorted_snapshot_facts, identity_requirements, strict=True
        ):
            actual = actual_attestations.get(requirement)
            identity = identity_by_fact.get(st_fact.fact_id.value)
            if (
                actual is None
                or actual.valid is not True
                or actual.validated_at.value > snapshot.evaluated_at.value
                or identity is None
                or identity.decided_at.value > snapshot.evaluated_at.value
            ):
                findings.add(ComparisonFindingCode.IDENTITY_RECEIPT_MISSING)
                continue
            if identity.status is not IdentityStatus.MATCHED:
                findings.add(ComparisonFindingCode.IDENTITY_UNRESOLVED)
            if (
                identity.expected_subject_identity_sha256
                != st_fact.subject_identity_sha256
                or identity.observed_subject_identity_sha256
                != st_fact.subject_identity_sha256
            ):
                findings.add(ComparisonFindingCode.IDENTITY_SUBJECT_MISMATCH)

    for fact_id, fact in fact_by_id.items():
        matching_claim_fact = snapshot_fact_by_id.get(fact_id)
        if matching_claim_fact is None:
            findings.add(ComparisonFindingCode.CLAIM_FACT_SET_MISMATCH)
            continue
        if (
            matching_claim_fact.fact_sha256 != fact.fact_sha256
            or matching_claim_fact.subject_identity_sha256
            != fact.subject_identity_sha256
        ):
            findings.add(ComparisonFindingCode.IDENTITY_SUBJECT_MISMATCH)
    if set(snapshot_fact_by_id) != set(fact_by_id):
        findings.add(ComparisonFindingCode.CLAIM_FACT_SET_MISMATCH)

    proof_by_claim = {
        item.claim_id.value: item for item in claim_snapshot.requirement_proofs
    }
    links_by_claim: dict[UUID, set[UUID]] = {}
    for link in claim_snapshot.links:
        if link.support_type is PolicyLinkSupportType.SUPPORTS:
            links_by_claim.setdefault(link.claim_id.value, set()).add(
                link.fact_id.value
            )
    comparison_claims = tuple(
        sorted(
            (
                item
                for item in claim_snapshot.claims
                if item.claim_type
                in {PolicyClaimType.COMPARATIVE, PolicyClaimType.SUPERLATIVE}
            ),
            key=lambda item: item.claim_id.value.int,
        )
    )
    if len(comparison_claims) != len(comparison_requirements):
        findings.add(ComparisonFindingCode.COMPARISON_REQUIREMENT_MISSING)
    supported_union: set[UUID] = set()
    for claim in comparison_claims:
        proof = proof_by_claim.get(claim.claim_id.value)
        if proof is None:
            findings.add(ComparisonFindingCode.COMPARISON_REQUIREMENT_MISSING)
            continue
        if (
            proof.comparison_population_sha256
            != snapshot.candidate_universe.candidate_universe_sha256
        ):
            findings.add(ComparisonFindingCode.CLAIM_POPULATION_MISMATCH)
        if proof.temporal_scope_sha256 != snapshot.temporal_scope_sha256:
            findings.add(ComparisonFindingCode.CLAIM_TEMPORAL_SCOPE_MISMATCH)
        linked = links_by_claim.get(claim.claim_id.value, set())
        supported_union.update(linked)
        if not linked or not linked <= set(fact_by_id):
            findings.add(ComparisonFindingCode.CLAIM_FACT_SET_MISMATCH)
    if supported_union != set(fact_by_id):
        findings.add(ComparisonFindingCode.CLAIM_FACT_SET_MISMATCH)
    return comparison_requirements, requirement_digest


def _emit_comparison_attestations(
    requirements: tuple[
        tuple[ValidationAttestationKind, Sha256Digest, Sha256Digest], ...
    ],
    *,
    validated_at: AwareUtcDateTime,
) -> tuple[EvidenceValidationAttestation, ...]:
    owner, version, contract_sha256 = validation_attestation_owner_binding(
        ValidationAttestationKind.COMPARISON
    )
    receipts = tuple(
        EvidenceValidationAttestation(
            kind=kind,
            owner_story_id=owner,
            contract_version=version,
            contract_sha256=contract_sha256,
            origin=ValidationAttestationOrigin.RECORDED_SYNTHETIC_ONLY,
            subject_sha256=subject,
            input_sha256=input_digest,
            decision_sha256=recorded_synthetic_attestation_decision_sha256(
                kind, subject, input_digest
            ),
            validated_at=validated_at,
            valid=True,
        )
        for kind, subject, input_digest in requirements
    )
    if any(not _valid_emitted_receipt(item) for item in receipts):
        _invalid()
    return receipts


def validate_comparison_v2(value: object) -> ComparisonValidationReportV2:
    """Validate one V2 envelope without mutation or external authority."""

    if type(value) is not ComparisonValidationEnvelopeV2:
        return _make_report(
            snapshot=None,
            requested_article_version_id=None,
            findings={ComparisonFindingCode.INPUT_TYPE_INVALID},
            requirement_set_sha256=None,
            attestations=(),
        )
    try:
        comparison_value = value.comparison
        claim_evidence_value = value.claim_evidence
    except Exception:
        return _make_report(
            snapshot=None,
            requested_article_version_id=None,
            findings={ComparisonFindingCode.INPUT_TYPE_INVALID},
            requirement_set_sha256=None,
            attestations=(),
        )
    if type(comparison_value) is not ComparisonSnapshotV2:
        return _make_report(
            snapshot=None,
            requested_article_version_id=None,
            findings={ComparisonFindingCode.INPUT_TYPE_INVALID},
            requirement_set_sha256=None,
            attestations=(),
        )
    snapshot = comparison_value
    try:
        findings: set[ComparisonFindingCode] = set()
        product_by_id, axis_by_id, fact_by_id = _validate_comparison_shape(
            snapshot, findings
        )
        _validate_cells(
            snapshot,
            product_by_id,
            axis_by_id,
            fact_by_id,
            findings,
        )
        requirements, requirement_digest = _validate_claim_evidence_boundary(
            snapshot,
            claim_evidence_value,
            fact_by_id,
            findings,
        )
        attestations: tuple[EvidenceValidationAttestation, ...] = ()
        if not findings:
            attestations = _emit_comparison_attestations(
                requirements,
                validated_at=snapshot.evaluated_at,
            )
        return _make_report(
            snapshot=snapshot,
            requested_article_version_id=(
                snapshot.article.article_version_id
                if _article_shape(snapshot.article)
                else None
            ),
            findings=findings,
            requirement_set_sha256=requirement_digest,
            attestations=attestations,
        )
    except Exception:
        return _make_report(
            snapshot=None,
            requested_article_version_id=None,
            findings={ComparisonFindingCode.RECORD_TYPE_INVALID},
            requirement_set_sha256=None,
            attestations=(),
        )


__all__ = [
    "ARTICLE_LIFECYCLE_SOURCE_SHA256",
    "AxisCatalogId",
    "CLAIM_EVIDENCE_CONTRACT_SHA256",
    "COMPARISON_SCHEMA_SHA256",
    "CONTRACT_ID",
    "CONTRACT_VERSION",
    "CandidateUniverse",
    "CandidateUniverseId",
    "ComparisonAxisCatalog",
    "ComparisonAxisDataType",
    "ComparisonAxisDefinition",
    "ComparisonCell",
    "ComparisonCellStatus",
    "ComparisonContractBinding",
    "ComparisonFactBinding",
    "ComparisonFindingCode",
    "ComparisonProduct",
    "ComparisonRecordReceipt",
    "ComparisonRuntimeValueError",
    "ComparisonSnapshotV2",
    "ComparisonValidationEnvelopeV2",
    "ComparisonValidationReportV2",
    "ComparisonValidationStatus",
    "EVALUATOR_VERSION",
    "ExecutionStatus",
    "IDENTITY_CONTRACT_SHA256",
    "TypedComparisonValue",
    "article_binding_sha256",
    "axis_catalog_sha256",
    "candidate_universe_sha256",
    "canonical_decimal",
    "comparison_input_sha256",
    "fact_set_sha256",
    "temporal_scope_sha256",
    "unavailable_comparison_report",
    "validate_comparison_v2",
]

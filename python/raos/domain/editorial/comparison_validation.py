"""Pure fail-closed validation for an already assembled TEST_ONLY comparison.

The validator makes no identity, conversion, ranking, coverage, publication,
or persistence decision. Caller-controlled values are redacted from string and
representation output, and findings contain closed codes without input data.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import re
from typing import NoReturn, TypeAlias


_TOKEN = re.compile(r"[A-Z][A-Z0-9_:-]{0,126}\Z", re.ASCII)
_FIELD = re.compile(r"[A-Z][A-Z0-9_]{0,126}\Z", re.ASCII)
_PROHIBITED_FIELD_PARTS = frozenset(
    {
        "AFFILIATE",
        "COMMISSION",
        "COST",
        "EPC",
        "FINANCE",
        "PROFIT",
        "RATE",
        "REVENUE",
        "RPM",
    }
)


class ComparisonMode(str, Enum):
    TEST_ONLY = "TEST_ONLY"


class ProductIdentityStatus(str, Enum):
    PRE_RESOLVED_TEST_ONLY = "PRE_RESOLVED_TEST_ONLY"
    UNRESOLVED = "UNRESOLVED"
    CONFLICTING = "CONFLICTING"


class ComparisonCellState(str, Enum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"


class ComparisonDecision(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"


class ExecutionStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


class CoverageStatus(str, Enum):
    UNEVALUABLE = "UNEVALUABLE"


class MappingStatus(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"


class ComparisonFindingCode(str, Enum):
    INPUT_TYPE_INVALID = "INPUT_TYPE_INVALID"
    MODE_INVALID = "MODE_INVALID"
    COLLECTION_TYPE_INVALID = "COLLECTION_TYPE_INVALID"
    PRODUCT_COUNT_INVALID = "PRODUCT_COUNT_INVALID"
    AXIS_COUNT_INVALID = "AXIS_COUNT_INVALID"
    RECORD_TYPE_INVALID = "RECORD_TYPE_INVALID"
    PRODUCT_ID_INVALID = "PRODUCT_ID_INVALID"
    DUPLICATE_PRODUCT = "DUPLICATE_PRODUCT"
    AXIS_ID_INVALID = "AXIS_ID_INVALID"
    DUPLICATE_AXIS = "DUPLICATE_AXIS"
    PROHIBITED_FIELD = "PROHIBITED_FIELD"
    SHOW_UNKNOWN_VALUES_REQUIRED = "SHOW_UNKNOWN_VALUES_REQUIRED"
    IDENTITY_UNRESOLVED = "IDENTITY_UNRESOLVED"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
    IDENTITY_BINDING_INVALID = "IDENTITY_BINDING_INVALID"
    VARIANT_BINDING_INVALID = "VARIANT_BINDING_INVALID"
    CELL_COORDINATE_INVALID = "CELL_COORDINATE_INVALID"
    DUPLICATE_CELL = "DUPLICATE_CELL"
    MISSING_CELL = "MISSING_CELL"
    CELL_STATE_INVALID = "CELL_STATE_INVALID"
    IMPUTATION_FORBIDDEN = "IMPUTATION_FORBIDDEN"
    VALUE_REQUIRED = "VALUE_REQUIRED"
    VALUE_TYPE_INVALID = "VALUE_TYPE_INVALID"
    VALUE_NONFINITE = "VALUE_NONFINITE"
    UNKNOWN_VALUE_PRESENT = "UNKNOWN_VALUE_PRESENT"
    UNIT_REQUIRED = "UNIT_REQUIRED"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    UNKNOWN_UNIT_PRESENT = "UNKNOWN_UNIT_PRESENT"
    EVIDENCE_REQUIRED = "EVIDENCE_REQUIRED"
    EVIDENCE_MISMATCH = "EVIDENCE_MISMATCH"


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted>)"

    def __str__(self) -> str:
        return "<redacted>"


class ComparisonValueConstructionError(ValueError):
    """Closed construction failure which never includes caller input."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("INVALID_EXACT_VALUE")


def _fail_value_construction() -> NoReturn:
    raise ComparisonValueConstructionError() from None


@dataclass(frozen=True, slots=True, repr=False)
class _ExactToken(_Redacted):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _TOKEN.fullmatch(self.value) is None:
            _fail_value_construction()


@dataclass(frozen=True, slots=True, repr=False)
class ProductId(_ExactToken):
    pass


@dataclass(frozen=True, slots=True, repr=False)
class AxisId(_ExactToken):
    pass


@dataclass(frozen=True, slots=True, repr=False)
class EvidenceId(_ExactToken):
    pass


@dataclass(frozen=True, slots=True, repr=False)
class IdentityId(_ExactToken):
    pass


@dataclass(frozen=True, slots=True, repr=False)
class VariantId(_ExactToken):
    pass


@dataclass(frozen=True, slots=True, repr=False)
class UnitCode(_ExactToken):
    pass


@dataclass(frozen=True, slots=True, repr=False)
class ComparisonFieldName(_Redacted):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _FIELD.fullmatch(self.value) is None:
            _fail_value_construction()


ComparisonScalarPrimitive: TypeAlias = str | int | float


def _is_exact_finite_float(value: object) -> bool:
    return isinstance(value, float) and type(value) is float and math.isfinite(value)


@dataclass(frozen=True, slots=True, repr=False)
class ComparisonScalar(_Redacted):
    value: ComparisonScalarPrimitive

    def __post_init__(self) -> None:
        primitive = self.value
        if isinstance(primitive, str):
            if (
                type(primitive) is not str
                or not primitive
                or len(primitive) > 1024
                or primitive != primitive.strip()
                or any(
                    ord(character) < 32 or ord(character) == 127
                    for character in primitive
                )
            ):
                _fail_value_construction()
            return
        if isinstance(primitive, int):
            if type(primitive) is int:
                return
            _fail_value_construction()
        if _is_exact_finite_float(primitive):
            return
        _fail_value_construction()


@dataclass(frozen=True, slots=True, repr=False)
class ComparisonProduct(_Redacted):
    product_id: ProductId
    identity_status: ProductIdentityStatus
    identity_id: IdentityId | None
    variant_id: VariantId | None


@dataclass(frozen=True, slots=True, repr=False)
class ComparisonAxis(_Redacted):
    axis_id: AxisId
    field_name: ComparisonFieldName
    unit: UnitCode


@dataclass(frozen=True, slots=True, repr=False)
class EvidenceBinding(_Redacted):
    evidence_id: EvidenceId
    product_id: ProductId
    axis_id: AxisId
    identity_id: IdentityId
    variant_id: VariantId


@dataclass(frozen=True, slots=True, repr=False)
class ComparisonCell(_Redacted):
    product_id: ProductId
    axis_id: AxisId
    state: ComparisonCellState
    value: ComparisonScalar | None
    unit: UnitCode | None
    evidence: EvidenceBinding | None
    identity_id: IdentityId | None
    variant_id: VariantId | None
    imputed: bool = False


@dataclass(frozen=True, slots=True, repr=False)
class ComparisonInput(_Redacted):
    mode: ComparisonMode
    products: tuple[ComparisonProduct, ...]
    axes: tuple[ComparisonAxis, ...]
    cells: tuple[ComparisonCell, ...]
    show_unknown_values: bool


@dataclass(frozen=True, slots=True, repr=False)
class ComparisonValidationReport(_Redacted):
    decision: ComparisonDecision
    findings: tuple[ComparisonFindingCode, ...]
    publication_authorized: bool
    production_eligible: bool
    identity_resolution_status: ExecutionStatus
    coverage_status: CoverageStatus
    coverage_mapping_status: MappingStatus
    coverage_calculation_status: ExecutionStatus
    formal_test_status: ExecutionStatus
    live_validation_status: ExecutionStatus

    @property
    def passed(self) -> bool:
        return self.decision is ComparisonDecision.PASS


def _report(findings: set[ComparisonFindingCode]) -> ComparisonValidationReport:
    ordered = tuple(code for code in ComparisonFindingCode if code in findings)
    return ComparisonValidationReport(
        decision=(ComparisonDecision.PASS if not ordered else ComparisonDecision.BLOCK),
        findings=ordered,
        publication_authorized=False,
        production_eligible=False,
        identity_resolution_status=ExecutionStatus.NOT_EXECUTED,
        coverage_status=CoverageStatus.UNEVALUABLE,
        coverage_mapping_status=MappingStatus.UNAVAILABLE,
        coverage_calculation_status=ExecutionStatus.NOT_EXECUTED,
        formal_test_status=ExecutionStatus.NOT_EXECUTED,
        live_validation_status=ExecutionStatus.NOT_EXECUTED,
    )


def _valid_token(value: object, expected_type: type[_ExactToken]) -> bool:
    return (
        type(value) is expected_type
        and type(value.value) is str
        and _TOKEN.fullmatch(value.value) is not None
    )


def _valid_field(value: object) -> bool:
    return (
        type(value) is ComparisonFieldName
        and type(value.value) is str
        and _FIELD.fullmatch(value.value) is not None
    )


def _scalar_finding(value: object) -> ComparisonFindingCode | None:
    if type(value) is not ComparisonScalar:
        return ComparisonFindingCode.VALUE_TYPE_INVALID
    primitive: object = value.value
    if isinstance(primitive, str):
        if (
            type(primitive) is not str
            or not primitive
            or len(primitive) > 1024
            or primitive != primitive.strip()
            or any(
                ord(character) < 32 or ord(character) == 127 for character in primitive
            )
        ):
            return ComparisonFindingCode.VALUE_TYPE_INVALID
        return None
    if isinstance(primitive, int):
        if type(primitive) is int:
            return None
        return ComparisonFindingCode.VALUE_TYPE_INVALID
    if _is_exact_finite_float(primitive):
        return None
    if type(primitive) is float:
        return ComparisonFindingCode.VALUE_NONFINITE
    return ComparisonFindingCode.VALUE_TYPE_INVALID


def validate_comparison(value: object) -> ComparisonValidationReport:
    """Validate without mutation, I/O, implicit resolution, conversion, or echo."""

    findings: set[ComparisonFindingCode] = set()
    if type(value) is not ComparisonInput:
        findings.add(ComparisonFindingCode.INPUT_TYPE_INVALID)
        return _report(findings)

    if (
        type(value.mode) is not ComparisonMode
        or value.mode is not ComparisonMode.TEST_ONLY
    ):
        findings.add(ComparisonFindingCode.MODE_INVALID)
    if type(value.show_unknown_values) is not bool or not value.show_unknown_values:
        findings.add(ComparisonFindingCode.SHOW_UNKNOWN_VALUES_REQUIRED)

    collection_values = (value.products, value.axes, value.cells)
    if any(type(collection) is not tuple for collection in collection_values):
        findings.add(ComparisonFindingCode.COLLECTION_TYPE_INVALID)
    products = value.products if type(value.products) is tuple else ()
    axes = value.axes if type(value.axes) is tuple else ()
    cells = value.cells if type(value.cells) is tuple else ()

    if not 2 <= len(products) <= 20:
        findings.add(ComparisonFindingCode.PRODUCT_COUNT_INVALID)
    if not 1 <= len(axes) <= 30:
        findings.add(ComparisonFindingCode.AXIS_COUNT_INVALID)

    product_by_value: dict[str, ComparisonProduct] = {}
    for product in products:
        if type(product) is not ComparisonProduct:
            findings.add(ComparisonFindingCode.RECORD_TYPE_INVALID)
            continue
        if not _valid_token(product.product_id, ProductId):
            findings.add(ComparisonFindingCode.PRODUCT_ID_INVALID)
            continue
        product_key = product.product_id.value
        if product_key in product_by_value:
            findings.add(ComparisonFindingCode.DUPLICATE_PRODUCT)
        else:
            product_by_value[product_key] = product
        if type(product.identity_status) is not ProductIdentityStatus:
            findings.add(ComparisonFindingCode.IDENTITY_UNRESOLVED)
        elif product.identity_status is ProductIdentityStatus.UNRESOLVED:
            findings.add(ComparisonFindingCode.IDENTITY_UNRESOLVED)
        elif product.identity_status is ProductIdentityStatus.CONFLICTING:
            findings.add(ComparisonFindingCode.IDENTITY_CONFLICT)
        if product.identity_status is ProductIdentityStatus.PRE_RESOLVED_TEST_ONLY:
            if not _valid_token(product.identity_id, IdentityId):
                findings.add(ComparisonFindingCode.IDENTITY_BINDING_INVALID)
            if not _valid_token(product.variant_id, VariantId):
                findings.add(ComparisonFindingCode.VARIANT_BINDING_INVALID)

    axis_by_value: dict[str, ComparisonAxis] = {}
    for axis in axes:
        if type(axis) is not ComparisonAxis:
            findings.add(ComparisonFindingCode.RECORD_TYPE_INVALID)
            continue
        if not _valid_token(axis.axis_id, AxisId):
            findings.add(ComparisonFindingCode.AXIS_ID_INVALID)
            continue
        axis_key = axis.axis_id.value
        if axis_key in axis_by_value:
            findings.add(ComparisonFindingCode.DUPLICATE_AXIS)
        else:
            axis_by_value[axis_key] = axis
        if not _valid_field(axis.field_name):
            findings.add(ComparisonFindingCode.PROHIBITED_FIELD)
        elif any(
            component in _PROHIBITED_FIELD_PARTS
            for component in axis.field_name.value.split("_")
        ):
            findings.add(ComparisonFindingCode.PROHIBITED_FIELD)
        if not _valid_token(axis.unit, UnitCode):
            findings.add(ComparisonFindingCode.UNIT_REQUIRED)

    seen_cells: set[tuple[str, str]] = set()
    for cell in cells:
        if type(cell) is not ComparisonCell:
            findings.add(ComparisonFindingCode.RECORD_TYPE_INVALID)
            continue
        product_valid = _valid_token(cell.product_id, ProductId)
        axis_valid = _valid_token(cell.axis_id, AxisId)
        product_key = cell.product_id.value if product_valid else ""
        axis_key = cell.axis_id.value if axis_valid else ""
        product_record = product_by_value.get(product_key)
        axis_record = axis_by_value.get(axis_key)
        if (
            not product_valid
            or not axis_valid
            or product_record is None
            or axis_record is None
        ):
            findings.add(ComparisonFindingCode.CELL_COORDINATE_INVALID)
        else:
            coordinate = (product_key, axis_key)
            if coordinate in seen_cells:
                findings.add(ComparisonFindingCode.DUPLICATE_CELL)
            seen_cells.add(coordinate)

        imputed_value: object = cell.imputed
        if type(imputed_value) is not bool:
            findings.add(ComparisonFindingCode.RECORD_TYPE_INVALID)
        elif imputed_value:
            findings.add(ComparisonFindingCode.IMPUTATION_FORBIDDEN)
        if type(cell.state) is not ComparisonCellState:
            findings.add(ComparisonFindingCode.CELL_STATE_INVALID)
            continue

        if cell.state is ComparisonCellState.KNOWN:
            if cell.value is None:
                findings.add(ComparisonFindingCode.VALUE_REQUIRED)
            else:
                scalar_finding = _scalar_finding(cell.value)
                if scalar_finding is not None:
                    findings.add(scalar_finding)
            if not _valid_token(cell.unit, UnitCode):
                findings.add(ComparisonFindingCode.UNIT_REQUIRED)
            elif axis_record is not None and cell.unit != axis_record.unit:
                findings.add(ComparisonFindingCode.UNIT_MISMATCH)
            if not _valid_token(cell.identity_id, IdentityId):
                findings.add(ComparisonFindingCode.IDENTITY_BINDING_INVALID)
            elif (
                product_record is not None
                and cell.identity_id != product_record.identity_id
            ):
                findings.add(ComparisonFindingCode.IDENTITY_BINDING_INVALID)
            if not _valid_token(cell.variant_id, VariantId):
                findings.add(ComparisonFindingCode.VARIANT_BINDING_INVALID)
            elif (
                product_record is not None
                and cell.variant_id != product_record.variant_id
            ):
                findings.add(ComparisonFindingCode.VARIANT_BINDING_INVALID)
            if type(cell.evidence) is not EvidenceBinding:
                findings.add(ComparisonFindingCode.EVIDENCE_REQUIRED)
            elif not (
                _valid_token(cell.evidence.evidence_id, EvidenceId)
                and cell.evidence.product_id == cell.product_id
                and cell.evidence.axis_id == cell.axis_id
                and cell.evidence.identity_id == cell.identity_id
                and cell.evidence.variant_id == cell.variant_id
            ):
                findings.add(ComparisonFindingCode.EVIDENCE_MISMATCH)
        else:
            if cell.value is not None:
                findings.add(ComparisonFindingCode.UNKNOWN_VALUE_PRESENT)
            if cell.unit is not None:
                findings.add(ComparisonFindingCode.UNKNOWN_UNIT_PRESENT)
            if cell.identity_id is not None and (
                not _valid_token(cell.identity_id, IdentityId)
                or product_record is None
                or cell.identity_id != product_record.identity_id
            ):
                findings.add(ComparisonFindingCode.IDENTITY_BINDING_INVALID)
            if cell.variant_id is not None and (
                not _valid_token(cell.variant_id, VariantId)
                or product_record is None
                or cell.variant_id != product_record.variant_id
            ):
                findings.add(ComparisonFindingCode.VARIANT_BINDING_INVALID)
            if cell.evidence is not None:
                if (
                    type(cell.evidence) is not EvidenceBinding
                    or product_record is None
                    or not (
                        _valid_token(cell.evidence.evidence_id, EvidenceId)
                        and cell.evidence.product_id == cell.product_id
                        and cell.evidence.axis_id == cell.axis_id
                        and cell.evidence.identity_id == product_record.identity_id
                        and cell.evidence.variant_id == product_record.variant_id
                    )
                ):
                    findings.add(ComparisonFindingCode.EVIDENCE_MISMATCH)

    expected_cells = {
        (product_key, axis_key)
        for product_key in product_by_value
        for axis_key in axis_by_value
    }
    if seen_cells != expected_cells:
        findings.add(ComparisonFindingCode.MISSING_CELL)

    return _report(findings)

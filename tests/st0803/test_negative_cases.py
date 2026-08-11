"""Fail-closed and no-bypass tests for ST-0803."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from conftest import axis, valid_comparison
from raos.domain.editorial.comparison_validation import (
    ComparisonAxis,
    ComparisonCell,
    ComparisonCellState,
    ComparisonDecision,
    ComparisonFieldName,
    ComparisonFindingCode,
    ComparisonInput,
    ComparisonProduct,
    ComparisonScalar,
    EvidenceBinding,
    ProductId,
    ProductIdentityStatus,
    UnitCode,
    VariantId,
    validate_comparison,
)


def _assert_blocked(
    comparison: object,
    expected: ComparisonFindingCode,
) -> None:
    report = validate_comparison(comparison)
    assert report.decision is ComparisonDecision.BLOCK
    assert expected in report.findings
    assert report.publication_authorized is False
    assert report.production_eligible is False


def _unsafe_scalar(value: object) -> ComparisonScalar:
    scalar = object.__new__(ComparisonScalar)
    object.__setattr__(scalar, "value", value)
    return scalar


def test_hidden_unknown_and_imputation_are_blocked() -> None:
    comparison = valid_comparison()
    hidden = replace(comparison, show_unknown_values=False)
    imputed_cell = replace(comparison.cells[0], imputed=True)
    imputed = replace(
        comparison,
        cells=(imputed_cell, *comparison.cells[1:]),
    )

    _assert_blocked(hidden, ComparisonFindingCode.SHOW_UNKNOWN_VALUES_REQUIRED)
    _assert_blocked(imputed, ComparisonFindingCode.IMPUTATION_FORBIDDEN)


def test_unknown_cell_cannot_carry_an_invented_value_or_unit() -> None:
    comparison = valid_comparison()
    unknown = comparison.cells[1]
    dishonest = replace(
        comparison,
        cells=(
            comparison.cells[0],
            replace(
                unknown,
                value=ComparisonScalar(0),
                unit=comparison.axes[0].unit,
            ),
        ),
    )

    report = validate_comparison(dishonest)

    assert ComparisonFindingCode.UNKNOWN_VALUE_PRESENT in report.findings
    assert ComparisonFindingCode.UNKNOWN_UNIT_PRESENT in report.findings


def test_unresolved_conflicting_and_mismatched_identity_or_variant_block() -> None:
    comparison = valid_comparison()
    unresolved_product = replace(
        comparison.products[0],
        identity_status=ProductIdentityStatus.UNRESOLVED,
        identity_id=None,
        variant_id=None,
    )
    conflicting_product = replace(
        comparison.products[0],
        identity_status=ProductIdentityStatus.CONFLICTING,
        identity_id=None,
        variant_id=None,
    )
    mismatched_cell = replace(
        comparison.cells[0],
        variant_id=VariantId("VARIANT_MISMATCH"),
    )

    _assert_blocked(
        replace(
            comparison,
            products=(unresolved_product, comparison.products[1]),
        ),
        ComparisonFindingCode.IDENTITY_UNRESOLVED,
    )
    _assert_blocked(
        replace(
            comparison,
            products=(conflicting_product, comparison.products[1]),
        ),
        ComparisonFindingCode.IDENTITY_CONFLICT,
    )
    _assert_blocked(
        replace(comparison, cells=(mismatched_cell, comparison.cells[1])),
        ComparisonFindingCode.VARIANT_BINDING_INVALID,
    )


def test_known_cell_requires_exact_unit_and_evidence_binding() -> None:
    comparison = valid_comparison()
    known = comparison.cells[0]
    assert known.evidence is not None
    wrong_evidence = replace(
        known.evidence,
        product_id=ProductId("PRODUCT_DIFFERENT"),
    )
    wrong = replace(
        known,
        unit=UnitCode("KILOGRAM"),
        evidence=wrong_evidence,
    )

    report = validate_comparison(
        replace(comparison, cells=(wrong, comparison.cells[1]))
    )

    assert ComparisonFindingCode.UNIT_MISMATCH in report.findings
    assert ComparisonFindingCode.EVIDENCE_MISMATCH in report.findings


@pytest.mark.parametrize(
    "field_name",
    [
        "FINANCE_VALUE",
        "AFFILIATE_RATE",
        "REVENUE",
        "COMMISSION",
        "COST",
        "PROFIT",
        "EPC",
        "RPM",
    ],
)
def test_finance_and_affiliate_fields_are_impossible(field_name: str) -> None:
    comparison = valid_comparison()
    contaminated_axis = axis(1, field_name=field_name)
    contaminated = replace(comparison, axes=(contaminated_axis,))

    _assert_blocked(contaminated, ComparisonFindingCode.PROHIBITED_FIELD)


@pytest.mark.parametrize("primitive", [True, float("nan"), float("inf")])
def test_bool_and_nonfinite_scalar_bypasses_fail_closed(primitive: object) -> None:
    comparison = valid_comparison()
    bypassed = replace(
        comparison.cells[0],
        value=_unsafe_scalar(primitive),
    )
    report = validate_comparison(
        replace(comparison, cells=(bypassed, comparison.cells[1]))
    )

    expected = (
        ComparisonFindingCode.VALUE_TYPE_INVALID
        if type(primitive) is bool
        else ComparisonFindingCode.VALUE_NONFINITE
    )
    assert expected in report.findings


def test_subclass_mutable_and_runtime_type_bypasses_fail_closed() -> None:
    class ProductIdSubclass(ProductId):
        pass

    comparison = valid_comparison()
    subclass_product = replace(
        comparison.products[0],
        product_id=ProductIdSubclass("PRODUCT_01"),
    )
    mutable_products = cast(
        tuple[ComparisonProduct, ...],
        list(comparison.products),
    )
    invalid_state = cast(ComparisonCellState, "KNOWN")

    _assert_blocked(
        replace(
            comparison,
            products=(subclass_product, comparison.products[1]),
        ),
        ComparisonFindingCode.PRODUCT_ID_INVALID,
    )
    _assert_blocked(
        replace(comparison, products=mutable_products),
        ComparisonFindingCode.COLLECTION_TYPE_INVALID,
    )
    _assert_blocked(
        replace(
            comparison,
            cells=(
                replace(comparison.cells[0], state=invalid_state),
                comparison.cells[1],
            ),
        ),
        ComparisonFindingCode.CELL_STATE_INVALID,
    )


def test_input_and_record_subclasses_are_rejected() -> None:
    class ComparisonInputSubclass(ComparisonInput):
        pass

    class ComparisonCellSubclass(ComparisonCell):
        pass

    comparison = valid_comparison()
    input_subclass = ComparisonInputSubclass(
        mode=comparison.mode,
        products=comparison.products,
        axes=comparison.axes,
        cells=comparison.cells,
        show_unknown_values=True,
    )
    cell_subclass = ComparisonCellSubclass(
        product_id=comparison.cells[0].product_id,
        axis_id=comparison.cells[0].axis_id,
        state=comparison.cells[0].state,
        value=comparison.cells[0].value,
        unit=comparison.cells[0].unit,
        evidence=cast(EvidenceBinding, comparison.cells[0].evidence),
        identity_id=comparison.cells[0].identity_id,
        variant_id=comparison.cells[0].variant_id,
    )

    _assert_blocked(input_subclass, ComparisonFindingCode.INPUT_TYPE_INVALID)
    _assert_blocked(
        replace(
            comparison,
            cells=(cell_subclass, comparison.cells[1]),
        ),
        ComparisonFindingCode.RECORD_TYPE_INVALID,
    )


def test_axis_record_subclass_is_rejected() -> None:
    class ComparisonAxisSubclass(ComparisonAxis):
        pass

    comparison = valid_comparison()
    source_axis = comparison.axes[0]
    subclass_axis = ComparisonAxisSubclass(
        axis_id=source_axis.axis_id,
        field_name=ComparisonFieldName("FEATURE_01"),
        unit=source_axis.unit,
    )

    _assert_blocked(
        replace(comparison, axes=(subclass_axis,)),
        ComparisonFindingCode.RECORD_TYPE_INVALID,
    )

"""Synthetic builders for the isolated ST-0803 TEST_ONLY validator."""

from __future__ import annotations

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
)


def product(
    index: int,
    *,
    status: ProductIdentityStatus = ProductIdentityStatus.PRE_RESOLVED_TEST_ONLY,
) -> ComparisonProduct:
    suffix = f"{index:02d}"
    return ComparisonProduct(
        product_id=ProductId(f"PRODUCT_{suffix}"),
        identity_status=status,
        identity_id=(
            IdentityId(f"IDENTITY_{suffix}")
            if status is ProductIdentityStatus.PRE_RESOLVED_TEST_ONLY
            else None
        ),
        variant_id=(
            VariantId(f"VARIANT_{suffix}")
            if status is ProductIdentityStatus.PRE_RESOLVED_TEST_ONLY
            else None
        ),
    )


def axis(
    index: int,
    *,
    field_name: str | None = None,
    unit: str = "GRAM",
) -> ComparisonAxis:
    suffix = f"{index:02d}"
    return ComparisonAxis(
        axis_id=AxisId(f"AXIS_{suffix}"),
        field_name=ComparisonFieldName(field_name or f"FEATURE_{suffix}"),
        unit=UnitCode(unit),
    )


def known_cell(
    selected_product: ComparisonProduct,
    selected_axis: ComparisonAxis,
    *,
    value: str | int | float = 100,
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
        value=ComparisonScalar(value),
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


def valid_comparison() -> ComparisonInput:
    products = (product(1), product(2))
    axes = (axis(1),)
    cells = (
        known_cell(products[0], axes[0]),
        unknown_cell(products[1], axes[0]),
    )
    return ComparisonInput(
        mode=ComparisonMode.TEST_ONLY,
        products=products,
        axes=axes,
        cells=cells,
        show_unknown_values=True,
    )

"""Cardinality, matrix, ordering, and isolation boundaries for ST-0803."""

from __future__ import annotations

import builtins
from dataclasses import replace

import pytest

from .support import axis, known_cell, product, valid_comparison
import raos.domain.editorial.comparison_validation as comparison_module
from raos.domain.editorial.comparison_validation import (
    ComparisonDecision,
    ComparisonFindingCode,
    ComparisonInput,
    ComparisonValueConstructionError,
    ProductId,
    ProductIdentityStatus,
    validate_comparison,
)


def _matrix(product_count: int, axis_count: int) -> ComparisonInput:
    products = tuple(product(index) for index in range(1, product_count + 1))
    axes = tuple(axis(index) for index in range(1, axis_count + 1))
    cells = tuple(
        known_cell(selected_product, selected_axis, value=product_index + axis_index)
        for product_index, selected_product in enumerate(products, start=1)
        for axis_index, selected_axis in enumerate(axes, start=1)
    )
    return ComparisonInput(
        mode=comparison_module.ComparisonMode.TEST_ONLY,
        products=products,
        axes=axes,
        cells=cells,
        show_unknown_values=True,
    )


@pytest.mark.parametrize(
    ("product_count", "axis_count"),
    [(2, 1), (20, 30)],
)
def test_inclusive_cardinality_limits_pass(
    product_count: int,
    axis_count: int,
) -> None:
    report = validate_comparison(_matrix(product_count, axis_count))

    assert report.decision is ComparisonDecision.PASS
    assert report.findings == ()


@pytest.mark.parametrize("product_count", [1, 21])
def test_product_count_outside_closed_range_blocks(product_count: int) -> None:
    report = validate_comparison(_matrix(product_count, 1))

    assert ComparisonFindingCode.PRODUCT_COUNT_INVALID in report.findings


@pytest.mark.parametrize("axis_count", [0, 31])
def test_axis_count_outside_closed_range_blocks(axis_count: int) -> None:
    report = validate_comparison(_matrix(2, axis_count))

    assert ComparisonFindingCode.AXIS_COUNT_INVALID in report.findings


def test_duplicate_products_axes_and_cells_block() -> None:
    comparison = valid_comparison()
    duplicate_product = replace(
        comparison,
        products=(comparison.products[0], comparison.products[0]),
    )
    duplicate_axis = replace(
        comparison,
        axes=(comparison.axes[0], comparison.axes[0]),
    )
    duplicate_cell = replace(
        comparison,
        cells=(comparison.cells[0], comparison.cells[0], comparison.cells[1]),
    )

    assert (
        ComparisonFindingCode.DUPLICATE_PRODUCT
        in validate_comparison(duplicate_product).findings
    )
    assert (
        ComparisonFindingCode.DUPLICATE_AXIS
        in validate_comparison(duplicate_axis).findings
    )
    assert (
        ComparisonFindingCode.DUPLICATE_CELL
        in validate_comparison(duplicate_cell).findings
    )


def test_missing_matrix_coordinate_blocks() -> None:
    comparison = valid_comparison()
    missing = replace(comparison, cells=(comparison.cells[0],))

    report = validate_comparison(missing)

    assert ComparisonFindingCode.MISSING_CELL in report.findings


def test_findings_are_closed_ordered_deduplicated_and_no_echo() -> None:
    comparison = valid_comparison()
    unresolved = replace(
        comparison.products[0],
        identity_status=ProductIdentityStatus.UNRESOLVED,
        identity_id=None,
        variant_id=None,
    )
    invalid = replace(
        comparison,
        products=(unresolved, comparison.products[1]),
        axes=(
            replace(
                comparison.axes[0],
                field_name=comparison_module.ComparisonFieldName("AFFILIATE_RATE"),
            ),
        ),
        cells=(replace(comparison.cells[0], imputed=True), comparison.cells[1]),
        show_unknown_values=False,
    )

    first = validate_comparison(invalid)
    second = validate_comparison(invalid)
    expected_order = tuple(
        code for code in ComparisonFindingCode if code in set(first.findings)
    )

    assert first == second
    assert first.findings == expected_order
    assert len(first.findings) == len(set(first.findings))
    assert repr(first) == "ComparisonValidationReport(<redacted>)"
    for raw_value in ("PRODUCT_01", "AXIS_01", "AFFILIATE_RATE", "IDENTITY_01"):
        assert raw_value not in repr(first)
        assert raw_value not in str(first)


def test_validator_performs_no_file_environment_clock_random_or_network_work(
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
        "random",
        "requests",
        "socket",
        "subprocess",
        "time",
        "urllib",
    ):
        assert forbidden_name not in vars(comparison_module)

    assert validate_comparison(valid_comparison()).passed is True


def test_invalid_exact_value_error_is_stable_and_redacted() -> None:
    raw_value = "secret value which must not echo"

    with pytest.raises(ComparisonValueConstructionError) as captured:
        ProductId(raw_value)

    assert str(captured.value) == "INVALID_EXACT_VALUE"
    assert raw_value not in repr(captured.value)

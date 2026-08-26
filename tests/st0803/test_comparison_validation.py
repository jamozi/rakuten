"""Happy-path contract tests for ST-0803."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from .support import valid_comparison
from raos.domain.editorial.comparison_validation import (
    ComparisonDecision,
    CoverageStatus,
    ExecutionStatus,
    MappingStatus,
    validate_comparison,
)


def test_synthetic_pre_resolved_matrix_passes_without_authorizing_use() -> None:
    comparison = valid_comparison()

    report = validate_comparison(comparison)

    assert report.decision is ComparisonDecision.PASS
    assert report.findings == ()
    assert report.passed is True
    assert report.publication_authorized is False
    assert report.production_eligible is False
    assert report.identity_resolution_status is ExecutionStatus.NOT_EXECUTED
    assert report.coverage_status is CoverageStatus.UNEVALUABLE
    assert report.coverage_mapping_status is MappingStatus.UNAVAILABLE
    assert report.coverage_calculation_status is ExecutionStatus.NOT_EXECUTED
    assert report.formal_test_status is ExecutionStatus.NOT_EXECUTED
    assert report.live_validation_status is ExecutionStatus.NOT_EXECUTED


def test_validation_is_deterministic_non_mutating_and_redacted() -> None:
    comparison = valid_comparison()
    original_hash = hash(comparison)

    first = validate_comparison(comparison)
    second = validate_comparison(comparison)

    assert first == second
    assert hash(comparison) == original_hash
    assert repr(comparison) == "ComparisonInput(<redacted>)"
    assert str(comparison.products[0].product_id) == "<redacted>"
    assert "PRODUCT_01" not in repr(comparison)
    with pytest.raises(FrozenInstanceError):
        setattr(comparison, "show_unknown_values", False)

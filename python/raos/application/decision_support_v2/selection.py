"""Selection use case with an explicit finance non-interference boundary."""

from __future__ import annotations

from raos.domain.decision_support_v2.selection import (
    FitInputs,
    RankedProduct,
    rank_products,
    render_semantic_hash,
)


def select_for_reader(
    candidates: tuple[FitInputs, ...],
) -> tuple[tuple[RankedProduct, ...], str]:
    ranked = rank_products(candidates)
    return ranked, render_semantic_hash(ranked)


__all__ = ["select_for_reader"]

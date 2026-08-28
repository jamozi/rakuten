"""Eligibility-first product selection without business inputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import json
from typing import Mapping

from raos.domain.decision_support_v2.models import (
    FreshnessState,
    IdentityStatus,
    ProductModel,
    exact_decimal,
)


FIT_WEIGHTS: Mapping[str, Decimal] = {
    "compatibility": Decimal("0.30"),
    "declared_constraint": Decimal("0.25"),
    "verified_spec": Decimal("0.20"),
    "tradeoff_clarity": Decimal("0.15"),
    "evidence_freshness": Decimal("0.10"),
}
FRESHNESS_VALUE: Mapping[FreshnessState, Decimal] = {
    FreshnessState.FRESH: Decimal("1.00"),
    FreshnessState.DUE: Decimal("0.70"),
    FreshnessState.SOFT_STALE: Decimal("0.30"),
    FreshnessState.HARD_STALE: Decimal("0.00"),
    FreshnessState.UNKNOWN: Decimal("0.00"),
    FreshnessState.UNAVAILABLE: Decimal("0.00"),
    FreshnessState.REJECTED: Decimal("0.00"),
}


@dataclass(frozen=True, slots=True)
class FitInputs:
    product: ProductModel
    checked_at: datetime
    compatibility: Decimal
    declared_constraint: Decimal
    verified_spec: Decimal
    tradeoff_clarity: Decimal
    evidence_freshness: FreshnessState
    hard_constraint_pass: bool

    def __post_init__(self) -> None:
        if self.checked_at.tzinfo is None or self.checked_at.utcoffset() is None:
            raise ValueError("checked_at must be timezone-aware")
        for field_name in (
            "compatibility",
            "declared_constraint",
            "verified_spec",
            "tradeoff_clarity",
        ):
            value = exact_decimal(getattr(self, field_name))
            if value > 1:
                raise ValueError("fit components must be between zero and one")
            object.__setattr__(self, field_name, value)


@dataclass(frozen=True, slots=True)
class RankedProduct:
    product_id: str
    score: Decimal
    compatibility: Decimal
    checked_at: datetime
    eligible: bool
    reason_codes: tuple[str, ...]


def calculate_fit(inputs: FitInputs) -> RankedProduct:
    reasons: list[str] = []
    if inputs.product.identity_status is not IdentityStatus.EXACT:
        reasons.append("IDENTITY_NOT_EXACT")
    if not inputs.hard_constraint_pass:
        reasons.append("HARD_CONSTRAINT_FAILED")
    if inputs.evidence_freshness in {
        FreshnessState.HARD_STALE,
        FreshnessState.UNKNOWN,
        FreshnessState.UNAVAILABLE,
        FreshnessState.REJECTED,
    }:
        reasons.append("EVIDENCE_NOT_ELIGIBLE")
    eligible = not reasons
    components = {
        "compatibility": inputs.compatibility,
        "declared_constraint": inputs.declared_constraint,
        "verified_spec": inputs.verified_spec,
        "tradeoff_clarity": inputs.tradeoff_clarity,
        "evidence_freshness": FRESHNESS_VALUE[inputs.evidence_freshness],
    }
    score = sum(
        (components[name] * weight for name, weight in FIT_WEIGHTS.items()),
        Decimal(0),
    ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN)
    return RankedProduct(
        inputs.product.product_id,
        score if eligible else Decimal(0),
        inputs.compatibility,
        inputs.checked_at,
        eligible,
        tuple(reasons) if reasons else ("ELIGIBLE",),
    )


def rank_products(candidates: tuple[FitInputs, ...]) -> tuple[RankedProduct, ...]:
    """Exclude hard-ineligible products and apply deterministic tie breaks."""

    results = tuple(calculate_fit(candidate) for candidate in candidates)
    eligible = tuple(result for result in results if result.eligible)
    return tuple(
        sorted(
            eligible,
            key=lambda item: (
                -item.score,
                -item.compatibility,
                -item.checked_at.timestamp(),
                item.product_id,
            ),
        )
    )


def render_semantic_hash(results: tuple[RankedProduct, ...]) -> str:
    payload = [
        {
            "product_id": item.product_id,
            "score": format(item.score, "f"),
            "compatibility": format(item.compatibility, "f"),
            "eligible": item.eligible,
            "reason_codes": list(item.reason_codes),
        }
        for item in results
    ]
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "FIT_WEIGHTS",
    "FitInputs",
    "RankedProduct",
    "calculate_fit",
    "rank_products",
    "render_semantic_hash",
]

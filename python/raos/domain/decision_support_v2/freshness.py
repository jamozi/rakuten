"""Frozen-clock freshness classification for source-backed facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from raos.domain.decision_support_v2.models import FreshnessState, RiskClass


_SOFT_GRACE = {
    RiskClass.HIGH: timedelta(days=7),
    RiskClass.MEDIUM: timedelta(days=30),
    RiskClass.LOW: timedelta(days=60),
}


@dataclass(frozen=True, slots=True)
class FreshnessAssessment:
    state: FreshnessState
    action: str
    seal_allowed: bool


def assess_freshness(
    *, now: datetime, next_review_at: datetime | None, risk_class: RiskClass
) -> FreshnessAssessment:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if next_review_at is None:
        return FreshnessAssessment(FreshnessState.UNKNOWN, "REVIEW_NOW", False)
    if next_review_at.tzinfo is None or next_review_at.utcoffset() is None:
        raise ValueError("next_review_at must be timezone-aware")
    if now < next_review_at:
        return FreshnessAssessment(FreshnessState.FRESH, "NONE", True)
    if now == next_review_at:
        return FreshnessAssessment(FreshnessState.DUE, "QUEUE_REVIEW", True)
    if now <= next_review_at + _SOFT_GRACE[risk_class]:
        return FreshnessAssessment(FreshnessState.SOFT_STALE, "REVIEW_NOW", False)
    return FreshnessAssessment(FreshnessState.HARD_STALE, "BLOCK_AND_REFRESH", False)


__all__ = ["FreshnessAssessment", "assess_freshness"]

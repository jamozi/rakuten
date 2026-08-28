"""Pure calculations for the reliability-first bounded context V1."""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_EVEN
from math import floor
from typing import Final, Iterable, Literal

from raos.domain.editorial.recommendation_v2 import (
    CandidateEligibility,
    RankingState,
    RecommendationReportV2,
)
from raos.domain.reliability.contracts_v1 import (
    ARTICLE_ID,
    ConfidenceGradeV1,
    FitCandidateV1,
    FitScoreV1,
    ProductReviewSignalV1,
    RecommendationProfileV1,
    RecommendationStatusV1,
    ReviewAggregateSetV1,
    ReviewContributionV1,
    ReviewEvidenceStatusV1,
    ReviewObservationV1,
    RiskLevelV1,
    SafetyStateV1,
    ThemeSeverityV1,
    TrustedCandidateEvidenceV1,
    TrustedRecommendationCandidateV1,
    TrustedRecommendationResultV1,
)


SCORE_QUANTUM: Final = Decimal("0.0001")
REVIEW_PRIOR_WEIGHT: Final = Decimal("50")
REVIEW_COUNT_CAP: Final = 500
REVIEW_MINIMUM_DOMAINS: Final = 2
REVIEW_MINIMUM_TOTAL: Final = 30
REVIEW_SOURCE_CAP: Final = Decimal("0.4")
REVIEW_CONFLICT_MINIMUM_COUNT: Final = 30
REVIEW_CONFLICT_PERCENTILE_SPREAD: Final = Decimal("40")
TIE_MAXIMUM_DIFFERENCE: Final = Decimal("3")
PRICE_FRESHNESS: Final = timedelta(hours=24)
REVIEW_FRESHNESS: Final = timedelta(days=30)

PROFILES: Final = (
    RecommendationProfileV1(
        profile_id="LIGHTWEIGHT",
        weight_weight=35,
        capacity_weight=10,
        access_weight=10,
        support_weight=20,
        price_weight=25,
    ),
    RecommendationProfileV1(
        profile_id="CAPACITY",
        weight_weight=10,
        capacity_weight=35,
        access_weight=10,
        support_weight=20,
        price_weight=25,
    ),
    RecommendationProfileV1(
        profile_id="ACCESS",
        weight_weight=10,
        capacity_weight=15,
        access_weight=30,
        support_weight=20,
        price_weight=25,
    ),
)


def _aware_utc(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("AWARE_UTC_REQUIRED")
    return value.astimezone(timezone.utc)


def _score(value: Decimal) -> Decimal:
    return min(Decimal("100"), max(Decimal("0"), value)).quantize(
        SCORE_QUANTUM,
        rounding=ROUND_HALF_EVEN,
    )


def add_calendar_months(value: datetime, months: int) -> datetime:
    """Add calendar months while clamping the day to the target month."""

    current = _aware_utc(value)
    if type(months) is not int or not 0 <= months <= 120:
        raise ValueError("INVALID_RETENTION_MONTHS")
    absolute = current.year * 12 + current.month - 1 + months
    year, zero_month = divmod(absolute, 12)
    month = zero_month + 1
    day = min(current.day, calendar.monthrange(year, month)[1])
    return current.replace(year=year, month=month, day=day)


def _percentile(values: tuple[Decimal, ...], percentile: Decimal) -> Decimal:
    if not values:
        raise ValueError("EMPTY_PERCENTILE_INPUT")
    ordered = tuple(sorted(values))
    if len(ordered) == 1:
        return ordered[0]
    position = Decimal(len(ordered) - 1) * percentile
    lower = floor(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - Decimal(lower)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _utility(
    value: Decimal,
    values: tuple[Decimal, ...],
    *,
    lower_is_better: bool,
) -> Decimal:
    low = _percentile(values, Decimal("0.1"))
    high = _percentile(values, Decimal("0.9"))
    if high == low:
        return Decimal("50")
    bounded = min(high, max(low, value))
    result = (bounded - low) * Decimal("100") / (high - low)
    return Decimal("100") - result if lower_is_better else result


def _median(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise ValueError("EMPTY_MEDIAN_INPUT")
    ordered = tuple(sorted(values))
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal("2")


def _hard_gate(candidate: FitCandidateV1) -> tuple[bool, str | None]:
    dimensions = (candidate.height_cm, candidate.width_cm, candidate.depth_cm)
    if any(value is None for value in dimensions):
        return False, "HARD_CONSTRAINT_UNAVAILABLE"
    height, width, depth = dimensions
    assert height is not None and width is not None and depth is not None
    if (
        height > Decimal("55")
        or width > Decimal("40")
        or depth > Decimal("25")
        or height + width + depth > Decimal("115")
    ):
        return False, "HARD_CONSTRAINT_FAILED"
    return True, None


def _fresh_price(candidate: FitCandidateV1, now: datetime) -> Decimal | None:
    current = _aware_utc(now)
    prices = tuple(
        Decimal(offer.displayed_price_jpy)
        for offer in candidate.offers
        if offer.is_new
        and offer.is_domestic_regular
        and timedelta(0) <= current - _aware_utc(offer.observed_at) <= PRICE_FRESHNESS
    )
    return None if not prices else _median(prices)


def calculate_fit_scores(
    candidates: tuple[FitCandidateV1, ...],
    *,
    now: datetime,
) -> tuple[FitScoreV1, ...]:
    """Calculate the three fixed suitcase profiles deterministically."""

    _aware_utc(now)
    if not candidates or len({item.product_id for item in candidates}) != len(candidates):
        raise ValueError("INVALID_FIT_CANDIDATE_SET")
    gate = {item.product_id: _hard_gate(item) for item in candidates}
    prices = {item.product_id: _fresh_price(item, now) for item in candidates}
    eligible = tuple(item for item in candidates if gate[item.product_id][0])
    weight_values = tuple(
        item.body_weight_kg for item in eligible if item.body_weight_kg is not None
    )
    capacity_values = tuple(
        item.base_capacity_l for item in eligible if item.base_capacity_l is not None
    )
    price_values = tuple(
        price for item in eligible if (price := prices[item.product_id]) is not None
    )
    results: list[FitScoreV1] = []
    for profile in PROFILES:
        for candidate in sorted(candidates, key=lambda item: item.product_id):
            passed, gate_reason = gate[candidate.product_id]
            current_price = prices[candidate.product_id]
            if not passed:
                results.append(
                    FitScoreV1(
                        product_id=candidate.product_id,
                        profile_id=profile.profile_id,
                        hard_gate_passed=False,
                        fit_score=None,
                        evidence_coverage=Decimal("0"),
                        median_price_jpy=current_price,
                        price_current=current_price is not None,
                        reason_codes=(gate_reason or "HARD_CONSTRAINT_FAILED",),
                    )
                )
                continue
            components: tuple[tuple[int, Decimal | None], ...] = (
                (
                    profile.weight_weight,
                    None
                    if candidate.body_weight_kg is None or not weight_values
                    else _utility(
                        candidate.body_weight_kg,
                        weight_values,
                        lower_is_better=True,
                    ),
                ),
                (
                    profile.capacity_weight,
                    None
                    if candidate.base_capacity_l is None or not capacity_values
                    else _utility(
                        candidate.base_capacity_l,
                        capacity_values,
                        lower_is_better=False,
                    ),
                ),
                (profile.access_weight, candidate.access_utility),
                (profile.support_weight, candidate.support_utility),
                (
                    profile.price_weight,
                    None
                    if current_price is None or not price_values
                    else _utility(
                        current_price,
                        price_values,
                        lower_is_better=True,
                    ),
                ),
            )
            known_weight = sum(weight for weight, value in components if value is not None)
            fit_score = sum(
                (
                    Decimal(weight) * value / Decimal("100")
                    for weight, value in components
                    if value is not None
                ),
                start=Decimal("0"),
            )
            reasons: list[str] = []
            if candidate.body_weight_kg is None:
                reasons.append("WEIGHT_UNKNOWN")
            if candidate.base_capacity_l is None:
                reasons.append("CAPACITY_UNKNOWN")
            if current_price is None:
                reasons.append("PRICE_MISSING_OR_STALE")
            results.append(
                FitScoreV1(
                    product_id=candidate.product_id,
                    profile_id=profile.profile_id,
                    hard_gate_passed=True,
                    fit_score=_score(fit_score),
                    evidence_coverage=(
                        Decimal(known_weight) / Decimal("100")
                    ).quantize(SCORE_QUANTUM),
                    median_price_jpy=current_price,
                    price_current=current_price is not None,
                    reason_codes=tuple(reasons),
                )
            )
    return tuple(results)


def _midrank_percentile(value: Decimal, values: tuple[Decimal, ...]) -> Decimal:
    if len(values) <= 1:
        return Decimal("50")
    less = sum(1 for item in values if item < value)
    equal = sum(1 for item in values if item == value)
    position = Decimal(less) + (Decimal(equal) - Decimal("1")) / Decimal("2")
    return _score(position * Decimal("100") / Decimal(len(values) - 1))


def _capped_weights(counts: dict[str, Decimal]) -> dict[str, Decimal]:
    if len(counts) == 2:
        return {source: Decimal("0.5") for source in counts}
    remaining = dict(counts)
    assigned: dict[str, Decimal] = {}
    remaining_mass = Decimal("1")
    while remaining:
        total = sum(remaining.values())
        if total <= 0:
            equal = remaining_mass / Decimal(len(remaining))
            assigned.update({source: equal for source in remaining})
            break
        provisional = {
            source: remaining_mass * count / total
            for source, count in remaining.items()
        }
        capped = tuple(
            source
            for source, weight in provisional.items()
            if weight > REVIEW_SOURCE_CAP
        )
        if not capped:
            assigned.update(provisional)
            break
        for source in sorted(capped):
            assigned[source] = REVIEW_SOURCE_CAP
            remaining_mass -= REVIEW_SOURCE_CAP
            del remaining[source]
    return assigned


def _review_adjustment(signal: Decimal) -> Decimal:
    if signal >= Decimal("50"):
        return min(Decimal("5"), (signal - Decimal("50")) * Decimal("0.10")).quantize(
            SCORE_QUANTUM
        )
    return -min(Decimal("8"), (Decimal("50") - signal) * Decimal("0.16")).quantize(
        SCORE_QUANTUM
    )


def calculate_review_aggregates(
    observations: tuple[ReviewObservationV1, ...],
    *,
    article_id: Literal["raos-reliability-suitcase-pilot-001"] = ARTICLE_ID,
    artifact_id: str,
    acquired_at: datetime,
) -> ReviewAggregateSetV1:
    """Normalize aggregate ratings without retaining review bodies."""

    current = _aware_utc(acquired_at)
    keys = tuple((item.product_id, item.source_id) for item in observations)
    if len(keys) != len(set(keys)):
        raise ValueError("DUPLICATE_REVIEW_OBSERVATION")
    valid = tuple(
        item
        for item in observations
        if item.identity_match_confirmed
        and item.anomaly_factor > 0
        and timedelta(0)
        <= current - _aware_utc(item.acquired_at)
        <= REVIEW_FRESHNESS
    )
    by_source: dict[str, list[ReviewObservationV1]] = defaultdict(list)
    for item in valid:
        by_source[item.source_id].append(item)
    shrunk: dict[tuple[str, str], Decimal] = {}
    percentiles: dict[tuple[str, str], Decimal] = {}
    for source, items in by_source.items():
        prior = sum(item.rating_average for item in items) / Decimal(len(items))
        source_values: list[Decimal] = []
        for item in items:
            count = Decimal(min(item.rating_count, REVIEW_COUNT_CAP))
            value = (
                count * item.rating_average + REVIEW_PRIOR_WEIGHT * prior
            ) / (count + REVIEW_PRIOR_WEIGHT)
            value = value.quantize(SCORE_QUANTUM)
            shrunk[(item.product_id, source)] = value
            source_values.append(value)
        values = tuple(source_values)
        for item in items:
            percentiles[(item.product_id, source)] = _midrank_percentile(
                shrunk[(item.product_id, source)],
                values,
            )
    by_product: dict[str, list[ReviewObservationV1]] = defaultdict(list)
    for item in valid:
        by_product[item.product_id].append(item)
    all_products = sorted({item.product_id for item in observations})
    signals: list[ProductReviewSignalV1] = []
    for product_id in all_products:
        items = by_product.get(product_id, [])
        total_count = sum(item.rating_count for item in items)
        domains = {item.source_id for item in items}
        if len(domains) < REVIEW_MINIMUM_DOMAINS or total_count < REVIEW_MINIMUM_TOTAL:
            signals.append(
                ProductReviewSignalV1(
                    product_id=product_id,
                    status=ReviewEvidenceStatusV1.INSUFFICIENT,
                    total_rating_count=total_count,
                    review_signal=None,
                    review_adjustment=Decimal("0"),
                    maximum_percentile_spread=None,
                    structural_anomaly_detected=False,
                    contributions=(),
                )
            )
            continue
        effective_counts = {
            item.source_id: Decimal(min(item.rating_count, REVIEW_COUNT_CAP))
            * item.anomaly_factor
            for item in items
        }
        weights = _capped_weights(effective_counts)
        contributions = tuple(
            ReviewContributionV1(
                source_id=item.source_id,
                rating_count=item.rating_count,
                bayesian_rating=shrunk[(product_id, item.source_id)],
                percentile=percentiles[(product_id, item.source_id)],
                final_weight=weights[item.source_id].quantize(SCORE_QUANTUM),
                verified_purchase=item.verified_purchase,
            )
            for item in sorted(items, key=lambda value: value.source_id)
        )
        signal = _score(
            sum(
                (item.percentile * item.final_weight for item in contributions),
                start=Decimal("0"),
            )
        )
        reliable_percentiles = tuple(
            item.percentile
            for item in contributions
            if item.rating_count >= REVIEW_CONFLICT_MINIMUM_COUNT
        )
        maximum_spread = (
            max(reliable_percentiles) - min(reliable_percentiles)
            if len(reliable_percentiles) >= 2
            else Decimal("0")
        ).quantize(SCORE_QUANTUM)
        conflicting = maximum_spread >= REVIEW_CONFLICT_PERCENTILE_SPREAD
        signals.append(
            ProductReviewSignalV1(
                product_id=product_id,
                status=(
                    ReviewEvidenceStatusV1.CONFLICTING
                    if conflicting
                    else ReviewEvidenceStatusV1.SUFFICIENT
                ),
                total_rating_count=total_count,
                review_signal=signal,
                review_adjustment=(
                    Decimal("0") if conflicting else _review_adjustment(signal)
                ),
                maximum_percentile_spread=maximum_spread,
                structural_anomaly_detected=conflicting,
                contributions=contributions,
            )
        )
    return ReviewAggregateSetV1(
        artifact_id=artifact_id,
        article_id=article_id,
        observations=observations,
        signals=tuple(signals),
        acquired_at=current,
        expires_at=add_calendar_months(current, 13),
    )


def _confidence(
    evidence: TrustedCandidateEvidenceV1,
) -> tuple[int, ConfidenceGradeV1]:
    dimensions = evidence.evidence_dimensions
    score = (
        dimensions.identity
        + dimensions.official_information
        + dimensions.safety
        + dimensions.independent_evidence
        + dimensions.review_diversity
        + dimensions.freshness_consistency
    )
    cap = 12
    if dimensions.identity < 2:
        cap = min(cap, 5)
    if dimensions.safety_required and dimensions.safety < 2:
        cap = min(cap, 5)
    if dimensions.unresolved_major_conflict:
        cap = min(cap, 8)
    if dimensions.source_family_count < 2:
        cap = min(cap, 5)
    score = min(score, cap)
    if score >= 11:
        return score, ConfidenceGradeV1.A
    if score >= 9:
        return score, ConfidenceGradeV1.B
    if score >= 6:
        return score, ConfidenceGradeV1.C
    if score >= 3:
        return score, ConfidenceGradeV1.D
    return score, ConfidenceGradeV1.E


def _risk(
    evidence: TrustedCandidateEvidenceV1,
) -> tuple[RiskLevelV1, Decimal]:
    if evidence.safety_state is SafetyStateV1.ACTIVE_RECALL:
        return RiskLevelV1.HIGH, Decimal("15")
    if evidence.safety_state in {
        SafetyStateV1.POSSIBLE_MATCH,
        SafetyStateV1.NOT_CHECKED,
    }:
        return RiskLevelV1.UNKNOWN, Decimal("0")
    if evidence.maximum_theme_severity is ThemeSeverityV1.HIGH:
        return RiskLevelV1.HIGH, Decimal("15")
    if evidence.maximum_theme_severity is ThemeSeverityV1.MEDIUM:
        return RiskLevelV1.MEDIUM, Decimal("8")
    if evidence.maximum_theme_severity is ThemeSeverityV1.LOW:
        return RiskLevelV1.LOW, Decimal("3")
    return RiskLevelV1.LOW, Decimal("0")


def _status(
    *,
    v2_eligible: bool,
    evidence: TrustedCandidateEvidenceV1,
    grade: ConfidenceGradeV1,
    risk: RiskLevelV1,
) -> RecommendationStatusV1:
    if not v2_eligible or evidence.safety_state is SafetyStateV1.ACTIVE_RECALL:
        return RecommendationStatusV1.EXCLUDED
    if (
        evidence.safety_state is SafetyStateV1.POSSIBLE_MATCH
        or evidence.review_status is ReviewEvidenceStatusV1.CONFLICTING
        or risk is RiskLevelV1.HIGH
    ):
        return RecommendationStatusV1.WATCH
    if evidence.safety_state is SafetyStateV1.NOT_CHECKED:
        return RecommendationStatusV1.INSUFFICIENT_EVIDENCE
    if grade in {ConfidenceGradeV1.D, ConfidenceGradeV1.E}:
        return RecommendationStatusV1.INSUFFICIENT_EVIDENCE
    if (
        not evidence.price_current
        or grade is ConfidenceGradeV1.C
        or evidence.review_status is ReviewEvidenceStatusV1.INSUFFICIENT
        or evidence.evidence_dimensions.official_information < 2
        or evidence.support_utility < Decimal("100")
    ):
        return RecommendationStatusV1.CONDITIONAL
    return RecommendationStatusV1.RECOMMENDED


def _risk_sort(level: RiskLevelV1) -> int:
    return {
        RiskLevelV1.LOW: 0,
        RiskLevelV1.MEDIUM: 1,
        RiskLevelV1.UNKNOWN: 2,
        RiskLevelV1.HIGH: 3,
    }[level]


def _grade_sort(grade: ConfidenceGradeV1) -> int:
    return {
        ConfidenceGradeV1.A: 0,
        ConfidenceGradeV1.B: 1,
        ConfidenceGradeV1.C: 2,
        ConfidenceGradeV1.D: 3,
        ConfidenceGradeV1.E: 4,
    }[grade]


def enhance_recommendation_v2(
    report: RecommendationReportV2,
    evidence: tuple[TrustedCandidateEvidenceV1, ...],
    *,
    article_id: Literal["raos-reliability-suitcase-pilot-001"] = ARTICLE_ID,
    artifact_id: str,
    profile_id: Literal["LIGHTWEIGHT", "CAPACITY", "ACCESS"],
    calculated_at: datetime,
) -> TrustedRecommendationResultV1:
    """Apply bounded review/risk/confidence logic to exact V2 base scores."""

    if type(report) is not RecommendationReportV2:
        raise TypeError("RECOMMENDATION_V2_REPORT_REQUIRED")
    report.require_valid()
    if not report.locally_calculated or report.findings:
        raise ValueError("RECOMMENDATION_V2_REPORT_NOT_CALCULATED")
    evidence_by_product = {item.product_id: item for item in evidence}
    if len(evidence_by_product) != len(evidence):
        raise ValueError("DUPLICATE_TRUSTED_CANDIDATE_EVIDENCE")
    v2_products = {str(item.product_id.value) for item in report.candidates}
    if set(evidence_by_product) != v2_products:
        raise ValueError("V2_EVIDENCE_PRODUCT_SET_MISMATCH")
    candidates: list[TrustedRecommendationCandidateV1] = []
    for item in report.candidates:
        product_id = str(item.product_id.value)
        candidate_evidence = evidence_by_product[product_id]
        confidence_score, grade = _confidence(candidate_evidence)
        risk, risk_penalty = _risk(candidate_evidence)
        v2_eligible = (
            item.eligibility is CandidateEligibility.ELIGIBLE
            and item.ranking_state is RankingState.RANKED
            and item.base_score is not None
        )
        status = _status(
            v2_eligible=v2_eligible,
            evidence=candidate_evidence,
            grade=grade,
            risk=risk,
        )
        internal_score = None
        reasons: list[str] = []
        if v2_eligible:
            if status not in {
                RecommendationStatusV1.EXCLUDED,
                RecommendationStatusV1.INSUFFICIENT_EVIDENCE,
            }:
                assert item.base_score is not None
                internal_score = min(
                    Decimal("105"),
                    max(
                        Decimal("0"),
                        item.base_score
                        + candidate_evidence.review_adjustment
                        - risk_penalty,
                    ),
                ).quantize(SCORE_QUANTUM)
        else:
            reasons.append("V2_NOT_RANKED")
        if candidate_evidence.safety_state is SafetyStateV1.ACTIVE_RECALL:
            reasons.append("ACTIVE_RECALL")
        elif candidate_evidence.safety_state is SafetyStateV1.POSSIBLE_MATCH:
            reasons.append("SAFETY_MATCH_REQUIRES_REVIEW")
        elif candidate_evidence.safety_state is SafetyStateV1.NOT_CHECKED:
            reasons.append("SAFETY_NOT_CHECKED")
        if not candidate_evidence.price_current:
            reasons.append("PRICE_MISSING_OR_STALE")
        if candidate_evidence.review_status is ReviewEvidenceStatusV1.INSUFFICIENT:
            reasons.append("REVIEW_EVIDENCE_INSUFFICIENT")
        elif candidate_evidence.review_status is ReviewEvidenceStatusV1.CONFLICTING:
            reasons.append("REVIEW_SIGNAL_CONFLICTING")
        if candidate_evidence.evidence_dimensions.official_information < 2:
            reasons.append("OFFICIAL_EVIDENCE_INCOMPLETE")
        if candidate_evidence.support_utility < Decimal("100"):
            reasons.append("SUPPORT_EVIDENCE_INCOMPLETE")
        if grade in {ConfidenceGradeV1.D, ConfidenceGradeV1.E}:
            reasons.append("CONFIDENCE_TOO_LOW")
        candidates.append(
            TrustedRecommendationCandidateV1(
                product_id=product_id,
                fit_score=item.base_score,
                review_signal=candidate_evidence.review_signal,
                review_adjustment=candidate_evidence.review_adjustment,
                confidence_score=confidence_score,
                confidence_grade=grade,
                risk_level=risk,
                risk_penalty=risk_penalty,
                internal_rank_score=internal_score,
                recommendation_status=status,
                reason_codes=tuple(reasons),
            )
        )
    evidence_sort = evidence_by_product

    def rank_key(candidate: TrustedRecommendationCandidateV1) -> tuple[object, ...]:
        internal_score = candidate.internal_rank_score
        if internal_score is None:
            raise ValueError("RANKABLE_SCORE_REQUIRED")
        return (
            -internal_score,
            _grade_sort(candidate.confidence_grade),
            _risk_sort(candidate.risk_level),
            -evidence_sort[candidate.product_id].support_utility,
            -evidence_sort[candidate.product_id].evidence_dimensions.identity,
            -evidence_sort[
                candidate.product_id
            ].evidence_dimensions.freshness_consistency,
            candidate.product_id,
        )

    rankable = sorted(
        (
            candidate
            for candidate in candidates
            if candidate.internal_rank_score is not None
        ),
        key=rank_key,
    )
    ranked_by_product: dict[str, tuple[int, int]] = {}
    anchor: Decimal | None = None
    tie_group = 0
    for rank, ranked_candidate in enumerate(rankable, start=1):
        assert ranked_candidate.internal_rank_score is not None
        if (
            anchor is None
            or anchor - ranked_candidate.internal_rank_score
            > TIE_MAXIMUM_DIFFERENCE
        ):
            anchor = ranked_candidate.internal_rank_score
            tie_group += 1
        ranked_by_product[ranked_candidate.product_id] = (rank, tie_group)
    final_candidates = tuple(
        item.model_copy(
            update={
                "rank": ranked_by_product[item.product_id][0],
                "tie_group": ranked_by_product[item.product_id][1],
            }
        )
        if item.product_id in ranked_by_product
        else item
        for item in sorted(candidates, key=lambda value: value.product_id)
    )
    return TrustedRecommendationResultV1(
        artifact_id=artifact_id,
        article_id=article_id,
        profile_id=profile_id,
        v2_report_sha256=report.report_sha256.value,
        candidates=final_candidates,
        ranking_order=tuple(item.product_id for item in rankable),
        calculated_at=_aware_utc(calculated_at),
    )


def maximum_theme_severity(
    severities: Iterable[ThemeSeverityV1],
) -> ThemeSeverityV1 | None:
    """Return maximum validated severity without cumulative penalties."""

    priority = {
        ThemeSeverityV1.LOW: 1,
        ThemeSeverityV1.MEDIUM: 2,
        ThemeSeverityV1.HIGH: 3,
    }
    values = tuple(severities)
    return None if not values else max(values, key=priority.__getitem__)


__all__ = [
    "PROFILES",
    "add_calendar_months",
    "calculate_fit_scores",
    "calculate_review_aggregates",
    "enhance_recommendation_v2",
    "maximum_theme_severity",
]

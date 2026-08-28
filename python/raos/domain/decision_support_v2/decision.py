"""Fail-closed, all-segment carry-on decision engine."""

from __future__ import annotations

from decimal import Decimal
from itertools import permutations

from raos.domain.decision_support_v2.models import (
    AirlineRuleSet,
    AirlineRuleVariant,
    BagInput,
    BagItem,
    DecisionStatus,
    DecisionSupport,
    DimensionOrientation,
    FreshnessState,
    JourneySegment,
    ItemAllowance,
    ItemPlacement,
    JourneyScope,
    SegmentDecision,
)


def _applicability(
    segment: JourneySegment, variant: AirlineRuleVariant
) -> tuple[bool | None, tuple[str, ...]]:
    rule = variant.applicability
    if segment.carrier is None:
        return None, ("CARRIER_REQUIRED",)
    if segment.carrier.casefold() != rule.carrier.casefold():
        return False, ("CARRIER_MISMATCH",)
    if rule.operator is not None:
        if segment.operator is None:
            return None, ("OPERATOR_REQUIRED",)
        if segment.operator.casefold() != rule.operator.casefold():
            return False, ("OPERATOR_MISMATCH",)
    if rule.min_seat_count is not None or rule.max_seat_count is not None:
        if segment.seat_count is None:
            return None, ("SEAT_COUNT_REQUIRED",)
        if rule.min_seat_count is not None and segment.seat_count < rule.min_seat_count:
            return False, ("SEAT_COUNT_MISMATCH",)
        if rule.max_seat_count is not None and segment.seat_count > rule.max_seat_count:
            return False, ("SEAT_COUNT_MISMATCH",)
    if rule.fare_classes:
        if segment.fare_class is None:
            return None, ("FARE_CLASS_REQUIRED",)
        if segment.fare_class.casefold() not in {
            value.casefold() for value in rule.fare_classes
        }:
            return False, ("FARE_CLASS_MISMATCH",)
    if rule.required_options:
        if segment.options is None:
            return None, ("OPTIONS_REQUIRED",)
        present = {value.casefold() for value in segment.options}
        if not all(value.casefold() in present for value in rule.required_options):
            return False, ("REQUIRED_OPTION_MISSING",)
    if rule.forbidden_options:
        if segment.options is None:
            return None, ("OPTIONS_REQUIRED",)
        present = {value.casefold() for value in segment.options}
        if any(value.casefold() in present for value in rule.forbidden_options):
            return False, ("FORBIDDEN_OPTION_PRESENT",)
    return True, ()


def _dimensions_pass(bag: BagInput, rule: AirlineRuleVariant) -> bool:
    return _edges_pass(
        bag.external_dimensions_cm.as_tuple(),
        rule.dimension_edges_cm.as_tuple(),
        rule.orientation,
    )


def _non_item_dimension_checks(
    bag: BagInput, rule: AirlineRuleVariant
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Check every identified carry-on item for rules without item slots."""

    if bag.carry_on_bag_count == 0:
        return (), ()
    if bag.items is None:
        reasons: list[str] = []
        if not _dimensions_pass(bag, rule):
            reasons.append("DIMENSION_EDGE_EXCEEDED")
        if (
            rule.sum_edges_cm is not None
            and bag.external_dimensions_cm.sum_cm > rule.sum_edges_cm
        ):
            reasons.append("DIMENSION_SUM_EXCEEDED")
        return tuple(reasons), ()

    carry_items = tuple(
        item
        for item in bag.items
        if item.placement in {ItemPlacement.MAIN, ItemPlacement.OVERHEAD}
    )
    unresolved: list[str] = []
    if any(item.placement is None for item in bag.items) or len(carry_items) != (
        bag.carry_on_bag_count
    ):
        unresolved.append("CARRY_ON_ITEM_ROLE_REQUIRED")
    reasons = []
    for item in carry_items:
        if not _edges_pass(
            item.external_dimensions_cm.as_tuple(),
            rule.dimension_edges_cm.as_tuple(),
            rule.orientation,
        ):
            reasons.append("DIMENSION_EDGE_EXCEEDED")
        if (
            rule.sum_edges_cm is not None
            and item.external_dimensions_cm.sum_cm > rule.sum_edges_cm
        ):
            reasons.append("DIMENSION_SUM_EXCEEDED")
        if rule.appendages_included and item.appendages_included is not True:
            unresolved.append("APPENDAGES_INCLUSION_UNCONFIRMED")
    return tuple(sorted(set(reasons))), tuple(sorted(set(unresolved)))


def _edges_pass(
    actual: tuple[Decimal, Decimal, Decimal],
    limit: tuple[Decimal, Decimal, Decimal],
    orientation: DimensionOrientation,
) -> bool:
    candidates = (
        tuple(permutations(actual))
        if orientation is DimensionOrientation.PERMUTABLE
        else (actual,)
    )
    return any(
        all(edge <= maximum for edge, maximum in zip(candidate, limit))
        for candidate in candidates
    )


def _item_against_slot(item: BagItem, allowance: ItemAllowance) -> DecisionStatus:
    failed = False
    unknown = False
    if item.placement is None:
        unknown = True
    elif item.placement is not allowance.placement:
        failed = True
    if allowance.dimension_edges_cm is not None:
        if not _edges_pass(
            item.external_dimensions_cm.as_tuple(),
            allowance.dimension_edges_cm.as_tuple(),
            allowance.orientation,
        ):
            failed = True
        if (
            allowance.includes_wheels_and_handles is True
            and item.appendages_included is not True
        ):
            unknown = True
    if allowance.max_weight_kg is not None and item.weight_kg > allowance.max_weight_kg:
        failed = True
    if allowance.fit_requirement is not None:
        if allowance.fit_requirement in item.rejected_fit:
            failed = True
        elif allowance.fit_requirement not in item.confirmed_fit:
            unknown = True
    if failed:
        return DecisionStatus.FAIL
    if unknown:
        return DecisionStatus.UNKNOWN
    return DecisionStatus.PASS


def _item_allowance_status(bag: BagInput, rule: AirlineRuleVariant) -> DecisionStatus:
    if not rule.item_allowances:
        return DecisionStatus.PASS
    item_count = bag.carry_on_bag_count + bag.personal_item_count
    if item_count > len(rule.item_allowances):
        return DecisionStatus.FAIL
    if bag.items is None:
        return DecisionStatus.UNKNOWN
    assignment_statuses: list[DecisionStatus] = []
    for slots in permutations(rule.item_allowances, len(bag.items)):
        statuses = tuple(
            _item_against_slot(item, slot)
            for item, slot in zip(bag.items, slots, strict=True)
        )
        if all(status is DecisionStatus.PASS for status in statuses):
            return DecisionStatus.PASS
        if any(status is DecisionStatus.UNKNOWN for status in statuses) and not any(
            status is DecisionStatus.FAIL for status in statuses
        ):
            assignment_statuses.append(DecisionStatus.UNKNOWN)
        else:
            assignment_statuses.append(DecisionStatus.FAIL)
    if DecisionStatus.UNKNOWN in assignment_statuses:
        return DecisionStatus.UNKNOWN
    return DecisionStatus.FAIL


def _evaluate_against_rule(
    segment: JourneySegment,
    bag: BagInput,
    rule_set: AirlineRuleSet,
    variant: AirlineRuleVariant,
) -> SegmentDecision:
    reasons: list[str] = []
    unresolved: list[str] = []
    if rule_set.source_status in {
        FreshnessState.SOFT_STALE,
        FreshnessState.HARD_STALE,
    }:
        return SegmentDecision(
            segment.segment_id,
            DecisionStatus.STALE,
            (f"RULE_SOURCE_{rule_set.source_status.value}",),
            (rule_set.source_id,),
            rule_set.checked_at,
            variant.variant_id,
        )
    if rule_set.source_status in {
        FreshnessState.UNKNOWN,
        FreshnessState.UNAVAILABLE,
    }:
        return SegmentDecision(
            segment.segment_id,
            DecisionStatus.UNKNOWN,
            (f"RULE_SOURCE_{rule_set.source_status.value}",),
            (rule_set.source_id,),
            rule_set.checked_at,
            variant.variant_id,
        )
    if rule_set.source_status is FreshnessState.REJECTED:
        return SegmentDecision(
            segment.segment_id,
            DecisionStatus.BLOCKED,
            ("RULE_SOURCE_REJECTED",),
            (rule_set.source_id,),
            rule_set.checked_at,
            variant.variant_id,
        )
    if (
        rule_set.recheck_required_before_use
        or segment.departure_at >= rule_set.source_next_review_at
    ):
        return SegmentDecision(
            segment.segment_id,
            DecisionStatus.STALE,
            ("RULE_RECHECK_REQUIRED_BEFORE_DEPARTURE",),
            (rule_set.source_id,),
            rule_set.checked_at,
            variant.variant_id,
        )
    if bag.appendages_included is not True and variant.appendages_included:
        unresolved.append("APPENDAGES_INCLUSION_UNCONFIRMED")
    if bag.expanded is None:
        unresolved.append("EXPANSION_STATE_UNCONFIRMED")
    if bag.carry_on_bag_count > variant.carry_on_bag_count:
        reasons.append("CARRY_ON_COUNT_EXCEEDED")
    if bag.personal_item_count > variant.personal_item_count:
        reasons.append("PERSONAL_ITEM_COUNT_EXCEEDED")
    if variant.item_allowances:
        if bag.carry_on_bag_count + bag.personal_item_count > len(
            variant.item_allowances
        ):
            reasons.append("TOTAL_ITEM_COUNT_EXCEEDED")
    else:
        dimension_reasons, dimension_unresolved = _non_item_dimension_checks(
            bag, variant
        )
        reasons.extend(dimension_reasons)
        unresolved.extend(dimension_unresolved)
    if (
        variant.total_weight_kg is not None
        and bag.combined_weight_kg > variant.total_weight_kg
    ):
        reasons.append("TOTAL_WEIGHT_EXCEEDED")
    item_status = _item_allowance_status(bag, variant)
    if item_status is DecisionStatus.FAIL:
        reasons.append("ITEM_ALLOWANCE_FAILED")
    elif item_status is DecisionStatus.UNKNOWN:
        unresolved.append("ITEM_DETAILS_OR_FIT_CONFIRMATION_REQUIRED")
    if variant.max_per_item_weight_kg is not None and not variant.item_allowances:
        if bag.item_weights_kg is not None:
            if any(
                weight > variant.max_per_item_weight_kg
                for weight in bag.item_weights_kg
            ):
                reasons.append("PER_ITEM_WEIGHT_EXCEEDED")
        elif bag.combined_weight_kg > variant.max_per_item_weight_kg:
            unresolved.append("PER_ITEM_WEIGHT_REQUIRED")
    if not reasons and unresolved:
        return SegmentDecision(
            segment.segment_id,
            DecisionStatus.UNKNOWN,
            tuple(unresolved),
            (rule_set.source_id,),
            rule_set.checked_at,
            variant.variant_id,
        )
    return SegmentDecision(
        segment.segment_id,
        DecisionStatus.FAIL if reasons else DecisionStatus.PASS,
        tuple(reasons) if reasons else ("ALL_CONFIRMED_CONDITIONS_PASS",),
        (rule_set.source_id,),
        rule_set.checked_at,
        variant.variant_id,
    )


def evaluate_segment(
    segment: JourneySegment,
    bag: BagInput,
    rule_sets: tuple[AirlineRuleSet, ...],
) -> SegmentDecision:
    """Resolve exactly one variant, never inferring carrier/applicability."""

    if segment.carrier is None:
        return SegmentDecision(
            segment.segment_id,
            DecisionStatus.UNKNOWN,
            ("CARRIER_REQUIRED",),
            (),
            None,
            None,
        )
    effective = tuple(
        rule_set
        for rule_set in rule_sets
        if rule_set.carrier.casefold() == segment.carrier.casefold()
        and (rule_set.effective_from or rule_set.observed_applicable_from)
        <= segment.departure_at
        and (
            rule_set.effective_to is None
            or segment.departure_at < rule_set.effective_to
        )
    )
    if segment.journey_scope is None and any(
        rule_set.journey_scope is not JourneyScope.ALL for rule_set in effective
    ):
        return SegmentDecision(
            segment.segment_id,
            DecisionStatus.UNKNOWN,
            ("JOURNEY_SCOPE_REQUIRED",),
            tuple(sorted({rule_set.source_id for rule_set in effective})),
            min((rule_set.checked_at for rule_set in effective), default=None),
            None,
        )
    scope_matched = tuple(
        rule_set
        for rule_set in effective
        if rule_set.journey_scope is JourneyScope.ALL
        or rule_set.journey_scope is segment.journey_scope
    )
    if effective and not scope_matched:
        return SegmentDecision(
            segment.segment_id,
            DecisionStatus.NO_MATCH,
            ("JOURNEY_SCOPE_MISMATCH",),
            tuple(sorted({rule_set.source_id for rule_set in effective})),
            min((rule_set.checked_at for rule_set in effective), default=None),
            None,
        )
    effective = scope_matched
    if not effective:
        # An empty recorded resolution is absence of evidence for this
        # carrier/date, not evidence that the bag is inapplicable.  In
        # particular, rules observed without a published effective date
        # cannot be projected backwards before their capture boundary.
        return SegmentDecision(
            segment.segment_id,
            DecisionStatus.UNKNOWN,
            ("RULE_DATA_UNAVAILABLE_FOR_SEGMENT",),
            (),
            None,
            None,
        )
    matches: list[tuple[AirlineRuleSet, AirlineRuleVariant]] = []
    unresolved_reasons: set[str] = set()
    for rule_set in effective:
        for variant in rule_set.variants:
            applies, reasons = _applicability(segment, variant)
            if applies is True:
                matches.append((rule_set, variant))
            elif applies is None:
                unresolved_reasons.update(reasons)
    if len(matches) > 1:
        return SegmentDecision(
            segment.segment_id,
            DecisionStatus.BLOCKED,
            ("AMBIGUOUS_RULE_VARIANTS",),
            tuple(sorted({item[0].source_id for item in matches})),
            min(item[0].checked_at for item in matches),
            None,
        )
    if matches and unresolved_reasons:
        return SegmentDecision(
            segment.segment_id,
            DecisionStatus.UNKNOWN,
            tuple(sorted(unresolved_reasons)),
            tuple(
                sorted(
                    {item[0].source_id for item in matches}
                    | {rule_set.source_id for rule_set in effective}
                )
            ),
            min((rule_set.checked_at for rule_set in effective), default=None),
            None,
        )
    if not matches:
        return SegmentDecision(
            segment.segment_id,
            DecisionStatus.UNKNOWN if unresolved_reasons else DecisionStatus.NO_MATCH,
            tuple(sorted(unresolved_reasons)) or ("NO_APPLICABLE_RULE",),
            tuple(sorted({rule_set.source_id for rule_set in effective})),
            min((rule_set.checked_at for rule_set in effective), default=None),
            None,
        )
    rule_set, variant = matches[0]
    return _evaluate_against_rule(segment, bag, rule_set, variant)


def evaluate_journey(
    segments: tuple[JourneySegment, ...],
    bag: BagInput,
    rule_sets: tuple[AirlineRuleSet, ...],
) -> DecisionSupport:
    """Use every segment; a single known violation fails the whole journey."""

    if not segments:
        return DecisionSupport(
            DecisionStatus.UNKNOWN,
            (),
            ("JOURNEY_SEGMENT_REQUIRED",),
            (),
            None,
        )
    results = tuple(evaluate_segment(segment, bag, rule_sets) for segment in segments)
    return aggregate_segment_decisions(results)


def aggregate_segment_decisions(
    results: tuple[SegmentDecision, ...],
) -> DecisionSupport:
    """Aggregate already-resolved segments with known failures taking precedence."""

    if not results:
        return DecisionSupport(
            DecisionStatus.UNKNOWN,
            (),
            ("JOURNEY_SEGMENT_REQUIRED",),
            (),
            None,
        )
    statuses = {result.status for result in results}
    if DecisionStatus.FAIL in statuses:
        overall = DecisionStatus.FAIL
    elif DecisionStatus.BLOCKED in statuses:
        overall = DecisionStatus.BLOCKED
    elif DecisionStatus.STALE in statuses:
        overall = DecisionStatus.STALE
    elif DecisionStatus.UNKNOWN in statuses:
        overall = DecisionStatus.UNKNOWN
    elif DecisionStatus.NO_MATCH in statuses:
        overall = DecisionStatus.NO_MATCH
    else:
        overall = DecisionStatus.PASS
    return DecisionSupport(
        overall,
        results,
        tuple(sorted({reason for result in results for reason in result.reason_codes})),
        tuple(sorted({source for result in results for source in result.source_ids})),
        min(
            (result.checked_at for result in results if result.checked_at is not None),
            default=None,
        ),
    )


__all__ = ["aggregate_segment_decisions", "evaluate_journey", "evaluate_segment"]

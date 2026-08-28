from datetime import datetime
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from raos.adapters.decision_support_v2.recorded_airline import RecordedRuleRegistry
from raos.application.decision_support_v2.checker import CarryOnChecker
from raos.domain.decision_support_v2.decision import evaluate_journey
from raos.domain.decision_support_v2.models import (
    BagInput,
    BagItem,
    DecisionStatus,
    DimensionEdges,
    DimensionOrientation,
    FreshnessState,
    ItemAllowance,
    ItemPlacement,
    JourneySegment,
    JourneyScope,
    RuleApplicability,
)


ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "changes/raos-v2/phase-2/fixtures/recorded-airline-rules.v2.json"
JST = datetime.fromisoformat


def _bag(
    dimensions: tuple[str, str, str] = ("55", "35", "25"),
    *,
    weight: str = "10",
) -> BagInput:
    return BagInput(
        DimensionEdges(*(Decimal(value) for value in dimensions)),
        Decimal(weight),
        appendages_included=True,
        expanded=False,
    )


def _segment(
    segment_id: str = "S1",
    carrier: str | None = "ANA",
    *,
    seat_count: int | None = 100,
    operator: str | None = None,
    options: tuple[str, ...] | None = (),
    journey_scope: JourneyScope | None = JourneyScope.DOMESTIC,
    departure: str = "2026-09-01T09:00:00+09:00",
) -> JourneySegment:
    return JourneySegment(
        segment_id,
        carrier,
        JST(departure),
        journey_scope=journey_scope,
        operator=operator,
        seat_count=seat_count,
        options=options,
    )


def test_t_v2_020_exact_boundary_passes_with_source() -> None:
    registry = RecordedRuleRegistry.from_file(RULES)
    result = CarryOnChecker(registry).check(segments=(_segment(),), bag=_bag())
    assert result.status is DecisionStatus.PASS
    assert result.source_ids == ("SRC-V2-ANA-CARRY-ON",)
    assert result.segments[0].rule_variant_id == "ANA-100-SEATS-OR-MORE"


def test_domestic_rule_requires_explicit_matching_journey_scope() -> None:
    registry = RecordedRuleRegistry.from_file(RULES)
    missing = CarryOnChecker(registry).check(
        segments=(_segment(journey_scope=None),), bag=_bag()
    )
    assert missing.status is DecisionStatus.UNKNOWN
    assert missing.reason_codes == ("JOURNEY_SCOPE_REQUIRED",)

    international = CarryOnChecker(registry).check(
        segments=(_segment(journey_scope=JourneyScope.INTERNATIONAL),), bag=_bag()
    )
    assert international.status is DecisionStatus.NO_MATCH
    assert international.reason_codes == ("JOURNEY_SCOPE_MISMATCH",)


def test_all_scope_rule_does_not_require_domestic_or_international_guess() -> None:
    registry = RecordedRuleRegistry.from_file(RULES)
    result = CarryOnChecker(registry).check(
        segments=(
            _segment(
                carrier="PEACH",
                seat_count=None,
                journey_scope=None,
            ),
        ),
        bag=_bag(weight="7"),
    )
    assert result.status is DecisionStatus.PASS


def test_t_v2_021_any_edge_violation_fails() -> None:
    registry = RecordedRuleRegistry.from_file(RULES)
    result = CarryOnChecker(registry).check(
        segments=(_segment(),), bag=_bag(("55.01", "35", "25"))
    )
    assert result.status is DecisionStatus.FAIL
    assert "DIMENSION_EDGE_EXCEEDED" in result.reason_codes


def test_non_item_rule_checks_role_identified_main_bag_not_first_personal_item() -> (
    None
):
    registry = RecordedRuleRegistry.from_file(RULES)
    personal = BagItem(
        "PERSONAL-FIRST",
        DimensionEdges(Decimal("20"), Decimal("20"), Decimal("10")),
        Decimal("2"),
        True,
        placement=ItemPlacement.UNDERSEAT,
    )
    oversized_main = BagItem(
        "MAIN-SECOND",
        DimensionEdges(Decimal("56"), Decimal("40"), Decimal("25")),
        Decimal("8"),
        True,
        placement=ItemPlacement.MAIN,
    )
    bag = BagInput(
        personal.external_dimensions_cm,
        Decimal("10"),
        items=(personal, oversized_main),
        appendages_included=True,
        expanded=False,
    )
    result = CarryOnChecker(registry).check(segments=(_segment(),), bag=bag)
    assert result.status is DecisionStatus.FAIL
    assert "DIMENSION_EDGE_EXCEEDED" in result.reason_codes


def test_unknown_item_role_cannot_make_non_item_rule_pass() -> None:
    registry = RecordedRuleRegistry.from_file(RULES)
    personal = BagItem(
        "PERSONAL-FIRST",
        DimensionEdges(Decimal("20"), Decimal("20"), Decimal("10")),
        Decimal("2"),
        True,
        placement=ItemPlacement.UNDERSEAT,
    )
    unknown_role = BagItem(
        "UNKNOWN-SECOND",
        DimensionEdges(Decimal("55"), Decimal("40"), Decimal("25")),
        Decimal("8"),
        True,
        placement=None,
    )
    bag = BagInput(
        personal.external_dimensions_cm,
        Decimal("10"),
        items=(personal, unknown_role),
        appendages_included=True,
        expanded=False,
    )
    result = CarryOnChecker(registry).check(segments=(_segment(),), bag=bag)
    assert result.status is DecisionStatus.UNKNOWN
    assert "CARRY_ON_ITEM_ROLE_REQUIRED" in result.reason_codes


def test_known_weight_violation_fails_even_when_other_inputs_are_unconfirmed() -> None:
    registry = RecordedRuleRegistry.from_file(RULES)
    bag = BagInput(
        DimensionEdges(Decimal("55"), Decimal("40"), Decimal("25")),
        Decimal("10.01"),
        appendages_included=None,
        expanded=None,
    )
    result = CarryOnChecker(registry).check(segments=(_segment(),), bag=bag)
    assert result.status is DecisionStatus.FAIL
    assert "TOTAL_WEIGHT_EXCEEDED" in result.reason_codes


def test_t_v2_022_permutation_only_when_rule_allows() -> None:
    registry = RecordedRuleRegistry.from_file(RULES)
    ana = CarryOnChecker(registry).check(
        segments=(_segment(),), bag=_bag(("35", "25", "55"))
    )
    jetstar_main = BagItem(
        "MAIN",
        DimensionEdges(Decimal("36"), Decimal("23"), Decimal("56")),
        Decimal("5"),
        True,
        placement=ItemPlacement.MAIN,
    )
    jetstar_personal = BagItem(
        "PERSONAL",
        DimensionEdges(Decimal("30"), Decimal("20"), Decimal("10")),
        Decimal("2"),
        True,
        confirmed_fit=("UNDERSEAT",),
        placement=ItemPlacement.UNDERSEAT,
    )
    jetstar = CarryOnChecker(registry).check(
        segments=(
            _segment(
                carrier="JETSTAR_JAPAN",
                seat_count=None,
                operator="JETSTAR_JAPAN",
            ),
        ),
        bag=BagInput(
            jetstar_main.external_dimensions_cm,
            Decimal("7"),
            items=(jetstar_main, jetstar_personal),
            appendages_included=True,
            expanded=False,
        ),
    )
    assert ana.status is DecisionStatus.PASS
    assert jetstar.status is DecisionStatus.FAIL


def test_all_segments_use_strict_common_outcome() -> None:
    registry = RecordedRuleRegistry.from_file(RULES)
    result = CarryOnChecker(registry).check(
        segments=(
            _segment("LARGE", seat_count=100),
            _segment("SMALL", seat_count=99),
        ),
        bag=_bag(),
    )
    assert result.status is DecisionStatus.FAIL
    assert [segment.status for segment in result.segments] == [
        DecisionStatus.PASS,
        DecisionStatus.FAIL,
    ]


@pytest.mark.parametrize(
    ("segment", "reason"),
    [
        (_segment(carrier=None), "CARRIER_REQUIRED"),
        (_segment(seat_count=None), "SEAT_COUNT_REQUIRED"),
    ],
)
def test_missing_applicability_is_unknown(segment: JourneySegment, reason: str) -> None:
    registry = RecordedRuleRegistry.from_file(RULES)
    result = CarryOnChecker(registry).check(segments=(segment,), bag=_bag())
    assert result.status is DecisionStatus.UNKNOWN
    assert reason in result.reason_codes


def test_future_jetstar_variant_is_effective_date_and_option_bound() -> None:
    registry = RecordedRuleRegistry.from_file(RULES)
    before = _segment(
        carrier="JETSTAR_AIRWAYS",
        operator="JETSTAR_AIRWAYS",
        seat_count=None,
        departure="2027-02-01T09:00:00+09:00",
    )
    base = _segment(
        carrier="JETSTAR_AIRWAYS",
        operator="JETSTAR_AIRWAYS",
        seat_count=None,
        departure="2027-02-02T09:00:00+09:00",
    )
    priority = _segment(
        carrier="JETSTAR_AIRWAYS",
        operator="JETSTAR_AIRWAYS",
        seat_count=None,
        options=("PRIORITY-CARRY-ON",),
        departure="2027-02-02T09:00:00+09:00",
    )
    current_main = BagItem(
        "MAIN",
        DimensionEdges(Decimal("55"), Decimal("35"), Decimal("23")),
        Decimal("5"),
        True,
        placement=ItemPlacement.MAIN,
    )
    current_personal = BagItem(
        "PERSONAL",
        DimensionEdges(Decimal("30"), Decimal("20"), Decimal("10")),
        Decimal("2"),
        True,
        confirmed_fit=("UNDERSEAT",),
        placement=ItemPlacement.UNDERSEAT,
    )
    current_bag = BagInput(
        current_main.external_dimensions_cm,
        Decimal("7"),
        items=(current_main, current_personal),
        appendages_included=True,
        expanded=False,
    )
    underseat = BagItem(
        "UNDERSEAT",
        DimensionEdges(Decimal("40"), Decimal("30"), Decimal("20")),
        Decimal("10"),
        True,
        placement=ItemPlacement.UNDERSEAT,
    )
    base_bag = BagInput(
        underseat.external_dimensions_cm,
        Decimal("10"),
        carry_on_bag_count=0,
        personal_item_count=1,
        items=(underseat,),
        appendages_included=True,
        expanded=False,
    )
    overhead = BagItem(
        "OVERHEAD",
        DimensionEdges(Decimal("56"), Decimal("36"), Decimal("23")),
        Decimal("10"),
        True,
        placement=ItemPlacement.OVERHEAD,
    )
    priority_bag = BagInput(
        overhead.external_dimensions_cm,
        Decimal("20"),
        carry_on_bag_count=1,
        personal_item_count=1,
        items=(overhead, underseat),
        appendages_included=True,
        expanded=False,
    )
    before_result = CarryOnChecker(registry).check(segments=(before,), bag=current_bag)
    assert before_result.status is DecisionStatus.STALE
    assert before_result.segments[0].rule_variant_id is not None
    assert before_result.segments[0].rule_variant_id.startswith(
        "JETSTAR-AIRWAYS-CURRENT"
    )
    assert "RULE_RECHECK_REQUIRED_BEFORE_DEPARTURE" in before_result.reason_codes
    assert (
        CarryOnChecker(registry).check(segments=(base,), bag=base_bag).status
        is DecisionStatus.STALE
    )
    assert (
        CarryOnChecker(registry).check(segments=(priority,), bag=priority_bag).status
        is DecisionStatus.STALE
    )

    current_rule = registry.resolve(before, at=before.departure_at)[0]
    future_rule = registry.resolve(base, at=base.departure_at)[0]
    revalidated_current = replace(
        current_rule,
        source_next_review_at=datetime.fromisoformat("2027-02-02T00:00:00+09:00"),
    )
    revalidated_future = replace(
        future_rule,
        checked_at=datetime.fromisoformat("2027-02-02T00:00:00+09:00"),
        source_next_review_at=datetime.fromisoformat("2027-03-04T00:00:00+09:00"),
        recheck_required_before_use=False,
    )
    assert (
        CarryOnChecker(RecordedRuleRegistry((revalidated_current,)))
        .check(segments=(before,), bag=current_bag)
        .status
        is DecisionStatus.PASS
    )
    revalidated_registry = RecordedRuleRegistry((revalidated_future,))
    assert (
        CarryOnChecker(revalidated_registry)
        .check(segments=(base,), bag=base_bag)
        .status
        is DecisionStatus.PASS
    )
    assert (
        CarryOnChecker(revalidated_registry)
        .check(segments=(priority,), bag=priority_bag)
        .status
        is DecisionStatus.PASS
    )
    oversized = BagItem(
        "UNDERSEAT-OVERSIZED",
        DimensionEdges(Decimal("40.01"), Decimal("30"), Decimal("20")),
        Decimal("10"),
        True,
        placement=ItemPlacement.UNDERSEAT,
    )
    overweight = BagItem(
        "UNDERSEAT-OVERWEIGHT",
        DimensionEdges(Decimal("40"), Decimal("30"), Decimal("20")),
        Decimal("10.01"),
        True,
        placement=ItemPlacement.UNDERSEAT,
    )
    for invalid_item in (oversized, overweight):
        invalid_bag = BagInput(
            invalid_item.external_dimensions_cm,
            invalid_item.weight_kg,
            carry_on_bag_count=0,
            personal_item_count=1,
            items=(invalid_item,),
            appendages_included=True,
            expanded=False,
        )
        assert (
            CarryOnChecker(revalidated_registry)
            .check(segments=(base,), bag=invalid_bag)
            .status
            is DecisionStatus.FAIL
        )


def test_jetstar_effective_to_is_exclusive_at_2027_boundary() -> None:
    registry = RecordedRuleRegistry.from_file(RULES)
    before = _segment(
        carrier="JETSTAR_AIRWAYS",
        operator="JETSTAR_AIRWAYS",
        seat_count=None,
        departure="2027-02-01T23:59:59.999999+09:00",
    )
    boundary = _segment(
        carrier="JETSTAR_AIRWAYS",
        operator="JETSTAR_AIRWAYS",
        seat_count=None,
        departure="2027-02-02T00:00:00+09:00",
    )
    assert [
        rule.rule_set_id for rule in registry.resolve(before, at=before.departure_at)
    ] == ["AIR-JETSTAR-AIRWAYS-CURRENT-TO-2027-02-02"]
    assert [
        rule.rule_set_id
        for rule in registry.resolve(boundary, at=boundary.departure_at)
    ] == ["AIR-JETSTAR-AIRWAYS-2027-02-02"]


def test_unpublished_effective_date_uses_observed_lower_bound_only() -> None:
    registry = RecordedRuleRegistry.from_file(RULES)
    before_capture = _segment(
        carrier="ANA",
        seat_count=100,
        departure="2026-08-28T06:41:51+09:00",
    )
    assert registry.resolve(before_capture, at=before_capture.departure_at) == ()
    decision = CarryOnChecker(registry).check(
        segments=(before_capture,),
        bag=_bag(),
    )
    assert decision.status is DecisionStatus.UNKNOWN
    assert decision.reason_codes == ("RULE_DATA_UNAVAILABLE_FOR_SEGMENT",)


@pytest.mark.parametrize(
    "departure",
    ["2026-09-27T06:41:52+09:00", "2030-01-01T00:00:00+09:00"],
)
def test_rule_never_passes_at_or_after_source_next_review(departure: str) -> None:
    registry = RecordedRuleRegistry.from_file(RULES)
    result = CarryOnChecker(registry).check(
        segments=(_segment(departure=departure),), bag=_bag()
    )
    assert result.status is DecisionStatus.STALE
    assert "RULE_RECHECK_REQUIRED_BEFORE_DEPARTURE" in result.reason_codes


def test_exact_decimal_rejects_binary_float() -> None:
    with pytest.raises(TypeError):
        DimensionEdges(55.0, Decimal("40"), Decimal("25"))  # type: ignore[arg-type]


def test_empty_journey_never_passes() -> None:
    result = evaluate_journey((), _bag(), ())
    assert result.status is DecisionStatus.UNKNOWN


@pytest.mark.parametrize(
    "bag",
    [
        lambda: BagInput(
            DimensionEdges(Decimal("1"), Decimal("1"), Decimal("1")),
            Decimal("1"),
            carry_on_bag_count=0,
            personal_item_count=0,
        ),
        lambda: BagInput(
            DimensionEdges(Decimal("1"), Decimal("1"), Decimal("1")),
            Decimal("0"),
        ),
    ],
)
def test_empty_or_zero_weight_bag_is_rejected(bag: object) -> None:
    with pytest.raises(ValueError):
        bag()  # type: ignore[operator]


def test_unconfirmed_expansion_state_is_unknown() -> None:
    registry = RecordedRuleRegistry.from_file(RULES)
    bag = BagInput(
        DimensionEdges(Decimal("55"), Decimal("35"), Decimal("25")),
        Decimal("10"),
        appendages_included=True,
    )
    result = CarryOnChecker(registry).check(segments=(_segment(),), bag=bag)
    assert result.status is DecisionStatus.UNKNOWN
    assert "EXPANSION_STATE_UNCONFIRMED" in result.reason_codes


def test_unconfirmed_option_state_is_unknown_when_rule_depends_on_it() -> None:
    registry = RecordedRuleRegistry.from_file(RULES)
    segment = _segment(
        carrier="JETSTAR_JAPAN",
        seat_count=None,
        operator="JETSTAR_JAPAN",
        options=None,
    )
    result = CarryOnChecker(registry).check(
        segments=(segment,), bag=_bag(("56", "36", "23"), weight="7")
    )
    assert result.status is DecisionStatus.UNKNOWN
    assert "OPTIONS_REQUIRED" in result.reason_codes


def test_jetstar_14kg_option_requires_and_enforces_per_item_weight() -> None:
    registry = RecordedRuleRegistry.from_file(RULES)
    segment = _segment(
        carrier="JETSTAR_JAPAN",
        seat_count=None,
        operator="JETSTAR_JAPAN",
        options=("PLUS-14KG",),
    )
    dimensions = DimensionEdges(Decimal("56"), Decimal("36"), Decimal("23"))
    personal_dimensions = DimensionEdges(Decimal("30"), Decimal("20"), Decimal("10"))
    unknown = CarryOnChecker(registry).check(
        segments=(segment,),
        bag=BagInput(
            dimensions,
            Decimal("14"),
            appendages_included=True,
            expanded=False,
        ),
    )
    failed_items = (
        BagItem(
            "MAIN",
            dimensions,
            Decimal("11"),
            True,
            placement=ItemPlacement.MAIN,
        ),
        BagItem(
            "PERSONAL",
            personal_dimensions,
            Decimal("3"),
            True,
            confirmed_fit=("UNDERSEAT",),
            placement=ItemPlacement.UNDERSEAT,
        ),
    )
    passed_items = (
        BagItem(
            "MAIN",
            dimensions,
            Decimal("10"),
            True,
            placement=ItemPlacement.MAIN,
        ),
        BagItem(
            "PERSONAL",
            personal_dimensions,
            Decimal("4"),
            True,
            confirmed_fit=("UNDERSEAT",),
            placement=ItemPlacement.UNDERSEAT,
        ),
    )
    failed = CarryOnChecker(registry).check(
        segments=(segment,),
        bag=BagInput(
            dimensions,
            Decimal("14"),
            items=failed_items,
            appendages_included=True,
            expanded=False,
        ),
    )
    passed = CarryOnChecker(registry).check(
        segments=(segment,),
        bag=BagInput(
            dimensions,
            Decimal("14"),
            items=passed_items,
            appendages_included=True,
            expanded=False,
        ),
    )
    assert unknown.status is DecisionStatus.UNKNOWN
    assert "ITEM_DETAILS_OR_FIT_CONFIRMATION_REQUIRED" in unknown.reason_codes
    assert failed.status is DecisionStatus.FAIL
    assert "ITEM_ALLOWANCE_FAILED" in failed.reason_codes
    assert passed.status is DecisionStatus.PASS


def test_current_jetstar_personal_underseat_confirmation_is_required() -> None:
    registry = RecordedRuleRegistry.from_file(RULES)
    segment = _segment(
        carrier="JETSTAR_JAPAN",
        seat_count=None,
        operator="JETSTAR_JAPAN",
        options=(),
    )
    main = BagItem(
        "MAIN",
        DimensionEdges(Decimal("55"), Decimal("35"), Decimal("23")),
        Decimal("5"),
        True,
        placement=ItemPlacement.MAIN,
    )
    personal = BagItem(
        "PERSONAL",
        DimensionEdges(Decimal("30"), Decimal("20"), Decimal("10")),
        Decimal("2"),
        True,
        placement=ItemPlacement.UNDERSEAT,
    )
    result = CarryOnChecker(registry).check(
        segments=(segment,),
        bag=BagInput(
            main.external_dimensions_cm,
            Decimal("7"),
            items=(main, personal),
            appendages_included=True,
            expanded=False,
        ),
    )
    assert result.status is DecisionStatus.UNKNOWN
    assert "ITEM_DETAILS_OR_FIT_CONFIRMATION_REQUIRED" in result.reason_codes


def test_current_jetstar_rejected_underseat_fit_is_known_failure() -> None:
    registry = RecordedRuleRegistry.from_file(RULES)
    segment = _segment(
        carrier="JETSTAR_JAPAN",
        seat_count=None,
        operator="JETSTAR_JAPAN",
        options=(),
    )
    main = BagItem(
        "MAIN",
        DimensionEdges(Decimal("55"), Decimal("35"), Decimal("23")),
        Decimal("5"),
        True,
        placement=ItemPlacement.MAIN,
    )
    personal = BagItem(
        "PERSONAL",
        DimensionEdges(Decimal("30"), Decimal("20"), Decimal("10")),
        Decimal("2"),
        True,
        rejected_fit=("UNDERSEAT",),
        placement=ItemPlacement.UNDERSEAT,
    )
    result = CarryOnChecker(registry).check(
        segments=(segment,),
        bag=BagInput(
            main.external_dimensions_cm,
            Decimal("7"),
            items=(main, personal),
            appendages_included=True,
            expanded=False,
        ),
    )
    assert result.status is DecisionStatus.FAIL
    assert "ITEM_ALLOWANCE_FAILED" in result.reason_codes


@pytest.mark.parametrize(
    ("source_status", "expected"),
    [
        ("SOFT_STALE", DecisionStatus.STALE),
        ("HARD_STALE", DecisionStatus.STALE),
        ("UNKNOWN", DecisionStatus.UNKNOWN),
        ("UNAVAILABLE", DecisionStatus.UNKNOWN),
        ("REJECTED", DecisionStatus.BLOCKED),
    ],
)
def test_nonfresh_rule_source_never_passes(
    source_status: str, expected: DecisionStatus
) -> None:
    registry = RecordedRuleRegistry.from_file(RULES)
    ana = registry.resolve(
        _segment(), at=datetime.fromisoformat("2026-09-01T09:00:00+09:00")
    )[0]
    mutated = replace(ana, source_status=FreshnessState(source_status))
    result = CarryOnChecker(RecordedRuleRegistry((mutated,))).check(
        segments=(_segment(),), bag=_bag()
    )
    assert result.status is expected


def test_item_role_counts_cannot_relabel_two_carry_on_items_as_underseat() -> None:
    dimensions = DimensionEdges(Decimal("40"), Decimal("30"), Decimal("20"))
    items = (
        BagItem(
            "FIRST",
            dimensions,
            Decimal("5"),
            True,
            placement=ItemPlacement.MAIN,
        ),
        BagItem(
            "SECOND",
            dimensions,
            Decimal("5"),
            True,
            placement=ItemPlacement.MAIN,
        ),
    )
    with pytest.raises(ValueError):
        BagInput(
            dimensions,
            Decimal("10"),
            carry_on_bag_count=1,
            personal_item_count=1,
            items=items,
            appendages_included=True,
            expanded=False,
        )


def test_two_carry_on_items_cannot_consume_personal_underseat_allowance() -> None:
    registry = RecordedRuleRegistry.from_file(RULES)
    dimensions = DimensionEdges(Decimal("40"), Decimal("30"), Decimal("20"))
    items = (
        BagItem(
            "FIRST",
            dimensions,
            Decimal("3.5"),
            True,
            placement=ItemPlacement.MAIN,
        ),
        BagItem(
            "SECOND",
            dimensions,
            Decimal("3.5"),
            True,
            placement=ItemPlacement.MAIN,
        ),
    )
    result = CarryOnChecker(registry).check(
        segments=(
            _segment(
                carrier="JETSTAR_JAPAN",
                seat_count=None,
                operator="JETSTAR_JAPAN",
                options=(),
            ),
        ),
        bag=BagInput(
            dimensions,
            Decimal("7"),
            carry_on_bag_count=2,
            personal_item_count=0,
            items=items,
            appendages_included=True,
            expanded=False,
        ),
    )
    assert result.status is DecisionStatus.FAIL
    assert "CARRY_ON_COUNT_EXCEEDED" in result.reason_codes


def test_exact_variant_plus_unresolved_competitor_is_unknown() -> None:
    registry = RecordedRuleRegistry.from_file(RULES)
    peach = registry.resolve(
        _segment(carrier="PEACH", seat_count=None),
        at=datetime.fromisoformat("2026-09-01T09:00:00+09:00"),
    )[0]
    base = peach.variants[0]
    unresolved = replace(
        base,
        variant_id="PEACH-SEAT-CONDITIONAL",
        applicability=RuleApplicability(carrier="PEACH", min_seat_count=100),
    )
    ambiguous_registry = RecordedRuleRegistry(
        (replace(peach, variants=(base, unresolved)),)
    )
    result = CarryOnChecker(ambiguous_registry).check(
        segments=(_segment(carrier="PEACH", seat_count=None),),
        bag=_bag(("50", "40", "25"), weight="7"),
    )
    assert result.status is DecisionStatus.UNKNOWN
    assert "SEAT_COUNT_REQUIRED" in result.reason_codes


def test_rule_weight_limit_must_be_positive() -> None:
    registry = RecordedRuleRegistry.from_file(RULES)
    rule = registry.resolve(
        _segment(), at=datetime.fromisoformat("2026-09-01T09:00:00+09:00")
    )[0].variants[0]
    with pytest.raises(ValueError):
        replace(rule, total_weight_kg=Decimal("0"))


@pytest.mark.parametrize("value", [Decimal("0"), Decimal("-1"), 1.5])
def test_rule_sum_edge_limit_is_exact_and_positive(value: object) -> None:
    registry = RecordedRuleRegistry.from_file(RULES)
    rule = registry.resolve(
        _segment(), at=datetime.fromisoformat("2026-09-01T09:00:00+09:00")
    )[0].variants[0]
    with pytest.raises((TypeError, ValueError)):
        replace(rule, sum_edges_cm=value)  # type: ignore[arg-type]


def test_item_allowance_constructs_without_unrelated_sum_edge_state() -> None:
    allowance = ItemAllowance(
        slot_id="TEST-SLOT",
        placement=ItemPlacement.OVERHEAD,
        dimension_edges_cm=DimensionEdges(Decimal("56"), Decimal("36"), Decimal("23")),
        orientation=DimensionOrientation.ORDERED,
        includes_wheels_and_handles=True,
        max_weight_kg=Decimal("10"),
    )
    assert allowance.max_weight_kg == Decimal("10")

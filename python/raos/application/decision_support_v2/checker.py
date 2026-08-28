"""Carry-on checker orchestration over a local rule registry."""

from __future__ import annotations

from raos.adapters.decision_support_v2.errors import AdapterError
from raos.domain.decision_support_v2.decision import (
    aggregate_segment_decisions,
    evaluate_segment,
)
from raos.domain.decision_support_v2.models import (
    BagInput,
    DecisionStatus,
    DecisionSupport,
    JourneySegment,
    SegmentDecision,
)
from raos.ports.decision_support_v2.protocols import RuleRegistryPort


class CarryOnChecker:
    __slots__ = ("_registry",)

    def __init__(self, registry: RuleRegistryPort) -> None:
        self._registry = registry

    def check(
        self, *, segments: tuple[JourneySegment, ...], bag: BagInput
    ) -> DecisionSupport:
        decisions: list[SegmentDecision] = []
        for segment in segments:
            try:
                rules = self._registry.resolve(segment, at=segment.departure_at)
            except AdapterError as exc:
                decisions.append(
                    SegmentDecision(
                        segment_id=segment.segment_id,
                        status=DecisionStatus.UNKNOWN,
                        reason_codes=(f"RULE_ADAPTER_{exc.code.value}",),
                        source_ids=(),
                        checked_at=None,
                        rule_variant_id=None,
                    )
                )
            else:
                decisions.append(evaluate_segment(segment, bag, rules))
        return aggregate_segment_decisions(tuple(decisions))


__all__ = ["CarryOnChecker"]

"""Bounded immutable DEV/CI fixtures for ST-1402 safe degradation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn, SupportsIndex, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.freshness.safe_degradation import (
    MAX_RECORDED_SAFE_DEGRADATION_FIXTURES,
    SafeDegradationDecision,
    SafeDegradationFailureCode,
    SafeDegradationRequest,
    decide_safe_degradation,
    fail_safe_degradation,
    snapshot_safe_degradation_request,
)


def _snapshot_decision(candidate: object) -> SafeDegradationDecision:
    snapshot: SafeDegradationDecision | None = None
    matches = False
    if type(candidate) is SafeDegradationDecision:
        try:
            source_fingerprint = candidate.fingerprint
            snapshot = SafeDegradationDecision(
                mode=candidate.mode,
                request_fingerprint=candidate.request_fingerprint,
                freshness_evaluation_fingerprint=(
                    candidate.freshness_evaluation_fingerprint
                ),
                freshness_class_id=candidate.freshness_class_id,
                availability_aggregate=candidate.availability_aggregate,
                actions=candidate.actions,
                notice_code=candidate.notice_code,
                review_action=candidate.review_action,
                recommendation_order_action=candidate.recommendation_order_action,
                renderer_effects=candidate.renderer_effects,
                persistence=candidate.persistence,
                attestation=candidate.attestation,
                can_change_state=candidate.can_change_state,
                publication_authorized=candidate.publication_authorized,
                live_eligible=candidate.live_eligible,
            )
            matches = (
                snapshot == candidate
                and snapshot.fingerprint == source_fingerprint
                and candidate.fingerprint == source_fingerprint
            )
        except Exception:
            matches = False
    if snapshot is None or not matches:
        fail_safe_degradation(SafeDegradationFailureCode.DECISION_MISMATCH)
    return snapshot


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedSafeDegradationFixture:
    request: SafeDegradationRequest
    decision: SafeDegradationDecision

    def __post_init__(self) -> None:
        request: SafeDegradationRequest | None = None
        expected: SafeDegradationDecision | None = None
        matches = False
        if (
            type(self.request) is SafeDegradationRequest
            and type(self.decision) is SafeDegradationDecision
        ):
            try:
                request = snapshot_safe_degradation_request(self.request)
                expected = decide_safe_degradation(request)
                decision = _snapshot_decision(self.decision)
                matches = (
                    decision == expected
                    and decision.fingerprint == expected.fingerprint
                )
            except Exception:
                matches = False
        if request is None or expected is None or not matches:
            fail_safe_degradation(SafeDegradationFailureCode.DECISION_MISMATCH)
        object.__setattr__(self, "request", request)
        object.__setattr__(self, "decision", expected)

    def __repr__(self) -> str:
        return "RecordedSafeDegradationFixture(<redacted-st1402-safe-degradation>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("safe-degradation fixture serialization is not supported")


def _fixture_binding(
    fixture: RecordedSafeDegradationFixture,
) -> tuple[str, str]:
    fixture.__post_init__()
    request = snapshot_safe_degradation_request(fixture.request)
    expected = decide_safe_degradation(request)
    if (
        fixture.decision != expected
        or fixture.decision.fingerprint != expected.fingerprint
    ):
        fail_safe_degradation(SafeDegradationFailureCode.DECISION_MISMATCH)
    return request.fingerprint, expected.fingerprint


@final
class RecordedSafeDegradationAdapter:
    """Return only exact deterministic fixture decisions without state writes."""

    __slots__ = ("_bindings",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        fixture_capacity: int,
        fixtures: tuple[RecordedSafeDegradationFixture, ...],
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or type(fixture_capacity) is not int
            or not 1 <= fixture_capacity <= MAX_RECORDED_SAFE_DEGRADATION_FIXTURES
            or type(fixtures) is not tuple
            or not 1 <= len(fixtures) <= fixture_capacity
            or any(
                type(item) is not RecordedSafeDegradationFixture for item in fixtures
            )
        ):
            fail_safe_degradation()
        bindings: tuple[tuple[str, str], ...] = ()
        try:
            bindings = tuple(_fixture_binding(fixture) for fixture in fixtures)
        except Exception:
            fail_safe_degradation()
        request_fingerprints = tuple(binding[0] for binding in bindings)
        if len(set(request_fingerprints)) != len(request_fingerprints):
            fail_safe_degradation()
        self._bindings = bindings

    def __repr__(self) -> str:
        return "RecordedSafeDegradationAdapter(<redacted-st1402-safe-degradation>)"

    def __str__(self) -> str:
        return "<redacted-st1402-safe-degradation>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("safe-degradation adapter serialization is not supported")

    def decide(self, request: SafeDegradationRequest) -> SafeDegradationDecision:
        snapshot = snapshot_safe_degradation_request(request)
        decision = decide_safe_degradation(snapshot)
        matches = tuple(
            binding
            for binding in self._bindings
            if binding == (snapshot.fingerprint, decision.fingerprint)
        )
        if len(matches) != 1:
            fail_safe_degradation(SafeDegradationFailureCode.DECIDER_UNAVAILABLE)
        return decision


__all__ = [
    "RecordedSafeDegradationAdapter",
    "RecordedSafeDegradationFixture",
]

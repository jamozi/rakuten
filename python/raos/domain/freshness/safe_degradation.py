"""Value-free deterministic safe-degradation decisions for ST-1402."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import NoReturn, SupportsIndex, final

from raos.domain.freshness.freshness import (
    FreshnessAttestationStatus,
    FreshnessPersistenceStatus,
    FreshnessPolicyActivation,
    FreshnessPolicyAuthority,
    FreshnessProjectionAction,
    FreshnessReviewAction,
    FreshnessState,
    FreshnessUnknownReason,
    OpenDecisionStatus,
    RecommendationOrderAction,
)


MAX_RECORDED_SAFE_DEGRADATION_FIXTURES = 10_000

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_SUPPORTED_FRESHNESS_CLASSES = frozenset({"FRESH-001", "FRESH-002", "FRESH-003"})
_REDACTED = "<redacted-st1402-safe-degradation>"


class SafeDegradationMode(str, Enum):
    RECORDED_DEV_CI_ONLY = "RECORDED_DEV_CI_ONLY"


class AvailabilityAggregate(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_ALL_PRIMARY_OFFERS_UNAVAILABLE = "NOT_ALL_PRIMARY_OFFERS_UNAVAILABLE"
    ALL_PRIMARY_OFFERS_UNAVAILABLE = "ALL_PRIMARY_OFFERS_UNAVAILABLE"


class SafeDegradationAction(str, Enum):
    HIDE_VALUE = "HIDE_VALUE"
    HIDE_AVAILABILITY_ASSERTION = "HIDE_AVAILABILITY_ASSERTION"
    CTA_PAUSE_CANDIDATE = "CTA_PAUSE_CANDIDATE"
    HIDE_CTA = "HIDE_CTA"
    RETAIN_ARTICLE_BODY = "RETAIN_ARTICLE_BODY"


class SafeDegradationNoticeCode(str, Enum):
    FRESH_001_OFFER_PRICE_NOT_LATEST = "FRESH_001_OFFER_PRICE_NOT_LATEST"


class SafeDegradationExecutionStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


class SafeDegradationAttestationStatus(str, Enum):
    NOT_ATTESTED = "NOT_ATTESTED"


class SafeDegradationFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"
    FRESHNESS_RESULT_INVALID = "FRESHNESS_RESULT_INVALID"
    FRESHNESS_NOT_DEGRADABLE = "FRESHNESS_NOT_DEGRADABLE"
    UNSUPPORTED_FRESHNESS_CLASS = "UNSUPPORTED_FRESHNESS_CLASS"
    RECOMMENDATION_BASIS_INVALID = "RECOMMENDATION_BASIS_INVALID"
    DECIDER_UNAVAILABLE = "DECIDER_UNAVAILABLE"
    DECISION_MISMATCH = "DECISION_MISMATCH"


@final
class SafeDegradationFailure(RuntimeError):
    """Closed failure that retains no rejected or collaborator material."""

    __slots__ = ("_code",)
    _code: SafeDegradationFailureCode

    def __init__(self, code: SafeDegradationFailureCode) -> None:
        if type(code) is not SafeDegradationFailureCode:
            raise TypeError("invalid safe-degradation failure code")
        RuntimeError.__init__(self, code.value)
        object.__setattr__(self, "_code", code)

    @property
    def code(self) -> SafeDegradationFailureCode:
        return self._code

    def __setattr__(self, name: str, value: object) -> None:
        if name == "__traceback__":
            BaseException.__setattr__(self, name, value)
            return
        del name, value
        raise AttributeError("SafeDegradationFailure is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("SafeDegradationFailure is immutable")

    def __repr__(self) -> str:
        return f"SafeDegradationFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("safe-degradation failure serialization is not supported")


def fail_safe_degradation(
    code: SafeDegradationFailureCode = SafeDegradationFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise SafeDegradationFailure(code) from None


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("safe-degradation value serialization is not supported")


def _require_sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_safe_degradation()
    return value


def _compact_sha256(value: object) -> str:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except Exception:
        fail_safe_degradation()
    return hashlib.sha256(payload).hexdigest()


@final
@dataclass(frozen=True, slots=True, repr=False)
class SafeDegradationFreshnessBinding(_RedactedValue):
    evaluation_fingerprint: str
    request_fingerprint: str
    policy_binding_fingerprint: str
    freshness_class_id: str
    state: FreshnessState
    unknown_reason: FreshnessUnknownReason
    projection_action: FreshnessProjectionAction
    stale: bool
    latest: bool
    review_action: FreshnessReviewAction
    recommendation_order_action: RecommendationOrderAction
    policy_authority: FreshnessPolicyAuthority
    policy_activation: FreshnessPolicyActivation
    open_decision_id: str
    open_decision_status: OpenDecisionStatus
    policy_active: bool
    persistence: FreshnessPersistenceStatus
    attestation: FreshnessAttestationStatus
    live_eligible: bool

    def __post_init__(self) -> None:
        _require_sha256(self.evaluation_fingerprint)
        _require_sha256(self.request_fingerprint)
        _require_sha256(self.policy_binding_fingerprint)
        if type(self.freshness_class_id) is not str:
            fail_safe_degradation(SafeDegradationFailureCode.FRESHNESS_RESULT_INVALID)
        if self.freshness_class_id not in _SUPPORTED_FRESHNESS_CLASSES:
            fail_safe_degradation(
                SafeDegradationFailureCode.UNSUPPORTED_FRESHNESS_CLASS
            )
        if (
            type(self.state) is not FreshnessState
            or self.state not in {FreshnessState.UNKNOWN, FreshnessState.CRITICAL}
            or type(self.unknown_reason) is not FreshnessUnknownReason
            or type(self.projection_action) is not FreshnessProjectionAction
            or self.stale is not True
            or self.latest is not False
            or type(self.review_action) is not FreshnessReviewAction
            or self.recommendation_order_action
            is not RecommendationOrderAction.FORBIDDEN
            or self.policy_authority
            is not FreshnessPolicyAuthority.PROVISIONAL_CANONICAL_SAFE_DEFAULT
            or self.policy_activation
            is not FreshnessPolicyActivation.DISABLED_UNRESOLVED_OD_007
            or self.open_decision_id != "OD-007"
            or self.open_decision_status
            is not OpenDecisionStatus.HUMAN_DECISION_REQUIRED
            or self.policy_active is not False
            or self.persistence is not FreshnessPersistenceStatus.NOT_EXECUTED
            or self.attestation is not FreshnessAttestationStatus.NOT_ATTESTED
            or self.live_eligible is not False
        ):
            fail_safe_degradation(SafeDegradationFailureCode.FRESHNESS_RESULT_INVALID)
        if self.state is FreshnessState.UNKNOWN:
            if (
                self.unknown_reason is FreshnessUnknownReason.NONE
                or self.projection_action
                is not FreshnessProjectionAction.KEEP_LAST_WITH_STALE_STATE_NOT_LATEST
            ):
                fail_safe_degradation(
                    SafeDegradationFailureCode.FRESHNESS_RESULT_INVALID
                )
        elif (
            self.unknown_reason is not FreshnessUnknownReason.NONE
            or self.projection_action is not FreshnessProjectionAction.SAFE_DEGRADE
        ):
            fail_safe_degradation(SafeDegradationFailureCode.FRESHNESS_RESULT_INVALID)

    @property
    def fingerprint(self) -> str:
        return _compact_sha256(
            {
                "attestation": self.attestation.value,
                "evaluation_fingerprint": self.evaluation_fingerprint,
                "freshness_class_id": self.freshness_class_id,
                "latest": self.latest,
                "live_eligible": self.live_eligible,
                "open_decision_id": self.open_decision_id,
                "open_decision_status": self.open_decision_status.value,
                "persistence": self.persistence.value,
                "policy_activation": self.policy_activation.value,
                "policy_active": self.policy_active,
                "policy_authority": self.policy_authority.value,
                "policy_binding_fingerprint": self.policy_binding_fingerprint,
                "projection_action": self.projection_action.value,
                "recommendation_order_action": (self.recommendation_order_action.value),
                "request_fingerprint": self.request_fingerprint,
                "review_action": self.review_action.value,
                "stale": self.stale,
                "state": self.state.value,
                "unknown_reason": self.unknown_reason.value,
            }
        )


def _owned_freshness_binding(
    value: object,
) -> SafeDegradationFreshnessBinding:
    snapshot: SafeDegradationFreshnessBinding | None = None
    matches = False
    if type(value) is SafeDegradationFreshnessBinding:
        try:
            source_fingerprint = value.fingerprint
            snapshot = SafeDegradationFreshnessBinding(
                evaluation_fingerprint=value.evaluation_fingerprint,
                request_fingerprint=value.request_fingerprint,
                policy_binding_fingerprint=value.policy_binding_fingerprint,
                freshness_class_id=value.freshness_class_id,
                state=value.state,
                unknown_reason=value.unknown_reason,
                projection_action=value.projection_action,
                stale=value.stale,
                latest=value.latest,
                review_action=value.review_action,
                recommendation_order_action=value.recommendation_order_action,
                policy_authority=value.policy_authority,
                policy_activation=value.policy_activation,
                open_decision_id=value.open_decision_id,
                open_decision_status=value.open_decision_status,
                policy_active=value.policy_active,
                persistence=value.persistence,
                attestation=value.attestation,
                live_eligible=value.live_eligible,
            )
            matches = (
                snapshot == value
                and snapshot.fingerprint == source_fingerprint
                and value.fingerprint == source_fingerprint
            )
        except Exception:
            matches = False
    if snapshot is None or not matches:
        fail_safe_degradation(SafeDegradationFailureCode.FRESHNESS_RESULT_INVALID)
    return snapshot


@final
@dataclass(frozen=True, slots=True, repr=False)
class SafeDegradationRequest(_RedactedValue):
    freshness: SafeDegradationFreshnessBinding
    availability_aggregate: AvailabilityAggregate

    def __post_init__(self) -> None:
        freshness = _owned_freshness_binding(self.freshness)
        if type(self.availability_aggregate) is not AvailabilityAggregate:
            fail_safe_degradation()
        if freshness.freshness_class_id == "FRESH-002":
            if self.availability_aggregate not in {
                AvailabilityAggregate.NOT_ALL_PRIMARY_OFFERS_UNAVAILABLE,
                AvailabilityAggregate.ALL_PRIMARY_OFFERS_UNAVAILABLE,
            }:
                fail_safe_degradation()
        elif self.availability_aggregate is not AvailabilityAggregate.NOT_APPLICABLE:
            fail_safe_degradation()
        if (
            freshness.freshness_class_id == "FRESH-003"
            and freshness.review_action is not FreshnessReviewAction.NONE
        ):
            fail_safe_degradation(
                SafeDegradationFailureCode.RECOMMENDATION_BASIS_INVALID
            )
        object.__setattr__(self, "freshness", freshness)

    @property
    def fingerprint(self) -> str:
        return _compact_sha256(
            {
                "availability_aggregate": self.availability_aggregate.value,
                "freshness": self.freshness.fingerprint,
            }
        )


def snapshot_safe_degradation_request(
    value: object,
) -> SafeDegradationRequest:
    """Own and revalidate an already bound value-free request."""

    snapshot: SafeDegradationRequest | None = None
    matches = False
    if type(value) is SafeDegradationRequest:
        try:
            source_fingerprint = value.fingerprint
            snapshot = SafeDegradationRequest(
                freshness=_owned_freshness_binding(value.freshness),
                availability_aggregate=value.availability_aggregate,
            )
            matches = (
                snapshot == value
                and snapshot.fingerprint == source_fingerprint
                and value.fingerprint == source_fingerprint
            )
        except Exception:
            matches = False
    if snapshot is None or not matches:
        fail_safe_degradation()
    return snapshot


@final
@dataclass(frozen=True, slots=True, repr=False)
class SafeDegradationDecision(_RedactedValue):
    mode: SafeDegradationMode
    request_fingerprint: str
    freshness_evaluation_fingerprint: str
    freshness_class_id: str
    availability_aggregate: AvailabilityAggregate
    actions: tuple[SafeDegradationAction, ...]
    notice_code: SafeDegradationNoticeCode | None
    review_action: FreshnessReviewAction
    recommendation_order_action: RecommendationOrderAction
    renderer_effects: SafeDegradationExecutionStatus
    persistence: SafeDegradationExecutionStatus
    attestation: SafeDegradationAttestationStatus
    can_change_state: bool
    publication_authorized: bool
    live_eligible: bool

    def __post_init__(self) -> None:
        _require_sha256(self.request_fingerprint)
        _require_sha256(self.freshness_evaluation_fingerprint)
        if (
            self.mode is not SafeDegradationMode.RECORDED_DEV_CI_ONLY
            or type(self.freshness_class_id) is not str
            or type(self.availability_aggregate) is not AvailabilityAggregate
            or type(self.actions) is not tuple
            or not self.actions
            or any(type(action) is not SafeDegradationAction for action in self.actions)
            or len(set(self.actions)) != len(self.actions)
            or (
                self.notice_code is not None
                and type(self.notice_code) is not SafeDegradationNoticeCode
            )
            or type(self.review_action) is not FreshnessReviewAction
            or self.recommendation_order_action
            is not RecommendationOrderAction.FORBIDDEN
            or self.renderer_effects is not SafeDegradationExecutionStatus.NOT_EXECUTED
            or self.persistence is not SafeDegradationExecutionStatus.NOT_EXECUTED
            or self.attestation is not SafeDegradationAttestationStatus.NOT_ATTESTED
            or self.can_change_state is not False
            or self.publication_authorized is not False
            or self.live_eligible is not False
        ):
            fail_safe_degradation(SafeDegradationFailureCode.DECISION_MISMATCH)
        if self.freshness_class_id not in _SUPPORTED_FRESHNESS_CLASSES:
            fail_safe_degradation(SafeDegradationFailureCode.DECISION_MISMATCH)

        expected_actions: tuple[SafeDegradationAction, ...]
        if self.freshness_class_id == "FRESH-001":
            expected_actions = (SafeDegradationAction.HIDE_VALUE,)
            expected_notice = SafeDegradationNoticeCode.FRESH_001_OFFER_PRICE_NOT_LATEST
            valid_scope = (
                self.availability_aggregate is AvailabilityAggregate.NOT_APPLICABLE
            )
        elif self.freshness_class_id == "FRESH-002":
            expected_actions = (SafeDegradationAction.HIDE_AVAILABILITY_ASSERTION,)
            if (
                self.availability_aggregate
                is AvailabilityAggregate.ALL_PRIMARY_OFFERS_UNAVAILABLE
            ):
                expected_actions += (SafeDegradationAction.CTA_PAUSE_CANDIDATE,)
            expected_notice = None
            valid_scope = self.availability_aggregate in {
                AvailabilityAggregate.NOT_ALL_PRIMARY_OFFERS_UNAVAILABLE,
                AvailabilityAggregate.ALL_PRIMARY_OFFERS_UNAVAILABLE,
            }
            if (
                self.availability_aggregate
                is AvailabilityAggregate.ALL_PRIMARY_OFFERS_UNAVAILABLE
                and self.review_action
                is not FreshnessReviewAction.CREATE_REVIEW_CANDIDATE
            ):
                fail_safe_degradation(SafeDegradationFailureCode.DECISION_MISMATCH)
        else:
            expected_actions = (
                SafeDegradationAction.HIDE_CTA,
                SafeDegradationAction.RETAIN_ARTICLE_BODY,
            )
            expected_notice = None
            valid_scope = (
                self.availability_aggregate is AvailabilityAggregate.NOT_APPLICABLE
            )
            if self.review_action is not FreshnessReviewAction.NONE:
                fail_safe_degradation(SafeDegradationFailureCode.DECISION_MISMATCH)

        if (
            not valid_scope
            or self.actions != expected_actions
            or self.notice_code is not expected_notice
        ):
            fail_safe_degradation(SafeDegradationFailureCode.DECISION_MISMATCH)

    @property
    def fingerprint(self) -> str:
        return _compact_sha256(
            {
                "actions": [action.value for action in self.actions],
                "attestation": self.attestation.value,
                "availability_aggregate": self.availability_aggregate.value,
                "can_change_state": self.can_change_state,
                "freshness_class_id": self.freshness_class_id,
                "freshness_evaluation_fingerprint": (
                    self.freshness_evaluation_fingerprint
                ),
                "live_eligible": self.live_eligible,
                "mode": self.mode.value,
                "notice_code": (
                    None if self.notice_code is None else self.notice_code.value
                ),
                "persistence": self.persistence.value,
                "publication_authorized": self.publication_authorized,
                "recommendation_order_action": (self.recommendation_order_action.value),
                "renderer_effects": self.renderer_effects.value,
                "request_fingerprint": self.request_fingerprint,
                "review_action": self.review_action.value,
            }
        )


def decide_safe_degradation(
    request: SafeDegradationRequest,
) -> SafeDegradationDecision:
    """Return a closed value-free decision without applying renderer effects."""

    owned_request = snapshot_safe_degradation_request(request)
    freshness = owned_request.freshness
    if freshness.latest or not freshness.stale:
        fail_safe_degradation(SafeDegradationFailureCode.FRESHNESS_NOT_DEGRADABLE)

    actions: tuple[SafeDegradationAction, ...]
    if freshness.freshness_class_id == "FRESH-001":
        actions = (SafeDegradationAction.HIDE_VALUE,)
        notice_code: SafeDegradationNoticeCode | None = (
            SafeDegradationNoticeCode.FRESH_001_OFFER_PRICE_NOT_LATEST
        )
        review_action = freshness.review_action
    elif freshness.freshness_class_id == "FRESH-002":
        actions = (SafeDegradationAction.HIDE_AVAILABILITY_ASSERTION,)
        all_unavailable = (
            owned_request.availability_aggregate
            is AvailabilityAggregate.ALL_PRIMARY_OFFERS_UNAVAILABLE
        )
        if all_unavailable:
            actions += (SafeDegradationAction.CTA_PAUSE_CANDIDATE,)
        notice_code = None
        review_action = (
            FreshnessReviewAction.CREATE_REVIEW_CANDIDATE
            if all_unavailable
            else freshness.review_action
        )
    elif freshness.freshness_class_id == "FRESH-003":
        if freshness.review_action is not FreshnessReviewAction.NONE:
            fail_safe_degradation(
                SafeDegradationFailureCode.RECOMMENDATION_BASIS_INVALID
            )
        actions = (
            SafeDegradationAction.HIDE_CTA,
            SafeDegradationAction.RETAIN_ARTICLE_BODY,
        )
        notice_code = None
        review_action = FreshnessReviewAction.NONE
    else:
        fail_safe_degradation(SafeDegradationFailureCode.UNSUPPORTED_FRESHNESS_CLASS)

    return SafeDegradationDecision(
        mode=SafeDegradationMode.RECORDED_DEV_CI_ONLY,
        request_fingerprint=owned_request.fingerprint,
        freshness_evaluation_fingerprint=freshness.evaluation_fingerprint,
        freshness_class_id=freshness.freshness_class_id,
        availability_aggregate=owned_request.availability_aggregate,
        actions=actions,
        notice_code=notice_code,
        review_action=review_action,
        recommendation_order_action=RecommendationOrderAction.FORBIDDEN,
        renderer_effects=SafeDegradationExecutionStatus.NOT_EXECUTED,
        persistence=SafeDegradationExecutionStatus.NOT_EXECUTED,
        attestation=SafeDegradationAttestationStatus.NOT_ATTESTED,
        can_change_state=False,
        publication_authorized=False,
        live_eligible=False,
    )


__all__ = [
    "MAX_RECORDED_SAFE_DEGRADATION_FIXTURES",
    "AvailabilityAggregate",
    "SafeDegradationAction",
    "SafeDegradationAttestationStatus",
    "SafeDegradationDecision",
    "SafeDegradationExecutionStatus",
    "SafeDegradationFailure",
    "SafeDegradationFailureCode",
    "SafeDegradationFreshnessBinding",
    "SafeDegradationMode",
    "SafeDegradationNoticeCode",
    "SafeDegradationRequest",
    "decide_safe_degradation",
    "fail_safe_degradation",
    "snapshot_safe_degradation_request",
]

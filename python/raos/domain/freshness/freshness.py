"""Provisional, non-attesting freshness values for the ST-1401 safe seam."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import NoReturn, SupportsIndex, final
from uuid import UUID


FRESHNESS_POLICY_ID = "RAOS-CONTENT-FRESH-001"
FRESHNESS_POLICY_DOCUMENT_VERSION = "0.1"
FRESHNESS_POLICY_VERSION = "1.0.0"
FRESHNESS_POLICY_BYTES = 5_428
FRESHNESS_POLICY_SHA256 = (
    "a4d490d2a54b3def63c9c240b09d34a759ebd3924e60cfcca438ee979334cea2"
)
FRESHNESS_MATRIX_BYTES = 142_924
FRESHNESS_MATRIX_SHA256 = (
    "9be140d6f7015bf8c464993a34d127b2e8c118fd0ed49d20d113fb399ed8a564"
)
FRESHNESS_THRESHOLD_STATUS = (
    "PROVISIONAL; category and provider overrides require approval and measurement"
)
FRESHNESS_OPEN_DECISION_ID = "OD-007"
MAX_FRESHNESS_SCHEDULE_ENTRIES = 10_000
MAX_RECORDED_FRESHNESS_FIXTURES = 10_000

_MAX_SIGNED_PRIORITY = (1 << 31) - 1
_MICROSECONDS_PER_HOUR = 3_600_000_000
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_CLASS_ID = re.compile(r"FRESH-(?:00[1-9]|01[0-2])\Z", re.ASCII)
_CLASS_CODE = re.compile(r"[a-z][a-z0-9_]{0,99}\Z", re.ASCII)
_REDACTED = "<redacted-st1401-freshness>"

_POLICY_DEFINITIONS: tuple[tuple[str, str, int, int, str, str], ...] = (
    (
        "FRESH-001",
        "offer_price",
        24,
        72,
        "hide_value_and_show_provider_check_label",
        "if recommendation depends on price tier, create blocking review candidate",
    ),
    (
        "FRESH-002",
        "availability",
        12,
        48,
        "hide_availability_assertion",
        "if all primary offers unavailable, pause CTA and create review candidate",
    ),
    (
        "FRESH-003",
        "affiliate_link_health",
        24,
        72,
        "hide_cta",
        "article body remains unless product identity or policy also fails",
    ),
    (
        "FRESH-004",
        "shipping_condition",
        24,
        72,
        "hide_shipping_assertion",
        "do not infer free shipping",
    ),
    (
        "FRESH-005",
        "points_coupon_campaign",
        6,
        12,
        "hide_entire_field",
        "MVP default is not to editorially rely on promotions",
    ),
    (
        "FRESH-006",
        "official_ranking",
        24,
        72,
        "remove_rank_claim",
        "never convert provider rank into enduring popularity claim",
    ),
    (
        "FRESH-007",
        "product_specification",
        720,
        2160,
        "mark_for_review_or_hide_affected_field",
        "pause article if recommendation-critical specification is stale/conflicted",
    ),
    (
        "FRESH-008",
        "manufacturer_lifecycle_status",
        168,
        720,
        "show_last_checked_and_review",
        "pause CTA for discontinued/recall/safety concern as policy determines",
    ),
    (
        "FRESH-009",
        "editorial_methodology",
        720,
        2160,
        "revalidate_methodology",
        "new version requires impact analysis",
    ),
    (
        "FRESH-010",
        "policy_disclosure",
        0,
        0,
        "immediate_renderer_update",
        "blocking policy change overrides prior approval",
    ),
    (
        "FRESH-011",
        "first_hand_experience",
        4320,
        8760,
        "show_test_date_and_limitations",
        "do not imply current product revision without identity recheck",
    ),
    (
        "FRESH-012",
        "internal_link_target",
        168,
        720,
        "remove_or_replace_broken_link",
        "must not create redirect chain or orphan",
    ),
)


class FreshnessPolicyAuthority(str, Enum):
    PROVISIONAL_CANONICAL_SAFE_DEFAULT = "PROVISIONAL_CANONICAL_SAFE_DEFAULT"


class FreshnessPolicyActivation(str, Enum):
    DISABLED_UNRESOLVED_OD_007 = "DISABLED_UNRESOLVED_OD_007"


class OpenDecisionStatus(str, Enum):
    HUMAN_DECISION_REQUIRED = "HUMAN_DECISION_REQUIRED"


class FreshnessMode(str, Enum):
    RECORDED_DEV_CI_ONLY = "RECORDED_DEV_CI_ONLY"


class FreshnessObservationStatus(str, Enum):
    VALIDATED = "VALIDATED"
    MISSING = "MISSING"
    FETCH_FAILED = "FETCH_FAILED"
    RECOVERY_VALIDATED = "RECOVERY_VALIDATED"
    RECOVERY_UNVALIDATED = "RECOVERY_UNVALIDATED"


class FreshnessState(str, Enum):
    FRESH = "FRESH"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class FreshnessUnknownReason(str, Enum):
    NONE = "NONE"
    MISSING = "MISSING"
    FETCH_FAILED = "FETCH_FAILED"
    FUTURE_OBSERVATION = "FUTURE_OBSERVATION"
    RECOVERY_NOT_VALIDATED = "RECOVERY_NOT_VALIDATED"


class FreshnessProjectionAction(str, Enum):
    DISPLAY = "DISPLAY"
    DISPLAY_WITH_WARNING_QUEUE = "DISPLAY_WITH_WARNING_QUEUE"
    SAFE_DEGRADE = "SAFE_DEGRADE"
    KEEP_LAST_WITH_STALE_STATE_NOT_LATEST = "KEEP_LAST_WITH_STALE_STATE_NOT_LATEST"
    RESTORE_FIELD_AFTER_VALIDATION = "RESTORE_FIELD_AFTER_VALIDATION"


class FreshnessReviewAction(str, Enum):
    NONE = "NONE"
    CREATE_REVIEW_CANDIDATE = "CREATE_REVIEW_CANDIDATE"


class RecommendationOrderAction(str, Enum):
    FORBIDDEN = "FORBIDDEN"


class FreshnessScheduleStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DISABLED = "DISABLED"


class FreshnessPersistenceStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


class FreshnessAttestationStatus(str, Enum):
    NOT_ATTESTED = "NOT_ATTESTED"


class FreshnessFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"
    EVALUATOR_UNAVAILABLE = "EVALUATOR_UNAVAILABLE"
    EVALUATION_MISMATCH = "EVALUATION_MISMATCH"
    SCHEDULER_UNAVAILABLE = "SCHEDULER_UNAVAILABLE"
    SCHEDULE_MISMATCH = "SCHEDULE_MISMATCH"


@final
class FreshnessFailure(RuntimeError):
    """Stable failure that retains no rejected or collaborator material."""

    __slots__ = ("_code",)
    _code: FreshnessFailureCode

    def __init__(self, code: FreshnessFailureCode) -> None:
        if type(code) is not FreshnessFailureCode:
            raise TypeError("invalid freshness failure code")
        RuntimeError.__init__(self, code.value)
        object.__setattr__(self, "_code", code)

    @property
    def code(self) -> FreshnessFailureCode:
        return self._code

    def __setattr__(self, name: str, value: object) -> None:
        if name == "__traceback__":
            BaseException.__setattr__(self, name, value)
            return
        del name, value
        raise AttributeError("FreshnessFailure is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("FreshnessFailure is immutable")

    def __repr__(self) -> str:
        return f"FreshnessFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("freshness failure serialization is not supported")


def fail_freshness(
    code: FreshnessFailureCode = FreshnessFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise FreshnessFailure(code) from None


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("freshness value serialization is not supported")


def _require_sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_freshness()
    return value


def _require_uuid(value: object) -> UUID:
    if type(value) is not UUID or value.int == 0:
        fail_freshness()
    return value


def _owned_uuid(value: object) -> UUID:
    validated = _require_uuid(value)
    return UUID(int=validated.int)


def _as_utc(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is None:
        fail_freshness()
    converted: datetime | None = None
    offset_present = False
    failed = False
    try:
        offset_present = value.utcoffset() is not None
        converted = value.astimezone(timezone.utc)
    except Exception:
        failed = True
    if failed or not offset_present or type(converted) is not datetime:
        fail_freshness()
    return datetime(
        converted.year,
        converted.month,
        converted.day,
        converted.hour,
        converted.minute,
        converted.second,
        converted.microsecond,
        tzinfo=timezone.utc,
        fold=0,
    )


def _time_text(value: datetime) -> str:
    return _as_utc(value).isoformat(timespec="microseconds")


def _age_microseconds(*, observed_at: datetime, evaluated_at: datetime) -> int:
    age = _as_utc(evaluated_at) - _as_utc(observed_at)
    return ((age.days * 86_400) + age.seconds) * 1_000_000 + age.microseconds


def _compact_sha256(value: dict[str, object]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _policy_text(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > 512
        or any(ord(character) < 32 for character in value)
    ):
        fail_freshness()
    return value


@final
@dataclass(frozen=True, slots=True, repr=False)
class FreshnessPolicyBinding(_RedactedValue):
    policy_id: str
    document_version: str
    policy_version: str
    policy_bytes: int
    policy_sha256: str
    matrix_bytes: int
    matrix_sha256: str
    threshold_status: str
    class_count: int
    authority: FreshnessPolicyAuthority
    activation: FreshnessPolicyActivation
    open_decision_id: str
    open_decision_status: OpenDecisionStatus
    policy_active: bool

    def __post_init__(self) -> None:
        if (
            self.policy_id != FRESHNESS_POLICY_ID
            or self.document_version != FRESHNESS_POLICY_DOCUMENT_VERSION
            or self.policy_version != FRESHNESS_POLICY_VERSION
            or type(self.policy_bytes) is not int
            or self.policy_bytes != FRESHNESS_POLICY_BYTES
            or self.policy_sha256 != FRESHNESS_POLICY_SHA256
            or type(self.matrix_bytes) is not int
            or self.matrix_bytes != FRESHNESS_MATRIX_BYTES
            or self.matrix_sha256 != FRESHNESS_MATRIX_SHA256
            or self.threshold_status != FRESHNESS_THRESHOLD_STATUS
            or type(self.class_count) is not int
            or self.class_count != len(_POLICY_DEFINITIONS)
            or self.authority
            is not FreshnessPolicyAuthority.PROVISIONAL_CANONICAL_SAFE_DEFAULT
            or self.activation
            is not FreshnessPolicyActivation.DISABLED_UNRESOLVED_OD_007
            or self.open_decision_id != FRESHNESS_OPEN_DECISION_ID
            or self.open_decision_status
            is not OpenDecisionStatus.HUMAN_DECISION_REQUIRED
            or self.policy_active is not False
        ):
            fail_freshness()
        _require_sha256(self.policy_sha256)
        _require_sha256(self.matrix_sha256)

    @property
    def fingerprint(self) -> str:
        return _compact_sha256(
            {
                "activation": self.activation.value,
                "authority": self.authority.value,
                "class_count": self.class_count,
                "document_version": self.document_version,
                "matrix_bytes": self.matrix_bytes,
                "matrix_sha256": self.matrix_sha256,
                "open_decision_id": self.open_decision_id,
                "open_decision_status": self.open_decision_status.value,
                "policy_active": self.policy_active,
                "policy_bytes": self.policy_bytes,
                "policy_id": self.policy_id,
                "policy_sha256": self.policy_sha256,
                "policy_version": self.policy_version,
                "threshold_status": self.threshold_status,
            }
        )


def provisional_freshness_policy_binding() -> FreshnessPolicyBinding:
    return FreshnessPolicyBinding(
        policy_id=FRESHNESS_POLICY_ID,
        document_version=FRESHNESS_POLICY_DOCUMENT_VERSION,
        policy_version=FRESHNESS_POLICY_VERSION,
        policy_bytes=FRESHNESS_POLICY_BYTES,
        policy_sha256=FRESHNESS_POLICY_SHA256,
        matrix_bytes=FRESHNESS_MATRIX_BYTES,
        matrix_sha256=FRESHNESS_MATRIX_SHA256,
        threshold_status=FRESHNESS_THRESHOLD_STATUS,
        class_count=len(_POLICY_DEFINITIONS),
        authority=FreshnessPolicyAuthority.PROVISIONAL_CANONICAL_SAFE_DEFAULT,
        activation=FreshnessPolicyActivation.DISABLED_UNRESOLVED_OD_007,
        open_decision_id=FRESHNESS_OPEN_DECISION_ID,
        open_decision_status=OpenDecisionStatus.HUMAN_DECISION_REQUIRED,
        policy_active=False,
    )


@final
@dataclass(frozen=True, slots=True, repr=False)
class FreshnessPolicyClass(_RedactedValue):
    class_id: str
    code: str
    warning_after_hours: int
    blocking_after_hours: int
    safe_degradation: str
    editorial_impact: str

    def __post_init__(self) -> None:
        definition = (
            self.class_id,
            self.code,
            self.warning_after_hours,
            self.blocking_after_hours,
            self.safe_degradation,
            self.editorial_impact,
        )
        if (
            type(self.class_id) is not str
            or _CLASS_ID.fullmatch(self.class_id) is None
            or type(self.code) is not str
            or _CLASS_CODE.fullmatch(self.code) is None
            or type(self.warning_after_hours) is not int
            or type(self.blocking_after_hours) is not int
            or not 0 <= self.warning_after_hours <= self.blocking_after_hours
            or definition not in _POLICY_DEFINITIONS
        ):
            fail_freshness()
        _policy_text(self.safe_degradation)
        _policy_text(self.editorial_impact)


def freshness_policy_classes() -> tuple[FreshnessPolicyClass, ...]:
    return tuple(
        FreshnessPolicyClass(*definition) for definition in _POLICY_DEFINITIONS
    )


def freshness_policy_for(class_id: str) -> FreshnessPolicyClass:
    if type(class_id) is not str or _CLASS_ID.fullmatch(class_id) is None:
        fail_freshness()
    matches = tuple(
        policy for policy in freshness_policy_classes() if policy.class_id == class_id
    )
    if len(matches) != 1:
        fail_freshness()
    return matches[0]


@final
@dataclass(frozen=True, slots=True, repr=False)
class FreshnessEvaluationRequest(_RedactedValue):
    freshness_class_id: str
    observation_status: FreshnessObservationStatus
    observed_at: datetime | None
    evaluated_at: datetime
    recommendation_basis_affected: bool

    def __post_init__(self) -> None:
        freshness_policy_for(self.freshness_class_id)
        if (
            type(self.observation_status) is not FreshnessObservationStatus
            or type(self.recommendation_basis_affected) is not bool
        ):
            fail_freshness()
        evaluated_at = _as_utc(self.evaluated_at)
        observed_at = None if self.observed_at is None else _as_utc(self.observed_at)
        if (
            self.observation_status
            in {
                FreshnessObservationStatus.VALIDATED,
                FreshnessObservationStatus.RECOVERY_VALIDATED,
                FreshnessObservationStatus.RECOVERY_UNVALIDATED,
            }
            and self.observed_at is None
        ) or (
            self.observation_status is FreshnessObservationStatus.MISSING
            and self.observed_at is not None
        ):
            fail_freshness()
        object.__setattr__(self, "evaluated_at", evaluated_at)
        object.__setattr__(self, "observed_at", observed_at)

    @property
    def fingerprint(self) -> str:
        return _compact_sha256(
            {
                "evaluated_at": _time_text(self.evaluated_at),
                "freshness_class_id": self.freshness_class_id,
                "observation_status": self.observation_status.value,
                "observed_at": (
                    None if self.observed_at is None else _time_text(self.observed_at)
                ),
                "policy_binding": provisional_freshness_policy_binding().fingerprint,
                "recommendation_basis_affected": self.recommendation_basis_affected,
            }
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class FreshnessEvaluation(_RedactedValue):
    mode: FreshnessMode
    policy_binding: FreshnessPolicyBinding
    policy_class: FreshnessPolicyClass
    request_fingerprint: str
    observation_status: FreshnessObservationStatus
    state: FreshnessState
    unknown_reason: FreshnessUnknownReason
    projection_action: FreshnessProjectionAction
    age_microseconds: int | None
    stale: bool
    latest: bool
    review_action: FreshnessReviewAction
    recommendation_order_action: RecommendationOrderAction
    category_override_applied: bool
    provider_override_applied: bool
    persistence: FreshnessPersistenceStatus
    attestation: FreshnessAttestationStatus
    live_eligible: bool

    def __post_init__(self) -> None:
        if (
            type(self.policy_binding) is not FreshnessPolicyBinding
            or type(self.policy_class) is not FreshnessPolicyClass
        ):
            fail_freshness()
        self.policy_binding.__post_init__()
        self.policy_class.__post_init__()
        owned_policy_binding = provisional_freshness_policy_binding()
        owned_policy_class = freshness_policy_for(self.policy_class.class_id)
        _require_sha256(self.request_fingerprint)
        if (
            self.mode is not FreshnessMode.RECORDED_DEV_CI_ONLY
            or type(self.observation_status) is not FreshnessObservationStatus
            or type(self.state) is not FreshnessState
            or type(self.unknown_reason) is not FreshnessUnknownReason
            or type(self.projection_action) is not FreshnessProjectionAction
            or (
                self.age_microseconds is not None
                and (
                    type(self.age_microseconds) is not int or self.age_microseconds < 0
                )
            )
            or type(self.stale) is not bool
            or type(self.latest) is not bool
            or type(self.review_action) is not FreshnessReviewAction
            or self.recommendation_order_action
            is not RecommendationOrderAction.FORBIDDEN
            or self.category_override_applied is not False
            or self.provider_override_applied is not False
            or self.persistence is not FreshnessPersistenceStatus.NOT_EXECUTED
            or self.attestation is not FreshnessAttestationStatus.NOT_ATTESTED
            or self.live_eligible is not False
        ):
            fail_freshness()
        if self.state is FreshnessState.UNKNOWN:
            expected_unknown_reason = {
                FreshnessObservationStatus.MISSING: FreshnessUnknownReason.MISSING,
                FreshnessObservationStatus.FETCH_FAILED: (
                    FreshnessUnknownReason.FETCH_FAILED
                ),
                FreshnessObservationStatus.RECOVERY_UNVALIDATED: (
                    FreshnessUnknownReason.RECOVERY_NOT_VALIDATED
                ),
                FreshnessObservationStatus.VALIDATED: (
                    FreshnessUnknownReason.FUTURE_OBSERVATION
                ),
                FreshnessObservationStatus.RECOVERY_VALIDATED: (
                    FreshnessUnknownReason.FUTURE_OBSERVATION
                ),
            }[self.observation_status]
            if (
                self.unknown_reason is not expected_unknown_reason
                or self.age_microseconds is not None
                or self.projection_action
                is not FreshnessProjectionAction.KEEP_LAST_WITH_STALE_STATE_NOT_LATEST
                or self.stale is not True
                or self.latest is not False
            ):
                fail_freshness()
        else:
            if (
                self.observation_status
                not in {
                    FreshnessObservationStatus.VALIDATED,
                    FreshnessObservationStatus.RECOVERY_VALIDATED,
                }
                or self.unknown_reason is not FreshnessUnknownReason.NONE
                or self.age_microseconds is None
            ):
                fail_freshness()
            if self.state is FreshnessState.CRITICAL:
                if (
                    self.projection_action is not FreshnessProjectionAction.SAFE_DEGRADE
                    or self.stale is not True
                    or self.latest is not False
                ):
                    fail_freshness()
            else:
                expected_action = (
                    FreshnessProjectionAction.RESTORE_FIELD_AFTER_VALIDATION
                    if self.observation_status
                    is FreshnessObservationStatus.RECOVERY_VALIDATED
                    else (
                        FreshnessProjectionAction.DISPLAY
                        if self.state is FreshnessState.FRESH
                        else FreshnessProjectionAction.DISPLAY_WITH_WARNING_QUEUE
                    )
                )
                if (
                    self.projection_action is not expected_action
                    or self.stale is not False
                    or self.latest is not True
                ):
                    fail_freshness()
        object.__setattr__(self, "policy_binding", owned_policy_binding)
        object.__setattr__(self, "policy_class", owned_policy_class)

    @property
    def fingerprint(self) -> str:
        return _compact_sha256(
            {
                "age_microseconds": self.age_microseconds,
                "attestation": self.attestation.value,
                "category_override_applied": self.category_override_applied,
                "latest": self.latest,
                "live_eligible": self.live_eligible,
                "mode": self.mode.value,
                "observation_status": self.observation_status.value,
                "persistence": self.persistence.value,
                "policy_binding": self.policy_binding.fingerprint,
                "policy_class": self.policy_class.class_id,
                "projection_action": self.projection_action.value,
                "provider_override_applied": self.provider_override_applied,
                "recommendation_order_action": (self.recommendation_order_action.value),
                "request_fingerprint": self.request_fingerprint,
                "review_action": self.review_action.value,
                "stale": self.stale,
                "state": self.state.value,
                "unknown_reason": self.unknown_reason.value,
            }
        )


def _canonical_utc_fields(value: object) -> tuple[int, ...] | None:
    if (
        type(value) is not datetime
        or value.tzinfo is not timezone.utc
        or value.fold != 0
    ):
        return None
    return (
        value.year,
        value.month,
        value.day,
        value.hour,
        value.minute,
        value.second,
        value.microsecond,
    )


def _same_evaluation_request(
    left: FreshnessEvaluationRequest,
    right: FreshnessEvaluationRequest,
) -> bool:
    left_observed = (
        None if left.observed_at is None else _canonical_utc_fields(left.observed_at)
    )
    right_observed = (
        None if right.observed_at is None else _canonical_utc_fields(right.observed_at)
    )
    return (
        left.freshness_class_id == right.freshness_class_id
        and left.observation_status is right.observation_status
        and left_observed == right_observed
        and (left.observed_at is None) is (right.observed_at is None)
        and _canonical_utc_fields(left.evaluated_at)
        == _canonical_utc_fields(right.evaluated_at)
        and _canonical_utc_fields(left.evaluated_at) is not None
        and left.recommendation_basis_affected is right.recommendation_basis_affected
    )


def _snapshot_evaluation_request(
    candidate: object,
) -> FreshnessEvaluationRequest:
    snapshot: FreshnessEvaluationRequest | None = None
    matches = False
    if type(candidate) is FreshnessEvaluationRequest:
        try:
            source_fingerprint = candidate.fingerprint
            snapshot = FreshnessEvaluationRequest(
                freshness_class_id=candidate.freshness_class_id,
                observation_status=candidate.observation_status,
                observed_at=candidate.observed_at,
                evaluated_at=candidate.evaluated_at,
                recommendation_basis_affected=candidate.recommendation_basis_affected,
            )
            matches = (
                _same_evaluation_request(snapshot, candidate)
                and snapshot.fingerprint == source_fingerprint
                and candidate.fingerprint == source_fingerprint
            )
        except Exception:
            matches = False
    if snapshot is None or not matches:
        fail_freshness()
    return snapshot


def evaluate_freshness(request: FreshnessEvaluationRequest) -> FreshnessEvaluation:
    """Evaluate one observation without clocks, I/O, activation, or attestation."""
    validated_request = _snapshot_evaluation_request(request)
    policy_class = freshness_policy_for(validated_request.freshness_class_id)
    state = FreshnessState.UNKNOWN
    unknown_reason = FreshnessUnknownReason.NONE
    age_microseconds: int | None = None

    if validated_request.observation_status is FreshnessObservationStatus.MISSING:
        unknown_reason = FreshnessUnknownReason.MISSING
    elif (
        validated_request.observation_status is FreshnessObservationStatus.FETCH_FAILED
    ):
        unknown_reason = FreshnessUnknownReason.FETCH_FAILED
    elif (
        validated_request.observation_status
        is FreshnessObservationStatus.RECOVERY_UNVALIDATED
    ):
        unknown_reason = FreshnessUnknownReason.RECOVERY_NOT_VALIDATED
    else:
        if validated_request.observed_at is None:
            fail_freshness()
        candidate_age = _age_microseconds(
            observed_at=validated_request.observed_at,
            evaluated_at=validated_request.evaluated_at,
        )
        if candidate_age < 0:
            unknown_reason = FreshnessUnknownReason.FUTURE_OBSERVATION
        else:
            age_microseconds = candidate_age
            warning_edge = policy_class.warning_after_hours * _MICROSECONDS_PER_HOUR
            blocking_edge = policy_class.blocking_after_hours * _MICROSECONDS_PER_HOUR
            if candidate_age >= blocking_edge:
                state = FreshnessState.CRITICAL
            elif candidate_age >= warning_edge:
                state = FreshnessState.WARNING
            else:
                state = FreshnessState.FRESH

    if state is FreshnessState.UNKNOWN:
        projection_action = (
            FreshnessProjectionAction.KEEP_LAST_WITH_STALE_STATE_NOT_LATEST
        )
        stale = True
        latest = False
    elif state is FreshnessState.CRITICAL:
        projection_action = FreshnessProjectionAction.SAFE_DEGRADE
        stale = True
        latest = False
    else:
        projection_action = (
            FreshnessProjectionAction.RESTORE_FIELD_AFTER_VALIDATION
            if validated_request.observation_status
            is FreshnessObservationStatus.RECOVERY_VALIDATED
            else (
                FreshnessProjectionAction.DISPLAY
                if state is FreshnessState.FRESH
                else FreshnessProjectionAction.DISPLAY_WITH_WARNING_QUEUE
            )
        )
        stale = False
        latest = True

    return FreshnessEvaluation(
        mode=FreshnessMode.RECORDED_DEV_CI_ONLY,
        policy_binding=provisional_freshness_policy_binding(),
        policy_class=policy_class,
        request_fingerprint=validated_request.fingerprint,
        observation_status=validated_request.observation_status,
        state=state,
        unknown_reason=unknown_reason,
        projection_action=projection_action,
        age_microseconds=age_microseconds,
        stale=stale,
        latest=latest,
        review_action=(
            FreshnessReviewAction.CREATE_REVIEW_CANDIDATE
            if validated_request.recommendation_basis_affected
            else FreshnessReviewAction.NONE
        ),
        recommendation_order_action=RecommendationOrderAction.FORBIDDEN,
        category_override_applied=False,
        provider_override_applied=False,
        persistence=FreshnessPersistenceStatus.NOT_EXECUTED,
        attestation=FreshnessAttestationStatus.NOT_ATTESTED,
        live_eligible=False,
    )


@final
@dataclass(frozen=True, slots=True, repr=False)
class FreshnessScheduleEntry(_RedactedValue):
    schedule_id: UUID
    subject_fingerprint: str
    freshness_class_id: str
    status: FreshnessScheduleStatus
    next_due_at: datetime
    priority: int

    def __post_init__(self) -> None:
        schedule_id = _owned_uuid(self.schedule_id)
        _require_sha256(self.subject_fingerprint)
        freshness_policy_for(self.freshness_class_id)
        if (
            type(self.status) is not FreshnessScheduleStatus
            or type(self.priority) is not int
            or not 0 <= self.priority <= _MAX_SIGNED_PRIORITY
        ):
            fail_freshness()
        next_due_at = _as_utc(self.next_due_at)
        object.__setattr__(self, "schedule_id", schedule_id)
        object.__setattr__(self, "next_due_at", next_due_at)

    @property
    def fingerprint(self) -> str:
        return _compact_sha256(
            {
                "freshness_class_id": self.freshness_class_id,
                "next_due_at": _time_text(self.next_due_at),
                "priority": self.priority,
                "schedule_id": str(self.schedule_id),
                "status": self.status.value,
                "subject_fingerprint": self.subject_fingerprint,
            }
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class FreshnessScheduleRequest(_RedactedValue):
    evaluated_at: datetime
    limit: int
    schedules: tuple[FreshnessScheduleEntry, ...]

    def __post_init__(self) -> None:
        evaluated_at = _as_utc(self.evaluated_at)
        if (
            type(self.limit) is not int
            or not 1 <= self.limit <= MAX_FRESHNESS_SCHEDULE_ENTRIES
            or type(self.schedules) is not tuple
            or len(self.schedules) > MAX_FRESHNESS_SCHEDULE_ENTRIES
            or any(type(item) is not FreshnessScheduleEntry for item in self.schedules)
        ):
            fail_freshness()
        schedules = tuple(
            FreshnessScheduleEntry(
                schedule_id=item.schedule_id,
                subject_fingerprint=item.subject_fingerprint,
                freshness_class_id=item.freshness_class_id,
                status=item.status,
                next_due_at=item.next_due_at,
                priority=item.priority,
            )
            for item in self.schedules
        )
        schedule_ids = tuple(item.schedule_id for item in schedules)
        subject_fingerprints = tuple(item.subject_fingerprint for item in schedules)
        if len(set(schedule_ids)) != len(schedule_ids) or len(
            set(subject_fingerprints)
        ) != len(subject_fingerprints):
            fail_freshness()
        object.__setattr__(self, "evaluated_at", evaluated_at)
        object.__setattr__(self, "schedules", schedules)

    @property
    def fingerprint(self) -> str:
        canonical_schedules = tuple(
            sorted(self.schedules, key=lambda item: item.schedule_id.int)
        )
        return _compact_sha256(
            {
                "evaluated_at": _time_text(self.evaluated_at),
                "limit": self.limit,
                "policy_binding": provisional_freshness_policy_binding().fingerprint,
                "schedules": [item.fingerprint for item in canonical_schedules],
            }
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class FreshnessCheckIntent(_RedactedValue):
    schedule_id: UUID
    subject_fingerprint: str
    freshness_class_id: str
    next_due_at: datetime
    priority: int
    request_fingerprint: str

    def __post_init__(self) -> None:
        schedule_id = _owned_uuid(self.schedule_id)
        _require_sha256(self.subject_fingerprint)
        freshness_policy_for(self.freshness_class_id)
        _require_sha256(self.request_fingerprint)
        if (
            type(self.priority) is not int
            or not 0 <= self.priority <= _MAX_SIGNED_PRIORITY
        ):
            fail_freshness()
        next_due_at = _as_utc(self.next_due_at)
        object.__setattr__(self, "schedule_id", schedule_id)
        object.__setattr__(self, "next_due_at", next_due_at)

    @property
    def fingerprint(self) -> str:
        return _compact_sha256(
            {
                "freshness_class_id": self.freshness_class_id,
                "next_due_at": _time_text(self.next_due_at),
                "policy_binding": provisional_freshness_policy_binding().fingerprint,
                "priority": self.priority,
                "request_fingerprint": self.request_fingerprint,
                "schedule_id": str(self.schedule_id),
                "subject_fingerprint": self.subject_fingerprint,
            }
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class FreshnessScheduleSelection(_RedactedValue):
    mode: FreshnessMode
    policy_binding: FreshnessPolicyBinding
    request_fingerprint: str
    intents: tuple[FreshnessCheckIntent, ...]
    cadence_computed: bool
    persistence: FreshnessPersistenceStatus
    attestation: FreshnessAttestationStatus
    live_eligible: bool

    def __post_init__(self) -> None:
        if type(self.policy_binding) is not FreshnessPolicyBinding:
            fail_freshness()
        self.policy_binding.__post_init__()
        policy_binding = provisional_freshness_policy_binding()
        _require_sha256(self.request_fingerprint)
        if (
            self.mode is not FreshnessMode.RECORDED_DEV_CI_ONLY
            or type(self.intents) is not tuple
            or len(self.intents) > MAX_FRESHNESS_SCHEDULE_ENTRIES
            or any(type(item) is not FreshnessCheckIntent for item in self.intents)
            or self.cadence_computed is not False
            or self.persistence is not FreshnessPersistenceStatus.NOT_EXECUTED
            or self.attestation is not FreshnessAttestationStatus.NOT_ATTESTED
            or self.live_eligible is not False
        ):
            fail_freshness()
        intents = tuple(
            FreshnessCheckIntent(
                schedule_id=item.schedule_id,
                subject_fingerprint=item.subject_fingerprint,
                freshness_class_id=item.freshness_class_id,
                next_due_at=item.next_due_at,
                priority=item.priority,
                request_fingerprint=item.request_fingerprint,
            )
            for item in self.intents
        )
        if any(
            item.request_fingerprint != self.request_fingerprint for item in intents
        ) or (
            len({item.schedule_id for item in intents}) != len(intents)
            or len({item.subject_fingerprint for item in intents}) != len(intents)
        ):
            fail_freshness()
        object.__setattr__(self, "policy_binding", policy_binding)
        object.__setattr__(self, "intents", intents)

    @property
    def fingerprint(self) -> str:
        return _compact_sha256(
            {
                "attestation": self.attestation.value,
                "cadence_computed": self.cadence_computed,
                "intents": [item.fingerprint for item in self.intents],
                "live_eligible": self.live_eligible,
                "mode": self.mode.value,
                "persistence": self.persistence.value,
                "policy_binding": self.policy_binding.fingerprint,
                "request_fingerprint": self.request_fingerprint,
            }
        )


def _same_schedule_entry(
    left: FreshnessScheduleEntry,
    right: FreshnessScheduleEntry,
) -> bool:
    return (
        type(left.schedule_id) is UUID
        and type(right.schedule_id) is UUID
        and left.schedule_id.int == right.schedule_id.int
        and left.schedule_id.int != 0
        and left.subject_fingerprint == right.subject_fingerprint
        and left.freshness_class_id == right.freshness_class_id
        and left.status is right.status
        and _canonical_utc_fields(left.next_due_at)
        == _canonical_utc_fields(right.next_due_at)
        and _canonical_utc_fields(left.next_due_at) is not None
        and left.priority == right.priority
    )


def _same_schedule_request(
    left: FreshnessScheduleRequest,
    right: FreshnessScheduleRequest,
) -> bool:
    return (
        _canonical_utc_fields(left.evaluated_at)
        == _canonical_utc_fields(right.evaluated_at)
        and _canonical_utc_fields(left.evaluated_at) is not None
        and left.limit == right.limit
        and type(left.schedules) is tuple
        and type(right.schedules) is tuple
        and len(left.schedules) == len(right.schedules)
        and all(
            _same_schedule_entry(left_item, right_item)
            for left_item, right_item in zip(
                left.schedules, right.schedules, strict=True
            )
        )
    )


def _snapshot_schedule_request(candidate: object) -> FreshnessScheduleRequest:
    snapshot: FreshnessScheduleRequest | None = None
    matches = False
    if (
        type(candidate) is FreshnessScheduleRequest
        and type(candidate.schedules) is tuple
        and all(type(item) is FreshnessScheduleEntry for item in candidate.schedules)
    ):
        try:
            snapshot = FreshnessScheduleRequest(
                evaluated_at=candidate.evaluated_at,
                limit=candidate.limit,
                schedules=candidate.schedules,
            )
            matches = _same_schedule_request(snapshot, candidate)
        except Exception:
            matches = False
    if snapshot is None or not matches:
        fail_freshness()
    return snapshot


def select_due_freshness(
    request: FreshnessScheduleRequest,
) -> FreshnessScheduleSelection:
    """Select due ACTIVE entries without deriving cadence or writing state."""
    if type(request) is not FreshnessScheduleRequest:
        fail_freshness()
    try:
        request_fingerprint = request.fingerprint
    except Exception:
        fail_freshness()
    validated_request = _snapshot_schedule_request(request)
    evaluated_at = validated_request.evaluated_at
    due = tuple(
        sorted(
            (
                item
                for item in validated_request.schedules
                if item.status is FreshnessScheduleStatus.ACTIVE
                and _as_utc(item.next_due_at) <= evaluated_at
            ),
            key=lambda item: (
                _as_utc(item.next_due_at),
                -item.priority,
                item.schedule_id.int,
            ),
        )
    )[: validated_request.limit]
    intents = tuple(
        FreshnessCheckIntent(
            schedule_id=item.schedule_id,
            subject_fingerprint=item.subject_fingerprint,
            freshness_class_id=item.freshness_class_id,
            next_due_at=item.next_due_at,
            priority=item.priority,
            request_fingerprint=request_fingerprint,
        )
        for item in due
    )
    return FreshnessScheduleSelection(
        mode=FreshnessMode.RECORDED_DEV_CI_ONLY,
        policy_binding=provisional_freshness_policy_binding(),
        request_fingerprint=request_fingerprint,
        intents=intents,
        cadence_computed=False,
        persistence=FreshnessPersistenceStatus.NOT_EXECUTED,
        attestation=FreshnessAttestationStatus.NOT_ATTESTED,
        live_eligible=False,
    )


__all__ = [
    "FRESHNESS_MATRIX_BYTES",
    "FRESHNESS_MATRIX_SHA256",
    "FRESHNESS_OPEN_DECISION_ID",
    "FRESHNESS_POLICY_BYTES",
    "FRESHNESS_POLICY_DOCUMENT_VERSION",
    "FRESHNESS_POLICY_ID",
    "FRESHNESS_POLICY_SHA256",
    "FRESHNESS_POLICY_VERSION",
    "FRESHNESS_THRESHOLD_STATUS",
    "MAX_FRESHNESS_SCHEDULE_ENTRIES",
    "MAX_RECORDED_FRESHNESS_FIXTURES",
    "FreshnessAttestationStatus",
    "FreshnessCheckIntent",
    "FreshnessEvaluation",
    "FreshnessEvaluationRequest",
    "FreshnessFailure",
    "FreshnessFailureCode",
    "FreshnessMode",
    "FreshnessObservationStatus",
    "FreshnessPersistenceStatus",
    "FreshnessPolicyActivation",
    "FreshnessPolicyAuthority",
    "FreshnessPolicyBinding",
    "FreshnessPolicyClass",
    "FreshnessProjectionAction",
    "FreshnessReviewAction",
    "FreshnessScheduleEntry",
    "FreshnessScheduleRequest",
    "FreshnessScheduleSelection",
    "FreshnessScheduleStatus",
    "FreshnessState",
    "FreshnessUnknownReason",
    "OpenDecisionStatus",
    "RecommendationOrderAction",
    "evaluate_freshness",
    "fail_freshness",
    "freshness_policy_classes",
    "freshness_policy_for",
    "provisional_freshness_policy_binding",
    "select_due_freshness",
]

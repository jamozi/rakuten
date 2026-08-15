"""Immutable, non-authoritative refresh proposals for ST-1403."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import NoReturn, SupportsIndex, final

from raos.domain.editorial.policy_engine import (
    ExecutionStatus,
    LocalEvaluationStatus,
)
from raos.domain.freshness.freshness import (
    FreshnessAttestationStatus,
    FreshnessPersistenceStatus,
    FreshnessPolicyActivation,
    FreshnessProjectionAction,
    FreshnessReviewAction,
    FreshnessState,
    OpenDecisionStatus,
    RecommendationOrderAction,
)


MAX_REFRESH_PROPOSAL_DIFFS = 1_000
MAX_RECORDED_REFRESH_PROPOSALS = 1_000
REFRESH_PROPOSAL_POLICY_PROFILE = "ST0805_LOCAL_RESULT_V1"
REFRESH_PROPOSAL_OPEN_DECISION_ID = "OD-007"

_REFERENCE = re.compile(r"[A-Z0-9][A-Z0-9_.:-]{0,126}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_REDACTED = "<redacted-st1403-refresh-proposal>"


class RefreshProposalMode(str, Enum):
    RECORDED_DEV_CI_ONLY = "RECORDED_DEV_CI_ONLY"


class RefreshDiffKind(str, Enum):
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    CHANGED = "CHANGED"
    BECAME_STALE = "BECAME_STALE"
    RESOLVED_CONFLICT = "RESOLVED_CONFLICT"


class RefreshChangeType(str, Enum):
    PRICE = "PRICE"
    AVAILABILITY = "AVAILABILITY"
    PRODUCT_ATTRIBUTE = "PRODUCT_ATTRIBUTE"
    AFFILIATE_LINK = "AFFILIATE_LINK"
    SOURCE_CORRECTION = "SOURCE_CORRECTION"
    POLICY_CHANGE = "POLICY_CHANGE"
    PRODUCT_GROUPING = "PRODUCT_GROUPING"


class RefreshChangedEntityType(str, Enum):
    SOURCE_SNAPSHOT = "SOURCE_SNAPSHOT"
    FACT = "FACT"
    PRODUCT = "PRODUCT"
    OFFER = "OFFER"
    LINK = "LINK"
    POLICY_BUNDLE = "POLICY_BUNDLE"


class RefreshImpactLevel(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RefreshRequiredAction(str, Enum):
    NONE = "NONE"
    REFRESH_DRAFT = "REFRESH_DRAFT"
    REVIEW = "REVIEW"
    REPUBLISH = "REPUBLISH"
    DISABLE_LINK = "DISABLE_LINK"
    SUSPEND_PUBLICATION = "SUSPEND_PUBLICATION"


class RefreshActionType(str, Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    MERGE = "MERGE"
    DELETE = "DELETE"


class RefreshImpactSurface(str, Enum):
    DYNAMIC_PUBLIC_PROJECTION = "DYNAMIC_PUBLIC_PROJECTION"
    ARTICLE_BODY = "ARTICLE_BODY"
    RECOMMENDATION = "RECOMMENDATION"
    COMPARISON_AXIS = "COMPARISON_AXIS"
    METHODOLOGY = "METHODOLOGY"
    PRODUCT_SET = "PRODUCT_SET"
    MAJOR_SPECIFICATION = "MAJOR_SPECIFICATION"


class RefreshReapprovalArea(str, Enum):
    ARTICLE_VERSION = "ARTICLE_VERSION"
    EDITORIAL_REVIEW = "EDITORIAL_REVIEW"
    PUBLICATION_SNAPSHOT = "PUBLICATION_SNAPSHOT"
    RECOMMENDATION_ORDER = "RECOMMENDATION_ORDER"


class RefreshApprovalRequirement(str, Enum):
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"


class RefreshProposalAuthority(str, Enum):
    UNAPPROVED_PROPOSAL = "UNAPPROVED_PROPOSAL"


class RefreshActionStatus(str, Enum):
    PROPOSED = "PROPOSED"


class RefreshExecutionStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


class RefreshProposalFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"
    POLICY_INELIGIBLE = "POLICY_INELIGIBLE"
    POLICY_RESULT_INVALID = "POLICY_RESULT_INVALID"
    FRESHNESS_RESULT_INVALID = "FRESHNESS_RESULT_INVALID"
    CROSS_INPUT_MISMATCH = "CROSS_INPUT_MISMATCH"
    PROPOSER_UNAVAILABLE = "PROPOSER_UNAVAILABLE"
    PROPOSAL_MISMATCH = "PROPOSAL_MISMATCH"


@final
class RefreshProposalFailure(RuntimeError):
    """Closed failure that never retains caller or collaborator material."""

    __slots__ = ("_code",)
    _code: RefreshProposalFailureCode

    def __init__(self, code: RefreshProposalFailureCode) -> None:
        if type(code) is not RefreshProposalFailureCode:
            raise TypeError("invalid refresh proposal failure code")
        RuntimeError.__init__(self, code.value)
        object.__setattr__(self, "_code", code)

    @property
    def code(self) -> str:
        return self._code.value

    def __repr__(self) -> str:
        return f"RefreshProposalFailure(code={self.code!r})"


def fail_refresh_proposal(
    code: RefreshProposalFailureCode = RefreshProposalFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise RefreshProposalFailure(code) from None


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("refresh proposal serialization is not supported")


_IMPACT_ORDER = {
    RefreshImpactLevel.NONE: 0,
    RefreshImpactLevel.LOW: 1,
    RefreshImpactLevel.MEDIUM: 2,
    RefreshImpactLevel.HIGH: 3,
    RefreshImpactLevel.CRITICAL: 4,
}
_ACTION_ORDER = {value: index for index, value in enumerate(RefreshRequiredAction)}
_SURFACE_ORDER = {value: index for index, value in enumerate(RefreshImpactSurface)}
_REAPPROVAL_ORDER = {value: index for index, value in enumerate(RefreshReapprovalArea)}
_SUBSTANTIVE_SURFACES = frozenset(
    {
        RefreshImpactSurface.ARTICLE_BODY,
        RefreshImpactSurface.RECOMMENDATION,
        RefreshImpactSurface.COMPARISON_AXIS,
        RefreshImpactSurface.METHODOLOGY,
        RefreshImpactSurface.PRODUCT_SET,
        RefreshImpactSurface.MAJOR_SPECIFICATION,
    }
)


def _compact_sha256(value: object) -> str:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeError, RecursionError:
        fail_refresh_proposal()
    return hashlib.sha256(payload).hexdigest()


def _require_reference(value: object) -> str:
    if type(value) is not str or _REFERENCE.fullmatch(value) is None:
        fail_refresh_proposal()
    return value


def _require_sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_refresh_proposal()
    return value


def _reference_tuple(value: object) -> tuple[str, ...]:
    if (
        type(value) is not tuple
        or len(value) > MAX_REFRESH_PROPOSAL_DIFFS
        or any(type(item) is not str for item in value)
    ):
        fail_refresh_proposal()
    validated = tuple(_require_reference(item) for item in value)
    if len(set(validated)) != len(validated) or validated != tuple(sorted(validated)):
        fail_refresh_proposal()
    return validated


def _surface_tuple(value: object) -> tuple[RefreshImpactSurface, ...]:
    if (
        type(value) is not tuple
        or not value
        or any(type(item) is not RefreshImpactSurface for item in value)
    ):
        fail_refresh_proposal()
    validated = value
    expected = tuple(sorted(set(validated), key=_SURFACE_ORDER.__getitem__))
    if validated != expected:
        fail_refresh_proposal()
    return validated


def _reapproval_tuple(value: object) -> tuple[RefreshReapprovalArea, ...]:
    if type(value) is not tuple or any(
        type(item) is not RefreshReapprovalArea for item in value
    ):
        fail_refresh_proposal()
    validated = value
    expected = tuple(sorted(set(validated), key=_REAPPROVAL_ORDER.__getitem__))
    if validated != expected:
        fail_refresh_proposal()
    return validated


@final
@dataclass(frozen=True, slots=True, repr=False)
class RefreshDiff(_RedactedValue):
    diff_id: str
    kind: RefreshDiffKind
    change_type: RefreshChangeType
    changed_entity_type: RefreshChangedEntityType
    changed_entity_id: str
    before_sha256: str | None
    after_sha256: str | None
    affected_claim_ids: tuple[str, ...]
    impact_level: RefreshImpactLevel
    required_action: RefreshRequiredAction
    impact_surfaces: tuple[RefreshImpactSurface, ...]
    action_type: RefreshActionType
    deterministic_priority_rank: int
    recommendation_rank_change: bool

    def __post_init__(self) -> None:
        _require_reference(self.diff_id)
        _require_reference(self.changed_entity_id)
        if (
            type(self.kind) is not RefreshDiffKind
            or type(self.change_type) is not RefreshChangeType
            or type(self.changed_entity_type) is not RefreshChangedEntityType
            or type(self.impact_level) is not RefreshImpactLevel
            or type(self.required_action) is not RefreshRequiredAction
            or type(self.action_type) is not RefreshActionType
            or type(self.deterministic_priority_rank) is not int
            or not 1 <= self.deterministic_priority_rank <= MAX_REFRESH_PROPOSAL_DIFFS
            or type(self.recommendation_rank_change) is not bool
        ):
            fail_refresh_proposal()
        claims = _reference_tuple(self.affected_claim_ids)
        surfaces = _surface_tuple(self.impact_surfaces)
        before = (
            None if self.before_sha256 is None else _require_sha256(self.before_sha256)
        )
        after = (
            None if self.after_sha256 is None else _require_sha256(self.after_sha256)
        )
        if self.kind is RefreshDiffKind.ADDED:
            hash_shape_valid = before is None and after is not None
        elif self.kind is RefreshDiffKind.REMOVED:
            hash_shape_valid = before is not None and after is None
        else:
            hash_shape_valid = before is not None and after is not None
        if (
            not hash_shape_valid
            or (
                self.kind
                in {RefreshDiffKind.CHANGED, RefreshDiffKind.RESOLVED_CONFLICT}
                and before == after
            )
            or (
                self.impact_level is RefreshImpactLevel.NONE
                and self.required_action is not RefreshRequiredAction.NONE
            )
            or (
                self.recommendation_rank_change
                and RefreshImpactSurface.RECOMMENDATION not in surfaces
            )
        ):
            fail_refresh_proposal()
        object.__setattr__(self, "affected_claim_ids", claims)
        object.__setattr__(self, "impact_surfaces", surfaces)

    @property
    def fingerprint(self) -> str:
        return _compact_sha256(
            {
                "action_type": self.action_type.value,
                "affected_claim_ids": self.affected_claim_ids,
                "after_sha256": self.after_sha256,
                "before_sha256": self.before_sha256,
                "change_type": self.change_type.value,
                "changed_entity_id": self.changed_entity_id,
                "changed_entity_type": self.changed_entity_type.value,
                "deterministic_priority_rank": self.deterministic_priority_rank,
                "diff_id": self.diff_id,
                "impact_level": self.impact_level.value,
                "impact_surfaces": tuple(item.value for item in self.impact_surfaces),
                "kind": self.kind.value,
                "recommendation_rank_change": self.recommendation_rank_change,
                "required_action": self.required_action.value,
            }
        )


def _owned_diff(value: RefreshDiff) -> RefreshDiff:
    return RefreshDiff(
        diff_id=value.diff_id,
        kind=value.kind,
        change_type=value.change_type,
        changed_entity_type=value.changed_entity_type,
        changed_entity_id=value.changed_entity_id,
        before_sha256=value.before_sha256,
        after_sha256=value.after_sha256,
        affected_claim_ids=value.affected_claim_ids,
        impact_level=value.impact_level,
        required_action=value.required_action,
        impact_surfaces=value.impact_surfaces,
        action_type=value.action_type,
        deterministic_priority_rank=value.deterministic_priority_rank,
        recommendation_rank_change=value.recommendation_rank_change,
    )


@final
@dataclass(frozen=True, slots=True, repr=False)
class RefreshProposalCandidate(_RedactedValue):
    article_version_id: str
    baseline_publication_snapshot_sha256: str
    candidate_snapshot_sha256: str
    diffs: tuple[RefreshDiff, ...]

    def __post_init__(self) -> None:
        _require_reference(self.article_version_id)
        _require_sha256(self.baseline_publication_snapshot_sha256)
        _require_sha256(self.candidate_snapshot_sha256)
        if (
            self.baseline_publication_snapshot_sha256 == self.candidate_snapshot_sha256
            or type(self.diffs) is not tuple
            or not 1 <= len(self.diffs) <= MAX_REFRESH_PROPOSAL_DIFFS
            or any(type(item) is not RefreshDiff for item in self.diffs)
        ):
            fail_refresh_proposal()
        owned_diffs = tuple(_owned_diff(item) for item in self.diffs)
        if tuple(item.deterministic_priority_rank for item in owned_diffs) != tuple(
            range(1, len(owned_diffs) + 1)
        ) or len({item.diff_id for item in owned_diffs}) != len(owned_diffs):
            fail_refresh_proposal()
        object.__setattr__(self, "diffs", owned_diffs)

    @property
    def fingerprint(self) -> str:
        return _compact_sha256(
            {
                "article_version_id": self.article_version_id,
                "baseline_publication_snapshot_sha256": (
                    self.baseline_publication_snapshot_sha256
                ),
                "candidate_snapshot_sha256": self.candidate_snapshot_sha256,
                "diffs": tuple(item.fingerprint for item in self.diffs),
            }
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class FreshnessEvidenceBinding(_RedactedValue):
    evaluation_fingerprint: str
    request_fingerprint: str
    policy_binding_fingerprint: str
    freshness_class_id: str
    state: FreshnessState
    projection_action: FreshnessProjectionAction
    review_action: FreshnessReviewAction
    recommendation_order_action: RecommendationOrderAction
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
        if (
            type(self.freshness_class_id) is not str
            or re.fullmatch(r"FRESH-(?:00[1-9]|01[0-2])", self.freshness_class_id)
            is None
            or type(self.state) is not FreshnessState
            or type(self.projection_action) is not FreshnessProjectionAction
            or type(self.review_action) is not FreshnessReviewAction
            or self.recommendation_order_action
            is not RecommendationOrderAction.FORBIDDEN
            or self.policy_activation
            is not FreshnessPolicyActivation.DISABLED_UNRESOLVED_OD_007
            or self.open_decision_id != REFRESH_PROPOSAL_OPEN_DECISION_ID
            or self.open_decision_status
            is not OpenDecisionStatus.HUMAN_DECISION_REQUIRED
            or self.policy_active is not False
            or self.persistence is not FreshnessPersistenceStatus.NOT_EXECUTED
            or self.attestation is not FreshnessAttestationStatus.NOT_ATTESTED
            or self.live_eligible is not False
        ):
            fail_refresh_proposal(RefreshProposalFailureCode.FRESHNESS_RESULT_INVALID)

    @property
    def fingerprint(self) -> str:
        return _compact_sha256(
            {
                "attestation": self.attestation.value,
                "evaluation_fingerprint": self.evaluation_fingerprint,
                "freshness_class_id": self.freshness_class_id,
                "live_eligible": self.live_eligible,
                "open_decision_id": self.open_decision_id,
                "open_decision_status": self.open_decision_status.value,
                "persistence": self.persistence.value,
                "policy_activation": self.policy_activation.value,
                "policy_active": self.policy_active,
                "policy_binding_fingerprint": self.policy_binding_fingerprint,
                "projection_action": self.projection_action.value,
                "recommendation_order_action": self.recommendation_order_action.value,
                "request_fingerprint": self.request_fingerprint,
                "review_action": self.review_action.value,
                "state": self.state.value,
            }
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class EditorialPolicyEvidenceBinding(_RedactedValue):
    article_version_id: str
    local_result_digest: str
    serialization_profile: str
    status: LocalEvaluationStatus
    local_eligibility: bool
    publication_authorized: bool
    production_eligible: bool
    formal_test_status: ExecutionStatus
    live_validation_status: ExecutionStatus
    staging_status: ExecutionStatus
    release_status: ExecutionStatus
    production_status: ExecutionStatus

    def __post_init__(self) -> None:
        _require_reference(self.article_version_id)
        _require_sha256(self.local_result_digest)
        if (
            self.serialization_profile != REFRESH_PROPOSAL_POLICY_PROFILE
            or self.status is not LocalEvaluationStatus.EVALUATED
            or self.local_eligibility is not True
            or self.publication_authorized is not False
            or self.production_eligible is not False
            or any(
                status is not ExecutionStatus.NOT_EXECUTED
                for status in (
                    self.formal_test_status,
                    self.live_validation_status,
                    self.staging_status,
                    self.release_status,
                    self.production_status,
                )
            )
        ):
            fail_refresh_proposal(RefreshProposalFailureCode.POLICY_RESULT_INVALID)

    @property
    def fingerprint(self) -> str:
        return _compact_sha256(
            {
                "article_version_id": self.article_version_id,
                "formal_test_status": self.formal_test_status.value,
                "live_validation_status": self.live_validation_status.value,
                "local_eligibility": self.local_eligibility,
                "local_result_digest": self.local_result_digest,
                "production_eligible": self.production_eligible,
                "production_status": self.production_status.value,
                "publication_authorized": self.publication_authorized,
                "release_status": self.release_status.value,
                "serialization_profile": self.serialization_profile,
                "staging_status": self.staging_status.value,
                "status": self.status.value,
            }
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class RefreshProposalRequest(_RedactedValue):
    candidate: RefreshProposalCandidate
    freshness: FreshnessEvidenceBinding
    editorial_policy: EditorialPolicyEvidenceBinding

    def __post_init__(self) -> None:
        if (
            type(self.candidate) is not RefreshProposalCandidate
            or type(self.freshness) is not FreshnessEvidenceBinding
            or type(self.editorial_policy) is not EditorialPolicyEvidenceBinding
        ):
            fail_refresh_proposal()
        self.candidate.__post_init__()
        self.freshness.__post_init__()
        self.editorial_policy.__post_init__()
        if (
            self.candidate.article_version_id
            != self.editorial_policy.article_version_id
        ):
            fail_refresh_proposal(RefreshProposalFailureCode.POLICY_RESULT_INVALID)
        recommendation_surface_affected = any(
            RefreshImpactSurface.RECOMMENDATION in diff.impact_surfaces
            for diff in self.candidate.diffs
        )
        freshness_review_required = (
            self.freshness.review_action
            is FreshnessReviewAction.CREATE_REVIEW_CANDIDATE
        )
        if recommendation_surface_affected is not freshness_review_required:
            fail_refresh_proposal(RefreshProposalFailureCode.CROSS_INPUT_MISMATCH)

    @property
    def fingerprint(self) -> str:
        return _compact_sha256(
            {
                "candidate": self.candidate.fingerprint,
                "editorial_policy": self.editorial_policy.fingerprint,
                "freshness": self.freshness.fingerprint,
            }
        )


def _owned_request(value: object) -> RefreshProposalRequest:
    snapshot: RefreshProposalRequest | None = None
    matches = False
    if type(value) is RefreshProposalRequest:
        try:
            source_fingerprint = value.fingerprint
            candidate = RefreshProposalCandidate(
                article_version_id=value.candidate.article_version_id,
                baseline_publication_snapshot_sha256=(
                    value.candidate.baseline_publication_snapshot_sha256
                ),
                candidate_snapshot_sha256=value.candidate.candidate_snapshot_sha256,
                diffs=tuple(_owned_diff(diff) for diff in value.candidate.diffs),
            )
            freshness = FreshnessEvidenceBinding(
                evaluation_fingerprint=value.freshness.evaluation_fingerprint,
                request_fingerprint=value.freshness.request_fingerprint,
                policy_binding_fingerprint=(value.freshness.policy_binding_fingerprint),
                freshness_class_id=value.freshness.freshness_class_id,
                state=value.freshness.state,
                projection_action=value.freshness.projection_action,
                review_action=value.freshness.review_action,
                recommendation_order_action=(
                    value.freshness.recommendation_order_action
                ),
                policy_activation=value.freshness.policy_activation,
                open_decision_id=value.freshness.open_decision_id,
                open_decision_status=value.freshness.open_decision_status,
                policy_active=value.freshness.policy_active,
                persistence=value.freshness.persistence,
                attestation=value.freshness.attestation,
                live_eligible=value.freshness.live_eligible,
            )
            editorial_policy = EditorialPolicyEvidenceBinding(
                article_version_id=value.editorial_policy.article_version_id,
                local_result_digest=value.editorial_policy.local_result_digest,
                serialization_profile=value.editorial_policy.serialization_profile,
                status=value.editorial_policy.status,
                local_eligibility=value.editorial_policy.local_eligibility,
                publication_authorized=(value.editorial_policy.publication_authorized),
                production_eligible=value.editorial_policy.production_eligible,
                formal_test_status=value.editorial_policy.formal_test_status,
                live_validation_status=(value.editorial_policy.live_validation_status),
                staging_status=value.editorial_policy.staging_status,
                release_status=value.editorial_policy.release_status,
                production_status=value.editorial_policy.production_status,
            )
            snapshot = RefreshProposalRequest(
                candidate=candidate,
                freshness=freshness,
                editorial_policy=editorial_policy,
            )
            matches = (
                snapshot == value
                and snapshot.fingerprint == source_fingerprint
                and value.fingerprint == source_fingerprint
            )
        except RefreshProposalFailure:
            raise
        except Exception:
            matches = False
    if snapshot is None or not matches:
        fail_refresh_proposal()
    return snapshot


@final
@dataclass(frozen=True, slots=True, repr=False)
class RefreshImpactAssessment(_RedactedValue):
    source_diff_id: str
    changed_entity_type: RefreshChangedEntityType
    changed_entity_id: str
    affected_claim_ids: tuple[str, ...]
    impact_level: RefreshImpactLevel
    required_action: RefreshRequiredAction
    reapproval_areas: tuple[RefreshReapprovalArea, ...]

    def __post_init__(self) -> None:
        _require_reference(self.source_diff_id)
        _require_reference(self.changed_entity_id)
        if (
            type(self.changed_entity_type) is not RefreshChangedEntityType
            or type(self.impact_level) is not RefreshImpactLevel
            or type(self.required_action) is not RefreshRequiredAction
        ):
            fail_refresh_proposal()
        object.__setattr__(
            self, "affected_claim_ids", _reference_tuple(self.affected_claim_ids)
        )
        object.__setattr__(
            self, "reapproval_areas", _reapproval_tuple(self.reapproval_areas)
        )

    @property
    def fingerprint(self) -> str:
        return _compact_sha256(
            {
                "affected_claim_ids": self.affected_claim_ids,
                "changed_entity_id": self.changed_entity_id,
                "changed_entity_type": self.changed_entity_type.value,
                "impact_level": self.impact_level.value,
                "reapproval_areas": tuple(item.value for item in self.reapproval_areas),
                "required_action": self.required_action.value,
                "source_diff_id": self.source_diff_id,
            }
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class RefreshActionCandidate(_RedactedValue):
    source_diff_id: str
    action_type: RefreshActionType
    deterministic_priority_rank: int
    status: RefreshActionStatus
    approval_requirement: RefreshApprovalRequirement
    authority: RefreshProposalAuthority
    can_change_state: bool
    execution_status: RefreshExecutionStatus

    def __post_init__(self) -> None:
        _require_reference(self.source_diff_id)
        if (
            type(self.action_type) is not RefreshActionType
            or type(self.deterministic_priority_rank) is not int
            or not 1 <= self.deterministic_priority_rank <= MAX_REFRESH_PROPOSAL_DIFFS
            or self.status is not RefreshActionStatus.PROPOSED
            or self.approval_requirement
            is not RefreshApprovalRequirement.HUMAN_APPROVAL_REQUIRED
            or self.authority is not RefreshProposalAuthority.UNAPPROVED_PROPOSAL
            or self.can_change_state is not False
            or self.execution_status is not RefreshExecutionStatus.NOT_EXECUTED
        ):
            fail_refresh_proposal()

    @property
    def fingerprint(self) -> str:
        return _compact_sha256(
            {
                "action_type": self.action_type.value,
                "approval_requirement": self.approval_requirement.value,
                "authority": self.authority.value,
                "can_change_state": self.can_change_state,
                "deterministic_priority_rank": self.deterministic_priority_rank,
                "execution_status": self.execution_status.value,
                "source_diff_id": self.source_diff_id,
                "status": self.status.value,
            }
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class RefreshReapprovalScope(_RedactedValue):
    areas: tuple[RefreshReapprovalArea, ...]
    prior_article_approval_reusable: bool
    recommendation_rank_change: bool
    approval_requirement: RefreshApprovalRequirement

    def __post_init__(self) -> None:
        areas = _reapproval_tuple(self.areas)
        if (
            type(self.prior_article_approval_reusable) is not bool
            or type(self.recommendation_rank_change) is not bool
            or self.approval_requirement
            is not RefreshApprovalRequirement.HUMAN_APPROVAL_REQUIRED
            or self.prior_article_approval_reusable is bool(areas)
            or (
                self.recommendation_rank_change
                and not {
                    RefreshReapprovalArea.ARTICLE_VERSION,
                    RefreshReapprovalArea.EDITORIAL_REVIEW,
                    RefreshReapprovalArea.PUBLICATION_SNAPSHOT,
                    RefreshReapprovalArea.RECOMMENDATION_ORDER,
                }.issubset(areas)
            )
            or (
                not self.recommendation_rank_change
                and RefreshReapprovalArea.RECOMMENDATION_ORDER in areas
            )
        ):
            fail_refresh_proposal()
        object.__setattr__(self, "areas", areas)

    @property
    def fingerprint(self) -> str:
        return _compact_sha256(
            {
                "approval_requirement": self.approval_requirement.value,
                "areas": tuple(item.value for item in self.areas),
                "prior_article_approval_reusable": (
                    self.prior_article_approval_reusable
                ),
                "recommendation_rank_change": self.recommendation_rank_change,
            }
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class RefreshProposal(_RedactedValue):
    mode: RefreshProposalMode
    authority: RefreshProposalAuthority
    request_fingerprint: str
    freshness_evaluation_fingerprint: str
    editorial_policy_result_digest: str
    diffs: tuple[RefreshDiff, ...]
    impacts: tuple[RefreshImpactAssessment, ...]
    action_candidates: tuple[RefreshActionCandidate, ...]
    overall_impact_level: RefreshImpactLevel
    required_actions: tuple[RefreshRequiredAction, ...]
    reapproval_scope: RefreshReapprovalScope
    recommendation_order_action: RecommendationOrderAction
    automatic_reordering_authorized: bool
    can_change_state: bool
    persistence_status: RefreshExecutionStatus
    formal_test_status: RefreshExecutionStatus
    live_validation_status: RefreshExecutionStatus
    staging_status: RefreshExecutionStatus
    release_status: RefreshExecutionStatus
    production_status: RefreshExecutionStatus

    def __post_init__(self) -> None:
        _require_sha256(self.request_fingerprint)
        _require_sha256(self.freshness_evaluation_fingerprint)
        _require_sha256(self.editorial_policy_result_digest)
        if (
            self.mode is not RefreshProposalMode.RECORDED_DEV_CI_ONLY
            or self.authority is not RefreshProposalAuthority.UNAPPROVED_PROPOSAL
            or type(self.diffs) is not tuple
            or type(self.impacts) is not tuple
            or type(self.action_candidates) is not tuple
            or not len(self.diffs) == len(self.impacts) == len(self.action_candidates)
            or not self.diffs
            or len(self.diffs) > MAX_REFRESH_PROPOSAL_DIFFS
            or any(type(item) is not RefreshDiff for item in self.diffs)
            or any(type(item) is not RefreshImpactAssessment for item in self.impacts)
            or any(
                type(item) is not RefreshActionCandidate
                for item in self.action_candidates
            )
            or type(self.overall_impact_level) is not RefreshImpactLevel
            or type(self.required_actions) is not tuple
            or not self.required_actions
            or any(
                type(item) is not RefreshRequiredAction
                for item in self.required_actions
            )
            or type(self.reapproval_scope) is not RefreshReapprovalScope
            or self.recommendation_order_action
            is not RecommendationOrderAction.FORBIDDEN
            or self.automatic_reordering_authorized is not False
            or self.can_change_state is not False
            or any(
                status is not RefreshExecutionStatus.NOT_EXECUTED
                for status in (
                    self.persistence_status,
                    self.formal_test_status,
                    self.live_validation_status,
                    self.staging_status,
                    self.release_status,
                    self.production_status,
                )
            )
        ):
            fail_refresh_proposal()
        owned_diffs = tuple(_owned_diff(item) for item in self.diffs)
        owned_impacts = tuple(
            RefreshImpactAssessment(
                source_diff_id=item.source_diff_id,
                changed_entity_type=item.changed_entity_type,
                changed_entity_id=item.changed_entity_id,
                affected_claim_ids=item.affected_claim_ids,
                impact_level=item.impact_level,
                required_action=item.required_action,
                reapproval_areas=item.reapproval_areas,
            )
            for item in self.impacts
        )
        owned_action_candidates = tuple(
            RefreshActionCandidate(
                source_diff_id=item.source_diff_id,
                action_type=item.action_type,
                deterministic_priority_rank=item.deterministic_priority_rank,
                status=item.status,
                approval_requirement=item.approval_requirement,
                authority=item.authority,
                can_change_state=item.can_change_state,
                execution_status=item.execution_status,
            )
            for item in self.action_candidates
        )
        owned_reapproval_scope = RefreshReapprovalScope(
            areas=self.reapproval_scope.areas,
            prior_article_approval_reusable=(
                self.reapproval_scope.prior_article_approval_reusable
            ),
            recommendation_rank_change=(
                self.reapproval_scope.recommendation_rank_change
            ),
            approval_requirement=self.reapproval_scope.approval_requirement,
        )
        diff_ids = tuple(item.diff_id for item in owned_diffs)
        priority_ranks = tuple(item.deterministic_priority_rank for item in owned_diffs)
        if len(set(diff_ids)) != len(diff_ids) or priority_ranks != tuple(
            range(1, len(owned_diffs) + 1)
        ):
            fail_refresh_proposal()
        expected_actions = tuple(
            sorted(set(self.required_actions), key=_ACTION_ORDER.__getitem__)
        )
        expected_impacts = tuple(
            RefreshImpactAssessment(
                source_diff_id=diff.diff_id,
                changed_entity_type=diff.changed_entity_type,
                changed_entity_id=diff.changed_entity_id,
                affected_claim_ids=diff.affected_claim_ids,
                impact_level=diff.impact_level,
                required_action=diff.required_action,
                reapproval_areas=_areas_for(diff),
            )
            for diff in owned_diffs
        )
        expected_action_candidates = tuple(
            RefreshActionCandidate(
                source_diff_id=diff.diff_id,
                action_type=diff.action_type,
                deterministic_priority_rank=diff.deterministic_priority_rank,
                status=RefreshActionStatus.PROPOSED,
                approval_requirement=(
                    RefreshApprovalRequirement.HUMAN_APPROVAL_REQUIRED
                ),
                authority=RefreshProposalAuthority.UNAPPROVED_PROPOSAL,
                can_change_state=False,
                execution_status=RefreshExecutionStatus.NOT_EXECUTED,
            )
            for diff in owned_diffs
        )
        expected_reapproval_areas = tuple(
            sorted(
                {
                    area
                    for impact in expected_impacts
                    for area in impact.reapproval_areas
                },
                key=_REAPPROVAL_ORDER.__getitem__,
            )
        )
        expected_rank_change = any(
            item.recommendation_rank_change for item in owned_diffs
        )
        expected_reapproval_scope = RefreshReapprovalScope(
            areas=expected_reapproval_areas,
            prior_article_approval_reusable=not expected_reapproval_areas,
            recommendation_rank_change=expected_rank_change,
            approval_requirement=RefreshApprovalRequirement.HUMAN_APPROVAL_REQUIRED,
        )
        non_empty_required_actions = {
            item.required_action
            for item in owned_diffs
            if item.required_action is not RefreshRequiredAction.NONE
        }
        expected_required_actions = (
            tuple(
                sorted(
                    non_empty_required_actions,
                    key=_ACTION_ORDER.__getitem__,
                )
            )
            if non_empty_required_actions
            else (RefreshRequiredAction.NONE,)
        )
        if (
            self.required_actions != expected_actions
            or self.required_actions != expected_required_actions
            or owned_impacts != expected_impacts
            or owned_action_candidates != expected_action_candidates
            or owned_reapproval_scope != expected_reapproval_scope
            or tuple(item.source_diff_id for item in owned_impacts)
            != tuple(item.diff_id for item in owned_diffs)
            or tuple(item.source_diff_id for item in owned_action_candidates)
            != tuple(item.diff_id for item in owned_diffs)
            or tuple(
                item.deterministic_priority_rank for item in owned_action_candidates
            )
            != tuple(item.deterministic_priority_rank for item in owned_diffs)
            or tuple(item.action_type for item in owned_action_candidates)
            != tuple(item.action_type for item in owned_diffs)
            or self.overall_impact_level
            is not max(
                owned_diffs, key=lambda item: _IMPACT_ORDER[item.impact_level]
            ).impact_level
            or owned_reapproval_scope.recommendation_rank_change
            is not expected_rank_change
        ):
            fail_refresh_proposal()
        object.__setattr__(self, "diffs", owned_diffs)
        object.__setattr__(self, "impacts", owned_impacts)
        object.__setattr__(self, "action_candidates", owned_action_candidates)
        object.__setattr__(self, "reapproval_scope", owned_reapproval_scope)

    @property
    def fingerprint(self) -> str:
        return _compact_sha256(
            {
                "action_candidates": tuple(
                    item.fingerprint for item in self.action_candidates
                ),
                "authority": self.authority.value,
                "automatic_reordering_authorized": (
                    self.automatic_reordering_authorized
                ),
                "can_change_state": self.can_change_state,
                "diffs": tuple(item.fingerprint for item in self.diffs),
                "editorial_policy_result_digest": (self.editorial_policy_result_digest),
                "formal_test_status": self.formal_test_status.value,
                "freshness_evaluation_fingerprint": (
                    self.freshness_evaluation_fingerprint
                ),
                "impacts": tuple(item.fingerprint for item in self.impacts),
                "live_validation_status": self.live_validation_status.value,
                "mode": self.mode.value,
                "overall_impact_level": self.overall_impact_level.value,
                "persistence_status": self.persistence_status.value,
                "production_status": self.production_status.value,
                "reapproval_scope": self.reapproval_scope.fingerprint,
                "recommendation_order_action": self.recommendation_order_action.value,
                "release_status": self.release_status.value,
                "request_fingerprint": self.request_fingerprint,
                "required_actions": tuple(item.value for item in self.required_actions),
                "staging_status": self.staging_status.value,
            }
        )


def _areas_for(diff: RefreshDiff) -> tuple[RefreshReapprovalArea, ...]:
    areas: set[RefreshReapprovalArea] = set()
    if any(surface in _SUBSTANTIVE_SURFACES for surface in diff.impact_surfaces):
        areas = areas | {
            RefreshReapprovalArea.ARTICLE_VERSION,
            RefreshReapprovalArea.EDITORIAL_REVIEW,
            RefreshReapprovalArea.PUBLICATION_SNAPSHOT,
        }
    if diff.recommendation_rank_change:
        areas = areas | {RefreshReapprovalArea.RECOMMENDATION_ORDER}
    return tuple(sorted(areas, key=_REAPPROVAL_ORDER.__getitem__))


def build_refresh_proposal(request: RefreshProposalRequest) -> RefreshProposal:
    """Build one proposal without mutation, I/O, ranking, or authorization."""

    snapshot = _owned_request(request)
    owned_diffs = tuple(_owned_diff(diff) for diff in snapshot.candidate.diffs)
    impacts = tuple(
        RefreshImpactAssessment(
            source_diff_id=diff.diff_id,
            changed_entity_type=diff.changed_entity_type,
            changed_entity_id=diff.changed_entity_id,
            affected_claim_ids=diff.affected_claim_ids,
            impact_level=diff.impact_level,
            required_action=diff.required_action,
            reapproval_areas=_areas_for(diff),
        )
        for diff in owned_diffs
    )
    action_candidates = tuple(
        RefreshActionCandidate(
            source_diff_id=diff.diff_id,
            action_type=diff.action_type,
            deterministic_priority_rank=diff.deterministic_priority_rank,
            status=RefreshActionStatus.PROPOSED,
            approval_requirement=RefreshApprovalRequirement.HUMAN_APPROVAL_REQUIRED,
            authority=RefreshProposalAuthority.UNAPPROVED_PROPOSAL,
            can_change_state=False,
            execution_status=RefreshExecutionStatus.NOT_EXECUTED,
        )
        for diff in owned_diffs
    )
    all_areas = tuple(
        sorted(
            {area for impact in impacts for area in impact.reapproval_areas},
            key=_REAPPROVAL_ORDER.__getitem__,
        )
    )
    rank_change = any(diff.recommendation_rank_change for diff in owned_diffs)
    non_empty_actions = {
        diff.required_action
        for diff in owned_diffs
        if diff.required_action is not RefreshRequiredAction.NONE
    }
    required_actions = (
        tuple(sorted(non_empty_actions, key=_ACTION_ORDER.__getitem__))
        if non_empty_actions
        else (RefreshRequiredAction.NONE,)
    )
    overall_impact = max(
        owned_diffs,
        key=lambda item: _IMPACT_ORDER[item.impact_level],
    ).impact_level
    return RefreshProposal(
        mode=RefreshProposalMode.RECORDED_DEV_CI_ONLY,
        authority=RefreshProposalAuthority.UNAPPROVED_PROPOSAL,
        request_fingerprint=snapshot.fingerprint,
        freshness_evaluation_fingerprint=(snapshot.freshness.evaluation_fingerprint),
        editorial_policy_result_digest=(snapshot.editorial_policy.local_result_digest),
        diffs=owned_diffs,
        impacts=impacts,
        action_candidates=action_candidates,
        overall_impact_level=overall_impact,
        required_actions=required_actions,
        reapproval_scope=RefreshReapprovalScope(
            areas=all_areas,
            prior_article_approval_reusable=not all_areas,
            recommendation_rank_change=rank_change,
            approval_requirement=RefreshApprovalRequirement.HUMAN_APPROVAL_REQUIRED,
        ),
        recommendation_order_action=RecommendationOrderAction.FORBIDDEN,
        automatic_reordering_authorized=False,
        can_change_state=False,
        persistence_status=RefreshExecutionStatus.NOT_EXECUTED,
        formal_test_status=RefreshExecutionStatus.NOT_EXECUTED,
        live_validation_status=RefreshExecutionStatus.NOT_EXECUTED,
        staging_status=RefreshExecutionStatus.NOT_EXECUTED,
        release_status=RefreshExecutionStatus.NOT_EXECUTED,
        production_status=RefreshExecutionStatus.NOT_EXECUTED,
    )


__all__ = [
    "MAX_RECORDED_REFRESH_PROPOSALS",
    "MAX_REFRESH_PROPOSAL_DIFFS",
    "EditorialPolicyEvidenceBinding",
    "FreshnessEvidenceBinding",
    "RefreshActionCandidate",
    "RefreshActionStatus",
    "RefreshActionType",
    "RefreshApprovalRequirement",
    "RefreshChangeType",
    "RefreshChangedEntityType",
    "RefreshDiff",
    "RefreshDiffKind",
    "RefreshExecutionStatus",
    "RefreshImpactAssessment",
    "RefreshImpactLevel",
    "RefreshImpactSurface",
    "RefreshProposal",
    "RefreshProposalAuthority",
    "RefreshProposalCandidate",
    "RefreshProposalFailure",
    "RefreshProposalFailureCode",
    "RefreshProposalMode",
    "RefreshProposalRequest",
    "RefreshReapprovalArea",
    "RefreshReapprovalScope",
    "RefreshRequiredAction",
    "build_refresh_proposal",
    "fail_refresh_proposal",
]

"""Recorded-local PUBADM-004 values for ST-0901 PR3.

All values in this module belong only to the
``ST0901_PR3_RECORDED_LOCAL_V1`` ENV-DEV/CI fixture seam. They are not
authentication, attestation, a signature, canonical authorization policy,
durable audit evidence, a public API contract, or Story acceptance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, EnumType
import hashlib
import json
import re
from typing import Any, Callable, Final, NoReturn, SupportsIndex, cast, final
from uuid import RFC_4122, UUID

from raos.domain.iam.authorization import (
    ActionCode,
    AuthorizationDecision,
    AuthorizationDecisionReason,
    AuthorizationGrant,
    AuthorizationTarget,
    CorrelationId,
    DecisionEffect,
    EntitlementRevision,
    PermissionScope,
    PolicyRevision,
    ResourceScope,
    ResourceScopeKind,
    ResourceState,
    RuleId,
)
from raos.domain.portfolio.workflow import IdempotencyKey
from raos.domain.publishing.review_workflow import (
    ArticleVersionId,
    ChecklistItemId,
    ChecklistItemStatus,
    ChecklistResult,
    DecisionSummary,
    EvidenceId,
    EvidenceReference,
    HumanComment,
    PrincipalId,
    ReviewAssignment,
    ReviewAssignmentId,
    ReviewAssignmentState,
    ReviewDecisionDraft,
    ReviewDecisionId,
    ReviewDecisionReference,
    ReviewType,
    Sha256Digest,
    StructurallyValidatedReviewDecision,
    UtcTimestamp,
    validate_review_decision,
)


RECORDED_LOCAL_PROFILE: Final = "ST0901_PR3_RECORDED_LOCAL_V1"
_REDACTED: Final = "<redacted-st0901-pr3-recorded-local>"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


class _ClosedEnumType(EnumType):
    """Reject unknown vocabulary without retaining rejected caller material."""

    def __getitem__(cls, name: str) -> Any:
        if type(name) is not str:
            fail_review_decision_operation()
        member: Any
        for member in cls:
            if member.name == name:
                return member
        fail_review_decision_operation()

    def __call__(
        cls,
        value: Any,
        names: Any = None,
        *values: Any,
        **kwargs: Any,
    ) -> Any:
        if names is not None or values or kwargs:
            fail_review_decision_operation()
        member: Any
        for member in cls:
            if value is member:
                return member
        if type(value) is not str:
            fail_review_decision_operation()
        for member in cls:
            if member.value == value:
                return member
        fail_review_decision_operation()


class _ClosedEnum(str, Enum, metaclass=_ClosedEnumType):
    @classmethod
    def _missing_(cls, value: object) -> NoReturn:
        del cls, value
        fail_review_decision_operation()


class ReviewDecisionOperation(_ClosedEnum):
    RECORD = "PUBADM-004"


class RecordedSubjectKind(_ClosedEnum):
    HUMAN = "HUMAN"
    SERVICE = "SERVICE"


class RecordedSubjectStatus(_ClosedEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class RecordedExecution(_ClosedEnum):
    RECORDED_ONLY = "RECORDED_ONLY"
    NOT_EXECUTED = "NOT_EXECUTED"


class RecordedReadiness(_ClosedEnum):
    NOT_READY = "NOT_READY"


class RecordedAuditAction(_ClosedEnum):
    DECISION_RECORD = "review_decision_record"


class ReviewDecisionOperationFailureCode(_ClosedEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    LOCAL_EXCHANGE_UNAVAILABLE = "LOCAL_EXCHANGE_UNAVAILABLE"
    OUTCOME_MISMATCH = "OUTCOME_MISMATCH"
    IDEMPOTENCY_MISMATCH = "IDEMPOTENCY_MISMATCH"
    HISTORY_MISMATCH = "HISTORY_MISMATCH"


class ReviewDecisionOperationFailure(RuntimeError):
    """Closed immutable failure that never retains rejected input."""

    __slots__ = ("_code",)
    _code: ReviewDecisionOperationFailureCode

    def __init__(self, code: ReviewDecisionOperationFailureCode) -> None:
        if type(code) is not ReviewDecisionOperationFailureCode:
            raise TypeError("invalid review decision operation failure code")
        object.__setattr__(self, "_code", code)
        RuntimeError.__init__(self, code.value)

    @property
    def code(self) -> ReviewDecisionOperationFailureCode:
        return self._code

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("ReviewDecisionOperationFailure is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("ReviewDecisionOperationFailure is immutable")

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"ReviewDecisionOperationFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("review decision operation failure serialization denied")


def fail_review_decision_operation(
    code: ReviewDecisionOperationFailureCode = (
        ReviewDecisionOperationFailureCode.INVALID_ARGUMENT
    ),
) -> NoReturn:
    raise ReviewDecisionOperationFailure(code) from None


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded review decision serialization denied")


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedSha256(_RedactedValue):
    """Implementation-local lower-case SHA-256 value."""

    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _SHA256.fullmatch(self.value) is None:
            fail_review_decision_operation()


def _revalidation_failed(callback: Callable[[], object]) -> bool:
    try:
        callback()
    except Exception:
        return True
    return False


def _canonical_bytes(payload: dict[str, object]) -> bytes:
    encoded: bytes | None = None
    try:
        encoded = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeEncodeError, RecursionError:
        pass
    if encoded is None:
        fail_review_decision_operation()
    return encoded


def _canonical_sha256(payload: dict[str, object]) -> RecordedSha256:
    return RecordedSha256(hashlib.sha256(_canonical_bytes(payload)).hexdigest())


def _require_sha256(value: object) -> RecordedSha256:
    if type(value) is not RecordedSha256:
        fail_review_decision_operation()
    return RecordedSha256(value.value)


def _require_correlation(value: object) -> CorrelationId:
    if type(value) is not CorrelationId:
        fail_review_decision_operation()
    if _revalidation_failed(lambda: CorrelationId(value.value)):
        fail_review_decision_operation()
    return CorrelationId(value.value)


def _require_idempotency_key(value: object) -> IdempotencyKey:
    if type(value) is not IdempotencyKey:
        fail_review_decision_operation()
    if _revalidation_failed(lambda: IdempotencyKey(value.value)):
        fail_review_decision_operation()
    return IdempotencyKey(value.value)


def _normalize_target(value: object) -> AuthorizationTarget:
    """Detach one exact target while assigning no PR3 scope semantics."""

    if type(value) is not AuthorizationTarget:
        fail_review_decision_operation()
    normalized: AuthorizationTarget | None = None
    failed = False
    try:
        scope = value.scope
        if (
            type(scope) is not ResourceScope
            or type(scope.kind) is not ResourceScopeKind
            or type(scope.site_id) is not UUID
            or type(scope.resource_id) is not UUID
        ):
            fail_review_decision_operation()
        state = value.state
        if state is not None and type(state) is not ResourceState:
            fail_review_decision_operation()
        normalized = AuthorizationTarget(
            scope=ResourceScope(
                kind=scope.kind,
                site_id=UUID(int=scope.site_id.int),
                resource_id=UUID(int=scope.resource_id.int),
            ),
            state=None if state is None else ResourceState(state.value),
        )
        if normalized != value:
            fail_review_decision_operation()
    except Exception:
        failed = True
    if failed or normalized is None:
        fail_review_decision_operation()
    return normalized


def _target_payload(target: AuthorizationTarget) -> list[str]:
    return list(_normalize_target(target).canonical_key)


def _clone_uuid_value(value: Any, expected_type: type[Any]) -> Any:
    if type(value) is not expected_type:
        fail_review_decision_operation()
    normalized: Any = None
    failed = False
    try:
        raw = value.value
        if type(raw) is not UUID:
            fail_review_decision_operation()
        normalized = expected_type(UUID(int=raw.int))
    except Exception:
        failed = True
    if failed or type(normalized) is not expected_type:
        fail_review_decision_operation()
    return normalized


def _clone_timestamp(value: object) -> UtcTimestamp:
    if type(value) is not UtcTimestamp:
        fail_review_decision_operation()
    normalized: UtcTimestamp | None = None
    failed = False
    try:
        raw = value.value
        if type(raw) is not datetime or raw.tzinfo is not timezone.utc:
            fail_review_decision_operation()
        normalized = UtcTimestamp(
            datetime(
                raw.year,
                raw.month,
                raw.day,
                raw.hour,
                raw.minute,
                raw.second,
                raw.microsecond,
                tzinfo=timezone.utc,
                fold=raw.fold,
            )
        )
    except Exception:
        failed = True
    if failed or normalized is None:
        fail_review_decision_operation()
    return normalized


def _clone_timestamp_or_none(value: object) -> UtcTimestamp | None:
    if value is None:
        return None
    return _clone_timestamp(value)


def _timestamp_text(value: UtcTimestamp) -> str:
    return _clone_timestamp(value).value.isoformat().replace("+00:00", "Z")


def _clone_decision_reference(
    value: object,
) -> ReviewDecisionReference | None:
    if value is None:
        return None
    if type(value) is not ReviewDecisionReference:
        fail_review_decision_operation()
    return ReviewDecisionReference(
        decision_id=_clone_uuid_value(value.decision_id, ReviewDecisionId),
        review_assignment_id=_clone_uuid_value(
            value.review_assignment_id, ReviewAssignmentId
        ),
        article_version_id=_clone_uuid_value(
            value.article_version_id, ArticleVersionId
        ),
    )


def _clone_assignment(value: object) -> ReviewAssignment:
    if type(value) is not ReviewAssignment:
        fail_review_decision_operation()
    normalized: ReviewAssignment | None = None
    failed = False
    try:
        if type(value.review_type) is not ReviewType:
            fail_review_decision_operation()
        if type(value.status) is not ReviewAssignmentState:
            fail_review_decision_operation()
        normalized = ReviewAssignment(
            assignment_id=_clone_uuid_value(value.assignment_id, ReviewAssignmentId),
            article_version_id=_clone_uuid_value(
                value.article_version_id, ArticleVersionId
            ),
            review_type=value.review_type,
            assigned_by=_clone_uuid_value(value.assigned_by, PrincipalId),
            assigned_to=_clone_uuid_value(value.assigned_to, PrincipalId),
            priority=value.priority,
            status=value.status,
            started_at=_clone_timestamp_or_none(value.started_at),
            completed_at=_clone_timestamp_or_none(value.completed_at),
            cancelled_at=_clone_timestamp_or_none(value.cancelled_at),
            created_at=_clone_timestamp(value.created_at),
            updated_at=_clone_timestamp(value.updated_at),
            lock_version=value.lock_version,
            completion_decision_reference=_clone_decision_reference(
                value.completion_decision_reference
            ),
        )
    except Exception:
        failed = True
    if failed or normalized is None or normalized != value:
        fail_review_decision_operation()
    return normalized


def _clone_evidence_reference(value: object) -> EvidenceReference:
    if type(value) is not EvidenceReference:
        fail_review_decision_operation()
    normalized: EvidenceReference | None = None
    failed = False
    try:
        if type(value.sha256) is not Sha256Digest:
            fail_review_decision_operation()
        normalized = EvidenceReference(
            evidence_id=_clone_uuid_value(value.evidence_id, EvidenceId),
            sha256=Sha256Digest(value.sha256.value),
            review_assignment_id=_clone_uuid_value(
                value.review_assignment_id, ReviewAssignmentId
            ),
            article_version_id=_clone_uuid_value(
                value.article_version_id, ArticleVersionId
            ),
        )
    except Exception:
        failed = True
    if failed or normalized is None or normalized != value:
        fail_review_decision_operation()
    return normalized


def _clone_checklist_result(value: object) -> ChecklistResult:
    if type(value) is not ChecklistResult:
        fail_review_decision_operation()
    normalized: ChecklistResult | None = None
    failed = False
    try:
        if (
            type(value.item_id) is not ChecklistItemId
            or type(value.status) is not ChecklistItemStatus
            or type(value.evidence) is not tuple
        ):
            fail_review_decision_operation()
        comment = value.human_comment
        if comment is not None and type(comment) is not HumanComment:
            fail_review_decision_operation()
        normalized = ChecklistResult(
            item_id=ChecklistItemId(value.item_id.value),
            status=value.status,
            evidence=tuple(_clone_evidence_reference(item) for item in value.evidence),
            human_comment=None if comment is None else HumanComment(comment.value),
        )
    except Exception:
        failed = True
    if failed or normalized is None or normalized != value:
        fail_review_decision_operation()
    return normalized


def _clone_validated_decision(
    value: object,
) -> StructurallyValidatedReviewDecision:
    if type(value) is not StructurallyValidatedReviewDecision:
        fail_review_decision_operation()
    normalized: StructurallyValidatedReviewDecision | None = None
    failed = False
    try:
        if (
            type(value.summary) is not DecisionSummary
            or type(value.checklist_results) is not tuple
        ):
            fail_review_decision_operation()
        normalized = StructurallyValidatedReviewDecision(
            review_assignment_id=_clone_uuid_value(
                value.review_assignment_id, ReviewAssignmentId
            ),
            article_version_id=_clone_uuid_value(
                value.article_version_id, ArticleVersionId
            ),
            decision=value.decision,
            summary=DecisionSummary(value.summary.value),
            checklist_version=value.checklist_version,
            checklist_sha256=value.checklist_sha256,
            checklist_results=tuple(
                _clone_checklist_result(item) for item in value.checklist_results
            ),
        )
    except Exception:
        failed = True
    if failed or normalized is None or normalized != value:
        fail_review_decision_operation()
    return normalized


def _validated_to_draft(
    value: StructurallyValidatedReviewDecision,
) -> ReviewDecisionDraft:
    normalized = _clone_validated_decision(value)
    return ReviewDecisionDraft(
        review_assignment_id=normalized.review_assignment_id,
        article_version_id=normalized.article_version_id,
        decision=normalized.decision,
        summary=normalized.summary,
        checklist_version=normalized.checklist_version,
        checklist_sha256=normalized.checklist_sha256,
        checklist_results=normalized.checklist_results,
    )


def _assignment_payload(value: ReviewAssignment) -> dict[str, object]:
    assignment = _clone_assignment(value)
    reference = assignment.completion_decision_reference
    return {
        "article_version_id": str(assignment.article_version_id.value),
        "assigned_by": str(assignment.assigned_by.value),
        "assigned_to": str(assignment.assigned_to.value),
        "assignment_id": str(assignment.assignment_id.value),
        "cancelled_at": (
            None
            if assignment.cancelled_at is None
            else _timestamp_text(assignment.cancelled_at)
        ),
        "completed_at": (
            None
            if assignment.completed_at is None
            else _timestamp_text(assignment.completed_at)
        ),
        "completion_decision_reference": (
            None
            if reference is None
            else {
                "article_version_id": str(reference.article_version_id.value),
                "decision_id": str(reference.decision_id.value),
                "review_assignment_id": str(reference.review_assignment_id.value),
            }
        ),
        "created_at": _timestamp_text(assignment.created_at),
        "lock_version": assignment.lock_version,
        "priority": assignment.priority,
        "review_type": assignment.review_type.value,
        "started_at": (
            None
            if assignment.started_at is None
            else _timestamp_text(assignment.started_at)
        ),
        "status": assignment.status.value,
        "updated_at": _timestamp_text(assignment.updated_at),
    }


def _evidence_payload(value: EvidenceReference) -> dict[str, str]:
    reference = _clone_evidence_reference(value)
    return {
        "article_version_id": str(reference.article_version_id.value),
        "evidence_id": str(reference.evidence_id.value),
        "review_assignment_id": str(reference.review_assignment_id.value),
        "sha256": reference.sha256.value,
    }


def _validated_decision_payload(
    value: StructurallyValidatedReviewDecision,
) -> dict[str, object]:
    decision = _clone_validated_decision(value)
    return {
        "article_version_id": str(decision.article_version_id.value),
        "checklist_results": [
            {
                "evidence": [_evidence_payload(item) for item in result.evidence],
                "human_comment": (
                    None if result.human_comment is None else result.human_comment.value
                ),
                "item_id": result.item_id.value,
                "status": result.status.value,
            }
            for result in decision.checklist_results
        ],
        "checklist_sha256": decision.checklist_sha256,
        "checklist_version": decision.checklist_version,
        "decision": decision.decision.value,
        "review_assignment_id": str(decision.review_assignment_id.value),
        "summary": decision.summary.value,
    }


def _assignment_sha256(value: ReviewAssignment) -> RecordedSha256:
    return _canonical_sha256(_assignment_payload(value))


def _validated_decision_sha256(
    value: StructurallyValidatedReviewDecision,
) -> RecordedSha256:
    return _canonical_sha256(_validated_decision_payload(value))


def _validated_from_request(
    assignment: object,
    draft: object,
) -> StructurallyValidatedReviewDecision:
    """Preserve PR1's stable APPROVE/N/A failure precedence."""

    return validate_review_decision(
        cast(ReviewAssignment, assignment),
        cast(ReviewDecisionDraft, draft),
    )


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordReviewDecisionRequest(_RedactedValue):
    """Negative-only recorded-local PUBADM-004 command."""

    correlation_id: CorrelationId
    target: AuthorizationTarget
    assignment: ReviewAssignment
    draft: ReviewDecisionDraft
    idempotency_key: IdempotencyKey
    supersedes_decision_id: ReviewDecisionId | None = None
    operation: ReviewDecisionOperation = field(
        init=False, default=ReviewDecisionOperation.RECORD
    )
    assignment_sha256: RecordedSha256 = field(init=False)
    decision_sha256: RecordedSha256 = field(init=False)
    request_sha256: RecordedSha256 = field(init=False)

    def __post_init__(self) -> None:
        validated = _validated_from_request(self.assignment, self.draft)
        assignment = _clone_assignment(self.assignment)
        decision = _clone_validated_decision(validated)
        draft = _validated_to_draft(decision)
        correlation = _require_correlation(self.correlation_id)
        target = _normalize_target(self.target)
        idempotency_key = _require_idempotency_key(self.idempotency_key)
        supersedes = (
            None
            if self.supersedes_decision_id is None
            else _clone_uuid_value(self.supersedes_decision_id, ReviewDecisionId)
        )
        object.__setattr__(self, "assignment", assignment)
        object.__setattr__(self, "draft", draft)
        object.__setattr__(self, "correlation_id", correlation)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "idempotency_key", idempotency_key)
        object.__setattr__(self, "supersedes_decision_id", supersedes)
        object.__setattr__(self, "assignment_sha256", _assignment_sha256(assignment))
        object.__setattr__(
            self, "decision_sha256", _validated_decision_sha256(decision)
        )
        object.__setattr__(self, "request_sha256", self._expected_sha256())

    @property
    def validated_decision(self) -> StructurallyValidatedReviewDecision:
        return _clone_validated_decision(
            validate_review_decision(self.assignment, self.draft)
        )

    def _payload(self) -> dict[str, object]:
        return {
            "article_version_id": str(self.assignment.article_version_id.value),
            "assignment_id": str(self.assignment.assignment_id.value),
            "assignment_sha256": self.assignment_sha256.value,
            "correlation_id": self.correlation_id.value,
            "decision_sha256": self.decision_sha256.value,
            "operation_id": self.operation.value,
            "profile": RECORDED_LOCAL_PROFILE,
            "supersedes_decision_id": (
                None
                if self.supersedes_decision_id is None
                else str(self.supersedes_decision_id.value)
            ),
            "target": _target_payload(self.target),
        }

    def _expected_sha256(self) -> RecordedSha256:
        return _canonical_sha256(self._payload())

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        return _canonical_bytes(self._payload())

    def require_valid(self) -> None:
        validated = _validated_from_request(self.assignment, self.draft)
        if self.operation is not ReviewDecisionOperation.RECORD:
            fail_review_decision_operation()
        assignment = _clone_assignment(self.assignment)
        decision = _clone_validated_decision(validated)
        _require_correlation(self.correlation_id)
        _normalize_target(self.target)
        _require_idempotency_key(self.idempotency_key)
        if self.supersedes_decision_id is not None:
            _clone_uuid_value(self.supersedes_decision_id, ReviewDecisionId)
        if (
            _require_sha256(self.assignment_sha256) != _assignment_sha256(assignment)
            or _require_sha256(self.decision_sha256)
            != _validated_decision_sha256(decision)
            or _require_sha256(self.request_sha256) != self._expected_sha256()
        ):
            fail_review_decision_operation()


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedIdentityProjection(_RedactedValue):
    """Synthetic local identity coordinate; it grants no authority."""

    principal_id: PrincipalId
    subject_kind: RecordedSubjectKind
    subject_status: RecordedSubjectStatus

    def __post_init__(self) -> None:
        principal = _clone_uuid_value(self.principal_id, PrincipalId)
        if (
            type(self.subject_kind) is not RecordedSubjectKind
            or type(self.subject_status) is not RecordedSubjectStatus
        ):
            fail_review_decision_operation()
        object.__setattr__(self, "principal_id", principal)

    def require_valid(self) -> None:
        if (
            type(self.subject_kind) is not RecordedSubjectKind
            or type(self.subject_status) is not RecordedSubjectStatus
            or _clone_uuid_value(self.principal_id, PrincipalId) != self.principal_id
        ):
            fail_review_decision_operation()


def _identity_payload(value: RecordedIdentityProjection) -> dict[str, str]:
    value.require_valid()
    return {
        "principal_id": str(value.principal_id.value),
        "subject_kind": value.subject_kind.value,
        "subject_status": value.subject_status.value,
    }


def _require_permission(value: object) -> PermissionScope:
    if type(value) is not PermissionScope:
        fail_review_decision_operation()
    if _revalidation_failed(lambda: PermissionScope(value.value)):
        fail_review_decision_operation()
    return PermissionScope(value.value)


def _normalize_grant(value: object) -> AuthorizationGrant:
    """Return a detached exact ALLOW/RULE_MATCH ST-0403 grant."""

    if type(value) is not AuthorizationGrant:
        fail_review_decision_operation()
    normalized: AuthorizationGrant | None = None
    failed = False
    try:
        decision = object.__getattribute__(value, "_decision")
        if (
            object.__getattribute__(value, "_sealed") is not True
            or type(decision) is not AuthorizationDecision
            or object.__getattribute__(decision, "_sealed") is not True
            or type(decision.correlation_id) is not CorrelationId
            or type(decision.effect) is not DecisionEffect
            or decision.effect is not DecisionEffect.ALLOW
            or type(decision.reason) is not AuthorizationDecisionReason
            or decision.reason is not AuthorizationDecisionReason.RULE_MATCH
            or type(decision.policy_revision) is not PolicyRevision
            or type(decision.policy_fingerprint) is not str
            or type(decision.entitlement_revision) is not EntitlementRevision
            or type(decision.matched_rule_id) is not RuleId
            or type(decision.action) is not ActionCode
            or type(decision.target) is not AuthorizationTarget
        ):
            fail_review_decision_operation()
        normalized_decision = AuthorizationDecision(
            correlation_id=CorrelationId(decision.correlation_id.value),
            effect=decision.effect,
            reason=decision.reason,
            policy_revision=PolicyRevision(decision.policy_revision.value),
            policy_fingerprint=decision.policy_fingerprint,
            entitlement_revision=EntitlementRevision(
                decision.entitlement_revision.value
            ),
            matched_rule_id=RuleId(decision.matched_rule_id.value),
            action=ActionCode(decision.action.value),
            target=_normalize_target(decision.target),
        )
        normalized = AuthorizationGrant(recorded_decision=normalized_decision)
    except Exception:
        failed = True
    if failed or normalized is None:
        fail_review_decision_operation()
    return normalized


def _grant_payload(value: AuthorizationGrant) -> dict[str, object]:
    grant = _normalize_grant(value)
    decision = object.__getattribute__(grant, "_decision")
    assert type(decision) is AuthorizationDecision
    matched_rule = decision.matched_rule_id
    assert type(matched_rule) is RuleId
    return {
        "action": decision.action.value,
        "correlation_id": decision.correlation_id.value,
        "effect": decision.effect.value,
        "entitlement_revision": decision.entitlement_revision.value,
        "matched_rule_id": matched_rule.value,
        "policy_fingerprint": decision.policy_fingerprint,
        "policy_revision": decision.policy_revision.value,
        "reason": decision.reason.value,
        "target": _target_payload(decision.target),
    }


def _authorization_payload(
    *,
    request: RecordReviewDecisionRequest,
    grant: AuthorizationGrant,
    permission_scope: PermissionScope,
    actor: RecordedIdentityProjection,
) -> dict[str, object]:
    request.require_valid()
    return {
        "actor": _identity_payload(actor),
        "article_version_id": str(request.assignment.article_version_id.value),
        "assignment_id": str(request.assignment.assignment_id.value),
        "assignment_sha256": request.assignment_sha256.value,
        "correlation_id": request.correlation_id.value,
        "decision_sha256": request.decision_sha256.value,
        "grant": _grant_payload(grant),
        "operation_id": request.operation.value,
        "permission_scope": _require_permission(permission_scope).value,
        "profile": RECORDED_LOCAL_PROFILE,
        "request_sha256": request.request_sha256.value,
        "target": _target_payload(request.target),
    }


class _RecordedAuthorizationPermit:
    __slots__ = ()


_RECORDED_AUTHORIZATION_PERMIT = _RecordedAuthorizationPermit()


@final
class RecordedReviewDecisionAuthorizationV1(_RedactedValue):
    """Adapter-produced recorded self-consistency proof for one request."""

    __slots__ = (
        "_actor",
        "_article_version_id",
        "_assignment_id",
        "_assignment_sha256",
        "_authorization_sha256",
        "_correlation_id",
        "_decision_sha256",
        "_grant",
        "_operation",
        "_permission_scope",
        "_request_sha256",
        "_target",
    )
    _operation: ReviewDecisionOperation
    _request_sha256: RecordedSha256
    _correlation_id: CorrelationId
    _target: AuthorizationTarget
    _grant: AuthorizationGrant
    _permission_scope: PermissionScope
    _actor: RecordedIdentityProjection
    _assignment_id: ReviewAssignmentId
    _article_version_id: ArticleVersionId
    _assignment_sha256: RecordedSha256
    _decision_sha256: RecordedSha256
    _authorization_sha256: RecordedSha256

    def __init__(
        self,
        *,
        operation: ReviewDecisionOperation,
        request_sha256: RecordedSha256,
        correlation_id: CorrelationId,
        target: AuthorizationTarget,
        grant: AuthorizationGrant,
        permission_scope: PermissionScope,
        actor: RecordedIdentityProjection,
        assignment_id: ReviewAssignmentId,
        article_version_id: ArticleVersionId,
        assignment_sha256: RecordedSha256,
        decision_sha256: RecordedSha256,
        authorization_sha256: RecordedSha256,
        _recorded_local_permit: object = None,
    ) -> None:
        if _recorded_local_permit is not _RECORDED_AUTHORIZATION_PERMIT:
            fail_review_decision_operation(
                ReviewDecisionOperationFailureCode.NOT_AUTHORIZED
            )
        object.__setattr__(self, "_operation", operation)
        object.__setattr__(self, "_request_sha256", request_sha256)
        object.__setattr__(self, "_correlation_id", correlation_id)
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_grant", grant)
        object.__setattr__(self, "_permission_scope", permission_scope)
        object.__setattr__(self, "_actor", actor)
        object.__setattr__(self, "_assignment_id", assignment_id)
        object.__setattr__(self, "_article_version_id", article_version_id)
        object.__setattr__(self, "_assignment_sha256", assignment_sha256)
        object.__setattr__(self, "_decision_sha256", decision_sha256)
        object.__setattr__(self, "_authorization_sha256", authorization_sha256)
        self.require_valid()

    @property
    def profile(self) -> str:
        return RECORDED_LOCAL_PROFILE

    @property
    def operation(self) -> ReviewDecisionOperation:
        return self._operation

    @property
    def request_sha256(self) -> RecordedSha256:
        return self._request_sha256

    @property
    def correlation_id(self) -> CorrelationId:
        return self._correlation_id

    @property
    def target(self) -> AuthorizationTarget:
        return self._target

    @property
    def grant(self) -> AuthorizationGrant:
        return self._grant

    @property
    def permission_scope(self) -> PermissionScope:
        return self._permission_scope

    @property
    def actor(self) -> RecordedIdentityProjection:
        return self._actor

    @property
    def assignment_id(self) -> ReviewAssignmentId:
        return self._assignment_id

    @property
    def article_version_id(self) -> ArticleVersionId:
        return self._article_version_id

    @property
    def assignment_sha256(self) -> RecordedSha256:
        return self._assignment_sha256

    @property
    def decision_sha256(self) -> RecordedSha256:
        return self._decision_sha256

    @property
    def authorization_sha256(self) -> RecordedSha256:
        return self._authorization_sha256

    def _payload(self) -> dict[str, object]:
        return {
            "actor": _identity_payload(self.actor),
            "article_version_id": str(self.article_version_id.value),
            "assignment_id": str(self.assignment_id.value),
            "assignment_sha256": self.assignment_sha256.value,
            "correlation_id": self.correlation_id.value,
            "decision_sha256": self.decision_sha256.value,
            "grant": _grant_payload(self.grant),
            "operation_id": self.operation.value,
            "permission_scope": self.permission_scope.value,
            "profile": RECORDED_LOCAL_PROFILE,
            "request_sha256": self.request_sha256.value,
            "target": _target_payload(self.target),
        }

    def require_valid(self) -> None:
        if (
            self.operation is not ReviewDecisionOperation.RECORD
            or type(self.actor) is not RecordedIdentityProjection
            or _clone_uuid_value(self.assignment_id, ReviewAssignmentId)
            != self.assignment_id
            or _clone_uuid_value(self.article_version_id, ArticleVersionId)
            != self.article_version_id
        ):
            fail_review_decision_operation(
                ReviewDecisionOperationFailureCode.NOT_AUTHORIZED
            )
        self.actor.require_valid()
        _require_correlation(self.correlation_id)
        _normalize_target(self.target)
        _normalize_grant(self.grant)
        _require_permission(self.permission_scope)
        _require_sha256(self.request_sha256)
        _require_sha256(self.assignment_sha256)
        _require_sha256(self.decision_sha256)
        if _require_sha256(self.authorization_sha256) != _canonical_sha256(
            self._payload()
        ):
            fail_review_decision_operation(
                ReviewDecisionOperationFailureCode.NOT_AUTHORIZED
            )

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("RecordedReviewDecisionAuthorizationV1 is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("RecordedReviewDecisionAuthorizationV1 is immutable")


def build_recorded_review_decision_authorization(
    *,
    request: RecordReviewDecisionRequest,
    grant: AuthorizationGrant,
    permission_scope: PermissionScope,
    actor: RecordedIdentityProjection,
) -> RecordedReviewDecisionAuthorizationV1:
    """Build one immutable, non-authoritative recorded-local proof."""

    if type(request) is not RecordReviewDecisionRequest:
        fail_review_decision_operation()
    request.require_valid()
    normalized_grant = _normalize_grant(grant)
    normalized_permission = _require_permission(permission_scope)
    if type(actor) is not RecordedIdentityProjection:
        fail_review_decision_operation()
    normalized_actor = RecordedIdentityProjection(
        principal_id=actor.principal_id,
        subject_kind=actor.subject_kind,
        subject_status=actor.subject_status,
    )
    payload = _authorization_payload(
        request=request,
        grant=normalized_grant,
        permission_scope=normalized_permission,
        actor=normalized_actor,
    )
    return RecordedReviewDecisionAuthorizationV1(
        operation=request.operation,
        request_sha256=RecordedSha256(request.request_sha256.value),
        correlation_id=_require_correlation(request.correlation_id),
        target=_normalize_target(request.target),
        grant=normalized_grant,
        permission_scope=normalized_permission,
        actor=normalized_actor,
        assignment_id=_clone_uuid_value(
            request.assignment.assignment_id, ReviewAssignmentId
        ),
        article_version_id=_clone_uuid_value(
            request.assignment.article_version_id, ArticleVersionId
        ),
        assignment_sha256=RecordedSha256(request.assignment_sha256.value),
        decision_sha256=RecordedSha256(request.decision_sha256.value),
        authorization_sha256=_canonical_sha256(payload),
        _recorded_local_permit=_RECORDED_AUTHORIZATION_PERMIT,
    )


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedReviewDecisionV1(_RedactedValue):
    """Immutable recorded-local negative decision; it has no effective state."""

    decision_id: ReviewDecisionId
    decision: StructurallyValidatedReviewDecision
    decided_by: PrincipalId
    decided_at: UtcTimestamp
    assignment_sha256: RecordedSha256
    supersedes_decision_id: ReviewDecisionId | None = None
    superseded_record_sha256: RecordedSha256 | None = None
    decision_sha256: RecordedSha256 = field(init=False)
    record_sha256: RecordedSha256 = field(init=False)

    def __post_init__(self) -> None:
        decision_id = _clone_uuid_value(self.decision_id, ReviewDecisionId)
        decision = _clone_validated_decision(self.decision)
        decided_by = _clone_uuid_value(self.decided_by, PrincipalId)
        decided_at = _clone_timestamp(self.decided_at)
        assignment_sha256 = _require_sha256(self.assignment_sha256)
        supersedes = (
            None
            if self.supersedes_decision_id is None
            else _clone_uuid_value(self.supersedes_decision_id, ReviewDecisionId)
        )
        prior_sha256 = (
            None
            if self.superseded_record_sha256 is None
            else _require_sha256(self.superseded_record_sha256)
        )
        if (supersedes is None) is not (prior_sha256 is None):
            fail_review_decision_operation(
                ReviewDecisionOperationFailureCode.HISTORY_MISMATCH
            )
        object.__setattr__(self, "decision_id", decision_id)
        object.__setattr__(self, "decision", decision)
        object.__setattr__(self, "decided_by", decided_by)
        object.__setattr__(self, "decided_at", decided_at)
        object.__setattr__(self, "assignment_sha256", assignment_sha256)
        object.__setattr__(self, "supersedes_decision_id", supersedes)
        object.__setattr__(self, "superseded_record_sha256", prior_sha256)
        object.__setattr__(
            self, "decision_sha256", _validated_decision_sha256(decision)
        )
        object.__setattr__(self, "record_sha256", self._expected_sha256())

    @property
    def assignment_id(self) -> ReviewAssignmentId:
        return self.decision.review_assignment_id

    @property
    def article_version_id(self) -> ArticleVersionId:
        return self.decision.article_version_id

    def _payload(self) -> dict[str, object]:
        return {
            "article_version_id": str(self.article_version_id.value),
            "assignment_id": str(self.assignment_id.value),
            "assignment_sha256": self.assignment_sha256.value,
            "decided_at": _timestamp_text(self.decided_at),
            "decided_by": str(self.decided_by.value),
            "decision_id": str(self.decision_id.value),
            "decision_sha256": self.decision_sha256.value,
            "profile": RECORDED_LOCAL_PROFILE,
            "superseded_record_sha256": (
                None
                if self.superseded_record_sha256 is None
                else self.superseded_record_sha256.value
            ),
            "supersedes_decision_id": (
                None
                if self.supersedes_decision_id is None
                else str(self.supersedes_decision_id.value)
            ),
        }

    def _expected_sha256(self) -> RecordedSha256:
        return _canonical_sha256(self._payload())

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        return _canonical_bytes(
            {**self._payload(), "record_sha256": self.record_sha256.value}
        )

    def require_valid(self) -> None:
        _clone_uuid_value(self.decision_id, ReviewDecisionId)
        decision = _clone_validated_decision(self.decision)
        _clone_uuid_value(self.decided_by, PrincipalId)
        _clone_timestamp(self.decided_at)
        _require_sha256(self.assignment_sha256)
        if self.supersedes_decision_id is not None:
            _clone_uuid_value(self.supersedes_decision_id, ReviewDecisionId)
        if self.superseded_record_sha256 is not None:
            _require_sha256(self.superseded_record_sha256)
        if (self.supersedes_decision_id is None) is not (
            self.superseded_record_sha256 is None
        ):
            fail_review_decision_operation(
                ReviewDecisionOperationFailureCode.HISTORY_MISMATCH
            )
        if (
            _require_sha256(self.decision_sha256)
            != _validated_decision_sha256(decision)
            or _require_sha256(self.record_sha256) != self._expected_sha256()
        ):
            fail_review_decision_operation(
                ReviewDecisionOperationFailureCode.OUTCOME_MISMATCH
            )


def _clone_record(value: object) -> RecordedReviewDecisionV1:
    if type(value) is not RecordedReviewDecisionV1:
        fail_review_decision_operation()
    value.require_valid()
    normalized = RecordedReviewDecisionV1(
        decision_id=value.decision_id,
        decision=value.decision,
        decided_by=value.decided_by,
        decided_at=value.decided_at,
        assignment_sha256=value.assignment_sha256,
        supersedes_decision_id=value.supersedes_decision_id,
        superseded_record_sha256=value.superseded_record_sha256,
    )
    if normalized.canonical_bytes() != value.canonical_bytes():
        fail_review_decision_operation(
            ReviewDecisionOperationFailureCode.OUTCOME_MISMATCH
        )
    return normalized


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedReviewDecisionHistoryV1(_RedactedValue):
    """Append-ordered records only; no tail, latest, or effective semantics."""

    assignment_id: ReviewAssignmentId
    article_version_id: ArticleVersionId
    records: tuple[RecordedReviewDecisionV1, ...]
    history_sha256: RecordedSha256 = field(init=False)

    def __post_init__(self) -> None:
        assignment_id = _clone_uuid_value(self.assignment_id, ReviewAssignmentId)
        article_version_id = _clone_uuid_value(
            self.article_version_id, ArticleVersionId
        )
        if type(self.records) is not tuple:
            fail_review_decision_operation(
                ReviewDecisionOperationFailureCode.HISTORY_MISMATCH
            )
        records = tuple(_clone_record(item) for item in self.records)
        self._validate_records(
            assignment_id=assignment_id,
            article_version_id=article_version_id,
            records=records,
        )
        object.__setattr__(self, "assignment_id", assignment_id)
        object.__setattr__(self, "article_version_id", article_version_id)
        object.__setattr__(self, "records", records)
        object.__setattr__(self, "history_sha256", self._expected_sha256())

    @staticmethod
    def _validate_records(
        *,
        assignment_id: ReviewAssignmentId,
        article_version_id: ArticleVersionId,
        records: tuple[RecordedReviewDecisionV1, ...],
    ) -> None:
        prior_by_id: dict[ReviewDecisionId, RecordedReviewDecisionV1] = {}
        for record in records:
            record.require_valid()
            if (
                record.assignment_id != assignment_id
                or record.article_version_id != article_version_id
                or record.decision_id in prior_by_id
            ):
                fail_review_decision_operation(
                    ReviewDecisionOperationFailureCode.HISTORY_MISMATCH
                )
            supersedes = record.supersedes_decision_id
            if supersedes is not None:
                prior = prior_by_id.get(supersedes)
                if (
                    prior is None
                    or record.superseded_record_sha256 != prior.record_sha256
                ):
                    fail_review_decision_operation(
                        ReviewDecisionOperationFailureCode.HISTORY_MISMATCH
                    )
            prior_by_id[record.decision_id] = record

    def _payload(self) -> dict[str, object]:
        return {
            "article_version_id": str(self.article_version_id.value),
            "assignment_id": str(self.assignment_id.value),
            "profile": RECORDED_LOCAL_PROFILE,
            "record_sha256": [item.record_sha256.value for item in self.records],
        }

    def _expected_sha256(self) -> RecordedSha256:
        return _canonical_sha256(self._payload())

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        return _canonical_bytes(
            {**self._payload(), "history_sha256": self.history_sha256.value}
        )

    def require_valid(self) -> None:
        assignment_id = _clone_uuid_value(self.assignment_id, ReviewAssignmentId)
        article_version_id = _clone_uuid_value(
            self.article_version_id, ArticleVersionId
        )
        if type(self.records) is not tuple or any(
            type(item) is not RecordedReviewDecisionV1 for item in self.records
        ):
            fail_review_decision_operation(
                ReviewDecisionOperationFailureCode.HISTORY_MISMATCH
            )
        self._validate_records(
            assignment_id=assignment_id,
            article_version_id=article_version_id,
            records=self.records,
        )
        if _require_sha256(self.history_sha256) != self._expected_sha256():
            fail_review_decision_operation(
                ReviewDecisionOperationFailureCode.HISTORY_MISMATCH
            )


def _require_uuid7(value: object) -> UUID:
    if type(value) is not UUID or value.version != 7 or value.variant != RFC_4122:
        fail_review_decision_operation()
    return UUID(int=value.int)


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedAuditArtifactV1(_RedactedValue):
    """Deterministic local artifact; never durable/transactional audit evidence."""

    event_id: UUID
    action: RecordedAuditAction
    occurred_at: UtcTimestamp
    actor_id: PrincipalId
    assignment_id: ReviewAssignmentId
    article_version_id: ArticleVersionId
    decision_id: ReviewDecisionId
    correlation_id: CorrelationId
    authorization_sha256: RecordedSha256
    request_sha256: RecordedSha256
    record_sha256: RecordedSha256
    supersedes_decision_id: ReviewDecisionId | None = None
    superseded_record_sha256: RecordedSha256 | None = None
    audit_sha256: RecordedSha256 = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _require_uuid7(self.event_id))
        if self.action is not RecordedAuditAction.DECISION_RECORD:
            fail_review_decision_operation()
        object.__setattr__(self, "occurred_at", _clone_timestamp(self.occurred_at))
        object.__setattr__(
            self, "actor_id", _clone_uuid_value(self.actor_id, PrincipalId)
        )
        object.__setattr__(
            self,
            "assignment_id",
            _clone_uuid_value(self.assignment_id, ReviewAssignmentId),
        )
        object.__setattr__(
            self,
            "article_version_id",
            _clone_uuid_value(self.article_version_id, ArticleVersionId),
        )
        object.__setattr__(
            self, "decision_id", _clone_uuid_value(self.decision_id, ReviewDecisionId)
        )
        object.__setattr__(
            self, "correlation_id", _require_correlation(self.correlation_id)
        )
        object.__setattr__(
            self,
            "authorization_sha256",
            _require_sha256(self.authorization_sha256),
        )
        object.__setattr__(self, "request_sha256", _require_sha256(self.request_sha256))
        object.__setattr__(self, "record_sha256", _require_sha256(self.record_sha256))
        supersedes = (
            None
            if self.supersedes_decision_id is None
            else _clone_uuid_value(self.supersedes_decision_id, ReviewDecisionId)
        )
        prior_sha256 = (
            None
            if self.superseded_record_sha256 is None
            else _require_sha256(self.superseded_record_sha256)
        )
        if (supersedes is None) is not (prior_sha256 is None):
            fail_review_decision_operation()
        object.__setattr__(self, "supersedes_decision_id", supersedes)
        object.__setattr__(self, "superseded_record_sha256", prior_sha256)
        object.__setattr__(self, "audit_sha256", self._expected_sha256())

    def _payload(self) -> dict[str, object]:
        return {
            "action": self.action.value,
            "actor_id": str(self.actor_id.value),
            "article_version_id": str(self.article_version_id.value),
            "assignment_id": str(self.assignment_id.value),
            "authorization_sha256": self.authorization_sha256.value,
            "correlation_id": self.correlation_id.value,
            "decision_id": str(self.decision_id.value),
            "event_id": str(self.event_id),
            "occurred_at": _timestamp_text(self.occurred_at),
            "profile": RECORDED_LOCAL_PROFILE,
            "record_sha256": self.record_sha256.value,
            "request_sha256": self.request_sha256.value,
            "superseded_record_sha256": (
                None
                if self.superseded_record_sha256 is None
                else self.superseded_record_sha256.value
            ),
            "supersedes_decision_id": (
                None
                if self.supersedes_decision_id is None
                else str(self.supersedes_decision_id.value)
            ),
        }

    def _expected_sha256(self) -> RecordedSha256:
        return _canonical_sha256(self._payload())

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        return _canonical_bytes(
            {**self._payload(), "audit_sha256": self.audit_sha256.value}
        )

    def require_valid(self) -> None:
        if self.action is not RecordedAuditAction.DECISION_RECORD or (
            self.supersedes_decision_id is None
        ) is not (self.superseded_record_sha256 is None):
            fail_review_decision_operation(
                ReviewDecisionOperationFailureCode.OUTCOME_MISMATCH
            )
        _require_uuid7(self.event_id)
        _clone_timestamp(self.occurred_at)
        _clone_uuid_value(self.actor_id, PrincipalId)
        _clone_uuid_value(self.assignment_id, ReviewAssignmentId)
        _clone_uuid_value(self.article_version_id, ArticleVersionId)
        _clone_uuid_value(self.decision_id, ReviewDecisionId)
        _require_correlation(self.correlation_id)
        _require_sha256(self.authorization_sha256)
        _require_sha256(self.request_sha256)
        _require_sha256(self.record_sha256)
        if self.supersedes_decision_id is not None:
            _clone_uuid_value(self.supersedes_decision_id, ReviewDecisionId)
        if self.superseded_record_sha256 is not None:
            _require_sha256(self.superseded_record_sha256)
        if _require_sha256(self.audit_sha256) != self._expected_sha256():
            fail_review_decision_operation(
                ReviewDecisionOperationFailureCode.OUTCOME_MISMATCH
            )


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedIdempotencyReceiptV1(_RedactedValue):
    """Hash-only receipt; the raw Idempotency-Key is never retained."""

    operation: ReviewDecisionOperation
    idempotency_key_sha256: RecordedSha256
    request_sha256: RecordedSha256
    recorded_output_sha256: RecordedSha256
    receipt_sha256: RecordedSha256 = field(init=False)

    def __post_init__(self) -> None:
        if self.operation is not ReviewDecisionOperation.RECORD:
            fail_review_decision_operation()
        object.__setattr__(
            self,
            "idempotency_key_sha256",
            _require_sha256(self.idempotency_key_sha256),
        )
        object.__setattr__(self, "request_sha256", _require_sha256(self.request_sha256))
        object.__setattr__(
            self,
            "recorded_output_sha256",
            _require_sha256(self.recorded_output_sha256),
        )
        object.__setattr__(self, "receipt_sha256", self._expected_sha256())

    @classmethod
    def recorded_local(
        cls,
        *,
        idempotency_key: IdempotencyKey,
        request_sha256: RecordedSha256,
        recorded_output_sha256: RecordedSha256,
    ) -> RecordedIdempotencyReceiptV1:
        key = _require_idempotency_key(idempotency_key)
        return cls(
            operation=ReviewDecisionOperation.RECORD,
            idempotency_key_sha256=RecordedSha256(
                hashlib.sha256(key.value.encode("ascii", errors="strict")).hexdigest()
            ),
            request_sha256=request_sha256,
            recorded_output_sha256=recorded_output_sha256,
        )

    def _payload(self) -> dict[str, object]:
        return {
            "idempotency_key_sha256": self.idempotency_key_sha256.value,
            "operation_id": self.operation.value,
            "profile": RECORDED_LOCAL_PROFILE,
            "recorded_output_sha256": self.recorded_output_sha256.value,
            "request_sha256": self.request_sha256.value,
        }

    def _expected_sha256(self) -> RecordedSha256:
        return _canonical_sha256(self._payload())

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        return _canonical_bytes(
            {**self._payload(), "receipt_sha256": self.receipt_sha256.value}
        )

    def require_valid(self) -> None:
        if self.operation is not ReviewDecisionOperation.RECORD:
            fail_review_decision_operation()
        _require_sha256(self.idempotency_key_sha256)
        _require_sha256(self.request_sha256)
        _require_sha256(self.recorded_output_sha256)
        if _require_sha256(self.receipt_sha256) != self._expected_sha256():
            fail_review_decision_operation(
                ReviewDecisionOperationFailureCode.OUTCOME_MISMATCH
            )


def recorded_decision_output_sha256(
    *,
    assignment_sha256: RecordedSha256,
    record_sha256: RecordedSha256,
    history_sha256: RecordedSha256,
    audit_sha256: RecordedSha256,
) -> RecordedSha256:
    """Bind immutable local artifacts without claiming durable atomicity."""

    return _canonical_sha256(
        {
            "assignment_sha256": _require_sha256(assignment_sha256).value,
            "audit_sha256": _require_sha256(audit_sha256).value,
            "history_sha256": _require_sha256(history_sha256).value,
            "profile": RECORDED_LOCAL_PROFILE,
            "record_sha256": _require_sha256(record_sha256).value,
        }
    )


def _closed_result_flags_valid(result: object) -> bool:
    return (
        getattr(result, "execution", None) is RecordedExecution.RECORDED_ONLY
        and getattr(result, "authentication", None) is RecordedExecution.NOT_EXECUTED
        and getattr(result, "identity_attestation", None)
        is RecordedExecution.NOT_EXECUTED
        and getattr(result, "persistence", None) is RecordedExecution.NOT_EXECUTED
        and getattr(result, "transaction", None) is RecordedExecution.NOT_EXECUTED
        and getattr(result, "unit_of_work", None) is RecordedExecution.NOT_EXECUTED
        and getattr(result, "database_enforcement", None)
        is RecordedExecution.NOT_EXECUTED
        and getattr(result, "durable_idempotency", None)
        is RecordedExecution.NOT_EXECUTED
        and getattr(result, "audit_durability", None) is RecordedExecution.NOT_EXECUTED
        and getattr(result, "audit_atomicity", None) is RecordedExecution.NOT_EXECUTED
        and getattr(result, "events", None) is RecordedExecution.NOT_EXECUTED
        and getattr(result, "outbox", None) is RecordedExecution.NOT_EXECUTED
        and getattr(result, "delivery", None) is RecordedExecution.NOT_EXECUTED
        and getattr(result, "assignment_mutation", None)
        is RecordedExecution.NOT_EXECUTED
        and getattr(result, "finding_mutation", None) is RecordedExecution.NOT_EXECUTED
        and getattr(result, "approval", None) is RecordedExecution.NOT_EXECUTED
        and getattr(result, "http_api", None) is RecordedExecution.NOT_EXECUTED
        and getattr(result, "formal_verification", None)
        is RecordedExecution.NOT_EXECUTED
        and getattr(result, "live", None) is RecordedExecution.NOT_EXECUTED
        and getattr(result, "staging", None) is RecordedExecution.NOT_EXECUTED
        and getattr(result, "release", None) is RecordedExecution.NOT_EXECUTED
        and getattr(result, "production", None) is RecordedExecution.NOT_EXECUTED
        and getattr(result, "publication", None) is RecordedExecution.NOT_EXECUTED
        and getattr(result, "readiness", None) is RecordedReadiness.NOT_READY
    )


def _closed_result_payload(result: object) -> dict[str, str]:
    if not _closed_result_flags_valid(result):
        fail_review_decision_operation(
            ReviewDecisionOperationFailureCode.OUTCOME_MISMATCH
        )
    return {
        "approval": RecordedExecution.NOT_EXECUTED.value,
        "assignment_mutation": RecordedExecution.NOT_EXECUTED.value,
        "audit_atomicity": RecordedExecution.NOT_EXECUTED.value,
        "audit_durability": RecordedExecution.NOT_EXECUTED.value,
        "authentication": RecordedExecution.NOT_EXECUTED.value,
        "database_enforcement": RecordedExecution.NOT_EXECUTED.value,
        "delivery": RecordedExecution.NOT_EXECUTED.value,
        "durable_idempotency": RecordedExecution.NOT_EXECUTED.value,
        "events": RecordedExecution.NOT_EXECUTED.value,
        "execution": RecordedExecution.RECORDED_ONLY.value,
        "finding_mutation": RecordedExecution.NOT_EXECUTED.value,
        "formal_verification": RecordedExecution.NOT_EXECUTED.value,
        "http_api": RecordedExecution.NOT_EXECUTED.value,
        "identity_attestation": RecordedExecution.NOT_EXECUTED.value,
        "live": RecordedExecution.NOT_EXECUTED.value,
        "outbox": RecordedExecution.NOT_EXECUTED.value,
        "persistence": RecordedExecution.NOT_EXECUTED.value,
        "production": RecordedExecution.NOT_EXECUTED.value,
        "publication": RecordedExecution.NOT_EXECUTED.value,
        "readiness": RecordedReadiness.NOT_READY.value,
        "release": RecordedExecution.NOT_EXECUTED.value,
        "staging": RecordedExecution.NOT_EXECUTED.value,
        "transaction": RecordedExecution.NOT_EXECUTED.value,
        "unit_of_work": RecordedExecution.NOT_EXECUTED.value,
    }


def _clone_audit(value: object) -> RecordedAuditArtifactV1:
    if type(value) is not RecordedAuditArtifactV1:
        fail_review_decision_operation()
    value.require_valid()
    normalized = RecordedAuditArtifactV1(
        event_id=value.event_id,
        action=value.action,
        occurred_at=value.occurred_at,
        actor_id=value.actor_id,
        assignment_id=value.assignment_id,
        article_version_id=value.article_version_id,
        decision_id=value.decision_id,
        correlation_id=value.correlation_id,
        authorization_sha256=value.authorization_sha256,
        request_sha256=value.request_sha256,
        record_sha256=value.record_sha256,
        supersedes_decision_id=value.supersedes_decision_id,
        superseded_record_sha256=value.superseded_record_sha256,
    )
    if normalized.canonical_bytes() != value.canonical_bytes():
        fail_review_decision_operation(
            ReviewDecisionOperationFailureCode.OUTCOME_MISMATCH
        )
    return normalized


def _clone_receipt(value: object) -> RecordedIdempotencyReceiptV1:
    if type(value) is not RecordedIdempotencyReceiptV1:
        fail_review_decision_operation()
    value.require_valid()
    normalized = RecordedIdempotencyReceiptV1(
        operation=value.operation,
        idempotency_key_sha256=value.idempotency_key_sha256,
        request_sha256=value.request_sha256,
        recorded_output_sha256=value.recorded_output_sha256,
    )
    if normalized.canonical_bytes() != value.canonical_bytes():
        fail_review_decision_operation(
            ReviewDecisionOperationFailureCode.OUTCOME_MISMATCH
        )
    return normalized


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordReviewDecisionResultV1(_RedactedValue):
    """Immutable recorded append result with every external-effect flag closed."""

    authorization_sha256: RecordedSha256
    request_sha256: RecordedSha256
    assignment: ReviewAssignment
    record: RecordedReviewDecisionV1
    history: RecordedReviewDecisionHistoryV1
    audit: RecordedAuditArtifactV1
    idempotency: RecordedIdempotencyReceiptV1
    operation: ReviewDecisionOperation = field(
        init=False, default=ReviewDecisionOperation.RECORD
    )
    execution: RecordedExecution = field(
        init=False, default=RecordedExecution.RECORDED_ONLY
    )
    authentication: RecordedExecution = field(
        init=False, default=RecordedExecution.NOT_EXECUTED
    )
    identity_attestation: RecordedExecution = field(
        init=False, default=RecordedExecution.NOT_EXECUTED
    )
    persistence: RecordedExecution = field(
        init=False, default=RecordedExecution.NOT_EXECUTED
    )
    transaction: RecordedExecution = field(
        init=False, default=RecordedExecution.NOT_EXECUTED
    )
    unit_of_work: RecordedExecution = field(
        init=False, default=RecordedExecution.NOT_EXECUTED
    )
    database_enforcement: RecordedExecution = field(
        init=False, default=RecordedExecution.NOT_EXECUTED
    )
    durable_idempotency: RecordedExecution = field(
        init=False, default=RecordedExecution.NOT_EXECUTED
    )
    audit_durability: RecordedExecution = field(
        init=False, default=RecordedExecution.NOT_EXECUTED
    )
    audit_atomicity: RecordedExecution = field(
        init=False, default=RecordedExecution.NOT_EXECUTED
    )
    events: RecordedExecution = field(
        init=False, default=RecordedExecution.NOT_EXECUTED
    )
    outbox: RecordedExecution = field(
        init=False, default=RecordedExecution.NOT_EXECUTED
    )
    delivery: RecordedExecution = field(
        init=False, default=RecordedExecution.NOT_EXECUTED
    )
    assignment_mutation: RecordedExecution = field(
        init=False, default=RecordedExecution.NOT_EXECUTED
    )
    finding_mutation: RecordedExecution = field(
        init=False, default=RecordedExecution.NOT_EXECUTED
    )
    approval: RecordedExecution = field(
        init=False, default=RecordedExecution.NOT_EXECUTED
    )
    http_api: RecordedExecution = field(
        init=False, default=RecordedExecution.NOT_EXECUTED
    )
    formal_verification: RecordedExecution = field(
        init=False, default=RecordedExecution.NOT_EXECUTED
    )
    live: RecordedExecution = field(init=False, default=RecordedExecution.NOT_EXECUTED)
    staging: RecordedExecution = field(
        init=False, default=RecordedExecution.NOT_EXECUTED
    )
    release: RecordedExecution = field(
        init=False, default=RecordedExecution.NOT_EXECUTED
    )
    production: RecordedExecution = field(
        init=False, default=RecordedExecution.NOT_EXECUTED
    )
    publication: RecordedExecution = field(
        init=False, default=RecordedExecution.NOT_EXECUTED
    )
    readiness: RecordedReadiness = field(
        init=False, default=RecordedReadiness.NOT_READY
    )
    result_sha256: RecordedSha256 = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "authorization_sha256",
            _require_sha256(self.authorization_sha256),
        )
        object.__setattr__(self, "request_sha256", _require_sha256(self.request_sha256))
        object.__setattr__(self, "assignment", _clone_assignment(self.assignment))
        object.__setattr__(self, "record", _clone_record(self.record))
        if type(self.history) is not RecordedReviewDecisionHistoryV1:
            fail_review_decision_operation()
        object.__setattr__(
            self,
            "history",
            RecordedReviewDecisionHistoryV1(
                assignment_id=self.history.assignment_id,
                article_version_id=self.history.article_version_id,
                records=self.history.records,
            ),
        )
        object.__setattr__(self, "audit", _clone_audit(self.audit))
        object.__setattr__(self, "idempotency", _clone_receipt(self.idempotency))
        self._validate_components()
        object.__setattr__(self, "result_sha256", self._expected_sha256())

    def _validate_components(self) -> None:
        assignment = _clone_assignment(self.assignment)
        record = _clone_record(self.record)
        self.history.require_valid()
        self.audit.require_valid()
        self.idempotency.require_valid()
        expected_output = recorded_decision_output_sha256(
            assignment_sha256=_assignment_sha256(assignment),
            record_sha256=record.record_sha256,
            history_sha256=self.history.history_sha256,
            audit_sha256=self.audit.audit_sha256,
        )
        if (
            self.operation is not ReviewDecisionOperation.RECORD
            or assignment.status is not ReviewAssignmentState.IN_PROGRESS
            or _assignment_sha256(assignment) != record.assignment_sha256
            or assignment.assignment_id != record.assignment_id
            or assignment.article_version_id != record.article_version_id
            or assignment.assigned_to != record.decided_by
            or self.history.assignment_id != record.assignment_id
            or self.history.article_version_id != record.article_version_id
            or not self.history.records
            or self.history.records[-1].canonical_bytes() != record.canonical_bytes()
            or self.audit.action is not RecordedAuditAction.DECISION_RECORD
            or self.audit.actor_id != record.decided_by
            or self.audit.assignment_id != record.assignment_id
            or self.audit.article_version_id != record.article_version_id
            or self.audit.decision_id != record.decision_id
            or self.audit.occurred_at != record.decided_at
            or self.audit.authorization_sha256 != self.authorization_sha256
            or self.audit.request_sha256 != self.request_sha256
            or self.audit.record_sha256 != record.record_sha256
            or self.audit.supersedes_decision_id != record.supersedes_decision_id
            or self.audit.superseded_record_sha256 != record.superseded_record_sha256
            or self.idempotency.operation is not self.operation
            or self.idempotency.request_sha256 != self.request_sha256
            or self.idempotency.recorded_output_sha256 != expected_output
            or not _closed_result_flags_valid(self)
        ):
            fail_review_decision_operation(
                ReviewDecisionOperationFailureCode.OUTCOME_MISMATCH
            )

    def _payload(self) -> dict[str, object]:
        return {
            **_closed_result_payload(self),
            "assignment_sha256": _assignment_sha256(self.assignment).value,
            "audit_sha256": self.audit.audit_sha256.value,
            "authorization_sha256": self.authorization_sha256.value,
            "history_sha256": self.history.history_sha256.value,
            "idempotency_receipt_sha256": self.idempotency.receipt_sha256.value,
            "operation_id": self.operation.value,
            "profile": RECORDED_LOCAL_PROFILE,
            "record_sha256": self.record.record_sha256.value,
            "request_sha256": self.request_sha256.value,
        }

    def _expected_sha256(self) -> RecordedSha256:
        return _canonical_sha256(self._payload())

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        return _canonical_bytes(
            {**self._payload(), "result_sha256": self.result_sha256.value}
        )

    def require_valid(self) -> None:
        _require_sha256(self.authorization_sha256)
        _require_sha256(self.request_sha256)
        if (
            type(self.record) is not RecordedReviewDecisionV1
            or type(self.history) is not RecordedReviewDecisionHistoryV1
            or type(self.audit) is not RecordedAuditArtifactV1
            or type(self.idempotency) is not RecordedIdempotencyReceiptV1
        ):
            fail_review_decision_operation(
                ReviewDecisionOperationFailureCode.OUTCOME_MISMATCH
            )
        self._validate_components()
        if _require_sha256(self.result_sha256) != self._expected_sha256():
            fail_review_decision_operation(
                ReviewDecisionOperationFailureCode.OUTCOME_MISMATCH
            )


__all__ = (
    "RECORDED_LOCAL_PROFILE",
    "RecordReviewDecisionRequest",
    "RecordReviewDecisionResultV1",
    "RecordedAuditAction",
    "RecordedAuditArtifactV1",
    "RecordedExecution",
    "RecordedIdentityProjection",
    "RecordedIdempotencyReceiptV1",
    "RecordedReadiness",
    "RecordedReviewDecisionAuthorizationV1",
    "RecordedReviewDecisionHistoryV1",
    "RecordedReviewDecisionV1",
    "RecordedSha256",
    "RecordedSubjectKind",
    "RecordedSubjectStatus",
    "ReviewDecisionOperation",
    "ReviewDecisionOperationFailure",
    "ReviewDecisionOperationFailureCode",
    "fail_review_decision_operation",
    "recorded_decision_output_sha256",
)

"""Recorded-local PUBADM-001..003 values for ST-0901 PR2.

All values in this module belong only to the
``ST0901_PR2_RECORDED_LOCAL_V1`` ENV-DEV/CI fixture seam.  They are not
authentication, attestation, a signature, canonical authorization policy,
durable audit evidence, a public API contract, or Story acceptance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, EnumType
import hashlib
import json
import re
from typing import Any, Callable, Final, NoReturn, SupportsIndex, TypeAlias, final
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
from raos.domain.portfolio.workflow import EntityVersion, IdempotencyKey, StrongEtag
from raos.domain.publishing.review_workflow import (
    ArticleVersionId,
    PrincipalId,
    ReviewAssignment,
    ReviewAssignmentId,
    ReviewAssignmentState,
    ReviewDecisionReference,
    ReviewType,
    UtcTimestamp,
)


RECORDED_LOCAL_PROFILE: Final = "ST0901_PR2_RECORDED_LOCAL_V1"
_REDACTED: Final = "<redacted-st0901-pr2-recorded-local>"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_MAX_LIST_LIMIT: Final = 200


class _ClosedEnumType(EnumType):
    """Reject unknown vocabulary without retaining rejected caller material."""

    def __getitem__(cls, name: str) -> Any:
        if type(name) is not str:
            fail_review_assignment_operation()
        member: Any
        for member in cls:
            if member.name == name:
                return member
        fail_review_assignment_operation()

    def __call__(
        cls,
        value: Any,
        names: Any = None,
        *values: Any,
        **kwargs: Any,
    ) -> Any:
        if names is not None or values or kwargs:
            fail_review_assignment_operation()
        member: Any
        for member in cls:
            if value is member:
                return member
        if type(value) is not str:
            fail_review_assignment_operation()
        for member in cls:
            if member.value == value:
                return member
        fail_review_assignment_operation()


class _ClosedEnum(str, Enum, metaclass=_ClosedEnumType):
    @classmethod
    def _missing_(cls, value: object) -> NoReturn:
        del cls, value
        fail_review_assignment_operation()


class ReviewAssignmentOperation(_ClosedEnum):
    LIST = "PUBADM-001"
    CREATE = "PUBADM-002"
    UPDATE = "PUBADM-003"


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
    ASSIGNMENT_CREATE = "review_assignment_create"
    ASSIGNMENT_UPDATE = "review_assignment_update"


class ReviewAssignmentOperationFailureCode(_ClosedEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    LOCAL_EXCHANGE_UNAVAILABLE = "LOCAL_EXCHANGE_UNAVAILABLE"
    OUTCOME_MISMATCH = "OUTCOME_MISMATCH"
    IDEMPOTENCY_MISMATCH = "IDEMPOTENCY_MISMATCH"
    CONCURRENCY_MISMATCH = "CONCURRENCY_MISMATCH"


class ReviewAssignmentOperationFailure(RuntimeError):
    """Closed immutable failure that never retains rejected input."""

    __slots__ = ("_code",)
    _code: ReviewAssignmentOperationFailureCode

    def __init__(self, code: ReviewAssignmentOperationFailureCode) -> None:
        if type(code) is not ReviewAssignmentOperationFailureCode:
            raise TypeError("invalid review assignment operation failure code")
        object.__setattr__(self, "_code", code)
        RuntimeError.__init__(self, code.value)

    @property
    def code(self) -> ReviewAssignmentOperationFailureCode:
        return self._code

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("ReviewAssignmentOperationFailure is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("ReviewAssignmentOperationFailure is immutable")

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"ReviewAssignmentOperationFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("review assignment operation failure serialization denied")


def fail_review_assignment_operation(
    code: ReviewAssignmentOperationFailureCode = (
        ReviewAssignmentOperationFailureCode.INVALID_ARGUMENT
    ),
) -> NoReturn:
    raise ReviewAssignmentOperationFailure(code) from None


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded review assignment serialization denied")


def _revalidation_failed(callback: Callable[[], object]) -> bool:
    try:
        callback()
    except Exception:
        return True
    return False


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedSha256(_RedactedValue):
    """Implementation-local lower-case SHA-256 value."""

    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _SHA256.fullmatch(self.value) is None:
            fail_review_assignment_operation()


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedIdentityProjection(_RedactedValue):
    """Synthetic projection; a principal coordinate grants no authority."""

    principal_id: PrincipalId
    subject_kind: RecordedSubjectKind
    subject_status: RecordedSubjectStatus

    def __post_init__(self) -> None:
        if (
            type(self.principal_id) is not PrincipalId
            or type(self.subject_kind) is not RecordedSubjectKind
            or type(self.subject_status) is not RecordedSubjectStatus
        ):
            fail_review_assignment_operation()
        if _revalidation_failed(lambda: PrincipalId(self.principal_id.value)):
            fail_review_assignment_operation()

    def require_valid(self) -> None:
        RecordedIdentityProjection(
            principal_id=self.principal_id,
            subject_kind=self.subject_kind,
            subject_status=self.subject_status,
        )


def _identity_payload(value: RecordedIdentityProjection) -> dict[str, str]:
    value.require_valid()
    return {
        "principal_id": str(value.principal_id.value),
        "subject_kind": value.subject_kind.value,
        "subject_status": value.subject_status.value,
    }


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
        fail_review_assignment_operation()
    return encoded


def _canonical_sha256(payload: dict[str, object]) -> RecordedSha256:
    return RecordedSha256(hashlib.sha256(_canonical_bytes(payload)).hexdigest())


def _require_sha256(value: object) -> RecordedSha256:
    if type(value) is not RecordedSha256:
        fail_review_assignment_operation()
    return RecordedSha256(value.value)


def _require_principal(value: object) -> PrincipalId:
    if type(value) is not PrincipalId:
        fail_review_assignment_operation()
    if _revalidation_failed(lambda: PrincipalId(value.value)):
        fail_review_assignment_operation()
    return value


def _require_assignment_id(value: object) -> ReviewAssignmentId:
    if type(value) is not ReviewAssignmentId:
        fail_review_assignment_operation()
    if _revalidation_failed(lambda: ReviewAssignmentId(value.value)):
        fail_review_assignment_operation()
    return value


def _require_article_version_id(value: object) -> ArticleVersionId:
    if type(value) is not ArticleVersionId:
        fail_review_assignment_operation()
    if _revalidation_failed(lambda: ArticleVersionId(value.value)):
        fail_review_assignment_operation()
    return value


def _require_timestamp(value: object) -> UtcTimestamp:
    if type(value) is not UtcTimestamp:
        fail_review_assignment_operation()
    if _revalidation_failed(lambda: UtcTimestamp(value.value)):
        fail_review_assignment_operation()
    return value


def _require_etag(value: object) -> StrongEtag:
    """Revalidate one implementation-local recorded concurrency coordinate."""

    if type(value) is not StrongEtag:
        fail_review_assignment_operation()
    if _revalidation_failed(lambda: StrongEtag(value.value)):
        fail_review_assignment_operation()
    return value


def _require_idempotency_key(value: object) -> IdempotencyKey:
    if type(value) is not IdempotencyKey:
        fail_review_assignment_operation()
    if _revalidation_failed(lambda: IdempotencyKey(value.value)):
        fail_review_assignment_operation()
    return value


def _require_entity_version(value: object) -> EntityVersion:
    if type(value) is not EntityVersion:
        fail_review_assignment_operation()
    if _revalidation_failed(lambda: EntityVersion(value.value)):
        fail_review_assignment_operation()
    return value


def _require_correlation(value: object) -> CorrelationId:
    if type(value) is not CorrelationId:
        fail_review_assignment_operation()
    if _revalidation_failed(lambda: CorrelationId(value.value)):
        fail_review_assignment_operation()
    return value


def _normalize_target(value: object) -> AuthorizationTarget:
    """Detach one exact target while assigning no PR2 scope semantics."""

    if type(value) is not AuthorizationTarget:
        fail_review_assignment_operation()
    failed = False
    normalized: AuthorizationTarget | None = None
    try:
        scope = value.scope
        if (
            type(scope) is not ResourceScope
            or type(scope.kind) is not ResourceScopeKind
            or type(scope.site_id) is not UUID
            or type(scope.resource_id) is not UUID
        ):
            fail_review_assignment_operation()
        normalized_scope = ResourceScope(
            kind=scope.kind,
            site_id=scope.site_id,
            resource_id=scope.resource_id,
        )
        state = value.state
        normalized_state = None
        if state is not None:
            if type(state) is not ResourceState:
                fail_review_assignment_operation()
            normalized_state = ResourceState(state.value)
        normalized = AuthorizationTarget(
            scope=normalized_scope,
            state=normalized_state,
        )
        if normalized != value:
            fail_review_assignment_operation()
    except Exception:
        failed = True
    if failed or normalized is None:
        fail_review_assignment_operation()
    return normalized


def _require_target(value: object) -> AuthorizationTarget:
    """Revalidate the existing target while retaining its exact coordinate."""

    _normalize_target(value)
    assert type(value) is AuthorizationTarget
    return value


def _require_decision_reference(
    value: object,
) -> ReviewDecisionReference:
    if type(value) is not ReviewDecisionReference:
        fail_review_assignment_operation()
    if _revalidation_failed(
        lambda: ReviewDecisionReference(
            value.decision_id,
            value.review_assignment_id,
            value.article_version_id,
        )
    ):
        fail_review_assignment_operation()
    return value


def _timestamp_text(value: UtcTimestamp) -> str:
    return value.value.isoformat().replace("+00:00", "Z")


def _target_payload(target: AuthorizationTarget) -> list[str]:
    # This existing canonical key is opaque recorded input.  PR2 never infers a
    # hierarchy or relationship to its separate assignment/article coordinates.
    return list(target.canonical_key)


def _decision_reference_payload(
    value: ReviewDecisionReference | None,
) -> dict[str, str] | None:
    if value is None:
        return None
    return {
        "article_version_id": str(value.article_version_id.value),
        "decision_id": str(value.decision_id.value),
        "review_assignment_id": str(value.review_assignment_id.value),
    }


@final
@dataclass(frozen=True, slots=True, repr=False)
class ListReviewAssignmentsRequest(_RedactedValue):
    """Recorded-local PUBADM-001 projection request; it has no write receipt."""

    correlation_id: CorrelationId
    target: AuthorizationTarget
    article_version_id: ArticleVersionId | None = None
    assigned_to: PrincipalId | None = None
    status: ReviewAssignmentState | None = None
    limit: int = 100
    operation: ReviewAssignmentOperation = field(
        init=False, default=ReviewAssignmentOperation.LIST
    )
    request_sha256: RecordedSha256 = field(init=False)

    def __post_init__(self) -> None:
        self._validate_components()
        object.__setattr__(self, "request_sha256", self._expected_sha256())

    def _validate_components(self) -> None:
        _require_correlation(self.correlation_id)
        _require_target(self.target)
        if self.article_version_id is not None:
            _require_article_version_id(self.article_version_id)
        if self.assigned_to is not None:
            _require_principal(self.assigned_to)
        if self.status is not None and type(self.status) is not ReviewAssignmentState:
            fail_review_assignment_operation()
        if type(self.limit) is not int or not 1 <= self.limit <= _MAX_LIST_LIMIT:
            fail_review_assignment_operation()

    def _payload(self) -> dict[str, object]:
        return {
            "article_version_id": (
                None
                if self.article_version_id is None
                else str(self.article_version_id.value)
            ),
            "assigned_to": (
                None if self.assigned_to is None else str(self.assigned_to.value)
            ),
            "correlation_id": self.correlation_id.value,
            "limit": self.limit,
            "operation_id": self.operation.value,
            "profile": RECORDED_LOCAL_PROFILE,
            "status": None if self.status is None else self.status.value,
            "target": _target_payload(self.target),
        }

    def _expected_sha256(self) -> RecordedSha256:
        return _canonical_sha256(self._payload())

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        return _canonical_bytes(self._payload())

    def require_valid(self) -> None:
        self._validate_components()
        if (
            self.operation is not ReviewAssignmentOperation.LIST
            or _require_sha256(self.request_sha256) != self._expected_sha256()
        ):
            fail_review_assignment_operation()


@final
@dataclass(frozen=True, slots=True, repr=False)
class CreateReviewAssignmentRequest(_RedactedValue):
    """Recorded-local PUBADM-002 request with explicit deterministic inputs."""

    correlation_id: CorrelationId
    target: AuthorizationTarget
    assignment_id: ReviewAssignmentId
    article_version_id: ArticleVersionId
    review_type: ReviewType
    assigned_to: PrincipalId
    priority: int
    created_at: UtcTimestamp
    idempotency_key: IdempotencyKey
    operation: ReviewAssignmentOperation = field(
        init=False, default=ReviewAssignmentOperation.CREATE
    )
    request_sha256: RecordedSha256 = field(init=False)

    def __post_init__(self) -> None:
        self._validate_components()
        object.__setattr__(self, "request_sha256", self._expected_sha256())

    def _validate_components(self) -> None:
        _require_correlation(self.correlation_id)
        _require_target(self.target)
        _require_assignment_id(self.assignment_id)
        _require_article_version_id(self.article_version_id)
        if type(self.review_type) is not ReviewType:
            fail_review_assignment_operation()
        _require_principal(self.assigned_to)
        if type(self.priority) is not int or not 0 <= self.priority <= 100:
            fail_review_assignment_operation()
        _require_timestamp(self.created_at)
        _require_idempotency_key(self.idempotency_key)

    def _payload(self) -> dict[str, object]:
        return {
            "article_version_id": str(self.article_version_id.value),
            "assigned_to": str(self.assigned_to.value),
            "assignment_id": str(self.assignment_id.value),
            "correlation_id": self.correlation_id.value,
            "created_at": _timestamp_text(self.created_at),
            "operation_id": self.operation.value,
            "priority": self.priority,
            "profile": RECORDED_LOCAL_PROFILE,
            "review_type": self.review_type.value,
            "target": _target_payload(self.target),
        }

    def _expected_sha256(self) -> RecordedSha256:
        return _canonical_sha256(self._payload())

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        return _canonical_bytes(self._payload())

    def require_valid(self) -> None:
        self._validate_components()
        if (
            self.operation is not ReviewAssignmentOperation.CREATE
            or _require_sha256(self.request_sha256) != self._expected_sha256()
        ):
            fail_review_assignment_operation()


@final
@dataclass(frozen=True, slots=True, repr=False)
class UpdateReviewAssignmentRequest(_RedactedValue):
    """Status-transition-only recorded subset of PUBADM-003.

    Priority, assignment, article, type, assigner, assignee, and creation time
    are not mutable inputs.  ``due_at`` and ``instructions`` do not exist here.
    """

    correlation_id: CorrelationId
    target: AuthorizationTarget
    assignment_id: ReviewAssignmentId
    article_version_id: ArticleVersionId
    target_state: ReviewAssignmentState
    occurred_at: UtcTimestamp
    expected_lock_version: EntityVersion
    if_match: StrongEtag
    idempotency_key: IdempotencyKey
    completion_decision_reference: ReviewDecisionReference | None = None
    operation: ReviewAssignmentOperation = field(
        init=False, default=ReviewAssignmentOperation.UPDATE
    )
    request_sha256: RecordedSha256 = field(init=False)

    def __post_init__(self) -> None:
        self._validate_components()
        object.__setattr__(self, "request_sha256", self._expected_sha256())

    def _validate_components(self) -> None:
        _require_correlation(self.correlation_id)
        _require_target(self.target)
        _require_assignment_id(self.assignment_id)
        _require_article_version_id(self.article_version_id)
        if type(self.target_state) is not ReviewAssignmentState:
            fail_review_assignment_operation()
        _require_timestamp(self.occurred_at)
        _require_entity_version(self.expected_lock_version)
        _require_etag(self.if_match)
        _require_idempotency_key(self.idempotency_key)
        if self.completion_decision_reference is not None:
            _require_decision_reference(self.completion_decision_reference)

    def _payload(self) -> dict[str, object]:
        return {
            "article_version_id": str(self.article_version_id.value),
            "assignment_id": str(self.assignment_id.value),
            "completion_decision_reference": _decision_reference_payload(
                self.completion_decision_reference
            ),
            "correlation_id": self.correlation_id.value,
            "expected_lock_version": self.expected_lock_version.value,
            "if_match": self.if_match.value,
            "occurred_at": _timestamp_text(self.occurred_at),
            "operation_id": self.operation.value,
            "profile": RECORDED_LOCAL_PROFILE,
            "target": _target_payload(self.target),
            "target_state": self.target_state.value,
        }

    def _expected_sha256(self) -> RecordedSha256:
        return _canonical_sha256(self._payload())

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        return _canonical_bytes(self._payload())

    def require_valid(self) -> None:
        self._validate_components()
        if (
            self.operation is not ReviewAssignmentOperation.UPDATE
            or _require_sha256(self.request_sha256) != self._expected_sha256()
        ):
            fail_review_assignment_operation()


ReviewAssignmentRequest: TypeAlias = (
    ListReviewAssignmentsRequest
    | CreateReviewAssignmentRequest
    | UpdateReviewAssignmentRequest
)


def _require_permission(value: object) -> PermissionScope:
    if type(value) is not PermissionScope:
        fail_review_assignment_operation()
    if _revalidation_failed(lambda: PermissionScope(value.value)):
        fail_review_assignment_operation()
    return value


def _require_grant(value: object) -> AuthorizationGrant:
    """Return a detached exact ALLOW/RULE_MATCH ST-0403 grant."""

    if type(value) is not AuthorizationGrant:
        fail_review_assignment_operation()
    failed = False
    normalized: AuthorizationGrant | None = None
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
            fail_review_assignment_operation()
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
        fail_review_assignment_operation()
    return normalized


def _grant_payload(grant: AuthorizationGrant) -> dict[str, object]:
    normalized = _require_grant(grant)
    decision = object.__getattribute__(normalized, "_decision")
    assert type(decision) is AuthorizationDecision
    matched_rule_id = decision.matched_rule_id
    assert type(matched_rule_id) is RuleId
    return {
        "action": decision.action.value,
        "correlation_id": decision.correlation_id.value,
        "effect": decision.effect.value,
        "entitlement_revision": decision.entitlement_revision.value,
        "matched_rule_id": matched_rule_id.value,
        "policy_fingerprint": decision.policy_fingerprint,
        "policy_revision": decision.policy_revision.value,
        "reason": decision.reason.value,
        "target": _target_payload(decision.target),
    }


def _request_coordinates(
    request: ReviewAssignmentRequest,
) -> tuple[ReviewAssignmentId | None, ArticleVersionId | None]:
    if type(request) is ListReviewAssignmentsRequest:
        return None, request.article_version_id
    if type(request) is CreateReviewAssignmentRequest:
        return request.assignment_id, request.article_version_id
    if type(request) is UpdateReviewAssignmentRequest:
        return request.assignment_id, request.article_version_id
    fail_review_assignment_operation()


def _authorization_payload(
    *,
    operation: ReviewAssignmentOperation,
    request_sha256: RecordedSha256,
    correlation_id: CorrelationId,
    target: AuthorizationTarget,
    grant: AuthorizationGrant,
    permission_scope: PermissionScope,
    actor: RecordedIdentityProjection,
    reviewer: RecordedIdentityProjection | None,
    assignment_id: ReviewAssignmentId | None,
    article_version_id: ArticleVersionId | None,
) -> dict[str, object]:
    return {
        "actor": _identity_payload(actor),
        "article_version_id": (
            None if article_version_id is None else str(article_version_id.value)
        ),
        "assignment_id": (None if assignment_id is None else str(assignment_id.value)),
        "correlation_id": correlation_id.value,
        "grant": _grant_payload(grant),
        "operation_id": operation.value,
        "permission_scope": permission_scope.value,
        "profile": RECORDED_LOCAL_PROFILE,
        "request_sha256": request_sha256.value,
        "reviewer": None if reviewer is None else _identity_payload(reviewer),
        "target": _target_payload(target),
    }


def _validate_authorization_components(
    *,
    operation: object,
    request_sha256: object,
    correlation_id: object,
    target: object,
    grant: object,
    permission_scope: object,
    actor: object,
    reviewer: object,
    assignment_id: object,
    article_version_id: object,
) -> None:
    if type(operation) is not ReviewAssignmentOperation:
        fail_review_assignment_operation()
    _require_sha256(request_sha256)
    _require_correlation(correlation_id)
    _require_target(target)
    _require_grant(grant)
    _require_permission(permission_scope)
    if type(actor) is not RecordedIdentityProjection:
        fail_review_assignment_operation()
    actor.require_valid()
    if reviewer is not None:
        if type(reviewer) is not RecordedIdentityProjection:
            fail_review_assignment_operation()
        reviewer.require_valid()
    if assignment_id is not None:
        _require_assignment_id(assignment_id)
    if article_version_id is not None:
        _require_article_version_id(article_version_id)
    if operation is ReviewAssignmentOperation.LIST:
        if assignment_id is not None or reviewer is not None:
            fail_review_assignment_operation()
    elif assignment_id is None or article_version_id is None or reviewer is None:
        fail_review_assignment_operation()


class _RecordedAuthorizationPermit:
    __slots__ = ()


_RECORDED_AUTHORIZATION_PERMIT = _RecordedAuthorizationPermit()


@final
class RecordedReviewerAuthorizationV1(_RedactedValue):
    """Adapter-produced, hash-bound recorded self-consistency proof.

    The target remains an opaque exact coordinate.  This record establishes no
    authentication, identity attestation, canonical permission, or real-world
    relationship among target, assignment, and article coordinates.
    """

    __slots__ = (
        "_actor",
        "_article_version_id",
        "_assignment_id",
        "_authorization_sha256",
        "_correlation_id",
        "_grant",
        "_operation",
        "_permission_scope",
        "_request_sha256",
        "_reviewer",
        "_target",
    )
    _operation: ReviewAssignmentOperation
    _request_sha256: RecordedSha256
    _correlation_id: CorrelationId
    _target: AuthorizationTarget
    _grant: AuthorizationGrant
    _permission_scope: PermissionScope
    _actor: RecordedIdentityProjection
    _reviewer: RecordedIdentityProjection | None
    _assignment_id: ReviewAssignmentId | None
    _article_version_id: ArticleVersionId | None
    _authorization_sha256: RecordedSha256

    def __init__(
        self,
        *,
        operation: ReviewAssignmentOperation,
        request_sha256: RecordedSha256,
        correlation_id: CorrelationId,
        target: AuthorizationTarget,
        grant: AuthorizationGrant,
        permission_scope: PermissionScope,
        actor: RecordedIdentityProjection,
        reviewer: RecordedIdentityProjection | None,
        assignment_id: ReviewAssignmentId | None,
        article_version_id: ArticleVersionId | None,
        authorization_sha256: RecordedSha256,
        _recorded_local_permit: object = None,
    ) -> None:
        if _recorded_local_permit is not _RECORDED_AUTHORIZATION_PERMIT:
            fail_review_assignment_operation(
                ReviewAssignmentOperationFailureCode.NOT_AUTHORIZED
            )
        object.__setattr__(self, "_operation", operation)
        object.__setattr__(self, "_request_sha256", request_sha256)
        object.__setattr__(self, "_correlation_id", correlation_id)
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_grant", grant)
        object.__setattr__(self, "_permission_scope", permission_scope)
        object.__setattr__(self, "_actor", actor)
        object.__setattr__(self, "_reviewer", reviewer)
        object.__setattr__(self, "_assignment_id", assignment_id)
        object.__setattr__(self, "_article_version_id", article_version_id)
        object.__setattr__(self, "_authorization_sha256", authorization_sha256)
        self.require_valid()

    @property
    def profile(self) -> str:
        return RECORDED_LOCAL_PROFILE

    @property
    def operation(self) -> ReviewAssignmentOperation:
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
    def reviewer(self) -> RecordedIdentityProjection | None:
        return self._reviewer

    @property
    def assignment_id(self) -> ReviewAssignmentId | None:
        return self._assignment_id

    @property
    def article_version_id(self) -> ArticleVersionId | None:
        return self._article_version_id

    @property
    def authorization_sha256(self) -> RecordedSha256:
        return self._authorization_sha256

    def _payload(self) -> dict[str, object]:
        return _authorization_payload(
            operation=self.operation,
            request_sha256=self.request_sha256,
            correlation_id=self.correlation_id,
            target=self.target,
            grant=self.grant,
            permission_scope=self.permission_scope,
            actor=self.actor,
            reviewer=self.reviewer,
            assignment_id=self.assignment_id,
            article_version_id=self.article_version_id,
        )

    def require_valid(self) -> None:
        _validate_authorization_components(
            operation=self.operation,
            request_sha256=self.request_sha256,
            correlation_id=self.correlation_id,
            target=self.target,
            grant=self.grant,
            permission_scope=self.permission_scope,
            actor=self.actor,
            reviewer=self.reviewer,
            assignment_id=self.assignment_id,
            article_version_id=self.article_version_id,
        )
        if _require_sha256(self.authorization_sha256) != _canonical_sha256(
            self._payload()
        ):
            fail_review_assignment_operation(
                ReviewAssignmentOperationFailureCode.NOT_AUTHORIZED
            )

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("RecordedReviewerAuthorizationV1 is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("RecordedReviewerAuthorizationV1 is immutable")


def build_recorded_reviewer_authorization(
    *,
    request: ReviewAssignmentRequest,
    grant: AuthorizationGrant,
    permission_scope: PermissionScope,
    actor: RecordedIdentityProjection,
    reviewer: RecordedIdentityProjection | None,
) -> RecordedReviewerAuthorizationV1:
    """Build one immutable, non-authoritative recorded-local proof."""

    if type(request) not in {
        ListReviewAssignmentsRequest,
        CreateReviewAssignmentRequest,
        UpdateReviewAssignmentRequest,
    }:
        fail_review_assignment_operation()
    request.require_valid()
    normalized_grant = _require_grant(grant)
    assignment_id, article_version_id = _request_coordinates(request)
    _validate_authorization_components(
        operation=request.operation,
        request_sha256=request.request_sha256,
        correlation_id=request.correlation_id,
        target=request.target,
        grant=normalized_grant,
        permission_scope=permission_scope,
        actor=actor,
        reviewer=reviewer,
        assignment_id=assignment_id,
        article_version_id=article_version_id,
    )
    digest = _canonical_sha256(
        _authorization_payload(
            operation=request.operation,
            request_sha256=request.request_sha256,
            correlation_id=request.correlation_id,
            target=request.target,
            grant=normalized_grant,
            permission_scope=permission_scope,
            actor=actor,
            reviewer=reviewer,
            assignment_id=assignment_id,
            article_version_id=article_version_id,
        )
    )
    return RecordedReviewerAuthorizationV1(
        operation=request.operation,
        request_sha256=request.request_sha256,
        correlation_id=request.correlation_id,
        target=request.target,
        grant=normalized_grant,
        permission_scope=permission_scope,
        actor=actor,
        reviewer=reviewer,
        assignment_id=assignment_id,
        article_version_id=article_version_id,
        authorization_sha256=digest,
        _recorded_local_permit=_RECORDED_AUTHORIZATION_PERMIT,
    )


def _require_uuid7(value: object) -> UUID:
    if type(value) is not UUID or value.version != 7 or value.variant != RFC_4122:
        fail_review_assignment_operation()
    return value


def _require_assignment(value: object) -> ReviewAssignment:
    if type(value) is not ReviewAssignment:
        fail_review_assignment_operation()
    if _revalidation_failed(
        lambda: ReviewAssignment(
            value.assignment_id,
            value.article_version_id,
            value.review_type,
            value.assigned_by,
            value.assigned_to,
            value.priority,
            value.status,
            value.started_at,
            value.completed_at,
            value.cancelled_at,
            value.created_at,
            value.updated_at,
            value.lock_version,
            value.completion_decision_reference,
        )
    ):
        fail_review_assignment_operation()
    return value


def _assignment_payload(assignment: ReviewAssignment) -> dict[str, object]:
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
        "completion_decision_reference": _decision_reference_payload(
            assignment.completion_decision_reference
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


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedAssignmentSnapshotV1(_RedactedValue):
    """Immutable snapshot with an implementation-local recorded ETag."""

    assignment: ReviewAssignment
    etag: StrongEtag
    snapshot_sha256: RecordedSha256 = field(init=False)

    def __post_init__(self) -> None:
        _require_assignment(self.assignment)
        _require_etag(self.etag)
        object.__setattr__(self, "snapshot_sha256", self._expected_sha256())

    @property
    def profile(self) -> str:
        return RECORDED_LOCAL_PROFILE

    def _payload(self) -> dict[str, object]:
        return {
            "assignment": _assignment_payload(self.assignment),
            "etag": self.etag.value,
            "profile": RECORDED_LOCAL_PROFILE,
        }

    def _expected_sha256(self) -> RecordedSha256:
        return _canonical_sha256(self._payload())

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        return _canonical_bytes(
            {**self._payload(), "snapshot_sha256": self.snapshot_sha256.value}
        )

    def require_valid(self) -> None:
        _require_assignment(self.assignment)
        _require_etag(self.etag)
        if _require_sha256(self.snapshot_sha256) != self._expected_sha256():
            fail_review_assignment_operation(
                ReviewAssignmentOperationFailureCode.OUTCOME_MISMATCH
            )


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedAssignmentTransitionV1(_RedactedValue):
    before: RecordedAssignmentSnapshotV1
    after: RecordedAssignmentSnapshotV1
    transition_sha256: RecordedSha256 = field(init=False)

    def __post_init__(self) -> None:
        self._validate_components()
        object.__setattr__(self, "transition_sha256", self._expected_sha256())

    @property
    def profile(self) -> str:
        return RECORDED_LOCAL_PROFILE

    def _validate_components(self) -> None:
        if (
            type(self.before) is not RecordedAssignmentSnapshotV1
            or type(self.after) is not RecordedAssignmentSnapshotV1
        ):
            fail_review_assignment_operation()
        self.before.require_valid()
        self.after.require_valid()

    def _payload(self) -> dict[str, object]:
        return {
            "after_sha256": self.after.snapshot_sha256.value,
            "before_sha256": self.before.snapshot_sha256.value,
            "profile": RECORDED_LOCAL_PROFILE,
        }

    def _expected_sha256(self) -> RecordedSha256:
        return _canonical_sha256(self._payload())

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        return _canonical_bytes(
            {**self._payload(), "transition_sha256": self.transition_sha256.value}
        )

    def require_valid(self) -> None:
        self._validate_components()
        if _require_sha256(self.transition_sha256) != self._expected_sha256():
            fail_review_assignment_operation(
                ReviewAssignmentOperationFailureCode.OUTCOME_MISMATCH
            )


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
    correlation_id: CorrelationId
    request_sha256: RecordedSha256
    before_snapshot_sha256: RecordedSha256 | None
    after_snapshot_sha256: RecordedSha256
    audit_sha256: RecordedSha256 = field(init=False)

    def __post_init__(self) -> None:
        self._validate_components()
        object.__setattr__(self, "audit_sha256", self._expected_sha256())

    @property
    def profile(self) -> str:
        return RECORDED_LOCAL_PROFILE

    def _validate_components(self) -> None:
        _require_uuid7(self.event_id)
        if type(self.action) is not RecordedAuditAction:
            fail_review_assignment_operation()
        _require_timestamp(self.occurred_at)
        _require_principal(self.actor_id)
        _require_assignment_id(self.assignment_id)
        _require_article_version_id(self.article_version_id)
        _require_correlation(self.correlation_id)
        _require_sha256(self.request_sha256)
        if self.before_snapshot_sha256 is not None:
            _require_sha256(self.before_snapshot_sha256)
        _require_sha256(self.after_snapshot_sha256)
        if (
            self.action is RecordedAuditAction.ASSIGNMENT_CREATE
            and self.before_snapshot_sha256 is not None
        ) or (
            self.action is RecordedAuditAction.ASSIGNMENT_UPDATE
            and self.before_snapshot_sha256 is None
        ):
            fail_review_assignment_operation()

    def _payload(self) -> dict[str, object]:
        return {
            "action": self.action.value,
            "actor_id": str(self.actor_id.value),
            "after_snapshot_sha256": self.after_snapshot_sha256.value,
            "article_version_id": str(self.article_version_id.value),
            "assignment_id": str(self.assignment_id.value),
            "before_snapshot_sha256": (
                None
                if self.before_snapshot_sha256 is None
                else self.before_snapshot_sha256.value
            ),
            "correlation_id": self.correlation_id.value,
            "event_id": str(self.event_id),
            "occurred_at": _timestamp_text(self.occurred_at),
            "profile": RECORDED_LOCAL_PROFILE,
            "request_sha256": self.request_sha256.value,
        }

    def _expected_sha256(self) -> RecordedSha256:
        return _canonical_sha256(self._payload())

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        return _canonical_bytes(
            {**self._payload(), "audit_sha256": self.audit_sha256.value}
        )

    def require_valid(self) -> None:
        self._validate_components()
        if _require_sha256(self.audit_sha256) != self._expected_sha256():
            fail_review_assignment_operation(
                ReviewAssignmentOperationFailureCode.OUTCOME_MISMATCH
            )


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedIdempotencyReceiptV1(_RedactedValue):
    """Hash-only receipt; raw Idempotency-Key is never retained in results."""

    operation: ReviewAssignmentOperation
    idempotency_key_sha256: RecordedSha256
    request_sha256: RecordedSha256
    recorded_output_sha256: RecordedSha256
    receipt_sha256: RecordedSha256 = field(init=False)

    def __post_init__(self) -> None:
        self._validate_components()
        object.__setattr__(self, "receipt_sha256", self._expected_sha256())

    @classmethod
    def recorded_local(
        cls,
        *,
        operation: ReviewAssignmentOperation,
        idempotency_key: IdempotencyKey,
        request_sha256: RecordedSha256,
        recorded_output_sha256: RecordedSha256,
    ) -> RecordedIdempotencyReceiptV1:
        key = _require_idempotency_key(idempotency_key)
        return cls(
            operation=operation,
            idempotency_key_sha256=RecordedSha256(
                hashlib.sha256(key.value.encode("ascii", errors="strict")).hexdigest()
            ),
            request_sha256=request_sha256,
            recorded_output_sha256=recorded_output_sha256,
        )

    @property
    def profile(self) -> str:
        return RECORDED_LOCAL_PROFILE

    def _validate_components(self) -> None:
        if type(
            self.operation
        ) is not ReviewAssignmentOperation or self.operation not in {
            ReviewAssignmentOperation.CREATE,
            ReviewAssignmentOperation.UPDATE,
        }:
            fail_review_assignment_operation()
        _require_sha256(self.idempotency_key_sha256)
        _require_sha256(self.request_sha256)
        _require_sha256(self.recorded_output_sha256)

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
        self._validate_components()
        if _require_sha256(self.receipt_sha256) != self._expected_sha256():
            fail_review_assignment_operation(
                ReviewAssignmentOperationFailureCode.OUTCOME_MISMATCH
            )


def recorded_mutation_output_sha256(
    *,
    snapshot_sha256: RecordedSha256,
    audit_sha256: RecordedSha256,
    transition_sha256: RecordedSha256 | None,
) -> RecordedSha256:
    """Build the versioned local receipt coordinate from immutable artifacts."""

    _require_sha256(snapshot_sha256)
    _require_sha256(audit_sha256)
    if transition_sha256 is not None:
        _require_sha256(transition_sha256)
    return _canonical_sha256(
        {
            "audit_sha256": audit_sha256.value,
            "profile": RECORDED_LOCAL_PROFILE,
            "snapshot_sha256": snapshot_sha256.value,
            "transition_sha256": (
                None if transition_sha256 is None else transition_sha256.value
            ),
        }
    )


def _snapshot_order_key(snapshot: RecordedAssignmentSnapshotV1) -> tuple[str, str]:
    assignment = snapshot.assignment
    return (_timestamp_text(assignment.created_at), assignment.assignment_id.value.hex)


def _closed_result_flags_valid(result: object) -> bool:
    return (
        getattr(result, "execution", None) is RecordedExecution.RECORDED_ONLY
        and getattr(result, "persistence", None) is RecordedExecution.NOT_EXECUTED
        and getattr(result, "transaction", None) is RecordedExecution.NOT_EXECUTED
        and getattr(result, "unit_of_work", None) is RecordedExecution.NOT_EXECUTED
        and getattr(result, "database_enforcement", None)
        is RecordedExecution.NOT_EXECUTED
        and getattr(result, "audit_atomicity", None) is RecordedExecution.NOT_EXECUTED
        and getattr(result, "events", None) is RecordedExecution.NOT_EXECUTED
        and getattr(result, "outbox", None) is RecordedExecution.NOT_EXECUTED
        and getattr(result, "delivery", None) is RecordedExecution.NOT_EXECUTED
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
        fail_review_assignment_operation(
            ReviewAssignmentOperationFailureCode.OUTCOME_MISMATCH
        )
    return {
        "audit_atomicity": RecordedExecution.NOT_EXECUTED.value,
        "database_enforcement": RecordedExecution.NOT_EXECUTED.value,
        "delivery": RecordedExecution.NOT_EXECUTED.value,
        "events": RecordedExecution.NOT_EXECUTED.value,
        "execution": RecordedExecution.RECORDED_ONLY.value,
        "formal_verification": RecordedExecution.NOT_EXECUTED.value,
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


@final
@dataclass(frozen=True, slots=True, repr=False)
class ListReviewAssignmentsResult(_RedactedValue):
    """Ordered read projection with no audit or idempotency artifact."""

    authorization_sha256: RecordedSha256
    request_sha256: RecordedSha256
    items: tuple[RecordedAssignmentSnapshotV1, ...]
    operation: ReviewAssignmentOperation = field(
        init=False, default=ReviewAssignmentOperation.LIST
    )
    execution: RecordedExecution = field(
        init=False, default=RecordedExecution.RECORDED_ONLY
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
        self._validate_components()
        object.__setattr__(self, "result_sha256", self._expected_sha256())

    def _validate_components(self) -> None:
        _require_sha256(self.authorization_sha256)
        _require_sha256(self.request_sha256)
        if type(self.items) is not tuple or any(
            type(item) is not RecordedAssignmentSnapshotV1 for item in self.items
        ):
            fail_review_assignment_operation()
        for item in self.items:
            item.require_valid()
        keys = tuple(_snapshot_order_key(item) for item in self.items)
        assignment_ids = tuple(item.assignment.assignment_id for item in self.items)
        if (
            self.operation is not ReviewAssignmentOperation.LIST
            or keys != tuple(sorted(keys))
            or len(set(assignment_ids)) != len(assignment_ids)
            or not _closed_result_flags_valid(self)
        ):
            fail_review_assignment_operation(
                ReviewAssignmentOperationFailureCode.OUTCOME_MISMATCH
            )

    def _payload(self) -> dict[str, object]:
        return {
            **_closed_result_payload(self),
            "authorization_sha256": self.authorization_sha256.value,
            "items": [item.snapshot_sha256.value for item in self.items],
            "operation_id": self.operation.value,
            "profile": RECORDED_LOCAL_PROFILE,
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
        self._validate_components()
        if _require_sha256(self.result_sha256) != self._expected_sha256():
            fail_review_assignment_operation(
                ReviewAssignmentOperationFailureCode.OUTCOME_MISMATCH
            )


@final
@dataclass(frozen=True, slots=True, repr=False)
class CreateReviewAssignmentResult(_RedactedValue):
    authorization_sha256: RecordedSha256
    request_sha256: RecordedSha256
    snapshot: RecordedAssignmentSnapshotV1
    audit: RecordedAuditArtifactV1
    idempotency: RecordedIdempotencyReceiptV1
    operation: ReviewAssignmentOperation = field(
        init=False, default=ReviewAssignmentOperation.CREATE
    )
    execution: RecordedExecution = field(
        init=False, default=RecordedExecution.RECORDED_ONLY
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
        self._validate_components()
        object.__setattr__(self, "result_sha256", self._expected_sha256())

    def _validate_components(self) -> None:
        _require_sha256(self.authorization_sha256)
        _require_sha256(self.request_sha256)
        if (
            type(self.snapshot) is not RecordedAssignmentSnapshotV1
            or type(self.audit) is not RecordedAuditArtifactV1
            or type(self.idempotency) is not RecordedIdempotencyReceiptV1
        ):
            fail_review_assignment_operation()
        self.snapshot.require_valid()
        self.audit.require_valid()
        self.idempotency.require_valid()
        assignment = self.snapshot.assignment
        expected_output = recorded_mutation_output_sha256(
            snapshot_sha256=self.snapshot.snapshot_sha256,
            audit_sha256=self.audit.audit_sha256,
            transition_sha256=None,
        )
        if (
            self.operation is not ReviewAssignmentOperation.CREATE
            or assignment.status is not ReviewAssignmentState.ASSIGNED
            or assignment.lock_version != 0
            or self.audit.action is not RecordedAuditAction.ASSIGNMENT_CREATE
            or self.audit.actor_id != assignment.assigned_by
            or self.audit.assignment_id != assignment.assignment_id
            or self.audit.article_version_id != assignment.article_version_id
            or self.audit.request_sha256 != self.request_sha256
            or self.audit.before_snapshot_sha256 is not None
            or self.audit.after_snapshot_sha256 != self.snapshot.snapshot_sha256
            or self.idempotency.operation is not self.operation
            or self.idempotency.request_sha256 != self.request_sha256
            or self.idempotency.recorded_output_sha256 != expected_output
            or not _closed_result_flags_valid(self)
        ):
            fail_review_assignment_operation(
                ReviewAssignmentOperationFailureCode.OUTCOME_MISMATCH
            )

    def _payload(self) -> dict[str, object]:
        return {
            **_closed_result_payload(self),
            "audit_sha256": self.audit.audit_sha256.value,
            "authorization_sha256": self.authorization_sha256.value,
            "idempotency_receipt_sha256": self.idempotency.receipt_sha256.value,
            "operation_id": self.operation.value,
            "profile": RECORDED_LOCAL_PROFILE,
            "request_sha256": self.request_sha256.value,
            "snapshot_sha256": self.snapshot.snapshot_sha256.value,
        }

    def _expected_sha256(self) -> RecordedSha256:
        return _canonical_sha256(self._payload())

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        return _canonical_bytes(
            {**self._payload(), "result_sha256": self.result_sha256.value}
        )

    def require_valid(self) -> None:
        self._validate_components()
        if _require_sha256(self.result_sha256) != self._expected_sha256():
            fail_review_assignment_operation(
                ReviewAssignmentOperationFailureCode.OUTCOME_MISMATCH
            )


@final
@dataclass(frozen=True, slots=True, repr=False)
class UpdateReviewAssignmentResult(_RedactedValue):
    authorization_sha256: RecordedSha256
    request_sha256: RecordedSha256
    transition: RecordedAssignmentTransitionV1
    audit: RecordedAuditArtifactV1
    idempotency: RecordedIdempotencyReceiptV1
    operation: ReviewAssignmentOperation = field(
        init=False, default=ReviewAssignmentOperation.UPDATE
    )
    execution: RecordedExecution = field(
        init=False, default=RecordedExecution.RECORDED_ONLY
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
        self._validate_components()
        object.__setattr__(self, "result_sha256", self._expected_sha256())

    @property
    def snapshot(self) -> RecordedAssignmentSnapshotV1:
        return self.transition.after

    def _validate_components(self) -> None:
        _require_sha256(self.authorization_sha256)
        _require_sha256(self.request_sha256)
        if (
            type(self.transition) is not RecordedAssignmentTransitionV1
            or type(self.audit) is not RecordedAuditArtifactV1
            or type(self.idempotency) is not RecordedIdempotencyReceiptV1
        ):
            fail_review_assignment_operation()
        self.transition.require_valid()
        self.audit.require_valid()
        self.idempotency.require_valid()
        before = self.transition.before
        after = self.transition.after
        prior = before.assignment
        current = after.assignment
        expected_output = recorded_mutation_output_sha256(
            snapshot_sha256=after.snapshot_sha256,
            audit_sha256=self.audit.audit_sha256,
            transition_sha256=self.transition.transition_sha256,
        )
        if (
            self.operation is not ReviewAssignmentOperation.UPDATE
            or current.assignment_id != prior.assignment_id
            or current.article_version_id != prior.article_version_id
            or current.review_type is not prior.review_type
            or current.assigned_by != prior.assigned_by
            or current.assigned_to != prior.assigned_to
            or current.priority != prior.priority
            or current.created_at != prior.created_at
            or current.lock_version != prior.lock_version + 1
            or current.status is prior.status
            or after.etag == before.etag
            or self.audit.action is not RecordedAuditAction.ASSIGNMENT_UPDATE
            or self.audit.assignment_id != current.assignment_id
            or self.audit.article_version_id != current.article_version_id
            or self.audit.request_sha256 != self.request_sha256
            or self.audit.before_snapshot_sha256 != before.snapshot_sha256
            or self.audit.after_snapshot_sha256 != after.snapshot_sha256
            or self.idempotency.operation is not self.operation
            or self.idempotency.request_sha256 != self.request_sha256
            or self.idempotency.recorded_output_sha256 != expected_output
            or not _closed_result_flags_valid(self)
        ):
            fail_review_assignment_operation(
                ReviewAssignmentOperationFailureCode.OUTCOME_MISMATCH
            )

    def _payload(self) -> dict[str, object]:
        return {
            **_closed_result_payload(self),
            "audit_sha256": self.audit.audit_sha256.value,
            "authorization_sha256": self.authorization_sha256.value,
            "idempotency_receipt_sha256": self.idempotency.receipt_sha256.value,
            "operation_id": self.operation.value,
            "profile": RECORDED_LOCAL_PROFILE,
            "request_sha256": self.request_sha256.value,
            "snapshot_sha256": self.transition.after.snapshot_sha256.value,
            "transition_sha256": self.transition.transition_sha256.value,
        }

    def _expected_sha256(self) -> RecordedSha256:
        return _canonical_sha256(self._payload())

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        return _canonical_bytes(
            {**self._payload(), "result_sha256": self.result_sha256.value}
        )

    def require_valid(self) -> None:
        self._validate_components()
        if _require_sha256(self.result_sha256) != self._expected_sha256():
            fail_review_assignment_operation(
                ReviewAssignmentOperationFailureCode.OUTCOME_MISMATCH
            )


ReviewAssignmentResult: TypeAlias = (
    ListReviewAssignmentsResult
    | CreateReviewAssignmentResult
    | UpdateReviewAssignmentResult
)


__all__ = [
    "CreateReviewAssignmentRequest",
    "CreateReviewAssignmentResult",
    "ListReviewAssignmentsRequest",
    "ListReviewAssignmentsResult",
    "RECORDED_LOCAL_PROFILE",
    "RecordedAssignmentSnapshotV1",
    "RecordedAssignmentTransitionV1",
    "RecordedAuditAction",
    "RecordedAuditArtifactV1",
    "RecordedExecution",
    "RecordedIdentityProjection",
    "RecordedIdempotencyReceiptV1",
    "RecordedReadiness",
    "RecordedReviewerAuthorizationV1",
    "RecordedSha256",
    "RecordedSubjectKind",
    "RecordedSubjectStatus",
    "ReviewAssignmentOperation",
    "ReviewAssignmentOperationFailure",
    "ReviewAssignmentOperationFailureCode",
    "ReviewAssignmentRequest",
    "ReviewAssignmentResult",
    "UpdateReviewAssignmentRequest",
    "UpdateReviewAssignmentResult",
    "fail_review_assignment_operation",
    "recorded_mutation_output_sha256",
]

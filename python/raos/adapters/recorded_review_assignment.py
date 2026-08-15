"""Bounded deterministic adapter for ST-0901 PR2 ENV-DEV/CI fixtures.

The adapter performs no identity lookup, authentication, database access,
transaction, event emission, audit append, publication, or runtime generation.
All IDs, timestamps, grants, snapshots, and ETags are explicit script inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from threading import RLock
from typing import NoReturn, SupportsIndex, TypeAlias, cast, final
from uuid import UUID

from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authorization import AuthorizationGrant, PermissionScope
from raos.domain.publishing.review_assignment_operations import (
    CreateReviewAssignmentRequest,
    CreateReviewAssignmentResult,
    ListReviewAssignmentsRequest,
    ListReviewAssignmentsResult,
    RecordedAssignmentSnapshotV1,
    RecordedAssignmentTransitionV1,
    RecordedAuditAction,
    RecordedAuditArtifactV1,
    RecordedIdempotencyReceiptV1,
    RecordedIdentityProjection,
    RecordedReviewerAuthorizationV1,
    RecordedSha256,
    ReviewAssignmentOperation,
    ReviewAssignmentOperationFailureCode,
    ReviewAssignmentRequest,
    ReviewAssignmentResult,
    UpdateReviewAssignmentRequest,
    UpdateReviewAssignmentResult,
    build_recorded_reviewer_authorization,
    fail_review_assignment_operation,
    recorded_mutation_output_sha256,
)
from raos.domain.publishing.review_workflow import UtcTimestamp


_MAX_SCRIPT_CAPACITY = 100_000
_REDACTED = "<redacted-st0901-pr2-recorded-adapter>"


class _RedactedRecordedAdapterValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded review assignment adapter serialization denied")


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedListReviewAssignmentsStep(_RedactedRecordedAdapterValue):
    request: ListReviewAssignmentsRequest
    grant: AuthorizationGrant
    permission_scope: PermissionScope
    actor: RecordedIdentityProjection
    items: tuple[RecordedAssignmentSnapshotV1, ...]
    _authorization_sha256: RecordedSha256 = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.request) is not ListReviewAssignmentsRequest
            or type(self.grant) is not AuthorizationGrant
            or type(self.permission_scope) is not PermissionScope
            or type(self.actor) is not RecordedIdentityProjection
            or type(self.items) is not tuple
            or any(
                type(item) is not RecordedAssignmentSnapshotV1 for item in self.items
            )
        ):
            fail_review_assignment_operation()
        self.request.require_valid()
        self.actor.require_valid()
        for item in self.items:
            item.require_valid()
        authorization = build_recorded_reviewer_authorization(
            request=self.request,
            grant=self.grant,
            permission_scope=self.permission_scope,
            actor=self.actor,
            reviewer=None,
        )
        object.__setattr__(self, "grant", authorization.grant)
        object.__setattr__(
            self,
            "_authorization_sha256",
            authorization.authorization_sha256,
        )

    @property
    def authorization_sha256(self) -> RecordedSha256:
        return self._authorization_sha256


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedCreateReviewAssignmentStep(_RedactedRecordedAdapterValue):
    request: CreateReviewAssignmentRequest
    grant: AuthorizationGrant
    permission_scope: PermissionScope
    actor: RecordedIdentityProjection
    reviewer: RecordedIdentityProjection
    snapshot: RecordedAssignmentSnapshotV1
    audit_event_id: UUID
    audit_occurred_at: UtcTimestamp
    _authorization_sha256: RecordedSha256 = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.request) is not CreateReviewAssignmentRequest
            or type(self.grant) is not AuthorizationGrant
            or type(self.permission_scope) is not PermissionScope
            or type(self.actor) is not RecordedIdentityProjection
            or type(self.reviewer) is not RecordedIdentityProjection
            or type(self.snapshot) is not RecordedAssignmentSnapshotV1
            or type(self.audit_event_id) is not UUID
            or type(self.audit_occurred_at) is not UtcTimestamp
        ):
            fail_review_assignment_operation()
        self.request.require_valid()
        self.actor.require_valid()
        self.reviewer.require_valid()
        self.snapshot.require_valid()
        # The local audit value performs detached UUIDv7/timestamp validation.
        authorization = build_recorded_reviewer_authorization(
            request=self.request,
            grant=self.grant,
            permission_scope=self.permission_scope,
            actor=self.actor,
            reviewer=self.reviewer,
        )
        object.__setattr__(self, "grant", authorization.grant)
        object.__setattr__(
            self,
            "_authorization_sha256",
            authorization.authorization_sha256,
        )
        _create_audit(
            authorization=authorization,
            request=self.request,
            snapshot=self.snapshot,
            audit_event_id=self.audit_event_id,
            audit_occurred_at=self.audit_occurred_at,
        )

    @property
    def authorization_sha256(self) -> RecordedSha256:
        return self._authorization_sha256


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedUpdateReviewAssignmentStep(_RedactedRecordedAdapterValue):
    request: UpdateReviewAssignmentRequest
    grant: AuthorizationGrant
    permission_scope: PermissionScope
    actor: RecordedIdentityProjection
    reviewer: RecordedIdentityProjection
    transition: RecordedAssignmentTransitionV1
    audit_event_id: UUID
    audit_occurred_at: UtcTimestamp
    _authorization_sha256: RecordedSha256 = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.request) is not UpdateReviewAssignmentRequest
            or type(self.grant) is not AuthorizationGrant
            or type(self.permission_scope) is not PermissionScope
            or type(self.actor) is not RecordedIdentityProjection
            or type(self.reviewer) is not RecordedIdentityProjection
            or type(self.transition) is not RecordedAssignmentTransitionV1
            or type(self.audit_event_id) is not UUID
            or type(self.audit_occurred_at) is not UtcTimestamp
        ):
            fail_review_assignment_operation()
        self.request.require_valid()
        self.actor.require_valid()
        self.reviewer.require_valid()
        self.transition.require_valid()
        authorization = build_recorded_reviewer_authorization(
            request=self.request,
            grant=self.grant,
            permission_scope=self.permission_scope,
            actor=self.actor,
            reviewer=self.reviewer,
        )
        object.__setattr__(self, "grant", authorization.grant)
        object.__setattr__(
            self,
            "_authorization_sha256",
            authorization.authorization_sha256,
        )
        _update_audit(
            authorization=authorization,
            request=self.request,
            transition=self.transition,
            audit_event_id=self.audit_event_id,
            audit_occurred_at=self.audit_occurred_at,
        )

    @property
    def authorization_sha256(self) -> RecordedSha256:
        return self._authorization_sha256


RecordedReviewAssignmentStep: TypeAlias = (
    RecordedListReviewAssignmentsStep
    | RecordedCreateReviewAssignmentStep
    | RecordedUpdateReviewAssignmentStep
)


def _step_request(step: RecordedReviewAssignmentStep) -> ReviewAssignmentRequest:
    return step.request


def _step_authorization(
    step: RecordedReviewAssignmentStep,
) -> RecordedReviewerAuthorizationV1:
    reviewer = getattr(step, "reviewer", None)
    if reviewer is not None and type(reviewer) is not RecordedIdentityProjection:
        fail_review_assignment_operation()
    authorization = build_recorded_reviewer_authorization(
        request=step.request,
        grant=step.grant,
        permission_scope=step.permission_scope,
        actor=step.actor,
        reviewer=reviewer,
    )
    if (
        type(step.authorization_sha256) is not RecordedSha256
        or authorization.authorization_sha256 != step.authorization_sha256
    ):
        fail_review_assignment_operation(
            ReviewAssignmentOperationFailureCode.NOT_AUTHORIZED
        )
    return authorization


def _same_request(left: object, right: object) -> bool:
    try:
        return type(left) is type(right) and left == right
    except Exception:
        return False


def _idempotency_identity(
    request: ReviewAssignmentRequest,
) -> tuple[ReviewAssignmentOperation, str] | None:
    key = getattr(request, "idempotency_key", None)
    if key is None:
        return None
    encoded = key.value.encode("ascii", errors="strict")
    return (
        request.operation,
        hashlib.sha256(encoded).hexdigest(),
    )


def _authorization_matches(
    observed: RecordedReviewerAuthorizationV1,
    expected: RecordedReviewerAuthorizationV1,
) -> bool:
    try:
        observed.require_valid()
        expected.require_valid()
        return (
            observed.authorization_sha256 == expected.authorization_sha256
            and observed.operation is expected.operation
            and observed.request_sha256 == expected.request_sha256
            and observed.correlation_id == expected.correlation_id
            and observed.target == expected.target
            and observed.permission_scope == expected.permission_scope
            and observed.actor == expected.actor
            and observed.reviewer == expected.reviewer
            and observed.assignment_id == expected.assignment_id
            and observed.article_version_id == expected.article_version_id
        )
    except Exception:
        return False


def _create_audit(
    *,
    authorization: RecordedReviewerAuthorizationV1,
    request: CreateReviewAssignmentRequest,
    snapshot: RecordedAssignmentSnapshotV1,
    audit_event_id: UUID,
    audit_occurred_at: UtcTimestamp,
) -> RecordedAuditArtifactV1:
    return RecordedAuditArtifactV1(
        event_id=audit_event_id,
        action=RecordedAuditAction.ASSIGNMENT_CREATE,
        occurred_at=audit_occurred_at,
        actor_id=authorization.actor.principal_id,
        assignment_id=request.assignment_id,
        article_version_id=request.article_version_id,
        correlation_id=request.correlation_id,
        request_sha256=request.request_sha256,
        before_snapshot_sha256=None,
        after_snapshot_sha256=snapshot.snapshot_sha256,
    )


def _update_audit(
    *,
    authorization: RecordedReviewerAuthorizationV1,
    request: UpdateReviewAssignmentRequest,
    transition: RecordedAssignmentTransitionV1,
    audit_event_id: UUID,
    audit_occurred_at: UtcTimestamp,
) -> RecordedAuditArtifactV1:
    return RecordedAuditArtifactV1(
        event_id=audit_event_id,
        action=RecordedAuditAction.ASSIGNMENT_UPDATE,
        occurred_at=audit_occurred_at,
        actor_id=authorization.actor.principal_id,
        assignment_id=request.assignment_id,
        article_version_id=request.article_version_id,
        correlation_id=request.correlation_id,
        request_sha256=request.request_sha256,
        before_snapshot_sha256=transition.before.snapshot_sha256,
        after_snapshot_sha256=transition.after.snapshot_sha256,
    )


def _build_result(
    *,
    step: RecordedReviewAssignmentStep,
    authorization: RecordedReviewerAuthorizationV1,
) -> ReviewAssignmentResult:
    if type(step) is RecordedListReviewAssignmentsStep:
        request = step.request
        if len(step.items) > request.limit or any(
            (
                request.article_version_id is not None
                and item.assignment.article_version_id != request.article_version_id
            )
            or (
                request.assigned_to is not None
                and item.assignment.assigned_to != request.assigned_to
            )
            or (
                request.status is not None
                and item.assignment.status is not request.status
            )
            for item in step.items
        ):
            fail_review_assignment_operation(
                ReviewAssignmentOperationFailureCode.OUTCOME_MISMATCH
            )
        return ListReviewAssignmentsResult(
            authorization_sha256=authorization.authorization_sha256,
            request_sha256=step.request.request_sha256,
            items=step.items,
        )
    if type(step) is RecordedCreateReviewAssignmentStep:
        audit = _create_audit(
            authorization=authorization,
            request=step.request,
            snapshot=step.snapshot,
            audit_event_id=step.audit_event_id,
            audit_occurred_at=step.audit_occurred_at,
        )
        output_sha256 = recorded_mutation_output_sha256(
            snapshot_sha256=step.snapshot.snapshot_sha256,
            audit_sha256=audit.audit_sha256,
            transition_sha256=None,
        )
        return CreateReviewAssignmentResult(
            authorization_sha256=authorization.authorization_sha256,
            request_sha256=step.request.request_sha256,
            snapshot=step.snapshot,
            audit=audit,
            idempotency=RecordedIdempotencyReceiptV1.recorded_local(
                operation=step.request.operation,
                idempotency_key=step.request.idempotency_key,
                request_sha256=step.request.request_sha256,
                recorded_output_sha256=output_sha256,
            ),
        )
    update_step = step
    audit = _update_audit(
        authorization=authorization,
        request=update_step.request,
        transition=update_step.transition,
        audit_event_id=update_step.audit_event_id,
        audit_occurred_at=update_step.audit_occurred_at,
    )
    output_sha256 = recorded_mutation_output_sha256(
        snapshot_sha256=update_step.transition.after.snapshot_sha256,
        audit_sha256=audit.audit_sha256,
        transition_sha256=update_step.transition.transition_sha256,
    )
    return UpdateReviewAssignmentResult(
        authorization_sha256=authorization.authorization_sha256,
        request_sha256=update_step.request.request_sha256,
        transition=update_step.transition,
        audit=audit,
        idempotency=RecordedIdempotencyReceiptV1.recorded_local(
            operation=update_step.request.operation,
            idempotency_key=update_step.request.idempotency_key,
            request_sha256=update_step.request.request_sha256,
            recorded_output_sha256=output_sha256,
        ),
    )


@dataclass(frozen=True, slots=True)
class _ReplayEntry:
    request: CreateReviewAssignmentRequest | UpdateReviewAssignmentRequest
    request_sha256: RecordedSha256
    authorization: RecordedReviewerAuthorizationV1
    result: CreateReviewAssignmentResult | UpdateReviewAssignmentResult
    canonical_bytes: bytes


@final
class RecordedReviewAssignmentAdapter(_RedactedRecordedAdapterValue):
    """Consume exact scripts and retain deterministic mutation replays in memory."""

    __slots__ = ("_index", "_lock", "_replays", "_scripts")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        script_capacity: int,
        scripts: tuple[RecordedReviewAssignmentStep, ...],
    ) -> None:
        valid_types = {
            RecordedListReviewAssignmentsStep,
            RecordedCreateReviewAssignmentStep,
            RecordedUpdateReviewAssignmentStep,
        }
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or type(script_capacity) is not int
            or not 0 < script_capacity <= _MAX_SCRIPT_CAPACITY
            or type(scripts) is not tuple
            or not scripts
            or len(scripts) > script_capacity
            or any(type(step) not in valid_types for step in scripts)
            or any(
                _same_request(_step_request(left), _step_request(right))
                for index, left in enumerate(scripts)
                for right in scripts[index + 1 :]
            )
        ):
            fail_review_assignment_operation()
        self._scripts = scripts
        self._index = 0
        self._replays: dict[tuple[ReviewAssignmentOperation, str], _ReplayEntry] = {}
        self._lock = RLock()

    def issue_authorization(
        self, request: ReviewAssignmentRequest
    ) -> RecordedReviewerAuthorizationV1:
        with self._lock:
            if type(request) not in {
                ListReviewAssignmentsRequest,
                CreateReviewAssignmentRequest,
                UpdateReviewAssignmentRequest,
            }:
                fail_review_assignment_operation(
                    ReviewAssignmentOperationFailureCode.NOT_AUTHORIZED
                )
            request.require_valid()
            # Replays and mismatches are authorized from the retained recorded
            # identity/grant without consulting or consuming the next script.
            identity = _idempotency_identity(request)
            if identity is not None and identity in self._replays:
                replay = self._replays[identity]
                if replay.request_sha256 == request.request_sha256 and _same_request(
                    request, replay.request
                ):
                    return replay.authorization
                return build_recorded_reviewer_authorization(
                    request=request,
                    grant=replay.authorization.grant,
                    permission_scope=replay.authorization.permission_scope,
                    actor=replay.authorization.actor,
                    reviewer=replay.authorization.reviewer,
                )
            if self._index >= len(self._scripts):
                fail_review_assignment_operation(
                    ReviewAssignmentOperationFailureCode.NOT_AUTHORIZED
                )
            step = self._scripts[self._index]
            if not _same_request(request, _step_request(step)):
                fail_review_assignment_operation(
                    ReviewAssignmentOperationFailureCode.NOT_AUTHORIZED
                )
            return _step_authorization(step)

    def exchange(
        self,
        authorization: RecordedReviewerAuthorizationV1,
        request: ReviewAssignmentRequest,
    ) -> ReviewAssignmentResult:
        with self._lock:
            if type(authorization) is not RecordedReviewerAuthorizationV1 or type(
                request
            ) not in {
                ListReviewAssignmentsRequest,
                CreateReviewAssignmentRequest,
                UpdateReviewAssignmentRequest,
            }:
                fail_review_assignment_operation(
                    ReviewAssignmentOperationFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                )
            request.require_valid()
            identity = _idempotency_identity(request)
            if identity is not None and identity in self._replays:
                replay = self._replays[identity]
                if replay.request_sha256 != request.request_sha256:
                    fail_review_assignment_operation(
                        ReviewAssignmentOperationFailureCode.IDEMPOTENCY_MISMATCH
                    )
                if authorization is not replay.authorization or not _same_request(
                    request, replay.request
                ):
                    fail_review_assignment_operation(
                        ReviewAssignmentOperationFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                    )
                replay.result.require_valid()
                if replay.result.canonical_bytes() != replay.canonical_bytes:
                    fail_review_assignment_operation(
                        ReviewAssignmentOperationFailureCode.OUTCOME_MISMATCH
                    )
                return replay.result

            if self._index >= len(self._scripts):
                fail_review_assignment_operation(
                    ReviewAssignmentOperationFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                )
            step = self._scripts[self._index]
            if not _same_request(request, _step_request(step)):
                fail_review_assignment_operation(
                    ReviewAssignmentOperationFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                )
            expected_authorization = _step_authorization(step)
            if not _authorization_matches(authorization, expected_authorization):
                fail_review_assignment_operation(
                    ReviewAssignmentOperationFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                )
            result = _build_result(step=step, authorization=authorization)
            result.require_valid()
            canonical = result.canonical_bytes()
            if identity is not None:
                if type(result) not in {
                    CreateReviewAssignmentResult,
                    UpdateReviewAssignmentResult,
                }:
                    fail_review_assignment_operation(
                        ReviewAssignmentOperationFailureCode.OUTCOME_MISMATCH
                    )
                if type(request) not in {
                    CreateReviewAssignmentRequest,
                    UpdateReviewAssignmentRequest,
                }:
                    fail_review_assignment_operation(
                        ReviewAssignmentOperationFailureCode.OUTCOME_MISMATCH
                    )
                self._replays[identity] = _ReplayEntry(
                    request=cast(
                        CreateReviewAssignmentRequest | UpdateReviewAssignmentRequest,
                        request,
                    ),
                    request_sha256=request.request_sha256,
                    authorization=authorization,
                    result=cast(
                        CreateReviewAssignmentResult | UpdateReviewAssignmentResult,
                        result,
                    ),
                    canonical_bytes=canonical,
                )
            self._index += 1
            return result


__all__ = [
    "RecordedCreateReviewAssignmentStep",
    "RecordedListReviewAssignmentsStep",
    "RecordedReviewAssignmentAdapter",
    "RecordedReviewAssignmentStep",
    "RecordedUpdateReviewAssignmentStep",
]

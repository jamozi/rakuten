"""Validate one ST-0901 PR2 recorded-local review-assignment exchange.

The public service accepts only a request.  Its authorization source constructs
the sole hash-bound recorded identity/grant record before the exchange is
consulted.  This is deterministic ENV-DEV/CI self-consistency, not real
authentication, canonical authorization policy, persistence, or audit proof.
"""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.publishing.review_assignment_operations import (
    CreateReviewAssignmentRequest,
    CreateReviewAssignmentResult,
    ListReviewAssignmentsRequest,
    ListReviewAssignmentsResult,
    RecordedIdentityProjection,
    RecordedIdempotencyReceiptV1,
    RecordedReviewerAuthorizationV1,
    RecordedSubjectKind,
    RecordedSubjectStatus,
    ReviewAssignmentOperation,
    ReviewAssignmentOperationFailureCode,
    ReviewAssignmentRequest,
    ReviewAssignmentResult,
    UpdateReviewAssignmentRequest,
    UpdateReviewAssignmentResult,
    fail_review_assignment_operation,
    recorded_mutation_output_sha256,
)
from raos.domain.publishing.review_workflow import (
    ReviewAssignment,
    create_review_assignment,
    transition_review_assignment,
)
from raos.ports.review_assignment import (
    RecordedReviewerAuthorizationSource,
    ReviewAssignmentExchange,
)


# These action and permission pairs are fixture bindings under
# ST0901_PR2_RECORDED_LOCAL_V1.  Equality here does not establish a canonical
# operation-to-resource policy or real authorization.
_RECORDED_LOCAL_ACTION_BY_OPERATION = {
    ReviewAssignmentOperation.LIST: "publishing:review:read",
    ReviewAssignmentOperation.CREATE: "publishing:review:assign",
    ReviewAssignmentOperation.UPDATE: "publishing:review:assign",
}
_RECORDED_LOCAL_PERMISSION_BY_OPERATION = {
    ReviewAssignmentOperation.LIST: "publishing:review:read",
    ReviewAssignmentOperation.CREATE: "publishing:review:assign",
    ReviewAssignmentOperation.UPDATE: "publishing:review:assign",
}
_EXPECTED_RESULT: dict[type[object], type[object]] = {
    ListReviewAssignmentsRequest: ListReviewAssignmentsResult,
    CreateReviewAssignmentRequest: CreateReviewAssignmentResult,
    UpdateReviewAssignmentRequest: UpdateReviewAssignmentResult,
}


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except TypeError:
        return False


def _request(value: object) -> ReviewAssignmentRequest:
    if type(value) not in _EXPECTED_RESULT:
        fail_review_assignment_operation()
    typed = cast(ReviewAssignmentRequest, value)
    failed = False
    try:
        typed.require_valid()
    except Exception:
        failed = True
    if failed:
        fail_review_assignment_operation()
    return typed


def _identity_is_active_human(value: object) -> bool:
    if type(value) is not RecordedIdentityProjection:
        return False
    try:
        value.require_valid()
    except Exception:
        return False
    return (
        value.subject_kind is RecordedSubjectKind.HUMAN
        and value.subject_status is RecordedSubjectStatus.ACTIVE
    )


def _authorization_matches_request(
    authorization: object,
    request: ReviewAssignmentRequest,
) -> bool:
    if type(authorization) is not RecordedReviewerAuthorizationV1:
        return False
    try:
        authorization.require_valid()
        grant = authorization.grant
        actor = authorization.actor
        reviewer = authorization.reviewer
        operation = request.operation
        assignment_id = getattr(request, "assignment_id", None)
        article_version_id = getattr(request, "article_version_id", None)
        common_valid = (
            authorization.operation is operation
            and authorization.request_sha256 == request.request_sha256
            and authorization.correlation_id == request.correlation_id
            and authorization.target == request.target
            and authorization.assignment_id == assignment_id
            and authorization.article_version_id == article_version_id
            and grant.correlation_id == request.correlation_id
            and grant.target == request.target
            and grant.action.value == _RECORDED_LOCAL_ACTION_BY_OPERATION[operation]
            and authorization.permission_scope.value
            == _RECORDED_LOCAL_PERMISSION_BY_OPERATION[operation]
            and _identity_is_active_human(actor)
        )
        if not common_valid:
            return False
        if type(request) is ListReviewAssignmentsRequest:
            return reviewer is None and authorization.assignment_id is None
        if type(reviewer) is not RecordedIdentityProjection or not (
            _identity_is_active_human(reviewer)
        ):
            return False
        if type(request) is CreateReviewAssignmentRequest:
            return reviewer.principal_id == request.assigned_to
        return True
    except Exception:
        return False


def _list_semantics(
    request: ListReviewAssignmentsRequest,
    result: ListReviewAssignmentsResult,
) -> bool:
    if len(result.items) > request.limit:
        return False
    for snapshot in result.items:
        assignment = snapshot.assignment
        if (
            (
                request.article_version_id is not None
                and assignment.article_version_id != request.article_version_id
            )
            or (
                request.assigned_to is not None
                and assignment.assigned_to != request.assigned_to
            )
            or (request.status is not None and assignment.status is not request.status)
        ):
            return False
    # The exact result type structurally has no audit/idempotency fields.
    return not hasattr(result, "audit") and not hasattr(result, "idempotency")


def _create_semantics(
    authorization: RecordedReviewerAuthorizationV1,
    request: CreateReviewAssignmentRequest,
    result: CreateReviewAssignmentResult,
) -> bool:
    reviewer = authorization.reviewer
    if type(reviewer) is not RecordedIdentityProjection:
        return False
    expected: ReviewAssignment | None = None
    try:
        expected = create_review_assignment(
            assignment_id=request.assignment_id,
            article_version_id=request.article_version_id,
            review_type=request.review_type,
            assigned_by=authorization.actor.principal_id,
            assigned_to=reviewer.principal_id,
            priority=request.priority,
            created_at=request.created_at,
        )
    except Exception:
        return False
    expected_output_sha256 = recorded_mutation_output_sha256(
        snapshot_sha256=result.snapshot.snapshot_sha256,
        audit_sha256=result.audit.audit_sha256,
        transition_sha256=None,
    )
    expected_receipt = RecordedIdempotencyReceiptV1.recorded_local(
        operation=request.operation,
        idempotency_key=request.idempotency_key,
        request_sha256=request.request_sha256,
        recorded_output_sha256=expected_output_sha256,
    )
    return (
        result.snapshot.assignment == expected
        and reviewer.principal_id == request.assigned_to
        and result.audit.actor_id == authorization.actor.principal_id
        and result.audit.correlation_id == request.correlation_id
        and result.audit.request_sha256 == request.request_sha256
        and result.idempotency == expected_receipt
    )


def _update_semantics(
    authorization: RecordedReviewerAuthorizationV1,
    request: UpdateReviewAssignmentRequest,
    result: UpdateReviewAssignmentResult,
) -> bool:
    reviewer = authorization.reviewer
    if type(reviewer) is not RecordedIdentityProjection:
        return False
    before = result.transition.before
    prior = before.assignment
    if (
        prior.assignment_id != request.assignment_id
        or prior.article_version_id != request.article_version_id
        or prior.assigned_to != reviewer.principal_id
        or prior.lock_version != request.expected_lock_version.value
        or before.etag != request.if_match
    ):
        return False
    expected: ReviewAssignment | None = None
    try:
        expected = transition_review_assignment(
            prior,
            request.target_state,
            request.occurred_at,
            request.completion_decision_reference,
        )
    except Exception:
        return False
    expected_output_sha256 = recorded_mutation_output_sha256(
        snapshot_sha256=result.transition.after.snapshot_sha256,
        audit_sha256=result.audit.audit_sha256,
        transition_sha256=result.transition.transition_sha256,
    )
    expected_receipt = RecordedIdempotencyReceiptV1.recorded_local(
        operation=request.operation,
        idempotency_key=request.idempotency_key,
        request_sha256=request.request_sha256,
        recorded_output_sha256=expected_output_sha256,
    )
    return (
        result.transition.after.assignment == expected
        and result.audit.actor_id == authorization.actor.principal_id
        and result.audit.correlation_id == request.correlation_id
        and result.audit.request_sha256 == request.request_sha256
        and result.idempotency == expected_receipt
    )


def _result_matches(
    authorization: RecordedReviewerAuthorizationV1,
    request: ReviewAssignmentRequest,
    observed: object,
) -> bool:
    expected_type = _EXPECTED_RESULT[type(request)]
    if type(observed) is not expected_type:
        return False
    result = cast(ReviewAssignmentResult, observed)
    try:
        result.require_valid()
        first = result.canonical_bytes()
        second = result.canonical_bytes()
        if (
            result.operation is not request.operation
            or result.authorization_sha256 != authorization.authorization_sha256
            or result.request_sha256 != request.request_sha256
            or type(first) is not bytes
            or first != second
        ):
            return False
        if type(request) is ListReviewAssignmentsRequest:
            return _list_semantics(
                request,
                cast(ListReviewAssignmentsResult, result),
            )
        if type(request) is CreateReviewAssignmentRequest:
            return _create_semantics(
                authorization,
                request,
                cast(CreateReviewAssignmentResult, result),
            )
        return _update_semantics(
            authorization,
            request,
            cast(UpdateReviewAssignmentResult, result),
        )
    except Exception:
        return False


@final
class ReviewAssignmentService:
    """Authorize then exchange one request through recorded-local collaborators."""

    __slots__ = ("_authorization_source", "_exchange")
    _authorization_source: RecordedReviewerAuthorizationSource
    _exchange: ReviewAssignmentExchange

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        authorization_source: RecordedReviewerAuthorizationSource,
        exchange: ReviewAssignmentExchange,
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or not _implements(
                cast(object, authorization_source),
                RecordedReviewerAuthorizationSource,
            )
            or not _implements(cast(object, exchange), ReviewAssignmentExchange)
        ):
            fail_review_assignment_operation()
        self._authorization_source = authorization_source
        self._exchange = exchange

    def execute(self, *, request: ReviewAssignmentRequest) -> ReviewAssignmentResult:
        """Execute with no caller-supplied actor, reviewer, grant, or trust record."""

        typed_request = _request(request)
        observed_authorization: object = None
        authorization_failed = False
        try:
            observed_authorization = self._authorization_source.issue_authorization(
                typed_request
            )
        except Exception:
            authorization_failed = True
        if authorization_failed or not _authorization_matches_request(
            observed_authorization, typed_request
        ):
            fail_review_assignment_operation(
                ReviewAssignmentOperationFailureCode.NOT_AUTHORIZED
            )
        authorization = cast(RecordedReviewerAuthorizationV1, observed_authorization)

        observed_result: object = None
        exchange_failed = False
        try:
            observed_result = self._exchange.exchange(
                authorization,
                typed_request,
            )
        except Exception:
            exchange_failed = True
        if exchange_failed:
            fail_review_assignment_operation(
                ReviewAssignmentOperationFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
            )
        if not _result_matches(
            authorization,
            typed_request,
            observed_result,
        ):
            fail_review_assignment_operation(
                ReviewAssignmentOperationFailureCode.OUTCOME_MISMATCH
            )
        return cast(ReviewAssignmentResult, observed_result)


__all__ = ["ReviewAssignmentService"]

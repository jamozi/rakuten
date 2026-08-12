"""Validate one ST-0901 PR3 recorded-local review-decision append.

The public service accepts only a request. Its authorization source constructs
the sole hash-bound recorded identity/grant record before the exchange is
consulted. This is deterministic ENV-DEV/CI self-consistency, not real
authentication, canonical authorization policy, persistence, or audit proof.
"""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.publishing.review_decision_operations import (
    RecordReviewDecisionRequest,
    RecordReviewDecisionResultV1,
    RecordedIdentityProjection,
    RecordedIdempotencyReceiptV1,
    RecordedReviewDecisionAuthorizationV1,
    RecordedSubjectKind,
    RecordedSubjectStatus,
    ReviewDecisionOperation,
    ReviewDecisionOperationFailureCode,
    fail_review_decision_operation,
    recorded_decision_output_sha256,
)
from raos.domain.publishing.review_workflow import validate_review_decision
from raos.ports.review_decision import (
    RecordedReviewDecisionAuthorizationSource,
    ReviewDecisionExchange,
)


# These are implementation-local fixture equality bindings. They do not define
# a canonical operation-to-resource policy or authenticate the recorded actor.
_RECORDED_LOCAL_ACTION = "publishing:review:decide"
_RECORDED_LOCAL_PERMISSION = "publishing:review:decide"


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except TypeError:
        return False


def _request(value: object) -> RecordReviewDecisionRequest:
    if type(value) is not RecordReviewDecisionRequest:
        fail_review_decision_operation()
    typed = value
    # Do not catch this call: PR1's APPROVE and N/A stable failures must remain
    # the first visible boundary and must prevent authorization/exchange calls.
    typed.require_valid()
    return typed


def _active_human(value: object) -> bool:
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
    request: RecordReviewDecisionRequest,
) -> bool:
    if type(authorization) is not RecordedReviewDecisionAuthorizationV1:
        return False
    try:
        authorization.require_valid()
        grant = authorization.grant
        actor = authorization.actor
        assignment = request.assignment
        return (
            authorization.operation is ReviewDecisionOperation.RECORD
            and authorization.request_sha256 == request.request_sha256
            and authorization.correlation_id == request.correlation_id
            and authorization.target == request.target
            and authorization.assignment_id == assignment.assignment_id
            and authorization.article_version_id == assignment.article_version_id
            and authorization.assignment_sha256 == request.assignment_sha256
            and authorization.decision_sha256 == request.decision_sha256
            and grant.correlation_id == request.correlation_id
            and grant.target == request.target
            and grant.action.value == _RECORDED_LOCAL_ACTION
            and authorization.permission_scope.value == _RECORDED_LOCAL_PERMISSION
            and _active_human(actor)
            and actor.principal_id == assignment.assigned_to
        )
    except Exception:
        return False


def _result_matches(
    authorization: RecordedReviewDecisionAuthorizationV1,
    request: RecordReviewDecisionRequest,
    observed: object,
) -> bool:
    if type(observed) is not RecordReviewDecisionResultV1:
        return False
    result = observed
    try:
        result.require_valid()
        first = result.canonical_bytes()
        second = result.canonical_bytes()
        validated = validate_review_decision(request.assignment, request.draft)
        expected_output = recorded_decision_output_sha256(
            assignment_sha256=request.assignment_sha256,
            record_sha256=result.record.record_sha256,
            history_sha256=result.history.history_sha256,
            audit_sha256=result.audit.audit_sha256,
        )
        expected_receipt = RecordedIdempotencyReceiptV1.recorded_local(
            idempotency_key=request.idempotency_key,
            request_sha256=request.request_sha256,
            recorded_output_sha256=expected_output,
        )
        return (
            result.operation is ReviewDecisionOperation.RECORD
            and result.authorization_sha256 == authorization.authorization_sha256
            and result.request_sha256 == request.request_sha256
            and result.assignment == request.assignment
            and result.record.assignment_sha256 == request.assignment_sha256
            and result.record.decision == validated
            and result.record.decision_sha256 == request.decision_sha256
            and result.record.decided_by == authorization.actor.principal_id
            and result.record.supersedes_decision_id == request.supersedes_decision_id
            and result.audit.correlation_id == request.correlation_id
            and result.audit.authorization_sha256 == authorization.authorization_sha256
            and result.idempotency == expected_receipt
            and type(first) is bytes
            and first == second
        )
    except Exception:
        return False


@final
class ReviewDecisionService:
    """Authorize then append one negative decision through recorded collaborators."""

    __slots__ = ("_authorization_source", "_exchange")
    _authorization_source: RecordedReviewDecisionAuthorizationSource
    _exchange: ReviewDecisionExchange

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        authorization_source: RecordedReviewDecisionAuthorizationSource,
        exchange: ReviewDecisionExchange,
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or not _implements(
                cast(object, authorization_source),
                RecordedReviewDecisionAuthorizationSource,
            )
            or not _implements(cast(object, exchange), ReviewDecisionExchange)
        ):
            fail_review_decision_operation()
        self._authorization_source = authorization_source
        self._exchange = exchange

    def execute(
        self,
        *,
        request: RecordReviewDecisionRequest,
    ) -> RecordReviewDecisionResultV1:
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
            observed_authorization,
            typed_request,
        ):
            fail_review_decision_operation(
                ReviewDecisionOperationFailureCode.NOT_AUTHORIZED
            )
        authorization = cast(
            RecordedReviewDecisionAuthorizationV1,
            observed_authorization,
        )

        observed_result: object = None
        exchange_failed = False
        try:
            observed_result = self._exchange.exchange(authorization, typed_request)
        except Exception:
            exchange_failed = True
        if exchange_failed:
            fail_review_decision_operation(
                ReviewDecisionOperationFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
            )
        if not _result_matches(authorization, typed_request, observed_result):
            fail_review_decision_operation(
                ReviewDecisionOperationFailureCode.OUTCOME_MISMATCH
            )
        return cast(RecordReviewDecisionResultV1, observed_result)


__all__ = ["ReviewDecisionService"]

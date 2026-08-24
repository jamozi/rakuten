"""Authorize and complete one recorded-local ST-0901 human review."""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.publishing.review_completion_v2 import (
    ACTION,
    RecordedReviewCompletionAuthorizationV2,
    ReviewCompletionFailureCode,
    ReviewCompletionRequestV2,
    ReviewCompletionResultV2,
    complete_review_workflow_v2,
    fail_review_completion,
)
from raos.domain.publishing.review_decision_operations import (
    RecordedSubjectKind,
    RecordedSubjectStatus,
)
from raos.ports.review_completion import (
    RecordedReviewCompletionAuthorizationSource,
    ReviewCompletionExchange,
)


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except TypeError:
        return False


def _authorization_matches(
    authorization: object,
    request: ReviewCompletionRequestV2,
) -> bool:
    if type(authorization) is not RecordedReviewCompletionAuthorizationV2:
        return False
    try:
        authorization.require_valid()
        actor = authorization.actor
        return (
            authorization.request_sha256 == request.request_sha256
            and authorization.action == ACTION
            and authorization.permission == ACTION
            and actor.subject_kind is RecordedSubjectKind.HUMAN
            and actor.subject_status is RecordedSubjectStatus.ACTIVE
            and actor.principal_id == request.assignment.assigned_to
            and authorization.real_authentication_verified is False
            and authorization.durable_authorization_verified is False
            and authorization.external_authority is False
        )
    except Exception:
        return False


def _result_matches(
    *,
    request: ReviewCompletionRequestV2,
    authorization: RecordedReviewCompletionAuthorizationV2,
    observed: object,
) -> bool:
    if type(observed) is not ReviewCompletionResultV2:
        return False
    try:
        observed.require_valid()
        expected = complete_review_workflow_v2(
            request=request,
            authorization=authorization,
        )
        return (
            observed.canonical_bytes() == expected.canonical_bytes()
            and observed.result_sha256 == expected.result_sha256
        )
    except Exception:
        return False


@final
class ReviewCompletionService:
    """Execute with no caller-supplied actor or authority context."""

    __slots__ = ("_authorization_source", "_exchange")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        authorization_source: RecordedReviewCompletionAuthorizationSource,
        exchange: ReviewCompletionExchange,
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or not _implements(
                cast(object, authorization_source),
                RecordedReviewCompletionAuthorizationSource,
            )
            or not _implements(cast(object, exchange), ReviewCompletionExchange)
        ):
            fail_review_completion(
                ReviewCompletionFailureCode.LOCAL_ENVIRONMENT_REQUIRED
            )
        self._authorization_source = authorization_source
        self._exchange = exchange

    def execute(
        self,
        *,
        request: ReviewCompletionRequestV2,
    ) -> ReviewCompletionResultV2:
        if type(request) is not ReviewCompletionRequestV2:
            fail_review_completion()
        request.require_valid()
        authorization: object = None
        try:
            authorization = self._authorization_source.issue_authorization(request)
        except Exception:
            fail_review_completion(ReviewCompletionFailureCode.AUTHORIZATION_INVALID)
        if not _authorization_matches(authorization, request):
            fail_review_completion(ReviewCompletionFailureCode.AUTHORIZATION_INVALID)
        trusted = authorization
        observed: object = None
        try:
            observed = self._exchange.exchange(trusted, request)
        except Exception:
            fail_review_completion(
                ReviewCompletionFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
            )
        if not _result_matches(
            request=request,
            authorization=trusted,
            observed=observed,
        ):
            fail_review_completion(ReviewCompletionFailureCode.OUTCOME_MISMATCH)
        return observed


__all__ = ("ReviewCompletionService",)

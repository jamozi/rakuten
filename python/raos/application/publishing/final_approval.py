"""ENV-DEV/CI-only ST-0902 final-approval application service."""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.publishing.final_approval import (
    FinalApprovalFailureCode,
    FinalApprovalRequestV2,
    FinalApprovalResultV2,
    RecordedFinalApprovalAuthorizationV2,
    fail_final_approval,
    grant_final_approval_v2,
)
from raos.ports.final_approval import (
    FinalApprovalExchange,
    RecordedFinalApprovalAuthorizationSource,
)


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except Exception:
        return False


def _authorization_matches(
    observed: object,
    request: FinalApprovalRequestV2,
) -> bool:
    try:
        if type(observed) is not RecordedFinalApprovalAuthorizationV2:
            return False
        observed.require_valid()
        if observed.request_sha256 != request.request_sha256:
            return False
        expected = grant_final_approval_v2(
            request=request,
            authorization=observed,
        )
        expected.require_valid()
        return True
    except Exception:
        return False


def _result_matches(
    *,
    request: FinalApprovalRequestV2,
    authorization: RecordedFinalApprovalAuthorizationV2,
    observed: object,
) -> bool:
    try:
        if type(observed) is not FinalApprovalResultV2:
            return False
        observed.require_valid()
        expected = grant_final_approval_v2(
            request=request,
            authorization=authorization,
        )
        return observed.canonical_bytes() == expected.canonical_bytes()
    except Exception:
        return False


@final
class FinalApprovalService:
    """Execute without a caller-supplied actor, role, MFA, or step-up state."""

    __slots__ = ("_authorization_source", "_exchange")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        authorization_source: RecordedFinalApprovalAuthorizationSource,
        exchange: FinalApprovalExchange,
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or not _implements(
                cast(object, authorization_source),
                RecordedFinalApprovalAuthorizationSource,
            )
            or not _implements(cast(object, exchange), FinalApprovalExchange)
        ):
            fail_final_approval(FinalApprovalFailureCode.LOCAL_ENVIRONMENT_REQUIRED)
        self._authorization_source = authorization_source
        self._exchange = exchange

    def execute(self, *, request: FinalApprovalRequestV2) -> FinalApprovalResultV2:
        if type(request) is not FinalApprovalRequestV2:
            fail_final_approval()
        request.require_valid()
        authorization: object = None
        try:
            authorization = self._authorization_source.issue_authorization(request)
        except Exception:
            fail_final_approval(FinalApprovalFailureCode.AUTHORIZATION_INVALID)
        if not _authorization_matches(authorization, request):
            fail_final_approval(FinalApprovalFailureCode.AUTHORIZATION_INVALID)
        trusted = authorization
        observed: object = None
        try:
            observed = self._exchange.exchange(trusted, request)
        except Exception:
            fail_final_approval(FinalApprovalFailureCode.LOCAL_EXCHANGE_UNAVAILABLE)
        if not _result_matches(
            request=request,
            authorization=trusted,
            observed=observed,
        ):
            fail_final_approval(FinalApprovalFailureCode.OUTCOME_MISMATCH)
        return observed


__all__ = ("FinalApprovalService",)

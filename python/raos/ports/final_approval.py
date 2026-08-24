"""Provider-neutral ports for the ST-0902 recorded final-approval boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.publishing.final_approval import (
    FinalApprovalRequestV2,
    FinalApprovalResultV2,
    RecordedFinalApprovalAuthorizationV2,
)


@runtime_checkable
class RecordedFinalApprovalAuthorizationSource(Protocol):
    def issue_authorization(
        self,
        request: FinalApprovalRequestV2,
    ) -> RecordedFinalApprovalAuthorizationV2: ...


@runtime_checkable
class FinalApprovalExchange(Protocol):
    def exchange(
        self,
        authorization: RecordedFinalApprovalAuthorizationV2,
        request: FinalApprovalRequestV2,
    ) -> FinalApprovalResultV2: ...


__all__ = (
    "FinalApprovalExchange",
    "RecordedFinalApprovalAuthorizationSource",
)

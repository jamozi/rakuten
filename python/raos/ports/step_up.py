"""Inward factor-neutral source port for verified step-up assurance."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from raos.domain.iam.authentication import Session
from raos.domain.iam.step_up import (
    BoundStepUpGrant,
    BoundStepUpGrantId,
    StepUpBinding,
    StepUpAuditRecord,
    StepUpChallenge,
    StepUpChallengeId,
    StepUpCommandId,
    StepUpCommandResult,
    StepUpGrant,
    StepUpVerificationOutcome,
    StepUpVerificationReceipt,
    StepUpVerificationReceiptId,
)


@runtime_checkable
class StepUpVerifier(Protocol):
    """Return normalized assurance without exposing provider or factor types."""

    def verify(
        self, *, session: Session, now: datetime
    ) -> StepUpGrant | StepUpVerificationOutcome | None:
        """Return a grant, explicit rejection, or absence for one session."""

        ...


@runtime_checkable
class StepUpEntropySource(Protocol):
    """Return cryptographically strong bytes without exposing their source."""

    def token_bytes(self, size: int) -> bytes: ...


@runtime_checkable
class StepUpChallengeVerifier(Protocol):
    """Factor-neutral verifier used after one recorded challenge is loaded."""

    @property
    def external_action_count(self) -> int:
        """Return the exact recorded count; the local boundary requires zero."""

        ...

    def verify(
        self,
        *,
        challenge: StepUpChallenge,
        receipt_id: StepUpVerificationReceiptId,
        now: datetime,
        expires_at: datetime,
    ) -> StepUpVerificationReceipt: ...


@runtime_checkable
class StepUpLifecycleRepository(Protocol):
    """Atomic lifecycle and append-only audit port for critical step-up."""

    def create_challenge(
        self, *, command_id: StepUpCommandId, challenge: StepUpChallenge
    ) -> StepUpCommandResult: ...

    def load_challenge(self, challenge_id: StepUpChallengeId) -> StepUpChallenge: ...

    def record_verification(
        self,
        *,
        command_id: StepUpCommandId,
        verification: StepUpVerificationReceipt,
        now: datetime,
    ) -> StepUpCommandResult: ...

    def load_verification(
        self, receipt_id: StepUpVerificationReceiptId
    ) -> StepUpVerificationReceipt: ...

    def issue_grant(
        self,
        *,
        command_id: StepUpCommandId,
        grant: BoundStepUpGrant,
        now: datetime,
    ) -> StepUpCommandResult: ...

    def load_grant(self, grant_id: BoundStepUpGrantId) -> BoundStepUpGrant: ...

    def consume_grant(
        self,
        *,
        command_id: StepUpCommandId,
        grant_id: BoundStepUpGrantId,
        expected_binding: StepUpBinding,
        now: datetime,
    ) -> StepUpCommandResult: ...

    def revoke_grant(
        self,
        *,
        command_id: StepUpCommandId,
        grant_id: BoundStepUpGrantId,
        expected_binding: StepUpBinding,
        now: datetime,
    ) -> StepUpCommandResult: ...

    def recover(self, command_id: StepUpCommandId) -> StepUpCommandResult: ...

    def audit_snapshot(self) -> tuple[StepUpAuditRecord, ...]: ...


__all__ = [
    "StepUpChallengeVerifier",
    "StepUpEntropySource",
    "StepUpLifecycleRepository",
    "StepUpVerifier",
]

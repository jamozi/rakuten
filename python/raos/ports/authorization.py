"""Inward authorization policy, entitlement, and decision recording ports."""

from __future__ import annotations

from datetime import datetime
from typing import NoReturn, Protocol, runtime_checkable
from uuid import UUID

from raos.domain.iam.authentication import SessionId
from raos.domain.iam.authorization import (
    AuthorizationAuditRecord,
    AuthorizationCommandId,
    AuthorizationCommandResult,
    AuthorizationDecision,
    EntitlementSnapshot,
    IndependentActorEvidence,
    PolicySnapshot,
    PrincipalIdentity,
    ServicePrincipalAuthorizationStatus,
)
from raos.domain.iam.step_up import (
    BoundStepUpGrantId,
    CriticalStepUpAction,
    StepUpCommandId,
    StepUpCommandResult,
    StepUpResourceType,
)


@runtime_checkable
class AuthorizationPolicySource(Protocol):
    """Load one complete immutable authorization policy snapshot."""

    def load(self) -> PolicySnapshot:
        """Return the current snapshot without caller-controlled policy input."""

        ...


@runtime_checkable
class EntitlementSource(Protocol):
    """Resolve trusted server-side entitlements for one normalized identity."""

    def resolve(self, principal: PrincipalIdentity) -> EntitlementSnapshot:
        """Return versioned scoped roles/scopes; never parse a request or token."""

        ...


@runtime_checkable
class AuthorizationDecisionSink(Protocol):
    """Synchronously record one minimal decision before a grant is returned."""

    def record(self, decision: AuthorizationDecision) -> None:
        """Record inward decision data; this port is not durable audit evidence."""

        ...


@runtime_checkable
class AuthorizationUnitOfWork(Protocol):
    """One explicit decision transaction with immutable snapshot reads."""

    def load_command(
        self,
        *,
        command_id: AuthorizationCommandId,
        request_digest: str,
    ) -> AuthorizationCommandResult | None: ...

    def load_policy(self) -> PolicySnapshot: ...

    def load_entitlements(
        self, principal: PrincipalIdentity
    ) -> EntitlementSnapshot: ...

    def load_independent_actor_evidence(
        self, evidence_id: UUID
    ) -> IndependentActorEvidence | None: ...

    def record_decision(
        self,
        *,
        command_id: AuthorizationCommandId,
        request_digest: str,
        session_fingerprint: str,
        decision: AuthorizationDecision,
        occurred_at: datetime,
        step_up_receipt_fingerprint: str | None,
    ) -> AuthorizationCommandResult: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


@runtime_checkable
class AuthorizationRepository(Protocol):
    """Begin owner-private authorization units of work."""

    def begin(self) -> AuthorizationUnitOfWork: ...

    def recover(
        self, command_id: AuthorizationCommandId
    ) -> AuthorizationCommandResult: ...


@runtime_checkable
class RecordedAuthorizationAdministration(Protocol):
    """Recorded fixture administration; never a live policy-management API."""

    def install_policy(
        self,
        *,
        expected_revision: str,
        snapshot: PolicySnapshot,
    ) -> None: ...

    def install_entitlements(
        self,
        *,
        principal: PrincipalIdentity,
        expected_revision: str | None,
        snapshot: EntitlementSnapshot,
    ) -> None: ...

    def append_independent_actor_evidence(
        self, evidence: IndependentActorEvidence
    ) -> None: ...

    def audit_snapshot(self) -> tuple[AuthorizationAuditRecord, ...]: ...


@runtime_checkable
class SingleUseStepUpGrantConsumer(Protocol):
    """The exact ST-0402 consume/recover surface used by authorization."""

    def consume_grant(
        self,
        *,
        command_id: StepUpCommandId,
        session_id: SessionId,
        grant_id: BoundStepUpGrantId,
        action: CriticalStepUpAction,
        resource_type: StepUpResourceType,
        resource_id: UUID,
        now: datetime,
    ) -> StepUpCommandResult: ...

    def recover(self, *, command_id: StepUpCommandId) -> StepUpCommandResult: ...


@runtime_checkable
class ServicePrincipalAuthorizationPort(Protocol):
    """Disabled boundary until service principals map to workload roles."""

    def status(self) -> ServicePrincipalAuthorizationStatus: ...

    def require_internal_service(self, service_name: object) -> NoReturn: ...


__all__ = [
    "AuthorizationDecisionSink",
    "AuthorizationPolicySource",
    "AuthorizationRepository",
    "AuthorizationUnitOfWork",
    "EntitlementSource",
    "RecordedAuthorizationAdministration",
    "ServicePrincipalAuthorizationPort",
    "SingleUseStepUpGrantConsumer",
]

"""Inward authorization policy, entitlement, and decision recording ports."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.iam.authorization import (
    AuthorizationDecision,
    EntitlementSnapshot,
    PolicySnapshot,
    PrincipalIdentity,
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


__all__ = [
    "AuthorizationDecisionSink",
    "AuthorizationPolicySource",
    "EntitlementSource",
]

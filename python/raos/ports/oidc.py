"""Inward authentication ports with no provider SDK or delivery types."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from raos.domain.iam.authentication import (
    AuthorizationCallback,
    AuthorizationTransaction,
    OidcNonce,
    PkceVerifier,
    PrincipalIdentity,
    Session,
    SessionId,
)


@runtime_checkable
class EntropySource(Protocol):
    """Supply cryptographic bytes without exposing a global RNG to the domain."""

    def token_bytes(self, size: int) -> bytes:
        """Return exactly ``size`` bytes from a security-grade source."""

        ...


@runtime_checkable
class OidcProvider(Protocol):
    """Exchange an Authorization Code without leaking provider-specific values."""

    def exchange(
        self,
        *,
        callback: AuthorizationCallback,
        verifier: PkceVerifier,
        expected_nonce: OidcNonce,
        now: datetime,
    ) -> PrincipalIdentity:
        """Validate code, state binding, nonce, PKCE, expiry, and one-time use."""

        ...


@runtime_checkable
class AuthenticationRepository(Protocol):
    """Atomic persistence boundary for authorization and session lifecycle."""

    def add_authorization(self, transaction: AuthorizationTransaction) -> None:
        """Store one pending authorization transaction without replacement."""

        ...

    def consume_authorization(
        self, *, state_fingerprint: str, now: datetime
    ) -> AuthorizationTransaction:
        """Atomically consume exactly one unexpired transaction."""

        ...

    def create_session(self, session: Session) -> None:
        """Create one session without overwriting an existing identifier."""

        ...

    def load_session(self, session_id: SessionId) -> Session:
        """Load one session or fail closed."""

        ...

    def replace_session(self, *, expected: Session, replacement: Session) -> None:
        """Compare-and-set one session record."""

        ...

    def rotate_session(
        self,
        *,
        expected: Session,
        revoked_predecessor: Session,
        successor: Session,
    ) -> None:
        """Atomically revoke a predecessor and create its successor."""

        ...


__all__ = [
    "AuthenticationRepository",
    "EntropySource",
    "OidcProvider",
]

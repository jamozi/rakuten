"""Development-only deterministic OIDC fake and in-memory auth storage."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
import hashlib
import hmac
import re
import secrets
from threading import Lock
from typing import NoReturn, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authentication import (
    AuthenticationFailure,
    AuthenticationFailureCode,
    AuthorizationCallback,
    AuthorizationCode,
    AuthorizationRequest,
    AuthorizationTransaction,
    OidcNonce,
    PkceMethod,
    PkceVerifier,
    PrincipalIdentity,
    Session,
    SessionId,
    require_utc,
)


_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_MIN_CODE_LIFETIME = timedelta(seconds=15)
_MAX_CODE_LIFETIME = timedelta(minutes=5)
_CODE_DOMAIN_SEPARATOR = b"raos-st0401-development-code-v1\x00"


def _raise(code: AuthenticationFailureCode) -> NoReturn:
    raise AuthenticationFailure(code) from None


def _require_development(environment: object) -> RuntimeEnvironment:
    if (
        type(environment) is not RuntimeEnvironment
        or environment is not RuntimeEnvironment.ENV_DEV
    ):
        _raise(AuthenticationFailureCode.DEVELOPMENT_ONLY)
    return environment


@dataclass(frozen=True, slots=True, repr=False)
class _IssuedAuthorization:
    state_fingerprint: str = field(repr=False)
    nonce: OidcNonce = field(repr=False)
    challenge: str = field(repr=False)
    issued_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = field(default=None, repr=False)


@final
class SystemEntropySource:
    """Security-grade process entropy for OAuth and session identifiers."""

    def token_bytes(self, size: int) -> bytes:
        if type(size) is not int or size != 32:
            _raise(AuthenticationFailureCode.ENTROPY_FAILURE)
        return secrets.token_bytes(size)


@final
class DevelopmentOidcAdapter:
    """No-network fake that can exist only for exact ``ENV-DEV`` configuration.

    The fake has no password API. ``authorize`` deterministically issues a code
    from the request's already-high-entropy correlation values, while
    ``exchange`` enforces one-time use, state, nonce, PKCE S256, and expiry.
    """

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        principal: PrincipalIdentity,
        code_lifetime: timedelta = timedelta(minutes=2),
    ) -> None:
        self._environment = _require_development(environment)
        if type(principal) is not PrincipalIdentity:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        if (
            type(code_lifetime) is not timedelta
            or not _MIN_CODE_LIFETIME <= code_lifetime <= _MAX_CODE_LIFETIME
        ):
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        self._principal = principal
        self._code_lifetime = code_lifetime
        self._issued: dict[str, _IssuedAuthorization] = {}
        self._lock = Lock()

    def authorize(
        self, *, request: AuthorizationRequest, now: datetime
    ) -> AuthorizationCallback:
        """Simulate the provider interaction without network or local password."""

        self._guard()
        if (
            type(request) is not AuthorizationRequest
            or type(request.pkce_method) is not PkceMethod
            or request.pkce_method is not PkceMethod.S256
        ):
            _raise(AuthenticationFailureCode.PKCE_UNSUPPORTED)
        observed_at = require_utc(now)
        if observed_at < request.created_at:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        if observed_at >= request.expires_at:
            _raise(AuthenticationFailureCode.AUTHORIZATION_EXPIRED)
        code_digest = hashlib.sha256(
            _CODE_DOMAIN_SEPARATOR
            + request.state.reveal().encode("ascii")
            + b"\x00"
            + request.nonce.reveal().encode("ascii")
            + b"\x00"
            + request.pkce_challenge.reveal().encode("ascii")
        ).digest()
        code = AuthorizationCode.from_bytes(code_digest)
        issued = _IssuedAuthorization(
            state_fingerprint=request.state.fingerprint(),
            nonce=request.nonce,
            challenge=request.pkce_challenge.reveal(),
            issued_at=observed_at,
            expires_at=min(
                request.expires_at,
                observed_at + self._code_lifetime,
            ),
        )
        key = code.fingerprint()
        with self._lock:
            existing = self._issued.get(key)
            if existing is None:
                self._issued[key] = issued
            elif existing != issued:
                _raise(AuthenticationFailureCode.AUTHORIZATION_COLLISION)
        return AuthorizationCallback(state=request.state, code=code)

    def exchange(
        self,
        *,
        callback: AuthorizationCallback,
        verifier: PkceVerifier,
        expected_nonce: OidcNonce,
        now: datetime,
    ) -> PrincipalIdentity:
        """Perform a strict, single-use local code exchange without I/O."""

        self._guard()
        if (
            type(callback) is not AuthorizationCallback
            or type(verifier) is not PkceVerifier
            or type(expected_nonce) is not OidcNonce
        ):
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        observed_at = require_utc(now)
        key = callback.code.fingerprint()
        with self._lock:
            issued = self._issued.get(key)
            if issued is None:
                _raise(AuthenticationFailureCode.CODE_UNKNOWN)
            if issued.consumed_at is not None:
                _raise(AuthenticationFailureCode.CODE_REPLAY)
            consumed = replace(issued, consumed_at=observed_at)
            self._issued[key] = consumed
        if observed_at < issued.issued_at:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        if observed_at >= issued.expires_at:
            _raise(AuthenticationFailureCode.CODE_EXPIRED)
        if not hmac.compare_digest(
            callback.state.fingerprint(), issued.state_fingerprint
        ):
            _raise(AuthenticationFailureCode.STATE_MISMATCH)
        if not hmac.compare_digest(
            verifier.s256_challenge().reveal(), issued.challenge
        ):
            _raise(AuthenticationFailureCode.PKCE_MISMATCH)
        if not hmac.compare_digest(expected_nonce.reveal(), issued.nonce.reveal()):
            _raise(AuthenticationFailureCode.NONCE_MISMATCH)
        return self._principal

    def _guard(self) -> None:
        _require_development(self._environment)

    def __repr__(self) -> str:
        return "DevelopmentOidcAdapter(environment='ENV-DEV', state=<redacted>)"


@final
class InMemoryAuthenticationRepository:
    """Thread-safe ephemeral auth state, guarded for exact development only."""

    def __init__(self, *, environment: RuntimeEnvironment) -> None:
        self._environment = _require_development(environment)
        self._authorizations: dict[str, AuthorizationTransaction] = {}
        self._sessions: dict[str, Session] = {}
        self._lock = Lock()

    def add_authorization(self, transaction: AuthorizationTransaction) -> None:
        self._guard()
        if (
            type(transaction) is not AuthorizationTransaction
            or transaction.consumed_at is not None
        ):
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        with self._lock:
            if transaction.state_fingerprint in self._authorizations:
                _raise(AuthenticationFailureCode.AUTHORIZATION_COLLISION)
            self._authorizations[transaction.state_fingerprint] = transaction

    def consume_authorization(
        self, *, state_fingerprint: str, now: datetime
    ) -> AuthorizationTransaction:
        self._guard()
        if (
            type(state_fingerprint) is not str
            or _FINGERPRINT.fullmatch(state_fingerprint) is None
        ):
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        observed_at = require_utc(now)
        with self._lock:
            transaction = self._authorizations.get(state_fingerprint)
            if transaction is None:
                _raise(AuthenticationFailureCode.AUTHORIZATION_UNKNOWN)
            if transaction.consumed_at is not None:
                _raise(AuthenticationFailureCode.AUTHORIZATION_REPLAY)
            consumed = replace(transaction, consumed_at=observed_at)
            self._authorizations[state_fingerprint] = consumed
        if observed_at < transaction.created_at:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        if observed_at >= transaction.expires_at:
            _raise(AuthenticationFailureCode.AUTHORIZATION_EXPIRED)
        return consumed

    def create_session(self, session: Session) -> None:
        self._guard()
        if type(session) is not Session:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        key = session.session_id.fingerprint()
        with self._lock:
            if key in self._sessions:
                _raise(AuthenticationFailureCode.SESSION_COLLISION)
            self._sessions[key] = session

    def load_session(self, session_id: SessionId) -> Session:
        self._guard()
        if type(session_id) is not SessionId:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        with self._lock:
            session = self._sessions.get(session_id.fingerprint())
            if session is None:
                _raise(AuthenticationFailureCode.SESSION_UNKNOWN)
            return session

    def replace_session(self, *, expected: Session, replacement: Session) -> None:
        self._guard()
        if type(expected) is not Session or type(replacement) is not Session:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        if replacement.session_id != expected.session_id:
            _raise(AuthenticationFailureCode.SESSION_CONFLICT)
        key = expected.session_id.fingerprint()
        with self._lock:
            if self._sessions.get(key) != expected:
                _raise(AuthenticationFailureCode.SESSION_CONFLICT)
            self._sessions[key] = replacement

    def rotate_session(
        self,
        *,
        expected: Session,
        revoked_predecessor: Session,
        successor: Session,
    ) -> None:
        self._guard()
        if (
            type(expected) is not Session
            or type(revoked_predecessor) is not Session
            or type(successor) is not Session
            or revoked_predecessor.session_id != expected.session_id
            or revoked_predecessor.revoked_at is None
            or successor.rotated_from != expected.session_id
        ):
            _raise(AuthenticationFailureCode.SESSION_CONFLICT)
        old_key = expected.session_id.fingerprint()
        new_key = successor.session_id.fingerprint()
        with self._lock:
            if self._sessions.get(old_key) != expected or new_key in self._sessions:
                _raise(AuthenticationFailureCode.SESSION_CONFLICT)
            self._sessions[old_key] = revoked_predecessor
            self._sessions[new_key] = successor

    def _guard(self) -> None:
        _require_development(self._environment)

    def __repr__(self) -> str:
        return (
            "InMemoryAuthenticationRepository(environment='ENV-DEV', state=<redacted>)"
        )


__all__ = [
    "DevelopmentOidcAdapter",
    "InMemoryAuthenticationRepository",
    "SystemEntropySource",
]

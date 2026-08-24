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
    AuthorizationState,
    AuthorizationTransaction,
    OidcNonce,
    PkceMethod,
    PkceVerifier,
    PrincipalIdentity,
    Session,
    SessionId,
    require_utc,
    snapshot_authorization_callback,
    snapshot_authorization_request,
    snapshot_authorization_transaction,
    snapshot_principal_identity,
    snapshot_session,
    snapshot_session_id,
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
        try:
            detached_principal = snapshot_principal_identity(principal)
        except Exception:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        if (
            type(code_lifetime) is not timedelta
            or not _MIN_CODE_LIFETIME <= code_lifetime <= _MAX_CODE_LIFETIME
        ):
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        self._principal = detached_principal
        self._code_lifetime = code_lifetime
        self._issued: dict[str, _IssuedAuthorization] = {}
        self._lock = Lock()

    def authorize(
        self, *, request: AuthorizationRequest, now: datetime
    ) -> AuthorizationCallback:
        """Simulate the provider interaction without network or local password."""

        self._guard()
        try:
            received_request = snapshot_authorization_request(request)
        except Exception:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        if (
            type(received_request.pkce_method) is not PkceMethod
            or received_request.pkce_method is not PkceMethod.S256
        ):
            _raise(AuthenticationFailureCode.PKCE_UNSUPPORTED)
        observed_at = require_utc(now)
        if observed_at < received_request.created_at:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        if observed_at >= received_request.expires_at:
            _raise(AuthenticationFailureCode.AUTHORIZATION_EXPIRED)
        code_digest = hashlib.sha256(
            _CODE_DOMAIN_SEPARATOR
            + received_request.state.reveal().encode("ascii")
            + b"\x00"
            + received_request.nonce.reveal().encode("ascii")
            + b"\x00"
            + received_request.pkce_challenge.reveal().encode("ascii")
        ).digest()
        code = AuthorizationCode.from_bytes(code_digest)
        issued = _IssuedAuthorization(
            state_fingerprint=received_request.state.fingerprint(),
            nonce=OidcNonce(received_request.nonce.reveal()),
            challenge=received_request.pkce_challenge.reveal(),
            issued_at=observed_at,
            expires_at=min(
                received_request.expires_at,
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
        return AuthorizationCallback(
            state=AuthorizationState(received_request.state.reveal()),
            code=code,
        )

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
        try:
            received_callback = snapshot_authorization_callback(callback)
            received_verifier = PkceVerifier(verifier.reveal())
            received_nonce = OidcNonce(expected_nonce.reveal())
        except Exception:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        observed_at = require_utc(now)
        key = received_callback.code.fingerprint()
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
            received_callback.state.fingerprint(), issued.state_fingerprint
        ):
            _raise(AuthenticationFailureCode.STATE_MISMATCH)
        if not hmac.compare_digest(
            received_verifier.s256_challenge().reveal(), issued.challenge
        ):
            _raise(AuthenticationFailureCode.PKCE_MISMATCH)
        if not hmac.compare_digest(received_nonce.reveal(), issued.nonce.reveal()):
            _raise(AuthenticationFailureCode.NONCE_MISMATCH)
        return snapshot_principal_identity(self._principal)

    @property
    def external_action_count(self) -> int:
        """Recorded fake performs no external action."""

        return 0

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
        try:
            received = snapshot_authorization_transaction(transaction)
        except Exception:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        if received.consumed_at is not None:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        with self._lock:
            if received.state_fingerprint in self._authorizations:
                _raise(AuthenticationFailureCode.AUTHORIZATION_COLLISION)
            self._authorizations[received.state_fingerprint] = received

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
        return snapshot_authorization_transaction(consumed)

    def create_session(self, session: Session) -> None:
        self._guard()
        try:
            received = snapshot_session(session)
        except Exception:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        key = received.session_id.fingerprint()
        with self._lock:
            if key in self._sessions:
                _raise(AuthenticationFailureCode.SESSION_COLLISION)
            self._sessions[key] = received

    def load_session(self, session_id: SessionId) -> Session:
        self._guard()
        try:
            received_id = snapshot_session_id(session_id)
        except Exception:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        with self._lock:
            session = self._sessions.get(received_id.fingerprint())
            if session is None:
                _raise(AuthenticationFailureCode.SESSION_UNKNOWN)
            return snapshot_session(session)

    def replace_session(self, *, expected: Session, replacement: Session) -> None:
        self._guard()
        try:
            received_expected = snapshot_session(expected)
            received_replacement = snapshot_session(replacement)
        except Exception:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        if received_replacement.session_id != received_expected.session_id:
            _raise(AuthenticationFailureCode.SESSION_CONFLICT)
        key = received_expected.session_id.fingerprint()
        with self._lock:
            if self._sessions.get(key) != received_expected:
                _raise(AuthenticationFailureCode.SESSION_CONFLICT)
            self._sessions[key] = received_replacement

    def rotate_session(
        self,
        *,
        expected: Session,
        revoked_predecessor: Session,
        successor: Session,
    ) -> None:
        self._guard()
        try:
            received_expected = snapshot_session(expected)
            received_revoked = snapshot_session(revoked_predecessor)
            received_successor = snapshot_session(successor)
        except Exception:
            _raise(AuthenticationFailureCode.SESSION_CONFLICT)
        if (
            received_revoked.session_id != received_expected.session_id
            or received_revoked.revoked_at is None
            or received_successor.rotated_from != received_expected.session_id
        ):
            _raise(AuthenticationFailureCode.SESSION_CONFLICT)
        old_key = received_expected.session_id.fingerprint()
        new_key = received_successor.session_id.fingerprint()
        with self._lock:
            if (
                self._sessions.get(old_key) != received_expected
                or new_key in self._sessions
            ):
                _raise(AuthenticationFailureCode.SESSION_CONFLICT)
            self._sessions[old_key] = received_revoked
            self._sessions[new_key] = received_successor

    def recover_session_rotation(self, predecessor_id: SessionId) -> Session:
        self._guard()
        try:
            received_id = snapshot_session_id(predecessor_id)
        except Exception:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        predecessor_key = received_id.fingerprint()
        with self._lock:
            predecessor = self._sessions.get(predecessor_key)
            if predecessor is None:
                _raise(AuthenticationFailureCode.SESSION_UNKNOWN)
            successors = tuple(
                session
                for session in self._sessions.values()
                if session.rotated_from == received_id
            )
            if not successors:
                if predecessor.revoked_at is not None:
                    _raise(AuthenticationFailureCode.STORAGE_FAILURE)
                return snapshot_session(predecessor)
            if len(successors) != 1 or predecessor.revoked_at is None:
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            return snapshot_session(successors[0])

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

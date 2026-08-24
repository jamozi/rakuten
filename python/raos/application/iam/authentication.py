"""Transport-neutral OIDC authorization and application session lifecycle."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Callable, NoReturn, TypeVar, cast

from raos.domain.iam.authentication import (
    AuthenticationFailure,
    AuthenticationFailureCode,
    AuthorizationCallback,
    AuthorizationRequest,
    AuthorizationState,
    AuthorizationTransaction,
    OidcNonce,
    PkceMethod,
    PkceVerifier,
    PrincipalIdentity,
    RedirectUri,
    Session,
    SessionId,
    require_utc,
    snapshot_authorization_callback,
    snapshot_authorization_transaction,
    snapshot_principal_identity,
    snapshot_session,
    snapshot_session_id,
)
from raos.ports.oidc import AuthenticationRepository, EntropySource, OidcProvider


_ENTROPY_BYTES = 32
_MIN_AUTHORIZATION_LIFETIME = timedelta(seconds=30)
_MAX_AUTHORIZATION_LIFETIME = timedelta(minutes=10)
_MIN_IDLE_LIFETIME = timedelta(minutes=1)
_MAX_IDLE_LIFETIME = timedelta(hours=2)
_MAX_ABSOLUTE_LIFETIME = timedelta(hours=12)
_T = TypeVar("_T")


def _raise(code: AuthenticationFailureCode) -> NoReturn:
    raise AuthenticationFailure(code) from None


def _failure_code(
    error: AuthenticationFailure, fallback: AuthenticationFailureCode
) -> AuthenticationFailureCode:
    if (
        type(error) is AuthenticationFailure
        and type(error.code) is AuthenticationFailureCode
    ):
        return error.code
    return fallback


def _snapshot(operation: Callable[[], _T], failure: AuthenticationFailureCode) -> _T:
    """Detach exact values at trust boundaries without retaining diagnostics."""

    try:
        return operation()
    except Exception:
        _raise(failure)


def _require_unchanged(
    before: object,
    after: object,
    failure: AuthenticationFailureCode,
) -> None:
    try:
        unchanged = type(before) is type(after) and before == after
    except Exception:
        unchanged = False
    if not unchanged:
        _raise(failure)


class AuthenticationService:
    """Orchestrate OIDC correlation and sessions without choosing HTTP transport."""

    def __init__(
        self,
        *,
        provider: OidcProvider,
        repository: AuthenticationRepository,
        entropy: EntropySource,
        authorization_lifetime: timedelta = timedelta(minutes=5),
        session_idle_lifetime: timedelta = timedelta(minutes=30),
        session_absolute_lifetime: timedelta = timedelta(hours=8),
    ) -> None:
        if not isinstance(cast(object, provider), OidcProvider):
            raise TypeError("provider must implement OidcProvider")
        if not isinstance(cast(object, repository), AuthenticationRepository):
            raise TypeError("repository must implement AuthenticationRepository")
        if not isinstance(cast(object, entropy), EntropySource):
            raise TypeError("entropy must implement EntropySource")
        if (
            type(authorization_lifetime) is not timedelta
            or not _MIN_AUTHORIZATION_LIFETIME
            <= authorization_lifetime
            <= _MAX_AUTHORIZATION_LIFETIME
            or type(session_idle_lifetime) is not timedelta
            or not _MIN_IDLE_LIFETIME <= session_idle_lifetime <= _MAX_IDLE_LIFETIME
            or type(session_absolute_lifetime) is not timedelta
            or not session_idle_lifetime
            <= session_absolute_lifetime
            <= _MAX_ABSOLUTE_LIFETIME
        ):
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        self._provider = provider
        self._repository = repository
        self._entropy = entropy
        self._authorization_lifetime = authorization_lifetime
        self._session_idle_lifetime = session_idle_lifetime
        self._session_absolute_lifetime = session_absolute_lifetime

    def begin_authorization(
        self, *, redirect_uri: RedirectUri, now: datetime
    ) -> AuthorizationRequest:
        """Create and persist one high-entropy, S256-only authorization request."""

        redirect = _snapshot(
            lambda: RedirectUri(redirect_uri.reveal()),
            AuthenticationFailureCode.MALFORMED_INPUT,
        )
        observed_at = require_utc(now)
        state_bytes = self._token_bytes()
        nonce_bytes = self._token_bytes()
        verifier_bytes = self._token_bytes()
        if len({state_bytes, nonce_bytes, verifier_bytes}) != 3:
            _raise(AuthenticationFailureCode.ENTROPY_FAILURE)
        state = AuthorizationState.from_bytes(state_bytes)
        nonce = OidcNonce.from_bytes(nonce_bytes)
        verifier = PkceVerifier.from_bytes(verifier_bytes)
        request = AuthorizationRequest(
            state=state,
            nonce=nonce,
            pkce_challenge=verifier.s256_challenge(),
            pkce_method=PkceMethod.S256,
            redirect_uri=redirect,
            created_at=observed_at,
            expires_at=observed_at + self._authorization_lifetime,
        )
        transaction = AuthorizationTransaction(
            state_fingerprint=state.fingerprint(),
            nonce=nonce,
            verifier=verifier,
            redirect_uri=redirect,
            created_at=request.created_at,
            expires_at=request.expires_at,
        )
        failure: AuthenticationFailureCode | None = None
        repository_value = _snapshot(
            lambda: snapshot_authorization_transaction(transaction),
            AuthenticationFailureCode.MALFORMED_INPUT,
        )
        repository_baseline = _snapshot(
            lambda: snapshot_authorization_transaction(repository_value),
            AuthenticationFailureCode.MALFORMED_INPUT,
        )
        try:
            self._repository.add_authorization(repository_value)
            repository_after = _snapshot(
                lambda: snapshot_authorization_transaction(repository_value),
                AuthenticationFailureCode.STORAGE_FAILURE,
            )
            _require_unchanged(
                repository_baseline,
                repository_after,
                AuthenticationFailureCode.STORAGE_FAILURE,
            )
        except AuthenticationFailure as error:
            failure = _failure_code(error, AuthenticationFailureCode.STORAGE_FAILURE)
        except Exception:
            failure = AuthenticationFailureCode.STORAGE_FAILURE
        if failure is not None:
            _raise(failure)
        return request

    def complete_authorization(
        self, *, callback: AuthorizationCallback, now: datetime
    ) -> Session:
        """Consume correlation state, exchange once, and create a bounded session."""

        received_callback = _snapshot(
            lambda: snapshot_authorization_callback(callback),
            AuthenticationFailureCode.MALFORMED_INPUT,
        )
        observed_at = require_utc(now)
        transaction: AuthorizationTransaction | None = None
        failure: AuthenticationFailureCode | None = None
        try:
            transaction = self._repository.consume_authorization(
                state_fingerprint=received_callback.state.fingerprint(),
                now=observed_at,
            )
        except AuthenticationFailure as error:
            failure = _failure_code(error, AuthenticationFailureCode.STORAGE_FAILURE)
        except Exception:
            failure = AuthenticationFailureCode.STORAGE_FAILURE
        if failure is not None or transaction is None:
            _raise(failure or AuthenticationFailureCode.STORAGE_FAILURE)
        transaction = _snapshot(
            lambda: snapshot_authorization_transaction(transaction),
            AuthenticationFailureCode.STORAGE_FAILURE,
        )

        principal: PrincipalIdentity | None = None
        provider_callback = _snapshot(
            lambda: snapshot_authorization_callback(received_callback),
            AuthenticationFailureCode.PROVIDER_FAILURE,
        )
        provider_callback_baseline = _snapshot(
            lambda: snapshot_authorization_callback(provider_callback),
            AuthenticationFailureCode.PROVIDER_FAILURE,
        )
        provider_verifier = _snapshot(
            lambda: PkceVerifier(transaction.verifier.reveal()),
            AuthenticationFailureCode.PROVIDER_FAILURE,
        )
        provider_verifier_baseline = _snapshot(
            lambda: PkceVerifier(provider_verifier.reveal()),
            AuthenticationFailureCode.PROVIDER_FAILURE,
        )
        provider_nonce = _snapshot(
            lambda: OidcNonce(transaction.nonce.reveal()),
            AuthenticationFailureCode.PROVIDER_FAILURE,
        )
        provider_nonce_baseline = _snapshot(
            lambda: OidcNonce(provider_nonce.reveal()),
            AuthenticationFailureCode.PROVIDER_FAILURE,
        )
        try:
            principal = self._provider.exchange(
                callback=provider_callback,
                verifier=provider_verifier,
                expected_nonce=provider_nonce,
                now=observed_at,
            )
            _require_unchanged(
                provider_callback_baseline,
                _snapshot(
                    lambda: snapshot_authorization_callback(provider_callback),
                    AuthenticationFailureCode.PROVIDER_FAILURE,
                ),
                AuthenticationFailureCode.PROVIDER_FAILURE,
            )
            _require_unchanged(
                provider_verifier_baseline,
                _snapshot(
                    lambda: PkceVerifier(provider_verifier.reveal()),
                    AuthenticationFailureCode.PROVIDER_FAILURE,
                ),
                AuthenticationFailureCode.PROVIDER_FAILURE,
            )
            _require_unchanged(
                provider_nonce_baseline,
                _snapshot(
                    lambda: OidcNonce(provider_nonce.reveal()),
                    AuthenticationFailureCode.PROVIDER_FAILURE,
                ),
                AuthenticationFailureCode.PROVIDER_FAILURE,
            )
        except AuthenticationFailure as error:
            failure = _failure_code(error, AuthenticationFailureCode.PROVIDER_FAILURE)
        except Exception:
            failure = AuthenticationFailureCode.PROVIDER_FAILURE
        if failure is not None or principal is None:
            _raise(failure or AuthenticationFailureCode.PROVIDER_FAILURE)
        principal = _snapshot(
            lambda: snapshot_principal_identity(principal),
            AuthenticationFailureCode.PROVIDER_FAILURE,
        )

        session = Session(
            session_id=SessionId.from_bytes(self._token_bytes()),
            principal=principal,
            created_at=observed_at,
            last_seen_at=observed_at,
            idle_expires_at=observed_at + self._session_idle_lifetime,
            absolute_expires_at=observed_at + self._session_absolute_lifetime,
        )
        repository_session = _snapshot(
            lambda: snapshot_session(session),
            AuthenticationFailureCode.MALFORMED_INPUT,
        )
        repository_baseline = _snapshot(
            lambda: snapshot_session(repository_session),
            AuthenticationFailureCode.MALFORMED_INPUT,
        )
        try:
            self._repository.create_session(repository_session)
            _require_unchanged(
                repository_baseline,
                _snapshot(
                    lambda: snapshot_session(repository_session),
                    AuthenticationFailureCode.STORAGE_FAILURE,
                ),
                AuthenticationFailureCode.STORAGE_FAILURE,
            )
        except AuthenticationFailure as error:
            failure = _failure_code(error, AuthenticationFailureCode.STORAGE_FAILURE)
        except Exception:
            failure = AuthenticationFailureCode.STORAGE_FAILURE
        if failure is not None:
            _raise(failure)
        return _snapshot(
            lambda: snapshot_session(session),
            AuthenticationFailureCode.STORAGE_FAILURE,
        )

    def require_session(self, *, session_id: SessionId, now: datetime) -> Session:
        """Require an active session and deterministically advance its idle window."""

        session = self._load_session(session_id)
        observed_at = require_utc(now)
        self._require_monotonic_session_time(session, observed_at)
        session.require_active(observed_at)
        idle_expires_at = min(
            observed_at + self._session_idle_lifetime,
            session.absolute_expires_at,
        )
        refreshed = replace(
            session,
            last_seen_at=observed_at,
            idle_expires_at=idle_expires_at,
        )
        if refreshed == session:
            return session
        self._replace_session(expected=session, replacement=refreshed)
        return refreshed

    def rotate_session(self, *, session_id: SessionId, now: datetime) -> Session:
        """Atomically revoke one active session and create a new identifier."""

        try:
            predecessor = self._load_session(session_id)
        except AuthenticationFailure as error:
            if error.code is AuthenticationFailureCode.SESSION_REVOKED:
                _raise(AuthenticationFailureCode.SESSION_CONFLICT)
            raise
        observed_at = require_utc(now)
        self._require_monotonic_session_time(predecessor, observed_at)
        predecessor.require_active(observed_at)
        successor = Session(
            session_id=SessionId.from_bytes(self._token_bytes()),
            principal=predecessor.principal,
            created_at=observed_at,
            last_seen_at=observed_at,
            idle_expires_at=min(
                observed_at + self._session_idle_lifetime,
                predecessor.absolute_expires_at,
            ),
            absolute_expires_at=predecessor.absolute_expires_at,
            rotated_from=predecessor.session_id,
        )
        revoked_predecessor = replace(predecessor, revoked_at=observed_at)
        failure: AuthenticationFailureCode | None = None
        repository_expected = _snapshot(
            lambda: snapshot_session(predecessor),
            AuthenticationFailureCode.MALFORMED_INPUT,
        )
        repository_revoked = _snapshot(
            lambda: snapshot_session(revoked_predecessor),
            AuthenticationFailureCode.MALFORMED_INPUT,
        )
        repository_successor = _snapshot(
            lambda: snapshot_session(successor),
            AuthenticationFailureCode.MALFORMED_INPUT,
        )
        expected_baseline = _snapshot(
            lambda: snapshot_session(repository_expected),
            AuthenticationFailureCode.MALFORMED_INPUT,
        )
        revoked_baseline = _snapshot(
            lambda: snapshot_session(repository_revoked),
            AuthenticationFailureCode.MALFORMED_INPUT,
        )
        successor_baseline = _snapshot(
            lambda: snapshot_session(repository_successor),
            AuthenticationFailureCode.MALFORMED_INPUT,
        )
        try:
            self._repository.rotate_session(
                expected=repository_expected,
                revoked_predecessor=repository_revoked,
                successor=repository_successor,
            )
            for baseline, value in (
                (expected_baseline, repository_expected),
                (revoked_baseline, repository_revoked),
                (successor_baseline, repository_successor),
            ):
                try:
                    after = snapshot_session(value)
                except Exception:
                    _raise(AuthenticationFailureCode.STORAGE_FAILURE)
                _require_unchanged(
                    baseline,
                    after,
                    AuthenticationFailureCode.STORAGE_FAILURE,
                )
        except AuthenticationFailure as error:
            failure = _failure_code(error, AuthenticationFailureCode.STORAGE_FAILURE)
        except Exception:
            failure = AuthenticationFailureCode.STORAGE_FAILURE
        if failure is not None:
            _raise(failure)
        return successor

    def revoke_session(self, *, session_id: SessionId, now: datetime) -> Session:
        """Revoke one session; repeated revocation is safely idempotent."""

        session = self._load_session(session_id)
        observed_at = require_utc(now)
        if observed_at < session.created_at:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        if session.revoked_at is not None:
            return session
        revoked = replace(session, revoked_at=observed_at)
        self._replace_session(expected=session, replacement=revoked)
        return revoked

    def recover_session_rotation(
        self, *, predecessor_id: SessionId, now: datetime
    ) -> Session:
        """Resolve a repository commit ambiguity without retrying rotation."""

        requested_id = _snapshot(
            lambda: snapshot_session_id(predecessor_id),
            AuthenticationFailureCode.MALFORMED_INPUT,
        )
        observed_at = require_utc(now)
        recovered: Session | None = None
        failure: AuthenticationFailureCode | None = None
        repository_id = _snapshot(
            lambda: snapshot_session_id(requested_id),
            AuthenticationFailureCode.MALFORMED_INPUT,
        )
        repository_id_baseline = _snapshot(
            lambda: snapshot_session_id(repository_id),
            AuthenticationFailureCode.MALFORMED_INPUT,
        )
        try:
            recovered = self._repository.recover_session_rotation(repository_id)
            _require_unchanged(
                repository_id_baseline,
                _snapshot(
                    lambda: snapshot_session_id(repository_id),
                    AuthenticationFailureCode.STORAGE_FAILURE,
                ),
                AuthenticationFailureCode.STORAGE_FAILURE,
            )
        except AuthenticationFailure as error:
            failure = _failure_code(error, AuthenticationFailureCode.STORAGE_FAILURE)
        except Exception:
            failure = AuthenticationFailureCode.STORAGE_FAILURE
        if failure is not None or recovered is None or type(recovered) is not Session:
            _raise(failure or AuthenticationFailureCode.STORAGE_FAILURE)
        recovered = _snapshot(
            lambda: snapshot_session(recovered),
            AuthenticationFailureCode.STORAGE_FAILURE,
        )
        self._require_monotonic_session_time(recovered, observed_at)
        recovered.require_active(observed_at)
        return recovered

    def _token_bytes(self) -> bytes:
        value: object = None
        failed = False
        try:
            value = self._entropy.token_bytes(_ENTROPY_BYTES)
        except Exception:
            failed = True
        if failed or type(value) is not bytes or len(value) != _ENTROPY_BYTES:
            _raise(AuthenticationFailureCode.ENTROPY_FAILURE)
        return bytes(value)

    def _load_session(self, session_id: SessionId) -> Session:
        requested_id = _snapshot(
            lambda: snapshot_session_id(session_id),
            AuthenticationFailureCode.MALFORMED_INPUT,
        )
        session: Session | None = None
        failure: AuthenticationFailureCode | None = None
        repository_id = _snapshot(
            lambda: snapshot_session_id(requested_id),
            AuthenticationFailureCode.MALFORMED_INPUT,
        )
        repository_id_baseline = _snapshot(
            lambda: snapshot_session_id(repository_id),
            AuthenticationFailureCode.MALFORMED_INPUT,
        )
        try:
            session = self._repository.load_session(repository_id)
            _require_unchanged(
                repository_id_baseline,
                _snapshot(
                    lambda: snapshot_session_id(repository_id),
                    AuthenticationFailureCode.STORAGE_FAILURE,
                ),
                AuthenticationFailureCode.STORAGE_FAILURE,
            )
        except AuthenticationFailure as error:
            failure = _failure_code(error, AuthenticationFailureCode.STORAGE_FAILURE)
        except Exception:
            failure = AuthenticationFailureCode.STORAGE_FAILURE
        if failure is not None or session is None or type(session) is not Session:
            _raise(failure or AuthenticationFailureCode.STORAGE_FAILURE)
        return _snapshot(
            lambda: snapshot_session(session),
            AuthenticationFailureCode.STORAGE_FAILURE,
        )

    def _replace_session(self, *, expected: Session, replacement: Session) -> None:
        failure: AuthenticationFailureCode | None = None
        repository_expected = _snapshot(
            lambda: snapshot_session(expected),
            AuthenticationFailureCode.MALFORMED_INPUT,
        )
        repository_replacement = _snapshot(
            lambda: snapshot_session(replacement),
            AuthenticationFailureCode.MALFORMED_INPUT,
        )
        expected_baseline = _snapshot(
            lambda: snapshot_session(repository_expected),
            AuthenticationFailureCode.MALFORMED_INPUT,
        )
        replacement_baseline = _snapshot(
            lambda: snapshot_session(repository_replacement),
            AuthenticationFailureCode.MALFORMED_INPUT,
        )
        try:
            self._repository.replace_session(
                expected=repository_expected,
                replacement=repository_replacement,
            )
            _require_unchanged(
                expected_baseline,
                _snapshot(
                    lambda: snapshot_session(repository_expected),
                    AuthenticationFailureCode.STORAGE_FAILURE,
                ),
                AuthenticationFailureCode.STORAGE_FAILURE,
            )
            _require_unchanged(
                replacement_baseline,
                _snapshot(
                    lambda: snapshot_session(repository_replacement),
                    AuthenticationFailureCode.STORAGE_FAILURE,
                ),
                AuthenticationFailureCode.STORAGE_FAILURE,
            )
        except AuthenticationFailure as error:
            failure = _failure_code(error, AuthenticationFailureCode.STORAGE_FAILURE)
        except Exception:
            failure = AuthenticationFailureCode.STORAGE_FAILURE
        if failure is not None:
            _raise(failure)

    @staticmethod
    def _require_monotonic_session_time(session: Session, now: datetime) -> None:
        if now < session.created_at or now < session.last_seen_at:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)


__all__ = ["AuthenticationService"]

"""Focused lifecycle and fail-closed tests for ST-0401 authentication."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import hashlib
import socket
from typing import NoReturn, cast

import pytest

from raos.adapters.development_oidc import (
    DevelopmentOidcAdapter,
    InMemoryAuthenticationRepository,
)
from raos.application.iam.authentication import AuthenticationService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authentication import (
    AuthenticationFailure,
    AuthenticationFailureCode,
    AuthorizationCallback,
    AuthorizationCode,
    AuthorizationRequest,
    AuthorizationState,
    Issuer,
    OidcNonce,
    PkceMethod,
    PkceVerifier,
    PrincipalIdentity,
    RedirectUri,
    Session,
    Subject,
)


NOW = datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc)


def _bytes(index: int) -> bytes:
    return hashlib.sha256(f"SYNTHETIC-ST0401-{index}".encode()).digest()


class _ScriptedEntropy:
    def __init__(self, *indexes: int) -> None:
        self._values = iter(_bytes(index) for index in indexes)

    def token_bytes(self, size: int) -> bytes:
        assert size == 32
        return next(self._values)


def _principal() -> PrincipalIdentity:
    return PrincipalIdentity(
        issuer=Issuer("https://oidc.dev.invalid"),
        subject=Subject("synthetic-admin"),
        display_name="Synthetic administrator",
    )


def _stack(
    *,
    indexes: tuple[int, ...] = (1, 2, 3, 4, 5, 6),
    code_lifetime: timedelta = timedelta(minutes=2),
    idle_lifetime: timedelta = timedelta(minutes=30),
    absolute_lifetime: timedelta = timedelta(hours=8),
) -> tuple[
    AuthenticationService,
    DevelopmentOidcAdapter,
    InMemoryAuthenticationRepository,
]:
    repository = InMemoryAuthenticationRepository(
        environment=RuntimeEnvironment.ENV_DEV
    )
    provider = DevelopmentOidcAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        principal=_principal(),
        code_lifetime=code_lifetime,
    )
    service = AuthenticationService(
        provider=provider,
        repository=repository,
        entropy=_ScriptedEntropy(*indexes),
        session_idle_lifetime=idle_lifetime,
        session_absolute_lifetime=absolute_lifetime,
    )
    return service, provider, repository


def _request(
    *,
    state_index: int = 20,
    nonce_index: int = 21,
    verifier_index: int = 22,
    created_at: datetime = NOW,
) -> tuple[AuthorizationRequest, PkceVerifier]:
    verifier = PkceVerifier.from_bytes(_bytes(verifier_index))
    request = AuthorizationRequest(
        state=AuthorizationState.from_bytes(_bytes(state_index)),
        nonce=OidcNonce.from_bytes(_bytes(nonce_index)),
        pkce_challenge=verifier.s256_challenge(),
        pkce_method=PkceMethod.S256,
        redirect_uri=RedirectUri("https://admin.dev.invalid/auth/callback"),
        created_at=created_at,
        expires_at=created_at + timedelta(minutes=5),
    )
    return request, verifier


def _assert_failure(
    code: AuthenticationFailureCode,
    operation: Callable[[], object],
) -> AuthenticationFailure:
    with pytest.raises(AuthenticationFailure) as caught:
        operation()
    assert caught.value.code is code
    assert caught.value.args == (code.value,)
    return caught.value


def test_deterministic_development_flow_is_provider_neutral_and_single_use() -> None:
    service, provider, _repository = _stack()
    request = service.begin_authorization(
        redirect_uri=RedirectUri("https://admin.dev.invalid/auth/callback"),
        now=NOW,
    )

    callback = provider.authorize(request=request, now=NOW)
    assert provider.authorize(request=request, now=NOW) == callback
    session = service.complete_authorization(callback=callback, now=NOW)

    assert isinstance(request, AuthorizationRequest)
    assert request.pkce_method is PkceMethod.S256
    assert session.principal == _principal()
    assert service.require_session(session_id=session.session_id, now=NOW) == session
    _assert_failure(
        AuthenticationFailureCode.AUTHORIZATION_REPLAY,
        lambda: service.complete_authorization(callback=callback, now=NOW),
    )


def test_generated_state_nonce_and_pkce_are_distinct_canonical_256_bit_values() -> None:
    service, _provider, _repository = _stack()
    request = service.begin_authorization(
        redirect_uri=RedirectUri("http://127.0.0.1:8010/auth/callback"),
        now=NOW,
    )

    wire_values = {
        request.state.reveal(),
        request.nonce.reveal(),
        request.pkce_challenge.reveal(),
    }
    assert len(wire_values) == 3
    assert all(len(value) == 43 and "=" not in value for value in wire_values)
    assert AuthorizationState(request.state.reveal()) == request.state
    assert OidcNonce(request.nonce.reveal()) == request.nonce


@pytest.mark.parametrize(
    "malformed",
    ("", "A" * 42, "A" * 44, "+" + "A" * 42, "A" * 42 + "="),
)
def test_state_and_nonce_parsers_reject_malformed_values(malformed: str) -> None:
    _assert_failure(
        AuthenticationFailureCode.MALFORMED_INPUT,
        lambda: AuthorizationState(malformed),
    )
    _assert_failure(
        AuthenticationFailureCode.MALFORMED_INPUT,
        lambda: OidcNonce(malformed),
    )


def test_unknown_and_expired_authorizations_fail_closed_and_become_single_use() -> None:
    service, provider, _repository = _stack()
    request = service.begin_authorization(
        redirect_uri=RedirectUri("https://admin.dev.invalid/auth/callback"),
        now=NOW,
    )
    callback = provider.authorize(request=request, now=NOW)
    unknown = AuthorizationCallback(
        state=AuthorizationState.from_bytes(_bytes(90)),
        code=callback.code,
    )
    _assert_failure(
        AuthenticationFailureCode.AUTHORIZATION_UNKNOWN,
        lambda: service.complete_authorization(callback=unknown, now=NOW),
    )
    _assert_failure(
        AuthenticationFailureCode.AUTHORIZATION_EXPIRED,
        lambda: service.complete_authorization(
            callback=callback,
            now=NOW + timedelta(minutes=5),
        ),
    )
    _assert_failure(
        AuthenticationFailureCode.AUTHORIZATION_REPLAY,
        lambda: service.complete_authorization(
            callback=callback,
            now=NOW + timedelta(minutes=5),
        ),
    )


def test_code_expiry_is_strict_and_the_failed_exchange_cannot_be_replayed() -> None:
    service, provider, _repository = _stack(code_lifetime=timedelta(seconds=30))
    request = service.begin_authorization(
        redirect_uri=RedirectUri("https://admin.dev.invalid/auth/callback"),
        now=NOW,
    )
    callback = provider.authorize(request=request, now=NOW)

    _assert_failure(
        AuthenticationFailureCode.CODE_EXPIRED,
        lambda: service.complete_authorization(
            callback=callback,
            now=NOW + timedelta(seconds=30),
        ),
    )
    _assert_failure(
        AuthenticationFailureCode.AUTHORIZATION_REPLAY,
        lambda: service.complete_authorization(
            callback=callback,
            now=NOW + timedelta(seconds=30),
        ),
    )


@pytest.mark.parametrize(
    ("failure", "exchange_values"),
    (
        (AuthenticationFailureCode.STATE_MISMATCH, (99, 22, 21)),
        (AuthenticationFailureCode.PKCE_MISMATCH, (20, 98, 21)),
        (AuthenticationFailureCode.NONCE_MISMATCH, (20, 22, 97)),
    ),
)
def test_provider_denies_correlation_and_pkce_mismatches_once(
    failure: AuthenticationFailureCode,
    exchange_values: tuple[int, int, int],
) -> None:
    provider = DevelopmentOidcAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        principal=_principal(),
    )
    request, verifier = _request()
    callback = provider.authorize(request=request, now=NOW)
    state_index, verifier_index, nonce_index = exchange_values
    attempted_callback = AuthorizationCallback(
        state=(
            callback.state
            if state_index == 20
            else AuthorizationState.from_bytes(_bytes(state_index))
        ),
        code=callback.code,
    )
    attempted_verifier = (
        verifier
        if verifier_index == 22
        else PkceVerifier.from_bytes(_bytes(verifier_index))
    )
    attempted_nonce = (
        request.nonce
        if nonce_index == 21
        else OidcNonce.from_bytes(_bytes(nonce_index))
    )

    _assert_failure(
        failure,
        lambda: provider.exchange(
            callback=attempted_callback,
            verifier=attempted_verifier,
            expected_nonce=attempted_nonce,
            now=NOW,
        ),
    )
    _assert_failure(
        AuthenticationFailureCode.CODE_REPLAY,
        lambda: provider.exchange(
            callback=callback,
            verifier=verifier,
            expected_nonce=request.nonce,
            now=NOW,
        ),
    )


def test_plain_pkce_and_unknown_code_fail_closed() -> None:
    request, verifier = _request()
    _assert_failure(
        AuthenticationFailureCode.PKCE_UNSUPPORTED,
        lambda: AuthorizationRequest(
            state=request.state,
            nonce=request.nonce,
            pkce_challenge=request.pkce_challenge,
            pkce_method=cast(PkceMethod, "plain"),
            redirect_uri=request.redirect_uri,
            created_at=request.created_at,
            expires_at=request.expires_at,
        ),
    )
    provider = DevelopmentOidcAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        principal=_principal(),
    )
    unknown = AuthorizationCallback(
        state=request.state,
        code=AuthorizationCode.from_bytes(_bytes(96)),
    )
    _assert_failure(
        AuthenticationFailureCode.CODE_UNKNOWN,
        lambda: provider.exchange(
            callback=unknown,
            verifier=verifier,
            expected_nonce=request.nonce,
            now=NOW,
        ),
    )


def test_session_rotation_revocation_and_idle_expiry_fail_closed() -> None:
    service, provider, _repository = _stack()
    request = service.begin_authorization(
        redirect_uri=RedirectUri("https://admin.dev.invalid/auth/callback"),
        now=NOW,
    )
    session = service.complete_authorization(
        callback=provider.authorize(request=request, now=NOW),
        now=NOW,
    )
    successor = service.rotate_session(
        session_id=session.session_id,
        now=NOW + timedelta(minutes=1),
    )

    assert successor.session_id != session.session_id
    assert successor.rotated_from == session.session_id
    assert successor.absolute_expires_at == session.absolute_expires_at
    _assert_failure(
        AuthenticationFailureCode.SESSION_REVOKED,
        lambda: service.require_session(
            session_id=session.session_id,
            now=NOW + timedelta(minutes=1),
        ),
    )
    revoked = service.revoke_session(
        session_id=successor.session_id,
        now=NOW + timedelta(minutes=2),
    )
    assert (
        service.revoke_session(
            session_id=successor.session_id,
            now=NOW + timedelta(minutes=3),
        )
        == revoked
    )
    _assert_failure(
        AuthenticationFailureCode.SESSION_REVOKED,
        lambda: service.require_session(
            session_id=successor.session_id,
            now=NOW + timedelta(minutes=3),
        ),
    )

    expiring_service, expiring_provider, _ = _stack(indexes=(31, 32, 33, 34))
    expiring_request = expiring_service.begin_authorization(
        redirect_uri=RedirectUri("https://admin.dev.invalid/auth/callback"),
        now=NOW,
    )
    expiring_session = expiring_service.complete_authorization(
        callback=expiring_provider.authorize(request=expiring_request, now=NOW),
        now=NOW,
    )
    _assert_failure(
        AuthenticationFailureCode.SESSION_EXPIRED,
        lambda: expiring_service.require_session(
            session_id=expiring_session.session_id,
            now=NOW + timedelta(minutes=30),
        ),
    )


def test_absolute_session_lifetime_cannot_be_extended_by_activity() -> None:
    service, provider, _repository = _stack(
        idle_lifetime=timedelta(hours=2),
        absolute_lifetime=timedelta(hours=2),
    )
    request = service.begin_authorization(
        redirect_uri=RedirectUri("https://admin.dev.invalid/auth/callback"),
        now=NOW,
    )
    session = service.complete_authorization(
        callback=provider.authorize(request=request, now=NOW),
        now=NOW,
    )
    active = service.require_session(
        session_id=session.session_id,
        now=NOW + timedelta(hours=1),
    )
    assert active.idle_expires_at == session.absolute_expires_at
    _assert_failure(
        AuthenticationFailureCode.SESSION_EXPIRED,
        lambda: service.require_session(
            session_id=session.session_id,
            now=NOW + timedelta(hours=2),
        ),
    )


@pytest.mark.parametrize(
    "environment",
    tuple(
        value for value in RuntimeEnvironment if value is not RuntimeEnvironment.ENV_DEV
    ),
)
def test_development_adapter_and_repository_reject_every_other_environment(
    environment: RuntimeEnvironment,
) -> None:
    _assert_failure(
        AuthenticationFailureCode.DEVELOPMENT_ONLY,
        lambda: DevelopmentOidcAdapter(
            environment=environment,
            principal=_principal(),
        ),
    )
    _assert_failure(
        AuthenticationFailureCode.DEVELOPMENT_ONLY,
        lambda: InMemoryAuthenticationRepository(environment=environment),
    )


def test_development_guard_rejects_a_string_that_only_looks_like_env_dev() -> None:
    environment = cast(RuntimeEnvironment, "ENV-DEV")
    _assert_failure(
        AuthenticationFailureCode.DEVELOPMENT_ONLY,
        lambda: DevelopmentOidcAdapter(
            environment=environment,
            principal=_principal(),
        ),
    )
    _assert_failure(
        AuthenticationFailureCode.DEVELOPMENT_ONLY,
        lambda: InMemoryAuthenticationRepository(environment=environment),
    )


def test_development_fake_has_no_password_flow_and_uses_no_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, provider, _repository = _stack()

    def deny_network(*args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise AssertionError("network access is forbidden in ST-0401")

    monkeypatch.setattr(socket, "socket", deny_network)
    assert not hasattr(provider, "password")
    assert not hasattr(provider, "authenticate_password")
    request = service.begin_authorization(
        redirect_uri=RedirectUri("https://admin.dev.invalid/auth/callback"),
        now=NOW,
    )
    session = service.complete_authorization(
        callback=provider.authorize(request=request, now=NOW),
        now=NOW,
    )
    assert isinstance(session, Session)


def test_authentication_values_and_failures_are_redacted() -> None:
    request, verifier = _request()
    provider = DevelopmentOidcAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        principal=_principal(),
    )
    callback = provider.authorize(request=request, now=NOW)
    sensitive_values = (
        request.state.reveal(),
        request.nonce.reveal(),
        request.pkce_challenge.reveal(),
        request.redirect_uri.reveal(),
        verifier.reveal(),
        callback.code.reveal(),
    )
    rendered = " ".join(
        text
        for value in (request, callback, verifier, provider)
        for text in (str(value), repr(value))
    )
    failure = _assert_failure(
        AuthenticationFailureCode.PKCE_MISMATCH,
        lambda: provider.exchange(
            callback=callback,
            verifier=PkceVerifier.from_bytes(_bytes(91)),
            expected_nonce=request.nonce,
            now=NOW,
        ),
    )
    diagnostics = f"{failure!s} {failure!r} {failure.args!r} {rendered}"
    assert all(value not in diagnostics for value in sensitive_values)


class _ExplodingProvider:
    def __init__(self, canary: str) -> None:
        self._canary = canary

    def exchange(
        self,
        *,
        callback: AuthorizationCallback,
        verifier: PkceVerifier,
        expected_nonce: OidcNonce,
        now: datetime,
    ) -> PrincipalIdentity:
        del callback, verifier, expected_nonce, now
        raise RuntimeError(self._canary)


def test_provider_diagnostics_are_sanitized_at_the_application_boundary() -> None:
    canary = "-".join(("SYNTHETIC", "PRIVATE", "PROVIDER", "VALUE"))
    repository = InMemoryAuthenticationRepository(
        environment=RuntimeEnvironment.ENV_DEV
    )
    service = AuthenticationService(
        provider=_ExplodingProvider(canary),
        repository=repository,
        entropy=_ScriptedEntropy(61, 62, 63, 64),
    )
    request = service.begin_authorization(
        redirect_uri=RedirectUri("https://admin.dev.invalid/auth/callback"),
        now=NOW,
    )
    fake = DevelopmentOidcAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        principal=_principal(),
    )
    callback = fake.authorize(request=request, now=NOW)

    failure = _assert_failure(
        AuthenticationFailureCode.PROVIDER_FAILURE,
        lambda: service.complete_authorization(callback=callback, now=NOW),
    )
    assert canary not in f"{failure!s} {failure!r} {failure.args!r}"

"""Focused behavior and failure tests for the ST-0402 assurance seam."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import json
import pickle
from typing import cast

import pytest

from raos.adapters.development_oidc import (
    DevelopmentOidcAdapter,
    InMemoryAuthenticationRepository,
)
from raos.adapters.development_step_up import DevelopmentScriptedStepUpVerifier
from raos.application.iam.authentication import AuthenticationService
from raos.application.iam.step_up import StepUpGuard
from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authentication import (
    AuthenticationFailure,
    AuthenticationFailureCode,
    Issuer,
    PrincipalIdentity,
    Session,
    SessionId,
    Subject,
)
from raos.domain.iam.step_up import (
    StepUpAssuranceType,
    StepUpFailure,
    StepUpFailureCode,
    StepUpGrant,
    StepUpVerificationOutcome,
)
from raos.ports.step_up import StepUpVerifier


NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


def _bytes(index: int) -> bytes:
    return bytes((index + offset) % 256 for offset in range(32))


def _principal(index: int = 1) -> PrincipalIdentity:
    return PrincipalIdentity(
        issuer=Issuer(f"https://issuer-{index}.dev.invalid"),
        subject=Subject(f"synthetic-subject-{index}"),
        display_name=f"Synthetic Administrator {index}",
    )


def _session(
    *,
    index: int = 1,
    principal: PrincipalIdentity | None = None,
    idle_expires_at: datetime = NOW + timedelta(minutes=20),
    absolute_expires_at: datetime = NOW + timedelta(hours=2),
    revoked_at: datetime | None = None,
) -> Session:
    return Session(
        session_id=SessionId.from_bytes(_bytes(index)),
        principal=principal or _principal(index),
        created_at=NOW - timedelta(minutes=10),
        last_seen_at=NOW - timedelta(minutes=1),
        idle_expires_at=idle_expires_at,
        absolute_expires_at=absolute_expires_at,
        revoked_at=revoked_at,
    )


def _grant(
    session: Session,
    *,
    session_id: SessionId | None = None,
    issuer: Issuer | None = None,
    subject: Subject | None = None,
    assurance_type: StepUpAssuranceType = StepUpAssuranceType.MULTI_FACTOR,
    authenticated_at: datetime = NOW - timedelta(minutes=1),
    expires_at: datetime = NOW + timedelta(minutes=1),
) -> StepUpGrant:
    return StepUpGrant(
        session_id=session_id or session.session_id,
        issuer=issuer or session.principal.issuer,
        subject=subject or session.principal.subject,
        assurance_type=assurance_type,
        authenticated_at=authenticated_at,
        expires_at=expires_at,
    )


class _ScriptedEntropy:
    def __init__(self, *indexes: int) -> None:
        self._values = [_bytes(index) for index in indexes]

    def token_bytes(self, size: int) -> bytes:
        if size != 32 or not self._values:
            raise RuntimeError("synthetic entropy script exhausted")
        return self._values.pop(0)


def _service(
    session: Session, *, entropy_indexes: tuple[int, ...] = (90, 91)
) -> AuthenticationService:
    repository = InMemoryAuthenticationRepository(
        environment=RuntimeEnvironment.ENV_DEV
    )
    repository.create_session(session)
    return AuthenticationService(
        provider=DevelopmentOidcAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            principal=session.principal,
        ),
        repository=repository,
        entropy=_ScriptedEntropy(*entropy_indexes),
    )


def _guard(
    session: Session,
    verifier: object,
    *,
    entropy_indexes: tuple[int, ...] = (90, 91),
) -> StepUpGuard:
    return StepUpGuard(
        session_service=_service(session, entropy_indexes=entropy_indexes),
        verifier=cast(StepUpVerifier, verifier),
    )


def _assert_step_up_failure(
    code: StepUpFailureCode, operation: Callable[[], object]
) -> StepUpFailure:
    with pytest.raises(StepUpFailure) as captured:
        operation()
    assert captured.value.code is code
    return captured.value


def _assert_authentication_failure(
    code: AuthenticationFailureCode, operation: Callable[[], object]
) -> AuthenticationFailure:
    with pytest.raises(AuthenticationFailure) as captured:
        operation()
    assert captured.value.code is code
    return captured.value


class _StaticVerifier:
    def __init__(self, outcome: StepUpGrant | StepUpVerificationOutcome | None) -> None:
        self._outcome = outcome
        self.calls = 0

    def verify(
        self, *, session: Session, now: datetime
    ) -> StepUpGrant | StepUpVerificationOutcome | None:
        del session, now
        self.calls += 1
        return self._outcome


class _MalformedVerifier:
    def verify(
        self, *, session: Session, now: datetime
    ) -> StepUpGrant | StepUpVerificationOutcome | None:
        del session, now
        return cast(StepUpGrant, object())


class _ExplodingVerifier:
    def __init__(self, canary: str) -> None:
        self._canary = canary

    def verify(
        self, *, session: Session, now: datetime
    ) -> StepUpGrant | StepUpVerificationOutcome | None:
        raise RuntimeError(
            f"{self._canary}:{session.session_id.reveal()}:{now.isoformat()}"
        )


class _MutatingSessionVerifier:
    def __init__(self, outcome: StepUpGrant) -> None:
        self._outcome = outcome

    def verify(
        self, *, session: Session, now: datetime
    ) -> StepUpGrant | StepUpVerificationOutcome | None:
        del now
        object.__setattr__(
            session,
            "last_seen_at",
            session.last_seen_at + timedelta(seconds=1),
        )
        return self._outcome


def test_active_matching_session_and_current_multi_factor_grant_pass() -> None:
    session = _session()
    grant = _grant(session)
    verifier = DevelopmentScriptedStepUpVerifier(
        environment=RuntimeEnvironment.ENV_DEV,
        grants=(grant,),
    )

    accepted = _guard(session, verifier).require(
        session_id=session.session_id,
        now=NOW,
    )

    assert accepted == grant
    assert accepted is not grant


@pytest.mark.parametrize(
    ("outcome", "code"),
    (
        (None, StepUpFailureCode.CLAIM_MISSING),
        (StepUpVerificationOutcome.REJECTED, StepUpFailureCode.CLAIM_REJECTED),
    ),
)
def test_missing_and_negative_verifier_outcomes_fail_closed(
    outcome: StepUpGrant | StepUpVerificationOutcome | None,
    code: StepUpFailureCode,
) -> None:
    session = _session()
    verifier = _StaticVerifier(outcome)
    _assert_step_up_failure(
        code,
        lambda: _guard(session, verifier).require(
            session_id=session.session_id,
            now=NOW,
        ),
    )


def test_malformed_verifier_output_and_exception_are_sanitized() -> None:
    session = _session()
    _assert_step_up_failure(
        StepUpFailureCode.CLAIM_MALFORMED,
        lambda: _guard(session, _MalformedVerifier()).require(
            session_id=session.session_id,
            now=NOW,
        ),
    )

    canary = "SYNTHETIC-VERIFIER-PRIVATE-CANARY"
    failure = _assert_step_up_failure(
        StepUpFailureCode.VERIFIER_FAILURE,
        lambda: _guard(session, _ExplodingVerifier(canary)).require(
            session_id=session.session_id,
            now=NOW,
        ),
    )
    diagnostics = f"{failure!s} {failure!r} {failure.args!r}"
    assert canary not in diagnostics
    assert session.session_id.reveal() not in diagnostics
    assert failure.__cause__ is None
    assert failure.__context__ is None


def test_verifier_cannot_mutate_detached_session_input() -> None:
    session = _session()
    original_last_seen = session.last_seen_at
    _assert_step_up_failure(
        StepUpFailureCode.VERIFIER_FAILURE,
        lambda: _guard(
            session,
            _MutatingSessionVerifier(_grant(session)),
        ).require(session_id=session.session_id, now=NOW),
    )
    assert session.last_seen_at == original_last_seen


@pytest.mark.parametrize(
    ("grant_factory", "code"),
    (
        (
            lambda session: _grant(
                session,
                authenticated_at=NOW + timedelta(microseconds=1),
                expires_at=NOW + timedelta(minutes=1),
            ),
            StepUpFailureCode.CLAIM_NOT_YET_VALID,
        ),
        (
            lambda session: _grant(
                session,
                authenticated_at=NOW - timedelta(minutes=1),
                expires_at=NOW,
            ),
            StepUpFailureCode.CLAIM_EXPIRED,
        ),
        (
            lambda session: _grant(
                session,
                assurance_type=StepUpAssuranceType.UNSUPPORTED,
            ),
            StepUpFailureCode.ASSURANCE_TYPE_MISMATCH,
        ),
    ),
)
def test_future_expired_and_wrong_assurance_type_fail_closed(
    grant_factory: Callable[[Session], StepUpGrant],
    code: StepUpFailureCode,
) -> None:
    session = _session()
    verifier = _StaticVerifier(grant_factory(session))
    _assert_step_up_failure(
        code,
        lambda: _guard(session, verifier).require(
            session_id=session.session_id,
            now=NOW,
        ),
    )


@pytest.mark.parametrize(
    ("grant_factory", "code"),
    (
        (
            lambda session: _grant(
                session,
                session_id=SessionId.from_bytes(_bytes(42)),
            ),
            StepUpFailureCode.SESSION_MISMATCH,
        ),
        (
            lambda session: _grant(
                session,
                issuer=Issuer("https://different-issuer.dev.invalid"),
            ),
            StepUpFailureCode.PRINCIPAL_MISMATCH,
        ),
        (
            lambda session: _grant(
                session,
                subject=Subject("different-synthetic-subject"),
            ),
            StepUpFailureCode.PRINCIPAL_MISMATCH,
        ),
    ),
)
def test_session_and_stable_principal_binding_mismatches_fail(
    grant_factory: Callable[[Session], StepUpGrant],
    code: StepUpFailureCode,
) -> None:
    session = _session()
    _assert_step_up_failure(
        code,
        lambda: _guard(session, _StaticVerifier(grant_factory(session))).require(
            session_id=session.session_id,
            now=NOW,
        ),
    )


@pytest.mark.parametrize(
    ("session", "code"),
    (
        (
            _session(revoked_at=NOW - timedelta(seconds=1)),
            AuthenticationFailureCode.SESSION_REVOKED,
        ),
        (
            _session(idle_expires_at=NOW),
            AuthenticationFailureCode.SESSION_EXPIRED,
        ),
        (
            _session(idle_expires_at=NOW, absolute_expires_at=NOW),
            AuthenticationFailureCode.SESSION_EXPIRED,
        ),
    ),
)
def test_inactive_sessions_fail_before_assurance_is_consulted(
    session: Session,
    code: AuthenticationFailureCode,
) -> None:
    verifier = _StaticVerifier(_grant(session))
    _assert_authentication_failure(
        code,
        lambda: _guard(session, verifier).require(
            session_id=session.session_id,
            now=NOW,
        ),
    )
    assert verifier.calls == 0


def test_rotated_predecessor_fails_before_assurance_and_grant_cannot_move() -> None:
    predecessor = _session()
    service = _service(predecessor, entropy_indexes=(70,))
    successor = service.rotate_session(session_id=predecessor.session_id, now=NOW)
    predecessor_grant = _grant(predecessor, expires_at=NOW + timedelta(minutes=2))
    verifier = _StaticVerifier(predecessor_grant)
    guard = StepUpGuard(session_service=service, verifier=verifier)

    _assert_authentication_failure(
        AuthenticationFailureCode.SESSION_REVOKED,
        lambda: guard.require(session_id=predecessor.session_id, now=NOW),
    )
    assert verifier.calls == 0

    _assert_step_up_failure(
        StepUpFailureCode.SESSION_MISMATCH,
        lambda: guard.require(
            session_id=successor.session_id,
            now=NOW + timedelta(seconds=1),
        ),
    )
    assert verifier.calls == 1


def test_grant_cannot_be_reused_for_an_unrelated_active_session() -> None:
    original = _session(index=1)
    unrelated = _session(index=2)
    verifier = _StaticVerifier(_grant(original))

    _assert_step_up_failure(
        StepUpFailureCode.SESSION_MISMATCH,
        lambda: _guard(unrelated, verifier).require(
            session_id=unrelated.session_id,
            now=NOW,
        ),
    )


def test_grant_requires_explicit_strict_utc_interval() -> None:
    session = _session()
    _assert_step_up_failure(
        StepUpFailureCode.CLAIM_MALFORMED,
        lambda: _grant(
            session,
            authenticated_at=NOW.replace(tzinfo=None),
        ),
    )
    _assert_step_up_failure(
        StepUpFailureCode.CLAIM_MALFORMED,
        lambda: _grant(
            session,
            authenticated_at=NOW,
            expires_at=NOW,
        ),
    )


@pytest.mark.parametrize(
    "environment",
    tuple(
        value for value in RuntimeEnvironment if value is not RuntimeEnvironment.ENV_DEV
    ),
)
def test_development_adapter_rejects_every_non_development_environment(
    environment: RuntimeEnvironment,
) -> None:
    session = _session()
    _assert_step_up_failure(
        StepUpFailureCode.DEVELOPMENT_ONLY,
        lambda: DevelopmentScriptedStepUpVerifier(
            environment=environment,
            grants=(_grant(session),),
        ),
    )


def test_development_adapter_guards_construction_and_every_operation() -> None:
    session = _session()
    grant = _grant(session)
    _assert_step_up_failure(
        StepUpFailureCode.DEVELOPMENT_ONLY,
        lambda: DevelopmentScriptedStepUpVerifier(
            environment=cast(RuntimeEnvironment, "ENV-DEV"),
            grants=(grant,),
        ),
    )

    adapter = DevelopmentScriptedStepUpVerifier(
        environment=RuntimeEnvironment.ENV_DEV,
        grants=(grant,),
    )
    object.__setattr__(adapter, "_environment", RuntimeEnvironment.CI)
    _assert_step_up_failure(
        StepUpFailureCode.DEVELOPMENT_ONLY,
        lambda: adapter.verify(session=session, now=NOW),
    )


def test_claim_and_adapter_diagnostics_are_redacted_and_not_serializable() -> None:
    session = _session()
    grant = _grant(session)
    adapter = DevelopmentScriptedStepUpVerifier(
        environment=RuntimeEnvironment.ENV_DEV,
        grants=(grant,),
    )
    identifiers = (
        grant.session_id.reveal(),
        grant.issuer.reveal(),
        grant.subject.reveal(),
    )
    rendered = " ".join(
        (
            str(grant),
            repr(grant),
            repr(adapter),
            json.dumps(grant, default=str),
        )
    )
    assert all(identifier not in rendered for identifier in identifiers)
    with pytest.raises(TypeError):
        vars(grant)
    with pytest.raises(TypeError):
        asdict(grant)  # type: ignore[call-overload]
    with pytest.raises(TypeError, match="serialization is not supported"):
        pickle.dumps(grant)
    with pytest.raises(TypeError, match="serialization is not supported"):
        pickle.dumps(adapter)


def test_step_up_failure_is_immutable_and_contains_only_its_code() -> None:
    failure = StepUpFailure(StepUpFailureCode.CLAIM_MISSING)
    with pytest.raises(AttributeError, match="immutable"):
        failure.args = ("replacement",)
    assert str(failure) == StepUpFailureCode.CLAIM_MISSING.value
    assert repr(failure) == (
        "StepUpFailure(code=<StepUpFailureCode.CLAIM_MISSING: 'CLAIM_MISSING'>)"
    )

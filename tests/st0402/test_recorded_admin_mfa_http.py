"""Hostile boundary tests for the disabled and recorded ST-0402 adapters."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import pickle
import socket
from typing import Never
from uuid import UUID

import pytest

from raos.adapters.development_oidc import (
    DevelopmentOidcAdapter,
    InMemoryAuthenticationRepository,
)
from raos.adapters.disabled_admin_mfa_http import (
    DisabledAdminMfaHttpAdapter,
    RecordedAdminMfaDispatch,
)
from raos.adapters.recorded_step_up import (
    RecordedSqliteStepUpRepository,
    RecordedSyntheticMfaVerifier,
)
from raos.application.iam.authentication import AuthenticationService
from raos.application.iam.step_up import DurableStepUpService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authentication import (
    Issuer,
    PrincipalIdentity,
    Session,
    SessionId,
    Subject,
)
from raos.domain.iam.step_up import (
    CriticalStepUpAction,
    CriticalStepUpPolicyRegistry,
    StepUpCommandId,
    StepUpResourceType,
)


NOW = datetime(2026, 8, 25, 8, 0, tzinfo=timezone.utc)
RESOURCE_ID = UUID("018f3e90-7b00-7000-8000-000000000452")
TARGET = "/__recorded__/st-0402/admin-mfa"
ORIGIN = "http://127.0.0.1:48042"


def _raw(label: str) -> bytes:
    return hashlib.sha256(label.encode("ascii")).digest()


class _Entropy:
    def __init__(self, prefix: str) -> None:
        self._prefix = prefix
        self._index = 0

    def token_bytes(self, size: int) -> bytes:
        assert size == 32
        self._index += 1
        return _raw(f"{self._prefix}-{self._index}")


def _command(label: str) -> str:
    return StepUpCommandId.from_bytes(_raw(f"COMMAND-{label}")).reveal()


def _private(path: Path) -> Path:
    path.chmod(0o700)
    return path


def _adapter(
    root: Path,
) -> tuple[
    DisabledAdminMfaHttpAdapter,
    AuthenticationService,
    Session,
    DurableStepUpService,
]:
    principal = PrincipalIdentity(
        issuer=Issuer("https://recorded-mfa-http.invalid"),
        subject=Subject("recorded-mfa-admin"),
        display_name="Recorded MFA administrator",
    )
    session = Session(
        session_id=SessionId.from_bytes(_raw("HTTP-SESSION")),
        principal=principal,
        created_at=NOW - timedelta(minutes=5),
        last_seen_at=NOW - timedelta(minutes=1),
        idle_expires_at=NOW + timedelta(hours=1),
        absolute_expires_at=NOW + timedelta(hours=2),
    )
    authentication_repository = InMemoryAuthenticationRepository(
        environment=RuntimeEnvironment.ENV_DEV
    )
    authentication_repository.create_session(session)
    authentication = AuthenticationService(
        provider=DevelopmentOidcAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            principal=principal,
        ),
        repository=authentication_repository,
        entropy=_Entropy("HTTP-AUTH"),
    )
    service = DurableStepUpService(
        session_service=authentication,
        repository=RecordedSqliteStepUpRepository(
            environment=RuntimeEnvironment.ENV_DEV,
            private_root=root,
        ),
        verifier=RecordedSyntheticMfaVerifier(environment=RuntimeEnvironment.ENV_DEV),
        entropy=_Entropy("HTTP-STEP-UP"),
        policy=CriticalStepUpPolicyRegistry(),
    )
    return (
        DisabledAdminMfaHttpAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            service=service,
        ),
        authentication,
        session,
        service,
    )


def _document(body: dict[str, object]) -> dict[str, object]:
    return {
        "method": "POST",
        "target": TARGET,
        "origin": ORIGIN,
        "content_type": "application/json",
        "body": body,
    }


def _assert_safe(dispatch: RecordedAdminMfaDispatch) -> None:
    headers = {name.lower(): value for name, value in dispatch.response.headers}
    assert "set-cookie" not in headers
    assert "authorization" not in headers
    assert "location" not in headers
    assert headers["cache-control"] == "no-store"
    rendered = json.dumps(dict(dispatch.response.body), sort_keys=True)
    assert "recorded-mfa-admin" not in rendered
    assert "HTTP-SESSION" not in rendered


def test_external_admin_mfa_is_always_disabled_and_never_reflects_input(
    tmp_path: Path,
) -> None:
    adapter, _authentication, session, _service = _adapter(_private(tmp_path))
    secret_like = f"sensitive-{session.session_id.reveal()}"
    dispatch = adapter.dispatch_external(
        {"target": "/admin/mfa", "untrusted": secret_like}
    )
    assert dispatch.result is None
    assert dispatch.response.status == 503
    assert dispatch.response.body["code"] == "MFA_ROUTE_DISABLED"
    rendered = json.dumps(dict(dispatch.response.body), sort_keys=True)
    assert secret_like not in rendered
    assert rendered == (
        '{"code": "MFA_ROUTE_DISABLED", "detail": "No external /admin/mfa '
        'route is registered.", "instance": "urn:raos:recorded:st-0402", '
        '"status": 503, "title": "Admin MFA route is disabled", "type": '
        '"urn:raos:problem:st-0402:mfa-route-disabled"}'
    )
    _assert_safe(dispatch)


def test_loopback_harness_exercises_full_flow_without_delivering_handles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def deny_socket(*_args: object, **_kwargs: object) -> Never:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", deny_socket)
    adapter, _authentication, session, _service = _adapter(_private(tmp_path))
    begun = adapter.dispatch_recorded(
        _document(
            {
                "action": "BEGIN",
                "command_id": _command("BEGIN"),
                "session_id": session.session_id.reveal(),
                "critical_action": CriticalStepUpAction.PUBLISH.value,
                "resource_type": StepUpResourceType.PUBLICATION_SNAPSHOT.value,
                "resource_id": str(RESOURCE_ID),
                "expires_at": (NOW + timedelta(minutes=5))
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z"),
            }
        ),
        now=NOW,
    )
    assert begun.result is not None and begun.result.challenge is not None
    verified = adapter.dispatch_recorded(
        _document(
            {
                "action": "VERIFY",
                "command_id": _command("VERIFY"),
                "session_id": session.session_id.reveal(),
                "challenge_id": begun.result.challenge.challenge_id.reveal(),
                "expires_at": (NOW + timedelta(minutes=4))
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z"),
            }
        ),
        now=NOW + timedelta(minutes=1),
    )
    assert verified.result is not None and verified.result.verification is not None
    issued = adapter.dispatch_recorded(
        _document(
            {
                "action": "ISSUE",
                "command_id": _command("ISSUE"),
                "session_id": session.session_id.reveal(),
                "receipt_id": verified.result.verification.receipt_id.reveal(),
                "expires_at": (NOW + timedelta(minutes=4))
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z"),
            }
        ),
        now=NOW + timedelta(minutes=2),
    )
    assert issued.result is not None and issued.result.grant is not None
    consumed = adapter.dispatch_recorded(
        _document(
            {
                "action": "CONSUME",
                "command_id": _command("CONSUME"),
                "session_id": session.session_id.reveal(),
                "grant_id": issued.result.grant.grant_id.reveal(),
                "critical_action": CriticalStepUpAction.PUBLISH.value,
                "resource_type": StepUpResourceType.PUBLICATION_SNAPSHOT.value,
                "resource_id": str(RESOURCE_ID),
            }
        ),
        now=NOW + timedelta(minutes=3),
    )
    assert consumed.result is not None and consumed.result.authorization is not None
    recovered = adapter.dispatch_recorded(
        _document({"action": "RECOVER", "command_id": _command("CONSUME")}),
        now=NOW + timedelta(minutes=3, seconds=1),
    )
    assert recovered.result == consumed.result

    sensitive_values = (
        session.session_id.reveal(),
        begun.result.challenge.challenge_id.reveal(),
        verified.result.verification.receipt_id.reveal(),
        issued.result.grant.grant_id.reveal(),
        _command("CONSUME"),
    )
    for dispatch in (begun, verified, issued, consumed, recovered):
        _assert_safe(dispatch)
        rendered = json.dumps(dict(dispatch.response.body), sort_keys=True)
        assert dispatch.response.body["external_authority"] is False
        assert dispatch.response.body["route_registered"] is False
        assert dispatch.response.body["delivery"] == "UNSELECTED_NOT_DELIVERED"
        assert all(value not in rendered for value in sensitive_values)
        with pytest.raises(TypeError, match="not serializable"):
            pickle.dumps(dispatch)


@pytest.mark.parametrize(
    ("mutation", "expected_status", "expected_code"),
    (
        ({"method": "GET"}, 400, "CLAIM_MALFORMED"),
        ({"target": "/admin/mfa"}, 400, "CLAIM_MALFORMED"),
        ({"origin": "https://127.0.0.1:48042"}, 503, "DEVELOPMENT_ONLY"),
        ({"origin": "http://localhost:48042"}, 503, "DEVELOPMENT_ONLY"),
        ({"origin": "http://127.0.0.1:80"}, 503, "DEVELOPMENT_ONLY"),
        (
            {"content_type": "application/json; charset=utf-8"},
            400,
            "CLAIM_MALFORMED",
        ),
        ({"extra": "not-allowed"}, 400, "CLAIM_MALFORMED"),
    ),
)
def test_recorded_request_envelope_is_exact_and_sanitized(
    tmp_path: Path,
    mutation: dict[str, object],
    expected_status: int,
    expected_code: str,
) -> None:
    adapter, _authentication, _session, _service = _adapter(_private(tmp_path))
    document = _document({"action": "RECOVER", "command_id": _command("UNKNOWN")})
    document.update(mutation)
    dispatch = adapter.dispatch_recorded(document, now=NOW)
    assert dispatch.result is None
    assert dispatch.response.status == expected_status
    assert dispatch.response.body["code"] == expected_code
    assert "UNKNOWN" not in json.dumps(dict(dispatch.response.body))
    _assert_safe(dispatch)


def test_body_schema_policy_and_session_failures_are_closed_and_sanitized(
    tmp_path: Path,
) -> None:
    adapter, authentication, session, _service = _adapter(_private(tmp_path))
    malformed = adapter.dispatch_recorded(
        _document(
            {
                "action": "BEGIN",
                "command_id": _command("BAD-SCHEMA"),
                "session_id": session.session_id.reveal(),
                "critical_action": CriticalStepUpAction.PUBLISH.value,
                "resource_type": StepUpResourceType.PUBLICATION_SNAPSHOT.value,
                "resource_id": str(RESOURCE_ID),
                "expires_at": (NOW + timedelta(minutes=5))
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z"),
                "unknown": "rejected",
            }
        ),
        now=NOW,
    )
    assert malformed.response.body["code"] == "CLAIM_MALFORMED"

    mismatched = adapter.dispatch_recorded(
        _document(
            {
                "action": "BEGIN",
                "command_id": _command("BAD-POLICY"),
                "session_id": session.session_id.reveal(),
                "critical_action": CriticalStepUpAction.PUBLISH.value,
                "resource_type": StepUpResourceType.SECRET.value,
                "resource_id": str(RESOURCE_ID),
                "expires_at": (NOW + timedelta(minutes=5))
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z"),
            }
        ),
        now=NOW,
    )
    assert mismatched.response.body["code"] == "ACTION_RESOURCE_MISMATCH"

    authentication.revoke_session(session_id=session.session_id, now=NOW)
    rejected = adapter.dispatch_recorded(
        _document(
            {
                "action": "BEGIN",
                "command_id": _command("REVOKED"),
                "session_id": session.session_id.reveal(),
                "critical_action": CriticalStepUpAction.PUBLISH.value,
                "resource_type": StepUpResourceType.PUBLICATION_SNAPSHOT.value,
                "resource_id": str(RESOURCE_ID),
                "expires_at": (NOW + timedelta(minutes=5))
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z"),
            }
        ),
        now=NOW + timedelta(seconds=1),
    )
    assert rejected.result is None
    assert rejected.response.status == 401
    assert rejected.response.body["code"] == "AUTHENTICATION_REJECTED"
    for dispatch in (malformed, mismatched, rejected):
        _assert_safe(dispatch)


def test_non_development_adapter_construction_fails_closed(tmp_path: Path) -> None:
    _adapter_value, _authentication, _session, service = _adapter(_private(tmp_path))
    with pytest.raises(Exception) as caught:
        DisabledAdminMfaHttpAdapter(
            environment=RuntimeEnvironment.STAGING,
            service=service,
        )
    assert "recorded-mfa-admin" not in f"{caught.value!s} {caught.value!r}"

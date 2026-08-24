"""Closed HTTP-shape and loopback integration tests for ST-0401 V2."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import pickle
import socket
from typing import NoReturn

import pytest

from raos.adapters.development_oidc import (
    DevelopmentOidcAdapter,
    InMemoryAuthenticationRepository,
)
from raos.adapters.disabled_admin_auth_http import DisabledAdminAuthHttpAdapter
from raos.application.iam.authentication import AuthenticationService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authentication import Issuer, PrincipalIdentity, Subject


NOW = datetime(2026, 8, 25, 1, 0, tzinfo=timezone.utc)
ORIGIN = "http://127.0.0.1:18401"
TARGET = "/__recorded__/st-0401/admin-auth"


class _Text(str):
    pass


class _Entropy:
    def __init__(self) -> None:
        self._index = 0

    def token_bytes(self, size: int) -> bytes:
        assert size == 32
        self._index += 1
        return hashlib.sha256(f"RECORDED-ST0401-{self._index}".encode()).digest()


def _adapter() -> DisabledAdminAuthHttpAdapter:
    principal = PrincipalIdentity(
        issuer=Issuer("https://recorded.oidc.invalid"),
        subject=Subject("recorded-admin"),
        display_name="Recorded administrator",
    )
    provider = DevelopmentOidcAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        principal=principal,
    )
    service = AuthenticationService(
        provider=provider,
        repository=InMemoryAuthenticationRepository(
            environment=RuntimeEnvironment.ENV_DEV
        ),
        entropy=_Entropy(),
    )
    return DisabledAdminAuthHttpAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        service=service,
        driver=provider,
    )


def _document(body: dict[str, object]) -> dict[str, object]:
    return {
        "method": "POST",
        "target": TARGET,
        "origin": ORIGIN,
        "content_type": "application/json",
        "body": body,
    }


def _render_response(result: object) -> str:
    response = getattr(result, "response")
    return json.dumps(
        {
            "status": response.status,
            "headers": response.headers,
            "body": dict(response.body),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def test_external_dispatch_is_permanently_disabled_and_non_reflecting() -> None:
    canary = "SYNTHETIC-RAW-AUTHENTICATION-CANARY"
    result = _adapter().dispatch_external({"untrusted": canary})

    assert result.response.status == 503
    assert result.response.body["code"] == "AUTH_TRANSPORT_DISABLED"
    assert canary not in _render_response(result)
    assert result.callback is None
    assert result.session_id is None


def test_recorded_loopback_flow_rotates_revokes_and_never_delivers_a_token() -> None:
    adapter = _adapter()
    begin = adapter.dispatch_recorded(_document({"action": "BEGIN"}), now=NOW)
    assert begin.response.status == 202
    assert begin.callback is not None
    callback = begin.callback

    completed = adapter.dispatch_recorded(
        _document(
            {
                "action": "CALLBACK",
                "state": callback.state.reveal(),
                "code": callback.code.reveal(),
            }
        ),
        now=NOW,
    )
    assert completed.response.status == 200
    assert completed.session_id is not None
    first = completed.session_id

    active = adapter.dispatch_recorded(
        _document({"action": "REQUIRE", "session_id": first.reveal()}),
        now=NOW + timedelta(minutes=1),
    )
    assert active.response.body["outcome"] == "RECORDED_SESSION_ACTIVE"

    rotated = adapter.dispatch_recorded(
        _document({"action": "ROTATE", "session_id": first.reveal()}),
        now=NOW + timedelta(minutes=2),
    )
    assert rotated.session_id is not None
    assert rotated.session_id != first
    old_replay = adapter.dispatch_recorded(
        _document({"action": "REQUIRE", "session_id": first.reveal()}),
        now=NOW + timedelta(minutes=2),
    )
    assert old_replay.response.status == 401
    assert old_replay.response.body["code"] == "SESSION_REVOKED"

    successor = rotated.session_id
    revoked = adapter.dispatch_recorded(
        _document({"action": "REVOKE", "session_id": successor.reveal()}),
        now=NOW + timedelta(minutes=3),
    )
    assert revoked.response.body["outcome"] == "RECORDED_SESSION_REVOKED"
    denied = adapter.dispatch_recorded(
        _document({"action": "REQUIRE", "session_id": successor.reveal()}),
        now=NOW + timedelta(minutes=3),
    )
    assert denied.response.status == 401
    assert denied.response.body["code"] == "SESSION_REVOKED"

    all_responses = (begin, completed, active, rotated, old_replay, revoked, denied)
    rendered = " ".join(_render_response(result) for result in all_responses)
    secrets = (callback.state.reveal(), callback.code.reveal(), first.reveal())
    assert all(secret not in rendered for secret in secrets)
    assert all(
        name.lower() not in {"set-cookie", "authorization", "location"}
        for result in all_responses
        for name, _value in result.response.headers
    )
    assert all(
        result.response.body.get("delivery") == "UNSELECTED_NOT_DELIVERED"
        for result in (begin, completed, active, rotated, revoked)
    )


@pytest.mark.parametrize(
    "mutation",
    (
        {"extra": True},
        {"method": "GET"},
        {"target": "/admin/sign-in"},
        {"origin": "http://localhost:18401"},
        {"origin": "https://127.0.0.1:18401"},
        {"content_type": "text/plain"},
    ),
)
def test_unknown_fields_routes_origins_and_media_types_fail_closed(
    mutation: dict[str, object],
) -> None:
    document = _document({"action": "BEGIN"})
    document.update(mutation)
    result = _adapter().dispatch_recorded(document, now=NOW)
    assert result.response.status in {400, 503}
    assert result.callback is None
    assert result.session_id is None


@pytest.mark.parametrize(
    "body",
    (
        {},
        {"action": "UNKNOWN"},
        {"action": []},
        {"action": "BEGIN", "state": "unexpected"},
        {"action": "CALLBACK"},
        {"action": "REQUIRE"},
        {"action": "REVOKE", "session_id": "short"},
    ),
)
def test_unknown_or_incomplete_operation_shapes_are_rfc9457_problems(
    body: dict[str, object],
) -> None:
    result = _adapter().dispatch_recorded(_document(body), now=NOW)
    assert result.response.status == 400
    assert set(result.response.body) == {
        "type",
        "title",
        "status",
        "detail",
        "instance",
        "code",
    }
    assert result.response.body["code"] == "MALFORMED_INPUT"
    assert dict(result.response.body)["status"] == result.response.status


def test_request_shape_rejects_value_subclasses_instead_of_coercing_them() -> None:
    document = _document({"action": "BEGIN"})
    document["method"] = _Text("POST")
    result = _adapter().dispatch_recorded(document, now=NOW)
    assert result.response.status == 400
    assert result.response.body["code"] == "MALFORMED_INPUT"


def test_recorded_dispatch_uses_no_socket_and_is_nonserializable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def deny_network(*args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", deny_network)
    result = _adapter().dispatch_recorded(_document({"action": "BEGIN"}), now=NOW)
    assert result.response.status == 202
    with pytest.raises(TypeError, match="not serializable"):
        pickle.dumps(result)
    rendered = f"{result!s} {result!r}"
    assert result.callback is not None
    assert result.callback.state.reveal() not in rendered
    assert result.callback.code.reveal() not in rendered

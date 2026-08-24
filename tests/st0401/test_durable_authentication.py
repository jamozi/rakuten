"""Durability, atomicity, crash recovery, and corruption tests for ST-0401."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import sqlite3
from threading import Barrier, Thread

import pytest

from raos.adapters.development_oidc import DevelopmentOidcAdapter
from raos.adapters.disabled_admin_auth_http import DisabledAdminAuthHttpAdapter
from raos.adapters.recorded_authentication import (
    RecordedCommitFault,
    RecordedSqliteAuthenticationRepository,
)
from raos.application.iam.authentication import AuthenticationService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authentication import (
    AuthenticationFailure,
    AuthenticationFailureCode,
    Issuer,
    PrincipalIdentity,
    RedirectUri,
    Session,
    Subject,
)


NOW = datetime(2026, 8, 25, 2, 0, tzinfo=timezone.utc)


class _Entropy:
    def __init__(self, prefix: str) -> None:
        self._prefix = prefix
        self._index = 0

    def token_bytes(self, size: int) -> bytes:
        assert size == 32
        self._index += 1
        return hashlib.sha256(f"{self._prefix}-{self._index}".encode()).digest()


def _private_root(path: Path) -> Path:
    path.chmod(0o700)
    return path


def _provider() -> DevelopmentOidcAdapter:
    return DevelopmentOidcAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        principal=PrincipalIdentity(
            issuer=Issuer("https://recorded.oidc.invalid"),
            subject=Subject("durable-admin"),
            display_name="Durable recorded administrator",
        ),
    )


def _repository(
    root: Path, *, fault: RecordedCommitFault | None = None
) -> RecordedSqliteAuthenticationRepository:
    return RecordedSqliteAuthenticationRepository(
        environment=RuntimeEnvironment.ENV_DEV,
        private_root=root,
        fault_once_at=fault,
    )


def _service(
    repository: RecordedSqliteAuthenticationRepository, prefix: str
) -> AuthenticationService:
    return AuthenticationService(
        provider=_provider(),
        repository=repository,
        entropy=_Entropy(prefix),
    )


def _http_adapter(
    repository: RecordedSqliteAuthenticationRepository, prefix: str
) -> DisabledAdminAuthHttpAdapter:
    provider = _provider()
    return DisabledAdminAuthHttpAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        service=AuthenticationService(
            provider=provider,
            repository=repository,
            entropy=_Entropy(prefix),
        ),
        driver=provider,
    )


def _http_document(action: str, session: Session) -> dict[str, object]:
    return {
        "method": "POST",
        "target": "/__recorded__/st-0401/admin-auth",
        "origin": "http://127.0.0.1:18401",
        "content_type": "application/json",
        "body": {"action": action, "session_id": session.session_id.reveal()},
    }


def _establish(root: Path) -> tuple[Session, AuthenticationService]:
    repository = _repository(root)
    provider = _provider()
    service = AuthenticationService(
        provider=provider,
        repository=repository,
        entropy=_Entropy("ESTABLISH"),
    )
    request = service.begin_authorization(
        redirect_uri=RedirectUri(
            "http://127.0.0.1:18401/__recorded__/st-0401/admin-auth"
        ),
        now=NOW,
    )
    session = service.complete_authorization(
        callback=provider.authorize(request=request, now=NOW),
        now=NOW,
    )
    return session, service


def _failure_code(operation: object) -> AuthenticationFailureCode:
    assert callable(operation)
    with pytest.raises(AuthenticationFailure) as caught:
        operation()
    return caught.value.code


def test_repository_survives_restart_with_owner_private_storage(tmp_path: Path) -> None:
    root = _private_root(tmp_path)
    session, _service_one = _establish(root)
    database = root / "st0401-recorded-auth.sqlite3"
    assert database.is_file()
    assert (database.stat().st_mode & 0o777) == 0o600

    reopened = _service(_repository(root), "REOPENED")
    loaded = reopened.require_session(session_id=session.session_id, now=NOW)
    assert loaded.session_id == session.session_id
    assert loaded.principal == session.principal
    rendered = f"{_repository(root)!s} {_repository(root)!r}"
    assert str(root) not in rendered
    assert session.session_id.reveal() not in rendered


def test_before_commit_crash_rolls_back_rotation_and_recovery_returns_predecessor(
    tmp_path: Path,
) -> None:
    root = _private_root(tmp_path)
    predecessor, _ = _establish(root)
    crashing = _service(
        _repository(root, fault=RecordedCommitFault.BEFORE_COMMIT),
        "BEFORE-COMMIT",
    )
    code = _failure_code(
        lambda: crashing.rotate_session(
            session_id=predecessor.session_id,
            now=NOW + timedelta(minutes=1),
        )
    )
    assert code is AuthenticationFailureCode.STORAGE_FAILURE

    recovered_service = _service(_repository(root), "RECOVER-BEFORE")
    recovered = recovered_service.recover_session_rotation(
        predecessor_id=predecessor.session_id,
        now=NOW + timedelta(minutes=1),
    )
    assert recovered.session_id == predecessor.session_id
    assert recovered.revoked_at is None


def test_after_commit_crash_recovers_the_single_atomic_successor(
    tmp_path: Path,
) -> None:
    root = _private_root(tmp_path)
    predecessor, _ = _establish(root)
    crashing = _service(
        _repository(root, fault=RecordedCommitFault.AFTER_COMMIT),
        "AFTER-COMMIT",
    )
    code = _failure_code(
        lambda: crashing.rotate_session(
            session_id=predecessor.session_id,
            now=NOW + timedelta(minutes=1),
        )
    )
    assert code is AuthenticationFailureCode.STORAGE_COMMIT_UNKNOWN

    recovered_service = _service(_repository(root), "RECOVER-AFTER")
    recovered = recovered_service.recover_session_rotation(
        predecessor_id=predecessor.session_id,
        now=NOW + timedelta(minutes=1),
    )
    assert recovered.session_id != predecessor.session_id
    assert recovered.rotated_from == predecessor.session_id
    assert recovered.revoked_at is None
    assert (
        _failure_code(
            lambda: recovered_service.require_session(
                session_id=predecessor.session_id,
                now=NOW + timedelta(minutes=1),
            )
        )
        is AuthenticationFailureCode.SESSION_REVOKED
    )


def test_disabled_http_bridge_reports_unknown_commit_then_recovers_read_only(
    tmp_path: Path,
) -> None:
    root = _private_root(tmp_path)
    predecessor, _ = _establish(root)
    crashing = _http_adapter(
        _repository(root, fault=RecordedCommitFault.AFTER_COMMIT),
        "HTTP-CRASH",
    )

    ambiguous = crashing.dispatch_recorded(
        _http_document("ROTATE", predecessor),
        now=NOW + timedelta(minutes=1),
    )
    assert ambiguous.response.status == 503
    assert ambiguous.response.body["code"] == "STORAGE_COMMIT_UNKNOWN"
    assert ambiguous.session_id is None

    recovered = _http_adapter(_repository(root), "HTTP-RECOVER").dispatch_recorded(
        _http_document("RECOVER_ROTATION", predecessor),
        now=NOW + timedelta(minutes=1),
    )
    assert recovered.response.status == 200
    assert recovered.response.body["outcome"] == "RECORDED_ROTATION_RECOVERED"
    assert recovered.session_id is not None
    assert recovered.session_id != predecessor.session_id


def test_concurrent_rotation_has_one_atomic_winner_and_no_partial_state(
    tmp_path: Path,
) -> None:
    root = _private_root(tmp_path)
    predecessor, _ = _establish(root)
    barrier = Barrier(2)
    outcomes: list[tuple[str, object]] = []

    def rotate(prefix: str) -> None:
        service = _service(_repository(root), prefix)
        barrier.wait()
        try:
            outcomes.append(
                (
                    "SUCCESS",
                    service.rotate_session(
                        session_id=predecessor.session_id,
                        now=NOW + timedelta(minutes=1),
                    ),
                )
            )
        except AuthenticationFailure as error:
            outcomes.append(("FAILURE", error.code))

    threads = (
        Thread(target=rotate, args=("RACE-A",)),
        Thread(target=rotate, args=("RACE-B",)),
    )
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    successes = [value for kind, value in outcomes if kind == "SUCCESS"]
    failures = [value for kind, value in outcomes if kind == "FAILURE"]
    assert len(successes) == 1
    assert failures == [AuthenticationFailureCode.SESSION_CONFLICT]
    recovered = _service(_repository(root), "RACE-RECOVER").recover_session_rotation(
        predecessor_id=predecessor.session_id,
        now=NOW + timedelta(minutes=1),
    )
    assert recovered == successes[0]


def test_expired_authorization_is_durably_consumed_and_cannot_replay(
    tmp_path: Path,
) -> None:
    root = _private_root(tmp_path)
    repository = _repository(root)
    provider = _provider()
    service = AuthenticationService(
        provider=provider,
        repository=repository,
        entropy=_Entropy("EXPIRED"),
        authorization_lifetime=timedelta(seconds=30),
    )
    request = service.begin_authorization(
        redirect_uri=RedirectUri(
            "http://127.0.0.1:18401/__recorded__/st-0401/admin-auth"
        ),
        now=NOW,
    )
    callback = provider.authorize(request=request, now=NOW)
    assert (
        _failure_code(
            lambda: service.complete_authorization(
                callback=callback,
                now=NOW + timedelta(seconds=30),
            )
        )
        is AuthenticationFailureCode.AUTHORIZATION_EXPIRED
    )
    reopened = _service(_repository(root), "EXPIRED-REOPEN")
    assert (
        _failure_code(
            lambda: reopened.complete_authorization(
                callback=callback,
                now=NOW + timedelta(seconds=31),
            )
        )
        is AuthenticationFailureCode.AUTHORIZATION_REPLAY
    )


def test_tampered_record_fails_closed_without_exposing_values(tmp_path: Path) -> None:
    root = _private_root(tmp_path)
    session, _ = _establish(root)
    canary = "SYNTHETIC-TAMPERED-SUBJECT-CANARY"
    connection = sqlite3.connect(root / "st0401-recorded-auth.sqlite3")
    try:
        connection.execute(
            "UPDATE recorded_session SET subject = ? WHERE session_fingerprint = ?",
            (canary, session.session_id.fingerprint()),
        )
        connection.commit()
    finally:
        connection.close()

    repository = _repository(root)
    with pytest.raises(AuthenticationFailure) as caught:
        repository.load_session(session.session_id)
    assert caught.value.code is AuthenticationFailureCode.STORAGE_FAILURE
    assert canary not in f"{caught.value!s} {caught.value!r} {caught.value.args!r}"


def test_storage_rejects_non_private_root_symlink_and_non_dev(tmp_path: Path) -> None:
    public_root = tmp_path / "public"
    public_root.mkdir(mode=0o755)
    public_root.chmod(0o755)
    assert (
        _failure_code(
            lambda: RecordedSqliteAuthenticationRepository(
                environment=RuntimeEnvironment.ENV_DEV,
                private_root=public_root,
            )
        )
        is AuthenticationFailureCode.STORAGE_FAILURE
    )

    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    private.chmod(0o700)
    link = tmp_path / "private-link"
    os.symlink(private, link)
    assert (
        _failure_code(
            lambda: RecordedSqliteAuthenticationRepository(
                environment=RuntimeEnvironment.ENV_DEV,
                private_root=link,
            )
        )
        is AuthenticationFailureCode.STORAGE_FAILURE
    )
    assert (
        _failure_code(
            lambda: RecordedSqliteAuthenticationRepository(
                environment=RuntimeEnvironment.STAGING,
                private_root=private,
            )
        )
        is AuthenticationFailureCode.DEVELOPMENT_ONLY
    )

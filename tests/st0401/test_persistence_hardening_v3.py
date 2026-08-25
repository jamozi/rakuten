"""Hostile persistence and rollback checks for the ST-0401 V2 repository."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import sqlite3

import pytest

from raos.adapters.development_oidc import DevelopmentOidcAdapter
from raos.adapters.recorded_authentication import (
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


NOW = datetime(2026, 8, 25, 4, 0, tzinfo=timezone.utc)
DATABASE = "st0401-recorded-auth.sqlite3"


class _Entropy:
    def __init__(self) -> None:
        self._index = 0

    def token_bytes(self, size: int) -> bytes:
        assert size == 32
        self._index += 1
        return hashlib.sha256(f"ST0401-V3-{self._index}".encode()).digest()


def _root(path: Path) -> Path:
    path.mkdir(mode=0o700, exist_ok=True)
    path.chmod(0o700)
    return path


def _repository(root: Path) -> RecordedSqliteAuthenticationRepository:
    return RecordedSqliteAuthenticationRepository(
        environment=RuntimeEnvironment.ENV_DEV,
        private_root=root,
    )


def _establish(root: Path) -> tuple[RecordedSqliteAuthenticationRepository, Session]:
    repository = _repository(root)
    provider = DevelopmentOidcAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        principal=PrincipalIdentity(
            issuer=Issuer("https://hardening.oidc.invalid"),
            subject=Subject("recorded-hardening"),
            display_name="Recorded hardening administrator",
        ),
    )
    service = AuthenticationService(
        provider=provider,
        repository=repository,
        entropy=_Entropy(),
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
    return repository, session


def _storage_failure(operation: object) -> None:
    assert callable(operation)
    with pytest.raises(AuthenticationFailure) as caught:
        operation()
    assert caught.value.code is AuthenticationFailureCode.STORAGE_FAILURE


def _bypass_update_trigger(
    database: Path,
    *,
    trigger: str,
    statement: str,
    parameters: tuple[object, ...],
) -> None:
    connection = sqlite3.connect(database)
    try:
        trigger_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
            (trigger,),
        ).fetchone()
        assert trigger_sql is not None and type(trigger_sql[0]) is str
        connection.execute(f"DROP TRIGGER {trigger}")
        connection.execute(statement, parameters)
        connection.execute(trigger_sql[0])
        connection.commit()
    finally:
        connection.close()


@pytest.mark.parametrize("kind", ("EMPTY", "PARTIAL", "FOREIGN"))
def test_preexisting_private_file_is_never_initialized(
    kind: str, tmp_path: Path
) -> None:
    root = _root(tmp_path / kind.lower())
    database = root / DATABASE
    if kind == "EMPTY":
        database.touch(mode=0o600)
    else:
        connection = sqlite3.connect(database)
        try:
            if kind == "PARTIAL":
                connection.execute("CREATE TABLE recorded_auth_metadata_v2(x TEXT)")
            else:
                connection.execute("CREATE TABLE foreign_owner_data(x TEXT)")
            connection.commit()
        finally:
            connection.close()
        database.chmod(0o600)
    before = database.read_bytes()

    _storage_failure(lambda: _repository(root))

    assert database.read_bytes() == before


def test_schema_is_exact_strict_append_only_and_foreign_keyed(tmp_path: Path) -> None:
    root = _root(tmp_path / "schema")
    repository = _repository(root)
    connection = sqlite3.connect(repository.database_path)
    try:
        assert connection.execute("PRAGMA application_id").fetchone() == (1380400102,)
        assert connection.execute("PRAGMA user_version").fetchone() == (2,)
        table_list = {
            row[1]: row[5]
            for row in connection.execute("PRAGMA table_list").fetchall()
            if str(row[1]).startswith("recorded_")
        }
        assert table_list == {
            "recorded_auth_metadata_v2": 1,
            "recorded_auth_command_v2": 1,
            "recorded_authorization_revision_v2": 1,
            "recorded_session_revision_v2": 1,
        }
        triggers = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            ).fetchall()
        }
        assert len(triggers) == 8
        assert connection.execute(
            "PRAGMA foreign_key_list(recorded_session_revision_v2)"
        ).fetchall()
    finally:
        connection.close()


def test_deleted_history_is_detected_after_trigger_bypass(tmp_path: Path) -> None:
    root = _root(tmp_path / "deleted-history")
    repository, session = _establish(root)
    connection = sqlite3.connect(repository.database_path)
    trigger = "recorded_session_revision_v2_no_delete"
    try:
        statement = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
            (trigger,),
        ).fetchone()
        assert statement is not None and type(statement[0]) is str
        connection.execute(f"DROP TRIGGER {trigger}")
        connection.execute(
            "DELETE FROM recorded_session_revision_v2 "
            "WHERE session_fingerprint = ? AND revision = 1",
            (session.session_id.fingerprint(),),
        )
        connection.execute(statement[0])
        connection.commit()
    finally:
        connection.close()

    _storage_failure(lambda: repository.load_session(session.session_id))


@pytest.mark.parametrize(
    "mutation",
    ("NONCANONICAL_TIME", "REDUNDANT_FINGERPRINT", "NONCANONICAL_COMMAND_JSON"),
)
def test_rebound_or_noncanonical_material_fails_closed(
    mutation: str, tmp_path: Path
) -> None:
    root = _root(tmp_path / mutation.lower())
    repository, session = _establish(root)
    if mutation == "NONCANONICAL_TIME":
        current = sqlite3.connect(repository.database_path)
        try:
            timestamp = current.execute(
                "SELECT last_seen_at FROM recorded_session_revision_v2 "
                "WHERE session_fingerprint = ?",
                (session.session_id.fingerprint(),),
            ).fetchone()
            assert timestamp is not None and str(timestamp[0]).endswith("Z")
        finally:
            current.close()
        _bypass_update_trigger(
            repository.database_path,
            trigger="recorded_session_revision_v2_no_update",
            statement=(
                "UPDATE recorded_session_revision_v2 SET last_seen_at = ? "
                "WHERE session_fingerprint = ?"
            ),
            parameters=(
                str(timestamp[0])[:-1] + "+00:00",
                session.session_id.fingerprint(),
            ),
        )
    elif mutation == "REDUNDANT_FINGERPRINT":
        _bypass_update_trigger(
            repository.database_path,
            trigger="recorded_session_revision_v2_no_update",
            statement=(
                "UPDATE recorded_session_revision_v2 SET session_fingerprint = ? "
                "WHERE session_fingerprint = ?"
            ),
            parameters=("a" * 64, session.session_id.fingerprint()),
        )
    else:
        _bypass_update_trigger(
            repository.database_path,
            trigger="recorded_auth_command_v2_no_update",
            statement=(
                "UPDATE recorded_auth_command_v2 SET intent_bytes = ? "
                "WHERE sequence = (SELECT MAX(sequence) "
                "FROM recorded_auth_command_v2)"
            ),
            parameters=(b"{ }",),
        )

    _storage_failure(lambda: repository.load_session(session.session_id))


def test_same_inode_valid_snapshot_rollback_is_process_detected(tmp_path: Path) -> None:
    root = _root(tmp_path / "rollback")
    repository, session = _establish(root)
    database = repository.database_path
    old_snapshot = database.read_bytes()
    service = AuthenticationService(
        provider=DevelopmentOidcAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            principal=session.principal,
        ),
        repository=repository,
        entropy=_Entropy(),
    )
    service.require_session(
        session_id=session.session_id,
        now=NOW + timedelta(minutes=1),
    )
    assert database.read_bytes() != old_snapshot
    identity = database.stat().st_ino
    database.write_bytes(old_snapshot)
    assert database.stat().st_ino == identity

    _storage_failure(lambda: repository.load_session(session.session_id))
    _storage_failure(lambda: _repository(root))


def test_inode_replacement_is_rejected_by_existing_and_new_instances(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path / "replacement")
    repository, session = _establish(root)
    database = repository.database_path
    original_identity = database.stat().st_ino
    replacement = root / "replacement.sqlite3"
    replacement.write_bytes(database.read_bytes())
    replacement.chmod(0o600)
    os.replace(replacement, database)
    assert database.stat().st_ino != original_identity

    _storage_failure(lambda: repository.load_session(session.session_id))
    _storage_failure(lambda: _repository(root))


def test_precommit_sqlite_failure_is_not_misclassified_as_unknown_commit(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path / "precommit")
    repository = _repository(root)

    def fail_before_commit(_connection: sqlite3.Connection) -> None:
        raise sqlite3.OperationalError("synthetic precommit failure")

    _storage_failure(lambda: repository._write(fail_before_commit))

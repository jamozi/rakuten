"""Runner target, ordering, lifecycle, and error-hygiene tests."""

from __future__ import annotations

import os
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import pytest

from conftest import REPOSITORY_ROOT
from raos.migrations import (
    CatalogError,
    DatabaseTarget,
    MigrationError,
    MigrationRunner,
)
from raos.migrations import catalog
from raos.migrations import runner


class _FakeConnection:
    dialect = type("Dialect", (), {"name": "postgresql"})()

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.invalidated = False
        self.connection = type("ConnectionProxy", (), {"driver_connection": object()})()

    def in_transaction(self) -> bool:
        return False

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _FakeEngine:
    def __init__(self, connection: _FakeConnection) -> None:
        self.connection_value = connection
        self.disposed = False

    def connect(self):
        return nullcontext(self.connection_value)

    def dispose(self) -> None:
        self.disposed = True


def test_repository_graph_and_sources_verify_offline() -> None:
    verification = runner.verify_repository(REPOSITORY_ROOT)
    assert verification.runtime_sources[0].sha256 == (
        catalog.ALEMBIC_RUNTIME_SPECS[0].sha256
    )
    assert verification.revision_sources[0].sha256 == catalog.REVISION_SPECS[0].sha256
    assert len(verification.checkpoint_sources) == 18


def test_repository_verification_sanitizes_snapshot_runtime_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_snapshot(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise OSError("private-snapshot-canary")

    monkeypatch.setattr(runner.tempfile, "TemporaryDirectory", fail_snapshot)
    with pytest.raises(MigrationError) as raised:
        runner.verify_repository(REPOSITORY_ROOT)
    assert raised.value.code is runner.MigrationErrorCode.GRAPH_MISMATCH
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert "private-snapshot-canary" not in str(raised.value)


def test_source_verification_precedes_engine_factory(
    database_target: DatabaseTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fail(_: Path):
        calls.append("verify")
        raise CatalogError(catalog.CatalogErrorCode.SOURCE_DIGEST_MISMATCH)

    def engine_factory(_: DatabaseTarget):
        calls.append("connect")
        raise AssertionError("connection factory must not run")

    monkeypatch.setattr(runner, "verify_repository", fail)
    instance = MigrationRunner(
        REPOSITORY_ROOT,
        database_target,
        engine_factory=engine_factory,
    )
    with pytest.raises(CatalogError):
        instance.status()
    assert calls == ["verify"]


@pytest.mark.parametrize(
    ("field", "value", "code"),
    (
        ("host", "database.example", runner.MigrationErrorCode.INVALID_TARGET),
        ("port", 80, runner.MigrationErrorCode.INVALID_TARGET),
        ("port", True, runner.MigrationErrorCode.INVALID_TARGET),
        ("database", "Bad-Name", runner.MigrationErrorCode.INVALID_TARGET),
        ("user", "role;drop", runner.MigrationErrorCode.INVALID_TARGET),
        (
            "password_file",
            Path("relative"),
            runner.MigrationErrorCode.INVALID_PASSWORD_FILE,
        ),
    ),
)
def test_target_validation_fails_closed(
    database_target: DatabaseTarget,
    field: str,
    value: object,
    code: runner.MigrationErrorCode,
) -> None:
    values = {
        "environment": database_target.environment,
        "host": database_target.host,
        "port": database_target.port,
        "database": database_target.database,
        "user": database_target.user,
        "password_file": database_target.password_file,
    }
    values[field] = value
    mutated = DatabaseTarget(**values)  # type: ignore[arg-type]

    with pytest.raises(MigrationError) as raised:
        runner._validate_target(mutated)
    assert raised.value.code is code


@pytest.mark.parametrize("ambient", ("PGPASSWORD", "PGSERVICE", "PGOPTIONS", "PGHOST"))
def test_ambient_libpq_configuration_is_rejected(
    database_target: DatabaseTarget,
    ambient: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ambient, "private-canary")
    with pytest.raises(MigrationError) as raised:
        runner._validate_target(database_target)
    assert raised.value.code is runner.MigrationErrorCode.AMBIENT_CONFIGURATION
    assert "private-canary" not in str(raised.value)


def test_password_file_requires_owner_mode_and_safe_content(
    password_file: Path,
) -> None:
    assert runner._read_password_file(password_file) == "local-test-password"

    password_file.chmod(0o644)
    with pytest.raises(MigrationError) as raised:
        runner._read_password_file(password_file)
    assert raised.value.code is runner.MigrationErrorCode.INVALID_PASSWORD_FILE


@pytest.mark.parametrize("content", (b"", b"two\nlines\n", b"bad\x00value", b"\xff"))
def test_password_file_rejects_empty_control_or_non_utf8(
    tmp_path: Path,
    content: bytes,
) -> None:
    path = tmp_path / "password"
    path.write_bytes(content)
    path.chmod(0o600)

    with pytest.raises(MigrationError) as raised:
        runner._read_password_file(path)
    assert raised.value.code is runner.MigrationErrorCode.INVALID_PASSWORD_FILE


def test_password_file_rejects_symlink(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.write_text("private-canary", encoding="utf-8")
    outside.chmod(0o600)
    linked = tmp_path / "linked"
    linked.symlink_to(outside)

    with pytest.raises(MigrationError) as raised:
        runner._read_password_file(linked)
    assert raised.value.code is runner.MigrationErrorCode.INVALID_PASSWORD_FILE
    assert "private-canary" not in str(raised.value)


def test_password_file_rejects_symlink_ancestor(tmp_path: Path) -> None:
    physical = tmp_path / "physical"
    physical.mkdir()
    password = physical / "password"
    password.write_text("private-canary", encoding="utf-8")
    password.chmod(0o600)
    linked = tmp_path / "linked"
    linked.symlink_to(physical, target_is_directory=True)

    with pytest.raises(MigrationError) as raised:
        runner._read_password_file(linked / "password")
    assert raised.value.code is runner.MigrationErrorCode.INVALID_PASSWORD_FILE
    assert raised.value.__context__ is None


class _ScalarResult:
    def __init__(self, value: object) -> None:
        self.value = value

    def scalar_one(self) -> object:
        return self.value


class _WrongVersionConnection(_FakeConnection):
    def exec_driver_sql(self, statement: str) -> _ScalarResult:
        assert statement == "SHOW server_version_num"
        return _ScalarResult("180003")


def test_server_version_guard_rejects_other_postgresql_18_patch() -> None:
    connection = _WrongVersionConnection()

    with pytest.raises(MigrationError) as raised:
        MigrationRunner._prepare_and_lock(connection)  # type: ignore[arg-type]
    assert raised.value.code is runner.MigrationErrorCode.SERVER_VERSION_MISMATCH
    assert raised.value.__context__ is None


class _InvalidatedConnection:
    closed = False
    invalidated = True

    @property
    def connection(self) -> object:
        raise AssertionError("invalidated connection must never be revalidated")

    def in_transaction(self) -> bool:
        return False


def test_session_guard_rejects_invalidation_without_triggering_reconnect() -> None:
    identity = runner._LockedSession(123, object())

    with pytest.raises(MigrationError) as raised:
        MigrationRunner._assert_same_session(  # type: ignore[arg-type]
            _InvalidatedConnection(), identity
        )
    assert raised.value.code is runner.MigrationErrorCode.SESSION_CLEANUP_FAILED
    assert raised.value.__context__ is None


class _ReplacementConnection:
    closed = False
    invalidated = False

    def __init__(self, driver_connection: object) -> None:
        self.connection = type(
            "ConnectionProxy", (), {"driver_connection": driver_connection}
        )()
        self.execute_calls = 0

    def in_transaction(self) -> bool:
        return False

    def execute(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        self.execute_calls += 1
        raise AssertionError("replacement session must execute no SQL")


def test_session_guard_and_unlock_reject_replacement_before_any_sql() -> None:
    original_driver = object()
    connection = _ReplacementConnection(object())
    identity = runner._LockedSession(123, original_driver)

    for operation in (
        MigrationRunner._assert_same_session,
        MigrationRunner._unlock,
    ):
        with pytest.raises(MigrationError) as raised:
            operation(connection, identity)  # type: ignore[arg-type]
        assert raised.value.code is runner.MigrationErrorCode.SESSION_CLEANUP_FAILED
    assert connection.execute_calls == 0


def test_default_engine_url_contains_no_target_or_secret(
    database_target: DatabaseTarget,
) -> None:
    engine = runner._default_engine_factory(database_target)
    try:
        rendered = str(engine.url)
        assert rendered == "postgresql+psycopg://"
        assert database_target.database not in rendered
        assert database_target.user not in rendered
        assert os.fspath(database_target.password_file) not in rendered
    finally:
        engine.dispose()


def test_engine_rechecks_live_ambient_pg_before_libpq(
    database_target: DatabaseTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connect_calls: list[str] = []
    engine = runner._default_engine_factory(database_target)
    monkeypatch.setattr(
        runner.psycopg,
        "connect",
        lambda **kwargs: connect_calls.append(str(kwargs)),
    )
    monkeypatch.setenv("PGSERVICE", "private-canary")
    try:
        with pytest.raises(MigrationError) as raised:
            engine.connect()
        assert raised.value.code is runner.MigrationErrorCode.AMBIENT_CONFIGURATION
        assert "private-canary" not in str(raised.value)
        assert connect_calls == []
    finally:
        engine.dispose()


def test_history_state_machine_supports_future_revision_failure_and_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = catalog.REVISION_SPECS[0]
    future = catalog.RevisionSpec(
        revision="202608030002",
        down_revision=root.revision,
        story_id="ST-0302",
        relative_path=Path("migrations/versions/202608030002_future.py"),
        sha256="1" * 64,
        runner_version="1.1.0",
        server_version_num=180005,
    )
    monkeypatch.setattr(runner, "REVISION_SPECS", (root, future))
    root_attempt = "00000000-0000-4000-8000-000000000001"
    failed_attempt = "00000000-0000-4000-8000-000000000002"
    recovered_attempt = "00000000-0000-4000-8000-000000000003"

    def row(
        event_id: int,
        attempt_id: str,
        spec: catalog.RevisionSpec,
        status: str,
        error_code: str | None = None,
    ) -> tuple[object, ...]:
        return (
            event_id,
            attempt_id,
            spec.revision,
            spec.story_id,
            "UPGRADE",
            status,
            spec.sha256,
            spec.runner_version,
            spec.server_version_num,
            error_code,
        )

    rows = [
        row(1, root_attempt, root, "SUCCEEDED"),
        row(2, failed_attempt, future, "STARTED"),
    ]
    assert runner._analyze_history(
        rows, root.revision, allow_open=True
    ) == runner._OpenAttempt(failed_attempt, 1)

    rows.append(
        row(
            3,
            failed_attempt,
            future,
            "FAILED",
            "INTERRUPTED_BEFORE_TERMINAL",
        )
    )
    assert runner._analyze_history(rows, root.revision, allow_open=False) is None
    rows.extend(
        [
            row(4, recovered_attempt, future, "STARTED"),
            row(5, recovered_attempt, future, "SUCCEEDED"),
        ]
    )
    assert runner._analyze_history(rows, future.revision, allow_open=False) is None

    for field_index, invalid_value in ((7, "9.9.9"), (8, 180004)):
        invalid = list(rows)
        changed = list(invalid[-1])
        changed[field_index] = invalid_value
        invalid[-1] = tuple(changed)
        with pytest.raises(MigrationError) as raised:
            runner._analyze_history(
                invalid,
                future.revision,
                allow_open=False,
            )
        assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID

    with pytest.raises(MigrationError) as raised:
        runner._analyze_history(
            [rows[0], row(2, recovered_attempt, future, "SUCCEEDED")],
            future.revision,
            allow_open=False,
        )
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID


def test_status_base_releases_lock_and_disposes_engine(
    database_target: DatabaseTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FakeConnection()
    engine = _FakeEngine(connection)
    identity = runner._LockedSession(1, object())
    lifecycle: list[str] = []
    verification = runner.verify_repository(REPOSITORY_ROOT)

    monkeypatch.setattr(runner, "verify_repository", lambda _: verification)
    monkeypatch.setattr(
        MigrationRunner,
        "_prepare_and_lock",
        staticmethod(lambda _: (lifecycle.append("lock"), identity)[1]),
    )
    monkeypatch.setattr(
        MigrationRunner,
        "_unlock",
        staticmethod(lambda _connection, _identity: lifecycle.append("unlock")),
    )
    monkeypatch.setattr(
        MigrationRunner,
        "_assert_same_session",
        staticmethod(lambda _connection, _identity: None),
    )
    monkeypatch.setattr(runner, "_current_heads", lambda _: ())
    monkeypatch.setattr(
        runner, "_assert_empty_database", lambda _: lifecycle.append("empty")
    )
    instance = MigrationRunner(
        REPOSITORY_ROOT,
        database_target,
        engine_factory=lambda _: engine,  # type: ignore[arg-type]
    )

    result = instance.status()
    assert result.current_revision == "base"
    assert result.changed is False
    assert lifecycle == ["lock", "empty", "unlock"]
    assert engine.disposed is True


def test_unknown_revision_still_releases_lock(
    database_target: DatabaseTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FakeConnection()
    engine = _FakeEngine(connection)
    identity = runner._LockedSession(1, object())
    lifecycle: list[str] = []
    verification = runner.verify_repository(REPOSITORY_ROOT)

    monkeypatch.setattr(runner, "verify_repository", lambda _: verification)
    monkeypatch.setattr(
        MigrationRunner,
        "_prepare_and_lock",
        staticmethod(lambda _: (lifecycle.append("lock"), identity)[1]),
    )
    monkeypatch.setattr(
        MigrationRunner,
        "_unlock",
        staticmethod(lambda _connection, _identity: lifecycle.append("unlock")),
    )
    monkeypatch.setattr(
        MigrationRunner,
        "_assert_same_session",
        staticmethod(lambda _connection, _identity: None),
    )
    monkeypatch.setattr(runner, "_current_heads", lambda _: ("unknown",))
    instance = MigrationRunner(
        REPOSITORY_ROOT,
        database_target,
        engine_factory=lambda _: engine,  # type: ignore[arg-type]
    )

    with pytest.raises(MigrationError) as raised:
        instance.status()
    assert raised.value.code is runner.MigrationErrorCode.GRAPH_MISMATCH
    assert lifecycle == ["lock", "unlock"]
    assert engine.disposed is True


def test_upgrade_noop_never_invokes_alembic(
    database_target: DatabaseTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FakeConnection()
    engine = _FakeEngine(connection)
    verification = runner.verify_repository(REPOSITORY_ROOT)
    alembic_calls: list[Any] = []
    identity = runner._LockedSession(1, object())

    monkeypatch.setattr(runner, "verify_repository", lambda _: verification)
    monkeypatch.setattr(
        MigrationRunner, "_prepare_and_lock", staticmethod(lambda _: identity)
    )
    monkeypatch.setattr(
        MigrationRunner,
        "_unlock",
        staticmethod(lambda _connection, _identity: None),
    )
    monkeypatch.setattr(
        MigrationRunner,
        "_assert_same_session",
        staticmethod(lambda _connection, _identity: None),
    )
    monkeypatch.setattr(runner, "_current_heads", lambda _: (catalog.HEAD_REVISION,))
    monkeypatch.setattr(runner, "_validate_installed", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        runner.command, "upgrade", lambda *args: alembic_calls.append(args)
    )
    instance = MigrationRunner(
        REPOSITORY_ROOT,
        database_target,
        engine_factory=lambda _: engine,  # type: ignore[arg-type]
    )

    result = instance.upgrade()
    assert result.changed is False
    assert alembic_calls == []


def test_upgrade_injects_same_connection_and_exact_allowlist(
    database_target: DatabaseTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FakeConnection()
    engine = _FakeEngine(connection)
    verification = runner.verify_repository(REPOSITORY_ROOT)
    observed: dict[str, Any] = {}
    identity = runner._LockedSession(1, object())

    monkeypatch.setattr(runner, "verify_repository", lambda _: verification)
    monkeypatch.setattr(
        MigrationRunner, "_prepare_and_lock", staticmethod(lambda _: identity)
    )
    monkeypatch.setattr(
        MigrationRunner,
        "_unlock",
        staticmethod(lambda _connection, _identity: None),
    )
    monkeypatch.setattr(
        MigrationRunner,
        "_assert_same_session",
        staticmethod(lambda _connection, _identity: None),
    )
    monkeypatch.setattr(runner, "_current_heads", lambda _: ())
    monkeypatch.setattr(runner, "_assert_empty_database", lambda _: None)
    monkeypatch.setattr(runner, "_validate_installed", lambda *args, **kwargs: None)

    def upgrade(configuration: Any, target: str) -> None:
        observed["connection"] = configuration.attributes["connection"]
        observed["target"] = target
        observed["digests"] = configuration.attributes["revision_digests"]
        observed["stories"] = configuration.attributes["revision_stories"]
        observed["runner_versions"] = configuration.attributes[
            "revision_runner_versions"
        ]
        observed["server_versions"] = configuration.attributes[
            "revision_server_versions"
        ]

    monkeypatch.setattr(runner.command, "upgrade", upgrade)
    instance = MigrationRunner(
        REPOSITORY_ROOT,
        database_target,
        engine_factory=lambda _: engine,  # type: ignore[arg-type]
    )

    result = instance.upgrade()
    assert result.changed is True
    assert observed == {
        "connection": connection,
        "target": catalog.HEAD_REVISION,
        "digests": {catalog.HEAD_REVISION: catalog.REVISION_SPECS[0].sha256},
        "stories": {catalog.HEAD_REVISION: "ST-0301"},
        "runner_versions": {
            catalog.HEAD_REVISION: catalog.REVISION_SPECS[0].runner_version
        },
        "server_versions": {
            catalog.HEAD_REVISION: catalog.REVISION_SPECS[0].server_version_num
        },
    }


def test_driver_exception_is_never_chained_or_rendered(
    database_target: DatabaseTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canary = "private-driver-canary"
    verification = runner.verify_repository(REPOSITORY_ROOT)
    monkeypatch.setattr(runner, "verify_repository", lambda _: verification)

    def fail(_: DatabaseTarget):
        raise RuntimeError(canary)

    instance = MigrationRunner(
        REPOSITORY_ROOT,
        database_target,
        engine_factory=fail,
    )
    with pytest.raises(MigrationError) as raised:
        instance.status()
    assert raised.value.code is runner.MigrationErrorCode.CONNECTION_FAILED
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert canary not in str(raised.value)
    assert canary not in repr(raised.value)


def test_history_anchor_downgrade_is_always_forbidden(
    database_target: DatabaseTarget,
) -> None:
    instance = MigrationRunner(
        REPOSITORY_ROOT,
        database_target,
    )
    with pytest.raises(MigrationError) as raised:
        instance.downgrade()
    assert raised.value.code is runner.MigrationErrorCode.DOWNGRADE_FORBIDDEN

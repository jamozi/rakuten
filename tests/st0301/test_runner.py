"""Runner target, ordering, lifecycle, and error-hygiene tests."""

from __future__ import annotations

import errno
import os
import socket
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import pytest

from .support import REPOSITORY_ROOT
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


class _TransactionalFakeConnection(_FakeConnection):
    def __init__(self) -> None:
        super().__init__()
        self.transaction_active = False

    def in_transaction(self) -> bool:
        return self.transaction_active

    def commit(self) -> None:
        super().commit()
        self.transaction_active = False

    def rollback(self) -> None:
        super().rollback()
        self.transaction_active = False


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
        (
            "password_file",
            "/absolute/not-a-path-object",
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


def test_regular_password_leaf_uses_required_nonblocking_nofollow_flags(
    password_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_open = runner.os.open
    calls: list[tuple[object, int, int | None]] = []

    def record_open(
        path: object,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        calls.append((path, flags, dir_fd))
        if dir_fd is None:
            return real_open(path, flags, mode)  # type: ignore[arg-type]
        return real_open(path, flags, mode, dir_fd=dir_fd)  # type: ignore[arg-type]

    monkeypatch.setattr(runner.os, "open", record_open)

    assert runner._read_password_file(password_file) == "local-test-password"
    assert calls[-1][0] == password_file.name
    assert calls[-1][1] & os.O_NOFOLLOW
    assert calls[-1][1] & os.O_NONBLOCK


@pytest.mark.parametrize("missing_flag", ("O_NOFOLLOW", "O_NONBLOCK"))
def test_missing_required_password_open_flag_fails_closed(
    password_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing_flag: str,
) -> None:
    monkeypatch.delattr(runner.os, missing_flag)

    with pytest.raises(MigrationError) as raised:
        runner._read_password_file(password_file)
    assert raised.value.code is runner.MigrationErrorCode.INVALID_PASSWORD_FILE


@pytest.mark.serial
@pytest.mark.parametrize("node_kind", ("fifo", "socket", "directory"))
def test_special_password_leaf_fails_closed_without_blocking(
    tmp_path: Path,
    node_kind: str,
) -> None:
    password = tmp_path / "password"
    listener: socket.socket | None = None
    if node_kind == "fifo":
        os.mkfifo(password)
    elif node_kind == "socket":
        try:
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        except PermissionError as exc:
            if (
                exc.errno == errno.EPERM
                and os.environ.get("RAOS_NETWORK_DENIED") == "1"
            ):
                pytest.skip(
                    "outer denied-network seccomp blocks AF_UNIX socket setup; "
                    "ordinary hosts retain socket-leaf rejection coverage"
                )
            raise
        listener.bind(os.fspath(password))
    else:
        password.mkdir()
    script = """
import sys
from pathlib import Path
from raos.migrations import runner

try:
    runner._read_password_file(Path(sys.argv[1]))
except runner.MigrationError as error:
    print(error.code)
else:
    raise SystemExit(1)
"""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.fspath(REPOSITORY_ROOT / "python")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        completed = subprocess.run(
            [sys.executable, "-c", script, os.fspath(password)],
            cwd=REPOSITORY_ROOT,
            env=environment,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=2.0,
            check=False,
        )
    finally:
        if listener is not None:
            listener.close()
    assert completed.returncode == 0
    assert completed.stdout.strip() == runner.MigrationErrorCode.INVALID_PASSWORD_FILE
    assert completed.stderr == ""


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
    future = catalog.REVISION_SPECS[1]
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
        *,
        direction: str = "UPGRADE",
    ) -> tuple[object, ...]:
        return (
            event_id,
            attempt_id,
            spec.revision,
            spec.story_id,
            direction,
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
    ) == runner._OpenAttempt(failed_attempt, 1, "UPGRADE")

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

    for field_index, invalid_value in (
        (7, "9.9.9"),
        (8, future.server_version_num + 1),
    ):
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

    downgrade_attempt = "00000000-0000-4000-8000-000000000004"
    reupgrade_attempt = "00000000-0000-4000-8000-000000000005"
    round_trip_rows = [
        *rows,
        row(
            6,
            downgrade_attempt,
            future,
            "STARTED",
            direction="DOWNGRADE",
        ),
        row(
            7,
            downgrade_attempt,
            future,
            "SUCCEEDED",
            direction="DOWNGRADE",
        ),
    ]
    assert (
        runner._analyze_history(round_trip_rows, root.revision, allow_open=False)
        is None
    )
    round_trip_rows.extend(
        [
            row(8, reupgrade_attempt, future, "STARTED"),
            row(9, reupgrade_attempt, future, "SUCCEEDED"),
        ]
    )
    assert (
        runner._analyze_history(round_trip_rows, future.revision, allow_open=False)
        is None
    )

    overlap_a = "00000000-0000-4000-8000-000000000006"
    overlap_b = "00000000-0000-4000-8000-000000000007"
    for invalid_rows, expected_revision in (
        (
            [
                rows[0],
                row(2, overlap_a, future, "STARTED"),
                row(3, overlap_b, future, "STARTED"),
            ],
            root.revision,
        ),
        (
            [
                *rows,
                row(
                    6,
                    overlap_a,
                    future,
                    "STARTED",
                    direction="DOWNGRADE",
                ),
                row(
                    7,
                    overlap_b,
                    future,
                    "STARTED",
                    direction="DOWNGRADE",
                ),
            ],
            future.revision,
        ),
        (
            [
                *rows,
                row(
                    6,
                    overlap_a,
                    future,
                    "STARTED",
                    direction="DOWNGRADE",
                ),
                row(7, overlap_b, future, "STARTED"),
            ],
            future.revision,
        ),
    ):
        with pytest.raises(MigrationError) as raised:
            runner._analyze_history(
                invalid_rows,
                expected_revision,
                allow_open=True,
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
    monkeypatch.setattr(runner, "_append_attempt_event", lambda *args, **kwargs: None)

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
        observed["direction"] = configuration.attributes["operation_direction"]

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
        "digests": {spec.revision: spec.sha256 for spec in catalog.REVISION_SPECS},
        "stories": {spec.revision: spec.story_id for spec in catalog.REVISION_SPECS},
        "runner_versions": {
            spec.revision: spec.runner_version for spec in catalog.REVISION_SPECS
        },
        "server_versions": {
            spec.revision: spec.server_version_num for spec in catalog.REVISION_SPECS
        },
        "direction": "UPGRADE",
    }


@pytest.mark.parametrize(
    ("direction", "current_revision"),
    (
        ("UPGRADE", catalog.ANCHOR_REVISION),
        ("DOWNGRADE", catalog.FOUNDATION_REVISION),
    ),
)
def test_post_commit_session_failure_never_appends_failed_terminal(
    database_target: DatabaseTarget,
    monkeypatch: pytest.MonkeyPatch,
    direction: str,
    current_revision: str,
) -> None:
    connection = _TransactionalFakeConnection()
    identity = runner._LockedSession(1, object())
    verification = runner.verify_repository(REPOSITORY_ROOT)
    events: list[tuple[str, str]] = []

    monkeypatch.setattr(runner, "_current_heads", lambda _: (current_revision,))
    monkeypatch.setattr(
        MigrationRunner,
        "_reconcile_interrupted_attempt",
        lambda self, _connection, _revision, _identity, **kwargs: None,
    )

    def assert_same_session(_connection: object, _identity: object) -> None:
        if connection.commits > 0:
            raise MigrationError(runner.MigrationErrorCode.SESSION_CLEANUP_FAILED)

    monkeypatch.setattr(
        MigrationRunner,
        "_assert_same_session",
        staticmethod(assert_same_session),
    )

    def append_event(_connection: object, **values: object) -> None:
        events.append((str(values["direction"]), str(values["status"])))

    monkeypatch.setattr(runner, "_append_attempt_event", append_event)
    monkeypatch.setattr(
        runner,
        "_validate_installed",
        lambda *args, **kwargs: pytest.fail("post-commit validation must not run"),
    )

    def migration_command(configuration: Any, target: str) -> None:
        assert configuration.attributes["connection"] is connection
        expected_target = (
            catalog.FOUNDATION_REVISION
            if direction == "UPGRADE"
            else catalog.ANCHOR_REVISION
        )
        assert target == expected_target
        connection.transaction_active = True

    instance = MigrationRunner(REPOSITORY_ROOT, database_target)
    if direction == "UPGRADE":
        monkeypatch.setattr(runner.command, "upgrade", migration_command)
        operation = instance._upgrade_locked  # noqa: SLF001
    else:
        monkeypatch.setattr(runner.command, "downgrade", migration_command)
        operation = instance._downgrade_locked  # noqa: SLF001

    with pytest.raises(MigrationError) as raised:
        operation(
            connection,  # type: ignore[arg-type]
            identity,
            verification,
        )
    assert raised.value.code is runner.MigrationErrorCode.SESSION_CLEANUP_FAILED
    assert events == [(direction, "STARTED")]
    assert connection.commits == 1
    assert connection.rollbacks == 0


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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FakeConnection()
    identity = runner._LockedSession(1, object())
    verification = runner.verify_repository(REPOSITORY_ROOT)
    foundation_object_modes: list[bool] = []
    monkeypatch.setattr(
        MigrationRunner,
        "_assert_same_session",
        staticmethod(lambda _connection, _identity: None),
    )
    monkeypatch.setattr(
        MigrationRunner,
        "_reconcile_interrupted_attempt",
        lambda self, _connection, _revision, _identity, **kwargs: (
            foundation_object_modes.append(
                bool(kwargs.get("allow_foundation_objects", False))
            )
        ),
    )
    monkeypatch.setattr(runner, "_current_heads", lambda _: (catalog.ANCHOR_REVISION,))
    instance = MigrationRunner(
        REPOSITORY_ROOT,
        database_target,
    )
    with pytest.raises(MigrationError) as raised:
        instance._downgrade_locked(  # noqa: SLF001
            connection,  # type: ignore[arg-type]
            identity,
            verification,
        )
    assert raised.value.code is runner.MigrationErrorCode.DOWNGRADE_FORBIDDEN
    assert foundation_object_modes == [True]


def test_downgrade_snapshot_failure_precedes_started_history(
    database_target: DatabaseTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FakeConnection()
    identity = runner._LockedSession(1, object())
    verification = runner.verify_repository(REPOSITORY_ROOT)
    events: list[str] = []
    monkeypatch.setattr(
        MigrationRunner,
        "_assert_same_session",
        staticmethod(lambda _connection, _identity: None),
    )
    monkeypatch.setattr(
        MigrationRunner,
        "_reconcile_interrupted_attempt",
        lambda self, _connection, _revision, _identity, **kwargs: None,
    )
    monkeypatch.setattr(
        runner, "_current_heads", lambda _: (catalog.FOUNDATION_REVISION,)
    )
    monkeypatch.setattr(
        runner,
        "_append_attempt_event",
        lambda *args, **kwargs: events.append(str(kwargs["status"])),
    )

    def fail_snapshot(_verification: object) -> None:
        raise OSError("snapshot-canary")

    monkeypatch.setattr(runner, "_verified_migration_root", fail_snapshot)
    instance = MigrationRunner(REPOSITORY_ROOT, database_target)

    with pytest.raises(OSError, match="snapshot-canary"):
        instance._downgrade_locked(  # noqa: SLF001
            connection,  # type: ignore[arg-type]
            identity,
            verification,
        )
    assert events == []

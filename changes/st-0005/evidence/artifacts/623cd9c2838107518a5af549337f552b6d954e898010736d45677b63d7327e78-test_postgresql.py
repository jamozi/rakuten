"""Exact PostgreSQL 18.4 zero-to-latest runtime acceptance tests."""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import socket
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import psycopg
import pytest
from alembic import command as alembic_command
from psycopg import sql

from conftest import REPOSITORY_ROOT
from raos.migrations import DatabaseTarget, MigrationEnvironment, MigrationError
from raos.migrations import catalog
from raos.migrations import runner


POSTGRES_TOOLS = (
    "postgres",
    "initdb",
    "pg_ctl",
    "pg_isready",
    "psql",
    "createdb",
)
EXPECTED_SERVER_VERSION_NUM = 180004


def _tools() -> tuple[dict[str, Path], dict[str, str]]:
    configured = os.environ.get("RAOS_PG_BIN")
    if configured is None:
        pytest.skip("ST-0301 PostgreSQL tests require exact 18.4 via RAOS_PG_BIN")
    directory = Path(configured)
    tools = {name: directory / name for name in POSTGRES_TOOLS}
    if any(not path.is_file() for path in tools.values()):
        pytest.fail("RAOS_PG_BIN is missing a required PostgreSQL executable")
    environment = dict(os.environ)
    library_path = environment.get("RAOS_PG_LIB")
    if library_path is not None:
        environment["LD_LIBRARY_PATH"] = library_path
    version = subprocess.run(
        [os.fspath(tools["postgres"]), "--version"],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
        env=environment,
    )
    if version.returncode != 0:
        pytest.fail("configured PostgreSQL executable could not be inspected")
    if re.search(r"\b18[.]4\b", version.stdout) is None:
        pytest.fail("configured PostgreSQL runtime is not exact version 18.4")
    return tools, environment


def _available_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


@dataclass(slots=True)
class PostgreSQLCluster:
    tools: dict[str, Path]
    process_environment: dict[str, str]
    data_directory: Path
    socket_directory: Path
    log_path: Path
    password_file: Path
    port: int
    user: str = "raos_admin"
    migration_user: str = "raos_migrator"
    _counter: int = field(default=0, init=False)

    def run(
        self,
        tool: str,
        arguments: list[str],
        *,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        process = subprocess.run(
            [os.fspath(self.tools[tool]), *arguments],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
            env=self.process_environment,
        )
        if check and process.returncode != 0:
            tail = ""
            if self.log_path.exists():
                tail = self.log_path.read_text(encoding="utf-8", errors="replace")[
                    -4000:
                ]
            raise AssertionError(f"isolated PostgreSQL command failed: {tool}\n{tail}")
        return process

    def create_database(self, label: str) -> str:
        self._counter += 1
        safe = re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_")[:24]
        database = f"st0301_{self._counter}_{safe}"
        self.run(
            "createdb",
            [
                "--host",
                os.fspath(self.socket_directory),
                "--port",
                str(self.port),
                "--username",
                self.user,
                "--owner",
                self.migration_user,
                "--template",
                "template0",
                database,
            ],
        )
        return database

    def connect(self, database: str, *, autocommit: bool = True):
        return psycopg.connect(
            host=os.fspath(self.socket_directory),
            port=self.port,
            dbname=database,
            user=self.user,
            autocommit=autocommit,
        )

    def target(self, database: str) -> DatabaseTarget:
        return DatabaseTarget(
            environment=MigrationEnvironment.CI,
            host=os.fspath(self.socket_directory),
            port=self.port,
            database=database,
            user=self.migration_user,
            password_file=self.password_file,
        )


@pytest.fixture(scope="session")
def postgresql_cluster(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[PostgreSQLCluster]:
    tools, process_environment = _tools()
    root = tmp_path_factory.mktemp("st0301_postgresql_18_4")
    data_directory = root / "data"
    socket_directory = root / "socket"
    log_path = root / "postgres.log"
    password_file = root / "password"
    socket_directory.mkdir()
    migration_password = secrets.token_urlsafe(32)
    password_file.write_text(f"{migration_password}\n", encoding="utf-8")
    password_file.chmod(0o600)
    cluster = PostgreSQLCluster(
        tools=tools,
        process_environment=process_environment,
        data_directory=data_directory,
        socket_directory=socket_directory,
        log_path=log_path,
        password_file=password_file,
        port=_available_port(),
    )
    started = False
    try:
        cluster.run(
            "initdb",
            [
                "--pgdata",
                os.fspath(data_directory),
                "--username",
                cluster.user,
                "--auth-local=trust",
                "--auth-host=reject",
                "--encoding=UTF8",
                "--locale=C",
                "--no-sync",
            ],
        )
        cluster.run(
            "pg_ctl",
            [
                "--pgdata",
                os.fspath(data_directory),
                "--log",
                os.fspath(log_path),
                "--options",
                (
                    f"-k {socket_directory} -p {cluster.port} "
                    "-c listen_addresses='' -c fsync=off "
                    "-c synchronous_commit=off -c full_page_writes=off"
                ),
                "--wait",
                "start",
            ],
        )
        started = True
        cluster.run(
            "pg_isready",
            [
                "--host",
                os.fspath(socket_directory),
                "--port",
                str(cluster.port),
                "--username",
                cluster.user,
                "--dbname",
                "postgres",
            ],
        )
        with cluster.connect("postgres") as connection:
            version = connection.execute("SHOW server_version_num").fetchone()
            assert version == (str(EXPECTED_SERVER_VERSION_NUM),)
            connection.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(cluster.migration_user),
                    sql.Literal(migration_password),
                )
            )
        (data_directory / "pg_hba.conf").write_text(
            "\n".join(
                (
                    f"local all {cluster.user} trust",
                    f"local all {cluster.migration_user} scram-sha-256",
                    "local all all reject",
                    "",
                )
            ),
            encoding="utf-8",
        )
        cluster.run(
            "pg_ctl",
            ["--pgdata", os.fspath(data_directory), "reload"],
        )
        yield cluster
    finally:
        if started:
            cluster.run(
                "pg_ctl",
                [
                    "--pgdata",
                    os.fspath(data_directory),
                    "--mode",
                    "immediate",
                    "--wait",
                    "stop",
                ],
            )


@pytest.fixture
def empty_database(
    postgresql_cluster: PostgreSQLCluster, request: pytest.FixtureRequest
) -> str:
    return postgresql_cluster.create_database(request.node.name)


def _migration_runner(
    cluster: PostgreSQLCluster, database: str
) -> runner.MigrationRunner:
    return runner.MigrationRunner(
        REPOSITORY_ROOT,
        cluster.target(database),
    )


def test_runtime_authenticates_migration_role_with_password_file(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    tmp_path: Path,
) -> None:
    wrong_password_file = tmp_path / "wrong-password"
    wrong_password_file.write_text(f"{secrets.token_urlsafe(32)}\n", encoding="utf-8")
    wrong_password_file.chmod(0o600)
    target = postgresql_cluster.target(empty_database)
    wrong_target = DatabaseTarget(
        environment=target.environment,
        host=target.host,
        port=target.port,
        database=target.database,
        user=target.user,
        password_file=wrong_password_file,
    )

    with pytest.raises(MigrationError) as raised:
        runner.MigrationRunner(REPOSITORY_ROOT, wrong_target).status()
    assert raised.value.code is runner.MigrationErrorCode.CONNECTION_FAILED
    assert _migration_runner(
        postgresql_cluster, empty_database
    ).status().current_revision == ("base")


_FUTURE_REVISION_SOURCE = b'''\
"""Synthetic future revision used only by the ST-0301 framework test.

Revision ID: 202608030002
Revises: 202608030001
Create Date: 2026-08-03

RAOS metadata:
- story: ST-0302
- requirement IDs: none
- architecture: ST-0301 extensibility acceptance fixture
- risk class: A
- estimated lock: new test table only
- backfill job: none
- rollback category: forward recovery fixture
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202608030002"
down_revision: str | None = "202608030001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "st0301_future_probe",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_st0301_future_probe"),
        schema="public",
    )


def downgrade() -> None:
    raise RuntimeError("FORWARD_RECOVERY_REQUIRED")
'''


def _install_future_graph(monkeypatch: pytest.MonkeyPatch) -> catalog.RevisionSpec:
    verification = runner.verify_repository(REPOSITORY_ROOT)
    digest = hashlib.sha256(_FUTURE_REVISION_SOURCE).hexdigest()
    future = catalog.RevisionSpec(
        revision="202608030002",
        down_revision=catalog.ANCHOR_REVISION,
        story_id="ST-0302",
        relative_path=Path("migrations/versions/202608030002_future_fixture.py"),
        sha256=digest,
        runner_version="1.1.0",
        server_version_num=EXPECTED_SERVER_VERSION_NUM,
    )
    future_source = catalog.VerifiedSource(
        relative_path=future.relative_path,
        sha256=digest,
        size=len(_FUTURE_REVISION_SOURCE),
        content=_FUTURE_REVISION_SOURCE,
    )
    expanded = catalog.CatalogVerification(
        runtime_sources=verification.runtime_sources,
        revision_sources=(*verification.revision_sources, future_source),
        checkpoint_sources=verification.checkpoint_sources,
        catalog_sha256="2" * 64,
    )
    monkeypatch.setattr(runner, "REVISION_SPECS", (*catalog.REVISION_SPECS, future))
    monkeypatch.setattr(runner, "HEAD_REVISION", future.revision)
    with runner._verified_migration_root(expanded) as snapshot_root:
        runner._verify_graph(snapshot_root)
    monkeypatch.setattr(runner, "verify_repository", lambda _: expanded)
    return future


def test_empty_database_reaches_exact_head_atomically_and_repeats_as_noop(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    before = instance.status()
    first = instance.upgrade()
    second = instance.upgrade()
    after = instance.status()

    assert before.current_revision == "base"
    assert first.changed is True
    assert second.changed is False
    assert after.current_revision == catalog.HEAD_REVISION
    with postgresql_cluster.connect(empty_database) as connection:
        row = connection.execute(
            """
            SELECT v.version_num,
                   v.xmin::text,
                   h.revision_id,
                   h.status,
                   h.source_sha256,
                   h.runner_version,
                   h.server_version_num,
                   h.transaction_id,
                   h.xmin::text
            FROM public.raos_migration_version AS v
            CROSS JOIN public.raos_migration_history AS h
            """
        ).fetchone()
        assert row == (
            catalog.HEAD_REVISION,
            row[1],
            catalog.HEAD_REVISION,
            "SUCCEEDED",
            catalog.REVISION_SPECS[0].sha256,
            catalog.REVISION_SPECS[0].runner_version,
            EXPECTED_SERVER_VERSION_NUM,
            row[8],
            row[8],
        )
        assert row[1] == row[8]
        assert connection.execute(
            "SELECT count(*) FROM public.raos_migration_history"
        ).fetchone() == (1,)


def test_temporary_two_revision_graph_reaches_latest_with_per_revision_attempts(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    future = _install_future_graph(monkeypatch)
    instance = _migration_runner(postgresql_cluster, empty_database)

    assert instance.upgrade().current_revision == future.revision
    assert instance.upgrade().changed is False
    with postgresql_cluster.connect(empty_database) as connection:
        rows = connection.execute(
            """
            SELECT revision_id, status, attempt_id::text, transaction_id,
                   xmin::text, runner_version, server_version_num
            FROM public.raos_migration_history
            ORDER BY event_id
            """
        ).fetchall()
        version = connection.execute(
            """
            SELECT version_num, xmin::text
            FROM public.raos_migration_version
            """
        ).fetchone()
        assert [(row[0], row[1]) for row in rows] == [
            (catalog.ANCHOR_REVISION, "SUCCEEDED"),
            (future.revision, "STARTED"),
            (future.revision, "SUCCEEDED"),
        ]
        assert rows[0][2] != rows[1][2]
        assert rows[1][2] == rows[2][2]
        assert rows[1][3] != rows[2][3]
        assert version == (future.revision, rows[2][4])
        assert rows[2][3] == rows[2][4]
        assert [(row[5], row[6]) for row in rows] == [
            (
                catalog.REVISION_SPECS[0].runner_version,
                catalog.REVISION_SPECS[0].server_version_num,
            ),
            (future.runner_version, future.server_version_num),
            (future.runner_version, future.server_version_num),
        ]
        assert connection.execute(
            "SELECT to_regclass('public.st0301_future_probe')"
        ).fetchone() == ("st0301_future_probe",)


def test_post_bootstrap_failure_records_terminal_then_forward_recovers(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    future = _install_future_graph(monkeypatch)
    real_upgrade = alembic_command.upgrade
    failure_injected = False

    def fail_future_once(configuration, target) -> None:
        nonlocal failure_injected
        if target == future.revision and not failure_injected:
            failure_injected = True
            connection = configuration.attributes["connection"]
            connection.exec_driver_sql(
                "CREATE TABLE public.st0301_future_rolled_back (id integer)"
            )
            raise RuntimeError("private-future-detail")
        real_upgrade(configuration, target)

    monkeypatch.setattr(runner.command, "upgrade", fail_future_once)
    instance = _migration_runner(postgresql_cluster, empty_database)
    with pytest.raises(MigrationError) as raised:
        instance.upgrade()
    assert raised.value.code is runner.MigrationErrorCode.MIGRATION_FAILED
    assert "private-future-detail" not in str(raised.value)
    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.raos_migration_version"
        ).fetchone() == (catalog.ANCHOR_REVISION,)
        assert connection.execute(
            "SELECT to_regclass('public.st0301_future_rolled_back')"
        ).fetchone() == (None,)
        assert connection.execute(
            """
            SELECT revision_id, status, error_code
            FROM public.raos_migration_history
            ORDER BY event_id
            """
        ).fetchall() == [
            (catalog.ANCHOR_REVISION, "SUCCEEDED", None),
            (future.revision, "STARTED", None),
            (future.revision, "FAILED", "MIGRATION_FAILED"),
        ]

    monkeypatch.setattr(runner.command, "upgrade", real_upgrade)
    assert instance.upgrade().current_revision == future.revision
    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute(
            """
            SELECT status, error_code
            FROM public.raos_migration_history
            WHERE revision_id = %s
            ORDER BY event_id
            """,
            (future.revision,),
        ).fetchall() == [
            ("STARTED", None),
            ("FAILED", "MIGRATION_FAILED"),
            ("STARTED", None),
            ("SUCCEEDED", None),
        ]


def test_next_lock_holder_closes_interrupted_attempt_before_retry(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _migration_runner(postgresql_cluster, empty_database).upgrade().changed
    future = _install_future_graph(monkeypatch)
    interrupted_attempt = "00000000-0000-4000-8000-000000000004"
    engine = runner._default_engine_factory(postgresql_cluster.target(empty_database))
    try:
        with engine.connect() as connection:
            runner._append_attempt_event(
                connection,
                attempt_id=interrupted_attempt,
                revision_index=1,
                status="STARTED",
                error_code=None,
            )
    finally:
        engine.dispose()

    assert (
        _migration_runner(postgresql_cluster, empty_database).upgrade().current_revision
        == future.revision
    )
    with postgresql_cluster.connect(empty_database) as connection:
        rows = connection.execute(
            """
            SELECT attempt_id::text, status, error_code
            FROM public.raos_migration_history
            WHERE revision_id = %s
            ORDER BY event_id
            """,
            (future.revision,),
        ).fetchall()
        assert rows[:2] == [
            (interrupted_attempt, "STARTED", None),
            (
                interrupted_attempt,
                "FAILED",
                "INTERRUPTED_BEFORE_TERMINAL",
            ),
        ]
        assert rows[2][0] != interrupted_attempt
        assert rows[2][1:] == ("STARTED", None)
        assert rows[3][0] == rows[2][0]
        assert rows[3][1:] == ("SUCCEEDED", None)


def test_session_loss_never_reconnects_without_lock_or_writes_failed_history(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    assert instance.upgrade().current_revision == catalog.ANCHOR_REVISION
    future = _install_future_graph(monkeypatch)
    real_upgrade = alembic_command.upgrade

    def terminate_future_session(configuration, target) -> None:
        if target != future.revision:
            real_upgrade(configuration, target)
            return
        connection = configuration.attributes["connection"]
        backend_pid = connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
        with postgresql_cluster.connect(empty_database) as administrator:
            assert administrator.execute(
                "SELECT pg_terminate_backend(%s)", (backend_pid,)
            ).fetchone() == (True,)
        connection.exec_driver_sql("SELECT 1")

    monkeypatch.setattr(runner.command, "upgrade", terminate_future_session)
    with pytest.raises(MigrationError) as raised:
        instance.upgrade()
    assert raised.value.code is runner.MigrationErrorCode.SESSION_CLEANUP_FAILED
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.raos_migration_version"
        ).fetchone() == (catalog.ANCHOR_REVISION,)
        assert connection.execute(
            """
            SELECT status, error_code
            FROM public.raos_migration_history
            WHERE revision_id = %s
            ORDER BY event_id
            """,
            (future.revision,),
        ).fetchall() == [("STARTED", None)]

    monkeypatch.setattr(runner.command, "upgrade", real_upgrade)
    assert instance.upgrade().current_revision == future.revision
    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute(
            """
            SELECT status, error_code
            FROM public.raos_migration_history
            WHERE revision_id = %s
            ORDER BY event_id
            """,
            (future.revision,),
        ).fetchall() == [
            ("STARTED", None),
            ("FAILED", "INTERRUPTED_BEFORE_TERMINAL"),
            ("STARTED", None),
            ("SUCCEEDED", None),
        ]


def test_lost_advisory_lock_rolls_back_revision_before_forward_recovery(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    assert instance.upgrade().current_revision == catalog.ANCHOR_REVISION
    future = _install_future_graph(monkeypatch)
    real_upgrade = alembic_command.upgrade

    def release_lock_before_future(configuration, target) -> None:
        if target == future.revision:
            connection = configuration.attributes["connection"]
            connection.exec_driver_sql("SELECT pg_advisory_unlock_all()")
        real_upgrade(configuration, target)

    monkeypatch.setattr(runner.command, "upgrade", release_lock_before_future)
    with pytest.raises(MigrationError) as raised:
        instance.upgrade()
    assert raised.value.code is runner.MigrationErrorCode.SESSION_CLEANUP_FAILED
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.raos_migration_version"
        ).fetchone() == (catalog.ANCHOR_REVISION,)
        assert connection.execute(
            "SELECT to_regclass('public.st0301_future_probe')"
        ).fetchone() == (None,)
        assert connection.execute(
            """
            SELECT status, error_code
            FROM public.raos_migration_history
            WHERE revision_id = %s
            ORDER BY event_id
            """,
            (future.revision,),
        ).fetchall() == [("STARTED", None)]

    monkeypatch.setattr(runner.command, "upgrade", real_upgrade)
    assert instance.upgrade().current_revision == future.revision


def test_framework_head_creates_no_domain_schema_extension_or_payload_object(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _migration_runner(postgresql_cluster, empty_database).upgrade()
    with postgresql_cluster.connect(empty_database) as connection:
        schemas = connection.execute(
            """
            SELECT nspname
            FROM pg_catalog.pg_namespace
            WHERE nspname = ANY(%s)
            ORDER BY nspname
            """,
            (list(runner.DOMAIN_SCHEMAS),),
        ).fetchall()
        extensions = connection.execute(
            "SELECT extname FROM pg_catalog.pg_extension ORDER BY extname"
        ).fetchall()
        metadata_tables = connection.execute(
            """
            SELECT tablename
            FROM pg_catalog.pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
            """
        ).fetchall()
        assert schemas == []
        assert extensions == [("plpgsql",)]
        assert metadata_tables == [
            ("raos_migration_history",),
            ("raos_migration_version",),
        ]


def test_history_rejects_update_delete_and_truncate(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _migration_runner(postgresql_cluster, empty_database).upgrade()
    statements = (
        "UPDATE public.raos_migration_history SET status = 'FAILED'",
        "DELETE FROM public.raos_migration_history",
        "TRUNCATE public.raos_migration_history",
    )
    with postgresql_cluster.connect(empty_database) as connection:
        for statement in statements:
            with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState) as raised:
                connection.execute(statement)
            assert "append-only" in str(raised.value)
        assert connection.execute(
            "SELECT count(*) FROM public.raos_migration_history"
        ).fetchone() == (1,)


@pytest.mark.parametrize(
    "statements",
    (
        (
            "ALTER TABLE public.raos_migration_history "
            "DROP CONSTRAINT ck_raos_migration_history_status",
            "ALTER TABLE public.raos_migration_history ADD CONSTRAINT "
            "ck_raos_migration_history_status CHECK (true)",
        ),
        (
            "ALTER TABLE public.raos_migration_history "
            "ALTER COLUMN occurred_at SET DEFAULT now()",
        ),
        (
            "ALTER TABLE public.raos_migration_history "
            "DISABLE TRIGGER trg_raos_migration_history_append_only",
        ),
        (
            """
            CREATE FUNCTION public.st0301_suppress_success()
            RETURNS trigger LANGUAGE plpgsql AS $function$
            BEGIN
                IF NEW.status = 'SUCCEEDED' THEN
                    RETURN NULL;
                END IF;
                RETURN NEW;
            END;
            $function$
            """,
            """
            CREATE TRIGGER trg_st0301_suppress_success
            BEFORE INSERT ON public.raos_migration_history
            FOR EACH ROW EXECUTE FUNCTION public.st0301_suppress_success()
            """,
        ),
        (
            "CREATE RULE st0301_ignore_history_insert AS ON INSERT TO "
            "public.raos_migration_history DO INSTEAD NOTHING",
        ),
        ("ALTER TABLE public.raos_migration_history ENABLE ROW LEVEL SECURITY",),
        (
            "ALTER TABLE public.raos_migration_history "
            "ALTER COLUMN event_id DROP IDENTITY",
        ),
        ("DROP TABLE public.raos_migration_history",),
    ),
)
def test_metadata_shape_tampering_fails_closed(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    statements: tuple[str, ...],
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()
    with postgresql_cluster.connect(empty_database) as connection:
        for statement in statements:
            connection.execute(statement)

    with pytest.raises(MigrationError) as raised:
        instance.status()
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID


def test_extra_insert_trigger_blocks_future_revision_before_any_mutation(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()
    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            """
            CREATE FUNCTION public.st0301_suppress_success()
            RETURNS trigger LANGUAGE plpgsql AS $function$
            BEGIN
                IF NEW.status = 'SUCCEEDED' THEN
                    RETURN NULL;
                END IF;
                RETURN NEW;
            END;
            $function$
            """
        )
        connection.execute(
            """
            CREATE TRIGGER trg_st0301_suppress_success
            BEFORE INSERT ON public.raos_migration_history
            FOR EACH ROW EXECUTE FUNCTION public.st0301_suppress_success()
            """
        )
    _install_future_graph(monkeypatch)

    with pytest.raises(MigrationError) as raised:
        instance.upgrade()
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID
    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.raos_migration_version"
        ).fetchone() == (catalog.ANCHOR_REVISION,)
        assert connection.execute(
            "SELECT to_regclass('public.st0301_future_probe')"
        ).fetchone() == (None,)
        assert connection.execute(
            """
            SELECT revision_id, status
            FROM public.raos_migration_history
            ORDER BY event_id
            """
        ).fetchall() == [(catalog.ANCHOR_REVISION, "SUCCEEDED")]


def test_named_role_metadata_grant_fails_closed(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()
    role = f"st0301_metadata_reader_{postgresql_cluster._counter}"
    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(f'CREATE ROLE "{role}" NOLOGIN')
        connection.execute(f'GRANT SELECT ON public.raos_migration_history TO "{role}"')

    with pytest.raises(MigrationError) as raised:
        instance.status()
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID


def test_public_and_unprivileged_role_have_no_metadata_access(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _migration_runner(postgresql_cluster, empty_database).upgrade()
    role = f"st0301_reader_{postgresql_cluster._counter}"
    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(f'CREATE ROLE "{role}" NOLOGIN')
        try:
            connection.execute(f'SET ROLE "{role}"')
            for table in ("raos_migration_version", "raos_migration_history"):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    connection.execute(f"SELECT * FROM public.{table}")
            connection.execute("RESET ROLE")
        finally:
            connection.execute("RESET ROLE")
            connection.execute(f'DROP ROLE IF EXISTS "{role}"')


def test_lock_contention_fails_without_mutation_then_forward_recovers(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    with postgresql_cluster.connect(empty_database) as holder:
        assert holder.execute(
            "SELECT pg_try_advisory_lock(%s)", (runner.ADVISORY_LOCK_KEY,)
        ).fetchone() == (True,)
        with pytest.raises(MigrationError) as raised:
            instance.upgrade()
        assert raised.value.code is runner.MigrationErrorCode.LOCK_BUSY
        assert holder.execute(
            "SELECT to_regclass('public.raos_migration_history')"
        ).fetchone() == (None,)
        assert holder.execute(
            "SELECT pg_advisory_unlock(%s)", (runner.ADVISORY_LOCK_KEY,)
        ).fetchone() == (True,)

    assert instance.upgrade().changed is True
    with postgresql_cluster.connect(empty_database) as probe:
        assert probe.execute(
            "SELECT pg_try_advisory_lock(%s)", (runner.ADVISORY_LOCK_KEY,)
        ).fetchone() == (True,)
        assert probe.execute(
            "SELECT pg_advisory_unlock(%s)", (runner.ADVISORY_LOCK_KEY,)
        ).fetchone() == (True,)


def test_unmanaged_nonempty_database_is_rejected_without_mutation(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute("CREATE TABLE public.unmanaged_marker (id integer)")
    instance = _migration_runner(postgresql_cluster, empty_database)

    with pytest.raises(MigrationError) as raised:
        instance.upgrade()
    assert raised.value.code is runner.MigrationErrorCode.UNMANAGED_DATABASE
    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute(
            "SELECT to_regclass('public.raos_migration_version')"
        ).fetchone() == (None,)
        assert connection.execute(
            "SELECT to_regclass('public.raos_migration_history')"
        ).fetchone() == (None,)


def test_unmanaged_public_type_is_rejected_without_mutation(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute("CREATE TYPE public.unmanaged_state AS ENUM ('A')")

    with pytest.raises(MigrationError) as raised:
        _migration_runner(postgresql_cluster, empty_database).upgrade()
    assert raised.value.code is runner.MigrationErrorCode.UNMANAGED_DATABASE
    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute(
            "SELECT to_regclass('public.raos_migration_history')"
        ).fetchone() == (None,)


@pytest.mark.parametrize(
    "unmanaged_statement",
    (
        """
        CREATE OPERATOR public.=== (
            FUNCTION = pg_catalog.int4eq,
            LEFTARG = integer,
            RIGHTARG = integer
        )
        """,
        """
        CREATE TEXT SEARCH CONFIGURATION public.unmanaged_search
        (COPY = pg_catalog.simple)
        """,
        "SELECT pg_catalog.lo_create(0)",
    ),
)
def test_unmanaged_catalog_objects_are_rejected_without_mutation(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    unmanaged_statement: str,
) -> None:
    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(unmanaged_statement)

    with pytest.raises(MigrationError) as raised:
        _migration_runner(postgresql_cluster, empty_database).upgrade()
    assert raised.value.code is runner.MigrationErrorCode.UNMANAGED_DATABASE
    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute(
            "SELECT to_regclass('public.raos_migration_history')"
        ).fetchone() == (None,)


def test_failed_transaction_rolls_back_then_explicit_forward_recovery_succeeds(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    real_upgrade = alembic_command.upgrade

    def injected_failure(configuration, target) -> None:
        del target
        connection = configuration.attributes["connection"]
        connection.exec_driver_sql(
            "CREATE TABLE public.st0301_injected_failure (id integer)"
        )
        raise RuntimeError("private-driver-detail")

    monkeypatch.setattr(runner.command, "upgrade", injected_failure)
    with pytest.raises(MigrationError) as raised:
        instance.upgrade()
    assert raised.value.code is runner.MigrationErrorCode.MIGRATION_FAILED
    assert "private-driver-detail" not in str(raised.value)
    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute(
            "SELECT to_regclass('public.st0301_injected_failure')"
        ).fetchone() == (None,)
        assert connection.execute(
            "SELECT to_regclass('public.raos_migration_version')"
        ).fetchone() == (None,)

    monkeypatch.setattr(runner.command, "upgrade", real_upgrade)
    assert instance.upgrade().changed is True


def test_on_version_apply_failure_rolls_back_revision_version_and_history(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    target = postgresql_cluster.target(empty_database)
    engine = runner._default_engine_factory(target)
    try:
        with engine.connect() as connection:
            configuration = runner._alembic_config(REPOSITORY_ROOT)
            configuration.attributes.update(
                {
                    "attempt_id": "not-a-uuid",
                    "connection": connection,
                    "revision_digests": {
                        catalog.HEAD_REVISION: catalog.REVISION_SPECS[0].sha256
                    },
                    "revision_stories": {catalog.HEAD_REVISION: "ST-0301"},
                    "revision_runner_versions": {
                        catalog.HEAD_REVISION: catalog.REVISION_SPECS[0].runner_version
                    },
                    "revision_server_versions": {
                        catalog.HEAD_REVISION: catalog.REVISION_SPECS[
                            0
                        ].server_version_num
                    },
                }
            )
            with pytest.raises(Exception):
                alembic_command.upgrade(configuration, catalog.HEAD_REVISION)
            if connection.in_transaction():
                connection.rollback()
    finally:
        engine.dispose()

    with postgresql_cluster.connect(empty_database) as connection:
        for name in (
            "raos_migration_version",
            "raos_migration_history",
        ):
            assert connection.execute(
                "SELECT to_regclass(%s)", (f"public.{name}",)
            ).fetchone() == (None,)

    assert (
        _migration_runner(postgresql_cluster, empty_database).upgrade().changed is True
    )


def test_alembic_runs_while_same_backend_holds_session_lock(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_upgrade = alembic_command.upgrade
    observed: list[tuple[bool, str]] = []

    def inspect_then_upgrade(configuration, target) -> None:
        connection = configuration.attributes["connection"]
        lock_held = connection.exec_driver_sql(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_catalog.pg_locks
                WHERE locktype = 'advisory'
                  AND pid = pg_backend_pid()
                  AND granted
            )
            """
        ).scalar_one()
        observed.append((bool(lock_held), target))
        real_upgrade(configuration, target)

    monkeypatch.setattr(runner.command, "upgrade", inspect_then_upgrade)
    _migration_runner(postgresql_cluster, empty_database).upgrade()
    assert observed == [(True, catalog.HEAD_REVISION)]


def test_server_version_guard_is_exact_not_major_only(
    postgresql_cluster: PostgreSQLCluster,
) -> None:
    assert postgresql_cluster.connect("postgres").execute(
        "SHOW server_version_num"
    ).fetchone() == (str(EXPECTED_SERVER_VERSION_NUM),)
    assert EXPECTED_SERVER_VERSION_NUM != 180003

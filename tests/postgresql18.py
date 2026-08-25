"""Reusable isolated exact-PostgreSQL-18.4 pytest cluster fixture."""

from __future__ import annotations

import os
import re
import secrets
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from raos.migrations import DatabaseTarget, MigrationEnvironment


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
        pytest.skip("exact PostgreSQL 18.4 tests require RAOS_PG_BIN")
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
    # Every cluster owns a unique Unix-socket directory and disables TCP.
    # A random high port therefore names its socket without requiring AF_INET.
    return 20_000 + secrets.randbelow(30_000)


@dataclass(slots=True)
class PostgreSQLCluster:
    """One local, socket-only PostgreSQL cluster shared by a test session."""

    tools: dict[str, Path]
    process_environment: dict[str, str]
    data_directory: Path
    socket_directory: Path
    log_path: Path
    password_file: Path
    port: int
    user: str = "raos_admin"
    migration_user: str = "raos_schema_owner"
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
        database = f"raos_pg18_{self._counter}_{safe}"
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

    def connect(
        self, database: str, *, autocommit: bool = True
    ) -> psycopg.Connection[tuple[object, ...]]:
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
    """Start one exact, isolated, socket-only PostgreSQL 18.4 cluster."""

    tools, process_environment = _tools()
    root = tmp_path_factory.mktemp("raos_postgresql_18_4")
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
                sql.SQL("CREATE ROLE {} LOGIN CREATEROLE PASSWORD {}").format(
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
    """Create an isolated empty database owned by the migration role."""

    del request
    return postgresql_cluster.create_database("empty_database")

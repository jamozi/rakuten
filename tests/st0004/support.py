"""Isolated PostgreSQL 18 fixture for the ST-0004 migration story."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Iterator
from uuid import uuid4
import zipfile

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = REPOSITORY_ROOT / "tests"
if str(TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTS_ROOT))

from st0002.conftest import (  # noqa: E402
    BASELINE_ARCHIVE,
    BASELINE_SQL_MEMBERS,
    PostgresCluster,
    _archive_member,
    _postgres_tools,
)
from st0003.conftest import upgrade_st0002  # noqa: E402,F401


def read_sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def apply_sql(cluster: Any, database: str, *paths: Path) -> None:
    for path in paths:
        cluster.psql(database, read_sql(path))


@pytest.fixture(scope="session")
def st0004_postgresql_cluster(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[PostgresCluster]:
    tools = _postgres_tools()
    dropdb = tools["createdb"].with_name("dropdb")
    if not dropdb.is_file():
        pytest.skip(f"PostgreSQL test tool is unavailable: {dropdb}")
    tools["dropdb"] = dropdb
    cluster_root = tmp_path_factory.mktemp("st0004_postgresql")
    data_dir = cluster_root / "data"
    socket_dir = cluster_root / "socket"
    log_path = cluster_root / "postgres.log"
    socket_dir.mkdir()
    port = 55434
    started = False
    cluster = PostgresCluster(
        tools=tools,
        data_dir=data_dir,
        socket_dir=socket_dir,
        log_path=log_path,
        port=port,
        template_database="raos_st0004_baseline",
        server_version_num=0,
    )
    try:
        cluster.run(
            "initdb",
            [
                "--pgdata", str(data_dir),
                "--username", cluster.superuser,
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
                "--pgdata", str(data_dir),
                "--log", str(log_path),
                "--options",
                (
                    f"-k {socket_dir} -p {port} -c listen_addresses='' "
                    "-c fsync=off -c synchronous_commit=off -c full_page_writes=off"
                ),
                "--wait", "start",
            ],
        )
        started = True
        cluster.run(
            "pg_isready",
            [
                "--host", str(socket_dir),
                "--port", str(port),
                "--username", cluster.superuser,
                "--dbname", "postgres",
            ],
        )
        cluster.server_version_num = int(cluster.query("postgres", "SHOW server_version_num;"))
        if cluster.server_version_num < 180000:
            pytest.skip(
                "ST-0004 PostgreSQL integration tests require PostgreSQL 18 or later, "
                f"found server_version_num={cluster.server_version_num}"
            )
        cluster.run(
            "createdb",
            [
                "--host", str(socket_dir),
                "--port", str(port),
                "--username", cluster.superuser,
                cluster.template_database,
            ],
        )
        with zipfile.ZipFile(BASELINE_ARCHIVE) as archive:
            for suffix in BASELINE_SQL_MEMBERS:
                member = _archive_member(archive, suffix)
                cluster.psql(
                    cluster.template_database,
                    archive.read(member).decode("utf-8"),
                )
        yield cluster
    finally:
        if started:
            cluster.run(
                "pg_ctl",
                ["--pgdata", str(data_dir), "--mode", "fast", "--wait", "stop"],
            )


@pytest.fixture
def st0004_database(st0004_postgresql_cluster: PostgresCluster) -> Iterator[str]:
    cluster = st0004_postgresql_cluster
    database = f"st0004_{uuid4().hex}"
    common = [
        "--host", str(cluster.socket_dir),
        "--port", str(cluster.port),
        "--username", cluster.superuser,
    ]
    cluster.run(
        "createdb",
        [*common, "--template", cluster.template_database, database],
    )
    try:
        yield database
    finally:
        cluster.run("dropdb", [*common, "--if-exists", database])

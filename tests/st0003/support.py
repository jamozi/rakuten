"""Shared ST-0003 fixtures.

The PostgreSQL harness deliberately reuses the exercised ST-0002 cluster
implementation.  A distinct port keeps a full-repository pytest run from
colliding with the ST-0002 session fixture.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Iterator
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


ST0002_DATABASE_ROOT = REPOSITORY_ROOT / "changes" / "st-0002" / "database"
ST0002_UPGRADE_FILES = (
    "202607300001_job_state_expand.sql",
    "202607300002_job_state_expand_validate.sql",
    "202607300003_job_state_migrate_batch.sql",
    "202607300004_job_state_contract_prepare.sql",
    "202607300005_job_state_contract.sql",
)


def read_sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def apply_sql(cluster: Any, database: str, *paths: Path) -> None:
    for path in paths:
        cluster.psql(database, read_sql(path))


def st0002_remaining_rows(cluster: Any, database: str) -> int:
    return int(
        cluster.query(
            database,
            """
            SELECT count(*)
              FROM ops.job
             WHERE job_version IS NULL
                OR status IN ('PENDING', 'READY', 'FAILED');
            """,
        )
    )


def upgrade_st0002(cluster: Any, database: str) -> None:
    """Reach the exact finalized ST-0002 predecessor."""

    paths = tuple(ST0002_DATABASE_ROOT / name for name in ST0002_UPGRADE_FILES)
    expand, expand_validate, migrate_batch, contract_prepare, contract = paths
    apply_sql(cluster, database, expand, expand_validate)

    batch_count = 0
    while st0002_remaining_rows(cluster, database):
        before = st0002_remaining_rows(cluster, database)
        apply_sql(cluster, database, migrate_batch)
        after = st0002_remaining_rows(cluster, database)
        assert 0 <= before - after <= 1000
        assert after < before
        batch_count += 1
        assert batch_count < 10_000

    apply_sql(cluster, database, contract_prepare, contract)


@pytest.fixture(scope="session")
def st0003_postgresql_cluster(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[PostgresCluster]:
    tools = _postgres_tools()
    cluster_root = tmp_path_factory.mktemp("st0003_postgresql")
    data_dir = cluster_root / "data"
    socket_dir = cluster_root / "socket"
    log_path = cluster_root / "postgres.log"
    socket_dir.mkdir()
    port = 55433
    started = False

    cluster = PostgresCluster(
        tools=tools,
        data_dir=data_dir,
        socket_dir=socket_dir,
        log_path=log_path,
        port=port,
        template_database="raos_st0003_baseline",
        server_version_num=0,
    )

    try:
        cluster.run(
            "initdb",
            [
                "--pgdata",
                str(data_dir),
                "--username",
                cluster.superuser,
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
                str(data_dir),
                "--log",
                str(log_path),
                "--options",
                (
                    f"-k {socket_dir} -p {port} -c listen_addresses='' "
                    "-c fsync=off -c synchronous_commit=off "
                    "-c full_page_writes=off"
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
                str(socket_dir),
                "--port",
                str(port),
                "--username",
                cluster.superuser,
                "--dbname",
                "postgres",
            ],
        )

        cluster.server_version_num = int(
            cluster.query("postgres", "SHOW server_version_num;")
        )
        if cluster.server_version_num < 180000:
            pytest.skip(
                "ST-0003 PostgreSQL integration tests require PostgreSQL 18 "
                f"or later, found server_version_num={cluster.server_version_num}"
            )

        cluster.run(
            "createdb",
            [
                "--host",
                str(socket_dir),
                "--port",
                str(port),
                "--username",
                cluster.superuser,
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
                [
                    "--pgdata",
                    str(data_dir),
                    "--mode",
                    "fast",
                    "--wait",
                    "stop",
                ],
            )

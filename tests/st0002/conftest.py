from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Iterator
import zipfile

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_ARCHIVE = (
    REPO_ROOT / "docs" / "upstream" / "RAOS_03_data_model_package_v0.1.zip"
)
BASELINE_SQL_MEMBERS = (
    "sql/RAOS_03_001_baseline_v0.1.sql",
    "sql/RAOS_03_002_roles_and_grants_v0.1.sql",
    "sql/RAOS_03_003_reference_seed_v0.1.sql",
    "sql/RAOS_03_004_post_deploy_validation_v0.1.sql",
)
POSTGRES_TOOLS = (
    "postgres",
    "initdb",
    "pg_ctl",
    "pg_isready",
    "psql",
    "createdb",
)


def _postgres_tools() -> dict[str, Path]:
    configured_bin = os.environ.get("RAOS_PG_BIN")
    if configured_bin:
        bin_dir = Path(configured_bin).expanduser()
        missing = [name for name in POSTGRES_TOOLS if not (bin_dir / name).is_file()]
        if missing:
            pytest.fail(
                "RAOS_PG_BIN does not contain the required PostgreSQL tools: "
                + ", ".join(missing)
            )
        return {name: (bin_dir / name).resolve() for name in POSTGRES_TOOLS}

    resolved: dict[str, Path] = {}
    missing = []
    for name in POSTGRES_TOOLS:
        executable = shutil.which(name)
        if executable is None:
            missing.append(name)
        else:
            resolved[name] = Path(executable).resolve()

    if missing:
        pytest.skip(
            "ST-0002 PostgreSQL tests require PostgreSQL 18 tools via "
            "RAOS_PG_BIN or PATH; missing: " + ", ".join(missing)
        )
    return resolved


def _archive_member(archive: zipfile.ZipFile, suffix: str) -> str:
    matches = [name for name in archive.namelist() if name.endswith(suffix)]
    if len(matches) != 1:
        raise AssertionError(
            f"expected exactly one ZIP member ending in {suffix!r}, found {matches!r}"
        )
    return matches[0]


@dataclass
class PostgresCluster:
    tools: dict[str, Path]
    data_dir: Path
    socket_dir: Path
    log_path: Path
    port: int
    template_database: str
    server_version_num: int
    superuser: str = "postgres"
    _database_counter: int = field(default=0, init=False)

    def run(
        self,
        tool: str,
        arguments: list[str],
        *,
        input_text: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [str(self.tools[tool]), *arguments],
            input=input_text,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        if check and result.returncode != 0:
            log_tail = ""
            if self.log_path.exists():
                log_tail = self.log_path.read_text(encoding="utf-8", errors="replace")[
                    -8_000:
                ]
            raise AssertionError(
                f"{tool} failed with exit code {result.returncode}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}\n"
                f"postgres log tail:\n{log_tail}"
            )
        return result

    def psql(
        self,
        database: str,
        sql: str,
        *,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return self.run(
            "psql",
            [
                "-X",
                "--set=ON_ERROR_STOP=1",
                "--no-align",
                "--tuples-only",
                "--field-separator=\t",
                "--host",
                str(self.socket_dir),
                "--port",
                str(self.port),
                "--username",
                self.superuser,
                "--dbname",
                database,
            ],
            input_text=sql,
            check=check,
        )

    def query(self, database: str, sql: str) -> str:
        return self.psql(database, sql).stdout.strip()

    def clone_database(self, label: str) -> str:
        self._database_counter += 1
        safe_label = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:32]
        database = f"st0002_{self._database_counter}_{safe_label}"
        self.run(
            "createdb",
            [
                "--host",
                str(self.socket_dir),
                "--port",
                str(self.port),
                "--username",
                self.superuser,
                "--template",
                self.template_database,
                database,
            ],
        )
        return database


@pytest.fixture(scope="session")
def postgresql_cluster(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[PostgresCluster]:
    tools = _postgres_tools()
    cluster_root = tmp_path_factory.mktemp("st0002_postgresql")
    data_dir = cluster_root / "data"
    socket_dir = cluster_root / "socket"
    log_path = cluster_root / "postgres.log"
    socket_dir.mkdir()
    port = 55432
    started = False

    bootstrap = PostgresCluster(
        tools=tools,
        data_dir=data_dir,
        socket_dir=socket_dir,
        log_path=log_path,
        port=port,
        template_database="raos_st0002_previous",
        server_version_num=0,
    )

    try:
        bootstrap.run(
            "initdb",
            [
                "--pgdata",
                str(data_dir),
                "--username",
                bootstrap.superuser,
                "--auth-local=trust",
                "--auth-host=reject",
                "--encoding=UTF8",
                "--locale=C",
                "--no-sync",
            ],
        )
        bootstrap.run(
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
        bootstrap.run(
            "pg_isready",
            [
                "--host",
                str(socket_dir),
                "--port",
                str(port),
                "--username",
                bootstrap.superuser,
                "--dbname",
                "postgres",
            ],
        )

        server_version_num = int(
            bootstrap.query("postgres", "SHOW server_version_num;")
        )
        bootstrap.server_version_num = server_version_num
        if server_version_num < 180000:
            pytest.skip(
                "ST-0002 PostgreSQL integration tests require PostgreSQL 18 "
                f"or later, found server_version_num={server_version_num}"
            )

        bootstrap.run(
            "createdb",
            [
                "--host",
                str(socket_dir),
                "--port",
                str(port),
                "--username",
                bootstrap.superuser,
                bootstrap.template_database,
            ],
        )

        with zipfile.ZipFile(BASELINE_ARCHIVE) as archive:
            for suffix in BASELINE_SQL_MEMBERS:
                member = _archive_member(archive, suffix)
                sql = archive.read(member).decode("utf-8")
                bootstrap.psql(bootstrap.template_database, sql)

        yield bootstrap
    finally:
        if started:
            bootstrap.run(
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

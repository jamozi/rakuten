from __future__ import annotations

import hashlib
import io
import os
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPO_ROOT / "python"
for path in (REPO_ROOT, PYTHON_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts import build_st0307_migration_fixtures as fixture_generator  # noqa: E402
from tests.postgresql18 import (  # noqa: E402,F401
    PostgreSQLCluster,
    empty_database as empty_database,
    postgresql_cluster as postgresql_cluster,
)


def run_psql(
    cluster: PostgreSQLCluster,
    database: str,
    statement: str,
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Execute one isolated payload; callers never concatenate checkpoints."""

    result = subprocess.run(
        [
            os.fspath(cluster.tools["psql"]),
            "-X",
            "--set=ON_ERROR_STOP=1",
            "--no-align",
            "--tuples-only",
            "--field-separator=\t",
            "--host",
            os.fspath(cluster.socket_directory),
            "--port",
            str(cluster.port),
            "--username",
            cluster.user,
            "--dbname",
            database,
        ],
        input=statement,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
        env=cluster.process_environment,
    )
    if check and result.returncode != 0:
        tail = ""
        if cluster.log_path.exists():
            tail = cluster.log_path.read_text(encoding="utf-8", errors="replace")[
                -4000:
            ]
        raise AssertionError(
            "isolated PostgreSQL payload failed\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}\nlog:\n{tail}"
        )
    return result


def _archive_member(archive: zipfile.ZipFile, suffix: str) -> str:
    matches = [name for name in archive.namelist() if name.endswith(suffix)]
    assert len(matches) == 1, (suffix, matches)
    return matches[0]


def verified_fixture_bytes(path: Path, root: Path = REPO_ROOT) -> bytes:
    """Return the exact committed fixture bytes only after deterministic comparison."""

    if path not in fixture_generator.FIXTURE_PATHS:
        raise AssertionError("path is not an ST-0307 generated fixture")
    expected = fixture_generator.render_outputs(root)[path]
    observed = fixture_generator._read(root, path, f"executed fixture {path}")
    if observed != expected:
        raise AssertionError("ST-0307 fixture differs from deterministic output")
    return observed


def apply_fixture(
    cluster: PostgreSQLCluster,
    database: str,
    path: Path,
    *,
    root: Path = REPO_ROOT,
    executor: Any = run_psql,
) -> subprocess.CompletedProcess[str]:
    """Verify and execute the same immutable fixture byte snapshot."""

    content = verified_fixture_bytes(path, root)
    return executor(cluster, database, content.decode("utf-8"))


def verified_upstream_member_bytes(root: Path = REPO_ROOT) -> tuple[bytes, ...]:
    """Read one archive snapshot and verify every member before returning bytes."""

    archive_bytes = fixture_generator._read(
        root,
        fixture_generator.UPSTREAM_ARCHIVE_PATH,
        "ST-0307 upstream bootstrap archive",
    )
    if (
        hashlib.sha256(archive_bytes).hexdigest()
        != fixture_generator.EXPECTED_ARCHIVE_SHA256
    ):
        raise AssertionError("ST-0307 upstream bootstrap archive digest differs")
    members: list[bytes] = []
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        for (
            _purpose,
            suffix,
            expected_sha256,
        ) in fixture_generator.UPSTREAM_MEMBER_SPECS:
            member = archive.read(_archive_member(archive, suffix))
            if hashlib.sha256(member).hexdigest() != expected_sha256:
                raise AssertionError("ST-0307 upstream bootstrap member digest differs")
            members.append(member)
    return tuple(members)


def apply_upstream_bootstrap(
    cluster: PostgreSQLCluster,
    database: str,
    *,
    root: Path = REPO_ROOT,
    members: tuple[bytes, ...] | None = None,
    executor: Any = run_psql,
) -> None:
    """Verify all authorities, then execute the same verified member bytes."""

    if members is None:
        fixture_generator.validate_source_inputs(root)
        members = verified_upstream_member_bytes(root)
    for member in members:
        executor(cluster, database, member.decode("utf-8"))


@dataclass(slots=True)
class HistoricalDatabaseFactory:
    cluster: PostgreSQLCluster
    template_database: str
    counter: int = field(default=0, init=False)

    def clone(self, label: str) -> str:
        self.counter += 1
        safe = "".join(character if character.isalnum() else "_" for character in label)
        database = f"raos_st0307_hist_{self.counter}_{safe.casefold()[:18]}"
        self.cluster.run(
            "createdb",
            [
                "--host",
                os.fspath(self.cluster.socket_directory),
                "--port",
                str(self.cluster.port),
                "--username",
                self.cluster.user,
                "--owner",
                self.cluster.user,
                "--template",
                self.template_database,
                database,
            ],
        )
        return database


@pytest.fixture(scope="session")
def historical_database_factory(
    request: pytest.FixtureRequest,
) -> Iterator[HistoricalDatabaseFactory]:
    """Load the hash-pinned upstream package once, then clone disposable DBs."""

    postgresql_cluster: PostgreSQLCluster = request.getfixturevalue(
        "postgresql_cluster"
    )
    fixture_generator.validate_source_inputs(REPO_ROOT)
    verified_members = verified_upstream_member_bytes(REPO_ROOT)
    template = "raos_st0307_baseline"
    postgresql_cluster.run(
        "createdb",
        [
            "--host",
            os.fspath(postgresql_cluster.socket_directory),
            "--port",
            str(postgresql_cluster.port),
            "--username",
            postgresql_cluster.user,
            "--owner",
            postgresql_cluster.user,
            "--template",
            "template0",
            template,
        ],
    )
    apply_upstream_bootstrap(
        postgresql_cluster,
        template,
        members=verified_members,
    )
    yield HistoricalDatabaseFactory(postgresql_cluster, template)

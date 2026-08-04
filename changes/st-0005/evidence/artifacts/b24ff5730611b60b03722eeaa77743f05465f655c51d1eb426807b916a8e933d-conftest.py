"""Shared ST-0301 contract and target fixtures."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.migrations import DatabaseTarget, MigrationEnvironment  # noqa: E402
from tests.postgresql18 import (  # noqa: E402, F401
    empty_database,
    postgresql_cluster,
)


@pytest.fixture(scope="session")
def migration_contract() -> dict[str, Any]:
    path = REPOSITORY_ROOT / "changes/st-0301/contracts/migration-framework.v1.yaml"
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


@pytest.fixture
def password_file(tmp_path: Path) -> Path:
    path = tmp_path / "database-password"
    path.write_text("local-test-password\n", encoding="utf-8")
    path.chmod(0o600)
    return path


@pytest.fixture
def database_target(password_file: Path, tmp_path: Path) -> DatabaseTarget:
    socket_directory = tmp_path / "socket"
    socket_directory.mkdir()
    return DatabaseTarget(
        environment=MigrationEnvironment.CI,
        host=os.fspath(socket_directory),
        port=55432,
        database="raos_st0301",
        user="raos_migrator",
        password_file=password_file,
    )

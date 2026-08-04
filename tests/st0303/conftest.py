"""Shared strict-contract and exact PostgreSQL 18.4 ST-0303 fixtures."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from scripts import build_st0201_postgres_service as shared  # noqa: E402
from tests.postgresql18 import (  # noqa: E402, F401
    empty_database,
    postgresql_cluster,
)


@pytest.fixture(scope="session")
def iam_ops_contract() -> dict[str, Any]:
    path = REPOSITORY_ROOT / "changes/st-0303/contracts/iam-ops-schema.v1.yaml"
    value = shared.load_yaml(path)
    assert isinstance(value, dict)
    return value


@pytest.fixture(scope="session")
def iam_ops_tables(iam_ops_contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tables = iam_ops_contract["tables"]
    result = {item["fully_qualified_name"]: item for item in tables}
    assert len(result) == len(tables)
    return result

"""Shared ST-0302 contract and exact PostgreSQL 18.4 fixtures."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from tests.postgresql18 import (  # noqa: E402, F401
    empty_database,
    postgresql_cluster,
)


@pytest.fixture(scope="session")
def foundation_contract() -> dict[str, Any]:
    path = REPOSITORY_ROOT / "changes/st-0302/contracts/foundation-schema.v1.yaml"
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value

"""Shared strict-source fixtures for ST-0304 generator tests."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from scripts import build_st0304_domain_schemas as generator  # noqa: E402
from tests.postgresql18 import (  # noqa: E402, F401
    empty_database,
    postgresql_cluster,
)


@pytest.fixture(scope="session")
def domain_contract() -> dict[str, Any]:
    return generator._load_contract()


@pytest.fixture(scope="session")
def physical_objects() -> tuple[generator.PhysicalObject, ...]:
    return generator._load_objects()

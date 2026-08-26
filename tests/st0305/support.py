"""Shared exact-PostgreSQL fixtures for ST-0305 tests."""

from __future__ import annotations

import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from tests.postgresql18 import empty_database, postgresql_cluster  # noqa: E402, F401

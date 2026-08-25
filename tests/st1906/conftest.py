"""Import boundary for isolated ST-1906 tests."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = ROOT / "python"
for candidate in (ROOT, PYTHON_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

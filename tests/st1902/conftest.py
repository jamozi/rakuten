"""ST-1902 test import boundary."""

from __future__ import annotations

from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
for _root in (REPOSITORY_ROOT, PYTHON_ROOT):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

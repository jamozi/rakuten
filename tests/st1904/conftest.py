from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = ROOT / "python"
for path in (ROOT, PYTHON_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from __future__ import annotations

import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
for candidate in (REPOSITORY_ROOT, REPOSITORY_ROOT / "python"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

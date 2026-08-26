from __future__ import annotations

import shutil
from pathlib import Path

from scripts import build_st1607_gate_evidence_pack as builder


def repository_copy(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    paths = [builder.CONTRACT_PATH, *map(Path, builder.EXPECTED_SOURCE_HASHES)]
    for relative in paths:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(builder.REPO_ROOT / relative, target)
        target.chmod(0o600)
    return root

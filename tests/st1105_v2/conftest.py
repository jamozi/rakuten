from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from scripts import build_st1105_admin_visual_accessibility as owner


@pytest.fixture
def isolated_root(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    contract = json.loads((owner.REPO_ROOT / owner.CONTRACT_PATH).read_text("utf-8"))
    paths = {
        owner.CONTRACT_PATH,
        owner.BROWSER_CONTRACT_PATH,
        owner.FIXTURE_PATH,
        owner.SCREEN_CATALOG_PATH,
        owner.COMPONENT_CATALOG_PATH,
        owner.WORKFLOW_CATALOG_PATH,
        owner.CHECKLIST_PATH,
        owner.SUITE_CATALOG_PATH,
        *(Path(row["path"]) for row in contract["source_bindings"]),
    }
    for relative in paths:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(owner.REPO_ROOT / relative, target)
    return root

"""Shared fixtures for the isolated ST-0902 reference-plan suite."""

from __future__ import annotations

from pathlib import Path
import shutil
import sys

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import build_st0902_final_approval_reference_plan as generator  # noqa: E402


@pytest.fixture()
def isolated_repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    required = {
        *generator.SOURCE_PATHS,
        generator.HELPER_PATH,
        *(Path(path) for _role, path, _digest in generator.EXPECTED_SOURCES),
        *(
            Path(path)
            for _story_id, _role, path, _digest in generator.DEPENDENCY_INPUTS
        ),
    }
    for relative in required:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / relative, target)
    return root

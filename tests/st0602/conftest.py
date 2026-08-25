"""Shared fixtures for the isolated ST-0602 suites."""

from __future__ import annotations

from pathlib import Path
import shutil
import sys

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
for path in (REPOSITORY_ROOT, PYTHON_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts import (  # noqa: E402
    build_st0602_fact_extraction_validation_reference_plan as generator,
)


@pytest.fixture()
def isolated_repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    required = {
        *generator.SOURCE_PATHS,
        generator.HELPER_PATH,
        generator.STORY_PATH,
        *(path for path, _digest in generator.ST0601_ARTIFACTS),
        *(path for path, _digest in generator.ST0503_ARTIFACTS),
    }
    for relative in required:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / relative, target)
    return root

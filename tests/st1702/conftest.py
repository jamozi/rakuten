"""Shared fixtures for the isolated ST-1702 reference-plan suite."""

from __future__ import annotations

from pathlib import Path
import shutil
import sys

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import (  # noqa: E402
    build_st1702_category_fixtures_rules_reference_plan as generator,
)


@pytest.fixture()
def isolated_repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    for relative in generator.INPUT_PATHS:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / relative, target)
    return root

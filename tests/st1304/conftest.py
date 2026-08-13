"""Shared fixtures for the isolated ST-1304 reference-plan suite."""

from __future__ import annotations

from pathlib import Path
import shutil
import sys

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import (  # noqa: E402
    build_st1304_cost_unit_economics_reference_plan as generator,
)


@pytest.fixture()
def isolated_repository(tmp_path: Path) -> Path:
    """Copy the complete closed ST-1304 input set into an isolated root."""

    root = tmp_path / "repository"
    contract = generator.load_contract()
    required = {
        *generator.SOURCE_PATHS,
        generator.HELPER_PATH,
        *(path for path, _digest in generator._contract_artifacts(contract)),
    }
    for relative in required:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / relative, target)
    return root

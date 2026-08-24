"""Shared fixtures for ST-0708 historical compatibility and generation tests."""

from __future__ import annotations

from pathlib import Path
import shutil
import sys

import pytest
import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import (  # noqa: E402
    build_st0708_openai_live_bounded_evaluation_reference_plan as generator,
)


@pytest.fixture()
def isolated_repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    contract = yaml.safe_load(
        (REPOSITORY_ROOT / generator.RUNTIME_CONTRACT_PATH).read_bytes()
    )
    required = {
        generator.CONTRACT_PATH,
        generator.RUNTIME_CONTRACT_PATH,
        generator.HELPER_PATH,
    }
    for section in (
        "canonical_sources",
        "st0703_recorded_binding",
        "st0707_report_binding",
    ):
        for value in contract[section].values():
            if type(value) is dict and set(value) == {"path", "sha256"}:
                required.add(Path(value["path"]))
    required.update(Path(value) for value in contract["owned_sources"])
    for relative in required:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / relative, target)
    return root

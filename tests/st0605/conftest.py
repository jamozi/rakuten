from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import pytest
import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import (  # noqa: E402
    build_st0605_claim_evidence_coverage_reference_plan as generator,
)


BUILDER = REPOSITORY_ROOT / generator.GENERATOR_PATH
CONTRACT = REPOSITORY_ROOT / generator.CONTRACT_PATH
GENERATED = REPOSITORY_ROOT / generator.REFERENCE_PLAN_PATH
MANIFEST = REPOSITORY_ROOT / generator.MANIFEST_PATH


@pytest.fixture(scope="session")  # type: ignore[untyped-decorator]
def contract() -> dict[str, Any]:
    loaded = yaml.safe_load(CONTRACT.read_bytes())
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture(scope="session")  # type: ignore[untyped-decorator]
def generated() -> dict[str, Any]:
    loaded = json.loads(GENERATED.read_bytes())
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture()  # type: ignore[untyped-decorator]
def isolated_repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    required = {
        *generator.SOURCE_PATHS,
        *generator.GENERATED_PATHS,
        generator.HELPER_PATH,
        generator.STORY_PATH,
        *(path for path, _digest in generator.ST0602_ARTIFACTS),
        *(path for path, _digest in generator.ST0603_ARTIFACTS),
        *(path for path, _digest in generator.ST0604_ARTIFACTS),
        *(path for path, _digest, _relationship in generator.CONTEXT_SOURCES),
    }
    for relative in required:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / relative, target)
    return root


def run_builder(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BUILDER), *arguments],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

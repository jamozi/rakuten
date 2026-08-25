"""Shared fixtures for the isolated ST-1604 reference-plan suite."""

from __future__ import annotations

from pathlib import Path
import shutil
import sys

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import (  # noqa: E402
    build_st1505_staging_deployment as staging_generator,
    build_st1604_performance_load_reference_plan as generator,
)


@pytest.fixture()
def isolated_repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    required = {
        *generator.SOURCE_PATHS,
        generator.HELPER_PATH,
        *staging_generator.SOURCE_ARTIFACT_PATHS,
        Path(
            "infra/terraform/deployment-identity/"
            "github-oidc.evaluation.recorded.v1.json"
        ),
        *(Path(path) for _role, path, _digest in generator.EXPECTED_SOURCES),
        *(path for path, _digest in generator.EXPECTED_PREDECESSORS),
    }
    for relative in required:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / relative, target)
    return root

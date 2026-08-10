"""Fixtures for the isolated ST-1205 reference-plan suite."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
from typing import Any, cast

import pytest
import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


from scripts import build_st1205_kpi_read_model_reference_plan as builder  # noqa: E402


@pytest.fixture
def contract() -> dict[str, Any]:
    value = yaml.safe_load((REPOSITORY_ROOT / builder.CONTRACT_PATH).read_text())
    if type(value) is not dict:
        raise TypeError("invalid test contract")
    return cast(dict[str, Any], value)


@pytest.fixture
def plan() -> dict[str, Any]:
    value = json.loads((REPOSITORY_ROOT / builder.REFERENCE_PLAN_PATH).read_text())
    if type(value) is not dict:
        raise TypeError("invalid test plan")
    return cast(dict[str, Any], value)


@pytest.fixture
def manifest() -> dict[str, Any]:
    value = yaml.safe_load((REPOSITORY_ROOT / builder.MANIFEST_PATH).read_text())
    if type(value) is not dict:
        raise TypeError("invalid test manifest")
    return cast(dict[str, Any], value)


def copy_owner_root(destination: Path, *, include_outputs: bool = True) -> Path:
    paths = {
        *builder.SOURCE_PATHS,
        builder.STORY_PATH,
        builder.KPI_CATALOG_PATH,
        builder.INTEGRATION_PATH,
        builder.HELPER_PATH,
        *(path for path, _digest in builder.ST1201_ARTIFACTS),
        *(path for path, _digest in builder.ST1203_ARTIFACTS),
        *(path for path, _digest in builder.ST1204_ARTIFACTS),
    }
    if include_outputs:
        paths.update(builder.GENERATED_PATHS)
    for relative in paths:
        source = REPOSITORY_ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return destination


@pytest.fixture
def isolated_root(tmp_path: Path) -> Path:
    return copy_owner_root(tmp_path)

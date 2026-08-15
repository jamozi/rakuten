from __future__ import annotations

import copy
from collections.abc import Iterator
from pathlib import Path
import shutil

import pytest

from scripts import build_st1605_failure_injection_drill as builder


@pytest.fixture
def contract() -> dict[str, object]:
    return copy.deepcopy(dict(builder.load_contract()))


@pytest.fixture
def repository_copy(tmp_path: Path) -> Iterator[Path]:
    authority_paths = {
        Path(path) for path, _digest in builder.EXPECTED_AUTHORITY_SOURCES.values()
    }
    dependency_paths = {
        *map(Path, builder.EXPECTED_ST1602_HASHES),
        *map(Path, builder.EXPECTED_ST1405_HASHES),
        *map(Path, builder.EXPECTED_IMPLEMENTATION_HASHES),
        *(Path(path) for path, _digest in builder.EXPECTED_RUNTIME_MODULES.values()),
    }
    paths = {*authority_paths, *dependency_paths, *builder.SOURCE_PATHS}
    for relative in paths:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(builder.REPO_ROOT / relative, target)
    yield tmp_path

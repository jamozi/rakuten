from __future__ import annotations

import copy
from collections.abc import Iterator
from pathlib import Path
import shutil

import pytest

from scripts import build_st1705_pilot_signoff as builder


@pytest.fixture
def contract() -> dict[str, object]:
    return copy.deepcopy(dict(builder.load_contract()))


@pytest.fixture
def repository_copy(tmp_path: Path) -> Iterator[Path]:
    paths = {
        *map(Path, builder.EXPECTED_SOURCE_HASHES),
        *map(Path, builder.EXPECTED_DEPENDENCY_HASHES),
        *builder.SOURCE_PATHS,
    }
    for relative in paths:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(builder.REPO_ROOT / relative, target)
    (tmp_path / builder.DECISION_PATH.parent).mkdir(parents=True, exist_ok=True)
    yield tmp_path

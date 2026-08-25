from __future__ import annotations

import copy
from collections.abc import Iterator
from pathlib import Path
import shutil

import pytest

from scripts import build_st1502_data_services as data_generator
from scripts import build_st1505_staging_deployment as staging_generator
from scripts import build_st1606_backup_restore_drill as builder


@pytest.fixture
def contract() -> dict[str, object]:
    return copy.deepcopy(dict(builder.load_contract()))


@pytest.fixture
def repository_copy(tmp_path: Path) -> Iterator[Path]:
    paths = {
        *map(Path, builder.EXPECTED_SOURCE_HASHES),
        *map(Path, builder.EXPECTED_PREDECESSOR_HASHES),
        *map(Path, builder.EXPECTED_IMPLEMENTATION_DEPENDENCY_HASHES),
        *builder.SOURCE_PATHS,
        *map(Path, data_generator.PINNED_SOURCES),
        *data_generator.SOURCE_ARTIFACT_PATHS,
        *map(Path, staging_generator.PINNED_SOURCES),
        *staging_generator.SOURCE_ARTIFACT_PATHS,
    }
    for relative in paths:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(builder.REPO_ROOT / relative, target)
    yield tmp_path

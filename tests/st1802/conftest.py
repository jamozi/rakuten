from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
import shutil

import pytest

from scripts import build_st1802_gate1_decision as builder


@pytest.fixture
def contract() -> dict[str, object]:
    return dict(builder.load_contract())


@pytest.fixture
def repository_copy(tmp_path: Path) -> Iterator[Path]:
    paths = {
        *builder.SOURCE_PATHS,
        builder.FIXTURE_SCHEMA_PATH,
        builder.FIXTURE_PATH,
        *(Path(path) for path in builder.EXPECTED_SOURCE_HASHES),
        *(Path(path) for path in builder.EXPECTED_DEPENDENCY_HASHES),
    }
    for relative in sorted(paths):
        source = builder.REPO_ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    (tmp_path / builder.PACK_PATH.parent).mkdir(parents=True, exist_ok=True)
    yield tmp_path

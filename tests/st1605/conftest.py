from __future__ import annotations

import copy
from collections.abc import Iterator
from pathlib import Path
import shutil
import sys
from types import ModuleType

import pytest

from scripts import build_st1605_failure_injection_drill as builder


@pytest.fixture(autouse=True)
def isolated_raos_runtime_inventory() -> Iterator[None]:
    """Keep the fail-closed runtime loader independent of suite order.

    Other Story suites legitimately import ``raos`` during collection.  ST-1605
    deliberately rejects any preloaded RAOS runtime module, so its tests must
    provide the same clean process boundary used by the owner CLI.  Preserve
    and restore foreign module identities instead of weakening that production
    preflight or relying on a particular pytest invocation order.
    """

    preserved = {
        name: module
        for name, module in tuple(sys.modules.items())
        if builder._is_raos_module_name(name) and isinstance(module, ModuleType)
    }
    for name in preserved:
        sys.modules.pop(name, None)
    try:
        yield
    finally:
        for name in tuple(sys.modules):
            if builder._is_raos_module_name(name):
                sys.modules.pop(name, None)
        sys.modules.update(preserved)


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

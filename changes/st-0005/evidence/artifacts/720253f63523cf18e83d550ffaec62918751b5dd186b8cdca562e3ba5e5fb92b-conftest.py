"""Shared fixtures for the isolated ST-0104 contract-repository suite."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))
INSTALLER_PATH = REPO_ROOT / "scripts" / "build_st0104_contract_repository.py"
VERIFIER_PATH = REPO_ROOT / "scripts" / "verify_contract_repository.py"
VERSION_ROOT = REPO_ROOT / "contracts" / "raos-v0.4"
SOURCE_ROOT = REPO_ROOT / "changes" / "st-0004"
MANIFEST_NAME = "contract-repository.v0.4.json"


def load_module(path: Path, name: str) -> ModuleType:
    """Load one repository script under an isolated, dataclass-safe name."""

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


@pytest.fixture
def installer_module() -> Iterator[ModuleType]:
    name = "raos_test_st0104_installer"
    module = load_module(INSTALLER_PATH, name)
    try:
        yield module
    finally:
        sys.modules.pop(name, None)


@pytest.fixture
def verifier_module() -> Iterator[ModuleType]:
    name = "raos_test_st0104_verifier"
    module = load_module(VERIFIER_PATH, name)
    try:
        yield module
    finally:
        sys.modules.pop(name, None)

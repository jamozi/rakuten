"""Shared fixtures for the isolated ST-0105 code-generation suite."""

from __future__ import annotations

from collections.abc import Iterator
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
sys.path.insert(0, str(PYTHON_ROOT))
sys.dont_write_bytecode = True

from raos.shared.contract_repository import ContractRepository  # noqa: E402


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object without accepting a top-level scalar or array."""

    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), path
    return value


@pytest.fixture(scope="session")
def codegen_manifest() -> dict[str, Any]:
    return load_json(REPOSITORY_ROOT / "changes/st-0105/manifest.json")


@pytest.fixture(scope="session")
def contract_repository() -> ContractRepository:
    return ContractRepository(REPOSITORY_ROOT / "contracts/raos-v0.4")


@pytest.fixture(scope="session")
def node_executable() -> Path:
    configured = os.environ.get("NODE") or shutil.which("node")
    if not configured:
        pytest.fail("the pinned Node executable is unavailable")
    candidate = Path(configured).resolve(strict=True)
    result = subprocess.run(
        [str(candidate), "--version"],
        env={"PATH": os.defpath},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "v24.18.1"
    return candidate


@pytest.fixture(scope="session")
def generator_command(node_executable: Path) -> list[str]:
    datamodel_codegen = REPOSITORY_ROOT / ".venv/bin/datamodel-codegen"
    openapi_ts = REPOSITORY_ROOT / "node_modules/@hey-api/openapi-ts/bin/run.js"
    assert datamodel_codegen.is_file() and os.access(datamodel_codegen, os.X_OK)
    assert openapi_ts.is_file()
    return [
        sys.executable,
        str(REPOSITORY_ROOT / "scripts/build_st0105_generated_contracts.py"),
        "--datamodel-codegen",
        str(datamodel_codegen),
        "--node",
        str(node_executable),
        "--openapi-ts",
        str(openapi_ts),
    ]


@pytest.fixture(autouse=True)
def generated_tree_stays_bytecode_free() -> Iterator[None]:
    yield
    assert not list((REPOSITORY_ROOT / "python/raos/generated").rglob("*.pyc"))
    assert not list((REPOSITORY_ROOT / "python/raos/generated").rglob("__pycache__"))

"""Owner-generator and static authority-boundary checks for ST-0503 V2."""

from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_SOURCES = (
    REPOSITORY_ROOT / "python/raos/domain/catalog/catalog_normalization_runtime_v2.py",
    REPOSITORY_ROOT / "python/raos/ports/catalog_normalization_runtime_v2.py",
    REPOSITORY_ROOT
    / "python/raos/application/catalog/catalog_normalization_runtime_v2.py",
    REPOSITORY_ROOT
    / "python/raos/adapters/recorded_catalog_normalization_runtime_v2.py",
    REPOSITORY_ROOT / "python/raos/adapters/sqlite_catalog_normalization_runtime_v2.py",
)


def test_owner_generator_check_is_no_write_and_current() -> None:
    before = {
        path: path.read_bytes()
        for path in (
            REPOSITORY_ROOT
            / "changes/st-0503/generated/catalog-normalization-runtime.v2.json",
            REPOSITORY_ROOT / "changes/st-0503/manifest.v2.json",
        )
    }
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": "python",
    }
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_st0503_catalog_normalization_runtime.py",
            "--check",
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert {path: path.read_bytes() for path in before} == before


def test_runtime_has_no_network_credential_worker_or_ranking_surface() -> None:
    forbidden_import_roots = {
        "aiohttp",
        "http",
        "httpx",
        "requests",
        "socket",
        "subprocess",
        "urllib.request",
    }
    forbidden_definitions = {
        "activate",
        "fetch",
        "publish",
        "rank",
        "recommend",
        "run_worker",
        "send",
    }
    imported: set[str] = set()
    definitions: set[str] = set()
    for path in RUNTIME_SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.add(node.module)
            elif isinstance(
                node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
            ):
                definitions.add(node.name.casefold())

    assert imported.isdisjoint(forbidden_import_roots)
    assert definitions.isdisjoint(forbidden_definitions)

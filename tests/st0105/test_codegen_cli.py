"""CLI coverage for ST-0105 through the shared build entrypoint."""

from __future__ import annotations

import json
import subprocess
import sys

from .support import REPOSITORY_ROOT


def test_registry_exposes_codegen_semantics_without_absolute_tool_paths() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/raos_build.py", "registry", "--json"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    registry = json.loads(result.stdout)
    owner = next(
        item
        for item in registry["owners"]
        if item["owner_id"] == "build_st0105_generated_contracts"
    )
    assert owner["owner_version"] == 2
    assert owner["supports_check"] is True
    assert all(not value.startswith("/") for value in owner["outputs"])
    assert all(input_["uri"].startswith("repo://") for input_ in owner["inputs"])


def test_story_specific_codegen_wrapper_is_retired() -> None:
    assert not (REPOSITORY_ROOT / "scripts/codegen_toolchain.sh").exists()

"""Tracked ownership regression for the exact ST-0105 Python namespace."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import subprocess
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPOSITORY_ROOT / "changes/st-0105/manifest.json"
GENERATED_PREFIX = "python/raos/generated/"


def _mapping(value: object) -> dict[str, Any]:
    assert isinstance(value, dict)
    assert all(isinstance(key, str) for key in value)
    return value


def _tracked_generated_files() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "python/raos/generated"],
        cwd=REPOSITORY_ROOT,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
        check=False,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    paths = {
        value.decode("utf-8", errors="strict")
        for value in result.stdout.split(b"\0")
        if value
    }
    return {path for path in paths if (REPOSITORY_ROOT / path).is_file()}


def test_st0105_exclusively_owns_tracked_python_generated_namespace() -> None:
    manifest = _mapping(json.loads(MANIFEST_PATH.read_bytes()))
    outputs = _mapping(manifest.get("outputs"))
    artifacts = outputs.get("artifacts")
    assert isinstance(artifacts, list)

    expected: set[str] = set()
    for raw in artifacts:
        artifact = _mapping(raw)
        path = artifact.get("path")
        assert isinstance(path, str)
        if not path.startswith(GENERATED_PREFIX):
            continue
        relative = PurePosixPath(path)
        assert not relative.is_absolute()
        assert relative.as_posix() == path
        assert all(part not in {"", ".", ".."} for part in relative.parts)
        expected.add(path)

    assert expected
    assert _tracked_generated_files() == expected

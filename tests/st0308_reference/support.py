"""Shared fixtures for the isolated ST-0308 persistence-reference suite."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import build_st0308_persistence_boundary_reference as builder  # noqa: E402
from scripts import build_st1506_production_deployment as secure_io  # noqa: E402


def _copy_file(source_root: Path, target_root: Path, relative: Path) -> None:
    source = source_root / relative
    target = target_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _st0105_output_paths() -> tuple[Path, ...]:
    raw = json.loads(
        (REPO_ROOT / "changes/st-0105/manifest.json").read_text(encoding="utf-8")
    )
    document = cast(dict[str, Any], raw)
    outputs = cast(dict[str, Any], document["outputs"])
    artifacts = cast(list[dict[str, Any]], outputs["artifacts"])
    return tuple(Path(cast(str, artifact["path"])) for artifact in artifacts)


def _materialized_paths() -> tuple[Path, ...]:
    bound = (
        *(Path(path) for path, _size, _digest in builder.SOURCE_ROWS),
        *(Path(path) for path, _size, _digest in builder.ST0304_ROWS),
        *(Path(path) for path, _size, _digest in builder.ST0105_ROWS),
        Path(builder.SECURE_HELPER_ROW[0]),
        *builder.SOURCE_ARTIFACT_PATHS,
        *_st0105_output_paths(),
        *builder.OWNER_OUTPUT_PATHS,
    )
    return tuple(dict.fromkeys(bound))


def _tree_snapshot(root: Path) -> dict[str, tuple[str, int, int, int, str | None]]:
    snapshot: dict[str, tuple[str, int, int, int, str | None]] = {}
    for path in sorted(root.rglob("*")):
        metadata = path.lstat()
        if stat.S_ISREG(metadata.st_mode):
            kind = "file"
            digest: str | None = hashlib.sha256(path.read_bytes()).hexdigest()
        elif stat.S_ISDIR(metadata.st_mode):
            kind = "directory"
            digest = None
        elif stat.S_ISLNK(metadata.st_mode):
            kind = "symlink"
            digest = None
        else:
            kind = "other"
            digest = None
        snapshot[path.relative_to(root).as_posix()] = (
            kind,
            stat.S_IMODE(metadata.st_mode),
            metadata.st_size,
            metadata.st_mtime_ns,
            digest,
        )
    return snapshot


@dataclass(frozen=True, slots=True)
class RepositoryHarness:
    """A disposable exact copy of every file the owner builder reads."""

    root: Path

    def load_contract(self) -> dict[str, Any]:
        loaded = secure_io.load_yaml(self.root / builder.CONTRACT_PATH)
        return cast(dict[str, Any], copy.deepcopy(loaded))

    def write_contract(self, document: dict[str, Any]) -> None:
        rendered = yaml.dump(
            document,
            Dumper=secure_io.NoAliasDumper,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
        (self.root / builder.CONTRACT_PATH).write_text(rendered, encoding="utf-8")

    def snapshot(self) -> dict[str, tuple[str, int, int, int, str | None]]:
        return _tree_snapshot(self.root)


@pytest.fixture
def contract() -> dict[str, Any]:
    loaded = secure_io.load_yaml(REPO_ROOT / builder.CONTRACT_PATH)
    return cast(dict[str, Any], copy.deepcopy(loaded))


@pytest.fixture
def repository_harness(tmp_path: Path) -> RepositoryHarness:
    root = tmp_path / "repository"
    root.mkdir(mode=0o755)
    for relative in _materialized_paths():
        _copy_file(REPO_ROOT, root, relative)
    return RepositoryHarness(root)

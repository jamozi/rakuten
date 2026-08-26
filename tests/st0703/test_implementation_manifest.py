"""Deterministic installed-artifact checks for ST-0703."""

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil

import pytest
import yaml

from .support import REPOSITORY_ROOT
from scripts import build_st0703_recorded_adapter as generator


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_repository(tmp_path: Path) -> Path:
    target = tmp_path / "repository"
    contract = yaml.safe_load(
        (REPOSITORY_ROOT / generator.CONTRACT_PATH).read_text(encoding="utf-8")
    )
    paths = {
        generator.CONTRACT_PATH,
        generator.PYPROJECT_PATH,
        generator.UV_LOCK_PATH,
        generator.UV_CONFIG_PATH,
        generator.GENERATED_REGISTRY_PATH,
        generator.MANIFEST_PATH,
        *generator.IMPLEMENTATION_SOURCE_PATHS,
        *generator.PREDECESSOR_MANIFEST_PROJECTION_SHA256,
        *(generator.FIXTURE_ROOT / spec.path for spec in generator.FIXTURE_SPECS),
    }
    for entries in contract["provenance"].values():
        for entry in entries:
            paths.add(Path(entry["uri"].removeprefix("repo://")))
    for relative in paths:
        source = REPOSITORY_ROOT / relative
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return target


def test_installed_registry_and_manifest_are_current() -> None:
    expected = generator.check(REPOSITORY_ROOT)

    assert generator.check_installed(REPOSITORY_ROOT) == expected
    assert _sha256(REPOSITORY_ROOT / generator.GENERATED_REGISTRY_PATH) == expected


def test_check_installed_is_read_only() -> None:
    paths = (
        REPOSITORY_ROOT / generator.GENERATED_REGISTRY_PATH,
        REPOSITORY_ROOT / generator.MANIFEST_PATH,
    )
    before = {path: (path.stat().st_mtime_ns, path.read_bytes()) for path in paths}

    generator.check_installed(REPOSITORY_ROOT)

    after = {path: (path.stat().st_mtime_ns, path.read_bytes()) for path in paths}
    assert after == before


def test_installed_registry_drift_fails_closed(tmp_path: Path) -> None:
    root = _copy_repository(tmp_path)
    registry = root / generator.GENERATED_REGISTRY_PATH
    registry.write_bytes(registry.read_bytes() + b"\n")

    with pytest.raises(RuntimeError, match="generated artifact drift"):
        generator.check_installed(root)


def test_generate_repairs_only_owned_outputs(tmp_path: Path) -> None:
    root = _copy_repository(tmp_path)
    sentinel = root / "unrelated-sentinel.txt"
    sentinel.write_text("unchanged\n", encoding="utf-8")
    (root / generator.GENERATED_REGISTRY_PATH).unlink()
    (root / generator.MANIFEST_PATH).unlink()

    digest = generator.generate(root)

    assert digest == generator.check(root)
    assert generator.check_installed(root) == digest
    assert sentinel.read_text(encoding="utf-8") == "unchanged\n"

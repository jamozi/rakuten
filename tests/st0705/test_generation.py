"""Deterministic owner generation assertions for ST-0705."""

from __future__ import annotations

import json
from pathlib import Path
import stat

import pytest
import yaml

from .support import MANIFEST, run_builder
from scripts import build_st0705_ai_output_validation_reference_plan as generator


def _snapshot(path: Path) -> tuple[bytes, int, int]:
    metadata = path.stat()
    return path.read_bytes(), metadata.st_mtime_ns, stat.S_IMODE(metadata.st_mode)


def test_render_is_deterministic_and_matches_installed_outputs() -> None:
    first = generator.render_outputs()
    second = generator.render_outputs()
    assert first == second
    for relative, expected in first.items():
        assert (generator.REPO_ROOT / relative).read_bytes() == expected


def test_default_generate_and_check_cli_are_closed() -> None:
    generated = run_builder()
    checked = run_builder("--check")
    assert generated.returncode == 0, generated.stderr or generated.stdout
    assert checked.returncode == 0, checked.stderr or checked.stdout
    assert generator.main(["--check"]) == 0
    for arguments in (("--check=yes",), ("--unknown",), ("--check", "extra")):
        completed = run_builder(*arguments)
        assert completed.returncode == 2
        assert not completed.stdout
        assert not completed.stderr


def test_check_mode_is_an_exact_no_write_snapshot() -> None:
    paths = [generator.REPO_ROOT / relative for relative in generator.GENERATED_PATHS]
    before = {path: _snapshot(path) for path in paths}
    generator.build(check=True)
    after = {path: _snapshot(path) for path in paths}
    assert after == before


def test_isolated_publication_is_atomic_0644_and_checkable(
    isolated_repository: Path,
) -> None:
    generator.build(isolated_repository)
    for relative in generator.GENERATED_PATHS:
        path = isolated_repository / relative
        assert path.is_file()
        assert not path.is_symlink()
        assert stat.S_IMODE(path.stat().st_mode) == 0o644
        assert not tuple(path.parent.glob(f".{path.name}.*.tmp"))
    generator.build(isolated_repository, check=True)


def test_manifest_v2_uses_semantic_inputs_and_output_integrity() -> None:
    manifest = yaml.safe_load(MANIFEST.read_bytes())
    reference = (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    assert manifest["document"]["version"] == "2.0.0"
    assert manifest["semantic_inputs"]["canonical_package"] == (
        generator.expected_authority_manifest_rows()
    )
    assert manifest["semantic_inputs"]["predecessors"] == (
        generator.expected_predecessor_manifest_rows()
    )
    assert all(
        "sha256" not in row for row in manifest["semantic_inputs"]["predecessors"]
    )
    assert manifest["outputs"] == [
        {
            "uri": f"repo://{generator.REFERENCE_PLAN_PATH.as_posix()}",
            "bytes": len(reference),
            "sha256": generator._sha256(reference),
        }
    ]


def test_reference_plan_is_canonical_utf8_json() -> None:
    content = (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    assert content.endswith(b"\n")
    assert b"\r" not in content
    parsed = json.loads(content)
    assert content == generator._json_bytes(parsed)


def test_generated_or_manifest_drift_is_rejected_without_repair(
    isolated_repository: Path,
) -> None:
    generator.build(isolated_repository)
    for relative in generator.GENERATED_PATHS:
        path = isolated_repository / relative
        path.write_bytes(path.read_bytes() + b"drift")
        before = _snapshot(path)
        with pytest.raises(generator.AiOutputValidationReferenceError):
            generator.build(isolated_repository, check=True)
        assert _snapshot(path) == before
        generator.build(isolated_repository)

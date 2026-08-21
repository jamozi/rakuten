"""Deterministic owner generation tests for ST-0505."""

from __future__ import annotations

import json
from pathlib import Path
import stat

import pytest
import yaml

from scripts import build_st0505_rakuten_live_smoke_reference_plan as generator


def test_render_is_deterministic_and_matches_installed_outputs() -> None:
    first = generator.render_outputs()
    second = generator.render_outputs()
    assert first == second
    for relative, expected in first.items():
        assert (generator.REPO_ROOT / relative).read_bytes() == expected


def test_check_mode_accepts_exact_outputs() -> None:
    assert generator.main(["--check"]) == 0


def _snapshot(path: Path) -> tuple[bytes, int, int]:
    metadata = path.stat()
    return path.read_bytes(), metadata.st_mtime_ns, stat.S_IMODE(metadata.st_mode)


def test_check_mode_is_a_no_write_snapshot() -> None:
    paths = [generator.REPO_ROOT / relative for relative in generator.GENERATED_PATHS]
    before = {path: _snapshot(path) for path in paths}
    generator.build(check=True)
    after = {path: _snapshot(path) for path in paths}
    assert after == before


def test_isolated_publication_is_atomic_0644_and_adjacent(
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


def test_manifest_binds_sources_predecessor_generated_plan_and_helper() -> None:
    manifest = yaml.safe_load(
        (generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes()
    )
    reference = (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    assert manifest["document"]["version"] == "1.2.6"
    assert manifest["source_artifact_count"] == len(generator.SOURCE_PATHS)
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_PATHS
    ]
    assert manifest["provenance"]["predecessor_commit"] == (
        generator.PREDECESSOR_COMMIT
    )
    assert manifest["provenance"]["predecessor_inputs"] == (
        generator._expected_predecessor_artifacts()
    )
    assert len(manifest["provenance"]["predecessor_inputs"]) == 11
    assert manifest["generated_artifacts"] == [
        {
            "uri": f"repo://{generator.REFERENCE_PLAN_PATH.as_posix()}",
            "bytes": len(reference),
            "sha256": generator._sha256(reference),
        }
    ]
    assert manifest["provenance"]["implementation_helper"] == {
        "uri": f"repo://{generator.HELPER_PATH.as_posix()}",
        "sha256": generator.HELPER_SHA256,
    }
    assert manifest["provenance"]["credential_intake_design_handoff"] == {
        "uri": f"repo://{generator.DESIGN_HANDOFF_PATH.as_posix()}",
        "bytes": generator.DESIGN_HANDOFF_BYTES,
        "sha256": generator.DESIGN_HANDOFF_SHA256,
    }
    assert manifest["boundary"]["credential_intake_interface"] == (
        "LOCAL_IMPLEMENTATION_AVAILABLE"
    )
    assert manifest["boundary"]["credential_values"] == "NOT_RECEIVED_OR_READ"
    assert manifest["boundary"]["real_credential_store"] == "NOT_EXECUTED"


def test_generated_or_manifest_drift_is_rejected(
    isolated_repository: Path,
) -> None:
    generator.build(isolated_repository)
    for relative in generator.GENERATED_PATHS:
        path = isolated_repository / relative
        original = path.read_bytes()
        path.write_bytes(original + b"drift")
        with pytest.raises(generator.RakutenLiveSmokeReferenceError):
            generator.build(isolated_repository, check=True)
        path.write_bytes(original)


def test_reference_plan_bytes_are_canonical_utf8_json() -> None:
    content = (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    assert content.endswith(b"\n")
    assert b"\r" not in content
    parsed = json.loads(content)
    assert content == generator._json_bytes(parsed)


def test_cli_rejects_every_argument_except_exact_check() -> None:
    for arguments in (["--check=yes"], ["--unknown"], ["--check", "extra"]):
        with pytest.raises(SystemExit) as caught:
            generator.parse_args(arguments)
        assert caught.value.code == 2

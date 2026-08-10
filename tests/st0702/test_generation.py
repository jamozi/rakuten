"""Deterministic owner generation tests for ST-0702."""

from __future__ import annotations

import json
from pathlib import Path
import stat

import pytest
import yaml

from scripts import build_st0702_context_pack_reference_plan as generator


def test_render_is_deterministic_matches_outputs_and_check_is_no_write() -> None:
    first = generator.render_outputs()
    second = generator.render_outputs()
    assert first == second
    paths = [generator.REPO_ROOT / relative for relative in generator.GENERATED_PATHS]
    before = {
        path: (
            path.read_bytes(),
            path.stat().st_mtime_ns,
            stat.S_IMODE(path.stat().st_mode),
        )
        for path in paths
    }
    for relative, expected in first.items():
        assert (generator.REPO_ROOT / relative).read_bytes() == expected
    generator.build(check=True)
    after = {
        path: (
            path.read_bytes(),
            path.stat().st_mtime_ns,
            stat.S_IMODE(path.stat().st_mode),
        )
        for path in paths
    }
    assert after == before
    assert generator.main(["--check"]) == 0


def test_isolated_publication_is_atomic_mode_0644_and_checkable(
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


def test_manifest_binds_exact_sources_predecessors_and_generated_plan() -> None:
    manifest = yaml.safe_load(
        (generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes()
    )
    reference = (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    assert manifest["source_artifact_count"] == len(generator.SOURCE_PATHS) == 7
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_PATHS
    ]
    assert manifest["provenance"]["predecessors"] == (
        generator._predecessor_manifest_rows()
    )
    assert [len(row["inputs"]) for row in manifest["provenance"]["predecessors"]] == [
        9,
        9,
    ]
    assert manifest["generated_artifacts"] == [
        {
            "uri": f"repo://{generator.REFERENCE_PLAN_PATH.as_posix()}",
            "bytes": len(reference),
            "sha256": generator._sha256(reference),
        }
    ]
    boundary = manifest["boundary"]
    assert boundary["task_count"] == 12
    assert boundary["activation_inferred"] is False
    assert boundary["source_packet_count"] is None
    assert boundary["fact_count"] is None
    assert boundary["build_permitted"] is False
    assert boundary["provider_call_permitted"] is False
    assert boundary["runtime_actions"] == "NOT_EXECUTED"
    assert boundary["action_count_total"] == 0


def test_reference_json_is_stable_utf8_and_cli_is_closed() -> None:
    content = (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    assert content.endswith(b"\n")
    assert b"\r" not in content
    parsed = json.loads(content)
    assert content == generator._json_bytes(parsed)
    for arguments in (["--check=yes"], ["--unknown"], ["--check", "extra"]):
        with pytest.raises(SystemExit) as caught:
            generator.parse_args(arguments)
        assert caught.value.code == 2

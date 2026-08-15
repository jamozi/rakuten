"""Generation, manifest, atomic-mode, and no-write checks for ST-0308."""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path
from typing import Any, cast

import pytest

from conftest import RepositoryHarness
from scripts import build_st0308_persistence_boundary_reference as builder
from scripts import build_st1506_production_deployment as secure_io


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_committed_outputs_equal_deterministic_render() -> None:
    first = builder.render_outputs(REPO_ROOT)
    second = builder.render_outputs(REPO_ROOT)

    assert tuple(first) == builder.OWNER_OUTPUT_PATHS
    assert first == second
    for relative, expected in first.items():
        assert (REPO_ROOT / relative).read_bytes() == expected


def test_manifest_has_eight_sources_one_json_and_excludes_itself() -> None:
    raw = secure_io.load_yaml(REPO_ROOT / builder.MANIFEST_PATH)
    manifest = cast(dict[str, Any], raw)
    source_rows = cast(list[dict[str, Any]], manifest["source_artifacts"])
    generated_rows = cast(list[dict[str, Any]], manifest["generated_artifacts"])

    assert tuple(manifest) == (
        "document",
        "source_artifacts",
        "generated_artifacts",
        "boundary",
    )
    assert manifest["document"]["source_artifact_count"] == 8
    assert manifest["document"]["generated_artifact_count"] == 1
    assert manifest["document"]["manifest_self_excluded"] is True
    assert len(source_rows) == 8
    assert len(generated_rows) == 1
    assert [row["uri"] for row in source_rows] == [
        f"repo://{path.as_posix()}" for path in builder.SOURCE_ARTIFACT_PATHS
    ]
    assert generated_rows[0]["uri"] == f"repo://{builder.REFERENCE_PLAN_PATH}"
    assert all(tuple(row) == ("uri", "bytes", "sha256") for row in source_rows)
    assert tuple(generated_rows[0]) == ("uri", "bytes", "sha256")
    assert f"repo://{builder.MANIFEST_PATH}" not in {
        row["uri"] for row in (*source_rows, *generated_rows)
    }
    for row in (*source_rows, *generated_rows):
        relative = Path(cast(str, row["uri"]).removeprefix("repo://"))
        content = (REPO_ROOT / relative).read_bytes()
        assert row["bytes"] == len(content)
        assert row["sha256"] == hashlib.sha256(content).hexdigest()


def test_reference_plan_is_strict_json_with_exact_top_level_order() -> None:
    content = (REPO_ROOT / builder.REFERENCE_PLAN_PATH).read_bytes()
    document: dict[str, Any] = json.loads(content)

    assert content.endswith(b"\n")
    assert tuple(document) == builder.REFERENCE_PLAN_KEYS
    assert document["prohibited_interpretations"] == list(
        builder.PROHIBITED_INTERPRETATIONS
    )


def test_atomic_generation_sets_exact_owner_mode(
    repository_harness: RepositoryHarness,
) -> None:
    for relative in builder.OWNER_OUTPUT_PATHS:
        target = repository_harness.root / relative
        target.chmod(0o600)

    builder.build(repository_harness.root)

    for relative in builder.OWNER_OUTPUT_PATHS:
        target = repository_harness.root / relative
        assert stat.S_IMODE(target.lstat().st_mode) == 0o644
    builder.build(repository_harness.root, check=True)


def test_check_is_whole_tree_no_write_for_type_mode_size_mtime_and_hash(
    repository_harness: RepositoryHarness,
) -> None:
    builder.build(repository_harness.root)
    before = repository_harness.snapshot()

    builder.build(repository_harness.root, check=True)

    assert repository_harness.snapshot() == before


def test_check_rejects_any_reference_plan_drift(
    repository_harness: RepositoryHarness,
) -> None:
    builder.build(repository_harness.root)
    target = repository_harness.root / builder.REFERENCE_PLAN_PATH
    target.write_bytes(target.read_bytes() + b" ")

    with pytest.raises(builder.PersistenceReferenceError, match="OWNER_OUTPUT_DRIFT"):
        builder.build(repository_harness.root, check=True)


def test_check_reads_output_content_and_mode_from_one_descriptor_snapshot(
    repository_harness: RepositoryHarness,
) -> None:
    builder.build(repository_harness.root)
    target = repository_harness.root / builder.REFERENCE_PLAN_PATH
    target.chmod(0o600)
    with pytest.raises(builder.PersistenceReferenceError) as captured:
        builder.build(repository_harness.root, check=True)
    assert captured.value.code == "OWNER_OUTPUT_MODE_INVALID"


def test_cli_accepts_only_empty_or_exact_check() -> None:
    assert builder.parse_args([]).check is False
    assert builder.parse_args(["--check"]).check is True
    for arguments in (["--help"], ["--check", "extra"], ["--unknown"], ["-c"]):
        with pytest.raises(SystemExit) as raised:
            builder.parse_args(arguments)
        assert raised.value.code == 2

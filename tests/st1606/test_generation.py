from __future__ import annotations

import json
import os
from pathlib import Path
import stat

import pytest
import yaml

from scripts import build_st1606_backup_restore_drill as builder
from scripts import build_st1505_staging_deployment as base


def _snapshot(root: Path) -> dict[Path, tuple[bytes, int, int]]:
    return {
        path.relative_to(root): (
            path.read_bytes(),
            path.stat().st_mtime_ns,
            stat.S_IMODE(path.stat().st_mode),
        )
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def test_owner_generation_is_deterministic_and_check_is_no_write(
    repository_copy: Path,
) -> None:
    builder.build(repository_copy)
    first = {
        path: (repository_copy / path).read_bytes() for path in builder.GENERATED_PATHS
    }
    before = _snapshot(repository_copy)
    builder.build(repository_copy, check=True)
    after = _snapshot(repository_copy)
    assert before == after
    builder.build(repository_copy)
    assert first == {
        path: (repository_copy / path).read_bytes() for path in builder.GENERATED_PATHS
    }


def test_manifest_records_exact_owner_inventory(repository_copy: Path) -> None:
    builder.build(repository_copy)
    manifest = yaml.safe_load((repository_copy / builder.MANIFEST_PATH).read_text())
    assert manifest["source_artifact_count"] == len(builder.SOURCE_PATHS)
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in builder.SOURCE_PATHS
    ]
    assert manifest["generated_artifact_count"] == 1
    assert manifest["generated_artifacts"][0]["uri"] == (
        f"repo://{builder.REFERENCE_PLAN_PATH.as_posix()}"
    )
    assert manifest["boundary"]["restore_drill"] == "NOT_EXECUTED"
    assert manifest["boundary"]["st_1607_eligible"] is False


def test_generated_plan_has_no_selected_or_executable_value(
    repository_copy: Path,
) -> None:
    builder.build(repository_copy)
    plan = json.loads((repository_copy / builder.REFERENCE_PLAN_PATH).read_text())
    assert plan["executable"] is False
    assert all(value in (None, []) for value in plan["selected_bindings"].values())
    assert all(
        type(value) is int and value == 0 for value in plan["action_counts"].values()
    )
    assert plan["activation"]["enabled"] is False
    assert plan["evidence_boundary"]["restore_success_claim"] is False


def test_check_detects_generated_output_drift(repository_copy: Path) -> None:
    builder.build(repository_copy)
    (repository_copy / builder.REFERENCE_PLAN_PATH).write_text("{}\n")
    with pytest.raises(builder.BackupRestoreReferenceError) as error:
        builder.build(repository_copy, check=True)
    assert error.value.code == "GENERATED_OUTPUT_DRIFT"


def test_source_hash_drift_fails_closed(repository_copy: Path) -> None:
    source = repository_copy / next(iter(builder.EXPECTED_SOURCE_HASHES))
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(builder.BackupRestoreReferenceError) as error:
        builder.render_outputs(repository_copy)
    assert error.value.code == "SOURCE_HASH_DRIFT"


def test_predecessor_hash_drift_fails_closed(repository_copy: Path) -> None:
    relative = Path(next(iter(builder.EXPECTED_PREDECESSOR_HASHES)))
    target = repository_copy / relative
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(builder.BackupRestoreReferenceError) as error:
        builder.render_outputs(repository_copy)
    assert error.value.code == "PREDECESSOR_HASH_DRIFT"


def test_symlinked_output_target_is_rejected(repository_copy: Path) -> None:
    builder.build(repository_copy)
    output = repository_copy / builder.REFERENCE_PLAN_PATH
    output.unlink()
    output.symlink_to(repository_copy / builder.CONTRACT_PATH)
    with pytest.raises(base_exception_types()):
        builder.build(repository_copy)


def test_symlinked_output_ancestor_is_rejected(repository_copy: Path) -> None:
    generated = repository_copy / builder.REFERENCE_PLAN_PATH.parent
    generated.parent.mkdir(parents=True, exist_ok=True)
    if generated.exists():
        os.rmdir(generated)
    generated.symlink_to(
        repository_copy / "changes/st-1606/contracts", target_is_directory=True
    )
    with pytest.raises(base_exception_types()):
        builder.build(repository_copy)


def base_exception_types() -> tuple[type[BaseException], ...]:
    return (
        builder.BackupRestoreReferenceError,
        base.StagingDeploymentContractError,
    )

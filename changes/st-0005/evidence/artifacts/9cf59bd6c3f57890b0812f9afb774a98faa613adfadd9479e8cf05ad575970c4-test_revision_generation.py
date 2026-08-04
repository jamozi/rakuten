"""Deterministic and owned generation tests for ST-0006."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts import build_st0006_decision_gates as gates


BUNDLE_ROOT = gates.DEFAULT_BUNDLE_ROOT


def tree_snapshot(root: Path) -> dict[str, tuple[str, bytes | str]]:
    result: dict[str, tuple[str, bytes | str]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            result[relative] = ("symlink", os.readlink(path))
        elif path.is_file():
            result[relative] = ("file", path.read_bytes())
        elif path.is_dir():
            result[relative] = ("directory", "")
    return result


def test_committed_generation_has_no_drift() -> None:
    gates.check_generated()


def test_clean_generation_is_byte_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    gates.build(first)
    gates.build(second)
    assert gates.generated_file_map(first) == gates.generated_file_map(second)
    assert gates.generated_file_map(first) == gates.generated_file_map(BUNDLE_ROOT)


def test_generation_failure_preserves_previous_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "owned"
    gates.build(target)
    before = gates.generated_file_map(target)

    def fail_report(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("injected report failure")

    monkeypatch.setattr(gates, "build_gate_report", fail_report)
    with pytest.raises(RuntimeError, match="injected report failure"):
        gates.build(target)
    assert gates.generated_file_map(target) == before


def test_install_failure_restores_previous_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "owned"
    gates.build(target)
    before = gates.generated_file_map(target)
    original_replace = gates.os.replace
    replace_calls = 0

    def fail_after_two_new_installs(
        source: Any,
        destination: Any,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 6:
            raise OSError("injected install failure")
        original_replace(  # type: ignore[arg-type]
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(gates.os, "replace", fail_after_two_new_installs)
    with pytest.raises(OSError, match="injected install failure"):
        gates.build(target)
    assert replace_calls >= 6
    assert gates.generated_file_map(target) == before


def test_keyboard_interrupt_after_new_install_restores_previous_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "owned"
    gates.build(target)
    before = gates.generated_file_map(target)
    original_replace = gates.os.replace
    replace_calls = 0

    def interrupt_after_one_new_install(
        source: Any,
        destination: Any,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 5:
            raise KeyboardInterrupt
        original_replace(  # type: ignore[arg-type]
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(gates.os, "replace", interrupt_after_one_new_install)
    with pytest.raises(KeyboardInterrupt):
        gates.build(target)
    assert replace_calls >= 5
    assert gates.generated_file_map(target) == before


def test_double_failure_retains_recovery_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "owned"
    gates.build(target)
    original_replace = gates.os.replace
    replace_calls = 0

    def fail_install_and_every_rollback(
        source: Any,
        destination: Any,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls >= 6:
            raise OSError("persistent injected replacement failure")
        original_replace(  # type: ignore[arg-type]
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(gates.os, "replace", fail_install_and_every_rollback)
    with pytest.raises(gates.RollbackRecoveryRequired) as failure:
        gates.build(target)
    recovery = failure.value.recovery_path
    assert recovery.is_dir()
    assert (recovery / f"previous-{gates.CONTRACTS_NAME}").is_dir()
    assert (recovery / f"previous-{gates.REPORT_NAME}").is_file()
    assert (recovery / f"previous-{gates.MANIFEST_NAME}").is_file()
    assert "recovery retained" in str(failure.value)


def test_bundle_root_rebinding_cannot_redirect_descriptor_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "owned"
    gates.build(target)
    before = tree_snapshot(target)
    pinned = tmp_path / "pinned-owned"
    outside = tmp_path / "outside"
    (outside / gates.CONTRACTS_NAME).mkdir(parents=True)
    (outside / gates.CONTRACTS_NAME / "sentinel.txt").write_text(
        "outside\n", encoding="utf-8"
    )
    (outside / gates.REPORT_NAME).write_text("outside\n", encoding="utf-8")
    (outside / gates.MANIFEST_NAME).write_text("outside\n", encoding="utf-8")
    outside_before = tree_snapshot(outside)
    original_replace = gates.os.replace
    rebound = False

    def rebind_once(
        source: Any,
        destination: Any,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        nonlocal rebound
        if not rebound:
            rebound = True
            target.rename(pinned)
            target.symlink_to(outside, target_is_directory=True)
        original_replace(  # type: ignore[arg-type]
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(gates.os, "replace", rebind_once)
    with pytest.raises(RuntimeError, match="bundle root"):
        gates.build(target)
    assert rebound
    assert tree_snapshot(outside) == outside_before
    target.unlink()
    pinned.rename(target)
    assert tree_snapshot(target) == before


def test_staging_root_rebinding_is_rejected_before_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "owned"
    gates.build(target)
    before = tree_snapshot(target)
    original_install = gates.install_staged_generation
    rebound = False

    def rebind_stage(staged_root: Path, bundle_root: Path, **kwargs: Any) -> None:
        nonlocal rebound
        rebound = True
        staged_root.rename(staged_root.with_name("rebound-original"))
        staged_root.mkdir()
        original_install(staged_root, bundle_root, **kwargs)

    monkeypatch.setattr(gates, "install_staged_generation", rebind_stage)
    with pytest.raises(RuntimeError, match="identity changed"):
        gates.build(target)
    assert rebound
    assert tree_snapshot(target) == before


def test_staged_content_mutation_is_rejected_without_replacing_previous_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "owned"
    gates.build(target)
    before = tree_snapshot(target)
    original_install = gates.install_staged_generation
    mutated = False

    def mutate_stage(staged_root: Path, bundle_root: Path, **kwargs: Any) -> None:
        nonlocal mutated
        mutated = True
        (staged_root / gates.REPORT_NAME).write_text(
            "contradictory: true\n", encoding="utf-8"
        )
        original_install(staged_root, bundle_root, **kwargs)

    monkeypatch.setattr(gates, "install_staged_generation", mutate_stage)
    with pytest.raises(RuntimeError, match="changed before install"):
        gates.build(target)
    assert mutated
    assert tree_snapshot(target) == before


def test_builder_rejects_foreign_partial_and_symlinked_destinations(
    tmp_path: Path,
) -> None:
    partial = tmp_path / "partial"
    partial.mkdir()
    (partial / gates.REPORT_NAME).write_text("document: {}\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="partial"):
        gates.build(partial)

    foreign = tmp_path / "foreign"
    (foreign / gates.CONTRACTS_NAME).mkdir(parents=True)
    (foreign / gates.REPORT_NAME).write_text("document: {}\n", encoding="utf-8")
    (foreign / gates.MANIFEST_NAME).write_text(
        "document:\n  id: FOREIGN\n", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="not owned"):
        gates.build(foreign)

    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(RuntimeError, match="unsafe"):
        gates.build(linked)

    unowned = tmp_path / "unowned"
    unowned.mkdir()
    (unowned / "foreign.txt").write_text("foreign\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="unowned top-level"):
        gates.build(unowned)


def test_owned_tree_hash_drift_and_unlisted_file_are_rejected(tmp_path: Path) -> None:
    target = tmp_path / "owned"
    gates.build(target)
    (target / gates.REPORT_NAME).write_text("drift\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="hash drift"):
        gates.build(target)

    target = tmp_path / "second"
    gates.build(target)
    (target / gates.CONTRACTS_NAME / "unlisted.txt").write_text(
        "foreign\n", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="unowned or missing"):
        gates.build(target)

    target = tmp_path / "third"
    gates.build(target)
    (target / gates.CONTRACTS_NAME / "unlisted-directory").mkdir()
    with pytest.raises(RuntimeError, match="unowned directory"):
        gates.build(target)


def test_forged_manifest_cannot_expand_generated_ownership(tmp_path: Path) -> None:
    target = tmp_path / "owned"
    gates.build(target)
    foreign = target / gates.CONTRACTS_NAME / "foreign.txt"
    content = b"foreign but self-consistent\n"
    foreign.write_bytes(content)
    manifest_path = target / gates.MANIFEST_NAME
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["generated_artifacts"].append(
        {
            "path": "changes/st-0006/contracts/foreign.txt",
            "bytes": len(content),
            "sha256": gates.sha256_bytes(content),
        }
    )
    manifest["generated_artifact_count"] += 1
    gates.write_yaml(manifest_path, manifest)

    with pytest.raises(RuntimeError, match="cannot expand"):
        gates.build(target)
    assert foreign.read_bytes() == content


def test_manifest_hashes_exact_source_input_and_generated_inventory() -> None:
    manifest = yaml.safe_load(
        (BUNDLE_ROOT / gates.MANIFEST_NAME).read_text(encoding="utf-8")
    )
    for section in ("source_artifacts", "generated_artifacts"):
        for entry in manifest[section]:
            path = gates.REPO_ROOT / entry["path"]
            assert path.is_file() and not path.is_symlink()
            assert path.stat().st_size == entry["bytes"]
            assert gates.sha256_file(path) == entry["sha256"]
    assert {entry["path"] for entry in manifest["provenance"]["pinned_inputs"]} == set(
        gates.PINNED_INPUT_HASHES
    )
    assert "changes/st-0006/manifest.yaml" not in {
        entry["path"] for entry in manifest["generated_artifacts"]
    }
    assert manifest["generated_artifact_count"] == 4


def test_manifest_source_inventory_is_exact() -> None:
    manifest = yaml.safe_load(
        (BUNDLE_ROOT / gates.MANIFEST_NAME).read_text(encoding="utf-8")
    )
    actual = {entry["path"] for entry in manifest["source_artifacts"]}
    expected = {gates.relative_repo_path(path) for path in gates.source_paths()}
    assert actual == expected
    assert gates.GENERATOR_PATH in actual
    assert "scripts/import_raos_design.py" in actual
    assert "tests/st0006/test_decision_loader.py" in actual


def test_building_temp_bundle_does_not_change_st0005(tmp_path: Path) -> None:
    st0005 = gates.REPO_ROOT / "changes" / "st-0005"
    before = tree_snapshot(st0005)
    gates.build(tmp_path / "bundle")
    assert tree_snapshot(st0005) == before


def test_cli_validate_check_and_custom_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gates.main(["--validate-decisions"]) == 0
    validation = capsys.readouterr()
    lines = validation.out.splitlines()
    assert len(lines) == 1
    result = json.loads(lines[0])
    assert result == {
        "blocked_targets": 6,
        "command_status": "PASS",
        "decisions": 15,
        "mode": "validate-decisions",
        "open_decision_check": "BLOCKED",
        "release_authorized": False,
        "status": "EVALUATED",
        "story_id": "ST-0006",
        "unresolved_blocking": 14,
    }
    assert validation.err == ""

    assert gates.main(["--check"]) == 0
    checked = capsys.readouterr()
    checked_lines = checked.out.splitlines()
    assert len(checked_lines) == 1
    checked_result = json.loads(checked_lines[0])
    assert checked_result["command_status"] == "PASS"
    assert checked_result["status"] == "EVALUATED"
    assert checked_result["mode"] == "check"
    assert checked_result["open_decision_check"] == "BLOCKED"
    assert checked_result["release_authorized"] is False
    assert checked.err == ""

    custom = tmp_path / "custom"
    assert gates.main(["--output", str(custom)]) == 1
    rejected = capsys.readouterr()
    assert rejected.out == ""
    assert "custom output is forbidden" in rejected.err
    assert not custom.exists()

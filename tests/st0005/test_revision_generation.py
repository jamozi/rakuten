"""Deterministic, owned, failure-atomic ST-0005 generation."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from scripts import build_st0005_status as status


BUNDLE_ROOT = status.REPO_ROOT / "changes" / "st-0005"


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
    status.check_generated()


def test_clean_generation_is_byte_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    status.build(first)
    status.build(second)
    assert status.generated_file_map(first) == status.generated_file_map(second)
    assert status.generated_file_map(first) == status.generated_file_map(BUNDLE_ROOT)


def test_generation_failure_preserves_previous_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "owned"
    status.build(target)
    before = status.generated_file_map(target)

    def fail_overlay(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("injected overlay failure")

    monkeypatch.setattr(status, "build_overlay", fail_overlay)
    with pytest.raises(RuntimeError, match="injected overlay failure"):
        status.build(target)
    assert status.generated_file_map(target) == before


def test_install_failure_restores_previous_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "owned"
    status.build(target)
    before = status.generated_file_map(target)
    real_replace = status.os.replace
    injected = False

    def fail_manifest_once(source: object, destination: object) -> None:
        nonlocal injected
        source_path = Path(source)  # type: ignore[arg-type]
        if not injected and source_path.name == status.MANIFEST_NAME:
            injected = True
            raise OSError("injected install failure")
        real_replace(source, destination)  # type: ignore[arg-type]

    monkeypatch.setattr(status.os, "replace", fail_manifest_once)
    with pytest.raises(OSError, match="injected install failure"):
        status.build(target)
    assert injected
    assert status.generated_file_map(target) == before


def test_builder_rejects_unowned_or_symlinked_destination(
    tmp_path: Path,
) -> None:
    foreign = tmp_path / "foreign"
    (foreign / "contracts").mkdir(parents=True)
    (foreign / status.OVERLAY_NAME).write_text("document: {}\n", encoding="utf-8")
    (foreign / status.MANIFEST_NAME).write_text(
        "document:\n  id: FOREIGN\n", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="not owned"):
        status.build(foreign)

    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(RuntimeError, match="unsafe"):
        status.build(linked)


def test_owned_tree_hash_drift_and_unlisted_file_are_rejected(tmp_path: Path) -> None:
    target = tmp_path / "owned"
    status.build(target)
    (target / status.OVERLAY_NAME).write_text("drift\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="hash drift"):
        status.build(target)

    target = tmp_path / "second"
    status.build(target)
    (target / "contracts" / "unlisted.txt").write_text("foreign\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="unowned or missing"):
        status.build(target)


def test_manifest_exactly_hashes_source_and_generated_inventory() -> None:
    manifest = yaml.safe_load(
        (BUNDLE_ROOT / status.MANIFEST_NAME).read_text(encoding="utf-8")
    )
    for section in ("source_artifacts", "generated_artifacts"):
        for entry in manifest[section]:
            path = status.REPO_ROOT / entry["path"]
            assert path.is_file() and not path.is_symlink()
            assert path.stat().st_size == entry["bytes"]
            assert status.sha256_file(path) == entry["sha256"]
    overlay = yaml.safe_load(
        (BUNDLE_ROOT / status.OVERLAY_NAME).read_text(encoding="utf-8")
    )
    assert manifest["status_boundary"] == {
        "canonical_files_modified": False,
        "effective_apply_requests": overlay["counts"]["applied_requests"],
        "proposal_only_requests": overlay["counts"]["proposal_requests"],
        "authoritative_live_apply": "BLOCKED_PENDING_GOVERNANCE",
        "live_apply_activation_requires": ["ST-0006", "ST-0107"],
        "deployment_apply_activation_additionally_requires": [
            "ST-1505",
            "ST-1506",
            "ST-1607",
        ],
        "formal_tst_001": "NOT_EXECUTED",
        "ci_environment": "NOT_CONFIGURED",
        "real_pull_request_evidence": "ABSENT",
    }
    assert manifest["manifest_self_integrity"] == {
        "path": "changes/st-0005/manifest.yaml",
        "included_in_generated_artifacts": False,
        "reason": "SELF_HASH_RECURSION_AVOIDED",
        "verification": "DETERMINISTIC_REGENERATION_BYTE_COMPARE",
    }
    assert "changes/st-0005/manifest.yaml" not in {
        entry["path"] for entry in manifest["generated_artifacts"]
    }


def test_manifest_source_inventory_is_exact_and_includes_validator_dependencies() -> (
    None
):
    manifest = yaml.safe_load(
        (BUNDLE_ROOT / status.MANIFEST_NAME).read_text(encoding="utf-8")
    )
    actual = {entry["path"] for entry in manifest["source_artifacts"]}
    expected = {status.relative_repo_path(path) for path in status.source_paths()}
    assert actual == expected
    assert ".gitattributes" in actual
    assert "docs/README.md" in actual
    assert "scripts/import_raos_design.py" in actual
    assert "tests/test_import_raos_design.py" in actual
    assert ".github/workflows/status-registry.yml" not in actual
    assert "tests/st0005/test_transition_validation.py" in actual
    assert any(
        path.startswith("tests/st0005/fixtures/artifacts/")
        and path.endswith("manifest.json")
        for path in actual
    )


def test_cli_refuses_custom_output(tmp_path: Path) -> None:
    custom = tmp_path / "custom"
    assert status.main(["--output", str(custom)]) == 1
    assert not custom.exists()

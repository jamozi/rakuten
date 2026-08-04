"""Deterministic, pinned, path-safe, failure-atomic ST-0003 generation."""

from __future__ import annotations

import os
from pathlib import Path
import shutil

import pytest

from scripts import build_st0003_revision as revision


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_ROOT = REPOSITORY_ROOT / "changes" / "st-0003"


def copy_owned_bundle(target: Path) -> None:
    target.mkdir()
    shutil.copytree(BUNDLE_ROOT / "contracts", target / "contracts")
    shutil.copy2(BUNDLE_ROOT / "manifest.yaml", target / "manifest.yaml")
    shutil.copy2(BUNDLE_ROOT / "job-state.v1.yaml", target / "job-state.v1.yaml")


def tree_snapshot(root: Path) -> dict[str, tuple[str, bytes | str]]:
    snapshot: dict[str, tuple[str, bytes | str]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            snapshot[relative] = ("symlink", os.readlink(path))
        elif path.is_file():
            snapshot[relative] = ("file", path.read_bytes())
        elif path.is_dir():
            snapshot[relative] = ("directory", "")
    return snapshot


def test_committed_revision_has_no_generated_drift() -> None:
    revision.check_generated()


def test_clean_build_is_byte_deterministic_and_matches_committed(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    revision.build(first)
    revision.build(second)

    assert revision.generated_file_map(first) == revision.generated_file_map(second)
    assert revision.generated_file_map(first) == revision.generated_file_map(
        BUNDLE_ROOT
    )


def test_generation_failure_preserves_previous_complete_owned_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "owned"
    revision.build(target)
    before = revision.generated_file_map(target)

    def fail_generation(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("injected ST-0003 generation failure")

    monkeypatch.setattr(revision, "generate_contracts", fail_generation)
    with pytest.raises(RuntimeError, match="injected ST-0003 generation failure"):
        revision.build(target)

    assert revision.generated_file_map(target) == before


def test_install_failure_restores_previous_complete_owned_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "owned"
    revision.build(target)
    before = revision.generated_file_map(target)
    real_replace = revision.os.replace
    injected = False

    def fail_staged_manifest_once(source: object, destination: object) -> None:
        nonlocal injected
        source_path = Path(source)  # type: ignore[arg-type]
        if (
            not injected
            and source_path.parent.name == "generated"
            and source_path.name == "manifest.yaml"
        ):
            injected = True
            raise OSError("injected ST-0003 install failure")
        real_replace(source, destination)  # type: ignore[arg-type]

    monkeypatch.setattr(revision.os, "replace", fail_staged_manifest_once)
    with pytest.raises(OSError, match="injected ST-0003 install failure"):
        revision.build(target)

    assert injected
    assert revision.generated_file_map(target) == before


def test_cli_refuses_custom_output_and_builder_refuses_unowned_tree(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    custom = tmp_path / "foreign"
    assert revision.main(["--output", str(custom)]) == 1
    assert not custom.exists()
    assert "owned canonical" in capsys.readouterr().err

    unowned = tmp_path / "unowned"
    (unowned / "contracts").mkdir(parents=True)
    (unowned / "manifest.yaml").write_text(
        "document:\n  id: FOREIGN\n",
        encoding="utf-8",
    )
    with pytest.raises(
        RuntimeError,
        match="not owned|partial|incomplete|malformed|missing|must contain",
    ):
        revision.build(unowned)


def test_builder_refuses_symlinked_output_root(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)

    with pytest.raises(RuntimeError, match="symlink|owned canonical|unsafe"):
        revision.build(linked)


def test_builder_refuses_unowned_contract_file_without_mutating_tree(
    tmp_path: Path,
) -> None:
    target = tmp_path / "owned"
    copy_owned_bundle(target)
    unowned = target / "contracts" / "unowned.txt"
    unowned.write_text("do not overwrite me\n", encoding="utf-8")
    before = tree_snapshot(target)

    with pytest.raises(RuntimeError, match="unexpected|unowned|not owned"):
        revision.build(target)

    assert tree_snapshot(target) == before


def test_builder_refuses_nested_contract_symlink_without_mutating_tree(
    tmp_path: Path,
) -> None:
    target = tmp_path / "owned"
    copy_owned_bundle(target)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel.txt").write_text("outside\n", encoding="utf-8")
    nested_link = target / "contracts" / "nested-link"
    nested_link.symlink_to(outside, target_is_directory=True)
    before = tree_snapshot(target)

    with pytest.raises(RuntimeError, match="symlink|unsafe|unexpected"):
        revision.build(target)

    assert tree_snapshot(target) == before
    assert (outside / "sentinel.txt").read_text(encoding="utf-8") == "outside\n"


@pytest.mark.parametrize("unsafe_path", ("a/./b", "a//b"))
def test_relative_path_checker_rejects_noncanonical_segments(
    unsafe_path: str,
) -> None:
    with pytest.raises(RuntimeError, match="unsafe path"):
        revision.checked_relative_path(unsafe_path, source="negative test")


def test_builder_rejects_immutable_input_hash_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corrupted = dict(revision.EXPECTED_INPUT_HASHES)
    path = next(iter(corrupted))
    corrupted[path] = "0" * 64
    monkeypatch.setattr(revision, "EXPECTED_INPUT_HASHES", corrupted)

    with pytest.raises(RuntimeError, match="immutable input hash mismatch"):
        revision.assert_immutable_inputs()


def test_predecessor_verifier_rejects_manifest_hash_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_hash = revision.sha256_file
    predecessor_prefix = str(revision.PREDECESSOR_ROOT.resolve())
    injected = False

    def corrupt_one_predecessor(path: Path) -> str:
        nonlocal injected
        value = real_hash(path)
        if not injected and str(path.resolve()).startswith(predecessor_prefix):
            injected = True
            return "0" * 64
        return value

    monkeypatch.setattr(revision, "sha256_file", corrupt_one_predecessor)
    with pytest.raises(
        RuntimeError,
        match=r"(?i)(?:st-0002|predecessor).*(?:hash|drift)",
    ):
        revision.verify_predecessor()
    assert injected


def test_build_revalidates_pinned_inputs_and_predecessor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    immutable_checked = False
    predecessor_checked = False
    real_immutable = revision.assert_immutable_inputs
    real_predecessor = revision.verify_predecessor

    def mark_immutable() -> None:
        nonlocal immutable_checked
        immutable_checked = True
        real_immutable()

    def mark_predecessor() -> None:
        nonlocal predecessor_checked
        predecessor_checked = True
        real_predecessor()

    monkeypatch.setattr(revision, "assert_immutable_inputs", mark_immutable)
    monkeypatch.setattr(revision, "verify_predecessor", mark_predecessor)
    revision.build(tmp_path / "candidate")

    assert immutable_checked
    assert predecessor_checked

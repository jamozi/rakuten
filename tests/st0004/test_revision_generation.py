"""Deterministic, pinned, path-safe and failure-atomic ST-0004 generation."""

from __future__ import annotations

import os
from pathlib import Path
import pytest
import yaml

from scripts import build_st0004_revision as revision


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_ROOT = REPOSITORY_ROOT / "changes" / "st-0004"


def copy_owned_bundle(target: Path) -> None:
    revision.build(target)


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
    assert revision.generated_file_map(first) == revision.generated_file_map(BUNDLE_ROOT)


def test_generation_failure_preserves_previous_complete_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "owned"
    revision.build(target)
    before = revision.generated_file_map(target)

    def fail_generation(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("injected ST-0004 generation failure")

    monkeypatch.setattr(revision, "enrich_contracts", fail_generation)
    with pytest.raises(RuntimeError, match="injected ST-0004 generation failure"):
        revision.build(target)
    assert revision.generated_file_map(target) == before


def test_install_failure_restores_previous_complete_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
            raise OSError("injected ST-0004 install failure")
        real_replace(source, destination)  # type: ignore[arg-type]

    monkeypatch.setattr(revision.os, "replace", fail_staged_manifest_once)
    with pytest.raises(OSError, match="injected ST-0004 install failure"):
        revision.build(target)
    assert injected
    assert revision.generated_file_map(target) == before


def test_cli_refuses_custom_output_and_builder_refuses_unowned_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    custom = tmp_path / "foreign"
    assert revision.main(["--output", str(custom)]) == 1
    assert not custom.exists()
    assert "owned canonical" in capsys.readouterr().err

    unowned = tmp_path / "unowned"
    (unowned / "contracts").mkdir(parents=True)
    (unowned / "manifest.yaml").write_text(
        "document:\n  id: FOREIGN\n", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="owned|partial|malformed|missing"):
        revision.build(unowned)


def test_builder_refuses_symlinked_output_root(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(RuntimeError, match="symlink|unsafe"):
        revision.build(linked)


@pytest.mark.parametrize("kind", ("unowned-file", "nested-symlink"))
def test_builder_refuses_unowned_or_symlinked_generated_content_without_mutation(
    tmp_path: Path, kind: str
) -> None:
    target = tmp_path / "owned"
    copy_owned_bundle(target)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel.txt").write_text("outside\n", encoding="utf-8")
    if kind == "unowned-file":
        (target / "contracts" / "unowned.txt").write_text(
            "do not overwrite\n", encoding="utf-8"
        )
    else:
        (target / "contracts" / "nested-link").symlink_to(
            outside, target_is_directory=True
        )
    before = tree_snapshot(target)
    with pytest.raises(RuntimeError, match="symlink|unsafe|unexpected|unowned"):
        revision.build(target)
    assert tree_snapshot(target) == before
    assert (outside / "sentinel.txt").read_text(encoding="utf-8") == "outside\n"


@pytest.mark.parametrize(
    "unsafe_path",
    ("", "/absolute", "../escape", "a/../b", "a\\b"),
)
def test_relative_path_checker_rejects_unsafe_or_noncanonical_paths(
    unsafe_path: str,
) -> None:
    with pytest.raises(RuntimeError, match="unsafe relative path"):
        revision.checked_relative_path(unsafe_path, source="negative test")


@pytest.mark.parametrize("equivalent_path", ("a/./b", "a//b"))
def test_relative_path_checker_uses_pure_posix_normalization(
    equivalent_path: str,
) -> None:
    assert revision.checked_relative_path(
        equivalent_path, source="normalization test"
    ).as_posix() == "a/b"


def test_builder_rejects_immutable_input_hash_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corrupted = dict(revision.EXPECTED_INPUT_HASHES)
    path = next(iter(corrupted))
    corrupted[path] = "0" * 64
    monkeypatch.setattr(revision, "EXPECTED_INPUT_HASHES", corrupted)
    with pytest.raises(RuntimeError, match="immutable input hash mismatch"):
        revision.assert_immutable_inputs()


@pytest.mark.parametrize("section", ("inputs", "source_artifacts", "generated_artifacts"))
def test_predecessor_verifier_rejects_every_artifact_class_hash_drift(
    monkeypatch: pytest.MonkeyPatch, section: str
) -> None:
    manifest = yaml.safe_load(revision.PREDECESSOR_MANIFEST.read_text(encoding="utf-8"))
    target = REPOSITORY_ROOT / manifest[section][0]["path"]
    real_hash = revision.sha256_file

    def corrupt_target(path: Path) -> str:
        if path.resolve() == target.resolve():
            return "0" * 64
        return real_hash(path)

    monkeypatch.setattr(revision, "sha256_file", corrupt_target)
    with pytest.raises(RuntimeError, match="predecessor|immutable-input|artifact integrity"):
        revision.verify_predecessor()


def test_predecessor_verifier_rejects_manifest_hash_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(revision, "PREDECESSOR_MANIFEST_HASH", "0" * 64)
    with pytest.raises(RuntimeError, match="manifest.*hash drift"):
        revision.verify_predecessor()


def test_build_revalidates_inputs_archive_and_complete_predecessor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    real_inputs = revision.assert_immutable_inputs
    real_archive = revision.verify_content_archive
    real_predecessor = revision.verify_predecessor

    def inputs() -> None:
        calls.append("inputs")
        real_inputs()

    def archive() -> dict[str, bytes]:
        calls.append("archive")
        return real_archive()

    def predecessor() -> dict[str, object]:
        calls.append("predecessor")
        return real_predecessor()

    monkeypatch.setattr(revision, "assert_immutable_inputs", inputs)
    monkeypatch.setattr(revision, "verify_content_archive", archive)
    monkeypatch.setattr(revision, "verify_predecessor", predecessor)
    revision.build(tmp_path / "candidate")
    assert calls == ["inputs", "archive", "predecessor", "archive"]

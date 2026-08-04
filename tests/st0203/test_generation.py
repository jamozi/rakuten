"""Deterministic ST-0203 evidence-manifest generation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts import build_st0203_queue_fake as generator


def test_render_manifest_is_byte_deterministic() -> None:
    first = generator.render_manifest()
    second = generator.render_manifest()
    assert first == second


def test_installed_manifest_matches_renderer() -> None:
    target = generator.REPO_ROOT / generator.MANIFEST_PATH
    assert target.read_bytes() == generator.render_manifest()
    generator.check_generated()


def test_manifest_has_complete_unique_source_inventory() -> None:
    manifest = yaml.safe_load(generator.render_manifest())
    artifacts = manifest["source_artifacts"]

    assert manifest["source_artifact_count"] == len(generator.SOURCE_ARTIFACT_PATHS)
    assert len(artifacts) == len(generator.SOURCE_ARTIFACT_PATHS)
    assert [item["uri"] for item in artifacts] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_ARTIFACT_PATHS
    ]
    assert len({item["uri"] for item in artifacts}) == len(artifacts)
    assert len({item["sha256"] for item in artifacts}) == len(artifacts)
    assert manifest["generated_artifact_count"] == 0
    assert manifest["generated_artifacts"] == []


def test_check_mode_does_not_write(monkeypatch: pytest.MonkeyPatch) -> None:
    writes: list[tuple[bytes, Path]] = []

    def forbidden(content: bytes, root: Path = generator.REPO_ROOT) -> None:
        writes.append((content, root))

    monkeypatch.setattr(generator, "install_manifest", forbidden)
    assert generator.main(["--check"]) == 0
    assert writes == []


def test_install_rejects_symlink_target(tmp_path: Path) -> None:
    target = tmp_path / generator.MANIFEST_PATH
    target.parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.write_text("unchanged", encoding="utf-8")
    target.symlink_to(outside)

    with pytest.raises(RuntimeError, match="non-symlink"):
        generator.install_manifest(b"candidate", tmp_path)
    assert outside.read_text(encoding="utf-8") == "unchanged"


def test_install_rejects_symlink_root(tmp_path: Path) -> None:
    physical = tmp_path / "physical"
    physical.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(physical, target_is_directory=True)

    with pytest.raises(RuntimeError, match="root must be a real directory"):
        generator.install_manifest(b"candidate", linked)


def test_held_parent_descriptor_defeats_ancestor_symlink_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / generator.MANIFEST_PATH.parent
    parent.mkdir(parents=True)
    target = parent / generator.MANIFEST_PATH.name
    target.write_bytes(b"old")
    moved = tmp_path / "held-parent"
    outside = tmp_path / "outside"
    outside.mkdir()
    real_replace = generator.os.replace
    swapped = False

    def replace_with_swap(
        source: str,
        destination: str,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        nonlocal swapped
        if not swapped:
            parent.rename(moved)
            parent.symlink_to(outside, target_is_directory=True)
            swapped = True
        real_replace(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(generator.os, "replace", replace_with_swap)
    generator.install_manifest(b"candidate", tmp_path)

    assert swapped is True
    assert (moved / generator.MANIFEST_PATH.name).read_bytes() == b"candidate"
    assert not (outside / generator.MANIFEST_PATH.name).exists()

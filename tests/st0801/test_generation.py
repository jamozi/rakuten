"""Deterministic and symlink-safe ST-0801 manifest generation."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
import yaml

from scripts import build_st0801_content_ast as generator


def test_manifest_rendering_is_byte_deterministic() -> None:
    assert generator.render_manifest() == generator.render_manifest()


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
    assert manifest["generated_artifact_count"] == 0
    assert manifest["generated_artifacts"] == []
    assert {
        Path("scripts/build_st0201_postgres_service.py"),
        Path("python/raos/__init__.py"),
        Path("python/raos/generated/__init__.py"),
        Path("tests/conftest.py"),
        Path("tests/st0102/conftest.py"),
        Path(".github/workflows/ci.yml"),
    }.issubset(generator.SOURCE_ARTIFACT_PATHS)
    assert manifest["provenance"]["predecessor_recursive_integrity"] == {
        "story_id": "ST-0105",
        "manifest_uri": "repo://changes/st-0105/manifest.json",
        "declared_output_count": 354,
        "verification": "ALL_DECLARED_OUTPUT_BYTES_AND_SHA256_VERIFIED",
    }


def test_generation_toolchain_matches_contract() -> None:
    contract = generator.load_and_validate_contract()

    generator.assert_generation_toolchain()
    assert contract["toolchain"] == generator.EXPECTED_TOOLCHAIN


def test_generation_defers_runtime_version_verification_to_setup_and_final() -> None:
    source = Path(generator.__file__).read_text(encoding="utf-8")
    assert generator.assert_generation_toolchain() is None
    assert "sys.version_info" not in source
    assert "importlib_metadata" not in source
    assert generator.render_manifest()


def test_unselected_st0105_output_drift_fails_recursive_integrity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = Path("packages/web-contracts/src/generated/asyncapi.gen.ts")
    real_assert_digest = generator._assert_digest
    reached_target = False

    def assert_digest(
        root: Path, relative: Path, expected: object, label: str
    ) -> bytes:
        nonlocal reached_target
        if relative == target:
            reached_target = True
            raise RuntimeError("synthetic unselected output drift")
        return real_assert_digest(root, relative, expected, label)

    monkeypatch.setattr(generator, "_assert_digest", assert_digest)

    with pytest.raises(RuntimeError, match="unselected output drift"):
        generator.load_and_validate_contract()
    assert reached_target is True


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

    with pytest.raises(RuntimeError, match="regular non-symlink"):
        generator.install_manifest(b"candidate", tmp_path)
    assert outside.read_text(encoding="utf-8") == "unchanged"


def test_install_rejects_symlink_root(tmp_path: Path) -> None:
    physical = tmp_path / "physical"
    physical.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(physical, target_is_directory=True)

    with pytest.raises(RuntimeError, match="root must be a real directory"):
        generator.install_manifest(b"candidate", linked)


def test_source_reader_rejects_symlinked_ancestor(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    content = b"synthetic source"
    (outside / "source.txt").write_bytes(content)
    (tmp_path / "linked").symlink_to(outside, target_is_directory=True)

    with pytest.raises(RuntimeError, match="unavailable"):
        generator._assert_digest(
            tmp_path,
            Path("linked/source.txt"),
            hashlib.sha256(content).hexdigest(),
            "synthetic source",
        )


@pytest.mark.parametrize("swap_ancestor", [False, True])
def test_inventory_rejects_directory_or_ancestor_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    swap_ancestor: bool,
) -> None:
    ancestor = tmp_path / "source"
    inventory_root = ancestor / "schemas"
    inventory_root.mkdir(parents=True)
    (inventory_root / "expected.json").write_text("{}", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    moved = tmp_path / "held"
    swap_target = ancestor if swap_ancestor else inventory_root
    held_inventory = moved / "schemas" if swap_ancestor else moved
    real_listdir = generator.os.listdir
    swapped = False

    def listdir_with_swap(descriptor: int) -> list[str]:
        nonlocal swapped
        names = real_listdir(descriptor)
        if not swapped:
            swap_target.rename(moved)
            swap_target.symlink_to(outside, target_is_directory=True)
            (held_inventory / "foreign.json").write_text("{}", encoding="utf-8")
            swapped = True
        return names

    monkeypatch.setattr(generator.os, "listdir", listdir_with_swap)

    with pytest.raises(RuntimeError, match="inventory directory changed"):
        generator._exact_file_inventory(tmp_path, Path("source/schemas"))
    assert swapped is True


def test_inventory_rejects_symlink_entry(tmp_path: Path) -> None:
    inventory_root = tmp_path / "schemas"
    inventory_root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    (inventory_root / "linked.json").symlink_to(outside)

    with pytest.raises(RuntimeError, match="inventory contains a symlink"):
        generator._exact_file_inventory(tmp_path, Path("schemas"))


def test_inventory_rejects_special_file(tmp_path: Path) -> None:
    inventory_root = tmp_path / "schemas"
    inventory_root.mkdir()
    os.mkfifo(inventory_root / "blocking.fifo")

    with pytest.raises(RuntimeError, match="inventory contains a special file"):
        generator._exact_file_inventory(tmp_path, Path("schemas"))


def test_inventory_close_failure_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inventory_root = tmp_path / "schemas"
    inventory_root.mkdir()
    (inventory_root / "schema.json").write_text("{}", encoding="utf-8")
    real_close = generator.os.close
    failed = False

    def close_then_fail(descriptor: int) -> None:
        nonlocal failed
        real_close(descriptor)
        if not failed:
            failed = True
            raise OSError("synthetic close failure")

    monkeypatch.setattr(generator.os, "close", close_then_fail)

    with pytest.raises(RuntimeError, match="could not be closed safely"):
        generator._exact_file_inventory(tmp_path, Path("schemas"))
    assert failed is True


def test_held_parent_descriptor_defeats_ancestor_symlink_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / generator.MANIFEST_PATH.parent
    parent.mkdir(parents=True)
    (parent / generator.MANIFEST_PATH.name).write_bytes(b"old")
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

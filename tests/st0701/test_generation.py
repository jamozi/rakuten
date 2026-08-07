"""Deterministic generation and adversarial source tests for ST-0701."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import os
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import build_st0701_ai_registry as generator
from raos.shared import ContractRepository


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = REPOSITORY_ROOT / "contracts" / "raos-v0.4"
TASK_REGISTRY_PATH = "contracts/ai/RAOS_05_ai_task_catalog_v0.1.yaml"
PROMPT_REGISTRY_PATH = "contracts/ai/RAOS_05_prompt_registry_v0.1.yaml"
ARTICLE_DRAFT_PROMPT_PATH = "contracts/ai/prompts/PROMPT-AI-ARTICLE-DRAFT_v1.md"


class FakeRepository:
    """In-memory mutation wrapper around an already verified repository."""

    def __init__(
        self,
        base: ContractRepository,
        replacements: dict[str, bytes],
        *,
        rebind_manifest: bool,
    ) -> None:
        self._base = base
        self._replacements = replacements
        artifacts: list[object] = []
        for artifact in base.artifacts:
            replacement = replacements.get(artifact.path)
            if replacement is None or not rebind_manifest:
                artifacts.append(artifact)
            else:
                artifacts.append(
                    SimpleNamespace(
                        path=artifact.path,
                        byte_count=len(replacement),
                        sha256=hashlib.sha256(replacement).hexdigest(),
                    )
                )
        self.artifacts = tuple(artifacts)

    def read_bytes(self, path: str) -> bytes:
        return self._replacements.get(path, self._base.read_bytes(path))


def _repin_registry(monkeypatch: pytest.MonkeyPatch, path: str, content: bytes) -> None:
    updated = tuple(
        replace(
            spec,
            byte_count=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )
        if spec.path == path
        else spec
        for spec in generator.REGISTRY_SPECS
    )
    monkeypatch.setattr(generator, "REGISTRY_SPECS", updated)


def _snapshot(path: Path) -> tuple[int, int, int, int, int, int]:
    value = path.stat()
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
        value.st_mode,
    )


def test_render_is_deterministic_and_matches_generated_files() -> None:
    first = generator.render_outputs(REPOSITORY_ROOT)
    second = generator.render_outputs(REPOSITORY_ROOT)
    assert first == second
    assert tuple(first) == (generator.OUTPUT_PATH, generator.MANIFEST_PATH)
    for relative, content in first.items():
        assert (REPOSITORY_ROOT / relative).read_bytes() == content


def test_cli_check_is_read_only() -> None:
    paths = tuple(
        REPOSITORY_ROOT / relative
        for relative in (generator.OUTPUT_PATH, generator.MANIFEST_PATH)
    )
    before = {path: _snapshot(path) for path in paths}
    result = subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / generator.__file__), "--check"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert result.returncode == 0, result.stderr
    assert {path: _snapshot(path) for path in paths} == before


def test_check_detects_tampered_output_without_repairing_it(tmp_path: Path) -> None:
    expected = generator.render_outputs(REPOSITORY_ROOT)
    for relative, content in expected.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    target = tmp_path / generator.OUTPUT_PATH
    target.write_bytes(target.read_bytes() + b"\n")
    tampered = target.read_bytes()

    with pytest.raises(RuntimeError, match="out of date"):
        generator._check_outputs(expected, tmp_path)
    assert target.read_bytes() == tampered


def test_secure_reader_uses_descriptor_relative_traversal_and_required_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "nested" / "payload.json"
    source.parent.mkdir()
    source.write_bytes(b'{"safe":true}\n')
    real_open = os.open
    calls: list[tuple[str, int, int | None, int]] = []

    def tracked_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        calls.append((os.fsdecode(path), flags, dir_fd, descriptor))
        return descriptor

    monkeypatch.setattr(generator.os, "open", tracked_open)

    assert (
        generator._read_regular(
            tmp_path,
            Path("nested/payload.json"),
            label="descriptor-relative test source",
        )
        == b'{"safe":true}\n'
    )
    absolute_root = Path(os.path.abspath(tmp_path))
    assert [path for path, *_rest in calls] == [
        absolute_root.anchor,
        *absolute_root.parts[1:],
        "nested",
        "payload.json",
    ]
    assert calls[0][2] is None
    for previous, current in zip(calls, calls[1:]):
        assert current[2] == previous[3]
        assert "/" not in current[0]
    assert all(flags & os.O_NOFOLLOW for _path, flags, _dir_fd, _fd in calls)
    assert all(flags & os.O_CLOEXEC for _path, flags, _dir_fd, _fd in calls)
    assert all(flags & os.O_DIRECTORY for _path, flags, _dir_fd, _fd in calls[:-1])
    assert calls[-1][1] & os.O_NONBLOCK
    assert not calls[-1][1] & os.O_DIRECTORY


@pytest.mark.parametrize(
    "flag_name",
    ["O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK", "O_CLOEXEC"],
)
def test_secure_reader_fails_closed_without_required_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    flag_name: str,
) -> None:
    (tmp_path / "payload.json").write_bytes(b"safe\n")
    monkeypatch.setattr(generator.os, flag_name, 0)

    with pytest.raises(RuntimeError, match="filesystem safety is unavailable"):
        generator._read_regular(
            tmp_path,
            Path("payload.json"),
            label="missing-flag test source",
        )


def test_secure_reader_rejects_repository_root_swap_before_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    (root / "payload.json").write_bytes(b"trusted\n")
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    (replacement / "payload.json").write_bytes(b"untrusted\n")
    real_open = os.open
    swapped = False

    def swap_root_then_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if os.fsdecode(path) == root.name and not swapped:
            swapped = True
            root.rename(tmp_path / "captured-repository")
            replacement.rename(root)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(generator.os, "open", swap_root_then_open)

    with pytest.raises(RuntimeError, match="root changed before secure capture"):
        generator._read_regular(
            root,
            Path("payload.json"),
            label="root-swap test source",
        )


def test_secure_reader_rejects_symlinked_repository_root_ancestor(
    tmp_path: Path,
) -> None:
    real_parent = tmp_path / "real-parent"
    root = real_parent / "repository"
    root.mkdir(parents=True)
    (root / "payload.json").write_bytes(b"trusted\n")
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(RuntimeError, match="root and its ancestors"):
        generator._read_regular(
            linked_parent / "repository",
            Path("payload.json"),
            label="root-ancestor symlink test source",
        )


def test_secure_reader_rejects_repository_root_ancestor_swap_after_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trusted_parent = tmp_path / "trusted-parent"
    root = trusted_parent / "repository"
    root.mkdir(parents=True)
    (root / "payload.json").write_bytes(b"trusted\n")
    replacement_parent = tmp_path / "replacement-parent"
    replacement_root = replacement_parent / "repository"
    replacement_root.mkdir(parents=True)
    (replacement_root / "payload.json").write_bytes(b"replacement\n")
    real_open = os.open
    swapped = False

    def swap_after_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if os.fsdecode(path) == trusted_parent.name and not swapped:
            swapped = True
            trusted_parent.rename(tmp_path / "captured-trusted-parent")
            replacement_parent.rename(trusted_parent)
        return descriptor

    monkeypatch.setattr(generator.os, "open", swap_after_open)

    with pytest.raises(RuntimeError) as exc_info:
        generator._read_regular(
            root,
            Path("payload.json"),
            label="root-ancestor swap test source",
        )
    assert str(exc_info.value) in {
        "repository root changed before secure capture",
        "repository root changed during secure capture",
    }


@pytest.mark.parametrize("link_leaf", [False, True], ids=["ancestor", "leaf"])
def test_secure_reader_rejects_symlinks(
    tmp_path: Path,
    link_leaf: bool,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "payload.json").write_bytes(b"outside\n")
    if link_leaf:
        os.symlink(outside / "payload.json", tmp_path / "linked.json")
        relative = Path("linked.json")
    else:
        os.symlink(outside, tmp_path / "linked")
        relative = Path("linked/payload.json")

    with pytest.raises(RuntimeError):
        generator._read_regular(tmp_path, relative, label="symlink test source")


def test_secure_reader_rejects_fifo_before_opening_the_leaf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fifo = tmp_path / "payload.fifo"
    os.mkfifo(fifo)
    real_open = os.open
    opened: list[str] = []

    def tracked_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        opened.append(os.fsdecode(path))
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(generator.os, "open", tracked_open)

    with pytest.raises(RuntimeError, match="regular non-symlink file"):
        generator._read_regular(
            tmp_path,
            Path("payload.fifo"),
            label="FIFO test source",
        )
    assert "payload.fifo" not in opened


def test_secure_reader_rejects_multiply_linked_file(tmp_path: Path) -> None:
    source = tmp_path / "payload.json"
    source.write_bytes(b"linked\n")
    os.link(source, tmp_path / "second-name.json")

    with pytest.raises(RuntimeError, match="one filesystem link"):
        generator._read_regular(
            tmp_path,
            Path("payload.json"),
            label="hardlink test source",
        )


def test_secure_reader_rejects_ancestor_replacement_after_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trusted = tmp_path / "trusted"
    (trusted / "nested").mkdir(parents=True)
    (trusted / "nested" / "payload.json").write_bytes(b"trusted\n")
    replacement = tmp_path / "replacement"
    (replacement / "nested").mkdir(parents=True)
    (replacement / "nested" / "payload.json").write_bytes(b"replacement\n")
    real_open = os.open
    swapped = False

    def swap_after_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if os.fsdecode(path) == "trusted" and not swapped:
            swapped = True
            trusted.rename(tmp_path / "captured-trusted")
            replacement.rename(trusted)
        return descriptor

    monkeypatch.setattr(generator.os, "open", swap_after_open)

    with pytest.raises(RuntimeError, match="ancestor changed during secure capture"):
        generator._read_regular(
            tmp_path,
            Path("trusted/nested/payload.json"),
            label="ancestor replacement test source",
        )


@pytest.mark.parametrize("swap_before_open", [True, False], ids=["before", "after"])
def test_secure_reader_rejects_target_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    swap_before_open: bool,
) -> None:
    source = tmp_path / "payload.json"
    source.write_bytes(b"trusted\n")
    replacement = tmp_path / "replacement.json"
    replacement.write_bytes(b"untrusted\n")
    real_open = os.open
    real_read = os.read
    target_descriptor: int | None = None
    swapped = False

    def tracked_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped, target_descriptor
        if os.fsdecode(path) == "payload.json" and swap_before_open and not swapped:
            swapped = True
            source.rename(tmp_path / "captured-payload.json")
            replacement.rename(source)
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if os.fsdecode(path) == "payload.json":
            target_descriptor = descriptor
        return descriptor

    def swap_then_read(descriptor: int, count: int) -> bytes:
        nonlocal swapped
        if descriptor == target_descriptor and not swap_before_open and not swapped:
            swapped = True
            source.rename(tmp_path / "captured-payload.json")
            replacement.rename(source)
        return real_read(descriptor, count)

    monkeypatch.setattr(generator.os, "open", tracked_open)
    monkeypatch.setattr(generator.os, "read", swap_then_read)

    expected_message = (
        "changed before secure capture"
        if swap_before_open
        else "changed while it was read"
    )
    with pytest.raises(RuntimeError, match=expected_message):
        generator._read_regular(
            tmp_path,
            Path("payload.json"),
            label="target replacement test source",
        )


@pytest.mark.parametrize(
    "replacement",
    [b"mutated!", b"x", b"extended-content"],
    ids=["same-size", "truncated", "extended"],
)
def test_secure_reader_rejects_same_inode_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replacement: bytes,
) -> None:
    source = tmp_path / "payload.bin"
    source.write_bytes(b"original")
    real_read = os.read
    mutated = False

    def mutate_then_read(descriptor: int, count: int) -> bytes:
        nonlocal mutated
        if not mutated:
            mutated = True
            source.write_bytes(replacement)
            metadata = source.stat()
            os.utime(
                source,
                ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000_000),
            )
        return real_read(descriptor, count)

    monkeypatch.setattr(generator.os, "read", mutate_then_read)

    with pytest.raises(RuntimeError, match="changed while it was read"):
        generator._read_regular(
            tmp_path,
            Path("payload.bin"),
            label="same-inode mutation test source",
        )


def test_secure_reader_enforces_the_exact_four_mibibyte_limit(tmp_path: Path) -> None:
    source = tmp_path / "payload.bin"
    source.write_bytes(b"x" * generator.MAX_SOURCE_BYTES)
    assert (
        len(
            generator._read_regular(
                tmp_path,
                Path("payload.bin"),
                label="size-bound test source",
            )
        )
        == generator.MAX_SOURCE_BYTES
    )

    source.write_bytes(b"x" * (generator.MAX_SOURCE_BYTES + 1))
    with pytest.raises(RuntimeError, match="exceeds the size limit"):
        generator._read_regular(
            tmp_path,
            Path("payload.bin"),
            label="size-bound test source",
        )


def test_secure_reader_rejects_short_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "payload.bin").write_bytes(b"content")
    monkeypatch.setattr(generator.os, "read", lambda _descriptor, _count: b"")

    with pytest.raises(RuntimeError, match="changed while it was read"):
        generator._read_regular(
            tmp_path,
            Path("payload.bin"),
            label="short-read test source",
        )


def test_secure_reader_sanitizes_read_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canary = "private-read-failure-canary"
    (tmp_path / "payload.bin").write_bytes(b"content")

    def fail_read(_descriptor: int, _count: int) -> bytes:
        raise OSError(canary)

    monkeypatch.setattr(generator.os, "read", fail_read)
    with pytest.raises(RuntimeError, match="captured safely") as exc_info:
        generator._read_regular(
            tmp_path,
            Path("payload.bin"),
            label="failed-read test source",
        )
    assert canary not in str(exc_info.value)


def test_secure_reader_sanitizes_close_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canary = "private-close-failure-canary"
    source = tmp_path / "nested" / "payload.bin"
    source.parent.mkdir()
    source.write_bytes(b"content")
    real_open = os.open
    real_close = os.close
    opened: list[int] = []
    closed: list[int] = []
    failed = False

    def tracked_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        opened.append(descriptor)
        return descriptor

    def close_then_fail(descriptor: int) -> None:
        nonlocal failed
        real_close(descriptor)
        closed.append(descriptor)
        if not failed:
            failed = True
            raise OSError(canary)

    monkeypatch.setattr(generator.os, "open", tracked_open)
    monkeypatch.setattr(generator.os, "close", close_then_fail)
    with pytest.raises(RuntimeError, match="descriptor cleanup failed") as exc_info:
        generator._read_regular(
            tmp_path,
            Path("nested/payload.bin"),
            label="close-failure test source",
        )
    assert canary not in str(exc_info.value)
    assert sorted(closed) == sorted(opened)
    assert len(closed) == len(set(closed))


def test_secure_reader_preserves_primary_failure_when_close_also_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "payload.bin").write_bytes(b"x" * (generator.MAX_SOURCE_BYTES + 1))
    real_close = os.close

    def close_then_fail(descriptor: int) -> None:
        real_close(descriptor)
        raise OSError("private cleanup detail")

    monkeypatch.setattr(generator.os, "close", close_then_fail)
    with pytest.raises(RuntimeError, match="exceeds the size limit") as exc_info:
        generator._read_regular(
            tmp_path,
            Path("payload.bin"),
            label="primary-failure test source",
        )
    assert "descriptor cleanup also failed" in getattr(
        exc_info.value,
        "__notes__",
        (),
    )


def test_output_check_uses_the_secure_reader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = generator.render_outputs(REPOSITORY_ROOT)
    for relative, content in expected.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    real_read = generator._read_regular
    observed: list[Path] = []

    def tracked_read(root: Path, relative: Path, *, label: str) -> bytes:
        observed.append(relative)
        return real_read(root, relative, label=label)

    monkeypatch.setattr(generator, "_read_regular", tracked_read)
    generator._check_outputs(expected, tmp_path)
    assert observed == list(expected)


def _prepared_output_parent(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "repository"
    parent = root / generator.OUTPUT_PATH.parent
    parent.mkdir(parents=True)
    return root, parent, root / generator.OUTPUT_PATH


def test_installer_fresh_publish_uses_one_descriptor_chain_and_durable_fsyncs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    content = b'{"installed":true}\n'
    real_open = os.open
    real_mkdir = os.mkdir
    real_fsync = os.fsync
    real_replace = os.replace
    opened: list[tuple[str, int, int, int | None, int]] = []
    created: list[tuple[str, int, int | None]] = []
    synced: list[int] = []
    replaced: list[tuple[str, str, int | None, int | None]] = []

    def tracked_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        opened.append((os.fsdecode(path), flags, mode, dir_fd, descriptor))
        return descriptor

    def tracked_mkdir(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> None:
        created.append((os.fsdecode(path), mode, dir_fd))
        real_mkdir(path, mode, dir_fd=dir_fd)

    def tracked_fsync(descriptor: int) -> None:
        synced.append(descriptor)
        real_fsync(descriptor)

    def tracked_replace(
        source: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        destination: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        replaced.append(
            (
                os.fsdecode(source),
                os.fsdecode(destination),
                src_dir_fd,
                dst_dir_fd,
            )
        )
        real_replace(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(generator.os, "open", tracked_open)
    monkeypatch.setattr(generator.os, "mkdir", tracked_mkdir)
    monkeypatch.setattr(generator.os, "fsync", tracked_fsync)
    monkeypatch.setattr(generator.os, "replace", tracked_replace)

    generator._install(generator.OUTPUT_PATH, content, root)

    absolute_root = Path(os.path.abspath(root))
    assert [path for path, *_rest in opened[:-1]] == [
        absolute_root.anchor,
        *absolute_root.parts[1:],
        *generator.OUTPUT_PATH.parent.parts,
    ]
    assert opened[-1][0].startswith(f".{generator.OUTPUT_PATH.name}.st0701-")
    assert opened[0][3] is None
    assert all(
        current[3] == previous[4] for previous, current in zip(opened, opened[1:])
    )
    assert all(
        flags & os.O_DIRECTORY for _path, flags, _mode, _dir_fd, _fd in opened[:-1]
    )
    assert all(flags & os.O_NOFOLLOW for _path, flags, _mode, _dir_fd, _fd in opened)
    assert all(flags & os.O_CLOEXEC for _path, flags, _mode, _dir_fd, _fd in opened)
    assert opened[-1][1] & os.O_EXCL
    assert not opened[-1][1] & os.O_DIRECTORY
    assert opened[-1][2] == 0o600

    repository_descriptor = opened[-5][4]
    changes_descriptor = opened[-4][4]
    story_descriptor = opened[-3][4]
    generated_descriptor = opened[-2][4]
    staging_descriptor = opened[-1][4]
    assert created == [
        ("changes", 0o755, repository_descriptor),
        ("st-0701", 0o755, changes_descriptor),
        ("generated", 0o755, story_descriptor),
    ]
    assert synced == [
        repository_descriptor,
        changes_descriptor,
        story_descriptor,
        staging_descriptor,
        generated_descriptor,
    ]
    assert replaced == [
        (
            opened[-1][0],
            generator.OUTPUT_PATH.name,
            generated_descriptor,
            generated_descriptor,
        )
    ]
    target = root / generator.OUTPUT_PATH
    assert target.read_bytes() == content
    assert target.stat().st_mode & 0o777 == 0o644
    assert not tuple(target.parent.glob(f".{target.name}.st0701-*"))


@pytest.mark.parametrize("flag_name", ["O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC"])
def test_installer_fails_closed_without_required_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    flag_name: str,
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    monkeypatch.setattr(generator.os, flag_name, 0)

    with pytest.raises(RuntimeError, match="filesystem safety is unavailable"):
        generator._install(generator.OUTPUT_PATH, b"content\n", root)
    assert not (root / "changes").exists()


def test_installer_rejects_symlinked_output_ancestor(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "changes").symlink_to(outside, target_is_directory=True)

    with pytest.raises(RuntimeError, match="ancestors must be real directories"):
        generator._install(generator.OUTPUT_PATH, b"content\n", root)
    assert not tuple(outside.iterdir())


def test_installer_rejects_symlinked_repository_root_ancestor(tmp_path: Path) -> None:
    real_parent = tmp_path / "real-parent"
    root = real_parent / "repository"
    root.mkdir(parents=True)
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(RuntimeError, match="root and its ancestors"):
        generator._install(
            generator.OUTPUT_PATH,
            b"content\n",
            linked_parent / "repository",
        )
    assert not (root / generator.OUTPUT_PATH).exists()


@pytest.mark.parametrize("swap_timing", ["before_open", "after_open"])
def test_installer_rejects_repository_component_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    swap_timing: str,
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    captured = tmp_path / "captured-repository"
    real_open = os.open
    swapped = False

    def swap_around_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if (
            os.fsdecode(path) == root.name
            and not swapped
            and swap_timing == "before_open"
        ):
            swapped = True
            root.rename(captured)
            replacement.rename(root)
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if os.fsdecode(path) == root.name and not swapped:
            swapped = True
            root.rename(captured)
            replacement.rename(root)
        return descriptor

    monkeypatch.setattr(generator.os, "open", swap_around_open)
    message = (
        "root changed before secure installation"
        if swap_timing == "before_open"
        else "directory changed during secure installation"
    )
    with pytest.raises(RuntimeError, match=message):
        generator._install(generator.OUTPUT_PATH, b"content\n", root)
    assert not (root / generator.OUTPUT_PATH).exists()


@pytest.mark.parametrize("swap_timing", ["before_open", "after_open"])
def test_installer_rejects_output_ancestor_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    swap_timing: str,
) -> None:
    root = tmp_path / "repository"
    trusted = root / "changes"
    trusted.mkdir(parents=True)
    replacement = root / "replacement"
    replacement.mkdir()
    real_open = os.open
    swapped = False

    def swap_around_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if (
            os.fsdecode(path) == "changes"
            and not swapped
            and swap_timing == "before_open"
        ):
            swapped = True
            trusted.rename(root / "captured-changes")
            replacement.rename(trusted)
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if os.fsdecode(path) == "changes" and not swapped:
            swapped = True
            trusted.rename(root / "captured-changes")
            replacement.rename(trusted)
        return descriptor

    monkeypatch.setattr(generator.os, "open", swap_around_open)
    message = (
        "before secure installation"
        if swap_timing == "before_open"
        else "during secure installation"
    )
    with pytest.raises(RuntimeError, match=message):
        generator._install(generator.OUTPUT_PATH, b"content\n", root)
    assert not (root / generator.OUTPUT_PATH).exists()


@pytest.mark.parametrize(
    "target_kind",
    ["symlink", "fifo", "hardlink", "precommit_change", "absent_to_present"],
)
def test_installer_rejects_unsafe_or_changed_existing_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target_kind: str,
) -> None:
    root, parent, target = _prepared_output_parent(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"outside\n")
    if target_kind == "symlink":
        target.symlink_to(outside)
    elif target_kind == "fifo":
        os.mkfifo(target)
    elif target_kind in {"hardlink", "precommit_change"}:
        target.write_bytes(b"original\n")
        if target_kind == "hardlink":
            os.link(target, parent / "second-name.json")

    if target_kind in {"precommit_change", "absent_to_present"}:
        real_stat = os.stat
        target_stats = 0

        def mutate_before_second_target_stat(
            path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
            *,
            dir_fd: int | None = None,
            follow_symlinks: bool = True,
        ) -> os.stat_result:
            nonlocal target_stats
            if os.fsdecode(path) == target.name and dir_fd is not None:
                target_stats += 1
                if target_stats == 2:
                    content = (
                        b"changed-before-commit\n"
                        if target_kind == "precommit_change"
                        else b"appeared-before-commit\n"
                    )
                    target.write_bytes(content)
            return real_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

        monkeypatch.setattr(generator.os, "stat", mutate_before_second_target_stat)

    message = {
        "symlink": "regular file",
        "fifo": "regular file",
        "hardlink": "one filesystem link",
        "precommit_change": "changed before replacement",
        "absent_to_present": "changed before replacement",
    }[target_kind]
    with pytest.raises(RuntimeError, match=message):
        generator._install(generator.OUTPUT_PATH, b"replacement\n", root)
    assert outside.read_bytes() == b"outside\n"
    if target_kind == "absent_to_present":
        assert target.read_bytes() == b"appeared-before-commit\n"
    assert not tuple(parent.glob(f".{target.name}.st0701-*"))


def test_installer_completes_partial_write_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _parent, target = _prepared_output_parent(tmp_path)
    content = b"partial-write-progress\n"
    real_write = os.write
    writes: list[int] = []

    def partial_write(descriptor: int, remaining: object) -> int:
        view = memoryview(remaining)
        written = real_write(descriptor, view[: max(1, len(view) // 2)])
        writes.append(written)
        return written

    monkeypatch.setattr(generator.os, "write", partial_write)

    generator._install(generator.OUTPUT_PATH, content, root)
    assert len(writes) > 1
    assert sum(writes) == len(content)
    assert target.read_bytes() == content


def test_installer_rejects_staged_pathname_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, parent, target = _prepared_output_parent(tmp_path)
    real_stat = os.stat
    real_open = os.open
    real_write = os.write
    real_close = os.close
    real_unlink = os.unlink
    substituted = False

    def substitute_before_staged_stat(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> os.stat_result:
        nonlocal substituted
        name = os.fsdecode(path)
        if name.startswith(f".{target.name}.st0701-") and not substituted:
            substituted = True
            assert dir_fd is not None
            real_unlink(path, dir_fd=dir_fd)
            replacement_descriptor = real_open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o644,
                dir_fd=dir_fd,
            )
            try:
                assert real_write(replacement_descriptor, b"substitute\n") > 0
            finally:
                real_close(replacement_descriptor)
        return real_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(generator.os, "stat", substitute_before_staged_stat)

    with pytest.raises(RuntimeError, match="staging leaf changed before replacement"):
        generator._install(generator.OUTPUT_PATH, b"trusted-content\n", root)
    assert substituted
    assert not target.exists()
    assert not tuple(parent.glob(f".{target.name}.st0701-*"))


@pytest.mark.parametrize(
    ("invalid_kind", "message"),
    [
        ("fifo", "regular file"),
        ("hardlink", "one filesystem link"),
        ("size", "unexpected size"),
        ("mode", "unexpected mode"),
    ],
)
def test_installer_staged_metadata_validation_branches(
    tmp_path: Path,
    invalid_kind: str,
    message: str,
) -> None:
    staged = tmp_path / "staged"
    expected_size = len(b"content")
    if invalid_kind == "fifo":
        os.mkfifo(staged)
    else:
        staged.write_bytes(b"content")
        staged.chmod(0o644)
        if invalid_kind == "hardlink":
            os.link(staged, tmp_path / "second-name")
        elif invalid_kind == "size":
            expected_size += 1
        elif invalid_kind == "mode":
            staged.chmod(0o600)

    with pytest.raises(RuntimeError, match=message):
        generator._validate_staged_output(staged.lstat(), expected_size)


def test_installer_rejects_a_replacement_that_did_not_install_the_staged_inode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, parent, target = _prepared_output_parent(tmp_path)

    def copy_instead_of_replace(
        source: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        destination: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        assert src_dir_fd == dst_dir_fd
        source_path = parent / os.fsdecode(source)
        destination_path = parent / os.fsdecode(destination)
        destination_path.write_bytes(source_path.read_bytes())
        destination_path.chmod(0o644)

    monkeypatch.setattr(generator.os, "replace", copy_instead_of_replace)

    with pytest.raises(RuntimeError, match="preserve the staged inode"):
        generator._install(generator.OUTPUT_PATH, b"content\n", root)
    assert target.read_bytes() == b"content\n"
    assert not tuple(parent.glob(f".{target.name}.st0701-*"))


def test_installer_zero_write_fails_and_cleans_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, parent, target = _prepared_output_parent(tmp_path)
    monkeypatch.setattr(generator.os, "write", lambda _descriptor, _content: 0)

    with pytest.raises(RuntimeError, match="short ST-0701 generated write"):
        generator._install(generator.OUTPUT_PATH, b"content\n", root)
    assert not target.exists()
    assert not tuple(parent.glob(f".{target.name}.st0701-*"))


@pytest.mark.parametrize("failure_point", ["write", "replace"])
def test_installer_cleans_staging_after_write_or_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    root, parent, target = _prepared_output_parent(tmp_path)
    canary = f"private-{failure_point}-failure"

    if failure_point == "write":

        def fail_write(_descriptor: int, _content: object) -> int:
            raise OSError(canary)

        monkeypatch.setattr(generator.os, "write", fail_write)
    else:

        def fail_replace(*_args: object, **_kwargs: object) -> None:
            raise OSError(canary)

        monkeypatch.setattr(generator.os, "replace", fail_replace)

    with pytest.raises(RuntimeError, match="installed safely") as exc_info:
        generator._install(generator.OUTPUT_PATH, b"content\n", root)
    assert canary not in str(exc_info.value)
    assert not target.exists()
    assert not tuple(parent.glob(f".{target.name}.st0701-*"))


@pytest.mark.parametrize(
    "cleanup_case",
    [
        "cleanup_only_close",
        "primary_and_close",
        "primary_and_unlink",
        "primary_and_fsync",
    ],
)
def test_installer_cleanup_is_once_only_sanitized_and_preserves_primary_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cleanup_case: str,
) -> None:
    root, parent, target = _prepared_output_parent(tmp_path)
    real_open = os.open
    real_close = os.close
    real_fsync = os.fsync
    real_unlink = os.unlink
    opened: list[int] = []
    closed: list[int] = []
    synced: list[int] = []
    unlinked: list[str] = []
    cleanup_canary = f"private-{cleanup_case}-canary"

    def tracked_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        opened.append(descriptor)
        return descriptor

    def tracked_close(descriptor: int) -> None:
        closed.append(descriptor)
        real_close(descriptor)
        if "close" in cleanup_case:
            raise OSError(cleanup_canary)

    def tracked_fsync(descriptor: int) -> None:
        synced.append(descriptor)
        if cleanup_case == "primary_and_fsync":
            raise OSError(cleanup_canary)
        real_fsync(descriptor)

    def unlink_then_fail(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        *,
        dir_fd: int | None = None,
    ) -> None:
        unlinked.append(os.fsdecode(path))
        real_unlink(path, dir_fd=dir_fd)
        raise OSError(cleanup_canary)

    monkeypatch.setattr(generator.os, "open", tracked_open)
    monkeypatch.setattr(generator.os, "close", tracked_close)
    monkeypatch.setattr(generator.os, "fsync", tracked_fsync)
    if cleanup_case != "cleanup_only_close":
        monkeypatch.setattr(
            generator.os,
            "write",
            lambda _descriptor, _content: (_ for _ in ()).throw(
                RuntimeError("primary installation failure")
            ),
        )
    if cleanup_case == "primary_and_unlink":
        monkeypatch.setattr(generator.os, "unlink", unlink_then_fail)

    if cleanup_case == "cleanup_only_close":
        with pytest.raises(RuntimeError, match="artifact cleanup failed") as exc_info:
            generator._install(generator.OUTPUT_PATH, b"content\n", root)
        assert not getattr(exc_info.value, "__notes__", ())
        assert target.read_bytes() == b"content\n"
    else:
        with pytest.raises(
            RuntimeError, match="primary installation failure"
        ) as exc_info:
            generator._install(generator.OUTPUT_PATH, b"content\n", root)
        assert getattr(exc_info.value, "__notes__", ()) == [
            "ST-0701 generated artifact cleanup also failed"
        ]
        assert not target.exists()
    assert cleanup_canary not in str(exc_info.value)
    assert closed == list(reversed(opened))
    assert len(closed) == len(set(closed))
    assert synced[-1] == opened[-2]
    assert len(unlinked) == (1 if cleanup_case == "primary_and_unlink" else 0)
    assert not tuple(parent.glob(f".{target.name}.st0701-*"))


def test_exact_pinned_canonical_anchors_compile_successfully() -> None:
    repository = ContractRepository(CONTRACT_ROOT)
    content = repository.read_bytes(TASK_REGISTRY_PATH)
    assert b"&id001" in content
    assert b"*id001" in content
    compiled = generator.compile_registry(repository)
    assert compiled["task_count"] == 12


def test_yaml_alias_cycles_and_amplification_fail_closed() -> None:
    with pytest.raises(RuntimeError, match="cycle"):
        generator._strict_yaml(b"root: &root\n  child: *root\n", source="cycle")

    lines = ["a0: &a0 [x, x]"]
    for index in range(1, 18):
        lines.append(f"a{index}: &a{index} [*a{index - 1}, *a{index - 1}]")
    lines.append("root: *a17")
    with pytest.raises(RuntimeError, match="graph limit"):
        generator._strict_yaml(("\n".join(lines) + "\n").encode(), source="bomb")


def test_duplicate_registry_key_fails_after_explicit_test_repin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = ContractRepository(CONTRACT_ROOT)
    content = base.read_bytes(TASK_REGISTRY_PATH)
    duplicate = content.replace(
        b"  task_code: ai.opportunity_assessment.v1\n",
        b"  task_code: ai.opportunity_assessment.v1\n"
        b"  task_code: ai.opportunity_assessment.v1\n",
        1,
    )
    _repin_registry(monkeypatch, TASK_REGISTRY_PATH, duplicate)
    repository = FakeRepository(
        base, {TASK_REGISTRY_PATH: duplicate}, rebind_manifest=True
    )
    with pytest.raises(RuntimeError, match="strict YAML"):
        generator.compile_registry(repository)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("path", "old", "new", "message"),
    [
        (
            PROMPT_REGISTRY_PATH,
            b"  task_code: ai.opportunity_assessment.v1\n",
            b"  task_code: ai.unregistered.v1\n",
            "frontmatter task_code conflict",
        ),
        (
            TASK_REGISTRY_PATH,
            b"  route_code: route.reasoning_high.v1\n",
            b"  route_code: route.unknown.v1\n",
            "broken Route reference",
        ),
    ],
)
def test_conflict_and_bad_reference_fail_after_explicit_test_repin(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    old: bytes,
    new: bytes,
    message: str,
) -> None:
    base = ContractRepository(CONTRACT_ROOT)
    content = base.read_bytes(path)
    mutated = content.replace(old, new, 1)
    assert mutated != content
    _repin_registry(monkeypatch, path, mutated)
    repository = FakeRepository(base, {path: mutated}, rebind_manifest=True)
    with pytest.raises(RuntimeError, match=message):
        generator.compile_registry(repository)  # type: ignore[arg-type]


def test_unpinned_registry_and_tampered_prompt_bytes_fail() -> None:
    base = ContractRepository(CONTRACT_ROOT)
    registry_content = base.read_bytes(TASK_REGISTRY_PATH) + b"\n"
    unpinned = FakeRepository(
        base, {TASK_REGISTRY_PATH: registry_content}, rebind_manifest=True
    )
    with pytest.raises(RuntimeError, match="manifest binding mismatch"):
        generator.compile_registry(unpinned)  # type: ignore[arg-type]

    prompt_content = base.read_bytes(ARTICLE_DRAFT_PROMPT_PATH) + b"\n"
    tampered = FakeRepository(
        base, {ARTICLE_DRAFT_PROMPT_PATH: prompt_content}, rebind_manifest=False
    )
    with pytest.raises(RuntimeError, match="artifact hash mismatch"):
        generator.compile_registry(tampered)  # type: ignore[arg-type]


def test_generation_has_no_network_path(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    assert generator.render_outputs(REPOSITORY_ROOT)[generator.OUTPUT_PATH]

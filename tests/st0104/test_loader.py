"""Fail-closed read API and mutation tests for the ST-0104 loader."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from conftest import MANIFEST_NAME, VERSION_ROOT
from raos.shared.contract_repository import (
    MAX_ARTIFACT_BYTES,
    MAX_MANIFEST_BYTES,
    ContractRepository,
    ContractRepositoryError,
    parse_strict_json,
)


def copy_version(tmp_path: Path) -> Path:
    target = tmp_path / "raos-v0.4"
    shutil.copytree(VERSION_ROOT, target)
    return target


def load_manifest(root: Path) -> dict[str, Any]:
    value = json.loads((root / MANIFEST_NAME).read_bytes())
    assert isinstance(value, dict)
    return value


def write_manifest(root: Path, manifest: dict[str, Any]) -> None:
    (root / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def rebind_artifact(root: Path, path: str) -> None:
    manifest = load_manifest(root)
    payload = (root / path).read_bytes()
    entry = next(item for item in manifest["artifacts"] if item["path"] == path)
    entry["bytes"] = len(payload)
    entry["sha256"] = hashlib.sha256(payload).hexdigest()
    write_manifest(root, manifest)


def direct_reader(root: Path) -> ContractRepository:
    repository = object.__new__(ContractRepository)
    repository._root = root
    return repository


def test_repository_loads_complete_inventory_and_schema_id_index() -> None:
    repository = ContractRepository()
    assert repository.root == VERSION_ROOT
    assert len(repository.artifacts) == 306
    assert repository.artifacts[-1].path == "job-state.v1.yaml"
    assert len(repository.schema_ids) > 200
    assert repository.schema_ids == tuple(sorted(repository.schema_ids))
    assert len(repository.schema_retrieval_aliases) == 6
    assert repository.schema_retrieval_aliases == tuple(
        sorted(repository.schema_retrieval_aliases)
    )
    repository.verify_integrity()


def test_registered_reads_and_strict_json_loading() -> None:
    repository = ContractRepository()
    path = "contracts/schemas/common/actor-ref.schema.json"
    payload = repository.read_bytes(path)
    assert repository.read_text(path) == payload.decode("utf-8")
    document = repository.load_json(path)
    assert isinstance(document, dict)
    schema_id = document["$id"]
    assert isinstance(schema_id, str)
    assert repository.path_for_id(schema_id) == path
    assert repository.resolve_id(schema_id) == document

    retrieval_uri = repository.schema_retrieval_aliases[0]
    alias_path = repository.path_for_uri(retrieval_uri)
    alias_document = repository.resolve_uri(retrieval_uri)
    assert alias_path == (
        "contracts/schemas/ai-governance/ai-task-definition.v1.schema.json"
    )
    assert alias_document["$id"] == (
        "https://schemas.raos.local/ai-governance/ai-task-definition/v1"
    )


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/absolute",
        "../escape",
        "contracts/../job-state.v1.yaml",
        "contracts//double",
        "contracts\\windows",
        "https://schemas.raos.local/common/v1/actor-ref.schema.json",
        "contract-repository.v0.4.json",
        "contracts/unknown.schema.json",
    ],
)
def test_reads_reject_unregistered_or_unsafe_paths(path: str) -> None:
    repository = ContractRepository()
    with pytest.raises(ContractRepositoryError):
        repository.read_bytes(path)


@pytest.mark.parametrize(
    "schema_id",
    [
        "https://schemas.raos.local/unknown.schema.json",
        "http://schemas.raos.local/common/v1/actor-ref.schema.json",
        "https://example.com/schema.json",
        "https://schemas.raos.local/common/v1/actor-ref.schema.json#fragment",
        "https://schemas.raos.local/common/v1/actor-ref.schema.json?query=1",
        "http://[",
    ],
)
def test_schema_id_resolution_never_falls_back_to_remote(schema_id: str) -> None:
    repository = ContractRepository()
    with pytest.raises(ContractRepositoryError):
        repository.resolve_id(schema_id)


@pytest.mark.parametrize("mutation", ["missing", "extra", "tampered", "symlink"])
def test_filesystem_mutations_fail_on_construction(
    tmp_path: Path, mutation: str
) -> None:
    root = copy_version(tmp_path)
    target = root / "contracts" / "openapi-public.v0.1.yaml"
    if mutation == "missing":
        target.unlink()
    elif mutation == "extra":
        (root / "extra.txt").write_text("extra\n", encoding="utf-8")
    elif mutation == "tampered":
        target.write_bytes(target.read_bytes() + b"\n")
    else:
        target.unlink()
        target.symlink_to(root / "job-state.v1.yaml")
    with pytest.raises(ContractRepositoryError):
        ContractRepository(root)


def test_post_construction_mutation_is_rechecked(tmp_path: Path) -> None:
    root = copy_version(tmp_path)
    repository = ContractRepository(root)
    path = "contracts/openapi-public.v0.1.yaml"
    target = root / path
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(ContractRepositoryError, match="changed after verification"):
        repository.read_bytes(path)


def test_final_file_fifo_replacement_cannot_block_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copy_version(tmp_path)
    repository = ContractRepository(root)
    relative = "contracts/openapi-public.v0.1.yaml"
    target = root / relative
    real_open = os.open
    replaced = False

    def replace_with_fifo_before_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal replaced
        if not replaced and os.fsdecode(path) == target.name:
            assert dir_fd is not None
            assert flags & os.O_NONBLOCK
            target.unlink()
            os.mkfifo(target)
            replaced = True
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", replace_with_fifo_before_open)
    with pytest.raises(ContractRepositoryError, match="artifact is not regular"):
        repository.read_bytes(relative)
    assert replaced


def test_secure_read_uses_descriptor_relative_chain_and_required_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "reader-root"
    source = root / "nested" / "payload.bin"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"content")
    repository = direct_reader(root)
    real_open = os.open
    real_stat = os.stat
    open_calls: list[tuple[str, int, int | None, int]] = []
    stat_calls: list[tuple[str, int | None, bool]] = []

    def tracked_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        open_calls.append((os.fsdecode(path), flags, dir_fd, descriptor))
        return descriptor

    def tracked_stat(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> os.stat_result:
        stat_calls.append((os.fsdecode(path), dir_fd, follow_symlinks))
        return real_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(os, "open", tracked_open)
    monkeypatch.setattr(os, "stat", tracked_stat)

    assert repository._read_regular(PurePosixPath("nested/payload.bin")) == b"content"

    absolute_root = Path(os.path.abspath(root))
    expected_names = [
        absolute_root.anchor,
        *absolute_root.parts[1:],
        "nested",
        "payload.bin",
    ]
    assert [path for path, *_rest in open_calls] == expected_names
    assert open_calls[0][2] is None
    for previous, current in zip(open_calls, open_calls[1:]):
        assert current[2] == previous[3]
        assert "/" not in current[0]
    assert all(flags & os.O_NOFOLLOW for _path, flags, _dir_fd, _fd in open_calls)
    assert all(flags & os.O_CLOEXEC for _path, flags, _dir_fd, _fd in open_calls)
    assert all(flags & os.O_DIRECTORY for _path, flags, _dir_fd, _fd in open_calls[:-1])
    assert open_calls[-1][1] & os.O_NONBLOCK
    assert not open_calls[-1][1] & os.O_DIRECTORY

    expected_stat_names = [
        *absolute_root.parts[1:],
        "nested",
        "payload.bin",
    ]
    assert sorted(path for path, _dir_fd, _follow in stat_calls) == sorted(
        expected_stat_names * 2
    )
    assert all(dir_fd is not None for _path, dir_fd, _follow in stat_calls)
    assert all(not follow for _path, _dir_fd, follow in stat_calls)
    assert all("/" not in path for path, _dir_fd, _follow in stat_calls)


@pytest.mark.parametrize(
    "flag_name",
    ["O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK", "O_CLOEXEC"],
)
def test_secure_read_fails_closed_without_required_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    flag_name: str,
) -> None:
    (tmp_path / "payload.bin").write_bytes(b"content")
    repository = direct_reader(tmp_path)
    monkeypatch.setattr(os, flag_name, 0)

    with pytest.raises(
        ContractRepositoryError,
        match="required repository filesystem safety is unavailable",
    ):
        repository._read_regular(PurePosixPath("payload.bin"))


@pytest.mark.parametrize("location", ["root", "ancestor", "leaf"])
def test_secure_read_rejects_symlinks(tmp_path: Path, location: str) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "payload.bin").write_bytes(b"outside")

    if location == "root":
        root = tmp_path / "linked-root"
        root.symlink_to(outside, target_is_directory=True)
        relative = PurePosixPath("payload.bin")
    else:
        root = tmp_path / "reader-root"
        root.mkdir()
        if location == "ancestor":
            (root / "linked").symlink_to(outside, target_is_directory=True)
            relative = PurePosixPath("linked/payload.bin")
        else:
            (root / "linked.bin").symlink_to(outside / "payload.bin")
            relative = PurePosixPath("linked.bin")

    with pytest.raises(ContractRepositoryError):
        direct_reader(root)._read_regular(relative)


@pytest.mark.parametrize("after_open", [False, True], ids=["before", "after"])
def test_secure_read_rejects_repository_root_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    after_open: bool,
) -> None:
    root = tmp_path / "reader-root"
    root.mkdir()
    (root / "payload.bin").write_bytes(b"trusted")
    replacement = tmp_path / "replacement-root"
    replacement.mkdir()
    (replacement / "payload.bin").write_bytes(b"untrusted")
    repository = direct_reader(root)
    real_open = os.open
    swapped = False

    def swap_root(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        is_target = (
            not swapped
            and os.fsdecode(path) == root.name
            and bool(flags & os.O_DIRECTORY)
        )
        if is_target and not after_open:
            swapped = True
            root.rename(tmp_path / "captured-root")
            replacement.rename(root)
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if is_target and after_open:
            swapped = True
            root.rename(tmp_path / "captured-root")
            replacement.rename(root)
        return descriptor

    monkeypatch.setattr(os, "open", swap_root)
    with pytest.raises(ContractRepositoryError) as exc_info:
        repository._read_regular(PurePosixPath("payload.bin"))
    if after_open:
        assert str(exc_info.value) in {
            "contract repository root changed before secure capture",
            "contract repository root changed during secure capture",
        }
    else:
        assert (
            str(exc_info.value)
            == "contract repository root changed before secure capture"
        )
    assert swapped


def test_secure_read_allows_unrelated_parent_entry_churn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "reader-root"
    root.mkdir()
    (root / "payload.bin").write_bytes(b"trusted")
    repository = direct_reader(root)
    real_read = os.read
    churned = False

    def churn_parent_then_read(descriptor: int, count: int) -> bytes:
        nonlocal churned
        if not churned:
            churned = True
            (tmp_path / "unrelated-sibling.bin").write_bytes(b"outside")
        return real_read(descriptor, count)

    monkeypatch.setattr(os, "read", churn_parent_then_read)
    assert repository._read_regular(PurePosixPath("payload.bin")) == b"trusted"
    assert churned


@pytest.mark.parametrize("after_open", [False, True], ids=["before", "after"])
def test_secure_read_rejects_artifact_ancestor_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    after_open: bool,
) -> None:
    root = tmp_path / "reader-root"
    ancestor = root / "nested"
    ancestor.mkdir(parents=True)
    (ancestor / "payload.bin").write_bytes(b"trusted")
    replacement = root / "replacement"
    replacement.mkdir()
    (replacement / "payload.bin").write_bytes(b"untrusted")
    repository = direct_reader(root)
    real_open = os.open
    swapped = False

    def swap_ancestor(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        is_target = (
            not swapped
            and os.fsdecode(path) == ancestor.name
            and bool(flags & os.O_DIRECTORY)
        )
        if is_target and not after_open:
            swapped = True
            ancestor.rename(root / "captured-nested")
            replacement.rename(ancestor)
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if is_target and after_open:
            swapped = True
            ancestor.rename(root / "captured-nested")
            replacement.rename(ancestor)
        return descriptor

    monkeypatch.setattr(os, "open", swap_ancestor)
    with pytest.raises(ContractRepositoryError) as exc_info:
        repository._read_regular(PurePosixPath("nested/payload.bin"))
    if after_open:
        assert str(exc_info.value) in {
            "artifact ancestor changed before secure capture: nested/payload.bin",
            "artifact ancestor changed during read: nested/payload.bin",
        }
    else:
        assert (
            str(exc_info.value)
            == "artifact ancestor changed before secure capture: nested/payload.bin"
        )
    assert swapped


@pytest.mark.parametrize("after_open", [False, True], ids=["before", "after"])
def test_secure_read_rejects_leaf_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    after_open: bool,
) -> None:
    root = tmp_path / "reader-root"
    root.mkdir()
    source = root / "payload.bin"
    source.write_bytes(b"trusted")
    replacement = root / "replacement.bin"
    replacement.write_bytes(b"untrust")
    repository = direct_reader(root)
    real_open = os.open
    swapped = False

    def swap_leaf(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        is_target = not swapped and os.fsdecode(path) == source.name
        if is_target and not after_open:
            swapped = True
            source.rename(root / "captured-payload.bin")
            replacement.rename(source)
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if is_target and after_open:
            swapped = True
            source.rename(root / "captured-payload.bin")
            replacement.rename(source)
        return descriptor

    monkeypatch.setattr(os, "open", swap_leaf)
    with pytest.raises(ContractRepositoryError) as exc_info:
        repository._read_regular(PurePosixPath("payload.bin"))
    if after_open:
        assert str(exc_info.value) in {
            "artifact was replaced before open: payload.bin",
            "artifact changed during read: payload.bin",
        }
    else:
        assert str(exc_info.value) == "artifact was replaced before open: payload.bin"
    assert swapped


def test_secure_read_rejects_hardlinked_leaf(tmp_path: Path) -> None:
    source = tmp_path / "payload.bin"
    source.write_bytes(b"content")
    os.link(source, tmp_path / "second-name.bin")

    with pytest.raises(ContractRepositoryError, match="one filesystem link"):
        direct_reader(tmp_path)._read_regular(PurePosixPath("payload.bin"))


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        (b"mutated!", "changed during read"),
        (b"x", "short artifact read"),
        (b"extended-content", "changed during read"),
    ],
    ids=["rewrite", "truncate", "extend"],
)
def test_secure_read_rejects_same_inode_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replacement: bytes,
    message: str,
) -> None:
    source = tmp_path / "payload.bin"
    source.write_bytes(b"original")
    repository = direct_reader(tmp_path)
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

    monkeypatch.setattr(os, "read", mutate_then_read)
    with pytest.raises(ContractRepositoryError, match=message):
        repository._read_regular(PurePosixPath("payload.bin"))
    assert mutated


@pytest.mark.parametrize(
    "maximum_bytes",
    [MAX_MANIFEST_BYTES, MAX_ARTIFACT_BYTES],
    ids=["manifest-2-mib", "artifact-16-mib"],
)
def test_secure_read_enforces_exact_size_boundary(
    tmp_path: Path,
    maximum_bytes: int,
) -> None:
    source = tmp_path / "payload.bin"
    with source.open("wb") as stream:
        stream.truncate(maximum_bytes)
    repository = direct_reader(tmp_path)

    assert (
        len(
            repository._read_regular(
                PurePosixPath("payload.bin"), maximum_bytes=maximum_bytes
            )
        )
        == maximum_bytes
    )

    with source.open("r+b") as stream:
        stream.truncate(maximum_bytes + 1)
    with pytest.raises(ContractRepositoryError, match="exceeds size limit"):
        repository._read_regular(
            PurePosixPath("payload.bin"), maximum_bytes=maximum_bytes
        )


def test_secure_read_rejects_short_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "payload.bin").write_bytes(b"content")
    monkeypatch.setattr(os, "read", lambda _descriptor, _count: b"")

    with pytest.raises(ContractRepositoryError, match="short artifact read"):
        direct_reader(tmp_path)._read_regular(PurePosixPath("payload.bin"))


def test_secure_read_sanitizes_read_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canary = "private-read-failure-canary"
    (tmp_path / "payload.bin").write_bytes(b"content")

    def fail_read(_descriptor: int, _count: int) -> bytes:
        raise OSError(canary)

    monkeypatch.setattr(os, "read", fail_read)
    with pytest.raises(
        ContractRepositoryError, match="could not be captured safely"
    ) as exc_info:
        direct_reader(tmp_path)._read_regular(PurePosixPath("payload.bin"))
    assert canary not in str(exc_info.value)


def test_secure_read_sanitizes_close_only_failure_and_closes_once_in_reverse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canary = "private-close-failure-canary"
    source = tmp_path / "nested" / "payload.bin"
    source.parent.mkdir()
    source.write_bytes(b"content")
    repository = direct_reader(tmp_path)
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
        closed.append(descriptor)
        real_close(descriptor)
        if not failed:
            failed = True
            raise OSError(canary)

    monkeypatch.setattr(os, "open", tracked_open)
    monkeypatch.setattr(os, "close", close_then_fail)
    with pytest.raises(
        ContractRepositoryError, match="descriptor cleanup failed"
    ) as exc_info:
        repository._read_regular(PurePosixPath("nested/payload.bin"))
    assert canary not in str(exc_info.value)
    assert closed == list(reversed(opened))
    assert len(closed) == len(set(closed))


def test_secure_read_preserves_primary_failure_when_cleanup_also_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "payload.bin").write_bytes(b"content")
    repository = direct_reader(tmp_path)
    real_open = os.open
    real_close = os.close
    opened: list[int] = []
    closed: list[int] = []

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
        closed.append(descriptor)
        real_close(descriptor)
        raise OSError("private cleanup detail")

    monkeypatch.setattr(os, "open", tracked_open)
    monkeypatch.setattr(os, "read", lambda _descriptor, _count: b"")
    monkeypatch.setattr(os, "close", close_then_fail)
    with pytest.raises(
        ContractRepositoryError, match="short artifact read"
    ) as exc_info:
        repository._read_regular(PurePosixPath("payload.bin"))
    assert getattr(exc_info.value, "__notes__", ()) == [
        "descriptor cleanup also failed"
    ]
    assert closed == list(reversed(opened))
    assert len(closed) == len(set(closed))


def test_inventory_uses_only_descriptor_relative_traversal_and_required_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "inventory-root"
    (root / "nested" / "deeper").mkdir(parents=True)
    (root / "root.bin").write_bytes(b"root")
    (root / "nested" / "payload.bin").write_bytes(b"nested")
    (root / "nested" / "deeper" / "leaf.bin").write_bytes(b"leaf")
    repository = direct_reader(root)
    real_open = os.open
    real_close = os.close
    real_stat = os.stat
    real_listdir = os.listdir
    open_calls: list[tuple[str, int, int | None, int]] = []
    close_calls: list[int] = []
    active_descriptors: set[int] = set()
    stat_calls: list[tuple[str, int | None, bool]] = []
    listdir_calls: list[int] = []

    def tracked_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        assert descriptor not in active_descriptors
        active_descriptors.add(descriptor)
        open_calls.append((os.fsdecode(path), flags, dir_fd, descriptor))
        return descriptor

    def tracked_close(descriptor: int) -> None:
        assert descriptor in active_descriptors
        active_descriptors.remove(descriptor)
        close_calls.append(descriptor)
        real_close(descriptor)

    def tracked_stat(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> os.stat_result:
        stat_calls.append((os.fsdecode(path), dir_fd, follow_symlinks))
        return real_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    def tracked_listdir(descriptor: int) -> list[str]:
        assert isinstance(descriptor, int)
        listdir_calls.append(descriptor)
        return real_listdir(descriptor)

    def forbidden_scandir(*_args: object, **_kwargs: object) -> None:
        pytest.fail("inventory traversal must not call os.scandir")

    monkeypatch.setattr(os, "open", tracked_open)
    monkeypatch.setattr(os, "close", tracked_close)
    monkeypatch.setattr(os, "stat", tracked_stat)
    monkeypatch.setattr(os, "listdir", tracked_listdir)
    monkeypatch.setattr(os, "scandir", forbidden_scandir)

    files, directories = repository._filesystem_inventory()

    assert files == {
        "nested/deeper/leaf.bin",
        "nested/payload.bin",
        "root.bin",
    }
    assert directories == {"nested", "nested/deeper"}
    assert open_calls[0][0] == Path(os.path.abspath(root)).anchor
    assert open_calls[0][2] is None
    for path, _flags, dir_fd, _descriptor in open_calls[1:]:
        assert dir_fd is not None
        assert "/" not in path
    assert all(flags & os.O_NOFOLLOW for _path, flags, _dir_fd, _fd in open_calls)
    assert all(flags & os.O_CLOEXEC for _path, flags, _dir_fd, _fd in open_calls)
    flags_by_descriptor = {
        descriptor: flags for _path, flags, _dir_fd, descriptor in open_calls
    }
    assert len(listdir_calls) == 6
    assert len(set(listdir_calls)) == 3
    assert all(listdir_calls.count(descriptor) == 2 for descriptor in listdir_calls)
    assert all(
        flags_by_descriptor[descriptor] & os.O_DIRECTORY for descriptor in listdir_calls
    )
    assert all(dir_fd is not None for _path, dir_fd, _follow in stat_calls)
    assert all(not follow for _path, _dir_fd, follow in stat_calls)
    assert all("/" not in path for path, _dir_fd, _follow in stat_calls)
    assert not active_descriptors
    assert len(close_calls) == len(open_calls)


@pytest.mark.parametrize(
    "flag_name",
    ["O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK", "O_CLOEXEC"],
)
def test_inventory_fails_closed_without_required_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    flag_name: str,
) -> None:
    (tmp_path / "payload.bin").write_bytes(b"content")
    monkeypatch.setattr(os, flag_name, 0)

    with pytest.raises(
        ContractRepositoryError,
        match="required repository filesystem safety is unavailable",
    ):
        direct_reader(tmp_path)._filesystem_inventory()


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="descriptor-relative inventory is a Linux contract",
)
def test_contract_repository_loads_under_nofile_256() -> None:
    code = """
import resource
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "python"))
from raos.shared.contract_repository import ContractRepository

_soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
if hard != resource.RLIM_INFINITY and hard < 256:
    raise RuntimeError("hard RLIMIT_NOFILE below test contract")
resource.setrlimit(resource.RLIMIT_NOFILE, (256, hard))
repository = ContractRepository()
assert len(repository.artifacts) == 306
print(len(repository.artifacts))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=VERSION_ROOT.parents[1],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "306\n"


@pytest.mark.parametrize("after_open", [False, True], ids=["before", "after"])
def test_inventory_rejects_repository_root_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    after_open: bool,
) -> None:
    root = tmp_path / "inventory-root"
    root.mkdir()
    (root / "payload.bin").write_bytes(b"trusted")
    replacement = tmp_path / "replacement-root"
    replacement.mkdir()
    (replacement / "payload.bin").write_bytes(b"untrusted")
    repository = direct_reader(root)
    real_open = os.open
    swapped = False

    def swap_root(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        is_target = (
            not swapped
            and os.fsdecode(path) == root.name
            and bool(flags & os.O_DIRECTORY)
        )
        if is_target and not after_open:
            swapped = True
            root.rename(tmp_path / "captured-root")
            replacement.rename(root)
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if is_target and after_open:
            swapped = True
            root.rename(tmp_path / "captured-root")
            replacement.rename(root)
        return descriptor

    monkeypatch.setattr(os, "open", swap_root)
    with pytest.raises(ContractRepositoryError) as exc_info:
        repository._filesystem_inventory()
    if after_open:
        assert str(exc_info.value) in {
            "contract repository root changed before inventory capture",
            "contract repository root changed during inventory",
        }
    else:
        assert (
            str(exc_info.value)
            == "contract repository root changed before inventory capture"
        )
    assert swapped


def test_inventory_allows_unrelated_parent_entry_churn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "inventory-root"
    root.mkdir()
    (root / "payload.bin").write_bytes(b"trusted")
    repository = direct_reader(root)
    real_listdir = os.listdir
    churned = False

    def churn_parent_after_listing(descriptor: int) -> list[str]:
        nonlocal churned
        names = real_listdir(descriptor)
        if not churned:
            churned = True
            (tmp_path / "unrelated-sibling.bin").write_bytes(b"outside")
        return names

    monkeypatch.setattr(os, "listdir", churn_parent_after_listing)
    assert repository._filesystem_inventory() == ({"payload.bin"}, set())
    assert churned


@pytest.mark.parametrize("after_open", [False, True], ids=["before", "after"])
def test_inventory_rejects_nested_directory_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    after_open: bool,
) -> None:
    root = tmp_path / "inventory-root"
    nested = root / "nested"
    nested.mkdir(parents=True)
    (nested / "payload.bin").write_bytes(b"trusted")
    replacement = tmp_path / "replacement-nested"
    replacement.mkdir()
    (replacement / "payload.bin").write_bytes(b"untrusted")
    repository = direct_reader(root)
    real_open = os.open
    swapped = False

    def swap_nested(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        is_target = (
            not swapped
            and os.fsdecode(path) == nested.name
            and bool(flags & os.O_DIRECTORY)
        )
        if is_target and not after_open:
            swapped = True
            nested.rename(tmp_path / "captured-nested")
            replacement.rename(nested)
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if is_target and after_open:
            swapped = True
            nested.rename(tmp_path / "captured-nested")
            replacement.rename(nested)
        return descriptor

    monkeypatch.setattr(os, "open", swap_nested)
    with pytest.raises(ContractRepositoryError) as exc_info:
        repository._filesystem_inventory()
    if after_open:
        assert str(exc_info.value) in {
            "directory changed before inventory capture: nested",
            "directory changed during inventory: nested",
        }
    else:
        assert (
            str(exc_info.value) == "directory changed before inventory capture: nested"
        )
    assert swapped


@pytest.mark.parametrize("after_open", [False, True], ids=["before", "after"])
def test_inventory_rejects_file_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    after_open: bool,
) -> None:
    root = tmp_path / "inventory-root"
    root.mkdir()
    source = root / "payload.bin"
    source.write_bytes(b"trusted")
    replacement = tmp_path / "replacement.bin"
    replacement.write_bytes(b"untrust")
    repository = direct_reader(root)
    real_open = os.open
    swapped = False

    def swap_file(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        is_target = (
            not swapped
            and os.fsdecode(path) == source.name
            and not bool(flags & os.O_DIRECTORY)
        )
        if is_target and not after_open:
            swapped = True
            source.rename(tmp_path / "captured-payload.bin")
            replacement.rename(source)
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if is_target and after_open:
            swapped = True
            source.rename(tmp_path / "captured-payload.bin")
            replacement.rename(source)
        return descriptor

    monkeypatch.setattr(os, "open", swap_file)
    with pytest.raises(ContractRepositoryError) as exc_info:
        repository._filesystem_inventory()
    if after_open:
        assert str(exc_info.value) in {
            "file changed before inventory capture: payload.bin",
            "file changed during inventory: payload.bin",
        }
    else:
        assert (
            str(exc_info.value) == "file changed before inventory capture: payload.bin"
        )
    assert swapped


@pytest.mark.parametrize(
    ("mutation", "expected_messages"),
    [
        ("add", {"contract repository root changed during inventory"}),
        ("remove", {"repository inventory could not be captured safely"}),
        ("replace", {"contract repository root changed during inventory"}),
        ("symlink", {"symlink in repository: payload.bin"}),
        ("special", {"special file in repository: payload.bin"}),
    ],
)
def test_inventory_rejects_entry_mutation_after_listing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected_messages: set[str],
) -> None:
    root = tmp_path / "inventory-root"
    root.mkdir()
    source = root / "payload.bin"
    source.write_bytes(b"trusted")
    replacement = tmp_path / "replacement.bin"
    replacement.write_bytes(b"untrust")
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    repository = direct_reader(root)
    real_listdir = os.listdir
    mutated = False

    def mutate_after_list(descriptor: int) -> list[str]:
        nonlocal mutated
        names = real_listdir(descriptor)
        if not mutated:
            mutated = True
            if mutation == "add":
                (root / "added.bin").write_bytes(b"added")
            elif mutation == "remove":
                source.unlink()
            elif mutation == "replace":
                source.rename(root / "captured-payload.bin")
                replacement.rename(source)
            elif mutation == "symlink":
                source.unlink()
                source.symlink_to(outside)
            else:
                source.unlink()
                os.mkfifo(source)
        return names

    monkeypatch.setattr(os, "listdir", mutate_after_list)
    with pytest.raises(ContractRepositoryError) as exc_info:
        repository._filesystem_inventory()
    assert str(exc_info.value) in expected_messages
    assert mutated


def test_inventory_rejects_same_inode_file_mutation_after_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "inventory-root"
    trigger = root / "trigger"
    trigger.mkdir(parents=True)
    source = root / "payload.bin"
    source.write_bytes(b"original")
    repository = direct_reader(root)
    real_listdir = os.listdir
    list_count = 0

    def mutate_during_later_scan(descriptor: int) -> list[str]:
        nonlocal list_count
        names = real_listdir(descriptor)
        list_count += 1
        if list_count == 2:
            source.write_bytes(b"changed!")
            metadata = source.stat()
            os.utime(
                source,
                ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000_000),
            )
        return names

    monkeypatch.setattr(os, "listdir", mutate_during_later_scan)
    with pytest.raises(
        ContractRepositoryError,
        match="file changed during inventory: payload.bin",
    ):
        repository._filesystem_inventory()
    assert list_count == 2


def test_inventory_rejects_nested_directory_mutation_after_listing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "inventory-root"
    nested = root / "nested"
    nested.mkdir(parents=True)
    repository = direct_reader(root)
    real_listdir = os.listdir
    list_count = 0

    def mutate_nested_after_list(descriptor: int) -> list[str]:
        nonlocal list_count
        names = real_listdir(descriptor)
        list_count += 1
        if list_count == 2:
            (nested / "added.bin").write_bytes(b"added")
        return names

    monkeypatch.setattr(os, "listdir", mutate_nested_after_list)
    with pytest.raises(
        ContractRepositoryError,
        match="directory changed during inventory: nested",
    ):
        repository._filesystem_inventory()
    assert list_count == 3


@pytest.mark.parametrize("failure", ["list", "stat", "open"])
def test_inventory_sanitizes_list_stat_and_open_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    canary = f"private-{failure}-failure-canary"
    root = tmp_path / "inventory-root"
    root.mkdir()
    (root / "payload.bin").write_bytes(b"content")
    real_open = os.open
    real_stat = os.stat

    if failure == "list":

        def fail_listdir(_descriptor: int) -> list[str]:
            raise OSError(canary)

        monkeypatch.setattr(os, "listdir", fail_listdir)
    elif failure == "stat":

        def fail_stat(
            path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
            *,
            dir_fd: int | None = None,
            follow_symlinks: bool = True,
        ) -> os.stat_result:
            if os.fsdecode(path) == "payload.bin":
                raise OSError(canary)
            return real_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

        monkeypatch.setattr(os, "stat", fail_stat)
    else:

        def fail_open(
            path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            if os.fsdecode(path) == "payload.bin":
                raise OSError(canary)
            return real_open(path, flags, mode, dir_fd=dir_fd)

        monkeypatch.setattr(os, "open", fail_open)

    with pytest.raises(
        ContractRepositoryError,
        match="repository inventory could not be captured safely",
    ) as exc_info:
        direct_reader(root)._filesystem_inventory()
    assert canary not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


def test_inventory_sanitizes_cleanup_only_failure_and_closes_once_in_reverse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canary = "private-inventory-close-failure-canary"
    root = tmp_path / "inventory-root"
    (root / "nested").mkdir(parents=True)
    (root / "nested" / "payload.bin").write_bytes(b"content")
    repository = direct_reader(root)
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
        closed.append(descriptor)
        real_close(descriptor)
        if not failed:
            failed = True
            raise OSError(canary)

    monkeypatch.setattr(os, "open", tracked_open)
    monkeypatch.setattr(os, "close", close_then_fail)
    with pytest.raises(
        ContractRepositoryError,
        match="repository inventory file descriptor cleanup failed",
    ) as exc_info:
        repository._filesystem_inventory()
    assert canary not in str(exc_info.value)
    assert closed == list(reversed(opened))
    assert len(closed) == len(set(closed))


def test_inventory_preserves_file_primary_failure_when_immediate_close_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "inventory-root"
    root.mkdir()
    (root / "payload.bin").write_bytes(b"content")
    repository = direct_reader(root)
    real_open = os.open
    real_close = os.close
    real_fstat = os.fstat
    target_descriptor: int | None = None
    close_counts: dict[int, int] = {}

    def tracked_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal target_descriptor
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if os.fsdecode(path) == "payload.bin":
            target_descriptor = descriptor
        return descriptor

    def reject_target_fstat(descriptor: int) -> os.stat_result:
        if descriptor == target_descriptor:
            return os.stat(root)
        return real_fstat(descriptor)

    def close_target_then_fail(descriptor: int) -> None:
        close_counts[descriptor] = close_counts.get(descriptor, 0) + 1
        real_close(descriptor)
        if descriptor == target_descriptor:
            raise OSError("private immediate close detail")

    monkeypatch.setattr(os, "open", tracked_open)
    monkeypatch.setattr(os, "fstat", reject_target_fstat)
    monkeypatch.setattr(os, "close", close_target_then_fail)
    with pytest.raises(
        ContractRepositoryError,
        match="file changed before inventory capture: payload.bin",
    ) as exc_info:
        repository._filesystem_inventory()
    assert getattr(exc_info.value, "__notes__", ()) == [
        "inventory file descriptor cleanup also failed"
    ]
    assert target_descriptor is not None
    assert close_counts[target_descriptor] == 1


def test_inventory_preserves_primary_failure_when_cleanup_also_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary_canary = "private-inventory-list-failure-canary"
    cleanup_canary = "private-inventory-cleanup-failure-canary"
    root = tmp_path / "inventory-root"
    root.mkdir()
    repository = direct_reader(root)
    real_open = os.open
    real_close = os.close
    opened: list[int] = []
    closed: list[int] = []

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

    def fail_listdir(_descriptor: int) -> list[str]:
        raise OSError(primary_canary)

    def close_then_fail(descriptor: int) -> None:
        closed.append(descriptor)
        real_close(descriptor)
        raise OSError(cleanup_canary)

    monkeypatch.setattr(os, "open", tracked_open)
    monkeypatch.setattr(os, "listdir", fail_listdir)
    monkeypatch.setattr(os, "close", close_then_fail)
    with pytest.raises(
        ContractRepositoryError,
        match="repository inventory could not be captured safely",
    ) as exc_info:
        repository._filesystem_inventory()
    assert primary_canary not in str(exc_info.value)
    assert cleanup_canary not in str(exc_info.value)
    assert getattr(exc_info.value, "__notes__", ()) == [
        "inventory descriptor cleanup also failed"
    ]
    assert closed == list(reversed(opened))
    assert len(closed) == len(set(closed))


def test_manifest_duplicate_key_unknown_key_and_bad_hash_fail(tmp_path: Path) -> None:
    duplicate_root = copy_version(tmp_path / "duplicate")
    manifest_path = duplicate_root / MANIFEST_NAME
    content = manifest_path.read_text(encoding="utf-8")
    manifest_path.write_text(
        content.replace('  "document": {', '  "document": {},\n  "document": {', 1),
        encoding="utf-8",
    )
    with pytest.raises(ContractRepositoryError, match="duplicate JSON object key"):
        ContractRepository(duplicate_root)

    unknown_root = copy_version(tmp_path / "unknown")
    manifest = load_manifest(unknown_root)
    manifest["unknown"] = True
    write_manifest(unknown_root, manifest)
    with pytest.raises(ContractRepositoryError, match="top-level"):
        ContractRepository(unknown_root)

    hash_root = copy_version(tmp_path / "hash")
    manifest = load_manifest(hash_root)
    manifest["artifacts"][0]["sha256"] = "0" * 64
    write_manifest(hash_root, manifest)
    with pytest.raises(ContractRepositoryError, match="SHA-256 mismatch"):
        ContractRepository(hash_root)

    alias_root = copy_version(tmp_path / "alias")
    manifest = load_manifest(alias_root)
    manifest["schema_resolution"]["retrieval_uri_aliases"][0]["path"] = (
        "contracts/schemas/common/actor-ref.schema.json"
    )
    write_manifest(alias_root, manifest)
    with pytest.raises(ContractRepositoryError, match="schema_resolution"):
        ContractRepository(alias_root)


def test_casefold_collision_and_symlinked_root_fail(tmp_path: Path) -> None:
    root = copy_version(tmp_path / "casefold")
    original = root / "contracts" / "openapi-public.v0.1.yaml"
    duplicate = root / "contracts" / "OPENAPI-PUBLIC.v0.1.yaml"
    duplicate.write_bytes(original.read_bytes())
    with pytest.raises(ContractRepositoryError, match="casefold"):
        ContractRepository(root)

    link = tmp_path / "linked-root"
    link.symlink_to(VERSION_ROOT, target_is_directory=True)
    with pytest.raises(ContractRepositoryError, match="symlink|not a real directory"):
        ContractRepository(link)


def test_symlinked_ancestor_of_root_fails(tmp_path: Path) -> None:
    real_parent = tmp_path / "real-parent"
    root = copy_version(real_parent)
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(ContractRepositoryError, match="contains a symlink"):
        ContractRepository(linked_parent / root.name)


def test_malformed_json_and_duplicate_schema_id_fail_after_valid_rebind(
    tmp_path: Path,
) -> None:
    malformed_root = copy_version(tmp_path / "malformed")
    malformed_path = "contracts/schemas/common/actor-ref.schema.json"
    (malformed_root / malformed_path).write_text("{invalid\n", encoding="utf-8")
    rebind_artifact(malformed_root, malformed_path)
    with pytest.raises(ContractRepositoryError, match="invalid JSON"):
        ContractRepository(malformed_root)

    duplicate_root = copy_version(tmp_path / "duplicate-id")
    first_path = "contracts/schemas/common/actor-ref.schema.json"
    second_path = "contracts/schemas/common/artifact-ref.schema.json"
    first = json.loads((duplicate_root / first_path).read_bytes())
    second = json.loads((duplicate_root / second_path).read_bytes())
    second["$id"] = first["$id"]
    (duplicate_root / second_path).write_text(
        json.dumps(second, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rebind_artifact(duplicate_root, second_path)
    with pytest.raises(ContractRepositoryError, match="duplicate top-level \\$id"):
        ContractRepository(duplicate_root)


@pytest.mark.parametrize(
    "payload",
    [
        b'{"duplicate": 1, "duplicate": 2}',
        b'{"nan": NaN}',
        b"\xff",
        b"[",
    ],
)
def test_strict_json_rejects_extensions_and_malformed_input(payload: bytes) -> None:
    with pytest.raises(ContractRepositoryError):
        parse_strict_json(payload, source="test")

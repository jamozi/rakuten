"""Hostile local-only credential-intake tests for ST-0505."""

from __future__ import annotations

import ast
import ctypes
import json
import os
from pathlib import Path
import resource
import shlex
import stat
import subprocess
import sys
import termios
from typing import Any, Callable

import pytest

from scripts import rakuten_live_smoke_credentials as credentials


def _private_directory(path: Path) -> None:
    path.mkdir(mode=0o700)
    path.chmod(0o700)


def _private_file(path: Path, value: bytes = b"fixture\n") -> None:
    path.write_bytes(value)
    path.chmod(0o600)


def _ready_store(root: Path) -> Path:
    secret_parent = root / credentials.SECRET_PARENT_NAME
    store = secret_parent / credentials.SECRET_STORE_NAME
    _private_directory(secret_parent)
    _private_directory(store)
    _private_directory(secret_parent / credentials.SECRET_READY_NAME)
    _private_directory(secret_parent / credentials.SECRET_COMMITTED_NAME)
    for alias in credentials.SECRET_ALIASES:
        _private_file(store / alias)
    return store


def _inspect(root: Path) -> credentials.CredentialStoreStatus:
    return credentials.inspect_store(root, expected_root=root)


def test_contract_constants_are_exact_and_affiliate_alias_is_absent() -> None:
    assert credentials.EXPECTED_REPOSITORY_ROOT == Path("/home/minami/rakuten")
    assert credentials.SECRET_PARENT_NAME == ".secrets"
    assert credentials.SECRET_STORE_NAME == "rakuten-live-smoke"
    assert credentials.SECRET_STAGING_NAME == ".rakuten-live-smoke.preparing"
    assert credentials.SECRET_COMMITTING_NAME == ".rakuten-live-smoke.committing"
    assert credentials.SECRET_READY_NAME == ".rakuten-live-smoke.ready"
    assert credentials.SECRET_VALIDATING_NAME == ".rakuten-live-smoke.validating"
    assert credentials.SECRET_COMMITTED_NAME == ".rakuten-live-smoke.committed"
    assert credentials.SECRET_ALIASES == (
        "rakuten_web_service_application_id",
        "rakuten_web_service_access_key",
    )
    source = Path(credentials.__file__).read_text(encoding="utf-8")
    assert "rakuten_affiliate_id" not in source


def test_check_reports_absent_without_creating_any_path(tmp_path: Path) -> None:
    assert _inspect(tmp_path) is credentials.CredentialStoreStatus.ABSENT
    assert not (tmp_path / credentials.SECRET_PARENT_NAME).exists()


def test_check_reports_ready_from_metadata_only(tmp_path: Path) -> None:
    _ready_store(tmp_path)
    assert _inspect(tmp_path) is credentials.CredentialStoreStatus.READY


@pytest.mark.parametrize(
    "missing", (credentials.SECRET_READY_NAME, credentials.SECRET_COMMITTED_NAME)
)
def test_check_rejects_final_store_with_missing_readiness_marker(
    tmp_path: Path, missing: str
) -> None:
    _ready_store(tmp_path)
    (tmp_path / credentials.SECRET_PARENT_NAME / missing).rmdir()
    with pytest.raises(credentials.CredentialIntakeFailure) as caught:
        _inspect(tmp_path)
    assert caught.value.code is credentials.CredentialIntakeFailureCode.STORE_INVALID


@pytest.mark.parametrize(
    "active_name",
    (
        credentials.SECRET_STAGING_NAME,
        credentials.SECRET_COMMITTING_NAME,
        credentials.SECRET_VALIDATING_NAME,
    ),
)
@pytest.mark.parametrize("with_final", (False, True))
def test_check_rejects_active_residue_even_with_final_ready_shape(
    tmp_path: Path, active_name: str, with_final: bool
) -> None:
    if with_final:
        _ready_store(tmp_path)
    else:
        _private_directory(tmp_path / credentials.SECRET_PARENT_NAME)
    _private_directory(tmp_path / credentials.SECRET_PARENT_NAME / active_name)
    with pytest.raises(credentials.CredentialIntakeFailure) as caught:
        _inspect(tmp_path)
    assert caught.value.code is credentials.CredentialIntakeFailureCode.STORE_INVALID


@pytest.mark.parametrize(
    "mode",
    (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFSOCK),
)
def test_metadata_predicates_reject_wrong_owner_and_every_special_type(
    mode: int,
) -> None:
    unsafe = os.stat_result((mode | 0o600, 1, 1, 1, os.geteuid(), 0, 1, 0, 0, 0))
    wrong_owner = os.stat_result(
        (stat.S_IFREG | 0o600, 1, 1, 1, os.geteuid() + 1, 0, 1, 0, 0, 0)
    )
    wrong_directory_owner = os.stat_result(
        (stat.S_IFDIR | 0o700, 1, 1, 1, os.geteuid() + 1, 0, 0, 0, 0, 0)
    )
    assert credentials._private_file(unsafe) is False
    assert credentials._private_file(wrong_owner) is False
    assert credentials._private_directory(wrong_directory_owner) is False


def test_check_never_opens_secret_file_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ready_store(tmp_path)
    original_open: Callable[..., int] = os.open

    def guarded_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if os.fspath(path) in credentials.SECRET_ALIASES:
            raise AssertionError("secret content open attempted")
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", guarded_open)
    assert _inspect(tmp_path) is credentials.CredentialStoreStatus.READY


@pytest.mark.parametrize(
    "mutation",
    [
        "partial",
        "extra",
        "wrong_file_mode",
        "wrong_store_mode",
        "symlink_file",
        "hardlink_pair",
        "fifo",
        "directory_leaf",
        "empty",
        "newline_only",
        "oversized",
    ],
)
def test_check_rejects_partial_unknown_link_special_and_unsafe_metadata(
    tmp_path: Path, mutation: str
) -> None:
    store = _ready_store(tmp_path)
    application = store / credentials.APPLICATION_ID_ALIAS
    access = store / credentials.ACCESS_KEY_ALIAS
    if mutation == "partial":
        access.unlink()
    elif mutation == "extra":
        _private_file(store / "unexpected")
    elif mutation == "wrong_file_mode":
        application.chmod(0o644)
    elif mutation == "wrong_store_mode":
        store.chmod(0o755)
    elif mutation == "symlink_file":
        application.unlink()
        application.symlink_to(access.name)
    elif mutation == "hardlink_pair":
        access.unlink()
        os.link(application, access)
    elif mutation == "fifo":
        application.unlink()
        os.mkfifo(application, 0o600)
    elif mutation == "directory_leaf":
        application.unlink()
        application.mkdir(mode=0o700)
    elif mutation == "empty":
        application.write_bytes(b"")
    elif mutation == "newline_only":
        application.write_bytes(b"\n")
    else:
        application.write_bytes(b"x" * (credentials.MAX_SECRET_BYTES + 2))
    with pytest.raises(credentials.CredentialIntakeFailure) as caught:
        _inspect(tmp_path)
    assert caught.value.code is credentials.CredentialIntakeFailureCode.STORE_INVALID


def test_repository_or_secret_parent_symlink_is_rejected(tmp_path: Path) -> None:
    physical = tmp_path / "physical"
    physical.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(physical, target_is_directory=True)
    with pytest.raises(credentials.CredentialIntakeFailure):
        credentials.inspect_store(linked, expected_root=linked)

    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir(mode=0o700)
    (root / credentials.SECRET_PARENT_NAME).symlink_to(
        outside, target_is_directory=True
    )
    with pytest.raises(credentials.CredentialIntakeFailure):
        _inspect(root)


def test_setup_reads_both_values_before_first_durable_write_and_wipes_buffers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    values = [bytearray(b"one"), bytearray(b"two")]

    def guard() -> None:
        events.append("guard")

    def reader(_prompt: str) -> bytearray:
        events.append("read")
        return values[len([event for event in events if event == "read"]) - 1]

    def create(root: Path, received: tuple[bytearray, bytearray]) -> None:
        assert root == tmp_path
        assert received == tuple(values)
        events.append("write")

    monkeypatch.setattr(credentials, "_create_pair", create)
    assert (
        credentials.setup_store(
            tmp_path,
            expected_root=tmp_path,
            reader=reader,
            disclosure_guard=guard,
        )
        is credentials.CredentialStoreStatus.READY
    )
    assert events == ["guard", "read", "read", "write"]
    assert values == [bytearray(3), bytearray(3)]


def test_setup_ready_is_metadata_only_and_never_prompts_or_changes_dumpability(
    tmp_path: Path,
) -> None:
    _ready_store(tmp_path)

    def forbidden(*_args: object, **_kwargs: object) -> Any:
        raise AssertionError("READY setup attempted an input or process-state change")

    assert (
        credentials.setup_store(
            tmp_path,
            expected_root=tmp_path,
            reader=forbidden,
            disclosure_guard=forbidden,
        )
        is credentials.CredentialStoreStatus.READY
    )


def test_partial_store_fails_before_prompt(tmp_path: Path) -> None:
    store = _ready_store(tmp_path)
    (store / credentials.ACCESS_KEY_ALIAS).unlink()
    called = False

    def forbidden(_prompt: str) -> bytearray:
        nonlocal called
        called = True
        return bytearray(b"not-used")

    with pytest.raises(credentials.CredentialIntakeFailure):
        credentials.setup_store(
            tmp_path,
            expected_root=tmp_path,
            reader=forbidden,
            disclosure_guard=lambda: None,
        )
    assert called is False


def test_setup_creates_exact_private_pair_and_never_overwrites(tmp_path: Path) -> None:
    supplied = iter((bytearray(b"one"), bytearray(b"two")))
    assert (
        credentials.setup_store(
            tmp_path,
            expected_root=tmp_path,
            reader=lambda _prompt: next(supplied),
            disclosure_guard=lambda: None,
        )
        is credentials.CredentialStoreStatus.READY
    )
    parent = tmp_path / credentials.SECRET_PARENT_NAME
    store = parent / credentials.SECRET_STORE_NAME
    ready = parent / credentials.SECRET_READY_NAME
    committed = parent / credentials.SECRET_COMMITTED_NAME
    assert stat.S_IMODE(parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(store.stat().st_mode) == 0o700
    assert stat.S_IMODE(ready.stat().st_mode) == 0o700
    assert stat.S_IMODE(committed.stat().st_mode) == 0o700
    assert not tuple(ready.iterdir())
    assert not tuple(committed.iterdir())
    assert not (parent / credentials.SECRET_STAGING_NAME).exists()
    assert not (parent / credentials.SECRET_COMMITTING_NAME).exists()
    assert not (parent / credentials.SECRET_VALIDATING_NAME).exists()
    assert tuple(sorted(item.name for item in store.iterdir())) == tuple(
        sorted(credentials.SECRET_ALIASES)
    )
    before = {
        alias: (store / alias).read_bytes() for alias in credentials.SECRET_ALIASES
    }
    for alias in credentials.SECRET_ALIASES:
        metadata = (store / alias).stat()
        assert stat.S_ISREG(metadata.st_mode)
        assert stat.S_IMODE(metadata.st_mode) == 0o600
        assert metadata.st_uid == os.geteuid()
        assert metadata.st_nlink == 1
    assert (
        credentials.setup_store(
            tmp_path,
            expected_root=tmp_path,
            reader=lambda _prompt: pytest.fail("existing pair prompted"),
            disclosure_guard=lambda: pytest.fail("existing pair changed dumpability"),
        )
        is credentials.CredentialStoreStatus.READY
    )
    assert {
        alias: (store / alias).read_bytes() for alias in credentials.SECRET_ALIASES
    } == before


@pytest.mark.parametrize("fail_at", (1, 2))
def test_pair_write_failure_leaves_fail_closed_residue_without_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail_at: int
) -> None:
    original_write = credentials._write_secret
    calls = 0

    def fail_write(store_fd: int, name: str, value: bytearray) -> None:
        nonlocal calls
        calls += 1
        if calls == fail_at:
            raise credentials.CredentialIntakeFailure(
                credentials.CredentialIntakeFailureCode.WRITE_FAILED
            )
        original_write(store_fd, name, value)

    monkeypatch.setattr(credentials, "_write_secret", fail_write)
    monkeypatch.setattr(
        os,
        "unlink",
        lambda *_args, **_kwargs: pytest.fail("automatic file rollback attempted"),
    )
    monkeypatch.setattr(
        os,
        "rmdir",
        lambda *_args, **_kwargs: pytest.fail("automatic directory rollback attempted"),
    )
    values = iter((bytearray(b"first"), bytearray(b"second")))
    with pytest.raises(credentials.CredentialIntakeFailure):
        credentials.setup_store(
            tmp_path,
            expected_root=tmp_path,
            reader=lambda _prompt: next(values),
            disclosure_guard=lambda: None,
        )
    store = tmp_path / credentials.SECRET_PARENT_NAME / credentials.SECRET_STAGING_NAME
    assert store.is_dir()
    assert tuple(sorted(path.name for path in store.iterdir())) == (
        () if fail_at == 1 else (credentials.APPLICATION_ID_ALIAS,)
    )
    with pytest.raises(credentials.CredentialIntakeFailure):
        _inspect(tmp_path)


def test_write_system_failure_leaves_owner_only_fail_closed_residue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        os,
        "write",
        lambda _fd, _value: (_ for _ in ()).throw(OSError("write failed")),
    )
    values = iter((bytearray(b"one"), bytearray(b"two")))
    with pytest.raises(credentials.CredentialIntakeFailure):
        credentials.setup_store(
            tmp_path,
            expected_root=tmp_path,
            reader=lambda _prompt: next(values),
            disclosure_guard=lambda: None,
        )
    parent = tmp_path / credentials.SECRET_PARENT_NAME
    store = parent / credentials.SECRET_STAGING_NAME
    assert stat.S_IMODE(parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(store.stat().st_mode) == 0o700
    residue = store / credentials.APPLICATION_ID_ALIAS
    assert residue.is_file()
    assert stat.S_IMODE(residue.stat().st_mode) == 0o600
    with pytest.raises(credentials.CredentialIntakeFailure):
        _inspect(tmp_path)


def test_partial_second_value_write_never_publishes_ready_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_write = os.write
    regular_writes = 0

    def partial_second(fd: int, value: bytes | memoryview) -> int:
        nonlocal regular_writes
        if stat.S_ISREG(os.fstat(fd).st_mode):
            regular_writes += 1
            if regular_writes == 3:
                assert original_write(fd, bytes(value)[:2]) == 2
                raise OSError("partial write failure")
        return original_write(fd, value)

    monkeypatch.setattr(os, "write", partial_second)
    values = iter((bytearray(b"first"), bytearray(b"second")))
    with pytest.raises(credentials.CredentialIntakeFailure):
        credentials.setup_store(
            tmp_path,
            expected_root=tmp_path,
            reader=lambda _prompt: next(values),
            disclosure_guard=lambda: None,
        )
    parent = tmp_path / credentials.SECRET_PARENT_NAME
    staging = parent / credentials.SECRET_STAGING_NAME
    assert not (parent / credentials.SECRET_STORE_NAME).exists()
    assert (staging / credentials.ACCESS_KEY_ALIAS).stat().st_size == 2
    with pytest.raises(credentials.CredentialIntakeFailure):
        _inspect(tmp_path)


def test_newline_write_failure_never_publishes_ready_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_write = os.write

    def fail_newline(fd: int, value: bytes | memoryview) -> int:
        if bytes(value) == b"\n":
            raise OSError("newline write failure")
        return original_write(fd, value)

    monkeypatch.setattr(os, "write", fail_newline)
    values = iter((bytearray(b"first"), bytearray(b"second")))
    with pytest.raises(credentials.CredentialIntakeFailure):
        credentials.setup_store(
            tmp_path,
            expected_root=tmp_path,
            reader=lambda _prompt: next(values),
            disclosure_guard=lambda: None,
        )
    parent = tmp_path / credentials.SECRET_PARENT_NAME
    assert not (parent / credentials.SECRET_STORE_NAME).exists()
    assert (parent / credentials.SECRET_STAGING_NAME).is_dir()
    with pytest.raises(credentials.CredentialIntakeFailure):
        _inspect(tmp_path)


@pytest.mark.parametrize("failure", ("file_fsync", "stage_fsync"))
def test_prepublish_fsync_failure_never_publishes_ready_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    original_fsync = os.fsync

    def fail_selected(descriptor: int) -> None:
        metadata = os.fstat(descriptor)
        path = Path(os.readlink(f"/proc/self/fd/{descriptor}"))
        if failure == "file_fsync" and stat.S_ISREG(metadata.st_mode):
            raise OSError("file fsync failure")
        if (
            failure == "stage_fsync"
            and stat.S_ISDIR(metadata.st_mode)
            and path.name == credentials.SECRET_STAGING_NAME
        ):
            raise OSError("stage fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_selected)
    values = iter((bytearray(b"first"), bytearray(b"second")))
    with pytest.raises(credentials.CredentialIntakeFailure):
        credentials.setup_store(
            tmp_path,
            expected_root=tmp_path,
            reader=lambda _prompt: next(values),
            disclosure_guard=lambda: None,
        )
    parent = tmp_path / credentials.SECRET_PARENT_NAME
    assert not (parent / credentials.SECRET_STORE_NAME).exists()
    assert (parent / credentials.SECRET_STAGING_NAME).is_dir()
    with pytest.raises(credentials.CredentialIntakeFailure):
        _inspect(tmp_path)


@pytest.mark.parametrize(
    "failure", ("store_publish", "ready_publish", "commit_publish")
)
def test_atomic_publish_failure_never_reports_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    original_rename = credentials._rename_noreplace

    def fail_selected(parent_fd: int, source: str, target: str) -> None:
        if (
            (failure == "store_publish" and source == credentials.SECRET_STAGING_NAME)
            or (
                failure == "ready_publish"
                and source == credentials.SECRET_COMMITTING_NAME
            )
            or (
                failure == "commit_publish"
                and source == credentials.SECRET_VALIDATING_NAME
            )
        ):
            raise credentials.CredentialIntakeFailure(
                credentials.CredentialIntakeFailureCode.WRITE_FAILED
            )
        original_rename(parent_fd, source, target)

    monkeypatch.setattr(credentials, "_rename_noreplace", fail_selected)
    values = iter((bytearray(b"first"), bytearray(b"second")))
    with pytest.raises(credentials.CredentialIntakeFailure):
        credentials.setup_store(
            tmp_path,
            expected_root=tmp_path,
            reader=lambda _prompt: next(values),
            disclosure_guard=lambda: None,
        )
    parent = tmp_path / credentials.SECRET_PARENT_NAME
    if failure == "store_publish":
        assert (parent / credentials.SECRET_COMMITTING_NAME).is_dir()
        assert (parent / credentials.SECRET_STAGING_NAME).is_dir()
        assert not (parent / credentials.SECRET_STORE_NAME).exists()
    elif failure == "ready_publish":
        assert (parent / credentials.SECRET_COMMITTING_NAME).is_dir()
        assert not (parent / credentials.SECRET_STAGING_NAME).exists()
        assert (parent / credentials.SECRET_STORE_NAME).is_dir()
    else:
        assert not (parent / credentials.SECRET_COMMITTING_NAME).exists()
        assert (parent / credentials.SECRET_READY_NAME).is_dir()
        assert (parent / credentials.SECRET_STORE_NAME).is_dir()
    assert (parent / credentials.SECRET_VALIDATING_NAME).is_dir()
    with pytest.raises(credentials.CredentialIntakeFailure):
        _inspect(tmp_path)


def test_post_publish_parent_fsync_failure_keeps_committing_state_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_fsync = os.fsync
    original_rename = credentials._rename_noreplace
    published = False

    def track_publish(parent_fd: int, source: str, target: str) -> None:
        nonlocal published
        original_rename(parent_fd, source, target)
        if source == credentials.SECRET_STAGING_NAME:
            published = True

    def fail_after_publish(descriptor: int) -> None:
        path = Path(os.readlink(f"/proc/self/fd/{descriptor}"))
        if published and path.name == credentials.SECRET_PARENT_NAME:
            raise OSError("post-publish parent fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(credentials, "_rename_noreplace", track_publish)
    monkeypatch.setattr(os, "fsync", fail_after_publish)
    values = iter((bytearray(b"first"), bytearray(b"second")))
    with pytest.raises(credentials.CredentialIntakeFailure):
        credentials.setup_store(
            tmp_path,
            expected_root=tmp_path,
            reader=lambda _prompt: next(values),
            disclosure_guard=lambda: None,
        )
    parent = tmp_path / credentials.SECRET_PARENT_NAME
    assert (parent / credentials.SECRET_STORE_NAME).is_dir()
    assert (parent / credentials.SECRET_COMMITTING_NAME).is_dir()
    assert (parent / credentials.SECRET_VALIDATING_NAME).is_dir()
    assert not (parent / credentials.SECRET_READY_NAME).exists()
    with pytest.raises(credentials.CredentialIntakeFailure):
        _inspect(tmp_path)


def test_final_parent_fsync_failure_leaves_validating_marker_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_fsync = os.fsync
    original_rename = credentials._rename_noreplace
    ready_published = False

    def track_ready(parent_fd: int, source: str, target: str) -> None:
        nonlocal ready_published
        original_rename(parent_fd, source, target)
        if source == credentials.SECRET_COMMITTING_NAME:
            ready_published = True

    def fail_after_ready(descriptor: int) -> None:
        path = Path(os.readlink(f"/proc/self/fd/{descriptor}"))
        if ready_published and path.name == credentials.SECRET_PARENT_NAME:
            raise OSError("final parent fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(credentials, "_rename_noreplace", track_ready)
    monkeypatch.setattr(os, "fsync", fail_after_ready)
    values = iter((bytearray(b"first"), bytearray(b"second")))
    with pytest.raises(credentials.CredentialIntakeFailure):
        credentials.setup_store(
            tmp_path,
            expected_root=tmp_path,
            reader=lambda _prompt: next(values),
            disclosure_guard=lambda: None,
        )
    parent = tmp_path / credentials.SECRET_PARENT_NAME
    assert (parent / credentials.SECRET_STORE_NAME).is_dir()
    assert not (parent / credentials.SECRET_COMMITTING_NAME).exists()
    assert (parent / credentials.SECRET_READY_NAME).is_dir()
    assert (parent / credentials.SECRET_VALIDATING_NAME).is_dir()
    with pytest.raises(credentials.CredentialIntakeFailure):
        _inspect(tmp_path)


def test_ready_marker_replacement_is_preserved_and_store_stays_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_rename = credentials._rename_noreplace

    def replace_ready(parent_fd: int, source: str, target: str) -> None:
        original_rename(parent_fd, source, target)
        if source == credentials.SECRET_COMMITTING_NAME:
            os.rename(
                credentials.SECRET_READY_NAME,
                "preserved-ready-marker",
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            os.mkdir(credentials.SECRET_READY_NAME, 0o700, dir_fd=parent_fd)

    monkeypatch.setattr(credentials, "_rename_noreplace", replace_ready)
    values = iter((bytearray(b"first"), bytearray(b"second")))
    with pytest.raises(credentials.CredentialIntakeFailure):
        credentials.setup_store(
            tmp_path,
            expected_root=tmp_path,
            reader=lambda _prompt: next(values),
            disclosure_guard=lambda: None,
        )
    parent = tmp_path / credentials.SECRET_PARENT_NAME
    assert (parent / "preserved-ready-marker").is_dir()
    assert not (parent / credentials.SECRET_COMMITTING_NAME).exists()
    assert (parent / credentials.SECRET_READY_NAME).is_dir()
    assert (parent / credentials.SECRET_VALIDATING_NAME).is_dir()
    with pytest.raises(credentials.CredentialIntakeFailure):
        _inspect(tmp_path)


def test_postpublish_metadata_verification_failure_leaves_validating_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_inspect = credentials._inspect_store_state
    calls = 0

    def fail_second_inspection(
        repository_root: Path,
        *,
        expected_root: Path,
        allow_validating: bool,
    ) -> credentials.CredentialStoreStatus:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise credentials.CredentialIntakeFailure(
                credentials.CredentialIntakeFailureCode.STORE_INVALID
            )
        return original_inspect(
            repository_root,
            expected_root=expected_root,
            allow_validating=allow_validating,
        )

    monkeypatch.setattr(credentials, "_inspect_store_state", fail_second_inspection)
    values = iter((bytearray(b"first"), bytearray(b"second")))
    with pytest.raises(credentials.CredentialIntakeFailure):
        credentials.setup_store(
            tmp_path,
            expected_root=tmp_path,
            reader=lambda _prompt: next(values),
            disclosure_guard=lambda: None,
        )
    parent = tmp_path / credentials.SECRET_PARENT_NAME
    assert (parent / credentials.SECRET_STORE_NAME).is_dir()
    assert not (parent / credentials.SECRET_COMMITTING_NAME).exists()
    assert (parent / credentials.SECRET_READY_NAME).is_dir()
    assert (parent / credentials.SECRET_VALIDATING_NAME).is_dir()
    with pytest.raises(credentials.CredentialIntakeFailure):
        credentials.inspect_store(tmp_path, expected_root=tmp_path)


def test_final_store_race_is_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_rename = credentials._rename_noreplace

    def race_final(parent_fd: int, source: str, target: str) -> None:
        if source == credentials.SECRET_STAGING_NAME:
            os.mkdir(credentials.SECRET_STORE_NAME, 0o700, dir_fd=parent_fd)
        original_rename(parent_fd, source, target)

    monkeypatch.setattr(credentials, "_rename_noreplace", race_final)
    values = iter((bytearray(b"first"), bytearray(b"second")))
    with pytest.raises(credentials.CredentialIntakeFailure):
        credentials.setup_store(
            tmp_path,
            expected_root=tmp_path,
            reader=lambda _prompt: next(values),
            disclosure_guard=lambda: None,
        )
    parent = tmp_path / credentials.SECRET_PARENT_NAME
    assert not tuple((parent / credentials.SECRET_STORE_NAME).iterdir())
    assert (parent / credentials.SECRET_STAGING_NAME).is_dir()
    assert (parent / credentials.SECRET_VALIDATING_NAME).is_dir()
    with pytest.raises(credentials.CredentialIntakeFailure):
        _inspect(tmp_path)


@pytest.mark.parametrize("rename_result", ("unavailable", "nonzero"))
def test_rename_noreplace_unavailable_or_nonzero_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rename_result: str
) -> None:
    class FakeRename:
        restype: object = None
        argtypes: object = None

        def __call__(self, *_args: object) -> int:
            return -1

    class MissingLibc:
        pass

    class FailingLibc:
        renameat2 = FakeRename()

    library: object = MissingLibc() if rename_result == "unavailable" else FailingLibc()
    monkeypatch.setattr(ctypes, "CDLL", lambda *_args, **_kwargs: library)
    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(credentials.CredentialIntakeFailure) as caught:
            credentials._rename_noreplace(
                parent_fd,
                credentials.SECRET_STAGING_NAME,
                credentials.SECRET_STORE_NAME,
            )
    finally:
        os.close(parent_fd)
    assert caught.value.code is credentials.CredentialIntakeFailureCode.WRITE_FAILED


def test_failure_never_deletes_inode_replaced_after_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_write = credentials._write_secret
    calls = 0

    def replace_then_fail(store_fd: int, name: str, value: bytearray) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            original_write(store_fd, name, value)
            return
        os.rename(
            credentials.APPLICATION_ID_ALIAS,
            "preserved-created-inode",
            src_dir_fd=store_fd,
            dst_dir_fd=store_fd,
        )
        replacement_fd = os.open(
            credentials.APPLICATION_ID_ALIAS,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=store_fd,
        )
        os.write(replacement_fd, b"replacement\n")
        os.close(replacement_fd)
        raise credentials.CredentialIntakeFailure(
            credentials.CredentialIntakeFailureCode.WRITE_FAILED
        )

    monkeypatch.setattr(credentials, "_write_secret", replace_then_fail)
    values = iter((bytearray(b"first"), bytearray(b"second")))
    with pytest.raises(credentials.CredentialIntakeFailure):
        credentials.setup_store(
            tmp_path,
            expected_root=tmp_path,
            reader=lambda _prompt: next(values),
            disclosure_guard=lambda: None,
        )
    replacement = (
        tmp_path
        / credentials.SECRET_PARENT_NAME
        / credentials.SECRET_STAGING_NAME
        / credentials.APPLICATION_ID_ALIAS
    )
    assert replacement.read_bytes() == b"replacement\n"
    preserved = replacement.parent / "preserved-created-inode"
    assert preserved.read_bytes() == b"first\n"
    with pytest.raises(credentials.CredentialIntakeFailure):
        _inspect(tmp_path)


def test_hidden_tty_uses_direct_device_cloexec_and_restores_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    descriptor = 91
    opened: list[tuple[object, int]] = []
    writes: list[bytes] = []
    terminal_states: list[list[Any]] = []
    input_bytes = iter((b"v", b"a", b"l", b"u", b"e", b"\n"))
    original = [0, 0, 0, termios_flags(), 0, 0, []]

    def fake_open(path: object, flags: int) -> int:
        opened.append((path, flags))
        return descriptor

    def fake_write(_fd: int, value: bytes | memoryview) -> int:
        writes.append(bytes(value))
        return len(value)

    monkeypatch.setattr(os, "open", fake_open)
    monkeypatch.setattr(os, "set_inheritable", lambda _fd, _value: None)
    monkeypatch.setattr(os, "get_inheritable", lambda _fd: False)
    monkeypatch.setattr(os, "fstat", lambda _fd: _char_stat())
    monkeypatch.setattr(os, "read", lambda _fd, _size: next(input_bytes))
    monkeypatch.setattr(os, "write", fake_write)
    monkeypatch.setattr(os, "close", lambda _fd: None)
    monkeypatch.setattr(termios, "tcgetattr", lambda _fd: original.copy())
    monkeypatch.setattr(
        termios,
        "tcsetattr",
        lambda _fd, _when, state: terminal_states.append(state.copy()),
    )
    value = credentials._read_private_tty("ASCII prompt: ")
    assert value == bytearray(b"value")
    assert opened == [("/dev/tty", credentials._TTY_FLAGS)]
    assert credentials._TTY_FLAGS & getattr(os, "O_CLOEXEC", 0)
    assert credentials._TTY_FLAGS & getattr(os, "O_NOFOLLOW", 0)
    assert terminal_states[0][3] & termios.ECHO == 0
    assert terminal_states[0][3] & getattr(termios, "ECHONL", 0) == 0
    assert terminal_states[-1] == original
    assert b"".join(writes) == b"ASCII prompt: \n"


def termios_flags() -> int:
    return int(termios.ECHO) | int(getattr(termios, "ECHONL", 0))


def _char_stat() -> os.stat_result:
    return os.stat_result((stat.S_IFCHR | 0o600, 0, 0, 1, os.geteuid(), 0, 0, 0, 0, 0))


def test_hidden_tty_restores_terminal_on_input_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    restored: list[list[Any]] = []
    original = [0, 0, 0, termios_flags(), 0, 0, []]
    monkeypatch.setattr(os, "open", lambda _path, _flags: 92)
    monkeypatch.setattr(os, "set_inheritable", lambda _fd, _value: None)
    monkeypatch.setattr(os, "get_inheritable", lambda _fd: False)
    monkeypatch.setattr(os, "fstat", lambda _fd: _char_stat())
    monkeypatch.setattr(os, "read", lambda _fd, _size: b"")
    monkeypatch.setattr(os, "write", lambda _fd, value: len(value))
    monkeypatch.setattr(os, "close", lambda _fd: None)
    monkeypatch.setattr(termios, "tcgetattr", lambda _fd: original.copy())
    monkeypatch.setattr(
        termios,
        "tcsetattr",
        lambda _fd, _when, state: restored.append(state.copy()),
    )
    with pytest.raises(credentials.CredentialIntakeFailure):
        credentials._read_private_tty("ASCII prompt: ")
    assert restored[-1] == original


def test_hidden_tty_wipes_partial_value_and_fails_if_restore_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = [0, 0, 0, termios_flags(), 0, 0, []]
    input_bytes = iter((b"p", b"a", b"r", b"t", b"\n"))
    set_calls = 0
    wiped: list[tuple[bytes, bytes]] = []
    original_wipe = credentials._wipe

    def set_terminal(_fd: int, _when: int, _state: list[Any]) -> None:
        nonlocal set_calls
        set_calls += 1
        if set_calls == 2:
            raise OSError("restore failed")

    def record_wipe(value: bytearray | None) -> None:
        before = bytes(value or b"")
        original_wipe(value)
        after = bytes(value or b"")
        wiped.append((before, after))

    monkeypatch.setattr(os, "open", lambda _path, _flags: 93)
    monkeypatch.setattr(os, "set_inheritable", lambda _fd, _value: None)
    monkeypatch.setattr(os, "get_inheritable", lambda _fd: False)
    monkeypatch.setattr(os, "fstat", lambda _fd: _char_stat())
    monkeypatch.setattr(os, "read", lambda _fd, _size: next(input_bytes))
    monkeypatch.setattr(os, "write", lambda _fd, value: len(value))
    monkeypatch.setattr(os, "close", lambda _fd: None)
    monkeypatch.setattr(termios, "tcgetattr", lambda _fd: original.copy())
    monkeypatch.setattr(termios, "tcsetattr", set_terminal)
    monkeypatch.setattr(credentials, "_wipe", record_wipe)
    with pytest.raises(credentials.CredentialIntakeFailure) as caught:
        credentials._read_private_tty("ASCII prompt: ")
    assert (
        caught.value.code is credentials.CredentialIntakeFailureCode.INPUT_UNAVAILABLE
    )
    assert wiped == [(b"part", b"\x00\x00\x00\x00")]


def test_hidden_tty_wipes_partial_value_on_input_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = [0, 0, 0, termios_flags(), 0, 0, []]
    input_bytes = iter((b"p", b"a", b"r", b"t", b""))
    wiped: list[tuple[bytes, bytes]] = []
    original_wipe = credentials._wipe

    def record_wipe(value: bytearray | None) -> None:
        before = bytes(value or b"")
        original_wipe(value)
        after = bytes(value or b"")
        wiped.append((before, after))

    monkeypatch.setattr(os, "open", lambda _path, _flags: 94)
    monkeypatch.setattr(os, "set_inheritable", lambda _fd, _value: None)
    monkeypatch.setattr(os, "get_inheritable", lambda _fd: False)
    monkeypatch.setattr(os, "fstat", lambda _fd: _char_stat())
    monkeypatch.setattr(os, "read", lambda _fd, _size: next(input_bytes))
    monkeypatch.setattr(os, "write", lambda _fd, value: len(value))
    monkeypatch.setattr(os, "close", lambda _fd: None)
    monkeypatch.setattr(termios, "tcgetattr", lambda _fd: original.copy())
    monkeypatch.setattr(termios, "tcsetattr", lambda _fd, _when, _state: None)
    monkeypatch.setattr(credentials, "_wipe", record_wipe)
    with pytest.raises(credentials.CredentialIntakeFailure):
        credentials._read_private_tty("ASCII prompt: ")
    assert wiped == [(b"part", b"\x00\x00\x00\x00")]


@pytest.mark.parametrize("control", (b"\x00", b"\t", b"\n", b"\r", b"\x1f", b"\x7f"))
def test_read_value_rejects_controls_and_wipes_mutable_input(control: bytes) -> None:
    value = bytearray(b"opaque" + control + b"value")
    with pytest.raises(credentials.CredentialIntakeFailure) as caught:
        credentials._read_value(lambda _prompt: value, "ASCII prompt: ")
    assert (
        caught.value.code is credentials.CredentialIntakeFailureCode.INPUT_UNAVAILABLE
    )
    assert value == bytearray(len(value))


def test_read_value_preserves_non_control_opaque_bytes() -> None:
    value = bytearray(b"opaque-\x80-value")
    assert credentials._read_value(lambda _prompt: value, "ASCII prompt: ") is value


def test_process_disclosure_guard_requires_core_and_prctl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int]] = []

    class FakePrctl:
        restype: object = None
        argtypes: object = None

        def __call__(self, option: int, value: int, _a: int, _b: int, _c: int) -> int:
            calls.append((option, value))
            return 0

    class FakeLibc:
        prctl = FakePrctl()

    monkeypatch.setattr(resource, "setrlimit", lambda _which, _value: None)
    monkeypatch.setattr(resource, "getrlimit", lambda _which: (0, 0))
    monkeypatch.setattr(ctypes, "CDLL", lambda *_args, **_kwargs: FakeLibc())
    credentials._disable_process_disclosure()
    assert calls == [
        (credentials._PR_SET_DUMPABLE, 0),
        (credentials._PR_GET_DUMPABLE, 0),
    ]


def test_process_disclosure_guard_fails_closed_when_prctl_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resource, "setrlimit", lambda _which, _value: None)
    monkeypatch.setattr(resource, "getrlimit", lambda _which: (0, 0))
    monkeypatch.setattr(
        ctypes,
        "CDLL",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("unavailable")),
    )
    with pytest.raises(credentials.CredentialIntakeFailure) as caught:
        credentials._disable_process_disclosure()
    assert caught.value.code is credentials.CredentialIntakeFailureCode.PLATFORM_UNSAFE


def test_cli_receipts_are_fixed_sanitized_and_never_echo_exception_or_value(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    canary = "redaction-canary"

    def failed_reader(_prompt: str) -> bytearray:
        raise RuntimeError(canary)

    assert (
        credentials.main(
            ["setup"],
            repository_root=tmp_path,
            expected_root=tmp_path,
            reader=failed_reader,
            disclosure_guard=lambda: None,
        )
        == 1
    )
    output = capsys.readouterr()
    assert output.err == ""
    assert canary not in output.out
    assert json.loads(output.out) == {
        "command": "setup",
        "ok": False,
        "reason_code": "RAKUTEN_CREDENTIAL_INPUT_UNAVAILABLE",
        "status": "INVALID",
    }
    assert (
        credentials.main(["check"], repository_root=tmp_path, expected_root=tmp_path)
        == 0
    )
    assert json.loads(capsys.readouterr().out) == {
        "command": "check",
        "ok": True,
        "status": "ABSENT",
    }


@pytest.mark.parametrize(
    "argv", ([], ["setup", "extra"], ["--root", "/tmp"], ["SETUP"])
)
def test_cli_rejects_missing_extra_root_and_wrong_case_arguments(
    argv: list[str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert credentials.main(argv, repository_root=tmp_path, expected_root=tmp_path) == 1
    assert json.loads(capsys.readouterr().out) == {
        "command": "invalid",
        "ok": False,
        "reason_code": "RAKUTEN_CREDENTIAL_ARGUMENT_INVALID",
        "status": "INVALID",
    }


def test_launcher_never_executes_site_package_pth_startup_hooks(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    scripts = repository_root / "scripts"
    venv_root = repository_root / ".venv"
    venv_bin = venv_root / "bin"
    site_packages = venv_root / "lib/python3.14/site-packages"
    scripts.mkdir(parents=True)
    venv_bin.mkdir(parents=True)
    site_packages.mkdir(parents=True)

    source_launcher = (
        Path(__file__).resolve().parents[2]
        / "scripts/rakuten_live_smoke_credentials_python.sh"
    )
    launcher_source = source_launcher.read_text(encoding="utf-8")
    assert launcher_source.count("expected_repository_root=/home/minami/rakuten") == 1
    assert (
        launcher_source.count(
            "expected_base=/home/minami/.local/share/uv/python/"
            "cpython-3.14.6-linux-x86_64-gnu"
        )
        == 1
    )
    launcher_source = launcher_source.replace(
        "expected_repository_root=/home/minami/rakuten",
        f"expected_repository_root={shlex.quote(os.fspath(repository_root))}",
    ).replace(
        "expected_base=/home/minami/.local/share/uv/python/"
        "cpython-3.14.6-linux-x86_64-gnu",
        f"expected_base={shlex.quote(sys.base_prefix)}",
    )
    launcher = scripts / "rakuten_live_smoke_credentials_python.sh"
    launcher.write_text(launcher_source, encoding="utf-8")
    launcher.chmod(0o755)

    expected_python = Path(sys.base_prefix) / "bin/python3.14"
    assert sys.version_info[:3] == (3, 14, 6)
    assert expected_python.is_file()
    (venv_bin / "python").symlink_to(expected_python)
    (venv_root / "pyvenv.cfg").write_text(
        f"home = {Path(sys.base_prefix) / 'bin'}\n"
        "implementation = CPython\n"
        "uv = 0.12.1\n"
        "version_info = 3.14.6\n"
        "include-system-site-packages = false\n"
        "prompt = raos\n",
        encoding="utf-8",
    )

    canary = tmp_path / "executable-pth-hook-ran"
    (site_packages / "hostile-startup.pth").write_text(
        "import pathlib; "
        f"pathlib.Path({str(canary)!r}).write_text('ran', encoding='utf-8')\n",
        encoding="utf-8",
    )
    positive_control = subprocess.run(
        [os.fspath(venv_bin / "python"), "-I", "-c", "pass"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert positive_control.returncode == 0
    assert positive_control.stdout == ""
    assert positive_control.stderr == ""
    assert canary.read_text(encoding="utf-8") == "ran"
    canary.unlink()

    source_credential_script = (
        Path(__file__).resolve().parents[2]
        / "scripts/rakuten_live_smoke_credentials.py"
    ).read_text(encoding="utf-8")
    assert (
        source_credential_script.count(
            'EXPECTED_REPOSITORY_ROOT: Final = Path("/home/minami/rakuten")'
        )
        == 1
    )
    (scripts / "rakuten_live_smoke_credentials.py").write_text(
        source_credential_script.replace(
            'EXPECTED_REPOSITORY_ROOT: Final = Path("/home/minami/rakuten")',
            f'EXPECTED_REPOSITORY_ROOT: Final = Path("{repository_root}")',
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [os.fspath(launcher), "check"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0
    assert completed.stdout == '{"command":"check","ok":true,"status":"ABSENT"}\n'
    assert completed.stderr == ""
    assert not canary.exists()


def test_launcher_is_fixed_pinned_sanitized_and_argument_closed() -> None:
    launcher = (
        credentials.EXPECTED_REPOSITORY_ROOT
        / "scripts/rakuten_live_smoke_credentials_python.sh"
    )
    if not launcher.exists():
        launcher = (
            Path(__file__).resolve().parents[2]
            / "scripts/rakuten_live_smoke_credentials_python.sh"
        )
    source = launcher.read_text(encoding="utf-8")
    assert stat.S_IMODE(launcher.stat().st_mode) == 0o755
    assert source.startswith("#!/bin/bash -p\n")
    assert "expected_repository_root=/home/minami/rakuten" in source
    assert "version_info = 3.14.6" in source
    assert "and sys.flags.no_site == 1" in source
    assert "if [[ $# -ne 1 || ( $1 != setup && $1 != check ) ]]" in source
    assert 'if ! "$venv_python" -I -S - "$repository_root"' in source
    assert (
        'exec "$venv_python" -I -S '
        '"$repository_root/scripts/rakuten_live_smoke_credentials.py" "$1"' in source
    )
    assert '"$1"' in source
    for name in (
        "PYTHONPATH",
        "RAKUTEN_WEB_SERVICE_APPLICATION_ID",
        "RAKUTEN_WEB_SERVICE_ACCESS_KEY",
        "RAKUTEN_AFFILIATE_ID",
        "HTTPS_PROXY",
        "SSLKEYLOGFILE",
        "LD_PRELOAD",
    ):
        assert "unset " in source and name in source
    assert "curl" not in source
    assert "wget" not in source


def test_python_module_has_no_network_subprocess_environment_or_runtime_reader() -> (
    None
):
    source = Path(credentials.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name.partition(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").partition(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert imports.isdisjoint(
        {"http", "httpx", "requests", "socket", "subprocess", "urllib"}
    )
    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert {"environ", "getenv", "system", "popen"}.isdisjoint(attributes | names)
    assert "endpoint" not in source.lower()
    assert "affiliate_id" not in source.lower()
    assert "runtime_credential" not in source.lower()

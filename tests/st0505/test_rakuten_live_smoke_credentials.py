"""Hostile local-only credential-intake tests for ST-0505."""

from __future__ import annotations

import ast
import ctypes
import hashlib
import json
import os
from pathlib import Path
import pty
import resource
import select
import shlex
import shutil
import signal
import stat
import struct
import subprocess
import sys
import termios
import tempfile
import time
from typing import Any, Callable, Iterator, NamedTuple, cast

import pytest

from scripts import rakuten_live_smoke_credentials as credentials


_RUNTIME_RELATIVE_FILES = (
    "lib/python3.14/__future__.py",
    "lib/python3.14/_weakrefset.py",
    "lib/python3.14/collections/__init__.py",
    "lib/python3.14/contextlib.py",
    "lib/python3.14/copyreg.py",
    "lib/python3.14/ctypes/__init__.py",
    "lib/python3.14/ctypes/_endian.py",
    "lib/python3.14/encodings/__init__.py",
    "lib/python3.14/encodings/aliases.py",
    "lib/python3.14/encodings/utf_8.py",
    "lib/python3.14/encodings/utf_8_sig.py",
    "lib/python3.14/enum.py",
    "lib/python3.14/fnmatch.py",
    "lib/python3.14/functools.py",
    "lib/python3.14/glob.py",
    "lib/python3.14/json/__init__.py",
    "lib/python3.14/json/decoder.py",
    "lib/python3.14/json/encoder.py",
    "lib/python3.14/json/scanner.py",
    "lib/python3.14/keyword.py",
    "lib/python3.14/operator.py",
    "lib/python3.14/pathlib/__init__.py",
    "lib/python3.14/pathlib/_os.py",
    "lib/python3.14/re/__init__.py",
    "lib/python3.14/re/_casefix.py",
    "lib/python3.14/re/_compiler.py",
    "lib/python3.14/re/_constants.py",
    "lib/python3.14/re/_parser.py",
    "lib/python3.14/reprlib.py",
    "lib/python3.14/struct.py",
    "lib/python3.14/sysconfig/__init__.py",
    "lib/python3.14/threading.py",
    "lib/python3.14/types.py",
    "lib/python3.14/typing.py",
)


class _LauncherEnvironment(NamedTuple):
    trust_root: Path
    repository_root: Path
    scripts: Path
    launcher: Path
    credential_script: Path
    venv_root: Path
    venv_bin: Path
    pyvenv_cfg: Path
    runtime_parent: Path
    expected_base: Path
    expected_bin: Path
    expected_python: Path
    expected_lib: Path
    expected_stdlib: Path
    runtime_file: Path


@pytest.fixture(autouse=True)
def _closed_native_runtime_test_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep injected unit stores behind the same pre-resolved native boundary."""

    library = ctypes.CDLL(None, use_errno=True)
    renameat2 = library.renameat2
    renameat2.restype = ctypes.c_int
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    monkeypatch.setattr(credentials, "_RENAMEAT2", renameat2)
    monkeypatch.setattr(credentials, "_RUNTIME_LOCKED", True)


@pytest.fixture(scope="module")
def launcher_environment() -> Iterator[_LauncherEnvironment]:
    source_root = Path(__file__).resolve().parents[2]
    temporary_root = Path(tempfile.mkdtemp(prefix=".st0505-launcher-", dir=source_root))
    temporary_root.chmod(0o700)
    try:
        repository_root = temporary_root / "repository"
        scripts = repository_root / "scripts"
        venv_root = repository_root / ".venv"
        venv_bin = venv_root / "bin"
        expected_base = temporary_root / "runtime" / "cpython-3.14.6"
        expected_python = expected_base / "bin/python3.14"
        scripts.mkdir(parents=True, mode=0o755)
        venv_bin.mkdir(parents=True, mode=0o755)
        expected_python.parent.mkdir(parents=True, mode=0o755)
        expected_python.write_bytes(
            (Path(sys.base_prefix) / "bin/python3.14").read_bytes()
        )
        expected_python.chmod(0o755)

        shutil.copytree(
            Path(sys.base_prefix) / "lib/python3.14",
            expected_base / "lib/python3.14",
        )

        (venv_bin / "python").symlink_to(expected_python)
        pyvenv_cfg = venv_root / "pyvenv.cfg"
        pyvenv_cfg.write_text(
            f"home = {expected_base / 'bin'}\n"
            "implementation = CPython\n"
            "uv = 0.12.1\n"
            "version_info = 3.14.6\n"
            "include-system-site-packages = false\n"
            "prompt = raos\n",
            encoding="utf-8",
        )
        pyvenv_cfg.chmod(0o644)

        launcher_source = (
            source_root / "scripts/rakuten_live_smoke_credentials_python.sh"
        ).read_text(encoding="utf-8")
        assert (
            launcher_source.count("expected_repository_root=/home/minami/rakuten") == 1
        )
        assert (
            launcher_source.count(
                "expected_base=/home/minami/.local/share/uv/python/"
                "cpython-3.14.6-linux-x86_64-gnu"
            )
            == 1
        )
        assert launcher_source.count("expected_busybox_sha256=") == 1
        assert launcher_source.count("expected_python_sha256=") == 1
        busybox_sha256 = hashlib.sha256(
            Path("/usr/bin/busybox").read_bytes()
        ).hexdigest()
        python_sha256 = hashlib.sha256(expected_python.read_bytes()).hexdigest()
        launcher = scripts / "rakuten_live_smoke_credentials_python.sh"
        launcher.write_text(
            launcher_source.replace(
                "expected_repository_root=/home/minami/rakuten",
                f"expected_repository_root={shlex.quote(os.fspath(repository_root))}",
            )
            .replace(
                "expected_base=/home/minami/.local/share/uv/python/"
                "cpython-3.14.6-linux-x86_64-gnu",
                f"expected_base={shlex.quote(os.fspath(expected_base))}",
            )
            .replace(
                "expected_busybox_sha256="
                "b3c1009e1b5c927e537487c80639cdf404f69e3eb49371d9be5d841672be3ff9",
                f"expected_busybox_sha256={busybox_sha256}",
            )
            .replace(
                "expected_python_sha256="
                "c2afa8cc3c59d32bac482c122633a352c3910bfed85b59efd8ef49511d46bd2b",
                f"expected_python_sha256={python_sha256}",
            ),
            encoding="utf-8",
        )
        launcher.chmod(0o755)

        credential_source = (
            source_root / "scripts/rakuten_live_smoke_credentials.py"
        ).read_text(encoding="utf-8")
        assert (
            credential_source.count(
                'EXPECTED_REPOSITORY_ROOT: Final = Path("/home/minami/rakuten")'
            )
            == 1
        )
        expected_runtime_python = (
            "EXPECTED_RUNTIME_PYTHON: Final = Path(\n"
            '    "/home/minami/.local/share/uv/python/'
            'cpython-3.14.6-linux-x86_64-gnu/bin/python3.14"\n'
            ")"
        )
        assert credential_source.count(expected_runtime_python) == 1
        credential_script = scripts / "rakuten_live_smoke_credentials.py"
        credential_script.write_text(
            credential_source.replace(
                'EXPECTED_REPOSITORY_ROOT: Final = Path("/home/minami/rakuten")',
                f'EXPECTED_REPOSITORY_ROOT: Final = Path("{repository_root}")',
            ).replace(
                expected_runtime_python,
                f"EXPECTED_RUNTIME_PYTHON: Final = Path({os.fspath(expected_python)!r})",
            ),
            encoding="utf-8",
        )
        credential_script.chmod(0o644)

        yield _LauncherEnvironment(
            trust_root=temporary_root,
            repository_root=repository_root,
            scripts=scripts,
            launcher=launcher,
            credential_script=credential_script,
            venv_root=venv_root,
            venv_bin=venv_bin,
            pyvenv_cfg=pyvenv_cfg,
            runtime_parent=expected_base.parent,
            expected_base=expected_base,
            expected_bin=expected_python.parent,
            expected_python=expected_python,
            expected_lib=expected_base / "lib",
            expected_stdlib=expected_base / "lib/python3.14",
            runtime_file=expected_base / _RUNTIME_RELATIVE_FILES[-1],
        )
    finally:
        shutil.rmtree(temporary_root)


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

    monkeypatch.setattr(
        credentials,
        "_RENAMEAT2",
        None if rename_result == "unavailable" else FakeRename(),
    )
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
    terminal_states: list[tuple[int, list[Any]]] = []
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
        lambda _fd, when, state: terminal_states.append((when, state.copy())),
    )
    value = credentials._read_private_tty("ASCII prompt: ")
    assert value == bytearray(b"value")
    assert opened == [("/dev/tty", credentials._TTY_FLAGS)]
    assert credentials._TTY_FLAGS & getattr(os, "O_CLOEXEC", 0)
    assert credentials._TTY_FLAGS & getattr(os, "O_NOFOLLOW", 0)
    assert terminal_states[0][1][3] & termios.ECHO == 0
    assert terminal_states[0][1][3] & getattr(termios, "ECHONL", 0) == 0
    assert terminal_states[-1] == (termios.TCSAFLUSH, original)
    assert b"".join(writes) == b"ASCII prompt: \n"


def termios_flags() -> int:
    return int(termios.ECHO) | int(getattr(termios, "ECHONL", 0)) | int(termios.ICANON)


def _char_stat() -> os.stat_result:
    return os.stat_result((stat.S_IFCHR | 0o600, 0, 0, 1, os.geteuid(), 0, 0, 0, 0, 0))


def _read_until_prompt(descriptor: int, prompt: bytes) -> None:
    observed = bytearray()
    deadline = time.monotonic() + 5
    while prompt not in observed:
        remaining = deadline - time.monotonic()
        assert remaining > 0
        readable, _, _ = select.select([descriptor], [], [], remaining)
        assert readable
        chunk = os.read(descriptor, 4096)
        assert chunk
        observed.extend(chunk)


def _real_pty_rejection_report(line: bytes, *, maximum: int | None = None) -> bytes:
    report_read, report_write = os.pipe()
    child_pid, master_fd = pty.fork()
    if child_pid == 0:
        os.close(report_read)
        if maximum is not None:
            setattr(credentials, "MAX_SECRET_BYTES", maximum)
        report = b"UNEXPECTED"
        try:
            credentials._read_private_tty("ASCII prompt: ")
        except credentials.CredentialIntakeFailure as exc:
            if exc.code is credentials.CredentialIntakeFailureCode.INPUT_UNAVAILABLE:
                tty_fd = os.open(
                    "/dev/tty",
                    os.O_RDONLY
                    | os.O_NONBLOCK
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                )
                try:
                    try:
                        remaining = os.read(tty_fd, 8192)
                    except BlockingIOError:
                        remaining = b""
                    echo_restored = bool(termios.tcgetattr(tty_fd)[3] & termios.ECHO)
                    report = (b"LEFTOVER" if remaining else b"DRAINED") + (
                        b":ECHO_ON" if echo_restored else b":ECHO_OFF"
                    )
                finally:
                    os.close(tty_fd)
        except BaseException:
            report = b"UNEXPECTED"
        else:
            report = b"ACCEPTED"
        try:
            os.write(report_write, report)
        finally:
            os.close(report_write)
        os._exit(0)

    os.close(report_write)
    reaped = False
    try:
        _read_until_prompt(master_fd, b"ASCII prompt: ")
        offset = 0
        while offset < len(line):
            written = os.write(master_fd, line[offset:])
            assert written > 0
            offset += written
        readable, _, _ = select.select([report_read], [], [], 5)
        assert readable
        report = os.read(report_read, 64)
        waited_pid, status = os.waitpid(child_pid, 0)
        reaped = True
        assert waited_pid == child_pid
        assert os.waitstatus_to_exitcode(status) == 0
        return report
    finally:
        os.close(report_read)
        os.close(master_fd)
        if not reaped:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                os.waitpid(child_pid, 0)
            except ChildProcessError:
                pass


def _real_pty_success_typeahead_report(line: bytes) -> bytes:
    report_read, report_write = os.pipe()
    child_pid, master_fd = pty.fork()
    if child_pid == 0:
        os.close(report_read)
        report = b"UNEXPECTED"
        value: bytearray | None = None
        try:
            value = credentials._read_private_tty("ASCII prompt: ")
            if value == bytearray(b"accepted"):
                tty_fd = os.open(
                    "/dev/tty",
                    os.O_RDONLY
                    | os.O_NONBLOCK
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                )
                try:
                    try:
                        remaining = os.read(tty_fd, 8192)
                    except BlockingIOError:
                        remaining = b""
                    echo_restored = bool(termios.tcgetattr(tty_fd)[3] & termios.ECHO)
                    report = (b"LEFTOVER" if remaining else b"DRAINED") + (
                        b":ECHO_ON" if echo_restored else b":ECHO_OFF"
                    )
                finally:
                    os.close(tty_fd)
        except BaseException:
            report = b"UNEXPECTED"
        finally:
            credentials._wipe(value)
        try:
            os.write(report_write, report)
        finally:
            os.close(report_write)
        os._exit(0)

    os.close(report_write)
    reaped = False
    try:
        _read_until_prompt(master_fd, b"ASCII prompt: ")
        offset = 0
        while offset < len(line):
            written = os.write(master_fd, line[offset:])
            assert written > 0
            offset += written
        readable, _, _ = select.select([report_read], [], [], 5)
        assert readable
        report = os.read(report_read, 64)
        waited_pid, status = os.waitpid(child_pid, 0)
        reaped = True
        assert waited_pid == child_pid
        assert os.waitstatus_to_exitcode(status) == 0
        return report
    finally:
        os.close(report_read)
        os.close(master_fd)
        if not reaped:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                os.waitpid(child_pid, 0)
            except ChildProcessError:
                pass


@pytest.mark.parametrize(
    ("line", "maximum"),
    (
        (b"prefix\x01shell-suffix\n", None),
        (b"prefix\x01shell-suffix\nqueued-command\n", None),
        (b"123456789shell-suffix\n", 8),
        (b"x" * 4095 + b"shell-suffix\n", None),
    ),
)
def test_hidden_tty_discards_rejected_canonical_line_before_restoring_echo(
    line: bytes, maximum: int | None
) -> None:
    assert _real_pty_rejection_report(line, maximum=maximum) == b"DRAINED:ECHO_ON"


def test_hidden_tty_discards_queued_line_after_valid_input_before_echo_restore() -> (
    None
):
    assert (
        _real_pty_success_typeahead_report(b"accepted\nqueued-command\n")
        == b"DRAINED:ECHO_ON"
    )


def test_hidden_tty_restores_terminal_on_input_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    restored: list[tuple[int, list[Any]]] = []
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
        lambda _fd, when, state: restored.append((when, state.copy())),
    )
    with pytest.raises(credentials.CredentialIntakeFailure):
        credentials._read_private_tty("ASCII prompt: ")
    assert restored[-1] == (termios.TCSAFLUSH, original)


@pytest.mark.parametrize("termination", ("eof", "read_error", "interrupt", "prompt"))
def test_hidden_tty_pre_rejection_failure_flushes_typeahead_with_terminal_restore(
    termination: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptor = 98
    original: list[Any] = [0, 0, 0, termios_flags(), 0, 0, []]
    terminal_states: list[tuple[int, list[Any]]] = []

    def read_input(_fd: int, _size: int) -> bytes:
        if termination == "eof":
            return b""
        if termination == "interrupt":
            raise KeyboardInterrupt
        raise OSError("read failed")

    def write_output(_fd: int, value: bytes) -> int:
        if termination == "prompt":
            return 0
        return len(value)

    monkeypatch.setattr(os, "open", lambda _path, _flags: descriptor)
    monkeypatch.setattr(os, "set_inheritable", lambda _fd, _value: None)
    monkeypatch.setattr(os, "get_inheritable", lambda _fd: False)
    monkeypatch.setattr(os, "fstat", lambda _fd: _char_stat())
    monkeypatch.setattr(os, "read", read_input)
    monkeypatch.setattr(os, "write", write_output)
    monkeypatch.setattr(os, "close", lambda _fd: None)
    monkeypatch.setattr(termios, "tcgetattr", lambda _fd: original.copy())
    monkeypatch.setattr(
        termios,
        "tcsetattr",
        lambda _fd, when, state: terminal_states.append((when, state.copy())),
    )

    with pytest.raises(credentials.CredentialIntakeFailure) as caught:
        credentials._read_private_tty("ASCII prompt: ")
    assert (
        caught.value.code is credentials.CredentialIntakeFailureCode.INPUT_UNAVAILABLE
    )
    assert terminal_states[0][0] == termios.TCSANOW
    assert terminal_states[0][1][3] & termios.ECHO == 0
    assert terminal_states[-1] == (termios.TCSAFLUSH, original)


def test_hidden_tty_rejects_noncanonical_mode_without_reading_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    descriptor = 95
    original = [0, 0, 0, termios_flags() & ~termios.ICANON, 0, 0, []]
    terminal_states: list[tuple[int, list[Any]]] = []
    read_called = False

    def unexpected_read(_fd: int, _size: int) -> bytes:
        nonlocal read_called
        read_called = True
        return b"unexpected"

    monkeypatch.setattr(os, "open", lambda _path, _flags: descriptor)
    monkeypatch.setattr(os, "set_inheritable", lambda _fd, _value: None)
    monkeypatch.setattr(os, "get_inheritable", lambda _fd: False)
    monkeypatch.setattr(os, "fstat", lambda _fd: _char_stat())
    monkeypatch.setattr(os, "read", unexpected_read)
    monkeypatch.setattr(os, "write", lambda _fd, value: len(value))
    monkeypatch.setattr(os, "close", lambda _fd: None)
    monkeypatch.setattr(termios, "tcgetattr", lambda _fd: original.copy())
    monkeypatch.setattr(
        termios,
        "tcsetattr",
        lambda _fd, when, state: terminal_states.append((when, state.copy())),
    )
    with pytest.raises(credentials.CredentialIntakeFailure) as caught:
        credentials._read_private_tty("ASCII prompt: ")
    assert (
        caught.value.code is credentials.CredentialIntakeFailureCode.INPUT_UNAVAILABLE
    )
    assert read_called is False
    assert terminal_states == [(termios.TCSANOW, original)]


@pytest.mark.parametrize(
    "termination",
    (
        "eof",
        "read_error",
        "nonblocking_error",
        "select_error",
        "timeout",
        "discard_limit",
    ),
)
def test_hidden_tty_rejected_line_uses_atomic_flush_restore_when_drain_fails(
    termination: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptor = 96
    original = [0, 0, 0, termios_flags(), 0, 0, []]
    terminal_states: list[tuple[int, list[Any]]] = []
    wiped: list[tuple[bytes, bytes]] = []
    original_wipe = credentials._wipe
    chunks: list[bytes | BaseException]
    if termination == "eof":
        chunks = [b"p", b"\x01", b""]
    elif termination == "read_error":
        chunks = [b"p", b"\x01", OSError("read failed")]
    else:
        chunks = [b"p", b"\x01", b"a", b"b"]
        if termination == "discard_limit":
            monkeypatch.setattr(credentials, "MAX_TTY_DISCARD_BYTES", 1)
    input_chunks = iter(chunks)

    def read_input(_fd: int, _size: int) -> bytes:
        chunk = next(input_chunks)
        if isinstance(chunk, BaseException):
            raise chunk
        return chunk

    def record_wipe(value: bytearray | None) -> None:
        before = bytes(value or b"")
        original_wipe(value)
        wiped.append((before, bytes(value or b"")))

    monkeypatch.setattr(os, "open", lambda _path, _flags: descriptor)
    monkeypatch.setattr(os, "set_inheritable", lambda _fd, _value: None)
    monkeypatch.setattr(os, "get_inheritable", lambda _fd: False)
    if termination == "nonblocking_error":
        monkeypatch.setattr(
            os, "set_blocking", lambda *_args: (_ for _ in ()).throw(OSError())
        )
    else:
        monkeypatch.setattr(os, "set_blocking", lambda _fd, _value: None)
    monkeypatch.setattr(os, "fstat", lambda _fd: _char_stat())
    monkeypatch.setattr(os, "read", read_input)
    monkeypatch.setattr(os, "write", lambda _fd, value: len(value))
    monkeypatch.setattr(os, "close", lambda _fd: None)
    monkeypatch.setattr(termios, "tcgetattr", lambda _fd: original.copy())
    monkeypatch.setattr(
        termios,
        "tcsetattr",
        lambda _fd, when, state: terminal_states.append((when, state.copy())),
    )
    monkeypatch.setattr(credentials, "_wipe", record_wipe)
    if termination == "select_error":
        monkeypatch.setattr(
            select, "select", lambda *_args: (_ for _ in ()).throw(OSError())
        )
    elif termination == "timeout":
        monkeypatch.setattr(select, "select", lambda *_args: ([], [], []))
    else:
        monkeypatch.setattr(
            select, "select", lambda reads, _writes, _errors, _timeout: (reads, [], [])
        )

    with pytest.raises(credentials.CredentialIntakeFailure) as caught:
        credentials._read_private_tty("ASCII prompt: ")
    assert (
        caught.value.code is credentials.CredentialIntakeFailureCode.INPUT_UNAVAILABLE
    )
    assert terminal_states[0][0] == termios.TCSANOW
    assert terminal_states[0][1][3] & termios.ECHO == 0
    assert terminal_states[-1] == (termios.TCSAFLUSH, original)
    assert wiped[0] == (b"p", b"\x00")


def test_hidden_tty_rejected_line_wipes_then_drains_through_first_lf_before_flush(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    descriptor = 97
    original: list[Any] = [0, 0, 0, termios_flags(), 0, 0, []]
    chunks = iter((b"p", b"\x01", b"s", b"u", b"f", b"\n", b"next\n"))
    events: list[str] = []
    terminal_state: list[Any] = original.copy()

    def set_terminal(_fd: int, when: int, state: list[Any]) -> None:
        nonlocal terminal_state
        terminal_state = state.copy()
        events.append("flush-restore" if when == termios.TCSAFLUSH else "set")

    def read_input(_fd: int, _size: int) -> bytes:
        value = next(chunks)
        events.append(f"read:{value.hex()}")
        return value

    def ready(
        reads: list[int], _writes: list[int], _errors: list[int], _timeout: float
    ) -> tuple[list[int], list[int], list[int]]:
        assert int(terminal_state[3]) & int(termios.ECHO) == 0
        assert int(terminal_state[3]) & int(getattr(termios, "ECHONL", 0)) == 0
        events.append("select")
        return reads, [], []

    original_wipe = credentials._wipe

    def record_wipe(value: bytearray | None) -> None:
        original_wipe(value)
        events.append("wipe")

    monkeypatch.setattr(os, "open", lambda _path, _flags: descriptor)
    monkeypatch.setattr(os, "set_inheritable", lambda _fd, _value: None)
    monkeypatch.setattr(os, "get_inheritable", lambda _fd: False)
    blocking_states: list[bool] = []
    monkeypatch.setattr(
        os, "set_blocking", lambda _fd, value: blocking_states.append(value)
    )
    monkeypatch.setattr(os, "fstat", lambda _fd: _char_stat())
    monkeypatch.setattr(os, "read", read_input)
    monkeypatch.setattr(os, "write", lambda _fd, value: len(value))
    monkeypatch.setattr(os, "close", lambda _fd: None)
    monkeypatch.setattr(termios, "tcgetattr", lambda _fd: original.copy())
    monkeypatch.setattr(termios, "tcsetattr", set_terminal)
    monkeypatch.setattr(select, "select", ready)
    monkeypatch.setattr(credentials, "_wipe", record_wipe)

    with pytest.raises(credentials.CredentialIntakeFailure) as caught:
        credentials._read_private_tty("ASCII prompt: ")
    assert (
        caught.value.code is credentials.CredentialIntakeFailureCode.INPUT_UNAVAILABLE
    )
    assert next(chunks) == b"next\n"
    assert events.index("wipe") < events.index("select")
    assert len([event for event in events if event == "set"]) == 1
    assert events.index("flush-restore") > events.index("select")
    assert blocking_states == [False]


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
        renameat2 = FakePrctl()

    monkeypatch.setattr(resource, "setrlimit", lambda _which, _value: None)
    monkeypatch.setattr(resource, "getrlimit", lambda _which: (0, 0))
    monkeypatch.setattr(ctypes, "CDLL", lambda *_args, **_kwargs: FakeLibc())
    credentials._disable_process_disclosure(runtime_lock=lambda: None)
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
        credentials._disable_process_disclosure(runtime_lock=lambda: None)
    assert caught.value.code is credentials.CredentialIntakeFailureCode.PLATFORM_UNSAFE


def _run_runtime_child(code: str, *arguments: Path) -> subprocess.CompletedProcess[str]:
    source_root = Path(__file__).resolve().parents[2]
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-c",
            (f"import sys; sys.path.insert(0, {os.fspath(source_root)!r}); " + code),
            *(os.fspath(argument) for argument in arguments),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
    )


def test_native_runtime_inventory_is_exact_and_locked_before_input() -> None:
    completed = _run_runtime_child(
        "from scripts import rakuten_live_smoke_credentials as c; "
        "c._disable_process_disclosure(); "
        "c._assert_runtime_lock_intact(); "
        "c.os.write(1, b'LOCKED\\n')"
    )

    assert completed.returncode == 0
    assert completed.stdout == "LOCKED\n"
    assert completed.stderr == ""


@pytest.mark.parametrize("late_action", ("named_dlopen", "import"))
def test_native_runtime_lock_rejects_late_code_loading_with_fixed_receipt(
    tmp_path: Path,
    late_action: str,
) -> None:
    hostile_library = tmp_path / "late-loader.so"
    _build_hostile_loader_hook(hostile_library)
    code = (
        "from pathlib import Path; "
        "from scripts import rakuten_live_smoke_credentials as c; "
        "root=Path(sys.argv[1]); library=sys.argv[2]; "
        "c._disable_process_disclosure(); "
        "reader=(lambda _prompt: c.ctypes.CDLL(library)) "
        "if sys.argv[3] == 'named_dlopen' "
        "else (lambda _prompt: __import__('fractions')); "
        "raise SystemExit(c.main(['setup'], repository_root=root, "
        "expected_root=root, reader=reader, disclosure_guard=lambda: None))"
    )
    completed = _run_runtime_child(code, tmp_path, hostile_library, Path(late_action))

    assert completed.returncode == 1
    assert completed.stdout == (
        '{"command":"setup","ok":false,'
        '"reason_code":"RAKUTEN_CREDENTIAL_PLATFORM_UNSAFE",'
        '"status":"INVALID"}\n'
    )
    assert completed.stderr == ""
    assert os.fspath(hostile_library) not in completed.stdout


def test_native_runtime_inventory_rejects_object_loaded_before_freeze(
    tmp_path: Path,
) -> None:
    hostile_library = tmp_path / "prefreeze-loader.so"
    _build_hostile_loader_hook(hostile_library)
    code = (
        "from pathlib import Path; "
        "from scripts import rakuten_live_smoke_credentials as c; "
        "root=Path(sys.argv[1]); c.ctypes.CDLL(sys.argv[2]); "
        "raise SystemExit(c.main(['setup'], repository_root=root, "
        "expected_root=root, reader=lambda _prompt: bytearray(b'never'), "
        "disclosure_guard=c._disable_process_disclosure))"
    )
    completed = _run_runtime_child(code, tmp_path, hostile_library)

    assert completed.returncode == 1
    assert completed.stdout == (
        '{"command":"setup","ok":false,'
        '"reason_code":"RAKUTEN_CREDENTIAL_PLATFORM_UNSAFE",'
        '"status":"INVALID"}\n'
    )
    assert completed.stderr == ""
    assert os.fspath(hostile_library) not in completed.stdout


def test_native_runtime_freeze_keeps_cached_publish_primitive_usable(
    tmp_path: Path,
) -> None:
    code = (
        "from pathlib import Path; "
        "from scripts import rakuten_live_smoke_credentials as c; "
        "root=Path(sys.argv[1]); values=iter((bytearray(b'a'), bytearray(b'b'))); "
        "raise SystemExit(c.main(['setup'], repository_root=root, "
        "expected_root=root, reader=lambda _prompt: next(values), "
        "disclosure_guard=c._disable_process_disclosure))"
    )
    completed = _run_runtime_child(code, tmp_path)

    assert completed.returncode == 0
    assert completed.stdout == '{"command":"setup","ok":true,"status":"READY"}\n'
    assert completed.stderr == ""
    assert _inspect(tmp_path) is credentials.CredentialStoreStatus.READY


@pytest.mark.parametrize(
    "raw",
    (
        b"not-a-map-line\n",
        b"1000-2000 rwxp 00000000 00:00 0\n",
        b"1000-2000 r-xp 00000000 00:00 0\n",
        b"1000-2000 r-xp 00000000 00:00 0 [unexpected]\n",
        b"1000-2000 r-xp 00000000 08:30 0 /tmp/object\n",
    ),
)
def test_runtime_map_parser_rejects_malformed_or_executable_unknown_maps(
    raw: bytes,
) -> None:
    with pytest.raises(credentials.CredentialIntakeFailure) as caught:
        credentials._parse_runtime_maps(raw)
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
    launcher_environment: _LauncherEnvironment,
) -> None:
    environment = launcher_environment
    site_packages = environment.venv_root / "lib/python3.14/site-packages"
    site_packages.mkdir(parents=True)
    canary = environment.repository_root / "executable-pth-hook-ran"
    hostile_pth = (
        "import builtins; "
        f"builtins.open({str(canary)!r}, 'w', encoding='utf-8').write('ran')\n",
    )
    (site_packages / "hostile-startup.pth").write_text(*hostile_pth, encoding="utf-8")

    positive_venv = environment.repository_root / "positive-control-venv"
    positive_bin = positive_venv / "bin"
    positive_site = positive_venv / "lib/python3.14/site-packages"
    positive_bin.mkdir(parents=True)
    positive_site.mkdir(parents=True)
    real_base = Path(sys.base_prefix)
    (positive_bin / "python").symlink_to(real_base / "bin/python3.14")
    (positive_venv / "pyvenv.cfg").write_text(
        f"home = {real_base / 'bin'}\n"
        "implementation = CPython\n"
        "uv = 0.12.1\n"
        "version_info = 3.14.6\n"
        "include-system-site-packages = false\n"
        "prompt = raos\n",
        encoding="utf-8",
    )
    (positive_site / "hostile-startup.pth").write_text(*hostile_pth, encoding="utf-8")
    positive_control = subprocess.run(
        [os.fspath(positive_bin / "python"), "-I", "-c", "pass"],
        cwd=environment.repository_root,
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

    completed = subprocess.run(
        [os.fspath(environment.launcher), "check"],
        cwd=environment.repository_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0
    assert completed.stdout == '{"command":"check","ok":true,"status":"ABSENT"}\n'
    assert completed.stderr == ""
    assert not canary.exists()


def _build_hostile_loader_hook(output: Path) -> None:
    source = r"""
#define _GNU_SOURCE
#include <fcntl.h>
#include <link.h>
#include <stdlib.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <unistd.h>

static void mark(char value) {
    const char *path = getenv("RAOS_TEST_LOADER_CANARY");
    if (path == NULL) {
        return;
    }
    int descriptor = open(path, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0600);
    if (descriptor >= 0) {
        ssize_t written = write(descriptor, &value, 1);
        (void)written;
        (void)close(descriptor);
    }
}

__attribute__((constructor)) static void loaded(void) {
    mark('C');
}

uid_t getuid(void) {
    mark('I');
    return (uid_t)syscall(SYS_getuid);
}

unsigned int la_version(unsigned int version) {
    (void)version;
    mark('A');
    return LAV_CURRENT;
}

unsigned int la_objopen(
    struct link_map *map,
    Lmid_t namespace_id,
    uintptr_t *cookie
) {
    (void)map;
    (void)namespace_id;
    (void)cookie;
    mark('O');
    return LA_FLG_BINDTO | LA_FLG_BINDFROM;
}
"""
    completed = subprocess.run(
        [
            "/usr/bin/gcc",
            "-shared",
            "-fPIC",
            "-O2",
            "-Wl,-z,relro,-z,now",
            "-x",
            "c",
            "-",
            "-o",
            os.fspath(output),
        ],
        input=source,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0
    assert completed.stdout == ""
    assert completed.stderr == ""
    output.chmod(0o700)


@pytest.mark.parametrize(
    ("loader_variable", "positive_marker"),
    (("LD_PRELOAD", b"I"), ("LD_AUDIT", b"A")),
)
def test_launcher_static_entry_never_runs_hostile_loader_hook(
    launcher_environment: _LauncherEnvironment,
    loader_variable: str,
    positive_marker: bytes,
) -> None:
    environment = launcher_environment
    hostile_library = environment.trust_root / f"{loader_variable.lower()}.so"
    canary = environment.trust_root / f"{loader_variable.lower()}.canary"
    _build_hostile_loader_hook(hostile_library)
    hostile_environment = dict(os.environ)
    hostile_environment[loader_variable] = os.fspath(hostile_library)
    hostile_environment["RAOS_TEST_LOADER_CANARY"] = os.fspath(canary)

    positive = subprocess.run(
        ["/bin/bash", "-p", "-c", "/usr/bin/id -u >/dev/null"],
        check=False,
        capture_output=True,
        env=hostile_environment,
        timeout=10,
    )
    assert positive.returncode == 0
    assert canary.is_file()
    assert positive_marker in canary.read_bytes()
    canary.unlink()

    completed = subprocess.run(
        [os.fspath(environment.launcher), "check"],
        cwd=environment.repository_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        env=hostile_environment,
    )
    assert completed.returncode == 0
    assert completed.stdout == '{"command":"check","ok":true,"status":"ABSENT"}\n'
    assert completed.stderr == ""
    assert not canary.exists()


def test_launcher_static_entry_replaces_shell_control_environment(
    launcher_environment: _LauncherEnvironment,
) -> None:
    environment = launcher_environment
    canary = environment.trust_root / "shell-control.canary"
    startup = environment.trust_root / "hostile-bash-env.sh"
    startup.write_text(
        f"printf ran > {shlex.quote(os.fspath(canary))}\n", encoding="ascii"
    )
    startup.chmod(0o600)
    hostile_environment = dict(os.environ)
    hostile_environment.update(
        {
            "ASH_ENV": os.fspath(startup),
            "BASH_ENV": os.fspath(startup),
            "ENV": os.fspath(startup),
            "GLIBC_TUNABLES": "glibc.rtld.nns=8",
            "IFS": ":",
            "LD_DEBUG": "libs",
            "LD_LIBRARY_PATH": os.fspath(environment.trust_root),
            "PATH": os.fspath(environment.trust_root),
        }
    )

    positive = subprocess.run(
        ["/usr/bin/bash", "-c", ":"],
        check=False,
        capture_output=True,
        env=hostile_environment,
        timeout=10,
    )
    assert positive.returncode == 0
    assert canary.read_text(encoding="ascii") == "ran"
    canary.unlink()

    completed = subprocess.run(
        [os.fspath(environment.launcher), "check"],
        cwd=environment.repository_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        env=hostile_environment,
    )
    assert completed.returncode == 0
    assert completed.stdout == '{"command":"check","ok":true,"status":"ABSENT"}\n'
    assert completed.stderr == ""
    assert not canary.exists()


def test_static_busybox_entry_is_exact_loader_free_elf() -> None:
    busybox = Path("/usr/bin/busybox")
    metadata = busybox.lstat()
    data = busybox.read_bytes()
    assert metadata.st_uid == 0
    assert stat.S_ISREG(metadata.st_mode)
    assert stat.S_IMODE(metadata.st_mode) & 0o022 == 0
    assert hashlib.sha256(data).hexdigest() == (
        "b3c1009e1b5c927e537487c80639cdf404f69e3eb49371d9be5d841672be3ff9"
    )
    assert data[:6] == b"\x7fELF\x02\x01"
    assert struct.unpack_from("<H", data, 16)[0] == 2
    assert struct.unpack_from("<H", data, 18)[0] == 62
    program_offset = struct.unpack_from("<Q", data, 32)[0]
    program_entry_size = struct.unpack_from("<H", data, 54)[0]
    program_count = struct.unpack_from("<H", data, 56)[0]
    program_types = {
        struct.unpack_from("<I", data, program_offset + index * program_entry_size)[0]
        for index in range(program_count)
    }
    assert 2 not in program_types
    assert 3 not in program_types


@pytest.mark.parametrize(
    "target_name",
    (
        "trust_root",
        "repository_root",
        "scripts",
        "launcher",
        "credential_script",
        "venv_root",
        "venv_bin",
        "pyvenv_cfg",
        "runtime_parent",
        "expected_base",
        "expected_bin",
        "expected_python",
        "expected_lib",
        "expected_stdlib",
        "runtime_file",
    ),
)
@pytest.mark.parametrize("writable_bits", (0o020, 0o002))
def test_launcher_rejects_every_group_or_world_writable_trust_path(
    launcher_environment: _LauncherEnvironment,
    target_name: str,
    writable_bits: int,
) -> None:
    environment = launcher_environment
    target = cast(Path, getattr(environment, target_name))
    original_mode = stat.S_IMODE(target.stat().st_mode)
    try:
        target.chmod(original_mode | writable_bits)
        completed = subprocess.run(
            [os.fspath(environment.launcher), "check"],
            cwd=environment.repository_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    finally:
        target.chmod(original_mode)

    assert completed.returncode == 69
    assert completed.stdout == (
        '{"command":"invalid","ok":false,'
        '"reason_code":"RAKUTEN_CREDENTIAL_LAUNCHER_INVALID",'
        '"status":"INVALID"}\n'
    )
    assert completed.stderr == ""


def test_launcher_accepts_exact_owned_symlink_and_copied_environment(
    launcher_environment: _LauncherEnvironment,
) -> None:
    environment = launcher_environment
    python_link = environment.venv_bin / "python"
    assert stat.S_ISLNK(python_link.lstat().st_mode)
    assert stat.S_IMODE(python_link.lstat().st_mode) == 0o777
    assert os.readlink(python_link) == os.fspath(environment.expected_python)

    completed = subprocess.run(
        [os.fspath(environment.launcher), "check"],
        cwd=environment.repository_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0
    assert completed.stdout == '{"command":"check","ok":true,"status":"ABSENT"}\n'
    assert completed.stderr == ""


def test_launcher_rejects_newline_suffixed_python_symlink_target(
    launcher_environment: _LauncherEnvironment,
) -> None:
    environment = launcher_environment
    python_link = environment.venv_bin / "python"
    python_link.unlink()
    python_link.symlink_to(f"{environment.expected_python}\n")
    try:
        completed = subprocess.run(
            [os.fspath(environment.launcher), "check"],
            cwd=environment.repository_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    finally:
        python_link.unlink()
        python_link.symlink_to(environment.expected_python)

    assert completed.returncode == 69
    assert completed.stdout == (
        '{"command":"invalid","ok":false,'
        '"reason_code":"RAKUTEN_CREDENTIAL_LAUNCHER_INVALID",'
        '"status":"INVALID"}\n'
    )
    assert completed.stderr == ""


@pytest.mark.parametrize(
    "relative",
    ("lib/python314.zip", "lib/libc.so.6", "lib/libpthread.so.0"),
)
def test_launcher_rejects_unvalidated_python_or_loader_shadow(
    launcher_environment: _LauncherEnvironment,
    relative: str,
) -> None:
    environment = launcher_environment
    shadow = environment.expected_base / relative
    shadow.write_bytes(b"not executable\n")
    shadow.chmod(0o600)
    try:
        completed = subprocess.run(
            [os.fspath(environment.launcher), "check"],
            cwd=environment.repository_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    finally:
        shadow.unlink()

    assert completed.returncode == 69
    assert "RAKUTEN_CREDENTIAL_LAUNCHER_INVALID" in completed.stdout
    assert completed.stderr == ""


def test_launcher_rejects_pinned_python_content_digest_drift(
    launcher_environment: _LauncherEnvironment,
) -> None:
    environment = launcher_environment
    original = environment.expected_python.read_bytes()
    mutated = bytearray(original)
    mutated[-1] ^= 1
    try:
        environment.expected_python.write_bytes(mutated)
        environment.expected_python.chmod(0o755)
        completed = subprocess.run(
            [os.fspath(environment.launcher), "check"],
            cwd=environment.repository_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    finally:
        environment.expected_python.write_bytes(original)
        environment.expected_python.chmod(0o755)

    assert completed.returncode == 69
    assert "RAKUTEN_CREDENTIAL_LAUNCHER_INVALID" in completed.stdout
    assert completed.stderr == ""


def test_launcher_rejects_nested_glibc_loader_shadow(
    launcher_environment: _LauncherEnvironment,
) -> None:
    environment = launcher_environment
    namespace = environment.expected_lib / "glibc-hwcaps/x86-64-v3"
    namespace.mkdir(parents=True)
    shadow = namespace / "libc.so.6"
    shadow.write_bytes(b"not executable\n")
    shadow.chmod(0o600)
    try:
        completed = subprocess.run(
            [os.fspath(environment.launcher), "check"],
            cwd=environment.repository_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    finally:
        shadow.unlink()
        namespace.rmdir()
        namespace.parent.rmdir()

    assert completed.returncode == 69
    assert "RAKUTEN_CREDENTIAL_LAUNCHER_INVALID" in completed.stdout
    assert completed.stderr == ""


def test_launcher_missing_trusted_leaf_has_only_fixed_sanitized_output(
    launcher_environment: _LauncherEnvironment,
) -> None:
    environment = launcher_environment
    missing = environment.venv_root / "pyvenv.cfg.missing"
    environment.pyvenv_cfg.rename(missing)
    try:
        completed = subprocess.run(
            [os.fspath(environment.launcher), "check"],
            cwd=environment.repository_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    finally:
        missing.rename(environment.pyvenv_cfg)

    assert completed.returncode == 69
    assert completed.stdout == (
        '{"command":"invalid","ok":false,'
        '"reason_code":"RAKUTEN_CREDENTIAL_LAUNCHER_INVALID",'
        '"status":"INVALID"}\n'
    )
    assert completed.stderr == ""


@pytest.mark.parametrize(
    ("directory_name", "filename"),
    tuple(
        (directory_name, filename)
        for directory_name in ("venv_bin", "expected_bin", "expected_lib")
        for filename in (
            "python._pth",
            "python3.14._pth",
            "libpython3.14._pth",
            "pybuilddir.txt",
        )
    ),
)
def test_launcher_rejects_every_pre_python_path_configuration_shadow(
    launcher_environment: _LauncherEnvironment,
    directory_name: str,
    filename: str,
) -> None:
    environment = launcher_environment
    directory = cast(Path, getattr(environment, directory_name))
    shadow = directory / filename
    shadow.write_text("import site\n", encoding="utf-8")
    shadow.chmod(0o600)
    try:
        completed = subprocess.run(
            [os.fspath(environment.launcher), "check"],
            cwd=environment.repository_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    finally:
        shadow.unlink()

    assert completed.returncode == 69
    assert "RAKUTEN_CREDENTIAL_LAUNCHER_INVALID" in completed.stdout
    assert completed.stderr == ""


def test_launcher_sanitizes_base_executable_override_before_python_start(
    launcher_environment: _LauncherEnvironment,
) -> None:
    environment = launcher_environment
    hostile_environment = dict(os.environ)
    hostile_environment["__PYVENV_LAUNCHER__"] = "/untrusted/python"

    completed = subprocess.run(
        [os.fspath(environment.launcher), "check"],
        cwd=environment.repository_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        env=hostile_environment,
    )

    assert completed.returncode == 0
    assert completed.stdout == '{"command":"check","ok":true,"status":"ABSENT"}\n'
    assert completed.stderr == ""


def test_launcher_rejects_symlinked_runtime_ancestor(
    launcher_environment: _LauncherEnvironment,
) -> None:
    environment = launcher_environment
    stdlib = environment.expected_stdlib
    preserved = environment.expected_lib / "python3.14-preserved"
    stdlib.rename(preserved)
    stdlib.symlink_to(preserved)
    try:
        completed = subprocess.run(
            [os.fspath(environment.launcher), "check"],
            cwd=environment.repository_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    finally:
        stdlib.unlink()
        preserved.rename(stdlib)

    assert completed.returncode == 69
    assert "RAKUTEN_CREDENTIAL_LAUNCHER_INVALID" in completed.stdout
    assert completed.stderr == ""


def test_launcher_rejects_wrong_owner_from_metadata_helper(
    launcher_environment: _LauncherEnvironment,
) -> None:
    environment = launcher_environment
    original_launcher = environment.launcher.read_text(encoding="utf-8")
    assert original_launcher.count("/usr/bin/stat -c '%f %u'") == 1
    fake_stat = environment.repository_root / "fixture-stat"
    fake_stat.write_text(
        "#!/bin/bash -p\n"
        "set -euo pipefail\n"
        f"target={shlex.quote(os.fspath(environment.credential_script))}\n"
        'if [[ ${!#} == "$target" ]]; then\n'
        "  mode=$(/usr/bin/stat -c '%f' -- \"$target\")\n"
        f"  printf '%s %s\\n' \"$mode\" {os.geteuid() + 1}\n"
        "else\n"
        '  exec /usr/bin/stat "$@"\n'
        "fi\n",
        encoding="utf-8",
    )
    fake_stat.chmod(0o700)
    try:
        environment.launcher.write_text(
            original_launcher.replace(
                "/usr/bin/stat -c '%f %u'",
                f"{shlex.quote(os.fspath(fake_stat))} -c '%f %u'",
            ),
            encoding="utf-8",
        )
        environment.launcher.chmod(0o755)
        completed = subprocess.run(
            [os.fspath(environment.launcher), "check"],
            cwd=environment.repository_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    finally:
        environment.launcher.write_text(original_launcher, encoding="utf-8")
        environment.launcher.chmod(0o755)
        fake_stat.unlink()

    assert completed.returncode == 69
    assert "RAKUTEN_CREDENTIAL_LAUNCHER_INVALID" in completed.stdout
    assert completed.stderr == ""


def test_launcher_executes_opened_script_inode_after_path_replacement(
    launcher_environment: _LauncherEnvironment,
) -> None:
    environment = launcher_environment
    original_launcher = environment.launcher.read_text(encoding="utf-8")
    original_script = environment.credential_script.read_bytes()
    synchronization_point = "    os.set_inheritable(script_descriptor, True)\n"
    assert original_launcher.count(synchronization_point) == 1
    opened = environment.repository_root / "script-opened"
    release = environment.repository_root / "release-opened-script"
    os.mkfifo(release, 0o600)
    injected = (
        f"    signal_fd = os.open({os.fspath(opened)!r}, "
        "os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)\n"
        "    os.close(signal_fd)\n"
        f"    release_fd = os.open({os.fspath(release)!r}, os.O_RDONLY)\n"
        "    try:\n"
        '        if os.read(release_fd, 1) != b"x":\n'
        "            raise OSError\n"
        "    finally:\n"
        "        os.close(release_fd)\n"
    )
    replacement = environment.scripts / "replacement-credential.py"
    replacement.write_text('print("REPLACED")\n', encoding="utf-8")
    replacement.chmod(0o644)
    process: subprocess.Popen[str] | None = None
    try:
        environment.launcher.write_text(
            original_launcher.replace(
                synchronization_point,
                injected + synchronization_point,
            ),
            encoding="utf-8",
        )
        environment.launcher.chmod(0o755)
        process = subprocess.Popen(
            [os.fspath(environment.launcher), "check"],
            cwd=environment.repository_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + 10.0
        while not opened.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert opened.is_file()
        os.replace(replacement, environment.credential_script)
        release_fd = os.open(release, os.O_WRONLY)
        try:
            assert os.write(release_fd, b"x") == 1
        finally:
            os.close(release_fd)
        stdout, stderr = process.communicate(timeout=10)
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        environment.launcher.write_text(original_launcher, encoding="utf-8")
        environment.launcher.chmod(0o755)
        environment.credential_script.write_bytes(original_script)
        environment.credential_script.chmod(0o644)
        if replacement.exists():
            replacement.unlink()
        if opened.exists():
            opened.unlink()
        if release.exists():
            release.unlink()

    assert process.returncode == 0
    assert stdout == '{"command":"check","ok":true,"status":"ABSENT"}\n'
    assert "REPLACED" not in stdout
    assert stderr == ""


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
    assert source.startswith("#!/usr/bin/busybox sh\n")
    assert "exec /usr/bin/busybox env -i PATH=/usr/bin:/bin LC_ALL=C \\" in source
    assert '/usr/bin/bash -p -s -- "$@"' in source
    assert "expected_busybox_sha256=b3c1009e" in source
    assert "expected_python_sha256=c2afa8cc" in source
    assert "expected_repository_root=/home/minami/rakuten" in source
    assert "version_info = 3.14.6" in source
    assert "and sys.flags.no_site == 1" in source
    assert "if [[ $# -ne 1 || ( $1 != setup && $1 != check ) ]]" in source
    assert 'exec "$venv_python" -I -S - \\' in source
    assert "-perm /022" in source
    assert '! -uid "$effective_uid" ! -uid 0' in source
    assert "readlink_target_with_sentinel=$(" in source
    assert (
        "/usr/bin/readlink -n -- \"$venv_python\" 2>/dev/null && printf '\\034'"
        in source
    )
    assert (
        "[[ $readlink_target_with_sentinel == \"$expected_python\"$'\\034' ]]" in source
    )
    assert "os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC" in source
    assert "os.set_inheritable(script_descriptor, True)" in source
    assert 'f"/proc/self/fd/{script_descriptor}"' in source
    assert "os.execve(" in source
    assert '"LC_ALL": "C"' in source
    assert "sys.path == expected_path" in source
    for path_configuration_name in (
        "python._pth",
        "python3.14._pth",
        "libpython3.14._pth",
        "pybuilddir.txt",
    ):
        assert path_configuration_name in source
    for loader_namespace in ("glibc-hwcaps", "tls", "haswell", "avx512_1", "x86_64"):
        assert loader_namespace in source
    assert (
        '"$repository_root/scripts/rakuten_live_smoke_credentials.py" "$1"'
        not in source
    )
    assert '"$1"' in source
    for name in (
        "PYTHONPATH",
        "__PYVENV_LAUNCHER__",
        "RAKUTEN_WEB_SERVICE_APPLICATION_ID",
        "RAKUTEN_WEB_SERVICE_ACCESS_KEY",
        "RAKUTEN_AFFILIATE_ID",
        "HTTPS_PROXY",
        "SSLKEYLOGFILE",
        "LD_PRELOAD",
        "LD_AUDIT",
        "GLIBC_TUNABLES",
    ):
        assert "unset " in source and name in source
    assert "curl" not in source
    assert "wget" not in source
    credential_source = Path(credentials.__file__).read_text(encoding="utf-8")
    assert "__file__" not in credential_source


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

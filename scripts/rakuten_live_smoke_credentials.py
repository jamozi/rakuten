#!/usr/bin/env python3
"""Initialize or inspect the fixed local ST-0505 Rakuten credential store."""

from __future__ import annotations

import ctypes
from enum import Enum
import json
import os
from pathlib import Path
import resource
import select
import stat
import sys
import termios
import time
from typing import Any, Callable, Final, NoReturn, Sequence


EXPECTED_REPOSITORY_ROOT: Final = Path("/home/minami/rakuten")
SECRET_PARENT_NAME: Final = ".secrets"
SECRET_STORE_NAME: Final = "rakuten-live-smoke"
SECRET_STAGING_NAME: Final = ".rakuten-live-smoke.preparing"
SECRET_COMMITTING_NAME: Final = ".rakuten-live-smoke.committing"
SECRET_READY_NAME: Final = ".rakuten-live-smoke.ready"
SECRET_VALIDATING_NAME: Final = ".rakuten-live-smoke.validating"
SECRET_COMMITTED_NAME: Final = ".rakuten-live-smoke.committed"
APPLICATION_ID_ALIAS: Final = "rakuten_web_service_application_id"
ACCESS_KEY_ALIAS: Final = "rakuten_web_service_access_key"
SECRET_ALIASES: Final = (APPLICATION_ID_ALIAS, ACCESS_KEY_ALIAS)
# Linux N_TTY canonical input retains at most 4095 payload bytes before LF.
# Keep the accepted value below that boundary so an overlong submitted line is
# observed and rejected instead of being silently truncated by the line discipline.
MAX_SECRET_BYTES: Final = 4094
MAX_TTY_DISCARD_BYTES: Final = 4096
TTY_REJECT_DRAIN_TIMEOUT_SECONDS: Final = 1.0
EXPECTED_RUNTIME_PYTHON: Final = Path(
    "/home/minami/.local/share/uv/python/cpython-3.14.6-linux-x86_64-gnu/bin/python3.14"
)
EXPECTED_OS_RUNTIME_OBJECTS: Final = (
    Path("/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"),
    Path("/usr/lib/x86_64-linux-gnu/libc.so.6"),
    Path("/usr/lib/x86_64-linux-gnu/libdl.so.2"),
    Path("/usr/lib/x86_64-linux-gnu/libm.so.6"),
    Path("/usr/lib/x86_64-linux-gnu/libpthread.so.0"),
    Path("/usr/lib/x86_64-linux-gnu/librt.so.1"),
    Path("/usr/lib/x86_64-linux-gnu/libutil.so.1"),
)
MAX_RUNTIME_MAP_BYTES: Final = 262_144

_DIRECTORY_FLAGS: Final = (
    os.O_RDONLY
    | os.O_DIRECTORY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_TTY_FLAGS: Final = (
    os.O_RDWR
    | getattr(os, "O_NOCTTY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_WRITE_FLAGS: Final = (
    os.O_WRONLY
    | os.O_CREAT
    | os.O_EXCL
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_PR_GET_DUMPABLE: Final = 3
_PR_SET_DUMPABLE: Final = 4
_RENAME_NOREPLACE: Final = 1
_RUNTIME_SPECIAL_MAPPINGS: Final = frozenset({"[heap]", "[stack]", "[vdso]", "[vvar]"})
_RENAMEAT2: Callable[..., int] | None = None
_RUNTIME_LOCKED = False


class CredentialStoreStatus(str, Enum):
    """Closed metadata-only store states."""

    ABSENT = "ABSENT"
    READY = "READY"


class CredentialIntakeFailureCode(str, Enum):
    """Fixed value-free failure codes."""

    REPOSITORY_INVALID = "RAKUTEN_CREDENTIAL_REPOSITORY_INVALID"
    STORE_INVALID = "RAKUTEN_CREDENTIAL_STORE_INVALID"
    INPUT_UNAVAILABLE = "RAKUTEN_CREDENTIAL_INPUT_UNAVAILABLE"
    PLATFORM_UNSAFE = "RAKUTEN_CREDENTIAL_PLATFORM_UNSAFE"
    WRITE_FAILED = "RAKUTEN_CREDENTIAL_WRITE_FAILED"
    ARGUMENT_INVALID = "RAKUTEN_CREDENTIAL_ARGUMENT_INVALID"


class CredentialIntakeFailure(RuntimeError):
    """Sanitized credential-intake failure."""

    def __init__(self, code: CredentialIntakeFailureCode) -> None:
        self.code = code
        super().__init__(code.value)


def _fail(code: CredentialIntakeFailureCode) -> NoReturn:
    raise CredentialIntakeFailure(code)


def _set_cloexec(descriptor: int) -> None:
    try:
        os.set_inheritable(descriptor, False)
        if os.get_inheritable(descriptor):
            _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
    except OSError:
        _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)


def _require_no_symlink_ancestors(path: Path) -> None:
    if not path.is_absolute():
        _fail(CredentialIntakeFailureCode.REPOSITORY_INVALID)
    parts = path.parts
    current = Path(parts[0])
    for part in parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except OSError:
            _fail(CredentialIntakeFailureCode.REPOSITORY_INVALID)
        if stat.S_ISLNK(metadata.st_mode):
            _fail(CredentialIntakeFailureCode.REPOSITORY_INVALID)


def _physical_repository_root(value: object, expected_root: Path) -> Path:
    if not isinstance(value, Path) or not isinstance(expected_root, Path):
        _fail(CredentialIntakeFailureCode.REPOSITORY_INVALID)
    if (
        not value.is_absolute()
        or not expected_root.is_absolute()
        or value != expected_root
    ):
        _fail(CredentialIntakeFailureCode.REPOSITORY_INVALID)
    _require_no_symlink_ancestors(value)
    try:
        metadata = value.lstat()
    except OSError:
        _fail(CredentialIntakeFailureCode.REPOSITORY_INVALID)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_ISLNK(metadata.st_mode)
    ):
        _fail(CredentialIntakeFailureCode.REPOSITORY_INVALID)
    return value


def _open_directory(name: str | Path, *, dir_fd: int | None = None) -> int:
    descriptor: int | None = None
    try:
        descriptor = os.open(name, _DIRECTORY_FLAGS, dir_fd=dir_fd)
        _set_cloexec(descriptor)
        return descriptor
    except CredentialIntakeFailure:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise
    except BaseException:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        _fail(CredentialIntakeFailureCode.STORE_INVALID)


def _private_directory(metadata: os.stat_result) -> bool:
    return (
        stat.S_ISDIR(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode)
        and metadata.st_uid == os.geteuid()
        and stat.S_IMODE(metadata.st_mode) == 0o700
    )


def _private_file(metadata: os.stat_result) -> bool:
    return (
        stat.S_ISREG(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode)
        and metadata.st_uid == os.geteuid()
        and stat.S_IMODE(metadata.st_mode) == 0o600
        and metadata.st_nlink == 1
        and 2 <= metadata.st_size <= MAX_SECRET_BYTES + 1
    )


def _stat_child(parent_fd: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except BaseException:
        _fail(CredentialIntakeFailureCode.STORE_INVALID)


def _open_verified_child_directory(
    parent_fd: int, name: str, metadata: os.stat_result
) -> int:
    if not _private_directory(metadata):
        _fail(CredentialIntakeFailureCode.STORE_INVALID)
    descriptor = _open_directory(name, dir_fd=parent_fd)
    try:
        opened = os.fstat(descriptor)
    except BaseException:
        os.close(descriptor)
        _fail(CredentialIntakeFailureCode.STORE_INVALID)
    if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
        os.close(descriptor)
        _fail(CredentialIntakeFailureCode.STORE_INVALID)
    return descriptor


def inspect_store(
    repository_root: Path = EXPECTED_REPOSITORY_ROOT,
    *,
    expected_root: Path = EXPECTED_REPOSITORY_ROOT,
) -> CredentialStoreStatus:
    """Inspect only directory entries and metadata; never open secret files."""

    return _inspect_store_state(
        repository_root, expected_root=expected_root, allow_validating=False
    )


def _inspect_store_state(
    repository_root: Path,
    *,
    expected_root: Path,
    allow_validating: bool,
) -> CredentialStoreStatus:
    """Inspect the public state or the one internal precommit state."""

    root = _physical_repository_root(repository_root, expected_root)
    root_fd = _open_directory(root)
    try:
        secret_parent_metadata = _stat_child(root_fd, SECRET_PARENT_NAME)
        if secret_parent_metadata is None:
            return CredentialStoreStatus.ABSENT
        secret_parent_fd = _open_verified_child_directory(
            root_fd, SECRET_PARENT_NAME, secret_parent_metadata
        )
        try:
            if (
                _stat_child(secret_parent_fd, SECRET_STAGING_NAME) is not None
                or _stat_child(secret_parent_fd, SECRET_COMMITTING_NAME) is not None
            ):
                _fail(CredentialIntakeFailureCode.STORE_INVALID)
            store_metadata = _stat_child(secret_parent_fd, SECRET_STORE_NAME)
            ready_metadata = _stat_child(secret_parent_fd, SECRET_READY_NAME)
            validating_metadata = _stat_child(secret_parent_fd, SECRET_VALIDATING_NAME)
            committed_metadata = _stat_child(secret_parent_fd, SECRET_COMMITTED_NAME)
            if allow_validating:
                if validating_metadata is None or committed_metadata is not None:
                    _fail(CredentialIntakeFailureCode.STORE_INVALID)
                final_marker_name = SECRET_VALIDATING_NAME
                final_marker_metadata = validating_metadata
            else:
                if validating_metadata is not None:
                    _fail(CredentialIntakeFailureCode.STORE_INVALID)
                if (
                    store_metadata is None
                    and ready_metadata is None
                    and committed_metadata is None
                ):
                    return CredentialStoreStatus.ABSENT
                if committed_metadata is None:
                    _fail(CredentialIntakeFailureCode.STORE_INVALID)
                final_marker_name = SECRET_COMMITTED_NAME
                final_marker_metadata = committed_metadata
            if store_metadata is None or ready_metadata is None:
                _fail(CredentialIntakeFailureCode.STORE_INVALID)
            return _inspect_ready_metadata(
                secret_parent_fd,
                store_metadata,
                ready_metadata,
                final_marker_name,
                final_marker_metadata,
            )
        finally:
            os.close(secret_parent_fd)
    finally:
        os.close(root_fd)


def _inspect_empty_private_marker(
    secret_parent_fd: int, name: str, metadata: os.stat_result
) -> None:
    marker_fd = _open_verified_child_directory(secret_parent_fd, name, metadata)
    try:
        if os.listdir(marker_fd):
            _fail(CredentialIntakeFailureCode.STORE_INVALID)
    finally:
        os.close(marker_fd)


def _inspect_ready_metadata(
    secret_parent_fd: int,
    store_metadata: os.stat_result,
    ready_metadata: os.stat_result,
    final_marker_name: str,
    final_marker_metadata: os.stat_result,
) -> CredentialStoreStatus:
    _inspect_empty_private_marker(secret_parent_fd, SECRET_READY_NAME, ready_metadata)
    _inspect_empty_private_marker(
        secret_parent_fd, final_marker_name, final_marker_metadata
    )
    store_fd = _open_verified_child_directory(
        secret_parent_fd, SECRET_STORE_NAME, store_metadata
    )
    try:
        try:
            entries = tuple(sorted(os.listdir(store_fd)))
        except OSError:
            _fail(CredentialIntakeFailureCode.STORE_INVALID)
        if entries != tuple(sorted(SECRET_ALIASES)):
            _fail(CredentialIntakeFailureCode.STORE_INVALID)
        for alias in SECRET_ALIASES:
            metadata = _stat_child(store_fd, alias)
            if metadata is None or not _private_file(metadata):
                _fail(CredentialIntakeFailureCode.STORE_INVALID)
        return CredentialStoreStatus.READY
    finally:
        os.close(store_fd)


def _read_runtime_maps() -> bytes:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            "/proc/self/maps",
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
        _set_cloexec(descriptor)
        chunks = bytearray()
        while len(chunks) <= MAX_RUNTIME_MAP_BYTES:
            chunk = os.read(
                descriptor,
                min(8192, MAX_RUNTIME_MAP_BYTES + 1 - len(chunks)),
            )
            if not chunk:
                break
            chunks.extend(chunk)
        if not chunks or len(chunks) > MAX_RUNTIME_MAP_BYTES or chunks[-1:] != b"\n":
            _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
        return bytes(chunks)
    except CredentialIntakeFailure:
        raise
    except BaseException:
        _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _hexadecimal(value: bytes) -> bool:
    return bool(value) and all(byte in b"0123456789abcdefABCDEF" for byte in value)


def _parse_runtime_maps(
    raw: bytes,
) -> dict[str, tuple[tuple[int, int, int], bool]]:
    objects: dict[str, tuple[tuple[int, int, int], bool]] = {}
    for line in raw.splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) not in (5, 6):
            _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
        address, permissions, offset, device, inode = fields[:5]
        address_parts = address.split(b"-")
        device_parts = device.split(b":")
        if (
            len(address_parts) != 2
            or not all(_hexadecimal(part) for part in address_parts)
            or len(permissions) != 4
            or permissions[0] not in b"r-"
            or permissions[1] not in b"w-"
            or permissions[2] not in b"x-"
            or permissions[3] not in b"ps"
            or not _hexadecimal(offset)
            or len(device_parts) != 2
            or not all(_hexadecimal(part) for part in device_parts)
            or not inode.isdigit()
            or permissions[1:3] == b"wx"
        ):
            _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
        inode_value = int(inode, 10)
        identity = (
            int(device_parts[0], 16),
            int(device_parts[1], 16),
            inode_value,
        )
        if len(fields) == 5:
            if inode_value != 0 or permissions[2:3] == b"x":
                _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
            continue
        try:
            path = fields[5].decode("ascii")
        except UnicodeDecodeError:
            _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
        if path.startswith("["):
            if (
                path not in _RUNTIME_SPECIAL_MAPPINGS
                or inode_value != 0
                or device != b"00:00"
                or (permissions[2:3] == b"x" and path != "[vdso]")
            ):
                _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
            continue
        if not path.startswith("/") or inode_value == 0:
            _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
        executable = permissions[2:3] == b"x"
        existing = objects.get(path)
        if existing is None:
            objects[path] = (identity, executable)
        elif existing[0] != identity:
            _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
        elif executable and not existing[1]:
            objects[path] = (identity, True)
    return objects


def _secure_runtime_object(
    path: Path,
    identity: tuple[int, int, int],
    *,
    leaf_owner: int,
    ancestors_allow_current: bool,
) -> None:
    if not path.is_absolute() or path.parts[0] != "/":
        _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
    effective_uid = os.geteuid()
    current = Path("/")
    try:
        root_metadata = current.lstat()
        if (
            not stat.S_ISDIR(root_metadata.st_mode)
            or root_metadata.st_uid != 0
            or stat.S_IMODE(root_metadata.st_mode) & 0o022
        ):
            _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
        for part in path.parts[1:-1]:
            current /= part
            metadata = current.lstat()
            allowed_owners = {0, effective_uid} if ancestors_allow_current else {0}
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or metadata.st_uid not in allowed_owners
                or stat.S_IMODE(metadata.st_mode) & 0o022
            ):
                _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or before.st_uid != leaf_owner
            or stat.S_IMODE(before.st_mode) & 0o022
            or before.st_nlink != 1
            or (os.major(before.st_dev), os.minor(before.st_dev), before.st_ino)
            != identity
        ):
            _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            _set_cloexec(descriptor)
            opened = os.fstat(descriptor)
            current_metadata = path.lstat()
            opened_identity = (
                os.major(opened.st_dev),
                os.minor(opened.st_dev),
                opened.st_ino,
            )
            if (
                opened_identity != identity
                or (current_metadata.st_dev, current_metadata.st_ino)
                != (opened.st_dev, opened.st_ino)
                or not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != leaf_owner
                or stat.S_IMODE(opened.st_mode) & 0o022
                or opened.st_nlink != 1
            ):
                _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
        finally:
            os.close(descriptor)
    except CredentialIntakeFailure:
        raise
    except BaseException:
        _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)


def _validate_runtime_inventory(raw: bytes) -> None:
    effective_uid = os.geteuid()
    objects = _parse_runtime_maps(raw)
    expected_paths = {os.fspath(EXPECTED_RUNTIME_PYTHON)} | {
        os.fspath(path) for path in EXPECTED_OS_RUNTIME_OBJECTS
    }
    if set(objects) != expected_paths or tuple(os.listdir("/proc/self/task")) != (
        str(os.getpid()),
    ):
        _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
    if os.readlink("/proc/self/exe") != os.fspath(
        EXPECTED_RUNTIME_PYTHON
    ) or os.path.realpath(sys.executable) != os.fspath(EXPECTED_RUNTIME_PYTHON):
        _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
    for path_text, (identity, executable) in objects.items():
        path = Path(path_text)
        if not executable:
            _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
        if path == EXPECTED_RUNTIME_PYTHON:
            _secure_runtime_object(
                path,
                identity,
                leaf_owner=effective_uid,
                ancestors_allow_current=True,
            )
        else:
            _secure_runtime_object(
                path,
                identity,
                leaf_owner=0,
                ancestors_allow_current=False,
            )


def _runtime_audit_hook(event: str, arguments: tuple[object, ...]) -> None:
    del arguments
    if event == "import" or event in {"ctypes.dlopen", "ctypes.dlsym"}:
        _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)


def _freeze_runtime() -> None:
    global _RUNTIME_LOCKED
    if _RUNTIME_LOCKED:
        _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
    first = _read_runtime_maps()
    _validate_runtime_inventory(first)
    second = _read_runtime_maps()
    if second != first:
        _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
    sys.addaudithook(_runtime_audit_hook)
    _RUNTIME_LOCKED = True


def _assert_runtime_lock_intact() -> None:
    if not _RUNTIME_LOCKED:
        _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
    first = _read_runtime_maps()
    _validate_runtime_inventory(first)
    if _read_runtime_maps() != first:
        _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)


def _disable_process_disclosure(
    *, runtime_lock: Callable[[], None] = _freeze_runtime
) -> None:
    global _RENAMEAT2
    if sys.platform != "linux" or not hasattr(resource, "RLIMIT_CORE"):
        _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        if resource.getrlimit(resource.RLIMIT_CORE) != (0, 0):
            _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
        libc = ctypes.CDLL(None, use_errno=True)
        prctl = libc.prctl
        prctl.restype = ctypes.c_int
        prctl.argtypes = [
            ctypes.c_int,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_ulong,
        ]
        renameat2 = libc.renameat2
        renameat2.restype = ctypes.c_int
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        if prctl(_PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
            _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
        if prctl(_PR_GET_DUMPABLE, 0, 0, 0, 0) != 0:
            _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)
        _RENAMEAT2 = renameat2
        runtime_lock()
    except CredentialIntakeFailure:
        raise
    except BaseException:
        _fail(CredentialIntakeFailureCode.PLATFORM_UNSAFE)


def _read_private_tty(prompt: str) -> bytearray:
    if type(prompt) is not str or not prompt or not prompt.isascii():
        _fail(CredentialIntakeFailureCode.INPUT_UNAVAILABLE)
    descriptor: int | None = None
    original: list[Any] | None = None
    value = bytearray()
    completed = False
    restore_failed = False
    rejected = False
    discarded = 0
    drain_deadline: float | None = None
    hidden_restore_required = False
    try:
        descriptor = os.open("/dev/tty", _TTY_FLAGS)
        _set_cloexec(descriptor)
        if not stat.S_ISCHR(os.fstat(descriptor).st_mode):
            _fail(CredentialIntakeFailureCode.INPUT_UNAVAILABLE)
        original = termios.tcgetattr(descriptor)
        if int(original[3]) & termios.ICANON == 0:
            _fail(CredentialIntakeFailureCode.INPUT_UNAVAILABLE)
        hidden = original.copy()
        hidden[3] = int(hidden[3]) & ~(termios.ECHO | getattr(termios, "ECHONL", 0))
        hidden_restore_required = True
        termios.tcsetattr(descriptor, termios.TCSANOW, hidden)
        prompt_bytes = prompt.encode("ascii")
        offset = 0
        while offset < len(prompt_bytes):
            written = os.write(descriptor, prompt_bytes[offset:])
            if written <= 0:
                _fail(CredentialIntakeFailureCode.INPUT_UNAVAILABLE)
            offset += written
        while True:
            if rejected:
                try:
                    if drain_deadline is None:
                        raise RuntimeError("missing rejected-line deadline")
                    remaining = drain_deadline - time.monotonic()
                    if remaining <= 0:
                        _fail(CredentialIntakeFailureCode.INPUT_UNAVAILABLE)
                    readable, _, _ = select.select([descriptor], [], [], remaining)
                    if readable != [descriptor]:
                        _fail(CredentialIntakeFailureCode.INPUT_UNAVAILABLE)
                except CredentialIntakeFailure:
                    raise
                except BaseException:
                    raise
            try:
                chunk = os.read(descriptor, 1)
            except BaseException:
                raise
            if not chunk:
                _fail(CredentialIntakeFailureCode.INPUT_UNAVAILABLE)
            if chunk == b"\n":
                break
            if rejected:
                discarded += len(chunk)
                if discarded >= MAX_TTY_DISCARD_BYTES:
                    _fail(CredentialIntakeFailureCode.INPUT_UNAVAILABLE)
                continue
            if (
                chunk == b"\r"
                or chunk[0] < 0x20
                or chunk[0] == 0x7F
                or len(value) >= MAX_SECRET_BYTES
            ):
                rejected = True
                _wipe(value)
                value.clear()
                try:
                    os.set_blocking(descriptor, False)
                    drain_deadline = time.monotonic() + TTY_REJECT_DRAIN_TIMEOUT_SECONDS
                except BaseException:
                    raise
                continue
            value.extend(chunk)
        if rejected or not value:
            _fail(CredentialIntakeFailureCode.INPUT_UNAVAILABLE)
        completed = True
        return value
    except CredentialIntakeFailure:
        raise
    except BaseException:
        _fail(CredentialIntakeFailureCode.INPUT_UNAVAILABLE)
    finally:
        if descriptor is not None:
            if original is not None:
                try:
                    termios.tcsetattr(
                        descriptor,
                        (
                            termios.TCSAFLUSH
                            if hidden_restore_required
                            else termios.TCSANOW
                        ),
                        original,
                    )
                except BaseException:
                    restore_failed = True
            try:
                os.write(descriptor, b"\n")
            except BaseException:
                pass
            try:
                os.close(descriptor)
            except BaseException:
                pass
        if not completed or restore_failed:
            _wipe(value)
        if restore_failed:
            _fail(CredentialIntakeFailureCode.INPUT_UNAVAILABLE)


def _wipe(value: bytearray | None) -> None:
    if value is not None:
        for index in range(len(value)):
            value[index] = 0


def _mkdir_private(parent_fd: int, name: str) -> int:
    descriptor: int | None = None
    try:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not _private_directory(metadata):
            _fail(CredentialIntakeFailureCode.WRITE_FAILED)
        os.fsync(parent_fd)
        descriptor = _open_verified_child_directory(parent_fd, name, metadata)
        return descriptor
    except CredentialIntakeFailure:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise
    except BaseException:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        _fail(CredentialIntakeFailureCode.WRITE_FAILED)


def _write_secret(store_fd: int, name: str, value: bytearray) -> None:
    descriptor: int | None = None
    try:
        descriptor = os.open(name, _WRITE_FLAGS, 0o600, dir_fd=store_fd)
        _set_cloexec(descriptor)
        metadata = os.fstat(descriptor)
        if not _private_file_for_new_write(metadata):
            _fail(CredentialIntakeFailureCode.WRITE_FAILED)
        view = memoryview(value)
        offset = 0
        while offset < len(view):
            written = os.write(descriptor, view[offset:])
            if written <= 0:
                _fail(CredentialIntakeFailureCode.WRITE_FAILED)
            offset += written
        if os.write(descriptor, b"\n") != 1:
            _fail(CredentialIntakeFailureCode.WRITE_FAILED)
        os.fsync(descriptor)
        os.fsync(store_fd)
    except CredentialIntakeFailure:
        raise
    except BaseException:
        _fail(CredentialIntakeFailureCode.WRITE_FAILED)
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _private_file_for_new_write(metadata: os.stat_result) -> bool:
    return (
        stat.S_ISREG(metadata.st_mode)
        and metadata.st_uid == os.geteuid()
        and stat.S_IMODE(metadata.st_mode) == 0o600
        and metadata.st_nlink == 1
        and metadata.st_size == 0
    )


def _rename_noreplace(secret_parent_fd: int, source: str, target: str) -> None:
    if (source, target) not in {
        (SECRET_STAGING_NAME, SECRET_STORE_NAME),
        (SECRET_COMMITTING_NAME, SECRET_READY_NAME),
        (SECRET_VALIDATING_NAME, SECRET_COMMITTED_NAME),
    }:
        _fail(CredentialIntakeFailureCode.WRITE_FAILED)
    try:
        renameat2 = _RENAMEAT2
        if renameat2 is None or not _RUNTIME_LOCKED:
            _fail(CredentialIntakeFailureCode.WRITE_FAILED)
        result = renameat2(
            secret_parent_fd,
            source.encode("ascii"),
            secret_parent_fd,
            target.encode("ascii"),
            _RENAME_NOREPLACE,
        )
    except BaseException:
        _fail(CredentialIntakeFailureCode.WRITE_FAILED)
    if result != 0:
        _fail(CredentialIntakeFailureCode.WRITE_FAILED)


def _create_pair(repository_root: Path, values: tuple[bytearray, bytearray]) -> None:
    root_fd = _open_directory(repository_root)
    secret_parent_fd: int | None = None
    store_fd: int | None = None
    committing_fd: int | None = None
    validating_fd: int | None = None
    try:
        parent_metadata = _stat_child(root_fd, SECRET_PARENT_NAME)
        if parent_metadata is None:
            secret_parent_fd = _mkdir_private(root_fd, SECRET_PARENT_NAME)
        else:
            secret_parent_fd = _open_verified_child_directory(
                root_fd, SECRET_PARENT_NAME, parent_metadata
            )
        store_metadata = _stat_child(secret_parent_fd, SECRET_STORE_NAME)
        staging_metadata = _stat_child(secret_parent_fd, SECRET_STAGING_NAME)
        committing_metadata = _stat_child(secret_parent_fd, SECRET_COMMITTING_NAME)
        ready_metadata = _stat_child(secret_parent_fd, SECRET_READY_NAME)
        validating_metadata = _stat_child(secret_parent_fd, SECRET_VALIDATING_NAME)
        committed_metadata = _stat_child(secret_parent_fd, SECRET_COMMITTED_NAME)
        if any(
            metadata is not None
            for metadata in (
                store_metadata,
                staging_metadata,
                committing_metadata,
                ready_metadata,
                validating_metadata,
                committed_metadata,
            )
        ):
            _fail(CredentialIntakeFailureCode.WRITE_FAILED)
        committing_fd = _mkdir_private(secret_parent_fd, SECRET_COMMITTING_NAME)
        validating_fd = _mkdir_private(secret_parent_fd, SECRET_VALIDATING_NAME)
        store_fd = _mkdir_private(secret_parent_fd, SECRET_STAGING_NAME)
        if os.listdir(store_fd):
            _fail(CredentialIntakeFailureCode.WRITE_FAILED)
        for alias, value in zip(SECRET_ALIASES, values, strict=True):
            _write_secret(store_fd, alias, value)
        os.fsync(store_fd)
        os.fsync(secret_parent_fd)
        staging_identity = os.fstat(store_fd)
        _rename_noreplace(secret_parent_fd, SECRET_STAGING_NAME, SECRET_STORE_NAME)
        published_identity = os.fstat(store_fd)
        final_metadata = _stat_child(secret_parent_fd, SECRET_STORE_NAME)
        if (
            final_metadata is None
            or not _private_directory(final_metadata)
            or (final_metadata.st_dev, final_metadata.st_ino)
            != (staging_identity.st_dev, staging_identity.st_ino)
            or (published_identity.st_dev, published_identity.st_ino)
            != (staging_identity.st_dev, staging_identity.st_ino)
        ):
            _fail(CredentialIntakeFailureCode.WRITE_FAILED)
        if tuple(sorted(os.listdir(store_fd))) != tuple(sorted(SECRET_ALIASES)):
            _fail(CredentialIntakeFailureCode.WRITE_FAILED)
        os.fsync(secret_parent_fd)
        committing_identity = os.fstat(committing_fd)
        _rename_noreplace(secret_parent_fd, SECRET_COMMITTING_NAME, SECRET_READY_NAME)
        published_ready_identity = os.fstat(committing_fd)
        ready_metadata = _stat_child(secret_parent_fd, SECRET_READY_NAME)
        if (
            ready_metadata is None
            or not _private_directory(ready_metadata)
            or (ready_metadata.st_dev, ready_metadata.st_ino)
            != (committing_identity.st_dev, committing_identity.st_ino)
            or (published_ready_identity.st_dev, published_ready_identity.st_ino)
            != (committing_identity.st_dev, committing_identity.st_ino)
        ):
            _fail(CredentialIntakeFailureCode.WRITE_FAILED)
        os.fsync(secret_parent_fd)
        if (
            _inspect_store_state(
                repository_root,
                expected_root=repository_root,
                allow_validating=True,
            )
            is not CredentialStoreStatus.READY
        ):
            _fail(CredentialIntakeFailureCode.WRITE_FAILED)
        validating_identity = os.fstat(validating_fd)
        validating_metadata = _stat_child(secret_parent_fd, SECRET_VALIDATING_NAME)
        if (
            validating_metadata is None
            or not _private_directory(validating_metadata)
            or (validating_metadata.st_dev, validating_metadata.st_ino)
            != (validating_identity.st_dev, validating_identity.st_ino)
        ):
            _fail(CredentialIntakeFailureCode.WRITE_FAILED)
        _rename_noreplace(
            secret_parent_fd, SECRET_VALIDATING_NAME, SECRET_COMMITTED_NAME
        )
    except BaseException as exc:
        if isinstance(exc, CredentialIntakeFailure):
            raise
        _fail(CredentialIntakeFailureCode.WRITE_FAILED)
    finally:
        if store_fd is not None:
            try:
                os.close(store_fd)
            except OSError:
                pass
        if committing_fd is not None:
            try:
                os.close(committing_fd)
            except OSError:
                pass
        if validating_fd is not None:
            try:
                os.close(validating_fd)
            except OSError:
                pass
        if secret_parent_fd is not None:
            try:
                os.close(secret_parent_fd)
            except OSError:
                pass
        try:
            os.close(root_fd)
        except OSError:
            pass


def setup_store(
    repository_root: Path = EXPECTED_REPOSITORY_ROOT,
    *,
    expected_root: Path = EXPECTED_REPOSITORY_ROOT,
    reader: Callable[[str], bytearray] = _read_private_tty,
    disclosure_guard: Callable[[], None] = _disable_process_disclosure,
) -> CredentialStoreStatus:
    """Initialize the exact pair once, or return metadata-only READY."""

    root = _physical_repository_root(repository_root, expected_root)
    existing = inspect_store(root, expected_root=expected_root)
    if existing is CredentialStoreStatus.READY:
        return existing
    disclosure_guard()
    application_id: bytearray | None = None
    access_material: bytearray | None = None
    try:
        application_id = _read_value(reader, "Rakuten application ID: ")
        access_material = _read_value(reader, "Rakuten access key: ")
        _create_pair(root, (application_id, access_material))
        return CredentialStoreStatus.READY
    except CredentialIntakeFailure:
        raise
    except BaseException:
        _fail(CredentialIntakeFailureCode.WRITE_FAILED)
    finally:
        _wipe(application_id)
        _wipe(access_material)


def _read_value(reader: Callable[[str], bytearray], prompt: str) -> bytearray:
    try:
        if reader is _read_private_tty:
            _assert_runtime_lock_intact()
        value = reader(prompt)
    except CredentialIntakeFailure:
        raise
    except BaseException:
        _fail(CredentialIntakeFailureCode.INPUT_UNAVAILABLE)
    invalid = (
        type(value) is not bytearray
        or not value
        or len(value) > MAX_SECRET_BYTES
        or any(byte < 0x20 or byte == 0x7F for byte in value)
    )
    if invalid:
        if type(value) is bytearray:
            _wipe(value)
        _fail(CredentialIntakeFailureCode.INPUT_UNAVAILABLE)
    return value


def _receipt(command: str, status: CredentialStoreStatus) -> str:
    return json.dumps(
        {"command": command, "ok": True, "status": status.value},
        separators=(",", ":"),
        sort_keys=True,
    )


def _failure_receipt(command: str, code: CredentialIntakeFailureCode) -> str:
    return json.dumps(
        {
            "command": command,
            "ok": False,
            "reason_code": code.value,
            "status": "INVALID",
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def parse_args(argv: Sequence[str] | None = None) -> str:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments not in (["setup"], ["check"]):
        _fail(CredentialIntakeFailureCode.ARGUMENT_INVALID)
    return arguments[0]


def main(
    argv: Sequence[str] | None = None,
    *,
    repository_root: Path = EXPECTED_REPOSITORY_ROOT,
    expected_root: Path = EXPECTED_REPOSITORY_ROOT,
    reader: Callable[[str], bytearray] = _read_private_tty,
    disclosure_guard: Callable[[], None] = _disable_process_disclosure,
) -> int:
    command = "invalid"
    previous_umask = os.umask(0o077)
    try:
        command = parse_args(argv)
        status = (
            setup_store(
                repository_root,
                expected_root=expected_root,
                reader=reader,
                disclosure_guard=disclosure_guard,
            )
            if command == "setup"
            else inspect_store(repository_root, expected_root=expected_root)
        )
    except CredentialIntakeFailure as exc:
        print(_failure_receipt(command, exc.code))
        return 1
    finally:
        os.umask(previous_umask)
    print(_receipt(command, status))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

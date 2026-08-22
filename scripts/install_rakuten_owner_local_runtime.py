#!/usr/bin/env python3
"""Install the reviewed ST-0505 owner-local runtime outside the repository."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import uuid


REPOSITORY_ROOT = Path("/home/minami/rakuten")
OWNER_BASE = Path("/home/minami/.local/share")
REVIEWED_INSTALLER_PATH = (
    REPOSITORY_ROOT / "scripts/install_rakuten_owner_local_runtime.py"
)
REVIEWED_SYSTEM_PYTHON = Path("/usr/bin/python3.10")
EXPECTED_SYSTEM_PYTHON_SHA256 = (
    "7d51cd6b48b521277f5caa4610a82126e315fa2be4df069823a8b1eeb5bd4a86"
)
EXPECTED_BUNDLE_SHA256 = (
    "305ca66b8453a526395641a3cc1e535ac887283608fd94d5a433d7f15ba672ed"
)
INSTALLED = "RAKUTEN_OWNER_LOCAL_RUNTIME_INSTALLED"
ALREADY_INSTALLED = "RAKUTEN_OWNER_LOCAL_RUNTIME_ALREADY_INSTALLED"
INSTALL_FAILED = "RAKUTEN_OWNER_LOCAL_RUNTIME_INSTALL_FAILED"
_MANIFEST_NAME = "runtime-manifest.v1.json"
_MAX_SOURCE_BYTES = 2 * 1024 * 1024
_MAX_RUNTIME_BINARY_BYTES = 16 * 1024 * 1024
_INSTALL_STAGE_PYTHON_FD = 5
_INSTALL_STAGE_SOURCE_FD = 6
_INSTALL_STAGE_PYTHON_ENTRY = f"/proc/self/fd/{_INSTALL_STAGE_PYTHON_FD}"
_INSTALL_STAGE_SOURCE_ENTRY = f"/proc/self/fd/{_INSTALL_STAGE_SOURCE_FD}"
_RENAME_NOREPLACE = 1
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
_FILE_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
_PAYLOADS = (
    ("scripts/rakuten_owner_local_launcher.sh", "bin/rakuten-owner-local", 0o500),
    ("scripts/rakuten_owner_local.py", "scripts/rakuten_owner_local.py", 0o400),
    ("python/raos/__init__.py", "python/raos/__init__.py", 0o400),
    (
        "python/raos/domain/catalog/rakuten_item_search.py",
        "python/raos/domain/catalog/rakuten_item_search.py",
        0o400,
    ),
    (
        "python/raos/domain/catalog/rakuten_item_search_live_request_v1.py",
        "python/raos/domain/catalog/rakuten_item_search_live_request_v1.py",
        0o400,
    ),
    (
        "python/raos/domain/catalog/rakuten_owner_local.py",
        "python/raos/domain/catalog/rakuten_owner_local.py",
        0o400,
    ),
    (
        "python/raos/application/catalog/rakuten_owner_local.py",
        "python/raos/application/catalog/rakuten_owner_local.py",
        0o400,
    ),
    (
        "python/raos/ports/rakuten_owner_local.py",
        "python/raos/ports/rakuten_owner_local.py",
        0o400,
    ),
    (
        "python/raos/adapters/rakuten_owner_local.py",
        "python/raos/adapters/rakuten_owner_local.py",
        0o400,
    ),
)


class RuntimeInstallError(RuntimeError):
    pass


def _fail() -> None:
    raise RuntimeInstallError(INSTALL_FAILED) from None


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_mode == right.st_mode
        and left.st_uid == right.st_uid
    )


def _sha256_fd(descriptor: int, maximum_bytes: int) -> str:
    before = os.fstat(descriptor)
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_size < 1
        or before.st_size > maximum_bytes
    ):
        _fail()
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    remaining = maximum_bytes + 1
    total = 0
    while remaining:
        chunk = os.read(descriptor, min(64 * 1024, remaining))
        if not chunk:
            break
        digest.update(chunk)
        total += len(chunk)
        remaining -= len(chunk)
    after = os.fstat(descriptor)
    os.lseek(descriptor, 0, os.SEEK_SET)
    if total != before.st_size or not _same_identity(before, after):
        _fail()
    return digest.hexdigest()


def _validate_authenticated_bootstrap() -> None:
    if (
        sys.flags.isolated != 1
        or sys.flags.no_site != 1
        or sys.flags.dont_write_bytecode != 1
        or sys.flags.ignore_environment != 1
        or sys.version_info[:3] != (3, 10, 12)
        or sys.executable != _INSTALL_STAGE_PYTHON_ENTRY
        or getattr(sys, "_base_executable", None) != _INSTALL_STAGE_PYTHON_ENTRY
        or sys.prefix != "/usr"
        or sys.base_prefix != "/usr"
        or sys.path
        != [
            "/usr/lib/python310.zip",
            "/usr/lib/python3.10",
            "/usr/lib/python3.10/lib-dynload",
        ]
        or os.geteuid() != os.getuid()
        or __file__ != _INSTALL_STAGE_SOURCE_ENTRY
    ):
        _fail()

    python_details = os.fstat(_INSTALL_STAGE_PYTHON_FD)
    python_entry = os.stat(_INSTALL_STAGE_PYTHON_ENTRY)
    python_named = os.stat(REVIEWED_SYSTEM_PYTHON, follow_symlinks=False)
    if (
        not os.get_inheritable(_INSTALL_STAGE_PYTHON_FD)
        or not _same_identity(python_details, python_entry)
        or not _same_identity(python_entry, python_named)
        or not stat.S_ISREG(python_details.st_mode)
        or python_details.st_uid != 0
        or stat.S_IMODE(python_details.st_mode) != 0o755
        or python_details.st_nlink != 1
        or _sha256_fd(_INSTALL_STAGE_PYTHON_FD, _MAX_RUNTIME_BINARY_BYTES)
        != EXPECTED_SYSTEM_PYTHON_SHA256
    ):
        _fail()

    source_details = os.fstat(_INSTALL_STAGE_SOURCE_FD)
    source_entry = os.stat(_INSTALL_STAGE_SOURCE_ENTRY)
    source_named = os.stat(REVIEWED_INSTALLER_PATH, follow_symlinks=False)
    if (
        not os.get_inheritable(_INSTALL_STAGE_SOURCE_FD)
        or not _same_identity(source_details, source_entry)
        or not _same_identity(source_entry, source_named)
        or not stat.S_ISREG(source_details.st_mode)
        or source_details.st_uid != os.getuid()
        or stat.S_IMODE(source_details.st_mode) & 0o022 != 0
        or source_details.st_nlink != 1
        or source_details.st_size < 1
        or source_details.st_size > _MAX_SOURCE_BYTES
    ):
        _fail()

    os.close(_INSTALL_STAGE_PYTHON_FD)
    os.close(_INSTALL_STAGE_SOURCE_FD)


def _open_absolute_directory(path: Path) -> int:
    if not path.is_absolute() or any(
        part in {"", ".", ".."} for part in path.parts[1:]
    ):
        _fail()
    current = os.open("/", _DIRECTORY_FLAGS)
    try:
        for component in path.parts[1:]:
            following = os.open(component, _DIRECTORY_FLAGS, dir_fd=current)
            details = os.fstat(following)
            named = os.stat(component, dir_fd=current, follow_symlinks=False)
            if not _same_identity(details, named) or not stat.S_ISDIR(details.st_mode):
                os.close(following)
                _fail()
            os.close(current)
            current = following
        return current
    except BaseException:
        os.close(current)
        raise


def _private_directory(parent_fd: int, name: str, *, create: bool) -> int:
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
            os.fsync(parent_fd)
        except FileExistsError:
            pass
    child = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    details = os.fstat(child)
    named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if (
        not _same_identity(details, named)
        or not stat.S_ISDIR(details.st_mode)
        or details.st_uid != os.getuid()
        or stat.S_IMODE(details.st_mode) != 0o700
    ):
        os.close(child)
        _fail()
    return child


def _read_relative(root_fd: int, relative: str, *, installed_mode: int | None) -> bytes:
    parts = relative.split("/")
    if not parts or any(part in {"", ".", ".."} for part in parts):
        _fail()
    current = os.dup(root_fd)
    try:
        for component in parts[:-1]:
            following = os.open(component, _DIRECTORY_FLAGS, dir_fd=current)
            details = os.fstat(following)
            named = os.stat(component, dir_fd=current, follow_symlinks=False)
            if not _same_identity(details, named) or not stat.S_ISDIR(details.st_mode):
                os.close(following)
                _fail()
            if installed_mode is not None and (
                details.st_uid != os.getuid() or stat.S_IMODE(details.st_mode) != 0o700
            ):
                os.close(following)
                _fail()
            os.close(current)
            current = following
        descriptor = os.open(parts[-1], _FILE_FLAGS, dir_fd=current)
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.getuid()
                or before.st_nlink != 1
                or before.st_size < 0
                or before.st_size > _MAX_SOURCE_BYTES
                or (
                    installed_mode is None and stat.S_IMODE(before.st_mode) & 0o022 != 0
                )
                or (
                    installed_mode is not None
                    and stat.S_IMODE(before.st_mode) != installed_mode
                )
            ):
                _fail()
            remaining = _MAX_SOURCE_BYTES + 1
            chunks: list[bytes] = []
            while remaining:
                chunk = os.read(descriptor, min(remaining, 64 * 1024))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
            after = os.fstat(descriptor)
            named = os.stat(parts[-1], dir_fd=current, follow_symlinks=False)
            if (
                len(payload) > _MAX_SOURCE_BYTES
                or len(payload) != before.st_size
                or not _same_identity(before, after)
                or not _same_identity(after, named)
                or after.st_size != before.st_size
            ):
                _fail()
            return payload
        finally:
            os.close(descriptor)
    finally:
        os.close(current)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def _payload_rows(source_fd: int) -> tuple[list[dict[str, str]], dict[str, bytes]]:
    rows: list[dict[str, str]] = []
    payloads: dict[str, bytes] = {}
    for source, installed, mode in _PAYLOADS:
        payload = _read_relative(source_fd, source, installed_mode=None)
        payloads[installed] = payload
        rows.append(
            {
                "path": installed,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "mode": f"{mode:04o}",
            }
        )
    return rows, payloads


def _open_or_create_stage_directory(root_fd: int, relative: str) -> int:
    current = os.dup(root_fd)
    try:
        for component in relative.split("/"):
            following = _private_directory(current, component, create=True)
            os.close(current)
            current = following
        return current
    except BaseException:
        os.close(current)
        raise


def _write_file(root_fd: int, relative: str, payload: bytes, mode: int) -> None:
    parent, separator, name = relative.rpartition("/")
    if not separator:
        parent_fd = os.dup(root_fd)
    else:
        parent_fd = _open_or_create_stage_directory(root_fd, parent)
    descriptor = -1
    try:
        descriptor = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            mode,
            dir_fd=parent_fd,
        )
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                _fail()
            offset += written
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
        details = os.fstat(descriptor)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.getuid()
            or stat.S_IMODE(details.st_mode) != mode
            or details.st_nlink != 1
            or details.st_size != len(payload)
        ):
            _fail()
        os.fsync(parent_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_fd)


def _expected_children(paths: set[str], prefix: str) -> set[str]:
    children: set[str] = set()
    boundary = f"{prefix}/" if prefix else ""
    for path in paths:
        if path.startswith(boundary):
            remainder = path[len(boundary) :]
            children.add(remainder.split("/", 1)[0])
    return children


def _validate_inventory(directory_fd: int, paths: set[str], prefix: str = "") -> None:
    if set(os.listdir(directory_fd)) != _expected_children(paths, prefix):
        _fail()
    boundary = f"{prefix}/" if prefix else ""
    relevant = (
        item[len(boundary) :]
        for item in paths
        if not prefix or item.startswith(boundary)
    )
    child_directories = {path.split("/", 1)[0] for path in relevant if "/" in path}
    for name in child_directories:
        child = _private_directory(directory_fd, name, create=False)
        try:
            child_prefix = f"{prefix}/{name}" if prefix else name
            _validate_inventory(child, paths, child_prefix)
        finally:
            os.close(child)


def _validate_bundle(
    runtime_fd: int,
    bundle: str,
    rows: list[dict[str, str]],
    payloads: dict[str, bytes],
) -> None:
    bundle_fd = _private_directory(runtime_fd, bundle, create=False)
    try:
        expected_paths = {row["path"] for row in rows} | {_MANIFEST_NAME}
        _validate_inventory(bundle_fd, expected_paths)
        expected_manifest = (
            _canonical(
                {
                    "schema": "RAOS_ST0505_OWNER_LOCAL_INSTALLED_RUNTIME_V1",
                    "version": 1,
                    "bundle_sha256": bundle,
                    "files": rows,
                }
            )
            + b"\n"
        )
        if (
            _read_relative(bundle_fd, _MANIFEST_NAME, installed_mode=0o400)
            != expected_manifest
        ):
            _fail()
        for row in rows:
            mode = int(row["mode"], 8)
            actual = _read_relative(bundle_fd, row["path"], installed_mode=mode)
            if actual != payloads[row["path"]]:
                _fail()
    finally:
        os.close(bundle_fd)


def _rename_noreplace(directory_fd: int, source: str, target: str) -> None:
    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except AttributeError:
        _fail()
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    result = renameat2(
        directory_fd,
        os.fsencode(source),
        directory_fd,
        os.fsencode(target),
        _RENAME_NOREPLACE,
    )
    if result != 0:
        error_number = ctypes.get_errno()
        if error_number == errno.EEXIST:
            raise FileExistsError(error_number, "runtime already installed")
        _fail()


def _remove_stage(runtime_path: Path, stage_name: str) -> None:
    stage = runtime_path / stage_name
    try:
        details = stage.lstat()
    except FileNotFoundError:
        return
    if (
        not stage_name.startswith(".install-")
        or not stat.S_ISDIR(details.st_mode)
        or stat.S_ISLNK(details.st_mode)
        or details.st_uid != os.getuid()
    ):
        _fail()
    shutil.rmtree(stage)


def install(
    repository_root: Path,
    owner_base: Path,
    expected_bundle_sha256: str,
) -> str:
    source_fd = _open_absolute_directory(repository_root)
    owner_base_fd = _open_absolute_directory(owner_base)
    runtime_fd = -1
    stage_fd = -1
    stage_name = ""
    runtime_path = owner_base / "raos" / "rakuten-owner-local" / "runtime"
    try:
        rows, payloads = _payload_rows(source_fd)
        bundle = hashlib.sha256(_canonical(rows)).hexdigest()
        if bundle != expected_bundle_sha256:
            _fail()
        current = owner_base_fd
        owner_base_fd = -1
        for component in ("raos", "rakuten-owner-local", "runtime"):
            following = _private_directory(current, component, create=True)
            os.close(current)
            current = following
        runtime_fd = current
        try:
            _validate_bundle(runtime_fd, bundle, rows, payloads)
        except FileNotFoundError:
            pass
        else:
            return ALREADY_INSTALLED
        stage_name = f".install-{uuid.uuid4().hex}"
        os.mkdir(stage_name, 0o700, dir_fd=runtime_fd)
        stage_fd = _private_directory(runtime_fd, stage_name, create=False)
        for row in rows:
            _write_file(
                stage_fd,
                row["path"],
                payloads[row["path"]],
                int(row["mode"], 8),
            )
        manifest = (
            _canonical(
                {
                    "schema": "RAOS_ST0505_OWNER_LOCAL_INSTALLED_RUNTIME_V1",
                    "version": 1,
                    "bundle_sha256": bundle,
                    "files": rows,
                }
            )
            + b"\n"
        )
        _write_file(stage_fd, _MANIFEST_NAME, manifest, 0o400)
        os.fsync(stage_fd)
        before = os.fstat(stage_fd)
        os.close(stage_fd)
        stage_fd = -1
        try:
            _rename_noreplace(runtime_fd, stage_name, bundle)
        except FileExistsError:
            _remove_stage(runtime_path, stage_name)
            stage_name = ""
            _validate_bundle(runtime_fd, bundle, rows, payloads)
            os.fsync(runtime_fd)
            _validate_bundle(runtime_fd, bundle, rows, payloads)
            return ALREADY_INSTALLED
        stage_name = ""
        named = os.stat(bundle, dir_fd=runtime_fd, follow_symlinks=False)
        if not _same_identity(before, named):
            _fail()
        os.fsync(runtime_fd)
        _validate_bundle(runtime_fd, bundle, rows, payloads)
        return INSTALLED
    except RuntimeInstallError:
        raise RuntimeInstallError(INSTALL_FAILED) from None
    except OSError:
        raise RuntimeInstallError(INSTALL_FAILED) from None
    except ValueError:
        raise RuntimeInstallError(INSTALL_FAILED) from None
    except TypeError:
        raise RuntimeInstallError(INSTALL_FAILED) from None
    finally:
        if stage_fd >= 0:
            os.close(stage_fd)
        if stage_name and runtime_fd >= 0:
            _remove_stage(runtime_path, stage_name)
        if runtime_fd >= 0:
            os.close(runtime_fd)
        if owner_base_fd >= 0:
            os.close(owner_base_fd)
        os.close(source_fd)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments:
        print(INSTALL_FAILED)
        return 2
    try:
        _validate_authenticated_bootstrap()
        result = install(REPOSITORY_ROOT, OWNER_BASE, EXPECTED_BUNDLE_SHA256)
    except BaseException:
        print(INSTALL_FAILED)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

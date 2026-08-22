#!/usr/bin/env python3
"""Generate/check the reviewed ST-1703 self-hosted runtime inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
from typing import Final, NoReturn


ROOT: Final = Path(__file__).resolve().parents[1]
OUTPUT_PATH: Final = (
    ROOT / "changes/st-1703/self-hosted-minimum-start-v1/runtime-manifest.v1.json"
)
PYTHON_RUNTIME_INVENTORY_PATH: Final = (
    ROOT / "changes/st-1703/self-hosted-minimum-start-v1/"
    "python-runtime-code-inventory.v1.sha256"
)
PYTHON_BASE: Final = Path(
    "/home/minami/.local/share/uv/python/cpython-3.14.6-linux-x86_64-gnu"
)
PYTHON_STDLIB_ROOT: Final = PYTHON_BASE / "lib/python3.14"
PYTHON_EXECUTABLE: Final = PYTHON_BASE / "bin/python3.14"
PYTHON_BIN_DIRECTORY: Final = PYTHON_BASE / "bin"
PYTHON_ZIP_PATH: Final = PYTHON_BASE / "lib/python314.zip"
PYVENV_CONFIG: Final = Path("/home/minami/rakuten/.venv/pyvenv.cfg")
VENV_BIN_DIRECTORY: Final = Path("/home/minami/rakuten/.venv/bin")
SYSTEM_RUNTIME_DIRECTORY: Final = Path("/usr/lib/x86_64-linux-gnu")
DYNAMIC_LOADER: Final = SYSTEM_RUNTIME_DIRECTORY / "ld-linux-x86-64.so.2"
SYSTEM_RUNTIME_FILES: Final = (
    DYNAMIC_LOADER,
    SYSTEM_RUNTIME_DIRECTORY / "libpthread.so.0",
    SYSTEM_RUNTIME_DIRECTORY / "libdl.so.2",
    SYSTEM_RUNTIME_DIRECTORY / "libutil.so.1",
    SYSTEM_RUNTIME_DIRECTORY / "librt.so.1",
    SYSTEM_RUNTIME_DIRECTORY / "libm.so.6",
    SYSTEM_RUNTIME_DIRECTORY / "libc.so.6",
)
PYTHON_STARTUP_ABSENT_CANDIDATES: Final = (
    Path(f"{PYTHON_EXECUTABLE.as_posix()}\n._pth"),
    Path("/home/minami/rakuten/.venv/bin/python._pth"),
    Path(f"{PYTHON_EXECUTABLE.as_posix()}._pth"),
    PYTHON_BIN_DIRECTORY / "pybuilddir.txt",
)
APPROVED_BASE_COMMIT: Final = "b5a6157b878ca0435ee4120d33162aba5ae51f77"
MAX_RUNTIME_FILE_BYTES: Final = 4 * 1024 * 1024
MAX_MANIFEST_BYTES: Final = 128 * 1024
MAX_PYTHON_CODE_FILE_BYTES: Final = 8 * 1024 * 1024
MAX_PYTHON_EXECUTABLE_BYTES: Final = 64 * 1024 * 1024
MAX_PYTHON_INVENTORY_BYTES: Final = 512 * 1024
MAX_PYTHON_TREE_ENTRIES: Final = 10_000
REQUIRED_RUNTIME_PATHS: Final = (
    "changes/st-1703/self-hosted-minimum-start-v1/DESIGN_HANDOFF_V1.yaml",
    "changes/st-1703/self-hosted-minimum-start-v1/Makefile",
    "changes/st-1703/self-hosted-minimum-start-v1/content/first-suitcase-comparison.v1.json",
    "changes/st-1703/self-hosted-minimum-start-v1/python-runtime-code-inventory.v1.sha256",
    "changes/st-1703/self-hosted-minimum-start-v1/theme/kurashinoshirube-child/assets/theme.css",
    "changes/st-1703/self-hosted-minimum-start-v1/theme/kurashinoshirube-child/assets/theme.js",
    "changes/st-1703/self-hosted-minimum-start-v1/theme/kurashinoshirube-child/functions.php",
    "changes/st-1703/self-hosted-minimum-start-v1/theme/kurashinoshirube-child/parts/footer.html",
    "changes/st-1703/self-hosted-minimum-start-v1/theme/kurashinoshirube-child/parts/header.html",
    "changes/st-1703/self-hosted-minimum-start-v1/theme/kurashinoshirube-child/raos-assets.v1.json",
    "changes/st-1703/self-hosted-minimum-start-v1/theme/kurashinoshirube-child/style.css",
    "changes/st-1703/self-hosted-minimum-start-v1/theme/kurashinoshirube-child/templates/front-page.html",
    "changes/st-1703/self-hosted-minimum-start-v1/theme/kurashinoshirube-child/templates/single.html",
    "changes/st-1703/self-hosted-minimum-start-v1/theme/kurashinoshirube-child/theme.json",
    "python/raos/adapters/self_hosted_wordpress_credentials.py",
    "python/raos/adapters/self_hosted_wordpress_https.py",
    "python/raos/adapters/self_hosted_wordpress_journal.py",
    "python/raos/adapters/self_hosted_wordpress_rest.py",
    "python/raos/adapters/wordpress_rest.py",
    "python/raos/application/editorial/self_hosted_minimum_start.py",
    "python/raos/domain/editorial/market_learning_pilot.py",
    "python/raos/domain/editorial/self_hosted_wordpress.py",
    "python/raos/ports/self_hosted_wordpress.py",
    "scripts/build_st1703_self_hosted_theme.py",
    "scripts/self_hosted_wordpress.py",
    "scripts/self_hosted_wordpress_python.sh",
)


class RuntimeManifestFailure(RuntimeError):
    """Closed generator/check failure."""


def _fail() -> NoReturn:
    raise RuntimeManifestFailure("SELF_HOSTED_RUNTIME_MANIFEST_INVALID") from None


def _safe_relative(value: str) -> PurePosixPath:
    if type(value) is not str or not value or value != value.strip() or "\\" in value:
        _fail()
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or relative.as_posix() != value
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail()
    return relative


def _read_owned_regular(relative_value: str, *, maximum_bytes: int) -> bytes:
    relative = _safe_relative(relative_value)
    root_descriptor = -1
    parent_descriptor = -1
    descriptor = -1
    try:
        root_descriptor = os.open(
            ROOT,
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
        )
        parent_descriptor = os.dup(root_descriptor)
        for part in relative.parts[:-1]:
            child = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=parent_descriptor,
            )
            os.close(parent_descriptor)
            parent_descriptor = child
        descriptor = os.open(
            relative.parts[-1],
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=parent_descriptor,
        )
        before = os.fstat(descriptor)
        named_before = os.stat(
            relative.parts[-1], dir_fd=parent_descriptor, follow_symlinks=False
        )
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) & 0o022
            or not 1 <= before.st_size <= maximum_bytes
            or (before.st_dev, before.st_ino)
            != (
                named_before.st_dev,
                named_before.st_ino,
            )
        ):
            _fail()
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                _fail()
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _fail()
        after = os.fstat(descriptor)
        named_after = os.stat(
            relative.parts[-1], dir_fd=parent_descriptor, follow_symlinks=False
        )

        def identity(value: os.stat_result) -> tuple[int, ...]:
            return (
                value.st_dev,
                value.st_ino,
                value.st_mode,
                value.st_uid,
                value.st_gid,
                value.st_nlink,
                value.st_size,
                value.st_mtime_ns,
                value.st_ctime_ns,
            )

        if identity(before) != identity(after) or identity(after) != identity(
            named_after
        ):
            _fail()
        payload = b"".join(chunks)
        if len(payload) != before.st_size:
            _fail()
        return payload
    except RuntimeManifestFailure:
        raise
    except (OSError, ValueError):  # fmt: skip
        _fail()
    finally:
        for opened in (descriptor, parent_descriptor, root_descriptor):
            if opened >= 0:
                try:
                    os.close(opened)
                except OSError:
                    pass
    raise AssertionError("unreachable")


def _identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_gid,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _python_tree_snapshot() -> tuple[
    tuple[int, ...], dict[str, tuple[str, tuple[int, ...]]]
]:
    try:
        root_metadata = PYTHON_STDLIB_ROOT.lstat()
    except OSError:
        _fail()
    if (
        not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(root_metadata.st_mode) & 0o022
    ):
        _fail()
    entries: dict[str, tuple[str, tuple[int, ...]]] = {}
    try:
        for path in PYTHON_STDLIB_ROOT.rglob("*"):
            if len(entries) >= MAX_PYTHON_TREE_ENTRIES:
                _fail()
            relative = path.relative_to(PYTHON_STDLIB_ROOT).as_posix()
            if not relative or relative in entries:
                _fail()
            metadata = path.lstat()
            if (
                metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) & 0o022
            ):
                _fail()
            if stat.S_ISDIR(metadata.st_mode):
                kind = "directory"
            elif stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1:
                kind = "file"
            else:
                _fail()
            entries[relative] = (kind, _identity(metadata))
    except RuntimeManifestFailure:
        raise
    except (OSError, ValueError):  # fmt: skip
        _fail()
    return _identity(root_metadata), entries


def _read_external_regular(
    path: Path,
    *,
    maximum_bytes: int,
    minimum_bytes: int = 1,
    expected_uid: int | None = None,
) -> bytes:
    descriptor = -1
    try:
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != (os.geteuid() if expected_uid is None else expected_uid)
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) & 0o022
            or type(minimum_bytes) is not int
            or not 0 <= minimum_bytes <= before.st_size <= maximum_bytes
        ):
            _fail()
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
        )
        opened = os.fstat(descriptor)
        if _identity(opened) != _identity(before):
            _fail()
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                _fail()
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _fail()
        after = os.fstat(descriptor)
        named_after = path.lstat()
        if _identity(opened) != _identity(after) or _identity(after) != _identity(
            named_after
        ):
            _fail()
        return b"".join(chunks)
    except RuntimeManifestFailure:
        raise
    except OSError:
        _fail()
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    raise AssertionError("unreachable")


def _require_root_owned_directory_chain(path: Path) -> None:
    if not path.is_absolute():
        _fail()
    for directory in reversed((path, *path.parents)):
        try:
            metadata = directory.lstat()
        except OSError:
            _fail()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            _fail()


def _require_python_startup_candidates_absent() -> None:
    if (
        len(PYTHON_STARTUP_ABSENT_CANDIDATES) != 4
        or len(set(PYTHON_STARTUP_ABSENT_CANDIDATES)) != 4
    ):
        _fail()
    for candidate in PYTHON_STARTUP_ABSENT_CANDIDATES:
        try:
            candidate.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            _fail()
        _fail()


def _directory_path_inventory(directory: Path) -> tuple[int, bytes]:
    descriptor = -1
    try:
        before = directory.lstat()
        if (
            not stat.S_ISDIR(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or before.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) & 0o022
        ):
            _fail()
        descriptor = os.open(
            directory,
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
        )
        opened = os.fstat(descriptor)
        if _identity(opened) != _identity(before):
            _fail()
        names = os.listdir(descriptor)
        encoded_names: list[bytes] = []
        for name in names:
            encoded = os.fsencode(name)
            if not encoded or b"/" in encoded or encoded in {b".", b".."}:
                _fail()
            encoded_names.append(encoded)
        if len(encoded_names) != len(set(encoded_names)):
            _fail()
        after = os.fstat(descriptor)
        named_after = directory.lstat()
        if _identity(opened) != _identity(after) or _identity(after) != _identity(
            named_after
        ):
            _fail()
        prefix = os.fsencode(directory) + b"/"
        material = b"".join(prefix + name + b"\0" for name in sorted(encoded_names))
        return len(encoded_names), material
    except RuntimeManifestFailure:
        raise
    except (OSError, ValueError):  # fmt: skip
        _fail()
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    raise AssertionError("unreachable")


def _system_runtime_material() -> bytes:
    if (
        len(SYSTEM_RUNTIME_FILES) != 7
        or len(set(SYSTEM_RUNTIME_FILES)) != 7
        or SYSTEM_RUNTIME_FILES[0] != DYNAMIC_LOADER
        or any(path.parent != SYSTEM_RUNTIME_DIRECTORY for path in SYSTEM_RUNTIME_FILES)
    ):
        _fail()
    _require_root_owned_directory_chain(SYSTEM_RUNTIME_DIRECTORY)
    rows: list[bytes] = []
    for path in SYSTEM_RUNTIME_FILES:
        payload = _read_external_regular(
            path,
            maximum_bytes=16 * 1024 * 1024,
            expected_uid=0,
        )
        rows.append(
            hashlib.sha256(payload).hexdigest().encode("ascii")
            + b"  "
            + path.as_posix().encode("ascii", errors="strict")
            + b"\n"
        )
    return b"".join(rows)


def _is_python_code_path(relative: str) -> bool:
    parts = PurePosixPath(relative).parts
    return (
        "site-packages" not in parts
        and "__pycache__" not in parts
        and PurePosixPath(relative).suffix in {".py", ".pyc", ".so"}
    )


def render_python_runtime_inventory() -> bytes:
    try:
        PYTHON_ZIP_PATH.lstat()
    except FileNotFoundError:
        pass
    except OSError:
        _fail()
    else:
        _fail()
    _require_python_startup_candidates_absent()
    system_runtime_material = _system_runtime_material()
    python_bin_inventory = _directory_path_inventory(PYTHON_BIN_DIRECTORY)
    venv_bin_inventory = _directory_path_inventory(VENV_BIN_DIRECTORY)
    root_before, before = _python_tree_snapshot()
    code_paths = sorted(
        (
            relative
            for relative, (kind, _metadata) in before.items()
            if kind == "file" and _is_python_code_path(relative)
        ),
        key=os.fsencode,
    )
    if not code_paths:
        _fail()
    checksum_rows: list[bytes] = []
    path_material: list[bytes] = []
    total_bytes = 0
    allowed_path_bytes = frozenset(
        b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-/+@"
    )
    for relative in code_paths:
        try:
            encoded_relative = relative.encode("ascii", errors="strict")
        except UnicodeError:
            _fail()
        if not encoded_relative or any(
            byte not in allowed_path_bytes for byte in encoded_relative
        ):
            _fail()
        payload = _read_external_regular(
            PYTHON_STDLIB_ROOT / relative,
            maximum_bytes=MAX_PYTHON_CODE_FILE_BYTES,
            minimum_bytes=0,
        )
        if before[relative][1] != _identity((PYTHON_STDLIB_ROOT / relative).lstat()):
            _fail()
        total_bytes += len(payload)
        absolute = (PYTHON_STDLIB_ROOT / relative).as_posix().encode("ascii")
        checksum_rows.append(
            hashlib.sha256(payload).hexdigest().encode("ascii")
            + b"  "
            + absolute
            + b"\n"
        )
        path_material.append(b"./" + encoded_relative + b"\0")
    root_after, after = _python_tree_snapshot()
    if root_after != root_before or after != before:
        _fail()
    executable = _read_external_regular(
        PYTHON_EXECUTABLE,
        maximum_bytes=MAX_PYTHON_EXECUTABLE_BYTES,
    )
    pyvenv = _read_external_regular(PYVENV_CONFIG, maximum_bytes=4096)
    _require_python_startup_candidates_absent()
    if _system_runtime_material() != system_runtime_material:
        _fail()
    if (
        _directory_path_inventory(PYTHON_BIN_DIRECTORY) != python_bin_inventory
        or _directory_path_inventory(VENV_BIN_DIRECTORY) != venv_bin_inventory
    ):
        _fail()
    startup_path_material = b"".join(
        os.fsencode(candidate) + b"\0" for candidate in PYTHON_STARTUP_ABSENT_CANDIDATES
    )
    header = (
        "# schema=SELF_HOSTED_PYTHON_RUNTIME_CODE_INVENTORY_V1\n"
        "# generated_by=scripts/build_st1703_self_hosted_runtime_manifest.py\n"
        "# generate_command=make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile runtime-manifest-generate\n"
        f"# python_base={PYTHON_BASE.as_posix()}\n"
        f"# stdlib_root={PYTHON_STDLIB_ROOT.as_posix()}\n"
        f"# code_path_sha256={hashlib.sha256(b''.join(path_material)).hexdigest()}\n"
        f"# code_file_count={len(code_paths)}\n"
        f"# code_file_bytes={total_bytes}\n"
        f"# python_executable_sha256={hashlib.sha256(executable).hexdigest()}\n"
        f"# pyvenv_cfg_sha256={hashlib.sha256(pyvenv).hexdigest()}\n"
        "# python_zip_state=ABSENT\n"
        f"# dynamic_loader_path={DYNAMIC_LOADER.as_posix()}\n"
        f"# system_runtime_file_count={len(SYSTEM_RUNTIME_FILES)}\n"
        f"# system_runtime_sha256={hashlib.sha256(system_runtime_material).hexdigest()}\n"
        "# python_rpath_policy=PINNED_LOADER_INHIBIT_RPATH\n"
        f"# python_bin_entry_count={python_bin_inventory[0]}\n"
        f"# python_bin_path_sha256={hashlib.sha256(python_bin_inventory[1]).hexdigest()}\n"
        f"# venv_bin_entry_count={venv_bin_inventory[0]}\n"
        f"# venv_bin_path_sha256={hashlib.sha256(venv_bin_inventory[1]).hexdigest()}\n"
        f"# python_startup_landmark_candidate_count={len(PYTHON_STARTUP_ABSENT_CANDIDATES)}\n"
        f"# python_startup_landmark_path_sha256={hashlib.sha256(startup_path_material).hexdigest()}\n"
        "# python_startup_landmark_state=ABSENT\n"
        "\n"
    ).encode("ascii", errors="strict")
    rendered = header + b"".join(checksum_rows)
    if not 1 <= len(rendered) <= MAX_PYTHON_INVENTORY_BYTES:
        _fail()
    return rendered


def render() -> bytes:
    runtime_paths = tuple(sorted(REQUIRED_RUNTIME_PATHS))
    if len(set(runtime_paths)) != len(runtime_paths):
        _fail()
    entries: list[dict[str, object]] = []
    for relative in runtime_paths:
        payload = _read_owned_regular(relative, maximum_bytes=MAX_RUNTIME_FILE_BYTES)
        entries.append(
            {
                "bytes": len(payload),
                "path": relative,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    document = {
        "approved_base_commit": APPROVED_BASE_COMMIT,
        "external_action_authority": "NONE",
        "generated_by": "scripts/build_st1703_self_hosted_runtime_manifest.py",
        "paths": entries,
        "repository_development_authority": "ROOT_STANDING_DEVELOPMENT_AUTHORIZATION",
        "schema": "SELF_HOSTED_WORDPRESS_RUNTIME_MANIFEST_V1",
        "slice_id": "SELF_HOSTED_MINIMUM_START_V1",
        "story_id": "ST-1703",
    }
    rendered = (
        json.dumps(
            document,
            ensure_ascii=True,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("ascii", errors="strict")
    if not 1 <= len(rendered) <= MAX_MANIFEST_BYTES:
        _fail()
    return rendered


def _write_output(output_path: Path, payload: bytes, *, maximum_bytes: int) -> None:
    if (
        not output_path.is_absolute()
        or output_path == ROOT
        or ROOT not in output_path.parents
        or not 1 <= len(payload) <= maximum_bytes
    ):
        _fail()
    relative = output_path.relative_to(ROOT)
    temporary_name = f".{output_path.name}.new"
    root_descriptor = -1
    parent_descriptor = -1
    descriptor = -1
    published_identity: tuple[int, int, int, int, int] | None = None
    try:
        root_descriptor = os.open(
            ROOT,
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
        )
        parent_descriptor = os.dup(root_descriptor)
        for part in relative.parts[:-1]:
            child = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=parent_descriptor,
            )
            os.close(parent_descriptor)
            parent_descriptor = child
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o644,
            dir_fd=parent_descriptor,
        )
        os.fchmod(descriptor, 0o644)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                _fail()
            offset += written
        os.fsync(descriptor)
        details = os.fstat(descriptor)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.geteuid()
            or details.st_nlink != 1
            or details.st_size != len(payload)
        ):
            _fail()
        published_identity = (
            details.st_dev,
            details.st_ino,
            details.st_uid,
            details.st_nlink,
            details.st_size,
        )
        os.close(descriptor)
        descriptor = -1
        os.replace(
            temporary_name,
            relative.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        named = os.stat(relative.name, dir_fd=parent_descriptor, follow_symlinks=False)
        if published_identity != (
            named.st_dev,
            named.st_ino,
            named.st_uid,
            named.st_nlink,
            named.st_size,
        ):
            _fail()
        os.fsync(parent_descriptor)
    except RuntimeManifestFailure:
        raise
    except OSError:
        _fail()
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            if parent_descriptor >= 0:
                os.unlink(temporary_name, dir_fd=parent_descriptor)
        except OSError:
            pass
        if parent_descriptor >= 0:
            os.close(parent_descriptor)
        if root_descriptor >= 0:
            os.close(root_descriptor)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        if (
            sys.flags.isolated != 1
            or sys.flags.no_site != 1
            or sys.flags.dont_write_bytecode != 1
            or sys.pycache_prefix != "/dev/null"
        ):
            _fail()
        python_inventory = render_python_runtime_inventory()
        if arguments.check:
            current_python_inventory = _read_owned_regular(
                PYTHON_RUNTIME_INVENTORY_PATH.relative_to(ROOT).as_posix(),
                maximum_bytes=MAX_PYTHON_INVENTORY_BYTES,
            )
            if current_python_inventory != python_inventory:
                return 2
            rendered = render()
            current = _read_owned_regular(
                OUTPUT_PATH.relative_to(ROOT).as_posix(),
                maximum_bytes=MAX_MANIFEST_BYTES,
            )
            return 0 if current == rendered else 2
        _write_output(
            PYTHON_RUNTIME_INVENTORY_PATH,
            python_inventory,
            maximum_bytes=MAX_PYTHON_INVENTORY_BYTES,
        )
        rendered = render()
        _write_output(OUTPUT_PATH, rendered, maximum_bytes=MAX_MANIFEST_BYTES)
        return 0
    except RuntimeManifestFailure:
        return 2


if __name__ == "__main__":
    sys.exit(main())

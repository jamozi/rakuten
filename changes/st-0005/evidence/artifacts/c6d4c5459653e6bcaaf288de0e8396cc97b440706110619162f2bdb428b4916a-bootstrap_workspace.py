#!/usr/bin/env python3
"""Materialize and verify the inert RAOS monorepo skeleton for ST-0101."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
from dataclasses import dataclass
import errno
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
from typing import Any, Iterator, Mapping, Sequence


CONFIG_NAME = "workspace-layout.json"
MAX_CONFIG_BYTES = 256 * 1024
MAX_MARKER_BYTES = 64 * 1024
SCHEMA_VERSION = 1
WORKSPACE_NAME = "raos"
MARKER_FILE = "README.md"
GENERATED_HEADER = (
    "<!-- Generated from workspace-layout.json by "
    "scripts/bootstrap_workspace.py. Do not edit directly. -->"
)
EXPECTED_TOP_LEVEL_KEYS = {
    "schema_version",
    "workspace",
    "marker_file",
    "managed_roots",
    "required_files",
    "directories",
}
EXPECTED_ENTRY_KEYS = {"path", "purpose"}
EXPECTED_MANAGED_ROOTS = (
    "apps",
    "contracts",
    "docs",
    "infra",
    "migrations",
    "packages",
    "policies",
    "prompts",
    "python",
    "schemas",
    "tests",
)
EXPECTED_REQUIRED_FILES = (
    ".gitattributes",
    ".gitignore",
    "AGENTS.md",
    "Makefile",
    "README.md",
    "scripts/bootstrap_workspace.py",
    "workspace-layout.json",
)
EXPECTED_DIRECTORY_PATHS = (
    "apps/api",
    "apps/web",
    "apps/worker",
    "contracts",
    "docs/adr",
    "docs/architecture",
    "docs/runbooks",
    "infra/docker",
    "infra/terraform",
    "migrations",
    "packages/policy-schemas",
    "packages/web-contracts",
    "packages/web-ui",
    "policies",
    "prompts",
    "python/raos/adapters",
    "python/raos/api",
    "python/raos/application",
    "python/raos/domain/ai",
    "python/raos/domain/analytics",
    "python/raos/domain/catalog",
    "python/raos/domain/editorial",
    "python/raos/domain/evidence",
    "python/raos/domain/finance",
    "python/raos/domain/freshness",
    "python/raos/domain/iam",
    "python/raos/domain/ops",
    "python/raos/domain/policy",
    "python/raos/domain/portfolio",
    "python/raos/domain/publishing",
    "python/raos/ports",
    "python/raos/shared",
    "python/raos/workers",
    "schemas/ai",
    "schemas/content",
    "schemas/events",
    "schemas/openapi",
    "tests/contract",
    "tests/e2e",
    "tests/evals",
    "tests/fixtures",
    "tests/security",
)
PROTECTED_PREFIXES = (
    PurePosixPath("docs/canonical"),
    PurePosixPath("docs/upstream"),
)
ACTIVATED_DIRECTORY_OWNERS = {
    "packages/web-contracts": "ST-0105",
}
PR_GET_DUMPABLE = 3
PR_SET_DUMPABLE = 4


class WorkspaceError(RuntimeError):
    """Raised when workspace input or state violates the ST-0101 contract."""


class DirectoryMissing(WorkspaceError):
    """Raised when a no-create descriptor walk finds a missing component."""


@dataclass(frozen=True)
class MarkerPlan:
    """A preflighted marker operation run only after the full scan passes."""

    relative: PurePosixPath
    expected: bytes
    needs_write: bool
    preflight_identity: tuple[int, int] | None


def _exact_keys(value: Mapping[str, Any], expected: set[str], *, source: str) -> None:
    actual = set(value)
    if actual != expected:
        raise WorkspaceError(
            f"{source} keys differ: missing={sorted(expected - actual)}, "
            f"unknown={sorted(actual - expected)}"
        )


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WorkspaceError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _string(value: Any, *, source: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceError(f"{source} must be a non-empty string")
    if any(ord(character) < 32 for character in value):
        raise WorkspaceError(f"{source} contains a control character")
    return value


def _relative_path(value: Any, *, source: str) -> PurePosixPath:
    text = _string(value, source=source)
    if "\\" in text:
        raise WorkspaceError(f"{source} must use POSIX separators")
    relative = PurePosixPath(text)
    if relative.is_absolute() or relative.as_posix() != text:
        raise WorkspaceError(f"{source} must be a normalized relative path")
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise WorkspaceError(f"{source} contains an unsafe path component")
    return relative


def _path_has_prefix(path: PurePosixPath, prefix: PurePosixPath) -> bool:
    return path == prefix or prefix in path.parents


def _require_descriptor_platform() -> None:
    if not getattr(os, "O_DIRECTORY", 0) or not getattr(os, "O_NOFOLLOW", 0):
        raise WorkspaceError(
            "workspace bootstrap requires O_DIRECTORY and O_NOFOLLOW support"
        )


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _file_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _open_root_fd(root: Path) -> int:
    _require_descriptor_platform()
    try:
        descriptor = os.open(root, _directory_flags())
    except OSError as exc:
        raise WorkspaceError(
            "repository root must be an existing non-symlink directory"
        ) from exc
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise WorkspaceError(
            "repository root must be an existing non-symlink directory"
        )
    return descriptor


def _component_error(
    parent_fd: int,
    component: str,
    *,
    relative: PurePosixPath,
    source: str,
    cause: OSError,
) -> WorkspaceError:
    try:
        metadata = os.stat(component, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return DirectoryMissing(f"{source} is missing: {relative}")
    except OSError:
        return WorkspaceError(f"cannot inspect {source}: {relative}")
    if stat.S_ISLNK(metadata.st_mode) or cause.errno == errno.ELOOP:
        return WorkspaceError(f"{source} has a symlink component: {relative}")
    if not stat.S_ISDIR(metadata.st_mode):
        return WorkspaceError(f"{source} collides with a file: {relative}")
    return WorkspaceError(f"{source} changed during descriptor traversal: {relative}")


def _open_directory_fd(
    root_fd: int,
    relative: PurePosixPath,
    *,
    create: bool,
    require_final_creation: bool = False,
    source: str = "managed directory",
) -> int:
    current = os.dup(root_fd)
    final_created = False
    try:
        for index, component in enumerate(relative.parts):
            is_final = index == len(relative.parts) - 1
            try:
                next_descriptor = os.open(component, _directory_flags(), dir_fd=current)
            except FileNotFoundError as exc:
                if not create:
                    raise DirectoryMissing(f"{source} is missing: {relative}") from exc
                try:
                    os.mkdir(component, mode=0o755, dir_fd=current)
                    if is_final:
                        final_created = True
                except FileExistsError as mkdir_exc:
                    if is_final and require_final_creation:
                        raise WorkspaceError(
                            f"{source} appeared after preflight: {relative}"
                        ) from mkdir_exc
                try:
                    next_descriptor = os.open(
                        component, _directory_flags(), dir_fd=current
                    )
                except OSError as open_exc:
                    raise _component_error(
                        current,
                        component,
                        relative=relative,
                        source=source,
                        cause=open_exc,
                    ) from open_exc
            except OSError as exc:
                raise _component_error(
                    current,
                    component,
                    relative=relative,
                    source=source,
                    cause=exc,
                ) from exc
            os.close(current)
            current = next_descriptor
        if require_final_creation and not final_created:
            raise WorkspaceError(f"{source} appeared after preflight: {relative}")
        return current
    except BaseException:
        os.close(current)
        raise


def _open_regular_at(directory_fd: int, filename: str, *, source: str) -> int | None:
    try:
        before = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(before.st_mode):
        raise WorkspaceError(f"{source} is a symlink")
    if not stat.S_ISREG(before.st_mode):
        raise WorkspaceError(f"{source} must be a regular non-symlink file")
    try:
        descriptor = os.open(filename, _file_flags(), dir_fd=directory_fd)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise WorkspaceError(f"{source} is a symlink") from exc
        raise WorkspaceError(f"cannot open {source}") from exc
    after = os.fstat(descriptor)
    if not stat.S_ISREG(after.st_mode) or (before.st_dev, before.st_ino) != (
        after.st_dev,
        after.st_ino,
    ):
        os.close(descriptor)
        raise WorkspaceError(f"{source} changed during validation")
    return descriptor


def _read_bounded_fd(descriptor: int, *, maximum: int, source: str) -> bytes:
    metadata = os.fstat(descriptor)
    if metadata.st_size > maximum:
        raise WorkspaceError(f"{source} exceeds {maximum} bytes")
    chunks: list[bytes] = []
    total = 0
    while total <= maximum:
        chunk = os.read(descriptor, min(64 * 1024, maximum + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    if total > maximum:
        raise WorkspaceError(f"{source} exceeds {maximum} bytes")
    return b"".join(chunks)


def _open_repo_file_fd(root_fd: int, relative: PurePosixPath, *, source: str) -> int:
    parent_parts = relative.parts[:-1]
    parent_relative = PurePosixPath(*parent_parts) if parent_parts else None
    try:
        parent_fd = (
            _open_directory_fd(
                root_fd,
                parent_relative,
                create=False,
                source=f"{source} parent",
            )
            if parent_relative is not None
            else os.dup(root_fd)
        )
    except DirectoryMissing as exc:
        raise WorkspaceError(
            f"{source} must be a regular non-symlink file: {relative}"
        ) from exc
    try:
        descriptor = _open_regular_at(
            parent_fd, relative.name, source=f"{source}: {relative}"
        )
    finally:
        os.close(parent_fd)
    if descriptor is None:
        raise WorkspaceError(f"{source} must be a regular non-symlink file: {relative}")
    return descriptor


def _verify_repo_file(root_fd: int, relative: PurePosixPath, *, source: str) -> None:
    descriptor = _open_repo_file_fd(root_fd, relative, source=source)
    os.close(descriptor)


def load_config(root_fd: int) -> dict[str, Any]:
    descriptor = _open_repo_file_fd(
        root_fd,
        PurePosixPath(CONFIG_NAME),
        source="workspace configuration",
    )
    try:
        payload = _read_bounded_fd(
            descriptor,
            maximum=MAX_CONFIG_BYTES,
            source="workspace configuration",
        )
        raw = json.loads(payload.decode("utf-8"), object_pairs_hook=_strict_json_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkspaceError(f"cannot read strict JSON configuration: {exc}") from exc
    finally:
        os.close(descriptor)
    if not isinstance(raw, dict):
        raise WorkspaceError("workspace configuration must be an object")
    _exact_keys(raw, EXPECTED_TOP_LEVEL_KEYS, source="workspace configuration")
    if (
        type(raw["schema_version"]) is not int
        or raw["schema_version"] != SCHEMA_VERSION
    ):
        raise WorkspaceError("unsupported workspace schema_version")
    if raw["workspace"] != WORKSPACE_NAME:
        raise WorkspaceError("workspace name must be raos")
    if raw["marker_file"] != MARKER_FILE:
        raise WorkspaceError("marker_file must be README.md")

    managed_roots = raw["managed_roots"]
    if (
        not isinstance(managed_roots, list)
        or tuple(managed_roots) != EXPECTED_MANAGED_ROOTS
    ):
        raise WorkspaceError(
            "managed_roots must equal the sorted ST-0101 root allowlist"
        )
    required_files = raw["required_files"]
    if (
        not isinstance(required_files, list)
        or tuple(required_files) != EXPECTED_REQUIRED_FILES
    ):
        raise WorkspaceError("required_files must equal the sorted ST-0101 file set")

    entries = raw["directories"]
    if not isinstance(entries, list) or not entries:
        raise WorkspaceError("directories must be a non-empty list")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, value in enumerate(entries):
        source = f"directories[{index}]"
        if not isinstance(value, dict):
            raise WorkspaceError(f"{source} must be an object")
        _exact_keys(value, EXPECTED_ENTRY_KEYS, source=source)
        relative = _relative_path(value["path"], source=f"{source}.path")
        if relative.parts[0] not in EXPECTED_MANAGED_ROOTS:
            raise WorkspaceError(f"{source}.path is outside managed roots")
        if any(_path_has_prefix(relative, prefix) for prefix in PROTECTED_PREFIXES):
            raise WorkspaceError(f"{source}.path enters an immutable design root")
        path_text = relative.as_posix()
        if path_text in seen:
            raise WorkspaceError(f"duplicate managed directory: {path_text}")
        seen.add(path_text)
        normalized.append(
            {
                "path": path_text,
                "purpose": _string(value["purpose"], source=f"{source}.purpose"),
            }
        )
    paths = [entry["path"] for entry in normalized]
    if paths != sorted(paths):
        raise WorkspaceError("directories must be sorted by path")
    if tuple(paths) != EXPECTED_DIRECTORY_PATHS:
        expected_paths: set[str] = set(EXPECTED_DIRECTORY_PATHS)
        actual_paths: set[str] = set(paths)
        missing = sorted(expected_paths - actual_paths)
        unknown = sorted(actual_paths - expected_paths)
        raise WorkspaceError(
            "directories differ from the ST-0101 architecture contract: "
            f"missing={missing}, unknown={unknown}"
        )
    return {**raw, "directories": normalized}


def marker_bytes(entry: Mapping[str, str]) -> bytes:
    owner = ACTIVATED_DIRECTORY_OWNERS.get(entry["path"])
    footer = (
        f"ST-0101 established this boundary; {owner} activates and owns its "
        "functional generated content. Change the owning generator or source "
        "contract, never src/generated files by hand.\n"
        if owner is not None
        else (
            "ST-0101 reserves this directory as an inert boundary. Functional "
            "content is owned by later backlog Stories.\n"
        )
    )
    text = (
        f"{GENERATED_HEADER}\n\n"
        f"# `{entry['path']}`\n\n"
        f"{entry['purpose']}\n\n"
        f"{footer}"
    )
    return text.encode("utf-8")


def _read_marker_at(
    directory_fd: int, relative: PurePosixPath, *, missing_ok: bool
) -> bytes | None:
    source = f"managed marker: {relative}/{MARKER_FILE}"
    descriptor = _open_regular_at(directory_fd, MARKER_FILE, source=source)
    if descriptor is None:
        if missing_ok:
            return None
        raise WorkspaceError(f"managed marker is missing: {relative}/{MARKER_FILE}")
    try:
        if os.fstat(descriptor).st_nlink != 1:
            raise WorkspaceError(
                f"managed marker must have exactly one hard link: "
                f"{relative}/{MARKER_FILE}"
            )
        return _read_bounded_fd(
            descriptor,
            maximum=MAX_MARKER_BYTES,
            source=source,
        )
    finally:
        os.close(descriptor)


def _marker_needs_write(
    directory_fd: int,
    relative: PurePosixPath,
    expected: bytes,
    *,
    check: bool,
) -> bool:
    actual = _read_marker_at(directory_fd, relative, missing_ok=True)
    if actual is None:
        if check:
            raise WorkspaceError(f"managed marker is missing: {relative}/{MARKER_FILE}")
        return True
    if actual == expected:
        return False
    if not actual.startswith(GENERATED_HEADER.encode("utf-8")):
        raise WorkspaceError(
            f"refusing to overwrite an unmanaged marker: {relative}/{MARKER_FILE}"
        )
    raise WorkspaceError(f"managed marker drift: {relative}/{MARKER_FILE}")


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise WorkspaceError("short write while creating managed marker")
        offset += written


def _prctl(option: int, value: int = 0) -> int:
    """Call Linux prctl with a fail-closed, stdlib-only wrapper."""

    try:
        libc = ctypes.CDLL(None, use_errno=True)
        call = libc.prctl
    except (AttributeError, OSError) as exc:
        raise WorkspaceError(
            "managed-marker creation requires Linux prctl support"
        ) from exc
    call.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    call.restype = ctypes.c_int
    ctypes.set_errno(0)
    result = int(call(option, value, 0, 0, 0))
    if result < 0:
        error_number = ctypes.get_errno()
        raise WorkspaceError(
            "managed-marker creation cannot control process dumpability: "
            f"errno={error_number}"
        )
    return result


@contextmanager
def _private_fd_window() -> Iterator[None]:
    """Hide anonymous marker descriptors from other same-UID processes."""

    previous = _prctl(PR_GET_DUMPABLE)
    if previous not in {0, 1}:
        raise WorkspaceError(
            "managed-marker creation found an unsupported dumpability state"
        )
    changed = previous != 0
    if changed:
        _prctl(PR_SET_DUMPABLE, 0)
        if _prctl(PR_GET_DUMPABLE) != 0:
            _prctl(PR_SET_DUMPABLE, previous)
            raise WorkspaceError(
                "managed-marker creation cannot enter a private fd window"
            )
    try:
        yield
    finally:
        if changed:
            _prctl(PR_SET_DUMPABLE, previous)
            if _prctl(PR_GET_DUMPABLE) != previous:
                raise WorkspaceError(
                    "managed-marker creation cannot restore process dumpability"
                )


def _atomic_write_at(directory_fd: int, filename: str, payload: bytes) -> None:
    """Atomically create a missing marker without ever replacing an entry."""

    anonymous_flag = getattr(os, "O_TMPFILE", 0)
    if not anonymous_flag:
        raise WorkspaceError(
            "managed-marker creation requires anonymous O_TMPFILE support"
        )
    with _private_fd_window():
        try:
            descriptor = os.open(
                ".",
                os.O_WRONLY
                | anonymous_flag
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=directory_fd,
            )
        except OSError as exc:
            raise WorkspaceError(
                "managed-marker creation requires anonymous O_TMPFILE support"
            ) from exc
        try:
            _write_all(descriptor, payload)
            os.fchmod(descriptor, 0o644)
            os.fsync(descriptor)
            unpublished = os.fstat(descriptor)
            if not stat.S_ISREG(unpublished.st_mode) or unpublished.st_nlink != 0:
                raise WorkspaceError(
                    "anonymous managed-marker inode changed before publication"
                )
            try:
                os.link(
                    f"/proc/self/fd/{descriptor}",
                    filename,
                    dst_dir_fd=directory_fd,
                    follow_symlinks=True,
                )
            except FileExistsError as exc:
                raise WorkspaceError(
                    f"managed marker appeared during bootstrap: {filename}"
                ) from exc
            except OSError as exc:
                raise WorkspaceError(
                    "cannot publish anonymous managed-marker inode; "
                    "Linux procfs link support is required"
                ) from exc

            try:
                published = os.stat(
                    filename,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
                current = os.fstat(descriptor)
            except OSError as exc:
                raise WorkspaceError(
                    f"managed marker changed during publication: {filename}"
                ) from exc
            if (
                not stat.S_ISREG(published.st_mode)
                or not stat.S_ISREG(current.st_mode)
                or (published.st_dev, published.st_ino)
                != (current.st_dev, current.st_ino)
                or published.st_nlink != 1
                or current.st_nlink != 1
            ):
                raise WorkspaceError(
                    f"managed marker changed during publication: {filename}"
                )
            os.fsync(directory_fd)
        finally:
            os.close(descriptor)


def _descriptor_identity(descriptor: int) -> tuple[int, int]:
    metadata = os.fstat(descriptor)
    return metadata.st_dev, metadata.st_ino


def _assert_root_identity(root: Path, expected_identity: tuple[int, int]) -> None:
    try:
        metadata = os.stat(root, follow_symlinks=False)
    except OSError as exc:
        raise WorkspaceError("repository root changed during bootstrap") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or (metadata.st_dev, metadata.st_ino) != expected_identity
    ):
        raise WorkspaceError("repository root changed during bootstrap")


def bootstrap(root: Path, *, check: bool) -> dict[str, Any]:
    root_fd = _open_root_fd(root)
    root_identity = _descriptor_identity(root_fd)
    try:
        config = load_config(root_fd)
        for value in config["required_files"]:
            relative = _relative_path(value, source="required_files[]")
            _verify_repo_file(root_fd, relative, source="required repository file")

        plans: list[MarkerPlan] = []
        identities: dict[PurePosixPath, tuple[int, int]] = {}
        for entry in config["directories"]:
            relative = _relative_path(entry["path"], source="managed directory")
            expected = marker_bytes(entry)
            if len(expected) > MAX_MARKER_BYTES:
                raise WorkspaceError(
                    f"generated marker exceeds {MAX_MARKER_BYTES} bytes: "
                    f"{relative}/{MARKER_FILE}"
                )
            try:
                directory_fd = _open_directory_fd(root_fd, relative, create=False)
            except DirectoryMissing:
                if check:
                    raise WorkspaceError(
                        f"managed directory is missing: {relative}"
                    ) from None
                plans.append(
                    MarkerPlan(
                        relative=relative,
                        expected=expected,
                        needs_write=True,
                        preflight_identity=None,
                    )
                )
                continue
            try:
                needs_write = _marker_needs_write(
                    directory_fd, relative, expected, check=check
                )
                preflight_identity = _descriptor_identity(directory_fd)
                identities[relative] = preflight_identity
            finally:
                os.close(directory_fd)
            plans.append(
                MarkerPlan(
                    relative=relative,
                    expected=expected,
                    needs_write=needs_write,
                    preflight_identity=preflight_identity,
                )
            )

        changed: list[str] = []
        if not check:
            for plan in plans:
                directory_fd = _open_directory_fd(
                    root_fd,
                    plan.relative,
                    create=plan.preflight_identity is None,
                    require_final_creation=plan.preflight_identity is None,
                )
                try:
                    write_identity = _descriptor_identity(directory_fd)
                    if (
                        plan.preflight_identity is not None
                        and write_identity != plan.preflight_identity
                    ):
                        raise WorkspaceError(
                            "managed directory changed after preflight: "
                            f"{plan.relative}"
                        )
                    needs_write = _marker_needs_write(
                        directory_fd,
                        plan.relative,
                        plan.expected,
                        check=False,
                    )
                    if needs_write:
                        _atomic_write_at(directory_fd, MARKER_FILE, plan.expected)
                        changed.append(f"{plan.relative}/{MARKER_FILE}")
                    identities.setdefault(plan.relative, write_identity)
                finally:
                    os.close(directory_fd)

        for plan in plans:
            try:
                directory_fd = _open_directory_fd(root_fd, plan.relative, create=False)
            except DirectoryMissing as exc:
                raise WorkspaceError(
                    f"managed directory changed during bootstrap: {plan.relative}"
                ) from exc
            try:
                if _descriptor_identity(directory_fd) != identities[plan.relative]:
                    raise WorkspaceError(
                        f"managed directory changed during bootstrap: {plan.relative}"
                    )
                actual = _read_marker_at(directory_fd, plan.relative, missing_ok=False)
                if actual != plan.expected:
                    raise WorkspaceError(
                        f"managed marker drift: {plan.relative}/{MARKER_FILE}"
                    )
            finally:
                os.close(directory_fd)
        _assert_root_identity(root, root_identity)
        return {
            "status": "PASS",
            "story_id": "ST-0101",
            "mode": "check" if check else "bootstrap",
            "workspace": config["workspace"],
            "directories": len(plans),
            "changed": changed,
        }
    finally:
        os.close(root_fd)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize or verify the inert ST-0101 workspace layout."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify exact layout and generated markers without writing",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = bootstrap(args.root, check=args.check)
    except (OSError, WorkspaceError) as exc:
        print(
            json.dumps(
                {"status": "FAIL", "story_id": "ST-0101", "error": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

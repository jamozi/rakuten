#!/usr/bin/python3.10
"""Fail-closed verifier for the owner-private ST-0101 MCP runtime."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import NoReturn


REPOSITORY_ROOT = Path("/home/minami/rakuten")
SOURCE_ROOT = REPOSITORY_ROOT / "scripts/chatgpt_pro_mcp_runtime"
PRIVATE_ROOT = REPOSITORY_ROOT / ".secrets"
RUNTIME_ROOT = PRIVATE_ROOT / "chatgpt-pro-mcp-runtime"
MANIFEST_NAME = "runtime-manifest.v1.json"
EXPECTED_INVENTORY_NAME = "expected-runtime-inventory.v1.json"
PACKAGE_NAME = "@playwright/mcp"
PACKAGE_VERSION = "0.0.78"
NODE_VERSION = "24.18.1"
NPM_VERSION = "11.16.0"
SCHEMA = "RAOS_CHATGPT_PRO_MCP_RUNTIME_V1"
EXPECTED_INVENTORY_SCHEMA = "RAOS_CHATGPT_PRO_MCP_EXPECTED_INVENTORY_V1"
STORY_ID = "ST-0101"
MAX_FILE_BYTES = 64 * 1024 * 1024
MANIFEST_KEYS = frozenset(
    {
        "schema",
        "story_id",
        "package",
        "version",
        "node_version",
        "npm_version",
        "package_lock_sha256",
        "inventory",
    }
)
INVENTORY_KEYS = frozenset({"kind", "path", "mode", "sha256", "size"})
HEX_DIGEST = re.compile(r"[0-9a-f]{64}")
JSON_ERRORS = (UnicodeDecodeError, json.JSONDecodeError)


class VerificationRefusal(Exception):
    """A sanitized fail-closed runtime verification result."""


def _refuse(code: str) -> NoReturn:
    raise VerificationRefusal(code)


def _safe_ancestors(path: Path, code: str) -> None:
    if not path.is_absolute():
        _refuse(code)
    current = Path("/")
    allowed_owners = {0, os.getuid()}
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except OSError:
            _refuse(code)
        if (
            stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid not in allowed_owners
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            _refuse(code)


def _read_regular(
    path: Path,
    *,
    code: str,
    expected_mode: int | None = None,
    source_file: bool = False,
) -> bytes:
    try:
        metadata = path.lstat()
    except OSError:
        _refuse(code)
    mode = stat.S_IMODE(metadata.st_mode)
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_size > MAX_FILE_BYTES
        or (expected_mode is not None and mode != expected_mode)
        or (source_file and mode & 0o022)
    ):
        _refuse(code)
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError:
        _refuse(code)
    try:
        opened = os.fstat(descriptor)
        if (
            opened.st_dev != metadata.st_dev
            or opened.st_ino != metadata.st_ino
            or opened.st_size != metadata.st_size
        ):
            _refuse(code)
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                _refuse(code)
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _refuse(code)
    finally:
        os.close(descriptor)
    return b"".join(chunks)


def _json_object(data: bytes, code: str) -> dict[str, object]:
    try:
        value = json.loads(data)
    except JSON_ERRORS:
        _refuse(code)
    if not isinstance(value, dict):
        _refuse(code)
    return value


def _source_contract() -> tuple[bytes, bytes, str]:
    _safe_ancestors(SOURCE_ROOT, "PRO_RUNTIME_SOURCE_INVALID")
    try:
        metadata = SOURCE_ROOT.lstat()
    except OSError:
        _refuse("PRO_RUNTIME_SOURCE_INVALID")
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        _refuse("PRO_RUNTIME_SOURCE_INVALID")
    package_bytes = _read_regular(
        SOURCE_ROOT / "package.json",
        code="PRO_RUNTIME_SOURCE_INVALID",
        source_file=True,
    )
    lock_bytes = _read_regular(
        SOURCE_ROOT / "package-lock.json",
        code="PRO_RUNTIME_SOURCE_INVALID",
        source_file=True,
    )
    package = _json_object(package_bytes, "PRO_RUNTIME_SOURCE_INVALID")
    lock = _json_object(lock_bytes, "PRO_RUNTIME_SOURCE_INVALID")
    if (
        set(package) != {"private", "dependencies"}
        or package.get("private") is not True
        or package.get("dependencies") != {PACKAGE_NAME: PACKAGE_VERSION}
        or lock.get("lockfileVersion") != 3
        or lock.get("requires") is not True
    ):
        _refuse("PRO_RUNTIME_SOURCE_INVALID")
    packages = lock.get("packages")
    root = packages.get("") if isinstance(packages, dict) else None
    target = (
        packages.get(f"node_modules/{PACKAGE_NAME}")
        if isinstance(packages, dict)
        else None
    )
    if (
        not isinstance(root, dict)
        or root.get("dependencies") != {PACKAGE_NAME: PACKAGE_VERSION}
        or not isinstance(target, dict)
        or target.get("version") != PACKAGE_VERSION
        or not isinstance(target.get("integrity"), str)
        or not target["integrity"].startswith("sha512-")
    ):
        _refuse("PRO_RUNTIME_SOURCE_INVALID")
    return package_bytes, lock_bytes, hashlib.sha256(lock_bytes).hexdigest()


def _runtime_inventory(root: Path) -> list[dict[str, object]]:
    inventory: list[dict[str, object]] = []

    def visit(directory: Path, relative: Path) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError:
            _refuse("PRO_RUNTIME_DRIFTED")
        for entry in entries:
            child_relative = relative / entry.name
            if child_relative.as_posix() == MANIFEST_NAME:
                continue
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError:
                _refuse("PRO_RUNTIME_DRIFTED")
            mode = stat.S_IMODE(metadata.st_mode)
            if stat.S_ISLNK(metadata.st_mode):
                _refuse("PRO_RUNTIME_SYMLINK")
            if metadata.st_uid != os.getuid() or mode & 0o077:
                _refuse("PRO_RUNTIME_MODE")
            if stat.S_ISDIR(metadata.st_mode):
                if mode != 0o700:
                    _refuse("PRO_RUNTIME_MODE")
                inventory.append(
                    {
                        "kind": "directory",
                        "path": child_relative.as_posix(),
                        "mode": "0700",
                        "sha256": None,
                        "size": 0,
                    }
                )
                visit(Path(entry.path), child_relative)
                continue
            if not stat.S_ISREG(metadata.st_mode) or mode not in {0o600, 0o700}:
                _refuse("PRO_RUNTIME_MODE")
            data = _read_regular(
                Path(entry.path), code="PRO_RUNTIME_DRIFTED", expected_mode=mode
            )
            inventory.append(
                {
                    "kind": "file",
                    "path": child_relative.as_posix(),
                    "mode": f"{mode:04o}",
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size": metadata.st_size,
                }
            )

    visit(root, Path())
    inventory.sort(key=lambda item: str(item["path"]))
    return inventory


def _validate_inventory(inventory: object, *, code: str) -> list[dict[str, object]]:
    if not isinstance(inventory, list):
        _refuse(code)
    previous = ""
    for item in inventory:
        if not isinstance(item, dict) or set(item) != INVENTORY_KEYS:
            _refuse(code)
        path = item.get("path")
        kind = item.get("kind")
        mode = item.get("mode")
        item_digest = item.get("sha256")
        size = item.get("size")
        if (
            not isinstance(path, str)
            or not path
            or path <= previous
            or Path(path).is_absolute()
            or ".." in Path(path).parts
            or kind not in {"directory", "file"}
            or mode not in {"0600", "0700"}
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
        ):
            _refuse(code)
        if kind == "directory":
            if item_digest is not None or size != 0 or mode != "0700":
                _refuse(code)
        elif (
            not isinstance(item_digest, str)
            or HEX_DIGEST.fullmatch(item_digest) is None
        ):
            _refuse(code)
        previous = path
    return inventory


def _validate_manifest(value: dict[str, object]) -> list[dict[str, object]]:
    if set(value) != MANIFEST_KEYS:
        _refuse("PRO_RUNTIME_DRIFTED")
    digest = value.get("package_lock_sha256")
    if (
        value.get("schema") != SCHEMA
        or value.get("story_id") != STORY_ID
        or value.get("package") != PACKAGE_NAME
        or value.get("version") != PACKAGE_VERSION
        or value.get("node_version") != NODE_VERSION
        or value.get("npm_version") != NPM_VERSION
        or not isinstance(digest, str)
        or HEX_DIGEST.fullmatch(digest) is None
    ):
        _refuse("PRO_RUNTIME_DRIFTED")
    return _validate_inventory(value.get("inventory"), code="PRO_RUNTIME_DRIFTED")


def _expected_inventory(lock_hash: str) -> list[dict[str, object]]:
    anchor = _json_object(
        _read_regular(
            SOURCE_ROOT / EXPECTED_INVENTORY_NAME,
            code="PRO_RUNTIME_SOURCE_INVALID",
            source_file=True,
        ),
        "PRO_RUNTIME_SOURCE_INVALID",
    )
    if (
        set(anchor) != MANIFEST_KEYS
        or anchor.get("schema") != EXPECTED_INVENTORY_SCHEMA
        or anchor.get("story_id") != STORY_ID
        or anchor.get("package") != PACKAGE_NAME
        or anchor.get("version") != PACKAGE_VERSION
        or anchor.get("node_version") != NODE_VERSION
        or anchor.get("npm_version") != NPM_VERSION
        or anchor.get("package_lock_sha256") != lock_hash
    ):
        _refuse("PRO_RUNTIME_SOURCE_INVALID")
    return _validate_inventory(
        anchor.get("inventory"), code="PRO_RUNTIME_SOURCE_INVALID"
    )


def verify_runtime() -> None:
    package_bytes, lock_bytes, lock_hash = _source_contract()
    expected_inventory = _expected_inventory(lock_hash)
    _safe_ancestors(PRIVATE_ROOT.parent, "PRO_RUNTIME_SYMLINK")
    try:
        private_metadata = PRIVATE_ROOT.lstat()
    except OSError:
        _refuse("PRO_RUNTIME_MISSING")
    if (
        not stat.S_ISDIR(private_metadata.st_mode)
        or private_metadata.st_uid != os.getuid()
        or stat.S_IMODE(private_metadata.st_mode) != 0o700
    ):
        _refuse("PRO_RUNTIME_MODE")
    try:
        runtime_metadata = RUNTIME_ROOT.lstat()
    except FileNotFoundError:
        _refuse("PRO_RUNTIME_MISSING")
    except OSError:
        _refuse("PRO_RUNTIME_DRIFTED")
    if stat.S_ISLNK(runtime_metadata.st_mode):
        _refuse("PRO_RUNTIME_SYMLINK")
    if (
        not stat.S_ISDIR(runtime_metadata.st_mode)
        or runtime_metadata.st_uid != os.getuid()
        or stat.S_IMODE(runtime_metadata.st_mode) != 0o700
    ):
        _refuse("PRO_RUNTIME_MODE")
    manifest = _json_object(
        _read_regular(
            RUNTIME_ROOT / MANIFEST_NAME,
            code="PRO_RUNTIME_DRIFTED",
            expected_mode=0o600,
        ),
        "PRO_RUNTIME_DRIFTED",
    )
    inventory = _validate_manifest(manifest)
    if manifest["package_lock_sha256"] != lock_hash:
        _refuse("PRO_RUNTIME_DRIFTED")
    runtime_package = _read_regular(
        RUNTIME_ROOT / "package.json",
        code="PRO_RUNTIME_DRIFTED",
        expected_mode=0o600,
    )
    runtime_lock = _read_regular(
        RUNTIME_ROOT / "package-lock.json",
        code="PRO_RUNTIME_DRIFTED",
        expected_mode=0o600,
    )
    if runtime_package != package_bytes or runtime_lock != lock_bytes:
        _refuse("PRO_RUNTIME_DRIFTED")
    if inventory != expected_inventory:
        _refuse("PRO_RUNTIME_DRIFTED")
    if _runtime_inventory(RUNTIME_ROOT) != expected_inventory:
        _refuse("PRO_RUNTIME_DRIFTED")
    installed_package = _json_object(
        _read_regular(
            RUNTIME_ROOT / "node_modules/@playwright/mcp/package.json",
            code="PRO_RUNTIME_DRIFTED",
            expected_mode=0o600,
        ),
        "PRO_RUNTIME_DRIFTED",
    )
    if (
        installed_package.get("name") != PACKAGE_NAME
        or installed_package.get("version") != PACKAGE_VERSION
    ):
        _refuse("PRO_RUNTIME_DRIFTED")
    _read_regular(
        RUNTIME_ROOT / "node_modules/@playwright/mcp/cli.js",
        code="PRO_RUNTIME_DRIFTED",
        expected_mode=0o600,
    )


def main() -> int:
    if sys.argv != [sys.argv[0]]:
        print(
            "chatgpt-pro-mcp-runtime: fail-closed verification refusal "
            "(PRO_RUNTIME_ARGUMENTS)",
            file=sys.stderr,
        )
        return 64
    try:
        verify_runtime()
    except VerificationRefusal as error:
        print(
            f"chatgpt-pro-mcp-runtime: fail-closed verification refusal ({error})",
            file=sys.stderr,
        )
        return 64
    except Exception:
        print(
            "chatgpt-pro-mcp-runtime: fail-closed verification refusal "
            "(PRO_RUNTIME_VERIFIER_FAILURE)",
            file=sys.stderr,
        )
        return 64
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

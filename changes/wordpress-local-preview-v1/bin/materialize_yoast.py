#!/usr/bin/env python3
"""Materialize one checksum-locked Yoast release into owner-private storage."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
import zipfile


MAXIMUM_ARCHIVE_BYTES = 8 * 1024 * 1024
MAXIMUM_MANIFEST_BYTES = 512 * 1024
EXPECTED_PLUGIN = "wordpress-seo"
EXPECTED_VERSION = "28.3"


class MaterializationError(RuntimeError):
    """Fail-closed local plugin materialization error."""


def fail(code: str) -> None:
    raise MaterializationError(code)


def read_regular(path: Path, maximum_bytes: int) -> bytes:
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError:
        fail("RAOS_WORDPRESS_PREVIEW_YOAST_INPUT_INVALID")
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size <= 0
        or metadata.st_size > maximum_bytes
        or len(payload) != metadata.st_size
    ):
        fail("RAOS_WORDPRESS_PREVIEW_YOAST_INPUT_INVALID")
    return payload


def load_json(path: Path, maximum_bytes: int) -> tuple[dict[str, object], bytes]:
    payload = read_regular(path, maximum_bytes)
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        fail("RAOS_WORDPRESS_PREVIEW_YOAST_INPUT_INVALID")
    if type(decoded) is not dict:
        fail("RAOS_WORDPRESS_PREVIEW_YOAST_INPUT_INVALID")
    return decoded, payload


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def safe_member(name: str) -> PurePosixPath:
    if not name or "\\" in name or "\x00" in name:
        fail("RAOS_WORDPRESS_PREVIEW_YOAST_ARCHIVE_INVALID")
    value = PurePosixPath(name)
    if (
        value.is_absolute()
        or value.as_posix() != name.rstrip("/")
        or any(part in {"", ".", ".."} for part in value.parts)
        or value.parts[0] != EXPECTED_PLUGIN
    ):
        fail("RAOS_WORDPRESS_PREVIEW_YOAST_ARCHIVE_INVALID")
    return value


def validate_lock(lock: dict[str, object], archive: bytes, manifest: bytes) -> None:
    archive_contract = lock.get("archive")
    manifest_contract = lock.get("official_checksum_api")
    if (
        lock.get("schema") != "RAOS_WORDPRESS_PLUGIN_LOCK_V1"
        or lock.get("plugin_slug") != EXPECTED_PLUGIN
        or lock.get("version") != EXPECTED_VERSION
        or type(archive_contract) is not dict
        or type(manifest_contract) is not dict
        or archive_contract.get("byte_length") != len(archive)
        or archive_contract.get("sha256") != sha256(archive)
        or manifest_contract.get("manifest_byte_length") != len(manifest)
        or manifest_contract.get("manifest_sha256") != sha256(manifest)
    ):
        fail("RAOS_WORDPRESS_PREVIEW_YOAST_LOCK_MISMATCH")


def expected_checksums(manifest: bytes) -> dict[str, str]:
    try:
        decoded = json.loads(manifest)
    except (UnicodeDecodeError, json.JSONDecodeError):
        fail("RAOS_WORDPRESS_PREVIEW_YOAST_CHECKSUMS_INVALID")
    files = decoded.get("files") if type(decoded) is dict else None
    if (
        decoded.get("plugin") != EXPECTED_PLUGIN
        or decoded.get("version") != EXPECTED_VERSION
        or type(files) is not dict
        or len(files) != 1952
    ):
        fail("RAOS_WORDPRESS_PREVIEW_YOAST_CHECKSUMS_INVALID")
    result: dict[str, str] = {}
    for raw_name, hashes in files.items():
        if type(raw_name) is not str or type(hashes) is not dict:
            fail("RAOS_WORDPRESS_PREVIEW_YOAST_CHECKSUMS_INVALID")
        relative = PurePosixPath(raw_name)
        digest = hashes.get("sha256")
        if (
            relative.is_absolute()
            or relative.as_posix() != raw_name
            or any(part in {"", ".", ".."} for part in relative.parts)
            or type(digest) is not str
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            fail("RAOS_WORDPRESS_PREVIEW_YOAST_CHECKSUMS_INVALID")
        result[raw_name] = digest
    return result


def archive_files(archive_path: Path, checksums: dict[str, str]) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            for member in archive.infolist():
                relative = safe_member(member.filename)
                mode = member.external_attr >> 16
                if stat.S_ISLNK(mode):
                    fail("RAOS_WORDPRESS_PREVIEW_YOAST_ARCHIVE_INVALID")
                if member.is_dir():
                    continue
                if not stat.S_ISREG(mode) and mode != 0:
                    fail("RAOS_WORDPRESS_PREVIEW_YOAST_ARCHIVE_INVALID")
                plugin_relative = PurePosixPath(*relative.parts[1:]).as_posix()
                if plugin_relative in result or plugin_relative not in checksums:
                    fail("RAOS_WORDPRESS_PREVIEW_YOAST_ARCHIVE_INVALID")
                payload = archive.read(member)
                if sha256(payload) != checksums[plugin_relative]:
                    fail("RAOS_WORDPRESS_PREVIEW_YOAST_ARCHIVE_INVALID")
                result[plugin_relative] = payload
    except (OSError, zipfile.BadZipFile, RuntimeError):
        fail("RAOS_WORDPRESS_PREVIEW_YOAST_ARCHIVE_INVALID")
    if set(result) != set(checksums):
        fail("RAOS_WORDPRESS_PREVIEW_YOAST_ARCHIVE_INVALID")
    return result


def validate_materialized(root: Path, checksums: dict[str, str]) -> bool:
    if not root.exists():
        return False
    try:
        metadata = root.lstat()
    except OSError:
        fail("RAOS_WORDPRESS_PREVIEW_YOAST_RUNTIME_INVALID")
    if root.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        fail("RAOS_WORDPRESS_PREVIEW_YOAST_RUNTIME_INVALID")
    observed: dict[str, str] = {}
    try:
        for candidate in sorted(root.rglob("*")):
            item = candidate.lstat()
            if candidate.is_symlink():
                fail("RAOS_WORDPRESS_PREVIEW_YOAST_RUNTIME_INVALID")
            if stat.S_ISDIR(item.st_mode):
                continue
            if not stat.S_ISREG(item.st_mode):
                fail("RAOS_WORDPRESS_PREVIEW_YOAST_RUNTIME_INVALID")
            relative = candidate.relative_to(root).as_posix()
            observed[relative] = sha256(candidate.read_bytes())
    except OSError:
        fail("RAOS_WORDPRESS_PREVIEW_YOAST_RUNTIME_INVALID")
    if observed != checksums:
        fail("RAOS_WORDPRESS_PREVIEW_YOAST_RUNTIME_INVALID")
    return True


def materialize(output_parent: Path, files: dict[str, bytes], checksums: dict[str, str]) -> None:
    destination = output_parent / EXPECTED_PLUGIN
    if validate_materialized(destination, checksums):
        return
    try:
        output_parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if output_parent.is_symlink() or not output_parent.is_dir():
            fail("RAOS_WORDPRESS_PREVIEW_YOAST_OUTPUT_INVALID")
        os.chmod(output_parent, 0o700)
        with tempfile.TemporaryDirectory(
            prefix=".wordpress-seo-28.3-", dir=output_parent
        ) as temporary_name:
            temporary = Path(temporary_name)
            plugin_root = temporary / EXPECTED_PLUGIN
            plugin_root.mkdir(mode=0o755)
            for relative, payload in files.items():
                target = plugin_root.joinpath(*PurePosixPath(relative).parts)
                target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
                descriptor = os.open(
                    target,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                    0o644,
                )
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(payload)
            validate_materialized(plugin_root, checksums)
            try:
                os.rename(plugin_root, destination)
            except FileExistsError:
                validate_materialized(destination, checksums)
    except OSError:
        fail("RAOS_WORDPRESS_PREVIEW_YOAST_OUTPUT_INVALID")
    validate_materialized(destination, checksums)


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--checksums", required=True, type=Path)
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--output-parent", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        lock, _ = load_json(arguments.lock, MAXIMUM_MANIFEST_BYTES)
        archive = read_regular(arguments.archive, MAXIMUM_ARCHIVE_BYTES)
        _manifest_object, manifest = load_json(
            arguments.checksums, MAXIMUM_MANIFEST_BYTES
        )
        validate_lock(lock, archive, manifest)
        checksums = expected_checksums(manifest)
        files = archive_files(arguments.archive, checksums)
        materialize(arguments.output_parent, files, checksums)
        print("RAOS_WORDPRESS_PREVIEW_YOAST_28_3_READY")
        return 0
    except MaterializationError as error:
        print(str(error), file=sys.stderr)
        return 69


if __name__ == "__main__":
    raise SystemExit(main())

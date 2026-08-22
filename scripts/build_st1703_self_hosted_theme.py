#!/usr/bin/env python3
"""Validate and deterministically package the ST-1703 child theme.

Owner generator: scripts/build_st1703_self_hosted_theme.py
Package command: make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile theme-package
Read-only check: make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile theme-check
"""

from __future__ import annotations

import argparse
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Any, NoReturn, cast
import zipfile


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
THEME_SLUG = "kurashinoshirube-child"
THEME_ROOT = (
    REPOSITORY_ROOT / "changes/st-1703/self-hosted-minimum-start-v1/theme" / THEME_SLUG
)
MANIFEST_PATH = THEME_ROOT / "raos-assets.v1.json"
OUTPUT_PATH = (
    REPOSITORY_ROOT
    / "changes/st-1703/self-hosted-minimum-start-v1/generated"
    / f"{THEME_SLUG}.zip"
)
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_PACKAGE_BYTES = 16 * 1024 * 1024

_MANIFEST_KEYS = frozenset(
    {
        "schema",
        "theme_slug",
        "source_files",
        "required_images",
        "generated_by",
        "package_command",
        "check_command",
    }
)
_IMAGE_KEYS = frozenset({"path", "status", "sha256", "alt", "prompt", "usage"})
_TEMPLATE_PART_KEYS = frozenset({"slug", "tagName"})
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_REMOTE_REFERENCE = re.compile(r"(?:https?:)?//", re.ASCII | re.IGNORECASE)
_TEMPLATE_PART_BLOCK = re.compile(
    r"<!--\s*wp:template-part\s+(\{[^\r\n]*\})\s*/-->", re.ASCII
)
_TEMPLATE_PART_OPEN = re.compile(r"<!--\s*wp:template-part\b", re.ASCII)
_HEADER_FOOTER_ELEMENT = re.compile(
    r"<\s*/?\s*(?:header|footer)\b", re.ASCII | re.IGNORECASE
)
_HEADER_FOOTER_TAG_NAME = re.compile(r'"tagName"\s*:\s*"(?:header|footer)"', re.ASCII)
_FORBIDDEN_SOURCE = re.compile(
    r"(?:wp_remote_|curl_|file_get_contents\s*\(|<script[^>]+src=|"
    r"fetch\s*\(|XMLHttpRequest|navigator\.sendBeacon|@import)",
    re.ASCII | re.IGNORECASE,
)
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
_FILE_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
_PACKAGE_COMMAND = (
    "make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile theme-package"
)
_CHECK_COMMAND = (
    "make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile theme-check"
)


class ThemeBuildFailure(RuntimeError):
    pass


def _fail(code: str) -> NoReturn:
    raise ThemeBuildFailure(code) from None


class _DuplicateKey(ValueError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if type(key) is not str or key in value:
            raise _DuplicateKey
        value[key] = item
    return value


def _safe_relative(value: object) -> str:
    if type(value) is not str or not value or value != value.strip() or "\\" in value:
        _fail("THEME_PATH_INVALID")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        _fail("THEME_PATH_INVALID")
    return path.as_posix()


def _identity(details: os.stat_result) -> tuple[int, ...]:
    return (
        details.st_dev,
        details.st_ino,
        details.st_mode,
        details.st_uid,
        details.st_gid,
        details.st_nlink,
        details.st_size,
        details.st_mtime_ns,
        details.st_ctime_ns,
    )


def _same_named_object(
    details: os.stat_result,
    *,
    parent_fd: int,
    name: str,
    error_code: str,
) -> None:
    try:
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError:
        _fail(error_code)
    if _identity(named) != _identity(details):
        _fail(error_code)


@contextmanager
def _open_absolute_directory(
    path: Path, *, create: bool = False
) -> Generator[int, None, None]:
    if not path.is_absolute() or any(
        part in {"", ".", ".."} for part in path.parts[1:]
    ):
        _fail("THEME_ROOT_INVALID")
    try:
        descriptor = os.open("/", _DIRECTORY_FLAGS)
    except OSError:
        _fail("THEME_ROOT_INVALID")
    try:
        for part in path.parts[1:]:
            try:
                child = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    _fail("THEME_ROOT_INVALID")
                try:
                    os.mkdir(part, mode=0o755, dir_fd=descriptor)
                    os.fsync(descriptor)
                    child = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
                except OSError:
                    _fail("THEME_ROOT_INVALID")
            except OSError:
                _fail("THEME_ROOT_INVALID")
            try:
                opened = os.fstat(child)
                if not stat.S_ISDIR(opened.st_mode):
                    _fail("THEME_ROOT_INVALID")
                _same_named_object(
                    opened,
                    parent_fd=descriptor,
                    name=part,
                    error_code="THEME_ROOT_INVALID",
                )
            except BaseException:
                os.close(child)
                raise
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


@contextmanager
def _open_parent_at(
    root_fd: int, relative: str
) -> Generator[tuple[int, str], None, None]:
    parts = PurePosixPath(_safe_relative(relative)).parts
    try:
        descriptor = os.dup(root_fd)
    except OSError:
        _fail("THEME_FILE_INVALID")
    try:
        for part in parts[:-1]:
            child: int | None = None
            try:
                child = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
                opened = os.fstat(child)
                if not stat.S_ISDIR(opened.st_mode):
                    _fail("THEME_FILE_INVALID")
                _same_named_object(
                    opened,
                    parent_fd=descriptor,
                    name=part,
                    error_code="THEME_FILE_INVALID",
                )
            except OSError:
                _fail("THEME_FILE_INVALID")
            except BaseException:
                if child is not None:
                    os.close(child)
                raise
            os.close(descriptor)
            descriptor = child
        yield descriptor, parts[-1]
    finally:
        os.close(descriptor)


def _read_regular_at(
    root_fd: int,
    relative: str,
    *,
    max_bytes: int = MAX_FILE_BYTES,
    error_code: str = "THEME_FILE_INVALID",
) -> tuple[bytes, tuple[int, ...]]:
    with _open_parent_at(root_fd, relative) as (parent_fd, name):
        try:
            descriptor = os.open(name, _FILE_FLAGS, dir_fd=parent_fd)
        except OSError:
            _fail(error_code)
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.getuid()
                or before.st_nlink != 1
                or not 1 <= before.st_size <= max_bytes
            ):
                _fail(error_code)
            _same_named_object(
                before, parent_fd=parent_fd, name=name, error_code=error_code
            )
            chunks: list[bytes] = []
            remaining = before.st_size
            while remaining:
                try:
                    chunk = os.read(descriptor, min(remaining, 64 * 1024))
                except OSError:
                    _fail(error_code)
                if not chunk:
                    _fail(error_code)
                chunks.append(chunk)
                remaining -= len(chunk)
            try:
                if os.read(descriptor, 1):
                    _fail(error_code)
                after = os.fstat(descriptor)
            except OSError:
                _fail(error_code)
            if _identity(after) != _identity(before):
                _fail(error_code)
            _same_named_object(
                after, parent_fd=parent_fd, name=name, error_code=error_code
            )
            payload = b"".join(chunks)
            if len(payload) != before.st_size:
                _fail(error_code)
            return payload, _identity(before)
        finally:
            os.close(descriptor)


def _inventory_at(root_fd: int) -> dict[str, tuple[str, tuple[int, ...]]]:
    inventory: dict[str, tuple[str, tuple[int, ...]]] = {}

    def visit(directory_fd: int, prefix: str) -> None:
        try:
            names = sorted(os.listdir(directory_fd))
        except OSError:
            _fail("THEME_INVENTORY_INVALID")
        for name in names:
            if not name or "/" in name or name in {".", ".."}:
                _fail("THEME_INVENTORY_INVALID")
            relative = f"{prefix}/{name}" if prefix else name
            try:
                named_before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except OSError:
                _fail("THEME_INVENTORY_INVALID")
            if stat.S_ISDIR(named_before.st_mode):
                try:
                    child = os.open(name, _DIRECTORY_FLAGS, dir_fd=directory_fd)
                except OSError:
                    _fail("THEME_INVENTORY_INVALID")
                try:
                    opened = os.fstat(child)
                    if _identity(opened) != _identity(named_before):
                        _fail("THEME_INVENTORY_INVALID")
                    inventory[f"{relative}/"] = ("directory", _identity(opened))
                    visit(child, relative)
                    after = os.fstat(child)
                    if _identity(after) != _identity(opened):
                        _fail("THEME_INVENTORY_CHANGED")
                    _same_named_object(
                        after,
                        parent_fd=directory_fd,
                        name=name,
                        error_code="THEME_INVENTORY_CHANGED",
                    )
                finally:
                    os.close(child)
            elif stat.S_ISREG(named_before.st_mode):
                if named_before.st_uid != os.getuid() or named_before.st_nlink != 1:
                    _fail("THEME_FILE_INVALID")
                inventory[relative] = ("file", _identity(named_before))
            else:
                _fail("THEME_FILE_INVALID")

    visit(root_fd, "")
    return inventory


def _parse_manifest(payload: bytes) -> dict[str, object]:
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=lambda ignored: (_ for _ in ()).throw(ValueError()),
        )
    except UnicodeError, ValueError, TypeError, RecursionError:
        _fail("THEME_MANIFEST_INVALID")
    if type(value) is not dict:
        _fail("THEME_MANIFEST_INVALID")
    manifest = cast(dict[str, object], value)
    if (
        frozenset(manifest) != _MANIFEST_KEYS
        or manifest["schema"] != "RAOS_WORDPRESS_THEME_ASSETS_V1"
        or manifest["theme_slug"] != THEME_SLUG
        or manifest["generated_by"] != "scripts/build_st1703_self_hosted_theme.py"
        or manifest["package_command"] != _PACKAGE_COMMAND
        or manifest["check_command"] != _CHECK_COMMAND
        or type(manifest["source_files"]) is not list
        or type(manifest["required_images"]) is not list
    ):
        _fail("THEME_MANIFEST_INVALID")
    return manifest


def _source_inventory(
    manifest: dict[str, object],
    inventory: dict[str, tuple[str, tuple[int, ...]]],
) -> tuple[str, ...]:
    paths = tuple(
        _safe_relative(value) for value in cast(list[object], manifest["source_files"])
    )
    if len(paths) != len(set(paths)) or tuple(sorted(paths)) != paths:
        _fail("THEME_MANIFEST_INVALID")
    actual = tuple(
        sorted(
            path
            for path, (kind, _identity_value) in inventory.items()
            if kind == "file" and not path.startswith("assets/images/")
        )
    )
    if actual != paths:
        _fail("THEME_INVENTORY_MISMATCH")
    return paths


def _validate_source_file(relative: str, payload: bytes) -> None:
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeError:
        _fail("THEME_SOURCE_INVALID")
    inspected = text.replace('"$schema": "https://schemas.wp.org/trunk/theme.json"', "")
    if _REMOTE_REFERENCE.search(inspected) is not None:
        _fail("THEME_REMOTE_LOAD_FORBIDDEN")
    if _FORBIDDEN_SOURCE.search(text) is not None:
        _fail("THEME_CAPABILITY_FORBIDDEN")
    if relative == "assets/theme.css" and (
        "@media (prefers-reduced-motion: reduce)" not in text
        or ":focus-visible" not in text
        or ".raos-reveal-ready .raos-reveal:not(.is-visible)" not in text
        or ".raos-reveal-ready .raos-reveal" not in text
        or ".raos-reveal {\n  opacity: 1;\n  transform: none;" not in text
    ):
        _fail("THEME_ACCESSIBILITY_INVALID")
    if relative == "assets/theme.js" and (
        'root.classList.add("raos-reveal-ready")' not in text
        or 'root.classList.remove("raos-reveal-ready")' not in text
        or "const revealAll = () =>" not in text
        or "if (reduced ||" not in text
    ):
        _fail("THEME_ACCESSIBILITY_INVALID")
    if relative == "style.css" and (
        "Theme Name: 暮らしのしるべ Editorial" not in text
        or "Template: twentytwentyfive" not in text
    ):
        _fail("THEME_PARENT_INVALID")


def _validate_semantic_landmarks(payloads: Mapping[str, bytes]) -> None:
    expected_template_parts = (("header", "header"), ("footer", "footer"))
    for relative in ("templates/front-page.html", "templates/single.html"):
        try:
            text = payloads[relative].decode("utf-8", errors="strict")
        except KeyError, UnicodeError:
            _fail("THEME_SEMANTIC_LANDMARK_INVALID")
        matches = tuple(_TEMPLATE_PART_BLOCK.finditer(text))
        if (
            len(matches) != len(tuple(_TEMPLATE_PART_OPEN.finditer(text)))
            or _HEADER_FOOTER_ELEMENT.search(text) is not None
        ):
            _fail("THEME_SEMANTIC_LANDMARK_INVALID")
        actual: list[tuple[object, object]] = []
        for match in matches:
            try:
                attributes = json.loads(
                    match.group(1),
                    object_pairs_hook=_pairs,
                    parse_constant=lambda ignored: (_ for _ in ()).throw(ValueError()),
                )
            except ValueError, TypeError, RecursionError:
                _fail("THEME_SEMANTIC_LANDMARK_INVALID")
            if type(attributes) is not dict:
                _fail("THEME_SEMANTIC_LANDMARK_INVALID")
            attribute_map = cast(dict[str, object], attributes)
            if frozenset(attribute_map) != _TEMPLATE_PART_KEYS:
                _fail("THEME_SEMANTIC_LANDMARK_INVALID")
            actual.append((attribute_map.get("slug"), attribute_map.get("tagName")))
        if tuple(actual) != expected_template_parts:
            _fail("THEME_SEMANTIC_LANDMARK_INVALID")

    for relative in ("parts/header.html", "parts/footer.html"):
        try:
            text = payloads[relative].decode("utf-8", errors="strict")
        except KeyError, UnicodeError:
            _fail("THEME_SEMANTIC_LANDMARK_INVALID")
        stripped = text.strip()
        block_comment_end = stripped.find("-->")
        if (
            not stripped.startswith("<!-- wp:group ")
            or block_comment_end < 0
            or not stripped[block_comment_end + 3 :].lstrip().startswith("<div")
            or not stripped.endswith("</div>\n<!-- /wp:group -->")
            or _TEMPLATE_PART_OPEN.search(text) is not None
            or _HEADER_FOOTER_ELEMENT.search(text) is not None
            or _HEADER_FOOTER_TAG_NAME.search(text) is not None
        ):
            _fail("THEME_SEMANTIC_LANDMARK_INVALID")


@dataclass(frozen=True)
class _ThemeSnapshot:
    archive_files: tuple[tuple[str, bytes], ...]
    pending_asset_count: int
    source_file_count: int

    @property
    def package_ready(self) -> bool:
        return self.pending_asset_count == 0


def _validated_payload_snapshot(payload_values: Mapping[str, bytes]) -> _ThemeSnapshot:
    payloads = dict(payload_values)
    if not payloads or any(
        _safe_relative(path) != path or type(payload) is not bytes
        for path, payload in payloads.items()
    ):
        _fail("THEME_INVENTORY_INVALID")
    manifest_payload = payloads.get(MANIFEST_PATH.name)
    if manifest_payload is None:
        _fail("THEME_MANIFEST_INVALID")
    manifest = _parse_manifest(manifest_payload)
    inventory: dict[str, tuple[str, tuple[int, ...]]] = {
        path: ("file", ()) for path in payloads
    }
    paths = _source_inventory(manifest, inventory)
    for relative in paths:
        _validate_source_file(relative, payloads[relative])
    _validate_semantic_landmarks(payloads)

    images = cast(list[object], manifest["required_images"])
    if len(images) != 2:
        _fail("THEME_MANIFEST_INVALID")
    image_paths: set[str] = set()
    pending = 0
    for item in images:
        if type(item) is not dict:
            _fail("THEME_MANIFEST_INVALID")
        image = cast(dict[str, object], item)
        path = _safe_relative(image.get("path"))
        if (
            frozenset(image) != _IMAGE_KEYS
            or path in image_paths
            or not path.startswith("assets/images/")
            or not path.endswith(".webp")
            or type(image.get("alt")) is not str
            or not cast(str, image["alt"]).strip()
            or type(image.get("prompt")) is not str
            or not cast(str, image["prompt"]).strip()
            or type(image.get("usage")) is not str
            or not cast(str, image["usage"]).strip()
            or image.get("status") not in {"PENDING_FINAL_ASSET", "FINAL"}
        ):
            _fail("THEME_MANIFEST_INVALID")
        image_paths.add(path)
        if image["status"] == "PENDING_FINAL_ASSET":
            if image["sha256"] is not None or path in payloads:
                _fail("THEME_PENDING_ASSET_INVALID")
            pending += 1
            continue
        if (
            type(image["sha256"]) is not str
            or _SHA256.fullmatch(image["sha256"]) is None
        ):
            _fail("THEME_MANIFEST_INVALID")
        payload = payloads.get(path)
        if (
            payload is None
            or len(payload) < 12
            or payload[:4] != b"RIFF"
            or payload[8:12] != b"WEBP"
            or hashlib.sha256(payload).hexdigest() != image["sha256"]
        ):
            _fail("THEME_FINAL_ASSET_INVALID")

    if set(payloads) != {*paths, *image_paths.intersection(payloads)}:
        _fail("THEME_INVENTORY_MISMATCH")
    return _ThemeSnapshot(
        archive_files=tuple(sorted(payloads.items())),
        pending_asset_count=pending,
        source_file_count=len(paths),
    )


def _validated_snapshot() -> _ThemeSnapshot:
    with _open_absolute_directory(THEME_ROOT) as theme_fd:
        before = _inventory_at(theme_fd)
        payloads: dict[str, bytes] = {}
        for relative, (kind, expected_identity) in sorted(before.items()):
            if kind != "file":
                continue
            payload, identity = _read_regular_at(theme_fd, relative)
            if identity != expected_identity:
                _fail("THEME_INVENTORY_CHANGED")
            payloads[relative] = payload
        snapshot = _validated_payload_snapshot(payloads)
        if _inventory_at(theme_fd) != before:
            _fail("THEME_INVENTORY_CHANGED")
        return snapshot


def source_check() -> dict[str, object]:
    snapshot = _validated_snapshot()
    return _source_check_result(snapshot)


def source_check_from_verified_files(
    payloads: Mapping[str, bytes],
) -> dict[str, object]:
    """Validate already identity-bound bytes without reopening repository paths."""

    return _source_check_result(_validated_payload_snapshot(payloads))


def _source_check_result(snapshot: _ThemeSnapshot) -> dict[str, object]:
    return {
        "asset_status": (
            "PENDING_FINAL_ASSETS" if not snapshot.package_ready else "FINAL"
        ),
        "network_requests": 0,
        "package_ready": snapshot.package_ready,
        "pending_asset_count": snapshot.pending_asset_count,
        "source_file_count": snapshot.source_file_count,
        "status": "SOURCE_VALID",
        "theme_slug": THEME_SLUG,
    }


def package_bytes() -> bytes:
    snapshot = _validated_snapshot()
    if not snapshot.package_ready:
        _fail("THEME_FINAL_ASSET_MISSING")
    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for relative, payload in snapshot.archive_files:
            info = zipfile.ZipInfo(
                filename=f"{THEME_SLUG}/{relative}",
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload)
    payload = buffer.getvalue()
    if not payload or len(payload) > MAX_PACKAGE_BYTES:
        _fail("THEME_PACKAGE_INVALID")
    return payload


def _write_package(payload: bytes) -> None:
    if not payload or len(payload) > MAX_PACKAGE_BYTES:
        _fail("THEME_PACKAGE_INVALID")
    with _open_absolute_directory(OUTPUT_PATH.parent, create=True) as parent_fd:
        try:
            existing = os.stat(
                OUTPUT_PATH.name, dir_fd=parent_fd, follow_symlinks=False
            )
        except FileNotFoundError:
            existing = None
        except OSError:
            _fail("THEME_PACKAGE_WRITE_FAILED")
        if existing is not None and (
            not stat.S_ISREG(existing.st_mode)
            or existing.st_uid != os.getuid()
            or existing.st_nlink != 1
        ):
            _fail("THEME_PACKAGE_WRITE_FAILED")

        temporary = f".{OUTPUT_PATH.name}.preparing"
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                0o644,
                dir_fd=parent_fd,
            )
        except OSError:
            _fail("THEME_PACKAGE_WRITE_FAILED")
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.getuid()
                or before.st_nlink != 1
            ):
                _fail("THEME_PACKAGE_WRITE_FAILED")
            offset = 0
            while offset < len(payload):
                try:
                    written = os.write(descriptor, payload[offset:])
                except OSError:
                    _fail("THEME_PACKAGE_WRITE_FAILED")
                if written <= 0:
                    _fail("THEME_PACKAGE_WRITE_FAILED")
                offset += written
            os.fsync(descriptor)
            after = os.fstat(descriptor)
            if (
                after.st_dev != before.st_dev
                or after.st_ino != before.st_ino
                or after.st_uid != before.st_uid
                or after.st_nlink != before.st_nlink
                or after.st_size != len(payload)
            ):
                _fail("THEME_PACKAGE_WRITE_FAILED")
            _same_named_object(
                after,
                parent_fd=parent_fd,
                name=temporary,
                error_code="THEME_PACKAGE_WRITE_FAILED",
            )
            os.replace(
                temporary,
                OUTPUT_PATH.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            try:
                published = os.stat(
                    OUTPUT_PATH.name, dir_fd=parent_fd, follow_symlinks=False
                )
            except OSError:
                _fail("THEME_PACKAGE_WRITE_FAILED")
            if (
                not stat.S_ISREG(published.st_mode)
                or published.st_dev != after.st_dev
                or published.st_ino != after.st_ino
                or published.st_uid != after.st_uid
                or published.st_gid != after.st_gid
                or published.st_nlink != after.st_nlink
                or published.st_size != after.st_size
            ):
                _fail("THEME_PACKAGE_WRITE_FAILED")
            _same_named_object(
                published,
                parent_fd=parent_fd,
                name=OUTPUT_PATH.name,
                error_code="THEME_PACKAGE_WRITE_FAILED",
            )
            os.fsync(parent_fd)
        finally:
            os.close(descriptor)
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass


def _read_output_package() -> bytes:
    try:
        with _open_absolute_directory(OUTPUT_PATH.parent) as parent_fd:
            payload, _identity_value = _read_regular_at(
                parent_fd,
                OUTPUT_PATH.name,
                max_bytes=MAX_PACKAGE_BYTES,
                error_code="THEME_PACKAGE_DRIFT",
            )
            return payload
    except ThemeBuildFailure:
        _fail("THEME_PACKAGE_DRIFT")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--source-check", action="store_true")
    group.add_argument("--package", action="store_true")
    group.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.source_check:
            result = source_check()
        else:
            payload = package_bytes()
            if arguments.package:
                _write_package(payload)
            elif _read_output_package() != payload:
                _fail("THEME_PACKAGE_DRIFT")
            result = {
                "package_bytes": len(payload),
                "package_sha256": hashlib.sha256(payload).hexdigest(),
                "status": "PACKAGED" if arguments.package else "PACKAGE_VALID",
                "theme_slug": THEME_SLUG,
            }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except ThemeBuildFailure as error:
        print(
            json.dumps(
                {"reason_code": str(error), "status": "BLOCKED"},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())

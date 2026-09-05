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
OUTPUT_REPOSITORY_ROOT = REPOSITORY_ROOT
_PRIVATE_OUTPUT_PARTS = (
    ".secrets",
    "self-hosted-theme-packages",
)
OUTPUT_DIRECTORY = OUTPUT_REPOSITORY_ROOT.joinpath(*_PRIVATE_OUTPUT_PARTS)
OUTPUT_PATH = OUTPUT_DIRECTORY / f"{THEME_SLUG}.zip"
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_PACKAGE_BYTES = 16 * 1024 * 1024
PRIVATE_OUTPUT_DIRECTORY_MODE = 0o700
PRIVATE_OUTPUT_FILE_MODE = 0o600
EXPECTED_THEME_CSS_SHA256 = (
    "89accbdfabc159c566d78e83abea8d8a4cbe1478421fff1c0da6aeb768898973"
)
EXPECTED_THEME_FUNCTIONS_SHA256 = (
    "1b42f0cde0a82496671d2b659483ecf3e66c6ba6d161143375f47eb2786c8e88"
)
EXPECTED_THEME_VERSION = "1.0.2"
FIRST_ARTICLE_IMAGE_RELATIVE_PATH = "assets/images/article-suitcase-guide.webp"
FIRST_ARTICLE_IMAGE_ALT = "機内持ち込み手荷物の寸法を考えるための抽象的な旅支度の情景"
FIRST_ARTICLE_IMAGE_USAGE = "first article inline lead image"
FIRST_ARTICLE_SHORTCODE_TAG = "kurashinoshirube_first_article_lead_image"
FIRST_ARTICLE_LEAD_IMAGE_CLASS = "raos-first-article-lead-image"
FIRST_ARTICLE_IMAGE_WIDTH = 1600
FIRST_ARTICLE_IMAGE_HEIGHT = 900
FIRST_ARTICLE_SLUG = "carry-on-suitcase-comparison"
FIRST_ARTICLE_TARGET_ORIGIN = "https://kurashinoshirube.com"
FIRST_ARTICLE_TARGET_HOST = FIRST_ARTICLE_TARGET_ORIGIN.removeprefix("https://")
FIRST_ARTICLE_THEME_SLUG = "kurashinoshirube-child"
FIRST_ARTICLE_EMPTY_CONTENT_GUARD = "! in_array($content, array(null, ''), true)"
FIRST_ARTICLE_RESPONSIVE_FIGURE_RULE = f"""figure.{FIRST_ARTICLE_LEAD_IMAGE_CLASS} {{
  margin-inline: 0;
  max-width: 100%;
}}"""
FIRST_ARTICLE_RESPONSIVE_IMAGE_RULE = f"""figure.{FIRST_ARTICLE_LEAD_IMAGE_CLASS} > img {{
  display: block;
  height: auto;
  max-width: 100%;
  width: 100%;
}}"""
_COMPARISON_OVERFLOW_RULE = """.raos-comparison {
  overflow-x: auto;
}"""
FIRST_ARTICLE_RESPONSIVE_SEQUENCE = (
    f"{FIRST_ARTICLE_RESPONSIVE_FIGURE_RULE}\n\n"
    f"{FIRST_ARTICLE_RESPONSIVE_IMAGE_RULE}\n\n"
    f"{_COMPARISON_OVERFLOW_RULE}"
)
FIRST_ARTICLE_TITLE = (
    "機内持ち込み対応スーツケース3モデルを条件別比較｜軽さ・容量・開き方で選ぶ"
)
_EXPECTED_IMAGE_DELIVERY: dict[str, str] = {
    "assets/images/home-hero.webp": "THEME_CSS_BACKGROUND",
    FIRST_ARTICLE_IMAGE_RELATIVE_PATH: "FIRST_ARTICLE_THEME_SHORTCODE",
}

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
_IMAGE_KEYS = frozenset(
    {"path", "status", "sha256", "alt", "delivery", "prompt", "usage"}
)
_TEMPLATE_PART_KEYS = frozenset({"slug", "tagName"})
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_CSS_HEX_COLOR = re.compile(r"#[0-9a-f]{6}\Z", re.ASCII)
_CSS_COLOR_PROPERTY_TOKEN = re.compile(
    r"(?<![-A-Za-z0-9_])(?:outline-color|color)[ \t\r\n]*:",
    re.ASCII | re.IGNORECASE,
)
_CSS_COLOR_DECLARATION = re.compile(
    r"(?<![-A-Za-z0-9_])(?P<property>outline-color|color)[ \t\r\n]*:"
    r"[ \t\r\n]*(?P<value>[^;{}]+?)[ \t\r\n]*(?=[;}])",
    re.ASCII | re.IGNORECASE,
)
_CSS_BACKGROUND_PROPERTY_TOKEN = re.compile(
    r"(?<![-A-Za-z0-9_])background(?:-[A-Za-z0-9_-]+)?[ \t\r\n]*:",
    re.ASCII | re.IGNORECASE,
)
_CSS_BACKGROUND_DECLARATION = re.compile(
    r"(?<![-A-Za-z0-9_])(?P<property>background(?:-[A-Za-z0-9_-]+)?)"
    r"[ \t\r\n]*:[ \t\r\n]*(?P<value>[^;{}]+?)[ \t\r\n]*(?=[;}])",
    re.ASCII | re.IGNORECASE,
)
_CSS_OUTLINE_PROPERTY_TOKEN = re.compile(
    r"(?<![-A-Za-z0-9_])outline(?:-[A-Za-z0-9_-]+)?[ \t\r\n]*:",
    re.ASCII | re.IGNORECASE,
)
_CSS_OUTLINE_DECLARATION = re.compile(
    r"(?<![-A-Za-z0-9_])(?P<property>outline(?:-[A-Za-z0-9_-]+)?)"
    r"[ \t\r\n]*:[ \t\r\n]*(?P<value>[^;{}]+?)[ \t\r\n]*(?=[;}])",
    re.ASCII | re.IGNORECASE,
)
_CSS_FLAT_RULE = re.compile(
    r"(?P<selector>[^{}]+)\{(?P<body>[^{}]*)\}",
    re.ASCII,
)
_CSS_FIGURE_OR_IMAGE_SELECTOR = re.compile(
    r"(?<![-A-Za-z0-9_])(?:figure|img)(?![-A-Za-z0-9_])",
    re.ASCII | re.IGNORECASE,
)
_CSS_OVERFLOW_PROPERTY_TOKEN = re.compile(
    r"(?<![-A-Za-z0-9_])overflow(?:-[xy])?[ \t\r\n]*:",
    re.ASCII | re.IGNORECASE,
)
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
_WEBP_MAX_CHUNKS = 16
_WEBP_VP8X_ALLOWED_FLAGS = 0x3C
_WEBP_VP8X_ICC_FLAG = 0x20
_WEBP_VP8X_ALPHA_FLAG = 0x10
_WEBP_VP8X_EXIF_FLAG = 0x08
_WEBP_VP8X_XMP_FLAG = 0x04
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
_FILE_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
_PACKAGE_COMMAND = (
    "make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile theme-package"
)
_CHECK_COMMAND = (
    "make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile theme-check"
)
_THEME_ASSET_ENQUEUE_BLOCK = """add_action('wp_enqueue_scripts', static function (): void {
    $theme = wp_get_theme();
    wp_enqueue_style(
        'kurashinoshirube-editorial',
        get_stylesheet_directory_uri() . '/assets/theme.css',
        array(),
        $theme->get('Version')
    );
    wp_enqueue_script(
        'kurashinoshirube-editorial',
        get_stylesheet_directory_uri() . '/assets/theme.js',
        array(),
        $theme->get('Version'),
        array('in_footer' => true, 'strategy' => 'defer')
    );
});"""
_FUNCTIONS_ACTIVE_PREFIX = f"""<?php
/** Local-only presentation wiring. No remote requests or write capability. */

{_THEME_ASSET_ENQUEUE_BLOCK}

"""
_FIRST_ARTICLE_RETURN_FRAGMENT = f"""    return '<figure class="wp-block-image size-full {FIRST_ARTICLE_LEAD_IMAGE_CLASS}">'
        . '<img src="' . esc_url($image_uri) . '" alt="' . esc_attr($alt)
        . '" width="{FIRST_ARTICLE_IMAGE_WIDTH}" height="{FIRST_ARTICLE_IMAGE_HEIGHT}">'
        . '</figure>';"""
_FIRST_ARTICLE_HANDLER_END = "\n}\n\nadd_shortcode("


class ThemeBuildFailure(RuntimeError):
    pass


def _fail(code: str) -> NoReturn:
    raise ThemeBuildFailure(code) from None


def _shortcode_content_gate_allows(value: object) -> bool:
    """Model the exact PHP strict-in-array empty-content gate for offline tests."""

    return value is None or (type(value) is str and value == "")


def _validate_shortcode_content_gate(text: str) -> None:
    if (
        text.count(FIRST_ARTICLE_EMPTY_CONTENT_GUARD) != 1
        or "$content !== null" in text
        or not _shortcode_content_gate_allows(None)
        or not _shortcode_content_gate_allows("")
        or _shortcode_content_gate_allows(" ")
        or _shortcode_content_gate_allows("enclosed content")
        or _shortcode_content_gate_allows(False)
        or _shortcode_content_gate_allows(0)
    ):
        _fail("THEME_ARTICLE_ASSET_BINDING_INVALID")


def _validate_first_article_responsive_css(text: str) -> None:
    sequence_start = text.find(FIRST_ARTICLE_RESPONSIVE_SEQUENCE)
    related_rules = tuple(
        (match.group("selector").strip(), match.group("body"))
        for match in _CSS_FLAT_RULE.finditer(text)
        if (
            FIRST_ARTICLE_LEAD_IMAGE_CLASS in match.group("selector")
            or ".wp-block-image" in match.group("selector")
            or _CSS_FIGURE_OR_IMAGE_SELECTOR.search(match.group("selector")) is not None
        )
    )
    expected_rules = (
        (
            f"figure.{FIRST_ARTICLE_LEAD_IMAGE_CLASS}",
            "\n  margin-inline: 0;\n  max-width: 100%;\n",
        ),
        (
            f"figure.{FIRST_ARTICLE_LEAD_IMAGE_CLASS} > img",
            "\n  display: block;\n  height: auto;\n"
            "  max-width: 100%;\n  width: 100%;\n",
        ),
    )
    if (
        text.count(FIRST_ARTICLE_RESPONSIVE_FIGURE_RULE) != 1
        or text.count(FIRST_ARTICLE_RESPONSIVE_IMAGE_RULE) != 1
        or text.count(f".{FIRST_ARTICLE_LEAD_IMAGE_CLASS}") != 2
        or text.count(_COMPARISON_OVERFLOW_RULE) != 1
        or text.count(FIRST_ARTICLE_RESPONSIVE_SEQUENCE) != 1
        or sequence_start < 0
        or text[:sequence_start].count("{") != text[:sequence_start].count("}")
        or related_rules != expected_rules
        or len(_CSS_OVERFLOW_PROPERTY_TOKEN.findall(text)) != 1
    ):
        _fail("THEME_ARTICLE_ASSET_BINDING_INVALID")


def _validate_theme_asset_version_binding(text: str) -> None:
    if (
        not text.startswith(_FUNCTIONS_ACTIVE_PREFIX)
        or text.count(_THEME_ASSET_ENQUEUE_BLOCK) != 1
        or text.count("$theme->get('Version')") != 2
    ):
        _fail("THEME_PARENT_INVALID")


def _validate_first_article_return_binding(text: str) -> None:
    fragment_start = text.find(_FIRST_ARTICLE_RETURN_FRAGMENT)
    handler_end = text.find(_FIRST_ARTICLE_HANDLER_END)
    if (
        text.count(_FIRST_ARTICLE_RETURN_FRAGMENT) != 1
        or text.count(_FIRST_ARTICLE_HANDLER_END) != 1
        or fragment_start < 0
        or handler_end != fragment_start + len(_FIRST_ARTICLE_RETURN_FRAGMENT)
    ):
        _fail("THEME_ARTICLE_ASSET_BINDING_INVALID")


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


def _webp_vp8_dimensions(payload: bytes) -> tuple[int, int, bool] | None:
    if len(payload) < 12 or payload[3:6] != b"\x9d\x01\x2a":
        return None
    frame_tag = int.from_bytes(payload[:3], "little")
    first_partition_bytes = frame_tag >> 5
    if (
        frame_tag & 0x01
        or (frame_tag >> 1) & 0x07 > 3
        or (frame_tag >> 4) & 0x01 != 1
        or first_partition_bytes == 0
        or 10 + first_partition_bytes >= len(payload)
    ):
        return None
    width = int.from_bytes(payload[6:8], "little") & 0x3FFF
    height = int.from_bytes(payload[8:10], "little") & 0x3FFF
    if width == 0 or height == 0:
        return None
    return width, height, False


def _webp_vp8l_dimensions(payload: bytes) -> tuple[int, int, bool] | None:
    if len(payload) < 6 or payload[0] != 0x2F:
        return None
    header = int.from_bytes(payload[1:5], "little")
    if header >> 29:
        return None
    width = (header & 0x3FFF) + 1
    height = ((header >> 14) & 0x3FFF) + 1
    return width, height, bool((header >> 28) & 0x01)


def _webp_image_dimensions(
    chunk_type: bytes, payload: bytes
) -> tuple[int, int, bool] | None:
    if chunk_type == b"VP8 ":
        return _webp_vp8_dimensions(payload)
    if chunk_type == b"VP8L":
        return _webp_vp8l_dimensions(payload)
    return None


def _is_complete_static_webp_container(payload: bytes) -> bool:
    """Accept one bounded, complete, static WebP RIFF container."""

    if (
        type(payload) is not bytes
        or not 20 <= len(payload) <= MAX_FILE_BYTES
        or payload[:4] != b"RIFF"
        or payload[8:12] != b"WEBP"
        or int.from_bytes(payload[4:8], "little") != len(payload) - 8
    ):
        return False

    chunks: list[tuple[bytes, bytes]] = []
    cursor = 12
    while cursor < len(payload):
        if len(chunks) >= _WEBP_MAX_CHUNKS or len(payload) - cursor < 8:
            return False
        chunk_type = payload[cursor : cursor + 4]
        chunk_bytes = int.from_bytes(payload[cursor + 4 : cursor + 8], "little")
        data_start = cursor + 8
        data_end = data_start + chunk_bytes
        padded_end = data_end + (chunk_bytes & 0x01)
        if chunk_bytes == 0 or data_end > len(payload) or padded_end > len(payload):
            return False
        if chunk_bytes & 0x01 and payload[data_end] != 0:
            return False
        chunks.append((chunk_type, payload[data_start:data_end]))
        cursor = padded_end
    if cursor != len(payload) or not chunks:
        return False

    if len(chunks) == 1:
        return _webp_image_dimensions(*chunks[0]) is not None

    if chunks[0][0] != b"VP8X" or len(chunks[0][1]) != 10:
        return False
    extended_header = chunks[0][1]
    flags = extended_header[0]
    if flags & ~_WEBP_VP8X_ALLOWED_FLAGS or extended_header[1:4] != b"\x00\x00\x00":
        return False
    canvas = (
        int.from_bytes(extended_header[4:7], "little") + 1,
        int.from_bytes(extended_header[7:10], "little") + 1,
    )
    image_chunks = [item for item in chunks[1:] if item[0] in {b"VP8 ", b"VP8L"}]
    if len(image_chunks) != 1:
        return False
    image_type, image_payload = image_chunks[0]
    image = _webp_image_dimensions(image_type, image_payload)
    if image is None or image[:2] != canvas:
        return False
    image_uses_alpha = image[2]

    expected_types = [b"VP8X"]
    if flags & _WEBP_VP8X_ICC_FLAG:
        expected_types.append(b"ICCP")
    if image_type == b"VP8 " and flags & _WEBP_VP8X_ALPHA_FLAG:
        expected_types.append(b"ALPH")
    expected_types.append(image_type)
    if flags & _WEBP_VP8X_EXIF_FLAG:
        expected_types.append(b"EXIF")
    if flags & _WEBP_VP8X_XMP_FLAG:
        expected_types.append(b"XMP ")
    if [item[0] for item in chunks] != expected_types:
        return False

    chunk_payloads = {chunk_type: data for chunk_type, data in chunks[1:]}
    for optional_type, feature_flag in (
        (b"ICCP", _WEBP_VP8X_ICC_FLAG),
        (b"EXIF", _WEBP_VP8X_EXIF_FLAG),
        (b"XMP ", _WEBP_VP8X_XMP_FLAG),
    ):
        if bool(flags & feature_flag) != bool(chunk_payloads.get(optional_type)):
            return False
    alpha_flag = bool(flags & _WEBP_VP8X_ALPHA_FLAG)
    if image_type == b"VP8L":
        return alpha_flag == image_uses_alpha
    alpha_payload = chunk_payloads.get(b"ALPH")
    return (
        alpha_flag
        and alpha_payload is not None
        and len(alpha_payload) == 1 + canvas[0] * canvas[1]
        and alpha_payload[0] & 0xE3 == 0
    ) or (not alpha_flag and alpha_payload is None)


def _static_webp_canvas_dimensions(payload: bytes) -> tuple[int, int] | None:
    """Return the validated static canvas size without decoding image pixels."""

    if not _is_complete_static_webp_container(payload):
        return None
    chunk_type = payload[12:16]
    chunk_bytes = int.from_bytes(payload[16:20], "little")
    chunk_payload = payload[20 : 20 + chunk_bytes]
    if chunk_type == b"VP8X":
        return (
            int.from_bytes(chunk_payload[4:7], "little") + 1,
            int.from_bytes(chunk_payload[7:10], "little") + 1,
        )
    image = _webp_image_dimensions(chunk_type, chunk_payload)
    return None if image is None else image[:2]


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


def _same_named_ancestor_directory(
    details: os.stat_result, *, parent_fd: int, name: str
) -> None:
    """Bind traversal ancestors without treating unrelated child writes as swaps.

    Shared ancestors such as /tmp legitimately change size, link count and
    timestamps during parallel builds. Device/inode, type/mode and ownership
    must still match. The selected root and its inventory retain full checks.
    """
    try:
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError:
        _fail("THEME_ROOT_INVALID")
    if (
        not stat.S_ISDIR(details.st_mode)
        or not stat.S_ISDIR(named.st_mode)
        or _identity(named)[:5] != _identity(details)[:5]
    ):
        _fail("THEME_ROOT_INVALID")


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
        for index, part in enumerate(path.parts[1:], start=1):
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
                if index < len(path.parts) - 1:
                    _same_named_ancestor_directory(
                        opened, parent_fd=descriptor, name=part
                    )
                else:
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


def _validated_output_paths(error_code: str) -> tuple[Path, Path]:
    if not OUTPUT_REPOSITORY_ROOT.is_absolute() or any(
        part in {"", ".", ".."} for part in OUTPUT_REPOSITORY_ROOT.parts[1:]
    ):
        _fail(error_code)
    expected_directory = OUTPUT_REPOSITORY_ROOT.joinpath(*_PRIVATE_OUTPUT_PARTS)
    expected_path = expected_directory / f"{THEME_SLUG}.zip"
    if OUTPUT_DIRECTORY != expected_directory or OUTPUT_PATH != expected_path:
        _fail(error_code)
    return expected_directory, expected_path


def _require_private_output_directory_binding(
    descriptor: int, *, error_code: str
) -> None:
    _validated_output_paths(error_code)
    try:
        held = os.fstat(descriptor)
        with _open_absolute_directory(OUTPUT_DIRECTORY) as rebound_fd:
            rebound = os.fstat(rebound_fd)
    except OSError, ThemeBuildFailure:
        _fail(error_code)
    if _identity(held) != _identity(rebound):
        _fail(error_code)


@contextmanager
def _open_private_output_directory(
    *, create: bool, error_code: str
) -> Generator[int, None, None]:
    _validated_output_paths(error_code)
    try:
        root_context = _open_absolute_directory(OUTPUT_REPOSITORY_ROOT)
        with root_context as repository_fd:
            try:
                descriptor = os.dup(repository_fd)
            except OSError:
                _fail(error_code)
            try:
                for part in _PRIVATE_OUTPUT_PARTS:
                    child: int | None = None
                    try:
                        child = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
                    except FileNotFoundError:
                        if not create:
                            _fail(error_code)
                        try:
                            os.mkdir(
                                part,
                                mode=PRIVATE_OUTPUT_DIRECTORY_MODE,
                                dir_fd=descriptor,
                            )
                            os.fsync(descriptor)
                            child = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
                        except OSError:
                            _fail(error_code)
                    except OSError:
                        _fail(error_code)
                    try:
                        opened = os.fstat(child)
                        if (
                            not stat.S_ISDIR(opened.st_mode)
                            or opened.st_uid != os.getuid()
                            or stat.S_IMODE(opened.st_mode)
                            != PRIVATE_OUTPUT_DIRECTORY_MODE
                        ):
                            _fail(error_code)
                        _same_named_object(
                            opened,
                            parent_fd=descriptor,
                            name=part,
                            error_code=error_code,
                        )
                    except BaseException:
                        os.close(child)
                        raise
                    os.close(descriptor)
                    descriptor = child
                _require_private_output_directory_binding(
                    descriptor, error_code=error_code
                )
                try:
                    yield descriptor
                finally:
                    _require_private_output_directory_binding(
                        descriptor, error_code=error_code
                    )
            finally:
                os.close(descriptor)
    except ThemeBuildFailure:
        _fail(error_code)


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
    required_mode: int | None = None,
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
                or (
                    required_mode is not None
                    and stat.S_IMODE(before.st_mode) != required_mode
                )
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


def _css_custom_color(text: str, name: str) -> str:
    prefix = f"  {name}: "
    property_token = re.compile(
        rf"(?<![-A-Za-z0-9_]){re.escape(name)}[ \t\r\n]*:", re.ASCII
    )
    if text.count(prefix) != 1 or len(property_token.findall(text)) != 1:
        _fail("THEME_ACCESSIBILITY_INVALID")
    value = text.split(prefix, maxsplit=1)[1].split(";", maxsplit=1)[0]
    if _CSS_HEX_COLOR.fullmatch(value) is None:
        _fail("THEME_ACCESSIBILITY_INVALID")
    return value


def _relative_luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(first: str, second: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def _validate_footer_contrast(text: str) -> None:
    normal_block = (
        ".raos-footer a:link,\n.raos-footer a:visited {\n"
        "  color: var(--raos-footer-link);\n}"
    )
    interactive_block = (
        ".raos-footer a:hover,\n.raos-footer a:focus-visible,\n"
        ".raos-footer a:active {\n"
        "  color: var(--raos-footer-link-interactive);\n}"
    )
    focus_block = (
        ".raos-footer a:focus-visible {\n"
        "  outline-color: var(--raos-footer-link-interactive);\n}"
    )
    footer_background_block = ".raos-footer {\n  background: var(--raos-ink);"
    expected_color_declarations = (
        ("color", "var(--raos-ink)"),
        ("color", "var(--raos-warm)"),
        ("color", "var(--raos-ink)"),
        ("color", "#fff"),
        ("color", "currentColor"),
        ("color", "#fff"),
        ("color", "var(--raos-footer-link)"),
        ("color", "var(--raos-footer-link-interactive)"),
        ("outline-color", "var(--raos-footer-link-interactive)"),
    )
    expected_background_declarations = (
        (
            "background",
            "radial-gradient(circle at 14% 8%, rgb(164 79 49 / 7%), "
            "transparent 24rem), var(--raos-paper)",
        ),
        ("background", "#fff"),
        (
            "background",
            "linear-gradient(90deg, rgb(23 36 63 / 92%) 0 38%, "
            'rgb(23 36 63 / 42%) 70%), url("images/home-hero.webp") '
            "center / cover no-repeat",
        ),
        ("background", "var(--raos-ink)"),
        ("background-position", "62% center"),
    )
    expected_outline_declarations = (
        ("outline", "3px solid var(--raos-focus)"),
        ("outline-offset", "4px"),
        ("outline-color", "var(--raos-footer-link-interactive)"),
    )
    observed_color_declarations = tuple(
        (match.group("property"), " ".join(match.group("value").split()))
        for match in _CSS_COLOR_DECLARATION.finditer(text)
    )
    observed_background_declarations = tuple(
        (match.group("property"), " ".join(match.group("value").split()))
        for match in _CSS_BACKGROUND_DECLARATION.finditer(text)
    )
    observed_outline_declarations = tuple(
        (match.group("property"), " ".join(match.group("value").split()))
        for match in _CSS_OUTLINE_DECLARATION.finditer(text)
    )
    if (
        "\\" in text
        or "/*" in text
        or "*/" in text
        or text.count(normal_block) != 1
        or text.count(interactive_block) != 1
        or text.count(focus_block) != 1
        or text.count(footer_background_block) != 1
        or text.count(".raos-footer") != 7
        or len(_CSS_COLOR_PROPERTY_TOKEN.findall(text))
        != len(expected_color_declarations)
        or observed_color_declarations != expected_color_declarations
        or len(_CSS_BACKGROUND_PROPERTY_TOKEN.findall(text))
        != len(expected_background_declarations)
        or observed_background_declarations != expected_background_declarations
        or len(_CSS_OUTLINE_PROPERTY_TOKEN.findall(text))
        != len(expected_outline_declarations)
        or observed_outline_declarations != expected_outline_declarations
        or not (
            text.index(normal_block)
            < text.index(interactive_block)
            < text.index(focus_block)
            < text.index(".raos-reveal {")
        )
    ):
        _fail("THEME_ACCESSIBILITY_INVALID")
    background = _css_custom_color(text, "--raos-ink")
    normal = _css_custom_color(text, "--raos-footer-link")
    interactive = _css_custom_color(text, "--raos-footer-link-interactive")
    for foreground in (normal, interactive):
        if (
            _contrast_ratio(foreground, background) < 4.5
            or _contrast_ratio(foreground, "#24365f") < 4.5
        ):
            _fail("THEME_ACCESSIBILITY_INVALID")
    if _contrast_ratio(interactive, background) < 3.0:
        _fail("THEME_ACCESSIBILITY_INVALID")


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
    if relative == "assets/theme.css":
        if (
            "@media (prefers-reduced-motion: reduce)" not in text
            or ":focus-visible" not in text
            or ".raos-reveal-ready .raos-reveal:not(.is-visible)" not in text
            or ".raos-reveal-ready .raos-reveal" not in text
            or ".raos-reveal {\n  opacity: 1;\n  transform: none;" not in text
        ):
            _fail("THEME_ACCESSIBILITY_INVALID")
        _validate_first_article_responsive_css(text)
        _validate_footer_contrast(text)
        if hashlib.sha256(payload).hexdigest() != EXPECTED_THEME_CSS_SHA256:
            _fail("THEME_ACCESSIBILITY_INVALID")
    if relative == "assets/theme.js" and (
        'root.classList.add("raos-reveal-ready")' not in text
        or 'root.classList.remove("raos-reveal-ready")' not in text
        or "const revealAll = () =>" not in text
        or "if (reduced ||" not in text
    ):
        _fail("THEME_ACCESSIBILITY_INVALID")
    if relative == "functions.php":
        _validate_shortcode_content_gate(text)
        _validate_theme_asset_version_binding(text)
        _validate_first_article_return_binding(text)
    if relative == "functions.php" and (
        hashlib.sha256(payload).hexdigest() != EXPECTED_THEME_FUNCTIONS_SHA256
        or text.count(FIRST_ARTICLE_SHORTCODE_TAG) != 2
        or text.count("kurashinoshirube_render_first_article_lead_image") != 2
        or "get_stylesheet_directory_uri()" not in text
        or "get_post_field('post_title', get_the_ID(), 'raw')" not in text
        or FIRST_ARTICLE_TITLE not in text
        or "get_post_field('post_name', get_the_ID(), 'raw')" not in text
        or FIRST_ARTICLE_SLUG not in text
        or f"get_stylesheet() !== '{FIRST_ARTICLE_THEME_SLUG}'" not in text
        or "get_stylesheet_directory()" not in text
        or "is_link($image_path)" not in text
        or "is_file($image_path)" not in text
        or "is_readable($image_path)" not in text
        or "($uri['scheme'] ?? null) !== 'https'" not in text
        or f"($uri['host'] ?? null) !== '{FIRST_ARTICLE_TARGET_HOST}'" not in text
        or "assets/images/article-suitcase-guide.webp" not in text
        or FIRST_ARTICLE_IMAGE_ALT not in text
        or text.count(FIRST_ARTICLE_LEAD_IMAGE_CLASS) != 1
        or text.count(
            f'class="wp-block-image size-full {FIRST_ARTICLE_LEAD_IMAGE_CLASS}"'
        )
        != 1
        or text.count(
            f'width="{FIRST_ARTICLE_IMAGE_WIDTH}" height="{FIRST_ARTICLE_IMAGE_HEIGHT}"'
        )
        != 1
        or "featured_media" in text
        or "add_filter" in text
        or "media_handle" in text
        or "wp_insert_attachment" in text
    ):
        _fail("THEME_ARTICLE_ASSET_BINDING_INVALID")
    if relative == "style.css" and (
        "Theme Name: 暮らしのしるべ Editorial" not in text
        or "Template: twentytwentyfive" not in text
        or text.count(f"\nVersion: {EXPECTED_THEME_VERSION}\n") != 1
    ):
        _fail("THEME_PARENT_INVALID")
    if relative == "theme.json" and (
        '"color": {"background": "#24365f", "text": "#ffffff"}' not in text
        or '"link": {"color": {"text": "#24365f"}}' not in text
    ):
        _fail("THEME_ACCESSIBILITY_INVALID")


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
        if relative == "templates/single.html" and (
            text.count("<!-- wp:post-content ") != 1 or "wp:post-featured-image" in text
        ):
            _fail("THEME_ARTICLE_ASSET_BINDING_INVALID")

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
    first_article_asset_status: str
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
    first_article_asset_status: str | None = None
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
            or type(image.get("delivery")) is not str
            or type(image.get("usage")) is not str
            or not cast(str, image["usage"]).strip()
            or image.get("status") not in {"PENDING_FINAL_ASSET", "FINAL"}
        ):
            _fail("THEME_MANIFEST_INVALID")
        if image.get("delivery") != _EXPECTED_IMAGE_DELIVERY.get(path):
            _fail("THEME_ASSET_DELIVERY_INVALID")
        image_paths.add(path)
        if path == FIRST_ARTICLE_IMAGE_RELATIVE_PATH:
            if (
                image.get("alt") != FIRST_ARTICLE_IMAGE_ALT
                or image.get("usage") != FIRST_ARTICLE_IMAGE_USAGE
            ):
                _fail("THEME_ARTICLE_ASSET_BINDING_INVALID")
            first_article_asset_status = cast(str, image["status"])
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
            or not _is_complete_static_webp_container(payload)
            or hashlib.sha256(payload).hexdigest() != image["sha256"]
        ):
            _fail("THEME_FINAL_ASSET_INVALID")
        if path == FIRST_ARTICLE_IMAGE_RELATIVE_PATH and (
            _static_webp_canvas_dimensions(payload)
            != (FIRST_ARTICLE_IMAGE_WIDTH, FIRST_ARTICLE_IMAGE_HEIGHT)
        ):
            _fail("THEME_ARTICLE_ASSET_BINDING_INVALID")

    if first_article_asset_status is None or set(payloads) != {
        *paths,
        *image_paths.intersection(payloads),
    }:
        _fail("THEME_INVENTORY_MISMATCH")
    return _ThemeSnapshot(
        archive_files=tuple(sorted(payloads.items())),
        first_article_asset_status=first_article_asset_status,
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
        "first_article_asset_status": snapshot.first_article_asset_status,
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
    with _open_private_output_directory(
        create=True, error_code="THEME_PACKAGE_WRITE_FAILED"
    ) as parent_fd:
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
            or stat.S_IMODE(existing.st_mode) != PRIVATE_OUTPUT_FILE_MODE
            or not 1 <= existing.st_size <= MAX_PACKAGE_BYTES
        ):
            _fail("THEME_PACKAGE_WRITE_FAILED")

        temporary = f".{OUTPUT_PATH.name}.preparing"
        staging_inode: tuple[int, int] | None = None
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                PRIVATE_OUTPUT_FILE_MODE,
                dir_fd=parent_fd,
            )
        except OSError:
            _fail("THEME_PACKAGE_WRITE_FAILED")
        try:
            try:
                os.fchmod(descriptor, PRIVATE_OUTPUT_FILE_MODE)
            except OSError:
                _fail("THEME_PACKAGE_WRITE_FAILED")
            try:
                before = os.fstat(descriptor)
            except OSError:
                _fail("THEME_PACKAGE_WRITE_FAILED")
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.getuid()
                or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) != PRIVATE_OUTPUT_FILE_MODE
            ):
                _fail("THEME_PACKAGE_WRITE_FAILED")
            staging_inode = (before.st_dev, before.st_ino)
            try:
                os.fsync(parent_fd)
            except OSError:
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
            try:
                os.fsync(descriptor)
                after = os.fstat(descriptor)
            except OSError:
                _fail("THEME_PACKAGE_WRITE_FAILED")
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
            _require_private_output_directory_binding(
                parent_fd, error_code="THEME_PACKAGE_WRITE_FAILED"
            )
            if existing is None:
                try:
                    os.stat(
                        OUTPUT_PATH.name,
                        dir_fd=parent_fd,
                        follow_symlinks=False,
                    )
                except FileNotFoundError:
                    pass
                except OSError:
                    _fail("THEME_PACKAGE_WRITE_FAILED")
                else:
                    _fail("THEME_PACKAGE_WRITE_FAILED")
            else:
                _same_named_object(
                    existing,
                    parent_fd=parent_fd,
                    name=OUTPUT_PATH.name,
                    error_code="THEME_PACKAGE_WRITE_FAILED",
                )
            try:
                os.replace(
                    temporary,
                    OUTPUT_PATH.name,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                )
            except OSError:
                _fail("THEME_PACKAGE_WRITE_FAILED")
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
                or stat.S_IMODE(published.st_mode) != PRIVATE_OUTPUT_FILE_MODE
            ):
                _fail("THEME_PACKAGE_WRITE_FAILED")
            _same_named_object(
                published,
                parent_fd=parent_fd,
                name=OUTPUT_PATH.name,
                error_code="THEME_PACKAGE_WRITE_FAILED",
            )
            try:
                os.fsync(parent_fd)
            except OSError:
                _fail("THEME_PACKAGE_WRITE_FAILED")
            _require_private_output_directory_binding(
                parent_fd, error_code="THEME_PACKAGE_WRITE_FAILED"
            )
        finally:
            try:
                os.close(descriptor)
            except OSError:
                _fail("THEME_PACKAGE_WRITE_FAILED")
            stale: os.stat_result | None
            try:
                stale = os.stat(temporary, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                stale = None
            except OSError:
                _fail("THEME_PACKAGE_WRITE_FAILED")
            if stale is not None:
                if (
                    staging_inode is None
                    or (stale.st_dev, stale.st_ino) != staging_inode
                ):
                    _fail("THEME_PACKAGE_WRITE_FAILED")
                try:
                    os.unlink(temporary, dir_fd=parent_fd)
                    os.fsync(parent_fd)
                except OSError:
                    _fail("THEME_PACKAGE_WRITE_FAILED")
        _require_private_output_directory_binding(
            parent_fd, error_code="THEME_PACKAGE_WRITE_FAILED"
        )
        verified_payload, _verified_identity = _read_regular_at(
            parent_fd,
            OUTPUT_PATH.name,
            max_bytes=MAX_PACKAGE_BYTES,
            error_code="THEME_PACKAGE_WRITE_FAILED",
            required_mode=PRIVATE_OUTPUT_FILE_MODE,
        )
        if verified_payload != payload:
            _fail("THEME_PACKAGE_WRITE_FAILED")


def _read_output_package() -> bytes:
    try:
        with _open_private_output_directory(
            create=False, error_code="THEME_PACKAGE_DRIFT"
        ) as parent_fd:
            payload, _identity_value = _read_regular_at(
                parent_fd,
                OUTPUT_PATH.name,
                max_bytes=MAX_PACKAGE_BYTES,
                error_code="THEME_PACKAGE_DRIFT",
                required_mode=PRIVATE_OUTPUT_FILE_MODE,
            )
            return payload
    except ThemeBuildFailure:
        _fail("THEME_PACKAGE_DRIFT")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    group = parser.add_mutually_exclusive_group()
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
            package_mode = arguments.package or not arguments.check
            if package_mode:
                _write_package(payload)
            elif _read_output_package() != payload:
                _fail("THEME_PACKAGE_DRIFT")
            result = {
                "package_bytes": len(payload),
                "package_sha256": hashlib.sha256(payload).hexdigest(),
                "status": "PACKAGED" if package_mode else "PACKAGE_VALID",
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

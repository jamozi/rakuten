#!/usr/bin/env python3
"""Rasterize the ST-1704 theme's brand mark into deterministic site icons.

The only input is the repository-authored ``brand-mark.svg`` (a rounded
square, three bars and one dot). Its geometry is rendered here with a small
analytic rasterizer so the PNG and ICO outputs are byte-identical on every
machine without an external encoder or browser. ``--check`` validates the
tracked outputs without rendering.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
import struct
from typing import Final, NoReturn
import zlib


ROOT: Final = Path(__file__).resolve().parents[1]
THEME_IMAGES: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/images"
)
SOURCE: Final = THEME_IMAGES / "brand-mark.svg"
SOURCE_SHA256: Final = (
    "bd9f84f40eca90fb88b7e8a3967f6d7ceb5d337c6023d1f2ff748936a0f3acf3"
)
SOURCE_RELATIVE: Final = (
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/"
    "assets/images/brand-mark.svg"
)
# Generated outputs (registered with the build owner graph; sha256 fixed in ICONS).
OUTPUT_PATHS: Final = (
    THEME_IMAGES / "brand-mark-512.png",
    THEME_IMAGES / "apple-touch-icon.png",
    THEME_IMAGES / "favicon-32.png",
    THEME_IMAGES / "favicon.ico",
)
MAX_OUTPUT_BYTES: Final = 1024 * 1024
VIEWBOX: Final = 64.0
SUPERSAMPLE: Final = 4
CREATED_ON: Final = "2026-09-12"

# Geometry copied from brand-mark.svg (viewBox 0 0 64 64).
BACKGROUND_RGB: Final = (0x17, 0x24, 0x3F)
BAR_RGB: Final = (0xF7, 0xF2, 0xE9)
DOT_RGB: Final = (0xD4, 0x7A, 0x58)
CORNER_RADIUS: Final = 12.0
BARS: Final = ((18.0, 17.0, 28.0, 4.0), (18.0, 30.0, 22.0, 4.0), (18.0, 43.0, 16.0, 4.0))
DOT_CENTER: Final = (45.0, 45.0)
DOT_RADIUS: Final = 7.0


@dataclass(frozen=True)
class IconSpec:
    """One deterministic raster output derived from the brand mark."""

    output: Path
    kind: str  # "png" or "ico"
    sizes: tuple[int, ...]
    output_sha256: str
    allowed_uses: tuple[str, ...]
    usage: str
    delivery: str


ICONS: Final = (
    IconSpec(
        output=THEME_IMAGES / "brand-mark-512.png",
        kind="png",
        sizes=(512,),
        output_sha256=(
            "80587716081d3abc82d411068e264a8c3b2b4a833a05532b2668e728d540431e"
        ),
        allowed_uses=("ORGANIZATION_LOGO", "SITE_ICON_SOURCE"),
        usage="Organization logo (JSON-LD ImageObject) and WordPress site icon source",
        delivery="JSON_LD_ORGANIZATION_LOGO",
    ),
    IconSpec(
        output=THEME_IMAGES / "apple-touch-icon.png",
        kind="png",
        sizes=(180,),
        output_sha256=(
            "b4f5c749c4eb6319ceb115ef504d4bbfadc9e7eed0c8839468c5d309e0e8fec5"
        ),
        allowed_uses=("APPLE_TOUCH_ICON",),
        usage="180px apple-touch-icon link",
        delivery="HEAD_APPLE_TOUCH_ICON_LINK",
    ),
    IconSpec(
        output=THEME_IMAGES / "favicon-32.png",
        kind="png",
        sizes=(32,),
        output_sha256=(
            "f659ea0e294df0d3618c9207fa5be59170e4a08f69c25f00138571b1106edd0b"
        ),
        allowed_uses=("FAVICON",),
        usage="32px PNG favicon link",
        delivery="HEAD_ICON_LINK",
    ),
    IconSpec(
        output=THEME_IMAGES / "favicon.ico",
        kind="ico",
        sizes=(16, 32, 48),
        output_sha256=(
            "1781bc5617878f763a6e292baa734b9c3a6a3c89540073c86bc375184fa36cc5"
        ),
        allowed_uses=("FAVICON",),
        usage="/favicon.ico response and legacy icon link",
        delivery="FAVICON_ICO_RESPONSE",
    ),
)


class IconGenerationFailure(RuntimeError):
    """Stable, non-sensitive icon generation refusal."""


def _fail() -> NoReturn:
    raise IconGenerationFailure("ST1704_THEME_ICON_GENERATION_INVALID") from None


def _regular_payload(path: Path, maximum: int) -> bytes:
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError:
        _fail()
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size <= 0
        or metadata.st_size > maximum
        or len(payload) != metadata.st_size
    ):
        _fail()
    return payload


def _validate_source() -> None:
    payload = _regular_payload(SOURCE, MAX_OUTPUT_BYTES)
    if hashlib.sha256(payload).hexdigest() != SOURCE_SHA256:
        _fail()
    text = payload.decode("utf-8")
    for fragment in (
        'viewBox="0 0 64 64"',
        '<rect width="64" height="64" rx="12" fill="#17243f"/>',
        '<path d="M18 17h28v4H18zm0 13h22v4H18zm0 13h16v4H18z" fill="#f7f2e9"/>',
        '<circle cx="45" cy="45" r="7" fill="#d47a58"/>',
    ):
        if fragment not in text:
            _fail()


def manifest_provenance(icon: IconSpec) -> dict[str, object]:
    """Closed provenance record for the raster derived from the vector mark."""

    return {
        "allowed_modifications": ["FORMAT_CONVERSION", "RESIZE"],
        "allowed_uses": list(icon.allowed_uses),
        "created_on": CREATED_ON,
        "creation_method": "REPOSITORY_RASTERIZED_VECTOR",
        "creator_record": "SITE_REPOSITORY_MAINTAINER",
        "external_license_dependency": False,
        "generation_intent": "ORIGINAL_SITE_IDENTITY_MARK",
        "original_sha256": SOURCE_SHA256,
        "original_source_path": SOURCE_RELATIVE,
        "provenance_evidence": "GIT_TRACKED_SOURCE",
        "rights_basis": "OWNER_AUTHORIZED_REPOSITORY_ORIGINAL",
        "rights_status": "RECORDED_FOR_SITE_USE",
    }


# --- rasterizer -----------------------------------------------------------


def _classify(x: float, y: float) -> int:
    """0 transparent, 1 background, 2 bar, 3 dot (topmost shape wins)."""

    dx = x - DOT_CENTER[0]
    dy = y - DOT_CENTER[1]
    if dx * dx + dy * dy <= DOT_RADIUS * DOT_RADIUS:
        return 3
    for bx, by, bw, bh in BARS:
        if bx <= x < bx + bw and by <= y < by + bh:
            return 2
    if not (0.0 <= x < VIEWBOX and 0.0 <= y < VIEWBOX):
        return 0
    cx = min(max(x, CORNER_RADIUS), VIEWBOX - CORNER_RADIUS)
    cy = min(max(y, CORNER_RADIUS), VIEWBOX - CORNER_RADIUS)
    ex = x - cx
    ey = y - cy
    if ex * ex + ey * ey <= CORNER_RADIUS * CORNER_RADIUS:
        return 1
    return 0


_COLORS: Final = {
    0: (0, 0, 0, 0),
    1: (*BACKGROUND_RGB, 255),
    2: (*BAR_RGB, 255),
    3: (*DOT_RGB, 255),
}


def render_rgba(size: int) -> bytes:
    """Return straight-alpha RGBA rows (top-down) for one square size."""

    if size < 8 or size > 1024:
        _fail()
    scale = VIEWBOX / size
    fast_path = scale <= 1.0
    step = scale / SUPERSAMPLE
    samples = SUPERSAMPLE * SUPERSAMPLE
    out = bytearray(size * size * 4)
    for py in range(size):
        y0 = py * scale
        y1 = y0 + scale
        row = py * size * 4
        for px in range(size):
            x0 = px * scale
            x1 = x0 + scale
            if fast_path:
                first = _classify(x0, y0)
                if (
                    first == _classify(x1, y0)
                    and first == _classify(x0, y1)
                    and first == _classify(x1, y1)
                    and first == _classify((x0 + x1) / 2, (y0 + y1) / 2)
                ):
                    out[row + px * 4 : row + px * 4 + 4] = bytes(_COLORS[first])
                    continue
            r = g = b = a = 0
            for sy in range(SUPERSAMPLE):
                yy = y0 + (sy + 0.5) * step
                for sx in range(SUPERSAMPLE):
                    cr, cg, cb, ca = _COLORS[_classify(x0 + (sx + 0.5) * step, yy)]
                    r += cr * ca
                    g += cg * ca
                    b += cb * ca
                    a += ca
            if a == 0:
                continue
            alpha = a / samples
            out[row + px * 4 : row + px * 4 + 4] = bytes(
                (
                    round(r / a),
                    round(g / a),
                    round(b / a),
                    round(alpha),
                )
            )
    return bytes(out)


# --- encoders -------------------------------------------------------------


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def encode_png(size: int, rgba: bytes) -> bytes:
    stride = size * 4
    raw = b"".join(b"\x00" + rgba[y * stride : (y + 1) * stride] for y in range(size))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )


def _ico_image(size: int, rgba: bytes) -> bytes:
    """32-bit BGRA DIB with a 1-bit AND mask, rows bottom-up."""

    xor_rows = []
    and_rows = []
    mask_stride = ((size + 31) // 32) * 4
    for y in range(size - 1, -1, -1):
        row = rgba[y * size * 4 : (y + 1) * size * 4]
        xor = bytearray()
        mask = bytearray(mask_stride)
        for x in range(size):
            r, g, b, a = row[x * 4 : x * 4 + 4]
            xor += bytes((b, g, r, a))
            if a == 0:
                mask[x // 8] |= 0x80 >> (x % 8)
        xor_rows.append(bytes(xor))
        and_rows.append(bytes(mask))
    xor_data = b"".join(xor_rows)
    and_data = b"".join(and_rows)
    header = struct.pack(
        "<IiiHHIIiiII",
        40,
        size,
        size * 2,
        1,
        32,
        0,
        len(xor_data) + len(and_data),
        0,
        0,
        0,
        0,
    )
    return header + xor_data + and_data


def encode_ico(images: list[tuple[int, bytes]]) -> bytes:
    entries = []
    blobs = []
    offset = 6 + 16 * len(images)
    for size, rgba in images:
        blob = _ico_image(size, rgba)
        entries.append(
            struct.pack(
                "<BBBBHHII",
                0 if size >= 256 else size,
                0 if size >= 256 else size,
                0,
                0,
                1,
                32,
                len(blob),
                offset,
            )
        )
        blobs.append(blob)
        offset += len(blob)
    return struct.pack("<HHH", 0, 1, len(images)) + b"".join(entries) + b"".join(blobs)


def render(icon: IconSpec) -> bytes:
    if icon.kind == "png":
        (size,) = icon.sizes
        return encode_png(size, render_rgba(size))
    if icon.kind == "ico":
        return encode_ico([(size, render_rgba(size)) for size in icon.sizes])
    _fail()


# --- validation -----------------------------------------------------------


def png_dimensions(payload: bytes) -> tuple[int, int] | None:
    if len(payload) < 33 or payload[:8] != b"\x89PNG\r\n\x1a\n" or payload[12:16] != b"IHDR":
        return None
    return (
        int.from_bytes(payload[16:20], "big"),
        int.from_bytes(payload[20:24], "big"),
    )


def ico_sizes(payload: bytes) -> tuple[int, ...] | None:
    if len(payload) < 6 or payload[:4] != b"\x00\x00\x01\x00":
        return None
    count = int.from_bytes(payload[4:6], "little")
    if count < 1 or len(payload) < 6 + 16 * count:
        return None
    sizes = []
    for index in range(count):
        entry = payload[6 + 16 * index : 6 + 16 * (index + 1)]
        width = entry[0] or 256
        height = entry[1] or 256
        length = int.from_bytes(entry[8:12], "little")
        offset = int.from_bytes(entry[12:16], "little")
        if width != height or offset + length > len(payload):
            return None
        sizes.append(width)
    return tuple(sizes)


def validate_output(icon: IconSpec, payload: bytes) -> None:
    if len(payload) < 20 or len(payload) > MAX_OUTPUT_BYTES:
        _fail()
    if icon.kind == "png":
        if png_dimensions(payload) != (icon.sizes[0], icon.sizes[0]):
            _fail()
    elif icon.kind == "ico":
        if ico_sizes(payload) != icon.sizes:
            _fail()
    else:
        _fail()
    if hashlib.sha256(payload).hexdigest() != icon.output_sha256:
        _fail()


def _write(path: Path, payload: bytes) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        descriptor = os.open(
            temporary,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
            0o644,
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError:
        _fail()


def generate(*, check: bool) -> dict[str, str]:
    """Render (or, with ``check``, only validate) every tracked icon."""

    _validate_source()
    digests: dict[str, str] = {}
    for icon in ICONS:
        payload = (
            _regular_payload(icon.output, MAX_OUTPUT_BYTES) if check else render(icon)
        )
        validate_output(icon, payload)
        if not check:
            _write(icon.output, payload)
        digests[icon.output.name] = hashlib.sha256(payload).hexdigest()
    return digests


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--print-digests",
        action="store_true",
        help="render every icon and print its digest without validating the pinned digest",
    )
    arguments = parser.parse_args()
    if arguments.print_digests:
        _validate_source()
        for icon in ICONS:
            print(f"{icon.output.name}:{hashlib.sha256(render(icon)).hexdigest()}")
        return 0
    try:
        digests = generate(check=arguments.check)
    except IconGenerationFailure as error:
        print(str(error), file=os.sys.stderr)
        return 1
    inventory = ",".join(f"{name}:{digest}" for name, digest in digests.items())
    print(f"ST1704_THEME_ICONS_OK icons={len(digests)} sha256={inventory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

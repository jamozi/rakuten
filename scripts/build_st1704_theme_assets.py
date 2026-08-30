#!/usr/bin/env python3
"""Generate the ST-1704 theme's optimized raster asset from its owner source."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from typing import Final, NoReturn


ROOT: Final = Path(__file__).resolve().parents[1]
SOURCE: Final = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/"
    "article-portable-power-guide.png"
)
OUTPUT: Final = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/images/article-portable-power-guide.webp"
)
FFMPEG: Final = Path("/usr/bin/ffmpeg")
SOURCE_SHA256: Final = "703444cdf29740bb72de42d09c7c7222a3ee46a09bcaf4f78875df9131cc56d6"
OUTPUT_SHA256: Final = "54b84689cff952f6a384982b89d2f56adfbdeff9ff03fe628fcaf5a949ab0f5a"
MAX_SOURCE_BYTES: Final = 8 * 1024 * 1024
MAX_OUTPUT_BYTES: Final = 2 * 1024 * 1024


class AssetGenerationFailure(RuntimeError):
    """Stable, non-sensitive asset generation refusal."""


def _fail() -> NoReturn:
    raise AssetGenerationFailure("ST1704_THEME_ASSET_GENERATION_INVALID") from None


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
    payload = _regular_payload(SOURCE, MAX_SOURCE_BYTES)
    if (
        hashlib.sha256(payload).hexdigest() != SOURCE_SHA256
        or len(payload) < 33
        or payload[:8] != b"\x89PNG\r\n\x1a\n"
        or payload[12:16] != b"IHDR"
        or int.from_bytes(payload[16:20], "big") != 1536
        or int.from_bytes(payload[20:24], "big") != 1024
    ):
        _fail()


def _validate_webp(payload: bytes) -> None:
    if (
        len(payload) < 20
        or len(payload) > MAX_OUTPUT_BYTES
        or payload[:4] != b"RIFF"
        or payload[8:12] != b"WEBP"
        or int.from_bytes(payload[4:8], "little") != len(payload) - 8
        or b"ANIM" in payload[:128]
        or b"ANMF" in payload
    ):
        _fail()


def _render(directory: Path) -> bytes:
    target = directory / "article-portable-power-guide.webp"
    environment = {
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
        "TZ": "UTC",
    }
    command = [
        FFMPEG.as_posix(),
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        SOURCE.as_posix(),
        "-map_metadata",
        "-1",
        "-frames:v",
        "1",
        "-an",
        "-sn",
        "-dn",
        "-c:v",
        "libwebp",
        "-lossless",
        "0",
        "-quality",
        "82",
        "-compression_level",
        "6",
        "-preset",
        "picture",
        "-pix_fmt",
        "yuv420p",
        "-threads",
        "1",
        "-f",
        "webp",
        "-y",
        target.as_posix(),
    ]
    try:
        version = subprocess.run(
            [FFMPEG.as_posix(), "-version"],
            check=True,
            capture_output=True,
            env=environment,
            timeout=10,
        )
        if not version.stdout.startswith(b"ffmpeg version 4.4.2"):
            _fail()
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            env=environment,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        _fail()
    payload = _regular_payload(target, MAX_OUTPUT_BYTES)
    _validate_webp(payload)
    return payload


def generate(*, check: bool) -> str:
    _validate_source()
    if check:
        payload = _regular_payload(OUTPUT, MAX_OUTPUT_BYTES)
        _validate_webp(payload)
        digest = hashlib.sha256(payload).hexdigest()
        if digest != OUTPUT_SHA256:
            _fail()
        return digest
    with tempfile.TemporaryDirectory(prefix="raos-st1704-theme-asset.") as raw:
        payload = _render(Path(raw))
    digest = hashlib.sha256(payload).hexdigest()
    if digest != OUTPUT_SHA256:
        _fail()
    try:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        temporary = OUTPUT.with_name(f".{OUTPUT.name}.{os.getpid()}.tmp")
        descriptor = os.open(
            temporary,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
            0o644,
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, OUTPUT)
    except OSError:
        _fail()
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    try:
        digest = generate(check=arguments.check)
    except AssetGenerationFailure as error:
        print(str(error), file=os.sys.stderr)
        return 1
    print(f"ST1704_THEME_ASSET_OK sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

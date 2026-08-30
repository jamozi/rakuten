#!/usr/bin/env python3
"""Generate the ST-1704 theme's optimized raster assets from owner sources."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from typing import Final, NoReturn


ROOT: Final = Path(__file__).resolve().parents[1]
PORTABLE_POWER_SOURCE: Final = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/"
    "article-portable-power-guide.png"
)
PORTABLE_POWER_OUTPUT: Final = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/images/article-portable-power-guide.webp"
)
DISHWASHER_SOURCE: Final = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/"
    "article-countertop-dishwasher-guide.png"
)
DISHWASHER_OUTPUT: Final = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/images/article-countertop-dishwasher-guide.webp"
)
ROBOT_VACUUM_SOURCE: Final = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/"
    "article-robot-vacuum-guide.png"
)
ROBOT_VACUUM_OUTPUT: Final = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/images/article-robot-vacuum-guide.webp"
)
FFMPEG: Final = Path("/usr/bin/ffmpeg")
MAX_SOURCE_BYTES: Final = 8 * 1024 * 1024
MAX_OUTPUT_BYTES: Final = 2 * 1024 * 1024


@dataclass(frozen=True)
class AssetSpec:
    """Closed binding between one reviewed PNG and its deterministic WebP."""

    source: Path
    output: Path
    source_sha256: str
    output_sha256: str


ASSETS: Final = (
    AssetSpec(
        source=PORTABLE_POWER_SOURCE,
        output=PORTABLE_POWER_OUTPUT,
        source_sha256=(
            "703444cdf29740bb72de42d09c7c7222a3ee46a09bcaf4f78875df9131cc56d6"
        ),
        output_sha256=(
            "54b84689cff952f6a384982b89d2f56adfbdeff9ff03fe628fcaf5a949ab0f5a"
        ),
    ),
    AssetSpec(
        source=DISHWASHER_SOURCE,
        output=DISHWASHER_OUTPUT,
        source_sha256=(
            "26e50a383b313d79e65999e100fc82037a434550136fb293c3f20574965d090a"
        ),
        output_sha256=(
            "c36e87682ce9be33f70bc5b1a55e20a63b19ab6155172d670d5c019a984bcf9f"
        ),
    ),
    AssetSpec(
        source=ROBOT_VACUUM_SOURCE,
        output=ROBOT_VACUUM_OUTPUT,
        source_sha256=(
            "2ecd4dc8e55ea70a76287df30e44c874fea6292bf1be457934e049f1cfbcee4b"
        ),
        output_sha256=(
            "f589471aeed1064f2499ec5d32a8e9c4b6b14db8613d3b1743b37d245ecc2384"
        ),
    ),
)

# Compatibility aliases for callers that identify the original portable-power asset.
SOURCE: Final = PORTABLE_POWER_SOURCE
OUTPUT: Final = PORTABLE_POWER_OUTPUT
SOURCE_SHA256: Final = ASSETS[0].source_sha256
OUTPUT_SHA256: Final = ASSETS[0].output_sha256


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


def _validate_source(asset: AssetSpec) -> None:
    payload = _regular_payload(asset.source, MAX_SOURCE_BYTES)
    if (
        hashlib.sha256(payload).hexdigest() != asset.source_sha256
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


def _render(asset: AssetSpec, directory: Path) -> bytes:
    target = directory / asset.output.name
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
        asset.source.as_posix(),
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


def generate(*, check: bool) -> dict[str, str]:
    digests: dict[str, str] = {}
    for asset in ASSETS:
        _validate_source(asset)
        if check:
            payload = _regular_payload(asset.output, MAX_OUTPUT_BYTES)
            _validate_webp(payload)
        else:
            with tempfile.TemporaryDirectory(
                prefix="raos-st1704-theme-asset."
            ) as raw:
                payload = _render(asset, Path(raw))
        digest = hashlib.sha256(payload).hexdigest()
        if digest != asset.output_sha256:
            _fail()
        if not check:
            try:
                asset.output.parent.mkdir(parents=True, exist_ok=True)
                temporary = asset.output.with_name(
                    f".{asset.output.name}.{os.getpid()}.tmp"
                )
                descriptor = os.open(
                    temporary,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                    0o644,
                )
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, asset.output)
            except OSError:
                _fail()
        digests[asset.output.name] = digest
    return digests


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    try:
        digests = generate(check=arguments.check)
    except AssetGenerationFailure as error:
        print(str(error), file=os.sys.stderr)
        return 1
    inventory = ",".join(f"{name}:{digest}" for name, digest in digests.items())
    print(f"ST1704_THEME_ASSETS_OK assets={len(digests)} sha256={inventory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

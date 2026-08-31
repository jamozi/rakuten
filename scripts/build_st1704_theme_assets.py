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
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/"
    "article-portable-power-guide.png"
)
PORTABLE_POWER_OUTPUT: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/images/article-portable-power-guide.webp"
)
HOME_HERO_SOURCE: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/"
    "home-hero-v2.png"
)
HOME_HERO_OUTPUT: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/images/home-hero.webp"
)
SUITCASE_GUIDE_SOURCE: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/"
    "article-suitcase-guide-v2.png"
)
SUITCASE_GUIDE_OUTPUT: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/images/article-suitcase-guide.webp"
)
DISHWASHER_SOURCE: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/"
    "article-countertop-dishwasher-guide.png"
)
DISHWASHER_OUTPUT: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/images/article-countertop-dishwasher-guide.webp"
)
ROBOT_VACUUM_SOURCE: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/"
    "article-robot-vacuum-guide.png"
)
ROBOT_VACUUM_OUTPUT: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
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
    source_width: int = 1536
    source_height: int = 1024
    output_width: int = 1536
    output_height: int = 1024
    video_filter: str | None = None
    created_on: str = "2026-08-30"
    generation_intent: str = "EDITORIAL_SELECTION_GUIDE"
    allowed_uses: tuple[str, ...] = ("ARTICLE_EDITORIAL_ILLUSTRATION",)


ASSETS: Final = (
    AssetSpec(
        source=HOME_HERO_SOURCE,
        output=HOME_HERO_OUTPUT,
        source_sha256=(
            "91dc5bdd9d0047b45a324ca0aa72c3fe8bf5060baf9f8c52d59e022c81f24252"
        ),
        output_sha256=(
            "9a2d6d390ffd4ef0642d4c0a7a12da9daf7e904934ffd3f9e95e29907aedc493"
        ),
        source_width=1672,
        source_height=941,
        output_width=1600,
        output_height=900,
        video_filter="crop=1672:940:0:0,scale=1600:900:flags=lanczos",
        created_on="2026-08-31",
        generation_intent="ABSTRACT_EDITORIAL_PURCHASE_DECISION",
        allowed_uses=("HOMEPAGE_HERO", "SOCIAL_PREVIEW_FALLBACK"),
    ),
    AssetSpec(
        source=SUITCASE_GUIDE_SOURCE,
        output=SUITCASE_GUIDE_OUTPUT,
        source_sha256=(
            "14377a0035501c42e467e2fe962bef91059723992ddf35975a4106fb7ce7c949"
        ),
        output_sha256=(
            "dc8133377f21355ac0c187273d70904c305dd5687bf0e5e8ce3af76fab668046"
        ),
        source_width=1672,
        source_height=941,
        output_width=1600,
        output_height=900,
        video_filter="crop=1672:940:0:0,scale=1600:900:flags=lanczos",
        created_on="2026-08-31",
        generation_intent="GENERIC_SUITCASE_DIMENSION_AND_CAPACITY_COMPARISON",
        allowed_uses=("SUITCASE_ARTICLE_HEADER",),
    ),
    AssetSpec(
        source=PORTABLE_POWER_SOURCE,
        output=PORTABLE_POWER_OUTPUT,
        source_sha256=(
            "703444cdf29740bb72de42d09c7c7222a3ee46a09bcaf4f78875df9131cc56d6"
        ),
        output_sha256=(
            "54b84689cff952f6a384982b89d2f56adfbdeff9ff03fe628fcaf5a949ab0f5a"
        ),
        created_on="2026-08-28",
        generation_intent="PORTABLE_POWER_SELECTION_GUIDE",
        allowed_uses=("PORTABLE_POWER_ARTICLE_HEADER",),
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
        generation_intent="COUNTERTOP_DISHWASHER_SELECTION_GUIDE",
        allowed_uses=("DISHWASHER_ARTICLE_ILLUSTRATION",),
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
        generation_intent="ROBOT_VACUUM_SELECTION_GUIDE",
        allowed_uses=("ROBOT_VACUUM_ARTICLE_ILLUSTRATION",),
    ),
)

# Compatibility aliases for callers that identify the original portable-power asset.
SOURCE: Final = PORTABLE_POWER_SOURCE
OUTPUT: Final = PORTABLE_POWER_OUTPUT
SOURCE_SHA256: Final = next(
    asset.source_sha256 for asset in ASSETS if asset.source == PORTABLE_POWER_SOURCE
)
OUTPUT_SHA256: Final = next(
    asset.output_sha256 for asset in ASSETS if asset.output == PORTABLE_POWER_OUTPUT
)


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
        or int.from_bytes(payload[16:20], "big") != asset.source_width
        or int.from_bytes(payload[20:24], "big") != asset.source_height
        or b"c2pa" not in payload
        or b"OpenAI Media Service API" not in payload
    ):
        _fail()


def manifest_provenance(asset: AssetSpec) -> dict[str, object]:
    """Return the closed, non-prompt provenance record for a generated asset."""

    return {
        "allowed_modifications": [
            "CROP",
            "FORMAT_CONVERSION",
            "RESIZE",
            "WEB_OPTIMIZATION",
        ],
        "allowed_uses": list(asset.allowed_uses),
        "created_on": asset.created_on,
        "creation_method": "OPENAI_IMAGE_GENERATION",
        "creator_record": "SITE_OWNER_DIRECTED_OPENAI_MEDIA_SERVICE",
        "external_license_dependency": False,
        "generation_intent": asset.generation_intent,
        "original_sha256": asset.source_sha256,
        "original_source_path": asset.source.relative_to(ROOT).as_posix(),
        "provenance_evidence": "C2PA_OPENAI_MEDIA_SERVICE_API",
        "rights_basis": "OWNER_AUTHORIZED_GENERATION_FOR_THIS_SITE",
        "rights_status": "RECORDED_FOR_SITE_USE",
    }


def _validate_webp(payload: bytes, asset: AssetSpec) -> None:
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
    dimensions = _webp_dimensions(payload)
    if dimensions != (asset.output_width, asset.output_height):
        _fail()


def _webp_dimensions(payload: bytes) -> tuple[int, int] | None:
    vp8 = payload.find(b"VP8 ")
    if vp8 < 0 or vp8 + 30 > len(payload):
        return None
    frame = vp8 + 8
    if payload[frame + 3 : frame + 6] != b"\x9d\x01\x2a":
        return None
    width = int.from_bytes(payload[frame + 6 : frame + 8], "little") & 0x3FFF
    height = int.from_bytes(payload[frame + 8 : frame + 10], "little") & 0x3FFF
    return (width, height)


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
    ]
    if asset.video_filter is not None:
        command.extend(["-vf", asset.video_filter])
    command.extend(
        [
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
    )
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
    except OSError, subprocess.SubprocessError:
        _fail()
    payload = _regular_payload(target, MAX_OUTPUT_BYTES)
    _validate_webp(payload, asset)
    return payload


def generate(*, check: bool) -> dict[str, str]:
    digests: dict[str, str] = {}
    for asset in ASSETS:
        _validate_source(asset)
        if check:
            payload = _regular_payload(asset.output, MAX_OUTPUT_BYTES)
            _validate_webp(payload, asset)
        else:
            with tempfile.TemporaryDirectory(prefix="raos-st1704-theme-asset.") as raw:
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

from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import subprocess

import pytest

from scripts import build_st1704_theme_assets as generator


ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts/build_st1704_theme_assets.py"


def test_reviewed_assets_are_generated_webp_with_png_kept_outside_theme() -> None:
    assert len(generator.ASSETS) == 11
    for asset in generator.ASSETS:
        source = asset.source.read_bytes()
        output = asset.output.read_bytes()
        assert hashlib.sha256(source).hexdigest() == asset.source_sha256
        assert hashlib.sha256(output).hexdigest() == asset.output_sha256
        assert source[:8] == b"\x89PNG\r\n\x1a\n"
        assert b"c2pa" in source
        assert b"OpenAI Media Service API" in source
        assert output[:4] == b"RIFF"
        assert output[8:12] == b"WEBP"
        assert int.from_bytes(output[4:8], "little") == len(output) - 8
        assert not (asset.output.parent / f"{asset.output.stem}.png").exists()


def test_owner_generator_validates_the_tracked_webp() -> None:
    completed = subprocess.run(
        [str(ROOT / ".venv/bin/python"), str(GENERATOR), "--check"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    inventory = ",".join(
        f"{asset.output.name}:{asset.output_sha256}" for asset in generator.ASSETS
    )
    assert completed.stdout == (f"ST1704_THEME_ASSETS_OK assets=11 sha256={inventory}\n")


def test_check_is_portable_when_the_pinned_encoder_is_not_installed(
    monkeypatch,
) -> None:
    monkeypatch.setattr(generator, "FFMPEG", ROOT / "missing-ffmpeg")

    assert generator.generate(check=True) == {
        asset.output.name: asset.output_sha256 for asset in generator.ASSETS
    }


def test_check_rejects_a_corrupted_tracked_webp(tmp_path, monkeypatch) -> None:
    original = generator.ASSETS[0]
    corrupted = bytearray(original.output.read_bytes())
    corrupted[-1] ^= 1
    candidate = tmp_path / original.output.name
    candidate.write_bytes(corrupted)
    monkeypatch.setattr(
        generator,
        "ASSETS",
        (replace(original, output=candidate),),
    )

    with pytest.raises(
        generator.AssetGenerationFailure,
        match="ST1704_THEME_ASSET_GENERATION_INVALID",
    ):
        generator.generate(check=True)

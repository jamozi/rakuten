from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/"
    "article-portable-power-guide.png"
)
OUTPUT = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/images/article-portable-power-guide.webp"
)
GENERATOR = ROOT / "scripts/build_st1704_theme_assets.py"


def test_portable_power_asset_is_generated_webp_with_png_kept_outside_theme() -> None:
    source = SOURCE.read_bytes()
    output = OUTPUT.read_bytes()
    assert hashlib.sha256(source).hexdigest() == (
        "703444cdf29740bb72de42d09c7c7222a3ee46a09bcaf4f78875df9131cc56d6"
    )
    assert source[:8] == b"\x89PNG\r\n\x1a\n"
    assert output[:4] == b"RIFF"
    assert output[8:12] == b"WEBP"
    assert int.from_bytes(output[4:8], "little") == len(output) - 8
    assert not (OUTPUT.parent / "article-portable-power-guide.png").exists()


def test_owner_generator_reproduces_the_tracked_webp() -> None:
    completed = subprocess.run(
        [str(ROOT / ".venv/bin/python"), str(GENERATOR), "--check"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.startswith("ST1704_THEME_ASSET_OK sha256=")

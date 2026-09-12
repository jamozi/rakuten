from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import subprocess

import pytest

from scripts import build_st1704_theme_icons as generator


ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts/build_st1704_theme_icons.py"


def test_tracked_icons_are_the_deterministic_render_of_the_brand_mark() -> None:
    assert len(generator.ICONS) == 4
    assert hashlib.sha256(generator.SOURCE.read_bytes()).hexdigest() == generator.SOURCE_SHA256
    for icon in generator.ICONS:
        tracked = icon.output.read_bytes()
        assert hashlib.sha256(tracked).hexdigest() == icon.output_sha256
        assert generator.render(icon) == tracked
        if icon.kind == "png":
            assert generator.png_dimensions(tracked) == (icon.sizes[0], icon.sizes[0])
        else:
            assert generator.ico_sizes(tracked) == icon.sizes
    assert {icon.output.name for icon in generator.ICONS} == {
        "apple-touch-icon.png",
        "brand-mark-512.png",
        "favicon-32.png",
        "favicon.ico",
    }
    assert next(icon.sizes for icon in generator.ICONS if icon.output.name == "apple-touch-icon.png") == (180,)
    assert next(icon.sizes for icon in generator.ICONS if icon.output.name == "brand-mark-512.png") == (512,)


def test_rendered_pixels_follow_the_vector_geometry() -> None:
    size = 64
    rgba = generator.render_rgba(size)

    def pixel(x: int, y: int) -> tuple[int, int, int, int]:
        offset = (y * size + x) * 4
        return tuple(rgba[offset : offset + 4])

    assert pixel(0, 0) == (0, 0, 0, 0)  # rounded corner is transparent
    assert pixel(32, 5) == (*generator.BACKGROUND_RGB, 255)
    assert pixel(30, 19) == (*generator.BAR_RGB, 255)  # inside the first bar
    assert pixel(45, 45) == (*generator.DOT_RGB, 255)  # centre of the dot
    assert pixel(30, 33) == (*generator.BAR_RGB, 255)  # inside the second bar
    assert pixel(45, 33) == (*generator.BACKGROUND_RGB, 255)  # the second bar ends at x=40
    assert pixel(60, 45) == (*generator.BACKGROUND_RGB, 255)  # right of the dot
    assert pixel(3, 0) == (0, 0, 0, 0)  # outside the corner arc
    edge = pixel(10, 0)
    assert 0 < edge[3] < 255  # anti-aliased corner arc


def test_owner_generator_validates_the_tracked_icons() -> None:
    completed = subprocess.run(
        [str(ROOT / ".venv/bin/python"), str(GENERATOR), "--check"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    inventory = ",".join(
        f"{icon.output.name}:{icon.output_sha256}" for icon in generator.ICONS
    )
    assert completed.stdout == f"ST1704_THEME_ICONS_OK icons=4 sha256={inventory}\n"


def test_check_rejects_a_corrupted_tracked_icon(tmp_path, monkeypatch) -> None:
    original = generator.ICONS[0]
    corrupted = bytearray(original.output.read_bytes())
    corrupted[-1] ^= 1
    candidate = tmp_path / original.output.name
    candidate.write_bytes(corrupted)
    monkeypatch.setattr(generator, "ICONS", (replace(original, output=candidate),))
    with pytest.raises(generator.IconGenerationFailure, match="ST1704_THEME_ICON_GENERATION_INVALID"):
        generator.generate(check=True)


def test_provenance_is_the_vector_mark_without_external_dependencies() -> None:
    for icon in generator.ICONS:
        provenance = generator.manifest_provenance(icon)
        assert provenance["original_sha256"] == generator.SOURCE_SHA256
        assert provenance["original_source_path"].endswith("assets/images/brand-mark.svg")
        assert provenance["creation_method"] == "REPOSITORY_RASTERIZED_VECTOR"
        assert provenance["external_license_dependency"] is False
        assert provenance["rights_status"] == "RECORDED_FOR_SITE_USE"

"""Isolated visual and interaction checks for the reader measurement UI."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tests/reader_measurement_v1/browser_views.mjs"


def test_reader_measurement_views_are_isolated_accessible_and_exact() -> None:
    node = shutil.which("node")
    assert node, "explicit local Node runner required"
    assert HARNESS.is_file(), "browser views harness must exist"

    result = subprocess.run(
        [node, str(HARNESS)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    summary_line = next(
        line for line in result.stdout.splitlines() if line.startswith("BROWSER_VIEWS_JSON=")
    )
    summary = json.loads(summary_line.removeprefix("BROWSER_VIEWS_JSON="))
    assert summary["viewports"] == [360, 390, 768, 1024, 1440]
    assert summary["zoom_percent"] == 200
    assert summary["production_requests"] == 0
    assert summary["unexpected_requests"] == []
    assert len(summary["screenshots"]) == 10
    for relative_path in summary["screenshots"]:
        screenshot = ROOT / relative_path
        assert screenshot.is_file(), f"missing screenshot: {screenshot}"
        assert screenshot.stat().st_size > 0, f"empty screenshot: {screenshot}"
    assert "browser views OK" in result.stdout

"""PHP reads only the applied fixed article and its exact public projection."""

from pathlib import Path
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[2]
THEME = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
)


@pytest.mark.parametrize(
    "mode",
    [
        "valid",
        "unapproved",
        "raw-tampered",
        "runtime-tampered",
        "wrong-id",
        "password",
        "unpublished",
    ],
)
def test_purchase_runtime_requires_approved_unchanged_snapshot(mode):
    for slug in (
        "countertop-dishwasher-for-small-households",
        "dishwasher-running-cost",
        "privacy-policy",
    ):
        body = (
            ROOT / f"changes/wordpress-direct-publish-v1/articles/{slug}.html"
        ).read_text()
        harness = (
            Path(__file__)
            .with_name("purchase_snapshot_harness.php")
            .read_text()
            .removeprefix("<?php")
        )
        result = subprocess.run(
            [
                str(ROOT / "scripts/test-runtime-bin/php"),
                "-r",
                harness,
                "--",
                str(THEME),
                mode,
                body,
                slug,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr

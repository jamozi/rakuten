"""Execute the exact ST-1704 draft-writer role activation primitive."""

from __future__ import annotations

import glob
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tests/st1704_publication_operator/php/draft_writer_role_harness.php"


def _php_binary() -> str | None:
    configured = os.environ.get("RAOS_PHP_BIN")
    candidates = [configured, shutil.which("php")]
    candidates.extend(
        sorted(glob.glob("/tmp/raos-php-runtime.*/root/usr/bin/php8.1"))
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def test_draft_writer_role_php_behavior() -> None:
    php = _php_binary()
    if php is None:
        pytest.skip("PHP CLI is unavailable; set RAOS_PHP_BIN to run the harness")
    completed = subprocess.run(
        [php, "-d", "display_errors=1", str(HARNESS)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stderr == ""
    assert completed.stdout == "DRAFT_WRITER_ROLE_BEHAVIOR_OK\n"

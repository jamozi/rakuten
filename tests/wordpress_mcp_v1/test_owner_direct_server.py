from pathlib import Path
import os
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "harness", ["owner_direct_harness.php", "owner_direct_lease_harness.php"]
)
def test_owner_direct_authorization_and_draft_replay_behavior(harness):
    php = os.environ.get("RAOS_PHP_BIN") or shutil.which("php")
    if php is None:
        pytest.skip("PHP is required for the owner-direct behavior harness")
    result = subprocess.run(
        [php, "-n", str(ROOT / "tests/wordpress_mcp_v1/php" / harness)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OWNER_DIRECT_" in result.stdout and "_OK" in result.stdout

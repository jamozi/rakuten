from pathlib import Path
import shutil
import subprocess

import pytest


def test_local_cost_arithmetic_and_missing_data_behavior():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node runtime unavailable")
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [node, "--test", "tests/wordpress_local_preview/reader_running_cost.test.cjs"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

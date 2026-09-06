"""Focused PHP integration; each invocation uses a private tmpfs and no network."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
IMAGE = (
    "wordpress:7.1.0-php8.3-apache@sha256:"
    "8801a1239d7ba9fb340a5fc5ba0bf7f8d3652adbd64893e3fba7992ba618108e"
)


@pytest.mark.parametrize("arguments", [[], ["--without-plugin"]], ids=["local", "plugin-absent"])
def test_local_reader_guides_wordpress_integration(arguments):
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Focused PHP integration requires the existing local WordPress image")
    available = subprocess.run(
        [docker, "image", "inspect", IMAGE], capture_output=True, timeout=15, check=False
    )
    if available.returncode:
        pytest.skip("Pinned local WordPress image unavailable; this test never pulls images")
    result = subprocess.run(
        [docker, "run", "--pull=never", "--rm", "--network", "none", "--read-only",
         "--cap-drop=ALL", "--security-opt", "no-new-privileges",
         "--tmpfs", "/var/www/raos-local-preview:rw,noexec,nosuid,size=16m",
         "--mount", f"type=bind,src={ROOT},dst=/repo,readonly", "--workdir", "/repo",
         "--entrypoint", "php", IMAGE,
         "tests/wordpress_local_preview/local_reader_guides_integration.php", *arguments],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout
    assert result.stderr == ""

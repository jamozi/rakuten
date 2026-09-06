"""Execute the actual pinned Docker PHP fallback, including synthetic writes."""

import json
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


def fallback(*arguments):
    environment = dict(os.environ)
    environment.pop("RAOS_PHP_BIN", None)
    return subprocess.run(
        [str(ROOT / "scripts/test-runtime-bin/php"), *arguments],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=60,
    )


@pytest.mark.parametrize(
    "kind,plugin",
    [
        (
            "source",
            "packages/web-ui/src/decision-support-v2/wordpress/plugin/raos-v2-decision-support/raos-v2-decision-support.php",
        ),
        (
            "generated",
            "changes/raos-v2/phase-3/wordpress/artifact/raos-v2-decision-support/raos-v2-decision-support.php",
        ),
    ],
)
def test_phase3_actual_fallback_executes_all_assertions(kind, plugin):
    result = fallback(
        "tests/raos_v2/phase3-wordpress-runtime.php",
        kind,
        plugin,
        "changes/raos-v2/phase-3/generated/wordpress-update-candidate.v1.json",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "PASSED_LOCAL_CI_STUB"
    assert receipt["artifact_kind"] == kind
    assert receipt["assertion_count"] == 85
    assert receipt["php_version"].startswith("8.3.")
    assert receipt["capabilities_observed"] == {
        "wordpress_write": False,
        "network": False,
        "admin_hook": False,
        "rest_hook": False,
    }


def test_fallback_scratch_is_private_bounded_disposable_and_sources_readonly():
    source_directory = json.dumps(str(ROOT / "tests/raos_v2"))
    code = """
$directory = sys_get_temp_dir();
$path = $directory . '/raos-synthetic-scratch-probe';
$before = file_exists($path);
$written = file_put_contents($path, 'synthetic');
echo json_encode(array(
    'directory' => $directory,
    'mode' => fileperms($directory) & 0777,
    'capacity' => disk_total_space($directory),
    'before' => $before,
    'written' => $written,
    'source_writable' => is_writable(SOURCE_DIRECTORY),
    'wordpress_writable' => is_writable('/var/www/html'),
    'root_writable' => is_writable('/usr/local')
));
""".replace("SOURCE_DIRECTORY", source_directory)
    # Each invocation receives a new, empty tmpfs even though the path is identical.
    for _ in range(2):
        result = fallback("-r", code)
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout) == {
            "directory": "/tmp",
            "mode": 0o700,
            "capacity": 64 * 1024 * 1024,
            "before": False,
            "written": len("synthetic"),
            "source_writable": False,
            "wordpress_writable": False,
            "root_writable": False,
        }

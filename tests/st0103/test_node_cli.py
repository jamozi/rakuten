"""Node lock and inventory checks without Story-specific wrappers."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

from .support import REPOSITORY_ROOT


MANIFESTS = (
    "package.json",
    "apps/web/package.json",
    "packages/web-contracts/package.json",
    "packages/web-ui/package.json",
)


def run_inventory(*paths: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "node",
            "scripts/node_inventory.mjs",
            "verify-lock-manifests",
            str(REPOSITORY_ROOT / "package-lock.json"),
            *(str(path) for path in paths),
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_committed_node_lock_matches_all_workspace_manifests() -> None:
    result = run_inventory(*(REPOSITORY_ROOT / relative for relative in MANIFESTS))
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def test_node_lock_validator_rejects_manifest_drift(tmp_path: Path) -> None:
    source = REPOSITORY_ROOT / "package.json"
    manifest = json.loads(source.read_text(encoding="utf-8"))
    manifest["devDependencies"]["prettier"] = "3.9.5"
    drifted = tmp_path / "package.json"
    drifted.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    result = run_inventory(
        drifted,
        *(REPOSITORY_ROOT / relative for relative in MANIFESTS[1:]),
    )
    assert result.returncode != 0
    diagnostic = f"{result.stdout}\n{result.stderr}".lower()
    assert "lock" in diagnostic or "manifest" in diagnostic


def test_story_specific_node_wrapper_is_retired() -> None:
    assert not (REPOSITORY_ROOT / "scripts/node_toolchain.sh").exists()

"""CI v2 acceptance checks for the final-integration workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github/workflows/ci.yml"
WORKFLOW_TEXT = WORKFLOW_PATH.read_text(encoding="utf-8")
WORKFLOW: dict[str, Any] = yaml.load(WORKFLOW_TEXT, Loader=yaml.BaseLoader)


def test_workflow_has_one_unprivileged_final_integration_pipeline() -> None:
    assert WORKFLOW["on"] == {"pull_request": "", "workflow_dispatch": ""}
    assert WORKFLOW["permissions"] == {"contents": "read"}
    assert "pull_request_target" not in WORKFLOW_TEXT
    assert "workflow_run" not in WORKFLOW_TEXT
    assert WORKFLOW["concurrency"]["cancel-in-progress"] == "true"
    assert set(WORKFLOW["jobs"]) == {
        "lock",
        "static",
        "tests",
        "contracts",
        "data",
        "storage",
        "secrets",
        "final",
    }
    assert WORKFLOW["jobs"]["final"]["name"] == "Final Integration"
    assert set(WORKFLOW["jobs"]["final"]["needs"]) == {
        "lock",
        "static",
        "tests",
        "contracts",
        "data",
        "storage",
        "secrets",
    }


def test_external_actions_are_sha_pinned_and_checkout_never_persists_credentials() -> None:
    for job in WORKFLOW["jobs"].values():
        for step in job["steps"]:
            action = step.get("uses")
            if action is None or action.startswith("./"):
                continue
            repository, separator, revision = action.partition("@")
            assert repository
            assert separator == "@"
            assert len(revision) == 40
            assert all(character in "0123456789abcdef" for character in revision)
            if repository == "actions/checkout":
                assert step["with"]["persist-credentials"] == "false"


def test_lock_check_occurs_once_and_expensive_jobs_fan_out_after_it() -> None:
    lock = WORKFLOW["jobs"]["lock"]
    lock_commands = "\n".join(
        step["run"] for step in lock["steps"] if "run" in step
    )
    assert "uv lock --check" in lock_commands
    assert "npm ls --all" in lock_commands
    assert "npm@11.16.0" in lock_commands
    assert "scripts/verify_dev_toolchain.py" in lock_commands
    for job_id in ("static", "tests", "contracts", "data", "storage", "secrets"):
        assert WORKFLOW["jobs"][job_id]["needs"] == "lock"


def test_local_interface_is_reduced_to_five_development_commands() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    for target in ("setup", "generate", "check", "fast", "final"):
        assert f"\n{target}:" in f"\n{makefile}"
    for obsolete in (
        "ci-unit:",
        "ci-repository-policy:",
        "queue-generate:",
        "config-generate:",
        "content-ast-generate:",
        "ai-registry-generate:",
    ):
        assert obsolete not in makefile


def test_secret_scan_uses_the_current_reviewed_findings_without_live_access() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "scripts/scan_secrets.py --worktree" in makefile
    assert "--git-history" not in makefile
    assert "changes/st-0106/contracts/reviewed-secret-findings.v3.yaml" in makefile
    assert "RAOS_SECRET" not in WORKFLOW_TEXT

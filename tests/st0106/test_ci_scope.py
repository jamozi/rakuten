"""Focused tests for the ST-0106 affected-CI classifier."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import classify_ci_scope as classifier


@pytest.fixture
def scope_contract() -> dict[str, object]:
    return classifier.load_contract()


def test_docs_only_selects_light_static_and_secrets(
    scope_contract: dict[str, object],
) -> None:
    result = classifier.classify_paths(
        "pull_request", ["docs/worklogs/ST-0804.md", "README.md"], scope_contract
    )
    assert result["mode"] == "affected"
    assert result["risk"] == "docs_only"
    assert result["jobs"] == ["Static", "Secrets"]
    assert result["full_required"] is False


def test_single_story_selects_static_unit_and_secrets(
    scope_contract: dict[str, object],
) -> None:
    result = classifier.classify_paths(
        "pull_request",
        ["python/raos/domain/example.py", "tests/st0804/test_example.py"],
        scope_contract,
    )
    assert result["risk"] == "ordinary"
    assert result["story_suites"] == ["tests/st0804"]
    assert result["jobs"] == ["Static", "Unit", "Secrets"]


@pytest.mark.parametrize(
    "paths,expected_risk",
    [
        ([".github/workflows/ci.yml"], "high"),
        (["contracts/schema.json"], "high"),
        (["migrations/next.sql"], "high"),
        (["changes/st-0804/database/next.sql"], "high"),
        (["tests/st0804/test_a.py", "tests/st0805/test_b.py"], "multi_story"),
        (["unclassified.bin"], "unknown"),
    ],
)
def test_risky_or_ambiguous_changes_fail_safe_to_full(
    scope_contract: dict[str, object], paths: list[str], expected_risk: str
) -> None:
    result = classifier.classify_paths("pull_request", paths, scope_contract)
    assert result["risk"] == expected_risk
    assert result["jobs"] == list(classifier.EXPECTED_JOBS)
    assert result["full_required"] is True


@pytest.mark.parametrize("event", ["push", "schedule", "workflow_dispatch"])
def test_non_pr_events_always_run_full(
    scope_contract: dict[str, object], event: str
) -> None:
    result = classifier.classify_paths(event, [], scope_contract)
    assert result["risk"] == "full_event"
    assert result["jobs"] == list(classifier.EXPECTED_JOBS)


def test_secret_path_name_is_not_returned(
    scope_contract: dict[str, object],
) -> None:
    sensitive = ".secrets/do-not-echo-this-name"
    result = classifier.classify_paths("pull_request", [sensitive], scope_contract)
    rendered = json.dumps(result)
    assert sensitive not in rendered
    assert result["reasons"] == ["forbidden_secret_path_changed"]
    assert result["full_required"] is True


def test_github_output_contains_every_required_job_without_path_material(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "github-output"
    result = classifier.main(
        [
            "--event",
            "pull_request",
            "--path",
            "tests/st0804/test_example.py",
            "--github-output",
            str(output),
        ]
    )
    assert result == 0
    stdout = json.loads(capsys.readouterr().out)
    assert stdout["jobs"] == ["Static", "Unit", "Secrets"]
    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert values["static"] == "true"
    assert values["unit"] == "true"
    assert values["contracts"] == "false"
    assert values["database"] == "false"
    assert values["storage"] == "false"
    assert values["secrets"] == "true"


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True)


def test_git_rename_classifies_both_endpoints(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "st0106@example.invalid")
    _git(tmp_path, "config", "user.name", "ST-0106")
    source = tmp_path / "tests/st0804/test_old.py"
    source.parent.mkdir(parents=True)
    source.write_text("old = True\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "base")
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _git(tmp_path, "mv", "tests/st0804/test_old.py", "tests/st0804/test_new.py")
    _git(tmp_path, "commit", "-qam", "rename")

    assert classifier.git_changed_paths(tmp_path, base, "HEAD") == [
        "tests/st0804/test_new.py",
        "tests/st0804/test_old.py",
    ]


def test_contract_duplicate_key_is_rejected(tmp_path: Path) -> None:
    contract = tmp_path / classifier.CONTRACT_PATH
    contract.parent.mkdir(parents=True)
    contract.write_text('{"document": {}, "document": {}}', encoding="utf-8")
    with pytest.raises(classifier.ClassificationError, match="duplicate JSON key"):
        classifier.load_contract(tmp_path)

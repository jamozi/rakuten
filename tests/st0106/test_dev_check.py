"""Focused tests for the local developer-check runner."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import dev_check


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *arguments], cwd=root, check=True, capture_output=True
    )


def _repository(tmp_path: Path) -> str:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "st0106@example.invalid")
    _git(tmp_path, "config", "user.name", "ST-0106")
    (tmp_path / "tracked.txt").write_text("base\n", encoding="utf-8")
    secret = tmp_path / ".secrets/private-name"
    secret.parent.mkdir()
    secret.write_text("never-read\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt", ".secrets/private-name")
    _git(tmp_path, "commit", "-qm", "base")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_collect_changed_paths_unions_git_states_and_hides_secrets(
    tmp_path: Path,
) -> None:
    base = _repository(tmp_path)
    (tmp_path / "tracked.txt").write_text("worktree\n", encoding="utf-8")
    (tmp_path / "staged.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "untracked.sh").write_text("true\n", encoding="utf-8")
    secret = tmp_path / ".secrets/private-name"
    secret.write_text("still-never-read\n", encoding="utf-8")
    secret.chmod(0)
    _git(tmp_path, "add", "staged.py")

    paths, sensitive_count = dev_check.collect_changed_paths(tmp_path, base)

    assert paths == ["staged.py", "tracked.txt", "untracked.sh"]
    assert sensitive_count == 1


def test_node_projects_are_scoped_to_changed_workspace() -> None:
    assert dev_check._node_projects(["packages/web-contracts/src/index.ts"]) == [
        "packages/web-contracts/tsconfig.json"
    ]
    assert dev_check._node_projects(["apps/web/src/page.tsx"]) == ["tsconfig.json"]
    assert dev_check._node_projects(["package-lock.json"]) == [
        "packages/web-contracts/tsconfig.json",
        "tsconfig.json",
    ]


def test_run_checks_selects_changed_languages_story_and_generator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".venv/bin").mkdir(parents=True)
    (tmp_path / ".venv/bin/ruff").write_text("", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/example.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "scripts/example.sh").write_text("true\n", encoding="utf-8")
    (tmp_path / "tests/st0107").mkdir(parents=True)
    observed: list[tuple[str, list[str]]] = []

    def record(self: dev_check.StepRunner, name: str, command: list[str]) -> None:
        observed.append((name, list(command)))
        self.executed.append(
            {
                "name": name,
                "command": list(command),
                "status": "passed",
                "returncode": 0,
            }
        )

    monkeypatch.setattr(dev_check.StepRunner, "run", record)
    config = {
        "generator_checks": {
            "ST-0107": [["{python}", "-I", "generator.py", "--check"]]
        },
        "generator_owned_outputs": {"ST-0107": ["generated.json"]},
        "node_suffixes": [".cjs", ".js", ".jsx", ".mjs", ".ts", ".tsx"],
    }
    result = dev_check.run_checks(
        tmp_path,
        "ST-0107",
        "main",
        ["scripts/example.py", "scripts/example.sh", "generated.json"],
        config,
    )

    names = [name for name, _ in observed]
    assert "ruff-check-changed" in names
    assert "ruff-format-check-changed" in names
    assert "bash-syntax-changed" in names
    assert "pytest:tests/st0107" in names
    assert "generator-check:ST-0107:1" in names
    git_diff_commands = [
        command for name, command in observed if name.startswith("git-diff-check-")
    ]
    assert git_diff_commands
    assert all(
        ":(top,exclude).secrets" in command and ":(top,exclude).secrets/**" in command
        for command in git_diff_commands
    )
    assert all("generated.json" not in command for _, command in observed)
    assert result["status"] == "PASSED"
    assert result["executed_story_suites"] == ["tests/st0107"]


def test_run_checks_executes_every_declared_story_suite_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "tests/st0106").mkdir(parents=True)
    (tmp_path / "tests/st0107").mkdir()
    observed: list[tuple[str, list[str]]] = []

    def record(self: dev_check.StepRunner, name: str, command: list[str]) -> None:
        observed.append((name, list(command)))
        self.executed.append(
            {
                "name": name,
                "command": list(command),
                "status": "passed",
                "returncode": 0,
            }
        )

    monkeypatch.setattr(dev_check.StepRunner, "run", record)
    result = dev_check.run_checks(
        tmp_path,
        "ST-0106",
        "main",
        [],
        {
            "generator_checks": {},
            "generator_owned_outputs": {},
            "node_suffixes": [".cjs", ".js", ".jsx", ".mjs", ".ts", ".tsx"],
        },
        stories=["ST-0107", "ST-0106"],
    )

    suite_steps = [name for name, _ in observed if name.startswith("pytest:")]
    assert suite_steps == ["pytest:tests/st0106", "pytest:tests/st0107"]
    assert result["executed_story_suites"] == [
        "tests/st0106",
        "tests/st0107",
    ]


def test_run_checks_fails_closed_before_execution_when_declared_suite_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "tests/st0106").mkdir(parents=True)
    observed: list[str] = []

    def record(self: dev_check.StepRunner, name: str, command: list[str]) -> None:
        observed.append(name)

    monkeypatch.setattr(dev_check.StepRunner, "run", record)

    with pytest.raises(
        dev_check.DeveloperCheckError,
        match=r"isolated Story suite is missing: tests/st0107",
    ):
        dev_check.run_checks(
            tmp_path,
            "ST-0106",
            "main",
            [],
            {
                "generator_checks": {},
                "generator_owned_outputs": {},
                "node_suffixes": [
                    ".cjs",
                    ".js",
                    ".jsx",
                    ".mjs",
                    ".ts",
                    ".tsx",
                ],
            },
            stories=["ST-0106", "ST-0107"],
        )

    assert observed == []


def test_invalid_story_returns_machine_readable_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert dev_check.main(["--story", "not-a-story"]) == 2
    receipt = json.loads(capsys.readouterr().out)
    assert receipt == {
        "reason": "STORY must have the form ST-XXXX",
        "schema": "RAOS_DEV_CHECK_V1",
        "status": "ERROR",
    }


def test_changed_generator_output_runs_owner_check_for_another_story(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "tests/st0106").mkdir(parents=True)
    (tmp_path / "generated.json").write_text("{}\n", encoding="utf-8")
    observed: list[tuple[str, list[str]]] = []

    def record(self: dev_check.StepRunner, name: str, command: list[str]) -> None:
        observed.append((name, list(command)))
        self.executed.append(
            {
                "name": name,
                "command": list(command),
                "status": "passed",
                "returncode": 0,
            }
        )

    monkeypatch.setattr(dev_check.StepRunner, "run", record)
    config = {
        "generator_checks": {"ST-0107": [["generator", "--check"]]},
        "generator_owned_outputs": {"ST-0107": ["generated.json"]},
        "node_suffixes": [".cjs", ".js", ".jsx", ".mjs", ".ts", ".tsx"],
    }
    result = dev_check.run_checks(
        tmp_path,
        "ST-0106",
        "main",
        ["generated.json"],
        config,
    )

    assert "generator-check:ST-0107:1" in [name for name, _ in observed]
    assert "prettier-check-changed" not in [name for name, _ in observed]
    assert result["status"] == "PASSED"


def test_private_file_name_never_appears_in_error_receipt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base = _repository(tmp_path)
    private_name = ".secrets/do-not-print"
    private = tmp_path / private_name
    private.write_text("value\n", encoding="utf-8")
    _git(tmp_path, "add", private_name)
    assert (
        dev_check.main(
            [
                "--repository-root",
                str(tmp_path),
                "--story",
                "ST-0106",
                "--base-ref",
                base,
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert private_name not in captured.out + captured.err
    assert json.loads(captured.out) == {
        "reason": "forbidden_secret_path_changed",
        "schema": "RAOS_DEV_CHECK_V1",
        "sensitive_path_count": 1,
        "status": "ERROR",
    }


def test_story_scope_mismatch_fails_and_explicit_multi_story_is_reported(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / ".git").mkdir()
    config = dev_check.load_contract()
    monkeypatch.setattr(dev_check, "resolve_base_ref", lambda _root, _ref: "main")
    monkeypatch.setattr(
        dev_check,
        "collect_changed_paths",
        lambda _root, _base: (
            ["changes/st-0106/README.md", "tests/st0107/test_generation.py"],
            0,
        ),
    )
    monkeypatch.setattr(dev_check, "load_contract", lambda _root: config)

    assert (
        dev_check.main(["--repository-root", str(tmp_path), "--story", "ST-0106"]) == 2
    )
    mismatch = json.loads(capsys.readouterr().out)
    assert mismatch["reason"] == "changed_story_scope_mismatch"
    assert mismatch["detected_story_ids"] == ["ST-0106", "ST-0107"]
    assert mismatch["declared_story_ids"] == ["ST-0106"]

    monkeypatch.setattr(
        dev_check,
        "run_checks",
        lambda *_args, **_kwargs: {"schema": "RAOS_DEV_CHECK_V1", "status": "PASSED"},
    )
    assert (
        dev_check.main(
            [
                "--repository-root",
                str(tmp_path),
                "--story",
                "ST-0106",
                "--stories",
                "ST-0107,ST-0106",
            ]
        )
        == 0
    )
    allowed = json.loads(capsys.readouterr().out)
    assert allowed["detected_story_ids"] == ["ST-0106", "ST-0107"]
    assert allowed["declared_story_ids"] == ["ST-0106", "ST-0107"]

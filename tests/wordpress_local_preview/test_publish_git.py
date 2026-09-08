"""Git-only publication snapshots and resumable post-publication synchronization."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Any

import pytest

from scripts.raos_wordpress_publish_git import checkpoint, sync


ARTICLE_ROOT = Path("changes/wordpress-local-preview-v1/fixtures/articles")


def git(root: Path, *arguments: str, input_bytes: bytes | None = None) -> bytes:
    return subprocess.run(
        ("git", *arguments),
        cwd=root,
        input=input_bytes,
        capture_output=True,
        check=True,
    ).stdout


def repository(tmp_path: Path, *, identity: bool = True) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "--initial-branch=main")
    if identity:
        git(root, "config", "user.name", "RAOS Test")
        git(root, "config", "user.email", "raos-test@example.invalid")
    article = root / ARTICLE_ROOT / "original article.html"
    article.parent.mkdir(parents=True)
    article.write_text("original\n", encoding="utf-8")
    note = root / "notes/user work.txt"
    note.parent.mkdir()
    note.write_text("base\n", encoding="utf-8")
    git(root, "add", "--", ARTICLE_ROOT.as_posix(), "notes/user work.txt")
    git(root, "commit", "-m", "initial")
    return root


def test_checkpoint_commits_only_selected_rename_and_preserves_user_index(
    tmp_path: Path,
) -> None:
    """A shared-index implementation would overwrite the user's staged note."""
    root = repository(tmp_path)
    original_head = git(root, "rev-parse", "HEAD").strip().decode()
    old = root / ARTICLE_ROOT / "original article.html"
    new = root / ARTICLE_ROOT / "renamed article.html"
    old.rename(new)
    new.write_text("published bytes\n", encoding="utf-8")

    note = root / "notes/user work.txt"
    note.write_text("staged user bytes\n", encoding="utf-8")
    git(root, "add", "--", "notes/user work.txt")
    note.write_text("unstaged user bytes\n", encoding="utf-8")
    secret = root / ".secrets/token.txt"
    secret.parent.mkdir()
    secret.write_text("must not enter Git\n", encoding="utf-8")
    index_before = git(root, "diff", "--cached", "--raw", "-z")

    result = checkpoint(
        root,
        [
            (ARTICLE_ROOT / "original article.html").as_posix(),
            (ARTICLE_ROOT / "renamed article.html").as_posix(),
        ],
        "reader-20260908",
    )

    assert result["status"] == "created"
    assert result["branch"] == "codex/publish-reader-20260908"
    assert result["base_commit"] == original_head
    assert git(root, "rev-parse", "HEAD").strip().decode() == original_head
    assert git(root, "diff", "--cached", "--raw", "-z") == index_before
    assert (
        git(root, "show", f"{result['commit']}:{new.relative_to(root)}")
        == b"published bytes\n"
    )
    changed = set(
        value.decode()
        for value in git(
            root,
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            "-z",
            result["commit"],
        ).split(b"\0")
        if value
    )
    assert changed == {
        (ARTICLE_ROOT / "original article.html").as_posix(),
        (ARTICLE_ROOT / "renamed article.html").as_posix(),
    }
    assert (
        git(root, "rev-parse", f"{result['commit']}^{{tree}}").strip().decode()
        == result["tree"]
    )
    assert not git(
        root, "ls-tree", "-r", "--name-only", result["commit"], "--", ".secrets"
    )


def test_checkpoint_noop_and_same_snapshot_reuse_then_drift_conflict(
    tmp_path: Path,
) -> None:
    """Re-freezing after preview must detect changed bytes, not bless them."""
    root = repository(tmp_path)
    relative = (ARTICLE_ROOT / "original article.html").as_posix()
    clean = checkpoint(root, [relative], "clean")
    assert clean["status"] == "noop"
    assert clean["commit"] == clean["base_commit"]

    path = root / relative
    path.write_text("candidate\n", encoding="utf-8")
    created = checkpoint(root, [relative], "fixed")
    reused = checkpoint(root, [relative], "fixed")
    assert reused["status"] == "created"
    assert reused["checkpoint_action"] == "reused"
    assert reused["commit"] == created["commit"]

    path.write_text("changed after preview\n", encoding="utf-8")
    conflict = checkpoint(root, [relative], "fixed")
    assert conflict["status"] == "conflict"
    assert conflict["reason"] == "SNAPSHOT_DRIFT"
    assert conflict["commit"] == created["commit"]


def test_checkpoint_fails_closed_for_missing_identity_and_non_wordpress_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A commit must not silently use inferred identity or accept generic paths."""
    root = repository(tmp_path, identity=False)
    relative = (ARTICLE_ROOT / "original article.html").as_posix()
    (root / relative).write_text("candidate\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    missing = checkpoint(root, [relative], "missing-identity")
    assert missing["status"] == "error"
    assert missing["reason"] == "GIT_IDENTITY_MISSING"
    assert (
        subprocess.run(
            (
                "git",
                "show-ref",
                "--verify",
                "refs/heads/codex/publish-missing-identity",
            ),
            cwd=root,
            capture_output=True,
            check=False,
        ).returncode
        != 0
    )

    rejected = checkpoint(root, [".secrets/token.txt"], "secret")
    assert rejected["status"] == "error"
    assert rejected["reason"] == "PATH_NOT_ALLOWED"


def bare_origin(tmp_path: Path, root: Path) -> Path:
    origin = tmp_path / "origin.git"
    origin.mkdir()
    git(origin, "init", "--bare", "--initial-branch=main")
    git(root, "remote", "add", "origin", origin.as_posix())
    git(root, "push", "origin", "main")
    return origin


class GhRunner:
    def __init__(self, *, head: str, ci: str = "success", existing: bool = False):
        self.head = head
        self.ci = ci
        self.existing = existing
        self.created = False
        self.merged = False
        self.calls: list[tuple[str, ...]] = []
        self.body = ""

    def pr(self) -> dict[str, Any]:
        return {
            "number": 41,
            "url": "https://github.com/jamozi/rakuten/pull/41",
            "state": "MERGED" if self.merged else "OPEN",
            "isDraft": False,
            "headRefOid": self.head,
            "baseRefName": "main",
            "mergedAt": "2026-09-08T00:00:00Z" if self.merged else None,
        }

    def __call__(
        self, command: tuple[str, ...], **_kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        self.calls.append(command)
        if command[:3] == ("gh", "repo", "view"):
            payload: object = {
                "nameWithOwner": "jamozi/rakuten",
                "url": "https://github.com/jamozi/rakuten",
                "defaultBranchRef": {"name": "main"},
            }
        elif command[:3] == ("gh", "pr", "list"):
            payload = [self.pr()] if self.existing else []
        elif command[:3] == ("gh", "pr", "create"):
            body_path = Path(command[command.index("--body-file") + 1])
            self.body = body_path.read_text(encoding="utf-8")
            self.created = True
            self.existing = True
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=b"https://github.com/jamozi/rakuten/pull/41\n",
                stderr=b"",
            )
        elif command[:3] == ("gh", "pr", "view"):
            payload = self.pr()
        elif command[:2] == ("gh", "api") and "actions/runs?" in command[-1]:
            payload = {
                "workflow_runs": [
                    {
                        "id": 700,
                        "head_sha": self.head,
                        "path": ".github/workflows/ci.yml",
                        "event": "pull_request",
                        "run_number": 9,
                        "run_attempt": 1,
                        "status": "completed"
                        if self.ci != "pending"
                        else "in_progress",
                        "conclusion": self.ci if self.ci != "pending" else None,
                        "html_url": "https://github.com/jamozi/rakuten/actions/runs/700",
                    }
                ]
            }
        elif command[:2] == ("gh", "api") and "/jobs?" in command[-1]:
            payload = [
                {
                    "jobs": [
                        {
                            "id": 701,
                            "run_id": 700,
                            "run_attempt": 1,
                            "head_sha": self.head,
                            "name": "Final Integration",
                            "status": "completed",
                            "conclusion": self.ci,
                        }
                    ]
                }
            ]
        elif command[:3] == ("gh", "pr", "merge"):
            assert command[command.index("--match-head-commit") + 1] == self.head
            self.merged = True
            return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")
        else:  # pragma: no cover - exposes an unexpected external operation
            raise AssertionError(command)
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(payload).encode(), stderr=b""
        )


def publication_checkpoint(root: Path) -> dict[str, Any]:
    relative = (ARTICLE_ROOT / "original article.html").as_posix()
    (root / relative).write_text("published\n", encoding="utf-8")
    result = checkpoint(root, [relative], "post-publication")
    assert result["status"] == "created"
    return result


def test_sync_pushes_once_and_returns_pending_without_merging_before_exact_ci(
    tmp_path: Path,
) -> None:
    """Pending CI must remain separate from the already completed publication."""
    root = repository(tmp_path)
    frozen = publication_checkpoint(root)
    origin = bare_origin(tmp_path, root)
    runner = GhRunner(head=frozen["commit"], ci="pending", existing=True)

    result = sync(root, frozen, runner=runner)

    assert result["status"] == "pending"
    assert result["phase"] == "final_integration"
    assert result["publication"] == "ALREADY_COMPLETED_NO_REPUBLISH"
    assert result["resume"] == "CALL_SYNC_WITH_SAME_CHECKPOINT"
    assert not runner.merged
    assert (
        git(origin, "rev-parse", frozen["branch"]).strip().decode() == frozen["commit"]
    )


def test_sync_creates_pr_with_body_file_and_merges_only_successful_exact_head(
    tmp_path: Path,
) -> None:
    """A successful aggregate on another head must never merge this PR."""
    root = repository(tmp_path)
    frozen = publication_checkpoint(root)
    bare_origin(tmp_path, root)
    runner = GhRunner(head=frozen["commit"])

    result = sync(root, frozen, runner=runner)

    assert result["status"] == "merged"
    assert result["pr"]["number"] == 41
    assert result["final_integration"] == "success"
    assert frozen["snapshot_id"] in runner.body
    assert any(
        call[:3] == ("gh", "pr", "create") and "--body-file" in call
        for call in runner.calls
    )
    assert runner.merged


def test_sync_reports_conflict_when_pr_head_is_not_the_frozen_commit(
    tmp_path: Path,
) -> None:
    """A moved PR branch invalidates the exact-head merge precondition."""
    root = repository(tmp_path)
    frozen = publication_checkpoint(root)
    bare_origin(tmp_path, root)
    runner = GhRunner(head="f" * 40, existing=True)

    result = sync(root, frozen, runner=runner)

    assert result["status"] == "conflict"
    assert result["reason"] == "PR_HEAD_MISMATCH"
    assert not runner.merged

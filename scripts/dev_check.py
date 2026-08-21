#!/usr/bin/env python3
"""Run the focused, local RAOS developer check and emit a JSON receipt."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Final

SCRIPT_ROOT: Final = Path(__file__).resolve().parent
if os.fspath(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(SCRIPT_ROOT))

from classify_ci_scope import (  # noqa: E402
    ClassificationError,
    load_contract,
    normalize_path,
    story_ids,
)


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
STORY_ID: Final = re.compile(r"^ST-(\d{4})$")
SAFE_REVISION: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@^{}~+-]*$")
PYTHON_SUFFIXES: Final = {".py", ".pyi"}
SHELL_SUFFIXES: Final = {".bash", ".sh"}
NODE_FORMAT_EXTRA_SUFFIXES: Final = {
    ".css",
    ".json",
    ".md",
    ".yaml",
    ".yml",
}
MAX_STEP_OUTPUT: Final = 16 * 1024
SAFE_DIFF_PATHSPEC: Final = (
    ".",
    ":(top,exclude).secrets",
    ":(top,exclude).secrets/**",
)


class DeveloperCheckError(RuntimeError):
    """Raised when the local developer-check boundary is invalid."""


class DeveloperCheckScopeError(DeveloperCheckError):
    """The selected Story declaration does not equal detected changed Stories."""

    def __init__(self, detected: Sequence[str], declared: Sequence[str]) -> None:
        super().__init__("changed_story_scope_mismatch")
        self.detected = list(detected)
        self.declared = list(declared)


def _git_bytes(root: Path, arguments: Sequence[str]) -> bytes:
    result = subprocess.run(
        ["git", "-C", os.fspath(root), *arguments],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise DeveloperCheckError("unable to inspect repository changes")
    return result.stdout


def _nul_paths(content: bytes) -> list[str]:
    try:
        return [
            normalize_path(item.decode("utf-8"))
            for item in content.split(b"\0")
            if item
        ]
    except (UnicodeDecodeError, ClassificationError) as exc:
        raise DeveloperCheckError("repository contains an unsafe changed path") from exc


def _safe_revision(value: str, label: str) -> str:
    if value.startswith("-") or not SAFE_REVISION.fullmatch(value):
        raise DeveloperCheckError(f"{label} is not a safe Git revision")
    return value


def resolve_base_ref(root: Path, requested: str | None) -> str:
    candidates = [requested] if requested else ["main", "origin/main"]
    for candidate in candidates:
        safe = _safe_revision(candidate, "base ref")
        verified = subprocess.run(
            [
                "git",
                "-C",
                os.fspath(root),
                "rev-parse",
                "--verify",
                f"{safe}^{{commit}}",
            ],
            check=False,
            capture_output=True,
        )
        if verified.returncode == 0:
            return safe
    raise DeveloperCheckError("no usable base ref; pass BASE_REF explicitly")


def collect_changed_paths(root: Path, base_ref: str) -> tuple[list[str], int]:
    committed = _nul_paths(
        _git_bytes(
            root,
            [
                "diff",
                "--name-only",
                "--no-renames",
                "--diff-filter=ACDMRTUXB",
                "-z",
                f"{base_ref}...HEAD",
                "--",
            ],
        )
    )
    staged = _nul_paths(
        _git_bytes(
            root,
            [
                "diff",
                "--cached",
                "--name-only",
                "--no-renames",
                "--diff-filter=ACDMRTUXB",
                "-z",
                "--",
            ],
        )
    )
    unstaged = _nul_paths(
        _git_bytes(
            root,
            [
                "diff",
                "--name-only",
                "--no-renames",
                "--diff-filter=ACDMRTUXB",
                "-z",
                "--",
            ],
        )
    )
    untracked = _nul_paths(
        _git_bytes(root, ["ls-files", "--others", "--exclude-standard", "-z", "--"])
    )
    paths = sorted(set(committed + staged + unstaged + untracked))
    sensitive = [
        path for path in paths if path == ".secrets" or path.startswith(".secrets/")
    ]
    return [path for path in paths if path not in sensitive], len(sensitive)


def _existing_files(root: Path, paths: Sequence[str], suffixes: set[str]) -> list[str]:
    result: list[str] = []
    for relative in paths:
        if PurePosixPath(relative).suffix.lower() not in suffixes:
            continue
        target = root / relative
        try:
            metadata = target.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            raise DeveloperCheckError("changed source file must not be a symlink")
        if stat.S_ISREG(metadata.st_mode):
            result.append(relative)
    return result


class StepRunner:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.executed: list[dict[str, Any]] = []
        self.failed = False

    def run(self, name: str, command: Sequence[str]) -> None:
        public_command = [os.fspath(token) for token in command]
        try:
            result = subprocess.run(
                public_command,
                cwd=self.root,
                check=False,
                capture_output=True,
                text=True,
                errors="replace",
            )
            returncode = result.returncode
            combined = (result.stdout + result.stderr)[-MAX_STEP_OUTPUT:]
            if combined:
                print(
                    combined,
                    file=sys.stderr,
                    end="" if combined.endswith("\n") else "\n",
                )
        except FileNotFoundError:
            returncode = 127
            print(f"dev-check: executable missing for {name}", file=sys.stderr)
        status = "passed" if returncode == 0 else "failed"
        self.executed.append(
            {
                "name": name,
                "command": public_command,
                "status": status,
                "returncode": returncode,
            }
        )
        self.failed = self.failed or returncode != 0


def _node_projects(paths: Sequence[str]) -> list[str]:
    projects: set[str] = set()
    for path in paths:
        if path in {
            "package.json",
            "package-lock.json",
            "tsconfig.json",
            "tsconfig.base.json",
        }:
            projects.update(("tsconfig.json", "packages/web-contracts/tsconfig.json"))
        elif path.startswith("packages/web-contracts/"):
            projects.add("packages/web-contracts/tsconfig.json")
        elif path.startswith(("apps/", "packages/")) or path.endswith(
            ("eslint.config.mjs", "prettier.config.mjs", "vitest.config.ts")
        ):
            projects.add("tsconfig.json")
    return sorted(projects)


def _expand_generator_command(command: Sequence[str]) -> list[str]:
    return [sys.executable if token == "{python}" else token for token in command]


def declared_story_ids(selected_story: str, raw_stories: str | None) -> list[str]:
    if raw_stories is None:
        return [selected_story]
    values = raw_stories.split(",")
    if (
        not values
        or any(STORY_ID.fullmatch(value) is None for value in values)
        or len(values) != len(set(values))
        or selected_story not in values
    ):
        raise DeveloperCheckError(
            "STORIES must be a unique comma-separated set containing STORY"
        )
    return sorted(values)


def _story_suites(
    root: Path, selected_story: str, stories: Sequence[str] | None
) -> list[Path]:
    scoped_stories = [selected_story] if stories is None else list(stories)
    if (
        not scoped_stories
        or selected_story not in scoped_stories
        or len(scoped_stories) != len(set(scoped_stories))
        or any(STORY_ID.fullmatch(story) is None for story in scoped_stories)
    ):
        raise DeveloperCheckError(
            "Story suite scope must be a unique set containing selected Story"
        )

    suites: list[Path] = []
    for scoped_story in sorted(scoped_stories):
        story_number = STORY_ID.fullmatch(scoped_story)
        assert story_number is not None
        suite = root / f"tests/st{story_number.group(1)}"
        if not suite.is_dir() or suite.is_symlink():
            raise DeveloperCheckError(
                f"isolated Story suite is missing: {suite.relative_to(root)}"
            )
        suites.append(suite)
    return suites


def run_checks(
    root: Path,
    story: str,
    base_ref: str,
    paths: Sequence[str],
    config: Mapping[str, Any],
    *,
    stories: Sequence[str] | None = None,
) -> dict[str, Any]:
    story_suites = _story_suites(root, story, stories)
    runner = StepRunner(root)
    deferred: list[str] = []

    runner.run(
        "git-diff-check-committed",
        [
            "git",
            "diff",
            "--check",
            "--no-renames",
            f"{base_ref}...HEAD",
            "--",
            *SAFE_DIFF_PATHSPEC,
        ],
    )
    runner.run(
        "git-diff-check-staged",
        ["git", "diff", "--cached", "--check", "--", *SAFE_DIFF_PATHSPEC],
    )
    runner.run(
        "git-diff-check-worktree",
        ["git", "diff", "--check", "--", *SAFE_DIFF_PATHSPEC],
    )

    generator_outputs = {
        output
        for outputs in config["generator_owned_outputs"].values()
        for output in outputs
    }
    source_paths = [path for path in paths if path not in generator_outputs]

    python_files = _existing_files(root, source_paths, PYTHON_SUFFIXES)
    if python_files:
        ruff = root / ".venv/bin/ruff"
        runner.run(
            "ruff-check-changed", [os.fspath(ruff), "check", "--", *python_files]
        )
        runner.run(
            "ruff-format-check-changed",
            [os.fspath(ruff), "format", "--check", "--", *python_files],
        )
    else:
        deferred.append("ruff:no_changed_python")

    shell_files = _existing_files(root, paths, SHELL_SUFFIXES)
    if shell_files:
        runner.run("bash-syntax-changed", ["/bin/bash", "-n", *shell_files])
    else:
        deferred.append("bash_n:no_changed_shell")

    node_code_suffixes = set(config["node_suffixes"])
    node_files = _existing_files(
        root, source_paths, node_code_suffixes | NODE_FORMAT_EXTRA_SUFFIXES
    )
    node_projects = _node_projects(paths)
    if node_files or node_projects:
        node = shutil.which("node")
        if node is None:
            runner.run("node-missing", ["node", "--version"])
        else:
            if node_files:
                runner.run(
                    "prettier-check-changed",
                    [
                        node,
                        os.fspath(root / "node_modules/prettier/bin/prettier.cjs"),
                        "--check",
                        "--ignore-unknown",
                        *node_files,
                    ],
                )
            eslint_files = [
                path
                for path in node_files
                if PurePosixPath(path).suffix.lower() in node_code_suffixes
                and "/generated/" not in f"/{path}"
            ]
            if eslint_files:
                runner.run(
                    "eslint-changed",
                    [
                        node,
                        os.fspath(root / "node_modules/eslint/bin/eslint.js"),
                        "--max-warnings=0",
                        "--no-warn-ignored",
                        *eslint_files,
                    ],
                )
            for project in node_projects:
                runner.run(
                    f"typescript:{project}",
                    [
                        node,
                        os.fspath(root / "node_modules/typescript/bin/tsc"),
                        "--noEmit",
                        "--project",
                        os.fspath(root / project),
                    ],
                )
    else:
        deferred.append("node:no_changed_node_surface")

    executed_story_suites: list[str] = []
    for suite in story_suites:
        relative_suite = suite.relative_to(root)
        runner.run(
            f"pytest:{relative_suite}",
            [
                sys.executable,
                "-m",
                "pytest",
                "-p",
                "no:cacheprovider",
                "-q",
                "-m",
                "not raos_owner_private",
                os.fspath(relative_suite),
            ],
        )
        executed_story_suites.append(os.fspath(relative_suite))

    generator_stories = sorted(
        generator_story
        for generator_story, outputs in config["generator_owned_outputs"].items()
        if generator_story == story or generator_outputs.intersection(paths, outputs)
    )
    if generator_stories:
        for generator_story in generator_stories:
            commands = config["generator_checks"][generator_story]
            for index, command in enumerate(commands, start=1):
                runner.run(
                    f"generator-check:{generator_story}:{index}",
                    _expand_generator_command(command),
                )
    else:
        deferred.append(f"generator:{story}:not_allowlisted_or_unchanged")

    return {
        "schema": "RAOS_DEV_CHECK_V1",
        "status": "FAILED" if runner.failed else "PASSED",
        "story": story,
        "base_ref": base_ref,
        "changed_paths": list(paths),
        "executed_story_suites": executed_story_suites,
        "executed": runner.executed,
        "deferred": deferred,
    }


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--story", required=True)
    parser.add_argument(
        "--stories",
        help="explicit comma-separated changed Story set for a named integration slice",
    )
    parser.add_argument("--base-ref")
    parser.add_argument("--repository-root", type=Path, default=REPOSITORY_ROOT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        root = args.repository_root.resolve(strict=True)
        if root.is_symlink() or not (root / ".git").exists():
            raise DeveloperCheckError("repository root is not a Git worktree")
        if STORY_ID.fullmatch(args.story) is None:
            raise DeveloperCheckError("STORY must have the form ST-XXXX")
        base_ref = resolve_base_ref(root, args.base_ref)
        paths, sensitive_count = collect_changed_paths(root, base_ref)
        if sensitive_count:
            receipt = {
                "schema": "RAOS_DEV_CHECK_V1",
                "status": "ERROR",
                "reason": "forbidden_secret_path_changed",
                "sensitive_path_count": sensitive_count,
            }
            print(
                json.dumps(
                    receipt,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            return 2
        config = load_contract(root)
        detected = story_ids(paths, config["story_path_patterns"])
        declared = declared_story_ids(args.story, args.stories)
        if detected != declared:
            raise DeveloperCheckScopeError(detected, declared)
        receipt = run_checks(
            root, args.story, base_ref, paths, config, stories=declared
        )
        receipt["detected_story_ids"] = detected
        receipt["declared_story_ids"] = declared
    except DeveloperCheckScopeError as exc:
        receipt = {
            "schema": "RAOS_DEV_CHECK_V1",
            "status": "ERROR",
            "reason": "changed_story_scope_mismatch",
            "detected_story_ids": exc.detected,
            "declared_story_ids": exc.declared,
        }
        print(
            json.dumps(
                receipt, ensure_ascii=True, separators=(",", ":"), sort_keys=True
            )
        )
        return 2
    except (
        DeveloperCheckError,
        ClassificationError,
        FileNotFoundError,
        OSError,
    ) as exc:
        receipt = {
            "schema": "RAOS_DEV_CHECK_V1",
            "status": "ERROR",
            "reason": str(exc),
        }
        print(
            json.dumps(
                receipt, ensure_ascii=True, separators=(",", ":"), sort_keys=True
            )
        )
        return 2
    print(json.dumps(receipt, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
    return 0 if receipt["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

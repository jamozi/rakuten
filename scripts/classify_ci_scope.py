#!/usr/bin/env python3
"""Classify a Base CI run without network access or third-party packages."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Final


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path("changes/st-0106/contracts/developer-loop-scope.v1.json")
EXPECTED_KEYS: Final = {
    "document",
    "required_jobs",
    "always_jobs",
    "full_events",
    "docs_suffixes",
    "ordinary_prefixes",
    "high_risk_globs",
    "story_path_patterns",
    "node_suffixes",
    "generator_checks",
}
EXPECTED_JOBS: Final = (
    "Static",
    "Unit",
    "Contracts",
    "Database",
    "Storage",
    "Secrets",
)
STORY_PATH: Final = re.compile(r"^(?:changes/st-|tests/st)(\d{4})(?:/|$)")
SAFE_REVISION: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@^{}~+-]*$")
MAX_CONTRACT_BYTES: Final = 256 * 1024


class ClassificationError(RuntimeError):
    """Raised when classifier input or configuration is unsafe."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ClassificationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _private_regular_file(path: Path, label: str) -> bytes:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ClassificationError(f"{label} must be a regular non-symlink file")
    if metadata.st_size > MAX_CONTRACT_BYTES:
        raise ClassificationError(f"{label} exceeds size limit")
    return path.read_bytes()


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ClassificationError(f"{label} must be a string list")
    if len(value) != len(set(value)):
        raise ClassificationError(f"{label} contains duplicates")
    return value


def load_contract(root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    raw = _private_regular_file(root / CONTRACT_PATH, "scope contract")
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClassificationError("scope contract is not strict UTF-8 JSON") from exc
    if not isinstance(parsed, dict) or set(parsed) != EXPECTED_KEYS:
        raise ClassificationError("scope contract keys differ")
    document = parsed["document"]
    if document != {
        "id": "RAOS-DEVELOPER-LOOP-SCOPE-001",
        "version": "1.0.0",
        "story_id": "ST-0106",
    }:
        raise ClassificationError("scope contract identity differs")
    required = _string_list(parsed["required_jobs"], "required_jobs")
    if tuple(required) != EXPECTED_JOBS:
        raise ClassificationError("required job inventory differs")
    always = _string_list(parsed["always_jobs"], "always_jobs")
    if always != ["Secrets"]:
        raise ClassificationError("Secrets must be the sole always job")
    full_events = _string_list(parsed["full_events"], "full_events")
    if full_events != ["push", "schedule", "workflow_dispatch"]:
        raise ClassificationError("full event inventory differs")
    for key in (
        "docs_suffixes",
        "ordinary_prefixes",
        "high_risk_globs",
        "story_path_patterns",
        "node_suffixes",
    ):
        values = _string_list(parsed[key], key)
        if not values or any(not value for value in values):
            raise ClassificationError(f"{key} must not be empty")
    generators = parsed["generator_checks"]
    if not isinstance(generators, dict):
        raise ClassificationError("generator_checks must be a mapping")
    for story, commands in generators.items():
        if not re.fullmatch(r"ST-\d{4}", story) or not isinstance(commands, list):
            raise ClassificationError("generator_checks contains an invalid story")
        for command in commands:
            if (
                not isinstance(command, list)
                or not command
                or not all(isinstance(token, str) and token for token in command)
            ):
                raise ClassificationError("generator command must be tokenized")
    return parsed


def normalize_path(raw_path: str) -> str:
    if not raw_path or "\x00" in raw_path or "\\" in raw_path:
        raise ClassificationError("changed path is empty or unsafe")
    path = PurePosixPath(raw_path)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ClassificationError("changed path escapes the repository")
    return path.as_posix()


def _story_ids(paths: Sequence[str]) -> list[str]:
    identifiers = {
        f"ST-{match.group(1)}"
        for path in paths
        if (match := STORY_PATH.match(path)) is not None
    }
    return sorted(identifiers)


def _matches_any(path: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _full_result(
    config: Mapping[str, Any], risk: str, reasons: Sequence[str], path_count: int
) -> dict[str, Any]:
    return {
        "schema": "RAOS_CI_SCOPE_V1",
        "status": "OK",
        "mode": "full",
        "risk": risk,
        "story_suites": [],
        "jobs": list(config["required_jobs"]),
        "job_modes": {job: "full" for job in config["required_jobs"]},
        "reasons": list(reasons),
        "full_required": True,
        "path_count": path_count,
    }


def classify_paths(
    event: str, raw_paths: Sequence[str], config: Mapping[str, Any]
) -> dict[str, Any]:
    if event in config["full_events"]:
        return _full_result(config, "full_event", [f"full_event:{event}"], 0)
    if event != "pull_request":
        raise ClassificationError(f"unsupported event: {event}")

    paths = sorted({normalize_path(path) for path in raw_paths})
    sensitive_paths = [
        path for path in paths if path == ".secrets" or path.startswith(".secrets/")
    ]
    visible_paths = [path for path in paths if path not in sensitive_paths]
    if sensitive_paths:
        return _full_result(
            config,
            "high",
            ["forbidden_secret_path_changed"],
            len(paths),
        )
    if not visible_paths:
        return _full_result(config, "unknown", ["no_changed_paths"], 0)

    stories = _story_ids(visible_paths)
    if len(stories) > 1:
        return _full_result(
            config,
            "multi_story",
            ["multiple_story_scopes"],
            len(visible_paths),
        )

    high_risk = [
        path for path in visible_paths if _matches_any(path, config["high_risk_globs"])
    ]
    if high_risk:
        return _full_result(
            config,
            "high",
            ["high_risk_path"],
            len(visible_paths),
        )

    docs_only = all(
        PurePosixPath(path).suffix.lower() in config["docs_suffixes"]
        for path in visible_paths
    )
    if docs_only:
        return {
            "schema": "RAOS_CI_SCOPE_V1",
            "status": "OK",
            "mode": "affected",
            "risk": "docs_only",
            "story_suites": [],
            "jobs": ["Static", "Secrets"],
            "job_modes": {
                job: (
                    "light"
                    if job == "Static"
                    else "full"
                    if job == "Secrets"
                    else "skip"
                )
                for job in config["required_jobs"]
            },
            "reasons": ["documentation_only"],
            "full_required": False,
            "path_count": len(visible_paths),
        }

    unknown = [
        path
        for path in visible_paths
        if not any(path.startswith(prefix) for prefix in config["ordinary_prefixes"])
    ]
    if unknown or not stories:
        reason = "unknown_path" if unknown else "runtime_story_not_identifiable"
        return _full_result(config, "unknown", [reason], len(visible_paths))

    return {
        "schema": "RAOS_CI_SCOPE_V1",
        "status": "OK",
        "mode": "affected",
        "risk": "ordinary",
        "story_suites": [f"tests/st{stories[0].removeprefix('ST-').lower()}"],
        "jobs": ["Static", "Unit", "Secrets"],
        "job_modes": {
            job: (
                "focused"
                if job == "Unit"
                else "full"
                if job in {"Static", "Secrets"}
                else "skip"
            )
            for job in config["required_jobs"]
        },
        "reasons": [f"single_story:{stories[0]}"],
        "full_required": False,
        "path_count": len(visible_paths),
    }


def _validate_revision(revision: str, label: str) -> str:
    if revision.startswith("-") or not SAFE_REVISION.fullmatch(revision):
        raise ClassificationError(f"{label} is not a safe Git revision")
    return revision


def git_changed_paths(root: Path, base_ref: str, head_ref: str) -> list[str]:
    base = _validate_revision(base_ref, "base ref")
    head = _validate_revision(head_ref, "head ref")
    command = [
        "git",
        "-C",
        os.fspath(root),
        "diff",
        "--name-only",
        "--no-renames",
        "-z",
        "--diff-filter=ACDMRTUXB",
        f"{base}...{head}",
        "--",
    ]
    result = subprocess.run(command, check=False, capture_output=True)
    if result.returncode != 0:
        raise ClassificationError("unable to compute changed paths")
    try:
        return [part.decode("utf-8") for part in result.stdout.split(b"\0") if part]
    except UnicodeDecodeError as exc:
        raise ClassificationError("changed paths are not valid UTF-8") from exc


def _write_github_output(path: Path, result: Mapping[str, Any]) -> None:
    metadata = path.parent.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ClassificationError("GitHub output parent must be a real directory")
    selected = set(result["jobs"])
    lines = [
        f"{job.lower()}={'true' if job in selected else 'false'}"
        for job in EXPECTED_JOBS
    ]
    lines.extend(
        (
            f"full_required={'true' if result['full_required'] else 'false'}",
            f"static_mode={result['job_modes']['Static']}",
            f"unit_mode={result['job_modes']['Unit']}",
            "story_suite="
            + (result["story_suites"][0] if result["story_suites"] else ""),
            "classification_json="
            + json.dumps(result, ensure_ascii=True, separators=(",", ":")),
        )
    )
    with path.open("a", encoding="utf-8", newline="\n") as output:
        output.write("\n".join(lines) + "\n")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--event",
        required=True,
        choices=("pull_request", "push", "schedule", "workflow_dispatch"),
    )
    parser.add_argument("--base-ref")
    parser.add_argument("--head-ref", default="HEAD")
    parser.add_argument("--path", action="append", dest="paths", default=[])
    parser.add_argument("--github-output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        config = load_contract()
        if args.event == "pull_request" and not args.paths:
            if not args.base_ref:
                raise ClassificationError("pull_request requires --base-ref or --path")
            paths = git_changed_paths(REPOSITORY_ROOT, args.base_ref, args.head_ref)
        else:
            paths = args.paths
        result = classify_paths(args.event, paths, config)
        if args.github_output is not None:
            _write_github_output(args.github_output, result)
    except (ClassificationError, FileNotFoundError, OSError) as exc:
        print(f"ci-scope: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

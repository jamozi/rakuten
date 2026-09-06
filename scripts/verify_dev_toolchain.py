#!/usr/bin/env python3
"""Verify the repository development toolchain once at setup/final boundaries."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def _version(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(
            f"unable to run tool version check: {' '.join(command)}"
        ) from exc
    match = re.search(r"(?<![0-9])[0-9]+\.[0-9]+\.[0-9]+", result.stdout)
    if match is None:
        raise SystemExit(f"unable to parse tool version: {' '.join(command)}")
    return match.group(0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--test-runtime-only",
        action="store_true",
        help="set up the locked local PostgreSQL test runtime",
    )
    args = parser.parse_args()
    if args.test_runtime_only:
        from raos_test_runtime import setup_postgres

        environment = setup_postgres(os.environ)
        for key in ("RAOS_PG_BIN", "RAOS_PG_LIB", "LD_LIBRARY_PATH"):
            if key in environment:
                print(f"{key}={environment[key]}")
        github_env = os.environ.get("GITHUB_ENV")
        if github_env:
            with open(github_env, "a", encoding="utf-8") as stream:
                for key in ("RAOS_PG_BIN", "RAOS_PG_LIB", "LD_LIBRARY_PATH"):
                    if key in environment:
                        stream.write(f"{key}={environment[key]}\n")
        return 0
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    python_spec = project["project"]["requires-python"]
    expected_python = python_spec.removeprefix("==")
    expected_node = package["engines"]["node"]
    expected_npm = package["engines"]["npm"]
    node_command = os.environ.get("RAOS_NODE", "node")
    npm_cli = os.environ.get("RAOS_NPM_CLI")
    npm_command = (
        [node_command, npm_cli, "--version"]
        if npm_cli
        else [os.environ.get("RAOS_NPM", "npm"), "--version"]
    )
    observed = {
        "python": ".".join(str(item) for item in sys.version_info[:3]),
        "uv": _version(["uv", "--version"]),
        "node": _version([node_command, "--version"]),
        "npm": _version(npm_command),
    }
    if observed["python"] != expected_python:
        raise SystemExit(
            f"toolchain mismatch: python={observed['python']} expected={expected_python}"
        )
    if re.fullmatch(r"0\.12\.[0-9]+", observed["uv"]) is None:
        raise SystemExit(f"toolchain mismatch: uv={observed['uv']} expected=0.12.x")
    for name, expected in (("node", expected_node), ("npm", expected_npm)):
        if observed[name] != expected:
            raise SystemExit(
                f"toolchain mismatch: {name}={observed[name]} expected={expected}"
            )
    print(
        "RAOS_TOOLCHAIN status=PASS "
        + " ".join(f"{k}={v}" for k, v in observed.items())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

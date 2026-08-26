#!/usr/bin/env python3
"""Unified RAOS development build entrypoint."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import os
import subprocess
import sys
import tempfile

from raos_build_core import (
    BuildSpec,
    BuildRegistryError,
    OWNER_PRIVATE_OWNER_IDS,
    REPOSITORY_ROOT,
    affected_owners,
    canonical_json_bytes,
    check_active_manifest,
    changed_paths,
    discover_registry,
    generation_relevant_paths,
    registry_document,
    run_commands,
    topological_order,
    write_active_manifest,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="git base used for affected-owner discovery")
    subcommands = parser.add_subparsers(dest="command", required=True)
    registry = subcommands.add_parser("registry", help="validate the owner graph")
    registry.add_argument("--json", action="store_true", help="print the registry")
    generate = subcommands.add_parser("generate", help="run affected generators")
    generate.add_argument(
        "--all", action="store_true", help="regenerate every non-owner-private owner"
    )
    check = subcommands.add_parser("check", help="run generator checks")
    check.add_argument(
        "--all",
        action="store_true",
        help="check every owner instead of the merge-base affected set",
    )
    subcommands.add_parser("fast", help="run affected checks and focused tests")
    subcommands.add_parser("final", help="run all local, non-external tests")
    return parser


def _selected(
    registry: Mapping[str, BuildSpec], base: str | None
) -> tuple[str, ...]:
    return tuple(
        owner
        for owner in affected_owners(registry, changed_paths(base=base))
        if owner not in OWNER_PRIVATE_OWNER_IDS
    )


def _tests_for(
    registry: Mapping[str, BuildSpec], owners: tuple[str, ...]
) -> tuple[str, ...]:
    paths = {
        path.as_posix()
        for owner in owners
        for path in registry[owner].test_paths
    }
    return tuple(sorted(paths))


def _run(command: Sequence[str]) -> int:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        tuple(command), cwd=REPOSITORY_ROOT, env=environment, check=False
    ).returncode


def _run_tests(paths: tuple[str, ...], *, collect_threshold: int | None = None) -> int:
    if not paths:
        return 0
    if collect_threshold is not None:
        collection = subprocess.run(
            (
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                "-q",
                *paths,
            ),
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if collection.returncode != 0:
            sys.stdout.write(collection.stdout)
            sys.stderr.write(collection.stderr)
            return collection.returncode
        summary = collection.stdout.rsplit("\n", 2)[-2]
        digits = summary.split(" tests collected", 1)[0].rsplit(" ", 1)[-1]
        if not digits.isdigit() or int(digits) < collect_threshold:
            print(
                f"RAOS_TEST_COLLECTION expected>={collect_threshold} observed={digits}",
                file=sys.stderr,
            )
            return 1
        print(f"RAOS_TEST_COLLECTION count={digits} status=PASS")

    with tempfile.TemporaryDirectory(prefix="raos-pytest-") as temporary:
        common = (
            sys.executable,
            "-m",
            "pytest",
            "-s",
            "-p",
            "xdist.plugin",
        )
        parallel = _run(
            (
                *common,
                "--basetemp",
                f"{temporary}/parallel",
                "-n",
                "auto",
                "-m",
                "not serial and not live and not external and not raos_owner_private",
                *paths,
            )
        )
        if parallel != 0:
            return parallel
        serial = _run(
            (
                *common,
                "--basetemp",
                f"{temporary}/serial",
                "-m",
                "serial and not live and not external and not raos_owner_private",
                *paths,
            )
        )
    if serial == 5:  # no serial tests in a focused selection
        serial = 0
    if serial == 0:
        print("RAOS_EXTERNAL_TESTS live=NOT_RUN external=NOT_RUN owner_private=NOT_RUN")
    return serial


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        registry = discover_registry()
        if arguments.command == "registry":
            if arguments.json:
                sys.stdout.buffer.write(canonical_json_bytes(registry_document(registry)))
            else:
                print(f"RAOS_BUILD_REGISTRY owners={len(registry)} status=PASS")
            return 0

        changed = changed_paths(base=arguments.base)
        owners = (
            tuple(owner for owner in registry if owner not in OWNER_PRIVATE_OWNER_IDS)
            if arguments.command == "final"
            or (arguments.command == "check" and arguments.all)
            else tuple(
                owner
                for owner in affected_owners(registry, changed)
                if owner not in OWNER_PRIVATE_OWNER_IDS
            )
        )
        if arguments.command == "generate":
            generation_owners = (
                topological_order(registry)
                if arguments.all
                else affected_owners(registry, generation_relevant_paths(changed))
            )
            generation_owners = tuple(
                owner
                for owner in generation_owners
                if owner not in OWNER_PRIVATE_OWNER_IDS
            )
            run_commands(registry[owner].command() for owner in generation_owners)
            write_active_manifest(registry)
            print(
                "RAOS_GENERATE "
                f"owners={len(generation_owners)} manifest_owners={len(registry)} "
                "status=PASS"
            )
        elif arguments.command in {"check", "fast", "final"}:
            run_commands(registry[owner].command(check=True) for owner in owners)
            check_active_manifest(registry)
            print(f"RAOS_GENERATOR_CHECK owners={len(owners)} status=PASS")
        if arguments.command in {"fast", "final"}:
            tests = (
                _tests_for(registry, owners)
                if arguments.command == "fast"
                else ("tests",)
            )
            result = _run_tests(
                tests,
                collect_threshold=15_000 if arguments.command == "final" else None,
            )
            if result != 0:
                return result
        return 0
    except BuildRegistryError as exc:
        print(f"RAOS_BUILD_ERROR {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

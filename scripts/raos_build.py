#!/usr/bin/env python3
"""Unified RAOS development build entrypoint."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.raos_build_core import (  # noqa: E402
    BuildRegistryError,
    OWNER_PRIVATE_OWNER_IDS,
    REPOSITORY_ROOT,
    affected_generation_owners,
    canonical_json_bytes,
    changed_paths,
    discover_registry,
    registry_document,
    run_commands,
    topological_order,
    write_active_manifest,
)
from scripts.raos_checks import execute  # noqa: E402
from scripts.raos_test_plan import create_plan  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="git base used for affected discovery")
    commands = parser.add_subparsers(dest="command", required=True)
    registry = commands.add_parser("registry", help="validate the owner graph")
    registry.add_argument("--json", action="store_true")
    generate = commands.add_parser("generate", help="run affected generators")
    generate.add_argument("--all", action="store_true")
    for name in ("plan", "check", "fast", "final"):
        command = commands.add_parser(name)
        command.add_argument(
            "--all", action="store_true", help="select the complete local suite"
        )
        command.add_argument(
            "--critical", action="store_true", help="include critical PR regressions"
        )
        if name == "plan":
            command.add_argument("--json", action="store_true")
        if name == "fast":
            command.add_argument(
                "--stage",
                choices=(
                    "fast",
                    "static",
                    "tests",
                    "php",
                    "contracts",
                    "data",
                    "storage",
                    "secrets",
                ),
                default="fast",
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        registry = discover_registry()
        if arguments.command == "registry":
            if arguments.json:
                sys.stdout.buffer.write(
                    canonical_json_bytes(registry_document(registry))
                )
            else:
                print(f"RAOS_BUILD_REGISTRY owners={len(registry)} status=PASS")
            return 0
        changed = changed_paths(base=arguments.base)
        if arguments.command == "generate":
            owners = (
                topological_order(registry)
                if arguments.all
                else affected_generation_owners(registry, changed)
            )
            owners = tuple(o for o in owners if o not in OWNER_PRIVATE_OWNER_IDS)
            run_commands(registry[owner].command() for owner in owners)
            write_active_manifest(registry)
            print(f"RAOS_GENERATE owners={len(owners)} status=PASS")
            return 0
        plan = create_plan(
            REPOSITORY_ROOT,
            registry,
            changed,
            full=arguments.all or arguments.command == "final",
            critical=arguments.critical,
        )
        if arguments.command == "plan":
            print(json.dumps(plan.as_json(), ensure_ascii=False, indent=2))
            return 0
        print(
            f"RAOS_PLAN full={plan.full} generators={len(plan.generators)} "
            f"python_files={len(plan.python_tests)} node_files={len(plan.node_tests)}",
            flush=True,
        )
        if arguments.command == "final":
            for stage in (
                "static",
                "tests",
                "php",
                "contracts",
                "data",
                "storage",
                "secrets",
            ):
                result = execute(
                    REPOSITORY_ROOT, registry, plan, stage=stage, extended=True
                )
                if result:
                    return result
            return 0
        return execute(
            REPOSITORY_ROOT,
            registry,
            plan,
            stage="check" if arguments.command == "check" else arguments.stage,
            extended=arguments.all,
        )
    except (BuildRegistryError, RuntimeError, ValueError) as exc:
        print(f"RAOS_BUILD_ERROR {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

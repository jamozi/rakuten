"""Select CI jobs and aggregate explicitly required successful results."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.raos_build_core import REPOSITORY_ROOT, changed_paths, discover_registry  # noqa: E402
from scripts.raos_checks import execute  # noqa: E402
from scripts.raos_test_plan import JOBS, create_plan  # noqa: E402


def test_shards(*, full: bool, python_files: int, limit: int = 20) -> list[int]:
    """Fill the standard runner capacity without tiny affected-test jobs."""
    if not 1 <= limit <= 256:
        raise ValueError("RAOS_CI_TEST_SHARDS must be within 1..256")
    count = limit if full else min(limit, max(1, (python_files + 24) // 25))
    return list(range(1, count + 1))


def aggregate(
    required: object, results: object, *, plan_result: str, lock_result: str
) -> None:
    if plan_result != "success" or lock_result != "success":
        raise ValueError("planning and lock validation must succeed")
    if not isinstance(required, dict) or set(required) != set(JOBS):
        raise ValueError("missing or unknown required-job selection")
    if not isinstance(results, dict) or set(results) != set(JOBS):
        raise ValueError("missing or unknown job result")
    for job in JOBS:
        if not isinstance(required[job], bool):
            raise ValueError(f"invalid job selection: {job}")
        allowed = {"success"} if required[job] else {"skipped"}
        if results[job] not in allowed:
            raise ValueError(
                f"{job}: expected {sorted(allowed)}, observed {results[job]}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "aggregate", *JOBS))
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "aggregate":
            aggregate(
                json.loads(os.environ["RAOS_REQUIRED_JOBS"]),
                {
                    job: json.loads(os.environ["RAOS_JOB_RESULTS"])[job]["result"]
                    for job in JOBS
                },
                plan_result=os.environ["RAOS_PLAN_RESULT"],
                lock_result=os.environ["RAOS_LOCK_RESULT"],
            )
            print("Final Integration: all selected checks passed")
            return 0
        draft = os.environ.get("RAOS_CI_DRAFT") == "true"
        full = os.environ.get("RAOS_CI_EVENT") in {"schedule", "workflow_dispatch"}
        if draft and arguments.command != "plan":
            raise ValueError("Draft PRs do not execute CI checks")
        registry = discover_registry()
        plan = create_plan(
            REPOSITORY_ROOT,
            registry,
            changed_paths(base=os.environ.get("RAOS_CI_BASE") or None),
            full=full,
            critical=True,
        )
        if arguments.command == "plan":
            shards = test_shards(
                full=plan.full,
                python_files=len(plan.python_tests),
                limit=int(os.environ.get("RAOS_CI_TEST_SHARDS", "20")),
            )
            values = {
                job: str(selected and not draft).lower()
                for job, selected in plan.jobs.items()
            }
            values.update(
                required=json.dumps(plan.jobs, separators=(",", ":")),
                draft=str(draft).lower(),
                full=str(plan.full).lower(),
                shards=json.dumps(shards),
            )
            output = os.environ.get("GITHUB_OUTPUT")
            if output:
                with open(output, "a", encoding="utf-8") as stream:
                    for key, value in values.items():
                        stream.write(f"{key}={value}\n")
            report = (
                f"Verification: {'draft (checks deferred)' if draft else 'full' if plan.full else 'affected + critical'}\n\n"
                f"Python test files: {len(plan.python_tests)}; Node test files: "
                f"{len(plan.node_tests) + len(plan.vitest_tests)}; generators: {len(plan.generators)}.\n\n"
                f"Isolated test runners: {len(shards)}.\n\n"
                + "\n".join(f"- {reason}" for reason in plan.full_reasons)
                + "\n\nSelection detail: `scripts/raos_build.py --base <base> plan --critical --json`.\n"
            )
            print(report)
            summary = os.environ.get("GITHUB_STEP_SUMMARY")
            if summary:
                with open(summary, "a", encoding="utf-8") as stream:
                    stream.write(report)
            return 0
        if not plan.jobs[arguments.command]:
            raise ValueError(
                f"attempted to execute unselected job: {arguments.command}"
            )
        shard_index = shard_total = 1
        if arguments.command == "tests":
            shard_index = int(os.environ.get("RAOS_TEST_SHARD_INDEX", "1"))
            shard_total = int(os.environ.get("RAOS_TEST_SHARD_TOTAL", "1"))
            if not 1 <= shard_index <= shard_total:
                raise ValueError("test shard index must be within 1..total")
        return execute(
            REPOSITORY_ROOT,
            registry,
            plan,
            stage=arguments.command,
            extended=full,
            shard_index=shard_index,
            shard_total=shard_total,
        )
    except (KeyError, RuntimeError, ValueError) as exc:
        print(f"RAOS_CI_ERROR {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

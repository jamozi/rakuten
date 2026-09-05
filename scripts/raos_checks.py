"""Execute the shared test plan without regenerating repository artifacts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import unquote, urlsplit

from scripts.raos_build_core import BuildSpec, check_active_manifest
from scripts.raos_test_plan import TestPlan
from scripts.raos_test_shards import belongs_to_shard


LOCAL_MARKERS = "not live and not external and not raos_owner_private"
PYTEST_GROUPS = {
    "parallel": f"not serial and not database and not storage and {LOCAL_MARKERS}",
    "serial": f"serial and not database and not storage and {LOCAL_MARKERS}",
    "data": f"database and not storage and {LOCAL_MARKERS}",
    "storage": f"storage and {LOCAL_MARKERS}",
}


def run(
    root: Path, command: Sequence[str], label: str, *, empty_ok: bool = False
) -> int:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["RAOS_CHECK_LABEL"] = label
    environment["PYTHONPATH"] = os.pathsep.join((str(root), str(root / "python")))
    environment.setdefault(
        "PYTEST_XDIST_AUTO_NUM_WORKERS", str(min(4, os.cpu_count() or 1))
    )
    started = time.monotonic()
    result = subprocess.run(
        tuple(command), cwd=root, env=environment, check=False
    ).returncode
    if empty_ok and result == 5:
        result = 0
    elapsed = time.monotonic() - started
    print(f"RAOS_CHECK name={label} seconds={elapsed:.2f} result={result}", flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write(
                f"- {label}: {elapsed:.2f}s, {'PASS' if result == 0 else 'FAIL'}\n"
            )
    return result


def check_documents(root: Path, documents: Sequence[str]) -> None:
    for document in documents:
        source = (root / document).read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^\s)]+)\)", source):
            parsed = urlsplit(target.strip("<>"))
            if parsed.scheme or not parsed.path or parsed.path.startswith("/"):
                continue
            # Check local Markdown links, not illustrative code paths or URLs.
            path = Path(unquote(parsed.path))
            if (
                path.suffix == ".md"
                and not (root / document).parent.joinpath(path).exists()
            ):
                raise ValueError(f"broken document reference: {document}: {target}")


def _python_tests(
    root: Path,
    plan: TestPlan,
    group: str,
    *,
    shard_index: int = 1,
    shard_total: int = 1,
) -> int:
    if not plan.python_tests:
        return 0
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--tb=short",
        "--durations=15",
        "-o",
        "faulthandler_timeout=120",
        "-p",
        "xdist.plugin",
        "-p",
        "scripts.raos_pytest_summary",
        "-p",
        "scripts.raos_test_shards",
        f"--raos-shard-index={shard_index}",
        f"--raos-shard-total={shard_total}",
        "-m",
        PYTEST_GROUPS[group],
    ]
    if group == "parallel":
        command.extend(("-n", "auto"))
    command.extend(plan.python_tests)
    # Empty marker partitions are valid; an empty complete selection is not
    # accepted by the planner for critical/full runs.
    return run(root, command, f"pytest-{group}", empty_ok=True)


def execute(
    root: Path,
    registry: Mapping[str, BuildSpec],
    plan: TestPlan,
    *,
    stage: str = "fast",
    extended: bool = False,
    shard_index: int = 1,
    shard_total: int = 1,
) -> int:
    def call(command: Sequence[str], label: str) -> None:
        if run(root, command, label):
            raise RuntimeError(f"check failed: {label}")

    if stage in {"fast", "check", "static"}:
        call(("git", "diff", "--check"), "whitespace")
        check_documents(root, plan.documents)
        if plan.full:
            call(("make", "final-static"), "static-full")
        else:
            if plan.static_python:
                call(
                    (sys.executable, "-m", "ruff", "check", *plan.static_python), "ruff"
                )
                if any(
                    p.startswith("python/") or p.endswith("/projection.py")
                    for p in plan.static_python
                ):
                    call(
                        (
                            sys.executable,
                            "-m",
                            "mypy",
                            "python/raos",
                            "packages/web-ui/src/decision-support-v2/wordpress/projection.py",
                        ),
                        "mypy",
                    )
            if plan.static_node:
                for script in ("format:check", "lint", "typecheck"):
                    call(("npm", "run", script), script)
        if extended:
            call(("npm", "run", "pyright"), "pyright")
        for owner in plan.generators:
            call(registry[owner].command(check=True), owner)
        if plan.generators or plan.full:
            check_active_manifest(registry, root=root)
            call((sys.executable, "scripts/status_v2.py", "--check"), "status")
    if stage in {"fast", "tests"}:
        for group in ("parallel", "serial"):
            result = _python_tests(
                root, plan, group, shard_index=shard_index, shard_total=shard_total
            )
            if result:
                return result
        node_tests = tuple(
            p for p in plan.node_tests if belongs_to_shard(p, shard_index, shard_total)
        )
        vitest_tests = tuple(
            p
            for p in plan.vitest_tests
            if belongs_to_shard(p, shard_index, shard_total)
        )
        if node_tests:
            call(
                ("node", "--experimental-strip-types", "--test", *node_tests),
                "node-tests",
            )
        if vitest_tests:
            call(("npm", "run", "test:unit", "--", *vitest_tests), "vitest")
    if stage in {"fast", "php"} and plan.php:
        harness = "tests/raos_v2/phase3-wordpress-runtime.php"
        candidate = (
            "changes/raos-v2/phase-3/generated/wordpress-update-candidate.v1.json"
        )
        call(("php", "-l", harness), "php-lint-harness")
        for kind, plugin in (
            (
                "source",
                "packages/web-ui/src/decision-support-v2/wordpress/plugin/raos-v2-decision-support/raos-v2-decision-support.php",
            ),
            (
                "generated",
                "changes/raos-v2/phase-3/wordpress/artifact/raos-v2-decision-support/raos-v2-decision-support.php",
            ),
        ):
            call(("php", "-l", plugin), f"php-lint-{kind}")
            call(("php", harness, kind, plugin, candidate), f"php-runtime-{kind}")
    for group, service in (("data", "database"), ("storage", "storage")):
        if stage == group or (stage == "fast" and plan.jobs[group]):
            # Service smoke tests are CI/full diagnostics. Focused local tests
            # retain the suites' existing recorded/fake service adapters.
            if stage == group:
                call(("make", service), service)
            result = _python_tests(root, plan, group)
            if result:
                return result
    if stage == "contracts":
        call(
            (sys.executable, "scripts/build_st0104_contract_repository.py", "--check"),
            "contract-generator",
        )
        call(
            (sys.executable, "scripts/verify_contract_repository.py"),
            "contract-verifier",
        )
        # tests/st0104 is already routed by the shared plan, not run twice.
    if stage == "secrets":
        call(("make", "final-secrets"), "secrets")
    return 0

"""Read-only test selection shared by local development and CI.

Generator ownership covers artifacts; import consumers cover ordinary code.
Explicit component routes cover non-Python entrypoints and dynamic loading.
Unmapped executable/configuration inputs deliberately request the full suite.
"""

from __future__ import annotations

import ast
from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
import posixpath
import re
import subprocess

from scripts.raos_build_core import (
    BuildSpec,
    OWNER_PRIVATE_OWNER_IDS,
    FINGERPRINT_INPUT_CATALOGS,
    affected_owners,
)


# Small behavioral suites, not the complete legacy security/contract catalogs.
CRITICAL_TESTS = (
    "tests/st0401/test_authentication.py",
    "tests/st0403/test_authorization.py",
    "tests/st0404/test_security.py",
    "tests/st0901_pr3/test_authorization_idempotency.py",
    "tests/st0902_v2/test_domain.py",
    "tests/st0905/test_runtime_hostile_v2.py",
    "tests/st1001/public-shell-boundaries.test.ts",
    "tests/st1004_v2/disclosure-affiliate-negative.test.ts",
    "tests/st1305_v2/test_reconciliation_negative.py",
)

# Routes intentionally use executable boundaries, not Story IDs. Story-derived
# generator routes remain available for compatibility with existing artifacts.
COMPONENT_ROUTES = (
    (("tools/affiliate_ingestion/",), ("tests/test_affiliate_ingestion.py",)),
    (
        ("packages/wordpress-mcp-bridge/", "changes/wordpress-mcp-v1/"),
        ("tests/wordpress_mcp_v1",),
    ),
    (("changes/wordpress-local-preview-v1/",), ("tests/wordpress_local_preview",)),
    (
        (
            "scripts/raos_wordpress_runtime_audit.py",
            "scripts/raos_wordpress_seo_audit.py",
            "scripts/raos_wordpress_incremental_seo_audit.py",
        ),
        ("tests/wordpress_seo_audit_v1",),
    ),
    (
        ("changes/raos-v2/", "packages/web-ui/src/decision-support-v2/"),
        ("tests/raos_v2",),
    ),
)

FULL_INPUTS = {
    "uv.lock",
    "pyproject.toml",
    "uv.toml",
    ".python-version",
    "package-lock.json",
    "package.json",
    "Makefile",
    "tests/conftest.py",
    "scripts/raos_build.py",
    "scripts/raos_build_core.py",
    "scripts/raos_test_plan.py",
    "scripts/raos_checks.py",
    "scripts/raos_ci.py",
    "scripts/raos_pytest_summary.py",
    "scripts/raos_test_shards.py",
    "vitest.config.ts",
    "tsconfig.json",
    "tsconfig.base.json",
    "pyrightconfig.json",
    "eslint.config.mjs",
    "prettier.config.mjs",
}
DOC_SUFFIXES = {".md", ".rst", ".txt"}
JOBS = ("static", "tests", "php", "contracts", "data", "storage", "secrets")


@dataclass(frozen=True)
class TestPlan:
    changed_files: tuple[str, ...]
    full: bool
    full_reasons: tuple[str, ...]
    generators: tuple[str, ...]
    python_tests: tuple[str, ...]
    node_tests: tuple[str, ...]
    vitest_tests: tuple[str, ...]
    php: bool
    static_python: tuple[str, ...]
    static_node: bool
    documents: tuple[str, ...]
    jobs: dict[str, bool]
    reasons: dict[str, tuple[str, ...]]

    def as_json(self) -> dict[str, object]:
        return asdict(self)


def _under(path: str, prefix: str) -> bool:
    return path == prefix.rstrip("/") or path.startswith(prefix.rstrip("/") + "/")


def _tracked(root: Path) -> set[Path]:
    result = subprocess.run(
        ("git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"),
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return {Path(p) for p in result.stdout.split("\0") if p}


def _module(path: Path) -> str:
    parts = list(path.with_suffix("").parts)
    if parts[0] == "python":
        parts.pop(0)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _consumer_graph(
    root: Path, files: set[Path], changed: set[Path]
) -> dict[Path, set[Path]]:
    """Follow Python imports, JS imports/exports and literal local file references.

    Include deleted paths in the module index so removal still selects callers.
    Parse failures are handled by the selected compiler/test, not ignored as docs.
    """
    universe = files | changed
    sources = {
        p
        for p in universe
        if p.suffix in {".py", ".ts", ".tsx", ".js", ".mjs", ".php"}
        and p.parts[0] in {"python", "scripts", "tests", "tools", "packages", "apps"}
    }
    modules: dict[str, set[Path]] = defaultdict(set)
    for path in sources:
        if path.suffix == ".py":
            modules[_module(path)].add(path)
            if path.parts[0] == "scripts":
                modules[path.stem].add(path)
    reverse: dict[Path, set[Path]] = defaultdict(set)
    for path in sources:
        # Shared verification catalogs contain path/owner inventories. These
        # literals are metadata; real imports still contribute dependencies.
        skip_literals = path.as_posix() in FULL_INPUTS
        absolute = root / path
        if not absolute.is_file() or absolute.is_symlink():
            continue
        source = absolute.read_text(encoding="utf-8")
        dependencies: set[Path] = set()
        literals: list[str] = []
        if path.suffix == ".py":
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    prefix = node.module or ""
                    if node.level:
                        package = _module(path).split(".")
                        if path.name != "__init__.py":
                            package.pop()
                        prefix = ".".join(
                            package[: len(package) - node.level + 1]
                            + ([prefix] if prefix else [])
                        )
                    names = [
                        prefix,
                        *(f"{prefix}.{alias.name}" for alias in node.names),
                    ]
                elif (
                    not skip_literals
                    and isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                ):
                    literals.append(node.value)
                for name in names:
                    pieces = name.split(".")
                    for index in range(1, len(pieces) + 1):
                        dependencies.update(modules.get(".".join(pieces[:index]), ()))
        else:
            literals = re.findall(r"['\"]([^'\"\n]+)['\"]", source)
        for value in literals:
            if not value or "\x00" in value or "\n" in value or len(value) > 300:
                continue
            dependencies.update(modules.get(value, ()))
            if "/" not in value and "." not in value:
                continue
            candidates = [Path(value.removeprefix("repo://"))]
            if value.startswith("."):
                relative = Path(posixpath.normpath((path.parent / value).as_posix()))
                if not relative.is_absolute() and ".." not in relative.parts:
                    candidates.append(relative)
            for candidate in candidates:
                if candidate in universe:
                    dependencies.add(candidate)
                if candidate.name and candidate.suffix in {"", ".js"}:
                    dependencies.update(
                        p
                        for p in (candidate.with_suffix(".ts"), candidate / "index.ts")
                        if p in sources
                    )
        for dependency in dependencies:
            reverse[dependency].add(path)
    return reverse


def _consumers(reverse: Mapping[Path, set[Path]], changed: set[Path]) -> set[Path]:
    found = set(changed)
    pending = deque(changed)
    while pending:
        for consumer in reverse.get(pending.popleft(), ()):
            if consumer not in found:
                found.add(consumer)
                pending.append(consumer)
    return found


def create_plan(
    root: Path,
    registry: Mapping[str, BuildSpec],
    paths: Sequence[Path],
    *,
    full: bool = False,
    critical: bool = False,
) -> TestPlan:
    root = root.resolve()
    changed = set(paths)
    files = _tracked(root)
    reasons: dict[str, set[str]] = defaultdict(set)
    full_reasons = {"explicit full run"} if full else set()
    owners = affected_owners(registry, changed)
    # Check edited generated manifests too. The narrower generation-input
    # filter is appropriate for regeneration, not for detecting output drift.
    generator_owners = affected_owners(
        registry,
        tuple(p for p in changed if p.parts[0] != "tests")
        + tuple(
            registry[o].generator for o in owners if o in FINGERPRINT_INPUT_CATALOGS
        ),
    )
    selected: set[Path] = set()

    def add_test(path: Path, reason: str) -> None:
        matches = {f for f in files if _under(f.as_posix(), path.as_posix())}
        for match in matches:
            if match.parts[0] == "tests":
                selected.add(match)
                reasons[match.as_posix()].add(reason)

    reverse = _consumer_graph(root, files, changed)
    consumers = _consumers(reverse, changed)
    for path in consumers:
        if path.parts[0] == "tests":
            if path.name.startswith("test_") or ".test." in path.name:
                add_test(
                    path if (root / path).exists() else path.parent,
                    "changed test or import consumer",
                )
            else:
                add_test(path.parent, "shared test helper or fixture")
    for owner in owners:
        for test in registry[owner].test_paths:
            add_test(test, f"generator owner: {owner}")

    for path in changed:
        value = path.as_posix()
        if (
            value in FULL_INPUTS
            or value.startswith(".github/")
            or path.name == "package.json"
        ):
            full_reasons.add(f"shared infrastructure: {value}")
        routed = False
        for inputs, tests in COMPONENT_ROUTES:
            if any(_under(value, prefix) for prefix in inputs):
                routed = True
                for test in tests:
                    add_test(Path(test), f"component input: {value}")
        if value.startswith("tests/"):
            if not (root / path).is_file() or not (
                path.name.startswith("test_")
                and path.suffix == ".py"
                or ".test." in path.name
            ):
                add_test(path.parent, f"test support input: {value}")
            continue
        owned = bool(affected_owners(registry, (path,)))
        if path.suffix in DOC_SUFFIXES and not owned and not routed:
            continue
        if value.startswith(".codex/") or path.name == "AGENTS.md":
            continue
        # Import selection must find tests, not merely another production file.
        connected = (
            any(p.parts[0] == "tests" for p in _consumers(reverse, {path}))
            if not owned and not routed
            else False
        )
        if not owned and not routed and not connected and value not in FULL_INPUTS:
            full_reasons.add(f"unmapped input: {value}")

    full = bool(full_reasons)
    if full:
        selected = {p for p in files if p.parts[0] == "tests"}
        generator_owners = tuple(registry)
    elif critical and (
        not changed or owners or any(p.suffix not in DOC_SUFFIXES for p in changed)
    ):
        for test in CRITICAL_TESTS:
            if not (root / test).is_file():
                raise ValueError(f"missing critical regression suite: {test}")
            add_test(Path(test), "critical regression")
    selected = {p for p in selected if (root / p).is_file()}
    python_tests = tuple(
        sorted(
            p.as_posix()
            for p in selected
            if p.suffix == ".py" and p.name.startswith("test_")
        )
    )
    node = {
        p
        for p in selected
        if ".test." in p.name and p.suffix in {".ts", ".tsx", ".js", ".mjs"}
    }
    vitest = {
        p
        for p in node
        if "from 'vitest'" in (root / p).read_text()
        or 'from "vitest"' in (root / p).read_text()
    }
    documents = tuple(
        sorted(
            p.as_posix()
            for p in changed
            if p.suffix in DOC_SUFFIXES and (root / p).is_file()
        )
    )
    static_python = tuple(
        sorted(
            p.as_posix() for p in changed if p.suffix == ".py" and (root / p).is_file()
        )
    )
    static_node = full or any(
        p.suffix in {".ts", ".tsx", ".js", ".mjs", ".css"} or p.name == "package.json"
        for p in changed
    )
    php = full or any(_under(p.as_posix(), "tests/raos_v2") for p in selected)
    selected_owners = tuple(
        o for o in generator_owners if o not in OWNER_PRIVATE_OWNER_IDS
    )
    has_tests = bool(python_tests or node or php)
    return TestPlan(
        tuple(sorted(p.as_posix() for p in changed)),
        full,
        tuple(sorted(full_reasons)),
        selected_owners,
        python_tests,
        tuple(sorted(p.as_posix() for p in node - vitest)),
        tuple(sorted(p.as_posix() for p in vitest)),
        php,
        static_python,
        static_node,
        documents,
        {
            "static": True,
            "tests": has_tests,
            "php": php,
            "contracts": full or "build_st0104_contract_repository" in selected_owners,
            # DB/storage markers are routed at collection, not guessed from names.
            "data": has_tests,
            "storage": has_tests,
            "secrets": critical or full,
        },
        {
            key: tuple(sorted(value))
            for key, value in sorted(reasons.items())
            if Path(key) in selected
        },
    )

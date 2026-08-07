"""Make-command, wrapper, and evidence-boundary checks for ST-0103."""

from __future__ import annotations

import os
import subprocess

from conftest import EXPECTED_NODE_VERSION, EXPECTED_NPM_VERSION, REPOSITORY_ROOT


MAKEFILE = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
LOGICAL_MAKEFILE = " ".join(MAKEFILE.replace("\\\n\t", " ").split())
WRAPPER_COMMANDS = {
    "lock",
    "lock-check",
    "sync",
    "sync-offline",
    "versions",
    "format-check",
    "lint",
    "typecheck",
    "pyright",
    "test",
    "check",
}


def recipe(target: str) -> list[str]:
    """Extract the physical recipe lines for a simple Make target."""

    lines = MAKEFILE.splitlines()
    header = f"{target}:"
    for index, line in enumerate(lines):
        if line == header or line.startswith(f"{header} "):
            commands: list[str] = []
            for following in lines[index + 1 :]:
                if not following.startswith("\t"):
                    break
                commands.append(following.removeprefix("\t"))
            return commands
    raise AssertionError(f"missing Make target: {target}")


def dependencies(target: str) -> list[str]:
    """Return normal and order-only prerequisites from a simple target."""

    logical_lines = MAKEFILE.replace("\\\n\t", " ").splitlines()
    header = f"{target}:"
    line = next(line for line in logical_lines if line.startswith(header))
    return line.split(":", 1)[1].split()


def joined_recipe(target: str) -> str:
    return " ".join(command.removesuffix("\\").strip() for command in recipe(target))


def test_make_pins_tools_and_uses_an_allowlisted_environment() -> None:
    assert f"NODE_VERSION := {EXPECTED_NODE_VERSION}" in MAKEFILE
    assert f"NPM_VERSION := {EXPECTED_NPM_VERSION}" in MAKEFILE
    assert "POSTCSS_VERSION := 8.5.25" in MAKEFILE
    assert "SHARP_VERSION := 0.35.3" in MAKEFILE
    assert (
        "override RAOS_REPOSITORY_ROOT := "
        "$(abspath $(dir $(lastword $(MAKEFILE_LIST))))"
    ) in MAKEFILE
    clean_environment = (
        LOGICAL_MAKEFILE.split("NODE_CLEAN_ENV :=", 1)[1]
        .split("NODE_RUN :=", 1)[0]
        .strip()
    )
    assert clean_environment.startswith("env -i ")
    assert "NODE_OPTIONS=" not in clean_environment
    assert "NODE_PATH=" not in clean_environment
    assert "MAKEFLAGS=" not in clean_environment
    assert "MAKEFILES=" not in clean_environment
    assert "npm_config_" not in clean_environment
    assert "NPM_CONFIG_OFFLINE=" not in clean_environment
    assert "NPM_CONFIG_PACKAGE_LOCK=" not in clean_environment
    assert "NEXT_TELEMETRY_DISABLED=1" in clean_environment
    assert "COREPACK_ENABLE_NETWORK=0" in clean_environment
    assert "NPM_CONFIG_IGNORE_SCRIPTS=true" in clean_environment
    versions = joined_recipe("node-tool-versions")
    assert "'postcss=$(POSTCSS_VERSION)'" in versions
    assert "'sharp=$(SHARP_VERSION)'" in versions


def test_trusted_wrapper_has_valid_privileged_shell_and_fixed_cli() -> None:
    wrapper = REPOSITORY_ROOT / "scripts/node_toolchain.sh"
    assert wrapper.is_file()
    assert not wrapper.is_symlink()
    assert os.access(wrapper, os.X_OK)
    shell_check = subprocess.run(
        ["bash", "-n", str(wrapper)],
        env={"PATH": os.defpath},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert shell_check.returncode == 0, shell_check.stderr

    content = wrapper.read_text(encoding="utf-8")
    assert content.startswith("#!/bin/bash -p\n\nPATH=/usr/bin:/bin\nexport PATH\n")
    assert "realpath --canonicalize-existing --zero --" in content
    assert "reject_make_unsafe_path()" in content
    for label in (
        "canonical Node executable path",
        "canonical npm CLI path",
        "canonical Node installation prefix",
        "physical repository root",
    ):
        assert f"reject_make_unsafe_path '{label}'" in content
    assert "exec env -i" in content
    allowlisted_exec = content.split("exec env -i", 1)[1]
    assert "BASH_ENV=" not in allowlisted_exec
    assert "NODE_OPTIONS=" not in allowlisted_exec
    assert "MAKEFLAGS=" not in allowlisted_exec
    assert "--node ABSOLUTE_PATH --npm-cli ABSOLUTE_PATH COMMAND" in content
    assert EXPECTED_NODE_VERSION in content
    assert EXPECTED_NPM_VERSION in content
    assert "--no-builtin-rules --no-builtin-variables" in content
    assert 'cd -- "$repository_root"' in content
    assert "--file Makefile" in content
    assert '--file "$repository_root/Makefile"' not in content
    assert "canonicalize_existing 'Node executable'" in content
    assert "canonicalize_existing 'npm CLI'" in content
    assert "node_executable=$canonical_node" in content
    assert "npm_cli=$canonical_npm_cli" in content
    assert "canonicalize_existing 'Node installation prefix'" in content
    assert '"${node_executable%/*}/.." node_prefix' in content
    assert (
        "expected_npm_cli=$node_prefix/lib/node_modules/npm/bin/npm-cli.js" in content
    )
    assert '[[ $npm_cli != "$expected_npm_cli" ]]' in content
    for command in WRAPPER_COMMANDS:
        assert command in content


def test_dependency_tree_gate_uses_the_pinned_npm_after_sync() -> None:
    assert dependencies("node-dependency-tree-check") == ["|", "node-sync"]
    command = joined_recipe("node-dependency-tree-check")
    assert command == "$(NPM_RUN) ls --all >/dev/null"
    assert "npx" not in command
    assert "corepack" not in command


def test_mutable_lock_generation_is_separate_from_freshness_check() -> None:
    lock = joined_recipe("node-lock")
    lock_check = joined_recipe("node-lock-check")
    assert "--package-lock-only" in lock
    assert "$(NPM_RUN)" in lock
    assert "--package-lock-only" not in lock_check
    assert "$(NPM_RUN) ci" in lock_check
    assert "--dry-run" in lock_check
    assert "verify-lock-manifests" in lock_check
    assert lock_check.index("verify-lock-manifests") < lock_check.index("$(NPM_RUN) ci")
    assert "node-lock" not in dependencies("node-sync")
    assert "node-lock" not in dependencies("node-check")


def test_sync_uses_ci_and_never_runs_lifecycle_scripts() -> None:
    sync = joined_recipe("node-sync")
    offline = joined_recipe("node-sync-offline")
    for command in (sync, offline):
        assert "$(NPM_RUN) ci" in command
        assert " install " not in f" {command} "
        assert "npx" not in command
        assert "corepack" not in command
        assert "$(NPM_RUN)" in command
    npm_run = LOGICAL_MAKEFILE.split("NPM_RUN :=", 1)[1].split(".PHONY:", 1)[0]
    assert "--ignore-scripts" in npm_run
    assert "--no-audit" in npm_run
    assert "--no-fund" in npm_run
    assert "--offline" in offline
    assert "node_modules" in offline
    assert "npm-cache" in LOGICAL_MAKEFILE
    assert "mktemp -d" in offline
    assert "inventory" in offline
    assert "cmp --" in offline


def test_node_storage_and_lock_checks_fail_closed() -> None:
    storage = joined_recipe("node-storage-check")
    assert '"$(NPM_CACHE)"' in storage
    assert '"$(NODE_MODULES)"' in storage
    assert "apps/web/node_modules" in storage
    assert "packages/web-contracts/node_modules" in storage
    assert "packages/web-ui/node_modules" in storage
    lock_check = joined_recipe("node-lock-check")
    assert lock_check.count("sha256sum") == 2
    assert "set -eu;" in lock_check
    assert 'test "$$before" = "$$after"' in lock_check
    for relative in (
        "package-lock.json",
        "package.json",
        "apps/web/package.json",
        "packages/web-contracts/package.json",
        "packages/web-ui/package.json",
    ):
        assert f'"$(RAOS_REPOSITORY_ROOT)/{relative}"' in lock_check
    offline = joined_recipe("node-sync-offline")
    assert "set -eu;" in offline


def test_node_inventory_lock_preflight_is_closed_and_network_free() -> None:
    inventory = (REPOSITORY_ROOT / "scripts/node_inventory.mjs").read_text(
        encoding="utf-8"
    )
    assert "case 'verify-lock-manifests':" in inventory
    assert "arguments_.length !== 5" in inventory
    assert "verifyLockManifests(arguments_[0], arguments_.slice(1))" in inventory
    assert "EXPECTED_LOCK_MANIFEST_KEYS" in inventory
    assert "EXPECTED_LOCK_TOP_LEVEL_KEYS" in inventory
    assert "lock.requires !== true" in inventory
    assert "Object.entries(lock.packages)" in inventory
    assert "function isCanonicalNodeModulesLocation(location)" in inventory
    assert "isCanonicalNodeModulesLocation(packageKey)" in inventory
    assert "package-lock.json contains a noncanonical package location" in inventory
    assert "packageKey.startsWith('node_modules/')" not in inventory
    assert "fetch(" not in inventory
    assert "node:http" not in inventory
    assert "node:https" not in inventory
    assert "npm" not in "\n".join(
        line for line in inventory.splitlines() if "verifyLockManifests" in line
    )


def test_verification_targets_use_only_pinned_local_executables() -> None:
    for target in (
        "node-tool-versions",
        "node-format-check",
        "node-lint",
        "node-typecheck",
        "node-pyright",
        "node-test",
    ):
        command = joined_recipe(target)
        assert command
        assert "npx" not in command
        assert "corepack" not in command
        assert "npm install" not in command
        assert "npm ci" not in command
        assert "|| true" not in command
    format_command = joined_recipe("node-format-check")
    lint_command = joined_recipe("node-lint")
    typecheck_command = joined_recipe("node-typecheck")
    pyright_command = joined_recipe("node-pyright")
    test_command = joined_recipe("node-test")
    assert '"$(NODE_MODULES)/prettier/bin/prettier.cjs"' in format_command
    assert "--check" in format_command
    assert '"$(NODE_MODULES)/eslint/bin/eslint.js"' in lint_command
    assert "--max-warnings=0" in lint_command
    assert '"$(NODE_MODULES)/typescript/bin/tsc"' in typecheck_command
    assert "--noEmit" in typecheck_command
    assert '"$(NODE_MODULES)/pyright/index.js"' in pyright_command
    assert "verify-python-runtime" in pyright_command
    assert pyright_command.index("verify-python-runtime") < pyright_command.index(
        '"$(NODE_MODULES)/pyright/index.js"'
    )
    assert '"$(RAOS_REPOSITORY_ROOT)/.venv"' in pyright_command
    assert '"$(RAOS_REPOSITORY_ROOT)/.venv/bin"' in pyright_command
    assert '--pythonpath "$(RAOS_REPOSITORY_ROOT)/.venv/bin/python"' in pyright_command
    assert '"$(PYTHON_VERSION)"' in pyright_command
    assert "--project" in pyright_command
    assert '"$(NODE_MODULES)/vitest/vitest.mjs"' in test_command
    assert " run " in f" {test_command} "
    assert "--configLoader native" in test_command
    assert "--passWithNoTests" not in test_command
    assert dependencies("node-pyright") == ["|", "node-sync"]
    assert "python-sync" not in dependencies("node-pyright")


def test_aggregate_check_contains_every_read_only_gate_after_sync() -> None:
    assert dependencies("node-check") == [
        "node-tool-versions",
        "node-dependency-tree-check",
        "node-format-check",
        "node-lint",
        "node-typecheck",
        "node-pyright",
        "node-test",
    ]


def test_user_docs_define_the_wrapper_and_formal_evidence_boundary() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    agents = (REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    normalized = " ".join(f"{readme}\n{agents}".split())
    assert "scripts/node_toolchain.sh" in normalized
    assert "--node" in normalized
    assert "--npm-cli" in normalized
    assert "npm ci" in normalized
    assert "lifecycle scripts" in normalized
    assert "ST-0103" in normalized
    assert "TST-001" in normalized
    assert "TST-006" in normalized
    assert "not formal" in normalized.lower()
    assert "ST-0106" in normalized


def test_story_plan_and_worklog_preserve_effective_status_boundary() -> None:
    execplan = (REPOSITORY_ROOT / "docs/execplans/ST-0103.md").read_text(
        encoding="utf-8"
    )
    worklog = (REPOSITORY_ROOT / "docs/worklogs/ST-0103.md").read_text(encoding="utf-8")
    normalized_plan = " ".join(execplan.split())
    normalized_log = " ".join(worklog.split())
    assert "local implementation proposal" in normalized_plan
    assert "never becomes formal CI evidence" in normalized_plan
    assert "NOT_EXECUTED" in normalized_plan
    assert "IMPLEMENTED_NOT_VALIDATED" in normalized_log
    assert "NOT_STARTED" in normalized_log
    assert "NOT_EXECUTED" in normalized_log

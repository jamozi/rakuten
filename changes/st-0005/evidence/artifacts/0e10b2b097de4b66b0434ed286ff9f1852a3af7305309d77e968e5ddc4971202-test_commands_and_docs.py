"""Make-command and evidence-boundary checks for ST-0102."""

from __future__ import annotations

import os
import subprocess

from conftest import REPOSITORY_ROOT


MAKEFILE = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
LOGICAL_MAKEFILE = " ".join(MAKEFILE.replace("\\\n\t", " ").split())


def recipe(target: str) -> list[str]:
    """Extract a simple, non-continuation Make target recipe."""

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
    """Return the normal and order-only prerequisites of a simple target."""

    logical_lines = MAKEFILE.replace("\\\n\t", " ").splitlines()
    header = f"{target}:"
    line = next(line for line in logical_lines if line.startswith(header))
    return line.split(":", 1)[1].split()


def test_make_clears_contract_changing_environment_overrides() -> None:
    clean_environment = (
        LOGICAL_MAKEFILE.split("UV_CLEAN_ENV :=", 1)[1].split("UV_RUN :=", 1)[0].strip()
    )
    assert clean_environment.startswith("env ")
    for variable in (
        "UV_CONFIG_FILE",
        "UV_NO_CONFIG",
        "UV_ISOLATED",
        "UV_NO_PROJECT",
        "UV_WORKING_DIR",
        "UV_WORKING_DIRECTORY",
        "UV_PROJECT",
        "UV_WORKSPACE",
        "UV_PROJECT_ENVIRONMENT",
        "UV_REQUIRED_VERSION",
        "UV_ENV_FILE",
        "UV_NO_ENV_FILE",
        "UV_INDEX",
        "UV_DEFAULT_INDEX",
        "UV_INDEX_URL",
        "UV_EXTRA_INDEX",
        "UV_EXTRA_INDEX_URL",
        "UV_FIND_LINKS",
        "UV_INDEX_STRATEGY",
        "UV_KEYRING_PROVIDER",
        "UV_INSECURE_HOST",
        "UV_NO_SOURCES",
        "UV_PRERELEASE",
        "UV_PRERELEASE_PACKAGE",
        "UV_RESOLUTION",
        "UV_FORK_STRATEGY",
        "UV_EXCLUDE_NEWER",
        "UV_EXCLUDE_NEWER_PACKAGE",
        "UV_FROZEN",
        "UV_LOCKED",
        "UV_OVERRIDE",
        "UV_CONSTRAINT",
        "UV_BUILD_CONSTRAINT",
        "UV_UPGRADE",
        "UV_UPGRADE_PACKAGE",
        "UV_UPGRADE_GROUP",
        "UV_NO_BUILD",
        "UV_NO_BUILD_PACKAGE",
        "UV_NO_BUILD_ISOLATION",
        "UV_NO_BUILD_ISOLATION_PACKAGE",
        "UV_NO_BINARY",
        "UV_NO_BINARY_PACKAGE",
        "UV_NO_VERIFY_HASHES",
        "UV_PYTHON",
        "UV_PYTHON_DOWNLOADS",
        "UV_PYTHON_PREFERENCE",
        "UV_MANAGED_PYTHON",
        "UV_NO_MANAGED_PYTHON",
        "UV_SYSTEM_PYTHON",
        "UV_PYTHON_SEARCH_PATH",
        "UV_PYTHON_CPYTHON_BUILD",
        "UV_PYTHON_INSTALL_DIR",
        "UV_PYTHON_INSTALL_MIRROR",
        "UV_PYPY_INSTALL_MIRROR",
        "UV_ASTRAL_MIRROR_URL",
        "UV_PYTHON_DOWNLOADS_JSON_URL",
        "UV_OFFLINE",
        "UV_NO_CACHE",
        "UV_PREVIEW",
        "UV_MALWARE_CHECK",
        "UV_MALWARE_CHECK_URL",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "PYTHONINSPECT",
        "PYTHONOPTIMIZE",
        "PYTHONWARNINGS",
        "PYTEST_ADDOPTS",
        "PYTEST_PLUGINS",
        "MYPYPATH",
        "UV_NO_DEV",
        "UV_NO_DEFAULT_GROUPS",
    ):
        assert f"-u {variable}" in clean_environment
    assert (
        "override RAOS_REPOSITORY_ROOT := "
        "$(abspath $(dir $(lastword $(MAKEFILE_LIST))))"
    ) in MAKEFILE
    assert "override UV_CONFIG := $(RAOS_REPOSITORY_ROOT)/uv.toml" in MAKEFILE
    assert (
        'override UV_RUN := $(UV_CLEAN_ENV) "$(UV)" --config-file "$(UV_CONFIG)"'
    ) in MAKEFILE
    assert "override UV_OFFLINE_RUN := $(UV_CLEAN_ENV)" in MAKEFILE
    assert 'UV_PROJECT_ENVIRONMENT="$(PYTHON_OFFLINE_ENVIRONMENT)"' in MAKEFILE
    for target in (
        "python-install",
        "python-lock",
        "python-lock-check-offline",
        "python-tool-versions",
        "python-lint",
        "python-format-check",
        "python-typecheck",
        "python-test",
    ):
        assert all(command.startswith("$(UV_RUN) ") for command in recipe(target))
    for target in ("python-lock-check", "python-sync"):
        assert "$(UV_RUN)" in " ".join(recipe(target))


def test_mutable_python_operations_are_explicit_targets() -> None:
    assert recipe("python-install") == ["$(UV_RUN) python install $(PYTHON_VERSION)"]
    assert recipe("python-lock") == ["$(UV_RUN) lock"]
    assert "python-lock" not in dependencies("python-sync")


def test_makefile_fails_closed_on_non_verifying_interpreter_modes() -> None:
    assert "ifeq ($(origin MAKEFLAGS),command line)" in MAKEFILE
    assert "ifneq ($(strip $(MAKEFILES)),)" in MAKEFILE
    assert "$(error Direct MAKEFLAGS assignments" in MAKEFILE
    assert "$(error Preloaded MAKEFILES" in MAKEFILE
    assert "$(error Refusing non-verifying GNU Make mode(s)" in MAKEFILE
    for variable in ("UV_CLEAN_ENV", "UV_RUN", "UV_OFFLINE_RUN"):
        assert f"override {variable} :=" in MAKEFILE


def test_trusted_wrapper_cleans_preparse_make_inputs_and_has_valid_shell() -> None:
    wrapper = REPOSITORY_ROOT / "scripts/python_toolchain.sh"
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
    assert content.startswith("#!/bin/bash -p\n")
    assert "unset BASH_ENV ENV" in content
    assert "unset MAKEFLAGS GNUMAKEFLAGS MAKEFILES MFLAGS MAKEOVERRIDES" in content
    assert "--no-builtin-rules --no-builtin-variables" in content
    assert "'uv 0.12.1'|'uv 0.12.1 '*" in content
    assert "--uv ABSOLUTE_PATH COMMAND" in content


def test_sync_rejects_stale_lock_and_implicit_python_downloads() -> None:
    assert dependencies("python-sync") == ["python-lock-check"]
    assert dependencies("python-sync-offline") == ["python-lock-check-offline"]
    lock_check = " ".join(
        command.removesuffix("\\").strip() for command in recipe("python-lock-check")
    )
    assert 'test "$(RAOS_CI_OFFLINE)" = 1' in lock_check
    assert "$(UV_RUN) lock --check --offline" in lock_check
    assert "$(UV_RUN) lock --check" in lock_check
    assert recipe("python-lock-check-offline") == ["$(UV_RUN) lock --check --offline"]
    sync = " ".join(
        command.removesuffix("\\").strip() for command in recipe("python-sync")
    )
    assert 'test "$(RAOS_CI_OFFLINE)" = 1' in sync
    assert 'test "$(RAOS_NETWORK_DENIED)" = 1' in sync
    assert 'test -x "$(RAOS_REPOSITORY_ROOT)/.venv/bin/python"' in sync
    assert (
        "$(UV_RUN) sync --locked --group dev --managed-python "
        "--no-python-downloads --no-build --no-sources"
    ) in sync
    offline_recipe = " ".join(
        command.removesuffix("\\").strip() for command in recipe("python-sync-offline")
    )
    assert 'test ! -L "$(PYTHON_OFFLINE_ENVIRONMENT)"' in offline_recipe
    assert (
        "$(UV_RUN) venv --clear --offline --managed-python --no-python-downloads "
        '"$(PYTHON_OFFLINE_ENVIRONMENT)"'
    ) in offline_recipe
    assert (
        "$(UV_OFFLINE_RUN) sync --locked --offline --group dev --managed-python "
        "--no-python-downloads"
    ) in offline_recipe
    assert "--frozen" not in MAKEFILE


def test_check_commands_cannot_sync_or_rewrite_the_lock() -> None:
    checked_targets = (
        "python-tool-versions",
        "python-lint",
        "python-format-check",
        "python-typecheck",
        "python-test",
    )
    for target in checked_targets:
        assert dependencies(target) == ["|", "python-sync"]
        commands = recipe(target)
        assert commands
        if target == "python-tool-versions":
            assert commands[0] == (
                "$(UV_RUN) --version | grep -E '^uv $(UV_VERSION)( |$$)'"
            )
            commands = commands[1:]
        for command in commands:
            assert " run --locked --no-sync " in command
            assert " --no-env-file " in command
            assert " lock" not in command
            assert " sync" not in command


def test_pytest_and_format_commands_are_story_isolated_and_scoped() -> None:
    assert recipe("python-test") == [
        "$(UV_RUN) run --locked --no-sync --no-env-file pytest -q tests/st0102"
    ]
    assert recipe("python-format-check") == [
        "$(UV_RUN) run --locked --no-sync --no-env-file ruff format --check "
        "--exclude python/raos/generated python tests/st0102 "
        "scripts/build_st0105_generated_contracts.py tests/st0105 "
        "scripts/assert_network_denied.py scripts/scan_secrets.py tests/st0106 "
        "migrations tests/st0301 scripts/build_st0301_migration_framework.py"
    ]
    assert recipe("python-lint") == [
        "$(UV_RUN) run --locked --no-sync --no-env-file ruff check "
        "scripts tests python migrations"
    ]


def test_aggregate_check_contains_every_read_only_gate_after_sync() -> None:
    assert dependencies("python-check") == [
        "python-tool-versions",
        "python-lint",
        "python-format-check",
        "python-typecheck",
        "python-test",
    ]


def test_user_docs_keep_local_results_below_formal_ci_evidence() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    normalized = " ".join(readme.split())
    assert (
        "Those local results are not formal TST-001/TST-005 CI evidence." in normalized
    )
    assert "Base pull-request CI is implemented by ST-0106." in normalized
    assert "Do not use `--frozen` as a substitute for `uv lock --check`" in normalized
    assert "as uv's sole configuration file" in normalized


def test_story_plan_and_worklog_preserve_effective_status_boundary() -> None:
    execplan = (REPOSITORY_ROOT / "docs/execplans/ST-0102.md").read_text(
        encoding="utf-8"
    )
    worklog = (REPOSITORY_ROOT / "docs/worklogs/ST-0102.md").read_text(encoding="utf-8")
    normalized_plan = " ".join(execplan.split())
    assert (
        "Local checks can support an `IMPLEMENTED_NOT_VALIDATED` proposal only."
        in normalized_plan
    )
    assert (
        "Effective canonical status and formal suite status remain" in normalized_plan
    )
    assert "`NOT_STARTED` / `NOT_EXECUTED`" in normalized_plan
    assert "- Proposed implementation status: `IMPLEMENTED_NOT_VALIDATED`" in worklog
    assert "- Effective canonical implementation status: `NOT_STARTED`" in worklog
    assert "- Verification status: `NOT_EXECUTED`" in worklog

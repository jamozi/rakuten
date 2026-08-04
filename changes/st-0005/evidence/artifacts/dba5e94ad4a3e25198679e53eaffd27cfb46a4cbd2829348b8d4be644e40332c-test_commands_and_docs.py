"""Trusted command and documentation boundary checks for ST-0105."""

from __future__ import annotations

import os
import subprocess

from conftest import REPOSITORY_ROOT


MAKEFILE = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")


def recipe(target: str) -> str:
    lines = MAKEFILE.splitlines()
    header = f"{target}:"
    for index, line in enumerate(lines):
        if line == header or line.startswith(f"{header} "):
            commands: list[str] = []
            for following in lines[index + 1 :]:
                if not following.startswith("\t"):
                    break
                commands.append(following.removeprefix("\t").removesuffix("\\"))
            return " ".join(command.strip() for command in commands)
    raise AssertionError(f"missing Make target: {target}")


def test_make_exposes_mutating_and_read_only_codegen_targets_separately() -> None:
    hydrate = recipe("contract-codegen-hydrate")
    storage_check = recipe("contract-codegen-storage-check")
    environment_check = recipe("contract-codegen-environment-check")
    install = recipe("contract-codegen-install")
    check = recipe("contract-codegen-check")
    test = recipe("contract-codegen-test")
    typecheck = recipe("contract-codegen-typecheck")
    assert "build_st0105_generated_contracts.py" in install
    assert "--check" not in install
    assert "--check" in check
    assert "pytest -p no:cacheprovider -q tests/st0105" in test
    assert "typescript/bin/tsc" in typecheck
    assert "--noEmit" in typecheck
    assert "--verify-tools-only" in environment_check
    assert (
        "python-sync node-sync"
        in MAKEFILE.split("contract-codegen-hydrate:", 1)[1].splitlines()[0]
    )
    for target in ("install", "check", "test", "typecheck"):
        header = next(
            line
            for line in MAKEFILE.splitlines()
            if line.startswith(f"contract-codegen-{target}:")
        )
        assert "python-sync" not in header
        assert "node-sync" not in header
        if target == "install":
            assert "contract-codegen-storage-check" in header
            assert "contract-codegen-environment-check" not in header
        else:
            assert "contract-codegen-environment-check" in header
    assert hydrate == ""
    assert "node-storage-check" in next(
        line
        for line in MAKEFILE.splitlines()
        if line.startswith("contract-codegen-storage-check:")
    )
    assert ".venv/bin/datamodel-codegen" in storage_check
    for command in (
        install,
        check,
        test,
        typecheck,
        storage_check,
        environment_check,
    ):
        assert "npx" not in command
        assert "|| true" not in command
        assert "npm ci" not in command
    assert "UV_READONLY_RUN :=" in MAKEFILE
    assert "--locked --offline --no-cache" in MAKEFILE
    assert "--no-sync --no-env-file --no-python-downloads" in MAKEFILE


def test_composite_gate_includes_predecessor_drift_tests_and_ts_compile() -> None:
    logical = MAKEFILE.replace("\\\n\t", " ")
    header = next(
        line
        for line in logical.splitlines()
        if line.startswith("contract-codegen-gate:")
    )
    assert header.split(":", 1)[1].split() == [
        "contract-gate",
        "contract-codegen-check",
        "contract-codegen-test",
        "contract-codegen-typecheck",
    ]


def test_codegen_wrapper_is_executable_syntax_valid_and_fail_closed() -> None:
    wrapper = REPOSITORY_ROOT / "scripts/codegen_toolchain.sh"
    assert wrapper.is_file() and not wrapper.is_symlink()
    assert os.access(wrapper, os.X_OK)
    syntax = subprocess.run(
        ["bash", "-n", str(wrapper)],
        env={"PATH": os.defpath},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert syntax.returncode == 0, syntax.stderr
    content = wrapper.read_text(encoding="utf-8")
    assert content.startswith("#!/bin/bash -p\n\nPATH=/usr/bin:/bin\nexport PATH\n")
    assert "exec env -i" in content
    assert "--uv ABSOLUTE_PATH --node ABSOLUTE_PATH" in content
    assert "--npm-cli ABSOLUTE_PATH COMMAND" in content
    assert "required uv version ==0.12.1" in content
    assert "required Node version ==24.18.1" in content
    assert "required npm version ==11.16.0" in content
    assert "npm CLI is not bundled with the selected Node" in content
    assert "canonicalize_existing 'user home'" in content
    assert 'HOME="$canonical_user_home"' in content
    assert "MAKEFLAGS=" not in content.split("exec env -i", 1)[1]
    for command in ("hydrate", "install", "check", "test", "typecheck", "gate"):
        assert f"{command}) target=contract-codegen-" in content


def test_story_docs_define_generated_ownership_and_formal_evidence_boundary() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    agents = (REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    package_readme = (REPOSITORY_ROOT / "packages/web-contracts/README.md").read_text(
        encoding="utf-8"
    )
    execplan = (REPOSITORY_ROOT / "docs/execplans/ST-0105.md").read_text(
        encoding="utf-8"
    )
    worklog = (REPOSITORY_ROOT / "docs/worklogs/ST-0105.md").read_text(encoding="utf-8")
    normalized = " ".join(
        f"{readme}\n{agents}\n{package_readme}\n{execplan}\n{worklog}".split()
    )
    assert "scripts/codegen_toolchain.sh" in normalized
    assert "contract-codegen-gate" in normalized
    assert "ST-0105" in normalized
    assert "TST-004" in normalized
    assert "generated files" in normalized.lower()
    assert "do not edit" in normalized.lower()
    assert "IMPLEMENTED_NOT_VALIDATED" in normalized
    assert "NOT_STARTED" in normalized
    assert "NOT_EXECUTED" in normalized
    assert "ST-0106" in normalized
    assert "hydrate" in normalized
    assert "offline" in normalized.lower()
    assert "no-sync" in normalized.lower()
    assert ".install-transaction.v1" in normalized
    assert "O_NOFOLLOW" in normalized
    assert "ST-0105 activates and owns" in package_readme
    assert "src/generated files by hand" in package_readme
    assert "deferred" not in package_readme
    assert "inert boundary" not in package_readme

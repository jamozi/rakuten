"""Node workflow checks for the unified repository command surface."""

from __future__ import annotations

from .support import EXPECTED_NODE_VERSION, EXPECTED_NPM_VERSION, REPOSITORY_ROOT


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


def test_node_versions_are_lock_metadata_not_normal_loop_flags() -> None:
    package = (REPOSITORY_ROOT / "package.json").read_text(encoding="utf-8")
    assert f'"node": "{EXPECTED_NODE_VERSION}"' in package
    assert f'"npm": "{EXPECTED_NPM_VERSION}"' in package
    for target in ("generate", "check", "fast"):
        command = recipe(target)
        assert EXPECTED_NODE_VERSION not in command
        assert EXPECTED_NPM_VERSION not in command
        assert "--npm-cli" not in command
        assert "--node" not in command


def test_setup_is_the_only_dependency_sync_command() -> None:
    assert "$(NPM) ci --cache .npm-cache" in recipe("setup")
    for obsolete in (
        "node-lock",
        "node-sync",
        "node-sync-offline",
        "node-tool-versions",
        "node-check",
    ):
        assert f"{obsolete}:" not in MAKEFILE


def test_static_node_checks_are_grouped_once() -> None:
    static = recipe("final-static")
    for command in (
        "$(NPM) run format:check",
        "$(NPM) run lint",
        "$(NPM) run typecheck",
    ):
        assert command in static


def test_lock_and_dependency_tree_checks_run_at_final_boundary() -> None:
    final_lock = recipe("final-lock")
    assert "verify_dev_toolchain.py" in final_lock
    assert "$(UV) lock --check" in final_lock
    assert "$(NPM) ls --all" in final_lock

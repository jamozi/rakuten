"""Repository-level Python workflow checks for the unified developer interface."""

from __future__ import annotations

from .support import REPOSITORY_ROOT


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


def test_unified_developer_commands_are_the_supported_surface() -> None:
    for target in ("setup", "generate", "check", "fast", "final"):
        assert recipe(target)

    for obsolete in (
        "python-install",
        "python-sync",
        "python-sync-offline",
        "python-test",
        "python-check",
        "ai-registry-generate",
    ):
        assert f"{obsolete}:" not in MAKEFILE


def test_setup_uses_locks_and_reusable_caches() -> None:
    setup = recipe("setup")
    assert "$(UV) sync --locked" in setup
    assert "$(NPM) ci" in setup
    assert "--cache .npm-cache" in setup
    assert "verify_dev_toolchain.py" in setup
    assert "--no-cache" not in setup
    assert "--offline" not in setup


def test_normal_loop_does_not_reinstall_or_reverify_exact_tools() -> None:
    for target in ("generate", "check", "fast"):
        command = recipe(target)
        assert " sync " not in f" {command} "
        assert " npm ci " not in f" {command} "
        assert "verify_dev_toolchain.py" not in command
        assert "/home/" not in command


def test_generation_and_fast_paths_use_the_shared_owner_graph() -> None:
    assert "scripts/raos_build.py $(BASE_ARGUMENT) generate" in recipe("generate")
    assert "scripts/raos_build.py $(BASE_ARGUMENT) check" in recipe("check")
    assert "scripts/raos_build.py $(BASE_ARGUMENT) fast" in recipe("fast")
    assert "status_v2.py" in recipe("generate")


def test_final_keeps_lock_validation_and_the_shared_full_runner() -> None:
    assert "scripts/raos_build.py final" in recipe("final")
    header = next(line for line in MAKEFILE.splitlines() if line.startswith("final:"))
    assert "final-lock" in header

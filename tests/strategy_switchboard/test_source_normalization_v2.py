from __future__ import annotations

from pathlib import Path
import shutil

from scripts import finalize_strategy_switchboard_sources_v2 as normalizer


def _copy_sources(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    for relative in (
        Path("python/raos/strategy_switchboard/model.py"),
        Path("python/raos/strategy_switchboard/runtime.py"),
        Path("python/raos/strategy_switchboard/config.py"),
        Path("python/raos/strategy_switchboard/switchboard.py"),
        Path("python/raos/strategy_switchboard/__init__.py"),
        Path("python/raos/strategy_switchboard/cli.py"),
        Path("scripts/select_all_story_strategy.py"),
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(normalizer.REPOSITORY_ROOT / relative, target)
    return root


def test_repository_cli_wrapper_is_normalized() -> None:
    normalizer.check(normalizer.REPOSITORY_ROOT)


def test_v2_apply_is_idempotent(tmp_path: Path) -> None:
    root = _copy_sources(tmp_path)

    assert normalizer.apply(root) == ()
    normalizer.check(root)
    assert normalizer.apply(root) == ()


def test_v2_apply_replaces_drifted_cli_entry_point(tmp_path: Path) -> None:
    root = _copy_sources(tmp_path)
    cli = root / normalizer.CLI_PATH
    cli.write_text("raise RuntimeError('drift')\n", encoding="utf-8")

    changed = normalizer.apply(root)
    normalizer.check(root)

    assert normalizer.CLI_PATH.as_posix() in changed
    assert cli.read_text(encoding="utf-8") == normalizer.CLI_CONTENT

from __future__ import annotations

from pathlib import Path
import shutil

from scripts import finalize_strategy_switchboard_sources_v3 as normalizer


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


def test_repository_path_checks_are_normalized() -> None:
    normalizer.check(normalizer.REPOSITORY_ROOT)


def test_v3_apply_is_idempotent(tmp_path: Path) -> None:
    root = _copy_sources(tmp_path)

    assert normalizer.apply(root) == ()
    normalizer.check(root)
    assert normalizer.apply(root) == ()


def test_v3_repairs_exact_path_predecessor_shapes(tmp_path: Path) -> None:
    root = _copy_sources(tmp_path)
    cli = root / "python/raos/strategy_switchboard/cli.py"
    content = cli.read_text(encoding="utf-8")
    for old, new in normalizer._REPLACEMENTS:
        assert content.count(new) == 1
        content = content.replace(new, old)
    cli.write_text(content, encoding="utf-8")

    changed = normalizer.apply(root)
    normalizer.check(root)

    assert "python/raos/strategy_switchboard/cli.py" in changed
    assert normalizer.apply(root) == ()

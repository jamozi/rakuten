from __future__ import annotations

from pathlib import Path
import shutil

from scripts import finalize_strategy_switchboard_sources as normalizer


def _copy_owned_sources(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    for relative in (
        Path("python/raos/strategy_switchboard/model.py"),
        Path("python/raos/strategy_switchboard/runtime.py"),
        Path("python/raos/strategy_switchboard/config.py"),
        Path("python/raos/strategy_switchboard/switchboard.py"),
        Path("python/raos/strategy_switchboard/__init__.py"),
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(normalizer.REPOSITORY_ROOT / relative, target)
    return root


def test_repository_sources_are_normalized() -> None:
    normalizer.check(normalizer.REPOSITORY_ROOT)


def test_apply_is_idempotent(tmp_path: Path) -> None:
    root = _copy_owned_sources(tmp_path)

    first = normalizer.apply(root)
    normalizer.check(root)
    second = normalizer.apply(root)
    normalizer.check(root)

    assert first == ()
    assert second == ()


def test_apply_repairs_all_predecessor_shapes(tmp_path: Path) -> None:
    root = _copy_owned_sources(tmp_path)
    replacements = {
        Path("python/raos/strategy_switchboard/model.py"): (
            'r"^[A-Za-z0-9][A-Za-z0-9._:/_-]{0,191}$"',
            'r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$"',
        ),
        Path("python/raos/strategy_switchboard/runtime.py"): (
            "from typing import Protocol, cast, runtime_checkable",
            "from typing import Protocol, runtime_checkable",
        ),
        Path("python/raos/strategy_switchboard/config.py"): (
            "return cast(dict[str, object], value)",
            "return value",
        ),
        Path("python/raos/strategy_switchboard/switchboard.py"): (
            "requested_id = (\n"
            "            override_strategy_id\n"
            "            if override_strategy_id is not None\n"
            "            else profile_override\n"
            "        )",
            "requested_id = override_strategy_id or profile_override",
        ),
    }
    for relative, (current, predecessor) in replacements.items():
        path = root / relative
        content = path.read_text(encoding="utf-8")
        assert content.count(current) == 1
        path.write_text(content.replace(current, predecessor), encoding="utf-8")

    package = root / "python/raos/strategy_switchboard/__init__.py"
    content = package.read_text(encoding="utf-8")
    content = content.replace(
        "from raos.strategy_switchboard.config import (\n"
        "    load_gate_context_json,\n"
        "    load_profile_json,\n"
        ")\n",
        "",
    )
    content = content.replace(
        '    "load_gate_context_json",\n    "load_profile_json",\n',
        "",
    )
    package.write_text(content, encoding="utf-8")

    changed = normalizer.apply(root)
    normalizer.check(root)

    assert changed
    assert normalizer.apply(root) == ()

#!/usr/bin/env python3
"""Apply exact, idempotent source corrections before switchboard validation."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _replace(path: Path, old: str, new: str) -> bool:
    content = path.read_text(encoding="utf-8")
    if new in content:
        return False
    if content.count(old) != 1:
        raise RuntimeError(f"expected exact source shape not found in {path}")
    path.write_text(content.replace(old, new), encoding="utf-8")
    return True


def apply(root: Path) -> tuple[str, ...]:
    root = root.resolve()
    changed: list[str] = []

    model = root / "python/raos/strategy_switchboard/model.py"
    if _replace(
        model,
        'r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$"',
        'r"^[A-Za-z0-9][A-Za-z0-9._:/_-]{0,191}$"',
    ):
        changed.append(model.relative_to(root).as_posix())

    runtime = root / "python/raos/strategy_switchboard/runtime.py"
    if _replace(
        runtime,
        "from typing import Protocol, runtime_checkable",
        "from typing import Protocol, cast, runtime_checkable",
    ):
        changed.append(runtime.relative_to(root).as_posix())
    if _replace(
        runtime,
        """        return value

    def to_record(self) -> dict[str, object]:
""",
        """        return cast(dict[str, object], value)

    def to_record(self) -> dict[str, object]:
""",
    ):
        changed.append(runtime.relative_to(root).as_posix())
    if _replace(
        runtime,
        """        return parsed, encoded
""",
        """        return cast(dict[str, object], parsed), encoded
""",
    ):
        changed.append(runtime.relative_to(root).as_posix())

    config = root / "python/raos/strategy_switchboard/config.py"
    if _replace(
        config,
        """    return value


def _exact_fields(
""",
        """    return cast(dict[str, object], value)


def _exact_fields(
""",
    ):
        changed.append(config.relative_to(root).as_posix())
    if _replace(
        config,
        """    return frozenset(value)


def load_profile_json(
""",
        """    return frozenset(cast(list[str], value))


def load_profile_json(
""",
    ):
        changed.append(config.relative_to(root).as_posix())

    switchboard = root / "python/raos/strategy_switchboard/switchboard.py"
    if _replace(
        switchboard,
        "requested_id = override_strategy_id or profile_override",
        "requested_id = (\n"
        "            override_strategy_id\n"
        "            if override_strategy_id is not None\n"
        "            else profile_override\n"
        "        )",
    ):
        changed.append(switchboard.relative_to(root).as_posix())

    package = root / "python/raos/strategy_switchboard/__init__.py"
    if _replace(
        package,
        "from raos.strategy_switchboard.catalog import (",
        "from raos.strategy_switchboard.config import (\n"
        "    load_gate_context_json,\n"
        "    load_profile_json,\n"
        ")\n"
        "from raos.strategy_switchboard.catalog import (",
    ):
        changed.append(package.relative_to(root).as_posix())
    if _replace(
        package,
        '    "build_complete_catalog",\n',
        '    "build_complete_catalog",\n'
        '    "load_gate_context_json",\n'
        '    "load_profile_json",\n',
    ):
        changed.append(package.relative_to(root).as_posix())

    return tuple(sorted(set(changed)))


def check(root: Path) -> None:
    root = root.resolve()
    model = (root / "python/raos/strategy_switchboard/model.py").read_text(
        encoding="utf-8"
    )
    if 'r"^[A-Za-z0-9][A-Za-z0-9._:/_-]{0,191}$"' not in model:
        raise RuntimeError("stable error identifiers do not admit underscores")

    runtime = (root / "python/raos/strategy_switchboard/runtime.py").read_text(
        encoding="utf-8"
    )
    if "from typing import Protocol, cast, runtime_checkable" not in runtime:
        raise RuntimeError("runtime cast import is missing")
    if runtime.count("return cast(dict[str, object],") != 2:
        raise RuntimeError("runtime exact JSON casts are incomplete")

    config = (root / "python/raos/strategy_switchboard/config.py").read_text(
        encoding="utf-8"
    )
    if "return cast(dict[str, object], value)" not in config:
        raise RuntimeError("configuration object cast is missing")
    if "return frozenset(cast(list[str], value))" not in config:
        raise RuntimeError("configuration list cast is missing")

    switchboard = (
        root / "python/raos/strategy_switchboard/switchboard.py"
    ).read_text(encoding="utf-8")
    if "if override_strategy_id is not None" not in switchboard:
        raise RuntimeError("explicit empty override is not distinguished from absence")

    package = (root / "python/raos/strategy_switchboard/__init__.py").read_text(
        encoding="utf-8"
    )
    for name in ("load_gate_context_json", "load_profile_json"):
        if package.count(name) != 2:
            raise RuntimeError(f"public configuration export is incomplete: {name}")


def parse_args(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--apply", action="store_true")
    operation.add_argument("--check", action="store_true")
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    options = parse_args(sys.argv[1:] if arguments is None else arguments)
    try:
        changed = apply(options.root) if options.apply else ()
        check(options.root)
    except (OSError, RuntimeError, UnicodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        "switchboard source normalization: PASS"
        + (f" changed={','.join(changed)}" if changed else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

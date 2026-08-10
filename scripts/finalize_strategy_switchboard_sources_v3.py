#!/usr/bin/env python3
"""Normalize switchboard sources, CLI entry point, and concrete Path checks."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import finalize_strategy_switchboard_sources_v2 as base  # noqa: E402


_REPLACEMENTS = (
    ("type(namespace.root) is not Path", "not isinstance(namespace.root, Path)"),
    ("type(namespace.profile) is not Path", "not isinstance(namespace.profile, Path)"),
    ("type(namespace.context) is not Path", "not isinstance(namespace.context, Path)"),
    (
        "namespace.payload is not None\n            and type(namespace.payload) is not Path",
        "namespace.payload is not None\n            and not isinstance(namespace.payload, Path)",
    ),
)


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
    changed = list(base.apply(root))
    cli = root / "python/raos/strategy_switchboard/cli.py"
    for old, new in _REPLACEMENTS:
        if _replace(cli, old, new):
            changed.append(cli.relative_to(root).as_posix())
    return tuple(sorted(set(changed)))


def check(root: Path) -> None:
    root = root.resolve()
    base.check(root)
    cli = (root / "python/raos/strategy_switchboard/cli.py").read_text(
        encoding="utf-8"
    )
    for old, new in _REPLACEMENTS:
        if old in cli or new not in cli:
            raise RuntimeError(f"CLI Path normalization is incomplete: {old}")


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
        "switchboard source normalization v3: PASS"
        + (f" changed={','.join(changed)}" if changed else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

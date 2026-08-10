#!/usr/bin/env python3
"""Normalize the switchboard package and its repository CLI entry point."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import finalize_strategy_switchboard_sources as base  # noqa: E402


CLI_PATH = Path("scripts/select_all_story_strategy.py")
CLI_CONTENT = """#!/usr/bin/env python3
\"\"\"Repository entry point for explicit RAOS strategy selection.\"\"\"

from __future__ import annotations

from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPOSITORY_ROOT / \"python\"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.strategy_switchboard.cli import main  # noqa: E402


__all__ = [\"REPOSITORY_ROOT\", \"main\"]


if __name__ == \"__main__\":
    raise SystemExit(main())
"""


def apply(root: Path) -> tuple[str, ...]:
    root = root.resolve()
    changed = list(base.apply(root))
    cli = root / CLI_PATH
    existing = cli.read_text(encoding="utf-8") if cli.exists() else ""
    if existing != CLI_CONTENT:
        cli.parent.mkdir(parents=True, exist_ok=True)
        cli.write_text(CLI_CONTENT, encoding="utf-8")
        changed.append(CLI_PATH.as_posix())
    return tuple(sorted(set(changed)))


def check(root: Path) -> None:
    root = root.resolve()
    base.check(root)
    cli = root / CLI_PATH
    if not cli.is_file() or cli.is_symlink():
        raise RuntimeError("strategy CLI entry point is unavailable")
    if cli.read_text(encoding="utf-8") != CLI_CONTENT:
        raise RuntimeError("strategy CLI entry point differs from the exact wrapper")
    application = root / "python/raos/strategy_switchboard/cli.py"
    if not application.is_file() or application.is_symlink():
        raise RuntimeError("strategy CLI application module is unavailable")


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
        "switchboard source normalization v2: PASS"
        + (f" changed={','.join(changed)}" if changed else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

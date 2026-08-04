#!/usr/bin/env python3
"""Private subprocess driver for ST-0105 crash-recovery tests."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.dont_write_bytecode = True

from scripts import build_st0105_generated_contracts as generator  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--checkpoint")
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    root = arguments.root.resolve(strict=True)
    generator.REPO_ROOT = root
    generator.MANIFEST_PATH = root / "changes/st-0105/manifest.json"
    generator.PYTHON_OUTPUT_ROOT = root / "python/raos/generated"
    generator.TYPESCRIPT_OUTPUT_ROOT = root / "packages/web-contracts/src/generated"

    def crash(checkpoint: str) -> None:
        if checkpoint == arguments.checkpoint:
            os._exit(97)

    if arguments.checkpoint is not None:
        generator._checkpoint = crash
    generator._install(
        root / "rendered/python",
        root / "rendered/typescript",
        (root / "next-manifest.json").read_bytes(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generate/check the fixed ST-1703 Wave 3 runtime identity manifest."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "scripts/wordpresscom_review_draft.py"
OUTPUT_PATH = (
    ROOT
    / "changes/st-1703/wordpresscom-mvp-draft-preparation.wave3.runtime-manifest.v1.json"
)


def _load_cli() -> ModuleType:
    specification = importlib.util.spec_from_file_location(
        "st1703_wordpresscom_mvp_manifest_source", CLI_PATH
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("runtime manifest source unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _render() -> bytes:
    module = _load_cli()
    paths = module._MVP_RUNTIME_PATHS
    if type(paths) is not tuple or any(type(path) is not str for path in paths):
        raise RuntimeError("runtime path inventory invalid")
    entries: list[dict[str, object]] = []
    for relative in paths:
        path = ROOT / relative
        value = path.read_bytes()
        entries.append(
            {
                "bytes": len(value),
                "path": relative,
                "sha256": hashlib.sha256(value).hexdigest(),
            }
        )
    manifest = {
        "approved_base_commit": module._MVP_APPROVED_BASE_COMMIT,
        "generated_by": "python3 scripts/build_wordpresscom_mvp_runtime_manifest.py",
        "paths": entries,
        "schema": "WORDPRESSCOM_MVP_DRAFT_RUNTIME_MANIFEST_V1",
        "slice_id": "WORDPRESSCOM_MVP_DRAFT_PREPARATION_WAVE_3",
        "story_id": "ST-1703",
    }
    return (
        json.dumps(
            manifest,
            ensure_ascii=True,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("ascii", errors="strict")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    rendered = _render()
    if arguments.check:
        try:
            current = OUTPUT_PATH.read_bytes()
        except OSError:
            return 1
        return 0 if current == rendered else 1
    OUTPUT_PATH.write_bytes(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())

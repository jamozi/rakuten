#!/usr/bin/env python3
"""Build/check the separate ST-1704 bounded Rakuten capture manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Final


ROOT: Final = Path(__file__).resolve().parents[1]
SLICE: Final = Path("changes/st-1704/self-hosted-editorial-pilot-v1")
MANIFEST: Final = SLICE / "rakuten-capture-runtime-manifest.v1.json"
ARTICLE_IDS: Final = (
    "st1703-first-suitcase-comparison",
    "st1704-portable-power-station-guide",
    "st1704-anker-solix-c300-c800-c1000-differences",
    "st1704-countertop-dishwasher-for-small-households",
    "st1704-compact-robot-vacuum-shortlist",
)
REQUIRED_RUNTIME_PATHS: Final = tuple(
    sorted(
        (
            f"{SLICE}/DESIGN_HANDOFF_V1.yaml",
            f"{SLICE}/Makefile",
            f"{SLICE}/OPERATIONS_RUNBOOK.md",
            f"{SLICE}/PREFLIGHT.md",
            f"{SLICE}/RAKUTEN_CAPTURE_WORKLOG.md",
            f"{SLICE}/README.md",
            f"{SLICE}/content/articles.v1.json",
            f"{SLICE}/media/product-media-registry.v1.json",
            f"{SLICE}/sources/source-registry.v1.json",
            "python/raos/adapters/self_hosted_editorial_rakuten_capture.py",
            "python/raos/domain/editorial/self_hosted_editorial_pilot.py",
            "scripts/build_st1704_rakuten_capture_manifest.py",
            "scripts/st1704_rakuten_product_capture.py",
        )
    )
)


def _path_record(relative: str) -> dict[str, object]:
    payload = (ROOT / relative).read_bytes()
    if not payload:
        raise RuntimeError(f"empty runtime path: {relative}")
    return {
        "bytes": len(payload),
        "path": relative,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def build_manifest() -> bytes:
    document = {
        "article_ids": list(ARTICLE_IDS),
        "external_action_authority": "HUMAN_OWNER_BOUNDED_RAKUTEN_READ",
        "generated_by": "scripts/build_st1704_rakuten_capture_manifest.py",
        "paths": [_path_record(relative) for relative in REQUIRED_RUNTIME_PATHS],
        "publication_authority": "NONE",
        "schema": "ST1704_BOUNDED_RAKUTEN_CAPTURE_MANIFEST_V1",
        "slice_id": "SELF_HOSTED_EDITORIAL_PILOT_V1",
        "story_id": "ST-1704",
    }
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    expected = build_manifest()
    target = ROOT / MANIFEST
    if arguments.check:
        if not target.is_file() or target.read_bytes() != expected:
            print("ST1704_RAKUTEN_CAPTURE_MANIFEST_DRIFT")
            return 1
        print("ST1704_RAKUTEN_CAPTURE_MANIFEST_VALID")
        return 0
    target.write_bytes(expected)
    print("ST1704_RAKUTEN_CAPTURE_MANIFEST_GENERATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

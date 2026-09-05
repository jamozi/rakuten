#!/usr/bin/env python3
"""Regenerate authority-free manufacturer safety plans, never actual captures."""

from __future__ import annotations

import argparse
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT / "python"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from raos.application.editorial import product_safety_manufacturer_capture as owner  # noqa: E402
from scripts.raos_build_core import BuildRegistryError, atomic_write  # noqa: E402

INPUT_PATHS = (
    Path("changes/editorial-portfolio-v2/editorial-portfolio.v2.json"),
    Path("python/raos/application/editorial/product_safety_manufacturer_capture.py"),
)
OUTPUT_PATHS = (
    Path(
        "changes/st-1704/self-hosted-editorial-pilot-v1/sources/"
        "product-safety-manufacturer-query-plan.v1.json"
    ),
    Path(
        "changes/st-1704/self-hosted-editorial-pilot-v1/sources/"
        "product-safety-manufacturer-query-evidence.empty.v1.json"
    ),
)
TEST_PATHS = (
    Path("tests/editorial_product_safety_manufacturer_capture"),
    Path("tests/editorial_product_safety_receipts"),
)


class GenerationFailure(ValueError):
    """A sanitized local-generation failure, not an evidence result."""


def generate(*, root: Path = ROOT, check: bool = False) -> None:
    # Render both before writing either. Existing raw/metadata captures are not
    # inputs or outputs: a new plan never refreshes or rebinds old observations.
    outputs = {
        OUTPUT_PATHS[0]: owner.render_product_safety_manufacturer_query_plan(root),
        OUTPUT_PATHS[1]: owner.render_product_safety_manufacturer_empty_evidence(root),
    }
    differences = []
    for relative, payload in outputs.items():
        target = root / relative
        for parent in (target, *target.parents):
            if parent == root:
                break
            if parent.is_symlink():
                raise GenerationFailure("ST1704_MANUFACTURER_PLAN_OUTPUT_UNSAFE")
        if target.exists():
            metadata = target.lstat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise GenerationFailure("ST1704_MANUFACTURER_PLAN_OUTPUT_UNSAFE")
            if target.read_bytes() == payload:
                continue
        differences.append((relative, payload))
    if check:
        if differences:
            raise GenerationFailure("ST1704_MANUFACTURER_PLAN_DRIFT")
        return
    for relative, payload in differences:
        atomic_write(relative, payload, root=root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    try:
        generate(check=arguments.check)
    except (
        GenerationFailure,
        owner.ProductSafetyManufacturerCaptureFailure,
        BuildRegistryError,
        OSError,
    ):
        print("ST1704_MANUFACTURER_PLAN_GENERATION_FAILED", file=sys.stderr)
        return 1
    print("ST1704_MANUFACTURER_PLAN_GENERATED_NO_CAPTURE_OR_PUBLICATION_AUTHORITY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

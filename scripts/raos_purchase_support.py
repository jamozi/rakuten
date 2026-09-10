#!/usr/bin/env python3
"""Offline review-bound import from the existing ASP normalization pipeline."""

from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from raos.application.editorial.purchase_offer_import import (  # noqa: E402
    approved_offer_from_normalized,
)  # noqa: E402
from raos.application.editorial.purchase_support import validate_catalog  # noqa: E402  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("import-offer")
    p.add_argument("--normalized", type=Path, required=True)
    p.add_argument("--review", type=Path, required=True)
    p.add_argument(
        "--catalog",
        type=Path,
        default=ROOT / "changes/reader-purchase-support-v1/purchase-support.v1.json",
    )
    p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        # Accept one selected normalized product record, never reports or a whole account dump.
        if (
            args.normalized.stat().st_size > 1048576
            or args.review.stat().st_size > 65536
        ):
            raise ValueError("INPUT_TOO_LARGE")
        record = json.loads(args.normalized.read_text())
        review = json.loads(args.review.read_text())
        offer = approved_offer_from_normalized(record, review)
        catalog = json.loads(args.catalog.read_text())
        catalog["offers"] = [
            o for o in catalog["offers"] if o["offer_id"] != offer["offer_id"]
        ] + [offer]
        validate_catalog(catalog)
        # A separate candidate file is required; the active catalog/article is never auto-published.
        if args.output.resolve() == args.catalog.resolve():
            raise ValueError("SEPARATE_OUTPUT_REQUIRED")
        fd = os.open(
            args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(fd, "w") as stream:
            json.dump(catalog, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except ValueError, KeyError, TypeError, OSError:
        print("PURCHASE_OFFER_IMPORT_REJECTED", file=sys.stderr)
        return 2
    print("PURCHASE_OFFER_CANDIDATE_WRITTEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

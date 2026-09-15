#!/usr/bin/env python3
"""Print the read-only maintenance report for the reader purchase-support catalog.

Reads the catalog and writes JSON to stdout only. It fetches no URL and writes no
file. It is not a generator and is not registered in changes/build/manifest.v2.json.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
import json
from pathlib import Path
import sys
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from raos.application.editorial.purchase_maintenance import (  # noqa: E402
    maintenance_report,
)
from raos.application.editorial.purchase_support import JST  # noqa: E402

CATALOG_INPUT_PATH: Final = (
    ROOT / "changes/reader-purchase-support-v1/purchase-support.v1.json"
)


def jst_date(value: str) -> date:
    try:
        if len(value) != 10:
            raise ValueError(value)
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--as-of",
        type=jst_date,
        default=None,
        help="JST date to compare against (YYYY-MM-DD); default: today in JST",
    )
    parser.add_argument(
        "--spec-max-age-days",
        type=int,
        default=None,
        help="spec re-check interval in days; omit while the interval is undecided",
    )
    parser.add_argument("--catalog", type=Path, default=CATALOG_INPUT_PATH)
    args = parser.parse_args(argv)
    as_of = args.as_of or datetime.now(JST).date()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    try:
        report = maintenance_report(
            catalog, as_of=as_of, spec_max_age_days=args.spec_max_age_days
        )
    except ValueError as error:
        parser.error(str(error))
    sys.stdout.write(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

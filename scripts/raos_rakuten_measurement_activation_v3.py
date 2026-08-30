#!/usr/bin/env python3
"""Materialize verified Editorial V3 Rakuten Money Links owner-privately."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Final


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
PYTHON_ROOT: Final = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.application.editorial.editorial_portfolio_v3 import (  # noqa: E402
    EditorialPortfolioV3Failure,
    load_editorial_portfolio_v3,
)
from raos.application.editorial.rakuten_measurement_activation_v3 import (  # noqa: E402
    RakutenMeasurementActivationV3Failure,
    materialize_rakuten_measurement_activation_v3,
)


DEFAULT_PRIVATE_ROOT: Final = REPOSITORY_ROOT / ".secrets/editorial-portfolio-v3"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--private-root",
        type=Path,
        default=DEFAULT_PRIVATE_ROOT,
        help="absolute owner-private directory; mode must be 0700",
    )
    parser.add_argument(
        "--admin-receipt",
        required=True,
        help="relative mode-0600 administrator/CSV verification receipt",
    )
    parser.add_argument(
        "--money-link-mapping",
        required=True,
        help="relative mode-0600 final Money Link mapping",
    )
    parser.add_argument(
        "--dry-run-output",
        required=True,
        help="relative mode-0600 hash/count receipt to write",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        private_root = arguments.private_root.resolve()
        portfolio = load_editorial_portfolio_v3(REPOSITORY_ROOT)
        report = materialize_rakuten_measurement_activation_v3(
            repository_root=REPOSITORY_ROOT,
            private_root=private_root,
            portfolio=portfolio,
            admin_receipt_name=arguments.admin_receipt,
            money_link_mapping_name=arguments.money_link_mapping,
            dry_run_output_name=arguments.dry_run_output,
        )
    except (EditorialPortfolioV3Failure, RakutenMeasurementActivationV3Failure) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

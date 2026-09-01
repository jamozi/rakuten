#!/usr/bin/env python3
"""Materialize verified Editorial V3 Rakuten Money Links owner-privately."""

from __future__ import annotations

import argparse
import hashlib
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
    admin_verification_receipt_template_v3,
    materialize_rakuten_measurement_activation_v3,
    money_link_mapping_template_v3,
)
from raos.application.finance.editorial_economics_v3 import (  # noqa: E402
    EditorialEconomicsV3Failure,
    canonical_json_bytes,
    read_private_bytes,
    write_private_bytes,
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
    subcommands = parser.add_subparsers(dest="command", required=True)
    mapping_template = subcommands.add_parser("money-link-template")
    mapping_template.add_argument(
        "--output",
        required=True,
        help="relative mode-0600 incomplete 74-row mapping template to write",
    )
    admin_template = subcommands.add_parser("admin-receipt-template")
    admin_template.add_argument(
        "--money-link-mapping",
        required=True,
        help="relative mode-0600 completed Money Link mapping",
    )
    admin_template.add_argument(
        "--output",
        required=True,
        help="relative mode-0600 administrator/CSV receipt template to write",
    )
    activation = subcommands.add_parser("activate")
    activation.add_argument(
        "--admin-receipt",
        required=True,
        help="relative mode-0600 administrator/CSV verification receipt",
    )
    activation.add_argument(
        "--money-link-mapping",
        required=True,
        help="relative mode-0600 final Money Link mapping",
    )
    activation.add_argument(
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
        if arguments.command == "money-link-template":
            document = money_link_mapping_template_v3(
                repository_root=REPOSITORY_ROOT,
                portfolio=portfolio,
            )
            raw = canonical_json_bytes(document)
            write_private_bytes(private_root, arguments.output, raw)
            report: object = {
                "schema": "RAOS_EDITORIAL_V3_PRIVATE_TEMPLATE_RESULT_V1",
                "kind": "money_link_mapping",
                "row_count": len(portfolio.cta_by_candidate_id),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "complete": False,
            }
        elif arguments.command == "admin-receipt-template":
            mapping_raw = read_private_bytes(
                private_root,
                arguments.money_link_mapping,
            )
            document = admin_verification_receipt_template_v3(
                repository_root=REPOSITORY_ROOT,
                portfolio=portfolio,
                money_link_mapping=mapping_raw,
            )
            raw = canonical_json_bytes(document)
            write_private_bytes(private_root, arguments.output, raw)
            report = {
                "schema": "RAOS_EDITORIAL_V3_PRIVATE_TEMPLATE_RESULT_V1",
                "kind": "admin_verification_receipt",
                "row_count": len(portfolio.cta_by_candidate_id),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "complete": False,
            }
        else:
            report = materialize_rakuten_measurement_activation_v3(
                repository_root=REPOSITORY_ROOT,
                private_root=private_root,
                portfolio=portfolio,
                admin_receipt_name=arguments.admin_receipt,
                money_link_mapping_name=arguments.money_link_mapping,
                dry_run_output_name=arguments.dry_run_output,
            )
    except (
        EditorialEconomicsV3Failure,
        EditorialPortfolioV3Failure,
        RakutenMeasurementActivationV3Failure,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

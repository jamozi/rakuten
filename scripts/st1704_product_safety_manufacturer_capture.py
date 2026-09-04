#!/usr/bin/env python3
"""Closed CLI for manufacturer product-safety capture and replay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Final, NoReturn


SCRIPT_PATH: Final = Path(__file__).resolve()
REPOSITORY_ROOT: Final = SCRIPT_PATH.parent.parent
PYTHON_ROOT: Final = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.application.editorial.product_safety_manufacturer_capture import (  # noqa: E402
    MANUAL_REQUIRED_REASON,
    PUBLICATION_AUTHORITY,
    ProductSafetyManufacturerCaptureFailure,
    capture_product_safety_manufacturer_query,
    describe_product_safety_manufacturer_query,
    load_product_safety_manufacturer_query_plan,
    render_product_safety_manufacturer_empty_evidence,
    render_product_safety_manufacturer_query_plan,
    verify_product_safety_manufacturer_capture_set,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate, describe, capture, or replay exact manufacturer "
            "product-safety queries."
        )
    )
    parser.add_argument(
        "action",
        choices=(
            "validate",
            "render-plan",
            "render-empty-evidence",
            "dry-run",
            "capture",
            "verify-set",
        ),
    )
    parser.add_argument("--product")
    return parser


def _fail(message: str) -> NoReturn:
    raise SystemExit(message)


def _validate_arguments(arguments: argparse.Namespace) -> None:
    if (
        arguments.action
        in {
            "validate",
            "verify-set",
            "render-plan",
            "render-empty-evidence",
        }
        and arguments.product is not None
    ):
        _fail(f"{arguments.action} does not accept --product")
    if (
        arguments.action in {"dry-run", "capture"}
        and type(arguments.product) is not str
    ):
        _fail(f"{arguments.action} requires --product")


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    _validate_arguments(arguments)
    try:
        if arguments.action == "render-plan":
            sys.stdout.write(
                render_product_safety_manufacturer_query_plan(REPOSITORY_ROOT).decode(
                    "utf-8"
                )
            )
            return 0
        if arguments.action == "render-empty-evidence":
            sys.stdout.write(
                render_product_safety_manufacturer_empty_evidence(
                    REPOSITORY_ROOT
                ).decode("utf-8")
            )
            return 0
        if arguments.action == "validate":
            plan = load_product_safety_manufacturer_query_plan(REPOSITORY_ROOT)
            reviewed = sum(
                row.endpoint_review_status == "REVIEWED_EXACT_QUERY"
                for row in plan.products
            )
            output: dict[str, object] = {
                "status": "VALID_FAIL_CLOSED",
                "publication_authority": PUBLICATION_AUTHORITY,
                "credentials_used": False,
                "production_write": False,
                "product_count": len(plan.products),
                "reviewed_exact_query_product_count": reviewed,
                "manual_required_product_count": len(plan.products) - reviewed,
                "manual_required_reason": MANUAL_REQUIRED_REASON,
                "plan_sha256": plan.plan_sha256,
                "portfolio_sha256": plan.portfolio_sha256,
            }
        elif arguments.action == "verify-set":
            evidence = verify_product_safety_manufacturer_capture_set(REPOSITORY_ROOT)
            output = {
                "status": (
                    "VERIFIED_MANUFACTURER_CLEAR"
                    if evidence.complete
                    else "BLOCKED_MANUFACTURER_EVIDENCE"
                ),
                "network_used": False,
                "production_write": False,
                "product_count": len(evidence.products),
                "capture_count": evidence.capture_count,
                "verified_product_count": sum(
                    row.status == "VERIFIED_NONE_FOUND" for row in evidence.products
                ),
                "manual_required_product_count": sum(
                    row.status == "MANUAL_REQUIRED" for row in evidence.products
                ),
                "bundle_sha256": evidence.bundle_sha256,
            }
        elif arguments.action == "dry-run":
            output = describe_product_safety_manufacturer_query(
                REPOSITORY_ROOT,
                product_id=arguments.product,
            )
        else:
            result = capture_product_safety_manufacturer_query(
                REPOSITORY_ROOT,
                product_id=arguments.product,
            )
            output = {
                "status": "CAPTURED_OWNER_PRIVATE",
                "publication_authority": PUBLICATION_AUTHORITY,
                "credentials_used": result.credentials_used,
                "production_write": result.production_write,
                "product_id": result.product_id,
                "result": result.result,
                "result_count": result.result_count,
                "notice_ids": list(result.notice_ids),
                "retrieved_at_utc": result.retrieved_at_utc,
                "request_raw_sha256": result.request_sha256,
                "response_raw_sha256": result.response_sha256,
                "capture_sha256": result.capture_sha256,
                "metadata_path": result.metadata_path.relative_to(
                    REPOSITORY_ROOT
                ).as_posix(),
                "request_path": result.request_path.relative_to(
                    REPOSITORY_ROOT
                ).as_posix(),
                "response_path": result.response_path.relative_to(
                    REPOSITORY_ROOT
                ).as_posix(),
            }
    except ProductSafetyManufacturerCaptureFailure as exc:
        print(exc.code.value, file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

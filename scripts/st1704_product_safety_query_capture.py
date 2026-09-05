#!/usr/bin/env python3
"""Closed CLI for official CAA/NITE product-safety query evidence."""

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

from raos.application.editorial.product_safety_query_capture import (  # noqa: E402
    PUBLICATION_AUTHORITY,
    ProductSafetyQueryCaptureFailure,
    capture_product_safety_query,
    describe_product_safety_query,
    load_product_safety_query_plan,
    verify_product_safety_query_capture_set,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture one fixed, credential-free Japanese administrative "
            "product-safety search."
        )
    )
    parser.add_argument(
        "action", choices=("validate", "dry-run", "capture", "verify-set")
    )
    parser.add_argument("--product")
    parser.add_argument("--provider", choices=("CAA", "NITE"))
    parser.add_argument("--scope", choices=("RECALL", "ACCIDENT"))
    return parser


def _fail(message: str) -> NoReturn:
    raise SystemExit(message)


def _selection(arguments: argparse.Namespace) -> tuple[str, str, str]:
    values = (arguments.product, arguments.provider, arguments.scope)
    if not all(type(value) is str for value in values):
        _fail("dry-run and capture require --product, --provider, and --scope")
    return values  # type: ignore[return-value]


def _validate_arguments(arguments: argparse.Namespace) -> None:
    selected = (arguments.product, arguments.provider, arguments.scope)
    if arguments.action in {"validate", "verify-set"} and any(
        value is not None for value in selected
    ):
        _fail(f"{arguments.action} does not accept product, provider, or scope")


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    _validate_arguments(arguments)
    try:
        if arguments.action == "validate":
            plan = load_product_safety_query_plan(REPOSITORY_ROOT)
            output: dict[str, object] = {
                "status": "VALID",
                "publication_authority": PUBLICATION_AUTHORITY,
                "credentials_used": False,
                "production_write": False,
                "product_count": len(plan.products),
                "provider_scope_count": len(plan.provider_specs),
                "query_count": len(plan.products) * len(plan.provider_specs),
                "plan_sha256": plan.plan_sha256,
                "portfolio_sha256": plan.portfolio_sha256,
            }
        elif arguments.action == "verify-set":
            evidence = verify_product_safety_query_capture_set(REPOSITORY_ROOT)
            output = {
                "status": (
                    "VERIFIED_ADMINISTRATIVE_CLEAR"
                    if evidence.complete
                    else "BLOCKED_ADMINISTRATIVE_RESULT"
                ),
                "network_used": False,
                "production_write": False,
                "product_count": len(evidence.products),
                "capture_count": evidence.capture_count,
                "administratively_verified_product_count": sum(
                    product.status == "VERIFIED_NONE_FOUND"
                    for product in evidence.products
                ),
                "bundle_sha256": evidence.bundle_sha256,
            }
        else:
            product, provider, scope = _selection(arguments)
            if arguments.action == "dry-run":
                output = describe_product_safety_query(
                    REPOSITORY_ROOT,
                    product_id=product,
                    provider=provider,
                    scope=scope,
                )
            else:
                result = capture_product_safety_query(
                    REPOSITORY_ROOT,
                    product_id=product,
                    provider=provider,
                    scope=scope,
                )
                output = {
                    "status": "CAPTURED_OWNER_PRIVATE",
                    "publication_authority": PUBLICATION_AUTHORITY,
                    "credentials_used": result.credentials_used,
                    "production_write": result.production_write,
                    "product_id": result.product_id,
                    "provider": result.provider,
                    "scope": result.scope,
                    "result": result.result,
                    "result_count": result.result_count,
                    "notice_ids": list(result.notice_ids),
                    "retrieved_at_utc": result.retrieved_at_utc,
                    "request_material_sha256": result.request_material_sha256,
                    "response_raw_sha256": result.response_raw_sha256,
                    "capture_sha256": result.capture_sha256,
                    "metadata_path": result.metadata_path.relative_to(
                        REPOSITORY_ROOT
                    ).as_posix(),
                    "raw_response_path": result.raw_response_path.relative_to(
                        REPOSITORY_ROOT
                    ).as_posix(),
                }
    except ProductSafetyQueryCaptureFailure as exc:
        print(exc.code.value, file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

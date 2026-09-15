#!/usr/bin/env python3
"""KS-020 Rakuten price refresh: plan / fetch / apply / gate / purge-expired.

Only ``fetch`` talks to the network, and only with ``--owner-approved-run``.
API price and availability values are written exclusively to
``<owner checkout>/.secrets/rakuten-price-refresh/<run_id>/`` (0600). Nothing in
this command prints credentials or price values. Contract:
changes/reader-purchase-support-v1/price-refresh-contract.md
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))

from raos.adapters.rakuten_price_refresh_client import (  # noqa: E402
    PriceRefreshClient,
    PrivateStore,
    SystemHttpsTransport,
    Transport,
    observation_record,
    read_refresh_credentials,
    scan_repository_for_overlay,
)
from raos.domain.editorial.rakuten_price_refresh import (  # noqa: E402
    MAX_CACHE_AGE,
    MAX_REQUESTS_PER_RUN,
    OBSERVATION_SCHEMA,
    PURGED_SCHEMA,
    RUN_ID_PATTERN,
    UTC,
    GateFinding,
    RefreshError,
    Status,
    build_overlay,
    build_plan,
    classify_observation,
    fail,
    gate,
    iso,
    new_approval,
    parse_time,
    redact_approval,
    require_run_id,
    sha256_hex,
    validate_approval,
    validate_overlay,
    validate_plan,
)

EXIT_OK = 0
EXIT_REFUSED = 2
EXIT_GATE_REFUSED = 3


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="raos_rakuten_price_refresh")
    sub = root.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="offline: derive editorial identity bindings")
    plan.add_argument("--catalog", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    fetch = sub.add_parser("fetch", help="network: one itemCode GET per plan entry")
    fetch.add_argument("--owner-checkout", type=Path, required=True)
    fetch.add_argument("--plan", type=Path, required=True)
    fetch.add_argument("--owner-approved-run", dest="run_id")
    fetch.add_argument("--max-requests", type=int, default=MAX_REQUESTS_PER_RUN)
    apply = sub.add_parser("apply", help="offline: raw observations -> private overlay")
    apply.add_argument("--owner-checkout", type=Path, required=True)
    apply.add_argument("--run-id", required=True)
    apply.add_argument("--plan", type=Path, required=True)
    apply.add_argument("--now")
    check = sub.add_parser("gate", help="offline: refuse unsafe publication")
    check.add_argument("--owner-checkout", type=Path, required=True)
    check.add_argument("--run-id", required=True)
    check.add_argument("--repository", type=Path, required=True)
    check.add_argument("--body", action="append", default=[], metavar="KEY=PATH")
    check.add_argument("--now")
    purge = sub.add_parser("purge-expired", help="offline: delete expired API values")
    purge.add_argument("--owner-checkout", type=Path, required=True)
    purge.add_argument("--run-id")
    purge.add_argument("--include-unexpired", action="store_true")
    purge.add_argument("--now")
    return root


def _now(value: str | None, clock: Callable[[], datetime]) -> datetime:
    """``--now`` may only move the clock forward: an earlier value would bypass expiry checks."""
    current = clock()
    return max(current, parse_time(value)) if value else current


def _read_optional(store: PrivateStore, path: Path) -> Any:
    try:
        return store.read_json(path) if path.exists() else None
    except RefreshError, OSError, ValueError:
        return None


def _run_status(store: PrivateStore, run_id: str) -> tuple[str, datetime | None]:
    """PURGED / EMPTY / DATED (with the earliest expiry) / UNDATED (records unreadable or invalid)."""
    directory = store.run_directory(run_id)
    has_raw = (directory / "raw").exists()
    overlay_path, approval_path = (
        directory / "overlay.v1.json",
        directory / "approval.v1.json",
    )
    try:
        overlay = store.read_json(overlay_path) if overlay_path.exists() else None
        approval = store.read_json(approval_path) if approval_path.exists() else None
        if isinstance(overlay, dict) and overlay.get("schema") == PURGED_SCHEMA:
            return ("UNDATED", None) if has_raw else ("PURGED", None)
        if overlay is not None:
            validate_overlay(overlay)
            return "DATED", parse_time(overlay["cache_expires_at"])
        if approval is not None:
            # No overlay yet: every observation is later than approval, so this expiry is earlier.
            return "DATED", parse_time(
                validate_approval(approval, run_id)["approved_at"]
            ) + MAX_CACHE_AGE
    except RefreshError, OSError, ValueError, KeyError, TypeError:
        return "UNDATED", None
    return ("UNDATED", None) if has_raw else ("EMPTY", None)


def _expired_unpurged_runs(
    store: PrivateStore, now: datetime, *, exclude: str | None = None
) -> list[str]:
    stale = []
    for run_id in store.run_ids():
        if run_id == exclude or RUN_ID_PATTERN.fullmatch(run_id) is None:
            continue
        status, expires = _run_status(store, run_id)
        if status == "UNDATED" or (
            status == "DATED" and expires is not None and now >= expires
        ):
            stale.append(run_id)
    return stale


def command_plan(args: argparse.Namespace) -> int:
    if args.output.resolve() == args.catalog.resolve():
        fail("SEPARATE_OUTPUT_REQUIRED")
    raw = args.catalog.read_bytes()
    plan = build_plan(json.loads(raw), sha256_hex(raw))
    payload = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    args.output.write_text(payload, encoding="utf-8")
    emit(
        {
            "result": "PLAN_WRITTEN",
            "entries": len(plan["entries"]),
            "multi_sku": sum(1 for e in plan["entries"] if e["multi_sku"]),
            "skipped": len(plan["skipped"]),
            "plan_sha256": sha256_hex(payload.encode("utf-8")),
        }
    )
    return EXIT_OK


def command_fetch(
    args: argparse.Namespace,
    transport: Transport | None,
    clock: Callable[[], datetime],
    sleep: Callable[[float], None],
) -> int:
    if not args.run_id:
        fail("OWNER_APPROVAL_REQUIRED")
    run_id = require_run_id(args.run_id)
    if not 1 <= args.max_requests <= MAX_REQUESTS_PER_RUN:
        fail("MAX_REQUESTS_INVALID")
    plan_bytes = args.plan.read_bytes()
    entries = validate_plan(json.loads(plan_bytes))
    if not entries:
        fail("PLAN_EMPTY")
    if len(entries) > args.max_requests:
        fail("MAX_REQUESTS_EXCEEDED")
    store = PrivateStore(args.owner_checkout)
    directory = store.run_directory(run_id)
    if directory.exists():
        fail("RUN_ALREADY_EXISTS")
    if _expired_unpurged_runs(store, clock()):
        fail("EXPIRED_RUN_NOT_PURGED")
    credentials = read_refresh_credentials(args.owner_checkout)
    approval = new_approval(run_id, sha256_hex(plan_bytes), clock())
    store.write_json(directory / "approval.v1.json", approval)
    client = PriceRefreshClient(
        transport or SystemHttpsTransport(), credentials, clock=clock, sleep=sleep
    )
    counts: dict[str, int] = {}
    for index, entry in enumerate(entries, start=1):
        try:
            fetched = client.fetch(entry.item_code)
        except RefreshError as error:
            store.write_json(
                directory / "abort.v1.json", {"code": error.code, "at_index": index}
            )
            raise
        if fetched.http_status in (400, 401, 403):
            store.write_json(
                directory / "abort.v1.json",
                {"code": f"HTTP_{fetched.http_status}", "at_index": index},
            )
            fail(
                "RAKUTEN_WRONG_PARAMETER"
                if fetched.http_status == 400
                else "RAKUTEN_AUTH_REJECTED"
            )
        record = observation_record(run_id, entry.offer_id, entry.item_code, fetched)
        store.write_json(directory / "raw" / f"{index:03d}.json", record)
        key = str(fetched.http_status)
        counts[key] = counts.get(key, 0) + 1
    emit(
        {
            "result": "FETCHED",
            "run_id": run_id,
            "requests": len(entries),
            "http_status_counts": counts,
        }
    )
    return EXIT_OK


def command_apply(args: argparse.Namespace, clock: Callable[[], datetime]) -> int:
    run_id = require_run_id(args.run_id)
    store = PrivateStore(args.owner_checkout)
    directory = store.run_directory(run_id)
    approval = validate_approval(
        store.read_json(directory / "approval.v1.json"), run_id
    )
    plan_bytes = args.plan.read_bytes()
    if sha256_hex(plan_bytes) != approval["plan_sha256"]:
        fail("APPROVAL_PLAN_MISMATCH")
    entries = {e.offer_id: e for e in validate_plan(json.loads(plan_bytes))}
    now = _now(args.now, clock)
    results = []
    for record in store.raw_records(run_id):
        if record.get("schema") != OBSERVATION_SCHEMA or record.get("run_id") != run_id:
            fail("RAW_OBSERVATION_INVALID")
        entry = entries.get(record.get("offer_id"))
        if entry is None or record.get("item_code") != entry.item_code:
            fail("RAW_OBSERVATION_UNBOUND")
        body = record.get("body")
        if body is not None and sha256_hex(body.encode("utf-8")) != record.get(
            "body_sha256"
        ):
            fail("RAW_OBSERVATION_TAMPERED")
        results.append(
            classify_observation(
                entry,
                int(record["http_status"]),
                body,
                parse_time(record["observed_at"]),
            )
        )
    overlay = build_overlay(run_id, approval["plan_sha256"], results, now)
    store.write_json(directory / "overlay.v1.json", overlay)
    counts: dict[str, int] = {}
    for item in overlay["entries"]:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    emit(
        {
            "result": "OVERLAY_WRITTEN",
            "run_id": run_id,
            "status_counts": counts,
            "identity_mismatch_offer_ids": [
                e["offer_id"]
                for e in overlay["entries"]
                if e["status"] == Status.IDENTITY_MISMATCH.value
            ],
            "purge_publish_due_by": overlay["cache_expires_at"],
        }
    )
    return EXIT_OK


def command_gate(args: argparse.Namespace, clock: Callable[[], datetime]) -> int:
    run_id = require_run_id(args.run_id)
    store = PrivateStore(args.owner_checkout)
    directory = store.run_directory(run_id)
    overlay = store.read_json(directory / "overlay.v1.json")
    approval_path = directory / "approval.v1.json"
    approval = store.read_json(approval_path) if approval_path.exists() else None
    bodies = {}
    for item in args.body:
        key, separator, path = item.partition("=")
        if not separator or not key or key in bodies:
            fail("BODY_ARGUMENT_INVALID")
        bodies[key] = Path(path).read_text(encoding="utf-8")
    # The publisher commits in the owner checkout; the editor may work in a separate worktree.
    repositories = {
        "owner_checkout": args.owner_checkout.resolve(),
        "repository": args.repository.resolve(),
    }
    leaks: list[str] = []
    for label, repository in repositories.items():
        if label == "repository" and repository == repositories["owner_checkout"]:
            continue
        leaks.extend(
            f"{label}:{leak}"
            for leak in scan_repository_for_overlay(repository, overlay, approval)
        )
    now = _now(args.now, clock)
    findings = gate(
        overlay, now=now, bodies=bodies, tracked_leaks=leaks, approval=approval
    )
    findings.extend(
        GateFinding("EXPIRED_RUN_NOT_PURGED", r)
        for r in _expired_unpurged_runs(store, now, exclude=run_id)
    )
    findings.sort(key=lambda f: (f.code, f.subject))
    emit(
        {
            "result": "GATE_REFUSED" if findings else "GATE_PASS",
            "run_id": run_id,
            "findings": [{"code": f.code, "subject": f.subject} for f in findings],
        }
    )
    return EXIT_GATE_REFUSED if findings else EXIT_OK


def command_purge(args: argparse.Namespace, clock: Callable[[], datetime]) -> int:
    store = PrivateStore(args.owner_checkout)
    now = _now(args.now, clock)
    run_ids = (
        [require_run_id(args.run_id)]
        if args.run_id
        else [r for r in store.run_ids() if RUN_ID_PATTERN.fullmatch(r)]
    )
    report = []
    for run_id in run_ids:
        status, expires = _run_status(store, run_id)
        if status == "PURGED":
            report.append({"run_id": run_id, "result": "ALREADY_PURGED"})
            continue
        if status == "EMPTY":
            report.append({"run_id": run_id, "result": "NO_RECORDS"})
            continue
        if (
            status == "DATED"
            and expires is not None
            and now < expires
            and not args.include_unexpired
        ):
            report.append(
                {
                    "run_id": run_id,
                    "result": "NOT_EXPIRED",
                    "cache_expires_at": iso(expires),
                }
            )
            continue
        # UNDATED (unreadable or invalid records) is purged immediately: retention fails safe.
        directory = store.run_directory(run_id)
        overlay_path, approval_path = (
            directory / "overlay.v1.json",
            directory / "approval.v1.json",
        )
        overlay = _read_optional(store, overlay_path)
        approval = _read_optional(store, approval_path)
        deleted = store.delete_raw(run_id)
        entries = overlay.get("entries") if isinstance(overlay, dict) else None
        offer_ids = (
            sorted(
                str(e["offer_id"])
                for e in entries
                if isinstance(e, dict) and "offer_id" in e
            )
            if isinstance(entries, list)
            else []
        )
        store.write_json(
            overlay_path,
            {
                "schema": PURGED_SCHEMA,
                "run_id": run_id,
                "purged_at": iso(now),
                "offer_ids": offer_ids,
            },
            replace=True,
        )
        purge_publish_recorded = False
        if isinstance(approval, dict):
            purge_publish_recorded = approval.get("purge_publish") is not None
            store.write_json(approval_path, redact_approval(approval), replace=True)
        report.append(
            {
                "run_id": run_id,
                "result": "PURGED",
                "record_state": status,
                "raw_files_deleted": deleted,
                "published": bool(
                    isinstance(approval, dict) and approval.get("publish")
                ),
                "purge_publish_recorded": purge_publish_recorded,
                "approval_unreadable": approval_path.exists()
                and not isinstance(approval, dict),
            }
        )
    emit({"result": "PURGE_COMPLETE", "runs": report})
    return EXIT_OK


def main(
    argv: Sequence[str] | None = None,
    *,
    transport: Transport | None = None,
    clock: Callable[[], datetime] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> int:
    args = parser().parse_args(argv)
    now_clock = clock or (lambda: datetime.now(UTC))
    try:
        if args.command == "plan":
            return command_plan(args)
        if args.command == "fetch":
            import time

            return command_fetch(args, transport, now_clock, sleep or time.sleep)
        if args.command == "apply":
            return command_apply(args, now_clock)
        if args.command == "gate":
            return command_gate(args, now_clock)
        return command_purge(args, now_clock)
    except RefreshError as error:
        emit({"result": "REFUSED", "code": error.code})
        return EXIT_REFUSED
    except OSError, ValueError, KeyError, TypeError:
        # Exception text can contain paths or response fragments; only a code is shown.
        emit({"result": "REFUSED", "code": "INPUT_UNREADABLE_OR_INVALID"})
        return EXIT_REFUSED


if __name__ == "__main__":
    raise SystemExit(main())

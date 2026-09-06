#!/usr/bin/env python3
"""Validate registered hubs locally, then create bounded, resumable MCP drafts only."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "python"), str(ROOT / "scripts")]
import raos_reader_release_pages as pages  # noqa: E402
import raos_wordpress_publication_request as publication  # noqa: E402
from raos.application.finance.editorial_economics_v3 import (  # noqa: E402
    read_private_json,
    write_private_bytes,
)
from raos_wordpress_release_workflow import preview_origin  # noqa: E402
from raos_wordpress_verification import source_fingerprint  # noqa: E402

OWNER = Path("/home/minami/rakuten")
DIRECTORY = OWNER / ".secrets/wordpress-mcp/reader-hub-drafts"
SCHEMA = "RAOS_WORDPRESS_READER_HUB_DRAFTS_V1"
JOURNAL_NAME = "reader-hub-drafts.v1.json"


def fail(code: str) -> None:
    raise ValueError("RAOS_READER_HUB_" + code)


def selected_articles(root: Path) -> dict[str, str]:
    registry = json.loads((root / pages.PORTFOLIO_SOURCE).read_bytes())
    return {row["article_id"]: row["production_slug"] for row in registry["articles"]}


def require_validated_source(root: Path, evidence: Mapping[str, Any]) -> None:
    if source_fingerprint(root) != evidence.get("source_sha256"):
        fail("LOCAL_VALIDATION_CHANGED")


def reconcile_hub_drafts(
    client: Any,
    *,
    root: Path,
    selected: Sequence[str],
    receipt: dict[str, Any],
    persist: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    """Persist intent before sending; uncertainty never triggers automatic resend."""
    authored = pages.select_hub_pages(root, selected)
    registry_hash = pages.hub_registry_sha256(root)
    if (
        receipt.get("schema") != SCHEMA
        or receipt.get("registry_sha256") != registry_hash
        or receipt.get("slugs") != sorted(pages.HUB_SLUGS)
        or type(receipt.get("drafts")) is not dict
        or type(receipt.get("inflight")) is not dict
    ):
        fail("RECEIPT_INVALID")
    require_validated_source(root, receipt.get("local_validation", {}))
    listed = publication.list_all_documents(client, post_types=("post", "page"))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in listed:
        grouped.setdefault(row["slug"], []).append(row)
    for slug in selected_articles(root).values():
        entries = grouped.get(slug, [])
        if (
            len(entries) != 1
            or entries[0].get("post_type") != "post"
            or entries[0].get("status") != "publish"
        ):
            fail("PUBLIC_ARTICLE_IDENTITY_UNVERIFIED")
    for article in authored:
        slug = article.production_slug
        desired = article.document()
        expected = publication.sha256_json(desired)
        candidates = grouped.get(slug, [])
        if len(candidates) > 1:
            fail("SLUG_CONFLICT")
        known = receipt["drafts"].get(slug)
        intent = receipt["inflight"].get(slug)
        if intent is not None and intent != expected:
            fail("INTENT_CHANGED")
        if not candidates:
            if known or intent:
                fail("WRITE_RESULT_UNKNOWN")
            receipt["inflight"][slug] = expected
            persist(receipt)
            # Exceptions preserve inflight intent on disk. A later call reads first.
            try:
                require_validated_source(root, receipt.get("local_validation", {}))
            except ValueError:
                # No network call has begun. Keep uncertain sent operations
                # separately from this locally cancelled intent.
                receipt["inflight"].pop(slug, None)
                persist(receipt)
                raise
            document = client.call("raos-codex-content-create-draft", desired)
            if document.get("status") != "draft":
                fail("DRAFT_RESULT_INVALID")
        else:
            document = candidates[0]
            if (
                document.get("post_type") != "page"
                or document.get("status") not in {"draft", "publish"}
                or publication.document_projection(document) != desired
            ):
                fail("SLUG_CONFLICT")
            if known and known.get("id") != document.get("id"):
                fail("ID_CHANGED")
        if (
            type(document.get("id")) is not int
            or document["id"] < 1
            or publication.document_projection(document) != desired
        ):
            fail("DRAFT_RESULT_INVALID")
        readback = client.call("raos-codex-content-get", {"id": document["id"]})
        observed_hash = publication.sha256_json(
            {
                "schema": "ContentDocumentV1",
                "id": document["id"],
                "status": readback.get("status"),
                **publication.document_projection(readback),
            }
        )
        if readback != document or observed_hash != document.get("content_sha256"):
            fail("READBACK_CHANGED")
        receipt["drafts"][slug] = {
            "id": document["id"],
            "status": document["status"],
            "content_sha256": observed_hash,
            "template_sha256": hashlib.sha256(
                article.block_markup.encode()
            ).hexdigest(),
        }
        receipt["inflight"].pop(slug, None)
        persist(receipt)
    receipt["state"] = "DRAFT_IDENTITIES_BOUND"
    persist(receipt)
    return receipt


def validate_local_hubs(selected: Sequence[str]) -> dict[str, Any]:
    """Run the existing browser diagnostic; this is not a production approval."""
    origin = preview_origin(dict(os.environ))
    node = shutil.which("node")
    if (
        not node
        or subprocess.check_output([node, "--version"], text=True).strip() != "v24.18.1"
    ):
        fail("NODE_RUNTIME_UNAVAILABLE")
    before = source_fingerprint(ROOT)
    output = (
        ROOT
        / "output/playwright/reader-production"
        / datetime.now(UTC).strftime("hub-drafts-%Y%m%dT%H%M%S%fZ")
    )
    environment = {
        **os.environ,
        "READER_AUDIT_SURFACES": ",".join("hub-" + slug for slug in selected),
    }
    subprocess.run(
        [
            node,
            "changes/wordpress-local-preview-v1/browser/reader_experience_audit.mjs",
            origin,
            str(output),
        ],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    raw = (output / "manifest.json").read_bytes()
    report = json.loads(raw)
    if (
        report.get("profile") != "LOCAL_READER_DIAGNOSTIC"
        or report.get("errors")
        or report.get("failures")
        or {row["surface"] for row in report["results"]}
        != {"hub-" + slug for slug in selected}
        or any(
            {entry["width"] for entry in row["widths"]} != {360, 390, 768, 1024, 1440}
            for row in report["results"]
        )
        or before != source_fingerprint(ROOT)
    ):
        fail("LOCAL_VALIDATION_CHANGED")
    return {
        "profile": "LOCAL_HUB_DRAFT_PREPARATION",
        "source_sha256": before,
        "report_sha256": hashlib.sha256(raw).hexdigest(),
        "report_path": str(output / "manifest.json"),
        "publication_authority": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("stage", choices=("check", "drafts"))
    parser.add_argument("--slugs", required=True)
    args = parser.parse_args()
    try:
        selected = sorted(
            page.production_slug
            for page in pages.select_hub_pages(ROOT, args.slugs.split(","))
        )
        evidence = validate_local_hubs(selected)
        if args.stage == "check":
            print(json.dumps(evidence, ensure_ascii=False))
            return 0
        with publication.request_lock():
            require_validated_source(ROOT, evidence)
            registry_hash = pages.hub_registry_sha256(ROOT)
            name = JOURNAL_NAME
            if (DIRECTORY / name).exists():
                receipt = read_private_json(DIRECTORY, name)
            else:
                receipt = {
                    "schema": SCHEMA,
                    "registry_sha256": registry_hash,
                    "slugs": sorted(pages.HUB_SLUGS),
                    "drafts": {},
                    "inflight": {},
                    "state": "PREPARED",
                }
            receipt["local_validation"] = evidence

            def persist(value: dict[str, Any]) -> None:
                value["updated_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                write_private_bytes(
                    DIRECTORY, name, publication.canonical_json_bytes(value)
                )

            persist(receipt)
            client = publication.EditorMcpClient(owner_checkout=OWNER)
            client.initialize()
            publication.validate_site_status(
                client.call("raos-codex-site-status", {}),
                require_measurement_off=True,
                allow_legacy_runtime=True,
            )
            reconcile_hub_drafts(
                client, root=ROOT, selected=selected, receipt=receipt, persist=persist
            )
            print(
                json.dumps(
                    {
                        "state": receipt["state"],
                        "pages": receipt["drafts"],
                        "receipt": str(DIRECTORY / name),
                        "published": False,
                    },
                    ensure_ascii=False,
                )
            )
        return 0
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(
            type(error).__name__
            + ": hub draft preparation stopped; existing receipt retained",
            file=sys.stderr,
        )
        return 69


if __name__ == "__main__":
    raise SystemExit(main())

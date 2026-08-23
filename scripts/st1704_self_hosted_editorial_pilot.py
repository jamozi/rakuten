#!/usr/bin/env python3
"""Closed four-command CLI for the ST-1704 self-hosted editorial pilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Final, TextIO
from urllib.parse import urlencode


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
PYTHON_ROOT: Final = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

COMMANDS: Final = (
    "prepare",
    "create-review-draft",
    "recover-create-review-draft",
    "verify-public",
)
ARTICLE_IDS: Final = (
    "st1703-first-suitcase-comparison",
    "st1704-portable-power-station-guide",
    "st1704-anker-solix-c300-c800-c1000-differences",
    "st1704-countertop-dishwasher-for-small-households",
    "st1704-compact-robot-vacuum-shortlist",
)


class _CliRefusal(RuntimeError):
    __slots__ = ("code",)

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _write_json(value: object, *, target: TextIO = sys.stdout) -> None:
    target.write(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )


def _prepared_result(value: Any) -> dict[str, object]:
    return {
        "article_id": value.article_id,
        "command": "prepare",
        "content_sha256": value.content_sha256,
        "external_writes": value.external_writes,
        "network_requests": value.network_requests,
        "packet_sha256": value.packet_sha256,
        "payload_sha256": value.request.snapshot.payload_sha256,
        "product_count": value.product_count,
        "production_evidence": value.production_evidence,
        "publication_actions": value.publication_actions,
        "publication_authority": value.publication_authority,
        "request_sha256": value.request.request_sha256,
        "public_slug": value.request.public_slug,
        "review_slug": value.request.slug,
        "source_count": value.source_count,
        "status": "PREPARED_FOR_OWNER_REVIEW_DRAFT",
    }


def _receipt_result(command: str, value: Any, request: Any) -> dict[str, object]:
    owner_apply_path: str | None = None
    if value.article_id == "st1703-first-suitcase-comparison":
        if type(value.target_public_post_id) is not int:
            raise _CliRefusal("JOURNAL_MISMATCH")
        owner_apply_path = "/wp-admin/tools.php?" + urlencode(
            (
                ("page", "kurashinoshirube-at003-update-v1"),
                ("payload_sha256", request.snapshot.payload_sha256),
                ("packet_sha256", value.packet_sha256),
                ("request_sha256", value.request_sha256),
                ("review_draft_id", str(value.draft_id)),
                ("target_public_post_id", str(value.target_public_post_id)),
            )
        )
    return {
        "article_id": value.article_id,
        "command": command,
        "disposition": value.disposition.value,
        "draft_id": value.draft_id,
        "live_authority": value.live_authority,
        "packet_sha256": value.packet_sha256,
        "payload_sha256": request.snapshot.payload_sha256,
        "production_evidence": False,
        "publication_authority": value.publication_authority,
        "request_sha256": value.request_sha256,
        "response_sha256": value.response_sha256,
        "status": value.status,
        "target_public_post_id": value.target_public_post_id,
        "owner_apply_path": owner_apply_path,
    }


def _verification_result(value: Any) -> dict[str, object]:
    return {
        "article_id": value.article_id,
        "article_html_sha256": value.article_html_sha256,
        "category_sha256": value.category_sha256,
        "command": "verify-public",
        "core_sitemap_sha256": value.core_sitemap_sha256,
        "expected_public_post_id": value.expected_public_post_id,
        "homepage_html_sha256": value.homepage_html_sha256,
        "homepage_targets_sha256": value.homepage_targets_sha256,
        "live_read": value.live_read,
        "packet_sha256": value.packet_sha256,
        "page_sitemap_sha256": value.page_sitemap_sha256,
        "post_id": value.post_id,
        "post_sitemap_sha256": value.post_sitemap_sha256,
        "production_evidence": value.production_evidence,
        "public_surface_sha256": value.public_surface_sha256,
        "public_surface_verified": value.public_surface_verified,
        "related_target_sha256": value.related_target_sha256,
        "publication_authority": False,
        "request_sha256": value.request_sha256,
        "response_sha256": value.response_sha256,
        "robots_sha256": value.robots_sha256,
        "sitemap_index_sha256": value.sitemap_index_sha256,
        "status": value.status,
        "target_public_post_id": value.target_public_post_id,
        "verified_checks": list(value.verified_checks),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="st1704_self_hosted_editorial_pilot.py",
        description=(
            "Prepare or owner-operate one allowlisted ST-1704 review draft. "
            "There is no publish, schedule, update, delete, media, taxonomy, "
            "theme, plugin, or generic HTTP command."
        ),
        allow_abbrev=False,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in COMMANDS:
        command = commands.add_parser(name, allow_abbrev=False)
        command.add_argument("--article-id", choices=ARTICLE_IDS, required=True)
    return parser


def _run(command: str, article_id: str) -> dict[str, object]:
    from raos.adapters.self_hosted_editorial_pilot_https import (
        OfficialSelfHostedEditorialPilotWordPressAdapter,
    )
    from raos.adapters.self_hosted_editorial_pilot_json import (
        OwnerPrivateLiveReviewDraftJournal,
    )
    from raos.application.editorial.self_hosted_editorial_pilot import (
        prepare_editorial_article,
    )
    from raos.domain.editorial.self_hosted_editorial_pilot import (
        EditorialPilotFailure,
    )

    try:
        if command == "prepare":
            prepared = prepare_editorial_article(REPOSITORY_ROOT, article_id)
            return _prepared_result(prepared)
        adapter = OfficialSelfHostedEditorialPilotWordPressAdapter(REPOSITORY_ROOT)
        journal = OwnerPrivateLiveReviewDraftJournal(REPOSITORY_ROOT, adapter)
        if command == "create-review-draft":
            prepared = prepare_editorial_article(REPOSITORY_ROOT, article_id)
            receipt = journal.create(prepared.request)
            return _receipt_result(command, receipt, prepared.request)
        if command == "recover-create-review-draft":
            persisted_request = journal.request_for_recovery(article_id)
            receipt = journal.recover(persisted_request)
            return _receipt_result(command, receipt, persisted_request)
        if command == "verify-public":
            persisted_request, expected_public_post_id = journal.committed_request(
                article_id
            )
            return _verification_result(
                adapter.verify_public(persisted_request, expected_public_post_id)
            )
        raise AssertionError("unreachable command")
    except EditorialPilotFailure as error:
        raise _CliRefusal(error.code.value) from None


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        result = _run(arguments.command, arguments.article_id)
    except _CliRefusal as error:
        _write_json(
            {
                "article_id": arguments.article_id,
                "command": arguments.command,
                "error": error.code,
                "production_evidence": False,
                "publication_authority": False,
                "status": "REFUSED",
            },
            target=sys.stderr,
        )
        return 1
    except Exception:
        _write_json(
            {
                "article_id": arguments.article_id,
                "command": arguments.command,
                "error": "SELF_HOSTED_EDITORIAL_PILOT_INTERNAL_FAILURE",
                "production_evidence": False,
                "publication_authority": False,
                "status": "REFUSED",
            },
            target=sys.stderr,
        )
        return 1
    _write_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

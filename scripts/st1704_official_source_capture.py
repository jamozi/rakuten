#!/usr/bin/env python3
"""Closed official-source capture CLI for the ST-1704 editorial pilot."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Final, TextIO


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
PYTHON_ROOT: Final = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

ARTICLE_IDS: Final = (
    "st1703-first-suitcase-comparison",
    "st1704-portable-power-station-guide",
    "st1704-anker-solix-c300-c800-c1000-differences",
    "st1704-countertop-dishwasher-for-small-households",
    "st1704-compact-robot-vacuum-shortlist",
)
SOURCE_REFS: Final = (
    "SRC-ACE-CRESTA-06316",
    "SRC-ACE-DIFFERENCE-05721",
    "SRC-ACE-MAXPASS4-01471",
    "SRC-ANA-CARRY-ON-BAGGAGE",
    "SRC-ANKER-SOLIX-C300",
    "SRC-JACKERY-500-NEW",
    "SRC-BLUETTI-AC70",
    "SRC-ECOFLOW-DELTA3-CLASSIC",
    "SRC-PANASONIC-NP-TMLK1",
    "SRC-THANKO-RAKUA-MINI-PLUS",
    "SRC-SIROCA-SS-MA251",
    "SRC-PANASONIC-NP-TSP1",
    "SRC-ANKER-SOLIX-C800-PLUS",
    "SRC-ANKER-SOLIX-C1000",
    "SRC-ANKER-SOLIX-C1000-GEN2",
    "SRC-IROBOT-ROOMBA-MINI-AUTOEMPTY",
    "SRC-SWITCHBOT-K11-PRO",
    "SRC-SWITCHBOT-K10-PRO-COMBO",
    "SRC-IROBOT-ROOMBA-PLUS-515-COMBO",
    "SRC-RAKUTEN-AFFILIATE-GUIDELINE",
    "SRC-CAA-STEALTH-MARKETING-QA",
    "SRC-GOOGLE-QUALIFY-OUTBOUND-LINKS",
)


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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="st1704_official_source_capture.py",
        description=(
            "Capture exact allowlisted official HTML sources with read-only HTTPS. "
            "There is no caller URL, credential, WordPress, Rakuten API, product "
            "retrieval, publication, plugin, theme, or generic HTTP capability."
        ),
        allow_abbrev=False,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    source = commands.add_parser("capture-source", allow_abbrev=False)
    source.add_argument("--source-ref", choices=SOURCE_REFS, required=True)
    article = commands.add_parser("capture-article", allow_abbrev=False)
    article.add_argument("--article-id", choices=ARTICLE_IDS, required=True)
    return parser


def _run(
    command: str, *, source_ref: str | None, article_id: str | None
) -> dict[str, object]:
    from raos.adapters.self_hosted_editorial_source_capture import (
        capture_article_sources,
        capture_source_ref,
    )

    if command == "capture-source" and source_ref in SOURCE_REFS and article_id is None:
        results = capture_source_ref(
            REPOSITORY_ROOT,
            source_ref=source_ref,
            clock=lambda: datetime.now(timezone.utc),
        )
    elif (
        command == "capture-article"
        and article_id in ARTICLE_IDS
        and source_ref is None
    ):
        results = capture_article_sources(
            REPOSITORY_ROOT,
            article_id=article_id,
            clock=lambda: datetime.now(timezone.utc),
        )
    else:
        raise AssertionError("unreachable closed command")
    return {
        "article_id": article_id,
        "command": command,
        "credentials_used": False,
        "network_requests": len(results),
        "production_evidence": False,
        "publication_authority": False,
        "results": [
            {
                "body_sha256": result.body_sha256,
                "request_count": result.request_count,
                "response_sha256": result.response_sha256,
                "retrieved_at": result.retrieved_at,
                "source_ref": result.source_ref,
                "status": result.status,
            }
            for result in results
        ],
        "source_ref": source_ref,
        "status": "CAPTURE_COMPLETED",
    }


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        result = _run(
            arguments.command,
            source_ref=getattr(arguments, "source_ref", None),
            article_id=getattr(arguments, "article_id", None),
        )
    except Exception as error:
        from raos.adapters.self_hosted_editorial_source_capture import (
            OfficialSourceCaptureFailure,
        )

        code = (
            error.code.value
            if type(error) is OfficialSourceCaptureFailure
            else "OFFICIAL_SOURCE_CAPTURE_INTERNAL_FAILURE"
        )
        _write_json(
            {
                "article_id": getattr(arguments, "article_id", None),
                "command": arguments.command,
                "credentials_used": False,
                "error": code,
                "production_evidence": False,
                "publication_authority": False,
                "source_ref": getattr(arguments, "source_ref", None),
                "status": "REFUSED",
            },
            target=sys.stderr,
        )
        return 1
    _write_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

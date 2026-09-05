#!/usr/bin/env python3
"""Regenerate the offline NOT_EXECUTED template, never review/publication evidence."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import wordpress_quality_audit_v1 as audit  # noqa: E402
from scripts.raos_build_core import atomic_write  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = Path(
    "changes/wordpress-quality-audit-v1/quality-audit-contract.v1.json"
)
AUDIT_SOURCE_PATH = Path("scripts/wordpress_quality_audit_v1.py")
OUTPUT_PATH = Path("changes/wordpress-quality-audit-v1/quality-audit-ledger.v1.json")
TEST_PATHS = (Path("tests/wordpress_quality_audit_v1"),)
# Preserve the pre-existing NOT_EXECUTED template anchor. Regeneration does not
# advance an observation, review or publication timestamp.
TEMPLATE_ANCHOR = "2026-09-05T13:22:38Z"


def render(root: Path = ROOT) -> bytes:
    contract, digest = audit.load_contract(root / CONTRACT_PATH)
    fingerprints = audit.repository_fingerprints(contract, root)
    value = audit.build_blocked_baseline(
        contract,
        digest,
        fingerprints,
        evaluated_at=datetime.fromisoformat(TEMPLATE_ANCHOR),
    )
    assert value["completion"]["status"] == "BLOCKED"
    assert set(value["external_execution"].values()) == {"NOT_EXECUTED"}
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    expected = render()
    if arguments.check:
        if (ROOT / OUTPUT_PATH).read_bytes() != expected:
            parser.exit(1, "blocked quality template drift; run make generate\n")
    else:
        atomic_write(OUTPUT_PATH, expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

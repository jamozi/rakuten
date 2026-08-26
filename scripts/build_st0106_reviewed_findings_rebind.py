#!/usr/bin/env python3
"""Refresh reviewed secret-finding coordinates without mutable source pins.

The reviewed line bytes remain the authority. Ordinary edits may change a
source file's size, digest, or the physical line number of an unchanged
reviewed false positive. New, removed, or changed findings fail closed.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
import hashlib
import json
from pathlib import Path
import sys
from typing import cast, Final


REPO_ROOT: Final = Path(__file__).resolve(strict=True).parents[1]
LEDGER_PATH: Final = Path(
    "changes/st-0106/contracts/reviewed-secret-findings.v3.yaml"
)
MANIFEST_PATH: Final = Path(
    "changes/st-0106/generated/reviewed-findings-rebind.v3.manifest.json"
)
OWNER_ID: Final = "build_st0106_reviewed_findings_rebind"
OWNER_VERSION: Final = 2

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import scan_secrets as scanner  # noqa: E402
from scripts.raos_build_core import atomic_write, canonical_json_bytes  # noqa: E402


class OwnerError(RuntimeError):
    """A closed, value-free refresh refusal."""


def _line_hash(data: bytes, line: int) -> str:
    lines = data.splitlines(keepends=True)
    if line < 1 or line > len(lines):
        raise OwnerError("REVIEWED_LINE_MISSING")
    return hashlib.sha256(lines[line - 1]).hexdigest()


def _load_ledger(data: bytes) -> dict[str, object]:
    try:
        scanner.parse_reviewed_findings(data)
        value: object = json.loads(data)
    except (UnicodeDecodeError, ValueError, scanner.ScanError):
        raise OwnerError("INVALID_REVIEWED_LEDGER") from None
    if type(value) is not dict:
        raise OwnerError("INVALID_REVIEWED_LEDGER")
    return cast(dict[str, object], value)


def _entries(document: Mapping[str, object]) -> list[dict[str, object]]:
    raw = document.get("entries")
    if type(raw) is not list:
        raise OwnerError("INVALID_REVIEWED_LEDGER")
    entries: list[dict[str, object]] = []
    for item in cast(list[object], raw):
        if type(item) is not dict:
            raise OwnerError("INVALID_REVIEWED_LEDGER")
        entries.append(dict(cast(dict[str, object], item)))
    return entries


def _current_generic_findings(data: bytes, source: str) -> list[tuple[int, str]]:
    findings = scanner.scan_payload(data, source, source)
    if any(finding.rule_id != scanner.RULE_GENERIC_CREDENTIAL for finding in findings):
        raise OwnerError("SPECIFIC_SECRET_FINDING_PRESENT")
    return sorted(
        (finding.line, _line_hash(data, finding.line)) for finding in findings
    )


def refresh_ledger(ledger_data: bytes, *, root: Path = REPO_ROOT) -> bytes:
    """Rebind unchanged reviewed lines to the current tracked source metadata."""

    document = _load_ledger(ledger_data)
    entries = _entries(document)
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for entry in entries:
        if entry.get("scope") == "worktree":
            source = entry.get("exact_source_identifier")
            if type(source) is not str:
                raise OwnerError("INVALID_REVIEWED_LEDGER")
            grouped[source].append(entry)

    for source, reviewed in grouped.items():
        try:
            data = scanner.read_maintained_file(root, source)
        except scanner.ScanError:
            raise OwnerError("REVIEWED_SOURCE_UNAVAILABLE") from None
        current = _current_generic_findings(data, source)
        current_hashes = Counter(line_hash for _, line_hash in current)
        reviewed_hashes = Counter(
            cast(str, entry.get("exact_line_sha256")) for entry in reviewed
        )
        if current_hashes != reviewed_hashes:
            raise OwnerError(f"REVIEWED_FINDING_SET_DRIFT:{source}")
        lines_by_hash: dict[str, list[int]] = defaultdict(list)
        entries_by_hash: dict[str, list[dict[str, object]]] = defaultdict(list)
        for line, line_hash in current:
            lines_by_hash[line_hash].append(line)
        for entry in reviewed:
            line_hash = entry.get("exact_line_sha256")
            if type(line_hash) is not str:
                raise OwnerError("INVALID_REVIEWED_LEDGER")
            entries_by_hash[line_hash].append(entry)
        source_hash = hashlib.sha256(data).hexdigest()
        for line_hash, matching_entries in entries_by_hash.items():
            matching_entries.sort(
                key=lambda entry: cast(int, entry["exact_line_number"])
            )
            for entry, line in zip(
                matching_entries, sorted(lines_by_hash[line_hash]), strict=True
            ):
                entry["exact_line_number"] = line
                entry["exact_source_bytes"] = len(data)
                entry["exact_source_sha256"] = source_hash

    entries.sort(
        key=lambda entry: (
            0 if entry.get("scope") == "worktree" else 1,
            cast(str, entry.get("exact_source_identifier")),
            cast(int, entry.get("exact_line_number")),
        )
    )
    document["entries"] = entries
    rendered = canonical_json_bytes(document)
    _load_ledger(rendered)
    return rendered


def render_manifest(ledger_data: bytes) -> bytes:
    document = _load_ledger(ledger_data)
    entries = _entries(document)
    return canonical_json_bytes(
        {
            "schema_version": 2,
            "owner": {"owner_id": OWNER_ID, "owner_version": OWNER_VERSION},
            "story_ids": ["ST-0106"],
            "semantic_inputs": [
                {
                    "uri": "repo://scripts/scan_secrets.py",
                    "semantic_id": "secret_scanner_interface",
                    "version": 2,
                },
                {
                    "semantic_id": "reviewed_false_positive_line_set",
                    "version": 2,
                    "entry_count": len(entries),
                },
            ],
            "output": {
                "uri": f"repo://{LEDGER_PATH.as_posix()}",
                "bytes": len(ledger_data),
                "sha256": hashlib.sha256(ledger_data).hexdigest(),
            },
            "external_operations": "NOT_RUN",
        }
    )


def build_outputs(root: Path = REPO_ROOT) -> tuple[Path, bytes, Path, bytes]:
    try:
        current = scanner.read_maintained_file(root, LEDGER_PATH.as_posix())
    except scanner.ScanError:
        raise OwnerError("REVIEWED_LEDGER_UNAVAILABLE") from None
    ledger = refresh_ledger(current, root=root)
    return root / LEDGER_PATH, ledger, root / MANIFEST_PATH, render_manifest(ledger)


def _check(path: Path, expected: bytes) -> None:
    try:
        current = path.read_bytes()
    except OSError:
        raise OwnerError("GENERATED_ARTIFACT_MISSING") from None
    if current != expected:
        raise OwnerError("GENERATED_ARTIFACT_DRIFT")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        ledger_path, ledger, manifest_path, manifest = build_outputs()
        if arguments.check:
            _check(ledger_path, ledger)
            _check(manifest_path, manifest)
            print("ST-0106 reviewed-finding refresh checked")
        else:
            atomic_write(ledger_path, ledger)
            atomic_write(manifest_path, manifest)
            print("ST-0106 reviewed-finding refresh generated")
        return 0
    except (OSError, OwnerError) as error:
        code = error.args[0] if error.args else type(error).__name__
        print(f"ST-0106 reviewed-finding refresh failed: {code}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

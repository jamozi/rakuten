"""Acceptance and hostile tests for the reviewed-finding refresh owner."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import cast

import pytest

from scripts import build_st0106_reviewed_findings_rebind as owner


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LEDGER_PATH = REPOSITORY_ROOT / owner.LEDGER_PATH
MANIFEST_PATH = REPOSITORY_ROOT / owner.MANIFEST_PATH


def _generic_line(value: str = "q7Vx-4mNz-8rTk-2sPw") -> bytes:
    return f'token = "{value}"\n'.encode("ascii")


def _ledger(source: str, data: bytes, line: int = 1) -> bytes:
    line_bytes = data.splitlines(keepends=True)[line - 1]
    return owner.canonical_json_bytes(
        {
            "version": 1,
            "status": "UNAPPROVED_CANDIDATE",
            "rule_id": "GENERIC_CREDENTIAL",
            "entries": [
                {
                    "scope": "worktree",
                    "exact_source_identifier": source,
                    "exact_line_number": line,
                    "exact_source_bytes": len(data),
                    "exact_source_sha256": hashlib.sha256(data).hexdigest(),
                    "exact_line_sha256": hashlib.sha256(line_bytes).hexdigest(),
                    "classification": "REVIEWED_FALSE_POSITIVE",
                    "rationale": scanner_rationale(),
                }
            ],
        }
    )


def scanner_rationale() -> str:
    return "Sanitized source location reviewed; no live credential is present."


def _first_entry(data: bytes) -> dict[str, object]:
    document = cast(dict[str, object], json.loads(data))
    entries = cast(list[dict[str, object]], document["entries"])
    return entries[0]


def test_owner_check_is_read_only_and_outputs_are_current() -> None:
    before = (LEDGER_PATH.read_bytes(), MANIFEST_PATH.read_bytes())
    result = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts/build_st0106_reviewed_findings_rebind.py"),
            "--check",
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "ST-0106 reviewed-finding refresh checked\n"
    assert (LEDGER_PATH.read_bytes(), MANIFEST_PATH.read_bytes()) == before


def test_manifest_v2_has_semantic_inputs_and_only_output_integrity() -> None:
    manifest = cast(dict[str, object], json.loads(MANIFEST_PATH.read_bytes()))
    assert manifest["schema_version"] == 2
    assert manifest["owner"] == {
        "owner_id": owner.OWNER_ID,
        "owner_version": owner.OWNER_VERSION,
    }
    assert manifest["story_ids"] == ["ST-0106"]
    semantic_inputs = cast(list[dict[str, object]], manifest["semantic_inputs"])
    assert semantic_inputs[0] == {
        "uri": "repo://scripts/scan_secrets.py",
        "semantic_id": "secret_scanner_interface",
        "version": 2,
    }
    assert all("sha256" not in row for row in semantic_inputs)
    output = cast(dict[str, object], manifest["output"])
    assert output["sha256"] == hashlib.sha256(LEDGER_PATH.read_bytes()).hexdigest()
    assert "command" not in json.dumps(manifest)
    assert "approval" not in json.dumps(manifest).lower()


def test_refresh_allows_unrelated_edits_and_line_movement(tmp_path: Path) -> None:
    source = "example.py"
    original = _generic_line()
    ledger = _ledger(source, original)
    moved = b"# ordinary edit\n" + original + b"result = 1\n"
    (tmp_path / source).write_bytes(moved)

    refreshed = owner.refresh_ledger(ledger, root=tmp_path)
    entry = _first_entry(refreshed)
    assert entry["exact_line_number"] == 2
    assert entry["exact_source_bytes"] == len(moved)
    assert entry["exact_source_sha256"] == hashlib.sha256(moved).hexdigest()
    assert entry["exact_line_sha256"] == hashlib.sha256(original).hexdigest()


def test_refresh_rejects_changed_or_added_generic_findings(tmp_path: Path) -> None:
    source = "example.py"
    original = _generic_line()
    ledger = _ledger(source, original)

    (tmp_path / source).write_bytes(_generic_line("r8Wy-5nPa-9sUl-3tQx"))
    with pytest.raises(owner.OwnerError, match="REVIEWED_FINDING_SET_DRIFT"):
        owner.refresh_ledger(ledger, root=tmp_path)

    (tmp_path / source).write_bytes(original + _generic_line("r8Wy-5nPa-9sUl-3tQx"))
    with pytest.raises(owner.OwnerError, match="REVIEWED_FINDING_SET_DRIFT"):
        owner.refresh_ledger(ledger, root=tmp_path)


def test_refresh_rejects_specific_secret_findings(tmp_path: Path) -> None:
    source = "example.py"
    original = _generic_line()
    ledger = _ledger(source, original)
    specific = b'marker = "' + b"AK" + b"IAA1B2C3D4E5F6G7H8" + b'"\n'
    (tmp_path / source).write_bytes(original + specific)

    with pytest.raises(owner.OwnerError, match="SPECIFIC_SECRET_FINDING_PRESENT"):
        owner.refresh_ledger(ledger, root=tmp_path)

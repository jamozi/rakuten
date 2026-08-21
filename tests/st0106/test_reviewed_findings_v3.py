"""Exact additive-ledger checks for the PR #106 sanitized findings."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import build_st0106_reviewed_secret_findings_v3 as generator
from scripts.scan_secrets import parse_reviewed_findings, scan_bytes


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def require_reviewed_history_objects() -> None:
    source = json.loads((REPOSITORY_ROOT / generator.SOURCE_PATH).read_bytes())
    try:
        for entry in source["entries"]:
            generator._git_blob(REPOSITORY_ROOT, entry["exact_source_identifier"])
    except RuntimeError:
        pytest.skip("exact reviewed Git objects are unavailable in this checkout")


def test_generated_v3_ledger_preserves_parent_and_adds_three_history_bindings() -> None:
    parent_bytes = (REPOSITORY_ROOT / generator.PARENT_LEDGER_PATH).read_bytes()
    source_bytes = (REPOSITORY_ROOT / generator.SOURCE_PATH).read_bytes()
    output_bytes = (REPOSITORY_ROOT / generator.OUTPUT_PATH).read_bytes()
    parent = json.loads(parent_bytes)
    source = json.loads(source_bytes)
    output = json.loads(output_bytes)

    assert len(parent_bytes) == generator.EXPECTED_PARENT_BYTES
    assert hashlib.sha256(parent_bytes).hexdigest() == generator.EXPECTED_PARENT_SHA256
    assert source["document"] == generator.EXPECTED_DOCUMENT
    assert source["review"] == generator.EXPECTED_REVIEW
    assert len(source["entries"]) == generator.EXPECTED_NEW_ENTRIES
    assert output["entries"][: generator.EXPECTED_PARENT_ENTRIES] == parent["entries"]
    additions = output["entries"][generator.EXPECTED_PARENT_ENTRIES :]
    assert len(additions) == generator.EXPECTED_NEW_ENTRIES
    assert all(entry["scope"] == "git_history" for entry in additions)
    assert sum(entry["scope"] == "worktree" for entry in output["entries"]) == 31
    assert sum(entry["scope"] == "git_history" for entry in output["entries"]) == 87
    assert len(parse_reviewed_findings(output_bytes)) == 118


def test_generator_reproduces_v3_when_exact_history_objects_are_available() -> None:
    require_reviewed_history_objects()
    output_bytes = (REPOSITORY_ROOT / generator.OUTPUT_PATH).read_bytes()
    assert generator.render(REPOSITORY_ROOT) == output_bytes


def test_v3_source_and_current_operator_have_no_sanitized_finding() -> None:
    for relative in (
        generator.SOURCE_PATH,
        generator.OUTPUT_PATH,
        generator.CURRENT_OPERATOR_PATH,
        Path("changes/st-0106/REVIEWED-SECRET-FINDINGS-ACTIVATION-v3.yaml"),
    ):
        content = (REPOSITORY_ROOT / relative).read_bytes()
        assert scan_bytes(content, relative.as_posix()) == set()


def test_generator_rejects_reviewed_blob_hash_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_reviewed_history_objects()
    original = generator._git_blob
    first_identifier = json.loads(
        (REPOSITORY_ROOT / generator.SOURCE_PATH).read_bytes()
    )["entries"][0]["exact_source_identifier"]

    def drifted_blob(root: Path, object_id: str) -> bytes:
        content = original(root, object_id)
        if object_id == first_identifier:
            return content + b"\n"
        return content

    monkeypatch.setattr(generator, "_git_blob", drifted_blob)
    with pytest.raises(RuntimeError, match="hash binding differs"):
        generator.render(REPOSITORY_ROOT)

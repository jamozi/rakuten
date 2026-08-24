"""Hostile tests for the ST-0106 reviewed-finding V3 owner."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import cast

import pytest

from scripts import build_st0106_reviewed_findings_rebind as owner


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
INPUT_PATH = REPOSITORY_ROOT / "changes/st-0106/reviewed-finding-source-rebind.v3.json"
V2_PATH = REPOSITORY_ROOT / "changes/st-0106/contracts/reviewed-secret-findings.v2.yaml"
V3_PATH = REPOSITORY_ROOT / "changes/st-0106/contracts/reviewed-secret-findings.v3.yaml"
MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "changes/st-0106/generated/reviewed-findings-rebind.v3.manifest.json"
)
SCANNER_PATH = REPOSITORY_ROOT / "scripts/scan_secrets.py"
SOURCE_PATH = REPOSITORY_ROOT / "tests/st1703/test_wordpresscom_review_draft_https.py"
TARGET_RELATIVE = "tests/st1703/test_wordpresscom_review_draft_https.py"
EXPECTED_V2_SHA256 = "667fee6720dad2e25e71220b2ec2fc8918a845ee30309c581f687ca87f51ca1b"
EXPECTED_V3_SHA256 = "d89b24ce08871fb92c126bf02662c6174448abd5a70a0d804ee531b78a4765a0"
EXPECTED_REVIEWED_LINE_SHA256 = (
    "e7ce26448515f4510b0f6165edeeb2cd464b8db7309504eb969193824b726293"
)


def _input_document() -> dict[str, object]:
    value: object = json.loads(INPUT_PATH.read_bytes())
    assert type(value) is dict
    return cast(dict[str, object], value)


def _policy() -> owner.RebindPolicy:
    return owner.parse_rebind_policy(_input_document())


def _git_blob(object_id: str) -> bytes:
    result = subprocess.run(
        ["/usr/bin/git", "cat-file", "blob", object_id],
        cwd=REPOSITORY_ROOT,
        env={
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": os.defpath,
        },
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    return result.stdout


def _entry(document: dict[str, object]) -> dict[str, object]:
    raw_entries = document["entries"]
    assert type(raw_entries) is list
    entries = cast(list[object], raw_entries)
    matches: list[dict[str, object]] = []
    for item in entries:
        if type(item) is not dict:
            continue
        candidate = cast(dict[str, object], item)
        if (
            candidate.get("scope") == "worktree"
            and candidate.get("exact_source_identifier") == TARGET_RELATIVE
            and candidate.get("exact_line_number") == 961
        ):
            matches.append(candidate)
    assert len(matches) == 1
    return matches[0]


def _replace_line(data: bytes, line: int, replacement: bytes) -> bytes:
    lines = data.splitlines(keepends=True)
    assert replacement.endswith(b"\n")
    lines[line - 1] = replacement
    return b"".join(lines)


def _policy_for_current(
    policy: owner.RebindPolicy, current_data: bytes
) -> owner.RebindPolicy:
    return dataclasses.replace(
        policy,
        current=owner.SourceVersion(
            size=len(current_data),
            sha256=hashlib.sha256(current_data).hexdigest(),
            blob_oid=policy.current.blob_oid,
        ),
        allowed_hunks=owner.observed_hunks(
            _git_blob(policy.prior.blob_oid), current_data
        ),
    )


def _minimal_ledger(entry: dict[str, object]) -> bytes:
    document = {
        "version": 1,
        "status": "UNAPPROVED_CANDIDATE",
        "rule_id": "GENERIC_CREDENTIAL",
        "entries": [entry],
    }
    return (json.dumps(document, ensure_ascii=True, indent=2) + "\n").encode("utf-8")


def _run_scanner(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-I",
            str(root / "scripts/scan_secrets.py"),
            "--worktree",
            "--reviewed-findings",
            "reviewed.yaml",
        ],
        cwd=root,
        env={"PATH": os.defpath},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


def _install_scanner_fixture(
    root: Path, source_data: bytes, entry: dict[str, object]
) -> None:
    scanner = root / "scripts/scan_secrets.py"
    scanner.parent.mkdir(parents=True)
    shutil.copyfile(SCANNER_PATH, scanner)
    source = root / TARGET_RELATIVE
    source.parent.mkdir(parents=True)
    source.write_bytes(source_data)
    (root / "reviewed.yaml").write_bytes(_minimal_ledger(entry))


def _rebind_entry(entry: dict[str, object], source_data: bytes) -> dict[str, object]:
    rebound = dict(entry)
    rebound["exact_source_bytes"] = len(source_data)
    rebound["exact_source_sha256"] = hashlib.sha256(source_data).hexdigest()
    return rebound


def test_owner_check_is_read_only_and_generated_outputs_are_exact() -> None:
    before = (V3_PATH.read_bytes(), MANIFEST_PATH.read_bytes())
    result = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts/build_st0106_reviewed_findings_rebind.py"),
            "--check",
        ],
        cwd=REPOSITORY_ROOT,
        env={"PATH": os.defpath},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "ST-0106 reviewed-finding rebind checked\n"
    assert result.stderr == ""
    assert (V3_PATH.read_bytes(), MANIFEST_PATH.read_bytes()) == before


def test_v3_changes_only_the_source_envelope_of_one_reviewed_entry() -> None:
    v2_data = V2_PATH.read_bytes()
    v3_data = V3_PATH.read_bytes()
    assert len(v2_data) == len(v3_data) == 59769
    assert hashlib.sha256(v2_data).hexdigest() == EXPECTED_V2_SHA256
    assert hashlib.sha256(v3_data).hexdigest() == EXPECTED_V3_SHA256
    v2 = cast(dict[str, object], json.loads(v2_data))
    v3 = cast(dict[str, object], json.loads(v3_data))
    assert set(v2) == set(v3) == {"version", "status", "rule_id", "entries"}
    assert v2["version"] == v3["version"] == 1
    assert v2["status"] == v3["status"] == "UNAPPROVED_CANDIDATE"
    assert v2["rule_id"] == v3["rule_id"] == "GENERIC_CREDENTIAL"
    v2_entries = cast(list[dict[str, object]], v2["entries"])
    v3_entries = cast(list[dict[str, object]], v3["entries"])
    assert len(v2_entries) == len(v3_entries) == 115

    changed = [
        (before, after)
        for before, after in zip(v2_entries, v3_entries, strict=True)
        if before != after
    ]
    assert len(changed) == 1
    before, after = changed[0]
    assert before == _entry(v2)
    assert after == _entry(v3)
    changed_keys = {key for key in before if before[key] != after[key]}
    assert changed_keys == {"exact_source_bytes", "exact_source_sha256"}
    assert before["exact_source_bytes"] == 33671
    assert after["exact_source_bytes"] == 33667
    assert before["exact_line_sha256"] == after["exact_line_sha256"]
    assert after["exact_line_sha256"] == EXPECTED_REVIEWED_LINE_SHA256
    assert before["classification"] == after["classification"]
    assert before["rationale"] == after["rationale"]


def test_manifest_binds_owner_inputs_and_keeps_formal_boundaries() -> None:
    manifest = cast(dict[str, object], json.loads(MANIFEST_PATH.read_bytes()))
    assert manifest["story_id"] == "ST-0106"
    assert manifest["status"] == ("LOCAL_RECONCILIATION_COMPLETE_NOT_FORMAL_EVIDENCE")
    owner_binding = cast(dict[str, object], manifest["owner"])
    input_bindings = cast(list[dict[str, object]], manifest["inputs"])
    for binding in [owner_binding, *input_bindings]:
        relative = binding["path"]
        expected_bytes = binding["bytes"]
        expected_sha256 = binding["sha256"]
        assert type(relative) is str
        assert type(expected_bytes) is int
        assert type(expected_sha256) is str
        path = REPOSITORY_ROOT / relative
        data = path.read_bytes()
        assert len(data) == expected_bytes
        assert hashlib.sha256(data).hexdigest() == expected_sha256
    generated = cast(dict[str, object], manifest["generated_ledger"])
    assert generated["path"] == V3_PATH.relative_to(REPOSITORY_ROOT).as_posix()
    assert generated["bytes"] == len(V3_PATH.read_bytes())
    assert generated["sha256"] == EXPECTED_V3_SHA256
    assert generated["changed_entry_count"] == 1
    assert generated["specific_rule_suppression"] == "FORBIDDEN"
    source = cast(dict[str, object], manifest["source_rebind"])
    assert source["reviewed_line"] == 961
    assert source["reviewed_line_sha256"] == EXPECTED_REVIEWED_LINE_SHA256
    assert source["sanitized_finding_set_unchanged"] is True
    assert source["specific_rule_findings"] == 0
    assert source["classification_change"] == "NONE"
    assert source["rationale_change"] == "NONE"
    boundaries = cast(dict[str, object], manifest["boundaries"])
    assert boundaries == {
        "scanner_semantic_change": "NONE",
        "historical_v1_v2_artifact_change": "NONE",
        "external_action": "NONE",
        "formal_tst_001": "NOT_EXECUTED",
        "formal_tst_002": "NOT_EXECUTED",
        "release_or_production": "NOT_AUTHORIZED",
    }


def test_owner_refuses_a_reviewed_line_change_even_with_rebound_source_hash() -> None:
    policy = _policy()
    prior = _git_blob(policy.prior.blob_oid)
    current = SOURCE_PATH.read_bytes()
    changed_line = ("    to" + "ken = object()\n").encode("ascii")
    mutated = _replace_line(current, policy.reviewed_line, changed_line)
    rebound = _policy_for_current(policy, mutated)

    with pytest.raises(owner.OwnerError, match="REVIEWED_LINE_DRIFT"):
        owner.reconcile_ledger(V2_PATH.read_bytes(), prior, mutated, rebound)


def test_owner_refuses_a_new_generic_finding_outside_the_reviewed_line() -> None:
    policy = _policy()
    prior = _git_blob(policy.prior.blob_oid)
    current = SOURCE_PATH.read_bytes()
    value = "q7Vx-4mNz-8rTk-2sPw"
    replacement = ("    api_" + 'key = "' + value + '"\n').encode("ascii")
    mutated = _replace_line(current, 967, replacement)
    rebound = _policy_for_current(policy, mutated)

    with pytest.raises(owner.OwnerError, match="CURRENT_FINDING_SET_DRIFT"):
        owner.reconcile_ledger(V2_PATH.read_bytes(), prior, mutated, rebound)


def test_v3_entry_cannot_suppress_new_generic_or_specific_findings(
    tmp_path: Path,
) -> None:
    current = SOURCE_PATH.read_bytes()
    v3_entry = _entry(json.loads(V3_PATH.read_bytes()))
    _install_scanner_fixture(tmp_path, current, v3_entry)
    baseline = _run_scanner(tmp_path)
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr

    generic_value = "q7Vx-4mNz-8rTk-2sPw"
    generic_line = ("    api_" + 'key = "' + generic_value + '"\n').encode("ascii")
    generic_source = _replace_line(current, 967, generic_line)
    (tmp_path / TARGET_RELATIVE).write_bytes(generic_source)
    (tmp_path / "reviewed.yaml").write_bytes(
        _minimal_ledger(_rebind_entry(v3_entry, generic_source))
    )
    generic = _run_scanner(tmp_path)
    assert generic.returncode == 1
    assert "rule=GENERIC_CREDENTIAL" in generic.stdout
    assert f' source="{TARGET_RELATIVE}" line=967' in generic.stdout
    assert generic_value not in generic.stdout + generic.stderr

    specific_value = "AK" + "IA" + "A1B2C3D4E5F6G7H8"
    specific_source = _replace_line(
        current, 967, ('    marker = "' + specific_value + '"\n').encode("ascii")
    )
    (tmp_path / TARGET_RELATIVE).write_bytes(specific_source)
    (tmp_path / "reviewed.yaml").write_bytes(
        _minimal_ledger(_rebind_entry(v3_entry, specific_source))
    )
    specific = _run_scanner(tmp_path)
    assert specific.returncode == 1
    assert "rule=AWS_ACCESS_KEY_ID" in specific.stdout
    assert specific_value not in specific.stdout + specific.stderr


def test_v3_entry_fails_closed_when_the_reviewed_line_changes(
    tmp_path: Path,
) -> None:
    current = SOURCE_PATH.read_bytes()
    v3_entry = _entry(json.loads(V3_PATH.read_bytes()))
    changed_line = ("    to" + "ken = object()\n").encode("ascii")
    mutated = _replace_line(current, 961, changed_line)
    _install_scanner_fixture(
        tmp_path,
        mutated,
        _rebind_entry(v3_entry, mutated),
    )

    result = _run_scanner(tmp_path)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "reviewed-finding-line-hash-drift" in result.stderr

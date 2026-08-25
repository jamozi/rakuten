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
EXPECTED_V3_SHA256 = "be150c6dafe3055385abf46978213537296dca6cf3000d9cc8382542bf013690"
EXPECTED_REVIEWED_LINE_SHA256 = (
    "e7ce26448515f4510b0f6165edeeb2cd464b8db7309504eb969193824b726293"
)
EXPECTED_HISTORY_OBJECT_ID = "90716c9c3d514d265c3c7463c8d71b172e43d951"
EXPECTED_HISTORY_SOURCE_SHA256 = (
    "19b37f2470e01a261336d501ce0ef9739efd18150b7e446fbdf04af39ed66dd0"
)
EXPECTED_HISTORY_LINE_SHA256 = (
    "2ac0364bcf02c18716c5518114835168d24c88eccf2aea3d6d0f18dfd4b880db"
)


def _input_document() -> dict[str, object]:
    value: object = json.loads(INPUT_PATH.read_bytes())
    assert type(value) is dict
    return cast(dict[str, object], value)


def _policy() -> owner.RebindPolicy:
    return owner.parse_rebind_policy(_input_document())


def _history_binding() -> owner.ReviewedHistoryBinding:
    bindings = owner.parse_reviewed_history_bindings(_input_document())
    assert len(bindings) == 1
    return bindings[0]


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


def _history_entry(document: dict[str, object]) -> dict[str, object]:
    raw_entries = document["entries"]
    assert type(raw_entries) is list
    entries = cast(list[object], raw_entries)
    matches: list[dict[str, object]] = []
    for item in entries:
        if type(item) is not dict:
            continue
        candidate = cast(dict[str, object], item)
        if (
            candidate.get("scope") == "git_history"
            and candidate.get("exact_source_identifier") == EXPECTED_HISTORY_OBJECT_ID
            and candidate.get("exact_line_number") == 193
        ):
            matches.append(candidate)
    assert len(matches) == 1
    return matches[0]


def _entry_key(entry: dict[str, object]) -> tuple[str, str, int]:
    scope = entry["scope"]
    identifier = entry["exact_source_identifier"]
    line = entry["exact_line_number"]
    assert type(scope) is str
    assert type(identifier) is str
    assert type(line) is int
    return scope, identifier, line


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


def test_v3_rebinds_worktree_and_projects_only_the_current_history_blob() -> None:
    v2_data = V2_PATH.read_bytes()
    v3_data = V3_PATH.read_bytes()
    assert len(v2_data) == 59769
    assert len(v3_data) == 60805
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
    assert len(v2_entries) == 115
    assert len(v3_entries) == 117
    v2_by_key = {_entry_key(entry): entry for entry in v2_entries}
    v3_by_key = {_entry_key(entry): entry for entry in v3_entries}
    assert not (set(v2_by_key) - set(v3_by_key))
    added_keys = set(v3_by_key) - set(v2_by_key)
    assert added_keys == {
        ("git_history", "8dcd2ab01f276a6dac924b42e733a827574c13ed", 961),
        ("git_history", EXPECTED_HISTORY_OBJECT_ID, 193),
    }
    changed_keys_by_entry = {
        key for key in v2_by_key if v2_by_key[key] != v3_by_key[key]
    }
    assert changed_keys_by_entry == {("worktree", TARGET_RELATIVE, 961)}
    before = v2_by_key[("worktree", TARGET_RELATIVE, 961)]
    after = v3_by_key[("worktree", TARGET_RELATIVE, 961)]
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

    projected = v3_by_key[
        ("git_history", "8dcd2ab01f276a6dac924b42e733a827574c13ed", 961)
    ]
    assert projected["exact_source_bytes"] == after["exact_source_bytes"]
    assert projected["exact_source_sha256"] == after["exact_source_sha256"]
    assert projected["exact_line_sha256"] == after["exact_line_sha256"]
    assert projected["classification"] == after["classification"]
    assert projected["rationale"] == after["rationale"]

    reviewed_history = v3_by_key[("git_history", EXPECTED_HISTORY_OBJECT_ID, 193)]
    assert reviewed_history == _history_entry(v3)
    assert reviewed_history["exact_source_bytes"] == 16883
    assert reviewed_history["exact_source_sha256"] == EXPECTED_HISTORY_SOURCE_SHA256
    assert reviewed_history["exact_line_sha256"] == EXPECTED_HISTORY_LINE_SHA256
    assert reviewed_history["classification"] == "REVIEWED_FALSE_POSITIVE"
    assert reviewed_history["rationale"] == owner.RATIONALE


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
    assert generated["entry_count"] == 117
    assert generated["changed_entry_count"] == 1
    assert generated["added_entry_count"] == 2
    assert generated["specific_rule_suppression"] == "FORBIDDEN"
    source = cast(dict[str, object], manifest["source_rebind"])
    assert source["reviewed_line"] == 961
    assert source["reviewed_line_sha256"] == EXPECTED_REVIEWED_LINE_SHA256
    assert source["sanitized_finding_set_unchanged"] is True
    assert source["specific_rule_findings"] == 0
    assert source["current_blob_history_projection_added"] is True
    assert source["classification_change"] == "NONE"
    assert source["rationale_change"] == "NONE"
    history_additions = cast(
        list[dict[str, object]], manifest["reviewed_history_additions"]
    )
    assert len(history_additions) == 1
    history = history_additions[0]
    assert history["scope"] == "git_history"
    assert history["exact_source_identifier"] == EXPECTED_HISTORY_OBJECT_ID
    assert history["exact_line_number"] == 193
    assert history["exact_source_bytes"] == 16883
    assert history["exact_source_sha256"] == EXPECTED_HISTORY_SOURCE_SHA256
    assert history["exact_line_sha256"] == EXPECTED_HISTORY_LINE_SHA256
    assert history["classification"] == "REVIEWED_FALSE_POSITIVE"
    assert history["rationale"] == owner.RATIONALE
    assert history["sanitized_finding_set"] == [
        {"line": 193, "rule_id": "GENERIC_CREDENTIAL"}
    ]
    assert history["specific_rule_findings"] == 0
    boundaries = cast(dict[str, object], manifest["boundaries"])
    assert boundaries == {
        "scanner_semantic_change": "NONE",
        "historical_v1_v2_artifact_change": "NONE",
        "external_action": "NONE",
        "formal_tst_001": "NOT_EXECUTED",
        "formal_tst_002": "NOT_EXECUTED",
        "release_or_production": "NOT_AUTHORIZED",
    }


def test_owner_accepts_only_the_exact_reviewed_history_binding() -> None:
    document = _input_document()
    raw_bindings = document["reviewed_history_additions"]
    assert type(raw_bindings) is list
    bindings = cast(list[object], raw_bindings)
    assert len(bindings) == 1
    raw_binding = bindings[0]
    assert type(raw_binding) is dict
    changed_binding = dict(cast(dict[str, object], raw_binding))
    changed_binding["exact_line_number"] = 194
    document["reviewed_history_additions"] = [changed_binding]

    with pytest.raises(owner.OwnerError, match="UNAUTHORIZED_REVIEWED_HISTORY_BINDING"):
        owner.parse_reviewed_history_bindings(document)


def test_reviewed_history_binding_is_hash_and_finding_set_bound() -> None:
    binding = _history_binding()
    data = _git_blob(binding.source_identifier)
    owner.validate_reviewed_history_binding(data, binding)

    source_drift = dataclasses.replace(binding, source_sha256="0" * 64)
    with pytest.raises(owner.OwnerError, match="REVIEWED_HISTORY_SOURCE_DRIFT"):
        owner.validate_reviewed_history_binding(data, source_drift)

    line_drift = dataclasses.replace(binding, line_sha256="0" * 64)
    with pytest.raises(owner.OwnerError, match="REVIEWED_HISTORY_LINE_DRIFT"):
        owner.validate_reviewed_history_binding(data, line_drift)

    specific_value = "AK" + "IA" + "A1B2C3D4E5F6G7H8"
    mutated = _replace_line(
        data,
        binding.line + 1,
        ('marker = "' + specific_value + '"\n').encode("ascii"),
    )
    rebound = dataclasses.replace(
        binding,
        source_bytes=len(mutated),
        source_sha256=hashlib.sha256(mutated).hexdigest(),
    )
    with pytest.raises(owner.OwnerError, match="REVIEWED_HISTORY_FINDING_SET_DRIFT"):
        owner.validate_reviewed_history_binding(mutated, rebound)


def test_reviewed_history_binding_cannot_be_appended_twice() -> None:
    with pytest.raises(
        owner.OwnerError, match="REVIEWED_HISTORY_ENTRY_ALREADY_PRESENT"
    ):
        owner.append_reviewed_history_bindings(
            V3_PATH.read_bytes(),
            (_history_binding(),),
            root=REPOSITORY_ROOT,
        )


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

"""Generation and atomic-publication tests for ST-1903."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts import build_st1903_autonomous_publication_policy as generator


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_build_outputs_is_deterministic_and_matches_contract(
    contract: dict[str, Any],
) -> None:
    """Repeated pure builds return byte-identical JSON and manifest output."""

    first = generator.build_outputs()
    second = generator.build_outputs()

    assert first == second
    assert json.loads(first[generator.OUTPUT_PATH]) == contract
    manifest = yaml.safe_load(first[generator.MANIFEST_PATH])
    assert manifest["classification"] == (
        "OWNER_APPROVED_INERT_NON_EXECUTABLE_NON_ATTESTING_POLICY_CANDIDATE_ONLY"
    )
    assert manifest["approval_target"]["sha256"] == generator.EXPECTED_HANDOFF_SHA256
    assert manifest["approval_target"]["source_internal_status"] == (
        "PENDING_OWNER_SHA256_APPROVAL"
    )
    assert manifest["approval_target"]["effective_detached_status"] == (
        "OWNER_APPROVED_INERT_POLICY_CANDIDATE_ONLY"
    )
    assert manifest["approval_target"]["approval_record"] == {
        "path": generator.APPROVAL_PATH.as_posix(),
        "bytes": generator.EXPECTED_APPROVAL_BYTES,
        "sha256": generator.EXPECTED_APPROVAL_SHA256,
        "approved_by": "repository_owner:jamozi",
    }
    assert manifest["boundary"] == {
        "canonical_mutation_authority": "NONE",
        "st_1805": "UNMET",
        "tst_032": "NOT_EXECUTED",
        "activation": "DISABLED",
        "canonical_reconciliation": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "release_authority": "NOT_AUTHORIZED",
        "publication": "NOT_EXECUTED",
        "publication_authority": "NOT_AUTHORIZED",
        "production": "NOT_EXECUTED",
        "production_authority": "NOT_AUTHORIZED",
        "pro_review": "REVIEW_NOT_OBTAINED",
        "actions": [],
        "effects": [],
        "evidence": [],
    }
    assert len(manifest["source_artifacts"]) == len(generator.SOURCE_ARTIFACT_PATHS)
    assert manifest["generated_artifacts"] == [
        {
            "path": generator.OUTPUT_PATH.as_posix(),
            "bytes": len(first[generator.OUTPUT_PATH]),
            "sha256": _digest(first[generator.OUTPUT_PATH]),
        }
    ]


def test_manifest_has_no_alias_anchor_tag_or_merge() -> None:
    """Manifest output must never use YAML identity or executable tag syntax."""

    rendered = generator.build_outputs()[generator.MANIFEST_PATH]
    text = rendered.decode("utf-8")
    assert "&id" not in text
    assert "*id" not in text
    assert "!!python" not in text
    assert "<<:" not in text


def test_check_mode_is_no_write() -> None:
    """The read-only drift gate leaves both generated files byte-identical."""

    before = {
        path: (generator.REPO_ROOT / path).read_bytes()
        for path in generator.GENERATED_PATHS
    }
    assert generator.main(["--check"]) == 0
    after = {
        path: (generator.REPO_ROOT / path).read_bytes()
        for path in generator.GENERATED_PATHS
    }
    assert after == before


@pytest.mark.parametrize("arguments", (["--chec"], ["--check", "--check"], ["extra"]))
def test_cli_accepts_only_no_argument_or_exact_check(arguments: list[str]) -> None:
    """CLI abbreviation, repetition, and unreviewed commands are rejected."""

    with pytest.raises(SystemExit) as captured:
        generator._parse_args(arguments)
    assert captured.value.code == 2


def test_atomic_install_restores_pair_when_second_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed second replacement restores both previous output bytes."""

    first = tmp_path / "generated.json"
    second = tmp_path / "manifest.yaml"
    first.write_bytes(b"previous-json\n")
    second.write_bytes(b"previous-manifest\n")
    first.chmod(0o600)
    second.chmod(0o640)
    original_replace = generator._replace_file
    replacement_count = 0

    def fail_second_replace(source: Path, target: Path) -> None:
        nonlocal replacement_count
        replacement_count += 1
        if replacement_count == 2:
            raise OSError("synthetic second replace failure")
        original_replace(source, target)

    monkeypatch.setattr(generator, "_replace_file", fail_second_replace)
    with pytest.raises(generator.BuildRefusal) as captured:
        generator._atomic_install({first: b"new-json\n", second: b"new-manifest\n"})

    assert captured.value.code == "OUTPUT_INSTALL_FAILED"
    assert first.read_bytes() == b"previous-json\n"
    assert second.read_bytes() == b"previous-manifest\n"
    assert stat_mode(first) == 0o600
    assert stat_mode(second) == 0o640
    assert not list(tmp_path.glob(".st1903-stage-*"))


def test_atomic_install_restores_first_output_after_directory_fsync_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A post-replace fsync failure also restores the previous output pair."""

    first = tmp_path / "generated.json"
    second = tmp_path / "manifest.yaml"
    first.write_bytes(b"previous-json\n")
    second.write_bytes(b"previous-manifest\n")
    original_fsync = generator._fsync_directory
    fsync_count = 0

    def fail_first_fsync(path: Path) -> None:
        nonlocal fsync_count
        fsync_count += 1
        if fsync_count == 1:
            raise generator.BuildRefusal("OUTPUT_INSTALL_FAILED")
        original_fsync(path)

    monkeypatch.setattr(generator, "_fsync_directory", fail_first_fsync)
    with pytest.raises(generator.BuildRefusal) as captured:
        generator._atomic_install({first: b"new-json\n", second: b"new-manifest\n"})

    assert captured.value.code == "OUTPUT_INSTALL_FAILED"
    assert first.read_bytes() == b"previous-json\n"
    assert second.read_bytes() == b"previous-manifest\n"
    assert not list(tmp_path.glob(".st1903-stage-*"))


def test_atomic_install_writes_both_outputs(tmp_path: Path) -> None:
    """A successful install publishes the complete pair and no stage files."""

    first = tmp_path / "generated.json"
    second = tmp_path / "manifest.yaml"
    generator._atomic_install({first: b"new-json\n", second: b"new-manifest\n"})
    assert first.read_bytes() == b"new-json\n"
    assert second.read_bytes() == b"new-manifest\n"
    assert not list(tmp_path.glob(".st1903-stage-*"))
    assert stat_mode(first) == 0o644


def test_check_rejects_generated_mode_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Byte-identical output with a changed mode is still generated drift."""

    output = tmp_path / "generated.json"
    output.write_bytes(b"expected\n")
    output.chmod(0o600)
    monkeypatch.setattr(generator, "REPO_ROOT", tmp_path)
    with pytest.raises(generator.BuildRefusal) as captured:
        generator.check_outputs({Path("generated.json"): b"expected\n"})
    assert captured.value.code == "GENERATED_MODE_DRIFT"


def stat_mode(path: Path) -> int:
    """Return permission bits without following links."""

    return os.stat(path, follow_symlinks=False).st_mode & 0o777

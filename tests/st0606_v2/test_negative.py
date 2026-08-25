from __future__ import annotations

# pyright: reportPrivateUsage=false

import json
from pathlib import Path
import shutil

import pytest

from scripts import build_st0606_evidence_workspace_v2 as builder


REPO_ROOT = Path(__file__).resolve().parents[2]


def _copy_inputs(destination: Path) -> None:
    paths = set(builder.OWNED_SOURCE_PATHS)
    paths.update(
        Path(uri.removeprefix("repo://")) for uri in builder.EXPECTED_SOURCE_BINDINGS
    )
    paths.update(
        Path(uri.removeprefix("repo://")) for uri in builder.EXPECTED_CANONICAL_BINDINGS
    )
    for relative in paths:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, target)


def test_st0605_attestation_subject_input_and_contract_mutations_fail_closed(
    tmp_path: Path,
) -> None:
    for field in ("subject_sha256", "input_sha256", "contract_sha256"):
        root = tmp_path / field
        _copy_inputs(root)
        upstream_path = root / builder.ST0605_FIXTURE_PATH
        upstream = json.loads(upstream_path.read_text(encoding="ascii"))
        upstream["attestations"][0][field] = "f" * 64
        upstream_path.write_text(json.dumps(upstream), encoding="ascii")
        fixture = builder._load_fixture(root)
        with pytest.raises(builder.EvidenceWorkspaceBuildError) as caught:
            builder._verify_evidence(root, fixture)
        assert "ST0605_REPORT_INVALID" in str(caught.value)
        assert "f" * 64 not in str(caught.value)


def test_st0604_unknown_count_cannot_be_coerced_to_zero(tmp_path: Path) -> None:
    _copy_inputs(tmp_path)
    lifecycle_path = tmp_path / builder.ST0604_LIFECYCLE_PATH
    lifecycle = json.loads(lifecycle_path.read_text(encoding="utf-8"))
    lifecycle["collection_boundary"]["packet_count"] = 0
    lifecycle_path.write_text(json.dumps(lifecycle), encoding="ascii")
    with pytest.raises(builder.EvidenceWorkspaceBuildError) as caught:
        builder._verify_lifecycle(tmp_path)
    assert "ST0604_SEMANTIC_DRIFT" in str(caught.value)


def test_duplicate_json_key_and_symlink_are_rejected(tmp_path: Path) -> None:
    _copy_inputs(tmp_path)
    fixture_path = tmp_path / builder.FIXTURE_PATH
    fixture_path.write_text('{"schema_version":2,"schema_version":2}', encoding="ascii")
    with pytest.raises(builder.EvidenceWorkspaceBuildError) as duplicate:
        builder._load_fixture(tmp_path)
    assert "JSON_DUPLICATE_KEY" in str(duplicate.value)

    root = tmp_path / "symlink-case"
    _copy_inputs(root)
    upstream_path = root / builder.ST0605_FIXTURE_PATH
    copy_path = upstream_path.with_suffix(".copy.json")
    shutil.copyfile(upstream_path, copy_path)
    upstream_path.unlink()
    upstream_path.symlink_to(copy_path.name)
    fixture = builder._load_fixture(root)
    with pytest.raises(builder.EvidenceWorkspaceBuildError) as symlink:
        builder._verify_evidence(root, fixture)
    assert "SYMLINK_REJECTED" in str(symlink.value)

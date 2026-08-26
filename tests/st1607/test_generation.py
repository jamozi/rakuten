from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts import build_st1607_gate_evidence_pack as builder

from .support import repository_copy


def test_generation_is_deterministic_and_check_is_read_only(tmp_path: Path) -> None:
    root = repository_copy(tmp_path)
    builder.build(root)
    before = {path: (root / path).read_bytes() for path in builder.GENERATED_PATHS}
    builder.build(root, check=True)
    assert before == {
        path: (root / path).read_bytes() for path in builder.GENERATED_PATHS
    }


def test_check_detects_output_drift(tmp_path: Path) -> None:
    root = repository_copy(tmp_path)
    builder.build(root)
    (root / builder.REPORT_PATH).write_text("{}\n")
    with pytest.raises(builder.GateEvidencePackError, match="GENERATED_OUTPUT_DRIFT"):
        builder.build(root, check=True)


def test_manifest_v2_contains_no_mutable_source_hash_or_authority() -> None:
    manifest = yaml.safe_load((builder.REPO_ROOT / builder.MANIFEST_PATH).read_text())
    assert manifest["manifest_version"] == 2
    assert manifest["generator"] == {
        "owner_id": builder.OWNER_ID,
        "owner_version": builder.OWNER_VERSION,
    }
    serialized = yaml.safe_dump(manifest)
    assert "approval" not in serialized
    assert "base_commit" not in serialized
    assert "generation_command" not in serialized


def test_normal_tracked_source_change_does_not_require_digest_rebind(
    tmp_path: Path,
) -> None:
    root = repository_copy(tmp_path)
    tracked = root / "changes/st-1603/contracts/security-verification-pack.v1.yaml"
    tracked.parent.mkdir(parents=True)
    tracked.write_text("semantic_version: 2\n")
    builder.build(root)
    tracked.write_text("semantic_version: 2\n# normal edit\n")
    builder.build(root, check=True)

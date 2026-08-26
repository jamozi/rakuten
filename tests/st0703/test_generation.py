"""Shared-runner generation checks for the ST-0703 recorded adapter."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

from .support import REPOSITORY_ROOT
from scripts import build_st0703_recorded_adapter as generator


def copy_inputs(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    contract = yaml.safe_load(
        (REPOSITORY_ROOT / generator.CONTRACT_PATH).read_text(encoding="utf-8")
    )
    paths = {
        generator.CONTRACT_PATH,
        generator.PYPROJECT_PATH,
        generator.UV_LOCK_PATH,
        generator.UV_CONFIG_PATH,
        *generator.IMPLEMENTATION_SOURCE_PATHS,
        *generator.PREDECESSOR_MANIFEST_PROJECTION_SHA256,
        *(generator.FIXTURE_ROOT / spec.path for spec in generator.FIXTURE_SPECS),
    }
    for entries in contract["provenance"].values():
        for entry in entries:
            paths.add(Path(entry["uri"].removeprefix("repo://")))
    for relative in paths:
        source = REPOSITORY_ROOT / relative
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return root


def test_real_repository_check_succeeds() -> None:
    digest = generator.check(REPOSITORY_ROOT)
    assert len(digest) == 64
    assert generator.check_installed(REPOSITORY_ROOT) == digest


def test_cli_check_is_read_only() -> None:
    paths = (generator.GENERATED_REGISTRY_PATH, generator.MANIFEST_PATH)
    before = {path: (REPOSITORY_ROOT / path).read_bytes() for path in paths}
    result = subprocess.run(
        [sys.executable, "scripts/build_st0703_recorded_adapter.py", "--check"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert {path: (REPOSITORY_ROOT / path).read_bytes() for path in paths} == before


def test_registry_uses_semantic_mutable_inputs_and_integrity_locks() -> None:
    registry = json.loads(generator.render_fixture_registry(REPOSITORY_ROOT))
    by_path = {item["path"]: item for item in registry["source_inputs"]}
    assert by_path["changes/st-0703/contracts/openai-responses-adapter.v1.yaml"] == {
        "path": "changes/st-0703/contracts/openai-responses-adapter.v1.yaml",
        "semantic_id": "openai-responses-adapter-contract",
        "version": 2,
    }
    assert "sha256" not in by_path["pyproject.toml"]
    assert "sha256" not in by_path["uv.toml"]
    assert len(by_path["uv.lock"]["sha256"]) == 64
    for item in registry["source_inputs"]:
        lowered = item["path"].lower()
        assert "handoff" not in lowered
        assert "approval" not in lowered
        assert "execplan" not in lowered


def test_predecessors_are_owner_version_bound() -> None:
    contract = yaml.safe_load(
        (REPOSITORY_ROOT / generator.CONTRACT_PATH).read_text(encoding="utf-8")
    )
    assert contract.get("implementation_authority") is None
    assert contract["provenance"]["predecessors"] == [
        {
            "story_id": "ST-0701",
            "owner_id": "build_st0701_ai_task_registry",
            "owner_version": 2,
            "uri": "repo://changes/st-0701/manifest.yaml",
        },
        {
            "story_id": "ST-0204",
            "owner_id": "build_st0204_config_loader",
            "owner_version": 2,
            "uri": "repo://changes/st-0204/manifest.yaml",
        },
    ]


def test_mutable_contract_comment_does_not_require_digest_rebinding(tmp_path: Path) -> None:
    root = copy_inputs(tmp_path)
    contract = root / generator.CONTRACT_PATH
    contract.write_bytes(contract.read_bytes() + b"\n# semantic no-op\n")
    assert len(generator.check(root)) == 64


def test_dependency_lock_drift_remains_rejected(tmp_path: Path) -> None:
    root = copy_inputs(tmp_path)
    lock = root / generator.UV_LOCK_PATH
    lock.write_bytes(lock.read_bytes() + b"\n")
    with pytest.raises(RuntimeError, match=r"uv\.lock hash drift"):
        generator.check(root)


def test_canonical_provenance_drift_remains_rejected(tmp_path: Path) -> None:
    root = copy_inputs(tmp_path)
    canonical = root / "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"
    canonical.chmod(0o644)
    canonical.write_bytes(canonical.read_bytes() + b"\n")
    with pytest.raises(RuntimeError, match="provenance source hash drift"):
        generator.check(root)


def test_manifest_excludes_commands_authority_and_mutable_source_hashes() -> None:
    manifest = yaml.safe_load(generator.render_manifest(REPOSITORY_ROOT))
    document = manifest["document"]
    assert document["generator_owner_id"] == "build_st0703_recorded_adapter"
    assert document["generator_owner_version"] == 2
    assert "generation_command" not in document
    provenance = manifest["provenance"]
    assert "handoff_uri" not in provenance
    assert "contract_sha256" not in provenance
    semantic_uris = {item["uri"] for item in manifest["semantic_sources"]}
    assert "repo://scripts/build_st0703_recorded_adapter.py" in semantic_uris


def test_story_specific_make_targets_are_retired() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    for target in (
        "openai-recorded-generate",
        "openai-recorded-check",
        "openai-recorded-static",
        "openai-recorded-test",
        "openai-recorded-gate",
    ):
        assert f"{target}:" not in makefile
    assert "scripts/raos_build.py $(BASE_ARGUMENT) generate" in makefile

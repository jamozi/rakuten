"""Deterministic generation tests for the ST-1703 low-cost pilot."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

import pytest
import yaml
from yaml.tokens import AliasToken, AnchorToken, TagToken

from scripts import build_st1703_low_cost_publication_pilot as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_rendered_outputs_match_committed_bytes() -> None:
    outputs = generator.render_outputs(REPOSITORY_ROOT)
    assert set(outputs) == set(generator.GENERATED_PATHS)
    for relative, expected in outputs.items():
        assert (REPOSITORY_ROOT / relative).read_bytes() == expected


def test_check_mode_is_read_only() -> None:
    paths = [REPOSITORY_ROOT / path for path in generator.GENERATED_PATHS]
    before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
    generator.build(REPOSITORY_ROOT, check=True)
    after = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
    assert after == before


def test_projection_remains_non_executable_and_non_attesting() -> None:
    document = generator.load_yaml(REPOSITORY_ROOT, generator.CONTRACT_PATH)
    assert document["action_boundary"] == {
        "external_actions": [],
        "provider_calls": [],
        "purchases": [],
        "credential_operations": [],
        "domain_operations": [],
        "draft_operations": [],
        "publication_operations": [],
        "staging_operations": [],
        "release_operations": [],
        "production_operations": [],
    }
    assert all(not value for value in document["effect_boundary"].values())
    assert document["evidence_records"] == []


def test_manifest_hashes_every_owned_source_and_generated_projection() -> None:
    manifest = yaml.safe_load((REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes())
    assert manifest["source_artifact_count"] == len(generator.SOURCE_PATHS)
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_PATHS
    ]
    for row in manifest["source_artifacts"]:
        content = (REPOSITORY_ROOT / row["uri"].removeprefix("repo://")).read_bytes()
        assert row["bytes"] == len(content)
        assert row["sha256"] == hashlib.sha256(content).hexdigest()
    helper = manifest["provenance"]["helper_integrity"]
    assert helper == next(
        row
        for row in manifest["source_artifacts"]
        if row["uri"] == f"repo://{generator.GENERATOR_PATH.as_posix()}"
    )
    projection = (REPOSITORY_ROOT / generator.OUTPUT_PATH).read_bytes()
    assert manifest["generated_artifacts"] == [
        {
            "uri": f"repo://{generator.OUTPUT_PATH.as_posix()}",
            "bytes": len(projection),
            "sha256": hashlib.sha256(projection).hexdigest(),
        }
    ]
    reconciliation = manifest["provenance"]["reconciliation_v2"]
    assert reconciliation["semantic_delta_from_approved_v1"] == "NONE"
    assert reconciliation["authority_inputs"] == [
        {
            "uri": f"repo://{path.as_posix()}",
            "bytes": byte_count,
            "sha256": digest,
        }
        for path, byte_count, digest in generator.V2_AUTHORITY_INPUTS
    ]
    assert reconciliation["historical_v1_runtime_manifest_binding"] == {
        "uri": f"repo://{generator.WAVE3_RUNTIME_MANIFEST_PATH.as_posix()}",
        "bytes": generator.HISTORICAL_WAVE3_RUNTIME_MANIFEST_BYTES,
        "sha256": generator.HISTORICAL_WAVE3_RUNTIME_MANIFEST_SHA256,
        "validation_source": "EXACT_FROZEN_V1_AUTHORITY_BYTES",
        "silent_repin": "FORBIDDEN",
        "git_object_as_current_filesystem_substitute": "FORBIDDEN",
    }
    assert reconciliation["current_wave3_runtime_manifest"] == {
        "uri": f"repo://{generator.WAVE3_RUNTIME_MANIFEST_PATH.as_posix()}",
        "bytes": generator.CURRENT_WAVE3_RUNTIME_MANIFEST_BYTES,
        "sha256": generator.CURRENT_WAVE3_RUNTIME_MANIFEST_SHA256,
        "validation_source": "EXACT_REGULAR_FILESYSTEM_FILE",
        "authority": "COMMITTED_RUNTIME_METADATA_ONLY",
        "formal_evidence": False,
    }
    assert reconciliation["superseded_v1_generated_manifest"] == {
        "uri": f"repo://{generator.MANIFEST_PATH.as_posix()}",
        "bytes": generator.SUPERSEDED_V1_MANIFEST_BYTES,
        "sha256": generator.SUPERSEDED_V1_MANIFEST_SHA256,
        "classification": "HISTORICAL_GENERATED_OUTPUT_NOT_FORMAL_EVIDENCE",
    }
    reconciliation_v3 = manifest["provenance"]["reconciliation_v3"]
    assert reconciliation_v3["semantic_delta_from_approved_v1"] == "NONE"
    assert reconciliation_v3["semantic_delta_from_approved_v2"] == "NONE"
    assert reconciliation_v3["authority"] == {
        "handoff": {
            "uri": f"repo://{generator.V3_HANDOFF_PATH.as_posix()}",
            "bytes": generator.V3_HANDOFF_BYTES,
            "sha256": generator.V3_HANDOFF_SHA256,
        },
        "approval": {
            "uri": f"repo://{generator.V3_APPROVAL_PATH.as_posix()}",
            "bytes": generator.V3_APPROVAL_BYTES,
            "sha256": generator.V3_APPROVAL_SHA256,
        },
        "target_branch": generator.V3_TARGET_BRANCH,
        "target_commit": generator.V3_TARGET_COMMIT,
        "target_tree": generator.V3_TARGET_TREE,
        "source_commit": generator.V3_SOURCE_COMMIT,
        "source_tree": generator.V3_SOURCE_TREE,
        "range_parent": generator.V3_RANGE_PARENT,
        "merge_base": generator.V3_MERGE_BASE,
        "range_patch_bytes": generator.V3_RANGE_PATCH_BYTES,
        "range_patch_sha256": generator.V3_RANGE_PATCH_SHA256,
        "range_inventory_bytes": generator.V3_RANGE_INVENTORY_BYTES,
        "range_inventory_sha256": generator.V3_RANGE_INVENTORY_SHA256,
    }
    assert reconciliation_v3["historical_runtime_manifest_bindings"] == {
        "v1": {
            "bytes": generator.HISTORICAL_WAVE3_RUNTIME_MANIFEST_BYTES,
            "sha256": generator.HISTORICAL_WAVE3_RUNTIME_MANIFEST_SHA256,
        },
        "v2": {
            "bytes": generator.CURRENT_WAVE3_RUNTIME_MANIFEST_BYTES,
            "sha256": generator.CURRENT_WAVE3_RUNTIME_MANIFEST_SHA256,
        },
        "silent_repin": "FORBIDDEN",
        "git_object_as_current_filesystem_substitute": "FORBIDDEN",
    }
    assert reconciliation_v3["current_wave3_runtime_manifest"] == {
        "uri": f"repo://{generator.WAVE3_RUNTIME_MANIFEST_PATH.as_posix()}",
        "bytes": generator.V3_CURRENT_WAVE3_RUNTIME_MANIFEST_BYTES,
        "sha256": generator.V3_CURRENT_WAVE3_RUNTIME_MANIFEST_SHA256,
        "validation_source": "EXACT_REGULAR_FILESYSTEM_FILE",
        "authority": "COMMITTED_RUNTIME_METADATA_ONLY",
        "formal_evidence": False,
    }
    assert reconciliation_v3["generated_projection"] == {
        "uri": f"repo://{generator.OUTPUT_PATH.as_posix()}",
        "bytes": generator.PROJECTION_BYTES,
        "sha256": generator.PROJECTION_SHA256,
        "mutation": "FORBIDDEN",
    }
    assert reconciliation_v3["external_authority"] == "NONE"
    assert reconciliation_v3["authority_inputs"] == [
        {
            "uri": f"repo://{path.as_posix()}",
            "bytes": byte_count,
            "sha256": digest,
        }
        for path, byte_count, digest in generator.V3_AUTHORITY_INPUTS
    ]
    assert manifest["provenance"]["authority_inputs"] == [
        {
            "uri": f"repo://{path.as_posix()}",
            "bytes": byte_count,
            "sha256": digest,
        }
        for path, byte_count, digest in generator.V3_CURRENT_AUTHORITY_INPUTS
    ]


def test_manifest_serialization_is_alias_anchor_and_tag_free() -> None:
    content = (REPOSITORY_ROOT / generator.MANIFEST_PATH).read_text(encoding="utf-8")
    tokens = tuple(yaml.scan(content))
    assert not any(
        isinstance(token, (AliasToken, AnchorToken, TagToken)) for token in tokens
    )


def _copy_inputs(destination: Path) -> None:
    paths = {
        generator.HANDOFF_PATH,
        generator.APPROVAL_PATH,
        generator.V2_HANDOFF_PATH,
        generator.V2_APPROVAL_PATH,
        generator.V3_HANDOFF_PATH,
        generator.V3_APPROVAL_PATH,
        generator.CONTRACT_PATH,
        generator.README_PATH,
        generator.GENERATOR_PATH,
        *generator.TEST_PATHS,
        *(path for path, _bytes, _digest in generator.AUTHORITY_INPUTS),
        *(path for path, _bytes, _digest in generator.V2_AUTHORITY_INPUTS),
        *(path for path, _bytes, _digest in generator.V3_AUTHORITY_INPUTS),
    }
    for relative in paths:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / relative, target)


def test_authority_source_or_helper_drift_fails_closed(tmp_path: Path) -> None:
    _copy_inputs(tmp_path)
    for relative in (
        generator.HANDOFF_PATH,
        generator.APPROVAL_PATH,
        generator.V2_HANDOFF_PATH,
        generator.V2_APPROVAL_PATH,
        generator.V3_HANDOFF_PATH,
        generator.V3_APPROVAL_PATH,
        generator.CONTRACT_PATH,
        generator.AUTHORITY_INPUTS[0][0],
        generator.AUTHORITY_INPUTS[-1][0],
        generator.V2_AUTHORITY_INPUTS[-2][0],
        generator.V3_AUTHORITY_INPUTS[-1][0],
    ):
        original = (tmp_path / relative).read_bytes()
        (tmp_path / relative).write_bytes(original + b"\n")
        with pytest.raises(generator.PilotContractError):
            generator.render_outputs(tmp_path)
        (tmp_path / relative).write_bytes(original)

    generator.build(tmp_path)
    helper = tmp_path / generator.GENERATOR_PATH
    helper.write_bytes(helper.read_bytes() + b"\n")
    with pytest.raises(generator.PilotContractError) as captured:
        generator.build(tmp_path, check=True)
    assert captured.value.code == "OUTPUT_DRIFT"


def test_v1_protected_artifacts_and_projection_remain_exact() -> None:
    expected = {
        generator.HANDOFF_PATH: (13776, generator.HANDOFF_SHA256),
        generator.APPROVAL_PATH: (2592, generator.APPROVAL_SHA256),
        generator.CONTRACT_PATH: (7525, generator.CONTRACT_SHA256),
        generator.V2_HANDOFF_PATH: (28414, generator.V2_HANDOFF_SHA256),
        generator.V2_APPROVAL_PATH: (3756, generator.V2_APPROVAL_SHA256),
        generator.V3_HANDOFF_PATH: (46856, generator.V3_HANDOFF_SHA256),
        generator.V3_APPROVAL_PATH: (3883, generator.V3_APPROVAL_SHA256),
        generator.OUTPUT_PATH: (
            generator.PROJECTION_BYTES,
            generator.PROJECTION_SHA256,
        ),
        Path(
            "changes/st-1703/low-cost-publication-pilot/CANONICAL-RECONCILIATION-v2.md"
        ): (
            2394,
            "710bbdd53cdc517d8ec7ac73ad77ead1b1f8ed5c58e1b2a26708400166bdd21e",
        ),
        Path("changes/st-1703/source-packet-candidate.first-article.v1.yaml"): (
            8116,
            "730de77b730afd692ca734746a7321d29a5191244832e4f44fb0d84a871707b2",
        ),
        Path("tests/st1703_low_cost/conftest.py"): (
            454,
            "6c9a3b846e574e61496c67f886b754c55eb39fbf5345849c869f7ae9f45b52a4",
        ),
        Path("tests/st1703_low_cost/test_contract.py"): (
            2959,
            "d1f845ab8d77b4f0b41ed93ae3bca3b2da9a55e5f2ea216af7b1d61ea86fb780",
        ),
    }
    for relative, identity in expected.items():
        content = (REPOSITORY_ROOT / relative).read_bytes()
        assert (len(content), hashlib.sha256(content).hexdigest()) == identity


def test_current_manifest_is_required_without_git_object_fallback(
    tmp_path: Path,
) -> None:
    _copy_inputs(tmp_path)
    current = tmp_path / generator.WAVE3_RUNTIME_MANIFEST_PATH
    current.unlink()
    with pytest.raises(generator.PilotContractError) as captured:
        generator.render_outputs(tmp_path)
    assert captured.value.code == "INPUT_INVALID"


def test_current_manifest_must_be_exact_regular_filesystem_file(
    tmp_path: Path,
) -> None:
    _copy_inputs(tmp_path)
    current = tmp_path / generator.WAVE3_RUNTIME_MANIFEST_PATH
    original = current.read_bytes()
    current.write_bytes(original + b"\n")
    with pytest.raises(generator.PilotContractError) as captured:
        generator.render_outputs(tmp_path)
    assert captured.value.code == "AUTHORITY_INPUT_DRIFT"

    current.unlink()
    outside = tmp_path / "manifest-outside.json"
    outside.write_bytes(original)
    current.symlink_to(outside)
    with pytest.raises(generator.PilotContractError) as captured:
        generator.render_outputs(tmp_path)
    assert captured.value.code == "UNSAFE_PATH"


def test_install_rolls_back_pair_when_second_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _copy_inputs(tmp_path)
    old = {
        path: f"old-{index}\n".encode()
        for index, path in enumerate(generator.GENERATED_PATHS)
    }
    for relative, content in old.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    outputs = generator.render_outputs(tmp_path)
    real_replace = os.replace
    call_count = 0

    def fail_second(source: Path, destination: Path) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("injected")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_second)
    with pytest.raises(generator.PilotContractError) as captured:
        generator.install_outputs(outputs, tmp_path)
    assert captured.value.code == "OUTPUT_WRITE_FAILED"
    assert {path: (tmp_path / path).read_bytes() for path in old} == old


def test_install_rolls_back_replaced_target_when_fsync_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _copy_inputs(tmp_path)
    old = {
        path: f"old-{index}\n".encode()
        for index, path in enumerate(generator.GENERATED_PATHS)
    }
    for relative, content in old.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    outputs = generator.render_outputs(tmp_path)
    real_fsync = generator._fsync_directory  # noqa: SLF001
    call_count = 0

    def fail_first_publish(path: Path) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise generator.PilotContractError("OUTPUT_WRITE_FAILED")
        real_fsync(path)

    monkeypatch.setattr(generator, "_fsync_directory", fail_first_publish)
    with pytest.raises(generator.PilotContractError) as captured:
        generator.install_outputs(outputs, tmp_path)
    assert captured.value.code == "OUTPUT_WRITE_FAILED"
    assert {path: (tmp_path / path).read_bytes() for path in old} == old


def test_output_ancestor_symlink_is_rejected_without_escape(tmp_path: Path) -> None:
    _copy_inputs(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    generated = tmp_path / generator.OUTPUT_PATH.parent
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.symlink_to(outside, target_is_directory=True)
    with pytest.raises(generator.PilotContractError) as captured:
        generator.install_outputs(generator.render_outputs(tmp_path), tmp_path)
    assert captured.value.code == "UNSAFE_OUTPUT_PATH"
    assert list(outside.iterdir()) == []

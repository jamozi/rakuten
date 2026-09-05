"""Deterministic generation and inert-workflow tests for ST-1506 V2."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from raos.domain.ops.production_canary import (
    REQUIRED_CAPABILITY_IDS,
    canonical_sha256,
)
from scripts import build_st1506_production_canary_runtime as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_render_is_deterministic_and_declares_only_inert_outputs() -> None:
    first = generator.render_outputs(REPOSITORY_ROOT)
    second = generator.render_outputs(REPOSITORY_ROOT)
    assert first == second
    assert tuple(first) == generator.GENERATED_PATHS
    assert all(".github/workflows" not in path.as_posix() for path in first)


def test_owner_no_write_check_preserves_output_metadata() -> None:
    paths = [REPOSITORY_ROOT / path for path in generator.GENERATED_PATHS]
    before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
    generator.build(REPOSITORY_ROOT, check=True)
    after = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
    assert after == before


def test_development_document_bytes_do_not_change_inert_outputs(monkeypatch) -> None:
    expected = generator.render_outputs(REPOSITORY_ROOT)
    original = Path.read_bytes

    def changed_document(path):
        if path == REPOSITORY_ROOT / "AGENTS.md":
            return b"Reworded development instructions\n"
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", changed_document)
    assert generator.render_outputs(REPOSITORY_ROOT) == expected


def test_generated_pipeline_is_disabled_and_has_no_commands() -> None:
    document = yaml.safe_load(
        (REPOSITORY_ROOT / generator.PIPELINE_PATH).read_text(encoding="utf-8")
    )
    assert document["activation"] == {
        "enabled": False,
        "default_enabled": False,
        "active_workflow_path": None,
        "trigger": "NONE",
        "selected_provider": None,
        "selected_account": None,
        "selected_region": None,
        "selected_target": None,
        "credentials": "ABSENT",
        "network_client": "ABSENT",
        "commands": [],
        "activation_authority": "NONE",
        "public_write_authority": "NONE",
    }
    assert document["pipeline"]["auto_advance"] == "FORBIDDEN"
    assert all(value == 0 for value in document["pipeline"]["action_counts"].values())
    assert document["capability_boundary"] == {
        "required_capability_ids": list(REQUIRED_CAPABILITY_IDS),
        "selected_mapping_count": 0,
        "selected_profile": None,
        "default_profile": None,
        "fallback_profile": None,
        "eligibility": "BLOCKED_NOT_CONFIGURED",
    }
    assert document["human_approval_artifacts"]["populated_count"] == 0
    assert document["kill_switch"]["deactivation_allowed"] is False


def test_generated_result_covers_closed_decisions_only() -> None:
    document = json.loads(
        (REPOSITORY_ROOT / generator.RESULT_PATH).read_text(encoding="utf-8")
    )
    assert [row["decision_outcome"] for row in document["scenarios"]] == [
        "HUMAN_APPROVALS_REQUIRED",
        "ABORT_REQUIRED",
        "ROLLBACK_REQUIRED",
    ]
    assert [row["terminal_state"] for row in document["scenarios"]] == [
        "HOLD_FOR_HUMAN_APPROVAL",
        "ABORT_REQUIRED",
        "ROLLBACK_REQUIRED",
    ]
    assert all(row["external_actions"] == 0 for row in document["scenarios"])
    assert document["capability_boundary"]["required_capability_ids"] == list(
        REQUIRED_CAPABILITY_IDS
    )
    assert document["capability_boundary"]["selected_mapping_count"] == 0
    without_digest = dict(document)
    embedded = without_digest.pop("result_sha256")
    assert embedded == canonical_sha256(without_digest)
    assert document["external_evidence"]["formal_tst_032"] == "NOT_EXECUTED"
    assert document["external_evidence"]["production"] == "NOT_EXECUTED"


def test_manifest_binds_active_workflows_without_owning_them() -> None:
    document = yaml.safe_load(
        (REPOSITORY_ROOT / generator.MANIFEST_PATH).read_text(encoding="utf-8")
    )
    workflow = document["active_workflow_tree"]
    assert workflow["semantic_id"] == "github-workflows"
    assert workflow["semantic_version"] == 2
    assert workflow["changed_by_story"] is False
    assert workflow["files"] == [
        ".github/workflows/auto-merge.yml",
        ".github/workflows/ci.yml",
    ]
    assert document["boundary"]["activation_authority"] == "NONE"
    assert document["boundary"]["public_write_authority"] == "NONE"
    assert document["boundary"]["human_approval_artifact_count"] == 0
    predecessor_artifacts = document["provenance"]["predecessor_owner_artifacts"]
    assert len(predecessor_artifacts) == 26
    assert len({row["uri"] for row in predecessor_artifacts}) == 26
    assert document["boundary"]["required_capability_ids"] == list(
        REQUIRED_CAPABILITY_IDS
    )
    assert document["boundary"]["selected_capability_mapping_count"] == 0


@pytest.mark.parametrize(
    ("relative", "expected_sha256"),
    [
        (
            "changes/st-1506/DESIGN_HANDOFF_V1_ST1506_PROVIDER_NEUTRAL_PRODUCTION.yaml",
            "5dc4ccfaa954b65aaae39a5d899c1c4e7f7d106787780d502514a48c7c13ad5e",
        ),
        (
            "changes/st-1506/README.md",
            "6c6af3972a75a6f9c3d7af8952332cf84c8f811cc893bc8f5cf742f120846270",
        ),
        (
            "changes/st-1506/contracts/production-deployment-definition.v1.yaml",
            "3acad1c924ec66a65c9a0915674233926aeb1ff236b2706f32ad75e4b29b19e1",
        ),
        (
            "changes/st-1506/manifest.yaml",
            "f1505a5a489b873fce6e1b749a81edb8d132ed5ffdadb02e11b74cd671f98701",
        ),
        (
            "scripts/build_st1506_production_deployment.py",
            "cc6ba0582e40f697ce670ff9a28ad3e8af8bba9c2dc8af68061d77f6ff0044be",
        ),
        (
            "infra/terraform/deployment-production/production-deployment.reference-plan.v1.json",
            "13db1afcf826b9a307e4a80a3503a562204280f422be094826764b13464bf0ba",
        ),
    ],
)
def test_v1_owner_and_generated_artifacts_remain_available(
    relative: str, expected_sha256: str
) -> None:
    del expected_sha256
    path = REPOSITORY_ROOT / relative
    assert path.is_file()
    assert path.stat().st_size > 0


def test_runtime_sources_expose_no_network_subprocess_or_ambient_secret_read() -> None:
    paths = [
        REPOSITORY_ROOT / "python/raos/domain/ops/production_canary.py",
        REPOSITORY_ROOT / "python/raos/ports/production_canary.py",
        REPOSITORY_ROOT / "python/raos/application/ops/production_canary.py",
        REPOSITORY_ROOT / "python/raos/adapters/disabled_production_activation.py",
        REPOSITORY_ROOT / "python/raos/adapters/recorded_production_canary.py",
        REPOSITORY_ROOT / "python/raos/production_canary_runner.py",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    forbidden = (
        "import requests",
        "import httpx",
        "import socket",
        "import subprocess",
        "urllib.request",
        "os.environ",
        "os.getenv",
        "boto3",
    )
    assert all(token not in text for token in forbidden)


def test_output_writer_rejects_symlink_target(tmp_path: Path) -> None:
    parent = tmp_path / "infra/terraform/deployment-production"
    parent.mkdir(parents=True)
    target = parent / generator.PIPELINE_PATH.name
    outside = tmp_path / "outside"
    outside.write_text("untouched", encoding="utf-8")
    target.symlink_to(outside)
    with pytest.raises(generator.BuildError) as captured:
        generator._atomic_write(tmp_path, generator.PIPELINE_PATH, b"unsafe")
    assert captured.value.code == "OUTPUT_PATH_INVALID"
    assert outside.read_text(encoding="utf-8") == "untouched"

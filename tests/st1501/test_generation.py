"""Deterministic generation and ownership tests for ST-1501."""

from __future__ import annotations

import ast
import stat
from pathlib import Path

import pytest
import yaml

from scripts import build_st1501_terraform_foundation as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _snapshot(paths: tuple[Path, ...]) -> dict[Path, tuple[bytes, int, int]]:
    return {
        path: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
        for path in paths
    }


def test_committed_outputs_match_deterministic_renderer() -> None:
    expected = generator.render_outputs(REPOSITORY_ROOT)
    assert set(expected) == set(generator.GENERATED_PATHS)
    for relative, content in expected.items():
        assert (REPOSITORY_ROOT / relative).read_bytes() == content
    assert generator.render_outputs(REPOSITORY_ROOT) == expected


def test_check_mode_is_read_only() -> None:
    paths = tuple(REPOSITORY_ROOT / path for path in generator.GENERATED_PATHS)
    before = _snapshot(paths)
    generator.build(REPOSITORY_ROOT, check=True)
    after = _snapshot(paths)
    assert after == before


def test_manifest_inventory_matches_owned_source_and_generated_bytes() -> None:
    manifest = yaml.safe_load((REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes())
    assert manifest["source_artifact_count"] == len(generator.SOURCE_ARTIFACT_PATHS)
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_ARTIFACT_PATHS
    ]
    for row in manifest["source_artifacts"]:
        path = REPOSITORY_ROOT / row["uri"].removeprefix("repo://")
        content = path.read_bytes()
        assert row["bytes"] == len(content)
        assert row["sha256"] == generator.sha256_bytes(content)

    assert manifest["generated_artifact_count"] == len(
        generator.GENERATED_ARTIFACT_PATHS
    )
    assert manifest["generated_artifacts"] == [
        {
            "uri": f"repo://{relative.as_posix()}",
            "bytes": (REPOSITORY_ROOT / relative).stat().st_size,
            "sha256": generator.sha256_file(REPOSITORY_ROOT / relative),
        }
        for relative in generator.GENERATED_ARTIFACT_PATHS
    ]


def test_manifest_pins_contract_authority_and_status_boundary() -> None:
    manifest = yaml.safe_load((REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes())
    assert manifest["document"] == {
        "id": "RAOS-TERRAFORM-FOUNDATION-MANIFEST-001",
        "version": "1.2.0",
        "story_id": "ST-1501",
        "source_contract": generator.SOURCE_CONTRACT_URI,
        "generated_by": generator.GENERATOR_URI,
        "generation_command": generator.GENERATION_COMMAND,
    }
    assert manifest["provenance"]["contract_sha256"] == generator.sha256_file(
        REPOSITORY_ROOT / generator.CONTRACT_PATH
    )
    assert manifest["provenance"]["authority_inputs"] == [
        {"uri": f"repo://{path}", "sha256": digest}
        for path, digest in generator.PINNED_SOURCES.items()
    ]
    assert manifest["boundary"] == {
        "classification": "SOURCE_DERIVED_PROVIDER_NEUTRAL_HCL_FOUNDATION",
        "provider_policy": "STRICT_PROVIDER_NEUTRAL_FOUNDATION_CAPABILITY_ADMISSION",
        "admission_status": "NOT_EVALUATED",
        "eligible": False,
        "selected_profile": None,
        "default_profile": None,
        "fallback_profile": None,
        "required_capability_count": 10,
        "configured_mapping_count": 0,
        "aws_reference_role": "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY",
        "canonical_story_deliverables": (
            "CANONICAL_STORY_DELIVERABLES_PRESERVED_NOT_ERASED_REPLACED_OR_COMPLETED"
        ),
        "portable_implementation_paths": "ADDITIONAL_PORTABLE_IMPLEMENTATION_PATHS",
        "aws_reference_default": False,
        "aws_reference_fallback": False,
        "aws_reference_selected": False,
        "aws_reference_eligibility_shortcut": False,
        "aws_reference_admission_requirement": False,
        "aws_reference_evidence_substitute": False,
        "activation": "DISABLED",
        "planned_actions": {"create": 0, "update": 0, "delete": 0},
        "selected_cloud_provider": None,
        "selected_production_region": None,
        "selected_production_account": None,
        "selected_state_backend": None,
        "credentials": "ABSENT",
        "provider_account_or_project": "UNSET",
        "resource_definitions": [],
        "hcl_module": "PROVIDER_NEUTRAL_VALIDATION_ONLY",
        "hcl_file_count": 5,
        "terraform_cli_version": "1.15.9",
        "terraform_binary_sha256": generator.TERRAFORM_BINARY_SHA256,
        "provider_plugins": [],
        "native_iac_validation": "EXECUTED_NOT_FORMAL",
        "normal_check_network": "FORBIDDEN",
        "initialization": "FORBIDDEN",
        "formal_tst_026": "NOT_EXECUTED",
        "effective_canonical_status": "UNCHANGED",
    }
    assert manifest["manifest_self_integrity"] == {
        "included_in_generated_artifacts": False,
        "verification": "deterministic byte-for-byte regeneration via --check",
    }
    assert all(
        row["uri"] != f"repo://{generator.MANIFEST_PATH.as_posix()}"
        for row in manifest["generated_artifacts"]
    )


def test_manifest_hash_pins_direct_owner_handoff() -> None:
    manifest = yaml.safe_load((REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes())
    handoff_uri = f"repo://{generator.DESIGN_HANDOFF_PATH.as_posix()}"
    assert {
        row["uri"]: row["sha256"] for row in manifest["provenance"]["authority_inputs"]
    }[handoff_uri] == generator.sha256_file(
        REPOSITORY_ROOT / generator.DESIGN_HANDOFF_PATH
    )
    assert handoff_uri in {row["uri"] for row in manifest["source_artifacts"]}


def test_check_rejects_drift_without_echoing_bytes(tmp_path: Path) -> None:
    outputs = generator.render_outputs(REPOSITORY_ROOT)
    for relative, content in outputs.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    marker = b"REJECTED_OUTPUT_MARKER_91e6"
    (tmp_path / generator.REFERENCE_PLAN_PATH).write_bytes(marker)
    with pytest.raises(generator.FoundationContractError) as captured:
        generator.check_outputs(tmp_path, outputs)
    assert captured.value.code == "GENERATED_OUTPUT_DRIFT"
    assert marker.decode("ascii") not in str(captured.value)


def test_check_rejects_symlinked_output_ancestor_without_path_escape(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "infra").symlink_to(outside, target_is_directory=True)
    expected = generator.render_outputs(REPOSITORY_ROOT)
    with pytest.raises(generator.FoundationContractError) as captured:
        generator.check_outputs(tmp_path, expected)
    assert captured.value.code == "UNSAFE_OUTPUT_ANCESTOR"
    assert list(outside.iterdir()) == []


def test_check_rejects_symlinked_output_file_without_reading_target(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.json"
    marker = b"OUTSIDE_MARKER_91e6"
    outside.write_bytes(marker)
    target = tmp_path / generator.REFERENCE_PLAN_PATH
    target.parent.mkdir(parents=True)
    target.symlink_to(outside)
    expected = generator.render_outputs(REPOSITORY_ROOT)
    with pytest.raises(generator.FoundationContractError) as captured:
        generator.check_outputs(tmp_path, expected)
    assert captured.value.code == "UNSAFE_FILE_TYPE"
    assert outside.read_bytes() == marker


def test_atomic_writer_replaces_only_fixed_regular_output(tmp_path: Path) -> None:
    first = b"first\n"
    second = b"second\n"
    generator._atomic_write(tmp_path, generator.REFERENCE_PLAN_PATH, first)
    generator._atomic_write(tmp_path, generator.REFERENCE_PLAN_PATH, second)
    target = tmp_path / generator.REFERENCE_PLAN_PATH
    assert target.read_bytes() == second
    assert stat.S_IMODE(target.stat().st_mode) == 0o644
    assert not list(target.parent.glob(f".{target.name}.*.tmp"))


def test_builder_has_no_provider_or_network_library_execution_surface() -> None:
    path = REPOSITORY_ROOT / "scripts/build_st1501_terraform_foundation.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    called_names: set[str] = set()
    called_attributes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_attributes.add(node.func.attr)

    assert imported_roots.isdisjoint(
        {"boto3", "botocore", "http", "requests", "socket", "urllib"}
    )
    assert "subprocess" in imported_roots
    assert called_names.isdisjoint({"eval", "exec", "compile"})
    assert called_attributes.isdisjoint(
        {
            "check_call",
            "check_output",
            "environ",
            "getenv",
            "popen",
            "spawn",
            "system",
        }
    )
    assert "run" in called_attributes

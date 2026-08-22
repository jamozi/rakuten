"""Deterministic generation and static safety tests for ST-1506."""

from __future__ import annotations

import ast
import stat
from pathlib import Path

import pytest
import yaml

from scripts import build_st1506_production_deployment as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PREDECESSOR_SOURCE_PATHS = (
    "changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml",
    "changes/st-1501/contracts/terraform-foundation.v1.yaml",
    "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json",
    "scripts/build_st1501_terraform_foundation.py",
    "changes/st-1502/DESIGN_HANDOFF_V1_ST1502_PROVIDER_NEUTRAL_DATA_SERVICES.yaml",
    "changes/st-1502/contracts/data-services-foundation.v1.yaml",
    "infra/terraform/data-services/data-services.reference-plan.v1.json",
    "scripts/build_st1502_data_services.py",
    "changes/st-1503/DESIGN_HANDOFF_V1_ST1503_PROVIDER_NEUTRAL_COMPUTE_EDGE.yaml",
    "changes/st-1503/contracts/compute-edge-foundation.v1.yaml",
    "infra/terraform/compute-edge/compute-edge.reference-plan.v1.json",
    "scripts/build_st1503_compute_edge.py",
    "changes/st-0107/contracts/pr-governance.v1.yaml",
    "changes/st-0107/ruleset-policy.v1.json",
    "changes/st-1504/"
    "DESIGN_HANDOFF_V1_ST1504_PROVIDER_NEUTRAL_DEPLOYMENT_IDENTITY.yaml",
    "changes/st-1504/contracts/github-oidc-deployment.v1.yaml",
    "infra/terraform/deployment-identity/github-oidc.reference-plan.v1.json",
    "scripts/build_st1504_github_oidc.py",
    "changes/st-1505/DESIGN_HANDOFF_V1_ST1505_PROVIDER_NEUTRAL_STAGING.yaml",
    "changes/st-1505/contracts/staging-deployment.v1.yaml",
    "infra/terraform/staging/staging-deployment.reference-plan.v1.json",
    "scripts/build_st1505_staging_deployment.py",
)


def _snapshot(paths: tuple[Path, ...]) -> dict[Path, tuple[bytes, int, int]]:
    return {
        path: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
        for path in paths
    }


def test_render_outputs_match_committed_bytes() -> None:
    outputs = generator.render_outputs(REPOSITORY_ROOT)
    assert set(outputs) == set(generator.GENERATED_PATHS)
    for relative, expected in outputs.items():
        assert (REPOSITORY_ROOT / relative).read_bytes() == expected


def test_check_is_read_only_on_success() -> None:
    paths = tuple(REPOSITORY_ROOT / path for path in generator.GENERATED_PATHS)
    before = _snapshot(paths)
    generator.build(REPOSITORY_ROOT, check=True)
    assert _snapshot(paths) == before


def test_manifest_inventory_hashes_and_boundary_are_complete() -> None:
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
    plan = REPOSITORY_ROOT / generator.REFERENCE_PLAN_PATH
    assert manifest["generated_artifacts"] == [
        {
            "uri": f"repo://{generator.REFERENCE_PLAN_PATH.as_posix()}",
            "bytes": plan.stat().st_size,
            "sha256": generator.sha256_file(plan),
        }
    ]
    boundary = manifest["boundary"]
    assert boundary["environment_label"] == "PRODUCTION"
    assert boundary["reference_region_metadata"] == "ap-northeast-1"
    assert boundary["reference_region_use"] == "METADATA_ONLY"
    assert boundary["apply_target"] is None
    assert boundary["activation"] == "DISABLED"
    assert boundary["approval_artifact_count"] == 0
    assert boundary["action_counts"] == {
        name: 0 for name in generator.ACTION_COUNT_NAMES
    }
    assert boundary["provider_policy"] == (
        "STRICT_PROVIDER_NEUTRAL_CAPABILITY_ADMISSION"
    )
    assert boundary["provider_admission_status"] == "NOT_EVALUATED"
    assert boundary["provider_eligible"] is False
    assert boundary["selected_profile"] is None
    assert boundary["default_profile"] is None
    assert boundary["fallback_profile"] is None
    assert boundary["required_capability_count"] == len(
        generator.REQUIRED_CAPABILITY_IDS
    )
    assert boundary["configured_capability_count"] == 0
    assert boundary["required_dependency_count"] == 5
    assert boundary["satisfied_dependency_count"] == 0
    assert boundary["complete_dependency_chain"] is False
    assert boundary["aws_reference_role"] == (
        "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY"
    )
    assert boundary["canonical_story_deliverables"] == (
        "CANONICAL_STORY_DELIVERABLES_PRESERVED_NOT_ERASED_REPLACED_OR_COMPLETED"
    )
    assert boundary["portable_implementation_paths"] == (
        "ADDITIONAL_PORTABLE_IMPLEMENTATION_PATHS"
    )
    assert boundary["aws_reference_default"] is False
    assert boundary["aws_reference_fallback"] is False
    assert boundary["aws_reference_eligibility_shortcut"] is False
    assert boundary["formal_tst_032"] == "NOT_EXECUTED"
    assert boundary["predecessor_dependency_admission"] == "NOT_EXECUTED"
    assert boundary["production_profile_admission"] == "NOT_EXECUTED"
    assert boundary["independent_migration_review"] == "NOT_EXECUTED"
    assert boundary["transport_security"] == "NOT_EXECUTED"
    assert boundary["production"] == "NOT_EXECUTED"


def test_manifest_pins_authority_and_all_five_direct_predecessor_chains() -> None:
    manifest = yaml.safe_load((REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes())
    assert manifest["provenance"]["authority_inputs"] == [
        {"uri": f"repo://{path}", "sha256": digest}
        for path, digest in generator.AUTHORITY_SOURCES.items()
    ]
    assert tuple(generator.PREDECESSOR_SOURCES) == PREDECESSOR_SOURCE_PATHS
    assert manifest["provenance"]["predecessor_inputs"] == [
        {"uri": f"repo://{path}", "sha256": digest}
        for path, digest in generator.PREDECESSOR_SOURCES.items()
    ]
    assert [
        row["uri"].removeprefix("repo://")
        for row in manifest["provenance"]["predecessor_inputs"]
    ] == list(PREDECESSOR_SOURCE_PATHS)
    assert manifest["provenance"]["authority_inputs"][-1] == {
        "uri": f"repo://{generator.DESIGN_HANDOFF_PATH.as_posix()}",
        "sha256": generator.sha256_file(
            REPOSITORY_ROOT / generator.DESIGN_HANDOFF_PATH
        ),
    }


def test_check_rejects_drift_without_writing_or_echoing_bytes(
    tmp_path: Path,
) -> None:
    outputs = generator.render_outputs(REPOSITORY_ROOT)
    for relative, content in outputs.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    marker = b"REJECTED_OUTPUT_MARKER_1506"
    target = tmp_path / generator.REFERENCE_PLAN_PATH
    target.write_bytes(marker)
    before = _snapshot(tuple(tmp_path / path for path in generator.GENERATED_PATHS))
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.check_outputs(tmp_path, outputs)
    assert captured.value.code == "GENERATED_OUTPUT_DRIFT"
    assert marker.decode("ascii") not in str(captured.value)
    assert (
        _snapshot(tuple(tmp_path / path for path in generator.GENERATED_PATHS))
        == before
    )


def test_check_rejects_missing_and_unsafe_outputs_without_escape(
    tmp_path: Path,
) -> None:
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.check_outputs(tmp_path, generator.render_outputs(REPOSITORY_ROOT))
    assert captured.value.code == "GENERATED_OUTPUT_MISSING"
    assert list(tmp_path.iterdir()) == []

    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "infra").symlink_to(outside, target_is_directory=True)
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.check_outputs(tmp_path, generator.render_outputs(REPOSITORY_ROOT))
    assert captured.value.code == "UNSAFE_OUTPUT_ANCESTOR"
    assert list(outside.iterdir()) == []


def test_atomic_writer_is_scoped_and_rejects_symlinks(tmp_path: Path) -> None:
    generator._atomic_write(tmp_path, generator.REFERENCE_PLAN_PATH, b"first\n")
    generator._atomic_write(tmp_path, generator.REFERENCE_PLAN_PATH, b"second\n")
    target = tmp_path / generator.REFERENCE_PLAN_PATH
    assert target.read_bytes() == b"second\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o644
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside")
    target.unlink()
    target.symlink_to(outside)
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator._atomic_write(tmp_path, generator.REFERENCE_PLAN_PATH, b"blocked\n")
    assert captured.value.code == "UNSAFE_FILE_TYPE"
    assert outside.read_bytes() == b"outside"
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator._atomic_write(tmp_path, Path("../escape"), b"blocked\n")
    assert captured.value.code == "UNSAFE_OUTPUT_PATH"


def test_builder_has_no_env_network_process_provider_or_deployment_surface() -> None:
    path = REPOSITORY_ROOT / "scripts/build_st1506_production_deployment.py"
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
        {
            "boto3",
            "botocore",
            "github",
            "http",
            "playwright",
            "requests",
            "selenium",
            "socket",
            "subprocess",
            "terraform",
            "urllib",
        }
    )
    assert called_names.isdisjoint({"eval", "exec", "compile"})
    assert called_attributes.isdisjoint(
        {
            "check_call",
            "check_output",
            "connect",
            "environ",
            "getenv",
            "popen",
            "run",
            "spawn",
            "system",
            "urlopen",
        }
    )


def test_cli_accepts_only_optional_exact_check() -> None:
    assert generator.parse_args([]).check is False
    assert generator.parse_args(["--check"]).check is True
    for arguments in (
        ["--chec"],
        ["--check", "--check"],
        ["--deploy"],
        ["--region", "ap-northeast-1"],
        ["--credential", "value"],
        ["--help"],
    ):
        with pytest.raises(SystemExit):
            generator.parse_args(arguments)


def test_owned_sources_contain_no_sensitive_material() -> None:
    forbidden = (
        "AK" + "IA",
        "BEGIN PRIVATE" + " KEY",
        "aws_secret" + "_access_key",
        "github" + "_token",
        ".secret" + "s/",
    )
    for relative in generator.SOURCE_ARTIFACT_PATHS:
        text = (REPOSITORY_ROOT / relative).read_text(encoding="utf-8")
        assert all(marker not in text for marker in forbidden)

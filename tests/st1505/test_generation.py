"""Deterministic provider-neutral generation and ownership tests for ST-1505."""

from __future__ import annotations

import ast
import stat
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from scripts import build_st1505_staging_deployment as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GENERATED_PATHS = (
    Path("infra/terraform/staging/staging-deployment.reference-plan.v1.json"),
    Path("changes/st-1505/manifest.yaml"),
)
SOURCE_ARTIFACT_PATHS = (
    Path("changes/st-1505/contracts/staging-deployment.v1.yaml"),
    Path("changes/st-1505/DESIGN_HANDOFF_V1_ST1505_PROVIDER_NEUTRAL_STAGING.yaml"),
    Path("changes/st-1505/README.md"),
    Path("scripts/build_st1505_staging_deployment.py"),
    Path("tests/st1505/conftest.py"),
    Path("tests/st1505/test_contract.py"),
    Path("tests/st1505/test_generation.py"),
    Path("tests/st1505/test_negative_cases.py"),
)
PREDECESSOR_INPUTS = (
    (
        "changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml",
        "cbbf28700a9ce019cb821bb4bfadf529393c8c948101b205d74be898c7599d7f",
    ),
    (
        "changes/st-1501/contracts/terraform-foundation.v1.yaml",
        "488281f5178250ce90d0f01548ffbc390fc023eae3e27ea04291a44f263399f9",
    ),
    (
        "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json",
        "a933f47a6c06c6b1d8d57dae84a815018bd00b3bc0d576a8e68fc11621c7ac70",
    ),
    (
        "scripts/build_st1501_terraform_foundation.py",
        "8c24545a0b992db2116e956b8ff0948066ca86b78026aa546417a6be025a9ec8",
    ),
    (
        "changes/st-1502/DESIGN_HANDOFF_V1_ST1502_PROVIDER_NEUTRAL_DATA_SERVICES.yaml",
        "ee41e5d240322e084b0a9a945ac8a06347267e55dd6552a5669772925c9497e5",
    ),
    (
        "changes/st-1502/contracts/data-services-foundation.v1.yaml",
        "bb5eefc8bc5cfa62905bf87436b457cfaf3d40ac16e1d285ffabb13c8c3e1041",
    ),
    (
        "infra/terraform/data-services/data-services.reference-plan.v1.json",
        "84868985990b42dfb6824887582be127962af480d9f48cf50fa103ad92e01699",
    ),
    (
        "scripts/build_st1502_data_services.py",
        "ba974d9d44c2184f6809ba68e14c8cd9df422573cd517dd957015e070932a6cf",
    ),
    (
        "changes/st-1503/DESIGN_HANDOFF_V1_ST1503_PROVIDER_NEUTRAL_COMPUTE_EDGE.yaml",
        "2a6da0fa771153cafe2aa79f01b09843832e032ec13a29dd34884a31ae0c519d",
    ),
    (
        "changes/st-1503/contracts/compute-edge-foundation.v1.yaml",
        "07e78229b21b181c951fa6c7f7fa9cf601b9118149f8162691189b3739d8dd60",
    ),
    (
        "infra/terraform/compute-edge/compute-edge.reference-plan.v1.json",
        "62d0d2975ebc28951340488eed2da3138b29729b56d7638290deda886651d4d8",
    ),
    (
        "scripts/build_st1503_compute_edge.py",
        "9c322273a8c9a1106ee777bc7747d519d059e719fb40a91d4333209e06e8361d",
    ),
    (
        "changes/st-0107/contracts/pr-governance.v1.yaml",
        "b387255fa65577051203b0fb1f935d5340c0d00f1285fd25557a38776fb07d92",
    ),
    (
        "changes/st-0107/ruleset-policy.v1.json",
        "e999838c2f592e3795aa79222bcfbc8cedf4b59bad06024f0328ebd65b3e11f5",
    ),
    (
        "changes/st-1504/"
        "DESIGN_HANDOFF_V1_ST1504_PROVIDER_NEUTRAL_DEPLOYMENT_IDENTITY.yaml",
        "36ac3095033f8ad7c91deac77f6a6689d354dc63dd46f03350e0bf68b3ccca04",
    ),
    (
        "changes/st-1504/contracts/github-oidc-deployment.v1.yaml",
        "c9b01688f58be30dd561b9845aef2d8725c35af3ea9ce50e187c1a0866da011b",
    ),
    (
        "infra/terraform/deployment-identity/github-oidc.reference-plan.v1.json",
        "1a929da93ef2610db8a0d8a147fe52e32b01ddb6f8989b06dc6cb8abd41003d4",
    ),
    (
        "scripts/build_st1504_github_oidc.py",
        "996176c1f977d39dd1dbb36fa7b1159c35f5fa1e5adacf7c21f1dc93919e248f",
    ),
)
ACTION_COUNT_NAMES = (
    "create",
    "update",
    "delete",
    "build",
    "promote",
    "approve",
    "deploy",
    "migrate",
    "migration_review",
    "smoke",
    "security",
    "runtime",
    "browser",
    "transport_security",
    "telemetry",
    "alert",
    "rollback",
    "restore",
    "release",
    "production",
)


def _snapshot(paths: tuple[Path, ...]) -> dict[Path, tuple[bytes, int, int]]:
    return {
        path: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
        for path in paths
    }


def _rendered_manifest() -> dict[str, Any]:
    rendered = generator.render_outputs(REPOSITORY_ROOT)[
        Path("changes/st-1505/manifest.yaml")
    ]
    document = yaml.safe_load(rendered)
    assert isinstance(document, dict)
    return cast(dict[str, Any], document)


def test_generator_inventory_is_literal_and_rendering_is_deterministic() -> None:
    assert generator.GENERATED_PATHS == GENERATED_PATHS
    assert generator.SOURCE_ARTIFACT_PATHS == SOURCE_ARTIFACT_PATHS
    first = generator.render_outputs(REPOSITORY_ROOT)
    second = generator.render_outputs(REPOSITORY_ROOT)
    assert tuple(first) == GENERATED_PATHS
    assert first == second


def test_render_outputs_match_committed_bytes() -> None:
    outputs = generator.render_outputs(REPOSITORY_ROOT)
    for relative, expected in outputs.items():
        target = REPOSITORY_ROOT / relative
        assert target.is_file()
        assert not target.is_symlink()
        assert target.read_bytes() == expected


def test_check_is_read_only() -> None:
    paths = tuple(REPOSITORY_ROOT / path for path in GENERATED_PATHS)
    before = _snapshot(paths)
    generator.build(REPOSITORY_ROOT, check=True)
    after = _snapshot(paths)
    assert after == before


def test_manifest_source_inventory_and_hashes_are_complete() -> None:
    manifest = _rendered_manifest()
    assert manifest["document"] == {
        "id": "RAOS-STAGING-DEPLOYMENT-MANIFEST-001",
        "version": "1.1.0",
        "story_id": "ST-1505",
        "source_contract": (
            "repo://changes/st-1505/contracts/staging-deployment.v1.yaml"
        ),
        "generated_by": "repo://scripts/build_st1505_staging_deployment.py",
        "generation_command": (
            "uv run --locked --no-sync python "
            "scripts/build_st1505_staging_deployment.py"
        ),
    }
    assert manifest["source_artifact_count"] == len(SOURCE_ARTIFACT_PATHS)
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in SOURCE_ARTIFACT_PATHS
    ]
    for row in manifest["source_artifacts"]:
        path = REPOSITORY_ROOT / row["uri"].removeprefix("repo://")
        content = path.read_bytes()
        assert row["bytes"] == len(content)
        assert row["sha256"] == generator.sha256_bytes(content)
    reference = generator.render_outputs(REPOSITORY_ROOT)[GENERATED_PATHS[0]]
    assert manifest["generated_artifact_count"] == 1
    assert manifest["generated_artifacts"] == [
        {
            "uri": f"repo://{GENERATED_PATHS[0].as_posix()}",
            "bytes": len(reference),
            "sha256": generator.sha256_bytes(reference),
        }
    ]
    assert manifest["manifest_self_integrity"] == {
        "included_in_generated_artifacts": False,
        "verification": "deterministic byte-for-byte regeneration via --check",
    }


def test_manifest_pins_direct_handoff_and_all_predecessor_inputs() -> None:
    manifest = _rendered_manifest()
    provenance = manifest["provenance"]
    contract_path = REPOSITORY_ROOT / SOURCE_ARTIFACT_PATHS[0]
    assert provenance["contract_uri"] == (
        "repo://changes/st-1505/contracts/staging-deployment.v1.yaml"
    )
    assert provenance["contract_sha256"] == generator.sha256_file(contract_path)
    assert provenance["authority_inputs"][-1] == {
        "uri": (
            "repo://changes/st-1505/"
            "DESIGN_HANDOFF_V1_ST1505_PROVIDER_NEUTRAL_STAGING.yaml"
        ),
        "sha256": ("5438a2971ab60472e5145a0af7f5c9be03b30463484a483d188b77e014d1c9b5"),
    }
    assert provenance["predecessor_inputs"] == [
        {"uri": f"repo://{path}", "sha256": digest}
        for path, digest in PREDECESSOR_INPUTS
    ]


def test_manifest_boundary_preserves_provider_neutral_fail_closed_status() -> None:
    boundary = _rendered_manifest()["boundary"]
    assert boundary["classification"] == (
        "SOURCE_DERIVED_NON_EXECUTABLE_PROVIDER_NEUTRAL_STAGING_ADMISSION_"
        "REFERENCE_PLAN"
    )
    assert boundary["environment_label"] == "STAGING"
    assert boundary["configuration_status"] == "NOT_CONFIGURED"
    assert boundary["activation"] == "DISABLED"
    assert boundary["provider_policy"] == (
        "STRICT_PROVIDER_NEUTRAL_STAGING_CAPABILITY_AND_DEPENDENCY_ADMISSION"
    )
    assert boundary["admission_status"] == "NOT_EVALUATED"
    assert boundary["eligible"] is False
    assert boundary["configured_mapping_count"] == 0
    assert boundary["required_capability_count"] == 13
    assert boundary["required_dependency_count"] == 4
    assert boundary["satisfied_dependency_count"] == 0
    assert boundary["action_counts"] == {name: 0 for name in ACTION_COUNT_NAMES}

    for field in (
        "selected_profile_id",
        "selected_profile_kind",
        "selected_provider",
        "default_profile_id",
        "fallback_profile_id",
        "selected_account_project_or_tenant",
        "selected_region",
        "selected_backend",
        "selected_identity",
        "selected_adapter",
        "selected_repository",
        "selected_environment",
        "selected_artifact",
    ):
        assert boundary[field] is None

    assert boundary["aws_reference_only"] is True
    assert boundary["aws_reference_role"] == (
        "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY"
    )
    assert boundary["canonical_story_deliverables"] == (
        "CANONICAL_STORY_DELIVERABLES_PRESERVED_NOT_ERASED_REPLACED_OR_COMPLETED"
    )
    assert boundary["portable_implementation_paths"] == (
        "ADDITIONAL_PORTABLE_IMPLEMENTATION_PATHS"
    )
    for field in (
        "aws_reference_default",
        "aws_reference_implicit_fallback",
        "aws_reference_selected_binding",
        "aws_reference_eligibility_shortcut",
        "aws_reference_admission_requirement",
        "aws_reference_evidence_substitute",
    ):
        assert boundary[field] is False
    assert boundary["credentials"] == "ABSENT"
    for field in (
        "predecessor_dependency_admission",
        "target_profile_admission",
        "build_sbom_scan_provenance",
        "protected_environment_approval",
        "formal_tst_009",
        "formal_tst_022",
        "migration_database",
        "independent_migration_review",
        "smoke_security_runtime",
        "transport_security",
        "observability_alerting",
        "rollback_restore",
        "hosted_ci",
        "live_provider",
        "staging",
        "release",
        "production",
    ):
        assert boundary[field] == "NOT_EXECUTED"
    assert boundary["effective_canonical_status"] == "UNCHANGED"


def test_check_rejects_drift_without_echoing_bytes(tmp_path: Path) -> None:
    outputs = generator.render_outputs(REPOSITORY_ROOT)
    for relative, content in outputs.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    marker = b"REJECTED_OUTPUT_MARKER_1505"
    (tmp_path / GENERATED_PATHS[0]).write_bytes(marker)
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator.check_outputs(tmp_path, outputs)
    assert captured.value.code == "GENERATED_OUTPUT_DRIFT"
    assert marker.decode("ascii") not in str(captured.value)


def test_check_rejects_missing_output_without_creating_directories(
    tmp_path: Path,
) -> None:
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator.check_outputs(tmp_path, generator.render_outputs(REPOSITORY_ROOT))
    assert captured.value.code == "GENERATED_OUTPUT_MISSING"
    assert list(tmp_path.iterdir()) == []


def test_check_rejects_symlinked_output_ancestor_without_escape(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "infra").symlink_to(outside, target_is_directory=True)
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator.check_outputs(tmp_path, generator.render_outputs(REPOSITORY_ROOT))
    assert captured.value.code == "UNSAFE_OUTPUT_ANCESTOR"
    assert list(outside.iterdir()) == []


def test_check_rejects_symlinked_output_file_without_reading_target(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.json"
    marker = b"OUTSIDE_MARKER_1505"
    outside.write_bytes(marker)
    target = tmp_path / GENERATED_PATHS[0]
    target.parent.mkdir(parents=True)
    target.symlink_to(outside)
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator.check_outputs(tmp_path, generator.render_outputs(REPOSITORY_ROOT))
    assert captured.value.code == "UNSAFE_FILE_TYPE"
    assert outside.read_bytes() == marker


def test_atomic_writer_replaces_only_fixed_regular_output(tmp_path: Path) -> None:
    generator._atomic_write(tmp_path, GENERATED_PATHS[0], b"first\n")
    generator._atomic_write(tmp_path, GENERATED_PATHS[0], b"second\n")
    target = tmp_path / GENERATED_PATHS[0]
    assert target.read_bytes() == b"second\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o644
    assert not list(target.parent.glob(f".{target.name}.*.tmp"))


def test_atomic_writer_rejects_symlink_target_without_touching_outside(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.json"
    marker = b"OUTSIDE_WRITE_MARKER_1505"
    outside.write_bytes(marker)
    target = tmp_path / GENERATED_PATHS[0]
    target.parent.mkdir(parents=True)
    target.symlink_to(outside)
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator._atomic_write(tmp_path, GENERATED_PATHS[0], b"blocked\n")
    assert captured.value.code == "UNSAFE_FILE_TYPE"
    assert outside.read_bytes() == marker


def test_output_path_escape_and_symlinked_repository_root_are_rejected(
    tmp_path: Path,
) -> None:
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator._atomic_write(tmp_path, Path("../escape"), b"blocked\n")
    assert captured.value.code == "UNSAFE_OUTPUT_PATH"
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "root-link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator._atomic_write(link, GENERATED_PATHS[0], b"blocked\n")
    assert captured.value.code == "UNSAFE_ROOT_TYPE"


def test_owned_artifacts_have_no_workflow_or_executable_deployment_surface() -> None:
    staging = REPOSITORY_ROOT / "infra/terraform/staging"
    story = REPOSITORY_ROOT / "changes/st-1505"
    assert sorted(path.name for path in staging.iterdir()) == [
        "staging-deployment.reference-plan.v1.json"
    ]
    assert sorted(
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in story.rglob("*")
        if path.is_file()
    ) == [
        "changes/st-1505/DESIGN_HANDOFF_V1_ST1505_PROVIDER_NEUTRAL_STAGING.yaml",
        "changes/st-1505/README.md",
        "changes/st-1505/contracts/staging-deployment.v1.yaml",
        "changes/st-1505/manifest.yaml",
    ]
    assert not any(
        path.is_file() and path.suffix in {".tf", ".tfvars", ".hcl", ".sh", ".yml"}
        for directory in (staging, story)
        for path in directory.rglob("*")
    )
    assert not any(
        path.is_file() and path.stat().st_mode & 0o111
        for directory in (staging, story)
        for path in directory.rglob("*")
    )
    workflows = REPOSITORY_ROOT / ".github/workflows"
    assert not any(
        "st1505" in path.name.lower() or "st-1505" in path.name.lower()
        for path in workflows.iterdir()
        if path.is_file()
    )


def test_builder_has_no_external_runtime_or_ambient_configuration_surface() -> None:
    path = REPOSITORY_ROOT / "scripts/build_st1505_staging_deployment.py"
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
            "pulumi",
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


def test_builder_cli_exposes_only_generation_and_read_only_check() -> None:
    assert generator.parse_args([]).check is False
    assert generator.parse_args(["--check"]).check is True
    with pytest.raises(SystemExit):
        generator.parse_args(["--deploy"])
    source = (REPOSITORY_ROOT / "scripts/build_st1505_staging_deployment.py").read_text(
        encoding="utf-8"
    )
    for forbidden_option in (
        "--provider",
        "--account",
        "--region",
        "--repository",
        "--environment",
        "--role",
        "--credential",
        "--artifact",
        "--release",
        "--migration",
        "--domain",
        "--url",
        "--browser",
        "--rollback",
        "--deploy",
        "--apply",
    ):
        assert forbidden_option not in source

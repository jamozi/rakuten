"""Deterministic generation and boundary checks for ST-1603."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from scripts import build_st1603_security_verification_pack as generator
from scripts import build_st1506_production_deployment as base_generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _snapshot(paths: tuple[Path, ...]) -> dict[Path, tuple[bytes, int, int]]:
    return {
        path: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
        for path in paths
    }


def test_rendered_outputs_match_owner_generated_bytes() -> None:
    outputs = generator.render_outputs(REPOSITORY_ROOT)
    assert set(outputs) == set(generator.GENERATED_PATHS)
    for relative, expected in outputs.items():
        assert (REPOSITORY_ROOT / relative).read_bytes() == expected


def test_check_mode_is_read_only() -> None:
    paths = tuple(REPOSITORY_ROOT / path for path in generator.GENERATED_PATHS)
    before = _snapshot(paths)
    generator.build(REPOSITORY_ROOT, check=True)
    assert _snapshot(paths) == before


def test_check_rejects_symlinked_output_ancestor_without_escape(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "changes").symlink_to(outside, target_is_directory=True)
    with pytest.raises(base_generator.ProductionDeploymentContractError) as captured:
        generator.check_outputs(
            tmp_path,
            generator.render_outputs(REPOSITORY_ROOT),
        )
    assert captured.value.code == "UNSAFE_OUTPUT_ANCESTOR"
    assert list(outside.iterdir()) == []


def test_generated_plan_and_manifest_preserve_non_attesting_truth() -> None:
    plan = json.loads((REPOSITORY_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes())
    manifest = yaml.safe_load((REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes())
    assert plan["classification"] == (
        "SOURCE_DERIVED_NON_ATTESTING_SECURITY_VERIFICATION_REFERENCE_PLAN"
    )
    assert plan["executable"] is False
    assert len(plan["catalog_projection"]["controls"]) == 83
    assert plan["catalog_projection"]["verification_coverage"] == "0/83"
    assert plan["findings"]["open_critical"] is None
    assert plan["findings"]["open_high"] is None
    assert plan["evidence"]["collection_status"] == "NOT_EXECUTED"
    assert plan["decision"] == "NOT_READY"
    boundary = manifest["boundary"]
    assert boundary["projected_controls"] == 83
    assert boundary["verified_controls"] == 0
    assert boundary["open_critical"] is None
    assert boundary["open_high"] is None
    assert boundary["st_1607_eligible"] is False
    assert boundary["release_eligible"] is False


def test_manifest_inventory_hashes_every_owned_source_and_generated_plan() -> None:
    manifest = yaml.safe_load((REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes())
    assert manifest["source_artifact_count"] == len(generator.SOURCE_PATHS)
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_PATHS
    ]
    for row in manifest["source_artifacts"]:
        content = (REPOSITORY_ROOT / row["uri"].removeprefix("repo://")).read_bytes()
        assert row["bytes"] == len(content)
        assert row["sha256"] == hashlib.sha256(content).hexdigest()
    plan = (REPOSITORY_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    assert manifest["generated_artifacts"] == [
        {
            "uri": f"repo://{generator.REFERENCE_PLAN_PATH.as_posix()}",
            "bytes": len(plan),
            "sha256": hashlib.sha256(plan).hexdigest(),
        }
    ]
    assert manifest["provenance"]["implementation_inputs"] == [
        {"uri": f"repo://{path}", "sha256": digest}
        for path, digest in generator.EXPECTED_IMPLEMENTATION_DEPENDENCY_HASHES.items()
    ]
    current = manifest["provenance"]["current_development_rebinding"]
    assert current["authority_source"] == {
        "uri": f"repo://{generator.STANDING_DEVELOPMENT_AUTHORITY_PATH}",
        "bytes": generator.STANDING_DEVELOPMENT_AUTHORITY_BYTES,
        "sha256": generator.STANDING_DEVELOPMENT_AUTHORITY_SHA256,
        "authority": "ROOT_STANDING_DEVELOPMENT_AUTHORIZATION",
    }
    assert current["current_authority_inputs"] == [
        {
            "uri": f"repo://{path}",
            "bytes": binding[0],
            "sha256": binding[1],
        }
        for path, binding in generator.CURRENT_DEVELOPMENT_SOURCE_OVERRIDES.items()
    ]
    assert current["current_predecessor_inputs"] == [
        {
            "uri": f"repo://{path}",
            "bytes": binding[0],
            "sha256": binding[1],
        }
        for path, binding in (
            generator.CURRENT_DEVELOPMENT_PREDECESSOR_OVERRIDES.items()
        )
    ]
    assert current["historical_source_and_predecessor_rows_preserved"] is True
    assert current["semantic_delta_from_security_interface"] == "NONE"
    for field in (
        "external_authority",
        "live_provider_authority",
        "credential_authority",
        "publication_authority",
        "release_authority",
        "production_authority",
    ):
        assert current[field] == "NONE"


@pytest.mark.parametrize("target_kind", ("symlink", "directory"))
def test_check_rejects_unsafe_output_leaf_without_escape(
    tmp_path: Path, target_kind: str
) -> None:
    expected = generator.render_outputs(REPOSITORY_ROOT)
    for relative, content in expected.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    target = tmp_path / generator.REFERENCE_PLAN_PATH
    target.unlink()
    if target_kind == "symlink":
        outside = tmp_path / "outside"
        outside.write_bytes(b"outside")
        target.symlink_to(outside)
    else:
        target.mkdir()
    with pytest.raises(base_generator.ProductionDeploymentContractError) as captured:
        generator.check_outputs(tmp_path, expected)
    assert captured.value.code == "UNSAFE_FILE_TYPE"


def test_imported_local_builder_dependency_is_hash_bound() -> None:
    for (
        relative,
        expected,
    ) in generator.EXPECTED_IMPLEMENTATION_DEPENDENCY_HASHES.items():
        content = (REPOSITORY_ROOT / relative).read_bytes()
        assert hashlib.sha256(content).hexdigest() == expected


def test_builder_has_no_scan_network_environment_or_process_surface() -> None:
    tree = ast.parse(
        (REPOSITORY_ROOT / generator.GENERATOR_PATH).read_text(encoding="utf-8")
    )
    imports: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    assert imports.isdisjoint(
        {
            "boto3",
            "botocore",
            "github",
            "http",
            "os",
            "playwright",
            "requests",
            "socket",
            "subprocess",
            "urllib",
        }
    )
    assert calls.isdisjoint(
        {
            "connect",
            "environ",
            "getenv",
            "popen",
            "run",
            "scan",
            "system",
            "urlopen",
        }
    )


def test_cli_accepts_only_no_argument_or_exact_check() -> None:
    assert generator.parse_args([]).check is False
    assert generator.parse_args(["--check"]).check is True
    for arguments in (
        ["--chec"],
        ["--check", "--check"],
        ["--scan"],
        ["--credential", "value"],
        ["--deploy"],
    ):
        with pytest.raises(SystemExit):
            generator.parse_args(arguments)


def test_owned_sources_do_not_contain_credential_material() -> None:
    forbidden = (
        "AK" + "IA",
        "BEGIN PRIVATE" + " KEY",
        "aws_secret" + "_access_key",
        "github" + "_token",
        ".secret" + "s/",
    )
    for relative in generator.SOURCE_PATHS:
        text = (REPOSITORY_ROOT / relative).read_text(encoding="utf-8")
        assert all(marker not in text for marker in forbidden)

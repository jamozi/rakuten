"""Deterministic generation and prohibited-surface tests for ST-1701."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from scripts import build_st1506_production_deployment as base_generator
from scripts import build_st1701_business_inputs as generator


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
    paths = tuple(REPOSITORY_ROOT / relative for relative in generator.GENERATED_PATHS)
    before = _snapshot(paths)
    generator.build(REPOSITORY_ROOT, check=True)
    assert _snapshot(paths) == before


def test_check_rejects_symlinked_output_ancestor_without_escape(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "changes").symlink_to(outside, target_is_directory=True)
    with pytest.raises(base_generator.ProductionDeploymentContractError) as captured:
        generator.check_outputs(tmp_path, generator.render_outputs(REPOSITORY_ROOT))
    assert captured.value.code == "UNSAFE_OUTPUT_ANCESTOR"
    assert list(outside.iterdir()) == []


def test_generated_registry_and_manifest_preserve_unresolved_truth() -> None:
    registry = json.loads((REPOSITORY_ROOT / generator.REFERENCE_PATH).read_bytes())
    manifest = yaml.safe_load((REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes())
    assert registry["document"]["authority"] == "NON_AUTHORITATIVE"
    assert registry["document"]["executable"] is False
    assert registry["document"]["canonical_acceptance_achieved"] is False
    assert registry["registry"]["resolved_count"] == 0
    assert registry["registry"]["global_unresolved_blocker_count"] == 14
    assert registry["activation"]["status"] == "BLOCKED_UNRESOLVED_INPUTS"
    assert registry["evidence_boundary"]["formal_tst_032"] == "NOT_EXECUTED"
    boundary = manifest["boundary"]
    assert boundary["resolved_count"] == 0
    assert boundary["active_blocker_count"] == 7
    assert boundary["st_1701_acceptance_achieved"] is False
    assert boundary["st_1702_ready"] is False
    assert boundary["production_ready"] is False


def test_manifest_hashes_all_owned_sources_and_generated_registry() -> None:
    manifest = yaml.safe_load((REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes())
    assert manifest["source_artifact_count"] == len(generator.SOURCE_PATHS)
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_PATHS
    ]
    for row in manifest["source_artifacts"]:
        content = (REPOSITORY_ROOT / row["uri"].removeprefix("repo://")).read_bytes()
        assert row["bytes"] == len(content)
        assert row["sha256"] == hashlib.sha256(content).hexdigest()
    content = (REPOSITORY_ROOT / generator.REFERENCE_PATH).read_bytes()
    assert manifest["generated_artifacts"] == [
        {
            "uri": f"repo://{generator.REFERENCE_PATH.as_posix()}",
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    ]


def test_builder_has_no_external_value_or_approval_surface() -> None:
    tree = ast.parse((REPOSITORY_ROOT / generator.GENERATOR_PATH).read_text())
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
            "http",
            "os",
            "playwright",
            "requests",
            "socket",
            "sqlite3",
            "subprocess",
            "urllib",
        }
    )
    assert calls.isdisjoint(
        {"connect", "environ", "getenv", "popen", "run", "system", "urlopen"}
    )


def test_cli_accepts_only_no_argument_or_exact_check() -> None:
    assert generator.parse_args([]).check is False
    assert generator.parse_args(["--check"]).check is True
    for arguments in (
        ["--chec"],
        ["--check", "--check"],
        ["--resolve", "OD-001"],
        ["--value", "anything"],
        ["--approve"],
        ["--publish"],
    ):
        with pytest.raises(SystemExit):
            generator.parse_args(arguments)

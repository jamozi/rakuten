"""Hostile trust-boundary tests for the ST-1205 owner builder."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import stat
from typing import Any

import pytest
import yaml

from conftest import REPOSITORY_ROOT
from scripts import build_st1205_kpi_read_model_reference_plan as builder
from scripts.build_st1505_staging_deployment import StagingDeploymentContractError


def _rewrite_contract(root: Path, value: dict[str, Any]) -> str:
    content = yaml.safe_dump(value, sort_keys=False, allow_unicode=True).encode()
    (root / builder.CONTRACT_PATH).write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _rebind_artifact(
    artifacts: tuple[tuple[Path, str], ...],
    target: Path,
    digest: str,
) -> tuple[tuple[Path, str], ...]:
    return tuple((path, digest if path == target else old) for path, old in artifacts)


@pytest.mark.parametrize(
    ("section", "key"),
    [
        ("document", "decision"),
        ("authority", "authority_kind"),
        ("catalog_projection", "definition_count"),
        ("calculation_boundary", "calculation_version"),
        ("execution_boundary", "formula_engine"),
        ("verification_boundary", "story_acceptance"),
    ],
)
def test_missing_contract_key_is_rejected(
    isolated_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    section: str,
    key: str,
) -> None:
    contract = yaml.safe_load((isolated_root / builder.CONTRACT_PATH).read_text())
    del contract[section][key]
    monkeypatch.setattr(
        builder, "EXPECTED_CONTRACT_SHA256", _rewrite_contract(isolated_root, contract)
    )
    with pytest.raises((builder.KpiReferencePlanError, StagingDeploymentContractError)):
        builder.load_contract(isolated_root)


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("document", "executable", 0),
        ("document", "story_acceptance", 0),
        ("catalog_projection", "definition_count", True),
        ("catalog_projection", "calculation_count", False),
        ("calculation_boundary", "empty_means_zero", 0),
        ("execution_boundary", "action_counts", []),
        ("verification_boundary", "calculations_completed", False),
    ],
)
def test_exact_types_reject_bool_integer_and_container_bypass(
    isolated_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    section: str,
    key: str,
    value: object,
) -> None:
    contract = yaml.safe_load((isolated_root / builder.CONTRACT_PATH).read_text())
    contract[section][key] = value
    monkeypatch.setattr(
        builder, "EXPECTED_CONTRACT_SHA256", _rewrite_contract(isolated_root, contract)
    )
    with pytest.raises((builder.KpiReferencePlanError, StagingDeploymentContractError)):
        builder.load_contract(isolated_root)


def test_unknown_contract_key_is_rejected(
    isolated_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = yaml.safe_load((isolated_root / builder.CONTRACT_PATH).read_text())
    contract["document"]["unexpected"] = "SECRET_CANARY_ST1205"
    monkeypatch.setattr(
        builder, "EXPECTED_CONTRACT_SHA256", _rewrite_contract(isolated_root, contract)
    )
    with pytest.raises(builder.KpiReferencePlanError) as captured:
        builder.load_contract(isolated_root)
    assert "SECRET_CANARY" not in str(captured.value)


@pytest.mark.parametrize(
    "payload",
    [
        "document: &x {schema_version: 1.0.0}\nauthority: *x\n",
        "document:\n  schema_version: 1.0.0\n  schema_version: 2.0.0\n",
        "document:\n  <<: {schema_version: 1.0.0}\n",
        "document: !unsafe value\n",
    ],
)
def test_yaml_alias_duplicate_merge_and_tag_are_rejected(
    isolated_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: str,
) -> None:
    content = payload.encode()
    (isolated_root / builder.CONTRACT_PATH).write_bytes(content)
    monkeypatch.setattr(
        builder, "EXPECTED_CONTRACT_SHA256", hashlib.sha256(content).hexdigest()
    )
    with pytest.raises((builder.KpiReferencePlanError, Exception)):
        builder.load_contract(isolated_root)


def test_canonical_row_tamper_rejected_when_catalog_hash_is_rebound(
    isolated_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = isolated_root / builder.KPI_CATALOG_PATH
    path.chmod(0o600)
    catalog = yaml.safe_load(path.read_text())
    catalog["kpis"][0]["formula"] = "SECRET_CANARY_ST1205"
    content = yaml.safe_dump(catalog, sort_keys=False, allow_unicode=True).encode()
    path.write_bytes(content)
    monkeypatch.setattr(
        builder, "KPI_CATALOG_SHA256", hashlib.sha256(content).hexdigest()
    )
    with pytest.raises(builder.KpiReferencePlanError) as captured:
        builder.load_contract(isolated_root)
    assert "SECRET_CANARY" not in str(captured.value)


@pytest.mark.parametrize(
    ("constant", "artifact_index", "old", "new"),
    [
        ("ST1201_ARTIFACTS", 1, "measurement_observed", "measurement_claimed"),
        ("ST1203_ARTIFACTS", 1, "top_rows_only", "all_rows_complete"),
        ("ST1204_ARTIFACTS", 1, "len(self.rows) != 2", "len(self.rows) != 3"),
    ],
)
def test_predecessor_semantic_tamper_rejected_when_hash_is_rebound(
    isolated_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    constant: str,
    artifact_index: int,
    old: str,
    new: str,
) -> None:
    artifacts = getattr(builder, constant)
    target = artifacts[artifact_index][0]
    path = isolated_root / target
    source = path.read_text()
    assert old in source
    path.write_text(source.replace(old, new, 1))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(builder, constant, _rebind_artifact(artifacts, target, digest))
    with pytest.raises(builder.KpiReferencePlanError):
        builder.load_contract(isolated_root)


@pytest.mark.parametrize("relative", [builder.STORY_PATH, builder.HELPER_PATH])
def test_authority_or_helper_hash_drift_is_rejected(
    isolated_root: Path, relative: Path
) -> None:
    path = isolated_root / relative
    path.chmod(0o600)
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(builder.KpiReferencePlanError):
        builder.load_contract(isolated_root)


def test_oversized_contract_is_rejected(
    isolated_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"x" * (builder.MAX_SOURCE_BYTES + 1)
    (isolated_root / builder.CONTRACT_PATH).write_bytes(content)
    monkeypatch.setattr(
        builder, "EXPECTED_CONTRACT_SHA256", hashlib.sha256(content).hexdigest()
    )
    with pytest.raises((builder.KpiReferencePlanError, StagingDeploymentContractError)):
        builder.load_contract(isolated_root)


def test_input_symlink_target_is_rejected(isolated_root: Path) -> None:
    target = isolated_root / builder.CONTRACT_PATH
    replacement = target.with_name("elsewhere.yaml")
    replacement.write_bytes(target.read_bytes())
    target.unlink()
    target.symlink_to(replacement.name)
    with pytest.raises((builder.KpiReferencePlanError, Exception)):
        builder.load_contract(isolated_root)


def test_input_symlink_ancestor_is_rejected(isolated_root: Path) -> None:
    changes = isolated_root / "changes"
    moved = isolated_root / "changes-real"
    changes.rename(moved)
    changes.symlink_to(moved.name, target_is_directory=True)
    with pytest.raises((builder.KpiReferencePlanError, Exception)):
        builder.load_contract(isolated_root)


def test_nonregular_contract_is_rejected(isolated_root: Path) -> None:
    target = isolated_root / builder.CONTRACT_PATH
    target.unlink()
    target.mkdir()
    with pytest.raises((builder.KpiReferencePlanError, Exception)):
        builder.load_contract(isolated_root)


def test_output_symlink_is_rejected(isolated_root: Path) -> None:
    target = isolated_root / builder.REFERENCE_PLAN_PATH
    target.unlink()
    outside = isolated_root / "outside.json"
    outside.write_text("unchanged")
    target.symlink_to(outside)
    with pytest.raises((builder.KpiReferencePlanError, Exception)):
        builder.build(isolated_root)
    assert outside.read_text() == "unchanged"


def test_output_mode_drift_is_detected_without_write(isolated_root: Path) -> None:
    target = isolated_root / builder.REFERENCE_PLAN_PATH
    target.chmod(0o600)
    before = target.read_bytes()
    with pytest.raises((builder.KpiReferencePlanError, Exception)):
        builder.build(isolated_root, check=True)
    assert target.read_bytes() == before
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_builder_ast_has_no_external_or_runtime_capability() -> None:
    source = (REPOSITORY_ROOT / builder.GENERATOR_PATH).read_text()
    tree = ast.parse(source)
    forbidden_imports = {
        "boto3",
        "botocore",
        "http",
        "os",
        "requests",
        "socket",
        "sqlalchemy",
        "sqlite3",
        "subprocess",
        "urllib",
    }
    imported: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    assert imported.isdisjoint(forbidden_imports)
    assert calls.isdisjoint(
        {
            "eval",
            "exec",
            "compile",
            "system",
            "popen",
            "connect",
            "request",
            "execute",
        }
    )


def test_builder_uses_only_fixed_owned_output_paths() -> None:
    assert builder.GENERATED_PATHS == (
        builder.REFERENCE_PLAN_PATH,
        builder.MANIFEST_PATH,
    )
    assert all(
        not path.is_absolute() and ".." not in path.parts
        for path in builder.GENERATED_PATHS
    )

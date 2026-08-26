"""Owner generation, provenance, and V1 compatibility tests for ST-1602 V2."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import stat

import pytest
import yaml

from scripts import build_st1602_slo_alert_runtime as generator


def _isolated_repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    required = {
        *generator.SOURCE_PATHS,
        *(Path(path) for _role, path, _digest in generator.AUTHORITY_SOURCES),
        *(Path(path) for path, _digest in generator.DEPENDENCY_SOURCES),
        *(Path(path) for path, _digest in generator.V1_SOURCES),
        generator.HELPER_PATH,
    }
    for relative in required:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(generator.REPO_ROOT / relative, target)
    return root


def test_render_is_deterministic_and_installed_outputs_are_exact() -> None:
    first = generator.render_outputs()
    second = generator.render_outputs()
    assert first == second
    assert tuple(first) == generator.GENERATED_PATHS
    for relative, expected in first.items():
        assert (generator.REPO_ROOT / relative).read_bytes() == expected


def test_owner_check_is_no_write() -> None:
    paths = [generator.REPO_ROOT / path for path in generator.GENERATED_PATHS]
    before = {
        path: (
            path.read_bytes(),
            path.stat().st_mtime_ns,
            stat.S_IMODE(path.stat().st_mode),
        )
        for path in paths
    }
    assert generator.main(["--check"]) == 0
    after = {
        path: (
            path.read_bytes(),
            path.stat().st_mtime_ns,
            stat.S_IMODE(path.stat().st_mode),
        )
        for path in paths
    }
    assert after == before


def test_isolated_generation_is_atomic_and_checkable(tmp_path: Path) -> None:
    root = _isolated_repository(tmp_path)
    generator.build(root)
    for relative in generator.GENERATED_PATHS:
        path = root / relative
        assert path.is_file() and not path.is_symlink()
        assert stat.S_IMODE(path.stat().st_mode) == 0o644
        assert not tuple(path.parent.glob(f".{path.name}.*.tmp"))
    generator.build(root, check=True)


def test_manifest_binds_all_owned_sources_and_generated_artifacts() -> None:
    manifest = yaml.safe_load(
        (generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes()
    )
    assert manifest["source_artifact_count"] == len(generator.SOURCE_PATHS)
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_PATHS
    ]
    assert manifest["generated_artifact_count"] == 3
    assert manifest["boundary"]["external_action_count"] == 0
    assert manifest["boundary"]["formal_tst_027"] == "NOT_EXECUTED"
    assert manifest["boundary"]["formal_tst_028"] == "NOT_EXECUTED"


def test_v1_owner_artifacts_are_byte_compatible() -> None:
    generator.v1.build(check=True)


def test_contract_activation_route_or_false_claim_mutations_are_rejected() -> None:
    contract = deepcopy(generator.load_contract())
    for section, field, value in (
        ("alert_routing", "notifications_enabled", True),
        ("alert_routing", "channel", "smtp"),
        ("runtime_boundary", "external_actions", 1),
        ("runtime_boundary", "production", "READY"),
        ("compiler", "actual_measurement_claim", True),
        ("verification_boundary", "formal_tst_027", "PASS"),
    ):
        mutated = deepcopy(contract)
        mutated[section][field] = value
        with pytest.raises(generator.SloAlertRuntimeBuildError):
            generator.validate_contract(mutated)


def test_tracked_dependency_is_semantic_and_canonical_drift_is_rejected(
    tmp_path: Path,
) -> None:
    root = _isolated_repository(tmp_path)
    dependency = Path(generator.DEPENDENCY_SOURCES[0][0])
    (root / dependency).write_bytes((root / dependency).read_bytes() + b"\ndrift\n")
    assert generator.render_outputs(root)

    canonical = root / generator.ALERT_PATH
    canonical.write_bytes(canonical.read_bytes() + b"\ndrift\n")
    with pytest.raises(generator.SloAlertRuntimeBuildError):
        generator.render_outputs(root)


def test_generated_catalog_and_fixture_are_canonical_utf8_json() -> None:
    catalog = (generator.REPO_ROOT / generator.CATALOG_PATH).read_bytes()
    fixture = (generator.REPO_ROOT / generator.FIXTURE_PATH).read_bytes()
    for content in (catalog, fixture):
        assert content.endswith(b"\n")
        assert b"\r" not in content
        assert json.loads(content)


def test_generated_evidence_never_claims_formal_live_or_production_success() -> None:
    evidence = yaml.safe_load(
        (generator.REPO_ROOT / generator.EVIDENCE_PATH).read_bytes()
    )
    assert evidence["inventory"] == {
        "typed_slo_rules": 14,
        "typed_alert_rules": 20,
        "runbook_catalog_rows": 20,
        "owner_routes": 20,
        "runbook_routes": 20,
        "recorded_slo_windows": 14,
        "recorded_alert_observations": 20,
    }
    boundary = evidence["safety_boundary"]
    assert boundary["external_action_count"] == 0
    assert boundary["notification_delivery_claim"] is False
    assert boundary["actual_slo_attainment_claim"] is False
    assert boundary["formal_tst_027"] == "NOT_EXECUTED"
    assert boundary["formal_tst_028"] == "NOT_EXECUTED"
    assert boundary["production"] == "NOT_EXECUTED"

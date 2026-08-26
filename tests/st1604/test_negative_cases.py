"""Fail-closed and hostile-boundary tests for the ST-1604 builder."""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts import build_st1505_staging_deployment as base
from scripts import build_st1604_performance_load_reference_plan as generator


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("document", "executable", True),
        ("document", "interface_only", False),
        ("document", "decision", "READY"),
        ("document", "approval", "approved"),
        ("document", "story_acceptance", True),
        ("document", "production_eligible", True),
        ("test_suite_rule", "selected_tool", "k6"),
        ("test_suite_rule", "runner", "runner"),
        ("test_suite_rule", "version", "1"),
        ("test_suite_rule", "executor", "host"),
        ("test_suite_rule", "selected_environment", "staging"),
        ("test_suite_rule", "release_evidence_status", "PASS"),
        ("test_suite_rule", "release_evidence", "artifact"),
        ("target_surface_defaults", "endpoint", "https://example.invalid"),
        ("target_surface_defaults", "protocol", "HTTP"),
        ("target_surface_defaults", "authentication", "bearer"),
        ("target_surface_defaults", "scenarios", ["load"]),
        ("target_surface_defaults", "scenario_mix", [100]),
        ("target_surface_defaults", "fixtures", ["fixture"]),
        ("target_surface_defaults", "artifacts", ["report"]),
        ("target_surface_defaults", "deployment", "staging"),
        ("slo_projection_rule", "selected_slo_ids", ["SLO-001"]),
        ("slo_projection_rule", "evaluations", ["PASS"]),
        ("slo_projection_rule", "targets_met", ["SLO-001"]),
        ("slo_projection_rule", "capacities", ["100rps"]),
        ("measurement_requirements", "values", [0]),
        ("measurement_requirements", "evidence", ["report"]),
        ("workload_defaults", "concurrency", 1),
        ("workload_defaults", "duration", "1m"),
        ("workload_defaults", "arrival_rate", 1),
        ("workload_defaults", "request_count", 1),
        ("workload_defaults", "worker_job_count", 1),
        ("workload_defaults", "dataset", "fixture"),
        ("workload_defaults", "headers", ["Authorization"]),
        ("workload_defaults", "payloads", ["payload"]),
        ("resource_and_cost_defaults", "cpu_cap", 1),
        ("resource_and_cost_defaults", "memory_cap", 1),
        ("resource_and_cost_defaults", "db_connection_cap", 1),
        ("resource_and_cost_defaults", "queue_depth_cap", 1),
        ("resource_and_cost_defaults", "cost_cap", 1),
        ("resource_and_cost_defaults", "currency", "JPY"),
        ("resource_and_cost_defaults", "stop_conditions", ["cost"]),
        ("resource_and_cost_defaults", "scale_caps", ["worker=1"]),
        ("resource_and_cost_defaults", "execution_permitted", True),
        ("report_defaults", "status", "PASS"),
        ("report_defaults", "results", [0]),
        ("report_defaults", "metrics", [0]),
        ("report_defaults", "errors", [0]),
        ("report_defaults", "capacity_claim", "100rps"),
        ("report_defaults", "slo_target_claim", "met"),
        ("activation_defaults", "enabled", True),
        ("activation_defaults", "load_execution", "EXECUTED"),
        ("activation_defaults", "network_access", "ALLOWED"),
        ("activation_defaults", "credential_access", "ALLOWED"),
        ("verification_defaults", "formal_tst_027", "PASS"),
        ("verification_defaults", "actual_load", "PASS"),
        ("verification_defaults", "staging", "READY"),
        ("verification_defaults", "production", "READY"),
    ],
)
def test_forbidden_selection_execution_or_claim_is_rejected(
    section: str,
    field: str,
    value: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract[section][field] = value
    with pytest.raises(generator.PerformanceLoadReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("replacement", [False, True, 0.0, "0"])
def test_bool_float_and_string_do_not_bypass_exact_integer_zero(
    replacement: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract["activation_defaults"]["action_counts"]["load"] = replacement
    with pytest.raises(generator.PerformanceLoadReferenceError):
        generator.validate_contract(contract)


def _remove_top(value: dict[str, Any]) -> None:
    value.pop("report_defaults")


def _add_top(value: dict[str, Any]) -> None:
    value["unknown"] = None


def _add_nested(value: dict[str, Any]) -> None:
    value["activation_defaults"]["unknown"] = None


def _reverse_sources(value: dict[str, Any]) -> None:
    value["authority"]["sources"].reverse()


def _bool_count(value: dict[str, Any]) -> None:
    value["slo_projection_rule"]["exact_count"] = True


@pytest.mark.parametrize(
    "mutation",
    [_remove_top, _add_top, _add_nested, _reverse_sources, _bool_count],
)
def test_missing_unknown_reordered_and_type_drift_are_rejected(
    mutation: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    mutation(contract)  # type: ignore[operator]
    with pytest.raises(generator.PerformanceLoadReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    "payload",
    [
        b"document: {}\ndocument: {}\n",
        b"document: &shared {}\nauthority: *shared\n",
        b"document: !!python/object/apply:os.system [id]\n",
        b"base: &base {enabled: false}\nmerged: {<<: *base}\n",
    ],
)
def test_yaml_duplicate_alias_tag_and_merge_are_rejected(
    isolated_repository: Path,
    payload: bytes,
) -> None:
    (isolated_repository / generator.CONTRACT_PATH).write_bytes(payload)
    with pytest.raises(
        (generator.PerformanceLoadReferenceError, base.StagingDeploymentContractError)
    ):
        generator.load_contract(isolated_repository)


def test_oversized_contract_is_rejected(isolated_repository: Path) -> None:
    path = isolated_repository / generator.CONTRACT_PATH
    path.write_bytes(b"x" * (generator.MAX_SOURCE_BYTES + 1))
    with pytest.raises(
        (generator.PerformanceLoadReferenceError, base.StagingDeploymentContractError)
    ):
        generator.load_contract(isolated_repository)


def test_symlink_contract_is_rejected(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    contract = isolated_repository / generator.CONTRACT_PATH
    outside = tmp_path / "outside.yaml"
    outside.write_bytes(contract.read_bytes())
    contract.unlink()
    contract.symlink_to(outside)
    with pytest.raises(base.StagingDeploymentContractError):
        generator.load_contract(isolated_repository)


def test_symlink_contract_ancestor_is_rejected(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    changes = isolated_repository / "changes"
    moved = tmp_path / "changes"
    changes.rename(moved)
    changes.symlink_to(moved, target_is_directory=True)
    with pytest.raises(base.StagingDeploymentContractError):
        generator.load_contract(isolated_repository)


def test_output_symlink_target_is_rejected(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    target = isolated_repository / generator.REFERENCE_PLAN_PATH
    target.parent.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside")
    target.symlink_to(outside)
    with pytest.raises(base.StagingDeploymentContractError):
        generator.build(isolated_repository)
    assert outside.read_bytes() == b"outside"


def test_path_traversal_is_rejected(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generator, "CONTRACT_PATH", Path("../outside.yaml"))
    with pytest.raises(base.StagingDeploymentContractError):
        generator.load_contract(isolated_repository)


@pytest.mark.parametrize(
    "relative",
    [
        generator.SLO_PATH,
        generator.TEST_CATALOG_PATH,
        generator.STORY_PATH,
        generator.ST1505_CONTRACT_PATH,
        generator.ST1505_PLAN_PATH,
        generator.ST1505_MANIFEST_PATH,
        generator.ST1601_PATH,
    ],
)
def test_authority_or_predecessor_byte_drift_is_rejected(
    isolated_repository: Path,
    relative: Path,
) -> None:
    path = isolated_repository / relative
    path.write_bytes(path.read_bytes() + b"\ndrift\n")
    if relative == generator.ST1601_PATH:
        generator.render_outputs(isolated_repository)
    else:
        with pytest.raises(generator.PerformanceLoadReferenceError):
            generator.render_outputs(isolated_repository)


def test_slo_semantic_drift_is_rejected_even_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = isolated_repository / generator.SLO_PATH
    catalog = yaml.safe_load(path.read_bytes())
    catalog["slos"][0]["measurement_status"] = "PASS"
    path.write_text(yaml.safe_dump(catalog, sort_keys=False), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rebound = tuple(
        (role, source, digest if source == generator.SLO_PATH.as_posix() else expected)
        for role, source, expected in generator.EXPECTED_SOURCES
    )
    monkeypatch.setattr(generator, "EXPECTED_SOURCES", rebound)
    contract = yaml.safe_load(
        (isolated_repository / generator.CONTRACT_PATH).read_bytes()
    )
    for source in contract["authority"]["sources"]:
        if source["role"] == "slo_catalog":
            source["sha256"] = digest
    (isolated_repository / generator.CONTRACT_PATH).write_text(
        yaml.safe_dump(contract, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(generator.PerformanceLoadReferenceError):
        generator.render_outputs(isolated_repository)


def test_predecessor_semantic_drift_is_rejected_even_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = isolated_repository / generator.ST1505_CONTRACT_PATH
    contract = yaml.safe_load(path.read_bytes())
    contract["execution_boundary"]["activation_enabled"] = True
    path.write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rebound = tuple(
        (relative, digest if relative == generator.ST1505_CONTRACT_PATH else expected)
        for relative, expected in generator.EXPECTED_PREDECESSORS
    )
    monkeypatch.setattr(generator, "EXPECTED_PREDECESSORS", rebound)
    authored = yaml.safe_load(
        (isolated_repository / generator.CONTRACT_PATH).read_bytes()
    )
    authored["predecessors"][0]["bindings"][0]["sha256"] = digest
    (isolated_repository / generator.CONTRACT_PATH).write_text(
        yaml.safe_dump(authored, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(generator.PerformanceLoadReferenceError):
        generator.render_outputs(isolated_repository)


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("eligible",), True),
        (("mapping_policy", "complete_mapping"), True),
        (("mapping_policy", "configured_mapping_count"), 13),
        (("selected_provider_name",), "aws"),
        (("selected_profile_id",), "default-profile"),
        (("default_profile_id",), "default-profile"),
        (("fallback_profile_id",), "fallback-profile"),
        (
            ("aws_reference_boundary", "role"),
            "OPTIONAL_HISTORICAL_REFERENCE_MAPPINGS_ONLY",
        ),
        (
            ("aws_reference_boundary", "canonical_story_deliverables"),
            "REPLACED_BY_PORTABLE_OVERLAY",
        ),
        (
            ("aws_reference_boundary", "non_aws_owner_managed_profiles"),
            "REPLACEMENT_IMPLEMENTATION_PATHS",
        ),
        (("aws_reference_boundary", "selected_binding"), True),
        (("aws_reference_boundary", "eligibility_shortcut"), True),
        (("aws_reference_boundary", "admission_requirement"), True),
        (("aws_reference_boundary", "evidence_substitute"), True),
    ),
)
def test_provider_neutral_staging_shortcut_is_rejected_after_byte_rebind(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    path: tuple[str, ...],
    value: object,
) -> None:
    plan_path = isolated_repository / generator.ST1505_PLAN_PATH
    plan = json.loads(plan_path.read_bytes())
    target = plan["provider_neutral_staging_admission"]
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    plan_path.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    rebound = tuple(
        (relative, digest if relative == generator.ST1505_PLAN_PATH else expected)
        for relative, expected in generator.EXPECTED_PREDECESSORS
    )
    monkeypatch.setattr(generator, "EXPECTED_PREDECESSORS", rebound)
    authored = yaml.safe_load(
        (isolated_repository / generator.CONTRACT_PATH).read_bytes()
    )
    authored["predecessors"][0]["bindings"][1]["sha256"] = digest
    (isolated_repository / generator.CONTRACT_PATH).write_text(
        yaml.safe_dump(authored, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(generator.PerformanceLoadReferenceError) as captured:
        generator.render_outputs(isolated_repository)
    assert "aws" not in str(captured.value).lower()


def test_current_canonical_reference_cannot_be_demoted_after_byte_rebind(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_path = isolated_repository / generator.ST1505_PLAN_PATH
    plan = json.loads(plan_path.read_bytes())
    plan["reference_architecture"]["classification"] = (
        "OPTIONAL_HISTORICAL_AWS_STAGING_REFERENCE_MAPPINGS_ONLY"
    )
    plan_path.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        generator,
        "EXPECTED_PREDECESSORS",
        tuple(
            (
                relative,
                digest if relative == generator.ST1505_PLAN_PATH else expected,
            )
            for relative, expected in generator.EXPECTED_PREDECESSORS
        ),
    )
    authored = yaml.safe_load(
        (isolated_repository / generator.CONTRACT_PATH).read_bytes()
    )
    authored["predecessors"][0]["bindings"][1]["sha256"] = digest
    (isolated_repository / generator.CONTRACT_PATH).write_text(
        yaml.safe_dump(authored, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(generator.PerformanceLoadReferenceError):
        generator.render_outputs(isolated_repository)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("aws_reference_role", "OPTIONAL_HISTORICAL_REFERENCE_MAPPINGS_ONLY"),
        ("canonical_story_deliverables", "REPLACED_BY_PORTABLE_OVERLAY"),
        ("portable_implementation_paths", "REPLACEMENT_IMPLEMENTATION_PATHS"),
    ),
)
def test_manifest_canonical_reference_boundary_cannot_be_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
) -> None:
    manifest_path = isolated_repository / generator.ST1505_MANIFEST_PATH
    manifest = yaml.safe_load(manifest_path.read_bytes())
    manifest["boundary"][field] = value
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
    )
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        generator,
        "EXPECTED_PREDECESSORS",
        tuple(
            (
                relative,
                digest if relative == generator.ST1505_MANIFEST_PATH else expected,
            )
            for relative, expected in generator.EXPECTED_PREDECESSORS
        ),
    )
    authored = yaml.safe_load(
        (isolated_repository / generator.CONTRACT_PATH).read_bytes()
    )
    authored["predecessors"][0]["bindings"][2]["sha256"] = digest
    (isolated_repository / generator.CONTRACT_PATH).write_text(
        yaml.safe_dump(authored, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(generator.PerformanceLoadReferenceError):
        generator.render_outputs(isolated_repository)


def test_failure_is_stable_sanitized_and_does_not_echo_rejected_value() -> None:
    canary = "secret-canary-endpoint-value"
    contract = deepcopy(generator.load_contract())
    contract["target_surface_defaults"]["endpoint"] = canary
    with pytest.raises(generator.PerformanceLoadReferenceError) as caught:
        generator.validate_contract(contract)
    assert canary not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_builder_ast_has_no_external_runtime_or_action_surface() -> None:
    source = (generator.REPO_ROOT / generator.GENERATOR_PATH).read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    assert imported.isdisjoint(
        {
            "boto3",
            "httpx",
            "requests",
            "socket",
            "subprocess",
            "urllib",
            "selenium",
            "playwright",
        }
    )
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert called.isdisjoint(
        {"eval", "exec", "getenv", "Popen", "system", "sleep", "urlopen"}
    )
    assert attributes.isdisjoint(
        {"connect", "execute", "publish", "send", "request", "navigate", "getenv"}
    )

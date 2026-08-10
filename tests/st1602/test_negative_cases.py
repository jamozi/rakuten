"""Initial fail-closed tests for the ST-1602 builder."""

from __future__ import annotations

from copy import deepcopy
import ast
import hashlib
from pathlib import Path

import pytest
import yaml

from scripts import build_st1505_staging_deployment as base
from scripts import build_st1602_slo_alert_reference_plan as generator


def test_notification_activation_is_rejected() -> None:
    contract = deepcopy(generator.load_contract())
    contract["routing_defaults"]["notifications_enabled"] = True
    with pytest.raises(generator.SloAlertReferenceError):
        generator.validate_contract(contract)


def test_bool_does_not_bypass_zero_count() -> None:
    contract = deepcopy(generator.load_contract())
    contract["verification_defaults"]["implemented_count"] = False
    with pytest.raises(generator.SloAlertReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("document", "executable", True),
        ("document", "decision", "READY"),
        ("document", "approval", "approved"),
        ("document", "story_acceptance", True),
        ("document", "production_eligible", True),
        ("open_decision", "safe_default", "EMAIL"),
        ("open_decision", "channel", "secret-channel"),
        ("routing_defaults", "mode", "PAGER"),
        ("routing_defaults", "owner", "ops@example.invalid"),
        ("routing_defaults", "runbook_links", ["RB-001"]),
        ("routing_defaults", "external_actions", ["notify"]),
        ("telemetry_defaults", "connected", True),
        ("telemetry_defaults", "metric", "requests"),
        ("telemetry_defaults", "formula", "rate(x)"),
        ("telemetry_defaults", "trigger", "x > 1"),
        ("telemetry_defaults", "window", "5m"),
        ("telemetry_defaults", "error_budget", "1%"),
        ("telemetry_defaults", "backend", "vendor"),
        ("verification_defaults", "tested_count", 20),
        ("verification_defaults", "formal_tst_027", "PASS"),
        ("verification_defaults", "production", "READY"),
    ],
)
def test_forbidden_selection_execution_or_false_claim_is_rejected(
    section: str,
    field: str,
    value: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract[section][field] = value
    with pytest.raises(generator.SloAlertReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.pop("routing_defaults"),
        lambda value: value.update({"unknown": None}),
        lambda value: value["routing_defaults"].update({"unknown": None}),
        lambda value: value["authority"]["sources"].reverse(),
        lambda value: value["projection_rules"].update({"exact_slo_count": True}),
    ],
)
def test_missing_unknown_reordered_and_type_drift_are_rejected(
    mutation: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    mutation(contract)  # type: ignore[operator]
    with pytest.raises(generator.SloAlertReferenceError):
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
    path = isolated_repository / generator.CONTRACT_PATH
    path.write_bytes(payload)
    with pytest.raises(
        (
            generator.SloAlertReferenceError,
            base.StagingDeploymentContractError,
        )
    ):
        generator.load_contract(isolated_repository)


def test_oversized_contract_is_rejected(isolated_repository: Path) -> None:
    path = isolated_repository / generator.CONTRACT_PATH
    path.write_bytes(b"x" * (generator.MAX_SOURCE_BYTES + 1))
    with pytest.raises(
        (
            generator.SloAlertReferenceError,
            base.StagingDeploymentContractError,
        )
    ):
        generator.load_contract(isolated_repository)


def test_symlink_contract_and_ancestor_are_rejected(
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


@pytest.mark.parametrize("relative", [generator.ST1601_PATH, generator.SLO_PATH])
def test_dependency_or_catalog_byte_drift_is_rejected(
    isolated_repository: Path,
    relative: Path,
) -> None:
    path = isolated_repository / relative
    path.write_bytes(path.read_bytes() + b"\ndrift\n")
    with pytest.raises(generator.SloAlertReferenceError):
        generator.render_outputs(isolated_repository)


def test_catalog_semantic_drift_is_rejected_even_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = isolated_repository / generator.SLO_PATH
    catalog = yaml.safe_load(path.read_bytes())
    catalog["slos"][0]["implementation_status"] = "IMPLEMENTED"
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
    with pytest.raises(generator.SloAlertReferenceError):
        generator.render_outputs(isolated_repository)


def test_failure_is_stable_sanitized_and_does_not_echo_rejected_value() -> None:
    canary = "secret-canary-routing-value"
    contract = deepcopy(generator.load_contract())
    contract["routing_defaults"]["channel"] = canary
    with pytest.raises(generator.SloAlertReferenceError) as caught:
        generator.validate_contract(contract)
    assert canary not in str(caught.value)
    assert caught.value.__cause__ is None


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
        {"boto3", "httpx", "requests", "socket", "subprocess", "urllib"}
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
    assert called.isdisjoint({"eval", "exec", "getenv", "Popen", "system"})
    assert attributes.isdisjoint(
        {"connect", "execute", "publish", "send", "notify", "request"}
    )

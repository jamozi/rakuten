"""Hostile owner-generator boundary tests for ST-0708."""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
from pathlib import Path

import pytest
import yaml

from scripts import (
    build_st0708_openai_live_bounded_evaluation_reference_plan as generator,
)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    (
        ("document", "executable", True),
        ("document", "interface_only", False),
        ("document", "runtime_eligible", True),
        ("document", "release_eligible", True),
        ("open_decision", "resolved", True),
        ("open_decision", "safe_default", "LIVE"),
        ("activation_boundary", "enabled", True),
        ("activation_boundary", "external_actions", ["provider-call"]),
    ),
)
def test_historical_compatibility_contract_cannot_gain_authority(
    section: str, field: str, value: object
) -> None:
    contract = deepcopy(generator.load_contract())
    contract[section][field] = value
    with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("replacement", (False, True, 0.0, "0", 1))
@pytest.mark.parametrize("action", generator.ACTION_COUNT_KEYS)
def test_non_exact_zero_does_not_bypass_historical_action_boundary(
    action: str, replacement: object
) -> None:
    contract = deepcopy(generator.load_contract())
    contract["activation_boundary"]["action_counts"][action] = replacement
    with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    "payload",
    (
        b"document: {}\ndocument: {}\n",
        b"document: &shared {}\nauthority: *shared\n",
        b"document: !!python/object/apply:os.system [id]\n",
        b"base: &base {enabled: false}\nmerged: {<<: *base}\n",
    ),
)
def test_yaml_duplicate_alias_tag_and_merge_are_rejected(
    isolated_repository: Path, payload: bytes
) -> None:
    (isolated_repository / generator.RUNTIME_CONTRACT_PATH).write_bytes(payload)
    with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError):
        generator.render_outputs(isolated_repository)


def test_oversized_runtime_contract_is_rejected(isolated_repository: Path) -> None:
    path = isolated_repository / generator.RUNTIME_CONTRACT_PATH
    path.write_bytes(b"x" * (generator.MAX_SOURCE_BYTES + 1))
    with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError):
        generator.render_outputs(isolated_repository)


def test_symlink_contract_is_rejected(
    isolated_repository: Path, tmp_path: Path
) -> None:
    contract = isolated_repository / generator.RUNTIME_CONTRACT_PATH
    outside = tmp_path / "outside.yaml"
    outside.write_bytes(contract.read_bytes())
    contract.unlink()
    contract.symlink_to(outside)
    with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError):
        generator.render_outputs(isolated_repository)


def test_output_symlink_target_is_rejected(
    isolated_repository: Path, tmp_path: Path
) -> None:
    target = isolated_repository / generator.REQUEST_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside")
    target.symlink_to(outside)
    with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError):
        generator.build(isolated_repository)
    assert outside.read_bytes() == b"outside"


def test_pinned_dependency_byte_drift_is_rejected(
    isolated_repository: Path,
) -> None:
    relative = Path("changes/st-0703/fixtures/recorded/success-structured.json")
    path = isolated_repository / relative
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError):
        generator.render_outputs(isolated_repository)


def test_st0703_semantic_drift_is_rejected_even_if_runtime_contract_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = isolated_repository / "tests/st0703/test_adapter.py"
    source.write_text(
        source.read_text(encoding="utf-8").replace(
            'prompt_version="PRM-004-v1"',
            'prompt_version="PRM-OTHER-v1"',
            1,
        ),
        encoding="utf-8",
    )
    runtime = isolated_repository / generator.RUNTIME_CONTRACT_PATH
    contract = yaml.safe_load(runtime.read_bytes())
    contract["st0703_recorded_binding"]["binding_source"]["sha256"] = hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    runtime.write_text(
        yaml.safe_dump(contract, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        generator,
        "RUNTIME_CONTRACT_SHA256",
        hashlib.sha256(runtime.read_bytes()).hexdigest(),
    )
    with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError):
        generator.render_outputs(isolated_repository)


def test_failure_is_stable_and_does_not_echo_rejected_material() -> None:
    canary = "secret-canary-live-endpoint-value"
    with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError) as caught:
        generator._string(canary + "x" * 600)
    assert canary not in str(caught.value)
    assert caught.value.__cause__ is None


def test_builder_has_no_external_provider_or_network_surface() -> None:
    tree = ast.parse(
        (generator.REPO_ROOT / generator.GENERATOR_PATH).read_text(encoding="utf-8")
    )
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert imports.isdisjoint(
        {"openai", "boto3", "httpx", "requests", "socket", "subprocess", "urllib"}
    )
    attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert attributes.isdisjoint(
        {"connect", "request", "send", "resolve_credentials", "publish"}
    )

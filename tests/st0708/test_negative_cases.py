"""Hostile closed-boundary tests for the ST-0708 builder."""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any, Callable

import pytest
import yaml

from scripts import (
    build_st0708_openai_live_bounded_evaluation_reference_plan as generator,
)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("document", "executable", True),
        ("document", "interface_only", False),
        ("document", "runtime_eligible", True),
        ("document", "decision", "READY"),
        ("document", "approval", "approved"),
        ("document", "story_acceptance", True),
        ("document", "release_candidate", True),
        ("document", "release_eligible", True),
        ("document", "production_eligible", True),
        ("open_decision", "resolved", True),
        ("open_decision", "blocking", False),
        ("open_decision", "safe_default", "LIVE"),
        ("open_decision", "credentials_available", True),
        ("open_decision", "live_execution_authorized", True),
        ("candidate_selection", "model_id", "model"),
        ("candidate_selection", "prompt_id", "prompt"),
        ("candidate_selection", "provider_id", "provider"),
        ("dataset_boundary", "approved", True),
        ("dataset_boundary", "locked", True),
        ("dataset_boundary", "dataset_id", "dataset"),
        ("dataset_boundary", "dataset_sha256", "0" * 64),
        ("dataset_boundary", "splits", ["holdout"]),
        ("dataset_boundary", "observed_case_count", 1),
        ("thresholds", "risk_specific_thresholds", ["threshold"]),
        ("thresholds", "zero_tolerance_classes", ["security"]),
        ("thresholds", "statistical_method", "method"),
        ("execution_configuration", "runnable", True),
        ("execution_configuration", "runner", "runner"),
        ("execution_configuration", "command", "evaluate --live"),
        ("execution_configuration", "credential", "secret"),
        ("execution_configuration", "request", "request"),
        ("execution_configuration", "response", "response"),
        ("execution_configuration", "evidence", ["evidence"]),
        ("observations", "status", "PASS"),
        ("observations", "observations", ["observation"]),
        ("observations", "findings", ["finding"]),
        ("observations", "failures", ["failure"]),
        ("observations", "evidence", ["evidence"]),
        ("activation_boundary", "enabled", True),
        ("activation_boundary", "provider", "ALLOWED"),
        ("activation_boundary", "network", "ALLOWED"),
        ("activation_boundary", "credential", "ALLOWED"),
        ("activation_boundary", "external_actions", ["provider-call"]),
        ("verification_boundary", "formal_tst_018", "PASS"),
        ("verification_boundary", "live_evaluation", "PASS"),
        ("verification_boundary", "release_eligible", True),
        ("command_surface", "run", "run"),
        ("command_surface", "commands", ["run"]),
    ],
)
def test_forbidden_selection_execution_or_claim_is_rejected(
    section: str,
    field: str,
    value: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract[section][field] = value
    with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("replacement", [False, True, 0.0, "0", 1])
@pytest.mark.parametrize("action", generator.ACTION_COUNT_KEYS)
def test_non_exact_zero_does_not_bypass_action_boundary(
    action: str,
    replacement: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract["activation_boundary"]["action_counts"][action] = replacement
    with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError):
        generator.validate_contract(contract)


def _remove_top(value: dict[str, Any]) -> None:
    value.pop("observations")


def _add_top(value: dict[str, Any]) -> None:
    value["unknown"] = None


def _add_nested(value: dict[str, Any]) -> None:
    value["candidate_selection"]["unknown"] = None


def _reverse_sources(value: dict[str, Any]) -> None:
    value["authority"]["sources"].reverse()


def _reverse_actions(value: dict[str, Any]) -> None:
    counts = value["activation_boundary"]["action_counts"]
    value["activation_boundary"]["action_counts"] = dict(
        reversed(tuple(counts.items()))
    )


@pytest.mark.parametrize(
    "mutation",
    [_remove_top, _add_top, _add_nested, _reverse_sources, _reverse_actions],
)
def test_missing_unknown_and_reordered_keys_are_rejected(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    contract = deepcopy(generator.load_contract())
    mutation(contract)
    with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError):
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
    with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError):
        generator.load_contract(isolated_repository)


def test_oversized_contract_is_rejected(isolated_repository: Path) -> None:
    path = isolated_repository / generator.CONTRACT_PATH
    path.write_bytes(b"x" * (generator.MAX_SOURCE_BYTES + 1))
    with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError):
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
    with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError):
        generator.load_contract(isolated_repository)


def test_symlink_contract_ancestor_is_rejected(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    changes = isolated_repository / "changes"
    moved = tmp_path / "changes"
    changes.rename(moved)
    changes.symlink_to(moved, target_is_directory=True)
    with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError):
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
    with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError):
        generator.build(isolated_repository)
    assert outside.read_bytes() == b"outside"


def test_output_symlink_ancestor_is_rejected(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    generated = isolated_repository / generator.REFERENCE_PLAN_PATH.parent
    outside = tmp_path / "generated"
    outside.mkdir()
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.symlink_to(outside, target_is_directory=True)
    with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError):
        generator.build(isolated_repository)
    assert not tuple(outside.iterdir())


def test_path_traversal_is_rejected(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generator, "CONTRACT_PATH", Path("../outside.yaml"))
    with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError):
        generator.load_contract(isolated_repository)


@pytest.mark.parametrize("relative", tuple(generator.PINNED_INPUTS))
def test_authority_or_dependency_byte_drift_is_rejected(
    isolated_repository: Path,
    relative: Path,
) -> None:
    path = isolated_repository / relative
    path.write_bytes(path.read_bytes() + b"\ndrift\n")
    with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError):
        generator.render_outputs(isolated_repository)


def test_st0707_semantic_drift_is_rejected_even_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = Path("python/raos/domain/ai/evaluation.py")
    path = isolated_repository / relative
    text = path.read_text(encoding="utf-8").replace(
        'default="BOOTSTRAP_SMOKE_ONLY"',
        'default="LIVE"',
        1,
    )
    path.write_text(text, encoding="utf-8")
    rebound = dict(generator.PINNED_INPUTS)
    rebound[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(generator, "PINNED_INPUTS", rebound)
    with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError):
        generator.render_outputs(isolated_repository)


def test_st0703_semantic_drift_is_rejected_even_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = Path("changes/st-0703/contracts/openai-responses-adapter.v1.yaml")
    path = isolated_repository / relative
    contract = yaml.safe_load(path.read_bytes())
    contract["boundary"]["live_api"] = "USED"
    path.write_text(
        yaml.safe_dump(contract, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    rebound = dict(generator.PINNED_INPUTS)
    rebound[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(generator, "PINNED_INPUTS", rebound)
    with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError):
        generator.render_outputs(isolated_repository)


def test_canonical_story_semantic_drift_is_rejected_even_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = isolated_repository / generator.STORY_PATH
    catalog = yaml.safe_load(path.read_bytes())
    story = next(item for item in catalog["stories"] if item["id"] == "ST-0708")
    story["verification_status"] = "PASS"
    path.write_text(
        yaml.safe_dump(catalog, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    rebound = dict(generator.PINNED_INPUTS)
    rebound[generator.STORY_PATH] = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(generator, "PINNED_INPUTS", rebound)
    with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError):
        generator.render_outputs(isolated_repository)


def test_failure_is_stable_sanitized_and_does_not_echo_rejected_value() -> None:
    canary = "secret-canary-live-endpoint-value"
    contract = deepcopy(generator.load_contract())
    contract["execution_configuration"]["endpoint"] = canary
    with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError) as caught:
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
        {
            "boto3",
            "httpx",
            "requests",
            "socket",
            "subprocess",
            "urllib",
            "sqlalchemy",
            "psycopg",
            "os",
            "random",
            "time",
            "uuid",
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
        {
            "connect",
            "execute",
            "publish",
            "send",
            "request",
            "getenv",
            "resolve_credentials",
        }
    )

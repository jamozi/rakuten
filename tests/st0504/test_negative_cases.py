"""Hostile closed-boundary tests for the ST-0504 builder."""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any, Callable, cast

import pytest
import yaml

from scripts import build_st1505_staging_deployment as base
from scripts import (
    build_st0504_product_identity_human_review_reference_plan as generator,
)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("document", "executable", True),
        ("document", "interface_only", False),
        ("document", "decision", "READY"),
        ("document", "approval", "approved"),
        ("document", "story_acceptance", True),
        ("document", "production_eligible", True),
        ("predecessor", "commit", "0" * 40),
        ("predecessor", "connection_status", "CONNECTED"),
        ("open_decision", "resolved", True),
        ("open_decision", "blocking", False),
        ("open_decision", "safe_default", "AUTOMATIC_MERGE"),
        ("open_decision", "category_rules", ["same-JAN"]),
        ("open_decision", "thresholds", [0.9]),
        ("open_decision", "scores", [100]),
        ("candidate_projection", "candidate_records", ["candidate"]),
        ("candidate_projection", "candidate_count", 0),
        ("candidate_projection", "source_snapshots", ["snapshot"]),
        ("candidate_projection", "input_evidence", ["evidence"]),
        ("human_review_default", "required", False),
        ("human_review_default", "status", "EXECUTED"),
        ("human_review_default", "routing_status", "CONFIGURED"),
        ("human_review_default", "queue", "identity-review"),
        ("human_review_default", "route", "domain-editor"),
        ("human_review_default", "reviewer", "reviewer-1"),
        ("human_review_default", "actor", "actor-1"),
        ("human_review_default", "role", "editor"),
        ("human_review_default", "assignment", "assignment-1"),
        ("human_review_default", "sla", "24h"),
        ("human_review_default", "approval", "approved"),
        ("human_review_default", "review_records", ["review"]),
        ("human_review_default", "delivery_records", ["delivery"]),
        ("identity_defaults", "automatic_merge_enabled", True),
        ("identity_defaults", "automatic_split_enabled", True),
        ("identity_defaults", "category_rule", "same-model"),
        ("identity_defaults", "threshold", 0.9),
        ("identity_defaults", "score", 90),
        ("identity_defaults", "confidence", "HIGH"),
        ("identity_defaults", "canonical_product_id", "product-1"),
        ("identity_defaults", "identity_decisions", ["merge"]),
        ("identity_defaults", "membership_records", ["membership"]),
        ("identity_defaults", "merge_records", ["merge"]),
        ("identity_defaults", "split_records", ["split"]),
        ("identity_defaults", "supersession_records", ["supersede"]),
        ("identity_defaults", "decision_history", ["decision"]),
        ("identity_defaults", "external_actions", ["enqueue"]),
        ("execution_boundary", "enabled", True),
        ("execution_boundary", "rule_engine", "EXECUTED"),
        ("execution_boundary", "human_review", "EXECUTED"),
        ("execution_boundary", "queue", "EXECUTED"),
        ("execution_boundary", "event", "EXECUTED"),
        ("execution_boundary", "repository", "AVAILABLE"),
        ("execution_boundary", "database", "EXECUTED"),
        ("execution_boundary", "provider", "EXECUTED"),
        ("execution_boundary", "live", "EXECUTED"),
        ("verification_boundary", "formal_tst_007", "PASS"),
        ("verification_boundary", "formal_tst_020", "PASS"),
        ("verification_boundary", "human_review", "PASS"),
        ("verification_boundary", "decision_history", "PASS"),
        ("verification_boundary", "production", "READY"),
    ],
)
def test_forbidden_rule_selection_execution_or_claim_is_rejected(
    section: str,
    field: str,
    value: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract[section][field] = value
    with pytest.raises(generator.ProductIdentityReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("replacement", [False, True, 0.0, "0"])
@pytest.mark.parametrize("action", generator.ACTION_COUNT_KEYS)
def test_bool_float_string_and_nonzero_do_not_bypass_exact_zero_actions(
    action: str,
    replacement: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract["execution_boundary"]["action_counts"][action] = replacement
    with pytest.raises(generator.ProductIdentityReferenceError):
        generator.validate_contract(contract)


def _remove_top(value: dict[str, Any]) -> None:
    value.pop("identity_defaults")


def _add_top(value: dict[str, Any]) -> None:
    value["unknown"] = None


def _add_nested(value: dict[str, Any]) -> None:
    value["human_review_default"]["unknown"] = None


def _reverse_sources(value: dict[str, Any]) -> None:
    value["authority"]["sources"].reverse()


def _reverse_actions(value: dict[str, Any]) -> None:
    counts = value["execution_boundary"]["action_counts"]
    value["execution_boundary"]["action_counts"] = dict(reversed(tuple(counts.items())))


@pytest.mark.parametrize(
    "mutation",
    [_remove_top, _add_top, _add_nested, _reverse_sources, _reverse_actions],
)
def test_missing_unknown_and_reordered_keys_are_rejected(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    mutation(contract)
    with pytest.raises(generator.ProductIdentityReferenceError):
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
        (generator.ProductIdentityReferenceError, base.StagingDeploymentContractError)
    ):
        generator.load_contract(isolated_repository)


def test_oversized_contract_is_rejected(isolated_repository: Path) -> None:
    path = isolated_repository / generator.CONTRACT_PATH
    path.write_bytes(b"x" * (generator.MAX_SOURCE_BYTES + 1))
    with pytest.raises(
        (generator.ProductIdentityReferenceError, base.StagingDeploymentContractError)
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


def test_output_symlink_ancestor_is_rejected(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    generated = isolated_repository / generator.REFERENCE_PLAN_PATH.parent
    outside = tmp_path / "generated"
    outside.mkdir()
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.symlink_to(outside, target_is_directory=True)
    with pytest.raises(base.StagingDeploymentContractError):
        generator.build(isolated_repository)
    assert not tuple(outside.iterdir())


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
        generator.OPEN_DECISIONS_PATH,
        generator.TEST_CATALOG_PATH,
        generator.STORY_PATH,
        *(path for path, _digest in generator.EXPECTED_PREDECESSOR_ARTIFACTS),
    ],
)
def test_authority_or_predecessor_byte_drift_is_rejected(
    isolated_repository: Path,
    relative: Path,
) -> None:
    path = isolated_repository / relative
    path.write_bytes(path.read_bytes() + b"\ndrift\n")
    with pytest.raises(generator.ProductIdentityReferenceError):
        generator.render_outputs(isolated_repository)


def test_predecessor_semantic_drift_is_rejected_even_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = generator.EXPECTED_PREDECESSOR_ARTIFACTS[1][0]
    path = isolated_repository / relative
    text = path.read_text(encoding="utf-8").replace(
        'REVIEW_REQUIRED = "REVIEW_REQUIRED"',
        'REVIEW_REQUIRED = "AUTOMATIC_MERGE"',
        1,
    )
    path.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rebound = tuple(
        (candidate, digest if candidate == relative else expected)
        for candidate, expected in generator.EXPECTED_PREDECESSOR_ARTIFACTS
    )
    monkeypatch.setattr(generator, "EXPECTED_PREDECESSOR_ARTIFACTS", rebound)
    contract = yaml.safe_load(
        (isolated_repository / generator.CONTRACT_PATH).read_bytes()
    )
    contract["predecessor"]["artifacts"][1]["sha256"] = digest
    (isolated_repository / generator.CONTRACT_PATH).write_text(
        yaml.safe_dump(contract, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(generator.ProductIdentityReferenceError):
        generator.render_outputs(isolated_repository)


def test_canonical_story_semantic_drift_is_rejected_even_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = isolated_repository / generator.STORY_PATH
    catalog = yaml.safe_load(path.read_bytes())
    story = next(item for item in catalog["stories"] if item["id"] == "ST-0504")
    story["implementation_status"] = "IMPLEMENTED"
    path.write_text(yaml.safe_dump(catalog, sort_keys=False), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rebound = tuple(
        (
            role,
            source,
            digest if source == generator.STORY_PATH.as_posix() else expected,
        )
        for role, source, expected in generator.EXPECTED_SOURCES
    )
    monkeypatch.setattr(generator, "EXPECTED_SOURCES", rebound)
    contract = yaml.safe_load(
        (isolated_repository / generator.CONTRACT_PATH).read_bytes()
    )
    for source in contract["authority"]["sources"]:
        if source["role"] == "story":
            source["sha256"] = digest
    (isolated_repository / generator.CONTRACT_PATH).write_text(
        yaml.safe_dump(contract, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(generator.ProductIdentityReferenceError):
        generator.render_outputs(isolated_repository)


def test_failure_is_stable_sanitized_and_does_not_echo_rejected_value() -> None:
    canary = "secret-canary-review-route-value"
    contract = deepcopy(generator.load_contract())
    contract["human_review_default"]["route"] = canary
    with pytest.raises(generator.ProductIdentityReferenceError) as caught:
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
            "enqueue",
            "approve",
            "merge",
            "split",
            "getenv",
        }
    )
